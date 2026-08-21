> **Status em 2026-08-21 — arquivo HISTORICO (lista solta de 2026-05/06, pre-cutover
> pra Oregon). Nao rode o comando do item 1:** ele aponta pro projeto/regiao ANTIGOS de
> Sao Paulo (`project-26fb9c99-8ee9-4179-aef` / `southamerica-east1`). Prod hoje =
> `project-4a851bf9-f475-418c-800` / `us-west1`. Mapa vivo das frentes:
> [`docs/PENDENCIAS_E_ROADMAP.md`](../PENDENCIAS_E_ROADMAP.md).
> Ja resolvido desta lista: **item 1** (as envs `WHATSAPP_PHONE_NUMBER_ID` /
> `WHATSAPP_WABA_ID` foram removidas de prod de proposito — ver `docs/deploy/README.md`)
> e **item 3** (`.env` esta no `.gitignore`). Os demais nao foram reconferidos hoje —
> trate como rascunho, nao como pendencia confirmada.

vO que falta fazer — em ordem de prioridade
🔥 Higiene rápida (baixo esforço, alto valor)
1 Limpar env vars do Cloud Run prod pra parar de recriar o canal #2 standard a cada deploy:


gcloud run services update castro-crm `
  --region=southamerica-east1 --project=project-26fb9c99-8ee9-4179-aef `
  --remove-env-vars=WHATSAPP_PHONE_NUMBER_ID,WHATSAPP_WABA_ID
2 Rotacionar WHATSAPP_TOKEN de novo — foi exposto no chat hoje. Atualizar Secret Manager + .env.

3 Adicionar .env ao .gitignore (se já não está) pra evitar commit acidental.

🐛 Bugs descobertos hoje (não bloqueiam, mas vale corrigir)
4 "Equipe" deveria mostrar nome do operador. _user_map em database_firestore.py:1326 provavelmente faz lookup flat e não acha users que vivem em tenants/{tid}/users. Trocar pra usar _get_doc("users", id) que respeita tenant_context.

5 [HISTORY MEDIA] Mensagem original nao encontrada — webhook de mídia chega antes da msg referenciada (race entre chunks da Meta). Solução: enfileirar mídia órfã pra retry depois, ou fazer lookup retentativo.

🎨 Frente principal de valor pro cliente — Fase 3.5 UI
6 <TenantHealthBanner/> informativo (lê tenants/{id}/health_status)
7 Página /setup checklist (CONTA / WHATSAPP / PAGAMENTO / OPERADORES / TEMPLATES)
8 Modal erro 402 ao enviar template (link pro Business Manager)
9 Card "Uso este mês" no dashboard (consome /api/wa/usage/current-month)
10 Frontend passar template_category em send-template (backend já aceita, frontend já tem o campo)
11 UI da fila pending_webhook_events (endpoints já prontos)
⚙️ Infra & validação
12 Cloud Scheduler em prod pra cron health-check (existe em staging com OIDC + Secret Manager — só replicar)
13 Firestore rules estritas em staging — investigar bug do snapshot wa_messages (WIP em firestore-rules-staging-strict.wip)
14 Validações Fase 4 ainda não testadas:
Mesmo wa_id em standard + coex como 2 entradas (precisa standard ativo)
Bulk reassign exclui canais coex
Badge de canal por linha na UI
Painel de perfil unificado
Auditoria sender_user_id != channel_owner_user_id em transferência
Isolamento multi-tenant via rules
📺 Sem urgência operacional
15 Re-screencast App Review — app está Live e funcional, perms aprovadas, cleanup feito. Roteiro em docs/APP_REVIEW_SCREENCAST_SCRIPT.md. Vale fazer pra prevenir review futura, mas não bloqueia nada.
🚀 Roadmap pós-Fase 2 (nada urgente, ficam pra quando cliente #2 fechar)
Onboarding self-service de tenant (super-admin UI)
Self-service signup do cliente final (landing → tenant criado)
Billing automation (Stripe/Asaas/Iugu)
White-label
Cross-tenant analytics
Backup/export per-tenant
Limites enforced por plano
Remover espelho wa_contacts.assigned_to/unread_count (dívida transitional documentada)