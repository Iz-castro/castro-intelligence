// Regressao local das GUIAS DE CONVERSA. Rode (na raiz): node tools/sim_chat_tabs.mjs
// Executa o codigo REAL (frontend/src/hooks/useChatTabs.ts e
// frontend/src/components/chat/ChatTabs.tsx) compilado pelo esbuild ja
// instalado por npm ci em frontend; sem rede/ADC. React (hooks minimos, com
// layout effect antes dos passivos), Firestore (docs/listeners em memoria),
// localStorage e teclado sao simulados. Confere tambem, por AST/texto, a
// fiacao em App.tsx, CrmContext.tsx e styles.css. Nao substitui teste em
// navegador (layout, foco, StrictMode, rules reais do Firestore).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const frontendRequire = createRequire(new URL("../frontend/package.json", import.meta.url));
const { transformSync } = frontendRequire("esbuild");
const ts = frontendRequire("typescript");
const srcRoot = new URL("../frontend/src/", import.meta.url);
let checks = 0;
function check(value, message) { assert.ok(value, message); checks++; }
const same = (actual, expected) => JSON.stringify(actual) === JSON.stringify(expected);

// --- React minimo -----------------------------------------------------------
let rendering = null;
const reactStub = {
  useState: (...args) => rendering.useState(...args),
  useRef: (...args) => rendering.useRef(...args),
  useMemo: (...args) => rendering.useMemo(...args),
  useCallback: (...args) => rendering.useCallback(...args),
  useEffect: (...args) => rendering.useEffect(...args),
  useLayoutEffect: (...args) => rendering.useLayoutEffect(...args),
};
const jsxStub = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: "Fragment" };

function createHarness(render) {
  const slots = [];
  let cursor = 0, dirty = true, layout = [], passive = [], output = null, mounted = true;
  const changed = (prev, next) => !prev || !next || prev.length !== next.length || next.some((value, index) => !Object.is(value, prev[index]));
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) {
        const slot = { value: typeof initial === "function" ? initial() : initial };
        slot.setter = (value) => {
          const next = typeof value === "function" ? value(slot.value) : value;
          if (!Object.is(next, slot.value)) { slot.value = next; dirty = true; }
        };
        slots[index] = slot;
      }
      return [slots[index].value, slots[index].setter];
    },
    useRef(initial) { const index = cursor++; if (!(index in slots)) slots[index] = { current: initial }; return slots[index]; },
    useMemo(factory, deps) { const index = cursor++; if (changed(slots[index]?.deps, deps)) slots[index] = { value: factory(), deps }; return slots[index].value; },
    useCallback(callback, deps) { const index = cursor++; if (changed(slots[index]?.deps, deps)) slots[index] = { value: callback, deps }; return slots[index].value; },
    useEffect(callback, deps) { const index = cursor++; if (changed(slots[index]?.deps, deps)) passive.push({ index, callback, deps }); },
    useLayoutEffect(callback, deps) { const index = cursor++; if (changed(slots[index]?.deps, deps)) layout.push({ index, callback, deps }); },
  };
  const harness = {
    get out() { return output; },
    flush() {
      let renders = 0;
      while (dirty && mounted) {
        assert.ok(++renders <= 60, "Loop de render/effect");
        dirty = false; cursor = 0; layout = []; passive = [];
        rendering = hooks;
        try { output = render(); } finally { rendering = null; }
        // Como o React: layout effects (cleanup + setup) antes dos passivos.
        for (const queue of [layout, passive]) {
          for (const effect of queue) { const cleanup = slots[effect.index]?.cleanup; if (typeof cleanup === "function") cleanup(); }
          for (const effect of queue) slots[effect.index] = { deps: effect.deps, cleanup: effect.callback() };
        }
      }
      return output;
    },
    async settle() { for (let index = 0; index < 6; index++) { await new Promise((resolve) => setImmediate(resolve)); harness.flush(); } },
    unmount() {
      mounted = false;
      for (const slot of slots) if (slot && typeof slot.cleanup === "function" && "deps" in slot) slot.cleanup();
    },
  };
  return harness;
}

// --- Firestore / navegador simulados -----------------------------------------
let world = null;
const docSnap = (id, data, fromCache = false) => ({ id, exists: () => data != null, data: () => data, metadata: { fromCache } });
const firebaseStub = {
  async getSessionDoc(_auth, ref) {
    world.reads.push(ref.id);
    await Promise.resolve();
    if (world.denied.has(ref.id)) throw Object.assign(new Error("Missing or insufficient permissions."), { code: "permission-denied" });
    if (world.transient.has(ref.id)) throw Object.assign(new Error("client is offline"), { code: "unavailable" });
    return docSnap(ref.id, world.docs.get(ref.id));
  },
  watchSessionDocument(_auth, ref, onNext, onError) {
    const entry = { onNext, onError };
    if (!world.listeners.has(ref.id)) world.listeners.set(ref.id, new Set());
    world.listeners.get(ref.id).add(entry);
    return () => { world.listeners.get(ref.id)?.delete(entry); };
  },
};
// Como o SDK: referencia de documento exige numero par de segmentos e id nao vazio.
const firestoreStub = {
  doc: (_db, path, id) => {
    if (!id || `${path}/${id}`.split("/").length % 2 !== 0) throw Object.assign(new Error("Invalid document reference"), { code: "invalid-argument" });
    return { path: `${path}/${id}`, id };
  },
};
const fakeWindow = {
  localStorage: null,
  keydown: new Set(),
  confirmAnswer: true,
  confirms: [],
  confirm(message) { this.confirms.push(message); return this.confirmAnswer; },
  addEventListener(type, handler) { if (type === "keydown") this.keydown.add(handler); },
  removeEventListener(type, handler) { if (type === "keydown") this.keydown.delete(handler); },
};
function makeStorage() {
  const map = new Map();
  return {
    map,
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => { map.set(key, String(value)); },
    removeItem: (key) => { map.delete(key); },
  };
}

// --- Carga dos modulos reais --------------------------------------------------
function loadModule(relative, loader, requireStub) {
  const source = readFileSync(new URL(relative, srcRoot), "utf8");
  const code = transformSync(source, { loader, format: "cjs", jsx: "automatic", target: "es2020" }).code;
  const module = { exports: {} };
  new Function("module", "exports", "require", "window", code)(module, module.exports, requireStub, fakeWindow);
  return module.exports;
}
const normalization = loadModule("utils/normalization.ts", "ts", (name) => { throw new Error(`Import nao simulado: ${name}`); });
const tabsModule = loadModule("hooks/useChatTabs.ts", "ts", (name) => {
  if (name === "react") return reactStub;
  if (name === "firebase/firestore") return firestoreStub;
  if (name === "../firebase") return firebaseStub;
  if (name === "../utils/normalization") return normalization;
  throw new Error(`Import nao simulado: ${name}`);
});
let crmContext = null;
const { ChatTabs } = loadModule("components/chat/ChatTabs.tsx", "tsx", (name) => {
  if (name === "react") return reactStub;
  if (name === "react/jsx-runtime") return jsxStub;
  if (name === "../../context/CrmContext") return { useCrm: () => crmContext };
  if (name === "../../hooks/useChatTabs") return tabsModule;
  throw new Error(`Import nao simulado: ${name}`);
});

// --- Fixtures -----------------------------------------------------------------
const PATH = "castro_crm_tenants/t1/wa_conversations";
const OPERATORS = [{ id: 5, display_name: "Operadora" }, { id: 9, display_name: "Fulano" }, { id: 1, display_name: "Admin" }];
const waId = (n) => `5531900000${String(n).padStart(3, "0")}`;
const tid = (n) => `1__${waId(n)}`;
const raw = (n, extra = {}) => ({
  contact_id: 100 + n, wa_id: waId(n), channel_id: 1, channel_type: "standard",
  assigned_to: 5, assigned_to_uid: "uid-op", unread_count: 0, attendance_status: "aberto",
  last_message_at: new Date(Date.UTC(2026, 9, 28, 12, n)).toISOString(), ...extra,
});
const thread = (n, extra) => normalization.normalizeConversation(raw(n, extra), tid(n));
const contact = (n, extra = {}) => ({ id: 100 + n, wa_id: waId(n), display_name: `Cliente ${n}`, assigned_to: 5, ...extra });
// Copia OTIMISTA que o picker poe em extraConversations (sem attendance_status).
const optimistic = (n) => normalization.normalizeConversation({ id: tid(n), contact_id: 100 + n, channel_id: 1, assigned_to: 5, assigned_to_uid: "uid-op", status: "open", unread_count: 0 }, tid(n));
const STORAGE_TABS = (uid) => `castro_crm.tabs.${uid}`;
const STORAGE_ACTIVE = (uid) => `castro_crm.active_tab.${uid}`;
const STORAGE_DRAFTS = (uid) => `castro_crm.drafts.${uid}`;
const storedDrafts = (storage, uid = "uid-op") => JSON.parse(storage.getItem(STORAGE_DRAFTS(uid)) || "{}");

