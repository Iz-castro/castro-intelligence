# -*- coding: utf-8 -*-

import logging

import firebase_admin
from firebase_admin import auth

from config import FIREBASE_STORAGE_BUCKET, FIRESTORE_PROJECT_ID

logger = logging.getLogger("castro_crm.firebase_admin")


def get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        options = {}
        if FIRESTORE_PROJECT_ID:
            options["projectId"] = FIRESTORE_PROJECT_ID
        if FIREBASE_STORAGE_BUCKET:
            options["storageBucket"] = FIREBASE_STORAGE_BUCKET
        return firebase_admin.initialize_app(options=options or None)


def verify_firebase_id_token(id_token):
    app = get_firebase_app()
    return auth.verify_id_token(id_token, app=app, check_revoked=False)


def set_tenant_claims(firebase_uid, tenant_id, role=None):
    """Define custom claims tenant_id (e role opcional) no usuario Firebase.

    O JWT do usuario passa a carregar essas claims, lidas pelo backend em
    get_current_user. O cliente precisa renovar o ID token (forceRefresh)
    para o claim aparecer na proxima chamada — o frontend deve chamar
    user.getIdToken(true) apos qualquer set_tenant_claims.
    """
    if not firebase_uid:
        raise ValueError("firebase_uid obrigatorio")
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    app = get_firebase_app()
    try:
        existing = auth.get_user(firebase_uid, app=app)
        current_claims = dict(existing.custom_claims or {})
    except Exception as exc:
        logger.warning("set_tenant_claims: get_user falhou para %s: %s", firebase_uid, exc)
        current_claims = {}
    current_claims["tenant_id"] = str(tenant_id)
    if role:
        current_claims["role"] = str(role)
    try:
        auth.set_custom_user_claims(firebase_uid, current_claims, app=app)
        logger.info(
            "Custom claims atualizados | uid=%s tenant_id=%s role=%s",
            firebase_uid, tenant_id, role or "(unchanged)",
        )
        return True
    except Exception as exc:
        logger.error("set_tenant_claims: falha ao setar claims | uid=%s exc=%s", firebase_uid, exc)
        return False


def get_user_claims(firebase_uid):
    """Retorna o dict de custom claims do usuario Firebase, ou {} se none."""
    if not firebase_uid:
        return {}
    app = get_firebase_app()
    try:
        return dict((auth.get_user(firebase_uid, app=app).custom_claims or {}))
    except Exception as exc:
        logger.warning("get_user_claims: falha para %s: %s", firebase_uid, exc)
        return {}
