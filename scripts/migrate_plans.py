# -*- coding: utf-8 -*-
"""Backfill one-off: renomeia planos legados dos tenants para o vocabulario novo.

Mapa (decisao PO 2026-07-13):
  starter      -> professional
  professional -> professional (sem mudanca)
  enterprise   -> enterprise_ai
  premium      -> ai_custom

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "<projeto>"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"  # ou "castro_crm_staging"
  ./.venv/Scripts/python.exe -m scripts.migrate_plans            # dry-run
  ./.venv/Scripts/python.exe -m scripts.migrate_plans --yes      # aplica

Idempotente: docs ja no vocabulario novo sao ignorados. Enquanto o backfill
nao roda, a leitura ja normaliza via _LEGACY_PLAN_MAP (tenant_service).
"""
import argparse
import sys

from firestore_common import get_firestore_client, global_collection, utcnow
from tenant_service import PLAN_OPTIONS, normalize_plan


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--yes", action="store_true", help="aplica (default: dry-run)")
    args = p.parse_args()

    get_firestore_client()  # falha cedo se credencial/projeto errados

    changes = []
    unknown = []
    for snap in global_collection("tenants").stream():
        data = snap.to_dict() or {}
        current = str(data.get("plan") or "").strip().lower()
        target = normalize_plan(current)
        if current == target:
            continue
        if current and current not in ("starter", "professional", "enterprise", "premium"):
            unknown.append((snap.id, current))
        changes.append((snap.id, current or "(vazio)", target, snap.reference))

    print(f"=== Tenants com plano a migrar: {len(changes)} ===")
    for tid, old, new, _ in changes:
        print(f"  {tid}: {old} -> {new}")
    if unknown:
        print("ATENCAO — valores fora do mapa legado (viraram default professional):")
        for tid, val in unknown:
            print(f"  {tid}: {val!r}")
    if not changes:
        print("Nada a fazer.")
        return 0

    if not args.yes:
        print("\nDRY-RUN. Adicione --yes para aplicar.")
        return 0

    print("\n=== Aplicando ===")
    for tid, _old, new, ref in changes:
        ref.set({"plan": new, "updated_at": utcnow()}, merge=True)
        print(f"  {tid}: plan={new} OK")

    print(f"\n{len(changes)} tenant(s) migrados. Opcoes validas: {', '.join(PLAN_OPTIONS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
