# -*- coding: utf-8 -*-
"""Registro e ciclo de vida do Ver como; nunca altera contas dos alvos."""

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import FIRESTORE_COLLECTION_PREFIX, IMPERSONATE_TTL_MINUTES
from firestore_common import collection, document, tenant_context, utcnow
from impersonation_identity import build_auth_uid, is_impersonation_uid, valid_impersonation_subject

logger = logging.getLogger("castro_crm.impersonation")
COLLECTION = "impersonation_sessions"
CLEANUP_DELAY = timedelta(hours=2)


def _timestamp(value):
    return value if isinstance(value, datetime) and value.tzinfo is not None else None


def create_session(admin, target, tenant_id, role, perfil_id, sid=None, now=None):
    """Persiste somente metadados de suporte, antes de entregar credencial."""
    sid = sid or uuid4().hex
    now = (now or utcnow()).astimezone(timezone.utc).replace(microsecond=0)
    session = {
        "sid": sid, "auth_uid": build_auth_uid(sid),
        "target_uid": target["firebase_uid"], "target_user_id": target["id"],
        "admin_uid": admin["firebase_uid"], "admin_user_id": admin["id"],
        "tenant_id": tenant_id, "environment": FIRESTORE_COLLECTION_PREFIX,
        "role_at_start": role, "perfil_acesso_id_at_start": perfil_id,
        "ttl_seconds": IMPERSONATE_TTL_MINUTES * 60, "created_at": now,
        "expires_at": now + timedelta(minutes=IMPERSONATE_TTL_MINUTES),
        "cleanup_after": now + CLEANUP_DELAY, "status": "active",
    }
    if not _valid_record(session, sid, tenant_id):
        raise ValueError("Registro de visualizacao invalido")
    with tenant_context(tenant_id):
        document(COLLECTION, sid).create(session)
    return session


def _valid_record(session, sid, tenant_id):
    if not isinstance(session, dict):
        return False
    if session.get("sid") != sid or session.get("tenant_id") != tenant_id:
        return False
    if session.get("environment") != FIRESTORE_COLLECTION_PREFIX:
        return False
    try:
        if session.get("auth_uid") != build_auth_uid(sid):
            return False
    except ValueError:
        return False
    target_uid, admin_uid = session.get("target_uid"), session.get("admin_uid")
    if (not isinstance(target_uid, str) or not target_uid or is_impersonation_uid(target_uid)
            or not isinstance(admin_uid, str) or not admin_uid or is_impersonation_uid(admin_uid)
            or target_uid == admin_uid):
        return False
    if (type(session.get("target_user_id")) is not int or session["target_user_id"] <= 0
            or type(session.get("admin_user_id")) is not int or session["admin_user_id"] <= 0
            or session["target_user_id"] == session["admin_user_id"]):
        return False
    ttl = session.get("ttl_seconds")
    created = _timestamp(session.get("created_at"))
    expires = _timestamp(session.get("expires_at"))
    cleanup = _timestamp(session.get("cleanup_after"))
    return (type(ttl) is int and 300 <= ttl <= 3600
            and created is not None and expires is not None and cleanup is not None
            and created.microsecond == 0 and expires == created + timedelta(seconds=ttl)
            and cleanup >= created + CLEANUP_DELAY
            and session.get("role_at_start") in ("operador", "supervisor")
            and isinstance(session.get("perfil_acesso_id_at_start"), str)
            and bool(session["perfil_acesso_id_at_start"]))


def validate_session(decoded):
    """Le registro autoritativo, sem cache/escrita. Falha de banco propaga."""
    if not valid_impersonation_subject(decoded):
        return None
    tenant_id, sid = decoded["tenant_id"], decoded["imp_sid"]
    with tenant_context(tenant_id):
        snap = document(COLLECTION, sid).get()
    session = snap.to_dict() if snap.exists else None
    if not _valid_record(session, sid, tenant_id) or session.get("status") != "active":
        return None
    pairs = {
        "auth_uid": decoded.get("uid") or decoded.get("sub"),
        "target_uid": decoded["imp_target_uid"], "admin_uid": decoded["imp_by_uid"],
        "admin_user_id": decoded["imp_by"], "role_at_start": decoded["role"],
        "perfil_acesso_id_at_start": decoded["perfil_acesso_id"],
    }
    if any(session.get(key) != value for key, value in pairs.items()):
        return None
    now = utcnow()
    exp, auth_time = decoded.get("imp_exp"), decoded.get("auth_time")
    if type(exp) is not int or type(auth_time) is not int:
        return None
    if (exp != int(session["expires_at"].timestamp()) or now >= session["expires_at"]
            or session["created_at"] > now + timedelta(seconds=60)
            or auth_time < session["created_at"].timestamp() - 60
            or auth_time > now.timestamp() + 60
            or now.timestamp() - auth_time > session["ttl_seconds"] + 60):
        return None
    return session


def close_session(session):
    """Fechamento monotono; update nao recria registro que foi removido."""
    if not _valid_record(session, session.get("sid"), session.get("tenant_id")):
        raise ValueError("Registro de visualizacao invalido")
    with tenant_context(session["tenant_id"]):
        document(COLLECTION, session["sid"]).update({"status": "closed", "closed_at": utcnow()})
    return True


def cleanup_expired_sessions(now=None, batch_size=100):
    """Seleciona registros vencidos, incluindo tenants inativos; nunca varre Auth."""
    from firebase_admin import auth as firebase_auth
    from firebase_admin_client import get_firebase_app
    from tenant_service import list_tenants

    now = now or utcnow()
    batch_size = max(1, min(500, int(batch_size)))
    result = {"cleaned": 0, "failed": 0, "rejected": 0, "tenants": 0}
    for tenant in list_tenants(active_only=False):
        tid = str(tenant.get("id") or "")
        if not tid:
            continue
        result["tenants"] += 1
        with tenant_context(tid):
            try:
                rows = list(collection(COLLECTION).where("status", "in", ["active", "closed"])
                            .where("cleanup_after", "<=", now).order_by("cleanup_after").limit(batch_size).stream())
            except Exception:
                result["failed"] += 1
                logger.warning("impersonate cleanup leitura indisponivel | tenant_id=%s", tid)
                continue
            for snap in rows:
                session = snap.to_dict() or {}
                if (not _valid_record(session, snap.id, tid)
                        or session["expires_at"] > now or session["created_at"] + CLEANUP_DELAY > now
                        or session.get("status") not in ("active", "closed")):
                    result["rejected"] += 1
                    logger.warning("impersonate cleanup registro rejeitado | tenant_id=%s", tid)
                    # Desloca registro invalido para nao ocupar todos os lotes.
                    try:
                        snap.reference.update({"cleanup_after": now + timedelta(days=1)})
                    except Exception:
                        result["failed"] += 1
                    continue
                try:
                    try:
                        firebase_auth.delete_user(session["auth_uid"], app=get_firebase_app())
                    except firebase_auth.UserNotFoundError:
                        pass
                    snap.reference.update({"status": "cleaned", "cleaned_at": now})
                    result["cleaned"] += 1
                except Exception:
                    result["failed"] += 1
                    logger.warning("impersonate cleanup falhou | sid=%s", session["sid"])
    return result
