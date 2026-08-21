---
name: project_firestore_cost_hotspots
description: Auditoria 2026-06-20 dos drenos de leitura/gravacao Firestore — onde cortar custo
metadata: 
  node_type: memory
  type: project
  originSessionId: 4a88a0f8-336a-41bc-8e73-70a3a3ec2622
---

Auditoria multi-agente (2026-06-20) dos custos de read/write no Firestore. Há só 5 pontos de `onSnapshot` (3 em CrmContext.tsx: wa_contacts/wa_conversations/wa_messages; 2 em InternalChatPanel.tsx: gc_conversations/gc_messages). O custo NÃO está nos listeners — está em:

**Maior dreno de LEITURA:** `close_stale_attendances` (database_firestore.py:951) faz `collection("wa_conversations").stream()` SEM `where`, por tenant, no cron `castro-crm-expire-takeovers` (*/30). ~3k conversas × 48/dia ≈ **~144k reads/dia/tenant**. Comentário em main.py:3040 diz "dormente" mas docs da migração Oregon indicam scheduler ativo — CONFIRMAR com `gcloud scheduler jobs list`. Fix: `where(attendance_status=="aberto").where(last_message_at<cutoff)` + índice composto (NÃO usar 2 inequalities — Firestore rejeita).

**Maior dreno de GRAVAÇÃO:** `save_wa_message` (database_firestore.py:1837) = ~8-9 writes + ~8 reads por mensagem inbound (≈17 ops/msg). Quick wins: (1) fundir os 2 `.set` no mesmo doc wa_contacts (ensure_daily_attendance:1523 + save_wa_message:2004); (2) `increment_audit_metrics` (2182) usa read-modify-write não-atômico — migrar pra `firestore.Increment` como `increment_usage_metrics` (2264) já faz; (3) `skip_metrics` para `direction='system'` (banners não são msg faturável).

**Outros:** auth.py:135 faz ~4 reads+3 writes/request sem cache de sessão; `_active_gc_participants` varre `users` 2x/msg de gchat; `gc_messages` listener (InternalChatPanel.tsx:65) lê 100 globais e filtra no cliente (custo+vazamento+bug, fix trivial = add `where(conversation_id)`); targets backup(admin)/pool(operador) de wa_conversations sem `limit`.

**REFUTADO #1 (não implementar):** reescrever `_ch_fields` no upsert NÃO custa — Firestore cobra por doc-op, não por campo/bytes.

**REFUTADO #2 — RECLASSIFICADO como NÃO-CONFIRMADO:** a ideia de que "banner com merge idêntico não re-dispara listeners / não cobra read" NÃO foi confirmada em fonte primária (2026-06-20). O comportamento de no-op documentado é só p/ Cloud Functions triggers, não p/ billing de reads de onSnapshot. Só teste empírico garante. O write idêntico CUSTA 1 write de qualquer jeito.

**Gotcha Firestore confirmado (2026-06-20):** um `create()` que falha com `AlreadyExists` (precondition) É cobrado como write ("you still incur charges if the operations result in no changes"). Não usar create()-como-guard em hot path achando que é grátis.

**Cron CONFIRMADO VIVO (gcloud scheduler jobs list):** `castro-crm-expire-takeovers` `*/30` ENABLED em us-west1 (Oregon), batendo `/api/internal/cron/expire-takeovers`. O "dormente" em main.py:3040 está desatualizado.

**FIXES DEPLOYADOS EM PROD 2026-06-20 (commit 53ac967 em develop; revisao Cloud Run castro-crm-00020-cds em Oregon us-west1):** (1) cron `close_stale_attendances` agora `.where("attendance_status","==","aberto")` — ressalva: docs abertos legados SEM o campo não auto-fecham (reabrem na próx msg); (2) `increment_audit_metrics` migrado p/ `firestore.Increment` (atômico, 0 reads), `first_activity_at` deixou de ser gravado (era dado morto na UI); (3) cache in-memory de auth em auth.py (`_auth_user_cache`, TTL `AUTH_USER_CACHE_TTL_SECONDS`=45s) — token ainda verificado sempre; `invalidate_auth_cache()` disponível p/ wiring em mudança de role/is_active. (4) memoização de `fetchBillingStatus` em CrmContext.tsx via `useCallback([bundle])` — corta spam de `GET /api/wa/channel/{id}/billing-status` (commit 909b475, revisão castro-crm-00021-xqr). O banner BillingHealthBanner re-disparava o GET a cada render do provider; pra Castro (Tech Provider/managed billing) a consulta retorna erro Meta #10 cosmético e o banner é suprimido, então o GET era puro desperdício. Frontend: efeito só vale após cada sessão recarregar o bundle.

## FRENTE DOS LISTENERS DO OPERADOR — ✅ DEPLOYADA 2026-06-23

