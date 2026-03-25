# -*- coding: utf-8 -*-

from __future__ import annotations

"""
Transcricao de audio via Faster Whisper (CTranslate2).
Substitui o fluxo anterior baseado em Google Cloud Speech-to-Text.
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger("castro_crm.transcription")

_whisper_model = None

# Tamanho do modelo. Opcoes comuns: tiny, base, small, medium, large-v3.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

# Dispositivo: cpu, cuda ou auto.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# Tipo de computacao: int8, float16, int8_float16.
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_MIME_EXTENSION_MAP = {
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/opus": ".ogg",
    "application/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/amr": ".amr",
    "audio/amr-wb": ".amr",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
}


def init_speech_client():
    """Inicializa o modelo Faster Whisper uma vez. Retorna True se ok."""
    global _whisper_model
    if _whisper_model is not None:
        return True
    try:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        logger.info(
            "Faster Whisper carregado | modelo=%s | device=%s | compute=%s",
            WHISPER_MODEL_SIZE,
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
        return True
    except Exception as exc:
        logger.error("Falha ao carregar Faster Whisper: %s", exc, exc_info=True)
        _whisper_model = None
        return False


def get_speech_client():
    return _whisper_model


def _resolve_extension(media_mime: str | None) -> str:
    mime = (media_mime or "").lower().strip()
    ext = _MIME_EXTENSION_MAP.get(mime)
    if not ext:
        for key, value in _MIME_EXTENSION_MAP.items():
            if mime.startswith(key.split(";")[0].strip()):
                ext = value
                break
    return ext or ".ogg"


def _convert_to_wav(audio_bytes: bytes, input_ext: str) -> bytes | None:
    """
    Converte audio arbitrario para WAV 16kHz mono via FFmpeg para reduzir
    problemas de codec no processo de transcricao.
    """
    tmp_in = None
    tmp_out = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=input_ext, delete=False)
        tmp_in.write(audio_bytes)
        tmp_in.close()

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_out.close()

        cmd = [
            "ffmpeg",
            "-i",
            tmp_in.name,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-y",
            tmp_out.name,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("FFmpeg conversao falhou (code=%d): %s", result.returncode, stderr_text)
            return None

        with open(tmp_out.name, "rb") as fh:
            wav_data = fh.read()

        if len(wav_data) < 100:
            logger.error("WAV convertido muito pequeno (%d bytes)", len(wav_data))
            return None

        return wav_data
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout na conversao para WAV")
        return None
    except Exception as exc:
        logger.error("Erro na conversao para WAV: %s", exc)
        return None
    finally:
        for handle in (tmp_in, tmp_out):
            if handle is not None:
                try:
                    os.unlink(handle.name if hasattr(handle, "name") else handle)
                except OSError:
                    pass


def transcribe_audio_bytes(
    audio_content: bytes,
    *,
    media_mime: str | None = None,
    language_code: str = "pt-BR",
    timeout_s: float = 30.0,
) -> str:
    """
    Transcreve bytes de audio usando Faster Whisper.
    Mantem a assinatura compativel com a implementacao anterior.
    """
    model = get_speech_client()
    if model is None or not audio_content:
        return ""

    whisper_lang = language_code.split("-")[0].lower() if language_code else "pt"

    tmp_audio = None
    try:
        input_ext = _resolve_extension(media_mime)
        wav_data = _convert_to_wav(audio_content, input_ext)

        if wav_data is None:
            logger.warning("Conversao WAV falhou, tentando arquivo original")
            tmp_audio = tempfile.NamedTemporaryFile(suffix=input_ext, delete=False)
            tmp_audio.write(audio_content)
            tmp_audio.close()
            audio_path = tmp_audio.name
        else:
            tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_audio.write(wav_data)
            tmp_audio.close()
            audio_path = tmp_audio.name

        segments, info = model.transcribe(
            audio_path,
            language=whisper_lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 200,
            },
        )

        parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        transcript = " ".join(parts).strip()
        if transcript:
            logger.info(
                "Transcricao concluida | idioma=%s | prob=%.2f | caracteres=%d",
                info.language,
                info.language_probability,
                len(transcript),
            )
        return transcript
    except Exception as exc:
        logger.error("Falha na transcricao Faster Whisper: %s", exc, exc_info=True)
        return ""
    finally:
        if tmp_audio is not None:
            try:
                os.unlink(tmp_audio.name)
            except OSError:
                pass
