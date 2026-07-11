# -*- coding: utf-8 -*-
"""Cloud Run B — painel super-admin (`castro-superadmin`). Fase B, bloco 1.

Servico SEPARADO do CRM operacional (Cloud Run A). Deploy proprio, service
account propria, imagem minima (Dockerfile.superadmin). Reusa o nucleo
compartilhado (bootstrap_tenant, super_admin, tenant_service) — fonte unica
da verdade, sem drift.

Escopo v1 (enxuto seguro): criar tenant. require_super_admin exige claim
super_admin + doc super_admins/{uid} ativo + MFA-na-sessao. Impersonate/
analytics/kill-switch-UI ficam pra depois (M-B3).

Rodar local (bootstrap/teste):
  SUPERADMIN_REQUIRE_MFA=false FIRESTORE_PROJECT_ID=<oregon> \
    uvicorn superadmin_main:app --port 8090
(SUPERADMIN_REQUIRE_MFA=false NUNCA em prod — so pra testar antes do enroll.)
"""

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

from config import (
    FIREBASE_WEB_API_KEY, FIREBASE_WEB_APP_ID, FIREBASE_WEB_AUTH_DOMAIN,
    FIREBASE_WEB_MESSAGING_SENDER_ID, FIRESTORE_PROJECT_ID,
)
from firebase_admin_client import verify_firebase_id_token
from super_admin import (
    get_super_admin, is_active_super_admin, log_system_audit,
    set_super_admin_mfa_enrolled,
)
from tenant_service import list_tenants, tenant_exists

logger = logging.getLogger("castro_crm.superadmin")

# Enforcement de MFA-na-sessao. DEFAULT true. So pode ser desligado em
# bootstrap/teste controlado (antes do enrollment) — nunca em prod. Mesmo
# desligado, claim super_admin + doc ativo continuam OBRIGATORIOS.
_REQUIRE_MFA = os.getenv("SUPERADMIN_REQUIRE_MFA", "true").strip().lower() not in ("0", "false", "no", "off")

_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "superadmin_web")

