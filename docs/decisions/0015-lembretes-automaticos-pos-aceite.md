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
