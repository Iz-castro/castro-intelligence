# -*- coding: utf-8 -*-
"""Janelas HTTP do Ver como com dados sinteticos e Firestore em memoria.

Nao inicia lifespan, nao usa credenciais nem permite conexao externa.
Rodar com o Python do venv principal, como os demais tools/sim_*.py.
"""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import socket
import sys
import traceback
from unittest.mock import patch

import sim_impersonate as sim
import impersonation_views as views

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = sim.TARGET["firebase_uid"]
check, title = sim.check, sim.title


def user(broad=False, role="operador"):
    sim.bucket("perfis_acesso")["perfil_views"] = {
        "role_equivalente": role, "toggles": {"ver_todos_leads": broad, "ver_dashboard_uso": False}}
    sim.rbac.invalidate_perfil_cache()
    return dict(sim.TARGET, role=role, perfil_acesso_id="perfil_views", impersonation={
        "auth_uid": sim.temp_uid(), "expires_at": (BASE + timedelta(hours=1)).isoformat()})


def ids(rows):
    return [row["id"] for row in rows]


def deny(call, status, label):
    sim.expect_http(call, status, label)


def large_fixture():
    sim.reset()
    # Mais de 50 por target; estrangeiros recentes dominam o global top-300.
    for name in ("wa_contacts", "wa_conversations"):
        for group, owner, offset, count in (("mine", UID, 1000, 75), ("blank", "", 2000, 75),
                                            ("null", None, 3000, 75), ("foreign", "uid-other", 10000, 450)):
            for rank in range(count):
                key = f"{group}-{rank:03}"
                row = {"id": key, "assigned_to_uid": owner, "is_archived": 0,
                       "last_message_at": BASE + timedelta(seconds=offset - rank),
                       "unread_count": rank % 4, "department_id": 88}
                if rank in (0, 20):
                    row["is_backup"] = True
                elif rank != 2:
                    row["is_backup"] = False
                sim.bucket(name)[key] = row
        sim.bucket(name)["missing-owner"] = {
            "id": "missing-owner", "is_archived": 0, "last_message_at": BASE + timedelta(days=1)}
        sim.bucket(name)["missing-order"] = {"id": "missing-order", "assigned_to_uid": None, "is_archived": 0}
    sim.bucket("wa_contacts")["archived"] = {"id": "archived", "assigned_to_uid": UID,
        "is_archived": 1, "last_message_at": BASE + timedelta(days=2)}
    sim.bucket("wa_contacts", sim.OTHER_TENANT)["other-tenant"] = {
        "id": "other-tenant", "assigned_to_uid": UID, "is_archived": 0,
        "last_message_at": BASE + timedelta(days=3)}


