# 2026-06-10 — Fix: Embedded Signup v4 (WABA via session-info) + System User token

## Sintoma

Onboarding coex falhava com **"Nenhuma conta WhatsApp Business retornada pelo signup"**.
O `/exchange` logava `granted=<vazio>`; o `debug_token` voltava
`valid=True type=SYSTEM_USER scopes=[public_profile] granular=[]`.

O popup **funcionava** e conectava o número (aparecia **Conectado/Alta** no
WhatsApp Manager) — o erro era só na troca de credenciais no CRM.

## Causa raiz

O CRM extraía a WABA dos **`granular_scopes` do token** (padrão do Embedded
Signup **v3**). A Meta migrou para o **Embedded Signup v4**, que entrega
`waba_id`/`phone_number_id` na **mensagem `postMessage` `WA_EMBEDDED_SIGNUP`
(session-info)** do popup — e **não** mais nos `granular_scopes` (que no v4
voltam só com `public_profile`).

O frontend **não tinha** `addEventListener("message")` para capturar essa
mensagem → o CRM nunca lia a WABA, mesmo o popup concedendo o número.

Funcionou até ~maio porque o v3 ainda colocava a WABA nos `granular_scopes`.
Deadline da Meta para v2/v3 → v4: **15/out/2026** (feature type `coex` exige
migração manual).

### Hipóteses descartadas (todas falsas)
- "Re-onboard de número já conectado" → onboarding do zero falhava igual.
- Bloqueio/throttle/cooldown da Meta → probe ao vivo: saúde verde, `x-app-usage`
  0/0/0, `can_send_message=AVAILABLE`, `estimated_time_to_regain_access=0`.
- Remoção do `business_management` (8/mai) → coex funcionou **após** removê-lo.
- Regressão do commit 817e730 → `extras` do coex byte-idêntico ao de maio.

## Fix

**Frontend** (`frontend/src/App.tsx`):
- Listener `window.addEventListener("message")` captura `WA_EMBEDDED_SIGNUP` e
  guarda `waba_id` + `phone_number_id` num ref.
- O ref é enviado no `POST /api/admin/embedded-signup/exchange`.

**Backend** (`main.py`):
- `EmbeddedSignupExchange` aceita `phone_number_id` + `waba_id` (session-info).
- `/exchange` usa a WABA da session-info como fonte primária (fallback:
  `granular_scopes` v3).
- `wa_token = WHATSAPP_SYSTEM_USER_TOKEN or access_token` é usado para ler
  phone_numbers, assinar webhook, disparar `smb_app_data` e como `access_token`
  do canal — porque o token do popup (`public_profile`) não tem permissão.

**Config / infra** (`config.py` + Cloud Run):
- `WHATSAPP_SYSTEM_USER_TOKEN` lido do Secret Manager `castro-crm-system-user-token`
  (System User token long-lived do portfolio **Castro Operações**, acessa todas
  as WABAs onboardadas no app).
- Deploy: `--update-secrets WHATSAPP_SYSTEM_USER_TOKEN=castro-crm-system-user-token:latest`.
- SA `castro-crm-run@...` recebeu `roles/secretmanager.secretAccessor` no secret.

## Validação (prod, rev castro-crm-00157-dww)

```
Embedded Signup: WABA ID = 985540003931801 (fonte=session-info, system_user_token=True)
Embedded Signup concluido | waba=985540003931801 phone_id=1093519330516990 display=***6195
Embedded Signup: webhook subscription = True
Embedded Signup smb_app_data smb_app_state_sync OK
Embedded Signup smb_app_data history OK
POST /api/admin/embedded-signup/exchange -> 200 OK
```

Número ...6195 reconectado, canal criado no CRM, agenda sincronizada.

## Pendências

1. **Rotacionar `META_APP_SECRET`** + silenciar `httpx` (o logger do httpx loga as
   URLs da Graph API em INFO, expondo o app secret e tokens em texto puro no
   Cloud Logging — `oauth/access_token` e `debug_token` usam `APP_ID|SECRET` na
   query). Coordenar a rotação para não quebrar chamadas in-flight.
2. **Log de diagnóstico temporário** em `main.py` (`Embedded Signup debug_token | ...`)
   — agora útil (mostra `fonte`/`system_user_token`); decidir manter ou limpar.
3. **Onboarding de número NOVO (WABA nova):** confirmar que o System User token
   alcança a WABA recém-criada. Se der `#200` em "Erro ao buscar numeros", a WABA
   nova precisa ser atribuída ao System User (ou dar acesso de business/portfólio).

## Arquitetura

Managed billing → todas as WABAs no portfólio Castro Operações → **um** System
User token (Secret Manager) acessa todas. O token-por-canal (guardado no Firestore)
era herança da era passthrough e se perdia no `wipe_all_collections.py --purge-channels`;
o token global sobrevive a wipe (fica no Secret Manager).
