# Proposta Técnica: Módulo de Comunicação Interna Integrada (Hubloc CRM)

**Preparado por:** Castro Intelligence  
**Cliente:** Hubloc – Locação de Equipamentos  
**Data:** 23 de Março de 2026  

---

## 1. Resumo Executivo
Esta proposta visa a implementação de um **Widget de Comunicação Interna** dentro do ecossistema do CRM da Hubloc. O objetivo é eliminar o gargalo de comunicação entre os atendentes (escritório) e os supervisores (pátio/campo), centralizando as decisões de locação em uma única interface auditável e em tempo real.

---

## 2. Caso de Uso: Agilidade na Operação
**Cenário:** Aprovação de desconto e consulta de estoque em tempo real.

* **Ana (Atendente):** No escritório via CRM (React), precisa de aprovação para um desconto de 10% em uma Betoneira.
* **Beto (Supervisor):** No pátio de máquinas, recebe a notificação no celular via **Google Chat**.
* **Interação:** Beto responde por **áudio** confirmando a disponibilidade e o desconto. A Ana ouve o áudio diretamente no CRM e fecha o contrato na hora.

---

## 3. Arquitetura de Sistema e Rotas (FastAPI)

O backend no **Cloud Run** servirá como o "orquestrador" entre o CRM e o Google Workspace.

### Endpoints Principais:

| Método | Rota | Descrição | Origem |
| :--- | :--- | :--- | :--- |
| `POST` | `/chat/send-message` | Envia texto/áudio do CRM para o Google Chat. | React (CRM) |
| `POST` | `/webhooks/google-chat` | **Endpoint Público:** Recebe respostas do Google e atualiza o Firestore. | Google Chat |
| `POST` | `/storage/upload-url` | Gera URL assinada para upload de áudios/anexos. | React (CRM) |

---

## 4. Fluxo de Dados (Data Flow)

> **Fluxo de Saída (CRM -> Supervisor):**
> 1. O `React` envia a mensagem para o `FastAPI`.
> 2. O `FastAPI` registra a escrita no `Firestore` (Coleção: `internal_chats`).
> 3. O `FastAPI` dispara a mensagem para o Supervisor via `Google Chat API`.
>
> **Fluxo de Entrada (Supervisor -> CRM):**
> 1. O Supervisor responde no app nativo do Google Chat.
> 2. O `Google Webhook` notifica o `FastAPI`.
> 3. O `FastAPI` salva o conteúdo (texto ou link do áudio) no `Firestore`.
> 4. O `React` atualiza a tela da Ana automaticamente via `onSnapshot`.

---

## 5. Modelagem de Dados (Firestore)

Estrutura sugerida para suporte a histórico e dashboards de performance:

### Coleção: `internal_chats`
* **ID:** `hash_dos_participantes` (Ex: `ana_beto_conversas`)
* **Fields:** `participants`, `last_update`, `context_id` (ID do Pedido).

### Sub-coleção: `messages`
```json
{
  "sender_id": "beto@hubloc.com.br",
  "type": "audio", // ou "text"
  "content": "Transcrição automática opcional aqui",
  "media_url": "[https://storage.googleapis.com/hubloc-chat/audio_789.mp3](https://storage.googleapis.com/hubloc-chat/audio_789.mp3)",
  "timestamp": "2026-03-23T14:05:00Z",
  "metadata": {
    "source": "google_chat_mobile",
    "status": "delivered"
  }
}