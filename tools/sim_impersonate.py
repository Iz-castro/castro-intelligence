# -*- coding: utf-8 -*-

"""Simulador LOCAL do Ver como (ADR 0014), sem startup nem acesso externo.

Exercita main.py, auth.py, rbac.py e os lookups reais de usuarios com
Firestore em memoria. Assinatura e verificacao Firebase sao stubadas;
qualquer tentativa de usar cliente Firestore ou socket real falha.

Rodar na worktree:
    C:\\Rafael\\castro-intelligence\\.venv\\Scripts\\python.exe tools\\sim_impersonate.py

Sai com 0 quando todos os asserts passam, 1 caso contrario.
"""

import asyncio
from contextlib import closing, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import HTTPException, Request  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from firebase_admin import auth as firebase_auth  # noqa: E402
import httpx  # noqa: E402

import auth  # noqa: E402
import config  # noqa: E402
import channel_service  # noqa: E402
import database_firestore as dbf  # noqa: E402
import firebase_admin_client as fac  # noqa: E402
import firestore_common as fsc  # noqa: E402
import main  # noqa: E402
import impersonation  # noqa: E402
import impersonation_views  # noqa: E402
import monitor_service  # noqa: E402
import pending_events  # noqa: E402
import rbac  # noqa: E402
import tenant_service  # noqa: E402
import superadmin_main  # noqa: E402

TENANT = "sim-tenant"
OTHER_TENANT = "sim-other"
ENVIRONMENT = config.FIRESTORE_COLLECTION_PREFIX
SID = "a" * 32
ADMIN = {
    "id": 1, "username": "admin_sim", "display_name": "Admin Sim",
    "role": "admin", "firebase_uid": "uid-admin-sim", "is_active": 1,
    "email": "admin@example.invalid", "tenant_id": TENANT,
    "perfil_acesso_id": "perfil_admin",
}
TARGET = {
    "id": 2, "username": "alvo_sim", "display_name": "Alvo Sim",
    "role": "supervisor", "firebase_uid": "uid-target-sim", "is_active": 1,
    "email": "target@example.invalid", "tenant_id": TENANT,
    "perfil_acesso_id": "perfil_sim_custom", "last_login": None,
}
REASON = "Verificar visibilidade da conversa"
CUSTOM_TOKEN = "custom-token-somente-simulado"
STORE = {}
WRITES = []
AUDITS = []
SIGNED = []
TOKENS = {}
CLAIMS = {}
DELETED = []
DELETE_ERRORS = {}
QUERIES = []
FAILS = []
CHECKS = 0
EVENT_LOOP = None


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"      OK {label}")
    else:
        FAILS.append(label)
        print(f"      FALHOU {label}")


def title(label):
    print("\n" + "=" * 68)
    print(label)
    print("=" * 68)


def no_external(*args, **kwargs):
    raise AssertionError("Simulador tentou acesso externo")


def bucket(name, tenant=None):
    tid = tenant if tenant is not None else (fsc.get_tenant_context() or "")
    return STORE.setdefault((tid, name), {})


class Snapshot:
    def __init__(self, ref, value):
        self.reference = ref
        self.id = ref.id
        self.exists = value is not None
        self._value = deepcopy(value)

    def to_dict(self):
        return deepcopy(self._value)


class Document:
    def __init__(self, name, doc_id, tenant=None):
        self.name = name
        self.id = str(doc_id)
        self.tenant = tenant if tenant is not None else (fsc.get_tenant_context() or "")

    def get(self):
        return Snapshot(self, bucket(self.name, self.tenant).get(self.id))

    def set(self, value, merge=False):
        WRITES.append((self.name, self.id, deepcopy(value)))
        docs = bucket(self.name, self.tenant)
        if merge:
            docs.setdefault(self.id, {}).update(deepcopy(value))
        else:
            docs[self.id] = deepcopy(value)

    def update(self, value):
        if self.id not in bucket(self.name, self.tenant):
            from google.api_core.exceptions import NotFound
            raise NotFound("Documento simulado ausente")
        self.set(value, merge=True)

    def create(self, value):
        if self.id in bucket(self.name, self.tenant):
            from google.api_core.exceptions import AlreadyExists
            raise AlreadyExists("Documento simulado ja existe")
        self.set(value)


class Collection:
    def __init__(self, name):
        self.name = name
        self.tenant = fsc.get_tenant_context() or ""
        self.filters = []
        self.orders = []
        self.cap = None

    def _clone(self):
        query = Collection(self.name)
        query.tenant = self.tenant
        query.filters = list(self.filters)
        query.orders = list(self.orders)
        query.cap = self.cap
        if self.orders:
            query.order = self.orders[0]
        return query

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = "sim-auto-" + str(len(bucket(self.name, self.tenant)) + 1)
        return Document(self.name, doc_id, self.tenant)

    def where(self, field, op, value):
        assert op in ("==", "!=", "<=", ">", "in"), "Operador nao previsto no mock"
        query = self._clone()
        query.filters.append((field, op, value))
        return query

    def order_by(self, field, direction="ASCENDING"):
        query = self._clone()
        query.orders.append((field, str(direction).upper().startswith("DESC")))
        query.order = query.orders[0]
        return query

    def limit(self, cap):
        query = self._clone()
        query.cap = cap
        return query

    def stream(self):
        QUERIES.append((self.tenant, self.name, deepcopy(self.filters),
                        getattr(self, "order", None), self.cap))
        emitted = 0
        rows = list(bucket(self.name, self.tenant).items())
        for field, reverse in reversed(self.orders):
            rows = [(doc_id, value) for doc_id, value in rows if field in value]
            rows.sort(key=lambda row: (row[1].get(field) is not None, row[1].get(field)), reverse=reverse)
        for doc_id, value in rows:
            def matches(field, op, expected):
                if field not in value:
                    return False
                got = value.get(field)
                if op == "==":
                    return got == expected
                if op == "!=":
                    return got is not None and got != expected
                if op == "in":
                    return got in expected
                if op == ">":
                    return got is not None and got > expected
                return got is not None and got <= expected
            if all(matches(*condition) for condition in self.filters):
                yield Snapshot(Document(self.name, doc_id, self.tenant), value)
                emitted += 1
                if self.cap is not None and emitted >= self.cap:
                    break


def audit(user_id, action, details, *args, **kwargs):
    record = {"user_id": user_id, "action": action, "details": details,
              "strict": kwargs.get("strict", False)}
    AUDITS.append(record)
    dbf.log_audit(user_id, action, details, *args, **kwargs)


def sync_identity(user_id, **fields):
    Document("users", user_id).set(fields, merge=True)


def last_login(user_id):
    Document("users", user_id).set({"last_login": datetime.now(timezone.utc)}, merge=True)


def claims_write(*args, **kwargs):
    WRITES.append(("firebase_claims", args, kwargs))


def verify_token(id_token, **kwargs):
    if id_token not in TOKENS:
        raise ValueError("Token simulado desconhecido")
    return deepcopy(TOKENS[id_token])


def sign_token(uid, developer_claims, **kwargs):
    SIGNED.append((uid, deepcopy(developer_claims)))
    return CUSTOM_TOKEN.encode("utf-8")


def delete_user(uid, **kwargs):
    DELETED.append(uid)
    error = DELETE_ERRORS.get(uid)
    if error is not None:
        raise error


def list_tenants(active_only=True):
    rows = [{"id": TENANT, "is_active": True}, {"id": OTHER_TENANT, "is_active": False}]
    return [row for row in rows if row["is_active"]] if active_only else rows


def temp_uid(sid=SID, environment=ENVIRONMENT):
    return "imp_ro_" + sha256(environment.encode("utf-8")).hexdigest()[:8] + "_" + sid


def seed_session(sid=SID, tenant=TENANT, **changes):
    created = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp()), timezone.utc)
    ttl = auth.IMPERSONATE_TTL_MINUTES * 60
    session = {
        "sid": sid,
        "auth_uid": temp_uid(sid), "target_uid": TARGET["firebase_uid"], "target_user_id": TARGET["id"],
        "admin_uid": ADMIN["firebase_uid"], "admin_user_id": ADMIN["id"], "tenant_id": tenant,
        "environment": ENVIRONMENT, "role_at_start": TARGET["role"],
        "perfil_acesso_id_at_start": TARGET["perfil_acesso_id"], "ttl_seconds": ttl,
        "created_at": created, "expires_at": datetime.fromtimestamp(created.timestamp() + ttl, timezone.utc),
        "cleanup_after": datetime.fromtimestamp(created.timestamp() + 7200, timezone.utc), "status": "active",
    }
    session.update(changes)
    bucket("impersonation_sessions", tenant)[sid] = session
    return session


