# Product Docs

Visao funcional do CRM hoje.

## Objetivo do produto

O repositorio implementa um CRM operacional com foco em:

- atendimento via WhatsApp Business Cloud API
- autenticacao com Google via Firebase Auth
- leitura em tempo real via Firestore
- envio e armazenamento de midia
- comunicacao interna complementar via Google Chat

## O que esta ativo hoje

- login com Google
- leitura em tempo real por Firestore `onSnapshot()`
- fallback por polling quando necessario
- atendimento WhatsApp completo no frontend React
- transferencia entre operadores e departamentos
- configuracoes operacionais por usuario e por sistema
- comunicacao complementar por Google Chat

## Fluxos principais

### Atendimento inbound

- receber webhook da Meta
- identificar ou criar contato
- persistir mensagem
- atualizar nao lidas
- baixar midia quando houver
- transcrever audio quando habilitado

### Atendimento outbound

- enviar texto
- enviar imagem, video e documento
- enviar audio
- enviar localizacao
- enviar template para reabertura
- responder mensagem com `context.message_id`

### Operacao do atendente

- qualificar contato
- escrever notas
- assumir atendimento
- transferir atendimento
- marcar conversa como lida
- arquivar e restaurar contato

### Administracao

- editar role e departamento de usuarios
- manter configuracoes do sistema
- manter mensagens rapidas globais e por usuario

## Estado atual do frontend

O frontend React cobre hoje:

- listagem de contatos WhatsApp
- filtros e views `novos`, `meus`, `nao_qualificados` e `equipe`
- timeline de mensagens
- lightbox de imagem e video
- gravacao de audio no navegador
- transcricao manual
- painel de Google Chat

## Pontos em aberto

- evoluir `firestore.rules` para um modelo mais fino por operador e departamento
- definir a estrategia futura do chat interno, caso Google Chat deixe de ser o caminho principal
