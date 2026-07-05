# -*- coding: utf-8 -*-
"""RBAC dinamico por tenant (M-B2 do roadmap multi-tenant, PLANO_RBAC §3).

Perfis de acesso vivem em `tenants/{tid}/perfis_acesso/{perfil_id}` como
source of truth; cada usuario referencia um perfil via
`users/{id}.perfil_acesso_id` (espelhado em operator_profiles e no custom
claim). O backend decide permissao por `has_permission(user, perm)` em modo
DUAL-CHECK (§3.8 fase 2): se o toggle existe no perfil do usuario, ele manda;
se o perfil/toggle nao existe (tenant pre-seed, chave nova de catalogo,
falha de leitura), cai no default do seed da role — que reproduz 1:1 o
comportamento hardcoded anterior. Dia 0 do RBAC = dia anterior.

O catalogo de toggles e FIXO da plataforma (decisao §10.1 do PLANO_RBAC):
admin do tenant escolhe perfis e valores, nunca inventa chave nova. So
entram no catalogo chaves com ponto de enforcement REAL no codigo — toggle
sem efeito enganaria o admin do tenant (ver inventario M-B2 no doc).

Limite arquitetural (§3.6): Firestore rules continuam autorizando pelo
claim `role` grosso (admin/supervisor/operador) — nunca leem toggles. Um
perfil customizado que AMPLIE visibilidade alem da role do usuario vale so
no caminho REST/backend; os snapshot listeners continuam limitados pelas
rules. Os seeds nao cruzam esse teto.
"""

import logging
import os
import time

from fastapi import HTTPException

from firestore_common import document, get_tenant_context, tenant_context, utcnow

logger = logging.getLogger("castro_crm.rbac")

# ---------------------------------------------------------------------------
# Catalogo de toggles. Chaves snake_case ESTAVEIS — mudam apenas com
# migracao explicita. Agrupamento e rotulo alimentam a UI master-detail;
# a semantica de cada chave vive nos endpoints/branches que a checam.
#
# Nota de inventario (2026-07-04): as chaves ver_proprios_leads,
# ver_leads_sem_dono, ver_leads_setor, ver_canal_coex_proprio, ver_audit_log,
# ver_transfer_log e re_onboarding_coex do rascunho do PLANO_RBAC §3.4 NAO
# entraram: o escopo do operador comum (proprios + pool) e estrutural
# (queries scoped + Firestore rules por claim role) e nao ha check de codigo
# que um toggle pudesse controlar sem redesenho das rules.
# ---------------------------------------------------------------------------

PERMISSION_CATALOG = [
    # (grupo, chave, rotulo UI)
    ("Visibilidade", "ver_todos_leads", "Ver todos os leads e atendimentos do tenant"),
    ("Atendimento", "enviar_mensagem_propria_thread", "Enviar mensagem em thread propria"),
    ("Atendimento", "enviar_mensagem_qualquer_thread", "Agir em qualquer thread (co-pilotagem)"),
    ("Atendimento", "assumir_coex_proprio", "Assumir thread do proprio numero coexistence"),
    ("Atendimento", "assumir_supervisor", "Takeover supervisor"),
    ("Atendimento", "transferir_atendimento", "Transferir atendimento"),
    ("Atendimento", "fechar_atendimento_manual", "Fechar atendimento"),
    ("Atendimento", "reabrir_atendimento_manual", "Reabrir atendimento"),
    ("Atendimento", "enviar_nota_interna", "Sussurro (nota interna)"),
    ("Atendimento", "enviar_template", "Enviar template"),
    ("Lead", "editar_dono_lead", "Reatribuir dono do lead / devolver ao bot"),
    ("Lead", "qualificar_lead", "Qualificar lead"),
    ("Lead", "editar_declared_name", "Editar nome declarado"),
    ("Lead", "arquivar_lead", "Arquivar lead"),
    ("Lead", "adicionar_contato_manual", "Adicionar contato manual"),
    ("Lead", "exportar_contatos", "Exportar contatos e conversas (LGPD)"),
    ("Canais", "gerenciar_canais", "Gerenciar canais WhatsApp"),
    ("Canais", "desativar_canais", "Desativar canais / descartar eventos de webhook"),
    ("Canais", "autorizar_coex_para_operador", "Autorizar coexistence para operador"),
    ("Auditoria", "ver_painel_conflitos", "Ver painel de conflitos"),
    ("Auditoria", "ver_dashboard_uso", "Ver dashboard e uso (billing)"),
    ("Auditoria", "buscar_protocolo", "Buscar protocolo de atendimento"),
    ("Gestao", "gerenciar_usuarios", "Criar e editar usuarios"),
    ("Gestao", "desativar_usuarios", "Desativar usuarios"),
    ("Gestao", "gerenciar_perfis_acesso", "Gerenciar perfis de acesso"),
    ("Gestao", "gerenciar_departamentos", "Criar e editar setores"),
    ("Gestao", "desativar_departamentos", "Desativar setores"),
    ("Gestao", "gerenciar_config_sistema", "Alterar configuracoes do sistema"),
]

