# -*- coding: utf-8 -*-
"""Backfill da denormalizacao de canal nas wa_conversations (Fase 2).

A UI (faixa de contexto, modo snapshot) le os campos de canal direto do doc
da conversation: channel_phone_number, channel_label, channel_type,
channel_active. O upsert_wa_conversation passou a gravar isso, mas as
conversations antigas (pre-denorm) e as de canal inativo/removido ficaram
sem. Este script preenche, casando channel_id -> canal flat.

Usa o canal mesmo quando INATIVO (le a colecao flat inteira, nao o cache
so-ativos) -> recupera o ultimo numero/label conhecido das threads orfas
(ex.: conv do canal 4 do 7195-7758). channel_active reflete o is_active
ATUAL do canal. Se o canal sumiu de vez, marca channel_active=False e
preserva o numero/label que ja estiver no doc.

dry-run por default. Use --confirm pra gravar. Idempotente.
Ver docs/PLANO_LEAD_ATENDIMENTO_E_REGRAS.md (Fase 2).

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"   # staging: castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.backfill_conversation_channel_denorm --tenant-id hubloc
  ./.venv/Scripts/python.exe -m scripts.backfill_conversation_channel_denorm --tenant-id hubloc --confirm
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")


def _norm_id(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill denorm de canal nas wa_conversations.")
    ap.add_argument("--tenant-id", default="hubloc")
    ap.add_argument("--confirm", action="store_true", help="Grava de fato. Sem isso, dry-run.")
    args = ap.parse_args()
    tid = args.tenant_id

    c = get_firestore_client()

    # 1. Mapa channel_id -> dados do canal (TODOS, inclui inativos).
    channels: dict = {}
    for d in c.collection(f"{PREFIX}_channels").stream():
        x = d.to_dict() or {}
        cid = _norm_id(x.get("id") if x.get("id") is not None else d.id)
        channels[cid] = {
            "channel_phone_number": x.get("display_phone_number", "") or "",
            "channel_label": x.get("label", "") or "",
            "channel_type": x.get("channel_type", "") or "",
            "channel_active": bool(x.get("is_active")),
        }

    convs = c.collection(f"{PREFIX}_tenants").document(tid).collection("wa_conversations")

    total = 0
    no_channel_id = 0
    channel_missing = 0
    to_update = 0
    updated = 0
    for snap in convs.stream():
        x = snap.to_dict() or {}
        total += 1
        cid = x.get("channel_id")
        if cid is None:
            no_channel_id += 1
            continue
        ch = channels.get(_norm_id(cid))
        if ch is None:
            # Canal sumiu: so garante channel_active=False, preserva o resto.
            channel_missing += 1
            if x.get("channel_active") is not False:
                to_update += 1
                if args.confirm:
                    snap.reference.set({"channel_active": False}, merge=True)
                    updated += 1
            continue
        # Campos desejados vs atuais (idempotente — so grava o que mudou).
        desired = {
            "channel_phone_number": ch["channel_phone_number"],
            "channel_label": ch["channel_label"],
            "channel_type": ch["channel_type"],
            "channel_active": ch["channel_active"],
        }
        diff = {k: v for k, v in desired.items() if x.get(k) != v}
        if diff:
            to_update += 1
            if args.confirm:
                snap.reference.set(diff, merge=True)
                updated += 1

    print(f"=== Backfill denorm canal | tenant={tid} prefix={PREFIX} ===")
    print(f"  modo:                {'CONFIRMED (grava)' if args.confirm else 'DRY-RUN (nada gravado)'}")
    print(f"  canais carregados:   {len(channels)}")
    print(f"  conversations:       {total}")
    print(f"  sem channel_id:      {no_channel_id}")
    print(f"  canal inexistente:   {channel_missing}   (marca channel_active=False)")
    if args.confirm:
        print(f"  atualizadas:         {updated}")
    else:
        print(f"  a atualizar:         {to_update}")
        print("  [DRY-RUN] Nada gravado. Use --confirm para aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
