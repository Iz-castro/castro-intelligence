# Arquitetura Completa - Castro Intelligence CRM

**Data:** 2026-03-21
**Proposito:** Documento de referencia para dar contexto ao Claude ou qualquer desenvolvedor em conversas futuras.

---

## 1. Visao Geral

Castro Intelligence e um CRM de atendimento via WhatsApp que integra diretamente com a API Cloud da Meta (sem Twilio). O sistema permite que operadores recebam, respondam e gerenciem conversas de WhatsApp em tempo real.

**Stack:**
- **Backend:** Python 3.10 + FastAPI + Uvicorn
- **Frontend:** React 18 + TypeScript + Vite
- **Banco de Dados:** Google Firestore (migrado de Cloud SQL)
- **Autenticacao:** Firebase Auth (Google Sign-In)
- **Deploy:** Docker + Google Cloud Run
- **Midia:** Google Cloud Storage (producao) / local (dev)

---

## 2. Estrutura de Diretorios

```
castro-intelligence/
├── main.py                    # FastAPI - 42 endpoints, entry point do backend
├── config.py                  # Configuracoes via .env, validacoes
├── auth.py                    # Firebase Auth + Legacy JWT
├── database.py                # Router: seleciona backend (firestore ou sql)
├── database_firestore.py      # Implementacao Firestore (ATIVO)
├── database_sql.py            # Implementacao SQL (INATIVO, preservado)
├── webhook.py                 # Processamento de webhooks da Meta
├── media.py                   # Download, conversao e storage de midia
├── transcription_service.py   # Google Speech-to-Text (opcional)
├── firestore_common.py        # Helpers do Firestore (collection names, refs)
├── firebase_admin_client.py   # Inicializacao Firebase Admin SDK
├── bootstrap_data.py          # Seed de departamentos padrao
├── init_db.py                 # Inicializacao do banco
├── requirements.txt           # Dependencias Python
│
├── frontend/                  # React + TypeScript + Vite
│   └── src/
│       ├── App.tsx            # Componente principal (monolitico, ~52KB)
│       ├── api.ts             # Cliente HTTP (getJson, sendJson, etc.)
│       ├── firebase.ts        # Inicializacao Firebase SDK
│       ├── types.ts           # Tipos TypeScript
│       ├── styles.css         # Estilos
│       └── main.tsx           # Entry point React
│
├── frontend_dist/             # Build compilado (servido pelo FastAPI)
├── static/                    # Frontend legado (HTML/JS puro, fallback)
├── media/                     # Armazenamento local de midia
├── docs/                      # Documentacao
├── Dockerfile                 # Build multi-stage (Node + Python)
├── docker-compose.yml         # Dev local
├── deploy.sh / deploy.ps1     # Deploy para Cloud Run
├── firestore.rules            # Regras de seguranca Firestore
├── storage.rules              # Regras de seguranca Cloud Storage
└── .env / .env.example        # Variaveis de ambiente
```

---

## 3. Fluxo de Mensagens

### 3.1 Mensagem Recebida (Inbound)

```
Cliente envia WhatsApp
    |
    v
Meta Cloud API envia POST /webhook
    |
    v
webhook.py::process_webhook_payload()
    ├── Valida assinatura HMAC-SHA256
    ├── Extrai mensagem do payload Meta
    ├── Se tem midia: baixa via Media API da Meta
    ├── upsert_wa_contact() -> cria/atualiza contato no Firestore
    ├── save_wa_message() -> salva mensagem no Firestore
    ├── Incrementa unread_count no contato
    └── broadcast_to_operators() -> notifica via WebSocket (legado)
    |
    v
Frontend React detecta via:
    ├── Firestore onSnapshot (modo snapshot) -> atualiza automatico
    └── Polling /api/wa/contacts + /api/wa/messages (modo polling)
    |
    v
Operador ve a mensagem no CRM
```

### 3.2 Mensagem Enviada (Outbound)

