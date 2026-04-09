# Proposta Tecnica: Modulo de Comunicacao Interna Integrada (Hubloc CRM)

**Preparado por:** Castro Intelligence
**Cliente:** Hubloc - Locacao de Equipamentos (dominio workspace: `@centralloc.com.br`)
**Data:** 23 de Marco de 2026
**Atualizado em:** 25 de Marco de 2026

---

## 1. Resumo Executivo

Esta proposta visa a implementacao de um **Painel de Comunicacao Interna** dentro do CRM da Hubloc. O painel sera um chat customizado construido no React que utiliza a **Google Chat API** como transporte de mensagens para os supervisores em campo.

O objetivo e eliminar o gargalo de comunicacao entre os atendentes (escritorio) e os supervisores (patio/campo), centralizando as decisoes de locacao em uma unica interface auditavel e em tempo real.

> **Nota tecnica:** Nao se trata de embutir o Google Chat como iframe — o Google nao permite isso. E um chat proprio no CRM que envia/recebe mensagens via Google Chat API.

---

## 2. Caso de Uso: Agilidade na Operacao

**Cenario:** Aprovacao de desconto e consulta de estoque em tempo real.

* **Ana (Atendente):** No escritorio via CRM (React), precisa de aprovacao para um desconto de 10% em uma Betoneira.
* **Beto (Supervisor):** No patio de maquinas, recebe a notificacao no celular via **Google Chat** (app nativo).
* **Interacao:** Beto responde por **audio** confirmando a disponibilidade e o desconto. A Ana ouve o audio diretamente no CRM e fecha o contrato na hora.

---

## 3. Arquitetura de Sistema e Rotas (FastAPI)

O backend no **Cloud Run** servira como o "orquestrador" entre o CRM e o Google Workspace.

### Endpoints Principais:

| Metodo | Rota | Descricao | Autenticacao |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/chat/send-message` | Envia texto/audio do CRM para o Google Chat | Firebase Auth |
| `POST` | `/api/chat/spaces` | Lista spaces/salas disponiveis | Firebase Auth |
| `POST` | `/api/chat/history/{space_id}` | Historico de mensagens de um space | Firebase Auth |
| `POST` | `/webhooks/google-chat` | Recebe eventos do Google Chat e atualiza o Firestore | Token de verificacao do Google |
| `POST` | `/api/storage/upload-url` | Gera URL assinada para upload de audios/anexos | Firebase Auth |

### Autenticacao do Webhook Google Chat

Quando o Google Chat envia eventos para o endpoint `/webhooks/google-chat`, a requisicao inclui um **Bearer token** (JWT) no header `Authorization`. O backend deve:

1. Extrair o token do header `Authorization: Bearer <token>`
2. Verificar o JWT usando as chaves publicas do Google (`https://www.googleapis.com/service_accounts/v1/metadata/x509/chat@system.gserviceaccount.com`)
3. Validar que o `iss` (emissor) seja `chat@system.gserviceaccount.com`
4. Validar que o `audience` do token corresponde ao **Project Number** do seu projeto GCP
5. Rejeitar requisicoes com token invalido ou expirado

---

## 4. Fluxo de Dados (Data Flow)

### Fluxo de Saida (CRM -> Supervisor):
1. O `React` envia a mensagem para o `FastAPI` (rota `/api/chat/send-message`)
2. O `FastAPI` valida o token Firebase do operador
3. O `FastAPI` registra a mensagem no `Firestore` (colecao: `internal_chats`)
4. O `FastAPI` dispara a mensagem para o Space do Supervisor via `Google Chat API`
5. O `React` ve a mensagem aparecer via `onSnapshot` (confirmacao visual)

### Fluxo de Entrada (Supervisor -> CRM):
1. O Supervisor responde no app nativo do Google Chat (celular ou desktop)
2. O `Google Chat` envia evento para `/webhooks/google-chat` (com JWT de verificacao)
3. O `FastAPI` valida o token, salva o conteudo (texto ou link do audio) no `Firestore`
4. O `React` atualiza a tela da Ana automaticamente via `onSnapshot`

