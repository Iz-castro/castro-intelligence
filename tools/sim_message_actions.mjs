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
    sessionUser: { id: 7, firebase_uid: "uid7" }, conversations: [], meusConversations: [], novosConversations: [], equipeConversations: [],
    botConversations: [], nqConversations: [], canSeeAll: false, selectedContact: null,
    channels: [{ id: 4, channel_type: "standard", label: "Empresa", display_phone_number: "+55 31 4000-0000", is_active: true }],
    contactsById: new Map(), pickerSearch: async () => ({ contacts: [] }),
  };
}
const pinPreview = (out) => nodes(out.pinBar, (n) => n.props?.className === "pinned-message-preview")[0];
const destinations = (out) => nodes(out, (n) => n.props?.className?.includes("forward-destination"));
const destinationNames = (out) => destinations(out).map((n) => n.props.children[0].props.children);
const settleNoRender = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };
const message = { id: 1, direction: "inbound", msg_type: "text", content: "Primeira", timestamp_wa: "2026-01-01" };
assert.equal(normal.normalizeMessage({ id: 1, is_forwarded: true, latitude: 0, longitude: 1 }, "1").is_forwarded, true);
assert.equal(normal.normalizeMessage({ latitude: 0 }, "1").latitude, 0);
assert.equal(normal.normalizeConversation({ pinned_message: { message_id: 1, expires_at: { seconds: 1 }, preview: "Fixada" } }, "c").pinned_message.expires_at, "1970-01-01T00:00:01.000Z");
for (const direction of ["system", "internal"]) assert.equal(actions.canForwardMessage({ ...message, direction }), false);
assert.equal(actions.canForwardMessage({ ...message, visibility: "admin_only" }), false);
assert.equal(actions.canForwardMessage({ ...message, msg_type: "image", media_path: "" }), false);
assert.equal(actions.canForwardMessage({ ...message, msg_type: "location", latitude: 0, longitude: 0 }), true);
// Template guarda o rotulo interno com dados de quem recebeu; toque em botao, o id do botao.
assert.equal(actions.canForwardMessage({ ...message, msg_type: "template", content: "[template: x] Maria" }), false);
assert.equal(actions.canPinMessage({ ...message, msg_type: "template", content: "[template: x] Maria" }), true, "Fixar template continua");
assert.equal(actions.canForwardMessage({ ...message, interactive_reply: true, content: "lgpd_aceitar" }), false);
assert.equal(actions.canForwardMessage({ ...message, is_rating_message: true }), false);
const raw = normal.normalizeMessage({ id: 3, interactive_reply: true, is_rating_message: true }, "3");
assert.equal(raw.interactive_reply, true); assert.equal(raw.is_rating_message, true);
// Origem estrita (espelha o backend): thread que atendo ou pool de verdade.
const me = { id: 7, firebase_uid: "uid7" };
assert.equal(actions.canActOnThread({ assigned_to: 7 }, null, me, false), true);
assert.equal(actions.canActOnThread({ assigned_to_uid: "uid7" }, null, me, false), true);
assert.equal(actions.canActOnThread({}, { assigned_to: null }, me, false), true, "Pool sem dono");
assert.equal(actions.canActOnThread({}, { assigned_to: 9 }, me, false), false, "Orfa de lead alheio nao e pool");
assert.equal(actions.canActOnThread({ assigned_to: 9, assigned_to_uid: "uid9" }, { assigned_to: 7 }, me, false), false, "Coex de colega com lead meu");
assert.equal(actions.canActOnThread({ assigned_to: 9 }, { assigned_to: 9 }, me, true), true, "Gestao com ver_todos_leads");
assert.equal(actions.canActOnThread({ assigned_to: 7, is_backup: true }, null, me, false), false);

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
ctx.channels = [
  { id: 4, channel_type: "standard", label: "Empresa", display_phone_number: "+55 31 4000-0000", is_active: true },
  { id: 5, channel_type: "coexistence", label: "Meu coex", display_phone_number: "+55 31 9555-0000", owner_user_id: 7, is_active: true },
  { id: 9, channel_type: "coexistence", label: "Coex colega", display_phone_number: "+55 31 9999-0000", owner_user_id: 8, is_active: true },
];
ctx.contactsById = new Map([[2, { id: 2, display_name: "Busca meu" }], [3, { id: 3, display_name: "Busca pool" }]]);
ctx.meusConversations = [
  { id: "mine", contact_id: 2, assigned_to: 7, channel_id: 4, last_message_at: "2026-10-01" },
  { id: "mine-coex-colega", contact_id: 2, assigned_to: 7, channel_id: 9, channel_type: "coexistence", last_message_at: "2026-11-02" },
];
ctx.novosConversations = [{ id: "pool", contact_id: 3, channel_id: 4, last_message_at: "2026-11-01" }];
// Camada crua do listener: thread orfa de lead alheio (contato inacessivel) — nunca vira destino.
ctx.conversations = [{ id: "orfa", contact_id: 4, wa_id: "5531977776666", channel_id: 4, last_message_at: "2026-11-03" }];
const searches = [];
ctx.pickerSearch = (q) => new Promise((resolve) => searches.push({ q, resolve }));
h = harness(() => actions.ForwardPicker({ messageIds: [1], onSent() {}, onClose() {} }));
const search = (q) => { nodes(h.out, (n) => n.type === "input")[0].props.onChange({ target: { value: q } }); h.flush(); advance(300); };
assert.deepEqual(destinationNames(h.out), ["Busca meu"], "Sem busca: so os proprios, sem thread pelo coex de colega");
search("B");
assert.deepEqual(destinationNames(h.out), ["Busca meu"], "1 caractere filtra so os proprios (pool exige 2)");
search("Busca");
assert.deepEqual(destinationNames(h.out), ["Busca meu", "Busca pool"], "Meus atendimentos antes da pool mesmo com recencia menor");
search("55319");
assert.ok(!destinationNames(h.out).some((name) => String(name).includes("5531977776666")), "Telefone de orfa alheia nao aparece");
search("Novo");
searches[0].resolve({ contacts: [{ id: 99, display_name: "Resultado atrasado" }] }); await h.settle();
assert.equal(destinations(h.out).length, 0, "Busca antiga descartada");
searches.at(-1).resolve({ contacts: [
  { id: 20, display_name: "Novo contato", phone_formatted: "0000", channel_id: 4 },
  { id: 21, display_name: "Novo do coex colega", phone_formatted: "1111", channel_id: 9 },
  { id: 22, display_name: "Novo do meu coex", phone_formatted: "2222", channel_id: 5 },
] }); await h.settle();
const details = destinations(h.out).map((n) => n.props.children[1].props.children);
assert.ok(details[1].includes("Sai por Empresa"), `Canal de criacao no coex alheio sai pelo numero da empresa: ${details[1]}`);
assert.ok(details[2].includes("Sai por Meu coex"), details[2]);
destinations(h.out)[1].props.onClick(); h.flush();
http.handler = async (_method, path) => path.endsWith("/open") ? { conversation_id: "opened-thread" } : {};
button(h.out, "Encaminhar").props.onClick(); await h.settle();
assert.deepEqual(http.calls.map((c) => c.path), ["/api/wa/conversation/open", "/api/wa/send"]);
assert.deepEqual(http.calls[0].body, { contact_id: 21, channel_id: 4 }, "Nunca abre pelo coex de outra pessoa");
assert.equal(http.calls[1].body.conversation_id, "opened-thread");
assert.equal(ctx.selectedThreadId, "one", "Escolher destino nao muda a conversa de origem");
h.unmount();

