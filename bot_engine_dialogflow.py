# -*- coding: utf-8 -*-

"""
Conector Dialogflow CX (motor de bot "dialogflow_cx" por tenant).

Chama o DetectIntent REST v3 do agente configurado em
tenants/{tid}.settings.ai e normaliza a resposta para o contrato do
bot do CRM. Nao conhece Firestore nem o pipeline do webhook — recebe a
config e devolve um dict normalizado; quem decide o que fazer com
handoff/estado e o bot_service.

Contrato de retorno de detect_intent_text:
    {
      "ok": bool,                    # False = falha de transporte/API
      "reply_text": str,             # texto concatenado das responseMessages
      "handoff_request": bool,       # parametro de sessao setado pelo agente
      "handoff_summary": str,        # resumo para o atendente (se houver)
      "conversation_complete": bool, # fim de sessao sem handoff
      "user_name": str,              # nome declarado (se o agente coletou)
      "parameters": dict,            # session params BRUTOS acumulados
                                     # (temperatura do lead + sumario do
                                     # handoff; pode ter PII — nao logar)
    }

Autenticacao: ADC (service account do Cloud Run) com scope cloud-platform.
A SA do CRM precisa de roles/dialogflow.client no projeto do agente.
Sem env vars novas — projeto/agente/idioma vem da config por tenant.

LGPD: nunca logar o texto do usuario nem session_id em claro.
"""

import asyncio
import logging
import threading
from typing import Any, Optional

import httpx

from pii_redaction import redact_phone

logger = logging.getLogger("castro_crm.bot_cx")

# Limites da API do Dialogflow CX
_MAX_INPUT_CHARS = 256      # queryInput.text.text
_MAX_REPLY_CHARS = 4096     # limite de texto da Cloud API do WhatsApp

_DETECT_TIMEOUT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# Token ADC (cacheado; refresh sob demanda)
# ---------------------------------------------------------------------------

_token_lock = threading.Lock()
_cached_credentials = None


def _get_access_token() -> str:
    """Token OAuth2 da ADC com refresh por expiry.

    google.auth.transport.requests.Request() e sync; o refresh e raro
    (tokens duram ~1h) e roda em thread via asyncio.to_thread no caminho
    async — aceitavel para o volume do bot.
    """
    global _cached_credentials
    import google.auth
    import google.auth.transport.requests

    with _token_lock:
        if _cached_credentials is None:
            _cached_credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not _cached_credentials.valid:
            _cached_credentials.refresh(google.auth.transport.requests.Request())
        return _cached_credentials.token


def _detect_intent_url(cfg: dict, session_id: str) -> str:
    project = str(cfg.get("gcp_project_id") or "").strip()
    location = str(cfg.get("location") or "global").strip() or "global"
    agent_id = str(cfg.get("agent_id") or "").strip()
    environment_id = str(cfg.get("environment_id") or "").strip()

    host = (
        "dialogflow.googleapis.com"
        if location == "global"
        else f"{location}-dialogflow.googleapis.com"
    )
    agent_path = f"projects/{project}/locations/{location}/agents/{agent_id}"
    if environment_id:
        agent_path += f"/environments/{environment_id}"
    return f"https://{host}/v3/{agent_path}/sessions/{session_id}:detectIntent"


