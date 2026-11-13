# Handoff — Mensagens automáticas da assistente (lembretes de inatividade) — hotfeature Varizemed

> **Revisao com o PO em 11/11/2026:** a secao **Resposta do Codex — 2026-11-11**, ao final,
> substitui as propostas e decisoes conflitantes deste documento. Tres lembretes apenas pos-aceite,
> tela nesta entrega, regra textual no CRM, comandos persistentes de parada/reativacao e sem
> tetos comerciais adicionais. Serie A e bloqueio por desfecho de sete dias foram retirados.

Branch `hotfeature/mensagens-automaticas` · worktree `C:\Rafael\castro-intelligence-mensagens-automaticas` ·
base `develop @ 5fc6dad` (2026-11-10, igual ao `origin/develop`).
Autor: Claude (2026-11-10). Executor: Codex. Produto: PO (Rafael/Izael). Revisão e merge do PR: Claude.

**Nada contra produção** (Firestore, Meta, gcloud): o que precisar de dado real vira script só-leitura, que o Claude
ou o PO rodam. **Commit, push e PR só quando quem conduz a sessão pedir. Deploy nunca é seu.**

**Em 10/11 o PO separou o trabalho em duas branches.** Esta cuida só dos lembretes dentro da janela de 24 h, como
hotfeature para a Varizemed. Os templates criados pelo tenant foram para a branch `feature/templates-por-tenant`
(`docs/HANDOFF_TEMPLATES_POR_TENANT.md`, na worktree `C:\Rafael\castro-intelligence-templates-tenant`). Não
implemente nada de template aqui.

**Prazo do PO: 11/11/2026**, prioridade urgente (card do quadro de pendências). Em 10/11 ele também fechou quatro
decisões, que já estão na seção 6: o lembrete não conta no teto do lote, o último sai 23h40 depois da última
mensagem do paciente, não há horário de silêncio, e são duas séries de três mensagens (A antes do aceite da LGPD,
B depois).

O desenho base passou por três rodadas de revisão adversarial em 10/11: as âncoras de código foram conferidas uma a
uma, os fatos da Meta que sustentam o desenho foram relidos nas páginas oficiais por verificadores independentes, e
o desenho foi atacado com casos numéricos. A separação em duas branches e as decisões do PO vieram depois e
passaram por uma quarta rodada (leitura fria e conferência no código), cujos achados já estão no texto. O que não
fechou está marcado.

Marcações usadas no texto:

- **[CÓDIGO]** lido em `develop @ 5fc6dad`, com âncora `arquivo:linha`.
- **[META]** lido na documentação oficial da Meta em 2026-11-10 (fontes na seção 10). A plataforma mudou muito em
  2025–2026; confira de novo antes de transformar em contrato.
- **[DOC]** registrado em documento do repositório.
- **[PROPOSTA]** desenho sugerido pelo Claude, aberto a crítica.
- **[A CONFIRMAR]** não fechou.

---

## Resumo para o PO

1. **O que você decidiu em 10/11 e já está neste documento** (seção 6):
   - o lembrete **não conta** no teto de 2 envios em 90 dias do lote. É um recurso vendido, ligado cliente a
     cliente e só pela Castro;
   - o último lembrete sai **23h40** depois da última mensagem do paciente;
   - os lembretes saem **a qualquer hora**, inclusive de madrugada e no fim de semana;
   - são **duas séries de três mensagens**: A1 a A3 para quem ainda não aceitou a LGPD, B1 a B3 para quem já
     aceitou e parou de responder à Val;
   - os **seis textos são seus**, e você entrega direto ao Codex.
2. **Os três horários não precisam de template.** 20 min, 4 h e 23h40 cabem na janela de 24 h da Meta, onde vale
   mensagem fora de template, sem aprovação da Meta.
3. **O molde já está em produção.** O aviso de espera da Hubloc é uma mensagem automática de texto livre dentro da
   janela de 24 h. O lembrete copia dele o cron de 5 min (com endereço e job novos), o lugar da configuração (na
   primeira versão, gravada por script e sem tela) e o simulador (seção 4.1, "Aviso de espera × lembrete"). A parte
   nova é o CRM passar a saber que o bot falou por último e que o lead não respondeu.
4. **Tem custo, e exige forma de pagamento em dia.** Desde 01/10/2026 a Meta cobra mensagem fora de template acima
   de 1.000 por número por mês (R$ 0,035 de tabela). A franquia é dividida com todas as respostas da Val e das
   atendentes do mesmo número, então, na prática, cada lembrete deve custar. Sem forma de pagamento na conta, a
   Meta não entrega nada acima da franquia — nem as respostas da Val. Pelos registros do repositório, a fatura hoje
   chega à Castro (a confirmar na Meta). O aviso de espera da Hubloc entra na mesma conta.
5. **Limites próprios que ficaram como padrão** (os números são seus para mudar): cada mensagem sai uma vez por
   ciclo; por paciente, no máximo duas das mensagens de 20 min e 4 h em 24 horas, seis lembretes em 7 dias e 60
   minutos entre dois. As duas séries somam.
6. **A decisão que mais pesa entre as que faltam é a MA6.** A Val costuma fechar com "Posso te ajudar em algo
   mais?", e o CRM não sabe distinguir isso de uma pergunta de verdade. No padrão, a série B só sai quando a última
   fala da Val tinha uma pergunta de verdade; a alternativa é mandar só o primeiro lembrete nos outros casos. O
   medidor traz os números para você escolher. Para isso funcionar, o sistema precisa de duas listas curtas, que
   você aprova junto com os textos: as frases de cortesia da Val e as palavras com que o paciente pede para parar
   (MA7). Faltam também quem já recebeu o link de agendamento (MA5) e as demais da seção 6, todas com padrão
   definido. Nenhuma segura o código.
7. **Ligar é um passo seu** (MA17). O código entra em produção desligado. Primeiro roda em modo simulação, que
   registra o que enviaria sem enviar nada; o envio de verdade começa quando você mandar.
8. **Madrugada.** Sem horário de silêncio, quem escreve às 22h recebe o lembrete de 4 h às 2h. Vale acompanhar os
   bloqueios e a qualidade do número na primeira semana.
9. **Um cuidado com os textos.** A série A fala com quem ainda não aceitou a política de privacidade: sem nome,
   sem sintoma, sem dado de saúde. Os limites estão na seção 4.5, e alguns pedem o jurídico da clínica.
10. **A primeira versão é configurada pela Castro, por script.** A tela para a clínica editar textos e horários vem
    num segundo PR, depois que o motor estiver em produção.
11. **Achado de segurança fora deste trabalho** (seção 9, item 1), tratado à parte.

---

## 0. Como usar este documento

1. Leia `CLAUDE.md`, `AGENTS.md` e a seção 8 antes de tudo.
2. **É um hotfeature com prazo em 11/11: o caminho é curto, e a ordem importa.**
   1. **Medidor** (seção 2, linha "Medidor"). É pequeno e só lê. A função que classifica a fala da Val nasce com
      ele, já no módulo que o motor vai importar (4.2, item 3). Avise quando estiver pronto: o Claude roda em
      produção enquanto você segue.
   2. **Resposta escrita** (N1, N2 e N3), curta, numa seção nova no fim deste arquivo,
      `## Resposta do Codex — AAAA-MM-DD`. A N1 depende dos seis textos: se ainda não chegaram, entregue N2 e N3,
      siga para o motor e anexe a N1 depois.
   3. **Motor** (fatia 1), com tudo desligado por padrão.

   A tela (fatia 2) é um segundo PR, depois que o motor estiver em produção.
3. **Os seis textos chegam pelo PO, na sua sessão** (séries A e B, seção 4.5). Não invente texto e não ponha
   texto da clínica como default no código: eles entram pela configuração do tenant. As duas listas da 4.6
   (frases de cortesia e palavras de parada) você propõe na N3, e o PO aprova.
4. **Nenhuma decisão do PO segura o código.** As que ele já tomou estão na coluna "Decisão do PO" da seção 6 e
   valem mais que qualquer recomendação. Para as que faltam, implemente a recomendação como padrão — sempre que
   der, como valor de configuração, para a decisão virar troca de valor e não de código — e registre no PR quais
   padrões usou.
5. **Objeção estrutural vem antes do código.** Se você discorda de algo que mudaria o desenho (o carimbo, a
   agenda, o gate), escreva na N3 e alinhe com quem conduz a sessão antes de implementar aquela parte. Objeção de
   detalhe: siga a sua opção e registre.
