# Plano: Embed Signup Coexistence + Multi-Tenant + Sub-Threads por Canal

> Plano arquitetural unificado. Fase 1 (embed signup fixes) já foi entregue
> em produção. As demais fases ficam pausadas até aprovação do App Review
> da Meta. Quando o sinal verde chegar, tudo é executado num único refator
> e o Firestore é resetado (sistema ainda não está em produção real
> multi-cliente, então pode ser zerado).

## Context

Três objetivos casados nesta refatoração:

**1. Onboarding de coexistence funcional** — código já blindado em produção
(commit `a8566b0`, revisão `castro-crm-00073-xxk` ou superior). Aguardando
Advanced Access da Meta nas permissões `whatsapp_business_messaging`,
`whatsapp_business_management` e `business_management` pra finalizar testes
end-to-end com `featureType: whatsapp_business_app_onboarding`.

**2. Mesmo número em dois canais sem colidir** — hoje `wa_contacts` é
chaveado só por telefone e `_resolve_channel_creds` lê `contact.channel_id`
pra decidir o canal de envio. Resultado: cliente que aparece no Cloud API
padrão E no coexistence colapsa numa única thread; transferência de contato
coexistence acaba enviando pelo número pessoal do dono original sem
audit trail; `sender_user_id` e `channel_owner_user_id` ficam indistintos
em mensagens.

**3. Multi-tenant nativo (Castro Intelligence como Tech Provider)** —
reaproveitar o mesmo App Meta verificado e a mesma infraestrutura para
atender múltiplos clientes (Hubloc + futuras clínicas, locadoras etc).
Cada cliente faz Embedded Signup conectando sua própria WABA; webhook
único do CRM roteia para o tenant correto. Sem precisar passar por App
Review novamente para cada cliente.

**Resultado pretendido:**
- Embed Signup coexistence funciona end-to-end (depois da aprovação Meta).
- Mesmo telefone aparece como múltiplas linhas na lista, uma por canal,
  com badge identificando o canal.
- Envio sempre usa o canal correto da thread.
- Auditoria registra `channel_owner_user_id` + `sender_user_id` distintos.
- Admin mantém visão unificada do cliente via perfil compartilhado.
- Cada tenant é um "mundo isolado" no Firestore — impossível vazar dados
  entre clientes mesmo se o backend tiver bug em filtro.

## Decisões aprovadas pelo usuário

- **Notas, qualificação, rating, arquivamento** ficam **per-contato**
  (compartilhados entre canais — é o cliente, não a thread).
- **`assigned_to`, `department_id`, `unread_count`, `channel_id`,
  `phone_number_id`, `last_message_at`** ficam **per-conversa** (per-thread).
- **Bulk reassign do admin** exclui conversations em canal coexistence cujo
  `owner_user_id` é o operador X (é o WhatsApp pessoal dele).
- **Multi-tenant por subcoleções** (não flat com `tenant_id`). Trade-off
  aceito: queries cross-tenant exigem `collectionGroup` — caso raro,
  resolvido via pré-agregação em `_meta/system_metrics` quando precisar.
- **Firestore pode ser zerado** entre Fase 1 e Fase 2 — sistema ainda não
  está em produção multi-cliente.
- **Onboarding self-service de novo tenant fica pra depois** — Fase 2
  entrega o esqueleto multi-tenant, mas com 1 tenant fixo (`hubloc`).
  Quando cliente #2 fechar, faz a UI super-admin de criar tenants.

---

## Fase 1 — Embed Signup Fixes ✅ Concluída

Commit `a8566b0` no branch `develop` (push feito). Deploy ativo.

### 1.1 `main.py` — `/api/admin/embedded-signup/exchange`

- `_meta_error_detail` extrai `message`/`code`/`subcode`/`fbtrace_id` da Meta.
- 4 chamadas Graph API (`oauth/access_token`, `debug_token`,
  `phone_numbers`, `subscribed_apps`) checam `status_code >= 400` antes de
  parsear JSON.
