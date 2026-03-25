# -*- coding: utf-8 -*-

"""
Servico de integracao com Google Chat API.
Gerencia autenticacao via service account, envio de mensagens e download de midia.
"""

import logging
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GOOGLE_CHAT_SERVICE_ACCOUNT_FILE, FEATURE_GOOGLE_CHAT

logger = logging.getLogger("castro_crm.google_chat")

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
]


@lru_cache(maxsize=1)
def _get_credentials():
    """Cria credenciais da service account. No Cloud Run usa ADC se arquivo nao configurado."""
    if GOOGLE_CHAT_SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(
            GOOGLE_CHAT_SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )
    import google.auth
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


@lru_cache(maxsize=1)
def get_chat_service():
    """Retorna cliente autenticado da Google Chat API."""
    if not FEATURE_GOOGLE_CHAT:
        return None
    try:
        creds = _get_credentials()
        return build("chat", "v1", credentials=creds)
    except Exception as exc:
        logger.error("Falha ao inicializar Google Chat API: %s", exc, exc_info=True)
        return None


def list_spaces():
    """Lista spaces (salas) que o Chat App participa."""
    service = get_chat_service()
    if not service:
        return []
    try:
        result = service.spaces().list().execute()
        spaces = result.get("spaces", [])
        return [
            {
                "space_id": s["name"],
                "display_name": s.get("displayName", s["name"]),
                "type": s.get("spaceType", ""),
                "single_user_bot_dm": s.get("singleUserBotDm", False),
            }
            for s in spaces
        ]
    except Exception as exc:
        logger.error("Erro ao listar spaces: %s", exc, exc_info=True)
        return []


def get_space_members(space_id):
    """Lista membros de um space."""
    service = get_chat_service()
    if not service:
        return []
    try:
        result = service.spaces().members().list(parent=space_id).execute()
        members = result.get("memberships", [])
        return [
            {
                "name": m["name"],
                "member_type": m.get("member", {}).get("type", ""),
                "display_name": m.get("member", {}).get("displayName", ""),
                "email": m.get("member", {}).get("domainId", ""),
            }
            for m in members
        ]
    except Exception as exc:
        logger.error("Erro ao listar membros do space %s: %s", space_id, exc, exc_info=True)
        return []


def send_text_message(space_id, text):
    """Envia mensagem de texto para um space."""
    service = get_chat_service()
    if not service:
        return None
    try:
        result = service.spaces().messages().create(
            parent=space_id,
            body={"text": text},
        ).execute()
        logger.info("[GC OUT] Mensagem enviada para %s | id=%s", space_id, result.get("name", ""))
        return {
            "gchat_message_id": result.get("name", ""),
            "text": result.get("text", ""),
            "sender": result.get("sender", {}).get("displayName", ""),
            "create_time": result.get("createTime", ""),
        }
    except Exception as exc:
        logger.error("Erro ao enviar mensagem para %s: %s", space_id, exc, exc_info=True)
        return None


def download_attachment(resource_name):
    """Baixa anexo (audio, imagem, etc) do Google Chat usando resourceName.

    O Google Chat nao envia o binario direto no webhook — envia um resourceName
    que deve ser usado com media.download para obter o conteudo.
    """
    service = get_chat_service()
    if not service:
        return None
    try:
        result = service.media().download(resourceName=resource_name).execute()
        return result
    except Exception as exc:
        logger.error("Erro ao baixar anexo %s: %s", resource_name, exc, exc_info=True)
        return None


def get_message(message_name):
    """Busca uma mensagem especifica pelo name (spaces/X/messages/Y)."""
    service = get_chat_service()
    if not service:
        return None
    try:
        return service.spaces().messages().get(name=message_name).execute()
    except Exception as exc:
        logger.error("Erro ao buscar mensagem %s: %s", message_name, exc, exc_info=True)
        return None
