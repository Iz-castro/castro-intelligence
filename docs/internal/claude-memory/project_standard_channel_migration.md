---
name: project-standard-channel-migration
description: Migracao do numero para canal STANDARD (Cloud API); Embedded Signup standard FEITO+PROVADO (botao Cloud API, config 2342621062931210, 7195-7758 conectado E2E); decisoes e plano multi-empresa
metadata: 
  node_type: memory
  type: project
  originSessionId: dab2543b-9e4a-40cf-88c3-3d467d17781b
---

Jun/2026: migrando o numero oficial da empresa (Hubloc) para canal
**standard** (Cloud API, vira o default), descontinuando coexistence aos
poucos. Decisoes tomadas:

- **Embedded Signup do CRM e COEX-ONLY.** O front fixa
  `channel_type:"coexistence"` e usa `featureType:"whatsapp_business_app_onboarding"`
  (App.tsx ~1426-1499). NAO existe caminho de UI pra standard. O backend
  `/api/admin/embedded-signup/exchange` ate suporta standard, mas sem front
  e sem config_id standard na Meta. → standard HOJE so via **criacao manual**
  `POST /api/admin/channels` (channel_type=standard).
- **Caminho A (manual)** pra Hubloc: bot **LIGADO** (is_bot_enabled=true).
- **Billing (decidido):** a WABA do Hubloc FICA na conta/portfolio da Hubloc
  (NAO transfere). A Castro **compartilha a linha de credito** dela com essa
  WABA → a Meta cobra a Castro (managed billing consolidado) sem a Castro ser
  dona da WABA. A Castro tem linha de credito na Meta (confirmado). Resolve o
  131042. Acesso operacional: app Tech Provider 1434723791183375 compartilhado
  na WABA + token de System User com acesso a WABA. (CRM e portfolio-agnostico.)
- **Secret do Cloud Run `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID` fica VAZIO.**
  Com o secret setado, TODO canal standard envia pelo unico numero global
  (channel_service.py:186-193) — mata multi-standard. Vazio → cada standard
  usa o `access_token` do proprio doc (channel_service.py:195-201), roteado
  por channel_id. Decisao forward-compatible pra multi-empresa.
- **O POST manual NAO assina webhook nem registra PIN.** Assinar a mao via
  `POST /{waba_id}/subscribed_apps` (4 campos standard); registrar numero via
  `/{phone_number_id}/register` com PIN. `phone_routing` esse SIM e populado
  automatico por create_channel (validar que aponta pro tenant `hubloc`).
- CRM e **portfolio-agnostico** (conecta so por waba_id/phone_number_id/token).

**Pendente (cadastrar mais empresas com standard, sem colidir):**
1. ADR 0007 Fase 2 — `channels` → `tenants/{tid}/channels` + **default por
   tenant** (hoje `_default_channel_id` e o 1o standard global, channel_service.py:83-84).
2. Gargalo do **secret global** do standard (acima) — registrar no ADR 0007.
3. **Metodo B — FEITO e PROVADO (2026-06-05).** (A nota "COEX-ONLY" no topo deste
   arquivo esta DESATUALIZADA.) Embedded Signup standard esta LIVE: botao "☁️ Conectar
   numero (Cloud API)" (App.tsx:119 -> whatsapp-standard -> WhatsAppSignupModal
   channelType=standard, App.tsx:1730); endpoint `/api/admin/embedded-signup/config?type=standard`
   (admin/sup) devolve EMBEDDED_SIGNUP_CONFIG_ID_STANDARD=2342621062931210 (PLUGADO em prod,
   confirmado no env do Cloud Run 2026-07-01); `exchange` recebe channel_type=standard;
   `create_channel` (channel_service.py:238-241) carimba `tenant_id` do CONTEXTO atual + grava
   phone_routing -> serve pro tenant #2 self-service. Numero 7195-7758 foi conectado E2E por
   esse fluxo. Standard exige verificacao SMS/ligacao (chip) + `POST /{phone_id}/register` com
   PIN (rodado pelo CRM, Castro = Tech Provider).

