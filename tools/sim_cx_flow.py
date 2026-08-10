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
    "varizemed-test": {"id": "varizemed-test", "plan": "ai_custom", "settings": {"ai": _AI_CFG}},
    "hubloc": {"id": "hubloc", "plan": "professional", "settings": {}},
}

_CURRENT_TENANT = {"id": _TENANT_ID}

_fc = types.ModuleType("firestore_common")
_fc.document = lambda name, doc_id: _DocRef(name, doc_id)
_fc.collection = lambda name: _CollRef(name)
_fc.utcnow = lambda: datetime.now(timezone.utc)
_fc.get_firestore_client = lambda: None
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


async def _fake_detect_intent(cfg, session_id, text, session_params=None):
    CX_CALLS.append({
        "cfg": dict(cfg),
        "session_id": session_id,
        "text": text,
        "params": dict(session_params or {}),
    })
    if CX_SCRIPT:
        return CX_SCRIPT.pop(0)
    return _cx_ok("(sem script)")


_cx = types.ModuleType("bot_engine_dialogflow")
_cx.detect_intent_text = _fake_detect_intent
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
CX_SCRIPT.append(_cx_ok(
    "Claro! Estou te transferindo para a equipe.",
    handoff_request=True,
    handoff_summary="Paciente quer agendar consulta de angiologia",
    user_name="Daniel",
))
r4 = envia(1, "quero falar com atendente")
contato1 = STORE["wa_contacts"]["1"]
check(contato1.get("bot_completed") is True, "handoff -> bot_completed=True")
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

print("\n" + "=" * 70)
if FAILS:
    print(f"RESULTADO: {len(FAILS)}/{CHECKS} checagens FALHARAM:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print(f"RESULTADO: TODAS as {CHECKS} checagens passaram.")
sys.exit(0)
