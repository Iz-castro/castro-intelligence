---
name: project_visibilidade_pos_assume
description: "Bug 2026-08-19 (hubloc) — operador B continuava vendo a conversa depois que A assumia; causas (admin/supervisor por design, picker auto-atribuía thread, cópias estáticas + extraContacts stale) e fix em camadas EM PROD rev 00084-h4w (commit 3aa9d05, 2026-08-20)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 24683375-79f3-4d64-8eed-9f6090a72c61
  modified: 2026-08-19T18:33:17.591Z
---

**Relato (Rafael, 2026-08-19):** hubloc, A e B abrem o mesmo lead em Novos, A assume, B continua vendo tudo.

**Investigação:** prod OK (assume grava dono+uid em contato E thread; pool=3). No clique simples de operador
comum o código já fechava. Caminhos reais: (1) B admin/supervisor (Helenice id 6 opera a fila) — nada fechava
o painel; (2) B abriu pelo picker "+" — `/conversation/open` em legacy auto-atribuía a thread sem tocar o
contato → split-brain contato=A/thread=B; (3) extraConversations/pagedConversations congeladas +
extraContacts engolindo 403 + rules de wa_messages liberando qualquer operador.

**Fix EM PROD (rev `castro-crm-00084-h4w`, promovida 2026-08-20 ~15h BRT; commit `3aa9d05` pushado; deploy atrasado por incidente do GCP em us-west1 — 2 builds expiraram na FILA; gcloud imprimiu rev velha de novo):** frontend watcher "thread mudou de dono → fecha + notice" (todos os papéis),
listener de doc da thread selecionada (refresh estáticas + permission-denied fecha), extraContacts despeja em
403/404, assume manda conversation_id; backend `assign_orphan_threads_to_lead_owner` no assume,
`/conversation/open` só auto-atribui se o lead já é meu. Sims 56/167/93 + build OK. Diário:
`docs/internal/2026-08-19-visibilidade-pos-assume.md`.

**Why:** invariante LGPD (isolamento do operador) tinha furo no "depois" — escopo só era checado na lista, não
na thread aberta. Ver [[project_operator_isolation_lgpd]].

**Rodada 2 (mesmo dia):** 32/32 verificações concluídas, 0 dos 7 pendentes refutados; síntese no diário.
P0 encerrado: varredura read-only 3 tenants = ZERO thread roubada pelo picker (215 divergências hubloc = coex
by design + transferências; contato 7351 explicado pelo transfer_log) → sem backfill. P5 aplicado: reassign-lead
também carimba threads órfãs. Resíduo: 1 doc canal 4 contato 4458 `assigned_to=1`/uid="" (1 write pendente de ok).

**How to apply:** não regredir o watcher nem o gate do `/conversation/open`; premissa não testada em prod:
Firestore entrega `permission-denied` ao listener de doc quando o doc sai do escopo (se não, só os caminhos
picker/"Carregar mais" ficam como antes). Regressões de produto a validar com PO: picker+enviar direto agora exige
Assumir; admin perde chat aberto quando thread muda de dono. Follow-ups priorizados no diário (P1 `GET /media` sem
auth, P2 `_require_contact_access` em `/conversation/{id}/read|takeover|return`, P3 rules wa_messages, P4-P10).
