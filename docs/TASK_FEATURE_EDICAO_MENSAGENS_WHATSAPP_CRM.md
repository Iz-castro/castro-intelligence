# Task - Feature de edicao de mensagens WhatsApp no CRM

## Data

12/04/2026

## Pergunta de produto

No WhatsApp, o usuario consegue editar uma mensagem pelo menu da bolha.

Queremos analisar se faz sentido implementar comportamento equivalente no chat do CRM.

## Resposta curta da analise

- No app do WhatsApp, a edicao de mensagens existe oficialmente.
- A fonte oficial que foi validada informa que a mensagem pode ser editada por ate 15 minutos apos o envio.
- Nao encontrei fonte oficial confirmando a regra "so pode editar uma vez".
- No nosso CRM, hoje nao existe suporte de UI, backend, schema ou webhook para tratar edicao de mensagens.
- A viabilidade da feature depende de um `spike` tecnico para confirmar se a Cloud API permite edicao real de mensagem outbound ja enviada, ou se isso precisara virar uma experiencia alternativa dentro do CRM.

## Fonte oficial validada

- WhatsApp / Meta Newsroom: a feature de editar mensagem existe no produto e funciona por ate 15 minutos apos o envio:
  - https://about.fb.com/news/2023/05/edit-whatsapp-messages/
- Documentacao oficial da Message API da Meta, usada hoje pelo CRM para envio:
  - https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
- Documentacao oficial de webhooks da Meta para WhatsApp:
  - https://developers.facebook.com/docs/whatsapp/webhooks/reference/messages

## Observacoes importantes

### 1. Regra de produto confirmada

O material oficial validado diz:

- o WhatsApp permite editar mensagens enviadas por ate 15 minutos;
- a mensagem aparece como editada;
- nao e exibido historico de edicoes no app.

### 2. Regra "editar so uma vez" nao foi confirmada

Nao encontrei na fonte oficial usada uma afirmacao clara de que a mensagem so pode ser editada uma unica vez.

Por isso, a premissa correta neste momento e:

- janela de 15 minutos: confirmada;
- limite de "uma unica edicao": nao confirmado.

### 3. A Cloud API ainda precisa de validacao pratica

Na documentacao publica usada na analise:

- existe a Message API oficial para enviar novas mensagens;
- existe referencia oficial de webhooks de mensagens;
- nao foi encontrado, de forma clara e confiavel, um endpoint publico confirmado para editar uma mensagem outbound existente do negocio;
- durante a analise, referencias detalhadas de `messages/edit` na navegacao publica apareceram inconsistentes.

Interpretacao pratica:

- a feature do app existe;
- a capacidade equivalente na API usada pelo CRM ainda precisa ser provada tecnicamente antes de virar compromisso de produto.

## Estado atual do CRM

### UI atual

No menu da bolha da mensagem, hoje temos apenas:

- `Responder`
- `Copiar`

Ponto atual no frontend:

- `frontend/src/App.tsx`

### Backend atual

O envio de texto no CRM hoje faz apenas criacao de mensagem nova via:

- `POST /api/wa/send`
- payload para `POST /{phone_id}/messages`

Ponto atual no backend:

- `main.py`

### Modelo de dados atual

As mensagens salvas no Firestore hoje nao possuem campos de edicao, como:

- `is_edited`
- `edited_at`
- `edited_by`
- `edit_count`
- `original_content`
- `edit_source`

Pontos atuais:

- `database_firestore.py`
- `frontend/src/types.ts`
- `docs/DOCUMENTACAO_SISTEMA.md`

## Conclusao de viabilidade

## Cenario A - Meta suporta edicao real via API

Se o `spike` provar que a Cloud API permite editar uma mensagem outbound existente, a feature e viavel como edicao real end-to-end:

- editar no CRM;
- refletir no WhatsApp do destinatario;
- atualizar o historico local;
- marcar a mensagem como editada.

## Cenario B - Meta NAO suporta edicao real via API

Se a Cloud API nao suportar edicao outbound real, ainda existem duas alternativas:

### Opcao B1 - nao implementar "Editar", so "Corrigir"

UX:

