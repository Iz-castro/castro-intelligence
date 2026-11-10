# -*- coding: utf-8 -*-
"""REST do funil comercial (/api/funnel); dependencias do app injetadas.

Erros sempre como {"detail": {"code", "message"}} (codes estaveis para a UI).
Os corpos (POST da etapa, PUT dos textos da clinica) sao validados aqui SEM
ecoar o que foi enviado: o 422 padrao do FastAPI/pydantic devolve o "input"
(a nota livre do motivo, por exemplo).
Query/path invalidos (ge/le/max_length abaixo) viram 422 invalid_request
pelo handler de RequestValidationError do main.py, restrito a /api/funnel.
"""

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

import config
import funnel_service
from database import get_user_raw_by_id
from firestore_common import get_tenant_context, tenant_context
from followup_access import build_authorizer
from funnel_repository import FunnelRepository
from funnel_service import FunnelService
from rbac import ensure_permission, has_permission


class StageChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_stage: StrictStr
    expected_version: int = Field(strict=True, ge=0)
    reason: StrictStr | None = None
    # Sem max_length de proposito: o limite (NOTE_MAX) e checado no servico,
    # que responde 422 generico sem devolver o texto.
    reason_note: StrictStr | None = None
    appointment_kind: StrictStr | None = None
    operation_id: str = Field(strict=True, pattern=r"^[A-Za-z0-9_-]{8,128}$")
    suggested_by: Literal["bot_outcome", "task_result"] | None = None


class FunnelSettingsRequest(BaseModel):
    """Textos da clinica (tela "Etapas"). Mapa ausente ou nulo = fica como
    esta; mapa enviado substitui o salvo. Tamanho e chaves: no servico
    (funnel_catalog.validate_overrides), com 422 sem eco."""
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=0)
    stage_labels: dict[str, Any] | None = None
    stage_descriptions: dict[str, Any] | None = None
    reason_labels: dict[str, Any] | None = None


def _error(status, code, message):
    return HTTPException(status, detail={"code": code, "message": message})


def _parse(model_class, payload):
    if not isinstance(payload, dict):
        raise _error(422, "invalid_payload", "Dados inválidos.")
    try:
        return model_class.model_validate(payload)
    except ValidationError as exc:
        fields = sorted({str(error["loc"][0]) for error in exc.errors()
                         if error.get("loc") and error["loc"][0] in model_class.model_fields})
        raise HTTPException(422, detail={"code": "invalid_payload", "message": "Dados inválidos.",
                                         "fields": fields})


def parse_stage_body(payload):
    """Corpo canonico (dict com todos os campos) ou 422 sem eco. Usado
    tambem pelo desfecho do "Encerrar atendimento" (body.funnel)."""
    return _parse(StageChangeRequest, payload).model_dump()


def parse_settings_body(payload):
    """{version, <mapas enviados e nao nulos>} ou 422 sem eco."""
    model = _parse(FunnelSettingsRequest, payload)
    body = {"version": model.version}
    for field in ("stage_labels", "stage_descriptions", "reason_labels"):
        value = getattr(model, field)
        if value is not None:
            body[field] = value
    return body


