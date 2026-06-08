# -*- coding: utf-8 -*-
"""Importador do backup de conversas WhatsApp (caixa "Backup").

Le os JSONs exportados (1 por contato) e cria, no tenant, conversas
HISTORICAS marcadas is_backup (sentinela "__backup__") — visiveis so a
admin/supervisor na aba Backup. NAO toca phone_routing/registro de numero.

- Resolve o canal pelo NOSSO numero (Phone das msgs de saida) -> casa o
  conversation_id com o que o webhook gera ao vivo, pra a msg nova do cliente
  ANEXAR na conversa do backup (sobe pro topo + nao-lida), sem ir pra Novos.
- Idempotente (dedup por Message Id). Dry-run por default.
- LGPD: loga so contagens e wa_id MASCARADO; nunca telefone/conteudo. A pasta
  de backup e GITIGNORED — nunca commitar os JSONs.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.import_backup_hubloc --dir "backup_test" --dry-run
  ./.venv/Scripts/python.exe -m scripts.import_backup_hubloc --dir "backup_test" --confirm
  ./.venv/Scripts/python.exe -m scripts.import_backup_hubloc --dir "backup hubloc" --confirm
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import set_tenant_context, get_firestore_client, collection_name  # noqa: E402
import database_firestore as db  # noqa: E402


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _mask(wa_id: str) -> str:
    s = str(wa_id or "")
    return (s[:4] + "*" * max(0, len(s) - 6) + s[-2:]) if len(s) > 6 else "***"


def _msg_type_and_content(m: dict):
    """chat -> (text, Message). Midia (so metadata no JSON) -> placeholder texto."""
    raw = str(m.get("Message Type") or "chat").lower()
    msg = m.get("Message") or ""
    cap = m.get("Caption") or ""
    fname = m.get("File Name") or ""
    if raw in ("chat", "text", ""):
        return "text", msg
    label = {"image": "imagem", "video": "video", "ptt": "audio", "audio": "audio",
             "document": "documento", "sticker": "figurinha", "location": "localizacao"}.get(raw, raw)
    extra = cap or fname
    return "text", f"[{label} — backup, midia indisponivel]" + (f" {extra}" if extra else "")


def _build_channel_map(c):
    """{ digitos_normalizados: channel_id } a partir dos canais (display_phone_number),
    incluindo variantes com/sem 9 (Brasil)."""
    out = {}
    for snap in c.collection(collection_name("channels")).stream():
        d = snap.to_dict() or {}
        cid = d.get("id", snap.id)
        for raw in (d.get("display_phone_number"), d.get("phone_number_id")):
            dd = _digits(raw)
            if not dd:
                continue
            for v in db.wa_id_variants(dd) or [dd]:
                out.setdefault(v, cid)
            out.setdefault(dd, cid)
    return out


def _resolve_channel_id(our_digits: str, channel_map: dict):
    for v in (db.wa_id_variants(our_digits) or [our_digits]):
        if v in channel_map:
            return channel_map[v]
    return channel_map.get(our_digits)


def process_file(path: str, channel_map: dict, confirm: bool, stats: dict):
    with open(path, "r", encoding="utf-8") as fh:
        msgs = json.load(fh)
    if not isinstance(msgs, list) or not msgs:
        stats["skipped_empty"] += 1
        return

    def is_out(m):
        return str(m.get("Message Id", "")).startswith("true_") or m.get("Formatted Name") == "Você"

    # Nosso numero (saida) -> canal
    our_raw = next((m.get("Phone") for m in msgs if is_out(m)), None)
    our_digits = _digits(our_raw)
    channel_id = _resolve_channel_id(our_digits, channel_map) if our_digits else None
    if not channel_id:
        stats["skipped_no_channel"] += 1
        print(f"  SKIP (canal nao resolvido p/ nosso numero {_mask(our_digits)}): {os.path.basename(path)}")
        return

    # Cliente (entrada) -> wa_id
    client_raw = next((m.get("Phone") for m in msgs if not is_out(m)), None)
    if not client_raw:
        client_raw = next((m.get("Phone") for m in msgs if _digits(m.get("Phone")) != our_digits), None)
    if not client_raw:
        stats["skipped_no_client"] += 1
        return
    wa_id = db.normalize_br_phone(_digits(client_raw))
    if _digits(client_raw) != wa_id:
        stats["normalized_9"] += 1

    # Nome do cliente: Formatted Name de uma entrada que nao seja so o telefone
    cli_name = ""
    for m in msgs:
        if not is_out(m):
            fn = (m.get("Formatted Name") or "").strip()
            # Nome real do cliente (entrada que nao seja so o telefone "+55 ...").
            if fn and not fn.startswith("+"):
                cli_name = fn
                break

    # Ordena asc por Message Time (antigas -> novas)
    def _ts(m):
        return str(m.get("Message Time") or "")
    msgs_asc = sorted(msgs, key=_ts)
    first_ts = _ts(msgs_asc[0]) or None
    last_ts = _ts(msgs_asc[-1]) or None
    last_in = next((_ts(m) for m in reversed(msgs_asc) if not is_out(m)), None)
    last_out = next((_ts(m) for m in reversed(msgs_asc) if is_out(m)), None)

    existing = db._find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        stats["collisions"] += 1
        print(f"  COLISAO (contato ja existe p/ {_mask(wa_id)}): anexa mensagens, nao rebaixa")

    stats["files"] += 1
    stats["contacts"] += 0 if existing else 1
    stats["messages"] += len(msgs_asc)

    if not confirm:
        return

    set_label = "Backup — " + (str(our_raw) if our_raw else "")
    contact_id = db.create_backup_contact(wa_id, cli_name, channel_id, first_ts, last_ts)
    conversation_id = db._make_conversation_id(channel_id, wa_id)
    db.upsert_backup_conversation(conversation_id, contact_id, wa_id, channel_id,
                                  first_ts, last_ts, last_in, last_out, channel_label=set_label)
    for m in msgs_asc:
        mid = str(m.get("Message Id") or "")
        direction = "outbound" if is_out(m) else "inbound"
        mtype, content = _msg_type_and_content(m)
        db.write_backup_message(
            wa_message_id="backup_" + mid if mid else "",
            contact_id=contact_id, conversation_id=conversation_id,
            direction=direction, msg_type=mtype, content=content,
            timestamp_wa=_ts(m), channel_id=channel_id,
            filename=m.get("File Name") or "", status="read",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa backup de conversas WhatsApp p/ a caixa Backup.")
    ap.add_argument("--dir", default="backup hubloc", help="Pasta com os JSONs.")
    ap.add_argument("--tenant-id", default="hubloc")
    ap.add_argument("--confirm", action="store_true", help="Grava de fato. Sem isso, dry-run.")
    args = ap.parse_args()

    set_tenant_context(args.tenant_id)
    c = get_firestore_client()
    channel_map = _build_channel_map(c)

    base = Path(__file__).resolve().parent.parent
    files = sorted(glob.glob(str(base / args.dir / "*.json")))

    stats = {"files": 0, "contacts": 0, "messages": 0, "collisions": 0,
             "skipped_empty": 0, "skipped_no_channel": 0, "skipped_no_client": 0, "normalized_9": 0}

    print(f"=== Import backup | dir='{args.dir}' tenant={args.tenant_id} "
          f"modo={'CONFIRMED (grava)' if args.confirm else 'DRY-RUN'} | {len(files)} arquivos ===")
    print(f"  canais mapeados (variantes): {len(channel_map)}")
    for path in files:
        try:
            process_file(path, channel_map, args.confirm, stats)
        except Exception as exc:
            stats.setdefault("errors", 0)
            stats["errors"] = stats.get("errors", 0) + 1
            print(f"  ERRO em {os.path.basename(path)}: {exc}")

    print("--- resumo ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not args.confirm:
        print("  [DRY-RUN] Nada gravado. Use --confirm para aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
