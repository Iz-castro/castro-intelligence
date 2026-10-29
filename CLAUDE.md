# CLAUDE.md

Guia operacional do **Castro Intelligence CRM** — CRM de WhatsApp multi-tenant.
Curto e de propósito: só o que já foi verificado no código atual. Se algo aqui
divergir do código, **o código vence** — corrija este arquivo.

Cliente principal em produção: **Hubloc / Hub Loc** (locadora de equipamentos,
plano `professional`). Tenant #2 **operacional em prod desde 2026-07-29**:
**Varizemed** (clínica, plano `ai_custom`, bot Dialogflow CX com temperatura de
lead). Há ainda um 3º tenant interno de teste (`varizemed-test`, mesmo agente CX).

---

## Stack e runtime

- Backend: **FastAPI 0.115 + uvicorn** (async), app único em `main.py` servido por
  `uvicorn main:app --workers 1`. Runtime **Python 3.10** (container `python:3.10-slim`).
- Dados: **Firestore Native** + **Firebase Auth** + **Google Cloud Storage** (mídia).
  `DATA_BACKEND` e `AUTH_MODE` são constantes em `config.py` (não configuráveis por env).
- `database.py` só reexporta `database_firestore.py`. **Não existe caminho SQL.**
  `POST /api/login` é legado (410 Gone); auth real = Firebase ID token.
- Frontend: **React 18 + Vite 5 + TypeScript + Firebase 11** em `frontend/`,
  compilado **dentro** da imagem Docker (`/frontend_dist`) e servido pelo backend.
- Deploy: **Google Cloud Run** (`castro-crm`), projeto Oregon (ver Deploy).

## Rodar e validar

Não há suíte de testes automatizada versionada (sem pytest/tox/conftest). Os gates são:

- **Backend:** `.venv\Scripts\python.exe -m py_compile main.py webhook.py bot_service.py bot_engine_dialogflow.py bot_sender.py lgpd_bot.py database_firestore.py config.py tenant_service.py channel_service.py`
- **Lógica do bot:** `.venv\Scripts\python.exe tools\sim_bot_flow.py` (mocka Firestore + WhatsApp
  API, exercita o código real, 76 asserts, exit 0/1). CX: `tools\sim_cx_flow.py` (235).
  Modo Recepção (pool compartilhada) + reabertura em lote por público + gates de origem do transfer/takeover + Continuar devolve ao agente: `tools\sim_reception_flow.py` (333).
  Buffer/debounce do webhook: `tools\sim_buffer_flow.py` (61).
  Aviso de espera na pool (cron 5 min): `tools\sim_pool_wait_notice.py` (48).
  Monitor de atendimento (fila, metricas, origem, auditoria): `tools\sim_monitor_flow.py` (73).
  History sync/eco do coex (recência real, janela de 24h, dono da thread, idempotência por bloco): `tools\sim_history_recency.py` (62).
  Ver como (UID temporario, registro/end/cleanup, trava de escrita, TTL e auditoria):
  `tools\sim_impersonate.py`. Janelas HTTP/polling, backup e IDOR:
  `tools\sim_impersonate_views.py`. Auth/Firestore Emulators locais: `tools/impersonate_emulators/README.md`
  (rules combinadas com o follow-up: 861 verificacoes em 2026-10-18).
  Follow-up (tarefas, API/RBAC, preferencia comercial, produtores de envio): `tools\sim_followup_flow.py` (81),
  `tools\sim_followup_api.py` (56), `tools\sim_commercial_contact_policy.py` (55), `tools\sim_followup_send_guards.py`;
  na raiz, `node tools\sim_followup_frontend.mjs` (19) e `node tools\sim_followup_lifecycle.mjs` (25).
  Guias de conversa (limite por uso, rascunho+modo por guia, storage por uid + restauracao sem abrir, auto-fechamento so com dado do servidor, Ctrl+Alt+Seta, Sair apaga rascunho, Ver como/polling sem guias): na raiz, `node tools\sim_chat_tabs.mjs` (174).
  ⚠️ `tools\cx_smoke.py` **não é mockado** — bate no agente Dialogflow CX real (precisa ADC).
  ⚠️ `tools\reopen_conciliation.py --tenant <id>` **não é mockado** — lê o Firestore real (só leitura,
  escrita travada no cliente): conciliação v1 × v2 da reabertura em lote (plano 11.1).
