# -*- coding: utf-8 -*-
r"""Disparo de template APROVADO em lote (campanha), por um canal do CRM.

Le uma lista de numeros de um CSV, normaliza/deduplica e manda UM template
para cada destinatario. Default e DRY-RUN: so envia com --yes.

PRINCIPIO: o script NAO escreve NADA no Firestore. Ele so LE o doc do canal
(pra pegar token/phone_id/waba). Quem responder ao template entra pelo webhook
normal e vira lead pelo funil de sempre (gate LGPD -> bot -> pool). Pre-criar
contato/conversation aqui seria pior em todos os eixos:
  - thread vazia sem `bot_completed` nunca fecha no modo recepcao;
  - thread com `bot_completed=True` MATA o bot (a Val nunca atende);
  - milhares de threads com last_message_at=agora estouram o listener
    orderBy(desc).limit(50) e escondem as conversas reais da recepcao;
  - vira lead ate pra numero que nem tem WhatsApp.
Deixando o inbound criar, so quem realmente respondeu vira lead.

O relatorio de saida tem telefone em claro (necessario pra retomada) e por isso
vive em scripts/_exports/ (ja no .gitignore). O console so mostra mascarado.

ATENCAO — HTTP 200 nao significa "entregue", significa "aceito pra envio". O
desfecho real (delivered/failed) chega assincrono no webhook do CRM; falhas
aparecem no log do Cloud Run como "[WA STATUS] ... failed" com o codigo Meta.

Uso (PowerShell, a partir da raiz do repo):

  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"

  # 1) preflight + dry-run: valida canal/template e mostra o plano, sem enviar
  .\.venv\Scripts\python.exe -m scripts.send_template_bulk `
      --csv scripts\_exports\campanhas\varizemed_todas_20260807_1316.csv `
      --column user_id

  # 2) teste com os 2 numeros combinados (ignora o CSV)
  .\.venv\Scripts\python.exe -m scripts.send_template_bulk --test --yes

  # 3) campanha real, fatiada (rode 1x por dia respeitando o tier da Meta)
  .\.venv\Scripts\python.exe -m scripts.send_template_bulk `
      --csv scripts\_exports\campanhas\varizemed_todas_20260807_1316.csv `
      --column user_id --max-sends 250 --yes

Retomada: antes de enviar, o script le os relatorios ja existentes da campanha
(o proprio --out e os irmaos <template>_*.csv na mesma pasta) e pula quem tem
desfecho terminal. Rodar o mesmo comando amanha continua de onde parou.
O nome default do relatorio NAO leva data de proposito — se levasse, a virada
do dia geraria um arquivo novo, a retomada nao acharia nada e o fatiamento
reenviaria os MESMOS primeiros N todo dia.
"""

import argparse
import csv
import glob
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_RAIZ, _AQUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pii_redaction import redact_phone  # noqa: E402
from wa_phone_norm import inspect_wa_id, load_targets  # noqa: E402

# Numeros de teste combinados com o Rafael (modo --test).
NUMEROS_TESTE = ["+55 31 8277-9779", "+55 31 8344-0484"]

GRAPH_VERSION = "v23.0"
GRAPH_BASE = "https://graph.facebook.com/" + GRAPH_VERSION

# --- Triagem de erro da Meta -----------------------------------------------
# FATAL: aborta a campanha inteira. Continuar disparando depois destes e o
# caminho pro ban do numero.
CODIGOS_FATAIS = {
    368,     # WABA restrita/desabilitada por violacao de politica
    100,     # parametro invalido/sem permissao -> bug de payload ou token
    131042,  # problema no metodo de pagamento
    131047,  # janela de 24h (so vale p/ NAO-template) -> payload errado
    131048,  # restricao de envio por qualidade/spam no numero
    132000,  # qtd de variaveis nao bate com o template
    132001,  # template nao existe no idioma / nao aprovado
    132007,  # conteudo do template viola politica
    132015,  # template PAUSADO por baixa qualidade
    132016,  # template desabilitado em definitivo
    133010,  # phone number nao registrado na plataforma
}
# GLOBAL: pausa e tenta de novo o MESMO numero (nao pula).
CODIGOS_BACKOFF = {4, 80007, 130429, 131000, 131016}
# POR-NUMERO: pula, nao retenta.
CODIGOS_PULA = {131026, 131049, 131056}

# Sinais de que um 131009 e, na verdade, billing da WABA (vira FATAL).
SUBCODES_BILLING = {2494051, 2494052}

COLUNAS_RELATORIO = [
    "ts_utc", "input_raw", "wa_id_enviado", "wa_id_meta", "outcome",
    "message_status", "wa_message_id", "http_status", "error_code",
    "error_subcode", "error_title", "error_message", "tentativas",
]
# Desfechos que NAO devem ser reenviados numa retomada.
# "sent_incerto" ENTRA aqui de proposito: a Meta pode ter aceitado a mensagem e
# so a resposta ter se perdido. Reenviar por via das duvidas duplicaria o aviso
# pro paciente, que e pior do que deixar um numero sem receber. Pra reabrir
# esses casos depois de conferir o log do Cloud Run, use --retry-incertos.
OUTCOMES_TERMINAIS = {"sent", "sent_incerto", "failed_permanent"}
# Precedencia no merge de varios relatorios da mesma campanha: o desfecho mais
# "forte" vence, pra que um sent nunca seja rebaixado por um retryable.
_PESO_OUTCOME = {"sent": 4, "sent_incerto": 3, "failed_permanent": 2, "failed_retryable": 1}


