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
- `internal/`: notas locais, diarios e contexto temporario

## Regras praticas

- documentacao oficial e compartilhavel deve ficar versionada em `docs/`
- material local do agente ou anotacoes temporarias deve ficar em `docs/internal/`
- nao existe mais arquivo obrigatorio de contexto do agente
- o diretorio `docs/` continua fora do deploy via `.gcloudignore`

## Documentos atuais

- [Arquitetura Firebase](architecture/FIREBASE_ARCHITECTURE.md)
- [Guia do Codebase](architecture/CODEBASE_GUIDE.md)
- [Produto](product/README.md)
- [Deploy e Operacao](deploy/README.md)
