# -*- coding: utf-8 -*-
"""Catalogo do funil comercial por tenant: etapas, motivos e regras puras.

Nucleo generico (sem `if tenant`): o tenant aponta um TEMPLATE daqui em
tenants/{tid}.settings.funnel (mesmo doc e cache de 60 s de settings.ai; o
super-admin nao edita settings). Rotulos, etapas/motivos inativos, limiares de
"parado" e tipos de canal da entrada automatica podem ser sobrepostos sem
deploy (scripts/set_tenant_funnel.py, dry-run default). Sem config habilitada =
funil desligado: rotas /api/funnel 404 e entrada automatica inerte.

Modulo PURO de proposito: sem Firestore/httpx/FastAPI no import. A unica
leitura (doc do tenant, em cache) e lazy e protegida. Importavel pelo webhook,
pelos simuladores e pelo script de migracao.

Invariantes (ADR 0015 + emenda de 28/10/2026):
- chave de etapa/motivo e estavel e nunca sai de um template (desativar em
  vez de remover); `new` (entrada) e `unclassified` (triagem) existem em todo
  template;
- a etapa vive em campos PLANOS do contato (merge profundo nao deixa subchave
  velha); o motivo NAO fica no contato (categoria pode ser dado de saude e o
  doc do contato e legivel via SDK pela pool): so na Activity, apontada por
  crm_stage_activity_id;
- "uma classificacao so" (decisao do PO, 28/10): em template com
  legacy_qualification_sync, a mudanca MANUAL de etapa grava tambem o desfecho
  legado equivalente (stage.legacy_qualification), para os gates que ainda
  leem `qualification` (reabertura em lote, caixas, gate do fechamento)
  continuarem coerentes. Entrada automatica, automacoes por evento e migracao
  NUNCA escrevem qualification (o handoff gravar em_atendimento tiraria o lead
  da caixa da recepcao);
- automacoes so por evento explicito (template["automations"]), so para
  frente a partir das etapas listadas em "from";
- este modulo nao faz I/O de escrita: devolve campos/eventos para o chamador.
"""

import copy
import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    BR_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - tzdata ausente
    BR_TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")

logger = logging.getLogger("castro_crm.funnel_catalog")

ENTRY_STAGE = "new"
TRIAGE_STAGE = "unclassified"

KIND_OPEN = "open"
KIND_WON = "won"
KIND_LOST = "lost"
KIND_EXCLUDED = "excluded"
KIND_TRIAGE = "triage"
STAGE_KINDS = (KIND_OPEN, KIND_WON, KIND_LOST, KIND_EXCLUDED, KIND_TRIAGE)
# Contam na "maior etapa alcancada" (piramide por coorte).
PIPELINE_KINDS = (KIND_OPEN, KIND_WON)
# Sair destes para aberto/ganho e reativacao.
CLOSED_KINDS = (KIND_LOST, KIND_EXCLUDED)

STALE_PATIENT_SILENCE = "patient_silence"   # sem mensagem DO PACIENTE ha N dias
STALE_TIME_IN_STAGE = "time_in_stage"       # na etapa ha N dias
STALE_TASK = "task"                         # sinal vem da tarefa (atrasada / sem proxima acao)
STALE_KINDS = (STALE_PATIENT_SILENCE, STALE_TIME_IN_STAGE, STALE_TASK)

EVENT_CHANGED = "crm_stage_changed"
EVENT_REASON_CHANGED = "crm_stage_reason_changed"
EVENT_MIGRATED = "crm_stage_migrated"
EVENT_MIGRATION_REVERTED = "crm_stage_migration_reverted"
STAGE_EVENTS = (EVENT_CHANGED, EVENT_REASON_CHANGED, EVENT_MIGRATED, EVENT_MIGRATION_REVERTED)
STAGE_EVENT_PREFIX = "crm_stage_"

ENTRY_KIND_MOVE = "move"                # entre etapas do funil
ENTRY_KIND_TRIAGE = "triage"            # vindo de A classificar ou de sem etapa
ENTRY_KIND_REACTIVATION = "reactivation"  # de perdido/excluido para aberto/ganho
# "Movimentos do mes" no painel: triagem de antigos fica a parte.
COUNTED_ENTRY_KINDS = (ENTRY_KIND_MOVE, ENTRY_KIND_REACTIVATION)

SOURCE_USER = "user"
SOURCE_INTAKE = "intake"
SOURCE_GRADUATION = "graduation"
SOURCE_MIGRATION = "migration"
SOURCE_SYSTEM = "system"
SOURCE_RULE_PREFIX = "rule:"   # automacao por evento: "rule:handoff", "rule:human_reply"

# Eventos explicitos que podem mover etapa sozinhos (template["automations"]).
AUTO_HANDOFF = "handoff"          # a Val (agente de IA) entregou o lead a recepcao
AUTO_HUMAN_REPLY = "human_reply"  # 1a resposta de uma pessoa da equipe pelo CRM
AUTO_EVENTS = (AUTO_HANDOFF, AUTO_HUMAN_REPLY)

