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
import channel_service  # noqa: E402
import firestore_common  # noqa: E402
import tenant_service  # noqa: E402

# Guarda originais pra restaurar entre cenarios.
_REAL_IS_RECEPTION = dbf.is_reception_mode
_REAL_GET_DOC = dbf._get_doc
_REAL_DOCUMENT = dbf.document
_REAL_COLLECTION = dbf.collection
_REAL_NEXT_SEQUENCE = dbf.next_sequence
_REAL_GET_CHANNEL = channel_service.get_channel
_REAL_REFRESH_CHANNELS = channel_service.refresh_channels
_REAL_MAIN_FS_COLL = main.fs_coll
_REAL_MAIN_FS_DOCUMENT = main.fs_document
_REAL_COMMON_COLLECTION = firestore_common.collection
_REAL_COMMON_DOCUMENT = firestore_common.document

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
# Log de writes (coll, doc_id, campos) — prova "no MESMO write" nos cenarios
# da reabertura. Zerado pelo cenario que o le.
WRITES = []


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

    @property
    def id(self):
        return self.doc_id

    def get(self):
        return _Snap(STORE.get(self.coll, {}).get(self.doc_id))

    def set(self, data, merge=False):
        coll = STORE.setdefault(self.coll, {})
        cur = coll.get(self.doc_id) if merge else None
        resolved = {}
        for k, v in data.items():
            # Sentinela firestore.ArrayUnion (teto por contato da reabertura):
            # resolve como o servidor — acrescenta so o que ainda nao existe.
            if type(v).__name__ == "ArrayUnion":
                base = list((cur or {}).get(k) or [])
                for item in v.values:
                    if item not in base:
                        base.append(item)
                resolved[k] = base
            else:
                resolved[k] = v
        WRITES.append((self.coll, self.doc_id, dict(resolved)))
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(resolved)
        else:
            coll[self.doc_id] = dict(resolved)

    def create(self, data):
        # Claim atomico (wa_message_index / wa_contact_index): falha se existe.
        from google.api_core import exceptions as _gexc
        coll = STORE.setdefault(self.coll, {})
        if self.doc_id in coll:
            raise _gexc.AlreadyExists("ja existe")
        coll[self.doc_id] = dict(data)

    def delete(self):
        STORE.get(self.coll, {}).pop(self.doc_id, None)


class _QSnap:
    def __init__(self, coll, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = _DocRef(coll, doc_id)

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


def _sort_value(v):
    # Ordenacao do mock: datetime e ISO viram o mesmo eixo (instante UTC).
    if isinstance(v, datetime):
        return (0, (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).timestamp())
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return (0, (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp())
        except ValueError:
            return (1, v)
    if v is None:
        return (-1, 0)
    return (0, v)


def _match(data, field, op, value):
    got = data.get(field)
    if op == "==":
        return got == value
    if op == "in":
        return got in value
    if got is None:
        return False
    try:
        if op == ">=":
            return got >= value
        if op == ">":
            return got > value
        if op == "<=":
            return got <= value
        if op == "<":
            return got < value
    except TypeError:
        return False
    raise AssertionError(f"operador nao suportado no mock: {op}")


class _CollRef:
    def __init__(self, coll):
        self.coll = coll
        self._filters = []
        self._limit = None
        self._order = None

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def order_by(self, field, direction="ASCENDING"):
        # Reabertura (heuristica do P5): ultimas N mensagens da thread.
        self._order = (field, str(direction).upper().startswith("DESC"))
        return self

    def limit(self, n):
        # Necessario p/ _get_first_by_field (.where().limit(1)) — usado pelo
        # upsert_wa_contact e pelo dedup do save_wa_message.
        self._limit = n
        return self

    def document(self, doc_id=None):
        if doc_id is None:
            _SEQ["n"] += 1
            doc_id = _SEQ["n"]
        return _DocRef(self.coll, doc_id)

    def stream(self):
        rows = [(doc_id, data) for doc_id, data in list(STORE.get(self.coll, {}).items())
                if all(_match(data, f, op, v) for (f, op, v) in self._filters)]
        if self._order:
            field, desc = self._order
            rows.sort(key=lambda r: _sort_value(r[1].get(field)), reverse=desc)
        emitted = 0
        for doc_id, data in rows:
            yield _QSnap(self.coll, doc_id, data)
            emitted += 1
            if self._limit is not None and emitted >= self._limit:
                break


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
    # upsert_wa_conversation importa estes nomes dentro da funcao. Sem o stub,
    # um cache miss do simulador tenta descobrir ADC/gcloud e deixa de ser local.
    channel_service.get_channel = lambda channel_id: {
        "id": channel_id, "is_active": True, "channel_type": "standard",
        "display_phone_number": "", "label": "Teste",
    }
    channel_service.refresh_channels = lambda: None
    main.fs_coll = lambda coll: _CollRef(coll)
    main.fs_document = lambda coll, doc_id: _DocRef(coll, doc_id)
    firestore_common.collection = lambda coll: _CollRef(coll)
    firestore_common.document = lambda coll, doc_id: _DocRef(coll, doc_id)


def restore_dbf():
    dbf.is_reception_mode = _REAL_IS_RECEPTION
    database.is_reception_mode = _REAL_IS_RECEPTION
    dbf._get_doc = _REAL_GET_DOC
    dbf.document = _REAL_DOCUMENT
    dbf.collection = _REAL_COLLECTION
    dbf.next_sequence = _REAL_NEXT_SEQUENCE
    channel_service.get_channel = _REAL_GET_CHANNEL
    channel_service.refresh_channels = _REAL_REFRESH_CHANNELS
    main.fs_coll = _REAL_MAIN_FS_COLL
    main.fs_document = _REAL_MAIN_FS_DOCUMENT
    firestore_common.collection = _REAL_COMMON_COLLECTION
    firestore_common.document = _REAL_COMMON_DOCUMENT


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
# Cenario 5d — reforma de qualificacoes (2026-09): 1o outbound humano
# promove lead "novo" a "em_atendimento" com rastro na nota
# =========================================================================

def cenario_promocao_qualificacao():
    titulo("CENARIO 5d — 1o outbound humano promove novo -> em_atendimento")
    patch_store()
    STORE["wa_contacts"] = {"55": {"id": 55, "wa_id": "5531977776666",
                                   "assigned_to": None, "qualification": "novo",
                                   "notes": "", "source_channel_type": "standard"}}
    STORE["wa_conversations"] = {}

    def _msg(direction, **kw):
        # Snapshot fresco a cada chamada (o caller real re-le o contato).
        contato = dict(STORE["wa_contacts"]["55"])
        dbf.save_wa_message(
            wa_message_id="", contact_id=55, direction=direction, msg_type="text",
            content="x", status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            channel_id=6, conversation_id="6__5531977776666", contact=contato, **kw,
        )
        return STORE["wa_contacts"]["55"]

    ctc = _msg("outbound")  # bot: sem sender_user_id
    check(ctc.get("qualification") == "novo", "mensagem do BOT nao promove")
    ctc = _msg("inbound")
    check(ctc.get("qualification") == "novo", "inbound nao promove")
    ctc = _msg("outbound", sender_user_id=7, promote_qualification=False)
    check(ctc.get("qualification") == "novo",
          "recibo de sistema (promote_qualification=False) nao promove")
    ctc = _msg("outbound", sender_user_id=7)
    check(ctc.get("qualification") == "em_atendimento",
          "outbound de OPERADOR promove novo -> em_atendimento")
    check("Atendimento iniciado em" in str(ctc.get("notes") or ""),
          "promocao deixa rastro na nota com timestamp")
    check(ctc.get("first_human_contact_at") is not None,
          "promocao carimba first_human_contact_at")
    notas_antes = str(ctc.get("notes") or "")
    ctc = _msg("outbound", sender_user_id=7)
    check(str(ctc.get("notes") or "") == notas_antes
          and ctc.get("qualification") == "em_atendimento",
          "lead ja em_atendimento: 2o outbound nao re-promove nem duplica nota")
    restore_dbf()


# =========================================================================
# Cenario 5e — toggle auto_close_enabled=False (PO 2026-09-01): fechamento
# por inatividade desligado, mas a VALVULA de orfaos continua ativa
# =========================================================================

def cenario_auto_close_toggle():
    titulo("CENARIO 5e — auto_close OFF: so a valvula de orfaos fecha")
    patch_store()
    dbf.is_reception_mode = lambda: True
    _seed_handoff_pendente()
    # P7: thread ASSUMIDA cujo handoff nunca teve resposta humana e estourou
    # o teto — a valvula TAMBEM alcanca thread com dono (revisao 2026-09-01:
    # sem isto o lead assumido-e-abandonado ficava preso pra sempre).
    STORE["wa_conversations"]["P7"] = _conv("P7", 46, 7, hours_old=48, handoff_at=_ts(24 * 9))
    STORE["wa_contacts"]["46"] = {"id": 46, "bot_completed": True}

    closed = dbf.close_stale_attendances(24, 7, inactivity_enabled=False)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["P4", "P7"], f"toggle OFF: so os orfaos estourados (valvula) fecham (fechou {ids})")
    check(STORE["wa_conversations"]["P2"].get("attendance_status") == "aberto",
          "toggle OFF: pool JA atendida nao fecha por inatividade")
    check(STORE["wa_conversations"]["P5"].get("attendance_status") == "aberto",
          "toggle OFF: doc legado sem handoff_at nao fecha (conservador)")
    check(STORE["wa_conversations"]["P6"].get("attendance_status") == "aberto",
          "toggle OFF: thread com dono DENTRO do teto nao fecha")
    check(STORE["wa_contacts"]["46"].get("bot_completed") is False,
          "toggle OFF: assumido-e-nunca-respondido estourado volta pro agente de IA")
    check(STORE["wa_contacts"]["43"].get("bot_completed") is False,
          "toggle OFF: valvula devolve o orfao estourado ao agente de IA")
    check(STORE["wa_contacts"]["40"].get("bot_completed") is True,
          "toggle OFF: orfao dentro do teto segue esperando na pool")

    # Legacy com toggle OFF: nada fecha automaticamente.
    dbf.is_reception_mode = lambda: False
    _seed_close_stale()
    closed = dbf.close_stale_attendances(24, 7, inactivity_enabled=False)
    check(closed == [], "legacy + toggle OFF: nenhum fechamento automatico")

    # Default do parametro preserva o comportamento historico (ligado).
    dbf.is_reception_mode = lambda: True
    _seed_close_stale()
    closed = dbf.close_stale_attendances(24)
    ids = sorted(c["conversation_id"] for c in closed)
    check(ids == ["A", "B"], f"default (ligado): comportamento historico intacto (fechou {ids})")
    restore_dbf()


# =========================================================================
# Cenario 11 — release_lead_to_bot (fechamento devolve ao agente de IA)
# =========================================================================

def cenario_release_to_bot():
    titulo("CENARIO 11 — release_lead_to_bot: fechamento devolve ao agente (PO 2026-08-05)")
    patch_store()
    _antes = datetime.now(timezone.utc)
    STORE["wa_contacts"] = {
        "20": {"id": 20, "assigned_to": 3, "assigned_to_uid": "uid3",
               "bot_completed": True, "department_id": 5, "qualification": "novo",
               "attendance_protocol": "20260805-20-REC", "sale_owner_user_id": 3,
               "lead_temperature": "morno",
               "bot_outcome": "agendado", "bot_outcome_at": _antes - timedelta(days=3)},
        "21": {"id": 21, "assigned_to": 3, "lgpd_revoked": True},
        "22": {"id": 22, "assigned_to": 3, "bot_completed": True,
               "bot_outcome": "link_enviado", "bot_outcome_at": _antes - timedelta(days=1)},
    }
    WRITES.clear()
    STORE["wa_conversations"] = {
        "T1": {"id": "T1", "contact_id": 20, "assigned_to": 3, "assigned_to_uid": "uid3"},
        "T2": {"id": "T2", "contact_id": 20, "assigned_to": None,
               "assigned_to_uid": "__backup__", "is_backup": True},
    }
    STORE["bot_states"] = {"20": {"lgpd_status": "accepted", "cx_snapshot": {"x": 1},
                                  "human_active": True, "cx_fail_count": 2}}
    STORE["bot_buffers"] = {
        "20": {"items": [{"text": "ciclo velho"}], "token": "a"},
        "22": {"items": [{"text": "ciclo velho"}], "token": "b"},
    }

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
    check("20" not in STORE.get("bot_buffers", {}),
          "release_lead_to_bot limpa o buffer do ciclo fechado")
    # Plano de reabertura (etapa 2): marco de ciclo + desfecho zerado.
    _rel = c.get("bot_released_at")
    check(isinstance(_rel, datetime) and _rel.tzinfo is not None and _rel >= _antes,
          "release grava bot_released_at datetime UTC (marco de ciclo, mesmo tipo de handoff_at)")
    check(c.get("bot_outcome") is None and c.get("bot_outcome_at") is None
          and "bot_outcome" in c and "bot_outcome_at" in c,
          "release zera bot_outcome e bot_outcome_at")
    _w20 = [w for w in WRITES if w[0] == "wa_contacts" and w[1] == "20"]
    check(len(_w20) == 1 and _w20[0][2].get("bot_completed") is False
          and "bot_released_at" in _w20[0][2] and "bot_outcome" in _w20[0][2],
          "release: marco e desfecho vao no MESMO write do commit-point (1 write no contato)")
    _hand = dbf._coerce_timestamp(_ts(1))
    try:
        _cmp_ok = isinstance(_rel > _hand, bool)
    except TypeError:
        _cmp_ok = False
    check(_cmp_ok, "bot_released_at compara com handoff_at coagido (_coerce_timestamp) sem TypeError")
    check(dbf.release_lead_to_bot(21, None, "fechado_manual") is None
          and "bot_released_at" not in STORE["wa_contacts"]["21"],
          "guard J-3: lgpd_revoked NAO volta pro funil (release=None, sem marco)")
    WRITES.clear()
    check(dbf.return_contact_to_bot(22, 7) is True
          and "22" not in STORE.get("bot_buffers", {}),
          "return_contact_to_bot tambem limpa o buffer anterior")
    c22 = STORE["wa_contacts"]["22"]
    _w22 = [w for w in WRITES if w[0] == "wa_contacts" and w[1] == "22"]
    check(isinstance(c22.get("bot_released_at"), datetime)
          and c22.get("bot_outcome") is None and c22.get("bot_outcome_at") is None
          and len(_w22) == 1 and "bot_released_at" in _w22[0][2],
          "return_contact_to_bot: marco datetime + desfecho zerado no mesmo write do contato")
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


def cenario_gate_desfecho():
    titulo("CENARIO 16 — gate de desfecho no encerramento manual (reforma 2026-09)")
    reset_rbac()
    set_reception(False)
    patch_store()
    STORE["wa_conversations"] = {"c16": {"id": "c16", "contact_id": 1, "assigned_to": 7,
                                         "attendance_status": "aberto",
                                         "source_channel_type": "standard"}}
    STORE["wa_contacts"] = {"1": {"id": 1, "wa_id": "5531966665555", "assigned_to": 7,
                                  "qualification": "em_atendimento", "notes": ""}}
    real_get_conv = main.get_wa_conversation_by_id
    real_get_ctc = main.get_wa_contact
    real_sysmsg = main.insert_transfer_system_message
    main.get_wa_conversation_by_id = lambda cid: dict(STORE["wa_conversations"]["c16"])
    main.get_wa_contact = lambda cid: dict(STORE["wa_contacts"]["1"])
    # Banner de sistema nao e o alvo aqui (o mock nao cobre o dedup por
    # wa_message_id que ele dispara) — stub no-op, padrao do sim.
    main.insert_transfer_system_message = lambda *a, **k: None
    try:
        req = _FakeRequest({"status": "fechado_manual"})
        expect_http(lambda: asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR))),
                    400, "fechar em_atendimento SEM desfecho -> 400")
        check(STORE["wa_conversations"]["c16"].get("attendance_status") == "aberto",
              "400 do gate nao fecha a thread")
        req = _FakeRequest({"status": "fechado_manual", "qualification": "banana"})
        expect_http(lambda: asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR))),
                    400, "desfecho fora do vocabulario -> 400")
        req = _FakeRequest({"status": "fechado_manual", "qualification": "novo"})
        expect_http(lambda: asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR))),
                    400, "estado de passagem (novo) nao e desfecho -> 400")
        req = _FakeRequest({"status": "fechado_manual", "qualification": "nao_convertido",
                            "notes": "negociou e nao fechou"})
        asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR)))
        check(STORE["wa_conversations"]["c16"].get("attendance_status") == "fechado_manual",
              "com desfecho valido: fecha")
        check(STORE["wa_contacts"]["1"].get("qualification") == "nao_convertido",
              "desfecho gravado no contato no MESMO request")
        check(STORE["wa_contacts"]["1"].get("notes") == "negociou e nao fechou",
              "notas do modal gravadas junto")
        # Lead ja com desfecho terminal fecha direto, sem exigir qualificacao.
        STORE["wa_conversations"]["c16"]["attendance_status"] = "aberto"
        req = _FakeRequest({"status": "fechado_manual"})
        asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR)))
        check(STORE["wa_conversations"]["c16"].get("attendance_status") == "fechado_manual",
              "lead ja qualificado (terminal) fecha sem gate")
        # Tags no encerramento (Frente B): gravadas NORMALIZADAS no contato.
        # ("qualificado" e nao "convertido": o carimbo converted_by usa o
        # fs_document REAL do main, fora do mock deste harness.)
        STORE["wa_conversations"]["c16"]["attendance_status"] = "aberto"
        req = _FakeRequest({"status": "fechado_manual", "qualification": "qualificado",
                            "notes": "fechou", "tags": ["Varizes", "Consulta Marcada"],
                            "tag_labels": {"consulta-marcada": "Consulta Marcada"}})
        asyncio.run(main.wa_set_attendance("c16", req, current_user=dict(OPERADOR)))
        check(STORE["wa_contacts"]["1"].get("tags") == ["varizes", "consulta-marcada"],
              "tags do modal gravadas normalizadas (slug) no contato")
        check(any(t.get("slug") == "consulta-marcada"
                  for t in (STORE.get("user_settings", {}).get("7", {}).get("tags") or [])),
              "tag inedita vira tag PESSOAL do operador (on-the-fly)")
    finally:
        main.get_wa_conversation_by_id = real_get_conv
        main.get_wa_contact = real_get_ctc
        main.insert_transfer_system_message = real_sysmsg
        restore_dbf()


