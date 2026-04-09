# Google Chat Integration - Documentacao Tecnica

**Projeto:** Hubloc CRM - Castro Intelligence
**Data:** 26 de Marco de 2026
**Status:** Implementado (feature flag: `FEATURE_GOOGLE_CHAT`)

---

## 1. Visao Geral

O CRM possui um painel lateral de comunicacao interna que faz bridge entre o React (operadores no escritorio) e o Google Chat (supervisores em campo) via Google Chat API.

**Nao e um iframe do Google Chat** — e um chat proprio construido no React que usa a Google Chat API como transporte. O Google bloqueia incorporacao via iframe (X-Frame-Options / CSP).

---

## 2. Arquitetura

```
Operador (CRM React)                    Supervisor (Google Chat celular/desktop)
       |                                              |
       | POST /api/gc/send                            |
       v                                              |
   FastAPI (Cloud Run)                                |
       |                                              |
       |-- salva no Firestore (gc_messages)           |
       |-- envia via Google Chat API ------>  Space do Google Chat
       |                                              |
       |                                    Supervisor responde
       |                                              |
       |<-- webhook /webhooks/google-chat ---  Google Chat webhook
       |
       |-- valida JWT do Google
       |-- salva no Firestore (gc_messages)
       |
       v
   React (onSnapshot) -- atualiza painel em tempo real
```

---

## 3. Como o Supervisor Ve as Mensagens

Mensagens enviadas pelo CRM chegam no Google Chat **como mensagens do bot "Hubloc CRM"**, nao do operador diretamente. Isso e uma limitacao da Google Chat API — nao permite enviar "como se fosse" outro usuario.

Exemplo do que o supervisor ve no Google Chat:

```
Hubloc CRM (bot): Beto, tem betoneira 400L disponivel?
Beto Souza: Tem 3 unidades, todas revisadas
Hubloc CRM (bot): O cliente quer desconto de 10%, posso dar?
Beto Souza: 10% pode sim
```

Para identificar qual operador enviou, o sistema pode prefixar o nome na mensagem:
```
Hubloc CRM (bot): [Ana Silva] Beto, tem betoneira 400L disponivel?
```

---

## 4. O que Aparece no Painel do CRM

O painel mostra **spaces do Google Chat** em que o bot foi adicionado — nao todos os usuarios do workspace.

### Fluxo de ativacao de um space:

1. Admin ou supervisor cria um **Space** no Google Chat (ex: "Patio de Maquinas")
2. Adiciona membros (supervisores) + bot **Hubloc CRM**
3. Bot recebe evento `ADDED_TO_SPACE` e registra a conversa no Firestore
4. Space aparece automaticamente no painel do CRM para todos os operadores

### Visibilidade:

- Hoje: todos os operadores veem todos os spaces
- Futuro: filtro por departamento (operadores de logistica so veem spaces de logistica)

---

## 5. Arquivos do Projeto

### Backend (Python/FastAPI)

| Arquivo | Descricao |
|---------|-----------|
| `config.py` | Feature flag `FEATURE_GOOGLE_CHAT`, `GOOGLE_CHAT_PROJECT_NUMBER`, `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE` |
| `google_chat.py` | Servico de integracao: auth via service account, envio de mensagens, download de anexos, listagem de spaces |
| `webhook_google_chat.py` | Validacao JWT (iss + audience + chave publica Google), processamento de eventos MESSAGE/ADDED_TO_SPACE |
| `database_firestore.py` | Colecoes `gc_conversations` e `gc_messages` com operacoes CRUD |
| `main.py` | 6 rotas: `/api/gc/*` e `/webhooks/google-chat` |

### Frontend (React/TypeScript)

| Arquivo | Descricao |
|---------|-----------|
| `frontend/src/components/gchat/InternalChatPanel.tsx` | Painel slide-in com lista de conversas, chat real-time (onSnapshot), composer |
| `frontend/src/types.ts` | Tipos `GcConversation`, `GcMessage` |
| `frontend/src/styles.css` | Estilos do painel, mensagens, badges, toast |
| `frontend/src/App.tsx` | Icone na TopBar + integracao do painel (controlado por feature flag) |

### Configuracao

| Arquivo | Descricao |
|---------|-----------|
| `firestore.rules` | Regras de leitura para `gc_conversations` e `gc_messages` |
| `.env.example` | Variaveis de ambiente documentadas |
| `requirements.txt` | `google-api-python-client`, `google-auth`, `cryptography` |
| `seed_gchat.py` | Script para popular dados de teste no Firestore |

---

## 6. Rotas da API

