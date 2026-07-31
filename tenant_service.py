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
        ├── plan: str (professional | ai_custom | enterprise_ai — ver
        │     PLAN_OPTIONS; valores legados sao traduzidos NA LEITURA por
        │     _LEGACY_PLAN_MAP)
        ├── is_active: bool
        ├── allowed_email_domains: list[str] (SOFT — guarda-corpo + roteamento
        │     de login sem claim; NUNCA autoriza acesso, so o claim autoriza.
        │     Decisao 2026-07-03, ver ROADMAP "Identidade/dominio do tenant")
        ├── settings: dict (logo_url, brand_color, default_locale; settings.ai
        │     = config do motor de bot por tenant, gravada por
        │     scripts/set_tenant_ai.py)
        ├── billing: dict (status, next_due — RESERVADO: gravado na criacao e
        │     nao lido por nenhum runtime hoje)
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

# Planos comerciais (decisao PO 2026-07-13):
#   professional  — bot de triagem, setores, transferencias, templates, humano.
#   ai_custom     — professional + agente de IA dedicado (Dialogflow CX).
#   enterprise_ai — ai_custom + integracoes/SLA/relatorios (sob consulta).
PLAN_OPTIONS = ("professional", "ai_custom", "enterprise_ai")

# Docs gravados antes da renomeacao podem carregar valores legados; o mapa
# normaliza NA LEITURA (get_tenant/list_tenants) ate o backfill
# (scripts/migrate_plans.py) rodar em todos os ambientes.
_LEGACY_PLAN_MAP = {
    "starter": "professional",
    "enterprise": "enterprise_ai",
    "premium": "ai_custom",
}

# Modulos derivados do plano EM CODIGO (fonte unica, sem persistencia — evita
# drift entre doc e codigo). Override por tenant, se um dia precisar, entraria
# como settings.modules_extra — NAO IMPLEMENTADO: nenhum codigo le essa chave
# hoje; e so a convencao reservada pro futuro.
# NOTA: hoje NENHUM runtime gateia por plano/modulo — /api/session apenas
# EXPOE plan+modules; o que liga o agente de IA e settings.ai (bot_engine/
# status) + system_settings.bot_enabled do tenant. Gate real por plano e
# backlog (ver docs/PLANO_MODELOS_CRM_E_PLANOS.md).
PLAN_MODULES = {
    "professional": ("crm", "whatsapp", "bot_builtin"),
    "ai_custom": ("crm", "whatsapp", "bot_builtin", "ai_agent"),
    "enterprise_ai": ("crm", "whatsapp", "bot_builtin", "ai_agent"),
}


def normalize_plan(plan: str | None) -> str:
    """Traduz plano legado pro vocabulario atual; default professional."""
    value = str(plan or "").strip().lower()
    value = _LEGACY_PLAN_MAP.get(value, value)
    return value if value in PLAN_OPTIONS else "professional"


def modules_for_plan(plan: str | None) -> list[str]:
    """Modulos habilitados pelo plano (lista nova a cada call)."""
    return list(PLAN_MODULES.get(normalize_plan(plan), PLAN_MODULES["professional"]))

_SLUG_RE = re.compile(r"^[a-z][a-z0-9\-]{2,63}$")

# Provedores de email PUBLICOS: NUNCA viram allowed_email_domains de um tenant.
# Se virassem, resolve_tenant_by_email_domain casaria QUALQUER conta desse
# provedor e o AUTO_PROVISION criaria estranhos como operadores (vazamento de
# PII cross-tenant — achado critico da revisao 2026-07-06). O dominio do
# tenant tem que ser um dominio proprio do cliente (ex: clientenovo.com.br).
_PUBLIC_EMAIL_PROVIDERS = frozenset({
    "gmail.com", "googlemail.com",
    "outlook.com", "outlook.com.br", "hotmail.com", "hotmail.com.br",
    "live.com", "live.com.br", "msn.com",
    "yahoo.com", "yahoo.com.br", "ymail.com", "rocketmail.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "gmx.com", "gmx.net", "mail.com", "zoho.com",
    "proton.me", "protonmail.com", "pm.me", "tutanota.com",
    "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "globo.com",
    "globomail.com", "zipmail.com.br", "oi.com.br", "r7.com",
})


