# Castro Intelligence CRM — Documentacao Completa do Sistema

## 1. Visao Geral

CRM WhatsApp multi-canal para empresa do setor imobiliario. Permite que operadores atendam clientes via WhatsApp com controle, auditoria e rastreabilidade completa.

**Stack:**
- Backend: Python 3.10 + FastAPI + Uvicorn
- Banco de dados: Google Cloud Firestore
- Autenticacao: Firebase Auth (Google Sign-In + Email/Password opcional)
- Frontend: React 18 + TypeScript + Vite
- Midia: Google Cloud Storage (GCS)
- Deploy: Google Cloud Run (Docker)
- API WhatsApp: Meta Cloud API v22.0

**URL de producao:** https://castro-crm-286866630844.southamerica-east1.run.app

---

## 2. Arquitetura Multi-Canal

O sistema suporta dois tipos de canais WhatsApp simultaneamente:

### Canal Standard (Cloud API)
- Numero compartilhado da empresa
- Funciona como entrada de novos leads (fila do bot)
- Leads ficam em "Novos" ate um operador assumir (ou o bot rotear para um departamento)
- Flag `is_bot_enabled=true` habilita o bot para responder automaticamente no canal

### Canal Coexistence
- Numero pessoal do operador (WhatsApp Business App continua no celular)
- Mensagens sao auto-atribuidas ao operador dono do numero
- Aparecem direto em "Meus Atendimentos" do operador
- Admin/Supervisor consegue ver todas as mensagens
- Operadores comuns NAO veem coexistence de outros

### Registro de Canais
- Colecao Firestore: `castro_crm_channels`
- Modulo: `channel_service.py` com cache em memoria (TTL 60s)
- Bootstrap automatico: cria canal default a partir das env vars no startup
- Embedded Signup cria canais coexistence automaticamente

---

## 3. Roles e Permissoes

| Funcionalidade | Admin | Supervisor | Operador |
|---|---|---|---|
| Enviar/receber mensagens | Sim | Sim | Sim |
| Assumir contatos | Sim | Sim | Sim |
| Transferir contatos | Sim | Sim | Sim |
| Qualificar contatos | Sim | Sim | Sim |
| Ver "Equipe" (contatos de outros) | Sim | Sim | Nao |
| Ver coexistence de outros | Sim | Sim | Nao |
| Criar/editar usuarios | Sim | Sim | Nao |
| Desativar usuarios | Sim | Nao | Nao |
| Criar/editar departamentos | Sim | Sim | Nao |
| Remover departamentos | Sim | Nao | Nao |
| Gerenciar canais WhatsApp | Sim | Sim | Nao |
| Dashboard de auditoria | Sim | Sim | Nao |
| Exportar dados (CSV) | Sim | Sim | Nao |
| Devolver contato ao bot | Sim | Sim | Nao |
| Reatribuicao em lote | Sim | Sim | Nao |
| Configuracoes do sistema | Sim | Nao | Nao |
| Embedded Signup (coexistence) | Sim | Sim | Nao |
| Ver avaliacoes de atendimento | Sim | Sim | Nao |
| Ver mensagens de avaliacao | Sim | Sim | Nao |

---

## 4. Pipeline de Qualificacao

```
Novo → Em Atendimento → Qualificado → Convertido
                      ↘ Nao Qualificado
```

| Estagio | Descricao | Onde aparece |
|---|---|---|
| `novo` | Lead recem-chegado, sem operador | Aba "Novos" |
| `em_atendimento` | Operador assumiu o atendimento | Aba "Meus Atendimentos" |
| `qualificado` | Lead demonstrou interesse real | Aba "Meus Atendimentos" |
| `nao_qualificado` | Lead sem interesse / descartado | Aba "Nao Qualificados" |
| `convertido` | Venda fechada / objetivo atingido | Aba "Meus Atendimentos" |

### Ao marcar "Convertido":
1. Sistema grava `converted_by_user_id` (quem converteu)
2. Envia template de avaliacao (1-10) via WhatsApp
3. Mensagem de avaliacao fica invisivel para operadores (`visibility: admin_only`)
4. Quando o lead responde com um numero 1-10, o webhook captura a nota