PERMISSION_KEYS = [key for _, key, _ in PERMISSION_CATALOG]

# §3.3 (endurecido pos-canario M-B2): no perfil de SISTEMA (perfil_admin,
# is_system_locked) TODOS os toggles sao travados em ligado — o perfil e o
# teto do tenant. Travar so um subconjunto criava um ratchet: desligar um
# toggle do proprio perfil_admin fazia o guard anti-amplificacao ("nao
# concede o que nao possui") impedir o admin de RELIGA-lo em qualquer
# perfil, sem saida pela UI. Perfil administrativo limitado = perfil
# customizado com base admin, nunca o de sistema.

ROLE_TO_PERFIL = {
    "admin": "perfil_admin",
    "supervisor": "perfil_supervisor",
    "operador": "perfil_operador",
}

SEED_PERFIL_IDS = tuple(ROLE_TO_PERFIL.values())


def _toggles(true_keys):
    return {key: (key in true_keys) for key in PERMISSION_KEYS}


# ---------------------------------------------------------------------------
# Perfis seed (§3.5) — REPRODUZEM 1:1 o comportamento hardcoded pre-RBAC
# (inventario M-B2 2026-07-04 sobre main.py/database_firestore.py/App.tsx/
# CrmContext.tsx). Divergencias conscientes do rascunho original do plano:
# - supervisor TEM exportar_contatos e autorizar_coex_para_operador (o
#   codigo atual permite; o rascunho dizia que nao);
# - supervisor TEM gerenciar_canais (create/update/sync sao admin+supervisor
#   hoje); acoes destrutivas ficam em desativar_* (so admin hoje);
# - operador TEM transferir_atendimento (POST /api/wa/transfer nunca teve
#   gate de role — o fluxo do bot depende disso).
# ---------------------------------------------------------------------------

