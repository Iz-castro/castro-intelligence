import type { ChatMessage, MessageReplyReference } from "../types";
import { waPlainText } from "./waFormat";

const dtf = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export function when(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--" : dtf.format(date);
}

export function formatRecordingTime(seconds: number) {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
  const rest = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

export function messageTypeLabel(value?: string) {
  const kind = String(value || "").trim().toLowerCase();
  if (!kind) return "mensagem";
  if (kind === "unsupported" || kind === "unknown") return "midia";
  if (kind === "contacts") return "contato";
  if (kind === "location") return "localizacao";
  return kind;
}

export function messageContentLabel(message: ChatMessage) {
  const content = String(message.content || "").trim();
  if (!content) return "";
  const kind = String(message.msg_type || "").trim().toLowerCase();
  if (content.toLowerCase() === "[unknown]" || content.toLowerCase() === "[unsupported]" || kind === "unsupported" || kind === "unknown") {
    return "Midia nao suportada pelo payload recebido do WhatsApp.";
  }
  return content;
}

export function messageSenderLabel(message: ChatMessage, operators?: Array<{ id: number; display_name: string }>) {
  if (message.direction === "outbound") {
    // Autoria por mensagem (ADR 0010): operator_name so existe no caminho
    // REST; sent_by_name e o denormalizado no doc (snapshot mode); o mapa de
    // operators cobre o historico anterior ao campo.
    if (message.operator_name) return message.operator_name;
    if (message.sent_by_name) return message.sent_by_name;
    const senderId = message.sender_user_id ?? message.operator_id;
    if (senderId != null && operators) {
      const found = operators.find((item) => item.id === senderId);
      if (found?.display_name) return found.display_name;
    }
    return message.operator_id || message.sender_user_id ? "Equipe" : "Bot";
  }
  if (message.direction === "inbound") return "Cliente";
  return "Sistema";
}

export function messageCopyText(message: ChatMessage) {
  const content = messageContentLabel(message);
  if (content) return content;
  return String(message.transcription || "").trim();
}

export function messagePreviewText(message: ChatMessage) {
  const copyText = messageCopyText(message);
  if (copyText) return copyText;

  const filename = String(message.filename || "").trim();
  const kind = String(message.msg_type || "").trim().toLowerCase();
  if (filename && kind === "document") return `Documento: ${filename}`;
  if (filename && kind === "video") return `Video: ${filename}`;
  if (filename && kind === "image") return `Imagem: ${filename}`;
  if (filename && kind === "audio") return `Audio: ${filename}`;

  if (kind === "audio") return "Audio";
  if (kind === "image") return "Imagem";
  if (kind === "video" || kind === "gif") return "Video";
  if (kind === "sticker") return "Figurinha";
  if (kind === "document") return "Documento";
  if (kind === "location") return "Localizacao";
  if (kind === "template") return "Template";
  return "Mensagem";
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

export function buildMessageReplyReference(message: ChatMessage): MessageReplyReference {
  return {
    message_id: message.id,
    // Sem marcadores do WhatsApp na citacao (igual ao app faz).
    preview: truncateText(waPlainText(messagePreviewText(message)), 280),
    sender_name: truncateText(messageSenderLabel(message), 80),
  };
}

export function messageMoment(value?: string) {
  if (!value) return Number.NaN;
  const date = new Date(value);
  return date.getTime();
}