def _coerce_bool(value: Any) -> bool:
    """Parametros do CX chegam como bool OU string ('true'/'false')."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() == "true"


def _unwrap_struct_params(parameters: dict) -> dict:
    """Desembrulha params que o agente devolve como struct {chave: valor}.

    Observado em PROD 2026-07-29 (varizemed): apos edicao no agente (que roda
    em DRAFT), cada session param passou a chegar como {'user_name': 'Timmy'}
    em vez do escalar 'Timmy'. Sem o unwrap, _coerce_bool/str() sujam o resumo
    do operador e a classificacao de temperatura (estado QUENTE inalcancavel).
    Regra conservadora: dict de UMA entrada cuja chave repete a do param, ou
    cuja unica entrada e escalar, vira o valor interno (ate 2 niveis). Dicts
    com 2+ entradas passam intactos.
    """
    out = {}
    for key, value in parameters.items():
        for _ in range(2):
            if isinstance(value, dict) and len(value) == 1:
                inner_key, inner_val = next(iter(value.items()))
                if inner_key == key or not isinstance(inner_val, dict):
                    value = inner_val
                    continue
            break
        out[key] = value
    return out


def _extract_reply_text(query_result: dict) -> str:
    parts = []
    for msg in query_result.get("responseMessages", []) or []:
        text_block = msg.get("text") or {}
        for line in text_block.get("text", []) or []:
            line = str(line).strip()
            if line:
                parts.append(line)
    reply = "\n\n".join(parts)
    return reply[:_MAX_REPLY_CHARS]


def _normalize_response(payload: dict) -> dict:
    query_result = payload.get("queryResult") or {}
    parameters = query_result.get("parameters") or {}
    if isinstance(parameters, dict):
        parameters = _unwrap_struct_params(parameters)
    return {
        "ok": True,
        "reply_text": _extract_reply_text(query_result),
        "handoff_request": _coerce_bool(parameters.get("handoff_request")),
        "handoff_summary": str(parameters.get("handoff_summary") or "").strip(),
        "conversation_complete": _coerce_bool(parameters.get("conversation_complete")),
        "user_name": str(parameters.get("user_name") or "").strip(),
        # Dict BRUTO dos session params acumulados — consumido pelo
        # _finalize_cx_handoff (temperatura do lead + sumario enriquecido).
        # Pode conter PII (nome/sintoma): NUNCA logar o conteudo.
        "parameters": dict(parameters) if isinstance(parameters, dict) else {},
    }


_FAILURE = {
    "ok": False,
    "reply_text": "",
    "handoff_request": False,
    "handoff_summary": "",
    "conversation_complete": False,
    "user_name": "",
    "parameters": {},
}


async def detect_intent_text(
    cfg: dict,
    session_id: str,
    text: str,
    session_params: Optional[dict] = None,
) -> dict:
    """Roda um turno de DetectIntent no agente CX do tenant.

    Args:
        cfg: dict settings.ai do tenant (gcp_project_id, location, agent_id,
             environment_id, language_code).
        session_id: digitos do wa_id do contato (sem '+'; 10-15 digitos —
             formato que a ValMemory do agente valida).
        text: mensagem do usuario (truncada ao limite do CX).
        session_params: parametros de sessao injetados neste turno
             (user_id, tenant_id, lgpd_consent, ...).

    Returns:
        dict normalizado (ver docstring do modulo). ok=False em falha —
        o chamador decide fallback/handoff. Nunca levanta excecao de
        transporte.
    """
    url = _detect_intent_url(cfg, session_id)
    body = {
        "queryInput": {
            "text": {"text": str(text or "")[:_MAX_INPUT_CHARS]},
            "languageCode": str(cfg.get("language_code") or "pt-br"),
        },
        "queryParams": {
            "timeZone": "America/Bahia",
            "parameters": dict(session_params or {}),
        },
    }

    last_error = ""
    for attempt in (1, 2):
        try:
            token = await asyncio.to_thread(_get_access_token)
            async with httpx.AsyncClient(timeout=_DETECT_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 200:
                result = _normalize_response(resp.json())
                logger.info(
                    "[BOT-CX] turno ok | sessao=%s | handoff=%s | complete=%s | tentativa=%d",
                    redact_phone(session_id),
                    result["handoff_request"],
                    result["conversation_complete"],
                    attempt,
                )
                return result
            # 5xx: transitorio, tenta de novo; 4xx: config errada, nao adianta
            last_error = f"http {resp.status_code}"
            if resp.status_code < 500:
                logger.warning(
                    "[BOT-CX] DetectIntent %s | sessao=%s (config/permissao? "
                    "ver roles/dialogflow.client e agent_id)",
                    last_error, redact_phone(session_id),
                )
                return dict(_FAILURE)
        except httpx.TimeoutException:
            last_error = "timeout"
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
        except Exception as exc:  # credencial ADC indisponivel etc.
            last_error = type(exc).__name__
        if attempt == 1:
            await asyncio.sleep(0.5)

    logger.warning(
        "[BOT-CX] DetectIntent falhou (%s) apos retry | sessao=%s",
        last_error, redact_phone(session_id),
    )
    return dict(_FAILURE)
