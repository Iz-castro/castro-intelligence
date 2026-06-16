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


# =========================================================================
# Stubs de firestore_common e database (injetados antes dos imports reais)
# =========================================================================

_fc = types.ModuleType("firestore_common")
_fc.document = lambda name, doc_id: _DocRef(name, doc_id)
_fc.utcnow = lambda: datetime.now(timezone.utc)
_fc.get_firestore_client = lambda: None
sys.modules["firestore_common"] = _fc

_DEPARTMENTS = [
    {"id": 1, "name": "Comercial", "bot_key": "comercial"},
    {"id": 2, "name": "Financeiro", "bot_key": "financeiro"},
    {"id": 3, "name": "Administrativo", "bot_key": "administrativo"},
    {"id": 4, "name": "SAC", "bot_key": "sac"},
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
    titulo("CENARIO 1 — Fluxo feliz com BOTOES (LGPD -> nome -> equip -> setor)")
    cid = 1
    _novo_contato(cid)

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
    check(isinstance(store, str), "content persistido e STRING (nunca o dict cru)")

    reply, _, _ = cliente_envia(cid, button_id="lgpd_aceitar", button_title="Aceitar")
    contato = STORE["wa_contacts"]["1"]
    check(contato.get("lgpd_consent") is True, "consentimento gravado no contato")
    check(bool(contato.get("lgpd_consent_at")), "carimbo lgpd_consent_at gravado")
    check(bool(contato.get("lgpd_policy_version")), "versao da politica gravada")
    check(any(a["action"] == "LGPD_CONSENT_ACCEPTED" for a in AUDIT),
          "audit_log registrou LGPD_CONSENT_ACCEPTED")
    check(isinstance(reply, str) and "nome" in reply.lower(), "apos aceite, pede o nome")

    reply, _, _ = cliente_envia(cid, text="João Silva")
    check(STORE["wa_contacts"]["1"].get("display_name") == "João Silva",
          "nome formatado e gravado (João Silva)")
    check("equipamento" in (reply or "").lower(), "apos nome, pergunta equipamento")

    reply, _, _ = cliente_envia(cid, text="betoneira")
    st = STORE["bot_states"]["1"]
    check(st.get("equipamento") == "betoneira", "equipamento betoneira detectado")
    check(st.get("step") == "ask_sector", "avancou para ask_sector")

    reply, _, _ = cliente_envia(cid, text="1")
    contato = STORE["wa_contacts"]["1"]
    check(reply is None, "setor escolhido finaliza o bot (sem nova resposta)")
    check(contato.get("bot_completed") is True, "bot_completed=True")
    check(contato.get("department_id") == 1, "encaminhado ao Comercial (department_id=1)")
    check("1" not in STORE.get("bot_states", {}), "bot_state limpo apos finalizar")


def cenario_recusa_reconsentimento():
    titulo("CENARIO 2 — Recusa via botao e RE-CONSENTIMENTO depois")
    cid = 2
    _novo_contato(cid)

    cliente_envia(cid, text="bom dia")
    reply, _, _ = cliente_envia(cid, button_id="lgpd_recusar", button_title="Recusar")
    check(STORE["bot_states"]["2"].get("lgpd_consent") is False,
          "recusa registrada no estado (lgpd_consent=False)")
    check(isinstance(reply, str) and "não podemos prosseguir" in reply.lower(),
          "mensagem de recusa enviada")

    # Cliente muda de ideia e toca em Aceitar
    reply, _, _ = cliente_envia(cid, button_id="lgpd_aceitar", button_title="Aceitar")
    check(STORE["wa_contacts"]["2"].get("lgpd_consent") is True,
          "re-consentimento grava consentimento no contato")


def cenario_fallback_texto():
    titulo("CENARIO 3 — Fallback TEXTUAL (cliente digita 'sim', sem usar botao)")
    cid = 3
    _novo_contato(cid)

    reply, payload, _ = cliente_envia(cid, text="oi")
    check("responda sim" in payload["interactive"]["body"]["text"].lower(),
          "aviso inclui instrucao textual de fallback (SIM/NAO)")
    reply, _, _ = cliente_envia(cid, text="sim")
    check(STORE["wa_contacts"]["3"].get("lgpd_consent") is True,
          "aceite por TEXTO ('sim') tambem funciona")


def cenario_lixo_equipamento():
    titulo("CENARIO 4 — ask_equipment rejeita LIXO (pontuacao, risada)")
    cid = 4
    _novo_contato(cid)
    cliente_envia(cid, text="oi")
    cliente_envia(cid, button_id="lgpd_aceitar", button_title="Aceitar")
    cliente_envia(cid, text="Maria")  # nome -> agora em ask_equipment

    for ruido in ("????", "kkkk", "!!!"):
        reply, _, _ = cliente_envia(cid, text=ruido)
        st = STORE["bot_states"]["4"]
        check("não consegui identificar" in (reply or "").lower()
              and st.get("step") == "ask_equipment"
              and not st.get("equipamento"),
              f"ruido {ruido!r} rejeitado (nao vira equipamento)")

    reply, _, _ = cliente_envia(cid, text="andaime")
    check(STORE["bot_states"]["4"].get("equipamento") == "andaime",
          "equipamento valido 'andaime' aceito")


def cenario_limites_payload():
    titulo("CENARIO 5 — bot_transport: limites da Graph API (defensivo)")
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


def main():
    cenario_fluxo_feliz_botoes()
    cenario_recusa_reconsentimento()
    cenario_fallback_texto()
    cenario_lixo_equipamento()
    cenario_limites_payload()

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
