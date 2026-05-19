# -*- coding: utf-8 -*-
"""Detecta duplicidade de contatos (read-only, sem PII).

Agrupa por wa_id normalizado e por doc-id pattern; so imprime contagens
e exemplos de DOC IDS (nunca o numero/nome).

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_dupes
"""
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


def mask(wa):
    """So tamanho + ultimos 2 digitos pra agrupar sem expor o numero."""
    s = str(wa or "")
    return f"len{len(s)}..{s[-2:]}" if s else "VAZIO"


by_wa = defaultdict(list)        # wa_id cru -> [doc_id]
by_norm = defaultdict(list)      # wa_id sem nao-digito -> [doc_id]
total = 0
created_src = Counter()
for snap in tcol("wa_contacts").stream():
    total += 1
    x = snap.to_dict() or {}
    wa = str(x.get("wa_id") or "")
    norm = "".join(ch for ch in wa if ch.isdigit())
    by_wa[wa].append(snap.id)
    by_norm[norm].append(snap.id)
    created_src[x.get("created_source")] += 1

dup_wa = {k: v for k, v in by_wa.items() if len(v) > 1}
dup_norm = {k: v for k, v in by_norm.items() if len(v) > 1}

print(f"=== wa_contacts dupes (tenant {TENANT}) ===")
print(f"  total docs:                 {total}")
print(f"  wa_id distintos (cru):      {len(by_wa)}")
print(f"  wa_id distintos (so digito):{len(by_norm)}")
print(f"  grupos duplicados (cru):    {len(dup_wa)}  contatos extras: {sum(len(v)-1 for v in dup_wa.values())}")
print(f"  grupos duplicados (norm):   {len(dup_norm)} contatos extras: {sum(len(v)-1 for v in dup_norm.values())}")
print(f"  created_source distrib:     {dict(created_src)}")
print(f"  dist tamanho grupos (norm): {dict(Counter(len(v) for v in by_norm.values()))}")
print("  exemplos (doc ids dos 5 maiores grupos norm; SEM numero):")
for k, v in sorted(dup_norm.items(), key=lambda kv: -len(kv[1]))[:5]:
    print(f"    {mask(k)} -> {len(v)} docs: {sorted(v)[:8]}")