SEED_PERFIS = {
    "perfil_admin": {
        "nome": "Administrador",
        "descricao": "Acesso total ao tenant. Perfil de sistema (travado).",
        "role_equivalente": "admin",
        "is_system_locked": True,
        "toggles": {key: True for key in PERMISSION_KEYS},
    },
    "perfil_supervisor": {
        "nome": "Supervisor",
        "descricao": "Gestao de atendimento e equipe, sem acoes destrutivas de administracao.",
        "role_equivalente": "supervisor",
        "is_system_locked": False,
        "toggles": _toggles({
            "ver_todos_leads",
            # Atendimento (tudo exceto assumir_coex_proprio — exclusivo do dono)
            "enviar_mensagem_propria_thread", "enviar_mensagem_qualquer_thread",
            "assumir_supervisor", "transferir_atendimento",
            "fechar_atendimento_manual", "reabrir_atendimento_manual",
            "enviar_nota_interna", "enviar_template",
            # Lead
            "editar_dono_lead", "qualificar_lead", "editar_declared_name",
            "arquivar_lead", "adicionar_contato_manual", "exportar_contatos",
            # Canais (sem acoes destrutivas)
            "gerenciar_canais", "autorizar_coex_para_operador",
            # Auditoria
            "ver_painel_conflitos", "ver_dashboard_uso", "buscar_protocolo",
            # Gestao (cria/edita usuarios e setores; NAO desativa, NAO mexe
            # em perfis nem config de sistema — hoje so admin)
            "gerenciar_usuarios", "gerenciar_departamentos",
        }),
    },
    "perfil_operador": {
        "nome": "Operador",
        "descricao": "Atendimento do proprio escopo (atribuidos + pool).",
        "role_equivalente": "operador",
        "is_system_locked": False,
        "toggles": _toggles({
            "enviar_mensagem_propria_thread", "assumir_coex_proprio",
            "transferir_atendimento", "fechar_atendimento_manual",
            "reabrir_atendimento_manual", "enviar_template",
            "qualificar_lead", "editar_declared_name", "arquivar_lead",
            "adicionar_contato_manual",
        }),
    },
}


def default_perfil_for_role(role):
    """Perfil seed correspondente a role legada ('' se role desconhecida)."""
    return ROLE_TO_PERFIL.get(str(role or "").strip().lower(), "")


# ---------------------------------------------------------------------------
# Cache in-memory (por instancia Cloud Run) dos toggles por (tenant, perfil).
# Mesmo racional do cache de auth: o perfil e lido em TODA request que checa
# permissao. TTL curto limita staleness entre replicas — o PUT de perfil
# invalida a replica local na hora; as demais convergem no TTL.
# ---------------------------------------------------------------------------

_PERFIL_CACHE_TTL = float(os.getenv("RBAC_PERFIL_CACHE_TTL_SECONDS", "60") or 60)
_perfil_cache: dict = {}

# Sentinela para cachear tambem a AUSENCIA do doc (evita re-read por request
# em tenant pre-seed) sem confundir com falha de leitura.
_MISSING = object()

# Falha de leitura e cacheada por TTL CURTO: sem isso, numa janela de
# degradacao do Firestore toda request autenticada re-tentaria a leitura
# sincrona no hot path (retry storm que amplifica o incidente). O dual-check
# cobre o intervalo com o fallback da role.
_FAILED = object()
_FAILURE_CACHE_TTL = min(5.0, _PERFIL_CACHE_TTL) if _PERFIL_CACHE_TTL > 0 else 5.0


def invalidate_perfil_cache(tenant_id=None, perfil_id=None):
    """Limpa o cache de perfis. Sem args -> tudo; so tenant -> perfis do
    tenant; tenant+perfil -> entrada unica. Chamar em qualquer mutacao de
    perfis_acesso."""
    if tenant_id is None:
        _perfil_cache.clear()
        return
    if perfil_id is not None:
        _perfil_cache.pop((str(tenant_id), str(perfil_id)), None)
        return
    for key in [k for k in _perfil_cache if k[0] == str(tenant_id)]:
        _perfil_cache.pop(key, None)


def _read_perfil_doc(tenant_id, perfil_id):
    with tenant_context(tenant_id):
        snap = document("perfis_acesso", perfil_id).get()
    if not snap.exists:
        return None
    return snap.to_dict() or {}


def get_perfil(tenant_id, perfil_id):
    """Doc completo do perfil (ou None se nao existe). Cacheado por TTL.

    Falha de leitura do Firestore retorna None SEM cachear — o caller
    (has_permission) degrada pro fallback de role e a proxima request
    re-tenta.
    """
    tenant_id = str(tenant_id or "")
    perfil_id = str(perfil_id or "")
    if not tenant_id or not perfil_id:
        return None
    key = (tenant_id, perfil_id)
    entry = _perfil_cache.get(key)
    if entry is not None:
        expires_at, value = entry
        if time.monotonic() < expires_at:
            return None if value in (_MISSING, _FAILED) else value
        _perfil_cache.pop(key, None)
    try:
        doc = _read_perfil_doc(tenant_id, perfil_id)
    except Exception as exc:
        logger.warning("get_perfil: leitura falhou (tenant=%s perfil=%s): %s", tenant_id, perfil_id, exc)
        _perfil_cache[key] = (time.monotonic() + _FAILURE_CACHE_TTL, _FAILED)
        return None
    if _PERFIL_CACHE_TTL > 0:
        _perfil_cache[key] = (time.monotonic() + _PERFIL_CACHE_TTL, doc if doc is not None else _MISSING)
    return doc


