# -*- coding: utf-8 -*-
"""Simulador local do codigo real. Sem ADC, Firestore, CX ou Meta reais."""

import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot_reminders as br
import bot_reminder_routes as routes
import bot_sender
import config
import database_firestore as db
import firestore_common as fc
import tenant_service
import channel_service


def forbidden_client(*args, **kwargs):
    raise AssertionError("Simulador: acesso ao cliente Firestore real bloqueado")


# Guard independente das fixtures: uma consulta esquecida falha antes da rede.
for module in (fc, db, br, tenant_service):
    if hasattr(module, "get_firestore_client"):
        module.get_firestore_client = forbidden_client

NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
COUNT = 0


def check(value, label):
    global COUNT
    COUNT += 1
    if not value:
        raise AssertionError(label)


class Ref:
    def __init__(self, data=None, name="thread"):
        self.data = copy.deepcopy(data) if data is not None else None
        self.id = name

    def get(self, **kwargs):
        return self

    def to_dict(self):
        return copy.deepcopy(self.data)

    def update(self, values):
        self.data.update(copy.deepcopy(values))

    def set(self, values, merge=False):
        if self.data is None or not merge:
            self.data = {}
        self.update(values)

    @property
    def exists(self):
        return self.data is not None

    def create(self, values):
        if self.data is not None:
            from google.api_core.exceptions import AlreadyExists
            raise AlreadyExists("fixture existente")
        self.set(values)


class Tx:
    # O teste exercita o corpo transacional real com snapshots isolados.
    def update(self, ref, values):
        ref.update(values)

    def set(self, ref, values, merge=False):
        ref.set(values, merge)


def fixture():
    cfg = {**br.DEFAULTS, "bot_reminder_enabled": True, "bot_enabled": True,
           "bot_reminder_generation": "g1", **{f"bot_reminder_text_{i}": f"texto {i}" for i in range(1, 4)},
           **{f"bot_reminder_lgpd_text_{i}": f"aviso {i}" for i in range(1, 4)}}
    thread = {"id": "thread", "contact_id": 1, "wa_id": "5500000000000", "channel_id": 4,
              "last_inbound_at": NOW - timedelta(minutes=21), "last_bot_turn_at": NOW - timedelta(minutes=20),
              "attendance_status": "aberto", "bot_reminder_cycle": NOW - timedelta(minutes=21),
              "bot_reminder_entry": NOW - timedelta(minutes=21), "bot_reminder_scope": "todas",
              "bot_reminder_epoch": "e1", "bot_reminder_generation": "g1", "bot_reminder_done": []}
    contact = {"id": 1, "wa_id": thread["wa_id"], "last_inbound_at": thread["bot_reminder_entry"],
               "last_new_inbound_at": thread["bot_reminder_entry"],
               "bot_reminder_latest_thread": "thread", "lgpd_consent": True}
    state = {"lgpd_consent": True, "lgpd_status": "accepted"}
    tenant = {"id": "test", "is_active": True, "settings": {"bot_reminder_mode": "on", "bot_reminder_epoch": "e1",
              "ai": {"bot_engine": "dialogflow_cx", "status": "active"}}}
    channel = {"id": 4, "tenant_id": "test", "is_active": True, "channel_type": "standard",
               "phone_number_id": "test", "access_token": "test"}
    return thread, contact, state, {}, tenant, cfg, channel


