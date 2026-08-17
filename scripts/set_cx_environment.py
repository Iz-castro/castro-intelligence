# -*- coding: utf-8 -*-
"""Aponta um tenant CX para outro environment publicado do agente Dialogflow.

Uso operacional (PO sem o agente): docs/deploy/TROCAR_ENVIRONMENT_VAL.md.

Por que NAO usar scripts/set_tenant_ai.py pra isso: ele reconstroi as 13
chaves de settings.ai a partir de argv — o --location default e "global"
(varizemed e us-central1: derrubaria o agente) e o lgpd_notice acentuado
atravessando o PowerShell arrisca mojibake no aviso que o paciente le. Este
script le settings.ai inteiro, troca SO environment_id (+ core_version no
MESMO write — regra desde 2026-08-10) e regrava.

Travas:
  - dry-run por padrao; so grava com --yes;
  - --expect-current: aborta se o environment atual nao for o esperado
    (evita trocar em cima de um estado que voce nao conhece);
  - --draft devolve pro Draft (environment_id vazio, core_version "draft");
  - imprime diff campo a campo e confere depois de gravar.

Trocar environment RESETA a sessao de quem esta conversando com o agente
(o environment faz parte do caminho da sessao no CX). Conferir antes:
    python -m scripts.set_cx_environment --tenant varizemed --who-is-in-bot

Exemplos (PowerShell, na raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed --show
  ./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed `
      --env 05267e69-9632-444c-b009-b6069a7474e2 --core-version val-5.0.21        # dry-run
  ... --yes                                                                        # aplica
  ./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed-test --draft --yes
"""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

from tenant_service import get_tenant, update_tenant, refresh_tenants

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_BR = timezone(timedelta(hours=-3))


def _extract_env_id(value: str) -> str:
    """Aceita o UUID puro OU o caminho completo que o dev de IA manda
    (projects/.../environments/<uuid>) e devolve so o UUID."""
    v = (value or "").strip()
    if "/environments/" in v:
        v = v.rsplit("/environments/", 1)[1].strip("/")
    return v


def _show(tenant_id: str, ai: dict) -> None:
    print(f"tenant={tenant_id}")
    env = ai.get("environment_id") or ""
    print(f"  environment_id : {env or '(vazio = DRAFT do agente)'}")
    print(f"  core_version   : {ai.get('core_version')}")
    print(f"  agent_id       : {ai.get('agent_id')}")
    print(f"  gcp_project_id : {ai.get('gcp_project_id')}  location={ai.get('location')}")
    print(f"  status         : {ai.get('status')}  bot_engine={ai.get('bot_engine')}")


