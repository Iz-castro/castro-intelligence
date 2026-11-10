# -*- coding: utf-8 -*-
"""Integracao REST real do funil, sem ADC, rede ou banco externo.

Router, require_user, autorizador, RBAC, service e repository sao reais
(mesmo fake de Firestore do sim_funnel_flow). Tambem exercita o main.app de
verdade para o que so existe la: no-store por prefixo (inclusive em erro),
client-config, /api/session, a trava do "Ver como" no middleware e o
"Encerrar atendimento" com o desfecho do funil (POST
/api/wa/conversation/{id}/set-attendance com `funnel`, decisao do PO de
28/10): gate sem mover_etapa_funil (inclusive o paciente que volta de
desfecho aberto/perdido), fora do gate (ganho/excluido) exige, 409/422/403
abortam sem fechar nem gravar, legado gravado, thread de backup de contato
vivo no funil e contato backup no legado, linha do usuario relida (role
mudada no cache de auth fecha; inativa = 403), Hub Loc/front antigo
intactos e nenhuma mensagem alem das que o fechamento ja manda. O /config
abre tambem para quem so tem fechar_atendimento_manual (desfechos do modal);
o resto do funil segue exigindo ver_funil.

Rodar na raiz do worktree:
    C:\\Rafael\\castro-intelligence\\.venv\\Scripts\\python.exe tools\\sim_funnel_api.py
"""

import contextlib
import copy
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import tools.sim_funnel_flow as fake  # noqa: E402  (instala o Firestore em memoria)
import config  # noqa: E402
import firebase_admin_client  # noqa: E402
import followup_access as access  # noqa: E402
import followup_repository  # noqa: E402
import followup_routes  # noqa: E402
import funnel_routes as routes  # noqa: E402
import funnel_service as service_module  # noqa: E402
import main  # noqa: E402
import rbac  # noqa: E402
from firestore_common import get_tenant_context, reset_tenant_context, set_tenant_context  # noqa: E402
from followup_repository import FollowupRepository  # noqa: E402
from followup_service import FollowupService  # noqa: E402
from funnel_service import FunnelService  # noqa: E402


TENANT = fake.TENANT
SESSION = {"user": copy.deepcopy(fake.ALICE), "context": TENANT}
CHECKS = [0]
FUNNEL_ONLY = {"id": 7, "firebase_uid": "funnel-only", "tenant_id": TENANT, "role": "operador",
               "perfil_acesso_id": "p_funnel_only", "display_name": "So funil"}
FOLLOWUP_ONLY = {"id": 8, "firebase_uid": "followup-only", "tenant_id": TENANT, "role": "operador",
                 "perfil_acesso_id": "p_followup_only", "display_name": "So follow-up"}
# Encerra atendimento sem ver o funil (decisao do PO: so o /config abre).
CLOSE_ONLY = {"id": 11, "firebase_uid": "close-only", "tenant_id": TENANT, "role": "operador",
              "perfil_acesso_id": "p_close_only", "display_name": "So encerra"}
OTHER_ADMIN = {"id": 1, "firebase_uid": "other-admin", "tenant_id": fake.OTHER_TENANT, "role": "admin",
               "display_name": "Admin de outro tenant"}
SECRET = "SEGREDO-CLINICO-" + "y" * 200
IMPERSONATION = {"by": 3, "sid": "a" * 32, "expires_at": "2026-10-19T17:00:00+00:00",
                 "auth_uid": "imp_ro_" + "a" * 32, "environment": config.FIRESTORE_COLLECTION_PREFIX}
INVALID_REQUEST = {"code": "invalid_request", "message": "Parâmetros inválidos."}
USER_READS = [0]


def check(condition, label):
    CHECKS[0] += 1
    if not condition:
        raise AssertionError(label)
    print("  OK " + label)


def raw_user(user_id):
    USER_READS[0] += 1
    return copy.deepcopy(fake.DATA.get((get_tenant_context(), "users", str(user_id))))


# Lookups implicitos das rotas e o relogio do servico (resto e real).
routes.get_user_raw_by_id = raw_user
routes.FunnelService = lambda repo, user, authorize, catalog, **kwargs: FunnelService(
    repo, user, authorize, catalog, clock=lambda: fake.NOW[0], **kwargs)
followup_routes.get_user_raw_by_id = raw_user
followup_routes.FEATURE_FOLLOWUP = True
followup_routes.tenant_collection = fake.repository_module.tenant_collection
followup_routes.FollowupService = lambda repo, user, authorize, **kwargs: FollowupService(
    repo, user, authorize, clock=lambda: fake.NOW[0], **kwargs)
followup_repository.tenant_collection = lambda tenant, name: fake.Query(tenant, name)
followup_repository.tenant_document = lambda tenant, name, doc_id: fake.Reference(tenant, name, doc_id)
followup_repository.global_document = lambda name, doc_id: fake.Reference(fake.GLOBAL, name, doc_id)
followup_repository.get_firestore_client = lambda: fake.CLIENT
followup_repository.firestore = fake.repository_module.firestore


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


app.include_router(routes.create_funnel_router(current_user, main._require_contact_access))
app.include_router(followup_routes.create_followup_router(current_user, main._require_contact_access))
# O mesmo handler de 422 do main.app (restrito a /api/funnel).
app.add_exception_handler(RequestValidationError, main.request_validation_handler)


def session(user=None, context=None):
    SESSION["user"] = copy.deepcopy(user or fake.ALICE)
    SESSION["context"] = TENANT if context is None else context
    rbac.invalidate_perfil_cache()
    service_module.reset_rate_limits()


def seed():
    fake.seed()
    fake.PROFILES[(TENANT, "p_funnel_only")] = {"toggles": {"ver_funil": True, "gerenciar_followup": False}}
    fake.PROFILES[(TENANT, "p_followup_only")] = {"toggles": {"ver_funil": False, "gerenciar_followup": True,
                                                              "fechar_atendimento_manual": False}}
    fake.PROFILES[(TENANT, "p_close_only")] = {"toggles": {"ver_funil": False, "fechar_atendimento_manual": True,
                                                           "gerenciar_followup": False}}
    for user in (FUNNEL_ONLY, FOLLOWUP_ONLY, CLOSE_ONLY):
        fake.put("users", user["id"], {**user, "is_active": 1})
    fake.put("users", OTHER_ADMIN["id"], {**OTHER_ADMIN, "is_active": 1}, tenant=fake.OTHER_TENANT)
    rbac.invalidate_perfil_cache()
    session()


def call(client, method, path, status=200, code=None, body=None, label="", prefix="/api/funnel", **kwargs):
    response = client.request(method, prefix + path, json=body, **kwargs)
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    actual = detail.get("code") if isinstance(detail, dict) else detail
    check(response.status_code == status and (code is None or actual == code),
          "%s (HTTP %s %s)" % (label or path, response.status_code, actual if response.status_code >= 400 else "ok"))
    return response


def stage_body(to_stage, version, op, **extra):
    return {"to_stage": to_stage, "expected_version": version, "operation_id": op, **extra}


