# -*- coding: utf-8 -*-

"""
Simulador LOCAL do fluxo do bot + consentimento LGPD com botoes interativos.

NAO toca em producao: Firestore e a WhatsApp Cloud API sao MOCKADOS em
memoria. Exercita o codigo real de bot_service.py, lgpd_bot.py e
bot_transport.py, reproduzindo o que o webhook faz no inbound (extrair
button_reply) e no outbound (montar o payload da Meta).

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_bot_flow.py

Sai com codigo 0 se todos os asserts passarem, 1 caso contrario.
"""

import os
import sys
import types
from datetime import datetime, timezone

# Permitir rodar de qualquer cwd: poe a raiz do projeto no path.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Saida UTF-8 (evita UnicodeEncodeError no console cp1252 do Windows).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# =========================================================================
# Firestore em memoria
# =========================================================================

STORE = {}          # { collection_name: { doc_id(str): {campos} } }
MESSAGES = []       # save_wa_message
AUDIT = []          # log_audit


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
    """Query minima: encadeia .where(campo, '==', valor) e itera .stream()."""
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
# Stubs de firestore_common e database (injetados antes dos imports reais)
# =========================================================================

_fc = types.ModuleType("firestore_common")
_fc.document = lambda name, doc_id: _DocRef(name, doc_id)
_fc.collection = lambda name: _CollRef(name)
_fc.utcnow = lambda: datetime.now(timezone.utc)
_fc.get_firestore_client = lambda: None
_fc.get_tenant_context = lambda: "hubloc"  # _get_dept_map cacheia por tenant
sys.modules["firestore_common"] = _fc

_DEPARTMENTS = [
    {"id": 1, "name": "Comercial", "bot_key": "comercial"},
    {"id": 2, "name": "Suporte", "bot_key": "sac"},
    {"id": 3, "name": "Financeiro", "bot_key": "financeiro"},
    {"id": 4, "name": "Administrativo", "bot_key": "administrativo"},
]

# tenant_service stubado: a despedida da recusa LGPD resolve tenant.name
# (data-driven; incidente Hub Loc x varizemed de 2026-08-10).
_ts = types.ModuleType("tenant_service")
_ts.get_tenant = lambda tid: ({"id": "hubloc", "name": "Hub Loc"}
                              if tid == "hubloc" else None)
sys.modules["tenant_service"] = _ts

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


# =========================================================================
# Imports REAIS (usam os stubs acima)
# =========================================================================

import bot_service as bot                    # noqa: E402
from bot_transport import (                  # noqa: E402
    build_outbound_payload,
    extract_interactive_inbound,
)


# =========================================================================
# Harness de asserts e impressao legivel
# =========================================================================

FAILS = []
CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"      ✓ {label}")
    else:
        FAILS.append(label)
        print(f"      ✗ FALHOU: {label}")


def _novo_contato(cid):
    STORE.setdefault("wa_contacts", {})[str(cid)] = {"id": cid}


def cliente_envia(cid, *, text=None, button_id=None, button_title=None):
    """Reproduz o caminho do webhook: extrai conteudo inbound, roda o gate
    do bot e monta o payload outbound. Retorna (reply, payload, store)."""
    if button_id is not None:
        msg = {
            "type": "interactive",
            "interactive": {
                "button_reply": {"id": button_id, "title": button_title or ""}
            },
        }
        content = extract_interactive_inbound(msg)
        rotulo = f"[toca botao: {button_title or button_id}]"
    else:
        content = text
        rotulo = text
    print(f"  \U0001f9d1  Cliente: {rotulo}")

    # Gate do bot (espelha webhook.py:721-728)
    contact = _db.get_wa_contact(cid)
    if not (contact and not contact.get("assigned_to")
            and not contact.get("bot_completed")):
        print("  \U0001f916  Bot: (nao responde — contato atribuido/concluido)")
        return None, None, None

    reply = bot.process_bot_message(cid, content)
    if not reply:
        print("  \U0001f916  Bot: (sem resposta — fluxo finalizado)")
        return None, None, None

    payload, store = build_outbound_payload(reply, "5531999998888")
    if payload["type"] == "interactive":
        botoes = " ".join(
            f"[ {b['reply']['title']} ]"
            for b in payload["interactive"]["action"]["buttons"]
        )
        print(f"  \U0001f916  Bot: {store}")
        print(f"        Botoes: {botoes}")
    else:
        print(f"  \U0001f916  Bot: {store}")
    return reply, payload, store