class Fatal(Exception):
    """Erro que aborta a campanha."""


# ---------------------------------------------------------------------------
# HTTP (stdlib, igual aos scripts de diagnostico do repo)
# ---------------------------------------------------------------------------
def graph_get(caminho, token, timeout=30):
    url = "{}/{}".format(GRAPH_BASE, caminho)
    sep = "&" if "?" in url else "?"
    url = "{}{}access_token={}".format(url, sep, urllib.parse.quote(token, safe=""))
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        corpo = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(corpo)
        except ValueError:
            return exc.code, {"error": {"message": corpo[:300]}}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": {"message": "falha de rede: {}".format(exc)}}


def fase_da_falha(exc):
    """'pre' se a excecao PROVA que o request nao chegou na Meta; senao 'incerta'.

    Existe porque o Cloud API nao tem chave de idempotencia: repetir um POST que
    a Meta JA aceitou cria uma SEGUNDA mensagem de verdade, e o paciente recebe
    o mesmo aviso duas vezes. Entao so retentamos quando da pra provar que nada
    foi criado — falha de DNS e conexao recusada acontecem antes de qualquer
    byte sair da maquina.

    Timeout de leitura e reset de conexao sao ambiguos: a Meta pode ter aceitado
    e enfileirado a mensagem e so a RESPOSTA ter se perdido. Nesses casos nao
    retentamos; marcamos como incerto e deixamos o operador decidir depois de
    conferir o log do Cloud Run.
    """
    raiz = getattr(exc, "reason", exc)
    if isinstance(raiz, (socket.gaierror, ConnectionRefusedError)):
        return "pre"
    return "incerta"


def graph_post(caminho, token, payload, timeout=30):
    """(http_status, corpo). Status sinteticos: 0 = falha ANTES de enviar
    (retentar e seguro), -1 = falha DEPOIS de enviar (nao retentar)."""
    url = "{}/{}".format(GRAPH_BASE, caminho)
    dados = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=dados, method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        corpo = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(corpo)
        except ValueError:
            return exc.code, {"error": {"message": corpo[:300]}}
    except Exception as exc:  # noqa: BLE001
        fase = fase_da_falha(exc)
        return (0 if fase == "pre" else -1), {
            "error": {"message": "falha de rede ({}): {}".format(fase, exc)}}


# ---------------------------------------------------------------------------
# Canal (LEITURA do Firestore — unica coisa que o script le do banco)
# ---------------------------------------------------------------------------
def carregar_canal(channel_id, tenant, expect_phone_id):
    """Le o doc do canal e valida tenant/tipo/ativo/phone_id.

    Le o doc DIRETO em vez de channel_service.get_send_credentials de proposito:
    aquele helper tem um override por env (WHATSAPP_TOKEN/WHATSAPP_PHONE_NUMBER_ID)
    que, num shell com essas vars setadas, mandaria a campanha pelo numero de
    OUTRO cliente sem avisar. Aqui a fonte e so o registry.
    """
    from firestore_common import global_document

    snap = global_document("channels", channel_id).get()
    if not snap.exists:
        raise Fatal("Canal {} nao existe na colecao channels.".format(channel_id))
    canal = snap.to_dict() or {}

    tid = str(canal.get("tenant_id") or "")
    if tenant and tid != tenant:
        raise Fatal("Canal {} pertence ao tenant {!r}, esperado {!r}.".format(
            channel_id, tid, tenant))
    if not canal.get("is_active"):
        raise Fatal("Canal {} esta INATIVO.".format(channel_id))
    if canal.get("channel_type") != "standard":
        raise Fatal("Canal {} e {!r}; campanha so sai por canal standard.".format(
            channel_id, canal.get("channel_type")))

    phone_id = str(canal.get("phone_number_id") or "").strip()
    token = str(canal.get("access_token") or "").strip()
    waba = str(canal.get("waba_id") or "").strip()
    if not phone_id or not token or not waba:
        raise Fatal("Canal {} sem phone_number_id/access_token/waba_id.".format(channel_id))
    if expect_phone_id and phone_id != expect_phone_id:
        raise Fatal(
            "phone_number_id do canal {} e {}, mas --expect-phone-id exige {}. "
            "Abortando pra nao disparar pelo numero errado.".format(
                channel_id, phone_id, expect_phone_id))
    return canal, token, phone_id, waba


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def checar_saude(phone_id, token):
    st, data = graph_get(
        "{}?fields=health_status,quality_rating,throughput,status,name_status".format(phone_id),
        token)
    if st != 200:
        raise Fatal("Nao consegui ler o phone_id na Meta: {}".format(
            json.dumps(data, ensure_ascii=False)[:300]))
    saude = (data.get("health_status") or {}).get("can_send_message")
    print("  numero      : status={} quality={} throughput={} name_status={}".format(
        data.get("status"), data.get("quality_rating"),
        (data.get("throughput") or {}).get("level"), data.get("name_status")))
    print("  can_send    : {}".format(saude))
    for ent in (data.get("health_status") or {}).get("entities") or []:
        if ent.get("can_send_message") not in ("AVAILABLE", None):
            print("  !! entidade {} {} -> {}".format(
                ent.get("entity_type"), ent.get("id"), ent.get("can_send_message")))
    if saude != "AVAILABLE":
        raise Fatal("health_status.can_send_message={} — nao comece a campanha.".format(saude))
    return data


