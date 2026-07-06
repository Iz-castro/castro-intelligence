# -*- coding: utf-8 -*-

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from config import (
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
    ALLOWED_FIREBASE_EMAILS,
    AUTO_PROVISION_FIREBASE_USERS,
)
from database import (
    get_user_by_email,
    get_user_by_firebase_uid,
    get_user_by_id,
    get_user_raw_by_firebase_uid_or_email,
    log_audit,
    sync_user_identity,
    update_last_login,
    upsert_firebase_user,
)
from firebase_admin_client import set_tenant_claims, verify_firebase_id_token
from firestore_common import set_tenant_context
from tenant_service import resolve_tenant_by_email_domain, single_active_tenant

logger = logging.getLogger("castro_crm.auth")

# Resolucao de tenant no login (pre-#2): NAO existe mais default cego pra
# 'hubloc'. Ordem: claim tenant_id -> dominio do email (allowed_email_domains
# do tenant) -> rede de transicao (single_active_tenant, so enquanto houver 1
# tenant). Um login que nao resolve tenant e negado (nunca cai num tenant
# arbitrario). Ver ROADMAP "Identidade/dominio do tenant" (decisao SOFT).

# authenticate_firebase_token roda em TODO request autenticado (validacao de
# token na dependency get_current_user), nao apenas no login. Logar
# LOGIN_SUCCESS a cada chamada gravava no audit em toda request e, sob rajada
# de requests paralelos, saturava o contador de sequence do audit no Firestore
# (contencao de transacao -> 409 -> 500). Registramos no maximo um LOGIN_SUCCESS
# por janela de sessao por usuario.
_LOGIN_AUDIT_WINDOW = timedelta(minutes=30)

# Cache in-memory (por instancia Cloud Run) do usuario resolvido por
# (tenant, firebase_uid), para evitar ~4 reads + 3 writes Firestore em TODA
# request autenticada. O ID token CONTINUA sendo verificado a cada request
# (seguranca) e o tenant_context continua sendo setado; so o lookup/sync do
# usuario no Firestore e que e cacheado. TTL curto limita a janela de staleness
# (usuario desativado, troca de role/departamento, novo last_login) — apos o TTL
# a proxima request refaz o caminho completo. Chave inclui tenant por defesa
# (firebase_uid ja e unico por projeto Firebase).
_AUTH_CACHE_TTL = float(os.getenv("AUTH_USER_CACHE_TTL_SECONDS", "45") or 45)
_auth_user_cache: dict = {}


def _auth_cache_get(tenant, firebase_uid):
    entry = _auth_user_cache.get((tenant, firebase_uid))
    if not entry:
        return None
    expires_at, user = entry
    if time.monotonic() >= expires_at:
        _auth_user_cache.pop((tenant, firebase_uid), None)
        return None
    return user


def _auth_cache_put(tenant, firebase_uid, user):
    if _AUTH_CACHE_TTL <= 0:
        return
    _auth_user_cache[(tenant, firebase_uid)] = (time.monotonic() + _AUTH_CACHE_TTL, user)


def invalidate_auth_cache(firebase_uid=None):
    """Limpa o cache de auth. Sem arg -> limpa tudo. Chamar ao alterar
    role/departamento/is_active de um usuario para refletir antes do TTL."""
    if firebase_uid is None:
        _auth_user_cache.clear()
        return
    for key in [k for k in _auth_user_cache if k[1] == firebase_uid]:
        _auth_user_cache.pop(key, None)


