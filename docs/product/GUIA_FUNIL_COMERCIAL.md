# Funil comercial — guia da equipe e da gestão

Entrega local de 28/10/2026 (com as decisões do PO da mesma data). Vale depois
da habilitação do funil para a clínica; ainda não foi publicado em produção. O funil mostra **onde cada paciente está na
jornada**. Ele não envia mensagens, não assume conversas, não muda a dona do
contato e não mexe na Val.

| Pergunta | Onde responder |
|---|---|
| O que eu preciso fazer agora com este paciente? | **Follow-up** (tarefas) |
| Em que ponto da jornada ele está? | **Funil** (etapa) |
| Como a operação está indo no mês? | **Funil → Painel gerencial** |

## As etapas

| Etapa | Quando usar |
|---|---|
| **Novo contato** | Está conversando com a Val (agente de IA), primeira interação. Entra sozinho na primeira mensagem. |
| **Em atendimento** | Está na recepção: a Val fez o handoff ou a equipe iniciou a conversa. Entra sozinho nesses casos. |
| **Aguardando retorno** | Ficou combinado um retorno ("vou falar com meu marido", orçamento em decisão). Crie a tarefa de follow-up com a data. |
| **Cliente Agendado** | Marcou consulta. Quem agendou pelo link da Val não aparece sozinho: confirme quando a pessoa chegar à clínica (o card mostra "Val: enviou o link"). |
| **Paciente em acompanhamento** | Fez tratamento e deve voltar: revisões, retorno anual, novos tratamentos. |
| **Não convertido** | Não aceitou a proposta, convênio não aceito, desistiu. O motivo é obrigatório. O paciente não some e pode voltar ao funil depois. |
| **Não qualificado** | Spam, golpe, número errado ou contato sem interesse para a clínica. Fica fora das métricas de conversão. |
| **A classificar** | Contatos antigos, de antes do funil. Vão sozinhos para Em atendimento quando passarem pela recepção. |

Os nomes e os textos explicativos de cada etapa podem ser trocados pela gestão
na aba **Etapas** do funil.

**Motivos de não conversão:** Não aceitou a proposta, Convênio não aceito,
Preço, Distância, Questão financeira, Sem interesse, Sem resposta, Adiou, Não
compareceu, Indicação médica ou Outro (texto curto). Use **Sem resposta** e
**Adiou** só quando a equipe decidir parar as retomadas; se há data combinada, o
certo é **Aguardando retorno**. Nunca escreva dados clínicos no texto do motivo.

## Uma classificação só

Ao **encerrar um atendimento**, o desfecho que você escolhe já é a etapa do
funil (Aguardando retorno, Cliente Agendado, Paciente em acompanhamento, Não
convertido ou Não qualificado). O CRM atualiza o funil e a classificação antiga
juntos; não é preciso classificar duas vezes. A opção "Qualificado" deixou de
existir: quem marcou consulta é **Cliente Agendado**.

Se o paciente estava em **Aguardando retorno** ou **Não convertido** e voltou a
conversar, o encerramento pergunta o desfecho de novo (já vem marcado o atual;
basta confirmar ou trocar, por exemplo para Cliente Agendado). Em Cliente
Agendado, Paciente em acompanhamento e Não qualificado o atendimento fecha
direto; para corrigir esses, peça à supervisão ou use **Mover para…** (se o seu
perfil tiver a permissão).

## Usar o quadro

- O botão **Funil**, no topo, abre o quadro com uma coluna por etapa. Cada
  coluna mostra o total e quantos estão **parados**; o ⓘ explica a etapa. A
  coluna Novo contato (contatos ainda com a Val) aparece só para quem tem a
  permissão "ver contatos com o agente de IA".
- **Parado** não é etapa: é um aviso. Em Novo contato (1 dia) e Em atendimento
  (2 dias), o paciente está sem escrever; em Aguardando retorno, a tarefa de
  follow-up está atrasada ou não existe. As demais etapas não ficam paradas. Os
  prazos podem ser ajustados para a clínica.
- Clicar no nome abre a ficha **só para leitura**: etapa, histórico, próximas
  tarefas e as últimas mensagens. Abrir a ficha não assume o contato, não pega
  tarefa e não marca nada como lido. **Abrir conversa no chat** é uma ação à
  parte e marca as mensagens como lidas, como no chat normal.
- **Mover para…** pede confirmação. Se outra pessoa mudou a etapa antes, o CRM
  avisa quem mudou e para onde, e você decide se aplica a sua mudança.
- O quadro não se atualiza sozinho: use **Atualizar**.
- No painel do contato, o cartão **Etapa do funil** mostra a etapa atual e
  permite mover sem sair da conversa.

## Painel gerencial (gestão)

Escolha o mês e compare com o anterior:
- **Pirâmide do mês:** dos contatos que entraram no mês, quantos aceitaram o
  aviso, quantos chegaram a Em atendimento, Cliente Agendado e Paciente em
  acompanhamento, e quantos **encerraram sem agendar**. Os **Não qualificados**
  aparecem à parte e não entram nos percentuais. Contatos antigos contam no mês do primeiro contato,
  por isso um mês já fechado pode crescer quando eles entram no funil.
- **Agora no funil:** quantos estão em cada etapa e quantos estão parados.
- **Movimentos do mês:** quantas mudanças de etapa aconteceram, por destino.
  A classificação de contatos antigos e as reativações aparecem separadas, para
  não distorcer o mês.
- **Não convertidos por motivo:** com as correções de motivo já aplicadas — uma
  tabela para os movimentos do mês e outra para a classificação de antigos.

Se uma coluna do quadro mostra um total maior que os cartões que você consegue
ver, alguns contatos daquela etapa estão fora do seu acesso (por exemplo, leads
de uma colega).
