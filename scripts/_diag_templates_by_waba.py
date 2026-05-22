"""Diagnostico read-only: lista templates por WABA de cada canal, com status.

Responde "por que o template X nao aparece no canal Y": ou nao esta na WABA
daquele canal, ou esta com status != APPROVED (a UI so mostra APPROVED).

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_templates_by_waba
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from firestore_common import collection_name, get_firestore_client


def graph_get_url(url, token):
    sep = "&" if "?" in url else "?"
    full = "{}{}access_token={}".format(url, sep, urllib.parse.quote(token, safe=""))
    try:
        with urllib.request.urlopen(full, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return None, json.loads(body)
        except Exception:
            return None, {"raw": body, "status": e.code}


def mask_phone(p):
    p = str(p or "")
    return p[:-4].ljust(0) + "****" if len(p) > 4 else "****"


c = get_firestore_client()
channels = []
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    channels.append(data)

channels.sort(key=lambda x: x.get("id") or 0)
print("Canais encontrados: {}".format(len(channels)))
print()

for ch in channels:
    cid = ch.get("id")
    waba = str(ch.get("waba_id") or "").strip()
    token = str(ch.get("access_token") or "").strip()
    ctype = ch.get("channel_type")
    display = mask_phone(ch.get("display_phone_number"))
    active = ch.get("is_active")
    print("=" * 70)
    print("Canal #{} | type={} | active={} | display={} | WABA={}".format(
        cid, ctype, active, display, waba or "(vazio)"))
    if not waba:
        print("  -> sem waba_id, pula.")
        continue
    if not token:
        print("  -> sem access_token, pula.")
        continue

    url = ("https://graph.facebook.com/v22.0/{}/message_templates"
           "?fields=name,language,category,status&limit=100".format(waba))
    rows = []
    err = None
    while url:
        data, err = graph_get_url(url, token)
        if err is not None:
            break
        rows.extend(data.get("data", []) or [])
        url = ((data.get("paging") or {}).get("next"))

    if err is not None:
        print("  -> ERRO Meta: {}".format(json.dumps(err)[:300]))
        continue

    by_status = {}
    for t in rows:
        st = str(t.get("status", "?")).upper()
        by_status.setdefault(st, 0)
        by_status[st] += 1
    print("  total templates={} | por status={}".format(len(rows), by_status))
    for t in sorted(rows, key=lambda x: (str(x.get("status")), str(x.get("name")))):
        print("    [{:<10}] {:<32} lang={:<6} cat={}".format(
            str(t.get("status")), str(t.get("name")),
            str(t.get("language")), str(t.get("category"))))
print("=" * 70)