def _is_new_login_session(previous_login):
    """True se o ultimo login foi ha mais que a janela (ou nunca), indicando
    uma nova sessao que merece audit. Caso contrario e apenas mais um request
    da mesma sessao e nao deve gerar escrita de auditoria."""
    if not previous_login:
        return True
    if isinstance(previous_login, str):
        try:
            previous_login = datetime.fromisoformat(previous_login.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(previous_login, datetime):
        return True
    if previous_login.tzinfo is None:
        previous_login = previous_login.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - previous_login > _LOGIN_AUDIT_WINDOW


def _resolve_tenant_id(decoded_token, user):
    """Resolve tenant_id do usuario autenticado.

    Ordem de busca:
      1. custom_claims do token (preferencia — set por set_tenant_claims)
      2. user.tenant_id (campo do doc do CRM — raro, redundante com path)
      3. tenant_context atual — agora o tenant JA RESOLVIDO em
         authenticate_firebase_token (claim > dominio > rede de transicao),
         nunca mais um default cego. Caso comum: operador sem claim ainda,
         resolvido por dominio, que tera o claim carimbado aqui.
      4. None (nao resolvivel — backend legado ignora).

    Quando claim e ausente mas algum fallback retorna tenant, ressincroniza
    custom_claims em background. Cliente precisa renovar token na
    proxima request (getIdToken(true) ou logout/login) para o claim
    aparecer no JWT — Firestore rules tenant-scoped dependem disso.
    """
    claim_tenant = (decoded_token or {}).get("tenant_id")
    if claim_tenant:
        return str(claim_tenant)

    db_tenant = (user or {}).get("tenant_id") if user else None
    if not db_tenant:
        # Fallback: tenant context atual — o tenant JA RESOLVIDO em
        # authenticate_firebase_token (claim > dominio > rede), nunca cego.
        from firestore_common import get_tenant_context as _get_ctx
        db_tenant = _get_ctx()

    if db_tenant:
        firebase_uid = (user or {}).get("firebase_uid", "") or (decoded_token or {}).get("uid", "")
        if firebase_uid:
            try:
                # Propaga o perfil CUSTOM do doc (se houver) — sem isso o
                # claim nasceria com o seed derivado da role e divergiria do
                # banco ate a proxima edicao do usuario (M-B2).
                set_tenant_claims(
                    firebase_uid, str(db_tenant),
                    role=(user or {}).get("role") or "operador",
                    perfil_acesso_id=(user or {}).get("perfil_acesso_id") or None,
                )
                logger.info(
                    "tenant_id sincronizado em custom_claims | user_id=%s tenant_id=%s "
                    "(usuario precisa renovar ID token para refletir)",
                    (user or {}).get("id"), db_tenant,
                )
            except Exception as exc:
                logger.warning("Falha ao sincronizar custom_claims: %s", exc)
        return str(db_tenant)

    return None


def _is_founder(email):
    """Founder/super-admin da plataforma (env ALLOWED_FIREBASE_EMAILS). Humano
    cross-tenant da Castro Intelligence — loga independente de tenant/dominio."""
    return bool(email) and email in ALLOWED_FIREBASE_EMAILS


def _global_env_domain_match(email):
    """Dominio global do env (ALLOWED_FIREBASE_EMAIL_DOMAIN). Belt-and-
    suspenders da transicao: uniao com os allowed_email_domains por-tenant,
    pra nao regredir o hubloc caso o backfill do doc do tenant falhe."""
    if not ALLOWED_FIREBASE_EMAIL_DOMAIN:
        return False
    return bool(email) and "@" in email and email.split("@", 1)[1].lower() == ALLOWED_FIREBASE_EMAIL_DOMAIN


def _login_gate(claim_tenant, email, domain_authorized):
    """Quem pode INICIAR sessao (reject barato antes de qualquer read de
    usuario). Passa se: founder/super-admin; OU ja tem claim tenant_id (o
    claim autoriza — dominio irrelevante, design SOFT); OU o dominio casa
    algum tenant (candidato a operador do dominio / auto-provision). Mata o
    antigo 'sem allowlist -> libera todo mundo'."""
    return bool(_is_founder(email) or claim_tenant or domain_authorized)


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

    # -- Resolucao de tenant (SEM default cego) --
    # claim > dominio do email > rede de transicao (1 tenant ativo).
    claim_tenant = decoded.get("tenant_id")
    domain_tenant = None if claim_tenant else resolve_tenant_by_email_domain(email)
    # Dominio AUTORIZADO p/ auto-provision: casou um tenant OU o dominio global
    # do env (transicao). Founder nao conta aqui — founder nao auto-provisiona.
    domain_authorized = bool(domain_tenant) or _global_env_domain_match(email)

    # Gate barato (antes de qualquer read de usuario).
    if not _login_gate(claim_tenant, email, domain_authorized):
        return {"success": False, "status_code": 403, "error": "Acesso restrito: usuario nao vinculado a nenhum tenant"}

    # Contexto de LOOKUP: claim > dominio > rede. Se nada resolve (multi-tenant
    # sem claim/dominio), so um founder chegou aqui — e sem contexto nao ha
    # como resolver o tenant dele; nega (nao deveria ocorrer: founders sao
    # provisionados e carregam claim).
    resolved_tenant = claim_tenant or domain_tenant or single_active_tenant()
    if not resolved_tenant:
        logger.error(
            "Login sem tenant resolvivel | email=%s is_founder=%s (sem claim/dominio, multi-tenant)",
            (email[:3] + "***") if email else "?", _is_founder(email),
        )
        return {"success": False, "status_code": 403, "error": "Usuario sem tenant resolvido"}
    resolved_tenant = str(resolved_tenant)

    # Seta tenant_context EARLY para que todos os lookups abaixo
    # (get_user_by_firebase_uid, get_user_by_email etc.) operem na subcolecao
    # correta. Nao reseta — o contextvar vive ate o fim da request via FastAPI
    # dependency lifecycle.
    set_tenant_context(resolved_tenant)

    # Cache hit: evita ~4 reads + 3 writes Firestore por request. O token ja foi
    # verificado acima e o tenant_context ja foi setado — so reaproveitamos o
    # perfil de usuario resolvido (com tenant_id anexado).
    cached_user = _auth_cache_get(resolved_tenant, firebase_uid)
    if cached_user is not None:
        return {"success": True, "decoded_token": decoded, "user": cached_user}

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
    else:
        # M-A4b (offboarding terminal): nenhum doc ATIVO casou. Se existe um
        # doc DESATIVADO para este uid/email, e um ex-operador tentando
        # re-logar — NEGAR. Sem isso, com AUTO_PROVISION ligado o desativado
        # seria recriado como doc novo ativo (e o claim re-emitido no
        # _resolve_tenant_id), ressuscitando o acesso e anulando a
        # desativacao. Tambem evita a duplicata "_2" (auto-provision sobre
        # doc filtrado). Reativacao legitima = is_active=1 no doc original.
        prior = get_user_raw_by_firebase_uid_or_email(firebase_uid, email)
        if prior is not None and not prior.get("is_active", 1):
            logger.warning(
                "Login negado: conta desativada tentou re-provisionar | uid=%s",
                firebase_uid,
            )
            return {"success": False, "status_code": 403, "error": "Usuario desativado"}
        # AUTO_PROVISION tenant-aware: so cria quando o DOMINIO resolveu um
        # tenant (nunca num default cego). Founder/usuario sem dominio casado
        # NAO e auto-criado — cai no "nao provisionado" abaixo. Cria dentro do
        # resolved_tenant (contexto ja setado).
        if AUTO_PROVISION_FIREBASE_USERS and email and domain_authorized:
            user = upsert_firebase_user(
                firebase_uid=firebase_uid,
                email=email,
                display_name=display_name or email,
            )

    if not user:
        return {"success": False, "status_code": 403, "error": "Usuario nao provisionado no CRM"}

    if not user.get("is_active", 1):
        return {"success": False, "status_code": 403, "error": "Usuario desativado"}

    # Captura o ultimo login ANTES de atualizar para decidir se este request
    # inaugura uma nova sessao (merece audit) ou e mais uma chamada da mesma.
    previous_login = user.get("last_login")
    update_last_login(user["id"])
    if _is_new_login_session(previous_login):
        log_audit(user["id"], "LOGIN_SUCCESS_FIREBASE", email or firebase_uid, ip_address)

    # Resolve e anexa tenant_id ao user retornado.
    # No estado atual (pre Fase 2.B/C), tenant_id pode ser None — backend
    # legado ignora. Apos Fase 2.B/C, todas as queries usam.
    tenant_id = _resolve_tenant_id(decoded, user)
    if tenant_id:
        user = dict(user)
        user["tenant_id"] = tenant_id

    _auth_cache_put(resolved_tenant, firebase_uid, user)
    return {
        "success": True,
        "decoded_token": decoded,
        "user": user,
    }
