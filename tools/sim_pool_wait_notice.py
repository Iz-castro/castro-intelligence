# -*- coding: utf-8 -*-

"""
Simulador LOCAL do aviso de espera na pool (PO 2026-09-29).

NAO toca em producao: exercita o codigo REAL de database_firestore.py
(pool_wait_notice_eligible, find_pool_wait_notice_candidates,
save_system_settings) e do endpoint /api/internal/cron/pool-wait-notice de
main.py, com Firestore e envio pela Graph API substituidos por stubs em
memoria.

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_pool_wait_notice.py

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

import main  # noqa: E402
import database_firestore as dbf  # noqa: E402
import bot_sender  # noqa: E402
import channel_service  # noqa: E402
import tenant_service  # noqa: E402

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


def titulo(txt):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


# =========================================================================
# Firestore em memoria (suporta ==, >= e <= no where)
# =========================================================================

STORE = {}


class _Snap:
    def __init__(self, coll, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = _DocRef(coll, doc_id)

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, coll, doc_id):
        self.coll = coll
        self.doc_id = str(doc_id)

    def get(self):
        return _Snap(self.coll, self.doc_id, STORE.get(self.coll, {}).get(self.doc_id))

    def set(self, data, merge=False):
        coll = STORE.setdefault(self.coll, {})
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(data)
        else:
            coll[self.doc_id] = dict(data)


def _match(value, op, ref):
    if op == "==":
        return value == ref
    if value is None:
        return False
    try:
        return value >= ref if op == ">=" else value <= ref
    except TypeError:
        return False  # tipo diferente: o Firestore tambem nao casa


class _CollRef:
    def __init__(self, coll):
        self.coll = coll
        self._filters = []

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def stream(self):
        for doc_id, data in list(STORE.get(self.coll, {}).items()):
            if all(_match(data.get(f), op, v) for (f, op, v) in self._filters):
                yield _Snap(self.coll, doc_id, data)


dbf.document = lambda name, doc_id: _DocRef(name, doc_id)
dbf.collection = lambda name: _CollRef(name)

# =========================================================================
# Cenario base
# =========================================================================

BR = timezone(timedelta(hours=-3))
# 2026-09-28 = segunda. Hubloc abre 8h-17h (business_hours).
SEG_10H = datetime(2026, 9, 28, 10, 0, tzinfo=BR).astimezone(timezone.utc)


def conv(**over):
    base = {
        "contact_id": 1, "wa_id": "5531999990001", "channel_id": 4,
        "source_channel_type": "standard", "channel_type": "standard",
        "channel_active": True, "attendance_status": "aberto",
        "assigned_to": None, "is_backup": False,
        "handoff_at": SEG_10H - timedelta(minutes=16),
        "last_inbound_at": SEG_10H - timedelta(minutes=16),
        "last_human_outbound_at": None,
    }
    base.update(over)
    return base


def elig(c, now=SEG_10H, minutes=15, tid="hubloc"):
    return dbf.pool_wait_notice_eligible(c, minutes, tid, now)


def cenario_regras_da_thread():
    titulo("CENARIO 1 — regras de elegibilidade da thread (hubloc, segunda 10h)")
    check(elig(conv()) is True, "16 min na pool, sem dono, sem resposta -> envia")
    check(elig(conv(handoff_at=SEG_10H - timedelta(minutes=14))) is False,
          "14 min na pool -> ainda nao")
    check(elig(conv(handoff_at=SEG_10H - timedelta(minutes=15))) is True,
          "exatamente 15 min -> envia")
    check(elig(conv(assigned_to=7)) is False, "operador assumiu -> nao envia")
    check(elig(conv(last_human_outbound_at=SEG_10H - timedelta(minutes=5))) is False,
          "operador respondeu apos o handoff -> nao envia")
    check(elig(conv(last_human_outbound_at=SEG_10H - timedelta(days=3))) is True,
          "resposta humana de ciclo ANTERIOR nao conta -> envia")
    check(elig(conv(pool_wait_notice_at=SEG_10H - timedelta(minutes=1))) is False,
          "aviso deste ciclo ja saiu -> nao repete")
    check(elig(conv(pool_wait_notice_at=SEG_10H - timedelta(days=2))) is True,
          "aviso de ciclo ANTERIOR nao bloqueia o ciclo novo")
    check(elig(conv(channel_type="coexistence", source_channel_type="coexistence")) is False,
          "canal coex -> nao envia")
    check(elig(conv(channel_type="coexistence", source_channel_type="standard")) is False,
          "thread coex com source herdado 'standard' -> vale o channel_type vivo, nao envia")
    check(elig(conv(channel_type="standard", source_channel_type="coexistence")) is True,
          "lead nascido em coex, thread no standard -> envia (revisao 2026-09-29)")
    check(elig(conv(channel_type="", source_channel_type="coexistence")) is False,
          "doc legado sem channel_type cai no source_channel_type")
    check(elig(conv(channel_active=False)) is False, "canal inativo -> nao envia")
    check(elig(conv(is_backup=True)) is False, "thread de backup -> nao envia")
    check(elig(conv(attendance_status="fechado_manual")) is False, "atendimento fechado -> nao envia")
    check(elig(conv(handoff_at=None)) is False, "sem handoff (nunca passou pelo bot) -> nao envia")
    check(elig(conv(handoff_at=datetime(2026, 9, 28, 12, 44))) is False,
          "handoff naive (timestamp duvidoso) -> nao envia")
    check(elig(conv(handoff_at=SEG_10H - timedelta(hours=25),
                    last_inbound_at=SEG_10H - timedelta(minutes=30))) is False,
          "ciclo com mais de 24h -> nao envia (aviso atrasado de dias)")
    check(elig(conv(last_inbound_at=SEG_10H - timedelta(hours=23, minutes=55),
                    handoff_at=SEG_10H - timedelta(hours=23, minutes=55))) is False,
          "janela de 24h da Meta fechando -> nao envia texto livre")
    check(elig(conv(), minutes=30) is False, "tenant configurado com 30 min -> 16 min nao basta")


def cenario_horario_comercial():
    titulo("CENARIO 2 — horario comercial (relogio conta da abertura)")
    sab_10h = datetime(2026, 9, 26, 10, 0, tzinfo=BR).astimezone(timezone.utc)
    check(elig(conv(handoff_at=sab_10h - timedelta(minutes=30),
                    last_inbound_at=sab_10h - timedelta(minutes=30)), now=sab_10h) is False,
          "sabado (fechado) -> nao envia mesmo com 30 min de espera")
    seg_0730 = datetime(2026, 9, 28, 7, 30, tzinfo=BR).astimezone(timezone.utc)
    lead = conv(handoff_at=seg_0730, last_inbound_at=seg_0730)
    check(elig(lead, now=datetime(2026, 9, 28, 8, 10, tzinfo=BR)) is False,
          "lead das 7h30: as 8h10 ainda nao (conta das 8h)")
    check(elig(lead, now=datetime(2026, 9, 28, 8, 16, tzinfo=BR)) is True,
          "lead das 7h30: as 8h16 envia")
    seg_1655 = datetime(2026, 9, 28, 16, 55, tzinfo=BR)
    lead2 = conv(handoff_at=seg_1655, last_inbound_at=seg_1655)
    check(elig(lead2, now=datetime(2026, 9, 28, 17, 10, tzinfo=BR)) is False,
          "lead das 16h55: 17h10 ja fechou -> nao envia")
    check(elig(lead2, now=datetime(2026, 9, 29, 8, 5, tzinfo=BR)) is True,
          "lead das 16h55: na abertura seguinte envia (janela e ciclo < 24h)")
    sex_20h = datetime(2026, 9, 25, 20, 0, tzinfo=BR)
    lead3 = conv(handoff_at=sex_20h, last_inbound_at=sex_20h)
    check(elig(lead3, now=datetime(2026, 9, 28, 8, 20, tzinfo=BR)) is False,
          "lead de sexta 20h: segunda 8h20 nao envia (janela 24h fechada)")
    check(elig(conv(), tid="tenant-sem-tabela") is True,
          "tenant sem tabela de horario conta do handoff")


def cenario_busca_candidatos():
    titulo("CENARIO 3 — busca de candidatos (contato + 1 thread por contato)")
    STORE.clear()
    STORE["wa_conversations"] = {
        "4__a": conv(contact_id=1, wa_id="a"),
        "5__a": conv(contact_id=1, wa_id="a", channel_id=5,
                     last_inbound_at=SEG_10H - timedelta(minutes=2)),
        "4__b": conv(contact_id=2, wa_id="b"),
        "4__c": conv(contact_id=3, wa_id="c"),
        "4__d": conv(contact_id=4, wa_id="d", handoff_at=SEG_10H - timedelta(days=3)),
    }
    STORE["wa_contacts"] = {
        "1": {"bot_completed": True, "assigned_to": None},
        "2": {"bot_completed": True, "assigned_to": 9},     # dono no LEAD
        "3": {"bot_completed": False, "assigned_to": None},  # voltou pro bot
        "4": {"bot_completed": True, "assigned_to": None},
    }
    out = dbf.find_pool_wait_notice_candidates(15, "hubloc", now=SEG_10H)
    ids = sorted(str(c["conversation"]["id"]) for c in out)
    check(ids == ["5__a"], f"so o contato 1, na thread de inbound mais recente (got {ids})")
    STORE["wa_contacts"]["1"]["qualification"] = "nao_qualificado"
    check(dbf.find_pool_wait_notice_candidates(15, "hubloc", now=SEG_10H) == [],
          "lead marcado N/Q (fora da caixa Novos) -> nao envia")
    STORE["wa_contacts"]["1"]["qualification"] = "novo"
    STORE["wa_contacts"]["1"]["is_archived"] = 1
    check(dbf.find_pool_wait_notice_candidates(15, "hubloc", now=SEG_10H) == [],
          "lead arquivado -> nao envia")
    STORE["wa_contacts"]["1"]["is_archived"] = 0
    check(len(dbf.find_pool_wait_notice_candidates(15, "hubloc", now=SEG_10H)) == 1,
          "qualificacao 'novo' e desarquivado -> volta a ser candidato")
    STORE["wa_contacts"]["1"]["lgpd_revoked"] = True
    check(dbf.find_pool_wait_notice_candidates(15, "hubloc", now=SEG_10H) == [],
          "LGPD revogada -> nao envia")


def cenario_config():
    titulo("CENARIO 4 — validacao da configuracao (save_system_settings)")
    STORE.clear()
    s = dbf.save_system_settings({"pool_wait_notice_minutes": "abc"})
    check(s["pool_wait_notice_minutes"] == 15, "minutos invalidos -> 15")
    s = dbf.save_system_settings({"pool_wait_notice_minutes": 1})
    check(s["pool_wait_notice_minutes"] == 5, "minutos abaixo do piso -> 5")
    s = dbf.save_system_settings({"pool_wait_notice_minutes": 999})
    check(s["pool_wait_notice_minutes"] == 240, "minutos acima do teto -> 240")
    try:
        dbf.save_system_settings({"pool_wait_notice_enabled": True, "pool_wait_notice_text": "  "})
        check(False, "ligar sem texto deveria falhar")
    except ValueError:
        check(True, "ligar sem texto -> ValueError (400 no endpoint)")
    try:
        dbf.save_system_settings({"pool_wait_notice_text": "x" * 1001})
        check(False, "texto > 1000 deveria falhar")
    except ValueError:
        check(True, "texto acima de 1000 caracteres -> ValueError")
    s = dbf.save_system_settings({"pool_wait_notice_enabled": "false"})
    check(s["pool_wait_notice_enabled"] is False, "string 'false' -> desligado (coercao fechada)")
    s = dbf.save_system_settings({"pool_wait_notice_enabled": True,
                                  "pool_wait_notice_text": "  Oi! Ligue para +55 31 3351-7604.  "})
    check(s["pool_wait_notice_enabled"] is True
          and s["pool_wait_notice_text"] == "Oi! Ligue para +55 31 3351-7604.",
          "ligar com texto -> grava (texto aparado)")


def cenario_endpoint():
    titulo("CENARIO 5 — endpoint do cron ponta a ponta (tenant sem tabela de horario)")
    now = datetime.now(timezone.utc)
    STORE.clear()
    STORE["system_settings"] = {"chat": {
        "pool_wait_notice_enabled": True, "pool_wait_notice_minutes": 15,
        "pool_wait_notice_text": "Oi! Ligue para +55 31 3351-7604.",
    }}
    STORE["wa_conversations"] = {
        "4__a": conv(contact_id=1, wa_id="5531999990001",
                     handoff_at=now - timedelta(minutes=20), last_inbound_at=now - timedelta(minutes=20)),
        "4__b": conv(contact_id=2, wa_id="5531999990002",
                     handoff_at=now - timedelta(minutes=5), last_inbound_at=now - timedelta(minutes=5)),
    }
    STORE["wa_contacts"] = {
        "1": {"id": 1, "bot_completed": True, "assigned_to": None},
        "2": {"id": 2, "bot_completed": True, "assigned_to": None},
    }
    SENT, AUDIT = [], []

    async def fake_send(wa_id, reply, contact_id, token, phone_id, channel_id=None,
                        channel_owner_user_id=None):
        SENT.append({"wa_id": wa_id, "text": reply, "contact_id": contact_id,
                     "phone_id": phone_id, "channel_id": channel_id})
        return True

    bot_sender.send_bot_reply = fake_send
    main._verify_cron_auth = lambda request: None
    main.log_audit = lambda uid, action, detail="": AUDIT.append(action)
    tenant_service.list_tenants = lambda active_only=True: [{"id": "tenant-sim"}]
    channel_service.get_channel = lambda cid: {"id": cid, "access_token": "tok",
                                               "phone_number_id": "pn4", "owner_user_id": None}
    main.get_system_settings = dbf.get_system_settings

    res = asyncio.run(main.cron_pool_wait_notice(None))
    check(res.get("sent_total") == 1, f"1 aviso enviado (got {res})")
    check(len(SENT) == 1 and SENT[0]["wa_id"] == "5531999990001",
          "enviado so pro lead com 20 min (o de 5 min espera)")
    check(bool(SENT) and SENT[0]["text"] == "Oi! Ligue para +55 31 3351-7604.",
          "texto do tenant enviado")
    check(bool(SENT) and SENT[0]["phone_id"] == "pn4" and SENT[0]["channel_id"] == 4,
          "enviado pelo canal da thread")
    check(STORE["wa_conversations"]["4__a"].get("pool_wait_notice_at") is not None,
          "ciclo carimbado com pool_wait_notice_at")
    check(AUDIT == ["POOL_WAIT_NOTICE_SENT"], "audit POOL_WAIT_NOTICE_SENT")

    res = asyncio.run(main.cron_pool_wait_notice(None))
    check(res.get("sent_total") == 0 and len(SENT) == 1, "2o tick nao repete o aviso")

    STORE["wa_conversations"]["4__b"]["handoff_at"] = now - timedelta(minutes=40)
    channel_service.get_channel = lambda cid: {"id": cid, "channel_type": "coexistence",
                                               "access_token": "tok", "phone_number_id": "pn4"}
    res = asyncio.run(main.cron_pool_wait_notice(None))
    check(res.get("sent_total") == 0 and len(SENT) == 1,
          "canal VIVO coex (thread dizia standard) -> nada enviado pelo numero pessoal")
    channel_service.get_channel = lambda cid: {"id": cid, "channel_type": "standard", "access_token": "tok",
                                               "phone_number_id": "pn4", "owner_user_id": None}

    STORE["system_settings"]["chat"]["pool_wait_notice_enabled"] = False
    res = asyncio.run(main.cron_pool_wait_notice(None))
    check(res.get("sent_total") == 0 and len(SENT) == 1, "toggle desligado -> nada enviado")


def main_sim():
    cenario_regras_da_thread()
    cenario_horario_comercial()
    cenario_busca_candidatos()
    cenario_config()
    cenario_endpoint()
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
    sys.exit(main_sim())
