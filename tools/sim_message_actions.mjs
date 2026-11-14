// Codigo React/normalizacao real, hooks e HTTP simulados; sem rede/ADC.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const requireFrontend = createRequire(new URL("../frontend/package.json", import.meta.url));
const { transformSync } = requireFrontend("esbuild");
let active, ctx, now = 1_800_000_000_000;
let timerId = 0;
const timers = new Map();
global.window = {
  setTimeout(fn, ms) { const id = ++timerId; timers.set(id, { fn, at: now + ms }); return id; },
  clearTimeout(id) { timers.delete(id); }, addEventListener() {}, removeEventListener() {},
};
global.requestAnimationFrame = (fn) => { fn(); return 1; };
global.cancelAnimationFrame = () => {};
const realNow = Date.now;
Date.now = () => now;
function advance(ms) {
  now += ms;
  for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.fn(); }
}
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: "Fragment" };
const react = { useState: (...a) => active.state(...a), useRef: (...a) => active.ref(...a), useEffect: (...a) => active.effect(...a) };
function harness(render) {
  const slots = [];
  let cursor, dirty = true, output, effects;
  const h = {
    state(initial) {
      const i = cursor++;
      if (!slots[i]) slots[i] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[i].value, (next) => { const v = typeof next === "function" ? next(slots[i].value) : next; if (!Object.is(v, slots[i].value)) { slots[i].value = v; dirty = true; } }];
    },
    ref(initial) { const i = cursor++; return slots[i] ||= { current: initial }; },
    effect(fn, deps) {
      const i = cursor++, previous = slots[i];
      if (!previous || !deps || deps.some((v, index) => !Object.is(v, previous.deps[index]))) effects.push({ i, fn, deps });
    },
    flush() {
      let count = 0;
      while (dirty) {
        assert.ok(++count < 50, "Sem loop de render");
        dirty = false; cursor = 0; effects = []; active = h;
        output = render(); active = null;
        for (const { i, fn, deps } of effects) { slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; }
      }
      return output;
    },
    rerender() { dirty = true; return h.flush(); },
    async settle() { for (let i = 0; i < 5; i++) { await new Promise(setImmediate); h.flush(); } return output; },
    unmount() { for (const s of slots) s?.cleanup?.(); },
    get out() { return output; },
  };
  h.flush(); return h;
}
function compile(path, mocks = {}) {
  const source = readFileSync(new URL(`../frontend/src/${path}`, import.meta.url), "utf8");
  const code = transformSync(source, { loader: path.endsWith("tsx") ? "tsx" : "ts", format: "cjs", jsx: "automatic" }).code;
  const module = { exports: {} };
  new Function("require", "module", "exports", code)((name) => {
    if (name in mocks) return mocks[name];
    if (name === "react") return react;
    if (name === "react/jsx-runtime") return jsx;
    throw Error(`Import nao simulado: ${name}`);
  }, module, module.exports);
  return module.exports;
}
const normal = compile("utils/normalization.ts");
const http = { calls: [], handler: async () => ({}), async call(method, _auth, path, body) { this.calls.push({ method, path, body }); return this.handler(method, path, body); } };
const actions = compile("components/chat/MessageActions.tsx", {
  "../../context/CrmContext": { useCrm: () => ctx },
  "../../api": Object.fromEntries(["sendJson", "getJson", "deleteJson"].map((name) => [name, (...a) => http.call(name, ...a)])),
  "../../utils/errors": { errorText: (e) => e.message }, "../../utils/normalization": normal,
  "../../utils/formatting": { messageContentLabel: (m) => m.content || "" },
  "../../utils/waFormat": { waPlainText: (v) => v }, "../../hooks/useClickOutside": { useClickOutside() {} },
});
function nodes(root, predicate) {
  if (root == null || typeof root !== "object") return [];
  if (Array.isArray(root)) return root.flatMap((n) => nodes(n, predicate));
  return [...(predicate(root) ? [root] : []), ...nodes(root.props?.children, predicate)];
}
const button = (root, label) => nodes(root, (n) => n.type === "button" && (n.props["aria-label"] === label || n.props.children === label))[0];
function reset() {
  http.calls = []; http.handler = async () => ({}); timers.clear();
  ctx = { readOnly: false, bundle: { auth: {} }, selectedThreadId: "one", selectedConversation: {},
    messagesRef: { current: { querySelector: () => null } }, scrollIntentRef: { current: "normal" },
    chatSearch: "", messages: [], setChatSearch(v) { this.chatSearch = v; }, setError(v) { this.error = v; }, setNotice(v) { this.notice = v; },
    sessionUser: { id: 7 }, conversations: [], meusConversations: [], contactsById: new Map(), pickerSearch: async () => ({ contacts: [] }),
  };
}
const message = { id: 1, direction: "inbound", msg_type: "text", content: "Primeira", timestamp_wa: "2026-01-01" };
assert.equal(normal.normalizeMessage({ id: 1, is_forwarded: true, latitude: 0, longitude: 1 }, "1").is_forwarded, true);
assert.equal(normal.normalizeMessage({ latitude: 0 }, "1").latitude, 0);
assert.equal(normal.normalizeConversation({ pinned_message: { message_id: 1, expires_at: { seconds: 1 }, preview: "Fixada" } }, "c").pinned_message.expires_at, "1970-01-01T00:00:01.000Z");
for (const direction of ["system", "internal"]) assert.equal(actions.canForwardMessage({ ...message, direction }), false);
assert.equal(actions.canForwardMessage({ ...message, visibility: "admin_only" }), false);
assert.equal(actions.canForwardMessage({ ...message, msg_type: "image", media_path: "" }), false);
assert.equal(actions.canForwardMessage({ ...message, msg_type: "location", latitude: 0, longitude: 0 }), true);

