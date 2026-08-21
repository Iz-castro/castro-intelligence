# Decision Records

Esta pasta e reservada para registros curtos de decisoes tecnicas.

Formato sugerido:

- contexto
- decisao tomada
- alternativas consideradas
- consequencias

Boa opcao para ADRs simples ao longo da evolucao do projeto.

## Indice dos ADRs (status em 2026-08-21)

| # | Titulo | Status |
|---|---|---|
| [0001](0001-prevenir-coex-signup-duplicado.md) | Prevenir Embedded Signup duplicado pro mesmo numero coexistence | Proposed |
| [0002](0002-lgpd-canal-coex-compartilhado.md) | LGPD em canal coexistence compartilhado por multiplos operadores | Proposed (emenda 2026-06-03: visibilidade por `department_id` removida) |
| [0003](0003-refactor-lead-atendimento.md) | Refactor Lead/Atendimento/Mensagem + regras coex hibrido (Fases 1-5A) | Implementado em prod (Fases 2b/5B/5C pendentes) |
| [0004](0004-falha-billing-assincrona-webhook.md) | Tratar falha de billing assincrona (webhook failed) e avisar o admin | Proposed |
| [0005](0005-templates-meta-e-disparo-em-lote.md) | Padronizacao de templates Meta e arquitetura de disparo em lote | Proposed (existe caminho por script: `scripts/send_template_bulk.py`) |
| [0006](0006-fluxo-redefinicao-senha-operadores.md) | Fluxo de redefinicao de senha para operadores | Proposed ("esqueci minha senha" no login entrou em 2026-07-29, commit `9bbf51f`) |
| [0007](0007-isolamento-channels-pending-events.md) | Isolamento multi-tenant de `channels` e `pending_webhook_events` | Fase 1 EM PROD (`channels` em `_GLOBAL_COLLECTIONS`); Fase 2 (channels tenant-scoped) pendente/congelada; Metodo B (signup standard) FEITO 2026-06-05 |
| [0008](0008-lead-gruda-na-vendedora.md) | Lead "gruda" na vendedora (dona de origem + revert no fechamento) | Accepted — em prod desde 2026-06-05 (default do `pool_mode=legacy`, Hubloc) |
| [0009](0009-modelos-crm-d1-d3-retorno-ao-bot.md) | Modelos de CRM: decisoes D1-D3 do retorno-ao-bot (clinica) | Aceito pelo PO (2026-08-01) |
| [0010](0010-pool-mode-recepcao.md) | Modo Recepcao: pool compartilhada por tenant (`pool_mode`) | Aceito — EM PRODUCAO desde 2026-08-05 (promocao; varizemed real com pool_mode=reception desde 2026-08-06) |
| [0011](0011-unread-derivado-das-threads-e-sons-por-caixa.md) | `unread_count` do contato derivado das threads; beep/alarme so sobre o que a caixa mostra | Aceito — EM PRODUCAO em 2026-08-21 (backfill aplicado) |

Estado por frente (o que falta em cada uma): [`docs/PENDENCIAS_E_ROADMAP.md`](../PENDENCIAS_E_ROADMAP.md).