def decoded_imp(**changes):
    now = int(datetime.now(timezone.utc).timestamp())
    session = bucket("impersonation_sessions").get(SID) or {}
    decoded = {
        "uid": temp_uid(), "tenant_id": TENANT, "imp_env": ENVIRONMENT,
        "imp_target_uid": TARGET["firebase_uid"],
        "role": TARGET["role"], "perfil_acesso_id": TARGET["perfil_acesso_id"],
        "imp": True, "imp_by": ADMIN["id"], "imp_by_uid": ADMIN["firebase_uid"],
        "imp_sid": SID, "imp_exp": int(session["expires_at"].timestamp()) if session else now + auth.IMPERSONATE_TTL_MINUTES * 60,
        "auth_time": now,
    }
    decoded.update(changes)
    return decoded


def decoded_normal(user=None):
    user = user or TARGET
    return {"uid": user["firebase_uid"], "email": user["email"], "name": user["display_name"],
            "tenant_id": user["tenant_id"], "role": user["role"],
            "perfil_acesso_id": user["perfil_acesso_id"],
            "auth_time": int(datetime.now(timezone.utc).timestamp())}


def reset():
    STORE.clear()
    WRITES.clear()
    AUDITS.clear()
    SIGNED.clear()
    TOKENS.clear()
    CLAIMS.clear()
    DELETED.clear()
    DELETE_ERRORS.clear()
    QUERIES.clear()
    auth.invalidate_auth_cache()
    rbac.invalidate_perfil_cache()
    fsc.set_tenant_context(TENANT)
    bucket("users")[str(ADMIN["id"])] = deepcopy(ADMIN)
    bucket("users")[str(TARGET["id"])] = deepcopy(TARGET)
    bucket("operator_profiles")[TARGET["firebase_uid"]] = {
        "uid": TARGET["firebase_uid"], "user_id": TARGET["id"], "role": TARGET["role"],
        "perfil_acesso_id": TARGET["perfil_acesso_id"], "is_active": 1,
    }
    bucket("users", OTHER_TENANT)["99"] = dict(TARGET, id=99, tenant_id=OTHER_TENANT)
    bucket("perfis_acesso")["perfil_sim_custom"] = {
        "id": "perfil_sim_custom", "role_equivalente": "supervisor",
        "toggles": {"ver_todos_leads": True, "gerenciar_usuarios": True,
                    "ver_dashboard_uso": False, "ver_como_usuario": False},
    }
    CLAIMS[TARGET["firebase_uid"]] = {
        "tenant_id": TENANT, "role": TARGET["role"],
        "perfil_acesso_id": TARGET["perfil_acesso_id"],
        "super_admin": True, "extra_claim": "nao-copiar",
    }
    seed_session()
    main.FEATURE_IMPERSONATE = True


def request(method="POST", path="/api/admin/impersonate", token=None, decoded=None):
    headers = [] if token is None else [(b"authorization", ("Bearer " + token).encode())]
    req = Request({"type": "http", "method": method, "path": path,
                   "headers": headers, "query_string": b"", "scheme": "http",
                   "server": ("sim.local", 80), "client": ("127.0.0.1", 12345)})
    if decoded is not None:
        req.state.firebase_decoded = decoded
    return req


def start(user_id=2, reason=REASON, user=None, decoded=None):
    return EVENT_LOOP.run_until_complete(main.admin_impersonate(
        body=main.ImpersonateRequest(user_id=user_id, reason=reason),
        request=request(decoded=decoded), current_user=deepcopy(user or ADMIN),
    ))


def expect_http(call, expected, label):
    try:
        call()
    except HTTPException as exc:
        check(exc.status_code == expected, f"{label} (HTTP {exc.status_code})")
        return exc
    check(False, f"{label}: nao levantou HTTPException")
    return None


