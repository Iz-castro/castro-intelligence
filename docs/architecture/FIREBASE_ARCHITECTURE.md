# Firebase Architecture

Atualizado em: 2026-05-28

## Modelo atual

O CRM esta consolidado em um unico runtime:

- `FastAPI` no backend
- `Firestore` como persistencia operacional
- `Firebase Auth` como autenticacao oficial
- `React 18 + TypeScript + Vite` no frontend
- `Cloud Storage` ou `Firestore media` para arquivos, conforme configuracao

Em termos práticos:

- o frontend le dados em tempo real do Firestore via `onSnapshot()`
- o backend concentra mutacoes sensiveis, webhook da Meta, integracoes, upload de midia e regras operacionais
- `database.py` hoje eh apenas um alias para `database_firestore.py`

## Decisoes estruturais ja fechadas

- `DATA_BACKEND` esta fixo em `firestore`
- `AUTH_MODE` esta fixo em `firebase`
- o endpoint legado `POST /api/login` nao autentica mais e responde `410 Gone`
- nao existe mais fallback real para frontend legado em `static/`
- o runtime atual serve apenas o build React em `frontend_dist/`
- o chat interno legado por WebSocket/HTML saiu do caminho operacional

## Stack principal

Backend:

- `FastAPI`
- `httpx`
- `google-cloud-firestore`
- `google-cloud-storage`
- `firebase-admin`
- `google-api-python-client`
- `faster-whisper`
- `ffmpeg`

Frontend:

- `React 18`
- `TypeScript`
- `Vite`
- `firebase` SDK

## Camadas do sistema

### Frontend

Cliente principal em `frontend/`.

Responsabilidades:

- login Google via Firebase
- abrir a sessao do CRM com `GET /api/session`
- consumir `GET /api/client-config`
- assinar colecoes Firestore liberadas pelas rules
- chamar rotas REST para envio, handoff, admin e operacoes que exigem segredo de servidor

Capacidades ativas no frontend:

- login com Google
- listagem de contatos via `wa_conversations` (1 linha por canal-thread)
- views `bot`, `novos`, `meus`, `nao_qualificados` e `equipe`
- leitura de mensagens por snapshot ou polling
- envio de texto, imagem, video, documento, audio e localizacao
- reply com contexto, copia e correcao de mensagens proprias
- transcricao manual de audio
- qualificacao, notas e assumir atendimento
- transferencia entre operadores e departamentos
- transferencia POR ATENDIMENTO (thread) vs "Reatribuir Lead" (Dono do Lead — admin)
- intervencao do supervisor — 3 modos:
  - **Sussurro** (nota interna, toggle no composer, cliente nao recebe)
  - **Co-pilotagem** (texto assinado `[Supervisao - nome]:` sem assumir; faixa de aviso)
  - **Takeover** (botao "Assumir como supervisor" muda Dono do Atendimento + avisa o lead)
- ciclo de vida do Atendimento: badge `🔒 fechado` na faixa + item "Fechar/Reabrir atendimento" no menu ⋮; reabre em qualquer nova mensagem
- protocolo do dia visivel na faixa (`📄 YYYYMMDD-{contact_id}-SETOR`); admin tem card "Buscar protocolo" no detail-panel (timeline do dia)
- Painel de Conflitos (admin/sup): Leads com >=2 atendimentos ativos de operadores distintos
- edicao basica de role e departamento por admin
- configuracoes de prefixo de mensagem
- mensagens rapidas por usuario e globais
- painel slide-in de Google Chat

Rotas HTML entregues pelo backend:

- `GET /`
- `GET /chat`
- `GET /app`

Comportamento:

- se `frontend_dist/index.html` existir, o FastAPI serve o bundle React
- se o build nao existir, o backend responde `503` com orientacao para rodar `cd frontend && npm run build`

### Backend

Arquivo principal: `main.py`

Responsabilidades centrais:

- validar ID token do Firebase
- sincronizar e provisionar usuarios internos
- expor configuracao do cliente
- receber webhook da Meta
- enviar mensagens para WhatsApp
- armazenar e servir midia
- transcrever audio quando habilitado
- integrar Google Chat
- manter logs e contadores operacionais

### Persistencia

Persistencia efetiva do repo:

- `Firestore` para entidades de CRM
- `Cloud Storage` ou `Firestore` para blobs

### Tenant-scoped (`tenants/{tid}/...`)

Subcolecoes do tenant — sao isoladas pelas Firestore rules (path-based).

