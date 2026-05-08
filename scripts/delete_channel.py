"""Deleta um canal flat e limpa entries do phone_routing apontando pra ele.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"  # ou "castro_crm_staging"
  ./.venv/Scripts/python.exe -m scripts.delete_channel --channel-id 1

Sem --confirm e que mostra o plano (dry-run). Com --confirm executa.
"""
import argparse
import sys

from firestore_common import get_firestore_client, collection_name


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int, required=True)
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    cid = args.channel_id
    c = get_firestore_client()

    ch_ref = c.collection(collection_name("channels")).document(str(cid))
    ch_doc = ch_ref.get()
    if not ch_doc.exists:
        print(f"Canal {cid} nao existe.")
        return 1

    ch_data = ch_doc.to_dict() or {}
    print("=== Canal a deletar ===")
    print(f"  doc_id={ch_doc.id}")
    print(f"  type={ch_data.get('channel_type')}")
    print(f"  phone_id={ch_data.get('phone_number_id')}")
    print(f"  waba={ch_data.get('waba_id')}")
    print(f"  display={ch_data.get('display_phone_number')}")
    print(f"  label={ch_data.get('label')}")

    routing_to_delete = []
    for d in c.collection(collection_name("phone_routing")).stream():
        data = d.to_dict() or {}
        if data.get("channel_id") == cid:
            routing_to_delete.append(d.id)

    print()
    print(f"=== phone_routing entries apontando pra channel_id={cid} ===")
    for pid in routing_to_delete:
        print(f"  {pid}")
    if not routing_to_delete:
        print("  (nenhuma)")

    if not args.confirm:
        print()
        print("DRY-RUN. Adicione --confirm para executar.")
        return 0

    print()
    print("=== Executando ===")
    for pid in routing_to_delete:
        c.collection(collection_name("phone_routing")).document(pid).delete()
        print(f"  phone_routing/{pid} deletado")

    ch_ref.delete()
    print(f"  channels/{cid} deletado")

    print()
    print("Pronto. Reinicie o backend (ou aguarde o cache TTL ~60s) "
          "para refletir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