def scenario_start():
    title("CENARIO 1 - Inicio, claims e auditoria")
    reset()
    before = int(datetime.now(timezone.utc).timestamp())
    result = start(reason="  " + REASON + "  ")
    uid, claims = SIGNED[0]
    check(uid == temp_uid(result["session_id"]) and uid not in (TARGET["firebase_uid"], ADMIN["firebase_uid"]),
          "custom token emitido para identidade temporaria diferente do admin/alvo")
    check(result["custom_token"] == CUSTOM_TOKEN, "bytes da assinatura convertidos para texto")
    check(claims["tenant_id"] == TENANT and claims["role"] == TARGET["role"]
          and claims["perfil_acesso_id"] == TARGET["perfil_acesso_id"],
          "claims copiam tenant/role/perfil custom do alvo")
    check(claims["imp_target_uid"] == TARGET["firebase_uid"] and claims["imp_env"] == ENVIRONMENT,
          "claims vinculam alvo e ambiente sem trocar identidade Firebase")
    check(not {"email", "name", "phone_number", "password", "providers"}.intersection(claims),
          "nenhuma PII ou credencial do alvo e copiada para Auth")
    check(claims["imp"] is True and claims["imp_by"] == ADMIN["id"]
          and claims["imp_by_uid"] == ADMIN["firebase_uid"], "claims identificam solicitante")
    check(claims["imp_sid"] == result["session_id"] and len(claims["imp_sid"]) == 32,
          "sid unico hex presente na resposta e no token")
    check(before + config.IMPERSONATE_TTL_MINUTES * 60 <= claims["imp_exp"]
          <= before + config.IMPERSONATE_TTL_MINUTES * 60 + 2, "TTL do config carimbado em imp_exp")
    check(int(datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00")).timestamp())
          == claims["imp_exp"], "expires_at corresponde ao claim")
    reserved = {"acr", "amr", "at_hash", "aud", "auth_time", "azp", "cnf", "c_hash", "exp",
                "firebase", "iat", "iss", "jti", "nbf", "nonce", "sub"}
    check(not reserved.intersection(claims) and "extra_claim" not in claims
          and "super_admin" not in claims, "allowlist de claims nao copia reservados nem privilegios extras")
    check(result["target"] == {"id": TARGET["id"], "display_name": TARGET["display_name"],
                               "role": TARGET["role"]}, "resposta contem alvo minimo")
    check(len(AUDITS) == 1 and AUDITS[0]["user_id"] == ADMIN["id"]
          and AUDITS[0]["action"] == "IMPERSONATE_START", "auditoria atribuida ao admin antes da resposta")
    check(AUDITS[0]["strict"] is True, "emissao exige persistencia estrita da auditoria")
    persisted = list(bucket("audit_log").values())
    check(len(persisted) == 1 and persisted[0]["action"] == "IMPERSONATE_START"
          and persisted[0]["user_id"] == ADMIN["id"], "log_audit real persiste inicio no Firestore em memoria")
    details = AUDITS[0]["details"]
    check("target=2" in details and "sid=" + result["session_id"] in details
          and "exp=" in details and "motivo=" + REASON in details,
          "auditoria contem alvo, sid, vencimento e motivo normalizado")
    check(CUSTOM_TOKEN not in details, "auditoria nao contem token")
    check(bucket("users")["2"]["last_login"] is None, "emissao nao altera last_login do alvo")
    registered = bucket("impersonation_sessions")[result["session_id"]]
    check(registered["auth_uid"] == uid and registered["target_uid"] == TARGET["firebase_uid"]
          and registered["admin_uid"] == ADMIN["firebase_uid"] and registered["environment"] == ENVIRONMENT,
          "registro server-side corresponde ao principal assinado")
    check(registered["status"] == "active" and registered["ttl_seconds"] == config.IMPERSONATE_TTL_MINUTES * 60
          and registered["cleanup_after"].timestamp() - registered["created_at"].timestamp() == 7200,
          "registro ativo tem TTL e cleanup separado duas horas apos emissao")

    reset()
    CLAIMS[TARGET["firebase_uid"]] = {}
    start()
    check(SIGNED[0][1]["role"] == TARGET["role"]
          and SIGNED[0][1]["perfil_acesso_id"] == TARGET["perfil_acesso_id"],
          "claims ausentes usam doc do alvo e seu perfil custom")
    reset()
    CLAIMS[TARGET["firebase_uid"]] = {}
    bucket("users")["2"]["perfil_acesso_id"] = ""
    bucket("operator_profiles")[TARGET["firebase_uid"]]["perfil_acesso_id"] = "perfil_supervisor"
    start()
    check(SIGNED[0][1]["perfil_acesso_id"] == "perfil_supervisor", "perfil ausente usa seed da role")


def scenario_denials():
    title("CENARIO 2 - Negacoes e falhas sem vazamento")
    cases = [
        ("flag desligada", 404, lambda: setattr(main, "FEATURE_IMPERSONATE", False), {}),
        ("sem toggle", 403, lambda: None, {"user": TARGET}),
        ("alvo inexistente", 404, lambda: bucket("users").pop("2"), {}),
        ("alvo inativo", 404, lambda: bucket("users")["2"].update(is_active=0), {}),
        ("alvo sem uid", 409, lambda: bucket("users")["2"].update(firebase_uid=""), {}),
        ("alvo admin", 403, lambda: bucket("users")["2"].update(role="admin"), {}),
        ("proprio solicitante", 403, lambda: None, {"user_id": 1}),
        ("uid do proprio solicitante", 403,
         lambda: bucket("users")["2"].update(firebase_uid=ADMIN["firebase_uid"]), {}),
        ("outro tenant por lookup", 404, lambda: None, {"user_id": 99}),
        ("outro tenant por claim", 403,
         lambda: CLAIMS[TARGET["firebase_uid"]].update(tenant_id=OTHER_TENANT), {}),
        ("motivo curto", 400, lambda: None, {"reason": "  curto  "}),
        ("motivo vazio", 400, lambda: None, {"reason": "            "}),
        ("sem aninhamento", 403, lambda: None, {"decoded": decoded_imp()}),
        ("perfil operador ausente", 409, lambda: bucket("operator_profiles").pop(TARGET["firebase_uid"]), {}),
        ("perfil operador inativo", 409,
         lambda: bucket("operator_profiles")[TARGET["firebase_uid"]].update(is_active=0), {}),
        ("perfil com user_id divergente", 409,
         lambda: bucket("operator_profiles")[TARGET["firebase_uid"]].update(user_id=999), {}),
        ("perfil com role divergente", 409,
         lambda: bucket("operator_profiles")[TARGET["firebase_uid"]].update(role="operador"), {}),
        ("perfil com perfil_acesso divergente", 409,
         lambda: bucket("operator_profiles")[TARGET["firebase_uid"]].update(perfil_acesso_id="perfil_outro"), {}),
        ("perfil com uid divergente", 409,
         lambda: bucket("operator_profiles")[TARGET["firebase_uid"]].update(uid="uid-outro"), {}),
        ("claims role desatualizada", 409,
         lambda: CLAIMS[TARGET["firebase_uid"]].update(role="operador"), {}),
        ("claims perfil desatualizado", 409,
         lambda: CLAIMS[TARGET["firebase_uid"]].update(perfil_acesso_id="perfil_outro"), {}),
    ]
    for label, status, prepare, kwargs in cases:
        reset()
        prepare()
        expect_http(lambda: start(**kwargs), status, label)
        check(not SIGNED and not AUDITS, f"{label}: nao emite token nem audit de inicio")

    reset()
    bucket("perfis_acesso")["perfil_admin"] = {"toggles": {"ver_como_usuario": False}}
    expect_http(start, 403, "toggle explicitamente OFF no perfil admin")
    check(not SIGNED and not AUDITS, "toggle OFF sai antes de assinatura/auditoria")

    reset()
    reason = "x" * 230
    start(reason=reason)
    check(AUDITS[0]["details"].split("motivo=", 1)[1] == reason[:200], "motivo auditado limitado a 200 caracteres")

    reset()
    with patch.object(firebase_auth, "create_custom_token", side_effect=RuntimeError("segredo-interno-IAM")):
        error = expect_http(start, 503, "falha de assinatura IAM")
    check(error is not None and "segredo-interno-IAM" not in str(error.detail)
          and "token" in str(error.detail).lower(), "503 da assinatura claro e sem detalhe interno")
    check(not AUDITS, "falha de assinatura nao gera inicio bem-sucedido")
    check(all(record["status"] == "closed" for sid, record in bucket("impersonation_sessions").items() if sid != SID),
          "falha de assinatura fecha registro parcial sem conceder acesso")

    reset()
    with patch.object(firebase_auth, "get_user", side_effect=RuntimeError("segredo-interno-claims")):
        error = expect_http(start, 503, "leitura estrita dos claims falha")
    check(error is not None and "segredo-interno-claims" not in str(error.detail)
          and not SIGNED, "falha de claims nao emite token nem vaza excecao")

    reset()
    real_set = Document.set

    def fail_audit_write(doc, value, merge=False):
        if doc.name == "audit_log":
            raise RuntimeError("segredo-interno-audit")
        return real_set(doc, value, merge=merge)

    with patch.object(main, "log_audit", dbf.log_audit), patch.object(Document, "set", fail_audit_write):
        error = expect_http(start, 503, "falha de auditoria impede resposta de acesso")
    check(error is not None and CUSTOM_TOKEN not in str(error.detail)
          and "segredo-interno-audit" not in str(error.detail), "falha de audit nao devolve token nem excecao")
    check(all(record["status"] == "closed" for sid, record in bucket("impersonation_sessions").items() if sid != SID),
          "falha de auditoria fecha registro parcial ja assinado")
    reset()
    with patch.object(Document, "create", side_effect=RuntimeError("segredo-interno-registro")):
        error = expect_http(start, 503, "falha de criacao do registro impede emissao")
    check(error is not None and not SIGNED and not AUDITS
          and "segredo-interno-registro" not in str(error.detail), "sem registro persistido nao ha token nem detalhes internos")


def scenario_auth():
    title("CENARIO 3 - Auth sem escrita, cache isolado e fidelidade RBAC")
    reset()
    bucket("users")["2"].update(password_hash="hash-interno-simulado", department_id=10)
    bucket("departments")["10"] = {"id": 10, "name": "Setor Simulado"}
    TOKENS["imp"] = decoded_imp()
    original = deepcopy(bucket("users")["2"])
    result = auth.authenticate_firebase_token("imp", "127.0.0.1")
    check(result["success"] is True, "token imp valido autentica alvo")
    user = result["user"]
    check(user["id"] == TARGET["id"] and user["firebase_uid"] == TARGET["firebase_uid"],
          "identidade resolvida corresponde ao alvo")
    check(user.get("impersonation", {}).get("by") == ADMIN["id"]
          and user["impersonation"]["sid"] == SID
          and bool(user["impersonation"]["expires_at"]), "metadata de impersonation anexada em copia")
    check("impersonating" not in user and "read_only" not in user, "dict nao usa chaves que negam RBAC")
    check(not WRITES and not AUDITS and bucket("users")["2"] == original,
          "auth imp nao sincroniza identidade, login, audit nem claims")
    check(not auth._auth_user_cache, "auth imp nao grava no cache da sessao normal")
    expected_user = dict(TARGET)
    expected = rbac.effective_toggles(expected_user)
    check(rbac.effective_toggles(user) == expected and any(expected.values()), "toggles efetivos sao os do alvo")
    session = EVENT_LOOP.run_until_complete(main.session_info(current_user=user))
    check(session["user"]["impersonation"] == user["impersonation"]
          and session["perfil"]["toggles"] == expected, "/api/session preserva metadata e toggles do alvo")
    check("password_hash" not in session["user"] and "hash-interno-simulado" not in json.dumps(session),
          "/api/session usa whitelist e nao expoe hash do doc bruto")
    check(session["user"]["department_id"] == 10
          and session["user"]["department_name"] == "Setor Simulado",
          "/api/session enriquece setor como na sessao normal")
    check(not WRITES, "/api/session imp nao gera escrita")

    normal = decoded_normal()
    TOKENS["normal"] = normal
    result_normal = auth.authenticate_firebase_token("normal")
    check(result_normal["success"] and "impersonation" not in result_normal["user"],
          "sessao normal logo depois nao herda metadata imp")
    check(any(entry[0] == "users" for entry in WRITES), "sessao normal mantem fluxo normal de login")
    normal_cached = deepcopy(auth._auth_user_cache)
    WRITES.clear()
    AUDITS.clear()
    result_imp_again = auth.authenticate_firebase_token("imp")
    check(result_imp_again["success"] and "impersonation" in result_imp_again["user"]
          and auth._auth_user_cache == normal_cached and not WRITES,
          "imp depois de cache normal continua separado, sem alterar cache nem gravar")
    check("impersonation" not in result_normal["user"], "copia imp nao anota dict retornado a sessao real")

    reset()
    TOKENS["imp"] = decoded_imp(tenant_id="")
    result = auth.authenticate_firebase_token("imp")
    check(not result["success"] and result["status_code"] in (401, 403) and not WRITES,
          "imp sem tenant nao entra em fallback de dominio/provisionamento")
    reset()
    bucket("users").pop("2")
    TOKENS["imp"] = decoded_imp()
    result = auth.authenticate_firebase_token("imp")
    check(not result["success"] and not WRITES, "imp sem alvo provisionado nao cria usuario")
    reset()
    bucket("users")["2"]["is_active"] = 0
    TOKENS["imp"] = decoded_imp()
    result = auth.authenticate_firebase_token("imp")
    check(not result["success"] and not WRITES, "alvo desativado durante sessao perde acesso sem escrita")


def scenario_expiry():
    title("CENARIO 4 - Expiracao dura e claims malformados")
    reset()
    now = int(datetime.now(timezone.utc).timestamp())
    ttl_seconds = auth.IMPERSONATE_TTL_MINUTES * 60
    invalid = [
        ("imp_exp vencido", {"imp_exp": now - 1}),
        ("imp_exp no limite", {"imp_exp": now}),
        ("auth_time alem TTL + folga", {"auth_time": now - ttl_seconds - 65}),
        ("auth_time futuro alem folga", {"auth_time": now + 65}),
        ("imp_exp ausente", {"imp_exp": None}),
        ("auth_time ausente", {"auth_time": None}),
        ("imp_exp texto invalido", {"imp_exp": "invalido"}),
        ("auth_time texto invalido", {"auth_time": "invalido"}),
        ("imp_exp bool", {"imp_exp": True}),
        ("auth_time bool", {"auth_time": True}),
        ("imp_exp infinito", {"imp_exp": float("inf")}),
        ("auth_time nan", {"auth_time": float("nan")}),
    ]
    for label, changes in invalid:
        TOKENS["imp"] = decoded_imp(**changes)
        check(auth.validate_impersonation_claims(TOKENS["imp"]) is False, f"{label}: helper rejeita")
        result = auth.authenticate_firebase_token("imp")
        check(not result["success"] and result["status_code"] == 401
              and result["error"] == "Sessao de visualizacao expirada", f"{label}: auth retorna 401")
    check(not WRITES and not AUDITS, "expiracao nunca passa pelo fluxo de escrita")
    check(auth.validate_impersonation_claims(decoded_imp(auth_time=now - ttl_seconds - 30)) is True,
          "folga de 60s em auth_time aceita pequeno desvio")
    check(auth.validate_impersonation_claims(decoded_imp(auth_time=now + 30)) is True,
          "folga de 60s aceita auth_time ligeiramente futuro")


def scenario_contract():
    title("CENARIO 5 - Principal separado, registro obrigatorio e ausencia de fallback")
    variants = [
        ("UID real com imp legado", {"uid": TARGET["firebase_uid"]}),
        ("UID temporario de outro SID", {"uid": temp_uid("b" * 32)}),
        ("ambiente diferente", {"imp_env": ENVIRONMENT + "_other"}),
        ("alvo divergente", {"imp_target_uid": "uid-outro-sim"}),
        ("SID malformado", {"imp_sid": "nao-hex"}),
        ("sem referencia do alvo", {"imp_target_uid": None}),
        ("sem ambiente", {"imp_env": None}),
        ("sem SID", {"imp_sid": None}),
        ("sem tenant", {"tenant_id": None}),
        ("admin id divergente", {"imp_by": 100}),
        ("admin uid divergente", {"imp_by_uid": "uid-outro-admin"}),
    ]
    for label, changes in variants:
        reset()
        TOKENS["invalid"] = decoded_imp(**changes)
        result = auth.authenticate_firebase_token("invalid")
        check(not result["success"] and result["status_code"] in (401, 403)
              and not WRITES, f"{label}: negado sem escrita")
    for changes in ({"imp": False}, {"imp": None}, {"imp": False, "email": TARGET["email"]}):
        reset()
        TOKENS["no-claim"] = decoded_imp(**changes)
        with patch.object(auth, "get_user_by_firebase_uid", no_external), \
                patch.object(auth, "get_user_by_email", no_external), \
                patch.object(auth, "_auth_cache_get", no_external):
            result = auth.authenticate_firebase_token("no-claim")
        check(not result["success"] and not WRITES,
              "prefixo sem imp nunca entra em lookup/cache/login normal")
    invalid_records = [
        ("registro ausente", lambda: bucket("impersonation_sessions").pop(SID)),
        ("sessao fechada", lambda: bucket("impersonation_sessions")[SID].update(status="closed")),
        ("sessao limpa", lambda: bucket("impersonation_sessions")[SID].update(status="cleaned")),
        ("UID do registro divergente", lambda: bucket("impersonation_sessions")[SID].update(auth_uid="outro")),
        ("alvo do registro divergente", lambda: bucket("impersonation_sessions")[SID].update(target_uid="outro")),
        ("tenant do registro divergente", lambda: bucket("impersonation_sessions")[SID].update(tenant_id=OTHER_TENANT)),
        ("ambiente do registro divergente", lambda: bucket("impersonation_sessions")[SID].update(environment="outro")),
        ("admin do registro divergente", lambda: bucket("impersonation_sessions")[SID].update(admin_uid="outro")),
        ("TTL inferior minimo", lambda: bucket("impersonation_sessions")[SID].update(ttl_seconds=299)),
        ("TTL superior maximo", lambda: bucket("impersonation_sessions")[SID].update(ttl_seconds=3601)),
        ("role do alvo mudou", lambda: bucket("users")["2"].update(role="operador")),
        ("perfil do alvo mudou", lambda: bucket("users")["2"].update(perfil_acesso_id="perfil_outro")),
    ]
    for label, prepare in invalid_records:
        reset()
        TOKENS["invalid"] = decoded_imp()
        prepare()
        result = auth.authenticate_firebase_token("invalid")
        check(not result["success"] and not WRITES, f"{label}: negado sem tocar alvo")
    reset()
    TOKENS["imp"] = decoded_imp()
    first = auth.authenticate_firebase_token("imp")
    first_toggles = rbac.effective_toggles(first["user"])
    bucket("perfis_acesso")["perfil_sim_custom"]["toggles"]["gerenciar_usuarios"] = False
    rbac.invalidate_perfil_cache()
    after = auth.authenticate_firebase_token("imp")
    check(after["success"] and first_toggles["gerenciar_usuarios"] is True
          and rbac.effective_toggles(after["user"])["gerenciar_usuarios"] is False,
          "mudanca de toggles do mesmo perfil continua refletida sem trocar identidade")
    reset()
    TOKENS["imp"] = decoded_imp()
    with patch.object(Document, "get", side_effect=RuntimeError("falha-interna-registro")):
        result = auth.authenticate_firebase_token("imp")
    check(not result["success"] and result["status_code"] == 503
          and "falha-interna-registro" not in result["error"] and not WRITES,
          "falha de leitura do registro nega auth sem escrita nem detalhes internos")


def run_middleware(method, path, decoded):
    TOKENS["middleware"] = deepcopy(decoded)
    executed = []

    async def endpoint(req):
        executed.append(fsc.get_tenant_context())
        # call_next real fornece body_iterator ao middleware de tenant.
        return StreamingResponse(iter([b'{"reached":true}']), media_type="application/json")

    result = EVENT_LOOP.run_until_complete(main.tenant_context_middleware(
        request(method=method, path=path, token="middleware"), endpoint))
    return result, executed


def scenario_middleware():
    title("CENARIO 6 - Trava antes do endpoint e tenant context")
    reset()
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response, executed = run_middleware(method, "/api/wa/send", decoded_imp())
        check(response.status_code == 403 and not executed, f"{method}: 403 sem executar endpoint")
        check(json.loads(response.body)["detail"] == "Modo visualizacao: somente leitura",
              f"{method}: motivo de somente leitura")
    for method in ("GET", "HEAD", "OPTIONS"):
        response, executed = run_middleware(method, "/api/session", decoded_imp())
        check(response.status_code == 200 and executed == [TENANT], f"{method} passivo passa no tenant do alvo")
    read_posts = (
        "/api/wa/contacts/picker/search",
        "/api/wa/contacts/picker/by-tag",
        "/api/admin/reopen-batch/preview",
    )
    for path in read_posts:
        response, executed = run_middleware("POST", path, decoded_imp())
        check(response.status_code == 200 and executed == [TENANT], f"allowlist POST leitura: {path}")
        response, executed = run_middleware("PATCH", path, decoded_imp())
        check(response.status_code == 403 and not executed, f"allowlist nao libera PATCH: {path}")
    for path in (read_posts[0] + "/extra", "/api/admin/reopen-batch/execute", "/api/wa/conversation/open"):
        response, executed = run_middleware("POST", path, decoded_imp())
        check(response.status_code == 403 and not executed, f"POST fora da allowlist bloqueado: {path}")
    for method in ("GET", "HEAD"):
        response, executed = run_middleware(method, "/api/admin/monitor/auditoria", decoded_imp())
        check(response.status_code == 403 and not executed, f"{method} auditoria com efeito colateral bloqueado")
        normal = decoded_normal()
        response, executed = run_middleware(method, "/api/admin/monitor/auditoria", normal)
        check(response.status_code == 200 and executed == [TENANT], f"{method} auditoria normal preservado")
    normal = decoded_normal()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        response, executed = run_middleware(method, "/api/wa/send", normal)
        check(response.status_code == 200 and executed == [TENANT], f"token normal {method} continua intacto")
    for method in ("GET", "POST", "OPTIONS"):
        response, executed = run_middleware(method, "/api/session", decoded_imp(imp_exp=1))
        check(response.status_code == 401 and not executed, f"imp expirado {method}: 401 antes do endpoint")
    response, executed = run_middleware("GET", "/api/session", decoded_imp(auth_time=1))
    check(response.status_code == 401 and not executed, "auth_time velho: middleware retorna 401")
    for invalid in (decoded_imp(uid=TARGET["firebase_uid"]), decoded_imp(imp=False),
                    decoded_imp(imp_env="outro")):
        response, executed = run_middleware("GET", "/api/session", invalid)
        check(response.status_code in (401, 403) and not executed,
              "middleware nega principal legado/incompleto/ambiente sem executar endpoint")
    check(fsc.get_tenant_context() == TENANT, "middleware restaura contexto depois do endpoint")


def scenario_rbac():
    title("CENARIO 7 - Seed e fallback do toggle Ver como")
    reset()
    check("ver_como_usuario" in rbac.PERMISSION_KEYS, "toggle presente no catalogo")
    check(rbac.SEED_PERFIS["perfil_admin"]["toggles"]["ver_como_usuario"] is True,
          "seed admin recebe Ver como")
    for perfil in ("perfil_supervisor", "perfil_operador"):
        check(rbac.SEED_PERFIS[perfil]["toggles"]["ver_como_usuario"] is False,
              f"{perfil} nao recebe Ver como")
    check(rbac.has_permission(ADMIN, "ver_como_usuario") is True, "admin antigo sem chave usa fallback ON")
    check(rbac.has_permission(dict(TARGET, perfil_acesso_id="perfil_sem_doc"), "ver_como_usuario") is False,
          "supervisor antigo sem chave usa fallback OFF")
    old_doc = {"role_equivalente": "admin", "toggles": {}}
    check(rbac._fill_missing_toggles(old_doc)["toggles"]["ver_como_usuario"] is True,
          "editor de perfil antigo preenche toggle novo pelo seed")
    check(rbac.has_permission(dict(ADMIN, read_only=True), "gerenciar_usuarios") is False,
          "defesa RBAC legada read_only continua presente")


def scenario_rules_static():
    title("CENARIO 8 - Contrato de rules (inspecao estatica, nao substitui emulator)")
    source = Path(ROOT, "firestore.rules").read_text(encoding="utf-8")
    source = re.sub(r"//[^\n]*", "", source)
    check("impersonation_sessions" in source and "normalPrincipal()" in source,
          "fonte rules reserva registro server-only e principal normal")
    check("!reservedUid(request.auth.uid) && !isImpersonation()" in source
          and "imp_ro_" in source and "effectiveUid" not in source,
          "fonte rules nega temporario e imp legado sem mapear UID efetivo")


def scenario_cleanup():
    title("CENARIO 9 - Cleanup registrado, limitado e idempotente sem atingir UIDs reais")
    reset()
    now = datetime.fromtimestamp(int(datetime.now(timezone.utc).timestamp()), timezone.utc)

    def old(sid, tenant=TENANT, **changes):
        record = seed_session(
            sid, tenant=tenant,
            created_at=datetime.fromtimestamp(now.timestamp() - 10800, timezone.utc),
            expires_at=datetime.fromtimestamp(now.timestamp() - 9000, timezone.utc),
            cleanup_after=datetime.fromtimestamp(now.timestamp() - 3600, timezone.utc), **changes)
        return record

    old("b" * 32)
    old("c" * 32, tenant=OTHER_TENANT, status="closed")
    old("d" * 32, status="cleaned")
    result = impersonation.cleanup_expired_sessions(now=now, batch_size=2)
    check(set(DELETED) == {temp_uid("b" * 32), temp_uid("c" * 32)}
          and result["cleaned"] == 2, "cleanup inclui tenant inativo e exclui so sessoes vencidas registradas")
    check(bucket("impersonation_sessions")["b" * 32]["status"] == "cleaned"
          and bucket("impersonation_sessions", OTHER_TENANT)["c" * 32]["status"] == "cleaned",
          "cleanup marca cleaned somente apos apagar conta temporaria")
    queries = [query for query in QUERIES if query[1] == "impersonation_sessions"]
    check(queries and all(query[3] and query[3][0] == "cleanup_after" and query[4] == 2 for query in queries),
          "cleanup usa query ordenada com limite por tenant")
    check(all(any(field == "status" and op == "in" and set(value) == {"active", "closed"}
                  for field, op, value in query[2]) for query in queries),
          "query exclui tombstones cleaned para nao bloquear drenagem")

    reset()
    old("e" * 32)
    DELETE_ERRORS[temp_uid("e" * 32)] = firebase_auth.UserNotFoundError("Conta simulada ja ausente")
    result = impersonation.cleanup_expired_sessions(now=now)
    check(result["cleaned"] == 1 and bucket("impersonation_sessions")["e" * 32]["status"] == "cleaned",
          "UserNotFound e sucesso idempotente")

    reset()
    old("f" * 32)
    DELETE_ERRORS[temp_uid("f" * 32)] = RuntimeError("Falha transitoria simulada")
    result = impersonation.cleanup_expired_sessions(now=now)
    check(result["failed"] == 1 and bucket("impersonation_sessions")["f" * 32]["status"] != "cleaned",
          "falha Auth preserva registro elegivel para retry")
    DELETE_ERRORS.clear()
    result = impersonation.cleanup_expired_sessions(now=now)
    check(result["cleaned"] == 1 and bucket("impersonation_sessions")["f" * 32]["status"] == "cleaned",
          "retry posterior conclui limpeza")

    reset()
    for sid in ("b" * 32, "c" * 32, "d" * 32):
        old(sid)
    result = impersonation.cleanup_expired_sessions(now=now, batch_size=2)
    check(result["cleaned"] == 2 and len(DELETED) == 2,
          "lote limita chamadas Auth mesmo com mais registros pendentes")
    result = impersonation.cleanup_expired_sessions(now=now, batch_size=2)
    check(result["cleaned"] == 1 and len(DELETED) == 3,
          "proximo lote avanca alem dos tombstones limpos")

    reset()
    old("b" * 32)
    real_update = Document.update

    def fail_mark_cleaned(doc, value):
        if value.get("status") == "cleaned":
            raise RuntimeError("Falha simulada depois de delete Auth")
        return real_update(doc, value)

    with patch.object(Document, "update", fail_mark_cleaned):
        result = impersonation.cleanup_expired_sessions(now=now)
    check(result["failed"] == 1 and bucket("impersonation_sessions")["b" * 32]["status"] == "active",
          "falha Firestore apos delete Auth preserva registro para retry")
    DELETE_ERRORS[temp_uid("b" * 32)] = firebase_auth.UserNotFoundError("Conta removida na tentativa anterior")
    result = impersonation.cleanup_expired_sessions(now=now)
    check(result["cleaned"] == 1 and bucket("impersonation_sessions")["b" * 32]["status"] == "cleaned",
          "retry de falha parcial Auth/Firestore termina por UserNotFound")

    for label, changes in (
        ("auth_uid normal alvo", {"auth_uid": TARGET["firebase_uid"]}),
        ("auth_uid normal admin", {"auth_uid": ADMIN["firebase_uid"]}),
        ("target_uid colide temporario", {"target_uid": temp_uid("b" * 32)}),
        ("admin_uid colide temporario", {"admin_uid": temp_uid("b" * 32)}),
        ("ambiente divergente", {"environment": ENVIRONMENT + "_outro"}),
        ("UID reconstruido divergente", {"auth_uid": temp_uid("c" * 32)}),
        ("tenant divergente", {"tenant_id": OTHER_TENANT}),
    ):
        reset()
        old("b" * 32, **changes)
        result = impersonation.cleanup_expired_sessions(now=now)
        check(not DELETED and result["rejected"] >= 1, f"cleanup rejeita {label} sem chamar Auth")


def scenario_end():
    title("CENARIO 10 - Encerrar somente a propria sessao e auditar como admin original")
    reset()
    TOKENS["imp"] = decoded_imp()
    current_user = auth.authenticate_firebase_token("imp")["user"]
    seed_session("b" * 32)
    result = EVENT_LOOP.run_until_complete(main.impersonation_end(
        request=request(path="/api/impersonation/end", token="imp", decoded=decoded_imp()),
        current_user=current_user))
    check(bucket("impersonation_sessions")[SID]["status"] == "closed"
          and bucket("impersonation_sessions")["b" * 32]["status"] == "active",
          "encerramento altera somente registro da sessao autenticada")
    check(any(entry["action"] == "IMPERSONATE_END" and entry["user_id"] == ADMIN["id"] for entry in AUDITS),
          "auditoria de encerramento atribuida ao admin original")
    check(all(write[0] in ("impersonation_sessions", "audit_log") for write in WRITES)
          and not DELETED, "encerramento nao altera alvo nem deleta conta antes do cleanup")
    after = auth.authenticate_firebase_token("imp")
    check(not after["success"], "token fechado nao recupera acesso em request posterior")
    reset()
    expect_http(lambda: EVENT_LOOP.run_until_complete(main.impersonation_end(
        request=request(path="/api/impersonation/end", decoded=decoded_normal(ADMIN)), current_user=ADMIN)),
        403, "sessao normal nao pode encerrar sessao de terceiro")


def scenario_namespace():
    title("CENARIO 11 - Namespace nao vira usuario CRM ou super-admin")
    reset()
    for label, call in (
        ("sync identidade", lambda: dbf.sync_user_identity(2, firebase_uid=temp_uid())),
        ("auto-provision", lambda: dbf.upsert_firebase_user(temp_uid(), TARGET["email"])),
        ("claims tenant", lambda: fac.set_tenant_claims(temp_uid(), TENANT)),
        ("limpar claims", lambda: fac.clear_tenant_claims(temp_uid())),
        ("claims super-admin", lambda: fac.set_super_admin_claim(temp_uid())),
        ("revogar refresh", lambda: fac.revoke_refresh_tokens(temp_uid())),
    ):
        try:
            call()
        except ValueError:
            check(not WRITES, f"{label} rejeita UID reservado antes de escrita/API")
        else:
            check(False, f"{label} deveria rejeitar UID reservado")
    for decoded in (decoded_imp(super_admin=True), decoded_imp(imp=False, super_admin=True),
                    decoded_imp(uid=TARGET["firebase_uid"], super_admin=True)):
        TOKENS["superadmin"] = decoded
        with patch.object(superadmin_main, "get_super_admin", no_external):
            expect_http(lambda: superadmin_main._authorize(request(token="superadmin"), require_mfa=False),
                        403, "app B rejeita namespace/imp antes de ler cadastro super-admin")


def scenario_http():
    title("CENARIO 12 - HTTP ASGI real, sem lifespan nem startup")
    reset()
    bucket("users")["2"].update(password_hash="hash-http-simulado", department_id=10)
    bucket("departments")["10"] = {"id": 10, "name": "Setor HTTP"}
    TOKENS["http-imp"] = decoded_imp()
    TOKENS["http-admin"] = {
        "uid": ADMIN["firebase_uid"], "email": ADMIN["email"], "name": ADMIN["display_name"],
        "tenant_id": TENANT, "role": ADMIN["role"], "perfil_acesso_id": "perfil_admin",
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
    }

    async def exercise():
        # ASGITransport nao roda lifespan. Os hooks reais de startup nao sao chamados.
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://sim.local") as client:
            headers = {"Authorization": "Bearer http-imp"}
            session = await client.get("/api/session", headers=headers)
            check(session.status_code == 200 and session.json()["user"]["id"] == TARGET["id"],
                  "HTTP GET /session autentica alvo pelo middleware e dependency reais")
            check(session.headers.get("cache-control") == "private, no-store",
                  "HTTP sessao de visualizacao recebe Cache-Control private, no-store")
            check(session.json()["user"]["department_name"] == "Setor HTTP"
                  and "password_hash" not in session.json()["user"],
                  "HTTP GET /session inclui setor e filtra campos internos")
            check(not WRITES and not AUDITS, "HTTP GET imp continua sem escrita automatica")
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                response = await client.request(method, "/api/wa/conversation/open", headers=headers,
                                                json={"contact_id": 2})
                check(response.status_code == 403
                      and response.json()["detail"] == "Modo visualizacao: somente leitura",
                      f"HTTP {method} mutacao bloqueada antes de parsing/endpoint")
            check(not WRITES and not SIGNED, "HTTP imp bloqueado nao grava nem assina tokens")
            response = await client.get("/api/admin/monitor/auditoria", headers=headers)
            check(response.status_code == 403 and not WRITES, "HTTP GET com auditoria bloqueado sem escrita")
            check(response.headers.get("cache-control") == "private, no-store",
                  "HTTP403 precoce do middleware tambem recebe no-store")
            with patch.object(main, "validate_session", side_effect=RuntimeError("registry-entrada-simulado")):
                response = await client.get("/api/session", headers=headers)
            check(response.status_code == 503 and response.headers.get("cache-control") == "private, no-store",
                  "HTTP503 precoce de registry tambem recebe no-store")
            for path in ("/api/wa/contacts", "/api/wa/conversations", "/api/wa/messages/1",
                         "/api/gc/conversations", "/api/gc/messages/1", "/api/rota-nao-revisada"):
                response = await client.get(path, headers=headers)
                check(response.status_code == 403, f"HTTP transporte antigo/GET fora da lista negado: {path}")
            response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 200 and "contact_groups" in response.json(),
                  "HTTP nova snapshot usa servico real sem SDK client-side")
            response = await client.get("/api/impersonation/view/snapshot?target_uid=nao-aceito", headers=headers)
            check(response.status_code == 400 and "nao-aceito" not in response.text,
                  "HTTP seletor de identidade desconhecido rejeitado sem ecoar valor")
            response = await client.get("/api/wa/contacts/all?q=termo-sensivel-simulado", headers=headers)
            check(response.status_code == 400 and "termo-sensivel-simulado" not in response.text,
                  "HTTP contatos/all nao aceita busca em query mesmo quando assinatura antiga aceita")
            for path in ("/api/wa/contacts/picker/search", "/api/impersonation/end"):
                response = await client.post(path + "?sid=seletor-nao-aceito", headers=headers, json={})
                check(response.status_code == 400 and bucket("impersonation_sessions")[SID]["status"] == "active",
                      f"HTTP POST {path} rejeita query antes de body/endpoint/encerramento")
            response = await client.get("/api/impersonation/view/snapshot",
                                        headers={"Authorization": "Bearer http-admin"})
            check(response.status_code == 403, "HTTP sessao normal nao entra no transporte exclusivo")
            WRITES.clear()
            AUDITS.clear()
            real_snapshot = impersonation_views.read_snapshot

            def closes_before_delivery(user):
                result = real_snapshot(user)
                bucket("impersonation_sessions")[SID]["status"] = "closed"
                result["never_deliver"] = "dado-sensivel-simulado"
                return result

            with patch.object(impersonation_views, "read_snapshot", closes_before_delivery):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 401 and "contact_groups" not in response.text
                  and "dado-sensivel-simulado" not in response.text,
                  "HTTP fechamento durante consulta nega corpo na revalidacao final sem memo")
            bucket("impersonation_sessions")[SID]["status"] = "active"
            clock = {"now": datetime.now(timezone.utc).timestamp()}

            def expires_before_delivery(user):
                result = real_snapshot(user)
                clock["now"] = TOKENS["http-imp"]["imp_exp"] + 1
                return result

            with patch.object(auth.time, "time", lambda: clock["now"]), \
                    patch.object(impersonation_views, "read_snapshot", expires_before_delivery):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 401 and "contact_groups" not in response.text
                  and response.headers.get("cache-control") == "private, no-store",
                  "HTTP consulta cruza TTL e nao entrega dados ja preparados")
            real_user_lookup = auth.get_user_by_id
            for transition in ("expires", "closes"):
                stage = {"ready": False, "clock": datetime.now(timezone.utc).timestamp()}

                def ready_snapshot(user):
                    result = real_snapshot(user)
                    stage["ready"] = True
                    return result

                def delayed_final_user_lookup(user_id):
                    user = real_user_lookup(user_id)
                    if stage["ready"]:
                        if transition == "expires":
                            stage["clock"] = TOKENS["http-imp"]["imp_exp"] + 1
                        else:
                            bucket("impersonation_sessions")[SID]["status"] = "closed"
                    return user

                with patch.object(impersonation_views, "read_snapshot", ready_snapshot), \
                        patch.object(auth, "get_user_by_id", delayed_final_user_lookup), \
                        patch.object(auth.time, "time", lambda: stage["clock"]):
                    response = await client.get("/api/impersonation/view/snapshot", headers=headers)
                check(response.status_code == 401 and "contact_groups" not in response.text,
                      f"HTTP {transition} durante lookup da propria auth final nega corpo")
                bucket("impersonation_sessions")[SID]["status"] = "active"
            stage = {"ready": False}
            real_validate = main.validate_session

            def ready_snapshot(user):
                result = real_snapshot(user)
                stage["ready"] = True
                return result

            def unavailable_final_registry(decoded):
                if stage["ready"]:
                    raise RuntimeError("registry-final-simulado")
                return real_validate(decoded)

            with patch.object(impersonation_views, "read_snapshot", ready_snapshot), \
                    patch.object(main, "validate_session", unavailable_final_registry):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 503 and "contact_groups" not in response.text
                  and "registry-final-simulado" not in response.text,
                  "HTTP falha de registry final nega corpo sem detalhe interno")
            perfil = bucket("perfis_acesso")[TARGET["perfil_acesso_id"]]
            rbac.invalidate_perfil_cache()
            check(rbac.has_permission(TARGET, "ver_todos_leads") is True,
                  "fixture aquece cache normal com toggle amplo antes da revogacao")
            perfil["toggles"]["ver_todos_leads"] = False
            response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 200 and "all" not in response.json()["conversation_groups"]
                  and response.json()["perfil"]["toggles"]["ver_todos_leads"] is False,
                  "HTTP perfil temporario ignora cache normal60s e reflete revogacao entre requests")
            check(rbac.has_permission(TARGET, "ver_todos_leads") is True,
                  "cache normal e comportamento normal permanecem independentes")
            perfil["toggles"]["ver_todos_leads"] = True

            def revokes_before_delivery(user):
                result = real_snapshot(user)
                bucket("perfis_acesso")[TARGET["perfil_acesso_id"]]["toggles"]["ver_todos_leads"] = False
                return result

            with patch.object(impersonation_views, "read_snapshot", revokes_before_delivery):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 409 and "contact_groups" not in response.text,
                  "HTTP toggle do mesmo perfil mudou durante query:409 sem payload antigo")
            response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 200 and "all" not in response.json()["conversation_groups"],
                  "HTTP proxima consulta utiliza perfil restrito atualizado")
            perfil["toggles"]["ver_todos_leads"] = True
            with patch.object(rbac, "document", side_effect=RuntimeError("perfil-strict-simulado")):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 503 and "contact_groups" not in response.text
                  and "perfil-strict-simulado" not in response.text,
                  "HTTP falha lendo perfil restrito nao cai no seed amplo de supervisor")
            real_toggles = main.read_impersonation_toggles
            profile_reads = []

            def fail_final_profile(*args):
                profile_reads.append(args)
                if len(profile_reads) > 1:
                    raise RuntimeError("perfil-final-simulado")
                return real_toggles(*args)

            with patch.object(main, "read_impersonation_toggles", fail_final_profile):
                response = await client.get("/api/impersonation/view/snapshot", headers=headers)
            check(response.status_code == 503 and "contact_groups" not in response.text,
                  "HTTP falha do perfil na validacao final tambem nega corpo")
            check(not WRITES and not AUDITS, "HTTP novas leituras/falhas finais continuam sem escrita")
            response = await client.post("/api/admin/impersonate", headers={"Authorization": "Bearer http-admin"},
                                         json={"user_id": 2, "reason": REASON})
            check(response.status_code == 200 and response.json()["custom_token"] == CUSTOM_TOKEN,
                  "HTTP admin normal emite acesso com body validado pelo FastAPI")
            check(response.headers.get("cache-control") == "private, no-store",
                  "HTTP emissao do token recebe Cache-Control private, no-store")
            check(len(SIGNED) == 1 and SIGNED[0][0] == temp_uid(response.json()["session_id"])
                  and any(entry["action"] == "IMPERSONATE_START" for entry in AUDITS),
                  "HTTP emissao assina identidade separada e persiste auditoria")
            unrelated_sid = response.json()["session_id"]
            response = await client.post("/api/impersonation/end", headers=headers,
                                         json={"sid": unrelated_sid})
            check(response.status_code == 200 and bucket("impersonation_sessions")[SID]["status"] == "closed"
                  and bucket("impersonation_sessions")[unrelated_sid]["status"] == "active",
                  "HTTP encerramento ignora SID arbitrario e fecha somente sessao autenticada")
            response = await client.get("/api/session", headers=headers)
            check(response.status_code == 401, "HTTP novo GET apos encerramento e negado")
            check(response.headers.get("cache-control") == "private, no-store",
                  "HTTP401 precoce do registro fechado tambem recebe no-store")
    EVENT_LOOP.run_until_complete(exercise())


