# -*- coding: utf-8 -*-
"""Fundacao do painel super-admin (Sprint 0 — PLANO_RBAC §4 + §6).

Camada de DADOS (sem FastAPI): reusada pelo Cloud Run B (Fase B) e pelo
scripts/grant_super_admin.py. O require_super_admin (dependency FastAPI com
o check de MFA-na-sessao) vem na Fase B, no servico separado.

Modelo de identidade HIBRIDO (§4.2):
- Claim `super_admin: true` no JWT = fast-path (rules globais isSuperAdmin()).
- Doc `super_admins/{uid}` (root) = SOURCE OF TRUTH. O claim sozinho NUNCA
  autoriza operacao nuclear — o Cloud Run B revalida doc ativo + MFA-na-sessao.

Colecoes (root, fora de qualquer tenant — via global_document/collection):
- `super_admins/{uid}`      : identidade dos super-admins.
- `audit_logs_system/{id}`  : trilha imutavel das operacoes cross-tenant
                              (escrita SO por Admin SDK; rules negam cliente).
"""

import logging

from firestore_common import global_collection, global_document, utcnow

logger = logging.getLogger("castro_crm.super_admin")

# Escopos do super-admin (§4.2). Impersonate fica FORA do v1 (M-B3).
DEFAULT_SCOPES = ["create_tenant", "read_cross_tenant", "kill_switch"]


# ---------------------------------------------------------------------------
# super_admins/{uid} — identidade
# ---------------------------------------------------------------------------

def get_super_admin(uid):
    """Doc do super-admin, ou None. Sem filtro is_active (o caller decide)."""
    if not uid:
        return None
    snap = global_document("super_admins", uid).get()
    return snap.to_dict() if snap.exists else None


def is_active_super_admin(uid):
    """True se existe doc ATIVO para o uid. NAO checa MFA (isso e na sessao,
    validado pelo require_super_admin da Fase B)."""
    doc = get_super_admin(uid)
    return bool(doc and doc.get("is_active"))


def seed_super_admin(uid, email, display_name="", reason="founder", scopes=None, mfa_enrolled=False):
    """Cria o doc super_admins/{uid} se nao existir (idempotente).

    NAO seta o claim super_admin — isso e responsabilidade do
    grant_super_admin.py, executado APOS o MFA estar enrolled (Fase B). Manter
    seed e grant separados preserva a invariante 'sem super-admin ATIVO com
    claim sem MFA'.
    """
    if not uid:
        raise ValueError("uid obrigatorio")
    ref = global_document("super_admins", uid)
    if ref.get().exists:
        logger.info("super_admin ja existe (seed no-op) | uid=%s", uid)
        return get_super_admin(uid)
    now = utcnow()
    doc = {
        "uid": uid,
        "email": (email or "").strip().lower(),
        "display_name": display_name or "",
        "granted_by": "bootstrap",
        "granted_at": now,
        "reason": reason,
        "mfa_enrolled": bool(mfa_enrolled),
        "is_active": True,
        "scopes": list(scopes) if scopes else list(DEFAULT_SCOPES),
        "last_seen_at": None,
        "created_at": now,
        "updated_at": now,
    }
    ref.set(doc)
    logger.info("super_admin semeado | uid=%s email=%s", uid, doc["email"])
    return doc


def set_super_admin_mfa_enrolled(uid, enrolled=True):
    """Marca mfa_enrolled no doc (chamado apos o enrollment TOTP na Fase B)."""
    global_document("super_admins", uid).set(
        {"mfa_enrolled": bool(enrolled), "updated_at": utcnow()}, merge=True,
    )


def deactivate_super_admin(uid):
    """Kill switch (parte doc): marca inativo. O script/B complementa com
    clear do claim + revoke tokens (§4.8)."""
    global_document("super_admins", uid).set(
        {"is_active": False, "updated_at": utcnow()}, merge=True,
    )


def list_super_admins():
    rows = []
    for snap in global_collection("super_admins").stream():
        d = snap.to_dict() or {}
        d.setdefault("uid", snap.id)
        rows.append(d)
    rows.sort(key=lambda r: str(r.get("email") or ""))
    return rows


# ---------------------------------------------------------------------------
# audit_logs_system/{id} — trilha imutavel (§4.6 tier 1)
# ---------------------------------------------------------------------------

def log_system_audit(actor_uid, action, detail=None, target=None,
                     target_tenant_id=None, ip="", user_agent=""):
    """Grava uma entry em audit_logs_system/{id} (root, doc-id automatico).

    Diferente do log_audit por-tenant (best-effort, engole falha): a auditoria
    de operacao NUCLEAR e obrigatoria — esta funcao PROPAGA excecao em falha,
    para o caller poder abortar a operacao (padrao audit-ANTES-da-acao, §4.8).
    Retorna o id da entry.

    NAO logar segredo/PII bruto no detail (mesma regra do log_audit).
    """
    ref = global_collection("audit_logs_system").document()
    entry = {
        "id": ref.id,
        "actor_uid": actor_uid or "",
        "action": action,
        "detail": detail if detail is not None else "",
        "target": target or "",
        "target_tenant_id": target_tenant_id or "",
        "ip": ip or "",
        "user_agent": user_agent or "",
        "created_at": utcnow(),
    }
    ref.set(entry)
    logger.info("system_audit | actor=%s action=%s target=%s", actor_uid, action, target or "-")
    return ref.id