def pure():
    for reply, expected in (("Qual é seu nome?", "pending"), ("Me informe seu nome.", "pending"),
                            ("Obrigada! Posso te ajudar em algo mais, Maria?", "courtesy"),
                            ("Posso ajudar em algo mais?", "courtesy"),
                            ("Precisa de mais alguma coisa?", "courtesy"),
                            ("Posso te ajudar com mais alguma dúvida?", "courtesy"),
                            ("Você precisa de mais alguma informação?", "courtesy"),
                            ("Pode me informar seu nome? Depois posso ajudar em algo mais?", "pending"),
                            ("Até mais!", "courtesy"), ("Recebido.", "no_question"),
                            ("Acesse https://marcaconsultas.example", "link")):
        check(br.classify_reply(reply) == expected, "classificacao: " + reply)
    for kind in ("lgpd_notice", "lgpd_refusal", "engine_fallback", "handoff"):
        check(br.classify_reply("Qual seu nome?", kind) == kind, "tipo nao elegivel")
    check(br.command(" PARAR LEMBRETES! ") == "stop", "comando normalizado")
    check(br.command("Gostaria de parar o tratamento") is None, "nao interpreta palavra solta")
    check(br.command("ATIVAR LEMBRETES") == "start", "reativar")
    for bad in ("On", True, "dry-run", " on ", None, 1):
        check(br.tenant_mode({"settings": {"bot_reminder_mode": bad}}) == "off", "modo fechado")
    tenant = fixture()[4]
    tenant["settings"].update(bot_reminder_mode="off")
    tenant["settings"]["ai"]["status"] = "paused"
    with patch.object(tenant_service, "get_tenant", lambda *a: tenant):
        check(br.commands_available(), "parada continua disponivel com modo off e agente pausado")
    thread, _, _, _, _, cfg, _ = fixture()
    check(br.schedule(thread, cfg, NOW)["index"] == 1, "20 minutos exatos")
    check(br.schedule(thread, cfg, NOW - timedelta(seconds=1))["action"] == "wait", "nao antes")
    check(br.schedule(thread, cfg, NOW + timedelta(hours=4))["index"] == 2, "tick atrasado escolhe etapa avancada")
    check(br.schedule(thread, cfg, NOW + timedelta(hours=4))["skipped"] == ["etapa_1"], "pula anterior vencida")
    closing = thread["last_inbound_at"] + timedelta(minutes=1420)
    check(br.schedule(thread, cfg, closing)["index"] == 3, "fechamento pela entrada")
    check(br.schedule(thread, cfg, closing + timedelta(minutes=15))["index"] == 3, "limite exato")
    check(br.schedule(thread, cfg, closing + timedelta(minutes=15, seconds=1))["action"] == "clear", "fora janela")
    thread["last_inbound_at"] = NOW
    check(br.schedule(thread, cfg, NOW)["action"] == "clear", "inbound encerra ciclo")
    thread, _, _, _, _, cfg, _ = fixture()
    thread["last_inbound_at"] -= timedelta(seconds=1)
    check(br.schedule(thread, cfg, NOW)["action"] == "clear", "inbound recuado nao cria ciclo")
    for changes in ({"bot_reminder_minutes_1": 5}, {"bot_reminder_closing_minutes": 1430},
                    {"bot_reminder_text_1": "x" * 1001}, {"bot_reminder_text_1": "marcaconsultas"},
                    {"bot_reminder_lgpd_text_2": "y" * 1001}, {"bot_reminder_lgpd_text_3": "veja marcaconsultas"},
                    {"bot_reminder_enabled": True, **{key: "" for key in br.TEXT_KEYS}}):
        try:
            br.clean_settings(changes, cfg)
        except ValueError:
            check(True, "config invalida recusada")
        else:
            check(False, "config invalida aceita")
    thread, _, _, _, _, cfg, _ = fixture()
    cfg["bot_reminder_text_1"] = ""
    check(br.schedule(thread, cfg, NOW)["next_at"] == thread["last_bot_turn_at"] + timedelta(minutes=240), "etapa vazia desativa")


def transactions():
    tx = Tx()
    base = fixture()
    channel = Ref(base[-1])
    refs = [Ref(value, "thread" if i == 0 else str(i)) for i, value in enumerate(base[:-1])]
    thread_ref, contact_ref, state_ref, buffer_ref, tenant_ref, cfg_ref = refs
    def claim(now=NOW):
        return br._claim.to_wrap(tx, *refs, channel, base[0], now)
    with fc.tenant_context("test"):
        check(claim()["plan"]["stage"] == "etapa_1", "primeiro claim envia")
        again = claim()
        check(again.get("blocked") == "aguardando", "tick duplo nao repete")
        check(claim(NOW + timedelta(hours=4))["plan"]["stage"] == "etapa_2", "segunda etapa")
        thread_ref.data["bot_reminder_done"] = []
        state_ref.data["lgpd_consent"] = False
        check(claim(NOW + timedelta(hours=5))["blocked"] == "sem_aceite", "recusa bloqueia")
        check(thread_ref.data["bot_reminder_next_at"] is None, "bloqueio limpa agenda")
    for label, pos, update in (
            ("dono", 0, {"assigned_to": 7}), ("fechada", 0, {"attendance_status": "fechado_manual"}),
            ("backup", 0, {"is_backup": True}), ("humano", 0, {"last_human_outbound_at": NOW}),
            ("handoff", 0, {"handoff_at": NOW}), ("revogado", 1, {"lgpd_revoked": True}),
            ("opt out", 1, {"bot_reminder_opt_out": True}), ("reabertura opt out", 1, {"reopen_opt_out": True}),
            ("concluido", 1, {"bot_completed": True}), ("outro canal inbound", 1, {"last_new_inbound_at": NOW}),
            ("buffer", 3, {"items": [{"text": "novo"}]}),
            ("claim buffer", 3, {"claimed_at": NOW.isoformat()}),
            ("lgpd agente", 4, {"settings": {"ai": {"lgpd_by_agent": True}}}),
            ("coex", 6, {"channel_type": "coexistence"}), ("outro tenant", 6, {"tenant_id": "other"}),
            ("canal desligado", 6, {"is_active": False})):
        values = list(fixture())
        values[pos].update(update)
        with fc.tenant_context("test"):
            reason = br.gate(*values[:-1], values[-1], NOW)
        check(bool(reason), "gate " + label)
    thread, contact, state, buffer, tenant, cfg, channel = fixture()
    # Desfecho antigo nao bloqueia conversa retomada, conforme decisao do PO.
    contact.update(bot_outcome="link_enviado", bot_outcome_at=NOW - timedelta(hours=2))
    with fc.tenant_context("test"):
        check(br.gate(thread, contact, state, buffer, tenant, cfg, channel, NOW) is None, "link antigo nao bloqueia nova conversa")
    t, c, cfg_ref = Ref(thread), Ref(contact), Ref(cfg)
    meta = {"entry": contact["last_new_inbound_at"], "inbound": thread["last_inbound_at"], "epoch": "e1", "kind": "cx_reply", "generation": "g1"}
    # Reentrega da Meta (~23 s sem ACK): o upsert sobe last_inbound_at do contato,
    # mas nao ha mensagem nova. Nao pode impedir o carimbo nem cancelar o ciclo.
    c.data["last_inbound_at"] = NOW + timedelta(seconds=23)
    check(br._stamp.to_wrap(tx, t, c, cfg_ref, meta, NOW, "pending"), "carimba envio confirmado apesar da reentrega")
    check(t.data["bot_reminder_next_at"] == NOW + timedelta(minutes=20), "agenda apos fala")
    with fc.tenant_context("test"):
        check(br.gate({**t.data, "id": "thread"}, c.data, state, buffer, tenant, cfg, channel, NOW) is None,
              "reentrega da Meta nao cancela o ciclo")
    c.data["last_new_inbound_at"] = NOW + timedelta(seconds=1)
    check(not br._stamp.to_wrap(tx, t, c, cfg_ref, meta, NOW + timedelta(seconds=2), "pending"), "turno atrasado nao rearma")
    c.data["last_new_inbound_at"] = meta["entry"]
    br._stamp.to_wrap(tx, t, c, cfg_ref, meta, NOW, "courtesy")
    check(t.data["bot_reminder_next_at"] is None, "cortesia limpa agenda anterior")
    check(br._preference.to_wrap(tx, c, "stop", NOW), "para lembretes")
    check(c.data["bot_reminder_opt_out"] is True, "preferencia persistida")
    check(not br._preference.to_wrap(tx, c, "start", NOW - timedelta(seconds=1)), "comando antigo nao desfaz parada")
    check(br._preference.to_wrap(tx, c, "start", NOW + timedelta(seconds=1)), "reativa explicitamente")
    check(not c.data["bot_reminder_opt_out"], "reativada")
    cfg_ref = Ref(cfg)
    supplied = {"version": routes.version({key: cfg[key] for key in br.KEYS}), "settings": {"bot_reminder_enabled": False}}
    saved = routes._save.to_wrap(tx, cfg_ref, supplied)
    check(saved["bot_reminder_generation"] != "g1", "toggle muda geracao")
    try:
        routes._save.to_wrap(tx, cfg_ref, supplied)
    except Exception as exc:
        check(getattr(exc, "status_code", 0) == 409, "form antigo recusado")
    else:
        check(False, "form antigo aceito")


