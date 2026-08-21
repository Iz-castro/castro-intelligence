# Snapshot das memórias do Claude Code

> **Status em 2026-08-21:** espelho **ressincronizado** — agora são 30 memórias
> `project_*.md` (eram 8) mais o índice `MEMORY.md`. Isto é um **snapshot**: a fonte da
> verdade do estado atual é o `CLAUDE.md`, os ADRs em `docs/decisions/` (até o **0011**) e
> os diários em `docs/internal/`. Memórias `user_*.md` / `feedback_*.md` e telefones
> pessoais ou de lead ficam **fora** deste espelho (PII).

Estes `.md` são uma **cópia das memórias automáticas do Claude Code** deste
projeto (normalmente em `~/.claude/projects/<slug>/memory/`, que **não** vai
pelo git). Copiadas pra cá em **2026-06-08** pra poder continuar em outra máquina;
ressincronizadas em **2026-08-21**.

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
- `project_deploy_script_desatualizado.md` — deploy.ps1/.sh **REMOVIDOS do repo** (2026-08-06); usar `gcloud run deploy --source` + promover por nome.
- `project_gcloud_python.md` — `CLOUDSDK_PYTHON` → Python312.
- `project_whisper_cold_start_outage.md` — transcrição de áudio e cold-start.
- `project_gchat_integration.md` — painel de chat interno (Google Chat).
- `project_hubloc_context.md` — Hubloc x domínio @centralloc.com.br.

> As outras 22 memórias vieram na ressincronização de 2026-08-21 (cutover Oregon,
> multi-tenant/login tenant-aware, Modo Recepção ADR 0010, Val/Dialogflow CX, custos
> Firestore, ADR 0011 não-lido derivado das threads, ...). O índice completo, com uma
> linha por memória, é o `MEMORY.md` ao lado deste arquivo.

Estado operacional da sessão em que o espelho nasceu: ver
[../2026-06-08-handoff.md](../2026-06-08-handoff.md) (histórico). Estado mais recente:
`CLAUDE.md` + o diário mais novo em `docs/internal/` (hoje,
[../2026-08-21-diagnostico-alarme-sonoro.md](../2026-08-21-diagnostico-alarme-sonoro.md)).
