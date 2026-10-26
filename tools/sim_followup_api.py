# -*- coding: utf-8 -*-
"""Integracao REST real do follow-up, sem ADC, rede ou banco externo.

Factory, autorizador, RBAC, service e repository sao reais. Apenas acesso ao
Firestore/autenticacao externa sao substituidos pelas fixtures locais.
"""

import copy
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import tools.sim_followup_flow as fake
import followup_access as access
import followup_routes as routes
import rbac
from followup_service import FollowupService
from firestore_common import get_tenant_context, reset_tenant_context, set_tenant_context


SESSION = {"user": copy.deepcopy(fake.ALICE), "context": fake.TENANT}
PROFILES = {}
CHANNELS = {
    4: {"tenant_id": fake.TENANT, "channel_type": "standard"},
    6: {"tenant_id": fake.TENANT, "channel_type": "coexistence"},
    7: {"tenant_id": fake.TENANT, "channel_type": "standard"},
    8: {"tenant_id": "other_tenant", "channel_type": "standard"},
}
CHECKS = 0


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(label)
    print("  OK " + label)


def raw(name, doc_id):
    return copy.deepcopy(fake.DATA.get((get_tenant_context(), name, str(doc_id))))


def require_contact_access(contact, user):
    if rbac.can_see_all_tenant(user):
        return
    if contact.get("assigned_to") == user.get("id") or not contact.get("assigned_to_uid"):
        return
    for (tenant, name, _), row in fake.DATA.items():
        if (tenant == get_tenant_context() and name == "wa_conversations"
                and row.get("contact_id") == contact.get("id")
                and row.get("assigned_to_uid") == user.get("firebase_uid")):
            return
    raise HTTPException(403, "Contato fora do escopo")


def messages(contact_id, limit, conversation_id):
    rows = [copy.deepcopy(row) for (tenant, name, _), row in fake.DATA.items()
            if tenant == get_tenant_context() and name == "wa_messages"
            and row.get("contact_id") == contact_id and row.get("conversation_id") == conversation_id]
    return sorted(rows, key=lambda row: row["timestamp_wa"], reverse=True)[:limit]


def enriched_contact(contact_id):
    contact = raw("wa_contacts", contact_id)
    if contact is not None and not contact.get("assigned_to_uid"):
        owner = raw("users", contact.get("assigned_to")) or {}
        contact["assigned_to_uid"] = owner.get("firebase_uid", "")
    return contact


access.get_wa_contact = enriched_contact
access.get_wa_conversation_by_id = lambda conversation_id: raw("wa_conversations", conversation_id)
access.get_channel = lambda channel_id: copy.deepcopy(fake.DATA.get(("__global__", "channels", str(channel_id))))
fake.repository_module.global_document = lambda name, doc_id: fake.Reference("__global__", name, doc_id)
routes.get_user_raw_by_id = lambda user_id: raw("users", user_id)
routes.get_wa_conversation = messages
routes.tenant_collection = fake.repository_module.tenant_collection
routes.FollowupService = lambda repo, user, authorize, **kwargs: FollowupService(
    repo, user, authorize, clock=lambda: fake.NOW[0], **kwargs)
rbac._read_perfil_doc = lambda tenant_id, profile_id: copy.deepcopy(PROFILES.get(profile_id))
rbac.invalidate_perfil_cache()


def current_user():
    return copy.deepcopy(SESSION["user"])


app = FastAPI()


@app.middleware("http")
async def tenant_middleware(request, call_next):
    token = set_tenant_context(SESSION["context"])
    try:
        return await call_next(request)
    finally:
        reset_tenant_context(token)


app.include_router(routes.create_followup_router(current_user, require_contact_access))


def session(user=None, context=None):
    SESSION["user"] = copy.deepcopy(user or fake.ALICE)
    SESSION["context"] = fake.TENANT if context is None else context
    rbac.invalidate_perfil_cache()


def request(client, method, path, status=200, body=None, label="request"):
    response = client.request(method, "/api/followup" + path, json=body)
    check(response.status_code == status,
          "%s (HTTP %s esperado %s): %s" % (label, response.status_code, status, response.text[:140] if response.status_code != status else "ok"))
    return response.json()