def titulo(txt):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


# =========================================================================
# Cenarios
# =========================================================================

def cenario_fluxo_feliz_botoes():
    titulo("CENARIO 1 — Fluxo feliz com BOTOES (LGPD -> fila do Comercial direto)")
    cid = 1
    _novo_contato(cid)
    STORE.setdefault("wa_conversations", {})["conv1"] = {
        "id": "conv1", "contact_id": cid,
        "assigned_to": None, "assigned_to_uid": "", "department_id": None,
    }

    reply, payload, store = cliente_envia(cid, text="oi")
    check(isinstance(reply, dict) and reply.get("type") == "interactive_buttons",
          "1o contato retorna dict de botoes")
    check(payload["type"] == "interactive"
          and payload["interactive"]["type"] == "button",
          "payload outbound e interactive/button")
    check(bool(payload["interactive"]["body"]["text"]),
          "body.text presente e nao-vazio")
    check(len(payload["interactive"]["body"]["text"]) <= 1024,
          "body.text dentro do limite de 1024 chars")
    ids = [b["reply"]["id"] for b in payload["interactive"]["action"]["buttons"]]
    check(ids == ["lgpd_aceitar", "lgpd_recusar"], "botoes lgpd_aceitar/lgpd_recusar")
    titles = [b["reply"]["title"] for b in payload["interactive"]["action"]["buttons"]]
    check(titles == ["Sim", "Não"], "botoes rotulados Sim / Não")
    check(isinstance(store, str), "content persistido e STRING (nunca o dict cru)")

    reply, _, _ = cliente_envia(cid, button_id="lgpd_aceitar", button_title="Sim")
    contato = STORE["wa_contacts"]["1"]
    check(contato.get("lgpd_consent") is True, "consentimento gravado no contato")
    check(bool(contato.get("lgpd_consent_at")), "carimbo lgpd_consent_at gravado")
    check(bool(contato.get("lgpd_policy_version")), "versao da politica gravada")
    check(any(a["action"] == "LGPD_CONSENT_ACCEPTED" for a in AUDIT),
          "audit_log registrou LGPD_CONSENT_ACCEPTED")
    check(isinstance(reply, str) and "comercial" in reply.lower(),
          "apos aceite, confirma o encaminhamento pra fila do Comercial")
    check(contato.get("bot_completed") is True,
          "aceite ja finaliza o bot (bot_completed=True, sem menu)")
    check(contato.get("department_id") == 1,
          "encaminhado ao Comercial (department_id=1)")
    check(STORE["wa_conversations"]["conv1"].get("department_id") == 1,
          "thread tambem recebeu department_id=1 (pool Novos Leads/Comercial)")
    # Marco do ciclo de espera da pool (fix 2026-08-09) — no builtin tambem,
    # pra o Modo Recepcao funcionar em qualquer tenant, nao so nos de CX.
    check(STORE["wa_conversations"]["conv1"].get("handoff_at") is not None,
          "thread recebeu handoff_at (marco do ciclo da pool)")
    check("1" not in STORE.get("bot_states", {}), "bot_state limpo apos finalizar")
    check(any("Bot finalizado" in str(m.get("content", "")) for m in MESSAGES),
          "system message 'Bot finalizado' registrada")

    reply, _, _ = cliente_envia(cid, text="obrigado")
    check(reply is None, "apos finalizar, bot nao responde mais (gate bot_completed)")


def cenario_recusa_reconsentimento():
    titulo("CENARIO 2 — Recusa via botao e RE-CONSENTIMENTO depois")
    cid = 2
    _novo_contato(cid)

    cliente_envia(cid, text="bom dia")
    reply, _, _ = cliente_envia(cid, button_id="lgpd_recusar", button_title="Não")
    check(STORE["bot_states"]["2"].get("lgpd_consent") is False,
          "recusa registrada no estado (lgpd_consent=False)")
    check(isinstance(reply, str) and "não podemos prosseguir" in reply.lower(),
          "mensagem de recusa enviada")
    check(isinstance(reply, str) and "Hub Loc agradece o seu contato" in reply,
          "despedida assina com o NOME do tenant (tenant.name, data-driven)")

    # Cliente muda de ideia e toca em Sim
    reply, _, _ = cliente_envia(cid, button_id="lgpd_aceitar", button_title="Sim")
    contato = STORE["wa_contacts"]["2"]
    check(contato.get("lgpd_consent") is True,
          "re-consentimento grava consentimento no contato")
    check(contato.get("bot_completed") is True and contato.get("department_id") == 1,
          "re-consentimento tambem encaminha direto pro Comercial")
    check(isinstance(reply, str) and "comercial" in reply.lower(),
          "resposta confirma a fila do Comercial")


