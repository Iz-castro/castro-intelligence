# -*- coding: utf-8 -*-
"""Reatribui os contatos 'Devolvido ao bot' (todos da aline, user_id 5) de volta
para a aline. BATCHED (rapido p/ ~2290). Reatribui o CONTATO + as conversas do
canal 2 (coex da aline) que ficaram sem dono. Dry-run por default.

Uso:
  $env:FIRESTORE_PROJECT_ID="project-4a851bf9-f475-418c-800"
  ./.venv/Scripts/python.exe scripts/_reassign_bot_to_aline_tmp.py            # dry-run
  ./.venv/Scripts/python.exe scripts/_reassign_bot_to_aline_tmp.py --confirm  # aplica
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import set_tenant_context, get_firestore_client, collection_name  # noqa: E402
import database_firestore as db  # noqa: E402

TENANT = "hubloc"
ALINE_ID = 5
ALINE_UID = "mR9qyZjAOOhNF2nFtVwXFLMPSex2"
ALINE_CHANNEL = 2  # canal coex da aline


def _commit(c, items):
    n = 0
    batch = c.batch()
    cnt = 0
    for ref, data in items:
        batch.set(ref, data, merge=True)
        cnt += 1
        n += 1
        if cnt >= 400:
            batch.commit()
            batch = c.batch()
            cnt = 0
    if cnt:
        batch.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    set_tenant_context(TENANT)
    c = get_firestore_client()
    tn = c.collection(collection_name("tenants")).document(TENANT)

    # contatos devolvidos ao bot PELA aline
    cids = set()
    for s in tn.collection("wa_transfer_log").where("reason", "==", "Devolvido ao bot").stream():
        d = s.to_dict() or {}
        if d.get("from_user_id") == ALINE_ID:
            cids.add(str(d.get("contact_id")))

    # so os que AINDA estao sem dono (de fato no bot)
    contact_items = []
    for cid in cids:
        ref = tn.collection("wa_contacts").document(cid)
        cc = ref.get().to_dict() or {}
        if cc and not str(cc.get("assigned_to_uid") or "").strip():
            contact_items.append((ref, {"assigned_to": ALINE_ID, "assigned_to_uid": ALINE_UID, "is_backup": False}))

    # conversas do canal 2 (coex da aline) que ficaram SEM dono
    conv_items = []
    for s in tn.collection("wa_conversations").where("channel_id", "==", ALINE_CHANNEL).stream():
        d = s.to_dict() or {}
        if not str(d.get("assigned_to_uid") or "").strip():
            conv_items.append((s.reference, {"assigned_to": ALINE_ID, "assigned_to_uid": ALINE_UID, "is_backup": False}))

    print(f"contatos a reatribuir: {len(contact_items)} | conversas ch2 sem dono: {len(conv_items)}")
    if not args.confirm:
        print("DRY-RUN — nada gravado. Use --confirm para aplicar.")
        return

    nc = _commit(c, contact_items)
    nv = _commit(c, conv_items)
    print(f"OK: {nc} contatos + {nv} conversas reatribuidos para aline (user_id 5).")
    try:
        db.log_audit(0, "BULK_REASSIGN_BOT_TO_ALINE", f"{nc} contatos + {nv} conversas ch2 -> aline")
    except Exception as e:
        print("(audit log falhou, ok):", e)


if __name__ == "__main__":
    main()
