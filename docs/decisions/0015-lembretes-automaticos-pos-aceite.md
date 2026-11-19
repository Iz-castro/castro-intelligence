# ADR 0015 — Lembretes automáticos após o aceite

Data: 2026-11-11. Status: aceito pelo PO nesta sessão; implementação local, desligada por padrão.

O lead aceitou a política, recebeu resposta da Val e ficou em silêncio. O Castro Chat agenda até três textos
editáveis: 20 minutos e quatro horas após a resposta; 23h40 após a última mensagem do lead.

## Decisões

- Somente CX com LGPD local resolvida. Pendente, recusado, revogado, coexistence, backup e atendimento humano ficam fora.
- Classificador textual puro compartilhado com medidor. Link atual, cortesia, falha e handoff não armam.
  Nova mensagem e resposta sem link podem armar, independentemente de desfecho antigo.
- Entrada capturada antes do turno e validada em transação após envio confirmado. Turno antigo não sobrescreve
  entrada posterior. Etapas estáveis, claim antes do POST e nenhuma repetição em resultado incerto.
- `PARAR LEMBRETES` persiste preferência própria; `ATIVAR LEMBRETES` desfaz. Inbound comum não desfaz a parada.
- Env geral, modo comercial por tenant (`off`, `dry_run`, `on`) e toggle da clínica. Mudança de modo ou religamento
  invalida agendas antigas. Primeiro simulação no tenant de teste; operação em produção posterior pelo PO.
- Sem teto comercial diário/semanal adicional; cada etapa uma vez por ciclo. Limite técnico de 30/tick e 150s.
- Tela nesta entrega e API própria com RBAC e versão contra formulário antigo. Save geral/upload de som preservam
  campos. Textos inicialmente vazios; nenhum texto da clínica no código. Sem dependência ou coleção nova.
- O lembrete preserva recência, não reabre atendimento nem simula atenção humana. Lote pertence a outra frente:
  não usa seus contadores/orçamento. Uso mensal próprio por série/etapa mede envio aceito, não entrega faturável.

## Validação e limites

Simulador `tools/sim_bot_reminders.py` e gates do `CLAUDE.md`. Medidor exclusivamente de leitura e saída agregada.
A regra textual pode perder perguntas ou classificar cortesias desconhecidas; a medição histórica é estimativa.
Evolução: sinal explícito por turno da Val. Erro síncrono 131047 encerra agenda; cancelamento por status assíncrono
fica para evolução. Há corrida residual entre checagem e POST externo. Sem validação em produção.

Decisões detalhadas: resposta de 11/11 em `docs/HANDOFF_MENSAGENS_AUTOMATICAS.md`.

## Emenda — 2026-11-11 (tarde): série A, sem resposta ao aviso da LGPD

Pedido do PO no mesmo dia, depois do primeiro envio real: o mesmo sistema para o lead que recebeu o aviso da LGPD e
não respondeu. Reintroduz a série A do desenho original (handoff, seções 4.3 e 4.5), com os mesmos horários. A série
pós-aceite descrita acima passa a se chamar série B.

- Arma no turno `lgpd_notice` (o aviso e o "não entendi"). A série fica na thread (`bot_reminder_series`, `A` ou `B`;
  thread carimbada antes da emenda, sem o campo, é `B`). Troca de série no mesmo ciclo zera as etapas feitas.
- Gate da série A: `bot_states.lgpd_status == "awaiting"` sem `lgpd_consent`, contato sem recusa e sem
  `human_active`; consentimento já resolvido barra (`ja_aceitou`); sem doc de estado não envia. Quem recusou nunca
  recebe, em nenhuma série. Os demais gates são os da série B (canal standard, sem dono, `PARAR LEMBRETES`, recusa
  comercial, revogação, thread aberta etc.).
- Textos próprios (`bot_reminder_lgpd_text_1..3`, até 1.000 caracteres, sem o link de agendamento), mesmo toggle e
  mesmos intervalos; série sem texto fica desligada. Na tela, segundo grupo: "Sem resposta ao aviso da política de
  privacidade".
- Envio interativo com os botões do próprio aviso (`lgpd_aceitar` "Sim" e `lgpd_recusar` "Não"): o toque entra no
  gate que já existe. A instrução de parada vai no rodapé da mensagem (51 dos 60 caracteres). O texto não leva nome
  nem dado do paciente, que ainda não aceitou a política.
- Auditoria (`serie=A`), uso mensal (`bot_reminders_sent.A.<etapa>`) e o campo `automation_series` da mensagem
  separam as séries.
- Limite conhecido (R16 do handoff): depois do aceite, o toque em "Não" de um aviso ou lembrete antigo chega à Val
  como texto e não registra recusa. Já acontecia com o aviso; a série A acrescenta até três mensagens com esse botão.
  **Resolvido em 2026-11-13** (emenda do ADR 0009): o toque em "Não" depois do aceite vale como recusa e o toque
  repetido em "Sim" (até 5 minutos depois do aceite) é ignorado. Efeito nos lembretes: a recusa limpa a agenda
  (turno `lgpd_refusal`) e barra as duas séries pelo contato; o "Sim" repetido é mensagem nova sem resposta do
  agente, então encerra o ciclo e a série B só rearma no turno seguinte da Val.

