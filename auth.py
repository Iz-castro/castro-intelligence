# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import (
    SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES,
    MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_SECONDS,
    ALLOWED_FIREBASE_EMAIL_DOMAIN, ALLOWED_FIREBASE_EMAILS, AUTO_PROVISION_FIREBASE_USERS,
)
from database import (
    get_user_by_username, get_user_by_id, get_user_by_email, get_user_by_firebase_uid,
    upsert_firebase_user, sync_user_identity, update_last_login,
    increment_failed_attempts, log_audit,
)
from firebase_admin_client import verify_firebase_id_token

logger = logging.getLogger("castro_crm.auth")


def hash_password(plain):
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain, hashed):
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id, username):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "usr": username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def authenticate(username, password, ip_address=""):
    user = get_user_by_username(username)

    if not user:
        return {"success": False, "error": "Credenciais invalidas"}

    if user.get("locked_until"):
        lock_time = datetime.fromisoformat(user["locked_until"])
        if datetime.now(timezone.utc) < lock_time:
            remaining = int((lock_time - datetime.now(timezone.utc)).total_seconds())
            log_audit(user["id"], "LOGIN_BLOCKED", f"{remaining}s restantes", ip_address)
            return {"success": False, "error": f"Conta bloqueada. Tente em {remaining}s"}

    if not verify_password(password, user["password_hash"]):
        attempts = user.get("failed_attempts", 0) + 1
        lockout = None
        if attempts >= MAX_LOGIN_ATTEMPTS:
            lockout = (datetime.now(timezone.utc) + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat()
            log_audit(user["id"], "LOGIN_LOCKOUT", f"{attempts} tentativas", ip_address)
        increment_failed_attempts(username, lockout)
        log_audit(user["id"], "LOGIN_FAILED", f"Tentativa {attempts}", ip_address)
        return {"success": False, "error": "Credenciais invalidas"}

    update_last_login(user["id"])
    token = create_token(user["id"], user["username"])
    log_audit(user["id"], "LOGIN_SUCCESS", "", ip_address)

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
        },
    }


def _firebase_email_allowed(email):
    email = (email or "").strip().lower()
    # Email avulso autorizado → libera independente do dominio
    if ALLOWED_FIREBASE_EMAILS and email in ALLOWED_FIREBASE_EMAILS:
        return True
    # Dominio autorizado → checa sufixo
    if ALLOWED_FIREBASE_EMAIL_DOMAIN:
        return bool(email) and "@" in email and email.split("@", 1)[1].lower() == ALLOWED_FIREBASE_EMAIL_DOMAIN
    # Nenhuma restricao configurada → libera todos
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
