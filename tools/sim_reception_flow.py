# -*- coding: utf-8 -*-

"""
Simulador LOCAL do Modo Recepcao (pool compartilhada, ADR 0010).

NAO toca em producao: exercita o codigo REAL de main.py (gate de envio,
assume), rbac.py (dual-check + fallback de role) e database_firestore.py
(pool_mode, revert_lead_to_sale_owner, close_stale_attendances) com o
Firestore substituido por stubs em memoria via monkeypatch de modulo —
mesmo espirito do sim_bot_flow.py. O leitor de perfis RBAC e stubado
explicitamente para nunca usar ADC local por engano.

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_reception_flow.py

Sai com codigo 0 se todos os asserts passarem, 1 caso contrario.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import HTTPException  # noqa: E402

import main  # noqa: E402  (real: gate de envio + endpoint de assume)
import rbac  # noqa: E402
import database  # noqa: E402  (reexporta database_firestore)
import database_firestore as dbf  # noqa: E402

# Guarda originais pra restaurar entre cenarios.
_REAL_IS_RECEPTION = dbf.is_reception_mode
_REAL_GET_DOC = dbf._get_doc
_REAL_DOCUMENT = dbf.document
_REAL_COLLECTION = dbf.collection
_REAL_NEXT_SEQUENCE = dbf.next_sequence

# RBAC nunca le Firestore neste sim: doc de perfil ausente -> fallback da
# role (dual-check real). Cenarios especificos injetam um doc fake.
_PERFIL_DOC = {"value": None}
rbac._read_perfil_doc = lambda tenant_id, perfil_id: _PERFIL_DOC["value"]

OPERADOR = {"id": 7, "role": "operador", "tenant_id": "hubloc",
            "display_name": "Maria", "firebase_uid": "uid7"}
SUPERVISOR = {"id": 8, "role": "supervisor", "tenant_id": "hubloc",
              "display_name": "Chefe", "firebase_uid": "uid8"}

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


def expect_http(fn, status, label):
    try:
        fn()
    except HTTPException as exc:
        check(exc.status_code == status, f"{label} (HTTP {exc.status_code})")
        return exc
    check(False, f"{label} — nao levantou HTTPException")
    return None


def set_reception(value):
    """Patcha o binding usado por cada modulo (main resolve via database)."""
    database.is_reception_mode = lambda: value
    dbf.is_reception_mode = lambda: value


def reset_rbac():
    _PERFIL_DOC["value"] = None
    rbac.invalidate_perfil_cache()


def titulo(txt):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


# =========================================================================
# Store em memoria (padrao do sim_bot_flow)
# =========================================================================

STORE = {}


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


_SEQ = {"n": 1000}


def patch_store():
    STORE.clear()
    dbf._get_doc = lambda coll, doc_id: (
        dict(STORE.get(coll, {}).get(str(doc_id)))
        if STORE.get(coll, {}).get(str(doc_id)) is not None else None
    )
    dbf.document = lambda coll, doc_id: _DocRef(coll, doc_id)
    dbf.collection = lambda coll: _CollRef(coll)
    def _fake_next_sequence(*a, **k):
        _SEQ["n"] += 1
        return _SEQ["n"]
    dbf.next_sequence = _fake_next_sequence


def restore_dbf():
    dbf.is_reception_mode = _REAL_IS_RECEPTION
    database.is_reception_mode = _REAL_IS_RECEPTION
    dbf._get_doc = _REAL_GET_DOC
    dbf.document = _REAL_DOCUMENT
    dbf.collection = _REAL_COLLECTION
    dbf.next_sequence = _REAL_NEXT_SEQUENCE


# =========================================================================
# Cenario 1 — gate de envio (_check_conv_send_permission)
# =========================================================================

def cenario_gate_envio():
    titulo("CENARIO 1 — Gate de envio: legacy vs reception")
    reset_rbac()
    conv_orfa = {"id": "c1", "assigned_to": None, "source_channel_type": "standard"}
    # bot_completed=True e o estado normal da pool (aba Recepcao) — e evita
    # que o gate chame o mark_human_active REAL (que tentaria o Firestore).
    contato_pool = {"id": 1, "assigned_to": None, "bot_completed": True}

    set_reception(False)
    expect_http(lambda: main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_pool)),
                403, "legacy: orfa standard -> 403 (assuma antes)")

    set_reception(True)
    r = main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_pool))
    check(r is None, "reception: orfa standard -> envio liberado (sem atribuir)")

    conv_de_outro = {"id": "c2", "assigned_to": 99, "source_channel_type": "standard"}
    expect_http(lambda: main._check_conv_send_permission(dict(conv_de_outro), OPERADOR, dict(contato_pool)),
                403, "reception: thread de OUTRO operador segue 403")

    conv_coex = {"id": "c3", "assigned_to": None, "source_channel_type": "coexistence"}
    expect_http(lambda: main._check_conv_send_permission(dict(conv_coex), OPERADOR, dict(contato_pool)),
                403, "reception: orfa coexistence segue 403 (fora do escopo)")

    conv_sem_tipo = {"id": "c4", "assigned_to": None}
    expect_http(lambda: main._check_conv_send_permission(dict(conv_sem_tipo), OPERADOR, dict(contato_pool),
                                                         channel={"channel_type": "coexistence"}),
                403, "reception: doc legado sem tipo cai no channel coex -> 403")
    r = main._check_conv_send_permission(dict(conv_sem_tipo), OPERADOR, dict(contato_pool),
                                         channel={"channel_type": "standard"})
    check(r is None, "reception: doc legado sem tipo + channel standard -> liberado")

    set_reception(False)
    r = main._check_conv_send_permission(dict(conv_orfa), SUPERVISOR, dict(contato_pool))
    check(r is None, "sanidade: supervisor em orfa segue liberado em legacy")

    # --- Fixes da revisao adversarial (2026-08-04) ---
    set_reception(True)
    contato_de_outro = {"id": 1, "assigned_to": 99}
    expect_http(lambda: main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_de_outro)),
                403, "reception: orfa de LEAD com dono (outro operador) -> 403")

    conv_coex_denorm = {"id": "c5", "assigned_to": None, "channel_type": "coexistence"}
    expect_http(lambda: main._check_conv_send_permission(dict(conv_coex_denorm), OPERADOR, dict(contato_pool)),
                403, "reception: fallback channel_type denormalizado barra coex (channel=None)")

    import bot_service
    marked = []
    real_mark = bot_service.mark_human_active
    bot_service.mark_human_active = lambda cid: marked.append(cid)
    patch_store()
    set_reception(True)  # patch_store nao mexe no is_reception_mode patchado
    STORE["wa_contacts"] = {
        "42": {"id": 42, "assigned_to": None, "bot_completed": False},
        "43": {"id": 43, "assigned_to": None, "bot_completed": True},
    }
    try:
        contato_mid_bot = {"id": 42, "assigned_to": None, "bot_completed": False}
        r = main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_mid_bot))
        check(r is None and marked == [42],
              "reception: envio em contato mid-bot chama mark_human_active (bot nao atropela)")
        check(STORE["wa_contacts"]["42"].get("bot_completed") is True,
              "reception: envio na orfa mid-bot carimba bot_completed (opcao A — aparece na Recepcao)")
        marked.clear()
        contato_pos_bot = {"id": 43, "assigned_to": None, "bot_completed": True}
        r = main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_pos_bot))
        check(r is None and marked == [],
              "reception: contato com bot concluido NAO grava human_active (sem write extra)")
    finally:
        bot_service.mark_human_active = real_mark
        restore_dbf()
    set_reception(False)


# =========================================================================
# Cenario 2 — RBAC assumir_atendimento no POST /api/wa/assume
# =========================================================================

def cenario_assume_rbac():
    titulo("CENARIO 2 — RBAC assumir_atendimento no assume")
    reset_rbac()
    contato = {"id": 1, "assigned_to": None, "department_id": None}
    main_get_wa_contact = main.get_wa_contact
    main.get_wa_contact = lambda cid: dict(contato)
    try:
        # Perfil custom "so recepcao": toggle OFF -> 403 antes do 409.
        _PERFIL_DOC["value"] = {"toggles": {"assumir_atendimento": False,
                                            "enviar_mensagem_propria_thread": True}}
        rbac.invalidate_perfil_cache()
        expect_http(lambda: asyncio.run(main.wa_assume_contact(1, _FakeRequest({}), current_user=dict(OPERADOR))),
                    403, "toggle OFF -> assume bloqueado (403)")

        # Fallback da role (perfil sem doc): seed do operador tem o toggle ON,
        # entao o fluxo passa do RBAC e para no 409 (lead de outro operador).
        reset_rbac()
        contato_de_outro = {"id": 1, "assigned_to": 99, "department_id": None}
        main.get_wa_contact = lambda cid: dict(contato_de_outro)
        expect_http(lambda: asyncio.run(main.wa_assume_contact(1, _FakeRequest({}), current_user=dict(OPERADOR))),
                    409, "toggle ON (fallback role) -> passa RBAC e cai no 409")
    finally:
        main.get_wa_contact = main_get_wa_contact
        reset_rbac()


# =========================================================================
# Cenario 3 — revert_lead_to_sale_owner: no-op em reception
# =========================================================================

def cenario_revert_sale_owner():
    titulo("CENARIO 3 — revert_lead_to_sale_owner (fechamento)")
    patch_store()
    STORE["wa_contacts"] = {"1": {"id": 1, "sale_owner_user_id": 5, "assigned_to": None}}
    STORE["users"] = {"5": {"id": 5, "is_active": 1, "firebase_uid": "uid5"}}

    dbf.is_reception_mode = lambda: True
    r = dbf.revert_lead_to_sale_owner(1)
    check(r is None, "reception: revert NAO re-gruda e NAO mexe em posse (PO 2026-08-05)")
    check(STORE["wa_contacts"]["1"].get("assigned_to") is None,
          "reception: contato sem dono segue sem dono")
    # A devolucao em reception e via release_lead_to_bot (cenarios 5 e 11),
    # nunca pelo revert — fechamento automatico nao muda posse por aqui.
    STORE["wa_contacts"]["9"] = {"id": 9, "assigned_to": 3, "assigned_to_uid": "uid3",
                                 "sale_owner_user_id": 3}
    r = dbf.revert_lead_to_sale_owner(9)
    check(r is None and STORE["wa_contacts"]["9"].get("assigned_to") == 3,
          "reception: revert nao tira o dono atual (devolucao e do release)")

    dbf.is_reception_mode = lambda: False
    r = dbf.revert_lead_to_sale_owner(1)
    check(isinstance(r, dict) and r.get("assigned_to") == 5,
          "legacy: revert re-gruda na dona de origem (ADR 0008 intacto)")
    check(STORE["wa_contacts"]["1"].get("assigned_to") == 5,
          "legacy: contato reatribuido a sale_owner")

    STORE["wa_contacts"]["2"] = {"id": 2, "assigned_to": None}
    r = dbf.revert_lead_to_sale_owner(2)
    check(r is None, "legacy: sem sale_owner -> pool fica pool")
    restore_dbf()


# =========================================================================
# Cenario 4 — pool_mode em system_settings (coercao + leitura)
# =========================================================================

def cenario_pool_mode_settings():
    titulo("CENARIO 4 — pool_mode: default, coercao e is_reception_mode")
    patch_store()
    dbf.is_reception_mode = _REAL_IS_RECEPTION  # testa a funcao REAL

    s = dbf.get_system_settings()
    check(s.get("pool_mode") == "legacy", "default no READ = legacy (doc ausente)")
    check(dbf.is_reception_mode() is False, "is_reception_mode() False por default")

    dbf.save_system_settings({"pool_mode": "banana", "hax": 1})
    doc = STORE.get("system_settings", {}).get("chat", {})
    check(doc.get("pool_mode") == "legacy", "valor desconhecido coage pra legacy")
    check("hax" not in doc, "chave fora da allowlist e descartada")

    dbf.save_system_settings({"pool_mode": "reception"})
    check(dbf.get_system_settings().get("pool_mode") == "reception",
          "save reception persiste")
    check(dbf.is_reception_mode() is True, "is_reception_mode() True apos ligar")
    restore_dbf()


# =========================================================================
# Cenario 5 — close_stale_attendances fecha a pool em reception
# =========================================================================

def _conv(cid, contact_id, assigned_to, hours_old, **extra):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    base = {"id": cid, "contact_id": contact_id, "assigned_to": assigned_to,
            "attendance_status": "aberto", "last_message_at": ts}
    base.update(extra)
    return base


def _seed_close_stale():
    STORE.clear()
    STORE["wa_conversations"] = {
        "A": _conv("A", 10, 7, hours_old=48),                      # atribuida stale
        "B": _conv("B", 11, None, hours_old=48),                   # pool, bot ok
        "C": _conv("C", 12, None, hours_old=48),                   # ainda no bot
        "D": _conv("D", 13, None, hours_old=1),                    # pool fresca
        "E": _conv("E", 14, None, hours_old=48, is_backup=True),   # backup
    }
    STORE["wa_contacts"] = {
        "10": {"id": 10, "bot_completed": True},
        "11": {"id": 11, "bot_completed": True},
        "12": {"id": 12, "bot_completed": False},
        "13": {"id": 13, "bot_completed": True},
        "14": {"id": 14, "bot_completed": True},
    }


def cenario_close_stale():
    titulo("CENARIO 5 — close_stale_attendances: pool fecha so em reception")
    patch_store()

    dbf.is_reception_mode = lambda: False
    _seed_close_stale()
    closed = dbf.close_stale_attendances(24)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["A"], f"legacy: so a atribuida fecha (fechou {ids})")

    dbf.is_reception_mode = lambda: True
    _seed_close_stale()
    closed = dbf.close_stale_attendances(24)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["A", "B"], f"reception: pool com bot concluido fecha junto (fechou {ids})")
    check(STORE["wa_conversations"]["B"].get("attendance_status") == "fechado_inatividade",
          "reception: thread da pool carimbada fechado_inatividade")
    check(STORE["wa_conversations"]["B"].get("assigned_to") is None,
          "reception: fechamento nao inventa dono na orfa")
    check(STORE["wa_conversations"]["A"].get("assigned_to") is None,
          "reception: thread ATRIBUIDA fechada perde o dono (release)")
    check(STORE["wa_contacts"]["10"].get("bot_completed") is False
          and STORE["wa_contacts"]["11"].get("bot_completed") is False,
          "reception: fechados voltam pro AGENTE DE IA (bot_completed=False)")
    check(STORE["wa_contacts"]["12"].get("bot_completed") is False,
          "reception: mid-bot intacto (ja era False; conv nao fechou)")
    check(STORE["wa_conversations"]["C"].get("attendance_status") == "aberto",
          "reception: thread ainda no bot NAO fecha")
    check(STORE["wa_conversations"]["E"].get("attendance_status") == "aberto",
          "reception: backup NAO fecha")
    restore_dbf()


# =========================================================================
# Cenario 5b — handoff sem atendimento humano NAO volta pro bot (2026-08-09)
# =========================================================================

def _ts(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _seed_handoff_pendente():
    """Todas stale (48h sem mensagem) e todas na pool com bot concluido —
    o que muda entre elas e so o ciclo handoff_at x last_human_outbound_at."""
    STORE.clear()
    STORE["wa_conversations"] = {
        # Handoff sabado, ninguem respondeu: NAO pode fechar.
        "P1": _conv("P1", 40, None, hours_old=48, handoff_at=_ts(50)),
        # Handoff e resposta humana depois: ciclo atendido, fecha.
        "P2": _conv("P2", 41, None, hours_old=48,
                    handoff_at=_ts(50), last_human_outbound_at=_ts(49)),
        # Atendida no ciclo ANTIGO e devolvida; handoff NOVO ainda sem
        # resposta: o carimbo velho nao pode liberar o fechamento.
        "P3": _conv("P3", 42, None, hours_old=48,
                    handoff_at=_ts(50), last_human_outbound_at=_ts(200)),
        # Espera acima do teto (7 dias): lead morto volta pro bot.
        "P4": _conv("P4", 43, None, hours_old=48, handoff_at=_ts(24 * 9)),
        # Doc legado sem handoff_at: degrada pro comportamento anterior.
        "P5": _conv("P5", 44, None, hours_old=48),
        # Thread ATRIBUIDA: o guard e so da pool, dono continua fechando.
        "P6": _conv("P6", 45, 7, hours_old=48, handoff_at=_ts(50)),
    }
    STORE["wa_contacts"] = {
        str(cid): {"id": cid, "bot_completed": True} for cid in range(40, 46)
    }


def cenario_handoff_pendente():
    titulo("CENARIO 5b — handoff sem atendimento humano nao volta pro bot")
    patch_store()
    dbf.is_reception_mode = lambda: True
    _seed_handoff_pendente()

    closed = dbf.close_stale_attendances(24, 7)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["P2", "P4", "P5", "P6"], f"fecharam so os elegiveis (fechou {ids})")
    check(STORE["wa_conversations"]["P1"].get("attendance_status") == "aberto"
          and STORE["wa_contacts"]["40"].get("bot_completed") is True,
          "P1 handoff sem resposta: segue aberta na pool, bot_completed intacto")
    check(STORE["wa_contacts"]["41"].get("bot_completed") is False,
          "P2 ciclo atendido: fecha e devolve ao agente de IA")
    check(STORE["wa_conversations"]["P3"].get("attendance_status") == "aberto"
          and STORE["wa_contacts"]["42"].get("bot_completed") is True,
          "P3 carimbo humano ANTERIOR ao handoff novo nao libera fechamento")
    check(STORE["wa_contacts"]["43"].get("bot_completed") is False,
          "P4 teto de 7 dias: espera longa demais volta pro bot")
    check(STORE["wa_contacts"]["44"].get("bot_completed") is False,
          "P5 doc legado sem handoff_at: comportamento anterior preservado")
    check(STORE["wa_contacts"]["45"].get("bot_completed") is False,
          "P6 thread com dono fecha normal (guard e so da pool)")

    # Teto configuravel: com 30 dias, nem o P4 (9 dias) e liberado.
    _seed_handoff_pendente()
    closed = dbf.close_stale_attendances(24, 30)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["P2", "P5", "P6"], f"teto de 30d segura o P4 tambem (fechou {ids})")
    restore_dbf()


# =========================================================================
# Cenario 5c — carimbo de resposta humana (save_wa_message -> conversation)
# =========================================================================

def cenario_carimbo_humano():
    titulo("CENARIO 5c — last_human_outbound_at: so operador carimba")
    patch_store()
    STORE["wa_contacts"] = {"50": {"id": 50, "wa_id": "5531988887777",
                                   "assigned_to": None, "source_channel_type": "standard"}}
    STORE["wa_conversations"] = {}
    contato = dict(STORE["wa_contacts"]["50"])

    def _msg(direction, **kw):
        dbf.save_wa_message(
            wa_message_id="", contact_id=50, direction=direction, msg_type="text",
            content="x", status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            channel_id=6, conversation_id="6__5531988887777", contact=contato, **kw,
        )
        return STORE["wa_conversations"].get("6__5531988887777", {})

    conv = _msg("outbound")  # bot: sem sender_user_id
    check(conv.get("last_human_outbound_at") is None,
          "mensagem do BOT nao carimba (sender_user_id None)")
    conv = _msg("inbound")
    check(conv.get("last_human_outbound_at") is None, "inbound nao carimba")
    conv = _msg("system", sender_user_id=7)
    check(conv.get("last_human_outbound_at") is None,
          "system message do operador nao carimba (cliente nao ve)")
    conv = _msg("outbound", sender_user_id=7)
    check(conv.get("last_human_outbound_at") is not None,
          "outbound de OPERADOR carimba last_human_outbound_at")
    restore_dbf()


# =========================================================================
# Cenario 11 — release_lead_to_bot (fechamento devolve ao agente de IA)
# =========================================================================

def cenario_release_to_bot():
    titulo("CENARIO 11 — release_lead_to_bot: fechamento devolve ao agente (PO 2026-08-05)")
    patch_store()
    STORE["wa_contacts"] = {
        "20": {"id": 20, "assigned_to": 3, "assigned_to_uid": "uid3",
               "bot_completed": True, "department_id": 5, "qualification": "novo",
               "attendance_protocol": "20260805-20-REC", "sale_owner_user_id": 3,
               "lead_temperature": "morno"},
        "21": {"id": 21, "assigned_to": 3, "lgpd_revoked": True},
    }
    STORE["wa_conversations"] = {
        "T1": {"id": "T1", "contact_id": 20, "assigned_to": 3, "assigned_to_uid": "uid3"},
        "T2": {"id": "T2", "contact_id": 20, "assigned_to": None,
               "assigned_to_uid": "__backup__", "is_backup": True},
    }
    STORE["bot_states"] = {"20": {"lgpd_status": "accepted", "cx_snapshot": {"x": 1},
                                  "human_active": True, "cx_fail_count": 2}}

    fields = dbf.release_lead_to_bot(20, "T1", "fechado_manual")
    c = STORE["wa_contacts"]["20"]
    bs = STORE["bot_states"]["20"]
    check(fields == {"assigned_to": None, "assigned_to_uid": "",
                     "takeover_status": "none", "takeover_started_at": None},
          "release retorna campos pro caller carimbar a conversa fechada")
    check(c.get("bot_completed") is False and c.get("assigned_to") is None,
          "contato: bot volta a atender (bot_completed=False, sem dono)")
    check(c.get("department_id") == 5 and c.get("qualification") == "novo"
          and c.get("attendance_protocol") == "20260805-20-REC"
          and c.get("sale_owner_user_id") == 3 and c.get("lead_temperature") == "morno",
          "contato: setor/qualificacao/protocolo/sale_owner/temperatura preservados")
    check(STORE["wa_conversations"]["T1"].get("assigned_to") is None,
          "thread nao-backup perde o dono")
    check(STORE["wa_conversations"]["T2"].get("assigned_to_uid") == "__backup__",
          "thread backup intacta")
    check(bs.get("human_active") is False and bs.get("cx_snapshot") is None
          and bs.get("cx_fail_count") == 0 and bs.get("lgpd_status") == "accepted",
          "bot_states: ciclo CX zerado, prova LGPD preservada")
    check(dbf.release_lead_to_bot(21, None, "fechado_manual") is None,
          "guard J-3: lgpd_revoked NAO volta pro funil (release=None)")
    restore_dbf()


# =========================================================================
# Cenario 12 — return_contact_to_pool (acao explicita do menu)
# =========================================================================

def cenario_return_to_pool():
    titulo("CENARIO 12 — Devolver a recepcao (acao explicita do menu)")
    patch_store()
    STORE["wa_contacts"] = {"30": {"id": 30, "assigned_to": 3, "assigned_to_uid": "uid3",
                                   "bot_completed": True, "department_id": 5,
                                   "qualification": "novo"}}
    STORE["wa_conversations"] = {
        "P1": {"id": "P1", "contact_id": 30, "assigned_to": 3, "assigned_to_uid": "uid3"},
        "P2": {"id": "P2", "contact_id": 30, "assigned_to": None,
               "assigned_to_uid": "__backup__", "is_backup": True},
    }
    r = dbf.return_contact_to_pool(30, 3)
    c = STORE["wa_contacts"]["30"]
    check(r is True and c.get("assigned_to") is None and c.get("assigned_to_uid") == "",
          "lead devolvido a pool (sem dono)")
    check(c.get("bot_completed") is True and c.get("department_id") == 5,
          "bot_completed/setor preservados (NAO volta pro bot)")
    check(STORE["wa_conversations"]["P1"].get("assigned_to") is None,
          "thread nao-backup devolvida")
    check(STORE["wa_conversations"]["P2"].get("assigned_to_uid") == "__backup__",
          "thread backup intacta")
    check(len(STORE.get("wa_transfer_log", {})) == 1,
          "transfer_log registra a devolucao")
    restore_dbf()


# =========================================================================
# Cenario 6 — fechamento manual de orfa (gate do set-attendance)
# =========================================================================

def cenario_fechar_orfa():
    titulo("CENARIO 6 — _reception_send_allowed cobre o fechar manual de orfa")
    conv_orfa = {"id": "c9", "assigned_to": None, "source_channel_type": "standard"}
    set_reception(True)
    check(main._reception_send_allowed(dict(conv_orfa), None) is True,
          "reception: orfa standard -> operador comum pode fechar/reabrir")
    set_reception(False)
    check(main._reception_send_allowed(dict(conv_orfa), None) is False,
          "legacy: orfa segue restrita a dono/manager")
    restore_dbf()


class _FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return dict(self._body)


def cenario_transfer_rbac():
    titulo("CENARIO 7 — Transfer-para-si exige assumir_atendimento (fix revisao)")
    reset_rbac()
    _PERFIL_DOC["value"] = {"toggles": {"transferir_atendimento": True,
                                        "assumir_atendimento": False}}
    rbac.invalidate_perfil_cache()
    req = _FakeRequest({"conversation_id": "1__5531999998888", "to_user_id": 7, "summary": "s"})
    expect_http(lambda: asyncio.run(main.wa_transfer(req, current_user=dict(OPERADOR))),
                403, "toggle OFF: transfer PRA SI -> 403 (assuncao disfarcada)")

    # Transfer pra OUTRO nao exige o toggle: com sentinela no resolve,
    # o request passa do gate RBAC e para no 404 do sentinela.
    real_resolve = main._resolve_send_target
    real_validate = main._validate_transfer_department

    def _sentinel(*a, **k):
        raise HTTPException(status_code=404, detail="sentinela")
    main._resolve_send_target = _sentinel
    main._validate_transfer_department = lambda d: None
    try:
        req2 = _FakeRequest({"conversation_id": "1__5531999998888", "to_user_id": 99, "summary": "s"})
        expect_http(lambda: asyncio.run(main.wa_transfer(req2, current_user=dict(OPERADOR))),
                    404, "toggle OFF: transfer pra OUTRO passa o gate (para no sentinela)")
    finally:
        main._resolve_send_target = real_resolve
        main._validate_transfer_department = real_validate
        reset_rbac()


def cenario_perfis_merge():
    titulo("CENARIO 8 — list_perfis completa chave nova com default do seed (fix revisao)")
    import firestore_common
    real_coll = firestore_common.collection
    STORE.clear()
    STORE["perfis_acesso"] = {
        # docs pre-feature: SEM a chave assumir_atendimento
        "perfil_operador": {"id": "perfil_operador", "role_equivalente": "operador",
                            "toggles": {"enviar_mensagem_propria_thread": True}},
        "perfil_admin": {"id": "perfil_admin", "role_equivalente": "admin",
                         "is_system_locked": True,
                         "toggles": {"ver_todos_leads": True}},
        # opt-out explicito gravado pelo admin: tem que ser respeitado
        "perfil_recepcao": {"id": "perfil_recepcao", "role_equivalente": "operador",
                            "toggles": {"assumir_atendimento": False}},
    }
    firestore_common.collection = lambda name: _CollRef(name)
    try:
        rows = {r["id"]: r for r in rbac.list_perfis("hubloc")}
        check(rows["perfil_operador"]["toggles"].get("assumir_atendimento") is True,
              "doc antigo sem a chave -> editor ve ON (default do seed da role)")
        check(rows["perfil_admin"]["toggles"].get("assumir_atendimento") is True,
              "perfil_admin travado volta a ser salvavel (todas as chaves True)")
        check(rows["perfil_recepcao"]["toggles"].get("assumir_atendimento") is False,
              "False explicito gravado pelo admin e respeitado")
        check(all(k in rows["perfil_operador"]["toggles"] for k in rbac.PERMISSION_KEYS),
              "todas as chaves do catalogo presentes no payload da UI")
    finally:
        firestore_common.collection = real_coll
        STORE.clear()


def cenario_set_attendance_orfa():
    titulo("CENARIO 9 — set-attendance: orfa de lead com dono nao fecha (fix revisao)")
    reset_rbac()
    set_reception(True)
    conv_orfa = {"id": "c9", "contact_id": 1, "assigned_to": None,
                 "source_channel_type": "standard"}
    real_get_conv = main.get_wa_conversation_by_id
    real_get_ctc = main.get_wa_contact
    main.get_wa_conversation_by_id = lambda cid: dict(conv_orfa)
    main.get_wa_contact = lambda cid: {"id": 1, "assigned_to": 99}
    try:
        req = _FakeRequest({"status": "fechado_manual"})
        expect_http(lambda: asyncio.run(main.wa_set_attendance("c9", req, current_user=dict(OPERADOR))),
                    403, "reception: fechar orfa de LEAD com dono -> 403")
    finally:
        main.get_wa_conversation_by_id = real_get_conv
        main.get_wa_contact = real_get_ctc
        restore_dbf()


def cenario_contato_manual():
    titulo("CENARIO 10 — picker/contato manual nao assume sem permissao (fix canario)")
    patch_store()
    real_find = dbf._find_contact_by_wa_id_any_variant
    STORE["wa_contacts"] = {"7": {"id": 7, "wa_id": "5531999990000", "assigned_to": None,
                                  "assigned_to_uid": "", "is_archived": 1,
                                  "qualification": "novo"}}
    STORE["users"] = {"2": {"id": 2, "firebase_uid": "uid2", "department_id": 5}}
    dbf._find_contact_by_wa_id_any_variant = lambda w: dict(STORE["wa_contacts"]["7"])
    try:
        cid, err = dbf.create_manual_wa_contact("Nome", "5531999990000", 6, 2, auto_assume=False)
        doc = STORE["wa_contacts"]["7"]
        check(cid == 7 and err is None, "auto_assume=False: reabre o contato existente")
        check(doc.get("assigned_to") is None and doc.get("assigned_to_uid") == "",
              "auto_assume=False: NAO vira dono (lead segue na pool)")
        check(doc.get("is_archived") == 0, "auto_assume=False: desarquiva mesmo assim")
        check(doc.get("qualification") == "novo", "auto_assume=False: qualification intacta")

        cid, err = dbf.create_manual_wa_contact("Nome", "5531999990000", 6, 2, auto_assume=True)
        doc = STORE["wa_contacts"]["7"]
        check(doc.get("assigned_to") == 2 and doc.get("qualification") == "em_atendimento",
              "auto_assume=True (legacy): reabre/assume como antes")
    finally:
        dbf._find_contact_by_wa_id_any_variant = real_find
        restore_dbf()


def cenario_protocolo_dia_anterior():
    titulo("CENARIO 13 — protocolo de dia anterior FECHA no fechamento (fix 3a)")
    patch_store()
    # Protocolo de ONTEM preso em "aberto": o autoclose de 20h quase sempre
    # cruza a meia-noite BR, e o early-return antigo (pid nao e de hoje ->
    # return False) pulava TAMBEM o carimbo de fechamento — attendances_daily
    # ficava aberto pra sempre, sem fechado_em.
    STORE["attendances_daily"] = {
        "20260805-77-REC": {"id": "20260805-77-REC", "contact_id": 77,
                            "status": "aberto", "protocolo_informado": False,
                            "fechado_em": None},
    }
    contato = {"id": 77, "wa_id": "5531977770001",
               "attendance_protocol": "20260805-77-REC",
               "last_inbound_at": "2026-08-05T12:00:00+00:00"}
    conv = {"id": "9__5531977770001", "contact_id": 77}
    ok = asyncio.run(main._close_daily_and_send_protocol(
        contato, conv, None, None, "fechado_inatividade"))
    doc = STORE["attendances_daily"]["20260805-77-REC"]
    check(ok is True, "nao desiste mais por protocolo de dia anterior")
    check(doc.get("status") == "fechado_inatividade", "registro carimbado fechado")
    check(doc.get("fechado_em") is not None, "fechado_em preenchido")
    check(doc.get("protocolo_informado") is False,
          "recibo NAO enviado (gate de mesmo-dia do ENVIO preservado)")
    check(not STORE.get("wa_messages"), "nenhuma mensagem gravada pro lead")

    # Regressao: protocolo de HOJE (ja informado) continua fechando normal.
    pid_hoje = f"{dbf._today_br_str()}-78-REC"
    STORE["attendances_daily"][pid_hoje] = {
        "id": pid_hoje, "contact_id": 78, "status": "aberto",
        "protocolo_informado": True, "fechado_em": None,
    }
    contato2 = {"id": 78, "wa_id": "5531977770002",
                "attendance_protocol": pid_hoje}
    ok2 = asyncio.run(main._close_daily_and_send_protocol(
        contato2, {"id": "9__5531977770002", "contact_id": 78}, None, None,
        "fechado_manual"))
    check(ok2 is True
          and STORE["attendances_daily"][pid_hoje].get("status") == "fechado_manual",
          "protocolo de hoje segue fechando (regressao)")
    restore_dbf()


def cenario_assume_carimba_threads_orfas():
    titulo("CENARIO 14 — assume carimba dono nas threads ORFAS do contato (fix 2026-08-19)")
    patch_store()
    # Lead multi-canal: thread da pool (standard, orfa — a que A e B estao
    # olhando), thread coex JA de outro operador (nao pode ser roubada) e uma
    # thread de backup (nunca graduada por aqui). Antes do fix, o assume so
    # carimbava a thread derivada de contact.channel_id (efeito colateral da
    # system message) -> a thread da pool podia continuar orfa e visivel a todos.
    STORE["users"] = {"5": {"id": 5, "is_active": 1, "firebase_uid": "uidA", "department_id": 2}}
    STORE["wa_contacts"] = {"40": {"id": 40, "wa_id": "5531940000000", "channel_id": 2, "assigned_to": 5}}
    STORE["wa_conversations"] = {
        "4__5531940000000": {"id": "4__5531940000000", "contact_id": 40, "assigned_to": None, "assigned_to_uid": ""},
        "1__5531940000000": {"id": "1__5531940000000", "contact_id": 40, "assigned_to": 9, "assigned_to_uid": "uidB"},
        "2__5531940000000": {"id": "2__5531940000000", "contact_id": 40, "assigned_to": None, "assigned_to_uid": "",
                             "is_backup": True},
        "4__5531999999999": {"id": "4__5531999999999", "contact_id": 41, "assigned_to": None, "assigned_to_uid": ""},
    }
    n = dbf.assign_orphan_threads_to_lead_owner(40, 5)
    check(n == 1, "carimbou exatamente 1 thread (a orfa nao-backup do contato)")
    pool = STORE["wa_conversations"]["4__5531940000000"]
    check(pool.get("assigned_to") == 5 and pool.get("assigned_to_uid") == "uidA",
          "thread da pool herdou dono + uid do operador")
    check(pool.get("department_id") == 2, "setor do operador herdado (thread sem setor)")
    coex = STORE["wa_conversations"]["1__5531940000000"]
    check(coex.get("assigned_to") == 9 and coex.get("assigned_to_uid") == "uidB",
          "thread coex de OUTRO operador intacta (nao rouba)")
    check(STORE["wa_conversations"]["2__5531940000000"].get("assigned_to") is None, "thread backup intacta")
    check(STORE["wa_conversations"]["4__5531999999999"].get("assigned_to") is None,
          "thread de outro contato intacta")
    # Idempotente + usuario inexistente = no-op
    check(dbf.assign_orphan_threads_to_lead_owner(40, 5) == 0, "segunda chamada: nada a carimbar")
    check(dbf.assign_orphan_threads_to_lead_owner(40, 777) == 0, "usuario inexistente: no-op")
    restore_dbf()


def cenario_open_picker_nao_rouba_pool():
    titulo("CENARIO 15 — /conversation/open (picker) nao atribui thread de lead da POOL (fix 2026-08-19)")
    patch_store()
    calls = []
    real_upsert = database.upsert_wa_conversation
    real_get_contact = main.get_wa_contact
    real_get_conv = main.get_wa_conversation_by_id
    real_audit = main.log_audit
    database.upsert_wa_conversation = lambda **kw: calls.append(kw) or "4__5531950000000"
    main.get_wa_conversation_by_id = lambda cid: {"id": cid, "contact_id": 50, "assigned_to": None, "assigned_to_uid": ""}
    main.log_audit = lambda *a, **k: None
    try:
        # Lead da POOL (sem dono), legacy: abrir NAO carimba a thread.
        set_reception(False)
        main.get_wa_contact = lambda cid: {"id": 50, "wa_id": "5531950000000", "channel_id": 4,
                                           "assigned_to": None, "assigned_to_uid": ""}
        res = asyncio.run(main.wa_conversation_open(_FakeRequest({"contact_id": 50}), current_user=dict(OPERADOR)))
        check(calls and calls[-1].get("auto_assign_user_id") is None,
              "legacy + lead da pool: open NAO auto-atribui a thread (fica orfa ate o Assumir)")
        check(res.get("assigned_to") is None, "resposta devolve dono real (nenhum)")
        # Lead MEU, legacy: abrir carimba a thread em mim (thread do proprio lead).
        main.get_wa_contact = lambda cid: {"id": 50, "wa_id": "5531950000000", "channel_id": 4,
                                           "assigned_to": 7, "assigned_to_uid": "uid7"}
        asyncio.run(main.wa_conversation_open(_FakeRequest({"contact_id": 50}), current_user=dict(OPERADOR)))
        check(calls[-1].get("auto_assign_user_id") == 7, "legacy + lead MEU: open auto-atribui a thread a mim")
        # Lead de OUTRO: _require_contact_access barra (403) antes do upsert.
        main.get_wa_contact = lambda cid: {"id": 50, "wa_id": "5531950000000", "channel_id": 4,
                                           "assigned_to": 99, "assigned_to_uid": "uid99"}
        n_before = len(calls)
        expect_http(lambda: asyncio.run(main.wa_conversation_open(_FakeRequest({"contact_id": 50}), current_user=dict(OPERADOR))),
                    403, "lead de outro operador: 403")
        check(len(calls) == n_before, "nenhum upsert no 403")
        # Reception: mesmo lead MEU nao auto-atribui (ADR 0010 preservado).
        set_reception(True)
        main.get_wa_contact = lambda cid: {"id": 50, "wa_id": "5531950000000", "channel_id": 4,
                                           "assigned_to": 7, "assigned_to_uid": "uid7"}
        asyncio.run(main.wa_conversation_open(_FakeRequest({"contact_id": 50}), current_user=dict(OPERADOR)))
        check(calls[-1].get("auto_assign_user_id") is None, "reception: open nunca auto-atribui (ADR 0010)")
    finally:
        database.upsert_wa_conversation = real_upsert
        main.get_wa_contact = real_get_contact
        main.get_wa_conversation_by_id = real_get_conv
        main.log_audit = real_audit
        restore_dbf()



# =========================================================================
# Cenario — ADR 0011: wa_contacts.unread_count derivado das threads
# =========================================================================

def cenario_unread_sync():
    titulo("CENARIO — ADR 0011: recompute_wa_contact_unread (contato = soma das threads)")
    patch_store()
    STORE["wa_contacts"] = {"50": {"id": 50, "unread_count": 7}, "51": {"id": 51, "unread_count": 3}}
    STORE["wa_conversations"] = {
        "1__a": {"id": "1__a", "contact_id": 50, "unread_count": 3},
        "2__a": {"id": "2__a", "contact_id": 50, "unread_count": 0},
        "1__b": {"id": "1__b", "contact_id": 51, "unread_count": 0},
        "1__c": {"id": "1__c", "contact_id": 52, "unread_count": 2},  # contato inexistente
    }
    total = dbf.recompute_wa_contact_unread(50)
    check(total == 3 and STORE["wa_contacts"]["50"]["unread_count"] == 3,
          "2 threads (3 + 0) -> contato grava 3 (era 7)")
    total = dbf.recompute_wa_contact_unread(51)
    check(total == 0 and STORE["wa_contacts"]["51"]["unread_count"] == 0,
          "todas as threads em 0 -> contato zera (o drift do incidente 2026-08-21)")
    total = dbf.recompute_wa_contact_unread(52)
    check(total == 2 and "52" not in STORE["wa_contacts"],
          "conversa de contato inexistente -> soma sem criar contato fantasma")
    STORE["wa_contacts"]["50"] = {"id": 50, "unread_count": 3, "marker": "x"}
    dbf.recompute_wa_contact_unread(50, current=3)
    check(STORE["wa_contacts"]["50"] == {"id": 50, "unread_count": 3, "marker": "x"},
          "valor igual -> nenhuma escrita (idempotente)")
    restore_dbf()

def run():
    print("Simulador do Modo Recepcao (ADR 0010) — codigo real, Firestore mockado")
    cenario_gate_envio()
    cenario_assume_rbac()
    cenario_revert_sale_owner()
    cenario_pool_mode_settings()
    cenario_close_stale()
    cenario_handoff_pendente()
    cenario_carimbo_humano()
    cenario_fechar_orfa()
    cenario_transfer_rbac()
    cenario_perfis_merge()
    cenario_set_attendance_orfa()
    cenario_contato_manual()
    cenario_release_to_bot()
    cenario_return_to_pool()
    cenario_protocolo_dia_anterior()
    cenario_assume_carimba_threads_orfas()
    cenario_open_picker_nao_rouba_pool()
    cenario_unread_sync()

    print("\n" + "=" * 70)
    if FAILS:
        print(f"RESULTADO: {len(FAILS)} de {CHECKS} asserts FALHARAM:")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print(f"RESULTADO: todos os {CHECKS} asserts passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