- `/phone_numbers` paginado (`limit=100` + `paging.next`).
- `debug_token` parser robusto (deduplica WABAs, valida escopo
  `whatsapp_business_app_onboarding`).
- `subscribed_apps` envia `subscribed_fields` no body com lista específica
  de coexistence.
- `is_coexistence = body.channel_type == "coexistence"` (descarta verificação
  de `platform_type` que era inconsistente).
- `expires_in` parseado e armazenado como `token_expires_at` no canal.

### 1.2 `channel_service.py`

- `create_channel` aceita campos coexistence: `token_expires_at`,
  `platform_type`, `is_official_business_account`,
  `code_verification_status`, `messaging_limit_tier`, `verified_name`,
  `quality_rating`, `webhook_subscribed`.
- `update_channel` permite atualizar todos esses campos.
- `refresh_coexistence_token(channel_id)` faz `fb_exchange_token` para
  renovar token coexistence; chamado proativamente em
  `_resolve_channel_creds` quando token vai expirar em <5min.

### 1.3 `webhook.py` — `_resolve_webhook_channel`

- Loga `warning` explícito no fallback default (antes era silencioso e
  eventos coexistence caíam no canal do bot sem rastro).

### 1.4 `config.py` + `/api/admin/embedded-signup/config`

- Validação de `META_APP_ID`, `META_APP_SECRET`, `EMBEDDED_SIGNUP_CONFIG_ID`
  com mensagem clara das variáveis faltando.

### 1.5 `frontend/src/App.tsx`

- Script SDK FB carrega com `?v=<graph_api_version>` para alinhar com
  `FB.init`.

### 1.6 Documentação

- `docs/COEXISTENCE_GUIDE.md` ampliado com pré-requisitos manuais e tabela
  de troubleshooting.

---

## Fase 2 — Multi-Tenant + Sub-Threads (Backend)

> **Pré-requisito**: App Review aprovado pela Meta.
> **Pré-condição**: Firestore pode ser zerado completamente antes de
> executar (sistema ainda single-tenant Hubloc, sem dados de produção
> multi-cliente).

### 2.1 Modelo Firestore — subcoleções aninhadas em `tenants/`

```
tenants/{tenant_id}                              ← per-tenant
  └── (data: name, cnpj, plan, billing, settings, created_at, ...)

tenants/{tenant_id}/users/{user_id}
  └── { email, display_name, role, department_id, firebase_uid, is_active }

tenants/{tenant_id}/operator_profiles/{firebase_uid}
tenants/{tenant_id}/departments/{department_id}
tenants/{tenant_id}/channels/{channel_id}
  └── { channel_type, label, waba_id, phone_number_id, access_token,
        owner_user_id, default_department_id, is_bot_enabled, is_active,
        webhook_subscribed, token_expires_at, platform_type,
        is_official_business_account, code_verification_status,
        messaging_limit_tier, verified_name, quality_rating,
        created_at, updated_at }

tenants/{tenant_id}/wa_contacts/{contact_id}
  └── { wa_id, display_name, declared_name, contact_avatar_path,
        qualification, notes, rating, rating_received_at,
        is_archived, attendance_protocol, attendance_started_at,
        original_operator_id, first_seen_at, updated_at }

tenants/{tenant_id}/wa_conversations/{conversation_id}      ← NOVA
  conversation_id = "{channel_id}__{wa_id}"   (determinístico)
  └── { contact_id (FK), wa_id, channel_id,
        assigned_to, assigned_to_uid, department_id,
        unread_count, last_message_at, last_inbound_at, last_outbound_at,
        source_channel_type (standard | coexistence),
        status (open | archived), created_at }

tenants/{tenant_id}/wa_messages/{message_id}
  └── { conversation_id (FK),
        contact_id (FK denormalizado, p/ timeline cross-channel),
        channel_id, channel_owner_user_id, sender_user_id,    ← NOVOS
        wa_message_id, direction, msg_type, content, status,
        media_path, media_mime, filename, latitude, longitude,
        reply_to_message_id, reply_to_preview, reply_to_sender_name,
        is_corrected, corrected_by_message_id,
        created_at, timestamp_wa, is_read, transcription,
        operator_id (legado, mantido como alias de sender_user_id),
        visibility }

tenants/{tenant_id}/wa_transfer_log/{log_id}
  └── { conversation_id (FK), contact_id (FK), from_user_id, to_user_id,
        from_department_id, to_department_id, reason, summary,
        transferred_by_user_id, created_at }

tenants/{tenant_id}/wa_message_status/{status_id}
tenants/{tenant_id}/bot_states/{conversation_id}             ← chave por conversation_id
tenants/{tenant_id}/system_settings/{key}
tenants/{tenant_id}/user_settings/{user_id}
tenants/{tenant_id}/audit_log/{entry_id}
tenants/{tenant_id}/audit_metrics/{key}
tenants/{tenant_id}/operator_assume_counters/{user_id}

tenants/{tenant_id}/media_assets/{asset_id}
  └── chunks/{chunk_id}                          ← subcoleção (já existia)

tenants/{tenant_id}/gc_conversations/{conversation_id}
tenants/{tenant_id}/gc_messages/{message_id}
tenants/{tenant_id}/internal_unread/{key}
```