# Vocabulario do campo legado wa_contacts.qualification (config.QUALIFICATION_OPTIONS);
# os terminais satisfazem o gate do fechamento manual.
LEGACY_QUALIFICATIONS = ("novo", "em_atendimento", "qualificado", "nao_qualificado",
                         "convertido", "nao_convertido")
LEGACY_TERMINAL = ("qualificado", "nao_qualificado", "convertido", "nao_convertido")

APPOINTMENT_KINDS = ("consultation", "procedure")
NOTE_MAX = 120
LABEL_MAX = 40
DESCRIPTION_MAX = 200

# Campos planos da etapa no contato (wa_contacts). Escritos SO pelo backend do
# funil, pela entrada automatica e pelo script de migracao.
F_STAGE = "crm_stage"
F_VERSION = "crm_stage_version"
F_CHANGED_AT = "crm_stage_changed_at"
F_SOURCE = "crm_stage_source"
F_ACTIVITY = "crm_stage_activity_id"
F_BY_USER = "crm_stage_changed_by_user_id"
F_BY_UID = "crm_stage_changed_by_uid"
F_ENTERED_AT = "crm_funnel_entered_at"
F_COHORT = "crm_cohort_month"
F_MAX_ORDER = "crm_max_reached_order"
CONTACT_STAGE_FIELDS = (F_STAGE, F_VERSION, F_CHANGED_AT, F_SOURCE, F_ACTIVITY,
                        F_BY_USER, F_BY_UID, F_ENTERED_AT, F_COHORT, F_MAX_ORDER)

_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Texto que vai para a tela: alem dos controles ASCII, recusa os controles
# C1 (Cc), os invisiveis/bidi (Cf: zero-width, RLO, BOM) e os separadores de
# linha/paragrafo Unicode (Zl/Zp): nome "vazio" ou texto invertido na UI.
_HIDDEN_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp"))


def _has_control(text):
    return bool(_CONTROL.search(text)) or any(unicodedata.category(ch) in _HIDDEN_CATEGORIES for ch in text)


class FunnelRuleError(Exception):
    """Regra de negocio do funil violada. `code` vai para a UI (estavel)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Templates. Rotulos e textos ao usuario com acentuacao normal (UI).
# ---------------------------------------------------------------------------

# Etapas e definicoes do PO para a clinica (28/10/2026). Conversao = marcar
# consulta (Cliente Agendado); quem marca pelo link da Val e confirmado pela
# equipe quando chega a clinica. Rotulos e textos sao renomeaveis pela clinica
# (system_settings/funnel); chaves nunca mudam.
TEMPLATES = {
    "clinic_v1": {
        "label": "Clínica: agente de IA, recepção e consulta",
        "kpis": {"booked_stage": "scheduled", "won_stage": "scheduled"},
        # Desfecho manual grava o legado equivalente (ver docstring do modulo).
        "legacy_qualification_sync": True,
        # Automacoes por evento explicito: so para frente, so a partir de "from".
        "automations": {
            AUTO_HANDOFF: {"from": ["new", "unclassified"], "to": "in_service"},
            AUTO_HUMAN_REPLY: {"from": ["new", "unclassified"], "to": "in_service"},
        },
        "stages": [
            {"key": "new", "label": "Novo contato", "kind": KIND_OPEN, "order": 10,
             "milestone": True, "stale": {"kind": STALE_PATIENT_SILENCE, "days": 1},
             "visibility_permission": "ver_contatos_agente_funil",
             "description": "Conversando com a Val (agente de IA), primeira interação. Entra sozinho na primeira mensagem."},
            {"key": "in_service", "label": "Em atendimento", "kind": KIND_OPEN, "order": 20,
             "milestone": True, "stale": {"kind": STALE_PATIENT_SILENCE, "days": 2},
             "legacy_qualification": "em_atendimento",
             "description": "Na recepção: a Val fez o handoff ou a equipe iniciou a conversa. Entra sozinho nesses casos."},
            {"key": "awaiting_followup", "label": "Aguardando retorno", "kind": KIND_OPEN, "order": 30,
             "stale": {"kind": STALE_TASK}, "close_outcome": True,
             "legacy_qualification": "nao_convertido",
             "description": "Combinou um retorno (vai pensar, orçamento em decisão). A próxima ação fica na tarefa de follow-up."},
            {"key": "scheduled", "label": "Cliente Agendado", "kind": KIND_WON, "order": 40,
             "milestone": True, "appointment_kind": True, "close_outcome": True,
             "legacy_qualification": "convertido",
             "description": "Marcou consulta. Quem agendou pelo link da Val: confirme quando a pessoa chegar à clínica."},
            {"key": "loyal", "label": "Paciente em acompanhamento", "kind": KIND_WON, "order": 50,
             "milestone": True, "close_outcome": True,
             "legacy_qualification": "convertido",
             "description": "Fez tratamento e deve voltar: revisões, retorno anual, novos tratamentos."},
            {"key": "non_converted", "label": "Não convertido", "kind": KIND_LOST, "order": 60,
             "requires_reason": True, "close_outcome": True,
             "legacy_qualification": "nao_convertido",
             "description": "Não aceitou a proposta, convênio não aceito, desistiu. O motivo é obrigatório e o contato pode voltar depois."},
            {"key": "disqualified", "label": "Não qualificado", "kind": KIND_EXCLUDED, "order": 70,
             "close_outcome": True, "legacy_qualification": "nao_qualificado",
             "description": "Spam, golpe, número errado ou contato sem interesse para a clínica. Fica fora das métricas de conversão."},
            {"key": "unclassified", "label": "A classificar", "kind": KIND_TRIAGE, "order": 90,
             "manual_target": False,
             "description": "Contato que já existia antes do funil, sem informação suficiente. Vai sozinho para Em atendimento quando passar pela recepção."},
        ],
        "reasons": [
            {"key": "proposal_declined", "label": "Não aceitou a proposta"},
            {"key": "insurance_not_accepted", "label": "Convênio não aceito"},
            {"key": "price", "label": "Preço"},
            {"key": "distance", "label": "Distância"},
            {"key": "financial", "label": "Questão financeira"},
            {"key": "no_interest", "label": "Sem interesse"},
            {"key": "no_response", "label": "Sem resposta",
             "hint": "Só quando a equipe decide parar as retomadas; silêncio não basta."},
            {"key": "postponed", "label": "Adiou",
             "hint": "Adiou sem data. Com retorno combinado, use Aguardando retorno."},
            {"key": "no_show", "label": "Não compareceu",
             "hint": "Agendou e não veio. Se ainda for remarcar, volte para Em atendimento com tarefa."},
            {"key": "medical_recommendation", "label": "Indicação médica",
             "hint": "Só a categoria. Não registre detalhes clínicos."},
            {"key": "other", "label": "Outro", "allows_note": True,
             "hint": "Texto curto. Não registre dados clínicos."},
            {"key": "not_informed", "label": "Motivo não registrado", "selectable": False},
        ],
    },
}


# ---------------------------------------------------------------------------
# Resolucao da config do tenant
# ---------------------------------------------------------------------------

def _clean_label(value, fallback):
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    if not value or len(value) > LABEL_MAX or _has_control(value):
        return fallback
    return value


def _clean_keys(values):
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {v for v in values if isinstance(v, str) and _KEY.match(v)}


def _clean_days(value):
    """int 1..365 liga o limiar; None/0 desliga; lixo = None (sem selo)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= 365 else None


