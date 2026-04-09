# Arquitetura Completa - Castro Intelligence CRM

**Atualizado em:** 2026-04-08
**Proposito:** Documento de referencia para dar contexto ao Claude ou qualquer desenvolvedor em conversas futuras.

---

## 1. Visao Geral

Castro Intelligence e um CRM de atendimento via WhatsApp **multi-canal** que integra diretamente com a API Cloud da Meta (sem Twilio). O sistema permite que multiplos operadores atendam clientes via WhatsApp com controle, auditoria e rastreabilidade completa.

Suporta dois tipos de canais simultaneamente:
- **Canal Standard (Cloud API):** Numero compartilhado da empresa com bot futuro para novos leads
- **Canal Coexistence:** Numeros pessoais dos operadores (WhatsApp Business App continua no celular)

**Stack:**
- **Backend:** Python 3.10 + FastAPI + Uvicorn
- **Frontend:** React 18 + TypeScript + Vite
- **Banco de Dados:** Google Firestore
- **Autenticacao:** Firebase Auth (Google Sign-In)
- **Deploy:** Docker + Google Cloud Run
- **Midia:** Google Cloud Storage (producao) / local (dev)
- **WhatsApp:** Meta Cloud API v22.0

---

## 2. Estrutura de Diretorios

```
castro-intelligence/
├── main.py                    # FastAPI - 50+ endpoints, entry point do backend
├── config.py                  # Configuracoes via .env, validacoes
├── auth.py                    # Firebase Auth
├── channel_service.py         # Registry de canais WhatsApp (multi-canal)
├── database.py                # Router: reexporta database_firestore
├── database_firestore.py      # Implementacao Firestore (unica ativa)
├── webhook.py                 # Processamento de webhooks da Meta (multi-canal)
├── media.py                   # Download, conversao e storage de midia (multi-canal)
├── transcription_service.py   # Transcricao de audio (opcional)
├── firestore_common.py        # Helpers do Firestore (collection names, refs)
├── firebase_admin_client.py   # Inicializacao Firebase Admin SDK
├── bootstrap_data.py          # Seed de departamentos padrao
├── check_whatsapp_coexistence.py  # Diagnostico do provisionamento Meta
├── test_meta_app_review.py    # Testes para validacao do app na Meta
├── requirements.txt           # Dependencias Python
│
├── frontend/                  # React + TypeScript + Vite
│   └── src/
│       ├── App.tsx            # Componentes principais (CRM + admin + dashboard)
│       ├── context/CrmContext.tsx  # Estado central React Context
│       ├── api.ts             # Cliente HTTP (getJson, sendJson, putJson, deleteJson)
│       ├── firebase.ts        # Inicializacao Firebase SDK
│       ├── types.ts           # Tipos TypeScript (Channel, Contact, ChatMessage, etc.)
│       ├── styles.css         # Estilos
│       └── main.tsx           # Entry point React
│
├── frontend_dist/             # Build compilado (servido pelo FastAPI)
├── media/                     # Armazenamento local de midia
├── docs/                      # Documentacao
├── Dockerfile                 # Build multi-stage (Node + Python)
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
    ├── Extrai phone_number_id do metadata
    ├── Resolve canal via channel_service (standard ou coexistence)
    ├── Se tem midia: baixa via Media API usando token do canal
    ├── upsert_wa_contact(channel_id, auto_assign_user_id)
    │     ├── Canal standard: assigned_to=null (fila "Novos")
    │     └── Canal coexistence: auto-atribui ao operador dono
    ├── save_wa_message(channel_id, phone_number_id)
    ├── Incrementa unread_count + audit_metrics
    ├── Se lead convertido: captura rating (1-10) ou reroute ao operador original
    └── Se audio: transcreve (STT)
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
    ├── _resolve_channel_creds(contact) -> token, phone_id do canal correto
    ├── Se audio: FFmpeg converte WebM -> OGG/Opus
    ├── Se midia: upload para Meta via API (usando token do canal)
    ├── Envia mensagem via Meta Graph API (usando credenciais do canal)
    ├── save_wa_message(channel_id) -> salva no Firestore com status="sent"
    ├── increment_audit_metrics() -> metricas diarias
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
    └── log_audit() -> registra transferencia
    |
    v
Novo operador ve o contato na sua fila
```