def get_perfil_toggles(tenant_id, perfil_id):
    """Dict de toggles do perfil, ou None se o perfil nao existe/ilegivel."""
    doc = get_perfil(tenant_id, perfil_id)
    if doc is None:
        return None
    toggles = doc.get("toggles")
    return dict(toggles) if isinstance(toggles, dict) else None


# ---------------------------------------------------------------------------
# Decisao de permissao (dual-check §3.8 fase 2)
# ---------------------------------------------------------------------------

def _resolve_tenant(current_user):
    # SEM fallback cego pra um tenant fixo: fora de um contexto tenant-aware
    # a resolucao retorna '' e a decisao cai no fallback do seed da ROLE
    # (nunca nos docs de outro tenant). Matar o _DEFAULT_TENANT e debito
    # aberto do M-A4b — a infra nova nao reintroduz o padrao.
    return str((current_user or {}).get("tenant_id") or "") or get_tenant_context() or ""


def _fallback_role_toggle(role, perm):
    seed = SEED_PERFIS.get(default_perfil_for_role(role))
    if not seed:
        return False
    return bool(seed["toggles"].get(perm, False))


def has_permission(current_user, perm):
    """True se o usuario tem o toggle `perm`.

    Ordem: (1) modo impersonate read-only nega tudo; (2) toggle presente no
    perfil do usuario decide; (3) fallback = default do seed da role
    (comportamento pre-RBAC). Default final = False (deny-by-default).
    """
    if not current_user:
        return False
    if current_user.get("read_only") or current_user.get("impersonating"):
        return False
    role = current_user.get("role")
    perfil_id = str(current_user.get("perfil_acesso_id") or "") or default_perfil_for_role(role)
    toggles = get_perfil_toggles(_resolve_tenant(current_user), perfil_id) if perfil_id else None
    if toggles is not None and perm in toggles:
        return bool(toggles[perm])
    return _fallback_role_toggle(role, perm)


def ensure_permission(current_user, perm):
    """Levanta 403 se o usuario nao tem o toggle. Uso em endpoint FastAPI."""
    if not has_permission(current_user, perm):
        raise HTTPException(status_code=403, detail=f"Permissao negada ({perm})")
    return current_user


def effective_toggles(current_user):
    """Mapa EFETIVO {chave: bool} de todo o catalogo para o usuario —
    exatamente a decisao do has_permission, chave a chave (o perfil vem do
    cache, entao as N chamadas custam 1 leitura). Alimenta o frontend
    (/api/session) para o can() nao precisar replicar o fallback."""
    return {key: has_permission(current_user, key) for key in PERMISSION_KEYS}


def can_see_all_tenant(current_user):
    """Escopo de DADOS amplo: toggle ver_todos_leads E role privilegiada.

    O teto por role e o mesmo das Firestore rules (§3.6) e do frontend
    (canSeeAll): um perfil "ampliado" alem da role NAO ganha a agenda do
    tenant nem via REST — senao as 3 camadas de isolamento (rules,
    snapshot, REST) divergiriam por transporte (LGPD). Ampliar visibilidade
    exige mudar a role."""
    if str((current_user or {}).get("role") or "") not in ("admin", "supervisor"):
        return False
    return has_permission(current_user, "ver_todos_leads")


