# -*- coding: utf-8 -*-

"""Simulador local do debounce do webhook (sem Firestore/Meta/Dialogflow reais).

Exercita o codigo real de webhook._process_messages e seus caminhos concorrentes.
Os adaptadores de persistencia, CX e envio sao stores deterministas em memoria.
"""

import ast
import asyncio
import copy
import inspect
import logging
import os
import sys
import time
import types
import uuid
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webhook as wh  # noqa: E402
import database_firestore as dbf  # noqa: E402
import bot_service  # noqa: E402
import channel_service  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
import tenant_service  # noqa: E402


CONTACTS = {}
CONTACT_BY_WA = {}
STATES = {}
BUFFERS = {}
WA_MESSAGES = {}
SAVED = []
CX_CALLS = []
SENT = []
APPEND_CHANNELS = []
FAILS = []
CHECKS = 0
NEXT_CONTACT = 0
NEXT_MESSAGE = 0

AI_CFG = {
    "bot_engine": "dialogflow_cx",
    "status": "active",
    "buffer_seconds": 0.04,
    "lgpd_policy_version": "test-v1",
}

# system_settings do tenant em memoria (P2b: lgpd_consent_resolved le a data
# da politica LGPD daqui) — o sim nunca toca Firestore real.
SYS_SETTINGS = {"bot_enabled": True}

BLOCK_FIRST_CX = False
FIRST_CX_STARTED = None
RELEASE_FIRST_CX = None

CHANNEL = {
    "id": 7,
    "tenant_id": "varizemed-test",
    "phone_number_id": "phone-7",
    "channel_type": "standard",
    "owner_user_id": None,
    "access_token": "token-test",
}

# Registry de canais do cenario 22 (flush do cron). O coexistence e o numero
# pessoal de um operador: o agente nunca pode responder por ele.
COEX_CHANNEL = {
    "id": 3,
    "tenant_id": "varizemed-test",
    "phone_number_id": "phone-3-coex",
    "channel_type": "coexistence",
    "owner_user_id": 55,
    "access_token": "token-coex",
}
OTHER_TENANT_CHANNEL = {
    "id": 99,
    "tenant_id": "outro-tenant",
    "phone_number_id": "phone-99",
    "channel_type": "standard",
    "owner_user_id": None,
    "access_token": "token-outro-tenant",
}
UNTYPED_CHANNEL = {
    "id": 12,
    "tenant_id": "varizemed-test",
    "phone_number_id": "phone-12",
    "owner_user_id": None,
    "access_token": "token-sem-tipo",
}
CHANNELS = {
    CHANNEL["id"]: CHANNEL,
    COEX_CHANNEL["id"]: COEX_CHANNEL,
    OTHER_TENANT_CHANNEL["id"]: OTHER_TENANT_CHANNEL,
    UNTYPED_CHANNEL["id"]: UNTYPED_CHANNEL,
}


def check(condition, label):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"      OK  {label}")
    else:
        FAILS.append(label)
        print(f"      FALHOU  {label}")


def title(text):
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


class _Snap:
    def __init__(self, data):
        self._data = copy.deepcopy(data)

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.doc_id = str(doc_id)

    def _store(self):
        if self.collection == "bot_states":
            return STATES
        if self.collection == "bot_buffers":
            return BUFFERS
        if self.collection == "wa_contacts":
            return CONTACTS
        return {}

    def get(self):
        return _Snap(self._store().get(self.doc_id))

    def set(self, data, merge=False):
        store = self._store()
        if merge and self.doc_id in store:
            store[self.doc_id].update(copy.deepcopy(data))
        else:
            store[self.doc_id] = copy.deepcopy(data)

    def delete(self):
        self._store().pop(self.doc_id, None)


def _reset(consented=True, assigned=False, completed=False):
    global NEXT_CONTACT, NEXT_MESSAGE, BLOCK_FIRST_CX, FIRST_CX_STARTED, RELEASE_FIRST_CX
    CONTACTS.clear()
    CONTACT_BY_WA.clear()
    STATES.clear()
    BUFFERS.clear()
    WA_MESSAGES.clear()
    SAVED.clear()
    CX_CALLS.clear()
    SENT.clear()
    APPEND_CHANNELS.clear()
    NEXT_CONTACT = 0
    NEXT_MESSAGE = 0
    BLOCK_FIRST_CX = False
    FIRST_CX_STARTED = asyncio.Event()
    RELEASE_FIRST_CX = asyncio.Event()
    AI_CFG.update({
        "bot_engine": "dialogflow_cx",
        "status": "active",
        "buffer_seconds": 0.04,
        "lgpd_policy_version": "test-v1",
    })
    SYS_SETTINGS.clear()
    SYS_SETTINGS["bot_enabled"] = True
    cid = _ensure_contact("5531999999999")
    CONTACTS[str(cid)].update({
        "assigned_to": 9 if assigned else None,
        "bot_completed": completed,
    })
    if consented:
        STATES[str(cid)] = {"step": "cx", "lgpd_consent": True, "lgpd_status": "accepted"}
    return cid


def _ensure_contact(wa_id, name="Paciente"):
    global NEXT_CONTACT
    wa_id = wh.normalize_br_phone(wa_id)
    if wa_id in CONTACT_BY_WA:
        return CONTACT_BY_WA[wa_id]
    NEXT_CONTACT += 1
    cid = NEXT_CONTACT
    CONTACT_BY_WA[wa_id] = cid
    CONTACTS[str(cid)] = {
        "id": cid,
        "wa_id": wa_id,
        "display_name": name,
        "channel_id": CHANNEL["id"],
        "phone_number_id": CHANNEL["phone_number_id"],
        "assigned_to": None,
        "bot_completed": False,
        "qualification": "novo",
    }
    return cid


def _upsert_contact(wa_id, display_name="", **kwargs):
    is_new = wh.normalize_br_phone(wa_id) not in CONTACT_BY_WA
    cid = _ensure_contact(wa_id, display_name)
    contact = CONTACTS[str(cid)]
    # Espelha upsert_wa_contact/_update_existing_wa_contact: o canal do contato
    # e o de CRIACAO e so e gravado quando ainda esta vazio. O duble antigo
    # regravava a cada inbound e apagava a premissa "contato nascido em
    # coexistence", escondendo o defeito do flush do cron (revisao 2026-11-12).
    if kwargs.get("channel_id") is not None and (is_new or not contact.get("channel_id")):
        contact.update({
            "channel_id": kwargs.get("channel_id"),
            "phone_number_id": kwargs.get("phone_number_id"),
        })
    return cid


def _get_contact(contact_id):
    row = CONTACTS.get(str(contact_id))
    return copy.deepcopy(row) if row is not None else None


def _get_message(wa_message_id):
    row = WA_MESSAGES.get(str(wa_message_id))
    return copy.deepcopy(row) if row is not None else None


def _save_message(**kwargs):
    global NEXT_MESSAGE
    wa_mid = str(kwargs.get("wa_message_id") or "")
    if wa_mid and wa_mid in WA_MESSAGES:
        return WA_MESSAGES[wa_mid]["id"]
    NEXT_MESSAGE += 1
    row = dict(kwargs)
    row["id"] = NEXT_MESSAGE
    SAVED.append(copy.deepcopy(row))
    if wa_mid:
        WA_MESSAGES[wa_mid] = copy.deepcopy(row)
    return NEXT_MESSAGE


