"""Diagnostico rapido de canais e phone_routing em prod.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_channels_prod
"""
import os
from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()

print("=== Canais flat castro_crm_channels (full) ===")
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    print(
        "doc_id={} id={} type={} phone_id={} waba={} platform={} display={} owner_uid={} expires={} created={} updated={} webhook_sub={}".format(
            d.id,
            data.get("id"),
            data.get("channel_type"),
            data.get("phone_number_id"),
            data.get("waba_id"),
            data.get("platform_type"),
            data.get("display_phone_number"),
            data.get("owner_user_id"),
            data.get("token_expires_at"),
            data.get("created_at"),
            data.get("updated_at"),
            data.get("webhook_subscribed"),
        )
    )

print()
print("=== phone_routing flat ===")
for d in c.collection(collection_name("phone_routing")).stream():
    data = d.to_dict() or {}
    print(
        "phone_id={} -> tenant={} channel_id={}".format(
            d.id, data.get("tenant_id"), data.get("channel_id")
        )
    )

print()
print("=== wa_conversations em tenants/hubloc (amostra) ===")
convs = list(
    c.collection(collection_name("tenants"))
    .document("hubloc")
    .collection("wa_conversations")
    .limit(20)
    .stream()
)
print("count_amostra={}".format(len(convs)))
for d in convs[:5]:
    data = d.to_dict() or {}
    print(
        "id={} channel={} wa_id={} last={}".format(
            d.id,
            data.get("channel_id"),
            data.get("wa_id"),
            data.get("last_message_at"),
        )
    )

print()
print("=== wa_messages em tenants/hubloc (count amostra ate 50) ===")
msgs = list(
    c.collection(collection_name("tenants"))
    .document("hubloc")
    .collection("wa_messages")
    .limit(50)
    .stream()
)
print("count_amostra={}".format(len(msgs)))