- operador clica no menu da bolha;
- escolhe `Corrigir mensagem`;
- CRM abre composer com o texto anterior;
- ao confirmar, o sistema envia uma nova mensagem, opcionalmente respondendo/citando a anterior;
- a mensagem antiga fica marcada no CRM como "corrigida por nova mensagem", mas nao e alterada no WhatsApp do cliente.

### Opcao B2 - implementar apenas sincronizacao de edicoes inbound

Se a Meta entregar webhook de mensagem editada do cliente, o CRM pode:

- detectar a edicao feita pelo cliente no app;
- atualizar o texto da mensagem inbound no historico local;
- marcar visualmente como `editada`.

## Recomendacao

Nao prometer a feature como "editar mensagem no WhatsApp" antes do `spike`.

A recomendacao e dividir a task em 2 etapas:

1. `Spike tecnico` para validar suporte real da Meta.
2. `Implementacao` somente no caminho comprovado.

## Plano de implementacao

## Fase 0 - Spike tecnico obrigatorio

### Objetivo

Descobrir qual destes cenarios e verdadeiro no stack atual:

- `A`: existe edicao real outbound via Cloud API;
- `B`: nao existe edicao outbound, mas pode existir webhook de edicao inbound;
- `C`: nao existe suporte util na API e devemos fazer uma UX alternativa de correcao.

### Tasks

- [ ] Revisar a documentacao oficial atual da Meta focando em:
  - Message API
  - Webhooks de mensagens
  - changelog da plataforma
- [ ] Fazer experimento controlado em ambiente de teste:
  - enviar mensagem outbound via Cloud API
  - tentar identificar endpoint, parametro ou fluxo oficial de edicao
  - verificar se existe retorno de webhook quando uma mensagem inbound e editada no app
- [ ] Capturar payloads reais, erros e limitacoes
- [ ] Registrar a decisao tecnica final:
  - `editar real suportado`
  - `somente inbound suportado`
  - `sem suporte real, usar fallback`

### Criterio de aceite

- [ ] sair do spike com decisao `go/no-go` para edicao real
- [ ] documentar evidencias tecnicas e payloads

## Fase 1 - Preparacao de modelo de dados

Esta fase so deve avancar depois do spike.

### Campos sugeridos para `wa_messages`

- [ ] `is_edited: bool`
- [ ] `edited_at: datetime | null`
- [ ] `edited_by_operator_id: int | null`
- [ ] `edit_source: \"crm\" | \"whatsapp_user\" | \"system\" | \"unknown\"`
- [ ] `edit_count: int`
- [ ] `original_content: str`
- [ ] `last_edited_content: str`
- [ ] `supersedes_message_id: int | null`
- [ ] `superseded_by_message_id: int | null`
- [ ] `edit_window_expires_at: datetime | null`

### Observacao

No cenario de fallback, nem todos os campos acima serao necessarios. O schema final deve ser enxuto e guiado pela decisao do spike.

## Fase 2 - Backend

## Se o resultado for Cenario A - edicao real outbound

- [ ] criar endpoint dedicado, por exemplo:
  - `POST /api/wa/edit-message`
- [ ] validar permissao:
  - apenas operador responsavel, admin ou supervisor
- [ ] validar elegibilidade:
  - somente mensagens `outbound`
  - somente `msg_type=text`
  - dentro da janela suportada pela Meta
  - somente mensagens do proprio contato
- [ ] chamar a API oficial da Meta com o fluxo correto validado no spike
- [ ] atualizar a mensagem local sem perder trilha de auditoria
- [ ] registrar `audit_log`

## Se o resultado for Cenario B - somente inbound editado

- [ ] atualizar `webhook.py` para reconhecer evento/payload de edicao
- [ ] localizar a mensagem pelo `wa_message_id`
- [ ] atualizar `content`, `is_edited`, `edited_at`, `edit_source`
- [ ] notificar frontend em tempo real

## Se o resultado for Cenario C - fallback interno

- [x] criar endpoint de correcao interna, por exemplo:
  - `POST /api/wa/correct-message`
- [x] marcar a mensagem original como `superseded`
- [x] enviar uma nova mensagem citando ou substituindo semanticamente a anterior
- [x] manter trilha clara no banco e no audit log

## Fase 3 - Frontend

### Menu da bolha

