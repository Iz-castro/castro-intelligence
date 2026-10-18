# Retomada pela Val: o que confirmar no seu resumo

**Para:** Izael (dev de IA) · **De:** Rafael · **Data:** 09/10/2026
**Contexto:** continuação de `docs/CX_RETOMADA_LOTE_DEV_IA.md`. Para eu ligar as partes do CRM que dependem da Val, preciso
que o seu resumo responda os cinco pontos abaixo. Cada um diz o que o CRM já faz, o que esperamos do agente e o que responder.

**Combinado sobre integração:** a Val e o CRM trocam informação só pelos parâmetros de sessão que voltam na resposta do
DetectIntent (`queryResult.parameters`). O CRM não lê o banco da Val. Qualquer forma de gravar do seu lado serve, desde
que o parâmetro apareça nessa resposta.

---

## 1. Desfecho do atendimento (`desfecho_bot`)

**Para que serve.** Tirar da retomada em lote quem já resolveu com a Val. No lote de 23/09, dos 71 pacientes que clicaram
Encerrar, 46 tinham conversado sobre agendamento com a Val. Eles receberam "seu atendimento não foi concluído" sem motivo.

**O que o CRM já faz, em produção desde 07/10.** A cada turno da Val, o CRM procura `desfecho_bot` nos parâmetros da
resposta. Se o valor for um dos quatro abaixo, grava no paciente com a data. Quando o paciente volta para a Val depois de um
atendimento humano, o CRM zera o desfecho sozinho.

| Valor | Quando |
|---|---|
| `link_enviado` | a Val mandou o link de agendamento |
| `agendado` | o paciente confirmou que agendou |
| `duvida_respondida` | dúvida simples resolvida, sem agendamento |
| `sem_interesse` | o paciente disse que não quer seguir |

**O que esperamos.** Que o desfecho seja gerado no serviço, de forma determinística, e não dependa da LLM lembrar. Por
exemplo: o roteador marca `link_enviado` quando devolve a rota de agendamento com o link do marcaconsultas. Valor sempre
escalar (texto), nunca struct.

**Dois limites do lado do CRM, para você saber.**
- O CRM não lê o desfecho no mesmo turno em que a Val faz o handoff. Na prática não faz falta: o paciente vai para a recepção.
- Se o paciente voltar para a Val em menos de 30 minutos, a sessão antiga ainda está viva e um desfecho antigo pode reaparecer.

**Responda.** Os nomes e valores finais, se mudaram. Quem grava: roteador, memória ou playbook. Se sai como texto simples.
A partir de qual environment.

---

## 2. Retomada (`origem`)

**Para que serve.** Quando o paciente do público Bot clicar Continuar no template, a Val deve retomar a conversa em vez de
recomeçar do zero.

**O que o CRM vai fazer.** No turno do clique, manda como texto o rótulo do botão, hoje `Continuar`, com o parâmetro
`origem = retomada_lote`, além dos parâmetros de horário de sempre. No turno seguinte manda `origem = null`. Essa parte do CRM
ainda não está ligada: até ela entrar, quem clica Continuar vai para a recepção.

**O que mudou depois que vi os serviços.** A memória da Val (`get_session_memory`) já devolve nome, especialidade, convênio,
resumo e orientação quando a sessão nova começa. Então o parâmetro `origem` virou opcional. O CRM vai mandar mesmo assim,
porque não custa nada.

**Responda.** Se a Val vai usar `origem` para uma saudação própria de retomada, ou se fica só com a memória.

---

## 3. Mídia com a Val (`midia_tipo`)

**Para que serve.** Hoje foto, documento, vídeo, figurinha ou localização enviados a um paciente que está com a Val não chegam
ao agente, e ninguém responde. Nenhum serviço fica sabendo dessas mensagens.

**O que o CRM vai fazer.** Rodar um turno da Val com o texto `[cliente enviou imagem]`, `[cliente enviou documento]`,
`[cliente enviou vídeo]`, `[cliente enviou gif]`, `[cliente enviou figurinha]`, `[cliente enviou localização]` ou
`[cliente enviou áudio]` (áudio que não foi transcrito), seguido da legenda quando houver, e o parâmetro `midia_tipo` com o
tipo em inglês (`image`, `document`, `video`, `gif`, `sticker`, `location`, `audio`). No turno seguinte, `midia_tipo = null`.
Reação e contato compartilhado não geram turno. Isso entra atrás de uma chave própria, porque muda o comportamento da Val
para todos os pacientes, não só na retomada.

**O que esperamos.** A Val não vê o conteúdo. Ela nunca deve dizer que viu a imagem nem tratar o colchete como pergunta.
Sugestão: imagem ou documento que pareça exame, pedido médico ou laudo vai para a recepção pelo handoff de sempre, por ser
dado de saúde; nos outros casos, a Val pede que o paciente escreva o que precisa.

**Responda.** O comportamento escolhido e se exame ou documento médico vai para a recepção.

---

## 4. Publicação

**Para que serve.** A produção da Varizemed roda num environment publicado do agente. Mudança no Draft só chega lá quando
trocamos o environment.

**O que esperamos.** O teste no `varizemed-test`, no Draft, cobrindo os itens 1 a 3. No simulador do console dá para
preencher os parâmetros de sessão antes da mensagem. Depois, um environment novo publicado.

**Responda.** O ID do environment novo, o rótulo da versão e o que foi testado. Com isso eu troco `environment_id` e
`core_version` da `varizemed` no mesmo write, com conferência antes e depois.

---

## 5. Nome de exibição da Hubloc

**Situação conhecida.** O número da Hubloc (+55 31 3351-7604) segue limitado na Meta até o nome ser aprovado. O pedido
"Hub Loc Locações" estava em análise, e a orientação foi pedir exatamente "Hub Loc", como está no site. Os IDs para o suporte
estão no documento anterior. A reabertura em lote da Hubloc está desligada no CRM até isso resolver.

**Responda.** O que o suporte respondeu, o número do atendimento, se houver, e o próximo passo combinado com eles.

---

## Modelo de resposta

```text
1. Desfecho: nome/valores = ... | quem grava = ... | escalar = sim/não | a partir do environment = ...
2. Retomada: uso o param origem = sim/não | saudação = ...
3. Mídia: comportamento = ... | exame/documento médico vai para a recepção = sim/não
4. Publicação: environment = ... | versão = ... | testado no varizemed-test = ...
5. Hubloc: resposta do suporte = ... | atendimento nº = ... | próximo passo = ...
```