def seed():
    fake.DATA.clear()
    fake.WRITES.clear()
    fake.QUERY_LIMITS.clear()
    for channel_id, channel in CHANNELS.items():
        fake.put("channels", channel_id, {**channel, "id": channel_id}, tenant="__global__")
    for user in (fake.ALICE, fake.BOB, fake.MANAGER):
        fake.put("users", user["id"], {**user, "is_active": 1, "display_name": "Operador sintético %d" % user["id"]})
    fake.put("wa_contacts", 10, {"id": 10, "assigned_to": None, "assigned_to_uid": "", "display_name": "Paciente sintético", "bot_completed": False})
    fake.put("wa_contacts", 20, {"id": 20, "assigned_to": 2, "assigned_to_uid": "bob", "display_name": "Contato de colega"})
    fake.put("wa_contacts", 30, {"id": 30, "assigned_to": None, "assigned_to_uid": "", "is_backup": True})
    fake.put("wa_contacts", 40, {"id": 40, "assigned_to": 1, "display_name": "Contato legado sintético"})
    convs = {
        "4__synthetic": {"contact_id": 10, "channel_id": 4, "channel_type": "standard", "assigned_to": None, "assigned_to_uid": ""},
        "5__private": {"contact_id": 10, "channel_id": 5, "channel_type": "coexistence", "assigned_to": 2, "assigned_to_uid": "bob"},
        "6__orphan": {"contact_id": 10, "channel_id": 6, "assigned_to": None, "assigned_to_uid": ""},
        "7__legacy": {"contact_id": 10, "channel_id": 7, "assigned_to": None, "assigned_to_uid": ""},
        "8__foreign": {"contact_id": 10, "channel_id": 8, "assigned_to": None, "assigned_to_uid": ""},
        "9__unknown": {"contact_id": 10, "channel_id": 9, "assigned_to": None, "assigned_to_uid": ""},
        "6__stale-standard": {"contact_id": 10, "channel_id": 6, "channel_type": "standard", "assigned_to": None, "assigned_to_uid": ""},
        "7__stale-coex": {"contact_id": 10, "channel_id": 7, "source_channel_type": "coexistence", "assigned_to": None, "assigned_to_uid": ""},
        "4__mine": {"contact_id": 20, "channel_id": 4, "channel_type": "standard", "assigned_to": 1, "assigned_to_uid": "alice"},
        "4__backup": {"contact_id": 30, "channel_id": 4, "channel_type": "standard", "assigned_to_uid": "", "is_backup": True},
    }
    for doc_id, row in convs.items():
        fake.put("wa_conversations", doc_id, {**row, "id": doc_id, "attendance_status": "fechado_manual"})
    fake.put("wa_contacts", 99, {"id": 99, "assigned_to_uid": "", "display_name": "Outro tenant"}, tenant="other_tenant")
    for msg_id, extras in (("normal", {}), ("admin", {"visibility": "admin_only"}),
                           ("backup", {"is_backup": True}), ("flag-admin", {"admin_only": True})):
        fake.put("wa_messages", msg_id, {"id": msg_id, "contact_id": 10, "conversation_id": "4__synthetic",
                                       "direction": "inbound", "msg_type": "text", "timestamp_wa": fake.NOW[0] - timedelta(hours=1),
                                       "content": "Mensagem sintética", "status": "received", **extras})


