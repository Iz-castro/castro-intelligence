# Plano: reabertura em lote por público — Recepção e Bot (v2.2)

**Data:** 2026-09-30. **Status:** **todas** as decisões de produto fechadas com o PO (23, 24 e 30/09); implementação não iniciada.
**Histórico:** proposta de 22/09 (revisão adversarial: 23 achados) → v2 de 23/09 (19 achados) → v2.1 de 23/09 com P1–P4 em 24/09
→ **v2.2** (verificação final de 24/09: 19 achados, incorporados; ver Apêndice B). Apêndice A resume o que mudou desde a proposta original.
**Atalho operacional:** `scripts/reopen_bot_audience_once.py` executa o público Bot pelas regras deste plano antes da UI (dry-run por
padrão; ressalvas no docstring: hoje Continuar ainda leva à equipe e Encerrar ainda é permanente). Executado em 23/09: 368 envios.

**Objetivo:** o admin/supervisor escolhe na tela de reabertura em lote **quem** recebe a retomada: leads em atendimento humano
(**Recepção**) ou leads em fase de bot (**Bot**). Quem está com o bot e clica em Continuar volta a falar com a Val, não com a
equipe. O lote continua reutilizando o motor da Frente C2 (scan, worker, template, auto-resolve).

Este plano parte do código local e de leituras só-de-leitura feitas na Meta e no Firestore de prod em 23–24/09. Nada aqui foi
aplicado em produção além do script one-off.

---

## 0. Decisões do PO (fonte da verdade deste plano)

| # | Decisão | Data |
|---|---|---|
| D1 | Lead **sem aceite LGPD** (aviso pendente ou recusado) **nunca** entra em reabertura em lote, em nenhum público. | 23/09 |
| D2 | Público **Bot é definido por estado** (lead em fase de bot), não por "prova de resposta do agente". Lead devolvido ao bot por fechamento automático entra no Bot. | 23/09 |
| D3 | **Continuar** no público Bot dispara um **turno do CX** e a Val responde. Não vai para a equipe. | 23/09 |
| D4 | **Encerrar não é permanente**: nova mensagem do lead desfaz a marca (emenda do ADR 0009 D2). | 23/09 |
| D5 | Lead `novo` **pós-handoff sem atendimento** (caso 3) entra no público Recepção. | 23/09 |
| D6 | Fechamento **manual** exige desfecho terminal (gate existente) e portanto sai de todos os públicos. | 23/09 |
| D7 | Teto diário **250 por portfólio** (Hubloc, Varizemed e teste compartilham o TIER_2K do portfólio "Castro Operações WhatsApp"), começando como teste e configurável por env. | 23/09 |
| D8 + P1 | Teto por contato: **2 retomadas em 90 dias nos dois públicos**, lista única por contato, que não zera com mensagem. | 23–24/09 |
| D9 | "Encerrar sem resposta" no público Bot = carimbar como resolvido e fechar a thread **em silêncio** (sem devolução ao bot, sem mensagem de sistema, qualificação intacta). | 23/09 |
| D10 | **Mídia em fase de bot** vira turno do bot (CRM) e a resposta correta é do agente (Izael, playbook). | 23/09 |
| D11 + P3 | Hubloc: **todo o reabrir em lote desligado** até o nome de exibição do número ser aprovado. | 23–24/09 |
| D12 | **Templates**: os já aprovados (`varizemed_retomada_generica_utility_v1`; `atualizao_de_solicitao` na Hubloc). Sem template novo. | 23/09 |
| D13 | Texto enviado ao CX no Continuar = **rótulo do botão** clicado; contexto vai como **parâmetro de sessão** `origem=retomada_lote`. | 23/09 |
| D14 + P2 | Versão da política LGPD como **data** editável pelo admin da clínica na aba Sistema; reperguntar quem aceitou **antes** da data vigente; o lote exclui esses leads; vale também para a Hubloc (3.4). | 23/09–30/09 |
| P4 | Idade máxima de **30 dias** para `novo` pós-handoff **na Recepção**; o público Bot **não** tem teto de idade. Cadência semanal pelo admin da empresa. | 24/09 |
| P5 | Lead que já teve **desfecho com a Val** (agendou, recebeu o link) fica fora do público Bot; depende do sinal `desfecho_bot` do agente. | 24/09 |

**P2b fechada em 30/09 (3.4):** campos LGPD em `system_settings` editados pelo admin na aba Sistema; comparação pela data do
aceite; lote exclui quem aceitou antes da política vigente; o bot builtin da Hubloc também passa a ler os campos. Nenhuma
decisão de produto em aberto; restam só dependências externas (playbook do Izael, nome de exibição da Hubloc).

---

## 1. Funcionamento atual verificado (código local, 2026-09-24)

