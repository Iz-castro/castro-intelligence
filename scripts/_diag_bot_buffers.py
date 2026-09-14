# -*- coding: utf-8 -*-
"""Diag READ-ONLY dos bot_buffers de um tenant (debounce da Val).

NAO escreve nada. LGPD: nunca imprime o texto do paciente — so contact_id,
numero de itens, tamanho total do texto, e idades de oldest_at/claimed_at/
claim_hb. Serve para acompanhar o canario (buffers presos? claim vivo?) e
para conferir que a colecao esta vazia antes de um rollback para revisao
pre-buffer.

Uso (PowerShell) — passar o projeto EXPLICITO (cutover Oregon):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_bot_buffers --tenant varizemed-test
  ./.venv/Scripts/python.exe -m scripts._diag_bot_buffers --tenant varizemed-test --watch 5
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import (  # noqa: E402
    set_tenant_context, reset_tenant_context, collection as fs_collection,
)
import database_firestore as db  # noqa: E402


def _age(iso, now) -> str:
    dt = db._bot_buffer_dt(iso)
    if dt is None:
        return "-"
    return f"{(now - dt).total_seconds():.0f}s"


def snapshot(tenant_id: str) -> list[dict]:
    token = set_tenant_context(tenant_id)
    try:
        now = datetime.now(timezone.utc)
        ttl = db.bot_buffer_claim_ttl_seconds()
        rows = []
        # Colecao transiente e pequena: full scan e aceitavel aqui (diag manual).
        for snap in fs_collection("bot_buffers").stream():
            data = snap.to_dict() or {}
            items = [i for i in (data.get("items") or []) if isinstance(i, dict)]
            has_claim = bool(data.get("claimed_at"))
            live = db._bot_buffer_live_claim(data, now, ttl) if has_claim else False
            rows.append({
                "contact_id": snap.id,
                "items": len(items),
                "chars": sum(len(str(i.get("text") or "")) for i in items),
                "oldest_age": _age(data.get("oldest_at"), now),
                "claim": ("VIVO" if live else "vencido") if has_claim else "-",
                "claim_age": _age(data.get("claimed_at"), now),
                "hb_age": _age(data.get("claim_hb"), now),
            })
        return rows
    finally:
        reset_tenant_context(token)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--watch", type=float, default=0,
                    help="repete a cada N segundos (0 = uma vez)")
    args = ap.parse_args()
    while True:
        rows = snapshot(args.tenant)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
        print(f"[{stamp}] tenant={args.tenant} bot_buffers={len(rows)}")
        for r in rows:
            print(
                f"  contato={r['contact_id']:>8} itens={r['items']:>2} chars={r['chars']:>4} "
                f"oldest={r['oldest_age']:>6} claim={r['claim']:>7} "
                f"claim_age={r['claim_age']:>6} hb_age={r['hb_age']:>6}"
            )
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
