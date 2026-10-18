# -*- coding: utf-8 -*-
"""Contrato puro da identidade de visualizacao; nenhum acesso a servicos."""

import hashlib
import re

from config import FIRESTORE_COLLECTION_PREFIX

IMPERSONATION_UID_PREFIX = "imp_ro_"
_SID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ReservedImpersonationIdentityError(ValueError):
    """Identidade de suporte nao e uma conta provisionavel no CRM."""


def is_impersonation_uid(uid):
    return isinstance(uid, str) and uid.startswith(IMPERSONATION_UID_PREFIX)


def require_real_uid(uid):
    """Impede associar identidades temporarias a contas reais do CRM."""
    if is_impersonation_uid(uid):
        raise ReservedImpersonationIdentityError("Identidade temporaria nao pode ser vinculada a usuario CRM")
    return uid


def build_auth_uid(sid, environment=None):
    if not isinstance(sid, str) or not _SID_PATTERN.fullmatch(sid):
        raise ValueError("SID de visualizacao invalido")
    environment = FIRESTORE_COLLECTION_PREFIX if environment is None else environment
    digest = hashlib.sha256(environment.encode("utf-8")).hexdigest()[:8]
    return f"{IMPERSONATION_UID_PREFIX}{digest}_{sid}"


def is_impersonation_token(decoded):
    # Namespace continua restrito mesmo apos login sem os claims transitorios.
    return bool(decoded.get("imp")) or is_impersonation_uid(decoded.get("uid") or decoded.get("sub"))


def valid_impersonation_subject(decoded):
    uid = decoded.get("uid") or decoded.get("sub")
    sid = decoded.get("imp_sid")
    target_uid = decoded.get("imp_target_uid")
    actor_uid = decoded.get("imp_by_uid")
    if decoded.get("imp") is not True or not isinstance(sid, str) or not _SID_PATTERN.fullmatch(sid):
        return False
    if decoded.get("imp_env") != FIRESTORE_COLLECTION_PREFIX or uid != build_auth_uid(sid):
        return False
    if not isinstance(target_uid, str) or not target_uid or is_impersonation_uid(target_uid):
        return False
    if not isinstance(actor_uid, str) or not actor_uid or is_impersonation_uid(actor_uid):
        return False
    if target_uid == actor_uid or type(decoded.get("imp_by")) is not int or decoded["imp_by"] <= 0:
        return False
    return (isinstance(decoded.get("tenant_id"), str) and bool(decoded["tenant_id"])
            and decoded.get("role") in ("operador", "supervisor")
            and isinstance(decoded.get("perfil_acesso_id"), str) and bool(decoded["perfil_acesso_id"]))
