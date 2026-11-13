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
        return deepcopy(conv), deepcopy(contacts[conv["contact_id"]]), {"id": conv["channel_id"], "owner_user_id": 7}

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
            get_media_asset=lambda p: {"content": b"stored-file", "mime_type": "image/jpeg", "filename": "stored.jpg"} if p else None,
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

    queries = []
    class ContextQuery:
        def where(self, *a): queries.append(("where", a)); return self
        def order_by(self, *a, **k): return self
        def start_at(self, cursor): queries.append(("start", cursor)); return self
        def end_at(self, cursor): queries.append(("end", cursor)); return self
        def limit(self, n): queries.append(("limit", n)); return self
        def limit_to_last(self, n): queries.append(("last", n)); return self
        def stream(self):
            return [SimpleNamespace(id="3", exists=True, to_dict=lambda: dict(original, id=3, timestamp_wa=now - timedelta(seconds=1))),
                    SimpleNamespace(id="4", exists=True, to_dict=lambda: dict(original, id=4, contact_id=99))]
        def get(self):
            return [SimpleNamespace(id="2", exists=True, to_dict=lambda: dict(original, id=2, timestamp_wa=now + timedelta(seconds=1)))]
    with patch.object(db, "collection", lambda *a: ContextQuery()):
        context = db.get_wa_message_context(original)
        assert [row["id"] for row in context] == [3, 1, 2]
        assert ("where", ("conversation_id", "==", "thread-11")) in queries
        assert ("limit", 11) in queries and ("last", 11) in queries
    print("OK: encaminhamento, origem/destino, gates reais, midia, falhas, pin/TTL, contexto limitado e persistencia; sem rede/ADC")


if __name__ == "__main__":
    run()
