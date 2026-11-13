# -*- coding: utf-8 -*-

"""
Simulador LOCAL do motor de bot Dialogflow CX por tenant (CRM-2).

NAO toca em producao nem chama a API do Google: Firestore, tenant_service
e o conector bot_engine_dialogflow sao MOCKADOS em memoria. Exercita o
codigo real de bot_service.process_bot_message_async / _process_cx_message
e lgpd_bot.py.

Cobre (plano docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md, fase CRM-2):
  a) aviso LGPD do TENANT (settings.ai.lgpd_notice) no 1o contato;
  b) consentimento gravado no contato + audit com a policy version do tenant;
  c) parametros de sessao injetados (user_id/tenant_id/lgpd_consent) e
     session_id = digitos do wa_id; 1o turno usa o user_first_input;
  d) resposta do agente repassada (prefixada pela confirmacao do aceite);
  e) handoff -> bot_completed + department (bot_key) + system message +
     propagacao pra conversation + estado limpo;
  f) falha do conector: 1a -> fallback educado; 2a consecutiva -> handoff;
  g) tenant SEM settings.ai -> builtin intacto (dispatcher nao interfere);
  h) contato com operador atribuido -> bot silencioso.

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_cx_flow.py

Sai com codigo 0 se todas as checagens passarem, 1 caso contrario.
"""

import asyncio
import os
import sys
import types
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# =========================================================================
# Firestore em memoria (mesmo molde de tools/sim_bot_flow.py)
# =========================================================================

STORE = {}
MESSAGES = []
AUDIT = []


class _Snap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


class _DocRef:
    def __init__(self, coll, doc_id):
        self.coll = coll
        self.doc_id = str(doc_id)

    def get(self):
        return _Snap(STORE.get(self.coll, {}).get(self.doc_id))

    def set(self, data, merge=False):
        coll = STORE.setdefault(self.coll, {})
        cur = coll.get(self.doc_id) if merge else None
        resolved = {}
        for k, v in data.items():
            # Sentinela firestore.Increment (usada pelo cx_fail_count atomico):
            # resolve em memoria pro codigo real ler o numero de volta.
            if type(v).__name__ == "Increment":
                base = (cur or {}).get(k) or 0
                resolved[k] = base + getattr(v, "value", 0)
            else:
                resolved[k] = v
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(resolved)
        else:
            coll[self.doc_id] = dict(resolved)

    def delete(self):
        STORE.get(self.coll, {}).pop(self.doc_id, None)


class _QSnap:
    def __init__(self, coll, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = _DocRef(coll, doc_id)

    def to_dict(self):
        return dict(self._data) if self._data else None


class _CollRef:
    def __init__(self, coll):
        self.coll = coll
        self._filters = []

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def stream(self):
        for doc_id, data in list(STORE.get(self.coll, {}).items()):
            if all(op == "==" and data.get(f) == v for (f, op, v) in self._filters):
                yield _QSnap(self.coll, doc_id, data)


# =========================================================================
# Stubs de modulos (injetados ANTES dos imports reais)
# =========================================================================

_TENANT_ID = "varizemed-test"

_AI_CFG = {
    "bot_engine": "dialogflow_cx",
    "gcp_project_id": "castro-ai",
    "location": "global",
    "agent_id": "11111111-2222-3333-4444-555555555555",
    "environment_id": "",
    "language_code": "pt-br",
    "handoff_bot_key": "atendimento",
    "lgpd_notice": "Ola! Bem-vindo(a) a Clinica Varizemed. Tratamos seus dados de saude conforme a LGPD.",
    "lgpd_privacy_url": "https://varizemed.example/privacidade",
    "lgpd_policy_version": "varizemed-test-2026-07",
    "status": "active",
}

_TENANTS = {
    "varizemed-test": {"id": "varizemed-test", "name": "Clínica Varizemed",
                       "plan": "ai_custom", "settings": {"ai": _AI_CFG}},
    "hubloc": {"id": "hubloc", "name": "Hub Loc", "plan": "professional", "settings": {}},
}

_CURRENT_TENANT = {"id": _TENANT_ID}

BATCH_FAIL = {"on": False}


class _Batch:
    """WriteBatch em memoria: os sets so valem no commit (tudo ou nada)."""

    def __init__(self):
        self._ops = []

    def set(self, ref, data, merge=False):
        self._ops.append((ref, dict(data), merge))

    def commit(self):
        if BATCH_FAIL["on"]:
            raise RuntimeError("commit do batch falhou (simulado)")
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)


class _Client:
    def batch(self):
        return _Batch()


_fc = types.ModuleType("firestore_common")
_fc.document = lambda name, doc_id: _DocRef(name, doc_id)
_fc.collection = lambda name: _CollRef(name)
_fc.utcnow = lambda: datetime.now(timezone.utc)
_fc.get_firestore_client = lambda: _Client()
_fc.get_tenant_context = lambda: _CURRENT_TENANT["id"]
sys.modules["firestore_common"] = _fc

_ts = types.ModuleType("tenant_service")
_ts.get_tenant = lambda tid: dict(_TENANTS[tid]) if tid in _TENANTS else None
sys.modules["tenant_service"] = _ts

_DEPARTMENTS = [
    {"id": 10, "name": "Recepcao", "bot_key": "atendimento"},
    {"id": 1, "name": "Comercial", "bot_key": "comercial"},
    {"id": 2, "name": "Suporte", "bot_key": "sac"},
    {"id": 3, "name": "Financeiro", "bot_key": "financeiro"},
    {"id": 4, "name": "Administrativo", "bot_key": "administrativo"},
]

_db = types.ModuleType("database")
_db.get_wa_contact = lambda cid: (
    dict(STORE.get("wa_contacts", {}).get(str(cid)))
    if STORE.get("wa_contacts", {}).get(str(cid)) is not None else None
)
_db.get_system_settings = lambda: {"bot_enabled": True}
_db.get_all_departments = lambda: list(_DEPARTMENTS)
_db.assign_wa_contact = lambda *a, **k: None
_db.get_user_by_id = lambda uid: None


def _save_wa_message(**kwargs):
    MESSAGES.append(kwargs)
    return len(MESSAGES)


def _log_audit(user_id, action, detail=""):
    AUDIT.append({"user_id": user_id, "action": action, "detail": detail})


_db.save_wa_message = _save_wa_message
_db.log_audit = _log_audit
sys.modules["database"] = _db

# Conector CX mockado: controlavel por teste, registra as chamadas.
CX_CALLS = []
CX_SCRIPT = []  # fila de respostas; cada item e um dict de retorno


def _cx_ok(reply, **extra):
    base = {
        "ok": True,
        "reply_text": reply,
        "handoff_request": False,
        "handoff_summary": "",
        "conversation_complete": False,
        "user_name": "",
        "parameters": {},
    }
    base.update(extra)
    return base


_CX_FAIL = {
    "ok": False, "reply_text": "", "handoff_request": False,
    "handoff_summary": "", "conversation_complete": False, "user_name": "",
    "parameters": {},
}


async def _fake_detect_intent(cfg, session_id, text, session_params=None, timeout_s=None):
    CX_CALLS.append({
        "cfg": dict(cfg),
        "session_id": session_id,
        "text": text,
        "params": dict(session_params or {}),
        "timeout_s": timeout_s,
    })
    if CX_SCRIPT:
        return CX_SCRIPT.pop(0)
    return _cx_ok("(sem script)")


_cx = types.ModuleType("bot_engine_dialogflow")
_cx.detect_intent_text = _fake_detect_intent
# Desembrulho de struct REAL do conector (o bot_service reusa no desfecho_bot):
# carregado por spec, sem rede (o conector so importa config/httpx/pii).
import importlib.util as _ilu_stub  # noqa: E402
_spec_unwrap = _ilu_stub.spec_from_file_location(
    "bot_engine_dialogflow_unwrap", os.path.join(ROOT, "bot_engine_dialogflow.py"))
_mod_unwrap = _ilu_stub.module_from_spec(_spec_unwrap)
_spec_unwrap.loader.exec_module(_mod_unwrap)
_cx._unwrap_struct_params = _mod_unwrap._unwrap_struct_params
sys.modules["bot_engine_dialogflow"] = _cx


# =========================================================================
# Imports REAIS (usam os stubs acima)
# =========================================================================

import bot_service as bot  # noqa: E402


# =========================================================================
# Harness
# =========================================================================

FAILS = []
CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"      OK  {label}")
    else:
        FAILS.append(label)
        print(f"      FALHOU: {label}")


def novo_contato(cid, wa_id="5571999998888", **extra):
    STORE.setdefault("wa_contacts", {})[str(cid)] = {"id": cid, "wa_id": wa_id, **extra}
    STORE.setdefault("wa_conversations", {})[f"c{cid}"] = {
        "contact_id": cid, "department_id": None,
    }


def envia(cid, text):
    print(f"  Cliente: {text}")
    reply = asyncio.run(bot.process_bot_message_async(cid, text))
    if isinstance(reply, dict):
        print(f"  Bot (botoes): {reply.get('body', '')[:80]}...")
    elif isinstance(reply, str):
        print(f"  Bot: {reply[:100]}")
    else:
        print("  Bot: (silencio)")
    return reply


# =========================================================================
# Cenarios
# =========================================================================

print("\n=== a+b+c+d: LGPD do tenant -> aceite -> 1o turno CX com user_first_input ===")
novo_contato(1)
CX_SCRIPT.append(_cx_ok("Oi! Sou a Val. Sobre varizes, posso te ajudar sim."))

r1 = envia(1, "Oi, quero tratar minhas varizes")
check(isinstance(r1, dict) and r1.get("type") == "interactive_buttons",
      "1o contato -> botoes LGPD")
check(_AI_CFG["lgpd_notice"] in r1.get("body", ""),
      "aviso LGPD e o do TENANT (settings.ai.lgpd_notice)")
check(_AI_CFG["lgpd_privacy_url"] in r1.get("body", ""),
      "aviso inclui a URL de privacidade do tenant")
check(len(CX_CALLS) == 0, "CX NAO e chamado antes do consentimento")

r2 = envia(1, "lgpd_aceitar")
contato1 = STORE["wa_contacts"]["1"]
check(contato1.get("lgpd_consent") is True, "consentimento gravado no contato")
check(contato1.get("lgpd_policy_version") == "varizemed-test-2026-07",
      "policy version do TENANT no contato")
check(any(a["action"] == "LGPD_CONSENT_ACCEPTED" and "varizemed-test-2026-07" in a["detail"]
          for a in AUDIT), "audit_log do consentimento com a versao do tenant")
check(len(CX_CALLS) == 1, "1 chamada ao CX apos o aceite")
if CX_CALLS:
    c = CX_CALLS[0]
    check(c["session_id"] == "5571999998888", "session_id = digitos do wa_id")
    check(c["text"] == "Oi, quero tratar minhas varizes",
          "1o turno CX usa o user_first_input original")
    check(c["params"].get("user_id") == "+5571999998888", "param user_id E.164 com +")
    check(c["params"].get("tenant_id") == _TENANT_ID, "param tenant_id")
    check(c["params"].get("lgpd_consent") is True, "param lgpd_consent=True")
    # Frente b: as duas chaves de horario vao em TODO turno. Valor depende da
    # hora em que o sim roda -> aqui so presenca/tipo; valores deterministicos
    # no cenario de datas fixas la no fim.
    check(isinstance(c["params"].get("fora_do_expediente"), bool),
          "param fora_do_expediente (bool) em todo turno")
    check(isinstance(c["params"].get("retorno_previsto"), str),
          "param retorno_previsto (str) em todo turno")
check(isinstance(r2, str) and "Sou a Val" in r2,
      "resposta do agente repassada ao cliente")
check(isinstance(r2, str) and r2.index("Sou a Val") > 0,
      "confirmacao do aceite prefixa a resposta do agente")

print("\n=== d2: turno seguinte vai direto ao CX ===")
CX_SCRIPT.append(_cx_ok("O tratamento com microespuma e simples."))
r3 = envia(1, "Como funciona o tratamento?")
check(len(CX_CALLS) == 2 and CX_CALLS[1]["text"] == "Como funciona o tratamento?",
      "turno seguinte envia o texto do turno (nao o first_input)")
check(r3 == "O tratamento com microespuma e simples.",
      "resposta do 2o turno sem prefixo de aceite")

print("\n=== e: handoff pedido pelo agente ===")
STORE.setdefault("bot_buffers", {})["1"] = {
    "items": [{"text": "nao pode sobreviver", "ts": "2026-09-11T00:00:00+00:00", "n": 1}],
    "token": "old-token",
}
CX_SCRIPT.append(_cx_ok(
    "Claro! Estou te transferindo para a equipe.",
    handoff_request=True,
    handoff_summary="Paciente quer agendar consulta de angiologia",
    user_name="Daniel",
))
r4 = envia(1, "quero falar com atendente")
contato1 = STORE["wa_contacts"]["1"]
check(contato1.get("bot_completed") is True, "handoff -> bot_completed=True")
check("1" not in STORE.get("bot_buffers", {}), "handoff limpa buffer pendente do ciclo")
check(contato1.get("department_id") == 10,
      "handoff -> department_id do bot_key 'atendimento' (Recepcao)")
check(contato1.get("assigned_to") in (None, ""),
      "handoff NAO atribui operador (fica na pool)")
check(STORE["wa_conversations"]["c1"].get("department_id") == 10,
      "department_id propagado pra conversation")
# Marco do ciclo de espera da pool (fix 2026-08-09): sem handoff_at na
# conversation, o auto-close nao sabe distinguir "ninguem atendeu ainda" de
# "atendimento terminou" e devolve o lead do fim de semana pro bot.
check(STORE["wa_conversations"]["c1"].get("handoff_at") is not None,
      "handoff carimba handoff_at na conversation (marco do ciclo da pool)")
_sysmsgs = [m for m in MESSAGES if m.get("direction") == "system"]
check(any("Paciente quer agendar" in m.get("content", "") for m in _sysmsgs),
      "system message contem o handoff_summary do agente")
check(STORE.get("bot_states", {}).get("1") is None, "estado do bot limpo no handoff")
check(r4 == "Claro! Estou te transferindo para a equipe.",
      "mensagem de despedida do agente repassada")

print("\n=== e2: pos-handoff o bot silencia (gate bot_completed) ===")
# O gate real fica no webhook (bot_completed); simulamos o comportamento:
check(STORE["wa_contacts"]["1"].get("bot_completed") is True,
      "webhook nao rodara o bot (bot_completed=True)")

