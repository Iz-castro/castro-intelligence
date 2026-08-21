# Investigação — dreno de reads do Firestore (julho/2026)

> **Status:** investigação ~85% concluída (workflow multi-agente interrompido por fim
> de sessão em 17/07 17:11; 31 de ~37 agentes concluídos, resultados em cache).
> **Causa raiz IDENTIFICADA e convergente.** Falta só aplicar os fixes.
>
> Retomar o workflow: `Workflow({scriptPath: <script salvo da sessão>, resumeFromRunId: "wf_0d37b47a-d8f"})`
> — os 31 agentes concluídos voltam do cache instantaneamente.

> **Status em 2026-08-21 — o que já foi aplicado:**
>
> - **Fix #1 (a causa raiz) FEITO** — commit `f8f2b03` (2026-07-18): a sidebar usa
>   `GET /api/wa/contacts/all?count_only=1` (aggregate `count()`) e a agenda completa
>   só carrega quando o picker `+` é aberto; `loadAllContacts` tem single-flight
>   (`allContactsInflightRef`) contra o loop de retry citado no item 4.
> - **Item 2 FEITO** — `refreshPollingViews` retorna cedo em `snapshotMode`
>   (`frontend/src/context/CrmContext.tsx`, "dieta de reads 2026-07-20").
> - **Item 3 PENDENTE** — `GET /api/admin/conflicts` ainda faz full-scan
>   (`fs_coll("wa_conversations").stream()` + `get_all_wa_contacts()` em `main.py`) e
>   o listener da caixa `backup` continua sem limite.
> - ⚠️ Os números abaixo são de julho: a sidebar mudou de novo em 2026-08-21
>   (ADR 0011 — `unread_count` derivado das threads, buscas `getDocs` além da janela
>   e 2 índices novos). Ver `docs/internal/2026-08-21-diagnostico-alarme-sonoro.md`
>   antes de reusar qualquer estimativa.
> - O `resumeFromRunId` acima é de uma sessão de 17/07 — não conte com o cache.

## O problema

Após os fixes do incidente de 16/07, os reads do Firestore continuavam altos:

| Dia | Reads |
|---|---|
| 10/07 | 6,3k |
| 11/07 | 12,8k |
| 12/07 (domingo) | **319k** |
| 13/07 | 202k |
| 14/07 | 132k |
| 15/07 | 305k |
| 16/07 | 456k |

Estranho porque o `Listen` (listeners `onSnapshot`) aparecia perto de **zero** no
mix de APIs — o custo estava em `BatchGetDocuments` (54,7k/48h), `Commit` (39,3k/48h)
e `RunQuery` (15,7k/48h), ou seja **queries REST do backend**, não listeners.

## Causa raiz — `GET /api/wa/contacts/all` (~250-290k reads/dia)

**Um único caminho explica quase todo o dreno.** Três verificadores independentes
convergiram, dois deles medindo os logs reais do Cloud Run:

