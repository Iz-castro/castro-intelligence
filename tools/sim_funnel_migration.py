# -*- coding: utf-8 -*-
"""Simulador LOCAL dos scripts do funil: configuracao por tenant
(scripts/set_tenant_funnel.py) e migracao (scripts/classify_funnel_stage.py).

Sem ADC, rede ou Firestore real: o cliente de firestore_common e trocado por
um Firestore em memoria com caminhos, consultas, count(), precondicao de
update_time e transacoes otimistas (leitura alterada antes do commit =
Aborted; create de doc existente = AlreadyExists). As transacoes passam pelo
@firestore.transactional REAL da biblioteca (mesmas retentativas).

Cobre cada regra e os pre-filtros, idempotencia (2 execucoes), etapa
existente nunca tocada (inclusive quando o intake grava entre a leitura e a
transacao, e entre a leitura transacional e o commit), undo que nao reverte
depois de mudanca do usuario, dry-run sem nenhuma escrita (trava antes da 1a
leitura), saida e undo sem nome/telefone, datas ISO string coeridas para
datetime, Encerrar + link da Val em ciclo anterior que NAO vira
non_converted, set_tenant_funnel dry-run/diff/--yes substituindo a subarvore
e a recusa de inativar etapa com contatos. Gate estatico: toda consulta com
ordenacao ou intervalo tem indice exato em firestore.indexes.json.

Revisao adversarial (scripts-migracao-1..9): recusa comercial (inclusive
registro invalido) nunca vira non_converted e e contada por regra; revertido
pelo --undo aparece como revertido_antes; recent_untouched exige ausencia de
outbound humano e usa a entrada real fora das origens confiaveis; canal fora
da entrada automatica fica fora (salvo --include-channel-types), com
contagem por tipo; in_reception (ex-open_human) usa a ultima inbound REAL
(sem clique de avaliacao, controle ou reacao) na janela e no changed_at; erro
de leitura no meio imprime o relatorio e sai com 1 (migracao e undo); os dois
scripts exigem FIRESTORE_COLLECTION_PREFIX explicito; o subprocesso da CLI nao
alcanca o Firestore real nem com .env preenchido.

Decisoes do PO de 28/10/2026 (contrato v2, secao 4): open_human virou
in_reception (ligada; estado atual da recepcao: fora da fase do bot,
atendimento aberto e mensagem real na janela; first_human_contact_at
sozinho nao basta); legacy_outcome (ligada) leva convertido -> Cliente
Agendado, nao_convertido -> Nao convertido/not_informed, nao_qualificado ->
Nao qualificado e qualificado -> A classificar (contado a parte); o estado
atual vence o desfecho antigo e o conflito sai no relatorio, que separa os
desfechos anteriores a reforma de 02/09; recent_untouched so na fase do
bot; reopen_opt_out nao passa por cima de desfecho registrado;
request_welcome conta como mensagem do paciente; a migracao nunca escreve
qualification (whitelist de escrita conferida em cada escrita: contato so
com set(merge) dos campos crm_*, Activity so por create; undo so com
DELETE_FIELD dos crm_*). RULESET_VERSION nova reclassifica o que o --undo
reverteu (com a mesma, o undo e definitivo) e o undo de execucao anterior
(regra open_human) segue valido. set_tenant_funnel: catalogo v2 (sem
attended/converted, chaves v1 recusadas); etapa estrutural (KPI de
conversao, destino de automacao) nunca fica inativa; --show mostra os textos
da clinica (tela Etapas) e as marcas v2 do catalogo; avisos de rotulo
sombreado pela clinica e de chave fora do template.

Rodar (raiz do repo):
    .venv\\Scripts\\python.exe tools\\sim_funnel_migration.py

Exit 0 = todas as verificacoes passaram; 1 = alguma falhou.
"""

import ast
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROJECT = "sim-funnel-project"
PREFIX = "castro_crm_sim"
os.environ["FIRESTORE_PROJECT_ID"] = PROJECT
os.environ["FIRESTORE_COLLECTION_PREFIX"] = PREFIX
os.environ["REOPEN_DESFECHO_LINK"] = "marcaconsultas"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from google.api_core import exceptions as gex  # noqa: E402
from google.cloud import firestore as gfs  # noqa: E402
import google.cloud.firestore_v1 as gfs_v1  # noqa: E402

import config  # noqa: E402
import firestore_common as common  # noqa: E402
import funnel_catalog as fc  # noqa: E402

CHECKS = 0
FAILS = []
SAIDAS = []
TRAVAS = []
SLEEPS = []
RELOGIO = [0.0]
NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)   # 12h em Sao Paulo
AGORA = [NOW]
T = "sim-clinica"
OUTRA = "sim-outra"
CFG_T = "sim-config"
PII = []


def check(cond, label, contexto=None):
    global CHECKS
    CHECKS += 1
    if cond:
        print("  OK " + label)
        return True
    FAILS.append(label)
    print("  FALHOU: " + label)
    if contexto is not None:
        print("    --- saida da execucao ---")
        print("    " + str(contexto)[-3000:].replace("\n", "\n    "))
    return False


def titulo(texto):
    print("\n" + "=" * 72 + "\n" + texto + "\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Firestore em memoria
# ---------------------------------------------------------------------------

def _store(valor):
    """Como o Firestore devolve: datetime ingenuo vira UTC; tupla vira lista."""
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, dict):
        return {k: _store(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_store(v) for v in valor]
    return copy.deepcopy(valor)


def _merge(atual, dados):
    resultado = copy.deepcopy(atual)
    for chave, valor in dados.items():
        if valor is gfs.DELETE_FIELD:
            resultado.pop(chave, None)
        elif isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _merge(resultado[chave], valor)
        else:
            resultado[chave] = _store(valor)
    return resultado


def _caminhos(atual, mudancas):
    """update(): chave com ponto e caminho de campo e SUBSTITUI o valor."""
    resultado = copy.deepcopy(atual)
    for caminho, valor in mudancas.items():
        partes = caminho.split(".")
        alvo = resultado
        for parte in partes[:-1]:
            if not isinstance(alvo.get(parte), dict):
                alvo[parte] = {}
            alvo = alvo[parte]
        if valor is gfs.DELETE_FIELD:
            alvo.pop(partes[-1], None)
        else:
            alvo[partes[-1]] = _store(valor)
    return resultado


class FakeDB:
    def __init__(self):
        self.docs = {}
        self.rev = {}
        self.tick = 0
        self.reads = 0
        self.writes = []
        # Whitelist de escrita: (op, caminho, campos, merge, valores) de cada
        # escrita; `externo` marca as que o simulador faz por fora (intake no
        # meio da migracao, gravacao em paralelo), que nao sao do script.
        self.write_log = []
        self.externo = False
        self.locked = False
        self.shapes = []
        self.naive = []
        self.tx_attempts = 0
        self.hook_tx_read = {}    # caminho -> callback, 1x antes da leitura transacional
        self.hook_commit = {}     # caminho lido na transacao -> callback, 1x no commit
        self.hook_after_get = {}  # caminho -> callback, 1x depois de get fora de transacao
        self.fail_commit = {}     # caminho escrito -> excecao, 1x no commit
        self.fail_query = []      # [(predicado(consulta), excecao)], 1x no stream que casar

    def guard(self):
        if self.locked:
            raise RuntimeError("simulador: escrita com a trava do dry-run ligada")

    def compat(self, valor, caminho, em_lista=False):
        if valor is None or isinstance(valor, (bool, int, float, str, bytes)):
            return
        if isinstance(valor, datetime):
            if valor.tzinfo is None:
                self.naive.append(caminho)
            return
        if isinstance(valor, dict):
            for chave, item in valor.items():
                if not isinstance(chave, str) or not chave:
                    raise AssertionError("Firestore: chave invalida em %s" % caminho)
                self.compat(item, caminho + "." + chave)
            return
        if isinstance(valor, (list, tuple)):
            if em_lista:
                raise AssertionError("Firestore: lista dentro de lista em %s" % caminho)
            for indice, item in enumerate(valor):
                self.compat(item, "%s[%d]" % (caminho, indice), em_lista=True)
            return
        raise AssertionError("Firestore: tipo %s nao gravavel em %s" % (type(valor).__name__, caminho))

    def compat_doc(self, dados, caminho, apaga):
        if not isinstance(dados, dict):
            raise AssertionError("Firestore: documento precisa ser mapa em %s" % caminho)
        for chave, valor in dados.items():
            if valor is gfs.DELETE_FIELD:
                if not apaga:
                    raise AssertionError("DELETE_FIELD fora de update/merge em %s" % caminho)
                continue
            self.compat(valor, caminho + "." + chave)

    def apply(self, op, chave, dados=None, merge=False):
        if op == "create":
            if chave in self.docs:
                raise gex.AlreadyExists("documento ja existe")
            self.docs[chave] = _store(dados)
        elif op == "set":
            self.docs[chave] = _merge(self.docs.get(chave, {}), dados) if merge else _store(dados)
        elif op == "update":
            if chave not in self.docs:
                raise gex.NotFound("documento inexistente")
            self.docs[chave] = _caminhos(self.docs[chave], dados)
        elif op == "delete":
            self.docs.pop(chave, None)
        self.tick += 1
        self.rev[chave] = self.tick
        self.writes.append((op, chave))
        self.write_log.append({"op": op, "chave": chave, "campos": sorted(dados or {}), "merge": merge,
                               "valores": dict(dados or {}), "externo": self.externo})


class FakeSnapshot:
    def __init__(self, ref, dados, update_time):
        self.reference = ref
        self.id = ref.id
        self.exists = dados is not None
        self._dados = copy.deepcopy(dados)
        self.update_time = update_time

    def to_dict(self):
        return copy.deepcopy(self._dados) if self.exists else None

    def get(self, campo):
        return (self._dados or {}).get(campo)


class FakeDocRef:
    def __init__(self, db, chave):
        self._db = db
        self._chave = tuple(chave)
        self.id = self._chave[-1]

    @property
    def path(self):
        return "/".join(self._chave)

    def collection(self, nome):
        return FakeCollection(self._db, self._chave + (nome,))

    def get(self, transaction=None, **_k):
        db = self._db
        if transaction is not None:
            gancho = db.hook_tx_read.pop(self._chave, None)
            if gancho:
                gancho()
            transaction._ler(self._chave)
        db.reads += 1
        snap = FakeSnapshot(self, db.docs.get(self._chave), db.rev.get(self._chave))
        if transaction is None:
            gancho = db.hook_after_get.pop(self._chave, None)
            if gancho:
                gancho()
        return snap

    def set(self, dados, merge=False):
        self._db.guard()
        self._db.compat_doc(dados, self.path, apaga=merge)
        self._db.apply("set", self._chave, dados, merge)

    def create(self, dados):
        self._db.guard()
        self._db.compat_doc(dados, self.path, apaga=False)
        self._db.apply("create", self._chave, dados)

    def update(self, dados, option=None):
        self._db.guard()
        self._db.compat_doc(dados, self.path, apaga=True)
        esperado = getattr(option, "last_update_time", None) if option is not None else None
        if option is not None and esperado != self._db.rev.get(self._chave):
            raise gex.FailedPrecondition("update_time divergente")
        self._db.apply("update", self._chave, dados)

    def delete(self, option=None):
        self._db.guard()
        self._db.apply("delete", self._chave)

    def __eq__(self, other):
        return isinstance(other, FakeDocRef) and other._chave == self._chave

    def __hash__(self):
        return hash(self._chave)


class FakeTransaction:
    """Protocolo usado pelo _Transactional real (_begin/_commit/_rollback)."""
    _max_attempts = 5
    _read_only = False

    def __init__(self, db):
        self._db = db
        self._id = None
        self._lidas = {}
        self._pendentes = []

    @property
    def in_progress(self):
        return self._id is not None

    def _clean_up(self):
        self._pendentes = []
        self._id = None

    def _begin(self, retry_id=None):
        self._db.tx_attempts += 1
        self._id = b"sim-%d" % self._db.tx_attempts
        self._lidas = {}
        self._pendentes = []

    def _ler(self, chave):
        if self._pendentes:
            raise AssertionError("Firestore: leitura depois de escrita na transacao")
        self._lidas[chave] = self._db.rev.get(chave)

    def _enfileirar(self, op, ref, dados=None, merge=False):
        self._db.guard()
        if dados is not None:
            self._db.compat_doc(dados, ref.path, apaga=(op == "update" or merge))
        self._pendentes.append((op, ref._chave, copy.deepcopy(dados), merge))

    def set(self, ref, dados, merge=False):
        self._enfileirar("set", ref, dados, merge)

    def create(self, ref, dados):
        self._enfileirar("create", ref, dados)

    def update(self, ref, dados):
        self._enfileirar("update", ref, dados)

    def delete(self, ref):
        self._enfileirar("delete", ref)

    def _commit(self):
        db = self._db
        if not self.in_progress:
            raise ValueError("transacao sem _begin")
        for chave in list(self._lidas):
            gancho = db.hook_commit.pop(chave, None)
            if gancho:
                gancho()
        for chave, revisao in self._lidas.items():
            if db.rev.get(chave) != revisao:
                self._clean_up()
                raise gex.Aborted("conflito simulado")
        for op, chave, _dados, _merge in self._pendentes:
            falha = db.fail_commit.pop(chave, None)
            if falha is not None:
                self._clean_up()
                raise falha
            if op == "create" and chave in db.docs:
                self._clean_up()
                raise gex.AlreadyExists("documento ja existe")
        if self._pendentes:
            db.guard()
        for op, chave, dados, merge in self._pendentes:
            db.apply(op, chave, dados, merge)
        self._clean_up()
        return []

    def _rollback(self):
        self._clean_up()


def _rank(valor):
    if valor is None:
        return 0
    if isinstance(valor, bool):
        return 1
    if isinstance(valor, (int, float)):
        return 2
    if isinstance(valor, datetime):
        return 3
    if isinstance(valor, str):
        return 4
    return 9


def _ordem(valor):
    r = _rank(valor)
    if r == 3:
        return (r, (valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)).timestamp())
    if r == 1:
        return (r, int(valor))
    if r == 2:
        return (r, float(valor))
    if r == 4:
        return (r, valor)
    return (r, repr(valor))


def _passa(doc, campo, op, valor):
    if campo not in doc:
        return False
    atual = doc[campo]
    if op == "==":
        return _rank(atual) == _rank(valor) and _ordem(atual) == _ordem(valor)
    if op == "in":
        return any(_rank(atual) == _rank(v) and _ordem(atual) == _ordem(v) for v in valor)
    if op in ("<", "<=", ">", ">="):
        if _rank(atual) != _rank(valor):
            return False
        a, b = _ordem(atual), _ordem(valor)
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    raise AssertionError("operador nao simulado: %s" % op)


class FakeQuery:
    def __init__(self, db, pai, filtros=(), ordens=(), teto=None, depois=None):
        self._db = db
        self._pai = tuple(pai)
        self._filtros = tuple(filtros)
        self._ordens = tuple(ordens)
        self._teto = teto
        self._depois = depois

    def _novo(self, **mudancas):
        base = {"filtros": self._filtros, "ordens": self._ordens, "teto": self._teto, "depois": self._depois}
        base.update(mudancas)
        return FakeQuery(self._db, self._pai, **base)

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):  # noqa: A002
        if filter is not None:
            field_path, op_string, value = filter.field_path, filter.op_string, filter.value
        return self._novo(filtros=self._filtros + ((field_path, op_string, value),))

    def order_by(self, field_path, direction="ASCENDING"):
        return self._novo(ordens=self._ordens + ((field_path, direction),))

    def limit(self, quantos):
        return self._novo(teto=quantos)

    def start_after(self, cursor):
        return self._novo(depois=cursor)

    def _todas_ordens(self):
        ordens = list(self._ordens)
        if not any(campo == "__name__" for campo, _ in ordens):
            ordens.append(("__name__", ordens[-1][1] if ordens else "ASCENDING"))
        return ordens

    def _linhas(self):
        n = len(self._pai)
        linhas = [(k[-1], v) for k, v in self._db.docs.items() if len(k) == n + 1 and k[:n] == self._pai]
        linhas = [(i, d) for i, d in linhas if all(_passa(d, c, o, v) for c, o, v in self._filtros)]
        ordens = self._todas_ordens()
        linhas = [(i, d) for i, d in linhas if all(c == "__name__" or c in d for c, _ in ordens)]

        def chave(linha, campo):
            return (4, linha[0]) if campo == "__name__" else _ordem(linha[1][campo])

        for campo, direcao in reversed(ordens):
            linhas.sort(key=lambda linha, c=campo: chave(linha, c), reverse=(direcao == "DESCENDING"))
        if self._depois is not None:
            cursor = self._depois
            if isinstance(cursor, FakeSnapshot):
                dados = cursor.to_dict() or {}
                alvo = [(4, cursor.id) if c == "__name__" else _ordem(dados.get(c)) for c, _ in ordens]
            else:
                raise AssertionError("cursor nao simulado")

            def adiante(linha):
                for (campo, direcao), esperado in zip(ordens, alvo):
                    atual = chave(linha, campo)
                    if atual != esperado:
                        return atual < esperado if direcao == "DESCENDING" else atual > esperado
                return False
            linhas = [linha for linha in linhas if adiante(linha)]
        if self._teto is not None:
            linhas = linhas[:self._teto]
        return linhas

    def _forma(self):
        return {"collection": self._pai[-1],
                "eq": sorted(c for c, o, _ in self._filtros if o in ("==", "in")),
                "range": sorted(c for c, o, _ in self._filtros if o not in ("==", "in")),
                "orders": [(c, d) for c, d in self._ordens if c != "__name__"]}

    def stream(self, transaction=None, **_k):
        for indice, (predicado, falha) in enumerate(self._db.fail_query):
            if predicado(self):
                del self._db.fail_query[indice]
                raise falha
        self._db.shapes.append(self._forma())
        linhas = self._linhas()
        self._db.reads += max(1, len(linhas))
        return iter([FakeSnapshot(FakeDocRef(self._db, self._pai + (i,)), d, self._db.rev.get(self._pai + (i,)))
                     for i, d in linhas])

    def get(self, **_k):
        return list(self.stream())

    def count(self, alias=None):
        consulta = self

        class _Agregacao:
            def get(self, **_k):
                consulta._db.shapes.append(consulta._forma())
                consulta._db.reads += 1
                return [[SimpleNamespace(alias=alias, value=len(consulta._linhas()))]]
        return _Agregacao()


