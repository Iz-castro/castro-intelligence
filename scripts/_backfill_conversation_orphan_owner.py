# -*- coding: utf-8 -*-
"""Backfill: conversas ORFAS de dono herdam o Dono do Lead (contact.assigned_to).

Alvo: wa_conversations com assigned_to_uid vazio/None E contato com dono.
Preserva: takeover ativo/pendente, threads ja atribuidas (idempotente),
NUNCA toca lead_owner_user_id/takeover_*. Reversivel via --undo.

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"        # prod
  ./.venv/Scripts/python.exe -m scripts._backfill_conversation_orphan_owner            # dry-run
  ./.venv/Scripts/python.exe -m scripts._backfill_conversation_orphan_owner --apply
  ./.venv/Scripts/python.exe -m scripts._backfill_conversation_orphan_owner --undo <arq.json>
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm").strip("_")
TENANT = "hubloc"
BATCH = 400
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


def _is_orphan(d):
    a = d.get("assigned_to_uid")
    return a == "" or a is None


def run(apply):
    undo = []
    stats = {"scanned": 0, "skip_not_orphan": 0, "skip_no_contact": 0,
             "skip_contact_missing": 0, "skip_contact_orphan": 0,
             "skip_takeover": 0, "synced": 0}
    contact_cache = {}
    batch = c.batch()
    pending = 0

    for snap in tcol("wa_conversations").stream():
        stats["scanned"] += 1
        conv = snap.to_dict() or {}

        if not _is_orphan(conv):                       # passo 1: idempotente
            stats["skip_not_orphan"] += 1
            continue
        if conv.get("takeover_status") in ("pending", "active"):   # passo 5
            stats["skip_takeover"] += 1
            continue

        cid = conv.get("contact_id")
        if cid in (None, ""):                          # passo 2
            stats["skip_no_contact"] += 1
            continue

        if cid not in contact_cache:
            cs = tcol("wa_contacts").document(str(cid)).get()
            contact_cache[cid] = cs.to_dict() if cs.exists else None
        contact = contact_cache[cid]
        if not contact:                                # passo 3
            stats["skip_contact_missing"] += 1
            continue
        if _is_orphan(contact):                        # passo 4
            stats["skip_contact_orphan"] += 1
            continue

        stats["synced"] += 1
        undo.append({"col": "wa_conversations", "doc_id": snap.id, "old": {
            "assigned_to": conv.get("assigned_to"),
            "assigned_to_uid": conv.get("assigned_to_uid"),
            "department_id": conv.get("department_id"),
        }})
        if apply:
            batch.set(snap.reference, {
                "assigned_to": contact.get("assigned_to"),
                "assigned_to_uid": contact.get("assigned_to_uid"),
                "department_id": contact.get("department_id"),  # None se ausente
            }, merge=True)
            pending += 1
            if pending >= BATCH:
                batch.commit()
                batch = c.batch()
                pending = 0
    if apply and pending:
        batch.commit()
    return stats, undo


def undo_from(path):
    with open(path, "r", encoding="utf-8") as fh:
        records = json.load(fh)
    batch = c.batch()
    pending = 0
    for r in records:
        batch.set(tcol(r["col"]).document(r["doc_id"]), r["old"], merge=True)
        pending += 1
        if pending >= BATCH:
            batch.commit()
            batch = c.batch()
            pending = 0
    if pending:
        batch.commit()
    print(f"  [UNDO] revertidos {len(records)} docs de {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", metavar="ARQ")
    args = ap.parse_args()
    if args.undo:
        undo_from(args.undo)
        return
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Backfill conversa orfa -> Dono do Lead ({mode}) | tenant={TENANT} prefix={PREFIX} project={c.project} ===")
    stats, undo = run(args.apply)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if args.apply:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = Path(__file__).resolve().parent / f"_backfill_undo_conv_owner_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(undo, fh, ensure_ascii=False, indent=0)
        print(f"  [OK] aplicado. Undo: {out}")
        print(f"       desfazer: python -m scripts._backfill_conversation_orphan_owner --undo \"{out}\"")
    else:
        print("  (dry-run — nada escrito. Rode com --apply pra aplicar.)")


if __name__ == "__main__":
    main()
