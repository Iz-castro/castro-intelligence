import { ChangeEvent, FormEvent, KeyboardEvent, startTransition, useDeferredValue, useEffect, useRef, useState } from "react";
import { onIdTokenChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query, where } from "firebase/firestore";

import { ApiError, getJson, putJson, sendForm, sendJson } from "./api";
import { initializeFirebaseBundle, type FirebaseBundle } from "./firebase";
import type { ChatMessage, ClientConfig, Contact, Department, Operator, SessionUser, TransportMode } from "./types";

const TRANSPORT_KEY = "crm_transport_mode";
const THEME_KEY = "crm_theme";
const dtf = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

function errorText(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Erro inesperado";
}

function transportPref() {
  try {
    const mode = window.localStorage.getItem(TRANSPORT_KEY);
    return mode === "snapshot" || mode === "polling" ? mode : null;
  } catch {
    return null;
  }
}

function setTransportPref(mode: TransportMode) {
  try {
    window.localStorage.setItem(TRANSPORT_KEY, mode);
  } catch {
    return;
  }
}

function themePref(): "dark" | "light" {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    // ignore
  }
  return "dark";
}

function applyTheme(theme: "dark" | "light") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* ignore */ }
}

function firebaseReady(config: ClientConfig | null) {
  if (!config) return false;
  const item = config.firebase_web_config;
  return Boolean(item.apiKey && item.authDomain && item.projectId && item.appId);
}

function iso(value: unknown) {
  if (!value) return "";
  if (typeof value === "string") return value;
  const item = value as { toDate?: () => Date; seconds?: number; nanoseconds?: number };
  if (typeof item.toDate === "function") return item.toDate().toISOString();
  if (typeof item.seconds === "number") {
    return new Date(item.seconds * 1000 + Math.floor((item.nanoseconds || 0) / 1_000_000)).toISOString();
  }
  return String(value);
}

function num(value: unknown) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function normalizeContact(record: Record<string, unknown>, docId: string): Contact {
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
  };
}

function normalizeMessage(record: Record<string, unknown>, docId: string): ChatMessage {
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
    operator_name: String(record.operator_name || ""),
    created_at: iso(record.created_at),
    timestamp_wa: iso(record.timestamp_wa),
    transcription: String(record.transcription || ""),
  };
}

function when(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--" : dtf.format(date);
}