| Parte | Comportamento atual | Referência |
|---|---|---|
| Público do lote | `qualification == em_atendimento`; não olha `bot_completed`, dono nem status da thread | `database_firestore.scan_reopen_candidates` |
| Espera | ≥ 24h desde `last_inbound_at` do contato; cooldown por `last_reopen_template_at`; `reopen_attempts >= 1` vira auto-resolve; `reopen_resolved_at` = já resolvido | mesma função; `config.REOPEN_*` |
| Exclusões | arquivado, backup, `reopen_opt_out`, `lgpd_revoked` | mesma função |
| Promoção de qualificação | `novo → em_atendimento` só no 1º outbound com `sender_user_id`; bot não promove | `save_wa_message` |
| Fechamento em `reception` | manual ou cron → `release_lead_to_bot`: `bot_completed=False`, dono limpo em todas as threads, qualificação preservada, `lgpd_*` preservados. **Não envia nada ao cliente** | `set_attendance_status`, `close_stale_attendances`, `_close_daily_and_send_protocol` |
| Fechamento manual | gate exige desfecho terminal (`convertido`, `nao_convertido`, `qualificado`, `nao_qualificado`) | `main.py` set-attendance |
| Válvula de 7 dias | handoff sem resposta humana não fecha por 7 dias; depois o cron fecha e devolve ao bot, mesmo com auto-close desligado. `handoff_at` tem um único escritor (o bot) e um único significado | `_reception_handoff_unattended`, `_reception_unattended_release_due` |
| Thread em fase de bot | o cron **nunca** fecha (`bot_completed` falso). Vale para toda conversa com a Val | `close_stale_attendances` |
| Carimbos da thread | `last_outbound_at` sobe em **qualquer** outbound; `last_human_outbound_at` só com `sender_user_id` e `human_outbound=True`; ambos **datetime**; nunca zerados no fim de ciclo | `upsert_wa_conversation`, `save_wa_message` |
| Botão do template | `button` curto-circuita antes do bot. Retomar/Continuar: thread `aberto` + `mark_contact_bot_done` **incondicional** se `bot_completed` falso. Encerrar: `fechado_cliente` + `reopen_opt_out` + recibo. O clique não carrega o público; o handler tem `conv` e `contact` em mãos, não lê `bot_states` | `webhook._handle_reopen_button` |
| Turno interativo | `_run_immediate_bot_turn`: claim com espera; `busy`/`no_budget` **rodam o turno mesmo assim**; não devolve o `reply` | `webhook.py` |
| Reset por inbound | zera `reopen_attempts`/`reopen_resolved_at` **antes** do curto-circuito do botão, **sem** `was_dup`, guardado por `attempts > 0 or resolved_at`; não limpa `reopen_opt_out` | `webhook.py` |
| `was_dup` | calculado só para `text`, `audio` e `button` (1 leitura por inbound) | `webhook.py` |
| Bot só por texto | gate exige `text`; mídia não gera turno nem aviso LGPD | `webhook.py` |
| Aceite LGPD | contato: `lgpd_consent=True`, `lgpd_consent_at`, `lgpd_policy_version`; recusa só em `bot_states`. Gate só re-pergunta quando `bot_states.lgpd_consent` está ausente. **Varizemed tem `settings.ai.lgpd_policy_version = varizemed-2026-07` configurado** (não vazio); `settings.ai` mora em `tenants/{tid}` e hoje só o painel do super-admin / `tenant_service.update_tenant` escreve nele | `bot_service`, `lgpd_bot.py`, `tenant_service` |
| Termos de aceite LGPD | "continuar"/"retomar" **não** estão em `_ACEITE_TERMOS` | `lgpd_bot.py` |
| `system_settings` | defaults aplicados no READ; `save_system_settings` só persiste chaves presentes em `_DEFAULT_SYSTEM_SETTINGS` | `database_firestore.py` |
| Builtin (Hubloc) | aceite LGPD → `_finalize_bot` no mesmo turno; não existe fase de bot pós-consentimento | `bot_service._finalize_bot` |
| Envio | canal = `contact.channel_id`; só standard ativo; template por canal | `main._plan_reopen_batch` |
| Worker | BackgroundTasks; pacing 1,5s; breakers; carimba antes do save; save sem promoção/recência/reabertura/atenção humana (sobe `last_outbound_at`) | `main._run_reopen_batch` |
| Trava de lote | por tenant, query + stale 2h; GET "interrompido" após 5 min sem persistir | `main.py` |
| Templates e limites (Meta, 23/09) | Varizemed `varizemed_retomada_generica_utility_v1` ([Continuar]/[Encerrar atendimento]); Hubloc `atualizao_de_solicitao`. Portfólio `TIER_2K`; Hubloc canal 4 `LIMITED` | leitura Graph |
| Estado após o script de 23/09 | 368 contatos da Varizemed com `reopen_attempts=1`, `last_reopen_template_at`, `last_reopen_audience="bot"`, `last_reopen_conversation_id/channel_id`, `reopen_bot_sent_at` (lista ISO); 71 com `reopen_opt_out`; lotes 2–6 em `reopen_batches` com `audience`/`origem` | Firestore |

---

## 2. Modelo de públicos

Um único scan por prévia lê os contatos com `qualification in (em_atendimento, novo)` e os reparte em dois baldes. O
seletor da tela só escolhe qual balde é disparado. Os baldes são disjuntos dentro de um lote e estáveis entre lotes por causa
do marco de ciclo (2.2.4).

### 2.1 Regras comuns (os dois públicos)

- Tenant e permissão `reabrir_em_lote`; lote habilitado no tenant (`reopen_batch_enabled`, seção 7).
- **Consentimento (D1):** `lgpd_consent == True` no contato e `lgpd_revoked` falso → senão `consentimento_ausente`. Prova obtida fora do
  bot não é reconhecida nesta entrega. **P2b:** `lgpd_consent_at` anterior a `lgpd_policy_date` → `politica_desatualizada` (3.4).
- Excluídos: arquivado, backup, `reopen_opt_out` ativo, desfecho terminal (qualificação fora de `novo`/`em_atendimento`).
- Frio: `last_inbound_at` do **contato** ≥ 24h (desconhecido = não envia). Cooldown de 24h por `last_reopen_template_at`.
- **Teto por contato (D8 + P1):** `reopen_batch_sent_at` = lista de `{at, audience}`; no máximo `REOPEN_MAX_PER_CONTACT` (2) entradas
  em `REOPEN_WINDOW_DAYS` (90). Inbound **não** zera. Motivo `teto_contato`. Compatibilidade: `reopen_bot_sent_at` (lista ISO do script
  de 23/09) é lida como `{at, audience: "bot"}`; nunca é escrita.
- Envio só por canal standard ativo com template compatível; coexistence fora. Um envio por contato por lote; o plano interno
  guarda `contact_id`, `conversation_id` e `channel_id`.

### 2.2 Fase de bot (define o balde)

Um contato está **em fase de bot** quando todas valem:

1. Bot disponível no tenant: `system_settings.bot_enabled` **e** motor `dialogflow_cx` com `status=active`. Em tenant sem CX, contato
   sem dono e com `bot_completed` falso **não** vai para a Recepção: sai com `aguardando_bot`.
2. Contato sem dono (`assigned_to` vazio) e `bot_completed` falso ou ausente.
3. `bot_states.human_active` falso (1 leitura, só para quem passou nos filtros baratos).
4. **Sem atendimento humano no ciclo atual.** Marco de ciclo = `bot_released_at` do contato (**datetime**, `utcnow()`, gravado no
   commit-point de `release_lead_to_bot` e de `return_contact_to_bot`, nunca zerado). Regra: nenhuma thread não-backup do contato tem
   `last_human_outbound_at` **posterior** a `bot_released_at`. **Se `bot_released_at` estiver ausente** (todo o estoque pré-deploy),
   o critério 4 é **ignorado** e decide o critério 2: sem dono e `bot_completed` falso = fase de bot. Isso torna o caso 6 verdadeiro
   para o legado; o marco passa a valer daqui para a frente. Todos os carimbos passam por `_coerce_timestamp` antes de comparar.
   O outbound do próprio lote e os do bot não entram na comparação.
5. **Sem desfecho com a Val no ciclo (P5):** `bot_outcome` ausente. `bot_outcome` (`agendado` | `link_enviado` | `duvida_respondida`
   | `sem_interesse`) e `bot_outcome_at` são gravados no contato quando o CX devolve o param `desfecho_bot` (dependência do agente,
   seção 8) e zerados em `release_lead_to_bot`/`return_contact_to_bot`. Heurística provisória enquanto o param não existe: última
   resposta da Val no ciclo contém `marcaconsultas` → `desfecho_bot`.

**Recepção** = passa nas regras comuns e **não** está em fase de bot: `em_atendimento` com ou sem dono, thread aberta ou fechada
em `legacy`, `novo` **com `bot_completed` verdadeiro** (pós-handoff sem atendimento, D5) e o lead atendido por supervisor na aba Bot
depois do marco (caso 10). **P4 (só aqui):** candidato `novo` com `bot_completed` verdadeiro só entra se `last_inbound_at` ≤
`REOPEN_MAX_IDLE_DAYS` (30); motivo `mais_antigo_que_limite`. Efeito esperado (9.1): Hubloc 542 → 54; Varizemed 6 → 6.

**Bot** = passa nas regras comuns e **está** em fase de bot: lead consentido no meio da conversa com a Val (`novo` ou `em_atendimento`)
e lead devolvido ao bot por fechamento automático, mesmo que atendido antes (D2, caso 6). **Sem teto de idade** (P4 não se aplica:
os 365 elegíveis de 23/09 continuam elegíveis). Não exige thread aberta.

**Thread candidata** (envio e fechamento D9): thread não-backup do contato em canal standard ativo com template compatível e maior
`last_message_at`; empate por menor `channel_id`. Os critérios 2.2.2–2.2.5 e a janela de 24h são avaliados no **contato** (todas as
threads não-backup), nunca só na candidata. Sem thread standard = `sem_thread_standard`.

### 2.3 Tetos e ordem

- **Por dia, por portfólio (D7):** `REOPEN_DAILY_CAP` (250). No execute o backend itera os tenants ativos (`set_tenant_context` /
  `reset_tenant_context` em `try/finally`) e soma, nos lotes com `started_at` nas últimas 24h, `max(enviados, planejados)` para
  `executando` e `enviados` para concluídos; recusa (409) se `soma + planejados > cap`. `planejados` é a **reserva**; o worker
  reavalia a cada 10 envios. Folga aceita: cap + ~20. Não conta reabertura pontual, recibos nem CLI.
- **Por lote:** `max_sends` como hoje (default 100, máximo 250).
- **Ordem, antes do corte `REOPEN_SCAN_MAX`:** `em_atendimento` antes de `novo`; dentro de cada grupo, `last_inbound_at` mais recente primeiro.

---

## 3. Respostas do cliente e encerramento

| Evento | Público Recepção | Público Bot |
|---|---|---|
| Continuar / Retomar | Como hoje: thread `aberto`, `mark_contact_bot_done` se preciso, visível na Recepção ou no Meus do dono. **Renovação de `handoff_at` só no caso 3:** se a thread não tem `last_human_outbound_at` posterior ao `handoff_at` atual (nunca atendida), carimbar `handoff_at = agora` para a válvula de 7 dias não devolver ao bot logo após o clique. Thread já atendida **não** renova (renovar desarmaria o auto-close de 24h). | **Roteamento no clique (aproximação aceita, diferente do scan):** critérios 2.2.1–2.2.3 pelo contato + `bot_states` + `ai_cfg` (`get_tenant`), critério 2.2.4 **só na thread do clique** (`conv` já está em mãos), critério 2.2.5 pelo contato; `last_reopen_audience` desempata. Custo: ~3 leituras. Em fase de bot: **não carimbar nada antes**; abrir a thread; chamar `_run_immediate_bot_turn` com utterance = rótulo do botão e `session_params_extra={"origem": "retomada_lote"}` propagado até `detect_intent` (+ params de horário), e `origem: null` no turno seguinte do contato (session params persistem na sessão CX); a função passa a **devolver o `reply`**. **Rede de segurança, pelo valor de retorno:** `reply` falsy ou exceção → `mark_contact_bot_done` + equipe + log com motivo (causas reais: bot desligado, motor pausado, `human_active`, contato saiu da fase de bot entre envio e clique, `settings.ai` incompleto, exceção). `busy`/sem orçamento **não** são falhas: o código roda o turno mesmo assim. Texto sintético não é gravado como mensagem do cliente. |
| Encerrar | Como hoje: `fechado_cliente`, `reopen_opt_out`, recibo, devolução ao bot em `reception`. | Igual. |
| Nova mensagem do cliente | Zera tentativas e `reopen_resolved_at` (como hoje) **e limpa `reopen_opt_out` (D4)** num bloco **separado**: condicionado a `reopen_opt_out` verdadeiro, protegido por `not was_dup`, posicionado **depois** do curto-circuito do botão. | Igual; a Val responde. |
| Mídia | Roteamento normal para a equipe. | **D10, tipo a tipo:** `image`, `document`, `video`, `gif`, `sticker`, `location` → item sintético `[cliente enviou {tipo}]` (legenda, se houver, vem depois do marcador) + param `midia_tipo` (`image`, `document`, `video`, `gif`, `sticker`, `location`, `audio`), `null` no turno seguinte; `audio` sem transcrição → `[cliente enviou áudio]`; `contacts`, `reaction`, `unsupported` → nada. Entra pelo **mesmo `_buffered_bot_turn`** do texto (vira item da rajada: foto + legenda + texto = 1 resposta), então LGPD pendente sai primeiro. **`was_dup` estendido de forma condicional:** só quando `bot_media_turn_enabled` está ligada no tenant e o tipo está na lista (custo zero nos demais tenants); turno condicionado a `not was_dup`. Flag própria e canário separado: muda comportamento fora do lote. |
| Clique duplo no Continuar | Dois toques = dois `wamid`; `was_dup` não cobre. | Idempotência por conversa: sem novo turno se `reopen_response_at` da thread tem menos de 60s. |
| Sem resposta após o template | Como hoje: no lote seguinte, fecha threads abertas (release em `reception`), protocolo, `reopen_resolved_at`. | **D9:** `reopen_resolved_at` + `attendance_status=fechado_inatividade` gravados direto na thread da tentativa, sem `set_attendance_status`, sem mensagem de sistema, sem protocolo. |
| Outbound humano após o template | Grava `reopen_human_active_at`; o scan **não** manda para auto-resolve quem tem esse carimbo posterior ao template. **Não** zera `reopen_attempts`. | Igual. |

