# Plano: Lead × Atendimento × Mensagem + Regras de Negócio (híbrido WABA + Coexistence)

> **Status:** rascunho de design/ação para executar em sessão futura.
> **Origem:** análise de regras de negócio do Rafal (2026-05-27) + resposta do PO,
> motivados por bugs reais de produção (mesmo `wa_id` em várias threads,
> "Nenhum canal configurado" em canal coex antigo após re-signup, faixa de
> contexto mostrando "Conversa no número: —").
> **Relacionado:** [PLANO_COEXISTENCE_REFATORACAO.md](PLANO_COEXISTENCE_REFATORACAO.md)
> (multi-tenant + sub-threads por canal — base já parcialmente entregue),
> [decisions/0002-lgpd-canal-coex-compartilhado.md](decisions/0002-lgpd-canal-coex-compartilhado.md).

---

## 0. Veredito sobre A + B + C (o que motivou este doc)

Na sessão anterior eu havia proposto 3 patches:

- **A.** Denormalizar número/label/ativo do canal no doc do Atendimento (`wa_conversations`).
- **B.** Faixa de contexto mais honesta (número + badge de canal inativo; papel correto).
- **C.** Threads de canal inativo/removido viram "somente leitura" e somem da lista.

**Conclusão: A+B+C NÃO entra como patch isolado.**
- **C conflita diretamente** com a estratégia do PO para re-login coexistence: o
  PO quer **merge lógico** (mesmo operador + mesmo número ⇒ timeline contínua,
  *rebind* do canal), **não** uma thread antiga "somente leitura" separada.
- **A** sobrevive e é útil (o Atendimento precisa saber seu canal), mas deve ser
  feito junto da denormalização do modelo, não solto.
- **B** sobrevive como versão pequena da "apresentação por canal" (Fase 2).

Portanto: seguir o plano faseado abaixo. **Nada de A/B/C avulso.**

---

## 1. Insight central: o modelo de dados já está ~80% lá

O PO descreve três entidades. Elas **já existem** no Firestore:

| Entidade (PO) | Coleção atual | Chave |
|---|---|---|
| **Lead** (contato único, agenda, tags) | `tenants/{tid}/wa_contacts` | `id`; dedupe atômico por `wa_contact_index/{wa_id_canonico}` |
| **Atendimento** (thread/sessão por canal) | `tenants/{tid}/wa_conversations` | `id = "{channel_id}__{wa_id}"` |
| **Mensagem** | `tenants/{tid}/wa_messages` | `conversation_id` + `wa_message_id` (idempotente) |
| Canal (número de negócio) | **flat** `castro_crm_channels` | `id`; `channel_type` standard\|coexistence, `owner_user_id`, `display_phone_number`, `phone_number_id`, `access_token`, `active` |
| Roteamento webhook→tenant | flat `phone_routing/{phone_number_id}` | — |

> ⚠️ **Canais são flat/global** (`castro_crm_channels`), não tenant-scoped.
> `wa_contacts`/`wa_conversations`/`wa_messages` são tenant-scoped. Qualquer
> diagnóstico precisa usar `global_collection("channels")` para canais e
> `set_tenant_context(tid)` para o resto.

**Implicação:** o "refactor" é majoritariamente **regras de negócio +
apresentação + o merge de re-login**, e **não** um rewrite de schema. Isso
reduz muito o risco. O que falta, em ordem de dor:

1. **Re-login coex cria canal novo cego** → threads duplicadas e canal antigo
   morto (`active=False`) com conversas órfãs que dão "Nenhum canal configurado".
2. **Apresentação não deixa claro de qual canal/número é cada Atendimento**
   (faixa mostra "—" no modo snapshot; operador não tem lista de canais).
3. **Dono é do Lead, não do Atendimento** — a transferência move o contato mas
   não os Atendimentos; papel do usuário na thread fica ambíguo.
4. Sem **Painel de Conflitos**, sem **sticky routing com TTL**, sem
   **auto-close**, sem **protocolo por dia/thread padronizado**, sem
   **tipificação/resumo de auditoria**.

---

## 2. Diagnóstico concreto que originou o doc (dados reais de prod)

Contato `1870` (Lead "Rafa Timmy" `+55 31 98344-0484`), tenant `hubloc`, tinha
**4 Atendimentos**, um por canal que o tocou:

| Atendimento | Canal | Número (dono) | `active` | Sintoma |
|---|---|---|---|---|
| `3__…` | 3 | 9934-6195 (Izael, owner 2) | ✅ | conversa atual |
| `5__…` | 5 | 7195-7758 (teste1 **novo**, owner 4) | ✅ | ok |
| `4__…` | 4 | 7195-7758 (teste1 **antigo**, owner 4) | ❌ | **"Nenhum canal configurado"** |
| `2__…` | 2 | 9922-1744 (gerência, owner 3) | ✅ | thread antiga |

Canais `1` e `4` estão `active=False` (onboardings antigos do mesmo número
físico 7195-7758 antes do re-signup que criou o canal `5`). Causa exata do erro
de envio: `get_send_credentials` ([channel_service.py:155](../channel_service.py))
não acha canal inativo no cache → `ValueError` → `_resolve_channel_creds_by_id`
([main.py:1155](../main.py)) sem fallback de coex → 503 "Nenhum canal WhatsApp
configurado".

---

## 3. Regras de negócio alvo (com aterramento no código)

### 3.1 Dono do **Atendimento**, não só do Lead
- **Hoje:** `assign_wa_contact` ([database_firestore.py:1288](../database_firestore.py))
  atualiza só `wa_contacts.assigned_to`; os Atendimentos (`wa_conversations`)
  mantêm o `assigned_to` antigo. Daí o papel ambíguo na faixa.
- **Alvo:** "Dono do Lead" (CRM/agenda) e "Dono do Atendimento" (quem toca a
  thread) são campos distintos e ambos exibidos. Transferência opera no
  **Atendimento** selecionado (muda `wa_conversations.assigned_to`), não no Lead
  inteiro — a menos que admin queira reatribuir o Lead.
- **Faixa de contexto** deve usar `conversation.assigned_to` para "Você: dono do
  atendimento" e `contact.assigned_to` para "Dono do lead", e **não** inferir
  "handler" de `takeover_handler_user_id` quando `takeover_status == none`
  (bug atual da faixa).

### 3.2 Coexistence: anarquia controlada (não dá pra travar o app do celular)
- **Regra:** número **coex** pode criar Atendimento paralelo com Lead que já tem
  dono (a Meta já permitiu a mensagem). Sistema **registra + alerta**, não bloqueia.
- **Número API padrão (não-coex):** aí sim o CRM bloqueia "roubo" — só
  dono/admin/supervisor manda na janela 24h ou template. Já existe base em
  `_check_conv_send_permission` ([main.py:1230](../main.py)) e
  `create_manual_wa_contact` ([database_firestore.py:1059](../database_firestore.py));
  estender para diferenciar `channel_type` coex vs standard.
- **Painel de Conflitos (supervisor):** lista Leads com ≥2 Atendimentos **ativos**
  com operadores distintos. Query sobre `wa_conversations` agrupada por
  `contact_id`. Novo endpoint admin + aba no frontend.
- **Intervenção do supervisor — 3 modos (decisão do PO, 2026-05-27):** substitui
  o "bypass admin" cego por modos com intenção/auditoria claras:
  1. **Sussurro (nota interna):** `direction="internal"` em `wa_messages`, NÃO vai
     pra Meta; orienta o operador, cliente não vê. ✅ FEITO (`/api/wa/internal-note`,
     toggle 🔒 no composer, bolha amarela).
  2. **Co-pilotagem (intervenção assinada):** admin/sup envia ao lead **sem assumir**.
     ✅ FEITO — `_check_conv_send_permission` retorna `"intervention"` p/ admin/sup
     não-dono (bypass) e `/api/wa/send` faz prepend `[Supervisao - {1º nome}]:` +
     grava `sender_user_id=supervisor` (thread owner intacto); faixa de aviso no
     frontend. A permissão coex×standard p/ operador comum já era emergente (takeover
     é coex-only) e `create_manual_wa_contact` (manual = standard) já bloqueia certo.
  3. **Assunção (takeover do supervisor):** ✅ FEITO —
     `POST /api/wa/conversation/{id}/supervisor-takeover` (admin/sup) assume a thread
     via 3B (muda só o Dono do Atendimento) + avisa o lead com texto se ≤24h, senão
     assume sem msg. Botão "Assumir como supervisor" na faixa de intervenção.
     **Pendente (v2):** operador antigo ver a thread em read-only (hoje ela só sai
     da view dele, como numa transferência).

