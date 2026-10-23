# -*- coding: utf-8 -*-
"""Exercita service e repository reais com Firestore local em memoria.

Sem ADC, rede, agente CX ou WhatsApp. Fake existe somente neste simulador.
"""

import copy
import functools
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
import followup_repository as repository_module
from followup_repository import FollowupRepository
from followup_service import FollowupService


DATA = {}
QUERY_LIMITS = []
WRITES = []
BEFORE_TRANSACTION = None
NOW = [datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)]  # segunda, 09h local
CHECKS = 0


class Snapshot:
    def __init__(self, reference, value):
        self.reference = reference
        self.id = reference.id
        self.exists = value is not None
        self.value = copy.deepcopy(value)

    def to_dict(self):
        return copy.deepcopy(self.value)


class Reference:
    def __init__(self, tenant, collection, doc_id):
        self.key = (tenant, collection, str(doc_id))
        self.id = str(doc_id)

    def get(self, transaction=None):
        if transaction and transaction.writes:
            raise AssertionError("Firestore nao permite leitura depois de escrita")
        return Snapshot(self, (transaction.view if transaction else DATA).get(self.key))


class Query:
    def __init__(self, tenant, name):
        self.tenant, self.name = tenant, name
        self.filters, self.orders = [], []
        self.cap, self.after = None, None

    def where(self, key, operator, value):
        q = copy.copy(self)
        q.filters = self.filters + [(key, operator, value)]
        return q

    def order_by(self, key, direction=None):
        q = copy.copy(self)
        q.orders = self.orders + [(key, direction == "DESCENDING")]
        return q

    def limit(self, value):
        q = copy.copy(self)
        q.cap = value
        return q

    def start_after(self, value):
        q = copy.copy(self)
        q.after = value
        return q

    def stream(self):
        assert self.cap is not None, "Query sem limite"
        QUERY_LIMITS.append((self.name, self.cap))
        rows = []
        for (tenant, name, doc_id), value in DATA.items():
            if tenant != self.tenant or name != self.name:
                continue
            matches = True
            for field, operator, expected in self.filters:
                actual = value.get(field)
                if actual is None or not {"==": lambda: actual == expected, ">": lambda: actual > expected,
                                          ">=": lambda: actual >= expected, "<": lambda: actual < expected}[operator]():
                    matches = False
                    break
            if matches and all(key == "__name__" or value.get(key) is not None for key, _ in self.orders):
                rows.append((doc_id, value))
        for key, descending in reversed(self.orders):
            rows.sort(key=lambda row: row[0] if key == "__name__" else row[1][key], reverse=descending)
        if self.after:
            def beyond(row):
                for field, descending in self.orders:
                    actual = row[0] if field == "__name__" else row[1][field]
                    expected = self.after[field]
                    if isinstance(expected, Reference):
                        expected = expected.id
                    if actual != expected:
                        return actual < expected if descending else actual > expected
                return False
            rows = [row for row in rows if beyond(row)]
        return iter(Snapshot(Reference(self.tenant, self.name, doc_id), value) for doc_id, value in rows[:self.cap])


def firestore_compat(value, path="doc", in_array=False):
    """Restricoes do Firestore real que o fake em memoria nao tinha (o PUT de
    horarios deu 500 em staging, 2026-10-18): lista dentro de lista ("invalid
    nested entity"), tipo sem conversao (date sem hora, Decimal, objeto) e
    chave de mapa vazia ou nao-texto."""
    if value is None or isinstance(value, (bool, int, float, str, bytes, datetime)):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise AssertionError("Firestore: chave invalida em %s: %r" % (path, key))
            firestore_compat(item, "%s.%s" % (path, key))
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        if in_array:
            raise AssertionError("Firestore: lista dentro de lista em %s" % path)
        for index, item in enumerate(value):
            firestore_compat(item, "%s[%d]" % (path, index), in_array=True)
        return
    raise AssertionError("Firestore: tipo %s nao gravavel em %s" % (type(value).__name__, path))