// Host = recorte do CrmProvider na ORDEM REAL dos hooks: selecao, merge
// (extra < guias < ao vivo), effect de selecao orfa e effect de correcao
// ANTES do hook, setDraft por render e startCorrection/cancelCorrection com a
// ordem do provider (ref da correcao e modo normal antes do texto).
function makeHost(env0) {
  return () => {
    const [selectedThreadId, setSelectedThreadId] = reactStub.useState(null);
    const [tabPins, setTabPins] = reactStub.useState(() => new Map());
    const [draft, setDraftState] = reactStub.useState("");
    const [internalMode, setInternalMode] = reactStub.useState(false);
    const [env, setEnv] = reactStub.useState(env0);
    const holdEmptySelectionRef = reactStub.useRef(false);
    const correctionRef = reactStub.useRef(null);
    const allConversations = reactStub.useMemo(() => {
      const map = new Map();
      env.extra.forEach((conversation) => map.set(conversation.id, conversation));
      tabPins.forEach((conversation) => map.set(conversation.id, conversation));
      env.live.forEach((conversation) => map.set(conversation.id, conversation));
      return [...map.values()];
    }, [env.live, env.extra, tabPins]);
    reactStub.useEffect(() => {
      if (!selectedThreadId) return;
      holdEmptySelectionRef.current = false;
      if (!allConversations.some((conversation) => conversation.id === selectedThreadId)) setSelectedThreadId(null);
    }, [allConversations, selectedThreadId]);
    reactStub.useEffect(() => {
      if (correctionRef.current) { correctionRef.current = null; setDraft(""); }
    }, [selectedThreadId]);
    const tabs = tabsModule.useChatTabs({
      enabled: env.enabled, storageUid: env.storageUid, auth: env.auth, db: env.db, conversationsPath: PATH,
      snapshotMode: env.snapshotMode, sessionUser: env.sessionUser, canSeeAll: env.canSeeAll, operators: OPERATORS,
      allConversations, liveConversations: env.live, contactsById: env.contacts, unavailableContactIds: env.unavailable,
      selectedThreadId, setSelectedThreadId, holdEmptySelectionRef, setTabPins, setDraftState,
      internalMode, setInternalMode, correctionTargetRef: correctionRef, suggestionsOpen: env.suggestionsOpen,
      setNotice: (message) => world.notices.push(message), scopeGenerationRef: world.scopeGeneration,
    });
    const setDraft = (value) => tabs.writeDraft(selectedThreadId, value);
    const startCorrection = (text) => { correctionRef.current = { id: 31 }; setInternalMode(false); setDraft(text); };
    const cancelCorrection = () => { correctionRef.current = null; setDraft(""); };
    return { tabs, selectedThreadId, setSelectedThreadId, draft, setDraft, internalMode, setInternalMode, startCorrection, cancelCorrection, tabPins, allConversations, holdEmptySelectionRef, setEnv };
  };
}

function boot({ uid = "uid-op", userId = 5, canSeeAll = false, enabled = true, snapshotMode = true, storage = makeStorage(), live = [], extra = [], contacts = [], docs = {}, denied = [], transient = [] } = {}) {
  world = {
    notices: [], reads: [], listeners: new Map(), scopeGeneration: { current: 0 },
    docs: new Map(Object.entries(docs)), denied: new Set(denied), transient: new Set(transient),
  };
  fakeWindow.localStorage = storage;
  const env = {
    enabled, storageUid: enabled ? uid : "", auth: { uid }, db: { name: "db" }, snapshotMode, canSeeAll,
    sessionUser: { id: userId, firebase_uid: uid, display_name: "Operadora", role: canSeeAll ? "admin" : "operador" },
    live, extra, contacts: new Map(contacts.map((item) => [item.id, item])), unavailable: new Set(), suggestionsOpen: false,
  };
  const h = createHarness(makeHost(env));
  h.flush();
  const w = world;
  return {
    h, w, storage,
    select(id) { h.out.setSelectedThreadId(id); h.flush(); },
    type(text) { h.out.setDraft(text); h.flush(); },
    mode(internal) { h.out.setInternalMode(internal); h.flush(); },
    update(patch) { h.out.setEnv((prev) => ({ ...prev, ...patch })); h.flush(); },
    setLive(n, extra2) { h.out.setEnv((prev) => ({ ...prev, live: prev.live.map((item) => (item.id === tid(n) ? thread(n, extra2) : item)) })); h.flush(); },
    addLive(n, extra2) { h.out.setEnv((prev) => ({ ...prev, live: [...prev.live, thread(n, extra2)] })); h.flush(); },
    setExtra(list) { h.out.setEnv((prev) => ({ ...prev, extra: list })); h.flush(); },
    emit(id, data, fromCache = false) { for (const entry of [...(w.listeners.get(id) || [])]) entry.onNext(docSnap(id, data, fromCache)); h.flush(); },
    deny(id) { for (const entry of [...(w.listeners.get(id) || [])]) entry.onError({ code: "permission-denied" }); h.flush(); },
    listening: () => [...w.listeners.entries()].filter(([, set]) => set.size > 0).map(([id]) => id).sort(),
    lastNotice: () => w.notices[w.notices.length - 1] || "",
    tab: (id) => h.out.tabs.tabInfo.find((item) => item.id === id),
  };
}
const range = (from, to) => Array.from({ length: to - from + 1 }, (_, index) => from + index);
function press(key, { ctrl = true, alt = true, tag = "TEXTAREA", handled = false } = {}) {
  const event = { key, altKey: alt, ctrlKey: ctrl, metaKey: false, shiftKey: false, isComposing: false, target: { tagName: tag }, defaultPrevented: handled, preventDefault() { this.defaultPrevented = true; } };
  for (const handler of [...fakeWindow.keydown]) handler(event);
  return event;
}

// --- Cenarios -----------------------------------------------------------------
async function openLimitAndNeighbor() {
  const s = boot({ live: range(1, 12).map((n) => thread(n)), contacts: range(1, 12).map((n) => contact(n)) });
  try {
    s.select(tid(1));
    check(same(s.h.out.tabs.openTabs, [tid(1)]), "Abrir conversa cria a guia");
    check(s.h.out.tabPins.has(tid(1)), "Guia nova ganha pin propria (tabPins)");
    const first = s.h.out.tabs.tabInfo[0];
    check(first.isActive && first.name === "Cliente 1" && first.channel === "Standard" && first.unread === 0, "tabInfo: ativa, nome do contato e chip Standard");
    check(same(s.listening(), [tid(1)]), "Guia aberta = 1 listener no doc da thread");
    s.select(tid(1));
    check(s.h.out.tabs.openTabs.length === 1, "Reabrir a mesma conversa nao duplica a guia");
    for (const n of range(2, 10)) s.select(tid(n));
    check(s.h.out.tabs.openTabs.length === 10 && s.listening().length === 10, "Dez guias = dez listeners");
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    check(s.h.out.selectedThreadId === tid(1), "Clique na guia seleciona a thread");
    s.select(tid(11));
    const afterEleven = s.h.out.tabs.openTabs;
    check(afterEleven.length === 10 && afterEleven.includes(tid(1)) && !afterEleven.includes(tid(2)) && afterEleven[9] === tid(11), "11a guia fecha a MENOS USADA (2), nao a que a operadora acabou de usar (1)");
    check(!s.h.out.tabPins.has(tid(2)) && !s.listening().includes(tid(2)) && s.listening().length === 10, "Guia derrubada perde pin e listener");
    check(s.w.notices.length === 0, "Limite sem rascunho perdido nao gera aviso");
    s.h.out.tabs.activateTab(tid(5)); s.h.flush();
    s.h.out.tabs.closeTab(tid(5)); s.h.flush();
    check(!s.h.out.tabs.openTabs.includes(tid(5)) && s.h.out.selectedThreadId === tid(6), "Fechar a ativa seleciona a vizinha da direita");
    s.h.out.tabs.activateTab(tid(11)); s.h.flush();
    s.h.out.tabs.closeTab(tid(11)); s.h.flush();
    check(s.h.out.selectedThreadId === tid(10), "Fechar a ultima (ativa) seleciona a da esquerda");
    s.h.out.tabs.closeTab(tid(3)); s.h.flush();
    check(s.h.out.selectedThreadId === tid(10) && !s.h.out.tabs.openTabs.includes(tid(3)), "Fechar guia nao ativa mantem a selecao");
    s.setLive(4, { unread_count: 3 });
    check(s.tab(tid(4)).unread === 3 && !s.tab(tid(4)).isActive, "Badge: guia nao ativa mostra unread_count da conversa");
    s.h.out.tabs.closeAllTabs(); s.h.flush();
    check(s.h.out.tabs.openTabs.length === 0 && s.h.out.selectedThreadId === null && s.h.out.holdEmptySelectionRef.current === true, "Fechar todas zera guias e volta ao placeholder");
    check(s.listening().length === 0 && s.h.out.tabPins.size === 0, "Fechar todas encerra listeners e pins");
    check(s.storage.getItem(STORAGE_TABS("uid-op")) === null && s.storage.getItem(STORAGE_ACTIVE("uid-op")) === null, "Fechar todas limpa o storage do uid");
  } finally { s.h.unmount(); }
}