def create_funnel_router(get_current_user, require_contact_access):
    router = APIRouter(prefix="/api/funnel", tags=["funnel"])

    def load_context(current_user):
        """(usuario relido, catalogo, linha) sem checar o toggle da rota."""
        if not getattr(config, "FEATURE_FUNNEL", False):
            raise _error(404, "funnel_disabled", "Funil indisponível neste ambiente.")
        tenant_id = str(current_user.get("tenant_id") or "")
        if not tenant_id or get_tenant_context() != tenant_id:
            raise _error(403, "tenant_mismatch", "Sessão sem contexto de tenant válido.")
        # "Ver como" e sessoes somente leitura nunca chegam ao funil (alem da
        # trava de metodo/rota do middleware): os toggles seriam os do alvo.
        if current_user.get("impersonation") or current_user.get("read_only") or current_user.get("impersonating"):
            raise _error(403, "read_only_session", "Sessão somente de leitura não acessa o funil.")
        with tenant_context(tenant_id):
            row = get_user_raw_by_id(current_user.get("id"))
        # Linha relida por cima da sessao (mesma regra do encerramento).
        user = funnel_service.session_user(current_user, tenant_id, row)
        # Catalogo das telas: config do tenant + nomes/textos da clinica.
        catalog = funnel_service.load_catalog(tenant_id)
        if not catalog:
            raise _error(404, "funnel_disabled", "Funil não habilitado para este tenant.")
        return user, catalog, row

    def require_user(current_user=Depends(get_current_user)):
        context = load_context(current_user)
        ensure_permission(context[0], "ver_funil")
        return context

    def require_config_user(current_user=Depends(get_current_user)):
        # So o /config (decisao do PO): quem encerra atendimento precisa dos
        # desfechos do modal "Encerrar atendimento" mesmo sem ver o funil.
        # Sem nenhum dos dois = o mesmo 403 do RBAC de sempre (ver_funil).
        context = load_context(current_user)
        if not has_permission(context[0], "fechar_atendimento_manual"):
            ensure_permission(context[0], "ver_funil")
        return context

    def service(context):
        user, catalog, row = context
        # A linha relida acima vale para o _actor do servico (sem reler).
        return FunnelService(
            FunnelRepository(user["tenant_id"]), user,
            build_authorizer(user["tenant_id"], require_contact_access, permission="ver_funil"),
            catalog, require_contact_access=require_contact_access, actor_row=row,
        )

    @router.get("/config")
    def funnel_config(context=Depends(require_config_user)):
        # Catalogo + capacidades reais (can_move etc.); o quadro e as demais
        # rotas continuam exigindo ver_funil.
        return service(context).get_config()

    @router.get("/settings")
    def funnel_settings(context=Depends(require_user)):
        # Tela "Etapas": exige gerenciar_config_sistema (no servico, 403 com code).
        return service(context).get_settings()

    @router.put("/settings")
    def update_funnel_settings(payload: Any = Body(None), context=Depends(require_user)):
        return service(context).save_settings(parse_settings_body(payload))

    @router.get("/board")
    def board(order: str = Query("desc", max_length=4), owner_id: int | None = Query(None, ge=1),
              mine: int = Query(0, ge=0, le=1), context=Depends(require_user)):
        return service(context).board(order=order, owner_id=owner_id, mine=bool(mine))

    @router.get("/stages/{stage}/cards")
    def stage_cards(stage: str = Path(..., max_length=40), cursor: str | None = Query(None, max_length=1600),
                    order: str = Query("desc", max_length=4), owner_id: int | None = Query(None, ge=1),
                    mine: int = Query(0, ge=0, le=1), limit: int = Query(20, ge=1, le=50),
                    context=Depends(require_user)):
        return service(context).stage_cards(stage, cursor=cursor, order=order, owner_id=owner_id,
                                            mine=bool(mine), limit=limit)

    @router.get("/contacts/{contact_id}")
    def contact(contact_id: int = Path(..., ge=1), context=Depends(require_user)):
        return service(context).contact_drawer(contact_id)

    @router.get("/contacts/{contact_id}/stage")
    def contact_stage(contact_id: int = Path(..., ge=1), context=Depends(require_user)):
        # Revalidacao leve do drawer: so etapa, versao e acesso.
        return service(context).contact_stage(contact_id)

    @router.get("/contacts/{contact_id}/history")
    def history(contact_id: int = Path(..., ge=1), cursor: str | None = Query(None, max_length=1600),
                context=Depends(require_user)):
        return service(context).contact_history(contact_id, cursor)

    @router.get("/contacts/{contact_id}/context")
    def contact_context(contact_id: int = Path(..., ge=1),
                        conversation_id: str | None = Query(None, max_length=160),
                        context=Depends(require_user)):
        return service(context).contact_context(contact_id, conversation_id)

    @router.get("/contacts/{contact_id}/messages")
    def contact_messages(contact_id: int = Path(..., ge=1), conversation_id: str = Query(..., max_length=160),
                         limit: int = Query(30, ge=1, le=50), context=Depends(require_user)):
        return service(context).contact_messages(contact_id, conversation_id, limit)

    @router.post("/contacts/{contact_id}/stage")
    def change_stage(contact_id: int = Path(..., ge=1), payload: Any = Body(None),
                     context=Depends(require_user)):
        return service(context).change_stage(contact_id, parse_stage_body(payload))

    @router.get("/dashboard")
    def dashboard(month: str | None = Query(None, max_length=7), refresh: int = Query(0, ge=0, le=1),
                  context=Depends(require_user)):
        return service(context).dashboard(month=month, refresh=bool(refresh))

    return router