print("\n=== e3: handoff por TEXTO (param handoff_request=False, mas a Val fala a transferencia) ===")
novo_contato(12, wa_id="5571111112222")
STORE["bot_states"]["12"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok(
    "Entendido. Para te ajudar melhor com essa questao, estou transferindo nossa "
    "conversa para a equipe de atendimento humano agora mesmo.",
    handoff_request=False,   # agente NAO setou o parametro (caso real do staging)
))
re3 = envia(12, "quero um atendente")
check(STORE["wa_contacts"]["12"].get("bot_completed") is True,
      "handoff por texto -> bot_completed=True mesmo com param False")
check(STORE["wa_contacts"]["12"].get("department_id") == 10,
      "handoff por texto -> department Recepcao")

print("\n=== e3b: handoff por TEXTO na redacao do val-5.0.1 (env 75028a25) ===")
# O 5.0.1 reescreveu a mensagem de prioridade e nenhum dos 2 hints originais
# casava mais — o handoff passou a depender SO do parametro. Conferido no
# varizemed-test em 2026-08-09; texto abaixo e o real, copiado da conversa.
novo_contato(19, wa_id="5571333334444")
STORE["bot_states"]["19"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok(
    "Compreendido. Registrei sua solicitacao como prioridade no sistema.\n"
    "Nossa equipe de atendimento humano entrara em contato com voce por aqui "
    "assim que estiver disponivel, no proximo horario de atendimento.",
    handoff_request=False,   # a rede de texto e o unico sinal aqui
))
envia(19, "me passa pra equipe")
check(STORE["wa_contacts"]["19"].get("bot_completed") is True,
      "val-5.0.1: handoff por texto reconhecido (hints novos)")
check(STORE["wa_contacts"]["19"].get("department_id") == 10,
      "val-5.0.1: handoff por texto vai pro setor Recepcao")