def sender():
    thread, contact, _, _, _, _, channel = fixture()
    writes = []
    class Client:
        code = 200
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            return type("Response", (), {"status_code": self.code, "json": lambda s: {"messages": [{"id": "local_test"}]} if Client.code == 200 else {"error": {"code": Client.code}}})()
    with patch.object(bot_sender.httpx, "Client", Client), patch.object(db, "save_wa_message", lambda *a, **kw: writes.append(kw)):
        check(bot_sender.send_bot_reminder(contact, thread, channel, "texto", "etapa_1")["ok"], "envia")
        check(not writes[0]["advance_recency"] and not writes[0]["reopen_attendance"], "preserva recencia e fechamento")
        check(writes[0]["sender_user_id"] is None and not writes[0]["human_outbound"], "nao simula humano")
        check(writes[0]["automation_kind"] == "bot_reminder" and "PARAR LEMBRETES" in writes[0]["content"], "marcador e comando")
        Client.code = 131047
        check(bot_sender.send_bot_reminder(contact, thread, channel, "texto", "etapa_1")["code"] == 131047, "erro de janela")
        check(len(writes) == 1, "falha nao grava doc failed")


def worker():
    thread, contact, state, buffer, tenant, cfg, channel = fixture()
    thread["bot_reminder_next_at"] = NOW
    store = {("wa_conversations", "thread"): Ref(thread, "thread"), ("wa_contacts", "1"): Ref(contact, "1"),
             ("bot_states", "1"): Ref(state), ("bot_buffers", "1"): Ref(buffer),
             ("tenants", "test"): Ref(tenant), ("system_settings", "chat"): Ref(cfg), ("channels", "4"): Ref(channel)}
    def ref(name, key):
        return store.setdefault((name, str(key)), Ref(None, str(key)))
    reads = []
    class Query:
        def __init__(self, name): self.name, self.filters = name, []
        def where(self, field, op, value): self.filters.append((field, op, value)); return self
        def order_by(self, *a, **kw): return self
        def limit(self, *a): return self
        def stream(self):
            reads.append(self.name)
            for (name, key), item in list(store.items()):
                if name != self.name: continue
                if all(item.data.get(field) is not None and
                       (item.data[field] >= value if op == ">=" else item.data[field] <= value)
                       for field, op, value in self.filters):
                    yield item
    audits, sent = [], []
    real_claim = br._claim
    with ExitStack() as stack:
        for target, name, value in (
                (config, "FEATURE_BOT_REMINDER", True), (br, "document", ref), (br, "collection", Query),
                (br, "get_firestore_client", lambda: type("Client", (), {"transaction": lambda self: Tx()})()),
                (br, "_claim", lambda tx, *a: real_claim.to_wrap(tx, *a)),
                (br, "audit", lambda *a, **kw: audits.append((a, kw))),
                (tenant_service, "list_tenants", lambda **kw: [store[("tenants", "test")].data]),
                (tenant_service, "tenant_doc_ref", lambda tid: ref("tenants", tid)),
                (channel_service, "get_channel", lambda cid: channel),
                (bot_sender, "send_bot_reminder", lambda *a, **kw: sent.append(a) or {"ok": True})):
            stack.enter_context(patch.object(target, name, value))
        check(br.run_tick(NOW)["sent"] == 1, "worker integrado envia uma vez")
        check(br.run_tick(NOW)["sent"] == 0 and len(sent) == 1, "tick repetido sem reenvio")
        check(len(reads) == 2, "consulta limitada pela agenda")
        store[("tenants", "test")].data["settings"]["bot_reminder_mode"] = "off"
        before = len(reads)
        br.run_tick(NOW)
        check(len(reads) == before, "tenant off nao consulta threads")
        store[("tenants", "test")].data["settings"]["bot_reminder_mode"] = "dry_run"
        check(br.run_tick(NOW + timedelta(hours=4))["simulated"] == 1, "dry run simula segunda etapa")
        check(len(sent) == 1, "dry run nao usa transporte")
        simulated_before = len(audits)
        br.run_tick(NOW + timedelta(hours=4))
        check(len(audits) == simulated_before, "dry run nao repete auditoria")
        store[("tenants", "test")].data["settings"].update(bot_reminder_mode="on", bot_reminder_epoch="e2")
        close = thread["last_inbound_at"] + timedelta(minutes=1420)
        br.run_tick(close)
        check(len(sent) == 1 and ref("wa_conversations", "thread").data["bot_reminder_next_at"] is None,
              "mudanca de modo invalida restante da simulacao")
        store[("tenants", "test")].data["settings"].update(bot_reminder_mode="on", bot_reminder_epoch="e1")
        for index in range(2, 37):
            name = "thread_%s" % index
            row = {**thread, "id": name, "contact_id": index}
            person = {**contact, "id": index, "bot_reminder_latest_thread": name}
            if index == 36:
                row.update(last_inbound_at=NOW - timedelta(minutes=1420), last_bot_turn_at=NOW - timedelta(minutes=1400),
                           bot_reminder_cycle=NOW - timedelta(minutes=1420), bot_reminder_entry=NOW - timedelta(minutes=1420))
                person["last_inbound_at"] = person["last_new_inbound_at"] = row["bot_reminder_entry"]
            store[("wa_conversations", name)] = Ref(row, name)
            store[("wa_contacts", str(index))] = Ref(person, str(index))
            store[("bot_states", str(index))] = Ref(state)
        with patch.object(config, "BOT_REMINDER_MAX_PER_TICK", 1):
            check(br.run_tick(NOW)["sent"] == 1 and sent[-1][-1] == "fechamento", "prioriza fechamento antes das outras etapas")
        check(br.run_tick(NOW)["sent"] == 30, "teto tecnico global por tick")
        real_close = br._close_failed_window
        with patch.object(bot_sender, "send_bot_reminder", lambda *a, **kw: {"ok": False, "code": 131047}), \
                patch.object(br, "_close_failed_window", lambda tx, *a: real_close.to_wrap(tx, *a)):
            check(br.run_tick(NOW + timedelta(minutes=5))["failed"] == 4, "falhas de janela nas quatro restantes")
            check(br.run_tick(NOW + timedelta(minutes=10))["failed"] == 0, "janela fechada nao repete falhas")