### Lead Convertido Retornante:
- Se um lead ja convertido enviar nova mensagem, o sistema reatribui automaticamente ao operador original (`original_operator_id`)
- Muda qualificacao para `em_atendimento`

---

## 5. Fluxo de Mensagens

### Inbound (cliente → CRM)
```
WhatsApp → Meta Cloud API → Webhook POST /webhook
  → Validar assinatura HMAC-SHA256
  → Extrair phone_number_id do metadata
  → Resolver canal via channel_service
  → upsert_wa_contact (com auto-atribuicao se coexistence)
  → save_wa_message (com channel_id)
  → Atualizar audit_metrics
  → Se lead convertido: capturar rating ou reroute
  → Se audio: transcrever (Google STT)
```

### Outbound (CRM → cliente)
```
Operador clica "Enviar"
  → _resolve_channel_creds(contact) → token, phone_id do canal
  → POST Graph API /{phone_id}/messages
  → save_wa_message
  → Atualizar audit_metrics
```

---

## 6. Departamentos

Departamentos representam setores da empresa (Comercial, SAC, Financeiro, Cadastro, etc.).

- Admin/Supervisor pode criar, editar e remover departamentos
- Cada operador pertence a um departamento
- Contatos podem ser transferidos entre departamentos
- O bot roteia leads automaticamente para o departamento com `bot_key` correspondente

### Campo `bot_key` (roteamento do bot)

Cada departamento pode ter um `bot_key` opcional que liga o setor fixo do bot ao departamento real:

| `bot_key` | Setor do bot |
|---|---|
| `comercial` | Comercial (1) |
| `financeiro` | Financeiro (2) |
| `administrativo` | Administrativo (3) |
| `sac` | SAC (4) |
| `null` | Nao recebe do bot (so transferencias manuais) |

Se admin renomear o departamento, o `bot_key` continua igual e o roteamento do bot nao quebra. Qualquer mutacao em departamentos (create/update/delete) invalida o cache `_dept_cache` do bot automaticamente.

Se `bot_key` nao estiver definido, o bot cai em fallback para substring match no nome (ex: "Comercial" bate com "Departamento Comercial").

### Departamentos padrao (bootstrap):
| Nome | `bot_key` |
|---|---|
| Geral | `null` |
| Vendas | `comercial` |
| Suporte | `sac` |
| Financeiro | `financeiro` |

### Transferencia entre departamentos:
1. Operador seleciona contato
2. Escolhe operador destino e/ou departamento destino
3. Preenche motivo e resumo (obrigatorio)
4. Sistema registra no `wa_transfer_log` e insere mensagem de sistema

---

## 7. Dashboard de Auditoria

Acessivel por Admin/Supervisor via Configuracoes > Dashboard.

### Metricas disponiveis:
- **Total de leads recebidos** — contatos novos no periodo
- **Total de leads assumidos** — contatos que foram atribuidos a operadores
- **Mensagens recebidas (inbound)** — total geral
- **Mensagens enviadas (outbound)** — total geral
- **Total de mensagens** — soma de inbound + outbound

### Grafico de pico:
- Barras por intervalo de 30 minutos
- Visualizacao para identificar horarios de maior movimento

### Tabela por operador:
- Mensagens recebidas e enviadas por operador
- Leads assumidos por operador

### Tabela de avaliacoes:
- Nome do contato, nota (1-10), operador que converteu, data
- Notas color-coded: verde (7-10), amarelo (4-6), vermelho (1-3)

### Export:
- Botao "Exportar CSV" baixa arquivo com todos os contatos e metadados
- Filtro por intervalo de datas

---

## 8. Quando um Operador Sai da Empresa

### Opcoes para Admin/Supervisor:

**Contato por contato:**
- "Devolver ao bot" — contato volta para fila "Novos"
- Transferir para outro operador

**Em lote (secao "Reatribuicao em lote"):**
1. Selecionar operador de origem
2. Escolher acao:
   - "Devolver ao bot" — todos contatos voltam para "Novos"
   - "Transferir para operador X" — todos contatos vao para outro operador
3. Sistema registra transferencia e mensagem de sistema em cada contato

**Para canais coexistence:**
- Admin pode dar o numero para outro operador
- Ou deixar mensagens cairem na fila geral

---

## 9. API Endpoints

