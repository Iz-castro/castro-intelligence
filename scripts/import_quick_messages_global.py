# -*- coding: utf-8 -*-
"""Importa mensagens rapidas GLOBAIS de um tenant a partir de um JSON.

Grava em tenants/{tid}/system_settings/chat.quick_messages_global pelo MESMO
caminho da API (get_system_settings/save_system_settings: whitelist de chaves,
updated_at, set(merge=True)) — nenhum outro campo do doc e tocado.

Semantica: APPEND. Atalho que ja existe no tenant (comparacao case-insensitive,
com ou sem "/") e pulado, nunca sobrescrito — rodar 2x nao duplica. A lista
anterior e salva num JSON ao lado deste script; reverter = --undo <arquivo>.

Formato de entrada (lista JSON), aceita os dois:
  - nosso:      [{"shortcut": "/t", "message": "..."}]
  - CRM antigo: [{"shortcut": "/t", "title": "...", "text": "..."}]   (title e descartado)

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"   # prod Oregon (gcloud config aponta pro projeto VELHO)
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.import_quick_messages_global --tenant varizemed --file lista.json          # dry-run
  ./.venv/Scripts/python.exe -m scripts.import_quick_messages_global --tenant varizemed --file lista.json --apply
  ./.venv/Scripts/python.exe -m scripts.import_quick_messages_global --tenant varizemed --undo scripts/_backfill_undo_quick_messages_varizemed_<ts>.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client, tenant_context, tenant_doc_ref  # noqa: E402
from database_firestore import get_system_settings, save_system_settings  # noqa: E402


def _key(shortcut):
    s = str(shortcut or "").strip()
    return (s if s.startswith("/") else "/" + s).lower()


def load_entries(path):
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("arquivo precisa ser uma lista JSON")
    out = []
    for i, row in enumerate(rows):
        shortcut = str(row.get("shortcut") or "").strip()
        message = row.get("message") if row.get("message") is not None else row.get("text")
        message = str(message or "").strip()
        if not shortcut or not message:
            raise SystemExit(f"entrada #{i}: shortcut ou mensagem vazio: {row!r}")
        if not shortcut.startswith("/"):
            shortcut = "/" + shortcut
        out.append({"shortcut": shortcut, "message": message})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--file", help="JSON com as mensagens a importar")
    ap.add_argument("--apply", action="store_true", help="grava (sem isso e dry-run)")
    ap.add_argument("--undo", help="arquivo de undo gerado por um --apply anterior")
    args = ap.parse_args()

    if not os.environ.get("FIRESTORE_PROJECT_ID"):
        raise SystemExit("FIRESTORE_PROJECT_ID nao setado — passe explicito (gcloud config aponta pro projeto errado)")
    client = get_firestore_client()
    prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm")
    print(f"projeto={client.project} prefixo={prefix} tenant={args.tenant} modo={'APPLY' if args.apply else 'dry-run'}")
    if not tenant_doc_ref(args.tenant).get().exists:
        raise SystemExit(f"tenant '{args.tenant}' nao existe em {prefix}_tenants")

    with tenant_context(args.tenant):
        current = list(get_system_settings().get("quick_messages_global") or [])

        if args.undo:
            prev = json.loads(Path(args.undo).read_text(encoding="utf-8"))
            if prev.get("tenant") != args.tenant:
                raise SystemExit(f"undo e do tenant '{prev.get('tenant')}', nao de '{args.tenant}'")
            restore = list(prev.get("quick_messages_global") or [])
            print(f"undo: lista atual tem {len(current)}; restaurando {len(restore)}")
            if not args.apply:
                print("dry-run: nada gravado (use --apply junto com --undo)")
                return
            result = save_system_settings({"quick_messages_global": restore})
            print(f"restaurado: {len(result.get('quick_messages_global') or [])} mensagens globais")
            return

        if not args.file:
            raise SystemExit("--file obrigatorio (ou --undo)")
        entries = load_entries(args.file)
        existing = {_key(q.get("shortcut")) for q in current if q.get("shortcut")}
        added, skipped, seen = [], [], set()
        for entry in entries:
            k = _key(entry["shortcut"])
            if k in existing or k in seen:
                skipped.append(entry)
                continue
            seen.add(k)
            added.append(entry)

        print(f"atual={len(current)} no arquivo={len(entries)} novas={len(added)} puladas(atalho ja existe/duplicado)={len(skipped)}")
        for q in current:
            print(f"  . {str(q.get('shortcut')):26} (ja existia) {str(q.get('message'))[:60]}")
        for entry in added:
            print(f"  + {entry['shortcut']:26} {entry['message'][:60]}")
        for entry in skipped:
            print(f"  = {entry['shortcut']:26} PULADA")
        if not added:
            print("nada a fazer")
            return
        if not args.apply:
            print("dry-run: nada gravado (use --apply)")
            return

        undo_path = Path(__file__).with_name(
            f"_backfill_undo_quick_messages_{args.tenant}_{time.strftime('%Y%m%d_%H%M%S')}.json")
        undo_path.write_text(
            json.dumps({"tenant": args.tenant, "quick_messages_global": current}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        result = save_system_settings({"quick_messages_global": current + added})
        final = result.get("quick_messages_global") or []
        print(f"gravado: {len(final)} mensagens globais | undo: {undo_path}")


if __name__ == "__main__":
    main()
