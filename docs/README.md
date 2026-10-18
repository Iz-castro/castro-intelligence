# Docs

> **Retomada (links de Ver como atualizados em 2026-10-14):** para retomar qualquer frente, comece por
> [COMO_RETOMAR.md](COMO_RETOMAR.md); o mapa vivo das frentes (o que esta feito, o que esta em
> prod e o que continua pendente) e [PENDENCIAS_E_ROADMAP.md](PENDENCIAS_E_ROADMAP.md).
> Deploy de rotina do CRM = [deploy/DEPLOY_CLOUDRUN_A.md](deploy/DEPLOY_CLOUDRUN_A.md)
> (prod = projeto `project-4a851bf9-f475-418c-800`, regiao `us-west1`; trafego PINADO
> por revisao). Ultimo ADR: [0014](decisions/0014-impersonate-somente-leitura.md)
> (identidade e HTTP/polling de 15 s implementados/validados localmente, feature desligada);
> diario de referencia: [internal/2026-08-21-diagnostico-alarme-sonoro.md](internal/2026-08-21-diagnostico-alarme-sonoro.md).
> `internal/RETOMAR.md` e `internal/resumo.md` sao HISTORICO pre-cutover de Oregon —
> nao rode os comandos `gcloud` de la (apontam pro projeto/regiao antigos de SP).

Documentacao principal do projeto.

## Fonte de verdade

O projeto nao depende de arquivo local fixo de contexto para ser entendido ou operado.

A leitura recomendada agora e:

1. [Arquitetura Firebase](architecture/FIREBASE_ARCHITECTURE.md)
2. [Guia do Codebase](architecture/CODEBASE_GUIDE.md)
3. [Produto](product/README.md)
4. [Deploy e Operacao](deploy/README.md)
5. `docs/internal/` apenas se a tarefa depender de historico recente ou notas locais

## Estrutura

- `architecture/`: arquitetura tecnica, integracoes, modelo de dados e runtime
- `deploy/`: deploy, infraestrutura, variaveis de ambiente e operacao
- `product/`: regras de negocio, fluxos operacionais e capacidades do CRM
- `decisions/`: registros de decisoes tecnicas e trade-offs
- `compliance/`: RoPA, RIPD e mapeamento LGPD (versao interna e versao cliente)
- `internal/`: notas locais, diarios e contexto temporario

## Regras praticas

- documentacao oficial e compartilhavel deve ficar versionada em `docs/`
- material local do agente ou anotacoes temporarias deve ficar em `docs/internal/`
- nao existe mais arquivo obrigatorio de contexto do agente
- o diretorio `docs/` continua fora do deploy via `.gcloudignore`

## Documentos atuais

### Arquitetura e operacao
- [Arquitetura Firebase](architecture/FIREBASE_ARCHITECTURE.md)
- [Guia do Codebase](architecture/CODEBASE_GUIDE.md)
- [Produto](product/README.md)
- [Politica de Numeros WhatsApp](product/POLITICA_NUMEROS_WHATSAPP.md)
- [Deploy e Operacao](deploy/README.md)
- [Runbook de deploy do Cloud Run A](deploy/DEPLOY_CLOUDRUN_A.md) — deploy de rotina do `castro-crm` (comece por aqui)
- [Runbook de Cutover Prod](deploy/RUNBOOK_CUTOVER_PROD.md) — ⚠️ STALE (cita SP/`southamerica-east1`); so referencia historica

### Planos e refactors
- [Ver como: identidade separada](REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md) — contrato aprovado e implementado com transporte HTTP; gates locais aprovados, feature desligada e staging posterior
- [Ver como: TTL por backend](REVISAO_IMPERSONATE_TTL_BACKEND.md) — revisao APROVADA e validada localmente: HTTP/polling de 15 s, janelas e revalidacao final
- [Ver como: diagnostico local](../tools/impersonate_emulators/DIAGNOSTICO.md) — contrato atual: gate local aprovado (779 verificacoes); historico do contrato anterior reprovado (149 positivas, 24 entregas indevidas de backup); sem verificacao de producao
- [Follow-up no CRM — revisão da operação Varizemed](followup_crm_varizemed.md) — 2026-10-18: F1 humana sob flag desligada (FEATURE_FOLLOWUP=false); filas, histórico, calendário e preferência comercial comum, sem envio automático. Teto vigente segue 250/dia por portfólio (D7 do plano v2.2, ADR 0013); o objetivo de 500/dia ainda não foi ativado. Validação e preparo de liberação na seção 16
- [Plano Reabertura em lote — Recepção e Bot (v2)](PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md) — 2026-09-23: decisões fechadas do PO, públicos por estado, 24 casos de aceitação; ADR 0013
- [Retomada em lote pela Val — pedido ao dev de IA](CX_RETOMADA_LOTE_DEV_IA.md) — 2026-10-05: params `origem`, `midia_tipo`, `desfecho_bot`, roteiro de teste e nome de exibição da Hubloc
- [Pendencias e Roadmap](PENDENCIAS_E_ROADMAP.md) — estado por frente (revisado em 2026-08-21)
- [Plano Coexistence — refactor](PLANO_COEXISTENCE_REFATORACAO.md) (Fases 1-4 concluidas)
- [Plano Lead/Atendimento/Mensagem + regras coex hibrido](PLANO_LEAD_ATENDIMENTO_E_REGRAS.md) (Fases 1, 2a, 3, 4 e 5A em prod; 2b, 5B, 5C pendentes)

### Decisoes
- [ADRs](decisions/README.md)

### Compliance LGPD
- [RoPA/RIPD versao cliente](compliance/LGPD_RoPA_RIPD_CLIENTE.md)
- [RoPA/RIPD versao interna](compliance/LGPD_RoPA_RIPD_INTERNO.md) (CONFIDENCIAL — uso interno, nao compartilhar com cliente)

### Outros
- [Screencast App Review](APP_REVIEW_SCREENCAST_SCRIPT.md)
- [Referencia WhatsApp Business Platform (Meta API)](Whatsapp%20Business%20Platform/)
