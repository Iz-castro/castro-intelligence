# -*- coding: utf-8 -*-

"""Simulacao local da preferencia comercial; nenhum acesso a Firestore/Meta.

Exercita a funcao transacional real com adaptador de memoria que verifica
versoes de leitura no commit, inclusive corrida de duas operadoras.
"""

import copy
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi import HTTPException  # noqa: E402

import commercial_contact_policy as policy  # noqa: E402
import firestore_common as common  # noqa: E402


STORE = {}
REVISIONS = {}
LOCK = threading.RLock()
FAIL_AUDIT = False
CHECKS = 0
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
TENANT = "fixture-a"
ACTOR = {"id": 7, "firebase_uid": "fixture-uid-7", "tenant_id": TENANT, "is_active": 1}
MANAGER = {"id": 8, "firebase_uid": "fixture-uid-8", "tenant_id": TENANT,
           "is_active": 1, "can_unblock": True}


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(label)
    print("OK: " + label)


def expect_http(status, fn, label):
    try:
        fn()
    except HTTPException as exc:
        check(exc.status_code == status, label)
        return
    raise AssertionError(label + ": nenhuma HTTPException")


def expect_fatal(module, fn, label):
    try:
        fn()
    except module.Fatal:
        check(True, label)
        return
    raise AssertionError(label + ": nenhuma Fatal")


class Conflict(Exception):
    pass


class Snapshot:
    def __init__(self, data, ref):
        self.data = copy.deepcopy(data)
        self.reference = ref
        self.id = ref.id
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self.data)


class Ref:
    def __init__(self, tenant, collection, identifier):
        self.key = (tenant, collection, str(identifier))
        self.id = str(identifier)

    def get(self, transaction=None):
        with LOCK:
            if transaction is not None:
                if transaction.writes:
                    raise AssertionError("leitura apos escrita em transacao")
                transaction.reads[self.key] = REVISIONS.get(self.key, 0)
            return Snapshot(STORE.get(self.key), self)

    def set(self, data, merge=False):
        with LOCK:
            existing = STORE.get(self.key, {}) if merge else {}
            STORE[self.key] = {**copy.deepcopy(existing), **copy.deepcopy(data)}
            REVISIONS[self.key] = REVISIONS.get(self.key, 0) + 1


class Transaction:
    def __init__(self):
        self.reads = {}
        self.writes = []

    def set(self, ref, data, merge=False):
        self.writes.append(("set", ref, copy.deepcopy(data), merge))

    def create(self, ref, data):
        self.writes.append(("create", ref, copy.deepcopy(data), False))

    def commit(self):
        with LOCK:
            for key, revision in self.reads.items():
                if REVISIONS.get(key, 0) != revision:
                    raise Conflict()
            if FAIL_AUDIT and any(ref.key[1] == "audit_log" for _, ref, _, _ in self.writes):
                raise RuntimeError("falha de auditoria simulada")
            if any(kind == "create" and ref.key in STORE for kind, ref, _, _ in self.writes):
                raise Conflict()
            for _, ref, data, merge in self.writes:
                ref.set(data, merge)


REAL_BODY = policy._set_preference_transaction.to_wrap


def transaction_runner(transaction, *args, **kwargs):
    for _ in range(4):
        result = REAL_BODY(transaction, *args, **kwargs)
        try:
            transaction.commit()
            return result
        except Conflict:
            transaction = Transaction()
    raise AssertionError("retentativas simuladas esgotadas")


def authorize(contact, actor, action):
    if contact.get("assigned_to") not in (None, actor["id"]) and not actor.get("can_unblock"):
        raise HTTPException(403, "sem acesso ao contato")
    if action == "unblock" and not actor.get("can_unblock"):
        raise HTTPException(403, "sem permissao para reativar")


def seed():
    STORE.clear()
    REVISIONS.clear()
    Ref(TENANT, "wa_contacts", 1).set({
        "id": 1, "wa_id": "fixture-number", "display_name": "fixture-name",
        "notes": "fixture-private-note", "assigned_to": None,
        "qualification": "em_atendimento", "bot_completed": True,
        "lgpd_consent": True, "lgpd_revoked": False, "reopen_opt_out": True,
        "reopen_attempts": 1,
        "reopen_batch_sent_at": [{"at": NOW.isoformat(), "audience": "bot"}],
        "last_inbound_at": NOW - timedelta(days=3), "channel_id": 1,
    })


def change(active=True, version=0, operation="fixture-operation-0001", actor=None,
           confirmed=True, checker=authorize):
    return policy.set_commercial_contact_preference(
        TENANT, 1, actor or ACTOR, active=active, expected_version=version,
        operation_id=operation, patient_request_confirmed=confirmed, authorize=checker,
    )


