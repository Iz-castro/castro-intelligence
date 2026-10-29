import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { Auth } from "firebase/auth";
import { doc as firestoreDoc, type Firestore } from "firebase/firestore";

import { getSessionDoc, watchSessionDocument } from "../firebase";
import type { Contact, Conversation, Operator, SessionUser } from "../types";
import { normalizeConversation } from "../utils/normalization";

// ---------------------------------------------------------------------------
// Guias de conversa (PO 2026-10-28)
// ---------------------------------------------------------------------------
// Cada conversa aberta vira uma guia acima do chat, como as guias do
// navegador. Motivo: a operadora abria varias ABAS do navegador pra nao perder
// o cliente e a resposta pela metade — cada aba multiplica as leituras do
// Firestore e disputa o cache persistente (lista travada em "Carregando").
// Com as guias ela fica numa aba so.
//
// O que vive aqui:
// - lista de guias (ids das threads, max 10; o limite fecha a menos usada);
// - rascunho por guia, com o modo do composer (nota interna ou nao): o
//   composer e um so; trocar de guia guarda o texto da anterior e devolve o
//   da nova, no modo em que foi escrito;
// - persistencia por uid no localStorage (F5/fechar o navegador) e
//   restauracao no login: volta a FAIXA, validada no Firestore, sem abrir
//   conversa nenhuma (abrir marcaria como lida sem a operadora ver);
// - 1 listener por guia (doc da thread): badge/dono/status ao vivo mesmo fora
//   da janela top-50, e fechamento automatico quando o atendimento muda de dono
//   ou e encerrado (encerrado: so guia nao ativa);
// - atalho Ctrl+Alt+Seta cima/baixo (Ctrl+Tab e do navegador; Alt+Seta e
//   navegacao de paragrafo no macOS).
// A copia fixada de cada guia (tabPins) e estado do provider porque entra no
// merge de allConversations (abaixo so da camada ao vivo); aqui so se escreve
// nela. So com snapshot: sem listener (polling) a pin congelaria. Desligado na
// aba de Ver como (readOnly): sem faixa, sem storage, sem listener.

export const MAX_CHAT_TABS = 10;
const TABS_STORAGE_KEY = "castro_crm.tabs";
// Guia ativa nao e mais restaurada (abrir sozinha marcava como lida): a chave
// da versao anterior so e apagada no login.
const LEGACY_ACTIVE_TAB_KEY = "castro_crm.active_tab";
const DRAFTS_STORAGE_KEY = "castro_crm.drafts";
const LOADING_TAB_NAME = "Carregando…";
const UNAVAILABLE_TAB_NAME = "Contato indisponível";
// Rascunho salvo fora de qualquer lista (guia fechada automaticamente, ou de
// outra aba do navegador ja fechada) vale 7 dias e e limpo no login; reabrir a
// conversa antes disso devolve o texto. Sair pelo botao apaga todos (LGPD).
const ORPHAN_DRAFT_MS = 7 * 24 * 60 * 60 * 1000;
// Id de thread e deterministico: "{channel_id}__{wa_id}". Storage adulterado
// (id com "/", vazio...) nao pode virar referencia do Firestore.
const VALID_TAB_ID = /^\d+__\d+$/;

export type ChatTabInfo = {
  id: string;
  // null enquanto a thread nao chegou (restauracao/listener em voo).
  conversation: Conversation | null;
  contact: Contact | null;
  unread: number;
  isActive: boolean;
  // Rotulo pronto: nome do contato, "Carregando…" ate o contato chegar ou
  // "Contato indisponível" (403/404) — nunca o telefone de lead negado.
  name: string;
  // Chip curto do canal ("Standard"/"Coex"; vazio se desconhecido).
  channel: string;
  // Guia com rascunho guardado ("Fechar todas" pede confirmacao).
  hasDraft: boolean;
};