### 3.4 P2b — Versão da política LGPD como data (fechada em 30/09)

Decisão base (P2): a versão passa a ser a **data da política**, editável pelo admin da empresa. A verificação final mostrou três
buracos na forma como estava escrito, e a proposta corrigida é:

1. **Semântica por data do aceite, não por igualdade de texto.** Re-perguntar quando `lgpd_consent_at < data_da_politica`
   (o aceite é anterior à política vigente). Isso resolve o *grandfathering* sozinho: a Varizemed tem hoje `varizemed-2026-07`; ao
   escrever a data real dessa política (ex.: `2026-07-01`), quem aceitou depois continua válido e só quem aceitou antes é reperguntado.
   Comparar texto (`lgpd_policy_version != vigente`) reperguntaria a **base inteira** na primeira edição.
2. **O lote exclui quem está desatualizado** (motivo `politica_desatualizada`), em vez de mandar template pago para quem vai receber o
   aviso LGPD como resposta. Sem isso, o Continuar do público Bot cai no gate LGPD antes do CX: "continuar" não é termo de aceite, o
   paciente recebe o aviso em vez da Val e o parâmetro `origem=retomada_lote` é queimado.
3. **Onde a tela grava (decidido 30/09):** os campos de conteúdo LGPD saem do `settings.ai` (que fica só com a ligação ao agente:
   motor, projeto, agente, status, setor do handoff, sinais, buffer — território da Castro, gravado por `scripts/set_tenant_ai.py`) e
   passam a morar em `system_settings/chat`: `lgpd_policy_date`, `lgpd_privacy_url`, `lgpd_notice`. Editados pelo admin da clínica na
   aba Sistema (mesmo padrão de `pool_mode`), com `log_audit` na troca. Motivo: a clínica é a controladora dos dados e dona da
   política; o doc do tenant vive numa coleção global que só o super-admin e os scripts escrevem, e essa fronteira fica intacta.
   Leitura com fallback: campo vazio em `system_settings` → valor atual do `settings.ai` → nada muda no dia do deploy.
   **Alcance na Hubloc (decidido 30/09):** o bot builtin usa aviso, link e versão **fixos no código** (`lgpd_bot._AVISO_LGPD`,
   `bot_service.LGPD_POLICY_VERSION = "hubloc-2026-06"`). O builtin também passa a ler os três campos, com o texto atual como
   default; o PO edita com a conta admin da Hubloc depois da implementação.

O gate passa a comparar também quando o estado já é `True`. Escopo: só quem fala com o bot é reperguntado; atendimento humano não
tem gate. Continua sendo **frente própria, antes desta** (9.0 item 1).

**Regra operacional (guia do admin):** a data a escrever é a da **publicação da política vigente**, nunca a data de hoje. Escrever
hoje faz todo aceite anterior ficar "antes" e repergunta a base inteira. Na primeira configuração, usar a data da política que já está
no ar (Varizemed: a de `varizemed-2026-07`; Hubloc: a de `hubloc-2026-06`). Só trocar a data quando a política de fato mudar.
Contexto do PO (30/09): boa parte dos leads com aceite antigo já recebeu a retomada pelo script de 23/09, então a exclusão
`politica_desatualizada` tem impacto pequeno no primeiro lote.

### 3.5 Thread aberta em fase de bot

Um Continuar no público Bot deixa a thread `aberto`, sem dono e com `bot_completed` falso — o mesmo estado de qualquer conversa com
a Val hoje: o cron não fecha, o operador comum não vê, o Atendimento diário fica aberto. Não é efeito novo do lote; a "faxina da aba
Bot" (seção 11, fora desta entrega) cobre também esse caso.

---

## 4. Dados

Campos novos, todos só-backend (sem `normalization.ts`, sem `firestore.rules`):