def scenario_snapshot():
    title("VIEWS 1 - Janelas por target, backup, legado e tenant")
    large_fixture()
    normalized = views.normalize_snapshot_record({"at": BASE.replace(microsecond=123456),
        "nested": [{"at": BASE.replace(microsecond=123456)}], "legacy": "2026-01-01T00:00:00.123456+00:00"})
    check(normalized["at"] == "2026-01-01T00:00:00.123Z"
          and normalized["nested"][0]["at"] == normalized["at"],
          "Timestamp convertido recursivamente para UTC/milissegundos como SDK.toDate().toISOString")
    check(normalized["legacy"] == "2026-01-01T00:00:00.123456+00:00",
          "string legada permanece intacta durante normalizacao de snapshot")
    target = user()
    result = views.read_snapshot(target)
    for source in ("contact_groups", "conversation_groups"):
        for key, prefix in (("mine:" + UID, "mine"), ("unassigned:blank", "blank"), ("unassigned:null", "null")):
            expected = [f"{prefix}-{rank:03}" for rank in range(50) if rank not in (0, 20)]
            check(ids(result[source][key]) == expected, f"{source} {prefix}: top50 proprio, remove backup sem reposicao")
            check(result[source][key][1]["id"] == f"{prefix}-002", f"{source} {prefix}: is_backup ausente permanece visivel")
            check(all(isinstance(row["last_message_at"], str) for row in result[source][key]),
                  f"{source} {prefix}: timestamps normalizados antes do HTTP")
    check(all(result["contact_saturated"].values()) and all(result["conversation_saturated"].values()),
          "saturacao usa 50 documentos brutos, embora entregue 48")
    check(result["mine_load_more"] is True, "gate Meus conta janela bruta50 mesmo com backup removido")
    check("all" not in result["contact_groups"] and "backup" not in result["conversation_groups"],
          "operador nao recebe target global ou backup")
    check(all(query[0] == sim.TENANT for query in sim.QUERIES), "queries sempre no tenant autenticado")
    check(not sim.WRITES and not sim.AUDITS, "snapshot nao grava identidade, audit, unread ou ownership")
    sim.fsc.set_tenant_context(sim.OTHER_TENANT)
    isolated = views.read_snapshot(target)
    check(ids(isolated["contact_groups"]["mine:" + UID]) == ids(result["contact_groups"]["mine:" + UID])
          and sim.fsc.get_tenant_context() == sim.OTHER_TENANT,
          "servico prende tenant da sessao e restaura contexto anterior")
    sim.fsc.set_tenant_context(sim.TENANT)
    supervisor = user(True, "supervisor")
    broad = views.read_snapshot(supervisor)
    check(len(broad["contact_groups"]["all"]) == 50 and len(broad["conversation_groups"]["all"]) == 300,
          "supervisor custom recebe janelas all50/all300 originais")
    check(ids(broad["conversation_groups"]["all"])[:2] == ["missing-owner", "foreign-000"],
          "all usa recencia global, independentemente dos targets mine/pool")
    check(len(broad["conversation_groups"]["backup"]) == 8,
          "target backup explicito preserva consulta original sem limite silencioso")
    check(broad["perfil"]["toggles"]["ver_todos_leads"] is True
          and broad["perfil"]["toggles"]["ver_dashboard_uso"] is False,
          "perfil custom do supervisor preserva toggles sem abrir tudo")
    check(not sim.WRITES, "janelas amplas tambem sao apenas leitura")
    # Legado: ownership numerico proprio pode estar no target pool de UID vazio.
    sim.bucket("wa_conversations").clear()
    for rank in range(49):
        sim.bucket("wa_conversations")[f"legacy-{rank}"] = {"assigned_to_uid": "", "assigned_to": target["id"],
            "last_message_at": BASE + timedelta(seconds=rank), "is_backup": rank == 0}
    check(views.read_snapshot(target)["mine_load_more"] is False,
          "49 threads legadas da pool nao ativam carregar mais Meus")
    sim.bucket("wa_conversations")["legacy-49"] = {"assigned_to_uid": "", "assigned_to": target["id"],
        "last_message_at": BASE + timedelta(seconds=49), "is_backup": True}
    legacy = views.read_snapshot(target)
    check(legacy["mine_load_more"] is True and len(legacy["conversation_groups"]["unassigned:blank"]) == 48,
          "50 legadas da pool ativam gate por dono numerico sem entregar dois backups")
    check(set(legacy) == {"contact_groups", "conversation_groups", "contact_saturated", "conversation_saturated",
                         "perfil", "mine_load_more", "read_at", "expires_at"},
          "snapshot nao expoe colecao bruta ou IDs dos backups removidos")


def scenario_pages():
    title("VIEWS 2 - Limites crescentes, nao lidas e escopos")
    large_fixture()
    target = user()
    for limit in (50, 100, 150):
        result = views.read_page(target, "mine", "meus", limit)
        expected = [f"mine-{rank:03}" for rank in range(min(limit, 75)) if rank not in (0, 20)]
        check(ids(result["groups"]["mine:" + UID]) == expected, f"Meus limite {limit} sem teto silencioso")
        check(result["saturated"]["mine:" + UID] == (limit <= 75), f"Meus limite {limit} saturacao real")
    pooled = views.read_page(target, "pool", "novos", 100)
    check(set(pooled["groups"]) == {"unassigned:blank", "unassigned:null"}
          and all(len(rows) == 73 for rows in pooled["groups"].values()),
          "Carregar mais da pool mantem blank/null separados")
    unread = views.read_page(target, "unread", "meus", 50)
    ranks = [rank for rank in range(75) if rank % 4 > 0]
    ranks.sort(key=lambda rank: (-(rank % 4), rank))
    check(ids(unread["groups"]["mine:" + UID]) == [f"mine-{rank:03}" for rank in ranks[:50]],
          "nao lidas ordena unread desc e depois recencia desc")
    check(unread["saturated"]["mine:" + UID], "nao lidas preserva saturacao de origem")
    for scope, view in (("all", "equipe"), ("mine", "equipe"), ("pool", "meus"),
                        ("unread", "backup"), ("path", "meus"), ("mine", "inventado")):
        deny(lambda: views.read_page(target, scope, view, 50), 403, f"escopo {scope}/{view} negado")
    for invalid in (0, -1, True, 1.5, "50"):
        deny(lambda: views.read_page(target, "mine", "meus", invalid), 400, "limite invalido rejeitado")
    supervisor = user(True, "supervisor")
    for limit in (300, 600):
        result = views.read_page(supervisor, "all", "equipe", limit)
        check(len(result["groups"]["all"]) == limit, f"Equipe {limit} preserva janela global crescente")
    limited_supervisor = user(False, "supervisor")
    deny(lambda: views.read_page(limited_supervisor, "all", "equipe", 300), 403,
         "supervisor com toggle OFF nao ganha Equipe")
    expanded_operator = user(True, "operador")
    deny(lambda: views.read_page(expanded_operator, "all", "equipe", 300), 403,
         "toggle ON de operador nao ultrapassa teto de role")
    with patch.object(views, "collection", side_effect=RuntimeError("Indice simulado ausente")):
        try:
            views.read_page(target, "mine", "meus", 50)
        except RuntimeError:
            check(True, "erro de indice propaga sem full-scan de fallback")
        else:
            check(False, "ausencia de indice deveria falhar")
    check(not sim.WRITES, "paginacao e erros nao gravam")