def checar_template(waba, token, nome, idioma):
    """Confirma que o template esta APROVADO no idioma e SEM variaveis."""
    st, data = graph_get(
        "{}/message_templates?name={}&fields=name,language,category,status,components"
        "&limit=50".format(waba, urllib.parse.quote(nome)), token)
    if st != 200:
        raise Fatal("Nao consegui listar templates da WABA {}: {}".format(
            waba, json.dumps(data, ensure_ascii=False)[:300]))
    achados = [t for t in (data.get("data") or []) if t.get("name") == nome]
    if not achados:
        raise Fatal("Template {!r} nao existe na WABA {}.".format(nome, waba))
    no_idioma = [t for t in achados if str(t.get("language")) == idioma]
    if not no_idioma:
        raise Fatal("Template {!r} existe mas nao no idioma {!r} (tem: {}).".format(
            nome, idioma, sorted({str(t.get("language")) for t in achados})))
    tpl = no_idioma[0]
    if str(tpl.get("status")).upper() != "APPROVED":
        raise Fatal("Template {!r}/{} esta {}, nao APPROVED.".format(
            nome, idioma, tpl.get("status")))

    corpo = ""
    variaveis = 0
    for comp in tpl.get("components") or []:
        texto = str(comp.get("text") or "")
        variaveis += texto.count("{{")
        if str(comp.get("type")).upper() == "BODY":
            corpo = texto
        if comp.get("buttons"):
            variaveis += sum(1 for b in comp["buttons"] if b.get("type") == "URL"
                             and "{{" in str(b.get("url") or ""))
    print("  template    : {} / {} / {} / {}".format(
        tpl.get("name"), tpl.get("language"), tpl.get("category"), tpl.get("status")))
    print("  variaveis   : {}".format(variaveis))
    if variaveis:
        raise Fatal(
            "Template tem {} variavel(is). Este script envia SEM components "
            "(mandar components errado da erro 132000 e aborta tudo). Use um "
            "template estatico ou estenda o script.".format(variaveis))
    print("  --- corpo enviado ao cliente ---")
    for linha in corpo.splitlines():
        print("  | {}".format(linha))
    print("  --------------------------------")
    return tpl


# ---------------------------------------------------------------------------
# Relatorio / retomada
# ---------------------------------------------------------------------------
def _absorver_relatorio(caminho, acc):
    """Le UM relatorio para dentro de `acc`. Retorna quantas linhas usou.

    Valida o cabecalho antes de confiar: a pasta de relatorios e a mesma dos
    CSVs de ENTRADA, e o glob de irmaos poderia pegar uma lista de numeros por
    engano. Sem as colunas do relatorio, ignora o arquivo.
    """
    try:
        with open(caminho, "r", encoding="utf-8-sig", newline="") as fh:
            leitor = csv.DictReader(fh)
            if not {"wa_id_enviado", "outcome"}.issubset(set(leitor.fieldnames or [])):
                return 0
            usadas = 0
            for linha in leitor:
                wa = str(linha.get("wa_id_enviado") or "").strip()
                if not wa:
                    continue
                novo = str(linha.get("outcome") or "").strip()
                # TERMINAL VENCE: "sent" gravado em qualquer arquivo NUNCA e
                # rebaixado por um "failed_retryable" de outro. O merge ingenuo
                # ("ultimo vence") reintroduziria o reenvio que a retomada existe
                # pra impedir.
                if _PESO_OUTCOME.get(novo, 0) >= _PESO_OUTCOME.get(acc.get(wa, ""), 0):
                    acc[wa] = novo
                usadas += 1
            return usadas
    except (OSError, csv.Error, UnicodeDecodeError):
        return 0


def ler_relatorio(caminho, template):
    """{wa_id: outcome} de TODOS os relatorios desta campanha na mesma pasta.

    Nao basta ler `caminho`: versoes antigas deste script carimbavam a data no
    nome default, entao o relatorio de ontem tem outro nome. Ignora-lo faria a
    retomada devolver vazio EM SILENCIO e reenviar o template pra quem ja
    recebeu (no fatiamento diario, os MESMOS primeiros N todo dia).
    Retorna (mapa, arquivos_lidos).
    """
    if not caminho:
        return {}, []
    pasta = os.path.dirname(caminho) or "."
    candidatos = sorted(set(
        glob.glob(os.path.join(pasta, "{}_*.csv".format(template))) + [caminho]
    ))
    acc, lidos = {}, []
    for cand in candidatos:
        if not os.path.exists(cand):
            continue
        if _absorver_relatorio(cand, acc):
            lidos.append(os.path.basename(cand))
    return acc, lidos


def abrir_relatorio(caminho):
    novo = not os.path.exists(caminho)
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    fh = open(caminho, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=COLUNAS_RELATORIO, extrasaction="ignore")
    if novo:
        w.writeheader()
        fh.flush()
    return fh, w


