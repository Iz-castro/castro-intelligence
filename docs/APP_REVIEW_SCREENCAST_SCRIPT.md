# Roteiro do Screencast — App Review da Meta (resubmissão)

**Projeto:** Castro Intelligence CRM (Hubloc)
**App ID:** 1434723791183375
**Business ID:** 877897608035564 (Tech Provider verificado)
**Permissões solicitadas:** `whatsapp_business_messaging`, `whatsapp_business_management`, `business_management`
**Duração alvo:** 5 a 6 minutos
**Idioma:** narração em inglês OU português com legendas em inglês sobrepostas

---

## 1. Setup antes de começar a gravar

### 1.1. Ambiente

- [ ] CRM atualizado em produção: `https://castro-crm-286866630844.southamerica-east1.run.app` (revisão atual `castro-crm-00077-qls` ou superior).
- [ ] Login de teste válido: `teste1@centralloc.com.br` · senha `teste1` · role **admin**.
- [ ] Canal ativo: WABA CentralLoc (não precisa trocar pra número de teste Meta).
- [ ] Celular pessoal disponível pra simular cliente (você ou Izael).
- [ ] Templates aprovados no WhatsApp Manager: ao menos `hello_world`. Se quiser mostrar variáveis, criar um novo com `{{1}}` `{{2}}` e aguardar aprovação.

### 1.2. Ferramentas de gravação

Escolha uma:
- **Loom** (grátis, mais fácil, já compartilha link)
- **OBS Studio** (mais controle)
- **Windows Game Bar** — `Win+G`

### 1.3. Preparar a "conversa de demonstração"

1. Do seu celular pessoal, mande a primeira mensagem pro número business da CentralLoc: `"Hello, I'm interested in a property."`
2. Aguarde ela aparecer no CRM (pode cair na view "Novos" ou "Meus").
3. Assume essa conversa (se necessário) e deixa o chat aberto.

### 1.4. Preparar abas

- Aba 1: CRM Hubloc, logado como `teste1`.
- Aba 2: WhatsApp Manager da Meta — `https://business.facebook.com/wa/manage/message-templates` com os templates abertos.
- Aba 3 (opcional): Celular na câmera ou tela espelhada (scrcpy, AirDroid Cast).

### 1.5. Privacidade

- Durante a gravação, **evite expandir a lista de contatos** mais que o necessário — pode mostrar nomes e números de clientes reais da CentralLoc.
- Se a lista aparecer por acaso, use o CapCut na edição pra aplicar **mosaico/blur** na barra lateral.

---

## 2. Estrutura do vídeo

### Seção 0 — Intro (0:00 – 0:20)

**Tela:** slide de texto em inglês sobre fundo neutro.

**Conteúdo do slide:**

```
Castro Intelligence CRM
WhatsApp Business Platform integration for Hubloc real estate

App ID:        1434723791183375
Business ID:   877897608035564
Status:        Tech Provider verified

Permissions requested:
- whatsapp_business_messaging
- whatsapp_business_management
- business_management
```

**Legenda/Narração:**

> "This submission requests Advanced Access for three permissions needed for our WhatsApp Coexistence and Cloud API integration."

---

### Seção 1 — CRM Login (0:20 – 0:40)

**Tela:** página de login do CRM.

**Passos:**
1. Mostra a URL na barra do navegador.
2. Digita `teste1@centralloc.com.br` e senha `teste1`.
3. Clica em "Entrar".
4. A tela principal do CRM aparece.

**Legenda/Narração:**

> "Operators authenticate via Firebase Authentication — independent from Meta login. The Meta OAuth flow is only used during the Embedded Signup process shown at the end of this video."

---

### Seção 2 — `whatsapp_business_messaging` (0:40 – 2:10)

**Objetivo:** demonstrar envio e recebimento de mensagem livre (two-way messaging).

#### 2.1. Receber mensagem inbound (0:40 – 1:10)

**Tela:** CRM com a conversa de teste aberta.

**Passos:**
1. Mostra a lista de conversas. A conversa de teste está visível no topo.
2. Do celular, envia mais uma mensagem: `"What regions are available?"`
3. No CRM, mensagem aparece em tempo real no chat.

**Legenda/Narração:**

> "A customer sends a message to our business WhatsApp number. The webhook (POST /webhook) receives the event, validates it via HMAC signature, and routes the message to the assigned operator's conversation in real-time via Firestore snapshot."

#### 2.2. Responder pelo CRM (1:10 – 1:50)

**Tela:** CRM com o chat aberto.