### 3.4 Fluxo de Avaliacao (pos-conversao)

```
Operador marca contato como "convertido"
    |
    v
qualify_contact():
    ├── Grava converted_by_user_id
    ├── Envia template de avaliacao (1-10) via canal do contato
    └── Mensagem com visibility="admin_only" (operadores nao veem)
    |
    v
Cliente responde com numero 1-10
    |
    v
webhook.py:
    ├── Detecta rating pendente
    ├── Captura nota e grava no contato
    └── Marca resposta como admin_only
```

### 3.5 Lead Convertido Retornante

```
Lead ja convertido envia nova mensagem
    |
    v
webhook.py:
    ├── Detecta qualification="convertido" e sem rating pendente
    ├── Reatribui ao original_operator_id
    └── Muda qualification para "em_atendimento"
    |
    v
Operador original ve o lead em "Meus Atendimentos"
```

---

## 4. Colecoes do Firestore

Todas as colecoes usam o prefixo `castro_crm_` (configuravel via `FIRESTORE_COLLECTION_PREFIX`).

### 4.1 Colecoes Publicas (Frontend pode ler)

| Colecao | Chave Doc | Descricao |
|---------|-----------|-----------|
| `castro_crm_operator_profiles` | Firebase UID | Perfis de operadores (espelho read-only para o frontend) |
| `castro_crm_departments` | ID numerico | Departamentos (Comercial, Suporte, etc.) — CRUD via admin |
| `castro_crm_wa_contacts` | ID numerico | Contatos WhatsApp (channel_id, assigned_to, qualification, rating) |
| `castro_crm_wa_messages` | ID numerico | Mensagens WhatsApp (channel_id, visibility, is_rating_message) |
| `castro_crm_wa_transfer_log` | ID numerico | Historico de transferencias entre operadores |

### 4.2 Colecoes Privadas (Somente backend)

| Colecao | Chave Doc | Descricao |
|---------|-----------|-----------|
| `castro_crm_channels` | ID numerico | Canais WhatsApp conectados (standard + coexistence) |
| `castro_crm_users` | ID numerico | Contas de usuario (role, department_id, email) |
| `castro_crm_audit_log` | ID numerico | Log de auditoria (acoes do sistema) |
| `castro_crm_audit_metrics` | date ou date_userId | Metricas diarias pre-agregadas (dashboard) |
| `castro_crm_wa_message_status` | ID numerico | Historico de status de entrega (sent/delivered/read) |
| `castro_crm_system_settings` | "config" | Configuracoes globais do sistema |
| `castro_crm_user_settings` | user_id | Configuracoes por usuario |
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

## 6. Endpoints da API (50+ total)

### Autenticacao e Config
| Metodo | Rota | Descricao |
|--------|------|-----------|
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

### WhatsApp - Envio (multi-canal: usa credenciais do canal do contato)
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
| PUT | `/api/wa/contact/{id}/qualify` | Qualificar contato (envia rating se convertido) |
| DELETE | `/api/wa/contact/{id}` | Arquivar contato |
| POST | `/api/wa/contact/{id}/restore` | Restaurar contato |
| POST | `/api/wa/contact/{id}/return-to-bot` | Devolver ao bot (admin/supervisor) |
| POST | `/api/wa/transfer` | Transferir atendimento |
| POST | `/api/wa/assume/{contact_id}` | Assumir contato (grava original_operator_id) |
| POST | `/api/wa/messages/{id}/transcribe` | Transcrever audio |