### Fluxo de Audio:
1. Supervisor grava audio no Google Chat
2. Google Chat envia o evento com `attachment.resourceName` para o webhook (nao envia o binario direto)
3. FastAPI usa o `resourceName` para chamar `media.download` da Google Chat API e baixar o binario
4. FastAPI converte se necessario (iPhone envia `.m4a`, Android envia `.ogg`/`.3gp`) e armazena no Cloud Storage
5. FastAPI salva referencia (`media_url`) no Firestore
6. Frontend reproduz o audio diretamente do Cloud Storage (URL assinada) — componente de audio suporta multiplos formatos

---

## 5. Modelagem de Dados (Firestore)

Estrutura para suporte a historico, auditoria e dashboards de performance.

### Colecao: `internal_chats`

| Campo | Tipo | Descricao |
| :--- | :--- | :--- |
| `id` | string | ID do documento (hash dos participantes ou space_id) |
| `space_id` | string | ID do Google Chat Space associado |
| `space_name` | string | Nome legivel do space |
| `participants` | array | Lista de emails dos participantes |
| `last_message` | string | Preview da ultima mensagem |
| `last_update` | timestamp | Data/hora da ultima atividade |
| `context_id` | string | (Opcional) ID do pedido/contrato relacionado |
| `unread_count` | map | Contagem de nao-lidas por operador `{ "ana_id": 3 }` |

### Sub-colecao: `internal_chats/{chat_id}/messages`

```json
{
  "sender_id": "beto@centralloc.com.br",
  "sender_name": "Beto Silva",
  "type": "audio",
  "content": "Pode dar o desconto, tem 3 betoneiras disponiveis",
  "media_url": "gs://hubloc-media/internal-chat/audio_789.ogg",
  "timestamp": "2026-03-23T14:05:00Z",
  "gchat_message_id": "spaces/AAAA/messages/BBBB",
  "metadata": {
    "source": "google_chat_mobile",
    "status": "delivered",
    "transcription": "Pode dar o desconto, tem 3 betoneiras disponiveis"
  }
}
```

### Por que guardar no Firestore se o Google ja armazena?

- **Auditoria independente** — dados sob seu controle, nao depende da retencao do Google
- **Correlacao com CRM** — vincular mensagens a pedidos, contratos, clientes
- **Performance** — consultas rapidas sem depender da API do Google
- **Relatorios** — dashboards proprios de tempo de resposta, volume, etc.

---

## 6. Frontend: Painel Lateral (Slide-in)

O painel sera um componente React que desliza da **direita para a esquerda**, sem sobrepor o chat do WhatsApp.

### Comportamento:
- **Icone** ao lado do botao de configuracoes (header do CRM)
- **Clique** abre o painel lateral com animacao slide-in (~350px de largura)
- **Clique fora** ou no X fecha o painel
- **Nao bloqueia** o chat do WhatsApp — o operador pode ver ambos simultaneamente
- **Badge** com contagem de mensagens nao lidas no icone

### Componentes do painel:
1. **Lista de conversas** — spaces/salas do Google Chat com preview da ultima mensagem
2. **Tela de conversa** — mensagens em tempo real com suporte a texto e audio
3. **Input de mensagem** — campo de texto + botao de gravar audio
4. **Indicador de status** — online/offline dos participantes

### Notificacoes (painel fechado):
- Quando o painel estiver **fechado**, novas mensagens detectadas via `onSnapshot` disparam:
  - **Badge numerico** no icone do painel (contagem de nao-lidas)
  - **Notificacao sonora** (beep discreto, configuravel)
  - **Toast notification** com preview da mensagem e nome do remetente
- Ao **abrir o painel** ou **abrir a conversa**, o `unread_count` do operador e resetado via chamada ao backend

---

## 7. Variaveis de Ambiente (Novas)

Adicionar ao `.env` e ao deploy do Cloud Run:

```env
# Google Chat Integration
GOOGLE_CHAT_SERVICE_ACCOUNT_KEY=  # JSON key da service account (ou usar workload identity)
GOOGLE_CHAT_PROJECT_NUMBER=       # Project number do GCP (para validar JWT do webhook)
FEATURE_INTERNAL_CHAT=false       # Feature flag para habilitar/desabilitar
```

---

## 8. Guia para o Administrador do Google Workspace

> **Este guia deve ser repassado ao administrador do Google Workspace `@centralloc.com.br`** para que ele aprove o uso do Google Chat App interno.

