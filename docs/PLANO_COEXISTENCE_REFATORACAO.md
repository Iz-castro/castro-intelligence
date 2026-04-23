# Plano: Embed Signup Coexistence + Refatoração para Sub-Threads por Canal

> Copia do plano original aprovado em `C:\Users\rafal\.claude\plans\sleepy-seeking-lark.md`
> mantido aqui em `docs/` para referencia rapida no projeto.

## Context

Dois problemas interligados precisam ser resolvidos:

**1. Onboarding de coexistence está falhando para o número 3171957758.** A análise do código mostrou que o frontend está correto (passa `featureType: "whatsapp_business_app_onboarding"` + `sessionInfoVersion: "3"`), os webhooks de coexistence (`history`, `smb_message_echoes`, `smb_app_state_sync`) já têm handlers implementados, e a Castro Intelligence já tem o selo de Provedor de Tecnologia verificado. Porém, há **10 problemas no fluxo de troca de código → token → criação de canal** que vão de bloqueantes (sem checagem de status HTTP da Meta, body vazio na assinatura de webhook) a degradantes (token expira sem refresh, paginação de telefones ignorada).

**2. O modelo de dados não suporta o mesmo número em dois canais.** Hoje `wa_contacts` é chaveado só por `wa_id` (telefone), e `_resolve_channel_creds` lê `contact.channel_id` para decidir por onde enviar. Isso significa: (a) se um cliente já existe no Cloud API padrão e o operador conecta um coexistence onde já tinha conversa com ele, as duas threads colapsam em uma; (b) ao transferir um contato coexistence para outro operador, o destinatário continua enviando pelo número pessoal do dono original — sem que isso fique explícito; (c) auditoria fica ambígua porque `sender_user_id` e `channel_owner_user_id` não são distinguidos na mensagem.

**Resultado pretendido:** após este plano, (a) é possível onboardar números via coexistence sem falhas silenciosas; (b) o mesmo telefone pode aparecer como duas linhas separadas na lista de conversas (uma por canal, com badge); (c) envio sempre usa o canal correto da thread; (d) auditoria carrega `channel_owner_user_id` + `sender_user_id` distintos; (e) admin mantém visão unificada do cliente via perfil compartilhado (nome, notas, rating, qualificação).

**Decisões aprovadas pelo usuário:**
- Notas, qualificação, rating, arquivamento ficam **per-contato** (compartilhados entre canais).
- `assigned_to`, `department_id`, `unread_count`, `channel_id`, `phone_number_id`, `last_message_at` ficam **per-conversa**.
- Bulk reassign do admin **exclui** conversations em canal coexistence cujo `owner_user_id` é o operador X (porque é o WhatsApp pessoal dele).
- Ordem: Fase 1 (embed signup fixes) primeiro, para destravar testes com 3171957758. Depois Fases 2-4 (refatoração). Firestore pode ser apagado entre fases — sistema não está em produção.

---

## Fase 1 — Fixes do Embedded Signup Coexistence ✅ CONCLUÍDA

Commit `a8566b0` no branch `develop` (push feito). Deploy na revisão `castro-crm-00073-xxk`.

Objetivo: destravar o onboarding do 3171957758 e tornar o fluxo robusto.

### 1.1 `main.py` — Endpoint `/api/admin/embedded-signup/exchange`

Mudanças no mesmo arquivo, pontuais:

- `_meta_error_detail` extrai `message`/`code`/`subcode`/`fbtrace_id` da Meta.
- 4 chamadas Graph API (`oauth/access_token`, `debug_token`, `phone_numbers`, `subscribed_apps`) checam `status_code >= 400` antes de `.json()`.
- `/phone_numbers` paginado (`limit=100` + `paging.next`).
- `debug_token` parser robusto: deduplica WABAs, valida escopo `whatsapp_business_app_onboarding`.
- `subscribed_apps` envia `subscribed_fields` no body (lista específica para coexistence).
- `is_coexistence = body.channel_type == "coexistence"` (descarta check de `platform_type`).
- `expires_in` parseado e armazenado como `token_expires_at` no canal.

### 1.2 `channel_service.py` — `create_channel` e refresh

