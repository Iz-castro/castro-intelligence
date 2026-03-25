# AI Agent Context

Atualizado em: 2026-03-20
Projeto: Castro Intelligence CRM
Repositorio: `castro-intelligence`

## Objetivo do projeto

Este projeto e um CRM de atendimento com foco em WhatsApp Business.

Hoje ele tem duas camadas convivendo ao mesmo tempo:

- Arquitetura alvo: `FastAPI + Firestore + Firebase Auth + Cloud Storage/Firebase Storage + frontend React/Vite`.
- Arquitetura legado/fallback: `FastAPI + SQL (SQLite/PostgreSQL) + JWT proprio + frontend estatico em HTML/JS`.

A direcao atual do produto esta claramente puxando para `Firestore + Firebase Auth + React`.
O legado ainda existe, continua funcional em partes e nao deve ser removido sem decisao explicita.

## Estado atual do repositorio

- Branch atual: `develop`
- Ultimo commit local visto: `ab2db84 Alteracao para o firestore`
- O worktree esta sujo
- `frontend/` aparece como nao rastreado no `git status`
- Ha varios arquivos modificados localmente, inclusive `main.py`, `config.py`, `auth.py`, backends de banco, regras do Firebase e scripts de deploy

Implicacao pratica:

- Nao assuma que o estado atual ja esta commitado
- Nao reverta mudancas locais sem confirmar a intencao
- Se fizer alteracoes, trabalhe por cima do estado atual

## Como pensar o sistema

Modelo mental rapido:

1. O WhatsApp entrega eventos no webhook da Meta.
2. O backend processa o payload, cria/atualiza contatos, baixa midia quando existir e persiste historico.
3. Operadores acessam o CRM web.
4. No modo novo, o operador entra com Google via Firebase Auth.
5. O frontend consome REST do FastAPI para operacoes sensiveis e usa Firestore `onSnapshot()` para leitura em tempo real.
6. No modo legado, a autenticacao e via JWT proprio e o frontend estatico usa REST/polling.

## Stack real do projeto

Backend Python:

- `FastAPI`
- `httpx`
- `bcrypt`
- `PyJWT`
- `SQLAlchemy` so para engine/conexao SQL, nao ha ORM de models
- `google-cloud-firestore`
- `google-cloud-storage`
- `firebase-admin`
- `ffmpeg` para converter audio do navegador para `ogg/opus`

Frontend novo:

- `React 18`
- `TypeScript`
- `Vite`
- SDK `firebase`

Infra:

- Docker multi-stage
- `docker-compose.yml` para subir localmente
- `deploy.ps1` e `deploy.sh` para Cloud Run
- Secret Manager no deploy cloud
- Cloud SQL opcional se `DATA_BACKEND=sql`

## Entradas principais do codigo

Leia nesta ordem para entender o sistema:

1. `config.py`
2. `main.py`
3. `database.py`
4. `database_firestore.py` ou `database_sql.py`
5. `auth.py`
6. `webhook.py`
7. `media.py`
8. `frontend/src/App.tsx`
9. `FIREBASE_ARCHITECTURE.md`
10. `RESUMO_SISTEMA_E_ROTACAO.md`

Arquivos auxiliares importantes:

- `bootstrap_data.py`: departamentos padrao
- `init_db.py`: bootstrap inicial
- `firebase_admin_client.py`: inicializacao do Firebase Admin
- `firestore_common.py`: helper para nomes de collections, normalizacao e sequencias
- `firestore.rules`: regras do Firestore
- `storage.rules`: regras do Storage

Arquivos grandes/gerados:

- `estrutura_projeto.md`: inventario enorme do projeto; util como referencia bruta, ruim para leitura inicial
- `frontend_dist/`: build gerado do frontend React

## Modo de operacao atual

O codigo foi preparado para modos combinaveis, mas o alvo hoje e:

- `DATA_BACKEND=firestore`
- `AUTH_MODE=firebase`
- `CHAT_DELIVERY_MODE=snapshot`
- `MEDIA_STORAGE_BACKEND=gcs` ou `firestore`

Regras importantes:

- `database.py` escolhe a implementacao ativa com base em `DATA_BACKEND`
- `AUTH_MODE` pode ser `firebase` ou `legacy`
- O frontend React exige `AUTH_MODE=firebase`
- Se existir `frontend_dist/index.html` e `AUTH_MODE=firebase`, as rotas `/`, `/chat` e `/app` servem o build React
- Sem build React, o sistema cai no HTML legado de `static/`