def cenario_rating_botao():
    titulo("CENARIO 17 — recibo v2: captura de avaliacao SO por botao")
    import webhook as wh
    patch_store()
    # Matcher: rotulo puro so vale vindo de BOTAO de template; id rating_*
    # (interativa de sessao) vale sempre; texto comum nunca vira nota.
    check(wh._rating_choice_from_text("bom") is None,
          "texto 'bom' digitado NAO e nota (licao do digito engolido)")
    check(wh._rating_choice_from_text("Excelente", allow_bare_words=True) == (3, "Excelente"),
          "rotulo do botao de template mapeia (3, Excelente)")
    check(wh._rating_choice_from_text("rating_ruim") == (1, "Ruim"),
          "id interativo mapeia (1, Ruim)")
    check(wh._rating_choice_from_text("oi, tudo bem?", allow_bare_words=True) is None,
          "texto comum ignorado mesmo no caminho de botao")

    # Handler: bindings do webhook apontam pro firestore_common real —
    # patcha direto no modulo e restaura no finally.
    real_doc, real_get, real_audit = wh.document, wh.get_wa_contact, wh.log_audit
    wh.document = dbf.document
    wh.get_wa_contact = lambda cid: (
        dict(STORE["wa_contacts"][str(cid)])
        if STORE.get("wa_contacts", {}).get(str(cid)) is not None else None
    )
    wh.log_audit = lambda *a, **k: None
    def _pick(raw, bare=False):
        return wh._rating_choice_from_text(raw, allow_bare_words=bare)

    try:
        STORE["wa_contacts"] = {
            "70": {"id": 70, "rating_requested_at": _ts(1), "rating": None},
            "71": {"id": 71, "rating": None},
            "72": {"id": 72, "rating_requested_at": _ts(72), "rating": None},
            # Ciclo NOVO de fechamento: nota antiga respondida ha 200h, pedido
            # recarimbado ha 1h -> clique novo DEVE sobrescrever (fix da
            # revisao: re-pergunta cuja resposta era descartada pra sempre).
            "73": {"id": 73, "rating": 2, "rating_label": "Bom",
                   "rating_received_at": _ts(200), "rating_requested_at": _ts(1)},
        }
        STORE["wa_messages"] = {"900": {"id": 900}}
        asyncio.run(wh._handle_rating_reply(70, 900, _pick("rating_excelente")))
        check(STORE["wa_contacts"]["70"].get("rating") == 3
              and STORE["wa_contacts"]["70"].get("rating_label") == "Excelente",
              "clique valido (pedido de 1h atras) grava nota 3 + rotulo")
        check(STORE["wa_messages"]["900"].get("visibility") == "admin_only",
              "resposta de avaliacao vira admin_only (avaliado nao ve)")
        asyncio.run(wh._handle_rating_reply(70, 900, _pick("rating_ruim")))
        check(STORE["wa_contacts"]["70"].get("rating") == 3,
              "clique repetido (mesmo pedido) nao sobrescreve a nota")
        asyncio.run(wh._handle_rating_reply(71, None, _pick("rating_bom")))
        check(STORE["wa_contacts"]["71"].get("rating") is None,
              "sem pedido pendente: clique ignorado")
        asyncio.run(wh._handle_rating_reply(72, None, _pick("rating_bom")))
        check(STORE["wa_contacts"]["72"].get("rating") is None,
              "pedido de 72h atras: janela de captura (48h) expirou, ignora")
        asyncio.run(wh._handle_rating_reply(73, None, _pick("rating_ruim")))
        check(STORE["wa_contacts"]["73"].get("rating") == 1
              and STORE["wa_contacts"]["73"].get("rating_label") == "Ruim",
              "pedido NOVO (recarimbado apos resposta velha): clique sobrescreve")
    finally:
        wh.document, wh.get_wa_contact, wh.log_audit = real_doc, real_get, real_audit
        restore_dbf()


def cenario_tags_lead():
    titulo("CENARIO 19 — tags de lead (Frente B): normalizacao + limites")
    check(dbf.normalize_tag_slug("  Varizes  ") == "varizes", "slug: minusculo + trim")
    check(dbf.normalize_tag_slug("Hemorróidas") == "hemorroidas", "slug: sem acento")
    check(dbf.normalize_tag_slug("nao fechou") == "nao-fechou", "slug: espaco vira hifen")
    check(dbf.clean_lead_tags(["Varizes", "varizes", "VARIZES", ""]) == ["varizes"],
          "dedupe case/acento-insensitive; vazio descartado")
    try:
        dbf.clean_lead_tags([f"t{i}" for i in range(13)])
        check(False, "13 tags deveria levantar ValueError")
    except ValueError:
        check(True, "limite de 12 tags por lead (400 no endpoint)")
    try:
        dbf.clean_lead_tags("nao-lista")
        check(False, "nao-lista deveria levantar ValueError")
    except ValueError:
        check(True, "tags em formato nao-lista -> ValueError")
    try:
        dbf.clean_lead_tags([{"slug": "x"}])
        check(False, "item dict deveria levantar ValueError")
    except ValueError:
        check(True, "item nao-string vira 400 (nao slug-lixo silencioso)")
    defs = dbf._clean_tag_defs([{"label": "Varizes", "color": "#22c55e"}], "Tags globais")
    check(defs == [{"slug": "varizes", "label": "Varizes", "color": "#22c55e"}],
          "registry: slug derivado do rotulo + cor hex aceita")
    try:
        dbf._clean_tag_defs([{"label": "A", "color": "verde"}], "Tags globais")
        check(False, "cor invalida deveria levantar ValueError")
    except ValueError:
        check(True, "registry: cor invalida -> ValueError")
    try:
        dbf._clean_tag_defs([{"label": "Dor"}, {"label": "dor"}], "Tags globais")
        check(False, "slug repetido deveria levantar ValueError")
    except ValueError:
        check(True, "registry: slug repetido (case-insensitive) -> ValueError")


