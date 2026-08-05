# ADR 0010 — Modo Recepção: pool compartilhada por tenant (`pool_mode`)

- **Status:** aceito (2026-08-04) — implementado no mesmo dia (F0-F3)
- **Contexto:** a Varizemed pediu caixa compartilhada: 3 operadoras atendem
  juntas (quem está disponível responde; folga de uma é coberta pelas
  outras). O ADR 0008 registrou "assumir pra falar" como requisito do modelo
  locadora (Hubloc): thread sem dono → 403 no envio, e o assume gruda o lead
  na vendedora (`sale_owner`) para sempre. Os dois modelos são legítimos —
  a solução é um modo POR TENANT, não uma mudança global.

## Decisão

`system_settings/chat.pool_mode: "legacy" | "reception"` (per-tenant,
default **no READ** `"legacy"` — nunca backfill; kill-switch = PUT
`pool_mode=legacy`, sem deploy). Self-service pelo `PUT /api/settings/system`
existente (RBAC `gerenciar_config_sistema`); select na aba Sistema.
`pool_mode` é eixo **ortogonal** a `crm_model` (PLANO_MODELOS) — NÃO é um
terceiro valor de `CRM_MODEL_OPTIONS`.

Em `reception`, para **operador comum**, **thread SEM dono**, **canal
standard** (coexistence fica FORA — o auto-assign coex é semântico, dono
físico do número; fallback de doc legado sem `source_channel_type` cai no
`channel_type` do canal resolvido):

| Situação | legacy | reception |
|---|---|---|
| Responder órfã standard (lead SEM dono) | 403 | permitido, sem atribuir |
| Responder órfã de LEAD com dono (thread lateral) | 403 | 403 — não é pool; espelha `_require_contact_access` |
| Responder órfã coex | 403 | 403 |
| Thread de OUTRO operador | 403 | 403 (inalterado) |
| `conversation/open` (picker) | auto-atribui a thread | não atribui |
| Auto-close por inatividade | pula órfãs | fecha órfãs com `bot_completed` (bot/backup ficam) |
| Fechar/reabrir manual de órfã (op. comum) | 403 | permitido (toggle RBAC da ação continua valendo) |
| Fechamento re-gruda no `sale_owner` | sim (ADR 0008) | não — fechamento DEVOLVE o lead à pool (zera dono do contato e da conversa fechada; `sale_owner` preservado/inerte) |
| Reabertura pontual (ADR 0009 D3) | volta pro "Meus" | fica na pool (emergente: lead sem dono ⇒ nada a herdar) |

**Autoria desce da thread para a MENSAGEM:** `sender_user_id` (já existia,
Fase 2C) + `sent_by_name` denormalizado novo em `wa_messages` — necessário
porque no snapshot mode o frontend lê o doc direto e não tem o join REST de
`operator_name` (bolha mostrava "Equipe"). Sem prefixo no texto ao cliente
(o opt-in `chat_prefix_enabled` existente cobre quem quiser assinar).

**RBAC novo `assumir_atendimento`** (catálogo + seeds, default ON em todas
as roles — dia 0 idêntico via fallback de role): gate no
`POST /api/wa/assume` e no botão "Assumir atendimento". Perfil custom
"Recepção" com o toggle OFF = operadora que atende a pool mas nunca vira
dona de lead.

## Exceções e supersedes (por tenant em reception)

- **ADR 0008 §"assumir pra falar" e §revert:** invertidos SÓ no tenant em
  reception. Em legacy (Hubloc) nada muda — coberto por asserts de regressão
  (`tools/sim_reception_flow.py`, cenários 1/3/5).
- **ADR 0009 D3 (pontual):** em reception a retomada NÃO cai no "Meus" — o
  comportamento emerge de o lead estar sem dono (a conversa herda dono do
  contato no reopen; contato sem dono ⇒ pool). Supersede parcial registrado.
- **`_require_contact_access` / rules / listeners:** NENHUMA mudança — pool
  sem dono já é visível a todos por design (camadas de LGPD intactas).

## Interações com planos em andamento

- **PLANO_J3 F4 (rules de `wa_messages`):** o ramo "pool sem dono" do
  predicado é VITAL para o reception — removê-lo mata a feature. Num tenant
  reception a F4 entrega ~zero isolamento efetivo (quase tudo é pool) —
  registrar como risco aceito no DPA/RIPD. A F1.1 do J-3 rebaseia
  catálogo/seeds do rbac.py sobre o toggle `assumir_atendimento`.
- **PLANO_MODELOS Fase 2 (`release_lead_to_bot`):** o buraco do reopen 403
  em clinic (PLANO_MODELOS §item 11) é resolvido pelo reception (operador
  comum envia template e responde em contato sem dono). A Fase 2 deve
  respeitar o gate por `pool_mode` ao mexer em
  `database_firestore.py` (região `revert_lead_to_sale_owner` /
  `return_contact_to_bot` — 3 planos na mesma região; o guard do reception
  são 2 linhas no topo do `revert_lead_to_sale_owner`).