async def _fake_cx(text):
    global BLOCK_FIRST_CX
    CX_CALLS.append(str(text))
    if BLOCK_FIRST_CX and len(CX_CALLS) == 1:
        FIRST_CX_STARTED.set()
        await RELEASE_FIRST_CX.wait()
    if "HANDOFF" in str(text):
        cid = next(iter(CONTACTS))
        CONTACTS[cid]["bot_completed"] = True
        STATES.pop(cid, None)
        BUFFERS.pop(cid, None)
        return "Transferindo para a recepcao."
    return f"Resposta: {text}"


async def _fake_process_bot(contact_id, text, contact_name=""):
    state = STATES.setdefault(str(contact_id), {})
    # Hidratacao pela prova do contato (espelho de bot_service._process_cx_message).
    contact = CONTACTS.get(str(contact_id)) or {}
    if (state.get("lgpd_consent") is None and contact.get("lgpd_consent") is True
            and not contact.get("lgpd_revoked")
            and contact.get("lgpd_policy_version") == AI_CFG.get("lgpd_policy_version")):
        state["lgpd_consent"] = True
        state["lgpd_status"] = "accepted"
    if state.get("lgpd_consent") is True:
        return await _fake_cx(text)
    normalized = str(text or "").strip().lower()
    if state.get("lgpd_status") == "awaiting" and normalized in ("lgpd_aceitar", "sim"):
        state["lgpd_consent"] = True
        state["lgpd_status"] = "accepted"
        first = str(state.get("user_first_input") or "").strip()
        cx_reply = await _fake_cx(first) if first else ""
        return ("Consentimento aceito.\n\n" + cx_reply).strip()
    state["lgpd_status"] = "awaiting"
    state["user_first_input"] = str(text)
    return {"type": "interactive_buttons", "body": "Podemos continuar?", "buttons": []}


async def _fake_send(wa_id, reply, contact_id, token, phone_id, **kwargs):
    SENT.append({
        "wa_id": wa_id, "reply": copy.deepcopy(reply), "contact_id": contact_id,
        # Por qual numero a resposta saiu (cenario 22).
        "token": token, "phone_id": phone_id,
        "channel_id": kwargs.get("channel_id"),
    })
    return True


def _append_buffer(contact_id, text, timestamp_iso="", at_iso=None, channel_id=None):
    # Espelha _transactional_append_bot_buffer: ts = ordem (Meta), at = idade,
    # ch = canal de chegada (so quando informado).
    key = str(contact_id)
    data = BUFFERS.setdefault(key, {"items": [], "claimed_at": None, "oldest_at": None})
    n = max([int(i.get("n") or 0) for i in data["items"]] or [0]) + 1
    at = at_iso or datetime.now(timezone.utc).isoformat()
    ts = timestamp_iso or at
    item = {"text": str(text), "ts": ts, "n": n, "at": at}
    if channel_id is not None:
        item["ch"] = channel_id
    data["items"].append(item)
    APPEND_CHANNELS.append(channel_id)
    data["token"] = str(uuid.uuid4())
    data["oldest_at"] = data.get("oldest_at") or at
    return {"token": data["token"], "n": n, "oldest_at": data["oldest_at"]}


def _fresh_items(items):
    # Filtro REAL (idade por `at`, ordem por (ts, n)) — sem duble divergente.
    return dbf._filter_and_sort_bot_buffer_items(
        items, datetime.now(timezone.utc), 600,
    )


def _claim_buffer(contact_id, expected_token=None, claim_ttl_seconds=None, **kwargs):
    # Espelha o real: claim vivo = claimed_at OU claim_hb dentro do TTL
    # (TTL derivado quando None); claim vencido pode ser retomado.
    key = str(contact_id)
    data = BUFFERS.get(key)
    if data is None:
        return {"status": "missing", "items": [], "discarded": 0}
    if expected_token is not None and data.get("token") != expected_token:
        return {"status": "superseded", "items": [], "discarded": 0}
    now = datetime.now(timezone.utc)
    ttl = claim_ttl_seconds if claim_ttl_seconds is not None else dbf.bot_buffer_claim_ttl_seconds()
    if data.get("claimed_at") and dbf._bot_buffer_live_claim(data, now, ttl):
        return {"status": "busy", "items": [], "discarded": 0}
    if not data.get("items"):
        BUFFERS.pop(key, None)
        return {"status": "empty", "items": [], "discarded": 0}
    items, discarded = _fresh_items(data["items"])
    claim_id = now.isoformat()
    data.update({
        "items": [], "token": str(uuid.uuid4()), "claimed_at": claim_id,
        "claim_hb": claim_id, "oldest_at": None,
    })
    return {
        "status": "claimed", "items": items, "discarded": discarded,
        "claim_id": claim_id,
    }


