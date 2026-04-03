# -*- coding: utf-8 -*-

import logging

from config import (
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
    ALLOWED_FIREBASE_EMAILS,
    AUTO_PROVISION_FIREBASE_USERS,
)
from database import (
    get_user_by_email,
    get_user_by_firebase_uid,
    get_user_by_id,
    log_audit,
    sync_user_identity,
    update_last_login,
    upsert_firebase_user,
)
from firebase_admin_client import verify_firebase_id_token

logger = logging.getLogger("castro_crm.auth")


def _firebase_email_allowed(email):
    email = (email or "").strip().lower()
    if ALLOWED_FIREBASE_EMAILS and email in ALLOWED_FIREBASE_EMAILS:
        return True
    if ALLOWED_FIREBASE_EMAIL_DOMAIN:
        return bool(email) and "@" in email and email.split("@", 1)[1].lower() == ALLOWED_FIREBASE_EMAIL_DOMAIN
    return not ALLOWED_FIREBASE_EMAILS


def authenticate_firebase_token(id_token, ip_address=""):
    try:
        decoded = verify_firebase_id_token(id_token)
    except Exception as exc:
        logger.warning("Falha ao validar Firebase ID token: %s", exc)
        return {"success": False, "status_code": 401, "error": "Token Firebase invalido"}

    firebase_uid = decoded.get("uid") or decoded.get("sub")
    email = (decoded.get("email") or "").strip().lower()
    display_name = (decoded.get("name") or email.split("@", 1)[0] or firebase_uid or "").strip()

    if not firebase_uid:
        return {"success": False, "status_code": 401, "error": "Token Firebase sem uid"}

    if not _firebase_email_allowed(email):
        return {"success": False, "status_code": 403, "error": "Acesso restrito ao email ou dominio autorizado"}

    user = get_user_by_firebase_uid(firebase_uid) or get_user_by_email(email)
    if user:
        sync_user_identity(
            user["id"],
            email=email,
            firebase_uid=firebase_uid,
            auth_provider="firebase",
            display_name=display_name or user.get("display_name", ""),
        )
        user = get_user_by_id(user["id"])
    elif AUTO_PROVISION_FIREBASE_USERS and email:
        user = upsert_firebase_user(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name or email,
        )

    if not user:
        return {"success": False, "status_code": 403, "error": "Usuario nao provisionado no CRM"}

    if not user.get("is_active", 1):
        return {"success": False, "status_code": 403, "error": "Usuario desativado"}

    update_last_login(user["id"])
    log_audit(user["id"], "LOGIN_SUCCESS_FIREBASE", email or firebase_uid, ip_address)
    return {
        "success": True,
        "decoded_token": decoded,
        "user": user,
    }