print("\n=== f: falha do conector -> fallback e depois handoff ===")
novo_contato(2, wa_id="5571888887777")
STORE.setdefault("bot_states", {})["2"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(dict(_CX_FAIL))
rf1 = envia(2, "oi?")
check(isinstance(rf1, str) and "instabilidade" in rf1.lower(),
      "1a falha -> fallback educado")
check(STORE["bot_states"]["2"].get("cx_fail_count") == 1, "fail_count=1 persistido")
CX_SCRIPT.append(dict(_CX_FAIL))
rf2 = envia(2, "alo?")
contato2 = STORE["wa_contacts"]["2"]
check(contato2.get("bot_completed") is True, "2a falha consecutiva -> handoff")
check(contato2.get("department_id") == 10, "handoff de falha vai pro setor configurado")
check(any("Bot IA indisponivel" in m.get("content", "") for m in MESSAGES
          if m.get("direction") == "system"),
      "system message 'Bot IA indisponivel'")
check(isinstance(rf2, str) and "transferindo" in rf2.lower(),
      "cliente avisado da transferencia")

print("\n=== f2: sucesso zera fail_count ===")
novo_contato(3, wa_id="5571777776666")
STORE["bot_states"]["3"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx", "cx_fail_count": 1}
CX_SCRIPT.append(_cx_ok("Tudo certo por aqui!"))
envia(3, "oi")
check(STORE["bot_states"]["3"].get("cx_fail_count") == 0, "sucesso zera cx_fail_count")

print("\n=== g: tenant SEM settings.ai -> builtin intacto ===")
_CURRENT_TENANT["id"] = "hubloc"
novo_contato(4, wa_id="5531999990000")
rg = envia(4, "oi")
check(isinstance(rg, dict) and rg.get("type") == "interactive_buttons",
      "builtin responde botoes LGPD")
check("Hub Loc" in rg.get("body", ""), "builtin usa o aviso Hubloc (default preservado)")
check(len([c for c in CX_CALLS if c["params"].get("tenant_id") == "hubloc"]) == 0,
      "CX nunca chamado pro tenant professional")
_CURRENT_TENANT["id"] = _TENANT_ID

print("\n=== h: contato com operador atribuido -> silencio ===")
novo_contato(5, wa_id="5571666665555", assigned_to="operador1")
rh = envia(5, "oi")
check(rh is None, "bot silencioso com assigned_to")
check(len([c for c in CX_CALLS if c["session_id"] == "5571666665555"]) == 0,
      "CX nao chamado com operador atribuido")

print("\n=== i: wa_id invalido -> silencio (nao chama CX) ===")
novo_contato(6, wa_id="123")
STORE["bot_states"]["6"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
ri = envia(6, "oi")
check(ri is None, "wa_id fora do formato de sessao -> None")

print("\n=== j: reply vazio no turno do aceite -> confirmacao LGPD ainda vai (achado revisao) ===")
novo_contato(7, wa_id="5571555554444")
CX_SCRIPT.append(_cx_ok(""))  # agente responde vazio no 1o turno
envia(7, "quero informacoes")            # 1o contato -> botoes LGPD
rj = envia(7, "lgpd_aceitar")            # aceite -> DetectIntent vazio
check(isinstance(rj, str) and rj.lower().startswith("certo"),
      "aceite com reply CX vazio ainda entrega a confirmacao (nao silencio)")

print("\n=== k: handoff sem texto do agente -> mensagem padrao (nao silencio) ===")
novo_contato(8, wa_id="5571444443333")
STORE["bot_states"]["8"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("", handoff_request=True, handoff_summary="Quer atendente"))
rk = envia(8, "atendente")
check(isinstance(rk, str) and "transferindo" in rk.lower(),
      "handoff sem texto -> _CX_HANDOFF_DEFAULT_MSG")
check(STORE["wa_contacts"]["8"].get("bot_completed") is True, "handoff efetivado")

print("\n=== l: motor CX PAUSADO -> bot silencioso, NAO cai no builtin Hubloc (achado alta) ===")
_PAUSED_CFG = dict(_AI_CFG, status="paused")
_TENANTS["varizemed-paused"] = {"id": "varizemed-paused", "plan": "ai_custom",
                                "settings": {"ai": _PAUSED_CFG}}
_CURRENT_TENANT["id"] = "varizemed-paused"
novo_contato(9, wa_id="5571333332222")
rl = envia(9, "oi")
check(rl is None, "CX pausado -> None (nao responde)")
check(not (isinstance(rl, dict) and "Hub Loc" in str(rl.get("body", ""))),
      "CX pausado NUNCA mostra aviso do Hubloc")
_CURRENT_TENANT["id"] = _TENANT_ID

print("\n=== m: policy_version vazio no aceite -> marcador do tenant, NUNCA hubloc (achado alta) ===")
_NOVER_CFG = dict(_AI_CFG, lgpd_policy_version="")
_TENANTS["varizemed-nover"] = {"id": "varizemed-nover", "plan": "ai_custom",
                               "settings": {"ai": _NOVER_CFG}}
_CURRENT_TENANT["id"] = "varizemed-nover"
novo_contato(11, wa_id="5571222221111")
CX_SCRIPT.append(_cx_ok("ok"))
envia(11, "oi")
envia(11, "lgpd_aceitar")
pv = STORE["wa_contacts"]["11"].get("lgpd_policy_version")
check(pv and "hubloc" not in pv.lower(),
      f"policy_version nao carimba hubloc (veio {pv!r})")
check(pv == "varizemed-nover-sem-versao", "usa marcador neutro do proprio tenant")
_CURRENT_TENANT["id"] = _TENANT_ID

print("\n=== n: temperatura — EXECUCAO ADIADA (nenhum write durante o bot) ===")
novo_contato(13, wa_id="5571123451234", attendance_protocol="20260721-13-GERAL")
STORE["bot_states"]["13"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Posso agendar sim!", parameters={"wants_appointment": True}))
envia(13, "quero agendar uma consulta")
check("lead_temperature" not in STORE["wa_contacts"]["13"],
      "turno quente NAO grava temperatura (calculo so no handoff)")
check("lead_temperature" not in STORE["wa_conversations"]["c13"],
      "conversation sem temperatura durante o bot")

print("\n=== n2: handoff QUENTE — batch write + sumario enriquecido ===")
CX_SCRIPT.append(_cx_ok(
    "Transferindo para a equipe!",
    handoff_request=True,
    handoff_summary="Paciente quer agendar angiologia com Unimed",
    user_name="Daniel",
    parameters={
        "wants_appointment": "true",            # coercao string do CX
        "wants_treatment": True,
        "insurance_validated": True,
        "user_insurance": "Unimed",
        "user_specialty": "angiologia",
        "user_symptom": "dores e vasinhos nas pernas",
        "user_name": "Daniel",
    },
))
envia(13, "pode transferir")
c13 = STORE["wa_contacts"]["13"]
check(c13.get("lead_temperature") == "quente", "handoff -> contato quente")
check(c13.get("lead_temperature_at") is not None, "carimbo temporal no contato")
check(STORE["wa_conversations"]["c13"].get("lead_temperature") == "quente",
      "denorm quente na conversation")
check(STORE.get("attendances_daily", {}).get("20260721-13-GERAL", {}).get("lead_temperature") == "quente",
      "carimbo IMUTAVEL no protocolo do dia")
_m13 = [m for m in MESSAGES if m.get("direction") == "system"
        and "Temperatura do lead: QUENTE" in m.get("content", "")]
check(len(_m13) == 1, "system message com a temperatura")
if _m13:
    _c = _m13[0]["content"]
    check(_c.startswith("Bot IA finalizado | Transferido para atendimento humano"),
          "1a linha do sumario imutavel")
    check("Nome: Daniel" in _c, "sumario: nome")
    check("Sintoma: dores e vasinhos nas pernas" in _c, "sumario: sintoma")
    check("Convenio: Unimed (validado)" in _c, "sumario: convenio validado")
    check("Especialidade: angiologia" in _c, "sumario: especialidade")
    check("Quer agendar: sim" in _c, "sumario: quer agendar")
    check("Quer tratamento: sim" in _c, "sumario: quer tratamento")
    check("Resumo: Paciente quer agendar angiologia com Unimed" in _c,
          "sumario: resumo do agente")

print("\n=== n3: handoff FRIO — minimizacao (sem linhas vazias) ===")
novo_contato(14, wa_id="5571123459999")
STORE["bot_states"]["14"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Transferindo.", handoff_request=True, parameters={}))
envia(14, "atendente por favor")
check(STORE["wa_contacts"]["14"].get("lead_temperature") == "frio",
      "handoff sem sinais -> frio")
_m14 = [m for m in MESSAGES if m.get("direction") == "system"
        and m.get("contact_id") == 14]
check(bool(_m14) and "Temperatura do lead: FRIO" in _m14[-1].get("content", ""),
      "sumario frio presente")
if _m14:
    _c = _m14[-1]["content"]
    check("Nome:" not in _c and "Sintoma:" not in _c and "Convenio:" not in _c,
          "minimizacao: nenhuma linha de campo vazio")

print("\n=== n4: handoff por FALHA classifica frio (cenario f la atras) ===")
check(STORE["wa_contacts"]["2"].get("lead_temperature") == "frio",
      "handoff por falha do motor -> frio (sem params)")

print("\n=== n5: re-handoff SOBRESCREVE (semantica por-atendimento) ===")
c13 = STORE["wa_contacts"]["13"]
c13["bot_completed"] = False  # simulando 'Devolver ao bot'
c13["attendance_protocol"] = "20260722-13-GERAL"  # novo protocolo (outro dia)
STORE["bot_states"]["13"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Transferindo.", handoff_request=True, parameters={}))
envia(13, "so queria o endereco mesmo, me passa um atendente")
check(STORE["wa_contacts"]["13"].get("lead_temperature") == "frio",
      "novo engajamento generico REBAIXA quente->frio (nao fura a fila)")
check(STORE.get("attendances_daily", {}).get("20260721-13-GERAL", {}).get("lead_temperature") == "quente",
      "protocolo ANTIGO preserva o quente historico (carimbo imutavel)")
check(STORE.get("attendances_daily", {}).get("20260722-13-GERAL", {}).get("lead_temperature") == "frio",
      "protocolo NOVO carimbado frio")

print("\n=== n6: override temperature_signals por tenant (parcial) ===")
_SIG_CFG = dict(_AI_CFG, temperature_signals={"quente_bool_any": ["custom_flag"]})
_TENANTS["varizemed-sig"] = {"id": "varizemed-sig", "plan": "ai_custom",
                             "settings": {"ai": _SIG_CFG}}
_CURRENT_TENANT["id"] = "varizemed-sig"
novo_contato(15, wa_id="5571123457777")
STORE["bot_states"]["15"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Transferindo.", handoff_request=True,
                        parameters={"custom_flag": "true", "wants_appointment": True}))
envia(15, "atendente")
check(STORE["wa_contacts"]["15"].get("lead_temperature") == "quente",
      "override: custom_flag esquenta")
novo_contato(16, wa_id="5571123456666")
STORE["bot_states"]["16"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Transferindo.", handoff_request=True,
                        parameters={"wants_appointment": True, "user_specialty": "vascular"}))
envia(16, "atendente")
check(STORE["wa_contacts"]["16"].get("lead_temperature") == "morno",
      "override substitui quente_bool_any (wants_appointment nao esquenta mais) "
      "mas morno default segue valendo (user_specialty)")
_CURRENT_TENANT["id"] = _TENANT_ID

print("\n=== n7: builtin hubloc NUNCA ganha o campo ===")
check("lead_temperature" not in STORE["wa_contacts"]["4"],
      "contato do tenant professional sem lead_temperature")

print("\n=== o: LEAD SELF-SERVICE (bot resolve, sem handoff) -> assume classifica ===")
# Reproduz o caso real de 2026-07-21: cliente conversou, perguntou endereco/
# horario, decidiu agendar ONLINE e nunca pediu atendente.
novo_contato(17, wa_id="5531982779779", attendance_protocol="20260721-17-GERAL")
STORE["bot_states"]["17"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Temos microespuma e laser.",
                        parameters={"user_specialty": "angiologia"}))
envia(17, "me fale sobre os tratamentos")
check(STORE["bot_states"]["17"].get("cx_snapshot") == {"user_specialty": "angiologia"},
      "turno sem handoff guarda snapshot em bot_states")
check("lead_temperature" not in STORE["wa_contacts"]["17"],
      "NENHUM write em wa_contacts durante o bot (execucao adiada preservada)")
check("lead_temperature" not in STORE["wa_conversations"]["c17"],
      "NENHUM write em wa_conversations durante o bot")

_snap_antes = dict(STORE["bot_states"]["17"]["cx_snapshot"])
CX_SCRIPT.append(_cx_ok("O endereco e Rua X.",
                        parameters={"user_specialty": "angiologia"}))
envia(17, "qual o endereco?")
check(STORE["bot_states"]["17"]["cx_snapshot"] == _snap_antes,
      "params IGUAIS no turno seguinte -> snapshot inalterado (sem write inutil)")

CX_SCRIPT.append(_cx_ok("Voce pode agendar online.",
                        parameters={"user_specialty": "angiologia", "user_name": "Izael",
                                    "wants_appointment": True}))
envia(17, "como faco para agendar?")
check(STORE["bot_states"]["17"]["cx_snapshot"].get("wants_appointment") is True,
      "snapshot atualiza quando a informacao coletada MUDA")
check("lead_temperature" not in STORE["wa_contacts"]["17"],
      "ainda sem write no contato (cliente nunca pediu handoff)")

# Operador assume (o que o endpoint /api/wa/assume passa a chamar)
emitiu = bot.apply_cx_snapshot_on_assume(17)
check(emitiu is True, "assume com snapshot -> emite")
c17 = STORE["wa_contacts"]["17"]
check(c17.get("lead_temperature") == "quente",
      "assume classifica QUENTE (wants_appointment coletado no bot)")
check(STORE["wa_conversations"]["c17"].get("lead_temperature") == "quente",
      "badge: denorm na conversation")
check(STORE.get("attendances_daily", {}).get("20260721-17-GERAL", {}).get("lead_temperature") == "quente",
      "carimbo no protocolo do dia")
_m17 = [m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 17]
check(bool(_m17), "resumo emitido no thread")
if _m17:
    _c = _m17[-1]["content"]
    check(_c.startswith("Resumo do bot IA | Atendimento assumido durante a conversa"),
          "header do assume (NAO diz 'Transferido para atendimento humano')")
    check("Temperatura do lead: QUENTE" in _c, "resumo do assume traz a temperatura")
    check("Nome: Izael" in _c and "Especialidade: angiologia" in _c,
          "resumo do assume traz o que a IA coletou")

print("\n=== o2: assume e IDEMPOTENTE (2o clique nao duplica) ===")
_antes = len([m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 17])
emitiu2 = bot.apply_cx_snapshot_on_assume(17)
check(emitiu2 is False, "2o assume nao reemite (marcador cx_summary_emitted)")
check(len([m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 17]) == _antes,
      "nenhuma system message duplicada")
# O snapshot PRECISA sobreviver: os caminhos de takeover/picker nao silenciam
# o bot, entao ele segue coletando e um novo acionamento reemite atualizado.
# (Se alguem voltar a "consumir" o snapshot, esta checagem quebra.)
check(STORE["bot_states"]["17"].get("cx_snapshot"),
      "snapshot PRESERVADO apos emitir (idempotencia e por marcador, nao por consumo)")
check(STORE["bot_states"]["17"].get("cx_summary_emitted") == STORE["bot_states"]["17"].get("cx_snapshot"),
      "marcador registra exatamente o snapshot emitido")

print("\n=== o2b: ENGAJAMENTO NOVO com os MESMOS params -> reemite (regressao da revisao) ===")
# Protocolo novo (outro dia / lead devolvido ao bot). Sem chavear o marcador
# pelo protocolo, a igualdade do snapshot suprimia resumo E temperatura.
STORE["wa_contacts"]["17"]["attendance_protocol"] = "20260730-17-GERAL"
_antes2 = len([m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 17])
emitiu3 = bot.apply_cx_snapshot_on_assume(17)
check(emitiu3 is True, "protocolo NOVO com params iguais -> reemite o resumo")
check(len([m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 17]) == _antes2 + 1,
      "exatamente 1 system message nova")
check(STORE.get("attendances_daily", {}).get("20260730-17-GERAL", {}).get("lead_temperature") == "quente",
      "protocolo do dia NOVO recebe o carimbo de temperatura")
check(bot.apply_cx_snapshot_on_assume(17) is False,
      "e volta a ser idempotente dentro do protocolo novo")

print("\n=== o2c: human_active silencia o bot (takeover assume a THREAD, nao o Lead) ===")
novo_contato(21, wa_id="5531977776666")
STORE["bot_states"]["21"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
bot.mark_human_active(21)
check(STORE["bot_states"]["21"].get("human_active") is True, "flag human_active gravado")
_calls_antes = len(CX_CALLS)
r21 = envia(21, "oi, ainda esta ai?")
check(r21 is None, "bot NAO responde com humano conduzindo a thread")
check(len(CX_CALLS) == _calls_antes, "DetectIntent nem e chamado")

print("\n=== o3: assume de contato SEM bot CX -> no-op ===")
novo_contato(18, wa_id="5531999997777")
check(bot.apply_cx_snapshot_on_assume(18) is False,
      "contato sem snapshot (nunca falou com a IA) -> no-op")
check("lead_temperature" not in STORE["wa_contacts"]["18"], "nada gravado")
_CURRENT_TENANT["id"] = "hubloc"
novo_contato(19, wa_id="5531999996666")
STORE["bot_states"]["19"] = {"cx_snapshot": {"wants_appointment": True}}
check(bot.apply_cx_snapshot_on_assume(19) is False,
      "tenant builtin (hubloc) -> no-op mesmo com snapshot")
_CURRENT_TENANT["id"] = _TENANT_ID

print("\n=== o4: handoff normal segue com o header antigo (sem regressao) ===")
_hdr = [m for m in MESSAGES if m.get("direction") == "system"
        and str(m.get("content", "")).startswith("Bot IA finalizado | Transferido")]
check(len(_hdr) >= 3, "handoffs anteriores mantem o header 'Bot IA finalizado'")

print("\n=== p: params em STRUCT {chave: valor} (bug real de prod 2026-07-29) ===")
# O agente (rodando em DRAFT) passou a devolver cada param embrulhado num
# struct. O conector desembrulha na origem; aqui o mock injeta o struct CRU
# direto no bot_service pra provar a defesa em profundidade (_s/_b/classify).
novo_contato(20, wa_id="5531988887777")
STORE["bot_states"]["20"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok(
    "Perfeito! Estou transferindo nossa conversa para a equipe de atendimento.",
    handoff_request=True,
    parameters={
        "user_name": {"user_name": "Timmy"},
        "user_symptom": {"user_symptom": "varizes na perna"},
        "wants_appointment": {"wants_appointment": True},
    },
))
envia(20, "quero agendar com atendente")
c20 = STORE["wa_contacts"]["20"]
check(c20.get("lead_temperature") == "quente",
      "struct nos params NAO trava o QUENTE (wants_appointment embrulhado)")
_m20 = [m for m in MESSAGES if m.get("direction") == "system" and m.get("contact_id") == 20]
check(bool(_m20), "system message do handoff emitida")
if _m20:
    _c20 = _m20[-1]["content"]
    check("Nome: Timmy" in _c20, "resumo desembrulha o nome (sem repr de dict)")
    check("{'user_name'" not in _c20 and "{\"user_name\"" not in _c20,
          "nenhum dict cru vaza no resumo")
    check("Quer agendar: sim" in _c20, "linha 'Quer agendar: sim' alcancavel com struct")

print("\n=== p2: conector REAL desembrulha struct em _normalize_response ===")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "bot_engine_dialogflow_real", os.path.join(ROOT, "bot_engine_dialogflow.py"))
_real = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_real)
_norm = _real._normalize_response({
    "queryResult": {
        "responseMessages": [{"text": {"text": ["Ok, transferindo."]}}],
        "parameters": {
            "user_name": {"user_name": "Timmy"},
            "handoff_request": {"handoff_request": "true"},
            "wants_appointment": {"wants_appointment": True},
            "user_insurance": "Unimed",  # escalar segue intacto
            "composto": {"a": 1, "b": 2},  # dict de 2+ entradas passa intacto
        },
    },
})
check(_norm["user_name"] == "Timmy", "_normalize_response desembrulha user_name")
check(_norm["handoff_request"] is True, "_normalize_response coage handoff_request de struct")
check(_norm["parameters"].get("wants_appointment") is True,
      "parameters propagados ja desembrulhados")
check(_norm["parameters"].get("user_insurance") == "Unimed", "escalar preservado")
check(_norm["parameters"].get("composto") == {"a": 1, "b": 2},
      "dict legitimo de 2+ chaves nao e desembrulhado")

print("\n=== q: hidratacao LGPD pelo CONTATO (retorno pos-fechamento, Fase 2 item 9) ===")
# release_lead_to_bot limpa o ciclo (bot_states sem lgpd_*), mas a prova
# vive no contato: retorno NAO pode re-perguntar o aviso (ADR 0010/0009 D1).
novo_contato(40, wa_id="5571944443333", lgpd_consent=True,
             lgpd_consent_at="2026-08-05T00:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
CX_SCRIPT.append(_cx_ok("Ola de novo! O endereco e Rua X, 100."))
_n = len(CX_CALLS)
r = envia(40, "qual o endereco mesmo?")
check(isinstance(r, str) and "endereco" in r.lower(), "retorno vai DIRETO pro agente (sem aviso LGPD)")
check(len(CX_CALLS) == _n + 1, "CX chamado no 1o turno do retorno")
if len(CX_CALLS) > _n:
    check(CX_CALLS[-1]["text"] == "qual o endereco mesmo?",
          "mensagem ATUAL vai ao agente (sem replay de user_first_input)")
_st40 = STORE.get("bot_states", {}).get("40", {})
check(_st40.get("lgpd_consent") is True, "state hidratado persiste lgpd_consent")

novo_contato(41, wa_id="5571933332222", lgpd_consent=True,
             lgpd_policy_version="varizemed-velha-2020")
r = envia(41, "oi de novo")
check(isinstance(r, dict) and r.get("type") == "interactive_buttons",
      "policy_version divergente RE-PERGUNTA (fail-closed, D1)")

novo_contato(42, wa_id="5571922221111", lgpd_consent=True,
             lgpd_policy_version="varizemed-test-2026-07", lgpd_revoked=True)
r = envia(42, "oi")
check(isinstance(r, dict) and r.get("type") == "interactive_buttons",
      "lgpd_revoked NUNCA hidrata (guard J-3 D8)")

print("\n=== s: recusa LGPD assina com a marca do TENANT (incidente 10/08) ===")
# 2 leads reais da varizemed recusaram e receberam "A Hub Loc agradece o seu
# contato!" — a despedida era constante compartilhada. Agora resolve
# tenant.name (padrao do topbar).
novo_contato(43, wa_id="5571911110000")
envia(43, "oi")  # dispara o aviso LGPD
r = envia(43, "nao aceito")
check(isinstance(r, str) and "Clínica Varizemed agradece o seu contato" in r,
      "recusa no tenant CX assina 'Clínica Varizemed', nao 'Hub Loc'")
check(isinstance(r, str) and "Hub Loc" not in r,
      "nenhum vazamento de marca de outro tenant na recusa")

print("\n=== t: frase de erro do CX -> reenvia 3x, handoff no 4o erro (PO 2026-08-14) ===")
# O agente devolveu "Sorry something went wrong." com HTTP 200 e sem
# handoff_request — falha disfarcada de sucesso: o lead recebia erro em
# ingles e ficava preso no funil. Contrato: reenviar a MESMA mensagem do
# lead ate 3x (transparente); 4 erros consecutivos -> handoff generico.

# (a) 4 erros consecutivos -> handoff com a mensagem generica.
novo_contato(44, wa_id="5571900001111")
STORE["bot_states"]["44"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
for _ in range(4):
    CX_SCRIPT.append(_cx_ok("Sorry something went wrong.", handoff_request=False))
_n_calls = len(CX_CALLS)
rt = envia(44, "quero falar com a equipe")
check(len(CX_CALLS) == _n_calls + 4, "1 envio + 3 reenvios = 4 chamadas ao CX")
check(all(c["text"] == "quero falar com a equipe" for c in CX_CALLS[-4:]),
      "reenvios repetem a MESMA mensagem do lead")
check(isinstance(rt, str) and "Sorry" not in rt
      and "agente virtual" in rt.lower() and "operador humano" in rt.lower(),
      "4o erro -> mensagem generica de indisponibilidade (nunca o erro cru)")
check(STORE["wa_contacts"]["44"].get("bot_completed") is True,
      "4o erro -> handoff (bot_completed=True)")
check(STORE["wa_contacts"]["44"].get("department_id") == 10,
      "handoff-por-erro vai pro setor configurado")
check(any("erro interno" in m.get("content", "") for m in MESSAGES
          if m.get("direction") == "system"),
      "system message registra o motivo")

# (b) recupera num reenvio -> lead recebe a resposta boa, sem handoff.
novo_contato(45, wa_id="5571900002222")
STORE["bot_states"]["45"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok("Desculpe, algo deu errado.", handoff_request=False))
CX_SCRIPT.append(_cx_ok("Claro! Os horários de sexta estão livres a partir das 14h."))
_n_calls = len(CX_CALLS)
rt2 = envia(45, "tem horario sexta?")
check(len(CX_CALLS) == _n_calls + 2, "erro + reenvio limpo = 2 chamadas")
check(isinstance(rt2, str) and "horários de sexta" in rt2,
      "reenvio recuperou -> lead recebe a resposta boa (transparente)")
check(STORE["wa_contacts"]["45"].get("bot_completed") is not True,
      "recuperado -> sem handoff")

# (c) resposta LEGITIMA que cita "algo deu errado" NO MEIO nao dispara.
novo_contato(46, wa_id="5571900003333")
STORE["bot_states"]["46"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
CX_SCRIPT.append(_cx_ok(
    "Se algo deu errado no seu agendamento online, me conta o que aconteceu "
    "que eu te ajudo a corrigir.", handoff_request=False,
))
_n_calls = len(CX_CALLS)
rt3 = envia(46, "deu problema no agendamento")
check(len(CX_CALLS) == _n_calls + 1 and isinstance(rt3, str)
      and "agendamento online" in rt3,
      "resposta legitima contendo a expressao NO MEIO passa intacta, sem reenvio")

# (d) estrutura pro dev de IA: frase custom por tenant via
# settings.ai.cx_error_phrases, SEM deploy.
_AI_CFG["cx_error_phrases"] = ["Assistente em manutenção, tente novamente!"]
try:
    novo_contato(47, wa_id="5571900004444")
    STORE["bot_states"]["47"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    CX_SCRIPT.append(_cx_ok("Assistente em manutenção, tente novamente!"))
    CX_SCRIPT.append(_cx_ok("Voltei! Como posso ajudar?"))
    _n_calls = len(CX_CALLS)
    rt4 = envia(47, "oi")
    check(len(CX_CALLS) == _n_calls + 2 and isinstance(rt4, str) and "Voltei" in rt4,
          "frase custom do tenant (settings.ai.cx_error_phrases) tambem reenvia")
finally:
    _AI_CFG.pop("cx_error_phrases", None)

print("\n=== r: horario comercial da varizemed (business_hours, datas fixas) ===")
# 2026-08-10 = segunda. Tabela: seg-qui 08-18, sex 08-17, fds fechado.
from datetime import timedelta as _td, timezone as _tz
import business_hours as _bh

_BR = _tz(_td(hours=-3))
_qui_1730 = datetime(2026, 8, 13, 17, 30, tzinfo=_BR)
_sex_1730 = datetime(2026, 8, 14, 17, 30, tzinfo=_BR)
_seg_0732 = datetime(2026, 8, 10, 7, 32, tzinfo=_BR)
_ter_19h = datetime(2026, 8, 11, 19, 0, tzinfo=_BR)
_dom_22h = datetime(2026, 8, 9, 22, 0, tzinfo=_BR)

check(_bh.is_open("varizemed", _qui_1730) is True,
      "quinta 17:30 -> ABERTO (18h; a Val hardcoded dizia 'ate 18h' certo aqui)")
check(_bh.is_open("varizemed", _sex_1730) is False,
      "sexta 17:30 -> FECHADO (17h; saudacao hardcoded do agente errava aqui)")
_p = _bh.cx_hours_params("varizemed", _seg_0732)
check(_p == {"fora_do_expediente": True, "retorno_previsto": "hoje às 8h"},
      "segunda 07:32 -> 'hoje às 8h' (o caso real de 10/08 que disparou a frente)")
check(_bh.retorno_previsto_text("varizemed", _ter_19h) == "amanhã às 8h",
      "terca 19h -> 'amanhã às 8h'")
check(_bh.retorno_previsto_text("varizemed", _dom_22h) == "amanhã às 8h",
      "domingo 22h -> 'amanhã às 8h'")
check(_bh.retorno_previsto_text("varizemed", _sex_1730) == "segunda-feira às 8h",
      "sexta 17:30 -> 'segunda-feira às 8h'")
check(_bh.cx_hours_params("varizemed", _qui_1730)
      == {"fora_do_expediente": False, "retorno_previsto": ""},
      "aberto -> False + retorno vazio (agente nao interpola nada)")
check(_bh.get_schedule("varizemed-test") == _bh.get_schedule("varizemed"),
      "varizemed-test espelha a tabela da clinica real")
check(_bh.schedule_summary("varizemed")
      == "segunda a quinta das 8h às 18h e sexta das 8h às 17h",
      "resumo humano da tabela agrupa dias consecutivos")

print("\n=== u: conector REAL — read-timeout da chamada principal reenvia 1x; 5xx/connect reenviam 1x; teto vem do config ===")
# Historico: 18/08 o PO subiu o teto de 15s pra 60s e read-timeout passou a
# NAO reenviar (lead nao esperava 2 min). 20/08 o pendulo voltou: lead real
# aceitou a LGPD, o turno do agente passou de 109s (DEADLINE_EXCEEDED no
# proprio Dialogflow, que loga "Resend the request with a higher deadline")
# e o lead ficou no vacuo. PO decidiu: read-timeout da chamada PRINCIPAL
# (timeout_s=None) reenvia 1x com o teto inteiro antes do fallback
# (CX_READ_TIMEOUT_RETRY, default true; pior caso ~2x o teto). Reenvio por
# frase de erro (timeout_s explicito, roda na sobra do orcamento) segue sem
# read-retry. 5xx/rede/connect seguem com o retry rapido de sempre.
import httpx as _httpx

_real._get_access_token = lambda: "tok-fake"
_HTTP_CALLS = []


class _FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _fake_httpx(script):
    """Substitui o modulo httpx DENTRO do conector: AsyncClient roteirizado
    (excecao ou resposta por chamada POST), excecoes reais do httpx
    preservadas. Conta CHAMADAS (post), nao construcoes de client."""
    class _FakeClient:
        def __init__(self, *a, **kw):
            self._timeout = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            _HTTP_CALLS.append({"timeout": self._timeout, "text": json["queryInput"]["text"]["text"]})
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step

    return types.SimpleNamespace(
        AsyncClient=_FakeClient,
        Timeout=_httpx.Timeout,
        TimeoutException=_httpx.TimeoutException,
        ReadTimeout=_httpx.ReadTimeout,
        HTTPError=_httpx.HTTPError,
    )


_cfg_u = {"gcp_project_id": "p", "agent_id": "a", "location": "global"}
_ok_payload = {"queryResult": {"responseMessages": [{"text": {"text": ["Oi!"]}}]}}

# (a) read-timeout 2x na chamada principal -> 2 POSTs (reenvio 1x), ok=False.
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_httpx.ReadTimeout("lento"), _httpx.ReadTimeout("lento de novo")])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is False, "read-timeout 2x -> ok=False (chamador cai no fallback/handoff)")
check(len(_HTTP_CALLS) == 2, "read-timeout na chamada principal reenvia 1x: 2 POSTs ao CX")
check(len(_HTTP_CALLS) == 2 and _HTTP_CALLS[1]["timeout"].read == _real._DETECT_TIMEOUT_SECONDS,
      "o reenvio espera o teto INTEIRO de novo (nao a sobra)")
check(len(_HTTP_CALLS) == 2 and _HTTP_CALLS[1]["text"] == "oi",
      "o reenvio repete a MESMA mensagem do lead")
_t0 = _HTTP_CALLS[0]["timeout"] if _HTTP_CALLS else None
check(isinstance(_t0, _httpx.Timeout) and _t0.read == _real._DETECT_TIMEOUT_SECONDS
      == _real.CX_DETECT_TIMEOUT_SECONDS,
      "read do httpx.Timeout e o CX_DETECT_TIMEOUT_SECONDS do config (env-driven)")
check(isinstance(_t0, _httpx.Timeout) and _t0.connect == _real._CONNECT_TIMEOUT_SECONDS < _t0.read,
      "connect tem teto curto proprio (nao herda os 60s)")
check(os.getenv("CX_DETECT_TIMEOUT_SECONDS") or _real.CX_DETECT_TIMEOUT_SECONDS == 60.0,
      "default do teto = 60s (pedido do PO 2026-08-18)")

# (a2) read-timeout no 1o e 200 no reenvio -> turno ok (o retry salvou).
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_httpx.ReadTimeout("lento"), _FakeResp(200, _ok_payload)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is True and _ru["reply_text"] == "Oi!" and len(_HTTP_CALLS) == 2,
      "read-timeout + 200 no reenvio -> turno ok (lead nem ve instabilidade)")

# (a3) timeout_s explicito (reenvio por frase de erro, sobra do orcamento):
# read-timeout NAO reenvia — comportamento antigo preservado.
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_httpx.ReadTimeout("lento")])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}, timeout_s=20.0))
check(_ru["ok"] is False and len(_HTTP_CALLS) == 1,
      "read-timeout com timeout_s explicito -> 1 POST, sem reenvio (sobra do orcamento)")

