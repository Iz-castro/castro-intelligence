# -*- coding: utf-8 -*-
"""Diagnostico read-only do isolamento por operador (sem PII).

Uso (PowerShell, de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_isolation

So imprime ids/roles/contagens. NUNCA nome/telefone/conteudo.
"""
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
TEST_EMAIL = "teste1@hubloc.com.br"

c = get_firestore_client()


def tcol(name):
    """Subcolecao tenant-scoped: castro_crm_tenants/hubloc/<name>."""
    return (
        c.collection(f"{PREFIX}_tenants")
        .document(TENANT)
        .collection(name)
    )


def flat(name):
    return c.collection(f"{PREFIX}_{name}")


print(f"=== users (tenant-scoped {PREFIX}_tenants/{TENANT}/users) ===")
test_user = None
owner_candidates = {}
for d in tcol("users").stream():
    u = d.to_dict() or {}
    uid = u.get("id")
    owner_candidates[uid] = {"role": u.get("role"), "dept": u.get("department_id"),
                             "fb": u.get("firebase_uid"), "active": u.get("is_active")}
    if (u.get("email") or "").strip().lower() == TEST_EMAIL:
        test_user = {"doc_id": d.id, "id": uid, "role": u.get("role"),
                     "department_id": u.get("department_id"),
                     "firebase_uid": u.get("firebase_uid"),
                     "is_active": u.get("is_active")}
print(f"  total users no tenant: {len(owner_candidates)}")
print(f"  teste1 -> {test_user}")

print(f"\n=== channels (tenant-scoped) ===")
for d in tcol("channels").stream():
    ch = d.to_dict() or {}
    print(f"  channel id={ch.get('id')} type={ch.get('channel_type')} "
          f"owner_user_id={ch.get('owner_user_id')} phone_id={ch.get('phone_number_id')}")

print(f"\n=== wa_contacts (tenant-scoped) — varredura unica, so estrutura ===")
total = 0
non_archived = 0
uid_blank = 0
uid_none = 0
uid_set = 0
dept_counter = Counter()
test_id = test_user["id"] if test_user else None
test_dept = test_user["department_id"] if test_user else None
n_assigned_to_test = 0
n_dept_eq_test = 0
n_scoped_for_test = 0  # uniao do que MEU helper retornaria pro teste1

for d in tcol("wa_contacts").stream():
    x = d.to_dict() or {}
    total += 1
    archived = int(x.get("is_archived", 0) or 0) != 0
    if archived:
        continue
    non_archived += 1
    a_uid = x.get("assigned_to_uid")
    a_to = x.get("assigned_to")
    dept = x.get("department_id")
    if a_uid == "":
        uid_blank += 1
    elif a_uid is None:
        uid_none += 1
    else:
        uid_set += 1
    dept_counter[dept] += 1
    is_assigned_test = (test_id is not None and a_to == test_id)
    is_dept_test = (test_dept is not None and dept == test_dept)
    if is_assigned_test:
        n_assigned_to_test += 1
    if is_dept_test:
        n_dept_eq_test += 1
    if is_assigned_test or a_uid == "" or a_uid is None or is_dept_test:
        n_scoped_for_test += 1

print(f"  total docs:              {total}")
print(f"  nao-arquivados:          {non_archived}")
print(f"  assigned_to_uid == '':   {uid_blank}")
print(f"  assigned_to_uid is None: {uid_none}")
print(f"  assigned_to_uid setado:  {uid_set}")
print(f"  dept distrib (dept->qtd): {dict(dept_counter)}")
print(f"  -- teste1: id={test_id} dept={test_dept} role={test_user['role'] if test_user else None}")
print(f"  assigned_to == teste1.id:        {n_assigned_to_test}")
print(f"  department_id == teste1.dept:    {n_dept_eq_test}")
print(f"  >>> meu helper retornaria p/ teste1: {n_scoped_for_test} (esperado: poucos)")