def persistence():
    thread, contact, _, _, _, cfg, channel = fixture()
    cid = db._make_conversation_id(4, contact["wa_id"])
    thread.update(id=cid, last_message_at=NOW, unread_count=7, last_human_outbound_at=None)
    contact.update(last_message_at=NOW, unread_count=7, qualification="novo")
    store = {("wa_contacts", "1"): Ref(contact, "1"), ("wa_conversations", cid): Ref(thread, cid),
             ("system_settings", "chat"): Ref(cfg, "chat")}
    def ref(name, key):
        return store.setdefault((name, str(key)), Ref(None, str(key)))
    class Query:
        def __init__(self, name): self.name, self.filters = name, []
        def where(self, key, op, value): self.filters.append((key, value)); return self
        def limit(self, *a): return self
        def stream(self):
            return iter(item for (name, key), item in store.items() if name == self.name and item.data
                        and all(item.data.get(field) == value for field, value in self.filters))
    audits = []
    with ExitStack() as stack:
        for target, name, value in (
                (db, "document", ref), (db, "collection", Query), (db, "next_sequence", lambda *a, **kw: 4242),
                (db, "get_wa_message_by_wa_message_id", lambda *a, **kw: None),
                (db, "get_current_protocol_id", lambda *a, **kw: None),
                (db, "increment_audit_metrics", lambda **kw: audits.append(kw)),
                (channel_service, "get_channel", lambda *a: channel)):
            stack.enter_context(patch.object(target, name, value))
        db.save_wa_message("local_test_only", 1, "outbound", "text", "lembrete", status="sent", timestamp_wa=NOW.isoformat(),
                           contact=contact, channel_id=4, conversation_id=cid, advance_recency=False,
                           reopen_attendance=False, promote_qualification=False, human_outbound=False,
                           sent_by_name="Lembrete automático", automation_kind="bot_reminder", automation_stage="etapa_1")
        saved_thread = ref("wa_conversations", cid).data
        saved_contact = ref("wa_contacts", 1).data
        for key in ("last_message_at", "unread_count", "attendance_status", "last_human_outbound_at"):
            check(saved_thread.get(key) == thread.get(key), "persistencia real preserva thread " + key)
        for key in ("last_message_at", "unread_count", "qualification", "bot_outcome", "reopen_attempts"):
            check(saved_contact.get(key) == contact.get(key), "persistencia real preserva contato " + key)
        check(ref("wa_messages", 4242).data["automation_stage"] == "etapa_1", "marcador persistido real")
        usages = [value.data for (name, key), value in store.items() if key.startswith("usage_")]
        check(len(usages) == 1 and "etapa_1" in usages[0]["bot_reminders_sent"]["B"], "uso mensal por serie e etapa")
        check("automation_series" not in ref("wa_messages", 4242).data or ref("wa_messages", 4242).data["automation_series"] == "",
              "serie B legada sem campo novo obrigatorio")
        db.save_wa_message("local_test_only_a", 1, "outbound", "text", "lembrete A", status="sent", timestamp_wa=NOW.isoformat(),
                           contact=contact, channel_id=4, conversation_id=cid, advance_recency=False,
                           reopen_attendance=False, promote_qualification=False, human_outbound=False,
                           sent_by_name="Lembrete automático", automation_kind="bot_reminder", automation_stage="etapa_1",
                           automation_series="A")
        check(ref("wa_messages", 4242).data["automation_series"] == "A", "serie A persistida na mensagem")
        usages = [value.data for (name, key), value in store.items() if key.startswith("usage_")]
        check("etapa_1" in usages[0]["bot_reminders_sent"].get("A", {}), "uso mensal separa a serie A")
        # Entrada nova carimba o marcador; reentrega do mesmo wamid nao.
        db.save_wa_message("wamid_local_in", 1, "inbound", "text", "oi", status="received", timestamp_wa=NOW.isoformat(),
                           contact=contact, channel_id=4, conversation_id=cid)
        first_mark = ref("wa_contacts", 1).data.get("last_new_inbound_at")
        check(first_mark is not None, "mensagem nova carimba last_new_inbound_at")
        ref("wa_contacts", 1).data["last_new_inbound_at"] = "sentinela"
        db.save_wa_message("wamid_local_in", 1, "inbound", "text", "oi", status="received", timestamp_wa=NOW.isoformat(),
                           contact=contact, channel_id=4, conversation_id=cid)
        check(ref("wa_contacts", 1).data["last_new_inbound_at"] == "sentinela", "reentrega nao mexe no marcador")
        before = {key: ref("system_settings", "chat").data[key] for key in br.KEYS}
        db.save_system_settings({**db.get_system_settings(), "notification_sound_path": "local-test.ogg"})
        check(before == {key: ref("system_settings", "chat").data[key] for key in br.KEYS}, "save inteiro do upload de som preserva lembretes")


