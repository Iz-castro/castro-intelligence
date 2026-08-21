---
name: project_pending_events_cronico
description: Root cause da perda cronica de msgs = channels flat fora de _GLOBAL_COLLECTIONS (cache vazio no refresh sob contexto). FIX EM PROD rev 00065. NAO era cold-start
metadata: 
  node_type: memory
  type: project
  originSessionId: 535f93e8-1725-4ae6-827a-2268b798f3c3
---

Resolvido 2026-07-16. A colecao `pending_webhook_events` tinha ~615 eventos.
Investigacao forense (distribuicao temporal + leitura de codigo) achou:

**82% (503) era A COLISAO** (15-16/07): canal 2 (aline) sobrescrito pelo varizemed
-> todas as msgs da aline falhavam. Ver [[project_channel_id_collision]].

**18% (~112) era a perda CRONICA** — e o root cause NAO era cold-start (hipotese
inicial errada). Era: `channels` e FLAT (`castro_crm_channels/{id}`) mas estava
**fora de `_GLOBAL_COLLECTIONS`** ([firestore_common.py](firestore_common.py) L41).
Entao `collection("channels")` rodando sob contexto de tenant lia
`tenants/{tid}/channels` (VAZIO). O golpe: `refresh_channels`
([channel_service.py](channel_service.py) L62, cache 60s) disparado numa chamada
autenticada de admin (contexto setado) montava o cache com **ZERO canais** -> por
60s TODO phone_id dava `no_channel_for_phone` -> msgs de cliente em pending.
Explica o padrao: intermitente, horario comercial (admin usando o CRM), TODOS os
canais de uma vez (inclusive o standard ch4), pioraria com multi-tenant. Prova:
`collection("channels")` sem contexto=5 docs, sob `tenant_context(hubloc)`=0 docs.

**FIX (commit 073e1d0, PROD rev 00065-zif, 2026-07-16):** adicionar "channels" a
`_GLOBAL_COLLECTIONS` -> collection/document("channels") sempre flat. Provado
(0->5 docs sob contexto) + testes A-F em prod (monitor: zero no_channel novo
durante teste com WhatsApp real; isolamento cross-tenant OK; usuario confirmou
msgs chegando). Rollback ficou em rev 00061. main.py ja usava
global_document("channels") num ponto — o fix unificou.

**Drain:** os 591 eventos de conteudo (messages+echoes) foram entregues save-only
(gate `_silent_reprocess` no webhook, commit 35e25ac; script
scratchpad/drain_pending_silent.py) com 3 camadas de protecao (gate + bot noop +
tripwire de POST /messages) -> tripwire=0, ZERO outbound pro cliente. Restaram 24
nao-conteudo (19 "Failed to commit transaction" = issue separada de contencao de
contador; 5 agenda-syncs pulados).

FOLLOW-UPS abertos: auditar OUTRAS colecoes flat fora de _GLOBAL_COLLECTIONS
(mesma classe de bug); monitor/alerta permanente no pending count; investigar os
19 Failed-to-commit. Ver [[project_channel_id_collision]] e
[[project_firestore_cost_hotspots]].