export type ChatTabsParams = {
  // Liga as guias: sessao carregada, fora do Ver como e com snapshot.
  enabled: boolean;
  // uid da persistencia ("" = nao le nem grava o localStorage).
  storageUid: string;
  auth: Auth | null;
  db: Firestore | null;
  conversationsPath: string;
  snapshotMode: boolean;
  sessionUser: SessionUser | null;
  canSeeAll: boolean;
  operators: Operator[];
  allConversations: Conversation[];
  // Camada AO VIVO (listeners das janelas): junto com o snapshot do servidor
  // do listener da guia, e a base confiavel do fechamento automatico.
  liveConversations: Conversation[];
  contactsById: Map<number, Contact>;
  unavailableContactIds: ReadonlySet<number>;
  selectedThreadId: string | null;
  setSelectedThreadId: (id: string | null) => void;
  holdEmptySelectionRef: MutableRefObject<boolean>;
  setTabPins: Dispatch<SetStateAction<Map<string, Conversation>>>;
  setDraftState: Dispatch<SetStateAction<string>>;
  // Modo do composer (nota interna/sussurro): vai junto com o rascunho.
  internalMode: boolean;
  setInternalMode: (value: boolean) => void;
  // Correcao em andamento: o texto do composer e a mensagem corrigida, nao
  // rascunho — nao e salvo nem restaurado.
  correctionTargetRef: { readonly current: unknown };
  // Lista de mensagens rapidas aberta (/atalho): as setas sao dela.
  suggestionsOpen: boolean;
  setNotice: (message: string) => void;
  // Geracao do escopo do usuario (muda no logout/troca de conta): descarta a
  // restauracao em voo do usuario anterior (PC compartilhado).
  scopeGenerationRef: MutableRefObject<number>;
};

export type ChatTabsApi = {
  openTabs: string[];
  tabInfo: ChatTabInfo[];
  activateTab: (id: string) => void;
  // Fechamento manual (X): a ativa passa a vizinha, como no navegador.
  closeTab: (id: string) => void;
  closeAllTabs: () => void;
  // Fecha sem aviso e sem vizinha (ex.: transferencia — o chat ja fecha).
  discardTab: (id: string | null) => void;
  // Escrita do composer feita pelo setDraft do provider (ver comentario).
  writeDraft: (threadId: string | null, value: string) => void;
  // Logout/troca de usuario: zera a memoria e os listeners. NAO apaga o
  // localStorage — as guias voltam no proximo login do mesmo uid.
  resetTabs: () => void;
  // Botao Sair (logout explicito): apaga os rascunhos salvos do uid (PC
  // compartilhado); a lista de guias fica.
  clearSavedDrafts: () => void;
};

export function chatTabChannel(conversation: Conversation | null): string {
  const type = conversation?.channel_type || conversation?.source_channel_type || "";
  return type === "standard" ? "Standard" : type === "coexistence" ? "Coex" : "";
}

export function chatTabName(contact: Contact | null, unavailable: boolean): string {
  if (contact) return contact.display_name || contact.phone_formatted || "Contato";
  // Contato negado/inexistente (403/404): nunca o telefone/wa_id do doc da
  // thread — e lead de outra operadora (LGPD).
  if (unavailable) return UNAVAILABLE_TAB_NAME;
  return LOADING_TAB_NAME;
}

// Nome so quando e de fato o contato (sem "Carregando…"/"indisponivel"):
// usado em avisos e no rotulo do X.
export function chatTabRealName(name: string): string {
  return name === LOADING_TAB_NAME || name === UNAVAILABLE_TAB_NAME ? "" : name;
}

type DraftEntry = { text: string; internal: boolean; at: number };

function readStorage(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch { /* storage indisponivel: vale so na sessao */ }
}

function parseJson(raw: string | null): unknown {
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

// Le e saneia a lista salva (storage e editavel pelo usuario: so ids no
// formato de thread, sem repetir, no maximo o limite de guias).
function readStoredTabs(uid: string): string[] {
  const rawIds = parseJson(readStorage(`${TABS_STORAGE_KEY}.${uid}`));
  const ids: string[] = [];
  if (Array.isArray(rawIds)) {
    for (const item of rawIds) {
      if (typeof item === "string" && item.length <= 64 && VALID_TAB_ID.test(item) && !ids.includes(item)) ids.push(item);
    }
  }
  return ids.slice(-MAX_CHAT_TABS);
}

// Rascunhos salvos: {id: {text, internal, at}}. Entrada sem o modo (formato
// so-texto) e descartada — restaurar sem saber se era nota interna poderia
// mandar ao cliente.
function readStoredDrafts(uid: string): Record<string, DraftEntry> {
  const parsed = uid ? parseJson(readStorage(`${DRAFTS_STORAGE_KEY}.${uid}`)) : null;
  const drafts: Record<string, DraftEntry> = {};
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return drafts;
  for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (!VALID_TAB_ID.test(id) || !value || typeof value !== "object") continue;
    const item = value as { text?: unknown; internal?: unknown; at?: unknown };
    if (typeof item.text !== "string" || !item.text || typeof item.internal !== "boolean") continue;
    drafts[id] = { text: item.text, internal: item.internal, at: typeof item.at === "number" ? item.at : 0 };
  }
  return drafts;
}