**Coleções globais (fora de `tenants/`):**

```
_meta/
  ├── counters                                   ← auto-increment global
  └── system_metrics                             ← agregações cross-tenant
                                                   (super-admin Castro Intelligence)

phone_routing/{phone_number_id}                  ← índice O(1) p/ webhook
  └── { tenant_id, channel_id }
```

`phone_routing` é a peça crítica: o webhook da Meta entrega só
`phone_number_id`, e precisa virar (tenant_id, channel_id) sem ter que
varrer todos os tenants. Mantemos esse índice atualizado em transações
junto com `tenants/{id}/channels/{cid}`.

### 2.2 `firestore_common.py` — helpers

```python
def tenant_path(tenant_id: str, *parts: str) -> str:
    return "/".join(["tenants", tenant_id, *parts])

def tenant_collection(tenant_id: str, name: str):
    return prefixed_collection(tenant_path(tenant_id, name))

def tenant_document(tenant_id: str, name: str, doc_id):
    return prefixed_document(tenant_path(tenant_id, name), doc_id)
```

Mantém `prefixed_collection`/`prefixed_document` para coleções globais
(`_meta`, `phone_routing`, `tenants`).

### 2.3 `database_firestore.py` — refatoração das funções

Toda função relacionada a um tenant ganha `tenant_id` como primeiro
parâmetro. Quebrar e renomear:

- **`upsert_wa_contact`** → divide em duas:
  - `upsert_wa_contact(tenant_id, wa_id, display_name)` — só dados do
    cliente.
  - `upsert_wa_conversation(tenant_id, contact_id, channel_id,
    source_channel_type, auto_assign_user_id=None)` — cria/atualiza
    conversation. `conversation_id` determinístico.
- **`save_wa_message`** — assinatura passa a exigir `tenant_id` +
  `conversation_id` + `channel_owner_user_id` + `sender_user_id`.
  Atualiza `conversation.unread_count`, `conversation.last_message_at`,
  `conversation.last_inbound_at`/`last_outbound_at`.
- **`get_wa_conversation`** → renomeado para
  `get_messages_by_conversation(tenant_id, conversation_id)`. Query
  `WHERE conversation_id == X`.
- **`assign_wa_contact`** → renomeado para
  `assign_wa_conversation(tenant_id, conversation_id, ...)`. Atualiza só
  a conversation; log de transferência referencia `conversation_id` E
  `contact_id`.
- **`return_contact_to_bot`** → `return_conversation_to_bot(tenant_id,
  conversation_id)`.
