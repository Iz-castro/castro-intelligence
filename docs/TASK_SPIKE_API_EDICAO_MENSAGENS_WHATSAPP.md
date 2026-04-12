# Task - Spike API edicao de mensagens WhatsApp

## Data

12/04/2026

## Objetivo

Validar tecnicamente se o stack atual do CRM com WhatsApp Business Cloud API permite suportar edicao real de mensagens, e definir com seguranca qual caminho de implementacao seguir.

## Contexto

O app do WhatsApp permite editar mensagens enviadas por ate 15 minutos.

No CRM, hoje:

- nao existe acao de `Editar mensagem` no menu da bolha;
- nao existe endpoint de backend para edicao;
- nao existe schema de mensagem com trilha de edicao;
- nao ha confirmacao tecnica de que a Cloud API usada pelo projeto suporta edicao real de outbound.

Esta task existe para responder a pergunta tecnica antes de comecar a feature final.

## Perguntas que o spike precisa responder

- [ ] A Cloud API permite editar uma mensagem outbound ja enviada?
- [ ] Se permitir, qual endpoint, payload, restricoes e erros envolvidos?
- [ ] Existe janela de tempo oficial para a API, e ela bate com os 15 minutos do app?
- [ ] Existe limite de quantidade de edicoes por mensagem?
- [ ] O webhook envia evento quando uma mensagem inbound do cliente e editada no app?
- [ ] Se houver webhook de edicao, qual o payload exato?
- [ ] Se a API nao suportar edicao real outbound, qual fallback entrega melhor UX no CRM?

## Resultado esperado

Ao final do spike, precisamos sair com uma decisao tecnica unica:

### Cenario A

`edicao real outbound suportada`

### Cenario B

`somente sincronizacao de edicao inbound suportada`

### Cenario C

`sem suporte util na API; usar fallback de correcao`

## Escopo do spike

### Inclui

- leitura da documentacao oficial atual da Meta;
- experimentos controlados com numero de teste ou ambiente seguro;
- captura de requests, responses, webhooks e erros;
- documento de conclusao com recomendacao objetiva.

### Nao inclui

- entrega final da feature no frontend;
- alteracao permanente de schema;
- rollout para producao;
- mudanca definitiva de UX no CRM.

## Plano de execucao

## Etapa 1 - Revisao de documentacao oficial

- [ ] Revisar a documentacao oficial da Message API
- [ ] Revisar a documentacao oficial de webhooks de mensagens
- [ ] Revisar changelog oficial da plataforma WhatsApp
- [ ] Procurar referencias oficiais para:
  - edit message
  - edited message webhook
  - revoke message
  - message update
  - outbound message mutation

### Evidencia minima

- [ ] links oficiais salvos
- [ ] resumo das regras confirmadas
- [ ] lista das lacunas ainda nao confirmadas

## Etapa 2 - Experimento de outbound

- [ ] Enviar mensagem de texto outbound via fluxo atual do CRM ou chamada direta da Cloud API
- [ ] Registrar:
  - `wa_message_id`
  - `phone_number_id`
  - horario de envio
- [ ] Tentar identificar fluxo oficial de edicao dessa mensagem
- [ ] Testar respostas da API:
  - sucesso
  - erro funcional
  - erro de permissao
  - erro de janela expirada
- [ ] Verificar se ha reflexo real no WhatsApp do destinatario

### Evidencia minima

- [ ] request usado
- [ ] response bruto
- [ ] print ou descricao do resultado no WhatsApp real

## Etapa 3 - Experimento de inbound

- [ ] Enviar mensagem de teste do celular para o numero integrado
- [ ] Editar a mensagem no app do WhatsApp dentro da janela suportada
- [ ] Capturar o webhook recebido pelo CRM
- [ ] Validar se houve:
  - novo evento
  - atualizacao da mesma mensagem
  - ausencia total de evento

### Evidencia minima

- [ ] payload bruto do webhook
- [ ] identificacao do tipo de evento
- [ ] impacto real no banco/local state

## Etapa 4 - Mapeamento de impacto no CRM

- [ ] Listar quais arquivos do CRM seriam afetados em cada cenario
- [ ] Estimar complexidade de implementacao:
  - baixa
  - media
  - alta
- [ ] Identificar riscos de produto e auditoria

### Areas provaveis

- `main.py`
- `webhook.py`
- `database_firestore.py`
- `frontend/src/App.tsx`
- `frontend/src/context/CrmContext.tsx`
- `frontend/src/types.ts`

## Etapa 5 - Decisao final

- [ ] Consolidar conclusao tecnica do spike
- [ ] Recomendar explicitamente um dos 3 cenarios
- [ ] Definir a nomenclatura correta de produto:
  - `Editar mensagem`
  - `Corrigir mensagem`
  - `Sincronizar edicao do cliente`

## Criterios de aceite

- [ ] a task responde com clareza se ha ou nao suporte real para edicao outbound
- [ ] ha evidencias tecnicas suficientes para sustentar a conclusao
- [ ] a recomendacao final evita prometer algo que o WhatsApp do cliente nao reflita
- [ ] a task final da feature pode ser refinada com base nessa conclusao

## Riscos do spike

- a documentacao publica da Meta pode estar incompleta ou inconsistente;
- o recurso pode existir no app, mas nao estar disponivel na Cloud API;
- o webhook pode cobrir apenas mensagens editadas pelo usuario final;
- a plataforma pode mudar comportamento por versao da Graph API.

## Artefatos esperados ao final

- [ ] nota final com conclusao tecnica
- [ ] exemplos de payload ou erro
- [ ] recomendacao de UX
- [ ] decisao `A`, `B` ou `C`

## Dependencias

- acesso a numero de teste ou numero seguro para experimento;
- token valido da Meta;
- ambiente com webhook observavel;
- opcionalmente logs do Cloud Run durante o teste.

## Proxima task depois do spike

Se o resultado for positivo ou parcialmente positivo, avancar para:

- `TASK_FEATURE_EDICAO_MENSAGENS_WHATSAPP_CRM.md`

Se o resultado for negativo para edicao real, refinar a feature para:

- `Corrigir mensagem`
- ou `Sincronizar edicao inbound`
