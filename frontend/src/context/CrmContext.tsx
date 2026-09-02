import { ChangeEvent, createContext, FormEvent, KeyboardEvent, startTransition, useCallback, useContext, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { onIdTokenChanged, sendPasswordResetEmail, signInWithEmailAndPassword, signInWithPopup, signOut, getMultiFactorResolver, TotpMultiFactorGenerator, type MultiFactorError, type MultiFactorResolver, type User } from "firebase/auth";
import { collection, doc as firestoreDoc, getDocs, limit as firestoreLimit, onSnapshot, orderBy, query, where } from "firebase/firestore";

import { deleteJson, getJson, putJson, sendForm, sendJson } from "../api";
import { initializeFirebaseBundle, type FirebaseBundle } from "../firebase";
import type {
  ActiveView, Channel, ChatMessage, ClientConfig, ConflictLead, Contact, Conversation, Department,
  MessageReplyReference, Operator, PermissionKey, ProtocolSearchResult, SessionPerfil, SessionUser,
  SettingsPage, SystemSettings, TemplateSendComponent, TransportMode, UserSettings, WhatsAppTemplate,
} from "../types";
import type { QuickMessage } from "../types";
import { quickMessagesProblem } from "../utils/quickMessages";
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

// Opcao do filtro por canal do "Meus": um canal distinto entre as conversas
// do operador. label pronto pra UI ("Standard - <numero>" / "Coex - <numero>").
export type ChannelFilterOption = { id: string; type: "standard" | "coexistence"; label: string };

type CrmContextValue = {
  // Core
  config: ClientConfig | null;
  bundle: FirebaseBundle | null;
  firebaseUser: User | null;
  sessionUser: SessionUser | null;
  // Nome do tenant (dado no super-admin) — branding do topbar por tenant.
  tenantName: string;
  operators: Operator[];
  departments: Department[];
  channels: Channel[];
  booting: boolean;
  busyLogin: boolean;
  snapshotMode: boolean;
  // RBAC dinamico (M-B2): toggles efetivos da sessao + helper de checagem.
  // (Nao ha mais gate por role exportado — checagens de UI usam can(), e
  // escopo de dados usa canSeeAll; role cru so vive dentro do contexto.)
  perfil: SessionPerfil | null;
  can: (perm: PermissionKey) => boolean;
  // Escopo de dados amplo: exige o toggle E a role privilegiada — as
  // Firestore rules autorizam leitura ampla pelo claim role, entao um
  // perfil operador "ampliado" nao consegue ouvir a colecao inteira.
  canSeeAll: boolean;

  // Theme
  theme: "dark" | "light";
  toggleTheme: () => void;

  // Auth
  loginWithGoogle: () => Promise<void>;
  loginWithEmail: (email: string, password: string) => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  // MFA (TOTP): so entra em cena quando a conta tem 2o fator enrollado.
  // Operador comum (sem MFA) nunca ve isso — o login segue direto.
  mfaPending: boolean;
  resolveMfaCode: (code: string) => Promise<void>;
  cancelMfa: () => void;

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
  backupConversations: Conversation[];
  novosUnread: number;
  meusUnread: number;
  nqUnread: number;
  equipeUnread: number;
  botUnread: number;
  backupUnread: number;
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
  quickSuggestions: QuickMessage[];
  setQuickSuggestions: React.Dispatch<React.SetStateAction<QuickMessage[]>>;
  // Item da lista de mensagens rapidas destacado pelo teclado (-1 = nenhum).
  quickSelectedIndex: number;
  sendTextMessage: () => Promise<void>;
  submitText: (e: FormEvent<HTMLFormElement>) => void;
  submitMedia: (file: File) => Promise<void>;
  submitFile: (file: File, label: string) => Promise<void>;
  sendLocation: () => Promise<void>;
  handleDraftKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  handleDraftChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  applyQuickMessage: (qm: QuickMessage) => void;
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
  setAttendance: (conversationId: string, status: "fechado_manual" | "aberto", outcome?: { qualification: string; notes: string }) => Promise<boolean>;
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
  // Contador BARATO da agenda (aggregate count no backend, ~7 reads) — usado
  // pelo header da sidebar, que so exibe o numero. NAO carrega a lista.
  countAllContacts: () => Promise<number>;
  // Incrementa quando a agenda muda (contato manual criado / refresh) —
  // dependencia do useEffect do contador pra ele se atualizar sem F5.
  contactsCountNonce: number;
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
  returnContactToPool: (contactId: number) => Promise<void>;
  transferContact: () => Promise<void>;

  // Admin users
  editingUserId: number | null;
  setEditingUserId: (v: number | null) => void;
  editRole: string;
  setEditRole: (v: string) => void;
  editPerfilId: string;
  setEditPerfilId: (v: string) => void;
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
  openSettingsPage: (page: "chat" | "quick" | "admin" | "perfis" | "whatsapp" | "whatsapp-standard" | "dashboard") => Promise<void>;
  saveSystemSettingsAction: () => Promise<void>;
  saveUserSettingsAction: () => Promise<void>;
  settingsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Sidebar search
  search: string;
  setSearch: (v: string) => void;
  searchText: string;
  qualificationFilter: string;
  setQualificationFilter: (v: string) => void;
  // Filtro por canal do "Meus" (standard vs coex). Opcoes derivadas das
  // conversas do proprio operador; só ha filtro com 2+ canais.
  channelFilter: string;
  setChannelFilter: (v: string) => void;
  myChannelOptions: ChannelFilterOption[];
  filteredConversations: Conversation[];
  viewConversations: Conversation[];

  // Notifications
  error: string;
  setError: (msg: string) => void;
  notice: string;
  setNotice: (msg: string) => void;

  loadMoreMyConversations: () => Promise<void>;
  canLoadMoreMine: boolean;
  loadMorePoolConversations: () => Promise<void>;
  canLoadMorePool: boolean;
  loadMoreAllConversations: () => Promise<void>;
  canLoadMoreAll: boolean;
  loadingMoreConvs: boolean;
  // Filtro "Nao lidas" (busca alem da janela) e modo "So espiar" (admin/supervisor).
  loadUnreadConversations: (reset?: boolean) => Promise<void>;
  canLoadMoreUnread: boolean;
  unreadMode: boolean;
  peekMode: boolean;
  setPeekMode: (v: boolean) => void;
  canPeek: boolean;

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
  pool_mode: "legacy",
  auto_close_enabled: true,
  rating_request_enabled: false,
};

const DEFAULT_USER_SETTINGS: UserSettings = {
  chat_prefix_enabled: false,
  chat_prefix_name: "",
  quick_messages: [],
};

// Janela AO VIVO do admin/supervisor (target "all") e tamanho da pagina
// estatica do "Carregar mais" da Equipe. Mantidos iguais de proposito.
const ADMIN_CONV_WINDOW = 300;

const CONVERSATION_OPEN_DEBOUNCE_MS = 350;
const CONVERSATION_READ_DEBOUNCE_MS = 1200;
// Filtro "Nao lidas" do select de qualificacao (valor do option), pagina da
// busca de nao lidas e chave do modo "So espiar" (localStorage, por navegador).
const UNREAD_FILTER = "nao_lidos";
const UNREAD_PAGE = 50;
const PEEK_STORAGE_KEY = "castro_crm.peek_mode";
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
  const [tenantName, setTenantName] = useState("");
  // Perfil RBAC efetivo da sessao (M-B2). Nasce do /api/session (toggles ja
  // resolvidos com fallback de role) e e atualizado ao vivo pelo snapshot do
  // doc perfis_acesso/{id} do tenant.
  const [perfil, setPerfil] = useState<SessionPerfil | null>(null);
  const [operators, setOperators] = useState<Operator[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  // Fase 3: lista de conversations (sub-threads por canal). Mesmo wa_id em
  // dois canais aparece como duas entradas distintas.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  // Conversas FIXADAS que escapam do top-50 ao vivo mas precisam permanecer na
  // sessao: abertas explicitamente pelo picker/deep-link (openConversationForContact).
  // Sobrevivem aos re-publishes do snapshot (que reconstroem `conversations` so
  // com o top-50), evitando que o painel do operador seja derrubado. Mapa
  // conversation_id -> Conversation. Zerado no logout/troca de conta.
  const [extraConversations, setExtraConversations] = useState<Map<string, Conversation>>(new Map());
  // Camada ESTATICA de paginacao do "Meus" (operador comum): getDocs do `mine`
  // com limite crescente. O listener AO VIVO continua em 50; estas sao paginas
  // antigas carregadas sob demanda ("Carregar mais"), sem snapshot. Uma conversa
  // daqui que recebe msg sobe pro top-50 ao vivo e o dedup (live ganha) corrige.
  const [pagedConversations, setPagedConversations] = useState<Map<string, Conversation>>(new Map());
  const [myConvPageLimit, setMyConvPageLimit] = useState(50);
  const [myConvHasMore, setMyConvHasMore] = useState(true);
  // Paginacao estatica da EQUIPE (admin/supervisor): mesmo padrao do "Meus",
  // mas sobre a janela GLOBAL de 300 (ADMIN_CONV_WINDOW). Compartilha
  // pagedConversations/loadingMoreConvs com o fluxo do operador — os dois
  // caminhos sao mutuamente exclusivos por role+view.
  const [allConvPageLimit, setAllConvPageLimit] = useState(ADMIN_CONV_WINDOW);
  const [allConvHasMore, setAllConvHasMore] = useState(true);
  // Paginacao estatica da POOL sem dono (operador comum em Novos/Recepcao):
  // mesmo padrao do "Meus", sobre os targets unassigned:blank + unassigned:null
  // (limite crescente em cada um). Pedido do PO 2026-08-17. Alcanca threads da
  // pool que cairam fora do top-50 ao vivo; NAO lista lead ja devolvido ao bot
  // (reception: fechamento => bot_completed=False, a caixa filtra) — pra esse
  // caso o caminho e o picker "+" (agenda) do Meus.
  const [poolConvPageLimit, setPoolConvPageLimit] = useState(50);
  const [poolConvHasMore, setPoolConvHasMore] = useState(true);
  // Algum target sem dono do listener ao vivo (unassigned:blank | :null)
  // encheu os 50? Calculado no publish do listener — client-side nao da pra
  // separar os dois (normalizeConversation coage null -> ""), e a SOMA
  // enganaria (30+25 >= 50 sem nenhum target saturado = clique sem pagina).
  const [poolLiveSaturated, setPoolLiveSaturated] = useState(false);
  const [loadingMoreConvs, setLoadingMoreConvs] = useState(false);
  // Caixa ativa no momento em que um "Carregar mais" comecou: resposta tardia
  // do getDocs apos trocar de caixa e descartada (senao repovoava a camada
  // estatica que o reset de troca acabou de limpar).
  const activeViewRef = useRef<ActiveView>("novos");
  // Remove uma conversa das camadas ESTATICAS (fixada + paginada) — ex.: apos
  // transferir, a thread saiu das maos do operador e o ao vivo nao reentrega
  // threads fora do escopo. No-op se nao estiver nas estaticas (conversa normal
  // do top-50 e removida pelo proprio listener).
  const removeExtraConversation = useCallback((conversationId: string | null) => {
    if (!conversationId) return;
    const drop = (prev: Map<string, Conversation>) => {
      if (!prev.has(conversationId)) return prev;
      const next = new Map(prev);
      next.delete(conversationId);
      return next;
    };
    setExtraConversations(drop);
    setPagedConversations(drop);
  }, []);
  // Cache em memoria de TODOS os contatos do tenant (inclui agenda
  // sincronizada via smb_app_state_sync que nao aparece na sidebar).
  // null = ainda nao carregado; array = carregado (mesmo se vazio).
  // Zera junto com o provider (logout/refresh/aba fechada) — sem
  // persistencia em localStorage por LGPD.
  const [allContactsCache, setAllContactsCache] = useState<Contact[] | null>(null);
  const [allContactsCacheTotal, setAllContactsCacheTotal] = useState<number>(0);
  // Nonce do contador da sidebar: bump quando a agenda muda (contato manual
  // criado / refreshAllContacts) pro contador re-buscar sem recarregar pagina.
  const [contactsCountNonce, setContactsCountNonce] = useState(0);
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
  // Fonte de verdade unificada das conversas: snapshot AO VIVO (top-50) +
  // FIXADAS (extraConversations). Dedup por id com a versao ao vivo sempre
  // sobrescrevendo a estatica (o listener e mais fresco). Alimenta selecao,
  // lazy-fetch de contatos e todas as views.
  const allConversations = useMemo(() => {
    if (extraConversations.size === 0 && pagedConversations.size === 0) return conversations;
    const map = new Map<string, Conversation>();
    extraConversations.forEach((c) => map.set(c.id, c));  // fixadas (otimista do picker)
    pagedConversations.forEach((c) => map.set(c.id, c));  // paginadas (getDocs, mais frescas)
    conversations.forEach((c) => map.set(c.id, c));        // ao vivo sobrescreve tudo
    return Array.from(map.values())
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""));
  }, [conversations, extraConversations, pagedConversations]);
  const selectedConversation = useMemo(
    () => (selectedThreadId ? allConversations.find((c) => c.id === selectedThreadId) || null : null),
    [allConversations, selectedThreadId],
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
      allConversations
        .map((c) => c.contact_id)
        .filter((id): id is number => typeof id === "number" && !localIds.has(id) && !fetchedExtraRef.current.has(id)),
    ));
    if (missing.length === 0) return;
    missing.forEach((id) => fetchedExtraRef.current.add(id));
    const fetchOne = (id: number) =>
      getJson<{ contact: Record<string, unknown> }>(bundle.auth, `/api/wa/contact/${id}`)
        .then((res) => normalizeContact(res.contact, String(res.contact.id)))
        // Falha TRANSITORIA (rede/5xx/deploy) libera o id pra retry no proximo
        // run. 403/404 sao permanentes (LGPD/inexistente) — re-tentar viraria
        // tempestade de requests a cada publish do snapshot.
        .catch((e) => {
          const st = Number((e as { status?: number })?.status ?? 0);
          if (st !== 403 && st !== 404) fetchedExtraRef.current.delete(id);
          return null;
        });
    // Concorrencia LIMITADA (lotes de 8): uma pagina do "Carregar mais" pode
    // trazer 100-300 conversas de uma vez e o backend roda uvicorn --workers 1
    // — 200 GETs simultaneos viram 429/503, que caem no ramo "transitorio" e
    // repetem a rajada no proximo publish (mesmo padrao do incidente do
    // allContactsInflightRef). Cada lote publica ao chegar (progressivo).
    const HYDRATE_BATCH = 8;
    const publishBatch = (fetched: (Contact | null)[]) => {
      // SEM guard de dispose: o effect re-roda a cada publish do snapshot
      // (conversations muda o tempo todo) e o cleanup descartava o batch
      // inteiro — com os ids ja marcados em fetchedExtraRef, os contatos
      // nunca chegavam ao estado (join preso nos 50 do snapshot). O provider
      // vive a sessao inteira; armazenar apos re-run e seguro e correto.
      const valid = fetched.filter((c): c is Contact => !!c);
      if (!valid.length) return;
      setExtraContacts((prev) => {
        const next = new Map(prev);
        valid.forEach((c) => next.set(c.id, c));
        return next;
      });
    };
    void (async () => {
      for (let i = 0; i < missing.length; i += HYDRATE_BATCH) {
        const batch = missing.slice(i, i + HYDRATE_BATCH);
        publishBatch(await Promise.all(batch.map(fetchOne)));
      }
    })();
  }, [allConversations, contacts, bundle]);

  const [transportMode, setTransportMode] = useState<TransportMode>("snapshot");
  const [booting, setBooting] = useState(true);
  const [busyLogin, setBusyLogin] = useState(false);
  const [mfaPending, setMfaPending] = useState(false);
  const mfaResolverRef = useRef<{ resolver: MultiFactorResolver; hintUid: string } | null>(null);

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
  // "Nao lidas" (select de qualificacao): alem de filtrar o carregado, busca
  // no Firestore as threads com unread_count>0 do escopo da caixa, fora da
  // janela de recencia (mensagem de fim de semana some do top-50 e a operadora
  // nao deveria ter que paginar as cegas). Resultado vai pra camada estatica.
  const unreadMode = qualificationFilter === UNREAD_FILTER;
  const [unreadPageLimit, setUnreadPageLimit] = useState(UNREAD_PAGE);
  const [unreadHasMore, setUnreadHasMore] = useState(false);
  // Guardas da busca assincrona: resposta tardia depois de SAIR do modo (ou
  // de outra busca mais nova) e descartada — senao repovoava a camada
  // estatica ja limpa.
  const unreadModeRef = useRef(false);
  const unreadReqRef = useRef(0);
  useEffect(() => { unreadModeRef.current = unreadMode; }, [unreadMode]);
  // "So espiar" (admin/supervisor): abrir conversa NAO marca como lida.
  // Lembrado por navegador e POR USUARIO (uid) — em PC compartilhado o proximo
  // gestor nao herda; nunca vale pra operador comum (canPeek).
  const [peekMode, setPeekModeState] = useState(false);
  const peekKey = sessionUser?.firebase_uid ? `${PEEK_STORAGE_KEY}.${sessionUser.firebase_uid}` : "";
  useEffect(() => {
    if (!peekKey) { setPeekModeState(false); return; }
    try { setPeekModeState(window.localStorage.getItem(peekKey) === "1"); } catch { setPeekModeState(false); }
  }, [peekKey]);
  const setPeekMode = useCallback((v: boolean) => {
    setPeekModeState(v);
    if (!peekKey) return;
    try { window.localStorage.setItem(peekKey, v ? "1" : "0"); } catch { /* storage indisponivel: vale so na sessao */ }
  }, [peekKey]);
  const [channelFilter, setChannelFilter] = useState("");
  const searchText = useDeferredValue(search.trim().toLowerCase());

  // -- Composer --
  const [draft, setDraft] = useState("");
  const [replyTarget, setReplyTarget] = useState<MessageReplyReference | null>(null);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [quickSuggestions, setQuickSuggestions] = useState<QuickMessage[]>([]);
  // Item da lista de sugestoes destacado pelo teclado (-1 = nenhum). Reseta
  // sempre que a lista muda (digitacao) ou fecha.
  const [quickSelectedIndex, setQuickSelectedIndex] = useState(-1);
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
  // Ultimo seed do form (qualificacao/notas) e pra qual contato. Permite
  // (a) semear so quando o contato fica disponivel (pode chegar DEPOIS da
  // selecao, via hidratacao) e (b) re-semear se o contato mudou no servidor
  // enquanto o operador ainda nao mexeu no form — sem clobberar digitacao.
  const detailSeedRef = useRef<{ id: number; qualification: string; notes: string } | null>(null);
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
  // RBAC (M-B2): perfil explicito no editor de usuario. "" = derivar do
  // cargo (seed) — o backend re-alinha ao trocar a role sem perfil.
  const [editPerfilId, setEditPerfilId] = useState("");
  const [editDeptId, setEditDeptId] = useState<number | "">("");
  const [busyRoleUpdate, setBusyRoleUpdate] = useState(false);
  const [coexEditingUserId, setCoexEditingUserId] = useState<number | null>(null);
  const [coexPhoneInput, setCoexPhoneInput] = useState("");
  const [busyCoexUpdate, setBusyCoexUpdate] = useState(false);

  // -- Settings --
  const [showSettings, setShowSettings] = useState<SettingsPage>(false);
  const [systemSettings, setSystemSettings] = useState<SystemSettings>(DEFAULT_SYSTEM_SETTINGS);
  // true depois que /api/settings/system respondeu na sessao atual. Os efeitos
  // de som so armam com isso true: os DEFAULTS do frontend (beep ON, alarme ON)
  // nao podem valer enquanto as settings reais do tenant nao chegaram.
  const [settingsLoaded, setSettingsLoaded] = useState(false);
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
  // RBAC (M-B2): checagem por toggle efetivo. Deny-by-default — sem perfil
  // carregado (sessao ainda montando), tudo false.
  const can = useCallback(
    (perm: PermissionKey) => perfil?.toggles?.[perm] === true,
    [perfil],
  );
  // Escopo amplo de DADOS: toggle E role privilegiada (teto das rules — ver
  // comentario no CrmContextValue). Gates de UI puros usam can(...) direto.
  const canSeeAll = (perfil?.toggles?.ver_todos_leads === true) && isManagerRole;

  const botEnabled = systemSettings.bot_enabled;
  // Fase 3.D: filtros operam sobre conversations (sub-threads por canal).
  // Mesmo wa_id em 2 canais = 2 entradas distintas em cada filtro. Campos
  // que pertencem ao contato (qualification, bot_completed, notes) sao
  // resolvidos via contactsById; o resto vem da propria conversation
  // (assigned_to, department_id, source_channel_type, unread_count).
  // Bot: sem atribuicao, no fluxo do bot (ainda nao completaram)
  const botConversations = useMemo(() => {
    if (!botEnabled) return [] as Conversation[];
    return allConversations.filter((conv) => {
      if (conv.is_backup) return false;
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      return c.qualification !== "nao_qualificado" && !c.bot_completed;
    });
  }, [botEnabled, allConversations, contactsById]);
  // Novos: pool sem dono. Exige thread SEM dono (conv.assigned_to) E lead SEM
  // dono (contact.assigned_to) — senao threads orfas de leads ja atribuidos
  // (ex.: reassign-lead muda so o contato, nao a thread) vazariam pra ca.
  // Com bot ativo, so threads que ja completaram bot.
  // Operador comum so ve threads do seu departamento (ou sem); admin/supervisor veem todas.
  const novosConversations = useMemo(() => {
    return allConversations.filter((conv) => {
      if (conv.is_backup) return false;
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      if (c.assigned_to) return false;
      if (c.qualification === "nao_qualificado") return false;
      if (botEnabled && !c.bot_completed) return false;
      if (!canSeeAll && conv.department_id != null && conv.department_id !== sessionUser?.department_id) return false;
      return true;
    });
  }, [allConversations, contactsById, botEnabled, canSeeAll, sessionUser?.department_id]);
  // Meus: atribuidas ao usuario logado (inclui coexistence auto-atribuidas).
  // Aceita o id numerico OU o assigned_to_uid (string) — o listener ao vivo e a
  // paginacao filtram por assigned_to_uid, entao casar so o numerico poderia
  // esconder uma conversa paginada se houver drift de denormalizacao.
  const meusConversations = useMemo(
    () => allConversations.filter((conv) => (conv.assigned_to === sessionUser?.id || (!!conv.assigned_to_uid && conv.assigned_to_uid === sessionUser?.firebase_uid)) && !conv.is_backup),
    [allConversations, sessionUser?.id, sessionUser?.firebase_uid],
  );
  // Filtro por canal do "Meus": canal "acessivel" = canal onde o operador tem
  // thread (derivado das proprias conversas; sem endpoint novo). channel_id
  // pode faltar em doc antigo — o id deterministico "{channel_id}__{wa_id}"
  // cobre o fallback, entao nenhuma thread fica invisivel sob filtro.
  const convChannelKey = (conv: Conversation): string =>
    conv.channel_id != null ? String(conv.channel_id) : (conv.id.includes("__") ? conv.id.split("__")[0] : "");
  const myChannelOptions = useMemo<ChannelFilterOption[]>(() => {
    const byKey = new Map<string, { id: string; type: "standard" | "coexistence"; phone: string }>();
    for (const conv of meusConversations) {
      const key = convChannelKey(conv);
      if (!key) continue;
      const phone = conv.channel_phone_number || conv.channel_label || "";
      const existing = byKey.get(key);
      if (existing && (existing.phone || !phone)) continue;
      const type: "standard" | "coexistence" =
        (conv.channel_type || conv.source_channel_type) === "standard" ? "standard" : "coexistence";
      byKey.set(key, { id: key, type, phone });
    }
    return [...byKey.values()]
      .sort((a, b) => (a.type !== b.type ? (a.type === "standard" ? -1 : 1) : a.phone.localeCompare(b.phone)))
      .map((o) => ({ id: o.id, type: o.type, label: `${o.type === "standard" ? "Standard" : "Coex"} - ${o.phone || `canal ${o.id}`}` }));
  }, [meusConversations]);
  // Sem opcao "Todos" (decisao de produto): com 2+ canais o filtro abre no
  // primeiro (standard vem antes); com 0-1 canal a caixa some e o filtro
  // desarma pra nao esconder nada.
  useEffect(() => {
    if (myChannelOptions.length > 1) {
      if (!myChannelOptions.some((o) => o.id === channelFilter)) setChannelFilter(myChannelOptions[0].id);
    } else if (channelFilter) {
      setChannelFilter("");
    }
  }, [myChannelOptions, channelFilter]);
  // "Carregar mais" do "Meus" so faz sentido se o mine AO VIVO saturou os 50
  // (senao nao ha pagina antiga e um getDocs seria leitura desperdicada). Conta
  // a camada ao vivo (conversations), nao allConversations (que ja inclui paged).
  const myLiveCount = useMemo(
    () => conversations.filter((c) => c.assigned_to === sessionUser?.id || (!!c.assigned_to_uid && c.assigned_to_uid === sessionUser?.firebase_uid)).length,
    [conversations, sessionUser?.id, sessionUser?.firebase_uid],
  );
  const canLoadMoreMine = !canSeeAll && activeView === "meus" && myConvHasMore && myLiveCount >= 50;
  // "Carregar mais" da POOL (operador comum em Novos/Recepcao): so pagina se
  // ALGUM target sem dono do listener ao vivo saturou os 50 (senao nao ha
  // pagina antiga). Nota: e a pool "crua" — a caixa ainda aplica seus filtros
  // (lead sem dono, bot_completed, setor), entao uma pagina pode nao acrescentar
  // linhas visiveis (ex.: thread orfa de lead com dono => contato 403).
  // Pool sem dono pagina por target proprio pra todo perfil (Novos/Recepcao;
  // pra admin tambem a caixa Bot, que deriva da mesma pool).
  const canLoadMorePool = (activeView === "novos" || (canSeeAll && activeView === "bot")) && poolConvHasMore && poolLiveSaturated;
  // "Carregar mais" da janela GLOBAL (admin/supervisor): so pagina se a janela
  // ao vivo saturou os 300 (senao nao ha pagina antiga). Conta so as
  // conversas nao-backup — o target "backup" infla `conversations` sem
  // consumir a janela do target "all". Vale pra Equipe, Bot e Novos/Recepcao:
  // a caixa Equipe do admin deriva da janela global (Novos/Bot agora vem dos
  // targets da pool, com paginacao propria); a pagina estatica alimenta Equipe.
  const allLiveCount = useMemo(
    () => conversations.filter((c) => !c.is_backup).length,
    [conversations],
  );
  // Janela GLOBAL so alimenta Equipe (Novos/Bot agora vem da pool acima).
  const canLoadMoreAll = canSeeAll && activeView === "equipe" && allConvHasMore && allLiveCount >= ADMIN_CONV_WINDOW;
  // "Nao lidas": ha mais pagina da busca de nao lidas (independe das janelas acima).
  const canLoadMoreUnread = unreadMode && unreadHasMore;
  // "So espiar" so existe pra admin/supervisor (role); operador sempre marca lida.
  const canPeek = isManagerRole;
  // Troca de caixa limpa a paginacao estatica ("Meus", pool e Equipe) — bound
  // na janela de staleness (thread paginada reatribuida/fechada por terceiros
  // nao fica fantasma) e re-habilita o "Carregar mais" (hasMore) ao voltar.
  useEffect(() => {
    activeViewRef.current = activeView;
    setPagedConversations(new Map());
    setMyConvPageLimit(50);
    setMyConvHasMore(true);
    setPoolConvPageLimit(50);
    setPoolConvHasMore(true);
    setAllConvPageLimit(ADMIN_CONV_WINDOW);
    setAllConvHasMore(true);
    setUnreadPageLimit(UNREAD_PAGE);
    setUnreadHasMore(false);
  }, [activeView]);
  // Entrar no modo "Nao lidas" dispara a busca (pagina 1); sair limpa a camada
  // estatica que ela preencheu (senao threads antigas ficariam em "Todos").
  useEffect(() => {
    if (unreadMode) {
      void loadUnreadConversations(true);
    } else {
      // Preserva a thread SELECIONADA se ela so vivia na camada estatica —
      // senao o guard de selecao orfa fecha o chat que o usuario esta lendo.
      const keepId = selectedThreadId;
      setPagedConversations((prev) => {
        const next = new Map<string, Conversation>();
        const keep = keepId ? prev.get(keepId) : undefined;
        if (keepId && keep) next.set(keepId, keep);
        return next;
      });
      setUnreadPageLimit(UNREAD_PAGE);
      setUnreadHasMore(false);
      // As outras paginacoes perderam a pagina (camada limpa): reseta os
      // cursores pra o "Buscar conversas mais antigas" refazer do inicio.
      setMyConvPageLimit(50);
      setMyConvHasMore(true);
      setPoolConvPageLimit(50);
      setPoolConvHasMore(true);
      setAllConvPageLimit(ADMIN_CONV_WINDOW);
      setAllConvHasMore(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadMode, activeView]);
  // Nao qualificadas: qualification do contato e "nao_qualificado"
  const nqConversations = useMemo(() => {
    return allConversations.filter((conv) => {
      if (conv.is_backup) return false;
      const c = contactsById.get(conv.contact_id);
      return c?.qualification === "nao_qualificado";
    });
  }, [allConversations, contactsById]);
  // Equipe: atribuidas a outros operadores. Operadores comuns nao veem
  // coexistence de outros; admin/supervisor veem tudo.
  const equipeConversations = useMemo(() => {
    return allConversations.filter((conv) => {
      if (conv.is_backup) return false;
      if (!conv.assigned_to || conv.assigned_to === sessionUser?.id) return false;
      if (!canSeeAll && conv.source_channel_type === "coexistence") return false;
      return true;
    });
  }, [allConversations, canSeeAll, sessionUser?.id]);

  // Backup: conversas historicas importadas (is_backup). So privilegiado ve;
  // ordenadas por mais recente — a que recebe msg nova sobe pro topo (triagem).
  const backupConversations = useMemo(() => {
    if (!canSeeAll) return [] as Conversation[];
    return allConversations
      .filter((conv) => conv.is_backup === true)
      .slice()
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""));
  }, [allConversations, canSeeAll]);

  // Fase 3.D: unread agregado e a soma das conversations daquela view.
  // Single source of truth — coerente com mark-read otimista por thread.
  const sumUnread = (list: Conversation[]) =>
    list.reduce((s, conv) => s + (conv.unread_count ?? conv.unread ?? 0), 0);
  const botUnread = sumUnread(botConversations);
  const novosUnread = sumUnread(novosConversations);
  const meusUnread = sumUnread(meusConversations);
  const nqUnread = sumUnread(nqConversations);
  const equipeUnread = sumUnread(equipeConversations);
  const backupUnread = sumUnread(backupConversations);
  const equipeFiltered = equipeOperatorFilter
    ? equipeConversations.filter((conv) => String(conv.assigned_to) === equipeOperatorFilter)
    : equipeConversations;

  const viewConversations = activeView === "bot" ? botConversations
    : activeView === "novos" ? novosConversations
    : activeView === "meus" ? meusConversations
    : activeView === "equipe" ? equipeFiltered
    : activeView === "backup" ? backupConversations
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
    // Mesmo fallback do chip da sidebar (`|| "novo"`): qualification vazia/
    // ausente (doc legado) conta como "novo" — senao o item mostraria "novo"
    // e sumiria de TODAS as opcoes do filtro, inclusive "Novo".
    // "Nao lidas" e um filtro por THREAD (badge), nao por qualificacao do contato.
    // A thread SELECIONADA fica isenta do filtro "Nao lidas": abrir marca lida e
    // ela sumiria debaixo do cursor.
    const matchesQual = !qualificationFilter
      || (qualificationFilter === UNREAD_FILTER
        ? ((conv.unread_count ?? conv.unread ?? 0) > 0 || conv.id === selectedThreadId)
        : (c?.qualification || "novo") === qualificationFilter);
    const matchesChannel = activeView !== "meus" || !channelFilter || convChannelKey(conv) === channelFilter;
    return matchesSearch && matchesQual && matchesChannel;
  });

  const chatSearchLower = chatSearch.trim().toLowerCase();
  const visibleMessagesFiltered = chatSearchLower ? messages.filter((m) => String(m.content || "").toLowerCase().includes(chatSearchLower)) : null;
  const hasDraft = Boolean(draft.trim());
  const busyComposerAction = busyAudio || busySend;

  const visibleMessages = messages.filter((message, index, allMessages) => {
    // Filtrar mensagens admin_only para quem nao supervisiona o tenant
    if (message.visibility === "admin_only" && !canSeeAll) return false;
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
        // Espelha o zeramento nas camadas ESTATICAS (paginada + fixada) — senao
        // uma thread que vive SO em pagedConversations mantem unread velho e
        // infla meusUnread (o listener ao vivo nao a reentrega pra corrigir).
        const markRead = (prev: Map<string, Conversation>) => {
          const c = prev.get(conversationId);
          if (!c) return prev;
          const next = new Map(prev);
          next.set(conversationId, { ...c, unread: 0, unread_count: 0 });
          return next;
        };
        setPagedConversations(markRead);
        setExtraConversations(markRead);
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

    // canSeeAll = toggle ver_todos_leads E role privilegiada — as rules
    // autorizam a query ampla pelo claim role, entao um perfil operador
    // "ampliado" nao pode receber o target "all" (rules negariam o snapshot).
    // Pool sem dono (Novos/Recepcao + Bot) e "minhas" sao targets PROPRIOS
    // pra todo perfil — admin incluso: a janela global do admin (top-50
    // contatos / top-300 threads por recencia) nao alcanca lead velho parado
    // na pool, e a caixa Bot vinha vazia exigindo "Carregar mais" as cegas
    // (PO 2026-08-21).
    const targets: { key: string; ref: ReturnType<typeof query> }[] = [
      { key: "unassigned:blank", ref: query(waContacts, where("assigned_to_uid", "==", ""), ...baseConstraints) },
      { key: "unassigned:null", ref: query(waContacts, where("assigned_to_uid", "==", null), ...baseConstraints) },
    ];
    if (canSeeAll) {
      targets.push({ key: "all", ref: query(waContacts, ...baseConstraints) });
    }

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

  // `cap`: admin/supervisor tem mais targets (pool + minhas + all) e o corte
  // em 50 descartaria os contatos da pool mais velhos que a janela global.
  function mergeVisibleContacts(groups: Contact[][], cap = 50) {
    const merged = new Map<number, Contact>();
    for (const group of groups) {
      for (const contact of group) {
        merged.set(contact.id, contact);
      }
    }
    return Array.from(merged.values())
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""))
      .slice(0, cap);
  }

  // Escopo de conversations por operador — espelha buildContactSnapshotTargets.
  // Admin/supervisor: 300 mais recentes + backup (ver comentario no branch).
  // Operador comum: so atribuidas a si ou sem dono, agora com
  // orderBy("last_message_at","desc")+limit(50) por target (igual aos contatos)
  // — antes baixava o pool inteiro a cada abertura do CRM. Exige o indice
  // composto (assigned_to_uid ASC, last_message_at DESC) em firestore.indexes.json
  // (publicado e construido ANTES deste deploy). Dedupe final e client-side em
  // mergeVisibleConversations.
  function buildConversationSnapshotTargets() {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations || !sessionUser) return [];

    const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);

    // Top-50 por recencia em cada target. Exige o indice composto
    // (assigned_to_uid, last_message_at). mergeVisibleConversations junta/ordena
    // os targets client-side. Pool sem dono (Novos/Recepcao + Bot) e target
    // PROPRIO pra todo perfil — admin incluso: a janela global top-300 nao
    // alcancava lead velho parado na pool (caixa Bot vazia + "Carregar mais"
    // as cegas; PO 2026-08-21).
    const opConstraints = [orderBy("last_message_at", "desc"), firestoreLimit(50)] as const;
    const targets: { key: string; ref: ReturnType<typeof query> }[] = [
      { key: "unassigned:blank", ref: query(waConversations, where("assigned_to_uid", "==", ""), ...opConstraints) },
      { key: "unassigned:null", ref: query(waConversations, where("assigned_to_uid", "==", null), ...opConstraints) },
    ];

    if (canSeeAll) {
      // Corte de leitura: a colecao cresceu (~3k conversas) e o snapshot sem
      // limite custava ~3k reads por sessao e 1000+ itens em memoria/DOM.
      // Admin ouve as 300 mais recentes (orderBy single-field = indice
      // automatico) + um target dedicado pra caixa Backup (igualdade simples,
      // sem indice composto), cujas conversas tem last_message_at antigo e
      // cairiam fora do top-300. Equipe e Nao qualificados derivam desta janela.
      targets.push(
        { key: "all", ref: query(waConversations, orderBy("last_message_at", "desc"), firestoreLimit(ADMIN_CONV_WINDOW)) },
        { key: "backup", ref: query(waConversations, where("is_backup", "==", true)) },
      );
    }

    if (sessionUser.firebase_uid) {
      targets.push({
        key: `mine:${sessionUser.firebase_uid}`,
        ref: query(waConversations, where("assigned_to_uid", "==", sessionUser.firebase_uid), ...opConstraints),
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
    setPerfil(null);
    setSettingsLoaded(false);
    // Settings sao POR TENANT: nao deixar bot_enabled/pool_mode/alarme do
    // usuario anterior regerem as caixas do proximo (PC compartilhado).
    setSystemSettings(DEFAULT_SYSTEM_SETTINGS);
    setUserSettings(DEFAULT_USER_SETTINGS);
    setTenantName("");
    setContacts([]);
    setConversations([]);
    setExtraConversations(new Map());
    setPagedConversations(new Map());
    setMyConvPageLimit(50);
    setMyConvHasMore(true);
    setPoolConvPageLimit(50);
    setPoolConvHasMore(true);
    setPoolLiveSaturated(false);
    setAllConvPageLimit(ADMIN_CONV_WINDOW);
    setAllConvHasMore(true);
    setLoadingMoreConvs(false);
    setExtraContacts(new Map());
    fetchedExtraRef.current.clear();
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
          tenant?: { id: string; name?: string; plan?: string; modules?: string[] };
          firestore_collections?: Record<string, string>;
          perfil?: SessionPerfil;
        }>(bundle.auth, "/api/session");
        const [ops, deps, chs] = await Promise.all([
          getJson<Operator[]>(bundle.auth, "/api/operators"),
          getJson<{ departments: Department[] }>(bundle.auth, "/api/departments"),
          getJson<{ channels: Channel[] }>(bundle.auth, "/api/admin/channels").catch(() => ({ channels: [] as Channel[] })),
        ]);
        setSessionUser(session.user);
        // Branding por tenant: o nome dado no super-admin (tenant.name) vira o
        // titulo do topbar. Fallback = tenant_id (o backend ja faz isso).
        setTenantName(session.tenant?.name || "");
        setPerfil(session.perfil ?? null);
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
        // Fetches SEPARADOS: o gate de som (settingsLoaded) depende so de
        // /api/settings/system — falha do /user nao pode calar o tenant. Em
        // falha, os sons ficam desarmados ate o proximo refresh de token
        // (~1h, que re-executa este handler) ou ate abrir Configuracoes.
        getJson<SystemSettings>(bundle.auth, "/api/settings/system")
          .then((sys) => { setSystemSettings(sys); setSettingsLoaded(true); })
          .catch((e) => { console.warn("settings/system indisponivel — sons desarmados:", errorText(e)); });
        getJson<UserSettings>(bundle.auth, "/api/settings/user").then((usr) => setUserSettings(usr)).catch(() => {});
      } catch (e) { setError(errorText(e)); await signOut(bundle.auth); }
    });
  }, [bundle]);

  // RBAC (M-B2): mantem os toggles do perfil ao vivo. Mescla o doc do
  // Firestore POR CIMA do mapa efetivo vindo do /api/session — edicao de
  // perfil pelo admin reflete sem re-login, e chave nova de catalogo
  // ausente no doc antigo preserva o valor efetivo (fallback) da sessao.
  // Depende de perfil?.id (nao do objeto) pra nao reassinar a cada merge.
  useEffect(() => {
    const path = config?.firestore.collections["perfis_acesso"];
    const perfilId = perfil?.id;
    if (!bundle?.db || !path || !perfilId || !snapshotMode) return undefined;
    return onSnapshot(
      firestoreDoc(bundle.db, path, perfilId),
      (snap) => {
        const toggles = (snap.data()?.toggles ?? null) as Record<string, boolean> | null;
        if (!toggles) return;
        setPerfil((prev) => (prev && prev.id === perfilId
          ? { ...prev, toggles: { ...prev.toggles, ...toggles } }
          : prev));
      },
      () => { /* sem permissao/offline: segue com os toggles da sessao */ },
    );
  }, [bundle, config, perfil?.id, snapshotMode]);

  // Selecao inicial: NENHUMA conversa aberta ao carregar (canario ADR 0010,
  // 2026-08-05 — o auto-select da allConversations[0] abria na tela uma
  // thread que o operador nunca clicou, ex. a mais recente de outro teste).
  // Selecao orfa (a thread selecionada saiu da lista, ex.: transferida)
  // volta pro placeholder em vez de pular pra 1a da lista.
  useEffect(() => {
    if (!selectedThreadId) return;
    holdEmptySelectionRef.current = false;
    if (!allConversations.some((c) => c.id === selectedThreadId)) {
      setSelectedThreadId(null);
    }
  }, [allConversations, selectedThreadId]);

  // Thread aberta MUDOU de dono pra OUTRO usuario (ex.: colega clicou
  // "Assumir atendimento" num lead da pool que eu tambem estava olhando):
  // fecha o chat, limpa as camadas estaticas e avisa. O guard de selecao orfa
  // acima so fecha quando a thread SOME da lista — e ela nao some quando (a)
  // sou admin/supervisor (janela global continua entregando o doc), (b) a
  // thread esta numa copia estatica (fixada pelo picker / "Carregar mais"),
  // que o listener de lista nunca atualiza. Reage so a MUDANCA enquanto a
  // mesma thread esta aberta: abrir uma thread que JA e de outro (Equipe,
  // intervencao de supervisao) nao fecha. Nao fecha se o dono novo sou eu
  // (assumi / recebi transferencia), se sou o Dono do LEAD (coex: thread no
  // numero de outro operador) nem se sou o handler do takeover.
  const selectedOwnerRef = useRef<{ id: string; uid: string; user: number | null } | null>(null);
  useEffect(() => {
    if (!selectedThreadId || !selectedConversation || !sessionUser) {
      selectedOwnerRef.current = null;
      return;
    }
    const ownerUid = selectedConversation.assigned_to_uid || "";
    const ownerId = selectedConversation.assigned_to ?? null;
    const prev = selectedOwnerRef.current;
    selectedOwnerRef.current = { id: selectedThreadId, uid: ownerUid, user: ownerId };
    if (!ownerUid && ownerId == null) return;                       // voltou pra pool: nada a fazer
    const mine = (!!ownerUid && ownerUid === sessionUser.firebase_uid) || (ownerId != null && ownerId === sessionUser.id);
    if (mine) return;
    if (selectedContact?.assigned_to != null && selectedContact.assigned_to === sessionUser.id) return;
    if (selectedConversation.takeover_handler_user_id != null && selectedConversation.takeover_handler_user_id === sessionUser.id) return;
    if (!prev || prev.id !== selectedThreadId) return;                // acabou de abrir: registra e observa
    if (prev.uid === ownerUid && prev.user === ownerId) return;       // sem mudanca de dono
    const ownerName = operators.find((o) => o.id === ownerId)?.display_name || "outro operador";
    const fromPool = !prev.uid && prev.user == null;
    holdEmptySelectionRef.current = true;
    removeExtraConversation(selectedThreadId);
    setSelectedThreadId(null);
    setNotice(fromPool ? `Atendimento assumido por ${ownerName}.` : `Atendimento transferido para ${ownerName}.`);
  }, [selectedThreadId, selectedConversation, selectedContact?.assigned_to, sessionUser, operators, removeExtraConversation]);

  // Observa o DOC da thread selecionada (1 listener por selecao). Duas
  // funcoes: (a) manter fresca a copia das camadas ESTATICAS (fixada pelo
  // picker / "Carregar mais") — o listener de lista nao reentrega thread fora
  // do escopo do operador, entao a copia congelada ficaria com dono velho pra
  // sempre e o effect acima nunca veria a mudanca; (b) detectar PERDA DE
  // ESCOPO: quando o dono vira outro operador, as rules (canSeeContactScoped)
  // negam a leitura do doc e o listener cai com permission-denied — esse erro
  // e o sinal pra fechar o chat mesmo que nenhuma lista tenha reentregado
  // nada. Admin/supervisor nunca recebe permission-denied (caem no caso (a) +
  // effect acima). So em snapshot mode; polling ja recarrega a lista.
  useEffect(() => {
    const path = config?.firestore.collections.wa_conversations;
    if (!bundle?.db || !snapshotMode || !selectedThreadId || !path) return undefined;
    const id = selectedThreadId;
    let disposed = false;
    const unsubscribe = onSnapshot(
      firestoreDoc(bundle.db, path, id),
      (snap) => {
        if (disposed || !snap.exists()) return;
        const fresh = normalizeConversation(snap.data() as Record<string, unknown>, snap.id);
        const refresh = (prev: Map<string, Conversation>) => {
          if (!prev.has(id)) return prev;
          const next = new Map(prev);
          next.set(id, fresh);
          return next;
        };
        setExtraConversations(refresh);
        setPagedConversations(refresh);
      },
      (e) => {
        if (disposed) return;
        if ((e as { code?: string })?.code !== "permission-denied") return;
        holdEmptySelectionRef.current = true;
        removeExtraConversation(id);
        setSelectedThreadId(null);
        setNotice("Este atendimento foi assumido por outro operador.");
      },
    );
    return () => { disposed = true; unsubscribe(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundle, snapshotMode, selectedThreadId, config?.firestore.collections.wa_conversations]);

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

  // Reset detail state on contact change (so o que NAO deriva do contato; os
  // campos derivados — qualificacao/notas/destino — sao semeados no effect
  // seguinte, quando o contato estiver disponivel).
  useEffect(() => {
    detailSeedRef.current = null;
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

  // Semeia o form do painel (qualificacao/notas/destino de transferencia) a
  // partir do contato resolvido em contactsById (ao vivo + hidratado). Antes
  // lia so `contacts` (top-50 ao vivo): thread cujo contato veio de
  // extraContacts (Equipe alem do top-50, "Carregar mais", picker) abria o
  // form EM BRANCO e "Salvar" gravava qualification="" e APAGAVA as notas do
  // lead. Qualificacao vazia e semeada como "novo" (mesmo fallback do chip da
  // sidebar), entao um Salvar nunca persiste "".
  useEffect(() => {
    if (selectedContactId == null || !selectedContact) {
      if (selectedContactId == null) detailSeedRef.current = null;
      setQualification(""); setNotes(""); setToUserId(""); setToDepartmentId("");
      return;
    }
    const seed = { qualification: selectedContact.qualification || "novo", notes: selectedContact.notes || "" };
    const prev = detailSeedRef.current;
    if (prev && prev.id === selectedContactId) {
      // Ja semeado pra este contato: so re-semeia se o servidor mudou E o
      // operador nao tocou no form (estado ainda igual ao seed anterior).
      const untouched = qualification === prev.qualification && notes === prev.notes;
      const changed = seed.qualification !== prev.qualification || seed.notes !== prev.notes;
      if (!untouched || !changed) return;
    } else {
      setToUserId(selectedContact.assigned_to || "");
      setToDepartmentId(selectedContact.department_id || "");
    }
    detailSeedRef.current = { id: selectedContactId, ...seed };
    setQualification(seed.qualification);
    setNotes(seed.notes);
  }, [selectedContactId, selectedContact, qualification, notes]);

  // Revalida o contato hidratado ao ABRIR a thread. extraContacts e fetch
  // unico por sessao (nunca revalidado): sem isto o form seria semeado com
  // qualificacao/notas de horas atras e um "Salvar" sobrescreveria a edicao de
  // um colega; o chip/filtro da sidebar tambem ficam frescos pra thread aberta.
  // So pra contato FORA do snapshot ao vivo (o listener cobre os demais) e ja
  // hidratado (se ainda esta em voo, o effect de hidratacao traz fresco).
  // Custo: 1 GET por selecao. Guard de dispose evita repovoar extraContacts
  // depois de um logout/troca de conta (resetUserScopedState) em PC compartilhado.
  useEffect(() => {
    if (!bundle || selectedContactId == null) return undefined;
    if (contacts.some((c) => c.id === selectedContactId)) return undefined;
    if (!extraContacts.has(selectedContactId)) return undefined;
    let disposed = false;
    const id = selectedContactId;
    void getJson<{ contact: Record<string, unknown> }>(bundle.auth, `/api/wa/contact/${id}`)
      .then((res) => {
        if (disposed) return;
        const fresh = normalizeContact(res.contact, String(res.contact.id));
        setExtraContacts((prev) => { const next = new Map(prev); next.set(id, fresh); return next; });
      })
      .catch((e) => {
        if (disposed) return;
        // 403/404 = o backend diz que este contato NAO e mais meu/pool
        // (ex.: colega assumiu o lead, contato apagado): DESPEJA a copia —
        // manter a copia velha renderizava nome/telefone/notas do lead de
        // outro operador (e segurava o ChatPanel aberto) pelo resto da
        // sessao. Transitorio (rede/5xx): fica com a copia em cache.
        const st = Number((e as { status?: number })?.status ?? 0);
        if (st !== 403 && st !== 404) return;
        setExtraContacts((prev) => {
          if (!prev.has(id)) return prev;
          const next = new Map(prev);
          next.delete(id);
          return next;
        });
      });
    return () => { disposed = true; };
    // So na troca de selecao — contacts/extraContacts sao lidos no momento
    // da selecao de proposito (nao re-disparar a cada publish do snapshot).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundle, selectedContactId]);

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
      const nextContacts = mergeVisibleContacts(Array.from(partialContacts.values()), canSeeAll ? 50 * targets.length : 50);
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
  }, [bundle, snapshotMode, config?.firestore.collections.wa_contacts, canSeeAll, sessionUser?.firebase_uid, sessionUser?.department_id]);

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
      // Saturacao por target da pool (gate do "Carregar mais" de Novos/Recepcao).
      const poolSaturated = Array.from(partialConversations.entries())
        .some(([key, list]) => key.startsWith("unassigned:") && list.length >= 50);
      startTransition(() => { setConversations(next); setPoolLiveSaturated(poolSaturated); });
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
  }, [bundle, snapshotMode, config?.firestore.collections.wa_conversations, canSeeAll, sessionUser?.firebase_uid, sessionUser?.department_id]);

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
    // "So espiar" (admin/supervisor): abrir NAO marca como lida — badge fica e
    // a thread segue contando como nao lida (inclusive no alarme do setor).
    if (canPeek && peekMode) return undefined;
    // ADR 0010 (revisado): com thread ativa, o gatilho e o unread da
    // CONVERSATION — e o que o POST /conversation/read zera; o contador do
    // CONTATO nunca zera pelo caminho de thread, e um valor stale dele
    // re-dispararia o efeito em loop (1 POST/1,2s). Sem thread, cai no
    // contador do contato (endpoint legado por contact_id).
    const threadConv = activeThreadId ? allConversations.find((c) => c.id === activeThreadId) : null;
    const unreadCount = activeThreadId
      ? (threadConv?.unread_count ?? threadConv?.unread ?? 0)
      : (activeContact?.unread_count ?? activeContact?.unread ?? 0);
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
  }, [activeContact?.unread, activeContact?.unread_count, activeConversationId, activeThreadId, allConversations, bundle, selectedContactId, sessionUser, canPeek, peekMode]);

  // =========================================================================
  // Sound notifications
  // =========================================================================

  // Beep: baseline por thread (id -> unread) + instante da ultima avaliacao.
  const beepBaselineRef = useRef<Map<string, number> | null>(null);
  const beepLastEvalRef = useRef<number>(0);
  // Alarme: instante do ultimo toque (dedupe entre o effect (a) e o tick).
  const lastAlarmRingAtRef = useRef<number>(0);
  const alarmAudioRef = useRef<HTMLAudioElement | null>(null);
  const alarmAudioPathRef = useRef<string>("");
  // Ids das threads "atrasadas" no ultimo calculo: toca na hora SO quando uma
  // thread nova entra no conjunto; o tick de 30 s cobre a repeticao.
  const overdueIdsRef = useRef<Set<string>>(new Set());
  const soundConversationsRef = useRef<Conversation[]>([]);

  // Destrava o Web Audio no primeiro gesto do usuario — Chrome bloqueia o
  // AudioContext antes de qualquer interacao (warning "was not allowed to start").
  useEffect(() => { installAudioUnlock(); }, []);

  // Conjunto que alimenta beep e alarme = SO as threads que o usuario VE nas
  // caixas Novos + Meus (ja filtradas por bot_completed, setor, backup, dono e
  // pool_mode). Antes os efeitos liam o array cru `contacts` (janela de
  // wa_contacts: pool sem dono de QUALQUER setor, inclusive lead em fase de
  // bot), que nao corresponde a nada na sidebar do operador comum — o alarme
  // tocava sem nada na tela (diagnostico 2026-08-21). Contador = unread_count
  // da THREAD (o mesmo do badge), nao o do contato.
  // So a camada AO VIVO (`conversations`): as camadas estaticas ("Carregar
  // mais" e fixada pelo picker) trazem threads antigas que nao sao atividade
  // nova e nao sao atualizadas por terceiros (copia congelada) — entrariam no
  // som sem mensagem nova e so sairiam trocando de caixa.
  const soundConversations = useMemo(() => {
    const live = new Set(conversations.map((c) => c.id));
    const seen = new Set<string>();
    const out: Conversation[] = [];
    for (const conv of [...novosConversations, ...meusConversations]) {
      if (seen.has(conv.id) || !live.has(conv.id)) continue;
      seen.add(conv.id);
      out.push(conv);
    }
    return out;
  }, [novosConversations, meusConversations, conversations]);
  useEffect(() => { soundConversationsRef.current = soundConversations; }, [soundConversations]);
  const convUnread = (c: Conversation) => c.unread_count ?? c.unread ?? 0;
  const convTime = (iso?: string | null) => {
    const t = iso ? new Date(iso).getTime() : NaN;
    return isNaN(t) ? null : t;
  };

  // Beep (todos os usuarios) quando chega mensagem NOVA numa thread visivel:
  // baseline por thread (ref) — bipa se uma thread ja conhecida teve o
  // unread AUMENTADO, ou se uma thread nova aparece com mensagem posterior a
  // ultima avaliacao. Thread que entra no conjunto com mensagem antiga
  // (hidratacao de contato, rotacao da janela) e absorvida sem som. So arma
  // com as settings reais do tenant carregadas.
  const beepEnabled = Boolean(sessionUser) && settingsLoaded && systemSettings.notification_sound_enabled;
  useEffect(() => {
    if (!beepEnabled) {
      beepBaselineRef.current = null;
      return;
    }
    const now = Date.now();
    const next = new Map<string, number>();
    soundConversations.forEach((c) => next.set(c.id, convUnread(c)));
    const prev = beepBaselineRef.current;
    const lastEval = beepLastEvalRef.current;
    beepBaselineRef.current = next;
    beepLastEvalRef.current = now;
    if (prev === null) return; // primeiro calculo da sessao: nao bipa
    let ring = false;
    for (const c of soundConversations) {
      const u = convUnread(c);
      if (u <= 0) continue;
      const before = prev.get(c.id);
      if (before === undefined) {
        const t = convTime(c.last_message_at);
        if (t !== null && t >= lastEval - 5_000) ring = true;
      } else if (u > before) {
        ring = true;
      }
      if (ring) break;
    }
    if (ring) {
      if (systemSettings.notification_sound_path) {
        const audio = new Audio(systemSettings.notification_sound_path);
        audio.volume = 0.5;
        audio.play().catch(() => {});
      } else {
        playBeep({ freq: 880, type: "sine", gain: 0.3, duration: 0.3 });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soundConversations, beepEnabled, systemSettings.notification_sound_path]);

  // Alarme repetitivo (departamentos configurados): thread visivel com
  // unread>0 e last_message_at mais velho que o limiar. Toca IMEDIATAMENTE
  // quando uma thread nova entra no conjunto atrasado e a cada 30 s enquanto
  // houver alguma. Deps PRIMITIVAS + refs: o effect antigo tinha `contacts`,
  // `sessionUser` e o array de departamentos nas deps e chamava checkAlarm()
  // a cada re-arme — tocava a cada publish do snapshot, refresh de token e ao
  // abrir Configuracoes (identidade nova de array/objeto), nao so a cada 30 s.
  const alarmDeptKey = (systemSettings.alarm_department_ids || []).map(String).join(",");
  const userDeptKey = sessionUser?.department_id != null ? String(sessionUser.department_id) : "";
  const alarmActive = Boolean(sessionUser) && settingsLoaded && systemSettings.alarm_enabled
    && alarmDeptKey.length > 0 && userDeptKey !== "" && alarmDeptKey.split(",").includes(userDeptKey);
  const alarmThresholdMs = (systemSettings.alarm_threshold_minutes || 5) * 60 * 1000;
  const alarmSoundPath = systemSettings.alarm_sound_path || "";

  // "Atrasada" = unread>0 e a ultima mensagem DO CLIENTE (last_inbound_at;
  // fallback last_message_at em doc legado) mais velha que o limiar. Ancorar
  // em last_message_at deixava outbound do bot / banner de sistema "resetar"
  // o relogio do cliente que esta esperando.
  const computeOverdueIds = (list: Conversation[], thresholdMs: number): Set<string> => {
    const now = Date.now();
    const ids = new Set<string>();
    for (const conv of list) {
      if (convUnread(conv) <= 0) continue;
      const t = convTime(conv.last_inbound_at) ?? convTime(conv.last_message_at);
      if (t !== null && (now - t) >= thresholdMs) ids.add(conv.id);
    }
    return ids;
  };
  const stopAlarmAudio = () => {
    if (alarmAudioRef.current) { alarmAudioRef.current.pause(); alarmAudioRef.current = null; }
    alarmAudioPathRef.current = "";
  };
  const playAlarmSound = (path: string) => {
    // Dedupe: o effect (a) e o tick de 30 s sao caminhos independentes —
    // nunca toca 2x em menos de 5 s.
    const now = Date.now();
    if (now - lastAlarmRingAtRef.current < 5_000) return;
    lastAlarmRingAtRef.current = now;
    if (path) {
      if (!alarmAudioRef.current || alarmAudioPathRef.current !== path) {
        stopAlarmAudio();
        alarmAudioRef.current = new Audio(path);
        alarmAudioRef.current.volume = 0.6;
        alarmAudioPathRef.current = path;
      }
      alarmAudioRef.current.currentTime = 0;
      alarmAudioRef.current.play().catch(() => {});
    } else {
      playBeep({
        freq: 660, type: "square", gain: 0.25, duration: 0.6,
        steps: [{ freq: 880, at: 0.15 }, { freq: 660, at: 0.3 }, { freq: 880, at: 0.45 }],
      });
    }
  };

  // (a) reacao a mudanca do conjunto visivel: toca na hora so se ENTROU thread
  // nova no atrasado; limpa o estado quando o alarme esta inativo.
  useEffect(() => {
    if (!alarmActive) {
      overdueIdsRef.current = new Set();
      stopAlarmAudio();
      return;
    }
    const next = computeOverdueIds(soundConversations, alarmThresholdMs);
    const prev = overdueIdsRef.current;
    let hasNew = false;
    next.forEach((id) => { if (!prev.has(id)) hasNew = true; });
    overdueIdsRef.current = next;
    if (next.size === 0) stopAlarmAudio();
    else if (hasNew) playAlarmSound(alarmSoundPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [soundConversations, alarmActive, alarmThresholdMs, alarmSoundPath]);

  // (b) tick de 30 s: repete enquanto houver thread atrasada (le o conjunto
  // atual pela ref — NAO re-arma o intervalo a cada publish).
  useEffect(() => {
    if (!alarmActive) return undefined;
    const tick = () => {
      const next = computeOverdueIds(soundConversationsRef.current, alarmThresholdMs);
      overdueIdsRef.current = next;
      if (next.size > 0) playAlarmSound(alarmSoundPath);
      else stopAlarmAudio();
    };
    const intervalId = window.setInterval(tick, 30_000);
    return () => {
      window.clearInterval(intervalId);
      stopAlarmAudio();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarmActive, alarmThresholdMs, alarmSoundPath]);

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
    closeQuickSuggestions();
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
    // Em snapshot mode os listeners ja entregam as mudancas (contacts,
    // conversations e mensagens) — o refresh manual e relicario do polling.
    // Pro admin, este par de GETs custa ~14k reads Firestore por clique
    // (conversations 500+backup+join full-scan + contacts see_all): era
    // disparado por "Devolver ao bot" e "Reatribuicao em lote" mesmo com
    // snapshot ativo (dieta de reads 2026-07-20).
    if (snapshotMode) return;
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

  // Se o erro for o desafio de 2o fator, prepara o resolver e sinaliza a UI
  // pra pedir o codigo TOTP. Retorna true se tratou (nao mostrar como erro).
  function startMfaChallenge(e: unknown): boolean {
    if (!bundle || (e as { code?: string })?.code !== "auth/multi-factor-auth-required") return false;
    const resolver = getMultiFactorResolver(bundle.auth, e as MultiFactorError);
    const hint = resolver.hints.find((h) => h.factorId === TotpMultiFactorGenerator.FACTOR_ID) || resolver.hints[0];
    mfaResolverRef.current = { resolver, hintUid: hint.uid };
    setMfaPending(true);
    return true;
  }

  // setNotice("") nos dois logins: o aviso de "link de redefinicao enviado" e
  // estado GLOBAL e sobreviveria ao login, reaparecendo dentro do CRM depois
  // que a tela de login desmonta.
  async function loginWithGoogle() {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); setNotice(""); await signInWithPopup(bundle.auth, bundle.provider); }
    catch (e) { if (!startMfaChallenge(e)) setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function loginWithEmail(email: string, password: string) {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); setNotice(""); await signInWithEmailAndPassword(bundle.auth, email, password); }
    catch (e) { if (!startMfaChallenge(e)) setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  // Solucao A do ADR 0006: o proprio operador pede o link de redefinicao.
  // Roda 100% client-side (quem envia o email e o Firebase) — sem endpoint,
  // sem provedor transacional, sem segredo novo.
  //
  // A confirmacao e NEUTRA de proposito ("se este email tiver uma conta"):
  // confirmar o envio de verdade transformaria a tela num verificador de
  // quais emails existem no projeto. Pelo mesmo motivo, user-not-found e
  // tratado como sucesso — so vira erro visivel o que a pessoa precisa
  // resolver (email malformado, excesso de tentativas, rede).
  //
  // ATENCAO: so recupera conta que TEM provider de senha. Conta nascida do
  // provisionamento (get_or_create_firebase_user) vem SEM senha e o link nao
  // a resgata — por isso operador e criado com senha no Firebase Console.
  async function resetPassword(email: string) {
    if (!bundle) return;
    const target = email.trim();
    if (!target) return;
    let failed = false;
    try {
      setBusyLogin(true); setError(""); setNotice("");
      await sendPasswordResetEmail(bundle.auth, target);
    } catch (e) {
      if ((e as { code?: string })?.code !== "auth/user-not-found") {
        setError(errorText(e));
        failed = true;
      }
    } finally {
      setBusyLogin(false);
    }
    if (!failed) {
      setNotice(
        "Se este email tiver uma conta, enviamos um link para você criar uma nova senha. "
        + "Verifique também a caixa de spam.",
      );
    }
  }

  async function resolveMfaCode(code: string) {
    const pending = mfaResolverRef.current;
    if (!pending) return;
    try {
      setBusyLogin(true); setError("");
      const assertion = TotpMultiFactorGenerator.assertionForSignIn(pending.hintUid, code.trim());
      await pending.resolver.resolveSignIn(assertion);
      mfaResolverRef.current = null;
      setMfaPending(false);
    } catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  function cancelMfa() {
    mfaResolverRef.current = null;
    setMfaPending(false);
    setError("");
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
    finally {
      setBusySend(false);
      // Mantem o foco na caixa apos enviar: a textarea fica disabled durante o
      // envio (perde o foco); rAF refoca depois do re-render reabilitar.
      requestAnimationFrame(() => composerInputRef.current?.focus());
    }
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
    finally {
      setBusySend(false);
      requestAnimationFrame(() => composerInputRef.current?.focus());
    }
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
    // Lista de mensagens rapidas aberta (draft comecando com "/"): a lista
    // fica ACIMA da caixa, entao a primeira seta pra cima destaca o item mais
    // proximo dela (o ultimo) e cada seta sobe um; seta pra baixo desce e,
    // passando do ultimo, volta pra caixa. Enter (item destacado) e Tab
    // completam NO CAMPO sem enviar — o operador revisa e da Enter de novo
    // pra mandar (Tab sem selecao completa a primeira). Esc fecha.
    const count = quickSuggestions.length;
    if (count > 0) {
      const selected = quickSelectedIndex < count ? quickSelectedIndex : -1;
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setQuickSelectedIndex(selected < 0 ? count - 1 : Math.max(0, selected - 1));
        return;
      }
      if (event.key === "ArrowDown" && selected >= 0) {
        event.preventDefault();
        setQuickSelectedIndex(selected >= count - 1 ? -1 : selected + 1);
        return;
      }
      if (event.key === "Escape") { event.preventDefault(); closeQuickSuggestions(); return; }
      if (event.key === "Tab" && !event.shiftKey) {
        event.preventDefault();
        applyQuickMessage(quickSuggestions[selected >= 0 ? selected : 0]);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey && selected >= 0) {
        event.preventDefault();
        applyQuickMessage(quickSuggestions[selected]);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!busySend && draft.trim()) void sendTextMessage(); return; }
    // Atalhos de formatacao do WhatsApp (os mesmos do WhatsApp Web):
    // envolvem a selecao com o marcador; sem selecao, inserem o par e
    // deixam o cursor no meio; com o par ja em volta, tiram (toggle).
    if ((event.ctrlKey || event.metaKey) && !event.altKey) {
      const key = event.key.toLowerCase();
      const marker = !event.shiftKey && key === "b" ? "*"
        : !event.shiftKey && key === "i" ? "_"
        : event.shiftKey && key === "x" ? "~"
        : event.shiftKey && key === "m" ? "`"
        : null;
      if (marker) { event.preventDefault(); wrapDraftSelection(marker); }
    }
  }

  function wrapDraftSelection(marker: string) {
    const input = composerInputRef.current;
    if (!input) return;
    const value = input.value;
    const start = input.selectionStart ?? value.length;
    const end = input.selectionEnd ?? start;
    const wrapped = start > 0 && value[start - 1] === marker && value[end] === marker;
    const next = wrapped
      ? value.slice(0, start - 1) + value.slice(start, end) + value.slice(end + 1)
      : value.slice(0, start) + marker + value.slice(start, end) + marker + value.slice(end);
    const delta = wrapped ? -1 : 1;
    setDraft(next);
    requestAnimationFrame(() => { input.focus(); input.setSelectionRange(start + delta, end + delta); });
  }

  function handleDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const value = event.target.value;
    setDraft(value);
    const trimmed = value.trim();
    if (trimmed.startsWith("/") && trimmed.length >= 1) {
      const typed = trimmed.toLowerCase();
      const allQuick = [...systemSettings.quick_messages_global, ...userSettings.quick_messages].filter((qm) => qm.shortcut && qm.message);
      const matches = allQuick.filter((qm) => { const s = qm.shortcut.startsWith("/") ? qm.shortcut.toLowerCase() : `/${qm.shortcut.toLowerCase()}`; return s.startsWith(typed); });
      setQuickSuggestions(matches); setQuickSelectedIndex(-1);
    } else { closeQuickSuggestions(); }
  }

  function closeQuickSuggestions() { setQuickSuggestions([]); setQuickSelectedIndex(-1); }

  // Completa no campo (clique, Tab ou Enter no item destacado) — o operador
  // revisa/edita e da Enter de novo pra enviar.
  function applyQuickMessage(qm: QuickMessage) {
    setDraft(qm.message); closeQuickSuggestions();
    // Cursor no fim do texto completado (o value troca no re-render; rAF espera).
    requestAnimationFrame(() => {
      const el = composerInputRef.current;
      if (!el) return;
      el.focus();
      const end = el.value.length;
      el.setSelectionRange(end, end);
    });
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
    const contactId = selectedContact.id;
    try {
      setBusySave(true); setError(""); setNotice("");
      const r = await putJson(bundle.auth, `/api/wa/contact/${contactId}/qualify`, { qualification, notes }) as { qualification_effective?: string };
      // Verdade do servidor: "novo" em lead ja promovido e ignorado pelo
      // backend (reforma 2026-09) — patchar com o valor efetivo, senao a UI
      // mostraria "novo" salvo e o listener reverteria sem explicacao.
      const effective = r?.qualification_effective || qualification;
      setNotice(effective !== qualification && qualification === "novo"
        ? "Notas salvas. Lead ja em atendimento nao volta a Novo."
        : "Qualificacao atualizada.");
      // Contato hidratado sob demanda (extraContacts, fora do top-50 ao vivo)
      // e um fetch unico — sem este patch o chip e o filtro por qualificacao
      // da sidebar ficariam com o valor antigo ate recarregar a pagina. Quem
      // esta no snapshot ao vivo (`contacts`) e atualizado pelo listener e
      // vence no join do contactsById, entao so mexemos na camada estatica.
      setExtraContacts((prev) => {
        const cur = prev.get(contactId);
        if (!cur) return prev;
        const next = new Map(prev);
        next.set(contactId, { ...cur, qualification: effective, notes });
        return next;
      });
      // O que VALE no servidor vira o novo seed: o form volta a contar como
      // "nao tocado" e segue acompanhando mudancas futuras.
      detailSeedRef.current = { id: contactId, qualification: effective, notes };
      setQualification(effective);
      if (!snapshotMode) await refreshPollingViews();
    }
    catch (e) { setError(errorText(e)); }
    finally { setBusySave(false); }
  }

  function startEditUser(op: Operator) { setEditingUserId(op.id); setEditRole(op.role); setEditPerfilId(op.perfil_acesso_id || ""); setEditDeptId(op.department_id ?? ""); }

  async function saveUserRole(userId: number) {
    if (!bundle) return;
    try {
      setBusyRoleUpdate(true); setError("");
      // perfil vazio = derivar do cargo (backend re-alinha ao seed da role).
      const body: Record<string, unknown> = { role: editRole, department_id: editDeptId || null };
      if (editPerfilId) body.perfil_acesso_id = editPerfilId;
      await putJson(bundle.auth, `/api/admin/users/${userId}`, body);
      setNotice("Usuario atualizado.");
      setEditingUserId(null);
      // Patch local (evita full-scan server-side de /api/operators por
      // clique): os valores novos ja estao no estado do editor; perfil
      // vazio = seed derivado do cargo (mesma derivacao do backend).
      setOperators((prev) => prev.map((op) => op.id === userId
        ? { ...op, role: editRole, department_id: editDeptId || null, perfil_acesso_id: editPerfilId || `perfil_${editRole}` }
        : op));
      if (!snapshotMode) await refreshPollingViews();
    }
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

  // useCallback: o BillingHealthBanner depende da IDENTIDADE desta funcao no
  // seu useEffect. Sem memoizacao, cada render do provider (todo publish de
  // snapshot de contacts/conversations) recriava a funcao e re-disparava o
  // GET /billing-status em loop (o spam visivel no log). Memoizada por
  // [bundle], o efeito do banner roda so quando muda bundle/canal/role.
  // Mesmo motivo do fetchTemplates abaixo.
  const fetchBillingStatus = useCallback(async (channelId: number): Promise<{ ok: boolean; has_payment_method: boolean; error?: string } | null> => {
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
  }, [bundle]);

  // useCallback: o TemplatePickerModal depende da IDENTIDADE desta funcao no
  // useEffect — sem memoizacao, cada publish do snapshot recriava a funcao,
  // re-disparava o fetch e RESETAVA o modal (flicker continuo + GETs em loop
  // + impossivel completar o envio).
  const fetchTemplates = useCallback(async (channelId?: number | null): Promise<WhatsAppTemplate[]> => {
    if (!bundle) return [];
    const qs = channelId ? `?channel_id=${encodeURIComponent(String(channelId))}` : "";
    try {
      const res = await getJson<{ templates: WhatsAppTemplate[] }>(bundle.auth, `/api/wa/templates${qs}`);
      return res.templates || [];
    } catch (e) {
      setError(errorText(e));
      return [];
    }
  }, [bundle]);

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
      setContactsCountNonce((n) => n + 1);
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

  // useCallback: o contador da sidebar (ContactList) depende da IDENTIDADE
  // desta funcao no useEffect — mesmo motivo do fetchBillingStatus acima.
  // Antes o ContactList chamava loadAllContacts() (full scan de ~6.5k docs
  // no backend) so pra exibir o TOTAL no header, em todo page-load de todo
  // usuario — o maior dreno de leitura do Firestore (~250k reads/dia; ver
  // docs/INVESTIGACAO_READS_FIRESTORE_2026-07.md). count_only=1 usa
  // aggregate count (~7 reads). A lista completa continua sendo carregada
  // APENAS quando o picker + e aberto (NewContactModal -> loadAllContacts).
  const countAllContacts = useCallback(async (): Promise<number> => {
    if (!bundle) return 0;
    try {
      const r = await getJson<{ total: number }>(bundle.auth, "/api/wa/contacts/all?count_only=1");
      return r.total || 0;
    } catch {
      // Contador e cosmetico — falha nao vira banner de erro nem retry.
      return 0;
    }
  }, [bundle]);

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
    setContactsCountNonce((n) => n + 1);
  }

  // "Carregar mais" do "Meus" (operador comum): pagina ESTATICA via getDocs do
  // mine com limite crescente (50 -> 100 -> 150...). O listener ao vivo continua
  // em 50; isto e leitura UNICA (sem snapshot). Usa o indice composto
  // (assigned_to_uid, last_message_at). Admin/supervisor ja ouvem 300 ao vivo.
  // Busca de NAO LIDAS (filtro "Nao lidas" do select de qualificacao): getDocs
  // por escopo da caixa com unread_count>0, ordenado por unread_count desc +
  // recencia (Firestore exige o primeiro orderBy no campo da desigualdade); o
  // cliente reordena por recencia. Indices em firestore.indexes.json:
  // (assigned_to_uid, unread_count desc, last_message_at desc) e
  // (unread_count desc, last_message_at desc). Mesmo escopo/rules das janelas
  // ao vivo: operador = minhas ou pool; admin em Equipe = tenant inteiro.
  // Pagina crescente (100, 200...). Resultado vai pra camada estatica
  // (pagedConversations); contato hidrata sob demanda (extraContacts).
  async function loadUnreadConversations(reset = false) {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations || !sessionUser) return;
    if (loadingMoreConvs && !reset) return;
    const limit = reset ? UNREAD_PAGE : unreadPageLimit + UNREAD_PAGE;
    const viewAtStart = activeViewRef.current;
    const reqId = ++unreadReqRef.current;
    const keepId = selectedThreadId;
    const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);
    const tail = [
      where("unread_count", ">", 0),
      orderBy("unread_count", "desc"),
      orderBy("last_message_at", "desc"),
      firestoreLimit(limit),
    ] as const;
    const scopes: ReturnType<typeof query>[] = [];
    if (viewAtStart === "meus") {
      if (sessionUser.firebase_uid) scopes.push(query(waConversations, where("assigned_to_uid", "==", sessionUser.firebase_uid), ...tail));
    } else if (viewAtStart === "novos" || viewAtStart === "bot") {
      scopes.push(query(waConversations, where("assigned_to_uid", "==", ""), ...tail));
      scopes.push(query(waConversations, where("assigned_to_uid", "==", null), ...tail));
    } else if (viewAtStart === "equipe" && canSeeAll) {
      scopes.push(query(waConversations, ...tail));
    }
    if (!scopes.length) { setUnreadHasMore(false); return; }
    setLoadingMoreConvs(true);
    try {
      const snaps = await Promise.all(scopes.map((q) => getDocs(q)));
      // Resposta tardia: trocou de caixa, saiu do modo ou ja ha busca mais nova.
      if (activeViewRef.current !== viewAtStart || !unreadModeRef.current || unreadReqRef.current !== reqId) return;
      const next = new Map<string, Conversation>();
      for (const snap of snaps) {
        for (const d of snap.docs) {
          const c = normalizeConversation(d.data() as Record<string, unknown>, d.id);
          next.set(c.id, c);
        }
      }
      // Preserva a thread selecionada que so vivia na camada estatica (senao o
      // chat aberto fecha ao paginar).
      setPagedConversations((prev) => {
        const keep = keepId ? prev.get(keepId) : undefined;
        if (keepId && keep && !next.has(keepId)) next.set(keepId, keep);
        return next;
      });
      setUnreadPageLimit(limit);
      // Ha mais pagina enquanto ALGUM escopo encher o limite.
      setUnreadHasMore(snaps.some((s) => s.docs.length >= limit));
    } catch (e) {
      // Indice ainda construindo / rules: degrada pro filtro client-side (so o
      // que ja esta carregado) sem travar a caixa — aviso como ERRO, nao sucesso.
      console.warn("busca de nao lidas indisponivel:", errorText(e));
      setError("Busca de não lidas indisponível no momento — mostrando só as conversas já carregadas.");
      setUnreadHasMore(false);
    } finally {
      setLoadingMoreConvs(false);
    }
  }

  async function loadMoreMyConversations() {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations || !sessionUser?.firebase_uid) return;
    if (canSeeAll) return;
    if (loadingMoreConvs) return;
    const nextLimit = myConvPageLimit + 50;
    const viewAtStart = activeViewRef.current;
    setLoadingMoreConvs(true);
    try {
      const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);
      const q = query(
        waConversations,
        where("assigned_to_uid", "==", sessionUser.firebase_uid),
        orderBy("last_message_at", "desc"),
        firestoreLimit(nextLimit),
      );
      const snap = await getDocs(q);
      if (activeViewRef.current !== viewAtStart) return; // trocou de caixa: reset ja limpou
      const fetched = snap.docs.map((d) => normalizeConversation(d.data() as Record<string, unknown>, d.id));
      const next = new Map<string, Conversation>();
      fetched.forEach((c) => next.set(c.id, c));
      setPagedConversations(next);
      setMyConvPageLimit(nextLimit);
      // Se voltou menos que o pedido, nao ha mais paginas.
      setMyConvHasMore(snap.docs.length >= nextLimit);
    } catch (e) {
      setError(`Falha ao carregar mais conversas: ${errorText(e)}`);
    } finally {
      setLoadingMoreConvs(false);
    }
  }

  // "Carregar mais" da POOL sem dono (operador comum em Novos/Recepcao):
  // pagina ESTATICA via getDocs dos DOIS targets sem dono (assigned_to_uid ==
  // "" e == null) com limite crescente (50 -> 100 -> 150...) em cada um. Mesma
  // shape das queries do listener ao vivo (que as rules ja autorizam pro
  // operador: pool sem dono), so o limite cresce; indice composto
  // (assigned_to_uid, last_message_at). Leitura UNICA (sem snapshot). As
  // conversas paginadas passam pelos mesmos filtros de caixa
  // (novosConversations: lead sem dono, bot_completed, setor...) — o contato
  // e hidratado sob demanda pelo effect de extraContacts.
  async function loadMorePoolConversations() {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations || !sessionUser) return;
    if (loadingMoreConvs) return;
    const nextLimit = poolConvPageLimit + 50;
    const viewAtStart = activeViewRef.current;
    setLoadingMoreConvs(true);
    try {
      const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);
      const poolQuery = (uid: string | null) => query(
        waConversations,
        where("assigned_to_uid", "==", uid),
        orderBy("last_message_at", "desc"),
        firestoreLimit(nextLimit),
      );
      const [blankSnap, nullSnap] = await Promise.all([getDocs(poolQuery("")), getDocs(poolQuery(null))]);
      if (activeViewRef.current !== viewAtStart) return; // trocou de caixa: reset ja limpou
      const next = new Map<string, Conversation>();
      for (const d of [...blankSnap.docs, ...nullSnap.docs]) {
        const c = normalizeConversation(d.data() as Record<string, unknown>, d.id);
        next.set(c.id, c);
      }
      setPagedConversations(next);
      setPoolConvPageLimit(nextLimit);
      // Ha mais paginas enquanto ALGUM dos targets ainda encher o limite.
      setPoolConvHasMore(blankSnap.docs.length >= nextLimit || nullSnap.docs.length >= nextLimit);
    } catch (e) {
      setError(`Falha ao carregar mais conversas: ${errorText(e)}`);
    } finally {
      setLoadingMoreConvs(false);
    }
  }

  // "Carregar mais" da janela GLOBAL (admin/supervisor — Equipe, Bot e
  // Novos/Recepcao): pagina ESTATICA via getDocs
  // da janela global com limite crescente (300 -> 600 -> 900...). O listener
  // ao vivo continua em ADMIN_CONV_WINDOW; isto e leitura UNICA (sem snapshot),
  // orderBy single-field = indice automatico. As rules ja autorizam a query
  // ampla pro role privilegiado (mesma shape do listener do target "all").
  async function loadMoreAllConversations() {
    if (!bundle?.db || !config?.firestore.collections.wa_conversations) return;
    if (!canSeeAll) return;
    if (loadingMoreConvs) return;
    const nextLimit = allConvPageLimit + ADMIN_CONV_WINDOW;
    const viewAtStart = activeViewRef.current;
    setLoadingMoreConvs(true);
    try {
      const waConversations = collection(bundle.db, config.firestore.collections.wa_conversations);
      const q = query(
        waConversations,
        orderBy("last_message_at", "desc"),
        firestoreLimit(nextLimit),
      );
      const snap = await getDocs(q);
      if (activeViewRef.current !== viewAtStart) return; // trocou de caixa: reset ja limpou
      const fetched = snap.docs.map((d) => normalizeConversation(d.data() as Record<string, unknown>, d.id));
      const next = new Map<string, Conversation>();
      fetched.forEach((c) => next.set(c.id, c));
      setPagedConversations(next);
      setAllConvPageLimit(nextLimit);
      // Se voltou menos que o pedido, nao ha mais paginas.
      setAllConvHasMore(snap.docs.length >= nextLimit);
    } catch (e) {
      setError(`Falha ao carregar mais conversas: ${errorText(e)}`);
    } finally {
      setLoadingMoreConvs(false);
    }
  }

  async function openConversationForContact(contact_id: number, channel_id?: number): Promise<string | null> {
    if (!bundle) return null;
    try {
      setError("");
      const payload: Record<string, unknown> = { contact_id };
      if (channel_id) payload.channel_id = channel_id;
      const res = await sendJson(bundle.auth, "/api/wa/conversation/open", payload) as {
        conversation_id: string; contact_id: number; channel_id: number;
        assigned_to?: number | null; assigned_to_uid?: string;
      };
      // A conversa pode estar FORA do top-50 ao vivo (ex.: contato antigo
      // achado no picker). Fixa em extraConversations pra (a) selectedConversation
      // resolver o contact_id e o chat abrir, e (b) o auto-select nao derrubar o
      // painel quando o snapshot republica so com o top-50. O backend
      // (/conversation/open) valida o acesso via _require_contact_access (operador
      // comum so abre proprio/pool/thread que atende) -> isolamento por tenant E
      // entre operadores respeitado. No merge (allConversations), a versao AO VIVO do
      // listener sempre sobrescreve esta estatica.
      if (res.conversation_id) {
        const cid = res.conversation_id;
        // Dono REAL devolvido pelo backend (nao forja "meu"): se a conversa ja
        // era de outro operador, vem o dono original -> nao vira fantasma em
        // "Meus" com dono falso.
        const realAssignedTo = res.assigned_to ?? null;
        const realAssignedUid = res.assigned_to_uid ?? "";
        if (!conversations.some((c) => c.id === cid)) {
          setExtraConversations((prev) => {
            if (prev.has(cid)) return prev;
            const next = new Map(prev);
            next.set(cid, normalizeConversation({
              id: cid,
              contact_id: res.contact_id,
              channel_id: res.channel_id,
              assigned_to: realAssignedTo,
              assigned_to_uid: realAssignedUid,
              status: "open",
              unread_count: 0,
            }, cid));
            return next;
          });
        }
        setSelectedThreadId(cid);
        // So pula pra "Meus" se a conversa e de fato do operador — senao ela nao
        // apareceria na lista filtrada de "Meus" (so abriria no chat). O chat
        // abre via selectedThreadId independentemente da view.
        const mine = realAssignedTo === sessionUser?.id || (!!realAssignedUid && realAssignedUid === sessionUser?.firebase_uid);
        if (mine) setActiveView("meus");
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
    // Manda a thread ABERTA: o backend carimba o dono nela (e nas demais
    // threads orfas do contato) explicitamente e grava a system message do
    // assume nessa thread — antes dependia do efeito colateral da system
    // message na thread do contact.channel_id, que pode nao ser a que o
    // operador esta olhando (lead multi-canal).
    const threadId = selectedConversation?.contact_id === contactId ? selectedConversation.id : null;
    try { setBusyAssume(true); setError(""); setNotice(""); await sendJson(bundle.auth, `/api/wa/assume/${contactId}`, threadId ? { conversation_id: threadId } : {}); setNotice("Atendimento assumido."); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyAssume(false); }
  }

  // ADR 0010: devolve o lead a POOL da recepcao (acao explicita do menu).
  async function returnContactToPool(contactId: number) {
    if (!bundle) return;
    try { setBusyAssume(true); setError(""); setNotice(""); await sendJson(bundle.auth, `/api/wa/contact/${contactId}/return-to-pool`, {}); setNotice("Lead devolvido à recepção."); if (!snapshotMode) await refreshPollingViews(); }
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
      // Se a conversa transferida estava FIXADA (aberta pelo picker, fora do
      // top-50), tira da camada estatica — senao ficaria fantasma em "Meus" com
      // dono defasado (o ao vivo nao reentrega thread fora do escopo).
      removeExtraConversation(selectedThreadId);
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
  // `outcome` (reforma 2026-09): qualificacao final + notas do gate de
  // desfecho, no MESMO request — o backend recusa fechar lead novo/
  // em_atendimento sem isso. Retorna sucesso pro modal so fechar se salvou.
  async function setAttendance(conversationId: string, status: "fechado_manual" | "aberto", outcome?: { qualification: string; notes: string }): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      const body: Record<string, unknown> = { status };
      if (outcome) { body.qualification = outcome.qualification; body.notes = outcome.notes; }
      await sendJson(bundle.auth, `/api/wa/conversation/${conversationId}/set-attendance`, body);
      setNotice(status === "fechado_manual" ? "Atendimento fechado." : "Atendimento reaberto.");
      if (outcome && selectedContact) {
        // Mesmo patch do saveQualification: camada estatica + seed do form,
        // senao chip/filtro da sidebar e painel ficam com o valor antigo.
        // `selectedContact` e o do momento da CHAMADA (o lead do modal) —
        // correto pro patch por id. Ja o estado GLOBAL do form so pode ser
        // tocado se o usuario ainda estiver NESSE lead: se trocou de conversa
        // durante o await, sobrescreveria o form do lead novo com dados do
        // antigo (revisao adversarial 2026-09-01). detailSeedRef acompanha a
        // selecao (efeito de seed), entao id divergente = usuario trocou.
        const contactId = selectedContact.id;
        setExtraContacts((prev) => {
          const cur = prev.get(contactId);
          if (!cur) return prev;
          const next = new Map(prev);
          next.set(contactId, { ...cur, qualification: outcome.qualification, notes: outcome.notes });
          return next;
        });
        if (detailSeedRef.current?.id === contactId) {
          detailSeedRef.current = { id: contactId, qualification: outcome.qualification, notes: outcome.notes };
          setQualification(outcome.qualification);
          setNotes(outcome.notes);
        }
      }
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) { setError(errorText(e)); return false; }
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

  async function openSettingsPage(page: "chat" | "quick" | "admin" | "perfis" | "whatsapp" | "whatsapp-standard" | "dashboard") {
    if (!bundle) return;
    if (page === "whatsapp" || page === "whatsapp-standard" || page === "perfis") {
      setShowSettings(page);
      return;
    }
    try {
      setBusySettings(true);
      const [sys, usr] = await Promise.all([getJson<SystemSettings>(bundle.auth, "/api/settings/system"), getJson<UserSettings>(bundle.auth, "/api/settings/user")]);
      setSystemSettings(sys); setUserSettings(usr); setSettingsLoaded(true); setShowSettings(page);
    } catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveSystemSettingsAction() {
    if (!bundle) return;
    // Trava: mensagem global sem titulo/atalho/texto ou atalho repetido nao salva.
    const problem = quickMessagesProblem(systemSettings.quick_messages_global, "Mensagens globais");
    if (problem) { setError(problem); return; }
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/system", systemSettings) as SystemSettings; setSystemSettings(r); setSettingsLoaded(true); setNotice("Configuracoes do sistema salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveUserSettingsAction() {
    if (!bundle) return;
    const problem = quickMessagesProblem(userSettings.quick_messages, "Minhas mensagens rapidas");
    if (problem) { setError(problem); return; }
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/user", userSettings) as UserSettings; setUserSettings(r); setNotice("Suas configuracoes salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  // =========================================================================
  // Value
  // =========================================================================

  const value: CrmContextValue = {
    config, bundle, firebaseUser, sessionUser, tenantName, operators, departments, channels, booting, busyLogin, snapshotMode,
    perfil, can, canSeeAll,
    theme, toggleTheme,
    loginWithGoogle, loginWithEmail, resetPassword, logout, mfaPending, resolveMfaCode, cancelMfa,
    contacts, contactsById, conversations, selectedContactId, selectedContact, selectedConversation,
    selectedThreadId, setSelectedThreadId,
    activeView, setActiveView, novosConversations, meusConversations, nqConversations, equipeConversations, botConversations, backupConversations, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, backupUnread, equipeOperatorFilter, setEquipeOperatorFilter, equipeFiltered,
    messages, setMessages, visibleMessages, messageLimit, setMessageLimit, loadingMore, setLoadingMore, messagesRef, scrollIntentRef, prevMessageCountRef,
    transcribingMessageId, transcribeMessage,
    replyTarget, startReplyToMessage, cancelReply, copyMessageText: copyMessageTextAction,
    draft, setDraft, busySend, busyUpload, busyAudio, quickSuggestions, setQuickSuggestions, quickSelectedIndex,
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
    loadAllContacts, countAllContacts, contactsCountNonce, refreshAllContacts, openConversationForContact, loadConflicts,
    correctMessage, correctionTarget, startCorrection, cancelCorrection,
    fetchTemplates, sendTemplate, reopenConversation, busyTemplate, fetchBillingStatus,
    busySave, busyTransfer, busyAssume, saveQualification, assumeContact, returnContactToPool, transferContact, reassignLead, supervisorTakeover, setAttendance, loadProtocol,
    editingUserId, setEditingUserId, editRole, setEditRole, editPerfilId, setEditPerfilId, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole,
    coexEditingUserId, coexPhoneInput, setCoexPhoneInput, busyCoexUpdate, startEditCoex, cancelEditCoex, saveCoex, revokeCoex,
    takeoverConversation, returnConversation,
    showSettings, setShowSettings, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, toggleSettingsMenu, openSettingsPage, saveSystemSettingsAction, saveUserSettingsAction, settingsMenuRef,
    search, setSearch, searchText, qualificationFilter, setQualificationFilter, channelFilter, setChannelFilter, myChannelOptions, filteredConversations, viewConversations,
    error, setError, notice, setNotice,
    loadMoreMyConversations, canLoadMoreMine, loadingMoreConvs,
    loadMorePoolConversations, canLoadMorePool,
    loadMoreAllConversations, canLoadMoreAll,
    loadUnreadConversations, canLoadMoreUnread, unreadMode, peekMode, setPeekMode, canPeek,
    refreshPollingViews,
  };

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
