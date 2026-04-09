# Análise Arquitetural Completa — Castro Intelligence CRM

**Data:** 30/03/2026  
**Projeto:** Castro Intelligence CRM (WhatsApp Business + Google Chat)

---

## 1. Visão Geral

O Castro Intelligence é um **CRM de atendimento multicanal** (WhatsApp Business + Google Chat) voltado para operações de locação de equipamentos pesados. O sistema permite que operadores gerenciem conversas com clientes via WhatsApp e se comuniquem com supervisores de campo via Google Chat, tudo em uma única interface web.

### Stack Tecnológico

| Camada | Tecnologia |
|--------|-----------|
| **Backend** | Python 3.10 + FastAPI (uvicorn) |
| **Frontend** | React 18 + TypeScript + Vite |
| **Banco de Dados** | Google Cloud Firestore |
| **Autenticação** | Firebase Auth (Google OAuth) + JWT legado |
| **Storage de Mídia** | Cloud Storage / Firestore / Local |
| **Transcrição** | Faster Whisper (local, CPU) |
| **Deploy** | Cloud Run + Docker (multi-stage) |
| **Conversão de Áudio** | FFmpeg (OGG/Opus) |

---

## 2. Estrutura de Pastas

```
castro-intelligence/
├── main.py                      # Aplicação FastAPI (rotas, WebSocket, startup)
├── config.py                    # Configuração centralizada via env vars
├── auth.py                      # Autenticação (Firebase + Legacy JWT)
├── database.py                  # Facade — re-exporta database_firestore
├── database_firestore.py        # Camada de persistência Firestore (1007 linhas)
├── firebase_admin_client.py     # Inicialização Firebase Admin SDK
├── firestore_common.py          # Client Firestore, utilitários, sequências atômicas
├── webhook.py                   # Processamento webhook WhatsApp (Meta)
├── webhook_google_chat.py       # Processamento webhook Google Chat
├── google_chat.py               # Cliente API Google Chat
├── media.py                     # Storage de mídia (3 backends)
├── transcription_service.py     # Transcrição de áudio (Faster Whisper)
├── bootstrap_data.py            # Departamentos padrão
├── init_db.py                   # Seed inicial (admin + departamentos)
├── seed_gchat.py                # Dados de teste Google Chat
├── requirements.txt             # 14 dependências Python
├── Dockerfile                   # Build multi-stage (Node + Python)
├── docker-compose.yml           # Orquestração local
├── firestore.rules              # Regras de segurança Firestore
├── firestore.indexes.json       # Índices compostos Firestore
├── storage.rules                # Regras Cloud Storage
├── frontend/                    # Aplicação React
│   ├── src/
│   │   ├── main.tsx             # Entry point React
│   │   ├── App.tsx              # Componente principal (~658 linhas)
│   │   ├── api.ts               # Camada HTTP (getJson, sendJson, etc.)
│   │   ├── firebase.ts          # Inicialização Firebase client-side
│   │   ├── types.ts             # Tipos TypeScript
│   │   ├── context/
│   │   │   └── CrmContext.tsx   # State management (~978 linhas)
│   │   ├── components/
│   │   │   ├── icons/index.tsx  # 11 ícones SVG
│   │   │   └── gchat/
│   │   │       └── InternalChatPanel.tsx  # Painel Google Chat
│   │   ├── hooks/
│   │   │   └── useClickOutside.ts
│   │   └── utils/
│   │       ├── formatting.ts    # Formatação de datas, mensagens
│   │       ├── normalization.ts # Normalização Firestore → app
│   │       ├── storage.ts       # LocalStorage (tema, transport)
│   │       ├── media.ts         # Resolução de tipo de mídia
│   │       ├── firebase-helpers.ts
│   │       └── errors.ts
│   └── vite.config.ts           # Build config (output: ../frontend_dist)
├── frontend_dist/               # Build compilado do frontend
├── docs/                        # Documentação do projeto
├── media/                       # Mídia local (dev)
├── logs/                        # Logs da aplicação
└── data/                        # Dados auxiliares
```

---

## 3. Arquitetura de Comunicação entre APIs

### Princípio Central: Firestore como Ponte