def is_public_email_provider(domain: str) -> bool:
    return str(domain or "").strip().lower().lstrip("@") in _PUBLIC_EMAIL_PROVIDERS


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
    """Recarrega todos os tenants ativos do Firestore para o cache.

    RESILIENTE a falha de leitura: esta funcao roda no caminho de LOGIN
    (auth resolve tenant por dominio) que corre em toda request autenticada.
    Uma excecao aqui viraria 500 em toda request durante um blip do Firestore.
    Em falha, mantem o cache atual (stale) e NAO atualiza _last_refresh (a
    proxima call re-tenta) — o login por CLAIM nem passa por aqui (short-
    circuita antes), entao o impacto fica so em login claimless durante a
    janela de degradacao.
    """
    global _last_refresh

    try:
        rows: dict[str, dict] = {}
        for snap in global_collection("tenants").stream():
            data = snap.to_dict() or {}
            if "id" not in data:
                data["id"] = snap.id
            rows[str(data["id"])] = data
    except Exception as exc:
        logger.warning("refresh_tenants: leitura falhou, mantendo cache stale: %s", exc)
        return

    with _lock:
        _tenants_by_id.clear()
        _tenants_by_id.update(rows)
        _last_refresh = time.monotonic()

    logger.info("Tenant cache refreshed: %d tenants", len(rows))


