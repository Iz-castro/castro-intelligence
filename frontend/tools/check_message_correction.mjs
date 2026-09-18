// Gate offline da correcao de mensagens. Uso: node tools/check_message_correction.mjs
// Extrai as funcoes reais por AST; cada render captura seu proprio estado, como
// no React, enquanto refs e setters permanecem compartilhados. Nao monta o DOM.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { setImmediate } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import ts from "typescript";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const parse = (path) => ts.createSourceFile(path, readFileSync(resolve(frontend, path), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const context = parse("src/context/CrmContext.tsx");
const app = parse("src/App.tsx");
const provider = context.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === "CrmProvider");
assert.ok(provider?.body, "CrmProvider deve existir");
const names = [
  "buildReplyPayload", "buildSendTarget", "startReplyToMessage", "cancelReply",
  "sendTextMessage", "sendInternalNote", "submitText", "handleDraftKeyDown",
  "closeQuickSuggestions", "handlePrimaryAction", "startCorrection",
  "cancelCorrection", "correctMessage", "startRecording", "discardRecording",
  "clearRecordingTimer", "releaseAudioStream",
];
const functions = names.map((name) => {
  const node = provider.body.statements.find((item) => ts.isFunctionDeclaration(item) && item.name?.text === name);
  assert.ok(node, `Funcao real ausente: ${name}`);
  return node.getText(context);
});
const derived = ["hasDraft", "busyComposerAction"].map((name) => {
  const node = provider.body.statements.filter(ts.isVariableStatement)
    .flatMap((item) => [...item.declarationList.declarations])
    .find((item) => ts.isIdentifier(item.name) && item.name.text === name);
  assert.ok(node, `Estado derivado ausente: ${name}`);
  return `const ${node.getText(context)};`;
});
const selectionEffects = provider.body.statements.filter(ts.isExpressionStatement)
  .map((node) => node.expression)
  .filter((node) => ts.isCallExpression(node) && node.expression.getText(context) === "useEffect")
  .filter((node) => node.arguments[0]?.getText(context).includes("correctionTargetRef.current")
    && node.arguments[0]?.getText(context).includes("setCorrectionTarget"));
