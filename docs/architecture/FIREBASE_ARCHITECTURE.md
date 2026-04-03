# Firebase Architecture

Atualizado em: 2026-04-02

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
- listagem de contatos WhatsApp
- views `novos`, `meus`, `nao_qualificados` e `equipe`
- leitura de mensagens por snapshot ou polling
- envio de texto, imagem, video, documento, audio e localizacao
- reply com contexto
- transcricao manual de audio
- qualificacao, notas e assumir atendimento
- transferencia entre operadores e departamentos
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

Colecoes backend principais:

- `users`
- `departments`
- `operator_profiles`
- `wa_contacts`
- `wa_messages`
- `wa_transfer_log`
- `wa_message_status`
- `audit_log`
- `system_settings`
- `user_settings`
- `gc_conversations`
- `gc_messages`
- `media_assets`
- `_meta`

Entidades que mais importam no dia a dia:

- `users`: cadastro interno do operador
- `operator_profiles`: espelho seguro do operador autenticado
- `wa_contacts`: resumo do atendimento por contato
- `wa_messages`: historico completo de mensagens WhatsApp
- `wa_transfer_log`: historico de handoff
- `gc_conversations`: conversas do Google Chat com preview e nao lidas
- `gc_messages`: mensagens e anexos do Google Chat

## Colecoes lidas pelo React

O frontend recebe os nomes finais das colecoes por `/api/client-config`.

Colecoes expostas ao cliente:

- `departments`
- `operator_profiles`
- `wa_contacts`
- `wa_messages`
- `wa_transfer_log`
- `gc_conversations`
- `gc_messages`

Observacao importante:

- os nomes finais passam por `FIRESTORE_COLLECTION_PREFIX`
- as rules atuais continuam hardcoded para o prefixo `castro_crm_*`
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
- transferir atendimento
- marcar conversa como lida
- arquivar e restaurar contato

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

Estado atual das rules:

- ainda sao regras amplas para desenvolvimento/demo controlada
- usam emails autorizados e prefixos hardcoded
- ainda nao implementam isolamento fino por operador ou departamento

Conclusao:

- o maior risco arquitetural restante nao e mais o legado
- o ponto que mais pede maturidade agora e seguranca das rules e o desenho futuro do chat interno

## Rotas de referencia

Autenticacao:

- `GET /api/session`
- `GET /api/client-config`
- `POST /api/login` apenas para responder `410 Gone`

WhatsApp:

- `GET /api/wa/contacts`
- `GET /api/wa/messages/{contact_id}`
- `POST /api/wa/send`
- `POST /api/wa/send-media`
- `POST /api/wa/send-audio`
- `POST /api/wa/send-location`
- `POST /api/wa/send-template`
- `POST /api/wa/messages/{message_id}/transcribe`
- `PUT /api/wa/contact/{contact_id}/qualify`
- `POST /api/wa/contact/{contact_id}/read`
- `POST /api/wa/transfer`
- `POST /api/wa/assume/{contact_id}`
- `GET /api/wa/transfer-history/{contact_id}`

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
