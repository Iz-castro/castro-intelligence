# -*- coding: utf-8 -*-
"""Drena pending_webhook_events reprocessando via process_webhook_payload.
Idempotente. Loop multi-passe ate convergir (a midia fora de ordem re-enfileira
e anexa num passe seguinte, quando o placeholder de texto ja existe).

Uso:
  $env:FIRESTORE_PROJECT_ID="project-4a851bf9-f475-418c-800"
  ./.venv/Scripts/python.exe scripts/_drain_pending_tmp.py                 # dry-run
  ./.venv/Scripts/python.exe scripts/_drain_pending_tmp.py --limit 20 --confirm  # teste 1 passe
  ./.venv/Scripts/python.exe scripts/_drain_pending_tmp.py --confirm       # loop ate convergir
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import global_collection  # noqa: E402
from pending_events import mark_event_attempt, count_pending, PENDING_COLLECTION, STATUS_PENDING  # noqa: E402
import webhook  # noqa: E402

_ORDER = {"no_channel_for_phone": 0, "history_media_no_placeholder": 1}


def _fetch(limit, shard=None, workers=None):
    rows = []
    for s in global_collection(PENDING_COLLECTION).where("status", "==", STATUS_PENDING).stream():
        d = s.to_dict() or {}
        d["_id"] = d.get("id") or s.id
        if shard is not None and workers:
            try:
                if int(d["_id"]) % workers != shard:
                    continue
            except (TypeError, ValueError):
                continue
        rows.append(d)
    rows.sort(key=lambda r: (_ORDER.get(r.get("reason"), 2), str(r.get("received_at"))))
    return rows[:limit] if limit else rows


async def drain(limit, confirm, max_passes, shard=None, workers=None):
    tag = f"[shard {shard}/{workers}] " if shard is not None else ""
    rows = _fetch(limit, shard, workers)
    print(f"{tag}pending inicial: {len(rows)}", flush=True)
    if not confirm:
        print("DRY-RUN — nada reprocessado.")
        return
    prev = None
    tok = terr = 0
    for p in range(max_passes):
        rows = _fetch(limit, shard, workers)
        if not rows:
            print("sem pending — convergiu", flush=True)
            break
        ok = err = 0
        for i, r in enumerate(rows):
            payload = r.get("payload") or {}
            if not payload:
                continue
            try:
                # timeout por evento: um evento pendurado (download de midia sem
                # resposta) nao pode bloquear o resto da fila
                await asyncio.wait_for(
                    webhook.process_webhook_payload(payload, ws_notify_callback=None),
                    timeout=120,
                )
                mark_event_attempt(r["_id"], success=True)
                ok += 1
            except asyncio.TimeoutError:
                mark_event_attempt(r["_id"], success=False, error="drain timeout 120s")
                err += 1
                print(f"  TIMEOUT id={r['_id']} field={r.get('change_field')} (pulado)", flush=True)
            except Exception as e:
                mark_event_attempt(r["_id"], success=False, error=f"{type(e).__name__}: {e}")
                err += 1
            if (i + 1) % 25 == 0:
                print(f"  ... {i + 1}/{len(rows)} (ok={ok} err={err})", flush=True)
        tok += ok
        terr += err
        cur = len(_fetch(None, shard, workers))
        print(f"{tag}passe {p + 1}: processou {len(rows)} (ok={ok} err={err}) | restante no shard={cur}", flush=True)
        if cur == 0:
            break
        if prev is not None and cur >= prev:
            print(f"{tag}sem progresso entre passes — parando (residual provavel: midia expirada)", flush=True)
            break
        prev = cur
        if limit:  # com --limit roda so 1 passe (teste)
            break
    print(f"{tag}TOTAL: ok={tok} err={terr} | pending global={count_pending()}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-passes", type=int, default=6)
    ap.add_argument("--shard", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(drain(a.limit, a.confirm, a.max_passes, a.shard, a.workers))


if __name__ == "__main__":
    main()
