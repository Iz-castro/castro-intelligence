# -*- coding: utf-8 -*-

"""
Simulador LOCAL da recencia no history sync e no eco do coexistence.

Incidente 2026-10-14 (hubloc, Roberta): o _process_history carimbava
last_message_at/last_inbound_at = AGORA no contato e criava/atualizava a
conversa com "agora" a cada fase ou re-entrega do history. Centenas de
conversas antigas ficavam "recentes" (tomavam a janela top-50 do Meus) e a
janela de 24h da Meta ficava falsamente aberta. O eco (outbound do celular)
tambem marcava last_inbound_at.

NAO toca em producao: roda o codigo REAL de webhook.py (_process_history,
_process_smb_message_echoes) e database_firestore.py com o Firestore trocado
por um store em memoria (mesmo padrao do sim_reception_flow.py).

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_history_recency.py

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

import channel_service  # noqa: E402
import database_firestore as dbf  # noqa: E402
import firestore_common  # noqa: E402
import webhook  # noqa: E402

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
# Store em memoria (padrao do sim_reception_flow)
# =========================================================================

STORE = {}
_SEQ = {"n": 1000}


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
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(dict(data))
        else:
            coll[self.doc_id] = dict(data)

    def create(self, data):
        from google.api_core import exceptions as _gexc
        coll = STORE.setdefault(self.coll, {})
        if self.doc_id in coll:
            raise _gexc.AlreadyExists("ja existe")
        coll[self.doc_id] = dict(data)


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
        self._order = (field, str(direction).upper().startswith("DESC"))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def document(self, doc_id=None):
        if doc_id is None:
            _SEQ["n"] += 1
            doc_id = _SEQ["n"]
        return _DocRef(self.coll, doc_id)

    def stream(self):
        def ok(data):
            for f, op, v in self._filters:
                got = data.get(f)
                if op == "==" and got != v:
                    return False
                if op == "in" and got not in v:
                    return False
            return True
        rows = [(k, d) for k, d in list(STORE.get(self.coll, {}).items()) if ok(d)]
        if self._order:
            field, desc = self._order
            rows.sort(key=lambda r: _sort_value(r[1].get(field)), reverse=desc)
        for i, (k, d) in enumerate(rows):
            if self._limit is not None and i >= self._limit:
                break
            yield _QSnap(self.coll, k, d)


def _no_client(*_a, **_k):
    raise AssertionError("sim tentou abrir cliente Firestore REAL")


COEX_CH = {"id": 8, "is_active": True, "channel_type": "coexistence", "owner_user_id": 8,
           "display_phone_number": "+55 31 90000-3303", "label": "Roberta",
           "phone_number_id": "PNID8"}
STD_CH = {"id": 4, "is_active": True, "channel_type": "standard", "owner_user_id": None,
          "display_phone_number": "+55 31 3351-7604", "label": "Fixo", "phone_number_id": "PNID4"}


def patch_store():
    STORE.clear()
    dbf._get_doc = lambda coll, doc_id: (
        dict(STORE.get(coll, {}).get(str(doc_id)))
        if STORE.get(coll, {}).get(str(doc_id)) is not None else None
    )
    dbf.document = lambda coll, doc_id: _DocRef(coll, doc_id)
    dbf.collection = lambda coll: _CollRef(coll)

    def _seq(*_a, **_k):
        _SEQ["n"] += 1
        return _SEQ["n"]
    dbf.next_sequence = _seq
    dbf.get_firestore_client = _no_client
    firestore_common.get_firestore_client = _no_client
    dbf.increment_audit_metrics = lambda *a, **k: None
    dbf.increment_usage_metrics = lambda *a, **k: None
    dbf.ensure_daily_attendance = lambda *a, **k: None
    dbf.get_current_protocol_id = lambda *a, **k: None
    channel_service.get_channel = lambda cid: {8: COEX_CH, 4: STD_CH}.get(int(cid)) if cid is not None else None
    channel_service.refresh_channels = lambda: None
    STORE["users"] = {
        "4": {"id": 4, "display_name": "Danielle", "firebase_uid": "uid4", "department_id": 2, "is_active": 1},
        "8": {"id": 8, "display_name": "Roberta", "firebase_uid": "uid8", "department_id": 3, "is_active": 1},
    }


def ts(v):
    v = dbf._coerce_timestamp(v)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return None


def same(a, b, tol=2):
    a, b = ts(a), ts(b)
    return a is not None and b is not None and abs((a - b).total_seconds()) <= tol


def contact_by_wa(wa):
    for d in STORE.get("wa_contacts", {}).values():
        if d.get("wa_id") == wa:
            return d
    return None


NOW = datetime.now(timezone.utc).replace(microsecond=0)
BUSINESS = "5531900003303"


def unix(dt):
    return str(int(dt.timestamp()))


def hist_payload(customer, msgs, phase=1):
    """msgs: lista de (direction, datetime|str_timestamp, wamid)."""
    out = []
    for direction, when, wamid in msgs:
        raw_ts = unix(when) if isinstance(when, datetime) else when
        m = {"id": wamid, "type": "text", "timestamp": raw_ts, "text": {"body": "x"},
             "history_context": {"status": "read"}}
        if direction == "outbound":
            m["from"], m["to"] = BUSINESS, customer
        else:
            m["from"] = customer
        out.append(m)
    return {
        "metadata": {"display_phone_number": BUSINESS, "phone_number_id": "PNID8"},
        "history": [{"metadata": {"phase": phase, "chunk_order": 1, "progress": 50},
                     "threads": [{"id": customer, "messages": out}]}],
    }


def run(coro):
    return asyncio.run(coro)


# =========================================================================
# Cenarios
# =========================================================================

def cenario_a_contato_novo():
    titulo("A. History de contato NOVO (mensagens de meses atras)")
    patch_store()
    cust = "5531911110001"
    t1, t2, t3 = NOW - timedelta(days=90), NOW - timedelta(days=89), NOW - timedelta(days=60)
    run(webhook._process_history(hist_payload(cust, [
        ("inbound", t1, "w.a1"), ("outbound", t2, "w.a2"), ("inbound", t3, "w.a3")]), channel=COEX_CH))
    c = contact_by_wa(cust)
    check(c is not None, "contato criado")
    check(c.get("created_source") == "history", "created_source='history' (nao 'webhook'/'state_sync')")
    check(same(c.get("last_message_at"), t3), "contato.last_message_at = ultima msg REAL (nao agora)")
    check(same(c.get("last_inbound_at"), t3), "contato.last_inbound_at = ultima inbound REAL")
    check(NOW - ts(c.get("last_inbound_at")) > timedelta(hours=24), "janela de 24h FECHADA (contato antigo)")
    check(c.get("assigned_to") == 8, "contato novo auto-atribuido ao dono do numero coex")
    conv = STORE.get("wa_conversations", {}).get(f"8__{cust}")
    check(conv is not None, "conversa 8__<wa> criada")
    check(conv and conv.get("assigned_to") == 8, "conversa com o DONO DO NUMERO")
    check(conv and same(conv.get("last_message_at"), t3), "conversa.last_message_at = ultima msg REAL (nao agora)")


def cenario_b_contato_existente_de_outro_dono():
    titulo("B. History de contato EXISTENTE (lead da Danielle, ativo ha 1h no fixo)")
    patch_store()
    cust = "5531911110002"
    recent = NOW - timedelta(hours=1)
    STORE["wa_contacts"] = {"500": {
        "id": 500, "wa_id": cust, "display_name": "Cliente", "whatsapp_profile_name": "",
        "assigned_to": 4, "assigned_to_uid": "uid4", "department_id": 2, "channel_id": 4,
        "source_channel_type": "standard", "last_message_at": recent, "last_inbound_at": recent,
        "qualification": "em_atendimento", "is_backup": False,
    }}
    STORE["wa_contact_index"] = {cust: {"contact_id": 500}}
    STORE["wa_conversations"] = {f"4__{cust}": {
        "id": f"4__{cust}", "contact_id": 500, "wa_id": cust, "channel_id": 4,
        "assigned_to": 4, "assigned_to_uid": "uid4", "last_message_at": recent,
        "attendance_status": "aberto",
    }}
    old = NOW - timedelta(days=30)
    run(webhook._process_history(hist_payload(cust, [("inbound", old - timedelta(hours=1), "w.b1"),
                                                     ("outbound", old, "w.b2")]), channel=COEX_CH))
    c = STORE["wa_contacts"]["500"]
    check(same(c.get("last_message_at"), recent), "contato.last_message_at NAO vira 'agora' nem recua")
    check(same(c.get("last_inbound_at"), recent), "contato.last_inbound_at NAO vira 'agora' nem recua")
    check(c.get("assigned_to") == 4, "Dono do Lead preservado (Danielle)")
    conv8 = STORE["wa_conversations"].get(f"8__{cust}")
    check(conv8 is not None, "conversa do history criada no canal coex")
    check(conv8 and conv8.get("assigned_to") == 8,
          "conversa do historico PESSOAL fica com o dono do numero, nao com o dono do lead (LGPD)")
    check(conv8 and same(conv8.get("last_message_at"), old), "conversa.last_message_at = ultima msg REAL")
    conv4 = STORE["wa_conversations"][f"4__{cust}"]
    check(same(conv4.get("last_message_at"), recent), "thread do fixo intocada")
    return cust


def cenario_c_reentrega(cust):
    titulo("C. Re-entrega do MESMO chunk (fase repetida / retry da Meta)")
    c_before = dict(STORE["wa_contacts"]["500"])
    conv_before = dict(STORE["wa_conversations"][f"8__{cust}"])
    old = NOW - timedelta(days=30)
    run(webhook._process_history(hist_payload(cust, [("inbound", old - timedelta(hours=1), "w.b1"),
                                                     ("outbound", old, "w.b2")]), channel=COEX_CH))
    c = STORE["wa_contacts"]["500"]
    conv = STORE["wa_conversations"][f"8__{cust}"]
    check(same(c.get("last_message_at"), c_before.get("last_message_at")), "contato.last_message_at inalterado")
    check(same(c.get("last_inbound_at"), c_before.get("last_inbound_at")), "contato.last_inbound_at inalterado")
    check(same(conv.get("last_message_at"), conv_before.get("last_message_at")), "conversa.last_message_at inalterado")
    n_msgs = sum(1 for m in STORE.get("wa_messages", {}).values() if m.get("conversation_id") == f"8__{cust}")
    check(n_msgs == 2, f"mensagens nao duplicadas ({n_msgs})")


def cenario_d_fase0_recente():
    titulo("D. Fase 0: cliente escreveu ha 2h (janela de 24h REALMENTE aberta)")
    patch_store()
    cust = "5531911110004"
    t = NOW - timedelta(hours=2)
    run(webhook._process_history(hist_payload(cust, [("inbound", t, "w.d1")], phase=0), channel=COEX_CH))
    c = contact_by_wa(cust)
    check(same(c.get("last_inbound_at"), t), "last_inbound_at = inbound real de 2h atras")
    check(NOW - ts(c.get("last_inbound_at")) < timedelta(hours=24), "janela de 24h aberta (correto)")


def cenario_e_timestamp_invalido():
    titulo("E. Timestamp invalido no history nao abre janela")
    patch_store()
    cust = "5531911110005"
    run(webhook._process_history(hist_payload(cust, [("inbound", "nao-e-numero", "w.e1")]), channel=COEX_CH))
    c = contact_by_wa(cust)
    check(c is not None and c.get("last_inbound_at") is None,
          "last_inbound_at continua vazio (sem inbound com data real)")
    check(c is not None and c.get("last_message_at") is None,
          "last_message_at do contato nao vira 'agora' (mensagem sem data real)")


def cenario_e2_sem_data_lead_de_outro_dono():
    titulo("E2. History SEM data valida de lead da Danielle: thread nasce com o dono do numero")
    patch_store()
    cust = "5531911110010"
    recent = NOW - timedelta(hours=3)
    STORE["wa_contacts"] = {"510": {
        "id": 510, "wa_id": cust, "display_name": "Cliente", "whatsapp_profile_name": "",
        "assigned_to": 4, "assigned_to_uid": "uid4", "department_id": 2, "channel_id": 4,
        "source_channel_type": "standard", "last_message_at": recent, "last_inbound_at": recent,
        "qualification": "em_atendimento", "is_backup": False,
    }}
    STORE["wa_contact_index"] = {cust: {"contact_id": 510}}
    run(webhook._process_history(hist_payload(cust, [("inbound", "abc", "w.e2a"),
                                                     ("outbound", "", "w.e2b")]), channel=COEX_CH))
    conv8 = STORE.get("wa_conversations", {}).get(f"8__{cust}")
    check(conv8 is not None and conv8.get("assigned_to") == 8,
          "posse nao depende da data: thread do historico pessoal fica com o dono do numero")
    c = STORE["wa_contacts"]["510"]
    check(same(c.get("last_message_at"), recent), "contato.last_message_at intacto (sem data real nao avanca)")
    check(same(c.get("last_inbound_at"), recent), "contato.last_inbound_at intacto")


def cenario_i_thread_fechada_nao_reabre():
    titulo("I. Fase posterior (mensagens mais ANTIGAS) nao reabre thread fechada")
    patch_store()
    cust = "5531911110011"
    last_live = NOW - timedelta(days=2)
    STORE["wa_contacts"] = {"520": {
        "id": 520, "wa_id": cust, "display_name": "Cliente", "whatsapp_profile_name": "",
        "assigned_to": 8, "assigned_to_uid": "uid8", "channel_id": 8, "source_channel_type": "coexistence",
        "last_message_at": last_live, "last_inbound_at": last_live, "is_backup": False,
    }}
    STORE["wa_contact_index"] = {cust: {"contact_id": 520}}
    STORE["wa_conversations"] = {f"8__{cust}": {
        "id": f"8__{cust}", "contact_id": 520, "wa_id": cust, "channel_id": 8,
        "assigned_to": 8, "assigned_to_uid": "uid8", "last_message_at": last_live,
        "attendance_status": "fechado_manual",
    }}
    older = NOW - timedelta(days=120)
    run(webhook._process_history(hist_payload(cust, [("inbound", older, "w.i1"),
                                                     ("outbound", older + timedelta(minutes=5), "w.i2")],
                                              phase=2), channel=COEX_CH))
    conv = STORE["wa_conversations"][f"8__{cust}"]
    check(conv.get("attendance_status") == "fechado_manual", "atendimento fechado continua fechado")
    check(same(conv.get("last_message_at"), last_live), "recencia da thread intacta (msgs mais antigas)")
    c = STORE["wa_contacts"]["520"]
    check(same(c.get("last_inbound_at"), last_live), "last_inbound_at nao recua")


def cenario_j_idempotencia_por_bloco():
    titulo("J. Idempotencia por BLOCO (reentrega da Meta nao reprocessa)")
    patch_store()
    cust = "5531911110009"
    t1 = NOW - timedelta(days=30)
    payload = hist_payload(cust, [("inbound", t1, "w.j1"), ("outbound", t1 + timedelta(minutes=1), "w.j2"),
                                  ("inbound", t1 + timedelta(minutes=2), "w.j3")])
    saves = {"n": 0}
    real_save = webhook.save_wa_message

    def counting_save(*a, **k):
        saves["n"] += 1
        return real_save(*a, **k)
    webhook.save_wa_message = counting_save
    try:
        run(webhook._process_history(payload, channel=COEX_CH))
        check(saves["n"] == 3, "1a entrega grava as 3 mensagens")
        marks = STORE.get("history_chunks", {})
        check(len(marks) == 1, "1 marcador de bloco criado")
        key, mark = next(iter(marks.items()))
        check(key.startswith("PNID8__c8__1__1__"), f"chave = numero__canal__fase__ordem__hash ({key})")
        check(mark.get("status") == "done" and mark.get("msgs") == 3 and mark.get("attempts") == 1,
              "marcador done com msgs=3 e attempts=1")
        check(mark.get("lease_until") is None, "lease liberado no done")

        # Reentrega identica (envelope pode mudar; ids das msgs nao): nada grava.
        saves["n"] = 0
        payload2 = hist_payload(cust, [("inbound", t1, "w.j1"), ("outbound", t1 + timedelta(minutes=1), "w.j2"),
                                       ("inbound", t1 + timedelta(minutes=2), "w.j3")])
        payload2["metadata"]["display_phone_number"] = "+" + BUSINESS  # envelope diferente
        run(webhook._process_history(payload2, channel=COEX_CH))
        check(saves["n"] == 0, "reentrega do mesmo bloco: 0 gravacoes (200 em ms)")
        check(len(STORE.get("history_chunks", {})) == 1, "reentrega nao cria marcador novo")

        # Outra copia em processamento com lease valido: NAO e sucesso — levanta
        # HistoryChunkBusy (o HTTP responde 503 e a Meta reentrega). Um 200 aqui
        # perderia o bloco se o dono do lease morresse (revisao 2026-10-28).
        STORE["history_chunks"][key].update({"status": "processing", "lease_until": NOW + timedelta(minutes=10)})
        try:
            run(webhook._process_history(payload, channel=COEX_CH))
            check(False, "copia concorrente deveria levantar HistoryChunkBusy")
        except webhook.HistoryChunkBusy:
            check(True, "copia concorrente com lease valido: HistoryChunkBusy (503, Meta reentrega)")
        check(saves["n"] == 0 and STORE["history_chunks"][key]["status"] == "processing",
              "copia concorrente: 0 gravacoes e marcador intacto")

        # Lease vencido (request anterior morreu): reprocessa e fecha.
        STORE["history_chunks"][key].update({"status": "processing", "lease_until": NOW - timedelta(minutes=1)})
        run(webhook._process_history(payload, channel=COEX_CH))
        check(saves["n"] == 3 and STORE["history_chunks"][key]["status"] == "done"
              and STORE["history_chunks"][key]["attempts"] == 2,
              "lease vencido: reprocessa (idempotente) e marca done com attempts=2")

        # Falha no meio: marcador 'failed' (lease liberado) e excecao propaga.
        saves["n"] = 0
        STORE["history_chunks"].clear()
        real_threads = webhook._process_history_threads

        async def boom(*a, **k):
            raise RuntimeError("firestore caiu")
        webhook._process_history_threads = boom
        try:
            try:
                run(webhook._process_history(payload, channel=COEX_CH))
                check(False, "excecao deveria propagar (fila de pendentes reentrega)")
            except RuntimeError:
                check(True, "excecao propaga para o enqueue de pendentes")
        finally:
            webhook._process_history_threads = real_threads
        mark = next(iter(STORE["history_chunks"].values()))
        check(mark.get("status") == "failed" and mark.get("lease_until") is None, "falha -> marcador failed sem lease")
        run(webhook._process_history(payload, channel=COEX_CH))
        check(saves["n"] == 3 and next(iter(STORE["history_chunks"].values())).get("status") == "done",
              "apos falha, a reentrega reprocessa e fecha done")

        # Bloco DIFERENTE (mais uma mensagem) = chave nova: processa normalmente.
        saves["n"] = 0
        payload3 = hist_payload(cust, [("inbound", t1, "w.j1"), ("inbound", t1 + timedelta(minutes=5), "w.j4")])
        run(webhook._process_history(payload3, channel=COEX_CH))
        check(saves["n"] == 2 and len(STORE["history_chunks"]) == 2, "bloco com ids diferentes = chave nova, processa")
        check(len(STORE.get("wa_messages", {})) == 4, "mensagens no banco: 4 distintas (w.j1 nao duplicou)")

        # Midia inline que falha no download: 'done' congelaria a midia perdida.
        # Marcador 'failed' + excecao (payload vai para a fila de pendentes).
        real_dl = webhook.download_media

        async def no_media(*a, **k):
            return None
        webhook.download_media = no_media
        try:
            payload4 = hist_payload(cust, [("inbound", t1 + timedelta(minutes=9), "w.j9")])
            payload4["history"][0]["threads"][0]["messages"][0].update(
                {"type": "image", "image": {"id": "MID9", "mime_type": "image/jpeg"}})
            try:
                run(webhook._process_history(payload4, channel=COEX_CH))
                check(False, "midia sem download deveria levantar HistoryChunkIncomplete")
            except webhook.HistoryChunkIncomplete:
                check(True, "midia sem download: HistoryChunkIncomplete (fila de pendentes)")
            marks4 = [m for m in STORE["history_chunks"].values() if m.get("media_failures")]
            check(len(marks4) == 1 and marks4[0]["status"] == "failed",
                  "marcador 'failed' com media_failures=1 (reentrega re-baixa so o que faltou)")
        finally:
            webhook.download_media = real_dl
    finally:
        webhook.save_wa_message = real_save


def cenario_f_eco():
    titulo("F. Eco do celular (outbound) nao abre a janela de 24h")
    patch_store()
    cust = "5531911110006"
    three_days = NOW - timedelta(days=3)
    STORE["wa_contacts"] = {"600": {
        "id": 600, "wa_id": cust, "display_name": "Cliente", "whatsapp_profile_name": "",
        "assigned_to": 8, "assigned_to_uid": "uid8", "channel_id": 8, "source_channel_type": "coexistence",
        "last_message_at": three_days, "last_inbound_at": three_days, "qualification": "em_atendimento",
        "is_backup": False,
    }}
    STORE["wa_contact_index"] = {cust: {"contact_id": 600}}
    echo = {"message_echoes": [{"from": BUSINESS, "to": cust, "id": "w.f1", "type": "text",
                                "timestamp": unix(NOW), "text": {"body": "oi"}}],
            "metadata": {"display_phone_number": BUSINESS, "phone_number_id": "PNID8"}}
    run(webhook._process_smb_message_echoes(echo, channel=COEX_CH))
    c = STORE["wa_contacts"]["600"]
    check(ts(c.get("last_message_at")) >= NOW - timedelta(seconds=5), "eco ao vivo SOBE a recencia")
    check(same(c.get("last_inbound_at"), three_days), "eco NAO mexe em last_inbound_at")
    try:
        import main as _main  # gate real da janela
        try:
            _main._check_24h_window(c)
            check(False, "janela deveria seguir FECHADA apos o eco")
        except Exception as exc:
            check(getattr(exc, "status_code", None) == 403, "_check_24h_window: 403 (precisa template)")
    except Exception as exc:  # main indisponivel no ambiente: segue so com o campo
        print(f"      (main nao importado: {exc})")

    cust2 = "5531911110007"
    echo2 = {"message_echoes": [{"from": BUSINESS, "to": cust2, "id": "w.f2", "type": "text",
                                 "timestamp": unix(NOW), "text": {"body": "oi"}}],
             "metadata": {"display_phone_number": BUSINESS, "phone_number_id": "PNID8"}}
    run(webhook._process_smb_message_echoes(echo2, channel=COEX_CH))
    c2 = contact_by_wa(cust2)
    check(c2 is not None and c2.get("last_inbound_at") is None, "contato NOVO por eco: last_inbound_at vazio")
    check(c2 is not None and c2.get("created_source") == "webhook", "contato novo por eco segue 'webhook'")


def cenario_g_inbound_ao_vivo():
    titulo("G. Inbound AO VIVO continua abrindo a janela (sem regressao)")
    patch_store()
    cust = "5531911110008"
    STORE["wa_contacts"] = {"700": {
        "id": 700, "wa_id": cust, "display_name": "Cliente", "whatsapp_profile_name": "",
        "assigned_to": 8, "assigned_to_uid": "uid8", "channel_id": 8, "source_channel_type": "coexistence",
        "last_message_at": NOW - timedelta(days=3), "last_inbound_at": NOW - timedelta(days=3),
        "is_backup": False,
    }}
    STORE["wa_contact_index"] = {cust: {"contact_id": 700}}
    dbf.upsert_wa_contact(cust, "Cliente", channel_id=8, phone_number_id="PNID8",
                          source_channel_type="coexistence", auto_assign_user_id=8,
                          skip_conversation_upsert=True)
    c = STORE["wa_contacts"]["700"]
    check(ts(c.get("last_inbound_at")) >= NOW - timedelta(seconds=5), "inbound ao vivo: last_inbound_at = agora")
    check(ts(c.get("last_message_at")) >= NOW - timedelta(seconds=5), "inbound ao vivo: last_message_at = agora")
    cust_new = "5531911110009"
    dbf.upsert_wa_contact(cust_new, "Novo", channel_id=8, skip_conversation_upsert=True)
    cn = contact_by_wa(cust_new)
    check(cn is not None and cn.get("created_source") == "webhook", "contato novo ao vivo: created_source='webhook'")
    check(cn is not None and ts(cn.get("last_inbound_at")) is not None, "contato novo ao vivo: last_inbound_at setado")


def cenario_h_bump_monotonico():
    titulo("H. bump_contact_last_inbound_at e monotonico")
    patch_store()
    STORE["wa_contacts"] = {"900": {"id": 900, "last_inbound_at": NOW - timedelta(hours=5)}}
    check(dbf.bump_contact_last_inbound_at(900, NOW - timedelta(days=1)) is False, "data mais antiga: nao grava")
    check(same(STORE["wa_contacts"]["900"]["last_inbound_at"], NOW - timedelta(hours=5)), "valor preservado")
    check(dbf.bump_contact_last_inbound_at(900, NOW - timedelta(hours=1)) is True, "data mais nova: grava")
    check(same(STORE["wa_contacts"]["900"]["last_inbound_at"], NOW - timedelta(hours=1)), "valor avancado")
    check(dbf.bump_contact_last_inbound_at(999, NOW) is False, "contato inexistente: nao cria doc")
    check("999" not in STORE["wa_contacts"], "nenhum doc fantasma")


def main():
    cenario_a_contato_novo()
    cust = cenario_b_contato_existente_de_outro_dono()
    cenario_c_reentrega(cust)
    cenario_d_fase0_recente()
    cenario_e_timestamp_invalido()
    cenario_e2_sem_data_lead_de_outro_dono()
    cenario_i_thread_fechada_nao_reabre()
    cenario_f_eco()
    cenario_g_inbound_ao_vivo()
    cenario_h_bump_monotonico()
    cenario_j_idempotencia_por_bloco()
    print("\n" + "=" * 70)
    if FAILS:
        print(f"FALHOU: {len(FAILS)} de {CHECKS} asserts")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print(f"OK: {CHECKS} asserts")
    sys.exit(0)


if __name__ == "__main__":
    main()