def contact():
    return Ref(TENANT, "wa_contacts", 1).get().to_dict()


def audit_rows():
    return [row for key, row in STORE.items() if key[1] == "audit_log"]


def run():
    global FAIL_AUDIT
    policy.get_firestore_client = lambda: SimpleNamespace(transaction=Transaction)
    policy.tenant_document = lambda tenant, coll, identifier: Ref(tenant, coll, identifier)
    policy._set_preference_transaction = transaction_runner
    policy.utcnow = lambda: NOW
    # Importacoes do DB/script nao podem instanciar cliente com ADC.
    common.get_firestore_client = lambda: (_ for _ in ()).throw(AssertionError("cliente real proibido"))
    token = common.set_tenant_context(TENANT)
    try:
        seed()
        check(not policy.is_commercial_contact_blocked(contact()), "legado sem campo nao bloqueia")
        check(policy.is_commercial_contact_blocked(None), "contato indisponivel nao libera")
        check(policy.is_commercial_contact_blocked({policy.FIELD: {"active": False}}),
              "estrutura presente invalida falha fechada")
        view = policy.get_commercial_contact_preference(TENANT, 1, ACTOR, authorize)
        check(view[policy.FIELD] == {"active": False, "version": 0}, "leitura legado nao grava estado")
        check(not audit_rows(), "leitura nao gera mutacao/auditoria")
        before = contact()
        first = change()
        check(first[policy.FIELD]["active"] and first[policy.FIELD]["version"] == 1,
              "pedido expresso grava bloqueio e versao")
        check({k: v for k, v in contact().items() if k != policy.FIELD} == before,
              "bloquear preserva LGPD, Val, posse, historico e tetos")
        check(len(audit_rows()) == 1, "mutacao e auditoria atomicas")
        audit_dump = json.dumps(audit_rows(), default=str)
        check(all(value not in audit_dump for value in ("fixture-name", "fixture-number", "fixture-private-note")),
              "auditoria sem nome, telefone ou notas")
        repeat = change()
        check(repeat["replayed"] and len(audit_rows()) == 1 and contact()[policy.FIELD]["version"] == 1,
              "replay nao duplica versao ou auditoria")
        expect_http(409, lambda: change(version=1), "mesma operacao com outro conteudo e rejeitada")
        expect_http(409, lambda: change(version=0, operation="fixture-operation-stale"),
                    "versao obsoleta rejeitada")
        expect_http(400, lambda: change(version=1, operation="fixture-unconfirmed", confirmed=False),
                    "recusa nao pode ser inferida sem confirmacao")
        expect_http(400, lambda: change(False, 1, "fixture-unblock-unconfirmed", MANAGER, False),
                    "reversao exige manifestacao expressa")
        expect_http(403, lambda: change(False, 1, "fixture-unblock-denied"),
                    "autorizador impede reativacao por perfil comum")
        second = change(False, 1, "fixture-unblock-allowed", MANAGER)
        check(not second[policy.FIELD]["active"] and second[policy.FIELD]["version"] == 2,
              "reautorizacao especifica permitida e auditada")
        old = change()
        check(old["replayed"] and old["operation_version"] == 1 and old[policy.FIELD]["version"] == 2
              and not old[policy.FIELD]["active"], "replay antigo retorna atual e nao desfaz reversao posterior")
        check(contact()["reopen_opt_out"] and contact()["reopen_batch_sent_at"] == before["reopen_batch_sent_at"],
              "reversao comercial nao limpa outro opt-out nem repoe teto")
        expect_http(403, lambda: policy.get_commercial_contact_preference(
            "fixture-b", 1, ACTOR, authorize), "ator nao escolhe outro tenant")
        other = common.set_tenant_context("fixture-b")
        try:
            expect_http(403, lambda: policy.get_commercial_contact_preference(TENANT, 1, ACTOR, authorize),
                        "contexto divergente e negado")
        finally:
            common.reset_tenant_context(other)
        missing = common.set_tenant_context(None)
        try:
            expect_http(403, lambda: policy.get_commercial_contact_preference(TENANT, 1, ACTOR, authorize),
                        "contexto ausente nao cai no flat")
        finally:
            common.reset_tenant_context(missing)
        expect_http(403, lambda: policy.get_commercial_contact_preference(
            TENANT, 1, {**ACTOR, "is_active": 0}, authorize), "usuario inativo nao consulta preferencia")
        Ref(TENANT, "wa_contacts", 1).set({"assigned_to": 99}, merge=True)
        expect_http(403, lambda: change(), "replay revalida acesso apos transferencia")

        seed()
        FAIL_AUDIT = True
        try:
            change()
            raise AssertionError("falha de auditoria deveria abortar")
        except RuntimeError:
            pass
        finally:
            FAIL_AUDIT = False
        check(policy.FIELD not in contact() and not audit_rows(), "auditoria falha nao deixa bloqueio sem recibo")

        seed()
        barrier = threading.Barrier(2)
        seen = threading.local()

        def concurrent_authorize(row, actor, action):
            authorize(row, actor, action)
            if not getattr(seen, "waited", False):
                seen.waited = True
                barrier.wait(timeout=5)

        def concurrent_writer(operation):
            context = common.set_tenant_context(TENANT)
            try:
                try:
                    change(operation=operation, checker=concurrent_authorize)
                    return 200
                except HTTPException as exc:
                    return exc.status_code
            finally:
                common.reset_tenant_context(context)

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(concurrent_writer, "fixture-race-%s" % n) for n in (1, 2)]
            outcomes = sorted(item.result(timeout=10) for item in pending)
        check(outcomes == [200, 409] and len(audit_rows()) == 1,
              "duas escritoras mesma versao: uma confirma e outra conflita apos retry")

        import database_firestore as db  # noqa: E402
        db.document = lambda coll, identifier: Ref(common.get_tenant_context(), coll, identifier)
        existing = contact()
        db._update_existing_wa_contact(
            existing, existing["wa_id"], "", 1, None, "standard", None, True, NOW,
            skip_conversation_upsert=True,
        )
        check(contact()["last_inbound_at"] == NOW and policy.is_commercial_contact_blocked(contact()),
              "caminho real de inbound preserva recusa comercial geral")

        class Query:
            def where(self, field, operator, value):
                self.filter = (field, value)
                return self

            def stream(self):
                result = []
                for key in list(STORE):
                    if key[:2] == (TENANT, "wa_contacts"):
                        snap = Ref(*key).get()
                        if snap.to_dict().get(self.filter[0]) == self.filter[1]:
                            result.append(snap)
                return result

        db.collection = lambda _: Query()
        scan = db.scan_reopen_candidates()
        check(scan["pulados"].get("commercial_contact_blocked") == 1 and not scan["auto_resolve"]
              and not scan["enviaveis"], "scan real exclui bloqueado antes de envio e auto-resolve")

        import scripts.reopen_bot_audience_once as script  # noqa: E402
        script.collection = lambda _: Query()
        script.document = db.document
        script.get_channel = lambda _: (_ for _ in ()).throw(AssertionError("nao resolver canal bloqueado"))
        args = SimpleNamespace(min_cold_hours=24, max_age_days=0, only="", desfecho_link="")
        # Query desta selecao usa operador in; o fixture precisa ser devolvido.
        class ScriptQuery(Query):
            def stream(self):
                return [Ref(TENANT, "wa_contacts", 1).get()]
        script.collection = lambda _: ScriptQuery()
        plan, skipped = script._select(TENANT, args)
        check(not plan and skipped["commercial_contact_blocked"] == 1,
              "script real exclui preferencia no planejamento")
        calls = []
        response = SimpleNamespace(status_code=200)
        http = SimpleNamespace(post=lambda *args, **kwargs: calls.append(True) or response)
        before_send = copy.deepcopy(contact())
        result, reason = script._post_commercial_template(http, "fixture-url", contact_id=1,
                                                        payload={}, headers={})
        check(result is None and reason == "commercial_contact_blocked" and not calls,
              "bloqueio posterior ao plano impede HTTP no ultimo ponto")
        check(contact() == before_send, "pulo antes do HTTP nao altera cooldown/tentativa")
        Ref(TENANT, "wa_contacts", 1).set({policy.FIELD: {"active": False, "version": 2}}, merge=True)
        result, reason = script._post_commercial_template(http, "fixture-url", contact_id=1,
                                                        payload={}, headers={})
        check(result is response and not reason and len(calls) == 1, "preferencia livre permite transporte mockado")
        script.document = lambda *args: (_ for _ in ()).throw(RuntimeError("falha de leitura simulada"))
        result, reason = script._post_commercial_template(http, "fixture-url", contact_id=1,
                                                        payload={}, headers={})
        check(result is None and reason == "preferencia_indisponivel" and len(calls) == 1,
              "falha de leitura nao envia por fallback")

        import scripts.send_template_bulk as bulk  # noqa: E402

        class ContactQuery:
            def __init__(self, tenant):
                self.tenant = tenant
                self.field = None
                self.value = None
                self.maximum = 2

            def where(self, field, operator, value):
                assert operator == "=="
                self.field, self.value = field, value
                return self

            def limit(self, count):
                self.maximum = count
                return self

            def stream(self):
                rows = []
                for key in list(STORE):
                    if key[:2] == (self.tenant, "wa_contacts"):
                        snapshot = Ref(*key).get()
                        if snapshot.to_dict().get(self.field) == self.value:
                            rows.append(snapshot)
                return rows[:self.maximum]

        common.tenant_collection = lambda tenant, _: ContactQuery(tenant)
        seed()
        Ref(TENANT, "wa_contacts", 1).set({"reopen_opt_out": False}, merge=True)
        check(bulk._commercial_recipient_reason(TENANT, "fixture-number") == "",
              "CSV resolve contato unico do tenant com aceite valido")
        check(bulk._commercial_recipient_reason("", "fixture-number") == "tenant_invalido",
              "CSV nao usa tenant implicito na conferencia")
        check(bulk._commercial_recipient_reason("fixture-b", "fixture-number") == "contato_ausente",
              "CSV nao encontra o contato de outro tenant")
        check(bulk._commercial_recipient_reason(TENANT, "fixture-unknown") == "contato_ausente",
              "CSV sem contato nao recebe permissao por numero apenas")
        for fields, reason in (
            ({"lgpd_consent": None}, "consentimento_ausente"),
            ({"lgpd_consent": True, "lgpd_revoked": True}, "lgpd_revogado"),
            ({"lgpd_revoked": False, "reopen_opt_out": True}, "opt_out_retomada"),
            ({"reopen_opt_out": False, policy.FIELD: {"active": True, "version": 1}},
             "commercial_contact_blocked"),
            ({policy.FIELD: None}, "commercial_contact_blocked"),
        ):
            Ref(TENANT, "wa_contacts", 1).set(fields, merge=True)
            check(bulk._commercial_recipient_reason(TENANT, "fixture-number") == reason,
                  "CSV falha fechado: " + reason)
        Ref(TENANT, "wa_contacts", 1).set({policy.FIELD: {"active": False, "version": 2}}, merge=True)
        Ref(TENANT, "wa_contacts", 2).set({**contact(), "id": 2})
        check(bulk._commercial_recipient_reason(TENANT, "fixture-number") == "contato_ambiguo",
              "CSV nao escolhe contato permissivo entre duplicados")
        STORE.pop((TENANT, "wa_contacts", "2"))
        accepted, excluded = bulk.filtrar_destinatarios_comerciais(TENANT, [
            {"wa_id": "fixture-number"}, {"wa_id": "fixture-unknown"}])
        check(len(accepted) == 1 and excluded == {"contato_ausente": 1},
              "dry-run mostra exclusoes sem copiar dados do contato")
        network = []
        bulk.urllib.request.urlopen = lambda *args, **kwargs: network.append(True) or (
            _ for _ in ()).throw(AssertionError("rede proibida"))
        expect_fatal(bulk, lambda: bulk.graph_post(
            "fixture/messages", "fixture-token", {"to": "fixture-number"}, tenant_id=TENANT),
            "transporte legado recusa mesmo contato elegivel sem orcamento comum")
        Ref(TENANT, "wa_contacts", 1).set({policy.FIELD: {"active": True, "version": 3}}, merge=True)
        expect_fatal(bulk, lambda: bulk.enviar_um(
            "fixture-phone-id", "fixture-token", "fixture-number", "fixture-template",
            "pt_BR", 4, 0, tenant_id=TENANT), "chamada direta/retry legado nao contorna recusa geral")
        check(not network, "nenhum POST legado e realizado")
        original_argv = sys.argv
        try:
            for extra in ([], ["--no-resume", "--retry-incertos"], ["--tenant", "hubloc"]):
                sys.argv = ["send_template_bulk", "--test", "--yes", *extra]
                expect_fatal(bulk, bulk.main, "--yes recusado antes de CSV/ADC/preflight mesmo com flags legadas")
        finally:
            sys.argv = original_argv
        check(not network, "CLI bloqueada nao realiza preflight ou envio")
        common.tenant_collection = lambda *args: (_ for _ in ()).throw(RuntimeError("leitura indisponivel"))
        check(bulk._commercial_recipient_reason(TENANT, "fixture-number") == "verificacao_indisponivel",
              "CSV nao libera destinatario quando Firestore falha")
    finally:
        common.reset_tenant_context(token)
    print("\n%s verificacoes locais aprovadas; nenhuma chamada externa." % CHECKS)


if __name__ == "__main__":
    run()
