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


def set_tenant_claims(firebase_uid, tenant_id, role=None, base_claims=None):
    """Define custom claims tenant_id (e role opcional) no usuario Firebase,
    PRESERVANDO os demais claims ja existentes.

    O JWT do usuario passa a carregar essas claims, lidas pelo backend em
    get_current_user. O cliente precisa renovar o ID token (forceRefresh)
    para o claim aparecer na proxima chamada — o frontend deve chamar
    user.getIdToken(true) apos qualquer set_tenant_claims.

    base_claims: se fornecido (ex: leitura estrita ja feita pelo caller),
    usa como base e evita reler o usuario. Sem base_claims, le do Firebase;
    se a leitura falhar, NAO grava (retorna False) — gravar sobre base {}
    apagaria claims extras (ex: super_admin) do usuario.
    """
    if not firebase_uid:
        raise ValueError("firebase_uid obrigatorio")
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    app = get_firebase_app()
    if base_claims is not None:
        current_claims = dict(base_claims)
    else:
        try:
            existing = auth.get_user(firebase_uid, app=app)
            current_claims = dict(existing.custom_claims or {})
        except Exception as exc:
            logger.error(
                "set_tenant_claims: get_user falhou; NAO gravando p/ nao apagar "
                "claims existentes | uid=%s exc=%s", firebase_uid, exc,
            )
            return False
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


def get_user_claims_strict(firebase_uid):
    """Como get_user_claims, mas PROPAGA excecao em falha de leitura.

    Para fluxos que DECIDEM escrever claims com base no valor lido (ex:
    bootstrap de tenant): um erro transitorio nao pode ser confundido com
    'sem claims' — senao o caller reescreve/revoga sem necessidade e
    desloga o usuario.
    """
    if not firebase_uid:
        return {}
    app = get_firebase_app()
    return dict((auth.get_user(firebase_uid, app=app).custom_claims or {}))


def get_or_create_firebase_user(email, display_name=""):
    """Resolve a conta Firebase Auth do email; cria se nao existir.

    Retorna (uid, created). A conta nova nasce SEM provider de senha — o
    acesso inicial e via login federado (Google/OIDC com o mesmo email) OU
    um link de convite/definicao de senha gerado pelo painel super-admin
    (sign-in link). NAO assumir generate_password_reset_link direto: sem
    provider de senha ele pode falhar. Usado no provisionamento de tenant
    (M-A2) pra ter o uid ANTES do upsert local — assim users doc,
    operator_profile e custom claims nascem linkados de uma vez (D6).
    """
    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("email obrigatorio")
    app = get_firebase_app()
    try:
        return auth.get_user_by_email(email_norm, app=app).uid, False
    except auth.UserNotFoundError:
        pass
    user = auth.create_user(
        email=email_norm,
        display_name=display_name or None,
        app=app,
    )
    logger.info("Conta Firebase criada no provisionamento | uid=%s", user.uid)
    return user.uid, True


def revoke_refresh_tokens(firebase_uid):
    """Revoga os refresh tokens do usuario.

    Complemento do claim atomico (D6). NOTA HONESTA: como verify_id_token
    roda com check_revoked=False, um ID token JA emitido segue valido ate
    expirar (~1h) — o revoke NAO derruba a sessao atual na hora. O efeito e
    na PROXIMA renovacao/login (o refresh e recusado -> novo login ja emite
    o ID token com os claims novos). Serve exatamente ao caso-alvo do D6
    (admin RECEM-provisionado, sem sessao previa) e a trocas de claim onde
    ~1h de defasagem e aceitavel.
    """
    if not firebase_uid:
        return False
    app = get_firebase_app()
    try:
        auth.revoke_refresh_tokens(firebase_uid, app=app)
        logger.info("Refresh tokens revogados | uid=%s", firebase_uid)
        return True
    except Exception as exc:
        logger.warning("revoke_refresh_tokens falhou | uid=%s exc=%s", firebase_uid, exc)
        return False