// Item 6 (X5): limite por uso, preferindo guia sem rascunho.
async function limitLeastUsed() {
  const s = boot({ live: range(1, 12).map((n) => thread(n)), contacts: range(1, 12).map((n) => contact(n)) });
  try {
    for (const n of range(1, 10)) s.select(tid(n));
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    s.type("resposta pela metade para o cliente 1");
    s.select(tid(11));  // clique na sidebar
    check(s.h.out.tabs.openTabs.includes(tid(1)) && !s.h.out.tabs.openTabs.includes(tid(2)) && s.w.notices.length === 0, "Limite preserva a guia em uso com rascunho e fecha a menos usada sem rascunho (X5)");
    check(storedDrafts(s.storage)[tid(1)].text === "resposta pela metade para o cliente 1", "Rascunho da guia em uso continua salvo");
  } finally { s.h.unmount(); }
  // A menos usada TEM rascunho e as outras nao: fecha uma sem rascunho.
  const fresh = boot({ live: range(1, 11).map((n) => thread(n)), contacts: range(1, 11).map((n) => contact(n)) });
  try {
    fresh.select(tid(1)); fresh.type("rascunho esquecido na guia 1");
    for (const n of range(2, 11)) fresh.select(tid(n));
    check(fresh.h.out.tabs.openTabs.includes(tid(1)) && !fresh.h.out.tabs.openTabs.includes(tid(2)) && fresh.w.notices.length === 0, "Limite prefere fechar guia SEM rascunho, mesmo que a com rascunho seja a menos usada");
  } finally { fresh.h.unmount(); }
}

async function limitAllWithDrafts() {
  const s = boot({ live: range(1, 12).map((n) => thread(n)), contacts: range(1, 12).map((n) => contact(n)) });
  try {
    for (const n of range(1, 10)) s.select(tid(n));
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    s.type("resposta pela metade para o cliente 1");
    s.select(tid(11));
    for (const n of range(3, 11)) { s.h.out.tabs.activateTab(tid(n)); s.h.flush(); s.type(`rascunho ${n}`); }
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    s.select(tid(12));
    const tabs = s.h.out.tabs.openTabs;
    check(!tabs.includes(tid(3)) && tabs.includes(tid(1)) && tabs.includes(tid(12)), "Todas com rascunho: fecha a menos usada");
    check(s.lastNotice() === "Limite de 10 guias: Guia de Cliente 3 fechada (rascunho preservado).", "Aviso quando o limite fecha guia com rascunho");
    check(storedDrafts(s.storage)[tid(3)].text === "rascunho 3", "Rascunho da guia fechada pelo limite fica salvo");
    s.select(tid(3));
    check(s.h.out.draft === "rascunho 3", "Reabrir a conversa devolve o rascunho preservado");
  } finally { s.h.unmount(); }
}

async function draftsPerTab() {
  const s = boot({ live: [thread(1), thread(2, { channel_type: "coexistence" })], contacts: [contact(1), contact(2)] });
  try {
    s.select(tid(1));
    s.type("Olá, cliente 1");
    s.select(tid(2));
    check(s.h.out.draft === "", "Guia nova abre com composer vazio");
    check(s.h.out.tabs.tabInfo[1].channel === "Coex", "Chip Coex na guia do canal coexistence");
    s.type("Oi 2");
    s.select(tid(1));
    check(s.h.out.draft === "Olá, cliente 1", "Voltar a guia devolve o rascunho dela");
    s.select(tid(2));
    check(s.h.out.draft === "Oi 2", "Rascunho de cada guia preservado ao alternar");
    const saved = storedDrafts(s.storage);
    check(saved[tid(1)].text === "Olá, cliente 1" && saved[tid(1)].internal === false && typeof saved[tid(1)].at === "number" && saved[tid(2)].text === "Oi 2", "Rascunho gravado por uid com texto, modo e horario");
    s.h.out.setDraft(""); s.h.flush();  // envio normal: sendTextMessage chama setDraft("")
    check(s.h.out.draft === "" && !(tid(2) in storedDrafts(s.storage)) && storedDrafts(s.storage)[tid(1)], "Enviar limpa so o rascunho da guia enviada");
    s.select(tid(1));
    check(s.h.out.draft === "Olá, cliente 1", "Outra guia segue com o rascunho apos envio");
    const sendStartedHere = s.h.out.setDraft;  // render da guia 1: envio em voo
    s.select(tid(2));
    s.type("Texto novo da 2");
    sendStartedHere(""); s.h.flush();         // envio da guia 1 termina depois da troca
    check(s.h.out.draft === "Texto novo da 2", "Envio tardio nao apaga o texto da guia atual");
    s.select(tid(1));
    check(s.h.out.draft === "", "Envio tardio limpa o rascunho da guia de origem");
    s.type("rascunho antes da correcao");
    s.h.out.startCorrection("texto corrigido"); s.h.flush();
    check(s.h.out.draft === "texto corrigido" && storedDrafts(s.storage)[tid(1)].text === "rascunho antes da correcao", "Texto da correcao nao e gravado como rascunho");
    s.select(tid(2));
    check(s.h.out.draft === "Texto novo da 2", "Correcao cancelada pela troca nao apaga o rascunho da guia nova");
    s.select(tid(1));
    check(s.h.out.draft === "rascunho antes da correcao", "Voltar a guia: rascunho de antes da correcao; texto corrigido nunca volta");
    s.h.out.startCorrection("outra correcao"); s.h.flush();
    s.h.out.cancelCorrection(); s.h.flush();
    check(s.h.out.draft === "" && !(tid(1) in storedDrafts(s.storage)), "Correcao encerrada na propria guia limpa composer e rascunho");
    s.h.out.tabs.closeTab(tid(2)); s.h.flush();
    check(!(tid(2) in storedDrafts(s.storage)), "Fechar a guia descarta o rascunho dela");
  } finally { s.h.unmount(); }
}