reset();
let h = harness(() => actions.useMessageActions());
h.out.startForward({ ...message, id: 2, timestamp_wa: "2026-02-01" }); h.flush();
h.out.toggleSelection(message); h.flush();
button(h.out.selectionBar, "Escolher destino do encaminhamento").props.onClick(); h.flush();
let picker = nodes(h.out.dialogs, (n) => n.type === actions.ForwardPicker)[0];
assert.deepEqual(picker.props.messageIds, [1, 2], "Encaminha em ordem cronologica");
picker.props.onSent([1]); h.flush();
assert.deepEqual([...h.out.selection.keys()], [2], "Falha parcial preserva somente as restantes");
ctx.selectedThreadId = "two"; h.rerender();
assert.equal(h.out.selection, null, "Troca de thread limpa selecao e modal");
h.out.startPin(message); h.flush();
http.handler = async () => ({ pinned_message: { message_id: 1, preview: "Fixada", expires_at: new Date(now + 30 * 86400_000).toISOString(), pinned_by: 7 } });
nodes(h.out.dialogs, (n) => n.type === actions.PinDurationDialog)[0].props.onPin(30); await h.settle();
assert.equal(http.calls.at(-1).body.duration_days, 30);
assert.ok(h.out.pinBar);
advance(25 * 86400_000); h.flush(); assert.ok(h.out.pinBar, "Pin de 30 dias nao expira no limite de 32 bits do timer");
http.handler = async () => ({ messages: [message] });
nodes(h.out.pinBar, (n) => n.props?.className === "pinned-message-preview")[0].props.onClick();
await h.settle();
assert.equal(h.out.historicalMessages[0].id, 1, "Busca fixada fora da janela carregada");
advance(5 * 86400_000); h.flush(); assert.equal(h.out.pinBar, null, "Pin some ao expirar");
h.unmount();

reset(); ctx.readOnly = true;
h = harness(() => actions.useMessageActions());
h.out.startForward(message); h.out.startPin(message); h.flush();
assert.equal(h.out.selection, null); assert.equal(http.calls.length, 0); h.unmount();