def scenario_gates(client):
    print("\n== require_user: flag, tenant, sessao, usuario e permissao")
    seed()
    config.FEATURE_FUNNEL = False
    call(client, "GET", "/config", 404, "funnel_disabled", label="FEATURE_FUNNEL off = 404")
    call(client, "POST", "/contacts/10/stage", 404, "funnel_disabled", body=stage_body("in_service", 1, "op-off-0001"),
         label="FEATURE_FUNNEL off tambem no POST")
    config.FEATURE_FUNNEL = True
    session(OTHER_ADMIN, context=fake.OTHER_TENANT)
    call(client, "GET", "/config", 404, "funnel_disabled", label="tenant sem funil habilitado = 404")
    session(context=fake.OTHER_TENANT)
    call(client, "GET", "/board", 403, "tenant_mismatch", label="contexto de tenant divergente")
    session({**fake.ALICE, "tenant_id": ""})
    call(client, "GET", "/config", 403, "tenant_mismatch", label="sessao sem tenant")
    session()
    fake.bump("users", 1, is_active=0)
    call(client, "GET", "/config", 403, "user_inactive", label="usuario inativo relido")
    fake.bump("users", 1, is_active=1, firebase_uid="trocado")
    call(client, "GET", "/config", 403, "user_inactive", label="uid trocado revoga a sessao")
    fake.bump("users", 1, firebase_uid="alice", tenant_id=fake.OTHER_TENANT)
    call(client, "GET", "/config", 403, "user_inactive", label="doc do usuario de outro tenant")
    fake.bump("users", 1, tenant_id=TENANT)
    session(FOLLOWUP_ONLY)
    response = call(client, "GET", "/config", 403, label="sem ver_funil nem fechar_atendimento_manual = 403 do RBAC")
    check("ver_funil" in response.text, "403 do RBAC cita a permissao")
    # Decisao do PO: quem encerra atendimento le os desfechos (/config) sem
    # ver o funil; o resto do funil continua exigindo ver_funil.
    session(CLOSE_ONLY)
    check(not rbac.has_permission(CLOSE_ONLY, "ver_funil")
          and rbac.has_permission(CLOSE_ONLY, "fechar_atendimento_manual"), "perfil so-encerra: fecha, nao ve o funil")
    data = call(client, "GET", "/config", label="so fechar_atendimento_manual: /config 200").json()
    outcomes = [s["key"] for s in data["catalog"]["stages"] if s["close_outcome"]]
    check(outcomes == [s["key"] for s in fake.fc.close_outcomes(fake.CATALOG)]
          and data["capabilities"] == {"can_move": False, "can_dashboard": False, "privileged": False,
                                       "followup": False, "can_configure": False, "can_see_agent_contacts": False},
          "/config do so-encerra: desfechos do modal e capacidades reais (nada liberado)")
    for method, path in (("GET", "/board"), ("GET", "/stages/in_service/cards"), ("GET", "/contacts/10"),
                         ("GET", "/contacts/10/stage"), ("GET", "/contacts/10/history"), ("GET", "/dashboard"),
                         ("GET", "/settings"), ("POST", "/contacts/10/stage")):
        response = call(client, method, path, 403, label="so-encerra: %s %s = 403" % (method, path),
                        body=stage_body("in_service", 1, "op-close-only-1") if method == "POST" else None)
        check("ver_funil" in response.text, "so-encerra: %s %s nega por ver_funil" % (method, path))
    writes = len(fake.WRITES)
    for user, label in (({**fake.ALICE, "impersonation": IMPERSONATION}, "Ver como (user['impersonation'] real)"),
                        ({**fake.ALICE, "read_only": True}, "read_only"),
                        ({**fake.ALICE, "impersonating": True}, "impersonating")):
        session(user)
        call(client, "GET", "/config", 403, "read_only_session", label=label + " nega GET")
        call(client, "GET", "/board", 403, "read_only_session", label=label + " nega quadro")
        call(client, "POST", "/contacts/10/stage", 403, "read_only_session",
             body=stage_body("in_service", 1, "op-imp-0001"), label=label + " nega POST")
    check(len(fake.WRITES) == writes, "nenhuma sessao somente leitura grava")
    session({**fake.ALICE, "impersonation": IMPERSONATION})
    call(client, "GET", "/settings", 403, prefix="/api/followup", label="follow-up tambem nega user['impersonation']")
    session()


