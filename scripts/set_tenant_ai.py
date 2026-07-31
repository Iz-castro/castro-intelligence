# -*- coding: utf-8 -*-
"""One-off idempotente: grava settings.ai do tenant (motor de bot por tenant).

Config conforme o contrato em docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md.
So o super-admin/operacao roda este script (a UI nao edita settings.ai).

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "<projeto CRM>"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"  # ou castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.set_tenant_ai --tenant varizemed-test `
      --gcp-project castro-ai --agent-id <uuid> `
      --handoff-bot-key sac `
      --lgpd-notice "Ola! ..." --lgpd-privacy-url https://... `
      --lgpd-policy-version varizemed-test-2026-07 `
      --core-version val-05                       # dry-run
  ... --yes                                        # aplica

Desligar o motor sem apagar a config: --status paused --yes.
"""
import argparse
import json
import sys

from database_firestore import VALID_BOT_KEYS
from tenant_service import get_tenant, update_tenant


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--gcp-project", required=True, help="AI_PROJECT (projeto dos agentes)")
    p.add_argument("--agent-id", required=True, help="AGENT_ID do restore")
    p.add_argument("--location", default="global")
    p.add_argument("--environment-id", default="")
    p.add_argument("--language-code", default="pt-br")
    # required + choices: o default antigo ("atendimento") NAO existia em
    # VALID_BOT_KEYS -> _normalize_bot_key zerava e o handoff saia SEM
    # department_id (incidente evitado por sorte no varizemed, que usa "sac").
    p.add_argument(
        "--handoff-bot-key", required=True, choices=sorted(VALID_BOT_KEYS),
        help="bot_key do departamento que recebe o handoff (tem que existir "
             "num setor ATIVO do tenant)",
    )
    p.add_argument("--lgpd-notice", default="")
    p.add_argument("--lgpd-privacy-url", default="")
    p.add_argument("--lgpd-policy-version", default="")
    p.add_argument("--core-version", default="")
    p.add_argument("--customization-version", default="1")
    p.add_argument("--status", default="active", choices=("active", "paused"))
    p.add_argument(
        "--temperature-signals", default=None,
        help=("JSON opcional com override dos sinais de temperatura do lead "
              "(chaves: quente_bool_any, morno_bool_any, morno_nonempty_any; "
              "ver lead_temperature.DEFAULT_TEMPERATURE_SIGNALS). Ex.: "
              "'{\"quente_bool_any\": [\"wants_appointment\"]}'. Sem o arg, "
              "um override ja gravado e PRESERVADO no re-run."),
    )
    p.add_argument("--yes", action="store_true", help="aplica (default: dry-run)")
    args = p.parse_args()

    tenant = get_tenant(args.tenant)
    if not tenant:
        print(f"Tenant {args.tenant!r} nao existe.")
        return 1

    # Fail-closed LGPD: um motor CX ATIVO nao pode rodar sem aviso de
    # consentimento especifico e versao de politica do proprio tenant (dado
    # sensivel de clinica). Sem isso, o consentimento sairia generico e/ou
    # carimbado com a versao errada (achados da revisao).
    if args.status == "active":
        faltando = [nome for nome, val in (
            ("--lgpd-notice", args.lgpd_notice),
            ("--lgpd-policy-version", args.lgpd_policy_version),
        ) if not str(val).strip()]
        if faltando:
            print("Motor CX ativo exige " + ", ".join(faltando)
                  + " (LGPD: consentimento especifico e versionado). Abortando.")
            return 1

    ai_cfg = {
        "bot_engine": "dialogflow_cx",
        "gcp_project_id": args.gcp_project,
        "location": args.location,
        "agent_id": args.agent_id,
        "environment_id": args.environment_id,
        "language_code": args.language_code,
        "handoff_bot_key": args.handoff_bot_key,
        "lgpd_notice": args.lgpd_notice,
        "lgpd_privacy_url": args.lgpd_privacy_url,
        "lgpd_policy_version": args.lgpd_policy_version,
        "core_version": args.core_version,
        "customization_version": args.customization_version,
        "status": args.status,
    }

    current = (tenant.get("settings") or {}).get("ai") or {}

    # NOTA sobre o merge: update_tenant usa .set(merge=True), e o cliente
    # Firestore gera field paths de FOLHA — o merge e PROFUNDO (desce ate
    # settings.ai.<chave>). Consequencias: (a) chave ja gravada que este
    # script nao manda (ex.: handoff_text_hints) SOBREVIVE ao re-run;
    # (b) NAO existe caminho aqui para REMOVER uma chave obsoleta de
    # settings.ai — isso exige DELETE_FIELD manual.
    # temperature_signals: preservacao explicita mantida por clareza (com o
    # merge profundo ela e redundante, mas documenta a intencao).
    if args.temperature_signals is not None:
        try:
            sig = json.loads(args.temperature_signals)
        except json.JSONDecodeError as exc:
            print(f"--temperature-signals nao e JSON valido: {exc}")
            return 1
        known = {"quente_bool_any", "morno_bool_any", "morno_nonempty_any"}
        if not isinstance(sig, dict) or not set(sig).issubset(known):
            print(f"--temperature-signals: dict com chaves {sorted(known)} apenas.")
            return 1
        ai_cfg["temperature_signals"] = sig
    elif isinstance(current.get("temperature_signals"), dict):
        ai_cfg["temperature_signals"] = current["temperature_signals"]
    print(f"=== settings.ai atual do tenant {args.tenant} ===")
    print(json.dumps(current, indent=2, ensure_ascii=False) if current else "  (vazio)")
    print("=== settings.ai a gravar ===")
    print(json.dumps(ai_cfg, indent=2, ensure_ascii=False))

    if tenant.get("plan") not in ("ai_custom", "enterprise_ai"):
        print(f"ATENCAO: plano do tenant e {tenant.get('plan')!r} — o modulo ai_agent "
              "e dos planos ai_custom/enterprise_ai. Gravando mesmo assim (config "
              "por tenant nao depende do plano hoje), mas confira se e intencional.")

    if not args.yes:
        print("\nDRY-RUN. Adicione --yes para aplicar.")
        return 0

    update_tenant(args.tenant, settings={"ai": ai_cfg})
    print("\nGravado. O cache de tenants atualiza em ate 60s nas instancias do Cloud Run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
