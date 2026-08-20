# ADR 0010 — Modo Recepção: pool compartilhada por tenant (`pool_mode`)

- **Status:** aceito (2026-08-04) — **EM PRODUÇÃO desde 2026-08-05** (rev
  `castro-crm-00074-zrt` promovida a 100% após canário completo no
  `varizemed-test`; ajustes #1-#4 abaixo). Hubloc segue `legacy` (default);
  varizemed real liga via UI quando as operadoras forem treinadas.
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
| `conversation/open` (picker) | ~~auto-atribui a thread~~ **emenda 2026-08-19: só auto-atribui se o LEAD já é do operador**; lead da pool fica órfão até o "Assumir" explícito (fecha o assume silencioso sem RBAC/409/audit — ver diário 2026-08-19) | não atribui |
| Auto-close por inatividade | pula órfãs | fecha órfãs com `bot_completed` (bot/backup ficam) |
| Fechar/reabrir manual de órfã (op. comum) | 403 | permitido (toggle RBAC da ação continua valendo) |
| Fechamento (manual OU cron) | re-gruda no `sale_owner` (ADR 0008) | lead volta pro **AGENTE DE IA** — `release_lead_to_bot` (Fase 2 do PLANO_MODELOS antecipada, PO 2026-08-05): `bot_completed=False` + sem dono; setor/qualificação/protocolo/temperatura/`sale_owner` preservados; prova LGPD intacta |
| Devolver à pool SEM encerrar | n/a | ação explícita do menu "Devolver à recepção" (`return_contact_to_pool` — dono do lead ou manager; `bot_completed` fica True) |
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
placeholder em vez de pular pra 1ª); (b) decisão do PO sobre o fim do
atendimento: fechamento (manual e cron) devolve o lead ao **agente de IA**
via `release_lead_to_bot` — Fase 2 do PLANO_MODELOS antecipada com gate por
`pool_mode` (a variante intermediária "fechar devolve à pool" foi vetada:
fechamento automático não muda posse pra outro humano); pra devolver aos
colegas SEM encerrar existe a ação de menu "Devolver à recepção". Fluxo
completo: handoff → Recepção → conversa/transfer → fechar → Val; reabrir =
picker + template (o gate de envio já silencia a Val via `mark_human_active`
e o próximo fechamento devolve de novo). `release_lead_to_bot` nasce com o
guard `lgpd_revoked` do J-3 (F1 só precisa gravar o campo).

**Ajuste do canário #3 (2026-08-05):** o retorno pós-fechamento re-perguntava
o aviso LGPD (o `bot_states` do ciclo anterior é apagado no fim do funil e o
`handle_lgpd` lê SÓ o state). Implementada a **hidratação da prova pelo
CONTATO** (Fase 2 do PLANO_MODELOS, item 9, desenho literal): antes do
`handle_lgpd`, se o state não tem veredito e o contato tem `lgpd_consent=True`
com `lgpd_policy_version` igual à vigente (`_cx_policy_version`), hidrata
`accepted` — sem re-chamar `_record_lgpd_consent`. Recusa no state tem
precedência; versão divergente re-pergunta (ADR 0009 D1); `lgpd_revoked`
nunca hidrata (J-3 D8). Cobertura: `sim_cx_flow` cenário q (7 asserts).

