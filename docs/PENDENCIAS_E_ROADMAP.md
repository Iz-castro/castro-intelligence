# Pendências e Roadmap — Castro CRM

> Atualizado 2026-07-15. Consolida as pendências do motor CX/Varizemed + as
> alterações operacionais do Hubloc (notas de 03/07 e 08/07). Fonte viva —
> mover itens pra "feito" conforme forem saindo.

## Estado atual (o que já está no ar)

Motor de bot **Dialogflow CX por tenant** vivo e provado em PROD: Varizemed
(teste) com número real (+55 31 7195-7758), Val respondendo, LGPD + handoff
funcionando. Hubloc intacto (bot builtin). MFA no login do CRM entregue.
Painel super-admin aceita `ai_custom`. Detalhe do que foi feito:
`docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md` + `docs/RETOMAR_VARIZEMED_CX.md`.

---

## 🔴 CAMINHO CRÍTICO — trazer a Varizemed REAL

Decisão do PO: só liga a Varizemed de verdade quando estes gates fecharem.

- [ ] **Disparo em massa / templates** (ADR 0005) — reabrir conversas em lote
      (o "botão" que a Varizemed tem hoje) + campanha de marketing pra milhares.
      Não existe; é a maior obra. Serve Hubloc também.
- [ ] **Suporte a áudio no bot** — hoje o gate do bot é só texto; paciente manda
      áudio → transcrever (STT) antes do DetectIntent. (Cuidado com o custo/
      cold-start do Whisper — incidente 2026-06-03.)
- [ ] **Hardening LGPD** (clínica = dado sensível): TTL/retenção da memória
      (ValMemory), criptografia dos campos sensíveis (sintoma/convênio), audit
      de leitura, máscara de PII nos logs das 2 Cloud Functions.
- [ ] **Migração do histórico:** importar conversas + **re-hospedar a mídia**
      (hoje em URLs do Twilio com auth) ANTES de desligar o Twilio.
- [ ] Aviso LGPD + política + versão + DPA da própria clínica (hoje placeholder).
- [ ] Residência de dados: avaliar agente CX + banco em `southamerica-east1`.
- [ ] Limites da Meta: tier do número novo + quality rating.
- [ ] Decidir: `varizemed-test` vira o real ou cria tenant novo limpo?

---

## 🎨 SPRINT FRONTEND (modular + UI juntos)

Batch: a modularização já mexe no `App.tsx` (monolito 2581 linhas) — aproveitar.

- [ ] **Frontend modular:** Core compartilhado + Módulo Locadora + Módulo Clínica
      (Pacientes/Especialidades/Convênios/Médicos/Agendamentos), por feature
      flags/plano. `hasModule()` irmão do `can()`; `/api/session` já expõe
      `tenant.modules`. (ADR feito; falta implementar.)
- [ ] **[03/07 #1]** Separar no chat conversa da **API** × conversa **coexistence**
      (distinção visual). Objetivo estratégico: ir **minando o coexistence** com
      o tempo. *Prazo original: 15 dias.*
- [ ] **[03/07 #4]** **Repositório de encerrados:** tirar chamadas encerradas da
      caixa principal → higiene visual do sistema.
- [ ] **[03/07 #6]** **Versão mobile** (Paulo, Bruno, Helenice, Izael).
- [ ] Branding por tenant (logo/nome — trocar os 3 literais "Hubloc CRM").

---

## ⚙️ MELHORIAS OPERACIONAIS DO HUBLOC (backend/lógica)

- [ ] **[03/07 #2]** Remover a limitação de **dois atendimentos por pessoa**.
      *Prazo original: 15 dias.*
- [ ] **[08/07 #7]** Mensagem automática às **23:59** após a última conversa pra
      dar sobrevida de 24h. ⚠ **Rever a mecânica:** pela regra da Meta, a janela
      de 24h só reseta com **inbound do cliente** — mensagem do negócio NÃO
      estende. Se o objetivo é reengajar fora da janela, o caminho é **template**
      (liga com o item de disparo). Alinhar a intenção antes de implementar.
- [ ] **[03/07 #3]** Revisão dos scripts/mensagens automáticas do bot (Hubloc) +
      manual de treinamento da equipe de atendimento da API. *Prazo: 30 dias.*

---

## 🔐 SEGURANÇA / INFRA

- [ ] **IAP + domínio** (`admin.castrointelligence.com.br`) na frente do Cloud
      Run B (`castro-superadmin`) — 2ª camada de rede. Passo a passo:
      `docs/HANDOFF_IAP_E_TENANT2.md`.
- [ ] Pós-IAP: sessão-cookie 15min + re-MFA, sink **BigQuery** do
      `audit_logs_system`, impersonate read-only (M-B3), Cloud Armor/rate-limit.
- [ ] **Decommission** do projeto GCP antigo (SP). Quota `cpu_allocation`.
- [ ] Fase 5 do RBAC (remover fallback de role, pós-bake-in).
- [ ] **Follow-ups da revisão do fix de visibilidade pós-assume (2026-08-19)** —
      lista priorizada P1–P10 no diário `docs/internal/2026-08-19-visibilidade-pos-assume.md`.
      Destaques: **P1** `GET /media/{...}` sem auth (URL assinada; `<img src>` não
      manda header); **P2** `_require_contact_access` em
      `/conversation/{id}/read|takeover|return` (IDOR por id determinístico);
      **P3** endurecer rules de `wa_messages` (decisão de produto + backfill).

---

## 🧩 DÍVIDA TÉCNICA DO MOTOR CX

- [ ] **Dev IA:** reforçar o agente pra setar `handoff_request` de forma
      confiável (o CRM já cobre por texto, mas ideal nos dois sinais).
- [ ] Substituir a **ValMemory** por endpoints nativos do CRM
      (`tenants/{tid}/ai_sessions`) — médio prazo.
- [ ] **Multi-tenantizar** a lógica das Cloud Functions (hoje Varizemed-hardcoded)
      pro próximo cliente AI Custom.
- [ ] Recriar o **data store RAG** do agente (não veio no export).
- [ ] `cx_fail_count` atômico (lost update sob concorrência); debounce/agregação;
      reset de `bot_completed` no fechamento.
- [ ] Cloud Run A com tráfego **"pinado"** — deploys futuros precisam de
      `--to-revisions` explícito (senão a revisão nova fica em 0%).

---

## 👥 OPERACIONAL / PESSOAS (não-engenharia — tracking)

- [ ] **[03/07 #5]** +2 supervisores junto com a Helenice (evitar cliente sem
      atendimento) + **treinamento impresso** da supervisão.

---

## 🧹 HOUSEKEEPING DO TESTE (rápido)

- [ ] Desativar o canal de teste `+1 555-484-7272` do `varizemed-test`.
- [ ] Trocar a senha do admin `contato@castrointelligence.com.br`.
- [ ] Apagar tenant sintético `varizemed-cxtest` (prefixo `castro_crm_staging`) +
      canal fake; apagar doc de smoke `conversations/+5571900000001` no `castro-ia`.
- [ ] Dois setores com `bot_key=sac` (Recepção + Suporte) — decidir taxonomia.
