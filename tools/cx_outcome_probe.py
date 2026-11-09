# -*- coding: utf-8 -*-

"""
Probe REAL do desfecho da Val (scheduling_outcome / desfecho_bot) no agente CX.

NAO e mockado: bate no agente Dialogflow CX do tenant (le settings.ai do
tenant no Firestore real, SO LEITURA, e usa o conector real). Nao toca
wa_contacts/wa_conversations nem envia WhatsApp. Sessao numerica FAKE
(10-15 digitos, exigencia da ValMemory) - o router da Val grava a conversa
de teste no banco do AI_PROJECT, como o cx_smoke.

Pergunta que responde (plano de reabertura, etapa 4): o valor que o router
devolve na tool (scheduling_outcome=link_oferecido|encaminhado_atendente,
v4.11) chega a queryResult.parameters, isto e, a LLM copia o campo para a
sessao como faz com handoff_summary? Sem isso o CRM nao tem como gravar
bot_outcome (P5) e o criterio 2.2.5 fica so na heuristica do link.

Pre-requisitos: ADC local (gcloud auth application-default login) com
roles/dialogflow.client no AI_PROJECT e leitura no Firestore do CRM;
FIRESTORE_PROJECT_ID e FIRESTORE_COLLECTION_PREFIX no ambiente.

Uso:
  .venv/Scripts/python.exe tools/cx_outcome_probe.py --tenant varizemed-test
      [--session 5571900000002] [--turn "texto" ...]

Sai 0 se algum turno trouxe scheduling_outcome ou desfecho_bot; 1 se nao.
"""

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTCOME_PARAMS = ("scheduling_outcome", "desfecho_bot")

DEFAULT_TURNS = [
    "oi",
    "quero agendar uma consulta de varizes",
    "tenho unimed",
    "pode me mandar o link de agendamento?",
    "obrigado",
]


async def run(cfg: dict, tenant_id: str, session_id: str, turns: list) -> int:
    from bot_engine_dialogflow import detect_intent_text

    params = {
        "user_id": f"+{session_id}",
        "tenant_id": tenant_id,
        "lgpd_consent": True,
    }
    found = None
    for i, text in enumerate(turns, 1):
        print(f"\n>> Turno {i}: {text}")
        result = await detect_intent_text(cfg, session_id, text, params)
        if not result.get("ok"):
            print("   FALHA de transporte/API neste turno")
            continue
        reply = str(result.get("reply_text") or "")
        print(f"<< Val: {reply[:220]!r}{'...' if len(reply) > 220 else ''}")
        p = result.get("parameters") or {}
        print(f"   handoff_request={result.get('handoff_request')} | params={sorted(p.keys())}")
        for name in OUTCOME_PARAMS:
            if name in p:
                val = p.get(name)
                print(f"   {name} = {val!r} (tipo {type(val).__name__})")
                if val not in (None, "", "null"):
                    found = (name, val)
        if found:
            print(f"\nENCONTRADO: {found[0]} = {found[1]!r} no turno {i}")
            return 0
        # so o 1o turno manda lgpd_consent; os seguintes nao precisam reafirmar
        params = {"user_id": f"+{session_id}", "tenant_id": tenant_id}
    print("\nNENHUM turno trouxe scheduling_outcome/desfecho_bot nos parametros de sessao.")
    return 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True, help="tenant cujo settings.ai aponta o agente (ex.: varizemed-test)")
    p.add_argument("--session", default="5571900000002", help="sessao numerica fake (10-15 digitos)")
    p.add_argument("--turn", action="append", help="texto de um turno (repetir); default = roteiro de agendamento")
    args = p.parse_args()

    if not os.getenv("FIRESTORE_PROJECT_ID"):
        print("defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente")
        return 2
    digits = "".join(ch for ch in args.session if ch.isdigit())
    if not (10 <= len(digits) <= 15):
        print("--session precisa ter 10-15 digitos (formato ValMemory).")
        return 2

    from tenant_service import get_tenant
    tenant = get_tenant(args.tenant) or {}
    settings = tenant.get("settings") if isinstance(tenant.get("settings"), dict) else {}
    cfg = settings.get("ai") if isinstance(settings.get("ai"), dict) else {}
    if not cfg.get("agent_id") or cfg.get("bot_engine") != "dialogflow_cx":
        print(f"tenant {args.tenant!r}: settings.ai sem agente CX (bot_engine={cfg.get('bot_engine')!r}).")
        return 2
    print(f"agente: projeto={cfg.get('gcp_project_id')} location={cfg.get('location')} "
          f"agent={str(cfg.get('agent_id'))[:8]}... env={cfg.get('environment_id') or 'DRAFT'}")
    turns = args.turn or DEFAULT_TURNS
    return asyncio.run(run(cfg, args.tenant, digits, turns))


if __name__ == "__main__":
    sys.exit(main())
