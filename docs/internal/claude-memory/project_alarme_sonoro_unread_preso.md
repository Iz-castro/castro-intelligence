---
name: project_alarme_sonoro_unread_preso
description: "Alarme sonoro (CrmContext) tocava sem parar pro Comercial do hubloc — lia wa_contacts cru + wa_contacts.unread_count nunca zerava pelo read por thread; ADR 0011 EM PROD (2026-08-21) + backfill aplicado; mesmo dia: filtro \"Nao lidas\" (busca alem da janela, indices COLLECTION), \"So espiar\" (admin/supervisor), rotulos do botao; commit d9eb329"
metadata: 
  node_type: memory
  type: project
  originSessionId: f6b40a9e-0c51-4dd6-a9bf-214adc02fab2
  modified: 2026-08-21T20:44:04.007Z
---

Diagnostico 2026-08-21 (pedido do Rafael, operador `teste` hubloc ouvia "audio" sem conversa):
- Som = ALARME repetitivo (660 Hz quadrada, 30 s), nao o beep (beep OFF no hubloc; alarme ON, limiar
  1 min, depts [2]=Comercial).
- Causa A: alarme/beep iteravam `contacts` (janela crua de wa_contacts: pool sem dono + meus, sem
  filtro de bot_completed/depto); 3 leads do pool "no bot" invisiveis pro operador disparavam alarme
  perpetuo. **Os 3 (7996/7765/4457) foram APAGADOS a pedido do PO (26 docs, backup JSON no scratchpad
  da sessao f6b40a9e).**
- Causa B (raiz): `wa_contacts.unread_count` so era zerado pelo endpoint LEGADO por contato; o
  frontend (Fase 2C) usa o read por thread, que zerava so a conversation. Hubloc: ~1.5k presos.

Fix = **ADR 0011** (`docs/decisions/0011-...md`; diario `docs/internal/2026-08-21-diagnostico-alarme-sonoro.md`)
— **EM PROD rev `castro-crm-00086-fwt`**: contato = soma das threads (`recompute_wa_contact_unread`,
chamado no read por thread; endpoint de read com autorizacao); beep/alarme so sobre Novos+Meus ao vivo,
`settingsLoaded`, baseline por thread, deps primitivas, dedupe 5 s, ancora `last_inbound_at`; admin
ganhou targets da pool + minhas (Fase 3). Backfill APLICADO: hubloc 1.516, varizemed 264, -test 4.
- **Mesmo dia, pedidos seguintes — EM PROD rev `castro-crm-00088-tc9` (rollback 00086-fwt):** option **"Nao lidas"** no select de
  qualificacao (filtra por unread da THREAD + getDocs fora da janela por escopo; pagina 50; camada
  estatica; selecionada isenta/preservada; guardas de resposta tardia); **"So espiar"** (checkbox so
  admin/supervisor, localStorage por uid, early return no marcar-lida); botao: "Mostrar mais (N)" /
  "Buscar conversas mais antigas" / "Buscar mais nao lidas" (pisca vermelho so com linhas visiveis).
- **GOTCHA Firestore:** query "igualdade + desigualdade + 2 orderBy" em caminho de colecao do tenant
  exige indice **queryScope COLLECTION**; os COLLECTION_GROUP existentes so servem "igualdade + 1
  orderBy" (e `collectionGroup()` cruzaria tenants — nunca usar). Indices de unread criados em prod
  como COLLECTION (GROUP apagados). firestore.indexes.json mistura escopos de proposito.
- Follow-ups: ordenacao da busca e por unread_count desc (solucao definitiva = `has_unread` booleano +
  recencia + backfill); pool crua em Novos/Bot pode dar lista vazia com "ha mais"; badges inflam no
  modo; hidratacao sincrona no backend; Danielle 31/50 e Aline 28/50 threads com nao-lido REAL ->
  alarme delas segue com limiar 1 min (sugerir 5-10 min); UX da caixa Bot do admin; Backup sem limite.
- **Commitado** em `d9eb329` (feat(crm): ADR 0011 ...) apos pedido do PO.

**Why:** som/badge devem derivar das THREADS visiveis; contador do contato e derivado; filtros que
precisam alcancar fora da janela usam getDocs escopado + indice COLLECTION.

**How to apply:** nunca reintroduzir zeramento so da thread sem recompute do contato; nunca usar
`collectionGroup()` no frontend; ao criar indice pra query com desigualdade, escopo COLLECTION.
Ver [[project_bot_flow_e_pool_setor]], [[project_modo_recepcao_pool]], [[project_firestore_cost_hotspots]].
