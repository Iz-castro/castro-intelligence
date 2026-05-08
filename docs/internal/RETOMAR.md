# Contexto pra retomar — App Review parcial, refazer screencast

> Snapshot atualizado em 2026-05-08 (manhã) após resultado da revisão
> Meta. Quando voltar, leia este arquivo primeiro, depois
> [2026-05-05.md](2026-05-05.md), [2026-05-06.md](2026-05-06.md) e
> [2026-05-08.md](2026-05-08.md) pra detalhe cronológico, ou
> [PLANO_COEXISTENCE_REFATORACAO.md](../PLANO_COEXISTENCE_REFATORACAO.md)
> pra detalhe arquitetural.

## Onde paramos

**App Review parcialmente aprovado em 2026-05-08:**
- ✅ `whatsapp_business_messaging` — Advanced Access
- ✅ `whatsapp_business_management` — Advanced Access
- ✅ `public_profile` — renovada
- ❌ `business_management` — reprovada (é permission de Ads Manager,
  não de Embedded Signup do WhatsApp; descartada do escopo)

**Outras 2 permissions decididas como fora do escopo (mesma sessão):**
- `manage_app_solution` — não se aplica (somos Tech Provider direto
  pra clientes finais, não intermediamos Solution Partners)
- `whatsapp_business_manage_events` — Conversions API for WhatsApp
  não está implementada; pedir sem feature levaria a reprovação. A
  função `test_whatsapp_business_manage_events` em
  `test_meta_app_review.py` ficou comentada como referência histórica.

Meta também reprovou o screencast por "não demonstrar a experiência
completa do caso de uso" — faltou tela de consent + caso de uso
end-to-end. **Refazer screencast cobrindo as 2 perms aprovadas é a
frente crítica agora.** Roteiro novo pronto em
[`docs/APP_REVIEW_SCREENCAST_SCRIPT.md`](../APP_REVIEW_SCREENCAST_SCRIPT.md)
endereçando todos os pontos do feedback (login Meta completo, consent
screen, server-to-server note, narração+legendas inglês com tooltips).

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

**Produção:** intocada (`castro-crm`, `00077-qls`). Aguardando aprovação
Meta App Review pra cutover prod (Fase 4). Cloud Scheduler prod
**ainda não criado** — comandos OIDC + Secret Manager documentados em
`docs/deploy/RUNBOOK_CUTOVER_PROD.md` §6.

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

### 0. App Review — refazer screencast e ressubmeter (FRENTE CRÍTICA)

Resultado de 2026-05-08: 2 perms aprovadas Advanced
(`whatsapp_business_messaging` + `whatsapp_business_management`),
`business_management` reprovada (descartada do escopo — não é necessária
pra Embedded Signup do WhatsApp). Screencast anterior reprovado por
não demonstrar experiência completa do caso de uso.

**Sequência:**

1. **Revisar Configurador Embedded Signup no Painel Meta**
   (business.facebook.com → app `1434723791183375` → Account Tools →
   API setup). Localizar Configurador correspondente a
   `EMBEDDED_SIGNUP_CONFIG_ID`. Remover `business_management` dos
   scopes solicitados se estiver lá. Garantir que pede só
   `whatsapp_business_management` + `whatsapp_business_messaging`.
   Ver §5 do
   [APP_REVIEW_SCREENCAST_SCRIPT.md](../APP_REVIEW_SCREENCAST_SCRIPT.md).

2. **Deploy prod com a limpeza** (`main.py` simplificou a tupla de
   detection do scope coexistence — irrelevante operacionalmente, mas
   pra evitar drift fica em prod junto):
   ```powershell
   gcloud run deploy castro-crm `
     --source . --region southamerica-east1 `
     --project project-26fb9c99-8ee9-4179-aef --quiet
   ```

3. **Smoke test em staging**: abrir `Conectar WhatsApp` no CRM staging,
   iniciar Embedded Signup. Popup deve completar sem erro #2655111
   agora que as 2 perms estão Advanced. Se ainda der erro, capturar
   o erro REAL (provavelmente é o Configurador ainda pedindo
   `business_management`).

4. **Gravar screencast** seguindo
   [APP_REVIEW_SCREENCAST_SCRIPT.md](../APP_REVIEW_SCREENCAST_SCRIPT.md).
   Pontos críticos:
   - Narração em inglês + legendas em inglês visíveis
   - Tooltips em inglês explicando elementos da UI portuguesa
   - Consent screen do Meta visível e pausada ~3s
   - Embedded Signup conclui com sucesso (popup fecha, CRM mostra
     "Conexão realizada com sucesso!")
   - Disclaimer server-to-server explícito no slide intro + closing
   - Handle do destinatário visível em todos envios

5. **Resubmeter cada permission** com as notas técnicas atualizadas
   (§3 do roteiro). Reforçar disclaimer server-to-server em cada nota.

**Não submeter `business_management`, `manage_app_solution` nem
`whatsapp_business_manage_events`.** Todas três fora do escopo do
produto — ver bloco "Onde paramos" acima.

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
# 1. Ler este arquivo + o diário do 5/8 + roteiro do screencast
cd c:\Projetos\Hubloc\castro-intelligence
code docs/internal/RETOMAR.md
code docs/internal/2026-05-08.md
code docs/APP_REVIEW_SCREENCAST_SCRIPT.md

# 2. Confirmar conta gcloud certa
gcloud config get-value account
# deve retornar: rafaluisc@outlook.com

# 3. Working tree deve estar limpo
git status --short

# 4. (Opcional) Smoke test rapido do que ja existia
./.venv/Scripts/python.exe -m scripts.e2e_test_staging
# espera: ✓ E2E PASSED (9/9)

# 5. Abrir staging no browser
# https://castro-crm-staging-286866630844.southamerica-east1.run.app

# 6. Frente principal: re-screencast App Review
#    a) Painel Meta: revisar Configurador (ver §0 acima)
#    b) Deploy prod com cleanup business_management
#    c) Smoke test Embedded Signup em staging
#    d) Gravar screencast seguindo APP_REVIEW_SCREENCAST_SCRIPT.md
#    e) Resubmeter na pagina App Review
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

- **Staging:** https://castro-crm-staging-286866630844.southamerica-east1.run.app — `castro-crm-staging-00028-qbn`
- **Produção:** `castro-crm`, `00077-qls` (Fase 1 apenas, intocada)
- **Repo:** https://github.com/Iz-castro/castro-intelligence — branch `develop`
- **Último commit:** `78234f7`
- **Cloud Scheduler staging:** `castro-crm-staging-health-check` em
  `southamerica-east1` — schedule `0 9 * * *` (09:00 BRT diário), state
  ENABLED.