def scenario_reads(client):
    print("\n== Leituras: config, quadro, colunas, drawer, contexto e mensagens")
    seed()
    fake.QUERY_LOG.clear()
    USER_READS[0] = 0
    data = call(client, "GET", "/config", label="GET /config").json()
    check(data["catalog"]["template"] == "clinic_v1" and not data["capabilities"]["privileged"]
          and data["capabilities"]["can_move"], "config com catalogo e capacidades")
    check(USER_READS[0] == 1 and not [q for q in fake.QUERY_LOG if q["collection"] == "users" and q["kind"] == "get"],
          "usuario relido 1x por request: o servico reaproveita a linha do require_user")
    stages = data["catalog"]["stages"]
    check([s["key"] for s in stages] == [s["key"] for s in fake.CATALOG["stages"]]
          and [s["key"] for s in stages if not s["visible"]] == ["new"]
          and next(s for s in stages if s["key"] == "new")["visibility_permission"] == "ver_contatos_agente_funil"
          and not data["capabilities"]["can_see_agent_contacts"] and not data["capabilities"]["can_configure"]
          and "can_confirm_conversion" not in data["capabilities"],
          "/config lista todas as etapas; Novo contato invisivel para a operadora (sem a permissao)")
    board = call(client, "GET", "/board", label="GET /board").json()
    check("new" not in [column["stage"] for column in board["columns"]],
          "/board da operadora sem a coluna Novo contato (lead com o agente de IA)")
    call(client, "GET", "/stages/new/cards", 404, "unknown_stage", label="coluna Novo contato da operadora = 404")
    in_service = next(column for column in board["columns"] if column["stage"] == "in_service")
    page = call(client, "GET", "/stages/in_service/cards?limit=50&cursor=" + in_service["next_cursor"],
                label="GET /stages/{stage}/cards com cursor do quadro").json()
    check(len(page["cards"]) == 11 and page["next_cursor"] is None
          and not {c["contact_id"] for c in page["cards"]} & {c["contact_id"] for c in in_service["cards"]},
          "pagina seguinte sem repetir o quadro")
    call(client, "GET", "/stages/in_service/cards?cursor=" + in_service["next_cursor"] + "x", 400, "cursor_invalid",
         label="cursor adulterado via HTTP")
    call(client, "GET", "/board?owner_id=2", 403, "owner_filter_forbidden", label="owner_id por operador")
    print("\n== 422 de validacao (query/path) no contrato {code, message}, sem eco")
    for path, label in (("/board?mine=2", "mine fora de 0|1"), ("/board?mine=SEGREDO-mine", "mine nao numerico"),
                        ("/board?order=SEGREDO", "ordem com mais de 4 caracteres"),
                        ("/board?owner_id=0", "owner_id < 1"), ("/stages/new/cards?limit=0", "limit 0"),
                        ("/stages/new/cards?limit=51", "limit acima de 50"),
                        ("/stages/" + "s" * 41 + "/cards", "etapa com mais de 40 caracteres"),
                        ("/contacts/10/messages", "mensagens exigem conversation_id"),
                        ("/contacts/0", "contact_id 0"), ("/contacts/SEGREDO/stage", "contact_id nao numerico"),
                        ("/dashboard?refresh=2", "refresh fora de 0|1"),
                        ("/dashboard?month=SEGREDO-2026", "mes com mais de 7 caracteres")):
        response = call(client, "GET", path, 422, "invalid_request", label="422: " + label)
        check(response.json() == {"detail": INVALID_REQUEST} and "SEGREDO" not in response.text
              and "input" not in response.text and "loc" not in response.text,
              "422 sem eco do input nem loc/ctx (%s)" % label)
    drawer = call(client, "GET", "/contacts/10", label="GET /contacts/{id} (drawer)").json()
    check(set(drawer) == {"contact", "stage", "badges", "signals", "history", "tasks", "suggestions", "capabilities"}
          and set(drawer["contact"]) == {"id", "display_name", "lead_temperature", "lead_temperature_at", "owner",
                                         "bot_completed", "is_archived"}, "drawer no shape do contrato")
    check("5531990000" not in call(client, "GET", "/contacts/10", label="drawer sem telefone").text,
          "drawer nao devolve telefone")
    fake.QUERY_LOG.clear()
    light = call(client, "GET", "/contacts/10/stage", label="GET /contacts/{id}/stage (revalidacao leve)").json()
    check(light == {"stage": drawer["stage"], "version": drawer["stage"]["version"],
                    "can_move": drawer["capabilities"]["can_move"], "write_scope": drawer["capabilities"]["write_scope"]},
          "revalidacao leve: mesma etapa do drawer, versao e acesso")
    check(not [q for q in fake.QUERY_LOG if q["collection"] in ("crm_tasks", "crm_activities", "users")],
          "revalidacao leve sem historico, tarefas nem releitura do usuario (etapa sem motivo)")
    call(client, "GET", "/contacts/12/stage", 404, "out_of_scope", label="revalidacao leve de lead do colega")
    fake.contact(70, "new", display_name="+55 31 99000-0070", declared_name="", whatsapp_profile_name="")
    nameless = call(client, "GET", "/contacts/70", label="drawer de contato sem nome")
    nameless_context = call(client, "GET", "/contacts/70/context", label="contexto de contato sem nome")
    check(nameless.json()["contact"]["display_name"] == "Contato sem nome (final 0070)"
          and nameless_context.json()["contact"]["display_name"] == "Contato sem nome (final 0070)"
          and "99000-0" not in nameless.text + nameless_context.text,
          "contato sem nome: rotulo com o final do numero, sem telefone")
    history = call(client, "GET", "/contacts/10/history", label="GET /contacts/{id}/history").json()
    check(history["items"][-1]["synthetic"] and history["next_cursor"] is None, "historico com entrada sintetica")
    context = call(client, "GET", "/contacts/10/context", label="GET /contacts/{id}/context").json()
    check([row["id"] for row in context["conversations"]] == ["4__10"]
          and set(context["contact"]) == {"id", "display_name", "lead_temperature", "bot_completed", "is_archived"},
          "contexto: threads autorizadas e contato em whitelist")
    messages = call(client, "GET", "/contacts/10/messages?conversation_id=4__10", label="GET mensagens").json()
    check([row["id"] for row in messages["messages"]] == ["m-normal"], "mensagens filtradas no servidor")
    call(client, "GET", "/contacts/10/messages?conversation_id=", 422, "invalid_conversation",
         label="conversation_id vazio chega ao servico (invalid_conversation)")
    print("\n== IDOR por contact_id / conversation_id")
    call(client, "GET", "/contacts/12", 404, "out_of_scope", label="drawer de lead do colega")
    call(client, "GET", "/contacts/12/history", 404, "out_of_scope", label="historico de lead do colega")
    call(client, "GET", "/contacts/12/context", 404, "out_of_scope", label="contexto de lead do colega")
    call(client, "GET", "/contacts/99", 404, "out_of_scope", label="contato de outro tenant")
    call(client, "GET", "/contacts/10/context?conversation_id=6__coex10", 404, "out_of_scope",
         label="thread coex do colega pelo contato da pool")
    call(client, "GET", "/contacts/10/messages?conversation_id=6__coex10", 404, "out_of_scope",
         label="mensagens da thread coex do colega")
    call(client, "GET", "/contacts/10/messages?conversation_id=4__11", 404, "out_of_scope",
         label="thread de outro contato")
    call(client, "GET", "/contacts/12/messages?conversation_id=4__11", 404, "out_of_scope",
         label="mensagens de lead do colega")
    call(client, "POST", "/contacts/12/stage", 404, "out_of_scope",
         body=stage_body("awaiting_followup", 1, "op-idor-0001"), label="mover lead do colega")
    call(client, "POST", "/contacts/14/stage", 403, "out_of_scope_write",
         body=stage_body("awaiting_followup", 1, "op-idor-0002"), label="acesso so-thread nao move")
    check(not fake.WRITES, "IDOR nao grava nada")
    call(client, "GET", "/dashboard", 403, "permission_denied", label="painel exige visao do tenant")
    session(fake.MANAGER)
    dashboard = call(client, "GET", "/dashboard?month=2026-10", label="GET /dashboard (supervisao)").json()
    check(dashboard["month"] == "2026-10" and "cohort" in dashboard and not dashboard["cached"], "painel via HTTP")
    check({"excluded", "entered_net"} <= set(dashboard["cohort"]["month"])
          and all("reached_gross" in row for row in dashboard["cohort"]["month"]["levels"])
          and {"month_triage", "previous_triage"} <= set(dashboard["reasons"]),
          "painel via HTTP com descartados, degraus liquidos/brutos e motivos da triagem")
    call(client, "GET", "/dashboard?month=2026-1", 422, "month_invalid", label="mes invalido")
    for month in ("9999-12", "0001-01", "1999-12", "2026-12"):
        response = call(client, "GET", "/dashboard?month=" + month, 422, "month_invalid",
                        label="mes %s fora da faixa (nunca 500)" % month)
        check(response.headers.get("content-type", "").startswith("application/json"), "422 do mes %s em JSON" % month)
    owner = call(client, "GET", "/board?owner_id=2", label="owner_id pela supervisao").json()
    check({c["contact_id"] for col in owner["columns"] for c in col["cards"]} == {12, 14}, "filtro por dono via HTTP")
    board = call(client, "GET", "/board", label="quadro da supervisao (seed com ver_contatos_agente_funil)").json()
    new = next(column for column in board["columns"] if column["stage"] == "new")
    # 70 = contato sem nome criado acima em Novo contato.
    check(board["columns"][0]["stage"] == "new" and {c["contact_id"] for c in new["cards"]} == {10, 21, 70},
          "supervisao ve a coluna Novo contato")
    check({c["contact_id"] for c in call(client, "GET", "/stages/new/cards",
                                        label="coluna Novo contato da supervisao").json()["cards"]} == {10, 21, 70},
          "supervisao pagina a coluna Novo contato")
    session(fake.SUPNOAGENT)
    call(client, "GET", "/stages/new/cards", 404, "unknown_stage", label="supervisao com o toggle desligado = 404")
    session()
    drawer = call(client, "GET", "/contacts/21", label="drawer de contato em Novo contato (operadora)").json()
    check(drawer["stage"]["key"] == "new", "drawer de contato em etapa invisivel continua (acesso do CRM)")