def _drain_buffer(contact_id, claim_id, **kwargs):
    data = BUFFERS.get(str(contact_id))
    if data is None:
        return {"status": "missing", "items": [], "discarded": 0}
    if data.get("claimed_at") != claim_id:
        return {"status": "lost_claim", "items": [], "discarded": 0}
    items, discarded = _fresh_items(data.get("items") or [])
    data.update({
        "items": [], "token": str(uuid.uuid4()), "oldest_at": None,
        "claim_hb": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "drained", "items": items, "discarded": discarded}


def _release_claim(contact_id, claim_id):
    key = str(contact_id)
    data = BUFFERS.get(key)
    if data is None or data.get("claimed_at") != claim_id:
        return False
    if data.get("items"):
        data["claimed_at"] = None
        data["claim_hb"] = None
    else:
        BUFFERS.pop(key, None)
    return True


def _flush_stale(cutoff_iso, limit=10, max_claims=1, **kwargs):
    candidates = []
    for key, data in BUFFERS.items():
        oldest = data.get("oldest_at")
        if oldest and oldest < cutoff_iso:
            candidates.append((oldest, key, data.get("token")))
    claimed = []
    for _oldest, key, token in sorted(candidates)[:limit]:
        result = _claim_buffer(key, expected_token=token)
        if result.get("status") == "claimed":
            result["contact_id"] = int(key)
            claimed.append(result)
        if len(claimed) >= max_claims:
            break
    return claimed


async def _fake_download(media_id, media_type, *args, **kwargs):
    return {"path": f"/fake/{media_id}.ogg", "mime_type": "audio/ogg", "content": media_id.encode()}


def _install_patches():
    wh.get_tenant_context = lambda: "varizemed-test"
    wh.get_tenant = lambda tid: {"id": tid, "settings": {"ai": dict(AI_CFG)}}
    wh.document = lambda collection, doc_id: _Doc(collection, doc_id)
    wh.upsert_wa_contact = _upsert_contact
    wh.get_wa_contact = _get_contact
    wh.get_wa_message_by_wa_message_id = _get_message
    wh.save_wa_message = _save_message
    wh.update_wa_message_transcription = lambda *args, **kwargs: None
    wh._resolve_reply_reference = lambda *args, **kwargs: {}
    wh.process_bot_message_async = _fake_process_bot
    wh._send_bot_reply = _fake_send
    wh.append_bot_buffer = _append_buffer
    wh.claim_and_drain_bot_buffer = _claim_buffer
    wh.drain_claimed_bot_buffer = _drain_buffer
    wh.release_bot_buffer_claim = _release_claim
    wh.download_media = _fake_download
    wh.assign_wa_contact = lambda *args, **kwargs: None
    wh.update_wa_contact_qualification = lambda *args, **kwargs: None
    wh.flag_conversation_takeover = lambda *args, **kwargs: None
    wh.is_reception_mode = lambda: True
    wh._buffer_sleep = asyncio.sleep
    wh._buffer_monotonic = time.monotonic
    # lgpd_consent_resolved REAL (importado no webhook); so a config de IA do
    # tenant e substituida para nao tocar Firestore/tenant context.
    bot_service._get_tenant_ai_config = lambda: dict(AI_CFG)
    bot_service.get_system_settings = lambda: dict(SYS_SETTINGS)
    # Registry de canais em memoria (mesma semantica do real: busca pela chave
    # exata; so o flush do cron resolve canal por id neste harness).
    channel_service.get_channel = lambda cid: copy.deepcopy(CHANNELS.get(cid))

    stt = types.ModuleType("transcription_service")
    stt.get_speech_client = lambda: object()
    stt.transcribe_audio_bytes = lambda content, **kwargs: (
        "" if content == b"audio-vazio"
        else content.decode().replace("audio-", "fala-")
    )
    sys.modules["transcription_service"] = stt


def _text(mid, body, wa_id="5531999999999", unix_ts=None):
    return {
        "from": wa_id,
        "id": mid,
        "type": "text",
        "timestamp": str(unix_ts or int(time.time())),
        "text": {"body": body},
    }


def _interactive(mid, button_id, wa_id="5531999999999"):
    return {
        "from": wa_id,
        "id": mid,
        "type": "interactive",
        "timestamp": str(int(time.time())),
        "interactive": {"button_reply": {"id": button_id, "title": button_id}},
    }


def _audio(mid, media_id, wa_id="5531999999999"):
    return {
        "from": wa_id,
        "id": mid,
        "type": "audio",
        "timestamp": str(int(time.time())),
        "audio": {"id": media_id, "mime_type": "audio/ogg"},
    }


def _button(mid, text, wa_id="5531999999999"):
    return {
        "from": wa_id,
        "id": mid,
        "type": "button",
        "timestamp": str(int(time.time())),
        "button": {"text": text, "payload": text},
        "context": {"id": "wamid.template"},
    }


def _reaction(mid, target_mid, wa_id="5531999999999"):
    return {
        "from": wa_id,
        "id": mid,
        "type": "reaction",
        "timestamp": str(int(time.time())),
        "reaction": {"message_id": target_mid, "emoji": "👍"},
    }


async def _deliver(messages):
    await wh._process_messages(
        {
            "contacts": [{"profile": {"name": "Paciente"}}],
            "messages": list(messages),
        },
        None,
        channel=dict(CHANNEL),
    )


async def scenario_separate_payloads():
    title("1. Rajada em payloads separados")
    _reset(consented=True)
    await asyncio.gather(
        _deliver([_text("m1", "Oi")]),
        _deliver([_text("m2", "tudo bem?")]),
        _deliver([_text("m3", "queria marcar consulta")]),
    )
    check(CX_CALLS == ["Oi\ntudo bem?\nqueria marcar consulta"], "3 mensagens -> 1 turno em ordem")
    check(len(SENT) == 1, "uma unica resposta enviada")


async def scenario_same_payload():
    title("2. Rajada no mesmo payload")
    _reset(consented=True)
    await _deliver([
        _text("p1", "primeira"), _text("p2", "segunda"), _text("p3", "terceira"),
    ])
    check(CX_CALLS == ["primeira\nsegunda\nterceira"], "pre-varredura evita sleeps/turnos seriais")
    check(not BUFFERS, "buffer drenado ao final")


async def scenario_lgpd():
    title("3. Aceite LGPD nao entra no buffer")
    _reset(consented=False)
    await _deliver([_text("l1", "quero marcar")])
    accept = asyncio.create_task(_deliver([_interactive("l2", "lgpd_aceitar")]))
    await asyncio.sleep(0.003)
    followup = asyncio.create_task(_deliver([_text("l3", "tem cardiologista?")]))
    await asyncio.gather(accept, followup)
    check(STATES["1"].get("lgpd_consent") is True, "consentimento gravado")
    check(CX_CALLS == ["quero marcar", "tem cardiologista?"], "aceite exato; intencao e follow-up em turnos validos")
    check(all("lgpd_aceitar\n" not in text for text in CX_CALLS), "id interativo nunca foi concatenado")


async def scenario_interactive_order():
    title("4. Interativa pos-consentimento drena antes")
    _reset(consented=True)
    sleeping = asyncio.create_task(_deliver([_text("i1", "texto pendente")]))
    await asyncio.sleep(0.008)
    await _deliver([_interactive("i2", "acao_interativa")])
    await sleeping
    check(CX_CALLS == ["texto pendente", "acao_interativa"], "dois turnos sequenciais na ordem")
    check(len(SENT) == 2, "zero resposta duplicada")


async def scenario_redelivery():
    title("5. Reentrega durante o sleep")
    _reset(consented=True)
    first = asyncio.create_task(_deliver([_text("d1", "mensagem unica")]))
    await asyncio.sleep(0.008)
    await _deliver([_text("d1", "mensagem unica")])
    await first
    check(CX_CALLS == ["mensagem unica"], "was_dup impede re-append e segundo turno")


async def scenario_drain_loop():
    global BLOCK_FIRST_CX
    title("6. Mensagem durante turno e absorvida pelo drain-loop")
    _reset(consented=True)
    BLOCK_FIRST_CX = True
    first = asyncio.create_task(_deliver([_text("c1", "turno um")]))
    await FIRST_CX_STARTED.wait()
    second = asyncio.create_task(_deliver([_text("c2", "turno dois")]))
    await asyncio.sleep(0.01)
    RELEASE_FIRST_CX.set()
    await asyncio.gather(first, second)
    check(CX_CALLS == ["turno um", "turno dois"], "detentor processa item que chegou durante o turno")
    check(not BUFFERS, "nenhum item ficou orfao")


async def scenario_truncation():
    title("7. Truncagem preserva o fim")
    _reset(consented=True)
    await _deliver([
        _text("t1", "A" * 180),
        _text("t2", "B" * 180),
        _text("t3", "FINAL-IMPORTANTE"),
    ])
    check(len(CX_CALLS) == 1 and len(CX_CALLS[0]) == wh.BOT_BUFFER_MAX_CHARS, "texto final limitado a 256")
    check(CX_CALLS[0].endswith("FINAL-IMPORTANTE"), "corte preserva a informacao mais recente")


async def scenario_orphan_flush():
    title("8. Flush de orfao e descarte acima de 10min")
    cid = _reset(consented=True)
    now = datetime.now(timezone.utc)
    six_min_ago = (now - timedelta(minutes=6)).isoformat()
    _append_buffer(cid, "orfao recuperavel", six_min_ago, at_iso=six_min_ago)
    batch = _flush_stale((now - timedelta(minutes=5)).isoformat())[0]
    await wh.process_claimed_bot_buffer(
        cid, batch["claim_id"], batch["items"], "Paciente",
        CONTACTS[str(cid)]["wa_id"], "token", "phone", channel_id=7,
    )
    check(CX_CALLS == ["orfao recuperavel"], "item de 6min recuperado pelo flush")

    eleven_min_ago = (now - timedelta(minutes=11)).isoformat()
    _append_buffer(cid, "velho demais", eleven_min_ago, at_iso=eleven_min_ago)
    old_batch = _flush_stale((now - timedelta(minutes=5)).isoformat())[0]
    before = len(CX_CALLS)
    await wh.process_claimed_bot_buffer(
        cid, old_batch["claim_id"], old_batch["items"], "Paciente",
        CONTACTS[str(cid)]["wa_id"], "token", "phone", channel_id=7,
    )
    check(old_batch["discarded"] == 1 and len(CX_CALLS) == before, "item acima de 10min descartado sem turno")


async def scenario_kill_switch_and_gates():
    title("9/10. Kill-switch e gates")
    _reset(consented=True)
    AI_CFG["buffer_seconds"] = 0
    await _deliver([_text("z1", "um"), _text("z2", "dois"), _text("z3", "tres")])
    check(CX_CALLS == ["um", "dois", "tres"], "buffer zero mantem um turno por mensagem")
    check(not BUFFERS, "buffer zero nao toca na colecao")

    _reset(consented=True)
    AI_CFG["bot_engine"] = ""
    await _deliver([_text("g1", "builtin")])
    check(CX_CALLS == ["builtin"] and not BUFFERS, "engine builtin passa direto, sem buffer")

    _reset(consented=True, assigned=True)
    await _deliver([_text("g2", "com dono")])
    check(not CX_CALLS and not BUFFERS, "contato com dono nao arma buffer")

    _reset(consented=True, completed=True)
    await _deliver([_text("g3", "finalizado")])
    check(not CX_CALLS and not BUFFERS, "bot_completed nao arma buffer")


async def scenario_handoff_cleanup():
    title("11. Handoff limpa a rajada e separa o ciclo novo")
    cid = _reset(consented=True)
    await _deliver([_text("h1", "antes"), _text("h2", "HANDOFF agora")])
    check(CONTACTS[str(cid)]["bot_completed"] is True, "handoff finalizou o bot")
    check(not BUFFERS, "handoff apagou o buffer")
    CONTACTS[str(cid)]["bot_completed"] = False
    STATES[str(cid)] = {"step": "cx", "lgpd_consent": True, "lgpd_status": "accepted"}
    await _deliver([_text("h3", "novo ciclo")])
    check(CX_CALLS[-1] == "novo ciclo", "ciclo novo nao herdou texto anterior")


async def scenario_audio():
    title("12. Transcricao de audio entra no mesmo debounce")
    _reset(consented=True)
    previous = wh.FEATURE_AUDIO_TRANSCRIPTION
    wh.FEATURE_AUDIO_TRANSCRIPTION = True
    try:
        await asyncio.gather(
            _deliver([_audio("a1", "audio-um")]),
            _deliver([_audio("a2", "audio-dois")]),
        )
    finally:
        wh.FEATURE_AUDIO_TRANSCRIPTION = previous
    check(CX_CALLS == ["fala-um\nfala-dois"], "transcricoes agrupadas em um turno")


async def scenario_payload_last_candidate_fails():
    title("13. Ultimo candidato estrutural falha sem deixar texto orfao")
    _reset(consented=True)
    previous = wh.FEATURE_AUDIO_TRANSCRIPTION
    wh.FEATURE_AUDIO_TRANSCRIPTION = True
    try:
        await _deliver([
            _text("e1", "texto valido"),
            _audio("e2", "audio-vazio"),
        ])
    finally:
        wh.FEATURE_AUDIO_TRANSCRIPTION = previous
    check(CX_CALLS == ["texto valido"], "audio sem transcricao devolve o sleep ao ultimo append real")
    check(not BUFFERS, "falha do ultimo candidato nao deixa buffer orfao")

    _reset(consented=True)
    await _deliver([
        _text("e3", "nao duplicar"),
        _text("e3", "nao duplicar"),
    ])
    check(CX_CALLS == ["nao duplicar"], "ultima mid duplicada nao abandona o append anterior")
    check(not BUFFERS, "payload com redelivery termina sem buffer pendente")


async def scenario_delayed_delivery():
    title("15. Entrega atrasada/reprocesso: idade pelo append, nao pelo ts da Meta (F05)")
    _reset(consented=True)
    old_unix = int(time.time()) - 20 * 60
    await _deliver([_text("late1", "quero remarcar", unix_ts=old_unix)])
    check(CX_CALLS == ["quero remarcar"], "ts da Meta de 20min atras ainda recebe turno (nao nasce vencido)")
    check(not BUFFERS, "nada descartado nem orfao")


async def scenario_wall_clock_budget():
    global BLOCK_FIRST_CX
    title("16. Orcamento de parede: sem tempo para outro turno, detentor NAO drena (F02/F12)")
    cid = _reset(consented=True)
    BLOCK_FIRST_CX = True
    # Deadline ja vencido: o 1o turno roda (itens ja sairam do doc), mas o
    # drain-loop nao inicia um 2o; o item que chegou durante o turno fica no doc.
    _append_buffer(cid, "primeiro")
    claim = _claim_buffer(cid)
    holder = asyncio.create_task(wh.process_claimed_bot_buffer(
        cid, claim["claim_id"], claim["items"], "Paciente",
        CONTACTS[str(cid)]["wa_id"], "token", "phone", channel_id=7,
        deadline=wh._buffer_monotonic() - 1,
    ))
    await FIRST_CX_STARTED.wait()
    _append_buffer(cid, "chegou durante o turno")
    RELEASE_FIRST_CX.set()
    await holder
    check(CX_CALLS == ["primeiro"], "sem orcamento -> so o turno ja claimado roda")
    data = BUFFERS.get(str(cid)) or {}
    check([i["text"] for i in data.get("items", [])] == ["chegou durante o turno"]
          and not data.get("claimed_at"),
          "item novo preservado no doc e claim liberado (proximo handler/cron)")

    # Cron: max_drain_loops=1 -> mesmo comportamento mesmo com orcamento sobrando.
    cid = _reset(consented=True)
    BLOCK_FIRST_CX = True
    _append_buffer(cid, "cron um")
    claim = _claim_buffer(cid)
    holder = asyncio.create_task(wh.process_claimed_bot_buffer(
        cid, claim["claim_id"], claim["items"], "Paciente",
        CONTACTS[str(cid)]["wa_id"], "token", "phone", channel_id=7,
        max_drain_loops=1,
    ))
    await FIRST_CX_STARTED.wait()
    _append_buffer(cid, "cron dois")
    RELEASE_FIRST_CX.set()
    await holder
    check(CX_CALLS == ["cron um"], "cron roda 1 turno por contato")
    check([i["text"] for i in (BUFFERS.get(str(cid)) or {}).get("items", [])] == ["cron dois"],
          "item chegado durante o turno do cron fica para o proximo tick/handler")

    # Sleeper sem orcamento nao claima (itens ficam com token intacto).
    cid = _reset(consented=True)
    _append_buffer(cid, "sem orcamento")
    token_before = BUFFERS[str(cid)]["token"]
    result = await wh._claim_buffer_waiting(
        cid, expected_token=token_before, deadline=wh._buffer_monotonic() - 1,
    )
    check(result.get("status") == "no_budget" and BUFFERS[str(cid)]["items"]
          and BUFFERS[str(cid)]["token"] == token_before,
          "sem orcamento -> nao claima, lote fica no doc com token intacto")


async def scenario_interactive_busy_after_wait():
    global BLOCK_FIRST_CX
    title("17. Interativa com claim vivo alem da espera: clique nao se perde (F24)")
    _reset(consented=True)
    BLOCK_FIRST_CX = True
    previous_wait = wh._BUFFER_CLAIM_WAIT_SECONDS
    previous_poll = wh._BUFFER_CLAIM_POLL_SECONDS
    wh._BUFFER_CLAIM_WAIT_SECONDS = 0.05
    wh._BUFFER_CLAIM_POLL_SECONDS = 0.01
    try:
        first = asyncio.create_task(_deliver([_text("b1", "turno longo")]))
        await FIRST_CX_STARTED.wait()
        click = asyncio.create_task(_deliver([_interactive("b2", "acao_interativa")]))
        await asyncio.sleep(0.2)
        check(CX_CALLS == ["turno longo", "acao_interativa"],
              "apos a espera, o clique roda turno direto (degradacao registrada em log)")
        RELEASE_FIRST_CX.set()
        await asyncio.gather(first, click)
    finally:
        wh._BUFFER_CLAIM_WAIT_SECONDS = previous_wait
        wh._BUFFER_CLAIM_POLL_SECONDS = previous_poll
    check(len(SENT) == 2 and not BUFFERS, "duas respostas (uma por turno), nada orfao")


async def scenario_kill_switch_key_absent():
    title("18. Kill-switch com a config REAL do deploy: chave ausente + env 0 (F25)")
    _reset(consented=True)
    AI_CFG.pop("buffer_seconds", None)
    previous = wh.BOT_BUFFER_SECONDS
    wh.BOT_BUFFER_SECONDS = 0.0
    try:
        await _deliver([_text("k1", "um"), _text("k2", "dois")])
    finally:
        wh.BOT_BUFFER_SECONDS = previous
    check(CX_CALLS == ["um", "dois"] and not BUFFERS,
          "sem override e env 0 -> um turno por mensagem, sem tocar no buffer")


async def scenario_new_cycle_hydration():
    title("19. Ciclo novo apos release_lead_to_bot: bot_states sem lgpd_*, prova no contato (canario 2026-09-14)")
    cid = _reset(consented=False)
    STATES[str(cid)] = {"step": "cx", "human_active": False}  # recriado pelo release, sem lgpd_*
    CONTACTS[str(cid)].update({"lgpd_consent": True, "lgpd_policy_version": AI_CFG["lgpd_policy_version"]})
    await asyncio.gather(
        _deliver([_text("n1", "voltei")]),
        _deliver([_text("n2", "quero remarcar")]),
    )
    check(CX_CALLS == ["voltei\nquero remarcar"], "1a mensagem do ciclo novo entra no buffer (prova do contato)")
    check(STATES[str(cid)].get("lgpd_consent") is True and not BUFFERS, "turno hidratou o estado; nada orfao")

    # Prova de OUTRA versao de politica nao vale: pre-consentimento, turno direto (re-pergunta LGPD).
    cid = _reset(consented=False)
    STATES[str(cid)] = {"step": "cx"}
    CONTACTS[str(cid)].update({"lgpd_consent": True, "lgpd_policy_version": "outra-versao"})
    await _deliver([_text("n3", "oi")])
    check(CX_CALLS == [] and not BUFFERS and len(SENT) == 1, "prova de versao antiga: sem buffer, fluxo LGPD refeito")

    # Recusa registrada no estado tem precedencia sobre a prova do contato.
    cid = _reset(consented=False)
    STATES[str(cid)] = {"step": "cx", "lgpd_consent": False, "lgpd_status": "refused"}
    CONTACTS[str(cid)].update({"lgpd_consent": True, "lgpd_policy_version": AI_CFG["lgpd_policy_version"]})
    await _deliver([_text("n4", "oi")])
    check(CX_CALLS == [] and not BUFFERS, "recusa no estado: sem buffer, sem turno CX")


async def scenario_policy_date():
    title("20. P2b: aceite anterior a data da politica LGPD nao arma o debounce (estado True)")
    hoje_br = datetime.now(timezone(timedelta(hours=-3))).date()
    antigo = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recente = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    # Aceite ANTERIOR a politica, estado "aceito": lgpd_consent_resolved real
    # devolve False -> turno direto por mensagem (o turno real reapresenta o aviso).
    cid = _reset()
    SYS_SETTINGS["lgpd_policy_date"] = (hoje_br - timedelta(days=5)).isoformat()
    CONTACTS[str(cid)].update({"lgpd_consent": True, "lgpd_consent_at": antigo})
    await asyncio.gather(
        _deliver([_text("pd1", "um")]),
        _deliver([_text("pd2", "dois")]),
    )
    check(sorted(CX_CALLS) == ["dois", "um"] and not BUFFERS,
          "aceite desatualizado: sem debounce (1 turno direto por mensagem)")

    # Aceite POSTERIOR a politica: debounce normal (1 turno com a rajada).
    cid = _reset()
    SYS_SETTINGS["lgpd_policy_date"] = (hoje_br - timedelta(days=5)).isoformat()
    CONTACTS[str(cid)].update({"lgpd_consent": True, "lgpd_consent_at": recente})
    await asyncio.gather(
        _deliver([_text("pd3", "tres")]),
        _deliver([_text("pd4", "quatro")]),
    )
    check(CX_CALLS == ["tres\nquatro"] and not BUFFERS,
          "aceite em dia com a politica: debounce intacto")

    # Aceite legado sem lgpd_consent_at continua valido.
    cid = _reset()
    SYS_SETTINGS["lgpd_policy_date"] = (hoje_br - timedelta(days=5)).isoformat()
    CONTACTS[str(cid)].update({"lgpd_consent": True})
    await asyncio.gather(
        _deliver([_text("pd5", "cinco")]),
        _deliver([_text("pd6", "seis")]),
    )
    check(CX_CALLS == ["cinco\nseis"] and not BUFFERS,
          "aceite legado sem carimbo: debounce intacto")


async def scenario_reopen_opt_out_reset():
    title("21. D4 (plano v2.2): mensagem nova do cliente desfaz o opt-out do Encerrar")
    cid = _reset()
    CONTACTS[str(cid)].update({"reopen_opt_out": True, "reopen_opt_out_at": "2026-11-01T12:00:00+00:00"})
    await _deliver([_text("oo1", "oi, mudei de ideia")])
    c = CONTACTS[str(cid)]
    check(c.get("reopen_opt_out") is False and bool(c.get("reopen_opt_out_cleared_at"))
          and c.get("reopen_opt_out_at") == "2026-11-01T12:00:00+00:00",
          "texto novo: reopen_opt_out=False + reopen_opt_out_cleared_at (carimbo do Encerrar preservado)")
    check(CX_CALLS == ["oi, mudei de ideia"], "o turno do bot segue normal depois do reset")

    # Reentrega da Meta (mesmo wamid): was_dup protege (cenario 22a).
    CONTACTS[str(cid)].update({"reopen_opt_out": True})
    CONTACTS[str(cid)].pop("reopen_opt_out_cleared_at", None)
    await _deliver([_text("oo1", "oi, mudei de ideia")])
    check(CONTACTS[str(cid)].get("reopen_opt_out") is True
          and "reopen_opt_out_cleared_at" not in CONTACTS[str(cid)],
          "reentrega (was_dup): opt-out intacto")

    # Clique no botao do template nao conta (cenario 13): o curto-circuito do
    # botao vem ANTES do bloco. Handler do botao substituido por no-op.
    saved_btn = wh._handle_reopen_button

    async def _noop_btn(**kwargs):
        return None

    wh._handle_reopen_button = _noop_btn
    try:
        await _deliver([_button("oo2", "Encerrar")])
    finally:
        wh._handle_reopen_button = saved_btn
    check(CONTACTS[str(cid)].get("reopen_opt_out") is True, "clique de botao do template: opt-out intacto")

    # Reacao nao e mensagem nova (mesma regra da recusa comercial).
    await _deliver([_reaction("oo3", "oo1")])
    check(CONTACTS[str(cid)].get("reopen_opt_out") is True, "reacao: opt-out intacto")

    # Achado 1 da revisao de 09/11: mensagem com data REAL anterior ao clique
    # de Encerrar (midia reentregue, download paralelo, retry de pending) nao
    # limpa; mensagem posterior limpa.
    _stamp = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    CONTACTS[str(cid)].update({"reopen_opt_out": True, "reopen_opt_out_at": _stamp})
    CONTACTS[str(cid)].pop("reopen_opt_out_cleared_at", None)
    await _deliver([_text("oo5", "mensagem velha", unix_ts=int(time.time()) - 3600)])
    check(CONTACTS[str(cid)].get("reopen_opt_out") is True, "mensagem anterior ao Encerrar: opt-out intacto")
    await _deliver([_text("oo6", "mensagem nova")])
    check(CONTACTS[str(cid)].get("reopen_opt_out") is False, "mensagem posterior ao Encerrar: opt-out limpo")

    # Contato sem o carimbo: nenhuma escrita extra.
    CONTACTS[str(cid)].pop("reopen_opt_out", None)
    CONTACTS[str(cid)].pop("reopen_opt_out_cleared_at", None)
    await _deliver([_text("oo4", "de novo")])
    check("reopen_opt_out" not in CONTACTS[str(cid)] and "reopen_opt_out_cleared_at" not in CONTACTS[str(cid)],
          "sem opt-out: o bloco nao escreve nada")


def _load_real_cron():
    """Extrai o corpo REAL de main.cron_expire_takeovers por AST.

    Importar o main.py inteiro subiria o app; aqui so a funcao do cron e
    compilada (decorador removido) e roda com os dubles do harness. O defeito
    de 2026-11-12 morava na cola do cron, que o cenario 8 nao exercita. Nome
    global novo no cron aparece como erro no resumo do tenant: acrescente-o ao
    namespace abaixo.
    """
    main_path = os.path.join(ROOT, "main.py")
    with open(main_path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=main_path)
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "cron_expire_takeovers"
    )
    fn.decorator_list = []
    code = compile(ast.Module(body=[fn], type_ignores=[]), main_path, "exec")

    async def _inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def _noop_async(*args, **kwargs):
        return None

    # Imports feitos DENTRO do cron (resolvidos na chamada).
    tenant_service.list_tenants = lambda active_only=True: [{"id": "varizemed-test"}]
    database.is_auto_close_enabled = lambda: False
    namespace = {
        "Request": object,
        "_verify_cron_auth": lambda request: None,
        "run_in_threadpool": _inline,
        "expire_stale_takeovers": lambda hours: [],
        "close_stale_attendances": lambda *args, **kwargs: [],
        "insert_transfer_system_message": lambda *args, **kwargs: None,
        "log_audit": lambda *args, **kwargs: None,
        "_close_daily_and_send_protocol": _noop_async,
        "TAKEOVER_TIMEOUT_HOURS": config.TAKEOVER_TIMEOUT_HOURS,
        "ATTENDANCE_AUTOCLOSE_HOURS": config.ATTENDANCE_AUTOCLOSE_HOURS,
        "RECEPTION_UNATTENDED_RELEASE_DAYS": config.RECEPTION_UNATTENDED_RELEASE_DAYS,
        "CX_DETECT_TIMEOUT_SECONDS": config.CX_DETECT_TIMEOUT_SECONDS,
        "WHATSAPP_TOKEN": "env-token",
        "WHATSAPP_PHONE_NUMBER_ID": "env-phone",
        "get_wa_contact": _get_contact,
        "flush_stale_bot_buffers": _flush_stale,
        "release_bot_buffer_claim": _release_claim,
        "process_claimed_bot_buffer": wh.process_claimed_bot_buffer,        # REAL
        "resolve_orphan_buffer_channel": wh.resolve_orphan_buffer_channel,  # REAL
        "fs_utcnow": lambda: datetime.now(timezone.utc),
        "timedelta": timedelta,
        "logger": logging.getLogger("castro_crm.main"),
        "_monotonic": time.monotonic,
    }
    exec(code, namespace)
    return namespace["cron_expire_takeovers"]