- A `ContactList` é montada no layout principal para **todo usuário logado**
  ([App.tsx:2575](../frontend/src/App.tsx#L2575)) e o `useEffect`
  ([App.tsx:455-461](../frontend/src/App.tsx#L455-L461)) chama `loadAllContacts()`
  **no mount** — **não** ao abrir o picker `+`. A sidebar só quer o **contador**.
- O backend ([main.py:1131](../main.py#L1131)) faz
  `fs_coll("wa_contacts").stream()` — **full scan sem limit**. O `limit=10000` só
  trunca o array em Python **depois** de ler tudo.
- Volume medido em prod (aggregate `count()`, 17/07): **`wa_contacts` do hubloc =
  6.508 docs** (0 arquivados).
- Frequência medida (logs Cloud Run 13-17/07): **47-80 chamadas/dia**, das quais
  **19-48/dia são "pesadas"** (latência ≥1,5s = full scan privilegiado).

**Conta:** ~39-48 full scans/dia × 6.508 docs ≈ **254-286k reads/dia** — bate quase
exatamente com o dreno observado de ~260k/dia.

Agravante: as carteiras são **bimodais** — Danielle (3.401) e Aline (2.654)
concentram 93% da agenda; os outros 7 operadores têm ≤24 contatos cada. Então
admin paga 6.508, Danielle 3.401, Aline 2.654 por page-load.

### Fix (maior retorno de todos)
1. **A sidebar só precisa do contador** → trocar por `count()` aggregate:
   **7 reads em vez de 6.508** (Firestore cobra 1 read por 1000 docs no aggregate).
2. Carregar a agenda completa **só quando o picker `+` for realmente aberto**.
3. Cache em `sessionStorage` com TTL (hoje o cache em state zera a cada F5).
4. Memoizar `loadAllContacts` (`useCallback`) — não reduz o custo normal (o cache
   em state já segura re-renders), mas **contém o loop de retry em falha** (há
   comentário no código citando incidente real: *"visto em prod: 5 chamadas em
   0,1s -> 429"*).

**Impacto estimado: −250k reads/dia (~95% do dreno).**

## Demais fontes (ranked, todas verificadas)

| # | Fonte | Reads/dia | Nota |
|---|---|---|---|
| 1 | **`/api/wa/contacts/all`** (acima) | **~250-290k** | 🔴 a causa raiz |
| 2 | `/api/wa/conversations` (privilegiado) | ~14k **por clique** | 7.456/call (500 conv + 448 backup s/ limit + 6.508 join contacts). Dispara em "Devolver ao bot" e "Reatribuição em lote" **mesmo em snapshot mode** (App.tsx:1346/1362 sem gate) |
| 3 | `/api/admin/conflicts` | ~11k **por expansão** | 10.973/call (4.465 conv + 6.508 contacts). Card colapsado por default → piso 0 |
| 4 | Webhook por mensagem | ~9-16k | 12 reads exatos por msg de texto; echo coex ~8; bot turn +9 |
| 5 | Auth cache miss (TTL 45s) | ~3-8k | 4 reads + 3 Commits por miss |
| 6 | Refresh de token (~1h × abas) | ~3,6k | 13 abas × ~10 disparos × ~28 reads |
| 7 | Cron `expire-takeovers` (*/30) | ~5,3k (~2%) | Já otimizado em 06/2026. 48 runs × 111 reads |
| 8 | `refresh_channels` / `refresh_tenants` (TTL 60s) | ~1,5-6k | Piso constante em request-path |
| 9 | Startup/bootstrap por cold start | ~1,8k | Negligível (~0,7%) |
| 10 | `_process_statuses` (receipts) | ~1,1k | Medido: 556 statuses/dia × 2 reads |

## REFUTADO — não perder tempo aqui

- **Listeners `onSnapshot` NÃO são o dreno** (~1-2k/dia, não 15-18k). O frontend usa
  `persistentLocalCache` + `persistentMultipleTabManager` (IndexedDB) desde o commit
  `7397f42` (mar/2026). Re-anexar um listener **resume pelo token** e cobra ~0 reads
  se o gap for <30min. Isso explica o `Listen` perto de zero nas métricas e **valida
  a intuição original** de que "reads altos são estranhos pro onSnapshot".
- `get_wa_unread_count` — **código morto** (0 callers). Se reativado sob hubloc
  custaria 1.082 reads/call.
- `/api/wa/contacts` com `see_all` — **0 chamadas em 48h**. Custo latente existe
  (~6,5k/call) mas não contribui hoje.
- Polling REST fallback — **inativo** (`crm_transport_mode=polling` é vetor
  adormecido; se ligado, custaria 1,79M reads/h).
- Reescrever `_ch_fields` no upsert — Firestore cobra por doc-op, não por campo.

## Ordem de execução sugerida

1. **Fix #1 (`contacts/all` → `count()` + lazy picker)** — sozinho resolve ~95%.
2. Gate no `refreshPollingViews` para não disparar `/api/wa/conversations` quando o
   transporte é snapshot (item 2 da tabela).
3. `limit` no target `backup` do snapshot + filtro server-side em `/api/admin/conflicts`.
4. Higiene: `select()` não ajuda (cobra por doc retornado, não por campo).

## Método

Workflow multi-agente com verificação adversarial: 4 agentes de descoberta
(frontend, backend/endpoints, crons, hot paths) → ~27 verificadores independentes,
cada um obrigado a **medir em prod** (aggregate `count()`, Cloud Logging, Cloud
Monitoring REST) em vez de estimar. Resultado: 18 CONFIRMADO, 8 PARCIAL, 1 REFUTADO.
Vários achados tiveram a estimativa **corrigida** pelos verificadores (ex.: agenda
real = 6.508 e não ~5.000; carteiras bimodais e não uniformes).