- [x] adicionar acao contextual:
  - `Corrigir` (cenario C confirmado)
- [x] manter `Responder` e `Copiar`

### Composer

- [x] criar modo de edicao/correcao
- [x] exibir estado visual claro:
  - "Editando mensagem"
  - "Corrigindo mensagem"
- [x] permitir cancelar
- [x] reaproveitar texto original no input

### Timeline do chat

- [x] exibir badge visual:
  - `corrigida`
- [ ] mostrar tooltip ou texto auxiliar quando houver alteracao
- [ ] decidir se o CRM mostra ou nao o conteudo original

### Regras de UX recomendadas

- [x] permitir apenas em mensagem de texto outbound
- [x] esconder a opcao para audio, imagem, video, documento, template e system
- [ ] esconder a opcao quando a janela expirar
- [x] esconder para mensagens de outro operador, exceto admin/supervisor

## Fase 4 - Regras de negocio

- [ ] definir se a edicao pode ocorrer apenas dentro de uma janela local de tempo
- [ ] definir se a politica local sera:
  - varias edicoes dentro da janela; ou
  - uma unica edicao dentro da janela
- [ ] alinhar a regra local somente depois de confirmar a regra oficial da Meta
- [ ] definir como a auditoria deve registrar:
  - valor anterior
  - valor novo
  - usuario
  - data/hora

## Fase 5 - Observabilidade e auditoria

- [ ] adicionar evento de auditoria:
  - `WA_MESSAGE_EDIT`
  - `WA_MESSAGE_CORRECT`
  - `WA_MESSAGE_EDIT_INBOUND_SYNC`
- [ ] logar falhas da API
- [ ] logar expiracao de janela
- [ ] logar tentativas nao autorizadas

## Fase 6 - Testes

### Backend

- [ ] editar mensagem valida dentro da janela
- [ ] bloquear edicao fora da janela
- [ ] bloquear edicao de mensagem inbound
- [ ] bloquear edicao de midia/template/system
- [ ] bloquear edicao de mensagem de outro operador

### Frontend

- [ ] menu da bolha mostra a acao certa no contexto certo
- [ ] composer entra e sai do modo de edicao
- [ ] badge visual aparece corretamente
- [ ] lista e detalhe atualizam sem duplicar mensagens

### Integracao

- [ ] validar reflexo no WhatsApp real, se o cenario A for confirmado
- [ ] validar webhook de mensagem editada do cliente, se o cenario B for confirmado
- [ ] validar fallback de correcao, se o cenario C for escolhido

## Decisao de produto recomendada

### Se a Meta suportar edicao real outbound

Implementar a feature completa.

### Se a Meta NAO suportar edicao real outbound

Nao chamar a feature de `Editar mensagem` no CRM.

Preferir `Corrigir mensagem` ou `Enviar correcao`, para nao prometer um efeito que o cliente final nao vera no WhatsApp.

## Riscos

- risco de prometer "edicao" e entregar apenas nova mensagem;
- risco de perder rastreabilidade se sobrescrever `content` sem historico;
- risco de incoerencia entre CRM e WhatsApp do cliente;
- risco de regra local divergir da regra oficial da Meta;
- risco de atualizar mensagem antiga sem impacto real no canal externo.

## Criterios de aceite da feature

### Criterio minimo

- [x] ha uma decisao tecnica formal apos o spike
- [x] o CRM nao usa linguagem enganosa sobre a capacidade real

### Criterio ideal

- [ ] o operador entende claramente quando esta editando versus corrigindo
- [ ] o historico no CRM preserva auditoria
- [ ] o comportamento do CRM fica coerente com o comportamento real do WhatsApp

## Arquivos que provavelmente serao alterados

- `frontend/src/App.tsx`
- `frontend/src/context/CrmContext.tsx`
- `frontend/src/types.ts`
- `frontend/src/utils/formatting.ts`
- `database_firestore.py`
- `main.py`
- `webhook.py`
- `docs/DOCUMENTACAO_SISTEMA.md`

## Proxima acao sugerida

Abrir uma subtask chamada `SPIKE_API_EDICAO_MENSAGENS_WHATSAPP` e tratar esta descoberta tecnica como bloqueador da implementacao final.
