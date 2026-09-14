# 2026-09-14 — Buffer da Val: merge, revisão adversarial da implementação e deploy (desligado)

## Resumo

- A branch `feature/bot-buffer` (implementação do desenho v2 em
  `docs/BUFFER_MENSAGENS_BOT.md`, feita em worktree paralela) recebeu merge de
  develop (`50e949c`, picker v2.1 F2a) sem conflitos, passou pela revisão
  adversarial da implementação, ganhou 7 correções e foi mergeada no develop
  (fast-forward, commit `91e926f`) e deployada em prod com
  `BOT_BUFFER_SECONDS=0` — **nenhum tenant mudou de comportamento**.
- Revisão: workflow com 9 revisores Opus (conformidade com o desenho,
  LGPD/interativas, concorrência/claims, exceção/ACK, persistência, cron,
  kill-switch/regressão, cobertura do harness, integração no webhook) + dedup
  + 3 refutadores por achado (código real / cenário de runtime / escopo e
  severidade) + crítico de completude. 86 agentes. 46 achados brutos → 25
  únicos → **7 confirmados** (F01, F02, F03, F05, F06, F12, F19), 18 refutados.
  A primeira rodada caiu no limite de sessão nos últimos 13 agentes; a
  retomada (`resumeFromRunId`) reaproveitou os 73 do cache e rodou só o resto.
- Gates: py_compile OK; `sim_bot_flow` 56, `sim_cx_flow` 173,
  `sim_reception_flow` 173, `sim_buffer_flow` **52 (era 36)**, `sim_picker_v21`
  46. Frontend intocado (sem `npm run build`).
- Decisão registrada em `docs/decisions/0012-buffer-debounce-bot-cx.md`.

## Confirmados e correções (detalhe no desenho, §Revisão da implementação)

| # | Achado | Correção |
|---|---|---|
| F01 | `claimed_at` nunca renovado no drain-loop: 3 turnos lentos > TTL → claim roubado, 2 turnos CX concorrentes | heartbeat `claim_hb` renovado a cada drain; claim vivo = max(identidade, heartbeat) dentro do TTL |
| F02 | sem orçamento de parede: janela + 30s + 3 turnos > 300s do Cloud Run | `_BUFFER_REQUEST_BUDGET_SECONDS=240` por request; turno novo só se couber o pior caso; sleeper devolve `no_budget` |
| F03 | flush do cron com orçamento reiniciado POR TENANT | orçamento global do request (claim novo só < 150s), teto de 10 contatos global, `max_drain_loops=1` |
| F05 | idade do item pelo `ts` da Meta: reprocesso de pending nascia vencido | campo `at` (instante do append) para idade e `oldest_at`; `ts` só ordena |
| F06 | mock do harness ignorava TTL | mocks espelham o real; cenário 14 com relógio avançado (takeover só com heartbeat vencido) |
| F12 | teto do drain-loop liberava sem drenar, sleeper já tinha desistido | residual aceito pelo desenho; log explícito; nunca drena sem turno |
| F19 | `BOT_BUFFER_MAX_CHARS` sem teto | grampeado a 256 |

Também: pré-varredura do payload sob try/except (erro = payload sem buffer,
nunca exceção no wrapper) e TTL com fonte única
(`database_firestore.bot_buffer_claim_ttl_seconds`).

## Refutados que valem registro

- F04 flush do cron quase no-op (cron `*/30` × cutoff 5min × descarte 10min):
  trade-off explícito do desenho — a recuperação real é a próxima mensagem do
  paciente.
- F10 turno interativo direto após 30s de claim vivo: não duplica resposta (o
  clique nunca está no buffer).
- F11 "kill-switch falha aberto": é a semântica documentada de override no READ.
- F20 gate ignora `system_settings.bot_enabled`: o dispatch do bot já é
  bloqueado antes do buffer.
- F21 write extra de `_clear_bot_state` no hubloc: por lead, não por mensagem;
  linha prevista no desenho.
- F23/F24/F25 (tooling e cobertura, low) foram atendidos mesmo assim:
  `scripts/set_tenant_buffer.py`, cenários 17 e 18 do sim.

## Crítico de completude (fronteiras que a revisão de código não cobre)

