# Product Docs

> **Status em 2026-08-21:** este doc ainda descreve o CRM de um tenant so. Hoje ele e
> **multi-tenant** (3 tenants ativos em prod) e o atendimento tem **dois modos por
> tenant**: "assumir pra falar" (`pool_mode=legacy`, Hubloc —
> [ADR 0008](../decisions/0008-lead-gruda-na-vendedora.md)) e **Modo Recepcao** (pool
> compartilhada, varizemed — [ADR 0010](../decisions/0010-pool-mode-recepcao.md)).
> Ha agente de IA por tenant (bot builtin no Hubloc, Dialogflow CX "Val" na varizemed),
> gate LGPD antes do bot e horario comercial por tenant (fase 1). Desde 2026-08-21 o
> nao-lido do contato e derivado das threads e o som toca so sobre o que a caixa mostra
> ([ADR 0011](../decisions/0011-unread-derivado-das-threads-e-sons-por-caixa.md)).
> As views da sidebar hoje sao `novos`, `meus`, `nao_qualificados`, `equipe`, `bot` e
> `backup` (`frontend/src/types.ts`), com filtro de qualificacao e filtro "Nao lidas".
> Estado por frente: [`docs/PENDENCIAS_E_ROADMAP.md`](../PENDENCIAS_E_ROADMAP.md).

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

- ✅ (CONCLUIDO em 2026-06-03) `firestore.rules` evoluiu para modelo restritivo por operador: usuario comum ve APENAS contatos/conversas atribuidos a si OU sem dono (pool/fila); visibilidade por `department_id` removida; admin/supervisor veem tudo
- definir a estrategia futura do chat interno, caso Google Chat deixe de ser o caminho principal