- `create_channel` aceita: `token_expires_at`, `platform_type`, `is_official_business_account`, `code_verification_status`, `messaging_limit_tier`, `verified_name`, `quality_rating`, `webhook_subscribed`.
- `update_channel` ganha esses campos na allowlist.
- Nova função `refresh_coexistence_token(channel_id)` usa `fb_exchange_token` para renovar token de canal coexistence. Chamada proativa em `_resolve_channel_creds` quando `now() >= token_expires_at - 5min`.

### 1.3 `webhook.py` — `_resolve_webhook_channel`

- Log `warning` explícito no fallback default (antes era silencioso e eventos coexistence caíam no canal do bot sem rastro).

### 1.4 `config.py` + endpoint `/api/admin/embedded-signup/config`

- Validar `META_APP_ID`, `META_APP_SECRET`, `EMBEDDED_SIGNUP_CONFIG_ID`. Retorna 503 com lista de variáveis faltando.

### 1.5 `frontend/src/App.tsx` — SDK FB

- Script SDK FB com `?v=<graph_api_version>` para alinhar com `FB.init`.

### 1.6 Pré-requisitos manuais (documentados em `docs/COEXISTENCE_GUIDE.md`)

- Número em WhatsApp Business App (não comum).
- Número não cadastrado em outra WABA.
- App Dashboard: webhooks ligados (`history`, `smb_message_echoes`, `smb_app_state_sync`).
- `EMBEDDED_SIGNUP_CONFIG_ID` configurado como "Onboarding do WhatsApp Business App".

---

## Fase 2 — Refatoração de Schema (Backend) ⏸️ AGUARDANDO

Objetivo: introduzir `wa_conversations` como camada entre `wa_contacts` (cliente) e `wa_messages` (mensagens).

### 2.1 Modelo Firestore

Três coleções:

```
wa_contacts/{contact_id}
  wa_id (telefone)
  display_name, declared_name, contact_avatar_path
  qualification, notes, rating, rating_received_at
  is_archived, attendance_protocol, attendance_started_at
  original_operator_id
  first_seen_at, updated_at

wa_conversations/{conversation_id}
  conversation_id = "{channel_id}__{wa_id}"   (determinístico)
  contact_id (FK), wa_id, channel_id
  assigned_to, assigned_to_uid, department_id
  unread_count
  last_message_at, last_inbound_at, last_outbound_at
  source_channel_type   (standard | coexistence)
  status                (open | archived)
  created_at

wa_messages/{message_id}
  conversation_id (FK)              ← novo, substitui contact_id no agrupamento
  contact_id (FK)                   ← mantido para queries cross-channel do admin
  channel_id, channel_owner_user_id ← novo: dono físico do canal
  sender_user_id                    ← novo: quem digitou (pode ser != owner em coexistence)
  wa_message_id, direction, type, content, status
  created_at, is_read
```

### 2.2 `database_firestore.py` — Refatoração das funções

Quebrar e renomear:

- **`upsert_wa_contact`** → divide em duas:
  - `upsert_wa_contact(wa_id, display_name)` — só campos do cliente.
  - `upsert_wa_conversation(contact_id, channel_id, source_channel_type, auto_assign_user_id=None)` — cria/atualiza conversation. `conversation_id` determinístico.
- **`save_wa_message`** — assinatura passa a exigir `conversation_id`. Atualiza `conversation.unread_count`, `conversation.last_message_at`, `conversation.last_inbound_at`/`last_outbound_at`. Salva `channel_owner_user_id` e `sender_user_id` na mensagem.
- **`get_wa_conversation`** → renomear para `get_messages_by_conversation(conversation_id)`. Query `WHERE conversation_id == X`.
- **`assign_wa_contact`** → renomear para `assign_wa_conversation(conversation_id, ...)`. Atualiza só a conversation; log de transferência referencia conversation_id e contact_id.
- **`return_contact_to_bot`** → `return_conversation_to_bot(conversation_id)`.
- **`get_all_wa_contacts`** → renomear para `get_all_wa_conversations()`. Retorna lista de conversations enriquecidas com dados do contato (join in-memory). Mantém função `get_wa_contact(contact_id)` para o painel de perfil.
- **`mark_wa_conversation_read`** — passa a receber `conversation_id`. Zera `conversation.unread_count`, marca mensagens da conversation como lidas.
- **`get_wa_unread_count`** — query em `wa_conversations`.
- **`archive_wa_contact`** — permanece per-contato. Adicionar `archive_wa_conversation(conversation_id)` separado para arquivar uma thread sem arquivar o cliente.

