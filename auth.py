# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import (
    SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES,
    MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_SECONDS,
)
from database import (
    get_user_by_username, update_last_login,
    increment_failed_attempts, log_audit,
)

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
