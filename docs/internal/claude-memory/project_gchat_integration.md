---
name: Google Chat integration plan
description: Plan to build internal chat panel in CRM that bridges to Google Chat via API for operator-supervisor communication
type: project
---

Projeto de integração de chat interno no CRM Hubloc que faz bridge com Google Chat do workspace @centralloc.com.br.

**Why:** Atendentes (escritório) precisam se comunicar em tempo real com supervisores (pátio/campo) para aprovações de desconto, consulta de estoque, etc. Supervisores usam Google Chat no celular.

**How to apply:**
- Não é um widget embeddable do Google Chat — é um painel de chat customizado no React que usa a Google Chat API como transporte
- Backend: FastAPI no Cloud Run (mesmo projeto GCP existente)
- Dados: Firestore coleção `internal_chats` com sub-coleção `messages` para auditoria
- Frontend: painel lateral slide-in (direita para esquerda) ao lado do ícone de configurações
- Google Chat App será criado no mesmo projeto GCP, publicado como app interno do workspace
