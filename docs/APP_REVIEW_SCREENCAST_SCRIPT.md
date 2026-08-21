# Roteiro do Screencast — App Review da Meta (2ª resubmissão)

> **Status em 2026-08-21:** a URL e a região citadas neste roteiro são do
> **projeto ANTIGO de São Paulo** (`southamerica-east1`) e induzem erro se
> copiadas. A produção hoje é o projeto `project-4a851bf9-f475-418c-800` na
> região **`us-west1` (Oregon)**. Antes de gravar: pegue a URL vigente com
> `gcloud run services describe castro-crm --region us-west1 --project
> project-4a851bf9-f475-418c-800` e substitua as duas ocorrências de
> `castro-crm-286866630844.southamerica-east1.run.app` (§1.1 e slide da Seção 5),
> além da menção a `southamerica-east1` no slide da Seção 0. O login de teste
> (`teste1@centralloc.com.br`) também precisa ser reconferido no tenant `hubloc`
> antes da gravação. ⚠ Não há registro aqui de que o re-screencast tenha sido
> gravado/submetido — verificar com o PO.

**Projeto:** Castro Intelligence CRM (Hubloc)
**App ID:** 1434723791183375
**Business ID:** 877897608035564 (Tech Provider verificado)
**Permissões alvo desta resubmissão:** `whatsapp_business_messaging`,
`whatsapp_business_management`
**Duração alvo:** 5 a 6 minutos
**Idioma:** narração em inglês + legendas em inglês visíveis. UI do
CRM permanece em português, mas tooltips/legendas explicam cada
elemento conforme aparece (atende ao guia de gravação da Meta).

> **Histórico:** na revisão de 2026-05-08, a Meta aprovou
> `whatsapp_business_messaging` e `whatsapp_business_management` em
> Advanced Access e renovou `public_profile`. `business_management`
> foi reprovada — é permission de Ads Manager (impressions,
> conversions, ad spend), não de Embedded Signup do WhatsApp.
>
> Decididas como **fora do escopo** na mesma sessão:
> - `manage_app_solution` — não se aplica (não somos intermediário de
>   Solution Partners; somos Tech Provider direto pra clientes B2B).
> - `whatsapp_business_manage_events` — Conversions API for WhatsApp
>   não está implementada; reavaliar quando/se houver feature de
>   tracking de ROI pra ads click-to-WhatsApp.
>
> O screencast anterior também foi marcado como "não alinhado ao caso
> de uso completo"; este roteiro corrige cobrindo o fluxo end-to-end
> de consentimento + uso de cada uma das 2 permissões aprovadas.

---

## 1. Setup antes de começar a gravar

### 1.1. Ambiente

- [ ] CRM atualizado em produção: `https://castro-crm-286866630844.southamerica-east1.run.app` (revisão pós-deploy desta atualização).
- [ ] Login de teste válido: `teste1@centralloc.com.br` · senha `teste1` · role **admin**.
- [ ] Canal ativo: WABA CentralLoc.
- [ ] Celular pessoal disponível pra simular cliente final.
- [ ] Templates aprovados no WhatsApp Manager: ao menos `hello_world`.
- [ ] Conta Facebook disponível pra fazer o login no popup do Embedded Signup (admin do Business Portfolio CentralLoc).

### 1.2. Ferramentas de gravação

- **Loom** (grátis, mais fácil) ou **OBS Studio** (mais controle).
- Se a Meta exige inglês, ative captions automáticas no CapCut e edite
  pra inglês. Ou narre direto em inglês.

### 1.3. Preparar a "conversa de demonstração"

1. Do seu celular pessoal, mande a primeira mensagem pro número
   business da CentralLoc: `"Hello, I'm interested in a property."`
2. Aguarde aparecer no CRM.
3. Assume essa conversa e deixa o chat aberto.

### 1.4. Preparar abas

- Aba 1: CRM Hubloc, logado como `teste1`.
- Aba 2: WhatsApp Manager — `https://business.facebook.com/wa/manage/message-templates` com templates aprovados.
- Aba 3 (opcional): tela do celular espelhada (scrcpy, AirDroid Cast).

### 1.5. Privacidade

- Não expanda lista de contatos além do necessário — pode mostrar
  números reais de clientes da CentralLoc. Use blur no CapCut na edição
  se aparecer por acidente.

---

## 2. Estrutura do vídeo

### Seção 0 — Intro (0:00 – 0:25)

**Tela:** slide de texto em inglês sobre fundo neutro.

