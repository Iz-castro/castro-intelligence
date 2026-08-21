# Como trocar o environment da Val (agente Dialogflow CX) — runbook do PO

Para quando o Izael publicar uma versão nova do agente e mandar um caminho tipo:

```
projects/castro-ia/locations/us-central1/agents/5fa69ea1-.../environments/<UUID>
```

O que importa é só o **UUID do final** (o script aceita o caminho inteiro colado).
Leva 2 minutos, **não tem deploy**, vale em ~60 segundos.

---

## O que essa troca faz (e o que NÃO faz)

- Muda **um campo** no documento do tenant no Firestore
  (`castro_crm_tenants/varizemed → settings.ai.environment_id`) e o rótulo
  `core_version` junto. Só isso. Aviso LGPD, agente, projeto, setor do handoff —
  tudo fica como está (o script confere e imprime).
- **Não** mexe no agente, no Cloud Run, nem em nenhum lead.
- **Reseta a sessão de quem estiver conversando com a Val naquele instante**
  (o environment faz parte do "endereço" da sessão no CX). Quem estiver no meio
  de uma conversa recomeça do zero. Por isso o passo 2 abaixo.

## Passo a passo

Abra o PowerShell **na raiz do repo** (`c:\Rafael\castro-intelligence`) e cole
os dois `$env:` primeiro — o script precisa deles pra achar o projeto certo:

```powershell
$env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
$env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
```

**1. Ver como está hoje** (guarda essa saída — é o seu rollback):

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed --show
```

**2. Ver se tem alguém no meio de conversa com a Val:**

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed --who-is-in-bot
```

Se listar gente, espere um pouco (ou faça fora do expediente). Se disser
"nenhum — janela limpa pra trocar", segue.

**3. Ensaiar (dry-run — não grava nada):**

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed `
    --env "COLE_AQUI_O_CAMINHO_OU_UUID_QUE_O_IZAEL_MANDOU" `
    --core-version val-X.Y.Z `
    --expect-current UUID_ATUAL_DO_PASSO_1
```

- `--core-version`: o nome da versão que o Izael deu (ex.: `val-5.0.21`). Não
  aparece pro paciente, é só etiqueta pra quem investigar depois — mas é
  **obrigatório**, pra etiqueta nunca mais mentir.
- `--expect-current`: o UUID que apareceu no passo 1. É uma trava: se alguém
  já tiver trocado sem você saber, o script **aborta** em vez de gravar em cima.

Confira a saída: só duas linhas com `*` (environment_id e core_version); tudo
o mais com `=`. Se aparecer `*` em outra linha, **pare** e me chame.

**4. Aplicar** — mesmo comando, com `--yes` no fim:

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed `
    --env "..." --core-version val-X.Y.Z --expect-current UUID_ATUAL --yes
```

Saída esperada: `environment_id : <novo> (ok)`, `core_version : ... (ok)`,
`demais campos intactos: True`, `lgpd_notice preservado: True` — e a linha de
**ROLLBACK** pronta pra copiar. Guarde-a.

**5. Testar** (número de teste, ou o próximo lead real):

- mandar "olá" → aviso LGPD da Varizemed;
- aceitar → a Val cumprimenta;
- pedir atendimento → tem que cair na aba **Recepção** do CRM.
  Se ficar preso na aba **Bot**, é a mensagem de transferência que mudou de
  texto — rollback (passo 6) e me avisa.

**6. Rollback** (se algo estranhar): é o mesmo comando, com o environment
**anterior** (a linha ROLLBACK do passo 4):

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed `
    --env UUID_ANTERIOR --core-version ROTULO_ANTERIOR --yes
```

## O tenant de teste (`varizemed-test`)

Ele deve ficar no **Draft** por padrão (é onde o Izael edita e testa antes de
publicar). Se você o apontou pra algum environment pra testar algo, devolva:

```powershell
./.venv/Scripts/python.exe -m scripts.set_cx_environment --tenant varizemed-test --draft --yes
```

Draft = `environment_id` vazio. **Nunca** deixe a clínica real (`varizemed`)
no Draft: qualquer edição do Izael no console entraria em produção na hora.

## Histórico (pra saber o que já rodou)

| data | environment | versão | nota |
|---|---|---|---|
| 31/07 | `6bdfaeed-6dd3-445c-b32a-4e1f85ab32dd` | val-5.0 | primeiro publicado |
| 10/08 12:20 | `75028a25-7094-43d0-a033-9a2cb90e7988` | val-5.0.1 | reescreveu msg de transferência (CRM ajustou hints) |
| 10/08 16:35 | `39408565-9cb8-4cdd-8e5c-2c5493b2ab6f` | val-5.0.11 | correção de texto |
| 14/08 13:40 | `834d5241-5337-4848-91a5-1479c6fcdc9b` | val-5.0.12 | correção do erro "Sorry something went wrong" |
| 16/08 23:35 | `05267e69-9632-444c-b009-b6069a7474e2` | val-5.0.21 | greeting v3, router v7, tool v3 |
| 21/08 15:50 | `22390163-6bbc-47b5-a25a-e53eb3363d8f` | **val-5.0.3** | rótulo informado pelo Izael; aplicado com 1 contato na janela de 60 min (decisão do PO) — **atual** |

Atualize esta tabela a cada troca (é a memória de quem vier depois).

## Se der erro no script

- `Tenant 'x' nao existe` → conferiu o `$env:FIRESTORE_PROJECT_ID`? Sem ele o
  script bate no projeto errado (o `gcloud config` da máquina aponta pro
  projeto antigo de SP).
- `ABORTADO: environment atual e ...` → alguém já trocou; rode `--show`, entenda
  o estado, e refaça com o `--expect-current` certo.
- `--env invalido` → o UUID veio incompleto/colado errado; peça o caminho de
  novo pro Izael.
- Qualquer `ERRO` na conferência final → não mexa mais; me chame com a saída.
