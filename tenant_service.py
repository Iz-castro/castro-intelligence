# -*- coding: utf-8 -*-
"""
Servico de Tenants — Fase 2 multi-tenant.

Cada tenant representa um cliente B2B (imobiliaria, clinica, locadora)
operando dentro do mesmo Castro CRM. A Castro Intelligence (provedor)
gerencia os tenants via super-admin; cada tenant tem seu proprio
conjunto isolado de operadores, canais WhatsApp, contatos e mensagens
em subcolecao Firestore tenants/{tenant_id}/...

Modelo do doc principal:
    <prefix>_tenants/{tenant_id}
        ├── name: str
        ├── slug: str (alias humano, ex: "hubloc", "clinica-vida")
        ├── cnpj: str
        ├── plan: str (starter | professional | enterprise | premium)
        ├── is_active: bool
        ├── settings: dict (logo_url, brand_color, default_locale)
        ├── billing: dict (status, next_due, ...)
        ├── created_at, updated_at: ISO datetime

A coleção root tenants/ e os docs sao acessados via Admin SDK
(backend), nunca diretamente do frontend. Operadores leem apenas o
proprio doc do tenant deles para exibir nome/branding.

Uso:
    from tenant_service import (
        get_tenant, list_tenants, create_tenant,
        update_tenant, deactivate_tenant,
    )
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from firestore_common import (
    collection_name,
    get_firestore_client,
    global_collection,
    global_document,
    normalize_record,
    tenant_doc_ref,
    utcnow,
)

logger = logging.getLogger("castro_crm.tenants")

PLAN_OPTIONS = ("starter", "professional", "enterprise", "premium")

_SLUG_RE = re.compile(r"^[a-z][a-z0-9\-]{2,63}$")


# ---------------------------------------------------------------------------
# Cache em memoria (thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_tenants_by_id: dict[str, dict] = {}
# None = cache nunca foi populado (forca refresh na primeira call). Usar
# valor numerico inicial 0 era bug: time.monotonic() retorna seconds desde
# o container boot — pequeno na primeira call — entao 0 - 0.5 < 60 e o
# refresh nao era disparado, deixando o cache vazio ate o TTL expirar.
_last_refresh: float | None = None
_CACHE_TTL_SECONDS = 60


def _needs_refresh() -> bool:
    if _last_refresh is None:
        return True
    return time.monotonic() - _last_refresh > _CACHE_TTL_SECONDS


def refresh_tenants() -> None:
    """Recarrega todos os tenants ativos do Firestore para o cache."""
    global _last_refresh

    rows: dict[str, dict] = {}
    for snap in global_collection("tenants").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        rows[str(data["id"])] = data

    with _lock:
        _tenants_by_id.clear()
        _tenants_by_id.update(rows)
        _last_refresh = time.monotonic()

    logger.info("Tenant cache refreshed: %d tenants", len(rows))


def _ensure_cache() -> None:
    if _needs_refresh():
        refresh_tenants()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def get_tenant(tenant_id: str) -> dict | None:
    """Retorna o doc do tenant pelo id (slug)."""
    if not tenant_id:
        return None
    _ensure_cache()
    with _lock:
        cached = _tenants_by_id.get(str(tenant_id))
    if cached:
        return normalize_record(cached)
    # Fallback: leitura direta caso o cache esteja stale.
    snap = tenant_doc_ref(tenant_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = snap.id
    return normalize_record(data)


def list_tenants(active_only: bool = True) -> list[dict]:
    """Retorna lista de tenants. Filtro padrao: somente ativos."""
    _ensure_cache()
    with _lock:
        rows = list(_tenants_by_id.values())
    if active_only:
        rows = [t for t in rows if t.get("is_active", True)]
    rows.sort(key=lambda t: str(t.get("name") or t.get("id") or ""))
    return [normalize_record(t) for t in rows]


def tenant_exists(tenant_id: str) -> bool:
    return get_tenant(tenant_id) is not None


# ---------------------------------------------------------------------------
# Escrita (super-admin Castro Intelligence)
# ---------------------------------------------------------------------------

def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug or ""):
        raise ValueError(
            "Slug invalido. Use minusculas, comeco com letra, 3-64 chars, "
            "apenas a-z, 0-9 e hifen."
        )


def create_tenant(
    tenant_id: str,
    name: str,
    cnpj: str = "",
    plan: str = "professional",
    settings: dict | None = None,
    billing: dict | None = None,
) -> dict:
    """Cria um novo tenant. Retorna o doc criado.

    O tenant_id e tambem o slug do path (tenants/{tenant_id}). Deve ser
    URL-safe e estavel (nao mudar depois).
    """
    _validate_slug(tenant_id)
    if not name or not name.strip():
        raise ValueError("name obrigatorio")
    if plan not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    if tenant_exists(tenant_id):
        raise ValueError(f"Tenant '{tenant_id}' ja existe")

    now = utcnow()
    doc = {
        "id": tenant_id,
        "name": name.strip(),
        "slug": tenant_id,
        "cnpj": (cnpj or "").strip(),
        "plan": plan,
        "is_active": True,
        "settings": settings or {},
        "billing": billing or {"status": "trial", "next_due": None},
        "created_at": now,
        "updated_at": now,
    }
    tenant_doc_ref(tenant_id).set(doc)
    refresh_tenants()
    logger.info("Tenant criado: id=%s name=%s plan=%s", tenant_id, name, plan)
    return normalize_record(doc)


def update_tenant(tenant_id: str, **fields: Any) -> bool:
    """Atualiza campos do tenant. Retorna True se atualizou."""
    allowed = {"name", "cnpj", "plan", "settings", "billing", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "plan" in updates and updates["plan"] not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    updates["updated_at"] = utcnow()
    tenant_doc_ref(tenant_id).set(updates, merge=True)
    refresh_tenants()
    return True


def deactivate_tenant(tenant_id: str) -> bool:
    """Marca tenant como inativo (soft delete). Dados permanecem."""
    return update_tenant(tenant_id, is_active=False)


def activate_tenant(tenant_id: str) -> bool:
    return update_tenant(tenant_id, is_active=True)


# ---------------------------------------------------------------------------
# phone_routing — indice global phone_number_id -> tenant_id + channel_id
# ---------------------------------------------------------------------------

def upsert_phone_routing(phone_number_id: str, tenant_id: str, channel_id) -> None:
    """Atualiza/cria o indice phone_routing/{phone_number_id} para
    permitir que o webhook resolva tenant a partir do payload da Meta
    em O(1).
    """
    if not phone_number_id:
        raise ValueError("phone_number_id obrigatorio")
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    global_document("phone_routing", phone_number_id).set(
        {
            "tenant_id": str(tenant_id),
            "channel_id": channel_id,
            "updated_at": utcnow(),
        },
        merge=True,
    )


def lookup_phone_routing(phone_number_id: str) -> dict | None:
    """Retorna {tenant_id, channel_id} para um phone_number_id, ou None."""
    if not phone_number_id:
        return None
    snap = global_document("phone_routing", phone_number_id).get()
    if not snap.exists:
        return None
    return snap.to_dict() or None


def remove_phone_routing(phone_number_id: str) -> None:
    """Remove a entrada de routing (chamado quando canal e desativado)."""
    if not phone_number_id:
        return
    global_document("phone_routing", phone_number_id).delete()
