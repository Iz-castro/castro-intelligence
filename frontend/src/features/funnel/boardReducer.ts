import { parseInstant } from "./format";
import type { BoardColumnPayload, BoardFilters, BoardResponse, FunnelCard, FunnelSignals, FunnelStage, StageKind, StageState, TaskSummary } from "./types";

// Estado do quadro: PURO (sem I/O, sem React). Regras:
// - um contato aparece em UMA coluna so: a de stage_version maior (colunas
//   sao consultadas em paralelo e paginas antigas podem chegar depois);
// - totais locais apos mover (saiu de A: -1; entrou em B: +1; parados idem);
// - card movido entra no TOPO so em ordem desc (mais recente na etapa); em
//   asc so entra no fim quando a coluna ja esta toda carregada;
// - resposta de carregamento antigo (requestId) e descartada.

const DAY_MS = 86_400_000;

export type BoardColumn = {
  stage: string;
  label: string;
  kind: StageKind;
  active: boolean;
  count: number;
  staleCount: number | null;
  cards: FunnelCard[];
  nextCursor: string | null;
  loadingMore: boolean;
  error: string;
};

export type BoardStatus = "idle" | "loading" | "ready" | "error";

export type BoardState = {
  requestId: number;
  status: BoardStatus;
  error: string;
  errorCode: string;
  filters: BoardFilters;
  generatedAt: string;
  loadedAt: number;
  columns: BoardColumn[];
  // Mudanca fora dos cards carregados (drawer aberto pela busca, contato que
  // saiu do acesso): os totais locais nao sabem se o contato casava com o
  // filtro -> a UI pede "Atualizar".
  outdated: boolean;
};

export type BoardAction =
  | { type: "reset" }
  | { type: "load_started"; requestId: number; filters: BoardFilters }
  | { type: "load_succeeded"; requestId: number; response: BoardResponse; loadedAt: number }
  | { type: "load_failed"; requestId: number; error: string; code?: string; clear?: boolean }
  | { type: "more_started"; stage: string }
  | { type: "more_succeeded"; requestId: number; stage: string; cards: FunnelCard[]; nextCursor: string | null }
  | { type: "more_failed"; requestId: number; stage: string; error: string; expired?: boolean }
  | { type: "card_moved"; contactId: number; result: StageState; target: FunnelStage | null | undefined; now: number }
  | { type: "card_removed"; contactId: number };

export const DEFAULT_FILTERS: BoardFilters = { order: "desc", ownerId: null, mine: false };

let requestSequence = 0;
export function nextBoardRequestId(): number {
  requestSequence += 1;
  return requestSequence;
}

export function sameFilters(left: BoardFilters, right: BoardFilters): boolean {
  return left.order === right.order && left.ownerId === right.ownerId && left.mine === right.mine;
}

export function createBoardState(filters: BoardFilters = DEFAULT_FILTERS): BoardState {
  return { requestId: 0, status: "idle", error: "", errorCode: "", filters, generatedAt: "", loadedAt: 0, columns: [], outdated: false };
}

function cardVersion(card: FunnelCard): number {
  return Number.isInteger(card.stage_version) && card.stage_version > 0 ? card.stage_version : 0;
}

function safeCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

// Porte fiel de funnel_catalog.derived_signals (mesma regra dos selos e do
// "N parados" do cabecalho), usado so para recalcular o card movido.
export function deriveSignals(stage: FunnelStage | null | undefined, input: {
  changedAt: string | null | undefined; lastInboundAt: string | null | undefined; nextTask: TaskSummary | null | undefined; tasksVisible: boolean;
}, now: number): FunnelSignals {
  const changed = parseInstant(input.changedAt);
  const inbound = parseInstant(input.lastInboundAt);
  const daysInStage = changed == null ? null : Math.floor((now - changed) / DAY_MS);
  const idleDays = inbound == null ? null : Math.floor((now - inbound) / DAY_MS);
  const rule = stage?.stale || null;
  let stale = false;
  if (rule?.kind === "patient_silence" && rule.days && idleDays != null) stale = idleDays >= rule.days;
  else if (rule?.kind === "time_in_stage" && rule.days && daysInStage != null) stale = daysInStage >= rule.days;
  const signals: FunnelSignals = {
    days_in_stage: daysInStage, patient_idle_days: idleDays, stale, stale_kind: stale && rule ? rule.kind : null,
    task_overdue: false, no_next_action: false, new_activity: false,
  };
  if (input.tasksVisible) {
    const due = parseInstant(input.nextTask?.due_at);
    signals.task_overdue = due != null && due < now;
    if (rule?.kind === "task") signals.no_next_action = !input.nextTask;
  }
  if (stage && (stage.kind === "triage" || stage.kind === "lost" || stage.kind === "excluded" || stage.kind === "won")) {
    signals.new_activity = inbound != null && changed != null && inbound > changed;
  }
  return signals;
}

