# -*- coding: utf-8 -*-

"""
Simulador LOCAL do Monitor de atendimento (monitor_service.py, PO 2026-10-13).

NAO toca em producao: exercita o codigo REAL de monitor_service.py, das
leituras monitor_* de database_firestore.py e das rotas /api/admin/monitor/*
de main.py, com o Firestore substituido por um stub em memoria. Os cenarios
da fila reproduzem, em campos estruturados (handoff_at /
last_human_outbound_at), os casos A-I do modo demo do painel do Izael.

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\sim_monitor_flow.py

Sai com codigo 0 se todos os asserts passarem, 1 caso contrario.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
import database_firestore as dbf  # noqa: E402
import monitor_service as ms  # noqa: E402
import rbac  # noqa: E402
import tenant_service  # noqa: E402

FAILS = []
CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"      ✓ {label}")
    else:
        FAILS.append(label)
        print(f"      ✗ FALHOU: {label}")


def titulo(txt):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


# =========================================================================
# Firestore em memoria (where ==/>=/<, order_by, select, limit)
# =========================================================================

STORE = {}


class _Snap:
    def __init__(self, coll, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, coll, doc_id):
        self.coll = coll
        self.doc_id = str(doc_id)

    def get(self):
        READS.append((self.coll, self.doc_id))
        return _Snap(self.coll, self.doc_id, STORE.get(self.coll, {}).get(self.doc_id))

    def set(self, data, merge=False):
        raise AssertionError(f"monitor nao pode escrever: {self.coll}/{self.doc_id}")


def _match(value, op, ref):
    if op == "==":
        return value == ref
    if value is None:
        return False
    try:
        return {">=": value >= ref, "<": value < ref, "<=": value <= ref}[op]
    except TypeError:
        return False


class _Query:
    def __init__(self, coll):
        self.coll = coll
        self._filters = []
        self._order = None
        self._limit = None
        self._select = None

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def order_by(self, field, direction="ASCENDING"):
        self._order = (field, str(direction).upper().startswith("DESC"))
        return self

    def select(self, fields):
        self._select = list(fields)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        QUERIES.append((self.coll, tuple(self._filters)))
        rows = [(i, d) for i, d in STORE.get(self.coll, {}).items()
                if all(_match(d.get(f), op, v) for (f, op, v) in self._filters)]
        if self._order:
            campo, desc = self._order
            rows.sort(key=lambda kv: kv[1].get(campo), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        for i, d in rows:
            if self._select is not None:
                d = {k: d.get(k) for k in self._select if k in d}
            yield _Snap(self.coll, i, d)


QUERIES = []
READS = []
dbf.document = lambda name, doc_id: _DocRef(name, doc_id)
dbf.collection = lambda name: _Query(name)
rbac.get_perfil_toggles = lambda tenant_id, perfil_id: None   # sem doc: vale o seed da role
tenant_service.get_tenant = lambda tid: {"name": tid, "plan": "professional"}
AUDITS = []
main.log_audit = lambda uid, action, detail="", ip="": AUDITS.append((uid, action, detail))

BR = timezone(timedelta(hours=-3))
# 2026-09-28 = segunda. Hubloc abre 8h-17h (business_hours).
SEG_10H = datetime(2026, 9, 28, 10, 0, tzinfo=BR).astimezone(timezone.utc)
CFG = ms.monitor_config("hubloc")


def base_store():
    STORE.clear()
    STORE["departments"] = {
        "2": {"name": "Comercial", "bot_key": "comercial", "is_active": 1},
        "4": {"name": "Financeiro", "bot_key": "financeiro", "is_active": 1},
    }
    STORE["users"] = {
        "1": {"display_name": "Gerente", "role": "admin", "is_active": 1, "email": "g@hubloc.com.br", "username": "g@hubloc.com.br"},
        "4": {"display_name": "Danielle", "role": "operador", "is_active": 1, "email": "d@hubloc.com.br", "username": "d@hubloc.com.br"},
        "5": {"display_name": "Aline", "role": "operador", "is_active": 1, "email": "a@hubloc.com.br", "username": "a@hubloc.com.br"},
    }
    STORE["wa_conversations"] = {}
    STORE["wa_contacts"] = {}
    STORE["wa_messages"] = {}


def lead(cid, minutos, *, dept=2, dono=None, humano_min=None, contato=None, thread=None,
         canal=4, now=SEG_10H):
    """Contato que passou pelo bot (handoff ha `minutos`) + a thread dele."""
    h = now - timedelta(minutes=minutos)
    c = {"bot_completed": True, "assigned_to": dono, "department_id": dept,
         "qualification": None, "is_archived": 0, "attendance_protocol": f"20260928-{cid}-COM"}
    c.update(contato or {})
    STORE["wa_contacts"][str(cid)] = c
    t = {"id": f"{canal}__55319{cid:07d}", "contact_id": cid, "channel_id": canal,
         "department_id": dept, "assigned_to": dono, "attendance_status": "aberto",
         "is_backup": False, "handoff_at": h, "last_inbound_at": h - timedelta(seconds=30),
         "last_human_outbound_at": (now - timedelta(minutes=humano_min)) if humano_min is not None else None}
    t.update(thread or {})
    STORE["wa_conversations"][t["id"]] = t
    return t


def msg(mid, conv, contato, direcao, texto, quando, *, op=None, tipo="text", status="read",
        protocolo=None, canal=4):
    STORE["wa_messages"][str(mid)] = {
        "contact_id": contato, "conversation_id": conv, "direction": direcao, "msg_type": tipo,
        "status": status, "content": texto, "sender_user_id": op, "operator_id": op,
        "channel_id": canal, "protocol_id": protocolo, "created_at": quando, "timestamp_wa": quando,
    }


# =========================================================================
# Cenarios
# =========================================================================

def cenario_config_e_texto():
    titulo("CENARIO 1 — config por tenant, gate LGPD, PII e origem")
    check(CFG is not None and CFG["fila_minutos"] == 5, "hubloc tem monitor (fila 5 min)")
    check(ms.monitor_config("varizemed") is None, "varizemed NAO tem monitor (conversa de paciente)")
    check(all(ms.eh_resposta_lgpd(t) for t in ("Sim!", "lgpd_aceitar", "Não", "lgpd_recusar", "aceito os termos")),
          "respostas do aceite reconhecidas pelo vocabulario do lgpd_bot")
    check(not ms.eh_resposta_lgpd("quero uma betoneira"), "fala real do cliente nao e resposta LGPD")
    red = ms.redigir_pii("liga (31) 98344-0484 ou 31983440484, cpf 123.456.789-00, "
                         "cnpj 12.345.678/0001-90, mail joao.silva@empresa.com.br")
    check("98344" not in red and "83440484" not in red, "telefone formatado e corrido redigidos")
    check("123.456" not in red and "0001-90" not in red and red.count("[documento]") == 2,
          "CPF e CNPJ formatados redigidos")
    check("@" not in red and "[email]" in red, "e-mail redigido")
    co = lambda t: ms.classificar_origem(t, CFG)[0]  # noqa: E731
    check(co("Olá! Vim pelo site da Hub Loc e quero um orçamento de betoneira.") == "site",
          "marcador do site -> Site")
    check(co("Pedido de orçamento pelo site da Hub Loc: andaime") == "site", "2o marcador do site -> Site")
    check(co("Olá, quero alugar uma ferramenta!") == "meta", "template da Meta (igual, sem pontuacao) -> Meta")
    check(co("Olá, quero alugar uma ferramenta! Tem martelete?") == "indeterminada",
          "template + texto extra -> Indeterminada (regra ao pe da letra)")
    check(co("Bom dia") == "indeterminada", "texto livre -> Indeterminada")

    fila = ms._eh_entrada_na_fila
    check(fila({"direction": "system",
                "content": "Bot finalizado | Bot: Setor=Comercial | Encaminhado para Comercial"}),
          "handoff do bot simples conta como entrada na fila")
    check(fila({"direction": "system",
                "content": "Bot IA finalizado | Transferido para atendimento humano\nNome: Joao\nResumo: quer betoneira"}),
          "handoff do agente de IA (Hugo) conta como entrada na fila")
    check(not fila({"direction": "system",
                    "content": "Resumo do bot IA | Atendimento assumido durante a conversa\nResumo: x"}),
          "assumir durante a conversa do agente nao e entrada na fila")
    check(not fila({"direction": "inbound",
                    "content": "Bot IA finalizado | Transferido para atendimento humano"}),
          "so mensagem de sistema conta como entrada na fila")


def cenario_fila():
    titulo("CENARIO 2 — fila de espera (casos A-I do painel + extras), segunda 10h")
    base_store()
    a = lead(901, 7)                                     # A: 7 min na fila
    b = lead(902, 18)                                    # B: 18 min, cliente insistiu
    msg(1, b["id"], 902, "inbound", "Olá, quero alugar uma ferramenta!", SEG_10H - timedelta(minutes=19))
    msg(2, b["id"], 902, "inbound", "lgpd_aceitar", SEG_10H - timedelta(minutes=18, seconds=5))
    msg(3, b["id"], 902, "inbound", "alguem ai? me liga 31 98344-0484", SEG_10H - timedelta(minutes=12),
        protocolo="20260928-902-COM")
    msg(4, b["id"], 902, "inbound", "?", SEG_10H - timedelta(minutes=9))
    lead(903, 40, dono=5)                                # C: assumida pela Aline sem responder
    STORE["wa_contacts"]["904"] = {"bot_completed": False}   # D: parado no aceite (sem handoff)
    STORE["wa_conversations"]["4__553190000904"] = {"id": "4__553190000904", "contact_id": 904,
                                                    "handoff_at": None, "attendance_status": "aberto"}
    lead(905, 30, dono=4, humano_min=10)                 # E: respondida ha 10 min
    lead(906, 12, dept=4)                                # F: fila do Financeiro
    lead(907, 3)                                         # G: 3 min, abaixo do limite
    lead(908, 9)                                         # H: cliente antigo (consentimento ja dado)
    i = lead(909, 22)                                    # I: respondida pelo numero pessoal (coex)
    STORE["wa_conversations"]["3__553190000909"] = {
        **i, "id": "3__553190000909", "channel_id": 3, "assigned_to": 4,
        "last_human_outbound_at": SEG_10H - timedelta(minutes=15)}
    lead(910, 20, contato={"qualification": "nao_qualificado"})       # J
    lead(911, 20, thread={"attendance_status": "fechado_manual"})     # K
    lead(912, 20, contato={"lgpd_revoked": True})                     # L
    lead(913, 20, thread={"is_backup": True})                          # M
    lead(914, 20, humano_min=60 * 30)                    # N: resposta humana de ciclo ANTERIOR
    seg_0730 = datetime(2026, 9, 28, 7, 30, tzinfo=BR).astimezone(timezone.utc)
    lead(915, 150, thread={"handoff_at": seg_0730})      # O: chegou 7h30 (antes de abrir)
    lead(916, 60 * 80)                                   # P: handoff fora da janela de 72h

    QUERIES.clear()
    READS.clear()
    r = ms.fila_de_espera("hubloc", CFG, now=SEG_10H)
    al = {x["contato"]: x for x in r["alertas"]}
    check(r["dentro_do_expediente"] is True and r["limite_min"] == 5, "expediente aberto, limite 5 min")
    check(set(al) == {901, 902, 903, 908, 914, 915},
          f"alarma A, B, C, H, N e O e mais nada (veio {sorted(al)})")
    check(int(al[901]["minutos"]) == 7 and al[901]["fila"] == "Comercial", "A: 7 min na fila do Comercial")
    check(al[902]["mensagens_apos_fila"] == 2, "B: 2 mensagens do cliente depois do handoff (sem o aceite)")
    check(al[902]["previa"] == "?", "B: previa e a ultima fala do cliente")
    check(al[903]["responsavel"] == "Aline", "C: mostra quem assumiu sem responder")
    check(904 not in al, "D: parado no aceite nao alarma")
    check(905 not in al, "E: respondida pela pessoa nao alarma")
    check(906 not in al, "F: fila de outro setor nao alarma")
    check(907 not in al, "G: abaixo de 5 min nao alarma")
    check(909 not in al, "I: resposta pelo numero pessoal (coex) para o relogio")
    check(not ({910, 911, 912, 913} & set(al)), "nao qualificado, fechado, LGPD revogada e backup ficam fora")
    check(914 in al, "N: resposta humana de ciclo anterior nao conta")
    check(al[915]["desde"] == "08:00" and int(al[915]["minutos"]) == 120,
          "O: lead das 7h30 conta da abertura (8h) -> 120 min as 10h")
    check(916 not in al, "P: handoff de mais de 72h fica fora")
    check([x["contato"] for x in r["alertas"]][0] == 915, "ordenado do mais antigo para o mais novo")
    lidas = [q for q in QUERIES if q[0] == "wa_messages"]
    check(len(lidas) == len(al), "le mensagens SO das threads em alerta (1 consulta por alerta)")
    check(not any(q[0] == "wa_conversations" and not q[1] for q in QUERIES),
          "nunca faz full-scan de wa_conversations")
    lidos = sorted(int(i) for c, i in READS if c == "wa_contacts")
    check(lidos == [901, 902, 903, 908, 910, 912, 914, 915],
          f"cadastro lido SO de quem passou nos criterios da thread (veio {lidos})")

    sab = datetime(2026, 9, 26, 10, 0, tzinfo=BR).astimezone(timezone.utc)
    ms._cache.clear()
    r2 = ms.fila_de_espera("hubloc", CFG, now=sab)
    check(r2["dentro_do_expediente"] is False and r2["alertas"] == [], "sabado: alarme em pausa, lista vazia")

    ms._cache.clear()
    msg(5, a["id"], 901, "outbound", "Bom dia! Sou a Danielle", SEG_10H, op=4)  # mensagem nao muda a thread
    STORE["wa_conversations"][a["id"]]["last_human_outbound_at"] = SEG_10H
    r3 = ms.fila_de_espera("hubloc", CFG, now=SEG_10H + timedelta(seconds=30))
    check(901 not in {x["contato"] for x in r3["alertas"]}, "A sai da fila quando a Danielle responde")


def cenario_metricas():
    titulo("CENARIO 3 — metricas, palavras mais citadas e origem")
    t0 = datetime(2026, 9, 28, 9, 0, tzinfo=BR).astimezone(timezone.utc)
    m = []

    def add(conv, cid, dire, txt, minutos, op=None, tipo="text", prot=None, canal=4, status="read",
            aconteceu_dias_antes=0):
        gravada = t0 + timedelta(minutes=minutos)
        m.append({"conversation_id": conv, "contact_id": cid, "direction": dire, "msg_type": tipo,
                  "status": status, "content": txt, "sender_user_id": op, "operator_id": op,
                  "channel_id": canal, "protocol_id": prot, "created_at": gravada,
                  "timestamp_wa": gravada - timedelta(days=aconteceu_dias_antes, seconds=2)})

    # conv A (site): cliente 1, Danielle responde em 5 e depois em 20 min
    add("4__a", 1, "inbound", "Olá! Vim pelo site da Hub Loc e quero orçamento de betoneira", 0, prot="20260928-1-COM")
    add("4__a", 1, "inbound", "lgpd_aceitar", 1, prot="20260928-1-COM")
    add("4__a", 1, "system", "Bot finalizado | Bot: Setor=Comercial | Encaminhado para Comercial", 1, tipo="system",
        prot="20260928-1-COM")
    add("4__a", 1, "outbound", "posso ajudar", 5, op=4, prot="20260928-1-COM")
    add("4__a", 1, "inbound", "qual o valor da diaria do compactador", 10, prot="20260928-1-COM")
    add("4__a", 1, "outbound", "R$ 90", 30, op=4, prot="20260928-1-COM")
    add("4__a", 1, "inbound", "👍", 31, tipo="reaction", prot="20260928-1-COM")
    add("4__a", 1, "outbound", "falhou", 32, op=4, status="failed", prot="20260928-1-COM")
    # conv B (meta): cliente 2, Aline responde em 10 min
    add("4__b", 2, "inbound", "Olá, quero alugar uma ferramenta!", 60, prot="20260928-2-COM")
    add("4__b", 2, "inbound", "tem betoneira e compactador?", 61, prot="20260928-2-COM")
    add("4__b", 2, "outbound", "temos", 71, op=5, prot="20260928-2-COM")
    add("4__b", 2, "inbound", "valeu Aline, tem andaime tambem?", 72, prot="20260928-2-COM")
    add("4__b", 2, "outbound", "tem sim", 73, op=5, prot="20260928-2-COM")
    # conv C (indeterminada): cliente 3, so o bot respondeu
    add("4__c", 3, "inbound", "preciso de betoneira pra semana que vem", 90, prot="20260928-3-COM")
    add("4__c", 3, "outbound", "Olá! Que bom ter você na Hub Loc! Podemos continuar?", 90, prot="20260928-3-COM")
    # cliente 1 volta no dia seguinte com "bom dia" (continuacao, nao lead novo)
    add("4__a", 1, "inbound", "bom dia, e o compactador?", 60 * 24, prot="20260929-1-COM")
    # protocolo aberto antes da janela
    add("4__d", 4, "inbound", "oi", 5, prot="20260901-4-COM")
    # marcador de midia/erro ao vivo: e turno, mas nao e texto do cliente
    add("4__c", 3, "inbound", "[errors]", 91, tipo="errors", prot="20260928-3-COM")
    # historico importado ao conectar um numero coex: gravado hoje, aconteceu
    # 30 dias antes — fora de todas as metricas
    for k, (dire, txt, op) in enumerate((("inbound", "[Midia do historico - aguardando]", None),
                                         ("inbound", "betoneira antiga", None),
                                         ("outbound", "ok", 4))):
        add("8__h", 9, dire, txt, 100, op=op, tipo="media_placeholder" if txt.startswith("[") else "text",
            canal=8, prot="20260928-9-COM", aconteceu_dias_antes=30)

    nomes = {4: "Danielle", 5: "Aline"}
    corte = t0 - timedelta(days=1)
    d = ms.metricas_comercial(m, nomes, CFG, corte)
    check(d["total_atendimentos"] == 4 and d["total_mensagens"] == 15,
          f"4 conversas e 15 turnos (sem sistema, reacao, falha e historico) — veio {d['total_atendimentos']}/{d['total_mensagens']}")
    check(d["importadas_ignoradas"] == 3, "3 mensagens de historico importado ignoradas")
    check(d["atendimentos_por_operador"] == {"Danielle": 1, "Aline": 1}, "1 atendimento por atendente")
    check(d["resposta_mediana_min"]["Danielle"] == 12.5 and d["primeira_resposta_mediana_min"]["Danielle"] == 5.0,
          "Danielle: mediana 12,5 min (5 e 20), primeira resposta 5 min")
    check(d["primeira_resposta_mediana_min"]["Aline"] == 11.0 and d["resposta_mediana_min"]["Aline"] == 6.0,
          "Aline: 1a resposta 11 min (conta da 1a mensagem sem resposta), mediana 6 (11 e 1)")
    check(list(d["volume_por_dia"]) == ["2026-09-28", "2026-09-29"], "dias em ISO, ordenados")
    termos = [e["termo"] for e in d["equipamentos"]]
    check("betoneira" in termos and "compactador" in termos, f"betoneira e compactador no topo ({termos})")
    check(not ({"diaria", "valor", "site", "hub", "lgpd", "aceitar"} & set(" ".join(termos).split())),
          "termos de fluxo, preco e LGPD fora do grafico")
    check(not ({"historico", "midia", "aguardando", "errors", "antiga"} & set(" ".join(termos).split())),
          "marcadores de midia/erro e historico importado fora do grafico")
    check("aline" not in " ".join(termos).split(), "nome da atendente citado pelo cliente fora do grafico")
    o = d["origem"]
    check(o["resumo"]["site"]["protocolos"] == 1 and o["resumo"]["meta"]["protocolos"] == 1
          and o["resumo"]["indeterminada"]["protocolos"] == 1, "1 protocolo de cada origem")
    check(o["continuacoes"] == 1, "cliente que voltou com 'bom dia' conta como continuacao")
    check(o["fora_da_janela"] == 1, "protocolo aberto antes do periodo fica fora")
    check(o["resumo"]["site"]["na_fila"] == 1 and o["resumo"]["site"]["com_humano"] == 1,
          "site: chegou a fila e teve resposta humana")
    check(o["resumo"]["meta"]["primeira_resposta_mediana_min"] == 11.0,
          "meta: 1a resposta humana 11 min depois da 1a fala")
    check(o["resumo"]["indeterminada"]["com_humano"] == 0, "indeterminada: so o bot respondeu")

    txt, n = ms.gerar_auditoria(m, nomes, 4, t0 - timedelta(hours=1), t0 + timedelta(days=2), "Hub Loc")
    check(n == 2, f"auditoria da Danielle: 2 protocolos da conversa dela (veio {n})")
    check("Cliente 1" in txt and "Cliente 2" not in txt, "so conversas em que ela respondeu")
    check("Danielle: R$ 90" in txt and "cliente: qual o valor" in txt, "autoria por linha")
    check("[telefone]" not in txt and "Cliente 4" not in txt, "conversa sem resposta dela fica fora")


def cenario_rotas():
    titulo("CENARIO 4 — rotas: permissao, tenant, metricas e export auditado")
    base_store()
    admin = {"id": 1, "role": "admin", "tenant_id": "hubloc", "perfil_acesso_id": "perfil_admin"}
    sup = {"id": 12, "role": "supervisor", "tenant_id": "hubloc", "perfil_acesso_id": "perfil_supervisor"}
    op = {"id": 4, "role": "operador", "tenant_id": "hubloc", "perfil_acesso_id": "perfil_operador"}
    adm_vz = {"id": 2, "role": "admin", "tenant_id": "varizemed", "perfil_acesso_id": "perfil_admin"}

    check(rbac.has_permission(admin, "ver_monitor_atendimento"), "admin tem o toggle (seed)")
    check(not rbac.has_permission(sup, "ver_monitor_atendimento"), "supervisor NAO tem")
    check(not rbac.has_permission(op, "ver_monitor_atendimento"), "operador NAO tem")

    def status(coro):
        try:
            asyncio.run(coro)
            return 200
        except main.HTTPException as e:
            return e.status_code

    check(status(main.monitor_fila(current_user=sup)) == 403, "supervisor -> 403 na fila")
    check(status(main.monitor_fila(current_user=adm_vz)) == 404, "admin da varizemed -> 404 (sem monitor)")
    s_adm = asyncio.run(main.session_info(current_user=admin))
    s_sup = asyncio.run(main.session_info(current_user=sup))
    s_vz = asyncio.run(main.session_info(current_user=adm_vz))
    check(s_adm["monitor"]["enabled"] is True and s_sup["monitor"]["enabled"] is True
          and s_vz["monitor"]["enabled"] is False,
          "sessao: hubloc tem monitor, varizemed nao (o menu usa ainda o toggle, ao vivo)")
    rbac.get_perfil_toggles = lambda t, p: {"ver_monitor_atendimento": True} if p == "perfil_supervisor" else None
    check(rbac.has_permission(sup, "ver_monitor_atendimento")
          and status(main.monitor_fila(current_user=sup)) == 200,
          "admin liga o toggle no perfil Supervisor -> supervisor passa a ver (RBAC)")
    rbac.get_perfil_toggles = lambda t, p: None

    agora = datetime.now(timezone.utc)
    msg(10, "4__x", 50, "inbound", "Olá! Vim pelo site da Hub Loc: andaime", agora - timedelta(hours=2),
        protocolo=agora.astimezone(BR).strftime("%Y%m%d") + "-50-COM")
    msg(11, "4__x", 50, "outbound", "Oi, aqui é a Danielle, meu zap 31 98344-0484", agora - timedelta(hours=1),
        op=4, protocolo=agora.astimezone(BR).strftime("%Y%m%d") + "-50-COM")
    msg(12, "4__y", 51, "inbound", "velho", agora - timedelta(days=40))
    ms._cache.clear()
    met = asyncio.run(main.monitor_metricas(dias=14, refresh=True, current_user=admin))
    check(met["mensagens_lidas"] == 2 and met["truncado"] is False,
          "metricas leem so a faixa de created_at do periodo")
    check(met["dados"]["origem"]["resumo"]["site"]["protocolos"] == 1 and met["origem_ativa"] is True,
          "origem calculada pela rota")
    QUERIES.clear()
    asyncio.run(main.monitor_metricas(dias=14, refresh=False, current_user=admin))
    check(not QUERIES, "2a abertura dentro de 10 min sai do cache (zero leitura)")

    hoje = agora.astimezone(BR).date()
    check(status(main.monitor_auditoria(operador_id=4, inicio=str(hoje), fim=str(hoje - timedelta(days=1)),
                                        current_user=admin)) == 400, "fim antes do inicio -> 400")
    check(status(main.monitor_auditoria(operador_id=4, inicio=str(hoje - timedelta(days=40)), fim=str(hoje),
                                        current_user=admin)) == 400, "periodo acima de 31 dias -> 400")
    check(status(main.monitor_auditoria(operador_id=4, inicio=str(hoje), fim=str(hoje),
                                        current_user=sup)) == 403, "supervisor nao exporta")
    AUDITS.clear()
    resp = asyncio.run(main.monitor_auditoria(operador_id=4, inicio=str(hoje - timedelta(days=1)),
                                              fim=str(hoje), current_user=admin))
    corpo = resp.body.decode("utf-8")
    check("attachment" in resp.headers.get("content-disposition", "") and "danielle" in
          resp.headers.get("content-disposition", ""), "download .txt com o nome da atendente")
    check("Cliente 50" in corpo and "98344" not in corpo, "conversa dela no arquivo, telefone redigido")
    check(AUDITS and AUDITS[0][1] == "MONITOR_AUDITORIA_EXPORT" and "operador=4" in AUDITS[0][2],
          "export registrado na auditoria do tenant")


if __name__ == "__main__":
    cenario_config_e_texto()
    cenario_fila()
    cenario_metricas()
    cenario_rotas()
    print("\n" + "=" * 70)
    if FAILS:
        print(f"FALHOU: {len(FAILS)} de {CHECKS} checagens")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print(f"OK: {CHECKS} checagens passaram")
    sys.exit(0)
