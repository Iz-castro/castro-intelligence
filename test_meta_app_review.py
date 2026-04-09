# -*- coding: utf-8 -*-
"""
Script para executar as chamadas de API necessarias para completar
os testes de caso de uso na revisao do app Meta.

Uso:
  python test_meta_app_review.py
  python test_meta_app_review.py --token SEU_TOKEN
  python test_meta_app_review.py --section business_management
  python test_meta_app_review.py --dry-run

Secoes disponiveis:
  business_management, whatsapp_business_management,
  whatsapp_business_messaging, whatsapp_business_manage_events,
  public_profile
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Carrega .env
# ---------------------------------------------------------------------------

def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
APP_ID = os.getenv("META_APP_ID", "")
APP_SECRET = os.getenv("META_APP_SECRET", "")

# Token de usuario temporario (Graph API Explorer) tem mais permissoes
# que o system user token para fins de teste de app review
DEFAULT_TOKEN = os.getenv("authorization_bearer_token_temp", "") or os.getenv("WHATSAPP_TOKEN", "")

# Numero de teste para envio de mensagem (use seu proprio numero)
TEST_PHONE = "5531971957758"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_call(method: str, path: str, token: str, params: dict | None = None,
             body: dict | None = None, label: str = "") -> dict:
    """Faz uma chamada a Graph API e retorna o resultado."""
    url = f"{GRAPH_API_BASE}/{path.lstrip('/')}"

    if method == "GET" and params:
        url += "?" + urlencode({**params, "access_token": token})
    elif method == "GET":
        url += "?" + urlencode({"access_token": token})

    headers = {"Accept": "application/json"}

    data = None
    if method in ("POST", "DELETE") and body is not None:
        merged = {**body, "access_token": token}
        data = json.dumps(merged).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif method in ("POST", "DELETE"):
        data = urlencode({"access_token": token}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw) if raw.strip() else {}
            return {"ok": True, "status": response.status, "body": result}
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_body = json.loads(raw_body)
        except json.JSONDecodeError:
            error_body = raw_body
        return {"ok": False, "status": exc.code, "body": error_body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def print_result(label: str, result: dict) -> None:
    ok = result.get("ok", False)
    status = result.get("status", "?")
    icon = "OK" if ok else "FALHOU"
    print(f"  [{icon}] {label} (HTTP {status})")
    if not ok:
        body = result.get("body", result.get("error", ""))
        if isinstance(body, dict):
            error = body.get("error", {})
            if isinstance(error, dict):
                print(f"         code={error.get('code')} {error.get('message', '')[:120]}")
            else:
                print(f"         {str(body)[:150]}")
        else:
            print(f"         {str(body)[:150]}")


def run_test(label: str, method: str, path: str, token: str,
             params: dict | None = None, body: dict | None = None,
             dry_run: bool = False) -> dict:
    if dry_run:
        print(f"  [DRY] {label}: {method} /{path}")
        return {"ok": True, "dry_run": True}
    result = api_call(method, path, token, params=params, body=body, label=label)
    print_result(label, result)
    return result


# ---------------------------------------------------------------------------
# Secao 1: business_management (0/1 obrigatoria)
# ---------------------------------------------------------------------------

def test_business_management(token: str, dry_run: bool = False) -> None:
    print("\n=== business_management (0/1 obrigatoria) ===\n")

    # Listar businesses do usuario — endpoint principal desta permissao
    run_test("GET /me/businesses", "GET", "me/businesses",
             token, params={"fields": "id,name,created_time"}, dry_run=dry_run)

    # Consultar o app
    run_test("GET /app", "GET", APP_ID,
             token, params={"fields": "id,name,category"}, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 2: whatsapp_business_management
# ---------------------------------------------------------------------------

def test_whatsapp_business_management(token: str, dry_run: bool = False) -> None:
    print("\n=== whatsapp_business_management ===\n")

    # WABA info
    run_test("GET WABA info", "GET", WABA_ID,
             token, params={"fields": "id,name,currency,timezone_id,message_template_namespace"},
             dry_run=dry_run)

    # Phone numbers na WABA
    run_test("GET WABA phone_numbers", "GET", f"{WABA_ID}/phone_numbers",
             token, params={"fields": "id,display_phone_number,verified_name,quality_rating,status,platform_type,code_verification_status,name_status"},
             dry_run=dry_run)

    # Phone number individual
    run_test("GET phone number detail", "GET", PHONE_NUMBER_ID,
             token, params={"fields": "id,display_phone_number,verified_name,quality_rating,status,platform_type,code_verification_status"},
             dry_run=dry_run)

    # Message templates
    run_test("GET message_templates", "GET", f"{WABA_ID}/message_templates",
             token, params={"fields": "id,name,status,language,category,components"},
             dry_run=dry_run)

    # Subscribed apps (verificar inscricao do webhook)
    run_test("GET subscribed_apps", "GET", f"{WABA_ID}/subscribed_apps",
             token, dry_run=dry_run)

    # POST subscribe (idempotente — nao causa problemas)
    run_test("POST subscribed_apps", "POST", f"{WABA_ID}/subscribed_apps",
             token, dry_run=dry_run)

    # Analytics (ultimos 30 dias)
    run_test("GET analytics", "GET", f"{WABA_ID}/analytics",
             token, params={
                 "fields": "phone_numbers,granularity,data_points",
                 "granularity": "DAILY",
                 "start": str(int(time.time()) - 30 * 86400),
                 "end": str(int(time.time())),
             }, dry_run=dry_run)

    # Conversation analytics
    run_test("GET conversation_analytics", "GET", f"{WABA_ID}/conversation_analytics",
             token, params={
                 "granularity": "DAILY",
                 "start": str(int(time.time()) - 30 * 86400),
                 "end": str(int(time.time())),
             }, dry_run=dry_run)

    # Business profile do numero
    run_test("GET business_profile", "GET", f"{PHONE_NUMBER_ID}/whatsapp_business_profile",
             token, params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
             dry_run=dry_run)

    # Commerce settings
    run_test("GET whatsapp_commerce_settings", "GET", f"{PHONE_NUMBER_ID}/whatsapp_commerce_settings",
             token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 3: whatsapp_business_messaging
# ---------------------------------------------------------------------------

def test_whatsapp_business_messaging(token: str, dry_run: bool = False) -> None:
    print("\n=== whatsapp_business_messaging ===\n")

    # Enviar mensagem de texto
    result = run_test("POST send text message", "POST", f"{PHONE_NUMBER_ID}/messages",
             token, body={
                 "messaging_product": "whatsapp",
                 "to": TEST_PHONE,
                 "type": "text",
                 "text": {"body": "Teste de validacao do app Meta - mensagem de texto"}
             }, dry_run=dry_run)

    # Marcar como lida (precisa de um message_id real)
    msg_id = None
    if result.get("ok") and not dry_run:
        messages = result.get("body", {}).get("messages", [])
        if messages:
            msg_id = messages[0].get("id")

    if msg_id:
        run_test("POST mark_as_read", "POST", f"{PHONE_NUMBER_ID}/messages",
                 token, body={
                     "messaging_product": "whatsapp",
                     "status": "read",
                     "message_id": msg_id
                 }, dry_run=dry_run)
    else:
        print("  [SKIP] mark_as_read - sem message_id (precisa de msg inbound recente)")

    # Enviar template (hello_world e um template padrao que existe em todas as WABAs)
    run_test("POST send template message", "POST", f"{PHONE_NUMBER_ID}/messages",
             token, body={
                 "messaging_product": "whatsapp",
                 "to": TEST_PHONE,
                 "type": "template",
                 "template": {
                     "name": "hello_world",
                     "language": {"code": "en_US"}
                 }
             }, dry_run=dry_run)

    # Upload de media (text file simples como teste)
    print("  [INFO] Para teste de media upload, use o Graph API Explorer manualmente")


# ---------------------------------------------------------------------------
# Secao 4: whatsapp_business_manage_events
# ---------------------------------------------------------------------------

def test_whatsapp_business_manage_events(token: str, dry_run: bool = False) -> None:
    print("\n=== whatsapp_business_manage_events ===\n")

    # manage_events precisa de App Access Token (APP_ID|APP_SECRET)
    app_token = f"{APP_ID}|{APP_SECRET}" if APP_ID and APP_SECRET else ""
    if not app_token:
        print("  [SKIP] META_APP_ID ou META_APP_SECRET nao configurado")
        return

    # Listar subscriptions do app (requer app token)
    run_test("GET app subscriptions", "GET", f"{APP_ID}/subscriptions",
             app_token, dry_run=dry_run)

    # Inscrever o app no campo messages (idempotente, requer app token)
    run_test("POST subscribe webhook field", "POST", f"{APP_ID}/subscriptions",
             app_token, body={
                 "object": "whatsapp_business_account",
                 "fields": "messages",
                 "callback_url": "https://castro-crm-286866630844.southamerica-east1.run.app/webhook",
                 "verify_token": "castro-webhook-2026",
             }, dry_run=dry_run)

    # Verificar WABA subscribed_apps (usa user token)
    run_test("GET WABA subscribed_apps", "GET", f"{WABA_ID}/subscribed_apps",
             token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 5: public_profile
# ---------------------------------------------------------------------------

def test_public_profile(token: str, dry_run: bool = False) -> None:
    print("\n=== public_profile ===\n")

    # Perfil do usuario autenticado
    run_test("GET /me", "GET", "me",
             token, params={"fields": "id,name"}, dry_run=dry_run)

    # Perfil com mais campos
    run_test("GET /me (extended)", "GET", "me",
             token, params={"fields": "id,name,email"}, dry_run=dry_run)

    # Accounts (paginas)
    run_test("GET /me/accounts", "GET", "me/accounts",
             token, params={"fields": "id,name,category"}, dry_run=dry_run)

    # Permissions
    run_test("GET /me/permissions", "GET", "me/permissions",
             token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_SECTIONS = {
    "business_management": test_business_management,
    "whatsapp_business_management": test_whatsapp_business_management,
    "whatsapp_business_messaging": test_whatsapp_business_messaging,
    "whatsapp_business_manage_events": test_whatsapp_business_manage_events,
    "public_profile": test_public_profile,
}

def main() -> int:
    parser = argparse.ArgumentParser(description="Testes de caso de uso para app review Meta")
    parser.add_argument("--token", default="", help="Token de acesso (default: authorization_bearer_token_temp do .env)")
    parser.add_argument("--section", default="all", choices=["all", *ALL_SECTIONS.keys()],
                        help="Qual secao testar (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria executado")
    parser.add_argument("--test-phone", default="", help="Numero de telefone para envio de teste")
    args = parser.parse_args()

    token = args.token or DEFAULT_TOKEN
    if not token:
        print("ERRO: Nenhum token disponivel.", file=sys.stderr)
        print("Use --token SEU_TOKEN ou configure authorization_bearer_token_temp no .env", file=sys.stderr)
        return 1

    global TEST_PHONE
    if args.test_phone:
        TEST_PHONE = args.test_phone

    print(f"Graph API: {GRAPH_API_BASE}")
    print(f"App ID: {APP_ID}")
    print(f"WABA ID: {WABA_ID}")
    print(f"Phone ID: {PHONE_NUMBER_ID}")
    print(f"Token: ...{token[-12:]}")
    print(f"Test Phone: {TEST_PHONE}")
    print(f"Dry Run: {args.dry_run}")

    if args.section == "all":
        for name, func in ALL_SECTIONS.items():
            func(token, dry_run=args.dry_run)
    else:
        ALL_SECTIONS[args.section](token, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("Concluido! Verifique no App Dashboard > Testar Casos de Uso")
    print("se as chamadas foram registradas (pode levar ate 24h).")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
