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


def patch_store():
    STORE.clear()
    dbf._get_doc = lambda coll, doc_id: (
        dict(STORE.get(coll, {}).get(str(doc_id)))
        if STORE.get(coll, {}).get(str(doc_id)) is not None else None
    )
    dbf.document = lambda coll, doc_id: _DocRef(coll, doc_id)
    dbf.collection = lambda coll: _CollRef(coll)


def restore_dbf():
    dbf.is_reception_mode = _REAL_IS_RECEPTION
    database.is_reception_mode = _REAL_IS_RECEPTION
    dbf._get_doc = _REAL_GET_DOC
    dbf.document = _REAL_DOCUMENT
    dbf.collection = _REAL_COLLECTION


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
    try:
        contato_mid_bot = {"id": 42, "assigned_to": None, "bot_completed": False}
        r = main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_mid_bot))
        check(r is None and marked == [42],
              "reception: envio em contato mid-bot chama mark_human_active (bot nao atropela)")
        marked.clear()
        contato_pos_bot = {"id": 43, "assigned_to": None, "bot_completed": True}
        r = main._check_conv_send_permission(dict(conv_orfa), OPERADOR, dict(contato_pos_bot))
        check(r is None and marked == [],
              "reception: contato com bot concluido NAO grava human_active (sem write extra)")
    finally:
        bot_service.mark_human_active = real_mark
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
        expect_http(lambda: asyncio.run(main.wa_assume_contact(1, current_user=dict(OPERADOR))),
                    403, "toggle OFF -> assume bloqueado (403)")

        # Fallback da role (perfil sem doc): seed do operador tem o toggle ON,
        # entao o fluxo passa do RBAC e para no 409 (lead de outro operador).
        reset_rbac()
        contato_de_outro = {"id": 1, "assigned_to": 99, "department_id": None}
        main.get_wa_contact = lambda cid: dict(contato_de_outro)
        expect_http(lambda: asyncio.run(main.wa_assume_contact(1, current_user=dict(OPERADOR))),
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
    check(r is None, "reception: revert e no-op (lead fica na pool)")
    check(STORE["wa_contacts"]["1"].get("assigned_to") is None,
          "reception: contato segue sem dono apos fechamento")

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
          "reception: fechamento nao inventa dono (revert no-op)")
    check(STORE["wa_conversations"]["C"].get("attendance_status") == "aberto",
          "reception: thread ainda no bot NAO fecha")
    check(STORE["wa_conversations"]["E"].get("attendance_status") == "aberto",
          "reception: backup NAO fecha")
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


def run():
    print("Simulador do Modo Recepcao (ADR 0010) — codigo real, Firestore mockado")
    cenario_gate_envio()
    cenario_assume_rbac()
    cenario_revert_sale_owner()
    cenario_pool_mode_settings()
    cenario_close_stale()
    cenario_fechar_orfa()
    cenario_transfer_rbac()
    cenario_perfis_merge()
    cenario_set_attendance_orfa()
    cenario_contato_manual()

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
