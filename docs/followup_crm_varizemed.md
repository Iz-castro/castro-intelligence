# Follow-up no Castro Intelligence CRM — revisão da operação Varizemed

**Revisão:** 18/10/2026. **Frente:** `feature/followup`, neste worktree, a partir de `develop`.
**Status:** F1 implementada localmente após autorização do PO em 18/10, sob flag desligada por padrão; sem alteração de produção. Inclui tarefas humanas, histórico contínuo, filas Recepção + Orçamentos, calendário e preferência comercial comum. O ciclo atual de retorno à Val está preservado. As decisões 1–9 permanecem registradas; automações futuras e o objetivo compartilhado de **500 envios/dia** dependem da integração comum e da capacidade Meta. O limite de 2 envios/90 dias não foi alterado. Detalhes da entrega, testes e preparo de liberação na seção 16.
**Fontes:** pedido do PO de 07/10, respostas de Cristina encaminhadas pelo PO em 08/10, esclarecimento do PO em 09/10 sobre apresentação do orçamento pelas operadoras e imagens dos filtros/qualificações e tags, decisões 1–3 do PO em 13/10, pergunta sobre retorno à Val, pedido de menu de horários, aprovação da sugestão de dia útil anterior e aprovação em 17/10 do tratamento de agendamento de última hora discutido em 14/10 e aprovações em 18/10 da extensão do contato único a coincidências após ajuste de calendário, do significado de AGENDOU como consulta ou procedimento/tratamento, da distinção entre recusa específica e recusa geral de contatos comerciais, da continuidade com prazo humano/revisão após três tentativas sem resposta, da referência do aviso de resposta após a última tentativa, da abrangência provisória dos limites para automações futuras, da solicitação de teto compartilhado de 500/dia e do esclarecimento do uso de `varizemed-test` pela Castro Intelligence, código local, ADRs e CSV `VENDAS - ORÇAMEN - Página1.csv`. A análise do CSV é de 07/10; as respostas esclarecem sua semântica, sem alterar as contagens. Esta versão atualiza as revisões de 05/10 e 07/10 nos pontos indicados na seção 13.

## 1. Evidência e objetivo

Usar os marcadores abaixo para distinguir origem e grau de certeza:

- **[OBSERVADO NO CÓDIGO]**: comportamento ou estrutura encontrados no worktree; não prova o estado atual de produção.
- **[OBSERVADO NA PLANILHA]**: estrutura, preenchimentos e padrões do CSV; não prova a intenção de quem preencheu.
- **[DECISÃO DO PO]**: definição expressa no pedido atual ou regra herdada da sessão.
- **[CONFIRMADO COM CRISTINA — 08/10]**: informação operacional recebida nesta sessão; não comprova integração implementada ou estado de produção.
- **[HIPÓTESE]**: interpretação ou desenho recomendado, ainda sujeito a validação.
- **[VALIDAR COM CRISTINA]**: dúvida operacional que não pode ser resolvida pelo código ou CSV.

**[DECISÃO DO PO]** O núcleo é **Contact + Conversation + Task + Activity**. `wa_contacts` e `wa_conversations` são reutilizados; entidades novas de F1 são `crm_tasks` e `crm_activities`. A implementação se adapta ao CRM, sem nova entidade Lead ou refatoração estrutural ampla.

O resultado desejado é **operadora agenda → CRM lembra → equipe executa**. Criadora e executora podem ser pessoas diferentes. A tarefa mantém ação, contexto mínimo, prazo, responsabilidade e histórico; mensagens e dados comerciais permanecem em suas fontes próprias.

**[CONFIRMADO COM CRISTINA — 08/10]** A operação é colaborativa: novos leads ficam mais com a Recepção; pacientes que receberam orçamento após consulta médica ficam mais com o Administrativo. Isso esclarece o encaminhamento do trabalho, sem substituir as regras atuais de acesso. O nome da fila de tarefas correspondente a esse trabalho foi aprovado como Orçamentos em 13/10.

**Esclarecimento operacional do PO em 09/10:** nesse fluxo, consulta é a consulta médica com o médico da clínica. O orçamento geralmente é apresentado pelas operadoras; o atendimento comercial e as retomadas são realizados pela equipe. Não atribuir ao médico a apresentação do orçamento ou a execução do follow-up.

Esta revisão é local, sem rede, consultas de produção, importação da planilha ou alteração do outro worktree. O CSV foi analisado em memória, sem copiar nomes, telefones, notas clínicas ou linhas individuais para o repositório. Estatísticas abaixo contam registros, não pacientes únicos nem contatos já existentes no CRM.

## 2. Escopo decidido

### F1 — follow-up humano

**[DECISÃO DO PO]** F1 funciona independentemente de F2/F3 e inclui:

- Criar, editar, listar, pegar, atribuir, concluir, cancelar e adiar tarefas.
- Registrar tentativa, resultado, quem tentou, quando tentou e eventual reagendamento; visualizar histórico.
- Filas Recepção e Orçamentos; Atrasadas, Hoje, Próximas, Concluídas e Canceladas. Em 13/10, o PO aprovou os nomes e Devolver à fila ao reagendar como padrão, com Manter comigo como exceção explícita.
- Próxima ação no contato: tarefa `pending` com menor `due_at`, com desempate determinístico por ID.
- **[DECISÃO DO PO — 18/10]** Sinal visual de resposta após a última tentativa real; antes da primeira, desde a criação da tarefa. Apenas adiar mantém referência/aviso, e mensagem não conclui a tarefa.
- Contexto acessível sem assumir contato/conversa ou concluir a tarefa.
- **[DECISÃO DO PO — 18/10]** Registrar dois escopos de recusa: apenas aquele orçamento/acompanhamento ou novas retomadas comerciais do paciente. O segundo exige preferência estruturada no contato e integração com os produtores comerciais existentes antes da liberação, conforme seção 7.5; consultas e tarefas independentes são preservadas.
- **[DECISÃO DO PO — 13/10]** Menu de configuração dos horários de follow-up para Cristina/gestão autorizada. Dias e faixas horárias, feriados e tratamento dos prazos são detalhados como proposta na seção 9; o pedido do menu não define seus valores ou autoriza mensagens automáticas.

**[DECISÃO DO PO]** F1 não inclui envio WhatsApp pelo módulo/vencimento, IA criando tarefas, nova classificação de lead, Automation Engine, Kanban completo, múltiplas oportunidades, agenda integrada sem fonte ou campanhas automáticas.

Atraso é calculado por `status=pending AND due_at < agora`, sem persistir `overdue` ou criar cron apenas para mudar status. Abrir contato/conversa, chegar o prazo, receber inbound ou registrar entrega/leitura não concluem tarefas.

### F2 — criação automática por eventos explícitos, futura

**[DECISÃO DO PO]** Algumas tarefas poderão nascer de eventos comprovados, como orçamento registrado ou consulta confirmada em fonte confiável. Não implementar nesta entrega. Não inferir esses eventos de link, texto livre, intenção de agendar ou silêncio.

**[CONFIRMADO COM CRISTINA — 08/10]** O retorno deve ser combinado individualmente. **[HIPÓTESE]** Orçamento → tarefa em dois dias continua apenas como candidato para casos específicos sem combinação; nenhum prazo universal está aprovado. F2 deverá respeitar a data combinada e a regra de não contatar no fim de semana. Eventos, duplicação por revisão de orçamento e eventual `complete_on_reply` dependem de desenho posterior.

### F3 — eventuais mensagens automáticas, futura

**[DECISÃO DO PO]** Automação de mensagem é separada de Task e usa as mesmas políticas de LGPD, opt-out, canal, limites e orçamento da reabertura, sem contador paralelo. Não implementar nem escolher um motor genérico agora. Contratos herdados e pré-requisitos estão na seção 11.

## 3. Fatos do código e implicações