| Coleção | Campo | Tipo | Uso |
|---|---|---|---|
| `wa_contacts` | `bot_released_at` | datetime | marco de ciclo (2.2.4); `release_lead_to_bot` e `return_contact_to_bot` |
| `wa_contacts` | `reopen_batch_sent_at` | lista de `{at: ISO, audience}` | teto por contato (D8 + P1); lê `reopen_bot_sent_at` legado |
| `wa_contacts` | `reopen_human_active_at` | datetime | suprime auto-resolve após outbound humano |
| `wa_contacts` | `last_reopen_at`, `last_reopen_audience`, `last_reopen_conversation_id`, `last_reopen_channel_id` | ISO / str | por tentativa; auditoria; D9; desempate no clique. Fallback de `last_reopen_at` = `last_reopen_template_at` |
| `wa_contacts` | `bot_outcome`, `bot_outcome_at` | str / datetime | desfecho com a Val (P5) |
| `reopen_batches` | `audience`, `criteria_version`, `planejados` (reserva), `cancel_requested` | | auditoria; teto diário; cancelamento |
| `system_settings` | `reopen_batch_enabled`, `reopen_bot_audience_enabled`, `bot_media_turn_enabled` | bool | entram em `_DEFAULT_SYSTEM_SETTINGS` **e** na tupla de coerção de `save_system_settings`, senão o PUT é ignorado |

Semântica nova em campo existente: `reopen_opt_out` (limpo por inbound, D4). A reabertura **pontual** passa a gravar os mesmos
campos por tentativa.

**Custo da prévia.** Ordem: filtros baratos de contato (consentimento, arquivado/backup, opt-out, frio, cooldown, teto por contato,
qualificação/`bot_completed` para P4) → só os sobreviventes pagam 1 query de threads + 1 get de `bot_states` (este só em tenant CX).
Cache da prévia por tenant com TTL 90s reaproveitado na troca de seletor; 1 prévia em voo por tenant. `REOPEN_SCAN_MAX` (2.000)
aplicado **depois** da ordenação de 2.3, com `log` do excedente. Scan em `run_in_threadpool`. Sem índice novo.

---

## 5. API e interface

```json
POST /api/admin/reopen-batch/preview   -> {"audiences": {"reception": {...}, "bot": {...}}, "bot_disponivel": true, "bot_indisponivel_motivo": "", "daily_cap": {"cap": 250, "usados_24h": 37, "disponiveis": 213}}
POST /api/admin/reopen-batch           {"audience": "bot", "max_sends": 100}
GET  /api/admin/reopen-batch/{id}      -> inclui "audience"
POST /api/admin/reopen-batch/{id}/cancel
```

- `audience` aceita `reception` (default) ou `bot`; inválido = 422; `bot` indisponível ou flag desligada = 409 com motivo.
- A prévia devolve os dois baldes de uma vez, com contagens, `por_setor`, `pulados` por motivo e amostra com `conversation_id`/`channel_id`.
  Auto-resolve aparece **separado** dos envios (no primeiro lote Bot pós-deploy ele será a maioria: ~260 contatos de 23/09 com tentativa pendente).
- Modal (`ReopenBatchModal`): seletor "Público da reabertura" (Recepção padrão); Bot desabilitado com motivo; textos por público
  (abertura, "setor de destino", "Continuar abre para a equipe" vs "volta para a assistente virtual"); prévia fora de ordem ignorada;
  disparo só quando a prévia corresponde à seleção; público no progresso; Cancelar lote; linha do teto diário.
- Motivos novos em `REOPEN_SKIP_LABELS`: `consentimento_ausente`, `politica_desatualizada`, `fase_bot`, `atendimento_humano`,
  `aguardando_bot`, `sem_thread_standard`, `mais_antigo_que_limite`, `teto_contato`, `teto_diario`, `desfecho_bot`, `bot_indisponivel`, `estado_alterado`.

---

## 6. Execução e concorrência

- Re-scan no execute é a verdade. Antes de cada envio o worker relê contato e thread e pula (`estado_alterado`) se mudou de balde,
  ganhou dono, respondeu, entrou em opt-out ou estourou teto.
- Trava de lote por tenant com **um TTL só** (`REOPEN_LOCK_TTL_MIN`, 10) no POST e no GET; o GET **persiste** `interrompido`.
  Serialização entre tenants pela reserva do teto diário (2.3). Reserva transacional fora desta entrega.
- Cancelamento: `cancel_requested` lido a cada item.
- Falhas: erro permanente → `reopen_failures`, 2 falhas → `envio_falhou`; timeout/5xx/sem `messages[]` → cooldown sem tentativa +
  lista de reconciliação. Sem retry cego.
- Carimbo de sucesso (lote e pontual): `reopen_attempts +1`, `last_reopen_template_at`, `last_reopen_at`, `last_reopen_audience`,
  `last_reopen_conversation_id/channel_id`, `reopen_batch_sent_at += {at, audience}`. Antes do save da mensagem.
- **Auto-resolve:** filtrado pelo público selecionado; estilo segue a audiência da **tentativa** (`last_reopen_audience`). Fallbacks
  para tentativas antigas: sem `last_reopen_conversation_id` → `{channel_id}__{wa_id}`; sem `last_reopen_audience` → reclassificar
  pelo estado (2.2); sem `last_reopen_at` → `last_reopen_template_at`; ausência dos dois = sem supressão por `reopen_human_active_at`.
- Teto diário: checado no execute (409) e a cada 10 envios no worker.

---

## 7. Flags e configuração

