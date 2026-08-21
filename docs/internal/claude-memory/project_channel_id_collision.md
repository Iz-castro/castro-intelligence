---
name: project_channel_id_collision
description: "Incidente 2026-07-16 — channel_id por-tenant colidiu na colecao flat global channels; raiz, recuperacao PITR e fix"
metadata: 
  node_type: memory
  type: project
  originSessionId: 535f93e8-1725-4ae6-827a-2268b798f3c3
---

Incidente 2026-07-16 (prod Oregon). Ao provisionar o tenant `varizemed-test`,
os canais dele (ids 1,2) **sobrescreveram** os canais coex 1,2 do Hubloc
(Izael, aline).

**Raiz:** a colecao `channels/{id}` e FLAT/global (`_flat_document`), mas o id
vinha de `next_sequence("channels")` que resolve o tenant do contexto → contador
POR-TENANT. Tenant novo comeca em 1,2 e colide com os canais existentes.

**Fix (commit 0afc3c4, prod rev 00061-kuh):** `next_sequence("channels", tenant_id="")`
em [channel_service.py](channel_service.py) linha ~265. CUIDADO: `tenant_id=None`
NAO resolve (e identico a nao passar — cai no contexto); tem que ser `""` (string
vazia): pula a resolucao de contexto e forca o ramo do contador flat global.
Provado com teste: `""` da ids globais monotonicos entre tenants; `None` reseta e
colide. Contador global `_meta/counters.channels` ajustado 4→6.

**Recuperacao (sem tocar nos 2476 docs corretos do Hubloc):** PITR (readTime via
REST API `?readTime=`, o kwarg `get(read_time=)` da lib nao funciona na versao
instalada) restaurou channels/1,2 do Hubloc; varizemed real movido pra channels/6;
dados de teste do varizemed apagados. Denormalizados corrompidos nas conversas
corrigidos em 2 passes: `channel_label`/`channel_phone_number` (45 convs) e depois
`channel_type`/`source_channel_type` (45+10 convs) — o segundo importa porque o
badge "(Coexistence)" vem de `channel_type` e o `source_channel_type` errado
vazava conversa coex na aba Equipe (LGPD, ver [[project_operator_isolation_lgpd]]).

Scripts da recuperacao no scratchpad da sessao (recover_channels.py,
fix_denorm.py, fix_channel_type.py). Ver tambem [[project_pending_events_cronico]].
