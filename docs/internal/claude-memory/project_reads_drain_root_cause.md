---
name: project_reads_drain_root_cause
description: Dreno de ~260k reads/dia do Firestore = /api/wa/contacts/all full-scan disparado pela SIDEBAR a cada page-load; listeners onSnapshot REFUTADOS como causa
metadata: 
  node_type: memory
  type: project
  originSessionId: 535f93e8-1725-4ae6-827a-2268b798f3c3
  modified: 2026-07-23T18:38:53.138Z
---

Investigação 2026-07-17/18 (workflow multi-agente, 31 agentes, verificação
adversarial com medição real em prod). Relatório completo em
[docs/INVESTIGACAO_READS_FIRESTORE_2026-07.md](docs/INVESTIGACAO_READS_FIRESTORE_2026-07.md).

**CAUSA RAIZ (~250-290k reads/dia, ~95% do dreno):** `GET /api/wa/contacts/all`.
A `ContactList` monta pra TODO usuário logado (App.tsx:2575) e o useEffect
(App.tsx:455-461) chama `loadAllContacts()` **no mount** — a sidebar só quer o
CONTADOR, mas o backend (main.py:1131) faz `fs_coll("wa_contacts").stream()` =
**full scan sem limit** (o `limit=10000` só trunca em Python depois de ler tudo).
Medido: `wa_contacts` do hubloc = **6.508 docs**; logs Cloud Run = 39-48 full scans
privilegiados/dia. 48 × 6.508 ≈ 260k = o dreno observado.
**RESULTADO FINAL (2026-07-23): 45k reads/dia util — ABAIXO do free tier (50k).**
Trajetoria: 260-455k -> 86k (Fix#1 contador) -> 45k (dieta do webhook rev 00081 +
fallback anti-transiente 00085). Ciclo da investigacao FECHADO. Picker v2 segue
como backlog so pra escala multi-tenant (agenda grande da Varizemed real).

**FIX EM PROD (2026-07-18, commit f8f2b03, rev castro-crm-00077-xer):**
`count_only=1` no endpoint (aggregate count; privilegiado = total − arquivados,
operador = `count_wa_contacts_scoped_for_user`) + `countAllContacts` memoizado
(useCallback [bundle]) + `contactsCountNonce` p/ atualizar ao criar contato.
Picker `+` intacto (carrega lista só sob demanda). Validado: 6.518→7 reads
(privilegiado), 2.665→~3 (aline). Meta pós-fix: ~15-30k reads/dia útil —
**MEDIR no Monitoring D+1** pra confirmar a queda.

**REFUTADO — não investigar de novo:** os listeners `onSnapshot` NÃO são o dreno
(~1-2k/dia). O frontend usa `persistentLocalCache` + IndexedDB desde o commit
`7397f42` (mar/2026), então re-anexar listener **resume pelo token** e cobra ~0 se
o gap for <30min. Por isso `Listen` aparece ~zero nas métricas e o custo todo está
em `BatchGetDocuments`/`RunQuery`/`Commit` (queries REST do backend).
Também refutados: `get_wa_unread_count` (código morto), `/api/wa/contacts` com
see_all (0 calls/48h), polling REST (inativo).

**Segundas fontes:** `/api/wa/conversations` privilegiado = 7.456 reads/call e
dispara em "Devolver ao bot"/"Reatribuição em lote" mesmo em snapshot mode
(App.tsx:1346/1362 sem gate); `/api/admin/conflicts` = 10.973/call por expansão do
card; webhook ~12 reads/msg de texto; cron expire-takeovers ~5,3k/dia (~2%, já
otimizado). Startup e refresh_channels/tenants: negligíveis.

**MEDIÇÃO 20/07 (segunda):** 86k reads/dia (era 260-455k). Composição via logs:
picos = rajadas de webhook/echo/state_sync, NÃO cliques de UI. Resposta em prod
no mesmo dia: **dieta do webhook** (commit da dieta, rev 00081-deb — contato
4→1 read/inbound via `contact=` opcional em save_wa_message/ensure_daily_attendance,
conversa 2→1 via `skip_conversation_upsert` em messages/echoes, state_sync sem
write vazio em `_update_existing_wa_contact`, gate `snapshotMode` no
refreshPollingViews) + **fallback anti-transiente** (commit 0abb84c, rev
00085-yeg — cache miss de canal → leitura direta `get_channel_by_phone_id_from_db`
só-ativo antes de enfileirar pending; mata os no_channel de cold-start, 9
recibos 18-19/07 drenados). **MEDIR 21/07: meta <50k/dia (free tier).**

**PICKER V2 (adiado pelo PO 2026-07-20 — backlog pré-Varizemed real):** desenho
completo em [docs/PICKER_V2_AGENDA_PAGINADA.md](docs/PICKER_V2_AGENDA_PAGINADA.md)
(commit 52654dd). Paginação por cursor (`sort_key` persistido) + busca no Enter
server-side (nome por PREFIXO via sort_key, telefone por SUFIXO via
`wa_id_reversed`) → ~50 reads/interação constante. Ordem: write-path → backfill
→ índices compostos (ESPERAR READY antes do código) → endpoint /picker →
modal. Gate: antes do go-live da Varizemed real (~15-20k pacientes). Trade-offs
de busca aprovados pelo PO (tel busca pelo final, nome pelo começo).

Workflow retomável: `resumeFromRunId: "wf_0d37b47a-d8f"`. Ver
[[project_firestore_cost_hotspots]] (auditoria anterior de 06/2026, cujas frentes
já deployadas seguem válidas).
