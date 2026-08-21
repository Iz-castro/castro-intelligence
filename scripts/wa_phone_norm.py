# -*- coding: utf-8 -*-
"""Normalizacao de wa_id brasileiro + leitura tolerante de CSV.

Usado por scripts/send_template_bulk.py (disparo de template em lote).

REGRA DO 9o DIGITO — alinhada com database_firestore.normalize_br_phone:
o CRM guarda o wa_id JA COM o 9 (13 digitos). O disparo tem que usar a mesma
forma, senao o webhook da resposta grava um wa_id diferente do que foi
disparado e, como conversation_id e deterministico ("{channel_id}__{wa_id}"),
a mesma pessoa vira DUAS threads.

SINAL DO "+": quando o valor cru comeca com "+", os digitos JA sao E.164
completos (com codigo de pais). Nesse caso e PROIBIDO aplicar o palpite
"10/11 digitos = BR sem DDI" — um "+1 415 555 0123" (11 digitos) viraria
"DDD 14" e o template sairia pra um celular brasileiro aleatorio. Sem "+",
o molde BR e apenas uma hipotese, validada por DDD e formato.

Autotestes: ./.venv/Scripts/python.exe scripts/wa_phone_norm.py  (exit 0/1)
"""

import csv
import io
import re
import unicodedata

# DDDs validos (Anatel). 55 e DDD valido (Santa Maria/RS) e colide com o codigo
# de pais do Brasil — a desambiguacao e por COMPRIMENTO + "+", nunca por prefixo.
VALID_DDDS = frozenset([
    "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "21", "22", "24", "27", "28",
    "31", "32", "33", "34", "35", "37", "38",
    "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "51", "53", "54", "55",
    "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "71", "73", "74", "75", "77", "79",
    "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "91", "92", "93", "94", "95", "96", "97", "98", "99",
])

# Primeiro digito do numero local. Celular no plano antigo (8 digitos) abria
# com 6/7/8/9; fixo abre com 2/3/4/5. Mesmo conjunto de normalize_br_phone.
MOBILE_LEADS = ("6", "7", "8", "9")
LANDLINE_LEADS = ("2", "3", "4", "5")

# Excel salva numero longo como float ("5,5319E+12") e PERDE digitos — nao ha
# reconstrucao possivel, entao rejeita e pede reexport com a coluna como TEXTO.
_SCI_NOTATION = re.compile(r"^\s*[+-]?\d(?:[.,]\d+)?\s*[eE]\s*[+-]?\d+\s*$")

# Vocabulario fechado de rejeicao (vira coluna do relatorio).
REASONS = (
    "vazio", "sem_digitos", "notacao_cientifica", "curto_demais",
    "longo_demais", "sem_ddd", "ddd_invalido", "br_formato_suspeito", "nao_br",
)


