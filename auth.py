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
from firebase_admin_client import set_tenant_claims, verify_firebase_id_token
from firestore_common import set_tenant_context

logger = logging.getLogger("castro_crm.auth")

# Tenant default usado durante a transicao multi-tenant — todos os usuarios
# pre-existentes do CRM Hubloc operam neste tenant ate que o custom_claim
# correspondente seja propagado.
_DEFAULT_TENANT = "hubloc"


def _resolve_tenant_id(decoded_token, user):
    """Resolve tenant_id do usuario autenticado.

    Ordem de busca:
      1. custom_claims do token (preferencia — set por set_tenant_claims)
      2. user.tenant_id (campo do doc do CRM, futuro Fase 2)
      3. None (sistema single-tenant ainda — backend trata como legado)

    Quando claim e ausente mas user.tenant_id existe, ressincroniza
    custom_claims em background. Cliente precisa renovar token na
    proxima request para o claim aparecer.
    """
    claim_tenant = (decoded_token or {}).get("tenant_id")
    if claim_tenant:
        return str(claim_tenant)

    db_tenant = (user or {}).get("tenant_id") if user else None
    if db_tenant:
        firebase_uid = (user or {}).get("firebase_uid", "")
        if firebase_uid:
            try:
                set_tenant_claims(firebase_uid, str(db_tenant), role=user.get("role"))
                logger.info(
                    "tenant_id sincronizado em custom_claims | user_id=%s tenant_id=%s "
                    "(usuario precisa renovar ID token para refletir)",
                    user.get("id"), db_tenant,
                )
            except Exception as exc:
                logger.warning("Falha ao sincronizar custom_claims: %s", exc)
        return str(db_tenant)

    return None


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

    # Seta tenant_context EARLY para que todos os lookups abaixo
    # (get_user_by_firebase_uid, get_user_by_email etc.) operem na
    # subcolecao correta do tenant. Usa claim do JWT ou fallback para
    # _DEFAULT_TENANT durante a migration. Nao reseta — o contextvar
    # vive ate o fim da request via FastAPI dependency lifecycle.
    claim_tenant = decoded.get("tenant_id") or _DEFAULT_TENANT
    set_tenant_context(claim_tenant)

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

    # Resolve e anexa tenant_id ao user retornado.
    # No estado atual (pre Fase 2.B/C), tenant_id pode ser None — backend
    # legado ignora. Apos Fase 2.B/C, todas as queries usam.
    tenant_id = _resolve_tenant_id(decoded, user)
    if tenant_id:
        user = dict(user)
        user["tenant_id"] = tenant_id

    return {
        "success": True,
        "decoded_token": decoded,
        "user": user,
    }
