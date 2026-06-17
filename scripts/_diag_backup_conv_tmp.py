# -*- coding: utf-8 -*-
"""Diag READ-ONLY de uma conversa de backup: por que last_message_at avancou
sem mensagem nova visivel.

NAO escreve nada. LGPD: nunca imprime telefone nem conteudo — so wa_id
MASCARADO, tipos/datas dos campos e tamanho do conteudo. Mostra o TIPO de
cada timestamp (datetime vs str) pra flagrar o bug data-como-texto, e busca
as mensagens SEM order_by (sort em Python) pra capturar ate msgs com
timestamp_wa ausente que a query do front (orderBy timestamp_wa) esconderia.

Uso (PowerShell) — passar o projeto EXPLICITO (cutover Oregon):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"   # ou o antigo
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_backup_conv_tmp --phone "5531998159547"
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import set_tenant_context, collection as fs_collection  # noqa: E402
import database_firestore as db  # noqa: E402


def _mask(wa_id) -> str:
    s = str(wa_id or "")
    return (s[:4] + "*" * max(0, len(s) - 6) + s[-2:]) if len(s) > 6 else "***"


def _t(v) -> str:
    """Descreve um valor de timestamp sem vazar PII: tipo + valor (datas sao OK)."""
    if v is None:
        return "None"
    if isinstance(v, datetime):
        return f"datetime({v.isoformat()})"
    if isinstance(v, str):
        return f"STR({v!r})"  # <- STR = bug data-como-texto (ordena acima de datetime)
    return f"{type(v).__name__}({v!r})"


def _show_doc(label, d, fields):
    print(f"\n[{label}]")
    if not d:
        print("  (nao encontrado)")
        return
    for f in fields:
        print(f"  {f:22s}= {_t(d.get(f)) if 'at' in f or 'time' in f else d.get(f)!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone", required=True, help="Digitos do cliente, ex 5531998159547")
    ap.add_argument("--tenant-id", default="hubloc")
    ap.add_argument("--limit", type=int, default=25, help="Ultimas N mensagens a mostrar")
    args = ap.parse_args()

    set_tenant_context(args.tenant_id)
    print(f"=== DIAG READ-ONLY | tenant={args.tenant_id} | "
          f"project={os.environ.get('FIRESTORE_PROJECT_ID') or '(ADC default)'} | "
          f"prefix={os.environ.get('FIRESTORE_COLLECTION_PREFIX') or '(none)'} ===")

    raw = "".join(ch for ch in args.phone if ch.isdigit())
    wa_id = db.normalize_br_phone(raw)
    variants = db.wa_id_variants(raw) or [raw]
    print(f"phone(masc)={_mask(raw)} -> wa_id_norm(masc)={_mask(wa_id)} variants={len(variants)}")

    # 1) Contato
    contact = db._find_contact_by_wa_id_any_variant(wa_id)
    _show_doc("CONTACT (wa_contacts)", contact,
              ["id", "is_backup", "last_message_at", "first_seen_at", "last_inbound_at",
               "unread_count", "channel_id", "assigned_to", "assigned_to_uid"])

    # 2) Conversas com esse wa_id (qualquer variante) — SEM filtrar is_backup.
    seen = set()
    convs = []
    for v in set(variants) | {wa_id}:
        for snap in fs_collection("wa_conversations").where("wa_id", "==", v).stream():
            if snap.id in seen:
                continue
            seen.add(snap.id)
            convs.append((snap.id, snap.to_dict() or {}))
    print(f"\n>>> {len(convs)} conversa(s) para esse wa_id")

    for cid, conv in convs:
        _show_doc(f"CONVERSATION {cid}", conv,
                  ["id", "is_backup", "channel_active", "attendance_status", "status",
                   "channel_id", "channel_label", "last_message_at", "created_at",
                   "last_inbound_at", "last_outbound_at", "unread_count",
                   "assigned_to", "assigned_to_uid"])

        # 3) Mensagens dessa conversa — SEM order_by (sort em Python) pra capturar
        #    ate msgs com timestamp_wa ausente que o front esconderia.
        msgs = [s.to_dict() or {} for s in
                fs_collection("wa_messages").where("conversation_id", "==", cid).stream()]

        def _key(m):
            v = m.get("timestamp_wa") or m.get("created_at")
            return (1, v.isoformat()) if isinstance(v, datetime) else (0, str(v or ""))

        msgs.sort(key=_key)
        miss = sum(1 for m in msgs if not isinstance(m.get("timestamp_wa"), datetime))
        bkp = sum(1 for m in msgs if m.get("is_backup") is True)
        print(f"    total msgs={len(msgs)} | is_backup={bkp} | live/non-backup={len(msgs) - bkp} "
              f"| timestamp_wa NAO-datetime={miss}")
        print(f"    --- ultimas {min(args.limit, len(msgs))} (asc) ---")
        for m in msgs[-args.limit:]:
            wid = str(m.get("wa_message_id") or "")
            print(f"      ts={_t(m.get('timestamp_wa')):42s} dir={str(m.get('direction')):8s} "
                  f"type={str(m.get('msg_type')):10s} bkp={str(m.get('is_backup')):5s} "
                  f"created={_t(m.get('created_at')):42s} "
                  f"len(content)={len(str(m.get('content') or '')):4d} "
                  f"mid={wid[:14]}... status={m.get('status')}")

    print("\n=== fim (nada gravado) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
