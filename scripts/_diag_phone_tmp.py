# -*- coding: utf-8 -*-
"""Diag READ-ONLY: consulta status do numero na Meta Graph API. Token redigido."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx  # noqa: E402
from firestore_common import get_firestore_client, collection_name  # noqa: E402

c = get_firestore_client()
ch = None
for snap in c.collection(collection_name("channels")).stream():
    d = snap.to_dict() or {}
    if str(d.get("channel_type")) == "standard":
        ch = d
        break

if not ch:
    print("Nenhum canal standard encontrado")
    sys.exit(1)

token = ch.get("access_token") or ""
phone_id = str(ch.get("phone_number_id") or "")
print(f"phone_id={phone_id} token={'PRESENTE' if token else 'VAZIO'}")

fields = "status,code_verification_status,name_status,verified_name,quality_rating,platform_type,display_phone_number,account_mode,messaging_limit_tier"
url = f"https://graph.facebook.com/v23.0/{phone_id}"
r = httpx.get(url, params={"fields": fields, "access_token": token}, timeout=30)
print(f"HTTP {r.status_code}")
try:
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except Exception:
    print(r.text[:1000])
