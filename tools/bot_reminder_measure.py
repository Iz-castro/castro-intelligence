# -*- coding: utf-8 -*-
"""Estimativa SO LEITURA. Saida exclusivamente agregada, sem amostras de mensagens."""

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot_reminders import classify_reply, normalize, timestamp


def trava_escrita():
    from google.cloud.firestore_v1 import batch, collection, document, transaction
    def blocked(*args, **kwargs):
        raise RuntimeError("Medidor somente leitura: escrita bloqueada")
    for cls, names in ((document.DocumentReference, ("set", "update", "delete", "create")),
                       (collection.CollectionReference, ("add",)), (batch.WriteBatch, ("commit",)),
                       (transaction.Transaction, ("commit",))):
        for name in names:
            setattr(cls, name, blocked)


def summarize(messages, now, excluded=(), link="marcaconsultas", notice=""):
    by_thread = defaultdict(list)
    days = defaultdict(set)
    classes = Counter()
    daily_last = {}
    delays = Counter()
    observed = []
    for msg in messages:
        at = timestamp(msg.get("timestamp_wa"))
        if at and msg.get("conversation_id"):
            by_thread[msg["conversation_id"]].append((at, msg))
    for thread, entries in by_thread.items():
        entries.sort(key=lambda item: item[0])
        responses = {}
        next_inbound = None
        for index in range(len(entries) - 1, -1, -1):
            at, msg = entries[index]
            if msg.get("direction") == "inbound":
                next_inbound = at
            else:
                responses[index] = next_inbound
        turns = []
        for index, (at, msg) in enumerate(entries):
            text = str(msg.get("content") or "")
            if (msg.get("direction") != "outbound" or msg.get("sender_user_id") is not None
                    or msg.get("operator_id") is not None or msg.get("msg_type") != "text"
                    or msg.get("status") == "failed" or msg.get("automation_kind")
                    or text in excluded or text.startswith(("[Reabertura", "Protocolo", "Seu protocolo"))
                    or "protocolo de atendimento" in text.lower()
                    or "como voce avalia" in normalize(text)):
                continue
            kind = "lgpd_notice" if "podemos continuar" in text.lower() or (notice and notice in text) else "cx_reply"
            category = classify_reply(text, kind, link)
            day = at.astimezone(timezone(timedelta(hours=-3))).date().isoformat()
            days[day].add(thread)
            daily_last[(day, thread)] = category
            turns.append(category)
            following = responses.get(index)
            if following:
                minutes = (following - at).total_seconds() / 60
                observed.append(minutes)
                delays["ate_20min" if minutes <= 20 else "20min_a_4h" if minutes <= 240 else "4h_a_24h" if minutes <= 1440 else "apos_24h"] += 1
            else:
                delays["sem_resposta_em_24h" if now - at >= timedelta(hours=24) else "ainda_em_observacao"] += 1
        if turns:
            classes[turns[-1]] += 1
    observed.sort()
    percentiles = {str(p): round(observed[min(len(observed)-1, int((len(observed)-1)*p/100))], 2)
                   for p in (50, 90, 95)} if observed else {}
    return {"fuso": "UTC-03:00", "threads_com_turno_por_dia": {day: len(ids) for day, ids in sorted(days.items())},
            "candidatas_por_texto_por_dia": dict(Counter(day for (day, _), category in daily_last.items() if category == "pending")),
            "ultima_fala_estimada": dict(classes), "candidatas_por_texto": classes["pending"],
            "tempo_de_resposta": dict(delays), "percentis_minutos_observados": percentiles,
            "limitacao": "Estimativa por texto; autoria historica ambigua e consentimento historico nao reconstruido. Nao e previsao exata de envios."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dias", type=int, default=7, choices=range(1, 91), metavar="1..90")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    trava_escrita()
    from firestore_common import collection, tenant_context
    from database_firestore import get_system_settings
    from config import REOPEN_DESFECHO_LINK
    import json
    now = datetime.now(timezone.utc)
    try:
        with tenant_context(args.tenant):
            cfg = get_system_settings()
            query = (collection("wa_messages").where("timestamp_wa", ">=", now - timedelta(days=args.dias))
                     .order_by("timestamp_wa").limit(50001))
            messages = [snap.to_dict() for snap in query.stream()]
            if len(messages) > 50000:
                print("Limite de leitura atingido; reduza --dias.")
                return 2
            report = summarize(messages, now, (cfg.get("pool_wait_notice_text"),), REOPEN_DESFECHO_LINK, cfg.get("lgpd_notice") or "")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        print("Falha na medição. Confira projeto, credenciais e índices; nenhum dado individual foi impresso.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