| Evidência | Implicação para o desenho |
|---|---|
| **[OBSERVADO NO CÓDIGO]** Contato único por `wa_id` dentro do tenant; conversa com `contact_id` e ID `{channel_id}__{wa_id}` ([database_firestore.py](../database_firestore.py#L1869)) | Referenciar IDs existentes; não duplicar contato, conversa ou telefone na tarefa. |
| **[OBSERVADO NO CÓDIGO]** Posse do contato, atribuição da thread e `sale_owner` são distintos; `sale_owner` fica inerte em Recepção ([database_firestore.py](../database_firestore.py#L2543)) | Responsabilidade de Task é uma quarta atribuição operacional, restrita à tarefa; não criar outro owner do contato. |
| **[OBSERVADO NO CÓDIGO]** Temperatura já existe em `lead_temperature.py`, calculada a partir de parâmetros/sinais do CX; persistência em contato/threads/protocolo ([bot_service.py](../bot_service.py#L1038)) | Reusar FRIO/MORNO/QUENTE. Não criar classificador ou temperatura paralela em Task. |
| **[OBSERVADO NO CÓDIGO]** UI/types/normalização já usam `lead_temperature`; cálculo ocorre no handoff ou ao assumir snapshot; devolução à Val preserva valor anterior | Exibir última temperatura consolidada disponível, com data quando disponível. Ausência = não informada, não FRIO; não prometer temperatura ao vivo. |
| **[OBSERVADO NO CÓDIGO]** `qualification`: `novo`, `em_atendimento`, `qualificado`, `nao_qualificado`, `convertido`, `nao_convertido` ([config.py](../config.py#L234)); fechamento usa desfechos operacionais | Preservar o campo e seus gates. Não misturar temperatura, AGENDOU e relacionamento nesse enum. O código não define o marco clínico/financeiro de Ganho; Cristina o esclareceu como pagamento confirmado no ProDoctor, sem alteração automática desses gates em F1. |
| **[OBSERVADO NO CÓDIGO]** Não foi encontrado modelo estruturado de Opportunity/Quote/orçamento/venda ou agenda médica no backend, frontend, scripts e arquitetura inspecionados | Não reutilizar um modelo fictício nem criar automaticamente Opportunity em F1. Não concluir que a clínica não tenha sistema externo. |
| **[OBSERVADO NO CÓDIGO]** `ReplyQuote` é citação de mensagem; agenda/picker é de contatos; `attendances_daily` é protocolo operacional | Esses nomes não representam orçamento comercial ou consulta médica. `wants_appointment` indica intenção, não confirmação. |
| **[OBSERVADO NO CÓDIGO]** Não foram encontrados `commercial_status`, `relationship_status`, `relationship_reason` operacionais | Documentar como proposta futura, não campos já existentes nem requisito implementado de F1. |
| **[OBSERVADO NO CÓDIGO]** `_require_contact_access` aplica acesso atual ([main.py](../main.py#L1747)); crons não gerenciam tarefas | Task não concede acesso extra, não bloqueia cron e não é concluída por fechamento/devolução à Val. |
| **[OBSERVADO NO CÓDIGO]** DELETE do contato chama `archive_wa_contact`, que marca `is_archived=1` ([main.py](../main.py#L3640), [database_firestore.py](../database_firestore.py#L2531)) | Arquivamento não é eliminação física nem encerramento do relacionamento. Não presumir uma rotina completa de eliminação já implementada. |

### Dois pontos do plano anterior que o código contradiz

**[OBSERVADO NO CÓDIGO]** `contact.last_inbound_at` é atualizado com o relógio de recebimento antes do guard de duplicação, inclusive em cliques de controle/reentregas ([webhook.py](../webhook.py#L1191), [database_firestore.py](../database_firestore.py#L2027)). Compará-lo sozinho à criação da Task pode produzir falso sinal de resposta nova.

**[HIPÓTESE]** Calcular o sinal na leitura a partir de `wa_messages` já persistidas: inbound elegível com `timestamp_wa` real posterior à âncora, no escopo autorizado. Excluir sistema/outbound, status de entrega, reações, rating/controle e backup. Definir tipos elegíveis; consultar com filtros, limites e paginação, sem copiar texto nem criar hook no webhook em F1. Timestamp agregado pode ser atalho para selecionar candidatos, não prova final. Exigir `timestamp_wa` real válido; ausência desse timestamp não autoriza usar ingestão/`created_at` da mensagem como comprovação. Reentrega de mensagem anterior à âncora não deve gerar o sinal.

**[DECISÃO DO PO — 18/10]** Decisão 8: o aviso considera mensagens após a **última tentativa real**, usando **criação da Task antes da primeira tentativa**. Apenas adiar preserva referência e aviso; a resposta é sinal para revisão, sem conclusão automática. Mostrar “Paciente respondeu após a última tentativa” ou “Paciente respondeu após a criação da tarefa”, conforme a referência efetiva.

**[HIPÓTESE]** Implementar a referência como o maior momento entre criação da Task e `occurred_at` das tentativas reais válidas, nunca `recorded_at`, `updated_at` ou `due_at`. Registro retroativo não a recua; edição, adiamento e troca de responsável não a avançam. Se persistida, a atualização de tentativa/referência/Activities é atômica e protegida por `version`; alternativa é derivar dos eventos válidos. `anchor_message_id` é opcional, pois ligação telefônica pode não ter mensagem vinculada. Nenhuma atualização da referência amplia acesso a contato/thread, copia mensagem ou cria hook no webhook.

**[OBSERVADO NO CÓDIGO]** `/api/wa/conversation/open` não é leitura pura: pode materializar thread, atribuí-la no legado e chamar `mark_human_active`/classificação do snapshot quando pertence ao usuário ([main.py](../main.py#L1653), [main.py](../main.py#L1722)).

**[HIPÓTESE]** Abrir contexto do follow-up deve ler/selecionar thread existente por caminho autorizado de consulta, sem chamar automaticamente `open`, `assume` ou `set-attendance`. Sem thread, mostrar o contato e a ausência de conversa, sem criar atendimento por efeito da tarefa. Ler contexto não registra tentativa nem conclusão.

## 4. Análise do CSV real

### 4.1 Estrutura e método

**[OBSERVADO NA PLANILHA]** Arquivo com 76.726 bytes, UTF-8 sem BOM, delimitado por vírgula: cabeçalho + **499 registros**, todos com **20 colunas**, sem registro inteiramente vazio. Leitura com parser CSV, respeitando aspas e posições; não mapear por nome de coluna porque há cabeçalhos repetidos.

- Colunas 1–13: DATA DO ORÇAMENTO, NOME, TELEFONE, CONVÊNIO, INDICAÇÃO, MÉDICO, VENDEDOR, VALOR ORÇ., VALOR PAGO, DATA FECHAMENTO, INTERESSE 1, DOR (ESTÉTICA, SINTOMA, ETC), BAIRRO.
- **Bloco posterior B1**, colunas 14–17: VENDEDOR, DATA, INTERESSE, OBS. 2.
- **Bloco posterior B2**, colunas 18–20: VENDEDOR, DATA, INTERESSE. Não há OBS. 3 neste export.
- VENDEDOR aparece três vezes; DATA e INTERESSE, duas. Parser baseado somente nesses nomes perderia valores de blocos anteriores.

Preenchimento significa célula não vazia após remover espaços; não significa dado válido, confirmado ou completo.

| Campo / grupo | Registros com preenchimento, de 499 |
|---|---:|
| NOME / TELEFONE | 499 / 50 |
| CONVÊNIO / INDICAÇÃO / MÉDICO / VENDEDOR inicial | 499 / 487 / 498 / 497 |
| DATA DO ORÇAMENTO / VALOR ORÇ. | 498 / 496 |
| VALOR PAGO / DATA FECHAMENTO | 8 / 90 |
| INTERESSE 1 | 494 |
| DOR / BAIRRO | 7 / 45 |
| B1: VENDEDOR / DATA / INTERESSE / OBS. 2 | 10 / 38 / 47 / 20 |
| B2: VENDEDOR / DATA / INTERESSE | 0 / 6 / 8 |
| Alguma célula em B1 / B2 / ambos | 67 / 8 / 7 |
| Algum bloco posterior, união B1+B2 | 68 |

**[OBSERVADO NA PLANILHA]** Há uma linha com B2 preenchido e B1 vazio. Nenhum vendedor está preenchido em B2. Isso demonstra registro incompleto; não permite identificar executora nem afirmar que cada bloco equivale a exatamente uma tentativa.

Há 449 linhas sem telefone na coluna TELEFONE. A normalização de nomes resulta em 495 nomes distintos, com quatro grupos repetidos; coincidência de nome não comprova identidade. Não vincular automaticamente registros a contatos por nome, não chamar as 499 linhas de pacientes únicos e não concluir que os repetidos comprovem múltiplos orçamentos da mesma pessoa.

### 4.2 INTERESSE não é uma dimensão única

**[OBSERVADO NA PLANILHA]** Contagem por igualdade exata após normalizar maiúsculas/acentos/espaços:

| Conteúdo | INTERESSE 1 | INTERESSE B1 | INTERESSE B2 |
|---|---:|---:|---:|
| FRIO | 1 | 18 | 4 |
| MORNO | 0 | 5 | 0 |
| QUENTE | 0 | 2 | 0 |
| AGENDOU | 0 | 13 | 2 |
| ENCERRADO | 0 | 9 | 2 |
| Outros textos | 493 | 0 | 0 |
| Vazio | 5 | 452 | 491 |

**[OBSERVADO NA PLANILHA]** `INTERESSE 1` contém principalmente texto livre: 274 células têm mais de 20 caracteres; 108 contêm uma data dia/mês. Procurar rótulo apenas no início encontra AGENDOU em duas células, FRIO em duas e MORNO em uma — método diferente da igualdade exata, não somar essas contagens.

**[CONFIRMADO COM CRISTINA — 08/10]** `INTERESSE 1` registra o que o paciente demonstra no dia em que recebe o orçamento, após consulta médica na clínica. Os interesses posteriores registram o que demonstra nas ligações de follow-up e tentativas de retomada. São avaliações/anotações em momentos diferentes, não um enum único de temperatura nem uma data estruturada.

**[OBSERVADO NA PLANILHA]** B1/B2 efetivamente misturam temperatura, avanço comercial e encerramento nos mesmos campos. A temperatura manual da planilha não prova a temperatura produzida pelo agente e não deve sobrescrevê-la. AGENDOU não é temperatura e ENCERRADO não informa causa ou caráter temporário/definitivo.

### 4.3 Datas: entrega do orçamento, pagamento e tentativas

**[OBSERVADO NA PLANILHA]** Foram diferenciadas datas únicas com ano, datas sem ano, células com várias datas e valores inválidos. Formatos dia/mês/ano com dois ou quatro dígitos foram lidos separadamente; não preencher automaticamente ano ausente.

| Campo | Perfil observado |
|---|---|
| DATA DO ORÇAMENTO, 498 preenchimentos | 494 datas plausíveis de 2026, entre 05/01 e 05/10; três formatos malformados e um ano `0226`, operacionalmente implausível |
| DATA FECHAMENTO, 90 | 88 datas válidas de 2026, entre 06/01 e 05/10; um formato malformado e uma data impossível no calendário |
| DATA B1, 38 | 35 datas únicas com ano, entre 23/02 e 28/09; duas sem ano e um literal que não é data |
| DATA B2, 6 | Três datas únicas com ano, uma sem ano e duas células com três datas dia/mês em cada uma |

Nos 35 pares completos B1/orçamento, quatro são do mesmo dia e 31 posteriores; mediana da diferença: **147 dias**. Isso é descrição dos registros parseáveis, não uma recomendação de cadência, e **não sustenta prazo padrão de dois dias**. Apenas dois pares B2/B1 têm ano explícito, com diferenças de um e 66 dias; não permitem inferir sequência universal.

Entre 88 pares fechamento/orçamento válidos, 27 têm mesma data, 60 são posteriores e um fechamento precede orçamento por um dia. Exige revisão operacional; não corrigir automaticamente.

**[OBSERVADO NA PLANILHA]** Das 20 OBS. 2 preenchidas, oito contêm marcadores de ausência de resposta e 15 coexistem com DATA B1. As células com três datas são evidência de registros comprimidos; o conteúdo clínico/pessoal das observações não foi reproduzido.

**[CONFIRMADO COM CRISTINA — 08/10]** DATA DO ORÇAMENTO é o dia em que o orçamento foi entregue. DATA FECHAMENTO é o dia em que o paciente pagou. DATAs dos blocos posteriores são os dias das tentativas de falar e retomar a venda: retrospectivas, não o próximo retorno. A mediana de 147 dias descreve o intervalo observado entre entrega e tentativa registrada, sem estabelecer cadência.

**[HIPÓTESE]** Células com várias datas representam registro comprimido de tentativas; sua leitura como lista de dias é compatível com a resposta, mas cada data não fornece resultado, autoria, hora ou ano suficientes para reconstruir eventos completos. Não gerar um `task_attempted` por data automaticamente. A análise não corrige formatos inválidos nem completa anos/horários; não importar essas DATAs como `due_at`.

### 4.4 Orçamento, fechamento e pagamento

**[OBSERVADO NA PLANILHA]** Somente três registros têm VALOR PAGO e DATA FECHAMENTO juntos; 87 têm fechamento sem valor pago, cinco têm valor pago sem fechamento e 404 têm nenhum. Valores não vazios são interpretáveis no formato numérico brasileiro, mas isso não comprova recebimento, receita reconhecida, venda concluída ou consulta realizada.

**[CONFIRMADO COM CRISTINA — 08/10]** Ganho/conversão se oficializa pelo **pagamento confirmado no ProDoctor**; DATA FECHAMENTO registra o dia desse pagamento. ProDoctor também é a agenda oficial. Agendamento, consulta realizada, tarefa concluída e envio do orçamento não substituem o pagamento.

A ausência de VALOR PAGO ao lado de DATA FECHAMENTO é incompletude da planilha, não indefinição do marco de Ganho nem prova de ausência de pagamento. A semântica confirmada não torna cada célula uma comprovação financeira: F1 não importa o CSV, consulta o ProDoctor por atuação humana e não escreve `qualification=convertido` por data ou tarefa. Para uma futura integração financeira, confirmar qual pagamento parcial/entrada conta e como associá-lo ao orçamento correto.

### 4.5 Mapeamento conceitual, sem importar

| Dados do CSV | Destino conceitual / cuidado |
|---|---|
| Nome, telefone | Contato existente, após identificação confiável; não duplicar em Task/Activity |
| Próximo retorno combinado, ação e responsabilidade | `crm_tasks`; a DATA histórica dos blocos não é `due_at`; prazo é uma escolha nova explícita |
| Tentativa realizada, executora, momento, resultado, reagendamento | `crm_activities`; DATAs posteriores têm essa finalidade histórica, mas o CSV não fornece eventos completos para importação |
| Médico, convênio, data/valor de orçamento, pago/fechamento | Fonte comercial própria, candidata futura Opportunity/Quote; não espalhar nos contatos/tarefas como conveniência de UI |
| INTERESSE 1 / interesses posteriores / OBS. 2 | Reação inicial ao orçamento e reações às retomadas; eventual contexto mínimo revisado pela pessoa, não cópia automática |
| FRIO/MORNO/QUENTE da planilha | Avaliação manual de origem distinta; não alimentar ou duplicar temperatura IA |
| AGENDOU / ENCERRADO | Fecham o ciclo acompanhado; não significam Ganho, encerramento global, `Task.status` ou temperatura |
| DOR e detalhes clínicos | Fora de contexto comercial mínimo de Task/Activity; não transcrever |

F1 não é uma migração desta planilha. Importação, conciliação de pacientes, datas sem ano e validação de identidade exigiriam um plano próprio.

## 5. Separar dimensões do domínio

| Dimensão | Fonte / candidatos | Regra |
|---|---|---|
| **Qualificação/temperatura IA** | **[OBSERVADO NO CÓDIGO]** `lead_temperature`: `frio`, `morno`, `quente` | Fonte existente do agente/classificador; contexto exibido, não campo copiado na Task |
| **Estado operacional CRM** | **[OBSERVADO NO CÓDIGO]** `qualification`, status da thread, `bot_completed`, `human_active` | Gates atuais preservados; não substituir por interesse/relacionamento |
| **Estado comercial** | **[HIPÓTESE]** `commercial_status`: `interested`, `scheduled`, `won`, `lost` | Candidatos futuros, não enum fechado. Ganho exige pagamento confirmado no ProDoctor; AGENDOU não é Ganho |
| **Ciclo de acompanhamento** | **[CONFIRMADO COM CRISTINA — 08/10]** Aberto enquanto indefinido; fecha com AGENDOU ou ENCERRADO | Escopo daquele acompanhamento, não estado permanente do contato; sem nova entidade em F1 |
| **Estado do relacionamento** | **[HIPÓTESE]** `relationship_status`: `active`, `paused`, `closed` | Situação explícita de continuidade; não inferir de ciclo, Task, thread ou qualificação |
| **Motivo do relacionamento** | **[HIPÓTESE]** `relationship_reason` separado | Categoria estruturada necessária ao domínio, sem diagnóstico ou narrativa clínica |
| **Estado da tarefa** | **[DECISÃO DO PO]** Ação humana independente; proposta `pending`, `completed`, `cancelled` | Concluir ação não converte lead nem encerra relacionamento |

**[DECISÃO DO PO]** Não usar AGENDOU no mesmo enum de FRIO/MORNO/QUENTE/ENCERRADO. Um contato pode ter temperatura QUENTE, estado comercial agendado e relacionamento ativo.

**[DECISÃO DO PO]** ENCERRADO não basta para situações tão diferentes como desinteresse, não fechamento, tratamento concluído e recomendação médica. Avaliar status separado do motivo. Não deduzir `paused`/`closed` automaticamente de `not_closed`: pode significar adiamento ou decisão definitiva.

**[HIPÓTESE]** Pausado representa interrupção temporária potencialmente retomável; encerrado representa relacionamento sem follow-up comercial automático esperado. Candidatos de motivo: `no_interest`, `not_closed`, `treatment_completed`, `medical_recommendation`, `no_response`, `financial`, `postponed`, `other`. **Nomes e enum não estão aprovados.**

**[CONFIRMADO COM CRISTINA — 08/10]** AGENDOU ou ENCERRADO fecha o ciclo acompanhado. Campo em branco/sem definição mantém o ciclo aberto e representa oportunidade de retomada, sem provar interesse afirmativo. Agendar pode encerrar o objetivo daquele retorno e originar confirmação/lembrete; não encerra todo o relacionamento nem comprova pagamento.

**[DECISÃO DO PO — 18/10]** Decisão 5: no pós-orçamento, **AGENDOU pode representar nova consulta ou procedimento/tratamento**, conforme o caso. A equipe identifica o tipo do compromisso efetivamente marcado e qual objetivo de acompanhamento foi resolvido. O desfecho é registrado humanamente naquela tarefa/ciclo, preservando confirmação/lembrete e outros objetivos independentes. Marcar uma nova consulta não prova que o procedimento orçado foi contratado ou pago; Ganho continua sendo pagamento confirmado no ProDoctor. A categoria não cria status novo de contato nem altera o uso atual de Convertido.

**[DECISÃO DO PO]** Em 13/10, continuidade aprovada pela mesma Task, acumulando tentativas e reagendamentos até seu desfecho explícito. Não adicionar `crm_cycles`, cadeia de tarefas para cada tentativa ou subsistema global de relacionamento. A preferência comercial mínima da decisão 6, descrita na seção 7.5, é distinta de `relationship_status`/`relationship_reason`. Concluir uma ação sem resposta não prova ciclo fechado. **[DECISÃO DO PO — 18/10]** Decisão 6 separa recusa daquele orçamento/procedimento de recusa de novos contatos comerciais, conforme abaixo. O catálogo completo de motivos e exemplos de pausa permanece proposta de detalhamento, sem reabrir os dois escopos aprovados. Não mapear `convertido`, `nao_convertido`, arquivo ou fechamento da thread automaticamente para novos estados.

**[DECISÃO DO PO — 18/10]** Decisão 6: **“Não quero esse orçamento/procedimento”** encerra apenas aquele acompanhamento; **“Não quero mais contatos comerciais”** interrompe futuras retomadas comerciais do paciente. Nos dois casos, consultas marcadas e outras tarefas independentes permanecem. A ação precisa identificar o escopo efetivamente pedido, sem inferi-lo de silêncio, tag, fechamento de thread ou Não convertido.

F1 registra desfechos da **tarefa** e a preferência comercial mínima no **contato**, sem instalar um subsistema de relacionamento. “Parar tentativas desta tarefa” continua específico; o pedido geral exige ação distinta e registro estruturado que alcance os demais produtores comerciais. Estados globais de relacionamento e catálogo amplo de motivos permanecem futuros.

### 5.1 Qualificações, temperatura, tags e follow-up na mesma visão

**Contexto trazido pelo PO em 09/10:** o filtro atual mostra Todos, Novo, Em atendimento, Qualificado, Convertido, Não convertido e Não lidas. O catálogo de tags apresentado mistura convênios/forma de atendimento, objeções, acontecimentos, perfil do contato e tema de saúde. As imagens não comprovam que todas essas tags estejam aplicadas a um paciente ou definem a finalidade de cada rótulo.

**[OBSERVADO NO CÓDIGO]** O dropdown filtra `contact.qualification`; Todos remove esse filtro e Não lidas consulta o indicador da thread, não uma qualificação. A primeira mensagem humana elegível promove Novo para Em atendimento. Os desfechos são escolhidos pela equipe; o backend não verifica consulta ou pagamento no ProDoctor.

**[OBSERVADO NO CÓDIGO]** Tags já existem em `wa_contacts.tags`, como slugs normalizados. Os catálogos global do tenant e pessoal do operador contêm `slug`, `label`, `color` opcional, sem categoria ou significado de negócio obrigatório. O filtro atual combina qualificação e tags; múltiplas tags selecionadas usam interseção. Aplicar tags exige acesso atual ao contato; nome/cor/categoria da tag não concede acesso.

O catálogo pessoal não torna a tag aplicada confidencial: ela aparece para quem tem acesso ao contato e já consta na exportação CSV. Preferir o vocabulário global da clínica para termos usados em colaboração; manter tags pessoais para necessidades específicas. Não renomear slugs existentes automaticamente para criar grupos.

**Desalinhamento documental:** o [guia atual de qualificação](product/GUIA_OPERADORES_QUALIFICACAO_FECHAMENTO.md) reserva Qualificado ao fluxo de locação e considera consulta marcada ou dúvida resolvida como exemplos de Convertido. Isso não corresponde ao marco financeiro informado por Cristina. Não usar registros históricos de `qualification=convertido` como prova de pagamento, recalcular receita, migrar desfechos ou alterar o guia compartilhado nesta revisão.

**[HIPÓTESE]** Reunir as informações no cartão do contato e na lista de tarefas, preservando as fontes:

| Informação | Pergunta respondida | Fonte / apresentação |
|---|---|---|
| Qualificação | Qual estado/desfecho foi registrado pela equipe? | `wa_contacts.qualification`; não mudar ao criar/adiar/concluir Task |
| Temperatura | Qual interesse a IA classificou? | `lead_temperature` atual, com origem/data quando disponível; não copiar na Task |
| Tags | Qual contexto complementa o acompanhamento? | Tags atuais do contato, resolvidas na leitura; não duplicar em Task/Activity |
| Próxima ação | O que fazer, quando e por qual fila/pessoa? | `crm_tasks`; histórico em `crm_activities` |

**[HIPÓTESE]** Organizar o vocabulário de tags por finalidade, inicialmente como convenção do catálogo, sem criar taxonomia obrigatória ou novos campos em F1:

| Grupo conceitual | Exemplos apresentados / cuidado |
|---|---|
| Convênio / forma de atendimento | Bradesco, IPSEMG, SulAmérica, Unifácil, Unimed, Particular; não tratar tag como validação atual de cobertura ou dado do orçamento |
| Objeção comercial | Preço, Distância; complementam a tentativa, sem determinar perda/pausa automaticamente |
| Acontecimento | Desmarcou / Faltou; separar os dois no vocabulário futuro e registrar data/resultado na fonte adequada. Tag atual não identifica qual consulta nem deve virar atributo permanente do paciente |
| Perfil do contato | Representantes, sujeito à confirmação de finalidade; não presumir paciente nem autorizar campanha |
| Tema de saúde | Tag como a exibida no catálogo permanece contexto de saúde sujeito ao acesso atual. Não copiar para título, descrição ou histórico de follow-up; não inferir diagnóstico ou criar seleção automática de massa |

ENCERROU CONVERSA deve ser esclarecida: fechamento de atendimento, desinteresse e pedido de parar contato são fatos diferentes. A tag isolada não define `relationship_status`, fim do ciclo, aceite LGPD ou `reopen_opt_out`; os gates reais continuam sendo a fonte de envio. Não criar tags redundantes de status, temperatura ou prazo, como Novo, Quente ou Retornar amanhã.

O [guia de tags e privacidade da Varizemed](compliance/TAGS_E_PRIVACIDADE_VARIZEMED.md) orienta uso por assunto do atendimento e registra pré-requisitos adicionais para campanhas segmentadas por saúde. Isso não prova que opt-in específico ou suas pendências estejam implementados. F1 usa contexto interno sob acesso atual; não implementa segmentação de massa por tag nem presume que aceite genérico LGPD a autorize.

**[HIPÓTESE]** Combinar filtros por qualificação, tags e prazo/fila da Task. Exemplo fictício: Não convertido + Preço + retorno Hoje mostra ações humanas a executar, sem declarar elegibilidade para lote. A implementação precisará validar consultas, índices, contagens e paginação com acesso atual, sem full-scan de contatos para filtrar tarefas no cliente.

**Orientação de escopo trazida pelo PO em 09/10:** simplificar Qualificado e deixar os demais estados como estão. A recomendação financeira da revisão anterior não foi aprovada como mudança do campo `qualification=convertido`. Preservar seu funcionamento atual; Ganho financeiro continua sendo pagamento confirmado no ProDoctor, como definição distinta, sem considerar o rótulo legado prova de pagamento. Eventual alinhamento de nome/uso será decisão posterior explícita, sem reclassificação automática de dados ou mudança em outros tenants. Em F1, Task continua independente e não escreve qualificação; integração financeira e novo estado comercial permanecem futuros.

### 5.2 Proposta de simplificação de Qualificado na Varizemed

**Relato do PO em 09/10:** após revisar o contexto das poucas conversas classificadas como Qualificado, encontrou pessoas com interesse que não fecharam e pessoas com plano de saúde não aceito. É informação operacional fornecida pelo PO; esta sessão não consultou conversas ou contagens de produção.

**[HIPÓTESE]** Descontinuar Qualificado nas novas marcações da Varizemed e usar Não convertido com tags de contexto/motivo. Manter Novo, Em atendimento, Convertido e Não convertido como estão; Todos e Não lidas continuam filtros. Não qualificado continua disponível para spam, número errado e contatos fora do escopo — não classificar um paciente legítimo como Não qualificado apenas porque seu convênio não é aceito.

| Situação revisada pela equipe | Desfecho sugerido quando encerrar aquele atendimento | Tag candidata, somente se corresponder ao contexto real |
|---|---|---|
| Interesse, mas ainda precisa decidir | Não convertido | Aguardando decisão |
| Convênio não aceito, sem fechamento | Não convertido | Convênio não aceito, com a tag do convênio quando útil |
| Não fechou por preço ou distância | Não convertido | Preço ou Distância, conforme motivo informado |

Não convertido registra que o objetivo daquele atendimento não foi alcançado; não declara perda definitiva, recusa global ou ausência de interesse. A próxima ação fica na Task, com prazo e histórico, sem transformar uma tag em agendamento. Durante o atendimento, os estados atuais continuam seus fluxos próprios; não marcar Não convertido automaticamente ao criar follow-up ou detectar silêncio.

**[HIPÓTESE]** Fazer a descontinuação por tenant, incluindo validação em ambiente/destinatários controlados, preservando Qualificado na Hubloc e a compatibilidade de leitura dos dados legados. O nome `varizemed-test` não comprova isolamento: em 18/10, o PO informou que ele corresponde ao canal usado pela Castro Intelligence. Não presumir que seja um canário sem uso operacional. Revisar os poucos casos existentes com contexto e aplicar Não convertido + motivo correto quando cabível, preservando notas, tags úteis e auditoria. Não migrar todos pelo nome do estado; não inventar motivo. Até concluir essa revisão autorizada, manter os registros existentes visíveis/consultáveis, sem retirar um filtro que os torne difíceis de localizar.

Filtros, formulário de qualificação e modal de fechamento da clínica precisam ser coerentes ao deixar de oferecer a opção para novos registros. Não eliminar `qualificado` do enum global compartilhado ou invalidar leitura legada. A retirada das telas e a eventual reclassificação são etapas futuras próprias, ainda sem implementação ou alteração de dados nesta revisão. Confirmar inclusão dessas etapas no escopo de desenvolvimento antes de executá-las.

Não convertido pode ter Task humana pendente sob acesso atual. Isso não amplia a elegibilidade da reabertura em massa: preservar a exclusão dos desfechos terminais prevista na ADR 0013 e os gates reais de envio, sem usar tag de motivo para contorná-los.

## 6. Tentativas, conclusão e continuidade

**[DECISÃO DO PO]** Tentativas precisam de histórico real: quem, quando, resultado e eventual reagendamento. `attempt_count=N` sozinho não atende.

**[CONFIRMADO COM CRISTINA — 08/10]** Normalmente há três tentativas, mas a quantidade depende do caso; a orientação comercial é continuar até o paciente dizer que não tem interesse. Não criar teto universal de três nem concluir/cancelar automaticamente por silêncio. **[DECISÃO DO PO — 18/10]** A continuidade exige decisão humana e próximo prazo explícito, conforme decisão 7 abaixo; ausência de resposta não é interesse afirmativo, aceite LGPD nem autorização para uma sequência automática ilimitada. Recusa deve interromper a retomada daquele objetivo, com motivo e escopo claros.

**[DECISÃO DO PO — 18/10]** Decisão 7: priorizar a data combinada com o paciente. Sem data combinada ou após tentativa sem resposta, a operadora escolhe o próximo prazo, usando atalhos nos dias/horários permitidos e confirmando a data/hora final. Após três tentativas sem resposta, a equipe revisa o histórico e a abordagem antes de continuar. A mesma Task permanece aberta, sem encerramento automático, intervalo universal ou limite rígido de tentativas. Recusa e demais restrições de contato continuam sendo respeitadas.

**[HIPÓTESE]** Na leitura do histórico/modal de reagendamento, evidenciar as tentativas sem resposta e orientar a revisão antes de escolher o próximo prazo. Essa revisão é parte do trabalho da equipe; não criar novo status, Task de aprovação, cron, contador paralelo ou exigência de aprovação da gestora. Não exigir relato clínico para justificar continuidade. A contagem continua baseada nos eventos reais, e adiar sem tentar não aumenta tentativas.

**[HIPÓTESE]** F1 oferece escolhas distintas:

| Ação humana | Efeito proposto |
|---|---|
| Registrar tentativa | Cria `task_attempted`; mantém Task pendente por padrão |
| Registrar tentativa e reagendar | Mesma Task/ID `pending`; registra tentativa e `task_rescheduled`, com prazo anterior/novo |
| Adiar sem ter tentado | Só muda prazo e gera `task_rescheduled`; não conta tentativa |
| Registrar tentativa e concluir objetivo | Grava tentativa e `task_completed` quando a pessoa resolve aquele objetivo; tentativa sem resposta mantém o acompanhamento pendente |
| Concluir uma ação que não foi contato | `task_completed`, sem fabricar tentativa de contato |
| Agendar ação com outra finalidade após concluir | Cria Task distinta, como confirmação/lembrete; a antiga continua concluída e seu histórico preservado |
| Parar tentativas desta tarefa | Cancelamento explícito com motivo, preservando histórico; não cancela outras tarefas nem encerra relacionamento |

**[DECISÃO DO PO]** Decisão 2 aprovada em 13/10: registrar tentativa e reagendar a mesma tarefa, acumulando todo o histórico. Troca de operadora, prazo ou tentativa não cria outro ID nem zera contagem. Nova finalidade, como lembrete depois de resolver o retorno de agendamento, pode gerar outra tarefa; continuidade do mesmo objetivo permanece na original. Não criar entidade de campanha ou vínculo `previous_task_id` para cada retorno.

Exemplo fictício: tentativa em 07/10 às 10h sem resposta → reagendar para 09/10 → nova tentativa sem resposta → reagendar novamente. Cada tentativa efetivamente realizada tem autora/momento/resultado; as datas futuras são prazos, não tentativas já feitas. Uma terceira tentativa é exemplo coerente com a prática informada, sem impedir uma quarta ou encerrar a tarefa por contagem.

Candidatos de `result_code`: `action_done`, `not_reached`, `customer_replied`, `scheduled`, `no_longer_interested`. **[VALIDAR COM CRISTINA]** Distinguir sem resposta, não atendeu, contato realizado, agenda confirmada e desinteresse; não fechar enum agora. `scheduled` só registra resultado informado pela pessoa, sem converter estado comercial/agenda automaticamente. **[DECISÃO DO PO — 18/10]** O compromisso pode ser consulta ou procedimento/tratamento; distinguir o que foi marcado no registro humano de AGENDOU, sem concluir outras tarefas por efeito colateral.

**[DECISÃO DO PO]** Conclusão é explícita e separada do objetivo comercial/financeiro. Para o acompanhamento contínuo aprovado em 13/10, `not_reached` registra o resultado de uma tentativa, mantendo a Task pendente para continuidade na mesma tarefa. Se a equipe decide parar aquele acompanhamento, registra desfecho/cancelamento explícito com motivo; não concluir a cada ligação e criar outra para o mesmo objetivo. Receber pergunta de endereço não confirma consulta, e receber mensagem não conclui toda tarefa.

A contagem vem de eventos `task_attempted` válidos, paginados; cache derivado é opcional, nunca fonte única. F1 não propõe `max_attempts` nem parada automática por contagem. A revisão após três tentativas sem resposta e a escolha humana do próximo prazo foram aprovadas na decisão 7; não repetir contatos sem agenda. Tentativas humanas não são `reopen_attempts` nem consomem, por si, orçamento de massa 2/90.

## 7. Modelo proposto para F1

### 7.1 `crm_tasks`, escopada por tenant

**[HIPÓTESE]** Usar helpers de prefixo/tenant existentes, serviço com tenant obrigatório, REST e nenhuma nova leitura/escrita direta do cliente em produção. Não usar fallback Hubloc.

| Campo / grupo | Semântica proposta |
|---|---|
| `id`, `tenant_id`, `contact_id` | ID imutável, caminho/tenant coerentes, contato existente obrigatório |
| `conversation_id`, `channel_id` | Opcionais; vínculo coerente com contato/tenant e escopo da thread |
| `type`, `title`, `description` | Ação e contexto mínimo limitados; `retorno` é caso inicial do PO; tipos específicos a validar |
| `contact_purpose` | **[HIPÓTESE]** Finalidade explícita `commercial`/`service`/`internal` para aplicar a preferência comercial; não inferir de texto, tag, fila ou rótulo genérico |
| `due_at`, `status` | Timestamp UTC; `pending`/`completed`/`cancelled` propostos, sem `overdue` persistido |
| `assignment_mode`, `queue_key` | `queue`/`user`; filas Recepção + Orçamentos aprovadas; identidade da fila preservada inclusive quando a Task está com uma pessoa, sem autorização por setor |
| `assignee_user_id`, `assignee_uid` | Responsável só pela Task, não owner; vazios em fila, coerentes quando pessoal |
| `created_by_user_id`, `created_by_uid`, `source` | Quem criou; F1 `source=manual`; criadora não precisa executar |
| `created_at`, `updated_at`, `version` | Relógio servidor, auditoria e concorrência otimista |
| `response_anchor_at`, `anchor_message_id` | Referência da decisão 8: criação/última tentativa real; se não persistida, derivar com as mesmas regras. ID de mensagem opcional, inclusive em ligação; sem cópia de conteúdo |
| `completed_at`, `completed_by_user_id`/`uid`, `result_code` | Conclusão/autoria/resultado; enum a validar; não conversão |
| `cancelled_at`, `cancelled_by_user_id`/`uid`, `cancel_reason` | Desfecho da tarefa, sem encerrar relacionamento por efeito colateral |

**[DECISÃO DO PO]** Os nomes iniciais das filas são Recepção e Orçamentos. **[HIPÓTESE]** Usar identificadores internos estáveis para `queue_key`, separados do rótulo exibido/configuração por tenant: mudar o nome depois preserva a fila, tarefas, prazos, autoria e histórico; não remapear tarefas pelo texto do nome. Não criar novo setor ou conceder acesso ao renomear.

Atribuir, pegar, editar, tentar, reagendar, concluir e cancelar validam `version` e autoridade sobre a tarefa. Conflito informa que outra pessoa alterou, sem overwrite. Concluída/cancelada preserva histórico; nova ação cria Task nova, sem reabrir silenciosamente a anterior.

Tipos sugeridos para validar: retorno comercial, sem resposta, orçamento, confirmação de consulta, lembrete de consulta e recuperação. **[CONFIRMADO COM CRISTINA — 08/10]** Confirmação é feita 72h antes e lembrete 24h antes: tipos/ações separados. Tipo é finalidade humana, não autorização de envio; evitar `agendamento` amplo se esconder confirmação versus remarcação.

**[DECISÃO DO PO]** Prazo UTC, exibição no timezone do tenant; piloto `America/Sao_Paulo`. Atalhos Em 1 hora, Amanhã, Em 2 dias, Em 7 dias, Escolher data, mostrando prazo final antes de salvar.

**[CONFIRMADO COM CRISTINA — 08/10]** Priorizar a data combinada individualmente; não realizar contatos aos sábados/domingos. Terça, quarta e quinta são preferência para retomadas, não dias exclusivos. **[HIPÓTESE]** No piloto, validar prazo de tarefas de contato contra essa regra e exigir escolha de dia útil se o atalho cair no fim de semana; não deslocar silenciosamente uma data combinada. Uma tentativa histórica pode ser registrada com sua data verdadeira, sem reescrever o acontecimento para atender ao calendário. **[DECISÃO DO PO — 13/10]** Dias/horários de follow-up serão configuráveis em menu para Cristina, sob autorização de gestão. Para confirmação/lembrete que cair em fim de semana ou feriado, o PO aprovou sugerir o dia útil anterior, com confirmação do horário pela operadora. **[DECISÃO DO PO — 17/10]** Prazo de confirmação já passado em agendamento de última hora segue a regra da seção 9: contato no primeiro horário permitido antes da consulta ou avaliação pela equipe se não houver horário. Valores e datas sem contato serão configurados pela clínica antes do uso; sem data combinada, a operadora escolhe o próximo prazo conforme decisão 7, sem fixar 10h ou +48h universal. Prazos fora da faixa em dia útil seguem escolha humana de horário permitido, sem deslocamento automático. Alterar configuração não desloca os prazos já combinados; conflitos precisam de revisão humana.

### 7.2 `crm_activities`, escopada por tenant

**[HIPÓTESE]** Eventos mínimos: `task_created`, `task_updated`, `task_assigned`, `task_taken`, `task_attempted`, `task_rescheduled`, `task_completed`, `task_cancelled`. `task_taken` identifica o claim da fila; não duplicar também `task_assigned` para o mesmo fato sem necessidade.

Campos comuns: `id`, `tenant_id`, `contact_id`, `task_id`, `conversation_id` opcional, `event_type`, `actor_type`, `actor_user_id`/`uid`, `occurred_at`, `recorded_at`, `operation_id`, `data` com estrutura controlada.

| Evento | Conteúdo mínimo específico |
|---|---|
| `task_taken` / `task_assigned` | Fila/responsável anterior e novo, IDs; sem posse de contato |
| `task_attempted` | `attempt_id` estável, quem tentou, quando efetivamente tentou, resultado; canal/método ou referência à mensagem somente se útil |
| `task_rescheduled` | Prazo anterior/novo e vínculo à tentativa quando foi parte da mesma operação |
| `task_completed` / `task_cancelled` | Resultado/motivo mínimo e autora; para AGENDOU, categoria do compromisso; para recusa, escopo explícito da ação. Cancelamento simples não altera preferência do contato |

**[HIPÓTESE]** Para resultado humano `scheduled`, guardar em `data` da Activity somente a categoria mínima do compromisso (`scheduled_kind`: consulta ou procedimento/tratamento), com autoria e referências já existentes. Não copiar descrição do procedimento, diagnóstico, sintomas, agenda médica ou dados financeiros. Não criar entidade de agenda/orçamento, `Task.status=scheduled` ou novo estado de `qualification`; a equipe consulta o ProDoctor e conclui explicitamente o objetivo resolvido. A identificação dessa categoria não implica integração/API ou comprovação de pagamento.

Distinguir momento efetivo da tentativa (`occurred_at`) de momento de registro (`recorded_at`, servidor). Se registro retroativo for admitido, validar horário efetivo e preservar quem registrou; não cadastrar tentativa futura. Quem tentou não deve ser inferido apenas da criadora da tarefa ou VENDEDOR incompleto da planilha.

Registrar tentativa + reagendar/concluir deve alterar Task e eventos atomicamente. Idempotência por operação/tentativa e tipo de evento evita dupla tentativa em clique/retry, permitindo eventos distintos da mesma operação. Contagem aumenta uma vez; adiar ou concluir a tentativa já registrada não cria outra.

**[DECISÃO DO PO — 17/10 e 18/10]** Na última hora ou quando os prazos coincidirem após ajuste de calendário, um contato real pode cumprir confirmação e lembrete do mesmo compromisso, com registro humano de ambas as ações e uma única tentativa. **[HIPÓTESE]** Registrar o `task_attempted` uma vez na tarefa que originou o contato; se a pessoa concluir também a outra Task, a segunda conclusão referencia o mesmo fato por `attempt_id`/`operation_id`, sem novo evento de tentativa. Preservar IDs e histórico das duas Tasks. Idempotência de conclusões compostas considera também `task_id`, permitindo um `task_completed` por tarefa sem duplicar a tentativa; validar versão, autoridade sobre cada Task e acesso atual antes de efetivar. Não transformar isso em permissão para concluir tarefa alheia ou funcionalidade genérica de conclusão em lote.

Histórico de negócio não substitui `log_audit` administrativo. Retificação não deve inventar ou apagar silenciosamente fatos: aplicar política autorizada, minimização e auditoria; append-only operacional não impede atender exigência de eliminação/retificação quando cabível.

**[DECISÃO DO PO]** Não duplicar mensagens, transcrições, sintomas, laudos, anexos, conteúdo clínico ou conversa completa. Activity pode referenciar entidades existentes e só expor referência se a pessoa tiver acesso atual.

### 7.3 Opportunity/Quote, futura e desacoplada

**[OBSERVADO NO CÓDIGO]** Não foi encontrada entidade equivalente estruturada local. **[HIPÓTESE]** Futuro Contact pode ter várias oportunidades/orçamentos com médico, convênio, data, valor, pagamento e status próprios. Não criar em F1.

Guardar último orçamento diretamente no contato pode sobrescrever versões, misturar médicos/convênios e atribuir pagamento ao ciclo errado. Guardar cópia em cada Task cria divergência e multiplica dados. A planilha não comprova múltiplos orçamentos por paciente, mas o risco estrutural é plausível.

Manter `contact_id` obrigatório e relação opcional à conversa; um `opportunity_id`/`quote_id` poderá ser adicionado depois, sem mudar a identidade do contato/tarefa ou reconstruir histórico. Não criar referência polimórfica/motor genérico agora. Dados comerciais exibidos virão da fonte adequada; sem fonte estruturada atual, não fabricar cartões de médico/valor/convênio com cópias em Task. Snapshot só com justificativa de auditoria explícita.

### 7.4 Configuração de horários, sem nova entidade de negócio

**[DECISÃO DO PO — 13/10]** O PO pediu um menu para Cristina selecionar os horários na decisão 4 e aprovou sugerir o dia útil anterior quando confirmação/lembrete cair em fim de semana ou feriado, com a operadora confirmando o horário. Os valores das faixas serão configurados pela clínica; regras complementares de última hora e coincidência após ajuste foram aprovadas em 17/10 e 18/10, respectivamente, conforme seção 9.

**[HIPÓTESE]** Persistir a política em configuração escopada por tenant, por exemplo `system_settings/followup`, usando a infraestrutura existente de settings. Não criar coleção de horários por paciente ou cópia de calendário em cada Task. Grupos mínimos propostos: dias habilitados e faixas locais, horário preferido opcional para atalhos, datas sem contato cadastradas pela clínica, fuso `America/Sao_Paulo`, versão e autoria/data da alteração. Para confirmação/lembrete em fim de semana ou feriado, a política aprovada é sugerir o dia útil anterior dentro dos dias/faixas permitidos, com confirmação humana antes de salvar; não reagendar tarefas existentes automaticamente. Marcação tardia e coincidência após ajuste seguem as decisões de 17/10 e 18/10 na seção 9. Prazo fora da faixa em dia útil mantém o desenho de revisão humana do menu: indicar conflito e exigir escolha de horário permitido, sem antecipação/postergação automática ou remarcação de Tasks existentes.

A configuração é da clínica, com o mesmo padrão inicial para Recepção e Orçamentos; não pessoal da Cristina, não compartilhada com Hubloc e não automaticamente espelhada para outro tenant. **[HIPÓTESE]** Leitura operacional para orientar agendamentos; escrita somente por gestão com permissão administrativa apropriada validada no backend, com controle de versão e auditoria existente. Não presumir o papel/permissões atuais da conta da Cristina.

**[OBSERVADO NO CÓDIGO]** [business_hours.py](../business_hours.py) contém a tabela de expediente usada pelo bot/CX, ainda fixa no código: Varizemed segunda a quinta 08h–18h, sexta 08h–17h, sábados/domingos sem faixas. O módulo suporta múltiplas faixas, mas não implementa edição via menu nem feriados nesta versão. O [plano de horário da Val](CX_HORARIO_COMERCIAL_DEV_IA.md) registra essa edição como fase futura. São fatos do worktree/documento, não confirmação dos horários atuais para follow-up.

**[HIPÓTESE]** Expediente da clínica e horário permitido para retomadas têm finalidades distintas: salvar este menu preserva os avisos/horários da Val. Reutilizar cálculo de datas/faixas quando adequado; migração do expediente do bot para configuração geral exige escopo e validação próprios. Sem horários de follow-up confirmados, não usar a tabela da Val como aprovação implícita.

### 7.5 Preferência de contato comercial, extensão mínima da decisão 6

**[DECISÃO DO PO — 18/10]** A recusa geral deve impedir novas retomadas comerciais do contato, preservando consultas marcadas e tarefas independentes. A recusa daquele orçamento encerra somente o acompanhamento correspondente. F1 continua com duas entidades novas de negócio (Task/Activity); a preferência usa o contato existente.

**[HIPÓTESE]** Campo estruturado em `wa_contacts`, por exemplo `commercial_contact_block`, com indicador ativo, data servidor, autoria/origem, versão, motivo controlado de pedido do paciente e referências opcionais à Task/mensagem. Escopo: contato e suas threads/canais dentro do tenant. Não copiar o texto da conversa ou dados clínicos. Nome/estrutura finais são desenho de implementação, não campo já operacional.

Aplicação é ação humana explícita com acesso atual ao contato e permissão apropriada, idempotência, controle de concorrência e auditoria existente (`log_audit`). Se houver cancelamento da Task em conjunto, validar também autoridade/versão dela e preservar histórico; cancelamento comum não cria bloqueio por efeito colateral. Não criar Task fictícia para auditar a preferência. A ausência do campo não deve transformar contatos legados em bloqueados; os gates LGPD/opt-out existentes continuam válidos.

A finalidade comercial ou de serviço precisa estar explícita na operação; tipo genérico, tag, fila e categoria de template não comprovam finalidade. Tasks comerciais já existentes ficam visíveis com impedimento de nova abordagem e revisão humana, sem status novo ou cancelamento global. Consultas, confirmação/lembrete pertinentes e tarefas internas/independentes permanecem sob seus próprios gates. Respostas solicitadas pelo paciente não autorizam automaticamente outras abordagens proativas.

**[DECIDIDO PELO PO — 18/10/2026]** A recusa geral se desfaz quando o paciente manda mensagem nova depois do registro, a mesma regra do Encerrar da reabertura (D4). O CRM grava `active=false`, `reason=patient_wrote` e `source=patient_message` no mesmo write da mensagem e registra `COMMERCIAL_CONTACT_UNBLOCK` no audit_log. Não desfazem: clique de controle (botões), reação, histórico importado, reentrega de mensagem anterior ao registro, transferência, mudança de qualificação, retorno à Val e criação/reagendamento/conclusão de Task. A reversão manual por ação autorizada/auditada continua disponível para quem pede por outro canal. Isso segue distinto de `lgpd_revoked`, que tem significado e gates próprios. Reverter uma preferência não limpa os outros bloqueios nem repõe orçamento de massa.

**Dependência de liberação de F1:** não basta o futuro job de follow-up respeitar a preferência. Todos os produtores comerciais existentes aplicáveis (reabertura pontual/lote, workers e scripts) precisam consultar o mesmo estado e revalidar antes de enviar. Coordenar a integração com a outra frente antes de disponibilizar o registro de recusa geral como proteção operacional; não pressupor cobertura implementada ou inspecionar/alterar o outro worktree. Para contato humano, exibir a restrição no contexto e impedir a execução de retomada comercial pelo fluxo de tarefa; envio livre ou ligação externa não têm classificação semântica automática presumida.

**[OBSERVADO NO CÓDIGO]** A busca local encontrou `reopen_opt_out` e `lgpd_revoked`; não foi localizada preferência comercial geral equivalente operacional nesta revisão. A integração acima é trabalho futuro necessário à implementação desta decisão, sem novo motor de mensagens, nova coleção ou contador. Não adiar essa cobertura para F3 enquanto outro caminho comercial puder abordar o paciente após a recusa registrada em F1.

## 8. Operação, acesso e mudanças de estado

**[DECISÃO DO PO]** Aproximadamente três operadoras da Recepção podem criar follow-up. Fluxo: criar na fila → CRM exibe no prazo → uma pessoa Pega → torna-se responsável somente pela Task. Não assumir contato/conversa, mudar owner/Val, reabrir ou alterar estados operacionais.

**[CONFIRMADO COM CRISTINA — 08/10]** Trabalho colaborativo, com Recepção mais voltada a novos leads e Administrativo a pacientes com orçamento. **[DECISÃO DO PO]** Decisão 1 aprovada em 13/10: filas de tarefas Recepção para novos leads/acompanhamento de consultas e Orçamentos para retomadas após a apresentação do orçamento. O termo Administrativo descreve a organização da clínica, não o nome da fila. As mesmas operadoras podem participar de ambas dentro do acesso atual. Não fixar nomes de funcionárias, atribuir pelo nome do CSV nem criar ownership de contato por setor. Colaboração não dispensa controle de concorrência, acesso e autoria real.

**[HIPÓTESE]** Operador gerencia próprias e tarefas ainda compartilhadas dentro do acesso atual; gestão autorizada redistribui. Acesso ao contato da pool não autoriza alterar Task pessoal da colega. Perfis/toggles novos devem seguir catálogo/seeds/defaults do editor RBAC; não exigir permissão de WhatsApp para anotar tentativa/concluir ação.

Ao atribuir ou Pegar, o backend valida também a pessoa destinatária: perfil ativo, mesmo tenant, acesso atual ao contato e à thread vinculada, além da autoridade de quem executa a operação. Não aceitar atribuição a alguém sem acesso nem usar Task para concedê-lo; lista de pessoas elegíveis vem do backend.

**[DECISÃO DO PO]** Decisão 3 aprovada em 13/10: reagendar e Devolver à fila como padrão, oferecendo Manter comigo como exceção explícita. A pessoa pode devolver sua Task; gestão autorizada cobre ausência/redistribui, com histórico e acesso atual. Detalhes na seção 8.1. Isso não modifica a posse do contato, o atendimento ou o ciclo da Val.

| Evento externo | Conduta proposta em F1 |
|---|---|
| Thread fecha por cron/lead volta à Val | Manter tarefa e prazo; informar estado atual, sem impedir fluxo operacional |
| Lead transferido | Revogar acesso antigo imediatamente se saiu do escopo; gestão identifica e redistribui pendências sem pessoa elegível |
| Responsável desativado | Pendência visível para gestão autorizada, com redistribuição manual |
| Arquivo/desfecho operacional | Não concluir ou encerrar relacionamento por inferência; destacar contexto e permitir decisão humana sobre cada tarefa |
| Opt-out/revogação LGPD | Não limpar marca por Task; impedir futuros envios automáticos; tarefa interna não autoriza contato |
| Recusa geral de contatos comerciais | Impedir novas retomadas comerciais, inclusive de Tasks pendentes; manter histórico e revisão humana; consultas/tarefas independentes preservadas |
| Eliminação/retificação aplicável | Alcançar Task/Activity no processo de privacidade; não tratar arquivo como apagamento |

**[HIPÓTESE]** Manter redistribuição/cancelamento por mudanças externas manuais pela gestão em F1, para evitar hooks amplos. Acesso atual e identificação de pendências são obrigatórios desde a primeira versão. Reconciliação automática fica para integração explícita posterior.

Cada leitura, busca, amostra, contagem e ação valida tenant, perfil ativo, permissões, contato e thread atuais. Criadora/responsável não ganha acesso por histórico; usar `_require_contact_access`/predicado compartilhado e `can_see_all_tenant`, sem autorizar por setor. Contato com dono não se torna público na fila, e Task não abre agenda coex ou backup alheio.

Consulta e histórico paginados por prazo/status/responsabilidade e contato; índices a validar ao implementar. Autorizar referências em lote sem perder cursor. Nada de carregar todos os contatos/conversas ou listener global para filtrar no React. Indicadores de Task não reutilizam unread/alarme sonoro; thread permanece fonte de não-lidos.

**[OBSERVADO NO CÓDIGO]** Novas coleções são negadas por padrão nas rules de produção, mas staging permite amplamente subcoleções por `emailAllowed()` ([firestore.rules](../firestore.rules#L438)). Validar/restringir acesso de testes antes de usar dados pessoais; REST e tenant no backend não corrigem regra direta aberta por si.

### 8.1 Responsabilidade após reagendar — decisão 3 aprovada

**[DECISÃO DO PO]** Duas opções de responsabilidade, com Devolver à fila como padrão e Manter comigo como exceção, sem trocar a identidade da Task:

| Política | Efeito no próximo retorno | Consequência operacional |
|---|---|---|
| Manter com a operadora | Task permanece atribuída e aparece em Minhas | Continuidade pessoal; ausência exige devolução/redistribuição explícita |
| Devolver à fila | Task conserva fila, novo prazo e histórico, ficando sem responsável individual | Próxima colega autorizada pode Pegar; facilita cobertura e distribuição |

**[DECISÃO DO PO]** Para a operação colaborativa: reagendar + Devolver à fila como padrão, oferecendo Manter comigo como exceção explícita, por exemplo quando o paciente pede a mesma operadora. A escolha deve estar visível antes de salvar. Política aprovada em 13/10; desenvolvimento ainda não iniciado.

Fluxo aprovado: Task futura na fila → uma pessoa Pega para executar → registra tentativa e resultado → escolhe o próximo prazo e Devolver à fila/Manter comigo → próxima execução usa a mesma Task. Registrar tentativa + prazo + mudança de responsável é uma operação coerente e auditada; a contagem aumenta uma vez. Concluir/cancelar é reservado ao desfecho explícito, não à simples mudança de responsável.

Pegar só atribui a Task e evita duas pessoas executarem a mesma pendência: concorrência/versionamento decide uma vencedora, e a colega precisa ver o estado atualizado. Responsabilidade “durante a execução” não introduz prazo de expiração, lease, cron ou status novo. Fechar tela/sair da sessão não devolve a tarefa. Devolver sem ter tentado gera mudança de atribuição, sem tentativa fictícia ou aumento da contagem.

Se a pessoa manteve para si e estará ausente, pode devolver explicitamente; gestão autorizada pode devolver/redistribuir, preservando autoria e preferência combinada com o paciente. Se Pegar e deixar sem andamento, a Task permanece pendente/atribuída e pode ficar atrasada; não some nem libera automaticamente. A visão de gestão acompanha isso dentro do acesso autorizado, sem dar à colega poder de tomar tarefa pessoal em silêncio.

No modo exclusivo de atendimento, devolver Task à fila não torna o contato/conversa público. Só quem já tem acesso pode receber/executar; mudança de posse do contato ou atribuição da conversa segue a ação própria autorizada do CRM. Pegar, devolver ou reagendar não altera Val, owner, qualificação ou thread.

### 8.2 Quando o lead volta à Val

**[DECISÃO DO PO] / [OBSERVADO NO CÓDIGO]** Preservar a regra herdada da [ADR 0010](decisions/0010-pool-mode-recepcao.md): em `pool_mode=reception`, fechamento autorizado do atendimento chama `release_lead_to_bot`, no fechamento manual ou por inatividade elegível. A Task não determina esse retorno e não prende o lead com a operadora até a próxima data.

| Ação / situação | Efeito no atendimento e na Task |
|---|---|
| Registrar tentativa, reagendar e Devolver à fila de tarefas | Só altera Task/histórico/responsabilidade; não fecha conversa nem libera a Val |
| Manter comigo | Mantém a responsável da Task; não mantém a Val silenciosa nem bloqueia cron/fechamento |
| Encerrar atendimento pelo caminho atual autorizado | Em Recepção, devolve à Val nos casos permitidos; mesma Task, prazo e histórico permanecem |
| Devolver contato à Recepção pelo menu existente | Retorna à pool humana sem encerrar; não é Devolver Task nem retorno ao bot |
| Novo inbound depois do retorno ao bot | Val pode responder conforme gates/motor atuais; Task pode sinalizar resposta, sem conclusão automática |

**[OBSERVADO NO CÓDIGO]** O release limpa `human_active` e o ciclo CX anterior, remove posse de contato/threads não-backup e define `bot_completed=False`, preservando qualificação, temperatura, setor/protocolo e prova LGPD ([database_firestore.py](../database_firestore.py#L2799)). Respeita guards como backup e revogação LGPD. Não dispara turno CX ou follow-up proativo; torna o bot apto a atender nova mensagem elegível. Não prometer que a Val já conheça tarefa, orçamento, data combinada ou agenda ProDoctor: F1 não integra esses dados ao agente.

**[OBSERVADO NO CÓDIGO]** Auto-close é configurável por tenant. Ligado: cron pode fechar atendimento elegível por inatividade; desligado: atendimento já respondido não fecha por esse motivo. Handoff sem resposta humana é protegido durante a espera; ultrapassado o teto, permanece a válvula de liberação quando cumprir as condições de inatividade e o cron executar, inclusive no caso assumido e abandonado sem resposta humana. Defaults do código local são 24h de inatividade e 7 dias de espera ([config.py](../config.py#L290)); não são confirmação dos valores/configuração ou da execução do cron em produção. Não confundir esses intervalos com a janela WhatsApp de 24h ou com antecedência de confirmação/lembrete.

Não foi acordado um novo prazo de retorno à IA por tarefa ou tentativa. F1 conserva configurações, crons e gates existentes. Um exemplo de operação é: combinar retorno → registrar/reagendar a mesma Task → encerrar o atendimento pelo fluxo atual → Val fica disponível para novo inbound → no prazo, uma operadora executa a Task pelos caminhos humanos existentes. Encerrar atendimento é ação separada; salvar a tarefa não deve fazê-lo implicitamente. Timeout de takeover também é outro mecanismo, sem equivaler ao release. Não usar `return_contact_to_bot` no reagendamento: ele redefine dados operacionais que F1 deve preservar.

## 9. Telas revisadas

### Lista e filas de trabalho

**[DECISÃO DO PO]** Atrasadas, Hoje, Próximas, Concluídas e Canceladas, fila compartilhada e próxima ação. Filtros Minhas/Fila; Equipe apenas para gestão autorizada. Atrasadas primeiro pelo prazo mais antigo; Hoje contém pendentes de hoje ainda não vencidas; Próximas, após hoje; agrupamento local, armazenamento UTC.

Linha: contato resolvido na leitura, ação, prazo, fila/responsável, quantidade derivada de tentativas e sinal de nova resposta. **[DECISÃO DO PO]** Filtro por Recepção/Orçamentos, com o mesmo acesso atual; fila não concede visibilidade por setor. Temperatura IA pode aparecer como contexto da fonte atual, sem cópia. Contagens respeitam acesso; não apresentar orçamento/pagamento sem fonte confiável.

### Cartão de próxima ação e criação/edição

**[DECISÃO DO PO]** Criar retorno é fluxo principal: “Me chama quinta”, “vou pensar”, “vou conversar com meu marido”, “preciso me organizar”. Campos mínimos: ação/tipo, prazo, contexto curto e fila Recepção; criadora pode não executar. **[DECISÃO DO PO]** Seleção de Recepção ou Orçamentos conforme objetivo; nomes podem mudar depois, preservando identidade e histórico.

Exemplo do fluxo esclarecido: consulta médica → operadora apresenta orçamento → equipe combina o próximo contato e cria a Task de acompanhamento, quando necessário. A apresentação do orçamento não cria tarefa ou encaminha o contato automaticamente em F1.

Cartão: próxima Task pendente, outras tarefas acessíveis e ações Pegar, Abrir contexto, Registrar tentativa, Adiar, Concluir, Cancelar. Abrir contexto é consulta e não tentativa/conclusão. **[DECISÃO DO PO — 18/10]** Se houver mensagem elegível posterior à referência, mostrar **Paciente respondeu após a última tentativa**; antes da primeira tentativa, **Paciente respondeu após a criação da tarefa**. Reagendar sem tentar preserva o aviso e a referência; tarefa continua pendente. Não apresentar resposta anterior à última tentativa como novidade daquela tentativa.

Modal: data/hora combinada em destaque, atalhos com prazo final visível, fila/pessoa autorizada e thread opcional. Informar conflito com fim de semana sem escolher outra data pela pessoa. Separar responsável da Task de dono do contato. Sem opção de envio automático em F1.

### Registro de tentativa e histórico

**[HIPÓTESE]** Modal com quem tentou, quando, resultado candidato e escolhas visíveis: manter pendente, reagendar ou concluir quando o objetivo daquela tarefa estiver resolvido. Mostrar próxima data antes de confirmar. **[DECISÃO DO PO — 18/10]** Aplicar a decisão 7: data combinada prioritária; sem combinação/retorno, próximo prazo escolhido pela operadora. Ao revisar três tentativas sem resposta, a equipe avalia histórico/abordagem e decide como continuar na mesma tarefa, com as opções de responsabilidade já aprovadas. Registrar apenas resultado/contexto comercial mínimo; não copiar mensagem ou pedir justificativa clínica.

**[DECISÃO DO PO — 18/10]** Ao informar AGENDOU, distinguir nova consulta de procedimento/tratamento. **[HIPÓTESE]** Mostrar essa escolha mínima no registro de resultado e identificar a tarefa cujo objetivo foi resolvido. A operadora verifica a marcação na agenda oficial, sem capturar detalhes clínicos; confirmação/lembrete, quando necessários, continuam como tarefas manuais distintas. A antecedência de 72h/24h foi confirmada para consulta; o rótulo procedimento/tratamento não cria automaticamente tarefas nem novas regras de lembrete.

Histórico mostra criação, Pegar/atribuição, cada tentativa, reagendamentos, conclusão/cancelamento e quem fez. Não transformar contagem em substituto do histórico. `not_reached` fica no resultado da tentativa, com reagendamento na mesma Task quando houver continuidade; parar tentativas tem escopo desta tarefa, sem “Encerrar paciente” implícito.

### Configurações → Follow-up → Dias e horários

**[DECISÃO DO PO — 13/10]** Incluir menu para Cristina configurar os horários. **[HIPÓTESE]** Situá-lo em Administração/Configurações, visível e editável conforme a autorização de gestão existente. Desenho mínimo:

| Controle | Comportamento proposto |
|---|---|
| Dias de contato | Selecionar dias de segunda a sexta; sábado/domingo permanecem indisponíveis no piloto, conforme regra já confirmada |
| Faixas por dia | Hora inicial/final, com possibilidade de intervalo; validar início anterior ao fim e ausência de sobreposição |
| Horário preferido dos atalhos | Opcional, escolhido pela clínica dentro de uma faixa válida; a data/hora combinada com o paciente tem prioridade e a prévia sempre mostra o resultado |
| Feriados e recessos | Cadastrar datas sem contato da clínica; nenhuma busca externa ou calendário importado presumidos |
| Confirmação e lembrete | Mostrar 72h e 24h como ações distintas; se cair em fim de semana/feriado, sugerir dia útil anterior e pedir confirmação do horário pela operadora |
| Prévia | Exibir o dia/hora final sugerido para cada ação antes de criar ou reagendar a Task |

**[HIPÓTESE]** Ao criar/reagendar, a pessoa continua escolhendo o retorno combinado com o paciente. O menu orienta e valida o prazo; se cair fora das faixas ou em data sem contato, pede outra escolha e mostra sugestões, sem substituir a data combinada silenciosamente. Preferência por terça/quarta/quinta não proíbe segunda/sexta. O calendário vale para Tasks de contato, não reescreve tentativas históricas nem exige mover uma tarefa interna que não envolva contato.

Mudar os horários vale para validação de novos agendamentos/reagendamentos; não muda `due_at`, responsabilidade, histórico ou estado de Tasks já existentes. Ao consultar uma pendência fora da configuração atual, exibir o conflito para revisão humana; nenhum reagendamento/cancelamento em massa ou cron novo. Na ausência de faixas confirmadas, indicar configuração pendente sem escolher 10h ou copiar automaticamente o expediente da Val. Um retorno incompatível exige novo acordo humano, sem exceção automática liberando fim de semana.

**[DECISÃO DO PO — 13/10]** Aprovado: para confirmação/lembrete cujo prazo nominal cair em fim de semana ou feriado, oferecer o dia útil anterior dentro dos dias/faixas permitidos e mostrar a data/hora final; a operadora confirma o horário antes de salvar. Exemplo fictício: consulta na segunda-feira → lembrete nominal no domingo → sugestão na sexta-feira, se houver contato permitido nesse dia. Se sexta também for data sem contato, buscar o dia permitido anterior. A sugestão respeita o acordo com o paciente e preserva prazos existentes até revisão humana; F1 continua lembrando a equipe.

**[DECISÃO DO PO — 17/10]** Se o prazo nominal ou dia útil anterior já passou quando a consulta foi marcada, seguir a regra de última hora abaixo: aproveitar o contato em curso ou sugerir primeiro horário permitido antes da consulta; sem horário disponível, destacar a pendência para decisão humana. Não sugerir prazo passado nem registrar contato fictício.

**[VALIDAR COM CRISTINA]** Cristina/gestão autorizada definirá faixas reais e datas sem contato antes do uso. Não presumir que o expediente da Val seja o horário aprovado de follow-up. **[HIPÓTESE]** Para prazo fora da faixa em dia útil, manter o fluxo já proposto: mostrar conflito, pedir escolha humana de horário permitido e preservar prazos existentes até revisão explícita; nenhuma política automática nova de antecipar/postergar.

### Confirmação em 72h e lembrete em 24h

**[CONFIRMADO COM CRISTINA — 08/10]** A agenda oficial é o **ProDoctor**, com **confirmação 72h antes** e **lembrete 24h antes** da consulta. São duas ações distintas; a conclusão da confirmação, por si, não elimina a tarefa do lembrete. As exceções aprovadas de última hora (17/10) e coincidência após ajuste de calendário (18/10) admitem cumprir ambas no mesmo contato do mesmo compromisso, com registro humano explícito de cada ação. Esses prazos não são a janela WhatsApp de 24h.

**[HIPÓTESE]** F1 permite duas Tasks manuais, com prazos escolhidos após consulta humana à agenda oficial e referência mínima ao compromisso quando disponível. Distinguir horário da consulta e prazo de cada contato; nenhum vem de “quer agendar”, link enviado ou texto inferido. Informar a finalidade da tarefa e manter histórico próprio, sem copiar agenda médica ou criar integração/API não verificada.

**[DECISÃO DO PO — 13/10]** Para fim de semana/feriado, sugerir o dia útil anterior e confirmar o horário com a operadora.

**[DECISÃO DO PO — 17/10]** Aprovado o tratamento de **agendamento de última hora**, discutido a partir do exemplo fictício: marcação segunda-feira às 13h para consulta terça-feira às 7h. Nesse caso, confirmação de 72h caiu no sábado às 7h e lembrete de 24h na segunda às 7h, ambos antes da marcação:

1. Se a operadora já está falando com o paciente na marcação, reforça data/hora, confirma com ele e registra o resultado naquele contato.
2. Se a consulta foi registrada sem esse contato, o CRM sugere tarefa no primeiro horário permitido disponível a partir da marcação e antes da consulta. Pode ser a própria segunda às 13h se estiver dentro das faixas; a operadora revisa o prazo.
3. Se não houver horário permitido antes da consulta, destacar pendência de consulta próxima para decisão da equipe; o alerta não confirma presença, não libera envio fora das regras e não move a consulta no ProDoctor.
4. Quando ambos os prazos já passaram, **um único contato pode cumprir confirmação e lembrete**, com registro humano explícito de cada ação efetivamente realizada. Se houver duas Tasks, preservar seus IDs/históricos e registrar as duas conclusões autorizadas, com uma única tentativa real. Apenas tentar falar ou enviar pergunta sem resposta não comprova confirmação; a ação que não foi cumprida continua pendente.

A exceção não elimina um lembrete ainda futuro só porque a consulta foi marcada com menos de 72h. Exemplo fictício: segunda às 13h para quarta às 13h permite confirmar na marcação e manter o lembrete de terça às 13h. F1 continua manual: registrar consulta ou chegar o prazo não cria/conclui Tasks nem envia mensagem automaticamente. Nenhuma nova integração com ProDoctor é presumida.

**[DECISÃO DO PO — 18/10]** Aprovada a extensão do contato único quando confirmação e lembrete do **mesmo compromisso** coincidirem após ajustes de fim de semana/feriado. A operadora pode cumprir as duas ações no mesmo contato e registrar explicitamente cada ação efetivamente realizada. Uma tentativa real, duas conclusões humanas autorizadas quando cabíveis, sem mesclar Tasks ou concluir uma por efeito da outra. O vínculo ao mesmo compromisso é conferido pela equipe na fonte oficial; não inferir que duas tarefas do contato pertencem à mesma consulta.

Exemplo fictício: consulta segunda às 10h → confirmação nominal sexta às 10h; lembrete nominal domingo às 10h → sugestão de sexta em horário permitido. Se as duas ações coincidirem no prazo escolhido pela operadora, um contato pode cumprir ambas. Sem confirmação do paciente, não registrar presença confirmada; lembretes futuros de outros casos, Tasks de outro compromisso, responsabilidade e histórico permanecem preservados. F1 não envia mensagem nem conclui as duas ações automaticamente.

Remarcação/cancelamento da consulta exige revisão humana das Tasks vinculadas à data anterior, preservando histórico e pendências independentes.

### Registrar recusa — escopo explícito em F1

**[DECISÃO DO PO — 18/10]** Oferecer ações distintas: **Encerrar este acompanhamento** e **Registrar pedido de não receber contatos comerciais**. A primeira altera apenas a Task correspondente; a segunda registra a preferência no contato, com o alcance descrito na seção 7.5. A operadora registra o pedido efetivamente feito pelo paciente, sem presumir recusa geral por ENCERRADO ou tag.

**[HIPÓTESE]** Mostrar o escopo e efeito antes de salvar e uma indicação persistente da preferência no contexto autorizado. Task comercial pendente fica identificada para revisão humana e sem nova abordagem; não cancelar consultas, lembretes pertinentes ou tarefas independentes. Ação de preferência não fecha thread, muda qualificação, silencia Val ou revoga LGPD. Detalhes de preço, adiamento e outras causas podem usar motivos mínimos a validar; sem narrativa clínica.

### Pausar/encerrar relacionamento — tela futura

**[HIPÓTESE]** Quando entrar: escolha explícita Pausado/Encerrado e motivo estruturado em campos separados. Exemplos de categorias a validar: sem interesse, não fechou agora, tratamento concluído, recomendação médica, sem resposta, questão financeira, adiou, outro.

Permitir relatórios separados de preço, adiamento, tratamento concluído e silêncio, sem lançar toda a população em ENCERRADO. Categorias `medical_recommendation`/`treatment_completed` não exigem diagnóstico, texto da recomendação, sintomas ou laudo. Mesmo categorias mínimas permanecem sujeitas ao acesso e retenção adequados; não são metadados públicos.

O painel amplo de relacionamento não faz parte de F1. A preferência comercial mínima da seção 7.5 integra a decisão 6 e não exige esse painel. Pausar Task significa adiar/gerir aquela ação; não altera relacionamento global.

## 10. Integração e privacidade

**[HIPÓTESE]** Novos módulos: `followup_repository.py`, `followup_service.py`, `followup_routes.py` e `frontend/src/features/followup/`. Router/RBAC/acesso e montagem de UI recebem integrações pequenas; evitar imports circulares ou cópia divergente do predicado de acesso.

Rotas indicativas: criar/listar/editar, pegar/atribuir, registrar tentativa com eventual reagendamento/conclusão, adiar, concluir, cancelar, listar histórico e próxima ação. Nenhuma rota F1 envia WhatsApp. Operações compostas transacionais com `version`/idempotência e limites de payload.

F1 não precisa de cron de atraso, hook de inbound ou novo mecanismo de IA. Consulta de mensagens para o sinal e leitura de contexto existente são pontos explícitos de integração. Novos campos em snapshot, se houver, exigem types/normalização/rules coerentes; REST mantém novas coleções isoladas do cliente. A preferência comercial da decisão 6 exige também integração compartilhada nos produtores comerciais já existentes antes da liberação de F1; isso não cria envio automático de follow-up ou subsistema de relacionamento.

`main.py`, `database_firestore.py`, `webhook.py`, `config.py` e App são compartilhados com a frente de reabertura: acordar pontos exatos antes de editar e revisar merge em `develop`. Não copiar worker ou alterar o outro worktree.

**[DECISÃO DO PO]** Minimização: não copiar médico, convênio, valor/pagamento, diagnóstico, laudo, sintomas ou conversas para facilitar UI. Task/Activity guardam IDs e contexto operacional mínimo. Aplicar políticas existentes de LGPD, retenção, retificação e eliminação; não inventar prazo de retenção.

**[OBSERVADO NO CÓDIGO]** Arquivo não elimina fisicamente dados. **[HIPÓTESE]** Revisar as rotinas efetivas de privacidade antes da liberação de F1 e incluir as novas entidades no processo aplicável, sem afirmar que um DELETE atual já as apagaria. Histórico append-only não pode criar dados pessoais inacessíveis ao processo de retificação/eliminação.

Implementação futura usa `C:\Rafael\castro-intelligence\.venv\Scripts\python.exe`; no frontend deste worktree, `npm ci` antes do build. Commit, push e deploy somente por pedido explícito. Deploy apenas da pasta principal após merge. Nesta revisão, apenas documentação é alterada.

## 11. Contratos de envio — limites, decisão 9 e integração da decisão 6

**[DECISÃO DO PO — 18/10]** A recusa geral de contatos comerciais deve alcançar também os envios comerciais já existentes antes da liberação de F1, conforme seção 7.5. As demais regras abaixo são contratos herdados para integrações e futura F3; a aprovação não autoriza implementar mensagens automáticas nesta fase.

**[DECISÃO DO PO]** Reativação/campanha de contatos abandonados na Val é distinta de Task individual. Script/fluxo de reabertura existe ou está preparado; não representá-lo como tentativas humanas em `crm_tasks`. Futura automação compartilha as políticas abaixo, não a semântica inteira de cada tentativa de reabertura.

**[DECISÃO DO PO — 18/10]** O PO solicitou elevar o teto interno compartilhado de **250 para 500 envios por dia**, mantendo uma única fonte de orçamento para o portfólio **Castro Operações WhatsApp**. **500 é o objetivo registrado, não um limite já ativado ou uma capacidade Meta verificada.** Nenhuma configuração, código ou produção foi alterada nesta etapa documental. A referência anterior de 250 era a regra combinada nesta sessão, não prova de configuração diária global em produção; não confundir teto diário, limite por lote e capacidade da Meta.

**Esclarecimento operacional do PO em 18/10:** o canal identificado na sessão como `varizemed-test` é usado pela **Castro Intelligence** e atualmente tem pouca utilização. Registrar essa finalidade sem renomear tenant/canal, mudar roteamento ou presumir sandbox. Seu uso continua dentro do mesmo orçamento compartilhado; uso baixo não representa reserva separada nem comprova capacidade adicional autorizada na Meta. Confirmar o mapeamento tenant/canal ao preparar a ativação.

**Dependência para elevar o teto:** conferir o limite/capacidade disponível na Meta para o portfólio e alinhar configuração, reservas e produtores no mecanismo comum. O aumento não é consequência automática de um canal estar pouco usado, não amplia o 2/90 e não libera a Hubloc enquanto permanecer a restrição informada. Até validar e ativar a mudança autorizada, não tratar 500 como saldo disponível ou fazer um ajuste isolado neste módulo. Registrar a nova intenção para conciliação com os planos/ADRs da frente paralela, sem editar o outro worktree.

| Regra | Aplicação na integração |
|---|---|
| Fora da janela de 24h exige template pago | Validar janela da thread/canal na execução; tarefa não autoriza texto livre |
| Texto livre dentro de 24h não consome limite Meta | Isso não isenta massa do teto interno CRM |
| Teto diário compartilhado: 500 solicitados pelo PO, substituindo o objetivo anterior de 250 | Mesma fonte/reserva para hubloc, varizemed e varizemed-test/Castro Intelligence, reabertura e follow-up; ativação dos 500 depende de validação Meta e integração comum |
| 2 envios em massa por contato em 90 dias | Lista única `reopen_batch_sent_at`, `{at, audience}`; inbound não zera |
| Sem aceite LGPD / revogado / desatualizado | Nenhum envio em massa; compartilhar gate por data da política |
| Encerrar em retomada | `reopen_opt_out` bloqueia até inbound novo válido; Task/reentrega/adiamento não limpam |
| Recusa geral de novos contatos comerciais | Preferência comum no contato, distinta do opt-out de retomada; produtores comerciais existentes e futuros respeitam; inbound genérico não libera |
| Hubloc limitada | Nenhuma massa lá enquanto vigorar o bloqueio, inclusive follow-up |
| Automático não passa pelo gate do operador | Não chamar `_check_conv_send_permission`, silenciar Val ou simular atenção humana |
| Canal de massa | Standard ativo do tenant; coexistence fora |

**[DECISÃO DO PO — 18/10, aprovação provisória]** Decisão 9: incluir **todo follow-up automático proativo**, inclusive job individual e texto livre dentro da janela de 24h, com `audience="followup"` na lista única `reopen_batch_sent_at`. Consome o mesmo teto de 2 envios/90 dias do contato e orçamento diário CRM compartilhado, sem contador de follow-up. A abrangência inclui eventuais confirmações e lembretes automáticos de consulta. Texto livre dentro de 24h continua sem consumo do limite Meta segundo a regra herdada; o consumo aqui é interno ao CRM.

Exemplo: uma reabertura e um follow-up automático consomem os dois envios do 2/90. A contagem é por envio efetivo, não por quantidade de Tasks ou finalidades cumpridas pela mesma mensagem. Tentativa humana, registro, prazo e tarefa não consomem teto por si; mensagens humanas unitárias e respostas reativas da Val mantêm os caminhos/regras próprios. A aprovação provisória do planejamento não autoriza automação em F1 nem alteração do teto em produção.

Três tentativas humanas usuais, ou continuidade além delas, não autorizam três envios em massa quando o teto é 2/90. Silêncio, consulta e pagamento não substituem aceite LGPD nem eliminam opt-out. Contagem humana e consumo de mensagens são fontes/finalidades diferentes; não reutilizar `reopen_attempts` para acompanhar tentativas de operadora.

O plano paralelo registra folga `cap + ~20` e reserva não transacional; isso conflita com o teto estrito desta sessão. Antes de F3, um mecanismo comum precisa de reserva atômica por portfólio/contato, cobertura dos produtores de massa inclusive scripts, horário efetivo de cada consumo e janela móvel de últimas 24h. Não criar contador de follow-up paralelo ou somas informais entre dois motores.

Sucesso confirma consumo uma vez; timeout/resultado incerto mantém reserva conservadora e exige reconciliação, sem retry cego. Agendamentos duráveis, revalidação antes de cada envio, cancelamento e freios de billing/qualidade são pré-requisitos futuros. Código desta branch não comprova que toda a evolução da reabertura esteja implementada ou em produção.

`audience=followup` é origem para consumo/auditoria, não destino de resposta; destino Val/equipe depende de contrato próprio e estado atual. Não inserir terceiro público implicitamente em `reception`/`bot`, não reutilizar `reopen_attempts`/auto-resolve para fechar thread por tarefa vencida. Preservar proteções de mensagem automática: `human_outbound=False`, `promote_qualification=False`, `reopen_attendance=False`, `advance_recency=False`.

Estados futuros paused/closed precisarão de política explícita de elegibilidade; não inferir liberação por motivo ou mensagem nova, nem usá-los para contornar LGPD/opt-out. Fechar Task não escreve esses estados. F3 não será implementada nesta frente documental.

## 12. Riscos e critérios de aceitação

### Riscos revisados

| Risco | Consequência | Contenção proposta |
|---|---|---|
| Copiar planilha inteira em Task | Mistura orçamento/contato/resultado e duplica dados | Mapeamento conceitual; F1 não importa CSV |
| Confundir INTERESSE 1 com enum | Anotações viram temperatura/prazo falsos | Reação ao orçamento pós-consulta confirmada; manter origem/momento separados da IA |
| DATA histórica tratada como prazo | Follow-up incorreto e tentativas inventadas | Datas posteriores são tentativas, não retorno; não reconstruir hora/ano/autoria ausentes |
| Nome sozinho identifica paciente | Liga orçamento ao contato errado | Não importar por nome; 449 telefones ausentes |
| FRIO/MORNO/QUENTE paralelos | Divergência da fonte IA | Fonte atual; falta de temperatura não é FRIO |
| Convertido legado interpretado como pagamento | Conversão/receita financeira falsas | Manter uso atual; Ganho financeiro confirmado no ProDoctor, sem migração automática |
| Remover Qualificado globalmente ou esconder registros antes da revisão | Quebra Hubloc e perde acesso a dados legados | Descontinuação proposta só clínica; leitura/filtro legado até revisar casos e auditoria |
| Tags viram status, prazo ou gatilho de envio | Contradições e contato sem autorização | Vocabulário complementar; estado/tarefa/gates reais preservados |
| Tag clínica copiada para tarefas ou audiência | Expõe contexto de saúde e amplia finalidade | Manter na fonte sob acesso atual; sem cópia ou seleção automática por tag de saúde |
| AGENDOU confundido com quente/Ganho/encerramento global | Conversão ou perda indevidas | Identificar consulta ou procedimento/tratamento e objetivo resolvido; pagamento confirmado no ProDoctor é Ganho; outras tarefas preservadas |
| ENCERRADO sem escopo / preferência só na Task ou tag | Outro produtor comercial retoma após a recusa | Escopos específicos, preferência no contato e gate comum antes da liberação; sem inferir paused ou revogação LGPD |
| Motivo clínico detalhado em Activity | Exposição desnecessária de dado sensível | Categoria mínima quando necessária; acesso/retenção |
| Orçamento no contato/cópia por Task | Sobrescreve ciclos, pagamentos e médicos | Fonte comercial futura própria; Task desacoplada |
| Counter único sem histórico de tentativas | Perde autoria, datas e sequência | Eventos `task_attempted`, contagem derivada |
| Terceira tentativa vira parada automática ou repetição sem revisão | Perde oportunidade ou insiste sem avaliar contexto | Revisão de histórico/abordagem após três sem resposta, prazo humano, mesma Task aberta e restrições de contato preservadas |
| Prazos 72h/24h caem no fim de semana ou confundem janela WhatsApp | Contato inoportuno ou template incorreto | Ações separadas, menu de dias/faixas; dia útil anterior sugerido com confirmação humana; exceções pendentes |
| Configuração de follow-up altera expediente da Val ou remarca compromissos existentes | Aviso incorreto ao paciente ou perda da data combinada | Configuração por finalidade; prazos existentes preservados e conflitos revisados por pessoa |
| Contato de última hora ou coincidente por calendário vira duas tentativas ou cancela lembrete ainda futuro | Histórico inflado ou acompanhamento perdido | Uma tentativa real; duas ações cumpridas e registradas explicitamente, mesmo compromisso conferido e lembrete futuro preservado |
| Tentativa sem resposta vira confirmação de presença | Agenda aparenta estar confirmada sem retorno do paciente | Registrar resultado efetivo; confirmação não inferida de envio, leitura ou prazo |
| Colaboração vira fila pública por setor | Expõe contato fora do acesso | Fila encaminha trabalho; autorização atual e responsabilidade auditada |
| Adiar/concluir conta nova tentativa | Inflaciona histórico/limite | Ações distintas, tentativa estável e idempotência |
| `last_inbound_at` vira prova de resposta | Reentrega antiga gera falso sinal | Mensagem elegível por timestamp real e âncora |
| Qualquer inbound/abertura conclui Task | Retorno ou confirmação desaparece | F1 sinaliza; conclusão humana explícita |
| Pegar/abrir Task usa gate/endpoint de atendimento | Assume lead ou silencia Val | Claim só Task; contexto por consulta |
| Acesso ao contato permite alterar Task da colega | Corrida/responsabilidade perdida | Autoridade sobre Task + versão + redistribuição |
| Transferência deixa acesso antigo ativo | Vazamento de contexto | Revalidar contato/thread em leitura/ação/contagem |
| Arquivo interpretado como eliminação | Dados novos fora do processo de privacidade | Revisar retenção/retificação/eliminação reais |
| Listeners/scans irrestritos | Custo e filtro de acesso tardio | Paginação/índices/escopo server-side |
| Tentativas humanas confundidas com 2/90 | Bloqueio indevido ou bypass de massa | Históricos distintos; mesmo orçamento para envios futuros |
| Corrida reabertura/follow-up | Excede teto comum ativo ou 2/90 | Reserva comum estrita; 500/dia é objetivo solicitado, sujeito a validação e ativação |
| Supor que varizemed-test seja sandbox ou que pouco uso libere 500 | Teste em canal operacional ou excesso de capacidade | Esclarecimento do uso pela Castro Intelligence; validar ambiente/destinatários e capacidade Meta antes da ativação |

### Critérios de aceitação de F1

| # | Caso | Resultado esperado |
|---|---|---|
| 1 | Criar Task manual em contato existente | Task + Activity, sem novo Lead/Conversation, orçamento ou mensagem |
| 2 | Criadora agenda na Recepção | Fila compartilhada; não precisa executar |
| 3 | Operadora Pega Task | Só responsabilidade de Task; nenhum owner/assignment da conversa/Val/status alterado |
| 4 | Prazo vence | Atrasadas/Hoje/Próximas conforme relógio local, sem status overdue persistido |
| 5 | Várias tarefas no contato | Próxima pendente por menor prazo/ID; demais preservadas |
| 6 | Paciente pergunta endereço após criação | Sinal de resposta; confirmação/Task continua pendente |
| 7 | Mensagem antiga é reentregue após criação | Sem falso sinal por relógio de ingestão e sem conclusão |
| 8 | Abrir contexto/contact/thread | Apenas consulta; não completa, registra tentativa, assume ou materializa atendimento |
| 9 | Tentativa sem resposta | Histórico com quem/quando/resultado; não altera conversão |
| 10 | Registrar tentativa + reagendar | Mesma Task pending e dois fatos coerentes; prazo anterior/novo; tentativa uma vez |
| 11 | Adiar sem tentativa | Novo prazo/histórico, contagem não aumenta |
| 12 | Múltiplas tentativas | Todas acessíveis paginadas; contagem derivada, sem só sobrescrever número |
| 13 | Tentativa com `not_reached` e continuidade | Mesma Task pendente, com resultado/data/autora no histórico e próximo prazo escolhido; sem nova tarefa ou conversão |
| 14 | Parar tentativas/cancelar | Histórico preservado, motivo da tarefa; nenhuma relação global encerrada |
| 15 | Duas operadoras na mesma versão | Primeira mutação válida; segunda recebe conflito, sem overwrite ou tentativa duplicada |
| 16 | Clique duplo/retry na mesma tentativa | Uma tentativa; eventos compostos idempotentes |
| 17 | Lead transferido/pessoa desativada | Acesso antigo revogado conforme escopo; gestão identifica pendência e redistribui |
| 18 | Task de colega da pool | Acesso ao contato não concede autoridade para alterar responsabilidade alheia |
| 19 | IDs de outro tenant ou thread alheia | Negado; Task não concede acesso; contagens não vazam |
| 19a | Atribuir a pessoa inativa, de outro tenant ou sem acesso ao contato/thread | Rejeitado pelo backend, mesmo se quem atribui for gestor |
| 20 | Qualquer ação F1 | Nenhum WhatsApp pelo módulo e nenhum consumo de orçamento de massa |
| 21 | Exibir temperatura | Fonte IA atual, sem copiar/classificar; ausente não vira FRIO |
| 22 | AGENDOU/ENCERRADO aparecem no contexto | Não viram temperatura, conversão, Task.status ou cancelamento global automaticamente |
| 23 | Cancelar/concluir Task | Não altera relationship_status/reason, qualification, LGPD, opt-out ou thread |
| 24 | Contexto/histórico | Não duplica mensagem, laudo, sintomas, convênio ou valor para UI |
| 25 | Prazo/registro de tentativa | UTC+fuso local; distinguir data efetiva, registro e próximo retorno; sem tentativa futura |
| 26 | Confirmação 72h e lembrete 24h de consulta | Duas ações manuais baseadas no ProDoctor; concluir uma, por si, preserva a outra; contato único nas exceções aprovadas exige registro humano de ambas e mesmo compromisso, sem integração/inferência por link |
| 27 | Privacidade/retificação aplicável | Novas entidades incluídas no processo autorizado; arquivo não anunciado como exclusão física |
| 28 | Painel/histórico/listagem | Paginação/índices/acesso atual; sem full-scan ou uso indevido de unread/alarme |
| 29 | Terceira tentativa sem resposta | Equipe revisa histórico/abordagem antes de continuar; mesma Task aberta e próximo prazo escolhido pela operadora; silêncio não vira interesse/consentimento |
| 30 | Atalho ou prazo de contato cai no fim de semana | Solicita escolha humana de dia útil; sem deslocamento silencioso; terça/quarta/quinta são preferência |
| 31 | AGENDOU fecha objetivo do acompanhamento | Categoria consulta ou procedimento/tratamento e desfecho humano explícito; não marca Ganho, fecha relacionamento ou cancela confirmação/lembrete independentes |
| 32 | Consulta remarcada/cancelada no ProDoctor | Revisão humana das Tasks relacionadas à data anterior, com histórico e demais tarefas preservados |
| 33 | Contato Não convertido com tag Preço e retorno pendente | Task humana válida sob acesso atual; filtro não autoriza lote nem altera desfecho |
| 34 | Criar/adiar/concluir Task em contato com tags | Tags e qualificação preservadas; nenhum contexto clínico copiado para Task/Activity |
| 35 | Renomear Recepção ou Orçamentos | Identificador da fila e tarefas/histórico preservados; nenhum acesso, setor ou prazo alterado |
| 36 | Registrar tentativa + reagendar com opção padrão Devolver à fila | Mesma Task, novo prazo, responsável individual liberada e histórico coerente; sem fechamento de atendimento ou mudança da Val |
| 37 | Reagendar com Manter comigo | Responsável preservada na Task; cron/retorno ao bot continuam seus fluxos próprios |
| 38 | Atendimento encerrado e lead devolvido à Val | Task mantém ID, prazo e histórico; nenhum disparo de follow-up automático pelo módulo |
| 39 | Gestão salva dias/faixas de follow-up | Tenant e autorização validados no backend; faixas válidas, versão e auditoria; nenhum horário da Val ou envio alterado |
| 40 | Alterar faixa ou cadastrar data sem contato com Tasks existentes | Prazos/histórico preservados; consulta aponta conflito para revisão humana, sem remarcação em massa |
| 41 | Criar/reagendar contato fora das faixas ou em data sem contato | Escolha humana de prazo permitido e prévia final; sem deslocamento silencioso ou alteração de tentativa passada |
| 42 | Confirmação/lembrete nominal em fim de semana ou feriado | Sugere dia útil anterior nas faixas permitidas, com prévia e confirmação da operadora; data anterior já passada segue última hora, sem criar tentativa fictícia ou mover Task existente |
| 43 | Marca segunda 13h para terça 7h, com prazos 72h/24h já passados | Aproveita contato humano na marcação ou sugere primeiro horário permitido antes da consulta; sem horário, destaca pendência para equipe; nenhum envio automático |
| 44 | Um contato efetivamente cumpre confirmação e lembrete na última hora ou coincidência após ajuste | Uma tentativa real, mesmo compromisso conferido, registro humano de ambas as ações e conclusões autorizadas sem perda de histórico; sem resposta, não registrar presença confirmada |
| 45 | Marca segunda 13h para quarta 13h, com lembrete ainda futuro | Confirmação pode ocorrer na marcação; lembrete terça 13h preservado, sem conclusão automática por antecedência menor que 72h |
| 46 | Confirmação e lembrete do mesmo compromisso coincidem após ajuste de calendário | Um contato pode cumprir as duas ações; registro/conclusão explícitos por Task e uma única tentativa, sem conclusão automática, outro compromisso ou perda de histórico |
| 47 | AGENDOU pode ser nova consulta ou procedimento/tratamento | Registro humano identifica categoria e objetivo resolvido, sem detalhes clínicos, novo status, conclusão de outras tarefas ou prova de pagamento |
| 48 | Paciente recusa somente aquele orçamento/procedimento | Encerra explicitamente o acompanhamento correspondente; demais tarefas, consulta e preferência comercial geral preservadas |
| 49 | Paciente pede fim de novos contatos comerciais | Preferência estruturada/auditada no contato; retomadas comerciais impedidas, Tasks pendentes visíveis para revisão; consultas e tarefas independentes preservadas |
| 50 | Novo inbound após recusa comercial geral | Pode liberar somente o opt-out herdado conforme sua regra; não apaga preferência comercial geral nem recompõe 2/90 ou orçamento diário |
| 51 | Reabertura/worker/script comercial tenta enviar após recusa geral | Mesmo estado consultado e envio impedido; cobertura dos produtores é dependência de liberação, não promessa de implementação futura só em F3 |
| 52 | Há data combinada com o paciente | Data/hora combinada têm prioridade sobre atalhos; conflito com calendário exige escolha humana, sem deslocamento silencioso |
| 53 | Sem data combinada ou após tentativa sem resposta | Operadora escolhe próximo prazo com prévia, dias/faixas permitidos e responsabilidade conforme decisão 3; sem intervalo universal, nova Task ou tentativa fictícia |
| 54 | Nova tentativa após resposta anterior | Referência avança para a tentativa efetiva e rótulo usa última tentativa; resposta anterior não vira novidade dessa tentativa; Task permanece pendente |
| 55 | Adiar/editar/redistribuir após paciente responder | Referência e aviso preservados, sem concluir Task ou consumir orçamento |
| 56 | Tentativa registrada retroativamente ou resposta sem timestamp real válido | Não recua referência nem usa recorded_at/ingestão como prova; sem falso sinal de replay ou tentativa futura |

**Critério futuro de relacionamento:** quando essa funcionalidade entrar, pausa/encerramento exigem status e motivo explícitos, AGENDOU continua separado e nenhum detalhe clínico é exigido por padrão.

**Critérios futuros F2/F3:** evento explícito não duplica Task; `complete_on_reply` só em intenção aprovada; reabertura/follow-up concorrentes não excedem o teto comum efetivamente validado/ativo nem 2/90; objetivo de 500/dia não é presumido ativo. Janela/LGPD/opt-out/Hubloc respeitados; falha ambígua reconciliada sem retry; audience de consumo não decide resposta/auto-resolve. Conforme decisão 9, job proativo individual e texto livre na janela também entram no orçamento CRM. Confirmação/lembrete automático sem saldo ou com 2/90 esgotado fica impedido; consulta e Task são preservadas para avaliação humana, sem migração automática para envio do operador ou liberação de outros gates.

A revisão documental foi seguida pela implementação local de F1, autorizada pelo PO em 18/10. As simulações e limites da validação estão registrados na seção 16. Nenhum smoke CX/produção foi executado.

## 13. Atualizações das versões anteriores e decisões pendentes

| Plano anterior | Situação nesta revisão |
|---|---|
| F1 manual, fila e sinal de inbound eram sugestões/decisões abertas | **[DECISÃO DO PO]** Fechados; não perguntar novamente se implementar mensagens/IA/Kanban em F1 |
| Tentativa aparecia só como resultado de conclusão | **[DECISÃO DO PO]** Tentativa exige evento/histórico próprio; conclusão permanece ação distinta |
| Orçamento +48h tratado como primeiro fluxo padrão; atalhos sugeridos às 10h | **[HIPÓTESE]** Dois dias só para alguns casos; horário/default universal não aprovado |
| Sinal por comparação de timestamps agregados | **[OBSERVADO NO CÓDIGO]** Insuficiente; proposta de mensagem persistida elegível após âncora |
| Abrir contexto respeitando caminho atual sem especificar mutação | **[OBSERVADO NO CÓDIGO]** `conversation/open` tem efeitos; contexto deve usar consulta |
| Temperatura IA não era explicitamente fonte do modelo | **[DECISÃO DO PO] / [OBSERVADO NO CÓDIGO]** Fonte existe; não duplicar qualificação |
| Etapa comercial ampla/`crm_stage` sem separar relacionamento | **[HIPÓTESE]** Separar comercial, relationship_status e relationship_reason, além de estados existentes |
| Cancelar pendências por desfecho terminal/arquivo como default sugerido | **[CONFIRMADO COM CRISTINA — 08/10]** AGENDOU/ENCERRADO fecha ciclo, sem autorizar cancelamento global |
| DATA dos blocos poderia ser retorno futuro; INTERESSE sem finalidade confirmada | **[CONFIRMADO COM CRISTINA — 08/10]** DATA registra tentativas passadas; interesses registram reação inicial e nas retomadas |
| Limite de duas/três tentativas e marco de Ganho ainda em aberto | **[CONFIRMADO COM CRISTINA — 08/10]** Três usuais sem teto rígido; Ganho é pagamento confirmado no ProDoctor |
| Lembrete de um dia sem fonte oficial definida | **[CONFIRMADO COM CRISTINA — 08/10]** Agenda ProDoctor; confirmação 72h e lembrete 24h. **[DECISÃO DO PO — 13/10]** Fim de semana/feriado: sugestão de dia útil anterior com confirmação humana; exceções pendentes |
| Rotina de exclusão do contato presumida | **[OBSERVADO NO CÓDIGO]** DELETE arquiva; revisão de processo real de privacidade necessária |
| Dados de orçamento poderiam ser extensão simples do contato | **[HIPÓTESE]** Fonte comercial própria futura para evitar sobrescrever ciclos; não criar em F1 |

**Decisões encerradas em 13/10:** (1) filas Recepção + Orçamentos, com possibilidade de renomear depois; (2) tentativas/reagendamentos na mesma tarefa, acumulando histórico; (3) Devolver à fila ao reagendar como padrão, com Manter comigo como exceção explícita e redistribuição pela gestão autorizada. Retorno à Val preserva o ciclo atual do atendimento, sem novo prazo por Task. Não reabrir essas escolhas.

**Decisão 4 de produto consolidada em 18/10:** aprovados menu de horários para Cristina/gestão autorizada, sugestão de dia útil anterior em fim de semana/feriado, tratamento de última hora e contato único para confirmação/lembrete coincidentes após ajuste de calendário. As duas ações do mesmo compromisso precisam ser efetivamente cumpridas e registradas pela operadora, com uma tentativa real e sem conclusão automática. Na última hora sem contato prévio, sugerir primeiro horário permitido antes da consulta; sem horário, pendência destacada para a equipe. Lembrete ainda futuro permanece nos demais casos. Faixas/datas sem contato são configuração operacional necessária antes do uso; fora da faixa em dia útil mantém escolha humana e prévia já propostas no menu, sem decidir ajuste automático. Não reabrir as aprovações de calendário. A decisão 9 e a solicitação de aumento de teto estão registradas abaixo; os detalhes de ativação continuam pendências técnicas.

**Decisão 5 consolidada em 18/10:** AGENDOU no pós-orçamento pode representar nova consulta ou procedimento/tratamento, conforme o caso. Categoria e objetivo resolvido identificados pela equipe; conclusão humana daquele acompanhamento, outras tarefas preservadas e Ganho separado, pelo pagamento confirmado no ProDoctor. Não perguntar novamente qual dos dois compromissos é permitido. Decisão 9 registrada provisoriamente abaixo; ativação continua futura.

**Decisão 6 — escopos consolidados em 18/10:** recusa daquele orçamento/procedimento encerra apenas o acompanhamento correspondente; pedido de fim de novos contatos comerciais interrompe futuras retomadas comerciais do contato, preservando consultas marcadas e tarefas independentes. F1 precisa da preferência mínima e integração comum da seção 7.5; não de um subsistema de relacionamento. Catálogo amplo de motivos e desenho de reversão continuam detalhamento proposto; não reabrir a separação aprovada. Decisão 9 registrada provisoriamente abaixo; ativação continua futura.

**Decisão 7 consolidada em 18/10:** data combinada prioritária; sem data/retorno, operadora escolhe o próximo prazo com atalhos permitidos. Após três tentativas sem resposta, equipe revisa histórico/abordagem antes de continuar na mesma Task aberta. Sem prazo universal, parada por contagem ou nova tarefa a cada tentativa. Responsabilidade mantém a decisão 3, e recusas/limites continuam válidos. Não reabrir quem escolhe o prazo ou a revisão já aprovada. Decisão 9 registrada provisoriamente abaixo; não criar automação ou contador novo nesta etapa.

**Decisão 8 consolidada em 18/10:** aviso considera resposta após a última tentativa real; antes da primeira, criação da tarefa. Adiamento preserva referência/aviso; nova mensagem não conclui Task. Implementação respeita timestamp real, acesso atual e regras de registro retroativo da seção 3. Não perguntar novamente qual referência usar. Decisão 9 registrada provisoriamente abaixo; F1 continua humana.

**Decisão 9 aprovada provisoriamente em 18/10:** todo follow-up automático proativo, inclusive individual e dentro de 24h, usa o mesmo 2/90 e orçamento CRM da reabertura, com `audience=followup` na lista única. Inclui confirmações/lembretes automáticos futuros; sem implementação ou contador adicional. O PO concordou com o planejado por enquanto e solicitou aumentar o objetivo diário compartilhado para **500**, sujeito à verificação Meta e ativação coordenada. Esclareceu o uso de `varizemed-test` pela Castro Intelligence, atualmente baixo. Não registrar capacidade disponível, produção alterada ou aprovação de disparos.

**Pendências do desenho e de liberação**, sem reabrir escopo decidido:
- **[HIPÓTESE]** Aprovar tipos/resultados mínimos e validação de prazo de contato sem fins de semana. Não criar limite rígido de tentativas; adotar data combinada antes de qualquer atalho.
- **[HIPÓTESE]** Aprovar descontinuação de Qualificado nas novas marcações da clínica e revisão dos poucos casos existentes para Não convertido + tags, conforme seção 5.2. Manter os demais estados e o uso atual de Convertido; Ganho financeiro no ProDoctor permanece distinto. Tags de motivo não criam tarefas ou liberam campanhas automaticamente.
- **[HIPÓTESE]** Detalhar motivos mínimos e reversão de preferência antes da implementação. Continuidade sem data/retorno, escopos da recusa, compromissos de AGENDOU, calendário, Ganho e fonte oficial já foram esclarecidos. Horários reais e feriados serão definidos pela clínica na configuração, sem inventar valores nesta revisão.
- **[HIPÓTESE]** Relacionamento estruturado e Opportunity/Quote ficam futuros; definir marco de entrada após F1, sem incluí-los silenciosamente.
- **[DEPENDÊNCIA DE ATIVAÇÃO]** Conferir capacidade Meta, teto comum realmente configurado e mapeamento do canal Castro Intelligence antes de elevar o objetivo para 500/dia. Integrar reservas e consumidores compartilhados; 2/90 e demais gates preservados. A abrangência de `audience=followup` foi aprovada provisoriamente na decisão 9, com implementação futura.

## 14. Respostas de Cristina e pendências operacionais

**[CONFIRMADO COM CRISTINA — 08/10]** Respostas encaminhadas pelo PO nesta sessão:

| Tema | Informação esclarecida |
|---|---|
| Datas | Inicial = entrega do orçamento; fechamento = pagamento; posteriores = dias de tentativas de retomada |
| Interesse | Inicial = reação ao orçamento após consulta médica; posteriores = reação nas ligações de follow-up |
| Quantidade | Geralmente três, depende do caso; orientação humana é continuar até recusa, sem teto rígido |
| Próximo contato | Idealmente combinado individualmente; sem fins de semana; terça/quarta/quinta como preferência |
| Responsabilidade | Trabalho colaborativo; Recepção mais em novos leads, Administrativo mais em pacientes com orçamento |
| Agenda | ProDoctor; confirmação 72h e lembrete 24h antes |
| Ciclo | Fecha com AGENDOU ou ENCERRADO; em branco/sem definição permanece aberto |
| Conversão | Pagamento confirmado no ProDoctor, não agendamento; DATA FECHAMENTO é o dia do pagamento |

Não repetir as oito perguntas originais. **Calendário (decisão 4):** regras de produto consolidadas em 18/10; Cristina/gestão configurará os dias, faixas e datas sem contato antes do uso. Dia útil anterior, última hora e contato único para coincidência após ajuste estão aprovados; revisões continuam humanas e prazos existentes preservados.

**Compromisso (decisão 5):** em 18/10, o PO confirmou que AGENDOU pode representar consulta ou procedimento/tratamento. Identificar humanamente o objetivo resolvido; isso não confirma pagamento nem cancela outras tarefas.

**Encerramento (decisão 6):** em 18/10, o PO aprovou recusa específica daquele orçamento/acompanhamento e recusa geral de novos contatos comerciais, com consultas e tarefas independentes preservadas. Catálogo amplo de motivos e reversão da preferência são detalhamento do desenho, sem reabrir os escopos.

**Continuidade (decisão 7):** em 18/10, o PO aprovou data combinada prioritária; sem combinação/retorno, operadora escolhe o próximo prazo permitido. Depois de três tentativas sem resposta, equipe revisa histórico/abordagem antes de continuar, preservando a mesma tarefa aberta e sem teto rígido. Não repetir essas perguntas. **Sinal de resposta (decisão 8):** aprovado em 18/10, com referência na última tentativa real ou criação antes da primeira, aviso preservado ao apenas adiar e nenhuma conclusão automática. **Automação futura (decisão 9):** em 18/10, o PO concordou provisoriamente com a abrangência de todo follow-up proativo automático no 2/90 e orçamento compartilhados. Solicitou objetivo de 500/dia e informou o uso de `varizemed-test` como canal da Castro Intelligence, pouco utilizado. A capacidade Meta/configuração ativa não foi consultada e nenhuma mudança operacional foi realizada; detalhes e dependências na seção 11.

A regra de Ganho está resolvida. Antes de futura integração financeira, detalhar entrada/parcelamento e conciliação por orçamento; isso não bloqueia o follow-up humano sem automação financeira. Datas comprimidas, sem ano/hora e autoria incompleta continuam impeditivos de uma importação automática, que não faz parte de F1.

## 15. Referências e limites

- [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md), [índice](README.md).
- [ADR 0010 — Modo Recepção](decisions/0010-pool-mode-recepcao.md): posse, atendimento compartilhado e Val.
- [ADR 0013 — Públicos da reabertura](decisions/0013-publicos-reabertura-lote.md) e [plano de reabertura](PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md): estados, tetos, consentimento e opt-out.
- [ADR 0005 — Templates e lote](decisions/0005-templates-meta-e-disparo-em-lote.md): estudo/riscos históricos; não prova infraestrutura/categoria vigente de template.
- [Plano de temperatura](PLANO_LEAD_TEMPERATURE.md), [classificador existente](../lead_temperature.py), [types](../frontend/src/types.ts), [normalização](../frontend/src/utils/normalization.ts).
- [Guia atual de qualificação e fechamento](product/GUIA_OPERADORES_QUALIFICACAO_FECHAMENTO.md): semântica operacional legada; não comprova o pagamento definido por Cristina.
- [Tags e privacidade na Varizemed](compliance/TAGS_E_PRIVACIDADE_VARIZEMED.md): organização, continuidade e pré-requisitos registrados para outra finalidade; não prova sua implementação.
- [Horário da Val](CX_HORARIO_COMERCIAL_DEV_IA.md) e [módulo atual](../business_hours.py): expediente usado pelo bot; menu de follow-up proposto não altera esses horários.
- CSV informado pelo PO: somente agregados/estrutura reproduzidos; conteúdo pessoal/clínico não versionado.
- Respostas de Cristina recebidas na sessão em 08/10/2026: fonte operacional das definições na seção 14, sem dados identificáveis de pacientes.

Não foram verificados estado atual de produção, outro worktree, publicação do agente, conteúdo da agenda externa ou aprovação Meta. ProDoctor é a fonte oficial informada, não uma integração/API validada. Nenhuma linha do CSV virou importação, evento financeiro confirmado ou automação.

## 16. Entrega F1 local — 18/10/2026

**Autorização do PO:** “pode implementar”. O código desta branch implementa
somente F1 humana. As hipóteses históricas deste plano não significam alteração
de todos os fluxos legados ou ativação de F2/F3.

Backend em `followup_routes.py`, `followup_access.py`, `followup_service.py` e
`followup_repository.py`; telas em `frontend/src/features/followup/` e integração
pequena no App. API autenticada em `/api/followup`, com tenant explícito, usuário
ativo, RBAC, acesso atual ao contato e à thread. Tarefas e atividades ficam nas
duas coleções previstas, sem novas entidades de paciente ou conversa.

Uso pela equipe: [guia das operadoras](product/GUIA_OPERADORAS_FOLLOWUP.md).

- Criar/editar/pegar/devolver/redistribuir/reagendar/concluir/cancelar tarefas;
  registrar tentativas na mesma tarefa, com versão e recibo idempotente.
  Tentativa, reagendamento, histórico e eventual conclusão complementar usam
  transação. Conflitos pedem atualização, sem sobrescrever a colega.
- Filas estáveis `reception`/`quotes`, renomeáveis como Recepção/Orçamentos;
  visões por prazo/estado e responsabilidade. Paginação limitada, cursor
  assinado e próxima ação acessível por contato.
- Calendário próprio em `system_settings/followup`, America/Sao_Paulo,
  inicialmente sem faixas confirmadas. Gestão configura dias úteis, faixas,
  feriados/recessos e horário preferido opcional. Sugestões 72h/24h exigem
  escolha humana; alterações não movem tarefas existentes. Agenda e referência
  do ProDoctor são informadas/corrigidas manualmente. Contato compartilhado só
  conclui as duas ações do mesmo compromisso nas exceções aprovadas, com uma
  tentativa originadora e referência na segunda conclusão.
- Resposta é sinal visual baseado na mensagem persistida após a âncora;
  leitura da mensagem não apaga o aviso. Não usa `last_inbound_at` como prova,
  não copia mensagens para atividades nem conclui a tarefa automaticamente.
- Contexto usa somente GET de conversa existente e mensagens autorizadas;
  não chama `conversation/open`, assume ou caminhos de envio. Fechar atendimento
  e o ciclo atual de retorno à Val continuam independentes das tarefas.
- Recusa específica cancela apenas aquela tarefa. Recusa comercial geral
  usa `commercial_contact_block` no contato, com versão, confirmação explícita
  e auditoria atômica existente. Reversão exige permissão própria e novo pedido
  específico do paciente; inbound genérico não remove o bloqueio. Os demais
  gates de LGPD/opt-out continuam separados.
- Reabertura pontual, scanner, worker e script de reabertura verificam a
  preferência; há releitura antes do HTTP. Templates manuais têm finalidade
  comercial/serviço declarada pela equipe, sem inferir por categoria Meta.
  O produtor legado `send_template_bulk.py` agora permanece em dry-run: seu
  `--yes` e transporte recusam envio porque ele não possui orçamento central.
  Não há exceção de serviço que crie um caminho proativo paralelo.

Permissões adicionadas: `gerenciar_followup`, `redistribuir_followup`,
`gerenciar_horarios_followup`, `registrar_recusa_comercial` e
`reativar_contato_comercial`. Redistribuição de equipe exige também visibilidade
ampla efetiva. Operadoras começam com tarefas no próprio escopo e registro de
recusa; supervisão/admin têm gestão conforme o perfil. A fila não amplia acesso
ao contato nem expõe thread coexistence de outra pessoa.

**Sem mensagens automáticas ou novos contadores.** Tetos ativos não foram
alterados. O objetivo de **500/dia** continua futuro, compartilhado e dependente
de Meta/integração; não se tornou configuração de 500 por lote ou por tenant.
Hubloc não recebeu habilitação de disparos. Qualificações/tags e conversão
legadas não foram migradas; pagamento/Ganho continua dependente do ProDoctor.

**Preparo de liberação:** `FEATURE_FOLLOWUP=false` por padrão. A ativação exige
merge com `develop`, conciliação com a frente de reabertura, publicação dos
índices/regras após autorização e configuração dos horários pela clínica. As
coleções novas são somente REST em produção e staging; o antigo wildcard de
staging não pode autorizá-las nem permitir adulteração de contatos, perfis ou
metadados globais de canal. Ver [processo de privacidade do follow-up](compliance/FOLLOWUP_PRIVACIDADE.md).
Nenhum push, deploy, importação ou acesso à produção foi realizado.

**Validação local:** Python da pasta principal; `npm.cmd ci` no frontend deste
worktree antes do build. Gates de compilação e simuladores de bot, CX, Recepção,
buffer e aviso de espera passaram. Simuladores novos usam código real com dados,
HTTP e Firestore em memória: núcleo (`sim_followup_flow.py`), API/RBAC/escopo
(`sim_followup_api.py`), preferência e produtores legados
(`sim_commercial_contact_policy.py`, `sim_followup_send_guards.py`) e calendário/
normalização no frontend (`node tools/sim_followup_frontend.mjs`). Build TypeScript
estrito + Vite validado. `node tools/sim_followup_lifecycle.mjs` acrescenta 25
verificações de respostas tardias, atualização, troca de contato e perda de
acesso executando TSX real com hooks/HTTP/timers simulados. Não houve teste visual em navegador autenticado, teste
no motor de regras do emulador, publicação de índices ou smoke com serviços
reais; esses checks pertencem ao preparo da liberação.
