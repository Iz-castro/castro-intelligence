"""Apaga wa_conversations e wa_messages cujo channel_id aponta para
um canal que nao existe mais (canal deletado).

Uso:
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._delete_orphan_conversations
  ./.venv/Scripts/python.exe -m scripts._delete_orphan_conversations --confirm
"""
import argparse
import sys

from firestore_common import get_firestore_client, collection_name


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", default="hubloc")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    c = get_firestore_client()
    tenant_root = c.collection(collection_name("tenants")).document(args.tenant_id)

    existing_channel_ids = set()
    for d in c.collection(collection_name("channels")).stream():
        data = d.to_dict() or {}
        existing_channel_ids.add(data.get("id"))
    print(f"Canais existentes (flat): {sorted(existing_channel_ids)}")

    convs_to_delete = []
    msgs_to_delete_by_conv = {}

    for d in tenant_root.collection("wa_conversations").stream():
        data = d.to_dict() or {}
        ch = data.get("channel_id")
        if ch not in existing_channel_ids:
            convs_to_delete.append((d.id, ch, data.get("wa_id")))

    for cid, ch, wa in convs_to_delete:
        msgs = list(
            tenant_root.collection("wa_messages")
            .where("conversation_id", "==", cid)
            .stream()
        )
        if msgs:
            msgs_to_delete_by_conv[cid] = [m.id for m in msgs]

    print()
    print(f"=== Conversations orfas (channel deletado) ===")
    for cid, ch, wa in convs_to_delete:
        n_msgs = len(msgs_to_delete_by_conv.get(cid, []))
        print(f"  conv_id={cid} (channel_id={ch}, wa_id={wa}, msgs={n_msgs})")
    if not convs_to_delete:
        print("  (nenhuma — nada a fazer)")
        return 0

    if not args.confirm:
        print()
        print("DRY-RUN. Adicione --confirm para executar.")
        return 0

    print()
    print("=== Executando ===")
    for cid, _, _ in convs_to_delete:
        for mid in msgs_to_delete_by_conv.get(cid, []):
            tenant_root.collection("wa_messages").document(mid).delete()
        n_msgs = len(msgs_to_delete_by_conv.get(cid, []))
        tenant_root.collection("wa_conversations").document(cid).delete()
        print(f"  deletada conv_id={cid} (+{n_msgs} mensagens)")

    print()
    print("Limpeza concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