reset(); ctx.selectedConversation.pinned_message = { message_id: 1, preview: "Fixada", expires_at: new Date(now + 86400_000).toISOString() };
h = harness(() => actions.useMessageActions());
let resolveContext;
http.handler = () => new Promise((resolve) => { resolveContext = resolve; });
nodes(h.out.pinBar, (n) => n.props?.className === "pinned-message-preview")[0].props.onClick();
ctx.selectedThreadId = "other"; ctx.selectedConversation = {}; h.rerender();
resolveContext({ messages: [message] }); await h.settle();
assert.equal(h.out.historicalMessages, null, "Resposta atrasada nao reabre historico de outra thread"); h.unmount();

reset();
ctx.meusConversations = [{ id: "dest", contact_id: 2, assigned_to: 7, display_name: "Destino", channel_label: "Canal proprio" }];
const sent = [];
let ids = [1, 2], closed = false;
h = harness(() => actions.ForwardPicker({ messageIds: ids, onSent: (v) => { sent.push(...v); ids = ids.filter((id) => !v.includes(id)); }, onClose: () => { closed = true; } }));
nodes(h.out, (n) => n.props?.className?.includes("forward-destination"))[0].props.onClick(); h.flush();
http.handler = async (_method, _path, body) => { if (body.forward_message_id === 2) throw Error("Janela expirada"); return {}; };
button(h.out, "Encaminhar").props.onClick();
button(h.out, "Encaminhar").props.onClick(); // Segundo clique antes do render de busy.
await h.settle();
assert.deepEqual(sent, [1]); assert.equal(closed, false);
assert.deepEqual(http.calls.map((c) => c.body.forward_message_id), [1, 2]);
assert.ok(nodes(h.out, (n) => n.props?.role === "alert")[0].props.children.includes("restantes"));
http.handler = async () => ({});
button(h.out, "Encaminhar").props.onClick(); await h.settle();
assert.deepEqual(http.calls.map((c) => c.body.forward_message_id), [1, 2, 2], "Retry nao repete a mensagem confirmada");
assert.equal(closed, true); h.unmount();

reset();
ctx.conversations = [
  { id: "other", contact_id: 3, assigned_to: 8, display_name: "Busca outro", last_message_at: "2026-11-01" },
  { id: "mine", contact_id: 2, assigned_to: 7, display_name: "Busca meu", last_message_at: "2026-10-01" },
];
const searches = [];
ctx.pickerSearch = (q) => new Promise((resolve) => searches.push({ q, resolve }));
h = harness(() => actions.ForwardPicker({ messageIds: [1], onSent() {}, onClose() {} }));
const search = (q) => { nodes(h.out, (n) => n.type === "input")[0].props.onChange({ target: { value: q } }); h.flush(); advance(300); };
search("Busca");
assert.deepEqual(nodes(h.out, (n) => n.props?.className?.includes("forward-destination")).map((n) => n.props.children[0].props.children), ["Busca meu", "Busca outro"], "Meus atendimentos antes dos outros mesmo com recencia menor");
search("Novo");
searches[0].resolve({ contacts: [{ id: 99, display_name: "Resultado atrasado" }] }); await h.settle();
assert.equal(nodes(h.out, (n) => n.props?.className?.includes("forward-destination")).length, 0, "Busca antiga descartada");
searches[1].resolve({ contacts: [{ id: 20, display_name: "Novo contato", phone_formatted: "0000", channel_id: 4 }] }); await h.settle();
nodes(h.out, (n) => n.props?.className?.includes("forward-destination"))[0].props.onClick(); h.flush();
http.handler = async (_method, path) => path.endsWith("/open") ? { conversation_id: "opened-thread" } : {};
button(h.out, "Encaminhar").props.onClick(); await h.settle();
assert.deepEqual(http.calls.map((c) => c.path), ["/api/wa/conversation/open", "/api/wa/send"]);
assert.deepEqual(http.calls[0].body, { contact_id: 20, channel_id: 4 });
assert.equal(http.calls[1].body.conversation_id, "opened-thread");
assert.equal(ctx.selectedThreadId, "one", "Escolher destino nao muda a conversa de origem");
h.unmount();
Date.now = realNow;
console.log("OK: normalizacao, selecao, ordem, falha parcial/retry, busca/picker, clique duplo, pin/expiracao 30d, historico e somente leitura");