def cenario_reabertura_travas():
    titulo("CENARIO 20 — Frente C1: matcher do botao + opt-out de retomada")
    import webhook as wh
    # Matcher: continuar = retomar (template da varizemed); rotulos de
    # avaliacao NUNCA podem virar acao de reabertura.
    check(wh._reopen_action_from_choice("Encerrar atendimento") == "encerrar",
          "Encerrar -> encerrar")
    check(wh._reopen_action_from_choice("Retomar atendimento") == "retomar",
          "Retomar -> retomar")
    check(wh._reopen_action_from_choice("Continuar") == "retomar",
          "[Continuar] (varizemed) -> retomar")
    check(wh._reopen_action_from_choice("Excelente") is None,
          "rotulo de avaliacao nao vira acao de reabertura")
    check(wh._reopen_action_from_choice("Sim, quero") is None,
          "texto qualquer -> None (log de nao reconhecida)")

    # Opt-out (ADR 0009 D2): envio pontual bloqueia com 409 ANTES de montar
    # template/enviar qualquer coisa.
    real_resolve = main._resolve_send_target
    real_check = main._check_conv_send_permission
    main._resolve_send_target = lambda cid, ch: (
        {"id": cid, "contact_id": 1, "channel_id": 6},
        {"id": 1, "wa_id": "5531966665555", "reopen_opt_out": True},
        {"id": 6, "channel_type": "standard"},
    )
    main._check_conv_send_permission = lambda *a, **k: None
    try:
        expect_http(lambda: asyncio.run(main.wa_reopen_conversation("6__5531966665555", body=None, current_user=dict(SUPERVISOR))),
                    409, "contato com reopen_opt_out: reabertura pontual -> 409")
    finally:
        main._resolve_send_target = real_resolve
        main._check_conv_send_permission = real_check


def cenario_scan_reabertura():
    titulo("CENARIO 21 — Frente C2: scan classifica o publico do lote")
    patch_store()
    _now = datetime.now(timezone.utc)

    def _h(hrs):
        return (_now - timedelta(hours=hrs)).isoformat()

    STORE["wa_contacts"] = {
        "1": {"id": 1, "qualification": "em_atendimento", "last_inbound_at": _h(30), "department_id": 2},
        "2": {"id": 2, "qualification": "em_atendimento", "last_inbound_at": _h(2)},
        "3": {"id": 3, "qualification": "em_atendimento", "last_inbound_at": _h(30), "reopen_opt_out": True},
        "4": {"id": 4, "qualification": "em_atendimento", "last_inbound_at": _h(30), "last_reopen_template_at": _h(3)},
        "5": {"id": 5, "qualification": "em_atendimento", "last_inbound_at": _h(30), "reopen_attempts": 1},
        "6": {"id": 6, "qualification": "em_atendimento"},
        "7": {"id": 7, "qualification": "em_atendimento", "last_inbound_at": _h(30), "is_archived": 1},
        "8": {"id": 8, "qualification": "em_atendimento", "last_inbound_at": _h(30), "is_backup": True},
        "9": {"id": 9, "qualification": "em_atendimento", "last_inbound_at": _h(30), "lgpd_revoked": True},
        "10": {"id": 10, "qualification": "novo", "last_inbound_at": _h(30)},
    }
    r = dbf.scan_reopen_candidates(max_attempts=1, cooldown_hours=24, window_hours=24)
    check([c["id"] for c in r["enviaveis"]] == [1],
          "so o lead frio/limpo e ENVIAVEL (novo nem entra na query)")
    check([c["id"] for c in r["auto_resolve"]] == [5],
          "attempts >= max vira AUTO-RESOLVE (fecha sem enviar)")
    check(r["pulados"] == {"janela_aberta": 1, "opt_out": 1, "cooldown": 1,
                           "janela_desconhecida": 1, "arquivado": 1,
                           "backup": 1, "lgpd_revogado": 1},
          f"pulados classificados por motivo ({r['pulados']})")
    check(r["por_setor"] == {2: 1}, "por_setor (D3) conta so os enviaveis")
    restore_dbf()


def cenario_worker_lote():
    titulo("CENARIO 22 — Frente C2: worker do lote (envio, auto-resolve, freios)")
    # Exercita main._run_reopen_batch de ponta a ponta com Meta stubada —
    # cobre o caminho que a revisao adversarial pegou quebrado (fs_coll
    # NameError matava o auto-resolve em silencio) e os freios novos.
    import types as _types
    patch_store()
    _now = datetime.now(timezone.utc)
    STORE["wa_contacts"] = {
        "31": {"id": 31, "wa_id": "5531911112222", "channel_id": 6,
               "qualification": "em_atendimento",
               "last_inbound_at": (_now - timedelta(hours=30)).isoformat(),
               "source_channel_type": "standard", "unread_count": 0},
        "32": {"id": 32, "wa_id": "5531933334444", "channel_id": 6,
               "qualification": "em_atendimento",
               "last_inbound_at": (_now - timedelta(hours=40)).isoformat(),
               "reopen_attempts": 1, "unread_count": 0},
        "33": {"id": 33, "wa_id": "5531955556666", "channel_id": 6,
               "qualification": "em_atendimento",
               "last_inbound_at": (_now - timedelta(hours=30)).isoformat(),
               "source_channel_type": "standard", "unread_count": 0},
    }
    STORE["wa_conversations"] = {
        "6__5531933334444": {"id": "6__5531933334444", "contact_id": 32, "channel_id": 6,
                             "attendance_status": "aberto", "unread_count": 0,
                             "last_message_at": (_now - timedelta(hours=40)).isoformat()},
    }
    canal = {"id": 6, "channel_type": "standard", "is_active": True, "owner_user_id": None}
    tpl = {"name": "atualizao_de_solicitao", "language": "pt_BR", "category": "UTILITY",
           "components": [
               {"type": "BODY", "text": "Ola {{1}}, sua ultima conversa foi em {{2}}.",
                "example": {"body_text": [["Rafael", "01/01/2026"]]}},
               {"type": "BUTTONS", "buttons": [
                   {"type": "QUICK_REPLY", "text": "Retomar"},
                   {"type": "QUICK_REPLY", "text": "Encerrar"}]},
           ]}

    sent_payloads = []
    resp_body = {"messages": [{"id": "wamid.SIM1"}]}

    class _FakeResp:
        status_code = 200

        def json(self):
            return dict(resp_body)

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            sent_payloads.append(json)
            return _FakeResp()

    async def _fast_sleep(_s):
        return None

    closed_daily = []

    async def _fake_close_daily(*a, **k):
        closed_daily.append(a)
        return True

    real_fs_coll, real_fs_doc = main.fs_coll, main.fs_document
    real_httpx, real_asyncio = main.httpx, main.asyncio
    real_creds = main._resolve_channel_creds_by_id
    real_close_daily = main._close_daily_and_send_protocol
    main.fs_coll = lambda name: _CollRef(name)
    main.fs_document = dbf.document
    main.httpx = _types.SimpleNamespace(AsyncClient=_FakeAsyncClient)
    main.asyncio = _types.SimpleNamespace(sleep=_fast_sleep)
    main._resolve_channel_creds_by_id = lambda chid: ("tok", "pnid", "https://graph.example")
    main._close_daily_and_send_protocol = _fake_close_daily
    try:
        asyncio.run(main._run_reopen_batch(
            "", 9001,
            [dict(STORE["wa_contacts"]["31"])],
            [dict(STORE["wa_contacts"]["32"])],
            {6: canal}, {6: tpl}, 7,
        ))
        check(len(sent_payloads) == 1
              and sent_payloads[0]["template"]["name"] == "atualizao_de_solicitao"
              and len(sent_payloads[0]["template"]["components"][0]["parameters"]) == 2,
              "envio: 1 template com 2 params (nome+data) pro lead enviavel")
        c31 = STORE["wa_contacts"]["31"]
        check(int(c31.get("reopen_attempts") or 0) == 1 and c31.get("last_reopen_template_at"),
              "envio 200: attempts+cooldown carimbados no contato")
        # Plano de reabertura (etapa 2): campos por tentativa + teto por contato.
        check(c31.get("last_reopen_at") == c31.get("last_reopen_template_at")
              and isinstance(c31.get("last_reopen_at"), str),
              "lote: last_reopen_at (ISO) = mesmo instante do last_reopen_template_at")
        check(c31.get("last_reopen_audience") == "reception"
              and c31.get("last_reopen_conversation_id") == "6__5531911112222"
              and c31.get("last_reopen_channel_id") == 6,
              "lote: audiencia reception + thread {channel_id}__{wa_id} + canal do envio")
        check(c31.get("reopen_batch_sent_at") == [{"at": c31.get("last_reopen_at"),
                                                   "audience": "reception"}],
              "lote: reopen_batch_sent_at recebe {at, audience: reception} (ArrayUnion)")
        th31 = STORE["wa_conversations"].get("6__5531911112222") or {}
        check(not th31.get("last_human_outbound_at"),
              "template de lote NAO carimba last_human_outbound_at (valvula reception)")
        check(th31.get("id") == c31.get("last_reopen_conversation_id"),
              "thread carimbada no contato e a mesma que o save da mensagem usou")
        check("reopen_human_active_at" not in c31 and "bot_released_at" not in c31
              and c31.get("bot_completed") is None and c31.get("assigned_to") is None,
              "template do lote nao muda o balde (sem reopen_human_active_at, marco, dono ou bot_completed)")
        check(STORE["wa_conversations"]["6__5531933334444"].get("attendance_status") == "fechado_inatividade",
              "auto-resolve: thread aberta do lead ja-tentado fecha (fs_coll vivo)")
        c32 = STORE["wa_contacts"]["32"]
        check(bool(c32.get("reopen_resolved_at")) and len(closed_daily) == 1,
              "auto-resolve: reopen_resolved_at carimbado + carimbo diario chamado")
        b1 = STORE["reopen_batches"]["9001"]
        check(b1.get("status") == "concluido" and b1.get("enviados") == 1
              and b1.get("resolvidos") == 1 and b1.get("falhas") == 0,
              f"doc do lote: concluido 1/1/0 ({b1})")

        # held_for_quality_assessment vem DENTRO do 200 (freio de reputacao).
        resp_body["messages"] = [{"id": "wamid.SIM2",
                                  "message_status": "held_for_quality_assessment"}]
        asyncio.run(main._run_reopen_batch(
            "", 9002,
            [dict(STORE["wa_contacts"]["33"])], [],
            {6: canal}, {6: tpl}, 7,
        ))
        b2 = STORE["reopen_batches"]["9002"]
        check(b2.get("status") == "abortado"
              and b2.get("abort_motivo") == "held_for_quality_assessment"
              and b2.get("enviados") == 1,
              "held no corpo do 200: envio conta/carimba e o lote ABORTA")

        # Scan pos-lote: enviado recente cai em cooldown; auto-resolvido e
        # TERMINAL (ja_resolvido) — nao volta ao balde em todo lote.
        r = dbf.scan_reopen_candidates(max_attempts=1, cooldown_hours=24, window_hours=24)
        check(r["enviaveis"] == [] and r["auto_resolve"] == []
              and r["pulados"] == {"cooldown": 2, "ja_resolvido": 1},
              f"scan pos-lote: cooldown x2 + ja_resolvido ({r['pulados']})")
    finally:
        main.fs_coll, main.fs_document = real_fs_coll, real_fs_doc
        main.httpx, main.asyncio = real_httpx, real_asyncio
        main._resolve_channel_creds_by_id = real_creds
        main._close_daily_and_send_protocol = real_close_daily
        restore_dbf()