def gravar(fh, w, **campos):
    campos.setdefault("ts_utc", datetime.now(timezone.utc).isoformat())
    w.writerow(campos)
    fh.flush()  # Ctrl+C nao pode perder o que ja foi enviado


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------
def so_nono_digito(enviado, canonico):
    """True quando a unica diferenca entre os dois e o 9o digito brasileiro.

    A Meta responde com o wa_id canonico DELA, que no Brasil costuma vir SEM o
    9 mesmo quando mandamos com (ex.: enviado 5531982779779 -> canonico
    553182779779). Isso e esperado e converge: o webhook aplica
    normalize_br_phone no inbound e a thread volta pra forma de 13 digitos.
    Divergencia de QUALQUER outro tipo nao e rotina e merece alarde.
    """
    if not enviado or not canonico or enviado == canonico:
        return False
    curto, longo = sorted((enviado, canonico), key=len)
    return (len(longo) - len(curto) == 1 and len(longo) == 13
            and longo.startswith("55") and longo[4] == "9"
            and longo[:4] + longo[5:] == curto)


def montar_payload(wa_id, template, idioma):
    # "+" explicito: sem ele a Meta prefixa o DDI do PROPRIO numero do negocio
    # e a mensagem pode ir pro destinatario errado.
    return {
        "messaging_product": "whatsapp",
        "to": "+" + wa_id,
        "type": "template",
        "template": {"name": template, "language": {"code": idioma}},
    }


def classificar(http_status, corpo):
    """(classe, code, subcode, title, message). classe in fatal|backoff|pula|ok."""
    if http_status == 200:
        return "ok", "", "", "", ""
    err = (corpo or {}).get("error") or {}
    code = err.get("code")
    subcode = err.get("error_subcode")
    title = str(err.get("error_title") or err.get("type") or "")
    msg = str(err.get("message") or "")

    try:
        code_i = int(code)
    except (TypeError, ValueError):
        code_i = None

    if code_i == 131009:
        texto = msg.lower()
        if subcode in SUBCODES_BILLING or "payment" in texto or "not subscribed" in texto:
            return "fatal", code, subcode, title, msg
        return "pula", code, subcode, title, msg
    if code_i in CODIGOS_FATAIS:
        return "fatal", code, subcode, title, msg
    if code_i in CODIGOS_BACKOFF:
        return "backoff", code, subcode, title, msg
    if code_i in CODIGOS_PULA:
        return "pula", code, subcode, title, msg
    # -1 = a conexao morreu DEPOIS do request sair; 504 = o gateway desistiu de
    # esperar o backend. Nos dois casos a Meta pode ter aceitado a mensagem.
    # Retentar aqui duplicaria o aviso pro paciente.
    if http_status in (-1, 504):
        return "incerto", code, subcode, title, msg
    # 429/500/502/503 e o status 0 (falha antes de enviar): a Meta afirmou que
    # NAO processou, ou nem chegou nela. Retentar e seguro.
    if http_status in (429, 500, 502, 503) or http_status == 0:
        return "backoff", code, subcode, title, msg
    # Desconhecido: trata como por-numero, mas o circuit breaker segura a onda
    # se virar epidemia.
    return "pula", code, subcode, title, msg


def enviar_um(phone_id, token, wa_id, template, idioma, tentativas_backoff, pausa_backoff):
    """Envia com retry em erro global. Retorna dict do resultado."""
    payload = montar_payload(wa_id, template, idioma)
    tentativa = 0
    while True:
        tentativa += 1
        http_status, corpo = graph_post("{}/messages".format(phone_id), token, payload)
        classe, code, subcode, title, msg = classificar(http_status, corpo)

        if classe == "ok":
            contatos = corpo.get("contacts") or [{}]
            msgs = corpo.get("messages") or [{}]
            return {
                "classe": "ok",
                "wa_id_meta": str(contatos[0].get("wa_id") or ""),
                "wa_message_id": str(msgs[0].get("id") or ""),
                "message_status": str(msgs[0].get("message_status") or ""),
                "http_status": http_status, "tentativas": tentativa,
                "error_code": "", "error_subcode": "", "error_title": "", "error_message": "",
            }

        if classe == "incerto":
            # NAO retenta: a Meta pode ter aceitado. Devolve pro chamador
            # registrar como incerto e seguir pro proximo numero.
            return {
                "classe": "incerto",
                "wa_id_meta": "", "wa_message_id": "", "message_status": "",
                "http_status": http_status, "tentativas": tentativa,
                "error_code": code, "error_subcode": subcode,
                "error_title": title, "error_message": msg,
            }

        if classe == "backoff" and tentativa <= tentativas_backoff:
            espera = pausa_backoff * (2 ** (tentativa - 1))
            print("    ~ backoff {}s (code={} http={} tentativa {}/{})".format(
                espera, code, http_status, tentativa, tentativas_backoff), flush=True)
            time.sleep(espera)
            continue

        return {
            "classe": "fatal" if classe == "fatal" else (
                "backoff_esgotado" if classe == "backoff" else "pula"),
            "wa_id_meta": "", "wa_message_id": "", "message_status": "",
            "http_status": http_status, "tentativas": tentativa,
            "error_code": code, "error_subcode": subcode,
            "error_title": title, "error_message": msg,
        }