- **`get_all_wa_contacts`** → `get_all_wa_conversations(tenant_id)`.
  Retorna conversations enriquecidas com dados do contato (join in-memory).
  Mantém `get_wa_contact(tenant_id, contact_id)` para painel de perfil.
- **`mark_wa_conversation_read`** — `(tenant_id, conversation_id)`.
- **`get_wa_unread_count`** — `(tenant_id, user_id)`. Query em
  `tenants/{id}/wa_conversations`.
- **`archive_wa_contact`** — permanece per-contato. Adicionar
  `archive_wa_conversation(tenant_id, conversation_id)` para arquivar
  uma thread sem arquivar o cliente.
- **`create_manual_wa_contact`** — recebe `tenant_id`. Lookup com
  variantes de wa_id (Fase 1.7 já implementou, só passar a chave por
  tenant).
- **`_find_contact_by_wa_id_any_variant`** — recebe `tenant_id` e busca
  na subcoleção do tenant.
- **Todas as funções de departments, users, audit, settings, etc.** —
  ganham `tenant_id`.

### 2.4 `main.py` — Endpoints

#### Resolução de tenant

`get_current_user` extrai `tenant_id` do custom claim do Firebase ID Token:

```python
async def get_current_user(...) -> dict:
    decoded = decoded_firebase_token  # auth check
    tenant_id = decoded.get("tenant_id")
    if not tenant_id:
        raise HTTPException(401, "Tenant não definido para o usuário")
    user = get_user_by_firebase_uid(tenant_id, decoded["uid"])
    user["tenant_id"] = tenant_id
    return user
```

Todo endpoint passa `current_user["tenant_id"]` pra camada de dados.

#### Renomeações e mudanças de payload

- `GET /api/wa/contacts` → `GET /api/wa/conversations`
- `GET /api/wa/messages/{contact_id}` → `GET /api/wa/messages/{conversation_id}`
- `POST /api/wa/send`, `/send-media`, `/send-audio`, `/send-location`,
  `/send-template` — payload usa `conversation_id`. `_resolve_channel_creds`
  passa a buscar canal via `conversation.channel_id` (não mais
  `contact.channel_id`). Adicionar `sender_user_id = current_user["id"]`
  e `channel_owner_user_id = channel.owner_user_id` ao chamar
  `save_wa_message`.
- `POST /api/wa/correct-message` — usa `conversation_id` da mensagem
  original.
- `POST /api/wa/contact/manual` — cria contato + cria conversation no
  canal escolhido pelo operador (frontend manda `channel_id`).
- `POST /api/wa/contact/{contact_id}/read` →
  `POST /api/wa/conversation/{conversation_id}/read`.
- `POST /api/wa/transfer` — payload: `{ conversation_id, to_user_id,
  to_department_id }`. Atualiza só a conversation. Mensagem de sistema
  referencia `conversation_id`.
- `POST /api/admin/bulk-reassign` — query lista conversations do operador,
  **filtra fora** as que estão em canal coexistence cujo
  `channel.owner_user_id == X`, reassigna o restante.
- `PUT /api/wa/contact/{contact_id}/qualify`,
  `DELETE /api/wa/contact/{contact_id}`,
  `PUT /api/wa/contact/{contact_id}/declared-name` — **mantêm
  `contact_id`** (atuam em campos compartilhados).
- `GET /api/wa/templates` — recebe `tenant_id` implícito; busca canal
  ativo do tenant pra resolver WABA.

#### Endpoint super-admin (futuro próximo, não urgente)

Reservar prefixo `/api/platform/...` para ações cross-tenant que apenas
o super-admin do Castro Intelligence pode fazer (criar tenant, ver
métricas globais, etc). Não implementado nesta fase — só prepara o
roteamento.

### 2.5 `webhook.py` — Fluxo de inbound multi-tenant

