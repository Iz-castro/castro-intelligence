# Buffer de mensagens do bot (Val) — debounce de mensagens picadas

> **Status em 2026-09-11: IMPLEMENTADO NESTA BRANCH, KILL-SWITCH DESLIGADO.**
> (`feature/bot-buffer`). `BOT_BUFFER_SECONDS=0` mantém todos os tenants no
> fluxo anterior; ativação deve começar pelo `varizemed-test`. O v1 deste desenho passou por revisão adversarial
> (2 críticos Opus contra o código real — 21 achados, 2 críticos de premissa)
> e este v2 incorpora TODAS as correções. Os pontos marcados **[REV]** vêm da
> revisão — não os "simplifique" de volta.
> Gates locais completos: `sim_bot_flow` 56 / `sim_cx_flow` 173 /
> `sim_reception_flow` 173 / `sim_buffer_flow` 36. Antes de mergear no develop:
> revisão adversarial da implementação e canário no `varizemed-test`.

## Problema numa frase

Paciente digita picado — "Oi" / "tudo bem?" / "queria marcar consulta" em 3
mensagens seguidas — e a Val roda **3 turnos CX separados**, respondendo 3
vezes: conversa trançada, custo triplo de CX, pior compreensão.

## Decisão

**Debounce "última mensagem vence", segurando o ACK como hoje.** Janela de
quietude configurável (default sugerido: 10s, best-effort). Mensagens de
texto elegíveis ao bot entram num buffer persistido em doc PRÓPRIO; quem
processa o turno é o handler da última mensagem da rajada, com o texto
concatenado. Os demais devolvem 200 sem turno.

Por que segurar o ACK (e não ACK-cedo + executor atrasado): o webhook já
segura o ACK durante o turno (60s de CX + read-retry ≈ até ~2min) e a
reentrega da Meta (~23s) já é absorvida por `was_dup`; e executor pós-ACK no
Cloud Run com CPU throttled é o desenho que o projeto já rejeitou
(docs/internal/2026-08-18.md) e que a revisão do reopen-batch confirmou
frágil. Zero mudança na semântica de perda: mensagem persistida ANTES de
qualquer espera.

## Escopo v1 (corrigido pela revisão)

- **Buffer SÓ com consentimento LGPD resolvido.** **[REV crítico]** O clique
  interativo do aceite ("Sim") NÃO curto-circuita no webhook: ele é
  normalizado para texto (`webhook.py:887-893` → `extract_interactive_inbound`
  devolve o id, ex. `lgpd_aceitar`, e `effective_msg_type` vira `"text"`) e
  ALIMENTA `process_bot_message_async`. O gate LGPD casa o texto INTEIRO por
  igualdade exata (`lgpd_bot.py:87-92`); um join `"lgpd_aceitar\nquero
  marcar"` cai no "não entendi" e o consentimento NUNCA é gravado. Além
  disso, no turno do aceite o `bot_service` SUBSTITUI o texto do turno por
  `user_first_input` (`bot_service.py:783`) — texto junto seria jogado fora.
  Regra: **antes do append, ler o estado; só bufferar se
  `lgpd_consent is True`** (fase CX plena). Pré-consentimento = fluxo atual,
  intocado, mensagem a mensagem.
- **Conteúdo de origem `interactive` NUNCA entra no buffer** **[REV]** —
  guardar o `msg_type` CRU antes da normalização da linha ~893 e usar como
  bypass. Clique pós-consentimento roda turno imediato; ver §Turno imediato.
- Curto-circuitos existentes (clique de avaliação `webhook.py:999`, botão de
  template `~1013`) ficam como estão — já saem antes do dispatch.
- **Só engine Dialogflow CX** (`settings.ai.bot_engine`). Builtin (hubloc)
  fora — é menu-driven.
- Áudio: transcript entra no buffer como texto (append no ponto ~1163).
  **[REV]** Ciente: o Whisper é síncrono e segura o event loop — o caminho
  de áudio quase não se beneficia do buffer e a janela escorrega. Aceito.
- Mensagem de humano/echo/system: fora (já não passam pelo funil).

## Estado — doc PRÓPRIO `bot_buffers/{contact_id}` [REV]

NÃO usar `bot_states`: `_set_bot_state` reescreve o dict inteiro com merge
(`bot_service.py:246`) e `_clear_bot_state` DELETA o doc (`:250`) — um turno
em voo ressuscitaria itens drenados e o handoff apagaria rajada pendente.
Coleção nova tenant-scoped `bot_buffers`, doc por contato:

```
items: [{"text": str, "ts": iso_da_Meta, "n": int}]  # n = ordem do append
token: str (uuid4, rotacionado a cada append)         # NUNCA contador int
claimed_at: iso | null
oldest_at: iso | null   # escalar consultavel p/ o flush do cron [REV]
```

**[REV]** Token opaco em vez de `seq` int: doc deletado/recriado reusaria o
contador e um handler velho "casaria" com rajada alheia. Ordenação do join:
`(ts, n)` — o ts da Meta tem granularidade de SEGUNDO (empata em rajada) e
relógio de servidor entre instâncias inverte ordem; o `n` transacional
desempata. **[REV]**

## Mecanismo (passo a passo, corrigido)

**Pré-passo por PAYLOAD** **[REV crítico]**: o loop do webhook é SERIAL
(`for msg in messages`, `webhook.py:728`) — se cada mensagem dormisse a
própria janela, a msg1 acordaria ANTES de a msg2 ser appendada (k turnos, e
3 msgs × janela+turno estoura os 300s do Cloud Run). Regra: pré-varrer
`value["messages"]`, identificar as elegíveis ao buffer; as k-1 primeiras
**appendam e NÃO dormem**; só a ÚLTIMA elegível do payload dorme/claima.

Para a mensagem que dorme:

1. **Append transacional** no `bot_buffers/{contact_id}`: `items += [item]`,
   `token = uuid4()`, `oldest_at = min(atual, ts)`; guarda `meu_token`.
2. `await asyncio.sleep(BUFFER_SECONDS)` — best-effort **[REV]**: Firestore
   sync/Whisper podem atrasar o despertar; o claim impede dupla resposta,
   e o pior caso vira 2 turnos sequenciais, não trançados.
3. **Re-lê o doc**: `token != meu_token` → chegou mais nova; retorna sem
   turno (o handler dela herda).
4. **Claim com espera** **[REV]**: transação — se `token == meu_token` e
   `claimed_at` vazio/vencido, carimba e **drena** (lê e zera `items`,
   `oldest_at=null`, rotaciona `token`). Se há claim VIVO (turno em voo),
   NÃO desistir: re-tentar a cada ~2s por até ~30s; se ainda vivo, retornar
   (o detentor fará o drain-loop do passo 5). TTL do claim **derivado do
   config**: `2*CX_DETECT_TIMEOUT_SECONDS + 60` (≥180s hoje) — 3min
   hardcoded é MENOR que turno real já visto (>109s + retry). **[REV]**
5. **Turno + drain-loop** **[REV]**: junta por `(ts, n)` com `"\n"`,
   **trunca a 256 preservando o FIM** (o conector corta pela CABEÇA —
   `bot_engine_dialogflow.py:45/222` — o corte útil é no webhook, com log),
   chama `process_bot_message_async`, envia. Antes de soltar o claim:
   re-lê `items`; se chegou item novo durante o turno, drena e roda OUTRO
   turno (loop com teto de ~3 iterações). Só então limpa `claimed_at`.
6. **Try/except no caminho INTEIRO** **[REV]**: qualquer exceção que escape
   vira pending_webhook_event e o retry re-entra com `was_dup=True` = bot
   pulado pra sempre (mesmo racional do bloco atual `webhook.py:1061-1075`).
   Degrada só a resposta do bot; `finally` (soltar claim) dentro do try.

Itens com `ts` mais velho que **10min são DESCARTADOS no drain** (com log)
**[REV]**: `return_contact_to_bot`/`release_lead_to_bot` não conhecem o
buffer e um ciclo novo não pode concatenar texto do atendimento anterior.
Handoff CX (`_clear_bot_state`, `bot_service.py:1291`) ganha uma linha:
limpar também o `bot_buffers/{contact_id}`.

## Turno imediato (clique interativo pós-consentimento) [REV]

Caminho que roda turno SEM passar pelo buffer precisa invalidar a rajada
pendente, senão = dupla resposta (classe do incidente 2026-08-14/18):
na chegada de interativa elegível ao bot, **drenar o buffer na transação**
(rotacionar token — handlers dormindo desistem sozinhos no passo 3) e, se
havia itens, rodar PRIMEIRO um turno com o texto junto, DEPOIS o turno do
clique (2 turnos sequenciais, ordem preservada).

## Flush de órfãos (cron) — não é "1 linha" [REV]

Instância morta no sleep deixa buffer órfão. Recuperação: (a) próxima
mensagem do contato drena tudo; (b) passo novo no cron de 30min:

- query barata por ESCALAR: `bot_buffers.where("oldest_at", "<", cutoff_5min)`
  (nunca full scan; `oldest_at` existe pra isso);
- **teto por tick** (ex.: 10 contatos) e orçamento de tempo (~60s), rodando
  DEPOIS do trabalho existente do cron (expire/close não podem ser
  sacrificados; request do cron também morre em 300s);
- pra ENVIAR é preciso resolver canal/token/phone_id pelo contato (padrão de
  `main.py:3958-3968`); extrair helper de envio compartilhado com
  `_send_bot_reply` (webhook.py:279) em vez de duplicar.

## Config e kill-switch

- `config.py`: `BOT_BUFFER_SECONDS` (env, **default 0 = DESLIGADO** — deploy
  não muda nenhum tenant), `BOT_BUFFER_MAX_CHARS=256`.
- Override por tenant: `settings.ai.buffer_seconds` (default no READ, nunca
  backfill). Ligar na varizemed = editar settings; kill sem deploy = zerar.
- `varizemed-test` primeiro, sempre.

## Custo por mensagem elegível [REV]

~3 reads + 3 writes (append transacional 1r+1w, re-leitura 1r, claim/drain
1r+1w, soltar claim 1w) + a janela de latência. Rajada de k: k appends,
1 turno CX (hoje: k turnos).

## Módulos tocados (tabela corrigida) [REV]

| Arquivo | Mudança |
|---|---|
| `webhook.py` | pré-varredura do payload; dispatch de texto/áudio via `_buffered_bot_turn`; bypass por msg_type cru interactive; turno imediato com drain |
| `bot_service.py` | 1 linha no `_clear_bot_state` (limpar bot_buffers) — o resto intocado |
| `database_firestore.py` | helpers transacionais `append_bot_buffer` / `claim_and_drain_bot_buffer` / `flush_stale_bot_buffers` + limpeza em `return_contact_to_bot`/`release_lead_to_bot` |
| `config.py` | 2 envs |
| `main.py` | passo do flush no cron (com teto/orçamento) |
| `bot_sender.py` | helper de envio extraído do webhook e compartilhado pelo caminho ao vivo/cron |
| harness NOVO | ver §Testes — `sim_cx_flow` NÃO exercita o webhook |

## Testes obrigatórios [REV: harness certo]

Os cenários vivem no caminho do WEBHOOK — `tools/sim_cx_flow.py` chama
`process_bot_message_async` direto e não serve. Criar `tools/sim_buffer_flow.py`
no molde do `sim_reception_flow` (STORE mock + `import webhook as wh`), com
**sleep injetável** (`webhook._buffer_sleep = asyncio.sleep` no módulo,
mockado pra 0.05s no sim — senão a suíte leva minutos) e `asyncio.gather`
pros cenários concorrentes:

1. Rajada de 3 textos (payloads separados) → 1 turno, texto junto em ordem.
2. Rajada no MESMO payload → 1 turno (pré-varredura).
3. **Aceite LGPD com texto 3s depois → aceite reconhecido, consentimento
   gravado** (o cenário do bug crítico da revisão).
4. Interativa pós-consentimento com rajada pendente → drena antes, 2 turnos
   na ordem, zero dupla resposta.
5. Reentrega (was_dup) durante o sleep → sem re-append.
6. Claim vivo: mensagem durante turno → drain-loop responde, nada órfão.
7. Junto > 256 chars → trunca preservando o FIM.
8. Órfão (claim vencido + oldest_at velho) → flush do cron roda o turno;
   itens >10min descartados.
9. `BOT_BUFFER_SECONDS=0` → byte-a-byte igual ao atual.
10. Tenant builtin / contato com dono / bot_completed → buffer não arma.
11. Handoff no meio da rajada → buffer limpo, ciclo novo não herda texto.

## O que NÃO fazer

- NÃO tirar `was_dup` da frente do append (dupla resposta, 2026-08-14/18).
- NÃO bufferar pré-consentimento nem conteúdo interactive (quebra o aceite).
- NÃO usar `bot_states` pro buffer nem contador int como token.
- NÃO processar turno em BackgroundTasks pós-ACK (CPU throttling).
- NÃO afirmar números de scaling sem `gcloud run services describe`.
- NÃO mexer em `CX_DETECT_TIMEOUT_SECONDS`/read-retry aqui — mas se alguém
  mexer, o TTL do claim acompanha (é derivado, nunca hardcoded).