### Autenticacao e Sessao
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/session` | Dados do usuario logado | Todos |
| GET | `/api/client-config` | Config do Firebase e features | Todos |

### WhatsApp — Mensagens
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| POST | `/api/wa/send` | Enviar texto | Todos |
| POST | `/api/wa/send-media` | Enviar imagem/video/documento | Todos |
| POST | `/api/wa/send-audio` | Enviar audio gravado | Todos |
| POST | `/api/wa/send-location` | Enviar localizacao | Todos |
| POST | `/api/wa/send-template` | Enviar template | Todos |

### WhatsApp — Contatos
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/wa/contacts` | Listar contatos | Todos |
| GET | `/api/wa/contact/{id}` | Detalhe do contato | Todos |
| GET | `/api/wa/messages/{id}` | Mensagens do contato | Todos |
| PUT | `/api/wa/contact/{id}/qualify` | Alterar qualificacao | Todos |
| POST | `/api/wa/contact/{id}/read` | Marcar como lido | Todos |
| DELETE | `/api/wa/contact/{id}` | Arquivar contato | Todos |
| POST | `/api/wa/contact/{id}/restore` | Restaurar contato | Todos |
| POST | `/api/wa/contact/{id}/return-to-bot` | Devolver ao bot | Admin/Sup |

### WhatsApp — Transferencia
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| POST | `/api/wa/transfer` | Transferir contato | Todos |
| POST | `/api/wa/assume/{id}` | Assumir contato | Todos |
| GET | `/api/wa/transfer-history/{id}` | Historico de transferencias | Todos |

### Admin — Usuarios
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/operators` | Listar operadores | Todos |
| POST | `/api/admin/users` | Criar usuario | Admin/Sup |
| PUT | `/api/admin/users/{id}` | Editar usuario | Admin/Sup |
| DELETE | `/api/admin/users/{id}` | Desativar usuario | Admin |
| GET | `/api/admin/roles` | Listar roles | Todos |

### Admin — Departamentos
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/departments` | Listar departamentos | Todos |
| POST | `/api/admin/departments` | Criar departamento | Admin/Sup |
| PUT | `/api/admin/departments/{id}` | Editar departamento | Admin/Sup |
| DELETE | `/api/admin/departments/{id}` | Remover departamento | Admin |

### Admin — Canais WhatsApp
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/admin/channels` | Listar canais | Todos* |
| POST | `/api/admin/channels` | Criar canal | Admin/Sup |
| PUT | `/api/admin/channels/{id}` | Editar canal | Admin/Sup |
| DELETE | `/api/admin/channels/{id}` | Desativar canal | Admin |

*Operadores veem apenas canais que podem acessar (standard + proprios coexistence).

### Admin — Dashboard e Export
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/admin/dashboard/summary` | Metricas agregadas | Admin/Sup |
| GET | `/api/admin/dashboard/ratings` | Avaliacoes | Admin/Sup |
| GET | `/api/admin/export` | Export CSV/JSON | Admin/Sup |
| POST | `/api/admin/bulk-reassign` | Reatribuicao em lote | Admin/Sup |