**BLOQUEADO na Meta (2026-06-04):** ao tentar migrar o numero 3351-7604
(WABA Central Loc - Comercial) pro standard via Embedded Signup, a conta
estava RESTRITA por Politica Empresarial — motivo: o site no Perfil do
Gerenciador de Negocios nao foi encontrado. Deletada a WABA vazia
"Central Loc - Equipamentos" (restrita) e a Comercial ficou verde, mas a
"Test WhatsApp Business Account" tb estava restrita pelo mesmo motivo.
Site corrigido + **pedido de analise aberto**; Meta responde em ~24h
(esperar ate ~2026-06-05). Migracao standard PAUSADA ate a Meta liberar.
Lado do CRM PRONTO: botao ☁️ "Conectar numero (Cloud API)" deployado
EMBEDDED_SIGNUP_CONFIG_ID_STANDARD = **2342621062931210** ("Castro CRM
Standard Prod", config Cloud API criada na Meta 2026-06-05; rev
castro-crm-00143-j6q). Coex config = 2785379481799560. WHATSAPP_TOKEN/
PHONE_NUMBER_ID seguem VAZIOS (envio usa token do canal). Apos wipe manual
(2026-06-05), redeploy disparou bootstrap (recriou hubloc + setores +
admin rafaluisc@outlook.com). Bootstrap admin e o Rafa, NAO o izael.
Proximo: popup -> migrar numero -> PIN; depois conferir phone_routing +
secret vazio + teste.

**SUCESSO (2026-06-05):** numero +55 31 7195-7758 conectado como STANDARD.
phone_number_id=1199019616617623, canal id=2, nome "Castro Intelligene SAC"
(name_status PENDING_REVIEW, cosmetico). O embed standard deixa o numero
PENDING+VERIFIED; o passo final e `POST /{phone_id}/register` com PIN — a
Meta diz "contate seu parceiro", mas o PARCEIRO = a propria Castro (Tech
Provider), entao o register e rodado pelo CRM com o token do canal (PIN
124104) -> status CONNECTED. Canal velho orfao (phone 1081361255070495,
da 1a tentativa deletada na Meta) foi limpo (doc + phone_routing).
Health-check de billing da #10 (requer BSP) e cosmetico, NAO bloqueia envio.
**E2E VALIDADO (2026-06-05):** inbound (telefone->CRM) E outbound (CRM->
telefone) funcionando, com cartao MasterCard na WABA. **MIGRACAO STANDARD
COMPLETA.** Bug corrigido no caminho: `_resolve_webhook_channel` caia no
canal default quando o phone_id nao batia com canal -> coex de operador
(canal apagado) vazava pro canal standard. Removido o fallback: agora vai
pra pending_webhook_events (commit 1ab6aa4, rev castro-crm-00144). Coex
sendo desconectado pelos celulares (vai pra pending, inofensivo). Pendencias
menores: nome "Castro Intelligene SAC" tem typo + em review; 13 operadores
apagados re-provisionam em branco no login (re-setar role/depto); sem
templates ainda (necessario p/ iniciar conversa fora da janela 24h).

**2o numero standard — EM ANDAMENTO (retomar):** numero comercial da Hubloc
**3351-7604** (553133517604; era coex, WABA Central Loc - Comercial). A WABA
antiga foi **deletada no celular** na noite de 2026-06-06, MAS o **chip nao
estava no aparelho** -> registro adiado p/ quando o chip estiver no celular
(a verificacao do embed manda codigo por SMS/ligacao -> precisa do chip).
PLANO ao retomar: (1) chip 3351-7604 no celular; (2) CRM como admin -> botao
"Conectar numero (Cloud API)" -> Embedded Signup standard com 3351-7604; (3)
verificacao por codigo -> numero fica PENDING+VERIFIED; (4) Claude roda
`POST /{phone_id}/register` com PIN (usei 124104 antes) -> CONNECTED; (5)
conferir phone_routing->hubloc + channel_active=true; (6) DESATIVAR o numero
de TESTE 7195-7758 via API (`DELETE /api/admin/channels/{id}` ->
deactivate_channel; **NAO existe botao na UI pra canal standard — so coex**,
App.tsx:2082) p/ ficar um unico standard ativo (senao o default fica
ambiguo). Conversas de teste JA limpas (CRM zerado, infra mantida).
Obs: desativar no CRM = some do sistema; liberar o numero de vez exige tirar
da WABA na Meta (numero na Cloud API fica preso).

**Feature "lead gruda na vendedora" (ADR 0008) implementada+VALIDADA
(2026-06-05):** assume grava sale_owner_user_id/_uid no contato; fechamento
(manual via set_attendance_status OU cron close_stale_attendances 6h) reverte
**lead (contato) E atendimento (conversa)** pra dona de origem. Transferencia
em canal standard move o contato junto (also_lead) p/ o destino enxergar.
Fixes do dia: rev castro-crm-00144..00148. Ver docs/decisions/0008 e
docs/internal/2026-06-05.md.

Ver [[project-operator-isolation-lgpd]] e docs/decisions/0007.
