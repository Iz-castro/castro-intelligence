# -*- coding: utf-8 -*-
"""Backfill: atribui contatos/conversas ORFAOS do canal coexistence id=2
ao dono (user id 3 = gerencia@hubloc.com.br). Reversivel.

So toca docs com channel_id==2 E assigned_to_uid vazio/None — NUNCA mexe
nos ja atribuidos nem em outros canais. Idempotente (re-rodar e seguro).

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._backfill_coex_owner            # dry-run
  ./.venv/Scripts/python.exe -m scripts._backfill_coex_owner --apply    # aplica

Desfazer:
  ./.venv/Scripts/python.exe -m scripts._backfill_coex_owner --undo <arquivo_undo.json>
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
CHANNEL_ID = 2
OWNER_ID = 3
OWNER_UID = "pIBWBGggN7SUSSraucjUz8iePq33"  # gerencia@hubloc.com.br (user id 3)
OWNER_DEPT = 1
BATCH = 400

c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


def _is_orphan(d):
    a = d.get("assigned_to_uid")
    return a == "" or a is None


def run(apply):
    undo = []
    stats = {}
    contact_ids = set()

    for colname in ("wa_contacts", "wa_conversations"):
        col = tcol(colname)
        changed = 0
        scanned = 0
        batch = c.batch()
        pending = 0

        for snap in col.where("channel_id", "==", CHANNEL_ID).stream():
            scanned += 1
            data = snap.to_dict() or {}
            if not _is_orphan(data):
                continue
            if colname == "wa_contacts":
                contact_ids.add(data.get("id", snap.id))
            undo.append({
                "col": colname,
                "doc_id": snap.id,
                "old": {
                    "assigned_to": data.get("assigned_to"),
                    "assigned_to_uid": data.get("assigned_to_uid"),
                    "department_id": data.get("department_id"),
                },
            })
            changed += 1
            if apply:
                batch.set(snap.reference, {
                    "assigned_to": OWNER_ID,
                    "assigned_to_uid": OWNER_UID,
                    "department_id": OWNER_DEPT,
                }, merge=True)
                pending += 1
                if pending >= BATCH:
                    batch.commit()
                    batch = c.batch()
                    pending = 0

        if apply and pending:
            batch.commit()

        stats[colname] = {"scanned_channel2": scanned, "orfaos_alterados": changed}

    return stats, undo, contact_ids


def undo_from(path):
    with open(path, "r", encoding="utf-8") as fh:
        records = json.load(fh)
    batch = c.batch()
    pending = 0
    n = 0
    for r in records:
        ref = tcol(r["col"]).document(r["doc_id"])
        batch.set(ref, r["old"], merge=True)
        pending += 1
        n += 1
        if pending >= BATCH:
            batch.commit()
            batch = c.batch()
            pending = 0
    if pending:
        batch.commit()
    print(f"  [UNDO] revertidos {n} docs a partir de {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="aplica (sem isso = dry-run)")
    ap.add_argument("--undo", metavar="ARQ", help="reverte a partir do log de undo")
    args = ap.parse_args()

    if args.undo:
        undo_from(args.undo)
        return

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Backfill coex owner ({mode}) | canal={CHANNEL_ID} -> user {OWNER_ID} "
          f"uid={OWNER_UID} dept={OWNER_DEPT} ===")
    stats, undo, contact_ids = run(args.apply)
    for col, s in stats.items():
        print(f"  {col}: scaneados(channel=2)={s['scanned_channel2']} "
              f"orfaos_alterados={s['orfaos_alterados']}")
    print(f"  contatos distintos afetados: {len(contact_ids)}")

    if args.apply:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = Path(__file__).resolve().parent / f"_backfill_undo_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(undo, fh, ensure_ascii=False, indent=0)
        print(f"  [OK] aplicado. Log reversivel: {out}")
        print(f"       desfazer: python -m scripts._backfill_coex_owner --undo \"{out}\"")
    else:
        print("  (dry-run — nada escrito. Rode com --apply pra aplicar.)")


if __name__ == "__main__":
    main()