Libera merge/deploy desligado. Antes de **ativar**: observabilidade
(`scripts/_diag_bot_buffers.py --watch 5`), Whisper síncrono (follow-up
`asyncio.to_thread` antes da varizemed real), rollback para revisão pré-buffer
só com `buffer_seconds=0` + 60s + 1 tick do cron + diag vazio, LGPD
(`wipe_channel_data.py`/purge/RoPA-RIPD não conhecem `bot_buffers`; avaliar TTL
policy), capacidade (`containerConcurrency=8`, `maxScale=10`, `minScale=1`),
não coincidir com lote de reabertura/campanha de template. Tudo em
§Checklist de ativação do desenho.

## Deploy

- **Pegadinha nova:** `gcloud run deploy --source C:\Rafael\...` pela Bash tool
  (Git Bash) mangla as barras → `could not find source [C:Rafaelcastro-intelligence]`,
  e um `| tail` no fim mascara o exit code (saiu 0 com deploy falhado). Rodar
  o comando de deploy pelo **PowerShell**.
- Revisão nova: `castro-crm-00098-g52` (descoberta por
  `gcloud run revisions list --sort-by "~metadata.creationTimestamp"`), promovida
  por nome com `update-traffic --to-revisions castro-crm-00098-g52=100`. Rollback =
  `castro-crm-00097-fd4`. Smoke: `GET /` 200 e `GET /api/client-config` 200
  (projectId Oregon).

## Canário no `varizemed-test` ("Castro Intelligence SAC"), 04:21–04:30Z

- Ligado às 04:21Z (`set_tenant_buffer --seconds 10 --yes`); cache das instâncias
  atualizou às 04:25:33 (log "Tenant cache refreshed"). PO testou pelo número
  ***0484 (contato 8) e reportou "não funcionou". Linha do tempo reconstruída
  pelos logs (request log do Cloud Run: `timestamp` = início, `latency` = duração):
  - 04:25:33–38: 3 textos → **nenhuma resposta**: o lead ainda estava com a
    equipe (`bot_completed`, qualificação "convertido"); foram pra caixa do
    operador. Não é o buffer.
  - 04:26:04: PO fechou o atendimento (`set-attendance`) → `release_lead_to_bot`
    → `bot_states` recriado SEM `lgpd_*` (o handoff anterior tinha apagado o doc).
  - 04:26:15: clique de avaliação "Bom" no recibo (curto-circuito, ok).
  - 04:26:32 (m5): gate antigo viu `lgpd_consent` ausente → **turno direto**
    (12s de CX) → resposta 04:26:45. Durante o turno, hidratação gravou o
    consentimento no estado.
  - 04:26:35 + 04:26:39 (m6, m7): **bufferizadas → 1 turno** (m6 superada em
    10,4s; m7 claimou, CX 6s) → resposta 04:26:56. 04:26:50 (m8) chegou durante
    o turno → **drain-loop** → resposta 04:27:02. Buffer funcionando.
  - 04:27:02 (m9): bufferizada, turno de handoff levou **36s** de CX; m10/m11
    chegaram durante o turno e, com o handoff, ficaram pra equipe (desenho).
  - 04:28:03: PO fechou de novo → `release_lead_to_bot` → estado sem `lgpd_*`.
  - 04:29:24 áudio (Whisper 3,2s, síncrono: o request do texto seguinte ficou
    parado 4s até a transcrição acabar) → **turno direto** (mesmo gap) →
    resposta 04:29:38; 04:29:30 texto → bufferizado (10s + 3s) → resposta
    04:29:44. Duas respostas = o gap de hidratação, não o buffer.
- Causa da percepção: (1) a 1ª mensagem de cada ciclo novo após
  `release_lead_to_bot` não era bufferizada (gate lia só `bot_states`); (2) turnos
  lentos da Val (12s, 36s) somados à janela de 10s; (3) zero log no caminho feliz
  do buffer.
- Fix (mesmo dia): `bot_service.lgpd_consent_resolved` (regra de hidratação
  compartilhada) usado pelo gate do buffer com o contato já lido no webhook;
  logs `[BOT-BUFFER]` por mensagem (turno N com k itens / handler sem turno /
  consentimento não resolvido); cenário 19 no sim (56 checagens). Verificado por
  3 refutadores Opus antes do deploy.

## Próximos passos

1. PO: canário no `varizemed-test`
   (`.venv\Scripts\python.exe -m scripts.set_tenant_buffer --tenant varizemed-test --seconds 10 --yes`)
   seguindo a checklist; teste real pelo número de teste 7195-7758.
2. PO decide a varizemed real.
3. Follow-ups: Whisper em thread; `wipe_channel_data.py` + RoPA/RIPD com
   `bot_buffers`; TTL policy do Firestore; backfill do picker v2.1 (agendado
   com o PO em casa — fora desta frente).