def cenario_reabertura_pontual_carimbo():
    titulo("CENARIO 22b — Reabertura pontual: campos por tentativa (audiencia manual, sem teto)")
    patch_store()
    _legado = [{"at": "2026-09-23T12:00:00+00:00", "audience": "bot"}]
    STORE["wa_contacts"] = {"34": {"id": 34, "wa_id": "5531977771111", "channel_id": 6,
                                   "reopen_attempts": 0, "reopen_batch_sent_at": list(_legado)}}
    # Kill-switch do LOTE desligado: a pontual nao pode ser afetada.
    STORE["system_settings"] = {"chat": {"reopen_batch_enabled": False}}
    enviados = []

    async def _fake_send(body=None, current_user=None):
        enviados.append(body)
        return {"status": "sent"}

    async def _fake_tpls(channel):
        return {"templates": []}

    real = (main._resolve_send_target, main._check_conv_send_permission,
            main.wa_send_template, main._load_approved_templates_for_channel, main.log_audit)
    main._resolve_send_target = lambda cid, ch: (
        {"id": cid, "contact_id": 34, "channel_id": 6},
        dict(STORE["wa_contacts"]["34"]),
        {"id": 6, "channel_type": "standard"},
    )
    main._check_conv_send_permission = lambda *a, **k: None
    main.wa_send_template = _fake_send
    main._load_approved_templates_for_channel = _fake_tpls
    main.log_audit = lambda *a, **k: None
    try:
        res = asyncio.run(main.wa_reopen_conversation("6__5531977771111", body=None,
                                                      current_user=dict(SUPERVISOR)))
        c34 = STORE["wa_contacts"]["34"]
        check(res.get("status") == "sent" and len(enviados) == 1,
              "pontual segue enviando com reopen_batch_enabled=False (kill-switch e so do lote)")
        check(c34.get("reopen_attempts") == 1
              and c34.get("last_reopen_at") == c34.get("last_reopen_template_at")
              and isinstance(c34.get("last_reopen_at"), str),
              "pontual: attempts+1, last_reopen_at = last_reopen_template_at (ISO)")
        check(c34.get("last_reopen_audience") == "manual"
              and c34.get("last_reopen_conversation_id") == "6__5531977771111"
              and c34.get("last_reopen_channel_id") == 6,
              "pontual: audiencia manual + conversa da rota + canal da thread")
        check(c34.get("reopen_batch_sent_at") == _legado,
              "pontual NAO acrescenta item em reopen_batch_sent_at (teto so p/ envio em massa)")
    finally:
        (main._resolve_send_target, main._check_conv_send_permission,
         main.wa_send_template, main._load_approved_templates_for_channel, main.log_audit) = real
        restore_dbf()


def cenario_reopen_human_active():
    titulo("CENARIO 22c — reopen_human_active_at: outbound HUMANO apos template de retomada")
    patch_store()
    _now = datetime.now(timezone.utc)
    STORE["wa_contacts"] = {
        "60": {"id": 60, "wa_id": "5531960000001", "qualification": "em_atendimento",
               "last_reopen_template_at": (_now - timedelta(hours=2)).isoformat(),
               "reopen_attempts": 1, "source_channel_type": "standard"},
        "61": {"id": 61, "wa_id": "5531960000002", "qualification": "em_atendimento",
               "source_channel_type": "standard"},
    }

    def _msg(cid, ts=None, **kw):
        contato = dict(STORE["wa_contacts"][str(cid)])
        dbf.save_wa_message(
            wa_message_id="", contact_id=cid, direction="outbound", msg_type="text",
            content="x", status="sent", timestamp_wa=(ts or _now).isoformat(),
            channel_id=6, conversation_id=f"6__{contato['wa_id']}", contact=contato, **kw,
        )
        return STORE["wa_contacts"][str(cid)]

    c = _msg(60, ts=_now - timedelta(minutes=100))  # bot: sem sender_user_id
    check("reopen_human_active_at" not in c, "resposta do BOT apos o template nao grava")
    c = _msg(60, ts=_now - timedelta(minutes=90), sender_user_id=7, human_outbound=False)
    check("reopen_human_active_at" not in c,
          "outbound com human_outbound=False (template de lote) nao grava")
    WRITES.clear()
    _t_h = _now - timedelta(hours=1)
    c = _msg(60, ts=_t_h, sender_user_id=7)
    check(c.get("reopen_human_active_at") == _t_h,
          "outbound HUMANO apos o template grava reopen_human_active_at = data real da mensagem")
    _w60 = [w for w in WRITES if w[0] == "wa_contacts" and w[1] == "60"]
    check(len(_w60) == 1 and "reopen_human_active_at" in _w60[0][2]
          and "last_message_at" in _w60[0][2],
          "carimbo vai no MESMO write do contato que o save ja fazia (sem write novo)")
    check(c.get("reopen_attempts") == 1, "outbound humano NAO zera reopen_attempts")
    c = _msg(60, ts=_now - timedelta(hours=5), sender_user_id=7)
    check(c.get("reopen_human_active_at") == _t_h, "replay mais antigo nao recua o carimbo")
    c61 = _msg(61, sender_user_id=7)
    check("reopen_human_active_at" not in c61,
          "contato sem template de retomada: outbound humano NAO grava")
    restore_dbf()


def cenario_kill_switch_lote():
    titulo("CENARIO 22d — reopen_batch_enabled=False: previa e disparo do lote -> 409")
    from fastapi import BackgroundTasks
    patch_store()
    reset_rbac()
    main._reopen_preview_cache.clear()
    varreduras = []

    def _view_vazia():
        return {"enviaveis": [], "auto_resolve": [], "pulados": {}, "por_setor": {}}

    async def _fake_plan(sys_settings=None):
        varreduras.append(1)
        return {"scan": {"criteria_version": "v2.2", "total": 0, "excedente": 0,
                         "audiences": {"reception": _view_vazia(), "bot": _view_vazia()}},
                "canais": {}, "tpls": {},
                "availability": {"cx_ok": False, "disponivel": False, "motivo": "x"}}

    real_plan = main._plan_reopen_batch
    real_list_tenants = tenant_service.list_tenants
    main._plan_reopen_batch = _fake_plan
    # Teto diario do disparo: sem tenants ativos no sim (nada de Firestore real).
    tenant_service.list_tenants = lambda active_only=True: []
    try:
        res = asyncio.run(main.reopen_batch_preview(current_user=dict(SUPERVISOR)))
        check(res.get("enviaveis") == 0 and varreduras == [1],
              "default (doc ausente): lote ligado, previa roda normal")
        STORE["system_settings"] = {"chat": {"reopen_batch_enabled": False}}
        varreduras.clear()
        exc = expect_http(lambda: asyncio.run(main.reopen_batch_preview(current_user=dict(SUPERVISOR))),
                          409, "flag desligada: previa -> 409")
        check(exc is not None and exc.detail == "Reabertura em lote desligada para esta empresa.",
              "detalhe do 409 legivel para o admin")
        bt = BackgroundTasks()
        expect_http(lambda: asyncio.run(main.reopen_batch_execute(
            _FakeRequest({"max_sends": 10}), bt, current_user=dict(SUPERVISOR))),
            409, "flag desligada: disparo -> 409")
        check(varreduras == [] and not STORE.get("reopen_batches") and not bt.tasks,
              "409 antes de qualquer varredura: sem scan, sem doc de lote, sem worker")
        expect_http(lambda: asyncio.run(main.reopen_batch_preview(current_user=dict(OPERADOR))),
                    403, "permissao segue antes da flag (operador sem reabrir_em_lote -> 403)")
        STORE["system_settings"]["chat"]["reopen_batch_enabled"] = True
        expect_http(lambda: asyncio.run(main.reopen_batch_execute(
            _FakeRequest({}), BackgroundTasks(), current_user=dict(SUPERVISOR))),
            400, "flag religada: disparo volta ao fluxo normal (400 sem elegiveis)")
        check(varreduras == [1], "flag religada: o scan voltou a rodar")
    finally:
        main._plan_reopen_batch = real_plan
        tenant_service.list_tenants = real_list_tenants
        main._reopen_preview_cache.clear()
        restore_dbf()


def cenario_flags_reabertura_settings():
    titulo("CENARIO 22e — flags da reabertura em system_settings (defaults + coercao no PUT)")
    patch_store()
    reset_rbac()
    real_audit = main.log_audit
    main.log_audit = lambda *a, **k: None
    try:
        s = dbf.get_system_settings()
        check(s.get("reopen_batch_enabled") is True
              and s.get("reopen_bot_audience_enabled") is False
              and s.get("bot_media_turn_enabled") is False,
              "defaults no READ: lote ligado, publico Bot e midia desligados")
        # Gravacao pela camada de dados (caminho do script da Castro): coage para bool.
        dbf.save_system_settings({
            "reopen_batch_enabled": "false", "reopen_bot_audience_enabled": "1",
            "bot_media_turn_enabled": 0,
        })
        doc = STORE.get("system_settings", {}).get("chat", {})
        check(doc.get("reopen_batch_enabled") is False
              and doc.get("reopen_bot_audience_enabled") is True
              and doc.get("bot_media_turn_enabled") is False,
              "save_system_settings coage as 3 chaves para bool ('false'->False, '1'->True, 0->False)")
        dbf.save_system_settings({
            "reopen_batch_enabled": True, "reopen_bot_audience_enabled": "off",
            "bot_media_turn_enabled": "TRUE",
        })
        doc = STORE["system_settings"]["chat"]
        check(doc.get("reopen_batch_enabled") is True
              and doc.get("reopen_bot_audience_enabled") is False
              and doc.get("bot_media_turn_enabled") is True,
              "segunda gravacao: True/'off'/'TRUE' -> True/False/True")
        # PUT da UI (objeto inteiro, aba stale) NAO consegue mexer nas flags da Castro.
        dbf.save_system_settings({"reopen_batch_enabled": False})
        res = asyncio.run(main.update_settings_system(_FakeRequest({
            "reopen_batch_enabled": True, "reopen_bot_audience_enabled": True,
            "bot_media_turn_enabled": True, "alarm_threshold_minutes": 7,
        }), current_user=dict(ADMIN)))
        doc = STORE["system_settings"]["chat"]
        check(doc.get("reopen_batch_enabled") is False
              and doc.get("reopen_bot_audience_enabled") is False
              and doc.get("bot_media_turn_enabled") is True,
              "PUT da UI descarta as flags da Castro (aba stale nao religa o lote)")
        check(res.get("alarm_threshold_minutes") == 7,
              "o resto do PUT da UI continua sendo gravado")
    finally:
        main.log_audit = real_audit
        restore_dbf()


def cenario_teto_contato_helper():
    titulo("CENARIO 22f — teto por contato: leitura unificada (reopen_batch_sent_at + legado)")
    _now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    _A = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    _B = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    _C = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    _D = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
    contato = {
        "reopen_batch_sent_at": [
            {"at": _A.isoformat(), "audience": "bot"},          # script grava nas 2 listas
            {"at": _B.isoformat(), "audience": "reception"},
            {"at": _C.isoformat(), "audience": "reception"},    # fora da janela de 90d
            {"at": "lixo", "audience": "bot"},
            {"audience": "reception"},                          # sem at
        ],
        "reopen_bot_sent_at": [
            _A.isoformat(),                                     # duplicata exata
            "2026-09-23T12:00:00Z",                             # mesmo instante, outro formato
            "2026-09-23T09:00:00-03:00",                        # mesmo instante, offset BR
            "2026-09-30T08:00:00",                              # naive = UTC, so no legado
            _B.isoformat(),                                     # dup de item com audiencia explicita
            None,
        ],
    }
    r = dbf.reopen_batch_sends(contato, window_days=90, now=_now)
    check([(s["at"], s["audience"]) for s in r] == [(_A, "bot"), (_D, "bot"), (_B, "reception")],
          "janela 90d: 3 envios unicos em ordem; dedup pelo instante; legado lido como bot")
    check(len(dbf.reopen_batch_sends(contato, now=_now)) == 4,
          "sem janela: inclui o envio antigo (4 unicos), ignora lixo/None/sem at")
    _borda = {"reopen_bot_sent_at": [(_now - timedelta(days=90)).isoformat(),
                                     (_now - timedelta(days=90, seconds=1)).isoformat()]}
    check(len(dbf.reopen_batch_sends(_borda, window_days=90, now=_now)) == 1,
          "borda da janela: at == now-90d entra, 1s antes fica fora")
    check(dbf.reopen_batch_sends({}, window_days=90) == [] and dbf.reopen_batch_sends(None) == [],
          "contato sem listas (ou None) -> lista vazia")
    import importlib
    _script = importlib.import_module("scripts.reopen_bot_audience_once")
    check(_script.reopen_batch_sends is dbf.reopen_batch_sends
          and not hasattr(_script, "_sent_timestamps"),
          "script one-off usa o helper unificado do CRM no teto por contato")


