# Task - Novo contato manual em Meus Atendimentos

## Data

12/04/2026

## Objetivo

Permitir que o atendente crie manualmente um novo contato direto na coluna `Meus Atendimentos`, antes de qualquer mensagem inbound do cliente, para iniciar a conversa via template WhatsApp.

## Problema de produto

Hoje o CRM cria contatos principalmente a partir de mensagens recebidas no webhook.

Isso impede um fluxo operacional comum:

- o atendente ja tem nome e telefone do lead;
- quer iniciar o contato sem esperar mensagem do cliente;
- precisa abrir a conversa no CRM e disparar um template `utility` ou `marketing`;
- como o contato ainda nao existe, ele nao aparece no chat.

## Comportamento desejado

Na coluna `Meus Atendimentos`:

- exibir um botao `Novo contato`
- ao clicar, abrir formulario/modal com:
  - `Nome declarado`
  - `Telefone`
  - opcionalmente `Canal de envio`, se o operador puder enviar por mais de um canal
- ao salvar:
  - o CRM cria o contato
  - o contato entra imediatamente em `Meus Atendimentos`
  - a conversa abre no painel central mesmo sem mensagens
  - o banner do contato fica visivel
  - o atendente consegue iniciar o contato via template

## Regra de negocio importante

Como o cliente ainda nao enviou mensagem, a janela livre de 24h nao existe.

Portanto:

- o composer de texto livre nao deve ser o caminho principal para esse contato
- a experiencia precisa destacar `Template Utility` e `Template Marketing`
- o sistema deve impedir tentativa de envio livre enquanto `last_inbound_at` estiver vazio

Essa regra ja existe no backend para mensagens livres:

- `POST /api/wa/send` bloqueia quando o cliente nunca enviou mensagem
- `POST /api/wa/send-template` pode ser usado fora da janela de 24h

## Estado atual relevante

- a view `meus` hoje mostra contatos com `assigned_to == usuario_logado`
- o banner do chat ja existe e ja exibe placeholders para:
  - `Templates Utility`
  - `Templates Marketing`
- o schema atual de `wa_contacts` usa `display_name` como nome principal visivel
- hoje nao existe separacao formal entre:
  - nome declarado pelo atendente
  - nome oficial/imediato do perfil do WhatsApp

## Requisito novo de naming do contato

Precisamos separar dois conceitos:

### 1. Nome declarado pelo atendente

Nome comercial/operacional digitado no CRM.

Caracteristicas:

- pode ser criado manualmente no cadastro do contato
- pode ser editado depois
- deve ser o nome preferencial exibido no CRM quando existir

### 2. Nome do perfil do WhatsApp

Nome vindo do perfil do contato na plataforma WhatsApp.

Caracteristicas:

- preenchido pelo webhook quando a Meta envia `contacts[].profile.name`
- imutavel no CRM
- serve como referencia fiel do nome declarado pelo proprio usuario no WhatsApp

## Recomendacao de modelo de dados

Adicionar em `wa_contacts`:

- `declared_name: str`
- `whatsapp_profile_name: str`
- `created_source: "webhook" | "manual"`
- `created_by_user_id: int | null`

### Compatibilidade

Para evitar regressao ampla no frontend atual, a recomendacao e manter um campo de exibicao efetivo:

- `display_name = declared_name || whatsapp_profile_name || phone_formatted`

Opcoes tecnicas:

1. Continuar persistindo `display_name` como campo derivado e sincronizado.
2. Parar de tratar `display_name` como fonte de verdade e montar esse valor na camada de leitura/API.

Recomendacao:

- no backend, tratar `declared_name` e `whatsapp_profile_name` como fonte de verdade
- expor `display_name` ja resolvido para preservar o frontend atual

## Migracao recomendada

Como hoje so existe `display_name`, precisamos de migracao defensiva:

- contatos existentes:
  - copiar `display_name` atual para `whatsapp_profile_name`
  - iniciar `declared_name` vazio
- contatos novos criados manualmente:
  - preencher `declared_name`
  - iniciar `whatsapp_profile_name` vazio
- quando chegar a primeira mensagem inbound:
  - preencher `whatsapp_profile_name` com o valor do webhook
  - manter `declared_name` intacto

## Fluxo funcional proposto

### Fase 1 - Criacao manual do contato

- [x] adicionar botao `Novo contato` na coluna `Meus Atendimentos`
- [x] abrir modal/formulario com nome e telefone
- [x] normalizar telefone antes de salvar
- [x] evitar duplicidade por `wa_id`

### Regras na criacao

- [x] se o telefone ja existir:
  - reutilizar o contato existente em vez de criar duplicado; ou
  - retornar erro claro ao atendente
- [x] criar contato ja atribuido ao atendente logado
- [x] definir `qualification = em_atendimento`
- [x] definir `created_source = manual`
- [x] gravar `created_by_user_id`
- [x] definir `last_inbound_at = null`
- [x] permitir abrir a conversa sem mensagens

