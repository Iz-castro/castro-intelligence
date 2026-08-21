# Auditoria — Listeners Firestore e custo de leituras/gravações

> **Data:** 2026-06-20 · **Escopo:** todos os `onSnapshot` + hotspots de read/write no Firestore
> **Método:** auditoria multi-agente (finders paralelos → verificação adversarial de cada achado → crítico de completude). 2 achados foram **refutados** na verificação (ver §5).
> **Links:** `file:line` relativos à raiz do repo.

> **Atualização 2026-08-21 — o que do §4 já está no código:** item **1 FEITO**
> (`close_stale_attendances` e `expire_stale_takeovers` filtram server-side com
> `.where(...)`, sem full-scan); item **2 FEITO** (`auth.py` tem cache in-memory por
> `(tenant, firebase_uid)` + cache de auth de 45 s, que limita indiretamente o `update_last_login`); item **4 parcial**
> (`increment_audit_metrics` usa `firestore.Increment` e zero reads, mas o *skip* de
> métricas em mensagens `system`/`internal` **não** existe); item **6 parcial** (os
> targets do operador em `wa_conversations` já têm `orderBy+limit(50)`; o target
> `backup` do admin **continua sem limite**). Fora da tabela: o full-scan de
> `/api/wa/contacts/all` que a sidebar disparava virou `count_only=1` (aggregate
> `count()`). Segue **ABERTO** o item **3** — `gc_messages` ainda lê as 100 últimas
> de *todas* as conversas, sem `where("conversation_id")` (custo + vazamento entre
> spaces + conversa vazia). Itens 5/7/8: ⚠ verificar caso a caso.

---

## Resumo executivo

O custo **não** está concentrado nos listeners — eles são poucos (5 pontos de `onSnapshot`). O grosso vem de **duas fontes**:

1. **Cron de auto-close que faz full-scan da coleção `wa_conversations` a cada 30 min, por tenant, 24/7** — sozinho pode gerar **~144.000 leituras/dia/tenant** mesmo sem ninguém logado.
2. **Cada mensagem do WhatsApp recebida custa ~8-9 gravações + ~8 leituras** (≈ **17 operações por mensagem inbound**), por causa de denormalização e métricas no caminho quente do `save_wa_message`.

Os listeners contribuem com amplificações reais mas secundárias (queries sem `limit`, leitura global filtrada no cliente).

---

## 1. Inventário de listeners (`onSnapshot`)

Existem **exatamente 5 pontos** de `onSnapshot` (confirmado por varredura — nenhum outro `.ts/.tsx` usa). Vários são **multi-target**: disparam 2-3 listeners simultâneos sobre a mesma coleção. Em runtime, **um operador comum mantém ~5-7 listeners abertos**; um admin, ~4 (+2 se abrir o chat interno).