def validate_template(name, template):
    """Erros estruturais de um template (lista vazia = ok). Usado por sims e
    pelo script de configuracao; o runtime confia nos templates do codigo."""
    errors = []
    stages = template.get("stages") or []
    keys = [s.get("key") for s in stages]
    if len(set(keys)) != len(keys):
        errors.append("%s: chave de etapa repetida" % name)
    for required in (ENTRY_STAGE, TRIAGE_STAGE):
        if required not in keys:
            errors.append("%s: falta a etapa reservada %s" % (name, required))
    for stage in stages:
        key = stage.get("key")
        if not isinstance(key, str) or not _KEY.match(key):
            errors.append("%s: chave invalida %r" % (name, key))
        if stage.get("kind") not in STAGE_KINDS:
            errors.append("%s: tipo invalido em %s" % (name, key))
        stale = stage.get("stale")
        if stale is not None and (not isinstance(stale, dict) or stale.get("kind") not in STALE_KINDS):
            errors.append("%s: limiar invalido em %s" % (name, key))
        legacy = stage.get("legacy_qualification")
        if legacy is not None and legacy not in LEGACY_QUALIFICATIONS:
            errors.append("%s: desfecho legado invalido em %s" % (name, key))
        if stage.get("close_outcome") and template.get("legacy_qualification_sync") and legacy not in LEGACY_TERMINAL:
            # O gate do fechamento exige desfecho terminal no legado.
            errors.append("%s: %s e desfecho de encerramento sem legado terminal" % (name, key))
        if stage.get("description") is not None and (
                not isinstance(stage["description"], str) or len(stage["description"]) > DESCRIPTION_MAX):
            errors.append("%s: descricao longa demais em %s" % (name, key))
    entry = next((s for s in stages if s.get("key") == ENTRY_STAGE), {})
    triage = next((s for s in stages if s.get("key") == TRIAGE_STAGE), {})
    if entry and entry.get("kind") != KIND_OPEN:
        errors.append("%s: %s precisa ser aberta" % (name, ENTRY_STAGE))
    if triage and (triage.get("kind") != KIND_TRIAGE or triage.get("manual_target", True)):
        errors.append("%s: %s precisa ser triagem e nao destino manual" % (name, TRIAGE_STAGE))
    if entry.get("legacy_qualification") or triage.get("legacy_qualification"):
        errors.append("%s: entrada e triagem nao gravam desfecho legado" % name)
    for event, rule in (template.get("automations") or {}).items():
        if event not in AUTO_EVENTS or not isinstance(rule, dict):
            errors.append("%s: automacao desconhecida %r" % (name, event))
            continue
        if rule.get("to") not in keys or any(k not in keys for k in rule.get("from") or []):
            errors.append("%s: automacao %s aponta etapa inexistente" % (name, event))
        target = next((s for s in stages if s.get("key") == rule.get("to")), {})
        if target.get("kind") not in PIPELINE_KINDS:
            errors.append("%s: automacao %s precisa levar a etapa de funil" % (name, event))
    reasons = [r.get("key") for r in template.get("reasons") or []]
    if len(set(reasons)) != len(reasons):
        errors.append("%s: motivo repetido" % name)
    for key in reasons:
        if not isinstance(key, str) or not _KEY.match(key):
            errors.append("%s: motivo invalido %r" % (name, key))
    kpis = template.get("kpis") or {}
    for slot in ("booked_stage", "won_stage"):
        if kpis.get(slot) and kpis[slot] not in keys:
            errors.append("%s: kpi %s aponta etapa inexistente" % (name, slot))
    return errors


