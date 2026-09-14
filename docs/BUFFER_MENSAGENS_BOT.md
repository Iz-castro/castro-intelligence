# Buffer de mensagens do bot (Val) — debounce de mensagens picadas

> **Status em 2026-09-14: IMPLEMENTAÇÃO REVISADA E MERGEADA NO DEVELOP; DEPLOY
> COM KILL-SWITCH DESLIGADO.** `BOT_BUFFER_SECONDS=0` mantém todos os tenants
> no fluxo anterior; ativação começa pelo `varizemed-test` via
> `scripts/set_tenant_buffer.py` (§Config). O v1 deste desenho passou por revisão
> adversarial de desenho (21 achados) e este v2 incorpora todas as correções —
> os pontos **[REV]** vêm de lá. A IMPLEMENTAÇÃO passou por segunda revisão
> adversarial em 2026-09-14 (9 revisores Opus + 3 refutadores por achado:
> 46 brutos → 25 únicos → 7 confirmados, todos corrigidos; pontos **[REV-IMPL]**,
> ver §Revisão da implementação). Não "simplifique" nada de volta.
> Gates locais completos: `sim_bot_flow` 56 / `sim_cx_flow` 173 /
> `sim_reception_flow` 173 / `sim_buffer_flow` 52 / `sim_picker_v21` 46.

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
  intocado, mensagem a mensagem. **[REV-IMPL canário 2026-09-14]** "estado"
  aqui segue a MESMA regra de hidratação do `bot_service`
  (`lgpd_consent_resolved`): estado `True` vale; estado `False` nunca vale;
  estado AUSENTE vale se o contato guarda a prova (`lgpd_consent=True`, não
  revogado, `policy_version` vigente). Sem isso, após `release_lead_to_bot`
  (que recria `bot_states` sem `lgpd_*` quando o handoff apagou o doc) a 1ª
  mensagem do ciclo novo rodava turno direto e a 2ª virava resposta dupla.
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
items: [{"text": str, "ts": iso_da_Meta, "n": int, "at": iso_do_append}]
        # ordem do join = (ts, n); IDADE (descarte 10min) = at [REV-IMPL F05]
token: str (uuid4, rotacionado a cada append)         # NUNCA contador int
claimed_at: iso | null   # identidade opaca do claim
claim_hb: iso | null     # heartbeat, renovado a cada drain [REV-IMPL F01]
oldest_at: iso | null    # append mais antigo pendente (flush do cron) [REV]
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
   **[REV-IMPL F01]** O TTL cobre UM turno: o claim tem identidade
   (`claimed_at`) e heartbeat (`claim_hb`) e está vivo se QUALQUER um estiver
   dentro do TTL; cada drain do passo 5 renova `claim_hb`. Sem isso, 3 turnos
   lentos somados venceriam o claim com o detentor em voo e outro ator
   dispararia um 2º DetectIntent na mesma sessão. Fonte única do TTL:
   `database_firestore.bot_buffer_claim_ttl_seconds()`.
5. **Turno + drain-loop** **[REV]**: junta por `(ts, n)` com `"\n"`,
   **trunca a 256 preservando o FIM** (o conector corta pela CABEÇA —
   `bot_engine_dialogflow.py:45/222` — o corte útil é no webhook, com log),
   chama `process_bot_message_async`, envia. Antes de soltar o claim:
   re-lê `items`; se chegou item novo durante o turno, drena e roda OUTRO
   turno (loop com teto de ~3 iterações). Só então limpa `claimed_at`.
   **[REV-IMPL F02/F12]** Além do teto por iterações há um **orçamento de
   parede por request** (`_BUFFER_REQUEST_BUDGET_SECONDS`, 240s < 300s do
   Cloud Run): um turno novo (claim do sleeper ou drain do detentor) só começa
   se ainda couber um turno no PIOR caso (`2*CX_DETECT_TIMEOUT_SECONDS + 15`).
   Sem orçamento, o detentor sai do loop SEM drenar (drenar sem turno perderia
   itens) e o sleeper devolve `no_budget` sem claimar: os itens ficam no doc
   com token intacto para o próximo handler/cron, com warning no log.
6. **Try/except no caminho INTEIRO** **[REV]**: qualquer exceção que escape
   vira pending_webhook_event e o retry re-entra com `was_dup=True` = bot
   pulado pra sempre (mesmo racional do bloco atual `webhook.py:1061-1075`).
   Degrada só a resposta do bot; `finally` (soltar claim) dentro do try.

