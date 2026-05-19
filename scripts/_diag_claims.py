# -*- coding: utf-8 -*-
"""Auditoria READ-ONLY dos custom claims no Firebase Auth.

Rules estritas (Fase 2) dependem de request.auth.token.tenant_id e .role.
Sem o claim no JWT, o operador e trancado pra fora. Este script so LE —
nao escreve claim nenhum.

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_claims
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firebase_admin import auth  # noqa: E402
from firebase_admin_client import get_firebase_app  # noqa: E402
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"

OPERATORS = [
    "rafaluisc@outlook.com",
    "izaeldecastro@gmail.com",
    "gerencia@hubloc.com.br",
    "teste1@hubloc.com.br",
]

app = get_firebase_app()
c = get_firestore_client()


def tprofile(uid):
    snap = (
        c.collection(f"{PREFIX}_tenants").document(TENANT)
        .collection("operator_profiles").document(uid).get()
    )
    return snap.to_dict() if snap.exists else None


print("=== Custom claims no Firebase Auth (read-only) ===")
ready = 0
for email in OPERATORS:
    try:
        u = auth.get_user_by_email(email, app=app)
    except Exception as e:  # noqa: BLE001
        print(f"  {email}: ERRO get_user -> {e!r}")
        continue
    cc = u.custom_claims or {}
    tid = cc.get("tenant_id")
    role = cc.get("role")
    prof = tprofile(u.uid)
    ok = bool(tid) and bool(role) and prof is not None
    ready += 1 if ok else 0
    print(
        f"  {email}\n"
        f"    uid={u.uid}\n"
        f"    claim.tenant_id={tid!r} claim.role={role!r}\n"
        f"    operator_profile (tenants/{TENANT}/operator_profiles/{u.uid}): "
        f"{'existe' if prof else 'AUSENTE'}"
        + (f" is_active={prof.get('is_active')} role={prof.get('role')}" if prof else "")
        + f"\n    -> {'PRONTO p/ rules estritas ✅' if ok else 'FALTA (lockout se subir rules) ❌'}"
    )

print(f"\n  {ready}/{len(OPERATORS)} prontos. "
      f"{'Pode planejar deploy das rules.' if ready == len(OPERATORS) else 'NAO subir rules ate 100% terem claim+profile.'}")
