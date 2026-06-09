# -*- coding: utf-8 -*-
"""Prova que o fix do state_sync (5e6ff21) funciona: contatos criados
APOS o deploy devem nascer atribuidos ao dono (nao orfaos).

Deploy 5e6ff21 -> revisao castro-crm-00100-dmw @ 2026-05-19T16:52:29Z.
Read-only, sem PII.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
DEPLOY = datetime(2026, 5, 19, 16, 52, 29, tzinfo=timezone.utc)
GERENCIA_UID = "pIBWBGggN7SUSSraucjUz8iePq33"
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


total = 0
unassigned_pre = 0
unassigned_post = 0       # <-- se >0, fix NAO funcionou
post_total = 0
post_to_gerencia = 0
post_other_assigned = 0
no_fs = 0

for s in tcol("wa_contacts").stream():
    x = s.to_dict() or {}
    total += 1
    a = x.get("assigned_to_uid")
    unassigned = (a == "" or a is None)
    fs = x.get("first_seen_at")
    if not isinstance(fs, datetime):
        no_fs += 1
        if unassigned:
            unassigned_pre += 1  # sem timestamp -> trata como legado/pre
        continue
    post = fs >= DEPLOY
    if post:
        post_total += 1
        if unassigned:
            unassigned_post += 1
        elif a == GERENCIA_UID:
            post_to_gerencia += 1
        else:
            post_other_assigned += 1
    elif unassigned:
        unassigned_pre += 1

print("=== Prova do fix state_sync (5e6ff21 @ 16:52:29Z) ===")
print(f"  total contatos: {total}")
print(f"  criados POS-deploy: {post_total}")
print(f"    -> atribuidos ao gerencia: {post_to_gerencia}")
print(f"    -> outro assigned:         {post_other_assigned}")
print(f"    -> ORFAOS pos-deploy:      {unassigned_post}  <<< tem que ser 0")
print(f"  orfaos PRE-deploy (gap a limpar no backfill final): {unassigned_pre}")
print(f"  (sem first_seen_at: {no_fs})")
print()
if unassigned_post == 0 and post_to_gerencia > 0:
    print("  >>> FIX OK ✅ — toda onda pos-deploy nasce atribuida ao dono.")
elif post_total == 0:
    print("  >>> inconclusivo: nenhuma criacao pos-deploy ainda (esperar nova onda).")
else:
    print("  >>> ATENCAO ⚠️ — ha orfaos criados POS-deploy. Fix nao efetivo, investigar.")
