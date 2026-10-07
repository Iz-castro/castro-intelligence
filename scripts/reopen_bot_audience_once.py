# -*- coding: utf-8 -*-
"""
Reabertura em lote do PUBLICO BOT — execucao unica por script (antes da UI).

Seleciona pelas regras do plano v2 (docs/PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md,
secao 2): lead consentido (lgpd_consent=True, nao revogado), frio (>= 24h sem
mensagem do cliente), em fase de bot (sem dono, bot_completed falso, human_active
falso, ultima mensagem ao cliente nao humana), sem opt-out, sem tentativa pendente,
abaixo do teto por contato (2 em 90 dias) e do teto diario do portfolio (250).

Envia o template de retomada aprovado do canal standard do tenant pelo MESMO
caminho do lote (main._run_reopen_batch): carimba o contato ANTES de gravar a
mensagem, grava o outbound sem promover/reabrir/avancar recencia/contar como
atencao humana, registra um doc em reopen_batches (audience=bot) para o teto
diario, pacing 1.5s, aborta em 5 falhas seguidas e em held_for_quality_assessment.

Desde 2026-10-05:
  - DESFECHO COM A VAL (heuristica provisoria ate o agente expor `desfecho_bot`):
    pula quem recebeu da Val o link de agendamento (`--desfecho-link`, default
    "marcaconsultas") entre as ultimas mensagens da thread. Motivo: no lote de
    23/09, dos 71 que clicaram Encerrar, varios ja tinham agendado pela Val.
  - Teto por contato le `reopen_bot_sent_at` (legado) E `reopen_batch_sent_at`
    (formato do plano v2.2: lista de {at, audience}); o envio grava os dois.
  - Relatorio/console sem telefone: conversation_id mascarado e sem o wamid
    (o wamid carrega o telefone em base64).

ATENCAO (estado do CRM em 2026-09-23, antes da implementacao do plano v2):
  - Continuar/Retomar pelo cliente hoje leva o lead para a EQUIPE (bot_completed=True),
    nao para a Val. O turno do CX no clique (D3) ainda nao existe.
  - Encerrar grava opt-out PERMANENTE (D4 ainda nao implementada).
  - Texto livre do cliente segue para a Val normalmente.
  - Midia do cliente em fase de bot nao gera resposta (D10 ainda nao implementada).

Uso (PowerShell, raiz do repo). DEFAULT = DRY-RUN; so envia com --yes:
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts.reopen_bot_audience_once --tenant varizemed
  ./.venv/Scripts/python.exe -m scripts.reopen_bot_audience_once --tenant varizemed --only 5531983440484 --yes
  ./.venv/Scripts/python.exe -m scripts.reopen_bot_audience_once --tenant varizemed --max-sends 100 --yes

Relatorio CSV do plano/execucao em logs/reopen_bot_<tenant>_<timestamp>.csv (gitignored).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from google.cloud import firestore as _fs

# Roda a partir da raiz do repo (python -m scripts.reopen_bot_audience_once)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from firestore_common import (  # noqa: E402
    collection, document, get_firestore_client, set_tenant_context, reset_tenant_context,
    collection_name,
)
from channel_service import get_channel, get_send_credentials  # noqa: E402
from database import (  # noqa: E402
    save_wa_message, log_audit, next_sequence, reopen_batch_sends, reopen_daily_usage,
)
# Tetos e heuristica do P5 vem do config do CRM (plano v2.2 secao 7, mesmos
# envs do lote da UI): REOPEN_DAILY_CAP, REOPEN_MAX_PER_CONTACT,
# REOPEN_WINDOW_DAYS, REOPEN_COOLDOWN_HOURS, REOPEN_DESFECHO_LINK. Os envs
# antigos REOPEN_BOT_MAX_PER_CONTACT/REOPEN_BOT_WINDOW_DAYS nao valem mais.
from config import (  # noqa: E402
    REOPEN_COOLDOWN_HOURS, REOPEN_DAILY_CAP, REOPEN_DESFECHO_LINK,
    REOPEN_MAX_PER_CONTACT, REOPEN_WINDOW_DAYS,
)

REOPEN_TEMPLATE_NAME = os.getenv("REOPEN_TEMPLATE_NAME", "atualizao_de_solicitao")
CODIGOS_PERMANENTES = {100, 131026, 131047, 131049, 131051, 132000, 132001, 132005, 132007, 132012}
BR_TZ = timezone(timedelta(hours=-3))


def _now():
    return datetime.now(timezone.utc)


def _ts(raw):
    if not raw:
        return None
    try:
        dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _mask(wa_id):
    s = str(wa_id or "")
    return s[:4] + "*" * max(0, len(s) - 6) + s[-2:] if len(s) > 6 else "***"


def _mask_conv(conv_id):
    """conversation_id = "{channel_id}__{wa_id}" -> mascara o wa_id."""
    s = str(conv_id or "")
    if "__" not in s:
        return _mask(s)
    ch, wa = s.split("__", 1)
    return f"{ch}__{_mask(wa)}"


def _val_sent_link(contact_id, conv_id, needle, limit=40):
    """True se, entre as ultimas `limit` mensagens da thread, alguma resposta do
    bot (outbound sem operador, fora o proprio template de lote) contem `needle`.
    Mesma forma de query (contact_id + conversation_id + timestamp_wa desc) que o
    CRM ja usa ao abrir a conversa."""
    if not needle:
        return False
    needle = needle.lower()
    q = (collection("wa_messages")
         .where("contact_id", "==", contact_id)
         .where("conversation_id", "==", conv_id)
         .order_by("timestamp_wa", direction=_fs.Query.DESCENDING)
         .limit(limit))
    for snap in q.stream():
        m = snap.to_dict() or {}
        if m.get("direction") != "outbound" or m.get("sender_user_id") is not None:
            continue
        content = str(m.get("content") or "")
        if m.get("msg_type") == "template" or content.startswith("[Reabertura"):
            continue
        if needle in content.lower():
            return True
    return False


def _first_name(contact):
    name = (
        str(contact.get("whatsapp_profile_name") or "").strip()
        or str(contact.get("declared_name") or "").strip()
        or str(contact.get("display_name") or "").strip()
    )
    return name.split()[0] if name else "cliente"


def _last_conv_date(conv, contact):
    raw = (conv or {}).get("last_message_at") or contact.get("last_message_at") or contact.get("last_inbound_at")
    dt = _ts(raw) or _now()
    return dt.astimezone(BR_TZ).strftime("%d/%m/%Y")


def _norm(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()


def _shape_ok(tpl):
    texts = [_norm(b.get("text")) for c in (tpl.get("components") or [])
             if str(c.get("type", "")).upper() == "BUTTONS" for b in (c.get("buttons") or [])]
    return (any(("retom" in t) or ("continu" in t) for t in texts) and any("encerr" in t for t in texts))


def _template_params(tpl, nome, data):
    body = next((c for c in (tpl.get("components") or []) if str(c.get("type", "")).upper() == "BODY"), None) or {}
    n = len(set(re.findall(r"\{\{(\d+)\}\}", str(body.get("text") or ""))))
    rows = ((body.get("example") or {}).get("body_text") or [])
    examples = rows[0] if rows else []
    date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
    params = []
    for i in range(n):
        ex = str(examples[i]).strip() if i < len(examples) else ""
        if date_re.match(ex):
            params.append({"type": "text", "text": data})
        else:
            params.append({"type": "text", "text": nome if i == 0 else data})
    return params


def _load_templates(channel):
    token, _pid, api_base = get_send_credentials(channel["id"])
    waba = str(channel.get("waba_id") or "").strip()
    if not waba:
        raise SystemExit(f"canal {channel['id']} sem waba_id")
    out, url = [], f"{api_base}/{waba}/message_templates"
    params = {"fields": "name,language,category,status,components,id", "limit": 100}
    with httpx.Client(timeout=20.0) as c:
        while url:
            r = c.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            j = r.json() or {}
            out.extend(j.get("data") or [])
            url = ((j.get("paging") or {}).get("next")) or None
            params = None
    return out


def _resolve_template(channel):
    tpls = [t for t in _load_templates(channel) if str(t.get("status") or "").upper() == "APPROVED"]
    named = next((t for t in tpls if t.get("name") == REOPEN_TEMPLATE_NAME and _shape_ok(t)), None)
    if named:
        return named
    cands = [t for t in tpls if _shape_ok(t) and str(t.get("category") or "").upper() == "UTILITY"]
    return (next((t for t in cands if str(t.get("language") or "").lower().startswith("pt")), None)
            or (cands[0] if cands else None))


def _daily_cap_used(tenant_id):
    """Teto diario do portfolio: a MESMA soma do disparo do CRM
    (database.reopen_daily_usage — tenants ativos, ultimas 24h,
    max(enviados, planejados) para lote em execucao)."""
    uso = reopen_daily_usage(include_tenant_ids=(tenant_id,))
    return int(uso.get("usados") or 0), dict(uso.get("por_tenant") or {})


def _bot_available(tenant_id):
    """Bot disponivel = system_settings.bot_enabled + settings.ai.bot_engine=dialogflow_cx ativo."""
    ss = (document("system_settings", "chat").get().to_dict() or {})
    if not ss.get("bot_enabled"):
        return False, "system_settings.bot_enabled desligado"
    tdoc = (get_firestore_client().collection(collection_name("tenants")).document(tenant_id).get().to_dict() or {})
    ai = ((tdoc.get("settings") or {}).get("ai") or {})
    engine = str(ai.get("bot_engine") or "").strip().lower()
    status = str(ai.get("status") or "active").strip().lower()
    if engine != "dialogflow_cx":
        return False, f"motor {engine or 'builtin'} nao tem fase de bot pos-consentimento"
    if status != "active":
        return False, f"motor CX com status={status}"
    return True, ""


def _select(tenant_id, args):
    now = _now()
    cold_cut = now - timedelta(hours=args.min_cold_hours)
    cooldown_cut = now - timedelta(hours=REOPEN_COOLDOWN_HOURS)
    max_age_cut = (now - timedelta(days=args.max_age_days)) if args.max_age_days else None
    only = set(x.strip() for x in (args.only or "").split(",") if x.strip())
    skips = Counter()
    plano = []
    canais, tpls = {}, {}

    def skip(m):
        skips[m] += 1

    q = collection("wa_contacts").where("qualification", "in", ["em_atendimento", "novo"])
    for snap in q.stream():
        c = snap.to_dict() or {}
        c.setdefault("id", int(snap.id) if str(snap.id).isdigit() else snap.id)
        wa_id = str(c.get("wa_id") or "")
        if only and wa_id not in only:
            continue
        if int(c.get("is_archived") or 0) or c.get("is_backup"):
            skip("arquivado_ou_backup"); continue
        if c.get("lgpd_revoked"):
            skip("lgpd_revogado"); continue
        if c.get("lgpd_consent") is not True:
            skip("consentimento_ausente"); continue
        if c.get("reopen_opt_out"):
            skip("opt_out"); continue
        if c.get("assigned_to") or c.get("bot_completed"):
            skip("fora_da_fase_de_bot"); continue
        li = _ts(c.get("last_inbound_at"))
        if li is None:
            skip("janela_desconhecida"); continue
        if li > cold_cut:
            skip("janela_aberta"); continue
        if max_age_cut is not None and li < max_age_cut:
            skip("mais_antigo_que_max_age"); continue
        lrt = _ts(c.get("last_reopen_template_at"))
        if lrt is not None and lrt > cooldown_cut:
            skip("cooldown"); continue
        if int(c.get("reopen_attempts") or 0) >= 1 or c.get("reopen_resolved_at"):
            skip("tentativa_pendente_ou_resolvido"); continue
        # Teto por contato: leitura unificada do CRM (reopen_batch_sent_at +
        # legado reopen_bot_sent_at, dedup pelo instante, janela >= now - N dias).
        sent = reopen_batch_sends(c, window_days=REOPEN_WINDOW_DAYS, now=now)
        if len(sent) >= REOPEN_MAX_PER_CONTACT:
            skip("teto_bot_contato"); continue
        ch_id = c.get("channel_id")
        if ch_id is None:
            skip("canal_invalido"); continue
        if ch_id not in canais:
            canais[ch_id] = get_channel(int(ch_id)) or {}
        ch = canais[ch_id]
        if (not ch or not ch.get("is_active") or ch.get("channel_type") != "standard"
                or str(ch.get("tenant_id") or "") != tenant_id):
            skip("canal_invalido"); continue
        # thread candidata: a do canal standard do contato
        conv = None
        for cs in collection("wa_conversations").where("contact_id", "==", c["id"]).stream():
            cd = cs.to_dict() or {}
            if cd.get("is_backup") or cd.get("channel_id") != ch_id:
                continue
            cd["id"] = cs.id
            conv = cd
            break
        if conv is None:
            skip("sem_thread_standard"); continue
        if conv.get("assigned_to"):
            skip("fora_da_fase_de_bot"); continue
        lho, lo = _ts(conv.get("last_human_outbound_at")), _ts(conv.get("last_outbound_at"))
        if lho is not None and (lo is None or lho >= lo):
            skip("atendimento_humano"); continue
        st = document("bot_states", c["id"]).get().to_dict() or {}
        if st.get("human_active"):
            skip("atendimento_humano"); continue
        if _val_sent_link(c["id"], conv["id"], args.desfecho_link):
            skip("desfecho_bot_link"); continue
        if ch_id not in tpls:
            tpls[ch_id] = _resolve_template(ch)
        if not tpls[ch_id]:
            skip("sem_template"); continue
        plano.append({"c": c, "conv": conv, "ch": ch, "tpl": tpls[ch_id], "li": li})

    ordem = {"em_atendimento": 0, "novo": 1}
    plano.sort(key=lambda p: (ordem.get(p["c"].get("qualification"), 9), -p["li"].timestamp()))
    return plano, skips


def _age_hist(plano):
    now = _now()
    h = Counter()
    for p in plano:
        d = (now - p["li"]).days
        h["<=7d" if d <= 7 else "8-30d" if d <= 30 else "31-90d" if d <= 90 else ">90d"] += 1
    return dict(h)


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["contact_id", "wa_id_mascarado", "qualification", "last_inbound_at",
                                          "conversation_id", "channel_id", "template", "resultado", "detalhe"])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True)
    p.add_argument("--max-sends", type=int, default=100, help="teto desta execucao (nunca acima de 250)")
    p.add_argument("--min-cold-hours", type=int, default=24)
    p.add_argument("--max-age-days", type=int, default=0, help="ignora leads com ultimo inbound mais antigo que N dias (0 = sem limite)")
    p.add_argument("--only", default="", help="wa_ids separados por virgula (canario)")
    p.add_argument("--desfecho-link", default=REOPEN_DESFECHO_LINK,
                   help="trecho do link de agendamento da Val; quem recebeu fica fora (vazio = desliga)")
    p.add_argument("--sleep", type=float, default=1.5)
    p.add_argument("--user-id", type=int, default=None, help="id do operador para auditoria (opcional)")
    p.add_argument("--yes", action="store_true", help="ENVIA (default: dry-run)")
    args = p.parse_args()

    if not os.getenv("FIRESTORE_PROJECT_ID"):
        raise SystemExit("defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente")
    max_sends = max(1, min(args.max_sends, 250))
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    csv_path = ROOT / "logs" / f"reopen_bot_{args.tenant}_{stamp}.csv"

    token_ctx = set_tenant_context(args.tenant)
    try:
        ok, motivo = _bot_available(args.tenant)
        if not ok:
            raise SystemExit(f"publico Bot indisponivel no tenant {args.tenant}: {motivo}")
        used, detalhe = _daily_cap_used(args.tenant)
        disponiveis = max(0, REOPEN_DAILY_CAP - used)
        print(f"teto diario do portfolio: {REOPEN_DAILY_CAP} | usados nas ultimas 24h: {used} {detalhe} | disponiveis: {disponiveis}")
        efetivo = min(max_sends, disponiveis)

        plano, skips = _select(args.tenant, args)
        print(f"\nelegiveis no publico Bot: {len(plano)} | por qualificacao: "
              f"{dict(Counter(p['c'].get('qualification') for p in plano))} | idade do ultimo inbound: {_age_hist(plano)}")
        print(f"fora do lote: {dict(skips)}")
        print(f"envios nesta execucao (min(max_sends={max_sends}, disponiveis={disponiveis})): {min(efetivo, len(plano))}")
        print("\namostra (ate 20):")
        for pl in plano[:20]:
            c = pl["c"]
            print(f"  #{c['id']:>6} {_mask(c.get('wa_id'))} {c.get('qualification'):<15} ultimo inbound {pl['li'].astimezone(BR_TZ):%d/%m %H:%M} "
                  f"template={pl['tpl'].get('name')}")

        rows = [{"contact_id": pl["c"]["id"], "wa_id_mascarado": _mask(pl["c"].get("wa_id")),
                 "qualification": pl["c"].get("qualification"), "last_inbound_at": pl["li"].isoformat(),
                 "conversation_id": _mask_conv(pl["conv"]["id"]), "channel_id": pl["ch"]["id"], "template": pl["tpl"].get("name"),
                 "resultado": "planejado" if i < efetivo else "fora_do_teto", "detalhe": ""}
                for i, pl in enumerate(plano)]
        if not args.yes:
            _write_csv(csv_path, rows)
            print(f"\nDRY-RUN — nada foi enviado. Plano em {csv_path}. Adicione --yes para disparar.")
            return
        if efetivo <= 0 or not plano:
            print("nada a enviar (teto diario esgotado ou sem elegiveis)")
            return

        batch_id = next_sequence("reopen_batches")
        started = _now().isoformat()
        document("reopen_batches", batch_id).set({
            "id": batch_id, "status": "executando", "audience": "bot", "criteria_version": "v2-script-2026-09-23",
            "started_by": args.user_id, "started_at": started, "origem": "scripts/reopen_bot_audience_once.py",
            "planejados": min(efetivo, len(plano)), "auto_resolve_planejados": 0, "max_sends": efetivo,
            "pulados_scan": dict(skips), "enviados": 0, "resolvidos": 0, "falhas": 0, "last_progress_at": started,
        })
        log_audit(args.user_id, "REOPEN_BATCH_START", f"batch={batch_id} audience=bot planejados={min(efetivo, len(plano))} origem=script")
        enviados = falhas = consecutivas = 0
        abortado = ""
        try:
            for i, pl in enumerate(plano[:efetivo]):
                c, conv, ch, tpl = pl["c"], pl["conv"], pl["ch"], pl["tpl"]
                row = rows[i]
                try:
                    token, phone_id, api_base = get_send_credentials(ch["id"])
                    wa_target = "".join(x for x in str(c.get("wa_id") or "") if x.isdigit())
                    params = _template_params(tpl, _first_name(c), _last_conv_date(conv, c))
                    payload = {
                        "messaging_product": "whatsapp", "to": wa_target, "type": "template",
                        "template": {"name": tpl.get("name"), "language": {"code": tpl.get("language") or "pt_BR"},
                                     **({"components": [{"type": "body", "parameters": params}]} if params else {})},
                    }
                    with httpx.Client(timeout=15.0) as client:
                        resp = client.post(f"{api_base}/{phone_id}/messages", json=payload,
                                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                    if resp.status_code == 200:
                        now_iso = _now().isoformat()
                        # Carimbo PRIMEIRO (template pago ja saiu)
                        document("wa_contacts", c["id"]).set({
                            "reopen_attempts": int(c.get("reopen_attempts") or 0) + 1,
                            "last_reopen_template_at": now_iso,
                            "last_reopen_at": now_iso,
                            "last_reopen_audience": "bot",
                            "last_reopen_conversation_id": conv["id"],
                            "last_reopen_channel_id": ch["id"],
                            "reopen_bot_sent_at": _fs.ArrayUnion([now_iso]),
                            "reopen_batch_sent_at": _fs.ArrayUnion([{"at": now_iso, "audience": "bot"}]),
                        }, merge=True)
                        try:
                            body = resp.json()
                        except Exception:
                            body = {}
                        msg0 = (body.get("messages") or [{}])[0]
                        try:
                            save_wa_message(
                                wa_message_id=msg0.get("id", ""), contact_id=c["id"], direction="outbound",
                                msg_type="template", content=f"[Reabertura em lote: {tpl.get('name')}]",
                                status="sent", timestamp_wa=now_iso, operator_id=args.user_id,
                                sender_user_id=args.user_id, channel_id=ch.get("id"),
                                channel_owner_user_id=ch.get("owner_user_id"), conversation_id=conv["id"],
                                template_category=str(tpl.get("category") or "utility").lower(),
                                promote_qualification=False, reopen_attendance=False,
                                advance_recency=False, human_outbound=False,
                            )
                        except Exception as exc:
                            print(f"  aviso: envio ok mas save falhou contato={c['id']}: {exc}")
                        enviados += 1
                        consecutivas = 0
                        # Sem o wamid no relatorio/console: ele carrega o telefone em base64.
                        row["resultado"], row["detalhe"] = "enviado", "ok" if msg0.get("id") else "sem_id"
                        if str(msg0.get("message_status") or "") == "held_for_quality_assessment":
                            abortado = "held_for_quality_assessment"
                            break
                    else:
                        falhas += 1
                        try:
                            err = resp.json().get("error") or {}
                        except Exception:
                            err = {}
                        code = err.get("code")
                        row["resultado"], row["detalhe"] = "falha", f"http={resp.status_code} code={code} {str(err.get('message'))[:80]}"
                        if code in CODIGOS_PERMANENTES:
                            document("wa_contacts", c["id"]).set({"last_reopen_template_at": _now().isoformat()}, merge=True)
                        else:
                            consecutivas += 1
                        if "held_for_quality" in str(err).lower():
                            abortado = "held_for_quality_assessment"
                            break
                except Exception as exc:
                    falhas += 1
                    consecutivas += 1
                    row["resultado"], row["detalhe"] = "excecao", str(exc)[:120]
                    # resultado indeterminado (timeout etc.): cooldown sem tentativa, pra nao duplicar amanha
                    try:
                        document("wa_contacts", c["id"]).set({"last_reopen_template_at": _now().isoformat()}, merge=True)
                    except Exception:
                        pass
                print(f"  [{i + 1}/{efetivo}] #{c['id']} {row['resultado']} {row['detalhe']}")
                if consecutivas >= 5:
                    abortado = "5 falhas consecutivas"
                    break
                if (i + 1) % 10 == 0:
                    document("reopen_batches", batch_id).set(
                        {"enviados": enviados, "falhas": falhas, "last_progress_at": _now().isoformat()}, merge=True)
                time.sleep(args.sleep)
        finally:
            document("reopen_batches", batch_id).set({
                "status": "abortado" if abortado else "concluido", "abort_motivo": abortado,
                "enviados": enviados, "resolvidos": 0, "falhas": falhas, "finished_at": _now().isoformat(),
            }, merge=True)
            log_audit(args.user_id, "REOPEN_BATCH_END",
                      f"batch={batch_id} audience=bot enviados={enviados} falhas={falhas} abort={abortado or '-'} origem=script")
            _write_csv(csv_path, rows)
            print(f"\nlote {batch_id}: enviados={enviados} falhas={falhas} abort={abortado or '-'} | relatorio em {csv_path}")
    finally:
        reset_tenant_context(token_ctx)


if __name__ == "__main__":
    main()
