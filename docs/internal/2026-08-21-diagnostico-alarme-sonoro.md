# 2026-08-21 — Diagnostico: alarme sonoro toca pro operador sem conversa (hubloc)

Relato do PO (Rafael): logado como operador `teste` (teste@hubloc.com.br, operador,
setor Comercial id=2), chegam "notificacoes de audio" mesmo sem nenhuma conversa com lead.

Investigacao read-only (codigo + prod). Nenhum dado alterado. Sem PII neste doc.

## 1. Onde o som nasce (codigo)

Dois efeitos em `frontend/src/context/CrmContext.tsx` ("Sound notifications"):

| Efeito | Linhas | Condicao | Som (sem arquivo custom) |
|---|---|---|---|
| Beep de nova mensagem | ~1645-1665 | `notification_sound_enabled` E soma de `contacts[].unread` AUMENTOU vs publish anterior | `playBeep` 880 Hz seno, 0.3 s, 1x |
| Alarme repetitivo | ~1667-1730 | `alarm_enabled` E `sessionUser.department_id` em `alarm_department_ids` E existe contato em `contacts` com `unread>0`, `assigned_to` vazio ou == meu id, `last_message_at` mais velho que `alarm_threshold_minutes` | `playBeep` 660 Hz quadrada com steps 880/660/880, 0.6 s, a cada 30 s |

- `playBeep` / unlock do AudioContext: `frontend/src/utils/audio.ts` (so toca apos o 1o gesto na pagina).
- Config: `system_settings/chat` do tenant (defaults em `database_firestore.py` `_DEFAULT_SYSTEM_SETTINGS`).
  `GET /api/settings/system` (qualquer usuario logado) / `PUT` exige `gerenciar_config_sistema`.
  UI admin: Administracao > Notificacoes (`App.tsx` ~2578-2620). Upload de som custom: `/api/admin/upload-alarm-sound`.
- NAO existe preferencia por usuario (mute/volume/snooze), nem gate de foco de janela/horario comercial.
- Settings sao lidas 1x no bootstrap (sem snapshot/polling); antes do fetch valem os defaults do
  frontend (`notification_sound_enabled: true`, `alarm_enabled: true`, `alarm_department_ids: []`).
- Historico: recurso criado em 2026-04-09 (commit 6f8a56e, `docs/internal/2026-04-09_notificacoes.md`).

## 2. Config real do hubloc em prod (2026-08-21)

`notification_sound_enabled=False` (beep OFF) · `alarm_enabled=True` · `alarm_threshold_minutes=1` ·
`alarm_department_ids=[2]` (Comercial) · sons custom vazios (sintetizados) · `updated_at=2026-07-29`.

=> O som que o `teste` ouve e o ALARME (3 tons, onda quadrada), nao o beep. Quem ouve: todo usuario
com `department_id=2` — `teste` (13), Danielle (4), Aline (5).

## 3. Por que toca sem conversa (2 causas encadeadas)

**Causa A — o alarme le `contacts` cru, a sidebar le `conversations` filtradas.**
`contacts` do operador comum = janela de `wa_contacts` (targets `assigned_to_uid==""`, `==null`,
`==meu uid`; `is_archived==0`; top-50 por `last_message_at`) SEM filtro de `bot_completed`,
departamento, canal ou qualificacao. A sidebar monta tudo a partir de `allConversations` + filtros:
"Novos" exige `bot_completed` quando `bot_enabled=True` (`CrmContext.tsx:697`), e a caixa "Bot"
so existe pra `canSeeAll` (`App.tsx:165`). Logo, contato do pool ainda "no bot" e INVISIVEL pro
operador comum, mas conta pro alarme.

Em prod: o pool sem dono do hubloc tem exatamente 3 contatos (ids 7996, 7765, 4457), todos com
`unread_count=1`, `bot_completed` ausente, `department_id=None`, canal 4 (standard), 1 inbound
(20, 35 e 72 dias atras) e nunca completaram o bot. Com limiar de 1 min, `hasOverdueUnread` e
PERMANENTEMENTE verdadeiro => alarme a cada 30 s pra todo o Comercial, sem nada na tela e sem
acao possivel pro operador (nao consegue abrir esses leads; so admin via caixa Bot).