def api():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import rbac
    _, _, _, _, tenant, cfg, _ = fixture()
    cfg_ref = Ref(cfg, "chat")
    user = {"id": 1, "role": "admin", "firebase_uid": "local"}
    allow_cron = {"value": False}
    async def identity(): return dict(user)
    def cron_auth(request):
        if not allow_cron["value"]:
            raise HTTPException(401, "Cron sem autenticacao")
    real_save = routes._save
    with ExitStack() as stack:
        for target, name, value in (
                (rbac, "get_perfil_toggles", lambda *a: None), (routes, "available", lambda: True),
                (routes, "document", lambda *a: cfg_ref), (routes, "get_firestore_client", lambda: type("Client", (), {"transaction": lambda self: Tx()})()),
                (routes, "_save", lambda tx, *a: real_save.to_wrap(tx, *a)),
                (db, "log_audit", lambda *a: None), (tenant_service, "get_tenant", lambda *a: tenant),
                (br, "run_tick", lambda: {"status": "off"})):
            stack.enter_context(patch.object(target, name, value))
        app = FastAPI()
        app.include_router(routes.create_router(identity, cron_auth))
        with TestClient(app) as client:
            response = client.get("/api/settings/bot-reminders")
            check(response.status_code == 200, "GET com permissao")
            body = response.json()
            body["settings"]["bot_reminder_text_1"] = "Texto editado"
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 200, "PUT salva textos")
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 409, "HTTP formulario obsoleto")
            body = client.get("/api/settings/bot-reminders").json()
            body["settings"]["bot_reminder_text_1"] = "x" * 1001
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 400, "HTTP limite de texto")
            body = client.get("/api/settings/bot-reminders").json()
            body["settings"].update({f"bot_reminder_text_{i}": "" for i in range(1, 4)})
            body["settings"]["bot_reminder_lgpd_text_1"] = "Podemos continuar?"
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 200, "ativa so com texto da serie A")
            body = client.get("/api/settings/bot-reminders").json()
            check(body["settings"]["bot_reminder_lgpd_text_1"] == "Podemos continuar?", "texto da serie A persistido")
            body["settings"]["bot_reminder_lgpd_text_2"] = "veja marcaconsultas"
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 400, "link recusado tambem na serie A")
            user["role"] = "operador"
            check(client.get("/api/settings/bot-reminders").status_code == 403, "GET exige permissao")
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 403, "PUT exige permissao")
            user.update(role="admin", read_only=True)
            check(client.put("/api/settings/bot-reminders", json=body).status_code == 403, "Ver como nao altera")
            check(client.post("/api/internal/cron/bot-reminders").status_code == 401, "cron exige auth mesmo desligado")
            allow_cron["value"] = True
            check(client.post("/api/internal/cron/bot-reminders").json()["status"] == "off", "cron autenticado")
            with patch.object(routes, "available", lambda: False):
                user.pop("read_only")
                check(client.get("/api/settings/bot-reminders").status_code == 404, "recurso indisponivel oculto na API")