Itens com **`at` (instante do append)** mais velho que **10min são
DESCARTADOS no drain** (com log) **[REV]**: `return_contact_to_bot`/
`release_lead_to_bot` não conhecem o buffer e um ciclo novo não pode
concatenar texto do atendimento anterior. **[REV-IMPL F05]** A idade NÃO usa
o `ts` da Meta: entrega atrasada ou reprocesso de `pending_webhook_events`
chegaria "vencida" e o bot nunca responderia. O `ts` da Meta serve só à
ordenação `(ts, n)`.
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
- **teto por tick** (10 contatos) e orçamento de tempo **GLOBAIS do request**
  (somados entre tenants, não por tenant): claim novo só antes de 150s desde a
  entrada do request e **1 turno por contato** (`max_drain_loops=1`), rodando
  DEPOIS do trabalho existente do cron (expire/close não podem ser
  sacrificados; request do cron também morre em 300s) **[REV-IMPL F03]**;
- pra ENVIAR é preciso resolver canal/token/phone_id pelo contato (padrão de
  `main.py:3958-3968`); extrair helper de envio compartilhado com
  `_send_bot_reply` (webhook.py:279) em vez de duplicar.

## Config e kill-switch

- `config.py`: `BOT_BUFFER_SECONDS` (env, **default 0 = DESLIGADO** — deploy
  não muda nenhum tenant), `BOT_BUFFER_MAX_CHARS=256` (**grampeado a 256**:
  é o limite de `queryInput.text` do CX e o conector corta pela CABEÇA —
  valor maior descartaria o FIM que o webhook preserva **[REV-IMPL F19]**).
- Override por tenant: `settings.ai.buffer_seconds` (default no READ, nunca
  backfill). Ligar/desligar sem deploy:
  `.venv\Scripts\python.exe -m scripts.set_tenant_buffer --tenant varizemed-test --seconds 10 --yes`
  (dry-run sem `--yes`; `--seconds 0` = kill-switch; cache de tenants ≤60s).
- `varizemed-test` primeiro, sempre; teste real pelo número de teste; depois
  o PO decide a varizemed real.

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
| `scripts/set_tenant_buffer.py` | liga/desliga por tenant sem deploy (dry-run default) |
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
12. Áudio: transcrições entram no mesmo debounce.
13. Último candidato estrutural do payload falha (áudio sem transcrição /
    mid duplicada) → o append anterior não fica órfão.
14. Contratos transacionais REAIS (`to_wrap` com transação fake): token
    rotaciona, `n` desempata, superseded, busy, drain em voo, **heartbeat
    mantém o claim vivo após o TTL da identidade, takeover só com heartbeat
    vencido (8b), detentor antigo perde drain/release** [REV-IMPL F01/F06].
15. Entrega atrasada (ts da Meta 20min atrás) → turno roda [REV-IMPL F05].
16. Orçamento de parede esgotado → detentor não drena, item novo preservado,
    cron roda 1 turno por contato, sleeper sem orçamento não claima
    [REV-IMPL F02/F03/F12].
17. Interativa com claim vivo além da espera → clique roda turno direto.
18. Kill-switch com a config real do deploy (chave ausente + env 0).

## Revisão da implementação (2026-09-14) [REV-IMPL]

Workflow de 9 revisores Opus (conformidade com o desenho, LGPD/interativas,
concorrência/claims, exceção/ACK, persistência Firestore, cron de flush,
kill-switch/regressão, cobertura do harness, integração no webhook) + dedup +
3 refutadores por achado (código real / cenário de runtime / escopo e
severidade) + crítico de completude. 46 achados brutos → 25 únicos →
**7 confirmados**, todos corrigidos nesta branch:

| # | Achado | Correção |
|---|---|---|
| F01 | `claimed_at` nunca renovado no drain-loop: 3 turnos lentos > TTL → claim roubado, 2 turnos CX concorrentes | heartbeat `claim_hb` renovado a cada drain; claim vivo = max(identidade, heartbeat) dentro do TTL |
| F02 | sem orçamento de parede: janela + 30s + 3 turnos > 300s do Cloud Run | `_BUFFER_REQUEST_BUDGET_SECONDS` (240s) por request; turno novo só se couber o pior caso; sleeper devolve `no_budget` |
| F03 | flush do cron com orçamento reiniciado POR TENANT e cego à duração do turno | orçamento global do request (claim novo só < 150s), teto de 10 contatos global, `max_drain_loops=1` |
| F05 | idade do item pelo `ts` da Meta: entrega atrasada/reprocesso nascia vencido e nunca recebia turno | campo `at` (instante do append) para idade e `oldest_at`; `ts` só ordena |
| F06 | mock do harness ignorava TTL: takeover de claim vencido nunca testado | mocks espelham o real (`_bot_buffer_live_claim`, filtro real); cenário 14 estendido com relógio avançado |
| F12 | no teto do drain-loop o detentor liberava sem drenar e o sleeper já tinha desistido | residual aceito pelo desenho (teto [REV]); agora com log explícito e nunca drena sem rodar turno |
| F19 | `BOT_BUFFER_MAX_CHARS` sem teto: >256 invertia a regra de preservar o FIM | grampeado a 256 em `config.py` |

