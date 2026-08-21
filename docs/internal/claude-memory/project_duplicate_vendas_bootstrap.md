---
name: project_duplicate_vendas_bootstrap
description: Setores "Vendas" duplicados (bot_key=comercial) criados pelo bootstrap no startup — sequestraram o roteamento comercial; leads movidos pra Comercial(2); delete na UI e seguro+permanente
metadata:
  node_type: memory
  type: project
  originSessionId: 4a88a0f8-336a-41bc-8e73-70a3a3ec2622
---

Descoberto 2026-06-29: hubloc tinha DOIS setores "Vendas" (departments id 7 e 8),
ambos `bot_key="comercial"`, criados 2026-06-23 10:14:07 com **0.076s de diferenca**
e SEM entrada no audit_log.

**Causa raiz (NAO foi rename do Comercial pelo usuario):**
- `bootstrap_data.py` `DEFAULT_DEPARTMENTS` tem `{"name":"Vendas","bot_key":"comercial"}`
  (colide com o setor real "Comercial" id=2, que tambem e bot_key=comercial).
- `bootstrap_departments()` roda em `@app.on_event("startup")` ([main.py:447-456]) em
  TODA instancia nova (deploy/cold-start/scale-up), chamando `ensure_default_departments`.
- `create_department` (database_firestore.py:191) e idempotente-POR-NOME (skip se existe),
  MAS o check-then-create NAO e transacional. Dois cold-starts concorrentes chamaram
  `create_department("Vendas")` ao mesmo tempo, ambos viram "nao existe" -> criaram 2
  docs (race TOCTOU). Sem audit porque e o create de DB, nao o endpoint (so o endpoint
  POST /api/admin/departments loga DEPARTMENT_CREATE).

**Impacto:** `_setor_to_dept_map` (bot_service.py:181) e last-wins por bot_key ->
"comercial" resolvia pro Vendas (id 8) em vez do Comercial real (id=2). 49 leads
(dept 7=15 + dept 8=34, criados desde 23/06) ficaram invisiveis pra Danielle(user 4)
e Aline(user 5), ambas dept=2. teste@ (user 13) tava preso em dept 8 — so REVELOU o bug.

**Fix de dados (FEITO 06-29):** 49 conversas + 46 contatos com department_id 7/8 -> 2;
`users/13` (teste@) -> dept 2. Via Firestore REST PATCH (ver [[project_oregon_prod_cutover]]).
Verificado: dept 2 = 789 (era 740), dept 7/8 zerados.

**Deletar setor na UI e SEGURO e PERMANENTE:**
- "Deletar" = soft delete: `deactivate_department` (db:245) so seta `is_active=0` +
  `updated_at` no doc do setor. NAO apaga conversa/contato/mensagem (colecoes separadas).
- Nao volta a recriar: `_get_first_by_field("departments","name","Vendas")` (db:56)
  IGNORA is_active -> acha o doc inativo -> bootstrap pula a recriacao.
- Bot para de ver: `get_all_departments()` exclui is_active=0 por padrao (db:212) ->
  "comercial" volta a rotear so pro id 2. (Cache `_dept_cache` por instancia; o endpoint
  de delete chama `invalidate_dept_cache`.)

**Mecanismo confirmado por revisao adversarial (Workflow, 4 agentes, 2026-06-29):**
o gatilho real e RENOMEAR um setor cujo nome esta em DEFAULT_DEPARTMENTS. O rename
deixa o nome default ORFAO; no proximo startup o bootstrap nao acha aquele nome
(`create_department` deduplica SO por nome) e recria. A race so explica o DOBRO
(Vendas saiu 2x). Casos: id1 "Geral"->renomeado p/ "Administrativo" (06-23 03:18:14)
-> bootstrap recriou "Geral" id6 33s depois (03:18:47, 1 copia, boot solo).
id2 "Vendas"->renomeado p/ "Comercial" (03:27:31) -> recriou "Vendas" id7+id8
(10:14:07, 2 copias, boots concorrentes). Suporte(3)/Financeiro(4) NAO renomeados
-> nomes batem com o default -> dedup idempotente -> nao duplicaram.

**REGRAS OPERACIONAIS (pos-hardening de 2026-06-30 — ver abaixo):**
- Renomear setor AGORA E SEGURO: o gate em bootstrap_departments + bootstrap_admin_user
  nao recria mais nada num tenant que ja tem setores. (Antes do fix era proibido renomear
  Suporte/Financeiro/qualquer nome default — o bootstrap recriava a versao default no boot.)
- NUNCA renomear o Geral(6)/Vendas(7,8) antes de deletar — renomear orfana o nome e
  recria um setor ATIVO novo. Deletar MANTENDO o nome e seguro.
- "Deletar" na UI = SOFT delete (is_active=0). E o caminho certo: nao apaga conversa,
  e o doc inativo "tombstona" o nome (`_get_first_by_field` ignora is_active) ->
  bootstrap nao recria. NUNCA hard-delete um setor de nome default (volta do zero, ativo).
- default_department_id de canal e CAMPO MORTO (write-only, sem leitor em runtime hoje).
  Nenhum canal aponta p/ 6/7/8 (so ch3->dept2, correto). transfer/reassign NAO validam
  to_department_id (da p/ carimbar dept inativo e esconder a conversa da pool).

**Geral id6 (cleanup pendente, aguardando go do usuario):** tem 1 conversa VIVA
`4__55319XXXXXXXX` (ABERTA, assigned_to=operador 6, unread=1, msg de hoje) + contato 7479,
ambos department_id=6. Plano: PATCH department_id 6->1 (Administrativo) na conversa E no
contato (merge, so o campo, sem tocar assigned_to/unread/status/last_message_at);
confirmar id6 zerado; usuario soft-deleta Geral(6) + Vendas(7,8) na UI mantendo os nomes.

**Hardening DEPLOYADO em prod 2026-06-30 (commit 5dfc66c, rev castro-crm-00035-zax):**
(A) gate em `bootstrap_departments` (main.py) — so semeia defaults se get_all_departments(
include_inactive=True) estiver vazio; trava principal, mata a recriacao. (B)
`ensure_default_departments` (bootstrap_data.py) pula default ja coberto por nome/bot_key
ativo (param opcional existing_departments — dormante, blindagem p/ init_db/callers diretos).
(C) gate em `bootstrap_admin_user` (main.py) — resolve setor do admin por nome existente;
so cria em tenant vazio; senao department_id=None (nao recria 'Geral' fantasma). (D)
`_validate_transfer_department` em /api/wa/transfer e /api/admin/reassign-lead — 400 se
to_department_id inexistente/inativo.
NAO implementado de proposito: o `create_department` atomico via doc-indice (department_index)
foi PROPOSTO e REVERTIDO — a revisao adversarial mostrou que o indice virava 2a fonte de
verdade nao-mantida em rename/delete (devolvia id errado); a race que ele resolvia so
acontecia via bootstrap concorrente, que o gate (A) ja elimina. Residual aceito: race de
duplo-clique do admin criando setor novo (raro, pre-existente) — daria p/ fechar com transacao
se algum dia incomodar. Validado em cold-start real no staging (departments seguiu == 8).

Relacionado: [[project_bot_flow_e_pool_setor]] [[project_operator_isolation_lgpd]].
