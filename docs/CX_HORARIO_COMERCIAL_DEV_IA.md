# Val — aviso de fora do expediente (spec para o Dev IA)

**Data:** 2026-08-09 · **Agente:** `5fa69ea1-bc68-445b-9d20-d72265aaaf36`
(projeto `castro-ia`, região `us-central1`) · **Tenant:** `varizemed`

> **Status (10/08):** backend **implementado** (`business_hours.py`; horários
> fixos no código nesta fase — a tela de admin com calendário de feriados é a
> fase 2). Os dois parâmetros chegam em **toda** chamada `detectIntent` assim
> que a revisão subir — o Rafael te confirma a hora. Seu lado (playbook) pode
> ser feito em paralelo: parâmetro ausente numa condição CX é só "false".
>
> **Status (21/08):** a fase 1 está **em produção** desde 10/08 — os dois
> parâmetros vão em **toda** chamada `detectIntent`. A fase 2 (tela de admin com
> feriados) continua pendente. ⚠ A tabela de ambientes do §5 envelheceu: a
> clínica real (`varizemed`) roda hoje o environment
> `22390163-6bbc-47b5-a25a-e53eb3363d8f` (`val-5.0.3`, 21/08 15:50 BRT) e o
> `varizemed-test` deve estar no **Draft** — histórico das trocas em
> `docs/deploy/TROCAR_ENVIRONMENT_VAL.md`.

Complementa o `docs/CX_AGENTE_PENDENCIAS_DEV_IA.md` (pendências de 30/07).

---

## 1. O problema que isso resolve

Lead que procura a clínica fora do expediente (noite, fim de semana, feriado)
pede atendimento, a Val faz o handoff — e some do radar dele. Ninguém responde
até o próximo dia útil e ele fica sem saber se alguém vai responder.

O lado do CRM já foi resolvido em **09/08**: o lead agora **fica na fila da
recepção** esperando, em vez de ser devolvido ao bot pelo fechamento automático.
O que falta é a Val **avisar** o lead do horário de retorno.

## 2. O contrato: dois parâmetros novos na sessão

Hoje o CRM já manda em toda chamada `detectIntent`:

```
user_id       "+5531999998888"
tenant_id     "varizemed"
lgpd_consent  true
```

Passará a mandar também:

| parâmetro | tipo | exemplo | significado |
|---|---|---|---|
| `fora_do_expediente` | boolean | `true` | o momento da mensagem está fora do horário configurado (inclui fim de semana; feriados entram na fase 2) |
| `retorno_previsto` | string | `"segunda-feira às 8h"` | texto **pronto** com o próximo horário de abertura |

Valores exatos que o `retorno_previsto` produz (interpolar sem mexer):

| situação (Varizemed) | `fora_do_expediente` | `retorno_previsto` |
|---|---|---|
| terça 10:00 (aberto) | `false` | `""` (vazio — não usar) |
| segunda 07:32 | `true` | `"hoje às 8h"` |
| terça 19:00 | `true` | `"amanhã às 8h"` |
| sexta 17:30 | `true` | `"segunda-feira às 8h"` |
| sábado / domingo | `true` | `"segunda-feira às 8h"` (domingo à noite vira `"amanhã às 8h"`) |

Quando `fora_do_expediente` for `false`, o `retorno_previsto` vem **vazio** de
propósito — a mensagem de fora-do-horário não deve existir nesse ramo.

O agente **não conhece o horário** e não deve tentar deduzi-lo. Quem calcula é o
CRM, a partir da configuração que a própria clínica edita na tela de
Administração — inclusive os feriados que ela decide fechar.

## 3. Regra de ouro: interpolar, nunca escrever a hora

A mensagem tem que usar `$session.params.retorno_previsto` como variável.

✅ `"Nosso atendimento retorna ${retorno_previsto}. Assim que abrirmos, nossa equipe te responde por aqui."`

❌ `"Nosso atendimento retorna segunda-feira às 8h."`

Motivo: o horário é editável pelo admin da clínica **sem deploy e sem mexer no
agente**. No dia em que ela mudar (feriado, recesso, mudança de expediente), o
booleano continua correto e a frase escrita à mão passa a mentir para o
paciente — sem ninguém perceber.

## 4. Onde ramificar

No passo da **transferência** (Step 6 do playbook). Quando `fora_do_expediente`
for `true`, acrescentar a informação de retorno à mensagem de transferência.

