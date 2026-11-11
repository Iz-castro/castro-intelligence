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

Simulador: 175 verificações (inclui a série A: carimbo, agenda, gate, claim, envio com botões, toque no gate real,
worker, uso mensal e API).
