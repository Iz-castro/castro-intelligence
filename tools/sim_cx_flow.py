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
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(data)
        else:
            coll[self.doc_id] = dict(data)

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
    }
    base.update(extra)
    return base


_CX_FAIL = {
    "ok": False, "reply_text": "", "handoff_request": False,
    "handoff_summary": "", "conversation_complete": False, "user_name": "",
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

print("\n" + "=" * 70)
if FAILS:
    print(f"RESULTADO: {len(FAILS)}/{CHECKS} checagens FALHARAM:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print(f"RESULTADO: TODAS as {CHECKS} checagens passaram.")
sys.exit(0)
