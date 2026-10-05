# Retomada em lote pela Val: o que precisamos do agente

**Para:** Izael (dev de IA) · **De:** Rafael · **Data:** 05/10/2026
**Status:** CRM em implementação. Tudo o que depende do agente entra atrás de chaves desligadas e só liga depois que o
playbook estiver publicado.
**Também neste documento:** o nome de exibição da Hubloc, para falar com o suporte da Meta hoje (seção final).

---

## Por que isso agora

O CRM vai reabrir conversas em lote para dois públicos: **Recepção** (pacientes em atendimento humano) e **Bot**
(pacientes que conversaram com a Val, aceitaram a LGPD e pararam de responder).

Em 23/09 rodamos o primeiro lote do público Bot por script, com o template `varizemed_retomada_generica_utility_v1`
("Seu atendimento iniciado em {{2}} não foi concluído. Ainda deseja continuar?", botões [Continuar] e [Encerrar atendimento]).

| Resultado em 24h | Quantidade |
|---|---|
| Templates enviados | 368 |
| Lidos | 229 |
| Clicaram Continuar | 19 |
| Clicaram Encerrar | 71 |
| Responderam com texto ou áudio | 17 |
| Falhas de envio | 0 |

Dois aprendizados que viram pedidos para o agente:

1. Hoje o Continuar leva o paciente para a recepção. A decisão é que, no público Bot, **Continuar volte para a Val**.
2. Dos 71 que clicaram Encerrar, **46 já tinham conversado sobre agendamento com a Val** e 10 receberam o link
   `marcaconsultas.com.br/Varizemed`. Muitos já tinham marcado consulta. O CRM não tem como saber disso, então mandou
   "seu atendimento não foi concluído" para quem já tinha resolvido.

Daí os três itens abaixo. Os três seguem o mesmo mecanismo dos parâmetros de horário (`fora_do_expediente`,
`retorno_previsto`): o CRM manda parâmetros de sessão em `queryParams.parameters` do DetectIntent e lê os parâmetros de
sessão que voltam na resposta.

---

## 1. Turno de retomada: parâmetro `origem`

**O que o CRM vai fazer.** Quando um paciente do público Bot clicar **[Continuar]** no template, o CRM chama o
DetectIntent com:

| Campo | Valor |
|---|---|
| Texto do turno | o rótulo do botão clicado, hoje `Continuar` |
| `origem` | `retomada_lote` |
| `fora_do_expediente`, `retorno_previsto` | como em todo turno |

No turno seguinte do mesmo paciente, o CRM manda `origem = null`, para o parâmetro não ficar preso na sessão.

**Estado em que a Val encontra o paciente.**
- A sessão do CX já expirou: o paciente sumiu há dias. Para o agente, é uma sessão nova.
- O consentimento LGPD já foi dado. O CRM só manda o template para quem aceitou, e o portão da LGPD continua no CRM,
  antes do agente.
- O paciente acabou de ler o template e tocou em Continuar. Ele não escreveu nada além disso.

**O que precisamos.** Quando `origem == "retomada_lote"`:
- Cumprimentar quem voltou e perguntar como pode ajudar, sem a apresentação completa do primeiro contato.
- Não repetir o texto do template.
- Respeitar o horário como hoje: fora do expediente, avisar com `retorno_previsto`.

Exemplo de resposta esperada: *"Que bom te ver de novo por aqui! Me conta como posso te ajudar a seguir com o seu
atendimento."*

---

## 2. Mídia com a Val: texto marcado e parâmetro `midia_tipo`

**Hoje.** Foto, documento, vídeo, figurinha ou localização enviados por um paciente que está com a Val **não chegam ao
agente**, e o paciente fica sem resposta. Só texto e áudio transcrito chegam.

**O que o CRM vai fazer.** Para essas mensagens, o CRM roda um turno do agente com:

| Recebido | Texto do turno | `midia_tipo` |
|---|---|---|
| Imagem | `[cliente enviou imagem]` | `image` |
| Documento | `[cliente enviou documento]` | `document` |
| Vídeo | `[cliente enviou vídeo]` | `video` |
| GIF | `[cliente enviou gif]` | `gif` |
| Figurinha | `[cliente enviou figurinha]` | `sticker` |
| Localização | `[cliente enviou localização]` | `location` |
| Áudio sem transcrição | `[cliente enviou áudio]` | `audio` |

Se a mídia vier com legenda, o texto do turno é o marcador seguido da legenda, por exemplo
`[cliente enviou imagem] segue meu pedido médico`. Reações e contatos compartilhados não geram turno. No turno seguinte o
CRM manda `midia_tipo = null`.

**O que precisamos.**
- A Val não vê o conteúdo. Ela nunca deve dizer que viu a imagem nem tratar o colchete como uma pergunta literal.
- Sugestão de comportamento, a decidir por você no playbook: imagem ou documento que pareça exame, pedido médico ou
  laudo vai para a recepção pelo handoff de sempre, porque é dado de saúde; nos demais casos, pedir que o paciente
  escreva em texto o que precisa.

