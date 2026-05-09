"""Verifica via Graph API se o app esta subscrito na WABA."""
import os
import urllib.request
import urllib.error
import json

from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()

channel = None
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    if data.get("channel_type") == "coexistence":
        channel = data
        break

if not channel:
    print("Nenhum canal coexistence encontrado.")
    raise SystemExit(1)

waba_id = channel.get("waba_id")
token = channel.get("access_token")
print("WABA: {} (canal #{})".format(waba_id, channel.get("id")))

url = "https://graph.facebook.com/v22.0/{}/subscribed_apps?fields=whatsapp_business_api_data,subscribed_fields,override_callback_uri&access_token={}".format(waba_id, token)
try:
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        apps = data.get("data", [])
        print("Apps subscribed: {}".format(len(apps)))
        for app in apps:
            wa_app = app.get("whatsapp_business_api_data", {})
            print("  app_id={} link={} fields={}".format(
                wa_app.get("id"),
                wa_app.get("link"),
                app.get("subscribed_fields") or app.get("override_callback_uri"),
            ))
            print("  full_app: {}".format(json.dumps(app, indent=2)[:600]))
except urllib.error.HTTPError as e:
    print("HTTP {}".format(e.code))
    err_body = e.read().decode("utf-8", errors="replace")
    print("  body: {}".format(err_body[:400]))
except Exception as e:
    print("Erro: {}".format(e))