def _clean_description(value, fallback):
    if not isinstance(value, str):
        return fallback
    value = value.strip()
    if not value or len(value) > DESCRIPTION_MAX or _has_control(value):
        return fallback
    return value


def validate_overrides(template_name, payload):
    """Valida os textos que a CLINICA edita na tela "Etapas" (doc
    tenant-scoped system_settings/funnel): rotulos e descricoes de etapa e
    rotulos de motivo. So chaves do template; texto vazio = volta ao padrao
    (chave omitida no resultado). Devolve o dict limpo ou levanta
    FunnelRuleError('overrides_invalid'). Nao muda etapas, ordem nem regras."""
    template = TEMPLATES.get(str(template_name or ""))
    if not template or not isinstance(payload, dict):
        raise FunnelRuleError("overrides_invalid", "Configuração de etapas inválida.")
    stage_keys = {s["key"] for s in template["stages"]}
    reason_keys = {r["key"] for r in template["reasons"]}
    clean = {"stage_labels": {}, "stage_descriptions": {}, "reason_labels": {}}
    for field, keys, maximum, label in (("stage_labels", stage_keys, LABEL_MAX, "Nome da etapa"),
                                        ("stage_descriptions", stage_keys, DESCRIPTION_MAX, "Texto da etapa"),
                                        ("reason_labels", reason_keys, LABEL_MAX, "Nome do motivo")):
        values = payload.get(field, {})
        if not isinstance(values, dict):
            raise FunnelRuleError("overrides_invalid", "%s inválido." % label)
        for key, value in values.items():
            if key not in keys:
                raise FunnelRuleError("overrides_invalid", "%s: chave desconhecida." % label)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if not isinstance(value, str):
                raise FunnelRuleError("overrides_invalid", "%s inválido." % label)
            text = value.strip()
            if len(text) > maximum or _has_control(text):
                raise FunnelRuleError("overrides_invalid", "%s: use até %d caracteres, sem quebra de linha." % (label, maximum))
            clean[field][key] = text
    return clean


