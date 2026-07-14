# -*- coding: utf-8 -*-

"""
Smoke test REAL do agente Dialogflow CX (pos-restore, trilha IA).

READ-ONLY no CRM: nao toca no Firestore do CRM nem no pipeline — usa o
conector real (bot_engine_dialogflow.detect_intent_text) contra o agente
restaurado, com uma sessao NUMERICA fake (a ValMemory do agente exige
10-15 digitos; sessoes de simulador sao rejeitadas por design).

Valida, em 3 turnos:
  1. saudacao da Val (agente responde texto);
  2. pergunta de convenio -> resposta do router (prova seed + function);
  3. pedido de atendente -> handoff_request=true nos parametros.

Pre-requisitos: ADC local com permissao (gcloud auth application-default
login OU rodar com a SA do CRM) + roles/dialogflow.client no AI_PROJECT.

Uso:
  ./.venv/Scripts/python.exe -m tools.cx_smoke --gcp-project castro-ai \
      --agent-id <uuid> [--location global] [--session 5571900000001]

Sai 0 se os 3 turnos passarem.
"""

import argparse
import asyncio
import sys

from bot_engine_dialogflow import detect_intent_text


async def run(cfg: dict, session_id: str) -> int:
    params = {
        "user_id": f"+{session_id}",
        "tenant_id": "varizemed-test",
        "lgpd_consent": True,
    }

    turns = [
        ("oi", "saudacao", lambda r: bool(r["reply_text"])),
        (
            "tenho unimed, voces aceitam para consulta de varizes?",
            "convenio (router+seed)",
            lambda r: bool(r["reply_text"]),
        ),
        (
            "quero falar com um atendente humano por favor",
            "handoff",
            lambda r: r["handoff_request"] is True,
        ),
    ]

    failures = 0
    for text, label, check in turns:
        print(f"\n>> Cliente: {text}")
        result = await detect_intent_text(cfg, session_id, text, params)
        if not result["ok"]:
            print(f"   FALHA de transporte/API no turno '{label}'")
            failures += 1
            continue
        print(f"<< Val: {result['reply_text'][:300]}")
        print(f"   handoff_request={result['handoff_request']} "
              f"conversation_complete={result['conversation_complete']} "
              f"user_name={result['user_name']!r}")
        if check(result):
            print(f"   OK  {label}")
        else:
            print(f"   FALHOU: {label}")
            failures += 1

    if failures:
        print(f"\n{failures} turno(s) falharam.")
        return 1
    print("\nSmoke completo: agente + tools respondendo. Confira tambem os docs "
          f"em conversations/+{session_id} no banco do AI_PROJECT (ValMemory).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gcp-project", required=True, help="AI_PROJECT")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--location", default="global")
    p.add_argument("--environment-id", default="")
    p.add_argument("--language-code", default="pt-br")
    p.add_argument("--session", default="5571900000001",
                   help="sessao numerica fake (10-15 digitos)")
    args = p.parse_args()

    digits = "".join(ch for ch in args.session if ch.isdigit())
    if not (10 <= len(digits) <= 15):
        print("--session precisa ter 10-15 digitos (formato ValMemory).")
        return 1

    cfg = {
        "gcp_project_id": args.gcp_project,
        "location": args.location,
        "agent_id": args.agent_id,
        "environment_id": args.environment_id,
        "language_code": args.language_code,
    }
    return asyncio.run(run(cfg, digits))


if __name__ == "__main__":
    sys.exit(main())