- `users` — cadastro interno do operador
- `operator_profiles` — espelho seguro do operador autenticado
- `departments` — setores configurados
- `wa_contacts` — Lead/contato unico por `wa_id` (dedup atomico via index abaixo)
- `wa_conversations` — Atendimento por (canal + wa_id); id deterministico `{channel_id}__{wa_id}`. Campos relevantes: `assigned_to`, `attendance_status` (`aberto`/`fechado_inatividade`/`fechado_manual`), `takeover_status` + `takeover_handler_user_id` + `lead_owner_user_id`, denormalizacao de canal (`channel_phone_number`, `channel_label`, `channel_active`, `channel_type`).
- `wa_messages` — historico cronologico (por `timestamp_wa`). Campos novos: `conversation_id` (denorm), `protocol_id` (denorm — Fase 5A), `sender_user_id` vs `channel_owner_user_id` (auditoria coex), `direction` aceita `inbound`/`outbound`/`system`/`internal`.
- `wa_contact_index` — doc-id = `wa_id` canonico. Claim atomico via `.create()` que previne duplicatas em rajada (Fase 2 do incidente de dedup).
- `wa_transfer_log` — historico de transferencias por thread e por Lead.
- `attendances_daily` — **Fase 5A**: id `{YYYYMMDD-{contact_id}-{SETOR}}` (TZ Brasil -3 fixo). 1 Atendimento por Lead/dia; concentra `status`, `protocolo_informado`, `criado_em`, `ultima_interacao`, `fechado_em`/`fechado_por_user_id`.
- `audit_log` — toda mutacao cross-user (transferencia, takeover, reassign, fechar atendimento, enviar/receber, intervencao de supervisor).
- `audit_metrics` — agregados de auditoria.
- `audit_metrics/usage_{YYYY-MM}` — Fase 2.10.4: contadores de uso mensal (`inbound_received`, `free_form_sent`, `templates_sent.{cat}`, `media_uploaded_bytes`).
- `health_status/current` — Fase 2.10.3: snapshot do estado de billing/canal escrito pelo cron diario.
- `system_settings`, `user_settings` — configuracoes globais e por-usuario.
- `gc_conversations`, `gc_messages` — Google Chat (`space_id`, mensagens, anexos).

### Flat / global (fora de `tenants/`)

- `channels` — registry de canais WhatsApp (standard + coexistence). Compartilhado entre tenants enquanto o sistema for single-tenant operacional.
- `phone_routing/{phone_number_id}` — indice global que mapeia `phone_number_id` da Meta para `{tenant_id, channel_id}`. Webhook resolve tenant em O(1) sem varrer canais.
- `pending_webhook_events` — fila de webhooks da Meta nao processados imediatamente (canal nao indexado durante onboarding, exception). Garante zero perda.
- `tenants` — lista flat de tenants (root).
- `media_assets` — metadados/referencias de blob.
- `_meta` — counters cross-tenant.

### Indices e contadores

- `firestore.indexes.json` foi reduzido a indices COLLECTION_GROUP ativos para `wa_conversations`, `wa_messages`, `wa_contacts`, `wa_transfer_log`.
- `_meta/counters` (sequencias atomicas) **NAO** e mais usado no caminho quente de auditoria — `log_audit` usa doc-id auto-gerado desde a remediacao do hotspot (2026-05-25). Reservado para entidades que precisam mesmo de id int sequencial.

## Colecoes lidas pelo React

O frontend recebe os nomes finais das colecoes por `/api/client-config`.

Colecoes expostas ao cliente:

- `departments`
- `operator_profiles`
- `wa_contacts`
- `wa_conversations`
- `wa_messages`
- `wa_transfer_log`
- `attendances_daily` (admin/sup via REST; nao via snapshot direto)
- `health_status` (manager — leitura do snapshot do estado de billing)
- `gc_conversations`
- `gc_messages`

Observacao importante:

- os nomes finais passam por `FIRESTORE_COLLECTION_PREFIX`
- as rules atuais sao estritas e escopadas por path `tenants/{tid}/...` (Fase 2 da remediacao de isolamento por operador, 2026-05-19; reconfirmadas 2026-05-22)
- claim `tenant_id` no JWT do Firebase Auth gateia leitura por tenant
- mudar o prefixo sem alinhar `firestore.rules` quebra snapshots no frontend

## Fluxo de autenticacao

1. O usuario faz login Google no Firebase Auth.
2. O frontend obtem um `ID token`.
3. O frontend chama `GET /api/session` com `Authorization: Bearer <ID_TOKEN>`.
4. `auth.py` valida o token com `firebase-admin`.
5. O backend sincroniza o operador no Firestore.
6. O documento `operator_profiles/{uid}` passa a espelhar o operador autenticado.

Regras atuais:

- acesso pode ser restringido por `ALLOWED_FIREBASE_EMAIL_DOMAIN` e `ALLOWED_FIREBASE_EMAILS`
- `AUTO_PROVISION_FIREBASE_USERS` pode provisionar automaticamente usuarios permitidos
- `BOOTSTRAP_ADMIN_EMAIL` continua sendo o caminho de bootstrap inicial para o primeiro admin

## Fluxos operacionais

### WhatsApp

Entrada:

- o webhook recebe eventos da Meta
- identifica ou cria contato
- persiste mensagens e atualiza nao lidas
- baixa midia quando necessario
- pode transcrever audio inbound conforme feature flag

Tipos tratados no inbound:

- `text`
- `image`
- `audio`
- `video`
- `gif`
- `sticker`
- `document`
- `location`
- `contacts`
- `reaction`
- `unsupported`

Saida:

- o frontend usa rotas REST para enviar texto, midia, audio, localizacao e templates
- o backend aplica regras de atribuicao, janela de 24h e contexto de reply

Operacoes de atendimento mais importantes:

- qualificar contato
- assumir atendimento
- transferir atendimento (POR THREAD; Reatribuir Lead e separado e admin-only)
- fechar / reabrir atendimento manual (`set-attendance`)
- intervir como supervisor — Sussurro (nota interna), Co-pilotagem (texto assinado), Takeover (assume thread + avisa o lead)
- marcar conversa como lida (por thread ou por contato — legacy)
- arquivar e restaurar contato
- auto-close por inatividade (cron `*/30` — threshold via env `ATTENDANCE_AUTOCLOSE_HOURS`)
- envio automatico do protocolo do dia ao cliente no fechamento (Fase 5A)

### Midia

Pipeline atual:

- uploads do operador e anexos do WhatsApp passam pelo backend
- o arquivo vai para `local`, `gcs` ou `firestore`, conforme `MEDIA_STORAGE_BACKEND`
- o Firestore guarda metadados e referencias de arquivo
- `GET /media/...` entrega o conteudo a partir do backend configurado

### Transcricao

Status atual:

- usa `faster-whisper`
- converte audio com `ffmpeg`
- suporta transcricao inbound e rota manual por mensagem
- a rota manual em `main.py` ja usa as configs corretas `STT_LANGUAGE_CODE` e `STT_TIMEOUT_SECONDS`

### Google Chat

Hoje o produto ainda usa Google Chat como camada complementar de comunicacao interna.

Fluxos ativos:

- listar spaces
- listar conversas e mensagens
- enviar mensagem do CRM para um `space`
- receber webhook do Google Chat
- persistir mensagens e anexos no Firestore

Modelo Firestore:

- `gc_conversations` guarda `space_id`, nome, preview, participantes e mapa de nao lidas
- `gc_messages` guarda remetente, texto, anexos e timestamps

Comportamento mais recente:

- anexos recebidos pelo webhook sao salvos com `await` correto no pipeline async
- `participants` passa a ser recalculado a partir dos emails ativos do CRM
- `unread_count` deixa de depender de uma lista vazia e acompanha operadores ativos

## Entrega de dados em tempo real

Modo principal:

- `snapshot`

Fallback operacional:

- `polling`

Interpretacao correta:

- a arquitetura alvo e em tempo real com Firestore
- polling existe como degradacao controlada
- o antigo caminho de chat interno por WebSocket nao representa mais a arquitetura atual

## Seguranca e restricoes atuais

Arquivos centrais:

- `firestore.rules`
- `storage.rules`

Estado atual das rules (2026-05-28):

- rules **estritas** em prod desde a Fase 2 da remediacao de isolamento por operador (2026-05-19; reconfirmadas 2026-05-22)
- escopadas por path `tenants/{tid}/...` (isolamento estrutural, nao apenas filtro logico)
- claim `tenant_id` + `role` no JWT (custom claims do Firebase Auth) sao a fonte de autorizacao
- backend valida `tenant_id` e role em todo endpoint mutador (cross-check com rules)
- snapshots Firestore para o operador comum: escopados a `assigned_to == self`, sem dono, ou mesmo `department_id`

Conclusao:

- o ciclo de seguranca de rules + claims esta fechado em prod
- isolamento e auditoria sao defensaveis (vide `docs/compliance/LGPD_RoPA_RIPD_INTERNO.md`)
- pendencia menor: ainda nao ha multi-tenant operacional (a `castro_crm_tenants` so contem `hubloc`); quando o cliente #2 fechar, validar isolamento end-to-end com 2+ tenants em paralelo

## Rotas de referencia

Autenticacao:

- `GET /api/session`
- `GET /api/client-config`
- `POST /api/login` apenas para responder `410 Gone`

WhatsApp — contatos e mensagens:

- `GET /api/wa/contacts`
- `GET /api/wa/contacts/all` (modal "Selecionar contato" — agenda)
- `GET /api/wa/conversations` (sub-threads enriquecidas com canal e contato)
- `GET /api/wa/messages/{contact_id}?conversation_id=...`
- `POST /api/wa/send`
- `POST /api/wa/send-media`
- `POST /api/wa/send-audio`
- `POST /api/wa/send-location`
- `POST /api/wa/send-template`
- `POST /api/wa/messages/{message_id}/transcribe`
- `PUT /api/wa/contact/{contact_id}/qualify`
- `POST /api/wa/contact/{contact_id}/read`
- `POST /api/wa/conversation/{conversation_id}/read` (Fase 2C — por thread)

WhatsApp — atribuicao e ciclo de vida:

- `POST /api/wa/transfer` (transferir thread; aceita `conversation_id`)
- `POST /api/wa/assume/{contact_id}`
- `POST /api/wa/contact/{contact_id}/return-to-bot`
- `GET /api/wa/transfer-history/{contact_id}`
- `POST /api/wa/conversation/{id}/takeover` (coex: lead-owner takeover temporario)
- `POST /api/wa/conversation/{id}/return` (devolve takeover ao dono do lead)
- `POST /api/wa/conversation/{id}/supervisor-takeover` (Modo 3: admin/sup assume thread + avisa lead)
- `POST /api/wa/conversation/{id}/set-attendance` (Fase 4: fechar/reabrir manual)
- `POST /api/wa/internal-note` (Modo 1: nota interna; nao vai pra Meta)
- `POST /api/wa/conversation/open` (materializa thread ao clicar contato da agenda)

Embedded Signup (coex):

- `GET /api/embedded-signup/config`
- `POST /api/embedded-signup/exchange` (Fase 1: rebind por `phone_number_id` em vez de criar duplicata)
- `POST /api/admin/channels/{id}/trigger-coex-sync` (re-disparo manual de `smb_app_data`)

Admin:

- `GET /api/admin/channels`, `POST /api/admin/channels`, `PUT /api/admin/channels/{id}`
- `GET /api/admin/conflicts` (Fase 3A: Leads com >=2 atendimentos ativos de operadores distintos)
- `GET /api/admin/protocol/{protocol_id}` (Fase 5A: timeline do dia por protocolo)
- `POST /api/admin/reassign-lead` (Fase 3B: muda Dono do Lead sem mover atendimentos)
- `POST /api/admin/bulk-reassign`
- `GET /api/admin/pending-webhook-events?status=pending`
- `POST /api/admin/pending-webhook-events/{id}/retry|dismiss`
- `DELETE /api/admin/pending-webhook-events/{id}`
- `POST /api/admin/operator/{user_id}/reset-assume-counter`

Cron / interno (auth via OIDC do Cloud Scheduler):

- `POST /api/internal/cron/health-check` (Fase 2.10.3: status billing por canal/tenant — escreve `health_status/current`)
- `POST /api/internal/cron/expire-takeovers` — schedule `*/30`. Roda: (1) expira takeover coex inativo > `TAKEOVER_TIMEOUT_HOURS`; (2) auto-close de atendimentos atribuidos ociosos > `ATTENDANCE_AUTOCLOSE_HOURS`; (3) envia protocolo ao lead no fechamento (Fase 5A) se nao informado e <=24h

Usage / billing:

- `GET /api/wa/usage/current-month`
- `GET /api/wa/usage/history?months=N`
- `GET /api/wa/usage/{YYYY-MM}`
- `GET /api/wa/channel/{id}/billing-status`

Usuarios e configuracoes:

- `GET /api/operators`
- `GET /api/departments`
- `POST /api/admin/users`
- `PUT /api/admin/users/{user_id}`
- `DELETE /api/admin/users/{user_id}`
- `GET /api/settings/system`
- `PUT /api/settings/system`
- `GET /api/settings/user`
- `PUT /api/settings/user`

Google Chat:

- `GET /api/gc/conversations`
- `GET /api/gc/messages/{conversation_id}`
- `POST /api/gc/send`
- `POST /api/gc/mark-read/{conversation_id}`
- `GET /api/gc/spaces`
- `POST /webhooks/google-chat`

## Leitura curta para quem chegar depois

Se voce abrir o repo hoje, a interpretacao correta eh:

- backend e frontend ja operam como `Firestore + Firebase Auth + React`
- SQL, login legado e frontend estatico antigo nao fazem mais parte do runtime real
- Google Chat continua ativo, mas seu estado operacional fica persistido no Firestore
- qualquer evolucao futura deve partir desse modelo, e nao de compatibilidade com o sistema antigo