def scenario_writes(client):
    print("\n== POST /contacts/{id}/stage: contrato, replay e 422 sem eco")
    seed()
    body = stage_body("in_service", 1, "op-http-0001")
    first = call(client, "POST", "/contacts/10/stage", body=body, label="POST muda a etapa").json()
    check(set(first) == {"contact_id", "stage", "replayed", "activity_id"} and not first["replayed"]
          and first["stage"]["key"] == "in_service" and first["stage"]["version"] == 2, "resposta no shape do contrato")
    again = call(client, "POST", "/contacts/10/stage", body=body, label="retry do mesmo POST").json()
    check(again["replayed"] and again["activity_id"] == first["activity_id"], "retry idempotente via HTTP")
    call(client, "POST", "/contacts/11/stage", 409, "operation_reused",
         body=stage_body("awaiting_followup", 1, "op-http-0001"), label="operation_id reusado em outro contato")
    stale = call(client, "POST", "/contacts/10/stage", 409, "stale_version",
                 body=stage_body("awaiting_followup", 1, "op-http-0002"), label="versao antiga via HTTP").json()
    check(stale["detail"]["current"]["version"] == 2 and stale["detail"]["current"]["changed_by_name"] == "Operadora Alice",
          "409 traz a versao atual e quem moveu")
    writes = len(fake.WRITES)
    for label, payload in (
        ("nota longa no motivo Outro", stage_body("non_converted", 2, "op-http-0003", reason="other", reason_note=SECRET)),
        ("campo extra com a nota", stage_body("non_converted", 2, "op-http-0004", reason="other", nota=SECRET)),
        ("faltando operation_id com nota", {"to_stage": "non_converted", "expected_version": 2, "reason": "other",
                                            "reason_note": SECRET}),
        ("corpo nao-objeto", SECRET),
        ("lista com a nota", [SECRET]),
        ("versao como texto", stage_body("non_converted", "2", "op-http-0005", reason="other", reason_note=SECRET)),
        ("nota com tipo errado", stage_body("non_converted", 2, "op-http-0006", reason="other", reason_note=12345)),
        ("operation_id curto", stage_body("non_converted", 2, "op", reason="other", reason_note=SECRET)),
    ):
        response = call(client, "POST", "/contacts/10/stage", 422, body=payload, label="422: " + label)
        check("SEGREDO" not in response.text and "yyyy" not in response.text, "422 nao ecoa a nota (%s)" % label)
    check(len(fake.WRITES) == writes, "nenhum 422 grava")
    note = call(client, "POST", "/contacts/10/stage", 422, "note_invalid", label="code estavel do 422 de nota",
                body=stage_body("non_converted", 2, "op-http-0007", reason="other", reason_note=SECRET)).json()
    check(note["detail"]["message"] and SECRET not in note["detail"]["message"], "mensagem generica do catalogo")
    lost = call(client, "POST", "/contacts/10/stage", label="Nao convertido com motivo e nota curta",
                body=stage_body("non_converted", 2, "op-http-0008", reason="other", reason_note="Prefere outra clinica")).json()
    check(lost["stage"]["reason"]["key"] == "other" and lost["stage"]["reason_note"] == "Prefere outra clinica",
          "autora recebe a nota de volta")
    session(fake.BOB)
    call(client, "POST", "/contacts/10/stage", 403, "permission_denied", body=stage_body("in_service", 3, "op-http-0009"),
         label="operador seed nao move (PO decide)")
    check(call(client, "GET", "/contacts/10", label="colega le o drawer da pool").json()["stage"]["reason_note"] is None,
          "colega nao ve a nota livre")
    session(fake.MANAGER)
    call(client, "POST", "/contacts/15/stage", 409, "contact_unavailable",
         body=stage_body("awaiting_followup", 1, "op-http-0010"), label="backup nao muda de etapa")
    session()
    converted = call(client, "POST", "/contacts/11/stage", label="operadora com mover marca Cliente Agendado",
                     body=stage_body("scheduled", 1, "op-http-0011", appointment_kind="consultation")).json()
    c11 = fake.doc("wa_contacts", 11)
    check(converted["stage"]["key"] == "scheduled" and c11["qualification"] == "convertido"
          and c11["converted_by_user_id"] == 1
          and fake.AUDIT[-1] == (TENANT, 1, "CONTACT_QUALIFY", "Contato 11: convertido (via funil)"),
          "conversao sem permissao propria; legado e quem converteu gravados junto, auditados '(via funil)'")


def scenario_settings(client):
    print("\n== GET/PUT /api/funnel/settings: textos da clinica (gerenciar_config_sistema)")
    seed()
    for user in (fake.ALICE, fake.MANAGER):
        session(user)
        call(client, "GET", "/settings", 403, "permission_denied", label="GET sem gerenciar_config_sistema (%s)"
             % user["firebase_uid"])
        call(client, "PUT", "/settings", 403, "permission_denied", body={"version": 0, "stage_labels": {"new": "X"}},
             label="PUT sem gerenciar_config_sistema (%s)" % user["firebase_uid"])
    check(fake.doc("system_settings", "funnel") is None and not fake.WRITES, "403 nao grava")
    session(fake.ADMIN)
    caps = call(client, "GET", "/config", label="config do admin").json()["capabilities"]
    check(caps["can_configure"] and caps["can_see_agent_contacts"], "admin: can_configure e can_see_agent_contacts")
    view = call(client, "GET", "/settings", label="GET /settings (admin)").json()
    check(view["version"] == 0 and view["template"] == "clinic_v1" and view["stage_labels"] == {}
          and {s["key"] for s in view["stages"]} == {s["key"] for s in fake.CATALOG["stages"]}
          and set(view["reasons"][0]) == {"key", "default_label"}, "GET /settings no shape do contrato")
    body = {"version": 0, "stage_labels": {"scheduled": "Consulta marcada"},
            "stage_descriptions": {"scheduled": "Marcou a primeira consulta."}, "reason_labels": {"price": "Valor"}}
    saved = call(client, "PUT", "/settings", body=body, label="PUT /settings grava").json()
    check(saved["version"] == 1 and saved["stage_labels"] == body["stage_labels"]
          and fake.doc("system_settings", "funnel")["updated_by_uid"] == "admin"
          and fake.AUDIT[-1][2] == "FUNNEL_SETTINGS_UPDATE", "versao 1, autor e auditoria")
    config_view = call(client, "GET", "/config", label="config depois do PUT").json()["catalog"]
    scheduled = next(s for s in config_view["stages"] if s["key"] == "scheduled")
    check(scheduled["label"] == "Consulta marcada" and scheduled["default_label"] == "Cliente Agendado"
          and scheduled["description"] == "Marcou a primeira consulta." and config_view["overrides_version"] == 1,
          "cache invalidado no PUT: /config ja traz os textos da clinica")
    board = call(client, "GET", "/board", label="quadro depois do PUT").json()
    check(next(c for c in board["columns"] if c["stage"] == "scheduled")["label"] == "Consulta marcada",
          "/board com o rotulo novo")
    stale = call(client, "PUT", "/settings", 409, "stale_version", body={"version": 0, "stage_labels": {}},
                 label="PUT com versao antiga").json()
    check(stale["detail"]["current"] == {"version": 1}, "409 traz a versao atual")
    writes = len(fake.WRITES)
    for label, bad, code in (
        ("rotulo longo", {"version": 1, "stage_labels": {"new": SECRET[:41]}}, "overrides_invalid"),
        ("chave desconhecida", {"version": 1, "reason_labels": {"attended": SECRET[:20]}}, "overrides_invalid"),
        ("texto com quebra", {"version": 1, "stage_descriptions": {"new": "a\n" + SECRET[:30]}}, "overrides_invalid"),
        ("campo extra", {"version": 1, "stage_labels": {}, "nota": SECRET}, "invalid_payload"),
        ("versao texto", {"version": "1", "stage_labels": {"new": SECRET[:30]}}, "invalid_payload"),
        ("mapa como lista", {"version": 1, "stage_labels": [SECRET]}, "invalid_payload"),
        ("corpo nao-objeto", SECRET, "invalid_payload"),
    ):
        response = call(client, "PUT", "/settings", 422, code, body=bad, label="422: " + label)
        check("SEGREDO" not in response.text and "yyyy" not in response.text and "input" not in response.text,
              "422 sem eco (%s)" % label)
    check(len(fake.WRITES) == writes and fake.doc("system_settings", "funnel")["version"] == 1, "nenhum 422/409 grava")
    kept = call(client, "PUT", "/settings", body={"version": 1, "reason_labels": None,
                                                  "stage_labels": {"scheduled": ""}},
                label="PUT com mapa nulo e texto vazio").json()
    check(kept["stage_labels"] == {} and kept["reason_labels"] == {"price": "Valor"}
          and kept["stage_descriptions"] == body["stage_descriptions"],
          "mapa nulo/ausente fica como esta; texto vazio volta ao padrao")
    config.FEATURE_FUNNEL = False
    call(client, "GET", "/settings", 404, "funnel_disabled", label="flag desligada = 404 tambem nos textos")
    config.FEATURE_FUNNEL = True
    session()