## Configuracao por ambiente

Arquivo base:

- `.env.example`

Arquivo real local:

- `.env`

Nao exponha valores reais de `.env` em logs, respostas ou commits.

Variaveis centrais:

- `DATA_BACKEND=firestore|sql`
- `AUTH_MODE=firebase|legacy`
- `CHAT_DELIVERY_MODE=snapshot|polling`
- `FIRESTORE_PROJECT_ID`
- `FIRESTORE_COLLECTION_PREFIX`
- `ALLOWED_FIREBASE_EMAIL_DOMAIN`
- `ALLOWED_FIREBASE_EMAILS`
- `AUTO_PROVISION_FIREBASE_USERS`
- `FIREBASE_WEB_API_KEY`
- `FIREBASE_WEB_AUTH_DOMAIN`
- `FIREBASE_WEB_APP_ID`
- `FIREBASE_WEB_MESSAGING_SENDER_ID`
- `FIREBASE_WEB_MEASUREMENT_ID`
- `FIREBASE_STORAGE_BUCKET`
- `GCS_MEDIA_BUCKET`
- `GCS_MEDIA_PREFIX`
- `MEDIA_STORAGE_BACKEND=local|gcs|firestore`
- `WHATSAPP_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_EMAIL` ou `BOOTSTRAP_ADMIN_USERNAME`/`BOOTSTRAP_ADMIN_PASSWORD`

Defaults relevantes em `config.py`:

- Se backend for Firestore, o auth default tende para Firebase
- Se backend for SQL, o auth default tende para legado
- Se houver bucket configurado, a midia tende para `gcs`
- Em Cloud Run com SQL, SQLite e proibido

## Persistencia e modelo de dados

### Camada de abstracao

`database.py` exporta a API comum e escolhe entre:

- `database_firestore.py`
- `database_sql.py`

Ambos implementam a mesma interface de funcoes para:

- usuarios
- departamentos
- mensagens internas
- contatos WhatsApp
- mensagens WhatsApp
- transferencia de atendimentos
- auditoria
- avatars

Regra importante para evolucao:

- Se adicionar campo novo de dominio, atualize os dois backends ou registre explicitamente que a feature so vale para um deles
- Manter a paridade da interface e responsabilidade de quem mexer na persistencia

### Entidades principais

Usuarios:

- operador/admin/supervisor
- podem ter `department_id`
- no modo Firebase podem ter `email`, `firebase_uid` e `auth_provider`

Departamentos:

- padrao atual: `Geral`, `Vendas`, `Suporte`, `Financeiro`

Contatos WhatsApp:

- identificados por `wa_id`
- guardam atribuicao, qualificacao, notas, avatar e metadados de ultima interacao

Mensagens WhatsApp:

- inbound, outbound ou system
- podem ter `content`, `media_path`, `media_mime`, `filename`, `status`, `timestamp_wa`

Historico de transferencia:

- registra handoff entre operadores/departamentos com `reason` e `summary`

## Firestore: visao pratica

Colecoes principais expostas ao frontend React:

- `operator_profiles`
- `departments`
- `wa_contacts`
- `wa_messages`
- `wa_transfer_log`

Colecoes privadas do backend:

- `users`
- `messages`
- `internal_unread`
- `audit_log`
- `wa_message_status`
- `_meta`

Detalhe importante:

- O prefixo real depende de `FIRESTORE_COLLECTION_PREFIX`
- `main.py` expoe os nomes finais em `/api/client-config`
- `frontend/src/App.tsx` usa esses nomes dinamicos para abrir snapshots

## Fluxos principais

### 1. Startup

Arquivo: `main.py`

Na subida da app:

- valida configuracao critica
- inicializa banco
- garante departamentos padrao
- provisiona admin bootstrap
- prepara diretorios de midia

### 2. Autenticacao

Modo Firebase:

1. React faz `signInWithPopup()` com Google.
2. O frontend pega o `ID token`.
3. Chama `GET /api/session` com `Authorization: Bearer <ID_TOKEN>`.
4. `auth.py` valida com `firebase-admin`.
5. O backend sincroniza/provisiona usuario interno.
6. O frontend passa a ler dados por Firestore snapshot e usar REST para escrita.

Modo legado:

1. `POST /api/login`
2. `auth.py` valida usuario/senha
3. backend devolve JWT proprio
4. frontend estatico guarda token em `sessionStorage`

### 3. Webhook WhatsApp

