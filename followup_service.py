# -*- coding: utf-8 -*-
"""Regras do follow-up F1. Nenhum envio ou efeito no atendimento."""

import base64
import copy
import hashlib
import hmac
import json
import re
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException

from config import SECRET_KEY

try:
    from zoneinfo import ZoneInfo
    BR_TZ = ZoneInfo("America/Sao_Paulo")
except (ImportError, KeyError):
    BR_TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")


TASK_TYPES = {
    "retorno": "commercial", "orcamento": "commercial",
    "sem_resposta": "commercial", "recuperacao": "commercial",
    "confirmacao_consulta": "service", "lembrete_consulta": "service",
    "internal": "internal",
}
RESULTS = {"action_done", "not_reached", "customer_replied", "scheduled", "no_longer_interested"}
CONTACT_FIELDS = ("assigned_to", "assigned_to_uid", "is_backup", "is_archived",
                  "lgpd_revoked", "commercial_contact_block")
CONVERSATION_FIELDS = ("contact_id", "assigned_to", "assigned_to_uid", "is_backup", "channel_id")
DEFAULT_SETTINGS = {
    "version": 0, "timezone": "America/Sao_Paulo", "configured": False,
    "queues": [{"key": "reception", "label": "Recepção", "active": True},
               {"key": "quotes", "label": "Orçamentos", "active": True}],
    "contact_hours": {str(day): [] for day in range(7)},
    "holidays": [], "preferred_time": None,
}


def _fail(message, status=422):
    raise HTTPException(status, message)


def _dt(value, field="data", nullable=False):
    if value is None and nullable:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        _fail("Informe %s com data, hora e fuso." % field)


def _text(value, field, maximum=160, required=False):
    if not isinstance(value, str):
        _fail("%s deve ser texto." % field)
    result = value.strip()
    if (required and not result) or len(result) > maximum or "\x00" in result:
        _fail("%s inválido (máximo %d caracteres)." % (field, maximum))
    return result


def _identifier(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        _fail("%s inválido." % field)
    return value


def _number(value, field):
    if isinstance(value, bool):
        _fail("%s inválido." % field)
    try:
        result = int(value)
        if str(value).strip() != str(result) or result < 1:
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        _fail("%s inválido." % field)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=lambda item: item.isoformat() if isinstance(item, (datetime, date)) else str(item))