// Item 2: rascunho volta com o modo do composer (nota interna nunca vira
// mensagem ao cliente ao voltar pra guia ou apos F5).
async function internalNoteDrafts() {
  const storage = makeStorage();
  const note = "NOTA INTERNA: cliente inadimplente, nao conceder desconto";
  const reply = "Bom dia! Seu pedido saiu para entrega.";
  let s = boot({ storage, live: [thread(1), thread(2)], contacts: [contact(1), contact(2)] });
  try {
    s.select(tid(1));
    s.mode(true);
    s.type(note);
    check(storedDrafts(storage)[tid(1)].text === note && storedDrafts(storage)[tid(1)].internal === true, "Rascunho de nota interna gravado com o modo");
    s.select(tid(2));
    check(s.h.out.internalMode === true && s.h.out.draft === "", "Guia sem rascunho mantem o modo atual (como antes das guias)");
    s.mode(false);
    s.type(reply);
    s.select(tid(1));
    check(s.h.out.draft === note && s.h.out.internalMode === true, "Voltar a guia da nota: texto E modo interno (Enter nao manda ao cliente)");
    s.select(tid(2));
    check(s.h.out.draft === reply && s.h.out.internalMode === false, "Guia com resposta ao cliente volta em modo normal");
    s.mode(true);
    check(storedDrafts(storage)[tid(2)].internal === true, "Ligar a nota interna com texto no composer muda o modo do rascunho");
    s.select(tid(1)); s.select(tid(2));
    check(s.h.out.internalMode === true, "Modo trocado com texto volta junto");
    s.mode(false);
    s.h.out.startCorrection("corrigindo"); s.h.flush();
    s.select(tid(1));
    check(storedDrafts(storage)[tid(2)].internal === false && storedDrafts(storage)[tid(2)].text === reply, "Correcao (que forca o modo normal) nao mexe no rascunho guardado");
  } finally { s.h.unmount(); }
  s = boot({ storage, live: [], contacts: [contact(1), contact(2)], docs: { [tid(1)]: raw(1), [tid(2)]: raw(2) } });
  try {
    await s.h.settle();
    check(s.h.out.selectedThreadId === null && same(s.h.out.tabs.openTabs, [tid(1), tid(2)]), "Apos F5 volta a faixa, sem abrir conversa");
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    check(s.h.out.draft === note && s.h.out.internalMode === true, "Apos F5 a nota volta no modo interno");
    s.select(tid(2));
    check(s.h.out.draft === reply && s.h.out.internalMode === false, "Apos F5 a resposta ao cliente volta em modo normal");
  } finally { s.h.unmount(); }
  const legacy = makeStorage();
  legacy.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(1), tid(2)]));
  legacy.setItem(STORAGE_DRAFTS("uid-op"), JSON.stringify({ [tid(1)]: "texto salvo sem o modo", [tid(2)]: { text: "objeto sem o modo", at: Date.now() } }));
  s = boot({ storage: legacy, live: [], contacts: [contact(1), contact(2)], docs: { [tid(1)]: raw(1), [tid(2)]: raw(2) } });
  try {
    await s.h.settle();
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    check(s.h.out.selectedThreadId === tid(1) && s.h.out.draft === "", "Rascunho salvo sem o modo (formato antigo) nao e restaurado");
    s.select(tid(2));
    check(s.h.out.draft === "", "Rascunho sem a marca de nota interna nao e restaurado");
  } finally { s.h.unmount(); }
}

async function persistAndRestore() {
  const storage = makeStorage();
  const contacts = range(1, 5).map((n) => contact(n));
  let s = boot({ storage, live: range(1, 3).map((n) => thread(n)), contacts });
  check(storage.map.size === 0, "Boot sem guias nao grava nada");
  s.select(tid(1)); s.select(tid(2)); s.select(tid(3));
  s.select(tid(2)); s.type("rascunho 2");
  check(storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2), tid(3)]), "Lista de guias gravada em castro_crm.tabs.<uid>");
  check(storage.getItem(STORAGE_ACTIVE("uid-op")) === null, "Guia ativa nao e gravada (a restauracao nao abre conversa)");
  s.h.unmount();

  // F5: janela ao vivo ainda vazia; thread 3 virou de outro operador (rules negam).
  s = boot({ storage, live: [], contacts, docs: { [tid(1)]: raw(1), [tid(2)]: raw(2, { unread_count: 2 }) }, denied: [tid(3)] });
  try {
    check(s.h.out.tabs.openTabs.length === 0 && storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2), tid(3)]), "Durante a validacao nada e mostrado nem apagado");
    await s.h.settle();
    check(same([...s.w.reads].sort(), [tid(1), tid(2), tid(3)].sort()), "Restauracao le cada thread salva (getSessionDoc)");
    check(same(s.h.out.tabs.openTabs, [tid(1), tid(2)]), "Guia sem permissao e descartada; as validas voltam na ordem");
    check(s.h.out.tabPins.has(tid(1)) && s.h.out.tabPins.has(tid(2)) && s.h.out.allConversations.length === 2, "Guias restauradas entram no merge pelas pins");
    check(s.h.out.selectedThreadId === null && s.h.out.draft === "", "Restauracao volta a FAIXA sem abrir conversa (sem mark-read sem a operadora ver)");
    check(s.tab(tid(2)).unread === 2, "Badge restaurado com o unread do doc");
    s.h.out.tabs.activateTab(tid(2)); s.h.flush();
    check(s.h.out.draft === "rascunho 2", "Clique na guia restaurada devolve o rascunho");
    check(same(s.listening(), [tid(1), tid(2)]), "Listeners so das guias validas");
    check(storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2)]), "Storage regravado sem a guia descartada");
    s.w.scopeGeneration.current += 1;
    s.h.out.tabs.resetTabs(); s.h.out.setSelectedThreadId(null);
    s.update({ enabled: false, storageUid: "", sessionUser: null });
    check(s.h.out.tabs.openTabs.length === 0 && s.listening().length === 0 && s.h.out.tabPins.size === 0, "Logout zera guias, pins e listeners");
    check(storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2)]) && storedDrafts(storage)[tid(2)].text === "rascunho 2", "Logout NAO apaga o storage do uid");
    s.update({ enabled: true, storageUid: "uid-op", sessionUser: { id: 5, firebase_uid: "uid-op", display_name: "Operadora", role: "operador" } });
    await s.h.settle();
    check(same(s.h.out.tabs.openTabs, [tid(1), tid(2)]) && s.h.out.selectedThreadId === null, "Novo login do mesmo uid restaura as guias (sem abrir nenhuma)");
  } finally { s.h.unmount(); }

  // Outro usuario no mesmo navegador (PC compartilhado): chaves separadas.
  s = boot({ storage, uid: "uid-outro", userId: 7, live: [thread(4, { assigned_to: 7, assigned_to_uid: "uid-outro" })], contacts, docs: { [tid(1)]: raw(1) } });
  try {
    await s.h.settle();
    check(s.h.out.tabs.openTabs.length === 0 && s.w.reads.length === 0, "Outro uid nao ve nem le as guias do anterior");
    s.select(tid(4));
    check(storage.getItem(STORAGE_TABS("uid-outro")) === JSON.stringify([tid(4)]) && storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2)]), "Cada uid grava a propria lista");
  } finally { s.h.unmount(); }

  // Inexistente descarta; falha transitoria mantem a guia (sem pin, "Carregando…").
  const storage2 = makeStorage();
  storage2.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(1), tid(2), tid(3), 42, tid(1)]));
  storage2.setItem(STORAGE_ACTIVE("uid-op"), tid(2));
  storage2.setItem(STORAGE_DRAFTS("uid-op"), JSON.stringify({ [tid(3)]: { text: "da thread apagada", internal: false, at: Date.now() }, [tid(9)]: { text: "sobra antiga", internal: false, at: 1 } }));
  s = boot({ storage: storage2, contacts, docs: { [tid(1)]: raw(1) }, transient: [tid(2)] });
  try {
    await s.h.settle();
    check(same(s.h.out.tabs.openTabs, [tid(1), tid(2)]), "Thread inexistente descartada; falha transitoria mantem a guia");
    check(s.h.out.tabs.tabInfo[1].conversation === null && s.h.out.tabs.tabInfo[1].name === "Carregando…", "Guia sem dados mostra Carregando…");
    check(s.h.out.selectedThreadId === null && storage2.getItem(STORAGE_ACTIVE("uid-op")) === null, "Nada selecionado e a chave antiga de guia ativa e apagada");
    check(same(storedDrafts(storage2), {}), "Restauracao limpa rascunho da guia descartada e sobra antiga de outra aba");
    s.emit(tid(2), raw(2));
    check(s.h.out.tabs.tabInfo[1].name === "Cliente 2" && s.h.out.tabPins.has(tid(2)), "Listener da guia entrega a thread depois");
  } finally { s.h.unmount(); }

  // Logout no meio da restauracao: nada do usuario anterior entra.
  const storage3 = makeStorage();
  storage3.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(1)]));
  s = boot({ storage: storage3, contacts, docs: { [tid(1)]: raw(1) } });
  try {
    s.w.scopeGeneration.current += 1;
    await s.h.settle();
    check(s.h.out.tabs.openTabs.length === 0 && s.listening().length === 0, "Restauracao em voo descartada apos logout/troca de conta");
  } finally { s.h.unmount(); }
}

