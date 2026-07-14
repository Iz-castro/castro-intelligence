# -*- coding: utf-8 -*-
"""Registra um numero standard na Cloud API (2FA/PIN) e opcionalmente
assina o app na WABA (subscribed_apps). Generalizacao do _register_tmp.py.

Pre-requisito: o canal ja existe no CRM (POST /api/admin/channels) com
access_token preenchido — o token do CANAL e usado nas chamadas.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "<projeto CRM>"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  $env:WA_REGISTER_PIN = "123456"   # PIN 2FA do numero (nunca hardcoded)
  ./.venv/Scripts/python.exe -m scripts.register_phone --phone-id <id>            # dry-run
  ./.venv/Scripts/python.exe -m scripts.register_phone --phone-id <id> --yes
  ./.venv/Scripts/python.exe -m scripts.register_phone --phone-id <id> --subscribe-waba --yes
"""
import argparse
import json
import os
import sys

import httpx

from config import GRAPH_API_BASE
from firestore_common import get_firestore_client, collection_name

# Campos de webhook que um canal standard precisa (mesma lista do fluxo
# Embedded Signup standard em main.py).
_STANDARD_SUBSCRIBED_FIELDS = [
    "messages",
    "message_template_status_update",
    "message_template_quality_update",
    "account_update",
]


def _find_channel(phone_id: str) -> dict | None:
    c = get_firestore_client()
    for snap in c.collection(collection_name("channels")).stream():
        d = snap.to_dict() or {}
        if str(d.get("phone_number_id")) == phone_id:
            return d
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--phone-id", required=True, help="phone_number_id da Meta")
    p.add_argument("--subscribe-waba", action="store_true",
                   help="tambem faz POST /{waba_id}/subscribed_apps")
    p.add_argument("--yes", action="store_true", help="executa (default: dry-run)")
    args = p.parse_args()

    pin = os.environ.get("WA_REGISTER_PIN", "")
    if not pin or len(pin) != 6 or not pin.isdigit():
        print("Defina WA_REGISTER_PIN (6 digitos) no ambiente. PIN nao vai hardcoded.")
        return 1

    ch = _find_channel(args.phone_id)
    if ch is None:
        print(f"Canal com phone_id={args.phone_id} nao encontrado no CRM. "
              "Crie antes via POST /api/admin/channels.")
        return 1

    token = str(ch.get("access_token") or "").strip()
    waba_id = str(ch.get("waba_id") or "").strip()
    if not token:
        print(f"Canal {ch.get('id')} sem access_token — preencha no canal primeiro.")
        return 1

    print(f"Canal: id={ch.get('id')} tenant={ch.get('tenant_id')} "
          f"type={ch.get('channel_type')} phone_id={args.phone_id} waba={waba_id or '?'}")
    print(f"Plano: 1) POST /{args.phone_id}/register (PIN)"
          + (f"  2) POST /{waba_id}/subscribed_apps" if args.subscribe_waba else ""))

    if not args.yes:
        print("\nDRY-RUN. Adicione --yes para executar.")
        return 0

    r = httpx.post(
        f"{GRAPH_API_BASE}/{args.phone_id}/register",
        json={"messaging_product": "whatsapp", "pin": pin},
        params={"access_token": token},
        timeout=60,
    )
    print(f"register -> HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text[:1500])
    if r.status_code >= 400:
        return 1

    if args.subscribe_waba:
        if not waba_id:
            print("Canal sem waba_id — nao da pra assinar o app. Preencha no canal.")
            return 1
        r2 = httpx.post(
            f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps",
            json={"subscribed_fields": _STANDARD_SUBSCRIBED_FIELDS},
            params={"access_token": token},
            timeout=60,
        )
        print(f"subscribed_apps -> HTTP {r2.status_code}")
        try:
            print(json.dumps(r2.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r2.text[:1500])
        if r2.status_code >= 400:
            return 1

    print("\nConcluido. Valide mandando uma mensagem pro numero e conferindo o /webhook.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