### Fase 2 - Experiencia do chat vazio

- [x] manter o banner visivel mesmo sem historico
- [x] mostrar estado vazio especifico:
  - `Contato criado manualmente. Envie um template para iniciar a conversa.`
- [x] destacar acoes de template no menu do banner
- [x] desabilitar ou desencorajar texto livre enquanto nao houver inbound

### Fase 3 - Templates iniciais

- [ ] ligar o menu do banner com envio real de template
- [ ] suportar pelo menos:
  - selecao do template
  - idioma
  - categoria exibida para o atendente (`utility` / `marketing`)
- [ ] apos envio bem-sucedido:
  - registrar mensagem `template` em `wa_messages`
  - manter conversa aberta

## API sugerida

### Criacao manual do contato

Criar endpoint dedicado, por exemplo:

- `POST /api/wa/contact/manual`

Payload sugerido:

```json
{
  "declared_name": "Maria Souza",
  "phone": "31999990000",
  "channel_id": 1
}
```

Resposta esperada:

```json
{
  "contact": {
    "id": 123,
    "wa_id": "5531999990000",
    "display_name": "Maria Souza",
    "declared_name": "Maria Souza",
    "whatsapp_profile_name": "",
    "assigned_to": 7,
    "qualification": "em_atendimento",
    "channel_id": 1,
    "created_source": "manual"
  }
}
```

### Edicao do nome declarado

Criar endpoint dedicado, por exemplo:

- `PUT /api/wa/contact/{contact_id}/declared-name`

Payload:

```json
{
  "declared_name": "Maria Souza - Investidor"
}
```

## Regra de canal na criacao manual

Esse ponto precisa ser fechado na implementacao.

Porque importa:

- o contato precisa nascer com `channel_id` valido
- o endpoint de envio usa `channel_id` para resolver credenciais de envio

### Recomendacao

- se o operador tiver apenas um canal disponivel para envio, usar esse canal automaticamente
- se houver mais de um canal disponivel, exigir selecao de canal no modal de criacao
- se nenhum canal estiver disponivel, bloquear a criacao com erro claro

## Impactos no frontend

- `frontend/src/App.tsx`
  - adicionar CTA em `Meus Atendimentos`
  - adicionar modal/form de novo contato
  - adaptar banner para mostrar os dois nomes quando existir diferenca
- `frontend/src/context/CrmContext.tsx`
  - adicionar acao de criar contato manual
  - atualizar lista local e selecao do contato criado
- `frontend/src/types.ts`
  - incluir:
    - `declared_name`
    - `whatsapp_profile_name`
    - `created_source`
    - `created_by_user_id`

## Impactos no backend

- `main.py`
  - criar endpoint de criacao manual
  - criar endpoint de edicao de nome declarado
- `database_firestore.py`
  - suportar persistencia dos novos campos
  - resolver `display_name` efetivo na leitura
- `webhook.py`
  - preencher `whatsapp_profile_name` sem sobrescrever `declared_name`
- exportacoes e relatorios
  - revisar se devem exportar os dois nomes

## Criterios de aceite

- [x] o atendente consegue criar manualmente um contato em `Meus Atendimentos`
- [x] o contato aparece imediatamente na lista e abre no chat
- [x] a conversa pode existir sem mensagens
- [x] o banner mostra informacoes suficientes do contato mesmo sem historico
- [x] o sistema bloqueia texto livre quando ainda nao existe janela de 24h
- [ ] o sistema permite iniciar o atendimento por template
- [x] o nome declarado pode ser editado depois
- [x] o nome do perfil do WhatsApp permanece imutavel
- [x] quando o webhook trouxer o nome oficial do WhatsApp, ele nao sobrescreve o nome declarado
- [x] nao ocorre duplicidade de contato para o mesmo telefone

## Perguntas em aberto para a implementacao

- [x] ao detectar telefone ja existente, vamos abrir o contato existente ou retornar erro?
  - **Decisao:** reutiliza o contato existente e reatribui ao operador
- [x] o modal deve permitir escolher canal logo na criacao ou so quando houver mais de um disponivel?
  - **Decisao:** so exibe seletor de canal quando ha mais de um ativo
- [x] o composer deve ficar totalmente bloqueado ou apenas mostrar erro ao tentar enviar?
  - **Decisao:** composer substituido por mensagem informativa quando nao ha janela 24h
- [x] vamos mostrar no banner algo como:
  - **Decisao:** formato `NomeWA - Apelido` no banner; apelido editavel via menu dots

## Resultado esperado

O atendente passa a conseguir iniciar contatos outbound de forma organizada dentro do proprio CRM, sem gambiarra externa, mantendo rastreabilidade do lead, separacao correta entre nome operacional e nome oficial do WhatsApp, e respeitando as regras da janela de 24h da Meta.

