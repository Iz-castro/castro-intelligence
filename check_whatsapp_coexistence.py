# -*- coding: utf-8 -*-
"""
Diagnostico rapido do provisionamento WhatsApp / Meta em cenarios de coexistence.

Uso comum:
  python check_whatsapp_coexistence.py
  python check_whatsapp_coexistence.py --token-source gcloud-secret --gcloud-project <project-id>
  python check_whatsapp_coexistence.py --token-source both --gcloud-project <project-id>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent


def load_local_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(BASE_DIR / ".env")

from config import (
    FIRESTORE_PROJECT_ID,
    GRAPH_API_BASE,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_WABA_ID,
)

STATUS_FIELDS = (
    "id,display_phone_number,verified_name,quality_rating,"
    "code_verification_status,name_status,status,platform_type"
)
DEFAULT_SECRET_NAME = "castro-crm-whatsapp-token"


@dataclass
class TokenResolution:
    label: str
    token: str
    details: str
    phone_id: str
    waba_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida token, WABA e numero configurados para a integracao WhatsApp/Meta."
    )
    parser.add_argument(
        "--token-source",
        choices=("env", "gcloud-secret", "both"),
        default="env",
        help="Origem do token de acesso da Meta.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Token explicito. Quando informado, substitui o token vindo do ambiente.",
    )
    parser.add_argument(
        "--token-secret",
        default=DEFAULT_SECRET_NAME,
        help="Nome do secret no Secret Manager quando --token-source=gcloud-secret.",
    )
    parser.add_argument(
        "--gcloud-project",
        default=FIRESTORE_PROJECT_ID,
        help="Project ID usado para ler o Secret Manager.",
    )
    parser.add_argument(
        "--phone-id",
        default="",
        help="Phone Number ID da Meta. Quando omitido, o script tenta descobrir a origem correta.",
    )
    parser.add_argument(
        "--waba-id",
        default="",
        help="WhatsApp Business Account ID. Quando omitido, o script tenta descobrir a origem correta.",
    )
    parser.add_argument(
        "--graph-api-base",
        default=GRAPH_API_BASE,
        help="Base da Graph API. Ex.: https://graph.facebook.com/v22.0",
    )
    parser.add_argument(
        "--cloud-run-service",
        default="castro-crm",
        help="Servico Cloud Run usado para descobrir os IDs de producao.",
    )
    parser.add_argument(
        "--cloud-run-region",
        default="southamerica-east1",
        help="Regiao do servico Cloud Run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime o resultado em JSON.",
    )
    return parser.parse_args()


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def get_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message", "erro sem mensagem")
            return f"code={code} message={message}"
    if payload is None:
        return "erro desconhecido"
    return str(payload)


def fetch_graph(path: str, token: str, base_url: str, fields: str | None = None) -> dict[str, Any]:
    query = {"access_token": token}
    if fields:
        query["fields"] = fields

    url = f"{normalize_base_url(base_url)}/{path.lstrip('/')}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "status": response.status, "body": body}
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body
        return {"ok": False, "status": exc.code, "body": body}
    except Exception as exc:  # pragma: no cover - depende do ambiente
        return {"ok": False, "error": str(exc)}


def resolve_env_token(
    explicit_token: str,
    phone_id_override: str = "",
    waba_id_override: str = "",
) -> TokenResolution:
    token = (explicit_token or WHATSAPP_TOKEN).strip()
    if not token:
        raise RuntimeError("WHATSAPP_TOKEN nao esta definido no ambiente atual.")
    phone_id = (phone_id_override or WHATSAPP_PHONE_NUMBER_ID).strip()
    waba_id = (waba_id_override or WHATSAPP_WABA_ID).strip()
    if not phone_id or not waba_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID e WHATSAPP_WABA_ID nao estao definidos no ambiente atual.")
    if explicit_token:
        return TokenResolution(
            label="token-explicito",
            token=token,
            details="via argumento --token",
            phone_id=phone_id,
            waba_id=waba_id,
        )
    return TokenResolution(
        label="env",
        token=token,
        details="via ambiente atual /.env",
        phone_id=phone_id,
        waba_id=waba_id,
    )


def _run_gcloud_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _run_gcloud_text(args: list[str]) -> str:
    attempts: list[list[str]] = []
    direct = shutil.which("gcloud")
    if direct:
        attempts.append([direct, *args])

    joined = " ".join(args)
    if os.name == "nt":
        attempts.append(["cmd.exe", "/d", "/c", f"gcloud {joined}"])
        attempts.append(["powershell", "-NoProfile", "-Command", f"gcloud {joined}"])
    else:
        attempts.append(["sh", "-lc", f"gcloud {joined}"])

    last_error = "gcloud nao encontrado"
    for command in attempts:
        try:
            result = _run_gcloud_command(command)
        except FileNotFoundError:
            continue

        if result.returncode == 0:
            return (result.stdout or "").strip()

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        last_error = stderr or stdout or f"gcloud saiu com codigo {result.returncode}"

    raise RuntimeError(last_error)


def read_cloud_run_env(project_id: str, service_name: str, region: str) -> dict[str, str]:
    if not project_id:
        raise RuntimeError("Informe --gcloud-project para consultar o Cloud Run.")

    raw = _run_gcloud_text(
        [
            "run",
            "services",
            "describe",
            service_name,
            f"--region={region}",
            f"--project={project_id}",
            "--format=json",
        ]
    )
    payload = json.loads(raw)
    env_list = (
        payload.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [{}])[0]
        .get("env", [])
    )
    env_map: dict[str, str] = {}
    for item in env_list:
        name = str(item.get("name", "")).strip()
        value = str(item.get("value", "")).strip()
        if name:
            env_map[name] = value
    return env_map


def resolve_gcloud_secret(
    secret_name: str,
    project_id: str,
    service_name: str,
    region: str,
    phone_id_override: str = "",
    waba_id_override: str = "",
) -> TokenResolution:
    if not project_id:
        raise RuntimeError("Informe --gcloud-project para ler o Secret Manager.")
    token = _run_gcloud_text(
        [
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_name}",
            f"--project={project_id}",
        ]
    )
    if not token:
        raise RuntimeError("Secret Manager retornou token vazio")

    env_map = read_cloud_run_env(project_id, service_name, region)
    phone_id = (phone_id_override or env_map.get("WHATSAPP_PHONE_NUMBER_ID", "")).strip()
    waba_id = (waba_id_override or env_map.get("WHATSAPP_WABA_ID", "")).strip()
    if not phone_id or not waba_id:
        raise RuntimeError("Nao foi possivel descobrir WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_WABA_ID via Cloud Run.")

    return TokenResolution(
        label="gcloud-secret",
        token=token,
        details=(
            f"via Secret Manager ({secret_name}) no projeto {project_id} "
            f"+ ids do Cloud Run {service_name}/{region}"
        ),
        phone_id=phone_id,
        waba_id=waba_id,
    )


def resolve_tokens(args: argparse.Namespace) -> list[TokenResolution]:
    if args.token_source == "env":
        return [
            resolve_env_token(
                args.token,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        ]
    if args.token_source == "gcloud-secret":
        return [
            resolve_gcloud_secret(
                args.token_secret,
                args.gcloud_project,
                args.cloud_run_service,
                args.cloud_run_region,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        ]

    resolutions: list[TokenResolution] = []
    env_error: str | None = None
    try:
        resolutions.append(
            resolve_env_token(
                args.token,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        )
    except RuntimeError as exc:
        env_error = str(exc)

    resolutions.append(
        resolve_gcloud_secret(
            args.token_secret,
            args.gcloud_project,
            args.cloud_run_service,
            args.cloud_run_region,
            phone_id_override=args.phone_id.strip(),
            waba_id_override=args.waba_id.strip(),
        )
    )

    if env_error:
        resolutions.append(
            TokenResolution(
                label="env-error",
                token="",
                details=env_error,
                phone_id=args.phone_id.strip(),
                waba_id=args.waba_id.strip(),
            )
        )

    return resolutions


def diagnose(phone_result: dict[str, Any], waba_result: dict[str, Any], phone_id: str) -> list[str]:
    notes: list[str] = []

    if not phone_result.get("ok"):
        notes.append(f"falha ao consultar o numero: {get_error_message(phone_result.get('body'))}")
        message = get_error_message(phone_result.get("body")).lower()
        if "application has been deleted" in message:
            notes.append("o token atual parece vinculado a uma app Meta removida")
        if "code=190" in message:
            notes.append("o token da Meta esta invalido, expirado ou associado a uma app incorreta")
        return notes

    phone_body = phone_result.get("body", {})
    status = str(phone_body.get("status", "")).upper()
    platform_type = str(phone_body.get("platform_type", "")).upper()
    verification = str(phone_body.get("code_verification_status", "")).upper()

    if status == "DISCONNECTED":
        notes.append("o numero ainda nao esta conectado para envio pela Cloud API")
    if verification == "NOT_VERIFIED":
        notes.append("a verificacao do numero ainda nao foi concluida no lado da Meta")
    if platform_type == "ON_PREMISE":
        notes.append("o numero ainda aparece como ON_PREMISE; a coexistence nao terminou de provisionar o canal cloud")
    if status == "CONNECTED":
        notes.append("o numero ja aparece como CONNECTED")

    if waba_result.get("ok"):
        data = waba_result.get("body", {}).get("data", [])
        if isinstance(data, list) and not any(str(item.get("id")) == phone_id for item in data if isinstance(item, dict)):
            notes.append("a WABA consultada nao retornou o phone_id esperado")
    else:
        notes.append(f"falha ao consultar a WABA: {get_error_message(waba_result.get('body'))}")

    return notes


def run_single_check(
    resolution: TokenResolution,
    base_url: str,
) -> dict[str, Any]:
    if not resolution.token:
        return {
            "token_source": resolution.label,
            "token_details": resolution.details,
            "phone_id": resolution.phone_id,
            "waba_id": resolution.waba_id,
            "ok": False,
            "error": resolution.details,
        }

    phone_result = fetch_graph(resolution.phone_id, resolution.token, base_url, STATUS_FIELDS)
    waba_result = fetch_graph(f"{resolution.waba_id}/phone_numbers", resolution.token, base_url, STATUS_FIELDS)
    diagnosis = diagnose(phone_result, waba_result, resolution.phone_id)

    return {
        "token_source": resolution.label,
        "token_details": resolution.details,
        "phone_id": resolution.phone_id,
        "waba_id": resolution.waba_id,
        "graph_api_base": normalize_base_url(base_url),
        "phone_lookup": phone_result,
        "waba_phone_numbers": waba_result,
        "diagnosis": diagnosis,
    }


def print_human(results: list[dict[str, Any]]) -> None:
    for index, result in enumerate(results, start=1):
        if index > 1:
            print()
            print("-" * 72)
            print()

        print(f"[{index}] token_source={result['token_source']}")
        print(f"token_details: {result['token_details']}")

        if not result.get("ok", True):
            print(f"erro: {result.get('error', 'falha ao resolver token')}")
            continue

        phone_body = result["phone_lookup"].get("body", {}) if result["phone_lookup"].get("ok") else {}
        print(f"phone_id: {result['phone_id']}")
        print(f"waba_id:  {result['waba_id']}")
        print(
            "phone: status={status} platform_type={platform} code_verification_status={verification}".format(
                status=phone_body.get("status", "n/a"),
                platform=phone_body.get("platform_type", "n/a"),
                verification=phone_body.get("code_verification_status", "n/a"),
            )
        )
        print(
            "phone: display={display} verified_name={name} quality={quality}".format(
                display=phone_body.get("display_phone_number", "n/a"),
                name=phone_body.get("verified_name", "n/a"),
                quality=phone_body.get("quality_rating", "n/a"),
            )
        )

        if result["phone_lookup"].get("ok"):
            print("phone_lookup: ok")
        else:
            print(f"phone_lookup: {get_error_message(result['phone_lookup'].get('body'))}")

        if result["waba_phone_numbers"].get("ok"):
            data = result["waba_phone_numbers"].get("body", {}).get("data", [])
            print(f"waba_phone_numbers: ok ({len(data)} numero(s) retornado(s))")
        else:
            print(f"waba_phone_numbers: {get_error_message(result['waba_phone_numbers'].get('body'))}")

        print("diagnosis:")
        if result["diagnosis"]:
            for note in result["diagnosis"]:
                print(f"- {note}")
        else:
            print("- sem alertas adicionais")


def main() -> int:
    args = parse_args()

    try:
        resolutions = resolve_tokens(args)
        results = [
            run_single_check(
                resolution=resolution,
                base_url=args.graph_api_base,
            )
            for resolution in resolutions
        ]
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print_human(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
