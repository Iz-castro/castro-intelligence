# Snapshot das memórias do Claude Code

Estes `.md` são uma **cópia das memórias automáticas do Claude Code** deste
projeto (normalmente em `~/.claude/projects/<slug>/memory/`, que **não** vai
pelo git). Copiadas pra cá em **2026-06-08** pra poder continuar em outra máquina.

`MEMORY.md` é o índice (uma linha por memória); os `project_*.md` são os fatos.

## Pra o Claude usar essas memórias em outro PC

Se o repo estiver no **mesmo caminho** (`c:\Rafael\castro-intelligence`), o slug
do projeto será o mesmo (`c--Rafael-castro-intelligence`). Copie estes arquivos
para a pasta de memória do Claude nesse PC:

```
# destino (Windows):
C:\Users\<voce>\.claude\projects\c--Rafael-castro-intelligence\memory\
```
Copie todos os `.md` (inclusive `MEMORY.md`) pra lá. O Claude carrega o
`MEMORY.md` no início de cada sessão e recupera as demais por relevância.

> Se o caminho do repo for diferente no outro PC, o slug muda — confira a pasta
> `~/.claude/projects/` pra achar o slug correto e copie pra dentro do `memory/`.

## Conteúdo (resumo)
- `project_standard_channel_migration.md` — migração standard + estado do 3351-7604/coex.
- `project_backup_inbox_feature.md` — caixa Backup + como importar.
- `project_operator_isolation_lgpd.md` — isolamento por operador (3 camadas).
- `project_deploy_script_desatualizado.md` — NÃO usar deploy.ps1/.sh; usar `gcloud run deploy --source`.
- `project_gcloud_python.md` — `CLOUDSDK_PYTHON` → Python312.
- `project_whisper_cold_start_outage.md` — transcrição de áudio e cold-start.
- `project_gchat_integration.md` — painel de chat interno (Google Chat).
- `project_hubloc_context.md` — Hubloc x domínio @centralloc.com.br.

Estado operacional da sessão: ver [../2026-06-08-handoff.md](../2026-06-08-handoff.md).
