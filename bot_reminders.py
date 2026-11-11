# -*- coding: utf-8 -*-
"""Lembretes pos-aceite: classificacao pura, agenda e worker tenant-scoped."""

import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from firestore_common import collection, document, get_firestore_client, utcnow

logger = logging.getLogger("castro_crm.bot_reminders")
KEYS = ("bot_reminder_enabled", "bot_reminder_text_1", "bot_reminder_text_2",
        "bot_reminder_text_3", "bot_reminder_minutes_1", "bot_reminder_minutes_2",
        "bot_reminder_closing_minutes", "bot_reminder_generation")
DEFAULTS = dict(zip(KEYS, (False, "", "", "", 20, 240, 1420, "")))
STAGES = ("etapa_1", "etapa_2", "fechamento")


def timestamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", value)).strip()


def command(text):
    return {"parar lembretes": "stop", "ativar lembretes": "start"}.get(normalize(text))


def classify_reply(reply, kind="cx_reply", link="marcaconsultas"):
    """Heuristica conservadora compartilhada pelo medidor e pelo turno real."""
    text = str(reply.get("body", "") if isinstance(reply, dict) else reply or "")
    if kind != "cx_reply":
        return kind
    if link and link.lower() in text.lower():
        return "link"
    # Cortesia pode terminar com nome, pronome ou uma pergunta generica.
    courtesy = re.compile(
        r"^(?:voce )?(?:(?:posso|podemos) (?:te |lhe |ajudar voce |auxiliar voce )?"
        r"(?:ajudar|auxiliar)? ?(?:em |com )?(?:algo|(?:mais )?alguma (?:outra )?(?:coisa|duvida|informacao)|mais algo)"
        r"(?: mais)?|(?:precisa|precisam|deseja|gostaria) (?:de )?(?:mais )?(?:algo|alguma (?:outra )?(?:coisa|duvida|informacao))"
        r"(?: mais)?|(?:ha|tem) mais alguma (?:coisa|duvida)|"
        r"(?:ficou|restou) (?:mais )?alguma duvida|(?:quer|deseja) mais alguma (?:coisa|informacao))\b"
    )
    actionable = False
    courtesy_seen = False
    for match in re.finditer(r"[^.!?\n]+[.!?]?", text):
        sentence = match.group().strip()
        norm = normalize(sentence)
        if courtesy.search(norm):
            courtesy_seen = True
            continue
        if "?" in sentence or re.search(
                r"\b(?:informe|envie|digite|escolha|selecione|confirme|me diga|me conte|"
                r"me informe|preciso saber|aguardo (?:seu|sua)|pode informar|poderia informar)\b", norm):
            actionable = True
    if actionable:
        return "pending"
    if courtesy_seen or re.search(r"\b(?:obrigad[oa]|disponha|ate mais|tchau|tenha um|ajudar|auxiliar)\b", normalize(text)):
        return "courtesy"
    return "no_question"


def tenant_mode(tenant):
    mode = ((tenant or {}).get("settings") or {}).get("bot_reminder_mode")
    return mode if isinstance(mode, str) and mode in ("on", "dry_run") else "off"


def tenant_allowed(tenant):
    ai = ((tenant or {}).get("settings") or {}).get("ai") or {}
    return bool(tenant and tenant.get("is_active", True) and tenant_mode(tenant) != "off"
                and ai.get("bot_engine") == "dialogflow_cx"
                and ai.get("status", "active") == "active" and ai.get("lgpd_by_agent") is not True
                and ((tenant.get("settings") or {}).get("bot_reminder_epoch")))


def available():
    from config import FEATURE_BOT_REMINDER
    if not FEATURE_BOT_REMINDER:
        return False
    from tenant_service import get_tenant
    from firestore_common import get_tenant_context
    return tenant_allowed(get_tenant(get_tenant_context()))


def commands_available():
    """Respeita a preferencia mesmo com o modo comercial off ou agente pausado."""
    from tenant_service import get_tenant
    from firestore_common import get_tenant_context
    tenant = get_tenant(get_tenant_context()) or {}
    settings = tenant.get("settings") or {}
    ai = settings.get("ai") or {}
    return bool(tenant.get("is_active", True) and settings.get("bot_reminder_epoch")
                and ai.get("bot_engine") == "dialogflow_cx" and ai.get("lgpd_by_agent") is not True)


