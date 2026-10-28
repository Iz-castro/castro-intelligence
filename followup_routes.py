# -*- coding: utf-8 -*-
"""REST do follow-up humano; dependencias do app sao injetadas na montagem."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from config import FEATURE_FOLLOWUP
from database import get_user_raw_by_id, get_wa_conversation
from firestore_common import get_tenant_context, tenant_collection
from followup_access import build_authorizer
from followup_repository import FollowupRepository
from followup_service import FollowupService
from commercial_contact_policy import (
    get_commercial_contact_preference, set_commercial_contact_preference,
)
from rbac import can_see_all_tenant, ensure_permission, has_permission


class CommercialPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool
    version: int = Field(strict=True, ge=0)
    operation_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    patient_request_confirmed: StrictBool = False


def _page_alias(response, key):
    return {**response, "items": response.get(key, [])}


def tenant_followup_enabled(tenant_id, tenant_doc=None) -> bool:
    """Follow-up ligado PARA O TENANT: chave geral (FEATURE_FOLLOWUP) E
    settings.followup_enabled=True no doc do tenant (so a Castro grava, como o
    settings.ai). Desligado no tenant = API 404 e tela escondida."""
    if not FEATURE_FOLLOWUP or not tenant_id:
        return False
    if tenant_doc is None:
        try:
            from tenant_service import get_tenant
            tenant_doc = get_tenant(tenant_id) or {}
        except Exception:
            return False
    settings = tenant_doc.get("settings") if isinstance(tenant_doc, dict) else None
    return isinstance(settings, dict) and settings.get("followup_enabled") is True


def create_followup_router(get_current_user, require_contact_access):
    router = APIRouter(prefix="/api/followup", tags=["followup"])

    def require_user(current_user=Depends(get_current_user)):
        if not FEATURE_FOLLOWUP:
            raise HTTPException(404, "Follow-up indisponível neste ambiente")
        tenant_id = str(current_user.get("tenant_id") or "")
        if not tenant_id or get_tenant_context() != tenant_id:
            raise HTTPException(403, "Sessão sem contexto de tenant válido")
        if not tenant_followup_enabled(tenant_id):
            raise HTTPException(404, "Follow-up indisponível para este cliente")
        row = get_user_raw_by_id(current_user.get("id"))
        if (not row or not row.get("is_active", True)
                or str(row.get("firebase_uid") or "") != str(current_user.get("firebase_uid") or "")
                or row.get("tenant_id") not in (None, "", tenant_id)):
            raise HTTPException(403, "Usuário inativo ou identidade alterada")
        user = {**current_user, **row, "tenant_id": tenant_id}
        # Flags de sessao read-only nao podem ser apagadas pelo documento.
        user["read_only"] = bool(current_user.get("read_only"))
        user["impersonating"] = bool(current_user.get("impersonating"))
        ensure_permission(user, "gerenciar_followup")
        return user

    def service(user, settings_write=False):
        can_manage = can_see_all_tenant(user) and has_permission(user, "redistribuir_followup")
        if settings_write:
            ensure_permission(user, "gerenciar_horarios_followup")
        return FollowupService(
            FollowupRepository(user["tenant_id"]), user,
            build_authorizer(user["tenant_id"], require_contact_access),
            can_manage=can_manage,
            can_configure=has_permission(user, "gerenciar_horarios_followup"),
        )

    def eligible(user, contact_id, conversation_id=None):
        authorize = build_authorizer(user["tenant_id"], require_contact_access)
        authorize(contact_id, conversation_id, user)
        manager = can_see_all_tenant(user) and has_permission(user, "redistribuir_followup")
        if not manager:
            return [{"id": user["id"], "display_name": str(user.get("display_name") or "Operador"),
                     "firebase_uid": user["firebase_uid"]}]
        candidates = tenant_collection(user["tenant_id"], "users").order_by("__name__").limit(100).stream()
        result = []
        for snap in candidates:
            row = snap.to_dict() or {}
            if not row.get("is_active", True) or not row.get("firebase_uid"):
                continue
            try:
                user_id = int(row.get("id", snap.id))
            except (TypeError, ValueError):
                continue
            if row.get("tenant_id") not in (None, "", user["tenant_id"]):
                continue
            target = {**row, "id": user_id, "tenant_id": user["tenant_id"]}
            if not has_permission(target, "gerenciar_followup"):
                continue
            try:
                authorize(contact_id, conversation_id, target)
            except HTTPException as exc:
                if exc.status_code in (403, 404, 503):  # 503 = checagem indisponivel: pula o candidato
                    continue
                raise
            result.append({"id": user_id, "display_name": str(row.get("display_name") or "Operador"),
                           "firebase_uid": row["firebase_uid"]})
        return sorted(result, key=lambda row: (row["display_name"].casefold(), row["id"]))

    def preference_authorizer(user):
        def authorize(contact, actor, action):
            if contact.get("is_backup") and not can_see_all_tenant(actor):
                raise HTTPException(403, "Histórico restrito à gestão autorizada")
            require_contact_access(contact, actor)
            if action == "block":
                ensure_permission(actor, "registrar_recusa_comercial")
            elif action == "unblock":
                ensure_permission(actor, "reativar_contato_comercial")
        return authorize

    @router.get("/settings")
    def settings(user=Depends(require_user)):
        return service(user).get_settings()

    @router.put("/settings")
    def update_settings(payload: dict = Body(...), user=Depends(require_user)):
        return service(user, settings_write=True).save_settings(payload)

    @router.get("/tasks")
    def tasks(view: str | None = None, status: str | None = None, group: str | None = None,
              scope: str | None = None, queue_key: str | None = None,
              contact_id: int | None = Query(None, ge=1), cursor: str | None = Query(None, max_length=1600),
              limit: int = Query(30, ge=1, le=50), user=Depends(require_user)):
        if view and view not in ("overdue", "today", "upcoming", "completed", "cancelled", "all"):
            raise HTTPException(422, "Visão de tarefas inválida")
        final_status = status or (view if view in ("completed", "cancelled") else "pending")
        final_group = group or (view if view in ("overdue", "today", "upcoming") else "all")
        final_scope = scope or ("all" if contact_id else "mine")
        if final_scope == "contact":
            if contact_id is None:
                raise HTTPException(422, "Informe o contato para essa visão")
            final_scope = "all"
        filters = {"status": final_status, "group": final_group, "scope": final_scope,
                   "queue_key": queue_key, "contact_id": contact_id, "cursor": cursor, "limit": limit}
        return _page_alias(service(user).list_tasks(filters), "tasks")

    @router.post("/tasks")
    def create_task(payload: dict = Body(...), user=Depends(require_user)):
        return service(user).create_task(payload)

    @router.post("/suggestion")
    def suggestion(payload: dict = Body(...), user=Depends(require_user)):
        return service(user).suggest_due(payload)

    @router.get("/tasks/{task_id}")
    def task(task_id: str, user=Depends(require_user)):
        result = service(user).get_task(task_id)
        row = result["task"]
        result["eligible_assignees"] = eligible(user, row["contact_id"], row.get("conversation_id"))
        return result

    @router.post("/tasks/{task_id}/actions")
    def action(task_id: str, payload: dict = Body(...), user=Depends(require_user)):
        return service(user).task_action(task_id, payload)

    @router.get("/tasks/{task_id}/activities")
    def activities(task_id: str, cursor: str | None = Query(None, max_length=1600),
                   limit: int = Query(30, ge=1, le=50), user=Depends(require_user)):
        return _page_alias(service(user).list_activities({"task_id": task_id, "cursor": cursor, "limit": limit}), "activities")

    @router.get("/operators")
    def operators(contact_id: int = Query(..., ge=1), conversation_id: str | None = None,
                  user=Depends(require_user)):
        return {"operators": eligible(user, contact_id, conversation_id)}

    @router.get("/contacts/{contact_id}/activities")
    def contact_activities(contact_id: int, cursor: str | None = Query(None, max_length=1600),
                           limit: int = Query(30, ge=1, le=50), user=Depends(require_user)):
        return _page_alias(service(user).list_activities({"contact_id": contact_id, "cursor": cursor, "limit": limit}), "activities")

    @router.get("/contacts/{contact_id}/commercial-preference")
    def read_preference(contact_id: int, user=Depends(require_user)):
        return get_commercial_contact_preference(user["tenant_id"], contact_id, user, preference_authorizer(user))

    @router.post("/contacts/{contact_id}/commercial-preference")
    def preference(contact_id: int, payload: CommercialPreferenceRequest, user=Depends(require_user)):
        return set_commercial_contact_preference(
            user["tenant_id"], contact_id, user, active=payload.active,
            expected_version=payload.version, operation_id=payload.operation_id,
            patient_request_confirmed=payload.patient_request_confirmed,
            authorize=preference_authorizer(user),
        )

    @router.get("/contacts/{contact_id}/context")
    def context(contact_id: int, conversation_id: str | None = None,
                user=Depends(require_user)):
        authorize = build_authorizer(user["tenant_id"], require_contact_access)
        source = authorize(contact_id, conversation_id, user)
        rows = []
        if conversation_id:
            rows = [source["conversation"]]
        else:
            # Leitura limitada por contato; nao materializa nem assume thread.
            query = (tenant_collection(user["tenant_id"], "wa_conversations")
                     .where("contact_id", "==", contact_id).order_by("__name__").limit(30))
            for snap in query.stream():
                try:
                    row = authorize(contact_id, snap.id, user)["conversation"]
                except HTTPException as exc:
                    if exc.status_code in (403, 404, 503):  # 503 = checagem indisponivel: pula o candidato
                        continue
                    raise
                rows.append(row)
        return {"contact": source["contact"], "conversations": rows}

    @router.get("/contacts/{contact_id}/messages")
    def messages(contact_id: int, conversation_id: str,
                 limit: int = Query(30, ge=1, le=50), user=Depends(require_user)):
        build_authorizer(user["tenant_id"], require_contact_access)(contact_id, conversation_id, user)
        rows = get_wa_conversation(contact_id, limit=limit, conversation_id=conversation_id)
        if not can_see_all_tenant(user):
            rows = [row for row in rows if not row.get("admin_only") and not row.get("is_backup")
                    and row.get("visibility") != "admin_only"]
        return {"messages": rows}

    return router
