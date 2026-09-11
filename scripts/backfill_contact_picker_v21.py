# -*- coding: utf-8 -*-
"""Backfill + reconciliacao do picker v2.1 (docs/PICKER_V2_1_AGENDA_PAGINADA.md §11).

Por contato do tenant:
  1. Campos de busca derivados via build_contact_search_fields (A MESMA funcao
     do write-path — importada de database_firestore, nunca duplicada).
  2. Canonicalizacao POR TIPO dos filtros das queries novas:
     is_archived -> int 0/1; is_backup -> bool; qualification vazia -> "novo";
     assigned_to_uid: dono resolve do usuario, pool vira "" (inclusive uid
     orfao de lead sem dono — contado a parte), par backup (is_backup=True +
     sentinela "__backup__") NUNCA e tocado, inconsistencia vira anomalia.
  3. So escreve doc cujo resultado REALMENTE mudou (idempotente; re-rodar e o
     proprio checkpoint). Valores ANTERIORES dos campos alterados vao pra um
     undo JSONL (fora do controle de versao; scripts/_* esta no .gitignore).

Uso:
  python scripts/backfill_contact_picker_v21.py --tenant varizemed-test           (dry-run, default)
  python scripts/backfill_contact_picker_v21.py --tenant varizemed-test --apply

ORDEM OBRIGATORIA (revisao adversarial F2a): deploy do dual-write ANTES do
--apply; depois re-rodar dry-run ate "a alterar: 0" (cobre docs criados
durante o run pelo codigo novo).

NUNCA imprime nome/telefone — so ids e contadores.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore  # noqa: E402

from database_firestore import (  # noqa: E402
    SEARCH_SCHEMA_VERSION,
    build_contact_search_fields,
)

PROJECT = "project-4a851bf9-f475-418c-800"
PREFIX = "castro_crm"
TENANTS_VALIDOS = ("hubloc", "varizemed", "varizemed-test")
BATCH_MAX = 400          # < limite de 500 do Firestore
SLEEP_ENTRE_LOTES = 1.0  # rampa de escrita: fica < 500 writes/s no hotspot
                         # do indice single-field novo (revisao F2a)

SEARCH_KEYS = (
    "sort_key", "name_normalized", "name_prefixes", "phone_e164_digits",
    "phone_national", "phone_local", "wa_id_reversed", "search_schema_version",
)
_AUSENTE = "__AUSENTE__"  # marcador de campo inexistente no undo


def _as_int(v):
    """Int defensivo: bool NAO e dono valido (True viraria usuario 1)."""
    if isinstance(v, bool):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True, choices=TENANTS_VALIDOS)
    ap.add_argument("--apply", action="store_true",
                    help="escreve de verdade (default: dry-run)")
    args = ap.parse_args()

    db = firestore.Client(project=PROJECT)
    base = f"{PREFIX}_tenants/{args.tenant}"
    col = db.collection(f"{base}/wa_contacts")

    # Mapa users -> firebase_uid pra reconciliar assigned_to_uid.
    users = {}
    for u in db.collection(f"{base}/users").stream():
        d = u.to_dict() or {}
        k = _as_int(d.get("id") if d.get("id") is not None else u.id)
        if k is not None:
            users[k] = str(d.get("firebase_uid") or "")

    undo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             f"_backfill_picker_undo_{args.tenant}.jsonl")
    undo_f = open(undo_path, "a", encoding="utf-8") if args.apply else None

    total = alterados = ja_ok = falhas = escritos = 0
    mudancas_por_campo = {}
    anomalias_dono = []    # dono sem usuario/uid resolvivel
    anomalias_backup = []  # par (is_backup, sentinela) inconsistente
    uid_orfao_limpo = 0    # pool com uid legado nao-vazio -> ""
    docs_falha = []
    batch = db.batch()
    pend = []  # (ref, updates, undo_row) do lote atual

    def _commit():
        nonlocal batch, pend, falhas, escritos
        if not pend:
            return
        try:
            batch.commit()
            escritos += len(pend)
            if undo_f:
                for _, _, row in pend:
                    undo_f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                undo_f.flush()
        except Exception as exc:  # noqa: BLE001
            falhas += len(pend)
            docs_falha.extend(r[2]["id"] for r in pend)
            print(f"  !! commit de {len(pend)} docs FALHOU: {type(exc).__name__}: {exc}")
        batch = db.batch()
        pend = []
        time.sleep(SLEEP_ENTRE_LOTES)

    try:
        for snap in col.stream():
            total += 1
            try:
                c = snap.to_dict() or {}
                updates = {}

                # 1) Campos de busca derivados.
                desejado = build_contact_search_fields(c)
                for k in SEARCH_KEYS:
                    if c.get(k) != desejado[k]:
                        updates[k] = desejado[k]

                # 2) Canonicalizacao POR TIPO (igualdade no Firestore e
                # sensivel a tipo: where(is_archived==0) nao casa False).
                ia = c.get("is_archived")
                if isinstance(ia, bool) or not isinstance(ia, int):
                    updates["is_archived"] = 1 if ia else 0
                if not str(c.get("qualification") or "").strip():
                    updates["qualification"] = "novo"

                uid_atual = c.get("assigned_to_uid")
                is_bkp_flag = c.get("is_backup") is True
                is_bkp = is_bkp_flag or uid_atual == "__backup__"
                if is_bkp:
                    # Par backup: NAO tocar em is_backup nem no sentinela.
                    # Inconsistencia (um lado so) = anomalia pra correcao
                    # manual — jamais "consertar" pro lado errado (rebaixar
                    # backup pra pool quebraria o listener do operador).
                    if not (is_bkp_flag and uid_atual == "__backup__"):
                        anomalias_backup.append(snap.id)
                else:
                    if not isinstance(c.get("is_backup"), bool):
                        updates["is_backup"] = bool(c.get("is_backup"))
                    dono = c.get("assigned_to")
                    dono_int = _as_int(dono)
                    if dono not in (None, "", 0):
                        uid_certo = users.get(dono_int) if dono_int is not None else None
                        if not uid_certo:
                            anomalias_dono.append(snap.id)
                        elif uid_atual != uid_certo:
                            updates["assigned_to_uid"] = uid_certo
                    else:
                        # Pool: null/ausente E uid legado nao-vazio viram ""
                        # (query unica `in [uid, ""]`; uid orfao esconderia o
                        # lead da pool e o mostraria a um dono fantasma).
                        if uid_atual != "":
                            if uid_atual:
                                uid_orfao_limpo += 1
                            updates["assigned_to_uid"] = ""

                if not updates:
                    ja_ok += 1
                    continue
                alterados += 1
                for k in updates:
                    mudancas_por_campo[k] = mudancas_por_campo.get(k, 0) + 1
                if args.apply:
                    undo_row = {"id": snap.id,
                                **{k: c.get(k, _AUSENTE) for k in updates}}
                    batch.set(snap.reference, updates, merge=True)
                    pend.append((snap.reference, updates, undo_row))
                    if len(pend) >= BATCH_MAX:
                        _commit()
                        print(f"  ... {escritos} escritos")
            except Exception as exc:  # noqa: BLE001
                falhas += 1
                docs_falha.append(snap.id)
                print(f"  !! doc {snap.id} falhou: {type(exc).__name__}: {exc}")
        if args.apply:
            _commit()
    finally:
        if undo_f:
            undo_f.close()
        modo = "APPLY" if args.apply else "DRY-RUN"
        print(f"\n[{modo}] tenant={args.tenant} schema=v{SEARCH_SCHEMA_VERSION}")
        print(f"  lidos: {total} | a alterar: {alterados} | ja ok: {ja_ok} | "
              f"escritos: {escritos} | falhas: {falhas}")
        for k in sorted(mudancas_por_campo, key=lambda x: -mudancas_por_campo[x]):
            print(f"    {k}: {mudancas_por_campo[k]}")
        if uid_orfao_limpo:
            print(f"  uid orfao de pool limpo: {uid_orfao_limpo} (lead volta a ser visivel na pool)")
        for nome, lista in (("dono-sem-uid", anomalias_dono),
                            ("par-backup-inconsistente", anomalias_backup)):
            if lista:
                print(f"  ANOMALIAS {nome} ({len(lista)}): ids {lista[:20]}"
                      + (" ..." if len(lista) > 20 else ""))
                print("  -> corrigir ANTES do cutover do endpoint (gate §11).")
            else:
                print(f"  anomalias {nome}: 0")
        if docs_falha:
            print(f"  DOCS COM FALHA ({len(docs_falha)}): {docs_falha[:20]}"
                  + (" ..." if len(docs_falha) > 20 else ""))
            print("  -> re-rodar o script (idempotente) apos investigar.")
        if args.apply:
            print(f"  undo: {undo_path}")
    return 1 if docs_falha else 0


if __name__ == "__main__":
    sys.exit(main())
