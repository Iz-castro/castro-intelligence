# -*- coding: utf-8 -*-
"""Reparo de recencia ESCOPADO por canal (history sync do coex, incidente 2026-10-14).

Contexto: ate o fix de 2026-10-14, o _process_history (webhook.py) carimbava
last_message_at=agora na conversa e last_message_at/last_inbound_at=agora no
contato a cada fase ou re-entrega do history sync do coex. Conversas antigas
ficavam "recentes" e empurravam as reais para fora da janela top-50 do Meus (e
da top-300 da Equipe); contatos antigos ficavam com a janela de 24h "aberta".

O que faz, para cada canal informado:
  conversa: real = timestamp_wa da ultima mensagem DA conversa, ignorando
            banner automatico de sistema (direction=system sem operator_id —
            gravado com advance_recency=False e timestamp=agora).
            last_message_at > real + EPS  ->  last_message_at = real
  contato (de cada conversa acima): real = idem, sobre TODAS as mensagens do
            contato; real_in = timestamp_wa da ultima inbound.
            last_message_at > real + EPS     ->  corrige
            last_inbound_at > real_in + EPS  ->  corrige (sem inbound nenhuma
            numa varredura COMPLETA -> None = "nunca escreveu", exige template;
            varredura incompleta sem inbound -> nao mexe)
Nunca AUMENTA valor. Conversa sem mensagem -> nao mexe (so reporta).
Escrita com PRECONDICAO de update_time: doc alterado depois da leitura (trafego
vivo) e pulado e reportado — rodar de novo resolve. Idempotente.

ORDEM: rodar DEPOIS do deploy do fix do webhook (antes dele, a proxima entrega
do history volta a inflar). Rodar de novo apos o deploy nao faz mal.

Dry-run por default (escrita travada no cliente). --apply grava um JSON de
desfazer em logs/ (gitignored; contem ids de conversa = canal__wa_id) ANTES de
escrever. --undo ARQUIVO restaura os valores antigos (so onde o valor atual
ainda e o que o reparo gravou).

Uso (PowerShell, raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.repair_recency_channels --tenant hubloc --channels 8,9,10
  ./.venv/Scripts/python.exe -m scripts.repair_recency_channels --tenant hubloc --channels 8,9,10 --apply
  ./.venv/Scripts/python.exe -m scripts.repair_recency_channels --undo logs/undo_recency_hubloc_<stamp>.json
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EPS = timedelta(seconds=120)
CONV_SCAN = 20
CONTACT_SCAN = 200
BRT = timezone(timedelta(hours=-3))
LOGS = ROOT / "logs"


def trava_escrita():
    from google.cloud.firestore_v1 import batch, collection, document, transaction

    def _b(*_a, **_k):
        raise RuntimeError("dry-run: escrita no Firestore bloqueada")

    for cls, nomes in (
        (document.DocumentReference, ("set", "update", "delete", "create")),
        (collection.CollectionReference, ("add",)),
        (batch.WriteBatch, ("commit",)),
        (transaction.Transaction, ("commit",)),
    ):
        for n in nomes:
            setattr(cls, n, _b)


def ts(v, dbf):
    if v in (None, ""):
        return None
    v = dbf._coerce_timestamp(v)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return None


def fmt(v):
    return v.astimezone(BRT).strftime("%d/%m %H:%M") if isinstance(v, datetime) else "-"


def iso(v):
    return v.isoformat() if isinstance(v, datetime) else None


def automatic_banner(m):
    """Banner automatico de sistema (cron, devolucao de takeover, release):
    direction=system SEM operator_id. Grava timestamp=agora com
    advance_recency=False — nao e atividade real da conversa."""
    return m.get("direction") == "system" and not m.get("operator_id")


def run_undo(path):
    from google.api_core import exceptions as gex
    from firestore_common import document, set_tenant_context
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    set_tenant_context(data["tenant"])
    import database_firestore as dbf
    done = Counter()
    for ch in data["changes"]:
        ref = document(ch["col"], ch["doc"])
        snap = ref.get()
        if not snap.exists:
            done["pulado_doc_inexistente"] += 1
            continue
        cur = ts((snap.to_dict() or {}).get(ch["field"]), dbf)
        new = datetime.fromisoformat(ch["new"]) if ch["new"] else None
        same = (cur is None and new is None) or (cur and new and abs((cur - new).total_seconds()) < 1)
        if not same:
            done["pulado_valor_mudou"] += 1
            continue
        old = datetime.fromisoformat(ch["old"]) if ch["old"] else None
        try:
            ref.update({ch["field"]: old}, option=ref._client.write_option(last_update_time=snap.update_time))
            done["restaurado"] += 1
        except gex.FailedPrecondition:
            done["pulado_valor_mudou"] += 1
        except gex.GoogleAPICallError as exc:
            done["erro"] += 1
            print(f"  erro em {ch['col']}/{ch['doc']}: {type(exc).__name__}")
    print("undo:", dict(done))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="hubloc")
    ap.add_argument("--channels", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", default="")
    a = ap.parse_args()
    if a.undo:
        return run_undo(a.undo)
    channels = [int(x) for x in a.channels.split(",") if x.strip()]
    if not channels:
        ap.error("--channels obrigatorio (ex.: 8,9,10)")
    if not a.apply:
        trava_escrita()

    from google.api_core import exceptions as gex
    from firestore_common import collection, document, set_tenant_context
    set_tenant_context(a.tenant)
    import database_firestore as dbf

    now = datetime.now(timezone.utc)
    users = {(s.to_dict() or {}).get("id"): s.to_dict() or {} for s in collection("users").stream()}
    chan_owner = {}
    for s in collection("channels").stream():
        d = s.to_dict() or {}
        if str(d.get("tenant_id") or "") == a.tenant:
            chan_owner[int(d.get("id"))] = d.get("owner_user_id")

    # ---------------------------------------------------------------- conversas
    conv_plan = []      # (snap, old, new)
    conv_new_lma = {}   # conv_id -> lma corrigido (para simular janelas)
    contact_ids = set()
    stats = Counter()
    for ch in channels:
        for snap in collection("wa_conversations").where("channel_id", "==", ch).stream():
            c = snap.to_dict() or {}
            stats[f"c{ch}_threads"] += 1
            if c.get("is_backup"):
                stats[f"c{ch}_backup_pulada"] += 1
                continue
            cid_contact = c.get("contact_id")
            if cid_contact is not None:
                contact_ids.add(cid_contact)
            lma = ts(c.get("last_message_at"), dbf)
            q = (collection("wa_messages").where("contact_id", "==", cid_contact)
                 .where("conversation_id", "==", snap.id)
                 .order_by("timestamp_wa", direction="DESCENDING").limit(CONV_SCAN))
            msgs = [s.to_dict() or {} for s in q.stream()]
            stats["banners_ignorados"] += sum(1 for m in msgs if automatic_banner(m))
            real = next((ts(m.get("timestamp_wa"), dbf) for m in msgs if not automatic_banner(m)), None)
            if real is None:
                stats[f"c{ch}_sem_mensagem"] += 1
                continue
            if lma is not None and lma > real + EPS:
                conv_plan.append((snap, lma, real))
                conv_new_lma[snap.id] = real
                stats[f"c{ch}_inflada"] += 1

    # ---------------------------------------------------------------- contatos
    ct_plan = []  # (snap, field, old, new)
    window_closes = 0
    for cid_contact in sorted(contact_ids, key=lambda x: str(x)):
        snap = document("wa_contacts", cid_contact).get()
        if not snap.exists:
            stats["contato_inexistente"] += 1
            continue
        d = snap.to_dict() or {}
        if d.get("is_backup"):
            continue
        q = (collection("wa_messages").where("contact_id", "==", cid_contact)
             .order_by("timestamp_wa", direction="DESCENDING").limit(CONTACT_SCAN))
        msgs = [s.to_dict() or {} for s in q.stream()]
        if not msgs:
            stats["contato_sem_mensagem"] += 1
            continue
        real_ct = next((ts(m.get("timestamp_wa"), dbf) for m in msgs if not automatic_banner(m)), None)
        real_in = next((ts(m.get("timestamp_wa"), dbf) for m in msgs if m.get("direction") == "inbound"), None)
        full_scan = len(msgs) < CONTACT_SCAN
        lma = ts(d.get("last_message_at"), dbf)
        lia = ts(d.get("last_inbound_at"), dbf)
        if lma is not None and real_ct is not None and lma > real_ct + EPS:
            ct_plan.append((snap, "last_message_at", lma, real_ct))
            stats["contato_lma_inflado"] += 1
        if lia is not None:
            if real_in is not None and lia > real_in + EPS:
                ct_plan.append((snap, "last_inbound_at", lia, real_in))
                stats["contato_inbound_inflado"] += 1
                if now - lia <= timedelta(hours=24) and now - real_in > timedelta(hours=24):
                    window_closes += 1
            elif real_in is None and full_scan:
                ct_plan.append((snap, "last_inbound_at", lia, None))
                stats["contato_inbound_inflado_sem_inbound"] += 1
                if now - lia <= timedelta(hours=24):
                    window_closes += 1
            elif real_in is None:
                stats["contato_inbound_desconhecido"] += 1

    # ------------------------------------------------------------ relatorio
    print(f"tenant={a.tenant} canais={channels} modo={'APPLY' if a.apply else 'DRY-RUN'} agora={fmt(now)}")
    for ch in channels:
        print(f"  canal {ch} (dono user {chan_owner.get(ch)}): threads={stats[f'c{ch}_threads']} "
              f"infladas={stats[f'c{ch}_inflada']} sem_msg={stats[f'c{ch}_sem_mensagem']} "
              f"backup={stats[f'c{ch}_backup_pulada']}")
    print(f"  banners automaticos ignorados no calculo: {stats['banners_ignorados']}")
    print(f"  contatos analisados={len(contact_ids)} | last_message_at inflado={stats['contato_lma_inflado']} | "
          f"last_inbound_at inflado={stats['contato_inbound_inflado'] + stats['contato_inbound_inflado_sem_inbound']} "
          f"(sem inbound real={stats['contato_inbound_inflado_sem_inbound']}, desconhecido={stats['contato_inbound_desconhecido']})")
    print(f"  janelas de 24h FALSAMENTE abertas que fecham com o reparo: {window_closes}")

    # Simulacao: janela top-50 do Meus por dono, antes x depois
    print("\n  Meus (top-50 por last_message_at), antes -> depois:")
    owners = sorted({chan_owner.get(ch) for ch in channels if chan_owner.get(ch)})
    for owner in owners:
        u = users.get(owner) or {}
        rows = [(s.id, s.to_dict() or {}) for s in collection("wa_conversations")
                .where("assigned_to_uid", "==", u.get("firebase_uid") or "-").stream()]
        rows = [(k, c) for k, c in rows if not c.get("is_backup")]

        def top(use_fix):
            def key(kc):
                k, c = kc
                v = conv_new_lma.get(k) if use_fix and k in conv_new_lma else ts(c.get("last_message_at"), dbf)
                return v or datetime.fromtimestamp(0, tz=timezone.utc)
            return sorted(rows, key=key, reverse=True)[:50]
        b, af = top(False), top(True)
        fake_b = sum(1 for k, _ in b if k in conv_new_lma)
        print(f"    user {owner} total={len(rows):4} | com data falsa no top-50: {fake_b} -> 0")

    glob = [(s.id, s.to_dict() or {}) for s in collection("wa_conversations")
            .order_by("last_message_at", direction="DESCENDING").limit(300).stream()]
    fake_g = sum(1 for k, _ in glob if k in conv_new_lma)
    print(f"\n  Equipe (janela global top-300): vagas ocupadas por data falsa = {fake_g} de {len(glob)}")

    if not a.apply:
        print("\nDRY-RUN: nada gravado. Adicione --apply para corrigir.")
        return

    # ---------------------------------------------------------------- apply
    LOGS.mkdir(exist_ok=True)
    stamp = now.astimezone(BRT).strftime("%Y%m%d_%H%M%S")
    undo_path = LOGS / f"undo_recency_{a.tenant}_{stamp}.json"
    changes = [{"col": "wa_conversations", "doc": s.id, "field": "last_message_at", "old": iso(o), "new": iso(n)}
               for s, o, n in conv_plan]
    changes += [{"col": "wa_contacts", "doc": s.id, "field": f, "old": iso(o), "new": iso(n)}
                for s, f, o, n in ct_plan]
    with open(undo_path, "w", encoding="utf-8") as fh:
        json.dump({"tenant": a.tenant, "channels": channels, "generated_at": iso(now), "changes": changes}, fh, indent=1)
    print(f"\nundo gravado: {undo_path} ({len(changes)} mudancas)")

    done = Counter()
    for snap, old, new in conv_plan:
        try:
            snap.reference.update({"last_message_at": new},
                                  option=snap.reference._client.write_option(last_update_time=snap.update_time))
            done["conversa_ok"] += 1
        except gex.FailedPrecondition:
            done["conversa_pulada_mudou"] += 1
    by_contact = {}
    for snap, field, old, new in ct_plan:
        by_contact.setdefault(snap.id, (snap, {}))[1][field] = new
    for _, (snap, fields) in by_contact.items():
        try:
            snap.reference.update(fields, option=snap.reference._client.write_option(last_update_time=snap.update_time))
            done["contato_ok"] += 1
        except gex.FailedPrecondition:
            done["contato_pulado_mudou"] += 1
    print("APPLY:", dict(done))


if __name__ == "__main__":
    main()