| # | Listener | Arquivo | Query | `limit`? | Problema |
|---|----------|---------|-------|----------|----------|
| 1 | **contacts** | [CrmContext.tsx:1006](../../frontend/src/context/CrmContext.tsx#L1006) | admin: 1 target (`is_archived==0`, orderBy `last_message_at`, **limit 50**); operador: **3 targets** (blank/null/mine), 50 cada | ✅ 50/target | Operador lê até **150 docs e descarta ~100** no `slice(0,50)`. Dois targets só pra "sem dono" (`''` vs `null`) dobram a leitura do pool |
| 2 | **conversations** | [CrmContext.tsx:1043](../../frontend/src/context/CrmContext.tsx#L1043) | admin: `all` (orderBy, **limit 300**) **+ `backup` (`is_backup==true`) SEM limit**; operador: **3 targets SEM limit e SEM orderBy** | ❌ (exceto `all`) | **Caixa Backup lida inteira** a cada sessão admin (cresce ilimitado). Operador lê **100% das atribuídas + 100% do pool sem dono** |
| 3 | **messages** (conversa aberta) | [CrmContext.tsx:1078](../../frontend/src/context/CrmContext.tsx#L1078) | `conversation_id==X`, orderBy `timestamp_wa`, limit `messageLimit` (10→25→40) | ✅ | **Re-subscreve e relê a janela inteira a cada "carregar mais"** (deps têm `messageLimit`). Usa os **objetos** `config`/`sessionUser` nas deps → risco de re-subscribe a cada refresh de token (~1h) |
| 4 | **gc_conversations** | [InternalChatPanel.tsx:41](../../frontend/src/components/gchat/InternalChatPanel.tsx#L41) | orderBy `last_message_at`, limit 50 | ✅ 50 | Lê 50 globais **sem filtrar por participante**; duplica com um GET REST no mesmo `open` |
| 5 | **gc_messages** | [InternalChatPanel.tsx:65](../../frontend/src/components/gchat/InternalChatPanel.tsx#L65) | orderBy `created_at`, **limit 100, SEM `where`** | ⚠️ enganoso | **Lê as 100 msgs mais recentes de TODAS as conversas** e filtra `conversation_id` no cliente. Amplificação + possível vazamento entre spaces + conversa pode aparecer **vazia** se as 100 globais não a incluírem |

**Detalhe que afeta os 2 primeiros:** `department_id` continua nas deps dos `useEffect` ([:1037](../../frontend/src/context/CrmContext.tsx#L1037), [:1072](../../frontend/src/context/CrmContext.tsx#L1072)) mas não é mais usado nos targets (foi removido por LGPD) → **re-subscribe espúrio** se o dept mudar.

---

## 2. De onde vêm as LEITURAS (reads)

### 🔴 ALTA — `close_stale_attendances` faz full-scan da coleção a cada 30 min
[database_firestore.py:943-983](../../database_firestore.py#L943) — o loop em [:951](../../database_firestore.py#L951) faz `collection("wa_conversations").stream()` **sem nenhum `where()`** e filtra em Python. Roda por tenant dentro do cron `castro-crm-expire-takeovers` (`*/30`, [main.py:3070](../../main.py#L3070) dentro do loop `list_tenants`).
- **Custo:** ~3.000 conversas × 48 execuções/dia ≈ **~144k reads/dia/tenant**, mesmo sem nada elegível e ninguém logado. Escala linear com o tamanho da coleção × nº de tenants.
- ⚠️ **Confirme primeiro:** o comentário em [main.py:3040](../../main.py#L3040) diz "dormente" (projeto antigo), mas a doc da migração Oregon (`FIREBASE_ARCHITECTURE.md`, `env.oregon.yaml`, checklist marcado) indica o Cloud Scheduler **ativo em prod**. Um `gcloud scheduler jobs list` resolve em 10s. Se estiver ativo, **é o maior dreno de leitura, disparado.**
- **Fix:** `where("attendance_status","==","aberto").where("last_message_at","<",cutoff)` + índice composto `(attendance_status, last_message_at)`. `attendance_status` já nasce `"aberto"` ([:716](../../database_firestore.py#L716)), então não há problema de null. Backups já têm `fechado_inatividade` → excluídos de graça. **De ~3.000 → dezenas de reads/run.**
- ⚠️ *Não* use 2 inequalities/range simultâneos (o Firestore rejeita) — apenas `==` em status + range em `last_message_at`.

### 🔴 ALTA — Auth: ~4 reads + 3 writes Firestore por request autenticado
[auth.py:135-161](../../auth.py#L135) roda em **toda** request: `get_user_by_firebase_uid` (1 read) + `sync_user_identity` (1 write + 1 read + 1 write) + `get_user_by_id` (2 reads, sem usar o cache de departamentos) + `update_last_login` (1 write). **Sem nenhum cache token→user.**
- **Fix:** cache in-memory por `firebase_uid` (TTL 30-60s, chaveado por tenant); *throttle* `update_last_login` (a lógica `_is_new_login_session` já existe); só rodar `sync_user_identity` quando email/nome mudam (comparar antes do `.set`). Elimina ~2 writes + reads no caso comum. ⚠️ manter `set_tenant_context` mesmo no cache-hit.

### 🔴 ALTA — `_active_gc_participants` varre a coleção `users` 2× por mensagem do Google Chat
[database_firestore.py:2662-2685](../../database_firestore.py#L2662) — cada msg de chat interno chama `upsert_gc_conversation` **e** `save_gc_message`, e ambas refazem `_all_docs("users")` sem cache. **2×N reads por mensagem interna** (N = operadores).
- **Fix:** cachear participantes ativos por tenant (padrão do `channel_service`) ou derivar de `conversation.participants`; no mínimo computar 1× por evento.

### 🟡 MÉDIA — Listeners de conversations sem `limit`
- **Target `backup` admin** ([:778-779](../../frontend/src/context/CrmContext.tsx#L778)): adicionar `orderBy("last_message_at","desc")+limit(N)` com paginação. Histórico é read-mostly, não precisa carregar tudo ao vivo.
- **Targets do operador comum** ([:783-792](../../frontend/src/context/CrmContext.tsx#L783)): criar índice `(assigned_to_uid, last_message_at)` e aplicar `limit(50)`. Hoje, **uma msg nova no pool gera 1 read em CADA operador online** que escuta o pool.

### 🟡 MÉDIA — `gc_messages` filtrando no cliente
[InternalChatPanel.tsx:65-73](../../frontend/src/components/gchat/InternalChatPanel.tsx#L65) — adicionar `where("conversation_id","==",selectedConv.id)` (índice já existe). Corrige custo **e** o risco de vazamento entre spaces **e** o bug de conversa vazia. Fix simples e de alto valor.

### 🟡 MÉDIA — Endpoints admin que varrem coleções inteiras
Frequência menor (admin-only), mas cada chamada = coleção(ões) inteira(s):
- [/api/wa/contacts/all](../../main.py#L863) → `stream()` de `wa_contacts` inteira (agenda coex ~9k docs). O `limit` só corta **depois** de ler tudo. *Mitigação real:* cache backend por tenant com TTL (o frontend já cacheia 1×/sessão, então é ~1 scan/sessão).
- [/api/admin/conflicts](../../main.py#L2428) → full-scan de `wa_conversations` **+** `get_all_wa_contacts()` (2 coleções).
- [/api/wa/conversations](../../main.py#L1052) → pagina as conversas mas faz `get_all_wa_contacts()` (coleção inteira) no join para admin.
- [dashboard/summary](../../database_firestore.py#L2230) → lê `audit_metrics` inteira e filtra período em memória → trocar por `.where("date",">=",from).where("date","<=",to)` (os docs `usage_` são excluídos de graça, sem índice composto).

### 🟡 MÉDIA — Webhook relê o mesmo contato 3-4× por mensagem inbound
[webhook.py:527-748](../../webhook.py#L527) + `save_wa_message`/`ensure_daily_attendance`. O doc `wa_contacts` é lido 3× ([:1916](../../database_firestore.py#L1916), [:1490](../../database_firestore.py#L1490), [webhook.py:716](../../webhook.py#L716)). Ponto mais flagrante: `ensure_daily_attendance` relê em [:1490](../../database_firestore.py#L1490) o doc que `save_wa_message` **já tinha em mãos** em [:1916](../../database_firestore.py#L1916). Passar o dict adiante elimina o read.

### 🟡 MÉDIA — Polling fallback a 5s em prod
[CrmContext.tsx:1130-1142](../../frontend/src/context/CrmContext.tsx#L1130) — `POLLING_INTERVAL_MS=5000` em `docs/deploy/env.oregon.yaml` (vs 15000 default). **Só ativo se o cliente cair fora do snapshot mode** (opt-in via localStorage), mas quando cai: 12 ticks/min × 3 endpoints, **sem pausar com aba oculta**. Fixes: guard `document.hidden` + subir o intervalo pra ≥15s.

---

## 3. De onde vêm as GRAVAÇÕES (writes)

### 🔴 ALTA — `save_wa_message`: fan-out de 8-9 writes por mensagem inbound
[database_firestore.py:1837-2043](../../database_firestore.py#L1837), o coração do caminho quente. Por inbound: `wa_message_index` + `wa_messages` + `wa_contacts` (recência) + `wa_conversations` (upsert) + `attendances_daily` + **`wa_contacts` de novo** (espelho de protocolo) + `audit_metrics` global + `audit_metrics` per-operador + `usage_metrics`. Denormaliza `last_message_at`/`unread_count` em 2 docs.

Quick wins de baixo risco:
- **Unificar os 2 writes no mesmo doc `wa_contacts`**: [ensure_daily_attendance:1523](../../database_firestore.py#L1523) e [save_wa_message:2004](../../database_firestore.py#L2004) escrevem o mesmo doc no mesmo evento → fundir num `.set` (−1 write/inbound).
- **`ensure_daily_attendance` só espelhar quando o protocolo muda** ([:1498-1525](../../database_firestore.py#L1498)) — hoje reescreve `attendance_started_at=utcnow()` em todo inbound (−1 write no caso comum, 2ª+ msg do dia; corrige também um bug de "início" andando pra frente).

### 🔴 ALTA — `increment_audit_metrics`: read-modify-write não-atômico, 2 reads + 2 writes por mensagem
[database_firestore.py:2182-2227](../../database_firestore.py#L2182) faz `ref.get()` → soma em Python → `ref.set()`, 2× (global + per-operador). **Perde contagem sob concorrência** e gasta 2 reads/msg. O irmão `increment_usage_metrics` ([:2264](../../database_firestore.py#L2264)) **já usa `firestore.Increment` atômico sem read** — é só replicar o padrão.
- **Fix:** migrar para `firestore.Increment` (inclusive `messages_by_half_hour` como campo aninhado). ⚠️ tratar `first_activity_at` como set-once (hoje depende do `.get()`).

### 🟡 MÉDIA — `update_wa_message_status`: 3 writes por mensagem enviada, sem coalescing
[database_firestore.py:2120](../../database_firestore.py#L2120) — a Meta entrega `sent→delivered→read` em 3 webhooks; cada um faz 1 query + 1 write na mesma mensagem, **sem checar progressão**. Em campanhas/templates em massa, triplica os writes. **Fix:** pular o write se o status não avança (o doc já foi lido na query).

### 🟡 MÉDIA — Banners de sistema disparam fan-out de métricas inútil
[main.py:3059/3074](../../main.py#L3059) — o fix de recência (`advance_recency=False`) já funciona, mas o `save_wa_message` ainda dispara `audit_metrics`×2 + `usage_metrics` (write "vazio" pra `direction='system'`). **Fix:** `skip_metrics=True` / pular métricas quando `direction in ('system','internal')`. Banner automático não é mensagem faturável e ainda **distorce o peak_chart** do dashboard.

### 🟡 MÉDIA — Reentrega de history reescreve doc inteiro
[database_firestore.py:1867-1886](../../database_firestore.py#L1867) — em retry/history-sync, faz `.set` de ~13 campos mesmo quando nada mudou. **Fix:** comparar com o `existing` (já em mãos) e pular o write se idêntico, ou só escrever quando o status avança.

### 🟢 BAIXA — outros confirmados
- **Recência inflada por banners** ([:2286, 3167, ...](../../main.py#L2286)): 11 callers de `insert_transfer_system_message` usam `advance_recency=True` (default). Padronizar default `False` + campo `system_event_at` separado.
- **mark-read N+1 writes** ([:1008-1032](../../database_firestore.py#L1008)): 1 write/msg ao abrir thread com backlog. **Não é "de graça" remover** — o status por-mensagem alimenta o indicador de leitura na UI ([App.tsx:915](../../frontend/src/App.tsx#L915), `FEATURE_MESSAGE_STATUS` default ON). Tem debounce/guard, então fica baixa prioridade.

---

## 4. Plano de ação priorizado

| Prioridade | Ação | Impacto | Esforço |
|-----------|------|---------|---------|
| **1** | Confirmar se o cron está ativo e adicionar `where` em `close_stale_attendances` | **−~140k reads/dia/tenant** | Médio (1 índice + 1 query) |
| **2** | Cache de sessão no `auth` + throttle `last_login` | −2-3 writes e −reads por request, ×todos online | Médio |
| **3** | `where("conversation_id")` no listener `gc_messages` | corta reads + tapa vazamento + corrige bug | **Trivial** |
| **4** | `firestore.Increment` no `audit_metrics` + `skip_metrics` em system | −2 reads/msg, writes atômicos | Médio |
| **5** | Unificar os 2 writes `wa_contacts` + espelho condicional | −1 a −2 writes/inbound | Pequeno |
| **6** | `limit` nos targets `backup` (admin) e pool (operador) | corta snapshot inicial e fan-out do pool | Pequeno (+1 índice operador) |
| **7** | Cache backend TTL/tenant em `/contacts/all`; `where(date)` no dashboard | −scans admin | Médio |
| **8** | Coalescing de status + skip de reentrega idêntica | −writes em massa/campanhas | Pequeno |

---

## 5. Notas de verificação — 2 achados REFUTADOS (não implementar)

1. **"`upsert_wa_conversation` reescrever `_ch_fields` em todo upsert custa caro"** → **falso**. O Firestore cobra **1 write por documento, independente de nº de campos ou bytes**. Omitir os campos do merge dá economia **zero** e ainda reintroduz staleness na UI do operador (a denormalização é intencional, [:642-646](../../database_firestore.py#L642)).
2. **"Banner do auto-close re-dispara TODOS os listeners (read amplificado)"** → **falso**. `set(merge)` com valores idênticos é no-op de estado: o Firestore **não emite evento nem cobra read** para doc inalterado. Os reads do fechamento vêm da escrita **legítima** de `attendance_status='fechado_inatividade'` ([:976](../../database_firestore.py#L976)), que é necessária. Só sobra 1 write redundante (micro-otimização).

---

*Auditoria gerada via workflow multi-agente (33 agentes) em 2026-06-20.*
