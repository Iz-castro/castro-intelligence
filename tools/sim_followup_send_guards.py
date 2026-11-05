# -*- coding: utf-8 -*-
"""Exercita produtores reais com HTTP/Firestore substituidos, sem rede/ADC."""
import asyncio
import os
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import HTTPException
import main


def run():
    user = {"id": 7, "firebase_uid": "uid7", "tenant_id": "tenant-sim", "role": "operador"}
    clean = {"id": 12, "wa_id": "5531999999999", "channel_id": 6}
    blocked = dict(clean, commercial_contact_block={"active": True, "version": 1})
    current = deepcopy(clean)
    conv = {"id": "6__5531999999999", "contact_id": 12, "channel_id": 6}
    calls = {"gate": 0, "posts": 0, "writes": [], "audits": []}
    changed_during_listing = False
    reopen_shape = False

    def gate(*args, **kwargs):
        calls["gate"] += 1

    async def templates(channel):
        nonlocal current
        if changed_during_listing:
            current = deepcopy(blocked)
        return {"templates": [{"name": "template_sim", "language": "pt_BR", "components":
            [{"type": "BUTTONS", "buttons": [{"text": "Retomar"}, {"text": "Encerrar"}]}] if reopen_shape else []}]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            calls["posts"] += 1
            # Para apos transporte, sem save/billing ou chamadas externas.
            return SimpleNamespace(status_code=400, json=lambda: {"error": {"message": "simulated", "code": 1}})

    class Ref:
        def __init__(self, name, key):
            self.name, self.key = name, key

        def set(self, data, **kwargs):
            calls["writes"].append((self.name, self.key, data))

    async def no_sleep(seconds):
        pass

    def expect(status, coroutine):
        try:
            asyncio.run(coroutine)
        except HTTPException as exc:
            assert exc.status_code == status, exc
        else:
            raise AssertionError("HTTP esperado")

    class EmptyQuery:
        # Thread-check do _require_contact_access: nenhuma thread do operador
        # (403 genuino; falha de infra na consulta agora responde 503).
        def where(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def stream(self):
            return iter(())

    with patch("firestore_common.collection", lambda name: EmptyQuery()), patch.multiple(main,
        _resolve_send_target=lambda *args: (conv, deepcopy(current), {"id": 6}),
        _check_conv_send_permission=gate,
        ensure_permission=lambda *args: None,
        _resolve_channel_creds_by_id=lambda *args: ("sim-token", "sim-phone", "https://example.invalid"),
        _load_approved_templates_for_channel=templates,
        get_wa_contact=lambda cid: deepcopy(current),
        httpx=SimpleNamespace(AsyncClient=Client),
        fs_document=lambda name, key: Ref(name, key),
        log_audit=lambda *args: calls["audits"].append(args),
        asyncio=SimpleNamespace(sleep=no_sleep),
    ):
        current = deepcopy(blocked)
        expect(409, main.wa_reopen_conversation(conv["id"], current_user=user))
        assert calls["gate"] == calls["posts"] == 0, "Recusa deve impedir gate que silencia Val"
        expect(409, main.wa_send_template(main.WaSendTemplateRequest(contact_id=12), current_user=user))
        assert calls["gate"] == calls["posts"] == 0

        # LGPD (2026-10-26): lead de OUTRA operadora com recusa -> 403 de acesso,
        # nunca o 409 que revelaria a recusa a quem nao ve o lead.
        current = dict(blocked, assigned_to=99, assigned_to_uid="uid99")
        expect(403, main.wa_reopen_conversation(conv["id"], current_user=user))
        expect(403, main.wa_send_template(main.WaSendTemplateRequest(contact_id=12), current_user=user))
        assert calls["gate"] == calls["posts"] == 0, "Sem acesso: nem recusa revelada nem gate que silencia a Val"

        current = deepcopy(clean)
        changed_during_listing = True
        body = main.WaSendTemplateRequest(contact_id=12, template_name="template_sim")
        expect(409, main.wa_send_template(body, current_user=user))
        assert calls["posts"] == 0, "Recusa durante await deve impedir o HTTP"

        changed_during_listing = False
        body = main.WaSendTemplateRequest(contact_id=12, template_name="template_sim", contact_purpose="service")
        expect(502, main.wa_send_template(body, current_user=user))
        assert calls["posts"] == 1, "Servico explicitamente escolhido continua permitido"

        calls["posts"] = 0
        body = main.WaSendTemplateRequest(contact_id=12, template_name=main.REOPEN_TEMPLATE_NAME,
                                          contact_purpose="service")
        expect(409, main.wa_send_template(body, current_user=user))
        assert calls["posts"] == 0, "Nome conhecido de retomada nao aceita override de servico"
        reopen_shape = True
        body = main.WaSendTemplateRequest(contact_id=12, template_name="template_sim", contact_purpose="service")
        expect(409, main.wa_send_template(body, current_user=user))
        assert calls["posts"] == 0, "Formato de retomada conhecido nao aceita override de servico"

        calls["posts"] = calls["gate"] = 0
        asyncio.run(main._run_reopen_batch("tenant-sim", 1, [clean], [], {6: {"id": 6}},
                                          {6: {"name": "template_sim"}}, user["id"]))
        assert calls["posts"] == calls["gate"] == 0, "Worker deve reler recusa sem gate humano"
        assert all(row[0] != "wa_contacts" for row in calls["writes"]), "Bloqueio nao consome tentativa"
        assert calls["writes"][-1][2]["enviados"] == 0
    print("OK: verificacoes dos produtores reais, incluindo override de finalidade, sem rede/ADC")


if __name__ == "__main__":
    run()