### 8.1 O que e necessario

Para que o CRM da Hubloc possa enviar e receber mensagens via Google Chat, precisamos que um **Google Chat App** (bot) seja aprovado no workspace `@centralloc.com.br`. Este app:

- E **interno** — visivel apenas para usuarios `@centralloc.com.br`
- **Nao acessa dados pessoais** — apenas envia/recebe mensagens nos spaces em que for adicionado
- Roda no **Cloud Run** da Castro Intelligence (mesmo servidor do CRM)

### 8.2 Passo a passo para o administrador

#### Passo 1: Habilitar a Google Chat API no Console GCP

1. Acesse [Google Cloud Console](https://console.cloud.google.com)
2. Selecione o projeto GCP do CRM (mesmo projeto do Cloud Run)
3. Va em **APIs e Servicos** > **Biblioteca**
4. Pesquise por **Google Chat API** e clique em **Ativar**

#### Passo 2: Configurar o Chat App

1. No Console GCP, va em **APIs e Servicos** > **Google Chat API** > **Configuracao**
2. Preencha os campos:
   - **Nome do app:** `Hubloc CRM`
   - **URL do avatar:** (logo da Hubloc)
   - **Descricao:** `Comunicacao interna entre atendentes e supervisores`
   - **Funcionalidade:** Marque "Receber mensagens 1:1" e "Participar de spaces"
   - **Configuracoes de conexao:** Selecione **URL do endpoint HTTP**
   - **URL do endpoint:** `https://SEU-SERVICO.run.app/webhooks/google-chat`
   - **Publico:** Selecione **Pessoas e grupos especificos no seu dominio**

3. Clique em **Salvar**

#### Passo 3: Permitir o Chat App no Admin Console do Workspace

1. Acesse [admin.google.com](https://admin.google.com) com conta de administrador `@centralloc.com.br`
2. Va em **Apps** > **Google Workspace** > **Google Chat**
3. Verifique que o Google Chat esta **ativado** para a organizacao
4. Va em **Apps** > **Marketplace apps** > **Configuracoes**
5. Em **Gerenciamento de apps do Chat**, garanta que apps internos sao permitidos

#### Passo 4: Autorizar a instalacao do app para os usuarios

1. Ainda no [admin.google.com](https://admin.google.com)
2. Va em **Apps** > **Google Workspace** > **Google Chat** > **Apps de Chat**
3. Procure pelo app **Hubloc CRM** (criado no passo 2)
4. Clique nele e selecione **Permitir para todos** (ou para unidades organizacionais especificas)
5. Salve as alteracoes

#### Passo 5: Testar

1. Qualquer usuario `@centralloc.com.br` abre o Google Chat
2. Inicia uma conversa com o bot **Hubloc CRM**
3. Envia uma mensagem de teste
4. O CRM deve receber a mensagem via webhook e exibir no painel

### 8.3 Permissoes necessarias (Escopos OAuth)

O app solicitara apenas os seguintes escopos:

| Escopo | Motivo |
| :--- | :--- |
| `https://www.googleapis.com/auth/chat.messages` | Enviar e ler mensagens nos spaces |
| `https://www.googleapis.com/auth/chat.spaces.readonly` | Listar spaces disponiveis |
| `https://www.googleapis.com/auth/chat.memberships.readonly` | Ver membros dos spaces |

### 8.4 Seguranca e privacidade

- O app **so acessa mensagens dos spaces em que for adicionado** — nao tem acesso a conversas privadas
- Todas as mensagens sao armazenadas no **Firestore** (servidor do CRM) para fins de **auditoria operacional**
- O app roda em infraestrutura **Google Cloud Run** com criptografia em transito (HTTPS)
- O administrador pode **revogar o acesso** a qualquer momento pelo Admin Console

---

## 9. Proximos Passos

1. **Admin aprova** o Chat App no workspace `@centralloc.com.br` (Secao 8)
2. **Backend:** Implementar rotas `/api/chat/*` e `/webhooks/google-chat` no FastAPI
3. **Frontend:** Construir painel lateral slide-in no React
4. **Teste integrado:** Enviar mensagem do CRM, receber resposta no Google Chat, verificar auditoria no Firestore
5. **Deploy:** Atualizar Cloud Run com novas variaveis de ambiente