def cenario_recibo_nao_reabre():
    titulo("CENARIO 18 — recibo/clique de controle nao reabrem nem contam (revisao)")
    patch_store()
    STORE["wa_contacts"] = {"80": {"id": 80, "wa_id": "5531955554444",
                                   "assigned_to": None, "qualification": "convertido",
                                   "unread_count": 0, "source_channel_type": "standard"}}
    STORE["wa_conversations"] = {"6__5531955554444": {
        "id": "6__5531955554444", "contact_id": 80,
        "attendance_status": "fechado_manual", "unread_count": 0,
        "last_message_at": _ts(1),
    }}

    def _save(direction, **kw):
        contato = dict(STORE["wa_contacts"]["80"])
        kw.setdefault("status", "sent" if direction == "outbound" else "received")
        dbf.save_wa_message(
            wa_message_id="", contact_id=80, direction=direction, msg_type="text",
            content="x",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            channel_id=6, conversation_id="6__5531955554444", contact=contato, **kw,
        )
        return STORE["wa_conversations"]["6__5531955554444"]

    # Recibo de fechamento: outbound com reopen_attendance=False NAO reabre.
    conv = _save("outbound", sender_user_id=7, reopen_attendance=False,
                 promote_qualification=False)
    check(conv.get("attendance_status") == "fechado_manual",
          "recibo (reopen_attendance=False) nao reabre o atendimento fechado")

    # Clique de avaliacao: inbound control_message nao conta nem reabre nada.
    lma_antes = STORE["wa_contacts"]["80"].get("last_message_at")
    conv = _save("inbound", control_message=True)
    check(conv.get("attendance_status") == "fechado_manual",
          "clique de controle nao reabre o atendimento")
    check(int(conv.get("unread_count") or 0) == 0,
          "clique de controle nao incrementa nao-lido da thread")
    check(int(STORE["wa_contacts"]["80"].get("unread_count") or 0) == 0,
          "clique de controle nao incrementa nao-lido do contato")
    check(STORE["wa_contacts"]["80"].get("last_message_at") == lma_antes,
          "clique de controle nao avanca recencia do contato")
    check(not STORE.get("attendances_daily"),
          "clique de controle nao cria/reabre Atendimento diario")

    # Comportamento historico preservado: inbound NORMAL reabre e conta.
    conv = _save("inbound")
    check(conv.get("attendance_status") == "aberto"
          and int(conv.get("unread_count") or 0) == 1,
          "inbound normal segue reabrindo e contando (retorno-zumbi intacto)")

    # Upsert do contato (topo do webhook) com control_click: nao bumpa
    # recencia nem auto-atribui coex; last_inbound_at (janela Meta) sobe.
    STORE["wa_contacts"]["81"] = {"id": 81, "wa_id": "5531944443333",
                                  "assigned_to": None, "qualification": "novo",
                                  "last_message_at": "2026-01-01T00:00:00+00:00"}
    STORE["users"] = {"9": {"id": 9, "firebase_uid": "uid9"}}
    dbf.upsert_wa_contact("5531944443333", "Paciente", channel_id=2,
                          source_channel_type="coexistence",
                          auto_assign_user_id=9, skip_conversation_upsert=True,
                          control_click=True)
    ctc81 = STORE["wa_contacts"]["81"]
    check(ctc81.get("last_message_at") == "2026-01-01T00:00:00+00:00",
          "upsert control_click: recencia do contato nao sobe")
    check(ctc81.get("assigned_to") is None,
          "upsert control_click: clique nao muda posse (coex nao auto-atribui)")
    check(ctc81.get("last_inbound_at") is not None,
          "upsert control_click: last_inbound_at sobe (janela Meta e real)")
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

# =========================================================================
# Cenario — P2b: conteudo LGPD na aba Sistema (save real + PUT + audit)
# =========================================================================

ADMIN = {"id": 9, "role": "admin", "tenant_id": "hubloc",
         "display_name": "Admin", "firebase_uid": "uid9"}


def cenario_lgpd_politica_sistema():
    titulo("CENARIO — P2b: politica LGPD na aba Sistema (validacao no save + PUT + audit)")
    import lgpd_bot
    patch_store()
    reset_rbac()
    audits = []
    real_audit = main.log_audit
    main.log_audit = lambda uid, action, detail="", *a, **k: audits.append((uid, action, detail))
    hoje = lgpd_bot.hoje_br(datetime.now(timezone.utc))
    amanha = (hoje + timedelta(days=1)).isoformat()
    data_pol = (hoje - timedelta(days=90)).isoformat()
    data_pol2 = (hoje - timedelta(days=30)).isoformat()
    aviso = "Aviso da clinica: seus dados de saude sao tratados conforme a LGPD."
    try:
        s = dbf.get_system_settings()
        check(s.get("lgpd_policy_date") == "" and s.get("lgpd_privacy_url") == ""
              and s.get("lgpd_notice") == "",
              "defaults vazios no READ (bot cai no fallback: nada muda no deploy)")
        for campos, rotulo in (
            ({"lgpd_policy_date": amanha}, "data futura"),
            ({"lgpd_privacy_url": "http://clinica.example/politica"}, "link sem https"),
            ({"lgpd_notice": "x" * 901}, "aviso com 901 caracteres"),
        ):
            try:
                dbf.save_system_settings(campos)
                levantou = False
            except ValueError:
                levantou = True
            doc = STORE.get("system_settings", {}).get("chat", {})
            check(levantou and not any(k in doc for k in campos),
                  f"save real rejeita {rotulo} (ValueError) e nao grava nada")

        exc = expect_http(lambda: asyncio.run(main.update_settings_system(
            _FakeRequest({"lgpd_policy_date": amanha}), current_user=dict(ADMIN))),
            400, "PUT com data futura")
        check(exc is not None and "futura" in str(exc.detail),
              "detalhe do 400 legivel (explica que a data nao pode ser futura)")
        expect_http(lambda: asyncio.run(main.update_settings_system(
            _FakeRequest({"lgpd_policy_date": data_pol}), current_user=dict(SUPERVISOR))),
            403, "supervisor sem gerenciar_config_sistema nao edita a politica")

        # Objeto INTEIRO, como o frontend manda.
        body = dict(dbf.get_system_settings())
        body.update(lgpd_policy_date=data_pol, lgpd_privacy_url=" https://clinica.example/politica ",
                    lgpd_notice=aviso)
        res = asyncio.run(main.update_settings_system(_FakeRequest(body), current_user=dict(ADMIN)))
        check(res.get("lgpd_policy_date") == data_pol
              and res.get("lgpd_privacy_url") == "https://clinica.example/politica"
              and res.get("lgpd_notice") == aviso,
              "PUT valido persiste os 3 campos (link normalizado)")
        lg = [a for a in audits if a[1] == "LGPD_POLICY_UPDATE"]
        check(len(lg) == 1 and lg[0][0] == ADMIN["id"]
              and lg[0][2] == f"data (vazia) -> {data_pol} | link alterado | aviso alterado",
              "LGPD_POLICY_UPDATE: data antiga -> nova + link/aviso alterados")
        check(all(aviso not in a[2] for a in audits),
              "texto do aviso nao vai inteiro para nenhum audit")

        body2 = dict(res)
        body2["alarm_enabled"] = False
        asyncio.run(main.update_settings_system(_FakeRequest(body2), current_user=dict(ADMIN)))
        check(len([a for a in audits if a[1] == "LGPD_POLICY_UPDATE"]) == 1,
              "save de outro campo (objeto inteiro) nao registra troca de politica")

        body3 = dict(res)
        body3["lgpd_policy_date"] = data_pol2
        asyncio.run(main.update_settings_system(_FakeRequest(body3), current_user=dict(ADMIN)))
        lg = [a for a in audits if a[1] == "LGPD_POLICY_UPDATE"]
        check(len(lg) == 2 and lg[-1][2] == f"data {data_pol} -> {data_pol2} | link mantido | aviso mantido",
              "troca so da data: audit com data antiga -> nova, link/aviso mantidos")
    finally:
        main.log_audit = real_audit
        restore_dbf()


# =========================================================================
# Reabertura por publico (plano v2.2, etapa 3): scan unico com dois baldes
# =========================================================================

_NOW3 = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
_TPL_RETOMADA = {
    "name": "varizemed_retomada_generica_utility_v1", "language": "pt_BR", "category": "UTILITY",
    "components": [
        {"type": "BODY", "text": "Ola {{1}}, sua ultima conversa foi em {{2}}.",
         "example": {"body_text": [["Rafael", "01/01/2026"]]}},
        {"type": "BUTTONS", "buttons": [
            {"type": "QUICK_REPLY", "text": "Continuar"},
            {"type": "QUICK_REPLY", "text": "Encerrar atendimento"}]},
    ],
}
# Canais do tenant no sim: 6 e 8 standard COM template, 7 standard SEM
# template, 9 coexistence (fora do lote por inteiro).
_CANAIS3 = [
    {"id": 6, "channel_type": "standard", "is_active": True, "owner_user_id": None},
    {"id": 7, "channel_type": "standard", "is_active": True, "owner_user_id": None},
    {"id": 8, "channel_type": "standard", "is_active": True, "owner_user_id": None},
    {"id": 9, "channel_type": "coexistence", "is_active": True, "owner_user_id": 7},
]
_CHANNELS_OK3 = {6: True, 7: False, 8: True}