class FakeCollection(FakeQuery):
    def __init__(self, db, chave):
        super().__init__(db, chave)

    @property
    def id(self):
        return self._pai[-1]

    def document(self, doc_id=None):
        return FakeDocRef(self._db, self._pai + (str(doc_id),))


class FakeClient:
    def __init__(self, db):
        self._db = db

    def collection(self, nome):
        return FakeCollection(self._db, (nome,))

    def transaction(self, **_k):
        return FakeTransaction(self._db)

    def write_option(self, **kwargs):
        return SimpleNamespace(**kwargs)


DB = FakeDB()
CLIENT = FakeClient(DB)
common.get_firestore_client = lambda: CLIENT


def _cliente_proibido(*_a, **_k):
    raise AssertionError("cliente Firestore REAL proibido no simulador")


gfs.Client = _cliente_proibido
gfs_v1.Client = _cliente_proibido

import scripts.classify_funnel_stage as mig  # noqa: E402
import scripts.set_tenant_funnel as conf  # noqa: E402

TRAVA_REAL = mig.trava_escrita
TRAVA_REAL_CONF = conf.trava_escrita


def trava_sim():
    TRAVAS.append(DB.reads)
    DB.locked = True


def _sleep_sim(segundos):
    SLEEPS.append(segundos)
    RELOGIO[0] += segundos


mig.trava_escrita = trava_sim
conf.trava_escrita = trava_sim
mig._agora = lambda: AGORA[0]
conf._agora = lambda: AGORA[0]
mig._sleep = _sleep_sim
mig._monotonic = lambda: RELOGIO[0]
LOGS = Path(tempfile.mkdtemp(prefix="sim_funnel_logs_"))
mig.LOGS_DIR = LOGS
TENANTS_COL = common.collection_name("tenants")
CATALOGO = fc.resolve_funnel({"enabled": True, "template": "clinic_v1"})


def tkey(tid):
    return (TENANTS_COL, tid)


def ckey(tid, colecao, doc_id):
    return (TENANTS_COL, tid, colecao, str(doc_id))


def put(chave, dados):
    DB.docs[chave] = _store(dados)
    DB.tick += 1
    DB.rev[chave] = DB.tick


def doc(chave):
    return copy.deepcopy(DB.docs.get(chave))


def sem_crm(dados):
    return {k: v for k, v in (dados or {}).items() if not k.startswith("crm_")}


def rodar(modulo, *argv):
    saida, erro = io.StringIO(), io.StringIO()
    TRAVAS.clear()
    DB.locked = False
    leituras, escritas, registro = DB.reads, len(DB.writes), len(DB.write_log)
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = modulo.main(list(argv))
        except SystemExit as exc:
            codigo = exc.code
    DB.locked = False
    texto = saida.getvalue() + erro.getvalue()
    SAIDAS.append(texto)
    return SimpleNamespace(code=codigo, out=saida.getvalue(), err=erro.getvalue(), text=texto,
                           reads0=leituras, writes=DB.writes[escritas:], travas=list(TRAVAS),
                           proprias=[w for w in DB.write_log[registro:] if not w["externo"]])


@contextlib.contextmanager
def por_fora():
    """Escrita feita pelo simulador (intake, usuario, gravacao em paralelo),
    fora da whitelist do script."""
    anterior, DB.externo = DB.externo, True
    try:
        yield
    finally:
        DB.externo = anterior


def dry_ok(r):
    """Trava ligada antes da 1a leitura e nenhuma escrita."""
    return r.travas == [r.reads0] and not r.writes


def linha(texto, rotulo, n):
    return re.search(r"^\s*%s\s+%d\s*$" % (re.escape(rotulo), n), texto, re.M) is not None


def amostra(texto, balde):
    achado = re.search(r"^amostra %s: (.*)$" % re.escape(balde), texto, re.M)
    return [int(x) for x in achado.group(1).split(", ")] if achado else []


def bloco(texto, cabecalho):
    """Linhas indentadas logo abaixo do cabecalho (um bloco do relatorio)."""
    linhas = texto.splitlines()
    for indice, atual in enumerate(linhas):
        if atual.startswith(cabecalho):
            corpo = []
            for seguinte in linhas[indice + 1:]:
                if not seguinte.startswith("  "):
                    break
                corpo.append(seguinte)
            return "\n".join(corpo)
    return ""


def consultas_falsas(link=(False, False), humano=False, inbound_real=(None, False),
                     primeira=(None, False), aberto=True, chamadas=None):
    """Leituras auxiliares de um contato para as regras puras; anota o nome
    de cada leitura feita em `chamadas`."""
    def leitura(nome, valor):
        def ler():
            if chamadas is not None:
                chamadas.append(nome)
            return valor
        return ler
    return SimpleNamespace(link_enviado=leitura("link", link), outbound_humano=leitura("humano", humano),
                           ultima_inbound_real=leitura("inbound_real", inbound_real),
                           primeira_inbound=leitura("primeira", primeira),
                           atendimento_aberto=leitura("aberto", aberto))


# ---------------------------------------------------------------------------
# Fixtures (nome/telefone/notas/conteudo sinteticos, para o teste de PII)
# ---------------------------------------------------------------------------

def dias(n):
    return NOW - timedelta(days=n)


def contato(cid, **extra):
    # bot_completed falso por padrao: na recepcao o fechamento devolve o lead
    # a Val (release_lead_to_bot); quem esta na recepcao agora e explicito.
    base = {
        "id": cid, "wa_id": "5511990%06d" % cid, "display_name": "Fixture Pessoa%d Silva" % cid,
        "declared_name": "Fixture Declarada%d" % cid, "whatsapp_profile_name": "PerfilFixture%d" % cid,
        "phone_formatted": "+55 (11) 99%03d-%04d" % (cid % 1000, cid), "notes": "nota privada fixture %d" % cid,
        "qualification": "em_atendimento", "created_source": "webhook", "is_archived": 0,
        "is_backup": False, "assigned_to": None, "assigned_to_uid": "", "bot_completed": False,
        "lgpd_consent": True, "first_seen_at": dias(90), "last_inbound_at": dias(60),
        "last_message_at": dias(60), "tags": ["tag-fixture"], "source_channel_type": "standard",
    }
    base.update(extra)
    if "last_message_at" not in extra:
        # Mensagem comum avanca as duas datas juntas; so o clique de controle
        # deixa last_inbound_at na frente (fixture explicita).
        base["last_message_at"] = base["last_inbound_at"]
    PII.extend([base["wa_id"], base["display_name"], base["declared_name"], base["whatsapp_profile_name"],
                base["phone_formatted"], base["notes"]])
    return base


MSG_ID = [1000]


def mensagem(tid, cid, direcao, quando, conteudo, sender=None, msg_type="text", **extra):
    MSG_ID[0] += 1
    PII.append(conteudo)
    dados = {
        "id": MSG_ID[0], "contact_id": cid, "conversation_id": "4__5511990%06d" % cid,
        "direction": direcao, "msg_type": msg_type, "content": conteudo, "timestamp_wa": quando,
        "sender_user_id": sender, "is_rating_message": False, "visibility": "all"}
    dados.update(extra)
    put(ckey(tid, "wa_messages", MSG_ID[0]), dados)


def clique_de_avaliacao(tid, cid, quando):
    """Clique valido de avaliacao, como o webhook grava (controle admin_only)."""
    mensagem(tid, cid, "inbound", quando, "[Fixture avaliacao: Bom]", msg_type="button",
             is_rating_message=True, visibility="admin_only")


def thread(tid, cid, status="aberto", canal=4, **extra):
    """Atendimento (wa_conversations) do contato, como upsert_wa_conversation
    grava; status = attendance_status (aberto | fechado_*)."""
    dados = {"id": "%d__5511990%06d" % (canal, cid), "contact_id": cid, "channel_id": canal,
             "attendance_status": status, "is_backup": False, "assigned_to": None, "assigned_to_uid": ""}
    dados.update(extra)
    put(ckey(tid, "wa_conversations", dados["id"]), dados)


SEED = {}


def semear_clinica():
    put(tkey(T), {"id": T, "name": "Clinica Simulada", "is_active": True,
                  "settings": {"ai": {"bot_engine": "dialogflow_cx", "lgpd_by_agent": False}}})
    linhas = [
        contato(101, qualification="novo", first_seen_at=dias(5), last_inbound_at=dias(4)),
        contato(102, qualification="novo", first_seen_at=datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
                last_inbound_at=dias(3)),
        contato(103, qualification="novo", first_seen_at=datetime(2026, 9, 3, 12, tzinfo=timezone.utc),
                last_inbound_at=dias(2)),
        # Na recepcao (o handoff carimbou bot_completed), atendimento aberto e
        # mensagem real recente: Em atendimento.
        contato(104, bot_completed=True, first_human_contact_at=dias(20), last_inbound_at=dias(3)),
        contato(105, first_human_contact_at=dias(50), last_inbound_at=dias(45)),
        # Encerrar e a equipe seguiu na recepcao (bot_completed, thread
        # aberta): o reopen_opt_out (opt-in) vence o in_reception.
        contato(106, bot_completed=True, first_human_contact_at=dias(40), reopen_opt_out=True,
                reopen_opt_out_at=dias(10).isoformat(), last_inbound_at=dias(10) + timedelta(seconds=30),
                bot_outcome=None),
        contato(107, reopen_opt_out=True, reopen_opt_out_at=dias(8).strftime("%Y-%m-%dT%H:%M:%SZ"),
                last_inbound_at=dias(8), bot_released_at=dias(20), bot_outcome=None),
        contato(108, reopen_opt_out=True, reopen_opt_out_at=dias(12).isoformat(), last_inbound_at=dias(2)),
        # Encerrar + desfecho registrado (convertido): quem cuida e o
        # legacy_outcome (Cliente Agendado).
        contato(109, reopen_opt_out=True, reopen_opt_out_at=dias(9).isoformat(), last_inbound_at=dias(9),
                qualification="convertido"),
        contato(110, reopen_opt_out=True, reopen_opt_out_at=dias(7).isoformat(), last_inbound_at=dias(7),
                bot_outcome="agendado"),
        contato(111, crm_stage="scheduled", crm_stage_version=3, crm_stage_source="user",
                crm_stage_changed_at=dias(2), crm_stage_activity_id="stage_" + "a" * 64,
                crm_stage_changed_by_user_id=7, crm_stage_changed_by_uid="uid-fixture-7",
                crm_funnel_entered_at=dias(30), crm_cohort_month="2026-09", crm_max_reached_order=40,
                last_inbound_at=dias(1)),
        contato(112, is_backup=True, assigned_to_uid="__backup__", last_inbound_at=dias(5)),
        contato(113, created_source="state_sync", last_inbound_at=None, last_message_at=None),
        contato(114, lgpd_revoked=True, last_inbound_at=dias(3)),
        contato(115, qualification="novo", first_seen_at="2026-10-19T08:00:00",
                last_inbound_at="2026-10-20T10:00:00Z"),
        contato(116, created_source="history", first_seen_at=dias(1),
                last_inbound_at=datetime(2025, 6, 1, 15, tzinfo=timezone.utc)),
        contato(117, created_source="state_sync", first_seen_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                last_inbound_at=datetime(2026, 2, 20, 12, tzinfo=timezone.utc)),
        contato(118, crm_funnel_entered_at=dias(10), last_inbound_at=dias(10)),
        contato(119, reopen_opt_out=True, reopen_opt_out_at=dias(15).isoformat(), last_inbound_at=dias(15)),
        contato(120, tenant_id=OUTRA, last_inbound_at=dias(5)),
        # Desfecho antigo (antes da reforma de 02/09), arquivado: Nao qualificado.
        contato(121, is_archived=1, qualification="nao_qualificado", last_inbound_at=dias(100)),
        contato(122, last_inbound_at="ontem", first_seen_at=dias(200)),
        contato(123, last_inbound_at=NOW + timedelta(days=2), first_seen_at=dias(300)),
        contato(124, last_inbound_at=dias(70)),
        contato(125, last_inbound_at=dias(71)),
        contato(126, created_source="backup_import", first_seen_at=dias(5),
                last_inbound_at=datetime(2025, 11, 1, 12, tzinfo=timezone.utc)),
        contato(127, created_source="history", first_seen_at=dias(1),
                last_inbound_at=datetime(2025, 5, 5, 12, tzinfo=timezone.utc)),
        # scripts-migracao-1: Encerrar + recusa comercial registrada DEPOIS do
        # clique (o clique nao a desfaz); valida e invalida (lado seguro).
        contato(128, reopen_opt_out=True, reopen_opt_out_at=dias(10), last_inbound_at=dias(10),
                commercial_contact_block={"active": True, "version": 1, "reason": "patient_request",
                                          "updated_at": dias(8)}),
        contato(129, reopen_opt_out=True, reopen_opt_out_at=dias(9), last_inbound_at=dias(9),
                commercial_contact_block={"active": "sim"}),
        # Recusa comercial ativa num Novo contato: so contada no relatorio.
        contato(130, qualification="novo", first_seen_at=dias(3), last_inbound_at=dias(2),
                commercial_contact_block={"active": True, "version": 2, "updated_at": dias(1)}),
        # scripts-migracao-3: nasceu em atendimento (manual com auto_assume),
        # a operadora conduziu e depois devolveu ao bot (novo sem carimbo).
        contato(131, created_source="manual", qualification="novo", first_seen_at=dias(6),
                last_inbound_at=dias(1), last_message_at=dias(1) + timedelta(minutes=1),
                bot_released_at=dias(2), bot_completed=False),
        # scripts-migracao-6: conversa real ha 45 dias e clique de avaliacao
        # ha 1 h (last_inbound_at sobe, last_message_at nao).
        contato(132, bot_completed=True, first_human_contact_at=dias(50), last_inbound_at=NOW - timedelta(hours=1),
                last_message_at=dias(45)),
        # Reacao recente sobre conversa real antiga.
        contato(133, bot_completed=True, first_human_contact_at=dias(50), last_inbound_at=dias(1)),
        # Conversa real ha 5 dias e clique de avaliacao ha 1 h: Em
        # atendimento, com changed_at na mensagem real.
        contato(134, bot_completed=True, first_human_contact_at=dias(30), last_inbound_at=NOW - timedelta(hours=1),
                last_message_at=dias(5)),
        # Decisao 3 do PO (28/10): desfechos registrados no Encerrar.
        contato(135, qualification="convertido", first_seen_at=dias(40), last_inbound_at=dias(10)),
        contato(136, qualification="nao_convertido", first_seen_at=dias(60), last_inbound_at=dias(20)),
        contato(137, qualification="qualificado", last_inbound_at=dias(15)),
        # Convertido no passado e de volta a recepcao agora: o estado atual
        # vence (Em atendimento) e o conflito sai no relatorio.
        contato(138, qualification="convertido", bot_completed=True, first_human_contact_at=dias(60),
                last_inbound_at=dias(2)),
        # Handoff da Val sem resposta humana ainda (novo, sem carimbo): Em
        # atendimento, nunca Novo contato.
        contato(139, qualification="novo", bot_completed=True, first_seen_at=dias(3), last_inbound_at=dias(2)),
        # bot_completed com o atendimento fechado (fechamento que nao devolveu
        # o lead a Val) e so a thread de backup aberta: nao e estado atual.
        contato(140, bot_completed=True, first_human_contact_at=dias(30), last_inbound_at=dias(3)),
        # Operadora assumiu antes do handoff (dono sem bot_completed); a unica
        # inbound e a abertura do chat (request_welcome, decisao 6 do PO).
        contato(141, qualification="novo", assigned_to=8, assigned_to_uid="uid-fixture-8",
                first_seen_at=dias(4), last_inbound_at=dias(3)),
        # Encerrar + Nao qualificado registrado: o clique nao o transforma em
        # Nao convertido.
        contato(142, reopen_opt_out=True, reopen_opt_out_at=dias(9), last_inbound_at=dias(9),
                qualification="nao_qualificado"),
        # Convertido antes da reforma das qualificacoes (02/09).
        contato(143, qualification="convertido", first_seen_at=datetime(2026, 4, 1, 12, tzinfo=timezone.utc),
                last_inbound_at=datetime(2026, 5, 10, 12, tzinfo=timezone.utc)),
    ]
    for dados in linhas:
        SEED[dados["id"]] = _store(dados)
        put(ckey(T, "wa_contacts", dados["id"]), dados)
    for cid in (104, 106, 132, 133, 134, 138, 139):
        thread(T, cid)
    thread(T, 141, assigned_to=8, assigned_to_uid="uid-fixture-8")
    thread(T, 140, status="fechado_manual")
    thread(T, 140, canal=9, is_backup=True)  # backup aberto nao conta
    mensagem(T, 138, "inbound", dias(2), "Fixture: voltou a recepcao")
    mensagem(T, 139, "inbound", dias(2), "Fixture: quero falar com a recepcao")
    mensagem(T, 139, "outbound", dias(2) + timedelta(minutes=1), "Fixture: Val encaminhou")
    mensagem(T, 140, "inbound", dias(3), "Fixture: mensagem real com atendimento fechado")
    mensagem(T, 141, "inbound", dias(3), "[request_welcome]", msg_type="request_welcome")
    mensagem(T, 101, "outbound", dias(4) + timedelta(minutes=1), "Fixture: resposta automatica da Val")
    mensagem(T, 104, "inbound", dias(3), "Fixture: mensagem real recente")
    mensagem(T, 106, "inbound", dias(10) + timedelta(seconds=30), "Fixture botao de encerrar", msg_type="button")
    mensagem(T, 106, "outbound", dias(12), "Fixture: posso ajudar com algo mais?")
    mensagem(T, 106, "outbound", dias(11), "Fixture: segue o orcamento combinado", sender=7)
    mensagem(T, 128, "outbound", dias(11), "Fixture: lembrete sem link")
    mensagem(T, 131, "outbound", dias(5), "Fixture: operadora conduziu a conversa", sender=7)
    mensagem(T, 131, "outbound", dias(1) + timedelta(minutes=1), "Fixture: Val de novo")
    mensagem(T, 132, "inbound", dias(45), "Fixture: ultima mensagem real antiga")
    clique_de_avaliacao(T, 132, NOW - timedelta(hours=1))
    mensagem(T, 133, "inbound", dias(40), "Fixture: mensagem real antiga")
    mensagem(T, 133, "inbound", dias(1), "Fixture reacao", msg_type="reaction")
    mensagem(T, 134, "inbound", dias(10), "Fixture: mensagem real mais antiga")
    mensagem(T, 134, "inbound", dias(5), "Fixture: mensagem real recente")
    clique_de_avaliacao(T, 134, NOW - timedelta(hours=1))
    mensagem(T, 107, "outbound", dias(40), "Fixture agende em https://MarcaConsultas.com.br/fixture")
    mensagem(T, 107, "outbound", dias(9), "Fixture: oi de novo, tudo bem?")
    for n in range(4):
        mensagem(T, 119, "outbound", dias(16 + n), "Fixture lembrete %d sem link" % n)
    mensagem(T, 116, "inbound", datetime(2025, 3, 10, 15, tzinfo=timezone.utc), "Fixture inbound antiga 1")
    mensagem(T, 116, "inbound", datetime(2025, 6, 1, 15, tzinfo=timezone.utc), "Fixture inbound antiga 2")
    mensagem(T, 116, "outbound", datetime(2025, 3, 11, 15, tzinfo=timezone.utc), "Fixture resposta antiga")
    mensagem(T, 117, "inbound", datetime(2026, 2, 15, 12, tzinfo=timezone.utc), "Fixture primeira ao vivo")
    mensagem(T, 117, "inbound", datetime(2026, 2, 20, 12, tzinfo=timezone.utc), "Fixture segunda ao vivo")
    mensagem(T, 126, "inbound", datetime(2025, 10, 15, 12, tzinfo=timezone.utc), "Fixture do backup")
    # Outro tenant: mesmo id de contato, sem etapa; nunca pode ser tocado.
    put(tkey(OUTRA), {"id": OUTRA, "name": "Outra", "is_active": True, "settings": {}})
    put(ckey(OUTRA, "wa_contacts", 101), contato(101, qualification="novo", first_seen_at=dias(5),
                                                 last_inbound_at=dias(4)))


