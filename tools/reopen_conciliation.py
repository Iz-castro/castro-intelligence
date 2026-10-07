# -*- coding: utf-8 -*-
"""
Conciliacao da reabertura em lote — classificacao v1 x v2.2 (SO LEITURA).

Plano: docs/PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md, secao 11.1 (criterio de
liberacao por tenant). Para UM tenant, roda lado a lado:
  - v1: database.scan_reopen_candidates (a classificacao antiga do lote C2);
  - v2: database.scan_reopen_audiences (scan unico com dois publicos);
e imprime a identidade, parcela por parcela, com o residuo:

  Recepcao_v2 = Recepcao_v1 - (consentimento_ausente + politica_desatualizada
                + fase_bot + teto_contato + mais_antigo_que_limite
                + sem_thread_standard + aguardando_bot)
                + novo_pos_handoff_elegivel

Cada contato de Recepcao_v1 que sai da Recepcao na v2 e atribuido ao motivo
que a v2 deu NA VISAO RECEPCAO; cada contato que entra na v2 sem estar na v1
precisa ser "novo" com bot_completed (pos-handoff). O que sobra e residuo:
qualquer residuo e bug de classificacao. O residuo e detalhado em
  - "novo em atendimento humano": novo SEM bot_completed que a v2 poe na
    Recepcao pelos criterios 2.2.2-2.2.4 (dono, human_active ou resposta
    humana apos o marco) — fora da formula do plano, listado para conferencia;
  - "inexplicado": todo o resto (o que realmente indica bug).

Comparacao no nivel do SCAN, antes do filtro de template: todo canal standard
ativo conta como tendo template (sem_template nao entra na identidade e nenhum
Graph/Meta e chamado). Os dois scans usam o MESMO relogio. Sem corte
REOPEN_SCAN_MAX por padrao (o corte so limitaria a v2); --scan-max aplica.

SO LEITURA, sem dry-run a escolher: o script trava set/update/delete/create/
add/commit do cliente Firestore antes de ler qualquer coisa — uma escrita
acidental vira RuntimeError. Nao envia nada, nao grava relatorio. Saida sem
telefone/nome (so contact_id, com --ids).

Uso (PowerShell, raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe tools/reopen_conciliation.py --tenant varizemed
  ./.venv/Scripts/python.exe tools/reopen_conciliation.py --tenant hubloc --ids

Exit 0 = sem residuo inexplicado; 1 = residuo inexplicado (bug); 2 = uso.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Parcelas que a formula 11.1 subtrai de Recepcao_v1 (motivo da v2 na visao Recepcao).
PARCELAS = (
    "consentimento_ausente", "politica_desatualizada", "fase_bot", "teto_contato",
    "mais_antigo_que_limite", "sem_thread_standard", "aguardando_bot",
)


def trava_escrita():
    """Torna o cliente Firestore so-leitura NESTE processo."""
    from google.cloud.firestore_v1 import batch, collection, document, transaction

    def _bloqueado(*_a, **_k):
        raise RuntimeError("reopen_conciliation e so-leitura: escrita no Firestore bloqueada")

    for cls, nomes in (
        (document.DocumentReference, ("set", "update", "delete", "create")),
        (collection.CollectionReference, ("add",)),
        (batch.WriteBatch, ("commit",)),
        (transaction.Transaction, ("commit",)),
    ):
        for nome in nomes:
            setattr(cls, nome, _bloqueado)


def classificar(channels_ok, cx_ok, policy_date, now=None, scan_max=None):
    """Roda v1 e v2 com o MESMO relogio (o tenant ja vem no contexto).
    Devolve (v1, v2). So leitura."""
    import database_firestore as dbf
    from config import (
        REOPEN_COOLDOWN_HOURS, REOPEN_DESFECHO_LINK, REOPEN_MAX_ATTEMPTS,
        REOPEN_MAX_IDLE_DAYS, REOPEN_MAX_PER_CONTACT, REOPEN_WINDOW_DAYS,
    )
    now = now or datetime.now(timezone.utc)
    # A v1 le utcnow() do modulo; fixa o relogio dela no mesmo instante da v2.
    real_utcnow = dbf.utcnow
    dbf.utcnow = lambda: now
    try:
        v1 = dbf.scan_reopen_candidates(
            max_attempts=REOPEN_MAX_ATTEMPTS, cooldown_hours=REOPEN_COOLDOWN_HOURS,
            window_hours=24,
        )
    finally:
        dbf.utcnow = real_utcnow
    v2 = dbf.scan_reopen_audiences(
        channels_ok, cx_ok, policy_date,
        max_attempts=REOPEN_MAX_ATTEMPTS, cooldown_hours=REOPEN_COOLDOWN_HOURS,
        window_hours=24, max_per_contact=REOPEN_MAX_PER_CONTACT,
        window_days=REOPEN_WINDOW_DAYS, max_idle_days=REOPEN_MAX_IDLE_DAYS,
        scan_max=scan_max, desfecho_link=REOPEN_DESFECHO_LINK, now=now,
        with_detail=True,
    )
    return v1, v2


def conciliar(v1, v2):
    """Identidade 11.1 a partir dos dois scans (funcao pura)."""
    det = v2.get("detalhe") or {}
    r1 = {c.get("id") for c in v1.get("enviaveis") or []}
    r2 = {cid for cid, d in det.items() if d.get("reception") == "enviavel"}
    parcelas = {p: [] for p in PARCELAS}
    saida_inexplicada = {}
    for cid in sorted(r1 - r2, key=str):
        motivo = (det.get(cid) or {}).get("reception") or "ausente_na_v2"
        if motivo in parcelas:
            parcelas[motivo].append(cid)
        else:
            saida_inexplicada.setdefault(motivo, []).append(cid)
    novo_pos_handoff, novo_humano, entrada_inexplicada = [], {}, {}
    for cid in sorted(r2 - r1, key=str):
        d = det.get(cid) or {}
        if d.get("qualification") == "novo" and d.get("bot_completed"):
            novo_pos_handoff.append(cid)
        elif d.get("qualification") == "novo":
            novo_humano.setdefault(d.get("via") or "?", []).append(cid)
        else:
            tipo = f"{d.get('qualification')}/{d.get('via') or '?'}"
            entrada_inexplicada.setdefault(tipo, []).append(cid)
    n1, n2 = len(r1), len(r2)
    esperado = n1 - sum(len(v) for v in parcelas.values()) + len(novo_pos_handoff)
    n_humano = sum(len(v) for v in novo_humano.values())
    n_inexplicado = (sum(len(v) for v in saida_inexplicada.values())
                     + sum(len(v) for v in entrada_inexplicada.values()))
    return {
        "recepcao_v1": n1, "recepcao_v2": n2,
        "parcelas": parcelas, "novo_pos_handoff_elegivel": novo_pos_handoff,
        "esperado": esperado, "residuo": n2 - esperado,
        "novo_em_atendimento_humano": novo_humano,
        "saida_inexplicada": saida_inexplicada,
        "entrada_inexplicada": entrada_inexplicada,
        "residuo_inexplicado": n_inexplicado,
        "residuo_novo_humano": n_humano,
    }


def _linha(rotulo, valor, ids=None, mostrar_ids=False):
    print(f"  {rotulo:<44} {valor:>7}")
    if mostrar_ids and ids:
        print(f"      ids: {', '.join(str(i) for i in ids)}")


def imprimir(tenant, now, ctx, v1, v2, conc, mostrar_ids=False):
    rec, bot = v2["audiences"]["reception"], v2["audiences"]["bot"]
    print(f"Conciliacao da reabertura em lote — tenant {tenant} — {now.isoformat()} (so leitura)")
    print(f"Motor CX: {'ativo' if ctx['cx_ok'] else 'indisponivel (' + ctx['cx_motivo'] + ')'}"
          f" | data da politica LGPD: {ctx['policy_date'] or 'sem data'}"
          f" | canais standard ativos: {sorted(ctx['canais'], key=str) or 'nenhum'}")
    print(f"v1 (scan_reopen_candidates): enviaveis={len(v1['enviaveis'])} "
          f"auto_resolve={len(v1['auto_resolve'])} pulados={dict(v1['pulados'])}")
    print(f"v2 ({v2['criteria_version']}): varridos={v2['total']} sobreviventes={v2.get('sobreviventes')} "
          f"| Recepcao enviaveis={len(rec['enviaveis'])} auto_resolve={len(rec['auto_resolve'])} "
          f"| Bot enviaveis={len(bot['enviaveis'])} auto_resolve={len(bot['auto_resolve'])}")
    print(f"   pulados (visao Recepcao): {dict(sorted(rec['pulados'].items()))}")
    print(f"   pulados (visao Bot):      {dict(sorted(bot['pulados'].items()))}")
    print(f"   leituras da v2: {v2['leituras']} | corte REOPEN_SCAN_MAX={ctx['scan_max_cfg']}: "
          f"excedente seria {max(0, int(v2.get('sobreviventes') or 0) - ctx['scan_max_cfg'])}")
    print("\nIdentidade (plano 11.1):")
    _linha("Recepcao_v1", conc["recepcao_v1"])
    for p in PARCELAS:
        _linha(f"- {p}", len(conc["parcelas"][p]), conc["parcelas"][p], mostrar_ids)
    _linha("+ novo_pos_handoff_elegivel", len(conc["novo_pos_handoff_elegivel"]),
           conc["novo_pos_handoff_elegivel"], mostrar_ids)
    _linha("= Recepcao_v2 esperado", conc["esperado"])
    _linha("Recepcao_v2 observado", conc["recepcao_v2"])
    _linha("residuo (observado - esperado)", conc["residuo"])
    if conc["residuo_novo_humano"]:
        print("\n  Residuo de 'novo em atendimento humano' (Recepcao pelos criterios 2.2.2-2.2.4,"
              " fora da formula — conferir):")
        for via, ids in sorted(conc["novo_em_atendimento_humano"].items()):
            _linha(f"  via {via}", len(ids), ids, mostrar_ids)
    if conc["residuo_inexplicado"]:
        print("\n  Residuo INEXPLICADO:")
        for motivo, ids in sorted(conc["saida_inexplicada"].items()):
            _linha(f"  saiu da Recepcao por {motivo}", len(ids), ids, mostrar_ids)
        for tipo, ids in sorted(conc["entrada_inexplicada"].items()):
            _linha(f"  entrou na Recepcao ({tipo})", len(ids), ids, mostrar_ids)
    v1_ar = {c.get("id") for c in v1["auto_resolve"]}
    v2_ar = {c.get("id") for c in rec["auto_resolve"]} | {c.get("id") for c in bot["auto_resolve"]}
    det = v2.get("detalhe") or {}
    fora = Counter((det.get(cid) or {}).get("reception") for cid in v1_ar - v2_ar)
    print(f"\nAuto-resolve (informativo): v1={len(v1_ar)} | v2 Recepcao={len(rec['auto_resolve'])} "
          f"Bot={len(bot['auto_resolve'])} | da v1 fora da v2: {dict(fora)}")
    if conc["residuo_inexplicado"]:
        print("\nRESULTADO: ATENCAO — residuo inexplicado (bug de classificacao).")
    elif conc["residuo"]:
        print("\nRESULTADO: OK pela formula com ressalva — residuo so de 'novo em atendimento humano'.")
    else:
        print("\nRESULTADO: OK — residuo zero.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True)
    p.add_argument("--ids", action="store_true", help="lista os contact_id de cada parcela/residuo")
    p.add_argument("--scan-max", type=int, default=0,
                   help="aplica o corte de candidatos da v2 (0 = sem corte, padrao)")
    args = p.parse_args(argv)
    if not os.getenv("FIRESTORE_PROJECT_ID"):
        print("defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente")
        return 2

    trava_escrita()
    from bot_service import _get_tenant_ai_config, _lgpd_policy_date
    from channel_service import get_all_active_channels
    from config import REOPEN_SCAN_MAX
    from database_firestore import get_system_settings, reopen_bot_engine_status
    from firestore_common import reset_tenant_context, set_tenant_context
    from tenant_service import get_tenant

    if not get_tenant(args.tenant):
        print(f"tenant {args.tenant} nao encontrado")
        return 2
    now = datetime.now(timezone.utc)
    token = set_tenant_context(args.tenant)
    try:
        sys_settings = get_system_settings()
        cx_ok, cx_motivo = reopen_bot_engine_status(sys_settings, _get_tenant_ai_config())
        policy_date = _lgpd_policy_date(sys_settings)
        canais = [ch.get("id") for ch in get_all_active_channels()
                  if ch.get("is_active") and ch.get("channel_type") == "standard"
                  and ch.get("id") is not None]
        v1, v2 = classificar({ch: True for ch in canais}, cx_ok, policy_date, now=now,
                             scan_max=args.scan_max or None)
    finally:
        reset_tenant_context(token)
    conc = conciliar(v1, v2)
    ctx = {"cx_ok": cx_ok, "cx_motivo": cx_motivo, "canais": canais,
           "policy_date": policy_date.isoformat() if policy_date else "",
           "scan_max_cfg": REOPEN_SCAN_MAX}
    imprimir(args.tenant, now, ctx, v1, v2, conc, mostrar_ids=args.ids)
    return 1 if conc["residuo_inexplicado"] else 0


if __name__ == "__main__":
    sys.exit(main())
