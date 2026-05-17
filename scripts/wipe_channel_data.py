# -*- coding: utf-8 -*-
"""
Wipe cirurgico de dados de UM canal especifico de um tenant.

Apaga `wa_contacts`, `wa_conversations` e `wa_messages` que tenham
`channel_id == <id>` na subcolecao `tenants/{tid}/`. Util pra desfazer
um onboarding coex de teste mantendo os outros canais intactos.

NUNCA apaga:
  - O doc do canal em si (`castro_crm_channels/{id}`).
    Use `DELETE /api/admin/channels/{id}` no backend (soft-delete que
    preserva audit + libera o phone_routing). Pra hard-delete do canal,
    apague manualmente no console depois.
  - audit_log (LGPD: trilha sobrevive).
  - Qualquer doc de outros canais (filtro estrito por channel_id).

Uso:
    # Dry-run (default — so mostra o plano):
    python -m scripts.wipe_channel_data --tenant-id hubloc --channel-id 1

    # Executa de fato:
    python -m scripts.wipe_channel_data --tenant-id hubloc --channel-id 1 --confirm

Variaveis de ambiente:
    FIRESTORE_PROJECT_ID         (obrigatorio)
    FIRESTORE_COLLECTION_PREFIX  (obrigatorio em prod, default castro_crm)

Confirmacao: alem de --confirm, pede que o operador digite "WIPE"
interativamente. LGPD: registra entrada CHANNEL_DATA_WIPE em audit_log
do tenant com contagens por colecao.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402

from firestore_common import (  # noqa: E402
    collection_name,
    get_firestore_client,
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


# Coletas alvo (subcolecao do tenant). Ordem importa: folha -> raiz.
TARGET_COLLECTIONS = ("wa_messages", "wa_conversations", "wa_contacts")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Wipe cirurgico de dados de um canal (LGPD)."
    )
    p.add_argument("--tenant-id", required=True, help="Slug do tenant (ex: hubloc).")
    p.add_argument("--channel-id", required=True, type=int, help="ID inteiro do canal.")
    p.add_argument("--confirm", action="store_true", help="Executa de fato. Sem isso, dry-run.")
    p.add_argument("--no-interactive", action="store_true", help="Pula confirmacao 'WIPE'. Cuidado.")
    p.add_argument("--operator", default="script:wipe_channel_data", help="Identificador do operador no audit_log.")
    return p.parse_args()


def query_by_channel(tenant_ref, subcol_name: str, channel_id: int):
    """Retorna iterator de snapshots em tenants/{tid}/{subcol} com channel_id == X.

    Tolera channel_id armazenado como int OU string (defesa contra
    documentos legados). Faz 2 queries e une.
    """
    ref = tenant_ref.collection(subcol_name)
    seen: set[str] = set()
    for value in (channel_id, str(channel_id)):
        query = ref.where(filter=FieldFilter("channel_id", "==", value))
        for snap in query.stream():
            if snap.id not in seen:
                seen.add(snap.id)
                yield snap


def count_by_channel(tenant_ref, subcol_name: str, channel_id: int) -> int:
    return sum(1 for _ in query_by_channel(tenant_ref, subcol_name, channel_id))


def delete_by_channel(tenant_ref, subcol_name: str, channel_id: int) -> int:
    """Apaga em batches de 200. Retorna total apagado."""
    client = get_firestore_client()
    total = 0
    pending: list = []
    for snap in query_by_channel(tenant_ref, subcol_name, channel_id):
        pending.append(snap.reference)
        if len(pending) >= 200:
            batch = client.batch()
            for ref in pending:
                batch.delete(ref)
            batch.commit()
            total += len(pending)
            pending = []
    if pending:
        batch = client.batch()
        for ref in pending:
            batch.delete(ref)
        batch.commit()
        total += len(pending)
    return total


def write_audit_entry(tenant_ref, channel_id: int, operator: str, counts: dict[str, int]) -> None:
    """Registra CHANNEL_DATA_WIPE em tenants/{tid}/audit_log."""
    audit_col = tenant_ref.collection("audit_log")
    audit_col.add({
        "user_id": operator,
        "action": "CHANNEL_DATA_WIPE",
        "details": (
            f"channel_id={channel_id} "
            f"contacts={counts.get('wa_contacts', 0)} "
            f"conversations={counts.get('wa_conversations', 0)} "
            f"messages={counts.get('wa_messages', 0)}"
        ),
        "created_at": datetime.now(timezone.utc),
    })


def main() -> int:
    args = parse_args()
    tid = args.tenant_id
    cid = args.channel_id

    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "<unset>")
    prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "<unset>")

    print(_bold(f"\n=== WIPE CHANNEL DATA: tenant={tid} channel_id={cid} ==="))
    print(f"  project={project_id}")
    print(f"  prefix= {prefix}")
    print(f"  modo:   {'CONFIRMED (vai apagar)' if args.confirm else 'DRY-RUN (nada apagado)'}")

    tenant_ref = tenant_doc_ref(tid)
    snap = tenant_ref.get()
    if not snap.exists:
        print(_red(f"\n  X tenant '{tid}' nao existe no Firestore"))
        print(_red(f"    path: {prefix}_tenants/{tid}"))
        return 2
    tdata = snap.to_dict() or {}
    print(f"  tenant: name={tdata.get('name')!r} plan={tdata.get('plan')} active={tdata.get('is_active')}")

    # Sanity check: o canal existe na coleção flat?
    chan_ref = get_firestore_client().collection(collection_name("channels")).document(str(cid))
    chan_snap = chan_ref.get()
    if not chan_snap.exists:
        print(_yellow(f"\n  ! canal id={cid} nao existe em {collection_name('channels')}"))
        print(_yellow(f"    (segue mesmo assim — vai apagar dados orfaos se houver)"))
    else:
        cdata = chan_snap.to_dict() or {}
        print(
            f"  canal:  label={cdata.get('label')!r} "
            f"phone_e164={cdata.get('phone_e164')!r} "
            f"type={cdata.get('channel_type')!r} "
            f"active={cdata.get('is_active')}"
        )

    # Plano
    print(_bold(f"\n=== PLANO ==="))
    counts: dict[str, int] = {}
    for subcol in TARGET_COLLECTIONS:
        n = count_by_channel(tenant_ref, subcol, cid)
        counts[subcol] = n
        print(f"  {_red('[WIPE]')} tenants/{tid}/{subcol:20s} {n:6d} docs (channel_id={cid})")

    print(f"\nNUNCA apagado:")
    print(f"  - {collection_name('channels')}/{cid} (canal preservado)")
    print(f"  - tenants/{tid}/audit_log (LGPD)")
    print(f"  - Qualquer doc com channel_id != {cid}")

    grand_plan = sum(counts.values())
    if grand_plan == 0:
        print(_yellow(_bold(
            f"\n  Nada a apagar — nenhum doc encontrado com channel_id={cid}."
        )))
        return 0

    if not args.confirm:
        print(_yellow(_bold(f"\n[DRY-RUN] {grand_plan} docs seriam apagados. Use --confirm.")))
        return 0

    if not args.no_interactive:
        print(_red(_bold(
            f"\n!!! ATENCAO !!!\n"
            f"Esta operacao apaga PERMANENTEMENTE {grand_plan} docs do canal id={cid}\n"
            f"no tenant '{tid}' em {prefix} (project {project_id}). NAO HA UNDO.\n"
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
    deleted_counts: dict[str, int] = {}
    for subcol in TARGET_COLLECTIONS:
        deleted = delete_by_channel(tenant_ref, subcol, cid)
        deleted_counts[subcol] = deleted
        print(f"  apagado tenants/{tid}/{subcol}: {deleted} docs")

    # Audit log (LGPD: justificativa rastreavel)
    try:
        write_audit_entry(tenant_ref, cid, args.operator, deleted_counts)
        print(f"  audit_log: entrada CHANNEL_DATA_WIPE registrada")
    except Exception as exc:
        print(_yellow(f"  ! falha ao registrar audit_log: {exc}"))

    grand_total = sum(deleted_counts.values())
    print(_green(_bold(
        f"\nOK Wipe completo. Total apagado: {grand_total} docs.\n"
        f"   Canal {collection_name('channels')}/{cid} preservado."
    )))
    return 0


if __name__ == "__main__":
    sys.exit(main())
