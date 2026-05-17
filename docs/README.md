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

- [Arquitetura Firebase](architecture/FIREBASE_ARCHITECTURE.md)
- [Guia do Codebase](architecture/CODEBASE_GUIDE.md)
- [Produto](product/README.md)
- [Deploy e Operacao](deploy/README.md)
- [Task - Novo contato manual em Meus Atendimentos](TASK_FEATURE_NOVO_CONTATO_MANUAL_MEUS_ATENDIMENTOS.md)
- [Task - Fix scroll vertical na coluna de contatos](TASK_FIX_SCROLL_VERTICAL_COLUNA_CONTATOS.md)
- [Task - Prod Hubloc + Coexistence](TASK_PROD_HUBLOC_COEXISTENCE.md)
- [Task - Edicao de Mensagens WhatsApp no CRM](TASK_FEATURE_EDICAO_MENSAGENS_WHATSAPP_CRM.md)
- [Task - Spike API Edicao de Mensagens WhatsApp](TASK_SPIKE_API_EDICAO_MENSAGENS_WHATSAPP.md)
- [LGPD - RoPA/RIPD versao cliente](compliance/LGPD_RoPA_RIPD_CLIENTE.md)
- [LGPD - RoPA/RIPD versao interna](compliance/LGPD_RoPA_RIPD_INTERNO.md) (CONFIDENCIAL - uso interno, nao compartilhar com cliente)