# (b) 5xx transitorio -> reenvia 1x e passa.
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_FakeResp(503), _FakeResp(200, _ok_payload)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is True and _ru["reply_text"] == "Oi!" and len(_HTTP_CALLS) == 2,
      "5xx -> retry rapido 1x -> turno ok")

# (c) 5xx e depois read-timeout -> para no timeout (2 chamadas, ok=False).
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_FakeResp(500), _httpx.ReadTimeout("lento")])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is False and len(_HTTP_CALLS) == 2,
      "5xx + read-timeout -> 2 chamadas e desiste (timeout nunca gera 3a chamada)")

# (d) 4xx (config/permissao) -> sem retry.
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_FakeResp(403)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is False and len(_HTTP_CALLS) == 1, "4xx -> falha sem retry (config errada)")

# (e) erro de rede (conexao) e CONNECT-timeout -> retry 1x (pedido nao chegou).
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_httpx.ConnectError("reset"), _FakeResp(200, _ok_payload)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is True and len(_HTTP_CALLS) == 2, "erro de rede -> retry 1x -> turno ok")
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_httpx.ConnectTimeout("dns"), _FakeResp(200, _ok_payload)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
check(_ru["ok"] is True and len(_HTTP_CALLS) == 2,
      "connect-timeout -> retry 1x (pedido nao chegou; nao consome o read-retry)")

# (f) timeout_s explicito (orcamento restante do turno) vence o default.
_HTTP_CALLS.clear()
_real.httpx = _fake_httpx([_FakeResp(200, _ok_payload)])
_ru = asyncio.run(_real.detect_intent_text(_cfg_u, "5531999990000", "oi", {}, timeout_s=7.5))
check(_HTTP_CALLS and _HTTP_CALLS[0]["timeout"].read == 7.5
      and _HTTP_CALLS[0]["timeout"].connect == 7.5,
      "timeout_s=7.5 -> read=7.5 e connect nao passa do read")

# (g) a env CX_DETECT_TIMEOUT_SECONDS chega de verdade no conector (recarrega
# config + modulo real com a env setada), e valor invalido cai no default.
_env_bak = os.environ.get("CX_DETECT_TIMEOUT_SECONDS")
try:
    import importlib as _il
    import config as _cfgmod
    os.environ["CX_DETECT_TIMEOUT_SECONDS"] = "42.5"
    _il.reload(_cfgmod)
    check(_cfgmod.CX_DETECT_TIMEOUT_SECONDS == 42.5, "config le CX_DETECT_TIMEOUT_SECONDS da env")
    _spec2 = _ilu.spec_from_file_location(
        "bot_engine_dialogflow_env", os.path.join(ROOT, "bot_engine_dialogflow.py"))
    _real2 = _ilu.module_from_spec(_spec2)
    _spec2.loader.exec_module(_real2)
    check(_real2._DETECT_TIMEOUT_SECONDS == 42.5, "conector recarregado usa o valor da env (42.5)")
    for _bad in ("abc", "0", "-3", ""):
        os.environ["CX_DETECT_TIMEOUT_SECONDS"] = _bad
        _il.reload(_cfgmod)
        check(_cfgmod.CX_DETECT_TIMEOUT_SECONDS == 60.0,
              f"env invalida {_bad!r} nao derruba o import: cai no default 60")
finally:
    if _env_bak is None:
        os.environ.pop("CX_DETECT_TIMEOUT_SECONDS", None)
    else:
        os.environ["CX_DETECT_TIMEOUT_SECONDS"] = _env_bak
    _il.reload(_cfgmod)

# (g2) kill-switch do read-retry: CX_READ_TIMEOUT_RETRY=false volta ao
# comportamento pre-2026-08-20 (read-timeout da chamada principal desiste
# na hora, 1 POST) — religavel/desligavel por env, sem deploy.
_env_bak = os.environ.get("CX_READ_TIMEOUT_RETRY")
try:
    os.environ["CX_READ_TIMEOUT_RETRY"] = "false"
    _il.reload(_cfgmod)
    _spec3 = _ilu.spec_from_file_location(
        "bot_engine_dialogflow_noretry", os.path.join(ROOT, "bot_engine_dialogflow.py"))
    _real3 = _ilu.module_from_spec(_spec3)
    _spec3.loader.exec_module(_real3)
    _real3._get_access_token = lambda: "tok-fake"
    _HTTP_CALLS.clear()
    _real3.httpx = _fake_httpx([_httpx.ReadTimeout("lento")])
    _ru = asyncio.run(_real3.detect_intent_text(_cfg_u, "5531999990000", "oi", {}))
    check(_ru["ok"] is False and len(_HTTP_CALLS) == 1,
          "CX_READ_TIMEOUT_RETRY=false -> read-timeout desiste na 1a chamada (kill-switch)")
finally:
    if _env_bak is None:
        os.environ.pop("CX_READ_TIMEOUT_RETRY", None)
    else:
        os.environ["CX_READ_TIMEOUT_RETRY"] = _env_bak
    _il.reload(_cfgmod)

# (h) orcamento por TURNO no bot_service: reenvios por frase de erro so usam o
# que sobrou dos 60s; esgotado -> para de reenviar e cai no handoff generico.
# Relogio falso: cada chamada ao CX "gasta" 25s.
_clock = {"t": 1000.0}


def _fake_monotonic():
    return _clock["t"]


async def _fake_detect_slow(cfg, session_id, text, session_params=None, timeout_s=None):
    r = await _fake_detect_intent(cfg, session_id, text, session_params, timeout_s)
    _clock["t"] += 25.0
    return r