O React **conversa diretamente com o Firestore** para leitura em real-time (via `onSnapshot()`), mas **toda escrita passa pelo FastAPI**. O Firestore funciona como ponte entre backend e frontend:

```
                    LEITURA DIRETA (onSnapshot real-time)
React  ──────────────────────────────────────────►  Firestore
  │                                                    ▲
  │    ESCRITA (todas as ações passam pelo backend)    │
  └──────────► FastAPI ────────────────────────────────┘
```

- **Firestore Rules:** `write: false` em todas as coleções para o frontend — React é read-only
- **Firebase Auth:** Autentica o React para acessar snapshots diretamente
- **Resultado:** Operador vê mensagens aparecerem instantaneamente sem polling

### 3.1 Fluxo Principal — WhatsApp Inbound

```
Cliente WhatsApp
      │
      ▼
Meta Cloud API (webhook)
      │
      ▼
┌─────────────────────────────────────┐
│  POST /webhook                      │
│  ├─ validate_signature() (HMAC-256) │
│  ├─ process_webhook_payload()       │
│  │   ├─ upsert_wa_contact()        │  ──► Firestore: wa_contacts
│  │   ├─ download_media()           │  ──► Meta API → Storage backend
│  │   ├─ transcribe_audio_bytes()   │  ──► Faster Whisper (opcional)
│  │   ├─ save_wa_message()          │  ──► Firestore: wa_messages
│  │   └─ ws_notify_callback()       │  ──► (legado, não usado atualmente)
│  └─ _process_statuses()            │  ──► Firestore: wa_message_status
└─────────────────────────────────────┘
      │
      ▼
Firestore Snapshot (real-time, direto para o React)
      │
      ▼
React Frontend (onSnapshot listener — sem passar pelo backend)
```

### 3.2 Fluxo Principal — WhatsApp Outbound

```
Operador (React)
      │
      ▼
POST /api/wa/send  (ou /send-media, /send-audio, /send-location)
      │
      ▼
┌─────────────────────────────────────┐
│  FastAPI Backend                    │
│  ├─ Valida token (Firebase/JWT)     │
│  ├─ upload_media_to_whatsapp()     │  ──► Meta API (upload)
│  ├─ POST messages (Graph API v22)  │  ──► Meta → Cliente WhatsApp
│  └─ save_wa_message(direction=out) │  ──► Firestore: wa_messages
└─────────────────────────────────────┘
      │
      ▼
Firestore Snapshot → React atualiza chat
```

### 3.3 Fluxo Google Chat

```
Supervisor (Google Chat App)
      │
      ▼
POST /webhooks/google-chat
      │
      ▼
┌─────────────────────────────────────┐
│  validate_google_chat_token()       │  ──► JWT RS256 vs Google certs
│  process_google_chat_event()        │
│  ├─ ADDED_TO_SPACE → boas-vindas   │
│  ├─ MESSAGE:                        │
│  │   ├─ upsert_gc_conversation()   │  ──► Firestore: gc_conversations
│  │   ├─ download_attachment()      │  ──► Google Chat API
│  │   └─ save_gc_message()          │  ──► Firestore: gc_messages
│  └─ REMOVED_FROM_SPACE → log       │
└─────────────────────────────────────┘
      │
      ▼
Firestore Snapshot → InternalChatPanel (React)
```

### 3.4 Fluxo de Autenticação (Firebase)

```
React App
  │
  ├─ 1. signInWithPopup(GoogleAuthProvider)
  │      └─► Google OAuth → Firebase Auth → ID Token
  │
  ├─ 2. GET /api/session (Bearer: ID Token)
  │      └─► FastAPI:
  │          ├─ verify_firebase_id_token()
  │          ├─ _firebase_email_allowed() (whitelist)
  │          ├─ upsert_firebase_user() (auto-provisão)
  │          ├─ sync_user_identity()
  │          └─ _sync_operator_profile_from_user()
  │                └─► Firestore: operator_profiles/{uid}
  │
  └─ 3. React usa Firestore snapshots para dados em tempo real
         (autenticado via Firebase Auth, regras via email whitelist)
```

---

## 4. Banco de Dados — Firestore

