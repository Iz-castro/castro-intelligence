# Plano: CRM Multi-Canal, Multi-Departamento com Auditoria

## Contexto

A empresa contratante nao tinha CRM. Operadores usam numeros WhatsApp Business pessoais com clientes recorrentes. O sistema precisa:
- Numero padrao Cloud API com bot (futuro) para novos leads
- Multi-numero coexistence para operadores com numeros proprios
- Departamentos com fluxo de transferencia entre setores
- Dashboard de auditoria para Admin/Supervisor
- Sistema de avaliacao pos-conversao

O CRM atual suporta apenas 1 numero WhatsApp (hardcoded em env vars). Precisa evoluir para multi-canal mantendo retrocompatibilidade.

---

## Respostas as perguntas do Rafal

### Quando operador sai da empresa
**Recomendacao**: Abordagem hibrida:
1. Admin/Supervisor ve lista de contatos do operador desativado
2. Opcoes por contato ou em lote:
   - **"Devolver ao bot"** — `assigned_to = null`, volta para fila de novos leads
   - **"Transferir para operador X"** — reatribui
   - **"Marcar como resolvido"** — qualification = "convertido" ou arquiva
3. Novas mensagens de contatos nao reatribuidos caem automaticamente na fila do bot
4. Para coexistence: admin pode dar o numero para outro operador ou deixar mensagens cairem na fila geral

### Mensagens do coexistence podem ser transferidas entre departamentos?
**Sim**, totalmente possivel. Todas as mensagens (standard e coexistence) passam pelo Firestore. A unica diferenca eh:
- Coexistence: mensagens chegam e sao auto-atribuidas ao dono do numero
- Mas o operador pode transferir para outro departamento normalmente
- Admin/Supervisor ve todas as mensagens de todos os canais

### Sistema de avaliacao
**Recomendacao**: Template aprovado pela Meta com mensagem interativa (lista de opcoes 1-10). Quando o lead responde com um numero, o sistema captura automaticamente. A mensagem de avaliacao e a resposta ficam invisiveis para operadores — apenas Admin/Supervisor ve no dashboard.

---

## Arquitetura Proposta

### 1. Nova colecao: `channels`

Substitui as env vars hardcoded. Cada numero WhatsApp conectado eh um canal.

```
castro_crm_channels:
  id: int
  channel_type: "standard" | "coexistence"
  label: str                        # "Bot Principal", "Timmy Pessoal"
  waba_id: str
  phone_number_id: str
  display_phone_number: str
  access_token: str                 # por canal (do embedded signup ou env var)
  owner_user_id: int | null         # null = canal compartilhado (bot)
  owner_firebase_uid: str
  default_department_id: int | null
  is_bot_enabled: bool              # placeholder para bot futuro
  is_active: bool
  webhook_subscribed: bool
  created_at, updated_at: datetime
```

### 2. Campos novos em `wa_contacts`

```
+ channel_id: int | null            # FK channels.id
+ phone_number_id: str              # denormalizado para query rapida
+ source_channel_type: str          # "standard" | "coexistence"
+ original_operator_id: int | null  # operador que primeiro atendeu (para lead retornante)
+ converted_by_user_id: int | null
+ rating: int | null                # 1-10
+ rating_requested_at: datetime | null
```

### 3. Campos novos em `wa_messages`

```
+ channel_id: int | null
+ phone_number_id: str
+ is_rating_message: bool           # true = msg de avaliacao
+ visibility: "all" | "admin_only"  # rating msgs sao admin_only
```

### 4. Nova colecao: `audit_metrics` (pre-agregada)

```
castro_crm_audit_metrics:
  date: str                         # "2026-04-08"
  user_id: int | null               # null = agregado global
  total_leads_received: int
  total_leads_assumed: int
  total_messages_inbound: int
  total_messages_outbound: int
  messages_by_half_hour: map        # {"07:00": 5, "07:30": 12, ...}
  first_activity_at: datetime
  last_activity_at: datetime
  ratings_sum: int
  ratings_count: int
```