// Item 5 (X4): duas abas do navegador com o mesmo uid.
async function twoBrowserTabs() {
  const storage = makeStorage();
  const b1 = boot({ storage, live: [thread(1), thread(3)], contacts: [contact(1), contact(3), contact(9)] });
  b1.select(tid(1)); b1.type("rascunho aba 1");
  const b2 = boot({ storage, live: [thread(9)], contacts: [contact(1), contact(9)], docs: { [tid(1)]: raw(1) } });
  try {
    await b2.h.settle();
    b2.select(tid(9)); b2.type("rascunho da aba 2 para o cliente 9");
    b1.type("rascunho aba 1 (editado)");
    const drafts = storedDrafts(storage);
    check(drafts[tid(9)]?.text === "rascunho da aba 2 para o cliente 9" && drafts[tid(1)]?.text === "rascunho aba 1 (editado)", "Duas abas do navegador: cada uma grava so o proprio rascunho (X4)");
    b1.h.out.tabs.closeTab(tid(1)); b1.h.flush();
    check(!(tid(1) in storedDrafts(storage)) && storedDrafts(storage)[tid(9)], "Fechar guia numa aba remove so o rascunho dela");
  } finally { b2.h.unmount(); b1.h.unmount(); }
}

async function autoClose() {
  const contacts = [contact(1), contact(2, { assigned_to: null }), contact(3), contact(4), contact(5), contact(6, { assigned_to: 5 }), contact(7)];
  const live = [thread(1), thread(2, { assigned_to: null, assigned_to_uid: "" }), thread(3), thread(4, { attendance_status: "fechado_manual" }), thread(6, { assigned_to: 9, assigned_to_uid: "uid-fulano" })];
  const s = boot({ live, contacts });
  try {
    s.select(tid(1)); s.select(tid(2)); s.select(tid(3));
    s.setLive(2, { assigned_to: 9, assigned_to_uid: "uid-fulano" });
    check(!s.h.out.tabs.openTabs.includes(tid(2)) && s.h.out.selectedThreadId === tid(3), "Pool assumida por outro operador fecha a guia (nao ativa: selecao fica)");
    check(s.lastNotice() === "Guia de Cliente 2 fechada: atendimento assumido por Fulano.", "Aviso de guia fechada por mudanca de dono");
    // Transferencia move thread e lead; enquanto so a thread mudou, o Dono do
    // LEAD (eu) segue com a guia — os dois listeners chegam em tempos diferentes.
    s.setLive(1, { assigned_to: 9, assigned_to_uid: "uid-fulano" });
    check(s.h.out.tabs.openTabs.includes(tid(1)), "Thread de outro mas lead ainda meu: guia fica");
    s.update({ contacts: new Map([...contacts.map((item) => [item.id, item]), [101, contact(1, { assigned_to: 9 })]]) });
    check(!s.h.out.tabs.openTabs.includes(tid(1)) && s.lastNotice() === "Guia de Cliente 1 fechada: atendimento transferido para Fulano.", "Minha thread transferida (thread + lead) fecha a guia");
    const noticesBefore = s.w.notices.length;
    s.setLive(3, { attendance_status: "fechado_inatividade" });
    check(s.h.out.tabs.openTabs.includes(tid(3)) && s.h.out.selectedThreadId === tid(3) && s.w.notices.length === noticesBefore, "Guia ATIVA encerrada fica aberta: o chat mostra o encerramento e o Reabrir (C1/D)");
    s.addLive(7);
    s.select(tid(7)); s.type("resposta pela metade do 7");
    s.select(tid(3));
    s.setLive(7, { attendance_status: "fechado_manual" });
    check(!s.h.out.tabs.openTabs.includes(tid(7)) && s.h.out.selectedThreadId === tid(3), "Guia NAO ativa encerrada fecha (selecao fica)");
    check(s.lastNotice() === "Guia de Cliente 7 fechada: atendimento encerrado (rascunho preservado).", "Aviso de encerramento diz que o rascunho ficou salvo (C2)");
    check(storedDrafts(s.storage)[tid(7)].text === "resposta pela metade do 7", "Rascunho da guia fechada automaticamente fica no storage");
    s.select(tid(7));
    check(s.h.out.tabs.openTabs.includes(tid(7)) && s.h.out.draft === "resposta pela metade do 7", "Reabrir a conversa recupera o rascunho preservado");
    s.select(tid(4));
    check(s.h.out.tabs.openTabs.includes(tid(4)), "Abrir thread JA fechada (janela ao vivo) mantem a guia");
    s.select(tid(6));
    check(s.h.out.tabs.openTabs.includes(tid(6)), "Dono do lead mantem a guia de thread no numero de outro operador");
    s.update({ contacts: new Map([...contacts.map((item) => [item.id, item]), [101, contact(1, { assigned_to: 9 })], [106, contact(6, { assigned_to: 9 })]]) });
    check(!s.h.out.tabs.openTabs.includes(tid(6)), "Perdeu o lead e a thread e de outro: guia fecha");
    s.addLive(5);
    s.select(tid(5));
    s.select(tid(4));
    s.deny(tid(5));
    check(!s.h.out.tabs.openTabs.includes(tid(5)) && s.lastNotice() === "Guia de Cliente 5 fechada: atendimento assumido por outro operador.", "permission-denied no listener fecha a guia");
    check(!s.listening().includes(tid(5)), "Listener da guia fechada encerrado");
    s.emit(tid(4), null);
    check(!s.h.out.tabs.openTabs.includes(tid(4)) && s.h.out.selectedThreadId === null, "Doc apagado (confirmado pelo servidor) fecha a guia");
  } finally { s.h.unmount(); }

  const admin = boot({ canSeeAll: true, uid: "uid-admin", userId: 1, live: [thread(1, { assigned_to: null, assigned_to_uid: "" }), thread(2)], contacts: [contact(1, { assigned_to: null }), contact(2)] });
  try {
    admin.select(tid(1)); admin.select(tid(2));
    admin.setLive(1, { assigned_to: 9, assigned_to_uid: "uid-fulano" });
    check(admin.h.out.tabs.openTabs.includes(tid(1)), "Admin/supervisor: pool assumida por outro NAO fecha a guia");
    admin.setLive(1, { assigned_to: 9, assigned_to_uid: "uid-fulano", attendance_status: "fechado_manual" });
    check(!admin.h.out.tabs.openTabs.includes(tid(1)) && admin.h.out.selectedThreadId === tid(2), "Admin/supervisor: fecha so por attendance_status fechado_*");
    admin.update({ live: [] });
    admin.emit(tid(2), raw(2, { unread_count: 7 }));
    check(admin.h.out.tabs.tabInfo[0].unread === 7 && admin.h.out.tabPins.get(tid(2)).unread_count === 7, "Listener mantem a pin fresca fora da janela ao vivo");
    admin.emit(tid(2), null, true);
    check(admin.h.out.tabs.openTabs.includes(tid(2)), "Doc ausente so no cache (offline) nao fecha a guia");
  } finally { admin.h.unmount(); }
}