```
1. Receber payload Meta com phone_number_id
2. tenant_id, channel_id = phone_routing[phone_number_id]
3. (se não achou: log warning, descarta)
4. channel = tenant_collection(tenant_id, "channels").doc(channel_id).get()
5. upsert_wa_contact(tenant_id, wa_id, display_name)
6. upsert_wa_conversation(tenant_id, contact_id, channel_id,
                          source_channel_type, auto_assign_user_id=...)
   → retorna conversation_id determinístico
7. save_wa_message(tenant_id, conversation_id, contact_id, channel_id,
                   channel_owner_user_id=channel.owner_user_id,
                   sender_user_id=None, ...)
8. Bot dispara somente se conversation.assigned_to is None
   AND not conversation.bot_completed
   AND channel.is_bot_enabled
   (gate atual já corrige re-entry em produção, replicar aqui)
```

`phone_routing` é atualizado em `create_channel`:

```python
def create_channel(tenant_id, ..., phone_number_id, channel_id, ...):
    # Salva o canal na subcoleção do tenant
    tenant_document(tenant_id, "channels", channel_id).set({...})
    # Mantém índice global pro webhook
    prefixed_document("phone_routing", phone_number_id).set({
        "tenant_id": tenant_id,
        "channel_id": channel_id,
    })
```

E removido em `deactivate_channel`.

### 2.6 `bot_service.py`

- `process_bot_message(tenant_id, conversation_id, content, contact_name)`
  passa a receber tenant_id; estado do bot na coleção
  `tenants/{id}/bot_states/{conversation_id}`.
- `_finalize_bot` atribui `assigned_to`/`department_id` na
  **conversation**, não no contato. `bot_completed=True` continua sendo
  o gate de re-entry.

### 2.7 Firebase Auth — Custom Claims

Quando um usuário é provisionado, set custom claim:

```python
firebase_admin.auth.set_custom_user_claims(firebase_uid, {
    "tenant_id": "hubloc",
    "role": "admin",
})
```

O ID Token do usuário passa a carregar `tenant_id` automaticamente. Todo
endpoint backend lê isso. Frontend não precisa enviar.

Helper `provision_firebase_user` em `firebase_admin_client.py` é o ponto
único de provisioning — adicionar set de claims lá.

### 2.8 `firestore.indexes.json`

Índices necessários (por tenant — Firestore considera o path completo):

```
collection: tenants/{tenantId}/wa_conversations
  composite: (channel_id, wa_id)
  composite: (assigned_to_uid, status, last_message_at DESC)
  composite: (department_id, status, last_message_at DESC)

collection: tenants/{tenantId}/wa_messages
  composite: (conversation_id, created_at DESC)
  composite: (contact_id, created_at DESC)        ← timeline cross-channel admin

collection: tenants/{tenantId}/wa_transfer_log
  composite: (conversation_id, created_at DESC)

collection: tenants/{tenantId}/wa_contacts
  composite: (is_archived, last_message_at DESC)  ← lista geral
```

`collectionGroup` indexes (cross-tenant, super-admin):

```
collectionGroup: wa_messages
  composite: (created_at DESC)                    ← timeline global

collectionGroup: wa_conversations
  composite: (assigned_to, last_message_at DESC)
```

Remover índices antigos órfãos de `wa_contacts` que dependiam de
`assigned_to_uid` e `department_id` (esses campos saem do contato).