// Trecho da fixada: recencia da THREAD mudou (cliente respondeu / operador enviou)
// ou busca digitada voltam as recentes. O fim de ctx.messages nao decide: o 1o
// snapshot pode chegar depois do /context e cliques admin_only nao aparecem.
reset(); ctx.selectedConversation.pinned_message = { message_id: 1, preview: "Fixada", expires_at: new Date(now + 86400_000).toISOString() };
ctx.selectedConversation.last_message_at = "2026-11-13T10:00:00.000Z";
h = harness(() => actions.useMessageActions());
http.handler = async () => ({ messages: [message] });
pinPreview(h.out).props.onClick(); await h.settle();
assert.ok(h.out.historicalMessages, "Abre o trecho antes do 1o snapshot");
ctx.messages = [{ id: 40 }, { id: 50 }]; h.rerender(); await h.settle();
assert.ok(h.out.historicalMessages, "Snapshot inicial (mensagens antigas) nao tira do trecho");
ctx.messages = [{ id: 40 }, { id: 50 }, { id: 60, visibility: "admin_only" }]; h.rerender(); await h.settle();
assert.ok(h.out.historicalMessages, "Clique admin_only (sem recencia) nao tira do trecho");
ctx.selectedConversation = { ...ctx.selectedConversation, last_message_at: "2026-11-13T10:05:00.000Z" }; h.rerender(); await h.settle();
assert.equal(h.out.historicalMessages, null, "Mensagem nova na thread sai do trecho");
assert.ok(String(ctx.notice).includes("Conversa atualizada"));
pinPreview(h.out).props.onClick(); await h.settle();
assert.ok(h.out.historicalMessages);
ctx.chatSearch = "boleto"; h.rerender(); await h.settle();
assert.equal(h.out.historicalMessages, null, "Busca digitada vale para as recentes");
h.unmount();

// Fora do escopo estrito (thread de colega) o /context responde 403: nao chama.
reset(); ctx.selectedConversation = { assigned_to: 9, assigned_to_uid: "uid9",
  pinned_message: { message_id: 1, preview: "Fixada", expires_at: new Date(now + 86400_000).toISOString() } };
