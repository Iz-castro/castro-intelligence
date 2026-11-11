# -*- coding: utf-8 -*-
"""Chave comercial do lembrete. Dry-run default; --yes aplica no tenant explicito."""

import argparse
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--mode", required=True, choices=("off", "dry_run", "on"))
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    from tenant_service import get_tenant, update_tenant
    tenant = get_tenant(args.tenant)
    if not tenant:
        parser.error("Tenant inexistente.")
    ai = (tenant.get("settings") or {}).get("ai") or {}
    if args.mode != "off" and (ai.get("bot_engine") != "dialogflow_cx" or ai.get("lgpd_by_agent") is True):
        parser.error("Lembretes exigem CX com aceite LGPD registrado pelo CRM.")
    current = tenant.get("settings") or {}
    epoch = current.get("bot_reminder_epoch")
    if args.mode != current.get("bot_reminder_mode") or not epoch:
        epoch = uuid.uuid4().hex
    print("Tenant=%s modo=%s -> %s. Mudanca de modo invalida agendas anteriores." % (
        args.tenant, current.get("bot_reminder_mode", "off"), args.mode))
    if not args.yes:
        print("DRY-RUN: nenhuma escrita. Use --yes para aplicar.")
        return 0
    update_tenant(args.tenant, settings={"bot_reminder_mode": args.mode, "bot_reminder_epoch": epoch})
    print("Gravado. Configure os textos na tela de Lembretes automaticos. Cache: ate 60s; cron rele antes do envio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
