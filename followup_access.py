# -*- coding: utf-8 -*-
"""Autorizacao atual do follow-up, sem efeitos de atendimento.

Tambem usada pelo funil comercial (permission="ver_funil"): contato, thread e
historico de mensagens so-leitura com o mesmo predicado do CRM.
"""

import re

from fastapi import HTTPException

from channel_service import get_channel_by_id_from_db as get_channel
from database import get_wa_contact, get_wa_conversation, get_wa_conversation_by_id
from firestore_common import get_tenant_context, tenant_collection, tenant_context
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


def conversation_visible(contact, conversation, channel, user, tenant_id, privileged=None):
    """Predicado PURO de leitura de uma thread ja lida: (visivel, access_channel).

    Privilegiado ve tudo; dono da thread ve a propria; os demais so a pool de
    canal standard VIVO do mesmo tenant, com contato e thread sem dono; thread
    de backup so para privilegiado. `channel` = doc do canal (ou {}/None quando desconhecido: nega).
    access_channel volta preenchido so no caso pool (guard do commit)."""
    privileged = can_see_all_tenant(user) if privileged is None else bool(privileged)
    if not isinstance(conversation, dict) or not isinstance(contact, dict):
        return False, None
    if conversation.get("is_backup") and not privileged:
        return False, None
    if privileged or _owns(conversation, user):
        return True, None
    channel = channel if isinstance(channel, dict) else {}
    kind = channel.get("channel_type") if channel.get("tenant_id") == tenant_id else None
    # Canal vivo prevalece sobre denormalizacao antiga; desconhecido nega.
    if _unassigned(conversation) and _unassigned(contact) and kind == "standard":
        return True, {key: channel.get(key) for key in ("id", "channel_type", "tenant_id")}
    return False, None


def build_authorizer(tenant_id, require_contact_access, permission="gerenciar_followup"):
    """Reusa predicado do CRM e restringe tambem a referencia da thread.

    `permission` = toggle exigido do usuario avaliado (o follow-up checa tambem
    o destinatario de uma redistribuicao; o funil passa "ver_funil")."""
    if not tenant_id:
        raise HTTPException(403, "Tenant obrigatorio")
    if not permission or not isinstance(permission, str):
        raise ValueError("permission obrigatoria no autorizador")

    def authorize(contact_id, conversation_id, user):
        if str((user or {}).get("tenant_id") or "") != tenant_id:
            raise HTTPException(403, "Acesso negado ao tenant")
        if user.get("is_active", True) not in (True, 1) or not user.get("firebase_uid"):
            raise HTTPException(403, "Operador inativo ou sem identidade valida")
        ensure_permission(user, permission)
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
                channel = None
                if not privileged and not _owns(conversation, user):
                    channel_id = conversation.get("channel_id")
                    channel = (get_channel(channel_id) or {}) if channel_id is not None else {}
                visible, access_channel = conversation_visible(
                    contact, conversation, channel, user, tenant_id, privileged=privileged)
                if not visible:
                    raise HTTPException(403, "Conversa fora do acesso atual do operador")
            return {"contact": contact, "conversation": conversation, "access_channel": access_channel}

    return authorize


def list_authorized_conversations(tenant_id, authorize, contact_id, user, limit=30):
    """Threads do contato que o usuario pode ler AGORA (cada uma pelo
    autorizador). Leitura limitada por contato; nao materializa nem assume."""
    query = (tenant_collection(tenant_id, "wa_conversations")
             .where("contact_id", "==", contact_id).order_by("__name__").limit(limit))
    rows = []
    for snap in query.stream():
        try:
            row = authorize(contact_id, snap.id, user)["conversation"]
        except HTTPException as exc:
            if exc.status_code in (403, 404):
                continue
            raise
        rows.append(row)
    return rows


def load_authorized_messages(authorize, contact_id, conversation_id, user, limit):
    """Historico so-leitura de UMA thread autorizada. Nao marca lida, nao abre
    atendimento. admin_only/backup/visibilidade restrita saem no servidor
    para quem nao tem a visao do tenant."""
    if not conversation_id:
        raise HTTPException(422, "Informe a conversa")
    authorize(contact_id, conversation_id, user)
    with tenant_context(str(user.get("tenant_id") or "")):
        rows = get_wa_conversation(contact_id, limit=limit, conversation_id=conversation_id)
    if not can_see_all_tenant(user):
        rows = [row for row in rows if not row.get("admin_only") and not row.get("is_backup")
                and row.get("visibility") != "admin_only"]
    return rows
