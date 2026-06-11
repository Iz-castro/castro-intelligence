# -*- coding: utf-8 -*-
"""One-off: registra o numero standard na Cloud API. Token redigido."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx  # noqa: E402
from firestore_common import get_firestore_client, collection_name  # noqa: E402

PIN = os.environ.get("WA_REGISTER_PIN", "")
if not PIN or len(PIN) != 6 or not PIN.isdigit():
    raise SystemExit("Defina WA_REGISTER_PIN (6 digitos) no ambiente. PIN nao vai hardcoded (2FA do numero).")
c = get_firestore_client()
TARGET_PHONE_ID = "1118622994671651"  # 3351-7604 (canal id=4); evita os bogus id=2/3
ch = None
for snap in c.collection(collection_name("channels")).stream():
    d = snap.to_dict() or {}
    if str(d.get("phone_number_id")) == TARGET_PHONE_ID:
        ch = d
        break
if ch is None:
    raise SystemExit(f"Canal com phone_id={TARGET_PHONE_ID} nao encontrado")

token = ch.get("access_token") or ""
phone_id = str(ch.get("phone_number_id") or "")
print(f"Registrando phone_id={phone_id} com PIN={PIN}...")

r = httpx.post(
    f"https://graph.facebook.com/v23.0/{phone_id}/register",
    json={"messaging_product": "whatsapp", "pin": PIN},
    params={"access_token": token},
    timeout=60,
)
print(f"HTTP {r.status_code}")
try:
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except Exception:
    print(r.text[:1500])
