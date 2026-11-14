# -*- coding: utf-8 -*-
"""Encaminhar/fixar com handlers e gates reais, sem rede/ADC."""
import asyncio
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
import main
import database_firestore as db


def run():
    user = {"id": 7, "firebase_uid": "uid7", "role": "operador", "display_name": "Sim", "tenant_id": "sim"}
    now = datetime.now(timezone.utc)
    contacts = {
        i: {"id": i, "wa_id": f"55000000000{i}", "assigned_to": 7, "assigned_to_uid": "uid7",
            "last_inbound_at": now, "bot_completed": True, "channel_id": i}
        for i in (11, 12)
    }
    threads = {
        f"thread-{i}": {"id": f"thread-{i}", "contact_id": i, "channel_id": i, "assigned_to": 7,
                        "assigned_to_uid": "uid7", "source_channel_type": "coexistence"}
        for i in (11, 12)
    }
    original = {"id": 1, "contact_id": 11, "conversation_id": "thread-11", "direction": "inbound",
                "msg_type": "text", "content": "Texto original", "visibility": "all", "timestamp_wa": now,
                "created_at": now, "reply_to_message_id": 44, "reply_to_preview": "Contexto privado"}
    messages = {1: deepcopy(original)}
    writes, posts, uploads, media_sends, pin_writes = [], [], [], [], []
    failure = {"http": False, "upload": False, "media": False}
    channel_owner = {11: 7, 12: 7}
    stored_media = {"content": b"stored-file", "mime_type": "image/jpeg", "filename": "stored.jpg", "error": None}

    media_reads = []

    def media_stream(path):
        media_reads.append(path)
        if stored_media["error"]:
            raise stored_media["error"]
        if not path:
            return None
        content = stored_media["content"]
        return {"size": stored_media.get("size", len(content)), "mime_type": stored_media["mime_type"],
                "filename": stored_media["filename"],
                "iter_content": lambda start, end: iter([content[start:end + 1]])}

    class EmptyQuery:
        def where(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def stream(self): return iter(())

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, **kwargs):
            posts.append((url, kwargs))
            return SimpleNamespace(status_code=502 if failure["http"] else 200,
                                   json=lambda: {"error": {"message": "sim"}} if failure["http"] else {"messages": [{"id": "fresh-wamid"}]})

    def resolve(cid, contact_id):
        conv = threads[cid or f"thread-{contact_id}"]
        return deepcopy(conv), deepcopy(contacts[conv["contact_id"]]), {"id": conv["channel_id"], "owner_user_id": channel_owner[conv["channel_id"]]}

    async def upload(content, mime, filename, **kwargs):
        uploads.append((content, mime, filename, kwargs))
        return None if failure["upload"] else "new-destination-media-id"

    async def send_media(*args, **kwargs):
        media_sends.append((args, kwargs))
        return {"error": "sim"} if failure["media"] else {"wa_message_id": "fresh-media-wamid"}

    def expect(status, fn):
        before = len(writes)
        try:
            result = fn()
            if asyncio.iscoroutine(result): asyncio.run(result)
        except HTTPException as exc:
            assert exc.status_code == status, (exc.status_code, exc.detail)
            assert len(writes) == before
        else: raise AssertionError(f"HTTP {status} esperado")

    def forward():
        return main.wa_send(main.WaSendRequest(conversation_id="thread-12", forward_message_id=1, content="Ignorar"), user)

    with patch("rbac._read_perfil_doc", lambda *a: None), \
         patch("firestore_common.collection", lambda *a: EmptyQuery()), \
         patch.multiple(main,
            get_wa_contact=lambda i: deepcopy(contacts.get(i)),
            get_wa_message_by_id=lambda i: deepcopy(messages.get(i)),
            get_wa_conversation_by_id=lambda i: deepcopy(threads.get(i)),
            _resolve_send_target=Mock(side_effect=resolve),
            _resolve_channel_creds_by_id=lambda i: (f"token-{i}", f"phone-{i}", "https://example.invalid"),
            save_wa_message=lambda **k: writes.append(k) or len(writes),
            _maybe_credit_assume_counter=lambda *a: None,
            log_audit=lambda *a: None,
            fs_document=lambda *a: SimpleNamespace(update=lambda d: pin_writes.append((a, d))),
            get_media_stream=media_stream,
            upload_media_to_whatsapp=upload, send_media_message=send_media), \
         patch.object(main.httpx, "AsyncClient", Client):
        asyncio.run(forward())
        saved = writes[-1]
        assert saved["content"] == original["content"] and saved["is_forwarded"] is True
        assert saved["conversation_id"] == "thread-12" and saved["channel_id"] == 12
        assert not saved.get("reply_to_message_id") and messages[1] == original
        assert posts[-1][0].endswith("/phone-12/messages")
        assert "context" not in posts[-1][1]["json"]

        # Origem e destino alheios sao negados antes do resolve/upsert/envio.
        for contact_id in (11, 12):
            contacts[contact_id].update(assigned_to=99, assigned_to_uid="uid99")
            count, resolved = len(posts), main._resolve_send_target.call_count
            expect(403, forward)
            assert len(posts) == count and main._resolve_send_target.call_count == resolved
            contacts[contact_id].update(assigned_to=7, assigned_to_uid="uid7")
        contacts[11].update(assigned_to=99, assigned_to_uid="uid99")
        with patch.object(main, "_require_contact_access", lambda *a: None):
            # Contato acessivel por OUTRA thread nao libera a origem alheia.
            threads["thread-11"].update(assigned_to=99, assigned_to_uid="uid99")
            expect(403, forward)
        contacts[11].update(assigned_to=7, assigned_to_uid="uid7")
        threads["thread-11"].update(assigned_to=7, assigned_to_uid="uid7")

        # Origem ESTRITA: ser Dono do Lead nao libera a thread coex de outra
        # vendedora com o mesmo cliente (antes um atalho pulava a checagem).
        threads["thread-11"].update(assigned_to=99, assigned_to_uid="uid99")
        expect(403, forward)
        expect(403, lambda: main.wa_pin_message(1, main.WaPinRequest(), user))
        expect(403, lambda: main.wa_unpin_message("thread-11", user))
        expect(403, lambda: main.wa_message_context(1, user))
        threads["thread-11"].update(assigned_to=7, assigned_to_uid="uid7")

        # Destino: nunca pelo WhatsApp pessoal (coex) de outra pessoa, mesmo
        # com o lead sendo meu (Opcao A do envio normal nao vale aqui).
        channel_owner[12] = 99
        count = len(posts)
        expect(403, forward)
        assert len(posts) == count, "Nada sai pelo coex alheio"
        channel_owner[12] = 7
        # Canal fora do cache: refresh antes de decidir, pelo tipo do CANAL (nao
        # pelo source_channel_type do contato); canal que nao resolve = 409.
        conv_no_cache = {"id": "thread-12", "channel_id": 12, "channel_type": "coexistence", "source_channel_type": "standard"}
        refreshed = []
        with patch("channel_service.refresh_channels", lambda: refreshed.append(1)), \
             patch("channel_service.get_channel", lambda cid: {"id": cid, "channel_type": "coexistence", "owner_user_id": 99}):
            try:
                main._require_forward_destination_channel(conv_no_cache, None, user)
            except HTTPException as exc:
                assert exc.status_code == 403 and refreshed == [1], (exc.status_code, refreshed)
            else:
                raise AssertionError("Coex de colega fora do cache liberado")
        with patch("channel_service.refresh_channels", lambda: None), patch("channel_service.get_channel", lambda cid: None):
            try:
                main._require_forward_destination_channel(conv_no_cache, None, user)
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("Canal inexistente deveria falhar fechado")
        # Sem conversation_id (so contact_id) o resolve faria upsert no canal de criacao.
        expect(400, lambda: main.wa_send(main.WaSendRequest(contact_id=12, forward_message_id=1), user))

        # Janela e gate de envio permanecem reais, inclusive coex/Recepcao.
        contacts[12]["last_inbound_at"] = now - timedelta(hours=25)
        expect(403, forward)
        contacts[12]["last_inbound_at"] = now
        threads["thread-12"].update(assigned_to=99, assigned_to_uid="uid99")
        contacts[12].update(assigned_to=None, assigned_to_uid="")
        expect(403, forward)
        threads["thread-12"].update(assigned_to=None, assigned_to_uid="")
        with patch("database.is_reception_mode", lambda: True):
            expect(403, forward)  # Coex nao entra na Recepcao.
            threads["thread-12"]["source_channel_type"] = "standard"
            asyncio.run(forward())
        with patch("database.is_reception_mode", lambda: False): expect(403, forward)
        contacts[12].update(assigned_to=7, assigned_to_uid="uid7")
        threads["thread-12"].update(assigned_to=7, assigned_to_uid="uid7", source_channel_type="coexistence")
        with patch.object(main, "ensure_permission", side_effect=HTTPException(403, "RBAC")): expect(403, forward)

        for kind in ("image", "audio", "video", "gif", "document", "sticker"):
            messages[1].update(msg_type=kind, media_path="/media/images/stored.jpg", media_id="old-other-number-id", filename="original.jpg")
            asyncio.run(forward())
            assert uploads[-1][0] == b"stored-file" and uploads[-1][3] == {"token": "token-12", "phone_id": "phone-12"}
            assert media_sends[-1][0][1] == "new-destination-media-id"
            assert writes[-1]["media_path"] == messages[1]["media_path"] and writes[-1]["is_forwarded"]
            assert writes[-1]["msg_type"] == ("video" if kind == "gif" else kind)
        # Nota de voz recebida: tipo puro e extensao coerente no novo upload.
        messages[1].update(msg_type="audio", media_mime="audio/ogg; codecs=opus", filename="20261113_abc.bin")
        asyncio.run(forward())
        assert uploads[-1][1] == "audio/ogg" and uploads[-1][2] == "20261113_abc.ogg", uploads[-1][1:3]
        # Documento chega ao paciente com o nome original.
        messages[1].update(msg_type="document", media_mime="application/pdf", filename="Pedido_exame.pdf")
        asyncio.run(forward())
        assert media_sends[-1][1].get("filename") == "Pedido_exame.pdf", media_sends[-1][1]
        messages[1].update(media_mime="", filename="original.jpg")
        # Storage fora do ar = 503 (antes 404 'nao encontrado'); acima de 16 MB = 413 sem baixar.
        stored_media["error"] = main.MediaStorageUnavailable()
        expect(503, forward)
        stored_media["error"] = None
        stored_media["size"] = 16 * 1024 * 1024 + 1
        expect(413, forward)
        stored_media.pop("size")
        # Janela vencida ou gate de envio recusando: a midia (ate 16 MB) nem e lida.
        reads = len(media_reads)
        contacts[12]["last_inbound_at"] = now - timedelta(hours=25)
        expect(403, forward)
        contacts[12]["last_inbound_at"] = now
        with patch.object(main, "ensure_permission", side_effect=HTTPException(403, "RBAC")):
            expect(403, forward)
        assert len(media_reads) == reads, "Midia lida antes de recusa sem efeito"
        # Recepcao: midia de origem ausente responde 404 SEM silenciar a Val do
        # destino (antes o gate de envio rodava antes da leitura da midia).
        marks = []
        threads["thread-12"].update(assigned_to=None, assigned_to_uid="", source_channel_type="standard")
        contacts[12].update(assigned_to=None, assigned_to_uid="", bot_completed=False)
        with patch("database.is_reception_mode", lambda: True), \
             patch("bot_service.mark_human_active", lambda cid: marks.append(("human", cid))), \
             patch("database.mark_contact_bot_done", lambda cid: marks.append(("done", cid))):
            messages[1]["media_path"] = ""
            expect(404, forward)
            assert marks == [], marks
            messages[1]["media_path"] = "/media/images/stored.jpg"
            asyncio.run(forward())
            assert ("human", 12) in marks and ("done", 12) in marks, marks
        contacts[12].update(assigned_to=7, assigned_to_uid="uid7", bot_completed=True)
        threads["thread-12"].update(assigned_to=7, assigned_to_uid="uid7", source_channel_type="coexistence")
        messages[1]["media_path"] = ""
        expect(404, forward)
        messages[1]["media_path"] = "/media/images/stored.jpg"
        for key in ("upload", "media"):
            failure[key] = True
            expect(502, forward)
            failure[key] = False

        messages[1].update(msg_type="location", latitude=-20.0, longitude=-40.0)
        asyncio.run(forward())
        assert posts[-1][1]["json"]["location"]["latitude"] == -20.0 and writes[-1]["longitude"] == -40.0
        # Localizacao sem nome nao manda name "" (campo opcional na Cloud API).
        messages[1]["content"] = ""
        asyncio.run(forward())
        assert "name" not in posts[-1][1]["json"]["location"]
        # Co-pilotagem: texto assinado, localizacao nao (a assinatura viraria o nome do local).
        with patch.object(main, "_check_conv_send_permission", lambda *a, **k: "intervention"):
            messages[1]["content"] = "Clinica Centro"
            asyncio.run(forward())
            assert posts[-1][1]["json"]["location"]["name"] == "Clinica Centro"
            messages[1] = deepcopy(original)
            asyncio.run(forward())
            assert posts[-1][1]["json"]["text"]["body"] == "[Supervisao - Sim]: Texto original"
        messages[1] = deepcopy(original)
        # Template (rotulo interno com dados de quem recebeu), toque em botao e
        # clique de avaliacao nao sao encaminhados; fixar template continua ok.
        for updates in ({"msg_type": "template", "content": "[template: lembrete] Maria | 14/11"},
                        {"interactive_reply": True, "content": "lgpd_aceitar"},
                        {"content": "lgpd_recusar"},  # toque gravado antes da marca interactive_reply
                        {"is_rating_message": True, "content": "[Avaliação do atendimento: 5]"}):
            messages[1].update(updates)
            expect(400, forward)
            messages[1] = deepcopy(original)
        messages[1].update(msg_type="template", content="[template: lembrete] Maria | 14/11")
        assert main.wa_pin_message(1, main.WaPinRequest(), user)["pinned_message"]["message_id"] == 1
        messages[1] = deepcopy(original)
        for updates in ({"direction": "internal"}, {"direction": "system"}, {"visibility": "admin_only"}, {"msg_type": "unknown"}):
            messages[1].update(updates)
            expect(400, forward)
            messages[1] = deepcopy(original)
        messages[1]["is_backup"] = True
        expect(403, forward)
        messages[1] = deepcopy(original)
        failure["http"] = True
        expect(502, forward)
        failure["http"] = False
        expect(400, lambda: main.wa_send(main.WaSendRequest(conversation_id="thread-12"), user))

        # Fixar e desfixar nao enviam mensagem e nao alteram bot/takeover.
        before = len(posts)
        for days in (1, 7, 30):
            result = main.wa_pin_message(1, main.WaPinRequest(duration_days=days), user)
            pin = result["pinned_message"]
            expiry = datetime.fromisoformat(pin["expires_at"])
            assert abs((expiry - datetime.now(timezone.utc)).total_seconds() - days * 86400) < 2
            assert pin["message_id"] == 1 and pin["preview"] == "Texto original"
            assert pin_writes[-1][0] == ("wa_conversations", "thread-11")
        main.wa_unpin_message("thread-11", user)
        assert pin_writes[-1][1] == {"pinned_message": None} and len(posts) == before
        threads["thread-11"]["is_backup"] = True
        expect(403, lambda: main.wa_unpin_message("thread-11", user))
        threads["thread-11"]["is_backup"] = False
        contacts[11].update(assigned_to=99, assigned_to_uid="uid99")
        expect(403, lambda: main.wa_pin_message(1, main.WaPinRequest(), user))
        expect(403, lambda: main.wa_unpin_message("thread-11", user))
        contacts[11].update(assigned_to=7, assigned_to_uid="uid7")
        for days in (0, 2, 31):
            try: main.WaPinRequest(duration_days=days)
            except ValidationError: pass
            else: raise AssertionError("Prazo invalido aceito")
        with patch("database.get_wa_message_context", lambda msg: [original, dict(original, id=2, visibility="admin_only"), dict(original, id=3, is_backup=True)]):
            assert [m["id"] for m in main.wa_message_context(1, user)["messages"]] == [1]

        # O caminho normal de upload continua usando o mesmo emissor.
        with patch.object(main, "get_current_user", lambda r: user), \
             patch.object(main, "save_upload_media", AsyncMock(return_value={"path": "/media/images/new.jpg", "msg_type": "image"})):
            file = UploadFile(BytesIO(b"new-file"), filename="new.jpg", headers={"content-type": "image/jpeg"})
            asyncio.run(main.wa_send_media(None, "thread-12", None, "Legenda", file, None, "", ""))
            assert writes[-1]["content"] == "Legenda" and writes[-1]["is_forwarded"] is False
            assert uploads[-1][0] == b"new-file"
    # Persistencia real: selo no insert e preservado quando chega eco coex.
    stored = []
    with patch.multiple(db, _get_first_by_field=lambda *a: None, next_sequence=lambda *a: 100,
                        document=lambda *a: SimpleNamespace(set=lambda data, **k: stored.append(data)),
                        get_current_protocol_id=lambda *a: None,
                        increment_audit_metrics=lambda **k: None, increment_usage_metrics=lambda **k: None):
        db.save_wa_message("", 12, "outbound", "text", content="sim", conversation_id="thread-12", contact={}, is_forwarded=True)
        assert stored[-1]["is_forwarded"] is True
        with patch.object(db, "_get_first_by_field", lambda *a: {"id": 100, "is_forwarded": True}):
            db.save_wa_message("wamid", 12, "outbound", "text")
            assert stored[-1]["is_forwarded"] is True
        # Toque em botao interativo recebe a marca que o encaminhamento recusa.
        db.save_wa_message("", 12, "outbound", "text", content="lgpd_aceitar", conversation_id="thread-12", contact={}, interactive_reply=True)
        assert next(d for d in reversed(stored) if d.get("content") == "lgpd_aceitar").get("interactive_reply") is True
        db.save_wa_message("", 12, "outbound", "text", content="texto comum", conversation_id="thread-12", contact={})
        assert "interactive_reply" not in next(d for d in reversed(stored) if d.get("content") == "texto comum")

    # Contexto da fixada: Firestore falso com ordem, cursor e limite de verdade
    # (o duble antigo devolvia listas fixas e escondia o bug do limit_to_last,
    # que na google-cloud-firestore 2.19 trazia as 11 PRIMEIRAS da conversa).
    base = now.replace(microsecond=0)
    dataset = [dict(original, id=i, conversation_id="thread-11", timestamp_wa=base + timedelta(minutes=i)) for i in range(1, 41)]
    dataset.append(dict(original, id=99, contact_id=99, conversation_id="thread-11", timestamp_wa=base + timedelta(minutes=25, seconds=30)))
    context_queries = []

    class ContextQuery:
        def __init__(self):
            self.filters, self.direction, self.cursor, self.n = [], "ASCENDING", None, None
            context_queries.append(self)
        def where(self, field, op, value): self.filters.append((field, op, value)); return self
        def order_by(self, field, direction="ASCENDING"): self.direction = direction; return self
        def start_at(self, cursor): self.cursor = cursor["timestamp_wa"]; return self
        def end_at(self, cursor): raise AssertionError("end_at nao e usado")
        def limit(self, n): self.n = n; return self
        def limit_to_last(self, n): raise AssertionError("limit_to_last inverte os Order in place (firestore 2.19)")
        def stream(self):
            desc = self.direction == "DESCENDING"
            rows = sorted((r for r in dataset if all(r.get(f) == v for f, _, v in self.filters)),
                          key=lambda r: r["timestamp_wa"], reverse=desc)
            if self.cursor is not None:
                rows = [r for r in rows if ((r["timestamp_wa"] <= self.cursor) if desc else (r["timestamp_wa"] >= self.cursor))]
            return [SimpleNamespace(id=str(r["id"]), exists=True, to_dict=lambda r=r: dict(r)) for r in rows[: self.n]]

    pinned = next(r for r in dataset if r["id"] == 30)
    with patch.object(db, "collection", lambda *a: ContextQuery()):
        ids = [row["id"] for row in db.get_wa_message_context(pinned)]
    # 10 antes (uma vaga ocupada pela linha de outro contato, filtrada) + marco + 10 depois.
    assert ids == list(range(21, 41)), ids
    assert {q.direction for q in context_queries} == {"DESCENDING", "ASCENDING"} and len(context_queries) == 2
    assert all(q.filters == [("conversation_id", "==", "thread-11")] and q.n == 11 for q in context_queries)
    assert db._context_sort_key({"id": 1, "timestamp_wa": "2026-01-01T00:00:00+00:00"}) < \
        db._context_sort_key({"id": 2, "timestamp_wa": datetime(2026, 1, 2, tzinfo=timezone.utc)})
    assert db._context_sort_key({"id": 3}) == (0.0, "3")

    # Status: update devolve se achou a mensagem; 'failed' que chega antes do
    # save do envio e reaplicado depois (sent/delivered nao: regrediria status).
    with patch.object(db, "_get_first_by_field", lambda *a: None):
        assert db.update_wa_message_status("wamid.missing", "failed") is False
    with patch.multiple(db, _get_first_by_field=lambda *a: {"id": 5},
                        document=lambda *a: SimpleNamespace(set=lambda *x, **k: None)):
        assert db.update_wa_message_status("wamid.ok", "delivered") is True
    import webhook
    status_calls = []

    def fake_status(msg_id, state, ts=""):
        status_calls.append((msg_id, state))
        return len(status_calls) >= 3

    async def statuses():
        # Retry DENTRO do request (antes do 200): fora dele o Cloud Run estrangula a CPU.
        with patch.object(webhook, "update_wa_message_status", fake_status), \
             patch.object(webhook, "_FAILED_STATUS_RETRY_DELAYS", (0.01, 0.01)):
            missed = webhook._process_statuses({"statuses": [
                {"id": "wamid.sent", "status": "sent", "timestamp": "1700000000"},
                {"id": "wamid.fail", "status": "failed", "timestamp": "1700000000", "errors": [{"code": 131026}]},
            ]})
            assert [m for m, _ in missed] == ["wamid.fail"], missed
            await webhook._retry_missed_failed_statuses(missed)
    asyncio.run(statuses())
    assert status_calls == [("wamid.sent", "sent"), ("wamid.fail", "failed"), ("wamid.fail", "failed")], status_calls
    print("OK: encaminhamento, origem estrita/destino sem coex alheio, gates reais, midia (404/503/413, voz, documento), "
          "template/botao/avaliacao recusados, efeitos so depois da midia, localizacao, pin/TTL, contexto real, "
          "persistencia e status failed reaplicado; sem rede/ADC")


if __name__ == "__main__":
    run()