Simulador: 175 verificações (inclui a série A: carimbo, agenda, gate, claim, envio com botões, toque no gate real,
worker, uso mensal e API).

## Emenda — 2026-11-19: sem rodapé de parada; último lembrete com botões

Decisão da clínica, repassada pelo PO: nenhum lembrete leva mais o rodapé "Para desativar os lembretes, envie PARAR
LEMBRETES.". O último lembrete da série B (fechamento, 23h40 depois da última mensagem do lead) passa a sair como
mensagem interativa com os botões **Continuar conversa** (`lembrete_continuar`) e **Encerrar conversa**
(`lembrete_encerrar`), e os textos da série B aceitam `[Nome]` ou `{Nome}` nas três etapas: primeiro nome do perfil
do WhatsApp (`whatsapp_profile_name`; se não tiver letra, o nome declarado), a mesma prioridade do recibo de protocolo.
Sem nome, o token sai sem deixar pontuação solta: "Olá, [Nome]!" e "Olá [Nome]!" viram "Olá!", e o vocativo que abre a
frase sai com a pontuação dele ("[Nome], tudo bem?" vira "Tudo bem?"). Se o nome fizer o último lembrete passar de
1.024 caracteres (limite da mensagem com botões), ele sai sem o nome. Etapas 1 e 2 da série B seguem como texto simples.

- Os toques valem como o Continuar/Encerrar da reabertura (`webhook._handle_reopen_button`, `origin="lembrete"`):
  Continuar devolve o lead à Val com o turno sintético de retomada (`origem=retomada_lote`; se a Val não responder,
  o lead vai para a equipe); Encerrar fecha o atendimento como `fechado_cliente`, envia o recibo de protocolo e grava
  `reopen_opt_out` (a conversa não é reaberta, nem em lote nem pela equipe, até o paciente mandar mensagem nova, D4).
  O toque nunca vira texto para a Val; reentrega da Meta (`was_dup`) não reprocessa.
- Diferenças da origem lembrete (revisão de 19/11): mensagem de sistema própria; auditoria `BOT_REMINDER_RESPONSE`
  com `contact_id` (o `conversation_id` embute o telefone); logs com a tag `[REMINDER BTN]`, sem o `conversation_id`
  e só com o tipo da exceção (as linhas `[REOPEN BTN]` medem o lote); `reopen_response_origin` na thread; e o
  Encerrar de lead ainda na fase de bot fecha com `keep_bot_cycle` — sem "Atendimento devolvido ao assistente
  virtual." e sem zerar `bot_outcome`/`bot_released_at`, que a proteção P5 do público Bot da reabertura lê (o lead
  nunca saiu da Val). Lead já com a equipe fecha como sempre.
- Follow-up: toque em botão interativo (`interactive_reply`, inclusive `lembrete_*`) não conta como resposta do
  paciente.
- Série A não muda: os três lembretes seguem com os botões Sim/Não do aviso, agora sem rodapé, e sem nome — o
  salvamento pela API e a tela recusam `[Nome]`/`{Nome}` nos textos da série A (o paciente ainda não aceitou a
  política). No envio, um token gravado antes dessa trava é retirado (nunca vira nome), sem parar os lembretes do tenant.
- `PARAR LEMBRETES` / `ATIVAR LEMBRETES` continuam funcionando, só não são anunciados.
- Implantar antes de gravar o texto novo: a revisão anterior enviaria `[Nome]` literal e o rodapé.
- **Rollback para revisão anterior a esta só depois de tirar `[Nome]` dos textos da série B** (na tela) e deixar o
  3º texto legível sem botões: a revisão antiga envia `[Nome]` literal com o rodapé e o último lembrete como texto
  simples. Toques em botões de lembretes já entregues chegam à Val como texto (`lembrete_continuar` /
  `lembrete_encerrar`): sem fechamento, protocolo ou opt-out até voltar a esta revisão.

Ficam como estão, iguais aos botões do template de reabertura (pontos para o PO, não defeitos desta mudança): o toque
vale pelo estado ATUAL do lead (um Encerrar tocado dias depois fecha o atendimento em curso); Continuar depois de
Encerrar não desfaz o `reopen_opt_out` (só mensagem nova desfaz); o turno sintético do Continuar não passa pelo
buffer; um turno da Val já em andamento quando o paciente toca Encerrar não é descartado; e o toque, como qualquer
mensagem nova, desfaz a recusa comercial (emenda de 13/11 ao ADR 0009).

Simuladores: `sim_bot_reminders.py` (231), `sim_buffer_flow.py` (122, roteamento do toque), `sim_reception_flow.py`
(370, Continuar e Encerrar pelo lembrete, `keep_bot_cycle` até o fechamento real, log do helper) e
`sim_followup_flow.py` (82). Duas rodadas de revisão adversarial (19/11) antes do deploy.