- **Frontend:** `npm run build` em `frontend/` (`tsc -b && vite build` = typecheck estrito + build).
  Parser da formatação WhatsApp (`src/utils/waFormat.ts`): `node tools\check_wa_format.mjs` em
  `frontend/` (~32 asserts, exit 0/1; compila com o esbuild do Vite).

## Deploy (produção)

Prod = projeto **`project-4a851bf9-f475-418c-800`**, região **`us-west1`** (Oregon),
prefixo de coleção `castro_crm`, tenant default `hubloc`.

**Runbook humano passo a passo** (deploy sem o agente): `docs/deploy/DEPLOY_CLOUDRUN_A.md`.

**Comando de deploy de rotina** (`--source` puro **preserva** env, secrets e scaling da revisão anterior):

```powershell
gcloud run deploy castro-crm --source C:\Rafael\castro-intelligence --region us-west1 --project project-4a851bf9-f475-418c-800 --quiet
```

Três pegadinhas que **já quebraram** deploy — não esqueça nenhuma:

1. **`--project` explícito sempre.** `gcloud config` aponta pro projeto ANTIGO de SP
   (`project-26fb9c99-8ee9-4179-aef`). Sem `--project`, o deploy vai pro projeto errado.
2. **Caminho ABSOLUTO em `--source`, nunca `.`** — se o shell estiver em `frontend/`
   (ex.: após `npm run build`), o `.` cai em Buildpacks e falha.
3. **`CLOUDSDK_PYTHON` → Python312** (`C:\Users\izael\AppData\Local\Programs\Python\Python312\python.exe`);
   já setado no escopo User, mas shells que não herdam (ex.: Bash tool) precisam prefixar.

- Os antigos `deploy.ps1` / `deploy.sh` foram **REMOVIDOS do repo** (2026-08-06): usavam
  `--env-vars-file` + `--set-secrets` + scaling hardcoded e **clobberavam** env/secrets/scaling
  de prod. Se recuperar do historico do git, NAO usar em prod; bootstrap de infra nova esta
  documentado em `docs/deploy/RUNBOOK_CUTOVER_PROD.md` (IAM/bucket/secrets).
- `docs/deploy/RUNBOOK_CUTOVER_PROD.md` está **STALE** (cita SP / `southamerica-east1`). O
  procedimento é útil, mas traduza projeto/região pro Oregon; não copie os `--project`/`--region` de lá.
- **Tráfego é FIXADO por revisão** (o serviço tem tag `staging` + traffic pinado, não "serve latest").
  Um `gcloud run deploy` direto na prod sobe a revisão nova **a 0%** e o gcloud ainda imprime
  "serving 100 percent" (mentira — é a revisão velha). Pior: o fluxo staging+promote **bagunça a
  numeração**, então a revisão nova pode ter número MENOR que as antigas → **`--to-latest` cai na
  errada**. **Sempre promova por NOME após o deploy:**
  `gcloud run services update-traffic castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --to-revisions <REV_NOVA>=100` e confira com `describe ... status.traffic`.
- **O NOME de revisão impresso pelo `gcloud run deploy` também pode estar ERRADO** (2026-07-29:
  imprimiu `00066-bsm`, mas a revisão criada foi `00067-frb` → promoção errada por ~2 min). Descubra
  a revisão nova com `gcloud run revisions list ... --sort-by "~metadata.creationTimestamp"` (a mais
  recente por data de criação), nunca pelo texto do deploy.
- **Smoke pós-deploy:** `GET /` → 200 e `GET /api/client-config` → 200 (confere `projectId`
  Oregon). Scaling vivo se preserva sozinho — não afirme números sem `gcloud run services describe castro-crm`.
- **Rollback:** `gcloud run services update-traffic castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --to-revisions <REV_ANTERIOR>=100`.
- **Cloud Run B** (`castro-superadmin`) tem pipeline **separado** (`cloudbuild-superadmin.yaml` +
  `Dockerfile.superadmin`); **não** use `--source` (pegaria o Dockerfile do A). Ver `docs/DEPLOY_CLOUDRUN_B.md`.

## Invariantes que NÃO podem quebrar (landmines reais)

