# -*- coding: utf-8 -*-
"""API de configuracao do lembrete; independente do save geral de Sistema."""

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from google.cloud import firestore
from starlette.concurrency import run_in_threadpool

from bot_reminders import DEFAULTS, KEYS, available, clean_settings
from firestore_common import document, get_firestore_client


def version(settings):
    return hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_config():
    if not available():
        raise HTTPException(404, "Recurso indisponível.")
    data = document("system_settings", "chat").get().to_dict() or {}
    cfg = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    from tenant_service import get_tenant
    from firestore_common import get_tenant_context
    from bot_reminders import tenant_mode
    return {"settings": cfg, "version": version(cfg),
            "simulation": tenant_mode(get_tenant(get_tenant_context())) == "dry_run"}


@firestore.transactional
def _save(transaction, ref, body):
    data = ref.get(transaction=transaction).to_dict() or {}
    current = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    if body.get("version") != version(current):
        raise HTTPException(409, "A configuração mudou. Reabra a tela antes de salvar.")
    supplied = body.get("settings")
    if not isinstance(supplied, dict):
        raise HTTPException(422, "Configuração inválida.")
    # Geracao e exclusiva do servidor, mesmo com body forjado.
    supplied = {key: value for key, value in supplied.items() if key in KEYS and key != "bot_reminder_generation"}
    try:
        cfg = clean_settings(supplied, current)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    if cfg["bot_reminder_enabled"] != current["bot_reminder_enabled"] or not cfg["bot_reminder_generation"]:
        cfg["bot_reminder_generation"] = uuid.uuid4().hex
    transaction.set(ref, cfg, merge=True)
    return cfg


def save_config(body, user_id=None):
    if not available():
        raise HTTPException(404, "Recurso indisponível.")
    if not isinstance(body, dict):
        raise HTTPException(422, "Configuração inválida.")
    cfg = _save(get_firestore_client().transaction(), document("system_settings", "chat"), body)
    from database_firestore import log_audit
    log_audit(user_id, "BOT_REMINDER_SETTINGS_UPDATE", "enabled=%s caracteres=%s lgpd=%s" % (
        cfg["bot_reminder_enabled"], ",".join(str(len(cfg[f"bot_reminder_text_{i}"])) for i in range(1, 4)),
        ",".join(str(len(cfg[f"bot_reminder_lgpd_text_{i}"])) for i in range(1, 4))))
    return read_config()


def create_router(get_current_user, verify_cron_auth):
    from rbac import ensure_permission
    from bot_reminders import run_tick
    router = APIRouter()

    @router.get("/api/settings/bot-reminders")
    async def get_reminders(user=Depends(get_current_user)):
        await run_in_threadpool(ensure_permission, user, "gerenciar_config_sistema")
        return await run_in_threadpool(read_config)

    @router.put("/api/settings/bot-reminders")
    async def put_reminders(request: Request, user=Depends(get_current_user)):
        await run_in_threadpool(ensure_permission, user, "gerenciar_config_sistema")
        body = await request.json()
        return await run_in_threadpool(save_config, body, user.get("id"))

    @router.post("/api/internal/cron/bot-reminders")
    async def cron_reminders(request: Request):
        await run_in_threadpool(verify_cron_auth, request)
        return await run_in_threadpool(run_tick)

    return router