```
Operador digita e envia no CRM
    |
    v
Frontend POST /api/wa/send (texto) ou /api/wa/send-media ou /api/wa/send-audio
    |
    v
main.py:
    ├── Valida token Firebase
    ├── Verifica atribuicao do contato
    ├── Se audio: FFmpeg converte WebM -> OGG/Opus
    ├── Se midia: upload para Meta via API
    ├── Envia mensagem via Meta Graph API
    ├── save_wa_message() -> salva no Firestore com status="sent"
    └── log_audit() -> registra no audit_log
    |
    v
Meta entrega ao cliente
    |
    v
Meta envia webhooks de status: sent -> delivered -> read
    |
    v
webhook.py::update_wa_message_status() -> atualiza status no Firestore
```

### 3.3 Transferencia de Atendimento

```
Operador clica "Transferir"
    |
    v
POST /api/wa/transfer { contact_id, to_user_id, to_department_id, reason, summary }
    |
    v
    ├── assign_wa_contact() -> atualiza assigned_to no contato
    ├── insert_transfer_system_message() -> mensagem de sistema no chat
    ├── Gera protocolo de atendimento
    ├── log_audit() -> registra transferencia
    └── broadcast_to_operators() -> notifica todos
    |
    v
Novo operador ve o contato na sua fila
```

---

## 4. Colecoes do Firestore

Todas as colecoes usam o prefixo `castro_crm_` (configuravel via `FIRESTORE_COLLECTION_PREFIX`).

### 4.1 Colecoes Publicas (Frontend pode ler)

| Colecao | Chave Doc | Descricao |
|---------|-----------|-----------|
| `castro_crm_operator_profiles` | Firebase UID | Perfis de operadores (espelho read-only para o frontend) |
| `castro_crm_departments` | ID numerico | Departamentos (Comercial, Suporte, etc.) |
| `castro_crm_wa_contacts` | ID numerico | Contatos WhatsApp (resumo da conversa, assigned_to, unread_count) |
| `castro_crm_wa_messages` | ID numerico | Mensagens WhatsApp (texto, midia, status, direction) |
| `castro_crm_wa_transfer_log` | ID numerico | Historico de transferencias entre operadores |

### 4.2 Colecoes Privadas (Somente backend)

| Colecao | Chave Doc | Descricao |
|---------|-----------|-----------|
| `castro_crm_users` | ID numerico | Contas de usuario (password_hash, role, email) |
| `castro_crm_messages` | ID numerico | Mensagens internas entre operadores |
| `castro_crm_internal_unread` | receiver_id_sender_id | Contadores de nao-lidas internas |
| `castro_crm_audit_log` | ID numerico | Log de auditoria (acoes do sistema) |
| `castro_crm_wa_message_status` | ID numerico | Historico de status de entrega (sent/delivered/read) |
| `castro_crm__meta` | "counters" | Contadores de sequencia para IDs numericos |

### 4.3 Sobre os IDs Numericos

Os documentos usam IDs sequenciais (1, 2, 3...) gerados pelo campo `counters` na colecao `__meta`. Isso foi herdado da migracao do SQL onde os IDs eram auto-increment. O sistema funciona assim:

```python
def next_sequence(collection_name):
    # Incrementa atomicamente o contador em __meta/counters
    # Retorna o proximo numero
```

---

## 5. Autenticacao

### Modo Atual: Firebase Auth

1. Frontend abre popup Google Sign-In via Firebase SDK
2. Firebase retorna ID Token
3. Frontend envia token como `Authorization: Bearer <ID_TOKEN>` em todas as requisicoes
4. Backend valida token com `firebase-admin` SDK
5. Verifica se email esta na lista/dominio permitido
6. Auto-provisiona usuario e cria `operator_profiles/{uid}` se necessario

**Emails permitidos (temporario):**
- `rafaluisc@outlook.com`
- `izaeldecastro@gmail.com`
- `*@centralloc.com.br`

### Modo Legado: JWT (desativado)

Existe implementacao completa de login por username/password com JWT (HS256). Ativavel trocando `AUTH_MODE=legacy`. Usado quando o backend era SQL.

---

## 6. Endpoints da API (42 total)