function formatRecordingTime(seconds: number) {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
  const rest = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function messageTypeLabel(value?: string) {
  const kind = String(value || "").trim().toLowerCase();
  if (!kind) return "mensagem";
  if (kind === "unsupported" || kind === "unknown") return "midia";
  return kind;
}

function messageContentLabel(message: ChatMessage) {
  const content = String(message.content || "").trim();
  if (!content) return "";
  const kind = String(message.msg_type || "").trim().toLowerCase();
  if (content.toLowerCase() === "[unknown]" || content.toLowerCase() === "[unsupported]" || kind === "unsupported" || kind === "unknown") {
    return "Midia nao suportada pelo payload recebido do WhatsApp.";
  }
  return content;
}

function messageMoment(value?: string) {
  if (!value) return Number.NaN;
  const date = new Date(value);
  return date.getTime();
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

function PhotoIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-9Z" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="9" cy="10" r="1.5" fill="currentColor" />
      <path d="m8 16 3.2-3.2a1.2 1.2 0 0 1 1.7 0l1.1 1.1a1.2 1.2 0 0 0 1.7 0l.3-.3a1.2 1.2 0 0 1 1.7 0L20 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="3.5" width="6" height="11" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3.5M8.5 20.5h7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19 20 12 4 5l2.7 7L4 19Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M6.7 12H20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M16.5 16.5 21 21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function DotsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="5" r="1.5" fill="currentColor" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      <circle cx="12" cy="19" r="1.5" fill="currentColor" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function VideoIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2" y="7" width="14" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 10 5-3v10l-5-3V10Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function MapPinIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="9" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

type LightboxMedia = {
  src: string;
  kind: "image" | "video";
  alt: string;
  gifLike?: boolean;
};

type ResolvedMessageMedia =
  | { kind: "image"; alt: string; gifLike: boolean; sticker: boolean }
  | { kind: "video"; alt: string; gifLike: boolean }
  | { kind: "audio" }
  | { kind: "document" };

function resolveMessageMedia(message: ChatMessage): ResolvedMessageMedia | null {
  if (!message.media_path) return null;

  const msgType = String(message.msg_type || "").toLowerCase();
  const mime = String(message.media_mime || "").toLowerCase();
  const alt = message.filename || (msgType === "sticker" ? "figurinha" : "midia");

  if (msgType === "audio" || mime.startsWith("audio/")) return { kind: "audio" };
  if (msgType === "gif") {
    if (mime.startsWith("image/")) return { kind: "image", alt, gifLike: true, sticker: false };
    return { kind: "video", alt, gifLike: true };
  }
  if (msgType === "sticker") return { kind: "image", alt, gifLike: false, sticker: true };
  if (msgType === "image" || mime.startsWith("image/")) return { kind: "image", alt, gifLike: mime === "image/gif", sticker: false };
  if (msgType === "video" || mime.startsWith("video/")) return { kind: "video", alt, gifLike: false };
  return { kind: "document" };
}

export default function App() {
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [bundle, setBundle] = useState<FirebaseBundle | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null);
  const [operators, setOperators] = useState<Operator[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null);
  const [transportMode, setTransportMode] = useState<TransportMode>("snapshot");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [qualification, setQualification] = useState("");
  const [notes, setNotes] = useState("");
  const [toUserId, setToUserId] = useState<number | "">("");
  const [toDepartmentId, setToDepartmentId] = useState<number | "">("");
  const [transferReason, setTransferReason] = useState("");
  const [transferSummary, setTransferSummary] = useState("");
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const pref = themePref();
    applyTheme(pref);
    return pref;
  });
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [showChatSearch, setShowChatSearch] = useState(false);
  const [chatSearch, setChatSearch] = useState("");
  const [showDotsMenu, setShowDotsMenu] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [lightboxMedia, setLightboxMedia] = useState<LightboxMedia | null>(null);
  const [booting, setBooting] = useState(true);
  const [busyLogin, setBusyLogin] = useState(false);
  const [busySend, setBusySend] = useState(false);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busyAudio, setBusyAudio] = useState(false);
  const [busySave, setBusySave] = useState(false);
  const [busyTransfer, setBusyTransfer] = useState(false);
  const [busyAssume, setBusyAssume] = useState(false);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editDeptId, setEditDeptId] = useState<number | "">("");
  const [busyRoleUpdate, setBusyRoleUpdate] = useState(false);
  const [transcribingMessageId, setTranscribingMessageId] = useState<number | null>(null);
  const [messageLimit, setMessageLimit] = useState(10);
  const [loadingMore, setLoadingMore] = useState(false);
  const [showSettings, setShowSettings] = useState<false | "menu" | "chat" | "quick" | "admin">(false);
  const settingsMenuRef = useRef<HTMLDivElement | null>(null);
  const [systemSettings, setSystemSettings] = useState<{
    chat_prefix_enabled: boolean;
    chat_prefix_roles: string[];
    quick_message_max: number;
    quick_messages_global: { shortcut: string; message: string }[];
  }>({ chat_prefix_enabled: false, chat_prefix_roles: ["admin", "supervisor", "operador"], quick_message_max: 20, quick_messages_global: [] });
  const [userSettings, setUserSettings] = useState<{
    chat_prefix_enabled: boolean;
    chat_prefix_name: string;
    quick_messages: { shortcut: string; message: string }[];
  }>({ chat_prefix_enabled: false, chat_prefix_name: "", quick_messages: [] });
  const [busySettings, setBusySettings] = useState(false);
  const [activeView, setActiveView] = useState<"novos" | "meus" | "nao_qualificados">("novos");
  const [qualificationFilter, setQualificationFilter] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [quickSuggestions, setQuickSuggestions] = useState<{ shortcut: string; message: string }[]>([]);
  const searchText = useDeferredValue(search.trim().toLowerCase());
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const videoInputRef = useRef<HTMLInputElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const attachMenuRef = useRef<HTMLDivElement | null>(null);
  const dotsMenuRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingTimerRef = useRef<number | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const snapshotMode = transportMode === "snapshot" && config?.data_backend === "firestore" && config?.firestore.snapshot_enabled && firebaseReady(config) && Boolean(bundle);
  const selectedContact = contacts.find((item) => item.id === selectedContactId) || null;

  const novosContacts = contacts.filter((c) => !c.assigned_to && c.qualification !== "nao_qualificado");
  const meusContacts = contacts.filter((c) => c.assigned_to === sessionUser?.id);
  const nqContacts = contacts.filter((c) => c.qualification === "nao_qualificado");
  const novosUnread = novosContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const meusUnread = meusContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const nqUnread = nqContacts.reduce((s, c) => s + (c.unread || 0), 0);

  const viewContacts = activeView === "novos" ? novosContacts : activeView === "meus" ? meusContacts : nqContacts;
  const filteredContacts = viewContacts.filter((item) => {
    const matchesSearch = !searchText || [item.display_name, item.phone_formatted || "", item.department_name || "", item.assigned_name || ""].join(" ").toLowerCase().includes(searchText);
    const matchesQual = !qualificationFilter || item.qualification === qualificationFilter;
    return matchesSearch && matchesQual;
  });
  const chatSearchLower = chatSearch.trim().toLowerCase();
  const visibleMessagesFiltered = chatSearchLower
    ? messages.filter((m) => String(m.content || "").toLowerCase().includes(chatSearchLower))
    : null;
  const hasDraft = Boolean(draft.trim());
  const busyComposerAction = busyAudio || busySend;
  const visibleMessages = messages.filter((message, index, allMessages) => {
    const kind = String(message.msg_type || "").trim().toLowerCase();
    if (kind !== "unsupported" && kind !== "unknown") return true;

    const nextMessage = allMessages[index + 1];
    if (!nextMessage || nextMessage.direction !== message.direction || !nextMessage.media_path) return true;

    const currentMoment = messageMoment(message.timestamp_wa || message.created_at);
    const nextMoment = messageMoment(nextMessage.timestamp_wa || nextMessage.created_at);
    if (Number.isNaN(currentMoment) || Number.isNaN(nextMoment)) return true;

    return (nextMoment - currentMoment) > 60_000;
  });

  function clearRecordingTimer() {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
  }

  function releaseAudioStream() {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }

  function discardRecording() {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        // Ignore recorder shutdown errors and reset local UI state.
      }
    }
    mediaRecorderRef.current = null;
    releaseAudioStream();
    audioChunksRef.current = [];
    setRecording(false);
    setRecordingSeconds(0);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const nextConfig = await getJson<ClientConfig>(null, "/api/client-config");
        if (cancelled) return;
        setConfig(nextConfig);
        setTransportMode(transportPref() || nextConfig.chat_delivery_mode || "snapshot");
        if (nextConfig.auth_mode === "firebase" && firebaseReady(nextConfig)) {
          setBundle(await initializeFirebaseBundle(nextConfig.firebase_web_config));
        }
      } catch (currentError) {
        if (!cancelled) setError(errorText(currentError));
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!bundle) return undefined;
    return onIdTokenChanged(bundle.auth, async (user) => {
      setFirebaseUser(user);
      if (!user) {
        setSessionUser(null);
        setContacts([]);
        setMessages([]);
        return;
      }
      try {
        const session = await getJson<{ user: SessionUser }>(bundle.auth, "/api/session");
        const [nextOperators, nextDepartments] = await Promise.all([
          getJson<Operator[]>(bundle.auth, "/api/operators"),
          getJson<{ departments: Department[] }>(bundle.auth, "/api/departments"),
        ]);
        setSessionUser(session.user);
        setOperators(nextOperators);
        setDepartments(nextDepartments.departments);
        setError("");
        // Carregar configuracoes em background
        Promise.all([
          getJson<typeof systemSettings>(bundle.auth, "/api/settings/system"),
          getJson<typeof userSettings>(bundle.auth, "/api/settings/user"),
        ]).then(([sys, usr]) => {
          setSystemSettings(sys);
          setUserSettings(usr);
        }).catch(() => { /* silenciar erro de settings no login */ });
      } catch (currentError) {
        setError(errorText(currentError));
        await signOut(bundle.auth);
      }
    });
  }, [bundle]);

  useEffect(() => {
    if (!contacts.length) {
      setSelectedContactId(null);
      return;
    }
    if (!selectedContactId || !contacts.some((item) => item.id === selectedContactId)) {
      setSelectedContactId(contacts[0].id);
    }
  }, [selectedContactId]);

  useEffect(() => {
    const contact = contacts.find((item) => item.id === selectedContactId) || null;
    setQualification(contact?.qualification || "");
    setNotes(contact?.notes || "");
    setToUserId(contact?.assigned_to || "");
    setToDepartmentId(contact?.department_id || "");
    setTransferReason("");
    setTransferSummary("");
    setShowAttachMenu(false);
    setLightboxMedia(null);
    setMessageLimit(10);
    discardRecording();
  }, [contacts, selectedContactId]);

  const prevMessageCountRef = useRef(0);
  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    const isLoadingOlder = prevMessageCountRef.current > 0 && messages.length > prevMessageCountRef.current && messageLimit > 10;
    if (isLoadingOlder) {
      // Manter posicao do scroll ao carregar mensagens antigas
      const newScrollHeight = container.scrollHeight;
      const prevScrollHeight = container.dataset.prevScrollHeight;
      if (prevScrollHeight) {
        container.scrollTop = newScrollHeight - Number(prevScrollHeight);
      }
    } else {
      container.scrollTop = container.scrollHeight;
    }
    prevMessageCountRef.current = messages.length;
    setLoadingMore(false);
  }, [messages, selectedContactId, messageLimit]);

  useEffect(() => {
    const container = messagesRef.current;
    if (!container || !selectedContactId) return undefined;
    const handleScroll = () => {
      if (container.scrollTop < 40 && !loadingMore) {
        container.dataset.prevScrollHeight = String(container.scrollHeight);
        setLoadingMore(true);
        setMessageLimit((prev) => prev + 15);
      }
    };
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [selectedContactId, loadingMore]);

  useEffect(() => {
    if (showSettings !== "menu") return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!settingsMenuRef.current?.contains(event.target as Node)) setShowSettings(false);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [showSettings]);

  useEffect(() => {
    const input = composerInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }, [draft, selectedContactId, recording]);

  useEffect(() => {
    if (!showAttachMenu) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!attachMenuRef.current?.contains(event.target as Node)) setShowAttachMenu(false);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [showAttachMenu]);

  useEffect(() => {
    if (!lightboxMedia) return undefined;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setLightboxMedia(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [lightboxMedia]);

  useEffect(() => () => {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        // Ignore shutdown errors on component unmount.
      }
    }
    releaseAudioStream();
  }, []);

  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    let disposed = false;
    let intervalId = 0;
    let unsubContacts: () => void = () => {};
    let unsubMessages: () => void = () => {};

    const loadContacts = async () => {
      const response = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
      if (!disposed) startTransition(() => setContacts(response.contacts));
    };

    const loadMessages = async (contactId: number) => {
      const response = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${contactId}?limit=${messageLimit}`);
      if (!disposed) startTransition(() => setMessages(response.messages));
    };

    if (snapshotMode && config.firestore.collections.wa_contacts) {
      unsubContacts = onSnapshot(
        query(collection(bundle.db, config.firestore.collections.wa_contacts), orderBy("last_message_at", "desc"), firestoreLimit(50)),
        (snap) => startTransition(() => setContacts(snap.docs.map((doc) => normalizeContact(doc.data(), doc.id)))),
        (currentError) => !disposed && setError(`Snapshot de contatos falhou: ${errorText(currentError)}`),
      );
      if (selectedContactId && config.firestore.collections.wa_messages) {
        void loadMessages(selectedContactId);
        unsubMessages = onSnapshot(
          query(
            collection(bundle.db, config.firestore.collections.wa_messages),
            where("contact_id", "==", selectedContactId),
            orderBy("created_at", "desc"),
            firestoreLimit(messageLimit),
          ),
          (snap) => startTransition(() => setMessages(
            snap.docs
              .map((doc) => normalizeMessage(doc.data(), doc.id))
              .sort((left, right) => (left.created_at || "").localeCompare(right.created_at || "")),
          )),
          (currentError) => !disposed && setError(`Snapshot da conversa falhou: ${errorText(currentError)}`),
        );
      } else {
        startTransition(() => setMessages([]));
      }
    } else {
      const tick = async () => {
        try {
          await loadContacts();
          if (selectedContactId) await loadMessages(selectedContactId);
        } catch (currentError) {
          if (!disposed) setError(errorText(currentError));
        }
      };
      void tick();
      intervalId = window.setInterval(() => { void tick(); }, config.polling_interval_ms || 15000);
    }

    return () => {
      disposed = true;
      unsubContacts();
      unsubMessages();
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [bundle, config, sessionUser, selectedContactId, snapshotMode, messageLimit]);

  async function refreshPollingViews() {
    if (!bundle) return;
    const contactsResponse = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
    startTransition(() => setContacts(contactsResponse.contacts));
    if (selectedContactId) {
      const messagesResponse = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${selectedContactId}?limit=${messageLimit}`);
      startTransition(() => setMessages(messagesResponse.messages));
    }
  }

  async function loginWithGoogle() {
    if (!bundle) return;
    try {
      setBusyLogin(true);
      setError("");
      await signInWithPopup(bundle.auth, bundle.provider);
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyLogin(false);
    }
  }

  async function logout() {
    if (bundle) await signOut(bundle.auth);
  }

  async function sendTextMessage() {
    if (!bundle || !selectedContact || !draft.trim()) return;
    try {
      setBusySend(true);
      setError("");
      setNotice("");
      let content = draft.trim();
      // Aplicar prefixo se habilitado
      if (userSettings.chat_prefix_enabled && userSettings.chat_prefix_name.trim() && systemSettings.chat_prefix_roles.includes(sessionUser?.role || "")) {
        content = `${userSettings.chat_prefix_name.trim()}: ${content}`;
      }
      await sendJson(bundle.auth, "/api/wa/send", { contact_id: selectedContact.id, content });
      setDraft("");
      setNotice("Mensagem enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusySend(false);
    }
  }

  async function submitText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendTextMessage();
  }

  async function submitMedia(file: File) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true);
      setError("");
      setNotice("");
      const form = new FormData();
      form.append("contact_id", String(selectedContact.id));
      form.append("caption", "");
      form.append("file", file);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setNotice("Foto enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyUpload(false);
    }
  }

  async function startRecording() {
    if (!selectedContact) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") {
      setError("O navegador nao oferece suporte para gravacao de audio.");
      return;
    }
    try {
      setError("");
      setNotice("");
      setShowAttachMenu(false);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];

      let recorder: MediaRecorder;
      try {
        recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      } catch {
        recorder = new MediaRecorder(stream);
      }

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        releaseAudioStream();
        mediaRecorderRef.current = null;
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setRecording(true);
      setRecordingSeconds(0);
      clearRecordingTimer();
      recordingTimerRef.current = window.setInterval(() => setRecordingSeconds((current) => current + 1), 1000);
    } catch (currentError) {
      setError(errorText(currentError));
      discardRecording();
    }
  }

  async function sendRecordedAudio() {
    if (!bundle || !selectedContact) return;
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    try {
      setBusyAudio(true);
      setError("");
      setNotice("");
      clearRecordingTimer();
      if (recorder.state !== "inactive") {
        await new Promise<void>((resolve) => {
          recorder.addEventListener("stop", () => resolve(), { once: true });
          recorder.stop();
        });
      }

      const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
      audioChunksRef.current = [];
      setRecording(false);
      setRecordingSeconds(0);

      if (!audioBlob.size) throw new Error("Nao foi possivel capturar o audio gravado.");

      const form = new FormData();
      form.append("contact_id", String(selectedContact.id));
      form.append("file", audioBlob, "gravacao.webm");
      await sendForm(bundle.auth, "/api/wa/send-audio", form);
      setNotice("Audio enviado.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
      discardRecording();
    } finally {
      releaseAudioStream();
      mediaRecorderRef.current = null;
      audioChunksRef.current = [];
      setRecording(false);
      setRecordingSeconds(0);
      setBusyAudio(false);
    }
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busySend && draft.trim()) void sendTextMessage();
    }
  }

  function handleDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const value = event.target.value;
    setDraft(value);

    // Detectar atalhos de mensagem rapida
    const trimmed = value.trim();
    if (trimmed.startsWith("/") && trimmed.length >= 1) {
      const typed = trimmed.toLowerCase();
      const allQuick = [
        ...systemSettings.quick_messages_global,
        ...userSettings.quick_messages,
      ].filter((qm) => qm.shortcut && qm.message);
      const matches = allQuick.filter((qm) => {
        const shortcut = qm.shortcut.startsWith("/") ? qm.shortcut.toLowerCase() : `/${qm.shortcut.toLowerCase()}`;
        return shortcut.startsWith(typed);
      });
      setQuickSuggestions(matches);
    } else {
      setQuickSuggestions([]);
    }
  }

  function applyQuickMessage(qm: { shortcut: string; message: string }) {
    setDraft(qm.message);
    setQuickSuggestions([]);
    composerInputRef.current?.focus();
  }

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  function toggleSettingsMenu() {
    setShowSettings((prev) => prev === "menu" ? false : "menu");
  }

  async function openSettingsPage(page: "chat" | "quick" | "admin") {
    if (!bundle) return;
    try {
      setBusySettings(true);
      const [sys, usr] = await Promise.all([
        getJson<typeof systemSettings>(bundle.auth, "/api/settings/system"),
        getJson<typeof userSettings>(bundle.auth, "/api/settings/user"),
      ]);
      setSystemSettings(sys);
      setUserSettings(usr);
      setShowSettings(page);
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusySettings(false);
    }
  }

  async function saveSystemSettingsAction() {
    if (!bundle) return;
    try {
      setBusySettings(true);
      const result = await putJson(bundle.auth, "/api/settings/system", systemSettings) as typeof systemSettings;
      setSystemSettings(result);
      setNotice("Configuracoes do sistema salvas.");
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusySettings(false);
    }
  }

  async function saveUserSettingsAction() {
    if (!bundle) return;
    try {
      setBusySettings(true);
      const result = await putJson(bundle.auth, "/api/settings/user", userSettings) as typeof userSettings;
      setUserSettings(result);
      setNotice("Suas configuracoes salvas.");
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusySettings(false);
    }
  }

  function toggleAttachMenu() {
    setShowAttachMenu((current) => !current);
  }

  function openImagePicker() {
    setShowAttachMenu(false);
    imageInputRef.current?.click();
  }

  function openVideoPicker() {
    setShowAttachMenu(false);
    videoInputRef.current?.click();
  }

  function openDocPicker() {
    setShowAttachMenu(false);
    documentInputRef.current?.click();
  }

  async function submitFile(file: File, label: string) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true);
      setError("");
      setNotice("");
      const form = new FormData();
      form.append("contact_id", String(selectedContact.id));
      form.append("caption", "");
      form.append("file", file);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setNotice(`${label} enviado.`);
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyUpload(false);
    }
  }

  async function sendLocation() {
    if (!bundle || !selectedContact) return;
    setShowAttachMenu(false);
    if (!navigator.geolocation) {
      setError("Geolocalização não disponível neste navegador.");
      return;
    }
    try {
      setError("");
      setNotice("");
      const position = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 })
      );
      await sendJson(bundle.auth, "/api/wa/send-location", {
        contact_id: selectedContact.id,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
      setNotice("Localização enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      const geoError = currentError as { code?: number };
      setError(geoError.code ? "Permissão de localização negada ou tempo esgotado." : errorText(currentError));
    }
  }

  async function transcribeMessage(messageId: number) {
    if (!bundle) return;
    try {
      setTranscribingMessageId(messageId);
      setError("");
      const result = await sendJson(bundle.auth, `/api/wa/messages/${messageId}/transcribe`, {}) as { transcription: string };
      setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, transcription: result.transcription } : m));
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setTranscribingMessageId(null);
    }
  }

  function toggleChatSearch() {
    setShowChatSearch((v) => {
      if (v) setChatSearch("");
      return !v;
    });
  }

  function toggleDotsMenu() {
    setShowDotsMenu((v) => !v);
  }

  function closeDotsMenu() {
    setShowDotsMenu(false);
  }

  function handleImageSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    void submitMedia(file);
  }

  function openLightbox(src: string, kind: "image" | "video", alt: string, gifLike = false) {
    setLightboxMedia({ src, kind, alt, gifLike });
  }

  function closeLightbox() {
    setLightboxMedia(null);
  }

  function handlePrimaryAction() {
    if (busyComposerAction) return;
    if (recording) {
      void sendRecordedAudio();
      return;
    }
    if (hasDraft) {
      void sendTextMessage();
      return;
    }
    void startRecording();
  }

  function renderMessageMedia(message: ChatMessage) {
    const media = resolveMessageMedia(message);
    if (!media || !message.media_path) return null;

    if (media.kind === "image") {
      const mediaClassName = ["media"];
      if (media.sticker) mediaClassName.push("sticker-media");
      if (media.gifLike) mediaClassName.push("gif-media");

      return (
        <button type="button" className={`media-button ${media.sticker ? "sticker-button" : ""}`} onClick={() => openLightbox(message.media_path || "", "image", media.alt, media.gifLike)} aria-label="Ampliar imagem">
          <img className={mediaClassName.join(" ")} src={message.media_path} alt={media.alt} loading="lazy" />
        </button>
      );
    }

    if (media.kind === "video") {
      if (media.gifLike) {
        return (
          <button type="button" className="media-button gif-button" onClick={() => openLightbox(message.media_path || "", "video", media.alt, true)} aria-label="Ampliar GIF">
            <video className="media video-media gif-video" src={message.media_path} autoPlay loop muted playsInline />
          </button>
        );
      }
      return (
        <a href={message.media_path} download={message.filename || "video"} target="_blank" rel="noreferrer" className="video-download-link">
          <VideoIcon /> <span>Baixar video{message.filename ? ` — ${message.filename}` : ""}</span>
        </a>
      );
    }

    if (media.kind === "audio") return (
      <div className="audio-container">
        <audio controls src={message.media_path} />
        {message.transcription ? (
          <p className="transcription-text">{message.transcription}</p>
        ) : (
          <button type="button" className="transcribe-btn" onClick={() => void transcribeMessage(message.id)} disabled={transcribingMessageId === message.id}>
            {transcribingMessageId === message.id ? "Transcrevendo..." : "🔤 Transcrever"}
          </button>
        )}
      </div>
    );

    return <a href={message.media_path} target="_blank" rel="noreferrer">Abrir {message.filename || "arquivo"}</a>;
  }

  async function saveQualification() {
    if (!bundle || !selectedContact) return;
    try {
      setBusySave(true);
      setError("");
      setNotice("");
      await putJson(bundle.auth, `/api/wa/contact/${selectedContact.id}/qualify`, { qualification, notes });
      setNotice("Qualificacao atualizada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusySave(false);
    }
  }

  function startEditUser(op: Operator) {
    setEditingUserId(op.id);
    setEditRole(op.role);
    setEditDeptId(op.department_id ?? "");
  }

  async function saveUserRole(userId: number) {
    if (!bundle) return;
    try {
      setBusyRoleUpdate(true);
      setError("");
      await putJson(bundle.auth, `/api/admin/users/${userId}`, { role: editRole, department_id: editDeptId || null });
      setNotice("Usuario atualizado.");
      setEditingUserId(null);
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyRoleUpdate(false);
    }
  }

  async function assumeContact(contactId: number) {
    if (!bundle) return;
    try {
      setBusyAssume(true);
      setError("");
      setNotice("");
      await sendJson(bundle.auth, `/api/wa/assume/${contactId}`, {});
      setNotice("Atendimento assumido.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyAssume(false);
    }
  }

  async function transferContact() {
    if (!bundle || !selectedContact || !toUserId || !transferSummary.trim()) return;
    try {
      setBusyTransfer(true);
      setError("");
      setNotice("");
      await sendJson(bundle.auth, "/api/wa/transfer", {
        contact_id: selectedContact.id,
        to_user_id: Number(toUserId),
        to_department_id: toDepartmentId ? Number(toDepartmentId) : null,
        reason: transferReason,
        summary: transferSummary,
      });
      setTransferReason("");
      setTransferSummary("");
      setNotice("Atendimento transferido.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (currentError) {
      setError(errorText(currentError));
    } finally {
      setBusyTransfer(false);
    }
  }

  if (booting) return <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Carregando Firebase e Firestore</h1></div></div>;
  if (config?.auth_mode !== "firebase") return <div className="screen"><div className="hero-card"><p className="eyebrow">Modo legado</p><h1>Este frontend exige Firebase Auth</h1><p>{error || "Defina AUTH_MODE=firebase para usar o CRM React."}</p></div></div>;
  if (!firebaseUser || !sessionUser) {
    return <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Entrar com Google</h1><p>{config?.allowed_email_domain ? `Use sua conta ${config.allowed_email_domain}.` : "Use uma conta Google autorizada."}</p><button className="primary" onClick={() => void loginWithGoogle()} disabled={!bundle || busyLogin}>{busyLogin ? "Conectando..." : "Entrar com Google"}</button>{error ? <div className="alert danger">{error}</div> : null}</div></div>;
  }

  const viewTitle = activeView === "novos" ? "Novos Leads" : activeView === "meus" ? "Meus Atendimentos" : "Nao Qualificados";

  return (
    <>
      <div className="crm-layout">
        <header className="crm-topbar">
          <div className="topbar-brand">
            <p className="eyebrow">Hubloc CRM</p>
          </div>
          <div className="topbar-user">
            <strong>{sessionUser.display_name}</strong>
            <span className="sub">{sessionUser.email || sessionUser.username} · <span className="chip">{sessionUser.role}</span></span>
          </div>
          <div className="topbar-actions">
            <button className="composer-icon" onClick={toggleTheme} title={theme === "dark" ? "Tema claro" : "Tema escuro"} aria-label="Alternar tema">
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <div ref={settingsMenuRef} style={{ position: "relative" }}>
              <button className="composer-icon" onClick={toggleSettingsMenu} title="Configuracoes" aria-label="Configuracoes">
                <GearIcon />
              </button>
              {showSettings === "menu" && (
                <div className="settings-dropdown">
                  <button type="button" className="attach-option" onClick={() => void openSettingsPage("chat")}>
                    <span>💬</span><span>Chat</span>
                  </button>
                  <button type="button" className="attach-option" onClick={() => void openSettingsPage("quick")}>
                    <span>⚡</span><span>Mensagens rapidas</span>
                  </button>
                  {sessionUser.role === "admin" && (
                    <button type="button" className="attach-option" onClick={() => void openSettingsPage("admin")}>
                      <span>🔧</span><span>Administracao</span>
                    </button>
                  )}
                </div>
              )}
            </div>
            <button className="ghost" style={{ padding: "0.55rem 1rem", fontSize: "0.9rem" }} onClick={() => void logout()}>Sair</button>
          </div>
        </header>
        <div className="crm-grid">
        <nav className="crm-nav">
          <button className={`nav-item ${activeView === "novos" ? "active" : ""}`} onClick={() => { setActiveView("novos"); setQualificationFilter(""); }} title="Novos leads">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="12" y1="8" x2="12" y2="14"/><line x1="9" y1="11" x2="15" y2="11"/></svg>
            <span className="nav-label">Novos</span>
            {novosUnread > 0 && <span className="nav-badge">{novosUnread > 99 ? "99+" : novosUnread}</span>}
          </button>
          <button className={`nav-item ${activeView === "meus" ? "active" : ""}`} onClick={() => { setActiveView("meus"); setQualificationFilter(""); }} title="Meus atendimentos">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            <span className="nav-label">Meus</span>
            {meusUnread > 0 && <span className="nav-badge">{meusUnread > 99 ? "99+" : meusUnread}</span>}
          </button>
          <button className={`nav-item ${activeView === "nao_qualificados" ? "active" : ""}`} onClick={() => { setActiveView("nao_qualificados"); setQualificationFilter(""); }} title="Nao qualificados">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>
            <span className="nav-label">N/Q</span>
            {nqUnread > 0 && <span className="nav-badge">{nqUnread > 99 ? "99+" : nqUnread}</span>}
          </button>
        </nav>

        <aside className="panel sidebar">
        <div className="panel-head">
          <div><p className="eyebrow">{viewTitle}</p><h2>{filteredContacts.length} conversa{filteredContacts.length !== 1 ? "s" : ""}</h2></div>
        </div>
        <div className="toolbar">
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar contato" />
          {activeView === "meus" && <select className="compact" value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}><option value="">Todos</option><option value="novo">Novo</option><option value="em_atendimento">Em atend.</option><option value="qualificado">Qualificado</option><option value="convertido">Convertido</option></select>}
        </div>
        <div className="contact-list">{filteredContacts.map((contact) => <button key={contact.id} className={`contact ${selectedContactId === contact.id ? "active" : ""}`} onClick={() => setSelectedContactId(contact.id)}><div className="avatar">{contact.contact_avatar_path ? <img src={contact.contact_avatar_path} alt={contact.display_name} /> : <span>{contact.display_name.slice(0, 1).toUpperCase()}</span>}</div><div className="contact-copy"><div className="row"><strong>{contact.display_name}</strong><span>{when(contact.last_message_at)}</span></div><div className="sub">{contact.phone_formatted || contact.wa_id}</div><div className="row"><span className="chip">{contact.qualification || "novo"}</span>{contact.unread ? <b className="badge">{contact.unread}</b> : null}</div></div></button>)}{!filteredContacts.length ? <div className="empty">{activeView === "novos" ? "Nenhum lead novo na fila." : activeView === "meus" ? "Nenhum atendimento ativo." : "Nenhum contato nao qualificado."}</div> : null}</div>
        </aside>

        <main className="panel chat-panel">
        {error ? <div className="alert danger">{error}</div> : null}
        {notice ? <div className="alert success">{notice}</div> : null}
        {selectedContact ? <>
          <div className="contact-banner">
            <div>
              <strong>{selectedContact.display_name}</strong>
              <div className="sub">{selectedContact.phone_formatted || selectedContact.wa_id} · {selectedContact.assigned_name || "Fila aberta"}</div>
              {selectedContact.attendance_protocol ? (
                <div className="sub" style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: "0.72rem", marginTop: "0.2rem" }}>
                  {selectedContact.attendance_protocol}
                  {selectedContact.attendance_started_at ? ` · inicio ${when(selectedContact.attendance_started_at)}` : ""}
                </div>
              ) : null}
            </div>
            <div className="banner-actions">
              <div className="chips">
                <span className="chip">{selectedContact.department_name || "Sem setor"}</span>
                <span className="chip">{selectedContact.qualification || "sem classificacao"}</span>
              </div>
              <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.4rem", justifyContent: "flex-end" }}>
                {!selectedContact.assigned_to || selectedContact.assigned_to !== sessionUser.id ? (
                  <button className="assume-btn" onClick={() => void assumeContact(selectedContact.id)} disabled={busyAssume}>
                    {busyAssume ? "Assumindo..." : "Assumir atendimento"}
                  </button>
                ) : null}
                <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleChatSearch} aria-label="Buscar na conversa" title="Buscar na conversa">
                  {showChatSearch ? <CloseIcon /> : <SearchIcon />}
                </button>
                <div ref={dotsMenuRef} style={{ position: "relative" }}>
                  <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleDotsMenu} aria-label="Mais opcoes" title="Mais opcoes">
                    <DotsIcon />
                  </button>
                  {showDotsMenu ? (
                    <div className="attach-menu" style={{ right: 0, left: "auto", bottom: "auto", top: "calc(100% + 0.5rem)", minWidth: 220 }}>
                      <button type="button" className="attach-option" onClick={() => { closeDotsMenu(); }}>
                        <span>📋</span><span>Templates Utility</span>
                      </button>
                      <button type="button" className="attach-option" onClick={() => { closeDotsMenu(); }}>
                        <span>📣</span><span>Templates Marketing</span>
                      </button>
                      <div style={{ height: 1, background: "var(--border)", margin: "0.3rem 0.5rem" }} />
                      <button type="button" className="attach-option" onClick={() => { if (selectedContact.attendance_protocol) navigator.clipboard.writeText(selectedContact.attendance_protocol).catch(() => {}); closeDotsMenu(); setNotice(`Protocolo copiado: ${selectedContact.attendance_protocol}`); }}>
                        <span>📋</span><span>Copiar protocolo</span>
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          {showChatSearch ? (
            <div className="toolbar">
              <input
                value={chatSearch}
                onChange={(e) => setChatSearch(e.target.value)}
                placeholder="Buscar na conversa..."
                autoFocus
              />
              {chatSearch ? <span className="sub">{(visibleMessagesFiltered ?? []).length} resultado(s)</span> : null}
            </div>
          ) : null}

          <div className="messages" ref={messagesRef}>
            {loadingMore && <div className="sub" style={{ textAlign: "center", padding: "0.5rem" }}>Carregando mensagens anteriores...</div>}
            {(visibleMessagesFiltered ?? visibleMessages).map((message) => (
              <article key={message.id} className={`bubble ${message.direction}`}>
                <header>
                  <strong>{message.direction === "outbound" ? (message.operator_name || "Equipe") : message.direction === "inbound" ? "Cliente" : "Sistema"}</strong>
                  <span>{when(message.created_at || message.timestamp_wa)}</span>
                </header>
                {messageContentLabel(message) ? <p>{messageContentLabel(message)}</p> : null}
                {renderMessageMedia(message)}
                <footer>
                  <span>{messageTypeLabel(message.msg_type)}</span>
                  {config?.feature_message_status !== false && <span>{message.status || "ok"}</span>}
                </footer>
              </article>
            ))}
            {visibleMessagesFiltered !== null && visibleMessagesFiltered.length === 0 ? (
              <div className="empty" style={{ alignSelf: "center" }}>Nenhuma mensagem encontrada para "{chatSearch}".</div>
            ) : null}
          </div>

          {quickSuggestions.length > 0 && (
            <div className="quick-suggestions">
              {quickSuggestions.map((qm, idx) => (
                <button key={idx} type="button" className="quick-suggestion-item" onClick={() => applyQuickMessage(qm)}>
                  <strong>{qm.shortcut.startsWith("/") ? qm.shortcut : `/${qm.shortcut}`}</strong>
                  <span className="sub">{qm.message.length > 80 ? qm.message.slice(0, 80) + "..." : qm.message}</span>
                </button>
              ))}
            </div>
          )}
          <form className="composer" onSubmit={submitText}>
            <div className={`composer-shell ${recording ? "is-recording" : ""}`}>
              <div className="composer-menu" ref={attachMenuRef}>
                <button type="button" className="composer-icon attach-trigger" onClick={toggleAttachMenu} disabled={!selectedContact || busyUpload || busyAudio} aria-label="Abrir menu de anexos">
                  <PlusIcon />
                </button>
                {showAttachMenu ? (
                  <div className="attach-menu">
                    <button type="button" className="attach-option" onClick={openImagePicker}><PhotoIcon /><span>Foto</span></button>
                    <button type="button" className="attach-option" onClick={openVideoPicker}><VideoIcon /><span>Vídeo</span></button>
                    <button type="button" className="attach-option" onClick={openDocPicker}><FileIcon /><span>Documento</span></button>
                    <button type="button" className="attach-option" onClick={() => void sendLocation()}><MapPinIcon /><span>Localização</span></button>
                  </div>
                ) : null}
                <input ref={imageInputRef} type="file" accept="image/*" onChange={handleImageSelected} hidden />
                <input ref={videoInputRef} type="file" accept="video/*" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Vídeo"); }} hidden />
                <input ref={documentInputRef} type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.zip,.csv" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Documento"); }} hidden />
              </div>

              <div className="composer-field">
                {recording ? <div className="recording-status"><span className="recording-dot" /><span>Gravando audio</span><strong>{formatRecordingTime(recordingSeconds)}</strong><button type="button" className="recording-cancel" onClick={discardRecording}>Cancelar</button></div> : <textarea ref={composerInputRef} value={draft} onChange={handleDraftChange} onKeyDown={handleDraftKeyDown} rows={1} placeholder="Digite uma mensagem" disabled={busySend || busyAudio} />}
              </div>

              <button type="button" className={`composer-icon mic-trigger ${recording ? "recording" : ""} ${hasDraft && !recording ? "send-ready" : ""}`} onClick={handlePrimaryAction} disabled={!selectedContact || busyUpload || busyComposerAction} aria-label={recording ? "Enviar audio gravado" : hasDraft ? "Enviar mensagem" : "Gravar audio"}>
                {busyComposerAction ? <span className="button-spinner" aria-hidden="true" /> : recording || hasDraft ? <SendIcon /> : <MicIcon />}
              </button>
            </div>
          </form>
        </> : <div className="empty large">Selecione um contato para abrir a conversa.</div>}
        </main>

        <aside className="panel detail-panel">
        <div className="panel-head"><div><p className="eyebrow">Contato</p><h2>Operacao</h2></div><span className="sub">{operators.length} operadores - {departments.length} setores</span></div>
        <div className="detail-scroll">
          {selectedContact ? <>
            <section className="card">
              <h3>Qualificacao</h3>
              <select value={qualification} onChange={(event) => setQualification(event.target.value)}>
                <option value="">Sem classificacao</option>
                <option value="novo">Novo</option>
                <option value="em_atendimento">Em atendimento</option>
                <option value="qualificado">Qualificado</option>
                <option value="nao_qualificado">Nao qualificado</option>
                <option value="convertido">Convertido</option>
              </select>
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} placeholder="Notas do atendimento" />
              <button className="primary" onClick={() => void saveQualification()} disabled={busySave}>{busySave ? "Salvando..." : "Salvar"}</button>
            </section>
            <section className="card">
              <h3>Transferencia</h3>
              <select value={toUserId} onChange={(event) => setToUserId(event.target.value ? Number(event.target.value) : "")}>
                <option value="">Selecione um operador</option>
                {operators.filter((item) => item.id !== sessionUser.id).map((item) => <option key={item.id} value={item.id}>{item.display_name} - {item.department_name || "Sem setor"}</option>)}
              </select>
              <select value={toDepartmentId} onChange={(event) => setToDepartmentId(event.target.value ? Number(event.target.value) : "")}>
                <option value="">Manter departamento atual</option>
                {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <input value={transferReason} onChange={(event) => setTransferReason(event.target.value)} placeholder="Motivo da transferencia" />
              <textarea value={transferSummary} onChange={(event) => setTransferSummary(event.target.value)} rows={4} placeholder="Resumo obrigatorio" />
              <button className="primary" onClick={() => void transferContact()} disabled={!toUserId || !transferSummary.trim() || busyTransfer}>{busyTransfer ? "Transferindo..." : "Transferir"}</button>
            </section>
          </> : <div className="empty">As acoes do contato aparecem aqui.</div>}

          {sessionUser?.role === "admin" ? (
            <section className="card">
              <h3>Usuarios e Roles</h3>
              <div className="admin-user-list">
                {operators.map((op) => (
                  <div key={op.id} className="admin-user-row">
                    <div className="admin-user-info">
                      <strong>{op.display_name}</strong>
                      <span className="sub">{op.email || ""}</span>
                    </div>
                    {editingUserId === op.id ? (
                      <div className="admin-user-edit">
                        <select value={editRole} onChange={(e) => setEditRole(e.target.value)}>
                          <option value="admin">admin</option>
                          <option value="supervisor">supervisor</option>
                          <option value="operador">operador</option>
                        </select>
                        <select value={editDeptId} onChange={(e) => setEditDeptId(e.target.value ? Number(e.target.value) : "")}>
                          <option value="">Sem setor</option>
                          {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                        </select>
                        <div style={{ display: "flex", gap: "0.4rem" }}>
                          <button className="primary" style={{ flex: 1, padding: "0.5rem" }} onClick={() => void saveUserRole(op.id)} disabled={busyRoleUpdate}>{busyRoleUpdate ? "..." : "Salvar"}</button>
                          <button className="ghost" style={{ padding: "0.5rem 0.7rem" }} onClick={() => setEditingUserId(null)}>✕</button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className="chip">{op.role}</span>
                        <button className="ghost" style={{ padding: "0.35rem 0.6rem", fontSize: "0.8rem" }} onClick={() => startEditUser(op)}>Editar</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
        </aside>
      </div>
      </div>

      {/* Modal: Chat */}
      {showSettings === "chat" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Configuracoes do Chat" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Chat</h2>
            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              {systemSettings.chat_prefix_roles.includes(sessionUser.role) ? (
                <div className="settings-block">
                  <label className="settings-toggle">
                    <input type="checkbox" checked={userSettings.chat_prefix_enabled} onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} />
                    <span>Usar prefixo (ex: <strong>Rafael:</strong> Bom dia...)</span>
                  </label>
                  {userSettings.chat_prefix_enabled && (
                    <input
                      value={userSettings.chat_prefix_name}
                      onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_name: e.target.value }))}
                      placeholder="Nome que aparecera como prefixo"
                      style={{ marginTop: "0.5rem" }}
                    />
                  )}
                </div>
              ) : (
                <div className="empty" style={{ fontSize: "0.88rem" }}>Prefixo de mensagem nao habilitado para seu cargo.</div>
              )}
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>
                {busySettings ? "Salvando..." : "Salvar"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Modal: Mensagens rapidas */}
      {showSettings === "quick" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Mensagens rapidas" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Mensagens rapidas</h2>
            <div className="settings-section">
              <h3>Minhas mensagens rapidas</h3>
              <div className="settings-block">
                {userSettings.quick_messages.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input
                      value={qm.shortcut}
                      onChange={(e) => {
                        const updated = [...userSettings.quick_messages];
                        updated[idx] = { ...updated[idx], shortcut: e.target.value };
                        setUserSettings((prev) => ({ ...prev, quick_messages: updated }));
                      }}
                      placeholder="/atalho"
                      style={{ width: 100 }}
                    />
                    <input
                      value={qm.message}
                      onChange={(e) => {
                        const updated = [...userSettings.quick_messages];
                        updated[idx] = { ...updated[idx], message: e.target.value };
                        setUserSettings((prev) => ({ ...prev, quick_messages: updated }));
                      }}
                      placeholder="Mensagem completa"
                      style={{ flex: 1 }}
                    />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => {
                      setUserSettings((prev) => ({ ...prev, quick_messages: prev.quick_messages.filter((_, i) => i !== idx) }));
                    }}>X</button>
                  </div>
                ))}
                {userSettings.quick_messages.length < systemSettings.quick_message_max ? (
                  <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => {
                    setUserSettings((prev) => ({ ...prev, quick_messages: [...prev.quick_messages, { shortcut: "", message: "" }] }));
                  }}>+ Adicionar mensagem rapida</button>
                ) : (
                  <div className="sub" style={{ fontSize: "0.82rem" }}>Limite de {systemSettings.quick_message_max} mensagens rapidas atingido.</div>
                )}
              </div>
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>
                {busySettings ? "Salvando..." : "Salvar"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Modal: Administracao (admin only) */}
      {showSettings === "admin" && sessionUser.role === "admin" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Administracao" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Administracao</h2>

            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              <div className="settings-block">
                <label className="settings-toggle">
                  <input type="checkbox" checked={systemSettings.chat_prefix_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} />
                  <span>Habilitar prefixo de mensagem (padrao do sistema)</span>
                </label>
              </div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Cargos que podem usar prefixo:</span>
                {["admin", "supervisor", "operador"].map((role) => (
                  <label key={role} className="settings-toggle" style={{ marginBottom: "0.25rem" }}>
                    <input
                      type="checkbox"
                      checked={systemSettings.chat_prefix_roles.includes(role)}
                      onChange={(e) => {
                        setSystemSettings((prev) => ({
                          ...prev,
                          chat_prefix_roles: e.target.checked
                            ? [...prev.chat_prefix_roles, role]
                            : prev.chat_prefix_roles.filter((r) => r !== role),
                        }));
                      }}
                    />
                    <span>{role}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="settings-section" style={{ marginTop: "1.2rem" }}>
              <h3>Mensagens rapidas</h3>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Limite por usuario:</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={systemSettings.quick_message_max}
                  onChange={(e) => setSystemSettings((prev) => ({ ...prev, quick_message_max: Math.max(1, Number(e.target.value) || 1) }))}
                  style={{ width: 100 }}
                />
              </div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Mensagens globais (padrao para todos):</span>
                {systemSettings.quick_messages_global.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input
                      value={qm.shortcut}
                      onChange={(e) => {
                        const updated = [...systemSettings.quick_messages_global];
                        updated[idx] = { ...updated[idx], shortcut: e.target.value };
                        setSystemSettings((prev) => ({ ...prev, quick_messages_global: updated }));
                      }}
                      placeholder="/atalho"
                      style={{ width: 100 }}
                    />
                    <input
                      value={qm.message}
                      onChange={(e) => {
                        const updated = [...systemSettings.quick_messages_global];
                        updated[idx] = { ...updated[idx], message: e.target.value };
                        setSystemSettings((prev) => ({ ...prev, quick_messages_global: updated }));
                      }}
                      placeholder="Mensagem completa"
                      style={{ flex: 1 }}
                    />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => {
                      setSystemSettings((prev) => ({ ...prev, quick_messages_global: prev.quick_messages_global.filter((_, i) => i !== idx) }));
                    }}>X</button>
                  </div>
                ))}
                <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => {
                  setSystemSettings((prev) => ({ ...prev, quick_messages_global: [...prev.quick_messages_global, { shortcut: "", message: "" }] }));
                }}>+ Adicionar mensagem global</button>
              </div>
            </div>

            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>
              {busySettings ? "Salvando..." : "Salvar configuracoes do sistema"}
            </button>
          </div>
        </div>
      ) : null}

      {lightboxMedia ? <div className="lightbox" role="dialog" aria-modal="true" aria-label="Visualizacao de midia" onClick={closeLightbox}><button type="button" className="lightbox-close" onClick={closeLightbox} aria-label="Fechar visualizacao">Fechar</button><div className="lightbox-content" onClick={(event) => event.stopPropagation()}>{lightboxMedia.kind === "image" ? <img className="lightbox-media" src={lightboxMedia.src} alt={lightboxMedia.alt} /> : <video className="lightbox-media" src={lightboxMedia.src} controls={!lightboxMedia.gifLike} autoPlay loop={lightboxMedia.gifLike} muted={lightboxMedia.gifLike} playsInline />}</div></div> : null}
    </>
  );
}