_mono_bak = bot._monotonic
_det_bak = _cx.detect_intent_text
bot._monotonic = _fake_monotonic
_cx.detect_intent_text = _fake_detect_slow
try:
    novo_contato(48, wa_id="5571900005555")
    STORE["bot_states"]["48"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    for _ in range(4):
        CX_SCRIPT.append(_cx_ok("Sorry something went wrong.", handoff_request=False))
    _n_calls = len(CX_CALLS)
    _clock["t"] = 1000.0
    rh = envia(48, "quero agendar")
    _calls_h = CX_CALLS[_n_calls:]
    # t=0 1a chamada (60s de teto) -> t=25 reenvio 1 (35s restantes) -> t=50
    # reenvio 2 (10s restantes) -> t=75: restam -15s < 5s -> para.
    check(len(_calls_h) == 3, "orcamento de 60s: 1 chamada + 2 reenvios (o 3o nao cabe)")
    check(_calls_h[0]["timeout_s"] is None, "1a chamada usa o teto inteiro (default do conector)")
    check(len(_calls_h) > 1 and _calls_h[1]["timeout_s"] is not None
          and abs(_calls_h[1]["timeout_s"] - 35.0) < 0.01,
          "reenvio 1 recebe o que sobrou (35s)")
    check(len(_calls_h) > 2 and abs(_calls_h[2]["timeout_s"] - 10.0) < 0.01,
          "reenvio 2 recebe o que sobrou (10s)")
    check(isinstance(rh, str) and "Sorry" not in rh and "operador humano" in rh.lower(),
          "orcamento esgotado com frase de erro -> handoff generico (nunca o erro cru)")
    check(STORE["wa_contacts"]["48"].get("bot_completed") is True,
          "orcamento esgotado -> handoff (bot_completed=True)")
    CX_SCRIPT.clear()
finally:
    bot._monotonic = _mono_bak
    _cx.detect_intent_text = _det_bak
    _real.httpx = _httpx  # restaura o modulo real no conector carregado por spec

print("\n=== w: P2b — politica LGPD como DATA + conteudo da aba Sistema (system_settings) ===")
# A clinica edita data/link/aviso na aba Sistema (system_settings). Datas
# RELATIVAS a hoje (Brasilia): o sim passa em qualquer dia. bot_service
# importou get_system_settings por nome — o patch e no modulo bot.
import lgpd_bot  # noqa: E402
from datetime import timedelta  # noqa: E402

_BR = timezone(timedelta(hours=-3))
_HOJE_BR = datetime.now(_BR).date()
_DATA_POL = (_HOJE_BR - timedelta(days=10)).isoformat()
_ACEITE_ANTIGO = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
_ACEITE_RECENTE = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
_SYS = {"bot_enabled": True}
_sys_bak = bot.get_system_settings
bot.get_system_settings = lambda: dict(_SYS)
try:
    # (a) sem data e sem campos: aviso e versao exatamente como antes.
    _cfg0 = bot.lgpd_policy_config({"bot_enabled": True}, _AI_CFG, cx=True)
    check(_cfg0["aviso"] == (_AI_CFG["lgpd_notice"] + "\n(Política de Privacidade: "
                             + _AI_CFG["lgpd_privacy_url"] + ")\n\nPodemos continuar?"),
          "sem campos na aba Sistema: aviso CX identico ao formato antigo (settings.ai)")
    check(_cfg0["policy_date"] is None and _cfg0["version"] == "varizemed-test-2026-07",
          "sem data: versao gravada segue a do settings.ai")
    novo_contato(60, wa_id="5571960000001", lgpd_consent=True, lgpd_consent_at=_ACEITE_ANTIGO,
                 lgpd_policy_version="varizemed-test-2026-07")
    STORE["bot_states"]["60"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    CX_SCRIPT.append(_cx_ok("Sem data configurada, sigo normal."))
    _n = len(CX_CALLS)
    r = envia(60, "oi de novo")
    check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
          "sem data: aceite antigo com estado aceito vai direto ao agente (nada muda no deploy)")

    # (b) data ANTERIOR ao aceite: passa direto, sem aviso.
    _SYS["lgpd_policy_date"] = _DATA_POL
    novo_contato(61, wa_id="5571960000002", lgpd_consent=True, lgpd_consent_at=_ACEITE_RECENTE,
                 lgpd_policy_version="varizemed-test-2026-07")
    STORE["bot_states"]["61"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    CX_SCRIPT.append(_cx_ok("Claro, temos horario na terca."))
    _n = len(CX_CALLS)
    r = envia(61, "tem horario terca?")
    check(isinstance(r, str) and "terca" in r and len(CX_CALLS) == _n + 1
          and CX_CALLS[-1]["text"] == "tem horario terca?",
          "data anterior ao aceite: segue direto pro agente, sem aviso")
    # Hidratacao (ciclo novo, bot_states sem lgpd_*): com data vale a regra por
    # data — versao de texto diferente NAO repergunta mais.
    novo_contato(62, wa_id="5571960000003", lgpd_consent=True, lgpd_consent_at=_ACEITE_RECENTE,
                 lgpd_policy_version="varizemed-velha-2020")
    CX_SCRIPT.append(_cx_ok("Bem-vindo de volta."))
    _n = len(CX_CALLS)
    r = envia(62, "voltei")
    check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
          "hidratacao com data: aceite posterior a politica vale mesmo com versao de texto diferente")
    check(STORE["bot_states"]["62"].get("lgpd_consent") is True, "estado hidratado persistido")

    # (c) data POSTERIOR ao aceite com estado "aceito": aviso reaparece, a
    # mensagem vira user_first_input; novo "sim" grava versao = data e segue.
    novo_contato(63, wa_id="5571960000004", lgpd_consent=True, lgpd_consent_at=_ACEITE_ANTIGO,
                 lgpd_policy_version="varizemed-test-2026-07")
    STORE["bot_states"]["63"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx",
                                 "user_first_input": "mensagem velha do 1o aceite"}
    _n = len(CX_CALLS)
    r = envia(63, "quero remarcar minha consulta")
    check(isinstance(r, dict) and r.get("type") == "interactive_buttons"
          and "Podemos continuar?" in r.get("body", ""),
          "aceite anterior a politica: aviso LGPD reaparece (botoes)")
    check([b.get("id") for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"]
          if isinstance(r, dict) else False, "aviso com os botoes Sim/Nao de sempre")
    check(len(CX_CALLS) == _n, "agente NAO e chamado enquanto o aceite esta desatualizado")
    _st63 = STORE["bot_states"]["63"]
    check(_st63.get("lgpd_consent") is None and _st63.get("lgpd_status") == "awaiting",
          "estado rebaixado e persistido (lgpd_consent None, aguardando)")
    check(_st63.get("user_first_input") == "quero remarcar minha consulta",
          "mensagem atual guardada como user_first_input")
    check(bot.lgpd_consent_resolved(_st63, STORE["wa_contacts"]["63"]) is False,
          "buffer: consentimento nao resolvido enquanto aguarda o novo aceite")
    _audit_n = len(AUDIT)
    CX_SCRIPT.append(_cx_ok("Vamos remarcar! Qual dia fica melhor?"))
    r = envia(63, "sim")
    _c63 = STORE["wa_contacts"]["63"]
    check(_c63.get("lgpd_policy_version") == _DATA_POL, "novo aceite grava versao = data da politica")
    check(lgpd_bot.data_aceite_br(_c63.get("lgpd_consent_at")) == _HOJE_BR,
          "novo aceite carimba lgpd_consent_at de agora")
    check(any(a["action"] == "LGPD_CONSENT_ACCEPTED" and _DATA_POL in a["detail"]
              for a in AUDIT[_audit_n:]), "audit do novo aceite cita a data da politica")
    check(len(CX_CALLS) == _n + 1 and CX_CALLS[-1]["text"] == "quero remarcar minha consulta",
          "apos o aceite, o agente recebe o user_first_input")
    check(isinstance(r, str) and "Vamos remarcar" in r, "resposta do agente chega ao paciente")
    CX_SCRIPT.append(_cx_ok("Terca as 10h esta livre."))
    r = envia(63, "pode ser terca")
    check(isinstance(r, str) and "Terca" in r and len(CX_CALLS) == _n + 2,
          "turno seguinte vai direto (sem loop de reconsentimento)")

    # (d) aviso e link da aba Sistema substituem os do settings.ai — campo a campo.
    _SYS["lgpd_notice"] = "Aviso novo da clinica: tratamos seus dados de saude conforme a LGPD."
    _SYS["lgpd_privacy_url"] = "https://clinica.example/politica-2026"
    novo_contato(64, wa_id="5571960000005")
    r = envia(64, "oi")
    _body = r.get("body", "") if isinstance(r, dict) else ""
    check(_body == (_SYS["lgpd_notice"] + "\n(Política de Privacidade: "
                    + _SYS["lgpd_privacy_url"] + ")\n\nPodemos continuar?"),
          "aviso e link da aba Sistema no formato do CX")
    check(_AI_CFG["lgpd_notice"] not in _body and _AI_CFG["lgpd_privacy_url"] not in _body,
          "nada do settings.ai quando a aba Sistema esta preenchida")
    _SYS["lgpd_privacy_url"] = ""
    novo_contato(65, wa_id="5571960000006")
    r = envia(65, "oi")
    _body = r.get("body", "") if isinstance(r, dict) else ""
    check(_SYS["lgpd_notice"] in _body and _AI_CFG["lgpd_privacy_url"] in _body,
          "link vazio na aba Sistema: cai no link do settings.ai (precedencia por campo)")
    _SYS["lgpd_notice"] = ""

    # (e) lgpd_consent_resolved (buffer do webhook) com a regra por data.
    _ctt_old = {"lgpd_consent": True, "lgpd_consent_at": _ACEITE_ANTIGO,
                "lgpd_policy_version": "varizemed-test-2026-07"}
    _ctt_new = {"lgpd_consent": True, "lgpd_consent_at": _ACEITE_RECENTE,
                "lgpd_policy_version": "outra-versao"}
    _sys_dt = {"lgpd_policy_date": _DATA_POL}
    _acc = {"lgpd_consent": True, "lgpd_status": "accepted"}
    check(bot.lgpd_consent_resolved(_acc, _ctt_old, _AI_CFG, _sys_dt) is False,
          "resolved: estado aceito + aceite desatualizado -> False")
    check(bot.lgpd_consent_resolved(_acc, _ctt_old, _AI_CFG, {}) is True,
          "resolved: sem data, estado aceito vale como sempre")
    check(bot.lgpd_consent_resolved(_acc, _ctt_new, _AI_CFG, _sys_dt) is True,
          "resolved: aceite em dia com a politica -> True")
    check(bot.lgpd_consent_resolved({}, _ctt_old, _AI_CFG, _sys_dt) is False
          and bot.lgpd_consent_resolved({}, _ctt_new, _AI_CFG, _sys_dt) is True,
          "resolved: hidratacao pela data (antigo nao, recente sim mesmo com outra versao)")
    check(bot.lgpd_consent_resolved({}, _ctt_new, _AI_CFG, {}) is False,
          "resolved: sem data, hidratacao segue exigindo a versao de texto")
    check(bot.lgpd_consent_resolved({"lgpd_consent": False}, _ctt_new, _AI_CFG, _sys_dt) is False,
          "resolved: recusa no estado nunca vale")
    check(bot.lgpd_consent_resolved(_acc, _ctt_old, _AI_CFG) is False,
          "resolved: sem sys_settings explicito le system_settings (1 leitura) e aplica a data")
    _sys_fut = {"lgpd_policy_date": (_HOJE_BR + timedelta(days=3)).isoformat()}
    check(bot.lgpd_consent_resolved(_acc, _ctt_old, _AI_CFG, _sys_fut) is True,
          "data futura gravada fora da UI e ignorada (sem loop de reconsentimento)")

    # (f) aceite legado sem lgpd_consent_at continua valido.
    _ctt_leg = {"lgpd_consent": True, "lgpd_policy_version": "varizemed-velha-2020"}
    check(bot.lgpd_consent_resolved(_acc, _ctt_leg, _AI_CFG, _sys_dt) is True,
          "resolved: aceite legado sem lgpd_consent_at vale")
    novo_contato(66, wa_id="5571960000007", lgpd_consent=True)
    STORE["bot_states"]["66"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    CX_SCRIPT.append(_cx_ok("Ola! Em que posso ajudar?"))
    _n = len(CX_CALLS)
    r = envia(66, "oi")
    check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
          "turno: aceite legado sem carimbo segue direto pro agente")
    novo_contato(67, wa_id="5571960000008", lgpd_consent=True, lgpd_consent_at=_ACEITE_RECENTE,
                 lgpd_revoked=True)
    r = envia(67, "oi")
    check(isinstance(r, dict) and r.get("type") == "interactive_buttons",
          "revogado nunca hidrata, com data tambem (guard J-3)")
    CX_SCRIPT.clear()
finally:
    bot.get_system_settings = _sys_bak

print("\n=== x: P2b — validacao do save da aba Sistema (funcao pura) ===")


def _rejeita(campos, hoje=None, atual=None):
    try:
        lgpd_bot.validar_config_lgpd(campos, hoje or _HOJE_BR, atual)
    except ValueError:
        return True
    return False


check(_rejeita({"lgpd_policy_date": (_HOJE_BR + timedelta(days=1)).isoformat()}),
      "data futura (amanha em Brasilia) e rejeitada")
check(not _rejeita({"lgpd_policy_date": _HOJE_BR.isoformat()}), "data de hoje e aceita")
check(_rejeita({"lgpd_policy_date": "01/07/2026"}) and _rejeita({"lgpd_policy_date": "2026-02-30"}),
      "data fora do formato AAAA-MM-DD ou inexistente e rejeitada")
check(_rejeita({"lgpd_privacy_url": "http://clinica.example/politica"})
      and _rejeita({"lgpd_privacy_url": "https://"})
      and _rejeita({"lgpd_privacy_url": "https://clinica .example"}),
      "link sem https://, so o esquema ou com espaco e rejeitado")
check(_rejeita({"lgpd_notice": "x" * 901}) and not _rejeita({"lgpd_notice": "x" * 900}),
      "aviso: 901 caracteres rejeitado, 900 aceito")
check(_rejeita({"lgpd_notice": "x" * 900, "lgpd_privacy_url": "https://e.x/" + "p" * 100}),
      "aviso + link que passam de 1024 no corpo do WhatsApp sao rejeitados")
check(_rejeita({"lgpd_privacy_url": "https://e.x/" + "p" * 100}, atual={"lgpd_notice": "x" * 900}),
      "PUT parcial: link novo conferido contra o aviso ja gravado")
_ok = lgpd_bot.validar_config_lgpd(
    {"lgpd_policy_date": f" {_DATA_POL} ", "lgpd_privacy_url": " https://c.example/p ",
     "lgpd_notice": " linha 1\r\nlinha 2 "}, _HOJE_BR)
check(_ok == {"lgpd_policy_date": _DATA_POL, "lgpd_privacy_url": "https://c.example/p",
              "lgpd_notice": "linha 1\nlinha 2"},
      "valores validos normalizados (trim, quebra de linha)")
check(lgpd_bot.validar_config_lgpd(
    {"lgpd_policy_date": "", "lgpd_privacy_url": None, "lgpd_notice": ""}, _HOJE_BR)
      == {"lgpd_policy_date": "", "lgpd_privacy_url": "", "lgpd_notice": ""},
      "campos vazios sao validos (voltam ao fallback)")

print("\n=== y: desfecho_bot do agente -> bot_outcome no contato (P5, reabertura 2.2.5) ===")
# Contrato: docs/CX_RETOMADA_LOTE_DEV_IA.md, pedido 3. O param persiste na
# sessao CX e volta em todo turno seguinte: o CRM so grava quando MUDA.
import logging as _logging  # noqa: E402


class _ListHandler(_logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


_lh = _ListHandler()
_bot_logger = _logging.getLogger("castro_crm.bot")
_bot_logger.addHandler(_lh)
try:
    novo_contato(70, wa_id="5571970000001")
    STORE["bot_states"]["70"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}

    # (a) escalar do contrato -> gravado com carimbo datetime.
    CX_SCRIPT.append(_cx_ok("Segue o link para agendar: marcaconsultas.com.br/Varizemed",
                            parameters={"desfecho_bot": "link_enviado"}))
    r = envia(70, "quero agendar")
    _c70 = STORE["wa_contacts"]["70"]
    check(isinstance(r, str) and "marcaconsultas" in r, "resposta da Val segue normal no turno do desfecho")
    check(_c70.get("bot_outcome") == "link_enviado" and isinstance(_c70.get("bot_outcome_at"), datetime),
          "desfecho_bot escalar gravado no contato (bot_outcome + bot_outcome_at datetime)")

    # (b) mesmo valor no turno seguinte (sessao CX persiste o param) -> sem write.
    STORE["wa_contacts"]["70"]["bot_outcome_at"] = "SENTINELA"
    CX_SCRIPT.append(_cx_ok("Qualquer duvida estou aqui.", parameters={"desfecho_bot": "link_enviado"}))
    envia(70, "obrigado")
    check(STORE["wa_contacts"]["70"].get("bot_outcome_at") == "SENTINELA",
          "mesmo desfecho repetido NAO regrava o contato (sem write por turno)")

    # (c) struct {desfecho_bot: valor} (regressao de 2026-07-29) -> desembrulhado.
    CX_SCRIPT.append(_cx_ok("Que otimo, consulta marcada!",
                            parameters={"desfecho_bot": {"desfecho_bot": "agendado"}}))
    envia(70, "ja marquei minha consulta")
    _c70 = STORE["wa_contacts"]["70"]
    check(_c70.get("bot_outcome") == "agendado" and isinstance(_c70.get("bot_outcome_at"), datetime),
          "desfecho_bot em struct e desembrulhado pelo helper do conector e gravado")

    # (d) valor fora da lista -> ignorado com log; o gravado fica intacto.
    STORE["wa_contacts"]["70"]["bot_outcome_at"] = "SENTINELA"
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Certo.", parameters={"desfecho_bot": "marcou_talvez"}))
    envia(70, "talvez")
    _c70 = STORE["wa_contacts"]["70"]
    check(_c70.get("bot_outcome") == "agendado" and _c70.get("bot_outcome_at") == "SENTINELA",
          "desfecho fora do contrato e ignorado (contato intacto)")
    _warn = [x.getMessage() for x in _lh.records
             if x.levelno == _logging.WARNING and "desfecho_bot fora do contrato" in x.getMessage()]
    check(len(_warn) == 1 and "marcou_talvez" in _warn[0],
          "valor fora do contrato gera 1 log de aviso (valor com cara de enum aparece)")
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Certo.", parameters={"desfecho_bot": "Maria Souza 31 99999-0000"}))
    envia(70, "meu nome")
    _warn = [x.getMessage() for x in _lh.records if "desfecho_bot fora do contrato" in x.getMessage()]
    check(len(_warn) == 1 and "Maria" not in _warn[0] and "<str>" in _warn[0],
          "valor livre fora do contrato NAO vaza no log (so o tipo)")

    # (e) param ausente ou null -> nada muda, sem aviso.
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Ok.", parameters={"desfecho_bot": None}))
    envia(70, "ok")
    CX_SCRIPT.append(_cx_ok("Ok."))
    envia(70, "ok de novo")
    _c70 = STORE["wa_contacts"]["70"]
    check(_c70.get("bot_outcome") == "agendado" and _c70.get("bot_outcome_at") == "SENTINELA"
          and not [x for x in _lh.records if "desfecho_bot" in x.getMessage()],
          "param null ou ausente nao mexe no contato nem loga")

    # (f) Val 4.11 (router de 06/10): o param real e scheduling_outcome;
    # link_oferecido vira link_enviado (vocabulario do plano), sem aviso.
    STORE["wa_contacts"]["70"]["bot_outcome"] = None
    STORE["wa_contacts"]["70"]["bot_outcome_at"] = "SENTINELA"
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Segue o link para agendar.", parameters={"scheduling_outcome": "link_oferecido"}))
    envia(70, "quero o link")
    _c70 = STORE["wa_contacts"]["70"]
    check(_c70.get("bot_outcome") == "link_enviado" and isinstance(_c70.get("bot_outcome_at"), datetime),
          "scheduling_outcome=link_oferecido (Val 4.11) grava bot_outcome=link_enviado")
    check(not [x for x in _lh.records if "fora do contrato" in x.getMessage()],
          "alias do vocabulario da Val nao gera aviso")

    # (g) encaminhado_atendente e handoff, nao desfecho com a Val: ignorado em silencio.
    STORE["wa_contacts"]["70"]["bot_outcome"] = None
    STORE["wa_contacts"]["70"]["bot_outcome_at"] = "SENTINELA"
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Vou te encaminhar.", parameters={"scheduling_outcome": "encaminhado_atendente"}))
    envia(70, "quero atendente")
    _c70 = STORE["wa_contacts"]["70"]
    check(_c70.get("bot_outcome") is None and _c70.get("bot_outcome_at") == "SENTINELA"
          and not [x for x in _lh.records if "fora do contrato" in x.getMessage()],
          "scheduling_outcome=encaminhado_atendente nao e desfecho: contato intacto, sem aviso")

    # (h) struct no nome novo e precedencia do desfecho_bot.
    CX_SCRIPT.append(_cx_ok("Link.", parameters={"scheduling_outcome": {"scheduling_outcome": "link_oferecido"}}))
    envia(70, "link de novo")
    check(STORE["wa_contacts"]["70"].get("bot_outcome") == "link_enviado",
          "struct {scheduling_outcome: valor} desembrulhado e gravado")
    CX_SCRIPT.append(_cx_ok("Marcado.", parameters={"desfecho_bot": "agendado", "scheduling_outcome": "link_oferecido"}))
    envia(70, "ja marquei")
    check(STORE["wa_contacts"]["70"].get("bot_outcome") == "agendado",
          "desfecho_bot valido tem precedencia sobre scheduling_outcome")

    # (i) valor fora do contrato no nome novo: 1 aviso nomeando o param.
    STORE["wa_contacts"]["70"]["bot_outcome_at"] = "SENTINELA"
    _lh.records.clear()
    CX_SCRIPT.append(_cx_ok("Ok.", parameters={"scheduling_outcome": "sei_la"}))
    envia(70, "ok")
    _warn = [x.getMessage() for x in _lh.records if "scheduling_outcome fora do contrato" in x.getMessage()]
    check(len(_warn) == 1 and "sei_la" in _warn[0]
          and STORE["wa_contacts"]["70"].get("bot_outcome_at") == "SENTINELA",
          "scheduling_outcome fora do contrato: 1 aviso nomeando o param, contato intacto")
    CX_SCRIPT.clear()
finally:
    _bot_logger.removeHandler(_lh)

print("\n=== omit_session_params: param que o agente declara com outro tipo (Hugo, 2026-10-23) ===")
_AI_CFG["omit_session_params"] = ["retorno_previsto", "user_id", "lgpd_consent", "inexistente"]
try:
    CX_CALLS.clear()
    CX_SCRIPT.append(_cx_ok("Certo."))
    envia(70, "mais uma pergunta")
    _p = CX_CALLS[-1]["params"] if CX_CALLS else {}
    check(bool(CX_CALLS) and "retorno_previsto" not in _p,
          "retorno_previsto omitido para o tenant que configurou")
    check(str(_p.get("user_id") or "").startswith("+") and _p.get("lgpd_consent") is True,
          "user_id e lgpd_consent nunca sao omitidos (contrato do gate)")
    check(isinstance(_p.get("fora_do_expediente"), bool) and _p.get("tenant_id") == _TENANT_ID,
          "params fora da lista seguem iguais")
finally:
    _AI_CFG.pop("omit_session_params", None)
    CX_SCRIPT.clear()

print("\n=== lgpd_by_agent: o agente trata a LGPD, sem aviso do CRM (Hugo/Hubloc, 2026-10-23) ===")
_AI_CFG["lgpd_by_agent"] = True
_aceites_antes = sum(1 for a in AUDIT if a["action"] == "LGPD_CONSENT_ACCEPTED")
try:
    CX_CALLS.clear()
    novo_contato(88, wa_id="5571988887777")
    CX_SCRIPT.append(_cx_ok("Aqui é o Hugo, atendente virtual."))
    _r88 = envia(88, "Vim pelo site da Hub Loc")
    check(isinstance(_r88, str) and "Hugo" in _r88,
          "1a mensagem vai direto ao agente, sem o aviso LGPD do CRM")
    check(len(CX_CALLS) == 1 and CX_CALLS[0]["text"] == "Vim pelo site da Hub Loc",
          "agente recebe o texto original no 1o turno")
    check(bool(CX_CALLS) and "lgpd_consent" not in CX_CALLS[0]["params"],
          "CRM nao afirma lgpd_consent sem gate local")
    check(not STORE["wa_contacts"]["88"].get("lgpd_consent")
          and sum(1 for a in AUDIT if a["action"] == "LGPD_CONSENT_ACCEPTED") == _aceites_antes,
          "CRM nao grava prova de aceite (fica com o agente)")
finally:
    _AI_CFG.pop("lgpd_by_agent", None)
    CX_SCRIPT.clear()

print("\n=== Continuar do lote (ADR 0013 item 4): origem=retomada_lote por UM turno ===")
novo_contato(61, wa_id="5571999990061")
STORE.setdefault("bot_states", {})["61"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
bot.queue_cx_session_params(61, {"origem": "retomada_lote"})
check(STORE["bot_states"]["61"].get("pending_session_params") == {"origem": "retomada_lote"},
      "queue_cx_session_params grava pending_session_params em bot_states")
CX_SCRIPT.append(_cx_ok("Que bom te ver de novo! Como posso ajudar?"))
envia(61, "Quero continuar o atendimento.")
_p1 = CX_CALLS[-1]["params"]
check(_p1.get("origem") == "retomada_lote", "1o turno apos o clique: origem=retomada_lote vai ao agente")
check(STORE["bot_states"]["61"].get("pending_session_params") == {}
      and STORE["bot_states"]["61"].get("clear_session_params") == ["origem"],
      "baixa gravada antes do DetectIntent: pendente vazio + limpeza agendada")
CX_SCRIPT.append(_cx_ok("Claro."))
envia(61, "quero marcar")
_p2 = CX_CALLS[-1]["params"]
check("origem" in _p2 and _p2["origem"] is None, "turno seguinte: origem=None (nao fica preso na sessao)")
check(STORE["bot_states"]["61"].get("clear_session_params") == [], "limpeza consumida")
CX_SCRIPT.append(_cx_ok("Ok."))
envia(61, "obrigado")
check("origem" not in CX_CALLS[-1]["params"], "3o turno: sem a chave origem")

print("\n=== Metadados dos turnos para lembretes: resposta, LGPD, falha e handoff ===")
_meta = {}
CX_SCRIPT.append(_cx_ok("Qual seu nome?"))
asyncio.run(bot.process_bot_message_async(61, "Uma pergunta nova", turn_meta=_meta))
check(_meta.get("kind") == "cx_reply", "resposta normal tem tipo cx_reply")
novo_contato(97)
_meta = {}
asyncio.run(bot.process_bot_message_async(97, "Quero atendimento", turn_meta=_meta))
check(_meta.get("kind") == "lgpd_notice", "aviso LGPD nao vira resposta elegivel")
_meta = {}
asyncio.run(bot.process_bot_message_async(97, "Não", turn_meta=_meta))
check(_meta.get("kind") == "lgpd_refusal", "recusa tem tipo proprio")
_meta = {}
CX_SCRIPT.append({"ok": False})
asyncio.run(bot.process_bot_message_async(61, "Outra pergunta", turn_meta=_meta))
check(_meta.get("kind") == "engine_fallback", "instabilidade nao arma lembretes")
_meta = {}
CX_SCRIPT.append({"ok": False})
_real_finalize = bot._finalize_cx_handoff
def _handoff_persist_fails(*args, **kwargs):
    raise RuntimeError("falha local simulada")
bot._finalize_cx_handoff = _handoff_persist_fails
try:
    asyncio.run(bot.process_bot_message_async(61, "Nova tentativa", turn_meta=_meta))
    check(_meta.get("kind") == "handoff", "handoff por falha nao arma mesmo sem persistencia")
finally:
    bot._finalize_cx_handoff = _real_finalize

print("\n=== z: botoes do aviso DEPOIS do aceite — 2o Sim ignorado, Nao vale como recusa (PO 2026-11-13) ===")
# Contato 1779 da varizemed, 12/11: tocou "Sim" no aviso e, 9 s depois, no
# lembrete. O 2o toque ia ao agente como o texto "lgpd_aceitar" e a Val
# respondia duas vezes. Com o aceite ja dado, "Nao" tambem ia ao agente e o
# aceite seguia valendo. Decisao do PO: 2o "Sim" e ignorado; "Nao" vale como
# recusa. So o TOQUE (id exato do botao) — texto digitado segue ao agente.
from datetime import date as _date  # noqa: E402

CX_SCRIPT.clear()


def _n_audit(action):
    return sum(1 for a in AUDIT if a["action"] == action)


def _aceita(cid, wa_id, primeira="Oi, quero agendar uma avaliacao"):
    """Contato novo que ve o aviso e aceita tocando em Sim (1 turno do agente)."""
    novo_contato(cid, wa_id=wa_id)
    envia(cid, primeira)
    CX_SCRIPT.append(_cx_ok("Oi! Sou a Val. Qual o seu nome?"))
    return envia(cid, "lgpd_aceitar")


print("  -- z1: segundo toque em Sim --")
_aceita(110, "5571990000110")
_calls = len(CX_CALLS)
_aceites = _n_audit("LGPD_CONSENT_ACCEPTED")
bot.queue_cx_session_params(110, {"origem": "retomada_lote"})
_meta = {}
r = asyncio.run(bot.process_bot_message_async(110, "lgpd_aceitar", turn_meta=_meta))
check(r is None, "2o toque em Sim: sem resposta")
check(len(CX_CALLS) == _calls,
      "2o toque em Sim: agente NAO e chamado (o id do botao nao vira fala do paciente)")
check(_n_audit("LGPD_CONSENT_ACCEPTED") == _aceites, "2o toque em Sim: nenhum aceite novo no audit")
check(STORE["bot_states"]["110"].get("pending_session_params") == {"origem": "retomada_lote"},
      "2o toque em Sim: params de UM turno nao sao baixados sem turno do agente")
check(STORE["bot_states"]["110"].get("lgpd_consent") is True
      and STORE["wa_contacts"]["110"].get("lgpd_consent") is True,
      "2o toque em Sim: aceite segue valendo (estado e contato)")
check(_meta.get("kind") == "lgpd_repeat", "2o toque em Sim: turno sem resposta, tipo lgpd_repeat")
r = envia(110, "  LGPD_ACEITAR ")
check(r is None and len(CX_CALLS) == _calls, "id do botao com caixa/espacos diferentes tambem e toque")
CX_SCRIPT.append(_cx_ok("Prazer, Ana! Em que posso ajudar?"))
envia(110, "Meu nome e Ana")
check(len(CX_CALLS) == _calls + 1 and CX_CALLS[-1]["text"] == "Meu nome e Ana"
      and CX_CALLS[-1]["params"].get("origem") == "retomada_lote",
      "turno seguinte vai ao agente com o texto digitado e os params que ficaram pendentes")

print("  -- z2: texto DIGITADO depois do aceite nao e toque --")
for _txt in ("sim", "Não", "nao", "ok", "recusar", "Recuso", "não aceito", "prefiro não", "n",
             "aceito", "lgpd recusar"):
    CX_SCRIPT.append(_cx_ok("Entendi."))
    _n = len(CX_CALLS)
    envia(110, _txt)
    check(len(CX_CALLS) == _n + 1 and CX_CALLS[-1]["text"] == _txt
          and STORE["bot_states"]["110"].get("lgpd_consent") is True
          and STORE["wa_contacts"]["110"].get("lgpd_consent") is True,
          f"'{_txt}' digitado depois do aceite segue para o agente e nao mexe no aceite")
check(lgpd_bot.botao_lgpd("lgpd_aceitar") == "aceitar" and lgpd_bot.botao_lgpd(" LGPD_RECUSAR ") == "recusar",
      "botao_lgpd reconhece os dois ids")
check(all(lgpd_bot.botao_lgpd(t) == "" for t in
          ("sim", "Sim", "nao", "Não", "aceitar", "recusar", "lgpd recusar", "lgpd_aceitar.",
           "lgpd_recusar.", "lgpd_recusar!", "", None)),
      "botao_lgpd ignora texto digitado, inclusive o vocabulario de aceite/recusa")

print("  -- z3: toque em Nao depois do Sim --")
_aceita(111, "5571990000111")
_c111_antes = dict(STORE["wa_contacts"]["111"])
_calls = len(CX_CALLS)
_recusas = _n_audit("LGPD_CONSENT_REFUSED")
_meta = {}
r = asyncio.run(bot.process_bot_message_async(111, "lgpd_recusar", turn_meta=_meta))
_st = STORE["bot_states"]["111"]
_c = STORE["wa_contacts"]["111"]
check(isinstance(r, str) and "não podemos prosseguir" in r.lower() and "Clínica Varizemed agradece" in r,
      "Nao depois do Sim: despedida da recusa, com a marca do tenant")
check(len(CX_CALLS) == _calls, "Nao depois do Sim: agente NAO e chamado")
check(_st.get("lgpd_consent") is False and _st.get("lgpd_status") == "refused",
      "Nao depois do Sim: estado vira recusa")
check(_c.get("lgpd_consent") is False,
      "Nao depois do Sim: a prova no CONTATO deixa de valer (lgpd_consent=False)")
check(_c.get("lgpd_consent_at") == _c111_antes.get("lgpd_consent_at")
      and _c.get("lgpd_policy_version") == _c111_antes.get("lgpd_policy_version"),
      "data e versao do aceite anterior ficam como historico")
check(bool(_c.get("lgpd_refused_at")), "carimbo lgpd_refused_at gravado no contato")
check(not _c.get("lgpd_revoked"), "lgpd_revoked NAO e usado (revogacao da equipe, J-3 D8, e outra coisa)")
check(_n_audit("LGPD_CONSENT_REFUSED") == _recusas + 1
      and any(a["action"] == "LGPD_CONSENT_REFUSED" and "contato 111" in a["detail"]
              and "varizemed-test-2026-07" in a["detail"] for a in AUDIT),
      "audit LGPD_CONSENT_REFUSED com o contato e a versao da politica")
check(_meta.get("kind") == "lgpd_refusal",
      "tipo do turno lgpd_refusal (lembretes nao armam e a agenda e limpa)")
check(_st.get("user_first_input") == "", "1a mensagem do ciclo nao fica guardada para replay")
check(bot.lgpd_consent_resolved(_st, _c) is False,
      "lgpd_consent_resolved: nao resolvido (texto novo nao entra no buffer; serie B barrada)")
check(lgpd_bot.aceite_vigente(_c, _date(2020, 1, 1)) is False
      and bot._contact_consent_hydrates(_c, None, _AI_CFG) is False
      and bot.lgpd_consent_resolved({}, _c) is False,
      "prova do contato nao hidrata mais, com ou sem data de politica")

print("  -- z4: depois da recusa --")
r = envia(111, "lgpd_recusar")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar"]
      and _n_audit("LGPD_CONSENT_REFUSED") == _recusas + 1 and len(CX_CALLS) == _calls,
      "novo toque em Nao ja recusado: lembrete de recusa so com o botao Sim, sem despedida nem audit repetidos")

print("  -- z5: novo aceite depois da recusa --")
_aceites = _n_audit("LGPD_CONSENT_ACCEPTED")
# Carimbo antigo fixo no lugar do aceite anterior: a comparacao abaixo nao pode
# depender da resolucao do relogio (no Windows, dois aceites no mesmo tick).
_carimbo_antigo = "2020-01-01T00:00:00+00:00"
STORE["wa_contacts"]["111"]["lgpd_consent_at"] = _carimbo_antigo
r = envia(111, "lgpd_aceitar")
_c = STORE["wa_contacts"]["111"]
check(r == lgpd_bot._ACEITO_RESPOSTA and len(CX_CALLS) == _calls,
      "novo aceite por botao: so a confirmacao, sem reenviar ao agente a 1a mensagem antiga")
check(_c.get("lgpd_consent") is True and _n_audit("LGPD_CONSENT_ACCEPTED") == _aceites + 1
      and _c.get("lgpd_consent_at") != _carimbo_antigo
      and lgpd_bot.data_aceite_br(_c.get("lgpd_consent_at")) == _HOJE_BR
      and STORE["bot_states"]["111"].get("lgpd_consent") is True,
      "novo aceite volta a valer e grava prova nova (contato, estado e audit)")
CX_SCRIPT.append(_cx_ok("Que bom! Vamos continuar."))
envia(111, "quero marcar a avaliacao")
check(len(CX_CALLS) == _calls + 1 and CX_CALLS[-1]["text"] == "quero marcar a avaliacao",
      "depois do novo aceite a conversa volta ao agente")

_aceita(112, "5571990000112")
envia(112, "lgpd_recusar")
_n = len(CX_CALLS)
r = envia(112, "pensando bem, quero agendar")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar"]
      and len(CX_CALLS) == _n,
      "texto digitado depois da recusa: lembrete de recusa so com o botao Sim, sem agente")
CX_SCRIPT.append(_cx_ok("Claro, vamos agendar."))
r = envia(112, "lgpd_aceitar")
check(len(CX_CALLS) == _n + 1 and CX_CALLS[-1]["text"] == "pensando bem, quero agendar"
      and isinstance(r, str) and "vamos agendar" in r,
      "o que o paciente DIGITOU durante a recusa e o que vai ao agente no novo aceite")

print("  -- z6: recusa gravada durante o DetectIntent de outro turno --")
_real_detect = _cx.detect_intent_text


def _detect_com_recusa(cid_alvo, resposta):
    async def _fake(cfg, session_id, text, session_params=None, timeout_s=None):
        CX_CALLS.append({"cfg": dict(cfg), "session_id": session_id, "text": text,
                         "params": dict(session_params or {}), "timeout_s": timeout_s})
        # Enquanto o agente pensa, o toque em "Nao" e processado por outro turno.
        await bot.process_bot_message_async(cid_alvo, "lgpd_recusar")
        return resposta
    return _fake


_aceita(113, "5571990000113")
_cx.detect_intent_text = _detect_com_recusa(
    113, _cx_ok("Vou te passar para a equipe.", handoff_request=True, handoff_summary="quer agendar"))
try:
    r = envia(113, "Qual o endereco?")
finally:
    _cx.detect_intent_text = _real_detect
check(r is None, "recusa durante o DetectIntent: a resposta atrasada do agente e descartada")
check(not STORE["wa_contacts"]["113"].get("bot_completed"),
      "recusa durante o DetectIntent: o handoff pedido nesse turno nao acontece")
check(STORE.get("bot_states", {}).get("113", {}).get("lgpd_consent") is False
      and STORE["wa_contacts"]["113"].get("lgpd_consent") is False,
      "a recusa continua gravada (estado nao foi apagado pelo handoff; contato recusado)")

novo_contato(114, wa_id="5571990000114")
envia(114, "Quero agendar")
_cx.detect_intent_text = _detect_com_recusa(114, _cx_ok("Oi! Sou a Val."))
try:
    r = envia(114, "lgpd_aceitar")
finally:
    _cx.detect_intent_text = _real_detect
check(r is None and STORE["wa_contacts"]["114"].get("lgpd_consent") is False
      and STORE["bot_states"]["114"].get("lgpd_consent") is False,
      "Sim e Nao em sequencia rapida: nem a confirmacao nem a saudacao do agente saem depois da recusa")

print("  -- z7: estado apagado e ciclo novo --")
STORE["bot_states"].pop("113", None)
r = envia(113, "oi, voltei")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"],
      "estado apagado depois da recusa: o contato NAO hidrata e o aviso completo sai de novo")

novo_contato(115, wa_id="5571990000115", lgpd_consent=True,
             lgpd_consent_at="2026-08-05T00:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
CX_SCRIPT.append(_cx_ok("Ola de novo!"))
_n = len(CX_CALLS)
r = envia(115, "lgpd_aceitar")
check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
      "conversa nova com prova antiga (estado hidratado): o toque em Sim vai ao agente, paciente nao fica sem resposta")

# Estado do ciclo anterior que SOBREVIVEU (conversa encerrada por atendente:
# release_lead_to_bot faz merge e preserva lgpd_*): mesmo tratamento (achado
# da revisao de 13/11 — o criterio e o TEMPO desde o aceite, nao o estado).
novo_contato(126, wa_id="5571990000126", lgpd_consent=True,
             lgpd_consent_at="2026-08-05T00:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
STORE["bot_states"]["126"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx",
                              "human_active": False, "cx_fail_count": 0}
CX_SCRIPT.append(_cx_ok("Que bom te ver de novo!"))
_n = len(CX_CALLS)
r = envia(126, "lgpd_aceitar")
check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
      "conversa nova com o estado antigo preservado (encerrada por atendente): o toque em Sim vai ao agente")

# Janela do toque repetido: conta do carimbo do aceite no contato.
_aceita(127, "5571990000127")
STORE["wa_contacts"]["127"]["lgpd_consent_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
_n = len(CX_CALLS)
r = envia(127, "lgpd_aceitar")
check(r is None and len(CX_CALLS) == _n, "aceite ha 4 minutos: toque em Sim ainda e repeticao (ignorado)")
STORE["wa_contacts"]["127"]["lgpd_consent_at"] = (
    datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
CX_SCRIPT.append(_cx_ok("Oi! Posso ajudar?"))
r = envia(127, "lgpd_aceitar")
check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
      "aceite ha 6 minutos: toque em Sim segue ao agente (fora da janela)")
for _carimbo in (None, "", "ontem", 12345):
    STORE["wa_contacts"]["127"]["lgpd_consent_at"] = _carimbo
    CX_SCRIPT.append(_cx_ok("Certo."))
    _n = len(CX_CALLS)
    r = envia(127, "lgpd_aceitar")
    check(isinstance(r, str) and len(CX_CALLS) == _n + 1,
          f"carimbo do aceite ausente ou ilegivel ({_carimbo!r}): toque em Sim segue ao agente")
_agora = datetime.now(timezone.utc)
check(bot._lgpd_accepted_recently({"lgpd_consent_at": (_agora - timedelta(seconds=280)).isoformat()}) is True
      and bot._lgpd_accepted_recently({"lgpd_consent_at": (_agora - timedelta(seconds=320)).isoformat()}) is False,
      "janela do toque repetido: 280 s ainda dentro, 320 s ja fora")
check(bot._lgpd_accepted_recently({"lgpd_consent_at": (_agora + timedelta(seconds=30)).isoformat()}) is True
      and bot._lgpd_accepted_recently({"lgpd_consent_at": (_agora + timedelta(minutes=2)).isoformat()}) is False,
      "carimbo no futuro: folga de 60 s para relogios de instancias diferentes, nao mais que isso")
check(bot._lgpd_accepted_recently({"lgpd_consent_at": _agora.replace(tzinfo=None).isoformat()}) is True
      and bot._lgpd_accepted_recently({"lgpd_consent_at": _agora.isoformat().replace("+00:00", "Z")}) is True
      and bot._lgpd_accepted_recently({"lgpd_consent_at": _agora}) is True
      and bot._lgpd_accepted_recently(None) is False,
      "carimbo sem fuso, com Z ou como datetime e lido; contato ausente nao e recente")

# Falha do motor no turno do aceite: o paciente so recebeu o pedido de reenviar.
novo_contato(128, wa_id="5571990000128")
envia(128, "Oi quero agendar")
CX_SCRIPT.append(dict(_CX_FAIL))
r = envia(128, "lgpd_aceitar")
check(isinstance(r, str) and STORE["bot_states"]["128"].get("cx_fail_count") == 1
      and STORE["wa_contacts"]["128"].get("lgpd_consent") is True,
      "turno do aceite com falha do motor: aceite gravado e paciente recebe o pedido de reenviar")
CX_SCRIPT.append(_cx_ok("Oi! Sou a Val."))
_n = len(CX_CALLS)
r = envia(128, "lgpd_aceitar")
check(isinstance(r, str) and "Sou a Val" in r and len(CX_CALLS) == _n + 1,
      "novo toque em Sim depois da falha do motor: vai ao agente (paciente nao fica sem resposta)")
r = envia(128, "lgpd_aceitar")
check(r is None and len(CX_CALLS) == _n + 1,
      "com o agente ja tendo respondido, o toque seguinte volta a ser repeticao (ignorado)")

# Estado sem lgpd_* e step ja em "cx" (prova hidratada so em memoria, sem
# regravacao): a conferencia depois do DetectIntent nao pode calar o agente.
novo_contato(129, wa_id="5571990000129", lgpd_consent=True,
             lgpd_consent_at="2026-08-05T00:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
STORE["bot_states"]["129"] = {"step": "cx", "human_active": False}
CX_SCRIPT.append(_cx_ok("Claro!"))
r = envia(129, "qual o horario?")
check(r == "Claro!" and STORE["bot_states"]["129"].get("lgpd_consent") is None,
      "estado sem lgpd_* (aceite hidratado so em memoria): a resposta do agente sai")

# Ciclo novo de quem recusou fora da fase de bot (estado apagado, contato
# recusado): toque num botao antigo nao pode virar a "1a mensagem" do paciente.
novo_contato(131, wa_id="5571990000131", lgpd_consent=False,
             lgpd_refused_at="2026-11-13T12:00:00+00:00",
             lgpd_consent_at="2026-11-10T12:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
r = envia(131, "lgpd_aceitar")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"]
      and STORE["bot_states"]["131"].get("user_first_input") == "",
      "toque em botao antigo sem estado: o aviso sai de novo e o id NAO fica guardado como 1a mensagem")
_n = len(CX_CALLS)
r = envia(131, "lgpd_aceitar")
check(r == lgpd_bot._ACEITO_RESPOSTA and len(CX_CALLS) == _n
      and STORE["wa_contacts"]["131"].get("lgpd_consent") is True,
      "aceite em seguida: so a confirmacao; o id do botao nao vai ao agente como fala do paciente")

# Com DATA de politica configurada na aba Sistema (P2b).
_sys_bak_z = bot.get_system_settings
bot.get_system_settings = lambda: {"bot_enabled": True, "lgpd_policy_date": _DATA_POL}
try:
    novo_contato(132, wa_id="5571990000132", lgpd_consent=True,
                 lgpd_consent_at=_ACEITE_RECENTE, lgpd_policy_version=_DATA_POL)
    STORE["bot_states"]["132"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    _n = len(CX_CALLS)
    r = envia(132, "lgpd_recusar")
    check(isinstance(r, str) and "não podemos prosseguir" in r.lower() and len(CX_CALLS) == _n
          and STORE["wa_contacts"]["132"].get("lgpd_consent") is False
          and STORE["bot_states"]["132"].get("lgpd_consent") is False,
          "com data de politica e aceite em dia: toque em Nao vale como recusa (estado e contato)")
    novo_contato(133, wa_id="5571990000133", lgpd_consent=True,
                 lgpd_consent_at=_ACEITE_ANTIGO, lgpd_policy_version="varizemed-test-2026-07")
    STORE["bot_states"]["133"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    _n = len(CX_CALLS)
    r = envia(133, "lgpd_recusar")
    check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"]
          and STORE["bot_states"]["133"].get("user_first_input") == "" and len(CX_CALLS) == _n,
          "aceite anterior a politica vigente: o toque mostra o aviso novo e o id nao fica como 1a mensagem")
    r = envia(133, "lgpd_recusar")
    check(isinstance(r, str) and "não podemos prosseguir" in r.lower()
          and STORE["bot_states"]["133"].get("lgpd_consent") is False and len(CX_CALLS) == _n,
          "no aviso novo, o toque em Nao e a recusa de sempre")
finally:
    bot.get_system_settings = _sys_bak_z

novo_contato(116, wa_id="5571990000116", lgpd_consent=True,
             lgpd_consent_at="2026-08-05T00:00:00+00:00",
             lgpd_policy_version="varizemed-test-2026-07")
_n = len(CX_CALLS)
r = envia(116, "lgpd_recusar")
check(isinstance(r, str) and "não podemos prosseguir" in r.lower() and len(CX_CALLS) == _n
      and STORE["wa_contacts"]["116"].get("lgpd_consent") is False
      and STORE["bot_states"]["116"].get("lgpd_consent") is False,
      "ciclo novo com prova antiga: toque em Nao vale como recusa (estado e contato)")

print("  -- z8: gravacao da recusa e tudo ou nada --")
_aceita(118, "5571990000118")
_recusas = _n_audit("LGPD_CONSENT_REFUSED")
BATCH_FAIL["on"] = True
try:
    try:
        envia(118, "lgpd_recusar")
        _levantou = False
    except RuntimeError:
        _levantou = True
finally:
    BATCH_FAIL["on"] = False
check(_levantou, "falha na gravacao da recusa propaga (o webhook loga e o turno nao responde)")
check(STORE["bot_states"]["118"].get("lgpd_consent") is True
      and STORE["wa_contacts"]["118"].get("lgpd_consent") is True
      and _n_audit("LGPD_CONSENT_REFUSED") == _recusas,
      "falha na gravacao: nada fica pela metade (estado e contato seguem aceitos, sem audit)")
r = envia(118, "lgpd_recusar")
check(isinstance(r, str) and STORE["wa_contacts"]["118"].get("lgpd_consent") is False
      and STORE["bot_states"]["118"].get("lgpd_consent") is False,
      "novo toque depois da falha grava a recusa normalmente")

print("  -- z10: toque em Nao com o lead FORA da fase de bot (fila ou atendente) --")
# O webhook chama record_lgpd_refusal_outside_bot quando o bot nao vai rodar
# (contato com dono ou bot_completed); a ligacao e testada no sim_buffer_flow (23).
_aceite_121 = "2026-11-10T12:00:00+00:00"
novo_contato(121, wa_id="5571990000121", lgpd_consent=True, lgpd_consent_at=_aceite_121,
             lgpd_policy_version="varizemed-test-2026-07", bot_completed=True)
_recusas = _n_audit("LGPD_CONSENT_REFUSED")
_ok = bot.record_lgpd_refusal_outside_bot(121, dict(STORE["wa_contacts"]["121"]))
_c = STORE["wa_contacts"]["121"]
check(_ok is True and _c.get("lgpd_consent") is False and bool(_c.get("lgpd_refused_at"))
      and _c.get("lgpd_consent_at") == _aceite_121 and not _c.get("lgpd_revoked"),
      "fora do bot: recusa gravada no contato; aceite anterior fica como historico")
check("121" not in STORE.get("bot_states", {}),
      "fora do bot: nao cria bot_states para lead em atendimento humano")
check(_n_audit("LGPD_CONSENT_REFUSED") == _recusas + 1
      and any(a["action"] == "LGPD_CONSENT_REFUSED" and "contato 121" in a["detail"]
              and "fora da fase de bot" in a["detail"] for a in AUDIT),
      "fora do bot: audit LGPD_CONSENT_REFUSED marcado como fora da fase de bot")
check(_c.get("bot_completed") is True, "fora do bot: o lead continua na fila (nada alem do aceite muda)")
check(bot.record_lgpd_refusal_outside_bot(121, dict(STORE["wa_contacts"]["121"])) is False
      and _n_audit("LGPD_CONSENT_REFUSED") == _recusas + 1,
      "fora do bot: novo toque com a recusa ja gravada nao repete o registro")
STORE["wa_contacts"]["121"]["bot_completed"] = False  # devolvido ao agente depois
r = envia(121, "oi")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"],
      "fora do bot: na proxima fase de bot o aviso sai de novo (prova do contato nao hidrata)")

novo_contato(122, wa_id="5571990000122", lgpd_consent=True,
             lgpd_policy_version="varizemed-test-2026-07", assigned_to=7)
STORE["bot_states"]["122"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx",
                              "human_active": True, "user_first_input": "quero agendar"}
bot.record_lgpd_refusal_outside_bot(122, dict(STORE["wa_contacts"]["122"]))
_st = STORE["bot_states"]["122"]
check(_st.get("lgpd_consent") is False and _st.get("lgpd_status") == "refused"
      and _st.get("user_first_input") == "" and _st.get("human_active") is True and _st.get("step") == "cx",
      "fora do bot: estado que sobreviveu ao atendimento humano vira recusa junto (o resto e preservado)")
STORE["wa_contacts"]["122"]["assigned_to"] = None
STORE["bot_states"]["122"]["human_active"] = False
_n = len(CX_CALLS)
r = envia(122, "voltei")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar"]
      and len(CX_CALLS) == _n,
      "fora do bot: devolvido ao agente, o estado preservado NAO ressuscita o aceite")

novo_contato(123, wa_id="5571990000123", bot_completed=True)
_recusas = _n_audit("LGPD_CONSENT_REFUSED")
check(bot.record_lgpd_refusal_outside_bot(123, dict(STORE["wa_contacts"]["123"])) is False
      and "lgpd_consent" not in STORE["wa_contacts"]["123"]
      and _n_audit("LGPD_CONSENT_REFUSED") == _recusas,
      "fora do bot: contato que nunca aceitou nao muda e nao gera audit")

novo_contato(125, wa_id="5571990000125", lgpd_consent=True, bot_completed=True)
STORE["bot_states"]["125"] = {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
BATCH_FAIL["on"] = True
try:
    try:
        bot.record_lgpd_refusal_outside_bot(125, dict(STORE["wa_contacts"]["125"]))
        _levantou = False
    except RuntimeError:
        _levantou = True
finally:
    BATCH_FAIL["on"] = False
check(_levantou and STORE["wa_contacts"]["125"].get("lgpd_consent") is True
      and STORE["bot_states"]["125"].get("lgpd_consent") is True,
      "fora do bot: falha na gravacao propaga (o webhook loga) e nada fica pela metade")

novo_contato(130, wa_id="5571990000130", lgpd_consent=True,
             lgpd_policy_version="varizemed-test-2026-07", bot_completed=True)
_estado_release = {"pending_session_params": {}, "human_active": False}  # formato deixado pelo release
STORE["bot_states"]["130"] = dict(_estado_release)
bot.record_lgpd_refusal_outside_bot(130, dict(STORE["wa_contacts"]["130"]))
check(STORE["bot_states"]["130"] == _estado_release
      and STORE["wa_contacts"]["130"].get("lgpd_consent") is False,
      "fora do bot: estado sem lgpd_* nao e tocado (so o contato muda)")
STORE["wa_contacts"]["130"]["bot_completed"] = False
r = envia(130, "oi")
check(isinstance(r, dict) and [b["id"] for b in r.get("buttons", [])] == ["lgpd_aceitar", "lgpd_recusar"],
      "fora do bot: com estado sem lgpd_*, a proxima fase de bot mostra o aviso completo")

_AI_CFG["lgpd_by_agent"] = True
try:
    novo_contato(124, wa_id="5571990000124", lgpd_consent=True, bot_completed=True)
    check(bot.record_lgpd_refusal_outside_bot(124, dict(STORE["wa_contacts"]["124"])) is False
          and STORE["wa_contacts"]["124"].get("lgpd_consent") is True,
          "fora do bot: tenant com lgpd_by_agent nao muda (a LGPD e do agente)")
    # Rollback documentado do agente para o builtin: bot_engine vazio com a opcao
    # lgpd_by_agent esquecida em settings.ai. O gate volta a ser do CRM.
    _engine_bak = _AI_CFG["bot_engine"]
    try:
        # O motor e comparado como no dispatcher (sem caixa nem espacos).
        _AI_CFG["bot_engine"] = " Dialogflow_CX "
        novo_contato(135, wa_id="5571990000135", lgpd_consent=True, bot_completed=True)
        check(bot.record_lgpd_refusal_outside_bot(135, dict(STORE["wa_contacts"]["135"])) is False
              and STORE["wa_contacts"]["135"].get("lgpd_consent") is True,
              "fora do bot: motor CX escrito com caixa/espacos diferentes continua sendo CX (lgpd_by_agent vale)")
        _AI_CFG["bot_engine"] = ""
        novo_contato(134, wa_id="5571990000134", lgpd_consent=True, bot_completed=True)
        check(bot.record_lgpd_refusal_outside_bot(134, dict(STORE["wa_contacts"]["134"])) is True
              and STORE["wa_contacts"]["134"].get("lgpd_consent") is False,
              "fora do bot: no builtin (bot_engine vazio) a opcao lgpd_by_agent esquecida nao desliga o registro")
    finally:
        _AI_CFG["bot_engine"] = _engine_bak
finally:
    _AI_CFG.pop("lgpd_by_agent", None)

print("  -- z9: tenant com lgpd_by_agent nao muda --")
_AI_CFG["lgpd_by_agent"] = True
try:
    novo_contato(117, wa_id="5571990000117")
    CX_SCRIPT.append(_cx_ok("Aqui é o Hugo."))
    envia(117, "oi")
    for _id in ("lgpd_aceitar", "lgpd_recusar"):
        CX_SCRIPT.append(_cx_ok("Certo."))
        _n = len(CX_CALLS)
        envia(117, _id)
        check(len(CX_CALLS) == _n + 1 and CX_CALLS[-1]["text"] == _id,
              f"lgpd_by_agent: '{_id}' segue para o agente (sem gate local)")
    check(STORE["wa_contacts"]["117"].get("lgpd_consent") is None
          and not STORE["wa_contacts"]["117"].get("lgpd_refused_at"),
          "lgpd_by_agent: o CRM nao grava aceite nem recusa")
    # Estado gravado ANTES de o tenant passar a LGPD para o agente nao pode
    # desviar nem calar o bot: sem gate local, nada disso e consultado.
    novo_contato(119, wa_id="5571990000119", lgpd_consent=True,
                 lgpd_consent_at=datetime.now(timezone.utc).isoformat())
    STORE.setdefault("bot_states", {})["119"] = {
        "lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    CX_SCRIPT.append(_cx_ok("Certo."))
    _n = len(CX_CALLS)
    r = envia(119, "lgpd_aceitar")
    check(r == "Certo." and len(CX_CALLS) == _n + 1,
          "lgpd_by_agent com estado antigo aceito: o toque em Sim NAO e ignorado")
    novo_contato(120, wa_id="5571990000120")
    STORE["bot_states"]["120"] = {"lgpd_consent": False, "lgpd_status": "refused", "step": "lgpd"}
    CX_SCRIPT.append(_cx_ok("Olá!"))
    r = envia(120, "bom dia")
    check(r == "Olá!",
          "lgpd_by_agent com estado antigo recusado: a resposta do agente sai (bot nao fica mudo)")
finally:
    _AI_CFG.pop("lgpd_by_agent", None)
    CX_SCRIPT.clear()

print("\n" + "=" * 70)
if FAILS:
    print(f"RESULTADO: {len(FAILS)}/{CHECKS} checagens FALHARAM:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print(f"RESULTADO: TODAS as {CHECKS} checagens passaram.")
sys.exit(0)