### Admin - Usuarios
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/operators` | Listar operadores ativos |
| POST | `/api/admin/users` | Criar usuario |
| PUT | `/api/admin/users/{id}` | Editar usuario |
| DELETE | `/api/admin/users/{id}` | Desativar usuario |
| GET | `/api/admin/roles` | Listar roles |
| POST | `/api/admin/bulk-reassign` | Reatribuicao em lote |

### Admin - Departamentos
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/departments` | Listar departamentos |
| POST | `/api/admin/departments` | Criar departamento |
| PUT | `/api/admin/departments/{id}` | Editar departamento |
| DELETE | `/api/admin/departments/{id}` | Remover departamento |

### Admin - Canais WhatsApp
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/admin/channels` | Listar canais |
| POST | `/api/admin/channels` | Criar canal |
| PUT | `/api/admin/channels/{id}` | Editar canal |
| DELETE | `/api/admin/channels/{id}` | Desativar canal |

### Admin - Dashboard e Export
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/admin/dashboard/summary` | Metricas agregadas + peak chart |
| GET | `/api/admin/dashboard/ratings` | Avaliacoes de atendimento |
| GET | `/api/admin/export` | Export CSV/JSON de contatos |

### Admin - Configuracoes
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET/PUT | `/api/settings/system` | Configuracoes globais |
| GET/PUT | `/api/settings/user` | Configuracoes pessoais |

### Admin - Embedded Signup (Coexistence)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/api/admin/embedded-signup/config` | Config para FB SDK |
| POST | `/api/admin/embedded-signup/exchange` | Troca code → token + cria canal |

### Webhook
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET/POST | `/webhook` | Webhook da Meta (multi-canal) |

---

## 7. Frontend (React)

### Estrutura Atual

O frontend usa React Context (`CrmContext.tsx`) para estado centralizado e `App.tsx` para os componentes visuais.

### Funcionalidades Implementadas
- Login via Google (Firebase Auth popup)
- Lista de contatos em tempo real (snapshot ou polling)
- 4 abas de navegacao: Novos, Meus Atendimentos, Nao Qualificados, Equipe
- Chat com mensagens em tempo real
- Envio de texto, imagens, audio gravado, localizacao, templates
- Qualificacao de contatos (novo, em_atendimento, qualificado, nao_qualificado, convertido)
- Transferencia de atendimento entre operadores e departamentos
- Indicador de canal (badge "coex" para coexistence)
- Filtragem de mensagens admin_only (rating) para operadores comuns
- Contatos coexistence de outros ocultos para operadores comuns
- Visualizador de imagens/videos (lightbox)
- Tema claro/escuro
- Avatares de operadores e contatos
- Status de mensagens (enviado, entregue, lido)
- Paginacao de mensagens (scroll carrega mais)
- Rating badge no painel de detalhes (color-coded 1-10)
- Botao "Devolver ao bot" (admin/supervisor)
- Reatribuicao em lote de contatos
- Admin: CRUD de departamentos, visualizacao de canais, config do sistema
- Dashboard de auditoria: metricas, grafico de pico, tabela por operador, ratings, export CSV
- Embedded Signup para conectar numeros coexistence
- Quick messages (atalhos de texto)
- Transcricao de audio inbound

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

## 12. Problemas Conhecidos e Proximos Passos

1. **Token temporario** - O token no Secret Manager expira em horas; precisa de System User Token permanente
2. **Template de avaliacao** - Template `rating_request` ainda nao criado/aprovado na Meta
3. **Numero de teste** - So envia, nao recebe inbound; precisa de numero real para fluxo completo
4. **Indices compostos Firestore** - Falta `firestore.indexes.json` para queries com `channel_id`
5. **Sem CI/CD** - Deploy manual via gcloud
6. **App.tsx grande** - Decomposicao incremental recomendada ao tocar cada area
7. **Regras de seguranca temporarias** - Nao filtram por departamento/atribuicao
