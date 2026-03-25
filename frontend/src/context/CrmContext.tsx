import { ChangeEvent, createContext, FormEvent, KeyboardEvent, startTransition, useCallback, useContext, useDeferredValue, useEffect, useRef, useState, type ReactNode } from "react";
import { onIdTokenChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query, where } from "firebase/firestore";

import { getJson, putJson, sendForm, sendJson } from "../api";
import { initializeFirebaseBundle, type FirebaseBundle } from "../firebase";
import type {
  ActiveView, ChatMessage, ClientConfig, Contact, Department,
  Operator, SessionUser, SettingsPage, SystemSettings, TransportMode, UserSettings,
} from "../types";
import { errorText } from "../utils/errors";
import { firebaseReady } from "../utils/firebase-helpers";
import { formatRecordingTime, messageMoment } from "../utils/formatting";
import { normalizeContact, normalizeMessage } from "../utils/normalization";
import { applyTheme, themePref, transportPref } from "../utils/storage";
import type { LightboxMedia } from "../utils/media";

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
  booting: boolean;
  busyLogin: boolean;
  snapshotMode: boolean;
  isManagerRole: boolean;

  // Theme
  theme: "dark" | "light";
  toggleTheme: () => void;

  // Auth
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;

  // Contacts
  contacts: Contact[];
  selectedContactId: number | null;
  setSelectedContactId: (id: number | null) => void;
  selectedContact: Contact | null;

  // Views
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  novosContacts: Contact[];
  meusContacts: Contact[];
  nqContacts: Contact[];
  equipeContacts: Contact[];
  novosUnread: number;
  meusUnread: number;
  nqUnread: number;
  equipeUnread: number;
  equipeOperatorFilter: string;
  setEquipeOperatorFilter: (v: string) => void;
  equipeFiltered: Contact[];

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

  // Settings
  showSettings: SettingsPage;
  setShowSettings: (v: SettingsPage) => void;
  systemSettings: SystemSettings;
  setSystemSettings: React.Dispatch<React.SetStateAction<SystemSettings>>;
  userSettings: UserSettings;
  setUserSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  busySettings: boolean;
  toggleSettingsMenu: () => void;
  openSettingsPage: (page: "chat" | "quick" | "admin") => Promise<void>;
  saveSystemSettingsAction: () => Promise<void>;
  saveUserSettingsAction: () => Promise<void>;
  settingsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Sidebar search
  search: string;
  setSearch: (v: string) => void;
  searchText: string;
  qualificationFilter: string;
  setQualificationFilter: (v: string) => void;
  filteredContacts: Contact[];
  viewContacts: Contact[];

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
};