Commit 067ea0a, revisão castro-crm-00022-ln7. Os 3 targets do operador (unassigned:blank/null, mine) ganharam `orderBy(last_message_at desc)+limit(50)`. Índice composto `(assigned_to_uid ASC, last_message_at DESC)` criado e READY (id CICAgJiH2JAK, scope COLLECTION_GROUP). Backup target do admin DEFERIDO de propósito (limitar exige paginação/busca-aware; Caixa Backup tem busca client-side que ficaria incompleta).

⚠️ Gotchas registrados: (a) `firebase` CLI NÃO instalado → criar índice via `gcloud firestore indexes composite create --database="(default)" --collection-group=... --query-scope=COLLECTION_GROUP --field-config='field-path=X,order=ascending'` — o `--field-config` PRECISA de aspas no PowerShell senão quebra na vírgula. (b) gcloud desta máquina NÃO tem `monitoring time-series` — puxar métricas via REST `https://monitoring.googleapis.com/v3/projects/{proj}/timeSeries` com `gcloud auth print-access-token`. (c) database Firestore = `(default)` us-west1.

MEDIÇÃO (Cloud Monitoring, 2026-06-23): últimas 24h = 375k reads / 34k writes; semana anterior rodava 528-806k reads/dia e 117-215k writes/dia; dia ocioso (22/06) despencou para 1.4k reads → confirma que o cron full-scan era o dreno de fundo 24/7. Os ~375k restantes em dias ativos eram operador-driven (alvo desta frente; medir de novo no próximo dia ativo).

PRÓXIMA FRENTE = write-side (ver "OUTRAS FRENTES NA FILA" abaixo). Detalhe histórico do plano já executado:

**Limitar+ordenar o listener onSnapshot de wa_conversations do OPERADOR comum (Achado #2 da auditoria).** Hoje `buildConversationSnapshotTargets` (frontend/src/context/CrmContext.tsx ~765-800) retorna os targets do operador comum (`unassigned:blank` assigned_to_uid=="", `unassigned:null` assigned_to_uid==null, `mine:{uid}`) SEM orderBy e SEM limit → ao abrir o CRM o operador baixa o pool inteiro. O target `backup` do admin (where is_backup==true) também está SEM limit. (Os listeners de CONTATOS `buildContactSnapshotTargets` JÁ têm limit(50)+orderBy e índice ok — NÃO mexer. Admin `all` de conversations já é limit(300).)

PLANO:
1. Adicionar `orderBy("last_message_at","desc"), firestoreLimit(50)` aos 3 targets do operador E ao target `backup` do admin em `buildConversationSnapshotTargets`. mergeVisibleConversations já ordena/dedupe client-side (operador = até 3×50=150 brutos, igual ao padrão de contatos).
2. Criar 2 índices compostos NOVOS em firestore.indexes.json (o existente assigned_to_uid+status+last_message_at NÃO serve — status no meio do índice):
   - wa_conversations `(assigned_to_uid ASC, last_message_at DESC)` — targets do operador
   - wa_conversations `(is_backup ASC, last_message_at DESC)` — target backup do admin
3. ⚠️ ORDEM DE DEPLOY CRÍTICA: publicar os índices e ESPERAR construírem ANTES de subir o código. Senão o onSnapshot do operador falha com FAILED_PRECONDITION e o operador fica sem conversas. Deploy de índices: `firebase deploy --only firestore:indexes --project project-4a851bf9-f475-418c-800` (firebase.json já mapeia firestore.indexes.json; sem .firebaserc, passar --project). Depois `gcloud run deploy castro-crm --source . --region us-west1 --project project-4a851bf9-f475-418c-800`.

OUTRAS FRENTES NA FILA (shortlist do relatório, por retorno/esforço): write-side — (a) unificar os 2 `.set` no mesmo wa_contacts em save_wa_message (:1523 + :2004), −1 write/inbound; (b) `skip_metrics` p/ direction='system' (banners), −2-3 writes/banner; (c) coalescing em update_wa_message_status (:2120), pular write se status não avança (grande em campanhas). read-side — cache backend TTL/tenant em /contacts/all; where(date) no dashboard audit_metrics. higiene — wiring de invalidate_auth_cache() no endpoint de role/desativação.

Deploy padrão Oregon: `gcloud run deploy castro-crm --source . --region us-west1 --project project-4a851bf9-f475-418c-800 --quiet` (ver [[project_oregon_prod_cutover]] e [[project_deploy_script_desatualizado]]; CLOUDSDK_PYTHON ver [[project_gcloud_python]]). Validar TS antes: `npm --prefix frontend run build`. Relacionado a [[project_system_msg_recency_inflation]] e [[project_operator_isolation_lgpd]].
