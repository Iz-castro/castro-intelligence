---
name: project_picker_pin_extraconversations
description: Camada extraConversations (fixa conversa do picker fora do top-50) + fix IDOR /conversation/open; Trilha B pendente
metadata: 
  node_type: memory
  type: project
  originSessionId: 4a88a0f8-336a-41bc-8e73-70a3a3ec2622
---

Consequência direta do limit(50) nos listeners do operador ([[project_firestore_cost_hotspots]]): abrir um contato antigo pelo picker (conversa FORA do top-50 ao vivo) era derrubado — o republish do snapshot reconstrói `conversations` só com o top-50, apaga a entrada otimista, e o auto-select "yankava" a seleção. 

**TRILHA A — DEPLOYADA EM PROD 2026-06-26** (rev `castro-crm-00027-rik`; commits `328a2f7` feature + `93728b6` segurança):
- Camada `extraConversations` (Map conversation_id->Conversation) em frontend/src/context/CrmContext.tsx: conversas abertas pelo picker fora do top-50 ficam FIXADAS. `allConversations` = merge(live + extra, dedup com ao-vivo sobrescrevendo a estática) alimenta selectedConversation, os 6 memos de view, auto-select e lazy-fetch. `openConversationForContact` insere em extraConversations (não mais em conversations).
- **A1**: App.tsx ChatPanel (:641) + DetailPanel (:1334) — `selectedThread` agora usa `selectedConversation` do contexto (resolve sobre allConversations), não o `conversations` cru. Sem isso, conversa do picker tinha selectedThread=null -> canal/takeover/banner cegos (risco WABA #132001).
- **g2**: resetUserScopedState limpa extraConversations + extraContacts + fetchedExtraRef (PII lazy-fetched não vaza na troca de conta).

**A2 — IDOR DE SEGURANÇA (achado pela revisão adversarial, era pré-existente):** `POST /api/wa/conversation/open` (main.py) NÃO chamava `_require_contact_access` — operador comum abria/lia (e se pool, auto-atribuía) o lead de QUALQUER contact_id (inteiro enumerável); admin via 5761 contatos com dono expostos. Fix: gate adicionado (espelha GET /contact/{id}). Validado 403 em staging E prod (teste@ abrir contato 6644 da elizabete -> 403).

**LIÇÃO:** sempre rodar revisão adversarial (Workflow) antes de prod — ela pegou A1 e A2 que eu deixei passar.

**TRILHA B — ✅ DEPLOYADA EM PROD 2026-06-26** (commit f50c9e9, rev castro-crm-00029-fih):
- **g1 (item 1) FEITO**: transferContact chama `removeExtraConversation(selectedThreadId)` (helper que dropa de extraConversations E pagedConversations) — fim do fantasma na transferência. Só transferContact precisou (takeover/return/supervisor são ações de admin sobre conversas no top-300 ao vivo; assume/setAttendance mantêm a conversa com o operador).
- **"carregar mais" estático (item 3) FEITO** com **getDocs-crescente** (NÃO startAfter — last_message_at é normalizado pra string ISO e heterogêneo no Firestore, cursor quebraria; decisão validada pela revisão que refutou o falso-positivo de cursor). Camada `pagedConversations` (getDocs do mine com limite 50->100->150); listener ao vivo fica em 50; allConversations mescla 3 camadas (extra < paged < live). Só "Meus" (pool fica em 50); só operador comum com >=50 ao vivo (gate `canLoadMoreMine`); admin segue com 300 ao vivo.
- Fixes da revisão adversarial (Workflow): mark-read zera unread nas 3 camadas; limpa pagedConversations ao sair de "Meus" (bound staleness de reatribuição out-of-band); gate em mine-ao-vivo>=50 (evita getDocs vazio); meusConversations casa assigned_to OU assigned_to_uid (robustez vs drift); disabled condicional.

**ITEM 2 (dono forjado) — ✅ DEPLOYADO EM PROD 2026-06-29** (commit ca8978a, rev castro-crm-00033-cej): backend `/api/wa/conversation/open` re-lê o doc após o upsert e devolve `assigned_to`/`assigned_to_uid` REAIS; frontend openConversationForContact usa o dono real na entrada otimista (não forja `sessionUser`) e `setActiveView("meus")` virou condicional (`mine = realAssignedTo===id || realAssignedUid===firebase_uid`). Conversa de outro operador abre no chat sem virar fantasma em "Meus". Revisão adversarial focada (1 agente) deu OK. **TRILHA B 100% COMPLETA.** (Prova via API do caso "não é meu" não foi rodada — tokens expiraram; caso comum validado na UI + review. Pra rodar depois: precisa lead pool/próprio + atendimento de outro operador, senão o gate A2 barra com 403.)

**WORKFLOW DE STAGING (estabelecido):** `gcloud run deploy castro-crm --source . --tag staging --no-traffic --region us-west1 --project project-4a851bf9-f475-418c-800` (URL estável https://staging---castro-crm-jdznvidcxq-uw.a.run.app entre redeploys). Promover pra prod: `gcloud run services update-traffic castro-crm --to-revisions <rev>=100 ...` (instantâneo, sobe o que foi testado). Login Google na URL staging precisa do domínio em Firebase Auth authorized domains; email/senha não. Testar endpoints com tokens Bearer do Network tab (operador comum + admin). Ver [[project_oregon_prod_cutover]] e [[project_gcloud_python]].