def cenario_fallback_texto():
    titulo("CENARIO 3 — Fallback TEXTUAL (cliente digita 'sim', sem usar botao)")
    cid = 3
    _novo_contato(cid)

    reply, payload, _ = cliente_envia(cid, text="oi")
    check("podemos continuar" in payload["interactive"]["body"]["text"].lower(),
          "aviso LGPD apresentado no primeiro contato")
    reply, _, _ = cliente_envia(cid, text="sim")
    contato = STORE["wa_contacts"]["3"]
    check(contato.get("lgpd_consent") is True,
          "aceite por TEXTO ('sim') tambem funciona")
    check(contato.get("bot_completed") is True and contato.get("department_id") == 1,
          "aceite textual tambem encaminha direto pro Comercial")
    check(isinstance(reply, str) and "comercial" in reply.lower(),
          "apos aceite textual, confirma a fila do Comercial")


def _contato_legado_ask_sector(cid, conv_id):
    """Contato em voo no deploy: ja aceitou a LGPD e recebeu o menu antigo
    (bot_states com step=ask_sector), mas ainda nao respondeu."""
    _novo_contato(cid)
    STORE.setdefault("wa_conversations", {})[conv_id] = {
        "id": conv_id, "contact_id": cid,
        "assigned_to": None, "assigned_to_uid": "", "department_id": None,
    }
    STORE.setdefault("bot_states", {})[str(cid)] = {
        "step": "ask_sector", "lgpd_consent": True, "lgpd_status": "accepted",
    }


def cenario_legado_escolha_setor():
    titulo("CENARIO 4 — LEGADO: estado ask_sector em voo honra a escolha digitada")
    cid = 4
    _contato_legado_ask_sector(cid, "conv4")

    # Palavra-chave de troca/defeito -> Assistencia Tecnica (setor 2 / bot_key sac)
    reply, _, _ = cliente_envia(
        cid, text="preciso trocar um equipamento com defeito"
    )
    contato = STORE["wa_contacts"]["4"]
    check(reply is None, "escolha reconhecida finaliza o bot sem nova resposta")
    check(contato.get("bot_setor") == 2, "classificado como setor 2 (Assistencia)")
    check(contato.get("department_id") == 2,
          "contato encaminhado ao Suporte (department_id=2, bot_key=sac)")
    check(STORE["wa_conversations"]["conv4"].get("department_id") == 2,
          "thread tambem recebeu department_id=2 (pool segmenta por setor)")
    check("4" not in STORE.get("bot_states", {}), "bot_state legado drenado")


def cenario_legado_invalida_vai_comercial():
    titulo("CENARIO 5 — LEGADO: entrada nao reconhecida cai no Comercial (sem re-prompt)")
    cid = 6
    _contato_legado_ask_sector(cid, "conv6")

    reply, _, _ = cliente_envia(cid, text="asdf ????")
    contato = STORE["wa_contacts"]["6"]
    check(isinstance(reply, str) and "comercial" in reply.lower(),
          "entrada invalida responde com a fila do Comercial (menu nao existe mais)")
    check(contato.get("bot_completed") is True, "bot finalizado (bot_completed=True)")
    check(contato.get("department_id") == 1,
          "encaminhado ao Comercial (department_id=1)")
    check(STORE["wa_conversations"]["conv6"].get("department_id") == 1,
          "thread recebeu department_id=1")
    check("6" not in STORE.get("bot_states", {}), "bot_state legado drenado")


