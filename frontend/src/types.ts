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
  auth_mode: "firebase" | string;
  chat_delivery_mode: TransportMode;
  polling_interval_ms: number;
  data_backend: "firestore" | string;
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
  perfil_acesso_id?: string;
  department_id?: number | null;
  department_name?: string;
  email?: string;
  firebase_uid?: string;
  avatar_path?: string;
  is_active?: number;
  coex_authorized?: number;
  coex_phone?: string;
};

// RBAC dinamico (M-B2). Catalogo FIXO da plataforma — manter em sincronia
// com PERMISSION_CATALOG em rbac.py (backend e a fonte da verdade).
export type PermissionKey =
  | "ver_todos_leads"
  | "enviar_mensagem_propria_thread"
  | "enviar_mensagem_qualquer_thread"
  | "assumir_coex_proprio"
  | "assumir_supervisor"
  | "transferir_atendimento"
  | "fechar_atendimento_manual"
  | "reabrir_atendimento_manual"
  | "enviar_nota_interna"
  | "enviar_template"
  | "editar_dono_lead"
  | "qualificar_lead"
  | "editar_declared_name"
  | "arquivar_lead"
  | "adicionar_contato_manual"
  | "exportar_contatos"
  | "gerenciar_canais"
  | "desativar_canais"
  | "autorizar_coex_para_operador"
  | "ver_painel_conflitos"
  | "ver_dashboard_uso"
  | "buscar_protocolo"
  | "gerenciar_usuarios"
  | "desativar_usuarios"
  | "gerenciar_perfis_acesso"
  | "gerenciar_departamentos"
  | "desativar_departamentos"
  | "gerenciar_config_sistema";

// Perfil EFETIVO da sessao (toggles ja resolvidos pelo backend com o
// fallback de role do dual-check). O snapshot do doc perfis_acesso mescla
// por cima para refletir edicoes ao vivo.
export type SessionPerfil = {
  id: string;
  toggles: Record<string, boolean>;
};

// Item do catalogo de toggles retornado por GET /api/admin/perfis-acesso.
export type PerfilCatalogoItem = { grupo: string; chave: string; rotulo: string };

// Doc completo de tenants/{tid}/perfis_acesso/{id} (UI de gestao).
export type PerfilAcesso = {
  id: string;
  nome: string;
  descricao?: string;
  role_equivalente?: string;
  is_system_locked?: boolean;
  is_seed?: boolean;
  toggles: Record<string, boolean>;
  updated_at?: string;
};

export type BotKey = "comercial" | "financeiro" | "administrativo" | "sac";

export type Department = {
  id: number;
  name: string;
  description?: string;
  is_active?: number;
  sort_order?: number;
  bot_key?: BotKey | null;
};