### 2.3 `main.py` — Endpoints

Renomear path params e payloads `contact_id` → `conversation_id` em:

- `GET /api/wa/contacts` → `GET /api/wa/conversations`
- `GET /api/wa/messages/{contact_id}` → `GET /api/wa/messages/{conversation_id}`
- `POST /api/wa/send`, `/send-media`, `/send-audio`, `/send-location`, `/send-template` — payload usa `conversation_id`. `_resolve_channel_creds` passa a buscar canal via `conversation.channel_id` (não mais `contact.channel_id`). Adicionar `sender_user_id = current_user["id"]` e `channel_owner_user_id = channel.owner_user_id` na chamada de `save_wa_message`.
- `POST /api/wa/correct-message` — usa `conversation_id` da mensagem original.
- `POST /api/wa/contact/manual` — cria contato + cria conversation no canal escolhido pelo operador (frontend manda `channel_id`).
- `POST /api/wa/contact/{contact_id}/read` → `POST /api/wa/conversation/{conversation_id}/read`.
- `POST /api/wa/transfer` — payload: `{ conversation_id, to_user_id, to_department_id }`. Atualiza só a conversation. Mensagem de sistema vai com `conversation_id`.
- `POST /api/admin/bulk-reassign` — query lista conversations do operador, **filtra fora** as conversations cujo `channel.owner_user_id == X AND channel.type == coexistence`, reassigna o restante.
- `PUT /api/wa/contact/{contact_id}/qualify`, `DELETE /api/wa/contact/{contact_id}`, `PUT /api/wa/contact/{contact_id}/declared-name` — **mantêm `contact_id`** porque atuam em campos compartilhados.

### 2.4 `webhook.py` — Fluxo de inbound

- Resolver `channel` pelo `phone_number_id` (já existe).
- `upsert_wa_contact(wa_id, display_name)` — só dados do cliente.
- `upsert_wa_conversation(contact_id, channel_id, ...)` — retorna `conversation_id`.
- `save_wa_message(conversation_id, contact_id, channel_id, channel_owner_user_id=channel.owner_user_id, sender_user_id=None, ...)`.
- Bot: só dispara se `conversation.assigned_to is None` E `channel.is_bot_enabled` (coexistence é sempre `False`).

### 2.5 `bot_service.py`

- `process_bot_message` recebe `conversation_id` em vez de `contact_id`. Estado do bot (coleção `bot_states`) passa a usar `conversation_id` como chave.
- `_finalize_bot` atribui `assigned_to`/`department_id` na **conversation**, não no contato.

### 2.6 `firestore.indexes.json`

Adicionar:
- `wa_conversations`: `(channel_id, wa_id)` para lookup determinístico
- `wa_conversations`: `(assigned_to_uid, status, last_message_at DESC)` para "minhas conversas"
- `wa_conversations`: `(department_id, status, last_message_at DESC)` para fila de departamento
- `wa_messages`: `(conversation_id, created_at DESC)` substitui o atual `(contact_id, created_at DESC)`
- Manter `(contact_id, created_at DESC)` em `wa_messages` para visão unificada do admin (timeline cross-channel do mesmo cliente)

Remover índices órfãos de `wa_contacts` que dependiam de `assigned_to_uid` e `department_id` (esses campos saem do contato).

### 2.7 `firestore.rules`

Adicionar regras para `wa_conversations` espelhando as de `wa_contacts` (operador vê só suas conversations + departamento; admin/supervisor veem tudo).

---

## Fase 3 — Frontend

### 3.1 `frontend/src/types.ts`

- Nova interface `Conversation` com: `id`, `contact_id`, `wa_id`, `channel_id`, `channel_label`, `channel_type`, `assigned_to`, `assigned_name`, `assigned_to_uid`, `department_id`, `department_name`, `unread_count`, `last_message_at`, `source_channel_type`.
- Mover de `Contact` para `Conversation`: `assigned_*`, `department_*`, `unread_count`, `channel_id`, `last_message_at`.
- `Contact` mantém: `display_name`, `declared_name`, `notes`, `qualification`, `rating`, `phone_formatted`, `contact_avatar_path`, `is_archived`, `attendance_protocol`, etc.

