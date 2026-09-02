# -*- coding: utf-8 -*-
"""Replica um template aprovado de um WABA-mestre para o WABA de outro canal.

Estrategia do PO (2026-09-01): o WABA do SAC da Castro (canal 6) e o
catalogo-mestre dos templates padrao da plataforma. A aprovacao da Meta e
POR WABA — nao existe transferencia; replicar = LER a definicao no mestre e
RE-SUBMETER a mesma definicao no WABA do tenant, que passa pela revisao dele.

Read-only por default (dry-run): mostra exatamente o payload que seria
submetido. So escreve na Meta com --apply.

Decisao consciente: NAO enviamos allow_category_change — se a Meta discordar
da categoria (ex.: quiser rebaixar UTILITY pra MARKETING), a submissao FALHA
em vez de aceitar em silencio. Rebaixamento de categoria muda preco e regra
de opt-out; tem que voltar pro PO.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.replicate_template `
      --template rating_request --lang pt_BR --from-channel 6 --to-channel 7
  # conferiu o payload? repete com --apply
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from firestore_common import collection_name, get_firestore_client

GRAPH = "https://graph.facebook.com/v22.0"


def _mask_phone(p):
    p = str(p or "")
    return (p[:-4] + "****") if len(p) > 4 else "****"


def _graph(url, token, payload=None):
    """GET (payload None) ou POST json. Nunca loga o token."""
    sep = "&" if "?" in url else "?"
    full = "{}{}access_token={}".format(url, sep, urllib.parse.quote(token, safe=""))
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        full, data=data,
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return None, json.loads(body)
        except Exception:
            return None, {"raw": body[:400], "status": e.code}


def _load_channel(fs, channel_id):
    for d in fs.collection(collection_name("channels")).stream():
        data = d.to_dict() or {}
        if data.get("id") == channel_id:
            return data
    return None


def _require(cond, msg):
    if not cond:
        print("FATAL: {}".format(msg))
        sys.exit(1)


def _fetch_template(waba, token, name, lang):
    url = ("{}/{}/message_templates?fields=name,language,category,status,components"
           "&name={}".format(GRAPH, waba, urllib.parse.quote(name, safe="")))
    data, err = _graph(url, token)
    _require(err is None, "Meta GET falhou: {}".format(json.dumps(err)[:300] if err else "?"))
    for t in data.get("data", []) or []:
        if t.get("name") == name and t.get("language") == lang:
            return t
    return None


def main():
    ap = argparse.ArgumentParser(description="Replica template entre WABAs (por canal)")
    ap.add_argument("--template", required=True)
    ap.add_argument("--lang", default="pt_BR")
    ap.add_argument("--from-channel", type=int, default=6, help="canal do WABA-mestre (default 6 = SAC)")
    ap.add_argument("--to-channel", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="submete de verdade (default: dry-run)")
    args = ap.parse_args()

    fs = get_firestore_client()
    src = _load_channel(fs, args.from_channel)
    dst = _load_channel(fs, args.to_channel)
    _require(src is not None, "canal de origem {} nao encontrado".format(args.from_channel))
    _require(dst is not None, "canal de destino {} nao encontrado".format(args.to_channel))

    for label, ch in (("origem", src), ("destino", dst)):
        _require(str(ch.get("waba_id") or "").strip(), "canal de {} sem waba_id".format(label))
        _require(str(ch.get("access_token") or "").strip(), "canal de {} sem access_token".format(label))
    _require(dst.get("channel_type") == "standard",
             "canal de destino nao e standard (template so serve canal standard)")
    _require(src.get("waba_id") != dst.get("waba_id"), "origem e destino sao o MESMO WABA")

    print("Origem : canal #{} | {} | WABA {}".format(
        src.get("id"), _mask_phone(src.get("display_phone_number")), src.get("waba_id")))
    print("Destino: canal #{} | {} | WABA {}".format(
        dst.get("id"), _mask_phone(dst.get("display_phone_number")), dst.get("waba_id")))

    tpl = _fetch_template(src["waba_id"], src["access_token"], args.template, args.lang)
    _require(tpl is not None, "template {}/{} nao existe no WABA de origem".format(args.template, args.lang))
    _require(str(tpl.get("status")).upper() == "APPROVED",
             "template de origem nao esta APPROVED (status={}) — replique so aprovado".format(tpl.get("status")))

    # Idempotencia: ja existe no destino? (qualquer status conta — PENDING
    # duplicado viraria erro da Meta de qualquer jeito)
    existing = _fetch_template(dst["waba_id"], dst["access_token"], args.template, args.lang)
    if existing is not None:
        print("\nJa existe no destino: status={} cat={} — nada a fazer.".format(
            existing.get("status"), existing.get("category")))
        return

    payload = {
        "name": tpl["name"],
        "language": tpl["language"],
        "category": tpl["category"],
        "components": tpl.get("components") or [],
    }
    print("\nPayload da submissao:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not args.apply:
        print("\nDRY-RUN — nada submetido. Repita com --apply para submeter.")
        return

    data, err = _graph("{}/{}/message_templates".format(GRAPH, dst["waba_id"]),
                       dst["access_token"], payload=payload)
    if err is not None:
        print("\nERRO na submissao: {}".format(json.dumps(err, ensure_ascii=False)[:500]))
        sys.exit(1)
    print("\nSubmetido: id={} status={} category={}".format(
        data.get("id"), data.get("status"), data.get("category")))
    print("Confira depois com: python -m scripts._diag_templates_by_waba")


if __name__ == "__main__":
    main()