def _clock_minutes(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        _fail("Horário inválido; use HH:MM.")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _is_blocked(contact):
    # Import tardio para manter independente da montagem das rotas.
    from commercial_contact_policy import is_commercial_contact_blocked
    return is_commercial_contact_blocked(contact)


class FollowupService:
    def __init__(self, repository, user, authorize_contact, can_manage=False, clock=None,
                 commercial_blocked=None, can_configure=None):
        self.repo = repository
        self.user = dict(user)
        self.authorize_contact = authorize_contact
        self.can_manage = bool(can_manage)
        self.can_configure = self.can_manage if can_configure is None else bool(can_configure)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.commercial_blocked = commercial_blocked or _is_blocked
        if str(user.get("tenant_id") or "") != repository.tenant_id or not user.get("firebase_uid"):
            _fail("Sessão sem tenant ou identidade válida.", 403)
        self.uid = str(user["firebase_uid"])
        self.user_id = _number(user.get("id"), "Usuário")

    def now(self):
        return _dt(self.clock())

    def _actor(self):
        if self.user.get("read_only") or self.user.get("impersonating"):
            _fail("Sessão somente de leitura não opera follow-up.", 403)
        row = self.repo.user(self.user_id)
        if not row or row.get("is_active", 1) not in (1, True) or str(row.get("firebase_uid") or "") != self.uid:
            _fail("Usuário inativo ou identidade alterada.", 403)
        if row.get("tenant_id") not in (None, "", self.repo.tenant_id):
            _fail("Usuário de outro tenant.", 403)
        if row.get("role", "operador") != self.user.get("role", "operador"):
            _fail("O perfil do usuário mudou. Atualize a sessão.", 403)
        return row

    def _access(self, contact_id, conversation_id=None, target_user=None):
        result = self.authorize_contact(contact_id, conversation_id, target_user or self.user)
        if not isinstance(result, dict) or not isinstance(result.get("contact"), dict):
            _fail("Contato indisponível.", 403)
        contact = result["contact"]
        if str(contact.get("id")) != str(contact_id):
            _fail("Contato inválido.", 403)
        conv = result.get("conversation")
        if conversation_id and (not conv or str(conv.get("contact_id")) != str(contact_id)):
            _fail("Conversa não pertence ao contato.", 403)
        return result

    def _guards(self, context, users=()):
        contact = context["contact"]
        guards = [("wa_contacts", contact["id"], {key: contact.get(key) for key in CONTACT_FIELDS})]
        conv = context.get("conversation")
        if conv:
            guards.append(("wa_conversations", conv["id"], {key: conv.get(key) for key in CONVERSATION_FIELDS}))
        channel = context.get("access_channel")
        if channel:
            guards.append(("__global_channels", channel["id"], {key: channel.get(key) for key in ("tenant_id", "channel_type")}))
        for row in users:
            guards.append(("users", row["id"], {key: row.get(key) for key in ("is_active", "firebase_uid", "role", "perfil_acesso_id")}))
        return guards

    def _settings_guards(self, settings):
        return [("system_settings", "followup", {"version": settings["version"]})] if settings.get("version", 0) > 0 else []

    def _task(self, task_id):
        _identifier(task_id, "Tarefa")
        row = self.repo.task(task_id)
        if not row or row.get("tenant_id") != self.repo.tenant_id:
            _fail("Tarefa não encontrada.", 404)
        context = self._access(row["contact_id"], row.get("conversation_id"))
        return row, context

    def _may_modify(self, task):
        return self.can_manage or task.get("assignment_mode") == "queue" or task.get("assignee_uid") == self.uid

    def _require_modify(self, task):
        if not self._may_modify(task):
            _fail("A tarefa está com outra pessoa. Solicite redistribuição.", 403)

    def _target(self, user_id, context, conversation_id):
        user_id = _number(user_id, "Responsável")
        row = self.repo.user(user_id)
        if not row or row.get("is_active", 1) not in (1, True) or not row.get("firebase_uid"):
            _fail("Responsável inativo ou inválido.")
        if row.get("tenant_id") not in (None, "", self.repo.tenant_id):
            _fail("Responsável de outro tenant.", 403)
        target = dict(row, id=user_id, tenant_id=self.repo.tenant_id)
        self._access(context["contact"]["id"], conversation_id, target)
        return target

    def _fingerprint(self, payload, task_id=None):
        return hashlib.sha256(_json({"task": task_id, "payload": payload}).encode("utf-8")).hexdigest()

    def _replay(self, operation_id, fingerprint, task_id=None):
        op = self.repo.operation(self.uid, operation_id)
        if not op:
            return None
        if op.get("request_fingerprint") != fingerprint or (task_id and op.get("task_id") != task_id):
            _fail("operation_id já utilizado para outra operação.", 409)
        task, context = self._task(op["task_id"])
        return {"task": self._enrich(task, context), "replayed": True,
                "applied_version": op.get("result_version")}

    def _event(self, task, event_type, data=None, occurred_at=None):
        return {"tenant_id": self.repo.tenant_id, "task_id": task["id"],
                "contact_id": task["contact_id"], "conversation_id": task.get("conversation_id"),
                "event_type": event_type, "actor_type": "user", "actor_user_id": self.user_id,
                "actor_uid": self.uid, "occurred_at": occurred_at or self.now(),
                "recorded_at": self.now(), "data": data or {}}

    def get_settings(self):
        self._actor()
        current = self.repo.settings()
        return {"settings": {**copy.deepcopy(DEFAULT_SETTINGS), **(current or {})}}

    def save_settings(self, payload):
        actor = self._actor()
        if not self.can_configure:
            _fail("Apenas gestão autorizada pode alterar horários.", 403)
        if not isinstance(payload, dict):
            _fail("Configuração inválida.")
        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            _fail("Informe a versão da configuração.")
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        existing = self.repo.settings() or settings
        queues = payload.get("queues", existing.get("queues"))
        if not isinstance(queues, list) or not 1 <= len(queues) <= 10:
            _fail("Configure de uma a dez filas.")
        old_keys = {q["key"] for q in existing["queues"]}
        clean_queues = []
        keys = set()
        for queue in queues:
            if not isinstance(queue, dict):
                _fail("Fila inválida.")
            key = _identifier(queue.get("key"), "Identificador de fila")
            if key in keys:
                _fail("Fila duplicada.")
            keys.add(key)
            active = queue.get("active", True)
            if not isinstance(active, bool):
                _fail("Estado da fila inválido.")
            clean_queues.append({"key": key, "label": _text(queue.get("label"), "Nome da fila", 60, True), "active": active})
        if not old_keys.issubset(keys):
            _fail("Preserve os identificadores das filas; desative em vez de excluir.")
        hours = payload.get("contact_hours", existing.get("contact_hours", {}))
        if not isinstance(hours, dict) or any(str(day) not in {str(d) for d in range(7)} for day in hours):
            _fail("Dias de contato inválidos.")
        clean_hours = {}
        for day in range(7):
            intervals = hours.get(str(day), [])
            if not isinstance(intervals, list) or len(intervals) > 4:
                _fail("Use até quatro faixas por dia.")
            clean = []
            for interval in intervals:
                if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                    _fail("Faixa de horário inválida.")
                start, end = map(_clock_minutes, interval)
                if start >= end:
                    _fail("O fim da faixa deve ser posterior ao início.")
                clean.append([interval[0], interval[1]])
            clean.sort()
            if any(clean[i][1] > clean[i + 1][0] for i in range(len(clean) - 1)):
                _fail("Faixas de horário não podem se sobrepor.")
            if day >= 5 and clean:
                _fail("Sábado e domingo não são dias de contato no piloto.")
            clean_hours[str(day)] = clean
        holidays = payload.get("holidays", existing.get("holidays", []))
        if not isinstance(holidays, list) or len(holidays) > 366:
            _fail("Datas sem contato inválidas.")
        try:
            holidays = sorted({date.fromisoformat(str(day)).isoformat() for day in holidays})
        except (ValueError, TypeError):
            _fail("Informe datas sem contato como AAAA-MM-DD.")
        preferred = payload.get("preferred_time", existing.get("preferred_time"))
        if preferred:
            _clock_minutes(preferred)
            if not any(start <= preferred < end for values in clean_hours.values() for start, end in values):
                _fail("Horário preferido deve estar em uma faixa permitida.")
        settings.update(version=version + 1, queues=clean_queues, contact_hours=clean_hours,
                        holidays=holidays, preferred_time=preferred or None,
                        configured=any(clean_hours.values()), updated_at=self.now(),
                        updated_by_user_id=actor["id"], updated_by_uid=self.uid)
        if payload.get("timezone", "America/Sao_Paulo") != "America/Sao_Paulo":
            _fail("O fuso do piloto é America/Sao_Paulo.")
        return {"settings": self.repo.save_settings(settings, version)}

    def _calendar_allowed(self, moment, settings):
        local = moment.astimezone(BR_TZ)
        if local.weekday() >= 5 or local.date().isoformat() in settings["holidays"]:
            return False
        hhmm = local.strftime("%H:%M")
        return any(start <= hhmm < end for start, end in settings["contact_hours"].get(str(local.weekday()), []))

    def _due(self, raw, purpose, settings):
        due = _dt(raw, "prazo")
        if due <= self.now():
            _fail("Escolha um prazo futuro; nenhum horário foi alterado automaticamente.")
        if purpose != "internal":
            if not settings.get("configured"):
                _fail("Configure os dias e horários de follow-up antes de agendar contatos.", 409)
            if not self._calendar_allowed(due, settings):
                _fail("Prazo fora dos dias/horários permitidos. Escolha e confirme outro horário.")
        return due

    def suggest_due(self, payload):
        """Sugestao para escolha humana; nunca salva tarefa ou contato."""
        self._actor()
        appointment = _dt(payload.get("appointment_at"), "horário da consulta")
        task_type = payload.get("type")
        if task_type not in ("confirmacao_consulta", "lembrete_consulta"):
            _fail("Sugestão disponível para confirmação e lembrete de consulta.")
        settings = self.get_settings()["settings"]
        nominal = appointment - timedelta(hours=72 if task_type == "confirmacao_consulta" else 24)
        result = {"nominal_at": nominal, "suggested_at": None, "requires_confirmation": True,
                  "late_notice": False, "use_current_contact": False, "reason": "configuration_required"}
        if not settings.get("configured"):
            return result
        suggestion = nominal
        local = nominal.astimezone(BR_TZ)
        if local.weekday() >= 5 or local.date().isoformat() in settings["holidays"]:
            result["reason"] = "previous_workday"
            for offset in range(1, 367):
                candidate = local - timedelta(days=offset)
                ranges = settings["contact_hours"].get(str(candidate.weekday()), [])
                if not ranges or candidate.date().isoformat() in settings["holidays"]:
                    continue
                hhmm = local.strftime("%H:%M")
                if not any(start <= hhmm < end for start, end in ranges):
                    hhmm = settings.get("preferred_time") or ranges[0][0]
                    if not any(start <= hhmm < end for start, end in ranges):
                        hhmm = ranges[0][0]
                suggestion = datetime.combine(candidate.date(), time.fromisoformat(hhmm), tzinfo=BR_TZ).astimezone(timezone.utc)
                break
            else:
                return dict(result, reason="no_available_time")
        elif nominal > self.now() and not self._calendar_allowed(nominal, settings):
            return dict(result, reason="choose_permitted_time")
        else:
            result["reason"] = "nominal"
        if suggestion <= self.now():
            result.update(late_notice=True, use_current_contact=True, reason="late_booking")
            first = (self.now() + timedelta(minutes=1)).astimezone(BR_TZ).replace(second=0, microsecond=0)
            suggestion = None
            for offset in range(367):
                day = first.date() + timedelta(days=offset)
                if day.isoformat() in settings["holidays"]:
                    continue
                for start, end in settings["contact_hours"].get(str(day.weekday()), []):
                    candidate = datetime.combine(day, time.fromisoformat(start), tzinfo=BR_TZ)
                    if candidate < first:
                        candidate = first
                    if candidate.date() != day or candidate.strftime("%H:%M") >= end:
                        continue
                    candidate = candidate.astimezone(timezone.utc)
                    if candidate < appointment:
                        suggestion = candidate
                        break
                if suggestion or datetime.combine(day, time.min, tzinfo=BR_TZ).astimezone(timezone.utc) >= appointment:
                    break
            if suggestion is None:
                result["reason"] = "needs_team_decision"
        result["suggested_at"] = suggestion
        return result

    def _queue(self, key, settings):
        if not any(q.get("key") == key and q.get("active") for q in settings["queues"]):
            _fail("Fila inexistente ou desativada.")
        return key

    def _commercial(self, task, context):
        if task.get("contact_purpose") == "commercial" and self.commercial_blocked(context["contact"]):
            _fail("Paciente pediu para não receber novas retomadas comerciais.", 409)

    def create_task(self, payload):
        actor = self._actor()
        if not isinstance(payload, dict):
            _fail("Tarefa inválida.")
        operation_id = _identifier(payload.get("operation_id"), "operation_id")
        fingerprint = self._fingerprint(payload)
        replay = self._replay(operation_id, fingerprint)
        if replay:
            return replay
        contact_id = _number(payload.get("contact_id"), "Contato")
        conversation_id = payload.get("conversation_id") or None
        if conversation_id:
            _identifier(conversation_id, "Conversa")
        context = self._access(contact_id, conversation_id)
        settings = self.get_settings()["settings"]
        task_type = payload.get("type", "retorno")
        if task_type not in TASK_TYPES:
            _fail("Tipo de tarefa inválido.")
        purpose = payload.get("contact_purpose", TASK_TYPES[task_type])
        if purpose not in ("commercial", "service", "internal"):
            _fail("Finalidade da tarefa inválida.")
        if purpose != TASK_TYPES[task_type]:
            _fail("A finalidade deve corresponder ao tipo explícito da tarefa.")
        task_id = "task_" + self.repo.operation_key(self.uid, operation_id)
        now = self.now()
        task = {"id": task_id, "tenant_id": self.repo.tenant_id, "contact_id": contact_id,
                "conversation_id": conversation_id,
                "channel_id": (context.get("conversation") or {}).get("channel_id"),
                "type": task_type, "contact_purpose": purpose,
                "title": _text(payload.get("title"), "Título", 160, True),
                "description": _text(payload.get("description", ""), "Contexto", 600),
                "due_at": self._due(payload.get("due_at"), purpose, settings),
                "status": "pending", "assignment_mode": "queue",
                "queue_key": self._queue(payload.get("queue_key", "reception"), settings),
                "assignee_user_id": None, "assignee_uid": "", "source": "manual",
                "created_by_user_id": self.user_id, "created_by_uid": self.uid,
                "created_at": now, "updated_at": now, "version": 1,
                "response_anchor_at": now, "response_anchor_kind": "created",
                "attempt_count": 0, "unanswered_attempts": 0}
        self._commercial(task, context)
        guards = self._guards(context, (actor,)) + self._settings_guards(settings)
        if payload.get("assignee_user_id") is not None:
            target = self._target(payload["assignee_user_id"], context, conversation_id)
            if target["id"] != self.user_id and not self.can_manage:
                _fail("Redistribuição para outra pessoa exige gestão autorizada.", 403)
            task.update(assignment_mode="user", assignee_user_id=target["id"], assignee_uid=target["firebase_uid"])
            guards += self._guards(context, (target,))
        if payload.get("appointment_at"):
            task["appointment_at"] = _dt(payload["appointment_at"], "horário do compromisso")
            if task["appointment_at"] <= task["due_at"]:
                _fail("O contato de confirmação/lembrete deve ocorrer antes do compromisso.")
        elif task_type in ("confirmacao_consulta", "lembrete_consulta"):
            _fail("Informe o horário confirmado da consulta na agenda oficial.")
        if payload.get("appointment_ref"):
            task["appointment_ref"] = _identifier(payload["appointment_ref"], "Referência do compromisso")
        if payload.get("appointment_kind"):
            task["appointment_kind"] = self._appointment_kind(payload["appointment_kind"])
        result = self.repo.commit(task_id, None, self.uid, operation_id, fingerprint, task,
                                  [self._event(task, "task_created", {"type": task_type, "due_at": task["due_at"], "queue_key": task["queue_key"]})], guards)
        result["task"] = self._enrich(result["task"], context)
        return result

    def _appointment_kind(self, value):
        if value not in ("consultation", "procedure"):
            _fail("Identifique consulta ou procedimento/tratamento.")
        return value

    def _validate_appointment_due(self, task):
        if task.get("appointment_at") and _dt(task["due_at"]) >= _dt(task["appointment_at"]):
            _fail("O prazo de contato deve ser anterior ao compromisso. Revise os horários manualmente.")

    def task_action(self, task_id, payload):
        actor = self._actor()
        if not isinstance(payload, dict):
            _fail("Operação inválida.")
        operation_id = _identifier(payload.get("operation_id"), "operation_id")
        fingerprint = self._fingerprint(payload, task_id)
        replay = self._replay(operation_id, fingerprint, task_id)
        if replay:
            return replay
        task, context = self._task(task_id)
        self._require_modify(task)
        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != task.get("version"):
            _fail("A tarefa mudou. Atualize a tela antes de continuar.", 409)
        if task.get("status") != "pending":
            _fail("Tarefa já concluída ou cancelada.", 409)
        action = payload.get("action")
        for boolean_field in ("keep_assigned", "complete", "reviewed_after_three", "shared_actions_confirmed"):
            if boolean_field in payload and not isinstance(payload[boolean_field], bool):
                _fail("%s deve ser verdadeiro ou falso." % boolean_field)
        if payload.get("complete") and payload.get("next_due_at"):
            _fail("Escolha concluir ou reagendar a tentativa.")
        updated = copy.deepcopy(task)
        events = []
        companions = []
        guards = self._guards(context, (actor,))
        settings = self.get_settings()["settings"]

        def return_to_queue():
            if updated.get("assignment_mode") != "queue":
                events.append(self._event(task, "task_assigned", {"from_user_id": updated.get("assignee_user_id"), "to_user_id": None, "queue_key": task["queue_key"]}))
            updated.update(assignment_mode="queue", assignee_user_id=None, assignee_uid="")

        if action == "take":
            if task.get("assignment_mode") != "queue":
                _fail("A tarefa já foi pega por outra pessoa.", 409)
            self._commercial(task, context)
            target = self._target(self.user_id, context, task.get("conversation_id"))
            updated.update(assignment_mode="user", assignee_user_id=self.user_id, assignee_uid=self.uid)
            events.append(self._event(task, "task_taken", {"assignee_user_id": self.user_id, "queue_key": task["queue_key"]}))
            guards += self._guards(context, (target,))
        elif action in ("return_to_queue", "assign"):
            target_id = payload.get("assignee_user_id")
            if action == "return_to_queue" or target_id is None:
                return_to_queue()
            else:
                if not self.can_manage and _number(target_id, "Responsável") != self.user_id:
                    _fail("Redistribuição exige gestão autorizada.", 403)
                target = self._target(target_id, context, task.get("conversation_id"))
                updated.update(assignment_mode="user", assignee_user_id=target["id"], assignee_uid=target["firebase_uid"])
                guards += self._guards(context, (target,))
                events.append(self._event(task, "task_assigned", {"from_user_id": task.get("assignee_user_id"), "to_user_id": target["id"], "queue_key": task["queue_key"]}))
        elif action == "update":
            for key, max_size in (("title", 160), ("description", 600)):
                if key in payload:
                    updated[key] = _text(payload[key], key, max_size, key == "title")
            if "queue_key" in payload:
                updated["queue_key"] = self._queue(payload["queue_key"], settings)
            appointment_fields = ("appointment_at", "appointment_ref", "appointment_kind")
            if any(key in payload for key in appointment_fields):
                if task["type"] not in ("confirmacao_consulta", "lembrete_consulta"):
                    _fail("Correção de compromisso é restrita à confirmação e ao lembrete.")
                if "appointment_at" in payload:
                    updated["appointment_at"] = _dt(payload["appointment_at"], "horário do compromisso")
                if "appointment_ref" in payload:
                    updated["appointment_ref"] = _identifier(payload["appointment_ref"], "Referência do compromisso")
                if "appointment_kind" in payload:
                    updated["appointment_kind"] = self._appointment_kind(payload["appointment_kind"])
                self._validate_appointment_due(updated)
            # Tipo/finalidade sao imutaveis: nao transformar comercial em servico para furar recusa.
            if any(key in payload and payload[key] != task.get(key) for key in ("type", "contact_purpose", "contact_id", "conversation_id")):
                _fail("Contato, conversa, tipo e finalidade não podem ser trocados nesta tarefa.")
            events.append(self._event(task, "task_updated", {"fields": [key for key in ("title", "description", "queue_key", *appointment_fields) if key in payload]}))
        elif action == "reschedule":
            self._commercial(task, context)
            due = self._due(payload.get("due_at"), task["contact_purpose"], settings)
            updated["due_at"] = due
            self._validate_appointment_due(updated)
            guards += self._settings_guards(settings)
            events.append(self._event(task, "task_rescheduled", {"from_due_at": task["due_at"], "due_at": due}))
            if payload.get("keep_assigned") is not True:
                return_to_queue()
        elif action == "attempt":
            self._commercial(task, context)
            occurred = _dt(payload.get("occurred_at"), "momento da tentativa")
            if occurred > self.now():
                _fail("Não registre uma tentativa futura.")
            result_code = payload.get("result", payload.get("result_code"))
            if result_code not in RESULTS:
                _fail("Resultado de tentativa inválido.")
            if task.get("unanswered_attempts", 0) >= 3 and payload.get("reviewed_after_three") is not True:
                _fail("Revise o histórico e a abordagem antes de registrar nova tentativa sem retorno.", 409)
            method = payload.get("method", "phone")
            if method not in ("phone", "whatsapp", "other"):
                _fail("Meio da tentativa inválido.")
            attempt_id = self.repo.operation_key(self.uid, operation_id)
            data = {"attempt_id": attempt_id, "result_code": result_code, "method": method,
                    "reviewed_after_three": payload.get("reviewed_after_three") is True}
            if result_code == "scheduled":
                data["appointment_kind"] = self._appointment_kind(payload.get("appointment_kind"))
            updated["attempt_count"] = int(task.get("attempt_count", 0)) + 1
            updated["unanswered_attempts"] = int(task.get("unanswered_attempts", 0)) + 1 if result_code == "not_reached" else 0
            current_anchor = _dt(task.get("response_anchor_at") or task["created_at"])
            if occurred >= current_anchor:
                updated.update(response_anchor_at=occurred, response_anchor_kind="attempt", last_attempt_id=attempt_id)
            events.append(self._event(task, "task_attempted", data, occurred))
            if payload.get("complete"):
                if result_code == "not_reached":
                    _fail("Sem resposta registra tentativa e mantém o acompanhamento pendente.")
                updated.update(status="completed", completed_at=self.now(), completed_by_user_id=self.user_id,
                               completed_by_uid=self.uid, result_code=result_code)
                events.append(self._event(task, "task_completed", {"result_code": result_code, **({"appointment_kind": data["appointment_kind"]} if "appointment_kind" in data else {})}))
            elif payload.get("next_due_at"):
                due = self._due(payload["next_due_at"], task["contact_purpose"], settings)
                updated["due_at"] = due
                self._validate_appointment_due(updated)
                guards += self._settings_guards(settings)
                events.append(self._event(task, "task_rescheduled", {"from_due_at": task["due_at"], "due_at": due, "attempt_id": attempt_id}))
                if payload.get("keep_assigned") is not True:
                    return_to_queue()
        elif action == "complete":
            result_code = payload.get("result", payload.get("result_code", "action_done"))
            if result_code not in RESULTS or result_code == "not_reached":
                _fail("Sem resposta mantém o acompanhamento pendente; escolha outro desfecho ou cancele com motivo.")
            data = {"result_code": result_code}
            if result_code == "scheduled":
                data["appointment_kind"] = self._appointment_kind(payload.get("appointment_kind"))
            updated.update(status="completed", completed_at=self.now(), completed_by_user_id=self.user_id,
                           completed_by_uid=self.uid, result_code=result_code)
            events.append(self._event(task, "task_completed", data))
        elif action in ("cancel", "refuse_specific"):
            reason = "specific_refusal" if action == "refuse_specific" else _text(payload.get("reason", ""), "Motivo", 120, True)
            updated.update(status="cancelled", cancelled_at=self.now(), cancelled_by_user_id=self.user_id,
                           cancelled_by_uid=self.uid, cancel_reason=reason)
            events.append(self._event(task, "task_cancelled", {"reason": reason}))
        else:
            _fail("Ação de tarefa inválida.")
        shared_ids = payload.get("shared_task_ids", [])
        if not isinstance(shared_ids, list) or len(shared_ids) > 1 or task_id in shared_ids:
            _fail("Informe no máximo uma tarefa complementar distinta.")
        if shared_ids:
            if action != "attempt" or payload.get("complete") is not True or payload.get("shared_actions_confirmed") is not True:
                _fail("Contato compartilhado exige tentativa real e confirmação explícita de ambas as ações.")
            if task.get("type") not in ("confirmacao_consulta", "lembrete_consulta"):
                _fail("Contato compartilhado é restrito à confirmação e ao lembrete do mesmo compromisso.")
            if not task.get("appointment_ref") or not task.get("appointment_at"):
                _fail("Vincule a referência e o horário do mesmo compromisso nas duas tarefas.")
            versions = payload.get("shared_task_versions")
            if not isinstance(versions, dict):
                _fail("Informe a versão da outra tarefa.")
            other, other_context = self._task(shared_ids[0])
            self._require_modify(other)
            other_version = versions.get(other["id"])
            if isinstance(other_version, bool) or not isinstance(other_version, int) or other_version != other.get("version"):
                _fail("A tarefa complementar mudou. Atualize a tela.", 409)
            if (other.get("status") != "pending" or other.get("contact_id") != task["contact_id"]
                    or other.get("appointment_ref") != task["appointment_ref"]
                    or other.get("appointment_at") != task["appointment_at"]
                    or {task.get("type"), other.get("type")} != {"confirmacao_consulta", "lembrete_consulta"}):
                _fail("As tarefas devem ser confirmação e lembrete pendentes do mesmo compromisso.")
            # Um contato so cumpre ambas quando seus prazos coincidem, ou ambos ja venceram.
            if task["due_at"] != other["due_at"] and not (task["due_at"] <= self.now() and other["due_at"] <= self.now()):
                _fail("Lembrete ainda futuro permanece pendente.")
            other_updated = copy.deepcopy(other)
            other_updated.update(status="completed", version=other_version + 1, updated_at=self.now(),
                                 completed_at=self.now(), completed_by_user_id=self.user_id,
                                 completed_by_uid=self.uid, result_code=updated["result_code"],
                                 unanswered_attempts=0)
            if occurred >= _dt(other.get("response_anchor_at") or other["created_at"]):
                other_updated.update(response_anchor_at=occurred, response_anchor_kind="attempt", last_attempt_id=attempt_id)
            for event in events:
                if event["event_type"] == "task_attempted":
                    event["data"]["shared_task_ids"] = [other["id"]]
            companions.append({"task": other_updated, "version": other_version,
                               "activities": [self._event(other, "task_completed", {
                                   "result_code": updated["result_code"], "attempt_id": attempt_id,
                                   "origin_task_id": task_id, "shared_task_ids": [task_id]})]})
            guards += self._guards(other_context)
        if not events:
            events = [self._event(task, "task_updated", {"fields": []})]
        updated.update(version=version + 1, updated_at=self.now())
        result = self.repo.commit(task_id, version, self.uid, operation_id, fingerprint, updated, events, guards, companions)
        result["task"] = self._enrich(result["task"], context)
        return result

    def _response(self, task, context):
        anchor = _dt(task.get("response_anchor_at") or task["created_at"])
        rows = self.repo.response_page(task["contact_id"], task.get("conversation_id"), anchor, limit=12)
        for row in rows:
            if row.get("direction") != "inbound" or row.get("is_backup") or row.get("is_rating_message") or row.get("admin_only"):
                continue
            # IDs de controle existentes sao normalizados para text pelo webhook.
            if row.get("msg_type") == "text" and str(row.get("content") or "").strip().lower() in {"lgpd_aceitar", "lgpd_recusar", "rating_ruim", "rating_bom", "rating_excelente"}:
                continue
            if row.get("visibility", "all") != "all" or row.get("msg_type") not in {"text", "audio", "image", "document", "video", "gif", "sticker", "location", "contacts"}:
                continue
            try:
                timestamp = _dt(row.get("timestamp_wa"))
            except HTTPException:
                continue
            if timestamp <= anchor or timestamp > self.now() or row.get("status", "received") not in ("received", "read"):
                continue
            # Cada referencia de thread tem o acesso atual validado; contato nao concede todas.
            conversation_id = row.get("conversation_id")
            if not conversation_id:
                continue
            try:
                self._access(task["contact_id"], conversation_id)
            except HTTPException as exc:
                if exc.status_code in (403, 404):
                    continue
                raise
            return True, True
        return False, len(rows) < 12

    def _enrich(self, task, context, response=True, settings=None):
        result = dict(task)
        contact = context["contact"]
        result["contact"] = {key: contact.get(key) for key in ("id", "display_name", "lead_temperature", "bot_completed", "is_archived")}
        result["can_modify"] = task.get("status") == "pending" and self._may_modify(task)
        result["commercial_blocked"] = self.commercial_blocked(contact)
        result["review_required"] = task.get("unanswered_attempts", 0) >= 3
        result["response_received"], result["response_checked_complete"] = self._response(task, context) if response else (False, False)
        result["response_label"] = "Paciente respondeu após última tentativa" if task.get("response_anchor_kind") == "attempt" else "Paciente respondeu após a criação da tarefa"
        settings = settings or {**copy.deepcopy(DEFAULT_SETTINGS), **(self.repo.settings() or {})}
        result["calendar_conflict"] = task.get("contact_purpose") != "internal" and not self._calendar_allowed(_dt(task["due_at"]), settings)
        return result

    def get_task(self, task_id):
        self._actor()
        task, context = self._task(task_id)
        return {"task": self._enrich(task, context)}

    def _cursor(self, value, filters, kind):
        scope = hashlib.sha256(_json([self.repo.tenant_id, self.uid, self.can_manage, filters, kind]).encode()).hexdigest()
        if value is None:
            return None, scope
        try:
            if not isinstance(value, str) or len(value) > 1600:
                raise ValueError()
            data, sig = value.split(".")
            expected = hmac.new(str(SECRET_KEY).encode(), data.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise ValueError()
            payload = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
            if payload["scope"] != scope or _dt(payload["expires"]) <= self.now():
                raise ValueError()
            return (_dt(payload["at"]), _identifier(payload["id"], "Cursor")), scope
        except (ValueError, KeyError, TypeError, UnicodeError, HTTPException):
            _fail("Cursor inválido ou expirado.", 400)

    def _encode_cursor(self, at, doc_id, scope):
        payload = {"scope": scope, "at": _dt(at).isoformat(), "id": doc_id,
                   "expires": (self.now() + timedelta(hours=1)).isoformat()}
        data = base64.urlsafe_b64encode(_json(payload).encode()).decode().rstrip("=")
        return data + "." + hmac.new(str(SECRET_KEY).encode(), data.encode(), hashlib.sha256).hexdigest()

    def list_tasks(self, filters=None):
        self._actor()
        filters = dict(filters or {})
        status = filters.get("status", "pending")
        group = filters.get("group", "all")
        scope = filters.get("scope", "mine")
        if status not in ("pending", "completed", "cancelled") or group not in ("all", "overdue", "today", "upcoming") or scope not in ("mine", "queue", "team", "all", "contact"):
            _fail("Filtro inválido.")
        if scope == "contact" and not filters.get("contact_id"):
            _fail("Visão por contato exige contact_id.")
        if scope in ("team", "all") and not self.can_manage and not filters.get("contact_id"):
            _fail("Visão da equipe exige gestão autorizada.", 403)
        try:
            limit = max(1, min(int(filters.get("limit", 25)), 50))
        except (ValueError, TypeError):
            _fail("Limite inválido.")
        query = {"status": status}
        if filters.get("contact_id"):
            query["contact_id"] = _number(filters["contact_id"], "Contato")
            self._access(query["contact_id"])
        today = datetime.combine(self.now().astimezone(BR_TZ).date(), time.min, tzinfo=BR_TZ).astimezone(timezone.utc)
        if group == "overdue":
            query["due_until"] = self.now()
        elif group == "today":
            query.update(due_from=self.now(), due_until=today + timedelta(days=1))
        elif group == "upcoming":
            query["due_from"] = today + timedelta(days=1)
        cursor_filters = {"status": status, "group": group, "scope": scope, "queue_key": filters.get("queue_key"), "contact_id": query.get("contact_id"), "day": today.isoformat()}
        after, scope_fp = self._cursor(filters.get("cursor"), cursor_filters, "tasks")
        items = []
        examined = 0
        authorized = 0
        exhausted = False
        last = None
        settings = self.get_settings()["settings"]
        while len(items) < limit and examined < 150:
            rows = self.repo.task_page(query, after, min(50, 150 - examined))
            if not rows:
                exhausted = True
                break
            for row in rows:
                examined += 1
                last = (_dt(row["due_at"]), row["id"])
                after = last
                if scope == "mine" and row.get("assignee_uid") != self.uid:
                    continue
                if scope == "queue" and row.get("assignment_mode") != "queue":
                    continue
                if filters.get("queue_key") and row.get("queue_key") != filters["queue_key"]:
                    continue
                try:
                    context = self._access(row["contact_id"], row.get("conversation_id"))
                except HTTPException as exc:
                    if exc.status_code in (403, 404):
                        continue
                    raise
                authorized += 1
                items.append(self._enrich(row, context, settings=settings))
                if len(items) >= limit:
                    break
            if len(rows) < 50 and len(items) < limit:
                exhausted = True
                break
        next_cursor = self._encode_cursor(*last, scope_fp) if last and not exhausted else None
        return {"tasks": items, "next_cursor": next_cursor, "has_more": bool(next_cursor), "scanned": authorized}

    def list_activities(self, filters=None):
        self._actor()
        filters = dict(filters or {})
        if filters.get("task_id"):
            task, context = self._task(filters["task_id"])
            field, value = "task_id", task["id"]
        elif filters.get("contact_id"):
            field, value = "contact_id", _number(filters["contact_id"], "Contato")
            self._access(value)
        else:
            _fail("Informe a tarefa ou o contato.")
        try:
            limit = max(1, min(int(filters.get("limit", 25)), 50))
        except (TypeError, ValueError):
            _fail("Limite inválido.")
        after, scope = self._cursor(filters.get("cursor"), {field: value}, "activities")
        items = []
        examined = 0
        exhausted = False
        last = None
        while len(items) < limit and examined < 150:
            rows = self.repo.activity_page(field, value, after, min(50, 150 - examined))
            if not rows:
                exhausted = True
                break
            for row in rows:
                examined += 1
                last = (_dt(row["recorded_at"]), row["id"])
                after = last
                try:
                    self._access(row["contact_id"], row.get("conversation_id"))
                except HTTPException as exc:
                    if exc.status_code in (403, 404):
                        continue
                    raise
                clean = {key: value for key, value in row.items() if key not in ("request_fingerprint", "result_version")}
                items.append(clean)
                if len(items) >= limit:
                    break
            if len(rows) < 50 and len(items) < limit:
                exhausted = True
                break
        next_cursor = self._encode_cursor(*last, scope) if last and not exhausted else None
        return {"activities": items, "next_cursor": next_cursor, "has_more": bool(next_cursor), "scanned": len(items)}