def _seed_publicos(now):
    """Um contato por caso da secao 10 que depende da selecao. Devolve
    {contact_id: (estado na visao Recepcao, estado na visao Bot)} esperado —
    estado = "enviavel" | "auto_resolve" | motivo do pulo."""
    def ago(**kw):
        return now - timedelta(**kw)

    def iso(**kw):
        return ago(**kw).isoformat()

    contacts, threads, msgs, states = {}, {}, {}, {}
    expected = {}

    def contato(cid, exp, **kw):
        base = {"id": cid, "wa_id": f"5531900{cid:06d}", "qualification": "novo",
                "lgpd_consent": True, "last_inbound_at": iso(hours=30),
                "assigned_to": None, "bot_completed": False, "channel_id": 6,
                "display_name": f"Lead {cid}"}
        base.update(kw)
        contacts[str(cid)] = base
        if exp is not None:
            expected[cid] = exp
        return base

    def thread(cid, ch, **kw):
        tid = f"{ch}__{contacts[str(cid)]['wa_id']}"
        base = {"id": tid, "contact_id": cid, "channel_id": ch,
                "attendance_status": "aberto", "last_message_at": iso(hours=30)}
        base.update(kw)
        threads[tid] = base
        return tid

    def msg(cid, conv, content, ts, **kw):
        base = {"contact_id": cid, "conversation_id": conv, "direction": "outbound",
                "sender_user_id": None, "msg_type": "text", "content": content,
                "timestamp_wa": ts}
        base.update(kw)
        msgs[f"m{len(msgs) + 1}"] = base

    RH, BOT = ("enviavel", "atendimento_humano"), ("fase_bot", "enviavel")
    link = "Agende aqui: https://marcaconsultas.com.br/varizemed"

    # Caso 1: aviso LGPD sem resposta. Caso 7: recusou.
    contato(101, ("consentimento_ausente",) * 2, lgpd_consent=None); thread(101, 6)
    contato(107, ("consentimento_ausente",) * 2, lgpd_consent=False); thread(107, 6)
    # Caso 2: aceitou, Val respondeu, sumiu > 24h -> Bot.
    contato(102, BOT); c102 = thread(102, 6); msg(102, c102, "Posso ajudar?", ago(hours=31))
    # Caso 3: handoff sem atendimento (novo + bot_completed) <= 30d -> Recepcao;
    # P4: 31 dias fora (so Recepcao); borda exata de 30 dias entra.
    contato(103, RH, bot_completed=True, last_inbound_at=iso(days=5), department_id=2); thread(103, 6)
    contato(1031, ("mais_antigo_que_limite", "atendimento_humano"), bot_completed=True,
            last_inbound_at=iso(days=31)); thread(1031, 6)
    contato(1032, RH, bot_completed=True, last_inbound_at=iso(days=30)); thread(1032, 6)
    # Caso 4: handoff e conversaram (em_atendimento).
    contato(104, RH, qualification="em_atendimento", bot_completed=True, department_id=2)
    thread(104, 6, last_human_outbound_at=ago(days=2))
    # Casos 5 e 21: desfecho terminal nem entra na varredura.
    contato(105, None, qualification="convertido"); thread(105, 6)
    contato(121, None, qualification="nao_convertido", last_inbound_at=iso(days=9)); thread(121, 6)
    # Caso 6 COM marco: atendido ANTES do release -> Bot (D2).
    contato(106, BOT, qualification="em_atendimento", bot_released_at=ago(days=3))
    c106 = thread(106, 6, last_human_outbound_at=ago(days=4))
    # Casos 6/27 SEM marco (legado): criterio 4 ignorado, criterio 2 decide.
    contato(1061, BOT, qualification="em_atendimento")
    thread(1061, 6, last_human_outbound_at=ago(days=10))
    # Caso 10: supervisor respondeu na aba Bot DEPOIS do marco -> Recepcao.
    contato(110, RH, qualification="em_atendimento", bot_released_at=ago(days=5))
    thread(110, 6, last_human_outbound_at=ago(days=2))
    # Caso 11 (CX): devolvido pelo menu (return_contact_to_bot) -> caso 6.
    contato(111, BOT, bot_released_at=ago(days=2)); thread(111, 6, last_human_outbound_at=ago(days=6))
    # Caso 12: lead com dono, frio -> Recepcao.
    contato(112, RH, qualification="em_atendimento", assigned_to=7, bot_completed=True,
            department_id=3); thread(112, 6)
    # Caso 14: ignorou o template da Recepcao -> auto-resolve Recepcao.
    contato(114, ("auto_resolve", "tentativa_outro_publico"), qualification="em_atendimento",
            bot_completed=True, reopen_attempts=1, last_reopen_audience="reception",
            last_reopen_at=iso(hours=30), last_reopen_template_at=iso(hours=30),
            last_inbound_at=iso(days=3))
    thread(114, 6)
    # Caso 15: 2 retomadas em 90 dias (qualquer publico) -> teto_contato;
    # com 1 dentro da janela (a outra ha 100 dias) ainda entra.
    contato(115, ("teto_contato",) * 2, qualification="em_atendimento", assigned_to=7,
            bot_completed=True, last_reopen_template_at=iso(days=10),
            reopen_batch_sent_at=[{"at": iso(days=40), "audience": "bot"},
                                  {"at": iso(days=10), "audience": "reception"}]); thread(115, 6)
    contato(1151, RH, qualification="em_atendimento", assigned_to=7, bot_completed=True,
            reopen_batch_sent_at=[{"at": iso(days=100), "audience": "bot"},
                                  {"at": iso(days=10), "audience": "reception"}]); thread(1151, 6)
    # Caso 18: duas threads. Coexistence com resposta humana apos o marco
    # decide no CONTATO (Recepcao); envio pela standard mais recente (canal 8).
    contato(118, RH, bot_released_at=ago(days=5))
    thread(118, 9, last_human_outbound_at=ago(days=1))
    thread(118, 6, last_message_at=iso(days=3))
    thread(118, 8, last_message_at=iso(days=2))
    # Empate de last_message_at entre standards: menor channel_id (6).
    contato(1181, RH, qualification="em_atendimento", assigned_to=7, bot_completed=True)
    thread(1181, 8, last_message_at=iso(days=2)); thread(1181, 6, last_message_at=iso(days=2))
    # Caso 23: canal sem template compativel. Sem thread standard (coex,
    # nenhuma thread, so backup).
    contato(123, ("sem_template",) * 2, qualification="em_atendimento", assigned_to=7,
            bot_completed=True); thread(123, 7)
    contato(1231, ("sem_thread_standard",) * 2); thread(1231, 9)
    contato(1232, ("sem_thread_standard",) * 2)
    contato(1233, ("sem_thread_standard",) * 2, assigned_to=7, bot_completed=True)
    thread(1233, 6, is_backup=True)
    # Caso 26: template como Recepcao, devolvido ao bot antes do lote seguinte
    # -> auto-resolve pela audiencia da TENTATIVA (Recepcao).
    contato(126, ("auto_resolve", "tentativa_outro_publico"), qualification="em_atendimento",
            reopen_attempts=1, last_reopen_audience="reception", last_reopen_at=iso(days=2),
            last_reopen_template_at=iso(days=2), bot_released_at=ago(days=1),
            last_inbound_at=iso(days=4)); thread(126, 6)
    # Caso 29 (P5): bot_outcome preenchido -> fora do Bot (desfecho_bot).
    contato(129, ("fase_bot", "desfecho_bot"), bot_outcome="agendado"); thread(129, 6)
    # P5 heuristica: link da Val no ciclo -> desfecho_bot; antes do marco,
    # de humano, no template do lote ou alem das 40 ultimas -> nao conta.
    contato(1291, ("fase_bot", "desfecho_bot")); c = thread(1291, 6)
    msg(1291, c, link, ago(days=2))
    contato(1292, BOT, bot_released_at=ago(days=2)); c = thread(1292, 6)
    msg(1292, c, link, ago(days=5))
    contato(1293, BOT); c = thread(1293, 6)
    msg(1293, c, link, ago(days=3), sender_user_id=7)
    msg(1293, c, "[Reabertura em lote: marcaconsultas]", ago(days=2), msg_type="template")
    contato(1294, BOT); c = thread(1294, 6)
    msg(1294, c, link, ago(days=10))
    for i in range(40):
        msg(1294, c, f"resposta {i}", ago(days=9, minutes=-i))
    # Caso 31 (P2b): aceite anterior a data da politica -> fora.
    contato(131, ("politica_desatualizada",) * 2, qualification="em_atendimento", assigned_to=7,
            bot_completed=True, lgpd_consent_at=iso(days=60)); thread(131, 6)
    contato(1311, RH, qualification="em_atendimento", assigned_to=7, bot_completed=True,
            lgpd_consent_at=iso(days=10)); thread(1311, 6)
    # Auto-resolve: supressao por outbound humano apos a tentativa (ancora
    # last_reopen_at; fallback last_reopen_template_at); humano ANTES nao suprime.
    contato(140, ("atendimento_pos_retomada",) * 2, qualification="em_atendimento",
            reopen_attempts=1, last_reopen_audience="reception", last_reopen_at=iso(days=3),
            last_reopen_template_at=iso(days=3), reopen_human_active_at=ago(days=2))
    contato(1401, ("atendimento_pos_retomada",) * 2, qualification="em_atendimento",
            reopen_attempts=1, last_reopen_template_at=iso(days=3),
            reopen_human_active_at=ago(days=2))
    contato(1402, ("auto_resolve", "tentativa_outro_publico"), qualification="em_atendimento",
            assigned_to=7, reopen_attempts=1, last_reopen_audience="reception",
            last_reopen_at=iso(days=2), last_reopen_template_at=iso(days=2),
            reopen_human_active_at=ago(days=3))
    # Tentativa sem audiencia (pre-deploy) ou "manual" -> reclassifica pelo estado.
    contato(141, ("tentativa_outro_publico", "auto_resolve"), reopen_attempts=1,
            last_reopen_template_at=iso(days=2)); thread(141, 6)
    contato(1411, ("auto_resolve", "tentativa_outro_publico"), qualification="em_atendimento",
            assigned_to=7, reopen_attempts=1, last_reopen_audience="manual",
            last_reopen_template_at=iso(days=2))
    # Caso 30: carimbado pelo script de 23/09 (audiencia bot) e ignorou.
    contato(142, ("tentativa_outro_publico", "auto_resolve"), reopen_attempts=1,
            last_reopen_audience="bot", last_reopen_template_at=iso(days=14),
            reopen_bot_sent_at=[iso(days=14)])
    contato(143, ("ja_resolvido",) * 2, reopen_attempts=1, reopen_resolved_at=iso(days=1),
            last_reopen_template_at=iso(days=2))
    # bot_states.human_active (criterio 2.2.3) -> Recepcao.
    contato(144, RH); thread(144, 6); states["144"] = {"human_active": True}
    # Filtros de contato herdados da C2.
    contato(145, ("opt_out",) * 2, reopen_opt_out=True)
    contato(146, ("arquivado",) * 2, is_archived=1)
    contato(147, ("backup",) * 2, is_backup=True)
    contato(148, ("lgpd_revogado",) * 2, lgpd_revoked=True)
    contato(149, ("janela_aberta",) * 2, last_inbound_at=iso(hours=2))
    contato(150, ("janela_desconhecida",) * 2, last_inbound_at=None)
    contato(151, ("cooldown",) * 2, last_reopen_template_at=iso(hours=3))

    STORE["wa_contacts"] = contacts
    STORE["wa_conversations"] = threads
    STORE["wa_messages"] = msgs
    STORE["bot_states"] = states
    return expected


def _ids(rows):
    return [c["id"] for c in rows]


def _view_sum(view):
    return len(view["enviaveis"]) + len(view["auto_resolve"]) + sum(view["pulados"].values())