function columnFromPayload(payload: BoardColumnPayload): BoardColumn {
  return {
    stage: String(payload.stage), label: String(payload.label || payload.stage), kind: payload.kind, active: payload.active !== false,
    count: safeCount(payload.count), staleCount: payload.stale_count == null ? null : safeCount(payload.stale_count),
    cards: Array.isArray(payload.cards) ? payload.cards.filter((card) => card && Number.isInteger(card.contact_id)) : [],
    nextCursor: payload.next_cursor || null, loadingMore: false, error: "",
  };
}

// Carregamento inteiro: fica a ocorrencia de versao maior; empate = primeira
// na ordem do catalogo (e a primeira dentro da coluna).
function dedupeColumns(columns: BoardColumn[]): BoardColumn[] {
  const best = new Map<number, { column: number; index: number; version: number }>();
  columns.forEach((column, columnIndex) => column.cards.forEach((card, index) => {
    const current = best.get(card.contact_id);
    if (!current || cardVersion(card) > current.version) best.set(card.contact_id, { column: columnIndex, index, version: cardVersion(card) });
  }));
  return columns.map((column, columnIndex) => {
    const cards = column.cards.filter((card, index) => {
      const keep = best.get(card.contact_id);
      return keep?.column === columnIndex && keep.index === index;
    });
    return cards.length === column.cards.length ? column : { ...column, cards };
  });
}

// Pagina seguinte de UMA coluna: card ja exibido com versao igual/maior e
// descartado; versao maior substitui a copia antiga (em qualquer coluna).
// Totais nao mudam (vem do servidor no carregamento).
function mergePage(columns: BoardColumn[], stage: string, incoming: FunnelCard[], nextCursor: string | null): BoardColumn[] {
  const target = columns.findIndex((column) => column.stage === stage);
  if (target < 0) return columns;
  const located = new Map<number, { column: number; version: number }>();
  columns.forEach((column, index) => column.cards.forEach((card) => located.set(card.contact_id, { column: index, version: cardVersion(card) })));
  const drops = new Map<number, Set<number>>();
  const accepted: FunnelCard[] = [];
  const seen = new Set<number>();
  for (const card of Array.isArray(incoming) ? incoming : []) {
    if (!card || !Number.isInteger(card.contact_id) || seen.has(card.contact_id)) continue;
    const existing = located.get(card.contact_id);
    if (existing && existing.version >= cardVersion(card)) continue;
    if (existing) {
      const set = drops.get(existing.column) || new Set<number>();
      set.add(card.contact_id);
      drops.set(existing.column, set);
    }
    seen.add(card.contact_id);
    accepted.push(card);
  }
  return columns.map((column, index) => {
    const drop = drops.get(index);
    const cards = drop ? column.cards.filter((card) => !drop.has(card.contact_id)) : column.cards;
    if (index === target) return { ...column, cards: [...cards, ...accepted], nextCursor, loadingMore: false, error: "" };
    return drop ? { ...column, cards } : column;
  });
}

function bump(value: number | null, delta: number): number | null {
  return value == null ? null : Math.max(0, value + delta);
}

