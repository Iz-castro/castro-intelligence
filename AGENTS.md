# AGENTS.md

Instruções para agentes de código que não são o Claude Code (Codex e outros).

1. As regras deste repositório estão em `CLAUDE.md`, na raiz. Leia o arquivo inteiro antes de qualquer tarefa. Elas valem
   para qualquer agente: produto, dados, LGPD, invariantes, testes, deploy e convenções.
2. Ignore em `CLAUDE.md` apenas o que for ferramenta específica do Claude Code, como workflows, subagentes e skills.
3. Não faça commit, push nem deploy sem pedido explícito de quem conduz a sessão. A branch de integração é `develop`.
4. Em um git worktree, use o Python da pasta principal: `C:\Rafael\castro-intelligence\.venv\Scripts\python.exe`.
   No frontend, rode `npm ci` dentro de `frontend/` do worktree antes do build.
5. Índice da documentação: `docs/README.md`. Decisões de arquitetura: `docs/decisions/`.
