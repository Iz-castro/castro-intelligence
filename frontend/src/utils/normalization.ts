import type { ChatMessage, Contact } from "../types";

export function iso(value: unknown) {
  if (!value) return "";
  if (typeof value === "string") return value;
  const item = value as { toDate?: () => Date; seconds?: number; nanoseconds?: number };
  if (typeof item.toDate === "function") return item.toDate().toISOString();
  if (typeof item.seconds === "number") {
    return new Date(item.seconds * 1000 + Math.floor((item.nanoseconds || 0) / 1_000_000)).toISOString();
  }
  return String(value);
}

export function num(value: unknown) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function normalizeContact(record: Record<string, unknown>, docId: string): Contact {
  return {
    id: num(record.id ?? docId),
    wa_id: String(record.wa_id || ""),
    display_name: String(record.display_name || record.phone_formatted || "Contato"),
    phone_formatted: String(record.phone_formatted || ""),
    qualification: String(record.qualification || ""),
    notes: String(record.notes || ""),
    assigned_to: record.assigned_to == null ? null : num(record.assigned_to),
    assigned_name: String(record.assigned_name || ""),
    assigned_to_uid: String(record.assigned_to_uid || ""),
    department_id: record.department_id == null ? null : num(record.department_id),
    department_name: String(record.department_name || ""),
    unread_count: num(record.unread_count ?? record.unread ?? 0),
    unread: num(record.unread ?? record.unread_count ?? 0),
    last_message_at: iso(record.last_message_at),
    contact_avatar_path: String(record.contact_avatar_path || ""),
    attendance_protocol: String(record.attendance_protocol || ""),
    attendance_started_at: iso(record.attendance_started_at),
    bot_completed: Boolean(record.bot_completed),
    bot_setor_nome: String(record.bot_setor_nome || ""),
  };
}

export function normalizeMessage(record: Record<string, unknown>, docId: string): ChatMessage {
  return {
    id: num(record.id ?? docId),
    contact_id: num(record.contact_id),
    direction: String(record.direction || "system"),
    msg_type: String(record.msg_type || "text"),
    content: String(record.content || ""),
    media_path: String(record.media_path || ""),
    media_mime: String(record.media_mime || ""),
    filename: String(record.filename || ""),
    status: String(record.status || ""),
    operator_id: record.operator_id == null ? null : num(record.operator_id),
    operator_name: String(record.operator_name || ""),
    created_at: iso(record.created_at),
    timestamp_wa: iso(record.timestamp_wa),
    transcription: String(record.transcription || ""),
    reply_to_message_id: record.reply_to_message_id == null ? null : num(record.reply_to_message_id),
    reply_to_preview: String(record.reply_to_preview || ""),
    reply_to_sender_name: String(record.reply_to_sender_name || ""),
  };
}