### 5. Nova colecao: `ratings`

```
castro_crm_ratings:
  id: int
  contact_id: int
  operator_id: int                  # quem converteu
  rating_value: int | null          # 1-10
  requested_at: datetime
  responded_at: datetime | null
```

---

## Mudancas nos arquivos criticos

### `channel_service.py` (NOVO)
Modulo central que substitui todas as refs a `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID`.
- `get_channel(channel_id)` / `get_channel_by_phone_id(phone_number_id)`
- `get_default_channel()` — canal bot/standard
- `get_channels_for_user(user_id)` — canais que o usuario pode acessar
- `get_send_credentials(channel_id)` → `(token, phone_id, base_url)`
- Cache em memoria com refresh periodico

### `main.py` — Envio de mensagens
Linhas 768, 801, 858, 916, 701: trocar `WHATSAPP_PHONE_NUMBER_ID` hardcoded por lookup via `channel_service.get_send_credentials(contact.channel_id)`.

### `webhook.py` — Roteamento de mensagens
Linha 115+: extrair `phone_number_id` do payload Meta (`value.metadata.phone_number_id`), resolver canal, e:
- Canal standard: `assigned_to = null` → fila "Novos"
- Canal coexistence: `assigned_to = channel.owner_user_id` → "Meus Atendimentos" do dono
- Lead convertido retornando: reatribuir ao `original_operator_id`

### `media.py` — Upload/envio de midia
Linhas 530, 561: parametrizar com `channel_id` para usar token/phone_id do canal correto.

### `database_firestore.py` — Schema e CRUD
- Adicionar campos novos em `upsert_wa_contact` e `save_wa_message`
- CRUD completo para departments (create, update, deactivate, reorder)
- CRUD para channels
- Funcoes de metricas: `increment_audit_metrics(date, user_id, metric, value)`
- Funcoes de rating: `create_rating`, `capture_rating_response`

### `config.py`
- Remover "sem_classificacao" de QUALIFICATION_OPTIONS (ja esta ok, so tem 5 opcoes)
- Manter env vars como fallback para bootstrap do canal default

### Frontend: `CrmContext.tsx`
- Carregar canais do backend
- Filtrar contatos por canal no "Meus Atendimentos" (coexistence auto-assigned)
- Filtrar mensagens de avaliacao por role
- Novo estado para dashboard

### Frontend: `App.tsx`
- Indicador visual de canal na lista de contatos (icone/badge)
- Admin: tela de gerenciamento de canais
- Admin: CRUD de departamentos
- Admin: opcoes de reatribuicao quando operador sai
- Botao "Devolver ao bot" (admin/supervisor)
- Dashboard de auditoria (novo componente)

### Frontend: `DashboardPage.tsx` (NOVO)
- Cards resumo (leads, assumidos, mensagens)
- Grafico de barras por operador
- Heatmap de pico de mensagens (buckets 30min, 07:00-17:00, seg-sex)
- Tabela de avaliacoes (admin/supervisor only)
- Botao de download/export

---

## Fluxos principais

### Fluxo: Novo lead chega pelo bot
```
Meta webhook → extrair phone_number_id → resolver canal "standard"
→ upsert_wa_contact(channel_id, assigned_to=null, qualification="novo")
→ aparece em "Novos" para todos operadores do departamento
→ operador assume → "Meus Atendimentos"
→ transfere entre departamentos conforme necessidade
→ marca "convertido" → envia template de avaliacao → captura nota
```

### Fluxo: Mensagem chega no coexistence do Timmy
```
Meta webhook → extrair phone_number_id → resolver canal "coexistence" do Timmy
→ upsert_wa_contact(channel_id, assigned_to=timmy.id, source="coexistence")
→ aparece em "Meus Atendimentos" do Timmy
→ Admin/Supervisor tambem ve (view "Equipe")
→ Timmy pode transferir para outro departamento se necessario
```