Arquivo: `webhook.py`

O webhook trata:

- verificacao `GET /webhook`
- recebimento `POST /webhook`
- validacao de assinatura HMAC-SHA256 quando configurada

Tipos tratados hoje:

- `text`
- `image`
- `audio`
- `video`
- `gif` via payload de video com flag gif
- `sticker`
- `document`
- `location`
- `contacts`
- `reaction`
- `unsupported`
- tipos desconhecidos viram placeholder textual

Para mensagens com midia:

- o backend consulta a URL da midia na Meta
- baixa o arquivo
- salva no backend de midia configurado
- persiste `media_path` e metadados

### 4. Envio de mensagens

Arquivo: `main.py`

Rotas principais:

- `POST /api/wa/send`
- `POST /api/wa/send-media`
- `POST /api/wa/send-audio`
- `POST /api/wa/send-template`

Regras atuais:

- exige `WHATSAPP_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID`
- respeita atribuicao do contato; se o contato estiver com outro operador o envio e bloqueado
- audio do navegador e convertido para `ogg/opus` com `ffmpeg` antes do envio

### 5. Midia

Arquivo: `media.py`

Backends suportados:

- `local`
- `gcs`
- `firestore`

Comportamento:

- `local`: grava em `MEDIA_DIR`
- `gcs`: grava no bucket configurado
- `firestore`: guarda metadados e chunks binarios em collection de assets

Implicacoes:

- qualquer mudanca em midia precisa considerar leitura, escrita e remocao nos 3 backends
- em Firestore existe compressao gzip e chunking

### 6. Frontend React

Arquivo principal: `frontend/src/App.tsx`

O frontend novo cobre hoje:

- login com Google
- leitura de contatos e mensagens
- snapshot Firestore ou fallback polling
- envio de texto
- envio de imagem
- gravacao e envio de audio
- qualificacao de contato
- transferencia de atendimento
- lightbox de imagem/video

O frontend React NAO cobre hoje:

- chat interno entre operadores
- CRUD admin de usuarios
- fluxo legado com JWT proprio

Essas areas ainda vivem no HTML legado ou apenas no backend.

### 7. Frontend legado

Arquivos:

- `static/index.html`
- `static/chat.html`

Ele ainda contem:

- login legado via `/api/login`
- painel unico em JS puro
- chamadas REST para contatos, mensagens, transferencia, avatar e admin
- codigo de WebSocket ainda existe

Mas ha um detalhe importante:

- `static/chat.html` hoje retorna `false` em `useWebSocketMode()`
- na pratica, o cliente legado esta trabalhando por polling, nao por WebSocket ativo

## Rotas mais importantes do backend

Paginas:

- `GET /`
- `GET /chat`
- `GET /app`
- `GET /media/{subdir}/{filename}`

Autenticacao:

- `POST /api/login`
- `GET /api/session`
- `GET /api/client-config`

Perfil:

- `POST /api/profile/avatar`
- `DELETE /api/profile/avatar`

WhatsApp:

- `GET /api/wa/contacts`
- `GET /api/wa/messages/{contact_id}`
- `POST /api/wa/send`
- `POST /api/wa/send-media`
- `POST /api/wa/send-audio`
- `POST /api/wa/send-template`
- `PUT /api/wa/contact/{contact_id}/qualify`
- `DELETE /api/wa/contact/{contact_id}`
- `POST /api/wa/contact/{contact_id}/restore`
- `GET /api/wa/contact/{contact_id}`
- `POST /api/wa/transfer`
- `GET /api/wa/transfer-history/{contact_id}`

Usuarios/departamentos:

- `GET /api/operators`
- `GET /api/departments`
- `POST /api/admin/users`
- `PUT /api/admin/users/{user_id}`
- `DELETE /api/admin/users/{user_id}`

Chat interno legado:

- `GET /api/users`
- `GET /api/messages/{contact_id}`
- `POST /api/messages`
- `GET /api/unread`
- `WS /ws/{token}`

## Firebase e seguranca

Arquivos:

- `firestore.rules`
- `storage.rules`

Estado atual das rules:

- sao temporarias
- usam emails especificos hardcoded para liberar acesso
- `wa_contacts`, `wa_messages` e `wa_transfer_log` estao com leitura ampla para esses emails liberados

Interpretacao correta:

- isso serve para desenvolvimento/demo
- ainda nao e o desenho final de seguranca por operador/departamento
- qualquer evolucao seria mais segura se endurecer essas rules antes de escalar