Refutados (18), com razões no transcript do workflow — entre eles: flush do
cron quase no-op (trade-off explícito deste desenho: cron */30 × cutoff 5min ×
descarte 10min), kill-switch "falha aberto" (é a semântica documentada de
override), turno interativo direto após 30s de claim vivo (não duplica
resposta: o clique nunca está no buffer). Também endurecido: a pré-varredura
do payload roda sob try/except (erro = payload sem buffer, nunca exceção no
wrapper) e o TTL tem fonte única (`bot_buffer_claim_ttl_seconds`).

## Checklist de ativação (canário no `varizemed-test`) [REV-IMPL crítico]

Fronteiras que a revisão do código NÃO cobre e que o crítico de completude
exigiu antes de LIGAR (o deploy desligado não depende delas):

1. **Observabilidade:** `scripts/_diag_bot_buffers.py --tenant varizemed-test --watch 5`
   (read-only, sem texto do paciente) aberto durante o canário; filtro
   `[BOT-BUFFER]` no Cloud Logging (uma linha por mensagem: `turno N com k
   item(ns)`, `handler sem turno (superseded|busy|missing)`, `consentimento LGPD
   nao resolvido; turno direto`); `bot_buffer_items_discarded` no retorno do cron.
   Nos logs de request do Cloud Run, o `timestamp` é o INÍCIO e `latency` a
   duração — um handler superado aparece com ~10s, o detentor com janela +
   turno(s).
2. **Ligar:** `scripts/set_tenant_buffer.py --tenant varizemed-test --seconds 10 --yes`
   (cache de tenant ≤60s). Roteiro: 3 textos em ~4s → 1 resposta com o texto
   junto e doc `bot_buffers/{contato}` apagado; handoff no meio da rajada;
   áudio + texto; clique em botão LGPD antigo pós-consentimento; kill
   (`--seconds 0`) medindo o retorno ao imediato (≤60s).
3. **Whisper síncrono:** `transcribe_audio_bytes` segura o event loop da
   instância (`--workers 1`); enquanto transcreve, sleepers/polls de OUTROS
   contatos não acordam (janela e espera escorregam; o orçamento de parede
   devolve os itens ao cron em vez de estourar os 300s). Aceito para o canário;
   follow-up antes da varizemed real: `await asyncio.to_thread(transcribe_audio_bytes, ...)`.
4. **Capacidade (2026-09-14):** `containerConcurrency=8`, `maxScale=10`,
   `minScale=1`, `timeoutSeconds=300`. Cada mensagem elegível ocupa um slot por
   janela + espera; NÃO ativar no mesmo dia de lote de reabertura/campanha de
   template (pico simultâneo por construção). Observar p95 de latência e
   `instance_count` no canário.
5. **Rollback/desativação:** antes de promover uma revisão PRÉ-buffer
   (≤ `castro-crm-00097-fd4`) com o buffer ligado: `--seconds 0`, esperar >60s
   + 1 tick do cron (drena os órfãos) e conferir `_diag_bot_buffers` vazio — a
   revisão velha não conhece a coleção e o texto ficaria sem resposta.
   Revisões pós-buffer coexistem sem problema (estado no Firestore).
6. **LGPD:** `bot_buffers` guarda texto bruto do paciente por segundos (normal)
   até ~35min (órfão). Pendências: `scripts/wipe_channel_data.py` e o checklist
   de purge de número de teste não cobrem a coleção (derivar por `contact_id`);
   atualizar RoPA/RIPD com coleção, finalidade e retenção; avaliar TTL policy
   do Firestore em `oldest_at` como rede independente do cron.
7. **Semântica temporal:** parâmetros de horário comercial são calculados no
   instante do turno (drain), não da mensagem; irrelevante na janela de 10s,
   possível na recuperação pelo cron (≤35min) na borda do expediente — aceito.
8. **Retry de pending pela UI admin:** re-entra pelo caminho com debounce
   (janela + turno dentro do request do admin); com F05 a mensagem atrasada
   não nasce vencida. Aceito.

Decisão registrada em `docs/decisions/0012-buffer-debounce-bot-cx.md`.

## O que NÃO fazer

- NÃO tirar `was_dup` da frente do append (dupla resposta, 2026-08-14/18).
- NÃO bufferar pré-consentimento nem conteúdo interactive (quebra o aceite).
- NÃO usar `bot_states` pro buffer nem contador int como token.
- NÃO processar turno em BackgroundTasks pós-ACK (CPU throttling).
- NÃO afirmar números de scaling sem `gcloud run services describe`.
- NÃO mexer em `CX_DETECT_TIMEOUT_SECONDS`/read-retry aqui — mas se alguém
  mexer, o TTL do claim acompanha (é derivado, nunca hardcoded).