class Transaction:
    def __init__(self):
        self.view = {}
        self.writes = []

    def set(self, reference, value):
        firestore_compat(value, "/".join(reference.key))
        self.writes.append((reference.key, copy.deepcopy(value), False))

    def create(self, reference, value):
        firestore_compat(value, "/".join(reference.key))
        self.writes.append((reference.key, copy.deepcopy(value), True))


def transactional(fn):
    @functools.wraps(fn)
    def wrapped(transaction):
        global BEFORE_TRANSACTION
        if BEFORE_TRANSACTION:
            callback, BEFORE_TRANSACTION = BEFORE_TRANSACTION, None
            callback()
        transaction.view = copy.deepcopy(DATA)
        result = fn(transaction)
        next_data = copy.deepcopy(DATA)
        for key, value, create in transaction.writes:
            if create and key in next_data:
                raise AssertionError("create duplicado")
            next_data[key] = value
        DATA.clear()
        DATA.update(next_data)
        WRITES.extend(key for key, _, _ in transaction.writes)
        return result
    return wrapped


repository_module.tenant_document = lambda tenant, name, doc_id: Reference(tenant, name, doc_id)
repository_module.tenant_collection = lambda tenant, name: Query(tenant, name)
repository_module.get_firestore_client = lambda: SimpleNamespace(transaction=Transaction)
repository_module.firestore = SimpleNamespace(transactional=transactional)

TENANT = "clinic_test"
ALICE = {"id": 1, "firebase_uid": "alice", "tenant_id": TENANT, "role": "operador"}
BOB = {"id": 2, "firebase_uid": "bob", "tenant_id": TENANT, "role": "operador"}
MANAGER = {"id": 3, "firebase_uid": "manager", "tenant_id": TENANT, "role": "admin"}


def put(name, doc_id, value, tenant=TENANT):
    DATA[(tenant, name, str(doc_id))] = copy.deepcopy(value)


def authorize(contact_id, conversation_id, user):
    contact = DATA.get((TENANT, "wa_contacts", str(contact_id)))
    if not contact:
        raise HTTPException(404, "Contato inexistente")
    if user.get("role") != "admin" and contact.get("assigned_to_uid") not in ("", None, user["firebase_uid"]):
        raise HTTPException(403, "Sem acesso ao contato")
    conversation = None
    if conversation_id:
        conversation = DATA.get((TENANT, "wa_conversations", str(conversation_id)))
        if not conversation or conversation.get("contact_id") != contact_id:
            raise HTTPException(403, "Thread invalida")
        if user.get("role") != "admin" and conversation.get("assigned_to_uid") not in ("", None, user["firebase_uid"]):
            raise HTTPException(403, "Sem acesso a thread")
    return {"contact": copy.deepcopy(contact), "conversation": copy.deepcopy(conversation)}


def service(user=ALICE, manager=False):
    return FollowupService(FollowupRepository(TENANT), user, authorize,
                          can_manage=manager, clock=lambda: NOW[0])


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(label)
    print("  OK " + label)


def expect(status, callback, label):
    try:
        callback()
    except HTTPException as exc:
        check(exc.status_code == status, label + " (HTTP %d)" % exc.status_code)
    else:
        raise AssertionError(label + " nao falhou")


def create(op, **changes):
    payload = {"operation_id": op, "contact_id": 10, "conversation_id": "4__synthetic",
               "type": "retorno", "title": "Retorno combinado", "description": "Contexto comercial mínimo",
               "due_at": NOW[0] + timedelta(hours=2), "queue_key": "reception"}
    payload.update(changes)
    return service().create_task(payload), payload


def action(svc, task, action_name, op, **changes):
    return svc.task_action(task["id"], {"action": action_name, "operation_id": op, "version": task["version"], **changes})


