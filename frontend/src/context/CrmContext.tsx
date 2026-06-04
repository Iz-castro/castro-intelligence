import { ChangeEvent, createContext, FormEvent, KeyboardEvent, startTransition, useCallback, useContext, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { onIdTokenChanged, signInWithEmailAndPassword, signInWithPopup, signOut, type User } from "firebase/auth";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query, where } from "firebase/firestore";

import { deleteJson, getJson, putJson, sendForm, sendJson } from "../api";
import { initializeFirebaseBundle, type FirebaseBundle } from "../firebase";
import type {
  ActiveView, Channel, ChatMessage, ClientConfig, ConflictLead, Contact, Conversation, Department,
  MessageReplyReference, Operator, ProtocolSearchResult, SessionUser, SettingsPage, SystemSettings,
  TemplateSendComponent, TransportMode, UserSettings, WhatsAppTemplate,
} from "../types";
import { errorText } from "../utils/errors";
import { firebaseReady } from "../utils/firebase-helpers";
import { buildMessageReplyReference, formatRecordingTime, messageCopyText, messageMoment } from "../utils/formatting";
import { normalizeContact, normalizeConversation, normalizeMessage } from "../utils/normalization";
import { applyTheme, themePref, transportPref } from "../utils/storage";
import type { LightboxMedia } from "../utils/media";
import { installAudioUnlock, playBeep } from "../utils/audio";

// ---------------------------------------------------------------------------
// Context value shape
// ---------------------------------------------------------------------------

type CrmContextValue = {
  // Core
  config: ClientConfig | null;
  bundle: FirebaseBundle | null;
  firebaseUser: User | null;
  sessionUser: SessionUser | null;
  operators: Operator[];
  departments: Department[];
  channels: Channel[];
  booting: boolean;
  busyLogin: boolean;
  snapshotMode: boolean;
  isManagerRole: boolean;

  // Theme
  theme: "dark" | "light";
  toggleTheme: () => void;

  // Auth
  loginWithGoogle: () => Promise<void>;
  loginWithEmail: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;

  // Contacts
  contacts: Contact[];
  contactsById: Map<number, Contact>;
  conversations: Conversation[];
  // selectedContactId é derivado de selectedThreadId -> conversation.contact_id.
  // Para selecionar uma conversa, chame setSelectedThreadId(conversationId).
  selectedContactId: number | null;
  selectedThreadId: string | null;
  setSelectedThreadId: (id: string | null) => void;
  selectedContact: Contact | null;
  selectedConversation: Conversation | null;

  // Views
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  novosConversations: Conversation[];
  meusConversations: Conversation[];
  nqConversations: Conversation[];
  equipeConversations: Conversation[];
  botConversations: Conversation[];
  novosUnread: number;
  meusUnread: number;
  nqUnread: number;
  equipeUnread: number;
  botUnread: number;
  equipeOperatorFilter: string;
  setEquipeOperatorFilter: (v: string) => void;
  equipeFiltered: Conversation[];

  // Messages
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  visibleMessages: ChatMessage[];
  messageLimit: number;
  setMessageLimit: React.Dispatch<React.SetStateAction<number>>;
  loadingMore: boolean;
  setLoadingMore: (v: boolean) => void;
  messagesRef: React.MutableRefObject<HTMLDivElement | null>;
  scrollIntentRef: React.MutableRefObject<"load_older" | "normal">;
  prevMessageCountRef: React.MutableRefObject<number>;

  // Transcription
  transcribingMessageId: number | null;
  transcribeMessage: (messageId: number) => Promise<void>;

  // Composer
  replyTarget: MessageReplyReference | null;
  startReplyToMessage: (message: ChatMessage) => void;
  cancelReply: () => void;
  copyMessageText: (message: ChatMessage) => Promise<void>;
  draft: string;
  setDraft: (v: string) => void;
  busySend: boolean;
  busyUpload: boolean;
  busyAudio: boolean;
  quickSuggestions: { shortcut: string; message: string }[];
  setQuickSuggestions: React.Dispatch<React.SetStateAction<{ shortcut: string; message: string }[]>>;
  sendTextMessage: () => Promise<void>;
  submitText: (e: FormEvent<HTMLFormElement>) => void;
  submitMedia: (file: File) => Promise<void>;
  submitFile: (file: File, label: string) => Promise<void>;
  sendLocation: () => Promise<void>;
  handleDraftKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  handleDraftChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  applyQuickMessage: (qm: { shortcut: string; message: string }) => void;
  handlePrimaryAction: () => void;
  handleImageSelected: (e: ChangeEvent<HTMLInputElement>) => void;
  // Modo 1 (Sussurro): nota interna — nao vai pra Meta.
  internalMode: boolean;
  setInternalMode: (v: boolean) => void;
  // Fase 3B: reatribui so o Dono do Lead (nao mexe nos atendimentos).
  reassignLead: (toUserId: number, toDeptId: number | null, reason: string, summary: string) => Promise<void>;
  // Modo 3: supervisor assume a thread (vira Dono do Atendimento).
  supervisorTakeover: (conversationId: string) => Promise<void>;
  // Fase 4: fecha/reabre um atendimento manualmente.
  setAttendance: (conversationId: string, status: "fechado_manual" | "aberto") => Promise<void>;
  // Fase 5A: busca por protocolo (admin/sup).
  loadProtocol: (protocolId: string) => Promise<ProtocolSearchResult | null>;
  composerInputRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  imageInputRef: React.MutableRefObject<HTMLInputElement | null>;
  videoInputRef: React.MutableRefObject<HTMLInputElement | null>;
  documentInputRef: React.MutableRefObject<HTMLInputElement | null>;

  // Attach menu
  showAttachMenu: boolean;
  setShowAttachMenu: (v: boolean) => void;
  toggleAttachMenu: () => void;
  openImagePicker: () => void;
  openVideoPicker: () => void;
  openDocPicker: () => void;
  attachMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Recording
  recording: boolean;
  recordingSeconds: number;
  startRecording: () => Promise<void>;
  sendRecordedAudio: () => Promise<void>;
  discardRecording: () => void;

  // Chat search
  showChatSearch: boolean;
  chatSearch: string;
  setChatSearch: (v: string) => void;
  toggleChatSearch: () => void;
  visibleMessagesFiltered: ChatMessage[] | null;

  // Dots menu
  showDotsMenu: boolean;
  toggleDotsMenu: () => void;
  closeDotsMenu: () => void;
  dotsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Lightbox
  lightboxMedia: LightboxMedia | null;
  openLightbox: (src: string, kind: "image" | "video", alt: string, gifLike?: boolean) => void;
  closeLightbox: () => void;

  // Manual contact creation
  createManualContact: (declared_name: string, phone: string, channel_id?: number) => Promise<Contact | null>;
  updateDeclaredName: (contact_id: number, declared_name: string) => Promise<void>;
  busyCreateContact: boolean;

  // Contact picker — lista TODOS contatos do tenant (inclui state_sync da agenda).
  // Cache em memoria do provider (zera no logout/fechar aba — LGPD-safe).
  loadAllContacts: (q?: string) => Promise<{ contacts: Contact[]; total: number }>;
  refreshAllContacts: () => Promise<void>;
  openConversationForContact: (contact_id: number, channel_id?: number) => Promise<string | null>;
  loadConflicts: () => Promise<ConflictLead[]>;

  // Message correction
  correctMessage: (messageId: number, newContent: string) => Promise<boolean>;
  correctionTarget: ChatMessage | null;
  startCorrection: (message: ChatMessage) => void;
  cancelCorrection: () => void;

  // Templates
  fetchTemplates: (channelId?: number | null) => Promise<WhatsAppTemplate[]>;
  fetchBillingStatus: (channelId: number) => Promise<{ ok: boolean; has_payment_method: boolean; error?: string } | null>;
  sendTemplate: (params: {
    contactId: number;
    templateName: string;
    language: string;
    components?: TemplateSendComponent[];
  }) => Promise<boolean>;
  // Reabertura: envia o template de inatividade com {{1}} (nome) e {{2}}
  // (data da ultima conversa) preenchidos no backend. Sem caixa manual.
  // templateName/language vem do template escolhido no picker.
  reopenConversation: (conversationId: string, templateName?: string, language?: string) => Promise<boolean>;
  busyTemplate: boolean;

  // Detail panel
  qualification: string;
  setQualification: (v: string) => void;
  notes: string;
  setNotes: (v: string) => void;
  toUserId: number | "";
  setToUserId: (v: number | "") => void;
  toDepartmentId: number | "";
  setToDepartmentId: (v: number | "") => void;
  transferReason: string;
  setTransferReason: (v: string) => void;
  transferSummary: string;
  setTransferSummary: (v: string) => void;
  busySave: boolean;
  busyTransfer: boolean;
  busyAssume: boolean;
  saveQualification: () => Promise<void>;
  assumeContact: (contactId: number) => Promise<void>;
  transferContact: () => Promise<void>;

  // Admin users
  editingUserId: number | null;
  setEditingUserId: (v: number | null) => void;
  editRole: string;
  setEditRole: (v: string) => void;
  editDeptId: number | "";
  setEditDeptId: (v: number | "") => void;
  busyRoleUpdate: boolean;
  startEditUser: (op: Operator) => void;
  saveUserRole: (userId: number) => Promise<void>;
  coexEditingUserId: number | null;
  coexPhoneInput: string;
  setCoexPhoneInput: (v: string) => void;
  busyCoexUpdate: boolean;
  startEditCoex: (op: Operator) => void;
  cancelEditCoex: () => void;
  saveCoex: (userId: number) => Promise<void>;
  revokeCoex: (userId: number) => Promise<void>;
  takeoverConversation: (conversationId: string, greetMessage?: string) => Promise<void>;
  returnConversation: (conversationId: string) => Promise<void>;

  // Settings
  showSettings: SettingsPage;
  setShowSettings: (v: SettingsPage) => void;
  systemSettings: SystemSettings;
  setSystemSettings: React.Dispatch<React.SetStateAction<SystemSettings>>;
  userSettings: UserSettings;
  setUserSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  busySettings: boolean;
  toggleSettingsMenu: () => void;
  openSettingsPage: (page: "chat" | "quick" | "admin" | "whatsapp" | "whatsapp-standard" | "dashboard") => Promise<void>;
  saveSystemSettingsAction: () => Promise<void>;
  saveUserSettingsAction: () => Promise<void>;
  settingsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Sidebar search
  search: string;
  setSearch: (v: string) => void;
  searchText: string;
  qualificationFilter: string;
  setQualificationFilter: (v: string) => void;
  filteredConversations: Conversation[];
  viewConversations: Conversation[];

  // Notifications
  error: string;
  setError: (msg: string) => void;
  notice: string;
  setNotice: (msg: string) => void;

  refreshPollingViews: () => Promise<void>;
};