def cenario_publicos_particao():
    titulo("CENARIO 23 — Reabertura por publico: particao Recepcao x Bot (secao 10)")
    from datetime import date as _date
    patch_store()
    expected = _seed_publicos(_NOW3)
    pol = (_NOW3 - timedelta(days=30)).date()

    def _scan(**kw):
        args = dict(max_attempts=1, cooldown_hours=24, window_hours=24, max_per_contact=2,
                    window_days=90, max_idle_days=30, scan_max=2000,
                    desfecho_link="marcaconsultas", now=_NOW3, with_detail=True)
        args.update(kw)
        return dbf.scan_reopen_audiences(_CHANNELS_OK3, args.pop("cx", True), pol, **args)

    try:
        r = _scan()
        det = r["detalhe"]
        rec, bot = r["audiences"]["reception"], r["audiences"]["bot"]
        errados = {cid: ((det.get(cid) or {}).get("reception"), (det.get(cid) or {}).get("bot"), exp)
                   for cid, exp in expected.items()
                   if ((det.get(cid) or {}).get("reception"), (det.get(cid) or {}).get("bot")) != exp}
        check(not errados, f"cada caso no destino esperado nas duas visoes ({len(expected)} contatos; divergentes={errados})")
        check(105 not in det and 121 not in det and r["total"] == len(expected),
              "casos 5/21: desfecho terminal nem entra na varredura (query por qualification)")
        baldes = [_ids(rec["enviaveis"]), _ids(rec["auto_resolve"]),
                  _ids(bot["enviaveis"]), _ids(bot["auto_resolve"])]
        todos = [i for b in baldes for i in b]
        check(len(todos) == len(set(todos)), "nenhum contato cai em dois baldes")
        check(_view_sum(rec) == r["total"] and _view_sum(bot) == r["total"],
              "cada visao soma o total varrido (enviaveis + auto_resolve + pulados)")
        check(sorted(_ids(bot["enviaveis"])) == [102, 106, 111, 1061, 1292, 1293, 1294],
              f"Bot = casos 2, 6 (com/sem marco), 11 CX e P5 fora do ciclo ({sorted(_ids(bot['enviaveis']))})")
        check(sorted(_ids(rec["auto_resolve"])) == [114, 126, 1402, 1411]
              and sorted(_ids(bot["auto_resolve"])) == [141, 142],
              "auto-resolve pelo publico da TENTATIVA (14, 26, manual/ausente reclassificado, 30)")
        chave = [(0 if c["qualification"] == "em_atendimento" else 1,
                  -datetime.fromisoformat(c["last_inbound_at"]).timestamp())
                 for c in rec["enviaveis"]]
        check(chave == sorted(chave) and rec["enviaveis"][-1]["id"] == 1032,
              "ordem 2.3: em_atendimento antes de novo; ultimo inbound mais recente primeiro")
        alvo = {c["id"]: c["_reopen_target"] for c in rec["enviaveis"] + bot["enviaveis"]}
        check(alvo[118]["channel_id"] == 8 and alvo[118]["conversation_id"] == "8__5531900000118",
              "caso 18: criterios no contato (coex atendida -> Recepcao), envio pela standard mais recente")
        check(alvo[1181]["channel_id"] == 6, "thread candidata: empate de last_message_at -> menor channel_id")
        check(all(t["channel_id"] in (6, 8) for t in alvo.values()),
              "envio so por canal standard ativo com template (nunca 7 sem template nem 9 coex)")
        check(rec["por_setor"].get(2) == 2 and rec["por_setor"].get(3) == 1,
              f"por_setor por publico (Recepcao: {rec['por_setor']})")
        check(rec["pulados"].get("fase_bot") == 9 and bot["pulados"].get("desfecho_bot") == 2
              and bot["pulados"].get("atendimento_humano") == 11,
              f"motivos do outro balde: fase_bot={rec['pulados'].get('fase_bot')} "
              f"desfecho_bot={bot['pulados'].get('desfecho_bot')} "
              f"atendimento_humano={bot['pulados'].get('atendimento_humano')}")
        lt = r["leituras"]
        check(lt["threads"] == 24 and lt["bot_states"] == 13 and lt["mensagens"] == 8,
              f"custo: threads/bot_states/mensagens so p/ sobreviventes ({lt})")

        # Sem heuristica (REOPEN_DESFECHO_LINK vazio): o link nao tira do Bot.
        r2 = _scan(desfecho_link="")
        check(1291 in _ids(r2["audiences"]["bot"]["enviaveis"]) and r2["leituras"]["mensagens"] == 0,
              "REOPEN_DESFECHO_LINK vazio desliga a heuristica (sem query de mensagens)")
        # Sem data de politica: o aceite antigo (caso 31) volta a valer.
        r3 = dbf.scan_reopen_audiences(_CHANNELS_OK3, True, None, now=_NOW3, with_detail=True,
                                       desfecho_link="marcaconsultas")
        check(r3["detalhe"][131]["reception"] == "enviavel",
              "sem lgpd_policy_date: politica_desatualizada nao se aplica")

        # Tenant SEM motor CX (builtin, Hubloc): nao ha fase de bot.
        rb = _scan(cx=False)
        db_ = rb["detalhe"]
        check(rb["audiences"]["bot"]["enviaveis"] == [] and rb["leituras"]["bot_states"] == 0,
              "builtin: publico Bot vazio e nenhuma leitura de bot_states")
        check(all(db_[i]["reception"] == "aguardando_bot" for i in (102, 106, 111, 118, 144, 1061)),
              "casos 11 builtin/19: sem dono + bot_completed falso -> aguardando_bot (fora da Recepcao)")
        check(db_[141]["reception"] == "auto_resolve" and db_[142]["bot"] == "auto_resolve",
              "builtin: tentativa sem audiencia reclassifica p/ Recepcao; a do script segue no Bot")
        check(db_[1031]["reception"] == "mais_antigo_que_limite" and db_[103]["reception"] == "enviavel",
              "caso 19: Recepcao muda pelo P4 tambem no builtin")
        check(_view_sum(rb["audiences"]["reception"]) == rb["total"], "builtin: visao Recepcao soma o total")

        # Corte REOPEN_SCAN_MAX depois da ordenacao: excedente nao paga leitura.
        rc = _scan(scan_max=3)
        rcr = rc["audiences"]["reception"]
        colocados = [c for v in rc["audiences"].values() for c in v["enviaveis"] + v["auto_resolve"]]
        check(rc["excedente"] > 0 and rcr["pulados"].get("limite_varredura") == rc["excedente"]
              and rc["audiences"]["bot"]["pulados"].get("limite_varredura") == rc["excedente"]
              and _view_sum(rcr) == rc["total"],
              f"corte: {rc['excedente']} candidatos alem do limite -> limite_varredura nas duas visoes")
        check(rc["leituras"]["threads"] <= 3 and len(colocados) <= 3
              and all(c["qualification"] == "em_atendimento" for c in colocados),
              "corte: so os 3 primeiros da ordem (em_atendimento) pagam leitura")

        # Conciliacao 11.1 (tools/reopen_conciliation.py) sobre o mesmo store:
        # nivel de scan, todo canal standard conta como tendo template.
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "reopen_conciliation", os.path.join(ROOT, "tools", "reopen_conciliation.py"))
        conc_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(conc_mod)
        v1, v2 = conc_mod.classificar({6: True, 7: True, 8: True}, True, pol, now=_NOW3)
        cc = conc_mod.conciliar(v1, v2)
        check(cc["recepcao_v1"] == 11 and cc["recepcao_v2"] == 11
              and {k: v for k, v in cc["parcelas"].items() if v} == {
                  "fase_bot": [106, 1061], "teto_contato": [115], "politica_desatualizada": [131]}
              and cc["novo_pos_handoff_elegivel"] == [103, 1032],
              f"conciliacao: v1 11 - (fase_bot 2 + teto 1 + politica 1) + novo pos-handoff 2 ({cc['parcelas']})")
        check(cc["esperado"] == 9 and cc["residuo"] == 2 and cc["residuo_inexplicado"] == 0
              and cc["novo_em_atendimento_humano"] == {"humano_pos_marco": [118], "human_active": [144]},
              "conciliacao: residuo 2 = novo em atendimento humano (caso 18 e human_active), 0 inexplicado")
        _v1b = {"enviaveis": [{"id": 1}, {"id": 2}], "auto_resolve": [], "pulados": {}}
        _v2b = {"detalhe": {1: {"reception": "cooldown"},
                            2: {"reception": "enviavel", "qualification": "em_atendimento"},
                            3: {"reception": "enviavel", "qualification": "em_atendimento", "via": "dono"}}}
        cb = conc_mod.conciliar(_v1b, _v2b)
        check(cb["residuo_inexplicado"] == 2 and cb["saida_inexplicada"] == {"cooldown": [1]}
              and cb["entrada_inexplicada"] == {"em_atendimento/dono": [3]},
              "conciliacao: saida/entrada fora das parcelas viram residuo inexplicado (bug)")
        from google.cloud.firestore_v1 import (
            batch as _fb, collection as _fc, document as _fdoc, transaction as _ft)
        _alvos = [(_fdoc.DocumentReference, n) for n in ("set", "update", "delete", "create")] + [
            (_fc.CollectionReference, "add"), (_fb.WriteBatch, "commit"), (_ft.Transaction, "commit")]
        _originais = [(cls, n, cls.__dict__.get(n)) for cls, n in _alvos]
        try:
            conc_mod.trava_escrita()
            try:
                _fdoc.DocumentReference("c", "d", client=None).set({"x": 1})
                bloqueou = False
            except RuntimeError:
                bloqueou = True
            check(bloqueou, "conciliacao: trava de escrita do cliente Firestore (so leitura)")
        finally:
            for cls, n, orig in _originais:
                if orig is None:
                    delattr(cls, n)  # metodo herdado: volta a resolver na base
                else:
                    setattr(cls, n, orig)
    finally:
        restore_dbf()


def _reopen_api_env(ai_cfg, tenants=("varizemed", "hubloc"), request_tenant="varizemed"):
    """Stubs do caminho HTTP da reabertura (sem Firestore/Meta reais).
    reopen_batches fica POR TENANT no store (chave "{tid}/reopen_batches")
    para o teto diario somar tenants de verdade. Devolve (restore, contadores)."""
    def _tcoll(coll):
        tid = firestore_common.get_tenant_context()
        return f"{tid}/{coll}" if (tid and coll == "reopen_batches") else coll

    contadores = {"scan": 0, "tpl": 0, "channels_creds": []}
    real = {
        "dbf.collection": dbf.collection, "dbf.document": dbf.document,
        "main.fs_coll": main.fs_coll, "main.fs_document": main.fs_document,
        "get_all_active_channels": channel_service.get_all_active_channels,
        "tpl": main._resolve_reopen_template, "get_tenant": tenant_service.get_tenant,
        "list_tenants": tenant_service.list_tenants, "next_seq": database.next_sequence,
        "log_audit": main.log_audit, "scan": database.scan_reopen_audiences,
    }
    dbf.collection = lambda coll: _CollRef(_tcoll(coll))
    dbf.document = lambda coll, doc_id: _DocRef(_tcoll(coll), doc_id)
    main.fs_coll = lambda coll: _CollRef(_tcoll(coll))
    main.fs_document = lambda coll, doc_id: _DocRef(_tcoll(coll), doc_id)
    channel_service.get_all_active_channels = lambda: [dict(c) for c in _CANAIS3]

    async def _fake_tpl(ch):
        contadores["tpl"] += 1
        return dict(_TPL_RETOMADA) if ch.get("id") in (6, 8) else None

    main._resolve_reopen_template = _fake_tpl
    tenant_service.get_tenant = lambda tid: {"id": tid, "settings": {"ai": dict(ai_cfg)}}
    tenant_service.list_tenants = lambda active_only=True: [{"id": t} for t in tenants]
    database.next_sequence = dbf.next_sequence
    main.log_audit = lambda *a, **k: None

    def _scan_contado(*a, **k):
        contadores["scan"] += 1
        return real["scan"](*a, **k)

    database.scan_reopen_audiences = _scan_contado
    main._reopen_preview_cache.clear()
    token = firestore_common.set_tenant_context(request_tenant)

    def restore():
        firestore_common.reset_tenant_context(token)
        dbf.collection, dbf.document = real["dbf.collection"], real["dbf.document"]
        main.fs_coll, main.fs_document = real["main.fs_coll"], real["main.fs_document"]
        channel_service.get_all_active_channels = real["get_all_active_channels"]
        main._resolve_reopen_template = real["tpl"]
        tenant_service.get_tenant = real["get_tenant"]
        tenant_service.list_tenants = real["list_tenants"]
        database.next_sequence = real["next_seq"]
        main.log_audit = real["log_audit"]
        database.scan_reopen_audiences = real["scan"]
        main._reopen_preview_cache.clear()

    return restore, contadores


_AI_CX = {"bot_engine": "dialogflow_cx", "status": "active"}
_OLD_PREVIEW_KEYS = ("enviaveis", "auto_resolve", "pulados", "por_setor", "amostra", "max_sends_default")


def _seed_batches(now, usados_varizemed=140, abortado=5, hubloc_reserva=100):
    """Lotes das ultimas 24h nos dois tenants (teto do portfolio)."""
    STORE["varizemed/reopen_batches"] = {
        "1": {"id": 1, "status": "concluido", "enviados": usados_varizemed, "planejados": 150,
              "started_at": (now - timedelta(hours=2)).isoformat()},
        "2": {"id": 2, "status": "abortado", "enviados": abortado, "planejados": 100,
              "started_at": (now - timedelta(hours=3)).isoformat()},
        "3": {"id": 3, "status": "concluido", "enviados": 90,
              "started_at": (now - timedelta(hours=30)).isoformat()},   # fora das 24h
    }
    STORE["hubloc/reopen_batches"] = {
        # Executando de outra instancia: conta a RESERVA (max(enviados, planejados)).
        "7": {"id": 7, "status": "executando", "enviados": 10, "planejados": hubloc_reserva,
              "started_at": (now - timedelta(hours=1)).isoformat(),
              "last_progress_at": (now - timedelta(hours=1)).isoformat()},
    }


