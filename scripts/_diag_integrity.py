# -*- coding: utf-8 -*-
"""Integridade pos-dedupe (read-only): refs orfas + dups restantes."""
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


contact_ids = set()
by_wa = defaultdict(list)
for s in tcol("wa_contacts").stream():
    x = s.to_dict() or {}
    contact_ids.add(x.get("id"))
    by_wa[str(x.get("wa_id") or "")].append(x.get("id"))

conv_total = conv_orphan = 0
for s in tcol("wa_conversations").stream():
    conv_total += 1
    if (s.to_dict() or {}).get("contact_id") not in contact_ids:
        conv_orphan += 1

msg_total = msg_orphan = 0
for s in tcol("wa_messages").stream():
    msg_total += 1
    if (s.to_dict() or {}).get("contact_id") not in contact_ids:
        msg_orphan += 1

dups = {k: v for k, v in by_wa.items() if len(v) > 1}
print(f"total contatos:            {len(contact_ids)}")
print(f"wa_id distintos:           {len(by_wa)}")
print(f"grupos duplicados restantes:{len(dups)} (esperado 0)")
print(f"conversations: total={conv_total} ORFAS={conv_orphan} (esperado 0)")
print(f"messages:      total={msg_total} ORFAS={msg_orphan} (esperado 0)")