def resolve_funnel(settings, overrides=None):
    """Catalogo efetivo a partir de tenants/{tid}.settings.funnel (Castro:
    habilitacao, template, inativos, limiares) e, por cima, dos textos que a
    clinica edita (`overrides` = doc system_settings/funnel). None quando
    desligado, template desconhecido ou config malformada. Nunca levanta."""
    try:
        if not isinstance(settings, dict) or settings.get("enabled") is not True:
            return None
        name = str(settings.get("template") or "")
        template = TEMPLATES.get(name)
        if not template:
            return None
        overrides = overrides if isinstance(overrides, dict) else {}
        stage_labels = dict(settings.get("stage_labels") if isinstance(settings.get("stage_labels"), dict) else {})
        reason_labels = dict(settings.get("reason_labels") if isinstance(settings.get("reason_labels"), dict) else {})
        for target, field in ((stage_labels, "stage_labels"), (reason_labels, "reason_labels")):
            if isinstance(overrides.get(field), dict):
                target.update(overrides[field])
        stage_descriptions = overrides.get("stage_descriptions") if isinstance(overrides.get("stage_descriptions"), dict) else {}
        inactive_stages = _clean_keys(settings.get("inactive_stages")) - {ENTRY_STAGE, TRIAGE_STAGE}
        inactive_reasons = _clean_keys(settings.get("inactive_reasons"))
        stale_days = settings.get("stale_days") if isinstance(settings.get("stale_days"), dict) else {}
        channel_types = [t for t in (settings.get("intake_channel_types") or ["standard"])
                         if isinstance(t, str) and t]
        stages = []
        for raw in template["stages"]:
            stage = copy.deepcopy(raw)
            stage["default_label"] = stage["label"]
            stage["default_description"] = stage.get("description") or ""
            stage["label"] = _clean_label(stage_labels.get(stage["key"]), stage["label"])
            stage["description"] = _clean_description(stage_descriptions.get(stage["key"]),
                                                      stage.get("description") or "")
            stage["active"] = stage["key"] not in inactive_stages
            stage.setdefault("requires_reason", False)
            stage.setdefault("manual_target", True)
            stage.setdefault("milestone", False)
            stage.setdefault("appointment_kind", False)
            stage.setdefault("close_outcome", False)
            stage.setdefault("visibility_permission", None)
            if not template.get("legacy_qualification_sync"):
                stage["legacy_qualification"] = None
            stage.setdefault("legacy_qualification", None)
            stale = stage.get("stale")
            if stale and stale.get("kind") != STALE_TASK and stage["key"] in stale_days:
                days = _clean_days(stale_days.get(stage["key"]))
                stage["stale"] = dict(stale, days=days) if days else None
            stages.append(stage)
        stages.sort(key=lambda s: (s["order"], s["key"]))
        reasons = []
        for raw in template["reasons"]:
            reason = copy.deepcopy(raw)
            reason["default_label"] = reason["label"]
            reason["label"] = _clean_label(reason_labels.get(reason["key"]), reason["label"])
            reason["active"] = reason["key"] not in inactive_reasons
            reason.setdefault("selectable", True)
            reason.setdefault("allows_note", False)
            reasons.append(reason)
        version = settings.get("version")
        overrides_version = overrides.get("version")
        return {
            "template": name,
            "template_label": template.get("label") or name,
            "version": version if isinstance(version, int) and not isinstance(version, bool) else 0,
            "overrides_version": (overrides_version if isinstance(overrides_version, int)
                                  and not isinstance(overrides_version, bool) else 0),
            "enabled_at": settings.get("enabled_at"),
            "stages": stages,
            "reasons": reasons,
            "kpis": dict(template.get("kpis") or {}),
            "automations": copy.deepcopy(template.get("automations") or {}),
            "legacy_qualification_sync": bool(template.get("legacy_qualification_sync")),
            "intake_channel_types": channel_types or ["standard"],
            "entry_stage": ENTRY_STAGE,
            "triage_stage": TRIAGE_STAGE,
        }
    except Exception as exc:  # config malformada nunca derruba o chamador
        logger.warning("config do funil invalida: %s", type(exc).__name__)
        return None


def funnel_for_tenant(tenant_doc, overrides=None):
    """Catalogo do doc de tenant (dict) ou None. `overrides` = textos da
    clinica (system_settings/funnel), so para telas; o webhook nao precisa."""
    settings = (tenant_doc or {}).get("settings") if isinstance(tenant_doc, dict) else None
    if not isinstance(settings, dict):
        return None
    return resolve_funnel(settings.get("funnel"), overrides)


def load_tenant_funnel(tenant_id):
    """Catalogo do tenant pelo cache do tenant_service (60 s), ou None.
    Respeita FEATURE_FUNNEL. Nunca levanta."""
    try:
        import config
        if not getattr(config, "FEATURE_FUNNEL", False) or not tenant_id:
            return None
        from tenant_service import get_tenant
        return funnel_for_tenant(get_tenant(str(tenant_id)) or {})
    except Exception as exc:
        logger.warning("leitura do funil do tenant falhou: %s", type(exc).__name__)
        return None