def cenario_previa_publicos_api():
    titulo("CENARIO 24 — Previa por publico: compatibilidade, flags, teto diario e cache")
    patch_store()
    reset_rbac()
    # O endpoint le o relogio real DEPOIS do seed: semear 5 min a frente mantem
    # a borda exata do P4 (30 dias) dentro da janela.
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    _seed_publicos(now)
    STORE["system_settings"] = {"chat": {"bot_enabled": True,
                                         "lgpd_policy_date": (now - timedelta(days=30)).date().isoformat()}}
    _seed_batches(now)
    restore, cont = _reopen_api_env(_AI_CX)
    prev = lambda body=None: asyncio.run(main.reopen_batch_preview(  # noqa: E731
        request=_FakeRequest(body) if body is not None else None, current_user=dict(SUPERVISOR)))
    try:
        res = prev()
        rec = res["audiences"]["reception"]
        check(all(k in res for k in _OLD_PREVIEW_KEYS)
              and all(res[k] == rec[k] for k in _OLD_PREVIEW_KEYS),
              "campos antigos da previa presentes e iguais ao balde Recepcao (tela atual intacta)")
        check(set(res["audiences"]) == {"reception", "bot"}
              and all(set(v) == set(_OLD_PREVIEW_KEYS) for v in res["audiences"].values()),
              "audiences.reception e audiences.bot com as mesmas chaves da previa antiga")
        check(res["enviaveis"] == 10 and res["audiences"]["bot"]["enviaveis"] == 7
              and res["audiences"]["bot"]["auto_resolve"] == 2,
              f"contagens dos dois baldes (Recepcao {res['enviaveis']}, Bot {res['audiences']['bot']['enviaveis']})")
        check(res["bot_disponivel"] is False
              and res["bot_indisponivel_motivo"] == "publico Bot ainda nao liberado para esta empresa",
              "flag do Bot desligada: indisponivel com motivo, contagens ainda visiveis")
        check(res["daily_cap"] == {"cap": 250, "usados_24h": 245, "disponiveis": 5},
              f"teto diario soma os dois tenants (reserva do executando, abortado, fora das 24h) ({res['daily_cap']})")
        a0 = res["amostra"][0]
        check(set(a0) >= {"contact_id", "nome", "department_id", "conversation_id", "channel_id"}
              and a0["conversation_id"].startswith(f"{a0['channel_id']}__"),
              "amostra traz conversation_id/channel_id da thread candidata")
        check(res["pulados"].get("fase_bot") == 9 and "canal_invalido" not in res["pulados"],
              "visao Recepcao mostra o lead do Bot como fase_bot (flag desligada nao muda a classificacao)")
        check(res["cache_hit"] is False and cont["scan"] == 1, "1a previa: varre (sem cache)")

        res2 = prev()
        check(res2["cache_hit"] is True and cont["scan"] == 1
              and res2["audiences"] == res["audiences"],
              "2a previa em < 90s (troca de publico): cache, sem nova varredura")
        res3 = prev({"refresh": True})
        check(res3["cache_hit"] is False and cont["scan"] == 2, "refresh=true ignora o cache")

        main._reopen_preview_cache.clear()

        async def _duas():
            return await asyncio.gather(
                main.reopen_batch_preview(request=None, current_user=dict(SUPERVISOR)),
                main.reopen_batch_preview(request=None, current_user=dict(SUPERVISOR)))
        a, b = asyncio.run(_duas())
        check(cont["scan"] == 3 and sorted([a["cache_hit"], b["cache_hit"]]) == [False, True],
              "uma previa por vez por tenant: a concorrente espera e sai do cache")

        STORE["system_settings"]["chat"]["reopen_bot_audience_enabled"] = True
        res4 = prev()
        check(res4["bot_disponivel"] is True and res4["bot_indisponivel_motivo"] == "",
              "flag ligada + CX ativo + bot_enabled: Bot disponivel")
        STORE["system_settings"]["chat"]["bot_enabled"] = False
        res5 = prev()
        check(res5["bot_disponivel"] is False
              and res5["bot_indisponivel_motivo"] == "bot desligado nas configuracoes da empresa",
              "bot_enabled desligado: Bot indisponivel com motivo")
    finally:
        restore()
        restore_dbf()

    # Caso 19 (Hubloc): builtin -> Bot indisponivel; lote inteiro desligado -> 409.
    patch_store()
    reset_rbac()
    _seed_publicos(now)
    STORE["system_settings"] = {"chat": {"bot_enabled": True}}
    restore, cont = _reopen_api_env({}, tenants=("hubloc",), request_tenant="hubloc")
    try:
        res = asyncio.run(main.reopen_batch_preview(request=None, current_user=dict(SUPERVISOR)))
        check(res["bot_disponivel"] is False and "motor CX" in res["bot_indisponivel_motivo"]
              and res["audiences"]["bot"]["enviaveis"] == 0
              and res["pulados"].get("aguardando_bot", 0) > 0,
              "caso 19: builtin -> Bot indisponivel (motor), aguardando_bot na Recepcao")
        STORE["system_settings"]["chat"]["reopen_batch_enabled"] = False
        expect_http(lambda: asyncio.run(main.reopen_batch_preview(request=None, current_user=dict(SUPERVISOR))),
                    409, "caso 19: reopen_batch_enabled=false -> previa 409")
    finally:
        restore()
        restore_dbf()


def cenario_disparo_publicos():
    titulo("CENARIO 25 — Disparo por publico: audience, 409/422, teto diario e reserva")
    from fastapi import BackgroundTasks
    patch_store()
    reset_rbac()
    now = datetime.now(timezone.utc) + timedelta(minutes=5)  # mesma razao do cenario 24
    _seed_publicos(now)
    STORE["system_settings"] = {"chat": {"bot_enabled": True,
                                         "lgpd_policy_date": (now - timedelta(days=30)).date().isoformat()}}
    _seed_batches(now)
    restore, cont = _reopen_api_env(_AI_CX)
    exe = lambda body, bt=None: asyncio.run(main.reopen_batch_execute(  # noqa: E731
        _FakeRequest(body), bt or BackgroundTasks(), current_user=dict(SUPERVISOR)))
    lotes = lambda: STORE.get("varizemed/reopen_batches", {})  # noqa: E731
    try:
        n0 = len(lotes())
        expect_http(lambda: exe({"audience": "robo"}), 422, "audience invalido -> 422")
        expect_http(lambda: exe({"audience": 123}), 422, "audience nao-string -> 422")
        exc = expect_http(lambda: exe({"audience": "bot"}), 409, "Bot com a flag desligada -> 409")
        check(exc is not None and "ainda nao liberado" in str(exc.detail) and len(lotes()) == n0
              and cont["scan"] == 0,
              "409 do Bot traz o motivo e sai antes de varrer/criar lote")

        # Recepcao (audience ausente = reception). Teto: 245 usados -> 5 disponiveis.
        main._reopen_preview_cache["varizemed"] = (main._monotonic(), {"x": 1})
        bt = BackgroundTasks()
        res = exe({"max_sends": 100}, bt)
        doc = lotes()[str(res["batch_id"])]
        check(res["audience"] == "reception" and doc["audience"] == "reception"
              and doc["criteria_version"] == "v2.2",
              "audience ausente = reception; doc do lote grava audience e criteria_version")
        check(res["planejados"] == 5 and doc["planejados"] == 5 and doc["elegiveis"] == 10,
              "planejados = min(enviaveis 10, max_sends 100, disponiveis 5) — a reserva do teto")
        args = bt.tasks[0].args
        check(args[0] == "varizemed" and len(args[2]) == 5 and len(args[3]) == 4
              and args[7] == "reception" and all("_reopen_target" in c for c in args[2]),
              "worker recebe 5 envios (com thread candidata), 4 auto-resolve e o publico do lote")
        check("varizemed" not in main._reopen_preview_cache, "disparo invalida o cache da previa do tenant")

        # O lote recem-criado conta pela reserva: 245 + 5 = 250 -> teto esgotado.
        lotes()[str(res["batch_id"])].update({"status": "concluido", "enviados": 5})
        exc = expect_http(lambda: exe({}), 409, "teto diario esgotado (250/250) -> 409")
        check(exc is not None and "Teto diario de reaberturas atingido (250 de 250" in str(exc.detail),
              "409 do teto legivel (usados de cap, somando todas as empresas)")

        # Abre espaco (lote de 140 sai das 24h) e libera o publico Bot.
        lotes()["1"]["started_at"] = (now - timedelta(hours=25)).isoformat()
        STORE["system_settings"]["chat"]["reopen_bot_audience_enabled"] = True
        bt = BackgroundTasks()
        res = exe({"audience": "BOT", "max_sends": 3}, bt)
        doc = lotes()[str(res["batch_id"])]
        args = bt.tasks[0].args
        check(res["audience"] == "bot" and doc["audience"] == "bot" and args[7] == "bot",
              "audience=bot (case-insensitive) chega ao doc e ao worker")
        check(res["planejados"] == 3 and [c["id"] for c in args[2]] == [106, 1061, 102],
              "Bot: planejados = max_sends (3) com teto folgado, na ordem 2.3 (em_atendimento primeiro)")
        check(all(c["_reopen_target"]["channel_id"] == 6 for c in args[2]),
              "Bot: cada envio leva a thread candidata (canal 6)")
        check(args[3] == [] and doc["auto_resolve_planejados"] == 0
              and doc["auto_resolve_fora_do_disparo"] == 2,
              "etapa 3: auto-resolve do Bot fica FORA do disparo (so na previa)")
        uso = dbf.reopen_daily_usage(now=now)
        check(uso["por_tenant"] == {"varizemed": 5 + 5 + 3, "hubloc": 100} and uso["usados"] == 113,
              f"reopen_daily_usage por tenant: concluido=enviados, executando=reserva ({uso})")
    finally:
        restore()
        restore_dbf()


def cenario_worker_publico_bot():
    titulo("CENARIO 26 — Worker: publico do lote no carimbo + canal da thread candidata")
    import types as _types
    patch_store()
    now = datetime.now(timezone.utc)
    STORE["wa_contacts"] = {
        "70": {"id": 70, "wa_id": "5531970000070", "channel_id": 6, "qualification": "novo",
               "last_inbound_at": (now - timedelta(hours=30)).isoformat(), "unread_count": 0},
    }
    alvo = {"conversation_id": "8__5531970000070", "channel_id": 8,
            "last_message_at": (now - timedelta(days=2)).isoformat()}
    item = dict(STORE["wa_contacts"]["70"], _reopen_target=alvo)
    creds, enviados = [], []

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": "wamid.BOT1"}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            enviados.append((url, json))
            return _Resp()

    async def _sleep(_s):
        return None

    real = (main.fs_coll, main.fs_document, main.httpx, main.asyncio,
            main._resolve_channel_creds_by_id, main.log_audit)
    main.fs_coll = lambda name: _CollRef(name)
    main.fs_document = dbf.document
    main.httpx = _types.SimpleNamespace(AsyncClient=_Client)
    main.asyncio = _types.SimpleNamespace(sleep=_sleep)
    main._resolve_channel_creds_by_id = lambda chid: (creds.append(chid) or ("tok", f"pnid{chid}", "https://graph.example"))
    main.log_audit = lambda *a, **k: None
    main._reopen_preview_cache["t3"] = (0.0, {})
    try:
        canais = {c["id"]: dict(c) for c in _CANAIS3}
        asyncio.run(main._run_reopen_batch(
            "t3", 9101, [item], [], canais, {6: _TPL_RETOMADA, 8: _TPL_RETOMADA}, 7, "bot"))
        c70 = STORE["wa_contacts"]["70"]
        check(creds == [8] and enviados and enviados[0][0].endswith("/pnid8/messages"),
              "envio sai pelo canal da THREAD CANDIDATA (8), nao pelo contact.channel_id (6)")
        check(c70.get("last_reopen_audience") == "bot"
              and c70.get("last_reopen_conversation_id") == "8__5531970000070"
              and c70.get("last_reopen_channel_id") == 8
              and c70.get("reopen_batch_sent_at") == [{"at": c70.get("last_reopen_at"), "audience": "bot"}],
              "carimbo da tentativa com o publico do LOTE (bot) e a thread candidata")
        msgs = [m for m in STORE.get("wa_messages", {}).values() if m.get("contact_id") == 70]
        check(len(msgs) == 1 and msgs[0].get("conversation_id") == "8__5531970000070",
              "mensagem do template gravada na thread candidata")
        check(STORE["reopen_batches"]["9101"].get("status") == "concluido"
              and STORE["reopen_batches"]["9101"].get("resolvidos") == 0,
              "lote Bot sem auto-resolve no disparo (etapa 3)")
        check("t3" not in main._reopen_preview_cache, "fim do lote invalida o cache da previa")
    finally:
        (main.fs_coll, main.fs_document, main.httpx, main.asyncio,
         main._resolve_channel_creds_by_id, main.log_audit) = real
        main._reopen_preview_cache.clear()
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
    cenario_promocao_qualificacao()
    cenario_auto_close_toggle()
    cenario_fechar_orfa()
    cenario_transfer_rbac()
    cenario_perfis_merge()
    cenario_set_attendance_orfa()
    cenario_gate_desfecho()
    cenario_rating_botao()
    cenario_tags_lead()
    cenario_reabertura_travas()
    cenario_scan_reabertura()
    cenario_worker_lote()
    cenario_reabertura_pontual_carimbo()
    cenario_reopen_human_active()
    cenario_kill_switch_lote()
    cenario_flags_reabertura_settings()
    cenario_teto_contato_helper()
    cenario_publicos_particao()
    cenario_previa_publicos_api()
    cenario_disparo_publicos()
    cenario_worker_publico_bot()
    cenario_recibo_nao_reabre()
    cenario_contato_manual()
    cenario_release_to_bot()
    cenario_return_to_pool()
    cenario_protocolo_dia_anterior()
    cenario_assume_carimba_threads_orfas()
    cenario_open_picker_nao_rouba_pool()
    cenario_unread_sync()
    cenario_lgpd_politica_sistema()

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
