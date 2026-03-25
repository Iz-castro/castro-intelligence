import type { ChatMessage } from "../types";

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

export function messageMoment(value?: string) {
  if (!value) return Number.NaN;
  const date = new Date(value);
  return date.getTime();
}