ctx.selectedContact = { assigned_to: 7 };
h = harness(() => actions.useMessageActions());
assert.equal(h.out.canAct, false);
pinPreview(h.out).props.onClick(); await h.settle();
assert.equal(http.calls.length, 0, "Sem /context fora do escopo");
assert.ok(String(ctx.notice).includes("Role a conversa"));
h.unmount();

// /api/admin/channels falhou na carga (lista vazia): o picker busca de novo e,
// enquanto nao sabe os numeros, linha de contato fica desabilitada.
reset(); ctx.channels = [];
let resolveChannels;
http.handler = (_method, path) => path === "/api/admin/channels" ? new Promise((resolve) => { resolveChannels = resolve; }) : Promise.resolve({});
const channelSearches = [];
ctx.pickerSearch = (q) => new Promise((resolve) => channelSearches.push({ q, resolve }));
h = harness(() => actions.ForwardPicker({ messageIds: [1], onSent() {}, onClose() {} }));
assert.equal(http.calls[0].path, "/api/admin/channels");
nodes(h.out, (n) => n.type === "input")[0].props.onChange({ target: { value: "Cliente" } }); h.flush(); advance(300);
channelSearches[0].resolve({ contacts: [{ id: 30, display_name: "Cliente novo", phone_formatted: "3333", channel_id: 9 }] }); await h.settle();
assert.equal(destinations(h.out)[0].props.disabled, true, "Sem numeros conhecidos a linha de contato fica desabilitada");
resolveChannels({ channels: [{ id: 4, channel_type: "standard", label: "Empresa", display_phone_number: "+55 31 4000-0000", is_active: true }] }); await h.settle();
assert.equal(destinations(h.out)[0].props.disabled, false);
assert.ok(destinations(h.out)[0].props.children[1].props.children.includes("Sai por Empresa"));
h.unmount();

// Falha no /context desarma o salto: o lote com a fixada chegando depois nao rola sozinho.
reset(); ctx.selectedConversation.pinned_message = { message_id: 1, preview: "Fixada", expires_at: new Date(now + 86400_000).toISOString() };
h = harness(() => actions.useMessageActions());
http.handler = async () => { throw Error("503 tente de novo"); };
pinPreview(h.out).props.onClick(); await h.settle();
assert.equal(ctx.error, "503 tente de novo");
let scrolled = false;
ctx.messagesRef.current = { querySelector: () => ({ scrollIntoView() { scrolled = true; } }) };
ctx.messages = [message]; h.rerender(); await h.settle();
assert.equal(scrolled, false, "pendingJump desarmado apos a falha");
h.unmount();

// Fixada ja carregada mas escondida pela busca: limpa a busca e rola, sem chamar /context.
reset(); ctx.selectedConversation.pinned_message = { message_id: 1, preview: "Fixada", expires_at: new Date(now + 86400_000).toISOString() };
ctx.messages = [message]; ctx.chatSearch = "boleto";
h = harness(() => actions.useMessageActions());
pinPreview(h.out).props.onClick(); h.flush();
ctx.messagesRef.current = { querySelector: () => ({ scrollIntoView() { scrolled = true; } }) };
scrolled = false; h.rerender(); await h.settle();
assert.equal(ctx.chatSearch, ""); assert.equal(scrolled, true); assert.equal(http.calls.length, 0, "Sem /context para mensagem ja carregada");
h.unmount();

// Erro do fixar aparece dentro do dialogo (o alerta global ficava atras do fundo escuro).
reset();
h = harness(() => actions.useMessageActions());
h.out.startPin(message); h.flush();
http.handler = async () => { throw Error("Sem permissão para fixar"); };
nodes(h.out.dialogs, (n) => n.type === actions.PinDurationDialog)[0].props.onPin(7); await h.settle();
assert.equal(nodes(h.out.dialogs, (n) => n.type === actions.PinDurationDialog)[0].props.error, "Sem permissão para fixar");
assert.equal(ctx.error, undefined);
h.unmount();

// Lote interrompido pela troca de conversa avisa quantas sairam.
reset(); ctx.meusConversations = [{ id: "dest", contact_id: 2, assigned_to: 7, display_name: "Destino" }];
let releaseSecond;
http.handler = (_method, _path, body) => body?.forward_message_id === 1 ? Promise.resolve({}) : new Promise((resolve) => { releaseSecond = resolve; });
h = harness(() => actions.ForwardPicker({ messageIds: [1, 2, 3], onSent() {}, onClose() {} }));
destinations(h.out)[0].props.onClick(); h.flush();
button(h.out, "Encaminhar").props.onClick(); await h.settle();
h.unmount();
releaseSecond({}); await settleNoRender();
assert.ok(String(ctx.notice).includes("interrompido") && String(ctx.notice).includes("2 de 3"), ctx.notice);
Date.now = realNow;
console.log("OK: normalizacao, selecao, ordem, falha parcial/retry, busca/picker (sem orfa alheia, sem coex alheio, canal de saida), "
  + "clique duplo, pin/expiracao 30d, trecho da fixada (mensagem nova/busca/falha), erro no dialogo, lote interrompido e somente leitura");