**Conteúdo do slide:**

```
Castro Intelligence CRM
WhatsApp Business Platform integration for Hubloc real estate

App ID:        1434723791183375
Business ID:   877897608035564
Status:        Tech Provider verified

Permissions in this submission:
- whatsapp_business_messaging  (Advanced Access requested)
- whatsapp_business_management (Advanced Access requested)

Authentication architecture
- Operators sign in via Firebase Authentication (independent from Meta).
- Meta OAuth (Embedded Signup) is used only when an admin connects
  a new WhatsApp Business Account to the CRM.
- All Graph API calls AFTER the OAuth code exchange are server-to-server
  (FastAPI backend on Google Cloud Run, region southamerica-east1).
```

**Narração (inglês):**

> "This submission requests Advanced Access for two WhatsApp
> permissions used end-to-end in our CRM. We will demonstrate the full
> consent flow and the complete use case experience for each one. Note
> that all Graph API calls after the Embedded Signup OAuth exchange
> are server-to-server — the Meta login front-end is only visible
> during onboarding, shown later in this video."

---

### Seção 1 — CRM login (0:25 – 0:45)

**Tela:** página de login do CRM.

**Passos:**
1. URL visível na barra do navegador.
2. Digita `teste1@centralloc.com.br` e senha `teste1`.
3. Clica em "Entrar" (tooltip em inglês: *"Sign in"*).
4. Tela principal do CRM aparece.

**Narração:**

> "Operators authenticate via Firebase Authentication, which is
> independent from Meta login. The Meta OAuth flow appears only during
> the Embedded Signup process shown in section 4."

---

### Seção 2 — `whatsapp_business_messaging` (0:45 – 2:30)

**Objetivo:** demonstrar o caso de uso completo — recepção + envio de
mensagem livre (two-way messaging) entre business e cliente.

#### 2.1. Receber mensagem inbound (0:45 – 1:20)

**Tela:** CRM com a conversa de teste aberta.

**Passos:**
1. Mostra a lista de conversas. Conversa de teste no topo.
2. Do celular pessoal, envia: `"What regions are available?"`
3. No CRM, mensagem aparece em tempo real. Recipient handle visível
   (número/nome do contato no header da conversa).

**Narração:**

> "A customer sends a message to the business WhatsApp number. Our
> webhook at POST /webhook receives the event from Meta, validates the
> HMAC signature, and routes the message to the assigned operator's
> conversation. The CRM updates the chat in real time via a Firestore
> snapshot listener."

#### 2.2. Responder pelo CRM (1:20 – 2:00)