def intake(tid, cid):
    """Escrita da entrada automatica (webhook) no meio da migracao."""
    chave = ckey(tid, "wa_contacts", cid)
    atual = doc(chave)
    campos = fc.intake_fields(atual, NOW, CATALOGO, origin="live")
    campos["last_inbound_at"] = NOW
    with por_fora():
        DB.apply("set", chave, campos, merge=True)


# ---------------------------------------------------------------------------
# Cenarios
# ---------------------------------------------------------------------------

SO_STANDARD = frozenset({"standard"})


def _skip_types_do_webhook():
    """webhook._FUNNEL_INTAKE_SKIP_TYPES lido do fonte (sem importar o webhook)."""
    arvore = ast.parse((ROOT / "webhook.py").read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(isinstance(alvo, ast.Name) and alvo.id == "_FUNNEL_INTAKE_SKIP_TYPES"
                                              for alvo in no.targets):
            return set(ast.literal_eval(no.value.args[0]))
    return None


def cenario_regras_puras():
    titulo("Regras puras (sem I/O)")
    sem_link = (lambda: (False, False))
    for dias_janela, esperado in ((30, []), (60, [103])):
        casou = [cid for cid in (102, 103)
                 if mig.avaliar_regras(SEED[cid], NOW, ("recent_untouched",), dias_janela, consultas_falsas(),
                                       mig.evidencia_de(SEED[cid], NOW)[0])[0]]
        check(casou == esperado, "recent_untouched com %d dias respeita a linhagem 02/09 (casou %s)" % (dias_janela, casou))
    check(mig.prefiltro({"crm_stage": "new", "is_backup": True}, T, SO_STANDARD) == "ja_tem_etapa",
          "pre-filtro: etapa existente vem antes de qualquer outra causa")
    check(mig.prefiltro({"crm_stage": "", "last_inbound_at": NOW}, T, SO_STANDARD) == "campos_crm_sem_etapa",
          "pre-filtro: crm_stage vazio presente e anomalia, nao candidato")

    # scripts-migracao-5: canal fora da entrada automatica.
    vivo = {"last_inbound_at": NOW}
    check(mig.prefiltro(dict(vivo, source_channel_type="coexistence"), T, SO_STANDARD) == "canal_fora_da_entrada",
          "pre-filtro: contato so do coexistence fica fora quando a entrada e so standard")
    check(mig.prefiltro(dict(vivo, source_channel_type="coexistence"), T,
                        frozenset({"standard", "coexistence"})) is None,
          "pre-filtro: tipo aceito (entrada do tenant ou --include-channel-types) entra")
    check(mig.prefiltro(vivo, T, SO_STANDARD) is None and mig.tipo_exibido(vivo) == "(vazio=standard)",
          "pre-filtro: source_channel_type vazio (legado) conta como standard e aparece como tal")
    check(mig.prefiltro({"source_channel_type": "coexistence"}, T, SO_STANDARD) == "sem_inbound",
          "pre-filtro: 'nunca escreveu' vem antes do canal (o bloco de canais so conta quem escreveu)")

    # scripts-migracao-1: recusa comercial nunca vira non_converted.
    base = {"reopen_opt_out": True, "reopen_opt_out_at": NOW.isoformat(), "qualification": "em_atendimento"}
    lidas = []
    causa = mig.descarte_opt_out(dict(base, last_inbound_at=NOW, commercial_contact_block={
        "active": True, "version": 1}), lambda: lidas.append(1) or (False, False))
    check(causa == "recusa_comercial" and not lidas,
          "reopen_opt_out: recusa comercial ativa descarta antes de ler mensagens")
    check(mig.descarte_opt_out(dict(base, last_inbound_at=NOW, commercial_contact_block={"active": "sim"}),
                               sem_link) == "recusa_comercial",
          "reopen_opt_out: registro de recusa invalido tambem bloqueia (lado seguro)")
    check(mig.descarte_opt_out(dict(base, last_inbound_at=NOW, commercial_contact_block={
        "active": False, "version": 2}), sem_link) is None,
          "reopen_opt_out: recusa desfeita (active=false) nao bloqueia")

    # scripts-migracao-3: ausencia REAL de humano no recent_untouched.
    novo = {"qualification": "novo", "created_source": "manual", "first_seen_at": dias(3),
            "last_inbound_at": dias(1)}
    lidas = []
    casadas, descartes = mig.avaliar_regras(novo, NOW, ("recent_untouched",), 30,
                                            consultas_falsas(humano=True, chamadas=lidas), dias(1))
    check(casadas == [] and descartes == {"recent_untouched": "outbound_humano"} and lidas == ["humano"],
          "recent_untouched: outbound com sender_user_id descarta (causa outbound_humano)")
    casadas, descartes = mig.avaliar_regras(novo, NOW, ("recent_untouched",), 30, consultas_falsas(), dias(1))
    check(casadas == ["recent_untouched"] and descartes == {}, "recent_untouched: sem outbound humano casa")
    lidas = []
    mig.avaliar_regras(dict(novo, qualification="em_atendimento"), NOW, ("recent_untouched",), 30,
                       consultas_falsas(humano=True, chamadas=lidas), dias(1))
    mig.avaliar_regras(dict(novo, first_seen_at=dias(40)), NOW, ("recent_untouched",), 30,
                       consultas_falsas(humano=True, chamadas=lidas), dias(1))
    check(lidas == [], "recent_untouched: outbound so e lido depois das condicoes baratas")

    # scripts-migracao-4: recencia pela entrada real fora das origens confiaveis.
    antiga = datetime(2025, 4, 1, 15, tzinfo=timezone.utc)
    historico = dict(novo, created_source="history", first_seen_at=dias(6), last_inbound_at=antiga)
    casadas, descartes = mig.avaliar_regras(historico, NOW, ("recent_untouched",), 30, consultas_falsas(
        primeira=(datetime(2025, 3, 1, 15, tzinfo=timezone.utc), False)), antiga)
    check(casadas == [] and descartes == {"recent_untouched": "entrada_real_fora_da_janela"},
          "recent_untouched: history com first_seen_at recente e 1a inbound antiga nao vira Novo contato")
    casadas, descartes = mig.avaliar_regras(historico, NOW, ("recent_untouched",), 30,
                                            consultas_falsas(primeira=(None, False)), antiga)
    check(descartes == {"recent_untouched": "entrada_real_fora_da_janela"},
          "recent_untouched: history sem inbound registrada usa a entrada limitada a ultima inbound")
    agenda = dict(novo, created_source="state_sync", first_seen_at=datetime(2026, 1, 10, 12, tzinfo=timezone.utc),
                  last_inbound_at=dias(2))
    casadas, _ = mig.avaliar_regras(agenda, NOW, ("recent_untouched",), 30,
                                    consultas_falsas(primeira=(dias(3), False)), dias(2))
    check(casadas == ["recent_untouched"],
          "recent_untouched: agenda antiga com a 1a conversa real recente vira Novo contato")

    # Contrato v2: so na fase do bot (o mesmo gate do webhook) e Novo contato.
    for extra, rotulo in (({"bot_completed": True}, "handoff (bot_completed)"),
                          ({"assigned_to": 8}, "dono (assigned_to)"),
                          ({"assigned_to_uid": "uid-fixture-8"}, "dono (assigned_to_uid)")):
        lidas = []
        casadas, descartes = mig.avaliar_regras(dict(novo, **extra), NOW, ("recent_untouched",), 30,
                                                consultas_falsas(chamadas=lidas), dias(1))
        check(casadas == [] and descartes == {"recent_untouched": "fora_da_fase_do_bot"} and lidas == [],
              "recent_untouched: %s fica fora (fora_da_fase_do_bot, sem ler outbound)" % rotulo)
    check(mig.na_fase_do_bot({}) and mig.na_fase_do_bot({"assigned_to_uid": "  ", "bot_completed": False})
          and not mig.na_fase_do_bot({"bot_completed": True}) and not mig.na_fase_do_bot({"assigned_to": 3}),
          "fase do bot = sem dono e sem bot_completed (webhook)")

    # scripts-migracao-6 + contrato v2: in_reception (ex-open_human) pela
    # ultima inbound REAL, com atendimento aberto, fora da fase do bot.
    humano = {"bot_completed": True, "first_human_contact_at": dias(50), "last_inbound_at": NOW - timedelta(hours=1)}
    for real, esperado, rotulo in (
            ((dias(45), False), {"in_reception": "inbound_real_fora_da_janela"}, "inbound real fora da janela"),
            ((None, False), {"in_reception": "sem_inbound_real"}, "sem inbound real lida"),
            ((dias(5), False), {}, "inbound real na janela casa")):
        casadas, descartes = mig.avaliar_regras(humano, NOW, ("in_reception",), 30,
                                                consultas_falsas(inbound_real=real), NOW - timedelta(hours=1))
        check(descartes == esperado and casadas == ([] if esperado else ["in_reception"]),
              "in_reception: %s" % rotulo)
    lidas = []
    mig.avaliar_regras(dict(humano, last_inbound_at=dias(45)), NOW, ("in_reception",), 30,
                       consultas_falsas(inbound_real=(dias(5), False), chamadas=lidas), dias(45))
    check(lidas == [], "in_reception: last_inbound_at fora da janela nem le mensagens (condicao barata)")
    lidas = []
    casadas, descartes = mig.avaliar_regras(humano, NOW, ("in_reception",), 30, consultas_falsas(
        inbound_real=(dias(1), False), aberto=False, chamadas=lidas), NOW - timedelta(hours=1))
    check(casadas == [] and descartes == {"in_reception": "sem_atendimento_aberto"} and lidas == ["aberto"],
          "in_reception: sem atendimento aberto descarta antes de ler mensagens")
    lidas = []
    historico_humano = {"first_human_contact_at": dias(5), "last_inbound_at": dias(1)}
    casadas, descartes = mig.avaliar_regras(historico_humano, NOW, ("in_reception",), 30, consultas_falsas(
        inbound_real=(dias(1), False), chamadas=lidas), dias(1))
    check(casadas == [] and descartes == {} and lidas == [],
          "in_reception: 1o contato humano antigo com o lead de volta a Val (fase do bot) nao e estado atual")
    casadas, _ = mig.avaliar_regras({"assigned_to_uid": "uid-fixture-8", "last_inbound_at": dias(1)}, NOW,
                                    ("in_reception",), 30, consultas_falsas(inbound_real=(dias(1), False)), dias(1))
    check(casadas == ["in_reception"], "in_reception: dono sem bot_completed (assumiu antes do handoff) casa")

    # Contrato v2 (decisao 3): legacy_outcome. Tabela esperada explicita.
    esperados = {"convertido": ("scheduled", None), "nao_convertido": ("non_converted", "not_informed"),
                 "nao_qualificado": ("disqualified", None), "qualificado": ("unclassified", None)}
    for desfecho, (etapa, motivo) in esperados.items():
        contato_legado = {"qualification": desfecho, "last_inbound_at": dias(100)}
        casadas, descartes = mig.avaliar_regras(contato_legado, NOW, mig.RULES, 30, consultas_falsas(), dias(100))
        destino = mig.destino_da_regra(casadas[0], contato_legado) if casadas else None
        check(casadas == ["legacy_outcome"] and descartes == {} and destino[:2] == (etapa, motivo),
              "legacy_outcome: %s -> %s%s" % (desfecho, etapa, " [%s]" % motivo if motivo else ""))
    check(set(mig.LEGACY_OUTCOME_TARGETS) == set(fc.LEGACY_TERMINAL)
          and all(fc.legacy_qualification_for(CATALOGO, mig.LEGACY_OUTCOME_TARGETS[d][0]) == d
                  for d in ("convertido", "nao_convertido", "nao_qualificado")),
          "legacy_outcome cobre os 4 desfechos terminais e a etapa gravaria o mesmo legado (uma classificacao so)")
    for desfecho in ("novo", "em_atendimento", ""):
        casadas, _ = mig.avaliar_regras({"qualification": desfecho, "last_inbound_at": dias(100)}, NOW,
                                        ("legacy_outcome",), 30, consultas_falsas(), dias(100))
        check(casadas == [], "legacy_outcome: %r nao e desfecho" % desfecho)
    agora_convertido = dict(humano, qualification="convertido", last_inbound_at=dias(1))
    casadas, _ = mig.avaliar_regras(agora_convertido, NOW, mig.RULES, 30,
                                    consultas_falsas(inbound_real=(dias(1), False)), dias(1))
    check(casadas == ["in_reception", "legacy_outcome"],
          "precedencia: o estado atual (in_reception) vence o desfecho antigo (legacy_outcome)")
    for desfecho in sorted(mig.LEGACY_OUTCOME_TARGETS):
        chamado = []
        causa = mig.descarte_opt_out(dict(base, qualification=desfecho, last_inbound_at=NOW),
                                     lambda: chamado.append(1) or (False, False))
        check(causa == "desfecho_registrado" and not chamado,
              "reopen_opt_out: desfecho registrado (%s) descarta antes de ler mensagens" % desfecho)
    reforma = mig.LINEAGE_START
    for dados, esperado, rotulo in (
            ({"last_message_at": reforma - timedelta(seconds=1)}, mig.PERIOD_BEFORE, "ultima mensagem antes"),
            ({"last_message_at": reforma}, mig.PERIOD_AFTER, "ultima mensagem no instante da reforma"),
            ({"last_message_at": reforma - timedelta(days=9), "last_inbound_at": reforma + timedelta(days=1)},
             mig.PERIOD_AFTER, "inbound depois da reforma"),
            ({}, mig.PERIOD_UNKNOWN, "sem data")):
        check(mig.periodo_do_desfecho(dados) == esperado, "periodo do desfecho: %s -> %s" % (rotulo, esperado))
    check(mig.sinal_de_clique({"last_inbound_at": NOW, "last_message_at": dias(1)})
          and not mig.sinal_de_clique({"last_inbound_at": NOW, "last_message_at": NOW})
          and not mig.sinal_de_clique({"last_inbound_at": NOW}),
          "sinal de clique de controle: last_inbound_at estritamente depois de last_message_at")
    check(_skip_types_do_webhook() == set(mig.INBOUND_CONTROL_TYPES),
          "tipos de inbound que nao sao mensagem do paciente = webhook._FUNNEL_INTAKE_SKIP_TYPES")
    check(mig.descarte_opt_out(dict(base, last_inbound_at=NOW + timedelta(minutes=5)), sem_link) is None,
          "reopen_opt_out: inbound dentro da folga de 5 min (o proprio clique) ainda casa")
    check(mig.descarte_opt_out(dict(base, last_inbound_at=NOW + timedelta(minutes=6)), sem_link)
          == "mensagem_depois_do_encerrar", "reopen_opt_out: mensagem depois da folga nao casa")
    check(mig.descarte_opt_out(dict(base, reopen_opt_out_at=None, last_inbound_at=NOW), sem_link)
          == "sem_data_do_encerrar", "reopen_opt_out: sem data do Encerrar nao casa (lado seguro)")
    chamado = []
    mig.descarte_opt_out(dict(base, last_inbound_at=NOW, bot_outcome="link_enviado"),
                         lambda: chamado.append(1) or (False, False))
    check(not chamado, "reopen_opt_out: condicao barata recusa antes de ler mensagens")
    check(mig.evidencia_de({"last_inbound_at": NOW + timedelta(days=1)}, NOW) == (NOW, "data_futura_limitada_a_agora"),
          "evidencia futura limitada a agora")
    r1 = mig.ruleset_version(("legacy_outcome", "in_reception", "recent_untouched"), 30)
    r2 = mig.ruleset_version(("recent_untouched", "in_reception", "legacy_outcome"), 30)
    check(r1 == r2 and r1 == "2026-10-28:recent_untouched+in_reception+legacy_outcome:30d",
          "ruleset_version nova (2026-10-28) e independe da ordem informada", r1)
    check(mig.DEFAULT_RULES == ("recent_untouched", "in_reception", "legacy_outcome")
          and "reopen_opt_out" in mig.RULES and "reopen_opt_out" not in mig.DEFAULT_RULES,
          "regras padrao: recent_untouched, in_reception e legacy_outcome; reopen_opt_out opt-in")
    ids = {mig.activity_id(T, 1, r1), mig.activity_id(OUTRA, 1, r1), mig.activity_id(T, 2, r1),
           mig.activity_id(T, 1, mig.ruleset_version(("recent_untouched",), 30))}
    check(len(ids) == 4 and all(re.fullmatch(r"stage_mig_[0-9a-f]{64}", i) for i in ids),
          "id da Activity deterministico e distinto por tenant, contato e ruleset")
    check(mig.activity_id(T, 1, r1) == mig.activity_id(T, 1, r1), "id da Activity estavel entre execucoes")


def cenario_preflight():
    titulo("Pre-checagens (exit 2, nada lido ou gravado)")
    projeto = config.FIRESTORE_PROJECT_ID
    config.FIRESTORE_PROJECT_ID = ""
    try:
        r = rodar(mig, "--tenant", T, "--template", "clinic_v1")
        check(r.code == 2 and "FIRESTORE_PROJECT_ID" in r.err and DB.reads == r.reads0 and not r.writes
              and "Traceback" not in r.text, "sem FIRESTORE_PROJECT_ID: erro claro, sem leitura e sem stack", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--show")
        check(r.code == 2 and "FIRESTORE_PROJECT_ID" in r.err and DB.reads == r.reads0,
              "set_tenant_funnel sem FIRESTORE_PROJECT_ID tambem recusa antes de ler", r.text)
    finally:
        config.FIRESTORE_PROJECT_ID = projeto
    # scripts-migracao-8: o padrao do config e o prefixo de PRODUCAO; sem a
    # variavel explicita, nada e lido (o config ja foi importado: o .env nao
    # a repoe neste processo).
    prefixo = os.environ.pop("FIRESTORE_COLLECTION_PREFIX")
    try:
        # Tenant inexistente: se a trava faltar, a falha aparece aqui (leitura
        # do doc do tenant) sem gravar nada que contamine os outros cenarios.
        r = rodar(mig, "--tenant", "sim-nao-existe", "--template", "clinic_v1", "--yes")
        check(r.code == 2 and "defina FIRESTORE_COLLECTION_PREFIX" in r.err and DB.reads == r.reads0
              and not r.writes and "Traceback" not in r.text,
              "migracao sem FIRESTORE_COLLECTION_PREFIX explicito: exit 2 antes de ler (mesmo com --yes)", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--enable", "--template", "clinic_v1", "--yes")
        check(r.code == 2 and "defina FIRESTORE_COLLECTION_PREFIX" in r.err and DB.reads == r.reads0
              and not r.writes, "set_tenant_funnel sem FIRESTORE_COLLECTION_PREFIX explicito: exit 2 antes de ler",
              r.text)
    finally:
        os.environ["FIRESTORE_COLLECTION_PREFIX"] = prefixo
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--include-channel-types", "standard,foo")
    check(r.code == 2 and "foo" in r.err and DB.reads == r.reads0, "--include-channel-types com tipo desconhecido "
          "recusa sem ler", r.text)
    r = rodar(mig, "--tenant", T, "--undo", str(LOGS / "qualquer.jsonl"), "--include-channel-types", "coexistence")
    check(r.code == 2 and "--include-channel-types" in r.err and DB.reads == r.reads0,
          "--undo nao combina com --include-channel-types", r.text)
    r = rodar(mig, "--tenant", T)
    check(r.code == 2 and "--template" in r.out and not r.writes,
          "tenant sem settings.funnel exige --template", r.text)
    r = rodar(mig, "--tenant", "sim-nao-existe", "--template", "clinic_v1")
    check(r.code == 2 and "nao existe" in r.out and not r.writes, "tenant inexistente recusa", r.text)
    put(tkey("sim-v0"), {"id": "sim-v0", "settings": {"funnel": {"enabled": True, "template": "clinic_v0"}}})
    r = rodar(mig, "--tenant", "sim-v0", "--template", "clinic_v1")
    check(r.code == 2 and "nao casa" in r.out, "--template diferente do settings.funnel do tenant recusa", r.text)
    r = rodar(mig, "--tenant", "sim-v0")
    check(r.code == 2 and "clinic_v0" in r.out, "template do tenant desconhecido no codigo recusa", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", "recent_untouched,inventada")
    check(r.code == 2 and "inventada" in r.err and DB.reads == r.reads0, "regra desconhecida recusa sem ler", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", "recent_untouched,open_human")
    check(r.code == 2 and "in_reception" in r.err and DB.reads == r.reads0,
          "open_human (nome antigo) recusado sem ler, com a dica do novo nome (in_reception)", r.text)
    link = config.REOPEN_DESFECHO_LINK
    config.REOPEN_DESFECHO_LINK = ""
    try:
        r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", "reopen_opt_out")
        check(r.code == 2 and "REOPEN_DESFECHO_LINK" in r.out and DB.reads == r.reads0,
              "reopen_opt_out sem trecho do link recusa (nao ha como provar 'nenhum link')", r.text)
    finally:
        config.REOPEN_DESFECHO_LINK = link
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rate", "0")
    check(r.code == 2 and not r.writes, "--rate 0 recusado", r.text)
    r = rodar(mig, "--tenant", T, "--only-contact", "12,abc")
    check(r.code == 2 and DB.reads == r.reads0, "--only-contact so aceita ids numericos", r.text)
    falso = LOGS / "inexistente.jsonl"
    r = rodar(mig, "--tenant", T, "--undo", str(falso))
    check(r.code == 2, "--undo de arquivo inexistente recusa", r.text)


def cenario_dry_run():
    titulo("Dry-run com todas as regras: classificacao, nenhuma escrita")
    mig.OUTBOUND_SCAN = 3  # forca o 'historico truncado' do contato 119
    sem_mudar = {k: copy.deepcopy(v) for k, v in DB.docs.items()}
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1",
              "--rules", "recent_untouched,in_reception,legacy_outcome,reopen_opt_out", "--sample", "50",
              "--rate", "200")
    check(r.code == 0, "dry-run termina com exit 0", r.text)
    check(dry_ok(r) and DB.docs == sem_mudar, "dry-run: trava antes da 1a leitura e zero escritas", r.text)
    check("projeto: %s" % PROJECT in r.out and "prefixo: %s" % PREFIX in r.out and "tenant:  %s" % T in r.out
          and r.out.index("projeto:") < r.out.index("funil do tenant"),
          "imprime projeto, prefixo e tenant antes das leituras", r.text)
    check("legacy_outcome: convertido -> scheduled, nao_convertido -> non_converted [not_informed], "
          "nao_qualificado -> disqualified, qualificado -> unclassified (a migracao nunca escreve qualification)"
          in r.out, "cabecalho mostra o mapa do legacy_outcome (decisao 3) e que qualification nao e escrita", r.text)
    check("contatos lidos: 43" in r.out, "43 contatos lidos (so do tenant)", r.text)
    check("candidatos (sem etapa): 37" in r.out and "a alterar: 37" in r.out, "37 candidatos, todos a alterar", r.text)
    for rotulo, n in (("recent_untouched -> new", 3), ("in_reception -> in_service", 5),
                      ("reopen_opt_out -> non_converted [not_informed]", 1),
                      ("legacy_outcome -> scheduled", 3), ("legacy_outcome -> non_converted [not_informed]", 1),
                      ("legacy_outcome -> disqualified", 2), ("legacy_outcome -> unclassified", 1),
                      ("no_rule -> unclassified", 21)):
        check(linha(r.out, rotulo, n), "regra %s = %d" % (rotulo, n), r.text)
    for causa in ("ja_tem_etapa", "backup", "sem_inbound", "lgpd_revogado", "campos_crm_sem_etapa", "tenant_divergente"):
        check(linha(r.out, causa, 1), "pre-filtro %s = 1" % causa, r.text)
    check(amostra(r.out, "recent_untouched") == [101, 115, 130]
          and amostra(r.out, "in_reception") == [104, 134, 138, 139, 141]
          and amostra(r.out, "reopen_opt_out") == [106]
          and amostra(r.out, "legacy_outcome") == [109, 121, 135, 136, 137, 142, 143],
          "ids por regra (com --sample) batem com as fixtures", r.text)
    # scripts-migracao-1: recusa comercial fora do non_converted, contada por regra.
    check(linha(bloco(r.out, "reopen_opt_out NAO aplicado"), "recusa_comercial", 2)
          and amostra(r.out, "opt_out_recusa_comercial") == [128, 129],
          "Encerrar + recusa comercial (valida e invalida) nao vira non_converted: descarte recusa_comercial",
          r.text)
    recusas = bloco(r.out, "recusa comercial ativa")
    check(linha(recusas, "no_rule", 2) and linha(recusas, "recent_untouched", 1)
          and amostra(r.out, "recusa_comercial_no_rule") == [128, 129]
          and amostra(r.out, "recusa_comercial_recent_untouched") == [130],
          "relatorio conta, por regra vencedora, os contatos com recusa comercial ativa (e os ids com --sample)",
          r.text)
    # scripts-migracao-3: outbound humano descarta o recent_untouched.
    recentes = bloco(r.out, "recent_untouched NAO aplicado")
    check(linha(recentes, "outbound_humano", 1)
          and amostra(r.out, "recent_untouched_outbound_humano") == [131] and 131 in amostra(r.out, "no_rule"),
          "novo sem carimbo mas com outbound da operadora (devolvido ao bot) vai para A classificar", r.text)
    # Contrato v2: handoff da Val sem resposta humana (139) e dono (141) nao
    # sao Novo contato: fora da fase do bot, o in_reception decide.
    check(linha(recentes, "fora_da_fase_do_bot", 2)
          and amostra(r.out, "recent_untouched_fora_da_fase_do_bot") == [139, 141],
          "novo fora da fase do bot (handoff, dono) nao vira Novo contato: vai para Em atendimento", r.text)
    # scripts-migracao-6 + v2: in_reception pela inbound real, com atendimento aberto.
    recepcao = bloco(r.out, "in_reception NAO aplicado")
    check(linha(recepcao, "inbound_real_fora_da_janela", 2)
          and amostra(r.out, "in_reception_inbound_real_fora_da_janela") == [132, 133],
          "in_reception: clique de avaliacao (132) e reacao (133) recentes sobre conversa antiga nao contam", r.text)
    check(linha(recepcao, "sem_atendimento_aberto", 1) and amostra(r.out, "in_reception_sem_atendimento_aberto") == [140]
          and 140 in amostra(r.out, "no_rule"),
          "in_reception: atendimento fechado (so o backup aberto) nao e estado atual: A classificar", r.text)
    check(141 in amostra(r.out, "in_reception"),
          "request_welcome (abriu o chat) conta como mensagem do paciente (decisao 6 do PO)", r.text)
    cliques = bloco(r.out, "last_inbound_at depois de last_message_at")
    check(linha(cliques, "no_rule", 1) and linha(cliques, "in_reception", 1)
          and amostra(r.out, "clique_de_controle_no_rule") == [132]
          and amostra(r.out, "clique_de_controle_in_reception") == [134],
          "relatorio mostra, por regra, quem tem last_inbound_at depois de last_message_at", r.text)
    # Contrato v2: desfechos antigos aplicados, separados pela reforma de 02/09.
    legado = bloco(r.out, "legacy_outcome aplicado")
    check(linha(legado, "convertido -> scheduled / depois_da_reforma", 2)
          and linha(legado, "convertido -> scheduled / antes_da_reforma", 1)
          and linha(legado, "nao_convertido -> non_converted / depois_da_reforma", 1)
          and linha(legado, "nao_qualificado -> disqualified / antes_da_reforma", 1)
          and linha(legado, "nao_qualificado -> disqualified / depois_da_reforma", 1)
          and linha(legado, "qualificado -> unclassified / depois_da_reforma", 1)
          and len(legado.splitlines()) == 6 and "reforma das qualificacoes em 2026-09-02" in r.out
          and amostra(r.out, "legacy_outcome_antes_da_reforma") == [121, 143],
          "relatorio separa os desfechos aplicados antes e depois da reforma das qualificacoes", r.text)
    check("qualificado (decisao 3: A classificar, contado a parte): 1" in r.out,
          "qualificado -> A classificar contado a parte", r.text)
    conflitos = bloco(r.out, "conflitos desfecho antigo x estado atual")
    check(linha(conflitos, "in_reception: convertido (seria scheduled) / depois_da_reforma", 1)
          and len(conflitos.splitlines()) == 1 and amostra(r.out, "conflito_convertido") == [138],
          "conflito: convertido de volta a recepcao fica Em atendimento e sai no relatorio", r.text)
    # scripts-migracao-5: contagem por tipo de canal.
    check("canais da entrada automatica: standard" in r.out
          and linha(bloco(r.out, "tipo de canal"), "standard: entrada_do_tenant", 37),
          "cabecalho mostra os canais da entrada e o relatorio conta por tipo de canal", r.text)
    check(amostra(r.out, "ja_tem_etapa") == [111] and amostra(r.out, "lgpd_revogado") == [114],
          "etapa existente e revogacao LGPD ficam fora", r.text)
    check(amostra(r.out, "opt_out_link_de_agendamento_enviado") == [107],
          "Encerrar + link da Val em ciclo ANTERIOR (antes do bot_released_at) nao vira non_converted", r.text)
    check(107 in amostra(r.out, "no_rule"), "contato 107 cai em A classificar", r.text)
    for causa, cids in (("mensagem_depois_do_encerrar", [108]), ("desfecho_registrado", [109, 142]),
                        ("desfecho_de_agendamento", [110]), ("historico_truncado", [119])):
        check(amostra(r.out, "opt_out_" + causa) == cids, "reopen_opt_out recusado por %s" % causa, r.text)
    check(linha(r.out, "reopen_opt_out / in_reception", 1) and linha(r.out, "in_reception / legacy_outcome", 1),
          "sobreposicoes reopen_opt_out x in_reception e in_reception x legacy_outcome reportadas", r.text)
    check(linha(r.out, "reopen_opt_out / em_atendimento", 1) and linha(r.out, "legacy_outcome / nao_qualificado", 2)
          and linha(r.out, "in_reception / convertido", 1),
          "qualification por regra no relatorio (so enum)", r.text)
    check(linha(r.out, "last_inbound_at: texto_iso_coerido", 1) and linha(r.out, "last_inbound_at: texto_invalido", 1)
          and linha(r.out, "reopen_opt_out_at: texto_iso_coerido", 6),
          "anomalias de tipo de data reportadas por campo", r.text)
    check(linha(r.out, "evidencia_por_first_seen_at", 1) and linha(r.out, "data_futura_limitada_a_agora", 1),
          "evidencia ilegivel e futura reportadas", r.text)
    check(linha(r.out, "primeira_inbound", 3), "history/state_sync/backup_import usam a 1a inbound real", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "regras: recent_untouched, in_reception, legacy_outcome (" in r.out
          and linha(r.out, "recent_untouched -> new", 3) and linha(r.out, "in_reception -> in_service", 6)
          and linha(r.out, "legacy_outcome -> scheduled", 3) and linha(r.out, "no_rule -> unclassified", 21)
          and "reopen_opt_out ->" not in r.out and not re.search(r"^amostra ", r.out, re.M),
          "regras padrao (recent_untouched, in_reception, legacy_outcome): o Encerrar (106) sem a regra opt-in "
          "fica Em atendimento; nenhum id sem --sample", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--limit", "3", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "candidatos (sem etapa): 3" in r.out and "--limit 3" in r.out,
          "--limit para no N-esimo candidato (relatorio parcial)", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", "recent_untouched,in_reception",
              "--only-contact", "101,104,999,111", "--sample", "5", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and amostra(r.out, "recent_untouched") == [101]
          and amostra(r.out, "in_reception") == [104] and amostra(r.out, "inexistente") == [999]
          and amostra(r.out, "ja_tem_etapa") == [111], "--only-contact le so os ids pedidos", r.text)
    # Corte da reforma das qualificacoes (02/09): mesmo com a janela de 60
    # dias, "novo" de antes da reforma nao vira Novo contato.
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--recent-days", "60", "--only-contact", "102,103",
              "--sample", "5", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and amostra(r.out, "recent_untouched") == [103]
          and amostra(r.out, "no_rule") == [102] and "entrada >= 2026-09-02" in r.out
          and "ruleset_version: 2026-10-28:recent_untouched+in_reception+legacy_outcome:60d" in r.out,
          "janela de 60 dias: novo de 03/09 vira Novo contato, o de 30/08 (antes da reforma) nao", r.text)
    SLEEPS.clear()
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rate", "20")
    check(r.code == 0 and len(SLEEPS) == 36 and abs(sum(SLEEPS) - 36 / 20.0) < 1e-9,
          "--rate 20: 37 candidatos levam 1,8 s de ritmo (36 esperas de 50 ms)", r.text)


# Pre-filtrados do tenant T: 111 etapa, 112 backup, 113 sem inbound, 114 LGPD,
# 118 crm_* solto, 120 outro tenant. 124/125: o intake grava no meio.
FORA_DA_MIGRACAO = (111, 112, 113, 114, 118, 120)
INTAKE_NO_MEIO = (124, 125)


def candidatos():
    return [c for c in sorted(SEED) if c not in FORA_DA_MIGRACAO]


def esperado_v2():
    """cid -> (etapa, motivo, changed_at, entrada, coorte, max_order, regra,
    confianca) com as 4 regras ligadas (inclusive o opt-in reopen_opt_out)."""
    utc = timezone.utc
    return {
        101: ("new", None, dias(4), dias(5), "2026-10", 10, "recent_untouched", "high"),
        # Novo antes da linhagem (30/08) e fora da janela de 30 dias (03/09).
        102: ("unclassified", None, dias(3), datetime(2026, 8, 30, 12, tzinfo=utc), "2026-08", 0, "no_rule", "low"),
        103: ("unclassified", None, dias(2), datetime(2026, 9, 3, 12, tzinfo=utc), "2026-09", 0, "no_rule", "low"),
        104: ("in_service", None, dias(3), dias(90), "2026-07", 20, "in_reception", "medium"),
        # 1o contato humano antigo, lead de volta a Val: nao e estado atual.
        105: ("unclassified", None, dias(45), dias(90), "2026-07", 0, "no_rule", "low"),
        106: ("non_converted", "not_informed", dias(10) + timedelta(seconds=30), dias(90), "2026-07", 0,
              "reopen_opt_out", "medium"),
        107: ("unclassified", None, dias(8), dias(90), "2026-07", 0, "no_rule", "low"),
        108: ("unclassified", None, dias(2), dias(90), "2026-07", 0, "no_rule", "low"),
        # Encerrar + convertido registrado: o legacy_outcome cuida (Cliente Agendado).
        109: ("scheduled", None, dias(9), dias(90), "2026-07", 40, "legacy_outcome", "medium"),
        110: ("unclassified", None, dias(7), dias(90), "2026-07", 0, "no_rule", "low"),
        115: ("new", None, datetime(2026, 10, 20, 10, tzinfo=utc), datetime(2026, 10, 19, 8, tzinfo=utc),
              "2026-10", 10, "recent_untouched", "high"),
        116: ("unclassified", None, datetime(2025, 6, 1, 15, tzinfo=utc), datetime(2025, 3, 10, 15, tzinfo=utc),
              "2025-03", 0, "no_rule", "low"),
        117: ("unclassified", None, datetime(2026, 2, 20, 12, tzinfo=utc), datetime(2026, 2, 15, 12, tzinfo=utc),
              "2026-02", 0, "no_rule", "low"),
        119: ("unclassified", None, dias(15), dias(90), "2026-07", 0, "no_rule", "low"),
        # Nao qualificado antes da reforma, arquivado; first_seen_at (90 d)
        # depois da ultima inbound (100 d): entrada limitada a evidencia.
        121: ("disqualified", None, dias(100), dias(100), "2026-07", 0, "legacy_outcome", "medium"),
        122: ("unclassified", None, dias(200), dias(200), "2026-04", 0, "no_rule", "low"),
        123: ("unclassified", None, NOW, dias(300), "2025-12", 0, "no_rule", "low"),
        126: ("unclassified", None, datetime(2025, 11, 1, 12, tzinfo=utc), datetime(2025, 10, 15, 12, tzinfo=utc),
              "2025-10", 0, "no_rule", "low"),
        127: ("unclassified", None, datetime(2025, 5, 5, 12, tzinfo=utc), datetime(2025, 5, 5, 12, tzinfo=utc),
              "2025-05", 0, "no_rule", "low"),
        # Recusa comercial (valida e invalida) com Encerrar: A classificar.
        128: ("unclassified", None, dias(10), dias(90), "2026-07", 0, "no_rule", "low"),
        129: ("unclassified", None, dias(9), dias(90), "2026-07", 0, "no_rule", "low"),
        130: ("new", None, dias(2), dias(3), "2026-10", 10, "recent_untouched", "high"),
        # Outbound humano: nao e Novo contato.
        131: ("unclassified", None, dias(1), dias(6), "2026-10", 0, "no_rule", "low"),
        # Fora do in_reception: changed_at segue a regra geral (last_inbound_at).
        132: ("unclassified", None, NOW - timedelta(hours=1), dias(90), "2026-07", 0, "no_rule", "low"),
        133: ("unclassified", None, dias(1), dias(90), "2026-07", 0, "no_rule", "low"),
        # in_reception: changed_at/evidence_at = ultima mensagem REAL, nao o clique.
        134: ("in_service", None, dias(5), dias(90), "2026-07", 20, "in_reception", "medium"),
        135: ("scheduled", None, dias(10), dias(40), "2026-09", 40, "legacy_outcome", "medium"),
        136: ("non_converted", "not_informed", dias(20), dias(60), "2026-08", 0, "legacy_outcome", "medium"),
        # Qualificado: A classificar (contado a parte), confianca baixa.
        137: ("unclassified", None, dias(15), dias(90), "2026-07", 0, "legacy_outcome", "low"),
        # Conflito: convertido de volta a recepcao -> Em atendimento (estado atual).
        138: ("in_service", None, dias(2), dias(90), "2026-07", 20, "in_reception", "medium"),
        # Handoff da Val sem resposta humana ainda: Em atendimento.
        139: ("in_service", None, dias(2), dias(3), "2026-10", 20, "in_reception", "medium"),
        140: ("unclassified", None, dias(3), dias(90), "2026-07", 0, "no_rule", "low"),
        # Dono antes do handoff; a unica inbound e o request_welcome.
        141: ("in_service", None, dias(3), dias(4), "2026-10", 20, "in_reception", "medium"),
        142: ("disqualified", None, dias(9), dias(90), "2026-07", 0, "legacy_outcome", "medium"),
        143: ("scheduled", None, datetime(2026, 5, 10, 12, tzinfo=utc), datetime(2026, 4, 1, 12, tzinfo=utc),
              "2026-04", 40, "legacy_outcome", "medium"),
    }


def whitelist_da_gravacao(proprias, n):
    """Escritas do script na gravacao: so set(merge) dos 10 campos crm_* no
    contato e create da Activity da migracao, n de cada."""
    contatos_w = [w for w in proprias if w["chave"][2] == "wa_contacts"]
    atividades_w = [w for w in proprias if w["chave"][2] == "crm_activities"]
    return (len(proprias) == 2 * n and len(contatos_w) == n and len(atividades_w) == n
            and all(w["op"] == "set" and w["merge"] and w["campos"] == sorted(fc.CONTACT_STAGE_FIELDS)
                    for w in contatos_w)
            and all(w["op"] == "create" and _ACTIVITY_MIG.fullmatch(w["chave"][3]) for w in atividades_w))


_ACTIVITY_MIG = re.compile(r"stage_mig_[0-9a-f]{64}")


def cenario_gravacao():
    titulo("--yes com as 4 regras: grava em transacao; intake no meio nunca e sobrescrito")
    regras = mig.RULES
    ruleset = mig.ruleset_version(regras, 30)
    esperado = esperado_v2()
    check(sorted(esperado) == [c for c in candidatos() if c not in INTAKE_NO_MEIO],
          "fixture: a tabela esperada cobre todos os candidatos menos os do intake")
    DB.hook_tx_read[ckey(T, "wa_contacts", 124)] = lambda: intake(T, 124)
    DB.hook_commit[ckey(T, "wa_contacts", 125)] = lambda: intake(T, 125)
    outra_antes = doc(ckey(OUTRA, "wa_contacts", 101))
    tentativas = DB.tx_attempts
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", ",".join(regras),
              "--sample", "50", "--rate", "200", "--yes")
    n = len(esperado)
    check(r.code == 0 and r.travas == [], "--yes termina com exit 0 e sem trava", r.text)
    check("a alterar (gravados): %d" % n in r.out and linha(r.out, "etapa_gravada_durante_execucao", 2),
          "%d gravados; 2 pulados porque o intake gravou durante a execucao" % n, r.text)
    check(DB.tx_attempts - tentativas == n + 3,
          "conflito no commit refaz a transacao (%d + 1 + 2 tentativas)" % n)
    check(sorted(amostra(r.out, "etapa_gravada_durante_execucao")) == list(INTAKE_NO_MEIO),
          "intake entre leitura e transacao (124) e entre leitura e commit (125)", r.text)
    for cid in INTAKE_NO_MEIO:
        atual = doc(ckey(T, "wa_contacts", cid))
        check(atual.get("crm_stage_source") == "intake" and atual.get("crm_stage_activity_id") is None
              and doc(ckey(T, "crm_activities", mig.activity_id(T, cid, ruleset))) is None,
              "contato %d mantem a etapa do intake e nao ganha Activity da migracao" % cid)
    check(doc(ckey(T, "wa_contacts", 111)) == SEED[111], "etapa existente (111) intocada, campo a campo")
    check(doc(ckey(T, "wa_contacts", 118)) == SEED[118], "crm_* solto (118) intocado")
    check(doc(ckey(OUTRA, "wa_contacts", 101)) == outra_antes, "contato de outro tenant intocado")
    colecoes = {chave[2] for _, chave in r.writes}
    check(colecoes == {"wa_contacts", "crm_activities"} and all(chave[1] == T for _, chave in r.writes),
          "so escreve wa_contacts e crm_activities do proprio tenant")
    check(whitelist_da_gravacao(r.proprias, n),
          "whitelist de escrita: contato so com set(merge) dos 10 campos crm_*; Activity so por create", r.proprias)
    check(all(doc(ckey(T, "wa_contacts", c)).get("qualification") == SEED[c].get("qualification")
              for c in candidatos()),
          "a migracao nunca escreve qualification (desfecho antigo intocado em todos os candidatos)")
    leituras = DB.reads
    try:
        mig.gravar_contato(T, 101, SEED[101], {"fields": {fc.F_STAGE: "scheduled", "qualification": "convertido"},
                                               "activity_id": "x", "activity": {}}, SO_STANDARD)
        recusou = False
    except RuntimeError:
        recusou = True
    check(recusou and DB.reads == leituras,
          "gravar_contato recusa plano com campo fora de crm_* (ex.: qualification) antes de ler ou gravar")
    # O relatorio da gravacao traz o mesmo plano do dry-run.
    check(linha(r.out, "legacy_outcome -> scheduled", 3) and linha(r.out, "no_rule -> unclassified", 21)
          and linha(r.out, "reopen_opt_out -> non_converted [not_informed]", 1)
          and linha(bloco(r.out, "conflitos desfecho antigo x estado atual"),
                    "in_reception: convertido (seria scheduled) / depois_da_reforma", 1)
          and linha(bloco(r.out, "legacy_outcome aplicado"), "convertido -> scheduled / antes_da_reforma", 1),
          "relatorio da gravacao: regras, conflito e desfechos por periodo da reforma", r.text)
    etapas = {}
    for cid, (etapa, motivo, mudou, entrou, coorte, ordem, regra, confianca) in esperado.items():
        atual = doc(ckey(T, "wa_contacts", cid))
        etapas[etapa] = etapas.get(etapa, 0) + 1
        aid = mig.activity_id(T, cid, ruleset)
        atividade = doc(ckey(T, "crm_activities", aid)) or {}
        ok = (atual.get("crm_stage") == etapa and atual.get("crm_stage_version") == 1
              and atual.get("crm_stage_source") == "migration" and atual.get("crm_stage_activity_id") == aid
              and atual.get("crm_stage_changed_at") == mudou and isinstance(atual.get("crm_stage_changed_at"), datetime)
              and atual.get("crm_funnel_entered_at") == entrou and atual.get("crm_cohort_month") == coorte
              and atual.get("crm_max_reached_order") == ordem and atual.get("crm_stage_changed_by_user_id") is None
              and atual.get("crm_stage_changed_by_uid") == "")
        check(ok, "contato %d: %s, changed_at=evidencia, entrada %s, coorte %s, max %d" % (
            cid, etapa, entrou.date(), coorte, ordem), atual)
        check(sem_crm(atual) == SEED[cid], "contato %d: nenhum campo fora de crm_* mudou" % cid)
        dados = atividade.get("data") or {}
        ok = (atividade.get("event_type") == fc.EVENT_MIGRATED and atividade.get("actor_type") == "migration"
              and atividade.get("contact_id") == cid and atividade.get("tenant_id") == T
              and atividade.get("task_id") is None and atividade.get("conversation_id") is None
              and atividade.get("from_stage") is None and atividade.get("to_stage") == etapa
              and atividade.get("stage_reason") == motivo and atividade.get("from_reason") is None
              and atividade.get("entry_kind") is None
              and atividade.get("occurred_at") == NOW and atividade.get("recorded_at") == NOW
              and atividade.get("result_version") == 1
              and re.fullmatch(r"[0-9a-f]{64}", atividade.get("request_fingerprint") or "") is not None
              and str(atividade.get("operation_id") or "").startswith("mig_")
              and dados.get("rule_id") == regra and dados.get("ruleset_version") == ruleset
              and dados.get("evidence_at") == mudou and dados.get("confidence") == confianca
              and dados.get("stage_version") == 1 and dados.get("source") == "migration"
              and dados.get("source_qualification") == SEED[cid].get("qualification"))
        check(ok, "Activity crm_stage_migrated do contato %d (regra %s)" % (cid, regra), atividade)
    check(etapas == {"new": 3, "in_service": 5, "non_converted": 2, "scheduled": 3, "disqualified": 2,
                     "unclassified": n - 15},
          "distribuicao por etapa; a migracao nunca infere Aguardando retorno nem Paciente em acompanhamento", etapas)
    atividades = [doc(ckey(T, "crm_activities", mig.activity_id(T, c, ruleset))) for c in esperado]
    bruto = json.dumps(atividades, default=str, ensure_ascii=False)
    check(not [p for p in PII if p in bruto], "Activities sem nome, telefone, wa_id, notas ou mensagens")
    check(not DB.naive, "nenhum datetime ingenuo gravado (tudo UTC com fuso)", DB.naive)
    arquivos = sorted(LOGS.glob("funnel_migration_undo_%s_*.jsonl" % T))
    check(len(arquivos) == 1, "um arquivo de undo JSONL em logs/")
    if not arquivos:
        return None, ruleset
    linhas = [json.loads(x) for x in arquivos[0].read_text(encoding="utf-8").splitlines() if x.strip()]
    cabecalho = linhas[0]
    check(cabecalho.get("type") == "header" and cabecalho.get("tenant") == T and cabecalho.get("project") == PROJECT
          and cabecalho.get("prefix") == PREFIX and cabecalho.get("ruleset_version") == ruleset
          and cabecalho.get("rules") == list(mig.RULES),
          "cabecalho do undo prende tenant, projeto, prefixo, ruleset e regras")
    contatos = [x for x in linhas[1:] if x.get("type") == "contact"]
    check(len(contatos) == len(candidatos()) and sorted(x["contact_id"] for x in contatos) == candidatos(),
          "uma linha de undo por candidato, escrita ANTES da transacao (inclusive 124/125)")
    check(all(set(x["before"].values()) == {mig.AUSENTE} and set(x["fields"]) == set(fc.CONTACT_STAGE_FIELDS)
              for x in contatos), "undo registra os 10 campos crm_* como __AUSENTE__ antes")
    check(all(x["stage"] == esperado[x["contact_id"]][0] and x["rule_id"] == esperado[x["contact_id"]][6]
              and x["reason"] == esperado[x["contact_id"]][1] for x in contatos if x["contact_id"] in esperado),
          "linha de undo registra etapa, motivo e regra gravados")
    bruto = arquivos[0].read_text(encoding="utf-8")
    check(not [p for p in PII if p in bruto], "undo sem nome, telefone, wa_id, notas ou mensagens")
    return arquivos[0], ruleset


def cenario_idempotencia(ruleset):
    titulo("Idempotencia: segunda execucao nao grava nada; regra a mais ou a menos nao reclassifica")
    escritas = len(DB.writes)
    com_etapa = len(candidatos()) + 1  # + 111, que ja tinha etapa
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", ",".join(mig.RULES),
              "--rate", "200", "--yes")
    check(r.code == 0 and len(DB.writes) == escritas and "candidatos (sem etapa): 0" in r.out
          and "a alterar (gravados): 0" in r.out and linha(r.out, "ja_tem_etapa", com_etapa),
          "2a execucao --yes (mesmas regras): 0 candidatos, 0 escritas", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "a alterar: 0" in r.out and linha(r.out, "ja_tem_etapa", com_etapa),
          "dry-run com as regras padrao (outro ruleset): a alterar 0 (quem tem etapa nunca e reclassificado)", r.text)


def cenario_undo(arquivo, ruleset):
    titulo("Undo: so o que a migracao gravou e ninguem mudou")
    if arquivo is None:
        check(False, "undo da gravacao disponivel para o teste do --undo")
        return
    chave101 = ckey(T, "wa_contacts", 101)
    with por_fora():
        DB.apply("set", chave101, {"crm_stage": "in_service", "crm_stage_version": 2, "crm_stage_source": "user",
                                   "crm_stage_activity_id": "stage_" + "b" * 64, "crm_stage_changed_at": NOW,
                                   "crm_stage_changed_by_user_id": 7, "crm_stage_changed_by_uid": "uid-fixture-7"},
                 merge=True)
    usuario = doc(chave101)
    intake124, intake125 = doc(ckey(T, "wa_contacts", 124)), doc(ckey(T, "wa_contacts", 125))
    mudaram = [101] + list(INTAKE_NO_MEIO)
    revertidos = [c for c in candidatos() if c not in mudaram]
    n = len(revertidos)
    r = rodar(mig, "--tenant", T, "--undo", str(arquivo), "--rules", "in_reception")
    check(r.code == 2 and DB.reads == r.reads0, "--undo nao combina com --rules", r.text)
    r = rodar(mig, "--tenant", T, "--undo", str(arquivo), "--sample", "50", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and linha(r.out, "a_reverter", n)
          and linha(r.out, "mudou_depois_da_migracao", 3),
          "undo dry-run: %d a reverter, 3 mudaram, nada gravado" % n, r.text)
    check(sorted(amostra(r.out, "mudou_depois_da_migracao")) == mudaram,
          "mudanca do usuario (101) e etapa do intake (124/125) nao sao revertidas", r.text)
    AGORA[0] = NOW + timedelta(hours=1)
    try:
        r = rodar(mig, "--tenant", T, "--undo", str(arquivo), "--rate", "200", "--yes")
    finally:
        AGORA[0] = NOW
    check(r.code == 0 and linha(r.out, "revertido", n) and "a reverter (revertidos): %d" % n in r.out,
          "undo --yes reverte %d" % n, r.text)
    contatos_w = [w for w in r.proprias if w["chave"][2] == "wa_contacts"]
    reversoes_w = [w for w in r.proprias if w["chave"][2] == "crm_activities"]
    check(len(r.proprias) == 2 * n and len(contatos_w) == n and len(reversoes_w) == n
          and all(w["op"] == "update" and w["campos"] == sorted(fc.CONTACT_STAGE_FIELDS)
                  and all(v is gfs.DELETE_FIELD for v in w["valores"].values()) for w in contatos_w)
          and all(w["op"] == "create" and w["chave"][3].startswith(mig.REVERT_PREFIX) for w in reversoes_w),
          "whitelist do undo: so apaga os 10 campos crm_* (DELETE_FIELD) e cria a reversao", r.proprias)
    check(doc(chave101) == usuario, "contato movido pelo usuario segue intacto")
    check(doc(ckey(T, "wa_contacts", 124)) == intake124 and doc(ckey(T, "wa_contacts", 125)) == intake125,
          "etapa do intake segue intacta")
    check(all(doc(ckey(T, "wa_contacts", c)) == SEED[c] for c in revertidos),
          "revertidos voltam exatamente ao doc original (campos crm_* removidos; qualification intocada)")
    ok = True
    for c in revertidos:
        aid = mig.activity_id(T, c, ruleset)
        original = doc(ckey(T, "crm_activities", aid))
        rev = doc(ckey(T, "crm_activities", mig.revert_id(T, c, aid))) or {}
        ok = ok and original is not None and (
            rev.get("event_type") == fc.EVENT_MIGRATION_REVERTED and rev.get("actor_type") == "migration"
            and rev.get("to_stage") is None and rev.get("from_stage") == original["to_stage"]
            and rev.get("from_reason") == original["stage_reason"]
            and (rev.get("data") or {}).get("reverted_activity_id") == aid
            and rev.get("occurred_at") == NOW + timedelta(hours=1))
    check(ok, "cada reversao cria crm_stage_migration_reverted e preserva a Activity original")
    escritas = len(DB.writes)
    r = rodar(mig, "--tenant", T, "--undo", str(arquivo), "--rate", "200", "--yes")
    check(r.code == 0 and len(DB.writes) == escritas and linha(r.out, "ja_revertido", n)
          and linha(r.out, "mudou_depois_da_migracao", 3), "undo repetido: nada gravado (idempotente)", r.text)
    alheio = LOGS / "undo_outro_projeto.jsonl"
    texto = arquivo.read_text(encoding="utf-8").replace('"project": "%s"' % PROJECT, '"project": "outro-projeto"')
    alheio.write_text(texto, encoding="utf-8")
    r = rodar(mig, "--tenant", T, "--undo", str(alheio), "--rate", "200", "--yes")
    check(r.code == 2 and not r.writes and "outro-projeto" in r.out, "undo de outro projeto/prefixo recusado", r.text)
    r = rodar(mig, "--tenant", OUTRA, "--undo", str(arquivo), "--rate", "200", "--yes")
    check(r.code == 2 and not r.writes and "tenant" in r.out, "undo de outro tenant recusado", r.text)
    editado = LOGS / "undo_editado.jsonl"
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    linhas[1] = linhas[1].replace(mig.AUSENTE, "valor-editado", 1)
    editado.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    r = rodar(mig, "--tenant", T, "--undo", str(editado), "--rate", "200", "--yes")
    check(r.code == 2 and not r.writes, "undo editado (valor anterior inesperado) recusado inteiro", r.text)

    titulo("Depois do undo: mesmo ruleset nao reaplica (revertido_antes); outras regras reclassificam")
    # 101: crm_* apagados por fora (sem --undo): a Activity existe e nao ha
    # reversao -> continua 'ja_migrado'.
    with por_fora():
        DB.apply("set", chave101, {campo: gfs.DELETE_FIELD for campo in fc.CONTACT_STAGE_FIELDS}, merge=True)
    regras = ",".join(mig.RULES)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", regras, "--sample", "50", "--rate", "200")
    resultado = bloco(r.out, "resultado:")
    check(r.code == 0 and dry_ok(r) and linha(resultado, "revertido_antes", n) and linha(resultado, "ja_migrado", 1)
          and "a alterar: 0" in r.out and amostra(r.out, "ja_migrado") == [101]
          and "%d contato(s) revertido(s) pelo --undo seguem sem etapa" % n in r.out and "RULESET_VERSION" in r.out,
          "dry-run: revertidos pelo undo aparecem como revertido_antes (com aviso), nao como ja_migrado", r.text)
    escritas = len(DB.writes)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rules", regras, "--rate", "200", "--yes")
    resultado = bloco(r.out, "resultado:")
    check(r.code == 0 and len(DB.writes) == escritas and linha(resultado, "revertido_antes", n)
          and linha(resultado, "ja_migrado", 1) and "a alterar (gravados): 0" in r.out,
          "--yes com o mesmo ruleset: nada regravado; revertido_antes x ja_migrado na transacao", r.text)
    r = rodar(mig, "--tenant", T, "--template", "clinic_v1", "--rate", "200", "--yes")
    novo = mig.ruleset_version(mig.DEFAULT_RULES, 30)
    c106 = doc(ckey(T, "wa_contacts", 106))
    check(r.code == 0 and "a alterar (gravados): %d" % (n + 1) in r.out and c106.get("crm_stage") == "in_service"
          and c106.get("crm_stage_activity_id") == mig.activity_id(T, 106, novo)
          and doc(ckey(T, "crm_activities", mig.activity_id(T, 106, ruleset))) is not None
          and whitelist_da_gravacao(r.proprias, n + 1),
          "regras padrao (sem o opt-in) = ruleset novo: o Encerrar (106) vira Em atendimento, com Activity nova; "
          "a antiga fica", r.text)


def cenario_ruleset_novo():
    titulo("RULESET_VERSION nova: reclassifica o que o --undo reverteu; undo de execucao antiga (open_human) segue valido")
    tid = "sim-ruleset"
    put(tkey(tid), {"id": tid, "settings": {"funnel": {"enabled": False, "template": "clinic_v1"}}})
    for dados in (
            contato(601, qualification="novo", first_seen_at=dias(5), last_inbound_at=dias(4)),
            contato(602, qualification="convertido", last_inbound_at=dias(20)),
            contato(603, bot_completed=True, first_human_contact_at=dias(10), last_inbound_at=dias(2))):
        put(ckey(tid, "wa_contacts", dados["id"]), dados)
    thread(tid, 603)
    mensagem(tid, 603, "inbound", dias(2), "Fixture: conversa na recepcao")
    contatos = (601, 602, 603)
    original = mig.RULESET_VERSION
    antiga = "2026-10-26"
    mig.RULESET_VERSION = antiga
    try:
        velho = mig.ruleset_version(mig.DEFAULT_RULES, 30)
        r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
        check(r.code == 0 and "a alterar (gravados): 3" in r.out and "ruleset_version: %s" % velho in r.out,
              "execucao com a RULESET_VERSION anterior grava os 3", r.text)
        arquivos = sorted(LOGS.glob("funnel_migration_undo_%s_*.jsonl" % tid))
        if len(arquivos) != 1:
            check(False, "undo da execucao com a RULESET_VERSION anterior disponivel")
            return
        r = rodar(mig, "--tenant", tid, "--undo", str(arquivos[0]), "--rate", "200", "--yes")
        check(r.code == 0 and linha(r.out, "revertido", 3), "undo da execucao anterior reverte os 3", r.text)
        r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
        check(r.code == 0 and linha(bloco(r.out, "resultado:"), "revertido_antes", 3)
              and "a alterar (gravados): 0" in r.out,
              "mesma RULESET_VERSION e mesmas regras: o undo e definitivo (revertido_antes)", r.text)
    finally:
        mig.RULESET_VERSION = original
    novo = mig.ruleset_version(mig.DEFAULT_RULES, 30)
    check(novo != velho and novo.startswith(mig.RULESET_VERSION + ":"), "ruleset novo difere so pela versao", novo)
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    estados = {cid: doc(ckey(tid, "wa_contacts", cid)) for cid in contatos}
    check(r.code == 0 and "a alterar (gravados): 3" in r.out
          and {c: e.get("crm_stage") for c, e in estados.items()} == {601: "new", 602: "scheduled", 603: "in_service"}
          and all(e.get("crm_stage_activity_id") == mig.activity_id(tid, c, novo) for c, e in estados.items())
          and all(doc(ckey(tid, "crm_activities", mig.activity_id(tid, c, velho))) is not None
                  and doc(ckey(tid, "crm_activities", mig.revert_id(tid, c, mig.activity_id(tid, c, velho))))
                  is not None for c in contatos),
          "RULESET_VERSION nova reclassifica os revertidos com Activity nova; as antigas e as reversoes ficam", r.text)
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    check(r.code == 0 and "a alterar (gravados): 0" in r.out and linha(r.out, "ja_tem_etapa", 3),
          "reexecucao com o ruleset novo: idempotente", r.text)

    # Undo escrito antes das decisoes de 28/10 (regra open_human, formato 1):
    # o script atual ainda reverte, e a regra nao e revalidada no undo.
    v1 = "2026-10-26:recent_untouched+open_human:30d"
    aid = mig.activity_id(tid, 604, v1)
    base = contato(604, bot_completed=True, first_human_contact_at=dias(30), last_inbound_at=dias(3))
    campos = {fc.F_STAGE: "in_service", fc.F_VERSION: 1, fc.F_CHANGED_AT: dias(3), fc.F_SOURCE: "migration",
              fc.F_ACTIVITY: aid, fc.F_BY_USER: None, fc.F_BY_UID: "", fc.F_ENTERED_AT: dias(90),
              fc.F_COHORT: "2026-07", fc.F_MAX_ORDER: 20}
    put(ckey(tid, "wa_contacts", 604), dict(base, **campos))
    put(ckey(tid, "crm_activities", aid), {
        "id": aid, "tenant_id": tid, "contact_id": 604, "task_id": None, "conversation_id": None,
        "event_type": fc.EVENT_MIGRATED, "actor_type": "migration", "from_stage": None, "to_stage": "in_service",
        "stage_reason": None, "entry_kind": None, "occurred_at": dias(2), "recorded_at": dias(2),
        "data": {"rule_id": "open_human", "ruleset_version": v1, "stage_version": 1, "source": "migration"}})
    thread(tid, 604)
    mensagem(tid, 604, "inbound", dias(3), "Fixture: conversa real na recepcao")
    cabecalho = {"type": "header", "format": 1, "tenant": tid, "project": PROJECT, "prefix": PREFIX,
                 "run_id": "mig_20261026T120000Z_abc123", "ruleset_version": v1, "template": "clinic_v1",
                 "rules": ["recent_untouched", "open_human"], "recent_days": 30, "include_channel_types": [],
                 "generated_at": dias(2).isoformat()}
    registro = {"type": "contact", "tenant": tid, "run_id": cabecalho["run_id"], "contact_id": 604,
                "activity_id": aid, "stage": "in_service", "reason": None, "rule_id": "open_human",
                "ruleset_version": v1, "version": 1, "fields": sorted(fc.CONTACT_STAGE_FIELDS),
                "before": {campo: mig.AUSENTE for campo in fc.CONTACT_STAGE_FIELDS}}
    arquivo_v1 = LOGS / "funnel_migration_undo_v1_fixture.jsonl"
    arquivo_v1.write_text(json.dumps(cabecalho) + "\n" + json.dumps(registro) + "\n", encoding="utf-8")
    r = rodar(mig, "--tenant", tid, "--undo", str(arquivo_v1), "--rate", "200", "--yes")
    reversao = doc(ckey(tid, "crm_activities", mig.revert_id(tid, 604, aid))) or {}
    check(r.code == 0 and linha(r.out, "revertido", 1) and doc(ckey(tid, "wa_contacts", 604)) == _store(base)
          and (reversao.get("data") or {}).get("rule_id") == "open_human",
          "undo de execucao anterior (regra open_human) ainda reverte com o script atual", r.text)
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    c604 = doc(ckey(tid, "wa_contacts", 604))
    atividade = doc(ckey(tid, "crm_activities", mig.activity_id(tid, 604, novo))) or {}
    check(r.code == 0 and "a alterar (gravados): 1" in r.out and c604.get("crm_stage") == "in_service"
          and (atividade.get("data") or {}).get("rule_id") == "in_reception",
          "depois do undo antigo, o ruleset novo reclassifica pelo in_reception (ex-open_human)", r.text)


def cenario_erro_e_retomada():
    titulo("Erro de escrita: exit 1, segue os outros e a re-execucao completa")
    tid = "sim-erro"
    put(tkey(tid), {"id": tid, "settings": {"funnel": {"enabled": False, "template": "clinic_v1"}}})
    for cid in (201, 202):
        put(ckey(tid, "wa_contacts", cid), contato(cid, last_inbound_at=dias(3)))
    DB.fail_commit[ckey(tid, "wa_contacts", 201)] = gex.ServiceUnavailable("indisponivel simulado")
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    check(r.code == 1 and "ServiceUnavailable" in r.out and "a alterar (gravados): 1" in r.out
          and doc(ckey(tid, "wa_contacts", 201)).get("crm_stage") is None
          and doc(ckey(tid, "wa_contacts", 202)).get("crm_stage") == "unclassified",
          "falha num contato nao grava pela metade e nao para os outros", r.text)
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    check(r.code == 0 and doc(ckey(tid, "wa_contacts", 201)).get("crm_stage") == "unclassified",
          "re-execucao (idempotente) completa o contato que falhou", r.text)


def cenario_erro_de_leitura():
    titulo("Erro fora do contato (pagina, relogio): relatorio impresso e exit 1, na migracao e no undo")
    tid = "sim-pagina"
    put(tkey(tid), {"id": tid, "settings": {"funnel": {"enabled": False, "template": "clinic_v1"}}})
    contatos = list(range(501, 506))
    for cid in contatos:
        put(ckey(tid, "wa_contacts", cid), contato(cid, last_inbound_at=dias(3)))

    def com_etapa():
        return [c for c in contatos if (doc(ckey(tid, "wa_contacts", c)) or {}).get("crm_stage")]

    pagina = mig.PAGE_SIZE
    mig.PAGE_SIZE = 2
    arquivos = []
    try:
        DB.fail_query.append((lambda q: q._pai == (TENANTS_COL, tid, "wa_contacts") and q._depois is not None,
                              gex.ServiceUnavailable("indisponivel simulado")))
        r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
        check(r.code == 1 and "=== Relatorio (GRAVACAO) ===" in r.out and "a alterar (gravados): 2" in r.out
              and re.search(r"^\s+ServiceUnavailable em \S+:\d+\s+1$", r.out, re.M) is not None
              and "PARADA ANTECIPADA: erro de leitura; execucao abortada" in r.out
              and "RESULTADO: ERRO de leitura" in r.out and "Traceback" not in r.text and com_etapa() == [501, 502],
              "falha ao ler a 2a pagina: relatorio parcial impresso, exit 1, 1a pagina gravada", r.text)
        arquivos = sorted(LOGS.glob("funnel_migration_undo_%s_*.jsonl" % tid))
        linhas = ([json.loads(x) for x in arquivos[0].read_text(encoding="utf-8").splitlines() if x.strip()]
                  if arquivos else [])
        check(len(arquivos) == 1 and sorted(x["contact_id"] for x in linhas if x.get("type") == "contact")
              == [501, 502], "undo fechado com as linhas do que foi gravado antes da falha")
        r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
        check(r.code == 0 and "a alterar (gravados): 3" in r.out and com_etapa() == contatos,
              "re-execucao (idempotente) completa os contatos das paginas seguintes", r.text)
    finally:
        mig.PAGE_SIZE = pagina
        DB.fail_query.clear()
    if not arquivos:
        check(False, "undo da execucao que falhou disponivel para o teste do --undo")
        return
    chamadas = [0]

    def relogio_que_falha():
        chamadas[0] += 1
        if chamadas[0] == 2:
            raise RuntimeError("relogio simulado")
        return RELOGIO[0]

    mig._monotonic = relogio_que_falha
    try:
        r = rodar(mig, "--tenant", tid, "--undo", str(arquivos[0]), "--rate", "200", "--yes")
    finally:
        mig._monotonic = lambda: RELOGIO[0]
    check(r.code == 1 and "=== Undo (GRAVACAO) ===" in r.out and linha(r.out, "revertido", 1)
          and re.search(r"^\s+RuntimeError em \S+:\d+\s+1$", r.out, re.M) is not None
          and "PARADA ANTECIPADA: erro fora do contato; execucao abortada" in r.out and "Traceback" not in r.text
          and com_etapa() == [502, 503, 504, 505],
          "undo: erro fora do contato imprime o relatorio (1 revertido) e sai com 1", r.text)
    r = rodar(mig, "--tenant", tid, "--undo", str(arquivos[0]), "--rate", "200", "--yes")
    check(r.code == 0 and linha(r.out, "ja_revertido", 1) and linha(r.out, "revertido", 1)
          and com_etapa() == [503, 504, 505], "undo de novo completa (idempotente)", r.text)


def cenario_canais():
    titulo("Canal fora da entrada automatica; recencia pela entrada real fora das origens confiaveis")
    tid = "sim-canais"
    put(tkey(tid), {"id": tid, "settings": {"funnel": {"enabled": False, "template": "clinic_v1"}}})
    antiga1 = datetime(2025, 3, 1, 15, tzinfo=timezone.utc)
    antiga2 = datetime(2025, 4, 1, 15, tzinfo=timezone.utc)
    legado = contato(405, last_inbound_at=dias(20))
    legado.pop("source_channel_type")
    for dados in (
            contato(401, last_inbound_at=dias(60)),
            contato(402, source_channel_type="coexistence", assigned_to=8, assigned_to_uid="uid-fixture-8",
                    last_inbound_at=dias(10)),
            # scripts-migracao-4: history de numero coex sincronizado ha 6 dias,
            # com conversa real de mar-abr/2025.
            contato(403, source_channel_type="coexistence", created_source="history", qualification="novo",
                    first_seen_at=dias(6), last_inbound_at=antiga2),
            # Agenda sincronizada em janeiro; a 1a conversa real e de 3 dias atras.
            contato(404, source_channel_type="coexistence", created_source="state_sync", qualification="novo",
                    first_seen_at=datetime(2026, 1, 10, 12, tzinfo=timezone.utc), last_inbound_at=dias(2)),
            legado,
            contato(406, source_channel_type="coexistence", created_source="state_sync",
                    last_inbound_at=None, last_message_at=None)):
        put(ckey(tid, "wa_contacts", dados["id"]), dados)
    mensagem(tid, 403, "inbound", antiga1, "Fixture coex antiga 1")
    mensagem(tid, 403, "inbound", antiga2, "Fixture coex antiga 2")
    mensagem(tid, 404, "inbound", dias(3), "Fixture coex primeira conversa")
    mensagem(tid, 404, "inbound", dias(2), "Fixture coex segunda mensagem")

    r = rodar(mig, "--tenant", tid, "--sample", "10", "--rate", "200")
    canais = bloco(r.out, "tipo de canal")
    check(r.code == 0 and dry_ok(r) and linha(r.out, "canal_fora_da_entrada", 3)
          and amostra(r.out, "canal_fora_da_entrada") == [402, 403, 404]
          and linha(canais, "coexistence: fora_da_entrada", 3) and linha(canais, "standard: entrada_do_tenant", 1)
          and linha(canais, "(vazio=standard): entrada_do_tenant", 1) and linha(r.out, "sem_inbound", 1)
          and "candidatos (sem etapa): 2" in r.out and "a alterar: 2" in r.out,
          "entrada so standard: contato so do coexistence fica fora; legado sem tipo conta como standard", r.text)
    r = rodar(mig, "--tenant", tid, "--rate", "200", "--yes")
    check(r.code == 0 and "a alterar (gravados): 2" in r.out, "--yes grava so os do canal da entrada", r.text)
    put(ckey(tid, "wa_contacts", 407), contato(407, source_channel_type="coexistence", last_inbound_at=NOW))
    r = rodar(mig, "--tenant", tid, "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "a alterar: 0" in r.out and linha(r.out, "canal_fora_da_entrada", 4),
          "trafego novo no coexistence (o intake o ignora) nao volta como 'a alterar': o gate converge", r.text)
    tenant = doc(tkey(tid))
    tenant["settings"]["funnel"]["intake_channel_types"] = ["standard", "coexistence"]
    put(tkey(tid), tenant)
    r = rodar(mig, "--tenant", tid, "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "candidatos (sem etapa): 4" in r.out
          and "canais da entrada automatica: standard, coexistence" in r.out
          and linha(bloco(r.out, "tipo de canal"), "coexistence: entrada_do_tenant", 4),
          "tenant com coexistence na entrada automatica: entra sem a flag", r.text)
    tenant["settings"]["funnel"].pop("intake_channel_types")
    put(tkey(tid), tenant)
    r = rodar(mig, "--tenant", tid, "--include-channel-types", "coexistence", "--sample", "10", "--rate", "200")
    check(r.code == 0 and dry_ok(r) and "incluidos por --include-channel-types: coexistence" in r.out
          and "candidatos (sem etapa): 4" in r.out
          and linha(bloco(r.out, "tipo de canal"), "coexistence: incluido_por_flag", 4)
          and linha(r.out, "recent_untouched -> new", 1) and amostra(r.out, "recent_untouched") == [404]
          and linha(bloco(r.out, "recent_untouched NAO aplicado"), "entrada_real_fora_da_janela", 1)
          and amostra(r.out, "recent_untouched_entrada_real_fora_da_janela") == [403],
          "--include-channel-types inclui o coexistence; recencia pela entrada real (403 fora, 404 dentro)", r.text)
    r = rodar(mig, "--tenant", tid, "--include-channel-types", "coexistence", "--rate", "200", "--yes")
    check(r.code == 0 and "a alterar (gravados): 4" in r.out, "--yes com a flag grava os 4", r.text)
    ruleset = mig.ruleset_version(mig.DEFAULT_RULES, 30)
    for cid, (etapa, mudou, entrou, coorte, ordem, regra) in (
            (403, ("unclassified", antiga2, antiga1, "2025-03", 0, "no_rule")),
            (404, ("new", dias(2), dias(3), "2026-10", 10, "recent_untouched"))):
        atual = doc(ckey(tid, "wa_contacts", cid))
        atividade = doc(ckey(tid, "crm_activities", mig.activity_id(tid, cid, ruleset))) or {}
        check(atual.get("crm_stage") == etapa and atual.get("crm_stage_changed_at") == mudou
              and atual.get("crm_funnel_entered_at") == entrou and atual.get("crm_cohort_month") == coorte
              and atual.get("crm_max_reached_order") == ordem
              and (atividade.get("data") or {}).get("rule_id") == regra,
              "contato %d: %s, entrada real %s, coorte %s, max %d" % (cid, etapa, entrou.date(), coorte, ordem),
              atual)
    cabecalhos = [json.loads(arquivo.read_text(encoding="utf-8").splitlines()[0])
                  for arquivo in sorted(LOGS.glob("funnel_migration_undo_%s_*.jsonl" % tid))]
    check(sorted(c.get("include_channel_types") for c in cabecalhos) == [[], ["coexistence"]],
          "cabecalho do undo registra os tipos incluidos por --include-channel-types")


ETAPAS_V2 = ["new", "in_service", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified",
             "unclassified"]


def linhas_do_catalogo(texto):
    """{etapa: linha} do catalogo resolvido impresso pelo set_tenant_funnel."""
    return {m.group(1): m.group(0) for m in re.finditer(r"^\s+\d+\s+([a-z_]+)\s.*$", texto, re.M)}


def cenario_set_tenant_funnel():
    titulo("set_tenant_funnel: dry-run, diff, --yes substituindo a subarvore (catalogo v2)")
    ai = {"bot_engine": "dialogflow_cx", "agent_id": "fixture-agent", "lgpd_by_agent": False}
    put(tkey(CFG_T), {"id": CFG_T, "name": "Clinica Config", "is_active": True,
                      "settings": {"ai": copy.deepcopy(ai), "logo_url": "https://fixture/logo.png"}})
    put(ckey(CFG_T, "wa_contacts", 301), contato(301, crm_stage="loyal", crm_stage_version=1))
    put(ckey(CFG_T, "wa_contacts", 302), contato(302, crm_stage="new", crm_stage_version=1))

    def funil():
        return copy.deepcopy(((doc(tkey(CFG_T)) or {}).get("settings") or {}).get("funnel"))

    r = rodar(conf, "--tenant", CFG_T, "--show")
    check(r.code == 0 and dry_ok(r) and "ausente" in r.out, "--show sem config: so leitura, trava antes de ler", r.text)
    r = rodar(conf, "--tenant", CFG_T, "--enable", "--template", "clinic_v1")
    check(r.code == 0 and dry_ok(r) and "enabled: (ausente) -> true" in r.out
          and 'template: (ausente) -> "clinic_v1"' in r.out and "DRY-RUN" in r.out,
          "dry-run mostra o diff e nao grava", r.text)
    linhas_cat = linhas_do_catalogo(r.out)
    check(list(linhas_cat) == ETAPAS_V2 and "Cliente Agendado" in linhas_cat["scheduled"]
          and "Paciente em acompanhamento" in linhas_cat["loyal"] and "Não qualificado" in linhas_cat["disqualified"],
          "catalogo v2: as 8 etapas da clinica, na ordem, com os nomes do PO (sem attended/converted)", r.text)
    check("so com ver_contatos_agente_funil" in linhas_cat["new"]
          and "legado=" not in linhas_cat["new"] and "legado=" not in linhas_cat["unclassified"]
          and "legado=em_atendimento" in linhas_cat["in_service"] and "desfecho do Encerrar" not in linhas_cat["in_service"]
          and all("desfecho do Encerrar" in linhas_cat[k] for k in ("awaiting_followup", "scheduled", "loyal",
                                                                      "non_converted", "disqualified"))
          and "legado=convertido" in linhas_cat["scheduled"] and "legado=convertido" in linhas_cat["loyal"]
          and "legado=nao_convertido" in linhas_cat["non_converted"]
          and "legado=nao_qualificado" in linhas_cat["disqualified"],
          "catalogo mostra as marcas v2: visibilidade do Novo contato, desfechos do Encerrar e legado sincronizado",
          r.text)
    check("automacoes: handoff: new, unclassified -> in_service; human_reply: new, unclassified -> in_service" in r.out
          and "kpis: booked_stage=scheduled, won_stage=scheduled" in r.out,
          "catalogo mostra as automacoes (handoff, 1a resposta humana) e os kpis", r.text)
    r = rodar(conf, "--tenant", CFG_T, "--enable", "--template", "clinic_v1", "--yes")
    tenant = doc(tkey(CFG_T))
    check(r.code == 0 and funil() == {"enabled": True, "template": "clinic_v1", "version": 1,
                                      "enabled_at": NOW, "updated_at": NOW}
          and tenant["settings"]["ai"] == ai and tenant["settings"]["logo_url"] == "https://fixture/logo.png"
          and tenant.get("updated_at") == NOW and [c for _, c in r.writes] == [tkey(CFG_T)],
          "--yes grava settings.funnel (versao 1, enabled_at) sem tocar settings.ai", r.text)
    check(fc.funnel_for_tenant(tenant) is not None, "doc gravado resolve o catalogo no runtime")
    r = rodar(conf, "--tenant", CFG_T, "--enable", "--yes")
    check(r.code == 0 and not r.writes and "Sem mudancas" in r.out, "--enable de novo: sem mudancas, nada gravado", r.text)
    AGORA[0] = NOW + timedelta(hours=2)
    try:
        r = rodar(conf, "--tenant", CFG_T, "--stage-label", "new=Novo lead", "--stage-label",
                  "in_service=Em conversa", "--yes")
        atual = funil()
        check(r.code == 0 and atual["stage_labels"] == {"new": "Novo lead", "in_service": "Em conversa"}
              and atual["version"] == 2 and atual["enabled_at"] == NOW and atual["updated_at"] == AGORA[0],
              "rotulos gravados; version +1; enabled_at do 1o enable preservado", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--stage-label", "in_service=", "--yes")
        atual = funil()
        check(r.code == 0 and atual["stage_labels"] == {"new": "Novo lead"} and atual["version"] == 3,
              "rotulo vazio volta ao template: a subarvore e substituida (merge deixaria a chave)", r.text)
        # Chaves do catalogo v1 sairam do template (decisao do PO de 28/10).
        for argumentos in (("--stage-label", "attended=Atendido"), ("--stage-label", "converted=Pagou"),
                           ("--inactive-stage", "converted"), ("--active-stage", "attended"),
                           ("--stale", "attended=3")):
            r = rodar(conf, "--tenant", CFG_T, *argumentos, "--yes")
            check(r.code == 2 and not r.writes and "nao existe no template" in r.out,
                  "chave do catalogo v1 recusada: %s %s" % argumentos, r.text)
        r = rodar(conf, "--tenant", CFG_T, "--inactive-stage", "loyal")
        check(r.code == 2 and "loyal=1" in r.out and not r.writes,
              "recusa inativar etapa com contatos (count por etapa)", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--inactive-stage", "loyal", "--allow-inactive-with-contacts", "--yes")
        catalogo = fc.funnel_for_tenant(doc(tkey(CFG_T)))
        check(r.code == 0 and funil()["inactive_stages"] == ["loyal"]
              and not fc.stage_def(catalogo, "loyal")["active"] and "etapa loyal fica inativa com 1 contato(s)" in r.out,
              "--allow-inactive-with-contacts desativa mesmo com contatos (com aviso)", r.text)
        for etapa, papel in (("scheduled", "kpi booked_stage"), ("in_service", "destino da automacao handoff")):
            r = rodar(conf, "--tenant", CFG_T, "--inactive-stage", etapa, "--allow-inactive-with-contacts", "--yes")
            check(r.code == 2 and not r.writes and "estrutural" in r.out and papel in r.out,
                  "etapa estrutural nunca fica inativa: %s (%s)" % (etapa, papel), r.text)
        for etapa in (fc.ENTRY_STAGE, fc.TRIAGE_STAGE):
            r = rodar(conf, "--tenant", CFG_T, "--inactive-stage", etapa, "--yes")
            check(r.code == 2 and not r.writes and "reservada" in r.out, "%s (reservada) nunca fica inativa" % etapa,
                  r.text)
        r = rodar(conf, "--tenant", CFG_T, "--stale", "new=3", "--stale", "in_service=off", "--yes")
        catalogo = fc.funnel_for_tenant(doc(tkey(CFG_T)))
        check(r.code == 0 and funil()["stale_days"] == {"new": 3, "in_service": 0}
              and fc.stage_def(catalogo, "new")["stale"]["days"] == 3
              and fc.stage_def(catalogo, "in_service")["stale"] is None, "--stale grava dias e off", r.text)
        for argumento, motivo in (("awaiting_followup=5", "selo vem da tarefa"),
                                  ("scheduled=5", "etapa sem limiar no template"),
                                  ("loyal=5", "etapa sem limiar no template")):
            r = rodar(conf, "--tenant", CFG_T, "--stale", argumento)
            check(r.code == 2 and not r.writes and "limiar por dias" in r.out,
                  "--stale recusa %s (%s)" % (argumento.split("=")[0], motivo), r.text)
        r = rodar(conf, "--tenant", CFG_T, "--stale", "new=default", "--yes")
        check(r.code == 0 and funil()["stale_days"] == {"in_service": 0}, "--stale k=default remove o override", r.text)
        for rotulo, motivo in (("new=" + "x" * 41, "rotulo longo"), ("new=linha\nquebrada", "quebra de linha"),
                               ("nao_existe=Rotulo", "etapa inexistente")):
            r = rodar(conf, "--tenant", CFG_T, "--stage-label", rotulo, "--yes")
            check(r.code == 2 and not r.writes, "recusa rotulo invalido: %s" % motivo, r.text)
        r = rodar(conf, "--tenant", CFG_T, "--reason-label", "no_show=Faltou", "--reason-label",
                  "proposal_declined=Recusou o orçamento", "--yes")
        catalogo = fc.funnel_for_tenant(doc(tkey(CFG_T)))
        check(r.code == 0 and funil()["reason_labels"] == {"no_show": "Faltou",
                                                           "proposal_declined": "Recusou o orçamento"}
              and fc.reason_label(catalogo, "no_show") == "Faltou",
              "--reason-label renomeia os motivos novos (no_show, proposal_declined)", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--intake-channel-types", "standard,coexistence", "--yes")
        check(r.code == 0 and funil()["intake_channel_types"] == ["standard", "coexistence"],
              "tipos de canal da entrada automatica", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--intake-channel-types", "standard,foo", "--yes")
        check(r.code == 2 and not r.writes, "tipo de canal desconhecido recusado", r.text)
        versao = funil()["version"]

        def gravacao_em_paralelo():
            with por_fora():
                DB.apply("set", tkey(CFG_T), {"settings": {"ai": {"status": "paused"}}}, merge=True)

        DB.hook_after_get[tkey(CFG_T)] = gravacao_em_paralelo
        r = rodar(conf, "--tenant", CFG_T, "--disable", "--yes")
        check(r.code == 1 and funil()["version"] == versao and funil()["enabled"] is True
              and doc(tkey(CFG_T))["settings"]["ai"]["status"] == "paused",
              "gravacao em paralelo no doc do tenant: precondicao falha, nada gravado", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--disable", "--yes")
        check(r.code == 0 and funil()["enabled"] is False and funil()["enabled_at"] == NOW
              and funil()["version"] == versao + 1, "--disable desliga e preserva enabled_at", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--show")
        check(r.code == 0 and dry_ok(r) and re.search(r"^\s+loyal\s+1\s+\(inativa\)$", r.out, re.M)
              and linha(r.out, "com etapa (total)", 2) and "DESLIGADO" in r.out
              and "Novo lead" in r.out and "(nenhum: valem os rotulos de settings.funnel" in r.out,
              "--show mostra catalogo resolvido, contagem por etapa e a ausencia de textos da clinica", r.text)

        # Textos da clinica (tela Etapas, system_settings/funnel): por cima de
        # settings.funnel; o script so le.
        textos_chave = ckey(CFG_T, "system_settings", "funnel")
        put(textos_chave, {"version": 4, "updated_by_user_id": 7,
                           "stage_labels": {"loyal": "Em acompanhamento"},
                           "stage_descriptions": {"scheduled": "Texto da clínica para Cliente Agendado."},
                           "reason_labels": {"price": "Valor"}})
        textos_antes = doc(textos_chave)
        r = rodar(conf, "--tenant", CFG_T, "--show")
        linhas_cat = linhas_do_catalogo(r.out)
        check(r.code == 0 and dry_ok(r) and "=== textos da clinica" in r.out and "versao 4" in r.out
              and "Em acompanhamento" in linhas_cat.get("loyal", "")
              and "Texto da clínica para Cliente Agendado." in r.out and "price=Valor" in r.out
              and "ATENCAO: textos da clinica" not in r.out,
              "--show mostra os textos da clinica e o catalogo com eles por cima de settings.funnel", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--stage-label", "loyal=Fidelizado", "--yes")
        linhas_cat = linhas_do_catalogo(r.out)
        check(r.code == 0 and "a clinica ja renomeou loyal na tela Etapas" in r.out
              and funil()["stage_labels"] == {"new": "Novo lead", "loyal": "Fidelizado"}
              and "Em acompanhamento" in linhas_cat.get("loyal", "")
              and [c for _, c in r.writes] == [tkey(CFG_T)] and doc(textos_chave) == textos_antes,
              "--stage-label avisa o rotulo sombreado pela clinica e nunca grava system_settings/funnel", r.text)
        put(textos_chave, {"version": 5, "stage_labels": {"attended": "Atendido"}})
        r = rodar(conf, "--tenant", CFG_T, "--show")
        check(r.code == 0 and dry_ok(r) and "ATENCAO: textos da clinica fora da validacao" in r.out
              and list(linhas_do_catalogo(r.out)) == ETAPAS_V2,
              "textos da clinica com chave fora do template: aviso, e o catalogo resolve mesmo assim", r.text)

        r = rodar(conf, "--tenant", CFG_T, "--active-stage", "loyal", "--yes")
        check(r.code == 0 and funil()["inactive_stages"] == [], "--active-stage reativa", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--inactive-stage", "disqualified", "--yes")
        check(r.code == 0 and funil()["inactive_stages"] == ["disqualified"],
              "etapa sem contatos (e nao estrutural) pode ser desativada", r.text)
        r = rodar(mig, "--tenant", CFG_T, "--rate", "200")
        check(r.code == 2 and "regra legacy_outcome: etapa disqualified esta inativa" in r.out and not r.writes,
              "migracao recusa regra cujo destino esta inativo no tenant (legacy_outcome -> disqualified)", r.text)
        r = rodar(mig, "--tenant", CFG_T, "--rules", "recent_untouched,in_reception", "--rate", "200")
        check(r.code == 0 and dry_ok(r) and "template clinic_v1, desligado" in r.out,
              "migracao usa o template do tenant quando --template e omitido", r.text)
        put(tkey("sim-sem-funil"), {"id": "sim-sem-funil", "settings": {}})
        r = rodar(conf, "--tenant", "sim-sem-funil", "--disable", "--yes")
        check(r.code == 0 and not r.writes and "ja esta desligado" in r.out,
              "--disable sem config: kill-switch nao falha e nao grava", r.text)
        r = rodar(conf, "--tenant", CFG_T, "--show", "--yes")
        check(r.code == 2 and DB.reads == r.reads0, "--show com --yes recusado antes de ler", r.text)
        r = rodar(conf, "--tenant", "sim-nao-existe", "--enable", "--template", "clinic_v1", "--yes")
        check(r.code == 2 and not r.writes, "tenant inexistente recusado", r.text)

        # Config com chaves de uma versao anterior do template (attended,
        # converted): o runtime ignora; o --show avisa.
        put(tkey("sim-v1-config"), {"id": "sim-v1-config", "settings": {"funnel": {
            "enabled": True, "template": "clinic_v1", "version": 3,
            "stage_labels": {"attended": "Atendido", "new": "Novo"}, "stale_days": {"attended": 2},
            "inactive_stages": ["converted"]}}})
        r = rodar(conf, "--tenant", "sim-v1-config", "--show")
        catalogo = fc.funnel_for_tenant(doc(tkey("sim-v1-config")))
        check(r.code == 0 and dry_ok(r)
              and "fora do template clinic_v1 (o runtime ignora): stage_labels.attended, stale_days.attended, "
                  "inactive_stages[converted]" in r.out
              and list(linhas_do_catalogo(r.out)) == ETAPAS_V2
              and re.search(r"\snew\s+Novo\s+open\s", linhas_do_catalogo(r.out)["new"]) is not None
              and catalogo is not None and fc.stage_label(catalogo, "new") == "Novo"
              and fc.stage_def(catalogo, "attended") is None
              and all(s["active"] for s in catalogo["stages"]),
              "settings.funnel com chaves do catalogo v1: aviso no --show e o runtime ignora", r.text)
    finally:
        AGORA[0] = NOW


def cenario_trava_real():
    titulo("trava_escrita real: bloqueia escrita direta e o commit interno da transacao")
    from google.cloud.firestore_v1 import batch, collection, document, transaction
    alvos = [(document.DocumentReference, ("set", "update", "delete", "create")),
             (collection.CollectionReference, ("add",)),
             (batch.WriteBatch, ("set", "update", "delete", "create", "commit")),
             (transaction.Transaction, ("set", "update", "delete", "create", "commit", "_commit"))]
    salvos = {(cls, nome): cls.__dict__.get(nome, None) for cls, nomes in alvos for nome in nomes}

    def restaurar():
        for (cls, nome), original in salvos.items():
            if original is None:
                if nome in cls.__dict__:
                    delattr(cls, nome)
            else:
                setattr(cls, nome, original)

    total = sum(len(nomes) for _, nomes in alvos)
    for trava in (TRAVA_REAL, TRAVA_REAL_CONF):
        try:
            trava()
            bloqueados = []
            for cls, nomes in alvos:
                for nome in nomes:
                    try:
                        getattr(cls, nome)(None)
                    except RuntimeError:
                        bloqueados.append(nome)
                    except Exception:  # noqa: BLE001
                        pass
            check(len(bloqueados) == total and "_commit" in bloqueados,
                  "%s trava %d de %d metodos de escrita (inclui Transaction._commit)" % (
                      trava.__module__, len(bloqueados), total))
        finally:
            restaurar()
    check(all(cls.__dict__.get(nome) is original for (cls, nome), original in salvos.items() if original),
          "classes reais restauradas depois do teste")


def cenario_cli():
    titulo("CLI real (subprocesso): --help e ambiente sem FIRESTORE_PROJECT_ID")
    # scripts-migracao-9: o config faz load_dotenv(override=False), que so
    # pula chave JA presente no ambiente. Remover FIRESTORE_PROJECT_ID do
    # filho deixaria um .env preenchido repor o projeto real (e o cliente
    # leria com ADC); a chave VAZIA nao e sobrescrita.
    env_falso = LOGS / "dotenv_sim.env"
    env_falso.write_text("FIRESTORE_PROJECT_ID=projeto-do-dotenv-sim\n", encoding="utf-8")
    sonda = ("import os, sys\nfrom dotenv import load_dotenv\nload_dotenv(sys.argv[1], override=False)\n"
             "print(repr(os.environ.get('FIRESTORE_PROJECT_ID')))")
    lidos = []
    for amb in ({k: v for k, v in os.environ.items() if k != "FIRESTORE_PROJECT_ID"},
                dict(os.environ, FIRESTORE_PROJECT_ID="")):
        lidos.append(subprocess.run([sys.executable, "-c", sonda, str(env_falso)], env=amb,
                                    capture_output=True, text=True, timeout=120).stdout.strip())
    check(lidos == ["'projeto-do-dotenv-sim'", "''"],
          "premissa: o .env repoe a chave removida, mas nao sobrescreve a chave vazia", lidos)
    # Reforco: emulador em porta morta e credencial inexistente; nada no
    # filho alcanca o Firestore real.
    ambiente = dict(os.environ, FIRESTORE_PROJECT_ID="", FIRESTORE_EMULATOR_HOST="127.0.0.1:9",
                    GOOGLE_APPLICATION_CREDENTIALS=str(LOGS / "credencial_inexistente.json"))
    visto = subprocess.run([sys.executable, "-c", "import config, os\nprint(repr(config.FIRESTORE_PROJECT_ID), "
                            "os.environ.get('FIRESTORE_EMULATOR_HOST'))"],
                           cwd=str(ROOT), env=ambiente, capture_output=True, text=True, timeout=120)
    check(visto.returncode == 0 and visto.stdout.strip() == "'' 127.0.0.1:9",
          "filho da CLI: config sem projeto (mesmo com .env no repo) e emulador em porta morta",
          visto.stdout + visto.stderr)
    for modulo, extra in (("scripts.classify_funnel_stage", ["--tenant", "sim-x"]),
                          ("scripts.set_tenant_funnel", ["--tenant", "sim-x", "--show"])):
        ajuda = subprocess.run([sys.executable, "-m", modulo, "--help"], cwd=str(ROOT), env=ambiente,
                               capture_output=True, text=True, timeout=120)
        check(ajuda.returncode == 0 and "--tenant" in ajuda.stdout, "%s --help (exit 0)" % modulo, ajuda.stderr)
        sem = subprocess.run([sys.executable, "-m", modulo] + extra, cwd=str(ROOT), env=ambiente,
                             capture_output=True, text=True, timeout=120)
        texto = sem.stdout + sem.stderr
        check(sem.returncode == 2 and "FIRESTORE_PROJECT_ID" in sem.stderr and "Traceback" not in texto,
              "%s sem FIRESTORE_PROJECT_ID: exit 2, erro claro, sem stack" % modulo, texto)


def cenario_gates_finais():
    titulo("Gates: indices, PII na saida, datetimes")
    try:
        indices = json.loads((ROOT / "firestore.indexes.json").read_text(encoding="utf-8")).get("indexes", [])
    except (OSError, ValueError) as exc:
        check(False, "firestore.indexes.json legivel (%s)" % type(exc).__name__)
        return
    faltando = []
    vistos = set()
    for forma in DB.shapes:
        chave = json.dumps(forma, sort_keys=True)
        if chave in vistos:
            continue
        vistos.add(chave)
        campos = set(forma["eq"]) | set(forma["range"]) | {c for c, _ in forma["orders"]}
        if (not forma["range"] and not forma["orders"]) or len(campos) <= 1:
            continue  # igualdade pura ou campo unico: indice automatico
        ultimo, direcao = forma["orders"][-1] if forma["orders"] else (forma["range"][0], "ASCENDING")
        ok = False
        for indice in indices:
            if indice.get("collectionGroup") != forma["collection"] or indice.get("queryScope", "COLLECTION") != "COLLECTION":
                continue
            lista = [f for f in indice.get("fields", []) if f.get("fieldPath") != "__name__"]
            if (lista and lista[-1].get("fieldPath") == ultimo and lista[-1].get("order") == direcao
                    and {f["fieldPath"] for f in lista[:-1]} == set(forma["eq"])):
                ok = True
                break
        if not ok:
            faltando.append(forma)
    check(not faltando, "toda consulta com ordem/intervalo dos scripts tem indice exato (%d formas)" % len(vistos),
          faltando)
    vazou = sorted({p for p in PII for texto in SAIDAS if p in texto})
    check(not vazou, "nenhuma saida (%d execucoes) contem nome, telefone, wa_id, notas ou mensagens" % len(SAIDAS),
          vazou)
    check(not DB.naive, "nenhum datetime ingenuo gravado em todo o simulador", DB.naive)


def main():
    try:
        semear_clinica()
        cenario_regras_puras()
        cenario_preflight()
        cenario_dry_run()
        arquivo, ruleset = cenario_gravacao()
        cenario_idempotencia(ruleset)
        cenario_undo(arquivo, ruleset)
        cenario_ruleset_novo()
        cenario_erro_e_retomada()
        cenario_erro_de_leitura()
        cenario_canais()
        cenario_set_tenant_funnel()
        cenario_trava_real()
        cenario_cli()
        cenario_gates_finais()
    except Exception:  # noqa: BLE001
        FAILS.append("excecao inesperada no simulador")
        traceback.print_exc()
    finally:
        shutil.rmtree(LOGS, ignore_errors=True)
    print("\n" + "=" * 72)
    if FAILS:
        print("FALHOU: %d de %d verificacoes" % (len(FAILS), CHECKS))
        for falha in FAILS:
            print("  - " + falha)
        return 1
    print("OK: %d verificacoes; nenhuma rede, credencial ou Firestore real." % CHECKS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
