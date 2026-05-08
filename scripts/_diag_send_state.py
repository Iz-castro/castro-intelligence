"""Diagnostico do estado pra debug do send error."""
import os
from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()
hub = c.collection(collection_name("tenants")).document("hubloc")

print("=== contact wa_id=5531983440484 ===")
for d in hub.collection("wa_contacts").where("wa_id", "==", "5531983440484").stream():
    data = d.to_dict() or {}
    keys = ["id", "channel_id", "phone_number_id", "wa_id",
            "display_name", "source_channel_type"]
    for k in keys:
        print("  {}={}".format(k, data.get(k)))

print()
print("=== conversations wa_id=5531983440484 ===")
for d in hub.collection("wa_conversations").where("wa_id", "==", "5531983440484").stream():
    data = d.to_dict() or {}
    print("  conv_id={} contact={} channel={} phone={} src={}".format(
        d.id,
        data.get("contact_id"),
        data.get("channel_id"),
        data.get("phone_number_id"),
        data.get("source_channel_type"),
    ))

print()
print("=== _meta counters global ===")
doc = c.collection("castro_crm__meta").document("counters").get()
print("  {}".format(doc.to_dict()))