**Passos:**
1. Clica no campo de texto do chat.
2. Digita: `"Hi! We have properties in Downtown, South Zone, and North Zone."`
3. Clica no ícone de enviar.
4. Mostra a mensagem sendo adicionada ao chat com status `sent`.
5. Mostra a mensagem chegando no celular (câmera apontada ou tela espelhada).

**Legenda/Narração:**

> "The operator replies directly from the CRM. The message is sent to Meta's Graph API at POST /{PHONE_ID}/messages and delivered to the customer's WhatsApp. Delivery status updates come back via webhook statuses."

#### 2.3. Confirmar ida e volta (1:50 – 2:10)

**Passos:**
1. Do celular, envia: `"Downtown, please."`
2. No CRM, mensagem aparece no chat.

**Legenda/Narração:**

> "Bidirectional messaging verified. Both inbound and outbound messages are persisted in Firestore with full audit trail including sender ID, timestamps, and delivery status."

---

### Seção 3 — `whatsapp_business_management` (2:10 – 4:00)

**Objetivo:** demonstrar descoberta e envio de template.

#### 3.1. Templates na Meta (2:10 – 2:40)

**Tela:** aba 2 — WhatsApp Manager da Meta.

**Passos:**
1. Mostra a lista de templates aprovados (`hello_world`, `br_convite_grupo`, `compre_com_a_gente`, etc).
2. Destaca a coluna "Status: Ativo / Approved".

**Legenda/Narração:**

> "Templates are created, submitted, and approved in Meta's WhatsApp Manager. Our CRM reads this list through the Graph API endpoint GET /{WABA_ID}/message_templates to show operators only templates currently approved by Meta."

#### 3.2. Abrir template picker no CRM (2:40 – 3:10)

**Tela:** volta pra aba 1 (CRM), chat aberto.

**Passos:**
1. No header do chat, clica no ícone de 3 pontinhos (⋮).
2. No menu, clica em **"Enviar template"**.
3. Modal abre. Mostra "Carregando templates aprovados da Meta...".
4. Templates aparecem listados por categoria (Marketing, Utility).

**Legenda/Narração:**

> "The CRM fetches the approved templates via GET /api/wa/templates, which internally calls Meta's Graph API using the whatsapp_business_management permission. Templates are grouped by category — Marketing, Utility, and Authentication."

#### 3.3. Selecionar template e enviar (3:10 – 3:50)

**Passos:**
1. Clica em `hello_world` (ou outro template aprovado).
2. Mostra o preview do template (header, body, buttons se houver).
3. Se o template tem variáveis, preenche cada input.
4. Clica em "Enviar template".
5. Modal fecha.
6. Mensagem aparece no chat do CRM como `[template: hello_world] <conteúdo>`.
7. Mensagem chega no celular (câmera apontada).

**Legenda/Narração:**

> "The operator selects an approved template, fills any placeholder variables, and sends. The CRM posts to POST /{PHONE_ID}/messages with the template payload. The message is rendered by WhatsApp on the recipient's device with the template's approved formatting. The send is audit-logged in our backend with the WA_SEND_TEMPLATE event."

---

### Seção 4 — `business_management` + Embedded Signup (4:00 – 5:00)

**Objetivo:** demonstrar o fluxo de Embedded Signup até o ponto do erro.

#### 4.1. Abrir Embedded Signup no CRM (4:00 – 4:20)

**Tela:** CRM, menu Configurações.

**Passos:**
1. Clica no ícone de engrenagem (⚙).
2. Menu abre. Clica em "Conectar WhatsApp" (ou equivalente).
3. Modal abre com botão "Iniciar conexão" (ou similar).
4. Clica no botão.

**Legenda/Narração:**

> "Administrators can onboard new business WhatsApp accounts via Meta's Embedded Signup. The CRM opens Meta's Facebook Login popup using featureType whatsapp_business_app_onboarding for Coexistence mode."

#### 4.2. Popup da Meta (4:20 – 4:50)

**Tela:** popup do Facebook que abriu.

**Passos:**
1. Mostra a tela de login do Facebook (se precisar autenticar).
2. Após logar, aparece a tela "Selecione os ativos de negócios para compartilhar".
3. Seleciona o portfólio empresarial.
4. Clica em "Conectar um app do WhatsApp Business".
5. Insere um número de WhatsApp Business na caixa de texto.
6. Clica "Avançar".

**Legenda/Narração:**

> "The user authenticates with their Facebook account, selects the business portfolio, chooses Coexistence onboarding, and enters the WhatsApp Business phone number to connect."

#### 4.3. Erro #2655111 (4:50 – 5:00)

**Tela:** popup mostra o erro.

