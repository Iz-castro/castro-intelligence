# -*- coding: utf-8 -*-
"""Consolida contatos duplicados (mesmo wa_id) — REVERSIVEL.

Por grupo (mesmo wa_id, >1 doc): escolhe um sobrevivente e, para cada
nao-sobrevivente, repointa wa_conversations.contact_id e
wa_messages.contact_id pro sobrevivente, depois deleta o doc duplicado.

Sobrevivente = maior score:
  (#mensagens, tem_conversation, created_source==webhook, assigned_to setado,
   id menor como desempate).

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._dedupe_contacts            # dry-run
  ./.venv/Scripts/python.exe -m scripts._dedupe_contacts --apply
  ./.venv/Scripts/python.exe -m scripts._dedupe_contacts --undo <arq.json>
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
BATCH = 400
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


def _load():
    contacts = {}          # contact_id -> (doc_id, data)
    by_wa = defaultdict(list)
    for snap in tcol("wa_contacts").stream():
        x = snap.to_dict() or {}
        cid = x.get("id")
        if cid is None:
            continue
        contacts[cid] = (snap.id, x)
        by_wa[str(x.get("wa_id") or "")].append(cid)

    conv_refs = defaultdict(list)   # contact_id -> [conv doc_id]
    for snap in tcol("wa_conversations").stream():
        x = snap.to_dict() or {}
        conv_refs[x.get("contact_id")].append(snap.id)
    msg_refs = defaultdict(list)    # contact_id -> [msg doc_id]
    for snap in tcol("wa_messages").stream():
        x = snap.to_dict() or {}
        msg_refs[x.get("contact_id")].append(snap.id)
    return contacts, by_wa, conv_refs, msg_refs


def _score(cid, data, conv_refs, msg_refs):
    return (
        len(msg_refs.get(cid, [])),
        1 if conv_refs.get(cid) else 0,
        1 if data.get("created_source") == "webhook" else 0,
        1 if data.get("assigned_to") else 0,
        -int(cid),
    )


def run(apply):
    contacts, by_wa, conv_refs, msg_refs = _load()
    dup_groups = {k: v for k, v in by_wa.items() if len(v) > 1}

    undo = {"deleted_contacts": [], "repointed": []}
    n_groups = n_deleted = n_repoint_conv = n_repoint_msg = 0
    batch = c.batch()
    pending = 0

    def _flush():
        nonlocal batch, pending
        if apply and pending:
            batch.commit()
            batch = c.batch()
            pending = 0

    for wa, cids in dup_groups.items():
        n_groups += 1
        survivor = max(cids, key=lambda i: _score(i, contacts[i][1], conv_refs, msg_refs))
        for cid in cids:
            if cid == survivor:
                continue
            doc_id, data = contacts[cid]
            # repointar conversations
            for conv_doc in conv_refs.get(cid, []):
                undo["repointed"].append({"col": "wa_conversations", "doc_id": conv_doc,
                                          "old_contact_id": cid})
                n_repoint_conv += 1
                if apply:
                    batch.set(tcol("wa_conversations").document(conv_doc),
                              {"contact_id": survivor}, merge=True)
                    pending += 1
                    if pending >= BATCH:
                        _flush()
            # repointar messages
            for msg_doc in msg_refs.get(cid, []):
                undo["repointed"].append({"col": "wa_messages", "doc_id": msg_doc,
                                          "old_contact_id": cid})
                n_repoint_msg += 1
                if apply:
                    batch.set(tcol("wa_messages").document(msg_doc),
                              {"contact_id": survivor}, merge=True)
                    pending += 1
                    if pending >= BATCH:
                        _flush()
            # deletar contato duplicado (guarda doc inteiro p/ undo)
            undo["deleted_contacts"].append({"doc_id": doc_id, "data": data})
            n_deleted += 1
            if apply:
                batch.delete(tcol("wa_contacts").document(doc_id))
                pending += 1
                if pending >= BATCH:
                    _flush()
    _flush()

    print(f"  grupos processados:        {n_groups}")
    print(f"  contatos deletados:        {n_deleted}")
    print(f"  conversations repontadas:  {n_repoint_conv}")
    print(f"  messages repontadas:       {n_repoint_msg}")
    return undo


def undo_from(path):
    with open(path, "r", encoding="utf-8") as fh:
        u = json.load(fh)
    batch = c.batch()
    pending = 0

    def _flush():
        nonlocal batch, pending
        if pending:
            batch.commit()
            batch = c.batch()
            pending = 0

    for rec in u.get("deleted_contacts", []):
        batch.set(tcol("wa_contacts").document(rec["doc_id"]), rec["data"])
        pending += 1
        if pending >= BATCH:
            _flush()
    for rec in u.get("repointed", []):
        batch.set(tcol(rec["col"]).document(rec["doc_id"]),
                  {"contact_id": rec["old_contact_id"]}, merge=True)
        pending += 1
        if pending >= BATCH:
            _flush()
    _flush()
    print(f"  [UNDO] restaurados {len(u.get('deleted_contacts', []))} contatos "
          f"+ {len(u.get('repointed', []))} refs de {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", metavar="ARQ")
    args = ap.parse_args()
    if args.undo:
        undo_from(args.undo)
        return
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Dedupe contatos ({mode}) ===")
    undo = run(args.apply)
    if args.apply:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = Path(__file__).resolve().parent / f"_dedupe_undo_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(undo, fh, ensure_ascii=False, default=str)
        print(f"  [OK] aplicado. Undo: {out}")
        print(f"       desfazer: python -m scripts._dedupe_contacts --undo \"{out}\"")
    else:
        print("  (dry-run — nada escrito.)")


if __name__ == "__main__":
    main()