def pipeline():
    import webhook
    recorded = []
    succeeded = {"value": True}
    async def process(*args, **kwargs):
        if kwargs.get("turn_meta") is not None:
            kwargs["turn_meta"].update(kind="cx_reply", generation="g1")
        return "Qual seu nome?"
    async def send(*args, **kwargs): return succeeded["value"]
    def prepare(*args): return {"kind": "none"}
    with patch.object(config, "FEATURE_BOT_REMINDER", True), patch.object(br, "prepare_turn", prepare), \
            patch.object(br, "stamp_turn", lambda *a: recorded.append(a)), \
            patch.object(webhook, "process_bot_message_async", process), patch.object(webhook, "_send_bot_reply", send):
        asyncio.run(webhook._run_bot_turn_and_send(1, "oi", "", "local", "local", "local", 4))
        check(len(recorded) == 1 and recorded[0][2]["kind"] == "cx_reply", "pipeline transmite tipo e carimba sucesso")
        succeeded["value"] = False
        asyncio.run(webhook._run_bot_turn_and_send(1, "oi", "", "local", "local", "local", 4))
        check(len(recorded) == 1, "envio falho nao carimba")
        def fail_prepare(*args): raise RuntimeError("fixture indisponivel")
        with patch.object(br, "prepare_turn", fail_prepare), patch.object(webhook.logger, "error"):
            reply = asyncio.run(webhook._run_bot_turn_and_send(1, "oi", "", "local", "local", "local", 4))
        check(reply == "Qual seu nome?", "falha de preparacao nao silencia Val")


def aguardando_aviso():
    """Fixture da serie A: lead recebeu o aviso da LGPD e nao respondeu."""
    thread, contact, state, buffer, tenant, cfg, channel = fixture()
    contact.pop("lgpd_consent")
    return thread, contact, {"lgpd_status": "awaiting", "step": "lgpd"}, buffer, tenant, cfg, channel


