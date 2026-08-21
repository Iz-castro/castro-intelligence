# Architecture Docs

Esta pasta concentra documentos tecnicos de arquitetura.

Coloque aqui:

- visao de runtime
- integracoes externas
- modelo de dados
- fluxo entre frontend, backend e infraestrutura

Documentos atuais:

- [Firebase Architecture](FIREBASE_ARCHITECTURE.md)
- [Codebase Guide](CODEBASE_GUIDE.md)

> **Status em 2026-08-21:** os **invariantes de runtime** que nao podem quebrar
> (`_GLOBAL_COLLECTIONS`, `channel_id` do contador global, `conversation_id`
> deterministico, isolamento do operador, `pool_mode`) vivem no `CLAUDE.md` da raiz;
> as decisoes que os criaram estao no [indice dos ADRs](../decisions/README.md).
