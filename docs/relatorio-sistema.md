# Castro Intelligence CRM — Relatório do Sistema

**Data:** Março de 2026
**Versão:** 1.0
**Projeto GCP:** `project-26fb9c99-8ee9-4179-aef`

---

## Visão Geral

Sistema de CRM para atendimento via WhatsApp, integrado à Meta Cloud API, com interface web para operadores, persistência em Firestore e infraestrutura no Google Cloud Run.

---

## Arquitetura

```
[WhatsApp / Meta]
       ↓ webhook HMAC-SHA256
[Cloud Run — FastAPI]
  ├── Auth: Firebase (Google OAuth)
  ├── Banco: Cloud Firestore
  ├── Mídia: Cloud Storage (GCS)
  ├── STT: Google Cloud Speech-to-Text
  └── Frontend: React 18 + TypeScript (servido pelo próprio FastAPI)
       ↓ WebSocket (tempo real)
[Operadores — navegador web]
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Frontend | React 18 + TypeScript + Vite |
| Backend | Python 3.10 + FastAPI + Uvicorn |
| Banco de dados | Google Cloud Firestore |
| Autenticação | Firebase Auth (Google Sign-In) |
| Armazenamento de mídia | Google Cloud Storage |
| Transcrição de áudio | Google Cloud Speech-to-Text |
| Conversão de áudio | FFmpeg (WebM → OGG/Opus) |
| Infraestrutura | Google Cloud Run (serverless) |
| CI/Deploy | `deploy.ps1` / `deploy.sh` → Cloud Build → Cloud Run |

---

## Funcionalidades

### Gestão de Usuários e Hierarquia

- Login exclusivo via Google (Firebase Auth)
- Roles: `admin`, `supervisor`, `operador`
- Admin pode alterar role e setor de qualquer usuário pelo painel lateral direito
- Provisionamento automático de conta no primeiro login Google

### Atendimentos

- Fila de conversas com filtro por texto
- **Assumir atendimento:** operador reivindica a conversa — gera protocolo único no formato `ATD-YYYYMMDDHHMMSS-CCCCC` e registra data/hora de início
- **Transferência:** move o contato para outro operador com motivo e resumo obrigatórios
- **Escopo por operador:** cada atendente vê apenas as conversas atribuídas a si ou na fila aberta; admin/supervisor veem tudo
- Protocolo e horário de início exibidos no banner do contato

### Chat

- Envio de texto, foto, vídeo, documento (PDF, DOC, XLS, ZIP, CSV) e localização (GPS do dispositivo)
- Gravação de áudio pelo microfone direto no browser (WebM → OGG/Opus via FFmpeg)
- Exibição de mensagens inbound e outbound com status (enviado, entregue, lido)
- Busca dentro da conversa (ícone de lupa no cabeçalho)
- Menu de 3 pontos: Templates Utility, Templates Marketing, Copiar protocolo
- Lightbox para visualização de imagens e vídeos em tela cheia

### Transcrição de Áudio

- Toda bolha de áudio exibe botão **🔤 Transcrever**
- Transcrição on-demand via Google Cloud Speech-to-Text (padrão `pt-BR`)
- Áudios recebidos via webhook também são transcritos automaticamente quando `FEATURE_AUDIO_TRANSCRIPTION=true`
- Texto transcrito aparece abaixo do player diretamente na bolha

### Interface

- **Tema escuro** por padrão, com toggle claro/escuro (preferência salva no navegador)
- Layout em 3 colunas: fila de contatos | chat central | painel de operação
- **Topbar global** com nome do operador, e-mail, role, toggle de tema e botão Sair
- Modo de entrega configurável: Snapshot (Firestore real-time) ou Polling (REST periódico)
- Responsivo até dispositivos mobile

### Qualificação de Contatos

- Status: Novo, Em atendimento, Qualificado, Não qualificado, Convertido
- Campo de notas livres por contato, salvo individualmente

---

## Infraestrutura Cloud

| Recurso | Valor |
|---------|-------|
| Projeto GCP | `project-26fb9c99-8ee9-4179-aef` |
| Região | `southamerica-east1` (São Paulo) |
| Serviço Cloud Run | `castro-crm` |
| URL pública | `https://castro-crm-6pasznyneq-rj.a.run.app` |
| Webhook Meta | `https://castro-crm-6pasznyneq-rj.a.run.app/webhook` |
| Bucket de mídia | `project-26fb9c99-8ee9-4179-aef.firebasestorage.app` |
| Instâncias | mín. 0 / máx. 3 · concorrência 40 · timeout 300s |
| Memória / CPU | 512Mi / 1 vCPU |
| Service Account | `castro-crm-run@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com` |

---

## Segurança

- Assinatura HMAC-SHA256 obrigatória no webhook (`REQUIRE_WEBHOOK_SIGNATURE=true`)
- Secrets sensíveis armazenados no GCP Secret Manager (token WhatsApp, chave app, chave JWT)
- Service account dedicada com permissões mínimas necessárias
- Firebase ID tokens validados no backend a cada requisição
- CORS configurável por variável de ambiente

---

## Variáveis de Ambiente Principais

| Variável | Descrição |
|----------|-----------|
| `GCP_PROJECT_ID` | ID do projeto GCP |
| `DATA_BACKEND` | `firestore` ou `sql` |
| `AUTH_MODE` | `firebase` (produção) ou `legacy` |
| `WHATSAPP_TOKEN` | Token permanente da Meta Cloud API |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificação do webhook |
| `WHATSAPP_APP_SECRET` | Chave para validação HMAC do webhook |
| `WHATSAPP_PHONE_NUMBER_ID` | ID do número de telefone WhatsApp |
| `FIREBASE_WEB_API_KEY` | Chave da web app Firebase |
| `GCS_MEDIA_BUCKET` | Bucket do Cloud Storage para mídias |
| `FEATURE_AUDIO_TRANSCRIPTION` | `true` para ativar transcrição STT |
| `STT_LANGUAGE_CODE` | Idioma STT (padrão: `pt-BR`) |
| `BOOTSTRAP_ADMIN_EMAIL` | E-mail do primeiro admin provisionado |

---

## Scripts de Deploy

| Script | Plataforma | Comando |
|--------|-----------|---------|
| `deploy.ps1` | Windows (PowerShell) | `.\deploy.ps1` |
| `deploy.sh` | Linux / macOS (Bash) | `./deploy.sh` |

O script realiza automaticamente:
1. Habilitação das APIs GCP necessárias
2. Criação da service account de runtime
3. Criação do bucket de mídia no GCS
4. Concessão de permissões IAM (Firestore, Storage, Secret Manager, Speech)
5. Armazenamento dos secrets no Secret Manager
6. Build da imagem Docker via Cloud Build
7. Deploy no Cloud Run com variáveis de ambiente

---

## Revisões Recentes

| Revisão | Descrição |
|---------|-----------|
| `castro-crm-00014-ck9` | Transcrição de áudio ativada (`FEATURE_AUDIO_TRANSCRIPTION=true`) |
| `castro-crm-00013-9gn` | Correção do bug no botão "Assumir atendimento" (type mismatch int/str) |
| `castro-crm-00012-pw2` | Transcrição on-demand na bolha + novos tipos de mídia (vídeo, doc, localização) |
| `castro-crm-00011-dz7` | Topbar global, tema escuro, protocolo de atendimento, hierarquia de roles |