def scenario_followup(client):
    print("\n== Follow-up: autorizador parametrizado e historico sem eventos do funil")
    seed()
    request = main._require_contact_access
    funnel_auth = access.build_authorizer(TENANT, request, permission="ver_funil")
    followup_auth = access.build_authorizer(TENANT, request)
    check(funnel_auth(10, None, FUNNEL_ONLY)["contact"]["id"] == 10, "ver_funil sem follow-up: autorizador do funil libera")
    try:
        followup_auth(10, None, FUNNEL_ONLY)
        check(False, "autorizador padrao deveria exigir gerenciar_followup")
    except HTTPException as exc:
        check(exc.status_code == 403, "ver_funil sem follow-up: autorizador padrao nega (gerenciar_followup)")
    check(followup_auth(10, None, FOLLOWUP_ONLY)["contact"]["id"] == 10, "follow-up sem funil: autorizador padrao libera")
    try:
        funnel_auth(10, None, FOLLOWUP_ONLY)
        check(False, "autorizador do funil deveria exigir ver_funil")
    except HTTPException as exc:
        check(exc.status_code == 403, "follow-up sem funil: autorizador do funil nega (ver_funil)")
    for bad in ("", None):
        try:
            access.build_authorizer(TENANT, request, permission=bad)
            check(False, "permission vazia deveria falhar")
        except ValueError:
            check(True, "permission %r recusada com ValueError" % (bad,))
    session(FUNNEL_ONLY)
    call(client, "GET", "/settings", 403, prefix="/api/followup", label="so funil nao abre o follow-up")
    check(call(client, "GET", "/config", label="so funil abre o funil").json()["capabilities"]["followup"] is False,
          "capability followup falsa sem gerenciar_followup")
    session()
    call(client, "POST", "/contacts/10/stage", body=stage_body("in_service", 1, "op-fu-0001"), label="evento do funil")
    fake.put("crm_activities", "op_followup_seed", {
        "id": "op_followup_seed", "tenant_id": TENANT, "contact_id": 10, "task_id": "T1", "conversation_id": None,
        "event_type": "task_created", "actor_type": "user", "actor_user_id": 1, "actor_uid": "alice",
        "occurred_at": fake.NOW[0], "recorded_at": fake.NOW[0], "operation_id": "seed", "data": {}})
    items = call(client, "GET", "/contacts/10/activities", prefix="/api/followup",
                 label="historico do follow-up por contato").json()["items"]
    check([row["event_type"] for row in items] == ["task_created"], "rota do follow-up nao devolve crm_stage_*")
    service = FollowupService(FollowupRepository(TENANT), {**fake.ALICE}, followup_auth, clock=lambda: fake.NOW[0])
    rows = service.list_activities({"contact_id": 10, "limit": 50})["activities"]
    check(rows and not [row for row in rows if row["event_type"].startswith("crm_stage_")],
          "FollowupService.list_activities descarta eventos do funil (motivo/nota)")


def scenario_rate(client):
    print("\n== Throttle via HTTP")
    seed()
    service_module.RATE_LIMIT, original = 2, service_module.RATE_LIMIT
    try:
        call(client, "GET", "/board", label="quadro 1")
        call(client, "GET", "/stages/in_service/cards", label="coluna 2")
        call(client, "GET", "/board", 429, "rate_limited", label="3a consulta seguida")
    finally:
        service_module.RATE_LIMIT = original
        service_module.reset_rate_limits()


def scenario_main_app():
    print("\n== main.py: no-store por prefixo, client-config, /api/session e Ver como")
    seed()
    check(not [path for path in (set(main._IMPERSONATE_READ_GETS) | set(main._IMPERSONATE_READ_POSTS)
                                 | set(main._IMPERSONATE_READ_PARAMS)) if path.startswith("/api/funnel")],
          "nenhuma rota /api/funnel nas allowlists do Ver como")
    check(any(getattr(route, "path", "") == "/api/funnel/board" for route in main.app.routes), "router montado no app")
    original_verify = firebase_admin_client.verify_firebase_id_token
    decoded = {"uid": "alice", "tenant_id": TENANT, "role": "operador"}
    firebase_admin_client.verify_firebase_id_token = lambda token: dict(decoded)
    main.app.dependency_overrides[main.get_current_user] = current_user
    headers = {"Authorization": "Bearer sintetico"}
    try:
        # nullcontext: sem lifespan — o startup real (init_database, bootstraps)
        # abriria o cliente Firestore, que este sim proibe de proposito.
        with contextlib.nullcontext(TestClient(main.app)) as client:
            for path, status, label in (("/api/funnel/config", 200, "200"), ("/api/funnel/contacts/12", 404, "404 IDOR"),
                                        ("/api/funnel/stages/nao_existe/cards", 404, "404 etapa")):
                response = client.get(path, headers=headers)
                check(response.status_code == status and response.headers.get("cache-control") == "private, no-store",
                      "no-store em %s (%s)" % (label, path))
            response = client.post("/api/funnel/contacts/10/stage", headers=headers, json={"nota": SECRET})
            check(response.status_code == 422 and response.headers.get("cache-control") == "private, no-store"
                  and "SEGREDO" not in response.text, "no-store e sem eco no 422 pelo app real")
            for path in ("/api/funnel/board?mine=" + SECRET[:30], "/api/funnel/contacts/0/stage",
                         "/api/funnel/dashboard?refresh=" + SECRET[:30]):
                response = client.get(path, headers=headers)
                check(response.status_code == 422 and response.json() == {"detail": INVALID_REQUEST}
                      and response.headers.get("cache-control") == "private, no-store"
                      and "SEGREDO" not in response.text,
                      "main.app: 422 de query/path do funil = invalid_request sem eco (%s)" % path.split("?")[0])
            response = client.get("/api/wa/conversations?limit=0", headers=headers)
            detail = response.json().get("detail")
            check(response.status_code == 422 and isinstance(detail, list) and detail and detail[0].get("loc"),
                  "main.app: fora de /api/funnel o 422 padrao do FastAPI fica inalterado")
            config.FEATURE_FUNNEL = False
            response = client.get("/api/funnel/board", headers=headers)
            check(response.status_code == 404 and response.headers.get("cache-control") == "private, no-store",
                  "no-store no 404 de flag desligada")
            check(client.get("/api/client-config").json()["feature_funnel"] is False, "client-config: feature_funnel false")
            check(client.get("/api/session", headers=headers).json()["funnel"] == {"enabled": False},
                  "/api/session: funil desligado com a flag global")
            config.FEATURE_FUNNEL = True
            check(client.get("/api/client-config").json()["feature_funnel"] is True, "client-config: feature_funnel true")
            check(client.get("/api/session", headers=headers).json()["funnel"] == {"enabled": True},
                  "/api/session: flag + tenant habilitado")
            fake.TENANTS[TENANT]["settings"]["funnel"]["enabled"] = False
            check(client.get("/api/session", headers=headers).json()["funnel"] == {"enabled": False},
                  "/api/session: tenant sem funil habilitado")
            fake.TENANTS[TENANT]["settings"]["funnel"]["enabled"] = True
            main.app.dependency_overrides.pop(main.get_current_user, None)
            response = client.get("/api/funnel/board")
            check(response.status_code == 401 and response.headers.get("cache-control") == "private, no-store",
                  "no-store tambem no 401 sem token (dependencia real)")
            # Token de visualizacao: a trava do middleware nega antes da rota.
            imp = {"uid": "imp_ro_" + "a" * 32, "imp": True, "imp_sid": "a" * 32, "tenant_id": TENANT,
                   "perfil_acesso_id": "op_move", "imp_target_uid": "alice", "imp_by_uid": "manager"}
            firebase_admin_client.verify_firebase_id_token = lambda token: dict(imp)
            patched = {"FEATURE_IMPERSONATE": True, "valid_impersonation_subject": lambda d: True,
                       "validate_impersonation_claims": lambda d: True,
                       "validate_session": lambda d: {"target_user_id": 1, "status": "active"}}
            saved = {name: getattr(main, name) for name in patched}
            for name, value in patched.items():
                setattr(main, name, value)
            try:
                writes = len(fake.WRITES)
                for method, path in (("GET", "/api/funnel/config"), ("GET", "/api/funnel/board"),
                                     ("GET", "/api/funnel/dashboard"), ("POST", "/api/funnel/contacts/10/stage")):
                    response = client.request(method, path, headers=headers,
                                              json=stage_body("in_service", 1, "op-imp-0002") if method == "POST" else None)
                    check(response.status_code == 403 and response.json()["detail"] == "Modo visualizacao: somente leitura"
                          and response.headers.get("cache-control") == "private, no-store",
                          "Ver como bloqueado no middleware: %s %s" % (method, path))
                check(len(fake.WRITES) == writes, "token de visualizacao nao grava")
            finally:
                for name, value in saved.items():
                    setattr(main, name, value)
    finally:
        firebase_admin_client.verify_firebase_id_token = original_verify
        main.app.dependency_overrides.pop(main.get_current_user, None)
        config.FEATURE_FUNNEL = True