const DEFAULT_USER_SETTINGS: UserSettings = {
  chat_prefix_enabled: false,
  chat_prefix_name: "",
  quick_messages: [],
};

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
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null);
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
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [quickSuggestions, setQuickSuggestions] = useState<{ shortcut: string; message: string }[]>([]);
  const [busySend, setBusySend] = useState(false);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busyAudio, setBusyAudio] = useState(false);

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

  // -- Admin users --
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editDeptId, setEditDeptId] = useState<number | "">("");
  const [busyRoleUpdate, setBusyRoleUpdate] = useState(false);

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

  // -- Derived --
  const snapshotMode = transportMode === "snapshot" && config?.data_backend === "firestore" && config?.firestore.snapshot_enabled && firebaseReady(config) && Boolean(bundle);
  const selectedContact = contacts.find((c) => c.id === selectedContactId) || null;
  const isManagerRole = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";

  const novosContacts = contacts.filter((c) => !c.assigned_to && c.qualification !== "nao_qualificado");
  const meusContacts = contacts.filter((c) => c.assigned_to === sessionUser?.id);
  const nqContacts = contacts.filter((c) => c.qualification === "nao_qualificado");
  const equipeContacts = contacts.filter((c) => c.assigned_to && c.assigned_to !== sessionUser?.id);

  const novosUnread = novosContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const meusUnread = meusContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const nqUnread = nqContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const equipeUnread = equipeContacts.reduce((s, c) => s + (c.unread || 0), 0);
  const equipeFiltered = equipeOperatorFilter ? equipeContacts.filter((c) => String(c.assigned_to) === equipeOperatorFilter) : equipeContacts;

  const viewContacts = activeView === "novos" ? novosContacts : activeView === "meus" ? meusContacts : activeView === "equipe" ? equipeFiltered : nqContacts;
  const filteredContacts = viewContacts.filter((item) => {
    const matchesSearch = !searchText || [item.display_name, item.phone_formatted || "", item.department_name || "", item.assigned_name || ""].join(" ").toLowerCase().includes(searchText);
    const matchesQual = !qualificationFilter || item.qualification === qualificationFilter;
    return matchesSearch && matchesQual;
  });

  const chatSearchLower = chatSearch.trim().toLowerCase();
  const visibleMessagesFiltered = chatSearchLower ? messages.filter((m) => String(m.content || "").toLowerCase().includes(chatSearchLower)) : null;
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

  // Auth listener
  useEffect(() => {
    if (!bundle) return undefined;
    return onIdTokenChanged(bundle.auth, async (user) => {
      setFirebaseUser(user);
      if (!user) { setSessionUser(null); setContacts([]); setMessages([]); return; }
      try {
        const session = await getJson<{ user: SessionUser }>(bundle.auth, "/api/session");
        const [ops, deps] = await Promise.all([
          getJson<Operator[]>(bundle.auth, "/api/operators"),
          getJson<{ departments: Department[] }>(bundle.auth, "/api/departments"),
        ]);
        setSessionUser(session.user);
        setOperators(ops);
        setDepartments(deps.departments);
        setError("");
        Promise.all([
          getJson<SystemSettings>(bundle.auth, "/api/settings/system"),
          getJson<UserSettings>(bundle.auth, "/api/settings/user"),
        ]).then(([sys, usr]) => { setSystemSettings(sys); setUserSettings(usr); }).catch(() => {});
      } catch (e) { setError(errorText(e)); await signOut(bundle.auth); }
    });
  }, [bundle]);

  // Auto-select contact
  useEffect(() => {
    if (!contacts.length) { setSelectedContactId(null); return; }
    if (!selectedContactId || !contacts.some((c) => c.id === selectedContactId)) setSelectedContactId(contacts[0].id);
  }, [contacts, selectedContactId]);

  // Reset detail state on contact change
  useEffect(() => {
    const contact = contacts.find((c) => c.id === selectedContactId) || null;
    setQualification(contact?.qualification || "");
    setNotes(contact?.notes || "");
    setToUserId(contact?.assigned_to || "");
    setToDepartmentId(contact?.department_id || "");
    setTransferReason("");
    setTransferSummary("");
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

  // Data subscription (contacts + messages)
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    let disposed = false;
    let intervalId = 0;
    let unsubContacts: () => void = () => {};
    let unsubMessages: () => void = () => {};

    const loadContacts = async () => {
      const r = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
      if (!disposed) startTransition(() => setContacts(r.contacts));
    };
    const loadMessages = async (cid: number) => {
      const r = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${cid}?limit=${messageLimit}`);
      if (!disposed) startTransition(() => setMessages(r.messages));
    };

    if (snapshotMode && config.firestore.collections.wa_contacts) {
      unsubContacts = onSnapshot(
        query(collection(bundle.db, config.firestore.collections.wa_contacts), orderBy("last_message_at", "desc"), firestoreLimit(50)),
        (snap) => startTransition(() => setContacts(snap.docs.map((doc) => normalizeContact(doc.data(), doc.id)))),
        (e) => !disposed && setError(`Snapshot de contatos falhou: ${errorText(e)}`),
      );
      if (selectedContactId && config.firestore.collections.wa_messages) {
        void loadMessages(selectedContactId);
        unsubMessages = onSnapshot(
          query(collection(bundle.db, config.firestore.collections.wa_messages), where("contact_id", "==", selectedContactId), orderBy("created_at", "desc"), firestoreLimit(messageLimit)),
          (snap) => startTransition(() => setMessages(snap.docs.map((doc) => normalizeMessage(doc.data(), doc.id)).sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "")))),
          (e) => !disposed && setError(`Snapshot da conversa falhou: ${errorText(e)}`),
        );
      } else {
        startTransition(() => setMessages([]));
      }
    } else {
      const tick = async () => { try { await loadContacts(); if (selectedContactId) await loadMessages(selectedContactId); } catch (e) { if (!disposed) setError(errorText(e)); } };
      void tick();
      intervalId = window.setInterval(() => { void tick(); }, config.polling_interval_ms || 15000);
    }

    return () => { disposed = true; unsubContacts(); unsubMessages(); if (intervalId) window.clearInterval(intervalId); };
  }, [bundle, config, sessionUser, selectedContactId, snapshotMode, messageLimit]);

  // =========================================================================
  // Actions
  // =========================================================================

  async function refreshPollingViews() {
    if (!bundle) return;
    const cr = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
    startTransition(() => setContacts(cr.contacts));
    if (selectedContactId) {
      const mr = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${selectedContactId}?limit=${messageLimit}`);
      startTransition(() => setMessages(mr.messages));
    }
  }

  async function loginWithGoogle() {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); await signInWithPopup(bundle.auth, bundle.provider); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function logout() { if (bundle) await signOut(bundle.auth); }

  async function sendTextMessage() {
    if (!bundle || !selectedContact || !draft.trim()) return;
    try {
      setBusySend(true); setError(""); setNotice("");
      let content = draft.trim();
      if (userSettings.chat_prefix_enabled && userSettings.chat_prefix_name.trim() && systemSettings.chat_prefix_roles.includes(sessionUser?.role || "")) {
        content = `${userSettings.chat_prefix_name.trim()}: ${content}`;
      }
      await sendJson(bundle.auth, "/api/wa/send", { contact_id: selectedContact.id, content });
      setDraft(""); setNotice("Mensagem enviada.");
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
      form.append("contact_id", String(selectedContact.id));
      form.append("caption", ""); form.append("file", file);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setNotice("Foto enviada.");
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
      form.append("contact_id", String(selectedContact.id));
      form.append("file", audioBlob, "gravacao.webm");
      await sendForm(bundle.auth, "/api/wa/send-audio", form);
      setNotice("Audio enviado.");
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
      form.append("contact_id", String(selectedContact.id)); form.append("caption", ""); form.append("file", file);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setNotice(`${label} enviado.`);
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
      await sendJson(bundle.auth, "/api/wa/send-location", { contact_id: selectedContact.id, latitude: pos.coords.latitude, longitude: pos.coords.longitude });
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
      await sendJson(bundle.auth, "/api/wa/transfer", { contact_id: selectedContact.id, to_user_id: Number(toUserId), to_department_id: toDepartmentId ? Number(toDepartmentId) : null, reason: transferReason, summary: transferSummary });
      setTransferReason(""); setTransferSummary(""); setNotice("Atendimento transferido.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  function toggleSettingsMenu() { setShowSettings((prev) => prev === "menu" ? false : "menu"); }

  async function openSettingsPage(page: "chat" | "quick" | "admin") {
    if (!bundle) return;
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
    config, bundle, firebaseUser, sessionUser, operators, departments, booting, busyLogin, snapshotMode, isManagerRole,
    theme, toggleTheme,
    loginWithGoogle, logout,
    contacts, selectedContactId, setSelectedContactId, selectedContact,
    activeView, setActiveView, novosContacts, meusContacts, nqContacts, equipeContacts, novosUnread, meusUnread, nqUnread, equipeUnread, equipeOperatorFilter, setEquipeOperatorFilter, equipeFiltered,
    messages, setMessages, visibleMessages, messageLimit, setMessageLimit, loadingMore, setLoadingMore, messagesRef, scrollIntentRef, prevMessageCountRef,
    transcribingMessageId, transcribeMessage,
    draft, setDraft, busySend, busyUpload, busyAudio, quickSuggestions, setQuickSuggestions,
    sendTextMessage, submitText, submitMedia, submitFile, sendLocation,
    handleDraftKeyDown, handleDraftChange, applyQuickMessage, handlePrimaryAction, handleImageSelected,
    composerInputRef, imageInputRef, videoInputRef, documentInputRef,
    showAttachMenu, setShowAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, attachMenuRef,
    recording, recordingSeconds, startRecording, sendRecordedAudio, discardRecording,
    showChatSearch, chatSearch, setChatSearch, toggleChatSearch, visibleMessagesFiltered,
    showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef,
    lightboxMedia, openLightbox, closeLightbox,
    qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary,
    busySave, busyTransfer, busyAssume, saveQualification, assumeContact, transferContact,
    editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole,
    showSettings, setShowSettings, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, toggleSettingsMenu, openSettingsPage, saveSystemSettingsAction, saveUserSettingsAction, settingsMenuRef,
    search, setSearch, searchText, qualificationFilter, setQualificationFilter, filteredContacts, viewContacts,
    error, setError, notice, setNotice,
    refreshPollingViews,
  };

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
