# -*- coding: utf-8 -*-
"""Migracao: classificacao inicial do funil comercial dos contatos existentes.

ADR 0015 / docs/funil_crm_varizemed.md secao 8 (decisoes do PO de
28/10/2026). Para UM tenant, da etapa (crm_stage) ao contato que ainda nao
tem, a partir de evidencia ja gravada. Nunca toca contato que ja tem etapa,
nem o que a entrada automatica (intake) ou um usuario gravarem durante a
execucao: a escrita e por contato, em transacao, relendo o contato antes de
gravar. Nunca escreve qualification: so le o desfecho antigo.

Pre-filtros (sempre): ja tem crm_stage -> pula; backup -> fora (entra ao ser
graduado); revogacao LGPD -> fora (mesma regra da entrada automatica); nunca
escreveu (sem last_inbound_at: agenda, historico sem mensagem) -> fora; canal
fora da entrada automatica do tenant (source_channel_type fora de
settings.funnel.intake_channel_types, padrao standard; ex.: contato so do
coexistence) -> fora, salvo --include-channel-types: o intake tambem o
ignora, e incluir sem pedir faria o "a alterar: 0" do rollout nunca
convergir. source_channel_type vazio = contato anterior aos canais tipados,
do canal unico de entao: conta como standard.
Campo crm_* solto sem crm_stage e anomalia: pula e reporta (nao constroi em
cima de estado quebrado).

Regras (--rules; padrao recent_untouched,in_reception,legacy_outcome;
precedencia reopen_opt_out > in_reception > recent_untouched >
legacy_outcome: o estado ATUAL vence o desfecho antigo; quem nao casa
nenhuma vai para A classificar, regra "no_rule"):
  recent_untouched (padrao) na fase do bot (o mesmo gate do webhook: sem dono
                            e sem bot_completed), qualification=novo, sem
                            first_human_contact_at, sem autor humano
                            (sender_user_id) nas ultimas 20 outbound (o
                            carimbo so nasce na promocao novo ->
                            em_atendimento: contato que nasceu em atendimento
                            e foi devolvido ao bot volta a novo sem ele) e
                            entrada >= max(agora - N dias, 02/09/2026,
                            linhagem da reforma) -> new (Novo contato).
                            Entrada = first_seen_at (webhook/manual) ou a 1a
                            inbound real (history, state_sync e outras
                            origens carimbam a sincronizacao em first_seen_at)
  in_reception (padrao)     estado ATUAL da recepcao (ex-open_human): fora da
                            fase do bot (o handoff da Val e o engajamento
                            humano carimbam bot_completed; ou ha dono), algum
                            atendimento aberto (thread fora de backup com
                            attendance_status=aberto) e ultima mensagem REAL
                            do paciente em wa_messages (sem clique de
                            avaliacao, controle admin_only e os tipos que a
                            entrada automatica ignora, como reacao e mensagem
                            de sistema) >= agora - N dias -> in_service (Em
                            atendimento), changed_at = essa mensagem (o
                            clique de avaliacao tambem sobe last_inbound_at).
                            first_human_contact_at sozinho e historico: na
                            recepcao o fechamento devolve o lead a Val (sem
                            dono e sem bot_completed), e o desfecho gravado
                            nele e mais novo que a conversa
  legacy_outcome (padrao)   desfecho registrado no Encerrar atendimento
                            (decisao 3 do PO): convertido -> scheduled,
                            nao_convertido -> non_converted (motivo
                            not_informed), nao_qualificado -> disqualified,
                            qualificado -> unclassified (contado a parte: o
                            PO juntou Qualificado e Convertido em Cliente
                            Agendado, e o registro antigo nao diz se a pessoa
                            marcou consulta)
  reopen_opt_out (opt-in)   clicou Encerrar (reopen_opt_out), sem mensagem do
                            paciente depois de reopen_opt_out_at (+5 min),
                            sem desfecho registrado (o legacy_outcome cuida:
                            Nao qualificado nao vira Nao convertido e
                            Qualificado pode ter marcado consulta),
                            bot_outcome fora de agendado/link_enviado, sem
                            recusa comercial ativa (commercial_contact_block;
                            registro invalido conta como ativa) e NENHUMA
                            outbound com o link de agendamento
                            (REOPEN_DESFECHO_LINK) em QUALQUER ciclo (stream
                            limitado; truncado nao casa) -> non_converted,
                            motivo not_informed (nunca um motivo selecionavel)
Recusa comercial, recusa LGPD e silencio nao tem regra: sem outra, vao para
A classificar. O relatorio mostra a qualification por regra, as
sobreposicoes, os CONFLITOS desfecho antigo x estado atual (o in_reception
venceu um desfecho registrado), os desfechos aplicados separados pela
reforma das qualificacoes de 02/09/2026 (o qualification nao tem data: vale
a ultima mensagem do contato), por que cada regra nao foi aplicada a quem
passou nas condicoes do proprio contato e, por regra vencedora, os contatos
com recusa comercial ativa e os com last_inbound_at depois de last_message_at
(sinal de clique de controle), para a revisao com o PO; e a contagem por
tipo de canal.

Gravacao (so campos crm_* no contato, transaction.set merge): crm_stage,
version 1, changed_at = ultima mensagem do paciente (last_inbound_at coerido;
em in_reception, a ultima inbound real; senao first_seen_at; sempre datetime
UTC), source migration, activity_id, entered_at (first_seen_at para criado
por webhook/manual; para history, state_sync e outras origens, a 1a inbound
real numa query limitada de wa_messages), cohort (mes de entered_at no fuso
da clinica) e max_order. Na mesma transacao, Activity crm_stage_migrated com
id stage_mig_<sha256(tenant|contato|ruleset)> via create (ja existe = replay,
nada regravado); data.source_qualification guarda o desfecho lido. O ruleset
inclui as regras ligadas e a janela: desfazer e rodar de novo com OUTRAS
regras reclassifica; com as mesmas, o contato revertido aparece como
revertido_antes e nao e regravado.

Seguranca:
  - exige FIRESTORE_PROJECT_ID e FIRESTORE_COLLECTION_PREFIX explicitos (no
    ambiente ou no .env): staging e prod compartilham o projeto e so o prefixo
    os separa; o padrao do config e o prefixo de PRODUCAO;
  - dry-run por padrao: escrita TRAVADA no cliente antes da 1a leitura; o
    dry-run le o mesmo que o --yes (inclusive mensagens) e mostra "a alterar";
  - undo JSONL em logs/ (fora do git; so ids) gravado ANTES de cada escrita;
    --undo ARQ [--yes] reverte so onde crm_stage_source=migration e versao,
    etapa e Activity sao as gravadas (ninguem mudou depois), em transacao,
    removendo os campos crm_* e criando crm_stage_migration_reverted;
  - relatorio agregado SEM PII (nada de nome, telefone, wa_id ou texto de
    mensagem); ids numericos de contato so com --sample; erro de leitura no
    meio da execucao imprime o relatorio parcial antes de sair com 1;
  - --rate limita os contatos candidatos por segundo (leituras extras +
    transacao); relogio unico para a execucao inteira.

Rollout (doc secao 8): dry-run e revisao com o PO -> --yes no varizemed-test e
depois na varizemed -> habilitar o tenant (scripts.set_tenant_funnel) -> novo
dry-run ate "a alterar: 0". Reaplicar contatos revertidos pelo --undo exige
trocar RULESET_VERSION (mudanca na semantica de uma regra) ou o conjunto de
regras/janela (--rules, --recent-days): com o mesmo ruleset eles aparecem
como revertido_antes e ficam sem etapa.

Uso (PowerShell, raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"     # ou castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --template clinic_v1
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --template clinic_v1 --rules recent_untouched,in_reception,legacy_outcome,reopen_opt_out --sample 5
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --template clinic_v1 --include-channel-types coexistence
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --template clinic_v1 --yes
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --undo logs/funnel_migration_undo_varizemed-test_<stamp>.jsonl
  ./.venv/Scripts/python.exe -m scripts.classify_funnel_stage --tenant varizemed-test --undo logs/<arquivo>.jsonl --yes

Exit 0 ok / 1 erro (alguma leitura ou escrita falhou) / 2 abortado (pre-checagem
recusou, nada gravado; ou interrompido, e o que ja foi gravado esta no undo).
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import funnel_catalog as fc  # noqa: E402  (modulo puro: nenhum Firestore no import)

LOGS_DIR = ROOT / "logs"
# Muda quando a semantica das regras muda (vai para o id da Activity).
# 2026-10-26: recusa comercial fora do reopen_opt_out, outbound humano e
# entrada real no recent_untouched, inbound real no open_human.
# 2026-10-28 (decisoes do PO): open_human virou in_reception (estado atual da
# recepcao, ligada); legacy_outcome aproveita o desfecho registrado (ligada);
# recent_untouched so na fase do bot; reopen_opt_out nao passa por cima de
# desfecho registrado; request_welcome conta como mensagem do paciente.
RULESET_VERSION = "2026-10-28"
RULES = ("recent_untouched", "in_reception", "legacy_outcome", "reopen_opt_out")
# O estado atual (Encerrar do paciente, recepcao, fase do bot) vence o
# desfecho antigo. recent_untouched x in_reception (fase do bot) e
# reopen_opt_out x legacy_outcome (desfecho registrado) sao disjuntas por
# construcao; a ordem decide reopen_opt_out x in_reception e in_reception x
# legacy_outcome (este, conflito reportado).
PRECEDENCE = ("reopen_opt_out", "in_reception", "recent_untouched", "legacy_outcome")
DEFAULT_RULES = ("recent_untouched", "in_reception", "legacy_outcome")
# Nome antigo -> atual: recusado com a dica (nada foi publicado com o antigo).
RENAMED_RULES = {"open_human": "in_reception"}
NO_RULE = "no_rule"
LEGACY_RULE = "legacy_outcome"
# regra -> (etapa, motivo, confianca)
RULE_TARGETS = {
    "recent_untouched": (fc.ENTRY_STAGE, None, "high"),
    "in_reception": ("in_service", None, "medium"),
    "reopen_opt_out": ("non_converted", "not_informed", "medium"),
    NO_RULE: (fc.TRIAGE_STAGE, None, "low"),
}
# legacy_outcome (decisao 3 do PO, 28/10): desfecho do Encerrar atendimento ->
# etapa. O motivo real nunca foi registrado (not_informed, nao selecionavel).
# Qualificado nao tem equivalente: o PO juntou Qualificado e Convertido em
# Cliente Agendado e o registro antigo nao diz se a pessoa marcou consulta
# (A classificar, contado a parte no relatorio).
LEGACY_OUTCOME_TARGETS = {
    "convertido": ("scheduled", None, "medium"),
    "nao_convertido": ("non_converted", "not_informed", "medium"),
    "nao_qualificado": ("disqualified", None, "medium"),
    "qualificado": (fc.TRIAGE_STAGE, None, "low"),
}
# Periodo do desfecho antigo no relatorio, pela reforma das qualificacoes
# (LINEAGE_START). O qualification nao tem data: vale a ultima mensagem.
PERIOD_BEFORE = "antes_da_reforma"
PERIOD_AFTER = "depois_da_reforma"
PERIOD_UNKNOWN = "sem_data"
DEFAULT_RECENT_DAYS = 30
# Reforma da qualification (2026-09): so a partir dela "novo" significa "sem
# interacao humana" de forma confiavel.
LINEAGE_START = datetime(2026, 9, 2, tzinfo=fc.BR_TZ)
# O clique no Encerrar e ele mesmo uma inbound; folga para o carimbo.
OPT_OUT_TOLERANCE = timedelta(minutes=5)
BOOKED_OUTCOMES = ("agendado", "link_enviado")
# first_seen_at so e a entrada real quando o contato nasceu de mensagem ao
# vivo ou pelo operador; agenda/historico/importacao carimbam a sincronizacao.
TRUSTED_SOURCES = ("", "webhook", "manual")
# Contato anterior aos canais tipados (source_channel_type vazio) veio do
# canal unico de entao, o standard.
LEGACY_CHANNEL_TYPE = "standard"
# Inbound que nao e mensagem do paciente: os tipos que a entrada automatica
# ignora (webhook._FUNNEL_INTAKE_SKIP_TYPES; o sim confere que nao divergem),
# alem do clique de avaliacao (is_rating_message) e do controle (admin_only).
# Midia que a Cloud API nao interpreta (unsupported, ephemeral) E mensagem; a
# abertura do chat (request_welcome) tambem, desde a decisao do PO de 28/10.
INBOUND_CONTROL_TYPES = frozenset({"reaction", "system", "unknown"})
PAGE_SIZE = 300
OUTBOUND_SCAN = 300
OUTBOUND_HUMAN_SCAN = 20
INBOUND_SCAN = 200
INBOUND_REAL_SCAN = 20
THREAD_SCAN = 50
MAX_RATE = 200.0
MAX_SAMPLE = 1000
MAX_ONLY = 1000
MAX_CONSECUTIVE_ERRORS = 10
PROGRESS_EVERY = 1000
AUSENTE = "__AUSENTE__"
ACTIVITY_PREFIX = "stage_mig_"
REVERT_PREFIX = "stage_migrev_"
UNDO_FORMAT = 1
# Entradas da classificacao: se mudarem entre a leitura da pagina e a
# transacao, o contato e pulado (rodar de novo resolve).
CLASSIFY_FIELDS = ("qualification", "first_human_contact_at", "first_seen_at", "last_inbound_at",
                   "created_source", "reopen_opt_out", "reopen_opt_out_at", "bot_outcome",
                   "commercial_contact_block", "bot_completed", "assigned_to", "assigned_to_uid")
DATE_FIELDS = ("last_inbound_at", "first_seen_at", "first_human_contact_at", "reopen_opt_out_at")
# Descarte de regra (passou nas condicoes do contato, a evidencia recusou):
# titulo no relatorio e prefixo do balde de amostra. legacy_outcome nao le
# nada (sem descarte).
DISCARD_TITLES = {
    "reopen_opt_out": "reopen_opt_out NAO aplicado (clicou Encerrar, mas):",
    "in_reception": "in_reception NAO aplicado (fora da fase do bot e last_inbound_at na janela, mas):",
    "recent_untouched": "recent_untouched NAO aplicado (novo, sem 1o contato humano e com inbound, mas):",
}
DISCARD_SAMPLE = {"reopen_opt_out": "opt_out_", "in_reception": "in_reception_",
                  "recent_untouched": "recent_untouched_"}

_TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_ACTIVITY_RE = re.compile(r"^stage_mig_[0-9a-f]{64}$")

# Pontos de troca do simulador (relogio de parede do ritmo).
_sleep = time.sleep
_monotonic = time.monotonic


class Recusa(Exception):
    """Pre-checagem recusou: nada gravado (exit 2)."""


def _agora():
    return datetime.now(timezone.utc)


def trava_escrita():
    """Dry-run: cliente Firestore so-leitura NESTE processo, antes da 1a
    leitura. Inclui o commit interno das transacoes (_commit, que e o que o
    @firestore.transactional chama na 2.x; travar so commit() nao basta)."""
    from google.cloud.firestore_v1 import batch, collection, document, transaction

    def _bloqueado(*_a, **_k):
        raise RuntimeError("dry-run: escrita no Firestore bloqueada")

    alvos = [
        (document.DocumentReference, ("set", "update", "delete", "create")),
        (collection.CollectionReference, ("add",)),
        (batch.WriteBatch, ("set", "update", "delete", "create", "commit")),
        (transaction.Transaction, ("set", "update", "delete", "create", "commit", "_commit")),
    ]
    try:
        from google.cloud.firestore_v1 import bulk_writer
        alvos.append((bulk_writer.BulkWriter, ("set", "update", "delete", "create")))
    except ImportError:  # pragma: no cover - versao sem BulkWriter
        pass
    for cls, nomes in alvos:
        for nome in nomes:
            if hasattr(cls, nome):
                setattr(cls, nome, _bloqueado)


def _stdout_seguro():
    for fluxo in (sys.stdout, sys.stderr):
        reconfigure = getattr(fluxo, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _ambiente():
    """(projeto, prefixo) que o cliente vai usar, ou None com erro claro.
    Os dois precisam vir explicitos do ambiente; o .env conta, porque o
    config o carrega no import (antes da checagem). Staging e prod
    compartilham o projeto e so o prefixo os separa: o padrao do config e
    o prefixo de PRODUCAO, entao nao serve de fallback."""
    import config
    projeto = str(getattr(config, "FIRESTORE_PROJECT_ID", "") or "").strip()
    if not projeto:
        print("ERRO: defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente. "
              "Sem ele o cliente cairia no projeto padrao do gcloud, que aponta para o projeto "
              "ERRADO. Nada foi lido nem gravado.", file=sys.stderr)
        return None
    if "FIRESTORE_COLLECTION_PREFIX" not in os.environ:
        print("ERRO: defina FIRESTORE_COLLECTION_PREFIX no ambiente (castro_crm = producao, "
              "castro_crm_staging = staging). Sem ele o config cai no prefixo de PRODUCAO, e "
              "staging e prod compartilham o projeto. Nada foi lido nem gravado.", file=sys.stderr)
        return None
    return projeto, str(getattr(config, "FIRESTORE_COLLECTION_PREFIX", "") or "")


def _onde(exc):
    """arquivo:linha do erro, sem a mensagem (pode carregar valores)."""
    quadros = traceback.extract_tb(exc.__traceback__)
    if not quadros:
        return "?"
    ultimo = quadros[-1]
    return "%s:%s" % (Path(ultimo.filename).name, ultimo.lineno)


def _iso(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return str(valor)


def _texto(valor):
    return str(valor or "").strip()


def _inteiro(valor):
    if isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _tenant(valor):
    if not _TENANT_RE.match(valor or ""):
        raise argparse.ArgumentTypeError("tenant invalido: use letras, numeros, '_' ou '-'")
    return valor


def _sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ruleset_version(regras, dias):
    ligadas = "+".join(r for r in RULES if r in regras)
    return "%s:%s:%dd" % (RULESET_VERSION, ligadas, dias)


def activity_id(tenant_id, contact_id, ruleset):
    return ACTIVITY_PREFIX + _sha("|".join((tenant_id, str(contact_id), ruleset)))


def revert_id(tenant_id, contact_id, migrated_id):
    return REVERT_PREFIX + _sha("|".join((tenant_id, str(contact_id), migrated_id)))


def _fingerprint(contact_id, payload):
    texto = json.dumps({"contact_id": contact_id, "payload": payload}, sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False, default=_iso)
    return _sha(texto)


def tipo_de_data(valor):
    """Anomalia de tipo de um campo de data, ou None (ausente ou datetime)."""
    if valor is None or valor == "" or isinstance(valor, datetime):
        return None
    if isinstance(valor, str):
        return "texto_iso_coerido" if fc.as_utc(valor) else "texto_invalido"
    return "tipo_inesperado"


# ---------------------------------------------------------------------------
# Regras (puras; as leituras vem pelos callbacks de `consultas`)
# ---------------------------------------------------------------------------

def _e_backup(contato):
    return bool(contato.get("is_backup")) or contato.get("assigned_to_uid") == "__backup__"


def na_fase_do_bot(contato):
    """O mesmo gate do bot no webhook: a Val so conversa com contato sem dono
    e sem bot_completed. O handoff e o engajamento humano carimbam
    bot_completed; na recepcao o fechamento (manual, cron ou Encerrar do
    paciente) devolve o lead a Val (bot_completed falso e sem dono)."""
    return (not contato.get("bot_completed") and not contato.get("assigned_to")
            and not _texto(contato.get("assigned_to_uid")))


def destino_da_regra(regra, contato):
    """(etapa, motivo, confianca) da regra vencedora."""
    if regra == LEGACY_RULE:
        return LEGACY_OUTCOME_TARGETS[_texto(contato.get("qualification"))]
    return RULE_TARGETS[regra]


def periodo_do_desfecho(contato):
    """Desfecho antigo antes ou depois da reforma das qualificacoes
    (LINEAGE_START). O qualification nao tem data: vale a ultima mensagem do
    contato, em qualquer direcao (sem nenhuma depois da reforma, o desfecho
    foi registrado antes dela)."""
    datas = [d for d in (fc.as_utc(contato.get("last_message_at")),
                         fc.as_utc(contato.get("last_inbound_at"))) if d is not None]
    if not datas:
        return PERIOD_UNKNOWN
    return PERIOD_BEFORE if max(datas) < LINEAGE_START else PERIOD_AFTER


def tipo_de_canal(contato):
    """source_channel_type do contato (tipo do 1o canal dele); vazio = legado."""
    return _texto(contato.get("source_channel_type")) or LEGACY_CHANNEL_TYPE


def tipo_exibido(contato):
    """Rotulo do tipo de canal no relatorio (o vazio aparece como tal)."""
    tipo = _texto(contato.get("source_channel_type"))
    return tipo if tipo else "(vazio=%s)" % LEGACY_CHANNEL_TYPE


def prefiltro(contato, tenant_id, canais):
    """Causa de ficar fora da migracao, ou None. `canais` = tipos de canal
    aceitos (entrada automatica do tenant + --include-channel-types)."""
    if contato.get("tenant_id") not in (None, "", tenant_id):
        return "tenant_divergente"
    if contato.get(fc.F_STAGE):
        return "ja_tem_etapa"
    if any(campo in contato for campo in fc.CONTACT_STAGE_FIELDS):
        return "campos_crm_sem_etapa"
    if _e_backup(contato):
        return "backup"
    if contato.get("lgpd_revoked"):
        return "lgpd_revogado"
    if not contato.get("last_inbound_at"):
        return "sem_inbound"
    if tipo_de_canal(contato) not in canais:
        return "canal_fora_da_entrada"
    return None


def recusa_comercial_ativa(contato):
    """Predicado puro do follow-up: registro invalido tambem bloqueia."""
    from commercial_contact_policy import is_commercial_contact_blocked
    return is_commercial_contact_blocked(contato)


def sinal_de_clique(contato):
    """last_inbound_at depois de last_message_at: o clique de avaliacao renova
    a janela de 24h sem avancar a recencia (sinal barato, sem leitura)."""
    inbound = fc.as_utc(contato.get("last_inbound_at"))
    mensagem = fc.as_utc(contato.get("last_message_at"))
    return inbound is not None and mensagem is not None and inbound > mensagem


def evidencia_de(contato, agora):
    """(datetime UTC da evidencia, anomalia|None) ou (None, causa).
    Ultima mensagem do paciente; data ilegivel cai no first_seen_at."""
    evidencia = fc.as_utc(contato.get("last_inbound_at"))
    anomalia = None
    if evidencia is None:
        evidencia = fc.as_utc(contato.get("first_seen_at"))
        if evidencia is None:
            return None, "data_ilegivel"
        anomalia = "evidencia_por_first_seen_at"
    if evidencia > agora:
        return agora, "data_futura_limitada_a_agora"
    return evidencia, anomalia


def descarte_opt_out(contato, link_enviado):
    """Motivo de o reopen_opt_out NAO casar, ou None (casa). link_enviado()
    -> (achou, truncado) so roda quando as condicoes baratas passam."""
    encerrou = fc.as_utc(contato.get("reopen_opt_out_at"))
    if encerrou is None:
        return "sem_data_do_encerrar"
    inbound = fc.as_utc(contato.get("last_inbound_at"))
    if inbound is None:
        return "inbound_ilegivel"
    if inbound > encerrou + OPT_OUT_TOLERANCE:
        return "mensagem_depois_do_encerrar"
    if _texto(contato.get("qualification")) in LEGACY_OUTCOME_TARGETS:
        # Desfecho registrado pela equipe diz mais que o clique, qualquer que
        # seja a ordem (a retomada pontual nao filtra qualification): Nao
        # qualificado nao vira Nao convertido e Qualificado pode ter marcado
        # consulta. O legacy_outcome cuida dele.
        return "desfecho_registrado"
    if _texto(contato.get("bot_outcome")) in BOOKED_OUTCOMES:
        return "desfecho_de_agendamento"
    # Recusa comercial nunca vira Nao convertido (ADR 0015 secao 8): vai para
    # A classificar. Registro invalido tambem bloqueia (lado seguro).
    if recusa_comercial_ativa(contato):
        return "recusa_comercial"
    achou, truncado = link_enviado()
    if achou:
        return "link_de_agendamento_enviado"
    if truncado:
        return "historico_truncado"
    return None


def descarte_in_reception(corte, consultas):
    """Motivo de o in_reception NAO casar depois das condicoes baratas (fora
    da fase do bot e last_inbound_at na janela), ou None. As threads (poucas
    por contato) sao lidas antes das mensagens."""
    if not consultas.atendimento_aberto():
        # Fechamento sem devolver a Val (modo legado) ou thread so de backup.
        return "sem_atendimento_aberto"
    ultima, _cheia = consultas.ultima_inbound_real()
    if ultima is None:
        return "sem_inbound_real"
    if ultima < corte:
        # last_inbound_at na janela so por clique de avaliacao/controle,
        # reacao ou mensagem de sistema.
        return "inbound_real_fora_da_janela"
    return None


def descarte_recente(contato, consultas):
    """Motivo de o recent_untouched NAO casar depois da janela de entrada, ou
    None: fora da fase do bot (handoff, dono ou engajamento humano; quem
    decide e o in_reception) ou autor humano nas ultimas outbound."""
    if not na_fase_do_bot(contato):
        return "fora_da_fase_do_bot"
    return "outbound_humano" if consultas.outbound_humano() else None


def _origem_confiavel(contato):
    return _texto(contato.get("created_source")) in TRUSTED_SOURCES


def avaliar_regras(contato, agora, regras, dias, consultas, evidencia):
    """(regras que casam, na ordem de precedencia; {regra: causa} das que
    passaram nas condicoes baratas do contato, mas a evidencia lida recusou).
    As leituras de `consultas` (link_enviado, atendimento_aberto,
    ultima_inbound_real, outbound_humano, primeira_inbound) so rodam depois
    das condicoes baratas de cada regra."""
    casadas, descartes = [], {}
    corte = agora - timedelta(days=dias)
    qualificacao = _texto(contato.get("qualification"))

    def decidir(regra, causa):
        if causa is None:
            casadas.append(regra)
        else:
            descartes[regra] = causa

    if "reopen_opt_out" in regras and contato.get("reopen_opt_out"):
        decidir("reopen_opt_out", descarte_opt_out(contato, consultas.link_enviado))
    inbound = fc.as_utc(contato.get("last_inbound_at"))
    if ("in_reception" in regras and not na_fase_do_bot(contato)
            and inbound is not None and inbound >= corte):
        decidir("in_reception", descarte_in_reception(corte, consultas))
    if ("recent_untouched" in regras and qualificacao == "novo"
            and not contato.get("first_human_contact_at") and contato.get("last_inbound_at")):
        piso = max(corte, LINEAGE_START)
        if _origem_confiavel(contato):
            visto = fc.as_utc(contato.get("first_seen_at"))
            if visto is not None and visto >= piso:  # senao: condicao barata, nao e descarte
                decidir("recent_untouched", descarte_recente(contato, consultas))
        else:
            # first_seen_at de history/state_sync/importacao e o carimbo da
            # sincronizacao: a recencia e a da entrada real (1a inbound), a
            # mesma que vai para crm_funnel_entered_at.
            entrada, _tipo = data_de_entrada(contato, evidencia, consultas)
            if entrada < piso:
                decidir("recent_untouched", "entrada_real_fora_da_janela")
            else:
                decidir("recent_untouched", descarte_recente(contato, consultas))
    if LEGACY_RULE in regras and qualificacao in LEGACY_OUTCOME_TARGETS:
        decidir(LEGACY_RULE, None)
    casadas.sort(key=PRECEDENCE.index)
    return casadas, descartes


# ---------------------------------------------------------------------------
# Leituras auxiliares (wa_messages; indice contact_id+direction+timestamp_wa)
# ---------------------------------------------------------------------------

class Leitores:
    def __init__(self, tenant_id, trecho, relatorio):
        self.tenant_id = tenant_id
        self.trecho = trecho
        self.rel = relatorio

    def _mensagens(self, contact_id, direcao, limite):
        from google.cloud.firestore_v1.base_query import FieldFilter
        from firestore_common import tenant_collection
        consulta = (tenant_collection(self.tenant_id, "wa_messages")
                    .where(filter=FieldFilter("contact_id", "==", contact_id))
                    .where(filter=FieldFilter("direction", "==", direcao))
                    .order_by("timestamp_wa", direction="DESCENDING")
                    .limit(limite))
        return [snap.to_dict() or {} for snap in consulta.stream()]

    def link_enviado(self, contact_id):
        """(achou, truncado). Qualquer outbound do contato, de qualquer ciclo
        e de qualquer autor (Val ou equipe): lado seguro do 'nao converteu'."""
        limite = OUTBOUND_SCAN
        linhas = self._mensagens(contact_id, "outbound", limite)
        achou = any(self.trecho in str(m.get("content") or "").lower() for m in linhas)
        return achou, (not achou and len(linhas) >= limite)

    def atendimento_aberto(self, contact_id):
        """Alguma thread do contato fora de backup com attendance_status
        aberto (o fechamento manual, o cron e o Encerrar do paciente gravam
        fechado_*). Igualdade em campo unico: indice automatico."""
        from google.cloud.firestore_v1.base_query import FieldFilter
        from firestore_common import tenant_collection
        consulta = (tenant_collection(self.tenant_id, "wa_conversations")
                    .where(filter=FieldFilter("contact_id", "==", contact_id))
                    .limit(THREAD_SCAN))
        for snap in consulta.stream():
            conversa = snap.to_dict() or {}
            if not conversa.get("is_backup") and conversa.get("attendance_status") == "aberto":
                return True
        return False

    def outbound_humano(self, contact_id):
        """Alguma das ultimas OUTBOUND_HUMAN_SCAN outbound tem autor humano
        (sender_user_id; o bot grava None)? first_human_contact_at so nasce
        na promocao novo -> em_atendimento, entao a ausencia do carimbo nao
        prova ausencia de humano."""
        linhas = self._mensagens(contact_id, "outbound", OUTBOUND_HUMAN_SCAN)
        return any(m.get("sender_user_id") not in (None, "") for m in linhas)

    def ultima_inbound_real(self, contact_id):
        """(maior timestamp_wa entre as ultimas INBOUND_REAL_SCAN inbound que
        sao mensagem do paciente, janela cheia). Fora: clique de avaliacao
        (is_rating_message), controle (visibility admin_only) e os tipos que
        a entrada automatica ignora (INBOUND_CONTROL_TYPES)."""
        linhas = self._mensagens(contact_id, "inbound", INBOUND_REAL_SCAN)
        datas = []
        for mensagem in linhas:
            if (mensagem.get("is_rating_message") or mensagem.get("visibility") == "admin_only"
                    or _texto(mensagem.get("msg_type")) in INBOUND_CONTROL_TYPES):
                continue
            momento = fc.as_utc(mensagem.get("timestamp_wa"))
            if momento is not None:
                datas.append(momento)
        return (max(datas) if datas else None), len(linhas) >= INBOUND_REAL_SCAN

    def primeira_inbound(self, contact_id):
        """(menor timestamp_wa das inbound lidas, aproximada). O indice existe
        so em DESC: lida a janela limitada; cheia = aproximacao por cima."""
        limite = INBOUND_SCAN
        linhas = self._mensagens(contact_id, "inbound", limite)
        datas = []
        for mensagem in linhas:
            valor = mensagem.get("timestamp_wa")
            tipo = tipo_de_data(valor)
            if tipo:
                self.rel.datas[("timestamp_wa", tipo)] += 1
            momento = fc.as_utc(valor)
            if momento is not None:
                datas.append(momento)
        if not datas:
            return None, False
        return min(datas), len(linhas) >= limite


class Consultas:
    """Leituras auxiliares de UM contato: cada uma roda no maximo uma vez (a
    regra e a gravacao reaproveitam o resultado) e so quando as condicoes
    baratas da regra passam."""

    def __init__(self, leitores, contact_id):
        self._leitores = leitores
        self._contact_id = contact_id
        self._memo = {}

    def _uma_vez(self, nome):
        if nome not in self._memo:
            self._memo[nome] = getattr(self._leitores, nome)(self._contact_id)
        return self._memo[nome]

    def link_enviado(self):
        return self._uma_vez("link_enviado")

    def atendimento_aberto(self):
        return self._uma_vez("atendimento_aberto")

    def outbound_humano(self):
        return self._uma_vez("outbound_humano")

    def ultima_inbound_real(self):
        return self._uma_vez("ultima_inbound_real")

    def primeira_inbound(self):
        return self._uma_vez("primeira_inbound")


def data_de_entrada(contato, evidencia, consultas):
    """(crm_funnel_entered_at, como foi obtida)."""
    if _origem_confiavel(contato):
        entrada = fc.as_utc(contato.get("first_seen_at"))
        tipo = "first_seen_at"
    else:
        entrada, aproximada = consultas.primeira_inbound()
        tipo = "primeira_inbound_aproximada" if aproximada else "primeira_inbound"
        if entrada is None:
            entrada = fc.as_utc(contato.get("first_seen_at"))
            tipo = "first_seen_at_sem_inbound_registrada"
    if entrada is None:
        return evidencia, "evidencia"
    if entrada > evidencia:
        # Ninguem entra no funil depois de entrar na etapa atual.
        return evidencia, tipo + "_limitada_a_evidencia"
    return entrada, tipo


def planejar(contato, contact_id, ctx, leitores, evidencia):
    """Plano de escrita do contato (sem I/O alem das leituras auxiliares)."""
    agora, tenant_id = ctx["agora"], ctx["tenant"]
    consultas = Consultas(leitores, contact_id)
    casadas, descartes = avaliar_regras(contato, agora, ctx["regras"], ctx["dias"],
                                        consultas, evidencia)
    regra = casadas[0] if casadas else NO_RULE
    etapa, motivo, confianca = destino_da_regra(regra, contato)
    qualificacao = _texto(contato.get("qualification"))
    # Desfecho antigo vencido pelo estado atual: conflito para a revisao.
    conflito = None
    if LEGACY_RULE in casadas and regra != LEGACY_RULE:
        conflito = (regra, qualificacao, LEGACY_OUTCOME_TARGETS[qualificacao][0])
    periodo = periodo_do_desfecho(contato) if (regra == LEGACY_RULE or conflito) else None
    anomalia = None
    if regra == "in_reception":
        # Evidencia = ultima mensagem REAL do paciente (ja lida pela regra):
        # o clique de avaliacao sobe last_inbound_at sem ser conversa.
        evidencia, _cheia = consultas.ultima_inbound_real()
        if evidencia > agora:
            evidencia, anomalia = agora, "inbound_real_futura_limitada_a_agora"
    entrada, tipo_entrada = data_de_entrada(contato, evidencia, consultas)
    act_id = activity_id(tenant_id, contact_id, ctx["ruleset"])
    campos = {
        fc.F_STAGE: etapa,
        fc.F_VERSION: 1,
        fc.F_CHANGED_AT: evidencia,
        fc.F_SOURCE: fc.SOURCE_MIGRATION,
        fc.F_ACTIVITY: act_id,
        fc.F_BY_USER: None,
        fc.F_BY_UID: "",
        fc.F_ENTERED_AT: entrada,
        fc.F_COHORT: fc.cohort_month(entrada),
        fc.F_MAX_ORDER: fc.next_max_order(ctx["catalogo"], None, etapa),
    }
    atividade = {
        "id": act_id, "tenant_id": tenant_id, "contact_id": contact_id,
        "task_id": None, "conversation_id": None,
        "event_type": fc.EVENT_MIGRATED, "actor_type": "migration",
        "actor_user_id": None, "actor_uid": "",
        "occurred_at": agora, "recorded_at": agora, "operation_id": ctx["run_id"],
        "request_fingerprint": _fingerprint(contact_id, {
            "to_stage": etapa, "stage_reason": motivo, "rule_id": regra,
            "ruleset_version": ctx["ruleset"]}),
        "result_version": 1,
        "from_stage": None, "to_stage": etapa, "stage_reason": motivo,
        "from_reason": None, "entry_kind": None,
        "data": {"stage_version": 1, "source": fc.SOURCE_MIGRATION, "rule_id": regra,
                 "ruleset_version": ctx["ruleset"], "evidence_at": evidencia,
                 "confidence": confianca,
                 # Desfecho lido (so o vocabulario conhecido); nunca regravado.
                 "source_qualification": (qualificacao if qualificacao in fc.LEGACY_QUALIFICATIONS
                                          else None)},
    }
    return {"rule": regra, "stage": etapa, "reason": motivo, "matched": casadas,
            "discards": descartes, "anomaly": anomalia, "entry_kind": tipo_entrada,
            "conflict": conflito, "period": periodo,
            "activity_id": act_id, "fields": campos, "activity": atividade}


# ---------------------------------------------------------------------------
# Relatorio e ritmo
# ---------------------------------------------------------------------------

class Relatorio:
    def __init__(self, amostra):
        self.amostra = amostra
        self.lidos = 0
        self.candidatos = 0
        self.pulados = Counter()
        self.plano = Counter()
        self.qualificacao = Counter()
        self.sobreposicao = Counter()
        self.descarte = Counter()   # (regra, causa)
        self.canais = Counter()     # (tipo exibido, situacao)
        self.recusa = Counter()     # regra vencedora
        self.clique = Counter()     # regra vencedora
        self.legado = Counter()     # (desfecho, etapa, periodo) do legacy_outcome aplicado
        self.conflito = Counter()   # (vencedora, desfecho, etapa que seria, periodo)
        self.entrada = Counter()
        self.datas = Counter()
        self.anomalias = Counter()
        self.resultado = Counter()
        self.erros = Counter()
        self.ids = defaultdict(list)
        self.parou = None

    def guardar_id(self, balde, contact_id):
        if self.amostra and contact_id is not None and len(self.ids[balde]) < self.amostra:
            self.ids[balde].append(contact_id)

    def contar_datas(self, contato):
        for campo in DATE_FIELDS:
            tipo = tipo_de_data(contato.get(campo))
            if tipo:
                self.datas[(campo, tipo)] += 1


class Ritmo:
    """No maximo `taxa` contatos candidatos por segundo."""

    def __init__(self, taxa):
        self.intervalo = 1.0 / float(taxa)
        self.proximo = None

    def esperar(self):
        agora = _monotonic()
        if self.proximo is not None and agora < self.proximo:
            _sleep(self.proximo - agora)
            agora = self.proximo
        self.proximo = agora + self.intervalo


def _bloco(contador, recuo=2):
    if not contador:
        print(" " * recuo + "(nenhum)")
        return
    # Coluna do tamanho da maior chave do bloco (chave longa nao desalinha).
    largura = max([46] + [len(str(chave)) for chave in contador])
    for chave, n in sorted(contador.items()):
        print("%s%-*s %7d" % (" " * recuo, largura, chave, n))


def imprimir_relatorio(rel, gravando):
    print("\n=== Relatorio (%s) ===" % ("GRAVACAO" if gravando else "DRY-RUN"))
    print("contatos lidos: %d" % rel.lidos)
    print("fora da migracao (pre-filtros):")
    _bloco(rel.pulados)
    if rel.canais:
        print("tipo de canal (source_channel_type) dos que escreveram:")
        _bloco({"%s: %s" % chave: n for chave, n in rel.canais.items()})
    print("candidatos (sem etapa): %d" % rel.candidatos)
    print("classificacao (regra -> etapa [motivo]):")
    _bloco({"%s -> %s%s" % (regra, etapa, " [%s]" % motivo if motivo else ""): n
            for (regra, etapa, motivo), n in rel.plano.items()})
    if rel.qualificacao:
        print("  qualification por regra:")
        _bloco({"%s / %s" % chave: n for chave, n in rel.qualificacao.items()}, recuo=4)
    if rel.sobreposicao:
        print("  tambem casariam (regra vencedora / outra regra ligada):")
        _bloco({"%s / %s" % chave: n for chave, n in rel.sobreposicao.items()}, recuo=4)
    if rel.legado:
        print("legacy_outcome aplicado (desfecho -> etapa / periodo pela ultima mensagem do contato; "
              "reforma das qualificacoes em %s):" % LINEAGE_START.date().isoformat())
        _bloco({"%s -> %s / %s" % chave: n for chave, n in rel.legado.items()})
        print("qualificado (decisao 3: A classificar, contado a parte): %d" % sum(
            n for (desfecho, _etapa, _periodo), n in rel.legado.items() if desfecho == "qualificado"))
    if rel.conflito:
        print("conflitos desfecho antigo x estado atual (prevaleceu o estado atual; revisar com o PO):")
        _bloco({"%s: %s (seria %s) / %s" % chave: n for chave, n in rel.conflito.items()})
    for regra in PRECEDENCE:
        causas = {causa: n for (dona, causa), n in rel.descarte.items() if dona == regra}
        if causas:
            print(DISCARD_TITLES.get(regra, regra + " NAO aplicado:"))
            _bloco(causas)
    if rel.recusa:
        print("recusa comercial ativa (registro invalido conta como ativa), por regra vencedora:")
        _bloco(rel.recusa)
    if rel.clique:
        print("last_inbound_at depois de last_message_at (sinal de clique de controle), "
              "por regra vencedora:")
        _bloco(rel.clique)
    if rel.entrada:
        print("crm_funnel_entered_at obtida por:")
        _bloco(rel.entrada)
    if rel.anomalias:
        print("anomalias:")
        _bloco(rel.anomalias)
    if rel.datas:
        print("datas fora do tipo datetime (gravacao sempre coerida para datetime UTC):")
        _bloco({"%s: %s" % chave: n for chave, n in rel.datas.items()})
    print("resultado:")
    _bloco(rel.resultado)
    alterar = rel.resultado.get("gravado" if gravando else "a_alterar", 0)
    print("a alterar%s: %d" % (" (gravados)" if gravando else "", alterar))
    revertidos = rel.resultado.get("revertido_antes", 0)
    if revertidos:
        print("ATENCAO: %d contato(s) revertido(s) pelo --undo seguem sem etapa: o undo e definitivo "
              "para este ruleset. Reaplicar exige trocar RULESET_VERSION ou as regras/janela "
              "(--rules, --recent-days)." % revertidos)
    if rel.erros:
        print("erros por tipo:")
        _bloco(rel.erros)
    for balde in sorted(rel.ids):
        print("amostra %s: %s" % (balde, ", ".join(str(i) for i in rel.ids[balde])))
    if rel.parou:
        print("PARADA ANTECIPADA: %s" % rel.parou)


# ---------------------------------------------------------------------------
# Undo (JSONL em logs/, so ids)
# ---------------------------------------------------------------------------

class UndoArquivo:
    """Cabecalho na 1a linha; uma linha por contato ANTES da transacao."""

    def __init__(self, caminho, cabecalho):
        self.caminho = caminho
        self.cabecalho = cabecalho
        self.linhas = 0
        self._fh = None

    def registrar(self, linha):
        if self._fh is None:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.caminho, "a", encoding="utf-8")
            self._escrever(self.cabecalho)
        self._escrever(linha)
        self.linhas += 1

    def _escrever(self, objeto):
        self._fh.write(json.dumps(objeto, sort_keys=True, ensure_ascii=True, default=_iso) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def fechar(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def linha_de_undo(ctx, contact_id, plano):
    campos = sorted(plano["fields"])
    return {"type": "contact", "tenant": ctx["tenant"], "run_id": ctx["run_id"],
            "contact_id": contact_id, "activity_id": plano["activity_id"],
            "stage": plano["stage"], "reason": plano["reason"], "rule_id": plano["rule"],
            "ruleset_version": ctx["ruleset"], "version": plano["fields"][fc.F_VERSION],
            "fields": campos, "before": {campo: AUSENTE for campo in campos}}


def _linha_valida(objeto, numero):
    contact_id = objeto.get("contact_id")
    campos = objeto.get("fields")
    anteriores = objeto.get("before")
    valido = (type(contact_id) is int and contact_id > 0
              and isinstance(objeto.get("activity_id"), str) and _ACTIVITY_RE.match(objeto["activity_id"])
              and type(objeto.get("version")) is int and objeto["version"] >= 1
              and isinstance(objeto.get("stage"), str) and _KEY_RE.match(objeto["stage"])
              and isinstance(campos, list) and campos
              and all(campo in fc.CONTACT_STAGE_FIELDS for campo in campos)
              and isinstance(anteriores, dict) and set(anteriores) == set(campos)
              and all(valor == AUSENTE for valor in anteriores.values()))
    if not valido:
        raise Recusa("undo: linha %d malformada (o arquivo foi editado?)" % numero)
    return objeto


def carregar_undo(caminho, tenant_id, projeto, prefixo):
    cabecalhos, linhas = [], []
    try:
        arquivo = open(caminho, encoding="utf-8")
    except OSError as exc:
        raise Recusa("nao foi possivel abrir o undo (%s)" % type(exc).__name__)
    with arquivo:
        for numero, bruto in enumerate(arquivo, 1):
            bruto = bruto.strip()
            if not bruto:
                continue
            try:
                objeto = json.loads(bruto)
            except ValueError:
                raise Recusa("undo: linha %d nao e JSON valido" % numero)
            tipo = objeto.get("type") if isinstance(objeto, dict) else None
            if tipo == "header":
                if objeto.get("format") != UNDO_FORMAT:
                    raise Recusa("undo: formato %r desconhecido" % objeto.get("format"))
                if objeto.get("tenant") != tenant_id:
                    raise Recusa("undo e do tenant %r, nao de %r" % (objeto.get("tenant"), tenant_id))
                if objeto.get("project") != projeto or objeto.get("prefix") != prefixo:
                    raise Recusa("undo gerado em %s/%s; o ambiente atual e %s/%s" % (
                        objeto.get("project"), objeto.get("prefix"), projeto, prefixo))
                cabecalhos.append(objeto)
            elif tipo == "contact":
                if not cabecalhos:
                    raise Recusa("undo: linha %d antes do cabecalho" % numero)
                if objeto.get("tenant") != tenant_id:
                    raise Recusa("undo: linha %d e de outro tenant" % numero)
                linhas.append(_linha_valida(objeto, numero))
            else:
                raise Recusa("undo: linha %d com tipo desconhecido" % numero)
    if not cabecalhos:
        raise Recusa("undo sem cabecalho (nao e um arquivo desta migracao)")
    return cabecalhos, linhas


def estado_para_reverter(existe, atual, ja_revertido, linha):
    """Causa de NAO reverter, ou None. So o que a propria migracao gravou e
    ninguem mudou depois (fonte, versao, etapa e Activity iguais)."""
    if not existe:
        return "contato_inexistente"
    if ja_revertido:
        return "ja_revertido"
    if (atual.get(fc.F_SOURCE) != fc.SOURCE_MIGRATION
            or _inteiro(atual.get(fc.F_VERSION)) != linha["version"]
            or atual.get(fc.F_ACTIVITY) != linha["activity_id"]
            or atual.get(fc.F_STAGE) != linha["stage"]):
        return "mudou_depois_da_migracao"
    return None


def atividade_de_reversao(ctx, linha, rid):
    agora = ctx["agora"]
    return {
        "id": rid, "tenant_id": ctx["tenant"], "contact_id": linha["contact_id"],
        "task_id": None, "conversation_id": None,
        "event_type": fc.EVENT_MIGRATION_REVERTED, "actor_type": "migration",
        "actor_user_id": None, "actor_uid": "",
        "occurred_at": agora, "recorded_at": agora, "operation_id": ctx["run_id"],
        "request_fingerprint": None, "result_version": 0,
        "from_stage": linha["stage"], "to_stage": None, "stage_reason": None,
        "from_reason": linha.get("reason"), "entry_kind": None,
        "data": {"stage_version": 0, "source": fc.SOURCE_MIGRATION,
                 "rule_id": linha.get("rule_id"), "ruleset_version": linha.get("ruleset_version"),
                 "reverted_activity_id": linha["activity_id"]},
    }


# ---------------------------------------------------------------------------
# Escritas (uma transacao por contato; todas as leituras antes das escritas)
# ---------------------------------------------------------------------------

def ja_aplicado(tenant_id, contact_id, activity_id, transaction=None):
    """None (este ruleset ainda nao classificou o contato), 'ja_migrado' ou
    'revertido_antes': a Activity existe e o --undo a reverteu (o contato
    candidato esta sem etapa); o undo e definitivo para o mesmo ruleset."""
    from firestore_common import tenant_document
    if not tenant_document(tenant_id, "crm_activities", activity_id).get(transaction=transaction).exists:
        return None
    reversao = tenant_document(tenant_id, "crm_activities", revert_id(tenant_id, contact_id, activity_id))
    return "revertido_antes" if reversao.get(transaction=transaction).exists else "ja_migrado"


def gravar_contato(tenant_id, contact_id, lido, plano, canais):
    """Desfecho da escrita: gravado | ja_migrado | revertido_antes |
    <causa>_durante_execucao."""
    from google.api_core import exceptions as gex
    from google.cloud import firestore
    from firestore_common import get_firestore_client, tenant_document
    # A migracao so escreve crm_*: nunca qualification nem outro campo do
    # contato (decisao 2 do PO: so a mudanca MANUAL sincroniza o legado).
    if not set(plano["fields"]) <= set(fc.CONTACT_STAGE_FIELDS):
        raise RuntimeError("plano da migracao com campo fora de crm_*")
    contato_ref = tenant_document(tenant_id, "wa_contacts", contact_id)
    atividade_ref = tenant_document(tenant_id, "crm_activities", plano["activity_id"])
    esperado = {campo: lido.get(campo) for campo in CLASSIFY_FIELDS}

    def corpo(transaction):
        snap = contato_ref.get(transaction=transaction)
        if not snap.exists:
            return "contato_sumiu_durante_execucao"
        atual = snap.to_dict() or {}
        causa = prefiltro(atual, tenant_id, canais)
        if causa == "ja_tem_etapa":
            return "etapa_gravada_durante_execucao"
        if causa:
            return causa + "_durante_execucao"
        if any(atual.get(campo) != valor for campo, valor in esperado.items()):
            return "mudou_durante_execucao"
        aplicado = ja_aplicado(tenant_id, contact_id, plano["activity_id"], transaction)
        if aplicado:
            return aplicado
        transaction.set(contato_ref, plano["fields"], merge=True)
        transaction.create(atividade_ref, plano["activity"])
        return "gravado"

    try:
        return firestore.transactional(corpo)(get_firestore_client().transaction())
    except gex.AlreadyExists:
        return "ja_migrado"


def reverter_contato(ctx, linha):
    from google.cloud import firestore
    from firestore_common import get_firestore_client, tenant_document
    tenant_id, contact_id = ctx["tenant"], linha["contact_id"]
    contato_ref = tenant_document(tenant_id, "wa_contacts", contact_id)
    rid = revert_id(tenant_id, contact_id, linha["activity_id"])
    reversao_ref = tenant_document(tenant_id, "crm_activities", rid)

    def corpo(transaction):
        snap = contato_ref.get(transaction=transaction)
        ja = reversao_ref.get(transaction=transaction).exists
        causa = estado_para_reverter(snap.exists, snap.to_dict() or {}, ja, linha)
        if causa:
            return causa
        transaction.update(contato_ref, {campo: firestore.DELETE_FIELD for campo in linha["fields"]})
        transaction.create(reversao_ref, atividade_de_reversao(ctx, linha, rid))
        return "revertido"

    return firestore.transactional(corpo)(get_firestore_client().transaction())


# ---------------------------------------------------------------------------
# Execucoes
# ---------------------------------------------------------------------------

def resolver_catalogo(doc, template_arg):
    """(catalogo, template, estado do funil no tenant). Recusa se o
    --template nao casar com o do tenant ou faltar."""
    settings = doc.get("settings") if isinstance(doc.get("settings"), dict) else {}
    funil = settings.get("funnel") if isinstance(settings.get("funnel"), dict) else {}
    atual = _texto(funil.get("template"))
    if atual:
        if template_arg and template_arg != atual:
            raise Recusa("--template %s nao casa com settings.funnel.template=%s do tenant"
                         % (template_arg, atual))
        nome = atual
    elif template_arg:
        nome = template_arg
    else:
        raise Recusa("tenant ainda sem settings.funnel: informe --template (%s)"
                     % ", ".join(sorted(fc.TEMPLATES)))
    template = fc.TEMPLATES.get(nome)
    if template is None:
        raise Recusa("template %r nao existe neste codigo" % nome)
    erros = fc.validate_template(nome, template)
    if erros:
        raise Recusa("template invalido: " + "; ".join(erros))
    catalogo = fc.resolve_funnel(dict(funil, enabled=True, template=nome))
    if not catalogo:
        raise Recusa("settings.funnel do tenant nao resolve um catalogo (confira com "
                     "scripts.set_tenant_funnel --show)")
    if not funil:
        estado = "settings.funnel ausente (funil ainda nao configurado)"
    else:
        estado = "template %s, %s" % (nome, "HABILITADO" if funil.get("enabled") is True else "desligado")
    return catalogo, nome, estado


def destinos(regra):
    """(etapa, motivo, confianca) que a regra pode gravar."""
    if regra == LEGACY_RULE:
        return list(LEGACY_OUTCOME_TARGETS.values())
    return [RULE_TARGETS[regra]]


def checar_destinos(catalogo, regras):
    for regra in tuple(regras) + (NO_RULE,):
        for etapa, motivo, _confianca in destinos(regra):
            definicao = fc.stage_def(catalogo, etapa)
            if not definicao:
                raise Recusa("regra %s: etapa %s nao existe no template" % (regra, etapa))
            if not definicao["active"]:
                raise Recusa("regra %s: etapa %s esta inativa no tenant" % (regra, etapa))
            if definicao.get("requires_reason") and not motivo:
                raise Recusa("regra %s: etapa %s exige motivo" % (regra, etapa))
            if motivo:
                definicao_motivo = fc.reason_def(catalogo, motivo)
                if not definicao_motivo:
                    raise Recusa("regra %s: motivo %s nao existe no template" % (regra, motivo))
                if definicao_motivo.get("selectable", True):
                    raise Recusa("regra %s: o motivo %s precisa ser nao selecionavel (a migracao "
                                 "nunca afirma um motivo real)" % (regra, motivo))


def iterar_contatos(tenant_id, ids):
    from firestore_common import tenant_collection, tenant_document
    if ids:
        for contact_id in ids:
            yield tenant_document(tenant_id, "wa_contacts", contact_id).get()
        return
    colecao = tenant_collection(tenant_id, "wa_contacts")
    ultimo = None
    while True:
        consulta = colecao.order_by("__name__").limit(PAGE_SIZE)
        if ultimo is not None:
            consulta = consulta.start_after(ultimo)
        pagina = list(consulta.stream())
        for snap in pagina:
            yield snap
        if len(pagina) < PAGE_SIZE:
            return
        ultimo = pagina[-1]


def migrar(opcoes, ctx):
    import config
    from firestore_common import tenant_doc_ref, tenant_document
    tenant_id = ctx["tenant"]
    regras = opcoes["regras"]
    trecho = _texto(getattr(config, "REOPEN_DESFECHO_LINK", "")).lower()
    if "reopen_opt_out" in regras and not trecho:
        raise Recusa("reopen_opt_out exige REOPEN_DESFECHO_LINK (trecho do link de agendamento): "
                     "sem ele nao ha como provar 'nenhum link em nenhum ciclo'")
    snapshot = tenant_doc_ref(tenant_id).get()
    if not snapshot.exists:
        raise Recusa("tenant %r nao existe neste projeto/prefixo" % tenant_id)
    doc = snapshot.to_dict() or {}
    catalogo, template, estado = resolver_catalogo(doc, opcoes["template"])
    checar_destinos(catalogo, regras)
    canais_tenant = tuple(catalogo["intake_channel_types"])
    canais_extra = tuple(t for t in opcoes["canais_extra"] if t not in canais_tenant)
    ctx.update(catalogo=catalogo, regras=regras, dias=opcoes["dias"],
               ruleset=ruleset_version(regras, opcoes["dias"]),
               canais_tenant=frozenset(canais_tenant),
               canais=frozenset(canais_tenant + canais_extra))
    if doc.get("is_active") is False:
        print("ATENCAO: tenant inativo.")
    print("funil do tenant: %s" % estado)
    print("template: %s (%s)" % (template, catalogo["template_label"]))
    print("canais da entrada automatica: %s%s" % (
        ", ".join(canais_tenant),
        " | incluidos por --include-channel-types: %s" % ", ".join(canais_extra) if canais_extra else ""))
    print("regras: %s (precedencia %s; o resto -> %s)" % (
        ", ".join(r for r in RULES if r in regras), " > ".join(PRECEDENCE), fc.TRIAGE_STAGE))
    if LEGACY_RULE in regras:
        print("legacy_outcome: %s (a migracao nunca escreve qualification)" % ", ".join(
            "%s -> %s%s" % (desfecho, etapa, " [%s]" % motivo if motivo else "")
            for desfecho, (etapa, motivo, _confianca) in LEGACY_OUTCOME_TARGETS.items()))
    print("janela: %d dias (recent_untouched exige tambem entrada >= %s: first_seen_at de webhook/manual, "
          "1a inbound real das outras origens)" % (ctx["dias"], LINEAGE_START.date().isoformat()))
    print("ruleset_version: %s" % ctx["ruleset"])
    print("ritmo: %g contatos candidatos/s | limite: %s | amostra: %d ids por balde" % (
        opcoes["rate"], opcoes["limit"] or "sem limite", opcoes["sample"]))
    if opcoes["only"]:
        print("so os contatos informados em --only-contact: %d id(s)" % len(opcoes["only"]))

    rel = Relatorio(opcoes["sample"])
    leitores = Leitores(tenant_id, trecho, rel)
    ritmo = Ritmo(opcoes["rate"])
    qualificacoes = set(getattr(config, "QUALIFICATION_OPTIONS", ()) or ())
    undo = None
    if ctx["yes"]:
        stamp = ctx["agora"].astimezone(fc.BR_TZ).strftime("%Y%m%d_%H%M%S")
        caminho = LOGS_DIR / ("funnel_migration_undo_%s_%s_%s.jsonl" % (tenant_id, stamp, ctx["run_id"][-6:]))
        undo = UndoArquivo(caminho, {
            "type": "header", "format": UNDO_FORMAT, "tenant": tenant_id,
            "project": ctx["projeto"], "prefix": ctx["prefixo"], "run_id": ctx["run_id"],
            "ruleset_version": ctx["ruleset"], "template": template,
            "rules": [r for r in RULES if r in regras], "recent_days": ctx["dias"],
            "include_channel_types": list(canais_extra),
            "generated_at": ctx["agora"]})
        print("undo: %s (gravado antes de cada escrita)" % caminho)

    seguidos = 0
    abortou = False
    try:
        for snap in iterar_contatos(tenant_id, opcoes["only"]):
            contact_id = _inteiro(snap.id)
            if not snap.exists:
                rel.pulados["inexistente"] += 1
                rel.guardar_id("inexistente", contact_id)
                continue
            rel.lidos += 1
            if rel.lidos % PROGRESS_EVERY == 0:
                print("  ... %d lidos, %d candidatos" % (rel.lidos, rel.candidatos))
            contato = snap.to_dict() or {}
            rel.contar_datas(contato)
            if contact_id is None or contact_id < 1:
                rel.pulados["id_nao_numerico"] += 1
                continue
            causa = prefiltro(contato, tenant_id, ctx["canais"])
            evidencia = None
            if causa is None:
                evidencia, anomalia = evidencia_de(contato, ctx["agora"])
                if evidencia is None:
                    causa = anomalia
                elif anomalia:
                    rel.anomalias[anomalia] += 1
            if causa:
                rel.pulados[causa] += 1
                rel.guardar_id(causa, contact_id)
                if causa == "canal_fora_da_entrada":
                    rel.canais[(tipo_exibido(contato), "fora_da_entrada")] += 1
                continue
            if opcoes["limit"] and rel.candidatos >= opcoes["limit"]:
                rel.parou = "--limit %d atingido (relatorio parcial)" % opcoes["limit"]
                break
            rel.candidatos += 1
            rel.canais[(tipo_exibido(contato), "entrada_do_tenant" if tipo_de_canal(contato)
                        in ctx["canais_tenant"] else "incluido_por_flag")] += 1
            ritmo.esperar()
            try:
                plano = planejar(contato, contact_id, ctx, leitores, evidencia)
                regra = plano["rule"]
                rel.plano[(regra, plano["stage"], plano["reason"])] += 1
                qualificacao = _texto(contato.get("qualification"))
                if qualificacao not in qualificacoes:
                    qualificacao = "(outra)" if qualificacao else "(vazia)"  # so enum no relatorio
                rel.qualificacao[(regra, qualificacao)] += 1
                for outra in plano["matched"][1:]:
                    rel.sobreposicao[(regra, outra)] += 1
                for descartada, motivo_descarte in plano["discards"].items():
                    rel.descarte[(descartada, motivo_descarte)] += 1
                    rel.guardar_id(DISCARD_SAMPLE[descartada] + motivo_descarte, contact_id)
                if plano["anomaly"]:
                    rel.anomalias[plano["anomaly"]] += 1
                # Desfechos antigos: aplicados (por periodo da reforma) e os
                # que o estado atual venceu (conflitos), so com o enum.
                if regra == LEGACY_RULE:
                    rel.legado[(qualificacao, plano["stage"], plano["period"])] += 1
                    if plano["period"] == PERIOD_BEFORE:
                        rel.guardar_id("%s_%s" % (LEGACY_RULE, PERIOD_BEFORE), contact_id)
                if plano["conflict"]:
                    vencedora, desfecho, seria = plano["conflict"]
                    rel.conflito[(vencedora, desfecho, seria, plano["period"])] += 1
                    rel.guardar_id("conflito_" + desfecho, contact_id)
                # Para a revisao com o PO: onde caem os contatos com recusa
                # comercial e os com sinal de clique de controle.
                if recusa_comercial_ativa(contato):
                    rel.recusa[regra] += 1
                    rel.guardar_id("recusa_comercial_" + regra, contact_id)
                if sinal_de_clique(contato):
                    rel.clique[regra] += 1
                    rel.guardar_id("clique_de_controle_" + regra, contact_id)
                rel.entrada[plano["entry_kind"]] += 1
                rel.guardar_id(regra, contact_id)
                if undo is not None:
                    undo.registrar(linha_de_undo(ctx, contact_id, plano))
                    desfecho = gravar_contato(tenant_id, contact_id, contato, plano, ctx["canais"])
                else:
                    desfecho = ja_aplicado(tenant_id, contact_id, plano["activity_id"]) or "a_alterar"
                rel.resultado[desfecho] += 1
                if desfecho not in ("gravado", "a_alterar"):
                    rel.guardar_id(desfecho, contact_id)
                seguidos = 0
            except Exception as exc:  # noqa: BLE001
                rel.erros["%s em %s" % (type(exc).__name__, _onde(exc))] += 1
                rel.guardar_id("erro", contact_id)
                seguidos += 1
                if seguidos >= MAX_CONSECUTIVE_ERRORS:
                    rel.parou = "%d erros seguidos; execucao abortada" % seguidos
                    break
    except KeyboardInterrupt:
        rel.parou = "interrompido pelo operador"
    except Exception as exc:  # noqa: BLE001
        # Fora do try por contato (pagina de iterar_contatos, get do
        # --only-contact): o relatorio do que ja foi feito sai do mesmo jeito.
        abortou = True
        rel.erros["%s em %s" % (type(exc).__name__, _onde(exc))] += 1
        rel.parou = "erro de leitura; execucao abortada"
    finally:
        if undo is not None:
            undo.fechar()

    imprimir_relatorio(rel, ctx["yes"])
    if undo is not None:
        print("undo: %s (%d linha(s))" % (undo.caminho, undo.linhas) if undo.linhas
              else "undo: nenhum arquivo (nada a gravar)")
    if rel.parou == "interrompido pelo operador":
        print("\nRESULTADO: INTERROMPIDO (o que ja foi gravado esta no undo).")
        return 2
    if abortou:
        print("\nRESULTADO: ERRO de leitura; execucao abortada (o que ja foi gravado esta no undo). "
              "Rode de novo (idempotente) depois de investigar.")
        return 1
    if rel.erros:
        print("\nRESULTADO: ERRO em %d contato(s); rode de novo (idempotente) depois de investigar."
              % sum(rel.erros.values()))
        return 1
    if not ctx["yes"]:
        print("\nDRY-RUN: nada gravado. Adicione --yes para aplicar.")
    else:
        print("\nRESULTADO: OK.")
    return 0


def desfazer(opcoes, ctx):
    from firestore_common import tenant_doc_ref, tenant_document
    tenant_id = ctx["tenant"]
    cabecalhos, linhas = carregar_undo(opcoes["undo"], tenant_id, ctx["projeto"], ctx["prefixo"])
    if not tenant_doc_ref(tenant_id).get().exists:
        raise Recusa("tenant %r nao existe neste projeto/prefixo" % tenant_id)
    vistos, unicas = set(), []
    for linha in linhas:
        chave = (linha["contact_id"], linha["activity_id"])
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(linha)
    if opcoes["only"]:
        filtro = set(opcoes["only"])
        unicas = [linha for linha in unicas if linha["contact_id"] in filtro]
    print("undo: %s" % opcoes["undo"])
    print("execucoes no arquivo: %s" % ", ".join(
        "%s (%s)" % (c.get("run_id"), c.get("ruleset_version")) for c in cabecalhos))
    print("linhas: %d | contatos unicos a conferir: %d" % (len(linhas), len(unicas)))

    rel = Relatorio(opcoes["sample"])
    ritmo = Ritmo(opcoes["rate"])
    seguidos = 0
    abortou = False
    try:
        for linha in unicas:
            contact_id = linha["contact_id"]
            ritmo.esperar()
            try:
                if ctx["yes"]:
                    desfecho = reverter_contato(ctx, linha)
                else:
                    snap = tenant_document(tenant_id, "wa_contacts", contact_id).get()
                    rid = revert_id(tenant_id, contact_id, linha["activity_id"])
                    ja = tenant_document(tenant_id, "crm_activities", rid).get().exists
                    desfecho = estado_para_reverter(snap.exists, snap.to_dict() or {}, ja, linha) or "a_reverter"
                rel.resultado[desfecho] += 1
                if desfecho not in ("revertido", "a_reverter"):
                    rel.guardar_id(desfecho, contact_id)
                seguidos = 0
            except Exception as exc:  # noqa: BLE001
                rel.erros["%s em %s" % (type(exc).__name__, _onde(exc))] += 1
                rel.guardar_id("erro", contact_id)
                seguidos += 1
                if seguidos >= MAX_CONSECUTIVE_ERRORS:
                    rel.parou = "%d erros seguidos; execucao abortada" % seguidos
                    break
    except KeyboardInterrupt:
        rel.parou = "interrompido pelo operador"
    except Exception as exc:  # noqa: BLE001
        # Fora do try por contato: o relatorio do que ja foi revertido sai do
        # mesmo jeito.
        abortou = True
        rel.erros["%s em %s" % (type(exc).__name__, _onde(exc))] += 1
        rel.parou = "erro fora do contato; execucao abortada"

    print("\n=== Undo (%s) ===" % ("GRAVACAO" if ctx["yes"] else "DRY-RUN"))
    _bloco(rel.resultado)
    print("a reverter%s: %d" % (" (revertidos)" if ctx["yes"] else "",
                                rel.resultado.get("revertido" if ctx["yes"] else "a_reverter", 0)))
    if rel.erros:
        print("erros por tipo:")
        _bloco(rel.erros)
    for balde in sorted(rel.ids):
        print("amostra %s: %s" % (balde, ", ".join(str(i) for i in rel.ids[balde])))
    if rel.parou:
        print("PARADA ANTECIPADA: %s" % rel.parou)
    if rel.parou == "interrompido pelo operador":
        return 2
    if abortou:
        print("\nRESULTADO: ERRO; execucao abortada. Rode o undo de novo (idempotente) depois de investigar.")
        return 1
    if rel.erros:
        print("\nRESULTADO: ERRO em %d contato(s); rode o undo de novo (idempotente)." % sum(rel.erros.values()))
        return 1
    print("\nDRY-RUN: nada revertido. Adicione --yes para aplicar." if not ctx["yes"] else "\nRESULTADO: OK.")
    return 0


def _tipos_de_canal():
    from channel_service import CHANNEL_TYPE_COEXISTENCE, CHANNEL_TYPE_STANDARD
    return (CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE)


def _canais_extra(valor):
    """--include-channel-types -> tipos conhecidos, sem repeticao."""
    if valor is None:
        return []
    conhecidos = _tipos_de_canal()
    tipos = []
    for tipo in (t.strip() for t in valor.split(",")):
        if not tipo:
            continue
        if tipo not in conhecidos:
            raise Recusa("--include-channel-types: tipo %r desconhecido (%s)" % (tipo, ", ".join(conhecidos)))
        if tipo not in tipos:
            tipos.append(tipo)
    if not tipos:
        raise Recusa("--include-channel-types vazio")
    return tipos


def _opcoes(args):
    """Normaliza e valida os argumentos (sem I/O). Levanta Recusa."""
    if args.undo:
        conflitos = [nome for nome, valor in (("--template", args.template), ("--rules", args.rules),
                                               ("--recent-days", args.recent_days), ("--limit", args.limit),
                                               ("--include-channel-types", args.include_channel_types))
                     if valor is not None]
        if conflitos:
            raise Recusa("--undo nao combina com %s" % ", ".join(conflitos))
        if not Path(args.undo).is_file():
            raise Recusa("arquivo de undo nao encontrado")
    regras = []
    for nome in (args.rules.split(",") if args.rules is not None else DEFAULT_RULES):
        nome = nome.strip()
        if not nome:
            continue
        if nome in RENAMED_RULES:
            raise Recusa("a regra %r agora se chama %s (decisoes do PO de 28/10)" % (nome, RENAMED_RULES[nome]))
        if nome not in RULES:
            raise Recusa("regra desconhecida %r (use %s)" % (nome, ", ".join(RULES)))
        if nome not in regras:
            regras.append(nome)
    if not regras and not args.undo:
        raise Recusa("--rules vazio")
    dias = DEFAULT_RECENT_DAYS if args.recent_days is None else args.recent_days
    if not 1 <= dias <= 365:
        raise Recusa("--recent-days entre 1 e 365")
    limite = 0 if args.limit is None else args.limit
    if limite < 0:
        raise Recusa("--limit >= 0 (0 = sem limite)")
    if not 0 <= args.sample <= MAX_SAMPLE:
        raise Recusa("--sample entre 0 e %d" % MAX_SAMPLE)
    if not (0 < args.rate <= MAX_RATE):  # tambem recusa NaN
        raise Recusa("--rate entre 0 (exclusivo) e %g contatos/s" % MAX_RATE)
    ids = []
    if args.only_contact is not None:
        for parte in args.only_contact.split(","):
            parte = parte.strip()
            if not parte:
                continue
            if not parte.isdigit() or int(parte) < 1:
                raise Recusa("--only-contact espera ids numericos de contato separados por virgula")
            if int(parte) not in ids:
                ids.append(int(parte))
        if not ids or len(ids) > MAX_ONLY:
            raise Recusa("--only-contact com 1 a %d ids" % MAX_ONLY)
    return {"regras": tuple(regras), "dias": dias, "limit": limite, "sample": args.sample,
            "rate": args.rate, "only": ids, "template": args.template, "undo": args.undo,
            "canais_extra": _canais_extra(args.include_channel_types)}


def _parser():
    p = argparse.ArgumentParser(
        prog="python -m scripts.classify_funnel_stage", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True, type=_tenant, help="id do tenant (obrigatorio)")
    p.add_argument("--template", choices=sorted(fc.TEMPLATES), default=None,
                   help="obrigatorio se o tenant ainda nao tem settings.funnel; se tem, precisa casar")
    p.add_argument("--rules", default=None, metavar="REGRA[,REGRA]",
                   help="padrao recent_untouched,in_reception,legacy_outcome; reopen_opt_out e opt-in")
    p.add_argument("--recent-days", type=int, default=None, metavar="N",
                   help="janela de recent_untouched e in_reception (padrao 30)")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="maximo de contatos candidatos nesta execucao (0 = sem limite)")
    p.add_argument("--only-contact", default=None, metavar="ID[,ID]",
                   help="so estes contatos (ids numericos)")
    p.add_argument("--include-channel-types", default=None, metavar="TIPO[,TIPO]",
                   help="inclui contatos destes tipos de canal mesmo fora da entrada automatica do "
                        "tenant (padrao: so os de settings.funnel.intake_channel_types)")
    p.add_argument("--sample", type=int, default=0, metavar="N",
                   help="imprime ate N ids de contato por regra/causa (sem PII)")
    p.add_argument("--rate", type=float, default=20.0, metavar="N",
                   help="contatos candidatos por segundo (padrao 20)")
    p.add_argument("--undo", default=None, metavar="ARQ",
                   help="reverte a partir do JSONL de undo (dry-run sem --yes)")
    p.add_argument("--yes", action="store_true", help="grava (padrao: dry-run)")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    _stdout_seguro()
    try:
        opcoes = _opcoes(args)
    except Recusa as exc:
        print("RECUSADO: %s" % exc, file=sys.stderr)
        return 2
    ambiente = _ambiente()
    if ambiente is None:
        return 2
    projeto, prefixo = ambiente
    from firestore_common import collection_name
    agora = _agora()
    tipo = "undo" if args.undo else "mig"
    ctx = {"tenant": args.tenant, "projeto": projeto, "prefixo": prefixo, "agora": agora,
           "yes": bool(args.yes),
           "run_id": "%s_%s_%s" % (tipo, agora.strftime("%Y%m%dT%H%M%SZ"), secrets.token_hex(3))}
    print("=== classify_funnel_stage (%s) ===" % ("UNDO da migracao" if args.undo else "migracao do funil"))
    print("projeto: %s" % projeto)
    print("prefixo: %s (contatos: %s/%s/wa_contacts)" % (prefixo or "(vazio)", collection_name("tenants"), args.tenant))
    print("tenant:  %s" % args.tenant)
    print("modo:    %s" % ("GRAVACAO (--yes)" if args.yes else "DRY-RUN (escrita travada no cliente)"))
    print("relogio: %s (unico para a execucao) | run_id: %s" % (agora.isoformat(), ctx["run_id"]))
    if not args.yes:
        trava_escrita()
    try:
        return desfazer(opcoes, ctx) if args.undo else migrar(opcoes, ctx)
    except Recusa as exc:
        print("\nRECUSADO: %s" % exc)
        return 2
    except KeyboardInterrupt:
        print("\nABORTADO pelo operador.")
        return 2
    except Exception as exc:  # noqa: BLE001
        print("\nERRO: %s em %s." % (type(exc).__name__, _onde(exc)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
