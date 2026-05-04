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

## Convencao de nomes para diarios

- Formato: `YYYY-MM-DD.md` (ISO 8601). Exemplo: `2026-04-02.md`.
- Para multiplos arquivos no mesmo dia, use sufixo descritivo:
  `2026-04-09_notificacoes.md`, `2026-04-12_pt2.md`.
- Esse formato garante que a ordem alfabetica dos arquivos seja igual
  a ordem cronologica (no explorer, no `git log` e em qualquer script).
