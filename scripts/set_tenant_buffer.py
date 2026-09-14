# -*- coding: utf-8 -*-
"""One-off idempotente: liga/desliga o buffer (debounce) do bot CX por tenant.

Grava settings.ai.buffer_seconds (override lido no READ; 0 = desligado;
chave ausente = BOT_BUFFER_SECONDS do env, hoje 0). So tenants com
bot_engine=dialogflow_cx sao afetados — o builtin ignora o campo.

Uso (PowerShell, na raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "<projeto CRM>"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"   # ou castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.set_tenant_buffer --tenant varizemed-test --seconds 10        # dry-run
  ./.venv/Scripts/python.exe -m scripts.set_tenant_buffer --tenant varizemed-test --seconds 10 --yes  # aplica
  ./.venv/Scripts/python.exe -m scripts.set_tenant_buffer --tenant varizemed-test --seconds 0 --yes   # kill-switch

Ordem combinada: varizemed-test primeiro (teste real pelo numero de teste),
depois o PO decide a varizemed real. O cache de tenants atualiza em ate 60s
nas instancias do Cloud Run — nao precisa de deploy.
"""
import argparse
import sys

from tenant_service import get_tenant, update_tenant

MAX_SECONDS = 60.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument(
        "--seconds", required=True, type=float,
        help="janela de quietude em segundos (0 = desligado; sugerido 10)",
    )
    p.add_argument("--yes", action="store_true", help="aplica (default: dry-run)")
    args = p.parse_args()

    if not (args.seconds >= 0) or args.seconds > MAX_SECONDS:
        print(f"--seconds tem que estar entre 0 e {MAX_SECONDS:g}.")
        return 1

    tenant = get_tenant(args.tenant)
    if not tenant:
        print(f"Tenant {args.tenant!r} nao existe.")
        return 1
    current = (tenant.get("settings") or {}).get("ai") or {}
    engine = str(current.get("bot_engine") or "").strip().lower()
    print(f"=== tenant {args.tenant}: bot_engine={engine or '(builtin)'} "
          f"status={current.get('status', 'active')} ===")
    print(f"buffer_seconds atual: {current.get('buffer_seconds', '(ausente = env BOT_BUFFER_SECONDS)')}")
    print(f"buffer_seconds novo:  {args.seconds:g}")
    if engine != "dialogflow_cx":
        print("ATENCAO: tenant nao usa Dialogflow CX — o buffer nunca arma para ele. "
              "Gravando mesmo assim.")

    if not args.yes:
        print("\nDRY-RUN. Adicione --yes para aplicar.")
        return 0

    # update_tenant usa .set(merge=True) com field paths de folha: o merge e
    # PROFUNDO, entao as outras chaves de settings.ai sobrevivem.
    update_tenant(args.tenant, settings={"ai": {"buffer_seconds": args.seconds}})
    print("\nGravado. O cache de tenants atualiza em ate 60s nas instancias do Cloud Run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
