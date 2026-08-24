# Como retomar uma frente (leia isto primeiro)

Atualizado em 2026-08-22. Este e o ponto de entrada curto; os antigos
`internal/RETOMAR.md` e `internal/resumo.md` sao HISTORICO pre-cutover (Oregon) e
nao devem ser usados como fonte de comandos.

## 1. Onde esta o quê

| Pergunta | Onde olhar |
|---|---|
| O que esta feito / em prod / pendente, por frente | [PENDENCIAS_E_ROADMAP.md](PENDENCIAS_E_ROADMAP.md) — secao **"Frentes abertas"** (uma linha por frente) |
| Regras que NAO podem quebrar (landmines) e como validar/deployar | [`CLAUDE.md`](../CLAUDE.md) na raiz |
| Por que o sistema e assim (decisoes) | [decisions/README.md](decisions/README.md) — indice dos ADRs 0001-0011 com status |
| O que aconteceu em cada dia (historico) | `internal/YYYY-MM-DD*.md` (diario mais recente primeiro) |
| Memoria do agente (espelho versionado) | [internal/claude-memory/](internal/claude-memory/) |
| Deploy do CRM (Cloud Run A) | [deploy/DEPLOY_CLOUDRUN_A.md](deploy/DEPLOY_CLOUDRUN_A.md) |
| Deploy do painel super-admin (Cloud Run B) | [DEPLOY_CLOUDRUN_B.md](DEPLOY_CLOUDRUN_B.md) |
| Trocar a versao (environment) da Val — sem deploy | [deploy/TROCAR_ENVIRONMENT_VAL.md](deploy/TROCAR_ENVIRONMENT_VAL.md) |
| Pedidos ao dev do agente CX (Izael) | `CX_*_DEV_IA.md` |

## 2. Estado de producao (resumo)

- Projeto `project-4a851bf9-f475-418c-800`, regiao `us-west1` (Oregon). Servico
  `castro-crm`; trafego **pinado por revisao** (deploy sobe a 0%, promover por NOME).
- 3 tenants ativos: `hubloc` (bot builtin, pool `legacy`), `varizemed` (agente CX "Val",
  Modo Recepcao ADR 0010), `varizemed-test` (mesmo agente, Draft).
- ADR mais recente: [0011](decisions/0011-unread-derivado-das-threads-e-sons-por-caixa.md)
  (nao-lido derivado das threads; sons so sobre a caixa visivel; filtro "Nao lidas";
  "So espiar").

## 3. Rotina de qualquer mudanca

1. Ler a secao da frente em `PENDENCIAS_E_ROADMAP.md` + o ADR/diario apontado la.
2. Gates locais (todos verdes antes de deploy):
   `py_compile` dos modulos da raiz · `tools\sim_bot_flow.py` · `tools\sim_reception_flow.py`
   · `tools\sim_cx_flow.py` · `npm run build` em `frontend/`.
3. Deploy + promocao por nome + smoke conforme `deploy/DEPLOY_CLOUDRUN_A.md`.
4. Registrar: diario `internal/YYYY-MM-DD-<assunto>.md`, ADR se houve decisao,
   linha da frente em `PENDENCIAS_E_ROADMAP.md`.

## 4. Frentes abertas (ponteiros — o detalhe vive no roadmap)

- Horario comercial **fase 2** (UI/feriados).
- Protecao de borda do Cloud Run B (IAP+LB vs Cloudflare Access) — decisao em aberto.
- Campanha de templates da Varizemed (revisao de seguranca/Meta pendente).
- Parceria Meta / billing (hoje Tech Provider).
- Pos-ADR 0011: limiar do alarme do hubloc; `has_unread` pra ordenar "Nao lidas" por
  recencia; UX da caixa Bot do admin; badges do nav com camada estatica.
- Editor/apagar tenant pelo super-admin (hoje so edita/desativa); `varizemed-test`:
  `bot_key=sac` duplicado (Suporte + Recepcao).
- ADR 0007 Fase 2 (channels tenant-scoped) — congelada; decommission do projeto de SP.