def inspect_wa_id(raw, allow_international=False):
    """Analisa um telefone cru e devolve o diagnostico completo.

    Chaves: raw, digits, wa_id, reason, country, ddd, local,
            kind ('mobile'|'landline'|'international'|''), added_ninth.
    `wa_id` vem "" sempre que `reason` != None.
    """
    out = {
        "raw": "" if raw is None else str(raw),
        "digits": "", "wa_id": "", "reason": None,
        "country": "", "ddd": "", "local": "",
        "kind": "", "added_ninth": False,
    }
    s = out["raw"].strip()
    if not s:
        out["reason"] = "vazio"
        return out
    if _SCI_NOTATION.match(s):
        out["reason"] = "notacao_cientifica"
        return out

    # "+" em qualquer posicao inicial (depois de espaco) = E.164 explicito.
    has_plus = s.startswith("+")

    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        out["reason"] = "sem_digitos"
        return out
    if not has_plus:
        # Prefixo de operadora/discagem ("031 98277-9779", "00 55 31...").
        # Com "+" isso nao se aplica: E.164 nunca comeca com 0.
        digits = digits.lstrip("0")
        if not digits:
            out["reason"] = "sem_digitos"
            return out
    out["digits"] = digits

    n = len(digits)
    if n < 8:
        out["reason"] = "curto_demais"
        return out
    if n > 15:  # maximo do E.164 — provavel 2 numeros colados na mesma celula
        out["reason"] = "longo_demais"
        return out
    if n in (8, 9) and not has_plus:
        out["reason"] = "sem_ddd"  # NUNCA chutar DDD: do outro lado tem gente
        return out

    def _international():
        out["country"] = digits[:2]
        out["kind"] = "international"
        if allow_international:
            out["wa_id"] = digits
        else:
            out["reason"] = "nao_br"
        return out

    # --- Onde comeca o numero nacional ---
    # Com "+": os digitos sao E.164 completos. So e BR se comecar com 55 E o
    #          resto casar com o molde brasileiro. Nada de palpite.
    # Sem "+": 12/13 digitos comecando com 55 => tem DDI; 10/11 => DDD + local.
    if has_plus:
        if n in (12, 13) and digits.startswith("55"):
            ddd, local, had_cc = digits[2:4], digits[4:], True
        else:
            return _international()
    elif n in (12, 13) and digits.startswith("55"):
        ddd, local, had_cc = digits[2:4], digits[4:], True
    elif n in (10, 11):
        ddd, local, had_cc = digits[:2], digits[2:], False
    else:
        return _international()

    br = _try_br(ddd, local)
    if br is None:
        # Sem DDI explicito o molde BR era so hipotese: se nao casa, e
        # estrangeiro (nao um brasileiro com DDD estranho).
        if not had_cc:
            return _international()
        out["reason"] = "ddd_invalido" if ddd not in VALID_DDDS else "br_formato_suspeito"
        return out

    out["country"], out["ddd"], out["local"] = "55", ddd, local
    out["wa_id"], out["kind"], out["added_ninth"] = br
    return out


def _try_br(ddd, local):
    """(wa_id, kind, added_ninth) se (ddd, local) formam numero BR valido; senao None."""
    if ddd not in VALID_DDDS:
        return None
    if len(local) == 9:
        # Pos-migracao todo celular de 9 digitos abre com 9. Fixo nunca tem 9.
        return ("55" + ddd + local, "mobile", False) if local[0] == "9" else None
    if len(local) == 8:
        if local[0] in MOBILE_LEADS:
            # Celular no formato pre-2016 (sem o 9) — mesma regra do CRM.
            return ("55" + ddd + "9" + local, "mobile", True)
        if local[0] in LANDLINE_LEADS:
            return ("55" + ddd + local, "landline", False)
    return None


def normalize_wa_id(raw, allow_international=False):
    """(wa_id_normalizado, motivo_de_rejeicao_ou_None)."""
    info = inspect_wa_id(raw, allow_international=allow_international)
    return info["wa_id"], info["reason"]


def dedup_key(raw, allow_international=False):
    """Chave canonica de dedupe — o proprio wa_id normalizado.

    Colapsa "5531982779779", "553182779779", "31982779779", "3182779779" e
    "(31) 98277-9779" na mesma chave. Retorna "" se rejeitado.
    """
    return normalize_wa_id(raw, allow_international=allow_international)[0]


# ---------------------------------------------------------------------------
# Leitura tolerante de CSV (export de Firestore feito por humano)
# ---------------------------------------------------------------------------
PHONE_HEADERS = frozenset([
    "phone", "phones", "phonenumber", "telephone", "tel", "telefone",
    "telefones", "numero", "num", "number", "waid", "waphone", "whatsapp",
    "whats", "zap", "celular", "cel", "fone", "msisdn", "contato", "mobile",
    "telefonecelular", "telefone1", "phone1", "numerowhatsapp", "whatsappnumero",
])


