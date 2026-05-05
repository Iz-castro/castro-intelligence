# -*- coding: utf-8 -*-
"""
E2E test do cenario multi-tenant + sub-threads no staging.

Executa, em sequencia:
  1. Wipe das colecoes do tenant hubloc + canais fake (mantem channel id=1).
  2. Cria 2 canais fictícios (id=100 standard, id=200 coexistence) com
     phone_number_ids unicos.
  3. Aguarda 70s para o cache de canais reciclar no servico Cloud Run.
  4. Dispara 4 webhooks Meta-shape para o staging:
       - canal 100, wa_id X, msg "Oi do Cloud API"
       - canal 200, wa_id X, msg "Oi do coexistence" (mesmo cliente!)
       - canal 100, wa_id X, msg "segunda no Cloud API"
       - canal 200, wa_id Y (cliente diferente), msg "outro cliente"
  5. Le Firestore e valida:
       - 2 contatos (X e Y)
       - 3 conversations: 100__X, 200__X, 200__Y
       - 4 mensagens, cada uma com conversation_id correto
  6. (Cutover Fase 2C) Loga como BOOTSTRAP_ADMIN_EMAIL e exercita
     POST /api/wa/conversation/{id}/read sobre a thread 100__X.
     Valida que unread_count zera so dela; threads 200__X e 200__Y
     mantem unread; mensagens inbound da thread 100 ficam status=read,
     enquanto inbound da 200 permanece received.
  7. (Cutover Fase 2C) POST /api/wa/send com conversation_id inexistente
     espera HTTP 404 — prova que _resolve_send_target rejeita antes da
     chamada Meta (caminho feliz nao testado: tokens dos canais sao fake
     e a Graph API recusaria).
  8. Imprime relatorio.

Uso (local com gcloud auth ja configurado):
    python -m scripts.e2e_test_staging

Variaveis de ambiente necessarias:
    FIRESTORE_PROJECT_ID         (default: project-26fb9c99-8ee9-4179-aef)
    FIRESTORE_COLLECTION_PREFIX  (default: castro_crm_staging)
    STAGING_URL                  (default: castro-crm-staging URL)
    WHATSAPP_APP_SECRET          (lido do GCP Secret Manager se ausente)
    FIREBASE_WEB_API_KEY         (lido do Cloud Run env se ausente)
    BOOTSTRAP_ADMIN_EMAIL        (lido do Cloud Run env se ausente)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

os.environ.setdefault("FIRESTORE_PROJECT_ID", "project-26fb9c99-8ee9-4179-aef")
os.environ.setdefault("FIRESTORE_COLLECTION_PREFIX", "castro_crm_staging")

STAGING_URL = os.environ.get(
    "STAGING_URL",
    "https://castro-crm-staging-286866630844.southamerica-east1.run.app",
)


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# ---------------------------------------------------------------------------
# Secret loader (Cloud Run usa GCP Secret Manager)
# ---------------------------------------------------------------------------

def get_app_secret() -> str:
    """Le WHATSAPP_APP_SECRET do GCP (mesmo do Cloud Run staging)."""
    cached = os.environ.get("WHATSAPP_APP_SECRET")
    if cached:
        return cached
    cmd = [
        "gcloud", "secrets", "versions", "access", "latest",
        "--secret=castro-crm-whatsapp-app-secret",
        "--project", os.environ["FIRESTORE_PROJECT_ID"],
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(f"Falha ao ler secret: {out.stderr}")
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Cloud Run env reader (para FIREBASE_WEB_API_KEY, BOOTSTRAP_ADMIN_EMAIL etc)
# ---------------------------------------------------------------------------

_cloud_run_env_cache: dict[str, str] | None = None


def _read_cloud_run_env() -> dict[str, str]:
    """Le todas as env vars do servico castro-crm-staging via gcloud."""
    global _cloud_run_env_cache
    if _cloud_run_env_cache is not None:
        return _cloud_run_env_cache
    cmd = [
        "gcloud", "run", "services", "describe", "castro-crm-staging",
        "--region", "southamerica-east1",
        "--project", os.environ["FIRESTORE_PROJECT_ID"],
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        _cloud_run_env_cache = {}
        return _cloud_run_env_cache
    try:
        data = json.loads(out.stdout)
        containers = (data.get("spec", {}).get("template", {}).get("spec", {})
                          .get("containers", []) or [])
        env_list = (containers[0].get("env", []) if containers else []) or []
        _cloud_run_env_cache = {e["name"]: e.get("value", "")
                                for e in env_list if "name" in e}
    except Exception:
        _cloud_run_env_cache = {}
    return _cloud_run_env_cache


def get_env_or_cloud_run(name: str) -> str:
    cached = os.environ.get(name, "").strip()
    if cached:
        return cached
    return (_read_cloud_run_env().get(name) or "").strip()


# ---------------------------------------------------------------------------
# Auth helper — admin idToken via Firebase custom token + REST exchange
# ---------------------------------------------------------------------------

_E2E_SIGNER_SA = (
    "castro-crm-run@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com"
)


def mint_admin_id_token() -> tuple[str, str] | None:
    """Retorna (id_token, admin_email) ou None se auth nao pode ser
    estabelecida (skip com warning amarelo nos passos 6-7).

    Cria custom token assinado pela SA do Cloud Run staging (precisa
    iam.serviceAccountTokenCreator no usuario corrente) e troca por
    idToken via REST. Evita BOOTSTRAP_ADMIN_PASSWORD (que nao existe —
    admin loga via Google SSO)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import firebase_admin
    from firebase_admin import auth as fb_auth, credentials as fb_credentials

    api_key = get_env_or_cloud_run("FIREBASE_WEB_API_KEY")
    if not api_key:
        print(_yellow("  [skip] FIREBASE_WEB_API_KEY indisponivel"))
        return None
    admin_email = get_env_or_cloud_run("BOOTSTRAP_ADMIN_EMAIL")
    if not admin_email:
        print(_yellow("  [skip] BOOTSTRAP_ADMIN_EMAIL indisponivel"))
        return None

    try:
        e2e_app = firebase_admin.get_app("e2e_signer")
    except ValueError:
        e2e_app = firebase_admin.initialize_app(
            credential=fb_credentials.ApplicationDefault(),
            options={
                "projectId": os.environ["FIRESTORE_PROJECT_ID"],
                "serviceAccountId": _E2E_SIGNER_SA,
            },
            name="e2e_signer",
        )

    try:
        user = fb_auth.get_user_by_email(admin_email, app=e2e_app)
    except Exception as exc:
        print(_yellow(f"  [skip] get_user_by_email falhou: {exc}"))
        return None
    try:
        custom_token = fb_auth.create_custom_token(
            user.uid,
            developer_claims={"tenant_id": "hubloc"},
            app=e2e_app,
        )
    except Exception as exc:
        print(_yellow(
            f"  [skip] create_custom_token falhou: {exc}\n"
            "         (usuario corrente precisa de roles/iam.serviceAccountTokenCreator "
            f"em {_E2E_SIGNER_SA})"
        ))
        return None
    if isinstance(custom_token, bytes):
        custom_token = custom_token.decode("utf-8")

    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:"
        f"signInWithCustomToken?key={api_key}"
    )
    body = json.dumps({"token": custom_token, "returnSecureToken": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(_yellow(
            f"  [skip] signInWithCustomToken falhou: {e.code} "
            f"{e.read().decode('utf-8', 'ignore')}"
        ))
        return None
    return payload["idToken"], admin_email


def http_post_authed(path: str, id_token: str, body: dict | None = None) -> tuple[int, dict | str]:
    url = STAGING_URL + path
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


# ---------------------------------------------------------------------------
# Firestore helpers (lazy import — depende do path)
# ---------------------------------------------------------------------------

def get_clients():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from firestore_common import (
        _flat_collection,
        _flat_document,
        collection_name,
        get_firestore_client,
        utcnow,
    )
    return {
        "client": get_firestore_client(),
        "flat_coll": _flat_collection,
        "flat_doc": _flat_document,
        "coll_name": collection_name,
        "utcnow": utcnow,
    }


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_wipe(c) -> None:
    print(_bold("\n[1/7] Wipe do tenant hubloc + canais fake"))
    client = c["client"]
    coll_name = c["coll_name"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    counts = {"contacts": 0, "conversations": 0, "messages": 0, "transfer_log": 0, "channels_fake": 0}

    for sub in ("wa_contacts", "wa_conversations", "wa_messages", "wa_transfer_log"):
        for snap in hubloc.collection(sub).stream():
            snap.reference.delete()
            counts[sub.replace("wa_", "")] = counts.get(sub.replace("wa_", ""), 0) + 1

    # Apaga canais fake (id != 1) na coleção flat
    for snap in c["flat_coll"]("channels").stream():
        data = snap.to_dict() or {}
        if data.get("id") != 1:
            snap.reference.delete()
            counts["channels_fake"] += 1

    for k, v in counts.items():
        print(f"  removidos {k}: {v}")
    print(_green("  ✓ wipe completo"))


def step_create_channels(c) -> None:
    print(_bold("\n[2/7] Criando 2 canais ficticios para teste"))
    utcnow = c["utcnow"]
    flat_doc = c["flat_doc"]

    flat_doc("channels", 100).set({
        "id": 100,
        "channel_type": "standard",
        "label": "E2E Cloud API Test",
        "waba_id": "e2e_test_waba_standard",
        "phone_number_id": "e2e_phone_100",
        "display_phone_number": "+55 31 1000-0100",
        "access_token": "FAKE_TOKEN_E2E_100",
        "owner_user_id": None,
        "owner_firebase_uid": "",
        "is_active": True,
        "is_bot_enabled": True,
        "webhook_subscribed": True,
        "platform_type": "CLOUD_API",
        "verified_name": "E2E Standard",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    })
    print(f"  ✓ canal id=100 standard phone_id=e2e_phone_100")

    flat_doc("channels", 200).set({
        "id": 200,
        "channel_type": "coexistence",
        "label": "E2E Coexistence Test",
        "waba_id": "e2e_test_waba_coex",
        "phone_number_id": "e2e_phone_200",
        "display_phone_number": "+55 31 2000-0200",
        "access_token": "FAKE_TOKEN_E2E_200",
        "owner_user_id": None,
        "owner_firebase_uid": "",
        "is_active": True,
        "is_bot_enabled": False,
        "webhook_subscribed": True,
        "platform_type": "WHATSAPP",
        "verified_name": "E2E Coexistence",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    })
    print(f"  ✓ canal id=200 coexistence phone_id=e2e_phone_200")
    print(_green("  ✓ canais criados"))


def step_wait_cache():
    print(_bold("\n[3/7] Aguardando 70s para cache de canais reciclar no Cloud Run"))
    print(f"  cache TTL = 60s; aguardamos um pouco a mais...")
    for remaining in range(70, 0, -10):
        print(f"  {remaining}s...", end="\r")
        time.sleep(10)
    print(_green("  ✓ cache reciclado"))


def post_webhook(secret: str, payload: dict) -> int:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        STAGING_URL + "/webhook",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def make_payload(phone_number_id: str, wa_id: str, profile_name: str, msg_id: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "e2e_test_waba",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "+55310000",
                        "phone_number_id": phone_number_id,
                    },
                    "contacts": [{
                        "profile": {"name": profile_name},
                        "wa_id": wa_id,
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": msg_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
            }],
        }],
    }