def run():
    global BEFORE_TRANSACTION
    print("Follow-up F1: service/repository reais, Firestore fake local")
    for user in (ALICE, BOB, MANAGER):
        put("users", user["id"], {**user, "is_active": 1})
    put("wa_contacts", 10, {"id": 10, "assigned_to": None, "assigned_to_uid": "", "bot_completed": False,
                            "qualification": "novo", "lead_temperature": "quente", "display_name": "Paciente sintético"})
    put("wa_conversations", "4__synthetic", {"id": "4__synthetic", "contact_id": 10, "channel_id": 4,
                                            "assigned_to": None, "assigned_to_uid": "", "attendance_status": "fechado_manual"})
    original_contact = copy.deepcopy(DATA[(TENANT, "wa_contacts", "10")])
    original_conv = copy.deepcopy(DATA[(TENANT, "wa_conversations", "4__synthetic")])
    expect(403, lambda: FollowupRepository(""), "tenant obrigatorio")
    expect(403, lambda: FollowupService(FollowupRepository(TENANT), {**ALICE, "tenant_id": "other"}, authorize), "sessao de outro tenant negada")
    expect(403, lambda: service({**ALICE, "read_only": True}, True).get_settings(), "service tambem nega sessao read_only mesmo com can_manage")
    expect(409, lambda: create("no-calendar"), "sem horarios nao inventa expediente")
    manager = service(MANAGER, True)
    settings = {"version": 0, "contact_hours": {str(day): [["08:00", "12:00"], ["13:00", "18:00"]] for day in range(5)}}
    configured = manager.save_settings(settings)["settings"]
    check(configured["configured"] and configured["version"] == 1, "configuracao explicita salva")
    stored = DATA[(TENANT, "system_settings", "followup")]["contact_hours"]
    check(stored["0"] == [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "18:00"}],
          "faixas gravadas como mapas (Firestore recusa lista dentro de lista)")
    check(manager.get_settings()["settings"]["contact_hours"]["0"] == [["08:00", "12:00"], ["13:00", "18:00"]],
          "leitura devolve faixas no contrato [inicio, fim]")
    expect(403, lambda: service().save_settings(settings), "operador nao altera horarios")
    expect(409, lambda: manager.save_settings(settings), "configuracao concorrente nao sobrescreve")
    expect(422, lambda: manager.save_settings({"version": 1, "contact_hours": {"0": [["10:00", "09:00"]]}}), "intervalo invalido recusado")
    expect(422, lambda: manager.save_settings({"version": 1, "contact_hours": {"5": [["08:00", "18:00"]]}}), "fim de semana preservado")
    expect(422, lambda: create("no-offset", due_at="2026-10-20T10:00:00"), "prazo exige fuso")
    expect(422, lambda: create("weekend", due_at="2026-10-24T10:00:00-03:00"), "prazo no sabado nao deslocado silenciosamente")
    result, payload = create("create-1")
    task = result["task"]
    check(task["assignment_mode"] == "queue" and task["version"] == 1, "criacao na fila sem owner")
    check(task["contact"]["lead_temperature"] == "quente", "temperatura existente lida sem copiar para Task")
    check("lead_temperature" not in DATA[(TENANT, "crm_tasks", task["id"])], "sem qualificador paralelo persistido")
    replay = service().create_task(payload)
    check(replay["replayed"] and replay["task"]["id"] == task["id"], "criacao idempotente")
    expect(409, lambda: service().create_task({**payload, "title": "Outra ação"}), "operation_id nao reutilizavel com outro payload")
    task = action(service(), task, "take", "take-1")["task"]
    check(task["assignee_uid"] == "alice", "pegar muda somente Task")
    expect(403, lambda: action(service(BOB), task, "cancel", "bob-cancel", reason="other"), "acesso ao contato nao autoriza tarefa de colega")
    expect(409, lambda: service().task_action(task["id"], {"action": "cancel", "operation_id": "stale", "version": 1, "reason": "other"}), "versao antiga negada")
    before_anchor = task["response_anchor_at"]
    NOW[0] += timedelta(minutes=20)
    put("wa_messages", "reply", {"id": "reply", "contact_id": 10, "conversation_id": "4__synthetic", "direction": "inbound", "msg_type": "text", "timestamp_wa": NOW[0], "status": "received"})
    check(service().get_task(task["id"])["task"]["response_received"], "inbound real posterior sinaliza")
    task = action(service(), task, "reschedule", "postpone-1", due_at=NOW[0] + timedelta(hours=4))["task"]
    check(task["response_anchor_at"] == before_anchor and task["response_received"], "adiar preserva ancora e aviso")
    check(task["assignment_mode"] == "queue", "reagendar devolve fila por padrao")
    NOW[0] += timedelta(minutes=10)
    attempted = action(service(), task, "attempt", "attempt-1", occurred_at=NOW[0], result="not_reached", next_due_at=NOW[0] + timedelta(hours=2))
    task = attempted["task"]
    check(task["attempt_count"] == 1 and task["status"] == "pending", "sem resposta fica na mesma Task")
    check(not task["response_received"] and task["response_anchor_kind"] == "attempt", "nova tentativa avanca ancora real")
    NOW[0] += timedelta(minutes=5)
    put("wa_messages", "old-replay", {"id": "old-replay", "contact_id": 10, "conversation_id": "4__synthetic", "direction": "inbound", "msg_type": "text", "timestamp_wa": before_anchor - timedelta(days=1), "created_at": NOW[0], "status": "received"})
    put("wa_messages", "rating", {"id": "rating", "contact_id": 10, "conversation_id": "4__synthetic", "direction": "inbound", "msg_type": "text", "timestamp_wa": NOW[0], "status": "received", "is_rating_message": True})
    for msg_id, extra in (("legacy-admin", {"admin_only": True}), ("lgpd-control", {"content": "lgpd_aceitar"}), ("future-provider-clock", {"timestamp_wa": NOW[0] + timedelta(days=2)})):
        put("wa_messages", msg_id, {"id": msg_id, "contact_id": 10, "conversation_id": "4__synthetic", "direction": "inbound", "msg_type": "text", "timestamp_wa": NOW[0], "status": "received", **extra})
    check(not service().get_task(task["id"])["task"]["response_received"], "replay antigo e rating nao simulam resposta nova")
    check(not service().get_task(task["id"])["task"]["response_received"], "admin legado, controles LGPD e data futura nao sao resposta")
    put("wa_messages", "genuine", {"id": "genuine", "contact_id": 10, "conversation_id": "4__synthetic", "direction": "inbound", "msg_type": "image", "timestamp_wa": NOW[0], "status": "received"})
    DATA[(TENANT, "wa_messages", "genuine")]["status"] = "read"
    check(service().get_task(task["id"])["task"]["response_received"], "ler a mensagem nao apaga sinal de resposta apos ancora")
    NOW[0] += timedelta(minutes=5)
    old_anchor = task["response_anchor_at"]
    task = action(service(), task, "attempt", "retroactive", occurred_at=before_anchor - timedelta(hours=1), result="not_reached")["task"]
    check(task["response_anchor_at"] == old_anchor and task["response_received"], "registro retroativo nao recua ancora nem usa recorded_at")
    events = service().list_activities({"task_id": task["id"], "limit": 50})["activities"]
    attempts = [event for event in events if event["event_type"] == "task_attempted"]
    check(len(attempts) == 2 and all(event.get("recorded_at") for event in attempts), "tentativas reais permanecem historico com recorded_at")
    check(any(event["occurred_at"] < event["recorded_at"] for event in attempts), "ocorrencia e registro sao distintos")
    check(all("description" not in event["data"] and "content" not in event["data"] for event in events), "historico nao duplica contexto nem mensagens")
    expect(422, lambda: action(service(), task, "attempt", "future", occurred_at=NOW[0] + timedelta(hours=1), result="not_reached"), "tentativa futura negada")
    expect(422, lambda: action(service(), task, "complete", "not-reached-complete", result="not_reached"), "sem resposta nao conclui objetivo continuo")
    task = action(service(), task, "attempt", "third", occurred_at=NOW[0], result="not_reached")["task"]
    check(task["review_required"] and task["status"] == "pending", "tres sem resposta pedem revisao e nao encerram")
    expect(409, lambda: action(service(), task, "attempt", "fourth-no-review", occurred_at=NOW[0], result="not_reached"), "quarta tentativa pede revisao humana")
    task = action(service(), task, "attempt", "fourth", occurred_at=NOW[0], result="not_reached", reviewed_after_three=True)["task"]
    check(task["attempt_count"] == 4, "revisao permite quarta sem limite rigido")
    snapshot = copy.deepcopy(DATA)
    def transfer_during_commit():
        DATA[(TENANT, "wa_contacts", "10")]["assigned_to_uid"] = "bob"
    BEFORE_TRANSACTION = transfer_during_commit
    expect(409, lambda: action(service(), task, "cancel", "race", reason="other"), "transferencia entre autorizacao e commit impede mutacao")
    check(DATA[(TENANT, "crm_tasks", task["id"])]["version"] == task["version"], "conflito atomico nao altera Task")
    expect(403, lambda: service().get_task(task["id"]), "perda de acesso nao tem excecao por autoria")
    DATA.clear()
    DATA.update(snapshot)
    old_settings = copy.deepcopy(DATA[(TENANT, "system_settings", "followup")])
    def calendar_during_commit():
        DATA[(TENANT, "system_settings", "followup")]["version"] += 1
    BEFORE_TRANSACTION = calendar_during_commit
    expect(409, lambda: action(service(), task, "reschedule", "calendar-race", due_at=NOW[0] + timedelta(hours=4)), "calendario alterado antes do commit invalida prazo validado")
    DATA[(TENANT, "system_settings", "followup")] = old_settings
    def preference_during_commit():
        DATA[(TENANT, "wa_contacts", "10")]["commercial_contact_block"] = {"active": True, "version": 1}
    BEFORE_TRANSACTION = preference_during_commit
    expect(409, lambda: action(service(), task, "reschedule", "preference-race", due_at=NOW[0] + timedelta(hours=4)), "recusa registrada entre autorizacao e commit impede retomada")
    del DATA[(TENANT, "wa_contacts", "10")]["commercial_contact_block"]
    def role_during_commit():
        DATA[(TENANT, "users", "1")]["role"] = "supervisor"
    BEFORE_TRANSACTION = role_during_commit
    expect(409, lambda: action(service(), task, "cancel", "role-race", reason="other"), "perfil alterado durante transacao impede mutacao")
    DATA[(TENANT, "users", "1")]["role"] = "operador"
    inactive = {**BOB, "is_active": 0}
    put("users", 2, inactive)
    expect(422, lambda: action(manager, task, "assign", "inactive", assignee_user_id=2), "destinatario inativo recusado")
    put("users", 2, {**BOB, "is_active": 1})
    DATA[(TENANT, "wa_contacts", "10")]["assigned_to_uid"] = "alice"
    expect(403, lambda: action(manager, task, "assign", "wrong-scope", assignee_user_id=2), "gestao nao concede acesso ao destinatario por atribuir")
    DATA[(TENANT, "wa_contacts", "10")]["assigned_to_uid"] = ""
    DATA[(TENANT, "wa_contacts", "10")]["commercial_contact_block"] = {"active": True, "version": 1}
    expect(409, lambda: create("blocked-commercial"), "recusa geral bloqueia novo comercial")
    expect(409, lambda: action(service(), task, "attempt", "blocked-attempt", occurred_at=NOW[0], result="not_reached", reviewed_after_three=True), "recusa bloqueia tentativa comercial existente")
    check(service().get_task(task["id"])["task"]["commercial_blocked"], "recusa preserva historico visivel")
    cancelled = action(service(), task, "refuse_specific", "cancel-specific")["task"]
    check(cancelled["status"] == "cancelled", "cancelamento especifico permanece permitido")
    check(DATA[(TENANT, "wa_contacts", "10")]["commercial_contact_block"]["active"], "cancelamento nao limpa recusa global")
    internal, _ = create("internal", type="internal", due_at="2026-10-24T11:00:00-03:00")
    check(internal["task"]["status"] == "pending", "tarefa interna independente preservada")
    del DATA[(TENANT, "wa_contacts", "10")]["commercial_contact_block"]
    confirmation, _ = create("confirmation", type="confirmacao_consulta", appointment_at="2026-10-20T14:00:00-03:00", appointment_ref="synthetic-appointment")
    reminder, _ = create("reminder", type="lembrete_consulta", appointment_at="2026-10-20T14:00:00-03:00", appointment_ref="synthetic-appointment")
    confirmation, reminder = confirmation["task"], reminder["task"]
    pair_payload = {"occurred_at": NOW[0], "result": "action_done", "complete": True,
                    "shared_task_ids": [reminder["id"]], "shared_task_versions": {reminder["id"]: 999},
                    "shared_actions_confirmed": True}
    expect(409, lambda: action(service(), confirmation, "attempt", "shared-stale", **pair_payload), "outra versao invalida impede contato compartilhado")
    check(DATA[(TENANT, "crm_tasks", confirmation["id"])]["version"] == 1, "par invalido nao conclui primeira Task")
    pair_payload["shared_task_versions"][reminder["id"]] = reminder["version"]
    pair_result = action(service(), confirmation, "attempt", "shared", **pair_payload)
    check(pair_result["task"]["status"] == "completed" and DATA[(TENANT, "crm_tasks", reminder["id"])]["status"] == "completed", "um contato conclui ambas somente com confirmacao explicita")
    pair_events = [row for (_, name, _), row in DATA.items() if name == "crm_activities" and row.get("event_type") == "task_attempted" and row.get("task_id") in (confirmation["id"], reminder["id"])]
    check(len(pair_events) == 1, "par possui exatamente um evento de tentativa real originadora")
    other_completion = [row for (_, name, _), row in DATA.items() if name == "crm_activities" and row.get("event_type") == "task_completed" and row.get("task_id") == reminder["id"]][0]
    check(other_completion["data"]["attempt_id"] == pair_events[0]["data"]["attempt_id"] and other_completion["data"]["origin_task_id"] == confirmation["id"], "segunda conclusao referencia fato sem duplicar tentativa")
    check(DATA[(TENANT, "crm_tasks", reminder["id"])]["attempt_count"] == 0, "cache da segunda Task nao inventa tentativa adicional")
    shared_replay = action(service(), confirmation, "attempt", "shared", **pair_payload)
    check(shared_replay["replayed"] and shared_replay["task"]["attempt_count"] == 1, "retry compartilhado nao duplica tentativa")
    first, _ = create("preserve-future-confirm", type="confirmacao_consulta", appointment_at="2026-10-20T14:00:00-03:00", appointment_ref="future-appointment")
    second, _ = create("preserve-future-remind", type="lembrete_consulta", appointment_at="2026-10-20T14:00:00-03:00", appointment_ref="future-appointment", due_at=NOW[0] + timedelta(hours=5))
    expect(422, lambda: action(service(), first["task"], "attempt", "future-reminder", occurred_at=NOW[0], result="action_done", complete=True, shared_task_ids=[second["task"]["id"]], shared_task_versions={second["task"]["id"]: 1}, shared_actions_confirmed=True), "lembrete em prazo distinto ainda futuro nao e concluido")
    expect(422, lambda: action(service(), second["task"], "reschedule", "after-appointment", due_at="2026-10-20T15:00:00-03:00"), "reagendamento nao ultrapassa horario do compromisso")
    before_due = second["task"]["due_at"]
    corrected = action(service(), second["task"], "update", "correct-appointment", appointment_at="2026-10-21T14:00:00-03:00", appointment_ref="rescheduled-appointment")["task"]
    check(corrected["appointment_ref"] == "rescheduled-appointment" and corrected["due_at"] == before_due, "correcao humana de consulta nao move prazo nem outraTask")
    expect(422, lambda: action(service(), corrected, "update", "invalid-appointment", appointment_at=NOW[0] + timedelta(minutes=30)), "correcao de consulta exige prazo ainda anterior")
    put("users", 1, {**ALICE, "role": "supervisor", "is_active": 1})
    expect(403, lambda: service().get_task(task["id"]), "perfil alterado revoga privilegio de sessao antiga")
    put("users", 1, {**ALICE, "is_active": 1})
    all_items = service().list_tasks({"contact_id": 10, "scope": "contact", "status": "pending"})["tasks"]
    check(any(row["id"] == internal["task"]["id"] for row in all_items), "proxima acao inclui Tasks do contato sem depender de owner")
    expect(422, lambda: service().list_tasks({"scope": "contact"}), "scope contact sem contato negado")
    expect(403, lambda: service().list_tasks({"scope": "team"}), "operador nao lista equipe inteira")
    page = service().list_tasks({"scope": "queue", "limit": 1})
    check(len(page["tasks"]) == 1, "paginacao limita resultado")
    if page["next_cursor"]:
        next_page = service().list_tasks({"scope": "queue", "limit": 1, "cursor": page["next_cursor"]})
        check(not next_page["tasks"] or next_page["tasks"][0]["id"] != page["tasks"][0]["id"], "cursor avanca sem repetir item")
        expect(400, lambda: service(BOB).list_tasks({"scope": "queue", "cursor": page["next_cursor"]}), "cursor nao passa para outra identidade")
        expect(400, lambda: service().list_tasks({"scope": "queue", "cursor": page["next_cursor"] + "x"}), "cursor adulterado negado")
    # Nao varrer indefinidamente tarefas que o operador nao pode ler.
    for index in range(175):
        hidden = copy.deepcopy(DATA[(TENANT, "crm_tasks", internal["task"]["id"])])
        hidden.update(id="hidden_%03d" % index, due_at=NOW[0], contact_id=999)
        put("crm_tasks", hidden["id"], hidden)
    QUERY_LIMITS.clear()
    hidden_page = service().list_tasks({"scope": "queue", "limit": 50})
    check(sum(limit for name, limit in QUERY_LIMITS if name == "crm_tasks") <= 150, "budget de scan limita leitura mesmo sem acesso")
    check(hidden_page["has_more"], "scan parcial devolve cursor para continuar")
    # Sugestoes nunca escrevem nem inventam contato realizado.
    previous_writes = len(WRITES)
    suggestion = service().suggest_due({"type": "lembrete_consulta", "appointment_at": "2026-10-26T13:00:00-03:00"})
    check(suggestion["reason"] == "previous_workday" and suggestion["requires_confirmation"], "domingo sugere sexta com confirmacao humana")
    check(suggestion["suggested_at"].astimezone(timezone(timedelta(hours=-3))).weekday() == 4, "sugestao encontra dia permitido anterior")
    late = service().suggest_due({"type": "confirmacao_consulta", "appointment_at": NOW[0] + timedelta(hours=10)})
    check(late["late_notice"] and late["suggested_at"] < NOW[0] + timedelta(hours=10), "ultima hora sugere contato futuro antes do compromisso")
    check(len(WRITES) == previous_writes, "sugestoes sao somente leitura")
    check(DATA[(TENANT, "wa_contacts", "10")] == original_contact, "nenhuma acao alterou contato/qualificacao/Val")
    check(DATA[(TENANT, "wa_conversations", "4__synthetic")] == original_conv, "nenhuma acao abriu ou assumiu atendimento")
    check(all(name in ("crm_tasks", "crm_activities", "system_settings") for _, name, _ in WRITES), "whitelist de escrita nao toca mensagens/bot/contadores")
    check(all(limit <= 150 for _, limit in QUERY_LIMITS), "todas queries possuem limite")
    print("\n%d verificacoes passaram; nenhuma rede ou credencial utilizada." % CHECKS)


if __name__ == "__main__":
    run()
