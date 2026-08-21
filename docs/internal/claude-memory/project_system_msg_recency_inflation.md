---
name: project_system_msg_recency_inflation
description: "System/auto messages stamp timestamp_wa=utcnow() and inflate last_message_at, floating inactive/backup threads to the top with misleading recency"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6ca44cfb-a8e5-42e9-a5cc-1bf809a16940
---

Toda mensagem `direction="system"` é gravada com `timestamp_wa = utcnow()` (`insert_transfer_system_message`, database_firestore.py ~1772) e **avança o `last_message_at`** do thread e do contato (save_wa_message ~1988/2013 → upsert_wa_conversation). Efeito colateral confuso: um atendimento **fechado por inatividade** (cron `cron_expire_takeovers` → banner "Atendimento fechado automaticamente por inatividade.", main.py ~3073) salta pro **topo** da caixa como se fosse o mais recente. Mesmo padrão no auto-return de takeover.

Sintoma real investigado (jun/2026, contato Fazza 7120): conversa de backup mostrando timestamp "02:30" mas última msg do cliente em 19/05 — o 02:30 era o banner de auto-close no thread coex da Danielle, não mensagem do cliente. (Lembrete: a Caixa Backup ordena por `conversation.last_message_at` do próprio thread, não do contato — CrmContext.tsx ~581. É um contato com 2 threads em 2 números = coexistence.)

**Fix aplicado (jun/2026, commit 6f8b5b4, rev castro-crm-00018-66z):** `save_wa_message`/`upsert_wa_conversation`/`insert_transfer_system_message` ganharam `advance_recency=True` (default = comportamento inalterado). Só os 2 banners automáticos do `cron_expire_takeovers` (auto-close + auto-return, main.py ~3063/3078) passam `advance_recency=False` — o banner ainda grava com timestamp_wa real (aparece no histórico) mas NÃO sobe `last_message_at`. Transferência/fechamento MANUAL seguem subindo (decisão: só os automáticos são gateados; manual combina com o badge de transferência [[project_transfer_badge]]).

Relacionado: [[project_backup_inbox_feature]], [[project_operator_isolation_lgpd]].