### 4.1 Coleções e seus Propósitos

Todas as coleções usam prefixo configurável (`castro_crm_` por padrão).

#### Coleções Públicas (acessíveis pelo React via Firestore Rules)

| Coleção | Propósito | Docs estimados |
|---------|-----------|---------------|
| `operator_profiles/{uid}` | Perfil público do operador (espelho de users) | ~5-20 |
| `departments/{id}` | Departamentos da empresa | ~4 |
| `wa_contacts/{id}` | Contatos WhatsApp / leads | Crescente (~2500/mês) |
| `wa_messages/{id}` | Mensagens WhatsApp (in/out/system) | Crescente (~70k/mês) |
| `wa_transfer_log/{id}` | Histórico de transferências entre operadores | Crescente |
| `gc_conversations/{id}` | Conversas Google Chat (spaces) | ~5-20 |
| `gc_messages/{id}` | Mensagens Google Chat | Crescente |

#### Coleções Privadas (apenas backend)

| Coleção | Propósito |
|---------|-----------|
| `users` | Contas de usuário (contém password_hash) |
| `messages` | Chat interno entre operadores (legado) |
| `internal_unread` | Contadores de não-lidos interno |
| `audit_log` | Log de auditoria (login, ações) |
| `wa_message_status` | Status de entrega das mensagens |
| `_meta/counters` | Contadores auto-incrementais (IDs) |
| `media_assets` | Metadados de mídia (quando backend=firestore) |

### 4.2 Modelo de Dados — Entidades Principais

#### Contact (wa_contacts)
```
id: int (auto-increment)
wa_id: "5511999999999"
display_name: string
phone_formatted: "+55 11 99999-9999"
qualification: "novo" | "em_atendimento" | "qualificado" | "nao_qualificado" | "convertido"
notes: string
assigned_to: int (user_id)
assigned_to_uid: string (Firebase UID)
department_id: int
unread_count: int
is_archived: bool
first_seen_at: ISO string
last_message_at: ISO string
contact_avatar_path: string
```

#### Message (wa_messages)
```
id: int (auto-increment)
wa_message_id: string (ID único da Meta)
contact_id: int
direction: "inbound" | "outbound" | "system"
msg_type: "text" | "image" | "audio" | "video" | "document" | "sticker" | "location" | "gif"
content: string
media_path: "/media/subdir/filename"
media_mime: string
status: "received" | "sent" | "delivered" | "read" | "failed"
operator_id: int
reply_to_message_id: int
reply_to_preview: string
reply_to_sender_name: string
transcription: string (Whisper)
timestamp_wa: ISO string
created_at: ISO string
```

#### User (users — privado)
```
id: int
username: string
email: string
firebase_uid: string
auth_provider: "firebase" | "legacy"
display_name: string
password_hash: string (bcrypt)
role: "admin" | "supervisor" | "operador"
department_id: int
is_active: bool
failed_attempts: int
locked_until: ISO string
```

### 4.3 IDs Auto-Incrementais

O sistema usa **contadores atômicos no Firestore** em vez de UUIDs:

```
Documento: _meta/counters
Campos: { users: 5, wa_contacts: 2847, wa_messages: 71230, ... }
```

Cada `next_sequence(counter_name)` executa uma **transação Firestore** que incrementa o contador e retorna o novo valor. Isso garante unicidade mesmo com múltiplas instâncias.

### 4.4 Índices Compostos

| Coleção | Campos | Uso |
|---------|--------|-----|
| `wa_messages` | `contact_id` ASC + `created_at` DESC | Mensagens de um contato por data |
| `wa_messages` | `contact_id` ASC + `direction` ASC + `status` ASC | Status por direção |
| `wa_contacts` | `is_archived` ASC + `last_message_at` DESC | Contatos ativos por recência |
| `wa_transfer_log` | `contact_id` ASC + `created_at` DESC | Histórico de transferências |

---

## 5. Rotas da API (42+ endpoints)

