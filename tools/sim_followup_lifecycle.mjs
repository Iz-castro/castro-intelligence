// Regressao local dos ciclos async de F1. Rode: node tools/sim_followup_lifecycle.mjs
// Usa o TSX real e esbuild ja instalado por npm ci em frontend; sem ADC/rede.
// Hooks, HTTP, contexto CRM e timers sao simulados. Nao substitui teste em navegador,
// React StrictMode, layout ou a autorizacao real do backend/Firestore.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const frontendRequire = createRequire(new URL("../frontend/package.json", import.meta.url));
const { transformSync } = frontendRequire("esbuild");
const sourceRoot = new URL("../frontend/src/features/followup/", import.meta.url);
let checks = 0;
function check(value, message) { assert.ok(value, message); checks++; }
class ApiError extends Error { constructor(status) { super(`HTTP ${status}`); this.status = status; } }

function harness(componentName) {
  const slots = [];
  const calls = [];
  const timers = new Map();
  let cursor = 0, dirty = true, pendingEffects = [], tree = null, timerId = 0;
  let signal = "initial-owner", changes = 0;
  const changedDeps = (previous, next) => !previous || !next || previous.length !== next.length || next.some((value, index) => !Object.is(value, previous[index]));
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
    useId() { return `synthetic-${cursor++}`; },
    useCallback(callback, deps) {
      const index = cursor++;
      if (changedDeps(slots[index]?.deps, deps)) slots[index] = { value: callback, deps };
      return slots[index].value;
    },
    useEffect(callback, deps) {
      const index = cursor++;
      if (changedDeps(slots[index]?.deps, deps)) pendingEffects.push({ index, callback, deps });
    },
  };
  const request = (url) => new Promise((resolve, reject) => {
    const call = { url, settled: false };
    call.resolve = (value) => { call.settled = true; resolve(value); };
    call.reject = (error) => { call.settled = true; reject(error); };
    calls.push(call);
  });
  const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
  let operationModule;
  const requireStub = (name) => {
    if (name === "react") return hooks;
    if (name === "react/jsx-runtime") return jsx;
    if (name === "../../api") return { getJson: (_auth, url) => request(url), ApiError };
    if (name === "./api") return {
      loadTask: () => request("task"), loadActivities: () => request("activities"),
      loadTasks: () => request("list"), actOnTask: () => request("action"),
    };
    if (name === "./useOperation") return operationModule;
    if (name === "./useAccessSignal") return { useAccessSignal: () => signal };
    if (name === "./time") return { formatMoment: (value) => String(value), localInput: () => "", scheduleProblem: () => "" };
    if (name === "./types") return { EVENT_LABELS: {}, RESULT_LABELS: {}, isCommercialBlocked: () => false, taskTypeLabel: () => "" };
    if (["./PreferenceEditor", "./ReadOnlyContext", "./TaskActionForm", "../../components/chat/WaText"].includes(name)) return {};
    throw new Error(`Import nao simulado: ${name}`);
  };
  function loadModule(fileName, loader) {
    const code = transformSync(readFileSync(new URL(fileName, sourceRoot), "utf8"), { loader, format: "cjs", jsx: "automatic" }).code;
    const sandbox = {
      module: { exports: {} }, require: requireStub, console,
      crypto: { randomUUID: () => "synthetic-operation-id" },
      document: { visibilityState: "visible" },
      window: {
        setInterval: (callback) => { const id = ++timerId; timers.set(id, callback); return id; },
        clearInterval: (id) => timers.delete(id),
      },
    };
    vm.runInNewContext(code, sandbox, { filename: fileName });
    return sandbox.module.exports;
  }
  operationModule = loadModule("useOperation.ts", "ts");
  const Component = loadModule(`${componentName}.tsx`, "tsx")[componentName];
  const props = componentName === "ReadOnlyContext" ? { auth: {}, contactId: 1 } : {
    auth: {}, taskId: "synthetic", settings: null, queues: [],
    onChanged: () => { changes++; }, onEdit: () => {}, onSelectTask: () => {}, onBack: () => {},
  };
  function flush() {
    let renders = 0;
    while (dirty) {
      assert.ok(++renders <= 40, "Loop de render/effect");
      dirty = false; cursor = 0; pendingEffects = [];
      tree = Component(props);
      const batch = pendingEffects;
      for (const effect of batch) slots[effect.index]?.cleanup?.();
      for (const effect of batch) slots[effect.index] = { deps: effect.deps, cleanup: effect.callback() };
    }
  }
  async function tick() { for (let index = 0; index < 12; index++) { await Promise.resolve(); flush(); } }
  function walk(predicate, node = tree) {
    if (!node || typeof node !== "object") return null;
    if (predicate(node)) return node;
    const children = node.props?.children;
    for (const child of Array.isArray(children) ? children : [children]) {
      if (!child || typeof child !== "object") continue;
      const found = walk(predicate, child); if (found) return found;
    }
    return null;
  }
  return {
    calls, props, timers, flush, tick, walk,
    shown: (text) => JSON.stringify(tree).includes(text),
    setSignal: (next) => { signal = next; dirty = true; flush(); },
    switchContact: (id) => { props.contactId = id; dirty = true; flush(); },
    changes: () => changes,
    unmount: () => { for (const slot of slots) slot?.cleanup?.(); },
  };
}