**Passos:**
1. Mensagem aparece: `"O app do parceiro não tem as permissões de mensagens e Gerenciamento do WhatsApp Business avançadas que são necessárias..."` ou `#2655111`.
2. Pausa alguns segundos no erro pra ser lido.

**Legenda/Narração:**

> "This error #2655111 is the expected behavior — it confirms that the app needs Advanced Access on the whatsapp_business_messaging and whatsapp_business_management permissions to complete the onboarding. This App Review submission is specifically intended to unlock that."

---

### Seção 5 — Closing / Server-to-server note (5:00 – 5:30)

**Tela:** slide final em inglês.

**Conteúdo do slide:**

```
Summary of demonstration

✓ whatsapp_business_messaging
  Two-way messaging shown at 0:40–2:10

✓ whatsapp_business_management
  Template list and send shown at 2:10–4:00

✓ business_management
  Embedded Signup flow shown at 4:00–5:00

Backend architecture

- Frontend Meta Login appears only during Embedded Signup (4:00–5:00)
- All Graph API calls after the OAuth code exchange are server-to-server
- Access tokens are stored in Firestore and auto-refreshed before expiry

Test account

URL:   https://castro-crm-286866630844.southamerica-east1.run.app
Email: teste1@centralloc.com.br
Role:  admin

Contact: contato@castrointelligence.com.br
```

**Legenda/Narração:**

> "To summarize: this video demonstrates the three permissions end-to-end. All Graph API calls after the Embedded Signup code exchange are server-to-server and not visible in the frontend. Thank you for reviewing."

---

## 3. Notas para colar na submissão

Ao reenviar cada permissão na página de App Review, use estes trechos:

### 3.1. `whatsapp_business_messaging`

```
Demonstrated at 0:40–2:10 in the attached screencast.

Inbound: a customer sends a message to the business WhatsApp number.
Webhook delivers the event to the CRM, which routes it to the assigned
operator's conversation.

Outbound: the operator types a reply in the CRM interface. The message
is sent via POST /{PHONE_ID}/messages to Meta's Graph API and arrives
at the customer's WhatsApp. Delivery status is updated via the statuses
webhook field.

Both sides of the exchange are shown with the handle/account visible,
as requested in the previous review note.
```

### 3.2. `whatsapp_business_management`

```
Demonstrated at 2:10–4:00 in the attached screencast.

Template management: shown at 2:10–2:40 in Meta's WhatsApp Manager,
where templates are created, submitted, and approved outside our app.

Template usage inside CRM: at 2:40–3:10, the operator opens the
template picker modal. The CRM calls GET /{WABA_ID}/message_templates
using the whatsapp_business_management permission to fetch currently
approved templates.

Template send: at 3:10–3:50, the operator selects a template, fills
any variables, and sends it to the test number. The message is rendered
by WhatsApp on the recipient's device.
```

### 3.3. `business_management`

```
Demonstrated at 4:00–5:00 in the attached screencast.

Our app uses business_management to read the customer's Business
Portfolio during Embedded Signup (featureType:
whatsapp_business_app_onboarding) and to subscribe our app to webhooks
on the customer's WhatsApp Business Account after the OAuth code
exchange completes.

The video shows the full Meta Login popup flow up to the point where
error #2655111 is displayed — which confirms the Advanced Access
requirement this review intends to unlock.

All API calls after the OAuth code exchange are server-to-server from
our FastAPI backend (hosted on Google Cloud Run). The frontend Meta
login only appears during this Embedded Signup flow.
```

---

## 4. Checklist antes de submeter

- [ ] Vídeo exportado em MP4 ou MOV, máximo 100MB (limite da Meta).
- [ ] Legendas em inglês visíveis ou narração em inglês audível.
- [ ] Handle/número do destinatário visível nos segmentos de envio.
- [ ] Mensagens de clientes reais não aparecem (ou estão blurradas).
- [ ] Cada permissão tem nota técnica e timestamp referenciado.
- [ ] Política de Privacidade configurada no App Dashboard.
- [ ] Categoria do app preenchida.
- [ ] URL do site (plataforma) adicionada em Settings > Basic.

---

## 5. Tips finais

- Se a gravação ficar com trechos ruins, pode cortar e remontar no **CapCut** ou **Clipchamp** — ambos gratuitos e bem fáceis.
- Para adicionar legendas em inglês sobre narração em português, use o **CapCut → Captions → Auto-Captions** e edite o idioma.
- Não se preocupe com produção — a Meta valoriza **clareza e correspondência ao que foi descrito nas notas**, não qualidade cinematográfica.
- Se qualquer seção der errado durante a gravação, grave só essa seção de novo e emende — ninguém vai perceber.
