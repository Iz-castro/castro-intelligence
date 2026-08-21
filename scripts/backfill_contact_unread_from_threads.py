# -*- coding: utf-8 -*-
"""Backfill: wa_contacts.unread_count := soma(unread_count das wa_conversations do contato).

Contexto (2026-08-21): desde a Fase 2C o frontend marca leitura POR THREAD
(POST /api/wa/conversation/{id}/read), que zerava so a conversation; o contador
do CONTATO so subia (todo inbound +1) e nunca descia. Beep/alarme do frontend
liam esse campo -> alarme perpetuo (hubloc: 1.691 contatos presos). O codigo
novo recalcula o contato a cada read; este script corrige o estoque antigo.

Uso (na raiz do repo, com ADC do projeto de prod):
  set FIRESTORE_PROJECT_ID=project-4a851bf9-f475-418c-800
  set FIRESTORE_COLLECTION_PREFIX=castro_crm
  .venv\Scripts\python.exe -m scripts.backfill_contact_unread_from_threads --tenant hubloc            (dry-run)
  .venv\Scripts\python.exe -m scripts.backfill_contact_unread_from_threads --tenant hubloc --apply

- Idempotente (rodar 2x da o mesmo resultado). Reversivel: grava
  scripts/_backfill_undo_unread_<tenant>_<stamp>.json com {contact_id: valor_antigo}.
- So toca docs cujo valor DIFERE da soma. Nunca imprime nome/telefone.
- Custo: 1 query por contato com unread>0 (+1 write quando muda).
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402

from firestore_common import collection_name, get_firestore_client  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--apply", action="store_true", help="grava (default: dry-run)")
    ap.add_argument("--include-archived", action="store_true", help="tambem is_archived != 0 (default: so ativos)")
    args = ap.parse_args()

    project = os.environ.get("FIRESTORE_PROJECT_ID", "")
    if not project:
        print("ERRO: defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX).")
        sys.exit(2)
    client = get_firestore_client()
    base = client.collection(collection_name("tenants")).document(args.tenant)
    if not base.get().exists:
        print(f"ERRO: tenant '{args.tenant}' nao existe em {project}/{collection_name('tenants')}")
        sys.exit(2)
    print(f"project={client.project} tenant={args.tenant} modo={'APPLY' if args.apply else 'DRY-RUN'}")

    contacts = base.collection("wa_contacts")
    convs = base.collection("wa_conversations")

    rows = []  # (contact_id, doc_ref, old, new)
    skipped_archived = 0
    # Materializa a lista ANTES do loop: o cursor do stream expira (DEADLINE
    # EXCEEDED ~60s) se ficar aberto enquanto rodam as N queries internas.
    pending = [(snap.reference, snap.to_dict() or {})
               for snap in contacts.where(filter=FieldFilter("unread_count", ">", 0)).stream()]
    for ref, data in pending:
        if not args.include_archived and data.get("is_archived") not in (0, None):
            skipped_archived += 1
            continue
        cid = data.get("id")
        try:
            cid_int = int(cid)
        except (TypeError, ValueError):
            continue
        total = 0
        for cs in convs.where(filter=FieldFilter("contact_id", "==", cid_int)).stream():
            total += int((cs.to_dict() or {}).get("unread_count", 0) or 0)
        old = int(data.get("unread_count", 0) or 0)
        if total != old:
            rows.append((cid_int, ref, old, total))

    print(f" contatos com unread_count>0 avaliados: {len(rows) + skipped_archived} (arquivados pulados: {skipped_archived})")
    print(f" a corrigir (contato != soma das threads): {len(rows)}")
    dist_new = Counter(r[3] for r in rows)
    print(f" distribuicao do valor NOVO: {dict(sorted(dist_new.items()))}")
    dist_old = Counter(min(r[2], 10) for r in rows)
    print(f" distribuicao do valor ANTIGO (10=10+): {dict(sorted(dist_old.items()))}")
    if rows:
        sample = sorted(rows, key=lambda r: -r[2])[:5]
        print(" maiores antigos (id, antigo -> novo): " + ", ".join(f"{r[0]}:{r[2]}->{r[3]}" for r in sample))

    if not args.apply:
        print(" DRY-RUN: nada gravado. Rode com --apply para corrigir.")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    undo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_backfill_undo_unread_{args.tenant}_{stamp}.json")
    with open(undo_path, "w", encoding="utf-8") as fh:
        json.dump({"tenant": args.tenant, "project": client.project, "field": "unread_count",
                   "old_values": {str(r[0]): r[2] for r in rows}}, fh, indent=1)
    print(f" undo salvo em {undo_path}")

    batch = client.batch()
    n = 0
    written = 0
    for _cid, ref, _old, new in rows:
        batch.set(ref, {"unread_count": new}, merge=True)
        n += 1
        if n >= 400:
            batch.commit(); written += n; batch = client.batch(); n = 0
    if n:
        batch.commit(); written += n
    print(f" gravados: {written}")

    # Conferencia: nenhum contato ativo deve divergir agora.
    left = 0
    remaining = [snap.to_dict() or {} for snap in contacts.where(filter=FieldFilter("unread_count", ">", 0)).stream()]
    for data in remaining:
        if not args.include_archived and data.get("is_archived") not in (0, None):
            continue
        total = sum(int((cs.to_dict() or {}).get("unread_count", 0) or 0)
                    for cs in convs.where(filter=FieldFilter("contact_id", "==", int(data.get("id")))).stream())
        if total != int(data.get("unread_count", 0) or 0):
            left += 1
    print(f" divergentes apos backfill: {left}  -> {'OK' if left == 0 else '!! CONFERIR'}")


if __name__ == "__main__":
    main()