def serie_a():
    """Emenda de 11/11 ao ADR 0015: lembretes para quem parou no aviso da LGPD."""
    import bot_service
    tx = Tx()
    check(br.text_key("A", 2) == "bot_reminder_lgpd_text_2" and br.text_key("B", 2) == "bot_reminder_text_2", "chaves por serie")
    check(br.series_of({}) == "B" and br.series_of({"bot_reminder_series": "A"}) == "A", "thread antiga continua serie B")
    thread, contact, state, buffer, tenant, cfg, channel = aguardando_aviso()
    t, c, cfg_ref = Ref(thread), Ref(contact), Ref(cfg)
    meta = {"entry": contact["last_new_inbound_at"], "inbound": thread["last_inbound_at"], "epoch": "e1",
            "kind": "lgpd_notice", "generation": "g1"}
    check(br.classify_reply({"type": "interactive_buttons", "body": "Podemos continuar?"}, "lgpd_notice") == "lgpd_notice",
          "aviso com botoes classificado pelo tipo do turno")
    check(br._stamp.to_wrap(tx, t, c, cfg_ref, meta, NOW, "lgpd_notice"), "aviso da LGPD carimba")
    check(t.data["bot_reminder_series"] == "A" and t.data["bot_reminder_scope"] == "todas", "aviso arma a serie A")
    check(t.data["bot_reminder_next_at"] == NOW + timedelta(minutes=20), "serie A usa os mesmos 20 minutos")
    a_thread = {**t.data, "id": "thread"}
    plan = br.schedule(a_thread, cfg, NOW + timedelta(minutes=20))
    check(plan["action"] == "send" and plan["index"] == 1, "serie A vence no mesmo horario")
    check(br.schedule(a_thread, cfg, NOW + timedelta(hours=4))["index"] == 2, "serie A segunda etapa em 4 h")
    closing = thread["last_inbound_at"] + timedelta(minutes=1420)
    check(br.schedule(a_thread, cfg, closing)["index"] == 3, "serie A fechamento pela entrada")
    only_b = {**cfg, **{br.text_key("A", i): "" for i in range(1, 4)}}
    check(br.schedule(a_thread, only_b, NOW + timedelta(minutes=20))["action"] == "clear", "sem textos da serie A nada sai")
    only_a = {**cfg, **{br.text_key("B", i): "" for i in range(1, 4)}}
    check(br.schedule({**thread, "id": "thread"}, only_a, NOW)["action"] == "clear", "textos da serie A nao valem para a B")
    # Turno seguinte no mesmo ciclo vira serie B: etapas da A nao contam como feitas.
    t.data["bot_reminder_done"] = ["etapa_1"]
    br._stamp.to_wrap(tx, t, c, cfg_ref, {**meta, "kind": "cx_reply"}, NOW, "pending")
    check(t.data["bot_reminder_series"] == "B" and t.data["bot_reminder_done"] == [], "troca de serie zera etapas feitas")
    br._stamp.to_wrap(tx, t, c, cfg_ref, {**meta, "kind": "lgpd_refusal"}, NOW, "lgpd_refusal")
    check(t.data["bot_reminder_scope"] == "nenhuma" and t.data["bot_reminder_next_at"] is None, "recusa nao arma e limpa agenda")
    with fc.tenant_context("test"):
        check(br.gate(a_thread, contact, state, buffer, tenant, cfg, channel, NOW) is None, "parado no aviso e elegivel")
        for label, st, extra in (("recusou no estado", {"lgpd_status": "refused", "lgpd_consent": False}, {}),
                                 ("recusou no contato", state, {"lgpd_consent": False}),
                                 ("aceitou", {"lgpd_status": "accepted", "lgpd_consent": True}, {"lgpd_consent": True}),
                                 ("sem doc de estado", {}, {}),
                                 ("humano conduzindo", {**state, "human_active": True}, {}),
                                 ("revogado", state, {"lgpd_revoked": True}),
                                 ("parou lembretes", state, {"bot_reminder_opt_out": True})):
            check(bool(br.gate(a_thread, {**contact, **extra}, st, buffer, tenant, cfg, channel, NOW)), "serie A barra: " + label)
        with patch.object(bot_service, "lgpd_consent_resolved", lambda *a, **kw: True):
            check(br.gate(a_thread, contact, state, buffer, tenant, cfg, channel, NOW) == "ja_aceitou", "aceite ja resolvido barra a serie A")
        check(br.gate({**thread, "id": "thread"}, contact, state, buffer, tenant, cfg, channel, NOW) == "sem_aceite",
              "serie B continua exigindo aceite")
    refs = [Ref(a_thread, "thread"), Ref(contact, "1"), Ref(state, "2"), Ref(buffer, "3"), Ref(tenant, "4"), Ref(cfg, "5")]
    with fc.tenant_context("test"):
        claimed = br._claim.to_wrap(tx, *refs, Ref(channel), a_thread, NOW + timedelta(minutes=20))
    check(claimed["series"] == "A" and claimed["text"] == "aviso 1", "claim usa o texto da serie A")


def sender_serie_a():
    import lgpd_bot
    thread, contact, _, _, _, _, channel = aguardando_aviso()
    posted, writes = [], []
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, json=None, headers=None):
            posted.append(json)
            return type("Response", (), {"status_code": 200, "json": lambda s: {"messages": [{"id": "local_a"}]}})()
    with patch.object(bot_sender.httpx, "Client", Client), patch.object(db, "save_wa_message", lambda *a, **kw: writes.append(kw)):
        check(bot_sender.send_bot_reminder(contact, thread, channel, "Podemos continuar?", "etapa_1", series="A")["ok"], "serie A envia")
        check(bot_sender.send_bot_reminder(contact, thread, channel, "texto", "etapa_1")["ok"], "serie B segue padrao")
    interactive = posted[0].get("interactive") or {}
    ids = [b["reply"]["id"] for b in interactive.get("action", {}).get("buttons", [])]
    check(posted[0]["type"] == "interactive" and ids == ["lgpd_aceitar", "lgpd_recusar"], "serie A sai com os botoes do aviso")
    check(interactive["body"]["text"] == "Podemos continuar?" and "PARAR LEMBRETES" in interactive["footer"]["text"],
          "corpo e o texto da clinica; parada no rodape")
    check(len(interactive["footer"]["text"]) <= 60, "rodape dentro do limite da Meta")
    check(writes[0]["automation_series"] == "A" and "PARAR LEMBRETES" in writes[0]["content"], "serie gravada e rodape visivel no CRM")
    check(not writes[0]["advance_recency"] and writes[0]["sender_user_id"] is None, "serie A tambem nao simula humano")
    check(posted[1]["type"] == "text" and writes[1]["automation_series"] == "B", "serie B continua texto simples")
    # O toque nos botoes do lembrete entra no gate LGPD que ja existe.
    st = {"lgpd_status": "awaiting"}
    lgpd_bot.handle_lgpd(st, ids[0])
    check(st.get("lgpd_consent") is True, "toque em Sim do lembrete registra o aceite")
    st = {"lgpd_status": "awaiting"}
    lgpd_bot.handle_lgpd(st, ids[1])
    check(st.get("lgpd_consent") is False, "toque em Nao do lembrete registra a recusa")