class _WarningCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


async def scenario_cron_reply_channel():
    title("22. Flush do cron: responde pelo canal de CHEGADA e so por canal standard")
    cron = _load_real_cron()
    capture = _WarningCapture()
    cron_logger = logging.getLogger("castro_crm.main")
    cron_logger.addHandler(capture)

    def _orphan(cid, text, channel_id=None, minutes=6.0):
        stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        _append_buffer(cid, text, stamp, at_iso=stamp, channel_id=channel_id)

    async def _tick():
        capture.messages.clear()
        result = await cron(None)
        errors = [t.get("error") for t in result.get("tenants", []) if "error" in t]
        return result, errors

    def _via_standard():
        return (
            len(SENT) == 1
            and SENT[0]["phone_id"] == CHANNEL["phone_number_id"]
            and SENT[0]["token"] == CHANNEL["access_token"]
            and SENT[0]["channel_id"] == CHANNEL["id"]
        )

    def _dropped(reason_fragment):
        return (
            not CX_CALLS and not SENT and not BUFFERS
            and any(
                "descartado sem envio" in message and reason_fragment in message
                for message in capture.messages
            )
        )

    try:
        # 22a. O defeito: contato NASCIDO num numero coexistence e devolvido ao
        # agente escreve no numero da empresa; a request morre na janela.
        cid = _reset(consented=True)
        CONTACTS[str(cid)]["channel_id"] = COEX_CHANNEL["id"]
        _orphan(cid, "escrevi no numero da empresa", channel_id=CHANNEL["id"])
        result, errors = await _tick()
        check(not errors, f"cron real roda sem erro no tenant ({errors or 'ok'})")
        check(result.get("bot_buffers_flushed_total") == 1
              and CX_CALLS == ["escrevi no numero da empresa"],
              "lote orfao recuperado em 1 turno pelo cron real")
        check(_via_standard(),
              "contato nascido em coexistence: resposta sai pelo canal da CHEGADA (standard)")
        check(not any(s["phone_id"] == COEX_CHANNEL["phone_number_id"] for s in SENT),
              "nada sai pelo numero pessoal do operador")
        check(not BUFFERS, "claim liberado depois do turno do cron")

        # 22b. Lote gravado antes do campo `ch` + contato nascido em coexistence:
        # o fallback e o canal de criacao, que nao e standard -> nao envia.
        cid = _reset(consented=True)
        CONTACTS[str(cid)]["channel_id"] = COEX_CHANNEL["id"]
        _orphan(cid, "lote antigo sem canal")
        result, errors = await _tick()
        check(not errors and _dropped("nao e standard (coexistence)"),
              "lote sem canal de chegada + contato nascido em coexistence: descartado, nada enviado")

        # 22c. Item que chegou por coexistence (gate do bot furado): nao envia.
        cid = _reset(consented=True)
        _orphan(cid, "chegou pelo numero pessoal", channel_id=COEX_CHANNEL["id"])
        result, errors = await _tick()
        check(not errors and _dropped("canal 3 (chegada) nao e standard"),
              "item que chegou por coexistence: descartado mesmo com contato nascido em standard")

        # 22d. Compatibilidade: lote antigo sem `ch` + contato nascido em
        # standard continua respondido (comportamento da Val antes do campo).
        cid = _reset(consented=True)
        _orphan(cid, "lote antigo da val")
        result, errors = await _tick()
        check(not errors and CX_CALLS == ["lote antigo da val"] and _via_standard(),
              "lote sem canal de chegada + contato nascido em standard: respondido pelo standard")

        # 22e. Canal standard de OUTRO tenant: nunca.
        cid = _reset(consented=True)
        _orphan(cid, "canal de outro tenant", channel_id=OTHER_TENANT_CHANNEL["id"])
        result, errors = await _tick()
        check(not errors and _dropped("pertence a outro tenant"),
              "canal de outro tenant: descartado, nada enviado")

        # 22f. Canal inexistente/inativo (o registry so tem canais ativos).
        cid = _reset(consented=True)
        _orphan(cid, "canal desativado", channel_id=404)
        result, errors = await _tick()
        check(not errors and _dropped("inexistente ou inativo"),
              "canal inexistente ou inativo: descartado, nada enviado")

        # 22g. Canal sem channel_type: falha FECHADO.
        cid = _reset(consented=True)
        _orphan(cid, "canal sem tipo", channel_id=UNTYPED_CHANNEL["id"])
        result, errors = await _tick()
        check(not errors and _dropped("nao e standard (sem tipo)"),
              "canal sem tipo: descartado (falha fechado)")

        # 22h. Id do canal gravado como texto ainda resolve.
        cid = _reset(consented=True)
        _orphan(cid, "id como texto", channel_id=str(CHANNEL["id"]))
        result, errors = await _tick()
        check(not errors and CX_CALLS == ["id como texto"] and _via_standard(),
              "id do canal gravado como texto: resolvido e respondido pelo standard")

        # 22i. Lote com canais mistos: vale o do item MAIS RECENTE.
        cid = _reset(consented=True)
        _orphan(cid, "mais antigo", channel_id=COEX_CHANNEL["id"], minutes=7.0)
        _orphan(cid, "mais recente", channel_id=CHANNEL["id"], minutes=6.0)
        result, errors = await _tick()
        check(not errors and CX_CALLS == ["mais antigo\nmais recente"] and _via_standard(),
              "canais mistos: responde pelo canal do item mais recente (standard)")
        cid = _reset(consented=True)
        _orphan(cid, "mais antigo", channel_id=CHANNEL["id"], minutes=7.0)
        _orphan(cid, "mais recente", channel_id=COEX_CHANNEL["id"], minutes=6.0)
        result, errors = await _tick()
        check(not errors and _dropped("canal 3 (chegada) nao e standard"),
              "canais mistos com o mais recente em coexistence: descartado")

        # 22j. O aviso do descarte so carrega ids (contato e canal), nunca texto.
        check(all("mais recente" not in m and "mais antigo" not in m for m in capture.messages),
              "aviso do descarte nao carrega o texto do cliente")

        # 22m. Ponta a ponta: o lote orfao e gravado pelo PROPRIO webhook (a
        # request morre na janela) para contato nascido em coexistence; o cron
        # real responde pelo standard da chegada. Cobre webhook -> orfao -> cron
        # sem depender de _append_buffer direto.
        cid = _reset(consented=True)
        CONTACTS[str(cid)].update({
            "channel_id": COEX_CHANNEL["id"],
            "phone_number_id": COEX_CHANNEL["phone_number_id"],
        })
        AI_CFG["buffer_seconds"] = 5.0
        dying = asyncio.create_task(_deliver([_text("e2e1", "escrevi e a request morreu")]))
        for _ in range(400):
            await asyncio.sleep(0.005)
            if (BUFFERS.get(str(cid)) or {}).get("items"):
                break
        dying.cancel()
        try:
            await dying
        except asyncio.CancelledError:
            pass
        AI_CFG["buffer_seconds"] = 0.04
        orphan = BUFFERS.get(str(cid)) or {}
        check(len(orphan.get("items") or []) == 1 and not CX_CALLS and not SENT,
              "request morta na janela deixa 1 item orfao, sem turno")
        check(CONTACTS[str(cid)]["channel_id"] == COEX_CHANNEL["id"],
              "inbound pelo standard nao troca o canal de criacao do contato (duble fiel ao upsert real)")
        six_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        for item in orphan.get("items") or []:
            item["at"] = six_min_ago
        if orphan:
            orphan["oldest_at"] = six_min_ago
        result, errors = await _tick()
        check(not errors and CX_CALLS == ["escrevi e a request morreu"] and _via_standard(),
              "ponta a ponta: lote gravado pelo webhook e respondido pelo cron no canal standard da chegada")
        check(not BUFFERS, "ponta a ponta: nada orfao depois do cron")
    finally:
        cron_logger.removeHandler(capture)

    # 22k. Caminho AO VIVO: o webhook grava no append o canal de CHEGADA (nao o
    # do contato, que continua sendo o coexistence de criacao) e responde pelo
    # canal da mensagem.
    cid = _reset(consented=True)
    CONTACTS[str(cid)].update({
        "channel_id": COEX_CHANNEL["id"],
        "phone_number_id": COEX_CHANNEL["phone_number_id"],
    })
    await _deliver([_text("ch1", "um"), _text("ch2", "dois")])
    check(CONTACTS[str(cid)]["channel_id"] == COEX_CHANNEL["id"]
          and APPEND_CHANNELS == [CHANNEL["id"], CHANNEL["id"]],
          "webhook grava o canal de chegada em cada append do buffer")
    check(CX_CALLS == ["um\ndois"] and _via_standard(),
          "ao vivo: 1 turno, resposta pelo canal da mensagem")

    # 22l. Contrato do resolvedor (sem cron): motivo vazio so quando ha canal.
    channel, reason = wh.resolve_orphan_buffer_channel(
        [{"text": "x", "ts": "2026-01-01T00:00:00+00:00", "n": 1, "ch": CHANNEL["id"]}],
        {"channel_id": COEX_CHANNEL["id"]},
    )
    check(bool(channel) and channel.get("id") == CHANNEL["id"] and reason == "",
          "resolvedor: canal de chegada vence o canal de criacao do contato")
    channel, reason = wh.resolve_orphan_buffer_channel([], {})
    check(channel is None and reason == "lote e contato sem canal",
          "resolvedor: sem canal nenhum devolve motivo e nao envia")
    channel, reason = wh.resolve_orphan_buffer_channel([{"text": "x", "ch": {"id": 7}}], None)
    check(channel is None and "inexistente ou inativo" in reason,
          "resolvedor: id de canal corrompido nao derruba o cron")