def scenario_legacy_scopes():
    title("CENARIO 13 - Leituras legadas sem canal/tenant/backup alheio")
    reset()
    perfil = bucket("perfis_acesso")[TARGET["perfil_acesso_id"]]
    perfil["toggles"].update(gerenciar_canais=False, ver_todos_leads=False,
                             ver_painel_conflitos=True, ver_dashboard_uso=True)
    TOKENS["scope-imp"] = decoded_imp()
    channels = {
        1: {"id": 1, "tenant_id": TENANT, "phone_number_id": "phone-own", "waba_id": "own-waba"},
        2: {"id": 2, "tenant_id": OTHER_TENANT, "phone_number_id": "phone-foreign", "waba_id": "foreign-waba"},
        3: {"id": 3, "tenant_id": TENANT, "phone_number_id": "phone-hidden", "waba_id": "hidden-waba"},
    }
    fetched = []

    async def templates(channel):
        fetched.append(("templates", channel["id"]))
        return {"templates": [{"id": channel["id"]}]}

    async def billing(channel_id):
        fetched.append(("billing", channel_id))
        return {"ok": True, "channel_id": channel_id}

    def global_query(name):
        query = Collection(name)
        query.tenant = ""
        return query

    def change(phone_id, marker):
        return {"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"text": marker}]}}

    now = datetime.now(timezone.utc)
    for event_id, phone_id, changes, offset in (
            ("own", "phone-own", [change("phone-own", "own-data"), change("phone-foreign", "foreign-data")], 1),
            ("foreign", "phone-foreign", [change("phone-foreign", "foreign-data")], 2),
            ("hidden", "phone-hidden", [change("phone-hidden", "hidden-data")], 3),
            ("unresolved", "unknown", [change("unknown", "unresolved-data")], 4),
            ("mismatch", "phone-own", [change("phone-foreign", "foreign-data")], 5)):
        bucket("pending_webhook_events", "")[event_id] = {"id": event_id, "phone_number_id": phone_id,
            "status": "pending", "reason": "processing_exception:foreign-error-secret", "last_error": "foreign-error-secret",
            "received_at": datetime.fromtimestamp(now.timestamp() + offset, timezone.utc),
            "payload": {"entry": [{"id": "foreign-waba-secret", "changes": changes}]}}
    bucket("gc_conversations")["1"] = {"id": 1, "space_id": "spaces/own", "space_name": "Sala local"}
    bucket("gc_conversations", OTHER_TENANT)["2"] = {"id": 2, "space_id": "spaces/foreign", "space_name": "Sala alheia"}
    bucket("gc_conversations")["3"] = {"id": 3, "space_name": "Sem vinculo"}
    for cid, backup in ((10, True), (20, False)):
        for owner in (2, 3):
            bucket("wa_conversations")[f"{cid}-{owner}"] = {"id": f"{cid}-{owner}", "contact_id": cid,
                "assigned_to": owner, "last_message_at": now, "is_backup": backup}
    bucket("wa_conversations")["20-backup"] = {"id": "20-backup", "contact_id": 20,
        "assigned_to": 4, "last_message_at": now, "is_backup": True}
    contacts = [{"id": 10, "is_backup": True, "display_name": "backup-secret"},
                {"id": 20, "is_backup": False, "display_name": "lead-visivel"}]

    async def exercise():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://sim.local") as client:
            headers = {"Authorization": "Bearer scope-imp"}
            for cid in (2, 3):
                response = await client.get(f"/api/wa/templates?channel_id={cid}", headers=headers)
                check(response.status_code == 404 and not fetched,
                      f"templates canal{cid} fora do tenant/visibilidade nega antes Meta/cache")
                main._billing_cache[cid] = (main._monotonic(), {"ok": True, "secret": "cached-foreign"})
                response = await client.get(f"/api/wa/channel/{cid}/billing-status", headers=headers)
                check(response.status_code == 404 and "cached-foreign" not in response.text and not fetched,
                      f"billing canal{cid} rejeitado antes de cache global/Meta")
            response = await client.get("/api/wa/templates?channel_id=1", headers=headers)
            check(response.status_code == 200 and fetched == [("templates", 1)], "templates canal proprio permitido via stub sem Meta")
            fetched.clear()
            response = await client.get("/api/wa/channel/1/billing-status", headers=headers)
            check(response.status_code == 200 and fetched == [("billing", 1)], "billing canal proprio permitido via stub sem Meta")
            perfil["toggles"]["gerenciar_canais"] = True
            response = await client.get("/api/admin/pending-webhook-events?status=pending&limit=100", headers=headers)
            check(response.status_code == 200 and {row["id"] for row in response.json()["events"]} == {"own", "hidden"},
                  "pending consulta somente phone_ids dos canais visiveis no tenant")
            check(all(marker not in response.text for marker in ("foreign-data", "foreign-error-secret", "foreign-waba-secret", "unresolved-data")),
                  "pending poda batch misto/erros/entry global e exclui sem vinculo comprovado")
            pending_queries = [query for query in QUERIES if query[1] == "pending_webhook_events"]
            check(pending_queries and all(any(field == "phone_number_id" and op == "==" and value in {"phone-own", "phone-hidden"}
                                              for field, op, value in query[2]) for query in pending_queries),
                  "pending usa igualdade server-side e nao consulta toda a colecao global")
            response = await client.get("/api/gc/spaces", headers=headers)
            check(response.status_code == 200 and [row["space_id"] for row in response.json()["spaces"]] == ["spaces/own"],
                  "GC spaces usa vinculos tenant, sem listar SA global ou sala alheia")
            response = await client.get("/api/admin/conflicts", headers=headers)
            check(response.status_code == 200 and [row["contact_id"] for row in response.json()["conflicts"]] == [20]
                  and len(response.json()["conflicts"][0]["conversations"]) == 2 and "backup-secret" not in response.text,
                  "conflitos permissionados removem contato/thread backup antes da resposta restrita")
            response = await client.get("/api/admin/dashboard/ratings", headers=headers)
            check(response.status_code == 200 and [row["id"] for row in response.json()["ratings"]] == [2, 3],
                  "ratings restrito remove backup e preserva legado sem campo")
            check(not WRITES and not AUDITS, "seis leituras legadas nao geram escritas ou auditoria do alvo")

    with ExitStack() as stack:
        for module, name, replacement in (
                (channel_service, "get_channel", lambda cid: deepcopy(channels.get(cid))),
                (main, "get_all_active_channels", lambda: deepcopy(list(channels.values()))),
                (main, "get_channels_for_user", lambda user_id: [deepcopy(channels[1])]),
                (main, "_load_approved_templates_for_channel", templates),
                (main, "_fetch_channel_billing_status", billing),
                (pending_events, "global_collection", global_query),
                (main, "fs_coll", Collection),
                (main, "get_all_wa_contacts", lambda: deepcopy(contacts)),
                (main, "get_all_ratings", lambda *args: [{"id": 1, "is_backup": True}, {"id": 2, "is_backup": False}, {"id": 3}]),
                (main, "FEATURE_GOOGLE_CHAT", True)):
            stack.enter_context(patch.object(module, name, replacement))
        main._billing_cache.clear()
        EVENT_LOOP.run_until_complete(exercise())
        main._billing_cache.clear()


def main_sim():
    global EVENT_LOOP
    # Windows cria um socketpair local para o loop. Cria-lo antes do guard
    # mantem qualquer conexao da aplicacao bloqueada durante os cenarios.
    with closing(asyncio.new_event_loop()) as loop, ExitStack() as stack:
        EVENT_LOOP = loop
        replacements = [
            (socket.socket, "connect", no_external),
            (socket.socket, "connect_ex", no_external),
            (fsc, "get_firestore_client", no_external),
            (fac, "get_firebase_app", lambda: SimpleNamespace(name="sim-firebase")),
            (firebase_auth, "verify_id_token", verify_token),
            (firebase_auth, "create_custom_token", sign_token),
            (firebase_auth, "get_user", lambda uid, **kwargs: SimpleNamespace(custom_claims=deepcopy(CLAIMS.get(uid, {})))),
            (firebase_auth, "delete_user", delete_user),
            (firebase_auth, "list_users", no_external),
            (firebase_auth, "create_user", no_external),
            (firebase_auth, "update_user", no_external),
            (firebase_auth, "set_custom_user_claims", no_external),
            (firebase_auth, "revoke_refresh_tokens", no_external),
            (dbf, "collection", Collection), (dbf, "document", Document),
            (fsc, "collection", Collection), (fsc, "document", Document),
            (rbac, "document", Document),
            (impersonation, "collection", Collection), (impersonation, "document", Document),
            (impersonation_views, "collection", Collection), (impersonation_views, "document", Document),
            (auth, "sync_user_identity", sync_identity), (auth, "update_last_login", last_login),
            (auth, "log_audit", audit), (auth, "set_tenant_claims", claims_write),
            (auth, "upsert_firebase_user", no_external),
            (auth, "resolve_tenant_by_email_domain", no_external),
            (auth, "single_active_tenant", no_external),
            (main, "log_audit", audit),
            (tenant_service, "get_tenant", lambda tid: {"id": tid, "plan": "professional"}),
            (tenant_service, "list_tenants", list_tenants),
            (monitor_service, "monitor_config", lambda tid: None),
        ]
        for module, name, replacement in replacements:
            stack.enter_context(patch.object(module, name, replacement))
        if hasattr(impersonation, "list_tenants"):
            stack.enter_context(patch.object(impersonation, "list_tenants", list_tenants))
        for scenario in (scenario_start, scenario_denials, scenario_auth, scenario_expiry, scenario_contract,
                         scenario_middleware, scenario_rbac, scenario_rules_static, scenario_cleanup,
                         scenario_end, scenario_namespace, scenario_http, scenario_legacy_scopes):
            try:
                scenario()
            except Exception:
                FAILS.append(scenario.__name__)
                traceback.print_exc()
        auth.invalidate_auth_cache()
        rbac.invalidate_perfil_cache()
    print(f"\nRESULTADO: {CHECKS} asserts, {len(FAILS)} falhas")
    for label in FAILS:
        print(f"  - {label}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main_sim())
