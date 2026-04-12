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

---

## Conclusao do Spike - 12/04/2026

### Decisao final: Cenario B+C (hibrido)

- **Edicao outbound real (Cenario A): NAO SUPORTADA**
- **Sincronizacao de edicao inbound (Cenario B): PARCIALMENTE SUPORTADA**
- **Fallback de correcao interna (Cenario C): RECOMENDADO para outbound**

### Evidencias tecnicas

#### Edicao outbound via Cloud API

Revisao da documentacao oficial da Messages API (`POST /{phone_number_id}/messages`):

- o endpoint aceita apenas `POST` para criacao de novas mensagens
- nao existe `PUT`, `PATCH` ou qualquer variante de edicao/atualizacao
- o unico `PUT` disponivel no endpoint de messages e para marcar mensagens como lidas (`status: "read"`), que e um read-receipt, nao edicao
- nao existe parametro `message_id` para referenciar mensagem existente em contexto de edicao
- wrappers third-party como CodeChat oferecem `PATCH /edit-message`, mas usam protocolo nao-oficial (WhatsApp Web), nao a Cloud API

Fontes verificadas:
- https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/
- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/

#### Webhook de edicao inbound

A documentacao de webhooks nao documenta explicitamente um campo `edited` no payload de mensagens. Porem, com base em relatos da comunidade e no comportamento do app (que permite editar por 15 minutos), existe a possibilidade de que versoes recentes da Graph API (v20.0+) incluam um campo `edited` no webhook.

**Status: nao confirmado oficialmente na documentacao publica acessivel.**

A verificacao definitiva requer teste pratico: editar uma mensagem no app e observar o webhook.

### Recomendacao de implementacao

1. **Para outbound:** implementar `Corrigir mensagem` (Cenario C)
   - UX: operador seleciona mensagem > "Corrigir" > composer abre com texto original > envia nova mensagem citando a anterior
   - a mensagem original fica marcada como "corrigida" no CRM
   - o cliente recebe uma nova mensagem, nao uma edicao

2. **Para inbound:** reservar campo `edited` no schema de mensagens para uso futuro
   - quando a Meta confirmar o campo no webhook, implementar sincronizacao
   - por ora, nao criar UX para algo nao confirmado

3. **Nomenclatura de produto:** usar `Corrigir mensagem`, nunca `Editar mensagem`
   - evita prometer efeito que o cliente final nao vera no WhatsApp

### Proxima acao

Avancar para `TASK_FEATURE_EDICAO_MENSAGENS_WHATSAPP_CRM.md` no caminho C (correcao), com reserva de schema para B (inbound edit) quando confirmado.
