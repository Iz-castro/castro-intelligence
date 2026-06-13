# -*- coding: utf-8 -*-
"""Processa UM pending_webhook_event (por id). Para usar com timeout de SO:
o que pendurar (chamada sincrona sem timeout no handler) e morto de fora.

Uso: python scripts/_drain_one_tmp.py <event_id>
Exit: 0 ok | 2 falha de processamento | 3 evento inexistente/nao-pending
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pending_events import get_pending_event, mark_event_attempt  # noqa: E402
import database_firestore as _db  # noqa: E402
_db.ensure_daily_attendance = lambda *a, **k: None  # replay nao cria protocolo
import webhook  # noqa: E402


def main() -> int:
    event_id = int(sys.argv[1])
    ev = get_pending_event(event_id)
    if not ev or ev.get("status") != "pending":
        return 3
    payload = ev.get("payload") or {}
    try:
        asyncio.run(webhook.process_webhook_payload(payload, ws_notify_callback=None))
        mark_event_attempt(event_id, success=True)
        print(f"ok {event_id}")
        return 0
    except Exception as exc:
        mark_event_attempt(event_id, success=False, error=f"{type(exc).__name__}: {exc}")
        print(f"err {event_id} {type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