def scenario_transaction_contracts():
    title("14. Contratos transacionais da persistencia real")

    class TxRef:
        def __init__(self):
            self.data = None

        def get(self, transaction=None):
            return _Snap(self.data)

    class Tx:
        def set(self, ref, data, merge=False):
            if merge and ref.data is not None:
                ref.data.update(copy.deepcopy(data))
            else:
                ref.data = copy.deepcopy(data)

        def delete(self, ref):
            ref.data = None

    tx = Tx()
    ref = TxRef()
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    first = dbf._transactional_append_bot_buffer.to_wrap(tx, ref, "um", stamp)
    second = dbf._transactional_append_bot_buffer.to_wrap(tx, ref, "dois", stamp)
    check(first["token"] != second["token"], "cada append rotaciona UUID/token")
    check([item["n"] for item in ref.data["items"]] == [1, 2], "n transacional desempata timestamp igual")

    superseded = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
        tx, ref, first["token"], 180, 600,
    )
    check(superseded["status"] == "superseded", "handler antigo nao claima rajada nova")
    claimed = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
        tx, ref, second["token"], 180, 600,
    )
    check(claimed["status"] == "claimed" and [i["text"] for i in claimed["items"]] == ["um", "dois"],
          "claim atomico drena em ordem")

    third = dbf._transactional_append_bot_buffer.to_wrap(tx, ref, "durante", stamp)
    busy = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
        tx, ref, third["token"], 180, 600,
    )
    check(busy["status"] == "busy", "claim vivo nao e roubado")
    ttl = dbf.bot_buffer_claim_ttl_seconds()
    check(ttl == 2 * wh.CX_DETECT_TIMEOUT_SECONDS + 60, "TTL do claim derivado do config (checklist e)")
    real_utcnow = dbf.utcnow
    try:
        # Relogio ja alem do TTL da IDENTIDADE quando o detentor drena: o drain
        # renova o heartbeat com o relogio "atual" e o claim continua VIVO (F01).
        dbf.utcnow = lambda: real_utcnow() + timedelta(seconds=ttl + 30)
        drained = dbf._transactional_drain_claimed_bot_buffer.to_wrap(
            tx, ref, claimed["claim_id"], 600,
        )
        check([i["text"] for i in drained["items"]] == ["durante"], "detentor drena append em voo")
        check(ref.data.get("claim_hb") and ref.data["claim_hb"] != claimed["claim_id"],
              "drain renova o heartbeat do claim (F01)")
        fourth = dbf._transactional_append_bot_buffer.to_wrap(tx, ref, "mais um", stamp)
        still_busy = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
            tx, ref, fourth["token"], ttl, 600,
        )
        check(still_busy["status"] == "busy",
              "identidade vencida + heartbeat fresco = claim vivo, nao e roubado (F01)")
        # Heartbeat tambem vencido -> takeover (cenario 8b); detentor antigo
        # perde drain e release.
        dbf.utcnow = lambda: real_utcnow() + timedelta(seconds=2 * (ttl + 30))
        taken = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
            tx, ref, fourth["token"], ttl, 600,
        )
        check(taken["status"] == "claimed" and [i["text"] for i in taken["items"]] == ["mais um"],
              "claim vencido (identidade + heartbeat) e retomado com os itens pendentes (8b)")
        lost = dbf._transactional_drain_claimed_bot_buffer.to_wrap(
            tx, ref, claimed["claim_id"], 600,
        )
        check(lost["status"] == "lost_claim", "detentor antigo nao drena mais")
        check(dbf._transactional_release_bot_buffer_claim.to_wrap(tx, ref, claimed["claim_id"]) is False,
              "detentor antigo nao libera o claim novo")
        released = dbf._transactional_release_bot_buffer_claim.to_wrap(
            tx, ref, taken["claim_id"],
        )
        check(released is True and ref.data is None, "claim vazio libera removendo o doc")
    finally:
        dbf.utcnow = real_utcnow

    # Canal de chegada no item (`ch`): gravado so quando informado e preservado
    # por claim e drain reais — e o que o flush do cron usa para responder.
    ref_ch = TxRef()
    dbf._transactional_append_bot_buffer.to_wrap(tx, ref_ch, "sem canal", stamp)
    dbf._transactional_append_bot_buffer.to_wrap(tx, ref_ch, "com canal", stamp, 7)
    check("ch" not in ref_ch.data["items"][0] and ref_ch.data["items"][1].get("ch") == 7,
          "append real grava o canal de chegada so quando informado")
    claimed_ch = dbf._transactional_claim_and_drain_bot_buffer.to_wrap(
        tx, ref_ch, None, 180, 600,
    )
    check([i.get("ch") for i in claimed_ch["items"]] == [None, 7],
          "claim real preserva o canal de cada item")
    dbf._transactional_append_bot_buffer.to_wrap(tx, ref_ch, "durante", stamp, 7)
    drained_ch = dbf._transactional_drain_claimed_bot_buffer.to_wrap(
        tx, ref_ch, claimed_ch["claim_id"], 600,
    )
    check([i.get("ch") for i in drained_ch["items"]] == [7],
          "drain real preserva o canal do item")
    # O harness troca wh.append_bot_buffer por um duble: sem esta checagem, uma
    # assinatura real sem channel_id so apareceria em producao (TypeError no
    # debounce -> turno direto, buffer desligado em silencio).
    check("channel_id" in inspect.signature(dbf.append_bot_buffer).parameters
          and "channel_id" in inspect.signature(database.append_bot_buffer).parameters,
          "append_bot_buffer real aceita channel_id (mesmo contrato do duble)")


