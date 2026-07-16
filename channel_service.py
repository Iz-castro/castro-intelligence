# -*- coding: utf-8 -*-
"""
Servico de canais WhatsApp.

Substitui as referencias hardcoded a WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID
por um registry que suporta multiplos canais (standard + coexistence).

Uso:
    from channel_service import (
        get_channel, get_channel_by_phone_id, get_default_channel,
        get_channels_for_user, get_send_credentials, refresh_channels,
    )
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from firestore_common import (
    _flat_collection as collection,
    _flat_document as document,
    get_tenant_context,
    next_sequence,
    utcnow,
    normalize_record,
)

# NOTA: channel_service usa explicitamente _flat_collection/_flat_document
# para que canais permanecam em colecao flat (compartilhada entre tenants)
# enquanto a migracao de canais para tenants/{id}/channels nao for feita.
# Isso evita que o webhook, que opera dentro de tenant_context, leia
# canais da subcolecao errada (vazia) e nao consiga rotear mensagens.

logger = logging.getLogger("castro_crm.channels")

CHANNEL_TYPE_STANDARD = "standard"
CHANNEL_TYPE_COEXISTENCE = "coexistence"

# ---------------------------------------------------------------------------
# In-memory cache (thread-safe via lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_channels_by_id: dict[int, dict] = {}
_channels_by_phone_id: dict[str, dict] = {}
# Default por tenant (ADR 0007 Fase 1): tenant_id -> channel_id (1o standard ativo).
# Antes era um int global -> envio sem channel_id explicito podia sair pela WABA
# de outro tenant.
_default_channel_id: dict[str, int] = {}
_last_refresh: float = 0
_CACHE_TTL_SECONDS = 60


def _needs_refresh() -> bool:
    return time.monotonic() - _last_refresh > _CACHE_TTL_SECONDS


def refresh_channels() -> None:
    """Recarrega todos os canais ativos do Firestore para o cache."""
    global _last_refresh

    rows = []
    for snap in collection("channels").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            try:
                data["id"] = int(snap.id)
            except ValueError:
                data["id"] = snap.id
        if data.get("is_active"):
            rows.append(data)

    by_id: dict[int, dict] = {}
    by_phone: dict[str, dict] = {}
    default_by_tenant: dict[str, int] = {}

    for row in rows:
        cid = row["id"]
        by_id[cid] = row
        phone_id = str(row.get("phone_number_id", "")).strip()
        if phone_id:
            by_phone[phone_id] = row
        # 1o canal standard ativo de CADA tenant vira o default daquele tenant.
        if row.get("channel_type") == CHANNEL_TYPE_STANDARD:
            tid = str(row.get("tenant_id") or "hubloc")
            if tid not in default_by_tenant:
                default_by_tenant[tid] = cid

    with _lock:
        _channels_by_id.clear()
        _channels_by_id.update(by_id)
        _channels_by_phone_id.clear()
        _channels_by_phone_id.update(by_phone)
        _default_channel_id.clear()
        _default_channel_id.update(default_by_tenant)
        _last_refresh = time.monotonic()

    logger.info("Channel cache refreshed: %d active channels", len(by_id))


def _ensure_cache() -> None:
    if _needs_refresh():
        refresh_channels()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def get_channel(channel_id: int) -> dict | None:
    """Retorna um canal pelo ID."""
    _ensure_cache()
    with _lock:
        return _channels_by_id.get(channel_id)


def get_channel_by_phone_id(phone_number_id: str) -> dict | None:
    """Retorna um canal pelo phone_number_id da Meta."""
    if not phone_number_id:
        return None
    _ensure_cache()
    with _lock:
        return _channels_by_phone_id.get(str(phone_number_id).strip())


def get_default_channel() -> dict | None:
    """Retorna o canal standard (bot) padrao DO TENANT ATUAL (ADR 0007)."""
    _ensure_cache()
    tid = get_tenant_context() or "hubloc"
    with _lock:
        cid = _default_channel_id.get(tid)
        if cid is not None:
            return _channels_by_id.get(cid)
    return None


def get_all_active_channels() -> list[dict]:
    """Retorna os canais ativos DO TENANT ATUAL (ADR 0007 Fase 1: isolamento).

    Filtro logico por tenant_id do contexto (o middleware seta por request via
    custom claim; fallback 'hubloc' durante a transicao single-tenant).
    """
    _ensure_cache()
    tid = get_tenant_context() or "hubloc"
    with _lock:
        return [
            normalize_record(ch)
            for ch in _channels_by_id.values()
            if str(ch.get("tenant_id") or "hubloc") == tid
        ]


def get_channels_for_user(user_id: int) -> list[dict]:
    """Retorna canais que o usuario pode acessar.

    - Canal standard (bot): acessivel por todos
    - Canal coexistence: acessivel apenas pelo owner + admin/supervisor
    """
    _ensure_cache()
    tid = get_tenant_context() or "hubloc"
    with _lock:
        result = []
        for ch in _channels_by_id.values():
            if str(ch.get("tenant_id") or "hubloc") != tid:
                continue
            if ch.get("channel_type") == CHANNEL_TYPE_STANDARD:
                result.append(ch)
            elif ch.get("owner_user_id") == user_id:
                result.append(ch)
        return [normalize_record(ch) for ch in result]


def get_send_credentials(channel_id: int | None) -> tuple[str, str, str]:
    """Retorna (access_token, phone_number_id, graph_api_base) para envio.

    Se channel_id for None, usa o canal default.
    Quando channel_id e explicito mas nao encontrado no cache, faz UM
    refresh sincrono e tenta de novo — protege contra cache stale entre
    instancias do Cloud Run apos create_channel recente. Se ainda assim
    nao for encontrado, falha em vez de cair em outro canal (caso
    contrario o envio iria pelo canal default com creds erradas).
    Raises ValueError se o canal nao for encontrado.
    """
    from config import GRAPH_API_BASE, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN

    channel = None
    if channel_id is not None:
        channel = get_channel(channel_id)
        if channel is None:
            # Cache stale entre instancias — recarrega do Firestore e
            # tenta de novo antes de aceitar o miss.
            refresh_channels()
            channel = get_channel(channel_id)
        if channel is None:
            raise ValueError(
                f"Canal {channel_id} solicitado nao existe (mesmo apos refresh). "
                "Recusa-se a cair em canal default para evitar enviar pelo canal errado."
            )
    if channel is None:
        channel = get_default_channel()
    if channel is None:
        raise ValueError("Nenhum canal WhatsApp configurado.")

    # Para o canal standard DO MESMO NUMERO do env, o segredo do Cloud Run
    # e a fonte de verdade (evita registry Firestore preso em token antigo
    # apos rotacao do secret). O override NUNCA se aplica a outro canal
    # standard: com multiplos tenants, cair no env enviaria pelo numero de
    # outro cliente.
    if channel.get("channel_type") == CHANNEL_TYPE_STANDARD:
        env_token = str(WHATSAPP_TOKEN or "").strip()
        env_phone_id = str(WHATSAPP_PHONE_NUMBER_ID or "").strip()
        channel_phone_id = str(channel.get("phone_number_id") or "").strip()
        if env_token and env_phone_id and channel_phone_id == env_phone_id:
            return env_token, env_phone_id, GRAPH_API_BASE

    token = str(channel.get("access_token", "")).strip()
    phone_id = str(channel.get("phone_number_id", "")).strip()

    if not token or not phone_id:
        raise ValueError(f"Canal {channel.get('id')} sem token ou phone_number_id.")

    return token, phone_id, GRAPH_API_BASE


# ---------------------------------------------------------------------------
# Escrita (CRUD)
# ---------------------------------------------------------------------------

def create_channel(
    channel_type: str,
    label: str,
    waba_id: str,
    phone_number_id: str,
    display_phone_number: str,
    access_token: str,
    owner_user_id: int | None = None,
    owner_firebase_uid: str = "",
    default_department_id: int | None = None,
    is_bot_enabled: bool = False,
    token_expires_at: str | None = None,
    platform_type: str = "",
    is_official_business_account: bool | None = None,
    code_verification_status: str = "",
    messaging_limit_tier: str = "",
    verified_name: str = "",
    quality_rating: str = "",
    webhook_subscribed: bool = False,
    tenant_id: str | None = None,
) -> int:
    """Cria um novo canal e retorna o ID.

    Tambem popula o indice global `phone_routing/{phone_number_id}` quando
    `phone_number_id` esta disponivel — permite ao webhook resolver
    tenant em O(1) sem varrer canais por tenant.
    """
    # ID do canal vem do contador GLOBAL (tenant_id=None), NAO do por-tenant:
    # a colecao `channels` e FLAT/global (_flat_document), entao um contador
    # por-tenant faria tenants diferentes gerarem os mesmos ids (1,2,...) e um
    # SOBRESCREVER os canais do outro (incidente 2026-07-16: varizemed
    # sobrescreveu os canais 1 e 2 do hubloc). Global garante id unico.
    channel_id = next_sequence("channels", tenant_id=None)
    now = utcnow()
    phone_id_norm = str(phone_number_id).strip()
    # Resolve tenant: prioridade explicito > contexto atual > 'hubloc'.
    if not tenant_id:
        from firestore_common import get_tenant_context
        tenant_id = get_tenant_context() or "hubloc"
    document("channels", channel_id).set({
        "id": channel_id,
        "channel_type": channel_type,
        "label": label,
        "waba_id": str(waba_id).strip(),
        "phone_number_id": phone_id_norm,
        "display_phone_number": display_phone_number,
        "access_token": access_token,
        "token_expires_at": token_expires_at,
        "owner_user_id": owner_user_id,
        "owner_firebase_uid": owner_firebase_uid,
        "default_department_id": default_department_id,
        "is_bot_enabled": is_bot_enabled,
        "is_active": True,
        "webhook_subscribed": webhook_subscribed,
        "platform_type": platform_type,
        "is_official_business_account": is_official_business_account,
        "code_verification_status": code_verification_status,
        "messaging_limit_tier": messaging_limit_tier,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
        "tenant_id": str(tenant_id),
        "created_at": now,
        "updated_at": now,
    })
    if phone_id_norm:
        try:
            from tenant_service import upsert_phone_routing
            upsert_phone_routing(phone_id_norm, str(tenant_id), channel_id)
        except Exception as exc:
            logger.warning(
                "Falha ao popular phone_routing | channel=%s phone=%s tenant=%s err=%s",
                channel_id, phone_id_norm, tenant_id, exc,
            )
    refresh_channels()
    logger.info("Channel created: id=%d type=%s label=%s phone=%s tenant=%s",
                channel_id, channel_type, label, phone_id_norm, tenant_id)
    return channel_id


def update_channel(channel_id: int, **fields: Any) -> bool:
    """Atualiza campos de um canal existente."""
    allowed = {
        "label", "access_token", "token_expires_at", "owner_user_id", "owner_firebase_uid",
        "default_department_id", "is_bot_enabled", "is_active",
        "webhook_subscribed", "display_phone_number", "phone_number_id", "waba_id",
        "platform_type", "is_official_business_account", "code_verification_status",
        "messaging_limit_tier", "verified_name", "quality_rating",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = utcnow()
    document("channels", channel_id).set(updates, merge=True)
    refresh_channels()
    return True


def refresh_coexistence_token(channel_id: int) -> bool:
    """Tenta estender o token de um canal coexistence via fb_exchange_token.

    Retorna True se renovou com sucesso, False caso contrario.
    Loga warning quando falha (sinaliza necessidade de re-onboarding).
    """
    from datetime import datetime, timedelta, timezone

    import httpx

    from config import GRAPH_API_BASE, META_APP_ID, META_APP_SECRET

    if not META_APP_ID or not META_APP_SECRET:
        logger.warning("refresh_coexistence_token: META_APP_ID/SECRET ausente")
        return False

    channel = get_channel(channel_id)
    if not channel:
        logger.warning("refresh_coexistence_token: canal %s nao encontrado", channel_id)
        return False
    if channel.get("channel_type") != CHANNEL_TYPE_COEXISTENCE:
        return False

    current_token = str(channel.get("access_token", "")).strip()
    if not current_token:
        logger.warning("refresh_coexistence_token: canal %s sem token armazenado", channel_id)
        return False

    url = f"{GRAPH_API_BASE}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "fb_exchange_token": current_token,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
        if resp.status_code >= 400:
            # NAO logar resp.text cru — pode conter token em sucesso parcial
            # ou outros campos sensiveis. Extrai apenas a mensagem de erro
            # estruturada do JSON da Graph API.
            err_msg = ""
            try:
                err_msg = ((resp.json() or {}).get("error") or {}).get("message", "")
            except Exception:
                err_msg = "<unparseable>"
            logger.warning(
                "refresh_coexistence_token: canal %s falhou status=%s erro=%s",
                channel_id, resp.status_code, err_msg,
            )
            return False
        data = resp.json()
    except Exception as exc:
        logger.warning("refresh_coexistence_token: canal %s exception=%s", channel_id, exc)
        return False

    new_token = data.get("access_token")
    if not new_token:
        # Loga apenas as chaves do response (sem valores) — o que importa
        # pra debug e qual campo veio (ex.: 'error' vs 'access_token').
        logger.warning(
            "refresh_coexistence_token: canal %s resposta sem access_token (campos=%s)",
            channel_id, sorted((data or {}).keys()),
        )
        return False

    expires_in = data.get("expires_in")
    expires_at_iso: str | None = None
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        expires_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    update_channel(channel_id, access_token=new_token, token_expires_at=expires_at_iso)
    logger.info("refresh_coexistence_token: canal %s renovado (expira em %s)", channel_id, expires_at_iso)
    return True


def deactivate_channel(channel_id: int) -> bool:
    """Desativa um canal e remove o indice phone_routing correspondente."""
    channel = get_channel(channel_id)
    phone_id = str((channel or {}).get("phone_number_id", "")).strip()
    ok = update_channel(channel_id, is_active=False)
    if phone_id:
        try:
            from tenant_service import remove_phone_routing
            remove_phone_routing(phone_id)
        except Exception as exc:
            logger.warning(
                "Falha ao remover phone_routing | channel=%s phone=%s err=%s",
                channel_id, phone_id, exc,
            )
    return ok


def get_channel_by_id_from_db(channel_id: int) -> dict | None:
    """Leitura direta do Firestore (sem cache)."""
    snap = document("channels", channel_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = channel_id
    return normalize_record(data)


def get_channel_by_phone_id_from_db(phone_number_id: str) -> dict | None:
    """Leitura direta do Firestore por phone_number_id, INCLUINDO inativos.

    Diferente de get_channel_by_phone_id (que usa o cache so-ativos —
    refresh_channels filtra is_active=True), este le o Firestore direto.
    E o que o rebind do Embedded Signup precisa: detectar um canal que foi
    desativado num onboarding anterior do MESMO numero e reativa-lo, em vez
    de criar uma duplicata.

    Quando ha mais de um canal com o mesmo phone_number_id (estado legado de
    prod antes do rebind, ex.: canais 1/4/5 do mesmo numero), escolhe o
    melhor candidato: prioriza is_active=True, depois updated_at mais
    recente. Loga warning na ambiguidade.
    """
    pid = str(phone_number_id or "").strip()
    if not pid:
        return None
    rows: list[dict] = []
    for snap in collection("channels").where("phone_number_id", "==", pid).stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            try:
                data["id"] = int(snap.id)
            except ValueError:
                data["id"] = snap.id
        rows.append(data)
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "get_channel_by_phone_id_from_db: %d canais com phone_id=%s (ids=%s) "
            "— escolhendo ativo/mais recente para rebind",
            len(rows), pid, sorted(str(r.get("id")) for r in rows),
        )
    rows.sort(
        key=lambda r: (bool(r.get("is_active")), str(r.get("updated_at") or "")),
        reverse=True,
    )
    return normalize_record(rows[0])


def rebind_channel(
    channel_id: int,
    *,
    waba_id: str,
    phone_number_id: str,
    display_phone_number: str,
    access_token: str,
    token_expires_at: str | None = None,
    owner_user_id: int | None = None,
    owner_firebase_uid: str | None = None,
    webhook_subscribed: bool | None = None,
    platform_type: str = "",
    is_official_business_account: bool | None = None,
    code_verification_status: str = "",
    messaging_limit_tier: str = "",
    verified_name: str = "",
    quality_rating: str = "",
    tenant_id: str | None = None,
) -> int:
    """Reaproveita um canal existente num re-onboarding do mesmo numero.

    Em vez de create_channel (que geraria channel_id novo -> threads
    duplicadas + canal antigo orfao), atualiza o canal existente: token/waba/
    metadata novos, REATIVA (is_active=True) e reaponta o phone_routing.
    Preserva config do operador (is_bot_enabled, label, default_department_id)
    — so mexe em identidade/credenciais/status.

    Mantem o channel_id, entao as threads {channel_id}__{wa_id} e as
    wa_conversations/wa_messages sobrevivem sem migracao. Retorna o
    channel_id reaproveitado.
    """
    pid = str(phone_number_id or "").strip()

    fields: dict[str, Any] = {
        "waba_id": str(waba_id).strip(),
        "phone_number_id": pid,
        "display_phone_number": display_phone_number,
        "access_token": access_token,
        "token_expires_at": token_expires_at,
        "is_active": True,
        "platform_type": platform_type,
        "is_official_business_account": is_official_business_account,
        "code_verification_status": code_verification_status,
        "messaging_limit_tier": messaging_limit_tier,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
    }
    # owner/webhook so sobrescrevem quando o caller fornece (None = preserva).
    if owner_user_id is not None:
        fields["owner_user_id"] = owner_user_id
    if owner_firebase_uid is not None:
        fields["owner_firebase_uid"] = owner_firebase_uid
    if webhook_subscribed is not None:
        fields["webhook_subscribed"] = webhook_subscribed

    update_channel(channel_id, **fields)  # ja faz refresh_channels()

    # Reaponta phone_routing -> este canal. deactivate_channel anterior pode
    # ter REMOVIDO a entrada; um create cego antigo pode te-la apontado p/
    # outro channel_id. upsert garante O(1) routing correto no webhook.
    if pid:
        try:
            from firestore_common import get_tenant_context
            from tenant_service import upsert_phone_routing
            tid = tenant_id or get_tenant_context() or "hubloc"
            upsert_phone_routing(pid, str(tid), channel_id)
        except Exception as exc:
            logger.warning(
                "rebind_channel: falha ao reapontar phone_routing | channel=%s phone=%s err=%s",
                channel_id, pid, exc,
            )

    # Unicidade no cache (so-ativos): desativa irmaos com o mesmo
    # phone_number_id (estado legado pre-rebind). Usa update_channel e NAO
    # deactivate_channel de proposito — deactivate removeria o phone_routing
    # que acabamos de apontar (mesma chave phone_id).
    if pid:
        for snap in collection("channels").where("phone_number_id", "==", pid).stream():
            other = snap.to_dict() or {}
            other_id = other.get("id")
            if other_id is None:
                try:
                    other_id = int(snap.id)
                except ValueError:
                    continue
            if other_id != channel_id and other.get("is_active"):
                update_channel(other_id, is_active=False)
                logger.info(
                    "rebind_channel: canal irmao %s (phone=%s) desativado p/ unicidade",
                    other_id, pid,
                )

    refresh_channels()
    logger.info(
        "Channel rebound: id=%s phone=%s waba=%s (reativado + credenciais novas)",
        channel_id, pid, str(waba_id).strip(),
    )
    return channel_id


# ---------------------------------------------------------------------------
# Bootstrap: cria canal default a partir das env vars legadas
# ---------------------------------------------------------------------------

def bootstrap_default_channel() -> int | None:
    """Cria o canal standard default se nao existir, usando env vars.

    Chamado no startup do app. Retorna o channel_id ou None se nao ha
    credenciais configuradas.
    """
    from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID

    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.info("Bootstrap channel: sem WHATSAPP_TOKEN/PHONE_NUMBER_ID, pulando")
        return None

    # Verifica se ja existe um canal standard
    refresh_channels()
    existing = get_default_channel()
    if existing:
        updates: dict[str, Any] = {}
        if str(existing.get("access_token", "")).strip() != str(WHATSAPP_TOKEN).strip():
            updates["access_token"] = WHATSAPP_TOKEN
        if str(existing.get("phone_number_id", "")).strip() != str(WHATSAPP_PHONE_NUMBER_ID).strip():
            updates["phone_number_id"] = WHATSAPP_PHONE_NUMBER_ID
        if str(existing.get("waba_id", "")).strip() != str(WHATSAPP_WABA_ID).strip():
            updates["waba_id"] = WHATSAPP_WABA_ID
        if updates:
            update_channel(existing["id"], **updates)
            logger.info(
                "Bootstrap channel: canal default sincronizado com env (id=%s fields=%s)",
                existing["id"],
                ",".join(sorted(updates.keys())),
            )
        else:
            logger.info("Bootstrap channel: canal default ja existe (id=%s)", existing["id"])
        # Garante que phone_routing aponta para o canal default ate quando
        # ele foi criado antes da Fase 2C (sem indice).
        eff_phone_id = str(updates.get("phone_number_id") or existing.get("phone_number_id") or "").strip()
        if eff_phone_id:
            try:
                from firestore_common import get_tenant_context
                from tenant_service import upsert_phone_routing
                tenant_id = existing.get("tenant_id") or get_tenant_context() or "hubloc"
                upsert_phone_routing(eff_phone_id, str(tenant_id), existing["id"])
            except Exception as exc:
                logger.warning("Bootstrap channel: falha ao backfill phone_routing: %s", exc)
        return existing["id"]

    channel_id = create_channel(
        channel_type=CHANNEL_TYPE_STANDARD,
        label="Canal Principal",
        waba_id=WHATSAPP_WABA_ID,
        phone_number_id=WHATSAPP_PHONE_NUMBER_ID,
        display_phone_number="",
        access_token=WHATSAPP_TOKEN,
        owner_user_id=None,
        is_bot_enabled=True,
    )
    logger.info("Bootstrap channel: canal default criado (id=%d)", channel_id)
    return channel_id