### Autenticacao
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/api/login` | Login legado (JWT) |
| GET | `/api/session` | Sessao atual do usuario |
| GET | `/api/client-config` | Configuracao do frontend (Firebase keys, colecoes) |

### WhatsApp - Leitura
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/wa/contacts` | Lista contatos WhatsApp |
| GET | `/api/wa/messages/{contact_id}` | Historico de mensagens |
| GET | `/api/wa/contact/{contact_id}` | Detalhes de um contato |
| GET | `/api/wa/qualifications` | Lista qualificacoes possiveis |
| GET | `/api/wa/transfer-history/{contact_id}` | Historico de transferencias |

### WhatsApp - Envio
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/api/wa/send` | Enviar texto |
| POST | `/api/wa/send-media` | Enviar imagem/video/documento |
| POST | `/api/wa/send-audio` | Enviar audio gravado (WebM -> OGG) |
| POST | `/api/wa/send-location` | Enviar localizacao |
| POST | `/api/wa/send-template` | Enviar template |

### WhatsApp - Gestao
| Metodo | Rota | Descricao |
|--------|------|-----------|
| PUT | `/api/wa/contact/{id}/qualify` | Qualificar contato |
| DELETE | `/api/wa/contact/{id}` | Arquivar contato |
| POST | `/api/wa/contact/{id}/restore` | Restaurar contato |
| POST | `/api/wa/transfer` | Transferir atendimento |
| POST | `/api/wa/assume/{contact_id}` | Assumir contato |
| POST | `/api/wa/messages/{id}/transcribe` | Transcrever audio |

### Admin
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `/api/admin/users` | Criar usuario |
| PUT | `/api/admin/users/{id}` | Editar usuario |
| DELETE | `/api/admin/users/{id}` | Deletar usuario |
| GET | `/api/admin/roles` | Listar roles |

### Outros
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/users` | Listar usuarios |
| GET | `/api/departments` | Listar departamentos |
| GET | `/api/operators` | Listar operadores ativos |
| GET/POST | `/webhook` | Webhook da Meta |
| WS | `/ws/{token}` | WebSocket (legado) |

---

## 7. Frontend (React)

### Estrutura Atual

O frontend e um **componente monolitico** em `App.tsx` (~52KB). Contem tudo: autenticacao, lista de contatos, chat, qualificacao, transferencia, tema, etc.

### Funcionalidades Implementadas
- Login via Google (Firebase Auth popup)
- Lista de contatos em tempo real (snapshot ou polling)
- Chat com mensagens em tempo real
- Envio de texto, imagens, audio gravado, localizacao
- Qualificacao de contatos (novo, em_atendimento, qualificado, etc.)
- Transferencia de atendimento entre operadores
- Visualizador de imagens/videos (lightbox)
- Tema claro/escuro
- Avatares de operadores e contatos
- Status de mensagens (enviado, entregue, lido)
- Paginacao de mensagens (20 por vez, scroll carrega mais)

### Funcionalidades NAO Implementadas
- UI de administracao de usuarios
- Chat interno entre operadores
- Exibicao de transcricao de audio
- Busca/filtros avancados de contatos

### Modos de Transporte
- **Snapshot** (padrao com Firestore): `onSnapshot` direto no Firestore
- **Polling** (fallback): Requisicoes HTTP a cada 5 segundos

---

## 8. Deploy

### Producao: Google Cloud Run

```bash
./deploy.sh  # ou deploy.ps1 no Windows
```

O script:
1. Le variaveis do `.env`
2. Habilita APIs do GCP (Firestore, Storage, Cloud Run, etc.)
3. Cria service account com permissoes
4. Configura secrets no Secret Manager
5. Faz build e deploy do container para Cloud Run

### Desenvolvimento Local

```bash
docker compose up --build
# ou
python main.py  # direto com uvicorn
```

### Dockerfile (Multi-stage)
1. **Stage 1 (Node 22):** Compila frontend React com Vite
2. **Stage 2 (Python 3.10):** Instala backend + copia frontend compilado
3. Instala FFmpeg para conversao de audio
4. Expoe porta 8080

---