def toggles_beyond_user(toggles, current_user):
    """Chaves em `toggles` ligadas (true) que o proprio usuario NAO tem.

    Mecanismo anti-amplificacao: ninguem concede (via atribuicao de perfil
    ou edicao de toggles) um privilegio que nao possui. Role ADMIN e o teto
    duro do tenant e faz bypass ([]): sem isso, qualquer estado degradado do
    perfil do admin viraria ratchet irreversivel pela UI (visto no canario
    M-B2). O guard morde quem esta ABAIXO do teto (ex.: supervisor com
    gerenciar_perfis_acesso delegado)."""
    if str((current_user or {}).get("role") or "") == "admin":
        return []
    return sorted(
        key for key, value in (toggles or {}).items()
        if value and key in PERMISSION_KEYS and not has_permission(current_user, key)
    )


# ---------------------------------------------------------------------------
# CRUD de perfis (tenant ATUAL — rodar com tenant_context da request).
# Autorizacao, guards de uso e audit ficam nos endpoints (main.py).
# ---------------------------------------------------------------------------

def sanitize_toggles(toggles):
    """Filtra para chaves do catalogo e coage a bool. Chave desconhecida e
    descartada (catalogo e fixo da plataforma — §10.1)."""
    if not isinstance(toggles, dict):
        return {}
    return {k: bool(v) for k, v in toggles.items() if k in PERMISSION_KEYS}


def list_perfis(tenant_id):
    """Todos os perfis do tenant, seeds primeiro, ordem estavel."""
    from firestore_common import collection
    rows = []
    with tenant_context(tenant_id):
        for snap in collection("perfis_acesso").stream():
            data = snap.to_dict() or {}
            data.setdefault("id", snap.id)
            rows.append(data)
    seed_order = {pid: i for i, pid in enumerate(SEED_PERFIL_IDS)}
    rows.sort(key=lambda r: (seed_order.get(r.get("id"), len(seed_order)), str(r.get("nome") or "")))
    return rows


def _slugify_perfil_id(nome):
    import re
    import unicodedata
    base = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_") or "custom"
    return f"perfil_{base}"[:60]


def create_perfil(tenant_id, nome, descricao="", toggles=None, base_perfil_id=None):
    """Cria perfil customizado no tenant. Toggles partem do perfil base
    SEED (default: operador — menor privilegio) e recebem os overrides
    sanitizados. base_perfil_id desconhecido e ERRO explicito — fallback
    silencioso criaria um perfil minimo que o admin acharia ser um clone.
    Retorna o doc criado. Levanta ValueError em conflito/base invalida."""
    nome = str(nome or "").strip()
    if not nome:
        raise ValueError("nome obrigatorio")
    base_id = base_perfil_id or "perfil_operador"
    if base_id not in SEED_PERFIS:
        raise ValueError(f"base_perfil_id invalido: '{base_id}' (use um perfil seed)")
    base = SEED_PERFIS[base_id]
    merged = dict(base["toggles"])
    merged.update(sanitize_toggles(toggles or {}))
    with tenant_context(tenant_id):
        perfil_id = _slugify_perfil_id(nome)
        ref = document("perfis_acesso", perfil_id)
        if ref.get().exists:
            raise ValueError(f"Perfil '{perfil_id}' ja existe")
        now = utcnow()
        doc = {
            "id": perfil_id,
            "nome": nome,
            "descricao": str(descricao or ""),
            "role_equivalente": base["role_equivalente"],
            "is_system_locked": False,
            "is_seed": False,
            "toggles": merged,
            "created_at": now,
            "updated_at": now,
        }
        ref.set(doc)
    invalidate_perfil_cache(tenant_id, perfil_id)
    return doc


