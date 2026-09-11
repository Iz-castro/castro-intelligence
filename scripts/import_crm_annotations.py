# -*- coding: utf-8 -*-
"""Re-import das anotacoes CRM-only apos o re-onboard (idempotente, por wa_id).

Le o JSON gerado por scripts/export_crm_annotations.py e re-aplica os campos
CRM-only nos contatos restaurados pelo re-sync coex, casando por wa_id.
Idempotente: rodar 2x nao muda nada (merge dos mesmos valores).
Ver docs/PLANO_LEAD_ATENDIMENTO_E_REGRAS.md (decisao #7 + checklist Helenice).

dry-run por default (so mostra o plano). Use --confirm pra gravar.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"   # staging: castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.import_crm_annotations --in scripts/_exports/crm_annotations_hubloc_<ts>.json
  ./.venv/Scripts/python.exe -m scripts.import_crm_annotations --in <arquivo> --confirm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database_firestore import (  # noqa: E402
    _resolve_display_name,
    build_contact_search_fields,
)
from firestore_common import get_firestore_client  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")

# Allowlist defensiva: so estes campos podem ser re-importados (espelha o
# export). Qualquer outro campo no arquivo e ignorado.
ALLOWED_FIELDS = frozenset({
    "declared_name", "notes", "qualification", "rating", "rating_requested_at",
    "attendance_protocol", "attendance_started_at", "original_operator_id",
    "converted_by_user_id", "is_archived", "department_id",
    "assigned_to", "assigned_to_uid",
})


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-import de anotacoes CRM-only (por wa_id).")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--tenant-id", default="", help="Default: tenant_id gravado no arquivo.")
    ap.add_argument("--confirm", action="store_true", help="Grava de fato. Sem isso, dry-run.")
    args = ap.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    tid = args.tenant_id or payload.get("tenant_id") or "hubloc"
    file_prefix = payload.get("prefix")
    records = payload.get("contacts") or {}

    print(f"=== Import CRM-only | tenant={tid} prefix={PREFIX} ===")
    print(f"  arquivo:         {args.in_path}")
    print(f"  exportado em:    {payload.get('exported_at')}")
    print(f"  registros:       {len(records)}")
    if file_prefix and file_prefix != PREFIX:
        print(f"  [WARN] prefix do arquivo ({file_prefix}) != ambiente atual ({PREFIX}).")
    print(f"  modo:            {'CONFIRMED (grava)' if args.confirm else 'DRY-RUN (nada gravado)'}")

    c = get_firestore_client()
    contacts = c.collection(f"{PREFIX}_tenants").document(tid).collection("wa_contacts")

    # Indexa wa_contacts por wa_id numa unica varredura (evita N queries).
    by_wa: dict[str, list] = {}
    for snap in contacts.stream():
        x = snap.to_dict() or {}
        w = str(x.get("wa_id") or "").strip()
        if w:
            by_wa.setdefault(w, []).append(snap.reference)

    applied = 0
    not_found = 0
    multi = 0
    empty = 0
    for wa_id, rec in records.items():
        fields = {k: v for k, v in (rec or {}).items() if k in ALLOWED_FIELDS}
        if not fields:
            empty += 1
            continue
        refs = by_wa.get(str(wa_id).strip())
        if not refs:
            not_found += 1
            continue
        if len(refs) > 1:
            multi += 1
        for ref in refs:
            payload_fields = dict(fields)
            # Picker v2.1 (revisao F2a): import que grava declared_name tem
            # que recalcular display_name + campos de busca no MESMO write
            # (senao o picker acha o lead pelo nome VELHO). Le o doc atual
            # so quando o nome muda — mesma regra do write-path.
            if "declared_name" in payload_fields:
                atual = ref.get().to_dict() or {}
                merged = {**atual, **payload_fields}
                merged["display_name"] = _resolve_display_name(
                    merged.get("declared_name", ""),
                    merged.get("whatsapp_profile_name", ""),
                    merged.get("phone_formatted", ""),
                )
                payload_fields["display_name"] = merged["display_name"]
                payload_fields.update(build_contact_search_fields(merged))
            if args.confirm:
                ref.set(payload_fields, merge=True)
        applied += 1

    print(f"  aplicados:       {applied}")
    print(f"  nao-encontrados: {not_found}   (wa_id nao voltou no re-sync)")
    if empty:
        print(f"  sem campos validos: {empty}")
    if multi:
        print(f"  [WARN] {multi} wa_id com >1 contato (dedup?) — aplicado em todos.")
    if not args.confirm:
        print("  [DRY-RUN] Nada gravado. Use --confirm para aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