def clean_settings(values, current=None):
    cfg = {**DEFAULTS, **(current or {}), **{k: v for k, v in values.items() if k in KEYS}}
    cfg = {k: cfg[k] for k in KEYS}
    cfg["bot_reminder_enabled"] = cfg["bot_reminder_enabled"] is True
    from config import REOPEN_DESFECHO_LINK, BOT_REMINDER_MARGIN_MINUTES
    for index in range(1, 4):
        key = f"bot_reminder_text_{index}"
        cfg[key] = str(cfg[key] or "").strip()
        if len(cfg[key]) > 1000:
            raise ValueError("Cada lembrete deve ter no máximo 1.000 caracteres.")
        if REOPEN_DESFECHO_LINK and REOPEN_DESFECHO_LINK in cfg[key].lower():
            raise ValueError("O lembrete não pode conter o link de agendamento.")
    times = []
    for key in ("bot_reminder_minutes_1", "bot_reminder_minutes_2", "bot_reminder_closing_minutes"):
        val = cfg[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not float(val).is_integer():
            raise ValueError("Os intervalos dos lembretes devem ser minutos inteiros.")
        cfg[key] = int(val)
        times.append(int(val))
    first, second, closing = times
    if not (10 <= first < second < closing <= 1440 - BOT_REMINDER_MARGIN_MINUTES - 10
            and second - first >= 60 and closing - second >= 60):
        raise ValueError("Use intervalos em ordem, separados por pelo menos 60 minutos, dentro da janela de 24 horas.")
    if cfg["bot_reminder_enabled"] and not any(cfg[f"bot_reminder_text_{i}"] for i in range(1, 4)):
        raise ValueError("Preencha pelo menos um lembrete antes de ativar.")
    return cfg


def schedule(thread, settings, now):
    """Decide enviar, limpar ou reagendar. Nao faz leitura nem escrita."""
    from config import BOT_REMINDER_MARGIN_MINUTES
    bot = timestamp(thread.get("last_bot_turn_at"))
    inbound = timestamp(thread.get("last_inbound_at"))
    cycle = timestamp(thread.get("bot_reminder_cycle"))
    if not bot or not inbound or not cycle or inbound != cycle or bot <= inbound:
        return {"action": "clear", "reason": "ciclo_encerrado"}
    if thread.get("bot_reminder_scope") != "todas":
        return {"action": "clear", "reason": "sem_pendencia"}
    limit = inbound + timedelta(hours=24, minutes=-BOT_REMINDER_MARGIN_MINUTES)
    if now > limit:
        return {"action": "clear", "reason": "janela_fechada"}
    done = set(thread.get("bot_reminder_done") or [])
    stages = []
    skipped = []
    for i, stage in enumerate(STAGES, 1):
        if stage in done or not str(settings.get(f"bot_reminder_text_{i}") or "").strip():
            continue
        due = (bot + timedelta(minutes=settings[f"bot_reminder_minutes_{i}"]) if i < 3
               else inbound + timedelta(minutes=settings["bot_reminder_closing_minutes"]))
        if due > limit or (i == 3 and due < bot + timedelta(minutes=60)):
            skipped.append(stage)
        else:
            stages.append((due, i, stage))
    due_now = [s for s in stages if s[0] <= now]
    if due_now:
        chosen = max(due_now, key=lambda s: s[1])
        skipped.extend(s[2] for s in due_now if s != chosen)
        future = [s[0] for s in stages if s[0] > now]
        return {"action": "send", "stage": chosen[2], "index": chosen[1], "due": chosen[0],
                "skipped": skipped, "next_at": min(future) if future else None}
    return {"action": "wait" if stages else "clear", "reason": "aguardando" if stages else "esgotado",
            "skipped": skipped, "next_at": min(s[0] for s in stages) if stages else None}


def prepare_turn(contact_id, channel_id):
    """Captura a entrada antes de aguardar o agente. Nunca arma por retroacao."""
    if not available() or channel_id is None:
        return None
    from database_firestore import _make_conversation_id
    from tenant_service import get_tenant
    from firestore_common import get_tenant_context
    contact = document("wa_contacts", contact_id).get().to_dict() or {}
    if not contact.get("wa_id"):
        return None
    cid = _make_conversation_id(channel_id, contact["wa_id"])
    thread = document("wa_conversations", cid).get().to_dict() or {}
    tenant = get_tenant(get_tenant_context())
    return {"conversation_id": cid, "entry": timestamp(contact.get("last_new_inbound_at")),
            "inbound": timestamp(thread.get("last_inbound_at")),
            "epoch": tenant["settings"]["bot_reminder_epoch"], "kind": "none"}


@firestore.transactional
def _stamp(transaction, thread_ref, contact_ref, cfg_ref, metadata, sent_at, classification):
    thread = thread_ref.get(transaction=transaction).to_dict() or {}
    contact = contact_ref.get(transaction=transaction).to_dict() or {}
    cfg = {**DEFAULTS, **(cfg_ref.get(transaction=transaction).to_dict() or {})}
    if (timestamp(contact.get("last_new_inbound_at")) != metadata.get("entry")
            or timestamp(thread.get("last_inbound_at")) != metadata.get("inbound")
            or not metadata.get("inbound") or not cfg.get("bot_reminder_enabled")
            or cfg.get("bot_reminder_generation") != metadata.get("generation")):
        return False
    old_cycle = timestamp(thread.get("bot_reminder_cycle"))
    if old_cycle and old_cycle > metadata["inbound"]:
        return False
    scope = "todas" if classification == "pending" and not contact.get("bot_reminder_opt_out") else "nenhuma"
    updates = {"last_bot_turn_at": sent_at, "last_bot_turn_kind": metadata["kind"],
               "bot_reminder_scope": scope, "bot_reminder_cycle": metadata["inbound"],
               "bot_reminder_entry": metadata["entry"], "bot_reminder_epoch": metadata["epoch"],
               "bot_reminder_generation": cfg["bot_reminder_generation"],
               "bot_reminder_done": (thread.get("bot_reminder_done") or [])
               if old_cycle == metadata["inbound"] and timestamp(thread.get("bot_reminder_entry")) == metadata["entry"] else []}
    plan = schedule({**thread, **updates}, cfg, sent_at)
    updates["bot_reminder_next_at"] = plan.get("next_at") if plan["action"] != "clear" else None
    transaction.update(thread_ref, updates)
    transaction.update(contact_ref, {"bot_reminder_latest_thread": thread_ref.id})
    return True


def stamp_turn(contact_id, reply, metadata, sent_at=None):
    if not metadata:
        return False
    from config import REOPEN_DESFECHO_LINK
    classification = classify_reply(reply, metadata["kind"], REOPEN_DESFECHO_LINK)
    return _stamp(get_firestore_client().transaction(), document("wa_conversations", metadata["conversation_id"]),
                  document("wa_contacts", contact_id), document("system_settings", "chat"),
                  metadata, sent_at or utcnow(), classification)


def apply_command(contact_id, action, at=None):
    """Preferencia exclusiva do lembrete. Inbound comum nao desfaz a recusa."""
    ref = document("wa_contacts", contact_id)
    at = timestamp(at) or utcnow()
    return _preference(get_firestore_client().transaction(), ref, action, at)


@firestore.transactional
def _preference(transaction, ref, action, at):
    contact = ref.get(transaction=transaction).to_dict() or {}
    previous = timestamp(contact.get("bot_reminder_opt_out_at"))
    if previous and previous >= at:
        return False
    transaction.update(ref, {"bot_reminder_opt_out": action == "stop", "bot_reminder_opt_out_at": at})
    return True


def gate(thread, contact, state, buffer, tenant, cfg, channel, now):
    """Motivo de bloqueio; buffer e a unica condicao temporaria."""
    from bot_service import lgpd_consent_resolved
    from commercial_contact_policy import is_commercial_contact_blocked
    from firestore_common import get_tenant_context
    if not tenant_allowed(tenant) or not cfg.get("bot_enabled") or not cfg.get("bot_reminder_enabled"):
        return "desligado"
    if (thread.get("bot_reminder_epoch") != tenant["settings"].get("bot_reminder_epoch")
            or thread.get("bot_reminder_generation") != cfg.get("bot_reminder_generation")):
        return "ativacao_antiga"
    if not channel or str(channel.get("tenant_id") or "hubloc") != str(get_tenant_context()):
        return "canal_invalido"
    if channel.get("channel_type") != "standard" or not channel.get("is_active", True):
        return "canal_invalido"
    if (thread.get("is_backup") or thread.get("assigned_to") or thread.get("assigned_to_uid")
            or thread.get("attendance_status") != "aberto"):
        return "thread_indisponivel"
    inbound = timestamp(thread.get("last_inbound_at"))
    bot = timestamp(thread.get("last_bot_turn_at"))
    if not inbound or not bot:
        return "sem_ciclo"
    for key in ("handoff_at", "last_human_outbound_at"):
        at = timestamp(thread.get(key))
        if at and at >= inbound:
            return "humano"
    if (not contact or contact.get("assigned_to") or contact.get("assigned_to_uid")
            or contact.get("bot_completed") or contact.get("archived")
            or contact.get("is_archived") or contact.get("is_backup") or contact.get("lgpd_revoked")
            or contact.get("reopen_opt_out") or contact.get("bot_reminder_opt_out")
            or contact.get("qualification", "novo") not in ("novo", "em_atendimento")
            or is_commercial_contact_blocked(contact)):
        return "contato_indisponivel"
    # Compara a entrada capturada, mesmo que o relogio da Meta tenha recuado.
    # last_new_inbound_at so muda em mensagem nova (reentrega da Meta nao conta).
    if timestamp(contact.get("last_new_inbound_at")) != timestamp(thread.get("bot_reminder_entry")):
        return "nova_entrada"
    if contact.get("bot_reminder_latest_thread") != thread.get("id"):
        return "outra_thread"
    released = timestamp(contact.get("bot_released_at"))
    if released and bot <= released:
        return "devolvido_ao_bot"
    ai = (tenant.get("settings") or {}).get("ai") or {}
    if (contact.get("lgpd_consent") is not True or state.get("human_active")
            or not lgpd_consent_resolved(state, contact, ai, cfg)):
        return "sem_aceite"
    from database_firestore import _bot_buffer_live_claim, bot_buffer_claim_ttl_seconds
    if buffer.get("items") or _bot_buffer_live_claim(buffer, now, bot_buffer_claim_ttl_seconds()):
        return "buffer"
    return None


@firestore.transactional
def _claim(transaction, thread_ref, contact_ref, state_ref, buffer_ref, tenant_ref, cfg_ref,
           channel_ref, expected, now):
    # Todas as leituras antecedem a primeira escrita da transacao.
    thread, contact, state, buffer, tenant, cfg, channel = [
        ref.get(transaction=transaction).to_dict() or {}
        for ref in (thread_ref, contact_ref, state_ref, buffer_ref, tenant_ref, cfg_ref, channel_ref)]
    thread["id"] = thread_ref.id
    contact["id"] = thread.get("contact_id")
    cfg = {**DEFAULTS, **cfg}
    try:
        cfg = {**cfg, **clean_settings({}, cfg)}
    except ValueError:
        transaction.update(thread_ref, {"bot_reminder_next_at": None})
        return {"blocked": "configuracao_invalida", "plan": {}}
    if (timestamp(thread.get("last_bot_turn_at")) != timestamp(expected.get("last_bot_turn_at"))
            or timestamp(thread.get("bot_reminder_entry")) != timestamp(expected.get("bot_reminder_entry"))):
        return None
    plan = schedule(thread, cfg, now)
    reason = gate(thread, contact, state, buffer, tenant, cfg, channel, now)
    if reason:
        transaction.update(thread_ref, {"bot_reminder_next_at": now + timedelta(minutes=5) if reason == "buffer" else None})
        return {"blocked": reason, "plan": plan}
    done = list(dict.fromkeys([*(thread.get("bot_reminder_done") or []), *plan.get("skipped", [])]))
    if plan["action"] != "send":
        transaction.update(thread_ref, {"bot_reminder_done": done, "bot_reminder_next_at": plan.get("next_at")})
        return {"blocked": plan.get("reason"), "plan": plan}
    # Uma thread por contato: claim no contato impede envio simultaneo por outros canais.
    last_claim = timestamp(contact.get("bot_reminder_claim_at"))
    if last_claim and last_claim >= now - timedelta(minutes=5):
        transaction.update(thread_ref, {"bot_reminder_next_at": now + timedelta(minutes=5)})
        return None
    done.append(plan["stage"])
    transaction.update(thread_ref, {"bot_reminder_done": done, "bot_reminder_next_at": plan.get("next_at")})
    transaction.update(contact_ref, {"bot_reminder_claim_at": now})
    return {"thread": thread, "contact": contact, "plan": plan, "mode": tenant_mode(tenant),
            "channel": channel, "epoch": tenant["settings"]["bot_reminder_epoch"],
            "text": cfg[f"bot_reminder_text_{plan['index']}"]}


def audit(action, contact_id, stage, **detail):
    from database_firestore import log_audit
    log_audit(None, "BOT_REMINDER_" + action,
              "contact_id=%s serie=B etapa=%s %s" % (contact_id, stage, " ".join(f"{k}={v}" for k, v in detail.items())))


@firestore.transactional
def _close_failed_window(transaction, ref, expected):
    current = ref.get(transaction=transaction).to_dict() or {}
    if (timestamp(current.get("last_bot_turn_at")) == timestamp(expected.get("last_bot_turn_at"))
            and timestamp(current.get("bot_reminder_entry")) == timestamp(expected.get("bot_reminder_entry"))):
        transaction.update(ref, {"bot_reminder_next_at": None})


def run_tick(now=None):
    """Worker inteiramente sincrono, chamado fora do event loop."""
    from config import FEATURE_BOT_REMINDER, BOT_REMINDER_MAX_PER_TICK
    if not FEATURE_BOT_REMINDER:
        return {"status": "off", "sent": 0, "simulated": 0, "failed": 0}
    from tenant_service import list_tenants, tenant_doc_ref
    from firestore_common import tenant_context
    from bot_sender import send_bot_reminder
    result = {"status": "ok", "sent": 0, "simulated": 0, "failed": 0}
    started = time.monotonic()
    processed = 0
    for tenant in list_tenants(active_only=True):
        if not tenant_allowed(tenant):
            continue
        with tenant_context(tenant["id"]):
            try:
                cfg = {**DEFAULTS, **(document("system_settings", "chat").get().to_dict() or {})}
                if not cfg.get("bot_reminder_enabled") or not cfg.get("bot_enabled"):
                    continue
                cfg = {**cfg, **clean_settings({}, cfg)}
                instant = now or utcnow()
                query = (collection("wa_conversations").where("bot_reminder_next_at", ">=", instant - timedelta(hours=24))
                         .where("bot_reminder_next_at", "<=", instant).order_by("bot_reminder_next_at").limit(200))
                rows = []
                for snap in query.stream():
                    rows.append({**(snap.to_dict() or {}), "id": snap.id})
                if len(rows) == 200:
                    logger.warning("bot-reminder tenant=%s limite de candidatos atingido", tenant["id"])
                newest = {}
                for row in rows:
                    cid = row.get("contact_id")
                    prev = newest.get(cid)
                    if prev is None or (timestamp(row.get("last_bot_turn_at")) or instant - timedelta(days=1)) > (timestamp(prev.get("last_bot_turn_at")) or instant - timedelta(days=1)):
                        newest[cid] = row
                rows = list(newest.values())
                rows.sort(key=lambda row: (0 if schedule(row, cfg, instant).get("index") == 3 else 1,
                                           timestamp(row.get("last_inbound_at")) or instant))
                for row in rows:
                    if processed >= BOT_REMINDER_MAX_PER_TICK or time.monotonic() - started >= 150:
                        return result
                    cid = row.get("contact_id")
                    claimed = _claim(get_firestore_client().transaction(), document("wa_conversations", row["id"]),
                                     document("wa_contacts", cid), document("bot_states", cid), document("bot_buffers", cid),
                                     tenant_doc_ref(tenant["id"]), document("system_settings", "chat"),
                                     document("channels", row.get("channel_id")), row, now or utcnow())
                    if not claimed:
                        continue
                    plan = claimed["plan"]
                    for skipped in plan.get("skipped", []):
                        audit("SKIPPED", cid, skipped, motivo="etapa_superada")
                    if claimed.get("blocked"):
                        if claimed["blocked"] not in ("buffer", "aguardando"):
                            audit("SKIPPED", cid, plan.get("stage", "ciclo"), motivo=claimed["blocked"])
                        continue
                    processed += 1
                    if claimed["mode"] == "dry_run":
                        result["simulated"] += 1
                        audit("SIMULATED", cid, plan["stage"], vencimento=plan["due"].isoformat())
                        continue
                    # Kill-switch e preferencia relidos apos o claim, antes do POST.
                    live = tenant_doc_ref(tenant["id"]).get().to_dict() or {}
                    live_contact = document("wa_contacts", cid).get().to_dict() or {}
                    if (tenant_mode(live) != "on" or not tenant_allowed(live)
                            or live["settings"].get("bot_reminder_epoch") != claimed["epoch"]
                            or live_contact.get("bot_reminder_opt_out")
                            or timestamp(live_contact.get("last_new_inbound_at")) != timestamp(row.get("bot_reminder_entry"))):
                        audit("SKIPPED", cid, plan["stage"], motivo="alterado_apos_claim")
                        continue
                    outcome = send_bot_reminder(claimed["contact"], row, claimed["channel"], claimed["text"], plan["stage"])
                    result["sent" if outcome["ok"] else "failed"] += 1
                    audit("SENT" if outcome["ok"] else "FAILED", cid, plan["stage"], code=outcome.get("code", ""))
                    if outcome.get("code") == 131047:
                        _close_failed_window(get_firestore_client().transaction(), document("wa_conversations", row["id"]), row)
            except Exception as exc:
                # So o tipo da excecao: a mensagem pode trazer PII do provedor.
                logger.error("bot-reminder falha no tenant=%s erro=%s", tenant.get("id"), type(exc).__name__)
                result["failed"] += 1
    return result