def detail_fixture():
    sim.reset()
    contacts = sim.bucket("wa_contacts")
    for contact_id, owner, wa in ((1, UID, "A"), (2, "uid-other", "B"),
                                 (3, "uid-other", "C"), (4, UID, "D"), (5, "", "E")):
        contacts[str(contact_id)] = {"id": contact_id, "assigned_to_uid": owner,
            "channel_id": 1, "wa_id": wa, "department_id": 88, "is_backup": contact_id == 4}
    threads = sim.bucket("wa_conversations")
    for channel, wa, cid, owner, backup in ((1, "A", 1, UID, False), (2, "A", 1, "uid-other", False),
            (3, "A", 1, UID, True), (4, "A", 1, "", False), (1, "B", 2, UID, False),
            (2, "B", 2, "uid-other", False), (1, "C", 3, "uid-other", False), (1, "D", 4, UID, True)):
        key = f"{channel}__{wa}"
        threads[key] = {"id": key, "contact_id": cid, "assigned_to_uid": owner, "is_backup": backup,
                        "last_message_at": BASE}


def scenario_details():
    title("VIEWS 3 - Thread canonica, IDOR e mensagens")
    detail_fixture()
    target = user()
    check(views.read_thread(target, 1)["conversation"]["id"] == "1__A", "canal omitido deriva contato, sem abrir/criar")
    check(views.read_thread(target, 2, 1)["conversation"]["id"] == "1__B",
          "thread propria hidrata lead cujo dono e outra pessoa")
    protocol_rows = [
        {"id": 71, "contact_id": 2, "conversation_id": "1__B", "timestamp_wa": BASE},
        {"id": 72, "contact_id": 2, "conversation_id": "2__B", "timestamp_wa": BASE},
        {"id": 73, "contact_id": 2, "timestamp_wa": BASE},
        {"id": 74, "contact_id": 2, "conversation_id": "1__B", "is_backup": True},
    ]
    check(ids(views.filter_message_rows(target, sim.bucket("wa_contacts")["2"], protocol_rows)) == [71],
          "protocolo de lead colega entrega somente thread propria, sem legado alheio/backup")
    for cid, channel in ((1, 2), (1, 3), (2, 2), (3, 1), (4, 1)):
        deny(lambda: views.read_thread(target, cid, channel), 403, f"thread {cid}/{channel}: owner/backup independente do lead")
    check(views.read_thread(target, 5)["conversation"] is None, "thread ausente retorna null sem criacao")
    deny(lambda: views.read_thread(target, 999), 404, "contato inexistente nao e enumerado")
    deny(lambda: views.read_thread(target, 1, 0), 400, "canal invalido rejeitado")
    sim.bucket("wa_conversations")["1__A"]["id"] = "2__A"
    check(views.read_thread(target, 1, 1)["conversation"]["id"] == "1__A",
          "ID da thread deriva servidor, nao confia em id gravado divergente")
    sim.bucket("wa_conversations")["1__A"]["id"] = "1__A"
    for number in range(1, 41):
        sim.bucket("wa_messages")[str(number)] = {"id": number, "contact_id": 1,
            "conversation_id": "1__A" if number % 2 else "2__A", "timestamp_wa": BASE + timedelta(seconds=number),
            "is_backup": number == 39}
    for limit in (10, 25):
        legacy = views.read_messages(target, 1, limit=limit)["messages"]
        expected = [number for number in range(41 - limit, 41) if number % 2 and number != 39]
        check(ids(legacy) == expected, f"timeline legado {limit}: filtra backup/thread alheia sem reposicao")
    selected = views.read_messages(target, 1, 1, 10)["messages"]
    check(ids(selected) == list(range(21, 39, 2)), "thread selecionada consulta propria janela10 e remove backup")
    check(views.read_messages(target, 5, 1)["messages"] == [], "mensagens de thread ausente sao vazias sem criar")
    for cid, channel in ((1, 2), (1, 3), (3, 1), (4, None)):
        deny(lambda: views.read_messages(target, cid, channel), 403, "historico tambem confere owner/backup")
    sim.bucket("wa_messages").clear()
    for ident in (100, 101, 102):
        sim.bucket("wa_messages")[str(ident)] = {"id": ident, "contact_id": 1,
            "conversation_id": "1__A", "timestamp_wa": BASE}
    check(ids(views.read_messages(target, 1, 1)["messages"]) == [100, 101, 102],
          "timestamps iguais preservam ordem estavel do snapshot, sem reverse")
    deny(lambda: views.read_snapshot(dict(target, impersonation={})), 403, "servico rejeita usuario sem identidade temporaria")
    deny(lambda: views.read_snapshot(dict(target, firebase_uid=sim.temp_uid())), 403,
         "UID efetivo reservado nao vira target")
    check(not sim.WRITES and not sim.AUDITS, "detalhes nao alteram unread/ownership nem contas")