**Ajuste do canário #4 (2026-08-05, opção A do PO):** thread órfã aberta
pelo picker com contato fora do funil concluído (`bot_completed=False`,
ex.: pós-release ou contato manual novo) não casava com NENHUMA aba (Meus
exige dono; Recepção exige `bot_completed`) — só existia no pin da sessão
de quem abriu. Fix: o primeiro ENVIO do operador na órfã (mesmo ponto do
`mark_human_active`) carimba `bot_completed=True` (`mark_contact_bot_done`)
— o retorno aparece na **Recepção de todos**, sem dono ("quem reabre não
fica dono do retorno"); o fechamento (`release`) re-arma a Val. Alternativa
"auto-atribuir → Meus" foi rejeitada (retorno privado some da pool e
contradiz "picker nunca é assunção disfarçada").

**7º achado (canário varizemed-test, 2026-08-05):** o picker de contato
manual (`create_manual_wa_contact`, ramo "reabre/assume") era um TERCEIRO
bypass do gate: operadora "só recepção" abriu o número pelo "+ Nova
conversa" e virou Dona do Lead — lead com dono + thread órfã = invisível
pra pool inteira (o colega perde a janela: contato 403 no lazy-fetch). Fix:
parâmetro `auto_assume` — False quando reception OU perfil sem
`assumir_atendimento` (reabre/cria no pool; só desarquiva). Sintoma
diagnóstico pra reincidência: contato `em_atendimento` + `assigned_to`
preenchido sem transfer_log.

## Emenda 2026-08-09 — handoff sem atendimento humano NÃO volta pro bot

**Incidente (produção, varizemed).** Lead procurou a clínica no fim de semana,
a Val fez o handoff e a thread ficou na Recepção esperando o próximo dia útil.
O auto-close a fechou 20h depois (`ATTENDANCE_AUTOCLOSE_HOURS=20`) e o
`release_lead_to_bot` zerou `bot_completed` — e o filtro da aba Recepção
**exige** `bot_completed`, enquanto a aba Bot só é renderizada para
admin/supervisor (`canSeeAll`). Resultado: **o lead sumia de todas as abas da
operadora**. Se voltasse a escrever na segunda, a Val o atendia do zero
(`cx_snapshot` zerado), como se o handoff nunca tivesse existido; ainda por
cima o cliente recebia banner de fechamento e recibo de protocolo de um
atendimento que nunca aconteceu.

A linha do auto-close na tabela acima passa a valer **só quando o ciclo teve
atendimento humano**.

**Decisão.** O ciclo é detectado por COMPARAÇÃO de dois carimbos novos em
`wa_conversations`, sem reset em lugar nenhum:

| campo | quem grava |
|---|---|
| `handoff_at` | o handoff — `_persist_lead_temperature` (CX) e `_finalize_bot` (builtin; saiu de dentro do gate de `dept_id`, senão thread sem setor ficava sem marco) |
| `last_human_outbound_at` | `save_wa_message`, quando o outbound tem `sender_user_id` (bot, inbound, system message e nota interna ficam de fora) |

`_reception_handoff_unattended` compara: carimbo humano **mais recente** que o
handoff ⇒ ciclo atendido ⇒ fecha e devolve como antes. Caso contrário, **não
fecha** — a thread segue `aberto` na pool. Não fechar (em vez de "fechar sem
devolver") é deliberado: fechar dispararia banner e recibo de protocolo para
quem nunca foi atendido.

**Por que comparação e não flag zerada:** zerar `last_human_outbound_at` no
handoff exigiria acertar TODOS os pontos de fim de ciclo (`release_lead_to_bot`,
`return_contact_to_bot`, `bulk-reassign`, fechamento manual) — esquecer um seria
landmine silenciosa. Com dois timestamps, um handoff novo invalida sozinho o
carimbo do ciclo anterior: lead atendido → devolvido à Val → volta a conversar →
handoff novo fica protegido de novo, sem código de limpeza.

**Fail-safe:** qualquer dúvida degrada para o comportamento anterior (doc legado
sem `handoff_at`, timestamp corrompido, naive×aware). Teto
`RECEPTION_UNATTENDED_RELEASE_DAYS` (env, default 7): passada a espera, o lead é
dado como morto e volta pro bot — senão ficaria preso em `bot_completed=True`
para sempre, com a Val muda e ninguém sabendo que ele existe. O guard só é
alcançável no ramo da pool sem dono, então **legacy (Hubloc) segue intocado**.

**Descartado:** subir `ATTENDANCE_AUTOCLOSE_HOURS` para 72h (proposta inicial do
PO). O env é **global** — mexeria na Hubloc junto — e só adiaria o problema
(feriado emendado, recesso); o buraco não era o tamanho do timer, e sim devolver
ao bot uma thread que ninguém atendeu. Um `autoclose_hours` por tenant chegou a
ser desenhado e foi dispensado pelo PO depois desta correção.

**Produção:** rev `castro-crm-00075-dnt`, promovida por nome a 100% em
2026-08-09. Validado com dado real: os 8 leads engolidos em 08-09/08 foram
restaurados à Recepção (`bot_completed=True` + `handoff_at` + reabertura) e
**sobreviveram** à rodada do cron das 22:00Z, que rodou 200 e sem log de erro.
A metade positiva ("continua fechando o que deve", sobretudo o legacy da Hubloc)
ainda não foi observada em produção — só nos simuladores.

## Validação

`tools/sim_reception_flow.py` (**73 asserts** desde 2026-08-09; 61 na
promoção original), código real de main/rbac/db
com Firestore mockado): gate legacy×reception×coex×thread-de-outro×
lead-com-dono, RBAC do assume (403/409) e do transfer-para-si,
mark_human_active + carimbo `bot_completed` (opção A), revert no-op,
coerção do `pool_mode`, auto-close da pool, fechar manual de órfã, merge
de toggles no editor de perfis, contato manual sem assume,
`release_lead_to_bot` (devolução ao agente + guards) e
`return_contact_to_pool`. Cenários 5b/5c (emenda 2026-08-09): os 6 casos do
guard de handoff não atendido — inclusive carimbo humano do ciclo ANTERIOR não
liberando fechamento — teto configurável, e o que carimba (ou não) resposta
humana. CX: `tools/sim_cx_flow.py` **118** (cenário q = hidratação LGPD;
+1 provando que o handoff grava `handoff_at`). Regressão:
`tools/sim_bot_flow.py` **45** (+1 pelo mesmo motivo no builtin).
Canário executado no `varizemed-test` em 2026-08-04/05 (4 ajustes) antes
da promoção; regressão Hubloc validada na staging antes do go.