### 2.9 `firestore.rules`

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Tudo dentro do tenant — operador autenticado precisa ter
    // tenant_id no claim batendo com o path
    match /tenants/{tenantId}/{document=**} {
      allow read, write: if request.auth != null
        && request.auth.token.tenant_id == tenantId;
    }

    // phone_routing: leitura só backend (via Admin SDK).
    // Frontend não acessa.
    match /phone_routing/{phoneId} {
      allow read, write: if false;
    }

    // _meta: só backend.
    match /_meta/{doc} {
      allow read, write: if false;
    }

    // tenants/ collection root: operador só lê o doc do próprio tenant
    // (caso queira mostrar nome/branding).
    match /tenants/{tenantId} {
      allow read: if request.auth != null
        && request.auth.token.tenant_id == tenantId;
      allow write: if false;  // só super-admin via Admin SDK
    }
  }
}
```

Uma única regra cobre 99% das queries do operador. Backend usa Admin SDK
e ignora rules.

---

## Fase 3 — Frontend

### 3.1 `frontend/src/types.ts`

Nova interface `Conversation`:

```typescript
export type Conversation = {
  id: string;                    // "{channel_id}__{wa_id}"
  contact_id: number;
  wa_id: string;
  channel_id: number;
  channel_label?: string;        // join in-memory pra exibição
  channel_type?: "standard" | "coexistence";
  source_channel_type?: "standard" | "coexistence";
  assigned_to?: number | null;
  assigned_name?: string;
  assigned_role?: string;
  assigned_to_uid?: string;
  department_id?: number | null;
  department_name?: string;
  unread_count?: number;
  last_message_at?: string;
  last_inbound_at?: string;
  last_outbound_at?: string;
  status?: "open" | "archived";
};
```

Mover de `Contact` para `Conversation`: `assigned_*`, `department_*`,
`unread_count`, `channel_id`, `last_message_at`, `last_inbound_at`,
`source_channel_type`.

`Contact` mantém: `display_name`, `declared_name`, `notes`,
`qualification`, `rating`, `phone_formatted`, `contact_avatar_path`,
`is_archived`, `attendance_protocol`, etc.

Tenant_id **não aparece no frontend** — está implícito no token Firebase.

### 3.2 `frontend/src/context/CrmContext.tsx`

- Renomear `selectedContactId` → `selectedConversationId` em todo o
  contexto.
- Estado `contacts` → `conversations`. Buscar de `/api/wa/conversations`.
- Estado adicional `contactsById: Map<contact_id, Contact>` para join
  in-memory ao renderizar (nome/avatar do cliente vêm do contato; resto
  vem da conversation).
- Snapshot Firestore — listar
  `tenants/{tenantId}/wa_conversations` filtrando por `assigned_to_uid`
  (operador) ou sem filtro (admin do tenant). `tenantId` lido do
  `firebaseUser.getIdTokenResult().claims.tenant_id`.
- Snapshot de mensagens —
  `where("conversation_id", "==", activeConversationId)`.
- Endpoints atualizados: `send`, `mark-read`, `transfer`, `messages fetch`
  — todos passam `conversation_id`.
- Filtros das views (novos / meus / não-qualificados / equipe) operam
  sobre conversations.

### 3.3 `frontend/src/App.tsx`

- Lista de conversas: cada item é uma conversation. Exibir telefone +
  **badge do canal** (label + tipo). Mesmo telefone em múltiplos canais
  = múltiplas linhas.
- Banner do chat: nome do cliente + badge do canal ativo + nome do
  operador atribuído.
- Painel de perfil: nome/notas/qualificação/rating vêm do contato
  (compartilhados); quando expandido, mostra também lista das outras
  conversations daquele contato (link clicável para alternar entre
  threads).
- Modal de transferir: atua sobre a conversation atual.
- Botão "assumir": assume só essa conversation.

### 3.4 `frontend/src/utils/normalization.ts`

- `normalizeConversation(raw): Conversation`.
- `normalizeContact` enxuto (sem campos que migraram).

---

## Fase 4 — Wipe + Validação End-to-End

Como o sistema não está em produção multi-cliente:

1. Deploy das mudanças em `castro-crm-staging` (Cloud Run separado, prefixo
   `castro_crm_staging` no Firestore).
2. Validar lógica em staging via webhook simulado (curl) e UI.
3. Quando estável, deploy em produção `castro-crm`.
4. **Wipe completo do Firestore prod** via script
   `scripts/wipe_all_collections.py` (criar). Apaga:
   - Todas as coleções legadas (`castro_crm_wa_contacts`,
     `castro_crm_wa_messages`, `castro_crm_users`, etc).
   - Recria `tenants/hubloc` com config inicial.
5. **Bootstrap do tenant Hubloc**:
   - Cria `tenants/hubloc` com nome, CNPJ, plan.
   - Provisiona admin `BOOTSTRAP_ADMIN_EMAIL` com role admin no tenant.
   - Adiciona claim `tenant_id="hubloc"` no Firebase Auth.
   - Re-onboarding do canal standard via `/api/admin/embedded-signup/exchange`
     (Cloud API com WABA da CentralLoc), que cria `phone_routing` e
     `tenants/hubloc/channels/{id}`.
   - Re-onboarding do canal coexistence (3171957758) — agora possível
     porque Meta aprovou Advanced Access.
6. **Validação end-to-end**:
   - Mensagem inbound do cliente entra via webhook → `phone_routing` →
     tenant correto → conversation criada.
   - Mesmo `wa_id` em standard e coexistence aparece como 2 entradas
     em `/api/wa/conversations`.
   - `_resolve_channel_creds` usa `conversation.channel_id` (verificar via
     debugger ou log).
   - Bulk reassign do operador X que tem coexistence próprio: confirmar
     que conversations no canal de X **não** são movidas.
   - UI mostra badge correto em cada linha.
   - Painel de perfil unificado funciona.
7. **Validação de auditoria**: abrir uma mensagem outbound de uma
   conversation coexistence transferida e confirmar que
   `sender_user_id != channel_owner_user_id` está corretamente registrado.
8. **Validação de isolamento (multi-tenant)**: criar tenant fictício
   `tenants/teste` no Firestore Console com 1 doc dummy. Confirmar via
   curl autenticado como user do tenant `hubloc` que ele não consegue ler
   nem escrever em `tenants/teste/...` (Firestore rules + backend filter).

---

## Verificação por fase

**Embed signup (Fase 1):**
- Onboardar 3171957758 sem erro no popup (após Advanced Access aprovado).
- Conferir nos logs do servidor que `subscribed_apps` retorna
  `success: true` com os campos certos.
- Verificar `token_expires_at` populado no canal Firestore.
- Verificar `is_coexistence == True` na criação (não fallback para
  standard).
- Disparar mensagem do celular 3171957758 para outro número (echo) e
  confirmar que webhook `smb_message_echoes` é processado.

**Refatoração (Fases 2-3):**
- `/api/wa/conversations` retorna conversations do tenant correto.
- Mesma `wa_id` em standard e coexistence aparece como 2 entradas
  separadas.
- Envio outbound usa `conversation.channel_id`.
- UI mostra badge de canal em cada linha da lista.
- Painel de perfil consolida threads do mesmo cliente.
- `phone_routing` atualizado consistentemente em create/deactivate channel.
- Custom claim `tenant_id` injetado em todo Firebase user.
- Firestore Rules bloqueiam acesso cross-tenant.

**Cenário fim:** operador no Cloud API conversando com 3183440484 +
mesmo operador entra no coexistence que já tinha conversa com 3183440484
resulta em **duas threads visíveis e independentes**, com envios indo
pelo canal correto de cada uma. Auditoria de transferência preserva
`sender_user_id` distinto de `channel_owner_user_id`. Tudo isolado dentro
de `tenants/hubloc/...`.

---

## Roadmap pós-Fase 2

Não faz parte deste plano, mas fica registrado como direção:

- **Tenant onboarding UI** (super-admin do Castro Intelligence cria
  tenant via interface).
- **Self-service signup do cliente** (cliente cria conta sem intervenção).
- **Billing por tenant** (uso de mensagens, storage, conversas pagas).
- **White-label** (logo/cor/sub-domínio por tenant).
- **Cross-tenant analytics** (super-admin Castro Intelligence vê uso
  agregado de todos os clientes).
- **Backup/export por tenant** (recursive export de
  `tenants/{id}` → arquivo, útil para compliance e portabilidade).