// Itens 1 e 4 (X1, X6): base do fechamento automatico so com dado confiavel;
// copia estatica do picker nao sombreia a pin fresca da guia.
async function pickerAndStaticCopies() {
  const closedDoc = raw(7, { attendance_status: "fechado_inatividade", last_message_at: "2026-01-10T10:00:00.000Z" });
  const s = boot({ live: [thread(1)], contacts: [contact(1), contact(7)] });
  try {
    s.select(tid(1));
    check(optimistic(7).attendance_status === "aberto", "Copia otimista do picker vem 'aberto' (sem attendance_status)");
    s.setExtra([optimistic(7)]);
    s.select(tid(7));
    check(s.h.out.selectedThreadId === tid(7) && s.h.out.tabs.openTabs.includes(tid(7)), "Picker abriu a thread 7 (guia criada e ativa)");
    s.setExtra([normalization.normalizeConversation(closedDoc, tid(7))]);  // listener da thread selecionada (provider)
    s.emit(tid(7), closedDoc);                                              // 1a leitura do servidor na guia
    check(s.h.out.tabs.openTabs.includes(tid(7)) && s.h.out.selectedThreadId === tid(7) && s.w.notices.length === 0, "Picker em atendimento JA encerrado: guia fica, sem aviso falso (X1)");
    s.select(tid(1)); s.select(tid(7));
    check(s.h.out.tabs.openTabs.includes(tid(7)) && s.h.out.selectedThreadId === tid(7), "Alternar de guia nao fecha a thread encerrada");
    s.emit(tid(7), raw(7, { last_message_at: "2026-01-10T10:00:00.000Z" }));  // reaberta
    s.select(tid(1));
    s.emit(tid(7), closedDoc);
    check(!s.h.out.tabs.openTabs.includes(tid(7)) && s.h.out.selectedThreadId === tid(1) && s.lastNotice() === "Guia de Cliente 7 fechada: atendimento encerrado.", "Reaberta e encerrada de novo (visto pelo servidor) fora da guia ativa: fecha");
  } finally { s.h.unmount(); }

  // X1 sem a protecao da guia ativa: a operadora abre pelo picker e troca de
  // guia ANTES do doc real chegar — o encerramento antigo nao pode virar
  // "mudanca" (fecharia a guia com aviso falso).
  const u = boot({ live: [thread(1)], contacts: [contact(1), contact(7)] });
  try {
    u.select(tid(1));
    u.setExtra([optimistic(7)]);
    u.select(tid(7));
    u.select(tid(1));
    u.emit(tid(7), closedDoc);
    check(u.h.out.tabs.openTabs.includes(tid(7)) && u.w.notices.length === 0, "Picker + troca de guia antes do doc real: thread ja encerrada nao fecha a guia (X1)");
  } finally { u.h.unmount(); }

  const openDoc = raw(7, { last_message_at: "2026-01-10T10:00:00.000Z" });
  const t = boot({ live: [thread(1)], contacts: [contact(1), contact(7)] });
  try {
    t.setExtra([normalization.normalizeConversation(openDoc, tid(7))]);
    t.select(tid(7));
    t.emit(tid(7), openDoc);
    t.select(tid(1));  // 7 deixa de ser a selecionada: a copia fixada (extra) congela
    t.emit(tid(7), { ...openDoc, unread_count: 4 });
    check(t.tab(tid(7)).unread === 4, "Pin fresca (listener) vence a copia estatica no merge: badge ao vivo (X6)");
    t.emit(tid(7), { ...openDoc, attendance_status: "fechado_inatividade" });
    check(!t.h.out.tabs.openTabs.includes(tid(7)) && t.h.out.selectedThreadId === tid(1), "Guia NAO selecionada fecha quando o cron encerra, sem esperar o clique (X6)");
  } finally { t.h.unmount(); }
}

// Item 7 (X7): contato indisponivel (lead de outra operadora) nunca vira
// rotulo com telefone e, pra quem nao ve tudo, fecha a guia.
async function unavailableContact() {
  const storage = makeStorage();
  storage.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(8)]));
  const s = boot({ storage, live: [], contacts: [], docs: { [tid(8)]: raw(8, { assigned_to: null, assigned_to_uid: "", display_name: "Lead Alheio" }) } });
  try {
    await s.h.settle();
    check(s.h.out.tabs.openTabs.includes(tid(8)) && s.tab(tid(8)).name === "Carregando…", "Thread de pool legivel volta enquanto o contato hidrata");
    s.update({ unavailable: new Set([108]) });  // GET /api/wa/contact/108 -> 403
    check(!s.h.out.tabs.openTabs.includes(tid(8)), "Contato indisponivel fecha a guia do operador comum (X7)");
    check(s.lastNotice() === "Guia fechada: contato indisponível.", "Aviso sem telefone nem nome do lead alheio");
    check(!s.w.notices.join(" ").includes(waId(8)) && !s.w.notices.join(" ").includes("Lead Alheio"), "Nada do lead alheio vaza no aviso");
  } finally { s.h.unmount(); }
  const a = boot({ canSeeAll: true, uid: "uid-admin", userId: 1, live: [thread(8, { assigned_to: null, assigned_to_uid: "", display_name: "Lead Alheio" })], contacts: [] });
  try {
    a.select(tid(8));
    a.update({ unavailable: new Set([108]) });
    check(a.h.out.tabs.openTabs.includes(tid(8)) && a.tab(tid(8)).name === "Contato indisponível", "Admin: guia fica, rotulo 'Contato indisponível' (nunca o telefone)");
  } finally { a.h.unmount(); }
}

// Item 3 (X2): sem snapshot (polling) nao ha guias.
async function pollingDisablesTabs() {
  const s = boot({ snapshotMode: false, live: [thread(1), thread(2, { unread_count: 3 })], contacts: [contact(1), contact(2)] });
  try {
    s.select(tid(2));
    check(s.h.out.tabs.openTabs.length === 0 && s.h.out.tabPins.size === 0 && s.listening().length === 0 && s.storage.map.size === 0, "Polling: sem guias, pins, listeners ou storage (X2)");
    s.setLive(2, { unread_count: 0 });
    s.update({ live: [thread(1)] });  // colega assumiu: o polling nao devolve mais a thread 2
    check(s.h.out.selectedThreadId === null && !s.h.out.allConversations.some((item) => item.id === tid(2)), "Polling: thread que saiu do escopo fecha como antes (nenhuma pin congelada)");
    check(fakeWindow.keydown.size === 0, "Polling: sem atalho de guias");
  } finally { s.h.unmount(); }
}

async function keyboard() {
  const s = boot({ live: range(1, 3).map((n) => thread(n)), contacts: range(1, 3).map((n) => contact(n)) });
  try {
    s.select(tid(1)); s.select(tid(2)); s.select(tid(3));
    s.h.out.tabs.activateTab(tid(1)); s.h.flush();
    let event = press("ArrowDown"); s.h.flush();
    check(s.h.out.selectedThreadId === tid(2) && event.defaultPrevented, "Ctrl+Alt+ArrowDown vai pra proxima guia");
    press("ArrowDown"); s.h.flush(); press("ArrowDown"); s.h.flush();
    check(s.h.out.selectedThreadId === tid(1), "Ctrl+Alt+ArrowDown e circular");
    press("ArrowUp"); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3), "Ctrl+Alt+ArrowUp volta (circular)");
    event = press("ArrowDown", { ctrl: false }); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3) && !event.defaultPrevented, "Alt+Seta sozinho (paragrafo no macOS) nao troca de guia (H)");
    event = press("ArrowDown", { alt: false }); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3) && !event.defaultPrevented, "Ctrl+Seta sem Alt nao troca de guia");
    event = press("ArrowDown", { tag: "SELECT" }); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3) && !event.defaultPrevented, "Atalho num select fica com o navegador");
    press("ArrowDown", { handled: true }); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3), "Tecla ja tratada por outro handler nao troca de guia");
    s.update({ suggestionsOpen: true });
    event = press("ArrowDown"); s.h.flush();
    check(s.h.out.selectedThreadId === tid(3) && !event.defaultPrevented, "Lista de mensagens rapidas aberta: as setas sao dela (H)");
    s.update({ suggestionsOpen: false });
    s.h.out.setSelectedThreadId(null); s.h.flush();
    press("ArrowDown"); s.h.flush();
    check(s.h.out.selectedThreadId === tid(1), "Sem guia ativa, Ctrl+Alt+ArrowDown abre a primeira");
  } finally { s.h.unmount(); }
  check(fakeWindow.keydown.size === 0, "Desmontar remove o atalho de teclado");
}