### Admin — Configuracoes
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/settings/system` | Config do sistema | Todos |
| PUT | `/api/settings/system` | Alterar config | Admin |
| GET | `/api/settings/user` | Config do usuario | Todos |
| PUT | `/api/settings/user` | Alterar config pessoal | Todos |

### Admin — Embedded Signup
| Metodo | Rota | Descricao | Acesso |
|---|---|---|---|
| GET | `/api/admin/embedded-signup/config` | Config para FB SDK | Admin/Sup |
| POST | `/api/admin/embedded-signup/exchange` | Trocar code por token | Admin/Sup |

### Webhook
| Metodo | Rota | Descricao |
|---|---|---|
| GET | `/webhook` | Verificacao do webhook Meta |
| POST | `/webhook` | Receber eventos da Meta |

---

## 10. Colecoes Firestore

Todas as colecoes usam prefixo configuravel (default: `castro_crm_`).

### `channels`
Canal WhatsApp conectado ao sistema.
```
id: int
channel_type: "standard" | "coexistence"
label: str                      # "Bot Principal", "Timmy - +55 31 99999"
waba_id: str
phone_number_id: str
display_phone_number: str
access_token: str               # token por canal
owner_user_id: int | null       # null = compartilhado, int = coexistence
owner_firebase_uid: str
default_department_id: int | null
is_bot_enabled: bool
is_active: bool
webhook_subscribed: bool
created_at, updated_at: datetime
```

### `wa_contacts`
Contato WhatsApp (lead/cliente).
```
id: int
wa_id: str                      # numero do cliente (ex: 5531999990000)
display_name: str
phone_formatted: str            # +55 (31) 99999-0000
qualification: str              # novo|em_atendimento|qualificado|nao_qualificado|convertido
notes: str
assigned_to: int | null         # user.id do operador
assigned_to_uid: str            # firebase_uid do operador
department_id: int | null
channel_id: int | null          # canal que recebeu este contato
phone_number_id: str
source_channel_type: str        # "standard" | "coexistence"
original_operator_id: int | null  # primeiro operador (para lead retornante)
converted_by_user_id: int | null
rating: int | null              # 1-10
rating_requested_at: str | null
rating_received_at: str | null
unread_count: int
is_archived: int
attendance_protocol: str        # ATD-YYYYMMDDHHMMSS-XXXXX (gerado ao assumir)
attendance_started_at: str
is_corrected: bool              # true quando msg foi corrigida
corrected_by_message_id: int    # id da msg de correcao
assume_pending_response: bool   # true se operador assumiu e ainda nao respondeu
first_seen_at, last_message_at, last_inbound_at: datetime
```

### `wa_messages`
Mensagem WhatsApp (inbound, outbound ou sistema).
```
id: int
wa_message_id: str              # ID da Meta ou local_XXX
contact_id: int
contact_doc_id: str
direction: "inbound" | "outbound" | "system"
msg_type: str                   # text|image|audio|video|gif|sticker|document|location|template|system
content: str
media_path: str
media_mime: str
media_id: str                   # ID de midia na Meta
filename: str
status: str                     # received|sent|delivered|read|failed
operator_id: int | null
assigned_to: int | null
assigned_to_uid: str
department_id: int | null
channel_id: int | null
phone_number_id: str
is_rating_message: bool         # true = msg de avaliacao
visibility: "all" | "admin_only"  # admin_only = invisivel para operadores
latitude, longitude: float | null
timestamp_wa: datetime
created_at: datetime
reply_to_message_id: int | null
reply_to_preview: str
reply_to_sender_name: str
transcription: str              # transcricao de audio (STT)
is_corrected: bool              # true se esta msg outbound foi corrigida
corrected_by_message_id: int    # id da msg que substituiu esta
```

### `wa_transfer_log`
Historico de transferencias entre operadores/departamentos.
```
id: int
contact_id: int
from_user_id: int | null
to_user_id: int | null
from_department_id: int | null
to_department_id: int | null
transferred_by: int
reason: str
summary: str
created_at: datetime
```

### `users`
Usuarios do sistema (operadores, supervisores, admin).
```
id: int
username: str
display_name: str
email: str
firebase_uid: str
auth_provider: "firebase"
role: "admin" | "supervisor" | "operador"
department_id: int | null
avatar_path: str
is_active: int                  # 1=ativo, 0=desativado
created_at, last_login: datetime
```

### `departments`
Setores da empresa.
```
id: int
name: str
description: str
bot_key: "comercial" | "financeiro" | "administrativo" | "sac" | null
is_active: int
sort_order: int
created_at, updated_at: datetime
```

### `operator_assume_counters`
Contador de "assumir sem responder" por operador. Doc ID = user_id.
```
user_id: int
counter: int                    # range -2 a 0
updated_at: datetime
```
Cada `assumir` sem resposta anterior decrementa o contador (minimo -2). Cada resposta apos assumir incrementa (maximo 0). Quando `counter <= -2`, o endpoint `POST /api/wa/assume/{id}` pode bloquear novas assumidas ate o operador responder os contatos pendentes (`assume_pending_response=true`).

### `bot_states`
Estado da conversa com o bot para cada contato. Doc ID = contact_id.
```
step: "greeting" | "ask_name" | "ask_equipment" | "ask_sector"
      | "ask_name_after_sector" | "ask_name_after_equip" | "done"
