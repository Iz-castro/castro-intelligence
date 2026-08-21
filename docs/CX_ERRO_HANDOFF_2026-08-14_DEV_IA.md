# Val — erro no passo da transferência ("Sorry something went wrong.") — para o Dev IA

**Data:** 2026-08-14 · **Agente:** `5fa69ea1-bc68-445b-9d20-d72265aaaf36`
(projeto `castro-ia`, `us-central1`) · **Tenant afetado:** `varizemed` (clínica real)

> **Atualização 2026-08-21:** resolvido do lado do agente — o environment
> `834d5241-5337-4848-91a5-1479c6fcdc9b` (`val-5.0.12`, "correção do erro
> 'Sorry something went wrong'") entrou em 14/08 13:40 BRT. A produção hoje roda
> `22390163-6bbc-47b5-a25a-e53eb3363d8f` (`val-5.0.3`, 21/08 15:50 BRT) —
> histórico das trocas em `docs/deploy/TROCAR_ENVIRONMENT_VAL.md`. A blindagem
> descrita no §5 (reenvia 3× e handoff no 4º) está em produção (commit
> `4bc5d79`); o convite do fim do §5 continua de pé: se você definir uma frase
> de erro customizada, manda a frase EXATA.

**Resumo em uma linha:** hoje de manhã o agente está instável e, no pedido de
atendimento humano, respondeu ao lead a frase de erro embutida do Dialogflow —
**"Sorry something went wrong."**, em inglês — sem setar `handoff_request`. O
erro é **dentro do agente** (playbook/tool); o CRM entregou e recebeu o turno
como "sucesso".

---

## 1. Contexto de versão

A produção roda o **`val-5.0.11`** (environment `39408565-9cb8-4cdd-8e5c-2c5493b2ab6f`)
desde **10/08 16:35 BRT**. Diferença única contra o `val-5.0.1` anterior:
`val_router` **v3 → v4** (a correção de texto que você publicou 10/08 16:26 BRT).
Flow, `val_greeting` e os dois tools estão nas MESMAS versões do 5.0.1.

## 2. Evidência (timestamps em UTC; BRT = −3)

**Sessão do teste do Rafael** (número de teste dele, final 0484 — a sessão no
console é o número só-dígitos; ele te confirma o número completo):

| UTC | o que houve |
|---|---|
| 14:48–14:51 | fluxo LGPD completo ok (aviso → recusa → reconsentimento → saudação personalizada da Val) |
| 14:51:52 | inbound **"equipe por favor"** |
| ~14:51:5x | 1ª chamada DetectIntent **falhou** (o conector re-tentou — log `tentativa=2`) |
| 14:52:16 | 2ª chamada voltou **HTTP 200** com `reply_text = "Sorry something went wrong."` e **sem** `handoff_request` |
| 14:52:17 | o CRM repassou o texto ao lead (não temos como saber que 200+esse texto = erro) |

**Não foi caso isolado.** Janela de instabilidade observada nos logs do CRM
desde **~14:12 UTC (11:12 BRT)** de hoje:

- sessão `…1919` — 14:11–14:12: turnos com retry (`tentativa=2`);
- sessão `…4320` (contato 192) — 14:25–14:27: dois turnos com retry e, aí sim,
  **duas falhas consecutivas de verdade** → o CRM acionou o handoff-de-falha
  ("Bot IA indisponível", lead na Recepção como FRIO);
- sessão do Rafael — 14:51–14:52 (acima).

## 3. Onde olhar (lado do agente — não temos acesso)

1. **Console do Dialogflow → Conversation history** da sessão do número de
   teste, nos horários acima — deve mostrar QUAL passo/tool estourou;
2. **Logs das Cloud Functions** `VarizemdRouter` e `ValMemory` no `castro-ia`
   na janela 14:00–15:00 UTC de hoje (timeout? 5xx? quota?);
3. O que exatamente mudou no `val_router` v4 — e se os erros começaram em
   10/08 à tarde (publicação) ou só HOJE (aí a suspeita vira tool/LLM/quota,
   que são os mesmos do 5.0.1).

## 4. Hipóteses, na nossa ordem de suspeita

- **Tool `VarizemdRouter` falhando/timeout** no turno da transferência (é o
  mesmo v2 do 5.0.1 — se for isso, rollback de environment NÃO resolve);
- **Algo no `val_router` v4** (se o histórico mostrar erro só pós-10/08);
- LLM/quota/RAI do próprio agente.

Nota pra descartar rápido: desde 10/08 ~13h BRT o CRM manda 2 session params
novos em todo turno (`fora_do_expediente` bool, `retorno_previsto` string —
spec `docs/CX_HORARIO_COMERCIAL_DEV_IA.md`). Rodaram 4 dias sem incidente e
param extra ignorado não derruba playbook, mas se o v4 referencia algum
parâmetro novo, vale conferir o nome.

## 5. O que o CRM já faz do nosso lado (independente da causa)

Blindagem no conector (definida com o Rafael em 14/08): quando o agente
devolve uma frase de erro conhecida com HTTP 200, o CRM **reenvia a MESMA
mensagem do lead até 3×** (transparente — o lead não vê nada). Se algum
reenvio vier limpo, o fluxo segue normal. No **4º erro consecutivo**, handoff
pra Recepção com mensagem genérica em pt-BR ("Nosso agente virtual está
indisponível no momento. Um operador humano vai continuar o seu atendimento
por aqui."). A frase de erro **nunca** chega ao lead.

Hoje a lista de frases reconhecidas é `"Sorry something went wrong."` (e a
variante "Desculpe, algo deu errado."), comparadas por igualdade da resposta
inteira — resposta legítima que *cite* o trecho no meio não dispara.

**Pra sua frase de erro customizada:** quando você definir o texto que o
agente vai responder em erro, me manda a frase EXATA — ela entra em
`settings.ai.cx_error_phrases` do tenant, **sem deploy**, e o mesmo
reenvia-3×-depois-handoff passa a valer pra ela. Importante: precisa ser uma
frase FIXA (sem variação do LLM) e que a Val nunca usaria numa resposta
normal. Isso NÃO conserta o agente — só degrada com dignidade.

## 6. O que precisamos de você

1. Diagnóstico pelo histórico/logs (itens do §3) e o que mudou no v4;
2. Um veredito: **vale rollback pro `val-5.0.1`** (`75028a25`) enquanto
   investiga? A troca do nosso lado leva 60s — mas se a causa for o tool,
   rollback só mascara;
3. Se publicar correção: environment novo + o ID pra gente apontar (mesmo
   fluxo de sempre; o `varizemed-test` está no **Draft** pra você testar
   antes).
