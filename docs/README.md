# Docs

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
- [Runbook de Cutover Prod](deploy/RUNBOOK_CUTOVER_PROD.md)

### Planos e refactors
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