async function readOnlyAndComponent() {
  const s = boot({ enabled: false, live: [thread(1)], contacts: [contact(1)] });
  try {
    s.select(tid(1));
    check(s.h.out.tabs.openTabs.length === 0 && s.listening().length === 0 && s.h.out.tabPins.size === 0, "Ver como (readOnly): selecionar nao abre guia nem listener");
    s.type("nao grava");
    check(s.h.out.draft === "nao grava" && s.storage.map.size === 0, "Ver como: composer legado e nada no storage");
    check(fakeWindow.keydown.size === 0, "Ver como: sem atalho de teclado");
  } finally { s.h.unmount(); }

  const calls = [];
  const info = (n, extra = {}) => ({ id: tid(n), conversation: thread(n), contact: contact(n), unread: 0, isActive: false, name: `Cliente ${n}`, channel: "Standard", hasDraft: false, ...extra });
  const ctx = (tabInfo, readOnly = false) => ({
    readOnly, tabInfo,
    activateTab: (id) => calls.push(["activate", id]), closeTab: (id) => calls.push(["close", id]), closeAllTabs: () => calls.push(["closeAll"]),
  });
  // Cada render monta uma instancia nova do componente (hooks simulados, sem DOM).
  const mounted = [];
  const render = (value) => {
    crmContext = value;
    const ui = createHarness(() => ChatTabs());
    mounted.push(ui);
    return ui.flush();
  };
  const nodes = (root) => {
    const out = [];
    const walk = (node) => {
      if (Array.isArray(node)) { node.forEach(walk); return; }
      if (!node || typeof node !== "object") return;
      out.push(node);
      walk(node.props?.children);
    };
    walk(root);
    return out;
  };
  check(render(ctx([info(1, { isActive: true })], true)) === null, "readOnly nao renderiza a faixa");
  check(render(ctx([])) === null, "Sem guias, sem faixa");
  const tree = render(ctx([info(1, { isActive: true, unread: 2 }), info(2, { unread: 3, channel: "Coex" }), info(3, { unread: 150 })]));
  const all = nodes(tree);
  const tablist = all.find((node) => node.props?.role === "tablist");
  check(tablist && tablist.props.className === "chat-tabs" && tablist.props["aria-label"], "Faixa .chat-tabs com role=tablist");
  const tabs = all.filter((node) => node.props?.role === "tab");
  check(tabs.length === 3 && same(tabs.map((tab) => tab.props["aria-selected"]), [true, false, false]), "Cada guia role=tab com aria-selected so na ativa");
  const wrappers = all.filter((node) => typeof node.props?.className === "string" && (node.props.className === "chat-tab" || node.props.className.startsWith("chat-tab ")));
  check(wrappers.length === 3 && wrappers[0].props.className.includes("active") && !wrappers[0].props.className.includes("unread"), "Guia ativa destacada e sem piscar mesmo com nao lidas");
  check(wrappers[1].props.className.includes("unread") && wrappers[2].props.className.includes("unread"), "Guia nao ativa com nao lidas pisca (classe unread)");
  const badges = all.filter((node) => node.type === "b" && String(node.props.className).includes("badge"));
  check(same(badges.map((badge) => badge.props.children), [2, 3, "99+"]), "Badge de nao lidas (99+ acima de 99)");
  check(tabs[1].props["aria-label"] === "Cliente 2, Coex, 3 não lidas", "aria-label com canal e nao lidas");
  check(tabs[0].props.title.includes("Ctrl+Alt+↑/↓"), "Tooltip da guia cita o atalho novo (H)");
  const chips = all.filter((node) => String(node.props?.className || "").startsWith("chat-tab__channel"));
  check(same(chips.map((chip) => chip.props.children), ["Std", "Coex", "Std"]) && chips[0].props.title.startsWith("Standard"), "Chip curto do canal (nome completo no title)");
  // G: roving tabindex, X fora da navegacao, aria-controls, Delete fecha.
  check(same(tabs.map((tab) => tab.props.tabIndex), [0, -1, -1]), "Roving tabindex: so a guia ativa entra no Tab (G)");
  check(tabs.every((tab) => tab.props["aria-controls"] === "chat-tabpanel") && same(tabs.map((tab) => tab.props.id), [1, 2, 3].map((n) => `chat-tab-${tid(n)}`)), "Guias apontam pra regiao do chat (aria-controls) com id proprio");
  const closers = all.filter((node) => String(node.props?.["aria-label"] || "").startsWith("Fechar guia"));
  check(closers.length === 3 && closers[1].props["aria-label"] === "Fechar guia de Cliente 2" && closers.every((x) => x.props.tabIndex === -1), "X com 'Fechar guia de {nome}' e fora da ordem do Tab (G)");
  tabs[1].props.onClick(); closers[2].props.onClick();
  wrappers[0].props.onAuxClick({ button: 1, preventDefault() {} });
  const del = { key: "Delete", defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  tabs[1].props.onKeyDown(del);
  const right = { key: "ArrowRight", defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  tabs[0].props.onKeyDown(right);
  check(del.defaultPrevented && right.defaultPrevented, "Delete fecha a guia focada; setas andam na faixa (G)");
  let closeAll = all.find((node) => node.type === "button" && node.props.children === "Fechar todas");
  check(closeAll, "Fechar todas aparece com 2+ guias");
  fakeWindow.confirms.length = 0;
  closeAll.props.onClick();
  check(same(calls, [["activate", tid(2)], ["close", tid(3)], ["close", tid(1)], ["close", tid(2)], ["closeAll"]]) && fakeWindow.confirms.length === 0, "Clique ativa, X/meio/Delete fecham; Fechar todas sem rascunho nao pergunta");
  const withDraft = nodes(render(ctx([info(1, { isActive: true }), info(2, { hasDraft: true })])));
  closeAll = withDraft.find((node) => node.type === "button" && node.props.children === "Fechar todas");
  calls.length = 0;
  fakeWindow.confirmAnswer = false;
  closeAll.props.onClick();
  check(calls.length === 0 && fakeWindow.confirms.length === 1, "Fechar todas com rascunho pede confirmacao; cancelar nao fecha (C3)");
  fakeWindow.confirmAnswer = true;
  closeAll.props.onClick();
  check(same(calls, [["closeAll"]]), "Confirmando, fecha todas");
  const noActive = nodes(render(ctx([info(1), info(2)]))).filter((node) => node.props?.role === "tab");
  check(same(noActive.map((tab) => tab.props.tabIndex), [0, -1]), "Sem guia ativa, o Tab entra pela primeira");
  const single = nodes(render(ctx([info(1, { isActive: true })])));
  check(!single.some((node) => node.props?.children === "Fechar todas"), "Fechar todas some com uma guia so");
  for (const ui of mounted) ui.unmount();
}

// Item E + I: restauracao descarta atendimento ja encerrado (aviso agregado)
// e id adulterado no storage (sem tela branca).
async function restoreClosedAndTampered() {
  const storage = makeStorage();
  storage.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(1), "a/b", "", "1__abc", tid(2), tid(3), "../x"]));
  storage.setItem(STORAGE_DRAFTS("uid-op"), JSON.stringify({ [tid(2)]: { text: "rascunho do encerrado", internal: false, at: Date.now() } }));
  const s = boot({ storage, contacts: [contact(1), contact(2), contact(3)], docs: { [tid(1)]: raw(1), [tid(2)]: raw(2, { attendance_status: "fechado_inatividade" }), [tid(3)]: raw(3, { attendance_status: "fechado_manual" }) } });
  try {
    await s.h.settle();
    check(same(s.h.out.tabs.openTabs, [tid(1)]), "Restauracao descarta atendimento encerrado (E) e id adulterado (I)");
    check(same([...s.w.reads].sort(), [tid(1), tid(2), tid(3)].sort()), "Id adulterado nem vira leitura no Firestore");
    check(s.lastNotice() === "2 guias de atendimentos encerrados não foram restauradas.", "Aviso agregado das guias encerradas");
    check(storedDrafts(storage)[tid(2)]?.text === "rascunho do encerrado", "Rascunho de atendimento encerrado fica salvo (volta se reabrir)");
    s.h.out.setSelectedThreadId("a/b"); s.h.flush();
    check(same(s.h.out.tabs.openTabs, [tid(1)]) && s.listening().every((id) => id !== "a/b"), "Id invalido que chegue pela selecao derruba so a guia (I)");
  } finally { s.h.unmount(); }
  const storage2 = makeStorage();
  storage2.setItem(STORAGE_TABS("uid-op"), JSON.stringify([tid(4)]));
  const t = boot({ storage: storage2, contacts: [contact(4)], docs: { [tid(4)]: raw(4, { attendance_status: "fechado_cliente" }) } });
  try {
    await t.h.settle();
    check(t.h.out.tabs.openTabs.length === 0 && t.lastNotice() === "1 guia de atendimento encerrado não foi restaurada.", "Aviso no singular");
  } finally { t.h.unmount(); }
}

// Item J: Sair pelo botao apaga os rascunhos salvos do uid; a lista fica.
async function explicitLogoutClearsDrafts() {
  const storage = makeStorage();
  const s = boot({ storage, live: [thread(1), thread(2)], contacts: [contact(1), contact(2)] });
  try {
    s.select(tid(1)); s.type("rascunho com dado de paciente");
    s.select(tid(2)); s.type("outro rascunho");
    s.h.out.tabs.clearSavedDrafts(); s.h.flush();
    check(storage.getItem(STORAGE_DRAFTS("uid-op")) === null && storage.getItem(STORAGE_TABS("uid-op")) === JSON.stringify([tid(1), tid(2)]), "Sair pelo botao apaga os rascunhos e mantem a lista de guias (J)");
  } finally { s.h.unmount(); }
  const t = boot({ storage, contacts: [contact(1), contact(2)], docs: { [tid(1)]: raw(1), [tid(2)]: raw(2) } });
  try {
    await t.h.settle();
    t.h.out.tabs.activateTab(tid(1)); t.h.flush();
    check(same(t.h.out.tabs.openTabs, [tid(1), tid(2)]) && t.h.out.draft === "", "Proximo login: as guias voltam, sem rascunho");
  } finally { t.h.unmount(); }
}