nome: str                       # nome coletado
equipamento: str                # equipamento mencionado (se detectado)
setor_sugerido: int             # 1-4 (Comercial/Financeiro/Administrativo/SAC)
updated_at: datetime
```
Quando o bot finaliza, o estado e apagado e o contato recebe `attendance_protocol` + `department_id` com base no `bot_key`.

### `operator_profiles`
Perfil do operador para snapshots Firestore (sincronizado com users).
```
uid: str                        # firebase_uid (doc ID)
user_id: int
email, display_name, role: str
department_id: int | null
is_active: int
updated_at: datetime
```

### `audit_metrics`
Metricas diarias pre-agregadas para o dashboard.
```
doc_id: "YYYY-MM-DD" ou "YYYY-MM-DD_userId"
date: str
user_id: int | null             # null = global
total_leads_received: int
total_leads_assumed: int
total_messages_inbound: int
total_messages_outbound: int
messages_by_half_hour: map      # {"07:00": 5, "07:30": 12}
first_activity_at, last_activity_at: datetime
```

### `audit_log`
Log de auditoria de acoes do sistema.
```
id: int
user_id: int
action: str                     # LOGIN_SUCCESS_FIREBASE, WA_SEND, WA_TRANSFER, etc.
detail: str
ip_address: str
created_at: datetime
```

### `system_settings`
Configuracoes globais (doc unico: "config").
```
chat_prefix_enabled: bool
chat_prefix_roles: list[str]
quick_message_max: int
quick_messages_global: list[{shortcut, message}]
```

### `user_settings`
Configuracoes por usuario (doc ID = user_id).
```
chat_prefix_enabled: bool
chat_prefix_name: str
quick_messages: list[{shortcut, message}]
```

### `_meta`
Metadados internos (doc "counters" com sequencias auto-incremento).

---

## 11. Frontend — Telas e Componentes

### Tela de Login
- Login com Google (Firebase Auth)
- Restricao por dominio de email e whitelist

### Layout Principal
```
+------------------------------------------+
|              TopBar                       |
|  Nome | Role | Tema | Config | Sair      |
+------+----------+----------+-------------+
| Nav  | Contatos | Chat     | Detalhes    |
| Bar  | (lista)  | (msgs)   | (operacoes) |
|      |          |          |             |
| Novos|  Busca   | Historico| Qualificacao|
| Meus |  Filtro  | Composer | Transferir  |
| N/Q  |          | Anexos   | Devolver bot|
| Equip|          | Audio    | Reatribuir  |
+------+----------+----------+-------------+
```

### Abas de navegacao (NavBar)
| Aba | Filtro | Quem ve |
|---|---|---|
| Novos | `assigned_to == null` | Todos |
| Meus Atendimentos | `assigned_to == eu` | Todos |
| Nao Qualificados | `qualification == nao_qualificado` | Todos |
| Equipe | `assigned_to != null && != eu` | Admin/Sup |

### Modais de Configuracoes
| Modal | Acesso | Funcionalidade |
|---|---|---|
| Chat | Todos | Prefixo de mensagem pessoal |
| Mensagens rapidas | Todos | Atalhos de texto |
| Administracao | Admin | Sistema + Departamentos + Canais |
| WhatsApp Coexistence | Admin/Sup | Embedded Signup |
| Dashboard | Admin/Sup | Metricas + Export |

---

## 12. Variaveis de Ambiente

### Obrigatorias para Cloud Run
```
FIRESTORE_PROJECT_ID=project-26fb9c99-8ee9-4179-aef
FIRESTORE_COLLECTION_PREFIX=castro_crm
WHATSAPP_PHONE_NUMBER_ID=983401388192837
WHATSAPP_WABA_ID=2752449755094588
WHATSAPP_VERIFY_TOKEN=castro-webhook-2026
FIREBASE_WEB_API_KEY=...
FIREBASE_WEB_AUTH_DOMAIN=...
FIREBASE_WEB_APP_ID=...
BOOTSTRAP_ADMIN_EMAIL=...
ALLOWED_FIREBASE_EMAIL_DOMAIN=...
MEDIA_STORAGE_BACKEND=gcs
GCS_MEDIA_BUCKET=...
```

### Secrets (via Secret Manager)
```
WHATSAPP_TOKEN — token de acesso da Meta
WHATSAPP_APP_SECRET — secret do app Meta (para validacao HMAC)
SECRET_KEY — chave de sessao do backend
```

### Meta Embedded Signup
```
META_APP_ID=1434723791183375
META_APP_SECRET=...
EMBEDDED_SIGNUP_CONFIG_ID=2785379481799560
```

### Opcionais
```
FEATURE_AUDIO_TRANSCRIPTION=false
FEATURE_MESSAGE_STATUS=true
FEATURE_GOOGLE_CHAT=false
CHAT_DELIVERY_MODE=snapshot
LOG_LEVEL=INFO
CORS_ORIGINS=...
```

---

## 13. Deploy

### Pre-requisitos
- gcloud CLI configurado
- Projeto GCP com Firestore, Cloud Run, Secret Manager
- Firebase projeto configurado com Auth (Google provider)

### Comandos
```bash
# Build do frontend
cd frontend && npm run build && cd ..