## 9. Dependencias Principais

### Backend (Python)
| Pacote | Versao | Uso |
|--------|--------|-----|
| fastapi | 0.115.0 | Framework web |
| uvicorn | 0.30.0 | Servidor ASGI |
| httpx | 0.27.0 | Cliente HTTP async (Meta API) |
| google-cloud-firestore | 2.19.0 | Firestore SDK |
| firebase-admin | 6.7.0 | Firebase Admin (auth, provisioning) |
| google-cloud-storage | 2.18.2 | Cloud Storage (midia) |
| google-cloud-speech | 2.36.1 | Speech-to-Text |
| SQLAlchemy | 2.0.36 | SQL engine (inativo) |
| pg8000 | 1.31.2 | Driver PostgreSQL (inativo) |
| bcrypt | 4.2.0 | Hash de senhas (modo legado) |
| PyJWT | 2.9.0 | Tokens JWT (modo legado) |
| pyngrok | 7.2.2 | Tunnel ngrok (dev) |

### Frontend (Node)
| Pacote | Versao | Uso |
|--------|--------|-----|
| react | 18.3.1 | UI framework |
| firebase | 11.0.2 | Firebase SDK (auth + firestore) |
| vite | 5.4.10 | Build tool |
| typescript | 5.6.3 | Tipagem |

---

## 10. Variaveis de Ambiente Criticas

| Variavel | Descricao |
|----------|-----------|
| `DATA_BACKEND` | `firestore` (ativo) ou `sql` |
| `AUTH_MODE` | `firebase` (ativo) ou `legacy` |
| `FIRESTORE_PROJECT_ID` | ID do projeto GCP |
| `FIRESTORE_COLLECTION_PREFIX` | Prefixo das colecoes (`castro_crm`) |
| `WHATSAPP_TOKEN` | Token de acesso da Meta API |
| `WHATSAPP_PHONE_NUMBER_ID` | ID do telefone no Meta Business |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificacao do webhook |
| `WHATSAPP_APP_SECRET` | Secret do app Meta (validacao HMAC) |
| `FIREBASE_WEB_API_KEY` | API key do Firebase para o frontend |
| `FIREBASE_WEB_AUTH_DOMAIN` | Dominio de autenticacao Firebase |
| `ALLOWED_FIREBASE_EMAILS` | Lista de emails permitidos |
| `ALLOWED_FIREBASE_EMAIL_DOMAIN` | Dominio de email permitido |
| `MEDIA_STORAGE_BACKEND` | `local`, `gcs`, ou `firestore` |
| `GCS_MEDIA_BUCKET` | Bucket do Cloud Storage para midia |
| `CHAT_DELIVERY_MODE` | `snapshot` ou `polling` |
| `POLLING_INTERVAL_MS` | Intervalo de polling em ms (padrao: 5000) |

---

## 11. Regras de Seguranca (Firestore)

**Status atual: TEMPORARIO / DESENVOLVIMENTO**

- Emails hardcoded na allowlist
- Contatos e mensagens WhatsApp: leitura liberada para emails permitidos (sem filtro por departamento/atribuicao)
- Todas as escritas bloqueadas (somente backend escreve)
- Colecoes privadas (users, audit_log) completamente bloqueadas

**Necessario para producao:**
- Substituir allowlist por validacao de dominio
- Implementar filtro por departamento e atribuicao nos contatos
- Considerar custom claims no Firebase Auth para roles

---

## 12. Problemas Conhecidos

1. **Leituras excessivas no Firestore** - Detalhado em `docs/analise-leituras-firestore.md`
2. **Frontend monolitico** - App.tsx com ~52KB precisa ser componentizado
3. **Codigo SQL preservado** - `database_sql.py` e dependencias SQL inativas no requirements.txt
4. **Regras de seguranca temporarias** - Nao prontas para producao
5. **Sem CI/CD** - Deploy manual via scripts
6. **Sem indices compostos** - Falta `firestore.indexes.json`
7. **IDs sequenciais** - Herdados do SQL, funcionam mas nao sao a melhor pratica do Firestore