// Grava so as chaves que mudaram (le, mescla e regrava): duas abas do
// navegador com o mesmo uid nao apagam o rascunho uma da outra. A LISTA de
// guias continua "a ultima aba que gravou vence" — cada aba tem a sua lista;
// no F5 volta a da ultima aba que mexeu nas guias.
function saveStoredDrafts(uid: string, changes: Map<string, DraftEntry | null>) {
  if (!uid || !changes.size) return;
  const drafts = readStoredDrafts(uid);
  changes.forEach((entry, id) => {
    if (entry) drafts[id] = entry;
    else delete drafts[id];
  });
  writeStorage(`${DRAFTS_STORAGE_KEY}.${uid}`, Object.keys(drafts).length ? JSON.stringify(drafts) : null);
}

// No login: tira do storage o rascunho de thread que nao existe mais e as
// sobras velhas (fora de qualquer lista ha mais de 7 dias). Rascunho recente
// fora desta lista fica — pode ser de outra aba do navegador aberta ou de
// guia fechada automaticamente (volta se a conversa for reaberta).
function pruneStoredDrafts(uid: string, keep: string[], removeNow: string[]) {
  const now = Date.now();
  const cleanup = new Map<string, DraftEntry | null>();
  for (const [id, entry] of Object.entries(readStoredDrafts(uid))) {
    if (keep.includes(id)) continue;
    if (removeNow.includes(id) || now - entry.at > ORPHAN_DRAFT_MS) cleanup.set(id, null);
  }
  saveStoredDrafts(uid, cleanup);
}

// Estado observado de cada guia: o fechamento automatico reage a MUDANCA
// (abrir uma thread que ja e de outro ou ja esta fechada nao fecha a guia).
type TabWatch = { pool: boolean; mine: boolean; closed: boolean };

type TabListeners = { auth: Auth | null; db: Firestore | null; path: string; subs: Map<string, () => void> };

type RestoreResult =
  | { id: string; kind: "ok"; conversation: Conversation | null; fromServer: boolean }
  | { id: string; kind: "denied" | "missing" | "closed" };