### 5.1 Autenticação & Sessão

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/login` | Login legado (username/password → JWT) |
| GET | `/api/session` | Sessão atual (Firebase token ou JWT) |
| GET | `/api/client-config` | Config do cliente (Firebase keys, features) |

### 5.2 WhatsApp — Contatos

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/wa/contacts` | Listar todos os contatos |
| GET | `/api/wa/contact/{id}` | Detalhes de um contato |
| POST | `/api/wa/contact/{id}/avatar` | Upload avatar do contato |
| PUT | `/api/wa/contact/{id}/qualify` | Qualificar contato |
| POST | `/api/wa/contact/{id}/read` | Marcar como lido |
| DELETE | `/api/wa/contact/{id}` | Arquivar contato |
| POST | `/api/wa/contact/{id}/restore` | Restaurar contato |

### 5.3 WhatsApp — Mensagens

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/wa/messages/{contact_id}` | Histórico de mensagens |
| POST | `/api/wa/send` | Enviar texto |
| POST | `/api/wa/send-media` | Enviar imagem/vídeo/documento |
| POST | `/api/wa/send-audio` | Enviar áudio |
| POST | `/api/wa/send-location` | Enviar localização |
| POST | `/api/wa/send-template` | Enviar template (janela 24h) |
| POST | `/api/wa/messages/{id}/transcribe` | Transcrever áudio |

### 5.4 WhatsApp — Transferências

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/wa/transfer` | Transferir contato para operador/setor |
| POST | `/api/wa/assume/{contact_id}` | Assumir contato da fila |
| GET | `/api/wa/transfer-history/{id}` | Histórico de transferências |

### 5.5 Google Chat

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/webhooks/google-chat` | Webhook recebimento (JWT) |
| GET | `/api/gc/conversations` | Listar conversas |
| GET | `/api/gc/messages/{id}` | Mensagens de uma conversa |
| POST | `/api/gc/send` | Enviar mensagem |
| POST | `/api/gc/mark-read/{id}` | Marcar como lida |
| GET | `/api/gc/spaces` | Listar espaços do Chat |

### 5.6 Administração & Lookup

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/admin/users` | Criar usuário |
| PUT | `/api/admin/users/{id}` | Atualizar cargo/setor |
| DELETE | `/api/admin/users/{id}` | Desativar usuário |
| GET | `/api/operators` | Listar operadores |
| GET | `/api/departments` | Listar departamentos |
| GET | `/api/users` | Listar todos os usuários |
| GET | `/api/qualifications` | Opções de qualificação |
| GET | `/api/admin/roles` | Cargos disponíveis |

### 5.7 Configurações

| Método | Rota | Descrição |
|--------|------|-----------|
| GET/PUT | `/api/settings/system` | Configurações globais (admin) |
| GET/PUT | `/api/settings/user` | Configurações pessoais |