- **Ver como (ADR 0014):** UID Firebase temporario `imp_ro_*`, nunca o do alvo/admin;
  `sessionUser.firebase_uid` e queries/toggles continuam do alvo. Registro tenant-scoped
  prende UID/SID/ambiente/prazo; contrato exige registro/TTL no backend e nega mutacoes CRM,
  inclusive sem claim `imp` no UID reservado. Sem escrita automatica no alvo. Fim so da
  propria sessao; cleanup apos 2h exclui apenas UID registrado, nunca contas reais.
  Auth temporario em memoria, sem cliente Firestore temporario, e marcador de aba sem
  segredo evitam restaurar admin no reload.
  **Transporte revisado aprovado:** temporario usa somente HTTP/polling fixo15s; rules
  negam toda leitura/escrita direta, inclusive UID reservado sem claim e imp legado.
  Backend preserva janelas por target, filtra backup/ownership antes de entregar e
  reautentica apos bufferizar cada corpo, sem memo final. UI descarta resposta tardia;
  nenhuma queda para Firestore. Sessoes normais mantem listeners atuais. A revisao veio
  apos listener +1,259s e backup indevido no emulador (prod nao verificado); pendencia de
  backup normal e URL de midia anonima conhecida continuam fora desta mudanca.
  Exigir gates do transporte HTTP atual; nao presumir prontidao pelos testes antigos.
  Polling repete leituras e target backup original nao tem cap; avaliar custo antes de
  ativar, sem reduzir janelas silenciosamente. Feature desligada por default.
  **Revisao do merge (2026-10-18):** so role admin inicia (o toggle sozinho nao basta);
  FEATURE_IMPERSONATE=false derruba sessoes ja emitidas no middleware; o solicitante e
  revalidado (ativo, admin, com o toggle; cache de 30 s); get_current_user falha FECHADO
  (503) se um token imp chegar sem a trava do middleware. `sim_impersonate.py` = 306.
- **`_GLOBAL_COLLECTIONS` (`firestore_common.py`)** = `channels, pending_webhook_events,
  super_admins, audit_logs_system, phone_routing, _meta, tenants`. Ficam **flat/globais** mesmo
  com tenant context ativo. Toda coleção que o webhook precisa ler **antes** de saber o tenant
  pertence aqui. Tirar `channels` daqui = refresh sob tenant monta cache vazio → `no_channel` por
  ~60s → inbound cai em pending (perda crônica de mensagens).
- **`channel_id` vem do contador GLOBAL:** `next_sequence("channels", tenant_id="")` com string
  **vazia**, nunca `None` (`None` colide ids entre tenants — incidente 2026-07-16).
- **`conversation_id` é determinístico:** `"{channel_id}__{wa_id}"`. Sem `channel_id`/`wa_id`,
  o webhook enfileira em `pending_webhook_events` (auto-id do Firestore) — nunca gera id sintético.
- **Isolamento do operador (LGPD) = 3 camadas em sincronia** (backend `get_wa_contacts_scoped_for_user`,
  frontend snapshot targets, `firestore.rules`). Operador comum vê **só próprios** (`assigned_to_uid==uid`)
  **+ pool sem dono** — **NUNCA por department_id** (query por depto vazava agenda coex pessoal pros colegas).
  `is_backup` só admin/supervisor. **4ª camada (2026-08-19):** o frontend fecha o chat quando a thread
  aberta **muda de dono** pra outro usuário (watcher + listener do doc da thread, `CrmContext.tsx`) e
  `/api/wa/assume` carimba o dono em **todas** as threads órfãs do contato; `/conversation/open` só
  auto-atribui thread de lead **já meu** — não regrida (B via picker/admin continuava vendo a conversa de A).
- **IDOR:** endpoints por `contact_id`/`message_id` chamam `_require_contact_access` (ex.:
  `/api/wa/conversation/open`). Sem isso, operador abre/auto-atribui lead alheio por id enumerável.
- **Atribuição POR THREAD** (`assign_wa_conversation`, `assigned_to` na conversation) é **separada**
  do **Dono do Lead** (`assign_wa_contact`, `/api/admin/reassign-lead`). Revert no fechamento tem que
  gravar `assigned_to_uid` (não só `assigned_to`), senão o lead some do frontend da própria dona.
- **Modo Recepção (ADR 0010):** `system_settings/chat.pool_mode` (`legacy`|`reception`, default no
  READ — nunca backfill). Em `reception` (varizemed): operador comum responde thread SEM dono de
  canal **standard** sem assumir (coex fica FORA), `conversation/open` não auto-atribui, fechamento
  (manual/cron) devolve o lead ao **agente de IA** (`release_lead_to_bot`: `bot_completed=False`,
  sem dono; `sale_owner`/setor/protocolo/prova LGPD preservados) e o menu "Devolver à recepção"
  devolve à pool SEM encerrar. O cron fecha órfãs com `bot_completed`. Autoria vive NA MENSAGEM
  (`sender_user_id` + `sent_by_name` denormalizado — campo novo em `wa_messages` exige whitelist em
  `normalization.ts`). "Assumir pra falar" (ADR 0008) segue sendo o default de todo tenant `legacy`;
  o toggle RBAC `assumir_atendimento` (ON por default) permite perfil "só recepção". Kill-switch sem
  deploy: `PUT pool_mode=legacy`.
