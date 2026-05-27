# -*- coding: utf-8 -*-
"""Inventario read-only de anotacoes CRM-only por contato (pre-wipe).

Conta, no tenant, quantos contatos tem dados que o re-sync coex NAO
restaura (declared_name manual, notas, qualificacao, avaliacao, protocolo,
etc.) — base pra decidir se o export antes do wipe e necessario.
Ver docs/PLANO_LEAD_ATENDIMENTO_E_REGRAS.md (decisao #7 + checklist Helenice).

NAO imprime PII (nome/telefone/conteudo de nota) — so contagens.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"   # staging: castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts._diag_crm_annotations --tenant-id hubloc
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")

# Campos operador-inseridos que se perdem no wipe (gatilho de export). NAO
# inclui assigned_to/department_id: voltam via auto-assign no re-sync coex.
TRIGGER_FIELDS = [
    "declared_name", "notes", "qualification", "rating",
    "attendance_protocol", "is_archived",
    "original_operator_id", "converted_by_user_id",
]


def _is_set(field: str, v) -> bool:
    if field == "qualification":
        return str(v or "").strip().lower() not in ("", "novo")
    if field == "is_archived":
        return bool(v)
    if field in ("declared_name", "notes", "attendance_protocol"):
        return bool(str(v or "").strip())
    return v is not None  # rating, *_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Inventario de anotacoes CRM-only (read-only).")
    ap.add_argument("--tenant-id", default="hubloc")
    args = ap.parse_args()
    tid = args.tenant_id

    c = get_firestore_client()
    contacts = c.collection(f"{PREFIX}_tenants").document(tid).collection("wa_contacts")

    total = 0
    coex = 0
    annotated = 0
    declared_diverges = 0  # declared_name != whatsapp_profile_name (rename manual)
    field_counts: Counter = Counter()
    for d in contacts.stream():
        x = d.to_dict() or {}
        total += 1
        if str(x.get("source_channel_type") or "") == "coexistence":
            coex += 1
        hit = False
        for f in TRIGGER_FIELDS:
            if _is_set(f, x.get(f)):
                field_counts[f] += 1
                hit = True
        if hit:
            annotated += 1
        dn = str(x.get("declared_name") or "").strip()
        pn = str(x.get("whatsapp_profile_name") or "").strip()
        if dn and dn != pn:
            declared_diverges += 1

    print(f"=== Inventario CRM-only | tenant={tid} prefix={PREFIX} ===")
    print(f"  contatos totais:          {total}")
    print(f"  coexistence:              {coex}")
    print(f"  COM anotacao CRM-only:    {annotated}   <- exportar antes do wipe se > 0")
    print(f"  declared_name != profile: {declared_diverges}   <- renomeacoes manuais (corrigem fallback +55...)")
    print(f"  --- por campo (nao-default) ---")
    for f in TRIGGER_FIELDS:
        print(f"    {f:24s} {field_counts.get(f, 0)}")
    if annotated == 0:
        print("  => Nenhuma anotacao CRM-only: export e no-op, pode wipar direto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
