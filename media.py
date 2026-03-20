# -*- coding: utf-8 -*-

"""
Gerencia download de midia recebida via WhatsApp Cloud API,
conversao de audio e persistencia em disco local, Cloud Storage ou Firestore.
"""

import gzip
import hashlib
import logging
import mimetypes
import os
import subprocess
import tempfile
from datetime import datetime

import httpx

from config import (
    WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    GRAPH_API_BASE,
    MEDIA_DIR,
    MAX_MEDIA_SIZE_MB,
    MEDIA_STORAGE_BACKEND,
    GCS_MEDIA_BUCKET,
    GCS_MEDIA_PREFIX,
    FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB,
    FIRESTORE_MEDIA_MAX_MB,
    FIRESTORE_MEDIA_CHUNK_KB,
)
from firestore_common import collection, document, utcnow

logger = logging.getLogger("castro_crm.media")

_storage_client = None
_storage_backend_logged = False


def _normalize_br(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55") and s[4] in ("6", "7", "8", "9"):
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


def _using_gcs():
    return MEDIA_STORAGE_BACKEND == "gcs" and bool(GCS_MEDIA_BUCKET)


def _using_firestore():
    return MEDIA_STORAGE_BACKEND == "firestore"


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError("google-cloud-storage nao instalado") from exc
        _storage_client = storage.Client()
    return _storage_client


def _get_bucket():
    return _get_storage_client().bucket(GCS_MEDIA_BUCKET)


def _log_storage_backend_once():
    global _storage_backend_logged
    if _storage_backend_logged:
        return
    if _using_gcs():
        logger.info(
            "Midia configurada para Cloud Storage | bucket=%s prefix=%s",
            GCS_MEDIA_BUCKET,
            GCS_MEDIA_PREFIX or "(raiz)",
        )
    elif _using_firestore():
        logger.info(
            "Midia configurada para Firestore | compress_threshold_kb=%d max_mb=%d chunk_kb=%d",
            FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB,
            FIRESTORE_MEDIA_MAX_MB,
            FIRESTORE_MEDIA_CHUNK_KB,
        )
    else:
        logger.info("Midia configurada para filesystem local | dir=%s", MEDIA_DIR)
    _storage_backend_logged = True


def ensure_media_dir():
    _log_storage_backend_once()
    if _using_gcs() or _using_firestore():
        return
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


def _build_media_path(subdir, filename):
    return f"/media/{subdir}/{filename}"


def _split_media_path(media_path):
    normalized = (media_path or "").strip()
    if not normalized.startswith("/media/"):
        return None, None
    parts = normalized.split("/", 3)
    if len(parts) != 4:
        return None, None
    subdir = os.path.basename(parts[2])
    filename = os.path.basename(parts[3])
    if not subdir or not filename:
        return None, None
    return subdir, filename


def _build_object_name(subdir, filename):
    parts = []
    if GCS_MEDIA_PREFIX:
        parts.append(GCS_MEDIA_PREFIX)
    parts.extend([subdir, filename])
    return "/".join(parts)


def _build_local_path(subdir, filename):
    return os.path.join(MEDIA_DIR, subdir, filename)


def _firestore_asset_id(subdir, filename):
    return f"{subdir}__{filename}"


def _firestore_asset_ref(subdir, filename):
    return document("media_assets", _firestore_asset_id(subdir, filename))


def _default_mime_type(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _resolve_extension(mime_type, filename=""):
    ext = MIME_EXTENSIONS.get(mime_type or "", "")
    if not ext and filename:
        _, ext = os.path.splitext(filename)
    return ext or ".bin"


def _maybe_compress_content(content):
    threshold = max(FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB, 0) * 1024
    if len(content) < threshold:
        return content, False
    compressed = gzip.compress(content, compresslevel=6)
    if len(compressed) + 64 < len(content):
        return compressed, True
    return content, False


def _store_media_in_firestore(content, subdir, filename, mime_type):
    stored_content, compressed = _maybe_compress_content(content)
    max_bytes = max(FIRESTORE_MEDIA_MAX_MB, 1) * 1024 * 1024
    if len(stored_content) > max_bytes:
        raise RuntimeError(
            f"Arquivo excede limite seguro para Firestore ({FIRESTORE_MEDIA_MAX_MB}MB apos compressao)."
        )

    chunk_size = min(max(FIRESTORE_MEDIA_CHUNK_KB, 64) * 1024, 900 * 1024)
    chunks = [
        stored_content[index:index + chunk_size]
        for index in range(0, len(stored_content), chunk_size)
    ] or [b""]

    asset_ref = _firestore_asset_ref(subdir, filename)
    asset_ref.set({
        "subdir": subdir,
        "filename": filename,
        "mime_type": mime_type,
        "content_encoding": "gzip" if compressed else "",
        "original_size": len(content),
        "stored_size": len(stored_content),
        "chunk_count": len(chunks),
        "created_at": utcnow(),
        "checksum": hashlib.sha256(content).hexdigest(),
    })

    for idx, chunk in enumerate(chunks):
        asset_ref.collection("chunks").document(f"{idx:06d}").set({
            "seq": idx,
            "data": chunk,
        })

    return _build_media_path(subdir, filename)


def _write_media_bytes(content, subdir, filename, mime_type):
    ensure_media_dir()
    if _using_firestore():
        return _store_media_in_firestore(content, subdir, filename, mime_type)
    if _using_gcs():
        blob = _get_bucket().blob(_build_object_name(subdir, filename))
        blob.upload_from_string(content, content_type=mime_type)
        return _build_media_path(subdir, filename)

    filepath = _build_local_path(subdir, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return _build_media_path(subdir, filename)


def save_avatar_media(content, prefix, entity_id, mime_type):
    ext = _resolve_extension(mime_type)
    file_hash = hashlib.sha256(content).hexdigest()[:16]
    filename = f"{prefix}_{entity_id}_{file_hash}{ext}"
    return _write_media_bytes(content, "avatars", filename, mime_type)


def delete_media(media_path):
    if not media_path:
        return

    subdir, filename = _split_media_path(media_path)
    if not subdir or not filename:
        return

    deleted = False
    if _using_firestore():
        try:
            asset_ref = _firestore_asset_ref(subdir, filename)
            chunk_refs = list(asset_ref.collection("chunks").stream())
            for chunk_snapshot in chunk_refs:
                chunk_snapshot.reference.delete()
            asset_ref.delete()
            deleted = True
        except Exception as exc:
            logger.warning("Falha ao remover midia no Firestore (%s): %s", media_path, exc)

    if _using_gcs():
        try:
            blob = _get_bucket().blob(_build_object_name(subdir, filename))
            if blob.exists():
                blob.delete()
                deleted = True
        except Exception as exc:
            logger.warning("Falha ao remover midia no Cloud Storage (%s): %s", media_path, exc)

    filepath = _build_local_path(subdir, filename)
    if os.path.isfile(filepath):
        try:
            os.remove(filepath)
            deleted = True
        except OSError:
            pass

    if deleted:
        logger.info("Midia removida: %s", media_path)


def get_media_asset(media_path):
    subdir, filename = _split_media_path(media_path)
    if not subdir or not filename:
        return None

    if _using_firestore():
        try:
            asset = _firestore_asset_ref(subdir, filename).get()
            if asset.exists:
                data = asset.to_dict() or {}
                chunk_docs = sorted(
                    asset.reference.collection("chunks").stream(),
                    key=lambda snapshot: int((snapshot.to_dict() or {}).get("seq", 0)),
                )
                content = b"".join((snapshot.to_dict() or {}).get("data", b"") for snapshot in chunk_docs)
                if data.get("content_encoding") == "gzip":
                    content = gzip.decompress(content)
                return {
                    "content": content,
                    "mime_type": data.get("mime_type") or _default_mime_type(filename),
                    "filename": filename,
                    "source": "firestore",
                }
        except Exception as exc:
            logger.warning("Falha ao ler midia no Firestore (%s): %s", media_path, exc)

    if _using_gcs():
        try:
            blob = _get_bucket().blob(_build_object_name(subdir, filename))
            if blob.exists():
                return {
                    "content": blob.download_as_bytes(),
                    "mime_type": blob.content_type or _default_mime_type(filename),
                    "filename": filename,
                    "source": "gcs",
                }
        except Exception as exc:
            logger.warning("Falha ao ler midia no Cloud Storage (%s): %s", media_path, exc)

    filepath = _build_local_path(subdir, filename)
    if os.path.isfile(filepath):
        return {
            "file_path": filepath,
            "mime_type": _default_mime_type(filename),
            "filename": filename,
            "source": "local",
        }
    return None


def convert_audio_to_ogg_opus(input_bytes, input_mime="audio/webm"):
    """
    Converte audio gravado pelo navegador (webm/opus) para OGG/Opus
    que e o formato aceito pelo WhatsApp.
    Retorna os bytes do arquivo OGG ou None em caso de falha.
    """
    ext_in = ".webm"
    if "mp4" in input_mime or "m4a" in input_mime:
        ext_in = ".m4a"
    elif "mpeg" in input_mime or "mp3" in input_mime:
        ext_in = ".mp3"
    elif "ogg" in input_mime:
        ext_in = ".ogg"

    tmp_in = None
    tmp_out_path = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=ext_in, delete=False)
        tmp_in.write(input_bytes)
        tmp_in.close()

        tmp_out_path = tmp_in.name.replace(ext_in, "_converted.ogg")
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
            ext = _resolve_extension(mime, original_filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_id = hashlib.sha256(media_id.encode()).hexdigest()[:12]
            filename = f"{timestamp}_{safe_id}{ext}"
            subdir = get_subdir_for_type(msg_type)
            relative_path = _write_media_bytes(content, subdir, filename, mime or _default_mime_type(filename))

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
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    return "document"


async def save_upload_media(file_content, filename, mime_type):
    ensure_media_dir()

    msg_type = detect_media_type(mime_type)
    subdir = get_subdir_for_type(msg_type)
    ext = _resolve_extension(mime_type, filename)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_hash = hashlib.sha256(file_content[:1024]).hexdigest()[:12]
    safe_name = f"{timestamp}_{safe_hash}{ext}"
    relative_path = _write_media_bytes(file_content, subdir, safe_name, mime_type)

    logger.info("Upload salvo: %s (%s, %d bytes)", relative_path, mime_type, len(file_content))
    return {
        "path": relative_path,
        "mime_type": mime_type,
        "size": len(file_content),
        "msg_type": msg_type,
    }


async def save_upload_locally(file_content, filename, mime_type):
    return await save_upload_media(file_content, filename, mime_type)


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
            error = result.get("error", {}).get("message", "Erro desconhecido")
            logger.error("[WA MEDIA FAIL] %s: %s", wa_id, error)
            return {"error": error}
        except Exception as exc:
            logger.error("Erro ao enviar midia para %s: %s", wa_id, exc)
            return {"error": str(exc)}