- **Whisper cold-start:** `FEATURE_AUDIO_TRANSCRIPTION=true` só é seguro porque o modelo está
  **embutido na imagem** (`HF_HUB_OFFLINE=1`). Ligar sem o modelo embutido trava o startup probe →
  cascata 500/503/429. Mudar `WHISPER_MODEL_SIZE` **exige rebuild** da imagem.
- **Bootstrap de setores:** `bootstrap_departments` roda a cada startup e só semeia defaults se o
  tenant tiver **zero** setores (inclusive inativos). Não remova o gate (setores "Vendas" duplicados
  já sequestraram roteamento). Após o seed, editar setor só pela UI.
- **Não regrida os fixes de custo:** header da sidebar usa `count_only=1` (aggregate), não o
  full-scan de `/api/wa/contacts/all`; os crons (`close_stale_attendances`, `expire_stale_takeovers`)
  usam `.where(...)` server-side, não full-scan de `wa_conversations`.
- **Não-lido: a THREAD é a fonte da verdade (ADR 0011).** `wa_contacts.unread_count` é DERIVADO
  (soma das threads; `recompute_wa_contact_unread`, chamado no read por thread). Beep/alarme do
  frontend avaliam só `novosConversations + meusConversations` (o que a caixa mostra) e o
  `unread_count` da thread — nunca o array cru `contacts` (incidente 2026-08-21: alarme perpétuo por
  lead em fase de bot invisível ao operador). Não reintroduza zeramento só da thread.
- **Resolução de canal no webhook:** `phone_number_id` sem canal **ativo** vai pra pending —
  nunca cai no canal default (número coex desconectado vazaria pro standard).
- **History sync do coex NÃO é mensagem ao vivo:** `_process_history` usa a data REAL de cada mensagem
  (contato com `from_message_event=False`; thread criada pelo pré-passe com o **dono do número**;
  mensagem antiga não reabre atendimento) e o eco (`smb_message_echoes`) não mexe em `last_inbound_at`
  (janela de 24h é só mensagem DO CLIENTE). Carimbar "agora" encheu o top-50 do Meus de conversas
  antigas (incidente Roberta, 2026-10-14). Reparo de dados: `scripts/repair_recency_channels.py` (dry-run default).
- **Reentrega da Meta:** `POST /webhook` só responde 200 **depois** do turno do bot (CX tem
  orçamento de `CX_DETECT_TIMEOUT_SECONDS`, 60s, por TURNO; read-timeout da chamada principal
  reenvia 1x com o teto inteiro — `CX_READ_TIMEOUT_RETRY`, default true, pior caso ~2min) e a Meta
  **reentrega o payload ~23s sem ACK**. O guard `was_dup` em `webhook.py` (texto **e áudio**) é o que impede bot e
  transcrição de rodarem 2x — tirar áudio dali = Val responde em dobro e Whisper re-transcreve o
  mesmo áudio por dias (incidente 2026-08-14/18).
- **Follow-up (PR #2, 2026-10-18):** liga POR TENANT (2026-10-26): `FEATURE_FOLLOWUP` (env, chave
  geral) **E** `tenants/{id}.settings.followup_enabled is True` (`tenant_followup_enabled`, em
  `followup_routes.py`); sem as duas, a API `/api/followup` da 404 e a sessao manda
  `followup.enabled=false` (tela, Finalidade do template e chaves de perfil somem). Template comercial
  e reabertura pontual checam `_require_contact_access` ANTES do 409 da recusa (senao o 409 revela a
  recusa de lead alheio — LGPD); o gate de envio, que silencia a Val na Recepcao, segue depois. A recusa
  comercial (`wa_contacts.commercial_contact_block`) barra template comercial, reabertura pontual, o scan
  v2 do lote (`scan_reopen_audiences`), o worker (pulo contado em `pulados_recusa_comercial`) e o script
  one-off; **se desfaz quando o paciente manda mensagem nova** (decisao do PO, mesmo D4 do Encerrar),
  no `save_wa_message`, so para inbound recebido posterior ao registro (clique, reacao e historico nao
  contam). `scripts/send_template_bulk.py` fica sem envio (campanha encerrada; nao respeitava o teto de
  250/dia). Tarefas e historico (`crm_tasks`, `crm_activities`) sao so do backend nas rules.
