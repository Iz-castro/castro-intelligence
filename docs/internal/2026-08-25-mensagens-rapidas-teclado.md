# 2026-08-25 — Mensagens rápidas: import das globais da Varizemed + navegação por teclado

Pedido do PO: (1) importar na lista **global** da Varizemed as mensagens rápidas do CRM anterior
da clínica (`docs/temp.json`); (2) com a lista de sugestões aberta no compositor, percorrer os
itens com as setas, Enter e Tab completam. Decisão do PO na hora: **Enter no item destacado
completa no campo (não envia)** — o operador revisa e dá Enter de novo pra mandar ao lead
(templates como `/ag`, `/remarcacao` têm "....." pra preencher).

## Onde as mensagens rápidas vivem (verificado no código)

- **Global do tenant:** `castro_crm_tenants/{tid}/system_settings/chat.quick_messages_global`
  (`[{shortcut, message}]`). Mesmo doc de `pool_mode`, `bot_enabled`, alarme.
  `quick_message_max` (default 20) é o teto **da lista pessoal**, aplicado só no frontend.
- **Por operador:** `castro_crm_tenants/{tid}/user_settings/{user_id numérico}.quick_messages`.
- API: `GET/PUT /api/settings/system` (PUT exige RBAC `gerenciar_config_sistema`, audita
  `SYSTEM_SETTINGS_UPDATE`) e `GET/PUT /api/settings/user` (só o próprio). Rules: `system_settings`
  read se `ownsTenant`, `user_settings` read/write false — tudo passa pela API.
- Compositor: draft começando com `/` faz prefix-match (case-insensitive) em
  `[...global, ...pessoal]`; ordem do array = ordem da sugestão; sem dedup entre escopos.
- Os `quick_reply` de `webhook.py`/`types.ts` são botões de template da Meta — outra coisa.

## Import (prod, tenant `varizemed`)

- Script novo e reutilizável: `scripts/import_quick_messages_global.py` — dry-run por padrão,
  `--apply`, **append idempotente** (atalho já existente é pulado, comparação case-insensitive),
  grava undo em `scripts/_backfill_undo_quick_messages_<tenant>_<ts>.json` (gitignored),
  `--undo <arquivo> --apply` restaura. Usa `save_system_settings` (mesmo caminho da API,
  `merge=True`) — nenhum outro campo do doc é tocado. Exige `FIRESTORE_PROJECT_ID` explícito
  (`gcloud config` aponta pro projeto velho de SP).
- `docs/temp.json` (export do CRM antigo, formato `shortcut/title/text`) veio **truncado**: o
  último objeto era só `{ "id` — **a 29ª mensagem se perdeu na cópia** (PO reenviar se existia).
  Ajustes no import: uma entrada tinha `shortcut: ""` e o atalho `/agendamentohemorroida` no
  `title` → recuperado; `**Valores do Tratamento:**` (markdown) → `*...*` (negrito WhatsApp) no
  `/ch`; `title` descartado (nosso modelo só tem shortcut+message).
- Resultado: **29 globais** = 28 novas + `/ola` → "ola global" (teste que já existia; apagar pela
  UI de admin é decisão do PO). hubloc e varizemed-test seguem com 0 globais. Acentos conferidos
  (`\xe1`, `\xe7`) — o `�` no console era só codepage do Git Bash.
- Sem deploy pra isso; as configurações carregam **no login** → quem já estava logado precisa de F5.
- Simulação do match: `/t` → `/t` (Tanusa) primeiro, depois `/te`, `/th`; `/$` → 3 preços.
  Undo deste apply: `scripts/_backfill_undo_quick_messages_varizemed_20260825_104439.json`.

## Navegação por teclado (frontend)

- `frontend/src/context/CrmContext.tsx`: estado `quickSelectedIndex` (-1 = nenhum), helper
  `closeQuickSuggestions()`; em `handleDraftKeyDown`, com a lista aberta: **↑** destaca o item
  mais próximo da caixa (a lista fica ACIMA, então o último) e cada ↑ sobe um (clamp no topo);
  **↓** desce e, passando do último, volta pra caixa; **Esc** fecha; **Tab** completa no campo
  (sem seleção, a primeira); **Enter com item destacado** completa no campo. Enter **sem** seleção
  continua enviando o draft literal (comportamento antigo, ex.: "/t" vai pro lead).
  `applyQuickMessage` (clique/Tab/Enter) agora põe o cursor no fim do texto.
- `frontend/src/App.tsx`: classe `.is-selected` + `aria-selected`, `role="listbox"/"option"`,
  `scrollIntoView({ block: "nearest" })` no item destacado (lista tem `max-height: 180px`),
  dica dos atalhos no `title` da textarea.
- `frontend/src/styles.css`: `.quick-suggestion-item.is-selected` (fundo mais forte + contorno).
- Gate: `npm run build` (tsc estrito + vite) OK.

## Deploy

- `gcloud run deploy castro-crm --source C:\Rafael\castro-intelligence --region us-west1
  --project project-4a851bf9-f475-418c-800 --quiet` → revisão criada **`castro-crm-00090-gx8`**
  (o gcloud imprimiu `00089-mhh` "serving 100 percent" — errado de novo; identificada por
  `revisions list --sort-by "~metadata.creationTimestamp"`).
- Promovida por nome (`update-traffic --to-revisions castro-crm-00090-gx8=100`); `status.traffic`
  conferido: 100% na 00090-gx8, tag `staging` segue na 00074-zrt a 0%.
