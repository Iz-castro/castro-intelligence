# Contexto pra retomar — Coexistence completo + contact picker com agenda do telefone

> **Adendo 2026-05-21:** WABA mismatch em `/api/wa/send-template`
> (Meta #132001) **resolvido e deployado** (commit `577b74a`, revisão
> `castro-crm-00105-954`). Backend valida template por-WABA antes da Meta
> (guard 422); frontend lista templates pela WABA do canal da thread. O
> "template do Izael não aparece" reportado depois **não era bug** — era
> status `PENDING` na WABA do canal 3 (a Meta aprovou e funcionou).
> Aprendizado: aprovação de template é **por-WABA**. Detalhe em
> [2026-05-21.md](2026-05-21.md); diag `scripts/_diag_templates_by_waba.py`.
>
> **Snapshot atualizado em 2026-05-19.** Dia de incidente+remediação
> em prod: isolamento por operador (#2), fix transferência (#3), surto
> de duplicatas do `state_sync`, e 429 de capacidade no Cloud Run.
>
> **Estado de prod (fim 2026-05-19):**
> - **Fase 2 rules estritas: DEPLOYADAS em prod e VALIDADAS** (gerencia
>   e izael admins OK; teste1 operador escopado). A
>   `firestore-rules-staging-strict.wip` foi portada e aplicada.
> - Duplicatas: **resolvidas** — `upsert_wa_contact` agora get-or-create
>   atômico (`wa_contact_index` + `.create()`), provado em prod.
> - `state_sync` de canal coexistence agora **atribui ao dono** (LGPD);
>   órfãos legados backfillados → `gerencia`. Pool vazio.
> - Capacidade: Cloud Run `maxScale 40`/`concurrency 8` + webhook
>   `state_sync` em threadpool + frontend single-flight.
> - **Firestore PITR habilitado** (7 dias).
>
> ⏳ **PENDENTE p/ próxima onda da Meta (amanhã):** provar
> `state_sync→dono` e ausência de 429 (runbook em
> [2026-05-19.md](2026-05-19.md) §6). ⚠️ O dedupe de 634 contatos foi
> **irreversível por log** (bug já corrigido) — rollback só via PITR.
>
> **Leia primeiro [2026-05-21.md](2026-05-21.md)** (sessão mais recente,
> fix do WABA mismatch + causa-raiz do template PENDING), depois
> [2026-05-19.md](2026-05-19.md) (incidente+remediação, runbook das
> verificações pendentes e rollbacks), depois
> [2026-05-11.md](2026-05-11.md), [2026-05-09.md](2026-05-09.md),
> [2026-05-08.md](2026-05-08.md) §5, [2026-05-06.md](2026-05-06.md),
> [2026-05-05.md](2026-05-05.md) pra detalhe cronológico, ou
> [PLANO_COEXISTENCE_REFATORACAO.md](../PLANO_COEXISTENCE_REFATORACAO.md)
> pra detalhe arquitetural. Histórico anterior preservado abaixo.

## Sessao 2026-05-11 — Contact picker com agenda do telefone

**Problema:** `smb_app_state_sync` sincronizava 160 contatos da agenda
e o `upsert_wa_contact` cascateava em `upsert_wa_conversation` criando
155 conversations VAZIAS com `last_message_at=now`. Sidebar (orderBy
last_message_at desc + limit 50) empurrava as 5 reais do history pra
fora da janela.

**Fixes (commit `c4c9632`):**
- `upsert_wa_contact` aceita `from_message_event=False` — state_sync
  agora cria contato sem conversation e sem `last_message_at`
- Backfill ja executado em prod: 155 convs vazias deletadas, 155
  contatos com `last_message_at` zerado
- Endpoint `GET /api/wa/contacts/all?q=` lista todos os contatos
  ordenados alfabeticamente (independente do snapshot de 50)
- Endpoint `POST /api/wa/conversation/open` materializa conversation
  on-demand quando operador clica num contato da agenda
- Modal `NewContactModal` reformulado: header "Total de contatos (N)" +
  busca + lista alfabetica + botao "+ Novo contato" (que abre o form
  original)
- Botao `+` virou icone de agenda (`AddressBookIcon`)
- Sidebar header ganha sub-linha "Y contatos cadastrados"
- Cache em memoria do contact picker (sem localStorage — LGPD-safe).
  Pre-aquecido pelo effect do `ContactList`, busca filtra local
- Fix race condition do auto-select: insercao otimista da conversation
  no estado antes do `setSelectedThreadId` (sem isso o effect resetava
  a selecao pra primeira conv ate o snapshot Firestore propagar)

**Revisao prod ativa apos hoje:** `castro-crm-00090-bmb`.

Ver detalhes em [2026-05-11.md](2026-05-11.md).

## Sessao 2026-05-09 — History sync + bugs conversation_id

Snapshot anterior (2026-05-09 madrugada do dia 10) após sessão longa
que (a) achou e fixou 5 bugs reais no caminho de
`conversation_id`, (b) introduziu sistema novo `pending_webhook_events`
pra zero perda, (c) wipe + reonboarding coex em prod, (d) cleanup
de 3 perms não-usadas na Meta + republish, (e) **descobriu gap
crítico: history sync precisava de `POST /smb_app_data` explícito**
— implementado auto-trigger no signup + endpoint admin de retrigger,
(f) ordenação de mensagens migrou de `created_at` pra `timestamp_wa`
(real), (g) **history sincronizou com sucesso: 7 contatos + 56
mensagens importadas e exibindo cronologicamente certas no CRM**.

## Onde paramos

**App Review aprovado e cleanup feito em 2026-05-09:**
- ✅ `whatsapp_business_messaging` — Advanced Access (5/8)
- ✅ `whatsapp_business_management` — Advanced Access (5/8)
- ✅ `public_profile` — renovada (5/8)
- 🧹 Removidas no painel Meta em 5/9 (não usadas): `business_management`
  (Ads Manager — reprovada), `manage_app_solution` (Solution Partners),
  `whatsapp_business_manage_events` (Conversions API)
- ✅ App republicado em 5/9 — Meta aceitou. Não precisa nova App
  Review pra manter o que já tem.

**App Live em prod desde 2026-05-08.** Embedded Signup, send/receive,
templates — tudo destravado pra clientes externos.

**Coexistence end-to-end validado em prod (2026-05-09):**
- Mensagem mandada do app celular aparece no CRM via
  `smb_message_echoes` ✓ (com `operator_id` populado, label "Equipe")
- Resposta do CRM chega no celular do cliente ✓ (delivered)
- Inbound do cliente chega no CRM via `messages` ✓
- Canal coex (id=1, WABA `680503338460083`, phone `1055982807598158`,
  "Izael Castro - +55 31 7195-7758") ativo, owner=2 (izael)
- Webhook subscription confirmada via `GET /{waba}/subscribed_apps`
  (resposta direta da Meta lista nosso app + URL do CRM)

**Revision prod ativa:** `castro-crm-00090-bmb` em 100% (sessao de 5/11
fez 3 deploys: `00088-f5r` → `00089-n5m` → `00090-bmb`; sessao de 5/9
tinha fechado em `00087-mkc`).

**5 bugs reais do `conversation_id` fixados em 2026-05-09** (ver
[2026-05-09.md §1-2](2026-05-09.md)):
1. `_make_conversation_id` falha-loud sem `channel_id`/`wa_id` (em vez
   de gerar `default__{wa_id}` órfão)
2. `save_wa_message` propaga `ConversationIdError` (sem mais salvar
   `conversation_id=None` silencioso)
3. `upsert_wa_contact` canoniza `wa_id` pra forma 13-dig com 9 quando
   acha contato via variante (12-dig)
4. `_process_history` normaliza phones em `business_phone`/`msg_from`/
   `msg_to` antes de calcular `is_outbound`
5. `get_wa_conversation` aceita `conversation_id` opcional pra
   preservar isolamento de canais no fallback legado
6. **Bonus:** `operator_id = channel_owner_user_id` em `smb_echoes` e
   history outbound — frontend para de mostrar "Bot" no echo do app.

**Sistema novo `pending_webhook_events`** ([pending_events.py](../../pending_events.py)):
fila global para webhooks da Meta que não puderam ser processados
imediatamente (canal não indexado durante onboarding, exception no
processamento). Webhook entrypoint nunca propaga 5xx pra Meta. 4
endpoints admin novos:
- `GET /api/admin/pending-webhook-events?status=pending`
- `POST /api/admin/pending-webhook-events/{id}/retry`
- `POST /api/admin/pending-webhook-events/{id}/dismiss`
- `DELETE /api/admin/pending-webhook-events/{id}`

UI da fila ainda **não foi feita** — endpoints prontos pra consumir.

**Wipe Firestore prod feito manualmente em 5/9** (Rafa apagou todas as
coleções pelo console). Reonboarding coex via Embedded Signup gerou:
- 1 contato + 1 conversation + 4 mensagens (testes manuais)
- users/operator_profiles/departments/audit_log recriados em
  `tenants/hubloc/...` no primeiro acesso

**Índices Firestore reduzidos de 19 → 9** ([firestore.indexes.json](../../firestore.indexes.json)):
removidos 12 índices flat legados (`castro_crm_*`, `castro_crm_staging_*`)
da era pré-Fase 2. Mantidos só os 9 `COLLECTION_GROUP` ativos
(`wa_conversations`, `wa_messages`, `wa_contacts`, `wa_transfer_log`).
Deploy: `firebase deploy --only firestore:indexes --force`.

**Token .env rotacionado em 5/9 + Secret Manager v26.** Canal coex usa
token próprio do Firestore (do signup), não afetado. Recomendado
rotacionar de novo (token foi exposto no chat).

**4 bugs adicionais fixados em 2026-05-08** (contexto histórico, ver
[2026-05-08.md §5](2026-05-08.md)):
1. `firestore.rules` prod sem rule pra `castro_crm_tenants`
2. `_process_messages` não normalizava `wa_id` BR (nono dígito)
3. `httpx.ReadTimeout` em `subscribe_apps` abortando signup
4. `get_send_credentials` caía em fallback default com cache stale

**Screencast App Review:** Meta reprovou em 5/8 ("não demonstra
experiência completa do caso de uso"). Refazer cobrindo as 2 perms
aprovadas continua na lista. Roteiro pronto em
[`docs/APP_REVIEW_SCREENCAST_SCRIPT.md`](../APP_REVIEW_SCREENCAST_SCRIPT.md).
**Não bloqueia operação** — app está Live e funcional, perms aprovadas.
Sem follow-up exigindo screencast novo após o cleanup/republish de 5/9.

Código já limpo: `business_management` removida da tupla de detection
em `main.py` (era fallback redundante) e neutralizada em
`test_meta_app_review.py`. Configurador da Meta (referenciado por
`EMBEDDED_SIGNUP_CONFIG_ID`) **precisa** ser revisado no painel
business.facebook.com pra remover `business_management` se estiver
solicitando — ver §5 do roteiro do screencast.

**Backend essencialmente fechado.** Fase 2C cutover + Fase 3 frontend
+ Fase 2.10.3 (cron health com OIDC + Secret Manager) + Fase 2.10.4
(usage per-tenant) + Auditoria LGPD logs + Fase 4 prep (wipe script
+ runbook prod) — todos validados em staging. **Pendência menor:
Firestore rules estritas em staging (frente WIP — 4ª da fila do
"fechar backend").** WIP preservado em
[`firestore-rules-staging-strict.wip`](firestore-rules-staging-strict.wip).
Rules permissivas restauradas no Firebase pra não bloquear staging.

15 commits acima do snapshot anterior (`022a6b0` → `78234f7`).

```
78234f7 feat(fase2.10.3): cron auth via OIDC + Secret Manager (staging migrado)
578f8c4 feat(fase4):      wipe_all_collections.py + runbook cutover prod
52c0ae5 feat(lgpd):       redact PII em logs (telefone, nome, secret)
c7c4716 docs(internal):   RETOMAR + diario 2026-05-05 cobrindo fase 2.10.3 + scheduler
11e299b feat(fase2.10.3): cron health-check + endpoint + e2e passo 9
08c0753 feat(fase2.10):   usage_{YYYY_MM} per-tenant + endpoints + e2e passo 8
d0367fd feat(fase3.D):    filtros novos/meus/NQ/equipe operam sobre conversations
235fe03 fix(fase3):       badges *Unread agregam por conversation, nao por contato
d045ee1 fix(fase3):       mark-read zera unread da thread + contato manual ganha conversation
9d1b66c feat(fase3):      selectedThreadId vira fonte unica de selecao
fb8eef6 test(fase2c):     e2e cobre POST /conversation/{id}/read e /send com conv invalida
e50a9fc docs:             corrige diario 2026-05-04 e regera SISTEMA_COMPLETO
2f93040 chore(docs):      remove references a docs arquivados
c67444b feat(fase2c):     phone_routing ativo no webhook
6cd4891 feat(fase2c):     endpoints de envio aceitam conversation_id
dcd27ba feat(fase2c):     wa_messages ganham channel_owner_user_id + sender_user_id
```

**Staging:** revision `castro-crm-staging-00028-qbn` em 100% do tráfego.
Service URL: https://castro-crm-staging-286866630844.southamerica-east1.run.app

**Cloud Scheduler em staging:** criado e validado, **migrado pra OIDC
+ Secret Manager**. Job `castro-crm-staging-health-check` em
`southamerica-east1`, schedule `0 9 * * *` (09:00 BRT diário). Auth
via OIDC token assinado pela SA dedicada
`castro-crm-scheduler@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com`
(`roles/run.invoker` no Cloud Run). `INTERNAL_CRON_SECRET` agora vem do
Secret Manager (`castro-crm-internal-cron-secret:latest`) — fallback
pra e2e/CI que continuam usando header `X-Cron-Secret`. Backend aceita
ambos via `_verify_cron_auth` (precedence: OIDC primeiro).

**Produção:** revision `castro-crm-00082-tm6` ativa (deploy de hoje
com cleanup business_management + fix nono dígito + fix httpx timeout
+ fix get_send_credentials). Cutover Fase 4 **executado parcialmente
hoje** (wipe tenant hubloc preservando users/audit_log + reonboarding
canal coex via Embedded Signup com Advanced Access). Cloud Scheduler
prod **ainda não criado** — comandos OIDC + Secret Manager
documentados em `docs/deploy/RUNBOOK_CUTOVER_PROD.md` §6.

---

## Status do Plano Coexistence — o que falta

Referência: [PLANO_COEXISTENCE_REFATORACAO.md](../PLANO_COEXISTENCE_REFATORACAO.md).

### Fase 1 — Embed Signup Fixes ✅ Concluída e validada
- 1.1-1.6 todas as fixes do plano original ✓
- **+ 4 bugs adicionais fixados em 2026-05-08** (nono dígito BR, httpx
  timeout no subscribe_apps, channel resolution stale, firestore.rules
  prod). Embedded Signup completou end-to-end em prod com sucesso.

### Fase 2 — Multi-Tenant + Sub-Threads (Backend) ✅ Concluída
- 2.1 Modelo Firestore subcoleções `tenants/{tid}/*` ✓
- 2.2 helpers `tenant_path/tenant_collection/tenant_document` ✓
- 2.3 `database_firestore.py` refatorado com `tenant_id` ✓
- 2.4 endpoints com `conversation_id` canônico ✓
- 2.5 webhook multi-tenant + `phone_routing` global ✓
- 2.6 `bot_service` per-conversation ✓
- 2.7 Firebase Auth custom claims (`tenant_id`, `role`) ✓
- 2.8 `firestore.indexes.json` ✓
- **2.9 `firestore.rules` ⚠️ PARCIAL** — permissivas via `emailAllowed()`
  em prod e staging. Rules estritas via custom claim `tenant_id` foram
  WIP em staging mas falhavam no snapshot `wa_messages`; preservadas em
  [`firestore-rules-staging-strict.wip`](firestore-rules-staging-strict.wip).
  Investigação retomada **só após** estabilizar fluxo principal.
- 2.10 Billing & Onboarding awareness:
  - 2.10.1 `GET /api/wa/channel/{id}/billing-status` ✓
  - 2.10.2 tradução erros Meta → 402 ✓ (commit `b15268a`)
  - 2.10.3 Cron health-check ✓ em staging (OIDC + Secret Manager).
    **Pendente: criar Cloud Scheduler em prod** (mesmo pattern, comandos
    em `RUNBOOK_CUTOVER_PROD.md` §6).
  - 2.10.4 `usage_{YYYY_MM}` per-tenant + endpoints ✓

### Fase 3 — Frontend ⚠️ PARCIAL
- 3.1-3.4 backend mudanças refletidas no frontend (types, context,
  App.tsx, normalization) ✓
- **3.5 Onboarding & Billing UI ⚠️ FALTA quase tudo:**
  - `<BillingHealthBanner/>` — **parcial** (versão básica existe; falta
    o `<TenantHealthBanner/>` mais informativo lendo
    `tenants/{tid}/health_status` via snapshot)
  - **`/setup` checklist (admin) — FALTA** (CONTA / WHATSAPP /
    PAGAMENTO / OPERADORES / TEMPLATES com tooltips e estados)
  - **Modal de erro 402 no envio de template — FALTA** (link pro
    Business Manager Meta)
  - **Card "Uso este mês" no dashboard — FALTA** (consome
    `GET /api/wa/usage/current-month`)
  - **Gráfico histórico (opcional) — FALTA** (consome
    `/api/wa/usage/history?months=6`)
  - Frontend passa `template_category` em send-template — **FALTA**
    (backend já aceita; basta repassar do `/api/wa/templates`)

### Fase 4 — Wipe + Validação End-to-End ⚠️ EM ANDAMENTO
- 1. Deploy staging ✓
- 2. Validação staging (e2e 9/9 PASSED) ✓
- 3. Deploy prod ✓ (`00085-qxp` em 5/9 com fixes do conversation_id +
  fila pending + operator_id em smb_echoes)
- 4. **Wipe Firestore prod ✓ refeito em 5/9** — Rafa apagou todas as
  coleções pelo console. Re-bootstrap automático criou
  `tenants/hubloc/users` (2), `operator_profiles` (2), `departments`
  (4), `audit_log` (94 LOGIN_SUCCESS) na primeira sessão.
- 5. Bootstrap tenant hubloc ✓ (recriado pelo primeiro acesso)
- 6. Reonboarding canal coex via Embedded Signup ✓ em 5/9 (canal #1,
  WABA `680503338460083`, "Izael Castro - +55 31 7195-7758",
  owner_user_id=2). Verificação direta na Meta:
  `GET /{waba}/subscribed_apps` retorna nosso app.
- **6.b Validações end-to-end:**
  - ✅ Mensagem inbound webhook → conversation (validado 5/9)
  - ✅ `_resolve_channel_creds` usa `conversation.channel_id` (5/8)
  - ✅ smb_echo do app celular → CRM (5/9)
  - ✅ Resposta do CRM → cliente (delivered, 5/9)
  - ⏸️ Mesmo wa_id em standard + coex como 2 entradas distintas (prod
    tem só coex; standard #2 existe mas é canal legado sem uso real)
  - ⏸️ Bulk reassign exclui canais coex onde owner=user X
  - ⏸️ UI badge de canal correto em cada linha
  - ⏸️ Painel de perfil unificado (mesmo cliente em múltiplas threads)
  - ⏸️ Auditoria `sender_user_id != channel_owner_user_id` em
    transferência real
  - ⏸️ Isolamento multi-tenant (rules + backend filter) — rules
    permissivas via `emailAllowed`; depende de 2.9.
- 7. **History sync via webhook `history` ✅ FUNCIONOU em 2026-05-09** —
  signup foi 02:21:42 UTC. Descoberto tarde na sessão que
  `POST /{phone_id}/smb_app_data` precisa ser chamado explicitamente
  (não é assíncrono "Meta entrega quando quiser"). Disparo manual em
  ~03:30 UTC; webhook `[HISTORY]` chegou em <5min e completou em
  ~3min: 5 threads, 56 mensagens, fases 0/1/2 todas com
  `progress=100%`. `audit_log/history_sync_complete` registrado.

  **Auto-trigger** agora roda no `embedded_signup_exchange` em
  [main.py](../../main.py) pra signups futuros, e há endpoint admin
  `POST /api/admin/channels/{id}/trigger-coex-sync?sync_type=both`
  pra repair manual dentro da janela de 24h.

  **Mensagens ordenadas cronologicamente** via `timestamp_wa` (não
  `created_at`) tanto no backend quanto no frontend
  ([CrmContext.tsx:837](../../frontend/src/context/CrmContext.tsx#L837),
  [database_firestore.py:1320](../../database_firestore.py#L1320)).
  Índices Firestore atualizados: `wa_messages` agora tem
  `conversation_id+timestamp_wa` e `contact_id+timestamp_wa`.

### Pós-Fase 4 / Roadmap futuro

Itens registrados no plano que ficam pra depois:
- Onboarding self-service de novo tenant (super-admin UI)
- Self-service signup cliente (landing → cartão → tenant criado)
- Billing automation (Stripe/Asaas/Iugu pra mensalidade SaaS)
- White-label (sub-domínio próprio do tenant)
- Cross-tenant analytics (super-admin Castro Intelligence)
- Backup/export per-tenant (recursive export pra compliance LGPD)
- Limites enforced por plano (Starter 5k msg/mês com block)
- UI dedicada "Importar últimos 6 meses" (já que `history` webhook
  funciona, falta só apresentar pro usuário)

### Pendências operacionais (fora do plano)
- **`bootstrap_default_channel` recria canal #N standard a cada deploy**
  (lê `WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_WABA_ID` env). Em prod 5/9
  recriou canal #2 "Canal Principal" com WABA `1633469507697155`. Não
  é usado pelo coex e gera 401 spam ao buscar billing-status. Solução:
  `gcloud run services update castro-crm
   --remove-env-vars=WHATSAPP_PHONE_NUMBER_ID,WHATSAPP_WABA_ID`.
- **UI exibe `WHATSAPP_TOKEN` em texto** no modal "Conexão realizada"
  ("Atualize o .env do servidor com os novos valores") — resíduo
  single-tenant. Token vai pro Firestore registry. Substituir por
  "Token salvo. Canal pronto."
- **SA prod sem permissão IAM `auth.get_user`** → spam de
  `INSUFFICIENT_PERMISSION` em logs. Adicionar role
  `roles/firebase.admin` ou similar.
- **Frontend faz polling agressivo em `/api/wa/channel/{id}/billing-status`**
  (~1 req/s). Deveria ter backoff em erro repetido.
- **`next_sequence("channels")` reusa IDs em alguns cenários** (task
  #52). Risco baixo agora, mas corrigir antes de cliente #2.
- **🆕 (5/9) "Equipe" deveria mostrar nome do operador.** Frontend
  ([formatting.ts:35](../../frontend/src/utils/formatting.ts#L35)) usa
  `message.operator_name` antes de cair em "Equipe". `_user_map` em
  [database_firestore.py:1326-1336](../../database_firestore.py#L1326-L1336)
  provavelmente não acha users que vivem em `tenants/{tid}/users`
  (subcoleção). Bug cosmético, não bloqueia uso.
- **🆕 (5/9) `WHATSAPP_TOKEN` foi exposto no chat** durante a sessão
  de hoje. Recomendado rotacionar de novo + atualizar Secret Manager.
  Considerar adicionar `.env` ao `.gitignore`.

---

## Validação — todos os 9 passos do e2e PASSED

`scripts/e2e_test_staging.py` foi estendido com 4 passos novos
(cutover 2C + usage 2.10.4 + cron health 2.10.3):

1. Wipe tenant hubloc + canais fake (também limpa `usage_{YYYY_MM}` corrente)
2. Cria 2 canais fake (id=100 standard, id=200 coexistence)
3. Aguarda 70s pra cache reciclar
4. Dispara 4 webhooks Meta-shape
5. Valida estado: 2 contatos, 3 conversations, 4 mensagens
6. **Loga como BOOTSTRAP_ADMIN_EMAIL via custom token assinado pela SA do
   Cloud Run** (e2e_signer app), troca por idToken via signInWithCustomToken.
   POST `/api/wa/conversation/100__<wa_x>/read` zera unread só dessa thread;
   threads `200__X` e `200__Y` mantém unread; mensagens inbound da thread
   100 viram `status=read`.
7. POST `/api/wa/send` com `conversation_id="9999__inexistente"` → 404
   (prova que `_resolve_send_target` rejeita antes de Meta). Sem target
   → 400.
8. **Valida `usage_{YYYY_MM}` per-tenant (Fase 2.10.4):** lê
   `tenants/hubloc/audit_metrics/usage_2026-05` (`inbound_received==4`,
   `month=="2026-05"`) e exercita `GET /api/wa/usage/current-month` —
   confere que o valor da API bate com Firestore.
9. **Cron health-check (Fase 2.10.3):** POST
   `/api/internal/cron/health-check` com header `X-Cron-Secret`. Itera
   tenants ativos, chama Meta Graph API por canal, classifica
   `payment_method_status` (ok/pending/error/expired) e grava agregação
   em `tenants/{tid}/health_status/current` (+ flat
   `channels.{id}.payment_method_status`). Valida que o doc do hubloc
   tem `channels_total>=2` e `per_channel` populado. No e2e os 3
   canais ficam como `error` (esperado: tokens fake + canal default
   sem permissão BSP).

## Pré-requisitos pra rodar e2e

**IAM:** `rafaluisc@outlook.com` precisa de `roles/iam.serviceAccountTokenCreator`
em `castro-crm-run@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com`
(já concedido em 2026-05-04). Sem isso, passos 6-7 ficam pulados graciosamente.

**Conta gcloud ativa:** `rafaluisc@outlook.com`. Confirmar antes de qualquer
operação IAM/GCP com `gcloud config get-value account`. (`izaeldecastro@gmail.com`
aparece em algumas configs do Claude Code mas **não** é a conta GCP.)

## O que mudou (resumo técnico)

### Cutover Fase 2C (commits `dcd27ba` → `c67444b`)
Já estava no working tree do RETOMAR anterior — agora consolidado:
- `wa_messages` ganham `channel_owner_user_id` + `sender_user_id`.
- Endpoints de escrita aceitam `conversation_id` (preferencial) ou `contact_id`
  (transitional). `_resolve_send_target` resolve em ponto único.
- Novo `POST /api/wa/conversation/{id}/read` por thread.
- `phone_routing` ativo no webhook (consultado antes do fallback).
- Frontend `buildSendTarget()` prefere `selectedThreadId`.

### Fase 3 frontend (commits `9d1b66c`, `d045ee1`, `235fe03`, `d0367fd`)
- **3.A** [`utils/normalization.ts`](../../frontend/src/utils/normalization.ts)
  ganhou `normalizeConversation()`. `normalizeMessage` ganhou
  `conversation_id`, `sender_user_id`, `channel_owner_user_id`.
- **3.B** [`CrmContext.tsx`](../../frontend/src/context/CrmContext.tsx)
  expõe `contactsById: Map<id, Contact>` (useMemo).
- **3.C** Eliminado `useState selectedContactId`. `selectedThreadId` é
  fonte única; `selectedContactId`/`selectedContact`/`selectedConversation`
  derivados. `setSelectedContactId` removido da API. App.tsx ContactList
  simplificado.
- **3.D** Filtros operam sobre conversations: `novosConversations`,
  `meusConversations`, `nqConversations`, `equipeConversations`,
  `botConversations`. Reduces de unread somam direto das conversations.
  `filteredConversations` substituiu `filteredContacts` no provider.
  App.tsx itera `filteredConversations` direto sem flatMap por contact.

### Fase 2.10.3 cron health-check (commit `11e299b`)
- `_fetch_channel_billing_status(channel_id)` extraído de
  `channel_billing_status` em [`main.py`](../../main.py) — retorna dict
  com `ok=False, error=...` em vez de raise (reusável pelo cron).
- `_compute_tenant_health()` itera `get_all_active_channels()` do
  tenant atual (assume ContextVar setado), paraleliza Graph API calls
  via `asyncio.gather`, classifica `payment_method_status`
  (ok/pending/error/expired), persiste no doc flat de cada canal +
  agrega `tenants/{tid}/health_status/current`.
- `POST /api/internal/cron/health-check` com auth via header
  `X-Cron-Secret` (env `INTERNAL_CRON_SECRET`, comparado timing-safe
  com `hmac.compare_digest`). Itera `list_tenants(active_only=True)`,
  com `tenant_context(tid)` chama compute, grava o doc.
- **Bug pré-existente corrigido em [`tenant_service.py`](../../tenant_service.py):**
  `_last_refresh: float = 0` somado com `time.monotonic()` baixo no
  boot fazia `_needs_refresh` retornar False na primeira chamada,
  deixando cache vazio até passar 60s. Trocado pra `float | None`
  (None força refresh).
- Cloud Scheduler **ainda não criado** — comando `gcloud scheduler
  jobs create` documentado em "Cloud Scheduler — comando de criação".

### Fase 2.10.4 usage tracking per-tenant (commit `08c0753`)
- `database_firestore.py` ganha `increment_usage_metrics` (atômico
  via `firestore.Increment`) gravando em
  `tenants/{tid}/audit_metrics/usage_{YYYY-MM}`:
  - `inbound_received` (+1 inbound)
  - `free_form_sent` (+1 outbound não-template)
  - `templates_sent.{marketing|utility|authentication|unknown}` (+1 outbound template)
  - `media_uploaded_bytes` (+bytes da mídia outbound)
- `save_wa_message` ganha 2 kwargs opcionais: `template_category` e
  `media_size_bytes`. Chama `increment_usage_metrics` fire-and-forget.
- `get_audit_metrics` agora pula docs com prefix `usage_` (não polui
  o dashboard de auditoria diário existente).
- Getters novos: `get_monthly_usage(year_month=None)` e
  `get_usage_history(months=3)`.
- 3 endpoints REST (admin/supervisor):
  - `GET /api/wa/usage/current-month`
  - `GET /api/wa/usage/history?months=N` (1–24)
  - `GET /api/wa/usage/{YYYY-MM}`
- `WaSendTemplateRequest` aceita `template_category` opcional (best-effort
  — frontend já conhece via `/api/wa/templates`).
- `wa_send_media` e `wa_send_audio` passam `media_size_bytes` automático.

### Bugs corrigidos no caminho
1. **Mark-read não zerava unread visível:** `applyConversationReadLocally`
   só atualizava `setContacts`. Fix: aceita `conversationId` opcional e
   atualiza `setConversations` direto (otimista).
2. **Contato manual sem conversation:** `create_manual_wa_contact` criava
   só o contato. Sidebar pós-3.D itera por threads, então contato ficava
   fantasma. Fix: backend chama `upsert_wa_conversation(direction_for_unread=None)`;
   endpoint retorna `conversation_id` determinístico; frontend seleciona direto.
3. **Badges \*Unread com soma stale:** `c.unread` do contato ficava
   stale pós mark-read (backend só zera `conversation.unread_count`).
   Fix: derivar unread do contato como soma das conversations.

## Decisões importantes

- **`selectedThreadId` é a fonte única de seleção.** `selectedContactId`,
  `selectedContact`, `selectedConversation` são todos derivados. Pra
  selecionar algo, sempre `setSelectedThreadId(conversation.id)`.
- **Filtros de view operam por conversation, não por contato.** Mesmo
  `wa_id` em 2 canais aparece como 2 entradas distintas em "Novos" (e
  outras views) se ambas se qualificarem.
- **Caminho feliz `/send` não é testável em staging hoje.** Tokens dos
  canais e2e (id=100/200) são fake; canal "Canal Principal" usa app
  Meta sem permissão BSP (precisa App Review). E2E passo 7 cobre só a
  rejeição interna (404/400 antes de Meta).
- **Janela transitional:** backend ainda aceita `contact_id` em `/send*`,
  e contact ainda mantém `assigned_to`/`unread_count` espelhados. Remover
  só quando frontend estiver 100% sobre threads e nenhum caller interno
  legado restar (rating template do `/qualify` é o que sobrou).

## Próximos passos (em ordem)

### 1. Limpeza operacional rápida (low effort)

- Limpar `WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_WABA_ID` do Cloud Run
  prod pra parar de recriar canal #2 standard a cada deploy:
  ```powershell
  gcloud run services update castro-crm `
    --region=southamerica-east1 --project=project-26fb9c99-8ee9-4179-aef `
    --remove-env-vars=WHATSAPP_PHONE_NUMBER_ID,WHATSAPP_WABA_ID
  ```
- Rotacionar `WHATSAPP_TOKEN` de novo na Meta + atualizar Secret
  Manager (foi exposto no chat de 5/9).
- Adicionar `.env` ao `.gitignore` se ainda não está.

### 2. Bug cosmético — "Equipe" mostrar nome do operador

`_user_map` em `database_firestore.py:1326-1336` não está achando
users que vivem em `tenants/{tid}/users`. Investigar e ajustar
provavelmente fazendo lookup via `_get_doc("users", id)` (que respeita
tenant_context) em vez de query flat. Validar com a mensagem #3 do
teste de 5/9 que está com `operator_id=2`.

### 3. Re-screencast App Review (sem urgência operacional)

App está Live, perms aprovadas, cleanup feito em 5/9 e Meta aceitou
republish — não há follow-up pendente. Mas o screencast reprovado em
5/8 segue como frente preservada. Roteiro pronto em
[APP_REVIEW_SCREENCAST_SCRIPT.md](../APP_REVIEW_SCREENCAST_SCRIPT.md).

**Pré-requisitos atendidos:**
- ✅ App em Live mode
- ✅ Canal coex ativo + funcional + validado end-to-end
- ✅ Token coex válido sem expiração
- ✅ Cleanup de perms não-usadas concluído

**Cenário ideal pra gravar:** abrir nova aba anônima, login admin,
abrir o app WhatsApp Business no celular (coex já confirmado),
preparar 2-3 mensagens com cliente teste pra demonstrar bidirecional +
echo. Estimar 30-45min.

### 0.B Firestore rules estritas em staging — INVESTIGAÇÃO PENDENTE

Ver [`2026-05-06.md` §3.4](2026-05-06.md) pro contexto detalhado do
bug. Resumo:

- Tentativa: substituir `match /castro_crm_staging_tenants/{tid}/{subcol=**}`
  permissivo por rules tenant-scoped via custom claim `tenant_id` no JWT.
- WIP completo (220 linhas) preservado em
  [`firestore-rules-staging-strict.wip`](firestore-rules-staging-strict.wip).
- Fix em `auth.py` (`_resolve_tenant_id` agora usa `get_tenant_context()`
  como fallback) já está no Cloud Run staging revision `00028-qbn`,
  e `set_custom_user_claims` foi rodado manualmente no UID
  `znkzvZTl2kZ4gmg95pHjBLElEjS2` (rafa) — claims persistem
  (`{tenant_id: hubloc, role: admin}` confirmado via Admin SDK).
- **Mas:** `wa_conversations` snapshot funciona com cache local, e
  `wa_messages` snapshot (que faz query `where conversation_id == ...
  orderBy created_at desc limit N`) é negado mesmo em janela anônima.
- Hipóteses não validadas: (a) JWT do client não está atualizando
  apesar de logout/login; (b) interação rules + query com filter +
  orderBy em wa_messages que rules engine recusa; (c) bundle JS
  cached lendo path errado.

**Como retomar:**

```js
// 1. Browser console (F12) na sessão logada:
firebase.auth().currentUser.getIdTokenResult(true).then(r =>
  console.log('claims:', JSON.stringify(r.claims)))

// 2. Se claims OK no JWT, simular query no Firebase Console >
//    Firestore > Rules Playground:
//    Operation: list
//    Path: castro_crm_staging_tenants/hubloc/wa_messages/anyId
//    Authenticated: { tenant_id: 'hubloc', role: 'admin' }
//    Query: where conversation_id == "100__5531777771111" orderBy created_at desc

// 3. Restaurar rules WIP (quando preparado pra testar de novo):
//    cp docs/internal/firestore-rules-staging-strict.wip firestore.rules
//    firebase deploy --only firestore:rules \
//      --project=project-26fb9c99-8ee9-4179-aef
```

**Não é blocker do App Review** — Meta valida BUSINESS app, não as
rules Firestore.

### 1. Fase 2.10 UI (entrega visível pro cliente — recomendada)
Backend 100% pronto: billing health-check
(`GET /api/wa/channel/{id}/billing-status`), tradução erro 402 (desde
`b15268a`), `usage_{YYYY_MM}` per-tenant + endpoints (commit `08c0753`),
cron health (commit `11e299b`) **com Cloud Scheduler ativo em staging**.
Frontend tem só o `BillingHealthBanner` parcial. Falta:
- `<TenantHealthBanner/>` mais informativo no topo da app — lê
  `tenants/{tid}/health_status/current` via Firestore snapshot (cron
  popula diariamente; em staging já tem o doc atualizado)
- Página `/setup` com checklist (CONTA / WHATSAPP / PAGAMENTO / OPERADORES / TEMPLATES)
- Modal específico do erro 402 no envio de template (com link pra
  Business Manager)
- **Card "Uso este mês" no dashboard** (consome `GET /api/wa/usage/current-month`)
- Opcional: gráfico histórico (consome `GET /api/wa/usage/history?months=6`)

### 2. Frontend passa `template_category` em send-template (low effort)
Hoje o backend aceita `template_category` opcional em `WaSendTemplateRequest`
e cai em `unknown` se ausente. Frontend já tem o campo `category` na
resposta de `/api/wa/templates` — basta repassar. Melhora a granularidade
da agregação `templates_sent.{marketing|utility|authentication}`.

### 3. Pré-cutover prod (preparar pra quando Meta aprovar)
- `scripts/wipe_all_collections.py` (Fase 4 do plano, ainda não criado).
- Runbook de cutover prod: ordem dos comandos (deploy → wipe →
  bootstrap tenant → reonboarding standard → reonboarding coex → smoke).
- Ativar Firestore rules estritas em staging (§ 2.9 do plano) pra
  validar isolamento antes de subir pra prod.
- **Replicar Cloud Scheduler em prod** (mesmo comando, trocando
  service e URL). Antes, **migrar `INTERNAL_CRON_SECRET` pra Secret
  Manager** e usar **OIDC token** em vez de header custom (Cloud
  Scheduler suporta nativamente — backend validaria issuer + SA email).

### 4. Auditoria LGPD dos logs (low effort, alto valor)
Revisar `logger.info`/`logger.warning` em `webhook.py`, `main.py`,
`bot_service.py` pra confirmar zero PII (telefones, conteúdo de
mensagem, tokens). CLAUDE.md §2 exige.

### 5. Pós re-screencast aprovado (parcialmente destravado em 2026-05-08)
- Wipe + reonboarding canal coexistence em prod (Fase 4) — destrava
  assim que o re-screencast for aprovado pela Meta.
- Promover staging → prod via wipe.
- Onboarding cliente #2 com coexistence.
- /send caminho feliz testável end-to-end.

**Status:** as 2 perms `whatsapp_business_*` já foram aprovadas Advanced
em 2026-05-08; o que falta é a Meta aceitar o novo screencast (que
demonstra o caso de uso completo). Sem isso, embora o app tenha as
permissions, o reviewer pode rejeitar a submissão em revisões futuras
e exigir re-aprovação.

## Pontos de atenção

- **Staging tem uso humano paralelo.** Se você abrir uma conversa no
  CRM enquanto o e2e roda, marca como read e contamina os asserts.
  Salvo em memory; testes flaky têm essa hipótese antes de bug real.
- **Auto-select effect.** Se nada está selecionado e há conversations,
  ele auto-seleciona a primeira. Útil pra UX, mas pode "sequestrar"
  cliques em legado. Deveria estar OK pós-3.D — todas conversations
  são threads válidas.
- **`channels` ainda em coleção flat** (não migrado pra
  `tenants/{tid}/channels`). Decisão preservada: só migra quando
  cliente #2 fechar. `_resolve_channel_creds(contact)` legado mantido
  apenas pro template de rating do `/qualify`.
- **Backend ainda mantém duplicação:** `contact.assigned_to`,
  `contact.unread_count` etc são espelhados das conversations. Remover
  espelho quando frontend estiver 100% sobre threads (frente futura).

## Quick start (próxima sessão)

```powershell
# 1. Ler este arquivo + diário de 5/9
cd c:\Projetos\Hubloc\castro-intelligence
code docs/internal/RETOMAR.md
code docs/internal/2026-05-09.md

# 2. Confirmar conta gcloud certa
gcloud config get-value account
# deve retornar: rafaluisc@outlook.com

# 3. Checar se history da Meta finalmente chegou
./.venv/Scripts/python.exe -c "
import os
os.environ['FIRESTORE_PROJECT_ID'] = 'project-26fb9c99-8ee9-4179-aef'
os.environ['FIRESTORE_COLLECTION_PREFIX'] = 'castro_crm'
from firestore_common import get_firestore_client, collection_name
c = get_firestore_client()
audit = list(c.collection(collection_name('tenants')).document('hubloc').collection('audit_log').where('action','==','history_sync_complete').stream())
print(f'history_sync_complete: {len(audit)} eventos')
msgs = list(c.collection(collection_name('tenants')).document('hubloc').collection('wa_messages').stream())
print(f'wa_messages: {len(msgs)} docs')
pending = list(c.collection(collection_name('pending_webhook_events')).stream())
print(f'pending_webhook_events: {len(pending)} docs')
"

# 4. Checar logs pra HISTORY/SMB ECHO mais recentes
gcloud run services logs read castro-crm --region=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef --limit=200 `
  --format="value(timestamp,textPayload)" `
  | Select-String "HISTORY|SMB ECHO|WA IN|PENDING"

# 5. Working tree deve estar limpo
git status --short
```

## Cloud Scheduler — comandos úteis (staging)

```powershell
# Trigger manual (sem esperar 09:00 BRT)
gcloud scheduler jobs run castro-crm-staging-health-check `
  --location=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef

# Status / proxima execucao
gcloud scheduler jobs describe castro-crm-staging-health-check `
  --location=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef `
  --format='value(state,schedule,scheduleTime,lastAttemptTime)'

# Pausar (sem deletar)
gcloud scheduler jobs pause castro-crm-staging-health-check `
  --location=southamerica-east1 --project=project-26fb9c99-8ee9-4179-aef

# Deletar
gcloud scheduler jobs delete castro-crm-staging-health-check `
  --location=southamerica-east1 --project=project-26fb9c99-8ee9-4179-aef
```

Após `jobs run`, validar com:

```powershell
./.venv/Scripts/python.exe -c "import os; os.environ.setdefault('FIRESTORE_PROJECT_ID','project-26fb9c99-8ee9-4179-aef'); os.environ.setdefault('FIRESTORE_COLLECTION_PREFIX','castro_crm_staging'); from firestore_common import get_firestore_client, collection_name; c=get_firestore_client(); d=c.collection(collection_name('tenants')).document('hubloc').collection('health_status').document('current').get().to_dict(); print('checked_at=', d.get('checked_at'))"
```

## URL e revisões úteis

- **Staging:** https://castro-crm-staging-286866630844.southamerica-east1.run.app — `castro-crm-staging-00029-bn5` (deploy de 5/9 com fixes do conversation_id + fila pending)
- **Produção:** https://castro-crm-286866630844.southamerica-east1.run.app — `castro-crm-00085-qxp` (deploy de 5/9 com operator_id em smb_echoes + Secret Manager v26)
- **Repo:** https://github.com/Iz-castro/castro-intelligence — branch `develop`
- **Cloud Scheduler staging:** `castro-crm-staging-health-check` em
  `southamerica-east1` — schedule `0 9 * * *` (09:00 BRT diário), state
  ENABLED. **Prod ainda não criado.**

### Snapshot Firestore prod apos sessao 5/11

```
tenants/hubloc/
  users (2)               — rafaluisc, izaeldecastro
  operator_profiles (2)
  departments (4)         — Geral, Vendas, Suporte, ...
  audit_log               — LOGIN_SUCCESS + history_sync_complete + WA_CONVERSATION_OPEN
  wa_contacts (160)       — 5 com conversas reais + 155 da agenda do telefone (state_sync)
  wa_conversations (5)    — so com mensagens; agenda nao polui mais (5/11 fix)
  wa_messages (56)        — history importado + testes; ordenadas por timestamp_wa real

(global/flat)
  channels (2)            — #1 coex (WABA 680503338460083), #2 standard legado (WABA 1633469507697155)
  phone_routing (2)       — 1055982807598158 → coex, 1070927076104221 → standard
  pending_webhook_events (0)
  tenants (1)             — hubloc
```

### Inspecionar Firestore prod via Python (admin)

Script ad-hoc rápido pra ler qualquer coleção sem token Firebase:

```powershell
cd c:\Projetos\Hubloc\castro-intelligence
./.venv/Scripts/python.exe -c "
import os
os.environ['FIRESTORE_PROJECT_ID'] = 'project-26fb9c99-8ee9-4179-aef'
os.environ['FIRESTORE_COLLECTION_PREFIX'] = 'castro_crm'
from firestore_common import get_firestore_client, collection_name
c = get_firestore_client()
for snap in c.collection(collection_name('channels')).stream():
    print(snap.to_dict())
"
```