class MainDoc:
    """fs_document do main.py sobre o fake (set com merge), registrando."""

    def __init__(self, name, doc_id):
        self.key = (get_tenant_context(), name, str(doc_id))

    def set(self, value, merge=False):
        with fake.LOCK:
            current = fake.DATA.get(self.key) or {}
            fake.DATA[self.key] = fake._deep_merge(current, value) if merge else copy.deepcopy(value)
            fake.REVISIONS[self.key] = fake.REVISIONS.get(self.key, 0) + 1
        MAIN_WRITES.append((self.key, tuple(sorted(value))))


class NoNetwork:
    """httpx.AsyncClient do main.py: qualquer envio (WhatsApp/Meta) e falha."""

    def __init__(self, *args, **kwargs):
        HTTP_CALLS.append("client")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        HTTP_CALLS.append("post")
        raise AssertionError("envio externo proibido no sim")

    async def get(self, *args, **kwargs):
        HTTP_CALLS.append("get")
        raise AssertionError("chamada externa proibida no sim")


class HttpxGuard:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return NoNetwork if name == "AsyncClient" else getattr(self._real, name)


MAIN_WRITES = []
MAIN_AUDIT = []
SYSTEM_MESSAGES = []
PROTOCOL_SENDS = []
HTTP_CALLS = []


def _main_update_qualification(contact_id, qualification, notes=None):
    # Mesma regra de database_firestore.update_wa_contact_qualification.
    fields = {}
    if qualification:
        fields["qualification"] = qualification
    if notes is not None:
        fields["notes"] = notes
    if fields:
        MainDoc("wa_contacts", contact_id).set(fields, merge=True)


def _main_set_status(conversation_id, status, clear_takeover=False):
    MainDoc("wa_conversations", conversation_id).set({"attendance_status": status}, merge=True)


async def _main_protocol(contact, conv, channel, current_user, close_status):
    PROTOCOL_SENDS.append((contact.get("id"), conv.get("id"), close_status))