# ---------------------------------------------------------------------------
# Selecao de alvos
# ---------------------------------------------------------------------------
def alvos_do_csv(args):
    alvos, rejeitados, meta = load_targets(
        args.csv, allow_international=args.allow_international, column=args.column)
    print("  arquivo     : {}".format(args.csv))
    print("  delimitador={!r} header={} coluna=[{}] ({})".format(
        meta["delimiter"], meta["has_header"], meta["column_index"], meta["column_source"]))
    if meta["header"]:
        print("  colunas     : {}".format([str(h) for h in meta["header"]]))
    print("  linhas de dados: {}".format(meta["total_lines"]))
    return alvos, rejeitados, meta


def alvos_de_teste():
    alvos = []
    for bruto in NUMEROS_TESTE:
        info = inspect_wa_id(bruto)
        if info["reason"]:
            raise Fatal("Numero de teste {!r} invalido: {}".format(bruto, info["reason"]))
        alvos.append({"wa_id": info["wa_id"], "line": 0, "raw": bruto,
                      "kind": info["kind"], "added_ninth": info["added_ninth"],
                      "dupes": [], "row": []})
    return alvos, [], {"header": [], "column_index": -1}


def _data_do_alvo(alvo, idx):
    """datetime da coluna de data do alvo, ou None se ausente/ilegivel."""
    linha = alvo.get("row") or []
    bruto = str(linha[idx]).strip() if idx < len(linha) else ""
    if not bruto:
        return None
    try:
        dt = datetime.fromisoformat(bruto)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _indice_da_coluna(meta, coluna_data, flag):
    header = [str(h) for h in (meta.get("header") or [])]
    if coluna_data not in header:
        raise Fatal("{} exige --date-column valido; {!r} nao existe no CSV "
                    "(colunas: {}).".format(flag, coluna_data, header))
    return header.index(coluna_data)


def ordenar_por_recencia(alvos, meta, coluna_data):
    """Mais recente primeiro. Quem nao tem data vai pro FIM.

    A ordem importa mais que o ritmo pra qualidade: quem falou com a clinica
    ontem reconhece o remetente e nao bloqueia; quem falou ha 11 meses e o
    publico que gera denuncia. Mandando dos quentes pros frios, a reputacao
    do template ja esta construida quando a cauda fria chega — e se a
    qualidade cair no meio, o que sobra sem enviar e justamente a parte que
    menos valia a pena.
    """
    idx = _indice_da_coluna(meta, coluna_data, "--sort-recent")
    sem_data = sum(1 for a in alvos if _data_do_alvo(a, idx) is None)
    antigo = datetime.min.replace(tzinfo=timezone.utc)
    ordenados = sorted(alvos, key=lambda a: _data_do_alvo(a, idx) or antigo, reverse=True)
    if ordenados:
        primeiro = _data_do_alvo(ordenados[0], idx)
        ultimo = next((_data_do_alvo(a, idx) for a in reversed(ordenados)
                       if _data_do_alvo(a, idx) is not None), None)
        print("  ordem       : mais recente primeiro ({} -> {}), {} sem data no fim".format(
            str(primeiro)[:10] if primeiro else "?",
            str(ultimo)[:10] if ultimo else "?", sem_data))
    return ordenados


def filtrar_por_data(alvos, meta, coluna_data, dias):
    """Mantem so quem tem contato mais recente que `dias`. Sem data -> mantem."""
    header = [str(h) for h in (meta.get("header") or [])]
    if coluna_data not in header:
        raise Fatal("--date-column {!r} nao existe no CSV (colunas: {}).".format(
            coluna_data, header))
    idx = header.index(coluna_data)
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    mantidos, fora, sem_data = [], [], 0
    for alvo in alvos:
        linha = alvo.get("row") or []
        bruto = str(linha[idx]).strip() if idx < len(linha) else ""
        if not bruto:
            sem_data += 1
            mantidos.append(alvo)
            continue
        try:
            dt = datetime.fromisoformat(bruto)
        except ValueError:
            sem_data += 1
            mantidos.append(alvo)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        (mantidos if dt >= corte else fora).append(alvo)
    print("  janela      : ultimos {} dias por {!r} -> mantidos={} fora={} sem_data={}".format(
        dias, coluna_data, len(mantidos), len(fora), sem_data))
    return mantidos, fora