def scenario_lgpd_by_agent():
    print("\n=== lgpd_by_agent: agente trata a LGPD, buffer arma sem aceite no CRM (Hugo, 2026-10-23) ===")
    check(wh._bot_buffer_consent_resolved(9901, {"id": 9901}) is False,
          "sem a opcao, contato sem aceite no CRM nao arma o buffer")
    AI_CFG["lgpd_by_agent"] = True
    try:
        check(wh._bot_buffer_consent_resolved(9901, {"id": 9901}) is True,
              "com lgpd_by_agent nao ha fase de consentimento no CRM: o buffer arma")
    finally:
        AI_CFG.pop("lgpd_by_agent", None)


async def main():
    _install_patches()
    scenario_lgpd_by_agent()
    await scenario_separate_payloads()
    await scenario_same_payload()
    await scenario_lgpd()
    await scenario_interactive_order()
    await scenario_redelivery()
    await scenario_drain_loop()
    await scenario_truncation()
    await scenario_orphan_flush()
    await scenario_kill_switch_and_gates()
    await scenario_handoff_cleanup()
    await scenario_audio()
    await scenario_payload_last_candidate_fails()
    await scenario_delayed_delivery()
    await scenario_wall_clock_budget()
    await scenario_interactive_busy_after_wait()
    await scenario_kill_switch_key_absent()
    await scenario_new_cycle_hydration()
    await scenario_policy_date()
    await scenario_reopen_opt_out_reset()
    await scenario_cron_reply_channel()
    scenario_transaction_contracts()
    print("\n" + "=" * 72)
    if FAILS:
        print(f"RESULTADO: {len(FAILS)} falha(s) em {CHECKS} checagens")
        for failure in FAILS:
            print(f"  - {failure}")
        return 1
    print(f"RESULTADO: TODAS as {CHECKS} checagens passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
