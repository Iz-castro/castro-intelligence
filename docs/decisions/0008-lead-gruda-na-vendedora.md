# ADR 0008 — Lead "gruda" na vendedora (dona de origem + revert no fechamento)

- **Status:** Accepted (implementado e validado em producao 2026-06-05)
- **Data:** 2026-06-05
- **Autores:** Rafa (regra de negocio) + Claude (mapeamento do codigo + implementacao)
- **Relacionado:** ADR [0003](0003-refactor-lead-atendimento.md) (separacao Dono do
  Lead vs Dono do Atendimento — Fase 3B); modelo de isolamento de operador
  ([firestore.rules](../../firestore.rules) `canSeeContactScoped`);
  assume [main.py](../../main.py) `wa_assume_contact`;
  reassign-lead [main.py](../../main.py) `admin_reassign_lead`;
  reroute de conversao [webhook.py:766](../../webhook.py#L766);
  helpers [database_firestore.py](../../database_firestore.py)
  `set_sale_owner`/`revert_lead_to_sale_owner`.

## Contexto

A Hubloc opera **um numero standard (Cloud API) compartilhado** por varias
vendedoras (operadoras comuns). O fluxo de atendimento: o lead chega no pool
("Novos"), uma vendedora **assume**, e pode **transferir** (handoff) pra outra
operadora durante o atendimento.

Regra de negocio pedida: **a vendedora que assumiu o lead "fica dona" dele** —
mesmo que o atendimento passe por outras maos durante a conversa, quando o
cliente voltar a falar, ele deve cair de novo **pra vendedora que fez a venda**
(prioridade comercial / relacionamento).

A Fase 3B (ADR 0003) ja separa **Dono do Lead** (`contact.assigned_to`) de
**Dono do Atendimento** (`conversation.assigned_to`). Mas faltavam duas coisas
pra implementar essa regra:

1. Um **registro persistente** de quem foi a vendedora de origem — o
   `assigned_to` do contato muda com handoff/reassign, entao nao serve.
2. Uma **acao de reversao** no momento certo (fechamento) que devolva o lead.

Confirmacoes do cliente (que viraram requisitos):

- **Quem e a "dona de origem":** a **primeira** operadora a assumir. Handoff
  entre operadores comuns **nao** muda. Apenas **admin/supervisor** trocam a
  dona de verdade (via `reassign-lead`), e nesse caso a dona de origem
  **acompanha** o novo dono.
- **Gatilho da reversao:** o **fechamento** — tanto **manual** quanto pelo
  **cron de inatividade** (hoje `ATTENDANCE_AUTOCLOSE_HOURS=6` em prod).
- **"Assumir pra falar":** operador comum nao pode enviar mensagem pra lead em
  "Novos" (pool) — tem que assumir antes.

## Decisao

### 1. Campo novo `sale_owner_user_id` / `sale_owner_uid` no `wa_contacts`

Criado um campo **dedicado** pra "dona de origem", **separado** de
`original_operator_id`. Motivo: `original_operator_id` ja tem uso ativo e
**conflitante** — reroute de lead ja convertido no **inbound**
([webhook.py:766](../../webhook.py#L766)) e e projetado pra ser **imutavel**.
Reusa-lo quebraria o requisito de o admin poder atualizar a dona, e acoplaria
dois gatilhos distintos (inbound vs fechamento) no mesmo campo.

- Gravado na **1a assuncao** (`wa_assume_contact`, so se ainda nao tiver).
- **Handoff** (`/api/wa/transfer` → `assign_wa_conversation`/`assign_wa_contact`)
  **nao toca** `sale_owner_*` — satisfaz "handoff nao muda a dona" de graca.
- **`reassign-lead`** (admin/supervisor) chama `set_sale_owner(contact, novo)`
  → a dona de origem acompanha.

### 2. Reversao no fechamento devolve **lead E atendimento**

No fechamento, `revert_lead_to_sale_owner(contact_id)` reverte o **contato**
(Dono do Lead) e **retorna** `{assigned_to, assigned_to_uid}` pro caller
reverter tambem a **conversa fechada** (Dono do Atendimento). Chamado nos dois
caminhos de fechamento:

- Manual: `set_attendance_status` (`status.startswith("fechado")`).
- Cron: `close_stale_attendances`.

Reverter **os dois** e essencial: se so o contato voltasse, ao reabrir no
proximo inbound a conversa **nao re-herda** (o guard de orfa em
`upsert_wa_conversation` so atribui quando `assigned_to` esta vazio) e ficaria
presa no ultimo handler — foi exatamente o bug observado no teste (Roberta
assumiu → transferiu p/ danielle → fechou → "Oi de novo" caiu na danielle). Com
a conversa tambem revertida, ao reabrir ela ja e da vendedora de origem.

### 3. Salvaguardas (nao inventar dono, nao vazar)

- **Sem `sale_owner`** (lead nunca assumido): nao reverte — fica no **pool**.
- **Dona inativa/deletada** (`is_active` falso): nao reverte — evita grudar o
  lead numa conta que ninguem opera (ficaria orfao invisivel).
- **Idempotente:** so escreve se o dono mudou.
- **`sale_owner_uid` e metadado de roteamento** — **NAO** entra em nenhuma query
  de escopo nem na rule `canSeeContactScoped`. O isolamento continua 100% por
  `assigned_to_uid`. A reversao grava `assigned_to`/`assigned_to_uid` da dona
  (por isso o helper busca o `firebase_uid`): sem o `_uid`, o lead "sumiria" do
  frontend/rules da propria dona — bug de isolamento ao contrario.

### 4. "Assumir pra falar" — ja existia (sem mudanca)

O requisito de bloquear operador comum de enviar em lead sem dono **ja estava
coberto** por `_check_conv_send_permission` (main.py): conversa sem
`assigned_to` → 403 "Assuma o atendimento antes de enviar mensagem". Admin/
supervisor isentos. Nenhum codigo novo.

## Consequencias

### Positivas
- A vendedora que trabalhou o lead recupera a prioridade no retorno do cliente,
  sem intervencao manual — automatico no fechamento.
- Reaproveita a separacao Lead vs Atendimento (Fase 3B) e a heranca de dono no
  inbound (`save_wa_message`) que ja existiam.
- Isolamento LGPD intacto: nenhum campo novo participa de escopo; a reversao
  respeita as 3 camadas (backend/frontend/rules) porque grava `assigned_to_uid`.

### Negativas / atencao
- No fechamento, a **ultima operadora perde a thread fechada** (volta pra
  origem). E o comportamento desejado, mas e uma mudanca de posse silenciosa —
  por isso a reversao so ocorre **no fechamento**, nunca durante o atendimento
  ativo (handoff em curso preserva quem esta atendendo).
- Leads **anteriores** a este deploy nao tem `sale_owner` (so e setado em novas
  assuncoes) — comportam-se como "nunca assumido" no revert (ficam no pool).
  Aceitavel; sem backfill.
- A reversao depende do `is_active` do usuario — se o flag tiver outro nome no
  schema de `users`, ajustar a checagem (`owner.get("is_active", 1)`).

## Implementacao

- `database_firestore.py`: helpers `set_sale_owner`, `revert_lead_to_sale_owner`;
  revert em `set_attendance_status` e `close_stale_attendances`; init do schema
  do contato.
- `main.py`: grava no `wa_assume_contact`; atualiza no `admin_reassign_lead`.
- `frontend/src/types.ts`: campos no tipo `Contact`.
- Commits `45f5fb9` (feat) e `903cfbb` (fix — revert da conversa). Revisoes
  Cloud Run `castro-crm-00146` e `00148`. Validado E2E em prod.