def update_perfil(tenant_id, perfil_id, nome=None, descricao=None, toggles=None, editor_user=None):
    """Atualiza perfil do tenant. Dois guards (defense-in-depth — a UI ja
    desabilita):
    - lock (§3.3, endurecido): perfil is_system_locked nao aceita NENHUM
      toggle desligado — o perfil de sistema e o teto do tenant, sempre
      tudo ligado (ver nota no topo do modulo sobre o ratchet);
    - anti-amplificacao: se editor_user for passado, ele nao pode LIGAR um
      toggle que ele proprio nao tem (senao quem tem so
      gerenciar_perfis_acesso editaria o proprio perfil ate virar admin).
      Role admin faz bypass — ver toggles_beyond_user.
    Retorna (before, after) para audit, ou None se o perfil nao existe."""
    with tenant_context(tenant_id):
        ref = document("perfis_acesso", perfil_id)
        snap = ref.get()
        if not snap.exists:
            return None
        before = snap.to_dict() or {}
        fields = {"updated_at": utcnow()}
        if nome is not None and str(nome).strip():
            fields["nome"] = str(nome).strip()
        if descricao is not None:
            fields["descricao"] = str(descricao)
        if toggles is not None:
            incoming = sanitize_toggles(toggles)
            if before.get("is_system_locked"):
                desligados = sorted(k for k, v in incoming.items() if v is False)
                if desligados:
                    raise PermissionError(
                        "Perfil de sistema: todas as permissoes ficam sempre ligadas. "
                        "Para um perfil administrativo limitado, crie um perfil customizado."
                    )
            if editor_user is not None:
                previous = before.get("toggles") or {}
                enabling = {k: v for k, v in incoming.items() if v and not previous.get(k)}
                beyond = toggles_beyond_user(enabling, editor_user)
                if beyond:
                    raise PermissionError(
                        "Voce nao pode conceder permissoes que nao possui: "
                        + ", ".join(beyond)
                    )
            merged = dict(before.get("toggles") or {})
            merged.update(incoming)
            fields["toggles"] = merged
        ref.set(fields, merge=True)
    invalidate_perfil_cache(tenant_id, perfil_id)
    after = dict(before)
    after.update(fields)
    return before, after


def delete_perfil(tenant_id, perfil_id):
    """Remove perfil customizado do tenant. Seeds/travados nunca —
    o caller tambem valida que nenhum usuario ativo referencia o perfil."""
    with tenant_context(tenant_id):
        ref = document("perfis_acesso", perfil_id)
        snap = ref.get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        if data.get("is_seed") or data.get("is_system_locked") or perfil_id in SEED_PERFIL_IDS:
            raise PermissionError("Perfis de sistema nao podem ser excluidos")
        ref.delete()
    invalidate_perfil_cache(tenant_id, perfil_id)
    return True


# ---------------------------------------------------------------------------
# Seed (§3.5) — idempotente, roda dentro de tenant_context no bootstrap.
# ---------------------------------------------------------------------------

def seed_perfis_acesso():
    """Cria os 3 perfis seed do tenant ATUAL se ainda nao existem.

    NAO sobrescreve perfil existente (ajustes do admin do tenant sao
    preservados em re-boot). Chave nova de catalogo em doc antigo fica
    ausente e resolve pelo fallback de role no dual-check.
    """
    created = 0
    for perfil_id, spec in SEED_PERFIS.items():
        ref = document("perfis_acesso", perfil_id)
        try:
            if ref.get().exists:
                continue
            now = utcnow()
            ref.set({
                "id": perfil_id,
                "nome": spec["nome"],
                "descricao": spec["descricao"],
                "role_equivalente": spec["role_equivalente"],
                "is_system_locked": spec["is_system_locked"],
                "is_seed": True,
                "toggles": dict(spec["toggles"]),
                "created_at": now,
                "updated_at": now,
            })
            created += 1
        except Exception as exc:
            # Best-effort: seed parcial nao derruba o boot; dual-check cobre
            # o perfil faltante e o proximo boot re-tenta.
            logger.warning("seed_perfis_acesso: falha ao semear %s: %s", perfil_id, exc)
    tid = get_tenant_context() or ""
    if created:
        invalidate_perfil_cache(tid or None)
        logger.info("Perfis RBAC semeados | tenant=%s created=%d", tid or "(flat)", created)
    return created