def _who_is_in_bot(tenant_id: str, minutes: int = 60) -> int:
    """Lista contatos ainda no funil do bot com mensagem recente (seriam
    resetados pela troca). Le so wa_conversations recentes + contatos."""
    from firestore_common import collection, set_tenant_context, reset_tenant_context
    from pii_redaction import redact_phone

    def _dt(v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    agora = datetime.now(timezone.utc)
    corte = agora - timedelta(minutes=minutes)
    token = set_tenant_context(tenant_id)
    try:
        contatos = {}
        for snap in collection("wa_contacts").stream():
            d = snap.to_dict() or {}
            contatos[d.get("id")] = d
        ativos = []
        for snap in collection("wa_conversations").stream():
            c = snap.to_dict() or {}
            if c.get("is_backup"):
                continue
            ult = _dt(c.get("last_message_at"))
            if not ult or ult < corte:
                continue
            ctc = contatos.get(c.get("contact_id")) or {}
            if not ctc.get("bot_completed") and not ctc.get("assigned_to"):
                ativos.append((ult, c.get("contact_id"), ctc.get("wa_id")))
    finally:
        reset_tenant_context(token)

    print(f"tenant={tenant_id}  agora={agora.astimezone(_BR):%d/%m %H:%M} BRT  "
          f"janela={minutes}min")
    print(f"  CONVERSANDO COM O AGENTE AGORA (seriam resetados): {len(ativos)}")
    for ult, cid, wa in sorted(ativos):
        print(f"    contato={cid} {redact_phone(str(wa))} "
              f"ultima msg {ult.astimezone(_BR):%d/%m %H:%M} BRT")
    if not ativos:
        print("    nenhum — janela limpa pra trocar")
    return len(ativos)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tenant", required=True, help="ex.: varizemed | varizemed-test")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--env", help="UUID do environment OU caminho completo projects/.../environments/<uuid>")
    g.add_argument("--draft", action="store_true", help="devolve pro Draft (environment_id vazio)")
    g.add_argument("--show", action="store_true", help="so mostra a config atual")
    g.add_argument("--who-is-in-bot", action="store_true",
                   help="lista quem esta conversando com o agente agora (seria resetado)")
    p.add_argument("--core-version", default=None,
                   help="rotulo da versao (ex.: val-5.0.21). Obrigatorio com --env; "
                        "--draft usa 'draft'")
    p.add_argument("--expect-current", default=None,
                   help="aborta se o environment atual nao for este (UUID ou vazio='')")
    p.add_argument("--minutes", type=int, default=60, help="janela do --who-is-in-bot")
    p.add_argument("--yes", action="store_true", help="aplica (default: dry-run)")
    args = p.parse_args()

    tenant = get_tenant(args.tenant)
    if not tenant:
        print(f"Tenant {args.tenant!r} nao existe.")
        return 1
    settings = dict(tenant.get("settings") or {})
    antes = dict(settings.get("ai") or {})
    if not antes:
        print(f"Tenant {args.tenant!r} nao tem settings.ai (nao e tenant CX).")
        return 1

    if args.who_is_in_bot:
        _who_is_in_bot(args.tenant, args.minutes)
        return 0
    if args.show or (not args.env and not args.draft):
        _show(args.tenant, antes)
        if not args.show:
            print("\n(nada a fazer: passe --env <uuid> --core-version <rotulo>, ou --draft)")
        return 0

    if args.draft:
        novo_env, novo_core = "", "draft"
    else:
        novo_env = _extract_env_id(args.env)
        if not _UUID_RE.match(novo_env):
            print(f"--env invalido: {novo_env!r} (esperado UUID ou caminho .../environments/<uuid>)")
            return 1
        if not args.core_version:
            print("--core-version e obrigatorio com --env (ex.: val-5.0.21). "
                  "Regra: quem aponta environment atualiza o rotulo no MESMO write.")
            return 1
        novo_core = args.core_version.strip()

    atual_env = antes.get("environment_id") or ""
    if args.expect_current is not None and atual_env != _extract_env_id(args.expect_current):
        print(f"ABORTADO: environment atual e {atual_env!r}, esperava "
              f"{_extract_env_id(args.expect_current)!r}. Rode --show e confira.")
        return 1
    if atual_env == novo_env and antes.get("core_version") == novo_core:
        print("Ja esta exatamente assim — nada a fazer.")
        return 0

    depois = dict(antes)
    depois["environment_id"] = novo_env
    depois["core_version"] = novo_core

    print(f"tenant={args.tenant}  {'APLICANDO' if args.yes else 'DRY-RUN'}\n")
    for k in sorted(set(antes) | set(depois)):
        a, d = antes.get(k), depois.get(k)
        if a == d:
            s = str(a)
            print(f"  = {k:24} {s[:60]}{'...' if len(s) > 60 else ''}")
        else:
            print(f"  * {k:24} {a!r}")
            print(f"  {'':26}-> {d!r}")

    if not args.yes:
        print("\nDRY-RUN. Adicione --yes para aplicar.")
        return 0

    settings["ai"] = depois
    update_tenant(args.tenant, settings=settings)
    refresh_tenants()

    conf = ((get_tenant(args.tenant) or {}).get("settings") or {}).get("ai") or {}
    ok_env = (conf.get("environment_id") or "") == novo_env
    ok_core = conf.get("core_version") == novo_core
    ok_resto = all(conf.get(k) == v for k, v in antes.items()
                   if k not in ("environment_id", "core_version"))
    print(f"\n  environment_id : {conf.get('environment_id') or '(vazio = DRAFT)'}  "
          f"({'ok' if ok_env else 'ERRO'})")
    print(f"  core_version   : {conf.get('core_version')}  ({'ok' if ok_core else 'ERRO'})")
    print(f"  demais campos intactos: {ok_resto}")
    print(f"  lgpd_notice preservado: {conf.get('lgpd_notice') == antes.get('lgpd_notice')}")
    print(f"\n  ROLLBACK: --env '{atual_env}' --core-version '{antes.get('core_version')}'"
          if atual_env else
          f"\n  ROLLBACK: --draft")
    print("  Vale em ate 60s nas instancias do Cloud Run (cache de tenant).")
    return 0 if (ok_env and ok_core and ok_resto) else 1


if __name__ == "__main__":
    sys.exit(main())