export type Channel = {
  id: number;
  channel_type: "standard" | "coexistence";
  label: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string;
  owner_user_id?: number | null;
  owner_firebase_uid?: string;
  default_department_id?: number | null;
  is_bot_enabled?: boolean;
  is_active?: boolean;
  webhook_subscribed?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type Operator = {
  id: number;
  username?: string;
  display_name: string;
  department_id?: number | null;
  department_name?: string;
  avatar_path?: string;
  role: string;
  perfil_acesso_id?: string;
  email?: string;
  firebase_uid?: string;
  coex_authorized?: number;
  coex_phone?: string;
};

export type Contact = {
  id: number;
  wa_id: string;
  display_name: string;
  declared_name?: string;
  whatsapp_profile_name?: string;
  created_source?: "webhook" | "manual" | string;
  created_by_user_id?: number | null;
  phone_formatted?: string;
  qualification?: string;
  notes?: string;
  assigned_to?: number | null;
  assigned_name?: string;
  assigned_role?: string;
  assigned_to_uid?: string;
  department_id?: number | null;
  department_name?: string;
  channel_id?: number | null;
  phone_number_id?: string;
  source_channel_type?: "standard" | "coexistence" | string;
  original_operator_id?: number | null;
  converted_by_user_id?: number | null;
  sale_owner_user_id?: number | null;
  sale_owner_uid?: string;
  rating?: number | null;
  unread_count?: number;
  unread?: number;
  is_archived?: number;
  first_seen_at?: string;
  last_message_at?: string;
  last_inbound_at?: string;
  contact_avatar_path?: string;
  attendance_protocol?: string;
  attendance_started_at?: string;
  bot_completed?: boolean;
  bot_setor_nome?: string;
};

// Conversation = thread unica (channel_id + wa_id). Mesmo wa_id em
// dois canais aparece como duas Conversations distintas.
// id deterministico: "{channel_id}__{wa_id}"
export type Conversation = {
  id: string;
  contact_id: number;
  wa_id: string;
  channel_id: number | null;
  channel_label?: string;
  channel_type?: "standard" | "coexistence" | string;
  channel_phone_number?: string;
  channel_active?: boolean;
  source_channel_type?: "standard" | "coexistence" | string;
  phone_number_id?: string;
  assigned_to?: number | null;
  assigned_to_uid?: string;
  department_id?: number | null;
  unread_count?: number;
  unread?: number;
  status?: "open" | "archived" | string;
  attendance_status?: "aberto" | "fechado_inatividade" | "fechado_manual" | "fechado_cliente" | string;
  // Backup: conversa historica importada — visivel so a admin/supervisor (aba Backup).
  is_backup?: boolean;
  // Resposta do cliente ao template de reabertura (webhook button reply).
  reopen_response?: "retomar" | "encerrar" | string;
  reopen_response_at?: string;
  client_requested_close?: boolean;
  last_message_at?: string;
  last_inbound_at?: string;
  last_outbound_at?: string;
  created_at?: string;
  // Dados do contato denormalizados (join in-memory feito pelo backend)
  display_name?: string;
  declared_name?: string;
  phone_formatted?: string;
  qualification?: string;
  notes?: string;
  rating?: number | null;
  is_archived?: number;
  contact_avatar_path?: string;
  attendance_protocol?: string;
  attendance_started_at?: string;
  // Takeover temporario (coexistence multi-operador): quando um lead de outro
  // operador manda mensagem pro numero deste operador.
  takeover_status?: "none" | "pending" | "active" | string;
  lead_owner_user_id?: number | null;
  takeover_handler_user_id?: number | null;
};

// Painel de Conflitos (Fase 3A): Lead com >=2 atendimentos ativos de
// operadores distintos.
export type ConflictConversation = {
  conversation_id: string;
  channel_id: number | null;
  channel_label: string;
  channel_phone_number: string;
  channel_active: boolean;
  assigned_to: number | null;
  unread: number;
  last_message_at: string;
};

export type ConflictLead = {
  contact_id: number;
  display_name: string;
  phone_formatted: string;
  lead_owner_user_id: number | null;
  conversations: ConflictConversation[];
};

// Fase 5A: Protocolo de Atendimento (1 dia = 1 por Lead).
export type ProtocolAtendimento = {
  id: string;
  contact_id: number;
  date: string;
  setor: string;
  criado_em?: string | null;
  ultima_interacao?: string | null;
  status: "aberto" | "fechado_inatividade" | "fechado_manual" | "fechado_cliente" | string;
  protocolo_informado: boolean;
  fechado_em?: string | null;
  fechado_por_user_id?: number | null;
};

export type ProtocolSearchResult = {
  atendimento: ProtocolAtendimento;
  contact: { id: number; display_name: string; phone_formatted: string; wa_id: string } | null;
  messages: ChatMessage[];
  count: number;
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
  conversation_id?: string | null;
  direction: "inbound" | "outbound" | "system" | string;
  msg_type: "text" | "image" | "audio" | "video" | "gif" | "sticker" | "document" | "system" | string;
  content?: string;
  media_path?: string;
  media_mime?: string;
  filename?: string;
  status?: string;
  // operator_id e o legado; sender_user_id e o novo (Fase 2C). Sao iguais
  // quando o operador atribuido envia. Diferem em coexistence quando a
  // thread foi transferida — channel_owner_user_id mostra o dono fisico
  // do numero, sender_user_id mostra quem digitou de fato.
  operator_id?: number | null;
  sender_user_id?: number | null;
  channel_owner_user_id?: number | null;
  operator_name?: string;
  assigned_to_uid?: string;
  created_at?: string;
  timestamp_wa?: string;
  transcription?: string;
  reply_to_message_id?: number | null;
  reply_to_preview?: string;
  reply_to_sender_name?: string;
  channel_id?: number | null;
  phone_number_id?: string;
  is_rating_message?: boolean;
  visibility?: "all" | "admin_only" | string;
  is_corrected?: boolean;
  corrected_by_message_id?: number | null;
};

export type TransferRequest = {
  conversation_id?: string;
  contact_id?: number;
  to_user_id: number;
  to_department_id?: number | null;
  reason: string;
  summary: string;
};

export type TemplateButton = {
  type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | string;
  text: string;
  url?: string;
  phone_number?: string;
};

export type TemplateComponent = {
  type: "HEADER" | "BODY" | "FOOTER" | "BUTTONS" | string;
  text?: string;
  format?: "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT" | string;
  example?: {
    body_text?: string[][];
    header_text?: string[];
    header_handle?: string[];
  };
  buttons?: TemplateButton[];
};

export type WhatsAppTemplate = {
  id?: string;
  name: string;
  language: string;
  category: "MARKETING" | "UTILITY" | "AUTHENTICATION" | string;
  status: "APPROVED" | "PENDING" | "REJECTED" | "PAUSED" | string;
  components: TemplateComponent[];
};

export type TemplateParameterValue = {
  type: "text";
  text: string;
};

export type TemplateSendComponent = {
  type: "header" | "body" | "button";
  sub_type?: "quick_reply" | "url";
  index?: string;
  parameters: TemplateParameterValue[];
};

export type SystemSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_roles: string[];
  quick_message_max: number;
  quick_messages_global: { shortcut: string; message: string }[];
  notification_sound_enabled: boolean;
  alarm_enabled: boolean;
  alarm_threshold_minutes: number;
  alarm_department_ids: number[];
  alarm_sound_path: string;
  notification_sound_path: string;
  bot_enabled: boolean;
};

export type UserSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_name: string;
  quick_messages: { shortcut: string; message: string }[];
};

export type ActiveView = "novos" | "meus" | "nao_qualificados" | "equipe" | "bot" | "backup";

export type SettingsPage = false | "menu" | "chat" | "quick" | "admin" | "perfis" | "whatsapp" | "whatsapp-standard" | "dashboard";

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