assert.equal(selectionEffects.length, 1, "Deve existir um efeito que cancela correcao ao trocar a thread");
assert.equal(selectionEffects[0].arguments[1].getText(context), "[selectedThreadId]");
const extracted = ts.transpileModule([
  ...derived, ...functions,
  `const runSelectionEffect = ${selectionEffects[0].arguments[0].getText(context)};`,
].join("\n"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText;
// with fornece apenas o ambiente do provider; nenhum corpo de funcao e reescrito.
const instantiate = new Function("scope", `with (scope) { ${extracted}\nreturn { ${names.join(", ")}, runSelectionEffect }; }`);

const helpers = await build({
  stdin: {
    contents: 'export { buildMessageReplyReference } from "./src/utils/formatting"; export { errorText } from "./src/utils/errors";',
    resolveDir: frontend, loader: "ts",
  },
  bundle: true, write: false, format: "esm", platform: "node", logLevel: "silent",
});
const realHelpers = await import(`data:text/javascript;base64,${Buffer.from(helpers.outputFiles[0].text).toString("base64")}`);
const original = {
  id: 31, contact_id: 7, conversation_id: "standard__fixture", channel_id: 1,
  direction: "outbound", msg_type: "text", content: "Texto original", operator_id: 1,
};

function harness(overrides = {}) {
  const state = {
    bundle: { auth: {} }, selectedContact: { id: 7 }, selectedContactId: 7,
    selectedThreadId: original.conversation_id, draft: "", correctionTarget: null,
    replyTarget: null, internalMode: false, showAttachMenu: false,
    quickSuggestions: [], quickSelectedIndex: -1,
    busySend: false, busyAudio: false, busyUpload: false, recording: false, recordingSeconds: 0,
    snapshotMode: true, error: "", notice: "", messages: [{ ...original }],
    userSettings: { chat_prefix_enabled: true, chat_prefix_name: "Operador" },
    systemSettings: { chat_prefix_roles: ["operator"] }, sessionUser: { role: "operator" },
    ...overrides,
  };
  const calls = [];
  const counters = { focus: 0, refresh: 0, record: 0, recorders: 0, sendAudio: 0, trackStops: 0, timers: 0 };
  const refs = {
    correctionTargetRef: { current: null }, correctionInFlightRef: { current: false },
    mediaRecorderRef: { current: null }, mediaStreamRef: { current: null },
    recordingRequestRef: { current: null }, recordingTimerRef: { current: null }, audioChunksRef: { current: [] },
  };
  const stream = { getTracks: () => [{ stop() { counters.trackStops += 1; } }] };
  let getMedia = async () => stream;
  class FakeMediaRecorder {
    constructor() { counters.recorders += 1; this.state = "inactive"; }
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.onstop?.(); }
  }
  let respond = async () => ({ corrected_message_id: original.id, new_message_id: 32 });
  const setters = Object.fromEntries(Object.keys(state).map((key) => [
    `set${key[0].toUpperCase()}${key.slice(1)}`,
    (value) => { state[key] = typeof value === "function" ? value(state[key]) : value; },
  ]));
  function render() {
    return instantiate({
      ...state, ...setters, ...refs, ...realHelpers,
      composerInputRef: { current: { focus: () => { counters.focus += 1; } } },
      requestAnimationFrame: (callback) => callback(),
      sendJson: async (auth, path, body) => { calls.push({ path, body }); return respond(auth, path, body); },
      refreshPollingViews: async () => { counters.refresh += 1; },
      navigator: { mediaDevices: { getUserMedia: () => { counters.record += 1; return getMedia(); } } },
      MediaRecorder: FakeMediaRecorder,
      window: {
        MediaRecorder: FakeMediaRecorder,
        setInterval: () => { counters.timers += 1; return counters.timers; },
        clearInterval: () => { counters.timers -= 1; },
      },
      sendRecordedAudio: async () => { counters.sendAudio += 1; },
      applyQuickMessage: () => assert.fail("Sugestoes nao devem interceptar a correcao"),
      wrapDraftSelection: () => assert.fail("Formatacao nao deve interceptar Enter"),
    });
  }
  function select(threadId, contactId = 7) {
    state.selectedThreadId = threadId;
    state.selectedContactId = contactId;
    state.selectedContact = contactId == null ? null : { id: contactId };
    render().runSelectionEffect();
  }
  function start(text = "Texto corrigido") {
    render().startCorrection(original);
    assert.equal(state.correctionTarget, original);
    state.draft = text;
    return render();
  }
  return {
    state, calls, counters, refs, render, select, start, stream,
    respond: (callback) => { respond = callback; }, media: (callback) => { getMedia = callback; },
  };
}

function event(overrides = {}) {
  return {
    key: "Enter", shiftKey: false, ctrlKey: false, metaKey: false, altKey: false,
    prevented: false, preventDefault() { this.prevented = true; }, ...overrides,
  };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function findNodes(source, predicate) {
  const found = [];
  function visit(node) { if (predicate(node)) found.push(node); ts.forEachChild(node, visit); }
  visit(source);
  return found;
}
function attribute(node, name) {
  return node.attributes.properties.find((item) => ts.isJsxAttribute(item) && item.name.getText(app) === name)?.initializer;
}

const tests = [];
const test = (name, run) => tests.push({ name, run });

test("App conecta formulario, teclado e botao aos handlers do provider", () => {
  const nodes = findNodes(app, (node) => ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node));
  const form = nodes.find((node) => node.tagName.getText(app) === "form" && attribute(node, "className")?.text === "composer");
  assert.ok(form);
  assert.equal(attribute(form, "onSubmit")?.expression?.getText(app), "submitText");
  const keyboard = nodes.find((node) => node.tagName.getText(app) === "textarea" && attribute(node, "onKeyDown")?.expression?.getText(app) === "handleDraftKeyDown");
  assert.ok(keyboard);
  const button = nodes.find((node) => node.tagName.getText(app) === "button" && attribute(node, "className")?.getText(app).includes("mic-trigger"));
  assert.ok(button);
  assert.equal(attribute(button, "onClick")?.expression?.getText(app), "handlePrimaryAction");
});

test("iniciar correcao limpa resposta, menus e modo interno e preenche o original", () => {
  const h = harness({ replyTarget: { message_id: 99 }, internalMode: true, showAttachMenu: true, quickSuggestions: [{ message: "Atalho" }], quickSelectedIndex: 0 });
  h.render().startCorrection(original);
  assert.equal(h.state.draft, original.content);
  assert.equal(h.state.correctionTarget, original);
  assert.equal(h.state.replyTarget, null);
  assert.equal(h.state.internalMode, false);
  assert.equal(h.state.showAttachMenu, false);
  assert.deepEqual(h.state.quickSuggestions, []);
  assert.equal(h.state.quickSelectedIndex, -1);
  assert.ok(h.counters.focus > 0);
});

for (const method of ["handleDraftKeyDown", "handlePrimaryAction", "submitText"]) {
  test(`${method} envia uma correcao sem prefixo ou payload de resposta antigo`, async () => {
    const h = harness({ replyTarget: { message_id: 99 }, snapshotMode: false });
    const handlers = h.start("  Novo valor  ");
    const e = event();
    await handlers[method](e);
    await setImmediate();
    assert.deepEqual(h.calls, [{ path: "/api/wa/correct-message", body: { message_id: original.id, new_content: "Novo valor" } }]);
    assert.equal(h.state.correctionTarget, null);
    assert.equal(h.state.draft, "");
    assert.equal(h.state.replyTarget, null);
    assert.equal(h.state.messages[0].is_corrected, true);
    assert.equal(h.state.messages[0].corrected_by_message_id, 32);
    assert.equal(h.state.busySend, false);
    assert.equal(h.counters.refresh, 1);
    assert.equal(h.counters.record, 0);
    if (method !== "handlePrimaryAction") assert.equal(e.prevented, true);
  });
}

test("Shift+Enter mantem a correcao aberta sem enviar", async () => {
  const h = harness();
  const e = event({ shiftKey: true });
  h.start().handleDraftKeyDown(e);
  await setImmediate();
  assert.equal(e.prevented, false);
  assert.equal(h.calls.length, 0);
  assert.equal(h.state.correctionTarget, original);
});

test("correcao vazia nao envia texto nem inicia gravacao", async () => {
  const h = harness();
  const handlers = h.start(" \n ");
  handlers.handlePrimaryAction();
  handlers.handleDraftKeyDown(event());
  await handlers.submitText(event());
  assert.equal(await handlers.correctMessage(original.id, "   "), false);
  assert.equal(h.calls.length, 0);
  assert.equal(h.counters.record, 0);
  assert.equal(h.state.correctionTarget, original);
});

for (const busy of ["busySend", "busyAudio", "busyUpload", "recording"]) {
  test(`iniciar correcao durante ${busy} preserva o composer`, () => {
    const h = harness({ [busy]: true, draft: "Rascunho preservado" });
    h.render().startCorrection(original);
    assert.equal(h.state.correctionTarget, null);
    assert.equal(h.state.draft, "Rascunho preservado");
  });
}

test("mensagem de outro contato ou canal nao inicia correcao", () => {
  for (const target of [{ ...original, contact_id: 8 }, { ...original, conversation_id: "coex__fixture" }]) {
    const h = harness({ draft: "Rascunho preservado" });
    h.render().startCorrection(target);
    assert.equal(h.state.correctionTarget, null);
    assert.equal(h.state.draft, "Rascunho preservado");
  }
});

test("corrigir id diferente do alvo selecionado nao chama API", async () => {
  const h = harness();
  assert.equal(await h.start().correctMessage(999, "Outro texto"), false);
  assert.equal(h.calls.length, 0);
});

test("responder a outra mensagem cancela correcao e permite envio normal com citacao", async () => {
  const h = harness();
  h.start().startReplyToMessage({ ...original, id: 40, direction: "inbound", content: "Pergunta" });
  assert.equal(h.state.correctionTarget, null);
  assert.equal(h.state.draft, "");
  assert.equal(h.state.replyTarget.message_id, 40);
  h.state.draft = "Resposta";
  await h.render().sendTextMessage();
  assert.deepEqual(h.calls, [{ path: "/api/wa/send", body: {
    conversation_id: original.conversation_id, content: "Operador: Resposta",
    reply_to_message_id: 40, reply_to_preview: "Pergunta", reply_to_sender_name: "Cliente",
  } }]);
});

test("cancelar correcao limpa seu texto e permite nova mensagem", async () => {
  const h = harness();
  h.start().cancelCorrection();
  assert.equal(h.state.correctionTarget, null);
  assert.equal(h.state.draft, "");
  h.state.draft = "Mensagem nova";
  await h.render().submitText(event());
  assert.equal(h.calls[0].path, "/api/wa/send");
  assert.equal(h.calls[0].body.content, "Operador: Mensagem nova");
});

test("erro preserva alvo e texto, libera envio e permite tentar novamente", async () => {
  const h = harness();
  h.respond(async () => { throw new Error("Falha de teste"); });
  const handlers = h.start("Texto para tentar novamente");
  assert.equal(await handlers.correctMessage(original.id, h.state.draft), false);
  assert.equal(h.state.error, "Falha de teste");
  assert.equal(h.state.correctionTarget, original);
  assert.equal(h.state.draft, "Texto para tentar novamente");
  assert.equal(h.state.messages[0].is_corrected, undefined);
  assert.equal(h.state.busySend, false);
  h.respond(async () => ({ corrected_message_id: original.id, new_message_id: 33 }));
  assert.equal(await h.render().correctMessage(original.id, h.state.draft), true);
  assert.equal(h.calls.length, 2);
  assert.equal(h.state.error, "");
  assert.equal(h.state.draft, "");
  assert.equal(h.state.messages[0].corrected_by_message_id, 33);
});

test("Enter e clique no mesmo render disparam apenas uma requisicao", async () => {
  const h = harness();
  const pending = deferred();
  h.respond(() => pending.promise);
  const handlers = h.start();
  handlers.handleDraftKeyDown(event());
  handlers.handlePrimaryAction();
  const submission = handlers.submitText(event());
  assert.equal(h.calls.length, 1);
  assert.equal(h.state.busySend, true);
  handlers.startReplyToMessage({ ...original, id: 40 });
  assert.equal(h.state.replyTarget, null);
  pending.resolve({ corrected_message_id: original.id, new_message_id: 32 });
  await submission;
  await setImmediate();
  assert.equal(h.state.busySend, false);
  assert.equal(h.state.correctionTarget, null);
});

for (const destination of ["coex__fixture", null]) {
  test(`troca de thread para ${destination} cancela a correcao e limpa seu texto`, () => {
    const h = harness();
    h.start();
    h.select(destination, destination == null ? null : 7);
    assert.equal(h.state.correctionTarget, null);
    assert.equal(h.state.draft, "");
  });
}

for (const outcome of ["success", "failure"]) {
  test(`resposta tardia (${outcome}) preserva composer da nova conversa`, async () => {
    const h = harness();
    const pending = deferred();
    h.respond(() => pending.promise);
    const request = h.start().correctMessage(original.id, "Correcao em andamento");
    h.select("coex__fixture", 8);
    h.state.messages = [{ ...original, id: 50, contact_id: 8, conversation_id: "coex__fixture" }];
    h.state.draft = "Texto da outra conversa";
    h.state.notice = "Aviso da outra conversa";
    h.state.error = "Erro da outra conversa";
    if (outcome === "success") pending.resolve({ corrected_message_id: original.id, new_message_id: 32 });
    else pending.reject(new Error("Falha antiga"));
    assert.equal(await request, outcome === "success");
    assert.equal(h.state.draft, "Texto da outra conversa");
    assert.equal(h.state.notice, "Aviso da outra conversa");
    assert.equal(h.state.error, "Erro da outra conversa");
    assert.equal(h.state.messages[0].is_corrected, undefined);
    assert.equal(h.state.busySend, false);
  });
}

test("envio normal, nota interna e gravacao continuam disponiveis", async () => {
  const h = harness({ draft: " Texto comum " });
  await h.render().submitText(event());
  assert.deepEqual(h.calls[0], { path: "/api/wa/send", body: { conversation_id: original.conversation_id, content: "Operador: Texto comum" } });
  h.state.internalMode = true;
  h.state.draft = "Nota privada";
  await h.render().sendTextMessage();
  assert.deepEqual(h.calls[1], { path: "/api/wa/internal-note", body: { conversation_id: original.conversation_id, content: "Nota privada" } });
  h.state.internalMode = false;
  h.render().handlePrimaryAction();
  assert.equal(h.counters.record, 1);
  await setImmediate();
  assert.equal(h.state.recording, true);
  assert.equal(h.counters.recorders, 1);
  h.render().discardRecording();
  assert.equal(h.state.recording, false);
  assert.equal(h.counters.trackStops, 1);
  assert.equal(h.counters.timers, 0);
});

for (const action of ["correction", "discard", "thread"]) {
  test(`permissao de microfone pendente e cancelada por ${action}`, async () => {
    const h = harness();
    const pending = deferred();
    h.media(() => pending.promise);
    const recordingRequest = h.render().startRecording();
    assert.equal(h.counters.record, 1);
    assert.equal(h.state.recording, false);
    if (action === "correction") h.start();
    else if (action === "discard") h.render().discardRecording();
    else h.select("coex__fixture");
    pending.resolve(h.stream);
    await recordingRequest;
    assert.equal(h.counters.trackStops, 1);
    assert.equal(h.counters.recorders, 0);
    assert.equal(h.counters.timers, 0);
    assert.equal(h.state.recording, false);
    if (action === "correction") {
      assert.equal(h.state.correctionTarget, original);
      assert.equal(h.state.draft, "Texto corrigido");
    }
  });
}

test("permissao negada depois de iniciar correcao nao mostra erro antigo", async () => {
  const h = harness();
  const pending = deferred();
  h.media(() => pending.promise);
  const recordingRequest = h.render().startRecording();
  h.start();
  h.state.error = "Aviso atual";
  pending.reject(new Error("Permissao de microfone negada"));
  await recordingRequest;
  assert.equal(h.state.error, "Aviso atual");
  assert.equal(h.state.correctionTarget, original);
  assert.equal(h.state.recording, false);
});

let passed = 0;
for (const { name, run } of tests) {
  try { await run(); passed += 1; }
  catch (error) { console.error(`FAIL ${name}\n${error.stack}`); }
}
console.log(`${passed} cenarios ok, ${tests.length - passed} falha(s)`);
process.exitCode = passed === tests.length ? 0 : 1;
