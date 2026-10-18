# -*- coding: utf-8 -*-
"""Autorizacao atual do follow-up, sem efeitos de atendimento."""

import re

from fastapi import HTTPException

from channel_service import get_channel_by_id_from_db as get_channel
from database import get_wa_contact, get_wa_conversation_by_id
from firestore_common import get_tenant_context, tenant_context
from rbac import can_see_all_tenant, ensure_permission


def _owns(record, user):
    owner_uid = str(record.get("assigned_to_uid") or "")
    if owner_uid:
        return owner_uid == str(user.get("firebase_uid") or "")
    try:
        return record.get("assigned_to") is not None and int(record["assigned_to"]) == int(user["id"])
    except (KeyError, TypeError, ValueError):
        return False


def _unassigned(record):
    return not record.get("assigned_to_uid") and record.get("assigned_to") in (None, "")


def build_authorizer(tenant_id, require_contact_access):
    """Reusa predicado do CRM e restringe tambem a referencia da thread."""
    if not tenant_id:
        raise HTTPException(403, "Tenant obrigatorio")

    def authorize(contact_id, conversation_id, user):
        if str((user or {}).get("tenant_id") or "") != tenant_id:
            raise HTTPException(403, "Acesso negado ao tenant")
        if user.get("is_active", True) not in (True, 1) or not user.get("firebase_uid"):
            raise HTTPException(403, "Operador inativo ou sem identidade valida")
        ensure_permission(user, "gerenciar_followup")
        if conversation_id is not None and (not isinstance(conversation_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", conversation_id)):
            raise HTTPException(422, "Identificador de conversa invalido")
        active_tenant = get_tenant_context()
        if active_tenant and active_tenant != tenant_id:
            raise HTTPException(403, "Contexto de tenant divergente")
        with tenant_context(tenant_id):
            contact = get_wa_contact(int(contact_id))
            if not contact:
                raise HTTPException(404, "Contato nao encontrado")
            privileged = can_see_all_tenant(user)
            if contact.get("is_backup") and not privileged:
                raise HTTPException(403, "Historico restrito a gestao autorizada")
            require_contact_access(contact, user)
            conversation = None
            access_channel = None
            if conversation_id:
                conversation = get_wa_conversation_by_id(str(conversation_id))
                if not conversation or str(conversation.get("contact_id")) != str(contact_id):
                    raise HTTPException(404, "Conversa nao encontrada para este contato")
                if conversation.get("is_backup") and not privileged:
                    raise HTTPException(403, "Historico restrito a gestao autorizada")
                if not privileged and not _owns(conversation, user):
                    kind = None
                    channel_id = conversation.get("channel_id")
                    channel = (get_channel(channel_id) or {}) if channel_id is not None else {}
                    if channel.get("tenant_id") == tenant_id:
                        kind = channel.get("channel_type")
                    # Canal vivo prevalece sobre denormalizacao antiga; desconhecido nega.
                    visible_pool = _unassigned(conversation) and _unassigned(contact) and kind == "standard"
                    if not visible_pool:
                        raise HTTPException(403, "Conversa fora do acesso atual do operador")
                    access_channel = {key: channel.get(key) for key in ("id", "channel_type", "tenant_id")}
            return {"contact": contact, "conversation": conversation, "access_channel": access_channel}

    return authorize