**Causa B (raiz, mais ampla) — `wa_contacts.unread_count` e catraca de mao unica.**
Todo inbound (inclusive msg pro bot / antes do aceite LGPD) incrementa o contador do CONTATO
(`database_firestore.py` ~2459) e o da CONVERSATION. O unico caminho que zera o do contato e o
endpoint legado `POST /api/wa/contact/{id}/read` (~2638). Desde a Fase 2C (2026-05-04) o frontend,
com thread aberta, chama `POST /api/wa/conversation/{id}/read`, que zera SO a conversation (~1192).
Nenhum assume/close/release/cron/archive zera o contato. Resultado: o campo que alimenta beep e
alarme nunca volta a zero na pratica.

Medido em prod (hubloc, `is_archived==0`): **1.691 contatos com `unread_count>0`**
(885 da Danielle, 731 da Aline, 33 Roberta, 19 Helenice, 8 Jaqueline, 8 Elizabete, 4 pool, 3 internos);
idade: 837 >=30d, 537 <30d, 188 <7d, 105 <1d, 20 <1h. Amostra de 40: em 33 as conversations do
contato ja estao com `unread_count=0` (desync). Janela top-50 das operadoras do Comercial:
Danielle 47/50 e Aline 50/50 com contador preso >=1 min => o alarme provavelmente toca o dia
inteiro pra elas tambem (confirmar com as operadoras).

**Agravantes confirmados:** o efeito do alarme tem `contacts`, `sessionUser` e
`alarm_department_ids` nas deps e chama `checkAlarm()` antes de re-armar o `setInterval` — cada
publish do snapshot (qualquer lead novo/mensagem no pool), refresh de token (~1 h) ou
`applyConversationReadLocally` toca NA HORA e reinicia os 30 s (pode soar bem mais que 1x/30 s;
em modo polling, a cada ~15 s). Desligar "som de notificacao" NAO desliga o alarme (flags independentes).
O predicado de posse usa `assigned_to` (id numerico) enquanto a janela usa `assigned_to_uid`.

Drift observado (menor): thread `4__...` do contato 4457 esta atribuida ao teste (`assigned_to=13`)
enquanto o contato segue sem dono — nao e a causa do som.

## 4. Kill-switch sem deploy (admin, Administracao > Notificacoes)

- Desmarcar "Habilitar alarme" (`alarm_enabled=false`), ou
- esvaziar "Departamentos que recebem alarme" (lista vazia DESLIGA o alarme — nao liga pra todos).

## 5. Opcoes de correcao (decisao do PO — nada implementado)

1. **Frontend (corta o sintoma):** alarme/beep passarem a avaliar o mesmo conjunto que a sidebar
   mostra ao usuario (conversations das caixas Novos/Meus), ou ao menos ignorar `!bot_completed`
   quando `bot_enabled`, e usar `assigned_to_uid`; guard de dedupe no efeito (nao re-tocar por
   identidade de array / refresh de token); opcional: teto de idade ou snooze por contato.
2. **Backend (causa raiz):** `POST /api/wa/conversation/{id}/read` tambem zerar
   `wa_contacts.unread_count` quando nao sobrar unread em nenhuma thread do contato (ou recalcular
   o contador do contato como soma das threads). Sem isso qualquer alarme baseado no contato fica preso.
3. **Dado:** backfill one-shot: `wa_contacts.unread_count := soma(unread_count das conversations)`
   (1.691 docs no hubloc; conferir varizemed) + decidir destino dos 3 leads orfaos do pool
   (arquivar / enviar pro Comercial).
4. **Config:** limiar de 1 min e praticamente "sempre"; rever com o cliente (default do sistema e 5).

Scripts read-only usados (scratchpad da sessao): `read_notif_settings.py`, `read_pool_details.py`,
`quantify_unread_desync.py`, `top50_comercial.py`.

## 6. Execucao (mesmo dia, apos aprovacao do PO)

- **Fase 0 (dado):** os 3 leads orfaos (7996 lead que nao aceitou LGPD; 7765 midia nao suportada/
  campanha; 4457 autenticador do WhatsApp) foram APAGADOS a pedido do PO (contato + indice + thread +
  mensagens + message_index + attendances_daily + bot_states = 26 docs; backup JSON local no scratchpad
  da sessao, `purge_backup_hubloc_7996_7765_4457_*.json`). Alarme do `teste` cessa na hora.