- **Event loop único (`--workers 1`): trabalho síncrono pesado roda em `run_in_threadpool`** (2026-10-28).
  O cliente Firestore é síncrono; uma chamada longa dentro de `async def` congela TODAS as requests da
  instância. Já estão fora do loop: Whisper (`_transcribe_off_loop`, semáforo de 1), os crons
  (`_verify_cron_auth` + `expire_stale_takeovers`/`close_stale_attendances`/pool-wait) e o `smb_app_state_sync`.
  `close_stale_attendances` retorna cedo em tenant legacy com auto_close OFF (lia 2.351 threads por execução).
  **History do coex é idempotente por BLOCO** (`history_chunks/{numero__c<canal>__fase__ordem__hash}`,
  `claim_history_chunk`/`finish_history_chunk`, `claim_id` por tentativa): a Meta reenviava o mesmo bloco ~1x/h
  por ~6 dias e cada reentrega travava o loop 43–63 s (apuração 2026-10-27: 75/75 congelamentos vistos pelas
  operadoras). `done` só depois de persistir tudo; `failed` libera o lease (mídia inline sem download também é
  `failed` + fila de pendentes). **Reentrega durante a importação (`busy`) responde 503** — única resposta não-2xx
  do `/webhook` — para a Meta reentregar até cair em `done`; um 200 sem cópia durável perderia o bloco se o dono do
  lease morresse. Ainda inline no loop: a PRIMEIRA entrega de cada bloco (194–210 s) — não conectar número coex
  novo em horário de pico até levar `_process_history_threads` para thread.
- **Transfer/return/takeover exigem posse da origem** (`_require_transfer_source_access`, 2026-10-28): operador
  comum só transfere thread própria ou da pool **com lead sem dono (ou seu)** — órfã de lead alheio não é pool;
  por `contact_id`, só lead próprio/pool, e o gate roda ANTES do `_resolve_send_target` (que faz upsert). Sem ramo
  de takeover: o handler é gravado pelo próprio `/takeover`, que agora só aceita `pending` com handler = eu ou número
  meu (antes qualquer operador virava handler de thread sem conflito, silenciava o bot e forjava posse).
- **Buffer CX:** debounce persistido em `bot_buffers/{contact_id}`, somente pós-LGPD e
  somente Dialogflow CX. Default global `BOT_BUFFER_SECONDS=0`; override no READ por
  `settings.ai.buffer_seconds` (`scripts/set_tenant_buffer.py`, dry-run default). Ativar
  primeiro no `varizemed-test`. Claim com heartbeat + orçamento de parede de 240s por request
  (Cloud Run mata em 300s) — não tire nenhum dos dois (`docs/BUFFER_MENSAGENS_BOT.md` §Revisão).

## Mapa de módulos (onde mexer)

| Assunto | Arquivos |
|---|---|
| Config / env / feature flags | `config.py` |
| App, rotas, middleware de tenant | `main.py` |
| Persistência CRM (tudo) | `database_firestore.py` (via `database.py`) |
| Acesso a dados, prefixo, tenant context, `next_sequence` | `firestore_common.py` |
| Webhook Meta (resolve tenant → canal, nunca propaga exceção) | `webhook.py` |
| Fila zero-perda de webhook | `pending_events.py` |
| Registry de canais WhatsApp (flat) | `channel_service.py` |
| Tenants, `phone_routing` global, resolução de login por domínio | `tenant_service.py` |
| Auth (Firebase ID token, resolução de tenant) | `auth.py` |
| Ver como (identidade, registro, HTTP/polling e cleanup) | `impersonation_identity.py`, `impersonation.py`, `impersonation_views.py` — ADR 0014 |
| RBAC dinâmico por tenant | `rbac.py` |
| Gate LGPD | `lgpd_bot.py` |
| Bot builtin + dispatcher builtin/CX | `bot_service.py` |
| Envio de resposta automática WhatsApp | `bot_sender.py` |
| Horário comercial por tenant (aviso builtin + params CX) | `business_hours.py` |
| Follow-up (tarefas, filas, calendario, preferencia comercial) | `followup_service.py`, `followup_routes.py`, `followup_access.py`, `followup_repository.py`, `commercial_contact_policy.py`, `frontend/src/features/followup/` — ver `docs/followup_crm_varizemed.md` (secao 16) |
| Monitor de atendimento (porte do painel do Izael; so-leitura, so admin por default) | `monitor_service.py`, `frontend/src/components/monitor/MonitorModal.tsx` — ver `docs/MONITOR_ATENDIMENTO.md` |
| Redação de PII em logs | `pii_redaction.py` |
| Frontend (estado central + listeners) | `frontend/src/context/CrmContext.tsx`, `App.tsx` |