def run():
    print("Follow-up API: factory, RBAC, acesso, service e repository reais")
    seed()
    with TestClient(app) as client:
        routes.FEATURE_FOLLOWUP = False
        request(client, "GET", "/settings", 404, label="flag desligada nega API")
        routes.FEATURE_FOLLOWUP = True
        # Chave por tenant (2026-10-26): alem da flag geral, settings.followup_enabled=True no doc do tenant.
        import tenant_service as _ts
        _ts.get_tenant = lambda tid: {"id": tid, "settings": {}}
        session()
        request(client, "GET", "/settings", 404, label="tenant sem a chave do follow-up nao ve a API (flag geral ligada)")
        check(routes.tenant_followup_enabled(fake.TENANT, {"settings": {"followup_enabled": "sim"}}) is False,
              "chave do tenant so vale com True explicito")
        routes.FEATURE_FOLLOWUP = False
        check(routes.tenant_followup_enabled(fake.TENANT, {"settings": {"followup_enabled": True}}) is False,
              "flag geral desligada vence a chave do tenant")
        routes.FEATURE_FOLLOWUP = True
        _ts.get_tenant = lambda tid: {"id": tid, "settings": {"followup_enabled": tid == fake.TENANT}}
        session({**fake.ALICE, "tenant_id": ""})
        request(client, "GET", "/settings", 403, label="sessao sem tenant negada")
        session(context="other_tenant")
        request(client, "GET", "/settings", 403, label="contexto divergente negado")
        session()
        fake.DATA[(fake.TENANT, "users", "1")]["is_active"] = 0
        request(client, "GET", "/settings", 403, label="usuario desativado revogado")
        fake.DATA[(fake.TENANT, "users", "1")]["is_active"] = 1
        fake.DATA[(fake.TENANT, "users", "1")]["firebase_uid"] = "changed"
        request(client, "GET", "/settings", 403, label="uid trocado revoga sessao")
        fake.DATA[(fake.TENANT, "users", "1")]["firebase_uid"] = "alice"
        session({**fake.ALICE, "read_only": True})
        request(client, "GET", "/settings", 403, label="read_only nao ganha permissoes")
        session({**fake.ALICE, "impersonating": True})
        request(client, "POST", "/tasks", 403, body={}, label="impersonacao nao cria Task")
        session()
        request(client, "GET", "/contacts/10/context?conversation_id=5__private", 403, label="thread coex privada de colega nao abre pelo contato pool")
        request(client, "GET", "/contacts/10/context?conversation_id=6__orphan", 403, label="coex legada sem tipo nao vira standard por default")
        request(client, "GET", "/contacts/10/context?conversation_id=7__legacy", label="standard legada resolve canal real")
        request(client, "GET", "/contacts/10/context?conversation_id=6__stale-standard", 403, label="canal vivo coex prevalece sobre tipo standard antigo")
        request(client, "GET", "/contacts/10/context?conversation_id=7__stale-coex", label="canal vivo standard prevalece sobre source herdado")
        request(client, "GET", "/contacts/10/context?conversation_id=8__foreign", 403, label="canal de outro tenant nao libera thread")
        request(client, "GET", "/contacts/10/context?conversation_id=9__unknown", 403, label="canal desconhecido nao vira pool")
        request(client, "GET", "/contacts/10/context?conversation_id=bad%2Fpath", 422, label="path invalido rejeitado antes do banco")
        request(client, "GET", "/contacts/30/context", 403, label="backup nao vaza pela pool")
        request(client, "GET", "/contacts/99/context", 404, label="contato de outro tenant nao resolvido")
        request(client, "GET", "/contacts/20/context?conversation_id=4__mine", label="thread propria permite contexto sem mover owner do lead")
        context_before = copy.deepcopy(fake.DATA)
        writes_before = len(fake.WRITES)
        context = request(client, "GET", "/contacts/10/context", label="contexto somente leitura com threads autorizadas")
        check({row["id"] for row in context["conversations"]} == {"4__synthetic", "7__legacy", "7__stale-coex"}, "contexto geral filtra threads privadas/desconhecidas")
        rows = request(client, "GET", "/contacts/10/messages?conversation_id=4__synthetic", label="historico autorizado somente leitura")["messages"]
        check([row["id"] for row in rows] == ["normal"], "rating/admin_only/backup nao vazam ao operador")
        request(client, "GET", "/contacts/10/messages?conversation_id=5__private", 403, label="historico privado nega antes da query")
        check(fake.DATA == context_before and len(fake.WRITES) == writes_before, "GET contexto/mensagens nao cria ou assume atendimento")
        request(client, "PUT", "/settings", 403, body={"version": 0}, label="operador sem configuracao nao salva")
        # Perfil permite horarios sem ver toda agenda/redistribuir; limites sao independentes.
        profile_user = {**fake.MANAGER, "role": "supervisor", "perfil_acesso_id": "settings_only"}
        fake.put("users", 3, {**profile_user, "is_active": 1})
        PROFILES["settings_only"] = {"toggles": {"gerenciar_followup": True, "gerenciar_horarios_followup": True,
                                                 "ver_todos_leads": False, "redistribuir_followup": False}}
        session(profile_user)
        settings = request(client, "PUT", "/settings", body={"version": 0, "contact_hours": {str(day): [["08:00", "18:00"]] for day in range(5)}}, label="horarios permitidos sem gestao de tarefas")["settings"]
        check(settings["version"] == 1 and settings["configured"], "settings schema coincide com UI")
        request(client, "GET", "/tasks?scope=team", 403, label="permissao horarios nao amplia agenda")
        request(client, "PUT", "/settings", 409, body={"version": 0}, label="versao settings stale mapeia 409")
        session()
        body = {"operation_id": "api-create-task-1", "contact_id": 10, "conversation_id": "4__synthetic",
                "type": "retorno", "title": "Retorno sintético", "due_at": (fake.NOW[0] + timedelta(hours=1)).isoformat(), "queue_key": "reception"}
        created = request(client, "POST", "/tasks", body=body, label="POST cria Task manual")["task"]
        legacy = request(client, "POST", "/tasks", body={**body, "operation_id": "api-legacy-contact", "contact_id": 40, "conversation_id": None}, label="guard aceita UID legado derivado sem backfill")["task"]
        check(legacy["contact_id"] == 40 and "assigned_to_uid" not in fake.DATA[(fake.TENANT, "wa_contacts", "40")], "normalizacao legado nao reescreve contato")
        replay = request(client, "POST", "/tasks", body=body, label="retry POST idempotente")
        check(replay["replayed"] and replay["task"]["id"] == created["id"], "retry retorna mesma Task sem duplicacao")
        detail = request(client, "GET", "/tasks/" + created["id"], label="detalhe contrato task e elegiveis")
        check(detail["task"]["can_modify"] and [row["id"] for row in detail["eligible_assignees"]] == [1], "elegiveis filtrados para operador")
        page = request(client, "GET", "/tasks?contact_id=10&status=pending&group=all&limit=1", label="proxima acao independe de assignee")
        check(page["items"][0]["id"] == created["id"] and page["tasks"] == page["items"], "alias items preserva contrato")
        request(client, "GET", "/tasks?scope=contact", 422, label="scope contact sem id negado")
        request(client, "GET", "/tasks?cursor=forged", 400, label="cursor invalido retorna 400")
        taken = request(client, "POST", "/tasks/" + created["id"] + "/actions", body={"action": "take", "operation_id": "api-take-1", "version": 1}, label="action pega sem alterar lead")["task"]
        request(client, "POST", "/tasks/" + created["id"] + "/actions", 409, body={"action": "cancel", "operation_id": "api-stale-cancel", "version": 1, "reason": "other"}, label="versao stale mapeia 409")
        original_manager = copy.deepcopy(fake.DATA[(fake.TENANT, "users", "3")])
        original_bob = copy.deepcopy(fake.DATA[(fake.TENANT, "users", "2")])
        fake.put("users", 3, {**fake.MANAGER, "is_active": 1})
        fake.put("users", 2, {**fake.BOB, "is_active": 1, "perfil_acesso_id": "followup_disabled"})
        PROFILES["followup_disabled"] = {"toggles": {"gerenciar_followup": False}}
        session(fake.MANAGER)
        writes_before = len(fake.WRITES)
        request(client, "POST", "/tasks/" + created["id"] + "/actions", 403,
                body={"action": "assign", "operation_id": "api-target-disabled", "version": taken["version"], "assignee_user_id": 2},
                label="destinatario com followup desligado negado mesmo por ID direto")
        check(len(fake.WRITES) == writes_before, "destinatario sem permissao nao recebe Task ou Activity")
        fake.DATA[(fake.TENANT, "users", "3")] = original_manager
        fake.DATA[(fake.TENANT, "users", "2")] = original_bob
        session(fake.BOB)
        readonly = request(client, "GET", "/tasks/" + created["id"], label="Task da colega acessivel no contexto pool")["task"]
        check(not readonly["can_modify"], "colega le mas nao recebe autoridade sobre Task")
        request(client, "POST", "/tasks/" + created["id"] + "/actions", 403, body={"action": "cancel", "operation_id": "api-bob-cancel", "version": taken["version"], "reason": "other"}, label="colega nao altera Task alheia")
        session()
        history = request(client, "GET", "/tasks/" + created["id"] + "/activities", label="historico paginado contrato")
        check({row["event_type"] for row in history["items"]} == {"task_created", "task_taken"}, "historico contem somente fatos humanos")
        context_doc = fake.DATA[(fake.TENANT, "wa_contacts", "10")]
        context_doc["assigned_to"], context_doc["assigned_to_uid"] = 2, "bob"
        request(client, "GET", "/tasks/" + created["id"], 403, label="transferencia revoga acesso mesmo para criadora/assignee")
        context_doc["assigned_to"], context_doc["assigned_to_uid"] = None, ""
        check(fake.DATA[(fake.TENANT, "wa_conversations", "4__synthetic")]["attendance_status"] == "fechado_manual", "Task nao reabriu atendimento")
        check(all(name in ("system_settings", "crm_tasks", "crm_activities") for _, name, _ in fake.WRITES), "rotas F1 nao gravam mensagens, owners, bot ou budgets")
        request(client, "POST", "/suggestion", body={"type": "lembrete_consulta", "appointment_at": "2026-10-26T13:00:00-03:00"}, label="preview calendario somente leitura")
    print("\n%d verificacoes REST passaram; nenhum ADC/rede/banco externo." % CHECKS)


if __name__ == "__main__":
    run()
