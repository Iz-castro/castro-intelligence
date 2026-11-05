# -*- coding: utf-8 -*-
"""Regras do funil comercial: quadro, drawer, mudanca de etapa, painel,
textos da clinica e o desfecho do modal "Encerrar atendimento".

Nada aqui envia WhatsApp, abre/assume atendimento, mexe em dono, setor,
bot, LGPD, recusa comercial, tags, threads, mensagens ou tarefas. Escritas,
todas pela transacao do repositorio: a etapa (campos crm_* do contato) + 1
Activity; o desfecho legado equivalente (qualification e, em 'convertido',
converted_by_user_id) junto, so em mudanca MANUAL ("uma classificacao so",
decisao do PO de 28/10); e os nomes/textos que a clinica edita. O MOTIVO
(categoria pode ser dado de saude) e a nota livre ficam so na Activity: o
contato nunca os recebe.

Escopo de leitura = o do CRM: privilegiado (can_see_all_tenant) ve o
tenant; operador ve proprios + pool sem dono (mesma consulta do picker
v2.1) com o predicado _require_contact_access por linha. Backup e arquivado
ficam fora do quadro. Etapa com visibility_permission (Novo contato = lead
ainda com o agente de IA) some do quadro de quem nao tem a permissao; o
drawer do contato continua (acesso do CRM, nao do quadro).
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from google.api_core import exceptions as google_exceptions

import config
import funnel_catalog as fc
from commercial_contact_policy import is_commercial_contact_blocked
from config import SECRET_KEY
from firestore_common import get_tenant_context, tenant_context
import followup_access
from funnel_repository import (
    CONTACT_GUARD_FIELDS, USER_GUARD_FIELDS, FunnelRepository, StageConflict, stage_version,
)
from rbac import can_see_all_tenant, has_permission

logger = logging.getLogger("castro_crm.funnel_service")


CARD_LIMIT = 20
PAGE_MAX = 50
HISTORY_PAGE = 20
TASK_BATCH = 30
TASK_LIMIT = 200
# Lote de tarefas cheio (len == TASK_LIMIT) pode ter cortado a proxima tarefa
# de algum contato: reconsulta so quem ficou sem, ate este teto de rodadas.
TASK_ROUNDS = 3
DRAWER_TASKS = 5
REASON_STREAM_LIMIT = 3000
COLUMN_WORKERS = 6
DASHBOARD_WORKERS = 8
DASHBOARD_TTL_SECONDS = 120.0
DASHBOARD_CACHE_MAX = 64
# Faixa aceita no painel: de DASHBOARD_FIRST_MONTH ate o mes seguinte ao
# atual (fuso BR). Fora dela = 422 month_invalid, sem calcular nada.
DASHBOARD_FIRST_MONTH = "2020-01"
# Motivos: um stream so por etapa de perda e mes; movimento/reativacao e
# triagem (antigos/sem etapa) sao separados em memoria (indice 10, in de 3).
REASON_ENTRY_KINDS = tuple(fc.COUNTED_ENTRY_KINDS) + (fc.ENTRY_KIND_TRIAGE,)
CURSOR_TTL = timedelta(hours=1)
# Throttle em memoria por tenant|uid nos GETs de quadro/coluna (e em todo
# calculo do painel, refresh ou cache vencido): sem polling no front, isto so
# morde clique repetido ou script.
RATE_LIMIT = 20
RATE_WINDOW_SECONDS = 10.0
BOT_OUTCOMES = ("agendado", "link_enviado", "duvida_respondida", "sem_interesse")
SUGGEST_OUTCOMES = ("agendado", "link_enviado")
_FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)
# Texto so com digitos e pontuacao de telefone (e digitos suficientes) nao e
# nome: o CRM grava o telefone formatado em display_name quando falta nome.
_PHONE_TEXT = re.compile(r"[\d\s()+.\-]+")
PHONE_DIGITS_MIN = 8

# Textos da clinica (tela "Etapas", doc system_settings/funnel): cache curto
# por tenant, invalidado no PUT desta instancia (as demais convergem no TTL).
OVERRIDES_TTL_SECONDS = 30.0
OVERRIDE_FIELDS = ("stage_labels", "stage_descriptions", "reason_labels")
# Legado "em andamento": o fechamento manual exige desfecho (gate de main.py).
LEGACY_OPEN = ("novo", "em_atendimento")

_RATE_LOCK = threading.Lock()
_RATE_HITS = {}
_DASHBOARD_LOCK = threading.Lock()
_DASHBOARD_CACHE = {}
_OVERRIDES_LOCK = threading.Lock()
_OVERRIDES_CACHE = {}


def reset_rate_limits():
    with _RATE_LOCK:
        _RATE_HITS.clear()


def reset_dashboard_cache():
    with _DASHBOARD_LOCK:
        _DASHBOARD_CACHE.clear()


def reset_overrides_cache(tenant_id=None):
    with _OVERRIDES_LOCK:
        if tenant_id is None:
            _OVERRIDES_CACHE.clear()
        else:
            _OVERRIDES_CACHE.pop(str(tenant_id), None)


def _cached_overrides(tenant_id):
    """Doc system_settings/funnel do tenant ({} sem doc), cache de 30 s.
    Leitura falha = rotulos padrao nesta request, sem cachear a falha."""
    now = time.monotonic()
    with _OVERRIDES_LOCK:
        entry = _OVERRIDES_CACHE.get(tenant_id)
    if entry and entry[0] > now:
        return entry[1]
    try:
        doc = FunnelRepository(tenant_id).overrides() or {}
    except Exception as exc:
        logger.warning("textos do funil ilegiveis (tenant=%s): %s", tenant_id, type(exc).__name__)
        return {}
    with _OVERRIDES_LOCK:
        _OVERRIDES_CACHE[tenant_id] = (now + OVERRIDES_TTL_SECONDS, doc)
    return doc


def load_catalog(tenant_id):
    """Catalogo das TELAS do funil e do encerramento: settings.funnel do
    tenant (cache de 60 s do tenant_service) com os textos da clinica por
    cima (system_settings/funnel). None = funil desligado (flag, tenant ou
    config). Nunca levanta. O webhook e a entrada automatica continuam com
    funnel_catalog.load_tenant_funnel (sem textos: rotulo nao muda regra)."""
    try:
        if not getattr(config, "FEATURE_FUNNEL", False) or not tenant_id:
            return None
        tenant_id = str(tenant_id)
        tenant_doc = _default_tenant_loader(tenant_id) or {}
        if not fc.funnel_for_tenant(tenant_doc):
            return None
        return fc.funnel_for_tenant(tenant_doc, _cached_overrides(tenant_id))
    except Exception as exc:
        logger.warning("catalogo do funil indisponivel (tenant=%s): %s", tenant_id, type(exc).__name__)
        return None


def _default_audit(tenant_id, user_id, action, detail):
    # Import tardio (database reexporta database_firestore). log_audit usa o
    # contexto implicito: roda sob o tenant explicito do funil.
    from database import log_audit
    with tenant_context(tenant_id):
        log_audit(user_id, action, detail)


def _dashboard_cache_get(key):
    with _DASHBOARD_LOCK:
        entry = _DASHBOARD_CACHE.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _dashboard_cache_put(key, payload):
    """Grava no cache do painel expurgando as vencidas e com teto fixo
    (mais antigas primeiro): meses distintos ou bumps de versao do catalogo
    nao acumulam memoria no worker."""
    now = time.monotonic()
    with _DASHBOARD_LOCK:
        for stale in [k for k, (expires, _) in _DASHBOARD_CACHE.items() if expires <= now]:
            _DASHBOARD_CACHE.pop(stale, None)
        _DASHBOARD_CACHE.pop(key, None)
        _DASHBOARD_CACHE[key] = (now + DASHBOARD_TTL_SECONDS, payload)
        while len(_DASHBOARD_CACHE) > max(1, int(DASHBOARD_CACHE_MAX)):
            _DASHBOARD_CACHE.pop(next(iter(_DASHBOARD_CACHE)))


def _shift_month(month, delta):
    year, mon = map(int, month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _phone_like(text, contact):
    """Vazio, igual ao telefone formatado do contato ou so telefone."""
    text = str(text or "").strip()
    if not text or text == str(contact.get("phone_formatted") or "").strip():
        return True
    return bool(_PHONE_TEXT.fullmatch(text) and len(_digits(text)) >= PHONE_DIGITS_MIN)


def display_name(contact):
    """Nome do contato no card, no drawer e no contexto, NUNCA o telefone.

    database_firestore._resolve_display_name cai para o telefone formatado
    sem nome declarado nem de perfil (webhook sem nome de perfil, nome
    declarado limpo): usa entao declared_name ou whatsapp_profile_name e, na
    falta, um rotulo com os 4 ultimos digitos para a equipe identificar."""
    contact = contact or {}
    for key in ("display_name", "declared_name", "whatsapp_profile_name"):
        value = contact.get(key)
        if isinstance(value, str) and not _phone_like(value, contact):
            return value.strip()
    digits = _digits(contact.get("wa_id")) or _digits(contact.get("phone_formatted"))
    if len(digits) >= 4:
        return "Contato sem nome (final %s)" % digits[-4:]
    return "Contato sem nome"


def _allow(key):
    now = time.monotonic()
    with _RATE_LOCK:
        if len(_RATE_HITS) > 5000:
            for stale in [k for k, hits in _RATE_HITS.items() if not hits or now - hits[-1] >= RATE_WINDOW_SECONDS]:
                _RATE_HITS.pop(stale, None)
        hits = [t for t in _RATE_HITS.get(key, ()) if now - t < RATE_WINDOW_SECONDS]
        allowed = len(hits) < RATE_LIMIT
        if allowed:
            hits.append(now)
        _RATE_HITS[key] = hits
        return allowed


def _fail(status, code, message, **extra):
    raise HTTPException(status, detail={"code": code, "message": message, **extra})


def _iso(value):
    moment = fc.as_utc(value)
    return moment.isoformat() if moment else None


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _int_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _same_user(value, user_id):
    parsed = _int_or_none(value)
    return parsed is not None and parsed == user_id


def _chunks(values, size):
    values = list(values)
    return [values[i:i + size] for i in range(0, len(values), size)]


def _default_tenant_loader(tenant_id):
    # Import tardio: cache de 60 s do tenant_service (mesmo doc do settings.ai).
    import tenant_service
    return tenant_service.get_tenant(tenant_id)


class FunnelService:
    def __init__(self, repository, user, authorize, catalog, require_contact_access=None,
                 clock=None, tenant_loader=None, channel_loader=None, commercial_blocked=None,
                 actor_row=None, audit=None):
        self.repo = repository
        self.user = dict(user or {})
        self.authorize = authorize
        self.catalog = catalog
        self.require_contact_access = require_contact_access
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.tenant_loader = tenant_loader or _default_tenant_loader
        # Canal vivo pelo mesmo lookup do autorizador (alvo de monkeypatch unico).
        self.channel_loader = channel_loader or (lambda channel_id: followup_access.get_channel(channel_id))
        self.commercial_blocked = commercial_blocked or is_commercial_contact_blocked
        # audit(tenant_id, user_id, action, detail): best-effort, apos o commit.
        self.audit = audit or _default_audit
        # Linha do usuario ja relida nesta request (require_user da rota): o
        # _actor a reaproveita em vez de reler. Sem ela (scripts/sims), rele.
        self._actor_row = dict(actor_row) if isinstance(actor_row, dict) else None
        if not catalog:
            _fail(404, "funnel_disabled", "Funil indisponível para este tenant.")
        if str(self.user.get("tenant_id") or "") != repository.tenant_id or not self.user.get("firebase_uid"):
            _fail(403, "tenant_mismatch", "Sessão sem tenant ou identidade válida.")
        self.uid = str(self.user["firebase_uid"])
        self.user_id = _int_or_none(self.user.get("id"))
        if self.user_id is None or self.user_id < 1:
            _fail(403, "user_inactive", "Usuário inválido.")
        self.privileged = can_see_all_tenant(self.user)
        self._users_cache = {}
        self._channels = {}
        self._conversations = {}
        self._lgpd_tracked = None
        self._defaults_cache = None

    # -- identidade e capacidades ---------------------------------------------

    def now(self):
        return fc.as_utc(self.clock()) or datetime.now(timezone.utc)

    def can(self, permission):
        return has_permission(self.user, permission)

    @property
    def tasks_visible(self):
        # Follow-up ligado PARA O TENANT (chave geral + settings.followup_enabled,
        # cache do tenant_service); sem ele o card nao mostra tarefa nem "sem
        # proxima acao". Import tardio: followup_routes importa o follow-up todo.
        if not self.can("gerenciar_followup"):
            return False
        from followup_routes import tenant_followup_enabled
        return tenant_followup_enabled(self.repo.tenant_id)

    def _actor(self):
        if self.user.get("read_only") or self.user.get("impersonating") or self.user.get("impersonation"):
            _fail(403, "read_only_session", "Sessão somente de leitura não acessa o funil.")
        row = self._actor_row if self._actor_row is not None else self.repo.user(self.user_id)
        if (not row or row.get("is_active", 1) not in (1, True)
                or str(row.get("firebase_uid") or "") != self.uid
                or row.get("tenant_id") not in (None, "", self.repo.tenant_id)):
            _fail(403, "user_inactive", "Usuário inativo ou identidade alterada.")
        if (row.get("role", "operador") != self.user.get("role", "operador")
                or (row.get("perfil_acesso_id") or "") != (self.user.get("perfil_acesso_id") or "")):
            _fail(403, "user_inactive", "O perfil do usuário mudou. Atualize a sessão.")
        return row

    def _rate(self):
        if not _allow((self.repo.tenant_id, self.uid)):
            _fail(429, "rate_limited", "Muitas consultas seguidas. Aguarde alguns segundos.")

    def _audit(self, action, detail):
        try:
            self.audit(self.repo.tenant_id, self.user_id, action, detail)
        except Exception as exc:
            logger.warning("auditoria do funil falhou (nao fatal): action=%s %s", action, type(exc).__name__)

    def capabilities(self):
        return {
            "can_move": self.can("mover_etapa_funil"),
            "can_dashboard": bool(self.privileged and self.can("ver_dashboard_funil")),
            "privileged": bool(self.privileged),
            "followup": self.tasks_visible,
            # Tela "Etapas" (nomes e textos da clinica): permissao existente.
            "can_configure": self.can("gerenciar_config_sistema"),
            "can_see_agent_contacts": self.can("ver_contatos_agente_funil"),
        }

    def visible(self, stage):
        """A etapa aparece no QUADRO deste usuario? (drawer nao depende)."""
        return fc.stage_visible(stage, self.can)

    def _defaults(self):
        """({etapa: (rotulo, texto)}, {motivo: rotulo}) SEM os textos da
        clinica: settings.funnel da Castro sobre o template, ou seja, o que
        "restaurar padrao" devolve. Doc do tenant do cache do tenant_service."""
        if self._defaults_cache is None:
            try:
                base = fc.funnel_for_tenant(self.tenant_loader(self.repo.tenant_id) or {}) or {}
            except Exception:
                base = {}
            stages, reasons = {}, {}
            for stage in self.catalog["stages"]:
                # Sem a config base (leitura falhou): o padrao do template.
                found = fc.stage_def(base, stage["key"]) or {
                    "label": stage.get("default_label") or stage["label"],
                    "description": stage.get("default_description") or ""}
                stages[stage["key"]] = (found["label"], found.get("description") or "")
            for reason in self.catalog["reasons"]:
                found = fc.reason_def(base, reason["key"]) or {
                    "label": reason.get("default_label") or reason["label"]}
                reasons[reason["key"]] = found["label"]
            self._defaults_cache = (stages, reasons)
        return self._defaults_cache

    def get_config(self):
        self._actor()
        stage_defaults, reason_defaults = self._defaults()
        stages = []
        for stage in self.catalog["stages"]:
            stale = stage.get("stale")
            default_label, default_description = stage_defaults[stage["key"]]
            stages.append({
                "key": stage["key"], "label": stage["label"], "kind": stage["kind"],
                "order": stage["order"], "requires_reason": bool(stage.get("requires_reason")),
                "manual_target": bool(stage.get("manual_target")),
                "milestone": bool(stage.get("milestone")), "appointment_kind": bool(stage.get("appointment_kind")),
                "stale": {"kind": stale.get("kind"), "days": stale.get("days")} if isinstance(stale, dict) else None,
                "description": stage.get("description") or "", "active": bool(stage.get("active")),
                # Desfecho oferecido no modal "Encerrar atendimento" e o legado
                # que a mudanca manual grava junto (decisao do PO, 28/10).
                "close_outcome": bool(stage.get("close_outcome")),
                "legacy_qualification": stage.get("legacy_qualification") or None,
                # Lista TODAS as etapas; `visible` = aparece no quadro deste usuario.
                "visibility_permission": stage.get("visibility_permission") or None,
                "visible": self.visible(stage),
                "default_label": default_label, "default_description": default_description,
            })
        reasons = []
        for reason in self.catalog["reasons"]:
            item = {"key": reason["key"], "label": reason["label"],
                    "allows_note": bool(reason.get("allows_note")),
                    "selectable": bool(reason.get("selectable", True)), "active": bool(reason.get("active")),
                    "default_label": reason_defaults[reason["key"]]}
            if reason.get("hint"):
                item["hint"] = reason["hint"]
            reasons.append(item)
        return {"catalog": {"template": self.catalog["template"], "template_label": self.catalog["template_label"],
                            "version": self.catalog.get("version", 0),
                            "overrides_version": self.catalog.get("overrides_version", 0),
                            "legacy_qualification_sync": bool(self.catalog.get("legacy_qualification_sync")),
                            "stages": stages, "reasons": reasons,
                            "kpis": dict(self.catalog.get("kpis") or {})},
                "capabilities": self.capabilities()}

    # -- leituras de apoio (em lote, cache por request) -----------------------

    def _users(self, ids):
        wanted = {str(value) for value in ids if _int_or_none(value) is not None}
        missing = [value for value in wanted if value not in self._users_cache]
        if missing:
            found = self.repo.get_many("users", missing)
            for value in missing:
                self._users_cache[value] = found.get(value)
        return {value: self._users_cache.get(value) for value in wanted}

    def _user_name(self, users, user_id, fallback="Operador"):
        row = users.get(str(user_id)) if user_id is not None else None
        return str((row or {}).get("display_name") or fallback)

    def _channel(self, channel_id):
        key = str(channel_id)
        if key not in self._channels:
            try:
                self._channels[key] = (self.channel_loader(channel_id) or {}) if channel_id is not None else {}
            except Exception:
                # Canal ilegivel = desconhecido: a thread nao vira pool (nega).
                self._channels[key] = {}
        return self._channels[key]

    def lgpd_tracked(self):
        """O CRM registra o aceite LGPD? Falso so com settings.ai.lgpd_by_agent
        True explicito (doc do tenant, 1x por request)."""
        if self._lgpd_tracked is None:
            try:
                doc = self.tenant_loader(self.repo.tenant_id) or {}
                settings = doc.get("settings") if isinstance(doc, dict) else None
                ai = settings.get("ai") if isinstance(settings, dict) else None
                self._lgpd_tracked = not (isinstance(ai, dict) and ai.get("lgpd_by_agent") is True)
            except Exception:
                self._lgpd_tracked = True
        return self._lgpd_tracked

    def _parallel(self, fn, items, workers):
        tenant_id = self.repo.tenant_id

        def run(item):
            # Threads do pool nao herdam o contextvar do request.
            with tenant_context(tenant_id):
                return fn(item)

        items = list(items)
        if len(items) <= 1:
            return [run(item) for item in items]
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
            return list(pool.map(run, items))

    # -- escopo ----------------------------------------------------------------

    def _order(self, order):
        if order not in ("desc", "asc"):
            _fail(422, "filter_invalid", "Ordenação inválida.")
        return order

    def _scope(self, owner_id=None, mine=False):
        if owner_id is not None and not self.privileged:
            _fail(403, "owner_filter_forbidden", "Filtrar por dono exige a visão do tenant.")
        if owner_id is not None and mine:
            _fail(422, "filter_invalid", "Use \"só meus\" ou um dono, não os dois.")
        if mine:
            return ("==", self.uid)
        if owner_id is not None:
            row = self.repo.user(owner_id)
            if (not row or row.get("tenant_id") not in (None, "", self.repo.tenant_id)
                    or not row.get("firebase_uid")):
                _fail(422, "owner_invalid", "Dono inválido.")
            return ("==", str(row["firebase_uid"]))
        if self.privileged:
            return None
        return ("in", [self.uid, ""])

    def _normalized(self, row, users):
        """UID legado derivado do dono (como get_wa_contact), sem backfill:
        contato com dono nunca e lido como pool so por faltar o UID."""
        if row.get("assigned_to_uid") or row.get("assigned_to") in (None, ""):
            return row
        owner = users.get(str(row.get("assigned_to"))) or {}
        return dict(row, assigned_to_uid=str(owner.get("firebase_uid") or ""))

    def _readable(self, row):
        if row.get("is_backup") or row.get("is_archived"):
            return False
        if self.privileged:
            return True
        if self.require_contact_access is None:
            return False
        try:
            with tenant_context(self.repo.tenant_id):
                self.require_contact_access(row, self.user)
            return True
        except HTTPException as exc:
            if exc.status_code in (403, 404):
                return False
            raise

    def _write_scope(self, contact):
        return bool(self.privileged or _same_user(contact.get("assigned_to"), self.user_id)
                    or not contact.get("assigned_to_uid"))

    # -- cursor (HMAC por valores, TTL 1 h) ------------------------------------

    def _cursor_scope(self, *parts):
        return hashlib.sha256(_json([self.repo.tenant_id, self.uid, bool(self.privileged), *parts]).encode()).hexdigest()

    def _encode_cursor(self, at, doc_id, scope):
        payload = {"s": scope, "at": _iso(at), "id": str(doc_id),
                   "exp": (self.now() + CURSOR_TTL).isoformat()}
        data = base64.urlsafe_b64encode(_json(payload).encode()).decode().rstrip("=")
        return data + "." + hmac.new(str(SECRET_KEY).encode(), data.encode(), hashlib.sha256).hexdigest()

    def _decode_cursor(self, value, scope):
        try:
            if not isinstance(value, str) or len(value) > 1600 or value.count(".") != 1:
                raise ValueError()
            data, sig = value.split(".")
            expected = hmac.new(str(SECRET_KEY).encode(), data.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise ValueError()
            payload = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
            expires = fc.as_utc(payload["exp"])
            at = fc.as_utc(payload["at"])
            doc_id = payload["id"]
            if (payload["s"] != scope or expires is None or expires <= self.now() or at is None
                    or not isinstance(doc_id, str) or not doc_id or len(doc_id) > 160):
                raise ValueError()
            return at, doc_id
        except (ValueError, KeyError, TypeError, UnicodeError, AttributeError):
            _fail(400, "cursor_invalid", "Cursor inválido ou expirado. Recarregue a lista.")

    # -- montagem de cards -------------------------------------------------------

    def _pointed_valid(self, contact, activity):
        return bool(activity and str(activity.get("contact_id")) == str(contact.get("id"))
                    and activity.get("tenant_id") in (None, "", self.repo.tenant_id)
                    and activity.get("to_stage") == contact.get(fc.F_STAGE)
                    and str(activity.get("event_type") or "").startswith(fc.STAGE_EVENT_PREFIX))

    def _pointed_reason(self, contact, activity):
        stage = fc.stage_def(self.catalog, contact.get(fc.F_STAGE))
        if not stage or not stage.get("requires_reason") or not self._pointed_valid(contact, activity):
            return None
        reason = activity.get("stage_reason")
        return reason if isinstance(reason, str) and reason else None

    def _reason_view(self, key):
        return {"key": key, "label": fc.reason_label(self.catalog, key)} if key else None

    def _owner(self, contact, users):
        owner_id = _int_or_none(contact.get("assigned_to"))
        if owner_id is None:
            return None
        name = contact.get("assigned_name") or self._user_name(users, owner_id)
        return {"user_id": owner_id, "name": str(name or "Operador")}

    def _badges(self, contact):
        outcome = contact.get("bot_outcome")
        return {
            "with_bot": bool(not contact.get("bot_completed") and not contact.get("assigned_to_uid")
                             and contact.get("assigned_to") in (None, "")),
            "lgpd_pending": bool(self.lgpd_tracked() and contact.get("lgpd_consent") is not True),
            "commercial_blocked": bool(self.commercial_blocked(contact)),
            "bot_outcome": outcome if outcome in BOT_OUTCOMES else None,
        }

    def _task_view(self, task, users, now):
        due = fc.as_utc(task.get("due_at"))
        assignee = _int_or_none(task.get("assignee_user_id"))
        return {"id": task.get("id"), "title": str(task.get("title") or ""), "due_at": _iso(due),
                "overdue": bool(due and due < now), "queue_key": task.get("queue_key"),
                "assignee_name": self._user_name(users, assignee) if assignee is not None else None}

    def _load_conversations(self, rows):
        """Threads das tarefas em lote (1 get_all por rodada, cache por request)."""
        if self.privileged:
            return
        wanted = {str(row["conversation_id"]) for row in rows if row.get("conversation_id")}
        missing = sorted(wanted - set(self._conversations))
        if missing:
            found = self.repo.get_many("wa_conversations", missing)
            for conversation_id in missing:
                self._conversations[conversation_id] = found.get(conversation_id)

    def _visible_tasks(self, rows, by_id):
        """Linhas pendentes do tenant que o leitor pode ver. Operador: tarefa
        de thread so conta se a thread for visivel para ele (coex de colega
        fica oculta)."""
        visible_rows = []
        for task in rows:
            contact = by_id.get(str(task.get("contact_id")))
            if (contact is None or task.get("status") != "pending"
                    or task.get("tenant_id") not in (None, "", self.repo.tenant_id)):
                continue
            conversation_id = task.get("conversation_id")
            if conversation_id and not self.privileged:
                conversation = self._conversations.get(str(conversation_id))
                if not conversation or str(conversation.get("contact_id")) != str(contact["id"]):
                    continue
                visible, _ = followup_access.conversation_visible(
                    contact, conversation, None, self.user, self.repo.tenant_id, privileged=False)
                if not visible:
                    visible, _ = followup_access.conversation_visible(
                        contact, conversation, self._channel(conversation.get("channel_id")),
                        self.user, self.repo.tenant_id, privileged=False)
                if not visible:
                    continue
            visible_rows.append(task)
        return visible_rows

    def _accessible_tasks(self, contacts, want=1):
        """Pendentes ACESSIVEIS por contato, em lote (<=30 contatos por
        consulta, sem N+1), e o conjunto de contatos com resultado INCERTO.

        A consulta ordena por due_at com limite TASK_LIMIT. Lote cheio pode
        ter cortado a proxima tarefa de quem ficou sem `want` tarefas
        acessiveis (inclusive por tarefas de thread oculta, que consomem o
        limite): so esses contatos sao reconsultados, a partir da ultima linha
        vista (as anteriores deles ja vieram), ate TASK_ROUNDS rodadas. Quem
        ainda faltar fica incerto: o card sai sem selo de tarefa, nunca com
        'sem proxima acao' falso. Quem aparece no resultado tem a 1a tarefa
        acessivel certa (o resultado e um prefixo da ordem global)."""
        if not self.tasks_visible or not contacts:
            return {}, set()
        by_id = {str(contact["id"]): contact for contact in contacts}
        found = {}
        uncertain = set()
        batches = [(chunk, None) for chunk in _chunks([contact["id"] for contact in contacts], TASK_BATCH)]
        for _ in range(TASK_ROUNDS):
            results = [(ids, self.repo.pending_tasks(ids, limit=TASK_LIMIT, after=after)) for ids, after in batches]
            self._load_conversations([row for _, rows in results for row in rows])
            batches = []
            for ids, rows in results:
                for task in self._visible_tasks(rows, by_id):
                    found.setdefault(str(task.get("contact_id")), []).append(task)
                if len(rows) < TASK_LIMIT:
                    continue
                remaining = [cid for cid in ids if len(found.get(str(cid), ())) < want]
                if not remaining:
                    continue
                last_id = str(rows[-1].get("id") or "")
                if last_id:
                    batches.append((remaining, (rows[-1].get("due_at"), last_id)))
                else:
                    # Sem id para o cursor nao da para continuar com certeza.
                    uncertain.update(str(cid) for cid in remaining)
            if not batches:
                break
        # Rodadas esgotadas: quem ainda seria reconsultado fica incerto.
        uncertain.update(str(cid) for ids, _ in batches for cid in ids)
        for items in found.values():
            items.sort(key=lambda row: (fc.as_utc(row.get("due_at")) or _FAR_FUTURE, str(row.get("id") or "")))
        return found, uncertain

    def _cards(self, rows, users, now):
        """Cards (whitelist explicita) para linhas ja autorizadas."""
        if not rows:
            return {}
        pointers = [row.get(fc.F_ACTIVITY) for row in rows
                    if (fc.stage_def(self.catalog, row.get(fc.F_STAGE)) or {}).get("requires_reason")]
        activities = self.repo.get_many("crm_activities", pointers) if pointers else {}
        tasks_visible = self.tasks_visible
        tasks, uncertain = self._accessible_tasks(rows) if tasks_visible else ({}, set())
        assignees = [task.get("assignee_user_id") for items in tasks.values() for task in items[:1]]
        users = dict(users, **self._users(assignees)) if assignees else users
        cards = {}
        for row in rows:
            key = str(row["id"])
            # Lote cortado sem certeza da proxima tarefa: o card sai como sem
            # tarefas visiveis (nada de "nenhuma pendente" nem "sem proxima acao").
            known = tasks_visible and key not in uncertain
            first = (tasks.get(key) or [None])[0] if known else None
            next_task = self._task_view(first, users, now) if first else None
            reason_key = self._pointed_reason(row, activities.get(str(row.get(fc.F_ACTIVITY) or "")))
            cards[key] = {
                "contact_id": row["id"],
                "display_name": display_name(row),
                "lead_temperature": row.get("lead_temperature") or None,
                "lead_temperature_at": _iso(row.get("lead_temperature_at")),
                "stage": row.get(fc.F_STAGE),
                "stage_version": stage_version(row),
                "stage_changed_at": _iso(row.get(fc.F_CHANGED_AT)),
                "stage_source": row.get(fc.F_SOURCE),
                "owner": self._owner(row, users),
                "last_inbound_at": _iso(row.get("last_inbound_at")),
                "last_activity_at": _iso(row.get("last_message_at")),
                "signals": fc.derived_signals(self.catalog, row, now, next_task=next_task,
                                              tasks_known=known),
                "badges": self._badges(row),
                "reason": self._reason_view(reason_key),
                "next_task": next_task,
                "tasks_visible": known,
            }
        return cards

    def _page(self, stage, scope, order, after, limit, cursor_scope):
        rows = self.repo.stage_page(stage, scope, order == "desc", after, limit + 1)
        examined = rows[:limit]
        next_cursor = None
        if len(rows) > limit and examined:
            last = examined[-1]
            next_cursor = self._encode_cursor(last.get(fc.F_CHANGED_AT), last["id"], cursor_scope)
        return examined, next_cursor

    def _visible_rows(self, rows, users):
        return [normalized for normalized in (self._normalized(row, users) for row in rows)
                if self._readable(normalized)]

    # -- quadro -----------------------------------------------------------------

    def board(self, order="desc", owner_id=None, mine=False):
        self._actor()
        self._rate()
        order = self._order(order)
        mine = bool(mine)
        scope = self._scope(owner_id, mine)
        now = self.now()

        def column(stage):
            count = self.repo.count_stage(stage["key"], scope)
            if not stage.get("active") and not count:
                return stage, count, None, [], None
            cut = fc.stale_cutoff(stage, now)
            stale = self.repo.count_stage(stage["key"], scope, stale=cut) if cut else None
            fp = self._cursor_scope("cards", stage["key"], order, owner_id, mine)
            rows, next_cursor = self._page(stage["key"], scope, order, None, CARD_LIMIT, fp)
            return stage, count, stale, rows, next_cursor

        # Etapa invisivel a este usuario (ex.: Novo contato sem
        # ver_contatos_agente_funil) nem e consultada: sem total, parados ou cards.
        stages = [stage for stage in self.catalog["stages"] if self.visible(stage)]
        results = self._parallel(column, stages, COLUMN_WORKERS)
        users = self._users(row.get("assigned_to") for _, _, _, rows, _ in results for row in rows)
        visible = {stage["key"]: self._visible_rows(rows, users) for stage, _, _, rows, _ in results}
        cards = self._cards([row for rows in visible.values() for row in rows], users, now)
        columns = []
        for stage, count, stale, _, next_cursor in results:
            if not stage.get("active") and not count:
                continue
            columns.append({"stage": stage["key"], "label": stage["label"], "kind": stage["kind"],
                            "active": bool(stage.get("active")), "count": count, "stale_count": stale,
                            "cards": [cards[str(row["id"])] for row in visible[stage["key"]]],
                            "next_cursor": next_cursor})
        return {"generated_at": now.isoformat(),
                "scope": {"privileged": bool(self.privileged), "owner_id": owner_id, "mine": mine, "order": order},
                "columns": columns}

    def stage_cards(self, stage_key, cursor=None, order="desc", owner_id=None, mine=False, limit=CARD_LIMIT):
        self._actor()
        self._rate()
        stage = fc.stage_def(self.catalog, stage_key) if isinstance(stage_key, str) else None
        # Etapa fora do quadro deste usuario responde como inexistente.
        if not stage or not self.visible(stage):
            _fail(404, "unknown_stage", "Etapa inexistente no funil deste tenant.")
        order = self._order(order)
        mine = bool(mine)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= PAGE_MAX:
            _fail(422, "filter_invalid", "Limite inválido.")
        scope = self._scope(owner_id, mine)
        now = self.now()
        fp = self._cursor_scope("cards", stage["key"], order, owner_id, mine)
        after = self._decode_cursor(cursor, fp) if cursor else None
        with tenant_context(self.repo.tenant_id):
            rows, next_cursor = self._page(stage["key"], scope, order, after, limit, fp)
        users = self._users(row.get("assigned_to") for row in rows)
        visible = self._visible_rows(rows, users)
        cards = self._cards(visible, users, now)
        return {"stage": stage["key"], "cards": [cards[str(row["id"])] for row in visible],
                "next_cursor": next_cursor}

    # -- contato (drawer, historico, contexto) ---------------------------------

    def _read_contact(self, contact_id, conversation_id=None):
        try:
            context = self.authorize(contact_id, conversation_id, self.user)
        except HTTPException as exc:
            if exc.status_code in (403, 404):
                _fail(404, "out_of_scope", "Contato fora do seu acesso.")
            if exc.status_code == 422:
                _fail(422, "invalid_conversation", "Conversa inválida.")
            raise
        contact = (context or {}).get("contact")
        if not isinstance(contact, dict) or str(contact.get("id")) != str(contact_id):
            _fail(404, "out_of_scope", "Contato fora do seu acesso.")
        if conversation_id and str(((context or {}).get("conversation") or {}).get("contact_id")) != str(contact_id):
            _fail(404, "out_of_scope", "Contato fora do seu acesso.")
        # Backup e arquivado nao aparecem para quem nao tem a visao do tenant.
        if not self.privileged and (contact.get("is_backup") or contact.get("is_archived")):
            _fail(404, "out_of_scope", "Contato fora do seu acesso.")
        return context

    def _pointed(self, contact):
        pointer = contact.get(fc.F_ACTIVITY)
        if not isinstance(pointer, str) or not pointer:
            return None
        return self.repo.get("crm_activities", pointer)

    def _stage_activity(self, contact):
        """Activity apontada so quando a etapa a usa (motivo ou tipo de
        compromisso): nas demais, _stage_view sai igual sem ela."""
        stage = fc.stage_def(self.catalog, contact.get(fc.F_STAGE))
        if not stage or not (stage.get("requires_reason") or stage.get("appointment_kind")):
            return None
        return self._pointed(contact)

    def _can_move(self, contact, write_scope):
        unavailable = bool(contact.get("is_backup") or contact.get("is_archived"))
        return bool(self.can("mover_etapa_funil") and write_scope and not unavailable)

    def _stage_view(self, contact, activity, show_note):
        key = contact.get(fc.F_STAGE)
        if not key:
            return None
        stage = fc.stage_def(self.catalog, key)
        valid = self._pointed_valid(contact, activity)
        data = (activity.get("data") if valid and isinstance(activity.get("data"), dict) else None) or {}
        reason = self._pointed_reason(contact, activity)
        note = data.get("reason_note") if reason and isinstance(data.get("reason_note"), str) else None
        author = valid and str(activity.get("actor_uid") or "") == self.uid
        kind = data.get("appointment_kind")
        return {"key": key, "label": fc.stage_label(self.catalog, key), "kind": (stage or {}).get("kind"),
                "version": stage_version(contact), "changed_at": _iso(contact.get(fc.F_CHANGED_AT)),
                "source": contact.get(fc.F_SOURCE), "entered_at": _iso(contact.get(fc.F_ENTERED_AT)),
                "reason": self._reason_view(reason),
                "reason_note": note if show_note and (self.privileged or author) else None,
                "appointment_kind": kind if kind in fc.APPOINTMENT_KINDS else None}

    def _actor_view(self, row, users):
        actor_type = row.get("actor_type") or "user"
        user_id = _int_or_none(row.get("actor_user_id"))
        if actor_type == "user":
            name = self._user_name(users, user_id)
        elif actor_type == "migration":
            name = "Classificação inicial"
        else:
            name = "Sistema"
        return {"type": actor_type, "user_id": user_id, "name": name}

    def _history_item(self, row, users, show_note):
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        from_stage = row.get("from_stage") or None
        to_stage = row.get("to_stage") or None
        author = str(row.get("actor_uid") or "") == self.uid
        note = data.get("reason_note") if isinstance(data.get("reason_note"), str) else None
        kind = data.get("appointment_kind")
        return {"id": row.get("id"), "event_type": row.get("event_type"), "occurred_at": _iso(row.get("occurred_at")),
                "actor": self._actor_view(row, users),
                "from_stage": from_stage, "from_label": fc.stage_label(self.catalog, from_stage) if from_stage else None,
                "to_stage": to_stage, "to_label": fc.stage_label(self.catalog, to_stage) if to_stage else None,
                "reason": self._reason_view(row.get("stage_reason")),
                "from_reason": self._reason_view(row.get("from_reason")),
                "reason_note": note if show_note and (self.privileged or author) else None,
                "appointment_kind": kind if kind in fc.APPOINTMENT_KINDS else None,
                "entry_kind": row.get("entry_kind"), "rule_id": data.get("rule_id"),
                # "close" = desfecho escolhido no "Encerrar atendimento".
                "via": data.get("via") if data.get("via") == "close" else None,
                "synthetic": False}

    def _history(self, contact, cursor=None):
        # Acesso so por thread propria (coex) = etapa atual, sem historico/nota.
        if not self._write_scope(contact):
            if cursor:
                _fail(400, "cursor_invalid", "Cursor inválido ou expirado. Recarregue a lista.")
            return {"items": [], "next_cursor": None}
        contact_id = contact["id"]
        fp = self._cursor_scope("history", str(contact_id))
        after = self._decode_cursor(cursor, fp) if cursor else None
        rows = [row for row in self.repo.history_page(int(contact_id), after, HISTORY_PAGE + 1)
                if str(row.get("event_type") or "") in fc.STAGE_EVENTS]
        page = rows[:HISTORY_PAGE]
        next_cursor = None
        if len(rows) > HISTORY_PAGE and page:
            next_cursor = self._encode_cursor(page[-1].get("occurred_at"), page[-1]["id"], fp)
        users = self._users(row.get("actor_user_id") for row in page)
        items = [self._history_item(row, users, True) for row in page]
        entered = fc.as_utc(contact.get(fc.F_ENTERED_AT))
        if next_cursor is None and entered:
            oldest = page[-1] if page else None
            if oldest is None:
                # Sem Activity nenhuma: a entrada foi automatica (intake/graduacao).
                synthetic_to = contact.get(fc.F_STAGE) if not cursor else None
            elif oldest.get("from_stage"):
                # A 1a Activity ja saiu de uma etapa: a entrada nao teve evento.
                synthetic_to = oldest.get("from_stage")
            else:
                synthetic_to = None
            if synthetic_to:
                items.append({"id": "entered_%s" % contact_id, "event_type": "crm_funnel_entered",
                              "occurred_at": entered.isoformat(),
                              "actor": {"type": "system", "user_id": None, "name": "Entrada no funil"},
                              "from_stage": None, "from_label": None, "to_stage": synthetic_to,
                              "to_label": fc.stage_label(self.catalog, synthetic_to), "reason": None,
                              "from_reason": None, "reason_note": None, "appointment_kind": None,
                              "entry_kind": None, "rule_id": None, "via": None, "synthetic": True})
        return {"items": items, "next_cursor": next_cursor}

    def contact_drawer(self, contact_id):
        self._actor()
        contact = self._read_contact(contact_id)["contact"]
        now = self.now()
        write_scope = self._write_scope(contact)
        activity = self._stage_activity(contact)
        tasks_visible = self.tasks_visible
        tasks_known = False
        tasks = None
        next_task = None
        if tasks_visible:
            key = str(contact["id"])
            found, uncertain = self._accessible_tasks([contact], want=DRAWER_TASKS)
            pending = (found.get(key) or [])[:DRAWER_TASKS]
            # Sem nenhuma acessivel e com o lote cortado: incerto (tasks=null,
            # sem selo de tarefa). Com alguma, a 1a e certa.
            if pending or key not in uncertain:
                users = self._users(task.get("assignee_user_id") for task in pending)
                tasks = [self._task_view(task, users, now) for task in pending]
                next_task = tasks[0] if tasks else None
                tasks_known = True
        suggestions = []
        booked = (self.catalog.get("kpis") or {}).get("booked_stage")
        target = fc.stage_def(self.catalog, booked) if booked else None
        if (contact.get("bot_outcome") in SUGGEST_OUTCOMES and target and target.get("active")
                and target.get("manual_target") and contact.get(fc.F_STAGE) != booked):
            suggestions.append({"to_stage": booked, "source": "bot_outcome", "label": target["label"]})
        return {
            "contact": {"id": contact["id"],
                        "display_name": display_name(contact),
                        "lead_temperature": contact.get("lead_temperature") or None,
                        "lead_temperature_at": _iso(contact.get("lead_temperature_at")),
                        "owner": self._owner(contact, {}),
                        "bot_completed": bool(contact.get("bot_completed")),
                        "is_archived": bool(contact.get("is_archived"))},
            "stage": self._stage_view(contact, activity, write_scope),
            "badges": self._badges(contact),
            "signals": fc.derived_signals(self.catalog, contact, now, next_task=next_task, tasks_known=tasks_known),
            "history": self._history(contact),
            "tasks": tasks,
            "suggestions": suggestions,
            "capabilities": {"can_move": self._can_move(contact, write_scope),
                             "write_scope": write_scope},
        }

    def contact_stage(self, contact_id):
        """Revalidacao leve do drawer (a cada 30 s com a aba visivel): mesma
        autorizacao do drawer (404 out_of_scope se perdeu o acesso), sem
        historico nem tarefas. Le o contato e, so quando a etapa usa motivo ou
        tipo de compromisso, a Activity apontada. `stage` sai no mesmo shape
        do drawer: o front so recarrega o drawer quando versao/etapa mudam."""
        self._actor()
        contact = self._read_contact(contact_id)["contact"]
        write_scope = self._write_scope(contact)
        return {"stage": self._stage_view(contact, self._stage_activity(contact), write_scope),
                "version": stage_version(contact),
                "can_move": self._can_move(contact, write_scope),
                "write_scope": write_scope}

    def contact_history(self, contact_id, cursor=None):
        self._actor()
        contact = self._read_contact(contact_id)["contact"]
        return self._history(contact, cursor)

    def contact_context(self, contact_id, conversation_id=None):
        """Mesmo contrato do contexto do follow-up (ReadOnlyContext), com o
        contato em whitelist. Nao assume, nao abre e nao marca como lida."""
        self._actor()
        source = self._read_contact(contact_id, conversation_id)
        contact = source["contact"]
        if conversation_id:
            rows = [source["conversation"]]
        else:
            rows = followup_access.list_authorized_conversations(
                self.repo.tenant_id, self.authorize, contact_id, self.user, limit=30)
        return {"contact": {"id": contact.get("id"), "display_name": display_name(contact),
                            "lead_temperature": contact.get("lead_temperature"),
                            "bot_completed": contact.get("bot_completed"),
                            "is_archived": contact.get("is_archived")},
                "conversations": rows}

    def contact_messages(self, contact_id, conversation_id, limit=30):
        self._actor()
        if not conversation_id:
            _fail(422, "invalid_conversation", "Informe a conversa.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= PAGE_MAX:
            _fail(422, "filter_invalid", "Limite inválido.")
        self._read_contact(contact_id)
        try:
            rows = followup_access.load_authorized_messages(
                self.authorize, contact_id, conversation_id, self.user, limit)
        except HTTPException as exc:
            if exc.status_code in (403, 404):
                _fail(404, "out_of_scope", "Conversa fora do seu acesso.")
            if exc.status_code == 422:
                _fail(422, "invalid_conversation", "Conversa inválida.")
            raise
        return {"messages": rows}

    # -- mudanca de etapa ----------------------------------------------------------

    def _current_detail(self, contact):
        contact = contact or {}
        by_user = _int_or_none(contact.get(fc.F_BY_USER))
        name = None
        if by_user is not None:
            name = self._user_name(self._users([by_user]), by_user)
        return {"stage": contact.get(fc.F_STAGE), "version": stage_version(contact),
                "changed_at": _iso(contact.get(fc.F_CHANGED_AT)),
                "changed_by_user_id": by_user, "changed_by_name": name}

    def _stale(self, contact):
        _fail(409, "stale_version", "A etapa deste contato mudou. Confira antes de reaplicar.",
              current=self._current_detail(contact))

    def _stage_response(self, contact_id, contact, replayed, activity_id, activity=None):
        contact = dict(contact or {}, id=int(contact_id))
        if activity is None or activity.get("id") != contact.get(fc.F_ACTIVITY):
            activity = self._pointed(contact)
        return {"contact_id": int(contact_id), "stage": self._stage_view(contact, activity, True),
                "replayed": bool(replayed), "activity_id": activity_id}

    def _parse_change(self, contact_id, payload):
        """(contact_id, fingerprint, recibo) do corpo canonico ou 422."""
        contact_id = _int_or_none(contact_id)
        if contact_id is None or contact_id < 1 or not isinstance(payload, dict):
            _fail(422, "invalid_payload", "Dados inválidos.")
        operation_id = payload.get("operation_id")
        to_stage = payload.get("to_stage")
        expected_version = payload.get("expected_version")
        if (not isinstance(operation_id, str) or not isinstance(to_stage, str)
                or isinstance(expected_version, bool) or not isinstance(expected_version, int)):
            _fail(422, "invalid_payload", "Dados inválidos.")
        fingerprint = hashlib.sha256(_json({"contact_id": contact_id, "payload": payload}).encode("utf-8")).hexdigest()
        return contact_id, fingerprint, self.repo.receipt_id(self.uid, contact_id, operation_id)

    def _prior_receipt(self, contact_id, operation_id, fingerprint, receipt_id):
        """Recibo desta mesma operacao (replay) ou None. operation_id ja
        usado com outro corpo ou em outro contato -> 409 operation_reused."""
        receipt = self.repo.get("crm_activities", receipt_id)
        if receipt:
            if receipt.get("request_fingerprint") != fingerprint or str(receipt.get("contact_id")) != str(contact_id):
                _fail(409, "operation_reused", "Este operation_id já foi usado em outra operação.")
            return receipt
        # O id do recibo inclui o contato: o mesmo operation_id em OUTRO
        # contato e detectado pelos eventos ja gravados desta identidade.
        for row in self.repo.operation_rows(self.uid, operation_id):
            if (str(row.get("event_type") or "").startswith(fc.STAGE_EVENT_PREFIX)
                    and str(row.get("contact_id")) != str(contact_id)):
                _fail(409, "operation_reused", "Este operation_id já foi usado em outra operação.")
        return None

    def _guards(self, contact, actor):
        return ({key: contact.get(key) for key in CONTACT_GUARD_FIELDS},
                (self.user_id, {key: actor.get(key) for key in USER_GUARD_FIELDS}))

    def _legacy_fields(self, contact, target):
        """Desfecho legado a gravar junto com a mudanca MANUAL (decisao do
        PO de 28/10, "uma classificacao so"): so quando o template sincroniza
        (target nao vazio) e o atual difere; 'convertido' carimba quem
        converteu, como o /qualify e o fechamento legado."""
        if not target or target == str(contact.get("qualification") or "novo"):
            return {}
        fields = {"qualification": target}
        if target == "convertido":
            fields["converted_by_user_id"] = self.user_id
        return fields

    def _audit_legacy(self, contact_id, qualification, via):
        if qualification:
            where = "no encerramento, via funil" if via == "close" else "via funil"
            self._audit("CONTACT_QUALIFY", "Contato %s: %s (%s)" % (contact_id, qualification, where))

    def _transaction(self, run):
        """Executa uma escrita do repositorio traduzindo conflitos em HTTP."""
        try:
            return run()
        except StageConflict as exc:
            if exc.code == "stale_version":
                self._stale(exc.contact)
            if exc.code == "operation_reused":
                _fail(409, "operation_reused", "Este operation_id já foi usado em outra operação.")
            if exc.code == "not_found":
                _fail(404, "out_of_scope", "Contato fora do seu acesso.")
            _fail(409, "context_changed", "O acesso ou o contato mudou. Atualize a tela.")
        except (google_exceptions.Aborted, google_exceptions.Conflict):
            _fail(409, "try_again", "Muitas alterações ao mesmo tempo. Tente de novo.")
        except ValueError as exc:
            if isinstance(exc.__cause__, google_exceptions.Aborted):
                _fail(409, "try_again", "Muitas alterações ao mesmo tempo. Tente de novo.")
            raise

    def _decide(self, contact, payload):
        """(decisao do catalogo, estado lido): valida contra a etapa e o
        motivo ATUAIS (Activity apontada). Levanta fc.FunnelRuleError."""
        pointed = self._pointed(contact)
        pre = {"stage": contact.get(fc.F_STAGE) or None, "pointer": contact.get(fc.F_ACTIVITY) or None,
               "reason": self._pointed_reason(contact, pointed)}
        decision = fc.validate_change(
            self.catalog, current_stage=pre["stage"], current_reason=pre["reason"],
            to_stage=payload.get("to_stage"), reason=payload.get("reason"), note=payload.get("reason_note"),
            appointment_kind=payload.get("appointment_kind"))
        return decision, pre

    def _commit_change(self, contact_id, contact, payload, fingerprint, receipt_id, actor, decision, pre,
                       via=None, recheck=None):
        """Grava a mudanca (etapa + legado equivalente + Activity) na
        transacao do repositorio e audita o legado depois do commit.
        `recheck(current)` = condicao extra revalidada sobre o doc lido NA
        transacao (levanta StageConflict); usada pelo encerramento."""
        now = self.now()
        event_type = decision["event_type"]
        to_stage = payload["to_stage"]
        operation_id = payload["operation_id"]
        legacy_target = decision.get("legacy_qualification")

        def build(current, current_pointed):
            current = dict(current, id=contact_id)
            # Mesma versao com etapa/ponteiro diferentes (ex.: undo da migracao
            # seguido de nova entrada) tambem e conflito: nada de ABA.
            if ((current.get(fc.F_STAGE) or None) != pre["stage"]
                    or (current.get(fc.F_ACTIVITY) or None) != pre["pointer"]
                    or self._pointed_reason(current, current_pointed) != pre["reason"]):
                raise StageConflict("stale_version", current)
            if recheck is not None:
                recheck(current)
            new_version = stage_version(current) + 1
            fields = {fc.F_VERSION: new_version, fc.F_SOURCE: fc.SOURCE_USER, fc.F_ACTIVITY: receipt_id,
                      fc.F_BY_USER: self.user_id, fc.F_BY_UID: self.uid}
            if event_type == fc.EVENT_CHANGED:
                fields[fc.F_STAGE] = to_stage
                fields[fc.F_CHANGED_AT] = now
                fields[fc.F_MAX_ORDER] = fc.next_max_order(self.catalog, current.get(fc.F_MAX_ORDER), to_stage)
            if not current.get(fc.F_ENTERED_AT):
                # Contato sem etapa movido a mao: quem ja conversava conta da
                # 1a vez que apareceu; contato novo, de agora. Write-once.
                entered = (fc.as_utc(current.get("first_seen_at")) if current.get("last_inbound_at") else None) or now
                fields[fc.F_ENTERED_AT] = entered
                fields[fc.F_COHORT] = fc.cohort_month(entered)
            # Desfecho legado no MESMO merge (decidido sobre o doc lido na
            # transacao: retry com o legado ja igual nao regrava).
            legacy = self._legacy_fields(current, legacy_target)
            fields.update(legacy)
            data = {"reason_note": decision["note"], "appointment_kind": decision["appointment_kind"],
                    "stage_version": new_version, "source": fc.SOURCE_USER,
                    "suggested_by": payload.get("suggested_by"),
                    "legacy_qualification": legacy.get("qualification")}
            if via:
                data["via"] = via
            activity = {
                "id": receipt_id, "tenant_id": self.repo.tenant_id, "contact_id": contact_id,
                "task_id": None, "conversation_id": None, "event_type": event_type,
                "actor_type": "user", "actor_user_id": self.user_id, "actor_uid": self.uid,
                "occurred_at": now, "recorded_at": now, "operation_id": operation_id,
                "from_stage": pre["stage"], "to_stage": to_stage,
                "stage_reason": decision["reason"], "from_reason": pre["reason"],
                "data": data,
                "request_fingerprint": fingerprint, "result_version": new_version,
            }
            if event_type == fc.EVENT_CHANGED:
                activity["entry_kind"] = fc.entry_kind(self.catalog, pre["stage"], to_stage)
            else:
                corrects_id, corrects_month = None, None
                if self._pointed_valid(current, current_pointed):
                    if current_pointed.get("event_type") == fc.EVENT_REASON_CHANGED:
                        corrects_id = current_pointed.get("corrects_entry_id")
                        corrects_month = current_pointed.get("corrects_month")
                    else:
                        corrects_id = current_pointed.get("id")
                        corrects_month = fc.cohort_month(current_pointed.get("occurred_at"))
                activity["corrects_entry_id"] = corrects_id
                activity["corrects_month"] = corrects_month
            return fields, activity

        contact_guard, user_guard = self._guards(contact, actor)
        result = self._transaction(lambda: self.repo.commit_stage(
            contact_id, receipt_id, fingerprint, payload["expected_version"], contact_guard, user_guard, build))
        if not result["replayed"]:
            data = (result.get("activity") or {}).get("data") or {}
            self._audit_legacy(contact_id, data.get("legacy_qualification"), via)
        return result

    def change_stage(self, contact_id, payload):
        """payload = corpo ja validado (dict canonico do modelo da rota)."""
        actor = self._actor()
        if not self.can("mover_etapa_funil"):
            _fail(403, "permission_denied", "Você não tem permissão para mover etapas do funil.")
        contact_id, fingerprint, receipt_id = self._parse_change(contact_id, payload)
        # Replay idempotente antes de validar: o contato ja esta na etapa nova.
        if self._prior_receipt(contact_id, payload["operation_id"], fingerprint, receipt_id):
            contact = self._read_contact(contact_id)["contact"]
            if not self._write_scope(contact):
                _fail(403, "out_of_scope_write", "Você pode ver, mas não mover, este contato.")
            return self._stage_response(contact_id, self.repo.get("wa_contacts", contact_id), True, receipt_id)

        contact = self._read_contact(contact_id)["contact"]
        if not self._write_scope(contact):
            _fail(403, "out_of_scope_write", "Você pode ver, mas não mover, este contato.")
        if contact.get("is_backup") or contact.get("is_archived"):
            _fail(409, "contact_unavailable", "Contato de backup ou arquivado não muda de etapa.")
        if stage_version(contact) != payload["expected_version"]:
            self._stale(contact)
        try:
            decision, pre = self._decide(contact, payload)
        except fc.FunnelRuleError as exc:
            # Mensagem do catalogo: nunca ecoa o texto enviado.
            _fail(422, exc.code, exc.message)
        result = self._commit_change(contact_id, contact, payload, fingerprint, receipt_id, actor, decision, pre)
        return self._stage_response(contact_id, result["contact"], result["replayed"], receipt_id,
                                    result.get("activity"))

    # -- desfecho do "Encerrar atendimento" (decisao do PO, 28/10) ---------------

    def _close_result(self, contact_id, contact, replayed, activity_id, activity=None):
        result = self._stage_response(contact_id, contact, replayed, activity_id, activity)
        result["qualification"] = str((contact or {}).get("qualification") or "novo")
        return result

    def close_stage(self, contact_id, contact, payload):
        """Desfecho do modal "Encerrar atendimento" como ETAPA, pelo mesmo
        caminho da mudanca manual (versao, recibo, Activity com
        data.via='close', legado equivalente). `contact` = doc ja lido e
        autorizado pelo endpoint de fechar (o escopo e o dele: dono, pool ou
        gestao da thread; o toggle de fechar ja foi checado la).

        Gate (close_gate): o contato ainda nao tem desfecho (etapa que nao e
        desfecho de encerramento ou legado novo/em_atendimento): o
        fechamento exige o desfecho e o toggle de FECHAR cobre a mudanca.
        Fora do gate, trocar um desfecho registrado por outro (ou corrigir o
        motivo) exige mover_etapa_funil. O gate e recalculado sobre o doc
        lido NA transacao: o legado muda sem versao da etapa (/qualify), e
        quem nao pode mover nao passa por um gate que deixou de valer.
        Desfecho igual a etapa atual (sem pedir motivo novo): sem Activity,
        so sincroniza o legado se divergente (mesma versao/etapa na
        transacao). Reenvio do mesmo operation_id = replay (o fechamento
        segue)."""
        actor = self._actor()
        contact_id, fingerprint, receipt_id = self._parse_change(contact_id, payload)
        contact = dict(contact or {}, id=contact_id)
        if self._prior_receipt(contact_id, payload["operation_id"], fingerprint, receipt_id):
            # Ja aplicado (e autorizado) na 1a tentativa; o gate de agora nao vale.
            current = self.repo.get("wa_contacts", contact_id) or contact
            return self._close_result(contact_id, current, True, receipt_id)
        if contact.get("is_backup") or contact.get("is_archived"):
            _fail(409, "contact_unavailable", "Contato de backup ou arquivado não muda de etapa.")
        if stage_version(contact) != payload["expected_version"]:
            self._stale(contact)
        target = fc.stage_def(self.catalog, payload["to_stage"]) or {}
        if (payload["to_stage"] == (contact.get(fc.F_STAGE) or None) and target.get("requires_reason")
                and payload.get("reason") in (None, "")):
            # Manter a etapa atual sem informar motivo (o modal nao pede): o
            # motivo vigente fica e so o legado e sincronizado.
            return self._close_sync(contact_id, contact, actor)
        try:
            decision, pre = self._decide(contact, payload)
        except fc.FunnelRuleError as exc:
            if exc.code != "same_stage":
                _fail(422, exc.code, exc.message)
            return self._close_sync(contact_id, contact, actor)
        can_move = self.can("mover_etapa_funil")
        if not can_move and not close_gate(self.catalog, contact):
            _fail(403, "permission_denied",
                  "Trocar um desfecho já registrado exige a permissão de mover etapas do funil.")

        def recheck(current):
            if not can_move and not close_gate(self.catalog, current):
                raise StageConflict("context_changed", current)

        result = self._commit_change(contact_id, contact, payload, fingerprint, receipt_id, actor,
                                     decision, pre, via="close", recheck=recheck)
        return self._close_result(contact_id, result["contact"], result["replayed"], receipt_id,
                                  result.get("activity"))

    def _close_sync(self, contact_id, contact, actor):
        """Desfecho = etapa atual: grava so o legado equivalente, se divergir."""
        stage = contact.get(fc.F_STAGE) or None
        target = fc.legacy_qualification_for(self.catalog, stage)
        if not self._legacy_fields(contact, target):
            return self._close_result(contact_id, contact, False, None)
        contact_guard, user_guard = self._guards(contact, actor)
        result = self._transaction(lambda: self.repo.commit_legacy(
            contact_id, stage_version(contact), stage, contact_guard, user_guard,
            lambda current: self._legacy_fields(current, target)))
        self._audit_legacy(contact_id, result["fields"].get("qualification"), "close")
        return self._close_result(contact_id, result["contact"], False, None)

    # -- textos da clinica (tela "Etapas") ---------------------------------------

    def _require_configure(self):
        if not self.can("gerenciar_config_sistema"):
            _fail(403, "permission_denied",
                  "Editar os nomes e textos do funil exige a permissão de configurações do sistema.")

    def _stored_overrides(self, doc):
        """Mapas validos do doc salvo, chave a chave: entrada invalida (edicao
        manual, chave que saiu do template) e ignorada, nunca derruba a tela."""
        clean = {field: {} for field in OVERRIDE_FIELDS}
        for field in OVERRIDE_FIELDS:
            values = (doc or {}).get(field)
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                try:
                    clean[field].update(fc.validate_overrides(self.catalog["template"], {field: {key: value}})[field])
                except fc.FunnelRuleError:
                    continue
        return clean

    def _settings_view(self, doc):
        stage_defaults, reason_defaults = self._defaults()
        version = (doc or {}).get("version")
        return {
            "version": version if isinstance(version, int) and not isinstance(version, bool) else 0,
            "template": self.catalog["template"],
            **self._stored_overrides(doc),
            "stages": [{"key": stage["key"], "default_label": stage_defaults[stage["key"]][0],
                        "default_description": stage_defaults[stage["key"]][1]}
                       for stage in self.catalog["stages"]],
            "reasons": [{"key": reason["key"], "default_label": reason_defaults[reason["key"]]}
                        for reason in self.catalog["reasons"]],
        }

    def get_settings(self):
        self._actor()
        self._require_configure()
        # Leitura direta (sem o cache): o editor precisa da versao atual.
        return self._settings_view(self.repo.overrides() or {})

    def save_settings(self, payload):
        """payload = {version, stage_labels?, stage_descriptions?, reason_labels?}
        (rota ja validou o shape). Mapa enviado SUBSTITUI o salvo (texto vazio
        = volta ao padrao); mapa ausente fica como esta."""
        self._actor()
        self._require_configure()
        version = (payload or {}).get("version") if isinstance(payload, dict) else None
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            _fail(422, "invalid_payload", "Dados inválidos.")
        present = [field for field in OVERRIDE_FIELDS if field in payload]
        template = self.catalog["template"]
        try:
            clean = fc.validate_overrides(template, {field: payload[field] for field in present})
        except fc.FunnelRuleError as exc:
            _fail(422, exc.code, exc.message)
        now = self.now()

        def build(current):
            kept = self._stored_overrides(current)
            doc = {field: (clean[field] if field in present else kept[field]) for field in OVERRIDE_FIELDS}
            doc.update({"template": template, "version": version + 1, "updated_at": now,
                        "updated_by_user_id": self.user_id, "updated_by_uid": self.uid})
            return doc

        try:
            saved = self.repo.save_overrides(version, build)
        except StageConflict as exc:
            current = exc.contact or {}
            current_version = current.get("version")
            _fail(409, "stale_version", "Os nomes e textos do funil mudaram. Recarregue antes de salvar.",
                  current={"version": current_version if isinstance(current_version, int)
                           and not isinstance(current_version, bool) else 0})
        except (google_exceptions.Aborted, google_exceptions.Conflict):
            _fail(409, "try_again", "Muitas alterações ao mesmo tempo. Tente de novo.")
        except ValueError as exc:
            if isinstance(exc.__cause__, google_exceptions.Aborted):
                _fail(409, "try_again", "Muitas alterações ao mesmo tempo. Tente de novo.")
            raise
        reset_overrides_cache(self.repo.tenant_id)
        self._audit("FUNNEL_SETTINGS_UPDATE", "Textos do funil: versao %d (%d nomes de etapa, %d textos, %d nomes de motivo)"
                    % (saved["version"], len(saved["stage_labels"]), len(saved["stage_descriptions"]),
                       len(saved["reason_labels"])))
        return self._settings_view(saved)

    # -- painel gerencial -------------------------------------------------------------

    def _dashboard_months(self, month, now):
        """(mes, anterior, limites, limites do anterior) ou 422 month_invalid.
        Faixa: DASHBOARD_FIRST_MONTH ate o mes seguinte ao atual (fuso BR);
        anos extremos (datetime fora da faixa) nunca viram 500."""
        current = fc.cohort_month(now)
        month = month or current
        try:
            bounds = fc.month_bounds(month)
            in_range = DASHBOARD_FIRST_MONTH <= month <= _shift_month(current, 1)
            previous = fc.previous_month(month) if in_range else None
            previous_bounds = fc.month_bounds(previous) if in_range else None
        except fc.FunnelRuleError as exc:
            _fail(422, exc.code, exc.message)
        except (ValueError, OverflowError):
            _fail(422, "month_invalid", "Mês inválido; use AAAA-MM.")
        if not in_range:
            _fail(422, "month_invalid", "Mês fora do período do painel (de %s até o mês seguinte ao atual)."
                  % DASHBOARD_FIRST_MONTH)
        return month, previous, bounds, previous_bounds

    def dashboard(self, month=None, refresh=False):
        self._actor()
        if not (self.privileged and self.can("ver_dashboard_funil")):
            _fail(403, "permission_denied", "O painel do funil exige a visão do tenant.")
        now = self.now()
        month, previous, bounds, previous_bounds = self._dashboard_months(month, now)
        # Versao dos textos da clinica na chave: renomear etapa/motivo nao
        # serve rotulo velho do cache.
        key = (self.repo.tenant_id, month, self.catalog.get("template"), self.catalog.get("version"),
               self.catalog.get("overrides_version"))
        if not refresh:
            cached = _dashboard_cache_get(key)
            if cached is not None:
                return dict(cached, cached=True)
        # Todo calculo (refresh ou cache ausente/vencido) consome o throttle:
        # percorrer meses distintos nao fura o limite.
        self._rate()
        payload = self._compute_dashboard(month, previous, bounds, previous_bounds, now)
        _dashboard_cache_put(key, payload)
        return dict(payload, cached=False)

    def _compute_dashboard(self, month, previous, bounds, previous_bounds, now):
        catalog = self.catalog
        stages = catalog["stages"]
        tracked = self.lgpd_tracked()
        booked = fc.stage_def(catalog, (catalog.get("kpis") or {}).get("booked_stage"))
        lost = [stage for stage in stages if stage["kind"] == fc.KIND_LOST]
        excluded = [stage for stage in stages if stage["kind"] == fc.KIND_EXCLUDED]
        milestones = fc.milestone_stages(catalog)
        periods = {"month": (month, bounds), "previous": (previous, previous_bounds)}
        repo = self.repo
        jobs = []
        for stage in stages:
            jobs.append((("stage", stage["key"]), lambda s=stage: repo.count_stage(s["key"])))
            cut = fc.stale_cutoff(stage, now)
            if cut:
                jobs.append((("stale", stage["key"]), lambda s=stage, c=cut: repo.count_stage(s["key"], stale=c)))
        jobs.append((("with_stage",), repo.count_with_stage))
        for label, (period, (start, end)) in periods.items():
            jobs.append((("entered", label), lambda p=period: repo.count_cohort(p)))
            if tracked:
                jobs.append((("lgpd", label), lambda p=period: repo.count_cohort(p, lgpd_accepted=True)))
            for stage in milestones:
                jobs.append((("level", label, stage["key"]),
                             lambda p=period, s=stage: repo.count_cohort(p, min_order=int(s["order"]))))
            # Descartado (kind excluded) fica fora da base de conversao: a
            # maior etapa e monotonica, entao o spam que passou por Novo
            # contato continua no degrau; tira-se por etapa atual (indice 8).
            for stage in excluded:
                jobs.append((("excluded", label, stage["key"]),
                             lambda p=period, s=stage: repo.count_cohort(p, stage=s["key"])))
                for level in milestones:
                    jobs.append((("excluded_level", label, stage["key"], level["key"]),
                                 lambda p=period, s=stage, m=level: repo.count_cohort(
                                     p, stage=s["key"], min_order=int(m["order"]))))
            if booked:
                for stage in lost:
                    jobs.append((("closed", label, stage["key"]),
                                 lambda p=period, s=stage: repo.count_cohort(p, stage=s["key"], below_order=int(booked["order"]))))
            for stage in stages:
                if stage.get("manual_target"):
                    jobs.append((("move", label, stage["key"]),
                                 lambda a=start, b=end, s=stage: repo.count_changes(a, b, entry_kinds=fc.COUNTED_ENTRY_KINDS, to_stage=s["key"])))
            jobs.append((("triage", label), lambda a=start, b=end: repo.count_changes(a, b, entry_kind=fc.ENTRY_KIND_TRIAGE)))
            jobs.append((("react", label), lambda a=start, b=end: repo.count_changes(a, b, entry_kind=fc.ENTRY_KIND_REACTIVATION)))
            for stage in lost:
                jobs.append((("entries", label, stage["key"]),
                             lambda a=start, b=end, s=stage: repo.stream_entries(s["key"], REASON_ENTRY_KINDS, a, b, REASON_STREAM_LIMIT)))
            jobs.append((("corrections", label), lambda p=period: repo.stream_corrections(p, REASON_STREAM_LIMIT)))
        values = dict(zip([name for name, _ in jobs],
                          self._parallel(lambda job: job[1](), jobs, DASHBOARD_WORKERS)))

        current = []
        template_total = 0
        for stage in stages:
            count = values[("stage", stage["key"])]
            template_total += count
            if not stage.get("active") and not count:
                continue
            current.append({"stage": stage["key"], "label": stage["label"], "kind": stage["kind"],
                            "count": count, "stale_count": values.get(("stale", stage["key"]))})
        with_stage = values[("with_stage",)]
        unknown = max(0, with_stage - template_total)

        def cohort(label):
            entered = values[("entered", label)]
            out = sum(values[("excluded", label, stage["key"])] for stage in excluded)
            levels = []
            for stage in milestones:
                gross = values[("level", label, stage["key"])]
                gone = sum(values[("excluded_level", label, ex["key"], stage["key"])] for ex in excluded)
                # reached = liquido (sem quem esta hoje em etapa excluida).
                levels.append({"stage": stage["key"], "label": stage["label"],
                               "reached": max(0, gross - gone), "reached_gross": gross})
            return {"entered": entered, "excluded": out, "entered_net": max(0, entered - out),
                    "lgpd_accepted": values[("lgpd", label)] if tracked else None,
                    "levels": levels,
                    "closed_without_booking": sum(values.get(("closed", label, stage["key"]), 0) for stage in lost)}

        truncated = False

        def tally(final):
            counts = {}
            for reason in final.values():
                if reason:
                    counts[reason] = counts.get(reason, 0) + 1
            return [{"reason": reason, "label": fc.reason_label(catalog, reason), "count": count}
                    for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]

        def reasons(label):
            """(movimento/reativacao, triagem): motivo vigente de cada entrada
            em etapa de perda no mes, com as correcoes aplicadas pelo
            corrects_entry_id em ordem de occurred_at."""
            nonlocal truncated
            moved, triaged = {}, {}
            for stage in lost:
                rows = values[("entries", label, stage["key"])]
                truncated = truncated or len(rows) >= REASON_STREAM_LIMIT
                for row in rows:
                    kind = row.get("entry_kind")
                    if kind in fc.COUNTED_ENTRY_KINDS:
                        moved[str(row.get("id"))] = row.get("stage_reason")
                    elif kind == fc.ENTRY_KIND_TRIAGE:
                        triaged[str(row.get("id"))] = row.get("stage_reason")
            corrections = values[("corrections", label)]
            truncated = truncated or len(corrections) >= REASON_STREAM_LIMIT
            for row in sorted(corrections, key=lambda item: (fc.as_utc(item.get("occurred_at")) or _FAR_FUTURE,
                                                             str(item.get("id") or ""))):
                target = str(row.get("corrects_entry_id") or "")
                for final in (moved, triaged):
                    if target in final:
                        final[target] = row.get("stage_reason")
            return tally(moved), tally(triaged)

        reasons_month, triage_month = reasons("month")
        reasons_previous, triage_previous = reasons("previous")
        triage_label = fc.stage_label(catalog, catalog.get("triage_stage") or fc.TRIAGE_STAGE)
        notes = ["Coorte = mês de entrada no funil, no fuso de São Paulo.",
                 "Contatos antigos (%s) e backups graduados contam na coorte do mês do primeiro contato: "
                 "um mês já fechado pode crescer quando eles entram no funil." % triage_label]
        if excluded:
            notes.append("Contatos hoje em %s ficam fora da base da coorte: os percentuais usam quem entrou "
                         "menos esses contatos." % ", ".join(stage["label"] for stage in excluded))
        if not tracked:
            notes.append("Neste tenant o aviso LGPD é conduzido pelo agente de IA: o aceite não é medido pelo CRM.")
        if unknown:
            notes.append("%d contato(s) com etapa fora do catálogo atual." % unknown)
        if truncated:
            notes.append("Motivos calculados sobre os primeiros %d registros do período." % REASON_STREAM_LIMIT)
        return {
            "month": month, "previous_month": previous, "generated_at": now.isoformat(),
            "current": {"stages": current, "with_stage": with_stage, "unknown_stage": unknown},
            "cohort": {"month": cohort("month"), "previous": cohort("previous")},
            "movements": [{"stage": stage["key"], "label": stage["label"],
                           "month": values[("move", "month", stage["key"])],
                           "previous": values[("move", "previous", stage["key"])]}
                          for stage in stages if stage.get("manual_target")],
            "triage": {"month": values[("triage", "month")], "previous": values[("triage", "previous")]},
            "reactivations": {"month": values[("react", "month")], "previous": values[("react", "previous")]},
            "reasons": {"month": reasons_month, "previous": reasons_previous,
                        "month_triage": triage_month, "previous_triage": triage_previous,
                        "truncated": truncated},
            "notes": notes,
        }


def close_gate(catalog, contact):
    """O fechamento manual EXIGE o desfecho agora (espelha o gate de
    main.wa_set_attendance e do front)? Contato fora de etapa de desfecho de
    encerramento (inclusive sem etapa) ou com o legado novo/em_atendimento."""
    contact = contact or {}
    outcomes = {stage["key"] for stage in fc.close_outcomes(catalog)}
    return (str(contact.get("qualification") or "novo") in LEGACY_OPEN
            or (contact.get(fc.F_STAGE) or None) not in outcomes)


def close_attendance_outcome(user, conversation, contact, payload, **service_options):
    """Encerramento unificado (main.wa_set_attendance, decisao do PO de
    28/10): o desfecho do modal "Encerrar atendimento" e a ETAPA do funil e
    o legado equivalente vai junto. O chamador invoca ANTES de qualquer
    escrita do fechamento; HTTPException (409/422/403, detail {code,
    message}) aborta o fechamento.

    Devolve {"applied", "stage", "qualification", "replayed", "activity_id"}:
    - applied=True: etapa (ou so o legado, se o desfecho = etapa atual)
      gravada pela transacao do funil; o chamador grava so notas e tags;
    - applied=False: contato fora do funil (backup ou arquivado): nada foi
      gravado e `qualification` = legado equivalente, para o chamador gravar
      como o modal antigo (mesmo gate, toggles e auditoria dele)."""
    # Import tardio: funnel_routes importa este modulo.
    from funnel_routes import parse_stage_body
    tenant_id = str((user or {}).get("tenant_id") or "")
    if not tenant_id or tenant_id != str(get_tenant_context() or ""):
        _fail(403, "tenant_mismatch", "Sessão sem contexto de tenant válido.")
    catalog = load_catalog(tenant_id)
    if not catalog or not catalog.get("legacy_qualification_sync"):
        # Funil desligado depois que a tela carregou: nao fecha sem o desfecho.
        _fail(409, "funnel_disabled", "O funil não está disponível agora. Atualize a tela e encerre de novo.")
    body = parse_stage_body(payload)
    outcomes = {stage["key"] for stage in fc.close_outcomes(catalog)}
    if body["to_stage"] not in outcomes:
        _fail(422, "stage_not_allowed", "Este desfecho não pode ser usado no encerramento.")
    contact = dict(contact or {})
    if (conversation or {}).get("is_backup") or contact.get("is_backup") or contact.get("is_archived"):
        try:
            fc.validate_change(catalog, current_stage=None, current_reason=None, to_stage=body["to_stage"],
                               reason=body.get("reason"), note=body.get("reason_note"),
                               appointment_kind=body.get("appointment_kind"))
        except fc.FunnelRuleError as exc:
            _fail(422, exc.code, exc.message)
        return {"applied": False, "stage": None, "replayed": False, "activity_id": None,
                "qualification": fc.legacy_qualification_for(catalog, body["to_stage"])}
    service = FunnelService(FunnelRepository(tenant_id), user, None, catalog, **service_options)
    result = service.close_stage(contact.get("id"), contact, body)
    return {"applied": True, "stage": result["stage"], "qualification": result["qualification"],
            "replayed": result["replayed"], "activity_id": result["activity_id"]}
