# -*- coding: utf-8 -*-
"""Higiene do rating pre-v2: limpa carimbos rating_requested_at orfaos e a
nota falso-positivo do contato 193 (varizemed).

Contexto (recibo v2, 2026-09-01): antes do v2, marcar "convertido" carimbava
rating_requested_at ANTES do envio do template — que nao existia (#132001) —
entao ~21 contatos ficaram com "pedido pendente" sem pedido nenhum (varizemed
16 + hubloc 5). No v2 esses carimbos sao INERTES (>7d nao bloqueia re-pergunta;
>48h nao captura clique), entao isto e so higiene de dados. Ja a nota do
contato 193 (varizemed, nota 2 em 2026-08-20) e um falso positivo real do
digito engolido e APARECE no dashboard novo (rating>0) — essa vale limpar.

Dry-run por default; so escreve com --apply. Grava undo JSON antes de
escrever; --undo <arquivo> --apply restaura.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.cleanup_rating_stamps --tenant varizemed
  ./.venv/Scripts/python.exe -m scripts.cleanup_rating_stamps --tenant varizemed --clear-rating-contact 193 --apply
  ./.venv/Scripts/python.exe -m scripts.cleanup_rating_stamps --tenant hubloc --apply
"""
import argparse
import json
import os
import sys
import time

from google.cloud import firestore

from firestore_common import collection, tenant_context  # noqa: E402

RATING_FIELDS = ("rating", "rating_label", "rating_received_at")


def main():
    ap = argparse.ArgumentParser(description="Limpa carimbos de rating pre-v2")
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--apply", action="store_true", help="escreve de verdade (default: dry-run)")
    ap.add_argument("--clear-rating-contact", type=int, default=None,
                    help="alem dos carimbos, zera rating/rating_label/rating_received_at deste contato (ex.: 193)")
    ap.add_argument("--undo", default=None, help="arquivo de undo gerado por uma execucao anterior")
    args = ap.parse_args()

    if not os.environ.get("FIRESTORE_PROJECT_ID"):
        print("FATAL: defina FIRESTORE_PROJECT_ID explicitamente (gcloud config aponta pro projeto errado)")
        sys.exit(1)

    with tenant_context(args.tenant):
        if args.undo:
            _run_undo(args)
            return

        # Carimbo orfao = rating_requested_at presente e rating ausente.
        # Igualdade nao serve (valor variavel) -> desigualdade em campo unico
        # (string ISO), indice automatico; filtro do rating em Python.
        candidates = []
        for snap in collection("wa_contacts").where("rating_requested_at", ">", "").stream():
            data = snap.to_dict() or {}
            if data.get("rating") is None:
                candidates.append({"doc_id": snap.id,
                                   "rating_requested_at": data.get("rating_requested_at")})

        print("Tenant {}: {} contato(s) com carimbo orfao de rating_requested_at".format(
            args.tenant, len(candidates)))
        for c in candidates:
            print("  contato {} | carimbo {}".format(c["doc_id"], c["rating_requested_at"]))

        clear_target = None
        if args.clear_rating_contact is not None:
            ref = collection("wa_contacts").document(str(args.clear_rating_contact))
            doc = ref.get()
            if not doc.exists:
                print("FATAL: contato {} nao existe no tenant {}".format(
                    args.clear_rating_contact, args.tenant))
                sys.exit(1)
            data = doc.to_dict() or {}
            clear_target = {"doc_id": str(args.clear_rating_contact),
                            **{f: data.get(f) for f in RATING_FIELDS},
                            "rating_requested_at": data.get("rating_requested_at")}
            print("Contato {}: rating={} label={} received={} (sera zerado)".format(
                args.clear_rating_contact, data.get("rating"),
                data.get("rating_label"), data.get("rating_received_at")))

        if not args.apply:
            print("\nDRY-RUN — nada escrito. Repita com --apply.")
            return

        undo = {"tenant": args.tenant, "stamps": candidates, "cleared_contact": clear_target}
        undo_path = os.path.join(
            os.path.dirname(__file__),
            "_cleanup_rating_undo_{}_{}.json".format(args.tenant, time.strftime("%Y%m%d_%H%M%S")))
        with open(undo_path, "w", encoding="utf-8") as fh:
            json.dump(undo, fh, ensure_ascii=False, indent=2, default=str)
        print("\nUndo salvo em {}".format(undo_path))

        for c in candidates:
            collection("wa_contacts").document(c["doc_id"]).set(
                {"rating_requested_at": firestore.DELETE_FIELD}, merge=True)
        if clear_target:
            collection("wa_contacts").document(clear_target["doc_id"]).set(
                {f: firestore.DELETE_FIELD for f in (*RATING_FIELDS, "rating_requested_at")},
                merge=True)
        print("OK: {} carimbo(s) removido(s){}".format(
            len(candidates),
            " + rating do contato {} zerado".format(clear_target["doc_id"]) if clear_target else ""))


def _run_undo(args):
    with open(args.undo, "r", encoding="utf-8") as fh:
        undo = json.load(fh)
    if undo.get("tenant") != args.tenant:
        print("FATAL: undo e do tenant {}, nao {}".format(undo.get("tenant"), args.tenant))
        sys.exit(1)
    if not args.apply:
        print("DRY-RUN do undo: {} carimbo(s) + cleared={} seriam restaurados. Use --apply.".format(
            len(undo.get("stamps") or []), bool(undo.get("cleared_contact"))))
        return
    for c in undo.get("stamps") or []:
        collection("wa_contacts").document(c["doc_id"]).set(
            {"rating_requested_at": c["rating_requested_at"]}, merge=True)
    ct = undo.get("cleared_contact")
    if ct:
        restore = {f: ct.get(f) for f in (*RATING_FIELDS, "rating_requested_at") if ct.get(f) is not None}
        if restore:
            collection("wa_contacts").document(ct["doc_id"]).set(restore, merge=True)
    print("Undo aplicado.")


if __name__ == "__main__":
    main()
