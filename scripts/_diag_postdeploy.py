# -*- coding: utf-8 -*-
"""Verificacao pos-deploy do get-or-create atomico (read-only, sem PII,
ZERO escrita em prod). Usa o trafego real de SMB sync como teste vivo.

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_postdeploy
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
TENANT = "hubloc"
c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


cids = set()
by_wa = defaultdict(list)
for s in tcol("wa_contacts").stream():
    x = s.to_dict() or {}
    cids.add(x.get("id"))
    by_wa[str(x.get("wa_id") or "")].append(x.get("id"))
dups = {k: v for k, v in by_wa.items() if len(v) > 1}

conv_orphan = sum(
    1 for s in tcol("wa_conversations").stream()
    if (s.to_dict() or {}).get("contact_id") not in cids
)

# wa_contact_index: criado SO pelo codigo novo. Se esta sendo populado,
# o caminho atomico esta ativo em prod.
idx_total = 0
idx_recent = 0
now = datetime.now(timezone.utc)
for s in tcol("wa_contact_index").stream():
    idx_total += 1
    ca = (s.to_dict() or {}).get("created_at")
    if isinstance(ca, datetime):
        if (now - ca).total_seconds() < 1800:
            idx_recent += 1

print(f"=== Pos-deploy 2730ca5 (prod, sync ativo) ===")
print(f"  contatos: {len(cids)} | wa_id distintos: {len(by_wa)}")
print(f"  grupos duplicados: {len(dups)}  (esperado 0)")
print(f"  conversations orfas: {conv_orphan}  (esperado 0)")
print(f"  wa_contact_index total: {idx_total}")
print(f"  wa_contact_index criados ult. 30min: {idx_recent}")
print(f"  >>> {'OK ✅ codigo novo ativo, 0 duplicatas sob sync' if (len(dups) == 0 and conv_orphan == 0 and idx_total > 0) else 'REVISAR ⚠️'}")