**Passos:**
1. Clica no campo de texto do chat (tooltip em inglês: *"Type a
   reply"*).
2. Digita: `"Hi! We have properties in Downtown, South Zone, and
   North Zone."`
3. Clica no ícone de enviar (tooltip: *"Send"*).
4. Mensagem aparece no chat com status `sent`, depois `delivered`,
   depois `read`.
5. **Mostra a mensagem chegando no celular** (câmera/scrcpy) — handle
   do destinatário (número do business + nome do contato) visível na
   tela do celular.

**Narração:**

> "The operator types a reply directly in the CRM. The backend posts
> the message to Meta's Graph API at POST /{PHONE_NUMBER_ID}/messages
> using the whatsapp_business_messaging permission. The message
> arrives on the customer's WhatsApp. Delivery status updates come
> back via the statuses webhook field and update the message bubble
> in real time."

#### 2.3. Confirmar bidireção (2:00 – 2:30)

**Passos:**
1. Do celular, envia: `"Downtown, please."`
2. CRM mostra a mensagem no chat.
3. Operador responde: `"Great. I will send you the available units
   shortly."`
4. Mensagem chega no celular.

**Narração:**

> "Bidirectional messaging confirmed. Both directions are persisted in
> Firestore with full audit trail — sender ID, timestamps, delivery
> status, and channel ownership."

---

### Seção 3 — `whatsapp_business_management` (2:30 – 4:00)

**Objetivo:** demonstrar leitura da WABA e envio de template.

#### 3.1. Templates na Meta (2:30 – 2:55)

**Tela:** aba 2 — WhatsApp Manager.

**Passos:**
1. Mostra lista de templates aprovados (`hello_world`, `br_convite_grupo`, etc).
2. Destaca coluna "Status: Approved".

**Narração:**

> "Templates are created, submitted, and approved inside Meta's
> WhatsApp Manager — outside our app. Our CRM reads this approved
> list using the whatsapp_business_management permission to make sure
> operators only send templates that Meta currently accepts."

#### 3.2. Abrir template picker no CRM (2:55 – 3:20)

**Tela:** volta pra aba 1 (CRM), chat aberto.

**Passos:**
1. No header do chat, clica no ícone ⋮ (tooltip: *"More actions"*).
2. Clica em "Enviar template" (tooltip: *"Send template"*).
3. Modal abre. Mostra "Carregando templates aprovados da Meta..."
   (tooltip: *"Loading approved templates from Meta"*).
4. Templates aparecem agrupados por categoria (Marketing, Utility).

**Narração:**

> "The CRM fetches approved templates via the backend endpoint GET
> /api/wa/templates, which internally calls Meta's Graph API at GET
> /{WABA_ID}/message_templates using the whatsapp_business_management
> permission. Templates are grouped by category."

#### 3.3. Selecionar template e enviar (3:20 – 4:00)

**Passos:**
1. Clica em `hello_world`.
2. Mostra preview do template.
3. Clica em "Enviar template" (tooltip: *"Send template"*).
4. Modal fecha.
5. Mensagem aparece no chat: `[template: hello_world] Hello, World!`.
6. Mensagem chega no celular (câmera apontada — handle visível).

**Narração:**

> "The operator selects an approved template, fills any placeholder
> variables, and sends it. The backend posts to Meta's Graph API with
> the template payload; the message is rendered on the recipient's
> WhatsApp with the approved formatting. The send is audit-logged in
> our backend with the WA_SEND_TEMPLATE event, including which
> operator sent it and which template was used."

---

### Seção 4 — Embedded Signup: full Meta login + consent flow (4:00 – 5:15)

**Objetivo crítico (foi o que faltou no screencast anterior):
demonstrar o fluxo de login Meta COMPLETO, com o usuário concedendo
explicitamente cada permission.**

#### 4.1. Admin inicia Embedded Signup no CRM (4:00 – 4:15)

**Tela:** CRM, menu de configurações administrativas.

**Passos:**
1. Clica no ícone de engrenagem (tooltip: *"Admin settings"*).
2. Abre seção "Conectar WhatsApp" (tooltip: *"Connect WhatsApp"*).
3. Modal abre com botão "Iniciar Embedded Signup" (tooltip: *"Start
   Embedded Signup"*).
4. Clica.

**Narração:**

> "An administrator can onboard a new WhatsApp Business Account to the
> CRM. The CRM opens Meta's Facebook Login popup using the official
> Embedded Signup flow with featureType
> whatsapp_business_app_onboarding."

#### 4.2. Popup da Meta — Facebook Login (4:15 – 4:35)

**Tela:** popup do Facebook que abriu.

**Passos:**
1. **Tela de login do Facebook** (mostrar mesmo se já estiver logado —
   se necessário, deslogue antes pra forçar). Email/senha digitados
   pelo admin do Business Portfolio.
2. Clica em "Log in" (tooltip: *"Log in to Facebook"*).

**Narração:**

> "The administrator logs in with their Facebook account. This
> Facebook account must be an admin of the Business Portfolio that
> owns the WhatsApp Business Account being connected."

#### 4.3. Tela de consentimento — usuário concede as permissions (4:35 – 5:00)

**Tela:** tela de "Continuar como [nome] / Selecione os ativos / Editar
permissões" do popup Meta.

**Passos:**
1. **Tela "Selecione seu portfólio empresarial"** — admin escolhe o
   portfólio CentralLoc. Tela mostra explicitamente o nome do
   portfólio.
2. **Tela "Selecione uma conta do WhatsApp Business"** — admin escolhe
   a WABA. Mostra ID e nome.
3. **Tela "Permissions / Editar permissões"** (essa é a tela-chave —
   pause aqui ~3 segundos pra Meta visualizar). Mostra a lista de
   permissões que o app está pedindo:
   - "Manage your WhatsApp Business accounts and message templates"
     (= `whatsapp_business_management`)
   - "Send and receive WhatsApp messages on behalf of your business"
     (= `whatsapp_business_messaging`)
4. Admin clica em "Continue" / "Avançar" — concede explicitamente.

**Narração (importante — referência explícita às 2 perms):**

> "This is the consent screen. The admin reviews the two permissions
> the app is requesting: whatsapp_business_management — to read the
> WABA configuration and approved message templates — and
> whatsapp_business_messaging — to send and receive messages on behalf
> of the business. The admin grants both by clicking Continue."

#### 4.4. Fluxo conclui com sucesso (5:00 – 5:15)

**Tela:** popup fecha → CRM mostra confirmação.

**Passos:**
1. Popup fecha.
2. Modal do CRM exibe "Conexão realizada com sucesso!" com:
   - WABA ID
   - Phone Number ID
   - Display phone number
   - Verified name
   - Status

**Narração:**

> "After the admin grants consent, Meta returns an authorization code
> to our front-end. The CRM forwards the code to our backend, which
> exchanges it server-to-server for an access token, fetches the
> phone numbers on the WABA, and subscribes our app to webhooks on
> the WhatsApp Business Account. From this point, all interactions
> are server-to-server and not visible in the front-end."

---

### Seção 5 — Closing / Server-to-server note (5:15 – 5:45)

**Tela:** slide final em inglês.

**Conteúdo do slide:**

```
Summary of demonstration

[checkmark] whatsapp_business_messaging
   Two-way messaging shown at 0:45–2:30
   - Inbound webhook routing
   - Outbound POST /{PHONE_ID}/messages
   - Delivery status updates

[checkmark] whatsapp_business_management
   Template list and send shown at 2:30–4:00
   - GET /{WABA_ID}/message_templates
   - POST /{PHONE_ID}/messages with template payload
   - Audit log entry per template send

Consent flow shown at 4:00–5:15
   - Full Meta login
   - Business Portfolio + WABA selection
   - Explicit grant of both permissions

Backend architecture
- Frontend Meta Login appears ONLY during Embedded Signup.
- All Graph API calls after the OAuth code exchange are
  server-to-server (FastAPI on Google Cloud Run).
- Access tokens stored encrypted in Firestore, auto-refreshed
  before expiry.

Test account
URL:   https://castro-crm-286866630844.southamerica-east1.run.app
Email: teste1@centralloc.com.br
Role:  admin

Contact: contato@castrointelligence.com.br
```

**Narração:**

> "To summarize: this video demonstrates both permissions end-to-end
> with the full consent flow. All Graph API calls after the Embedded
> Signup code exchange are server-to-server and therefore not visible
> in the front-end. Test account credentials are listed for the
> reviewer. Thank you for reviewing."

---

## 3. Notas para colar na submissão

Ao reenviar cada permissão na página de App Review, use estes
trechos. **Reforce o disclaimer server-to-server na nota** — é uma
exigência explícita da Meta no feedback de 2026-05-08.

### 3.1. `whatsapp_business_messaging`

```
Demonstrated at 0:45–2:30 in the attached screencast.

Use case: two-way messaging between the business and its customers
through the CRM web interface.

Inbound (0:45–1:20): a customer sends a message to the business
WhatsApp number. Our webhook (POST /webhook on FastAPI backend)
receives the event from Meta, validates the X-Hub-Signature-256 HMAC
using the App Secret, and routes the message to the assigned
operator's conversation. The CRM front-end shows the new message in
real time via a Firestore snapshot listener.

Outbound (1:20–2:30): the operator types a reply directly in the
CRM. The front-end calls the backend, which posts to Meta's Graph
API at POST /{PHONE_NUMBER_ID}/messages. Delivery status updates
return through the statuses field of the webhook and update the
message bubble in the UI.

Server-to-server note: all Graph API calls (send message, status
updates) are made from our FastAPI backend hosted on Google Cloud
Run. The Meta front-end login is not used for this permission —
only Firebase Authentication is used to log the operator into the
CRM.

Recipient handles are visible during both inbound and outbound
demonstrations as required by the previous review note.
```

### 3.2. `whatsapp_business_management`

```
Demonstrated at 2:30–4:00 in the attached screencast.

Use case: enabling operators to send pre-approved message templates
to customers from inside the CRM, with the template list always in
sync with what Meta has currently approved.

Template management (2:30–2:55): templates are created, submitted,
and approved inside Meta's WhatsApp Manager — outside our app.

Template list inside CRM (2:55–3:20): the operator opens the
template picker. The CRM front-end calls the backend endpoint
GET /api/wa/templates, which internally calls Meta's Graph API at
GET /{WABA_ID}/message_templates using whatsapp_business_management.
Templates are grouped by category (Marketing, Utility,
Authentication).

Template send (3:20–4:00): the operator selects an approved
template, fills any placeholder variables, and sends. The backend
posts to POST /{PHONE_NUMBER_ID}/messages with the template payload.
The send is audit-logged with the WA_SEND_TEMPLATE event, including
the operator ID and template name.

Embedded Signup consent (4:00–5:15): an admin onboards a new
WhatsApp Business Account using Meta's Embedded Signup with
featureType=whatsapp_business_app_onboarding. The video shows the
full Meta login flow, the Business Portfolio and WABA selection
screens, and the consent screen where the admin explicitly grants
this permission. After consent, the backend exchanges the OAuth
code server-to-server for an access token and reads the WABA
configuration.

Server-to-server note: all Graph API calls
(template list, template send, post-OAuth token exchange, WABA
queries, webhook subscription) are made from our FastAPI backend on
Google Cloud Run. The Meta front-end login is visible only during
the Embedded Signup flow shown in section 4.
```

---

## 4. Checklist antes de submeter

- [ ] Vídeo exportado em MP4 ou MOV, ≤100MB.
- [ ] Narração em inglês audível **e** legendas em inglês visíveis
      o vídeo todo.
- [ ] Tooltips em inglês explicando elementos da UI portuguesa
      conforme aparecem.
- [ ] Handle/número do destinatário visível em todos os segmentos
      de envio (atende ao feedback anterior).
- [ ] Mensagens de outros clientes reais não aparecem (ou estão
      blurradas no CapCut).
- [ ] **Tela de consent screen do Meta visível e pausada ~3s**
      (atende ao feedback "user granting access to the permission").
- [ ] **Embedded Signup conclui com sucesso** (popup fecha, CRM
      mostra "Conexão realizada com sucesso!"). Sem erro #2655111
      esperado, já que as 2 perms estão aprovadas Advanced.
- [ ] Cada permission tem nota técnica + timestamp referenciado +
      disclaimer server-to-server.
- [ ] Política de Privacidade configurada em Settings > Basic.
- [ ] Categoria do app preenchida.
- [ ] URL do site (plataforma) adicionada em Settings > Basic.

---

## 5. Pré-requisito: Configurador da Meta

Antes de gravar, **conferir o Configurador do Embedded Signup**
(referenciado pela env var `EMBEDDED_SIGNUP_CONFIG_ID`):

1. Abrir `https://business.facebook.com/wa/manage` → Account Tools → API setup → Configurações de assinatura embed (caminho exato pode variar).
2. Localizar o Configurador correspondente ao `EMBEDDED_SIGNUP_CONFIG_ID` em uso.
3. **Verificar se `business_management` está nos scopes solicitados.**
   Se sim, **remover** — não foi aprovada e não é necessária.
4. Garantir que o Configurador pede só:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
5. Salvar. Testar o fluxo Embedded Signup em staging — popup deve
   completar sem o erro #2655111.

Se o Configurador estava pedindo `business_management` e o usuário
era admin do Portfolio com a permission concedida, o popup
funcionava (em modo standard access, com user de teste). Mas em
produção pra qualquer admin externo, faltava Advanced Access. Como
descartamos `business_management`, basta removê-la do Configurador.

---

## 6. Tips finais

- Trechos ruins → cortar e remontar no **CapCut** ou **Clipchamp**.
- Legendas em inglês sobre narração pt-BR → **CapCut → Captions →
  Auto-Captions** (configurar idioma como inglês). Se a narração já
  for em inglês, melhor.
- Meta valoriza **clareza e correspondência ao caso de uso** mais que
  produção cinematográfica. O feedback de 2026-05-08 foi explicitamente
  sobre conteúdo (faltou consent screen + caso de uso completo), não
  qualidade visual.

---

## 7. Apêndice — feedback da Meta (2026-05-08) e como este roteiro
endereça cada ponto

| Ponto do feedback Meta | Onde este roteiro endereça |
|---|---|
| "Fluxo de login completo da Meta" | Seção 4.2 — login Facebook completo |
| "Usuário concedendo acesso à permissão" | Seção 4.3 — consent screen pausada ~3s, narração nomeia explicitamente as 2 perms |
| "Experiência completa do caso de uso" | Seções 2 e 3 — inbound + outbound msg + template list + template send, end-to-end |
| "UI em inglês, legendas, tooltips explicando elementos" | Tooltips em inglês marcados em todas as seções; narração em inglês; legendas em inglês ativas o vídeo todo |
| "Server-to-server: indicar no envio" | Seções 0 (intro slide), 4.4 e 5 (closing slide); disclaimer em cada nota de submissão na §3 |
