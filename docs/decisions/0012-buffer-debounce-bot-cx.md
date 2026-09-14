# ADR 0012 — Buffer/debounce de mensagens picadas para o bot CX (Val)

Data: 2026-09-14 · Status: **aceito** (implementado; kill-switch DESLIGADO por
default — deploy não muda nenhum tenant). Desenho completo e revisões em
`docs/BUFFER_MENSAGENS_BOT.md`.

## Contexto

Paciente digita picado ("Oi" / "tudo bem?" / "queria marcar consulta") e a
Val roda 3 turnos Dialogflow CX separados: conversa trançada, custo triplo de
CX e compreensão pior. O webhook já segura o ACK da Meta durante o turno (até
~2 min com read-retry) e absorve a reentrega (~23 s) pelo guard `was_dup`.
Executor pós-ACK (BackgroundTasks) no Cloud Run com CPU throttled já foi
rejeitado pelo projeto (`docs/internal/2026-08-18.md`).

## Decisão

Debounce "última mensagem vence", **segurando o ACK como hoje**, com estado
persistido em doc PRÓPRIO tenant-scoped `bot_buffers/{contact_id}`:

- Só tenants com `settings.ai.bot_engine == "dialogflow_cx"`; só após
  `bot_states.lgpd_consent is True`; NUNCA conteúdo de origem `interactive`
  (o aceite LGPD é casado por igualdade exata — um join quebraria o
  consentimento).
- Pré-varredura do payload (o loop do webhook é serial): só a última mensagem
  elegível de cada remetente dorme e claima; as anteriores só appendam.
- Token `uuid4` rotacionado a cada append (nunca contador int); claim
  transacional com identidade (`claimed_at`) + heartbeat (`claim_hb`) renovado
  a cada drain; TTL derivado de `2*CX_DETECT_TIMEOUT_SECONDS + 60`; drain-loop
  (teto 3) e **orçamento de parede de 240 s por request** (Cloud Run mata em
  300 s) — turno novo só começa se couber o pior caso.
- Idade do item pelo instante do append (`at`, não pelo `ts` da Meta);
  descarte >10 min no drain; flush de órfãos no cron `*/30` com orçamento
  GLOBAL do request e 1 turno por contato.
- Kill-switch em duas camadas: `BOT_BUFFER_SECONDS` (env, default 0) e
  `settings.ai.buffer_seconds` por tenant, lido no READ
  (`scripts/set_tenant_buffer.py`, dry-run por default).

## Alternativas rejeitadas

- **ACK cedo + executor atrasado** (BackgroundTasks / Cloud Tasks): CPU
  throttling após a resposta, infra nova, perda em instância morta.
- **Buffer dentro de `bot_states`**: `_set_bot_state` faz merge do dict
  inteiro e `_clear_bot_state` deleta o doc — turno em voo ressuscitaria itens
  drenados e o handoff apagaria rajada pendente.
- **Contador int como token**: doc deletado/recriado reutiliza o contador e um
  handler velho "casa" com rajada alheia.

## Consequências

- Rajada de k mensagens = k appends + **1 turno** (antes: k turnos). Custo
  ~3 reads + 3 writes por mensagem elegível; nada muda com o switch desligado.
- Latência de resposta + janela (10 s sugeridos) no caminho normal; até
  ~35 min em órfãos raros (instância morta durante o sleep) — residual aceito.
- Coleção nova com texto bruto do paciente por segundos (normal) até ~35 min
  (órfão): fora dos scripts de wipe por canal — pendência LGPD registrada no
  desenho (§Checklist de ativação).
- Rollback para revisão PRÉ-buffer só depois de zerar `buffer_seconds` e
  esperar a drenagem (cache de tenant 60 s + 1 tick do cron).
- Whisper síncrono segura o event loop e atrasa os timers do buffer na mesma
  instância — aceito para o canário; follow-up `asyncio.to_thread` antes da
  varizemed real.

## Referências

- Desenho v2 + revisão adversarial de desenho (21 achados) + revisão
  adversarial da implementação (46 → 25 → 7 confirmados, corrigidos):
  `docs/BUFFER_MENSAGENS_BOT.md`.
- Gate: `tools/sim_buffer_flow.py` (52 checagens, webhook real com
  persistência/CX/envio mockados; contratos transacionais reais).
- ADRs relacionados: 0010 (modo Recepção / pool), 0011 (não-lido derivado).
