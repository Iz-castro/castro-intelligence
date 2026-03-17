# -*- coding: utf-8 -*-

"""
Gerencia download de midia recebida via WhatsApp Cloud API
e conversao de formatos de audio para compatibilidade.
"""

import os
import logging
import hashlib
import subprocess
import tempfile
from datetime import datetime

import httpx

from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE, MEDIA_DIR, MAX_MEDIA_SIZE_MB

logger = logging.getLogger("castro_crm.media")


def _normalize_br(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55") and s[4] in ("6","7","8","9"):
        return f"55{s[2:4]}9{s[4:]}"
    return s


MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/amr": ".amr",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
}


def ensure_media_dir():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    for subdir in ("images", "audio", "video", "documents", "stickers", "avatars"):
        os.makedirs(os.path.join(MEDIA_DIR, subdir), exist_ok=True)


def get_subdir_for_type(msg_type):
    mapping = {
        "image": "images",
        "audio": "audio",
        "video": "video",
        "document": "documents",
        "sticker": "stickers",
    }
    return mapping.get(msg_type, "documents")


def convert_audio_to_ogg_opus(input_bytes, input_mime="audio/webm"):
    """
    Converte audio gravado pelo navegador (webm/opus) para OGG/Opus
    que e o formato aceito pelo WhatsApp.
    Retorna os bytes do arquivo OGG ou None em caso de falha.
    """
    # Determinar extensao de entrada
    ext_in = ".webm"
    if "mp4" in input_mime or "m4a" in input_mime:
        ext_in = ".m4a"
    elif "mpeg" in input_mime or "mp3" in input_mime:
        ext_in = ".mp3"
    elif "ogg" in input_mime:
        # Ja pode ser ogg valido, verificar se precisa conversao
        ext_in = ".ogg"

    tmp_in = None
    tmp_out_path = None
    try:
        # Criar arquivo temporario de entrada
        tmp_in = tempfile.NamedTemporaryFile(suffix=ext_in, delete=False)
        tmp_in.write(input_bytes)
        tmp_in.close()

        # Criar caminho de saida
        tmp_out_path = tmp_in.name.replace(ext_in, "_converted.ogg")

        # Executar ffmpeg para converter
        cmd = [
            "ffmpeg",
            "-i", tmp_in.name,
            "-c:a", "libopus",
            "-b:a", "48k",
            "-ar", "48000",
            "-ac", "1",
            "-application", "voip",
            "-f", "ogg",
            "-y",
            tmp_out_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("FFmpeg falhou (code=%d): %s", result.returncode, stderr_text)
            return None

        # Ler resultado
        with open(tmp_out_path, "rb") as f:
            converted = f.read()

        if len(converted) < 100:
            logger.error("Arquivo convertido muito pequeno (%d bytes)", len(converted))
            return None

        logger.info(
            "Audio convertido: %s -> ogg/opus (%d -> %d bytes)",
            ext_in, len(input_bytes), len(converted)
        )
        return converted

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout na conversao de audio")
        return None
    except Exception as exc:
        logger.error("Erro na conversao de audio: %s", exc)
        return None
    finally:
        if tmp_in and os.path.isfile(tmp_in.name):
            try:
                os.remove(tmp_in.name)
            except OSError:
                pass
        if tmp_out_path and os.path.isfile(tmp_out_path):
            try:
                os.remove(tmp_out_path)
            except OSError:
                pass


async def get_media_url(media_id):
    if not WHATSAPP_TOKEN:
        logger.error("WHATSAPP_TOKEN nao configurado")
        return None

    endpoint = f"{GRAPH_API_BASE}/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code != 200:
                logger.error("Falha ao obter URL da midia %s: %s", media_id, resp.text)
                return None
            data = resp.json()
            return {
                "url": data.get("url", ""),
                "mime_type": data.get("mime_type", ""),
                "file_size": data.get("file_size", 0),
                "sha256": data.get("sha256", ""),
            }
        except Exception as exc:
            logger.error("Erro ao consultar midia %s: %s", media_id, exc)
            return None


async def download_media(media_id, msg_type, original_filename=""):
    ensure_media_dir()

    media_info = await get_media_url(media_id)
    if not media_info or not media_info["url"]:
        return None

    file_size = media_info.get("file_size", 0)
    if file_size > MAX_MEDIA_SIZE_MB * 1024 * 1024:
        logger.warning("Midia %s excede limite de %dMB", media_id, MAX_MEDIA_SIZE_MB)
        return None

    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.get(media_info["url"], headers=headers)
            if resp.status_code != 200:
                logger.error("Falha no download da midia %s: HTTP %d", media_id, resp.status_code)
                return None

            content = resp.content
            mime = media_info["mime_type"]
            ext = MIME_EXTENSIONS.get(mime, "")

            if not ext and original_filename:
                _, ext = os.path.splitext(original_filename)
            if not ext:
                ext = ".bin"

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_id = hashlib.sha256(media_id.encode()).hexdigest()[:12]
            filename = f"{timestamp}_{safe_id}{ext}"

            subdir = get_subdir_for_type(msg_type)
            filepath = os.path.join(MEDIA_DIR, subdir, filename)

            with open(filepath, "wb") as f:
                f.write(content)

            relative_path = f"/media/{subdir}/{filename}"
            logger.info("Midia salva: %s (%s, %d bytes)", relative_path, mime, len(content))

            return {
                "path": relative_path,
                "mime_type": mime,
                "size": len(content),
                "filename": original_filename or filename,
            }

        except Exception as exc:
            logger.error("Erro no download da midia %s: %s", media_id, exc)
            return None


def detect_media_type(mime_type):
    if mime_type.startswith("image/"):
        return "image"
    elif mime_type.startswith("audio/"):
        return "audio"
    elif mime_type.startswith("video/"):
        return "video"
    else:
        return "document"


async def save_upload_locally(file_content, filename, mime_type):
    ensure_media_dir()

    msg_type = detect_media_type(mime_type)
    subdir = get_subdir_for_type(msg_type)
    ext = MIME_EXTENSIONS.get(mime_type, "")

    if not ext and filename:
        _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".bin"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_hash = hashlib.sha256(file_content[:1024]).hexdigest()[:12]
    safe_name = f"{timestamp}_{safe_hash}{ext}"

    filepath = os.path.join(MEDIA_DIR, subdir, safe_name)
    with open(filepath, "wb") as f:
        f.write(file_content)

    relative_path = f"/media/{subdir}/{safe_name}"
    logger.info("Upload local salvo: %s (%s, %d bytes)", relative_path, mime_type, len(file_content))

    return {
        "path": relative_path,
        "mime_type": mime_type,
        "size": len(file_content),
        "msg_type": msg_type,
    }


async def upload_media_to_whatsapp(file_content, mime_type, filename=""):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.error("WABA nao configurado para upload")
        return None

    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    if not filename:
        ext = MIME_EXTENSIONS.get(mime_type, ".bin")
        filename = f"upload{ext}"

    files = {"file": (filename, file_content, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, files=files, data=data)
            result = resp.json()
            if resp.status_code in (200, 201):
                media_id = result.get("id", "")
                logger.info("Upload para Meta OK: media_id=%s", media_id)
                return media_id
            else:
                error = result.get("error", {}).get("message", resp.text[:200])
                logger.error("Upload para Meta falhou: %s", error)
                return None
        except Exception as exc:
            logger.error("Erro no upload para Meta: %s", exc)
            return None


async def send_media_message(wa_id, media_id, msg_type, caption=""):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return None

    wa_id = _normalize_br(wa_id)

    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    media_object = {"id": media_id}
    if caption and msg_type in ("image", "video", "document"):
        media_object["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": msg_type,
        msg_type: media_object,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            result = resp.json()
            if resp.status_code == 200:
                wa_msg_id = result.get("messages", [{}])[0].get("id", "")
                logger.info("[WA MEDIA OUT] %s -> %s (type=%s)", wa_id, wa_msg_id, msg_type)
                return {"wa_message_id": wa_msg_id, "status": "sent"}
            else:
                error = result.get("error", {}).get("message", "Erro desconhecido")
                logger.error("[WA MEDIA FAIL] %s: %s", wa_id, error)
                return {"error": error}
        except Exception as exc:
            logger.error("Erro ao enviar midia para %s: %s", wa_id, exc)
            return {"error": str(exc)}
