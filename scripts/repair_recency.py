# -*- coding: utf-8 -*-
"""Repara last_message_at de conversas e contatos a partir do timestamp_wa REAL
das mensagens (max por conversa/contato). Corrige a poluicao de recencia causada
por replay de history pre-patch (lma carimbado com a hora da gravacao).

Rode apos grandes syncs de historico (onboarding coex re-importa ~180 dias e o
CREATE de contato ainda usa a hora corrente). Dry-run por default.

Uso:
  $env:FIRESTORE_PROJECT_ID="project-4a851bf9-f475-418c-800"
  ./.venv/Scripts/python.exe scripts/repair_recency.py            # dry-run
  ./.venv/Scripts/python.exe scripts/repair_recency.py --confirm
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client, collection_name, set_tenant_context  # noqa: E402

TENANT = "hubloc"
EPS = timedelta(seconds=120)  # ignora divergencias pequenas (corrida com trafego vivo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()

    set_tenant_context(TENANT)
    c = get_firestore_client()
    tn = c.collection(collection_name("tenants")).document(TENANT)

    # 1 passada: max(timestamp_wa) por conversa e por contato
    max_conv: dict = {}
    max_ct: dict = {}
    n = 0
    for s in tn.collection("wa_messages").stream():
        d = s.to_dict() or {}
        n += 1
        ts = d.get("timestamp_wa") or d.get("created_at")
        if not isinstance(ts, datetime):
            continue
        cv = d.get("conversation_id")
        ct = d.get("contact_id")
        if cv and (cv not in max_conv or ts > max_conv[cv]):
            max_conv[cv] = ts
        if ct is not None and (ct not in max_ct or ts > max_ct[ct]):
            max_ct[ct] = ts
    print(f"mensagens lidas: {n} | conversas c/ msg: {len(max_conv)} | contatos c/ msg: {len(max_ct)}", flush=True)

    def repair(col, key_field, real_by_key):
        fix = []
        for s in tn.collection(col).stream():
            d = s.to_dict() or {}
            key = d.get(key_field) if key_field != "__docid__" else s.id
            real = real_by_key.get(key)
            if real is None:
                continue
            cur = d.get("last_message_at")
            if isinstance(cur, datetime):
                try:
                    if abs(cur - real) <= EPS:
                        continue
                except TypeError:
                    pass
            fix.append((s.reference, real))
        print(f"{col}: {len(fix)} docs com recencia divergente", flush=True)
        if not a.confirm:
            return 0
        b = c.batch(); cnt = 0; total = 0
        for ref, real in fix:
            b.set(ref, {"last_message_at": real}, merge=True)
            cnt += 1; total += 1
            if cnt >= 400:
                b.commit(); b = c.batch(); cnt = 0
        if cnt:
            b.commit()
        return total

    nv = repair("wa_conversations", "__docid__", max_conv)
    nc = repair("wa_contacts", "id", max_ct)
    if a.confirm:
        print(f"REPARO OK: {nv} conversas + {nc} contatos corrigidos", flush=True)
    else:
        print("DRY-RUN — use --confirm para aplicar.", flush=True)


if __name__ == "__main__":
    main()
