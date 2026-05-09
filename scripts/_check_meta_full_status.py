"""Diagnostico Meta-side completo: WABA + phones + subscribed_apps + app webhook."""
import json
import os
import urllib.error
import urllib.request

from firestore_common import collection_name, get_firestore_client


def graph_get(path, token, params=None):
    qs = "?access_token=" + token
    if params:
        for k, v in params.items():
            qs += "&{}={}".format(k, v)
    url = "https://graph.facebook.com/v22.0/{}{}".format(path, qs)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return {"_error": json.loads(body), "_status": e.code}
        except Exception:
            return {"_error_raw": body, "_status": e.code}


c = get_firestore_client()
channel = None
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    if data.get("channel_type") == "coexistence":
        channel = data
        break

if not channel:
    print("Sem canal coexistence.")
    raise SystemExit(1)

waba = channel["waba_id"]
phone_id = channel["phone_number_id"]
token = channel["access_token"]
print("Canal #{} | WABA={} | phone_id={} | webhook_sub={}".format(
    channel.get("id"), waba, phone_id, channel.get("webhook_subscribed")))
print()

print("=== GET /WABA?fields=id,name,timezone_id,account_review_status ===")
r = graph_get(waba, token, {"fields": "id,name,timezone_id,account_review_status,business_verification_status,country,creation_time"})
print(json.dumps(r, indent=2)[:1000])
print()

print("=== GET /WABA/subscribed_apps ===")
r = graph_get("{}/subscribed_apps".format(waba), token)
print(json.dumps(r, indent=2)[:1500])
print()

print("=== GET /phone_id?fields=... (sem smb_app_data) ===")
r = graph_get(phone_id, token, {
    "fields": "id,display_phone_number,verified_name,platform_type,quality_rating,status,code_verification_status,is_official_business_account,name_status,messaging_limit_tier",
})
print(json.dumps(r, indent=2)[:1500])
print()

# Tentar campos alternativos pra coexistence
print("=== GET /phone_id?fields=throughput,account_mode,certificate ===")
r = graph_get(phone_id, token, {"fields": "throughput,account_mode,certificate,health_status"})
print(json.dumps(r, indent=2)[:800])
print()

# App-level subscriptions (precisa app_token)
app_id = os.getenv("META_APP_ID", "1434723791183375")
app_secret = os.getenv("META_APP_SECRET", "")
if app_secret:
    print("=== GET /APP/subscriptions (com app_access_token) ===")
    app_token = "{}|{}".format(app_id, app_secret)
    r = graph_get("{}/subscriptions".format(app_id), app_token)
    print(json.dumps(r, indent=2)[:2000])
else:
    print("META_APP_SECRET nao no env — pula app subscriptions check.")