> ⚠ **ACRESCENTE uma frase; não reescreva as existentes.**
>
> O CRM detecta o handoff por **dois** sinais: o parâmetro `handoff_request` e,
> como rede de segurança, o **texto** das frases imutáveis de transferência
> (`_DEFAULT_HANDOFF_TEXT_HINTS` em `bot_service.py`):
>
> - `"estou transferindo nossa conversa para a equipe de atendimento"`
> - `"deixei sua solicitação marcada como prioridade"`
>
> Já houve caso real em produção do agente transferir **sem** setar
> `handoff_request` — nessa hora só o texto salvou o lead de ficar preso no bot.
> Se essas frases forem reescritas, essa rede cai silenciosamente. Se a mudança
> for inevitável, avise: o CRM tem override por tenant
> (`settings.ai.handoff_text_hints`) e a gente ajusta junto, no mesmo dia.

> **Isso já aconteceu — teste do `val-5.0.1` em 09/08.** A mensagem de
> prioridade foi reescrita de *"deixei sua solicitação marcada como
> prioridade"* para *"Registrei sua solicitação como prioridade no sistema.
> Nossa equipe de atendimento humano entrará em contato…"*, e **nenhum** dos
> dois hints casava mais. O handoff do teste só funcionou porque o parâmetro
> `handoff_request` veio setado; se ele faltasse, o lead teria ficado preso no
> bot, sem erro nem alerta.
>
> Já cobrimos do nosso lado: a lista de hints virou aditiva e passou a aceitar
> as duas redações (`registrei sua solicitacao como prioridade` e `equipe de
> atendimento humano entrara em contato`), com teste travando o comportamento.
> **Mas o combinado continua valendo:** ao mexer nessas frases, avise — a rede
> só protege o que ela conhece.

Sugestão de forma (mantendo a frase existente intacta):

```
[frase de transferência atual, sem alteração]
No momento estamos fora do horário de atendimento. Nosso atendimento retorna
${retorno_previsto} e nossa equipe te responde por aqui assim que abrirmos.
```

## 5. Ambientes — conferido em 09/08

O tenant real e o de teste apontam para lugares **diferentes** do mesmo agente:

| tenant | `environment_id` | o que exercita |
|---|---|---|
| `varizemed` (clínica real) | `6bdfaeed-6dd3-445c-b32a-4e1f85ab32dd` (`val-5.0`) | ambiente **publicado** |
| `varizemed-test` | *(vazio)* | o **DRAFT** do agente |

Consequência prática, e é o que importa no seu fluxo:

- Editar no console mexe no **draft** → chega **na hora** ao `varizemed-test`,
  e **não** chega à clínica real.
- Para chegar à clínica, é preciso **publicar uma versão** e apontar o tenant
  para o environment correspondente (mudança de config no CRM, do nosso lado).

Existe um environment mais novo já publicado, `75028a25-7094-43d0-a033-9a2cb90e7988`
(`val-5.0.1Atualização`, de 08/08), que sobe `val_greeting` v2, `val_router` v3 e
o tool `VarizemdRouter` v2. **A produção ainda não aponta para ele** — em 09/08 o
`varizemed-test` foi apontado para lá e o handoff foi validado.

**Nota sobre o aviso de horário no `val-5.0.1`:** a mensagem nova já termina com
*"assim que estiver disponível, no próximo horário de atendimento"*. É meio
caminho do que este documento especifica — falta ela ser **condicional**
(hoje sai também às 10h de uma terça, quando a clínica está aberta) e dizer
**qual** é o horário, vindo de `retorno_previsto`.

## 6. Como testar

1. Editar no draft.
2. Mandar mensagem real pelo WhatsApp do `varizemed-test` — o draft responde na hora.
3. Conferir, em ordem:
   - a mensagem de retorno sai com o horário **certo** e vindo do parâmetro;
   - dentro do expediente a frase **não** aparece;
   - o handoff continua sendo detectado pelo CRM (o lead tem que cair na aba
     **Recepção**; se ficar preso na aba Bot, o handoff não foi reconhecido);
   - os params continuam **escalares**, não structs (ver pendência 1 do doc de 30/07).

## 7. Horário configurado (definido pela clínica em 09/08)

| dia | expediente |
|---|---|
| segunda a quinta | 08:00 – 18:00 |
| sexta | 08:00 – 17:00 |
| sábado e domingo | fechado |

Sem intervalo de almoço: sempre fica alguém de plantão. Feriados: a clínica
marca os dela na tela de Administração do CRM (nacionais por nome, mais as
datas municipais/recessos que ela quiser).

Fuso fixo `America/São_Paulo`.

## 8. O que NÃO muda

- **Roteamento continua igual.** Fora do expediente o handoff acontece
  normalmente e o lead fica na fila da recepção esperando o dia útil. A mudança
  é só de comunicação.
- **Nada é enviado ao lead pelo CRM** por causa disso — quem fala é a Val.
- A Hubloc não usa o agente CX (bot builtin), então o aviso dela é montado no
  backend com o mesmo cálculo. Não te afeta.
