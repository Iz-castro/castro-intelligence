# -*- coding: utf-8 -*-

"""
Transcricao de audio inbound via Google Cloud Speech-to-Text.
Baseado na arquitetura do servico webh.
"""

import logging

logger = logging.getLogger("castro_crm.transcription")

_AUDIO_ENCODING_MAP = {
    "audio/ogg": "OGG_OPUS",
    "audio/ogg; codecs=opus": "OGG_OPUS",
    "audio/opus": "OGG_OPUS",
    "application/ogg": "OGG_OPUS",
    "audio/mpeg": "MP3",
    "audio/mp3": "MP3",
    "audio/wav": "LINEAR16",
    "audio/x-wav": "LINEAR16",
    "audio/flac": "FLAC",
    "audio/amr": "AMR",
    "audio/amr-wb": "AMR_WB",
    "audio/aac": "MP3",
    "audio/mp4": "MP3",
}

_SAMPLE_RATE_MAP = {
    "OGG_OPUS": 48000,
    "AMR": 8000,
    "AMR_WB": 16000,
    "LINEAR16": 16000,
    "FLAC": 16000,
    "MP3": 16000,
}

# Candidatos de sample_rate para OGG_OPUS (fallback progressivo)
_OPUS_SAMPLE_RATE_CANDIDATES = [16000, 24000, 12000, 48000, 8000]

_speech_client = None


def init_speech_client():
    """Inicializa o SpeechClient uma vez. Retorna True se ok."""
    global _speech_client
    if _speech_client is not None:
        return True
    try:
        from google.cloud import speech
        _speech_client = speech.SpeechClient()
        logger.info("SpeechClient inicializado com sucesso")
        return True
    except Exception as exc:
        logger.error("Falha ao inicializar SpeechClient: %s", exc)
        _speech_client = None
        return False


def get_speech_client():
    return _speech_client


def _resolve_encoding(media_mime: str | None):
    mime = (media_mime or "").lower().strip()
    encoding_name = _AUDIO_ENCODING_MAP.get(mime)
    if not encoding_name:
        # tenta prefixo
        for key, enc in _AUDIO_ENCODING_MAP.items():
            if mime.startswith(key.split(";")[0].strip()):
                encoding_name = enc
                break
    if not encoding_name:
        encoding_name = "OGG_OPUS"
    sample_rate = _SAMPLE_RATE_MAP.get(encoding_name, 16000)
    return encoding_name, sample_rate


def _extract_transcript(response) -> str:
    parts = []
    for result in response.results:
        if result.alternatives:
            parts.append(result.alternatives[0].transcript.strip())
    return " ".join(parts).strip()


def transcribe_audio_bytes(
    audio_content: bytes,
    *,
    media_mime: str | None = None,
    language_code: str = "pt-BR",
    timeout_s: float = 30.0,
) -> str:
    """
    Transcreve bytes de audio usando Google Cloud Speech-to-Text.
    Retorna a transcricao como string, ou "" se falhar.
    """
    client = get_speech_client()
    if not client or not audio_content:
        return ""

    try:
        from google.cloud import speech
        from google.api_core import exceptions as gexc
    except ImportError:
        logger.error("google-cloud-speech nao instalado")
        return ""

    encoding_name, sample_rate = _resolve_encoding(media_mime)

    try:
        encoding_enum = speech.RecognitionConfig.AudioEncoding[encoding_name]
    except KeyError:
        encoding_enum = speech.RecognitionConfig.AudioEncoding.OGG_OPUS

    base_config = {
        "encoding": encoding_enum,
        "language_code": language_code,
        "enable_automatic_punctuation": True,
        "model": "default",
        "audio_channel_count": 1,
    }

    audio_obj = speech.RecognitionAudio(content=audio_content)

    # Para OGG_OPUS tenta multiplos sample rates
    if encoding_name == "OGG_OPUS":
        candidates = [{"sample_rate_hertz": r} for r in _OPUS_SAMPLE_RATE_CANDIDATES]
    else:
        candidates = [{"sample_rate_hertz": sample_rate}, {}]

    for extra in candidates:
        cfg = {**base_config, **extra}
        try:
            response = client.recognize(
                config=speech.RecognitionConfig(**cfg),
                audio=audio_obj,
                timeout=timeout_s,
            )
        except gexc.InvalidArgument:
            logger.warning("STT rejeitou config %s | mime=%s", extra, media_mime)
            continue
        except Exception as exc:
            logger.error("Falha na chamada STT: %s", exc, exc_info=True)
            return ""

        text = _extract_transcript(response)
        if text:
            if "sample_rate_hertz" in cfg:
                logger.info("STT ok | sample_rate=%s | mime=%s", cfg["sample_rate_hertz"], media_mime)
            return text

    return ""
