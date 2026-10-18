# -*- coding: utf-8 -*-
"""Liga/desliga as flags da reabertura em lote de um tenant (plano v2.2 secao 7).

Flags (system_settings/chat, so a Castro grava; o PUT da UI as descarta):
  reopen_batch_enabled         lote inteiro (previa e disparo). Hubloc: false ate o
                               nome de exibicao do numero sair do LIMITED.
  reopen_bot_audience_enabled  publico Bot na tela (so depois do playbook da Val).
  bot_media_turn_enabled       turno da Val para midia em fase de bot (canario proprio).

Uso (PowerShell, raiz do repo). Default = DRY-RUN; so grava com --yes:
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.set_reopen_flags --tenant hubloc --set reopen_batch_enabled=false
  ./.venv/Scripts/python.exe -m scripts.set_reopen_flags --tenant hubloc --set reopen_batch_enabled=false --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from firestore_common import reset_tenant_context, set_tenant_context  # noqa: E402
from database import get_system_settings, log_audit, save_system_settings  # noqa: E402

FLAGS = ("reopen_batch_enabled", "reopen_bot_audience_enabled", "bot_media_turn_enabled")
_TRUE = {"1", "true", "on", "sim", "yes"}
_FALSE = {"0", "false", "off", "nao", "no"}


def _parse_sets(items):
    out = {}
    for raw in items:
        if "=" not in raw:
            raise SystemExit(f"--set espera chave=valor, recebeu: {raw!r}")
        key, val = (x.strip() for x in raw.split("=", 1))
        if key not in FLAGS:
            raise SystemExit(f"flag desconhecida: {key!r}. Opcoes: {', '.join(FLAGS)}")
        low = val.lower()
        if low in _TRUE:
            out[key] = True
        elif low in _FALSE:
            out[key] = False
        else:
            raise SystemExit(f"valor invalido para {key}: {val!r} (use true/false)")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True)
    p.add_argument("--set", action="append", default=[], help="flag=true|false (pode repetir)")
    p.add_argument("--yes", action="store_true", help="grava (default: dry-run)")
    args = p.parse_args()
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        raise SystemExit("defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente")

    changes = _parse_sets(args.set)
    token = set_tenant_context(args.tenant)
    try:
        atual = get_system_settings()
        print(f"tenant {args.tenant} — valores atuais:")
        for k in FLAGS:
            print(f"  {k} = {atual.get(k)}")
        if not changes:
            print("nada a alterar (use --set flag=true|false)")
            return
        print("alteracoes:")
        for k, v in changes.items():
            print(f"  {k}: {atual.get(k)} -> {v}")
        if not args.yes:
            print("DRY-RUN — nada foi gravado. Adicione --yes para aplicar.")
            return
        result = save_system_settings(changes)
        log_audit(None, "REOPEN_FLAGS_UPDATE",
                  "; ".join(f"{k}: {atual.get(k)} -> {v}" for k, v in changes.items()) + " | origem=script")
        print("gravado:")
        for k in FLAGS:
            print(f"  {k} = {result.get(k)}")
    finally:
        reset_tenant_context(token)


if __name__ == "__main__":
    main()