- **`sale_owner` é PRESERVADO no doc** (inerte em reception). A limpeza
  global proposta originalmente foi rejeitada (quebraria ADR 0008/Fase 2).

## Limitações aceitas no v1

- **Unread é global por thread:** o primeiro operador que abre zera o badge
  para o time inteiro. (Fix do gatilho de mark-read por CONVERSATION
  incluído; contador por operador fica pra depois se doer.)
- **Sem typing indicator:** risco de resposta dupla aceito (equipe de 3).
  RTDB não existe no projeto; v2 avaliará alternativa barata (campo na
  conversation via backend com debounce) antes de considerar RTDB.
- **`correct-message`** ganhou o mesmo gate de thread dos demais envios
  (era o único caminho de texto sem gate — débito pré-existente quitado).

## Revisão adversarial (2026-08-04) — 6 confirmados, todos corrigidos

Workflow de 15 agentes (3 dimensões + refutação por achado) sobre o diff:

1. **Loop de mark-read (crítico, frontend):** o gatilho por `Math.max` com o
   unread do CONTATO (que nunca zera pelo caminho de thread) + dep nova
   re-disparava 1 POST/1,2s. Fix: com thread ativa o gatilho é o unread da
   CONVERSATION; contato só no fallback sem thread.
2. **Editor de perfis revogava `assumir_atendimento` em silêncio (major):**
   chave nova pós-seed ausente nos docs → draft `=== true` → 1º PUT persistia
   False (e `perfil_admin` travado ficava insalvável). Fix:
   `_fill_missing_toggles` no `list_perfis` (default do seed da
   `role_equivalente` — merge SÓ na listagem administrativa; `has_permission`
   intacto). Padrão a repetir em TODA chave nova de catálogo (vale pro J-3).
3. **Transfer-para-si contornava o toggle (major):** `POST /api/wa/transfer`
   com `to_user_id=eu` virava dono de thread+lead. Fix: auto-transferência
   exige `assumir_atendimento`.
4. **Órfã de LEAD com dono era escrevível (major):** o gate só olhava a
   conversation; thread lateral órfã (2º canal / pós-`reassign-lead`) de lead
   alheio aceitava envio por id determinístico. Fix: ramo órfão exige lead
   sem dono (e o mesmo espelho no fechar manual).
5. **Bot atropelava a recepcionista (major):** envio órfão não silenciava o
   CX em contato mid-bot. Fix: `mark_human_active` best-effort no gate quando
   `bot_completed` é falso (padrão do clear de takeover).
6. **`set-attendance` com doc coex legado (minor):** `_reception_send_allowed`
   ganhou fallback pro `channel_type` denormalizado da própria conversation.

Refutados (registrados, sem ação): open auto-assign em legacy sem o toggle
(pré-existente/escopo), 403 na correção da própria mensagem pós-assume
(especificado acima), reads sem cache (sugestão de eficiência — TTL 60s fica
como melhoria futura).

**Ajustes do canário #2 (2026-08-05):** (a) carregar o CRM não abre mais
conversa nenhuma — o auto-select legado de `allConversations[0]` exibia na
tela uma thread que o operador nunca clicou (seleção órfã também volta pro
placeholder em vez de pular pra 1ª); (b) fechamento em reception passou a
DEVOLVER ativamente o lead assumido/transferido à pool (a implementação
original só evitava o re-gruda do `sale_owner`, mas mantinha o dono atual —
a linha da tabela acima ficava sem caminho de volta pra caixa compartilhada).

**7º achado (canário varizemed-test, 2026-08-05):** o picker de contato
manual (`create_manual_wa_contact`, ramo "reabre/assume") era um TERCEIRO
bypass do gate: operadora "só recepção" abriu o número pelo "+ Nova
conversa" e virou Dona do Lead — lead com dono + thread órfã = invisível
pra pool inteira (o colega perde a janela: contato 403 no lazy-fetch). Fix:
parâmetro `auto_assume` — False quando reception OU perfil sem
`assumir_atendimento` (reabre/cria no pool; só desarquiva). Sintoma
diagnóstico pra reincidência: contato `em_atendimento` + `assigned_to`
preenchido sem transfer_log.

## Validação

`tools/sim_reception_flow.py` (39 asserts, código real de main/rbac/db com
Firestore mockado): gate legacy×reception×coex×thread-de-outro×lead-com-dono,
RBAC do assume (403/409) e do transfer-para-si, mark_human_active, revert
no-op, coerção do `pool_mode`, auto-close da pool, fechar manual de órfã,
merge de toggles no editor de perfis. Regressão: `tools/sim_bot_flow.py`
44/44 intacto. Canário: `varizemed-test` antes de ligar na `varizemed` real.
