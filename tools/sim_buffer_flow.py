# -*- coding: utf-8 -*-

"""Simulador local do debounce do webhook (sem Firestore/Meta/Dialogflow reais).

Exercita o codigo real de webhook._process_messages e seus caminhos concorrentes.
Os adaptadores de persistencia, CX e envio sao stores deterministas em memoria.
"""

import asyncio
import copy
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


CONTACTS = {}
CONTACT_BY_WA = {}
STATES = {}
BUFFERS = {}
WA_MESSAGES = {}
SAVED = []
CX_CALLS = []
SENT = []
FAILS = []
CHECKS = 0
NEXT_CONTACT = 0
NEXT_MESSAGE = 0

AI_CFG = {
    "bot_engine": "dialogflow_cx",
    "status": "active",
    "buffer_seconds": 0.04,
}

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
    NEXT_CONTACT = 0
    NEXT_MESSAGE = 0
    BLOCK_FIRST_CX = False
    FIRST_CX_STARTED = asyncio.Event()
    RELEASE_FIRST_CX = asyncio.Event()
    AI_CFG.update({
        "bot_engine": "dialogflow_cx",
        "status": "active",
        "buffer_seconds": 0.04,
    })
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
        "assigned_to": None,
        "bot_completed": False,
        "qualification": "novo",
    }
    return cid


def _upsert_contact(wa_id, display_name="", **kwargs):
    cid = _ensure_contact(wa_id, display_name)
    contact = CONTACTS[str(cid)]
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
    SENT.append({"wa_id": wa_id, "reply": copy.deepcopy(reply), "contact_id": contact_id})
    return True


def _append_buffer(contact_id, text, timestamp_iso=""):
    key = str(contact_id)
    data = BUFFERS.setdefault(key, {"items": [], "claimed_at": None, "oldest_at": None})
    n = max([int(i.get("n") or 0) for i in data["items"]] or [0]) + 1
    ts = timestamp_iso or datetime.now(timezone.utc).isoformat()
    data["items"].append({"text": str(text), "ts": ts, "n": n})
    data["token"] = str(uuid.uuid4())
    data["oldest_at"] = min(filter(None, (data.get("oldest_at"), ts)))
    return {"token": data["token"], "n": n, "oldest_at": data["oldest_at"]}


def _fresh_items(items):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    kept = []
    discarded = 0
    for item in items:
        try:
            parsed = datetime.fromisoformat(str(item.get("ts") or "").replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.now(timezone.utc)
        if parsed < cutoff:
            discarded += 1
        else:
            kept.append(copy.deepcopy(item))
    kept.sort(key=lambda item: (item.get("ts") or "", int(item.get("n") or 0)))
    return kept, discarded


def _claim_buffer(contact_id, expected_token=None, **kwargs):
    key = str(contact_id)
    data = BUFFERS.get(key)
    if data is None:
        return {"status": "missing", "items": [], "discarded": 0}
    if expected_token is not None and data.get("token") != expected_token:
        return {"status": "superseded", "items": [], "discarded": 0}
    if data.get("claimed_at"):
        return {"status": "busy", "items": [], "discarded": 0}
    if not data.get("items"):
        BUFFERS.pop(key, None)
        return {"status": "empty", "items": [], "discarded": 0}
    items, discarded = _fresh_items(data["items"])
    claim_id = str(uuid.uuid4())
    data.update({
        "items": [], "token": str(uuid.uuid4()), "claimed_at": claim_id,
        "oldest_at": None,
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
    data.update({"items": [], "token": str(uuid.uuid4()), "oldest_at": None})
    return {"status": "drained", "items": items, "discarded": discarded}


def _release_claim(contact_id, claim_id):
    key = str(contact_id)
    data = BUFFERS.get(key)
    if data is None or data.get("claimed_at") != claim_id:
        return False
    if data.get("items"):
        data["claimed_at"] = None
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
    _append_buffer(cid, "orfao recuperavel", (now - timedelta(minutes=6)).isoformat())
    batch = _flush_stale((now - timedelta(minutes=5)).isoformat())[0]
    await wh.process_claimed_bot_buffer(
        cid, batch["claim_id"], batch["items"], "Paciente",
        CONTACTS[str(cid)]["wa_id"], "token", "phone", channel_id=7,
    )
    check(CX_CALLS == ["orfao recuperavel"], "item de 6min recuperado pelo flush")

    _append_buffer(cid, "velho demais", (now - timedelta(minutes=11)).isoformat())
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
    drained = dbf._transactional_drain_claimed_bot_buffer.to_wrap(
        tx, ref, claimed["claim_id"], 600,
    )
    check([i["text"] for i in drained["items"]] == ["durante"], "detentor drena append em voo")
    released = dbf._transactional_release_bot_buffer_claim.to_wrap(
        tx, ref, claimed["claim_id"],
    )
    check(released is True and ref.data is None, "claim vazio libera removendo o doc")


async def main():
    _install_patches()
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