def intake_catalog_for_channel(channel, tenant_id):
    """Uma vez por payload, no webhook: catalogo se a 1a mensagem ao vivo do
    cliente neste canal deve colocar o contato no funil; None caso contrario.
    Exige o tenant do canal igual ao tenant do contexto (payload com varias
    entries e o fallback 'hubloc' do contexto implicito nao contaminam).
    Nunca levanta."""
    try:
        if not tenant_id or not isinstance(channel, dict):
            return None
        channel_tenant = str(channel.get("tenant_id") or "")
        if channel_tenant and channel_tenant != str(tenant_id):
            return None
        catalog = load_tenant_funnel(tenant_id)
        if not catalog:
            return None
        if str(channel.get("channel_type") or "") not in catalog["intake_channel_types"]:
            return None
        return catalog
    except Exception as exc:
        logger.warning("intake do funil desligado neste payload: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Consultas ao catalogo
# ---------------------------------------------------------------------------

def stage_def(catalog, key):
    for stage in (catalog or {}).get("stages") or []:
        if stage["key"] == key:
            return stage
    return None


def reason_def(catalog, key):
    for reason in (catalog or {}).get("reasons") or []:
        if reason["key"] == key:
            return reason
    return None


def stage_label(catalog, key):
    stage = stage_def(catalog, key)
    return stage["label"] if stage else (key or "Sem etapa")


def reason_label(catalog, key):
    reason = reason_def(catalog, key)
    return reason["label"] if reason else (key or "")


def manual_targets(catalog):
    return [s for s in (catalog or {}).get("stages") or [] if s["active"] and s["manual_target"]]


def pipeline_stages(catalog):
    return [s for s in (catalog or {}).get("stages") or [] if s["kind"] in PIPELINE_KINDS]


def milestone_stages(catalog):
    return [s for s in pipeline_stages(catalog) if s.get("milestone")]


def entry_kind(catalog, from_key, to_key):
    from_stage = stage_def(catalog, from_key) if from_key else None
    to_stage = stage_def(catalog, to_key)
    if not from_key or (from_stage and from_stage["kind"] == KIND_TRIAGE):
        return ENTRY_KIND_TRIAGE
    if from_stage and to_stage and from_stage["kind"] in CLOSED_KINDS and to_stage["kind"] in PIPELINE_KINDS:
        return ENTRY_KIND_REACTIVATION
    return ENTRY_KIND_MOVE


def next_max_order(catalog, current_max, to_key):
    """Maior etapa alcancada: monotonica, so etapas de funil (aberto/ganho)."""
    try:
        current = int(current_max or 0)
    except (TypeError, ValueError):
        current = 0
    stage = stage_def(catalog, to_key)
    if stage and stage["kind"] in PIPELINE_KINDS:
        return max(current, int(stage["order"]))
    return current


def validate_change(catalog, *, current_stage, current_reason, to_stage, reason=None,
                    note=None, appointment_kind=None):
    """Valida a mudanca pedida. Devolve {event_type, reason, note,
    appointment_kind, legacy_qualification}. Levanta FunnelRuleError (code
    estavel). `legacy_qualification` = desfecho legado a gravar junto (so em
    template com legacy_qualification_sync; None = nao tocar)."""
    target = stage_def(catalog, to_stage) if isinstance(to_stage, str) else None
    if not target:
        raise FunnelRuleError("unknown_stage", "Etapa inexistente no funil deste tenant.")
    if not target["active"] or not target["manual_target"]:
        raise FunnelRuleError("stage_not_allowed", "Esta etapa não pode ser escolhida.")
    legacy = target.get("legacy_qualification")
    clean_reason = None
    clean_note = None
    if target["requires_reason"]:
        if not reason:
            raise FunnelRuleError("reason_required", "Informe o motivo.")
        found = reason_def(catalog, reason) if isinstance(reason, str) else None
        if not found or not found["active"] or not found["selectable"]:
            raise FunnelRuleError("reason_not_allowed", "Motivo inválido para esta etapa.")
        allowed = target.get("reason_keys")
        if allowed and reason not in allowed:
            raise FunnelRuleError("reason_not_allowed", "Motivo inválido para esta etapa.")
        clean_reason = reason
        if note not in (None, ""):
            if not found["allows_note"]:
                raise FunnelRuleError("note_not_allowed", "Texto livre só no motivo Outro.")
            if not isinstance(note, str):
                raise FunnelRuleError("note_invalid", "Texto do motivo inválido.")
            clean_note = note.strip()
            if len(clean_note) > NOTE_MAX or _has_control(clean_note):
                raise FunnelRuleError("note_invalid", "Use até %d caracteres, sem quebra de linha." % NOTE_MAX)
            clean_note = clean_note or None
    elif reason not in (None, "") or note not in (None, ""):
        raise FunnelRuleError("reason_not_allowed", "Esta etapa não usa motivo.")
    clean_kind = None
    if appointment_kind not in (None, ""):
        if not target.get("appointment_kind") or appointment_kind not in APPOINTMENT_KINDS:
            raise FunnelRuleError("appointment_kind_invalid", "Tipo de compromisso inválido.")
        clean_kind = appointment_kind
    if current_stage == to_stage:
        if target["requires_reason"] and clean_reason != current_reason:
            return {"event_type": EVENT_REASON_CHANGED, "reason": clean_reason, "note": clean_note,
                    "appointment_kind": None, "legacy_qualification": legacy}
        raise FunnelRuleError("same_stage", "O contato já está nesta etapa.")
    return {"event_type": EVENT_CHANGED, "reason": clean_reason, "note": clean_note,
            "appointment_kind": clean_kind, "legacy_qualification": legacy}


def legacy_qualification_for(catalog, stage_key):
    """Desfecho legado equivalente a etapa (None = nao gravar)."""
    if not (catalog or {}).get("legacy_qualification_sync"):
        return None
    stage = stage_def(catalog, stage_key)
    return stage.get("legacy_qualification") if stage else None


def close_outcomes(catalog):
    """Etapas oferecidas como desfecho no modal "Encerrar atendimento"."""
    return [s for s in (catalog or {}).get("stages") or []
            if s["active"] and s["manual_target"] and s.get("close_outcome")]


def stage_visible(stage, has_permission):
    """Etapa sem permissao de visibilidade = visivel a quem ve o funil.
    `has_permission(chave)` e o predicado do RBAC do usuario."""
    perm = (stage or {}).get("visibility_permission")
    return not perm or bool(has_permission(perm))


# ---------------------------------------------------------------------------
# Datas e periodos (fuso da clinica)
# ---------------------------------------------------------------------------

def as_utc(value):
    """datetime com fuso (UTC) a partir de datetime/ISO; None se invalido.
    Datetime ingenuo e tratado como UTC (padrao dos campos do CRM)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cohort_month(moment):
    """'AAAA-MM' no fuso da clinica (America/Sao_Paulo)."""
    dt = as_utc(moment)
    if dt is None:
        return None
    return dt.astimezone(BR_TZ).strftime("%Y-%m")


def month_bounds(month):
    """(inicio_utc, fim_utc) do mes 'AAAA-MM' no fuso da clinica."""
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise FunnelRuleError("month_invalid", "Mês inválido; use AAAA-MM.")
    year, mon = map(int, month.split("-"))
    start = datetime(year, mon, 1, tzinfo=BR_TZ)
    end = datetime(year + (mon == 12), 1 if mon == 12 else mon + 1, 1, tzinfo=BR_TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def previous_month(month):
    year, mon = map(int, month.split("-"))
    return "%04d-%02d" % ((year - 1, 12) if mon == 1 else (year, mon - 1))


# ---------------------------------------------------------------------------
# Entrada automatica ("intake") — caminho quente: pura e sem excecao
# ---------------------------------------------------------------------------

def intake_fields(contact, at, catalog, *, origin, user_id=None, user_uid=""):
    """Campos da etapa para o MESMO write que o chamador ja faz (zero escrita
    extra). `contact` = doc atual (None = contato novo). `origin`:
    'live' (1a mensagem ao vivo do cliente), 'manual' (criacao manual pelo
    operador) ou 'graduation' (backup graduado). Devolve {} quando o funil
    nao esta habilitado (catalog None), o contato ja tem etapa, e backup ou
    tem revogacao LGPD. Contato que JA conversava antes (last_inbound_at
    anterior) ou backup graduado entra em A classificar, nao em Novo contato:
    paciente antigo nao conta como lead novo do mes. Criacao manual = a equipe
    iniciou a conversa: entra direto no destino da automacao human_reply (Em
    atendimento), quando o template a define. Nunca levanta."""
    try:
        if not catalog:
            return {}
        current = contact if isinstance(contact, dict) else {}
        if current.get(F_STAGE) or current.get("is_backup") or current.get("lgpd_revoked"):
            return {}
        moment = as_utc(at) or datetime.now(timezone.utc)
        legacy = origin == "graduation" or bool(current.get("last_inbound_at"))
        stage = TRIAGE_STAGE if legacy else ENTRY_STAGE
        if origin == "manual":
            human_target = ((catalog.get("automations") or {}).get(AUTO_HUMAN_REPLY) or {}).get("to")
            target = stage_def(catalog, human_target) if human_target else None
            if target and target["active"]:
                stage = human_target
        if not stage_def(catalog, stage):
            return {}
        try:
            version = int(current.get(F_VERSION) or 0)
        except (TypeError, ValueError):
            version = 0
        fields = {
            F_STAGE: stage,
            F_VERSION: version + 1,
            F_CHANGED_AT: moment,
            F_SOURCE: SOURCE_GRADUATION if origin == "graduation" else SOURCE_INTAKE,
            F_ACTIVITY: None,
            F_BY_USER: user_id if origin == "manual" else None,
            F_BY_UID: str(user_uid or "") if origin == "manual" else "",
        }
        if not current.get(F_ENTERED_AT):
            entered = (as_utc(current.get("first_seen_at")) if legacy else None) or moment
            fields[F_ENTERED_AT] = entered
            fields[F_COHORT] = cohort_month(entered)
        fields[F_MAX_ORDER] = next_max_order(catalog, current.get(F_MAX_ORDER), stage)
        return fields
    except Exception as exc:
        logger.warning("intake do funil ignorado: %s", type(exc).__name__)
        return {}


def auto_transition(contact, at, catalog, event, tenant_id):
    """Automacao por evento EXPLICITO (template["automations"][event]): so
    move para frente, a partir das etapas de "from" (nunca regride Cliente
    Agendado, Paciente em acompanhamento etc.). Devolve (campos, activity):
    os campos vao no MESMO write que o chamador ja faz; a Activity
    (crm_stage_changed, actor_type system, id deterministico por contato +
    evento + versao de origem -> reentrega e idempotente com set) o chamador
    grava best-effort, sem deixar excecao escapar. ({}, None) quando nao se
    aplica. Nunca escreve qualification (ver docstring do modulo). Nunca
    levanta."""
    try:
        if not catalog or event not in AUTO_EVENTS or not tenant_id:
            return {}, None
        rule = (catalog.get("automations") or {}).get(event) or {}
        current = contact if isinstance(contact, dict) else {}
        from_key = current.get(F_STAGE)
        to_key = rule.get("to")
        target = stage_def(catalog, to_key) if to_key else None
        if (not from_key or from_key not in (rule.get("from") or []) or not target
                or not target["active"] or current.get("is_backup")):
            return {}, None
        contact_id = current.get("id")
        if contact_id is None:
            return {}, None
        moment = as_utc(at) or datetime.now(timezone.utc)
        try:
            version = int(current.get(F_VERSION) or 0)
        except (TypeError, ValueError):
            version = 0
        # Sem o evento na chave: a versao de ORIGEM ja identifica a transicao
        # (o contato sai da versao v uma vez so). Handoff e 1a resposta humana
        # simultaneos a partir da mesma versao caem no MESMO doc: 1 movimento.
        key = "\x1f".join((str(tenant_id), "auto", str(contact_id), str(version)))
        activity_id = "stage_auto_" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        source = SOURCE_RULE_PREFIX + event
        fields = {
            F_STAGE: to_key,
            F_VERSION: version + 1,
            F_CHANGED_AT: moment,
            F_SOURCE: source,
            F_ACTIVITY: activity_id,
            F_BY_USER: None,
            F_BY_UID: "",
            F_MAX_ORDER: next_max_order(catalog, current.get(F_MAX_ORDER), to_key),
        }
        if not current.get(F_ENTERED_AT):
            fields[F_ENTERED_AT] = moment
            fields[F_COHORT] = cohort_month(moment)
        activity = {
            "id": activity_id, "tenant_id": str(tenant_id), "contact_id": contact_id,
            "task_id": None, "conversation_id": None,
            "event_type": EVENT_CHANGED, "actor_type": "system",
            "actor_user_id": None, "actor_uid": "",
            "occurred_at": moment, "recorded_at": datetime.now(timezone.utc),
            "operation_id": "auto:%s:%s" % (contact_id, version),
            "from_stage": from_key, "to_stage": to_key,
            "stage_reason": None, "from_reason": None,
            # Automacao e fato do periodo (paciente antigo voltou e foi atendido
            # agora): conta nos movimentos do mes, nao como triagem de antigos.
            "entry_kind": ENTRY_KIND_MOVE,
            "data": {"stage_version": version + 1, "source": source, "rule": event},
        }
        return fields, activity
    except Exception as exc:
        logger.warning("automacao do funil ignorada: %s", type(exc).__name__)
        return {}, None


# ---------------------------------------------------------------------------
# Sinais derivados ("parado", "mensagem nova") — nunca persistidos
# ---------------------------------------------------------------------------

def stale_cutoff(stage, now):
    """(campo, corte) da contagem de parados da etapa, ou None. Mesma regra
    dos selos dos cards (cabecalho e cards coerentes)."""
    rule = (stage or {}).get("stale")
    if not rule or rule.get("kind") == STALE_TASK or not rule.get("days"):
        return None
    field = "last_inbound_at" if rule["kind"] == STALE_PATIENT_SILENCE else F_CHANGED_AT
    return field, as_utc(now) - timedelta(days=int(rule["days"]))


def derived_signals(catalog, contact, now, next_task=None, tasks_known=False):
    """Selos do card a partir de campos ja lidos (sem I/O). `next_task` =
    resumo da proxima tarefa acessivel; `tasks_known` = o leitor pode ver
    tarefas (sem isso, nenhum selo de tarefa e emitido)."""
    now = as_utc(now) or datetime.now(timezone.utc)
    stage = stage_def(catalog, contact.get(F_STAGE))
    changed = as_utc(contact.get(F_CHANGED_AT))
    inbound = as_utc(contact.get("last_inbound_at"))
    days_in_stage = int((now - changed).total_seconds() // 86400) if changed else None
    idle_days = int((now - inbound).total_seconds() // 86400) if inbound else None
    signals = {"days_in_stage": days_in_stage, "patient_idle_days": idle_days,
               "stale": False, "stale_kind": None, "task_overdue": False,
               "no_next_action": False, "new_activity": False}
    rule = (stage or {}).get("stale") or {}
    if rule.get("kind") == STALE_PATIENT_SILENCE and rule.get("days") and idle_days is not None:
        signals["stale"] = idle_days >= int(rule["days"])
    elif rule.get("kind") == STALE_TIME_IN_STAGE and rule.get("days") and days_in_stage is not None:
        signals["stale"] = days_in_stage >= int(rule["days"])
    if signals["stale"]:
        signals["stale_kind"] = rule["kind"]
    if tasks_known:
        due = as_utc((next_task or {}).get("due_at"))
        signals["task_overdue"] = bool(due and due < now)
        if rule.get("kind") == STALE_TASK:
            signals["no_next_action"] = next_task is None
    if stage and stage["kind"] in (KIND_TRIAGE,) + CLOSED_KINDS + (KIND_WON,):
        signals["new_activity"] = bool(inbound and changed and inbound > changed)
    return signals