### Fluxo: Lead convertido retorna
```
Meta webhook → upsert_wa_contact → detecta qualification="convertido"
→ verifica rating pendente? Se sim, captura nota
→ senao: reatribui ao original_operator_id
→ muda qualification para "em_atendimento"
→ aparece em "Meus Atendimentos" do operador original
```

### Fluxo: Operador sai da empresa
```
Admin desativa usuario → sistema lista contatos atribuidos
→ Admin escolhe por contato ou lote:
  - Devolver ao bot (assigned_to=null, qualification="novo")
  - Transferir para operador X
  - Marcar como resolvido/arquivar
→ Novas msgs de contatos sem operador caem na fila do bot
```

---

## Fases de implementacao

### Fase 1: Fundacao (canais + departamentos)
1. Criar `channel_service.py` com registry e cache
2. Criar colecao `channels` no Firestore
3. Migrar env vars para canal default no bootstrap
4. CRUD de departamentos (backend API + frontend admin)
5. Limpar qualificacao (remover "sem_classificacao")

### Fase 2: Multi-canal backend
6. Refatorar endpoints de envio (main.py, media.py) para usar `channel_service`
7. Refatorar webhook routing com extracao de `phone_number_id`
8. Adicionar `channel_id`/`phone_number_id` em wa_contacts e wa_messages
9. Auto-atribuicao de contatos coexistence ao dono do canal
10. Integrar embedded signup para criar canais

### Fase 3: Multi-canal frontend
11. Indicador de canal na lista de contatos
12. Filtros de canal em CrmContext
13. Admin: tela de gerenciamento de canais
14. Admin: reatribuicao em lote

### Fase 4: Avaliacao + leads retornantes
15. Template de avaliacao (criar na Meta)
16. Envio automatico ao marcar "convertido"
17. Captura de resposta no webhook
18. Visibilidade filtrada por role
19. Roteamento de lead convertido retornante

### Fase 5: Dashboard + export
20. Instrumentar `save_wa_message` para `audit_metrics`
21. API endpoints do dashboard
22. Frontend dashboard com graficos (Recharts)
23. Sistema de export CSV/JSON com download

### Fase 6: Bot placeholder + polish
24. Endpoint "devolver ao bot"
25. Flag `is_bot_enabled`, documentacao para futuro dev do bot
26. Decomposicao incremental do App.tsx monolitico
27. Testes end-to-end

---

## Riscos e dependencias

| Risco | Impacto | Mitigacao |
|-------|---------|-----------|
| Tokens de coexistence expiram | Alto | Trocar por System User token de longa duracao apos signup |
| Template de avaliacao precisa aprovacao Meta | Medio | Submeter cedo, nao bloqueia outras fases |
| Firestore queries sem indice composto | Medio | Criar indices para (channel_id, last_message_at) |
| Race condition ao assumir lead | Medio | Usar Firestore transaction no assume |
| App.tsx monolitico (1600 linhas) | Baixo | Decompor incrementalmente ao tocar cada area |

---

## Verificacao

1. **Canal standard**: enviar msg do numero de teste → aparece em "Novos" → operador assume → aparece em "Meus Atendimentos"
2. **Canal coexistence**: msg chega no numero do operador → aparece auto-atribuida em "Meus Atendimentos" do operador + visivel para admin
3. **Transferencia inter-departamento**: transferir contato de Comercial → Cadastro → verificar que aparece no departamento correto
4. **Avaliacao**: marcar convertido → verificar template enviado → responder 1-10 → verificar nota no dashboard (invisivel para operador)
5. **Lead retornante**: lead convertido envia msg → cai no operador original
6. **Dashboard**: verificar metricas, graficos, export CSV
7. **Operador sai**: desativar usuario → reatribuir contatos → verificar que msgs novas caem na fila