export function useChatTabs(params: ChatTabsParams): ChatTabsApi {
  const {
    enabled, storageUid, auth, db, conversationsPath, snapshotMode, sessionUser, canSeeAll, operators,
    allConversations, liveConversations, contactsById, unavailableContactIds, selectedThreadId, setDraftState, internalMode,
  } = params;
  // Guias so com snapshot: sem listener por guia (polling) a pin congelaria,
  // seguraria thread que saiu do escopo e inflaria as nao lidas.
  const active = enabled && snapshotMode && !!auth && !!db && !!conversationsPath;
  // Valores do render mais recente para callbacks de listener/async.
  const latest = useRef({ ...params, active });
  latest.current = { ...params, active };

  const [openTabs, setOpenTabsState] = useState<string[]>([]);
  // Espelho sincrono da lista (callbacks de listener e acoes no mesmo tick).
  const openTabsRef = useRef<string[]>([]);
  // Rascunho guardado de cada guia aberta (id da thread -> texto + modo).
  const draftsRef = useRef<Map<string, DraftEntry>>(new Map());
  // Muda quando uma guia ganha ou perde rascunho (tabInfo.hasDraft).
  const [draftsVersion, setDraftsVersion] = useState(0);
  // Thread dona do texto que esta no composer (draft). So muda no effect de
  // troca, que roda DEPOIS do effect de correcao do provider.
  const draftOwnerRef = useRef<string | null>(null);
  // Selecao ja commitada (layout effect, antes de qualquer effect passivo).
  const committedRef = useRef<string | null>(null);
  const watchRef = useRef<Map<string, TabWatch>>(new Map());
  // Ultimo doc da thread CONFIRMADO PELO SERVIDOR (listener da guia ou leitura
  // da restauracao). Com a camada ao vivo, e a unica base do fechamento
  // automatico: copia otimista (picker) ou estatica (paginada) nao conta.
  const serverDocsRef = useRef<Map<string, Conversation>>(new Map());
  // Ordem de uso de cada guia (ultima ativacao): o limite fecha a menos usada.
  const usageRef = useRef<Map<string, number>>(new Map());
  const usageSeqRef = useRef(0);
  // Restauracao iniciada / concluida por uid. Antes de concluir, a lista nao e
  // gravada (senao a lista vazia do boot apagaria as guias salvas).
  const restoredUidRef = useRef("");
  const readyUidRef = useRef("");
  const listenersRef = useRef<TabListeners>({ auth: null, db: null, path: "", subs: new Map() });

  const commitTabs = useCallback((next: string[]) => {
    openTabsRef.current = next;
    setOpenTabsState(next);
  }, []);

  const saveDrafts = useCallback((changes: Map<string, DraftEntry | null>) => {
    saveStoredDrafts(latest.current.storageUid, changes);
  }, []);

  const bumpDrafts = useCallback(() => setDraftsVersion((value) => value + 1), []);

  // Lista de guias (a ultima aba do navegador que gravou vence).
  const persist = useCallback(() => {
    const uid = latest.current.storageUid;
    if (!uid || readyUidRef.current !== uid) return;
    const ids = openTabsRef.current;
    writeStorage(`${TABS_STORAGE_KEY}.${uid}`, ids.length ? JSON.stringify(ids) : null);
  }, []);

  // "Guia de Maria" pro aviso; sem nome conhecido (ou contato negado), "Guia".
  const tabLabel = useCallback((id: string) => {
    const p = latest.current;
    const conversation = p.allConversations.find((c) => c.id === id) || null;
    const contact = conversation ? p.contactsById.get(conversation.contact_id) || null : null;
    const name = chatTabRealName(chatTabName(contact, !!conversation && p.unavailableContactIds.has(conversation.contact_id)));
    return name ? `Guia de ${name}` : "Guia";
  }, []);

  // Esquece tudo de guias que sairam: rascunho, estado observado, doc do
  // servidor, ordem de uso, listener e pin. keepSaved: o rascunho fica no
  // storage (fechamento automatico/limite — volta se a conversa for reaberta).
  const forget = useCallback((ids: string[], keepSaved = false) => {
    if (!ids.length) return;
    const subs = listenersRef.current.subs;
    const removedDrafts = new Map<string, DraftEntry | null>();
    for (const id of ids) {
      if (draftsRef.current.delete(id)) removedDrafts.set(id, null);
      watchRef.current.delete(id);
      serverDocsRef.current.delete(id);
      usageRef.current.delete(id);
      const stop = subs.get(id);
      if (stop) { stop(); subs.delete(id); }
    }
    if (removedDrafts.size) {
      if (!keepSaved) saveDrafts(removedDrafts);
      bumpDrafts();
    }
    latest.current.setTabPins((prev) => {
      if (!ids.some((id) => prev.has(id))) return prev;
      const next = new Map(prev);
      ids.forEach((id) => next.delete(id));
      return next;
    });
  }, [bumpDrafts, saveDrafts]);

  // Limite: fecha a guia MENOS USADA (ultima ativacao), nunca a ativa, e
  // prefere as sem rascunho; so fecha guia com rascunho se todas tiverem.
  const trimToLimit = useCallback((ids: string[], keep: string | null) => {
    let next = ids;
    const dropped: string[] = [];
    const usage = usageRef.current;
    const byUse = (a: string, b: string) => (usage.get(a) ?? 0) - (usage.get(b) ?? 0);
    while (next.length > MAX_CHAT_TABS) {
      const candidates = next.filter((id) => id !== keep);
      if (!candidates.length) break;
      const clean = candidates.filter((id) => !draftsRef.current.has(id)).sort(byUse);
      const victim = clean[0] ?? candidates.slice().sort(byUse)[0];
      dropped.push(victim);
      next = next.filter((id) => id !== victim);
    }
    return { next, dropped };
  }, []);

  const removeTabs = useCallback((ids: string[], selectNeighbor: boolean, keepSaved = false) => {
    const current = openTabsRef.current;
    const removing = ids.filter((id) => current.includes(id));
    if (!removing.length) return;
    const next = current.filter((id) => !removing.includes(id));
    const p = latest.current;
    const selected = p.selectedThreadId;
    forget(removing, keepSaved);
    commitTabs(next);
    persist();
    if (!selected || !removing.includes(selected)) return;
    if (selectNeighbor) {
      // Como no navegador: a guia da direita; sem ela, a da esquerda.
      const index = current.indexOf(selected);
      const neighbor = next[index] ?? next[index - 1] ?? null;
      if (neighbor) { p.setSelectedThreadId(neighbor); return; }
    }
    p.holdEmptySelectionRef.current = true;
    p.setSelectedThreadId(null);
  }, [commitTabs, forget, persist]);

  const activateTab = useCallback((id: string) => {
    if (openTabsRef.current.includes(id)) latest.current.setSelectedThreadId(id);
  }, []);
  const closeTab = useCallback((id: string) => removeTabs([id], true), [removeTabs]);
  const closeAllTabs = useCallback(() => removeTabs([...openTabsRef.current], false), [removeTabs]);
  const discardTab = useCallback((id: string | null) => { if (id) removeTabs([id], false); }, [removeTabs]);

  // Fechamento automatico: guia ativa volta pro placeholder (nunca pula pra
  // outra conversa — a operadora poderia estar digitando e mandaria pro
  // cliente errado). O rascunho fica salvo (volta se a conversa for reaberta)
  // e o aviso diz isso.
  const autoClose = useCallback((items: { id: string; reason: string }[]) => {
    const current = openTabsRef.current;
    const valid = items.filter((item, index) => current.includes(item.id) && items.findIndex((other) => other.id === item.id) === index);
    if (!valid.length) return;
    const message = valid
      .map((item) => `${tabLabel(item.id)} fechada: ${item.reason}${draftsRef.current.has(item.id) ? " (rascunho preservado)" : ""}.`)
      .join(" ");
    removeTabs(valid.map((item) => item.id), false, true);
    latest.current.setNotice(message);
  }, [removeTabs, tabLabel]);

  // internal null = mantem o modo ja gravado (escrita que nao veio do composer
  // da guia, ex.: envio que terminou depois da troca).
  const storeDraft = useCallback((id: string, text: string, internal: boolean | null) => {
    if (!openTabsRef.current.includes(id)) return;
    const previous = draftsRef.current.get(id);
    const entry = text ? { text, internal: internal ?? previous?.internal ?? false, at: Date.now() } : null;
    if (entry) draftsRef.current.set(id, entry);
    else if (!draftsRef.current.delete(id)) return;
    saveDrafts(new Map([[id, entry]]));
    if (!previous !== !entry) bumpDrafts();
  }, [bumpDrafts, saveDrafts]);

  // O provider chama isto pelo setDraft de CADA render, passando a thread
  // daquele render. Casos que fogem do "composer = guia selecionada":
  // - handler de render ANTERIOR a troca de guia (envio que terminou depois
  //   que a operadora trocou de guia): o setDraft("") do envio limpa so o
  //   rascunho guardado daquela guia, sem apagar o texto da guia atual;
  // - effect de correcao (render novo, antes da troca do composer): o texto
  //   e o da correcao cancelada — nao vira rascunho; a troca repoe o composer;
  // - correcao em andamento: o composer tem o texto corrigido, nao rascunho
  //   (fica salvo o rascunho de antes da correcao).
  const writeDraft = useCallback((threadId: string | null, value: string) => {
    const p = latest.current;
    if (!p.active) { p.setDraftState(value); return; }
    if (threadId !== committedRef.current) {
      if (threadId) storeDraft(threadId, value, null);
      return;
    }
    const owner = draftOwnerRef.current;
    if (owner === threadId && owner && !p.correctionTargetRef.current) storeDraft(owner, value, p.internalMode);
    p.setDraftState(value);
  }, [storeDraft]);

  const resetTabs = useCallback(() => {
    listenersRef.current.subs.forEach((stop) => stop());
    listenersRef.current = { auth: null, db: null, path: "", subs: new Map() };
    draftsRef.current = new Map();
    watchRef.current = new Map();
    serverDocsRef.current = new Map();
    usageRef.current = new Map();
    restoredUidRef.current = "";
    readyUidRef.current = "";
    commitTabs([]);
    bumpDrafts();
    latest.current.setTabPins(new Map());
  }, [bumpDrafts, commitTabs]);

  const clearSavedDrafts = useCallback(() => {
    draftsRef.current = new Map();
    bumpDrafts();
    const uid = latest.current.storageUid;
    if (uid) writeStorage(`${DRAFTS_STORAGE_KEY}.${uid}`, null);
  }, [bumpDrafts]);

  // Selecao commitada: layout effect roda antes de todo effect passivo
  // (inclusive o de correcao do provider), base do writeDraft acima.
  useLayoutEffect(() => {
    committedRef.current = selectedThreadId;
  }, [selectedThreadId]);

  // Toda conversa aberta vira guia (sem mexer nos call sites de
  // setSelectedThreadId). A copia de allConversations vira a pin da guia, que
  // mantem a thread no merge mesmo fora das janelas ao vivo. Guia nova
  // recupera o rascunho que ficou salvo (ex.: fechada automaticamente).
  useEffect(() => {
    if (!active || !selectedThreadId) return;
    const id = selectedThreadId;
    const p = latest.current;
    usageRef.current.set(id, ++usageSeqRef.current);
    const conversation = p.allConversations.find((c) => c.id === id);
    if (conversation) p.setTabPins((prev) => (prev.get(id) === conversation ? prev : new Map(prev).set(id, conversation)));
    const current = openTabsRef.current;
    if (current.includes(id)) return;
    if (!draftsRef.current.has(id)) {
      const saved = readStoredDrafts(p.storageUid)[id];
      if (saved) { draftsRef.current.set(id, saved); bumpDrafts(); }
    }
    const { next, dropped } = trimToLimit([...current, id], id);
    // So avisa quando a guia fechada pelo limite tinha rascunho (fica salvo).
    const kept = dropped.filter((tab) => draftsRef.current.has(tab)).map(tabLabel);
    forget(dropped, true);
    commitTabs(next);
    persist();
    if (kept.length) p.setNotice(`Limite de ${MAX_CHAT_TABS} guias: ${kept.join(", ")} fechada (rascunho preservado).`);
  }, [active, selectedThreadId, bumpDrafts, commitTabs, forget, persist, tabLabel, trimToLimit]);

  // Troca de guia: o composer passa a mostrar o rascunho da nova, no modo em
  // que foi escrito (nota interna nao volta como mensagem ao cliente). Guia
  // sem rascunho mantem o modo atual, como antes das guias. Nao precisa salvar
  // a anterior aqui — toda escrita do composer ja passa por writeDraft.
  useEffect(() => {
    if (draftOwnerRef.current === selectedThreadId) return;
    draftOwnerRef.current = selectedThreadId;
    if (!active) return;
    const saved = selectedThreadId ? draftsRef.current.get(selectedThreadId) : undefined;
    setDraftState(saved?.text ?? "");
    if (saved) latest.current.setInternalMode(saved.internal);
  }, [active, selectedThreadId, setDraftState]);

  // Ligar/desligar a nota interna com texto no composer muda o modo do
  // rascunho guardado (fora de correcao, que forca o modo normal).
  useEffect(() => {
    if (!active) return;
    const owner = draftOwnerRef.current;
    if (!owner || owner !== committedRef.current || latest.current.correctionTargetRef.current) return;
    const saved = draftsRef.current.get(owner);
    if (saved && saved.internal !== internalMode) storeDraft(owner, saved.text, internalMode);
  }, [active, internalMode, storeDraft]);

  // Grava a lista a cada mudanca. Declarado ANTES da restauracao: no flush do
  // login ainda nao esta liberado e nao apaga o que esta salvo.
  useEffect(() => {
    persist();
  }, [openTabs, storageUid, persist]);

  // Restauracao no login (1x por uid): volta a FAIXA, sem selecionar nenhuma
  // guia (abrir sozinha dispararia o mark-read sem a operadora ver). Cada
  // thread e validada no Firestore: sem permissao (de outro operador agora),
  // inexistente ou com atendimento ja encerrado = descarta. Falha transitoria
  // = mantem (o listener da guia valida).
  useEffect(() => {
    if (!active || !storageUid || !auth || !db || restoredUidRef.current === storageUid) return;
    const uid = storageUid;
    restoredUidRef.current = uid;
    writeStorage(`${LEGACY_ACTIVE_TAB_KEY}.${uid}`, null);
    const storedIds = readStoredTabs(uid);
    if (!storedIds.length) {
      // Nada salvo: libera a gravacao na hora e limpa sobras velhas.
      readyUidRef.current = uid;
      pruneStoredDrafts(uid, openTabsRef.current, []);
      persist();
      return;
    }
    const generation = latest.current.scopeGenerationRef.current;
    void (async () => {
      const results = await Promise.all(storedIds.map(async (id): Promise<RestoreResult> => {
        try {
          const snap = await getSessionDoc(auth, firestoreDoc(db, conversationsPath, id));
          const fromServer = !snap.metadata?.fromCache;
          if (!snap.exists()) return fromServer ? { id, kind: "missing" } : { id, kind: "ok", conversation: null, fromServer };
          const conversation = normalizeConversation(snap.data() as Record<string, unknown>, snap.id);
          if (fromServer && (conversation.attendance_status || "").startsWith("fechado_")) return { id, kind: "closed" };
          return { id, kind: "ok", conversation, fromServer };
        } catch (error) {
          // Ausente so no cache/rede fora nao prova nada: mantem (listener valida).
          return (error as { code?: string })?.code === "permission-denied" ? { id, kind: "denied" } : { id, kind: "ok", conversation: null, fromServer: false };
        }
      }));
      const p = latest.current;
      // Logout/troca de conta no meio: nada do usuario anterior entra.
      if (generation !== p.scopeGenerationRef.current || p.storageUid !== uid || !p.active) return;
      const restored = results.filter((item): item is Extract<RestoreResult, { kind: "ok" }> => item.kind === "ok");
      const restoredIds = restored.map((item) => item.id);
      // Restauradas contam como usadas antes de tudo que foi aberto agora.
      restoredIds.forEach((id, index) => { if (!usageRef.current.has(id)) usageRef.current.set(id, index - restoredIds.length); });
      const current = openTabsRef.current;
      const { next, dropped } = trimToLimit([...restoredIds.filter((id) => !current.includes(id)), ...current], committedRef.current);
      forget(dropped, true);
      const pins = restored.filter((item) => item.conversation && next.includes(item.id));
      pins.forEach((item) => { if (item.fromServer) serverDocsRef.current.set(item.id, item.conversation as Conversation); });
      if (pins.length) {
        p.setTabPins((prev) => {
          const map = new Map(prev);
          pins.forEach((item) => map.set(item.id, item.conversation as Conversation));
          return map;
        });
      }
      // Rascunhos das guias que voltaram (sem pisar no que ja foi digitado
      // nesta sessao). Thread apagada perde o rascunho; encerrada ou sem
      // permissao mantem (volta se a conversa for reaberta) ate a validade.
      const storedDrafts = readStoredDrafts(uid);
      let loaded = false;
      for (const id of next) {
        const entry = storedDrafts[id];
        if (entry && !draftsRef.current.has(id) && draftOwnerRef.current !== id) { draftsRef.current.set(id, entry); loaded = true; }
      }
      if (loaded) bumpDrafts();
      pruneStoredDrafts(uid, next, results.filter((item) => item.kind === "missing").map((item) => item.id));
      commitTabs(next);
      readyUidRef.current = uid;
      persist();
      const closedCount = results.filter((item) => item.kind === "closed").length;
      if (closedCount) {
        p.setNotice(closedCount === 1
          ? "1 guia de atendimento encerrado não foi restaurada."
          : `${closedCount} guias de atendimentos encerrados não foram restauradas.`);
      }
    })();
  }, [active, storageUid, auth, db, conversationsPath, bumpDrafts, commitTabs, forget, persist, trimToLimit]);

  // 1 listener por guia (no maximo 10) no doc da thread: mantem a pin fresca
  // (badge, dono e status ao vivo fora do top-50), registra o doc confirmado
  // pelo servidor (base do fechamento automatico) e detecta perda de escopo
  // (permission-denied = atendimento passou pra outro operador). O listener da
  // thread selecionada no provider continua; o SDK reaproveita o mesmo alvo.
  // Id que nao vira referencia valida (storage adulterado) derruba so a guia.
  useEffect(() => {
    const store = listenersRef.current;
    if (!active || store.auth !== auth || store.db !== db || store.path !== conversationsPath) {
      store.subs.forEach((stop) => stop());
      listenersRef.current = { auth: active ? auth : null, db: active ? db : null, path: active ? conversationsPath : "", subs: new Map() };
    }
    if (!active || !auth || !db) return;
    const subs = listenersRef.current.subs;
    subs.forEach((stop, id) => {
      if (!openTabs.includes(id)) { stop(); subs.delete(id); }
    });
    const invalid: string[] = [];
    for (const id of openTabs) {
      if (subs.has(id)) continue;
      let stopped = false;
      let unsubscribe: () => void;
      try {
        if (!VALID_TAB_ID.test(id)) throw new Error("id de thread invalido");
        unsubscribe = watchSessionDocument(auth, firestoreDoc(db, conversationsPath, id),
          (snap) => {
            if (stopped || !openTabsRef.current.includes(id)) return;
            const fromServer = !snap.metadata?.fromCache;
            if (!snap.exists()) {
              // So o servidor prova que o doc sumiu (cache vazio offline nao).
              if (fromServer) autoClose([{ id, reason: "atendimento não está mais disponível" }]);
              return;
            }
            const fresh = normalizeConversation(snap.data() as Record<string, unknown>, snap.id);
            if (fromServer) serverDocsRef.current.set(id, fresh);
            latest.current.setTabPins((prev) => new Map(prev).set(id, fresh));
          },
          (error) => {
            if (stopped || !openTabsRef.current.includes(id)) return;
            if ((error as { code?: string })?.code === "permission-denied") autoClose([{ id, reason: "atendimento assumido por outro operador" }]);
          },
        );
      } catch {
        invalid.push(id);
        continue;
      }
      subs.set(id, () => { stopped = true; unsubscribe(); });
    }
    if (invalid.length) removeTabs(invalid, false);
  }, [active, auth, db, conversationsPath, openTabs, autoClose, removeTabs]);
  // Desmontagem: encerra todos os listeners das guias.
  useEffect(() => () => {
    listenersRef.current.subs.forEach((stop) => stop());
    listenersRef.current = { auth: null, db: null, path: "", subs: new Map() };
  }, []);

  // Fechamento automatico. Base CONFIAVEL apenas: doc confirmado pelo servidor
  // (listener da guia/restauracao) ou a camada ao vivo — a copia otimista do
  // picker (sem attendance_status vira "aberto") e as estaticas nao registram
  // nem disparam nada. Reage a MUDANCA observada:
  // - attendance_status passou a "fechado_*": fecha so guia NAO ativa — na
  //   ativa o chat ja mostra o encerramento e o "Reabrir atendimento" fica a
  //   mao (inclusive quando foi a propria operadora que fechou);
  // - operador comum: deixou de ser meu/pool (assumido/transferido por outro),
  //   inclusive a ativa. Mesmas excecoes do chat aberto: Dono do LEAD (coex no
  //   numero de outro operador) e handler do takeover. Admin/supervisor: nao.
  // E, sem depender de mudanca, operador comum perde a guia cujo contato ficou
  // indisponivel (403/404): lead de outra operadora nao fica aberto (LGPD).
  useEffect(() => {
    if (!active || !sessionUser) return;
    const live = new Map(liveConversations.map((c) => [c.id, c]));
    const closing: { id: string; reason: string }[] = [];
    for (const id of openTabs) {
      const known = allConversations.find((c) => c.id === id);
      if (!canSeeAll && known && unavailableContactIds.has(known.contact_id)) {
        closing.push({ id, reason: "contato indisponível" });
        continue;
      }
      const observed = serverDocsRef.current.get(id) ?? live.get(id);
      if (!observed) continue;  // so copia otimista/estatica: ainda sem base
      const closed = (observed.attendance_status || "").startsWith("fechado_");
      const ownerUid = observed.assigned_to_uid || "";
      const ownerId = observed.assigned_to ?? null;
      const pool = !ownerUid && ownerId == null;
      const contact = contactsById.get(observed.contact_id);
      const mine = (!!ownerUid && ownerUid === sessionUser.firebase_uid)
        || (ownerId != null && ownerId === sessionUser.id)
        || (contact?.assigned_to != null && contact.assigned_to === sessionUser.id)
        || (observed.takeover_handler_user_id != null && observed.takeover_handler_user_id === sessionUser.id);
      const prev = watchRef.current.get(id);
      watchRef.current.set(id, { pool, mine, closed });
      if (!prev) continue;  // primeira leitura confiavel: registra e observa
      if (!canSeeAll && (prev.pool || prev.mine) && !pool && !mine) {
        const ownerName = operators.find((o) => o.id === ownerId)?.display_name || "outro operador";
        closing.push({ id, reason: prev.mine ? `atendimento transferido para ${ownerName}` : `atendimento assumido por ${ownerName}` });
      } else if (closed && !prev.closed && id !== selectedThreadId) {
        closing.push({ id, reason: "atendimento encerrado" });
      }
    }
    if (closing.length) autoClose(closing);
  }, [active, sessionUser, canSeeAll, operators, openTabs, allConversations, liveConversations, contactsById, unavailableContactIds, selectedThreadId, autoClose]);

  // Atalho: Ctrl+Alt+Seta baixo = proxima guia, Ctrl+Alt+Seta cima = anterior
  // (circular). Nao age num <select>, com a lista de mensagens rapidas aberta
  // (as setas sao dela) nem em tecla ja tratada por outro handler.
  useEffect(() => {
    if (!active) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !event.ctrlKey || !event.altKey || event.metaKey || event.shiftKey || event.isComposing) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      if ((event.target as HTMLElement | null)?.tagName === "SELECT" || latest.current.suggestionsOpen) return;
      const tabs = openTabsRef.current;
      if (!tabs.length) return;
      const selected = latest.current.selectedThreadId;
      const index = selected ? tabs.indexOf(selected) : -1;
      const step = event.key === "ArrowDown" ? 1 : -1;
      const target = index < 0
        ? tabs[step > 0 ? 0 : tabs.length - 1]
        : tabs[(index + step + tabs.length) % tabs.length];
      if (!target || target === selected) return;
      event.preventDefault();
      latest.current.setSelectedThreadId(target);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active]);

  const tabInfo = useMemo<ChatTabInfo[]>(() => openTabs.map((id) => {
    const conversation = allConversations.find((c) => c.id === id) || null;
    const contact = conversation ? contactsById.get(conversation.contact_id) || null : null;
    const unavailable = !!conversation && unavailableContactIds.has(conversation.contact_id);
    return {
      id,
      conversation,
      contact,
      unread: conversation ? (conversation.unread_count ?? conversation.unread ?? 0) : 0,
      isActive: id === selectedThreadId,
      name: chatTabName(contact, unavailable),
      channel: chatTabChannel(conversation),
      hasDraft: draftsRef.current.has(id),
    };
    // draftsVersion: hasDraft le o ref; muda so quando uma guia ganha/perde rascunho.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [openTabs, allConversations, contactsById, unavailableContactIds, selectedThreadId, draftsVersion]);

  return { openTabs, tabInfo, activateTab, closeTab, closeAllTabs, discardTab, writeDraft, resetTabs, clearSavedDrafts };
}