def _domains_owned_by_other_active_tenant(domains, exclude_tenant_id) -> dict:
    """Mapa {dominio: tenant_id} dos dominios de `domains` ja usados por
    OUTRO tenant ativo. Vazio = sem colisao. Um dominio proprio nao pode
    pertencer a 2 tenants (senao resolve_tenant_by_email_domain fica ambiguo
    -> nega, ou pior, rotearia errado)."""
    domains = set(normalize_email_domains(domains))
    if not domains:
        return {}
    _ensure_cache()
    collisions: dict = {}
    with _lock:
        for t in _tenants_by_id.values():
            tid = str(t.get("id"))
            if tid == str(exclude_tenant_id) or not t.get("is_active", True):
                continue
            for d in normalize_email_domains(t.get("allowed_email_domains")):
                if d in domains:
                    collisions[d] = tid
    return collisions


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
        return _with_normalized_plan(normalize_record(cached))
    # Fallback: leitura direta caso o cache esteja stale.
    snap = tenant_doc_ref(tenant_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = snap.id
    return _with_normalized_plan(normalize_record(data))


def list_tenants(active_only: bool = True) -> list[dict]:
    """Retorna lista de tenants. Filtro padrao: somente ativos."""
    _ensure_cache()
    with _lock:
        rows = list(_tenants_by_id.values())
    if active_only:
        rows = [t for t in rows if t.get("is_active", True)]
    rows.sort(key=lambda t: str(t.get("name") or t.get("id") or ""))
    return [_with_normalized_plan(normalize_record(t)) for t in rows]


def _with_normalized_plan(record: dict) -> dict:
    """Aplica o mapa de planos legados na leitura (pre-backfill)."""
    if "plan" in record:
        record["plan"] = normalize_plan(record.get("plan"))
    return record


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


def normalize_email_domains(domains) -> list[str]:
    """Lista de dominios canonicos (minusculo, sem @/espacos, sem dup, ordem
    estavel). Aceita lista ou string CSV. DESCARTA provedores publicos
    (gmail/outlook/...) — eles nunca podem rotear/auto-provisionar um tenant
    (defesa em profundidade: vale em qualquer caller, nao so no create)."""
    if isinstance(domains, str):
        domains = domains.split(",")
    out: list[str] = []
    for d in domains or []:
        d = str(d or "").strip().lower().lstrip("@")
        if not d or d in out:
            continue
        if is_public_email_provider(d):
            logger.warning(
                "allowed_email_domains: provedor publico '%s' IGNORADO (nao "
                "pode rotear/auto-provisionar tenant)", d,
            )
            continue
        out.append(d)
    return out


def create_tenant(
    tenant_id: str,
    name: str,
    cnpj: str = "",
    plan: str = "professional",
    settings: dict | None = None,
    billing: dict | None = None,
    allowed_email_domains=None,
) -> dict:
    """Cria um novo tenant. Retorna o doc criado.

    O tenant_id e tambem o slug do path (tenants/{tenant_id}). Deve ser
    URL-safe e estavel (nao mudar depois). allowed_email_domains e SOFT
    (guarda-corpo + roteamento de login; nunca autoriza — ver modulo auth).
    """
    _validate_slug(tenant_id)
    if not name or not name.strip():
        raise ValueError("name obrigatorio")
    if plan not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    if tenant_exists(tenant_id):
        raise ValueError(f"Tenant '{tenant_id}' ja existe")

    domains = normalize_email_domains(allowed_email_domains)
    collisions = _domains_owned_by_other_active_tenant(domains, tenant_id)
    if collisions:
        raise ValueError(f"Dominio(s) ja em uso por outro tenant: {collisions}")

    now = utcnow()
    doc = {
        "id": tenant_id,
        "name": name.strip(),
        "slug": tenant_id,
        "cnpj": (cnpj or "").strip(),
        "plan": plan,
        "is_active": True,
        "allowed_email_domains": domains,
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
    allowed = {"name", "cnpj", "plan", "settings", "billing", "is_active", "allowed_email_domains"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "plan" in updates and updates["plan"] not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    if "allowed_email_domains" in updates:
        domains = normalize_email_domains(updates["allowed_email_domains"])
        collisions = _domains_owned_by_other_active_tenant(domains, tenant_id)
        if collisions:
            raise ValueError(f"Dominio(s) ja em uso por outro tenant: {collisions}")
        updates["allowed_email_domains"] = domains
    elif updates.get("is_active") is True:
        # REATIVACAO: a checagem de colisao ignora tenants inativos, entao os
        # dominios deste tenant podem ter sido tomados por outro enquanto ele
        # estava desligado. Reativar sem revalidar deixaria DOIS tenants ativos
        # com o mesmo dominio -> resolve_tenant_by_email_domain vira ambiguo e
        # NEGA o login dos dois (achado da revisao 2026-07-30).
        current = normalize_email_domains((get_tenant(tenant_id) or {}).get("allowed_email_domains"))
        collisions = _domains_owned_by_other_active_tenant(current, tenant_id)
        if collisions:
            raise ValueError(
                f"Nao da pra reativar: dominio(s) ja em uso por outro tenant ativo: "
                f"{collisions}. Remova o dominio de la (ou daqui) antes de reativar."
            )
    updates["updated_at"] = utcnow()
    tenant_doc_ref(tenant_id).set(updates, merge=True)
    refresh_tenants()
    return True


# ---------------------------------------------------------------------------
# Resolucao de tenant no login (SOFT — usado por auth.py). NENHUMA destas
# AUTORIZA acesso: sao so roteamento/contexto de lookup. A autorizacao e o
# claim tenant_id (rules) + gate de login (auth._login_gate).
# ---------------------------------------------------------------------------

def resolve_tenant_by_email_domain(email: str) -> str | None:
    """tenant_id ativo cujo allowed_email_domains contem o dominio do email.

    Retorna None se nenhum bate OU se >1 bate (ambiguo): nao adivinha o
    tenant — forca provisionamento explicito. Por um usuario no tenant
    ERRADO e pior (LGPD) que um login que exige provisionamento manual.
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    domain = email.split("@", 1)[1]
    _ensure_cache()
    with _lock:
        matches = sorted({
            str(t.get("id"))
            for t in _tenants_by_id.values()
            if t.get("is_active", True) and domain in normalize_email_domains(t.get("allowed_email_domains"))
        })
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.error(
            "resolve_tenant_by_email_domain: dominio '%s' em MULTIPLOS tenants %s -> "
            "negado (ambiguo; corrija allowed_email_domains)", domain, matches,
        )
    return None


def single_active_tenant() -> str | None:
    """Se existe EXATAMENTE 1 tenant ativo, retorna seu id; senao None.

    Rede de transicao multi-tenant: enquanto so existe o hubloc, um login que
    nao resolve por claim nem por dominio cai nesse unico tenant (equivalente
    ao antigo _DEFAULT_TENANT, mas SEM literal). Ao criar o 2o tenant, isto
    passa a retornar None -> logins nao-resolviveis sao negados/roteados so
    por dominio. Desarma sozinho exatamente quando o risco cross-tenant surge.
    """
    _ensure_cache()
    with _lock:
        actives = [str(t.get("id")) for t in _tenants_by_id.values() if t.get("is_active", True)]
    return actives[0] if len(actives) == 1 else None


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