def scenario_set_attendance():
    print("\n== main.app: POST /api/wa/conversation/{id}/set-attendance com o desfecho do funil")
    seed()
    import channel_service
    import database
    real_close = service_module.close_attendance_outcome
    patched_main = {
        "get_wa_conversation_by_id": fake.conversation_by_id,
        "get_wa_contact": fake.enriched_contact,
        "update_wa_contact_qualification": _main_update_qualification,
        "fs_document": MainDoc,
        "log_audit": lambda user_id, action, detail="", *args, **kwargs: MAIN_AUDIT.append((user_id, action, detail)),
        "set_attendance_status": _main_set_status,
        "insert_transfer_system_message": lambda contact_id, content, *args, **kwargs: SYSTEM_MESSAGES.append(
            (contact_id, kwargs.get("conversation_id"))),
        "_close_daily_and_send_protocol": _main_protocol,
        "_register_personal_tags": lambda *args, **kwargs: None,
        "get_current_protocol_id": lambda contact_id: None,
        "httpx": HttpxGuard(main.httpx),
    }
    saved = {name: getattr(main, name) for name in patched_main}
    saved_tags, saved_channel = database.update_wa_contact_tags, channel_service.get_channel
    original_verify = firebase_admin_client.verify_firebase_id_token
    for name, value in patched_main.items():
        setattr(main, name, value)
    database.update_wa_contact_tags = lambda contact_id, slugs: MainDoc("wa_contacts", contact_id).set(
        {"tags": list(slugs)}, merge=True)
    channel_service.get_channel = fake.channel_by_id
    # Relogio do sim no servico do funil (o resto da funcao e o real).
    service_module.close_attendance_outcome = lambda user, conversation, contact, payload: real_close(
        user, conversation, contact, payload, clock=lambda: fake.NOW[0])
    firebase_admin_client.verify_firebase_id_token = lambda token: {
        "uid": SESSION["user"]["firebase_uid"], "tenant_id": SESSION["context"], "role": SESSION["user"]["role"]}
    main.app.dependency_overrides[main.get_current_user] = current_user
    headers = {"Authorization": "Bearer sintetico"}
    for buffer in (MAIN_WRITES, MAIN_AUDIT, SYSTEM_MESSAGES, PROTOCOL_SENDS, HTTP_CALLS):
        buffer.clear()

    def thread(conv_id, contact_id, owner, tenant=TENANT, **extra):
        fake.put("wa_conversations", conv_id, {"id": conv_id, "contact_id": contact_id, "channel_id": 4,
                                               "assigned_to": owner["id"], "assigned_to_uid": owner["firebase_uid"],
                                               "attendance_status": "aberto", "source_channel_type": "standard",
                                               "unread_count": 0, **extra}, tenant=tenant)

    def funnel(to_stage, version, op, **extra):
        return {"to_stage": to_stage, "expected_version": version, "operation_id": op, "reason": None,
                "reason_note": None, "appointment_kind": None, **extra}

    def post(client, conv_id, body, status=200, code=None, label=""):
        response = client.post("/api/wa/conversation/%s/set-attendance" % conv_id, headers=headers, json=body)
        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith(
            "application/json") else None
        actual = detail.get("code") if isinstance(detail, dict) else None
        check(response.status_code == status and (code is None or actual == code),
              "%s (HTTP %s %s)" % (label, response.status_code, actual or ("ok" if status == 200 else detail)))
        return response

    def attendance(conv_id, tenant=TENANT):
        return (fake.doc("wa_conversations", conv_id, tenant=tenant) or {}).get("attendance_status")

    def counters():
        return (len(MAIN_WRITES), len(MAIN_AUDIT), len(SYSTEM_MESSAGES), len(PROTOCOL_SENDS), len(fake.WRITES),
                len(fake.AUDIT))

    def aborted(before_data, before_counts, conv_id, label):
        check(fake.DATA == before_data and counters() == before_counts and attendance(conv_id) == "aberto",
              "%s: nao fechou, nada gravado, nenhuma mensagem ou auditoria" % label)

    try:
        thread("4__12", 12, fake.BOB)
        thread("4__14", 14, fake.BOB)
        thread("4__19", 19, fake.BOB)
        thread("4__21", 21, fake.BOB, is_backup=True)
        thread("4__11", 11, fake.ALICE)
        thread("4__13", 13, fake.ALICE)
        thread("4__99", 99, OTHER_ADMIN, tenant=fake.OTHER_TENANT)
        thread("4__98", 99, OTHER_ADMIN, tenant=fake.OTHER_TENANT)
        with contextlib.nullcontext(TestClient(main.app)) as client:
            # Gate (legado em_atendimento, etapa nao desfecho): o toggle de
            # fechar cobre; Bob (operador seed) nao tem mover_etapa_funil.
            session(fake.BOB)
            body = {"status": "fechado_manual", "notes": "Marcou avaliação", "tags": ["Varizes"], "tag_labels": {},
                    "funnel": funnel("scheduled", 1, "op-att-0001", appointment_kind="consultation")}
            result = post(client, "4__12", body, label="gate sem mover_etapa_funil: fecha com o desfecho").json()
            c12 = fake.doc("wa_contacts", 12)
            check(set(result) == {"status", "attendance_status", "funnel"} and result["status"] == "ok"
                  and result["attendance_status"] == "fechado_manual" and result["funnel"]["stage"]["key"] == "scheduled"
                  and result["funnel"]["stage"]["version"] == 2
                  and result["funnel"]["stage"]["appointment_kind"] == "consultation",
                  "resposta = a de hoje + funnel.stage")
            check(attendance("4__12") == "fechado_manual" and c12[fake.fc.F_STAGE] == "scheduled"
                  and c12["qualification"] == "convertido" and c12["converted_by_user_id"] == 2
                  and c12["notes"] == "Marcou avaliação" and c12["tags"] == ["varizes"],
                  "fechou; etapa + legado 'convertido' + quem converteu; notas e tags como hoje")
            activity = fake.doc("crm_activities", fake.receipt("bob", 12, "op-att-0001"))
            check(activity and activity["data"]["via"] == "close" and activity["data"]["legacy_qualification"] == "convertido",
                  "Activity do encerramento com data.via='close'")
            check(("wa_contacts", ("notes",)) in [(key[1], fields) for key, fields in MAIN_WRITES]
                  and not [fields for key, fields in MAIN_WRITES if "qualification" in fields or "converted_by_user_id" in fields],
                  "endpoint grava so notas/tags: qualification nunca sobrescrita fora da transacao do funil")
            check([entry[1] for entry in MAIN_AUDIT] == ["CONTACT_TAGS", "ATTENDANCE_SET_STATUS"]
                  and fake.AUDIT[-1] == (TENANT, 2, "CONTACT_QUALIFY", "Contato 12: convertido (no encerramento, via funil)"),
                  "auditoria: legado pelo funil '(no encerramento, via funil)'; sem o CONTACT_QUALIFY legado")
            check(SYSTEM_MESSAGES == [(12, "4__12")] and PROTOCOL_SENDS == [(12, "4__12", "fechado_manual")] and not HTTP_CALLS,
                  "so as mensagens de hoje (aviso interno + protocolo); nenhum envio a mais")
            # Retry do mesmo fechamento (mesmo operation_id): replay e fecha de novo.
            fake.bump("wa_conversations", "4__12", attendance_status="aberto")
            writes = len(fake.WRITES)
            again = post(client, "4__12", body, label="retry do mesmo fechamento").json()
            check(again["funnel"]["stage"]["version"] == 2 and len(fake.WRITES) == writes
                  and attendance("4__12") == "fechado_manual", "replay idempotente: etapa nao regravada, fechamento segue")
            # Fora do gate: etapa de desfecho + legado terminal.
            fake.bump("wa_contacts", 14, qualification="convertido")
            before, counts = copy.deepcopy(fake.DATA), counters()
            post(client, "4__14", {"status": "fechado_manual", "notes": "nao gravar",
                                   "funnel": funnel("non_converted", 1, "op-att-0002", reason="price")},
                 403, "permission_denied", label="fora do gate sem mover_etapa_funil = 403")
            aborted(before, counts, "4__14", "403 fora do gate")
            # 409 stale_version aborta antes de qualquer escrita (notas e tags incluidas).
            before, counts = copy.deepcopy(fake.DATA), counters()
            stale = post(client, "4__19", {"status": "fechado_manual", "notes": "nao gravar", "tags": ["x"],
                                           "funnel": funnel("scheduled", 0, "op-att-0003")},
                         409, "stale_version", label="versao antiga = 409").json()
            check(stale["detail"]["current"]["stage"] == "in_service" and stale["detail"]["current"]["version"] == 1,
                  "409 traz a etapa atual (o front reaplica)")
            aborted(before, counts, "4__19", "409 stale_version")
            for label, payload, code in (
                ("desfecho que nao e de encerramento", {"status": "fechado_manual",
                                                         "funnel": funnel("in_service", 1, "op-att-0004")},
                 "stage_not_allowed"),
                ("motivo obrigatorio", {"status": "fechado_manual", "funnel": funnel("non_converted", 1, "op-att-0005")},
                 "reason_required"),
                ("funnel com campo extra", {"status": "fechado_manual",
                                            "funnel": dict(funnel("scheduled", 1, "op-att-0006"), nota=SECRET)},
                 "invalid_payload"),
                ("funnel na reabertura", {"status": "aberto", "funnel": funnel("scheduled", 1, "op-att-0007")},
                 "invalid_payload"),
            ):
                before, counts = copy.deepcopy(fake.DATA), counters()
                response = post(client, "4__19", payload, 422, code, label="422: " + label)
                check("SEGREDO" not in response.text, "422 sem eco (%s)" % label)
                aborted(before, counts, "4__19", "422 " + label)
            # Sem funnel (front antigo): gate legado intacto.
            before, counts = copy.deepcopy(fake.DATA), counters()
            post(client, "4__19", {"status": "fechado_manual"}, 400, label="sem funnel e sem desfecho: 400 legado")
            aborted(before, counts, "4__19", "400 legado")
            # Thread de backup de contato VIVO: o contato segue no funil (etapa
            # + legado pela transacao), como qualquer thread.
            check(not fake.doc("wa_contacts", 21).get("is_backup"), "21 e contato vivo (a thread 4__21 e de backup)")
            audit_before = len(MAIN_AUDIT)
            backup = post(client, "4__21", {"status": "fechado_manual", "notes": "backup",
                                            "funnel": funnel("scheduled", 1, "op-att-0008")},
                          label="thread de backup de contato vivo com funnel").json()
            c21 = fake.doc("wa_contacts", 21)
            check(backup["funnel"]["stage"]["key"] == "scheduled" and backup["funnel"]["stage"]["version"] == 2
                  and c21["qualification"] == "convertido" and c21[fake.fc.F_STAGE] == "scheduled"
                  and c21[fake.fc.F_VERSION] == 2 and c21["notes"] == "backup"
                  and attendance("4__21") == "fechado_manual"
                  and [entry[1] for entry in MAIN_AUDIT[audit_before:]] == ["ATTENDANCE_SET_STATUS"]
                  and fake.AUDIT[-1] == (TENANT, 2, "CONTACT_QUALIFY", "Contato 21: convertido (no encerramento, via funil)"),
                  "thread de backup de contato vivo: etapa + legado pela transacao do funil (nada pelo caminho antigo)")
            # CONTATO backup: fora do funil, o desfecho vale so no legado (como o modal antigo).
            thread("4__15", 15, fake.BOB, is_backup=True)
            stage15 = {key: value for key, value in fake.doc("wa_contacts", 15).items() if key.startswith("crm_")}
            legacy_backup = post(client, "4__15", {"status": "fechado_manual",
                                                   "funnel": funnel("scheduled", 1, "op-att-0015")},
                                 label="contato backup com funnel").json()
            c15 = fake.doc("wa_contacts", 15)
            check(legacy_backup["funnel"] == {"stage": None} and c15["qualification"] == "convertido"
                  and {key: value for key, value in c15.items() if key.startswith("crm_")} == stage15
                  and MAIN_AUDIT[-2] == (2, "CONTACT_QUALIFY", "Contato 15: convertido (no encerramento)"),
                  "contato backup: legado gravado pelo caminho antigo; etapa intocada")
            # Decisao do PO: paciente ja classificado que volta (desfecho de kind
            # aberto/perdido com o legado terminal): o toggle de fechar cobre.
            for cid, stage_key in ((80, "awaiting_followup"), (81, "non_converted")):
                fake.contact(cid, stage_key, qualification="nao_convertido", assigned_to=2, assigned_to_uid="bob")
                thread("4__%d" % cid, cid, fake.BOB)
                result = post(client, "4__%d" % cid, {"status": "fechado_manual", "funnel": funnel(
                    "scheduled", 1, "op-att-back%d" % cid, appointment_kind="consultation")},
                    label="%s com legado terminal: Bob (sem mover) encerra como Cliente Agendado" % stage_key).json()
                row = fake.doc("wa_contacts", cid)
                check(result["funnel"]["stage"]["key"] == "scheduled" and row[fake.fc.F_STAGE] == "scheduled"
                      and row["qualification"] == "convertido" and row["converted_by_user_id"] == 2
                      and attendance("4__%d" % cid) == "fechado_manual",
                      "paciente que volta de %s: 200, etapa Cliente Agendado e legado convertido" % stage_key)
            fake.contact(82, "loyal", qualification="convertido", assigned_to=2, assigned_to_uid="bob")
            fake.contact(83, "disqualified", qualification="nao_qualificado", assigned_to=2, assigned_to_uid="bob")
            for conv_id, stage_key, target in (("4__14", "scheduled", "loyal"), ("4__82", "loyal", "scheduled"),
                                               ("4__83", "disqualified", "scheduled")):
                if conv_id != "4__14":
                    thread(conv_id, int(conv_id[3:]), fake.BOB)
                row = fake.doc("wa_contacts", int(conv_id[3:]))
                check(row[fake.fc.F_STAGE] == stage_key and row["qualification"] in ("convertido", "nao_qualificado"),
                      "%s com legado terminal" % stage_key)
                before, counts = copy.deepcopy(fake.DATA), counters()
                post(client, conv_id, {"status": "fechado_manual", "funnel": funnel(
                    target, fake.repository_module.stage_version(row), "op-att-out%s" % conv_id[3:])},
                     403, "permission_denied", label="%s: trocar para %s sem mover_etapa_funil = 403" % (stage_key, target))
                aborted(before, counts, conv_id, "403 %s" % stage_key)
            # Decisao do PO: quem so encerra (sem ver_funil) fecha com o desfecho.
            session(CLOSE_ONLY)
            fake.contact(84, "in_service", assigned_to=11, assigned_to_uid="close-only")
            thread("4__84", 84, CLOSE_ONLY)
            closer = post(client, "4__84", {"status": "fechado_manual", "funnel": funnel("scheduled", 1, "op-att-0084")},
                          label="so-encerra (sem ver_funil) no caso do gate: fecha com o desfecho").json()
            c84 = fake.doc("wa_contacts", 84)
            check(closer["funnel"]["stage"]["key"] == "scheduled" and c84[fake.fc.F_STAGE] == "scheduled"
                  and c84["qualification"] == "convertido" and c84["converted_by_user_id"] == 11
                  and attendance("4__84") == "fechado_manual",
                  "so-encerra: etapa + legado gravados pela transacao do funil")
            # current_user do cache de auth (ate ~45 s) com a role velha: o
            # encerramento rele a linha do usuario (sem 403 user_inactive).
            session(fake.BOB)
            fake.bump("users", 2, role="supervisor")
            fake.contact(85, "in_service", assigned_to=2, assigned_to_uid="bob")
            thread("4__85", 85, fake.BOB)
            post(client, "4__85", {"status": "fechado_manual", "funnel": funnel("scheduled", 1, "op-att-0085")},
                 label="role mudou depois do cache de auth: fecha")
            check(fake.doc("wa_contacts", 85)[fake.fc.F_STAGE] == "scheduled" and attendance("4__85") == "fechado_manual",
                  "role nova: etapa gravada e atendimento fechado")
            fake.bump("users", 2, role="operador", is_active=0)
            fake.contact(86, "in_service", assigned_to=2, assigned_to_uid="bob")
            thread("4__86", 86, fake.BOB)
            before, counts = copy.deepcopy(fake.DATA), counters()
            post(client, "4__86", {"status": "fechado_manual", "notes": "nao gravar",
                                   "funnel": funnel("scheduled", 1, "op-att-0086")},
                 403, "user_inactive", label="linha do usuario inativa = 403")
            aborted(before, counts, "4__86", "403 user_inactive")
            fake.bump("users", 2, is_active=1)
            # Operadora com mover (Alice): Nao convertido com motivo Outro e nota.
            session(fake.ALICE)
            lost = post(client, "4__11", {"status": "fechado_manual", "funnel": funnel(
                "non_converted", 1, "op-att-0009", reason="other", reason_note="Prefere outra clínica")},
                label="Nao convertido com nota no encerramento").json()
            c11 = fake.doc("wa_contacts", 11)
            check(lost["funnel"]["stage"]["reason"]["key"] == "other"
                  and lost["funnel"]["stage"]["reason_note"] == "Prefere outra clínica"
                  and c11["qualification"] == "nao_convertido" and "Prefere" not in json_dump(c11),
                  "legado 'nao_convertido' gravado; a nota fica so na Activity")
            # Sem funnel no corpo: comportamento legado intacto.
            activities = len([key for key in fake.DATA if key[1] == "crm_activities"])
            stage_before = {key: value for key, value in fake.doc("wa_contacts", 13).items() if key.startswith("crm_")}
            legacy = post(client, "4__13", {"status": "fechado_manual", "qualification": "nao_convertido",
                                            "notes": "legado"}, label="sem funnel (front antigo)").json()
            c13 = fake.doc("wa_contacts", 13)
            check(legacy == {"status": "ok", "attendance_status": "fechado_manual"}
                  and c13["qualification"] == "nao_convertido" and c13["notes"] == "legado"
                  and {key: value for key, value in c13.items() if key.startswith("crm_")} == stage_before
                  and len([key for key in fake.DATA if key[1] == "crm_activities"]) == activities
                  and MAIN_AUDIT[-2] == (1, "CONTACT_QUALIFY", "Contato 13: nao_convertido (no encerramento)"),
                  "sem funnel: legado gravado como hoje, etapa e Activities intocadas, resposta sem funnel")
            # Tenant sem funil (Hub Loc): legado intacto; com funnel = 409 sem fechar.
            session(OTHER_ADMIN, context=fake.OTHER_TENANT)
            other_before = {key: value for key, value in fake.doc("wa_contacts", 99, tenant=fake.OTHER_TENANT).items()
                            if key.startswith("crm_")}
            hub = post(client, "4__99", {"status": "fechado_manual", "qualification": "convertido"},
                       label="tenant sem funil: fechamento legado").json()
            c99 = fake.doc("wa_contacts", 99, tenant=fake.OTHER_TENANT)
            check(hub == {"status": "ok", "attendance_status": "fechado_manual"} and c99["qualification"] == "convertido"
                  and c99["converted_by_user_id"] == 1
                  and {key: value for key, value in c99.items() if key.startswith("crm_")} == other_before
                  and attendance("4__99", tenant=fake.OTHER_TENANT) == "fechado_manual",
                  "tenant sem funil: legado gravado como hoje (inclusive quem converteu), nada do funil")
            before, counts = copy.deepcopy(fake.DATA), counters()
            post(client, "4__98", {"status": "fechado_manual", "funnel": funnel("scheduled", 1, "op-att-0010")},
                 409, "funnel_disabled", label="tenant sem funil com funnel no corpo = 409")
            check(fake.DATA == before and counters() == counts
                  and attendance("4__98", tenant=fake.OTHER_TENANT) == "aberto",
                  "409 funnel_disabled: nao fecha e nao grava")
            check(not HTTP_CALLS and len(SYSTEM_MESSAGES) == len(PROTOCOL_SENDS) == 11,
                  "11 fechamentos = 11 avisos internos + 11 protocolos (os de hoje); nenhum envio externo extra")
    finally:
        for name, value in saved.items():
            setattr(main, name, value)
        database.update_wa_contact_tags, channel_service.get_channel = saved_tags, saved_channel
        service_module.close_attendance_outcome = real_close
        firebase_admin_client.verify_firebase_id_token = original_verify
        main.app.dependency_overrides.pop(main.get_current_user, None)
        config.FEATURE_FUNNEL = True
        session()


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def run():
    print("Funil API: router, require_user, autorizador, RBAC, service e repository reais")
    with TestClient(app) as client:
        scenario_gates(client)
        scenario_reads(client)
        scenario_writes(client)
        scenario_settings(client)
        scenario_followup(client)
        scenario_rate(client)
    scenario_main_app()
    scenario_set_attendance()
    print("\n%d verificacoes REST passaram; nenhum ADC/rede/banco externo." % CHECKS[0])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        print("\nFALHA depois de %d verificacoes." % CHECKS[0])
        sys.exit(1)