## Bootstrap inicial

Arquivos:

- `init_db.py`
- `bootstrap_data.py`
- `main.py` no startup

Comportamento:

- departamentos padrao sempre sao garantidos
- no modo Firebase o admin inicial vem de `BOOTSTRAP_ADMIN_EMAIL`
- no modo legado o admin inicial vem de `BOOTSTRAP_ADMIN_USERNAME` + `BOOTSTRAP_ADMIN_PASSWORD`

## Como rodar localmente

### Opcao Python puro

1. Criar e ativar `.venv`
2. `pip install -r requirements.txt`
3. Configurar `.env` a partir de `.env.example`
4. Se for usar o frontend React: `cd frontend && npm ci && npm run build`
5. Voltar para a raiz do projeto
6. `python init_db.py`
7. `python main.py`

Observacoes:

- a app sobe em `http://127.0.0.1:8080`
- `ffmpeg` precisa existir na maquina para envio de audio gravado
- `start.example.ps1` mostra um fluxo local no Windows com ngrok

### Opcao Docker

- `docker compose up --build`

O `Dockerfile`:

- builda o frontend primeiro
- instala dependencias Python
- instala `ffmpeg`
- expoe a porta `8080`

## Como fazer deploy

Scripts prontos:

- `deploy.ps1`
- `deploy.sh`

Eles fazem, em alto nivel:

- leitura de `.env`
- validacao de envs obrigatorias
- habilitacao de APIs GCP
- criacao/configuracao de service account
- bucket de storage
- secrets no Secret Manager
- Cloud SQL opcional quando `DATA_BACKEND=sql`
- deploy no Cloud Run

Para a arquitetura alvo, o caminho esperado e:

- Cloud Run
- Firestore
- Firebase Auth
- Cloud Storage/Firebase Storage

## Pontos de atencao reais

- Nao existe suite de testes automatizados no repo
- `main.py` concentra muita regra de negocio
- Existem dois frontends convivendo
- Existem dois backends de persistencia convivendo
- Existem dois modelos de autenticacao convivendo
- Regras do Firebase ainda estao em modo temporario de liberacao por email
- Houve historico recente de preocupacao com segredos e rotacao de credenciais, veja `RESUMO_SISTEMA_E_ROTACAO.md`

## O que um proximo agente nao deve esquecer

- Priorize a arquitetura alvo atual: `Firestore + Firebase Auth + React`
- Nao remova o legado sem pedido explicito
- Se mudar schema/campos de dominio, verifique impacto em:
  - `database_firestore.py`
  - `database_sql.py`
  - `main.py`
  - `frontend/src/types.ts`
  - `frontend/src/App.tsx`
  - `firestore.rules`
- Se mudar autenticacao Firebase, verifique impacto em:
  - `auth.py`
  - `firebase_admin_client.py`
  - `frontend/src/firebase.ts`
  - `main.py` em `/api/session` e `/api/client-config`
- Se mudar fluxo de midia, verifique impacto em:
  - `webhook.py`
  - `media.py`
  - endpoints de envio em `main.py`
  - renderizacao do frontend React
- Nao editar `frontend_dist/` manualmente; altere `frontend/` e gere novo build
- Nao confiar nas rules atuais como desenho final de seguranca
- Nao vazar segredos do `.env`

## Melhor ponto de partida para novas tarefas

Se a tarefa for sobre:

- autenticacao/config: ler `config.py`, `auth.py`, `firebase_admin_client.py`, `main.py`
- CRM/atendimento: ler `main.py`, backend de banco ativo, `frontend/src/App.tsx`
- webhook/WhatsApp: ler `webhook.py`, `media.py`, `main.py`
- dados/snapshot: ler `firestore_common.py`, `database_firestore.py`, `firestore.rules`, `frontend/src/App.tsx`
- deploy/infra: ler `.env.example`, `Dockerfile`, `deploy.ps1`, `deploy.sh`, `docker-compose.yml`

## Resumo executivo

Este repo ja saiu do MVP puramente local e esta em migracao concreta para uma arquitetura moderna com Firebase/Firestore.
O backend FastAPI continua sendo o centro das operacoes sensiveis e da integracao com a Meta.
O frontend React novo ja atende o fluxo principal de operacao WhatsApp, mas ainda nao substituiu todo o legado.
O maior cuidado para qualquer continuidade e respeitar essa fase hibrida sem quebrar compatibilidade, seguranca ou paridade entre backends.
