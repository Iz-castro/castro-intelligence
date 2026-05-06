# -*- coding: utf-8 -*-
"""
Wipe controlado de um tenant em ambiente staging/prod (Fase 4).

Uso:
    # Dry-run (default — nada e apagado, so mostra o plano):
    python -m scripts.wipe_all_collections --tenant-id hubloc

    # Wipe completo do tenant (preserva users/departments por default):
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm

    # Wipe total (incluindo users/operator_profiles/departments):
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm --purge-users

    # Wipe tambem os channels flat e phone_routing relacionados ao tenant:
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm --purge-channels

NUNCA apaga:
- Doc raiz tenants/{tid} (preserva nome/plano/billing/settings).
- Colecao tenants flat (lista de tenants).
- _meta global (counters cross-tenant).
- audit_log: por default e preservado tambem (LGPD: trilha de
  auditoria sobrevive ao wipe). Use --purge-audit-log se realmente
  quiser apagar.

Variaveis de ambiente:
    FIRESTORE_PROJECT_ID         (obrigatorio)
    FIRESTORE_COLLECTION_PREFIX  (obrigatorio, default castro_crm em prod)

Confirmacao de seguranca: alem de --confirm, pede que o operador
digite "WIPE" interativamente — protege contra rerun acidental em
shell history ou CI.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Callable

# Permite rodar como `python -m scripts.wipe_all_collections` ou
# `python scripts/wipe_all_collections.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firestore_common import (  # noqa: E402
    collection_name,
    get_firestore_client,
    global_collection,
    tenant_doc_ref,
)


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# Subcolecoes preservadas por default (mesmo com --confirm). User pode
# liberar via flags --purge-users / --purge-audit-log.
DEFAULT_SKIP = frozenset()
USER_PRESERVED = frozenset({"users", "operator_profiles", "departments"})
AUDIT_PRESERVED = frozenset({"audit_log"})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Wipe controlado de um tenant (Fase 4 cutover)."
    )
    p.add_argument(
        "--tenant-id", required=True,
        help="Slug do tenant a apagar (ex: hubloc).",
    )
    p.add_argument(
        "--confirm", action="store_true",
        help="Executa de fato. Sem isso, dry-run.",
    )
    p.add_argument(
        "--purge-users", action="store_true",
        help="Tambem apaga users/operator_profiles/departments. Default: preserva.",
    )
    p.add_argument(
        "--purge-audit-log", action="store_true",
        help="Tambem apaga audit_log. Default: preserva (LGPD).",
    )
    p.add_argument(
        "--purge-channels", action="store_true",
        help="Tambem apaga channels flat + phone_routing entries do tenant.",
    )
    p.add_argument(
        "--no-interactive", action="store_true",
        help="Pula confirmacao interativa 'WIPE' (uso em CI). Cuidado.",
    )
    return p.parse_args()


def discover_tenant_subcollections(tid: str) -> list[str]:
    """Lista subcolecoes que existem em tenants/{tid}/.

    Usa list_subcollections do Admin SDK — retorna apenas as que tem
    pelo menos 1 doc.
    """
    refs = list(tenant_doc_ref(tid).collections())
    return sorted(c.id for c in refs)


def count_docs(ref) -> int:
    """Conta docs em uma colecao. Usa Aggregation (count) quando
    disponivel, senao stream-count."""
    try:
        results = ref.count().get()
        if results and results[0]:
            value = results[0][0].value
            return int(value) if value is not None else 0
    except Exception:
        pass
    return sum(1 for _ in ref.stream())


def recursive_delete_doc(doc_ref) -> int:
    """Apaga um doc + todas suas subcolecoes recursivamente. Retorna
    total de docs apagados (incluindo o proprio doc)."""
    deleted = 0
    for subcol in doc_ref.collections():
        for snap in subcol.stream():
            deleted += recursive_delete_doc(snap.reference)
    doc_ref.delete()
    deleted += 1
    return deleted


def batch_delete_collection(ref, batch_size: int = 200) -> int:
    """Apaga todos os docs de uma colecao em batches. Trata subcolecoes
    nested (recursive). Retorna total."""
    total = 0
    while True:
        batch = list(ref.limit(batch_size).stream())
        if not batch:
            break
        for snap in batch:
            total += recursive_delete_doc(snap.reference)
    return total


def collect_flat_targets(
    tenant_id: str, purge_channels: bool
) -> list[tuple[str, Callable[[dict], bool], str]]:
    """Retorna [(collection_name, predicate, description)] de colecoes flat
    cuja exclusao depende do escopo do tenant."""
    targets: list[tuple[str, Callable[[dict], bool], str]] = []
    if purge_channels:
        # Hoje channels eh single-tenant flat. Quando passar pra
        # subcolecao, este predicate precisa ajustar.
        targets.append((
            "channels",
            lambda d: True,
            "todos os canais (single-tenant flat)",
        ))
        targets.append((
            "phone_routing",
            lambda d: d.get("tenant_id") == tenant_id,
            f"entries de phone_routing apontando pra tenant_id={tenant_id}",
        ))
    return targets


def main() -> int:
    args = parse_args()
    tid = args.tenant_id

    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "<unset>")
    prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "<unset>")

    print(_bold(f"\n=== WIPE TENANT: {tid} ==="))
    print(f"  project={project_id}")
    print(f"  prefix= {prefix}")
    print(f"  modo:   {'CONFIRMED (vai apagar)' if args.confirm else 'DRY-RUN (nada apagado)'}")

    # Verifica que o doc do tenant existe (sanity check)
    tenant_ref = tenant_doc_ref(tid)
    snap = tenant_ref.get()
    if not snap.exists:
        print(_red(f"\n  ✗ tenant '{tid}' nao existe no Firestore"))
        print(_red(f"    path: {prefix}_tenants/{tid}"))
        return 2
    tdata = snap.to_dict() or {}
    print(f"  tenant: name={tdata.get('name')!r} plan={tdata.get('plan')} active={tdata.get('is_active')}")

    skip = set(DEFAULT_SKIP)
    if not args.purge_users:
        skip.update(USER_PRESERVED)
    if not args.purge_audit_log:
        skip.update(AUDIT_PRESERVED)

    subcols = discover_tenant_subcollections(tid)
    flat_targets = collect_flat_targets(tid, args.purge_channels)

    # Plan output
    print(_bold(f"\n=== PLANO ==="))
    print(f"\nSubcolecoes em tenants/{tid}/:")
    if not subcols:
        print(f"  (nenhuma — tenant ja esta vazio)")
    else:
        for sc in subcols:
            ref = tenant_ref.collection(sc)
            n = count_docs(ref)
            marker = _yellow("[SKIP]") if sc in skip else _red("[WIPE]")
            note = ""
            if sc in USER_PRESERVED and not args.purge_users:
                note = "  (use --purge-users)"
            elif sc in AUDIT_PRESERVED and not args.purge_audit_log:
                note = "  (use --purge-audit-log)"
            print(f"  {marker} {sc:30s} {n:6d} docs{note}")

    print(f"\nColecoes flat (escopo {tid}):")
    if not flat_targets:
        print(f"  (nenhuma — use --purge-channels pra incluir channels/phone_routing)")
    else:
        for col_name, predicate, desc in flat_targets:
            try:
                n = sum(
                    1 for snap in global_collection(col_name).stream()
                    if predicate(snap.to_dict() or {})
                )
            except Exception as exc:
                print(f"  [WARN] count em {col_name}: {exc}")
                n = -1
            print(f"  {_red('[WIPE]')} {col_name:30s} {n:6d} docs — {desc}")

    print(f"\nNUNCA apagado:")
    print(f"  - Doc raiz tenants/{tid} (preservado)")
    print(f"  - Colecao tenants flat (preservada)")
    print(f"  - _meta global (preservado)")

    if not args.confirm:
        print(_yellow(_bold("\n[DRY-RUN] Nada foi apagado. Use --confirm para executar.")))
        return 0

    if not args.no_interactive:
        print(_red(_bold(
            f"\n!!! ATENCAO !!!\n"
            f"Esta operacao apaga PERMANENTEMENTE os dados acima do tenant '{tid}'\n"
            f"em {prefix} (project {project_id}). NAO HA UNDO.\n"
        )))
        print("Digite 'WIPE' (em maiusculas, sem aspas) pra confirmar:")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "WIPE":
            print(_yellow("\nCancelado pelo operador."))
            return 1

    # Execute
    print(_bold(f"\n=== EXECUTANDO ==="))
    grand_total = 0
    for sc in subcols:
        if sc in skip:
            continue
        ref = tenant_ref.collection(sc)
        deleted = batch_delete_collection(ref)
        grand_total += deleted
        print(f"  apagado tenants/{tid}/{sc}: {deleted} docs")

    for col_name, predicate, desc in flat_targets:
        deleted = 0
        for snap in global_collection(col_name).stream():
            if predicate(snap.to_dict() or {}):
                snap.reference.delete()
                deleted += 1
        grand_total += deleted
        print(f"  apagado {col_name}: {deleted} docs")

    print(_green(_bold(
        f"\n✓ Wipe completo. Total apagado: {grand_total} docs.\n"
        f"  Tenant doc tenants/{tid} preservado."
    )))
    return 0


if __name__ == "__main__":
    sys.exit(main())