### 5.8 Mídia & Webhooks

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/media/{subdir}/{filename}` | Servir arquivo de mídia |
| GET | `/webhook` | Verificação webhook Meta |
| POST | `/webhook` | Receber mensagens WhatsApp |
| POST | `/api/profile/avatar` | Upload avatar operador |
| DELETE | `/api/profile/avatar` | Remover avatar |

---

## 6. Integrações Externas

### 6.1 Meta WhatsApp Business API (Graph API v22.0)

- **Autenticação:** Bearer token (`WHATSAPP_TOKEN`)
- **Webhook:** HMAC-SHA256 com `WHATSAPP_APP_SECRET`
- **Operações:** Receber/enviar mensagens, download/upload mídia, templates
- **Formatos suportados:** Texto, imagem, áudio, vídeo, documento, sticker, localização, contatos, reações

### 6.2 Firebase / Google Cloud

- **Firebase Auth:** Login com Google (signInWithPopup), verificação de ID tokens
- **Firestore:** Banco principal, snapshots real-time, regras de segurança
- **Cloud Storage:** Armazenamento de mídia (alternativo)
- **Cloud Run:** Plataforma de deploy (southamerica-east1)

### 6.3 Google Chat API

- **Autenticação:** Service account OAuth2
- **Escopos:** `chat.messages`, `chat.spaces.readonly`, `chat.memberships.readonly`
- **Webhook:** JWT RS256 validado contra certificados públicos do Google
- **Feature flag:** `FEATURE_GOOGLE_CHAT` (desabilitado por padrão)

### 6.4 Faster Whisper

- **Modelo:** `base` (configurável: tiny → large-v3)
- **Device:** CPU com int8 (configurável para CUDA)
- **Idioma:** pt-BR
- **Pré-processamento:** FFmpeg converte para WAV 16kHz mono
- **Feature flag:** `FEATURE_AUDIO_TRANSCRIPTION`

---

## 7. Real-Time: Snapshots vs Polling

O sistema suporta **dois modos de transporte** configuráveis:

### Modo Snapshot (padrão)
- React conecta diretamente ao Firestore via `onSnapshot()`
- Atualizações instantâneas quando backend grava no Firestore
- Usa cache IndexedDB no navegador para acesso offline
- Coleções monitoradas: `wa_contacts`, `wa_messages`, `gc_conversations`, `gc_messages`

### Modo Polling (fallback)
- React faz requests HTTP periódicos ao backend
- Intervalo configurável (`polling_interval_ms`, padrão 15s)
- Endpoints: `/api/wa/contacts`, `/api/wa/messages/{id}`
- Usado quando Firestore não está disponível

**Decisão em runtime:** `config.data_backend === "firestore" && config.snapshot_enabled && firebaseReady(config)`

---

## 8. Sistema de Mídia

### 3 Backends de Storage

| Backend | Config | Uso |
|---------|--------|-----|
| **Local** | `MEDIA_STORAGE_BACKEND=local` | Desenvolvimento (filesystem) |
| **GCS** | `MEDIA_STORAGE_BACKEND=gcs` | Produção (Cloud Storage bucket) |
| **Firestore** | `MEDIA_STORAGE_BACKEND=firestore` | Alternativa (chunks + compressão) |

### Fluxo de Download (inbound)
```
Meta Graph API → get_media_url(media_id) → download bytes → store no backend
```

### Fluxo de Upload (outbound)
```
Operador upload → save_upload_media() → upload_media_to_whatsapp() → Meta envia
```

### Conversão de Áudio
- Entrada: WebM, MP3, MP4, OGG (do navegador)
- Saída: OGG/Opus 48kHz mono 48kbps (formato WhatsApp)
- Ferramenta: FFmpeg

### Subdiretórios
```
/media/images/
/media/audio/
/media/video/
/media/documents/
/media/stickers/
/media/avatars/
```

---

## 9. Segurança

### Autenticação
- **Firebase Auth:** OAuth2/OpenID Connect via Google
- **Legacy:** bcrypt 12 rounds + JWT HS256
- **Lockout:** 5 tentativas → bloqueio 300s
- **Auto-provisão:** Novos emails do domínio permitido são criados automaticamente

### Autorização (Firestore Rules)
- **Estado atual:** Whitelist de emails (modo demo/teste)
- **Planejado:** RBAC por cargo + departamento
- **Coleções sensíveis** (`users`, `audit_log`, `_meta`): bloqueadas para o frontend

### Webhook Security
- **WhatsApp:** HMAC-SHA256 com App Secret
- **Google Chat:** JWT RS256 com certificados públicos do Google
- **Config:** `REQUIRE_WEBHOOK_SIGNATURE` pode desabilitar em dev

### CORS
- Restrito a `CORS_ORIGINS` (padrão: localhost:8080)

---

## 10. Deploy

### Docker Multi-Stage
```
Stage 1: Node 22-slim → npm run build → frontend_dist/
Stage 2: Python 3.10-slim + gcc + ffmpeg → pip install → uvicorn
```

### Cloud Run
- **Região:** `southamerica-east1`
- **Service:** `castro-crm`
- **Workers:** 1 (Uvicorn single worker)
- **Porta:** 8080
- **Credenciais:** ADC (Application Default Credentials)
- **Detecção:** `K_SERVICE` env var

### Local
- `docker-compose up` com volume para `/data`
- `.env` para configuração

---

## 11. Frontend — State Management

O frontend usa **Context API** (sem Redux/Zustand) com um único provider `CrmContext` que gerencia ~100 variáveis de estado:

### Componentes Principais
| Componente | Responsabilidade |
|-----------|-----------------|
| `BootScreen` | Splash de inicialização |
| `LoginScreen` | Login Google OAuth |
| `TopBar` | Header (usuário, tema, settings, gchat) |
| `NavBar` | Navegação lateral (Novos, Meus, N/Q, Equipe) |
| `ContactList` | Lista de contatos com filtros e busca |
| `ChatPanel` | Área de chat (mensagens, composer, mídia) |
| `DetailPanel` | Qualificação, transferência, admin de usuários |
| `InternalChatPanel` | Painel slide-in do Google Chat |
| `Lightbox` | Visualizador de mídia (imagem/vídeo) |

### Views do CRM
| View | Filtro | Descrição |
|------|--------|-----------|
| `novos` | `qualification == "novo"` + sem operador | Leads novos na fila |
| `meus` | `assigned_to_uid == currentUser` | Meus atendimentos |
| `nao_qualificados` | `qualification == "nao_qualificado"` | Descartados |
| `equipe` | Todos + filtro por operador | Visão supervisão |

---

## 12. Pontos de Atenção Identificados

### Performance
- **Leituras Firestore excessivas** — Snapshots sem `.limit()` adequado causaram 80k+ leituras em teste com 2 usuários. Otimizações aplicadas em 27/03, mas ainda requer monitoramento.
- **Frontend monolítico** — `App.tsx` (658 linhas) e `CrmContext.tsx` (978 linhas) precisam de componentização.

### Segurança
- **Rules em modo demo** — Firestore rules usam whitelist de email hardcoded. Precisa migrar para RBAC por role/departamento antes de produção.
- **Secrets históricos** — Credenciais foram expostas em commits anteriores. Rotação de tokens já recomendada.

### Funcionalidade
- **Google Chat attachments** — Path de download de anexos precisa validação antes de produção.
- **Janela de 24h Meta** — Sistema verifica janela de mensagens mas template sending precisa de mais testes.
- **Single worker** — Uvicorn roda com 1 worker, limitando concorrência em picos.

### Custos Estimados (produção)
- **Firestore:** ~1.67M leituras/mês (free tier: 1.5M) → ~$0.06-0.10 excedente
- **Cloud Run:** $5-15/mês (principal custo)
- **Cloud Storage:** 4-13 GB/mês para mídia
- **Total estimado:** $5-19 USD/mês

---

## 13. Diagrama de Dependências entre Módulos

```
main.py
├── config.py
├── auth.py
│   ├── config.py
│   ├── database.py
│   └── firebase_admin_client.py
├── database.py
│   └── database_firestore.py
│       ├── firestore_common.py
│       │   └── firebase_admin_client.py
│       ├── config.py
│       └── media.py
├── webhook.py
│   ├── config.py
│   ├── database.py
│   ├── media.py
│   └── transcription_service.py
├── webhook_google_chat.py
│   ├── config.py
│   ├── database.py
│   ├── google_chat.py
│   └── media.py
├── google_chat.py
│   └── config.py
├── media.py
│   ├── config.py
│   └── firestore_common.py
├── transcription_service.py
│   └── config.py (env vars)
├── init_db.py
│   ├── database.py
│   └── bootstrap_data.py
└── firebase_admin_client.py
    └── config.py
```

---

## 14. Resumo Executivo

O Castro Intelligence CRM é um sistema **funcional e bem estruturado** para atendimento WhatsApp Business com integração Google Chat. A arquitetura é centrada no **Firestore como single source of truth**, com o React consumindo dados em real-time via snapshots e o FastAPI atuando como **camada de orquestração** (webhooks, Meta API, autenticação, mídia).

**Pontos fortes:**
- Arquitetura clara de separação backend/frontend
- Suporte a múltiplos backends de storage
- Real-time robusto com fallback para polling
- Feature flags para rollout gradual
- Custo operacional baixo (~$5-19/mês)

**Próximos passos recomendados:**
1. Endurecer Firestore rules (sair do modo whitelist)
2. Componentizar frontend (quebrar App.tsx e CrmContext)
3. Monitorar leituras Firestore em produção
4. Validar fluxo de anexos Google Chat
5. Considerar CI/CD pipeline (inexistente atualmente)