---

## 3. Desfecho do atendimento: parâmetro `desfecho_bot`

**Por quê.** Para o CRM parar de mandar retomada a quem já resolveu com a Val.

**Contrato.**
- Parâmetro de sessão `desfecho_bot`, **escalar (string), nunca struct**, setado no turno em que acontece.
- Valores:

| Valor | Quando |
|---|---|
| `link_enviado` | a Val mandou o link de agendamento |
| `agendado` | o paciente confirmou que agendou |
| `duvida_respondida` | dúvida simples resolvida, sem agendamento |
| `sem_interesse` | o paciente disse que não quer seguir |

- Vale o último valor setado na sessão.
- O CRM lê o parâmetro da resposta do DetectIntent, grava no contato e tira esse paciente da retomada do público Bot.
  Quando o paciente volta para a Val depois de um atendimento humano, o CRM zera o desfecho sozinho. O agente não precisa
  limpar nada.

Se preferir outros nomes ou valores, me avise antes de publicar, porque o CRM vai ler exatamente estes.

---

## Como testar

No `varizemed-test`, no Draft. No simulador do console dá para preencher os parâmetros de sessão antes de mandar a mensagem.

| Cenário | Parâmetros | Mensagem | Esperado |
|---|---|---|---|
| Retomada | `origem = retomada_lote` | `Continuar` | saudação de retorno, sem apresentação completa |
| Retomada fora do horário | `origem = retomada_lote`, `fora_do_expediente = true` | `Continuar` | saudação + aviso com `retorno_previsto` |
| Foto sem legenda | `midia_tipo = image` | `[cliente enviou imagem]` | pede descrição em texto, não finge ter visto |
| Documento de exame | `midia_tipo = document` | `[cliente enviou documento] meu exame de ontem` | handoff para a recepção, se for a regra escolhida |
| Link de agendamento | nenhum | conversa até a Val mandar o link | resposta traz `desfecho_bot = link_enviado` |
| Já agendou | nenhum | "já marquei minha consulta" | resposta traz `desfecho_bot = agendado` |

Depois do teste, o caminho de sempre: publicar um environment novo e me mandar o ID. Eu troco o `environment_id` e o
`core_version` da `varizemed` no mesmo write.

---

## Ordem

1. O CRM entra em produção com tudo desligado.
2. O público Bot na tela de reabertura só liga depois que os itens **1 e 3** estiverem no environment publicado.
3. A mídia tem chave e teste próprios, porque muda o comportamento da Val para todos os pacientes, não só na retomada.
4. Até lá, a retomada do público Bot continua pelo script, e quem clica Continuar cai na recepção.

Me passa uma previsão quando puder.

---

## Nome de exibição da Hubloc (falar com o suporte hoje)

**Estado lido na Meta hoje, 05/10:**

| Campo | Valor |
|---|---|
| Nome atual | `HUBCLOC COMERCIAL`, **recusado** |
| Pedido pendente | `Hub Loc Locações`, **em análise** desde pelo menos 23/09 |
| Envio pelo número | **limitado**. A própria Meta diz: o limite sobe quando o nome for aprovado |
| Qualidade | verde |
| Limite do portfólio | 2.000 usuários por 24h |

O WhatsApp Manager mostra "Hub Loc Locações" como rejeitado enquanto a API mostra o pedido em análise, o que indica que
foi reenviado. Enquanto houver pedido pendente, nem a tela nem a API aceitam outro nome.

**Por que os nomes não passam.** A diretriz da Meta exige que o nome de exibição seja igual ao jeito como a marca aparece
no site, com a mesma grafia e o mesmo espaçamento. O site `hubloc.com.br` escreve **"Hub Loc"** em todo lugar: título
"Aluguel de Equipamentos em BH e Região | Hub Loc" e rodapé "© 2026 Hub Loc — Equipamentos para Construção Civil Ltda.".
"HUBCLOC COMERCIAL" e "Hub Loc Locações" não batem com isso. "Hubloc" junto também não bate. A Varizemed passou de
primeira porque "Varizemed" é exatamente o que está no site.

**O que pedir ao suporte.**
1. Concluir ou cancelar o pedido pendente de "Hub Loc Locações", para liberar um pedido novo.
2. Aprovar **"Hub Loc"**, idêntico ao site e ao rodapé com a razão social.
3. Se negarem, perguntar qual evidência eles querem: site, cartão CNPJ ou outro documento.

**Dados para o atendimento.**

| Item | Valor |
|---|---|
| Número | +55 31 3351-7604 |
| phone_number_id | 1118622994671651 |
| WABA | 1548003596823528, "Hub Loc Locações" |
| Portfólio | 948624047548258, "Castro Operações WhatsApp", verificado |
| Site | https://www.hubloc.com.br/ |

A Meta permite até 10 trocas de nome em 30 dias. Até a aprovação, a reabertura em lote da Hubloc fica desligada no CRM.

---

Detalhes de produto e implementação: `docs/PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md` e
`docs/decisions/0013-publicos-reabertura-lote.md`.
