---
name: project_bot_flow_e_pool_setor
description: Fluxo do bot WhatsApp (LGPD->setor) e como o setor vira pool segmentada por departamento
metadata: 
  node_type: memory
  type: project
  originSessionId: 337f8227-2958-4b6e-b200-f098069299a0
  modified: 2026-07-24T17:19:26.970Z
---

**MENU DE SETORES REMOVIDO em 2026-07-24 (prod rev castro-crm-00064-2f9, promovida
por nome — ver [[project_deploy_staging_tag_traffic]]). Validado pelo Rafael.**
Pedido da empresa: todo lead novo entra pelo Comercial; operador transfere de setor
no CRM se preciso.

**Fluxo atual:** `1o contato -> lgpd_awaiting -> done`. Apos o aceite da LGPD, o bot
chama `_finalize_bot(setor=1 Comercial)` na hora e responde "Você já está na fila do
nosso time Comercial". NAO mostra mais o menu 1-4, nem pergunta nome/equipamento.
LGPD curto com botoes Sim/Nao (ids `lgpd_aceitar`/`lgpd_recusar`).

**Legado ask_sector honrado:** contatos que ja tinham recebido o menu antigo (bot_states
step=ask_sector em voo no deploy) sao tratados — escolha digitada reconhecida roteia pro
setor; entrada nao reconhecida cai no Comercial (menu nao existe mais). Vocabularios de
setor (`_classificar_setor`, `_BOT_KEY_BY_SETOR`) mantidos so pra esse caminho legado.

Roteamento e por `bot_key`, entao **renomear departamento na UI nao quebra**.
`_get_dept_map` resolve por bot_key, fallback por nome. (Historico pre-2026-07-24: o menu
oferecia 1 Comercial/2 Assistencia-sac/3 Financeiro/4 Outros-administrativo.)

**Pegadinha critica (pool):** a pool ("novos") do frontend
([CrmContext.tsx] filtro novosConversations) segmenta por `department_id`
e exige dono vazio na **CONVERSATION** (`wa_conversations`), nao no contato.
Por isso:
- `_finalize_bot` grava `department_id` na conversation (nao so no contato),
  senao a pool nao segmenta por setor para operador comum.
- `return_contact_to_bot` ([database_firestore.py]) precisa limpar
  assigned_to/assigned_to_uid/department_id **nas threads** tambem, senao o
  lead devolvido fica preso na aba do operador anterior e nunca entra na pool.

Operador comum ve na pool so leads do seu departamento (ou sem dept);
admin/supervisor veem tudo. Ver [[project_operator_isolation_lgpd]].

Teste local sem tocar prod: `.venv\Scripts\python.exe tools\sim_bot_flow.py`
(Firestore/Meta mockados; exercita bot_service + lgpd_bot + bot_transport).
