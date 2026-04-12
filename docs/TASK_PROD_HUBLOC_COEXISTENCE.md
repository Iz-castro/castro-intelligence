# Task - Rollout Prod com numero Hubloc e Coexistence em 2 fases

## Data

12/04/2026

## Objetivo

Colocar o CRM em producao sem depender da finalizacao da analise da Meta, usando primeiro um unico numero padrao na Cloud API e deixando a liberacao do `coexistence` para uma segunda fase, quando as verificacoes estiverem prontas.

## Decisao recomendada

Seguir em 2 fases:

1. Fase 1: producao com apenas o canal `standard` ativo.
2. Fase 2: liberar `coexistence` para operadores com mais numeros, somente apos os ajustes de ownership e as verificacoes finais.

## Estado atual validado em 12/04/2026

- O canal padrao de producao atual esta configurado no Cloud Run com:
  - `WHATSAPP_PHONE_NUMBER_ID=1070927076104221`
  - `WHATSAPP_WABA_ID=1633469507697155`
  - numero exibido: `+55 31 9934-6195`
- O diagnostico via `check_whatsapp_coexistence.py` retornou para o canal padrao:
  - `status=CONNECTED`
  - `code_verification_status=VERIFIED`
  - `platform_type=CLOUD_API`
  - `quality_rating=GREEN`
- Os IDs antigos citados nas notas de 05/04/2026 nao responderam com o token atual de producao.
- Portanto, antes da troca para o numero da Hubloc, o `phone_number_id` e o `waba_id` exatos desse numero precisam ser validados novamente.

## Riscos encontrados

### 1. Numero da Hubloc ainda nao validado no ambiente atual

Nao ha confirmacao atual de que o numero que queremos promover para o canal padrao e o mesmo dos registros antigos de 05/04/2026.

Impacto:
- trocar as env vars sem validar os IDs pode derrubar envio e/ou recebimento no numero principal.

### 2. Signup de coexistence exposto cedo demais

Hoje o frontend exibe `WhatsApp Coexistence` para qualquer usuario autenticado e o backend dos endpoints de signup nao faz bloqueio por role.

Impacto:
- um operador pode iniciar o fluxo antes da fase correta de rollout;
- isso aumenta risco operacional durante a entrada em producao.

### 3. Ownership do coexistence incompleto

No fluxo atual, o frontend envia apenas `{ code }` no exchange. O backend aceita `owner_user_id`, mas ele nao esta sendo enviado no fluxo padrao.

Impacto:
- o canal pode nascer sem `owner_user_id`;
- a visibilidade por operador pode ficar inconsistente;
- a auto-atribuicao de contatos de `coexistence` pode nao funcionar como esperado.

## Plano de execucao

## Fase 1 - Entrar em prod com um unico numero padrao

### Escopo

- usar somente o canal `standard`;
- trocar o numero padrao da Cloud API para o numero da Hubloc, se os IDs forem validados;
- nao liberar `coexistence` operacionalmente nesta fase.

### Tasks

- [ ] Confirmar com a Meta ou via diagnostico os IDs exatos do numero da Hubloc:
  - `WHATSAPP_PHONE_NUMBER_ID`
  - `WHATSAPP_WABA_ID`
  - `display_phone_number`
- [ ] Rodar `python check_whatsapp_coexistence.py --token-source gcloud-secret --gcloud-project project-26fb9c99-8ee9-4179-aef --phone-id <PHONE_ID> --waba-id <WABA_ID> --json`
- [ ] Confirmar que o numero alvo responde com:
  - `status=CONNECTED`
  - `code_verification_status=VERIFIED`
  - `platform_type=CLOUD_API`
- [ ] Atualizar o Cloud Run para apontar o canal `standard` para o numero da Hubloc:
  - `WHATSAPP_PHONE_NUMBER_ID`
  - `WHATSAPP_WABA_ID`
  - manter `WHATSAPP_TOKEN` valido no Secret Manager
- [ ] Reiniciar a revision para forcar reload das env vars e secrets
- [ ] Validar no startup que o bootstrap sincronizou o canal default com as env vars
- [ ] Fazer smoke test real:
  - envio de texto
  - envio de midia
  - webhook inbound
  - resposta dentro da janela de 24h
- [ ] Esconder temporariamente o fluxo de `coexistence` do usuario final:
  - frontend
  - endpoints ou gate por role/feature flag

### Criterios de aceite

- [ ] o CRM envia e recebe normalmente no numero padrao da Hubloc
- [ ] o canal `standard` continua sendo a fonte de verdade do envio
- [ ] operadores usam o sistema sem acesso operacional ao signup de `coexistence`
- [ ] nao ha regressao no webhook, no bot e no fluxo normal de atendimento

## Fase 2 - Liberar coexistence depois

### Escopo

- habilitar operadores que possuem mais numeros a conectar canais proprios;
- manter o numero principal da empresa como canal `standard`;
- ativar `coexistence` somente depois que as verificacoes estiverem prontas.

### Tasks

- [ ] Ajustar o frontend do signup para enviar tambem:
  - `owner_user_id`
  - opcionalmente `label`
  - opcionalmente `default_department_id`
- [ ] Garantir no backend que um signup de `coexistence` salve corretamente:
  - `channel_type=coexistence`
  - `owner_user_id`
  - `owner_firebase_uid`
- [ ] Restringir o uso do signup na fase inicial:
  - admin/supervisor; ou
  - operadores explicitamente autorizados
- [ ] Testar visibilidade:
  - operador comum ve apenas o proprio canal coexistence
  - admin/supervisor ve todos
- [ ] Testar auto-atribuicao:
  - mensagem inbound do numero coexistence cai direto para o dono do canal
- [ ] Testar envio outbound pelo canal correto do contato
- [ ] Testar `history`, `smb_message_echoes` e `account_update`
- [ ] Validar fluxo de offboarding/reconexao de um numero coexistence

### Criterios de aceite

- [ ] cada canal coexistence nasce com dono definido
- [ ] contatos de coexistence sao auto-atribuidos corretamente
- [ ] operadores nao enxergam coexistence de outros operadores
- [ ] envio e recebimento continuam roteando pelo `channel_id` correto

## Ajustes tecnicos necessarios antes da Fase 2

- [ ] Remover a exposicao prematura de `WhatsApp Coexistence` para todos os usuarios
- [ ] Fechar ou condicionar os endpoints:
  - `GET /api/admin/embedded-signup/config`
  - `POST /api/admin/embedded-signup/exchange`
- [ ] Corrigir o payload do frontend para nao enviar apenas `{ code }`
- [ ] Validar se o canal criado no exchange esta recebendo `owner_user_id`

## Referencias no codigo

- `channel_service.py`
- `main.py`
- `webhook.py`
- `database_firestore.py`
- `frontend/src/App.tsx`
- `check_whatsapp_coexistence.py`

## Resultado esperado

Entrar em producao agora com um numero principal estavel e controlado, sem ficar bloqueado pela fase final da analise da Meta, e abrir o `coexistence` em seguida de forma segura, com ownership, visibilidade e auto-atribuicao funcionando de ponta a ponta.