| Onde | Chave | Default | Papel |
|---|---|---|---|
| `system_settings` (tenant) | `reopen_batch_enabled` | `true` | kill-switch do **lote inteiro** (prévia e disparo). **Pré-requisito de deploy (etapa 3):** `PUT reopen_batch_enabled=false` na Hubloc **antes** de promover a revisão; sem isso a Hubloc ganharia o público novo pelo canal 4 em LIMITED entre o deploy e a liberação (P3). |
| `system_settings` (tenant) | `reopen_bot_audience_enabled` | `false` | kill-switch do público Bot. **Desligada, a classificação não muda:** leads em fase de bot continuam fora da Recepção (`fase_bot` na prévia). Rollback do Bot = desligar. |
| `system_settings` (tenant) | `bot_media_turn_enabled` | `false` | turno do bot para mídia (D10) e `was_dup` condicional; canário próprio |
| `system_settings` (tenant) | `lgpd_policy_date`, `lgpd_privacy_url`, `lgpd_notice` | vazio → fallback `settings.ai` | P2b (frente própria): conteúdo LGPD editado pelo admin da clínica na aba Sistema |
| env | `REOPEN_DAILY_CAP` | `250` | teto por portfólio/dia (D7) |
| env | `REOPEN_MAX_PER_CONTACT` / `REOPEN_WINDOW_DAYS` | `2` / `90` | teto por contato, os dois públicos |
| env | `REOPEN_MAX_IDLE_DAYS` | `30` | idade máxima de `novo` pós-handoff na Recepção (P4) |
| env | `REOPEN_SCAN_MAX` | `2000` | candidatos avaliados por prévia |
| env | `REOPEN_LOCK_TTL_MIN` | `10` | TTL único da trava |

Nada muda em `REOPEN_TEMPLATE_NAME` (D12).

---

## 8. Dependências do agente CX (Izael)

Registradas em `docs/CX_AGENTE_PENDENCIAS_DEV_IA.md` (item 4):

1. Parâmetro de sessão `origem=retomada_lote` no turno do Continuar: cumprimentar quem voltou e perguntar no que pode ajudar.
   O CRM manda `origem: null` no turno seguinte.
2. Turno com texto `[cliente enviou imagem|documento|vídeo|gif|figurinha|localização|áudio]` (com ou sem legenda) e param
   `midia_tipo`, `null` no turno seguinte.
3. Parâmetro de sessão `desfecho_bot` (`link_enviado` | `agendado` | `duvida_respondida` | `sem_interesse`), escalar, no turno em que
   acontece — base do critério 2.2.5 (P5).

A flag do público Bot na UI só liga depois de 1 e 3 estarem no playbook publicado; até lá o script one-off é o caminho.
Pedido formal ao Izael, com contrato e roteiro de teste: `docs/CX_RETOMADA_LOTE_DEV_IA.md` (05/10).

---

## 9. Sequência de implementação

| Etapa | Trabalho | Conclusão |
|---|---|---|
| 1. Contagem prévia | Repetir a contagem com o critério 2.2 completo (threads + `bot_states` + P4 + P5 heurística) e medir leituras por prévia; produzir a conciliação da seção 11 | números e custo na mão do PO |
| 2. Marco de ciclo e campos | `bot_released_at` (datetime) em `release_lead_to_bot`/`return_contact_to_bot`; `bot_outcome` a partir de `desfecho_bot`; campos por tentativa (lote e pontual); `reopen_human_active_at`; leitura de `reopen_bot_sent_at` legado; chaves novas em `_DEFAULT_SYSTEM_SETTINGS` + coerção | `sim_reception_flow`: release → marco; template do lote não muda o balde; PUT das flags persiste |
| 3. Seleção | Scan único com dois baldes, regras 2.1–2.3 (thread candidata, `aguardando_bot`, P4 só na Recepção, P5), flags, teto diário com reserva, prévia com cache. **Antes de promover: `reopen_batch_enabled=false` na Hubloc** | cenários da seção 10 (partição) + conciliação |
| 4. Respostas | Continuar em fase de bot → `_run_immediate_bot_turn` devolvendo `reply` + `session_params_extra` + rede de segurança pelo retorno; reset de opt-out em bloco próprio; renovação condicional de `handoff_at`; `reopen_human_active_at`; mídia pelo `_buffered_bot_turn` com `was_dup` condicional; idempotência do clique duplo | `sim_cx_flow` + `sim_buffer_flow`: clique (Val responde / Val muda → equipe), clique duplo, reentrega de mídia, Encerrar → reentrega → mensagem nova → elegível |
| 5. Worker | Público no lote, revalidação, auto-resolve por audiência da tentativa com fallbacks (D9), teto por contato, falhas, TTL único, cancelamento | cenário 22 do sim para os dois públicos; contato carimbado pelo script de 23/09 |
| 6. UI | Seletor, textos por público, motivos, cancelar, teto diário, auto-resolve separado | `npm run build` + roteiro visual |
| 7. Liberação | Flags no `varizemed-test`, canário, depois Varizemed real (Bot só após playbook do Izael). Hubloc segue `false` | critérios da seção 11 |

Arquivos: `database_firestore.py`, `main.py`, `webhook.py`, `bot_service.py` (`session_params_extra`, `desfecho_bot`),
`bot_engine_dialogflow.py`, `config.py`, `frontend/src/App.tsx`. `bot_transport.py` e `normalization.ts` não mudam.

### 9.0 Pendências de planejamento fechadas em 24/09

1. **P2b é frente própria, antes desta** (3.4, fechada 30/09): campos LGPD em `system_settings` editados na aba Sistema, gate por
   data do aceite (CX e builtin), exclusão `politica_desatualizada` no lote, regra operacional da data no guia do admin.
2. **Dados do script de 23/09:** lidos nos formatos antigos; sem migração. Os ~260 que não responderam ficam com tentativa pendente
   até a flag do Bot ligar; o primeiro lote Bot pós-deploy será majoritariamente auto-resolve silencioso (D9), e o modal mostra isso separado.
3. **Ordem com o Izael:** D3, D10 e P5 atrás de flags desligadas; Bot na UI só depois do playbook. Até lá, script one-off com
   Continuar → Recepção, cadência semanal.
4. **Guia do operador** (`docs/product/GUIA_OPERADORES_QUALIFICACAO_FECHAMENTO.md`, seção 5): atualizar na liberação.
5. **Desfecho do bot não existe no CRM (P5).** Dos 71 Encerrar de 23/09, 46 tinham conversa de agendamento com a Val e 10 o link
   `marcaconsultas.com.br`; o PO confirma que muitos já consultaram. Template próprio para o Bot segue como decisão futura (D12).