async function readonlyDeniedThenLateMessage() {
  const h = harness("ReadOnlyContext");
  try {
    h.flush(); check(h.calls.length === 1, "Uma consulta inicial de contexto");
    h.calls[0].resolve({ conversations: [{ id: "thread_1" }] }); await h.tick();
    const oldMessages = h.calls.find((call) => call.url.includes("/messages?"));
    const validation = h.calls.find((call) => call.url.includes("/context?"));
    check(oldMessages && validation, "Mensagens e validacao pendentes");
    validation.reject(new ApiError(403)); await h.tick();
    oldMessages.resolve({ messages: [{ id: "late", content: "SYNTHETIC_LATE_MESSAGE" }] }); await h.tick();
    check(!h.shown("SYNTHETIC_LATE_MESSAGE"), "Resposta anterior nao ressuscita mensagem depois do 403");
    check(h.calls.length === 3, "403 nao dispara loop de requests");
  } finally { h.unmount(); }
}

async function readonlyRefreshAndContactSwitch() {
  const h = harness("ReadOnlyContext");
  async function finish(thread, label) {
    const message = h.calls.findLast((call) => call.url.includes("/messages?") && call.url.includes(encodeURIComponent(thread)));
    check(message, `Mensagens consultadas para ${thread}`);
    message.resolve({ messages: [{ id: label, content: label }] });
    for (const call of h.calls.filter((item) => !item.settled && item.url.includes("/context?"))) call.resolve({ conversations: [{ id: thread }] });
    await h.tick(); check(h.shown(label), `Contexto exibe ${label}`);
  }
  try {
    h.flush(); h.calls[0].resolve({ conversations: [{ id: "thread_1" }] }); await h.tick();
    await finish("thread_1", "SYNTHETIC_INITIAL");
    const refresh = h.walk((node) => node.type === "button" && node.props.children === "Atualizar contexto");
    check(refresh, "Atualizar contexto existe");
    const beforeReload = h.calls.length;
    refresh.props.onClick(); h.flush();
    const reloadContext = h.calls.slice(beforeReload).find((call) => call.url.includes("/context"));
    check(reloadContext, "Atualizar consulta contexto novo");
    reloadContext.resolve({ conversations: [{ id: "thread_refreshed" }] }); await h.tick();
    await finish("thread_refreshed", "SYNTHETIC_REFRESHED");
    const beforeSwitch = h.calls.length;
    h.switchContact(2);
    const switchedContext = h.calls.slice(beforeSwitch).find((call) => call.url.includes("/contacts/2/context"));
    check(switchedContext, "Troca de contato consulta contexto novo");
    switchedContext.resolve({ conversations: [{ id: "thread_2" }] }); await h.tick();
    await finish("thread_2", "SYNTHETIC_CONTACT2");
    check(!h.shown("SYNTHETIC_INITIAL") && !h.shown("SYNTHETIC_REFRESHED"), "Contato anterior nao permanece visivel");
    check(h.calls.length === 9, "Atualizar e trocar contato nao causam loop");
  } finally { h.unmount(); }
}

const syntheticTask = {
  id: "synthetic", contact_id: 1, status: "pending", version: 1,
  title: "SYNTHETIC_TASK", description: "SYNTHETIC_DESCRIPTION", due_at: "2030-10-01T12:00:00Z",
  queue_key: "reception", assignment_mode: "queue", can_modify: true, type: "retorno", contact_purpose: "commercial",
};
function resolveLateHistory(h) {
  h.calls.find((call) => call.url === "activities").resolve({ items: [{ id: "late", event_type: "task_created", data: { reason: "SYNTHETIC_HISTORY" } }] });
  h.calls.find((call) => call.url === "list").resolve({ items: [syntheticTask] });
}

async function transferDuringPoll() {
  const h = harness("TaskDetail");
  try {
    h.flush(); h.calls[0].resolve(syntheticTask); await h.tick();
    check(h.shown("SYNTHETIC_TASK"), "Tarefa inicialmente visivel");
    [...h.timers.values()][0](); await h.tick();
    const oldPoll = h.calls.filter((call) => call.url === "task")[1];
    h.setSignal("transferred-owner");
    check(h.walk((node) => node.props?.hidden === true), "Transferencia oculta detalhe imediatamente mesmo com poll pendente");
    const newPoll = h.calls.filter((call) => call.url === "task")[2];
    check(newPoll, "Transferencia nao perde nova validacao por poll anterior");
    newPoll.reject(new ApiError(403)); await h.tick();
    oldPoll.resolve(syntheticTask); resolveLateHistory(h); await h.tick();
    check(!h.shown("SYNTHETIC_"), "Poll e historico antigos nao ressuscitam dados apos transferencia/403");
    check(h.calls.length === 5 && h.changes() === 1, "Invalidacao unica, sem loop");
  } finally { h.unmount(); }
}

async function actionDeniedThenLateHistory() {
  const h = harness("TaskDetail");
  try {
    h.flush(); h.calls[0].resolve(syntheticTask); await h.tick();
    const take = h.walk((node) => node.type === "button" && node.props.children === "Pegar tarefa");
    check(take, "Acao de pegar tarefa disponivel"); take.props.onClick(); h.flush();
    const action = h.calls.find((call) => call.url === "action");
    check(action, "Acao consulta API"); action.reject(new ApiError(403)); await h.tick();
    check(!h.shown("SYNTHETIC_TASK"), "403 de acao limpa tarefa imediatamente");
    resolveLateHistory(h); await h.tick();
    check(!h.shown("SYNTHETIC_"), "Historico em voo nao repoe dados depois de acao403");
    check(h.calls.length === 4 && h.changes() === 1, "Acao403 invalida uma unica vez");
  } finally { h.unmount(); }
}

await readonlyDeniedThenLateMessage();
await readonlyRefreshAndContactSwitch();
await transferDuringPoll();
await actionDeniedThenLateHistory();
console.log(`Follow-up lifecycle: ${checks} checks passed (4 scenarios; mocked hooks/HTTP; no network).`);