def worker_serie_a():
    thread, contact, state, buffer, tenant, cfg, channel = aguardando_aviso()
    thread.update(bot_reminder_series="A", bot_reminder_next_at=NOW)
    store = {("wa_conversations", "thread"): Ref(thread, "thread"), ("wa_contacts", "1"): Ref(contact, "1"),
             ("bot_states", "1"): Ref(state), ("bot_buffers", "1"): Ref(buffer),
             ("tenants", "test"): Ref(tenant), ("system_settings", "chat"): Ref(cfg), ("channels", "4"): Ref(channel)}
    def ref(name, key):
        return store.setdefault((name, str(key)), Ref(None, str(key)))
    class Query:
        def __init__(self, name): self.name, self.filters = name, []
        def where(self, field, op, value): self.filters.append((field, op, value)); return self
        def order_by(self, *a, **kw): return self
        def limit(self, *a): return self
        def stream(self):
            for (name, key), item in list(store.items()):
                if name == self.name and all(item.data.get(field) is not None and
                                             (item.data[field] >= value if op == ">=" else item.data[field] <= value)
                                             for field, op, value in self.filters):
                    yield item
    audits, sent = [], []
    real_claim = br._claim
    with ExitStack() as stack:
        for target, name, value in (
                (config, "FEATURE_BOT_REMINDER", True), (br, "document", ref), (br, "collection", Query),
                (br, "get_firestore_client", lambda: type("Client", (), {"transaction": lambda self: Tx()})()),
                (br, "_claim", lambda tx, *a: real_claim.to_wrap(tx, *a)),
                (br, "audit", lambda *a, **kw: audits.append(a)),
                (tenant_service, "list_tenants", lambda **kw: [store[("tenants", "test")].data]),
                (tenant_service, "tenant_doc_ref", lambda tid: ref("tenants", tid)),
                (bot_sender, "send_bot_reminder", lambda *a, **kw: sent.append((a, kw)) or {"ok": True})):
            stack.enter_context(patch.object(target, name, value))
        check(br.run_tick(NOW)["sent"] == 1, "worker envia a serie A")
        check(sent[0][1].get("series") == "A" and sent[0][0][3] == "aviso 1", "worker passa serie e texto A")
        check(any(a[0] == "SENT" and a[3] == "A" for a in audits), "auditoria registra a serie A")
        # Lead respondeu ao aviso (aceitou) antes da etapa 2: o claim barra.
        ref("bot_states", 1).data.update(lgpd_status="accepted", lgpd_consent=True)
        check(br.run_tick(NOW + timedelta(hours=4))["sent"] == 0, "aceite antes da etapa seguinte barra a serie A")
        check(any(a[0] == "SKIPPED" and a[3] == "A" for a in audits), "pulo da serie A auditado")


def main():
    pure()
    transactions()
    sender()
    worker()
    persistence()
    api()
    pipeline()
    serie_a()
    sender_serie_a()
    worker_serie_a()
    from bot_reminder_measure import summarize
    report = summarize([{"conversation_id": "private", "direction": "outbound", "msg_type": "text", "timestamp_wa": NOW, "content": "Qual seu nome?"}], NOW)
    check(report["tempo_de_resposta"]["ainda_em_observacao"] == 1, "medidor nao inventa nunca respondeu")
    check("private" not in str(report), "medidor sem ids")
    early = NOW.replace(hour=1)
    report = summarize([{"conversation_id": "private", "direction": "outbound", "msg_type": "text", "timestamp_wa": early, "content": "Qual seu nome?"}], NOW)
    check("2026-11-10" in report["threads_com_turno_por_dia"], "agregacao por dia em Brasilia")
    with patch.object(config, "FEATURE_BOT_REMINDER", False), patch.object(br, "collection", side_effect=AssertionError("nao ler")):
        check(br.run_tick()["status"] == "off", "desligado nao le Firestore")
    from bot_reminder_measure import trava_escrita
    from google.cloud.firestore_v1 import document, batch
    trava_escrita()
    for method in (document.DocumentReference.set, document.DocumentReference.update, document.DocumentReference.delete,
                   document.DocumentReference.create, batch.WriteBatch.commit):
        try:
            method(None)
        except RuntimeError:
            check(True, "trava de escrita impede SDK")
        else:
            check(False, "SDK deixou escrever")
    print("OK: %s verificacoes locais de lembretes." % COUNT)


if __name__ == "__main__":
    main()