6. **Script one-off (feito em 05/10):** telefone mascarado no `conversation_id` do CSV e wamid fora do relatório; grava `reopen_batch_sent_at`
   além do legado; pula quem recebeu o link `marcaconsultas` da Val (`desfecho_bot_link`). Dry-run de 05/10: 54 elegíveis, 7 pulados pelo link.
7. **Estimativa:** etapas 2–6 ≈ 4 a 6 dias úteis com revisão adversarial por etapa; etapa 7 depende da Varizemed e do Izael.

### 9.1 Resultado da Etapa 1 (contagem só-de-leitura em prod, 23/09)

Contato-level (sem threads nem `bot_states`; teto superior para o Bot):

| Métrica | Hubloc | Varizemed | varizemed-test |
|---|---|---|---|
| Lote **atual** (`em_atendimento` frio, sem opt-out) | 1.466 | 48 | 0 |
| … coexistence (já excluídos hoje por canal) | 1.221 | 0 | 0 |
| … standard sem `lgpd_consent` (saem por D1) | 51 | 4 | 0 |
| **Recepção v2** (`em_atendimento` consentido + `novo` pós-handoff) | 194 + 542 (→ 54 com P4) | 38 + 6 | 0 |
| **Bot v2** (fase de bot, consentido) | 0 (builtin) | **411** (405 `novo`, 6 `em_atendimento`) | 1 |
| Fase de bot **sem** consentimento (fora, D1) | 0 | 351 | 0 |
| `novo` pós-handoff por idade | ≤30d: 54 · 31–90d: 419 · >90d: 69 | 8–30d: 6 | — |

Dry-run do script (23/09, com threads e `bot_states`, critério 2.2.4 na forma antiga): 365 elegíveis no Bot da Varizemed (≤7d 50,
8–30d 167, 31–90d 148). O script enviou 368 templates em 23/09 (lotes 2–6). Leitura de 24h: 229 lidos, 73 entregues, 53 sem entrega,
108 respostas (19 Continuar, 71 Encerrar, 16 texto, 1 áudio, 1 reação); número GREEN.

---

## 10. Cenários de aceitação

| # | Caso | Esperado |
|---|---|---|
| 1 | Escreveu, recebeu aviso LGPD, não respondeu | Fora (`consentimento_ausente`). |
| 2 | Aceitou, Val respondeu, sumiu > 24h | **Bot**. Continuar → turno CX, Val responde; se o turno não devolver resposta → equipe. Encerrar → fecha + opt-out. |
| 3 | Handoff, ninguém respondeu, thread aberta | **Recepção** (`novo`, `bot_completed` verdadeiro, ≤ 30d). Retomar → thread aberta, não-lido, `handoff_at` renovado (thread nunca atendida). |
| 4 | Handoff, conversaram, > 24h, thread aberta | **Recepção**. Retomar **não** renova `handoff_at`. |
| 5 | Operador fechou manualmente | Desfecho terminal → fora. |
| 6 | Fechamento automático → devolvido ao bot | **Bot** (D2), inclusive quando atendido antes. Com `bot_released_at`: `last_human_outbound_at` < marco. Sem marco (legado): critério 2 decide. |
| 7 | Recusou LGPD | Fora. |
| 8 | Responde ao template com texto | Roteamento normal. Zera tentativas. |
| 9 | Responde com mídia | Bot (flag ligada): item sintético na rajada do buffer, Val responde, reentrega não repete. Recepção: equipe. |
| 10 | Supervisor respondeu na aba Bot sem handoff | `last_human_outbound_at` > marco → **Recepção**. No clique, avaliado na thread do clique. |
| 11 | Devolvido pelo menu | CX: caso 6. Builtin: `aguardando_bot`. "Devolver à recepção" → caso 3/4. |
| 12 | Lead com dono, frio | Recepção; Retomar abre no Meus do dono. |
| 13 | Clicou Encerrar, escreveu de novo | Opt-out limpo pela mensagem nova, não pelo clique nem pela reentrega. |
| 14 | Ignorou o template da Recepção | Auto-resolve como hoje. |
| 15 | Recebeu 2 retomadas em 90 dias (qualquer público) | 3ª bloqueada (`teto_contato`). |
| 16 | Envio falhou | Permanente: 2 falhas → `envio_falhou`. Timeout: cooldown, sem tentativa. |
| 17 | Responde entre prévia e envio | `estado_alterado`. |
| 18 | Contato com duas threads | Thread candidata standard; critérios no contato. |
| 19 | Hubloc | Bot indisponível; Recepção muda (D1, P4); **lote inteiro desligado** por `reopen_batch_enabled=false` gravado antes do deploy. |
| 20 | Fim de semana | Val responde com horário; Recepção cai na pool. |
| 21 | Desfecho terminal, frio | Fora. |
| 22a | Reentrega da Meta (mesmo `wamid`) | `was_dup`: turno/mídia não roda 2x; opt-out não é limpo. |
| 22b | Clique duplo | Segundo Continuar em < 60s não dispara novo turno. |
| 23 | Canal sem template compatível | `sem_template`. |
| 24 | Encerrar em lead pré-consentimento | Não ocorre (D1). |
| 25 | Continuar no Bot e a Val não responde (bot desligado, motor pausado, `human_active`, saiu da fase de bot, exceção) | `reply` falsy → `mark_contact_bot_done`, equipe, motivo registrado. |
| 26 | Template como Recepção, sem resposta, devolvido ao bot antes do lote seguinte | Auto-resolve pela audiência da tentativa (Recepção). |
| 27 | Lead legado sem `bot_released_at` | Critério 4 ignorado; critério 2 decide. |
| 28 | Tentativa pontual/pré-deploy no auto-resolve | Fallbacks da seção 6. |
| 29 | Lead com `bot_outcome` (agendou com a Val) | Fora do Bot (`desfecho_bot`). |
| 30 | Contato carimbado pelo script de 23/09, flag do Bot ligada | Sem 2º envio até esfriar de novo; se ignorou, auto-resolve silencioso. |
| 31 | Aceite anterior à data da política (P2b) | Fora do lote (`politica_desatualizada`); ao escrever, recebe o aviso novo. |