### 3.2 `frontend/src/context/CrmContext.tsx`

- Renomear `selectedContactId` → `selectedConversationId` em todo o contexto.
- Estado `contacts` → `conversations`. Buscar de `/api/wa/conversations`.
- Estado adicional `contactsById: Map<contact_id, Contact>` para join in-memory ao renderizar (nome/avatar do cliente).
- Snapshot Firestore — listar `wa_conversations` filtrando por `assigned_to_uid` (operador) ou sem filtro (admin).
- Snapshot de mensagens — `where("conversation_id", "==", activeConversationId)`.
- Endpoints atualizados: `send`, `mark-read`, `transfer`, `messages fetch` — todos passam `conversation_id`.
- Filtros das views (novos / meus / não-qualificados / equipe) operam sobre conversations agora.

### 3.3 `frontend/src/App.tsx`

- Lista de conversas: cada item é uma conversation. Exibir telefone + **badge do canal** (label + tipo). Mesmo telefone em múltiplos canais = múltiplas linhas.
- Banner do chat: nome do cliente + badge do canal ativo + nome do operador atribuído.
- Painel de perfil: nome/notas/qualificação/rating vêm do contato (compartilhados); quando expandido, mostra também lista das outras conversations daquele contato (link clicável para alternar entre threads do mesmo cliente).
- Modal de transferir: atua sobre a conversation atual.
- Botão "assumir": assume só essa conversation.

### 3.4 `frontend/src/utils/normalization.ts`

- Adicionar `normalizeConversation(raw): Conversation`.
- Manter `normalizeContact` enxuto (sem campos que migraram).

---

## Fase 4 — Wipe + Validação End-to-End

Como o sistema não está em produção e o usuário aprovou apagar Firestore:

1. Deploy das mudanças em ambiente de teste.
2. Apagar coleções `wa_contacts`, `wa_messages`, `wa_conversations`, `wa_transfer_log`, `bot_states`, `wa_message_status` via console do Firestore ou script `scripts/wipe_wa_collections.py` (criar).
3. Reonboardar o canal standard (Cloud API) com o test phone +1 555-175-4802 (WABA 2752449755094588).
4. Reonboardar o canal coexistence com 3171957758 via embed signup (validando que os fixes da Fase 1 funcionam).
5. Disparar mensagens dos dois canais para o mesmo telefone de teste e validar:
   - Aparecem como duas linhas separadas na lista, cada uma com seu badge.
   - Enviar pelo standard sai pelo bot; enviar pelo coexistence sai pelo número pessoal.
   - Transferir uma conversation não afeta a outra.
   - Painel de perfil do cliente mostra ambas e linka para alternar.
6. Validar auditoria: abrir uma mensagem outbound de uma conversation coexistence transferida e confirmar que `sender_user_id != channel_owner_user_id` está corretamente registrado.

---

## Verificação

**Embed signup (Fase 1):**
- Onboardar 3171957758 sem erro no popup.
- Conferir nos logs do servidor que a chamada `subscribed_apps` retorna `success: true` com os campos certos.
- Verificar que o canal criado tem `token_expires_at` populado no Firestore.
- Verificar que `is_coexistence == True` na criação (não fallback para standard).
- Disparar mensagem do celular 3171957758 para outro número (echo) e confirmar que webhook `smb_message_echoes` é processado.

**Refatoração (Fases 2-3):**
- Mesma `wa_id` em standard e coexistence aparece como 2 entradas em `/api/wa/conversations`.
- `_resolve_channel_creds` usa `conversation.channel_id` (verificar via debugger ou log).
- Bulk reassign do operador X que tem coexistence próprio: confirmar via test que a conversation no canal de X **não** é movida.
- UI mostra badge correto em cada linha.
- Painel de perfil unificado funciona.

**Critério de pronto:** cenário descrito pelo usuário (operador no Cloud API conversando com 3183440484 + mesmo operador entra no coexistence que já tinha conversa com 3183440484) resulta em **duas threads visíveis e independentes**, com envios indo pelo canal correto de cada uma.