6. Nada de template nesta branch (seção 7).
7. As pastas `cx/` (export do agente) e `temp services/` (serviços da Val) estão no `.gitignore` e **não existem
   nesta worktree**. O que você precisa delas está resumido na seção 4.5. Existem na pasta principal
   (`C:\Rafael\castro-intelligence\`), só para leitura.

## 1. Pedido do PO (2026-11-10, literal) e vocabulário

Primeira mensagem:

> A Varizemed precisa das mensagens automáticas (para leads que esquecem de responder, ou seja, a Val mandou
> mensagem e ele não respondeu) de 20 minutos, 4h e 23:50h; coloca no handoff que preciso de sugestões de mensagens,
> análise de possibilidade de trocar os horários destas mensagens automáticas. No futuro o ideal seria escolher
> também as mensagens, o tenant cria um novo template na Meta e nosso sistema reconhece para ser selecionado e
> configurado. Preciso de sugestão e um plano para que o tenant possa fazer o template através do sistema, assim
> tiramos a responsabilidade da nossa empresa de ter que usar o portfólio Castro Operações, nele ficaria apenas os
> templates padrão do nosso sistema que seriam copiados para o portfólio do tenant. Preciso discutir isso com o
> Codex.

Segunda mensagem, no mesmo dia, depois de ler o resumo deste handoff (pontuação ajustada):

> Na verdade já temos um alerta na Hubloc que se aproveita disso. Vamos separar as coisas: quero uma branch de um
> hotfeature para colocar as mensagens automáticas na Varizemed. E na outra, a questão da criação de templates por
> tenant.

Card do quadro de pendências, reescrito pelo PO em 10/11 (prioridade urgente, prazo 11/11):

> Implementar no Castro Chat (não na Val) lembretes de 20min, 4h e 23h50, em dois estágios: Pré-LGPD (A1–A3):
> lembrar do aceite; Pós-LGPD (B1–B3): retomar atendimento. Usar os seis textos fornecidos. Regras: integrar ao
> contador, cancelar após resposta/encerramento, evitar duplicidades, respeitar LGPD e janela de 24h da Meta.

Respostas do PO a quatro perguntas do Claude, no mesmo dia:

| Pergunta | Resposta do PO |
|---|---|
| "Integrar ao contador": o lembrete conta no teto de 2 envios em 90 dias do lote? | "Não deve contar, vamos vender esse recurso." |
| Como os seis textos chegam ao handoff? | "Passo direto ao Codex." |
| O terceiro lembrete sai 23h40 ou 23h50 depois da última mensagem do paciente? | 23h40 |
| O que fazer com lembrete que cairia de madrugada? | "Enviar a qualquer hora." |

Desta branch é o começo do primeiro pedido: os lembretes e a análise dos horários. As sugestões de texto foram
substituídas pelos seis textos do PO. O que vem a partir de "No futuro" é da outra branch. O "alerta na Hubloc" é
o aviso de espera na pool (seção 4.1).

| Termo | Significado neste documento |
|---|---|
| Val | agente de IA (Dialogflow CX) do tenant `varizemed` (clínica) |
| Fase de bot | lead ainda conduzido pela Val, antes de ir para a equipe |
| Turno | uma resposta do bot a uma entrada do lead |
| Castro Chat | o CRM deste repositório |
| Lembrete | mensagem automática fora de template, dentro da janela de 24 h, quando o bot falou por último (o aviso da LGPD ou a Val) e o lead ficou em silêncio |
| Série A (A1, A2, A3) | lembretes para quem recebeu o aviso da LGPD e ainda não respondeu (pré-LGPD) |
| Série B (B1, B2, B3) | lembretes para quem já aceitou a LGPD e parou de responder à Val (pós-LGPD) |
| Etapa | a posição na série: 1 (20 min depois da fala do bot), 2 (4 h depois) e 3 (fechamento, 23h40 depois da última mensagem do lead) |
| Ciclo de lembrete | o período desde a última mensagem do lead numa thread; identificado pelo `last_inbound_at` da thread |
| Ciclo do bot | o período desde a última devolução do lead ao bot (`bot_released_at` do contato); é o marco que o lote de reabertura usa |
| Tick | uma execução do cron |
| Folga | margem de segurança antes do fim da janela de 24 h (proposta: 5 min) |

## 2. O que se espera de você

**Análise — curta, e não segura o motor.**

| # | O que | Ponto de partida |
|---|---|---|
| N1 | **Revisão dos seis textos do PO** contra os limites da 4.5 (tamanho, link, dado de saúde, promessa). Não reescreva por conta própria: aponte o problema e proponha a troca ao PO | 4.5 |
| N2 | **Análise dos horários**: dá para o tenant trocar? Com que limites e que precisão? Entregue a tabela-verdade das regras de horário em Markdown (colunas: situação → envia, adia ou pula) | 4.4 |
| Medidor | **Script de medição, só leitura** (`tools/bot_reminder_measure.py --tenant --dias`), com `trava_escrita()` no molde de `tools/reopen_conciliation.py:63`. Saída **só agregada** (contagens e percentis): nada de telefone, `wa_id`, nome, id de contato ou trecho de mensagem, nem em log. Responde: quantas threads por dia têm turno da Val; quantas ficariam elegíveis; como terminava a última fala da Val (pergunta de verdade, só cortesia, sem pergunta, link, aviso LGPD); em quanto tempo o lead responde (até 20 min, 20 min–4 h, 4–24 h, nunca). Aviso de espera, recibo e template ficam de fora pelo conteúdo e pelo `msg_type`. A classificação da última fala usa a **mesma função pura** do motor (4.2, item 3). Você escreve; o Claude ou o PO rodam | 4.1, 4.5, R1 e MA6 |
| N3 | **Objeções ao desenho**: o que você faria diferente e por quê | 4.2, 5 |

Formato da resposta: por item (N1, N2 e N3), recomendação, alternativas e perguntas em aberto.

**Implementação.** As fatias deste handoff não têm relação com as fases F1, F2 e F3 do
`docs/followup_crm_varizemed.md`.

- **Fatia 1 (motor) — é o hotfeature:** classificação do turno, carimbo, as duas séries (A e B), cron, gate,
  regras de horário, tetos, modo simulação, contador mensal, script da chave por tenant (modo, escopos e as duas
  listas), script da configuração, simulador. Tudo desligado por padrão.
- **Fatia 2 (tela) — segundo PR, depois da fatia 1 em produção:** bloco na aba Sistema para a clínica editar
  textos e horários. O selo no chat já sai na fatia 1, pelo `sent_by_name` (4.6).

Fica fora da fatia 1 (diga na resposta se cortou ou incluiu mais alguma coisa):

- horário de silêncio: o PO decidiu enviar a qualquer hora (MA3). Não deixe configuração morta para isso;
- lembrete para quem já recebeu o link de agendamento (MA5): esse turno não arma nada;
- o aviso à Val por parâmetro de sessão (4.7, MA16);
- o tratamento do erro 131047 quando ele só chega pelo webhook de status (4.4), salvo se você mostrar na N3 que é
  pequeno;
- lembrete depois de 24 h, que é template (seção 7).

Cada fatia termina com o código na worktree e todos os gates da 4.9 verdes. Commit e PR só a pedido; nesse caso,
commits pequenos, rebase sobre `origin/develop` e PR contra `develop`.

## 3. Fatos que mudam o desenho

1. **Os três horários cabem na janela de 24 h, então não precisam de template [META].** A janela abre e reinicia só
   por ação do lead (mensagem, ligação, ou atender uma ligação da empresa); mensagem da empresa não renova (dedução
   do texto oficial, que só cita ações do usuário). Dentro dela vale mensagem que não é template, sem aprovação da
   Meta e editável pelo tenant. Template só é obrigatório depois de 24 h, e isso é assunto da outra branch
   (seção 7). O aviso de espera na pool, que o PO citou como o alerta da Hubloc, já envia texto livre dentro da
   janela, com cron de 5 min **[CÓDIGO]** (`main.py:5380-5476`).
2. **Mensagem fora de template deixou de ser gratuita sem limite em 01/10/2026 [META].** Cada número tem uma
   franquia de 1.000 mensagens de serviço **entregues** por mês; da 1.001ª em diante a Meta cobra (Brasil: R$ 0,035
   de tabela, igual ao utility). "Serviço" é tudo que não é template — texto, mídia, botões —, inclusive as respostas
   da Val e das atendentes do mesmo número. Sem forma de pagamento na conta, a Meta não entrega o que passa da
   franquia. Exceção: lead que chega por anúncio Click-to-WhatsApp tem até 7 dias sem cobrança. Lembrete dentro da
   janela **não** consome o limite de mensagens do portfólio (ele só conta destinatários fora da janela).
3. **Regras que o PO já registrou e que, lidas ao pé da letra, impedem três lembretes [DOC].** Em
   `docs/followup_crm_varizemed.md`: automação de mensagem usa os limites e o orçamento da reabertura, "sem contador
   paralelo" (linhas 55 e 591); a aprovação "não autoriza implementar mensagens automáticas nesta fase" (562); e a
   decisão 9, provisória, de 18/10, põe todo follow-up automático proativo, "inclusive job individual e texto livre
   dentro da janela de 24h", na lista única `reopen_batch_sent_at`, consumindo o teto de **2 envios por contato em
   90 dias** e o orçamento diário compartilhado (585), com o exemplo e a ressalva da linha 587. **O PO decidiu
   em 10/11 que o lembrete não conta nesse teto** ("não deve contar, vamos vender esse recurso"; MA1). O PR leva a
   emenda dessas cinco linhas. Nesse documento, F1, F2 e F3 são as fases do follow-up, não as fatias deste
   handoff; a regra de não contatar no fim de semana (linha 51) é da fase F2 de lá e não vale para o lembrete
   (MA3).
4. **O CRM não sabe hoje que "a Val falou por último", nem se ela perguntou algo [CÓDIGO].** Não há carimbo de
   saída do bot: a thread só tem `last_outbound_at` (bot e humano) e `last_human_outbound_at`. O agente devolve um
   parâmetro `conversation_complete`, mas o CRM só o registra em log (`bot_engine_dialogflow.py:154`, `243-249`).
5. **23h50 exato não cabe no relógio do sistema.** O único relógio é o Cloud Scheduler (o precedente roda a cada
   5 min), e todo envio precisa de folga antes do fim da janela. Com tick de 5 min, uma etapa marcada para 23h50
   depois da última mensagem do lead sairia entre 23h50 e 23h55, sem tolerar um único tick perdido. O aviso de
   espera, que já existe, usa folga de 10 min (`database_firestore.py:1740`): com ela, 23h50 nunca sairia. O PO
   escolheu 23h40 (MA2).
6. **A Val não vê o lembrete.** O texto não passa pelo agente. **[A CONFIRMAR]** a sessão do Dialogflow expira em
   cerca de 30 min: no repo há só afirmações sem fonte (o comentário em `bot_service.py:1208-1210` e
   `docs/CX_RESUMO_RETOMADA_DEV_IA.md:35`), e o CRM não envia `sessionTtl`. Quem responde ao lembrete de 4 h
   provavelmente cai numa sessão nova, e o fio da conversa depende da memória da Val.
7. **Os bloqueios que já existem quase nunca protegem aqui [CÓDIGO].** `reopen_opt_out` e a recusa comercial se
   desfazem com mensagem nova do lead posterior ao registro (`webhook.py:1698-1722`;
   `database_firestore.py:3553-3568`). Como só texto ou áudio geram turno da Val, todo ciclo de lembrete começa
   com uma mensagem que desfaz os dois. Hoje não existe um jeito de o lead dizer "pare".

---

## 4. Lembretes de inatividade na fase de bot

### 4.1 Como é hoje [CÓDIGO]

| Assunto | Fato | Âncora |
|---|---|---|
| Envio do bot | `send_bot_reply`: POST na Graph (timeout 15 s) e grava outbound `msg_type="text"`, `sender_user_id=None`, `operator_id=None`; os demais kwargs ficam no default (`advance_recency=True`, `reopen_attendance=True`). Devolve só `bool`. Não confere janela | `bot_sender.py:17-56`; `database_firestore.py:3306-3321` |
| Envio que falha | quando a Meta responde não-200, grava um doc `status="failed"` que mesmo assim avança `last_outbound_at` e `last_message_at` e reabre `attendance_status` (o upsert não olha `status`). Timeout e erro de rede não gravam nada | `bot_sender.py:32-56`; `database_firestore.py:1265-1294` |
| Saída única do turno | `_run_bot_turn_and_send` envia **qualquer** retorno de `process_bot_message_async` (texto ou dict de botões): resposta do agente, aviso LGPD, "não entendi", confirmação do aceite (sozinha ou antes da resposta do agente), despedida e lembrete da recusa, mensagem de instabilidade do motor e mensagens de handoff (pedido do agente, falha do motor, erro do agente). Todo turno passa por ele (direto, buffer, flush do cron, Continuar do lote). O resultado do envio é ignorado e a mensagem sai sem tipo | `webhook.py:1067-1078` (chamadas em 532, 1110, 1206, 1220-1304); `bot_service.py:929-954`, `1086-1137`, `1142-1182` |
| Carimbos da thread | `last_outbound_at` (bot e humano); `last_human_outbound_at` (só com `sender_user_id` e `human_outbound`); `last_inbound_at` = data real da Meta, só para inbound `received` que não seja controle (reação e clique de botão contam) e **sem guarda monotônica**: mensagem entregue fora de ordem pode recuar o carimbo. Outbound reabre `attendance_status` | `database_firestore.py:1265-1294`, `3575-3608` |
| Carimbo do contato | `contact.last_inbound_at` = relógio do servidor em todo evento de mensagem do cliente, de qualquer canal, inclusive reentrega da Meta e evento pendente drenado (o `upsert_wa_contact` roda antes dos dois filtros). O import de history do coex também o avança, com a data real | `database_firestore.py:2195-2203`, `2282-2305`; `webhook.py:1432-1440` |
| O que não existe | carimbo de "última fala da Val"; campo de origem ou `is_bot` na mensagem | procurado em `*.py`, `*.ts`, `*.tsx` |
| Outbound sem remetente não é sinônimo de Val | aviso de espera e recibo de protocolo do cron saem por fora do turno, com o mesmo formato | `main.py:5451`, `5830` |
| Fase de bot (CX) | contato sem `assigned_to` e sem `bot_completed`; `bot_states.human_active` falso; motor `dialogflow_cx` com `status=active`; `system_settings.bot_enabled` | `webhook.py:1744-1749`; `bot_service.py:841-894` |
| Estado LGPD | máquina de estados em `bot_states` (`lgpd_status`: `awaiting`, `accepted`, `refused`; `lgpd_consent`). O contato guarda só a prova do aceite (`lgpd_consent=True`, `lgpd_consent_at`, `lgpd_policy_version`) e a revogação (`lgpd_revoked`, que nenhum código de produção grava hoje). A recusa **não** vai para o contato. Helper: `lgpd_consent_resolved`, que com estado já aceito confere a data da política mas **não** a revogação | `lgpd_bot.py:421-468`; `bot_service.py:429-453`, `793-827` |
| Quem recusou a LGPD | continua em fase de bot (sem dono, sem `bot_completed`); a última saída é a despedida da recusa ou, se voltou a escrever sem aceitar, o lembrete da recusa com botão Sim | `lgpd_bot.py:421-449` |
| Tenant com `lgpd_by_agent` | o CRM não mostra aviso nem guarda aceite ou recusa (é o caso do agente Hugo, na Hubloc) | `bot_service.py:900-929`, `1248-1253` |
| Handoff | `handoff_at` só na thread; `bot_completed=True` no contato (o último write); `bot_states` apagado. Se a persistência falha antes do write do contato, a mensagem de transferência sai mesmo assim e `bot_completed` fica falso, embora `handoff_at` possa já estar em parte das threads | `bot_service.py:566-576`, `1100-1112`, `1158-1182`, `1366-1390`, `1596-1625` |
| Devolução ao bot | `release_lead_to_bot` e `return_contact_to_bot`: `bot_completed=False`, `bot_released_at=agora`, zeram `bot_outcome` e os params pendentes | `database_firestore.py:2871-2933`, `3017-3084` |
| Desfecho da Val | `bot_outcome` é gravado só em turno sem handoff e quando o valor muda. No teste de 09/11 (agente em Draft) o `scheduling_outcome` chegou só no turno **seguinte** ao do link **[DOC]**. Heurística de apoio do lote: alguma resposta do bot contém `REOPEN_DESFECHO_LINK` ("marcaconsultas") nas últimas 40 mensagens | `bot_service.py:1193-1206`, `1291-1342`; `docs/internal/2026-11-09.md:30-41`; `database_firestore.py:4586-4613`; `config.py:298` |
| Parâmetro de um turno | `queue_cx_session_params` / `discard_cx_session_params`: entra no próximo turno que chega ao DetectIntent e sai como `None` no seguinte. Sem TTL | `bot_service.py:253-271`, `988-1007` |
| Janela de 24 h | `_check_24h_window` lê o `last_inbound_at` do **contato**, margem zero. O aviso de espera lê o da **thread**, folga de 10 min | `main.py:2486-2501`; `database_firestore.py:1740`, `1801-1805` |
| Concorrência | a inbound é salva **antes** do turno; o turno direto não tem lock; o único claim ligado ao turno é o do `bot_buffers` (só com buffer maior que zero). A reentrega da Meta é barrada antes, pelo `was_dup` | `webhook.py:1584-1588`, `1612`, `1761`; `database_firestore.py:168-194`, `275-335` |
| Flush do buffer pelo cron | responde pelo canal de `contact.channel_id` (o **primeiro** canal do contato), não pelo da thread | `main.py:5293-5357` |
| Precedente a copiar | aviso de espera na pool (commit `158b353`): cron de 5 min, config em `system_settings`, carimbo antes do envio; público = lead **fora** da fase de bot (`bot_completed=True`). Nele, só a auth e a busca de candidatos saem do event loop | `main.py:5380-5476`; `database_firestore.py:1718-1859`; `tools/sim_pool_wait_notice.py` |
| Crons | 4 endpoints `/api/internal/cron/*`; auth OIDC com audiência única, ou `X-Cron-Secret`. Com OIDC o middleware põe o request no contexto `hubloc`; com o segredo, sem contexto. Cada cron faz `set_tenant_context(tid)` e `reset` no laço | `main.py:5071-5149`, `5152-5476`, `309-364` |
| Fechamento automático | o cron nunca fecha thread **sem dono** em fase de bot | `database_firestore.py:1608-1715` (regras em 1651-1652 e 1686-1688) |
| Configurações (dados) | `_DEFAULT_SYSTEM_SETTINGS` com default no READ e sem cache; booleano novo entra na tupla de coerção | `database_firestore.py:4922-5091` |
| Configurações (API e tela) | `PUT` exige `gerenciar_config_sistema`; `GET` sem permissão; o front manda o objeto **inteiro** em todo save, inclusive na aba Notificações; chaves só da Castro são descartadas no `PUT` (`_CASTRO_ONLY_SETTINGS`); a auditoria grava o body, trocando `lgpd_notice` pelo tamanho | `main.py:1483-1549`; `frontend/src/context/CrmContext.tsx:4039-4051` |
| Chave por tenant | padrão do follow-up: env geral **e** `tenants/{id}.settings.<x> is True`; `list_tenants` já devolve o doc (cache de 60 s) | `followup_routes.py:31-44`; `tenant_service.py:227-235`; `scripts/set_tenant_buffer.py` |
| Horário comercial | tabela fixa no código, fuso −3, sem feriados; `is_open` modela o expediente da clínica, não um "horário de silêncio". À parte, o follow-up já guarda faixas de contato e feriados por tenant, usados só para prazo de tarefa | `business_hours.py:28-107`; `followup_service.py:284-289` |
| Contagem de uso | o doc mensal de uso do tenant já conta `free_form_sent` e `templates_sent` por categoria — por tenant, não por número, e contando todo outbound gravado, inclusive o que falhou | `database_firestore.py:3612-3623`, `3852-3891` |
| Frontend | bolha sem operador vira "Bot"; `sent_by_name` já passa na whitelist e aparece como autor; campo novo de mensagem exige `normalization.ts` | `frontend/src/utils/formatting.ts:37-53`; `frontend/src/utils/normalization.ts:77-111` |

**Aviso de espera × lembrete [CÓDIGO].** O aviso de espera na pool é o "alerta da Hubloc" que o PO citou: já é uma
mensagem automática de texto livre dentro da janela de 24 h. O lembrete é irmão dele. A tabela mostra o que dá
para reaproveitar e o que é novo (âncoras: `main.py:5380-5476`; `database_firestore.py:1718-1859`):

| | Aviso de espera (em produção) | Lembrete (este trabalho) |
|---|---|---|
| Quem recebe | lead que já saiu do bot e espera atendente: contato com `bot_completed`, sem dono | lead ainda em fase de bot, parado no aviso da LGPD ou na conversa com a Val: contato sem `bot_completed`, sem dono |
| O que dispara | N minutos depois do `handoff_at` (ou da abertura seguinte do expediente) | X depois da última fala do bot sem resposta do lead, mais o fechamento antes de a janela acabar |
| Quantas vezes | uma por ciclo de handoff (`pool_wait_notice_at`) | até três por ciclo de lembrete, em duas séries (A antes do aceite da LGPD, B depois), com tetos por contato |
| Horário | só com o expediente aberto (`business_hours.is_open`) | a qualquer hora (decisão do PO, MA3) |
| Janela | `last_inbound_at` da thread, folga de 10 min | a mesma leitura, folga proposta de 5 min |
| Consulta do cron | range em `handoff_at` das últimas 24 h | agenda `bot_reminder_next_at` |
| Contra envio em dobro | carimbo gravado antes do envio, sem transação | reivindicação da etapa em transação |
| Envio | `send_bot_reply`, que sobe a recência e reabre o atendimento | caminho próprio, que não sobe recência nem reabre (4.2, item 7) |
| Configuração | três chaves em `system_settings/chat`, editadas na aba Sistema | 4.6 |
| O que faltava no CRM | nada: o `handoff_at` já existia | saber que o bot falou por último, e que tipo de fala foi |

### 4.2 Desenho proposto [PROPOSTA]

Nome de trabalho no código: `bot_reminder` (escolha um e mantenha em tudo). Na tela: "Lembretes automáticos da
assistente".

1. **O turno sai classificado.** Hoje o retorno do turno é só a mensagem (texto ou dict de botões), sem tipo. O
   desenho precisa do tipo: `cx_reply` (resposta normal do agente), `lgpd_notice` (aviso LGPD e "não entendi"),
   `lgpd_refusal` (despedida e lembrete da recusa), `engine_fallback` (mensagem de instabilidade) e `handoff`
   (pedido do agente, falha do motor, erro do agente). A lista exata sai da leitura de
   `process_bot_message_async`; a confirmação do aceite que vem colada à resposta do agente conta como `cx_reply`.
   A confirmação que sai sozinha (sem pergunta guardada do lead, `bot_service.py:946-948`) também: o aceite já
   existe, então ela nunca é série A.
   Como devolver o tipo sem quebrar os simuladores é escolha sua (ex.: função irmã que devolve `(reply, kind)`).
   O tipo também escolhe a série: `lgpd_notice` arma a série A; `cx_reply`, a série B. O tipo dos turnos do gate
   sai do `lgpd_status` depois do `handle_lgpd`, não da forma do retorno: `awaiting` → `lgpd_notice`; `refused` →
   `lgpd_refusal`; `accepted` → segue para o agente (`cx_reply`, `engine_fallback` ou `handoff`). Dict com botões
   também é o lembrete da recusa, e texto simples também é a despedida.
2. **Carimbo na thread, regravado a cada turno do bot enviado com sucesso**, no mesmo write do envio:
   `last_bot_turn_at`, `last_bot_turn_kind`, `bot_reminder_scope` e a agenda `bot_reminder_next_at`. O escopo diz o
   que aquele turno autoriza: `todas` as etapas, só a `primeira`, ou `nenhuma`; com `nenhuma`, a agenda é gravada
   como `None`. Como todo turno regrava os quatro campos, **um turno que não arma apaga a agenda do turno
   anterior**. Só o caminho de `_run_bot_turn_and_send` grava (kwarg descendo por `send_bot_reply` →
   `save_wa_message` → `upsert_wa_conversation`, sem write extra). Aviso de espera, recibos, lembretes e envio que
   falhou não gravam. O turno só grava esses campos com a env ligada **e** o modo do tenant em `dry_run` ou `on`
   (lido do cache do tenant, sem leitura): com o recurso desligado, o turno não muda em nada, e ligar não dispara
   nada retroativo.
3. **Nem todo turno arma o ciclo, e o tipo do turno escolhe a série.**
   - `lgpd_notice` (o aviso e o "não entendi"): escopo `todas`, **série A** (MA4, decidida).
   - `cx_reply`: escopo `todas`, **série B**, salvo os casos abaixo.
   - Escopo `nenhuma`, fixo: `engine_fallback`, `handoff` (mesmo com a persistência falha), `lgpd_refusal` e
     resposta que contém o `REOPEN_DESFECHO_LINK` (MA5).
   - Escopo por configuração do tenant, com o padrão da seção 6 enquanto o PO não decidir: resposta sem pergunta
     de verdade (MA6; padrão `nenhuma`), turno do Continuar do lote (MA13; padrão `primeira`) e turno em que o
     lead pediu para parar (MA7; `nenhuma` quando o texto do lead contém uma palavra da lista de parada).
   - Quando mais de uma regra vale para o mesmo turno, fica o escopo mais restritivo (`nenhuma` vence `primeira`,
     que vence `todas`), inclusive sobre o `todas` do `lgpd_notice`.

   A resposta e o texto do lead estão em mãos no momento do envio. O que o turno precisa da configuração (o modo,
   os dois escopos configuráveis e as duas listas) mora no doc do tenant, que vem do cache (4.6); assim essa
   decisão não custa leitura nenhuma. "Pergunta de verdade" sai de uma **função pura única**, usada pelo motor e
   pelo medidor, para a medição valer como previsão do que o motor vai fazer. Ponto de partida: a resposta tem pelo
   menos uma frase interrogativa que não está na lista de frases de cortesia do tenant. A regra fina é sua;
   proponha na N3.
4. **"O lead não respondeu" é comparação de carimbos, não flag:** `last_bot_turn_at > last_inbound_at` na thread
   **e** `contact.last_inbound_at <= last_bot_turn_at` (nenhum evento de entrada do contato, em qualquer canal,
   depois da fala). Como a inbound é salva antes do turno, isso cobre lead com turno em voo ou em buffer. Nada a
   zerar no webhook quando o lead responde (mesmo raciocínio de `handoff_at` × `last_human_outbound_at`). Efeito
   conservador conhecido: reentrega tardia da Meta e evento pendente drenado também movem o carimbo do contato e
   podem barrar um lembrete devido; é raro e erra para o lado seguro.
5. **Ciclo e etapas.** O ciclo de lembrete é o `last_inbound_at` da thread e **só anda para a frente**: se o
   carimbo recuar, mantêm-se ciclo e etapas (nunca reenviar). As etapas enviadas ficam guardadas por **chave
   estável** da etapa na configuração (ex.: `"etapa_1"`, `"etapa_2"`, `"fechamento"`), nunca derivada do horário:
   editar o horário no meio do ciclo não muda a chave, então não reenvia nem pula nada. Guarde-as como lista junto
   do ciclo (ex.: `{"ciclo": <last_inbound_at>, "etapas": ["etapa_1"]}`) ou grave o campo com `update` na
   transação: um mapa por etapa regravado com `set(merge=True)` manteria as etapas do ciclo anterior (4.6). A
   lista de envios usada no teto por contato fica **no contato**; os envios simulados ficam numa lista à parte,
   para a simulação respeitar os mesmos tetos. Os tetos por contato somam as duas séries. O marcador da mensagem e
   a auditoria guardam a série e a etapa (A1 a B3).
6. **Cron novo `POST /api/internal/cron/bot-reminders`:**
   - auth e **todo** o Firestore em `run_in_threadpool` (o aviso de espera não faz isso com settings, carimbo e
     auditoria; aqui faça); orçamento de tempo de 150/200 s e teto de envios por tick (proposta: 30, como o
     `limit` do aviso de espera);
   - só tenant ativo com a chave ligada (doc do tenant, zero leitura quando desligado), sempre dentro de
     `set_tenant_context` com `reset` no `finally`;
   - candidatos pela agenda: `where("bot_reminder_next_at", ">=", agora − 24 h)` e
     `where("bot_reminder_next_at", "<=", agora)` + `order_by` no mesmo campo (índice automático). Tick sem nada
     vencido não lê thread nenhuma. O limite inferior é seguro: etapa vencida há mais de 24 h já passou do fim da
     janela, e agenda velha nunca é lida. Leia mais candidatos do que o teto de envios (ex.: até 200 por tenant,
     dentro do orçamento de tempo): o teto de 30 é de **envios**, e a ordem da regra 4 da 4.4 (fechamentos
     primeiro) é feita em memória sobre o que foi lido. Se vierem 200, registre em log que pode haver mais. Valor
     inicial da agenda: o vencimento da primeira etapa, se você tiver a configuração em mãos sem leitura extra por
     turno; senão, um valor conservador (agora + 10 min) que o cron corrige. Alternativa mais simples a avaliar:
     varrer `last_bot_turn_at >= agora − 24 h`, que custa cerca de 288 × N leituras por dia (N = threads com turno
     no dia, número que sai da medição);
   - uma função **pura** (`thread`, config, `agora`) decide: ciclo encerrado ou escopo esgotado → limpa a agenda;
     ainda não venceu (intervalo mínimo, configuração mudou) → reagenda; barrada pelo teto, ou adiada para
     depois do limite da janela → pula a etapa; venceu → segue para o gate;
   - um candidato por contato (a thread de `last_bot_turn_at` mais recente);
   - gate da 4.3 do mais barato para o mais caro; depois **reivindicar a etapa numa transação** que lê e grava
     thread e contato (confere ciclo, etapa e teto), e só então enviar. Falhou o envio: não tenta de novo (melhor
     perder um lembrete do que mandar dois) e registra auditoria;
   - gate que barra também mexe na agenda, na mesma escrita. Condição que não volta sozinha neste ciclo (thread
     com dono, fechada ou backup; handoff ou humano depois do inbound; `bot_completed`; contato arquivado; recusa
     ou revogação da LGPD; entrada do contato depois da fala; canal inativo, coexistence ou de outro tenant;
     janela fechada) → agenda `None`. Condição passageira (item no buffer ou claim vivo) → agenda = agora + 5 min.
     Sem isso, a thread morta fica vencida e é relida a cada tick até a janela fechar.
7. **Envio por caminho próprio**, irmão de `send_bot_reply` ou o mesmo com kwargs novos: `conversation_id`
   explícito, `sender_user_id=None`, `operator_id=None`, `advance_recency=False`, `reopen_attendance=False`,
   `promote_qualification=False`, `human_outbound=False`; `sent_by_name="Lembrete automático"` e um marcador no
   doc da mensagem (ex.: `automation_kind="bot_reminder"` e a chave da etapa); **não** gravar doc `failed`;
   devolver o id e o código de erro; persistência fora do event loop. Credenciais do canal **da thread**
   (`get_channel(conv.channel_id)`, conferindo que o canal é do tenant), nunca `contact.channel_id`. A série A
   sai como mensagem com botões, no formato que o aviso já usa (`bot_transport.build_outbound_payload` aceita o
   dict `interactive_buttons`); a série B, como texto.
8. **Chaves para ligar:** env `FEATURE_BOT_REMINDER` (geral, default false) **e** o modo no doc do tenant,
   `settings.bot_reminder_mode` = `off` (default), `dry_run` ou `on`, que só a Castro grava por script **e** o
   liga/desliga da clínica (na fatia 1, também gravado por script; 4.6). O modo é também a chave comercial: o
   recurso é vendido, e só a Castro o liga, cliente a cliente (MA1, MA9). **Vocabulário fechado:** só a string
   exata `"dry_run"` ou `"on"` liga; qualquer outro valor (ausente, maiúscula, espaço, booleano, `"dry-run"`)
   vale `off`, como já fazem `tenant_followup_enabled` (`followup_routes.py:44`) e o `pool_mode`
   (`database_firestore.py:5013-5014`). O cron escolhe os tenants pelo cache de `list_tenants` (60 s) e, antes de
   cada envio real, relê o doc do tenant direto do Firestore, para que `off` pare os envios no mesmo tick. No modo
   **simulação** (`dry_run`) o cron faz tudo menos enviar: avança a etapa como simulada e grava uma linha de
   auditoria por envio simulado (id do contato, série, etapa e vencimento; sem texto). Assim cada etapa é
   registrada uma vez só e, ao virar para `on`, nada sai retroativo: a etapa simulada no ciclo corrente não sai
   depois da virada. No modo `on`, tetos e intervalo contam só envios reais; a lista simulada serve só ao
   `dry_run`. Sem coleção nova.
9. **Medição antes de ligar** (o medidor da seção 2): é ela que sustenta horários, tetos e a regra da cortesia. O
   medidor sai primeiro para os números chegarem antes da hora de ligar.

### 4.3 Quem recebe e quem nunca recebe [PROPOSTA]

Gate relido do banco imediatamente antes de cada envio, do mais barato para o mais caro. Todos verdadeiros:

| Onde | Condição |
|---|---|
| Tenant | ativo; modo `dry_run` ou `on`; motor CX ativo; `settings.ai.lgpd_by_agent` **não** é `True` (barrado no código, não só por configuração); `system_settings.bot_enabled`; liga/desliga da clínica |
| Thread | não é backup; `attendance_status` aberto; sem `assigned_to`; canal **standard**, ativo e do próprio tenant (coexistence fora); `bot_reminder_scope` permite a etapa; `last_bot_turn_at > last_inbound_at`; nenhum `last_human_outbound_at` nem `handoff_at` depois do último inbound |
| Janela | `agora <= last_inbound_at (thread) + 24 h − folga`; nunca o carimbo do contato |
| Ritmo | intervalo mínimo desde o último lembrete ao contato (4.4). Não há horário de silêncio (MA3) |
| Contato | existe; não arquivado; não backup; sem `assigned_to`; `bot_completed` falso; qualificação `novo` ou `em_atendimento` (o mesmo recorte do lote, `database_firestore.py:4518`); sem `lgpd_revoked`; sem `reopen_opt_out`; sem recusa comercial (`is_commercial_contact_blocked`); `contact.last_inbound_at <= last_bot_turn_at`; `last_bot_turn_at` posterior ao `bot_released_at`, quando existir |
| `bot_states` | `human_active` falso. **Série B** (depois do aceite): `lgpd_consent_resolved(state, contact)` verdadeiro (cobre a data da política; a revogação é a condição `sem lgpd_revoked` da linha Contato, que por isso é obrigatória). **Série A** (antes do aceite): `lgpd_status == "awaiting"` e `lgpd_consent` diferente de `False`; sem doc de estado, não envia. `lgpd_consent is False` (recusou): **nunca**, em nenhuma série |
| Desfecho | sem `bot_outcome` registrado nos últimos 7 dias (MA5) |
| Buffer | `bot_buffers/{contact_id}` sem itens e sem claim vivo |
| Tetos | etapa ainda não enviada neste ciclo; teto por contato em 24 h móveis e em 7 dias (MA1) |

Encerram o ciclo sem código extra, porque o gate barra: inbound novo, handoff, humano assumindo ou respondendo,
fechamento da thread, devolução ao bot e clique em "Encerrar atendimento" (é inbound, grava `reopen_opt_out`, não
gera turno do bot e o recibo não carimba).

Fora o caso do Encerrar, `reopen_opt_out` e recusa comercial ficam no gate por segurança e quase nunca mordem
(fato 7 da seção 3). O que de fato para os lembretes é a MA7.

**Nunca** enviar por `/api/wa/send` nem passar por `_check_conv_send_permission`: na Recepção isso silencia a Val
(`mark_human_active` + `mark_contact_bot_done`, `main.py:2677-2696`).

### 4.4 Horários — a análise que o PO pediu

Fatos:

- **A Meta não fixa número máximo de mensagens dentro da janela [META].** O teto duro é 24 h contadas da última
  ação do lead. Há um limite técnico de 1 mensagem a cada 6 s para o mesmo usuário (erro 131056). A política
  permite automação na janela desde que existam caminhos de escalonamento claros (transferência para atendente,
  telefone, e-mail ou formulário). De uma leitura só, sem segunda conferência: a política exige respeitar pedidos
  de parar; a orientação de frequência é genérica ("Avoid sending too many messages per day"); e a qualidade do
  número cai com bloqueios, denúncias, silenciamentos e arquivamentos.
- **O relógio é o Cloud Scheduler [CÓDIGO].** Não há Cloud Tasks nem agendamento por documento. Com tick de 5 min,
  "20 min" sai entre 20 e 25 min.
- **A Val responde 24×7 [CÓDIGO]** (`webhook.py:1744-1750`; `bot_service.py:878-894`). O único envio que hoje
  espera o expediente é o aviso de espera. Um lembrete de 4 h para quem escreveu às 22h cai às 2h da manhã; o PO
  decidiu enviar mesmo assim (MA3).
- **Mensagem fora da janela falha com o erro 131047 [META].** O `send_bot_reply` não trata esse código
  (`bot_sender.py:50-56`). **[A CONFIRMAR]** se ele volta na resposta do POST ou só depois, pelo webhook de
  status: a documentação manda monitorar os dois. Na resposta do POST, trate como "janela fechada": sem nova
  tentativa e sem alarme. Se ele só chegar pelo webhook de status (`_process_statuses`, que hoje apenas registra
  em log), o desejável é encerrar o ciclo daquele contato; diga na N3 se cabe na fatia 1.
- **[A CONFIRMAR]** se reação e clique de botão reabrem a janela da Meta. No CRM os dois movem o `last_inbound_at`
  da thread; se a Meta não renovar a janela nesses casos, o fim da janela calculado pelo CRM fica otimista.

**Dá para o tenant trocar os horários?** Sim, sem depender da Meta, dentro destes limites. As duas séries usam os
mesmos horários; o que muda entre elas é o texto.

| Regra | Proposta |
|---|---|
| Quantidade | por série, até 2 etapas "depois da fala" e 1 de "fechamento" |
| Etapa "depois da fala" | vencimento = `last_bot_turn_at + X`. X de no mínimo 10 min (abaixo disso briga com o turno da Val, que pode levar até cerca de 2 min, e com o tick) e no máximo 24 h − Y − 60 min (para não colidir com o fechamento) |
| Etapa de fechamento | vencimento = `last_inbound_at + 24 h − Y`. Y de no mínimo folga + 2 ticks: com folga de 5 min e tick de 5 min, **Y ≥ 15 min**; o PO decidiu por 20 min ("23h40", MA2) |
| Entre etapas | pelo menos 60 min entre vencimentos consecutivos |
| Entre lembretes | 60 min de intervalo mínimo entre dois lembretes ao mesmo contato, de qualquer ciclo |
| Fechamento perto da fala | o fechamento só sai se vencer pelo menos 60 min depois da última fala do bot; senão, é pulado e auditado. Cobre turno atrasado e turno enviado por uma thread que não recebeu o inbound (o flush do buffer pelo cron responde pelo primeiro canal do contato, `main.py:5293-5357`) |
| Acima de 24 h | não é mais lembrete de texto, é template (outra branch, seção 7) |
| Na tela | dizer "aproximadamente": o envio acontece no primeiro tick a partir do vencimento (até 5 min depois) |

Sobre o "23:50h" do pedido: a leitura adotada é "depois da última mensagem **do lead**", porque é daí que a Meta
conta a janela. Com Y = 10 min e folga de 5 min sobraria um tick só, e qualquer tick perdido perderia o lembrete.
O PO escolheu 23h40 em 10/11 (MA2).

Regras de horário. O PO decidiu em 10/11 que **não há horário de silêncio** (MA3):

1. A etapa sai no primeiro tick em que `agora >= vencimento` (vencimento que cai exatamente num tick sai nele), a
   qualquer hora e em qualquer dia da semana.
2. Duas etapas vencidas no mesmo tick: envia só a mais avançada e marca as anteriores como puladas.
3. **Intervalo mínimo adia; teto pula.** Etapa segurada pelo intervalo mínimo espera; etapa barrada pelo teto por
   contato não é reagendada. Etapa que, adiada, passaria do limite da janela é pulada.
4. Mais etapas vencidas do que o teto do tick: primeiro os fechamentos, do mais perto do limite da janela para o
   mais longe; depois as outras, por vencimento. O que sobrar fica para o tick seguinte; fechamento que não couber
   até o limite da janela é pulado e auditado.
5. Os tetos e o intervalo mínimo são **por contato e somam as duas séries**.
6. O fechamento só sai se vencer pelo menos 60 min depois da última fala do bot; senão, é pulado e auditado.

Casos de prova (etapas de 20 min e 4 h depois da fala; fechamento com Y = 20 min; folga 5 min; tick 5 min, nos
minutos múltiplos de 5; intervalo mínimo 60 min; teto de 2 etapas "depois da fala" por contato em 24 h móveis; 30
envios por tick; horários com os segundos zerados; em todos, a fala da Val tem uma pergunta de verdade).

Os casos usam relógio exato (`now=`). Na produção o tick roda segundos depois do minuto e o `last_inbound_at` tem
segundos reais: o tick que cai exatamente no limite da janela em geral já passou dele, e um intervalo de exatamente
60 min pode virar 65. Com Y = 20 min, conte com três ticks úteis para o fechamento.

| # | Situação | Resultado esperado |
|---|---|---|
| 1 | lead 22:40 (ter), Val 22:41 | B1 vence 23:01 e sai 23:05; B2 vence 02:41 e sai 02:45 de quarta; B3 vence 22:20 de quarta e sai 22:20 |
| 2 | no caso 1, o cron não roda às 22:20 | B3 sai 22:25; até 22:35 ainda envia; depois disso é pulada e auditada |
| 3 | configuração com Y = 10 min | o validador recusa: o mínimo é 15 min |
| 4 | lead 10:00, Val 10:01; B1 sai 10:25; lead responde "ok" 10:30, Val 10:31 | ciclo novo; a B1 do ciclo novo venceria 10:51 e espera o intervalo: sai 11:25; a B2 (14:31) é barrada pelo teto e pulada; a B3 do ciclo novo sai 10:10 do dia seguinte |
| 5 | lead 10:00, Val 10:01; lead de novo 13:00, Val 13:01 | B1 sai 10:25; ciclo novo: B1 sai 13:25; a B2 (17:01) é barrada pelo teto e pulada; B3 sai 12:40 do dia seguinte |
| 6 | lead 03:10, Val 03:11 (madrugada) | B1 sai 03:35; B2 sai 07:15; B3 sai 02:50 do dia seguinte. Madrugada e fim de semana não mudam nada |
| 7 | lead 22:40, Val só responde 23:25 | B1 sai 23:45; B2 sai 03:25; B3 sai 22:20 do dia seguinte |
| 8 | série A: primeira mensagem do lead 08:59, aviso da LGPD 09:00; ele não responde | A1 sai 09:20; A2 sai 13:00; A3 vence 08:39 e sai 08:40 do dia seguinte |
| 9 | no caso 8, o lead toca "Sim" 09:22; a Val responde 09:23 e ele some | ciclo novo, série B. A B1 venceria 09:43 e espera o intervalo desde a A1: sai 10:20; a B2 (13:23) é barrada pelo teto (A1 e B1 já são duas em 24 h) e pulada; B3 sai 09:05 do dia seguinte |
| 10 | no caso 8, o lead toca "Não" 09:22 | recusa: a despedida não arma nada, e nenhum lembrete sai enquanto a recusa valer, em nenhuma série. Se depois ele aceitar pelo "Sim" do lembrete da recusa, vale a série B |
| 11 | 150 fechamentos com vencimento às 22:20 (limite da janela 22:35) | 30 por tick, em quatro ticks (22:20 a 22:35, 120 envios); os 30 restantes são pulados e auditados no tick de 22:40 |
| 12 | 40 etapas "depois da fala" vencidas antes de 10 fechamentos, todos no mesmo tick | saem os 10 fechamentos e 20 das outras; as 20 restantes ficam para o tick seguinte |
| 13 | thread com último inbound ontem 10:30; hoje o lead escreve por outro canal 09:50 e o bot responde nesta thread 09:55 | B1 sai 10:15; o fechamento venceria 10:10, a 15 min da fala: é pulado e auditado; a B2 (13:55) cai depois do limite da janela (10:25) e é pulada |

O que quero de você na N2: confirme ou derrube essas regras e escreva a tabela-verdade completa (ela vira o
simulador). Sem a medição, 20 min e 4 h são palpite: nenhuma fonte, oficial ou não, mediu essa cadência.

### 4.5 Textos — os seis são do PO

O PO entrega os seis textos na sua sessão (decisão de 10/11). Eles formam duas séries:

| Etapa | Quando | Série A — pré-LGPD (lembrar do aceite) | Série B — pós-LGPD (retomar o atendimento) |
|---|---|---|---|
| 1 | 20 min depois da última fala do bot | A1 | B1 |
| 2 | 4 h depois da última fala do bot | A2 | B2 |
| 3 | 23h40 depois da última mensagem do lead (fechamento) | A3 | B3 |

O que fazer com eles:

- **Não viram default no código.** Entram na configuração do tenant (4.6), gravada por script. A lista de etapas
  e horários é uma só para as duas séries; em cada série, etapa sem texto fica desligada. Com o recurso ligado, o
  validador exige pelo menos um texto, e o dry-run do script mostra quais etapas ficam ligadas em cada série.
- **Confira cada um** contra a tabela "o que não escrever", logo abaixo, e contra os limites do validador. Achou
  problema: aponte na N1 e proponha a troca ao PO. Não reescreva por conta própria.
- **A série A sai com os botões do aviso [PROPOSTA]:** mensagem interativa com os mesmos botões (`lgpd_aceitar`
  "Sim" e `lgpd_recusar` "Não", `lgpd_bot.py:104-127`), para o toque entrar no gate que já existe. O corpo é o texto
  do PO, até 1.024 caracteres (`lgpd_bot.py:142`); acima disso o transporte corta o texto sem avisar
  (`bot_transport.py:29-33`), por isso o validador recusa antes. O gate também aceita "sim" digitado
  (`lgpd_bot.py:55-62`, `438-443`). Ela fala com quem ainda **não** aceitou a política de privacidade: o texto não
  leva nome nem dado nenhum do paciente.
- **A série B sai como texto simples**, na voz da Val.

Referência de voz, para a revisão (fonte: export do agente de 12/07 e serviços v4.11, fora desta worktree; a
produção roda versão posterior, então trate como referência, não como contrato): "você", feminino ("Obrigada"),
primeiro nome só quando ela mesma coletou, **sem emoji**, frases curtas (uma ideia por mensagem), sem saudação no
meio da conversa, sem promessa clínica, sem inventar data ou horário. No export, ela fecha turnos com "Posso te
ajudar em algo mais, {nome}?".

O que **não** escrever, e por quê:

| Evitar | Motivo |
|---|---|
| "Seu atendimento não foi concluído" | o template do lote disse isso a quem já tinha resolvido: dos 71 que clicaram Encerrar nas 24 h seguintes ao lote de 23/09, 46 tinham falado de agendamento com a Val e 10 tinham recebido o link (`docs/CX_RETOMADA_LOTE_DEV_IA.md:15-32`) |
| "Última chance", "sua vaga pode acabar" | urgência falsa; a Val não vê a agenda |
| Sintoma, especialidade, convênio, procedimento | dado de saúde numa notificação que aparece na tela bloqueada **[A CONFIRMAR com o jurídico: LGPD art. 11; política da Meta sobre informação de saúde]** |
| "Não deixe piorar", promessa de resultado, preço, desconto | **[A CONFIRMAR com o jurídico: Resolução CFM 2.336/2023, art. 11]**; e vira mensagem comercial |
| A URL de agendamento | conta como "a Val mandou o link" na heurística do lote (`database_firestore.py:4586-4613`) |
| "Nossa equipe vai te chamar" fora do expediente | promete o que não existe naquela hora |
| "Encerrei seu atendimento" | só se o CRM de fato encerrar algo; prefira "em pausa" |
| Emoji, "senhor/senhora", reapresentar a Val | fora da voz dela |

Regras para o validador: limite de caracteres (1.000 na série B, como o aviso de espera; 1.024 na série A, que é o
corpo de uma mensagem com botões), pelo menos um texto com o recurso ligado, e recusar texto que contenha o
`REOPEN_DESFECHO_LINK`.

### 4.6 Configuração, chaves e tela [PROPOSTA]

- **Config que o cron usa**, em `system_settings/chat`: ligado, os horários das etapas (iguais nas duas séries) e
  os seis textos (A1 a A3 e B1 a B3). O script de configuração lê os textos de um arquivo passado por parâmetro;
  não versione o arquivo com os textos da clínica sem o PO pedir. Molde: as
  três chaves `pool_wait_notice_*` (`database_firestore.py:4960-4969`, `4994-4996`, `5018-5051`; tela em
  `frontend/src/App.tsx:3546-3566`; tipos em `frontend/src/types.ts`; default em `CrmContext.tsx:405-430`). Para
  lista validada, veja `_clean_quick_messages` e `QuickMessagesEditor`.
- **Formato [CÓDIGO]:** chaves planas (ex.: `bot_reminder_text_a1`) ou lista de dicts, que o Firestore substitui
  inteira; **nunca mapa aninhado**. O `save_system_settings` grava com `set(..., merge=True)`
  (`database_firestore.py:5090`), que mescla mapas campo a campo e não apaga a chave que saiu. O mock dos
  simuladores faz `update` raso (`tools/sim_reception_flow.py:156-157`) e não mostra essa diferença.
- **Na fatia 1 não há tela, e isso tem uma armadilha [CÓDIGO].** O `GET` devolve todas as chaves de
  `_DEFAULT_SYSTEM_SETTINGS`, e a aba Sistema regrava o objeto inteiro a cada save
  (`database_firestore.py:4999-5010`, `5090`; `CrmContext.tsx:4032-4048`). Uma aba aberta antes do script
  devolveria os valores antigos ao salvar qualquer outra coisa. É o motivo pelo qual as chaves do lote e o
  `tags_global` não passam pelo `PUT` (`main.py:1515-1527`). Na fatia 1, **todas** as chaves do lembrete entram em
  `_CASTRO_ONLY_SETTINGS` (`main.py:1483-1484`) e são gravadas por script com dry-run, no molde de
  `scripts/set_reopen_flags.py`. A fatia 2 tira da tupla as chaves que a clínica passa a editar na aba Sistema (MA11),
  com a permissão `gerenciar_config_sistema`, sem permissão nova.
- **Cuidados com o save (já na fatia 1):** além do `PUT`, o upload de som (`main.py:1595-1598`) chama
  `save_system_settings` com o objeto inteiro lido na hora, sem o filtro de `_CASTRO_ONLY_SETTINGS` e sem tratar
  `ValueError` (viraria 500). Validação nova do lembrete só pode recusar quando o recurso está **ligado**, e o
  script valida antes de gravar. Esse caminho também grava no doc o default de toda chave ausente: padrão que
  precisar mudar depois muda por script, não pelo default do código. Na auditoria (`SYSTEM_SETTINGS_UPDATE`),
  troque cada texto pelo tamanho, como já se faz com `lgpd_notice` (`main.py:1539-1543`).
- **Chave da Castro** no doc do tenant (`settings.bot_reminder_mode`), gravada por script com dry-run no molde de
  `scripts/set_tenant_buffer.py`; o script recusa tenant com `lgpd_by_agent`. Prefira o doc do tenant porque
  `list_tenants` já o traz em cache e tenant desligado não lê nada. Uma chave em `system_settings` só seria segura
  dentro de `_CASTRO_ONLY_SETTINGS` (`main.py:1483-1484`, `1521-1527`); fora dela a tela a regravaria. Na fatia
  2, exponha o resultado na sessão (como `followup.enabled`, `main.py:768-770`) para a tela esconder o bloco.
- **O que o turno usa, também no doc do tenant [PROPOSTA]:** os dois escopos configuráveis (MA6 e MA13) e duas
  listas, gravados pelo mesmo script da chave. Nomes de exemplo: `settings.bot_reminder_courtesy_phrases` (frases
  de cortesia, MA6) e `settings.bot_reminder_stop_words` (palavras de parada, MA7). Ficam aqui porque o turno os lê
  do cache do tenant, sem leitura no Firestore (`get_tenant` é cacheado; `lgpd_bot.py:204-216` já usa assim). As
  duas listas são **obrigatórias na fatia 1**, e o código não traz lista padrão: proponha as duas na N3. A de
  cortesia parte da referência de voz da 4.5 ("Posso te ajudar em algo mais?" e variações); a de parada é curta
  (ex.: "pare", "parar", "sair", "não quero mais"). O PO aprova junto com os textos. Com a lista de cortesia
  vazia, o script recusa `dry_run` e `on`: sem ela, toda despedida da Val contaria como pergunta de verdade (R1).
  A parada vale para o turno em que aparece; um ciclo novo arma de novo.
- **Env** em `config.py` (lida uma vez no import): `FEATURE_BOT_REMINDER`, folga, intervalo mínimo, tetos por
  contato e teto de envios por tick. Na fatia 1 esses números são globais, sem override por tenant: trocar é mudar
  a env no Cloud Run, o que cria revisão nova a 0% de tráfego e pede promoção por nome (`CLAUDE.md`, Deploy).
- **Tela (fatia 2):** etapa como "aproximadamente", contador de caracteres, preview com `WaText`, `readOnly` do
  Ver como.
- **Selo no chat:** `sent_by_name="Lembrete automático"` já aparece como autor da bolha, sem campo novo no front.
  O marcador no doc da mensagem serve ao backend e à medição; só precisa de `types.ts` e `normalization.ts` se a
  tela for usá-lo.
- **Auditoria:** uma linha por envio, por falha, por etapa pulada e por envio simulado
  (`log_audit(None, "BOT_REMINDER_SENT" | ...)`), sem o texto. O padrão atual grava `conv=<canal>__<wa_id>`, que
  carrega o telefone; grave o id do contato.
- **Contagem de custo:** some um contador de lembretes no doc mensal de uso que já existe
  (`database_firestore.py:3852-3891`), sem coleção nova. Ele é por tenant; a franquia da Meta é por número. Como o
  recurso é vendido (MA1), é também o número que a Castro mostra ao cliente: conte por série e por etapa. O
  contador entra na fatia 1 e conta só envio real.

### 4.7 Contrato com a Val (opcional, fase seguinte — MA16)

A Val não sabe que o lembrete saiu. Dá para avisar no turno em que o lead responder, com `queue_cx_session_params`
no envio do lembrete (ex.: `{"lembrete_etapa": "4h"}`), sem turno sintético e sem custo de LLM. Cuidados:

- o parâmetro pendente não tem TTL e o fim de ciclo não tem evento. Guarde a data junto e ignore na leitura depois
  de 24 h;
- use chave própria (`origem` já é da `retomada_lote`);
- parâmetro com tipo diferente do declarado no agente já quebrou turno (por isso existe
  `settings.ai.omit_session_params`). Só enviar com opção ligada por tenant, depois de combinar com o dev de IA
  (Izael), no padrão de `docs/CX_RETOMADA_LOTE_DEV_IA.md`.

Descartado para o MVP: a Val redigir o lembrete por turno sintético. Custa LLM por lembrete, pode gerar handoff
indevido, grava memória como se fosse fala do paciente e não funciona para quem está no aviso LGPD (o gate roda
antes do agente).

### 4.8 O que NÃO pode quebrar

1. **Não silenciar a Val nem simular atendimento humano:** `sender_user_id` e `operator_id` sempre `None`. Um
   "usuário sistema" ali vira resposta humana em pelo menos cinco lugares (qualificação, `last_human_outbound_at`,
   `reopen_human_active_at`, balde do lote, monitor), além do rótulo no chat e das métricas por operador.
2. **Não subir recência nem reabrir atendimento:** `advance_recency=False` e `reopen_attendance=False`. A fase de
   bot divide com a Recepção o top-50 da pool sem dono (`CrmContext.tsx:1399-1402`); subir recência tira conversa
   real da tela das operadoras (mesma classe do incidente do history coex, no `CLAUDE.md`).
3. **Não mexer no lote de reabertura** (ele não muda nesta entrega, MA15): não usar `build_reopen_attempt_stamp`,
   `reopen_attempts`, `last_reopen_*`. O lembrete não pode virar "a Val mandou o link" (4.5) nem mudar o `{{2}}`
   do template (ele lê `last_message_at`). Ele move `last_outbound_at`, que
   `scripts/reopen_bot_audience_once.py:311-313` compara com a última resposta humana: confira que a classificação
   do script não muda.
4. **Event loop único:** Firestore síncrono em `run_in_threadpool`; nada de laço longo dentro de `async def`.
5. **Custo:** consulta do cron sempre com `.where(...)` no servidor; tenant desligado não lê thread nenhuma.
6. **Multi-tenant:** toda leitura por tenant fica dentro de `set_tenant_context` (com OIDC o request do cron nasce
   no contexto `hubloc`; com `X-Cron-Secret`, sem contexto).
7. **Buffer da Val:** o lembrete não escreve em `bot_buffers` e não dispara com item pendente ou claim vivo.
8. **Reentrega da Meta:** nada novo roda duas vezes em reentrega (`was_dup`); o desenho por comparação de carimbos
   não depende de reset no webhook.
9. **Janela:** nunca enviar sem conferir a janela pela thread no momento do envio.
10. **Trava de segurança proposta:** tenant com `settings.ai.lgpd_by_agent=true` nunca recebe lembrete, e o código
    recusa (hoje é a Hubloc, no agente Hugo: o CRM não tem prova de aceite nem de recusa lá). Só uma decisão
    explícita do PO, com o jurídico, remove a trava.
11. **Regras do Firestore:** campo novo em thread, contato ou mensagem não exige mudança. Coleção nova só de
    backend entra na lista negada do staging (`firestore.rules:494-502`) e no teste do emulador
    (`tools/impersonate_emulators/test.mjs`).

### 4.9 Testes e gates

Simulador novo (sugestão `tools/sim_bot_reminders.py`), exit 0/1, registrado no `CLAUDE.md`. Base: o mock de
`tools/sim_reception_flow.py` (tem `where` com range, `order_by`, `limit` e roda o `save_wa_message` real) com o
harness de cron de `tools/sim_pool_wait_notice.py`. Esse mock **não tem transação**: para a reivindicação da etapa
use o padrão `.to_wrap` de `tools/sim_buffer_flow.py:878-931`, ou teste a função transacional à parte. Relógio por
parâmetro `now=` nas funções puras.

Cenários mínimos (viram o critério de pronto da fatia 1):

1. Carimbo e agenda só no turno do bot enviado com sucesso; não no aviso de espera, no recibo, no lembrete nem em
   envio que falhou.
2. Tipo do turno: `cx_reply` arma a série B e `lgpd_notice` arma a série A; `engine_fallback`, `handoff`
   (inclusive com persistência falha) e `lgpd_refusal` não armam.
3. Resposta com o link não arma; `bot_outcome` recente barra (MA5).
4. Resposta sem pergunta de verdade (MA6) e pedido de parar (MA7). **Turno que não arma apaga a agenda do turno
   anterior** (ex.: turno armado, lead pede para parar, Val responde: nenhum lembrete sai).
5. Escopo `primeira`: sai a primeira etapa e nenhuma outra.
6. Cada etapa no seu vencimento e não antes; tick atrasado; duas etapas vencidas juntas.
7. Inbound encerra o ciclo e um turno novo abre outro; carimbo de inbound que recua não reinicia o ciclo.
8. Reação e clique de botão (MA8).
9. Handoff, humano assumindo, humano respondendo, thread com dono, thread fechada, devolução ao bot.
10. Clique em Encerrar; turno do Continuar do lote (MA13).
11. Série A: sai com os botões; o toque em "Sim" entra no gate, e o próprio turno do toque (confirmação do aceite
    mais a resposta da Val) abre a série B, se a resposta tiver pergunta de verdade (MA6). Se o agente falhar
    nesse turno, sai a mensagem de instabilidade e nada arma. O toque em "Não" encerra tudo; "sim" digitado também
    aceita. LGPD recusada, revogada com estado aceito e tenant com `lgpd_by_agent`: nada sai. Aceite anterior à
    data da política: a série B já armada não sai (o gate da 4.3 barra); quando o lead escreve de novo, o turno
    rebaixa o estado, o aviso sai de novo e a série A arma normalmente. É reconsentimento, não bloqueio.
12. Recusa comercial e `reopen_opt_out`.
13. Canal coexistence, canal inativo, canal de outro tenant, thread backup.
14. Contato com duas threads: um candidato só; evento de entrada em outro canal barra.
15. Os treze casos de prova da 4.4, mais o validador da configuração.
16. Borda da janela e erro 131047.
17. Tick duplo e duas instâncias: uma só envia.
18. Falha de envio não repete e não grava doc `failed`.
19. Tetos por ciclo e por contato, somando as duas séries (teto pula); intervalo mínimo (adia); etapa adiada
    para depois do limite da janela é pulada.
20. Tenant desligado não lê thread; tick sem nada vencido não lê thread.
21. Texto vazio; texto com o link; etapa editada no meio do ciclo.
22. Modo simulação: não envia, registra uma vez por etapa, respeita os mesmos tetos e nada sai retroativo ao virar
    para `on`.
23. Depois do lembrete: recência, não-lido e `attendance_status` intactos; o lote de reabertura e o script
    one-off enxergam o lead igual a antes.
24. Na fatia 1: um `PUT /api/settings/system` com o objeto inteiro e valores antigos não muda nenhuma chave do
    lembrete (molde: `tools/sim_reception_flow.py:1804-1816`), e o upload de som (`main.py:1595-1598`), com a
    configuração do lembrete gravada, responde 200 sem alterá-la.
25. Madrugada e fim de semana: a etapa sai no horário, sem adiar (MA3).
26. Gate que barra limpa ou adia a agenda: a thread morta não volta à consulta no tick seguinte.
27. Contador do uso mensal por série e etapa (simulado e falha não contam) e auditoria com o id do contato, sem
    telefone nem texto.
28. Modo do tenant fora do vocabulário (`"On"`, `True`, `"dry-run"`) vale `off`; `off` gravado no meio do tick para
    os envios seguintes; com o modo em `off`, o turno não grava carimbo nem agenda.
29. Lista de cortesia vazia: o script recusa `dry_run` e `on`. Precedência de escopos: Continuar sem pergunta de
    verdade dá `nenhuma`; "pare" respondido com "não entendi" dá `nenhuma`.

Gates (Python da pasta principal: `C:\Rafael\castro-intelligence\.venv\Scripts\python.exe`):

- `py_compile` dos módulos tocados e do módulo novo (lista no `CLAUDE.md`);
- `tools\sim_bot_flow.py` (76), `tools\sim_cx_flow.py` (241), `tools\sim_reception_flow.py` (350),
  `tools\sim_buffer_flow.py` (69), `tools\sim_pool_wait_notice.py` (48), `tools\sim_monitor_flow.py` (73),
  `tools\sim_history_recency.py` (62), `tools\sim_impersonate.py`, `tools\sim_impersonate_views.py` e os do
  follow-up (`sim_followup_flow`, `sim_followup_api`, `sim_commercial_contact_policy`, `sim_followup_send_guards`);
- em `frontend/`: `npm run build` (`npm ci` já foi rodado nesta worktree) e `node tools\check_wa_format.mjs`;
- na raiz: `node tools\sim_followup_frontend.mjs`, `node tools\sim_followup_lifecycle.mjs`,
  `node tools\sim_chat_tabs.mjs`;
- se surgir coleção nova: o emulador de `tools/impersonate_emulators/`.

Documentação junto com o código: ADR novo em `docs/decisions/` (use o próximo número livre no dia — há um ADR do
coexistence planejado que pode ocupar o 0015), linha do simulador e invariante no `CLAUDE.md`, e a emenda em
`docs/followup_crm_varizemed.md` (linhas 55, 562, 585, 587 e 591) conforme a decisão da MA1: o lembrete não entra na
lista `reopen_batch_sent_at` nem no teto de 2 envios em 90 dias, e tem tetos próprios.

### 4.10 Fora do seu escopo (o Claude e o PO fazem)

- Rodar o script de medição em produção assim que ele ficar pronto, e trazer os números para a decisão de ligar.
- Job novo no Cloud Scheduler. Atenção para quem criar: `CRON_OIDC_AUDIENCE` é única e exata; o job novo usa o
  `--uri` do endpoint novo com a **mesma** `--oidc-token-audience` do `expire-takeovers`
  (`docs/deploy/env.oregon.yaml:49-50`; `docs/internal/2026-05-24.md:179-180`).
- Ligar `FEATURE_BOT_REMINDER=true` no Cloud Run, junto com o job do Scheduler: sem ela, nem o modo simulação
  roda.
- Gravar a configuração do tenant com os seis textos e as duas listas, pelos scripts da 4.6.
- Ligar o modo simulação, primeiro no `varizemed-test`; depois a Varizemed.
- Virar o modo para `on` só depois do critério da MA17 e do OK do PO.
- Conferir no Billing Hub a forma de pagamento da conta de mensagens (fato 2 da seção 3).

---

## 5. Riscos do desenho (para a N3)

| # | Risco | Mitigação proposta |
|---|---|---|
| R1 | **Conversa já encerrada recebe lembrete.** No export do agente, quase todo turno fecha com uma pergunta de cortesia; "obrigado" → "Posso te ajudar em algo mais?" → silêncio armaria três lembretes. O teto por contato **não** protege o primeiro ciclo | o escopo do turno, conforme a MA6, com a lista de frases de cortesia obrigatória (4.6); depois, um sinal do próprio agente |
| R2 | Lead que recebeu o link e sumiu ainda não tem `bot_outcome` | o turno com o link não arma; `bot_outcome` recente barra (MA5) |
| R3 | Bloqueios e denúncias derrubam a qualidade do número, que é o canal inteiro da clínica | medição, modo simulação, teto baixo, textos sem tom de cobrança. Sem horário de silêncio (MA3) há lembrete de madrugada: acompanhar bloqueios e a qualidade do número na primeira semana |
| R4 | Custo por lembrete acima da franquia; pelos registros, a fatura chega à Castro | contador mensal; MA10 |
| R5 | Corrida: o lead escreve entre a releitura e o POST | aceitar o resíduo; a transação e a checagem do buffer reduzem a janela |
| R6 | Lead manda foto depois da fala da Val (foto não gera turno) | a comparação de carimbos já barra, porque a foto é inbound; conferir no simulador |
| R7 | Lote e lembrete se somam nos dois sentidos: o lead ignora o fechamento e recebe o template do lote no dia seguinte; ou clica Continuar no template e o turno da Val arma lembretes | MA13 para o Continuar; o lote não muda nesta entrega (MA15) |
| R8 | Resposta ao lembrete de 4 h perde contexto na Val (sessão nova) | textos que convidam a responder com frase completa; contrato da 4.7 depois |
| R9 | Lead pede para parar e a Val responde com cortesia; opt-out e recusa não barram (fato 7) | conforme a MA7 |
| R10 | Mensagem de instabilidade do motor ou handoff com persistência falha seguidos de "continuo te ajudando" | o tipo do turno não arma (4.2 item 3) |
| R11 | Muitas etapas vencidas no mesmo tick | teto por tick, com o fechamento primeiro (4.4, regra 4) |
| R12 | Fim de janela calculado com reação ou clique, que talvez não renovem a janela na Meta | tratar 131047 como janela fechada; **[A CONFIRMAR]** |
| R13 | Contato com mais de uma thread standard | um candidato por contato; teto no contato; carimbo de entrada do contato no gate |
| R14 | Na fatia 1 o motor vai para produção sem a tela: uma aba Sistema aberta regravaria a configuração do lembrete com valores antigos | chaves do lembrete em `_CASTRO_ONLY_SETTINGS` até a fatia 2 (4.6) |
| R15 | A série A fala com quem ainda não aceitou a política de privacidade | texto sem nome e sem dado do paciente; botões do próprio aviso; quem recusou nunca recebe (4.3, 4.5) |
| R16 | Depois do aceite, o toque em "Não" de um aviso ou lembrete antigo vai à Val como o texto `lgpd_recusar` e não registra recusa (`lgpd_bot.py:417-418`). Já acontece com o aviso; a série A põe até três mensagens a mais com esse botão | o simulador registra o comportamento; a decisão de tratar vai ao PO pela N3. **Tratado em 2026-11-13** (emenda do ADR 0009): o toque em "Não" depois do aceite vale como recusa e o segundo toque em "Sim" é ignorado |

## 6. Decisões do PO

MA = mensagens automáticas (o prefixo evita confusão com o "D4" do `CLAUDE.md` e com o D1–D10 do plano de
reabertura). **Nenhuma decisão segura o código** (seção 0, item 4): o que o PO já decidiu está na última coluna;
para o resto, o código sai com a recomendação como padrão. "Trava ligar" = o modo `on`, que envia de verdade, só
é ligado depois dela. O modo simulação (`dry_run`) pode rodar antes, porque não envia nada.

| # | Decisão | Recomendação do Claude (padrão no código até a decisão) | Trava ligar | Decisão do PO (data) |
|---|---|---|---|---|
| MA1 | O lembrete da Val conta no teto de 2 envios/90 dias e no orçamento diário do lote? Hoje os docs dizem que sim e proíbem contador paralelo (`followup_crm_varizemed.md:55`, `562`, `585`, `587`, `591`) | **Não contar.** É continuidade da conversa que o lead abriu, dentro da janela; não consome o limite de mensagens da Meta (mas custa, MA10). Tetos próprios: cada etapa uma vez por ciclo; por contato, em 24 h móveis, até 2 etapas "depois da fala" (o fechamento não entra nessa conta); até 6 lembretes em 7 dias; 60 min entre dois. A emenda altera as cinco linhas e mantém os bloqueios de LGPD | não | **Não conta** (10/11: "não deve contar, vamos vender esse recurso"). Os tetos próprios ficam como padrão configurável |
| MA2 | O "23:50h" é (a) 23h50 depois da fala da Val, (b) 23h50 depois da última mensagem do lead ou (c) o horário 23h50? Com que folga? | (b), tratado como "fechamento": 23h40 com o cron de 5 min. 23h50 exato exigiria job de 1 min e folga de até 3 min — não recomendo | não | **23h40** depois da última mensagem do lead (10/11) |
| MA3 | Horário de silêncio: qual faixa? O que fazer com etapa que cai nele? A primeira etapa fica isenta? Fim de semana e feriado enviam? (O follow-up humano do piloto não contata no fim de semana: `followup_crm_varizemed.md:51`, `490`. Vale para o lembrete da Val?) | Silêncio das 21h às 8h, com a primeira etapa isenta; fim de semana envia (recomendação não adotada) | não | **Enviar a qualquer hora**, inclusive madrugada e fim de semana; sem horário de silêncio (10/11) |
| MA4 | Lead parado no aviso LGPD, sem aceite, recebe lembrete? Quantos? | Um (escopo `primeira`), com os botões Sim/Não. Quem recusou, nunca. Validar com o jurídico (o PO decidiu por três) | não | **Três lembretes, a série A** (A1 a A3), lembrando do aceite (card do quadro, 10/11). Quem recusou não recebe |
| MA5 | Lead que já recebeu o link de agendamento recebe? | Não no MVP: turno com o link não arma e `bot_outcome` dos últimos 7 dias barra | não | |
| MA6 | Como evitar lembrete em conversa já encerrada (R1)? Opções: (a) o turno só arma se a resposta tiver uma pergunta que não seja frase de cortesia; (b) resposta só com cortesia arma apenas a primeira etapa; (c) sinal do próprio agente | Decidir com a medição. Se a classificação por texto se mostrar confiável, (a); senão, (b). (c) é o alvo, depende do dev de IA. **Padrão no código: (a)**, a mais conservadora; (a) e (b) são o mesmo código com um valor de configuração diferente | não | |
| MA7 | Como o lead para os lembretes? Opções: (a) palavras de parada detectadas no CRM; (b) botão na última etapa (exige roteamento próprio: hoje botão interativo vira texto para a Val); (c) só o teto | (a) com lista curta, mais o teto | não | |
| MA8 | Reação e clique de botão contam como "respondeu"? | Sim (hoje já movem o `last_inbound_at` da thread) | não | |
| MA9 | Só Varizemed agora? | Sim; `varizemed-test` primeiro | não | O recurso é vendido: a Castro liga cliente a cliente (10/11) |
| MA10 | Custo de R$ 0,035 por lembrete acima da franquia. Pelos registros, a fatura da Meta chega à Castro: repassa ao tenant? Teto mensal? | Aceitar e medir; contador de lembretes no uso mensal; decidir o repasse | não | O recurso será vendido (10/11); preço e repasse ficam com o PO |
| MA11 | Quem edita textos e horários: admin da clínica ou só a Castro? | Clínica edita (fatia 2); até lá, por script | não | |
| MA12 | Como o lembrete aparece para a equipe no chat? | Autor "Lembrete automático" | não | |
| MA13 | Lead que voltou pelo Continuar do template do lote recebe lembretes? | Só a primeira etapa nesse ciclo (escopo `primeira`) | não | |
| MA14 | Quem aprova os textos finais? | A clínica (Cristina), antes de ligar (superada: o PO assumiu os textos) | não | Os seis textos vêm do PO, entregues ao Codex (10/11) |
| MA15 | O lote de reabertura deve esperar algum tempo depois do último lembrete? | Não mexer no lote nesta entrega; reavaliar com os números do piloto | não | |
| MA16 | Avisar a Val por parâmetro de sessão (4.7) agora ou depois? | Depois, desligado por padrão; é combinação técnica com o dev de IA | não | |
| MA17 | Critério para sair do modo simulação | Alguns dias de simulação, revisão dos números por etapa, N1 resolvida, forma de pagamento conferida no Billing Hub (4.10) e OK do PO | sim | |

O que muda se o PO decidir diferente nas que faltam:

- **Só configuração, por script e sem deploy:** MA6 entre (a) e (b); a lista de palavras da MA7, ou desligá-la
  (opção c); MA13; MA9 (ligar outro tenant).
- **Env, com revisão nova no Cloud Run:** os números dos tetos próprios (MA1) e o intervalo mínimo.
- **Código a mais:** MA5 com lembrete (hoje é regra fixa: o turno com o link não arma e o `bot_outcome` recente
  barra; um texto próprio para esse caso seria o sétimo); MA6 na opção (c) (depende do agente); MA7 na opção (b)
  (botão com roteamento próprio); MA8 se reação ou clique **não** contarem como resposta (os dois movem o
  `last_inbound_at` da thread, base do ciclo; seria preciso um carimbo próprio); MA10 com teto mensal (gate novo
  lendo o uso mensal); MA15 se o lote tiver de esperar o lembrete (mexe no lote, que a 4.8 item 3 congela); MA16
  agora (4.7); horário de silêncio, se a MA3 for revista (regras novas de adiar e antecipar).
- **Código a menos:** MA11 com "só a Castro edita" dispensa a fatia 2.

---

## 7. Templates criados pelo tenant — saíram desta branch

Em 10/11 o PO separou os assuntos. Tudo sobre templates (como funcionam hoje, o que a Meta permite, o plano em
fases T0 a T5 e as perguntas) está em `docs/HANDOFF_TEMPLATES_POR_TENANT.md`, na branch
`feature/templates-por-tenant` (worktree `C:\Rafael\castro-intelligence-templates-tenant`).

O que liga os dois trabalhos:

- lembrete **dentro** da janela de 24 h é texto livre e é desta branch; lembrete **depois** de 24 h é template e é
  a fase T4 de lá, que depende deste motor em produção;
- "escolher a mensagem" já sai aqui, como texto editável; escolher um template é de lá.

## 8. Regras do repositório e processo

- `CLAUDE.md` vale inteiro: comentários e docstrings em pt-BR **sem acento**; strings ao cliente com acento;
  `# -*- coding: utf-8 -*-` em todo `.py` da raiz; logger `castro_crm.<modulo>`; nunca PII nem token em log
  (`pii_redaction.py`); flags por env em `config.py`.
- Sem dependência nova no backend nem no frontend sem combinar.
- Commit e PR só a pedido de quem conduz a sessão. Nesse caso: commits pequenos, `git fetch` e rebase sobre
  `origin/develop`, PR contra `develop` descrevendo o que entrou, o que ficou de fora e os números dos gates.
- Arquivos quentes divididos com outras frentes: `main.py`, `database_firestore.py`, `webhook.py`, `config.py`,
  `frontend/src/App.tsx`, `CrmContext.tsx`. Prefira módulo novo (ex.: `bot_reminders.py`) e toques mínimos neles.
- É um hotfeature: o PR da fatia 1 leva só o que a 4.9 pede. Nada de refatoração de passagem.

## 9. Achados fora do escopo (não corrija nesta branch; não copie o padrão)

1. **Falha de autorização entre tenants (severidade alta, fora desta branch).** Endpoints que recebem `channel_id`
   não conferem de qual tenant é o canal (`get_channel` não filtra, `channel_service.py:114-118`). Está registrada
   no quadro de pendências da Castro e o Claude corrige à parte. **Regra para todo endpoint novo desta branch:**
   comparar `channel.tenant_id` (ausente = `hubloc`) com o tenant do contexto e responder 404 quando forem
   diferentes.
2. O `CLAUDE.md` diz que clique não desfaz a recusa comercial. No código, só o clique de avaliação válido é
   mensagem de controle (`webhook.py:1606`, `1633`); o clique em botão quick-reply de template e o clique em botão
   interativo (que vira texto, `webhook.py:1555-1561`) desfazem a recusa (`database_firestore.py:3553-3568`).
3. `bot_media_turn_enabled` existe nas configurações mas não tem consumidor: imagem, vídeo, documento e figurinha
   na fase de bot não geram turno (o áudio gera, pela transcrição).

## 10. Fontes da Meta (lidas em 2026-11-10)

Base: `https://developers.facebook.com/documentation/business-messaging/whatsapp/` + caminho abaixo.

| Tema | Caminho |
|---|---|
| Preço, janela de atendimento, franquia de serviço | `pricing` |
| Envio, qualidade | `messages/send-messages` |
| Códigos de erro (131047, 131056) | `support/error-codes` |
| Limites por portfólio | `messaging-limits`, `upcoming-messaging-limits-changes` |
| Limite por par e vazão | `about-the-platform`, `throughput` |

As fontes sobre templates, modelo de conta, Tech Provider e marketing foram com o plano de templates para o
handoff da outra branch (seção 7).

Outras: Política de Mensagens do WhatsApp Business (`https://whatsappbusiness.com/policy/`); tabela de preços do
Brasil pela calculadora oficial (`https://whatsappbusiness.com/products/platform-pricing/`); Resolução CFM
2.336/2023; LGPD (Lei 13.709/2018), arts. 5º, 8º e 11.

## Resposta do Codex — 2026-11-11

### Decisoes alinhadas nesta sessao (prevalecem sobre as propostas anteriores)

- Apenas tres mensagens pos-aceite LGPD. Sem serie A. Recuperacao de pendentes LGPD pertence a outra frente.
- Padroes: 20 minutos e quatro horas apos a resposta da Val; 23h40 apos ultima entrada do lead.
  Cron de cinco minutos; envio aproximado, inclusive madrugada e fim de semana.
- Mensagem nova cancela a sequencia anterior, inclusive midia. Resposta posterior elegivel pode iniciar outra.
- Link na resposta atual nao arma. Entrada nova e resposta sem link podem armar outro ciclo.
  Nao aplicar bloqueio por `bot_outcome` antigo nem pelo periodo de sete dias.
- Cortesia/despedida sao classificadas por texto no CRM. Pedidos diretos de dados sem interrogacao tambem podem
  armar. Nao depender de mudanca no agente. Heuristica conservadora; pode ser evoluida por sinal explicito da Val.
- Comandos exatos normalizados `PARAR LEMBRETES` e `ATIVAR LEMBRETES`, com preferencia propria persistida.
  Inbound comum nao desfaz a parada. Nao alterar LGPD, recusa comercial ou lote. A instrucao de parada e
  acrescentada automaticamente ao texto, inclusive na previa.
- Sem tetos de duas etapas/24h, seis/semana ou intervalo de uma hora. Permanecem uma tentativa por etapa/ciclo,
  transacao, limite tecnico do tick e janela Meta. Continuar da reabertura segue a regra normal.
- Tela nesta entrega: Administracao > Sistema > Lembretes automaticos. Toggle, tres textos, previa,
  contador de caracteres e ajuste de intervalos. Permissao `gerenciar_config_sistema`; Ver como somente leitura.
- Env geral desligada por default e modo comercial por tenant controlado pela Castro. Sem execucao em producao,
  commit, push ou deploy nesta sessao sem pedido explicito.

### N1 — Textos

Os tres textos finais nao foram fornecidos. Nao foram inventados nem incluidos como defaults. A clinica pode
preenche-los na tela; etapa vazia fica desativada. Pelo menos um texto e obrigatorio para ligar. Maximo de
1.000 caracteres por campo, sem o link de agendamento. Revisao editorial pendente dos textos reais.

### N2 — Horarios: tabela-verdade

| Situacao | Resultado |
|---|---|
| Etapa ainda nao venceu | Aguarda vencimento |
| Venceu, gates verdadeiros, janela valida | Envia no tick |
| Duas etapas venceram | Envia a mais avancada; pula anteriores |
| Mensagem nova de qualquer canal | Cancela ciclo anterior |
| Lead responde e a Val aguarda outra informacao | Novo ciclo e contagem |
| Link na resposta atual, cortesia, falha ou handoff | Nao arma; limpa agenda anterior |
| Foto/audio sem resposta nova da Val | Cancela; nao abre outra sequencia sozinho |
| Sem aceite valido, revogacao, parada, humano, canal invalido ou thread fechada | Cancela agenda |
| Buffer pendente ou claim vivo | Adia cinco minutos; revalida a janela |
| Texto vazio | Desativa etapa |
| Horario editado no ciclo | Recalcula vencimento; identidade da etapa e preservada |
| Fechamento a menos de uma hora da fala do bot | Pula fechamento |
| Apos janela menos cinco minutos | Pula, sem tentativa tardia |
| Mais candidatos que capacidade do tick | Prioriza fechamentos; restante aguarda outro tick |
| Falha no POST ou resultado incerto | Nao repete etapa |
| Simulacao | Registra uma vez; nao envia nem conta uso real |
| Mudanca de modo comercial ou desligar/religar na tela | Invalida agenda anterior; exige nova resposta elegivel |
| Madrugada/fim de semana | Mesmas regras |

Primeiro >=10 minutos; pelo menos 60 minutos entre vencimentos configurados; ultimo pelo menos 15 minutos
antes das 24h. Isso nao e intervalo minimo entre envios de ciclos distintos.

### N3 — Alteracoes estruturais e limites

- Carimbo em transacao propria apos envio confirmado, com entrada capturada ANTES de aguardar o agente.
  Leituras/escritas adicionais impedem turno atrasado de sobrescrever cancelamento por entrada posterior.
- Ponteiro de ultima thread no contato e claim transacional evitam envio concorrente por canais diferentes.
- Geracao comercial muda ao trocar modo; geracao da configuracao muda ao desligar/religar. Nada retroativo.
- API dedicada de configuracao com versao contra formulario antigo. Save geral e upload de som preservam campos.
- Medidor `tools/bot_reminder_measure.py`: classificador real, escrita bloqueada, saida agregada. Autoria e
  consentimento historicos nao sao reconstruidos com precisao; estimativa separa conversas ainda em observacao
  da ausencia de resposta apos 24h. O medidor nao foi executado contra ambiente real.
- Uso mensal por serie B/etapa mede envio aceito/persistido, nao conciliacao da cobranca por entrega.
- Erro 131047 sincrono encerra agenda; cancelamento via status assincrono fica para evolucao. Resta a corrida
  entre ultima checagem e POST externo; entrada e preferencia sao relidas antes do POST.

Operacao posterior do PO: criar Scheduler com audiencia OIDC existente, habilitar env e usar
`python -m scripts.set_tenant_bot_reminders --tenant varizemed-test --mode dry_run` (dry-run por default;
`--yes` aplica). Preencher tela, ativar e observar simulacao. Trocar para `on` apenas com OK do PO.
Nenhuma dessas operacoes foi executada pelo Codex. ADR: `0015-lembretes-automaticos-pos-aceite.md`.

Validacao local: `py_compile`, simulador novo (125 verificacoes), CX ampliado (246), demais simuladores
obrigatorios do `CLAUDE.md`, gates JavaScript (follow-up, lifecycle e guias), `npm ci`, build estrito e
formatacao WhatsApp aprovados. Sem colecao nova, sem alteracao das rules e sem execucao do medidor em producao.
