import type { ChatMessage, Contact, Conversation } from "../types";

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
    declared_name: String(record.declared_name || ""),
    whatsapp_profile_name: String(record.whatsapp_profile_name || ""),
    created_source: String(record.created_source || ""),
    created_by_user_id: record.created_by_user_id == null ? null : num(record.created_by_user_id),
    phone_formatted: String(record.phone_formatted || ""),
    qualification: String(record.qualification || ""),
    notes: String(record.notes || ""),
    assigned_to: record.assigned_to == null ? null : num(record.assigned_to),
    assigned_name: String(record.assigned_name || ""),
    assigned_role: String(record.assigned_role || ""),
    assigned_to_uid: String(record.assigned_to_uid || ""),
    department_id: record.department_id == null ? null : num(record.department_id),
    department_name: String(record.department_name || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    phone_number_id: String(record.phone_number_id || ""),
    source_channel_type: String(record.source_channel_type || ""),
    unread_count: num(record.unread_count ?? record.unread ?? 0),
    unread: num(record.unread ?? record.unread_count ?? 0),
    is_archived: num(record.is_archived ?? 0),
    first_seen_at: iso(record.first_seen_at),
    last_message_at: iso(record.last_message_at),
    last_inbound_at: iso(record.last_inbound_at),
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
    conversation_id: record.conversation_id == null ? null : String(record.conversation_id),
    direction: String(record.direction || "system"),
    msg_type: String(record.msg_type || "text"),
    content: String(record.content || ""),
    media_path: String(record.media_path || ""),
    media_mime: String(record.media_mime || ""),
    filename: String(record.filename || ""),
    status: String(record.status || ""),
    operator_id: record.operator_id == null ? null : num(record.operator_id),
    sender_user_id: record.sender_user_id == null ? null : num(record.sender_user_id),
    channel_owner_user_id: record.channel_owner_user_id == null ? null : num(record.channel_owner_user_id),
    operator_name: String(record.operator_name || ""),
    created_at: iso(record.created_at),
    timestamp_wa: iso(record.timestamp_wa),
    transcription: String(record.transcription || ""),
    reply_to_message_id: record.reply_to_message_id == null ? null : num(record.reply_to_message_id),
    reply_to_preview: String(record.reply_to_preview || ""),
    reply_to_sender_name: String(record.reply_to_sender_name || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    phone_number_id: String(record.phone_number_id || ""),
    is_corrected: Boolean(record.is_corrected),
    corrected_by_message_id: record.corrected_by_message_id == null ? null : num(record.corrected_by_message_id),
  };
}

export function normalizeConversation(record: Record<string, unknown>, docId: string): Conversation {
  return {
    id: String(record.id || docId),
    contact_id: num(record.contact_id),
    wa_id: String(record.wa_id || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    channel_label: String(record.channel_label || ""),
    channel_type: String(record.channel_type || ""),
    channel_phone_number: String(record.channel_phone_number || ""),
    channel_active: record.channel_active == null ? undefined : Boolean(record.channel_active),
    source_channel_type: String(record.source_channel_type || ""),
    phone_number_id: String(record.phone_number_id || ""),
    assigned_to: record.assigned_to == null ? null : num(record.assigned_to),
    assigned_to_uid: String(record.assigned_to_uid || ""),
    department_id: record.department_id == null ? null : num(record.department_id),
    unread_count: num(record.unread_count ?? record.unread ?? 0),
    unread: num(record.unread ?? record.unread_count ?? 0),
    status: String(record.status || "open"),
    attendance_status: String(record.attendance_status || "aberto"),
    is_backup: Boolean(record.is_backup),
    last_message_at: iso(record.last_message_at),
    last_inbound_at: iso(record.last_inbound_at),
    last_outbound_at: iso(record.last_outbound_at),
    created_at: iso(record.created_at),
    display_name: String(record.display_name || ""),
    declared_name: String(record.declared_name || ""),
    phone_formatted: String(record.phone_formatted || ""),
    qualification: String(record.qualification || ""),
    notes: String(record.notes || ""),
    rating: record.rating == null ? null : num(record.rating),
    is_archived: num(record.is_archived ?? 0),
    contact_avatar_path: String(record.contact_avatar_path || ""),
    attendance_protocol: String(record.attendance_protocol || ""),
    attendance_started_at: iso(record.attendance_started_at),
    takeover_status: String(record.takeover_status || "none"),
    lead_owner_user_id: record.lead_owner_user_id == null ? null : num(record.lead_owner_user_id),
    takeover_handler_user_id: record.takeover_handler_user_id == null ? null : num(record.takeover_handler_user_id),
  };
}