Cenários de sistema: teto diário com dois tenants no mesmo dia; troca rápida do seletor; lote cancelado; `pool_mode=legacy` ×
`reception`; flag do Bot desligada (`fase_bot`); PUT das flags persistido; `bot_released_at` datetime × `handoff_at` datetime.

Gates: `py_compile`, `sim_reception_flow`, `sim_cx_flow`, `sim_buffer_flow`, `sim_bot_flow`, `npm run build`. Relógio controlado.
A corrida entre instâncias na trava não é testável nos sims e fica registrada como janela aceita.

---

## 11. Liberação e rollback

1. **Critério de liberação por tenant, checado no script da etapa 1:**
   `Recepção_v2 = Recepção_v1 − (consentimento_ausente + politica_desatualizada + fase_bot + teto_contato + mais_antigo_que_limite +
   sem_thread_standard + aguardando_bot) + novo_pós_handoff_elegível`, com resíduo zero. Qualquer resíduo é bug de classificação.
2. **Dia do deploy da etapa 3:** `PUT reopen_batch_enabled=false` na Hubloc **antes** de promover a revisão.
3. `varizemed-test`: flags ligadas, canário com os números de teste: Continuar → Val e Continuar → equipe (Val muda); Encerrar →
   opt-out e limpeza por mensagem nova; mídia; teto por contato; auto-resolve silencioso.
4. Varizemed real: `reopen_bot_audience_enabled` só depois do playbook do Izael (itens 1 e 3 da seção 8); `bot_media_turn_enabled`
   só depois do canário. Primeiro lote Bot = faxina (auto-resolve dos ~260 de 23/09), avisado ao PO.
5. Hubloc: `reopen_batch_enabled=false` até o nome de exibição sair do `LIMITED`; depois decidir template e o backfill de qualificação.
6. Rollback: desligar as flags (sem deploy); revisão anterior para o resto. Campos novos são aditivos.

Fora desta entrega: outro número para enviar, campanhas agendadas, template novo, contagem por contato para o teto diário,
reserva transacional, faxina da aba Bot, backfill de qualificação da Hubloc, consentimento obtido fora do bot.

---

## Apêndice A — o que mudou desde a proposta de 22/09

Público Bot por **estado** com um marco de ciclo (`bot_released_at`) e sem instrumentação por mensagem; consentimento nos dois
públicos (D1); Continuar no Bot volta para a **Val** (D3) com rede de segurança pelo retorno; Encerrar não permanente (D4);
`novo` pós-handoff na Recepção com idade máxima (D5, P4); auto-resolve do Bot silencioso (D9); tetos diário (D7) e por contato
único (D8 + P1); desfecho da Val (P5); flags por tenant com pré-requisito de deploy para a Hubloc (D11 + P3); política LGPD como data
(P2, frente própria). Herdados das revisões: supressão de auto-resolve por outbound humano, TTL único, cancelamento, contador de
falhas, cooldown em timeout, scan em threadpool, cache da prévia, textos do modal por público, matriz de testes.

## Apêndice B — verificação final da v2.1 (24/09, 19 achados) e o que cada um mudou

| Achado | Onde entrou |
|---|---|
| P2 por igualdade de texto reperguntaria a base inteira e faria o Continuar cair no gate LGPD | 3.4 P2b (data do aceite; `politica_desatualizada`; onde grava) — ⚑ pendente |
| P4 nas regras comuns cortava 41% do público Bot (`novo` mid-bot) | P4 só na Recepção, predicado `novo` + `bot_completed` verdadeiro; Bot sem teto de idade |
| P1 sobreposto ao teto antigo (dois campos, dois envs, dois motivos) | um único `reopen_batch_sent_at`, `REOPEN_MAX_PER_CONTACT`/`REOPEN_WINDOW_DAYS`, `teto_contato` |
| Rede de segurança disparava em `busy`/sem orçamento e ignorava `reply` None | gatilho pelo valor de retorno; sem carimbo antes do turno; caso 25 |
| `reopen_batch_enabled` default `true` deixava a Hubloc exposta entre deploy e liberação; chaves fora de `_DEFAULT_SYSTEM_SETTINGS` | pré-requisito de deploy na etapa 3; chaves nos defaults e na coerção |
| Classificação no clique exigia leituras que o webhook não faz | roteamento no clique como aproximação declarada (2.2.4 só na thread do clique) |
| `bot_released_at` ausente jogava o legado na Recepção; tipo ISO × datetime | ausência ignora o critério 4; campo datetime; `_coerce_timestamp` |
| Renovar `handoff_at` no Retomar desarmava o auto-close de threads atendidas | renovação só em thread nunca atendida (caso 3) |
| 368 contatos de 23/09 presos com tentativa pendente; primeiro lote Bot = só auto-resolve | documentado (9.0 item 2, 11.4); auto-resolve separado no modal |
| Critério de liberação reprovava por construção após P1/P4 | identidade de conciliação (11.1) |
| Mídia sem caminho definido; `was_dup` global custando em todos os tenants | pelo `_buffered_bot_turn`; `was_dup` condicional à flag |
| `reopen_human_active_at` sem âncora nas tentativas antigas | fallback `last_reopen_template_at`; ausência = sem supressão |

Referências: [ADR 0009](decisions/0009-modelos-crm-d1-d3-retorno-ao-bot.md) (D2 emendado), [ADR 0010](decisions/0010-pool-mode-recepcao.md),
[ADR 0013](decisions/0013-publicos-reabertura-lote.md), [buffer do bot](BUFFER_MENSAGENS_BOT.md), [pendências do agente](CX_AGENTE_PENDENCIAS_DEV_IA.md).
