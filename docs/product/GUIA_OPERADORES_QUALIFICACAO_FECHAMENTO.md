# Guia do Operador — Qualificação e Fechamento de Atendimentos

> Para a equipe de atendimento. Versão 2026-09 (reforma das qualificações).

---

## 1. A regra de ouro: fechar a conversa ≠ resultado do lead

O sistema controla **duas coisas diferentes**, e é importante não confundir:

| | O que é | Quem controla |
|---|---|---|
| **Estado do atendimento** | A conversa está *aberta* ou *fechada* | Você (botão Encerrar) — e, se a empresa optar, o sistema por inatividade |
| **Qualificação do lead** | O *resultado comercial*: virou cliente? desistiu? era engano? | **Sempre você.** O sistema nunca decide isso sozinho |

Uma conversa fechada **não** significa que o paciente fechou com a clínica. Fechar é
arrumar a mesa; a qualificação é o que conta a história do lead — e é ela que
alimenta as buscas, os relatórios e as futuras campanhas de retorno.

## 2. As qualificações e o que cada uma significa

| Qualificação | Significado | Quem marca |
|---|---|---|
| **Novo** | Recém-chegado (no robô ou na recepção). Nenhum humano falou com ele ainda | Automático |
| **Em atendimento** | Um operador já interagiu com o lead | **Automático**: na sua primeira resposta, o sistema promove o lead e registra "Atendimento iniciado em (data/hora)" na nota |
| **Qualificado** | Lead apto a avançar (análise de cadastro/financeiro) — *uso do fluxo de locação; não se aplica à clínica* | Operador |
| **Não qualificado** | Propaganda, número errado, spam, perfil fora do atendimento | Operador |
| **Convertido** | **Fechou com a empresa** — marcou a consulta, contratou, tirou a dúvida que veio buscar | Operador |
| **Não convertido** | Negociou de verdade, mas **não fechou** | Operador |

**Novo** e **Em atendimento** são estados de passagem. **Os quatro últimos são
desfechos** — todo atendimento encerrado por você precisa terminar em um deles.

## 3. Ao encerrar: a janela de desfecho

Ao clicar em **Encerrar atendimento** com um lead ainda "Novo" ou "Em atendimento",
o sistema abre uma janela pedindo o desfecho:

- **Desfecho** (obrigatório): Convertido · Não convertido · Não qualificado (· Qualificado)
- **Notas de atendimento**: já vem preenchida com a nota atual — complemente à vontade
- **Salvar e encerrar**

Sem escolher o desfecho, o sistema **não encerra** — é proposital: um lead sem
desfecho é um lead invisível para as buscas e campanhas de amanhã.

**Exemplos práticos:**

- Paciente marcou a consulta → **Convertido** ✔
- Perguntou valores, negociou, disse "vou pensar" e sumiu → **Não convertido**
- Chegou oferecendo panfletagem / caiu aqui por engano → **Não qualificado**
- Tirou a dúvida que veio buscar (endereço, convênio) e agradeceu → **Convertido** —
  o atendimento cumpriu o objetivo do paciente

## 4. O que o sistema faz sozinho (e o que não faz)

- **Promove Novo → Em atendimento** na sua primeira resposta, com registro de data/hora.
- **Envia o recibo no seu encerramento**: protocolo do dia + pergunta de avaliação
  com botões (Ruim / Bom / Excelente). A nota do paciente é confidencial —
  visível só para a supervisão, nunca para o operador avaliado.
- **Não fecha conversa atendida sozinho** (quando o fechamento automático estiver
  desligado nas configurações da empresa). A exceção é a válvula de segurança:
  lead entregue pela Val que **ninguém respondeu em 7 dias** volta para o
  assistente virtual — assim, se ele escrever de novo, alguém (a Val) responde.
- **Nunca muda um desfecho seu.** Convertido, Não convertido e os demais só mudam
  pela mão de um operador.

## 5. Por que isso importa

1. **Busca**: "me mostra os convertidos de varizes" só funciona se convertido
   estiver marcado (e, em breve, com as tags).
2. **Campanhas de retorno**: a reabertura em lote vai procurar exatamente os leads
   **"Em atendimento"** cuja conversa esfriou — as negociações que valem retomar.
   Lead fechado sem desfecho fica fora do radar.
3. **Qualidade**: a avaliação por botões mede o atendimento da equipe, não a venda.

## Dúvidas frequentes

**"Fechei sem querer, e agora?"** — Reabra pelo mesmo menu (Reabrir atendimento).
A qualificação que você escolheu continua valendo e pode ser ajustada no painel.

**"O paciente voltou depois que marquei Não convertido."** — Ótimo sinal: atenda
normalmente. Se desta vez fechar, atualize para Convertido no encerramento.

**"Preciso qualificar quando a conversa fecha sozinha?"** — Não. Fechamento
automático (quando ligado) não pede desfecho — e é por isso que ele **não** é um
substituto do seu Encerrar: sempre que você concluir um atendimento, encerre você
mesmo, com o desfecho certo.