### 3.3 Re-login coexistence = **merge/rebind**, não canal novo (substitui o C)
- **Hoje:** Embedded Signup ([main.py](../main.py), handler `embedded_signup`)
  sempre faz `create_channel` → novo `channel_id` → novas threads; canal antigo
  fica `active=False` com conversas órfãs.
- **Alvo:** se já existe canal com **mesmo `owner_user_id` + mesmo número físico**
  (normalizar `display_phone_number`), **rebindar** o canal existente:
  atualizar `waba_id`, `access_token`, `token_expires_at`, `phone_number_id` e o
  índice `phone_routing/{novo_phone_number_id}` → mesmo `channel_id`, mesmas
  threads (`{channel_id}__{wa_id}`), timeline contínua.
- **Dedup de mensagens no re-sync já está garantido**: `save_wa_message`
  ([database_firestore.py:1417](../database_firestore.py)) é idempotente por
  `wa_message_id`; e o gate `_media_already_downloaded`
  ([webhook.py](../webhook.py)) evita re-baixar mídia. Ou seja, re-sync não
  duplica mensagem — só o `channel_id` novo é que duplicava **thread**. Rebind
  resolve.
- **Confirmado (decisão #1):** o `phone_number_id` **NÃO muda** no
  re-onboarding do mesmo número, então a **chave de detecção/dedup é o
  `phone_number_id`** e o `phone_routing` não troca de chave — só é reapontado
  para o `channel_id` reaproveitado. Como `conversation_id` usa `channel_id`, as
  threads sobrevivem ao rebind. ⚠️ A detecção tem que ler o Firestore **direto**:
  `get_channel_by_phone_id`/cache carrega **só canais ativos**
  ([channel_service.py:70](../channel_service.py)) e não enxerga o canal
  desativado que o rebind precisa reativar.
- **Migração dos órfãos atuais** (canais 1, 4 inativos + conv `4__…`): script de
  rebind/merge para o canal ativo correspondente, ou arquivamento explícito.

### 3.4 Sticky routing (afinidade) + TTL — só no número API padrão
- **Hoje:** já existe parcial — `original_operator_id`/`converted_by_user_id` no
  contato e o reroute em `_process_messages` ([webhook.py](../webhook.py))
  ("lead convertido retorna → reatribui operador original").
- **Falta:** TTL/condições do PO — se o dono está offline/férias ou a última
  venda foi há > N dias (sugestão 30), cai pro bot/fila em vez de forçar o dono.
  Requer sinal de presença/`last_seen` e `converted_at`.

### 3.5 Auto-close por inatividade
- **Hoje:** já existe cron `expire_stale_takeovers` ([database_firestore.py:803](../database_firestore.py))
  + Cloud Scheduler `castro-crm-expire-takeovers` (*/30). É a base ideal.
- **Alvo:** estender para um **status de Atendimento** (`attendance_status`:
  `aberto` | `fechado_inatividade` | `fechado_manual`). Fechar quando última
  mensagem > 24h. Fechar deixa pendente a **tipificação** (3.7).

### 3.6 Protocolo por dia/thread
- **Hoje:** `attendance_protocol`/`attendance_started_at` no contato
  (`set_attendance_protocol`), por-contato, não por-dia-por-thread.
- **Alvo:** padrão `YYYYMMDD-{LEAD_ID}-{SETOR}` (ex.: `20260527-1870-VEN`),
  gerado por dia, vinculado ao Atendimento. Busca por protocolo (admin/sup) →
  renderiza as mensagens daquela thread/dia. Novo endpoint de busca.

### 3.7 Auditoria: tipificação obrigatória + resumo por IA
- **Tipificação no fechamento:** Categoria / Sub-categoria / Status
  (catálogo configurável por tenant). Sem isso, relatórios viram texto sujo.
- **Resumo LLM em background:** ao fechar Atendimento, gatilho (Cloud
  Run/Tasks) manda o transcript pro Vertex AI → resumo de 2 linhas
  (motivo + desfecho) na tela de auditoria. **Compliance:** isso é novo
  processamento de dado pessoal → atualizar RoPA/RIPD
  ([compliance/](compliance/)), definir retenção e minimização (mandar só o
  necessário; considerar anonimização parcial).

### 3.8 Agenda por operador (decisão em aberto — ver §6)
- **Hoje:** `notes`/`declared_name` no contato são **compartilhados** (do Lead).
- **PO:** "cada operador tem uma agenda". Decidir: nota **por (operador, lead)**
  (subcoleção) vs nota do Lead compartilhada. Impacta LGPD e o Painel de
  Conflitos.

---

## 4. Apresentação no frontend (absorve A e B)

> **Status (2026-05-27):** entregue como **Fase 2a** (commit `957cef2`, prod) —
> denormalização + faixa honesta + read-only de canal inativo. As **abas por
> atendimento (Fase 2b) foram ADIADAS** por decisão do PO: a sidebar já lista
> cada canal como linha distinta (`ContactList`, `renderItems` = 1 por
> conversa), então a separação por canal já existe; as abas são refinamento de
> navegação, não correção de bug. Quando reabrir, há dois sabores:
> - **2b-light (baixo risco, só frontend):** barra de abas dentro da `ChatPanel`
>   agrupando `conversations.filter(c => c.contact_id === selectedContact.id)`;
>   clicar a aba só faz `setSelectedThreadId`. Não toca backend/filtros.
> - **2b-full (médio risco):** sidebar passa a 1 linha por **contato** (colapsa
>   as N conversas) + unread agregado + abas como navegação primária. Exige
>   refatorar `renderItems` e os **filtros das views** (novos/meus/equipe/bot),
>   que hoje operam por-conversa → mudam de semântica (ex.: "Equipe" com um
>   contato tendo conversas de 2 operadores). É decisão de produto.
>
> Recomendação: se reabrir, começar pela **2b-light**.

- **Ficha do Lead com abas/divisões por Atendimento** (canal):
  `📱 Coex (OpV1) [ativo]` · `🏢 Empresa 2121 (OpV3) [ativo]` · `📱 7195-7758 [canal removido]`.
  Mensagens **não** se mesclam entre canais; cada aba é um Atendimento.
- **Denormalizar no `wa_conversations`** (era o A): `channel_display_phone_number`,
  `channel_label`, `channel_active`, `channel_type` gravados no
  `upsert_wa_conversation` ([database_firestore.py](../database_firestore.py)) +
  **backfill** das existentes. Sem isso, o modo snapshot não tem como exibir o
  número (o join com canal só acontece no REST `/api/wa/conversations`
  [main.py:970](../main.py); operador nem recebe `/api/admin/channels`).
- **Faixa honesta** (era o B): número + badge "canal removido/antigo"; papel
  correto (§3.1).
- **Atendimento de canal inativo:** badge "somente leitura — canal removido" e
  composer desabilitado (em vez do 503 cru). Após o merge (§3.3), esse caso
  praticamente some.

---

## 5. Plano de ação faseado (ordem por dependência/risco)

> Premissa do PLANO existente: o Firestore **pode ser zerado** antes de produção
> real multi-cliente. Isso simplifica migrações/backfills. **Confirmado
> (decisão #7 — ver §6): pode zerar** (com export da Helenice antes do wipe).
> **Atualização (2026-05-27): o wipe deixou de ser PRÉ-REQUISITO** — as fases
> foram entregues evoluindo a base viva (backfills/scripts, sem zerar). Continua
> válido como **higiene opcional** antes do 1º cliente real pago (limpar canais
> duplicados 1/4 + contatos/dados de teste).

- **Fase 1 — Re-login = rebind de canal (§3.3).** Maior dor + destrava o resto.
  Detectar canal existente por **`phone_number_id`** (decisão #1) e dar UPDATE
  (reativar + novo token + reapontar `phone_routing`), em vez de `create_channel`.
  Sob o wipe (decisão #7) **não há merge de órfãos** — deploy do rebind → export
  da Helenice → wipe → re-onboard limpo.
  *Risco: médio (toca onboarding + cache de canais + roteamento).*
- **Fase 2 — Apresentação por Atendimento (§4).** **2a CONCLUÍDA (commit
  `957cef2`, prod):** denormalização (incl. `channel_type`) + REST cai no denorm
  p/ canal inativo + `normalizeConversation` mapeia `channel_active` + composer
  read-only + backfill (`scripts/backfill_conversation_channel_denorm.py`, 98
  convs). **2b (abas) ADIADA** — ver nota no §4. *Risco: baixo.*
- **Fase 3 — Dono do Atendimento + Conflitos (§3.1, §3.2). CONCLUÍDA em prod:**
  3A Conflitos (`5b121e2`); 3B desacople Dono-Atendimento×Lead; e os 3 modos do
  supervisor — Modo 1 Sussurro, Modo 2 Co-pilotagem assinada, Modo 3 Takeover.
  Pendente só o nice-to-have de read-only pro operador antigo após takeover (v2).
- **Fase 4 — Ciclo de vida (§3.5). CONCLUÍDA em prod:** campo
  `attendance_status` (`aberto`/`fechado_inatividade`/`fechado_manual`);
  reabre em qualquer mensagem (inbound ou outbound); `close_stale_attendances`
  plugado no **cron `*/30` existente** (auto-close de atendimentos
  ATRIBUÍDOS ociosos > `ATTENDANCE_AUTOCLOSE_HOURS`, **6h em prod** — encaixa
  no fechamento operacional 17h da Hubloc); endpoint
  `POST /api/wa/conversation/{id}/set-attendance` p/ fechar/reabrir manual
  (zera takeover no fechar). UI: badge "fechado" na faixa + item
  "Fechar/Reabrir atendimento" no menu ⋮. **Pendente:** sticky routing TTL
  (§3.4) e operador read-only pós-takeover supervisor (v2).
- **Fase 5 — Protocolo + Auditoria/IA (§3.6, §3.7).** Protocolo por dia/thread,
  busca por protocolo, tipificação obrigatória, resumo Vertex em background,
  relatórios. *Risco: baixo no protocolo; IA exige update de compliance.*

Cada fase: staging→prod no mesmo gate usado hoje
(`gcloud run deploy castro-crm-staging … && … castro-crm …`), com health check.

---

## 6. Decisões

### Resolvidas (2026-05-27) — destravam a Fase 1
- **#1 — Re-login / chave de dedup:** `phone_number_id` **NÃO muda** no
  re-onboarding do mesmo número (canais 1/4/5 do 7195-7758:
  `phone_id=1055982807598158` / `waba=680503338460083` idênticos). ⇒ detecção e
  dedup por **`phone_number_id`**; rebind = **UPDATE** (reativar + novo token),
  não `create_channel`. Acionado em §3.3 e na Fase 1 (§5).
- **#2 — Órfãos atuais:** híbrido por dono — merge só com mesmo `owner_user_id`
  + mesmo `phone_number_id`; dono diferente = **arquivar** (não mesclar, preserva
  autoria). **Moot sob o wipe (#7):** a Fase 1 pula o merge; o rebind impede
  novos órfãos.
- **#7 — Reset do Firestore:** **PODE ZERAR.** Offboarding no celular +
  re-signup re-libera o sync coex (contatos + histórico ≤6m). Ressalva: dados
  só-do-CRM (`declared_name`, notas, qualificação, protocolo, avaliação) **não**
  voltam — exportar antes (ver checklist da Helenice). Caminho: deploy do
  rebind → export → wipe → re-onboard limpo.

### Em aberto (responder antes das fases seguintes)
3. **Agenda (§3.8):** por-operador (subcoleção `wa_contacts/{id}/notes/{uid}`) ou
   compartilhada do Lead? (impacto LGPD).
4. **Sticky routing TTL:** N dias (sugestão 30)? Como detectar dono
   offline/férias (precisa de `last_seen`/flag de ausência)?
5. **`attendance_status`:** novo campo no `wa_conversations`? Fechar zera takeover
   também?
6. **Tipificação:** catálogo fixo ou configurável por tenant? Onde editar?

---

## 7. Compliance (LGPD) — não esquecer

- Painel de Conflitos e visão cross-operador para admin/supervisor seguem o
  modelo de isolamento por tenant + rules; nada de filtro só no backend.
- Resumo por LLM (Vertex) = novo tratamento → atualizar RoPA/RIPD, definir
  retenção, minimizar transcript enviado.
- Agenda por-operador vs compartilhada muda a superfície de exposição entre
  operadores — decidir com a diretriz de minimização em mente.
- Manter `audit_log` em toda mutação cross-user (transferência, rebind,
  fechamento, intervenção de supervisor).

---

## 8. O que já está pronto e ajuda (não reinventar)

- Dedupe atômico de Lead por `wa_contact_index` + idempotência de mensagem por
  `wa_message_id` (re-sync não duplica mensagem).
- `pending_webhook_events` (zero perda) — reusar no rebind.
- Cron `expire_stale_takeovers` + Scheduler (base do auto-close).
- Distinção `channel_owner_user_id` × `sender_user_id` em `wa_messages` (auditoria
  coex).
- Takeover temporário (pending/active/none) — vira caso particular do "Dono do
  Atendimento".
- Reroute de lead convertido (base do sticky routing).