def scenario_internal():
    title("VIEWS 4 - Janelas globais do chat interno e empates estaveis")
    sim.reset()
    target = user()
    for number in range(1, 61):
        sim.bucket("gc_conversations")[str(number)] = {"id": number,
            "last_message_at": BASE + timedelta(seconds=number)}
    for number in range(1, 131):
        sim.bucket("gc_messages")[str(number)] = {"id": number, "conversation_id": 1 if number % 3 else 2,
            "created_at": BASE + timedelta(seconds=number)}
    check(ids(views.read_internal_chat(target, "conversations")["items"]) == list(range(60, 10, -1)),
          "chat interno usa 50 conversas globais recentes")
    check(ids(views.read_internal_chat(target, "messages", 1)["items"]) == [n for n in range(31, 131) if n % 3],
          "chat interno filtra conversa depois do top100 global existente")
    sim.bucket("gc_messages").clear()
    for ident in (20, 21, 22):
        sim.bucket("gc_messages")[str(ident)] = {"id": ident, "conversation_id": 1, "created_at": BASE}
    check(ids(views.read_internal_chat(target, "messages", 1)["items"]) == [20, 21, 22],
          "chat interno preserva empates estaveis")
    deny(lambda: views.read_internal_chat(target, "conversations", 1), 400, "seletor nao aceito no kind conversations")
    deny(lambda: views.read_internal_chat(target, "messages", 999), 404, "conversa inexistente nao entrega mensagens")
    deny(lambda: views.read_internal_chat(target, "messages"), 400, "messages requer conversation_id")
    deny(lambda: views.read_internal_chat(target, "collection"), 400, "kind livre nao e query generica")
    check(not sim.WRITES, "chat interno nunca marca mensagens lidas")


def main_sim():
    with ExitStack() as stack:
        for module, name, value in ((socket.socket, "connect", sim.no_external),
                (socket.socket, "connect_ex", sim.no_external),
                (sim.fsc, "get_firestore_client", sim.no_external),
                (views, "collection", sim.Collection), (views, "document", sim.Document),
                (sim.rbac, "document", sim.Document)):
            stack.enter_context(patch.object(module, name, value))
        for scenario in (scenario_snapshot, scenario_pages, scenario_details, scenario_internal):
            try:
                scenario()
            except Exception:
                sim.FAILS.append(scenario.__name__)
                traceback.print_exc()
    print(f"\nRESULTADO VIEWS: {sim.CHECKS} asserts, {len(sim.FAILS)} falhas")
    for label in sim.FAILS:
        print("  - " + label)
    return 1 if sim.FAILS else 0


if __name__ == "__main__":
    sys.exit(main_sim())
