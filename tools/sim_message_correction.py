# -*- coding: utf-8 -*-
r"""Simulador offline da correcao de mensagens.

Extrai por AST o endpoint e seus helpers reais, sem importar o app/startup.
HTTP, credenciais, RBAC e persistencia usam fakes em memoria; nao usa ADC,
Firestore ou WhatsApp. Rodar: .venv\Scripts\python.exe tools\sim_message_correction.py
"""

import ast
import logging
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError, field_validator


ROOT = Path(__file__).resolve().parents[1]
OWN_SEND = "enviar_mensagem_propria_thread"
ANY_SEND = "enviar_mensagem_qualquer_thread"


def load_definitions(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    assert {node.name for node in nodes} == names, "Definicao real ausente"
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)


class MessageCorrectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {"id": 7, "display_name": "Ana", "permissions": {OWN_SEND}}
        self.supervisor = {"id": 8, "display_name": "Beatriz Lima", "permissions": {ANY_SEND}}
        self.contact = {
            "id": 50, "wa_id": "5531988887777", "channel_id": 2,
            "assigned_to": 7, "bot_completed": True,
            "last_inbound_at": datetime.now(timezone.utc),
        }
        self.conv_id = "1__5531988887777"
        self.conversations = {
            self.conv_id: {"id": self.conv_id, "contact_id": 50, "channel_id": 1, "assigned_to": 7},
        }
        self.original = {
            "id": 10, "contact_id": 50, "conversation_id": self.conv_id,
            "channel_id": 1, "direction": "outbound", "msg_type": "text",
            "sender_user_id": 7, "operator_id": 7, "sent_by_name": "Ana Original",
            "content": "Texto original", "wa_message_id": "wamid_original",
        }
        self.posts, self.saved, self.marked, self.credential_channels = [], [], [], []
        self.users = {7: {"display_name": "Ana Cadastro"}}
        self.http_status = 200
        self.reception = False
        self.channels = {1: {"id": 1, "owner_user_id": 7}, 2: {"id": 2}}

        database = ModuleType("database")
        database.get_wa_contact = self.get_contact
        database.get_wa_conversation_by_id = self.conversations.get
        database.upsert_wa_conversation = self.upsert_conversation
        channel_service = ModuleType("channel_service")
        channel_service.get_channel = self.channels.get
        module_patch = patch.dict(sys.modules, {"database": database, "channel_service": channel_service})
        module_patch.start()
        self.addCleanup(module_patch.stop)

        case = self

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, json, headers):
                case.posts.append({"url": url, "payload": json})
                return SimpleNamespace(
                    status_code=case.http_status,
                    json=lambda: {"messages": [{"id": "wamid_correction"}], "error": {"message": "Envio recusado"}},
                )

        self.ns = {
            "BaseModel": BaseModel, "field_validator": field_validator,
            "Depends": lambda dependency: None, "get_current_user": None,
            "HTTPException": HTTPException, "MAX_MESSAGE_LENGTH": 4000,
            "datetime": datetime, "timezone": timezone, "_24H": timedelta(hours=24),
            "httpx": SimpleNamespace(AsyncClient=FakeClient),
            "get_wa_message_by_id": lambda mid: dict(self.original) if self.original else None,
            "get_wa_contact": self.get_contact,
            "get_user_by_id": lambda uid: self.users.get(int(uid)),
            "has_permission": lambda user, perm: perm in user["permissions"],
            "ensure_permission": self.ensure_permission,
            "_reception_send_allowed": lambda *args: self.reception,
            "clear_conversation_takeover": lambda *args: None,
            "logger": logging.getLogger("sim_message_correction"),
            "_resolve_channel_creds_by_id": self.resolve_credentials,
            "save_wa_message": self.save_message,
            "mark_message_corrected": self.mark_corrected,
            "log_audit": lambda *args: None,
        }
        load_definitions("database_firestore.py", {"normalize_br_phone"}, self.ns)
        load_definitions("main.py", {
            "CorrectMessageRequest", "correct_message", "_check_conv_send_permission",
            "_resolve_send_target", "_check_24h_window", "_fallback_reply_sender", "_wa_target",
        }, self.ns)

    def get_contact(self, contact_id):
        return self.contact if self.contact and contact_id == self.contact["id"] else None

    def upsert_conversation(self, **kwargs):
        conv_id = f"{kwargs['channel_id']}__{kwargs['wa_id']}"
        self.conversations.setdefault(conv_id, {
            "id": conv_id, "contact_id": kwargs["contact_id"],
            "channel_id": kwargs["channel_id"], "assigned_to": 7,
        })
        return conv_id

    def ensure_permission(self, user, permission):
        if permission not in user["permissions"]:
            raise HTTPException(status_code=403, detail="Sem permissao")

    def resolve_credentials(self, channel_id):
        self.credential_channels.append(channel_id)
        return "fake-token", str(channel_id), "https://mock.invalid"

    def save_message(self, **kwargs):
        self.saved.append(kwargs)
        return 20

    def mark_corrected(self, original_id, new_id):
        self.marked.append((original_id, new_id))
        self.original["is_corrected"] = True

    async def correct(self, user=None):
        body = self.ns["CorrectMessageRequest"](message_id=10, new_content=" Texto corrigido ")
        return await self.ns["correct_message"](body, user or self.user)

    async def reject(self, status, user=None):
        with self.assertRaises(HTTPException) as raised:
            await self.correct(user)
        self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.saved, [])
        self.assertEqual(self.marked, [])

    async def test_author_sends_reply_and_marks_original(self):
        response = await self.correct()
        self.assertEqual(response["new_message_id"], 20)
        self.assertEqual(self.posts[0]["payload"]["context"], {"message_id": "wamid_original"})
        self.assertEqual(self.saved[0]["content"], "Texto corrigido")
        self.assertEqual(self.saved[0]["reply_to_sender_name"], "Ana Original")
        self.assertEqual(self.saved[0]["sender_user_id"], 7)
        self.assertEqual(self.marked, [(10, 20)])

    async def test_another_author_rejected_even_for_current_lead_owner(self):
        self.original.update(sender_user_id=9, operator_id=9)
        await self.reject(403)

    async def test_sender_id_is_authoritative_over_legacy_operator(self):
        self.original["sender_user_id"] = 9
        await self.reject(403)

    async def test_legacy_author_with_string_id_can_correct(self):
        self.original.update(sender_user_id=None, operator_id="7", sent_by_name="")
        await self.correct()
        self.assertEqual(self.saved[0]["reply_to_sender_name"], "Ana Cadastro")

    async def test_sender_id_used_for_original_author_lookup(self):
        self.original.update(operator_id=9, sent_by_name="")
        await self.correct()
        self.assertEqual(self.saved[0]["reply_to_sender_name"], "Ana Cadastro")

    async def test_manager_correction_has_signature_and_original_author(self):
        await self.correct(self.supervisor)
        expected = "[Supervisao - Beatriz]: Texto corrigido"
        self.assertEqual(self.posts[0]["payload"]["text"]["body"], expected)
        self.assertEqual(self.saved[0]["content"], expected)
        self.assertEqual(self.saved[0]["reply_to_sender_name"], "Ana Original")
        self.assertEqual(self.saved[0]["sender_user_id"], 8)

    async def test_missing_original_author_has_safe_fallback_for_manager(self):
        self.original.update(sender_user_id=None, operator_id=None, sent_by_name="")
        await self.correct(self.supervisor)
        self.assertEqual(self.saved[0]["reply_to_sender_name"], "Equipe")

    async def test_author_without_send_permission_rejected(self):
        self.user["permissions"].clear()
        await self.reject(403)

    async def test_author_cannot_send_into_another_operators_thread(self):
        self.contact["assigned_to"] = 9
        self.conversations[self.conv_id]["assigned_to"] = 9
        await self.reject(403)

    async def test_author_can_correct_in_own_takeover_thread(self):
        self.contact["assigned_to"] = 9
        self.conversations[self.conv_id]["takeover_status"] = "active"
        await self.correct()
        self.assertEqual(len(self.posts), 1)

    async def test_reception_operator_cannot_correct_another_author(self):
        self.reception = True
        self.contact["assigned_to"] = None
        self.conversations[self.conv_id]["assigned_to"] = None
        self.original.update(sender_user_id=9, operator_id=9)
        await self.reject(403)

    async def test_reception_author_can_correct(self):
        self.reception = True
        self.contact["assigned_to"] = None
        self.conversations[self.conv_id]["assigned_to"] = None
        await self.correct()
        self.assertEqual(len(self.posts), 1)

    async def test_legacy_message_uses_historical_channel_and_normalized_phone(self):
        self.original["conversation_id"] = None
        self.contact["wa_id"] = "553188887777"
        await self.correct()
        self.assertEqual(self.credential_channels, [1])
        self.assertEqual(self.saved[0]["conversation_id"], self.conv_id)
        self.assertEqual(self.saved[0]["channel_id"], 1)

    async def test_missing_historical_thread_does_not_fall_back_to_current_channel(self):
        self.original["conversation_id"] = None
        self.conversations.clear()
        await self.reject(404)
        self.assertEqual(self.credential_channels, [])

    async def test_removed_channel_does_not_use_global_credentials(self):
        self.channels.pop(1)
        await self.reject(503)
        self.assertEqual(self.credential_channels, [])

    async def test_inactive_channel_does_not_use_global_credentials(self):
        self.channels[1]["is_active"] = False
        await self.reject(503)
        self.assertEqual(self.credential_channels, [])

    async def test_legacy_without_channel_retains_contact_resolution(self):
        self.original.update(conversation_id=None, channel_id=None)
        await self.correct()
        self.assertEqual(self.credential_channels, [2])

    async def test_expired_whatsapp_window_rejected(self):
        self.contact["last_inbound_at"] -= timedelta(hours=25)
        await self.reject(403)

    async def test_already_corrected_rejected(self):
        self.original["is_corrected"] = True
        await self.reject(400)

    async def test_non_text_message_rejected(self):
        self.original["msg_type"] = "audio"
        await self.reject(400)

    async def test_inbound_message_rejected(self):
        self.original["direction"] = "inbound"
        await self.reject(400)

    async def test_missing_message_rejected(self):
        self.original = None
        await self.reject(404)

    async def test_synthetic_message_id_is_not_sent_as_whatsapp_context(self):
        self.original["wa_message_id"] = "local_10"
        await self.correct()
        self.assertNotIn("context", self.posts[0]["payload"])

    async def test_failed_delivery_does_not_mark_or_save_correction(self):
        self.http_status = 400
        with self.assertRaises(HTTPException) as raised:
            await self.correct()
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(self.saved, [])
        self.assertEqual(self.marked, [])

    def test_request_validation(self):
        for content in ("   ", "x" * 4001):
            with self.subTest(length=len(content)), self.assertRaises(ValidationError):
                self.ns["CorrectMessageRequest"](message_id=10, new_content=content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
