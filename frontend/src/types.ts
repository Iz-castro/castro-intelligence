export type TransportMode = "snapshot" | "polling";

export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  storageBucket: string;
  appId: string;
  messagingSenderId?: string;
  measurementId?: string;
};

export type ClientConfig = {
  auth_mode: "firebase" | "legacy" | string;
  chat_delivery_mode: TransportMode;
  polling_interval_ms: number;
  data_backend: "firestore" | "sql" | string;
  media_storage_backend: string;
  feature_message_status: boolean;
  feature_google_chat: boolean;
  allowed_email_domain: string;
  firebase_web_config: FirebaseWebConfig;
  firestore: {
    snapshot_enabled: boolean;
    collections: Record<string, string>;
  };
};

export type SessionUser = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  department_id?: number | null;
  department_name?: string;
  email?: string;
  firebase_uid?: string;
  avatar_path?: string;
  is_active?: number;
};

export type Department = {
  id: number;
  name: string;
  description?: string;
};

export type Operator = {
  id: number;
  display_name: string;
  department_id?: number | null;
  department_name?: string;
  avatar_path?: string;
  role: string;
  email?: string;
  firebase_uid?: string;
};

export type Contact = {
  id: number;
  wa_id: string;
  display_name: string;
  phone_formatted?: string;
  qualification?: string;
  notes?: string;
  assigned_to?: number | null;
  assigned_name?: string;
  assigned_role?: string;
  assigned_to_uid?: string;
  department_id?: number | null;
  department_name?: string;
  unread_count?: number;
  unread?: number;
  is_archived?: number;
  first_seen_at?: string;
  last_message_at?: string;
  contact_avatar_path?: string;
  attendance_protocol?: string;
  attendance_started_at?: string;
};

export type MessageReplyReference = {
  message_id: number;
  preview: string;
  sender_name: string;
};

export type ChatMessage = {
  id: number;
  wa_message_id?: string;
  contact_id: number;
  direction: "inbound" | "outbound" | "system" | string;
  msg_type: "text" | "image" | "audio" | "video" | "gif" | "sticker" | "document" | "system" | string;
  content?: string;
  media_path?: string;
  media_mime?: string;
  filename?: string;
  status?: string;
  operator_id?: number | null;
  operator_name?: string;
  assigned_to_uid?: string;
  created_at?: string;
  timestamp_wa?: string;
  transcription?: string;
  reply_to_message_id?: number | null;
  reply_to_preview?: string;
  reply_to_sender_name?: string;
};

export type TransferRequest = {
  contact_id: number;
  to_user_id: number;
  to_department_id?: number | null;
  reason: string;
  summary: string;
};

export type SystemSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_roles: string[];
  quick_message_max: number;
  quick_messages_global: { shortcut: string; message: string }[];
};

export type UserSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_name: string;
  quick_messages: { shortcut: string; message: string }[];
};

export type ActiveView = "novos" | "meus" | "nao_qualificados" | "equipe";

export type SettingsPage = false | "menu" | "chat" | "quick" | "admin";

export type QuickMessage = { shortcut: string; message: string };

// -- Google Chat (comunicacao interna) --

export type GcConversation = {
  id: number;
  space_id: string;
  space_name: string;
  participants: string[];
  last_message: string;
  last_message_at?: string;
  unread_count: Record<string, number>;
  created_at?: string;
};

export type GcMessage = {
  id: number;
  conversation_id: number;
  gchat_message_id: string;
  sender_email: string;
  sender_name: string;
  msg_type: "text" | "audio" | "image" | "video" | "document" | string;
  content?: string;
  media_path?: string;
  media_mime?: string;
  source: "google_chat" | "crm" | string;
  create_time?: string;
  created_at?: string;
};