| Metodo | Rota | Descricao | Auth |
|--------|------|-----------|------|
| `GET` | `/api/gc/conversations` | Lista conversas do Google Chat | Firebase |
| `GET` | `/api/gc/messages/{id}` | Mensagens de uma conversa | Firebase |
| `POST` | `/api/gc/send` | Envia mensagem do CRM para Google Chat | Firebase |
| `POST` | `/api/gc/mark-read/{id}` | Marca conversa como lida | Firebase |
| `GET` | `/api/gc/spaces` | Lista spaces disponiveis na API | Firebase |
| `POST` | `/webhooks/google-chat` | Recebe eventos do Google Chat | JWT Google |

---

## 7. Modelagem Firestore

### Colecao: `castro_crm_gc_conversations`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `id` | number | ID auto-incremento |
| `space_id` | string | ID do Google Chat Space (ex: `spaces/AAAA`) |
| `space_name` | string | Nome do space |
| `participants` | array | Emails dos participantes |
| `last_message` | string | Preview da ultima mensagem |
| `last_message_at` | timestamp | Data da ultima atividade |
| `unread_count` | map | Nao-lidas por operador `{ "email": count }` |
| `created_at` | timestamp | Data de criacao |

### Colecao: `castro_crm_gc_messages`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `id` | number | ID auto-incremento |
| `conversation_id` | number | FK para gc_conversations |
| `gchat_message_id` | string | ID da mensagem no Google Chat |
| `sender_email` | string | Email do remetente |
| `sender_name` | string | Nome do remetente |
| `msg_type` | string | text, audio, image, video, document |
| `content` | string | Conteudo da mensagem |
| `media_path` | string | Caminho do anexo no storage |
| `media_mime` | string | MIME type do anexo |
| `source` | string | `crm` ou `google_chat` |
| `create_time` | timestamp | Timestamp do Google Chat |
| `created_at` | timestamp | Timestamp local |

---

## 8. Variaveis de Ambiente

```env
FEATURE_GOOGLE_CHAT=false              # Habilita/desabilita o modulo
GOOGLE_CHAT_PROJECT_NUMBER=            # Project number do GCP (validacao JWT)
GOOGLE_CHAT_SERVICE_ACCOUNT_FILE=      # Caminho para JSON da service account (vazio = ADC)
```

Para adicionar no Cloud Run sem afetar as outras:
```bash
gcloud run services update castro-crm \
  --update-env-vars "FEATURE_GOOGLE_CHAT=true" \
  --region southamerica-east1
```

---

## 9. Seguranca

### Webhook do Google Chat
- Validacao de JWT com chave publica do Google
- Verifica `iss` == `chat@system.gserviceaccount.com`
- Verifica `audience` == project number do GCP
- Rejeita tokens expirados ou invalidos

### Firestore Rules
- Colecoes `gc_conversations` e `gc_messages` com leitura restrita a emails autorizados
- Escrita bloqueada (somente backend via service account)

### Rotas da API
- Todas protegidas por Firebase Auth (exceto webhook)
- Feature flag `FEATURE_GOOGLE_CHAT` retorna 404 quando desabilitado

---

## 10. Fluxo de Audio (Supervisor -> CRM)

1. Supervisor grava audio no Google Chat (celular)
2. Google Chat envia evento com `attachment.resourceName` no webhook
3. FastAPI usa `resourceName` para chamar `media.download` da Chat API
4. Converte formato se necessario (iPhone: `.m4a`, Android: `.ogg`/`.3gp`)
5. Armazena no Cloud Storage
6. Salva referencia no Firestore
7. Frontend reproduz via `<audio>` com URL assinada

---

## 11. Ativacao em Producao

### Pre-requisitos:
1. Admin do Google Workspace `@centralloc.com.br` aprova o Chat App (ver `docs/widgetgchat.md` Secao 8)
2. Chat API ativada no projeto GCP
3. Service account com escopos: `chat.messages`, `chat.spaces.readonly`, `chat.memberships.readonly`

### Deploy:
1. `gcloud run services update castro-crm --update-env-vars "FEATURE_GOOGLE_CHAT=true,GOOGLE_CHAT_PROJECT_NUMBER=SEU_NUMBER"`
2. Configurar webhook URL do Chat App: `https://castro-crm-XXXX.run.app/webhooks/google-chat`
3. Admin adiciona o bot nos spaces desejados

### Teste:
1. Enviar mensagem do CRM -> verificar que chega no Google Chat
2. Responder no Google Chat -> verificar que aparece no painel do CRM
3. Enviar audio pelo celular -> verificar reproducao no CRM

---

## 12. Melhorias Futuras

- **Prefixo do operador**: Mensagens do CRM com `[Nome] conteudo` para supervisor saber quem enviou
- **Filtro por departamento**: Operadores veem so spaces do seu setor
- **DMs 1:1**: Suporte a mensagens diretas com o bot (alem de spaces em grupo)
- **Criar space pelo CRM**: Botao "Nova conversa" que cria space via API
- **Notificacao sonora**: Beep quando mensagem chega com painel fechado
- **Transcricao de audio**: Reutilizar Faster Whisper para audios do Google Chat
