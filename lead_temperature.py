# -*- coding: utf-8 -*-

"""
Classificacao de temperatura do lead (quente / morno / frio) a partir dos
parametros de sessao devolvidos pelo DetectIntent do Dialogflow CX.

Modulo PURO de proposito: sem imports de Firestore/httpx/config — importavel
pelos simuladores (tools/sim_cx_flow.py) e testavel isolado. A persistencia
fica toda em bot_service._finalize_cx_handoff (execucao adiada: o calculo
roda UMA unica vez, no handoff, sobre os params acumulados da sessao —
decisao do PO 2026-07-21, docs/PLANO_LEAD_TEMPERATURE.md).

Semantica dos niveis (UI: bolinha vermelha/amarela/branca):
  quente — alta intencao / SLA critico (quer agendar, convenio validado)
  morno  — exploratorio (interesse em tratamento/especialidade/sintoma)
  frio   — suporte generico / curiosidade (default)

Os nomes default sao os session params REAIS do agente Varizemed gravados
pelo Router (fonte: docs/val-castrochat-firestore-schema_2026-07-18.md,
secao 4) — de proposito NAO usamos campos de origem "Provavel — playbook"
como turn_count, cuja procedencia nao foi confirmada. Outros tenants/agentes
podem sobrescrever por chave em settings.ai.temperature_signals.
"""

TEMPERATURE_QUENTE = "quente"
TEMPERATURE_MORNO = "morno"
TEMPERATURE_FRIO = "frio"

# Ordem util pra comparacoes/futuros usos (maior = mais quente).
TEMPERATURE_RANK = {"": 0, TEMPERATURE_FRIO: 1, TEMPERATURE_MORNO: 2, TEMPERATURE_QUENTE: 3}

DEFAULT_TEMPERATURE_SIGNALS = {
    # bools truthy que tornam o lead QUENTE
    "quente_bool_any": ["wants_appointment", "insurance_validated"],
    # bools truthy que tornam o lead MORNO
    "morno_bool_any": ["wants_treatment"],
    # strings nao-vazias que tornam o lead MORNO
    "morno_nonempty_any": ["user_specialty", "user_symptom"],
}


def _truthy(value) -> bool:
    """Params do CX chegam como bool OU string ("true"/"false") — mesma
    ambiguidade ja tratada pelo _coerce_bool do conector. Dict = param em
    struct {chave: valor} (agente pos-2026-07-29; o conector desembrulha,
    mas snapshots antigos em bot_states podem carregar o dict cru)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "sim")
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return any(_truthy(v) for v in value.values())
    return False


def _filled(value) -> bool:
    """String substantiva (nao-vazia e nao um null textual)."""
    if isinstance(value, dict):
        # Param em struct: preenchido so se algum valor interno for
        # substantivo (dict nao-vazio de valores nulos NAO conta).
        return any(_filled(v) for v in value.values())
    if not isinstance(value, str):
        return bool(value)
    v = value.strip()
    return bool(v) and v.lower() not in ("null", "none")


def _resolve_signals(overrides) -> dict:
    """Merge PARCIAL: override por tenant substitui so as chaves presentes;
    ausentes caem no default. Guard defensivo pra config malformada (mesmo
    padrao de _get_tenant_ai_config)."""
    signals = dict(DEFAULT_TEMPERATURE_SIGNALS)
    if isinstance(overrides, dict):
        for key in DEFAULT_TEMPERATURE_SIGNALS:
            value = overrides.get(key)
            if isinstance(value, (list, tuple)):
                signals[key] = [str(v) for v in value]
    return signals


def signal_keys(signals=None) -> list:
    """Todos os nomes de param referenciados pela config (default ou override).

    Usado pelo bot_service pra montar o snapshot MINIMO persistido em
    bot_states — sem isto, um override de tenant apontando pra params
    exoticos ficaria de fora do snapshot e a classificacao no 'assumir'
    sairia errada.
    """
    cfg = _resolve_signals(signals)
    names = []
    for key in ("quente_bool_any", "morno_bool_any", "morno_nonempty_any"):
        for name in cfg.get(key) or []:
            if name not in names:
                names.append(name)
    return names


def classify_lead_temperature(params, signals=None) -> str:
    """Classifica os params de sessao do CX em quente/morno/frio.

    `params`: queryResult.parameters do turno de handoff (acumulados da
    sessao). `signals`: override opcional de settings.ai.temperature_signals.
    Nunca levanta — params malformados viram frio.
    """
    if not isinstance(params, dict):
        return TEMPERATURE_FRIO
    cfg = _resolve_signals(signals)
    if any(_truthy(params.get(name)) for name in cfg["quente_bool_any"]):
        return TEMPERATURE_QUENTE
    if any(_truthy(params.get(name)) for name in cfg["morno_bool_any"]):
        return TEMPERATURE_MORNO
    if any(_filled(params.get(name)) for name in cfg["morno_nonempty_any"]):
        return TEMPERATURE_MORNO
    return TEMPERATURE_FRIO