def _norm_header(cell):
    """Minuscula, sem BOM, sem acento, so alfanumerico."""
    s = str(cell or "").replace("﻿", "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s if c.isalnum())


def _digit_count(cell):
    return sum(1 for ch in str(cell or "") if ch.isdigit())


def _decode(path):
    with open(path, "rb") as fh:
        blob = fh.read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("latin-1", errors="replace")


def _sniff_delimiter(text):
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    first = next((ln for ln in sample.splitlines() if ln.strip()), "")
    counts = {d: first.count(d) for d in (";", ",", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _pick_column(rows, header, column=""):
    """Indice da coluna de telefone.

    Prioridade: --column explicito > nome conhecido > coluna mais telefonica.
    Retorna (indice, origem). Levanta ValueError se --column nao existir.
    """
    if column:
        alvo = _norm_header(column)
        for idx, cell in enumerate(header or []):
            if _norm_header(cell) == alvo:
                return idx, "column_explicito"
        if alvo.isdigit():
            return int(alvo), "column_indice"
        raise ValueError(
            "coluna {!r} nao existe no CSV. Colunas: {}".format(
                column, [str(h) for h in (header or [])]))
    for idx, cell in enumerate(header or []):
        if _norm_header(cell) in PHONE_HEADERS:
            return idx, "header"
    width = max((len(r) for r in rows), default=1)
    best_idx, best_score = 0, -1.0
    for idx in range(width):
        hits = sum(1 for r in rows if idx < len(r) and 8 <= _digit_count(r[idx]) <= 15)
        score = hits / float(len(rows) or 1)
        if score > best_score:
            best_idx, best_score = idx, score
    if best_score <= 0:
        return 0, "fallback_primeira_coluna"
    return best_idx, "heuristica"


def _looks_like_header(row):
    if any(_norm_header(c) in PHONE_HEADERS for c in row):
        return True
    # Linha sem NENHUM candidato a telefone = cabecalho de nome desconhecido.
    return not any(_digit_count(c) >= 8 for c in row)


def read_phone_csv(path, text=None, column=""):
    """Le o CSV e devolve (rows, meta).

    rows = [{"line", "raw", "row"}] (linhas nao vazias)
    meta = {"delimiter", "has_header", "column_index", "column_source",
            "header", "total_lines"}
    """
    content = text if text is not None else _decode(path)
    delim = _sniff_delimiter(content)
    raw_rows = [r for r in csv.reader(io.StringIO(content), delimiter=delim)
                if any(str(c).strip() for c in r)]
    if not raw_rows:
        return [], {"delimiter": delim, "has_header": False, "column_index": 0,
                    "column_source": "vazio", "header": [], "total_lines": 0}

    has_header = _looks_like_header(raw_rows[0]) and len(raw_rows) > 1
    header = raw_rows[0] if has_header else []
    body = raw_rows[1:] if has_header else raw_rows

    idx, source = _pick_column(body, header, column=column)
    offset = 2 if has_header else 1
    rows = [{"line": i + offset, "raw": (r[idx] if idx < len(r) else ""), "row": r}
            for i, r in enumerate(body)]
    return rows, {"delimiter": delim, "has_header": has_header, "column_index": idx,
                  "column_source": source, "header": header, "total_lines": len(body)}


def load_targets(path, text=None, allow_international=False, column=""):
    """CSV -> (targets, rejeitados, meta). Dedupe preservando ordem de aparicao.

    targets = [{"wa_id", "line", "raw", "kind", "added_ninth", "dupes", "row"}]
    """
    rows, meta = read_phone_csv(path, text=text, column=column)
    seen, targets, rejects = {}, [], []
    for item in rows:
        info = inspect_wa_id(item["raw"], allow_international=allow_international)
        if info["reason"]:
            rejects.append({"line": item["line"], "raw": item["raw"],
                            "reason": info["reason"]})
            continue
        key = info["wa_id"]
        if key in seen:
            seen[key]["dupes"].append(item["line"])
            continue
        entry = {"wa_id": key, "line": item["line"], "raw": item["raw"],
                 "kind": info["kind"], "added_ninth": info["added_ninth"],
                 "dupes": [], "row": item["row"]}
        seen[key] = entry
        targets.append(entry)
    return targets, rejects, meta


# ---------------------------------------------------------------------------
# Autotestes
# ---------------------------------------------------------------------------
def _repo_normalize_br_phone(wa_id):
    """Copia FIEL de database_firestore.normalize_br_phone (oraculo de regressao)."""
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55"):
        ddd, local = s[2:4], s[4:]
        if local and local[0] in ("6", "7", "8", "9"):
            return "55%s9%s" % (ddd, local)
    return s


def _run_tests():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append("%s: got=%r want=%r" % (label, got, want))

    # --- todas as formas do MESMO numero colapsam ---
    for raw in ["+55 31 98277-9779", "5531982779779", "31982779779",
                "(31) 98277-9779", "55 31 8277-9779", "+553182779779",
                "3182779779", "553182779779", " 31 98277 9779 ",
                "031982779779", "+55 (31) 9 8277-9779", "55-31-98277.9779"]:
        eq(normalize_wa_id(raw), ("5531982779779", None), "mesmo numero %r" % raw)

    # --- os dois numeros de TESTE ---
    eq(normalize_wa_id("+55 31 8277-9779"), ("5531982779779", None), "teste 1")
    eq(normalize_wa_id("+553183440484"), ("5531983440484", None), "teste 2")
    eq(inspect_wa_id("+55 31 8277-9779")["added_ninth"], True, "teste 1 ganhou o 9")
    eq(inspect_wa_id("+55 31 8277-9779")["kind"], "mobile", "teste 1 e celular")

    # --- fixo nao ganha o 9 ---
    eq(normalize_wa_id("+55 31 3222-1000"), ("553132221000", None), "fixo 31")
    eq(inspect_wa_id("+55 31 3222-1000")["kind"], "landline", "fixo kind")
    eq(inspect_wa_id("5531988887777")["added_ninth"], False, "13 digitos nao mexe")

    # --- E.164 com "+": NUNCA aplicar o molde "sem DDI" ---
    # Regressao do furo real: +1 415 555 0123 = 11 digitos. Sem o tratamento do
    # "+", viraria DDD 14 e o template sairia pra um celular brasileiro.
    eq(normalize_wa_id("+14155550123"), ("", "nao_br"), "+1 EUA nao vira BR")
    eq(inspect_wa_id("+14155550123")["kind"], "international", "+1 e internacional")
    eq(normalize_wa_id("+351912345678"), ("", "nao_br"), "+351 Portugal")
    eq(normalize_wa_id("+5491123456789"), ("", "nao_br"), "+54 Argentina")
    # E.164 truncado com "+55": nao pode virar fixo de Santa Maria (DDD 55).
    eq(normalize_wa_id("+5531827797"), ("", "nao_br"), "+55 truncado rejeitado")
    eq(normalize_wa_id("+55318277"), ("", "nao_br"), "+55 muito truncado")
    # Sem "+", o mesmo 11 digitos e hipotese BR valida (DDD 41 + celular).
    eq(normalize_wa_id("41991234567"), ("5541991234567", None), "11 digitos sem + = BR")
    eq(normalize_wa_id("+351912345678", allow_international=True),
       ("351912345678", None), "internacional liberado")
    eq(normalize_wa_id("+14155550123", allow_international=True),
       ("14155550123", None), "+1 liberado quando pedido")

    # --- rejeicoes ---
    for raw, reason in [
        ("", "vazio"), ("   ", "vazio"), (None, "vazio"),
        ("sem telefone", "sem_digitos"), ("-", "sem_digitos"),
        ("98277-9779", "sem_ddd"), ("82779779", "sem_ddd"),
        ("123456", "curto_demais"),
        ("3182779779 3199998888", "longo_demais"),
        ("5,5319E+12", "notacao_cientifica"), ("5.5319e12", "notacao_cientifica"),
        ("2082779779", "nao_br"),                 # DDD 20 nao existe
        ("5520827797791", "ddd_invalido"),
        ("5531182779779", "br_formato_suspeito"),  # DDD ok, local 9 digitos com 1
    ]:
        eq(normalize_wa_id(raw)[1], reason, "rejeicao %r" % raw)
        eq(normalize_wa_id(raw)[0], "", "rejeitado nao devolve wa_id %r" % raw)

    # --- DDD 55 (Santa Maria) x codigo de pais 55 ---
    eq(normalize_wa_id("55999887766"), ("5555999887766", None), "DDD 55 sem DDI")
    eq(normalize_wa_id("5555999887766"), ("5555999887766", None), "DDD 55 com DDI")
    eq(normalize_wa_id("55 55 9988-7766"), ("5555999887766", None), "DDD 55 legado")

    # --- paridade com o CRM ---
    for s in ["553182779779", "553199998888", "551132221000", "554899887766"]:
        eq(normalize_wa_id(s)[0], _repo_normalize_br_phone(s), "paridade CRM %s" % s)

    # --- dedupe ---
    eq(dedup_key("553182779779"), dedup_key("5531982779779"), "dedupe com/sem 9")
    eq(dedup_key("(31) 98277-9779"), dedup_key("+55 31 8277-9779"), "dedupe formatos")
    if dedup_key("5531982779779") == dedup_key("553132779779"):
        fails.append("fixo colidiu com celular")

    # --- CSV: header + virgula + BOM ---
    t1 = "﻿nome,telefone,email\nMaria,+55 31 98277-9779,m@x.com\nJoao,553183440484,j@x.com\n"
    tg, rj, mt = load_targets(None, text=t1)
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv header virgula")
    eq(mt["has_header"], True, "csv header detectado")
    eq(mt["column_source"], "header", "csv coluna por nome")

    # --- CSV: ponto-e-virgula + acento no header ---
    t2 = "Nome;Número;Status\nA;31982779779;ok\nB;(31) 8344-0484;ok\n"
    tg, rj, mt = load_targets(None, text=t2)
    eq(mt["delimiter"], ";", "csv delimitador ;")
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv header acentuado")

    # --- CSV: sem header, telefone na 2a coluna ---
    t3 = "aBc123XyZ,5531982779779\ndEf456UvW,553183440484\n"
    tg, rj, mt = load_targets(None, text=t3)
    eq(mt["has_header"], False, "csv sem header")
    eq(mt["column_index"], 1, "csv coluna heuristica")
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv sem header")

    # --- CSV: --column explicito (o caso do export varizemed: 'user_id') ---
    t4 = ("wa_profile_name,user_id,status\n"
          "Maria,+553182779779,bot\n"
          "Joao,+5531983440484,active\n")
    tg, rj, mt = load_targets(None, text=t4, column="user_id")
    eq(mt["column_source"], "column_explicito", "coluna explicita")
    eq(mt["column_index"], 1, "indice da coluna explicita")
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv --column")
    try:
        load_targets(None, text=t4, column="nao_existe")
        fails.append("--column inexistente deveria levantar ValueError")
    except ValueError:
        pass

    # --- CSV: coluna unica ---
    t5 = "5531982779779\n31 8344-0484\n"
    tg, rj, mt = load_targets(None, text=t5)
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv coluna unica")

    # --- prefixos de discagem ---
    eq(normalize_wa_id("005531982779779"), ("5531982779779", None), "prefixo 00")
    eq(normalize_wa_id("031 98277-9779"), ("5531982779779", None), "prefixo 0 operadora")

    # --- CSV: sujeira + duplicata em formatos diferentes ---
    t6 = ("phone\n+55 31 98277-9779\n553182779779\n\n  \nsem telefone\n"
          "982779779\n5.5319E+12\n+55 31 8344-0484\n(31) 98344-0484\n")
    tg, rj, mt = load_targets(None, text=t6)
    eq([t["wa_id"] for t in tg], ["5531982779779", "5531983440484"], "csv dedupe")
    eq(len(tg[0]["dupes"]), 1, "dupe do 1o registrada")
    eq(len(tg[1]["dupes"]), 1, "dupe do 2o registrada")
    eq(sorted(r["reason"] for r in rj),
       ["notacao_cientifica", "sem_ddd", "sem_digitos"], "rejeicoes do csv")

    # --- CSV: TAB ---
    t7 = "nome\twhatsapp\nA\t5531982779779\n"
    tg, rj, mt = load_targets(None, text=t7)
    eq(mt["delimiter"], "\t", "csv TAB")
    eq([t["wa_id"] for t in tg], ["5531982779779"], "csv TAB valores")

    if fails:
        print("FALHAS (%d):" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("OK — autotestes de wa_phone_norm passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_tests())