def main():
    p = argparse.ArgumentParser(
        description="Dispara um template aprovado para uma lista de numeros.")
    p.add_argument("--csv", help="CSV com os numeros (obrigatorio sem --test)")
    p.add_argument("--column", default="",
                   help="nome da coluna de telefone (ex.: user_id). Sem isso, "
                        "o leitor tenta adivinhar — prefira explicito.")
    p.add_argument("--test", action="store_true",
                   help="ignora o CSV e usa os 2 numeros de teste combinados")
    p.add_argument("--tenant", default="varizemed")
    p.add_argument("--channel-id", type=int, default=7)
    p.add_argument("--expect-phone-id", default="1257632794095120",
                   help="trava de seguranca: aborta se o canal tiver outro phone_id")
    p.add_argument("--template", default="aviso_novo_numero_val")
    p.add_argument("--language", default="pt_BR")
    p.add_argument("--out", default="",
                   help="CSV de relatorio (default: scripts/_exports/campanhas/<template>_<data>.csv)")
    p.add_argument("--max-sends", type=int, default=250,
                   help="teto de envios NESTA execucao (tier da Meta e por 24h)")
    p.add_argument("--sleep", type=float, default=1.5, help="pausa entre envios (s)")
    p.add_argument("--batch-size", type=int, default=50, help="envios por lote")
    p.add_argument("--batch-pause", type=float, default=60.0, help="pausa entre lotes (s)")
    p.add_argument("--canary-pause", type=float, default=20.0,
                   help="pausa apos o 1o envio antes de liberar o resto (0 desliga)")
    p.add_argument("--date-column", default="",
                   help="coluna de data pra filtrar por recencia (ex.: last_inbound_at)")
    p.add_argument("--since-days", type=int, default=0,
                   help="so quem teve contato nos ultimos N dias (exige --date-column)")
    p.add_argument("--sort-recent", action="store_true",
                   help="envia primeiro para quem falou com a clinica mais "
                        "recentemente (exige --date-column). Constroi reputacao "
                        "com quem lembra da empresa antes de chegar na cauda fria.")
    p.add_argument("--include-landline", action="store_true",
                   help="nao pular numeros fixos (default: pula, quase nunca tem WhatsApp)")
    p.add_argument("--allow-international", action="store_true",
                   help="nao pular numeros de fora do Brasil")
    p.add_argument("--retry-failed", action="store_true",
                   help="reinclui quem falhou de forma permanente em execucao anterior")
    p.add_argument("--retry-incertos", action="store_true",
                   help="reinclui os 'sent_incerto' (conexao caiu depois de enviar). "
                        "So use depois de conferir no log do Cloud Run se a mensagem "
                        "chegou — senao o paciente recebe o aviso duas vezes.")
    p.add_argument("--no-resume", action="store_true",
                   help="ignora o relatorio existente (PERIGO: reenvia pra quem ja recebeu)")
    p.add_argument("--ignore-pacing", action="store_true",
                   help="nao aborta em held_for_quality_assessment")
    p.add_argument("--max-consecutivas", type=int, default=5,
                   help="aborta apos N falhas seguidas")
    p.add_argument("--backoff-tentativas", type=int, default=4)
    p.add_argument("--backoff-pausa", type=float, default=15.0)
    p.add_argument("--yes", action="store_true", help="ENVIA (default: dry-run)")
    args = p.parse_args()

    if not args.test and not args.csv:
        p.error("--csv e obrigatorio (ou use --test)")
    if args.since_days and not args.date_column:
        p.error("--since-days exige --date-column")
    if args.sort_recent and not args.date_column:
        p.error("--sort-recent exige --date-column (ex.: --date-column last_inbound_at)")
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        print("FIRESTORE_PROJECT_ID nao setado. Ex.: "
              "$env:FIRESTORE_PROJECT_ID = \"project-4a851bf9-f475-418c-800\"")
        return 1

    if args.test:
        args.max_sends = min(args.max_sends, len(NUMEROS_TESTE))
        args.sleep = max(args.sleep, 3.0)
        args.canary_pause = 0.0

    if not args.out:
        # NUNCA carimbar data neste nome. A retomada le exatamente este arquivo;
        # um nome que muda de um dia pro outro faz ler_relatorio devolver vazio
        # em silencio e o fatiamento diario reenvia os MESMOS primeiros N todo
        # dia — um grupo fixo de pacientes levaria uma mensagem por dia.
        # Estavel por tenant+canal: a mesma campanha acumula no mesmo relatorio.
        sufixo = "teste" if args.test else "{}_ch{}".format(args.tenant, args.channel_id)
        args.out = os.path.join(_AQUI, "_exports", "campanhas",
                                "{}_{}.csv".format(args.template, sufixo))

    print("=" * 72)
    print("CAMPANHA {} | tenant={} canal={} | {}".format(
        args.template, args.tenant, args.channel_id,
        "MODO TESTE" if args.test else "lista do CSV"))
    print("=" * 72)

    # --- 1. canal -----------------------------------------------------------
    print()
    print("[1/4] Canal")
    canal, token, phone_id, waba = carregar_canal(
        args.channel_id, args.tenant, args.expect_phone_id.strip())
    print("  canal       : #{} {!r} tenant={} tipo={}".format(
        canal.get("id"), canal.get("label"), canal.get("tenant_id"),
        canal.get("channel_type")))
    print("  numero      : {} (phone_id {})".format(
        canal.get("display_phone_number"), phone_id))
    print("  waba        : {}".format(waba))

    # --- 2. preflight na Meta ----------------------------------------------
    print()
    print("[2/4] Preflight na Meta")
    checar_saude(phone_id, token)
    checar_template(waba, token, args.template, args.language)

    # --- 3. lista -----------------------------------------------------------
    print()
    print("[3/4] Lista")
    if args.test:
        alvos, rejeitados, meta = alvos_de_teste()
        print("  numeros de teste: {}".format([redact_phone(n) for n in NUMEROS_TESTE]))
    else:
        alvos, rejeitados, meta = alvos_do_csv(args)

    total_bruto = len(alvos) + len(rejeitados)
    por_motivo = {}
    for r in rejeitados:
        por_motivo[r["reason"]] = por_motivo.get(r["reason"], 0) + 1
    dupes = sum(len(a["dupes"]) for a in alvos)
    print("  validos={} rejeitados={} {} duplicatas_colapsadas={}".format(
        len(alvos), len(rejeitados), por_motivo or "", dupes))
    com_nono = sum(1 for a in alvos if a["added_ninth"])
    if com_nono:
        print("  ganharam o 9o digito: {} (formato antigo do WhatsApp)".format(com_nono))

    if args.since_days:
        alvos, _fora = filtrar_por_data(alvos, meta, args.date_column, args.since_days)

    if args.sort_recent:
        alvos = ordenar_por_recencia(alvos, meta, args.date_column)

    if not args.include_landline:
        fixos = [a for a in alvos if a["kind"] == "landline"]
        alvos = [a for a in alvos if a["kind"] != "landline"]
        if fixos:
            print("  fixos pulados: {} (--include-landline pra incluir)".format(len(fixos)))

    if args.no_resume:
        ja_visto, relatorios = {}, []
        print("  !! --no-resume: a retomada esta DESLIGADA. Quem ja recebeu vai "
              "receber DE NOVO.")
    else:
        ja_visto, relatorios = ler_relatorio(args.out, args.template)
    # Silencio aqui e perigoso: relatorio vazio pode ser 'campanha nova' ou
    # 'apontei pro arquivo errado'. O operador tem que ver a diferenca.
    if relatorios:
        print("  relatorios lidos: {}".format(relatorios))
    elif not args.no_resume:
        print("  retomada    : nenhum relatorio anterior encontrado em {} "
              "(campanha nova)".format(os.path.dirname(args.out) or "."))
    if ja_visto:
        terminais = set(OUTCOMES_TERMINAIS)
        if args.retry_failed:
            terminais.discard("failed_permanent")
        if args.retry_incertos:
            terminais.discard("sent_incerto")
        antes = len(alvos)
        alvos = [a for a in alvos if ja_visto.get(a["wa_id"]) not in terminais]
        print("  retomada    : {} ja com desfecho no relatorio -> restam {}".format(
            antes - len(alvos), len(alvos)))

    elegiveis = len(alvos)
    if elegiveis > args.max_sends:
        print("  teto        : {} elegiveis > --max-sends {} -> envia os {} primeiros; "
              "rode de novo depois pra continuar".format(
                  elegiveis, args.max_sends, args.max_sends))
        alvos = alvos[:args.max_sends]

    if not alvos:
        print()
        print("Nada a enviar. Fim.")
        return 0

    por_lote = max(1, args.batch_size)
    lotes = (len(alvos) + por_lote - 1) // por_lote
    segundos = len(alvos) * args.sleep + max(0, lotes - 1) * args.batch_pause + args.canary_pause
    print()
    print("[4/4] Plano")
    print("  a enviar    : {} de {} elegiveis (lista bruta {})".format(
        len(alvos), elegiveis, total_bruto))
    print("  ritmo       : 1 a cada {}s, lotes de {} com pausa de {}s".format(
        args.sleep, por_lote, args.batch_pause))
    print("  duracao est.: {}".format(str(timedelta(seconds=int(segundos)))))
    print("  relatorio   : {}".format(args.out))
    print("  amostra     : {}".format([redact_phone(a["wa_id"]) for a in alvos[:5]]))

    if not args.yes:
        print()
        print("DRY-RUN — nada foi enviado. Adicione --yes para disparar.")
        return 0

    # --- envio --------------------------------------------------------------
    print()
    print("=" * 72)
    print("ENVIANDO (Ctrl+C interrompe com seguranca; o relatorio ja esta gravado)")
    print("=" * 72)
    fh, writer = abrir_relatorio(args.out)
    enviados = falhas = pulados = 0
    canonizados = estranhos = incertos = 0
    consecutivas = 0
    saida = 0
    try:
        for i, alvo in enumerate(alvos, start=1):
            wa_id = alvo["wa_id"]
            res = enviar_um(phone_id, token, wa_id, args.template, args.language,
                            args.backoff_tentativas, args.backoff_pausa)

            if res["classe"] == "ok":
                enviados += 1
                consecutivas = 0
                # A canonizacao do 9o digito acontece em TODO numero BR antigo:
                # avisar linha a linha viraria 4.500 linhas de ruido. Conta e
                # reporta no resumo. Divergencia de outro tipo, essa sim, grita.
                meta_wa = res["wa_id_meta"]
                if so_nono_digito(wa_id, meta_wa):
                    canonizados += 1
                    nota = ""
                elif meta_wa and meta_wa != wa_id:
                    estranhos += 1
                    nota = "  !! Meta resolveu para OUTRO numero: {} ({} digitos)".format(
                        redact_phone(meta_wa), len(meta_wa))
                else:
                    nota = ""
                print("  [{}/{}] OK   {} {}{}".format(
                    i, len(alvos), redact_phone(wa_id),
                    res["message_status"] or "accepted", nota), flush=True)
                gravar(fh, writer, input_raw=alvo["raw"], wa_id_enviado=wa_id,
                       outcome="sent", **{k: res[k] for k in (
                           "wa_id_meta", "message_status", "wa_message_id",
                           "http_status", "error_code", "error_subcode",
                           "error_title", "error_message", "tentativas")})
                if res["message_status"] == "held_for_quality_assessment" and not args.ignore_pacing:
                    raise Fatal(
                        "A Meta SEGUROU a mensagem (held_for_quality_assessment): o "
                        "template entrou em pacing. PARE, espere algumas horas e "
                        "confira a qualidade antes de continuar. (--ignore-pacing forca)")
            elif res["classe"] == "incerto":
                # A conexao caiu depois do request sair. Nao da pra saber se a
                # Meta aceitou. Registra como terminal (a retomada NAO reenvia)
                # e conta pro circuit breaker: se a rede quebrou de verdade,
                # isso se repete e o script para sozinho.
                incertos += 1
                consecutivas += 1
                print("  [{}/{}] INCERTO {} — a conexao caiu depois de enviar; "
                      "pode ter chegado. Nao vou reenviar. {}".format(
                          i, len(alvos), redact_phone(wa_id),
                          (res["error_message"] or "")[:80]), flush=True)
                gravar(fh, writer, input_raw=alvo["raw"], wa_id_enviado=wa_id,
                       outcome="sent_incerto", **{k: res[k] for k in (
                           "wa_id_meta", "message_status", "wa_message_id",
                           "http_status", "error_code", "error_subcode",
                           "error_title", "error_message", "tentativas")})
                if consecutivas >= args.max_consecutivas:
                    raise Fatal("{} falhas consecutivas — abortando por seguranca.".format(
                        consecutivas))
            else:
                permanente = res["classe"] in ("fatal", "pula")
                falhas += 1
                consecutivas += 1
                if res["classe"] == "pula":
                    pulados += 1
                print("  [{}/{}] FALHA {} http={} code={} sub={} {}".format(
                    i, len(alvos), redact_phone(wa_id), res["http_status"],
                    res["error_code"], res["error_subcode"],
                    (res["error_message"] or "")[:110]), flush=True)
                gravar(fh, writer, input_raw=alvo["raw"], wa_id_enviado=wa_id,
                       outcome="failed_permanent" if permanente else "failed_retryable",
                       **{k: res[k] for k in (
                           "wa_id_meta", "message_status", "wa_message_id",
                           "http_status", "error_code", "error_subcode",
                           "error_title", "error_message", "tentativas")})
                if res["classe"] == "fatal":
                    raise Fatal("Erro FATAL da Meta (code={}): {}".format(
                        res["error_code"], res["error_message"]))
                if consecutivas >= args.max_consecutivas:
                    raise Fatal("{} falhas consecutivas — abortando por seguranca.".format(
                        consecutivas))
                if enviados + falhas >= 20 and falhas > (enviados + falhas) * 0.10:
                    raise Fatal(
                        "Taxa de falha {:.0%} acima de 10% em {} tentativas — abortando.".format(
                            falhas / float(enviados + falhas), enviados + falhas))

            if i == len(alvos):
                break
            if i == 1 and args.canary_pause > 0:
                print("  ... canario enviado, aguardando {}s antes de liberar o resto".format(
                    args.canary_pause), flush=True)
                time.sleep(args.canary_pause)
            elif i % por_lote == 0:
                print("  ... lote de {} concluido, pausa de {}s".format(
                    por_lote, args.batch_pause), flush=True)
                time.sleep(args.batch_pause)
            else:
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print()
        print("Interrompido pelo operador.")
        saida = 130
    except Fatal as exc:
        print()
        print("ABORTADO: {}".format(exc))
        saida = 2
    finally:
        fh.close()

    print()
    print("=" * 72)
    print("RESUMO: aceitos_pela_meta={} falhas={} (pulados={}) incertos={} de {} tentados".format(
        enviados, falhas, pulados, incertos, enviados + falhas + incertos))
    if incertos:
        print("  !! {} envios INCERTOS: a conexao caiu depois do request sair, entao a".format(incertos))
        print("     Meta pode ter aceitado. NAO foram reenviados (evita duplicata).")
        print("     Confira no log do Cloud Run se chegaram; se NAO chegaram, rode de")
        print("     novo com --retry-incertos. Estao no relatorio como sent_incerto.")
    if canonizados:
        print("  {} tiveram o 9o digito removido pela Meta (esperado em numero BR "
              "antigo; o webhook devolve o 9 na resposta)".format(canonizados))
    if estranhos:
        print("  !! {} foram resolvidos pela Meta para um numero DIFERENTE — "
              "confira a coluna wa_id_meta do relatorio".format(estranhos))
    print("Relatorio: {}".format(args.out))
    print("Lembre: 'aceito' != 'entregue'. O desfecho real chega no webhook; falhas")
    print("aparecem no log do Cloud Run como '[WA STATUS] ... failed' com o codigo.")
    if enviados + falhas < elegiveis:
        print("Faltam {} da lista — rode o MESMO comando de novo (ele retoma).".format(
            elegiveis - (enviados + falhas)))
    print("=" * 72)
    return saida


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fatal as exc:
        print()
        print("ABORTADO: {}".format(exc))
        sys.exit(2)