- **Fase 1 (codigo, ADR 0011):**
  - `database_firestore.py`: `recompute_wa_contact_unread(contact_id, current=None)` (soma das threads;
    so grava se mudou; nao cria contato fantasma); `mark_wa_conversation_read_by_id(conversation_id,
    contact_id=None)` chama o recompute (nao-fatal, log sem PII); endpoint legado por contato tambem
    zera as threads (invariante nos dois sentidos).
  - `main.py` `POST /api/wa/conversation/{id}/read`: autorizacao (thread minha / pool / takeover meu /
    senao `_require_contact_access`) + rede de seguranca pro contador do contato quando a thread ja
    esta em 0.
  - `CrmContext.tsx`: beep/alarme sobre `novosConversations + meusConversations` restritos a camada AO
    VIVO; `settingsLoaded` (fetch de /api/settings/system separado do /user, re-armado em
    openSettingsPage/save; reset zera settings do usuario anterior); beep com baseline por thread
    (so mensagem NOVA bipa — hidratacao/rotacao de janela nao); alarme com deps primitivas + refs,
    toca ao entrar thread nova no conjunto atrasado e no tick de 30 s, dedupe de 5 s, ancora em
    `last_inbound_at` (fallback `last_message_at`).
  - `App.tsx`: textos da aba Notificacoes refletem o comportamento real.
  - Gates: py_compile OK; `sim_reception_flow.py` 97 asserts (4 novos do recompute), `sim_bot_flow.py`
    56, `sim_cx_flow.py` 172; `npm run build` OK. Revisao adversarial por workflow (12 agentes, Opus):
    8 achados verificados, 5 confirmados em severidade baixa e corrigidos (PII no log, IDOR no read,
    read/write redundantes, settingsLoaded fail-closed, beep por hidratacao); refutados: flap do
    alarme, "cura inalcancavel" (coberta pelo backfill), perda de beep da Equipe pro admin (decisao
    de produto), filtro de canal do Meus.
- **Fase 3 (codigo):** admin/supervisor ganham os targets da pool (`assigned_to_uid` ""/null, top-50,
  contatos + threads) e "minhas" alem da janela global; caixas Novos/Bot derivam da pool (com
  "Carregar mais" da pool); "Carregar mais" global so em Equipe; `mergeVisibleContacts` com cap
  50 x targets pro admin.
- **Fase 2 (backfill):** `scripts/backfill_contact_unread_from_threads.py` — dry-run hubloc:
  1.515 contatos a corrigir (1.195 -> 0; demais -> soma real das threads). APLICAR so apos o deploy.
- **Deploy:** revisao `castro-crm-00086-fwt` (criada 2026-08-21 18:48 UTC; o gcloud imprimiu
  "00085-vcr" — mentira conhecida) promovida por nome a 100%; smoke `GET /` 200 e
  `/api/client-config` 200 (projectId Oregon). Rollback = `--to-revisions castro-crm-00085-vcr=100`.
- **Backfill aplicado (pos-deploy):** hubloc 1.516 contatos (undo
  `scripts/_backfill_undo_unread_hubloc_20260821_190457.json`), varizemed 264, varizemed-test 4 —
  0 divergentes apos. Top-50 do Comercial depois: Danielle 31/50 e Aline 28/50 com nao-lido REAL de
  thread (ate ~7 h) — com limiar de 1 min o alarme delas continua ate abrirem as conversas (agora e o
  comportamento especificado; decisao de produto pendente: limiar maior, excluir atendimento fechado
  ou coex respondida pelo celular).
- **Revisao da Fase 3** (9 agentes Opus): 6 achados verificados, todos refutados/baixos. Follow-ups
  de UX (nao bloqueantes): caixa Bot do admin com "Carregar mais" que pode nao acrescentar linha
  (pool pagina por recencia, Bot e recorte); estado vazio renderizado junto com o botao; badges
  Bot/Novos do admin oscilam ao paginar (camada estatica); listener Backup sem limite (pre-existente).
- **Pendente:** teste manual do PO com o operador `teste` (sem som ao entrar / Configuracoes; som so com
  lead novo visivel) e commit (nao commitado por regra do repo).
