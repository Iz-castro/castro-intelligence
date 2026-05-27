# -*- coding: utf-8 -*-
"""Export das anotacoes CRM-only (Lead-level, keyed por wa_id) antes do wipe.

O re-sync coex (offboarding no celular + re-signup) restaura contatos +
historico, mas NAO restaura os campos so-do-CRM. Este script salva esses
campos num JSON keyed por wa_id (chave estavel que sobrevive ao re-sync),
para re-importar depois com scripts/import_crm_annotations.py.
Ver docs/PLANO_LEAD_ATENDIMENTO_E_REGRAS.md (decisao #7 + checklist Helenice).

LGPD: o arquivo gerado contem dado pessoal (nome declarado, notas).
  - NAO comitar no git (scripts/_exports/ esta no .gitignore).
  - Retencao curta: apague apos o re-import confirmado.
  - Finalidade unica: migracao tecnica do re-onboarding.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"   # staging: castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.export_crm_annotations --tenant-id hubloc
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")

# Campos CRM-only que o re-sync coex nao restaura. Lead-level (por wa_id).
# NAO inclui wa_conversations: o conversation_id muda no re-onboard (canal
# novo => channel_id novo) e a Helenice e operadora unica -> assigned_to e
# re-derivado pelo auto-assign. assigned_to/department ainda sao exportados
# (fidelidade), mas nao disparam a inclusao sozinhos.
CRM_FIELDS = [
    "declared_name",
    "notes",
    "qualification",
    "rating",
    "rating_requested_at",
    "attendance_protocol",
    "attendance_started_at",
    "original_operator_id",
    "converted_by_user_id",
    "is_archived",
    "department_id",
    "assigned_to",
    "assigned_to_uid",
]

# Subconjunto que dispara a exportacao do contato (operador-inserido).
TRIGGER_FIELDS = (
    "declared_name", "notes", "qualification", "rating",
    "attendance_protocol", "is_archived",
    "original_operator_id", "converted_by_user_id",
)


def _is_default(field: str, v) -> bool:
    if field == "qualification":
        return str(v or "").strip().lower() in ("", "novo")
    if field == "is_archived":
        return not v
    if field in ("declared_name", "notes", "attendance_protocol",
                 "attendance_started_at", "assigned_to_uid"):
        return not str(v or "").strip()
    # rating, rating_requested_at, *_id, assigned_to, department_id
    return v is None


def _trigger(contact: dict) -> bool:
    return any(not _is_default(f, contact.get(f)) for f in TRIGGER_FIELDS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export de anotacoes CRM-only (keyed por wa_id).")
    ap.add_argument("--tenant-id", default="hubloc")
    ap.add_argument("--out", default="", help="Caminho do JSON. Default: scripts/_exports/crm_annotations_<tid>_<ts>.json")
    args = ap.parse_args()
    tid = args.tenant_id

    out_path = args.out
    if not out_path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_dir = Path(__file__).resolve().parent / "_exports"
        out_dir.mkdir(exist_ok=True)
        out_path = str(out_dir / f"crm_annotations_{tid}_{ts}.json")

    c = get_firestore_client()
    contacts = c.collection(f"{PREFIX}_tenants").document(tid).collection("wa_contacts")

    records: dict[str, dict] = {}
    total = 0
    skipped_no_waid = 0
    for d in contacts.stream():
        x = d.to_dict() or {}
        total += 1
        wa_id = str(x.get("wa_id") or "").strip()
        if not wa_id:
            skipped_no_waid += 1
            continue
        if not _trigger(x):
            continue
        rec = {f: x.get(f) for f in CRM_FIELDS if not _is_default(f, x.get(f))}
        if rec:
            records[wa_id] = rec  # wa_id e unico (dedup atomico)

    payload = {
        "tenant_id": tid,
        "prefix": PREFIX,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "fields": CRM_FIELDS,
        "count": len(records),
        "contacts_scanned": total,
        "contacts": records,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)

    print(f"=== Export CRM-only | tenant={tid} prefix={PREFIX} ===")
    print(f"  contatos varridos:     {total}")
    print(f"  exportados (c/ anot.): {len(records)}")
    if skipped_no_waid:
        print(f"  pulados (sem wa_id):   {skipped_no_waid}")
    print(f"  arquivo:               {out_path}")
    print()
    print("  LGPD: o arquivo contem PII. NAO comitar (scripts/_exports/ no .gitignore),")
    print("        apague apos re-import confirmado, finalidade unica (migracao).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
