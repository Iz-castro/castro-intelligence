# Pendências e Roadmap — Castro CRM

> Atualizado 2026-07-15. Consolida as pendências do motor CX/Varizemed + as
> alterações operacionais do Hubloc (notas de 03/07 e 08/07). Fonte viva —
> mover itens pra "feito" conforme forem saindo.

> **Status em 2026-08-21 (revisão por frente).** Muita coisa saiu depois de 15/07 e
> o arquivo estava induzindo a erro: a **Varizemed real está em produção** desde
> 2026-07-28 e o **Modo Recepção** (ADR 0010) desde 2026-08-05 — o "caminho crítico"
> abaixo virou histórico e os gates que sobraram estão remarcados item a item.
> As frentes novas (e as que continuam paradas) estão em
> **[Frentes abertas — status em 2026-08-21](#-frentes-abertas--status-em-2026-08-21)**,
> no fim do arquivo. Fontes: `CLAUDE.md`, ADRs `0009`/`0010`/`0011` e os diários de
> `docs/internal/`.

## Estado atual (o que já está no ar)

Motor de bot **Dialogflow CX por tenant** vivo e provado em PROD: Varizemed
(teste) com número real (+55 31 7195-7758), Val respondendo, LGPD + handoff
funcionando. Hubloc intacto (bot builtin). MFA no login do CRM entregue.
Painel super-admin aceita `ai_custom`. Detalhe do que foi feito:
`docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md` + `docs/RETOMAR_VARIZEMED_CX.md`.

> **Atualização 2026-08-21:** superado. O tenant REAL `varizemed` (plano `ai_custom`)
> foi criado em prod em **2026-07-28** pelo painel do Cloud Run B e o fluxo CX rodou
> ponta a ponta em 29/07; `varizemed-test` continua ativo (mesmo agente, no DRAFT).
> Hubloc segue no bot builtin (`pool_mode=legacy`). **3 tenants ativos** ⇒ login sem
> claim e sem domínio casado é **403** (rede de transição desarmada, by design).

---

## 🔴 CAMINHO CRÍTICO — trazer a Varizemed REAL

Decisão do PO: só liga a Varizemed de verdade quando estes gates fecharem.

> **SUPERADO em 2026-07-28** — a Varizemed REAL entrou em prod antes de todos estes
> gates fecharem. O que sobrou de cada item está marcado abaixo.

- [ ] **Disparo em massa / templates** (ADR 0005) — reabrir conversas em lote
      (o "botão" que a Varizemed tem hoje) + campanha de marketing pra milhares.
      Não existe; é a maior obra. Serve Hubloc também.
      **PARCIAL (2026-08-21):** existe caminho por script — `scripts/send_template_bulk.py`
      + `scripts/wa_phone_norm.py` versionados no commit `51ff640`; teste real OK em
      2026-08-08. **Falta:** revisão adversarial (segurança + regras da Meta) e rodar a
      lista pendente. Não há UI de campanha.
- [x] **Suporte a áudio no bot** — **FEITO em 2026-08-10** (commit `7efd537`: áudio
      transcrito chega ao bot). O modelo Whisper é embutido na imagem
      (`HF_HUB_OFFLINE=1`), por isso `FEATURE_AUDIO_TRANSCRIPTION=true` é seguro —
      trocar `WHISPER_MODEL_SIZE` exige rebuild (incidente 2026-06-03). O guard
      `was_dup` para áudio entrou em `b503870` (a Meta reentrega o webhook ~23s sem
      ACK e o bot respondia 2x). **Aberto:** o Whisper roda síncrono e bloqueia o
      event loop.
- [ ] **Hardening LGPD** (clínica = dado sensível): TTL/retenção da memória
      (ValMemory), criptografia dos campos sensíveis (sintoma/convênio), audit
      de leitura, máscara de PII nos logs das 2 Cloud Functions.
      Continua **aberto** — plano em `docs/PLANO_J3_LGPD_E_REVOGACAO.md`; decisões
      D1-D3 já aceitas no [ADR 0009](decisions/0009-modelos-crm-d1-d3-retorno-ao-bot.md).
- [x] **Migração do histórico:** importar conversas + **re-hospedar a mídia**
      (hoje em URLs do Twilio com auth) ANTES de desligar o Twilio. — **Concluído**
      (PO 2026-08-22: Twilio desligado, servidor migrado).
- [x] Aviso LGPD + política + versão + DPA da própria clínica (hoje placeholder). —
      fechado segundo o PO (2026-08-22); texto vigente em `settings.ai.lgpd_notice`,
      `lgpd_policy_version=varizemed-2026-07`.
- [x] Residência de dados: avaliar agente CX + banco em `southamerica-east1`. —
      decidido/fechado (PO 2026-08-22): agente CX em `us-central1` (projeto `castro-ia`),
      banco/Cloud Run em `us-west1` (Oregon).
- [x] Limites da Meta: tier do número novo + quality rating. — fechado segundo o PO
      (2026-08-22); acompanhar pelo Business Manager quando a campanha de templates rodar.
- [x] Decidir: `varizemed-test` vira o real ou cria tenant novo limpo? —
      **RESOLVIDO em 2026-07-28:** tenant novo e limpo (`varizemed`); o
      `varizemed-test` foi mantido ativo (mesmo agente CX, no DRAFT).

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
      **PARCIAL:** a topbar já usa `tenant.name` desde 2026-07-21 (commit `c921ac8`) e
      a tela de login usa marca neutra (`9bbf51f`). Restam 3 literais no código:
      `frontend/src/App.tsx:65`, `frontend/src/components/gchat/InternalChatPanel.tsx:206`
      e `webhook_google_chat.py:136`.

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
      **Decisão do PO em aberto (2026-08-21):** Opção A = IAP + Load Balancer no GCP;
      Opção B = Cloudflare Access (US$0, recomendada — o DNS já está no Cloudflare).
      O gate é só no painel admin (Cloud Run B); **nunca** na frente do CRM.
- [ ] Pós-IAP: sessão-cookie 15min + re-MFA, sink **BigQuery** do
      `audit_logs_system`, impersonate read-only (M-B3), Cloud Armor/rate-limit.
- [ ] **Decommission** do projeto GCP antigo (SP). Quota `cpu_allocation`.
- [ ] Fase 5 do RBAC (remover fallback de role, pós-bake-in).
- [ ] **Follow-ups da revisão do fix de visibilidade pós-assume (2026-08-19)** —
      *(o fix base foi pra prod em 2026-08-20, commit `3aa9d05`; os follow-ups abaixo
      continuam abertos)* —
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
- [x] Cloud Run A com tráfego **"pinado"** — **não é pendência, é o procedimento**:
      todo deploy sobe a revisão nova a 0% e a promoção é manual, **pelo NOME da
      revisão** (o nome impresso pelo `gcloud run deploy` pode mentir — descobrir por
      `creationTimestamp`). Documentado em `CLAUDE.md` e no runbook
      `docs/deploy/DEPLOY_CLOUDRUN_A.md`.

---

## 👥 OPERACIONAL / PESSOAS (não-engenharia — tracking)

- [ ] **[03/07 #5]** +2 supervisores junto com a Helenice (evitar cliente sem
      atendimento) + **treinamento impresso** da supervisão.

---

## 🧹 HOUSEKEEPING DO TESTE (rápido)

- [x] Desativar o canal de teste `+1 555-484-7272` do `varizemed-test`. — feito: em
      2026-08-22 o registry `channels` do `varizemed-test` só tem o canal 6 (standard,
      +55 31 …7758); o número de teste da Meta não existe mais lá.
- [x] Trocar a senha do admin `contato@castrointelligence.com.br`. — PO 2026-08-22: trocada.
- [ ] Apagar tenant sintético `varizemed-cxtest` (prefixo `castro_crm_staging`) +
      canal fake; apagar doc de smoke `conversations/+5571900000001` no `castro-ia`.
      — **fica pra outra frente** (PO 2026-08-22: quer fazer pelo superadmin). Hoje o
      painel B só EDITA tenant (`PATCH /api/superadmin/tenants/{id}`: name/plan/cnpj/
      is_active/domínios) — dá pra **desativar**; apagar os dados exige script.
- [ ] Dois setores com `bot_key=sac` (Recepção + Suporte) — decidir taxonomia.
      — Só no `varizemed-test`: setores 3 "Suporte" e 5 "Recepção" têm ambos
      `bot_key=sac`; o handoff da Val (`handoff_bot_key=sac`) resolve o setor por esse
      campo e pega o PRIMEIRO que achar → lead pode cair em "Suporte". Correção: trocar o
      `bot_key` de um deles pela UI de setores. No `varizemed` REAL está certo (só
      "Recepção" ativa com `sac`; "Recepção (antiga)" inativa). Conferido em 2026-08-22.

---

## 🆕 Frentes abertas — status em 2026-08-21

Uma linha por frente, pra não perder o fio quando o dia a dia interromper.
**Legenda:** ✅ em prod · 🟡 parcial · ⛔ parado/pendente.

- ✅ **Modo Recepção / pool compartilhada** — [ADR 0010](decisions/0010-pool-mode-recepcao.md),
  em prod na `varizemed` desde 2026-08-05 (varizemed real com `pool_mode=reception` desde 2026-08-06). Hubloc segue `legacy` ("assumir pra falar",
  [ADR 0008](decisions/0008-lead-gruda-na-vendedora.md)). Kill-switch sem deploy:
  `PUT system_settings/chat.pool_mode=legacy`.
- ✅ **Não-lido derivado das threads + som só sobre o que a caixa mostra** —
  [ADR 0011](decisions/0011-unread-derivado-das-threads-e-sons-por-caixa.md), em prod
  em 2026-08-21 (commit `d9eb329`), backfill aplicado nos 3 tenants.
  ⛔ **Follow-ups abertos** (diário `internal/2026-08-21-diagnostico-alarme-sonoro.md`):
  limiar do alarme do Hubloc (1 min) e as não-lidas reais das operadoras; `has_unread`
  booleano pra ordenar "Não lidas" por recência; UX da caixa Bot do admin ("Carregar
  mais" pode não acrescentar linha + estado vazio); badges do nav inflando com a camada
  estática; listener da Caixa Backup sem limite.
- 🟡 **Horário comercial por tenant** — FASE 1 em prod em 2026-08-10 (commit `5854c2c`:
  `business_hours.py`, params pro CX da Val, aviso do builtin no Hubloc).
  ⛔ **FASE 2 (UI + feriados) pendente.**
- 🟡 **Motor CX / Val** — em prod: timeout do DetectIntent de 60s por TURNO e read-timeout
  da chamada principal reenviando 1x (`CX_READ_TIMEOUT_RETRY`, pior caso ~2min; commits
  `b503870` e `3c05457`); frase de erro do agente reenvia 3x e faz handoff no 4º
  (`4bc5d79`); troca de environment da Val por runbook (`deploy/TROCAR_ENVIRONMENT_VAL.md`).
  ⛔ Abertos: `user_first_input` não é reenviado quando o turno do aceite falha; Whisper
  síncrono bloqueia o event loop; pendências do agente em `CX_AGENTE_PENDENCIAS_DEV_IA.md`.
- 🟡 **Isolamento pós-assume (LGPD)** — fix em prod em 2026-08-20 (commit `3aa9d05`):
  o chat do outro operador fecha quando a thread muda de dono e `/api/wa/assume` carimba
  o dono nas threads órfãs. ⛔ Follow-ups P1–P10 continuam abertos (ver
  🔐 SEGURANÇA / INFRA acima; diário `internal/2026-08-19-visibilidade-pos-assume.md`).
- ✅ **Filtro de qualificação na sidebar e no picker + "carregar mais" na pool/bot** —
  em prod em 2026-08-17 (commit `bb668f2`).
- 🟡 **Campanha de templates da Varizemed** — ver "Disparo em massa / templates" acima.
- ⛔ **Queda de leads do Hubloc (14–16/08)** — diagnosticada: o serviço está OK (webhook
  100% 200, fila `pending` zerada); a queda é do **tráfego do botão do site**. Flag da
  Meta: canal 4 com `name_status DECLINED`. Diário
  `internal/2026-08-18-diagnostico-leads-hubloc.md`. Ação é do lado do cliente/marketing.
- ⛔ **Decommission do projeto GCP antigo (SP `project-26fb9c99-8ee9-4179-aef`)** — o
  `gcloud config` da máquina ainda aponta pra ele; por isso todo comando exige
  `--project` explícito.
- ⛔ **Refactor Lead/Atendimento: Fases 2b, 5B e 5C** — paradas desde 05/2026
  (`PLANO_LEAD_ATENDIMENTO_E_REGRAS.md`): abas por canal, tipificação obrigatória no
  fechamento e resumo por IA ao fechar.
- ⛔ **ADR 0007 Fase 2** (`channels` → `tenants/{tid}/channels`) — pendência congelada, reabrível só com desenho novo; o **Método B** (signup standard na UI) foi FEITO e PROVADO em 2026-06-05 (commit `817e730`). Multi-empresa no canal standard (plano ainda não
  iniciado).
- 🟡 **Parceria Meta / billing:** o cron de health-check de billing teve problema; para
  operar billing/limites como parceiro é preciso virar **Meta Partner** (hoje somos
  **Tech Provider**; App Review de Tech Provider FEITO; possivelmente um novo App Review
  para parceria). PO 2026-08-22. Ver `internal/RETOMAR.md` (tabela) e ADR 0004.