// --- Fiacao no codigo real (AST/texto) ----------------------------------------
function wiring() {
  const parse = (relative) => ts.createSourceFile(relative, readFileSync(new URL(relative, srcRoot), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const app = parse("App.tsx");
  const chatPanel = app.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === "ChatPanel");
  check(chatPanel, "ChatPanel existe");
  let main = null;
  const visit = (node) => {
    if (!main && ts.isJsxElement(node) && node.openingElement.tagName.getText(app) === "main"
      && node.openingElement.attributes.properties.some((attr) => ts.isJsxAttribute(attr) && attr.initializer?.getText(app) === '"panel chat-panel"')) main = node;
    ts.forEachChild(node, visit);
  };
  visit(chatPanel);
  const firstChild = main?.children.find((child) => !(ts.isJsxText(child) && !child.getText(app).trim()) && !(ts.isJsxExpression(child) && !child.expression));
  check(firstChild && ts.isJsxSelfClosingElement(firstChild) && firstChild.tagName.getText(app) === "ChatTabs", "ChatTabs e o primeiro item do .chat-panel (antes de avisos e cabecalho)");

  const context = readFileSync(new URL("context/CrmContext.tsx", srcRoot), "utf8");
  const merge = context.slice(context.indexOf("const allConversations = useMemo("), context.indexOf("const selectedConversation = useMemo("));
  const at = (text) => merge.indexOf(text);
  check(at("extraConversations.forEach") >= 0 && at("extraConversations.forEach") < at("pagedConversations.forEach")
    && at("pagedConversations.forEach") < at("tabPins.forEach")
    && at("tabPins.forEach") < at("conversations.forEach((c) => map.set(c.id, c));        // ao vivo"), "Merge: ao vivo > guias > paginadas > fixadas (pin fresca vence copia estatica)");
  check(/\}, \[conversations, extraConversations, pagedConversations, tabPins\]\);/.test(merge), "Merge depende de tabPins");
  const markRead = context.slice(context.indexOf("function applyConversationReadLocally("), context.indexOf("function buildContactSnapshotTargets("));
  check(markRead.includes("setTabPins(markRead);"), "Mark-read otimista zera tambem a pin da guia");
  const correction = context.search(/setCorrectionTarget\(null\);\r?\n\s*setDraft\(""\);\r?\n\s*\}\r?\n\s*setReplyTarget\(null\);/);
  const hookCall = context.indexOf("const chatTabs = useChatTabs(");
  check(correction > 0 && hookCall > correction, "useChatTabs e chamado DEPOIS do effect de correcao (ordem da troca de rascunho)");
  check(context.indexOf("const [internalMode, setInternalMode] = useState(false);") > 0 && context.indexOf("const [internalMode, setInternalMode] = useState(false);") < hookCall, "Modo interno declarado antes das guias");
  const hookArgs = context.slice(hookCall, context.indexOf("});", hookCall));
  check(/enabled: !readOnly && !!sessionUser && !!snapshotMode,/.test(hookArgs), "Guias so com snapshot e fora do Ver como");
  check(/liveConversations: conversations,/.test(hookArgs) && /internalMode,\s*setInternalMode,\s*correctionTargetRef,/.test(hookArgs), "Hook recebe camada ao vivo, modo interno e correcao");
  check(/suggestionsOpen: quickSuggestions\.length > 0,/.test(hookArgs), "Hook sabe quando a lista de mensagens rapidas esta aberta (H)");
  const logoutFn = context.slice(context.indexOf("async function logout()"), context.indexOf("function buildSendTarget()"));
  const clearAt = logoutFn.indexOf("chatTabs.clearSavedDrafts();");
  check(clearAt > logoutFn.indexOf("endImpersonation(true)") && clearAt < logoutFn.indexOf("await signOut(bundle.auth)"), "Botao Sair apaga os rascunhos salvos antes do signOut (J)");
  const appText = readFileSync(new URL("App.tsx", srcRoot), "utf8");
  check(/<div className="chat-tabpanel" id=\{CHAT_TABPANEL_ID\} role=\{tabsShown \? "tabpanel" : undefined\}/.test(appText), "Chat e a regiao tabpanel das guias (G)");
  const reset = context.slice(context.indexOf("function resetUserScopedState()"), context.indexOf("const endImpersonation = useCallback("));
  check(reset.includes("chatTabs.resetTabs();") && reset.includes("setDraftState(\"\");") && !reset.includes("setDraft(\"\")"), "Logout/troca de conta zera as guias e o composer cru");
  check(!/localStorage\.(removeItem|clear|setItem)\(|\.removeItem\(/.test(reset), "Logout nao apaga o storage das guias");
  check(/openTabs: chatTabs\.openTabs, tabInfo: chatTabs\.tabInfo, activateTab: chatTabs\.activateTab, closeTab: chatTabs\.closeTab, closeAllTabs: chatTabs\.closeAllTabs/.test(context), "Contexto expoe openTabs, tabInfo, activateTab, closeTab, closeAllTabs");

  const css = readFileSync(new URL("styles.css", srcRoot), "utf8");
  check(/\.chat-tabs \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto;[^}]*scrollbar-width: thin;/s.test(css), "CSS .chat-tabs: nowrap, overflow-x auto e scrollbar fina");
  check(css.includes("@keyframes chat-tab-blink") && /\.chat-tab\.unread \{[^}]*animation: chat-tab-blink 1s ease-in-out infinite;/.test(css), "CSS: guia nao lida pisca (1 s, ease-in-out, infinito)");
  check(/\.chat-tab\.active \{[^}]*var\(--accent\)/.test(css) && /prefers-reduced-motion: reduce\) \{ \.chat-tab\.unread/.test(css), "CSS: ativa destacada com --accent e sem animacao em reduced-motion");
  const rootBlock = css.slice(css.indexOf(":root {"), css.indexOf("}", css.indexOf(":root {")));
  const darkBlock = css.slice(css.indexOf(":root.dark {"), css.indexOf("}", css.indexOf(":root.dark {")));
  check(/--tab-blink-bg:/.test(rootBlock) && /--tab-blink-bg:/.test(darkBlock) && /--tab-active-bg:/.test(rootBlock) && /--tab-active-bg:/.test(darkBlock), "CSS: tokens da guia por tema (claro e escuro) (F)");
  check(/@keyframes chat-tab-blink \{[^}]*\}[^}]*var\(--tab-blink-bg\)/.test(css) && /\.chat-tab\.active \{[^}]*var\(--tab-active-bg\)/.test(css), "CSS: piscar e ativa usam os tokens do tema (F)");
  check(/prefers-reduced-motion: reduce\) \{ \.chat-tab\.unread \{ animation: none; border-style: dashed; \} \}/.test(css), "CSS: sem animacao, nao lida vira borda tracejada (mais discreta que a ativa) (F)");
  check(/\.chat-tab \{[^}]*min-width: 7\.5rem;[^}]*container-type: inline-size;/.test(css) && /\.chat-tabs \{[^}]*flex: 1 1 0;[^}]*\n\s+width: 0;/.test(css), "CSS: guias encolhem ate o minimo e a faixa nao empurra o painel (A)");
  check(/\.chat-tab__close \{[^}]*width: 24px;[^}]*height: 24px;/.test(css), "CSS: X com area minima de 24x24 (G)");
}

const scenarios = [
  openLimitAndNeighbor, limitLeastUsed, limitAllWithDrafts, draftsPerTab, internalNoteDrafts, persistAndRestore, twoBrowserTabs,
  autoClose, pickerAndStaticCopies, unavailableContact, pollingDisablesTabs, restoreClosedAndTampered, explicitLogoutClearsDrafts,
  keyboard, readOnlyAndComponent,
];
try {
  for (const scenario of scenarios) await scenario();
  wiring();
  console.log(`Guias de conversa: ${checks} verificacoes ok (${scenarios.length} cenarios + fiacao; hooks/Firestore/localStorage simulados; sem rede).`);
} catch (error) {
  console.error(`FALHA apos ${checks} verificacoes: ${error.message}`);
  if (error.stack) console.error(error.stack.split("\n").slice(1, 4).join("\n"));
  process.exit(1);
}
