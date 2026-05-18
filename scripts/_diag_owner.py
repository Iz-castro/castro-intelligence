# -*- coding: utf-8 -*-
"""Acha o canal coexistence e o dono pretendido (read-only, sem PII de cliente).

Mostra contas internas de operador (email/role) — necessario p/ o Rafal
decidir o dono. NUNCA imprime nome/telefone de contato.
"""
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


def flat(name):
    return c.collection(f"{PREFIX}_{name}")


print("=== 4 users do tenant (id / email / role / dept / fb_uid) ===")
for d in tcol("users").stream():
    u = d.to_dict() or {}
    print(f"  id={u.get('id')} email={u.get('email')} role={u.get('role')} "
          f"dept={u.get('department_id')} fb={u.get('firebase_uid')} active={u.get('is_active')}")

print("\n=== channels FLAT (castro_crm_channels) ===")
for d in flat("channels").stream():
    ch = d.to_dict() or {}
    print(f"  doc={d.id} id={ch.get('id')} type={ch.get('channel_type')} "
          f"owner_user_id={ch.get('owner_user_id')} phone_id={ch.get('phone_number_id')} "
          f"display={ch.get('display_phone_number')} active={ch.get('is_active')}")

print("\n=== channels tenant-scoped (castro_crm_tenants/hubloc/channels) ===")
n = 0
for d in tcol("channels").stream():
    n += 1
    ch = d.to_dict() or {}
    print(f"  doc={d.id} id={ch.get('id')} type={ch.get('channel_type')} "
          f"owner_user_id={ch.get('owner_user_id')} phone_id={ch.get('phone_number_id')}")
print(f"  (total tenant-scoped channels: {n})")

print("\n=== dos 129 contatos atribuidos: para quem? (assigned_to -> qtd) ===")
assignee = Counter()
chan = Counter()
src = Counter()
for d in tcol("wa_contacts").stream():
    x = d.to_dict() or {}
    if x.get("assigned_to_uid"):
        assignee[x.get("assigned_to")] += 1
    chan[x.get("channel_id")] += 1
    src[x.get("source_channel_type")] += 1
print(f"  assigned_to -> qtd: {dict(assignee)}")
print(f"  channel_id distrib (todos 3700): {dict(chan)}")
print(f"  source_channel_type distrib:     {dict(src)}")