# Deploy para Cloud Run
gcloud run deploy castro-crm \
  --source . \
  --region=southamerica-east1 \
  --project=project-26fb9c99-8ee9-4179-aef
```

### Dockerfile
- Multi-stage build: Node.js para frontend + Python para backend
- Inclui FFmpeg para conversao de audio
- Expoe porta 8080
- Uvicorn com 1 worker

---

## 14. Seguranca

- **Autenticacao:** Firebase Auth com Google Sign-In (primario) + Email/Password opcional. Em ambos os casos o backend valida o mesmo ID token. Email/Password precisa ser habilitado manualmente no Firebase Console (Authentication → Sign-in method) e os emails devem respeitar `ALLOWED_FIREBASE_EMAIL_DOMAIN` ou `ALLOWED_FIREBASE_EMAILS`
- **Webhook:** Validacao HMAC-SHA256 com `WHATSAPP_APP_SECRET`
- **CORS:** Configuravel via `CORS_ORIGINS`
- **Tokens:** Nunca expostos na API de listagem de canais
- **Roles:** Verificacao de permissao em cada endpoint
- **Audit log:** Todas as acoes criticas sao registradas
- **Mensagens de avaliacao:** `visibility: admin_only` impede visualizacao por operadores

---

## 15. Bot de Atendimento

O bot esta implementado em `bot_service.py` e opera como state machine. Fluxo coleta nome, equipamento e setor do cliente antes de transferir para o departamento correto.

### Quando o bot responde
- Canal com `is_bot_enabled=true` (standard tem por padrao; coexistence nao)
- Contato sem operador assumido (`assigned_to == null`)
- Respeito a horario de expediente (timezone -03:00, 07h-17h)

### Estados da state machine
```
greeting -> ask_name -> ask_equipment -> ask_sector -> done
         \-> ask_name_after_sector  (cliente pulou para setor direto)
         \-> ask_name_after_equip   (cliente mencionou equipamento)
```
Estado persistido em Firestore: `bot_states/{contact_id}` (ver Section 10).

### Roteamento para departamento
Ao finalizar (`done`), o bot:
1. Atribui o contato ao departamento via `bot_key` (ver Section 6)
2. Se nenhum departamento tem o `bot_key` do setor escolhido: cai em fallback (substring match) ou deixa em "Novos"
3. Insere mensagem de sistema com o protocolo e dados coletados

### Quando o bot para de responder
- Operador assume o contato (`assigned_to` deixa de ser null)
- Admin/Supervisor usa `POST /api/wa/contact/{id}/return-to-bot` para devolver ao bot (reseta `assigned_to=null` e o state)

### Assume counter (anti-spam de assumir)
Operadores que assumem contatos mas nao respondem sao limitados pelo contador em `operator_assume_counters` (ver Section 10). Cada assumir consecutivo sem resposta decrementa ate -2. Cada resposta apos assumir incrementa de volta. Campo `assume_pending_response` em `wa_contacts` marca os que ainda esperam primeira resposta.

### Protocolo de atendimento
Ao assumir (manual ou via bot), o contato recebe `attendance_protocol` no formato `ATD-YYYYMMDDHHMMSS-XXXXX` (onde XXXXX e o contact_id zero-padded). Usado para rastreabilidade nos relatorios.

Documentacao tecnica historica em `docs/BOT_ARCHITECTURE.md` (descreve o projeto original; algumas decisoes evoluiram).
