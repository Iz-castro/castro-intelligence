# ADR 0007 — Isolamento multi-tenant de `channels` e `pending_webhook_events`

> **Status em 2026-08-21:** **Fase 1 FEITA** (commit `c6ba72f`, 2026-07-01): filtro
> por tenant em `get_all_active_channels`/`get_channels_for_user`,
> `_default_channel_id` virou `dict[tenant_id, channel_id]`
> ([channel_service.py:53](../../channel_service.py#L53)) e `enqueue_pending_event`
> passou a usar **auto-id do Firestore** ([pending_events.py:60-66](../../pending_events.py#L60))
> — riscos 1, 2 e 3 fechados. Prod roda com **3 tenants** desde 2026-07-28.
> **Fase 2 (migrar `channels` para `tenants/{tid}/channels`) NÃO foi feita e hoje
> colide com um invariante:** `channels` e `pending_webhook_events` passaram a
> integrar `_GLOBAL_COLLECTIONS` (commits `073e1d0` e `c233ed1`, 2026-07-16) —
> tirar `channels` de lá foi a **causa raiz** da perda crônica de mensagens (refresh
> sob contexto de tenant montava cache vazio → `no_channel` por ~60s). Reabrir a
> Fase 2 exige desenho novo que preserve a resolução do webhook ANTES de o tenant
> ser conhecido (⚠ decisão do PO). O item "auditar consumidores de `channel_id`
> global" virou incidente real em 2026-07-16 (colisão de `channel_id` entre
> tenants): o contador agora é `next_sequence("channels", tenant_id="")` — string
> **vazia**, nunca `None`.

- **Status:** Proposed (aguardando priorizacao — recomendado resolver antes do 2o tenant)
- **Data:** 2026-06-03
- **Autores:** Rafa + Claude (investigacao do codigo + travessia do Firestore de producao)
- **Relacionado:** roteamento de colecoes [firestore_common.py:41](../../firestore_common.py#L41);
  registry de canais [channel_service.py:23](../../channel_service.py#L23);
  fila de eventos [pending_events.py:13](../../pending_events.py#L13);
  resolucao de tenant no webhook [webhook.py:44](../../webhook.py#L44);
  endpoint [main.py:2179](../../main.py#L2179);
  ADR [0002](0002-lgpd-canal-coex-compartilhado.md) (canal coex compartilhado);
  [docs/architecture/FIREBASE_ARCHITECTURE.md:142](../../docs/architecture/FIREBASE_ARCHITECTURE.md#L142).

## Contexto

Travessia do Firestore de producao (2026-06-03) confirmou que duas colecoes
estao **flat top-level**, fora do padrao `tenants/{tenant_id}/...`:

- `castro_crm_channels` — 8 docs.
- `castro_crm_pending_webhook_events` — 211 docs.

Hoje ha **1 tenant operacional** (`hubloc`), entao nada quebra. A diretriz do
CLAUDE.md (secao 2.6) exige isolamento **estrutural por path**, nao filtro
logico. Esta ADR avalia se cada colecao e flat por **gap** ou por **design**,
e o que precisa mudar antes do onboarding do 2o tenant.

Nota de roteamento: nenhuma das duas esta em
`_GLOBAL_COLLECTIONS = {"_meta", "tenants", "phone_routing"}`
([firestore_common.py:41](../../firestore_common.py#L41)) — elas ficam flat
por **import explicito** de `_flat_collection`/`global_collection`, nao por
serem marcadas como globais.
(⚠ Estado de 2026-06-03. Desde 2026-07-16 **ambas estao** em
`_GLOBAL_COLLECTIONS`, junto de `super_admins` e `audit_logs_system` — ver banner.)

## Veredito por colecao

### `pending_webhook_events` → flat por DESIGN LEGITIMO (manter)

A fila existe justamente para a janela em que o `tenant_id` **ainda nao e
conhecivel**: o webhook da Meta chega so com `phone_number_id`, e o evento e
enfileirado exatamente quando o canal/tenant nao pode ser resolvido
(`no_channel_for_phone`, `coex_no_owner`, excecao nao tratada). Forcar para
`tenants/{tid}/...` seria impossivel — o tenant ainda nao existe. Justificativa
documentada em [pending_events.py:13-15](../../pending_events.py#L13-L15); doc
carrega `phone_number_id` (chave para resolver depois), nao `tenant_id`; escrita
via `global_document` ([pending_events.py:75](../../pending_events.py#L75)).

**Manter flat.** Porem ha um **bug latente de contador** a corrigir antes do 2o
tenant: `enqueue_pending_event` chama
`next_sequence("pending_webhook_events")` **sem** `tenant_id`
([pending_events.py:62](../../pending_events.py#L62)). Como `next_sequence` le o
contextvar quando `tenant_id is None`
([firestore_common.py:237-240](../../firestore_common.py#L237-L240)) e o webhook
**ja chamou `set_tenant_context`** antes ([webhook.py:273](../../webhook.py#L273)),
o contador do id vai para `tenants/{tid}/_meta/counters` enquanto o **documento**
e escrito na colecao flat ([pending_events.py:75](../../pending_events.py#L75)).
Com 2+ tenants, o tenant B comeca seu contador do zero e gera `event_id=1`,
sobrescrevendo o doc `castro_crm_pending_webhook_events/1` do tenant A
(**colisao de doc id**, ultimo escrito vence).
- **Correcao recomendada:** usar **auto-id do Firestore (UUID)** para o doc de
  `pending_webhook_events`, eliminando a dependencia de contador. (Passar
  `tenant_id=None` nao resolve — `None` cai no contextvar; seria preciso um
  sentinel ou escrever direto no `_flat_document("_meta","counters")`.)

### `channels` → flat por DESIGN INTENCIONAL, mas com GAP de isolamento na leitura admin

Manter `channels` flat e intencional e documentado
([channel_service.py:31-35](../../channel_service.py#L31-L35);
[FIREBASE_ARCHITECTURE.md:142-150](../../docs/architecture/FIREBASE_ARCHITECTURE.md#L142-L150)),
e e mitigado para o **fluxo de webhook** pelo indice global `phone_routing`. O
problema nao e o webhook — e o **fluxo de leitura administrativa**, que nao
respeita o tenant, apesar de cada canal **carregar `tenant_id`**
([channel_service.py:263](../../channel_service.py#L263)).

## Isolamento de `channels` hoje

| Fluxo | Isolamento | Mecanismo / evidencia |
|---|---|---|
| Webhook (escrita de mensagens/contatos) | **Estrutural (seguro)** | `phone_routing[phone_id] → tenant_id` ([webhook.py:44-64](../../webhook.py#L44-L64)) → `set_tenant_context` ([webhook.py:273](../../webhook.py#L273)) → wa_* caem em `tenants/{tid}/...` |
| Leitura do registry `channels` | **Logico e incompleto** | `refresh_channels` faz `.stream()` sem `where(tenant_id)` ([channel_service.py:63](../../channel_service.py#L63)); `get_channels_for_user` filtra so por `channel_type`/`owner_user_id` ([channel_service.py:138-152](../../channel_service.py#L138-L152)) |
| `GET /api/admin/channels` (admin/supervisor) | **Ausente** | `get_all_active_channels()` retorna o cache inteiro ([channel_service.py:131-135](../../channel_service.py#L131-L135), [main.py:2181-2182](../../main.py#L2181-L2182)) |

`phone_routing` mitiga **apenas o roteamento inbound** (O(1) no webhook). Ele
**nao** protege a leitura do registry — `refresh_channels`/`get_all_active_channels`
leem `channels` direto, sem consultar `phone_routing`. `phone_routing` e e deve
continuar global por design.

## Riscos concretos no 2o tenant

1. **Cross-tenant READ (alta):** admin/supervisor do tenant A em
   `GET /api/admin/channels` recebe **todos** os canais, de todos os tenants.
   `access_token` e removido ([main.py:2189](../../main.py#L2189)), mas vazam
   `waba_id`, `phone_number_id`, `verified_name`, `owner_user_id` e `tenant_id`
   do tenant B. **Exposicao cross-tenant — viola CLAUDE.md secao 2.6.**
2. **Default cross-tenant (alta gravidade):** `_default_channel_id` e o **primeiro
   canal `standard` ativo do cache global** ([channel_service.py:83-84](../../channel_service.py#L83-L84)),
   nao por tenant. Com 2 tenants, um envio sem `channel_id` explicito pode sair
   pela **WABA do outro tenant** (cross-tenant **WRITE**, gravissimo).
3. **Colisao de `event_id`** em `pending_webhook_events` (descrito acima).
4. **Colisao de `phone_number_id`** (baixa): cache `_channels_by_phone_id` e
   `get_channel_by_phone_id_from_db` ([channel_service.py:424](../../channel_service.py#L424))
   chaveiam so por `phone_number_id`. Cada numero e unico na Meta, entao improvavel,
   mas o codigo nao impede.

## Plano

### Fase 1 — Minimo para destravar o 2o tenant com seguranca (baixo esforco, NAO migra paths)
Como o doc de canal **ja tem `tenant_id`**, basta filtrar por
`get_tenant_context()` (o middleware ja seta por request via custom claim):
- Filtro de tenant em `get_all_active_channels` ([channel_service.py:131-135](../../channel_service.py#L131-L135))
  e `get_channels_for_user` ([channel_service.py:138-152](../../channel_service.py#L138-L152)).
- `_default_channel_id` por tenant: trocar o `int` global por `dict[tenant_id, channel_id]`
  ([channel_service.py:49,83-84](../../channel_service.py#L49)).
- Auto-id (UUID) em `enqueue_pending_event` ([pending_events.py:62](../../pending_events.py#L62)).

Isso elimina os riscos 1, 2 e 3. **E filtro logico — explicitamente uma
mitigacao temporaria**, contraria a diretriz de isolamento estrutural; por isso
existe a Fase 2.

### Fase 2 — Migracao estrutural `channels → tenants/{tid}/channels` (alinha ao CLAUDE.md)
- **Pre-requisito:** garantir `phone_routing` populado para os 8 docs (backfill
  `upsert_phone_routing(phone_id, tenant_id, channel_id)`), senao o webhook quebra.
- Trocar o import flat ([channel_service.py:23-25](../../channel_service.py#L23-L25))
  por `collection`/`document` roteados por contexto, **e** refatorar o cache em
  memoria de global para **por tenant** (`_channels_by_id` →
  `dict[tenant_id, dict[channel_id, ...]]`) — senao recai no problema que o
  comentario [channel_service.py:31-35](../../channel_service.py#L31-L35) evita.
- Migrar os 8 docs **preservando `channel_id`** (threads sao `{channel_id}__{wa_id}`,
  [channel_service.py:474](../../channel_service.py#L474) — mudar o id duplicaria
  conversas). Semear o contador `tenants/{tid}/_meta/counters.channels` com
  `max(channel_id)+1` do tenant. Atencao: com ids por tenant, dois tenants terao
  `channels/1` (ok estruturalmente, mas auditar quem assume `channel_id` global —
  `phone_routing.channel_id`, refs em `wa_conversations`).
- **`phone_routing` permanece global e inalterado.** Nao migrar.
- Nao deletar os docs flat ate validar (rollback).

## Severidade / urgencia

- **`channels` cross-tenant READ + default global: BLOQUEANTE para o 2o tenant.**
  Dispara na primeira request admin / primeiro envio sem `channel_id`. Nao e teorico.
- **Fase 1 destrava com baixo esforco** e fecha os riscos 1-3 sem migrar paths.
- **Fase 2 e alta urgencia, nao bloqueante imediata** se a Fase 1 for aplicada;
  e o cumprimento pleno do isolamento estrutural. Agendar junto do onboarding.
- **`pending_webhook_events`: nao migrar** (design correto); so corrigir o id.
- **`phone_routing`: nenhuma acao** — global por design e correto.

## Consequencias

### Positivas
- Fecha exposicao cross-tenant de metadados de canal (LGPD secao 2.6) e o risco de
  envio pela WABA errada antes que o 2o tenant exista.
- Fase 1 e barata e reversivel; Fase 2 cumpre a diretriz de isolamento estrutural.

### Negativas / atencao
- Fase 1 introduz **filtro logico** (debito tecnico assumido conscientemente ate
  a Fase 2).
- Fase 2 exige refatorar o cache para por-tenant e migracao de dados com
  preservacao de `channel_id` — risco de quebrar threads/`phone_routing` se mal feito.
- O `access_token` ja vive no **cache em memoria** global de
  `get_all_active_channels`/`get_send_credentials` — a Fase 1 nao o isola do
  processo, so impede o vazamento via API; a Fase 2 (cache por tenant) e que
  resolve isso de fato.

## Itens dependentes (fora do escopo desta ADR)
- Script de migracao idempotente dos 8 docs + seed dos contadores por tenant.
- Auditar todos os consumidores de `channel_id` que assumem unicidade global.
- Backfill/validacao de `phone_routing` para canais antigos.