function applyMove(state: BoardState, action: Extract<BoardAction, { type: "card_moved" }>): BoardState {
  const { contactId, result, target, now } = action;
  let fromIndex = -1;
  let card: FunnelCard | null = null;
  for (let index = 0; index < state.columns.length; index += 1) {
    for (const entry of state.columns[index].cards) {
      if (entry.contact_id === contactId && (!card || cardVersion(entry) > cardVersion(card))) { card = entry; fromIndex = index; }
    }
  }
  if (!card) return { ...state, outdated: true };
  // Mudanca ja refletida (replay do recibo, dispatch em dobro, pagina nova).
  if (!Number.isInteger(result.version) || cardVersion(card) >= result.version) return state;
  const changedAt = result.changed_at || card.stage_changed_at;
  const updated: FunnelCard = {
    ...card, stage: result.key, stage_version: result.version, stage_changed_at: changedAt, stage_source: result.source || card.stage_source,
    reason: target?.requires_reason ? result.reason : null,
    signals: deriveSignals(target, { changedAt, lastInboundAt: card.last_inbound_at, nextTask: card.next_task, tasksVisible: card.tasks_visible }, now),
  };
  const staleBefore = card.signals?.stale ? 1 : 0;
  const staleAfter = updated.signals.stale ? 1 : 0;
  const toIndex = state.columns.findIndex((column) => column.stage === result.key);
  const columns = state.columns.map((column, index) => {
    if (index === fromIndex && index === toIndex) {
      // Correcao de motivo: mesma coluna, mesma posicao e mesmo total.
      return { ...column, cards: column.cards.map((entry) => entry.contact_id === contactId ? updated : entry), staleCount: bump(column.staleCount, staleAfter - staleBefore) };
    }
    if (index === fromIndex) {
      return { ...column, cards: column.cards.filter((entry) => entry.contact_id !== contactId), count: Math.max(0, column.count - 1), staleCount: bump(column.staleCount, -staleBefore) };
    }
    if (index === toIndex) {
      const others = column.cards.filter((entry) => entry.contact_id !== contactId);
      const cards = state.filters.order === "desc" ? [updated, ...others] : column.nextCursor ? others : [...others, updated];
      return { ...column, cards, count: column.count + 1, staleCount: bump(column.staleCount, staleAfter) };
    }
    return column;
  });
  return { ...state, columns, outdated: state.outdated || toIndex < 0 };
}

export function boardReducer(state: BoardState, action: BoardAction): BoardState {
  switch (action.type) {
    case "reset":
      return createBoardState();
    case "load_started": {
      // Troca de filtro nunca exibe a lista velha como se fosse a nova.
      const keep = sameFilters(state.filters, action.filters);
      return {
        ...state, requestId: action.requestId, status: "loading", error: "", errorCode: "", filters: action.filters,
        columns: keep ? state.columns.map((column) => column.loadingMore || column.error ? { ...column, loadingMore: false, error: "" } : column) : [],
        generatedAt: keep ? state.generatedAt : "", outdated: keep ? state.outdated : false,
      };
    }
    case "load_succeeded": {
      if (action.requestId !== state.requestId) return state;
      const columns = dedupeColumns((Array.isArray(action.response?.columns) ? action.response.columns : []).map(columnFromPayload));
      return { ...state, status: "ready", error: "", errorCode: "", generatedAt: action.response.generated_at || "", loadedAt: action.loadedAt, columns, outdated: false };
    }
    case "load_failed": {
      if (action.requestId !== state.requestId) return state;
      return { ...state, status: "error", error: action.error, errorCode: action.code || "", columns: action.clear ? [] : state.columns, generatedAt: action.clear ? "" : state.generatedAt };
    }
    case "more_started":
      return { ...state, columns: state.columns.map((column) => column.stage === action.stage ? { ...column, loadingMore: true, error: "" } : column) };
    case "more_succeeded":
      if (action.requestId !== state.requestId) return state;
      return { ...state, columns: mergePage(state.columns, action.stage, action.cards, action.nextCursor || null) };
    case "more_failed":
      if (action.requestId !== state.requestId) return state;
      return { ...state, columns: state.columns.map((column) => column.stage === action.stage ? { ...column, loadingMore: false, error: action.error, nextCursor: action.expired ? null : column.nextCursor } : column) };
    case "card_moved":
      return applyMove(state, action);
    case "card_removed": {
      if (!state.columns.some((column) => column.cards.some((card) => card.contact_id === action.contactId))) return state;
      return { ...state, outdated: true, columns: state.columns.map((column) => column.cards.some((card) => card.contact_id === action.contactId) ? { ...column, cards: column.cards.filter((card) => card.contact_id !== action.contactId) } : column) };
    }
    default:
      return state;
  }
}

// Paginacao encerrada (sem cursor, sem carga nem erro) com menos cards que o
// total do servidor: o restante da contagem nao chega a este usuario (ex.:
// lead de dono legado, contado no escopo mas negado por linha). A coluna
// avisa em vez de prometer cards que nao vem.
export function columnHasHidden(column: BoardColumn): boolean {
  return !column.nextCursor && !column.loadingMore && !column.error && column.cards.length < column.count;
}

// Card exibido (versao mais nova) de um contato, para reabrir o dialogo.
export function findCard(state: BoardState, contactId: number): FunnelCard | null {
  let found: FunnelCard | null = null;
  for (const column of state.columns) {
    for (const card of column.cards) if (card.contact_id === contactId && (!found || cardVersion(card) > cardVersion(found))) found = card;
  }
  return found;
}