Modelo de dados WhatsApp: `wa_contacts` (Lead único por `wa_id`) · `wa_conversations`
(Atendimento por canal+wa_id) · `wa_messages` (histórico por `timestamp_wa`).

## Multi-tenant

- Tenant context por request: middleware extrai `tenant_id` do claim do JWT antes do endpoint.
  Coleções roteiam para `tenants/{tid}/<name>` quando há contexto; senão, flat (compat).
- Prefixo final = `{FIRESTORE_COLLECTION_PREFIX}_{name}` (`castro_crm`; staging `castro_crm_staging`).
  Staging e prod **compartilham o mesmo Firebase/Auth**, isolados só pelo prefixo — claim de tenant
  só-de-prod dá 403 em staging.
- `allowed_email_domains` é **soft** (guarda-corpo + roteamento de login); quem autoriza é o **claim
  `tenant_id`**. Provedores públicos (gmail/outlook) nunca roteiam/auto-provisionam tenant.
- **3 tenants ativos em prod** (hubloc, varizemed, varizemed-test) desde 2026-07-28. Com >1 tenant
  ativo, `single_active_tenant()` retorna None → login sem claim e sem domínio casado é **403**
  (rede de transição desarmada, by design). `"hubloc"` segue hardcoded como fallback em vários
  pontos (`webhook.py`, middleware, `channel_service.py`) — revisar antes de qualquer fluxo que
  dependa de resolução implícita de tenant.
- Planos: vocabulário canônico = `professional | ai_custom | enterprise_ai` (`PLAN_OPTIONS`,
  em inglês). **Nenhum runtime gateia por plano hoje** — o agente de IA liga por
  `settings.ai` (bot_engine/status) + `system_settings.bot_enabled` do tenant.
- **Motor CX**: `settings.ai.environment_id` vazio = produção roda no **DRAFT** do agente
  Dialogflow (edição no console entra em prod na hora — já causou o bug dos params em struct,
  2026-07-29). Ver `docs/CX_AGENTE_PENDENCIAS_DEV_IA.md`.
- **Troca de motor (Hubloc -> agente Hugo, 2026-10-23):** voltar ao builtin = `settings.ai.bot_engine` vazio
  (cache de 60 s); NUNCA `status=paused` (bot mudo). O builtin trata o step `cx` como LGPD aceita e
  finaliza no Comercial. `settings.ai.omit_session_params` (lista fechada: `retorno_previsto`,
  `fora_do_expediente`, `tenant_id`) tira do turno CX o param que o agente declara com outro tipo.
  `settings.ai.lgpd_by_agent=true` (decisao do PO p/ o Hugo): o CRM NAO faz o gate LGPD nem grava prova de
  aceite; o agente trata aviso e recusa, e o CRM nao manda `lgpd_consent`. So com True explicito; a Val
  segue com o gate local. Emenda no ADR 0009.

## Convenções

- **Comentários e docstrings em pt-BR SEM acento** (evita encoding). Strings ao cliente final
  (respostas do WhatsApp) **mantêm** acentuação normal.
- Todo `.py` da raiz começa com `# -*- coding: utf-8 -*-`.
- Logging: um logger por módulo, `logging.getLogger("castro_crm.<modulo>")`. **Nunca** logar
  PII/tokens em claro — usar `pii_redaction.py` (`redact_phone`, `redact_name`) + `%s` lazy.
- Feature flags **env-driven**, centralizadas em `config.py`, lidas uma vez no import. Religar
  recurso = mudar env, não código. (`FEATURE_AUDIO_TRANSCRIPTION` default false — ver cold-start.)
- Branch de trabalho = **`develop`**. **Não commitar/push sem pedido explícito.**
- Decisões arquiteturais → `docs/decisions/` (ADR `NNNN-slug.md`). Diários/histórico →
  `docs/internal/` (`YYYY-MM-DD.md`).
- Nunca versionar segredos/PII (`.env`, `service-account*.json`, `media/`, `logs/` já no `.gitignore`).