app = FastAPI(title="Castro Superadmin", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Auth: require_super_admin (claim + doc ativo + MFA-na-sessao)
# ---------------------------------------------------------------------------

def _mfa_in_session(decoded: dict) -> bool:
    """True se o ID token veio de um login que usou 2o fator. No Firebase o
    campo e firebase.sign_in_second_factor (ex: 'totp')."""
    return bool((decoded.get("firebase") or {}).get("sign_in_second_factor"))


def _authorize(request: Request, require_mfa: bool) -> dict:
    """Camadas: (1) Bearer valido; (2) claim super_admin; (3) doc ativo;
    (4) MFA-na-sessao — SO se require_mfa (e _REQUIRE_MFA do env).
    Retorna o principal {uid, email, doc, decoded, ip, user_agent}."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
    try:
        decoded = verify_firebase_id_token(token)
    except Exception as exc:
        logger.warning("superadmin: token invalido: %s", exc)
        raise HTTPException(status_code=401, detail="Token invalido")

    uid = decoded.get("uid") or decoded.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token sem uid")
    if decoded.get("super_admin") is not True:
        raise HTTPException(status_code=403, detail="Acesso restrito (super-admin)")
    doc = get_super_admin(uid)
    if not (doc and doc.get("is_active")):
        raise HTTPException(status_code=403, detail="Super-admin inativo ou inexistente")
    if require_mfa and _REQUIRE_MFA and not _mfa_in_session(decoded):
        raise HTTPException(status_code=401, detail="MFA exigido nesta sessao")

    return {
        "uid": uid,
        "email": (decoded.get("email") or "").strip().lower(),
        "doc": doc,
        "decoded": decoded,
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", ""),
    }


def require_super_admin(request: Request) -> dict:
    """Gate COMPLETO (claim + doc ativo + MFA-na-sessao). Para as operacoes
    nucleares (criar tenant, listar, whoami do painel)."""
    return _authorize(request, require_mfa=True)


def require_super_admin_bootstrap(request: Request) -> dict:
    """Gate LEVE (claim + doc ativo, SEM MFA-na-sessao). SO para o
    enrollment do MFA: e chamado logo apos o enroll, quando o ID token
    ainda nao carrega o 2o fator (o enrollment nao muda o token da sessao
    atual). NAO usar em nada que mute tenant/dados."""
    return _authorize(request, require_mfa=False)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class CreateTenantBody(BaseModel):
    tenant_id: str            # slug: minusculo, comeca com letra, a-z 0-9 hifen
    name: str
    plan: str = "professional"
    cnpj: str = ""
    admin_email: str
    admin_display_name: str = ""
    allowed_email_domains: list[str] | None = None

    @field_validator("tenant_id", "name", "admin_email")
    @classmethod
    def _nonblank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("campo obrigatorio")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "require_mfa": _REQUIRE_MFA}


@app.get("/api/superadmin/whoami")
async def whoami(principal: dict = Depends(require_super_admin)):
    d = principal["doc"]
    return {
        "uid": principal["uid"],
        "email": principal["email"],
        "is_active": d.get("is_active"),
        "mfa_enrolled": d.get("mfa_enrolled"),
        "scopes": d.get("scopes"),
        "mfa_in_session": _mfa_in_session(principal["decoded"]),
    }


@app.get("/api/superadmin/tenants")
async def get_tenants(principal: dict = Depends(require_super_admin)):
    return {"tenants": list_tenants(active_only=False)}


@app.post("/api/superadmin/tenants")
async def create_tenant_endpoint(body: CreateTenantBody, principal: dict = Depends(require_super_admin)):
    actor = principal["uid"]
    ip, ua = principal["ip"], principal["user_agent"]

    # Nao reconciliar silenciosamente do painel: se o slug ja existe, e erro
    # explicito (bootstrap_tenant seria idempotente e mascararia).
    if tenant_exists(body.tenant_id):
        raise HTTPException(status_code=409, detail=f"Tenant '{body.tenant_id}' ja existe")

    # AUDIT ANTES DA ACAO (§4.8): se a auditoria falhar, ABORTA — nunca criar
    # tenant sem trilha. log_system_audit propaga excecao de proposito.
    try:
        log_system_audit(
            actor, "create_tenant_attempt",
            detail=f"tid={body.tenant_id} name={body.name} admin={body.admin_email} plan={body.plan}",
            target=body.tenant_id, ip=ip, user_agent=ua,
        )
    except Exception as exc:
        logger.error("superadmin: audit-antes falhou, abortando criacao | %s", exc)
        raise HTTPException(status_code=503, detail="Falha ao auditar; operacao abortada")

    from tenant_bootstrap import bootstrap_tenant
    try:
        result = bootstrap_tenant(
            body.tenant_id,
            name=body.name,
            plan=body.plan,
            cnpj=body.cnpj,
            admin_email=body.admin_email,
            admin_display_name=body.admin_display_name,
            allowed_email_domains=body.allowed_email_domains,
        )
    except ValueError as exc:
        # slug/plan invalido, colisao de dominio, etc. (tenant_service valida)
        log_system_audit(actor, "create_tenant_failed", detail=f"tid={body.tenant_id} err={exc}",
                         target=body.tenant_id, ip=ip, user_agent=ua)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log_system_audit(actor, "create_tenant_error", detail=f"tid={body.tenant_id} err={exc}",
                         target=body.tenant_id, ip=ip, user_agent=ua)
        logger.exception("superadmin: erro ao criar tenant %s", body.tenant_id)
        raise HTTPException(status_code=500, detail="Erro ao criar tenant")

    # Guard "um email = um tenant": ensure_tenant_admin ABORTA (retorna None em
    # admin_user_id) se o email do admin ja pertence a outro tenant. Sinaliza.
    admin_ok = bool(result.get("admin_user_id"))
    log_system_audit(
        actor, "create_tenant_ok",
        detail=f"tid={body.tenant_id} created={result.get('created')} admin_provisionado={admin_ok}",
        target=body.tenant_id, ip=ip, user_agent=ua,
    )
    return {
        **result,
        "admin_provisioned": admin_ok,
        "warning": None if admin_ok else (
            "Tenant criado, mas o admin NAO foi provisionado (email ja vinculado a "
            "outro tenant, ou conta Firebase indisponivel). Verifique."
        ),
    }


@app.post("/api/superadmin/mfa/enrolled")
async def mark_mfa_enrolled(principal: dict = Depends(require_super_admin_bootstrap)):
    """Chamado pela pagina LOGO APOS o enrollment TOTP — a sessao ainda nao
    tem o 2o fator, entao usa o gate LEVE (claim + doc, sem MFA). So o
    proprio super-admin marca a si mesmo (uid do token)."""
    uid = principal["uid"]
    set_super_admin_mfa_enrolled(uid, True)
    log_system_audit(uid, "mfa_enrolled", target=uid, ip=principal["ip"], user_agent=principal["user_agent"])
    return {"status": "ok", "uid": uid, "mfa_enrolled": True}


@app.get("/api/superadmin/config")
async def web_config():
    """Config web do Firebase pra pagina estatica inicializar o SDK. Publico
    (a apiKey web NAO e segredo; a autorizacao e o require_super_admin)."""
    return {
        "firebase": {
            "apiKey": FIREBASE_WEB_API_KEY,
            "authDomain": FIREBASE_WEB_AUTH_DOMAIN,
            "projectId": FIRESTORE_PROJECT_ID,
            "appId": FIREBASE_WEB_APP_ID,
            "messagingSenderId": FIREBASE_WEB_MESSAGING_SENDER_ID,
        },
    }


@app.get("/")
async def index():
    page = os.path.join(_WEB_DIR, "index.html")
    if os.path.exists(page):
        return FileResponse(page, media_type="text/html")
    # Bloco 3 entrega a pagina; ate la, placeholder.
    return JSONResponse({"service": "castro-superadmin", "status": "backend-only (bloco 1)"})