- **Val (varizemed), mesmo dia:** environment trocado para `22390163-6bbc-47b5-a25a-e53eb3363d8f`
  (`core_version` val-5.0.3, rotulo do Izael) com 1 contato na janela de 60 min por decisao do PO;
  rollback na tabela do runbook `docs/deploy/TROCAR_ENVIRONMENT_VAL.md`.

## 7. Mesmo dia, pedidos seguintes do PO: filtro "Nao lidas", "So espiar", rotulos do botao

- **"Nao lidas"** (option `nao_lidos` no select de qualificacao — Bot/Novos/Meus/Equipe): filtra por
  `unread_count` da THREAD e, ao entrar no modo, busca no Firestore (getDocs) as threads com
  `unread_count > 0` do escopo da caixa (Meus = `assigned_to_uid == uid`; Novos/Bot = pool `""`/`null`;
  Equipe = tenant inteiro, so `canSeeAll`), fora da janela de recencia — mensagem de fim de semana que
  saiu do top-50 aparece sem "Carregar mais" as cegas. Pagina de 50 por escopo (limite crescente),
  resultado na camada estatica (`pagedConversations`), thread selecionada isenta do filtro e
  preservada ao sair/paginar, guardas contra resposta tardia (`unreadModeRef`/`unreadReqRef`),
  falha => `setError` + degrada pro filtro client-side.
- **Indices** (firestore.indexes.json + prod): `wa_conversations (assigned_to_uid ASC, unread_count DESC,
  last_message_at DESC)` e `(unread_count DESC, last_message_at DESC)` com **queryScope COLLECTION**.
  GOTCHA descoberto: os indices COLLECTION_GROUP existentes servem as queries de colecao
  "igualdade + 1 orderBy", mas essa forma (igualdade + desigualdade + 2 orderBy) so e servida por
  indice COLLECTION (o GROUP so atende `collectionGroup()`, que cruzaria tenants — proibido). Criei
  primeiro em GROUP (inutil), depois em COLLECTION (READY) e apaguei os GROUP.
- **"So espiar"** (checkbox ao lado do select, so role admin|supervisor): `peekMode` faz o efeito de
  marcar-lida dar early return (badge e alarme continuam). Lembrado em localStorage POR USUARIO
  (`castro_crm.peek_mode.<uid>`).
- **Botao de paginacao**: "Mostrar mais (N restantes)" (revelar carregado) / "Buscar conversas mais
  antigas" (getDocs) / "Buscar mais nao lidas" (modo Nao lidas; classe `.attention` piscando em
  vermelho, so com linhas visiveis; `prefers-reduced-motion` desliga a animacao).
- Revisao adversarial (9 agentes Opus): 6 confirmados em baixa/media, tratados: fechamento do chat ao
  sair/paginar (preserva selecionado), resposta tardia (guardas), erro em verde (setError), item some
  sob o cursor (isento), piscar com lista vazia (so com linhas), peek herdado em PC compartilhado (chave
  por uid), textos (aria-label "Filtrar conversas", aba Notificacoes cita o So espiar).
- **Limites conhecidos / follow-ups:** a ordenacao da busca e por `unread_count desc` (imposicao do
  Firestore pela desigualdade) — a pagina 1 traz "quem tem mais nao lidas", nao "quem espera ha mais
  tempo" (o cliente reordena por recencia o que veio); solucao definitiva = denormalizar `has_unread`
  booleano na thread e consultar por igualdade + recencia (+ backfill). Em Novos/Bot a busca traz a
  pool crua (threads em fase de bot que a caixa esconde podem deixar a lista vazia com "ha mais").
  Paginacao por limite crescente (re-le a pagina; padrao do repo). Badges do nav inflam enquanto o
  modo esta ativo (camada estatica conta). Hidratacao de contatos (GET /api/wa/contact/{id}, lotes de
  8) e sincrona no backend (`uvicorn --workers 1`) — hazard pre-existente do "Carregar mais".
- **Deploy:** revisao `castro-crm-00088-tc9` (criada 2026-08-21 20:42 UTC) promovida por nome a 100%
  (a 00087-jwv, intermediaria, nunca serviu trafego). Rollback = `--to-revisions castro-crm-00086-fwt=100`
  (ADR 0011 sem Nao lidas/So espiar) ou `castro-crm-00085-vcr=100` (antes de tudo).
