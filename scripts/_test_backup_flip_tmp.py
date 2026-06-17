# -*- coding: utf-8 -*-
"""Teste REVERSIVEL: coloca a conversa de um numero em estado de Backup
(is_backup=True no contato + conversas) para validar a graduacao via
reatribuir-lead. Sempre grava um arquivo de UNDO antes de mexer.

LGPD: nunca imprime telefone/conteudo — so wa_id mascarado e metadados.

Uso (PowerShell) — projeto Oregon (prod):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._test_backup_flip_tmp --phone 553183440484 --mode inspect
  ./.venv/Scripts/python.exe -m scripts._test_backup_flip_tmp --phone 553183440484 --mode apply
  ./.venv/Scripts/python.exe -m scripts._test_backup_flip_tmp --mode undo --undo-file scripts/_undo_xxx.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import set_tenant_context, collection as col, document as doc  # noqa: E402
import database_firestore as db  # noqa: E402

BASE = Path(__file__).resolve().parent


def _mask(s) -> str:
    s = str(s or "")
    return (s[:4] + "*" * max(0, len(s) - 6) + s[-2:]) if len(s) > 6 else "***"


def _resolve(phone, tenant):
    set_tenant_context(tenant)
    raw = "".join(c for c in str(phone) if c.isdigit())
    wa_id = db.normalize_br_phone(raw)
    contact = db._find_contact_by_wa_id_any_variant(wa_id)
    if not contact:
        return wa_id, None, []
    convs = [(s.id, s.to_dict() or {})
             for s in col("wa_conversations").where("contact_id", "==", contact["id"]).stream()]
    return wa_id, contact, convs


def inspect(phone, tenant):
    wa_id, contact, convs = _resolve(phone, tenant)
    print(f"=== INSPECT (read-only) | tenant={tenant} | wa_id(masc)={_mask(wa_id)} ===")
    if not contact:
        print("  CONTATO NAO ENCONTRADO neste tenant.")
        return
    print(f"  CONTACT id={contact['id']} is_backup={contact.get('is_backup')} "
          f"assigned_to={contact.get('assigned_to')} assigned_uid={str(contact.get('assigned_to_uid'))[:10]}")
    for cid, c in convs:
        nmsg = sum(1 for _ in col("wa_messages").where("conversation_id", "==", cid).stream())
        print(f"  CONV {cid}: is_backup={c.get('is_backup')} assigned_to={c.get('assigned_to')} "
              f"attendance={c.get('attendance_status')} channel_id={c.get('channel_id')} "
              f"label={c.get('channel_label')!r} msgs={nmsg}")


def apply(phone, tenant):
    wa_id, contact, convs = _resolve(phone, tenant)
    if not contact:
        print("  CONTATO NAO ENCONTRADO — nada feito.")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    undo = {"tenant": tenant, "wa_id": wa_id, "stamp": stamp, "contacts": [], "conversations": []}

    # captura estado original (so os campos que vou tocar)
    undo["contacts"].append({"id": contact["id"], "is_backup": contact.get("is_backup")})
    for cid, c in convs:
        undo["conversations"].append({"id": cid, "is_backup": c.get("is_backup")})

    undo_path = BASE / f"_undo_backupflip_{stamp}.json"
    undo_path.write_text(json.dumps(undo, indent=2, default=str), encoding="utf-8")
    print(f"=== APPLY | undo salvo em: {undo_path} ===")

    # flip minimo e suficiente: is_backup=True no contato + conversas.
    # (NAO toco assigned_to nem mensagens — a thread vai pro Backup e a
    # graduacao via reatribuir-lead exige contact.is_backup e conv.is_backup.)
    doc("wa_contacts", contact["id"]).set({"is_backup": True}, merge=True)
    print(f"  contact {contact['id']}: is_backup -> True")
    for cid, c in convs:
        doc("wa_conversations", cid).set({"is_backup": True}, merge=True)
        print(f"  conv {cid}: is_backup -> True")
    print("  >>> Agora a conversa esta na Caixa Backup. Faca 'Reatribuir Lead' para o operador e observe o 'Meus'.")
    print(f"  >>> Para reverter: --mode undo --undo-file {undo_path.as_posix()}")
    return 0


def undo(undo_file):
    data = json.loads(Path(undo_file).read_text(encoding="utf-8"))
    set_tenant_context(data["tenant"])
    print(f"=== UNDO | tenant={data['tenant']} | de {undo_file} ===")
    for c in data.get("contacts", []):
        doc("wa_contacts", c["id"]).set({"is_backup": c.get("is_backup")}, merge=True)
        print(f"  contact {c['id']}: is_backup -> {c.get('is_backup')} (restaurado)")
    for cv in data.get("conversations", []):
        doc("wa_conversations", cv["id"]).set({"is_backup": cv.get("is_backup")}, merge=True)
        print(f"  conv {cv['id']}: is_backup -> {cv.get('is_backup')} (restaurado)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone")
    ap.add_argument("--tenant-id", default="hubloc")
    ap.add_argument("--mode", choices=["inspect", "apply", "undo"], required=True)
    ap.add_argument("--undo-file")
    a = ap.parse_args()
    if a.mode == "undo":
        if not a.undo_file:
            print("--undo-file obrigatorio no modo undo"); return 1
        return undo(a.undo_file)
    if not a.phone:
        print("--phone obrigatorio"); return 1
    if a.mode == "inspect":
        inspect(a.phone, a.tenant_id); return 0
    return apply(a.phone, a.tenant_id)


if __name__ == "__main__":
    sys.exit(main())