const CrmContext = createContext<CrmContextValue | null>(null);

export function useCrm() {
  const ctx = useContext(CrmContext);
  if (!ctx) throw new Error("useCrm must be used within CrmProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Default settings
// ---------------------------------------------------------------------------

const DEFAULT_SYSTEM_SETTINGS: SystemSettings = {
  chat_prefix_enabled: false,
  chat_prefix_roles: ["admin", "supervisor", "operador"],
  quick_message_max: 20,
  quick_messages_global: [],
  notification_sound_enabled: true,
  alarm_enabled: true,
  alarm_threshold_minutes: 5,
  alarm_department_ids: [],
  alarm_sound_path: "",
  notification_sound_path: "",
  bot_enabled: false,
};

const DEFAULT_USER_SETTINGS: UserSettings = {
  chat_prefix_enabled: false,
  chat_prefix_name: "",
  quick_messages: [],
};

const CONVERSATION_OPEN_DEBOUNCE_MS = 350;
const CONVERSATION_READ_DEBOUNCE_MS = 1200;
const RECENT_CONVERSATION_CACHE_LIMIT = 12;

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function CrmProvider({ children }: { children: ReactNode }) {
  // -- Core state --
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [bundle, setBundle] = useState<FirebaseBundle | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null);
  const [operators, setOperators] = useState<Operator[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  // Fase 3: lista de conversations (sub-threads por canal). Mesmo wa_id em
  // dois canais aparece como duas entradas distintas.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  // Cache em memoria de TODOS os contatos do tenant (inclui agenda
  // sincronizada via smb_app_state_sync que nao aparece na sidebar).
  // null = ainda nao carregado; array = carregado (mesmo se vazio).
  // Zera junto com o provider (logout/refresh/aba fechada) — sem
  // persistencia em localStorage por LGPD.
  const [allContactsCache, setAllContactsCache] = useState<Contact[] | null>(null);
  const [allContactsCacheTotal, setAllContactsCacheTotal] = useState<number>(0);
  // Contatos puxados sob demanda porque sao referenciados por uma conversa
  // atribuida a este operador mas estao FORA do snapshot escopado dele
  // (ex.: takeover — lead de outro operador escreveu no numero dele).
  const [extraContacts, setExtraContacts] = useState<Map<number, Contact>>(new Map());
  const contactsById = useMemo(() => {
    const m = new Map<number, Contact>(contacts.map((c) => [c.id, c]));
    extraContacts.forEach((c, id) => { if (!m.has(id)) m.set(id, c); });
    return m;
  }, [contacts, extraContacts]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  // Fase 3 V2: selectedThreadId e a fonte unica de selecao na sidebar.
  // selectedContactId vira derivado de selectedThreadId -> conversation.contact_id.
  // Quando setado, ChatPanel filtra mensagens por conversation_id (nao
  // cross-channel como o legado).
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const selectedConversation = useMemo(
    () => (selectedThreadId ? conversations.find((c) => c.id === selectedThreadId) || null : null),
    [conversations, selectedThreadId],
  );
  const selectedContactId = selectedConversation?.contact_id ?? null;

  // Lazy-load de contatos referenciados por conversas do operador que estao
  // fora do snapshot escopado dele (caso takeover). So buscamos ids que ja
  // aparecem em conversas no estado do operador — nao varre o tenant.
  const fetchedExtraRef = useRef<Set<number>>(new Set());
  useEffect(() => {
    if (!bundle) return;
    const localIds = new Set(contacts.map((c) => c.id));
    const missing = Array.from(new Set(
      conversations
        .map((c) => c.contact_id)
        .filter((id): id is number => typeof id === "number" && !localIds.has(id) && !fetchedExtraRef.current.has(id)),
    ));
    if (missing.length === 0) return;
    let disposed = false;
    missing.forEach((id) => fetchedExtraRef.current.add(id));
    void Promise.all(missing.map((id) =>
      getJson<{ contact: Record<string, unknown> }>(bundle.auth, `/api/wa/contact/${id}`)
        .then((res) => normalizeContact(res.contact, String(res.contact.id)))
        .catch(() => null),
    )).then((fetched) => {
      if (disposed) return;
      const valid = fetched.filter((c): c is Contact => !!c);
      if (!valid.length) return;
      setExtraContacts((prev) => {
        const next = new Map(prev);
        valid.forEach((c) => next.set(c.id, c));
        return next;
      });
    });
    return () => { disposed = true; };
  }, [conversations, contacts, bundle]);

  const [transportMode, setTransportMode] = useState<TransportMode>("snapshot");
  const [booting, setBooting] = useState(true);
  const [busyLogin, setBusyLogin] = useState(false);

  // -- Theme --
  const [theme, setTheme] = useState<"dark" | "light">(() => { const p = themePref(); applyTheme(p); return p; });
  const toggleTheme = useCallback(() => {
    setTheme((prev) => { const next = prev === "dark" ? "light" : "dark"; applyTheme(next); return next; });
  }, []);

  // -- Sidebar / nav --
  const [search, setSearch] = useState("");
  const [activeView, setActiveView] = useState<ActiveView>("novos");
  const [equipeOperatorFilter, setEquipeOperatorFilter] = useState("");
  const [qualificationFilter, setQualificationFilter] = useState("");
  const searchText = useDeferredValue(search.trim().toLowerCase());

  // -- Composer --
  const [draft, setDraft] = useState("");
  const [replyTarget, setReplyTarget] = useState<MessageReplyReference | null>(null);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [quickSuggestions, setQuickSuggestions] = useState<{ shortcut: string; message: string }[]>([]);
  const [busySend, setBusySend] = useState(false);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busyAudio, setBusyAudio] = useState(false);
  const [busyTemplate, setBusyTemplate] = useState(false);

  // -- Chat search --
  const [showChatSearch, setShowChatSearch] = useState(false);
  const [chatSearch, setChatSearch] = useState("");

  // -- Dots menu --
  const [showDotsMenu, setShowDotsMenu] = useState(false);

  // -- Recording --
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingTimerRef = useRef<number | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // -- Lightbox --
  const [lightboxMedia, setLightboxMedia] = useState<LightboxMedia | null>(null);

  // -- Messages --
  const [messageLimit, setMessageLimit] = useState(10);
  const [loadingMore, setLoadingMore] = useState(false);
  const [transcribingMessageId, setTranscribingMessageId] = useState<number | null>(null);

  // -- Detail panel --
  const [qualification, setQualification] = useState("");
  const [notes, setNotes] = useState("");
  const [toUserId, setToUserId] = useState<number | "">("");
  const [toDepartmentId, setToDepartmentId] = useState<number | "">("");
  const [transferReason, setTransferReason] = useState("");
  const [transferSummary, setTransferSummary] = useState("");
  const [busySave, setBusySave] = useState(false);
  const [busyTransfer, setBusyTransfer] = useState(false);
  const [busyAssume, setBusyAssume] = useState(false);
  const [busyCreateContact, setBusyCreateContact] = useState(false);
  const [correctionTarget, setCorrectionTarget] = useState<ChatMessage | null>(null);

  // -- Admin users --
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editDeptId, setEditDeptId] = useState<number | "">("");
  const [busyRoleUpdate, setBusyRoleUpdate] = useState(false);
  const [coexEditingUserId, setCoexEditingUserId] = useState<number | null>(null);
  const [coexPhoneInput, setCoexPhoneInput] = useState("");
  const [busyCoexUpdate, setBusyCoexUpdate] = useState(false);

  // -- Settings --
  const [showSettings, setShowSettings] = useState<SettingsPage>(false);
  const [systemSettings, setSystemSettings] = useState<SystemSettings>(DEFAULT_SYSTEM_SETTINGS);
  const [userSettings, setUserSettings] = useState<UserSettings>(DEFAULT_USER_SETTINGS);
  const [busySettings, setBusySettings] = useState(false);

  // -- Notifications --
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // -- Refs --
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const videoInputRef = useRef<HTMLInputElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const attachMenuRef = useRef<HTMLDivElement | null>(null);
  const dotsMenuRef = useRef<HTMLDivElement | null>(null);
  const settingsMenuRef = useRef<HTMLDivElement | null>(null);
  const prevMessageCountRef = useRef(0);
  const scrollIntentRef = useRef<"load_older" | "normal">("normal");
  const markingReadContactIdRef = useRef<number | null>(null);
  const selectedContactIdRef = useRef<number | null>(null);
  const messageCacheRef = useRef<Map<number, ChatMessage[]>>(new Map());
  // Quando true, o efeito de auto-select NAO abre conversations[0]
  // automaticamente — usado apos uma desselecao explicita (ex.:
  // transferencia de atendimento) pra manter o placeholder do ChatPanel.
  // Limpado assim que o usuario seleciona qualquer conversa.
  const holdEmptySelectionRef = useRef(false);
  // Single-flight do /api/wa/contacts/all (endpoint pesado: varre a
  // agenda inteira). Sem isso, varios gatilhos concorrentes com cache
  // ainda null disparam N requisicoes identicas simultaneas (visto em
  // prod: 5 chamadas em 0,1s -> 429). Colapsa concorrentes numa so.
  const allContactsInflightRef = useRef<Promise<{ base: Contact[]; total: number }> | null>(null);
  // UID Firebase atualmente carregado. Usado p/ detectar TROCA de
  // identidade (logout/login/troca de conta no mesmo navegador) e zerar
  // todo estado do usuario anterior — sem zerar em refresh de token
  // (~1h, mesmo uid). Evita vazamento LGPD entre sessoes (ex.: operador
  // logando no PC de um admin via dados ainda em memoria).
  const loadedUidRef = useRef<string | null>(null);

  // -- Derived --
  const snapshotMode = transportMode === "snapshot" && config?.data_backend === "firestore" && config?.firestore.snapshot_enabled && firebaseReady(config) && Boolean(bundle);
  const selectedContact = selectedContactId != null ? (contactsById.get(selectedContactId) || null) : null;
  const activeContact = activeConversationId != null ? (contactsById.get(activeConversationId) || null) : null;
  const isManagerRole = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";

  const botEnabled = systemSettings.bot_enabled;
  // Fase 3.D: filtros operam sobre conversations (sub-threads por canal).
  // Mesmo wa_id em 2 canais = 2 entradas distintas em cada filtro. Campos
  // que pertencem ao contato (qualification, bot_completed, notes) sao
  // resolvidos via contactsById; o resto vem da propria conversation
  // (assigned_to, department_id, source_channel_type, unread_count).
  // Bot: sem atribuicao, no fluxo do bot (ainda nao completaram)
  const botConversations = useMemo(() => {
    if (!botEnabled) return [] as Conversation[];
    return conversations.filter((conv) => {
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      return c.qualification !== "nao_qualificado" && !c.bot_completed;
    });
  }, [botEnabled, conversations, contactsById]);
  // Novos: pool sem dono. Exige thread SEM dono (conv.assigned_to) E lead SEM
  // dono (contact.assigned_to) — senao threads orfas de leads ja atribuidos
  // (ex.: reassign-lead muda so o contato, nao a thread) vazariam pra ca.
  // Com bot ativo, so threads que ja completaram bot.
  // Operador comum so ve threads do seu departamento (ou sem); admin/supervisor veem todas.
  const novosConversations = useMemo(() => {
    return conversations.filter((conv) => {
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      if (c.assigned_to) return false;
      if (c.qualification === "nao_qualificado") return false;
      if (botEnabled && !c.bot_completed) return false;
      if (!isManagerRole && conv.department_id != null && conv.department_id !== sessionUser?.department_id) return false;
      return true;
    });
  }, [conversations, contactsById, botEnabled, isManagerRole, sessionUser?.department_id]);
  // Meus: atribuidas ao usuario logado (inclui coexistence auto-atribuidas)
  const meusConversations = useMemo(
    () => conversations.filter((conv) => conv.assigned_to === sessionUser?.id),
    [conversations, sessionUser?.id],
  );
  // Nao qualificadas: qualification do contato e "nao_qualificado"
  const nqConversations = useMemo(() => {
    return conversations.filter((conv) => {
      const c = contactsById.get(conv.contact_id);
      return c?.qualification === "nao_qualificado";
    });
  }, [conversations, contactsById]);
  // Equipe: atribuidas a outros operadores. Operadores comuns nao veem
  // coexistence de outros; admin/supervisor veem tudo.
  const equipeConversations = useMemo(() => {
    return conversations.filter((conv) => {
      if (!conv.assigned_to || conv.assigned_to === sessionUser?.id) return false;
      if (!isManagerRole && conv.source_channel_type === "coexistence") return false;
      return true;
    });
  }, [conversations, isManagerRole, sessionUser?.id]);

  // Fase 3.D: unread agregado e a soma das conversations daquela view.
  // Single source of truth — coerente com mark-read otimista por thread.
  const sumUnread = (list: Conversation[]) =>
    list.reduce((s, conv) => s + (conv.unread_count ?? conv.unread ?? 0), 0);
  const botUnread = sumUnread(botConversations);
  const novosUnread = sumUnread(novosConversations);
  const meusUnread = sumUnread(meusConversations);
  const nqUnread = sumUnread(nqConversations);
  const equipeUnread = sumUnread(equipeConversations);
  const equipeFiltered = equipeOperatorFilter
    ? equipeConversations.filter((conv) => String(conv.assigned_to) === equipeOperatorFilter)
    : equipeConversations;

  const viewConversations = activeView === "bot" ? botConversations
    : activeView === "novos" ? novosConversations
    : activeView === "meus" ? meusConversations
    : activeView === "equipe" ? equipeFiltered
    : nqConversations;
  // Search e qualification filter operam no contato (denormalizado pra UX).
  const filteredConversations = viewConversations.filter((conv) => {
    const c = contactsById.get(conv.contact_id);
    const matchesSearch = !searchText || [
      c?.display_name || "",
      c?.phone_formatted || "",
      c?.department_name || "",
      c?.assigned_name || "",
    ].join(" ").toLowerCase().includes(searchText);
    const matchesQual = !qualificationFilter || c?.qualification === qualificationFilter;
    return matchesSearch && matchesQual;
  });

  const chatSearchLower = chatSearch.trim().toLowerCase();
  const visibleMessagesFiltered = chatSearchLower ? messages.filter((m) => String(m.content || "").toLowerCase().includes(chatSearchLower)) : null;
  const hasDraft = Boolean(draft.trim());
  const busyComposerAction = busyAudio || busySend;

  const visibleMessages = messages.filter((message, index, allMessages) => {
    // Filtrar mensagens admin_only para operadores comuns
    if (message.visibility === "admin_only" && !isManagerRole) return false;
    const kind = String(message.msg_type || "").trim().toLowerCase();
    if (kind !== "unsupported" && kind !== "unknown") return true;
    const nextMessage = allMessages[index + 1];
    if (!nextMessage || nextMessage.direction !== message.direction || !nextMessage.media_path) return true;
    const currentMoment = messageMoment(message.timestamp_wa || message.created_at);
    const nextMoment = messageMoment(nextMessage.timestamp_wa || nextMessage.created_at);
    if (Number.isNaN(currentMoment) || Number.isNaN(nextMoment)) return true;
    return (nextMoment - currentMoment) > 60_000;
  });

  // =========================================================================
  // Recording helpers
  // =========================================================================
  function clearRecordingTimer() {
    if (recordingTimerRef.current) { window.clearInterval(recordingTimerRef.current); recordingTimerRef.current = null; }
  }
  function releaseAudioStream() {
    if (mediaStreamRef.current) { mediaStreamRef.current.getTracks().forEach((t) => t.stop()); mediaStreamRef.current = null; }
  }
  function discardRecording() {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") { try { recorder.stop(); } catch { /* ignore */ } }
    mediaRecorderRef.current = null;
    releaseAudioStream();
    audioChunksRef.current = [];
    setRecording(false);
    setRecordingSeconds(0);
  }

  function rememberConversationMessages(contactId: number, nextMessages: ChatMessage[]) {
    const cache = messageCacheRef.current;
    if (cache.has(contactId)) cache.delete(contactId);
    cache.set(contactId, nextMessages);
    while (cache.size > RECENT_CONVERSATION_CACHE_LIMIT) {
      const oldestKey = cache.keys().next().value;
      if (oldestKey == null) break;
      cache.delete(oldestKey);
    }
  }

  function commitConversationMessages(contactId: number, nextMessages: ChatMessage[]) {
    rememberConversationMessages(contactId, nextMessages);
    if (selectedContactIdRef.current === contactId) {
      startTransition(() => setMessages(nextMessages));
    }
  }

  function restoreConversationFromCache(contactId: number | null) {
    if (!contactId) {
      startTransition(() => setMessages([]));
      return;
    }
    const cachedMessages = messageCacheRef.current.get(contactId) || [];
    startTransition(() => setMessages(cachedMessages));
  }

  function applyConversationReadLocally(contactId: number, conversationId?: string | null) {
    const cachedMessages = messageCacheRef.current.get(contactId);
    if (cachedMessages) {
      rememberConversationMessages(contactId, cachedMessages.map((message) => (
        message.direction === "inbound" && message.status === "received"
          ? { ...message, status: "read" }
          : message
      )));
    }
    startTransition(() => {
      // Fase 3: zera unread da conversation alvo (se houver), nao do contato
      // inteiro — outras threads do mesmo contato podem ter unread proprio.
      if (conversationId) {
        setConversations((prev) => prev.map((conv) => (
          conv.id === conversationId ? { ...conv, unread: 0, unread_count: 0 } : conv
        )));
      } else {
        setContacts((prev) => prev.map((contact) => (
          contact.id === contactId ? { ...contact, unread: 0, unread_count: 0 } : contact
        )));
      }
      if (selectedContactIdRef.current === contactId) {
        setMessages((prev) => {
          const nextMessages = prev.map((message) => (
            message.contact_id === contactId && message.direction === "inbound" && message.status === "received"
              ? { ...message, status: "read" }
              : message
          ));
          rememberConversationMessages(contactId, nextMessages);
          return nextMessages;
        });
      }
    });
  }

  function buildContactSnapshotTargets() {
    if (!bundle?.db || !config?.firestore.collections.wa_contacts || !sessionUser) return [];

    const waContacts = collection(bundle.db, config.firestore.collections.wa_contacts);
    const baseConstraints = [where("is_archived", "==", 0), orderBy("last_message_at", "desc"), firestoreLimit(50)] as const;

    if (sessionUser.role === "admin" || sessionUser.role === "supervisor") {
      return [{ key: "all", ref: query(waContacts, ...baseConstraints) }];
    }

    const targets: { key: string; ref: ReturnType<typeof query> }[] = [
      { key: "unassigned:blank", ref: query(waContacts, where("assigned_to_uid", "==", ""), ...baseConstraints) },
      { key: "unassigned:null", ref: query(waContacts, where("assigned_to_uid", "==", null), ...baseConstraints) },
    ];

    if (sessionUser.firebase_uid) {
      targets.push({
        key: `mine:${sessionUser.firebase_uid}`,
        ref: query(waContacts, where("assigned_to_uid", "==", sessionUser.firebase_uid), ...baseConstraints),
      });
    }

    // Isolamento LGPD: operador comum NAO ve a agenda de colegas do mesmo
    // departamento. O target por department_id vazava os contatos pessoais
    // (coexistence) de um operador para os demais do departamento. So
    // proprios + pool sem dono; admin/supervisor (acima) seguem vendo tudo.

    return targets;
  }

  function mergeVisibleContacts(groups: Contact[][]) {
    const merged = new Map<number, Contact>();
    for (const group of groups) {
      for (const contact of group) {
        merged.set(contact.id, contact);
      }
    }
    return Array.from(merged.values())
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""))
      .slice(0, 50);
  }

  // Escopo de conversations por operador — espelha buildContactSnapshotTargets.
  // Admin/supervisor: todas as conversas do tenant (paridade com contatos).
  // Operador comum: so atribuidas a si, sem dono, ou do seu departamento.
  // Sem orderBy/limit de proposito: queries de igualdade simples nao exigem
  // indice composto novo (Fase 1 nao mexe em indices/rules). Ordenacao e
  // dedupe sao feitos client-side em mergeVisibleConversations.
  function buildConversationSnapshotTargets() {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations || !sessionUser) return [];

    const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);

    if (sessionUser.role === "admin" || sessionUser.role === "supervisor") {
      return [{ key: "all", ref: query(waConversations) }];
    }

    const targets: { key: string; ref: ReturnType<typeof query> }[] = [
      { key: "unassigned:blank", ref: query(waConversations, where("assigned_to_uid", "==", "")) },
      { key: "unassigned:null", ref: query(waConversations, where("assigned_to_uid", "==", null)) },
    ];

    if (sessionUser.firebase_uid) {
      targets.push({
        key: `mine:${sessionUser.firebase_uid}`,
        ref: query(waConversations, where("assigned_to_uid", "==", sessionUser.firebase_uid)),
      });
    }

    // Isolamento LGPD: operador comum NAO ve conversas de colegas do mesmo
    // departamento (mesma regra dos contatos). So proprias + pool sem dono;
    // admin/supervisor (acima) seguem vendo todas.

    return targets;
  }

  function mergeVisibleConversations(groups: Conversation[][]) {
    const merged = new Map<string, Conversation>();
    for (const group of groups) {
      for (const conv of group) {
        merged.set(conv.id, conv);
      }
    }
    return Array.from(merged.values())
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""));
  }

  // =========================================================================
  // Effects
  // =========================================================================

  // Boot
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const c = await getJson<ClientConfig>(null, "/api/client-config");
        if (cancelled) return;
        setConfig(c);
        setTransportMode(transportPref() || c.chat_delivery_mode || "snapshot");
        if (c.auth_mode === "firebase" && firebaseReady(c)) setBundle(await initializeFirebaseBundle(c.firebase_web_config));
      } catch (e) { if (!cancelled) setError(errorText(e)); }
      finally { if (!cancelled) setBooting(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // Zera TODO estado sensivel/por-usuario em memoria. Chamado ao
  // deslogar e ao TROCAR de identidade (antes de carregar a nova
  // sessao). Sem isso, dados do usuario anterior — em especial o
  // allContactsCache (agenda inteira carregada por um admin) e os
  // arrays contacts/conversations — ficam visiveis ao proximo usuario
  // ate um hard refresh (vazamento LGPD em PC compartilhado).
  function resetUserScopedState() {
    setContacts([]);
    setConversations([]);
    setMessages([]);
    setAllContactsCache(null);
    setAllContactsCacheTotal(0);
    allContactsInflightRef.current = null;
    messageCacheRef.current.clear();
    setSelectedThreadId(null);
    setActiveThreadId(null);
    setActiveConversationId(null);
    holdEmptySelectionRef.current = false;
    setOperators([]);
    setDepartments([]);
    setChannels([]);
    setDraft("");
    setReplyTarget(null);
    setSearch("");
    setQualificationFilter("");
    setEquipeOperatorFilter("");
    setNotice("");
    setError("");
  }

  // Auth listener
  useEffect(() => {
    if (!bundle) return undefined;
    return onIdTokenChanged(bundle.auth, async (user) => {
      setFirebaseUser(user);
      const newUid = user?.uid ?? null;
      // Logout OU troca de identidade -> limpa tudo do usuario anterior
      // ANTES de carregar a nova sessao. Refresh de token (mesmo uid)
      // NAO reseta (senao limparia a sessao ativa a cada ~1h).
      if (newUid !== loadedUidRef.current) {
        resetUserScopedState();
        loadedUidRef.current = newUid;
      }
      if (!user) { setSessionUser(null); return; }
      try {
        const session = await getJson<{
          user: SessionUser;
          tenant_id?: string;
          firestore_collections?: Record<string, string>;
        }>(bundle.auth, "/api/session");
        const [ops, deps, chs] = await Promise.all([
          getJson<Operator[]>(bundle.auth, "/api/operators"),
          getJson<{ departments: Department[] }>(bundle.auth, "/api/departments"),
          getJson<{ channels: Channel[] }>(bundle.auth, "/api/admin/channels").catch(() => ({ channels: [] as Channel[] })),
        ]);
        setSessionUser(session.user);
        setOperators(ops);
        setDepartments(deps.departments);
        setChannels(chs.channels);
        setError("");
        // Fase 2: sobrescreve paths das colecoes Firestore com versoes
        // scopadas ao tenant. Snapshot listeners passam a ler de
        // tenants/{tenant_id}/* em vez de colecao flat.
        if (session.firestore_collections) {
          setConfig((prev) => prev ? {
            ...prev,
            firestore: {
              ...prev.firestore,
              collections: { ...prev.firestore.collections, ...session.firestore_collections! },
            },
          } : prev);
        }
        Promise.all([
          getJson<SystemSettings>(bundle.auth, "/api/settings/system"),
          getJson<UserSettings>(bundle.auth, "/api/settings/user"),
        ]).then(([sys, usr]) => { setSystemSettings(sys); setUserSettings(usr); }).catch(() => {});
      } catch (e) { setError(errorText(e)); await signOut(bundle.auth); }
    });
  }, [bundle]);

  // Auto-select primeira conversation se nada selecionado (ou seleção orfã).
  // Excecao: apos desselecao explicita (holdEmptySelectionRef, ex.:
  // transferencia) mantem o placeholder em vez de pular pra conversations[0].
  useEffect(() => {
    if (selectedThreadId) {
      // Algo selecionado -> cancela o "segurar vazio". Se a conversa saiu
      // da lista (orfa), mantem o comportamento legado: pula pra 1a ou
      // limpa se a lista esvaziou.
      holdEmptySelectionRef.current = false;
      if (!conversations.some((c) => c.id === selectedThreadId)) {
        setSelectedThreadId(conversations.length ? conversations[0].id : null);
      }
      return;
    }
    if (!conversations.length) return;
    if (holdEmptySelectionRef.current) return;
    setSelectedThreadId(conversations[0].id);
  }, [conversations, selectedThreadId]);

  // Track the selected conversation and restore its recent in-memory cache immediately.
  useEffect(() => {
    selectedContactIdRef.current = selectedContactId;
    restoreConversationFromCache(selectedContactId);
    if (!selectedContactId) {
      setActiveConversationId(null);
      return undefined;
    }
    const timeoutId = window.setTimeout(() => setActiveConversationId(selectedContactId), CONVERSATION_OPEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [selectedContactId]);

  // Debounce equivalente para a thread selecionada (V2 Fase 3).
  useEffect(() => {
    if (!selectedThreadId) {
      setActiveThreadId(null);
      return undefined;
    }
    const timeoutId = window.setTimeout(() => setActiveThreadId(selectedThreadId), CONVERSATION_OPEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [selectedThreadId]);

  // Reset detail state on contact change
  useEffect(() => {
    const contact = contacts.find((c) => c.id === selectedContactId) || null;
    setQualification(contact?.qualification || "");
    setNotes(contact?.notes || "");
    setToUserId(contact?.assigned_to || "");
    setToDepartmentId(contact?.department_id || "");
    setTransferReason("");
    setTransferSummary("");
    setReplyTarget(null);
    setShowAttachMenu(false);
    setLightboxMedia(null);
    setMessageLimit(10);
    setLoadingMore(false);
    prevMessageCountRef.current = 0;
    scrollIntentRef.current = "normal";
    discardRecording();
  }, [selectedContactId]);

  // Composer auto-resize
  useEffect(() => {
    const input = composerInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }, [draft, selectedContactId, recording]);

  // Attach menu click-outside
  useEffect(() => {
    if (!showAttachMenu) return undefined;
    const handler = (e: PointerEvent) => { if (!attachMenuRef.current?.contains(e.target as Node)) setShowAttachMenu(false); };
    window.addEventListener("pointerdown", handler);
    return () => window.removeEventListener("pointerdown", handler);
  }, [showAttachMenu]);

  // Lightbox escape
  useEffect(() => {
    if (!lightboxMedia) return undefined;
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") setLightboxMedia(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightboxMedia]);

  // Cleanup recording on unmount
  useEffect(() => () => {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") { try { recorder.stop(); } catch {} }
    releaseAudioStream();
  }, []);

  // Snapshot: contacts
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    let disposed = false;
    if (!snapshotMode || !config.firestore.collections.wa_contacts) return undefined;
    const targets = buildContactSnapshotTargets();
    const partialContacts = new Map<string, Contact[]>();

    const publish = () => {
      if (disposed) return;
      const nextContacts = mergeVisibleContacts(Array.from(partialContacts.values()));
      startTransition(() => setContacts(nextContacts));
    };

    const unsubscribers = targets.map(({ key, ref }) => onSnapshot(
      ref,
      (snap) => {
        partialContacts.set(key, snap.docs.map((doc) => normalizeContact(doc.data() as Record<string, unknown>, doc.id)));
        publish();
      },
      (e) => !disposed && setError(`Snapshot de contatos falhou: ${errorText(e)}`),
    ));

    return () => {
      disposed = true;
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
    // Deps primitivas (nao os objetos config/sessionUser): onIdTokenChanged
    // dispara a cada refresh de token e recria esses objetos com os mesmos
    // valores — depender da identidade causava teardown/re-subscribe (e
    // re-leitura completa) recorrente. Re-subscreve so se o escopo mudar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundle, snapshotMode, config?.firestore.collections.wa_contacts, sessionUser?.role, sessionUser?.firebase_uid, sessionUser?.department_id]);

  // Snapshot: wa_conversations (Fase 3 — sub-threads por canal).
  // Escopado por operador (espelha o listener de contatos): operador comum
  // so recebe do servidor as conversas do seu escopo — isolamento e corte
  // de leitura. Admin/supervisor segue recebendo todas (paridade #1).
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    if (!snapshotMode || !config.firestore.collections.wa_conversations) return undefined;
    let disposed = false;
    const targets = buildConversationSnapshotTargets();
    const partialConversations = new Map<string, Conversation[]>();

    const publish = () => {
      if (disposed) return;
      const next = mergeVisibleConversations(Array.from(partialConversations.values()));
      startTransition(() => setConversations(next));
    };

    const unsubscribers = targets.map(({ key, ref }) => onSnapshot(
      ref,
      (snap) => {
        if (disposed) return;
        partialConversations.set(key, snap.docs.map((doc) => normalizeConversation(doc.data() as Record<string, unknown>, doc.id)));
        publish();
      },
      (e) => !disposed && setError(`Snapshot de conversations falhou: ${errorText(e)}`),
    ));

    return () => {
      disposed = true;
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
    // Deps primitivas — ver nota no listener de contatos acima.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundle, snapshotMode, config?.firestore.collections.wa_conversations, sessionUser?.role, sessionUser?.firebase_uid, sessionUser?.department_id]);

  // Snapshot: selected conversation/thread
  // V2 Fase 3: se activeThreadId setado, filtra por conversation_id
  // (mostra so mensagens daquele canal). Senao, fallback para contact_id
  // (timeline cross-channel — comportamento legado).
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    if (!snapshotMode) return undefined;
    if (!activeConversationId || !config.firestore.collections.wa_messages) return undefined;
    let disposed = false;
    const baseRef = collection(bundle.db, config.firestore.collections.wa_messages);
    const messagesQuery = activeThreadId
      ? query(baseRef, where("conversation_id", "==", activeThreadId), orderBy("timestamp_wa", "desc"), firestoreLimit(messageLimit))
      : query(baseRef, where("contact_id", "==", activeConversationId), orderBy("timestamp_wa", "desc"), firestoreLimit(messageLimit));
    const unsubscribe = onSnapshot(
      messagesQuery,
      (snap) => {
        // Ordena por timestamp_wa (data real da mensagem), com fallback
        // para created_at em system messages legadas sem timestamp_wa.
        const nextMessages = snap.docs.map((doc) => normalizeMessage(doc.data(), doc.id)).sort((a, b) => {
          const ta = a.timestamp_wa || a.created_at || "";
          const tb = b.timestamp_wa || b.created_at || "";
          return ta.localeCompare(tb);
        });
        commitConversationMessages(activeConversationId, nextMessages);
      },
      (e) => !disposed && setError(`Snapshot da conversa falhou: ${errorText(e)}`),
    );
    return () => { disposed = true; unsubscribe(); };
  }, [activeConversationId, activeThreadId, bundle, config, sessionUser, snapshotMode, messageLimit]);

  // Polling fallback
  useEffect(() => {
    if (!bundle || !sessionUser || !config || snapshotMode) return undefined;
    let disposed = false;
    let intervalId = 0;

    const loadContacts = async () => {
      const r = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
      if (!disposed) startTransition(() => setContacts(r.contacts));
    };
    const loadConversations = async () => {
      try {
        const r = await getJson<{ conversations: Conversation[] }>(bundle.auth, "/api/wa/conversations");
        if (!disposed) startTransition(() => setConversations(r.conversations || []));
      } catch (e) {
        // Endpoint pode nao existir em ambientes legados; fallback silencioso.
        if (!disposed) setConversations([]);
      }
    };
    const loadMessages = async (cid: number) => {
      // V2 Fase 3: se ha thread selecionada, passa conversation_id como
      // query param para filtrar mensagens daquela thread especifica.
      const threadParam = activeThreadId ? `&conversation_id=${encodeURIComponent(activeThreadId)}` : "";
      const r = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${cid}?limit=${messageLimit}${threadParam}`);
      if (!disposed) commitConversationMessages(cid, r.messages);
    };
    const tick = async () => {
      try {
        await Promise.all([loadContacts(), loadConversations()]);
        if (activeConversationId) await loadMessages(activeConversationId);
      } catch (e) {
        if (!disposed) setError(errorText(e));
      }
    };

    void tick();
    intervalId = window.setInterval(() => { void tick(); }, config.polling_interval_ms || 15000);
    return () => { disposed = true; if (intervalId) window.clearInterval(intervalId); };
  }, [activeConversationId, activeThreadId, bundle, config, sessionUser, snapshotMode, messageLimit]);

  // Mark selected conversation as read explicitly
  useEffect(() => {
    if (!bundle || !sessionUser || !activeConversationId) return undefined;
    if (selectedContactId !== activeConversationId) return undefined;
    const unreadCount = activeContact?.unread_count ?? activeContact?.unread ?? 0;
    if (markingReadContactIdRef.current && markingReadContactIdRef.current !== activeConversationId) {
      markingReadContactIdRef.current = null;
    }
    if (unreadCount <= 0) {
      if (markingReadContactIdRef.current === activeConversationId) markingReadContactIdRef.current = null;
      return undefined;
    }
    if (markingReadContactIdRef.current === activeConversationId) return undefined;

    // Fase 2C: marca thread aberta como lida (se houver). Sem thread,
    // cai no endpoint legado por contact_id (timeline cross-channel).
    const threadIdAtMark = activeThreadId;
    const readPath = threadIdAtMark
      ? `/api/wa/conversation/${encodeURIComponent(threadIdAtMark)}/read`
      : `/api/wa/contact/${activeConversationId}/read`;

    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      if (cancelled) return;
      markingReadContactIdRef.current = activeConversationId;
      void sendJson<{ status: string; updated_count: number }>(bundle.auth, readPath, {})
        .then(() => {
          if (cancelled) return;
          markingReadContactIdRef.current = null;
          applyConversationReadLocally(activeConversationId, threadIdAtMark);
        })
        .catch((e) => {
          if (cancelled) return;
          markingReadContactIdRef.current = null;
          setError(errorText(e));
        });
    }, CONVERSATION_READ_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [activeContact?.unread, activeContact?.unread_count, activeConversationId, activeThreadId, bundle, selectedContactId, sessionUser]);

  // =========================================================================
  // Sound notifications
  // =========================================================================

  const prevTotalUnreadRef = useRef<number | null>(null);
  const alarmIntervalRef = useRef<number | null>(null);
  const alarmAudioRef = useRef<HTMLAudioElement | null>(null);

  // Destrava o Web Audio no primeiro gesto do usuario — Chrome bloqueia o
  // AudioContext antes de qualquer interacao (warning "was not allowed to start").
  useEffect(() => { installAudioUnlock(); }, []);

  // Beep for all users when total unread increases
  useEffect(() => {
    if (!sessionUser || !systemSettings.notification_sound_enabled) {
      prevTotalUnreadRef.current = null;
      return;
    }
    const totalUnread = contacts.reduce((s, c) => s + (c.unread || 0), 0);
    const prev = prevTotalUnreadRef.current;
    prevTotalUnreadRef.current = totalUnread;
    if (prev === null) return; // first load, don't beep
    if (totalUnread > prev) {
      // New message arrived — play notification beep
      if (systemSettings.notification_sound_path) {
        const audio = new Audio(systemSettings.notification_sound_path);
        audio.volume = 0.5;
        audio.play().catch(() => {});
      } else {
        playBeep({ freq: 880, type: "sine", gain: 0.3, duration: 0.3 });
      }
    }
  }, [contacts, sessionUser, systemSettings.notification_sound_enabled, systemSettings.notification_sound_path]);

  // Repeating alarm for configured departments when messages unread > threshold
  useEffect(() => {
    if (alarmIntervalRef.current) {
      window.clearInterval(alarmIntervalRef.current);
      alarmIntervalRef.current = null;
    }
    if (alarmAudioRef.current) {
      alarmAudioRef.current.pause();
      alarmAudioRef.current = null;
    }
    if (!sessionUser || !systemSettings.alarm_enabled) return undefined;
    // Check if user's department is in the alarm list
    const userDeptId = sessionUser.department_id;
    const alarmDepts = systemSettings.alarm_department_ids || [];
    if (alarmDepts.length > 0 && (!userDeptId || !alarmDepts.includes(userDeptId))) return undefined;
    // Only active if there are alarm departments configured (empty = disabled for dept filter)
    if (alarmDepts.length === 0) return undefined;

    const thresholdMs = (systemSettings.alarm_threshold_minutes || 5) * 60 * 1000;

    const checkAlarm = () => {
      const now = Date.now();
      // Check contacts assigned to this user (or unassigned in "novos") that have unread messages
      const hasOverdueUnread = contacts.some((c) => {
        if ((c.unread || 0) <= 0) return false;
        // Only alarm for contacts assigned to this user or unassigned (novos)
        if (c.assigned_to && c.assigned_to !== sessionUser.id) return false;
        // Check if last_message_at is older than threshold
        if (!c.last_message_at) return false;
        const msgTime = new Date(c.last_message_at).getTime();
        return !isNaN(msgTime) && (now - msgTime) >= thresholdMs;
      });

      if (hasOverdueUnread) {
        if (systemSettings.alarm_sound_path) {
          if (!alarmAudioRef.current) {
            alarmAudioRef.current = new Audio(systemSettings.alarm_sound_path);
            alarmAudioRef.current.volume = 0.6;
          }
          alarmAudioRef.current.currentTime = 0;
          alarmAudioRef.current.play().catch(() => {});
        } else {
          playBeep({
            freq: 660, type: "square", gain: 0.25, duration: 0.6,
            steps: [{ freq: 880, at: 0.15 }, { freq: 660, at: 0.3 }, { freq: 880, at: 0.45 }],
          });
        }
      } else {
        // No overdue messages — stop alarm audio if playing
        if (alarmAudioRef.current) {
          alarmAudioRef.current.pause();
          alarmAudioRef.current = null;
        }
      }
    };

    // Check immediately and then every 30 seconds
    checkAlarm();
    alarmIntervalRef.current = window.setInterval(checkAlarm, 30_000);
    return () => {
      if (alarmIntervalRef.current) window.clearInterval(alarmIntervalRef.current);
      if (alarmAudioRef.current) { alarmAudioRef.current.pause(); alarmAudioRef.current = null; }
    };
  }, [contacts, sessionUser, systemSettings.alarm_enabled, systemSettings.alarm_threshold_minutes, systemSettings.alarm_department_ids, systemSettings.alarm_sound_path]);

  // =========================================================================
  // Actions
  // =========================================================================

  function buildReplyPayload() {
    if (!replyTarget) return {};
    return {
      reply_to_message_id: replyTarget.message_id,
      reply_to_preview: replyTarget.preview,
      reply_to_sender_name: replyTarget.sender_name,
    };
  }

  function appendReplyFields(form: FormData) {
    if (!replyTarget) return;
    form.append("reply_to_message_id", String(replyTarget.message_id));
    form.append("reply_to_preview", replyTarget.preview);
    form.append("reply_to_sender_name", replyTarget.sender_name);
  }

  function startReplyToMessage(message: ChatMessage) {
    setReplyTarget(buildMessageReplyReference(message));
    setShowAttachMenu(false);
    setQuickSuggestions([]);
    composerInputRef.current?.focus();
  }

  function cancelReply() {
    setReplyTarget(null);
  }

  async function copyMessageTextAction(message: ChatMessage) {
    const text = messageCopyText(message);
    if (!text) {
      setError("");
      setNotice("Essa mensagem nao tem texto para copiar.");
      return;
    }
    if (!navigator.clipboard?.writeText) {
      setError("Nao foi possivel copiar a mensagem neste navegador.");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setError("");
      setNotice("Texto copiado.");
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function refreshPollingViews() {
    if (!bundle) return;
    const [cr, vr] = await Promise.all([
      getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts"),
      getJson<{ conversations: Conversation[] }>(bundle.auth, "/api/wa/conversations").catch(() => ({ conversations: [] })),
    ]);
    startTransition(() => {
      setContacts(cr.contacts);
      setConversations(vr.conversations || []);
    });
    if (selectedContactId) {
      const mr = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${selectedContactId}?limit=${messageLimit}`);
      commitConversationMessages(selectedContactId, mr.messages);
    }
  }

  async function loginWithGoogle() {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); await signInWithPopup(bundle.auth, bundle.provider); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function loginWithEmail(email: string, password: string) {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); await signInWithEmailAndPassword(bundle.auth, email, password); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function logout() { if (bundle) await signOut(bundle.auth); }

  // Resolve a chave de envio: preferimos conversation_id (thread atual)
  // — backend resolve canal pela thread, garantindo que mesmo wa_id em
  // 2 canais saia pelo canal correto. Se nao houver thread selecionada,
  // mandamos contact_id e o backend deriva a thread default.
  function buildSendTarget(): { conversation_id?: string; contact_id?: number } {
    if (selectedThreadId) return { conversation_id: selectedThreadId };
    if (selectedContact) return { contact_id: selectedContact.id };
    return {};
  }

  const [internalMode, setInternalMode] = useState(false);
  async function sendTextMessage() {
    if (!bundle || !selectedContact || !draft.trim()) return;
    if (internalMode) { await sendInternalNote(); return; }
    try {
      setBusySend(true); setError(""); setNotice("");
      let content = draft.trim();
      if (userSettings.chat_prefix_enabled && userSettings.chat_prefix_name.trim() && systemSettings.chat_prefix_roles.includes(sessionUser?.role || "")) {
        content = `${userSettings.chat_prefix_name.trim()}: ${content}`;
      }
      await sendJson(bundle.auth, "/api/wa/send", { ...buildSendTarget(), content, ...buildReplyPayload() });
      setDraft(""); setReplyTarget(null); setNotice("Mensagem enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusySend(false); }
  }

  // Modo 1 (Sussurro): grava nota interna na thread; NAO chama a Meta.
  async function sendInternalNote() {
    if (!bundle || !selectedContact || !draft.trim()) return;
    try {
      setBusySend(true); setError(""); setNotice("");
      await sendJson(bundle.auth, "/api/wa/internal-note", { ...buildSendTarget(), content: draft.trim() });
      setDraft(""); setNotice("Nota interna adicionada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusySend(false); }
  }

  async function submitText(event: FormEvent<HTMLFormElement>) { event.preventDefault(); await sendTextMessage(); }

  async function submitMedia(file: File) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true); setError(""); setNotice("");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("caption", ""); form.append("file", file);
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setReplyTarget(null); setNotice("Foto enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyUpload(false); }
  }

  async function startRecording() {
    if (!selectedContact) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") { setError("O navegador nao oferece suporte para gravacao de audio."); return; }
    try {
      setError(""); setNotice(""); setShowAttachMenu(false);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];
      let recorder: MediaRecorder;
      try { recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" }); } catch { recorder = new MediaRecorder(stream); }
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = () => { releaseAudioStream(); mediaRecorderRef.current = null; };
      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setRecording(true); setRecordingSeconds(0); clearRecordingTimer();
      recordingTimerRef.current = window.setInterval(() => setRecordingSeconds((c) => c + 1), 1000);
    } catch (e) { setError(errorText(e)); discardRecording(); }
  }

  async function sendRecordedAudio() {
    if (!bundle || !selectedContact) return;
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    try {
      setBusyAudio(true); setError(""); setNotice(""); clearRecordingTimer();
      if (recorder.state !== "inactive") { await new Promise<void>((res) => { recorder.addEventListener("stop", () => res(), { once: true }); recorder.stop(); }); }
      const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
      audioChunksRef.current = []; setRecording(false); setRecordingSeconds(0);
      if (!audioBlob.size) throw new Error("Nao foi possivel capturar o audio gravado.");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("file", audioBlob, "gravacao.webm");
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-audio", form);
      setReplyTarget(null); setNotice("Audio enviado.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); discardRecording(); }
    finally { releaseAudioStream(); mediaRecorderRef.current = null; audioChunksRef.current = []; setRecording(false); setRecordingSeconds(0); setBusyAudio(false); }
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!busySend && draft.trim()) void sendTextMessage(); }
  }

  function handleDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const value = event.target.value;
    setDraft(value);
    const trimmed = value.trim();
    if (trimmed.startsWith("/") && trimmed.length >= 1) {
      const typed = trimmed.toLowerCase();
      const allQuick = [...systemSettings.quick_messages_global, ...userSettings.quick_messages].filter((qm) => qm.shortcut && qm.message);
      const matches = allQuick.filter((qm) => { const s = qm.shortcut.startsWith("/") ? qm.shortcut.toLowerCase() : `/${qm.shortcut.toLowerCase()}`; return s.startsWith(typed); });
      setQuickSuggestions(matches);
    } else { setQuickSuggestions([]); }
  }

  function applyQuickMessage(qm: { shortcut: string; message: string }) {
    setDraft(qm.message); setQuickSuggestions([]); composerInputRef.current?.focus();
  }

  function toggleAttachMenu() { setShowAttachMenu((c) => !c); }
  function openImagePicker() { setShowAttachMenu(false); imageInputRef.current?.click(); }
  function openVideoPicker() { setShowAttachMenu(false); videoInputRef.current?.click(); }
  function openDocPicker() { setShowAttachMenu(false); documentInputRef.current?.click(); }

  async function submitFile(file: File, label: string) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true); setError(""); setNotice("");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("caption", ""); form.append("file", file);
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setReplyTarget(null); setNotice(`${label} enviado.`);
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyUpload(false); }
  }

  async function sendLocation() {
    if (!bundle || !selectedContact) return;
    setShowAttachMenu(false);
    if (!navigator.geolocation) { setError("Geolocalização não disponível neste navegador."); return; }
    try {
      setError(""); setNotice("");
      const pos = await new Promise<GeolocationPosition>((res, rej) => navigator.geolocation.getCurrentPosition(res, rej, { timeout: 10000 }));
      await sendJson(bundle.auth, "/api/wa/send-location", { ...buildSendTarget(), latitude: pos.coords.latitude, longitude: pos.coords.longitude, ...buildReplyPayload() });
      setNotice("Localização enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { const geo = e as { code?: number }; setError(geo.code ? "Permissão de localização negada ou tempo esgotado." : errorText(e)); }
  }

  async function transcribeMessage(messageId: number) {
    if (!bundle) return;
    try {
      setTranscribingMessageId(messageId); setError("");
      const result = await sendJson(bundle.auth, `/api/wa/messages/${messageId}/transcribe`, {}) as { transcription: string };
      setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, transcription: result.transcription } : m));
    } catch (e) { setError(errorText(e)); }
    finally { setTranscribingMessageId(null); }
  }

  function toggleChatSearch() { setShowChatSearch((v) => { if (v) setChatSearch(""); return !v; }); }
  function toggleDotsMenu() { setShowDotsMenu((v) => !v); }
  function closeDotsMenu() { setShowDotsMenu(false); }

  function handleImageSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return; void submitMedia(file);
  }

  function openLightbox(src: string, kind: "image" | "video", alt: string, gifLike = false) { setLightboxMedia({ src, kind, alt, gifLike }); }
  function closeLightbox() { setLightboxMedia(null); }

  function handlePrimaryAction() {
    if (busyComposerAction) return;
    // Modo interno e texto-only: nunca grava audio (que iria pra Meta).
    if (internalMode) { if (hasDraft) void sendTextMessage(); return; }
    if (recording) { void sendRecordedAudio(); return; }
    if (hasDraft) { void sendTextMessage(); return; }
    void startRecording();
  }

  async function saveQualification() {
    if (!bundle || !selectedContact) return;
    try { setBusySave(true); setError(""); setNotice(""); await putJson(bundle.auth, `/api/wa/contact/${selectedContact.id}/qualify`, { qualification, notes }); setNotice("Qualificacao atualizada."); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySave(false); }
  }

  function startEditUser(op: Operator) { setEditingUserId(op.id); setEditRole(op.role); setEditDeptId(op.department_id ?? ""); }

  async function saveUserRole(userId: number) {
    if (!bundle) return;
    try { setBusyRoleUpdate(true); setError(""); await putJson(bundle.auth, `/api/admin/users/${userId}`, { role: editRole, department_id: editDeptId || null }); setNotice("Usuario atualizado."); setEditingUserId(null); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyRoleUpdate(false); }
  }

  function startEditCoex(op: Operator) { setCoexEditingUserId(op.id); setCoexPhoneInput(op.coex_phone || ""); }
  function cancelEditCoex() { setCoexEditingUserId(null); setCoexPhoneInput(""); }
  async function saveCoex(userId: number) {
    if (!bundle) return;
    const digits = coexPhoneInput.replace(/\D/g, "");
    if (digits.length < 10) { setError("Numero invalido. Informe DDI+DDD+numero (ex: 5531999990000)."); return; }
    try { setBusyCoexUpdate(true); setError(""); await sendJson(bundle.auth, `/api/admin/users/${userId}/coex`, { phone: digits }); setNotice("Coexistence liberado para o operador."); setCoexEditingUserId(null); setCoexPhoneInput(""); setOperators(await getJson<Operator[]>(bundle.auth, "/api/operators")); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyCoexUpdate(false); }
  }
  async function revokeCoex(userId: number) {
    if (!bundle) return;
    try { setBusyCoexUpdate(true); setError(""); await deleteJson(bundle.auth, `/api/admin/users/${userId}/coex`); setNotice("Autorizacao coexistence revogada."); setCoexEditingUserId(null); setOperators(await getJson<Operator[]>(bundle.auth, "/api/operators")); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyCoexUpdate(false); }
  }

  // Takeover temporario: o snapshot realtime propaga a mudanca de status, entao
  // nao precisamos refresh manual aqui.
  async function takeoverConversation(conversationId: string, greetMessage?: string) {
    if (!bundle) return;
    try { setError(""); await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/takeover`); }
    catch (e) { setError(errorText(e)); return; }
    const msg = (greetMessage || "").trim();
    if (!msg) { setNotice("Atendimento assumido temporariamente."); return; }
    // Janela de 24h: o cliente acabou de escrever, entao em geral esta aberta.
    // Se estiver fechada, o /send recusa e avisamos (sem reverter o takeover).
    try { await sendJson(bundle.auth, `/api/wa/send`, { conversation_id: conversationId, content: msg }); setNotice("Atendimento assumido e mensagem enviada."); }
    catch (e) { setNotice("Atendimento assumido. A mensagem nao pode ser enviada: " + errorText(e)); }
  }
  async function returnConversation(conversationId: string) {
    if (!bundle) return;
    try { setError(""); await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/return`); setNotice("Atendimento devolvido ao operador de origem."); }
    catch (e) { setError(errorText(e)); }
  }

  function startCorrection(message: ChatMessage) {
    setCorrectionTarget(message);
    setDraft(message.content || "");
    composerInputRef.current?.focus();
  }

  function cancelCorrection() {
    setCorrectionTarget(null);
    setDraft("");
  }

  async function correctMessage(messageId: number, newContent: string): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusySend(true); setError("");
      const res = await sendJson(bundle.auth, "/api/wa/correct-message", { message_id: messageId, new_content: newContent }) as { corrected_message_id: number };
      // Marcar mensagem original como corrigida no state local
      setMessages(prev => prev.map(m => m.id === res.corrected_message_id ? { ...m, is_corrected: true } : m));
      setCorrectionTarget(null);
      setDraft("");
      setNotice("Correcao enviada.");
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) { setError(errorText(e)); return false; }
    finally { setBusySend(false); }
  }

  async function fetchBillingStatus(channelId: number): Promise<{ ok: boolean; has_payment_method: boolean; error?: string } | null> {
    if (!bundle) return null;
    try {
      const res = await getJson<{ ok: boolean; has_payment_method: boolean; error?: string }>(
        bundle.auth,
        `/api/wa/channel/${channelId}/billing-status`,
      );
      return res;
    } catch (e) {
      return { ok: false, has_payment_method: false, error: errorText(e) };
    }
  }

  async function fetchTemplates(channelId?: number | null): Promise<WhatsAppTemplate[]> {
    if (!bundle) return [];
    const qs = channelId ? `?channel_id=${encodeURIComponent(String(channelId))}` : "";
    try {
      const res = await getJson<{ templates: WhatsAppTemplate[] }>(bundle.auth, `/api/wa/templates${qs}`);
      return res.templates || [];
    } catch (e) {
      setError(errorText(e));
      return [];
    }
  }

  async function sendTemplate(params: {
    contactId: number;
    conversationId?: string | null;
    templateName: string;
    language: string;
    components?: TemplateSendComponent[];
  }): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusyTemplate(true); setError(""); setNotice("");
      // Prefere conversation_id explicito, depois selectedThreadId, e por
      // ultimo cai em contact_id (legado pra views que ainda nao tem thread).
      const targetConv = params.conversationId || selectedThreadId || null;
      await sendJson(bundle.auth, "/api/wa/send-template", {
        ...(targetConv ? { conversation_id: targetConv } : { contact_id: params.contactId }),
        template_name: params.templateName,
        language: params.language,
        components: params.components || [],
      });
      setNotice("Template enviado.");
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusyTemplate(false);
    }
  }

  // Reabre o atendimento via template de inatividade. {{1}}/{{2}} sao
  // resolvidos server-side (nome do cliente + data da ultima conversa) —
  // o operador nao digita nada.
  async function reopenConversation(conversationId: string, templateName?: string, language?: string): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusyTemplate(true); setError(""); setNotice("");
      await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/reopen`, {
        ...(templateName ? { template_name: templateName } : {}),
        ...(language ? { language } : {}),
      });
      setNotice("Template de reabertura enviado.");
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusyTemplate(false);
    }
  }

  async function createManualContact(declared_name: string, phone: string, channel_id?: number): Promise<Contact | null> {
    if (!bundle) return null;
    try {
      setBusyCreateContact(true); setError("");
      const payload: Record<string, unknown> = { declared_name, phone };
      if (channel_id) payload.channel_id = channel_id;
      const res = await sendJson(bundle.auth, "/api/wa/contact/manual", payload) as { contact: Record<string, unknown>; conversation_id?: string };
      const contact = normalizeContact(res.contact, String(res.contact.id));
      setContacts(prev => {
        const exists = prev.some(c => c.id === contact.id);
        if (exists) return prev.map(c => c.id === contact.id ? contact : c);
        return [contact, ...prev];
      });
      // Invalida cache do contact picker — novo contato precisa
      // aparecer no proximo open do modal.
      setAllContactsCache(null);
      setAllContactsCacheTotal(0);
      // Backend retorna conversation_id deterministico do contato manual
      // (Fase 3). Setamos a thread direto — o snapshot listener vai trazer
      // a Conversation logo em seguida.
      if (res.conversation_id) {
        setSelectedThreadId(res.conversation_id);
      }
      setActiveView("meus");
      setNotice("Contato criado.");
      return contact;
    } catch (e) { setError(errorText(e)); return null; }
    finally { setBusyCreateContact(false); }
  }

  // Garante a lista completa carregada (1x por sessao) com SINGLE-FLIGHT:
  // se ja existe uma busca em andamento, os chamadores concorrentes
  // aguardam a MESMA promessa em vez de abrir novas requisicoes pesadas.
  async function ensureAllContactsLoaded(): Promise<{ base: Contact[]; total: number }> {
    if (allContactsCache) return { base: allContactsCache, total: allContactsCacheTotal };
    if (allContactsInflightRef.current) return allContactsInflightRef.current;
    if (!bundle) return { base: [], total: 0 };
    const p = (async () => {
      const res = await getJson<{ contacts: Record<string, unknown>[]; total: number; returned: number }>(
        bundle.auth, "/api/wa/contacts/all?limit=10000",
      );
      const base = (res.contacts || []).map((c) => normalizeContact(c, String(c.id)));
      const total = res.total ?? base.length;
      setAllContactsCache(base);
      setAllContactsCacheTotal(total);
      return { base, total };
    })();
    allContactsInflightRef.current = p;
    try {
      return await p;
    } finally {
      // Libera pro proximo gatilho (em falha, permite nova tentativa —
      // mas 1 de cada vez, nunca a rajada de N simultaneas).
      allContactsInflightRef.current = null;
    }
  }

  async function loadAllContacts(q?: string): Promise<{ contacts: Contact[]; total: number }> {
    if (!bundle) return { contacts: [], total: 0 };
    // Carrega a lista completa uma vez por sessao e cacheia em memoria.
    // Busca subsequente filtra local sobre o cache (instantanea).
    let base: Contact[];
    let totalFromBackend: number;
    try {
      const r = await ensureAllContactsLoaded();
      base = r.base;
      totalFromBackend = r.total;
    } catch (e) {
      setError(errorText(e));
      return { contacts: [], total: 0 };
    }
    if (q && q.trim()) {
      const needle = q.trim().toLowerCase();
      const filtered = base.filter((c) => (
        (c.display_name || "").toLowerCase().includes(needle) ||
        (c.declared_name || "").toLowerCase().includes(needle) ||
        (c.whatsapp_profile_name || "").toLowerCase().includes(needle) ||
        (c.wa_id || "").toLowerCase().includes(needle) ||
        (c.phone_formatted || "").toLowerCase().includes(needle)
      ));
      return { contacts: filtered, total: totalFromBackend };
    }
    return { contacts: base, total: totalFromBackend };
  }

  async function loadConflicts(): Promise<ConflictLead[]> {
    if (!bundle) return [];
    const r = await getJson<{ conflicts: ConflictLead[] }>(bundle.auth, "/api/admin/conflicts");
    return r.conflicts || [];
  }

  async function refreshAllContacts(): Promise<void> {
    // Forca reload do cache. Util apos criar contato manual ou
    // se admin sabe que houve sincronizacao nova.
    setAllContactsCache(null);
    setAllContactsCacheTotal(0);
  }

  async function openConversationForContact(contact_id: number, channel_id?: number): Promise<string | null> {
    if (!bundle) return null;
    try {
      setError("");
      const payload: Record<string, unknown> = { contact_id };
      if (channel_id) payload.channel_id = channel_id;
      const res = await sendJson(bundle.auth, "/api/wa/conversation/open", payload) as {
        conversation_id: string; contact_id: number; channel_id: number;
      };
      // Insercao otimista no estado local pra evitar race com o snapshot
      // listener. Sem isso, o auto-select effect (que reseta seleção
      // quando selectedThreadId nao esta na lista de conversations)
      // sobrescreve nossa selecao antes do snapshot Firestore propagar.
      if (res.conversation_id) {
        setConversations((prev) => {
          if (prev.some((c) => c.id === res.conversation_id)) return prev;
          const optimistic = normalizeConversation({
            id: res.conversation_id,
            contact_id: res.contact_id,
            channel_id: res.channel_id,
            assigned_to: sessionUser?.id ?? null,
            assigned_to_uid: sessionUser?.firebase_uid ?? "",
            status: "open",
            unread_count: 0,
          }, res.conversation_id);
          return [optimistic, ...prev];
        });
        setSelectedThreadId(res.conversation_id);
        setActiveView("meus");
      }
      return res.conversation_id || null;
    } catch (e) {
      setError(errorText(e));
      return null;
    }
  }

  async function updateDeclaredName(contact_id: number, declared_name: string) {
    if (!bundle) return;
    try {
      setError("");
      const res = await putJson(bundle.auth, `/api/wa/contact/${contact_id}/declared-name`, { declared_name }) as { contact: Record<string, unknown> };
      const updated = normalizeContact(res.contact, String(res.contact.id));
      setContacts(prev => prev.map(c => c.id === updated.id ? updated : c));
      setNotice("Nome atualizado.");
    } catch (e) { setError(errorText(e)); }
  }

  async function assumeContact(contactId: number) {
    if (!bundle) return;
    try { setBusyAssume(true); setError(""); setNotice(""); await sendJson(bundle.auth, `/api/wa/assume/${contactId}`, {}); setNotice("Atendimento assumido."); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyAssume(false); }
  }

  async function transferContact() {
    if (!bundle || !selectedContact || !toUserId || !transferSummary.trim()) return;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      await sendJson(bundle.auth, "/api/wa/transfer", { ...buildSendTarget(), to_user_id: Number(toUserId), to_department_id: toDepartmentId ? Number(toDepartmentId) : null, reason: transferReason, summary: transferSummary });
      setTransferReason(""); setTransferSummary(""); setNotice("Atendimento transferido.");
      // Conversa saiu das maos deste operador: fecha o chat e volta pro
      // placeholder ("Selecione um contato..."). holdEmptySelectionRef
      // impede o auto-select de reabrir conversations[0].
      holdEmptySelectionRef.current = true;
      setSelectedThreadId(null);
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  // Fase 3B: reatribui SO o Dono do Lead (contact.assigned_to). Os
  // atendimentos (threads) mantem seus donos — a conversa aberta nao sai
  // da tela. Admin/supervisor.
  async function reassignLead(toUserId: number, toDeptId: number | null, reason: string, summary: string) {
    if (!bundle || !selectedContact || !toUserId) return;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      await sendJson(bundle.auth, "/api/admin/reassign-lead", { contact_id: selectedContact.id, to_user_id: toUserId, to_department_id: toDeptId, reason, summary });
      setNotice("Lead reatribuido (atendimentos mantidos).");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  // Modo 3: supervisor assume a thread (vira Dono do Atendimento; o Lead nao
  // muda). Backend avisa o lead se dentro de 24h.
  async function supervisorTakeover(conversationId: string) {
    if (!bundle) return;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/supervisor-takeover`, {});
      setNotice("Atendimento assumido pela supervisao.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  // Fase 4: fecha (fechado_manual) ou reabre (aberto) um atendimento.
  async function setAttendance(conversationId: string, status: "fechado_manual" | "aberto") {
    if (!bundle) return;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/set-attendance`, { status });
      setNotice(status === "fechado_manual" ? "Atendimento fechado." : "Atendimento reaberto.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  // Fase 5A: busca por protocolo (admin/sup). Retorna null se nao achou.
  async function loadProtocol(protocolId: string): Promise<ProtocolSearchResult | null> {
    if (!bundle || !protocolId.trim()) return null;
    try {
      return await getJson<ProtocolSearchResult>(bundle.auth, `/api/admin/protocol/${encodeURIComponent(protocolId.trim())}`);
    } catch {
      return null;
    }
  }

  function toggleSettingsMenu() { setShowSettings((prev) => prev === "menu" ? false : "menu"); }

  async function openSettingsPage(page: "chat" | "quick" | "admin" | "whatsapp" | "whatsapp-standard" | "dashboard") {
    if (!bundle) return;
    if (page === "whatsapp" || page === "whatsapp-standard") {
      setShowSettings(page);
      return;
    }
    try {
      setBusySettings(true);
      const [sys, usr] = await Promise.all([getJson<SystemSettings>(bundle.auth, "/api/settings/system"), getJson<UserSettings>(bundle.auth, "/api/settings/user")]);
      setSystemSettings(sys); setUserSettings(usr); setShowSettings(page);
    } catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveSystemSettingsAction() {
    if (!bundle) return;
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/system", systemSettings) as SystemSettings; setSystemSettings(r); setNotice("Configuracoes do sistema salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveUserSettingsAction() {
    if (!bundle) return;
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/user", userSettings) as UserSettings; setUserSettings(r); setNotice("Suas configuracoes salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  // =========================================================================
  // Value
  // =========================================================================

  const value: CrmContextValue = {
    config, bundle, firebaseUser, sessionUser, operators, departments, channels, booting, busyLogin, snapshotMode, isManagerRole,
    theme, toggleTheme,
    loginWithGoogle, loginWithEmail, logout,
    contacts, contactsById, conversations, selectedContactId, selectedContact, selectedConversation,
    selectedThreadId, setSelectedThreadId,
    activeView, setActiveView, novosConversations, meusConversations, nqConversations, equipeConversations, botConversations, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, equipeOperatorFilter, setEquipeOperatorFilter, equipeFiltered,
    messages, setMessages, visibleMessages, messageLimit, setMessageLimit, loadingMore, setLoadingMore, messagesRef, scrollIntentRef, prevMessageCountRef,
    transcribingMessageId, transcribeMessage,
    replyTarget, startReplyToMessage, cancelReply, copyMessageText: copyMessageTextAction,
    draft, setDraft, busySend, busyUpload, busyAudio, quickSuggestions, setQuickSuggestions,
    sendTextMessage, submitText, submitMedia, submitFile, sendLocation,
    handleDraftKeyDown, handleDraftChange, applyQuickMessage, handlePrimaryAction, handleImageSelected,
    internalMode, setInternalMode,
    composerInputRef, imageInputRef, videoInputRef, documentInputRef,
    showAttachMenu, setShowAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, attachMenuRef,
    recording, recordingSeconds, startRecording, sendRecordedAudio, discardRecording,
    showChatSearch, chatSearch, setChatSearch, toggleChatSearch, visibleMessagesFiltered,
    showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef,
    lightboxMedia, openLightbox, closeLightbox,
    qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary,
    createManualContact, updateDeclaredName, busyCreateContact,
    loadAllContacts, refreshAllContacts, openConversationForContact, loadConflicts,
    correctMessage, correctionTarget, startCorrection, cancelCorrection,
    fetchTemplates, sendTemplate, reopenConversation, busyTemplate, fetchBillingStatus,
    busySave, busyTransfer, busyAssume, saveQualification, assumeContact, transferContact, reassignLead, supervisorTakeover, setAttendance, loadProtocol,
    editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole,
    coexEditingUserId, coexPhoneInput, setCoexPhoneInput, busyCoexUpdate, startEditCoex, cancelEditCoex, saveCoex, revokeCoex,
    takeoverConversation, returnConversation,
    showSettings, setShowSettings, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, toggleSettingsMenu, openSettingsPage, saveSystemSettingsAction, saveUserSettingsAction, settingsMenuRef,
    search, setSearch, searchText, qualificationFilter, setQualificationFilter, filteredConversations, viewConversations,
    error, setError, notice, setNotice,
    refreshPollingViews,
  };

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