def cenario_limites_payload():
    titulo("CENARIO 6 — bot_transport: limites da Graph API (defensivo)")
    grande = {
        "type": "interactive_buttons",
        "body": "x" * 2000,
        "buttons": [
            {"id": "a", "title": "Titulo de botao muito longo demais"},
            {"id": "b", "title": "Beta"},
            {"id": "c", "title": "Gama"},
            {"id": "d", "title": "Delta (4o botao)"},
        ],
    }
    payload, store = build_outbound_payload(grande, "5531000000000")
    btns = payload["interactive"]["action"]["buttons"]
    check(len(payload["interactive"]["body"]["text"]) == 1024, "body truncado a 1024")
    check(len(btns) == 3, "limitado a 3 botoes")
    check(all(len(b["reply"]["title"]) <= 20 for b in btns), "titles truncados a <=20")
    check(isinstance(store, str), "store_content e string")

    # extract_interactive_inbound
    check(extract_interactive_inbound(
        {"interactive": {"button_reply": {"id": "lgpd_aceitar", "title": "Aceitar"}}}
    ) == "lgpd_aceitar", "extrai button_reply.id")
    check(extract_interactive_inbound(
        {"interactive": {"list_reply": {"id": "opt_1", "title": "Opcao 1"}}}
    ) == "opt_1", "extrai list_reply.id")
    check(extract_interactive_inbound({"type": "text"}) == "",
          "msg sem interactive -> string vazia")


def cenario_horario_comercial():
    """business_hours (frente b): datas FIXAS pra nao depender da hora em que
    o simulador roda. 2026-08-10 = segunda."""
    print("\n=== CENARIO: horario comercial (business_hours, hubloc 8h-17h) ===")
    from datetime import datetime, timedelta, timezone
    import business_hours as bh

    BR = timezone(timedelta(hours=-3))
    seg_10h = datetime(2026, 8, 10, 10, 0, tzinfo=BR)
    seg_0730 = datetime(2026, 8, 10, 7, 30, tzinfo=BR)
    sex_1730 = datetime(2026, 8, 14, 17, 30, tzinfo=BR)
    sab_10h = datetime(2026, 8, 15, 10, 0, tzinfo=BR)

    check(bh.is_open("hubloc", seg_10h) is True, "segunda 10h -> aberto")
    check(bh.is_open("hubloc", seg_0730) is False,
          "segunda 07:30 -> FECHADO (7h hardcoded antigo dizia aberto)")
    check(bh.retorno_previsto_text("hubloc", seg_0730) == "hoje às 8h",
          "07:30 de segunda -> retorno 'hoje às 8h'")
    check(bh.retorno_previsto_text("hubloc", sex_1730) == "segunda-feira às 8h",
          "sexta 17:30 -> retorno 'segunda-feira às 8h'")
    check(bh.retorno_previsto_text("hubloc", sab_10h) == "segunda-feira às 8h",
          "sabado -> retorno 'segunda-feira às 8h'")

    aviso = bh.builtin_expediente_notice("hubloc", sab_10h)
    check("segunda a sexta das 8h às 17h" in aviso,
          "aviso builtin resume a tabela real (8h, nao 7h)")
    check("retornaremos segunda-feira às 8h" in aviso,
          "aviso builtin interpola o retorno")
    check(bh.builtin_expediente_notice("hubloc", seg_10h) == "",
          "aberto -> sem aviso")

    # Fail-safe: tenant sem tabela NUNCA e declarado fechado.
    check(bh.is_open("tenant-inexistente", sab_10h) is None,
          "sem tabela -> is_open None (nem aberto nem fechado)")
    check(bh.cx_hours_params("tenant-inexistente", sab_10h)
          == {"fora_do_expediente": False, "retorno_previsto": ""},
          "sem tabela -> params neutros (nunca afirma fechado)")


def main():
    cenario_fluxo_feliz_botoes()
    cenario_recusa_reconsentimento()
    cenario_fallback_texto()
    cenario_legado_escolha_setor()
    cenario_legado_invalida_vai_comercial()
    cenario_limites_payload()
    cenario_horario_comercial()

    print("\n" + "=" * 70)
    if FAILS:
        print(f"RESULTADO: {len(FAILS)} de {CHECKS} checagens FALHARAM:")
        for f in FAILS:
            print(f"  - {f}")
        print("=" * 70)
        return 1
    print(f"RESULTADO: TODAS as {CHECKS} checagens passaram. ✅")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
