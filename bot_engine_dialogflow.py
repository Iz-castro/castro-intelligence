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

from config import CX_DETECT_TIMEOUT_SECONDS, CX_READ_TIMEOUT_RETRY
from pii_redaction import redact_phone

logger = logging.getLogger("castro_crm.bot_cx")

# Limites da API do Dialogflow CX
_MAX_INPUT_CHARS = 256      # queryInput.text.text
_MAX_REPLY_CHARS = 4096     # limite de texto da Cloud API do WhatsApp

# Teto de LEITURA por chamada do DetectIntent (env CX_DETECT_TIMEOUT_SECONDS,
# default 60s desde 2026-08-18; era 15s hardcoded). Ver comentario em config.py.
_DETECT_TIMEOUT_SECONDS = CX_DETECT_TIMEOUT_SECONDS
# Handshake com dialogflow.googleapis.com: falha de rede aparece em segundos;
# esperar 60s pra descobrir que nao conectou so queimaria o orcamento do turno.
_CONNECT_TIMEOUT_SECONDS = 10.0

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
    timeout_s: Optional[float] = None,
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
        timeout_s: teto de LEITURA desta chamada (default
             CX_DETECT_TIMEOUT_SECONDS). O bot_service passa o que sobrou do
             orcamento do turno nos reenvios por frase de erro.

    Returns:
        dict normalizado (ver docstring do modulo). ok=False em falha —
        o chamador decide fallback/handoff. Nunca levanta excecao de
        transporte.

    Retry: 5xx, erro de rede (conexao recusada/reset, timeout de CONNECT/
    write/pool, ADC indisponivel) tentam UMA vez mais apos 0.5s — sao
    falhas rapidas e transitorias em que o pedido NAO chegou ao agente.
    TIMEOUT DE LEITURA na chamada PRINCIPAL (timeout_s=None) tambem reenvia
    UMA vez, com o teto inteiro de novo (CX_READ_TIMEOUT_RETRY, default
    true; PO 2026-08-20: turno real do agente passou de 109s e o proprio
    Dialogflow pede "Resend the request with a higher deadline"). Pior caso
    ~2x o teto de espera; a Meta reentrega o webhook nesse meio tempo e o
    was_dup absorve. Risco assumido: se a 1a chamada completar no agente
    depois do nosso timeout, o reenvio duplica o turno na sessao. Com
    timeout_s explicito (reenvio por frase de erro, que ja roda na SOBRA do
    orcamento) read-timeout NAO reenvia — comportamento antigo. Connect tem
    teto curto proprio (_CONNECT_TIMEOUT_SECONDS): a perna lenta e a
    geracao da resposta, nao o handshake com o Google.
    """
    read_timeout = float(timeout_s) if timeout_s else _DETECT_TIMEOUT_SECONDS
    http_timeout = httpx.Timeout(
        read_timeout, connect=min(_CONNECT_TIMEOUT_SECONDS, read_timeout),
    )
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
            async with httpx.AsyncClient(timeout=http_timeout) as client:
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
        except httpx.ReadTimeout:
            # Chamada principal reenvia 1x com o teto inteiro (ver docstring);
            # chamada com timeout_s explicito ou flag off: desiste na hora.
            if attempt == 1 and timeout_s is None and CX_READ_TIMEOUT_RETRY:
                last_error = "ReadTimeout"
                logger.warning(
                    "[BOT-CX] DetectIntent timeout de leitura apos %.0fs — "
                    "reenviando a mensagem 1x (CX_READ_TIMEOUT_RETRY) | "
                    "sessao=%s",
                    read_timeout, redact_phone(session_id),
                )
            else:
                logger.warning(
                    "[BOT-CX] DetectIntent timeout de leitura apos %.0fs (sem "
                    "reenvio) | sessao=%s | tentativa=%d",
                    read_timeout, redact_phone(session_id), attempt,
                )
                return dict(_FAILURE)
        except httpx.HTTPError as exc:
            # Inclui ConnectTimeout/WriteTimeout/PoolTimeout (subclasses de
            # TimeoutException, que e HTTPError): o pedido NAO chegou -> retry.
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
