# -*- coding: utf-8 -*-
"""Para cada grupo de contatos duplicados (mesmo wa_id), verifica se ha
wa_conversations/wa_messages referenciando — define risco da limpeza.
Read-only, sem PII (so ids/contagens)."""
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


# 1. agrupa contatos por wa_id
by_wa = defaultdict(list)
contact_meta = {}
for snap in tcol("wa_contacts").stream():
    x = snap.to_dict() or {}
    cid = x.get("id")
    by_wa[str(x.get("wa_id") or "")].append(cid)
    contact_meta[cid] = {
        "src": x.get("created_source"),
        "assigned": x.get("assigned_to"),
        "doc": snap.id,
    }
dup_groups = {k: v for k, v in by_wa.items() if len(v) > 1}
dup_contact_ids = {cid for v in dup_groups.values() for cid in v}
print(f"grupos dup: {len(dup_groups)} | contatos em dup: {len(dup_contact_ids)} "
      f"| extras: {sum(len(v) - 1 for v in dup_groups.values())}")

# 2. quantas conversations/messages referenciam contatos duplicados
conv_by_contact = Counter()
for snap in tcol("wa_conversations").stream():
    x = snap.to_dict() or {}
    cid = x.get("contact_id")
    if cid in dup_contact_ids:
        conv_by_contact[cid] += 1
msg_by_contact = Counter()
for snap in tcol("wa_messages").stream():
    x = snap.to_dict() or {}
    cid = x.get("contact_id")
    if cid in dup_contact_ids:
        msg_by_contact[cid] += 1

print(f"contatos duplicados COM conversation: {len(conv_by_contact)} "
      f"(total convs: {sum(conv_by_contact.values())})")
print(f"contatos duplicados COM mensagem:     {len(msg_by_contact)} "
      f"(total msgs: {sum(msg_by_contact.values())})")

# 3. grupos onde >1 membro tem referencia (merge arriscado) vs 0-1 (seguro)
risky = 0
safe = 0
for k, ids in dup_groups.items():
    with_ref = sum(1 for i in ids if conv_by_contact.get(i) or msg_by_contact.get(i))
    if with_ref > 1:
        risky += 1
    else:
        safe += 1
print(f"grupos SEGUROS (<=1 membro com ref): {safe}")
print(f"grupos ARRISCADOS (>1 membro com ref, precisa repontar): {risky}")
src_extras = Counter()
for k, ids in dup_groups.items():
    for i in sorted(ids)[1:]:
        src_extras[contact_meta.get(i, {}).get("src")] += 1
print(f"created_source dos 'extras' (candidatos a remover): {dict(src_extras)}")
