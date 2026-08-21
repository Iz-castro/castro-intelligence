# Internal Docs

Esta pasta e reservada para notas locais ou operacionais.

Uso sugerido:

- memoria de trabalho do agente
- diarios de trabalho
- checklists temporarios
- rascunhos que nao precisam entrar no Git

Observacoes:

- nao existe mais arquivo fixo de contexto do agente nesta pasta
- a fonte de verdade agora esta em `docs/`
- diarios como `2026-04-02.md` fazem sentido aqui porque registram historico recente de trabalho

> **Status em 2026-08-21:** `RETOMAR.md` e `resumo.md` desta pasta sao **HISTORICO**
> (o "estado atual" deles e de 2026-05/06, ANTES do cutover pra Oregon — os comandos
> `gcloud` de la apontam pro projeto/regiao antigos de SP). Estado por frente hoje:
> [`docs/PENDENCIAS_E_ROADMAP.md`](../PENDENCIAS_E_ROADMAP.md); invariantes de runtime e
> deploy: `CLAUDE.md` na raiz; diario mais recente:
> [`2026-08-21-diagnostico-alarme-sonoro.md`](2026-08-21-diagnostico-alarme-sonoro.md).

## Convencao de nomes para diarios

- Formato: `YYYY-MM-DD.md` (ISO 8601). Exemplo: `2026-04-02.md`.
- Para multiplos arquivos no mesmo dia, use sufixo descritivo:
  `2026-04-09_notificacoes.md`, `2026-04-12_pt2.md`.
- Esse formato garante que a ordem alfabetica dos arquivos seja igual
  a ordem cronologica (no explorer, no `git log` e em qualquer script).