def step_send_webhooks(secret: str) -> None:
    print(_bold("\n[4/7] Disparando 4 webhooks Meta-shape"))
    wa_x = "5531777771111"
    wa_y = "5531777772222"

    cases = [
        ("e2e_phone_100", wa_x, "Cliente E2E X", "wamid.e2e_X_std_1", "Oi do Cloud API standard"),
        ("e2e_phone_200", wa_x, "Cliente E2E X", "wamid.e2e_X_coex_1", "Oi do canal coexistence"),
        ("e2e_phone_100", wa_x, "Cliente E2E X", "wamid.e2e_X_std_2", "segunda mensagem no Cloud API"),
        ("e2e_phone_200", wa_y, "Cliente E2E Y", "wamid.e2e_Y_coex_1", "cliente Y, canal coexistence"),
    ]

    for phone_id, wa, name, msg_id, text in cases:
        payload = make_payload(phone_id, wa, name, msg_id, text)
        status = post_webhook(secret, payload)
        ok = status == 200
        marker = _green("✓") if ok else _red("✗")
        print(f"  {marker} {phone_id} <- {wa} ({name}) status={status}")
        if not ok:
            print(_red(f"    payload: {json.dumps(payload)}"))
    print(_green("  ✓ webhooks enviados"))


def step_verify(c) -> int:
    print(_bold("\n[5/7] Verificando estado final dos webhooks no Firestore"))
    coll_name = c["coll_name"]
    client = c["client"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    contacts = list(hubloc.collection("wa_contacts").stream())
    conversations = list(hubloc.collection("wa_conversations").stream())
    messages = list(hubloc.collection("wa_messages").stream())

    contact_ids = {(s.to_dict() or {}).get("wa_id"): (s.to_dict() or {}).get("id") for s in contacts}

    print(f"  contatos:      {len(contacts)} (esperado: 2)")
    for s in contacts:
        d = s.to_dict() or {}
        print(f"    id={d.get('id')} wa_id={d.get('wa_id')} name={d.get('display_name')}")

    print(f"  conversations: {len(conversations)} (esperado: 3)")
    for s in conversations:
        d = s.to_dict() or {}
        print(f"    id={s.id} contact_id={d.get('contact_id')} channel_id={d.get('channel_id')} unread={d.get('unread_count')}")

    print(f"  mensagens:     {len(messages)} (esperado: 4)")
    for s in messages:
        d = s.to_dict() or {}
        print(f"    id={d.get('id')} channel_id={d.get('channel_id')} conversation_id={d.get('conversation_id')} content={(d.get('content') or '')[:50]}")

    # Validacao
    failures = []
    if len(contacts) != 2:
        failures.append(f"contatos esperado=2 obtido={len(contacts)}")
    if len(conversations) != 3:
        failures.append(f"conversations esperado=3 obtido={len(conversations)}")
    if len(messages) != 4:
        failures.append(f"mensagens esperado=4 obtido={len(messages)}")

    # Cada msg deve ter conversation_id no formato {channel_id}__{wa_id}
    for s in messages:
        d = s.to_dict() or {}
        ch = d.get("channel_id")
        contact_id = d.get("contact_id")
        # Buscar wa_id do contato
        wa_id = None
        for w, cid in contact_ids.items():
            if cid == contact_id:
                wa_id = w
                break
        expected_conv = f"{ch}__{wa_id}" if wa_id else None
        if d.get("conversation_id") != expected_conv:
            failures.append(f"msg {d.get('id')} conv_id={d.get('conversation_id')} esperado={expected_conv}")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1

    print(_green("  ✓ TODAS as assercoes passaram"))
    return 0


def _conv_doc(c, conv_id: str):
    coll_name = c["coll_name"]
    client = c["client"]
    return (client.collection(coll_name("tenants")).document("hubloc")
                  .collection("wa_conversations").document(conv_id).get())


def step_post_mark_read(c, id_token: str) -> int:
    """Cutover Fase 2C: POST /api/wa/conversation/{id}/read marca leitura
    de uma thread especifica e nao das outras do mesmo contato."""
    print(_bold("\n[6/7] POST /api/wa/conversation/{id}/read (cutover Fase 2C)"))
    coll_name = c["coll_name"]
    client = c["client"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    target_conv = "100__5531777771111"

    before_target = (_conv_doc(c, target_conv).to_dict() or {}).get("unread_count")
    before_other_x = (_conv_doc(c, "200__5531777771111").to_dict() or {}).get("unread_count")
    before_y = (_conv_doc(c, "200__5531777772222").to_dict() or {}).get("unread_count")
    print(f"  antes: {target_conv}.unread={before_target}, "
          f"200__X.unread={before_other_x}, 200__Y.unread={before_y}")

    status, payload = http_post_authed(f"/api/wa/conversation/{target_conv}/read", id_token)
    if status != 200:
        print(_red(f"  ✗ POST retornou {status}: {payload}"))
        return 1
    print(f"  ✓ POST status=200 payload={payload}")

    after_target = (_conv_doc(c, target_conv).to_dict() or {}).get("unread_count")
    after_other_x = (_conv_doc(c, "200__5531777771111").to_dict() or {}).get("unread_count")
    after_y = (_conv_doc(c, "200__5531777772222").to_dict() or {}).get("unread_count")
    print(f"  depois: {target_conv}.unread={after_target}, "
          f"200__X.unread={after_other_x}, 200__Y.unread={after_y}")

    failures = []
    if after_target != 0:
        failures.append(f"{target_conv}.unread esperado=0 obtido={after_target}")
    if after_other_x != before_other_x:
        failures.append(f"200__X.unread mudou (esperado {before_other_x} estavel, obtido {after_other_x})")
    if after_y != before_y:
        failures.append(f"200__Y.unread mudou (esperado {before_y} estavel, obtido {after_y})")

    # mensagens inbound da thread alvo devem estar status=read; das outras
    # threads do MESMO contato (200__X) devem manter received.
    msgs = list(hubloc.collection("wa_messages").stream())
    for s in msgs:
        d = s.to_dict() or {}
        if d.get("direction") != "inbound":
            continue
        conv = d.get("conversation_id")
        st = d.get("status")
        if conv == target_conv and st != "read":
            failures.append(f"msg {d.get('id')} ({conv}) esperado read, obtido {st}")
        if conv == "200__5531777771111" and st == "read":
            failures.append(f"msg {d.get('id')} ({conv}) virou read sem solicitacao (cross-channel leak!)")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1
    print(_green("  ✓ mark-read isolado por thread"))
    return 0


def step_post_send_validation(c, id_token: str) -> int:
    """Cutover Fase 2C: POST /api/wa/send com conversation_id inexistente
    deve retornar 404, provando que _resolve_send_target rejeita antes de
    chamar Meta. Caminho feliz nao testado (canais fake, tokens fake)."""
    print(_bold("\n[7/7] POST /api/wa/send com conversation_id invalido (cutover Fase 2C)"))

    bad_conv = "9999__inexistente"
    status, payload = http_post_authed(
        "/api/wa/send", id_token,
        {"conversation_id": bad_conv, "content": "ignored"},
    )
    print(f"  POST conversation_id={bad_conv} -> status={status}")
    if status != 404:
        print(_red(f"  ✗ esperado 404, obtido {status}: {payload}"))
        return 1

    # Tambem valida que sem nem conversation_id nem contact_id retorna 4xx
    status2, payload2 = http_post_authed(
        "/api/wa/send", id_token, {"content": "no target"},
    )
    print(f"  POST sem target -> status={status2}")
    if status2 not in (400, 422):
        print(_red(f"  ✗ esperado 400/422, obtido {status2}: {payload2}"))
        return 1

    print(_green("  ✓ _resolve_send_target rejeita antes de chegar em Meta"))
    return 0


def main() -> int:
    print(_bold(f"E2E test against {STAGING_URL}"))
    secret = get_app_secret()
    if not secret:
        print(_red("WHATSAPP_APP_SECRET nao disponivel"))
        return 2

    c = get_clients()
    step_wipe(c)
    step_create_channels(c)
    step_wait_cache()
    step_send_webhooks(secret)
    rc = step_verify(c)
    if rc != 0:
        print(_red(_bold("\n✗ E2E FAILED (passos 1-5)")))
        return rc

    auth = mint_admin_id_token()
    if auth is None:
        print(_yellow(_bold("\n⚠ Passos 6-7 pulados (auth indisponivel) — passos 1-5 OK")))
        print(_green(_bold("\n✓ E2E PASSED (parcial)")))
        return 0
    id_token, admin_email = auth
    print(_bold(f"\nAuth: idToken obtido para {admin_email}"))

    rc6 = step_post_mark_read(c, id_token)
    if rc6 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 6 mark-read)")))
        return rc6

    rc7 = step_post_send_validation(c, id_token)
    if rc7 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 7 send validation)")))
        return rc7

    print(_green(_bold("\n✓ E2E PASSED")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
