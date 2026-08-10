# -*- coding: utf-8 -*-
"""Horario comercial por tenant — fonte UNICA dos dois bots (frente b, fase 1).

Fase 1: tabela hardcoded por tenant (horarios definidos pelo PO em
2026-08-09/10). Fase 2 move a tabela pra system_settings (self-service na
tela Administracao, com calendario de feriados por CHAVE — ver
docs/CX_HORARIO_COMERCIAL_DEV_IA.md); a API deste modulo foi desenhada pra
essa troca nao mudar nenhum caller.

Consumidores:
- caminho CX (bot_service): cx_hours_params() injeta fora_do_expediente +
  retorno_previsto na sessao do agente a cada turno. O agente ramifica no
  booleano e interpola o texto — nunca decide horario sozinho (a Val dizia
  "ja encerrou por hoje" as 07:32 de segunda, e a saudacao anunciava
  "8h as 18h" com sexta indo so ate 17h).
- bot builtin (hubloc): builtin_expediente_notice() substitui o aviso
  hardcoded antigo (7h-17h — ja divergia do atendimento real, que abre 8h).

Fuso FIXO -3 (Brasil sem DST desde 2019) — mesma convencao do protocolo
diario. Sem feriados na fase 1. Fail-safe em toda ponta: tenant sem tabela
NUNCA e declarado "fechado".

Strings retornadas sao voltadas ao cliente final -> acentuacao normal.
"""

from datetime import datetime, timedelta, timezone

BR_TZ = timezone(timedelta(hours=-3))

# Faixas por dia da semana (0=segunda ... 6=domingo). Dia ausente = fechado.
# Intervalo aberto no fim: [inicio, fim). Mais de uma faixa por dia = intervalo
# no meio (ex.: almoco) — suportado desde ja, nenhum tenant usa hoje.
_SCHEDULES = {
    "hubloc": {
        0: (("08:00", "17:00"),),
        1: (("08:00", "17:00"),),
        2: (("08:00", "17:00"),),
        3: (("08:00", "17:00"),),
        4: (("08:00", "17:00"),),
    },
    "varizemed": {
        0: (("08:00", "18:00"),),
        1: (("08:00", "18:00"),),
        2: (("08:00", "18:00"),),
        3: (("08:00", "18:00"),),
        4: (("08:00", "17:00"),),
    },
}
# O tenant de teste espelha a clinica real DE PROPOSITO: o dev de IA valida o
# agente contra os mesmos horarios que valem em producao.
_SCHEDULES["varizemed-test"] = _SCHEDULES["varizemed"]

_DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _parse_hhmm(valor):
    h, m = str(valor).split(":")
    return int(h), int(m)


def _fmt_hora(h, m):
    return f"{h}h{m:02d}" if m else f"{h}h"


def _to_br(now):
    if now is None:
        now = datetime.now(timezone.utc)
    return now.astimezone(BR_TZ)


def get_schedule(tenant_id):
    """Tabela do tenant, ou None se nao configurado (ou toda vazia)."""
    sched = _SCHEDULES.get(str(tenant_id or ""))
    if not sched or not any(sched.values()):
        return None
    return sched


def is_open(tenant_id, now=None):
    """True/False dentro do horario; None = tenant sem tabela.

    O None e deliberado (nao vira False): sem tabela o caller nao pode
    afirmar "fechado" — e a diferenca entre ficar calado e mentir."""
    sched = get_schedule(tenant_id)
    if sched is None:
        return None
    agora = _to_br(now)
    for ini, fim in sched.get(agora.weekday(), ()):
        if _parse_hhmm(ini) <= (agora.hour, agora.minute) < _parse_hhmm(fim):
            return True
    return False


def next_opening(tenant_id, now=None):
    """Proxima abertura (datetime aware em BR_TZ) ou None."""
    sched = get_schedule(tenant_id)
    if sched is None:
        return None
    agora = _to_br(now)
    for dias in range(0, 8):
        dia = agora + timedelta(days=dias)
        for ini, _fim in sched.get(dia.weekday(), ()):
            h, m = _parse_hhmm(ini)
            abertura = dia.replace(hour=h, minute=m, second=0, microsecond=0)
            if abertura > agora:
                return abertura
    return None


def retorno_previsto_text(tenant_id, now=None):
    """Texto pronto pra interpolar: "hoje às 8h" / "amanhã às 8h" /
    "segunda-feira às 8h". Vazio quando aberto ou sem tabela."""
    if is_open(tenant_id, now) is not False:
        return ""
    abertura = next_opening(tenant_id, now)
    if abertura is None:
        return ""
    agora = _to_br(now)
    delta = (abertura.date() - agora.date()).days
    if delta == 0:
        dia = "hoje"
    elif delta == 1:
        dia = "amanhã"
    else:
        nome = _DIAS[abertura.weekday()]
        dia = nome + "-feira" if abertura.weekday() < 5 else nome
    return f"{dia} às {_fmt_hora(abertura.hour, abertura.minute)}"


def cx_hours_params(tenant_id, now=None):
    """Params de sessao pro agente CX — SEMPRE as duas chaves (contrato da
    spec): fora do horario -> True + texto; aberto OU sem tabela -> False +
    vazio. O agente nao distingue "aberto" de "nao configurado" de proposito."""
    fora = is_open(tenant_id, now) is False
    return {
        "fora_do_expediente": fora,
        "retorno_previsto": retorno_previsto_text(tenant_id, now) if fora else "",
    }


def schedule_summary(tenant_id):
    """Resumo humano da tabela ("segunda a quinta das 8h às 18h e sexta das
    8h às 17h"). Vazio sem tabela. Agrupa dias consecutivos com faixas iguais."""
    sched = get_schedule(tenant_id)
    if sched is None:
        return ""
    grupos = []  # (dia_inicial, dia_final, faixas)
    for d in range(7):
        faixas = sched.get(d)
        if not faixas:
            continue
        if grupos and grupos[-1][1] == d - 1 and grupos[-1][2] == faixas:
            grupos[-1] = (grupos[-1][0], d, faixas)
        else:
            grupos.append((d, d, faixas))
    partes = []
    for ini, fim, faixas in grupos:
        dias = _DIAS[ini] if ini == fim else f"{_DIAS[ini]} a {_DIAS[fim]}"
        horas = " e ".join(
            f"das {_fmt_hora(*_parse_hhmm(a))} às {_fmt_hora(*_parse_hhmm(b))}"
            for a, b in faixas
        )
        partes.append(f"{dias} {horas}")
    return " e ".join(partes)


def builtin_expediente_notice(tenant_id, now=None):
    """Sufixo do bot builtin quando fora do horario; "" quando aberto ou sem
    tabela. Substitui o aviso hardcoded 7h-17h que morava em bot_service."""
    retorno = retorno_previsto_text(tenant_id, now)
    if not retorno:
        return ""
    return (
        f"\n\nNosso horário de atendimento: {schedule_summary(tenant_id)}.\n"
        f"Sua mensagem já está registrada — retornaremos {retorno}."
    )
