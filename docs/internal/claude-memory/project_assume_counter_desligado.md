---
name: project_assume_counter_desligado
description: "Contador de \"assumidas sem resposta\" DESLIGADO em prod a pedido da empresa (2026-07-17); religavel via env FEATURE_ASSUME_COUNTER=true"
metadata: 
  node_type: memory
  type: project
  originSessionId: 350b14c8-c4e7-4e4e-9523-6f865d4e3b43
---

Em 2026-07-17 a empresa pediu para desligar o bloqueio de assume por
"assumidas sem resposta" (403 no /api/wa/assume quando counter <= -2).

- Flag nova `FEATURE_ASSUME_COUNTER` em config.py, default **false**
  (commit 328413c). Em prod: rev `castro-crm-00050-tpf` (Oregon,
  [[project_oregon_prod_cutover]]), 100% trafego promovido manualmente
  via update-traffic em 2026-07-17 ~12:23 BRT, SEM a env var setada.
  ATENCAO: numeracao de revisao MUITO fora de ordem nesse servico —
  a 00050-tpf foi criada DEPOIS da 00069-cef; quase promovi errado.
- Gate cobre: check 403 + decrement + mark_contact_pending_response.
- `_maybe_credit_assume_counter` ficou ATIVO de proposito: quita
  contadores -1/-2 e flags assume_pending_response antigos, para
  religar nao bloquear ninguem por divida velha.
- Botao "Reset" do admin no frontend continua (no-op inofensivo).
- Para religar: setar env `FEATURE_ASSUME_COUNTER=true` no Cloud Run
  (nova revisao), sem mudar codigo. "Por enquanto" — pode voltar.