- Smoke: `GET /` 200; `GET /api/client-config` 200 com `projectId` Oregon; bundle servido
  `index-P8REM3MN.js` (mesmo hash do build local) contém `quick-suggestion-item is-selected`.
- **Rollback:** `update-traffic --to-revisions castro-crm-00089-mhh=100`.
- **Não commitado** (PO não pediu): working tree com `frontend/src/App.tsx`,
  `frontend/src/context/CrmContext.tsx`, `frontend/src/styles.css` modificados +
  `scripts/import_quick_messages_global.py` novo.

## Tarde — título por mensagem + trava contra mensagem vazia (rev `castro-crm-00091-btk`)

Pedido do PO: título em cada mensagem rápida (global e pessoal) pra identificar/editar na
configuração; e trava — a UI aceitava adicionar mensagem sem conteúdo (em prod o user 13 do
hubloc tinha 3 linhas totalmente vazias).

- **Modelo:** `QuickMessage = { shortcut, message, title? }` (`frontend/src/types.ts`). `title` é
  só identificação (configurações + lista do compositor); não vai pro cliente. Backend guarda a
  lista como vem — sem migração de schema.
- **Editor novo** `frontend/src/components/settings/QuickMessagesEditor.tsx`, usado nos dois
  lugares (modal "Minhas mensagens rapidas" e seção admin "Mensagens globais"): um card por
  mensagem com nº, título, atalho e a mensagem em `textarea` (as da clínica têm até ~490
  caracteres; o `input` de uma linha era inutilizável). Card incompleto ou com atalho repetido
  fica marcado (borda âmbar + aviso) e **desabilita o "+ Adicionar"** até corrigir/remover.
- **Trava em 3 camadas:** (1) editor acima; (2) `saveSystemSettingsAction`/`saveUserSettingsAction`
  (`CrmContext.tsx`) recusam salvar com `quickMessagesProblem()` (`frontend/src/utils/quickMessages.ts`:
  título+atalho+mensagem obrigatórios, atalho único) e mostram o erro; (3) **backend**
  `_clean_quick_messages` (`database_firestore.py`): atalho e mensagem obrigatórios, atalho único
  (case-insensitive, com/sem "/"), **`quick_message_max` agora vale no backend** pra lista pessoal,
  título opcional; `ValueError` → **400** nos `PUT /api/settings/system|user` (`main.py`).
  Testado direto: vazio total / mensagem vazia / atalho vazio / duplicado `/a` vs `A` / limite /
  formato → todos rejeitados.
- Lista de sugestões do compositor mostra o título entre o atalho e a prévia (`.qs-title`).
- **Backfill (prod, com undo):** varizemed — 28 globais ganharam os títulos do CRM antigo
  (recuperados do `temp.json` original; typos corrigidos: "Consulta Hemorroida", "Desconto Consulta
  Angiologia") via `scripts/import_quick_messages_global.py`, que agora **preenche `title` de
  atalho já existente sem título** (nunca sobrescreve mensagem; undo guarda o estado original —
  `_backfill_undo_quick_messages_varizemed_20260825_113404.json`). Pessoais — título = nome do
  atalho sem "/" (hubloc já usava o atalho como nome: `/1º PASSO`, `/PJ DOCS`…): hubloc 36
  tituladas em 5 usuários + **3 linhas vazias removidas (user 13)**, varizemed 1; undo no scratchpad
  da sessão (`undo_quick_titles_<tenant>_20260825_1134*.json`). Depois do backfill **toda lista
  (global e pessoal) passa na validação nova** — ninguém fica travado ao salvar.
- Gates: `py_compile` (main, database_firestore, script) + `npm run build` OK.
- Deploy: revisão **`castro-crm-00091-btk`** (gcloud imprimiu `00090-gx8` de novo); promovida por
  nome, tráfego 100% conferido; smoke `GET /` 200, `client-config` 200, bundle `index-D3YjpPXv.js`
  com `qm-card`. **Rollback:** `update-traffic --to-revisions castro-crm-00090-gx8=100` (dados com
  `title` são ignorados pelo frontend antigo — rollback seguro). Quem está logado precisa de F5.
- **Commitado a pedido do PO em 2026-08-27** (commit seguinte ao `4166548` na `develop`):
  `database_firestore.py`, `main.py`, `scripts/import_quick_messages_global.py`,
  `frontend/src/{types.ts,App.tsx,context/CrmContext.tsx,styles.css}` + novos
  `frontend/src/utils/quickMessages.ts`, `frontend/src/components/settings/QuickMessagesEditor.tsx`.
- **Próxima frente (PO, 2026-08-27):** finalizar o `rating_request` — ver diário/memória
  "Avaliação pós-conversão dormente" (template não existe na Meta; carimbo antes do envio;
  captura de dígito sem janela).

## Pendências / follow-ups

- Enter com a lista aberta e **nada** selecionado ainda envia o literal ("/t") — candidato a
  completar a primeira sugestão (como Tab) em vez de enviar.
- Sem dedup entre global e pessoal (atalho igual aparece duas vezes na sugestão) — a validação
  de atalho único é por lista.
- 29ª mensagem do CRM antigo (truncada no `temp.json`) — reimportar com o script se o PO reenviar.
- Global de teste `/ola` da varizemed: **apagada pelo PO** (2026-08-25).
- Operadores do hubloc com título automático (= atalho) podem renomear na UI quando quiserem.
