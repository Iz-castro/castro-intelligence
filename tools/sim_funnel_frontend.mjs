// Regressao local do frontend do funil comercial (v2: decisoes do PO de
// 28/10/2026, "uma classificação só"). Rode da raiz do repo:
//   node tools/sim_funnel_frontend.mjs
// Compila o TS/TSX REAL com o esbuild ja instalado por npm ci em frontend/
// (sem rede, sem ADC, sem navegador). Fixtures do template clinic_v1 lidas do
// funnel_catalog.py (etapas, desfechos, legado, visibilidade). Cobre:
// normalizeContact (campos crm_*, origem "rule:"), ApiError com detail
// objeto, mapa de erros x codes do backend (inclusive os do encerramento),
// boardReducer (so as colunas devolvidas), sinais derivados, funnelAvailable
// + cache de 1 GET do /config e textos recem-salvos, operation_id estavel,
// catalogo puro (desfechos do encerramento, pre-selecao, congelamento no 409,
// nota so em Outro, Mover para…, filtro "stage:"), formulario da aba Etapas
// (limites, PUT com version, restaurar padrao, rebase no 409), guardas
// estaticas (sem polling, sem /conversation/open, sem qualification no
// quadro, sem conversao restrita), cartao da etapa, desfecho do Encerrar
// atendimento (payload funnel), revalidacao leve do drawer, painel gerencial,
// coluna e quadro. Nao substitui teste em navegador, layout ou a autorizacao
// real do backend.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const frontendDir = fileURLToPath(new URL("../frontend/", import.meta.url));
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { build } = require("esbuild");

let checks = 0;
function check(value, message) { assert.ok(value, message); checks += 1; }
function same(actual, expected, message) { assert.deepEqual(actual, expected, message); checks += 1; }

// firebase.ts le window.location no import: o sim usa um stub inerte.
const FIREBASE_STUB = `export const impersonationTab = false;
export function assertFirebaseSessionActive() {}
export function stopImpersonationReading() {}
export function trackImpersonationTask() { return () => {}; }
export function isFirebaseSessionActive() { return true; }`;
// React de mentira para rodar hooks/componentes fora de um renderer: cada
// chamada vai para o harness ativo (globalThis.__simHooks); JSX vira objeto
// {type, props}; filhos que sao componentes NAO sao renderizados (o teste
// inspeciona as props que eles receberiam).
const REACT_STUB = `const h = () => globalThis.__simHooks;
export const useState = (v) => h().useState(v);
export const useEffect = (f, d) => h().useEffect(f, d);
export const useLayoutEffect = (f, d) => h().useEffect(f, d);
export const useCallback = (f, d) => h().useCallback(f, d);
export const useMemo = (f, d) => h().useMemo(f, d);
export const useRef = (v) => h().useRef(v);
export const useId = () => h().useId();
export const useReducer = (r, a, i) => h().useReducer(r, a, i);
export const memo = (component) => component;
export const lazy = (factory) => { const Lazy = () => null; Lazy.factory = factory; return Lazy; };
export class Component { constructor(props) { this.props = props; } }
export const Suspense = "Suspense";
export const Fragment = "Fragment";`;
const JSX_STUB = `export function jsx(type, props, key) { return { type, props: props || {}, key }; }
export const jsxs = jsx;
export const Fragment = "Fragment";`;
const REACT_DOM_STUB = "export function createPortal(children) { return { type: \"Portal\", props: { children } }; }";
const CRM_STUB = "export function useCrm() { return globalThis.__simCrm; }";
const API_STUB = "export function loadFunnelConfig(auth) { return globalThis.__simLoadConfig(auth); }";
const STUB_SOURCES = { react: REACT_STUB, "react/jsx-runtime": JSX_STUB, "react-dom": REACT_DOM_STUB, crm: CRM_STUB, "funnel-api": API_STUB, firebase: FIREBASE_STUB };

function stubs({ react = false, funnelApi = false, crm = false } = {}) {
  return {
    name: "funnel-sim-stubs",
    setup(b) {
      const to = (path) => () => ({ path, namespace: "sim-stub" });
      b.onResolve({ filter: /^\.\.?\/firebase$/ }, to("firebase"));
      if (react) {
        b.onResolve({ filter: /^react$/ }, to("react"));
        b.onResolve({ filter: /^react\/jsx-runtime$/ }, to("react/jsx-runtime"));
        b.onResolve({ filter: /^react-dom$/ }, to("react-dom"));
      }
      if (crm) b.onResolve({ filter: /context\/CrmContext$/ }, to("crm"));
      if (funnelApi) b.onResolve({ filter: /^\.\/api$/ }, (args) => (/useFunnelConfig\.ts$/.test(args.importer) ? { path: "funnel-api", namespace: "sim-stub" } : undefined));
      b.onLoad({ filter: /.*/, namespace: "sim-stub" }, (args) => ({ loader: "js", contents: STUB_SOURCES[args.path] }));
    },
  };
}

// UM bundle por cenario: classes (ApiError) precisam ser a mesma copia em
// quem lanca e em quem testa instanceof.
async function load(contents, options) {
  const result = await build({
    stdin: { contents, resolveDir: frontendDir, loader: "ts", sourcefile: "sim-entry.ts" },
    bundle: true, write: false, platform: "node", format: "esm", jsx: "automatic", logLevel: "silent",
    loader: { ".css": "empty", ".png": "empty" },
    define: { "process.env.NODE_ENV": "\"production\"" }, plugins: [stubs(options)],
  });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
}

const read = (relative) => readFileSync(new URL(relative, import.meta.url), "utf8").replace(/\r\n/g, "\n");

// ---------------------------------------------------------------------------
// 0. Fixtures v2: template clinic_v1 lido do funnel_catalog.py (mesmo shape do
//    GET /config de funnel_service.get_config) e capabilities do servico
// ---------------------------------------------------------------------------
const pyCatalog = read("../funnel_catalog.py");
const pyService = read("../funnel_service.py");
const pyConstants = Object.fromEntries([...pyCatalog.matchAll(/^((?:STALE|KIND)_[A-Z_]+) = "([a-z_]+)"/gm)].map((match) => [match[1], match[2]]));
const clinicSource = /"clinic_v1": \{\n([\s\S]*?)\n    \},\n\}/.exec(pyCatalog)?.[1] || "";
const pyBlock = (name) => new RegExp(`"${name}": \\[\\n([\\s\\S]*?)\\n        \\],`).exec(clinicSource)?.[1] || "";
const pyString = (chunk, field) => new RegExp(`"${field}": "([^"]*)"`).exec(chunk)?.[1] ?? null;
const pyTrue = (chunk, field) => new RegExp(`"${field}": True`).test(chunk);
const pyChunks = (block) => block.split('{"key": "').slice(1).map((chunk) => ({ key: chunk.slice(0, chunk.indexOf('"')), chunk }));
const templateLabel = pyString(clinicSource, "label");
const templateStages = pyChunks(pyBlock("stages")).map(({ key, chunk }) => {
  const stale = /"stale": \{"kind": ([A-Z_]+)(?:, "days": (\d+))?\}/.exec(chunk);
  return {
    key, label: pyString(chunk, "label"), kind: pyConstants[/"kind": ([A-Z_]+)/.exec(chunk)?.[1]], order: Number(/"order": (\d+)/.exec(chunk)?.[1]),
    requires_reason: pyTrue(chunk, "requires_reason"), manual_target: !/"manual_target": False/.test(chunk),
    milestone: pyTrue(chunk, "milestone"), appointment_kind: pyTrue(chunk, "appointment_kind"),
    stale: stale ? { kind: pyConstants[stale[1]], days: stale[2] ? Number(stale[2]) : null } : null,
    description: pyString(chunk, "description") || "", close_outcome: pyTrue(chunk, "close_outcome"),
    legacy_qualification: pyString(chunk, "legacy_qualification"), visibility_permission: pyString(chunk, "visibility_permission"),
  };
});
const templateReasons = pyChunks(pyBlock("reasons")).map(({ key, chunk }) => ({
  key, label: pyString(chunk, "label"), allows_note: pyTrue(chunk, "allows_note"), selectable: !/"selectable": False/.test(chunk),
  ...(pyString(chunk, "hint") ? { hint: pyString(chunk, "hint") } : {}),
}));
same(templateStages.map((stage) => stage.key), ["new", "in_service", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified", "unclassified"], "clinic_v1: as 8 etapas v2, na ordem");
check(templateStages.every((stage) => stage.label && stage.kind && Number.isInteger(stage.order) && stage.description), "toda etapa tem rotulo, tipo, ordem e texto explicativo");
same(Object.fromEntries(templateStages.map((stage) => [stage.key, stage.label])), {
  new: "Novo contato", in_service: "Em atendimento", awaiting_followup: "Aguardando retorno", scheduled: "Cliente Agendado",
  loyal: "Paciente em acompanhamento", non_converted: "Não convertido", disqualified: "Não qualificado", unclassified: "A classificar",
}, "rotulos v2 do template");
same(templateStages.filter((stage) => stage.close_outcome).map((stage) => stage.key), ["awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"], "desfechos do encerramento = etapas com close_outcome");
same(Object.fromEntries(templateStages.filter((stage) => stage.legacy_qualification).map((stage) => [stage.key, stage.legacy_qualification])), {
  in_service: "em_atendimento", awaiting_followup: "nao_convertido", scheduled: "convertido", loyal: "convertido", non_converted: "nao_convertido", disqualified: "nao_qualificado",
}, "legado equivalente da mudanca manual (new/unclassified nao tocam)");
same(templateStages.filter((stage) => stage.visibility_permission).map((stage) => [stage.key, stage.visibility_permission]), [["new", "ver_contatos_agente_funil"]], "so Novo contato depende de ver_contatos_agente_funil");
same(templateStages.filter((stage) => !stage.manual_target).map((stage) => stage.key), ["unclassified"], "A classificar nao e destino manual");
same([templateStages.find((stage) => stage.key === "scheduled").kind, templateStages.find((stage) => stage.key === "loyal").kind, templateStages.find((stage) => stage.key === "disqualified").kind], ["won", "won", "excluded"], "Cliente Agendado e Paciente em acompanhamento ganham; Nao qualificado exclui");
check(!templateStages.some((stage) => ["attended", "converted"].includes(stage.key)), "chaves v1 attended/converted sairam");
check(/"legacy_qualification_sync": True/.test(clinicSource) && /"kpis": \{"booked_stage": "scheduled", "won_stage": "scheduled"\}/.test(clinicSource), "template com sync do legado e KPI = scheduled");
check(["proposal_declined", "no_show", "other", "not_informed"].every((key) => templateReasons.some((reason) => reason.key === key)), "motivos novos (proposal_declined, no_show) + Outro + nao informado");
same(templateReasons.filter((reason) => reason.allows_note).map((reason) => reason.key), ["other"], "nota livre so no motivo Outro");
same(templateReasons.filter((reason) => !reason.selectable).map((reason) => reason.key), ["not_informed"], "Motivo nao registrado nao e escolhivel");

const capabilityKeys = [.../def capabilities\(self\):\n\s+return \{([\s\S]*?)\n\s+\}/.exec(pyService)?.[1].matchAll(/"([a-z_]+)":/g) || []].map((match) => match[1]);
same(capabilityKeys, ["can_move", "can_dashboard", "privileged", "followup", "can_configure", "can_see_agent_contacts"], "capabilities v2 do /config (sem can_confirm_conversion)");
const funnelTypes = read("../frontend/src/features/funnel/types.ts");
const capabilityType = /export type FunnelCapabilities = \{([\s\S]*?)\n\};/.exec(funnelTypes)?.[1] || "";
check(capabilityKeys.every((key) => new RegExp(`\\b${key}\\??:`).test(capabilityType)), "FunnelCapabilities (TS) espelha as capabilities do servico");
const stageType = /export type FunnelStage = \{([\s\S]*?)\n\};/.exec(funnelTypes)?.[1] || "";
const configStageFields = ["key", "label", "kind", "order", "requires_reason", "manual_target", "milestone", "appointment_kind", "stale", "description", "active",
  "close_outcome", "legacy_qualification", "visibility_permission", "visible", "default_label", "default_description"];
const getConfig = /def get_config\(self\):([\s\S]*?)\n    def /.exec(pyService)?.[1] || "";
check(configStageFields.every((field) => getConfig.includes(`"${field}":`) && new RegExp(`\\b${field}\\??:`).test(stageType)), "campos da etapa no /config existem no FunnelStage (TS)");

const capabilities = (extra = {}) => ({ can_move: true, can_dashboard: false, privileged: false, followup: false, can_configure: false, can_see_agent_contacts: false, ...extra });
const allowAll = () => true;
const operatorHas = (permission) => permission !== "ver_contatos_agente_funil";
function clinicCatalog(has = allowAll, extra = {}) {
  return {
    template: "clinic_v1", template_label: templateLabel, version: 1, overrides_version: 0, legacy_qualification_sync: true,
    stages: templateStages.map((stage) => ({ ...stage, active: true, visible: !stage.visibility_permission || has(stage.visibility_permission), default_label: stage.label, default_description: stage.description })),
    reasons: templateReasons.map((reason) => ({ ...reason, active: true, default_label: reason.label })),
    kpis: { booked_stage: "scheduled", won_stage: "scheduled" }, ...extra,
  };
}
const clinic = clinicCatalog();                     // supervisor/admin: ve Novo contato
const clinicOperator = clinicCatalog(operatorHas);  // operador: Novo contato invisivel
const stageDefs = Object.fromEntries(clinic.stages.map((stage) => [stage.key, stage]));
const keysOf = (items) => items.map((item) => item.key);

const m = await load(`
export * as normalization from "./src/utils/normalization.ts";
export * as api from "./src/api.ts";
export * as errors from "./src/features/funnel/errors.ts";
export * as reducer from "./src/features/funnel/boardReducer.ts";
export * as format from "./src/features/funnel/format.ts";
export * as badges from "./src/features/funnel/badges.ts";
export * as a11y from "./src/features/funnel/a11y.ts";
export * as config from "./src/features/funnel/useFunnelConfig.ts";
export * as dialog from "./src/features/funnel/MoveStageDialog.tsx";
export * as search from "./src/features/funnel/FunnelSearch.tsx";
export * as catalog from "./src/features/funnel/catalog.ts";
export * as settings from "./src/features/funnel/settingsForm.ts";
`);
const hooked = await load(`
export * as config from "./src/features/funnel/useFunnelConfig.ts";
export * as operation from "./src/features/followup/useOperation.ts";
export { ApiError } from "./src/api.ts";
`, { react: true, funnelApi: true });

const { normalizeContact } = m.normalization;
const { ApiError, apiErrorFromPayload } = m.api;
const { FUNNEL_ERROR_MESSAGES, FUNNEL_CLOSE_ERROR_MESSAGES, funnelErrorCode, funnelErrorMessage, funnelCloseErrorMessage, isAccessLost } = m.errors;
const { boardReducer, createBoardState, deriveSignals, findCard, DEFAULT_FILTERS } = m.reducer;
const f = m.format;
const c = m.catalog;
const s = m.settings;

// ---------------------------------------------------------------------------
// 1. normalizeContact: whitelist dos campos crm_* (modo snapshot)
// ---------------------------------------------------------------------------
const base = { id: 7, display_name: "Paciente Sim" };
let contact = normalizeContact(base, "7");
same([contact.crm_stage, contact.crm_stage_version, contact.crm_stage_changed_at, contact.crm_stage_source, contact.crm_funnel_entered_at, contact.lead_temperature_at],
  [undefined, undefined, undefined, undefined, undefined, undefined], "contato sem funil = campos ausentes (Fora do funil)");
check(contact.is_backup === false, "is_backup ausente = false");
contact = normalizeContact({
  ...base, crm_stage: "scheduled", crm_stage_version: 3, crm_stage_source: "user", is_backup: true,
  crm_stage_changed_at: { seconds: 1761490800, nanoseconds: 5_000_000 },
  crm_funnel_entered_at: { toDate: () => new Date("2026-10-01T12:00:00Z") },
  lead_temperature_at: "2026-10-02T10:00:00+00:00",
}, "7");
same([contact.crm_stage, contact.crm_stage_version, contact.crm_stage_source], ["scheduled", 3, "user"], "etapa, versao e origem preservadas");
check(contact.crm_stage_changed_at === new Date(1761490800005).toISOString(), "Timestamp {seconds,nanoseconds} vira ISO");
check(contact.crm_funnel_entered_at === "2026-10-01T12:00:00.000Z", "Timestamp com toDate vira ISO");
check(contact.lead_temperature_at === "2026-10-02T10:00:00+00:00" && contact.is_backup === true, "ISO string mantida; is_backup lido");
for (const bad of ["Scheduled", "x", "1abc", "a-b", "", null, 5, {}, "a".repeat(41), "<b>novo</b>", "new stage"]) {
  check(normalizeContact({ ...base, crm_stage: bad }, "7").crm_stage === undefined, `crm_stage invalido descartado: ${JSON.stringify(bad)}`);
}
check(normalizeContact({ ...base, crm_stage: "a".repeat(40) }, "7").crm_stage === "a".repeat(40), "chave de 40 caracteres aceita");
const version = (value) => normalizeContact({ ...base, crm_stage_version: value }, "7").crm_stage_version;
same([version(0), version(4), version("5"), version(-1), version(1.5), version("abc"), version(" "), version(true), version(null)],
  [0, 4, 5, undefined, undefined, undefined, undefined, undefined, undefined], "versao: inteiro >= 0, senao ausente");
const source = (value) => normalizeContact({ ...base, crm_stage_source: value }, "7").crm_stage_source;
same([source("rule:handoff"), source("rule:human_reply"), source("intake"), source("migration")], ["rule:handoff", "rule:human_reply", "intake", "migration"], "origem: automacao por evento (rule:handoff) preservada");
same([source("User"), source("rule:"), source("rule:x"), source("rule:Handoff"), source("rule:rule:handoff"), source("rules:handoff"), source("x:handoff"), source(7), source(null)],
  [undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined], "origem fora do formato descartada");
const normalizationSource = read("../frontend/src/utils/normalization.ts");
const tsKey = /const FUNNEL_KEY = (\/.+\/);/.exec(normalizationSource)?.[1];
const pyKey = /_KEY = re\.compile\(r"(.+)"\)/.exec(pyCatalog)?.[1];
check(tsKey && pyKey && tsKey === `/${pyKey}/`, "regex de chave da etapa igual a do funnel_catalog.py");
check(/const FUNNEL_RULE_PREFIX = "([^"]+)"/.exec(normalizationSource)?.[1] === /^SOURCE_RULE_PREFIX = "([^"]+)"/m.exec(pyCatalog)?.[1], "prefixo rule: igual ao SOURCE_RULE_PREFIX do backend");

// ---------------------------------------------------------------------------
// 2. ApiError com detail objeto (retrocompativel; nunca "[object Object]")
// ---------------------------------------------------------------------------
const stale = apiErrorFromPayload({ detail: { code: "stale_version", message: "A etapa mudou.", current: { stage: "new", version: 4 } } }, 409);
check(stale instanceof ApiError && stale.status === 409 && stale.code === "stale_version", "detail objeto -> code");
check(stale.message === "A etapa mudou." && stale.detail.current.version === 4, "detail objeto -> message e detail preservados");
const legacy = apiErrorFromPayload({ detail: "Permissao negada (ver_funil)" }, 403);
check(legacy.message === "Permissao negada (ver_funil)" && legacy.code === undefined, "detail string segue como message, sem code");
const validation = apiErrorFromPayload({ detail: [{ msg: "campo obrigatorio" }, null, { loc: ["x"] }] }, 422);
check(validation.message === "campo obrigatorio; Valor invalido; Valor invalido" && validation.code === undefined, "detail array (422) juntado");
const odd = apiErrorFromPayload({ detail: { code: 7, extra: true } }, 500);
check(odd.message === "Erro HTTP 500" && odd.code === undefined && !odd.message.includes("[object"), "objeto sem message/code valido = fallback");
check(apiErrorFromPayload({ detail: { code: "rate_limited", message: "   " } }, 429).message === "Erro HTTP 429", "message em branco = fallback");
check(apiErrorFromPayload({}, 502).message === "Erro HTTP 502", "sem detail = fallback");
const plain = new ApiError("x", 404);
check(plain.code === undefined && plain.detail === undefined && plain.status === 404, "construtor antigo (message, status) intacto");

// ---------------------------------------------------------------------------
// 3. Mapa de erros x codes REAIS do backend (+ textos do encerramento)
// ---------------------------------------------------------------------------
const python = ["funnel_service.py", "funnel_routes.py", "funnel_catalog.py"].map((file) => read(`../${file}`)).join("\n");
const codes = new Set();
for (const match of python.matchAll(/_(?:fail|error)\(\s*\d{3},\s*"([a-z_]+)"/g)) codes.add(match[1]);
for (const match of python.matchAll(/FunnelRuleError\(\s*"([a-z_]+)"/g)) codes.add(match[1]);
for (const match of python.matchAll(/"code":\s*"([a-z_]+)"/g)) codes.add(match[1]);
check(codes.size >= 25, `codes do backend encontrados (${codes.size})`);
for (const code of codes) check(Boolean(FUNNEL_ERROR_MESSAGES[code]), `code do backend sem texto na UI: ${code}`);
check(codes.has("overrides_invalid") && codes.has("stage_not_allowed") && codes.has("funnel_disabled"), "codes v2 (aba Etapas, encerramento) no backend");
check(funnelErrorMessage(stale) === FUNNEL_ERROR_MESSAGES.stale_version, "code conhecido usa o texto local");
check(funnelErrorMessage(legacy) === "Seu acesso não permite esta ação.", "403 sem code = texto por status");
check(funnelErrorMessage(new ApiError("boom", 503)).startsWith("O servidor não respondeu"), "5xx = texto generico");
check(funnelErrorMessage(new TypeError("Failed to fetch")).startsWith("Sem conexão"), "falha de rede");
check(funnelErrorMessage(new DOMException("x", "AbortError")) === "Consulta cancelada.", "abort");
check(funnelErrorCode(stale) === "stale_version" && funnelErrorCode(new Error("x")) === "", "funnelErrorCode");
// 422 de validacao do FastAPI em /api/funnel/* (handler do main.py): detail
// objeto {code: invalid_request}, sem eco do input -> texto local proprio.
const invalidRequest = apiErrorFromPayload({ detail: { code: "invalid_request", message: "Parâmetros inválidos." } }, 422);
check(invalidRequest.code === "invalid_request" && funnelErrorCode(invalidRequest) === "invalid_request", "422 de validacao -> code invalid_request");
check(funnelErrorMessage(invalidRequest) === FUNNEL_ERROR_MESSAGES.invalid_request && FUNNEL_ERROR_MESSAGES.invalid_request.startsWith("Parâmetros inválidos."), "invalid_request tem texto local (nao o generico de 422)");
check(FUNNEL_ERROR_MESSAGES.invalid_request !== funnelErrorMessage(new ApiError("x", 422)) && !isAccessLost(invalidRequest), "invalid_request: distinto do 422 sem code e nao fecha o drawer");
check(isAccessLost(new ApiError("x", 401)) && isAccessLost(new ApiError("x", 403)) && isAccessLost(new ApiError("x", 404)), "401/403/404 = acesso perdido");
check(!isAccessLost(new ApiError("x", 409)) && !isAccessLost(new ApiError("x", 429)) && !isAccessLost(new Error("x")), "409/429/rede nao fecham o drawer");

// Encerrar atendimento com o desfecho pelo funil: mesmos codes, texto do
// contexto do encerramento; o resto cai no mapa geral.
same(Object.keys(FUNNEL_CLOSE_ERROR_MESSAGES).sort(), ["contact_unavailable", "context_changed", "funnel_disabled", "out_of_scope", "permission_denied", "stage_not_allowed"], "codes com texto proprio no encerramento");
for (const [code, text] of Object.entries(FUNNEL_CLOSE_ERROR_MESSAGES)) {
  check(codes.has(code), `encerramento: code ${code} existe no backend`);
  const error = apiErrorFromPayload({ detail: { code, message: "texto do servidor" } }, code === "permission_denied" ? 403 : code === "out_of_scope" ? 404 : 409);
  check(funnelCloseErrorMessage(error) === text && text !== FUNNEL_ERROR_MESSAGES[code], `encerramento: ${code} usa o texto do contexto`);
}
check(FUNNEL_CLOSE_ERROR_MESSAGES.permission_denied.includes("mover etapas") && FUNNEL_CLOSE_ERROR_MESSAGES.funnel_disabled.includes("Escolha o desfecho de novo"), "textos do encerramento explicam a saida");
check(funnelCloseErrorMessage(apiErrorFromPayload({ detail: { code: "reason_required", message: "x" } }, 422)) === "Informe o motivo.", "reason_required cai no mapa geral");
check(funnelCloseErrorMessage(apiErrorFromPayload({ detail: { code: "stale_version", message: "x" } }, 409)) === FUNNEL_ERROR_MESSAGES.stale_version, "stale_version cai no mapa geral");
check(funnelCloseErrorMessage(new ApiError("x", 403)) === "Seu acesso não permite esta ação." && funnelCloseErrorMessage(new TypeError("x")).startsWith("Sem conexão"), "sem code: texto por status/rede");

// 409 stale_version -> estado atual do servidor para "Reaplicar".
const { staleCurrent } = m.dialog;
same(staleCurrent(apiErrorFromPayload({ detail: { code: "stale_version", message: "m", current: { stage: "scheduled", version: 5, changed_at: "2026-10-26T12:00:00+00:00", changed_by_user_id: 3, changed_by_name: "Ana" } } }, 409)),
  { stage: "scheduled", version: 5, changed_at: "2026-10-26T12:00:00+00:00", changed_by_user_id: 3, changed_by_name: "Ana" }, "stale_version com quem moveu");
same(staleCurrent(apiErrorFromPayload({ detail: { code: "stale_version", message: "m", current: { stage: null, version: "x" } } }, 409)),
  { stage: null, version: 0, changed_at: null, changed_by_user_id: null, changed_by_name: null }, "current malformado tolerado");
check(staleCurrent(apiErrorFromPayload({ detail: { code: "context_changed", message: "m" } }, 409)) === null, "outro 409 nao e conflito de versao");
check(staleCurrent(apiErrorFromPayload({ detail: { code: "stale_version", message: "m" } }, 409)) === null, "stale_version sem current = null");

// ---------------------------------------------------------------------------
// 4. Sinais derivados (porte do funnel_catalog.derived_signals)
// ---------------------------------------------------------------------------
const DAY = 86_400_000;
const NOW = Date.UTC(2026, 9, 26, 15, 0, 0);
const at = (ms) => new Date(ms).toISOString();
let signals = deriveSignals(stageDefs.new, { changedAt: at(NOW - 3 * DAY), lastInboundAt: at(NOW - 2 * DAY), nextTask: null, tasksVisible: false }, NOW);
same([signals.stale, signals.stale_kind, signals.days_in_stage, signals.patient_idle_days], [true, "patient_silence", 3, 2], "paciente sem escrever ha 2 dias (limiar 1)");
signals = deriveSignals(stageDefs.new, { changedAt: at(NOW - DAY / 2), lastInboundAt: at(NOW - 23 * 3_600_000), nextTask: null, tasksVisible: false }, NOW);
check(!signals.stale && signals.stale_kind === null && signals.patient_idle_days === 0, "23 h sem escrever = 0 dia (piso), nao parado");
const timedStage = { ...stageDefs.awaiting_followup, key: "timed", stale: { kind: "time_in_stage", days: 14 } };
signals = deriveSignals(timedStage, { changedAt: at(NOW - 14 * DAY), lastInboundAt: null, nextTask: null, tasksVisible: false }, NOW);
check(signals.stale && signals.stale_kind === "time_in_stage" && signals.patient_idle_days === null, "14 dias na etapa = parado (time_in_stage)");
signals = deriveSignals(stageDefs.scheduled, { changedAt: at(NOW - 30 * DAY), lastInboundAt: null, nextTask: null, tasksVisible: false }, NOW);
check(!signals.stale && signals.days_in_stage === 30, "Cliente Agendado sem limiar: nunca parado");
signals = deriveSignals(stageDefs.awaiting_followup, { changedAt: at(NOW - DAY), lastInboundAt: null, nextTask: null, tasksVisible: true }, NOW);
check(signals.no_next_action && !signals.task_overdue && !signals.stale, "etapa de tarefa sem proxima acao (com follow-up visivel)");
signals = deriveSignals(stageDefs.awaiting_followup, { changedAt: at(NOW - DAY), lastInboundAt: null, nextTask: null, tasksVisible: false }, NOW);
check(!signals.no_next_action && !signals.task_overdue, "sem acesso ao follow-up nenhum sinal de tarefa");
signals = deriveSignals(stageDefs.awaiting_followup, { changedAt: at(NOW - DAY), lastInboundAt: null, nextTask: { id: "t", title: "Ligar", due_at: at(NOW - 60_000), overdue: true, queue_key: null, assignee_name: null }, tasksVisible: true }, NOW);
check(signals.task_overdue && !signals.no_next_action, "tarefa vencida = atrasada");
signals = deriveSignals(stageDefs.non_converted, { changedAt: at(NOW - 5 * DAY), lastInboundAt: at(NOW - DAY), nextTask: null, tasksVisible: false }, NOW);
check(signals.new_activity && !signals.stale, "paciente escreveu depois de Nao convertido = mensagem nova");
signals = deriveSignals(stageDefs.scheduled, { changedAt: at(NOW - 5 * DAY), lastInboundAt: at(NOW - DAY), nextTask: null, tasksVisible: false }, NOW);
check(signals.new_activity, "etapa ganha (Cliente Agendado) tambem emite mensagem nova");
signals = deriveSignals(stageDefs.in_service, { changedAt: at(NOW - 5 * DAY), lastInboundAt: at(NOW - DAY), nextTask: null, tasksVisible: false }, NOW);
check(!signals.new_activity, "etapa aberta nao emite mensagem nova");
signals = deriveSignals(null, { changedAt: null, lastInboundAt: "lixo", nextTask: null, tasksVisible: false }, NOW);
same([signals.days_in_stage, signals.patient_idle_days, signals.stale], [null, null, false], "datas ausentes/invalidas = sem sinal");

// ---------------------------------------------------------------------------
// 5. boardReducer (puro): dedupe por contato e versao, totais locais, ordem
// ---------------------------------------------------------------------------
const quiet = { days_in_stage: 6, patient_idle_days: 1, stale: false, stale_kind: null, task_overdue: false, no_next_action: false, new_activity: false };
function card(id, stage, stageVersion, extra = {}) {
  return {
    contact_id: id, display_name: `Contato ${id}`, lead_temperature: null, lead_temperature_at: null, stage, stage_version: stageVersion,
    stage_changed_at: at(NOW - 6 * DAY), stage_source: "user", owner: null, last_inbound_at: at(NOW - DAY), last_activity_at: null,
    signals: quiet, badges: { with_bot: false, lgpd_pending: false, commercial_blocked: false, bot_outcome: null },
    reason: null, next_task: null, tasks_visible: false, ...extra,
  };
}
function column(stage, cards, extra = {}) {
  return { stage, label: stageDefs[stage].label, kind: stageDefs[stage].kind, active: true, count: cards.length, stale_count: 0, cards, next_cursor: null, ...extra };
}
const response = {
  generated_at: "2026-10-26T15:04:00+00:00", scope: { privileged: true, owner_id: null, mine: false, order: "desc" },
  columns: [
    column("new", [card(1, "new", 2, { signals: { ...quiet, stale: true, stale_kind: "patient_silence" } }), card(2, "new", 1), card(2, "new", 1), card(3, "new", 5), { contact_id: "x" }], { count: 3, stale_count: 1, next_cursor: "cursor-new" }),
    column("scheduled", [card(3, "scheduled", 6), card(4, "scheduled", 1)], { count: -4, stale_count: 0 }),
    column("non_converted", [card(6, "non_converted", 2, { reason: { key: "price", label: "Preço" } })], { stale_count: null }),
  ],
};
const ids = (state, stage) => state.columns.find((entry) => entry.stage === stage).cards.map((entry) => entry.contact_id);
const col = (state, stage) => state.columns.find((entry) => entry.stage === stage);

let state = createBoardState();
check(state.status === "idle" && state.columns.length === 0 && state.filters === DEFAULT_FILTERS, "estado inicial vazio");
state = boardReducer(state, { type: "load_started", requestId: 1, filters: DEFAULT_FILTERS });
check(state.status === "loading" && state.requestId === 1, "carga iniciada");
check(boardReducer(state, { type: "load_succeeded", requestId: 99, response, loadedAt: NOW }) === state, "resposta de carga antiga descartada");
state = boardReducer(state, { type: "load_succeeded", requestId: 1, response, loadedAt: NOW });
check(state.status === "ready" && state.generatedAt === response.generated_at && state.loadedAt === NOW, "carga aplicada com dados de HH:MM");
same(ids(state, "new"), [1, 2], "contato em 2 colunas fica so na de versao maior; duplicata e id invalido saem");
same(ids(state, "scheduled"), [3, 4], "versao maior ganha a coluna");
check(col(state, "new").count === 3 && col(state, "scheduled").count === 0 && col(state, "new").staleCount === 1 && col(state, "non_converted").staleCount === null, "totais do servidor (negativo vira 0; null preservado)");
check(boardReducer(state, { type: "load_failed", requestId: 0, error: "x" }) === state, "erro de carga antiga descartado");

state = boardReducer(state, { type: "more_started", stage: "new" });
check(col(state, "new").loadingMore, "carregar mais em andamento");
check(boardReducer(state, { type: "more_succeeded", requestId: 7, stage: "new", cards: [], nextCursor: null }) === state, "pagina de carga antiga descartada");
state = boardReducer(state, { type: "more_succeeded", requestId: 1, stage: "new", cards: [card(2, "new", 1), card(4, "new", 3), card(5, "new", 1), card(5, "new", 1)], nextCursor: null });
same(ids(state, "new"), [1, 2, 4, 5], "pagina: repetida descartada, versao maior entra");
same(ids(state, "scheduled"), [3], "copia antiga sai da outra coluna");
check(col(state, "new").nextCursor === null && !col(state, "new").loadingMore && col(state, "new").count === 3, "pagina nao mexe nos totais do servidor");
check(findCard(state, 3).stage_version === 6 && findCard(state, 99) === null, "findCard devolve a versao exibida");

const scheduledResult = { key: "scheduled", label: "Cliente Agendado", kind: "won", version: 3, changed_at: at(NOW), source: "user", entered_at: null, reason: null, reason_note: null, appointment_kind: "consultation" };
const moveAction = { type: "card_moved", contactId: 1, result: scheduledResult, target: stageDefs.scheduled, now: NOW };
const beforeMove = state;
state = boardReducer(state, moveAction);
same(ids(state, "new"), [2, 4, 5], "card saiu da etapa de origem");
same(ids(state, "scheduled"), [1, 3], "ordem desc: card movido entra no topo");
check(col(state, "new").count === 2 && col(state, "scheduled").count === 1, "totais locais: -1 na origem, +1 no destino");
check(col(state, "new").staleCount === 0 && col(state, "scheduled").staleCount === 0, "parados recalculados (saiu parado, entrou em dia)");
const moved = findCard(state, 1);
check(moved.stage === "scheduled" && moved.stage_version === 3 && moved.signals.days_in_stage === 0 && moved.reason === null, "card atualizado com a etapa e os sinais novos");
check(beforeMove.columns !== state.columns && findCard(beforeMove, 1).stage === "new", "reducer nao muta o estado anterior");
check(boardReducer(state, moveAction) === state, "replay/dispatch em dobro nao altera nada");
const outside = boardReducer(state, { ...moveAction, contactId: 99 });
check(outside.outdated && outside.columns === state.columns, "contato fora dos cards carregados = totais desatualizados");

state = boardReducer(state, { type: "card_moved", contactId: 6, result: { ...scheduledResult, key: "non_converted", kind: "lost", version: 3, reason: { key: "other", label: "Outro" } }, target: stageDefs.non_converted, now: NOW });
check(col(state, "non_converted").count === 1 && findCard(state, 6).reason.key === "other" && col(state, "non_converted").staleCount === null, "correcao de motivo: mesma coluna, mesmo total");
state = boardReducer(state, { type: "card_moved", contactId: 2, result: { ...scheduledResult, key: "disqualified", kind: "excluded", version: 2 }, target: stageDefs.disqualified, now: NOW });
check(!ids(state, "new").includes(2) && col(state, "new").count === 1 && state.outdated, "destino fora do quadro: sai da origem e pede Atualizar");
state = boardReducer(state, { type: "card_removed", contactId: 4 });
check(!ids(state, "new").includes(4) && state.outdated, "card que saiu do acesso some e pede Atualizar");
check(boardReducer(state, { type: "card_removed", contactId: 404 }) === state, "remover ausente nao muda nada");

const ascFilters = { order: "asc", ownerId: null, mine: false };
let asc = boardReducer(state, { type: "load_started", requestId: 2, filters: ascFilters });
check(asc.columns.length === 0 && asc.generatedAt === "" && !asc.outdated, "troca de filtro nunca mostra a lista velha");
asc = boardReducer(asc, { type: "load_succeeded", requestId: 2, loadedAt: NOW, response: { ...response, columns: [
  column("new", [card(10, "new", 1), card(11, "new", 1)]),
  column("scheduled", [card(12, "scheduled", 1)], { next_cursor: "more" }),
  column("disqualified", [card(13, "disqualified", 1)]),
] } });
let ascMoved = boardReducer(asc, { type: "card_moved", contactId: 10, result: { ...scheduledResult, version: 2 }, target: stageDefs.scheduled, now: NOW });
same(ids(ascMoved, "scheduled"), [12], "ordem asc com mais paginas: card nao e inserido fora de ordem");
check(col(ascMoved, "scheduled").count === 2, "mas o total do destino sobe");
ascMoved = boardReducer(asc, { type: "card_moved", contactId: 11, result: { ...scheduledResult, key: "disqualified", kind: "excluded", version: 2 }, target: stageDefs.disqualified, now: NOW });
same(ids(ascMoved, "disqualified"), [13, 11], "ordem asc com coluna completa: entra no fim");

let failing = boardReducer(asc, { type: "more_started", stage: "scheduled" });
failing = boardReducer(failing, { type: "more_failed", requestId: 2, stage: "scheduled", error: "A lista expirou.", expired: true });
check(col(failing, "scheduled").nextCursor === null && col(failing, "scheduled").error === "A lista expirou." && !col(failing, "scheduled").loadingMore, "cursor vencido: sem novo carregar mais");
const failed = boardReducer(boardReducer(asc, { type: "load_started", requestId: 3, filters: ascFilters }), { type: "load_failed", requestId: 3, error: "x", code: "out_of_scope", clear: true });
check(failed.status === "error" && failed.columns.length === 0 && failed.errorCode === "out_of_scope", "acesso perdido limpa o quadro");
const kept = boardReducer(boardReducer(asc, { type: "load_started", requestId: 4, filters: ascFilters }), { type: "load_failed", requestId: 4, error: "x" });
check(kept.status === "error" && kept.columns.length === 3, "falha transitoria mantem os dados anteriores");
check(boardReducer(kept, { type: "reset" }).status === "idle", "reset (troca de identidade) zera o quadro");

// Paginacao encerrada com menos cards que o total: parte da etapa esta fora
// do acesso (ex.: lead de dono legado contado no escopo e negado por linha).
const { columnHasHidden } = m.reducer;
let partial = boardReducer(createBoardState(), { type: "load_started", requestId: 5, filters: DEFAULT_FILTERS });
partial = boardReducer(partial, { type: "load_succeeded", requestId: 5, loadedAt: NOW, response: { ...response, columns: [
  column("new", [card(20, "new", 1), card(21, "new", 1)], { count: 3, next_cursor: null }),
  column("scheduled", [card(22, "scheduled", 1)], { count: 4, next_cursor: "more" }),
  column("non_converted", [card(23, "non_converted", 1)], { count: 1, stale_count: null }),
] } });
check(columnHasHidden(col(partial, "new")), "sem cursor e 2 de 3 cards = aviso de contatos fora do acesso");
check(!columnHasHidden(col(partial, "scheduled")) && !columnHasHidden(col(partial, "non_converted")), "com cursor (Carregar mais) ou completa = sem aviso");
let paged = boardReducer(partial, { type: "more_started", stage: "scheduled" });
check(!columnHasHidden(col(paged, "scheduled")), "carregando a proxima pagina = sem aviso");
paged = boardReducer(paged, { type: "more_succeeded", requestId: 5, stage: "scheduled", cards: [card(24, "scheduled", 1)], nextCursor: null });
check(columnHasHidden(col(paged, "scheduled")), "ultima pagina chegou com 2 de 4 = aviso");
const expiredPage = boardReducer(boardReducer(partial, { type: "more_started", stage: "scheduled" }), { type: "more_failed", requestId: 5, stage: "scheduled", error: "A lista expirou.", expired: true });
check(!columnHasHidden(col(expiredPage, "scheduled")), "cursor vencido = sem aviso de acesso (o erro ja pede Atualizar)");
check(columnHasHidden({ ...col(partial, "non_converted"), cards: [] }), "etapa com total e nenhum card acessivel tambem avisa");

// v2: etapa invisivel ao usuario (Novo contato sem ver_contatos_agente_funil)
// nao vem no /board: o quadro tem SO as colunas devolvidas, na ordem dada.
const operatorBoardColumns = clinicOperator.stages.filter((stage) => stage.visible).map((stage) => column(stage.key, stage.key === "in_service" ? [card(30, "in_service", 2)] : []));
let operatorBoard = boardReducer(createBoardState(), { type: "load_started", requestId: 6, filters: DEFAULT_FILTERS });
operatorBoard = boardReducer(operatorBoard, { type: "load_succeeded", requestId: 6, loadedAt: NOW, response: { ...response, columns: operatorBoardColumns } });
same(operatorBoard.columns.map((entry) => entry.stage), ["in_service", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified", "unclassified"], "quadro do operador: sem a coluna Novo contato");
const toInvisible = boardReducer(operatorBoard, { type: "card_moved", contactId: 30, result: { ...scheduledResult, key: "new", kind: "open", version: 3 }, target: stageDefs.new, now: NOW });
check(!ids(toInvisible, "in_service").includes(30) && toInvisible.outdated && !toInvisible.columns.some((entry) => entry.stage === "new"), "card que foi para etapa invisivel sai do quadro (sem coluna nova)");

// ---------------------------------------------------------------------------
// 6. funnelAvailable (puro) + useFunnelConfig: nenhum request indisponivel;
//    1 GET de /config por chave (cache compartilhado entre componentes)
// ---------------------------------------------------------------------------
const { funnelAvailable } = m.config;
const ok = { readOnly: false, featureFunnel: true, funnelEnabled: true, canView: true };
check(funnelAvailable(ok), "flag + tenant + ver_funil fora do Ver como = disponivel");
for (const [change, why] of [[{ readOnly: true }, "Ver como"], [{ featureFunnel: false }, "flag global desligada"], [{ featureFunnel: undefined }, "client-config sem a flag"],
  [{ featureFunnel: null }, "flag nula"], [{ funnelEnabled: false }, "tenant sem funil"], [{ canView: false }, "perfil sem ver_funil"]]) {
  check(!funnelAvailable({ ...ok, ...change }), `indisponivel: ${why}`);
}

function hookHarness() {
  const slots = [];
  let cursor = 0;
  let pending = [];
  const changed = (prev, next) => !prev || !next || prev.length !== next.length || next.some((value, index) => !Object.is(value, prev[index]));
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) {
        const slot = { value: typeof initial === "function" ? initial() : initial };
        slot.set = (next) => { slot.value = typeof next === "function" ? next(slot.value) : next; };
        slots[index] = slot;
      }
      return [slots[index].value, slots[index].set];
    },
    useCallback(fn, deps) { const index = cursor++; if (!slots[index] || changed(slots[index].deps, deps)) slots[index] = { value: fn, deps }; return slots[index].value; },
    useMemo(fn, deps) { const index = cursor++; if (!slots[index] || changed(slots[index].deps, deps)) slots[index] = { value: fn(), deps }; return slots[index].value; },
    useRef(initial) { const index = cursor++; if (!(index in slots)) slots[index] = { current: initial }; return slots[index]; },
    useId() { const index = cursor++; if (!(index in slots)) slots[index] = { value: `:sim${index}:` }; return slots[index].value; },
    useReducer(reducer, initialArg, init) {
      const index = cursor++;
      if (!(index in slots)) {
        const slot = { value: init ? init(initialArg) : initialArg };
        slot.dispatch = (action) => { slot.value = reducer(slot.value, action); };
        slots[index] = slot;
      }
      return [slots[index].value, slots[index].dispatch];
    },
    useEffect(fn, deps) {
      const index = cursor++;
      const previous = slots[index];
      if (previous && !changed(previous.deps, deps)) return;
      slots[index] = { deps, cleanup: previous?.cleanup };
      pending.push(() => { if (typeof slots[index].cleanup === "function") slots[index].cleanup(); slots[index].cleanup = fn(); });
    },
  };
  return {
    // Desmontagem: roda as limpezas pendentes (ex.: clearInterval do drawer).
    unmount() {
      slots.forEach((slot) => { if (slot && typeof slot.cleanup === "function") { slot.cleanup(); slot.cleanup = undefined; } });
    },
    render(component) {
      let output;
      for (let pass = 0; pass < 10; pass += 1) {
        globalThis.__simHooks = hooks;
        cursor = 0;
        output = component();
        const run = pending;
        pending = [];
        if (!run.length) break;
        run.forEach((effect) => effect());
      }
      return output;
    },
  };
}
const flush = () => new Promise((resolve) => setImmediate(resolve));
const configCalls = [];
globalThis.__simLoadConfig = (auth) => new Promise((resolve, reject) => { configCalls.push({ auth, resolve, reject }); });
const { useFunnelConfig } = hooked.config;
const auth = { currentUser: null };
const catalogPayload = { catalog: clinicCatalog(), capabilities: capabilities() };

const cardA = hookHarness();
let view = cardA.render(() => useFunnelConfig(auth, false, "k1"));
check(configCalls.length === 0 && view.config === null && !view.loading, "indisponivel: nenhum GET /config");
view = cardA.render(() => useFunnelConfig(null, true, "k1"));
check(configCalls.length === 0 && !view.loading, "sem sessao Firebase: nenhum GET /config");
view = cardA.render(() => useFunnelConfig(auth, true, "k1"));
check(configCalls.length === 1 && view.loading && view.config === null, "disponivel: 1 GET e estado carregando");
const panelA = hookHarness();
view = panelA.render(() => useFunnelConfig(auth, true, "k1"));
check(configCalls.length === 1, "segundo componente com a mesma chave reaproveita o GET em voo");
configCalls[0].resolve(catalogPayload);
await flush();
view = cardA.render(() => useFunnelConfig(auth, true, "k1"));
check(view.config === catalogPayload && !view.loading && view.error === "", "config entregue ao primeiro componente");
view = panelA.render(() => useFunnelConfig(auth, true, "k1"));
check(view.config === catalogPayload, "config entregue ao segundo componente");
view = hookHarness().render(() => useFunnelConfig(auth, true, "k1"));
check(configCalls.length === 1 && view.config === catalogPayload, "montagem nova na mesma sessao = cache, sem GET");
const profileB = hookHarness();
view = profileB.render(() => useFunnelConfig(auth, true, "k2"));
check(configCalls.length === 2, "troca de perfil/identidade (chave) = novo GET");
configCalls[1].reject(new hooked.ApiError("Permissao negada (ver_funil)", 403));
await flush();
view = profileB.render(() => useFunnelConfig(auth, true, "k2"));
check(view.config === null && view.accessLost && view.error === "Seu acesso não permite esta ação." && !view.loading, "403 no /config = acesso perdido (sem cache)");
hookHarness().render(() => useFunnelConfig(auth, true, "k2"));
check(configCalls.length === 3, "erro nao fica em cache: proxima montagem tenta de novo");
configCalls[2].resolve(catalogPayload);
await flush();
hookHarness().render(() => useFunnelConfig(auth, false, "k2"));
hookHarness().render(() => useFunnelConfig(auth, true, "k2"));
check(configCalls.length === 4, "ficar indisponivel (ex.: Ver como) descarta o cache");
configCalls[3].resolve(catalogPayload);
await flush();

// Aba "Etapas" salvou textos: todos os consumidores buscam de novo (1 GET) e
// os textos salvos valem enquanto o /config vier de instancia com cache velho.
const savedSettings = { version: 2, template: "clinic_v1", stage_labels: { scheduled: "Agendou consulta" }, stage_descriptions: {}, reason_labels: {},
  stages: templateStages.map((stage) => ({ key: stage.key, default_label: stage.label, default_description: stage.description })), reasons: templateReasons.map((reason) => ({ key: reason.key, default_label: reason.label })) };
const consumer = hookHarness();
view = consumer.render(() => useFunnelConfig(auth, true, "k2"));
check(view.config === catalogPayload && configCalls.length === 4, "consumidor montado com o config em cache");
hooked.config.invalidateFunnelConfig(savedSettings);
view = consumer.render(() => useFunnelConfig(auth, true, "k2"));
check(configCalls.length === 5 && view.config?.catalog.stages.find((stage) => stage.key === "scheduled").label === "Agendou consulta", "invalidar = 1 GET novo; o texto salvo ja vale durante a recarga");
configCalls[4].resolve(catalogPayload);
await flush();
view = consumer.render(() => useFunnelConfig(auth, true, "k2"));
const overlaidView = view.config;
check(overlaidView !== catalogPayload && overlaidView.catalog.overrides_version === 2 && overlaidView.catalog.stages.find((stage) => stage.key === "scheduled").label === "Agendou consulta", "/config com overrides_version menor: textos salvos por cima");
check(consumer.render(() => useFunnelConfig(auth, true, "k2")).config === overlaidView && catalogPayload.catalog.stages.find((stage) => stage.key === "scheduled").label === "Cliente Agendado", "overlay estavel (mesmo objeto) e sem mutar o /config");
hooked.config.invalidateFunnelConfig();
consumer.render(() => useFunnelConfig(auth, true, "k2"));
const fresh = { catalog: clinicCatalog(allowAll, { overrides_version: 2, stages: clinicCatalog().stages.map((stage) => (stage.key === "scheduled" ? { ...stage, label: "Agendou (servidor)" } : stage)) }), capabilities: capabilities() };
configCalls[5].resolve(fresh);
await flush();
view = consumer.render(() => useFunnelConfig(auth, true, "k2"));
check(view.config === fresh, "/config alcancou a versao salva: overlay sai, vale o servidor");

// operation_id estavel por payload (inclui contact_id): reenvio apos falha
// de rede vira replay no backend; outro contato/corpo = id novo.
const { useOperationId } = hooked.operation;
const operation = hookHarness().render(() => useOperationId());
const body = { to_stage: "scheduled", expected_version: 2, reason: null, reason_note: null, appointment_kind: null, suggested_by: null };
const first = operation({ contact_id: 7, attempt: 0, ...body });
check(/^[A-Za-z0-9_-]{8,128}$/.test(first), "operation_id no formato aceito pelo backend");
check(operation({ contact_id: 7, attempt: 0, ...body }) === first, "mesmo payload = mesmo operation_id");
const otherContact = operation({ contact_id: 8, attempt: 0, ...body });
check(otherContact !== first, "outro contato = outro operation_id");
check(operation({ contact_id: 8, attempt: 1, ...body }) !== otherContact, "operation_reused (attempt+1) = id novo");

// ---------------------------------------------------------------------------
// 7. Pilha de camadas (Esc fecha so o topo), selos e busca
// ---------------------------------------------------------------------------
const layers = m.a11y.createLayerStack();
const closed = [];
const panel = layers.push(() => closed.push("panel"));
const drawer = layers.push(() => closed.push("drawer"));
check(layers.escape() && closed.join() === "drawer", "Esc com drawer aberto fecha so o drawer");
drawer.release();
check(layers.escape() && closed.join() === "drawer,panel", "Esc seguinte fecha o painel");
panel.release();
drawer.release();
check(layers.size() === 0 && !layers.escape(), "pilha vazia ignora Esc");

const { buildBadges } = m.badges;
const loud = { days_in_stage: 3, patient_idle_days: 2, stale: true, stale_kind: "patient_silence", task_overdue: true, no_next_action: true, new_activity: true };
const allBadges = { with_bot: true, lgpd_pending: true, commercial_blocked: true, bot_outcome: "agendado" };
const withTasks = buildBadges({ signals: loud, badges: allBadges, reason: { key: "price", label: "Preço" }, tasksVisible: true });
check(withTasks.length === 9 && withTasks.every((badge) => typeof badge.text === "string" && badge.text.trim().length > 3), "todo selo tem texto (cor so reforca)");
check(withTasks.find((badge) => badge.key === "bot_outcome").text === "Bot: agendou" && withTasks.find((badge) => badge.key === "reason").text === "Motivo: Preço", "rotulos de bot e motivo");
const noTasks = buildBadges({ signals: loud, badges: allBadges, reason: null, tasksVisible: false });
check(!noTasks.some((badge) => badge.key === "task_overdue" || badge.key === "no_next_action"), "sem follow-up: nenhum selo de tarefa");

const { searchProblem } = m.search;
same([searchProblem(""), searchProblem("  "), searchProblem("ab"), searchProblem("1234"), searchProblem("Jo")], ["", "", "", "", ""], "busca valida (picker v2.1)");
check(searchProblem("a") !== "" && searchProblem("123") !== "" && searchProblem("-") !== "", "busca curta pede mais texto sem request");

// ---------------------------------------------------------------------------
// 8. Formatacao (fuso da clinica, Intl em cache)
// ---------------------------------------------------------------------------
const instant = Date.UTC(2026, 9, 26, 15, 4);
same([f.parseInstant("2026-10-26T15:04:00"), f.parseInstant("2026-10-26T15:04:00Z"), f.parseInstant("2026-10-26T15:04:00+00:00"), f.parseInstant("2026-10-26T12:04:00-03:00")],
  [instant, instant, instant, instant], "ISO sem fuso = UTC (como o backend)");
same([f.parseInstant(""), f.parseInstant("lixo"), f.parseInstant(null), f.parseInstant(undefined)], [null, null, null, null], "data invalida = null");
check(f.formatClock("2026-10-26T15:04:00+00:00") === "12:04" && f.formatClock(null) === "--:--", "\"dados de HH:MM\" no fuso de Sao Paulo");
check(f.currentMonth(Date.UTC(2026, 10, 1, 2, 59)) === "2026-10" && f.currentMonth(Date.UTC(2026, 10, 1, 3, 0)) === "2026-11", "mes corrente no fuso da clinica");
same([f.shiftMonth("2026-01", -1), f.shiftMonth("2026-12", 1), f.shiftMonth("lixo", 1)], ["2025-12", "2027-01", "lixo"], "navegacao de meses");
check(!f.isMonthKey("2026-13") && f.isMonthKey("2026-09") && f.formatMonth("2026-10") === "outubro de 2026", "rotulo do mes");
same([f.formatCount(1234), f.formatCount(null), f.formatPercent(1, 3), f.formatPercent(1, 0)], ["1.234", "—", "33%", "—"], "numeros e percentuais pt-BR");
same([f.daysInStageText(0), f.daysInStageText(1), f.daysInStageText(5), f.daysInStageText(null)],
  ["há menos de 1 dia na etapa", "há 1 dia na etapa", "há 5 dias na etapa", "tempo na etapa não informado"], "texto literal do tempo na etapa");
check(f.elapsedDays("2026-10-20T12:00:00Z", Date.UTC(2026, 9, 26, 11, 59)) === 5 && f.elapsedDays(null) === null, "dias decorridos (piso)");
check(/26\/10\/2026/.test(f.formatDateTime("2026-10-26T15:04:00Z")) && f.formatDateTime(null) === "Data não informada", "data e hora curtas");

// ---------------------------------------------------------------------------
// 9. Catalogo puro (catalog.ts): visibilidade, filtro "stage:", Mover para…,
//    desfechos do Encerrar atendimento, pre-selecao, congelamento e payload
// ---------------------------------------------------------------------------
// Visibilidade (mesma regra do funnel_catalog.stage_visible + `visible`).
check(c.stageVisible({ visibility_permission: null }, () => false) && c.stageVisible(null, () => false), "etapa sem permissao de visibilidade aparece para quem ve o funil");
check(!c.stageVisible({ visibility_permission: "ver_contatos_agente_funil" }, () => false) && c.stageVisible({ visibility_permission: "ver_contatos_agente_funil" }, allowAll), "Novo contato so com ver_contatos_agente_funil");
check(!c.stageVisible({ visibility_permission: null, visible: false }, allowAll) && c.stageVisible({ visibility_permission: null, visible: true }, allowAll), "`visible` do /config tambem precisa permitir");
check(stageDefs.new.visible === true && clinicOperator.stages.find((stage) => stage.key === "new").visible === false, "fixture: /config do operador marca Novo contato invisivel");

// Filtro da barra lateral (valores "stage:<chave>", nunca colidem com o legado).
check(c.STAGE_FILTER_PREFIX === "stage:", "prefixo do filtro = stage:");
const operatorOptions = c.stageFilterOptions(clinicOperator, operatorHas);
same(operatorOptions.map((option) => option.value), ["stage:in_service", "stage:awaiting_followup", "stage:scheduled", "stage:loyal", "stage:non_converted", "stage:disqualified", "stage:unclassified"], "filtro do operador: etapas visiveis com prefixo, sem Novo contato");
check(operatorOptions.find((option) => option.value === "stage:scheduled").label === "Cliente Agendado", "opcao do filtro usa o rotulo do catalogo");
same(c.stageFilterOptions(clinic, allowAll).map((option) => option.value)[0], "stage:new", "supervisor: Novo contato no filtro");
check(!c.stageFilterOptions(clinic, operatorHas).some((option) => option.value === "stage:new"), "toggle tirado ao vivo (antes do /config novo): Novo contato sai do filtro");
check(!c.stageFilterOptions({ ...clinic, stages: clinic.stages.map((stage) => (stage.key === "loyal" ? { ...stage, active: false } : stage)) }, allowAll).some((option) => option.value === "stage:loyal"), "etapa inativa fora do filtro");
same(c.stageFilterOptions(null, allowAll), [], "sem catalogo = sem opcoes de etapa");
same([c.stageFromFilter("stage:new"), c.stageFromFilter("stage:"), c.stageFromFilter("novo"), c.stageFromFilter("convertido"), c.stageFromFilter(null), c.stageFromFilter(undefined)], ["new", null, null, null, null, null], "stageFromFilter");
check(c.filterValueValid("", operatorOptions, "nao_lidos") && c.filterValueValid("nao_lidos", operatorOptions, "nao_lidos") && c.filterValueValid("stage:scheduled", operatorOptions, "nao_lidos"), "filtro valido: vazio, Nao lidas ou etapa oferecida");
check(!c.filterValueValid("stage:new", operatorOptions, "nao_lidos") && !c.filterValueValid("convertido", operatorOptions, "nao_lidos"), "com catalogo: etapa invisivel ou valor legado = limpa o filtro");
check(c.filterValueValid("convertido", null, "nao_lidos") && !c.filterValueValid("stage:scheduled", null, "nao_lidos"), "sem catalogo: legado vale, stage: limpa");
check(c.contactMatchesFilter("", { crm_stage: undefined, qualification: "" }) && c.contactMatchesFilter("", null), "filtro vazio = todos");
check(c.contactMatchesFilter("stage:scheduled", { crm_stage: "scheduled", qualification: "novo" }) && !c.contactMatchesFilter("stage:scheduled", { crm_stage: "loyal", qualification: "convertido" }), "stage: compara crm_stage");
check(!c.contactMatchesFilter("stage:new", { crm_stage: undefined, qualification: "novo" }) && !c.contactMatchesFilter("stage:new", null), "contato fora do funil nao entra em nenhuma etapa");
check(c.contactMatchesFilter("novo", { crm_stage: "scheduled", qualification: "" }) && c.contactMatchesFilter("convertido", { crm_stage: undefined, qualification: "convertido" }) && !c.contactMatchesFilter("convertido", { crm_stage: "scheduled", qualification: "novo" }), "valor legado compara qualification (vazio = novo)");
same([c.contactStageLabel(clinic, "loyal"), c.contactStageLabel(clinic, null), c.contactStageLabel(clinic, "gone"), c.contactStageLabel(null, "new")],
  ["Paciente em acompanhamento", "Fora do funil", "Etapa fora do catálogo", "Etapa fora do catálogo"], "rotulo do chip (chat e barra lateral)");

// "Mover para…": ativas, escolhiveis e VISIVEIS; a atual so para corrigir motivo.
same(keysOf(c.moveTargets(clinicOperator, "in_service")), ["awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"], "operador: sem Novo contato (invisivel), sem a atual, sem A classificar");
same(keysOf(c.moveTargets(clinic, "in_service")), ["new", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"], "supervisor: Novo contato e destino");
same(keysOf(c.moveTargets(clinic, "non_converted")), ["new", "in_service", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"], "Nao convertido atual entra (corrigir motivo)");
same(keysOf(c.moveTargets(clinic, null)), ["new", "in_service", "awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"], "Incluir no funil: todos os destinos manuais");
check(!keysOf(c.moveTargets({ ...clinic, stages: clinic.stages.map((stage) => (stage.key === "loyal" ? { ...stage, active: false } : stage)) }, "new")).includes("loyal") && c.moveTargets(null, "new").length === 0, "etapa inativa nao e destino; sem catalogo = nenhum");

// Desfechos do encerramento (fc.close_outcomes) e modo do modal.
const outcomeKeys = ["awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"];
same(keysOf(c.closeOutcomeStages(clinic)), outcomeKeys, "desfechos do Encerrar = close_outcome, na ordem do catalogo");
same(keysOf(c.closeOutcomeStages(clinicOperator)), outcomeKeys, "desfechos nao dependem da visibilidade no quadro");
same(c.closeOutcomeStages({ ...clinic, legacy_qualification_sync: false }), [], "template sem sync do legado (explicito) = encerramento legado");
same(keysOf(c.closeOutcomeStages({ ...clinic, legacy_qualification_sync: undefined })), outcomeKeys, "payload sem o campo nao desliga (so false explicito)");
check(!keysOf(c.closeOutcomeStages({ ...clinic, stages: clinic.stages.map((stage) => (stage.key === "disqualified" ? { ...stage, active: false } : stage)) })).includes("disqualified"), "desfecho inativo sai do modal");
same(c.closeOutcomeStages({ ...clinic, stages: clinic.stages.map(({ close_outcome, ...stage }) => stage) }), [], "catalogo sem close_outcome (payload antigo) = nenhum desfecho");
same(c.closeOutcomeStages(null), [], "sem catalogo = nenhum desfecho");
const ready = { status: "ready", catalog: clinic };
same([c.closeFormMode({ status: "off", catalog: null }, {}), c.closeFormMode({ status: "loading", catalog: null }, {}), c.closeFormMode(ready, {}), c.closeFormMode({ status: "ready", catalog: { ...clinic, legacy_qualification_sync: false } }, {})],
  ["legacy", "loading", "funnel", "legacy"], "modo do modal: sem funil, carregando, funil, template sem sync");
same([c.closeFormMode(ready, { is_backup: true }), c.closeFormMode(ready, { is_archived: 1 }), c.closeFormMode(ready, {}, { is_backup: true }), c.closeFormMode(ready, null)],
  ["legacy", "legacy", "legacy", "legacy"], "backup/arquivado (contato ou thread) seguem o legado");
check(c.closeGateApplies(clinic, { crm_stage: undefined, qualification: "convertido" }) && c.closeGateApplies(clinic, { crm_stage: "in_service", qualification: "em_atendimento" }) && c.closeGateApplies(clinic, { crm_stage: "new", qualification: "convertido" }), "gate: sem etapa ou etapa que nao e desfecho");
check(c.closeGateApplies(clinic, { crm_stage: "scheduled", qualification: "em_atendimento" }) && c.closeGateApplies(clinic, { crm_stage: "scheduled", qualification: "" }), "gate: desfecho no funil mas legado novo/em_atendimento");
check(!c.closeGateApplies(clinic, { crm_stage: "scheduled", qualification: "convertido" }) && !c.closeGateApplies(clinic, { crm_stage: "non_converted", qualification: "nao_convertido" }), "sem gate: etapa ja e desfecho e o legado tambem");
check(c.closeOpensModal({ status: "loading", catalog: null }, { qualification: "convertido" }), "menu Fechar: catalogo carregando = modal");
check(c.closeOpensModal(ready, { crm_stage: "in_service", qualification: "em_atendimento" }) && !c.closeOpensModal(ready, { crm_stage: "loyal", qualification: "convertido" }), "menu Fechar com funil espelha o gate");
check(c.closeOpensModal({ status: "off", catalog: null }, { qualification: "" }) && !c.closeOpensModal({ status: "off", catalog: null }, { qualification: "convertido" }), "menu Fechar sem funil: gate legado (novo/em_atendimento)");
check(!c.closeOpensModal(ready, { crm_stage: "new", qualification: "convertido", is_backup: true }), "backup: gate legado mesmo com funil");

// Pre-selecao, escolha efetiva e nota so em Outro.
const nonConverted = stageDefs.non_converted;
same(keysOf(c.selectableReasons(clinic, nonConverted)), templateReasons.filter((reason) => reason.selectable).map((reason) => reason.key), "motivos escolhiveis (sem Motivo nao registrado)");
same(keysOf(c.selectableReasons(clinic, { ...nonConverted, reason_keys: ["price", "other", "not_informed"] })), ["price", "other"], "reason_keys da etapa limita os motivos");
same([c.initialCloseTarget(clinic, { stage: "scheduled", version: 4 }), c.initialCloseTarget(clinic, { stage: "in_service", version: 4 }), c.initialCloseTarget(clinic, { stage: null, version: 0 })], ["scheduled", "", ""], "pre-seleciona a etapa atual so quando ja e desfecho");
const draft0 = c.EMPTY_CLOSE_DRAFT;
same(c.effectiveCloseChoice(clinic, draft0, { stage: "in_service", version: 3 }), { target: "", reason: "", note: "", appointment: "" }, "sem desfecho escolhido");
same(c.effectiveCloseChoice(clinic, { ...draft0, appointment: "procedure" }, { stage: "scheduled", version: 4 }), { target: "scheduled", reason: "", note: "", appointment: "" }, "manter Cliente Agendado: sem tipo de compromisso");
same(c.effectiveCloseChoice(clinic, { target: "scheduled", note: "x", appointment: "consultation" }, { stage: "in_service", version: 3 }), { target: "scheduled", reason: "", note: "", appointment: "consultation" }, "Cliente Agendado: compromisso opcional, nota nunca");
same(c.effectiveCloseChoice(clinic, draft0, { stage: "non_converted", version: 4, reason: "price" }), { target: "non_converted", reason: "price", note: "", appointment: "" }, "manter Nao convertido: motivo atual pre-selecionado");
same(c.effectiveCloseChoice(clinic, draft0, { stage: "non_converted", version: 4 }), { target: "non_converted", reason: "", note: "", appointment: "" }, "motivo atual desconhecido: a pessoa escolhe");
same(c.effectiveCloseChoice(clinic, { target: "non_converted", reason: "other", note: "pensando", appointment: "consultation" }, { stage: "in_service", version: 3 }), { target: "non_converted", reason: "other", note: "pensando", appointment: "" }, "Outro: nota vale; compromisso nao");
same(c.effectiveCloseChoice(clinic, { target: "non_converted", reason: "price", note: "x", appointment: "" }, { stage: "in_service", version: 3 }).note, "", "motivo sem nota descarta o texto");
same(c.effectiveCloseChoice(clinic, { target: "non_converted", reason: "not_informed", note: "", appointment: "" }, { stage: "in_service", version: 3 }).reason, "", "motivo nao escolhivel descartado");
same(c.effectiveCloseChoice(clinic, { target: "awaiting_followup", reason: "price", note: "x", appointment: "" }, { stage: "in_service", version: 3 }), { target: "awaiting_followup", reason: "", note: "", appointment: "" }, "etapa sem motivo descarta motivo e nota");
check(c.closeNoteAllowed(clinic, { target: "non_converted", reason: "other" }, { stage: "in_service", version: 3 }) && !c.closeNoteAllowed(clinic, { target: "non_converted", reason: "price" }, { stage: "in_service", version: 3 }), "nota so no motivo Outro");
check(!c.closeNoteAllowed(clinic, { target: "scheduled", reason: "other" }, { stage: "in_service", version: 3 }) && !c.closeNoteAllowed(clinic, { target: "", reason: "other" }, { stage: null, version: 0 }), "nota nunca fora de etapa com motivo");
check(!c.closeNoteAllowed(clinic, { target: "non_converted", reason: "other" }, { stage: "non_converted", version: 4, reason: "other" }), "manter o MESMO Outro: sem nota (nada e gravado)");
check(c.closeNoteAllowed(clinic, { target: "non_converted", reason: "other" }, { stage: "non_converted", version: 4, reason: "price" }) && c.closeNoteAllowed(clinic, { target: "non_converted", reason: "other" }, { stage: "non_converted", version: 4 }), "corrigir para Outro: nota permitida");
check(c.closeKeepsStage({ target: "scheduled" }, { stage: "scheduled", version: 4 }) && !c.closeKeepsStage({ target: "" }, { stage: null, version: 0 }) && !c.closeKeepsStage({ target: "loyal" }, { stage: "scheduled", version: 4 }), "closeKeepsStage");

// Rascunho: trocar de desfecho recomeca motivo/nota/compromisso; motivo limpa nota.
let closeDraft = c.patchCloseDraft(draft0, { target: "non_converted" });
check(closeDraft.target === "non_converted" && closeDraft.reason === undefined && closeDraft.note === "" && closeDraft.appointment === "", "escolher desfecho");
closeDraft = c.patchCloseDraft(closeDraft, { reason: "other" });
closeDraft = c.patchCloseDraft(closeDraft, { note: "ligar em março" });
check(closeDraft.reason === "other" && closeDraft.note === "ligar em março", "motivo Outro + nota");
const priceDraft = c.patchCloseDraft(closeDraft, { reason: "price" });
check(priceDraft.reason === "price" && priceDraft.note === "", "trocar de motivo limpa a nota");
check(c.patchCloseDraft(closeDraft, { target: "non_converted" }).note === "ligar em março", "mesmo desfecho nao recomeca");
const scheduledDraft = c.patchCloseDraft(c.patchCloseDraft(closeDraft, { target: "scheduled" }), { appointment: "procedure" });
check(scheduledDraft.target === "scheduled" && scheduledDraft.reason === undefined && scheduledDraft.note === "" && scheduledDraft.appointment === "procedure", "trocar de desfecho recomeca motivo e nota");
check(c.patchCloseDraft(scheduledDraft, { target: "loyal" }).appointment === "", "trocar de desfecho limpa o compromisso");

// 409 stale_version: a escolha VISTA (inclusive pre-selecao) fica fixa.
const seenBase = { stage: "scheduled", version: 5 };
const seenChoice = c.effectiveCloseChoice(clinic, draft0, seenBase);
const frozenDraft = c.freezeCloseDraft(draft0, seenChoice);
const serverBase = { stage: "loyal", version: 9 };
check(c.effectiveCloseChoice(clinic, draft0, serverBase).target === "loyal", "sem congelar, a pre-selecao seguiria a etapa nova do servidor");
check(frozenDraft.target === "scheduled" && c.effectiveCloseChoice(clinic, frozenDraft, serverBase).target === "scheduled", "congelada: o desfecho confirmado nao muda sozinho");
same(c.buildCloseFunnel(clinic, c.effectiveCloseChoice(clinic, frozenDraft, serverBase), serverBase), { to_stage: "scheduled", expected_version: 9, reason: null, reason_note: null, appointment_kind: null }, "Reaplicar: mesma escolha a partir da versao do servidor");
const reasonBase = { stage: "non_converted", version: 4, reason: "price" };
const reasonFrozen = c.freezeCloseDraft(draft0, c.effectiveCloseChoice(clinic, draft0, reasonBase));
const reasonServer = { stage: "non_converted", version: 5 };
check(c.effectiveCloseChoice(clinic, draft0, reasonServer).reason === "" && c.effectiveCloseChoice(clinic, reasonFrozen, reasonServer).reason === "price", "motivo pre-selecionado tambem congela");
const noteFrozen = c.freezeCloseDraft({ target: "non_converted", reason: "other", note: "curto", appointment: "" }, { target: "non_converted", reason: "other", note: "curto", appointment: "" });
check(noteFrozen.note === "curto" && noteFrozen.reason === "other", "nota digitada preservada no congelamento");
check(c.freezeCloseDraft(draft0, c.effectiveCloseChoice(clinic, draft0, { stage: "in_service", version: 2 })).target === undefined, "sem escolha vista, nada a congelar");

// Problemas e payload `funnel` do set-attendance (sem operation_id).
const fromService = { stage: "in_service", version: 3 };
same([c.closeChoiceProblem(clinic, { target: "", reason: "", note: "", appointment: "" }, fromService), c.closeChoiceProblem(clinic, { target: "in_service", reason: "", note: "", appointment: "" }, fromService)],
  ["Escolha o desfecho.", "Escolha o desfecho."], "desfecho obrigatorio e so entre os de encerramento");
same([c.closeChoiceProblem(clinic, { target: "non_converted", reason: "", note: "", appointment: "" }, fromService), c.closeChoiceProblem(clinic, { target: "non_converted", reason: "not_informed", note: "", appointment: "" }, fromService)],
  ["Informe o motivo.", "Informe o motivo."], "Nao convertido exige motivo escolhivel");
same([c.closeChoiceProblem(clinic, { target: "non_converted", reason: "other", note: "x".repeat(121), appointment: "" }, fromService), c.closeChoiceProblem(clinic, { target: "non_converted", reason: "other", note: "a\tb", appointment: "" }, fromService)],
  ["Use até 120 caracteres, sem quebra de linha.", "Use até 120 caracteres, sem quebra de linha."], "nota: ate 120, sem controle");
same([c.closeChoiceProblem(clinic, { target: "non_converted", reason: "other", note: `  ${"x".repeat(120)}  `, appointment: "" }, fromService), c.closeChoiceProblem(clinic, { target: "non_converted", reason: "price", note: "a\tb", appointment: "" }, fromService), c.closeChoiceProblem(clinic, { target: "scheduled", reason: "", note: "", appointment: "" }, fromService)],
  ["", "", ""], "120 apos trim vale; nota ignorada fora de Outro; desfecho sem motivo ok");
check(c.CLOSE_NOTE_MAX === 120 && Number(/^NOTE_MAX = (\d+)/m.exec(pyCatalog)?.[1]) === 120, "limite da nota igual ao NOTE_MAX do backend");
const buildFunnel = (choice, baseState) => c.buildCloseFunnel(clinic, { target: "", reason: "", note: "", appointment: "", ...choice }, baseState);
same(buildFunnel({ target: "scheduled", appointment: "consultation" }, fromService), { to_stage: "scheduled", expected_version: 3, reason: null, reason_note: null, appointment_kind: "consultation" }, "payload: Cliente Agendado com consulta");
same(buildFunnel({ target: "loyal" }, fromService), { to_stage: "loyal", expected_version: 3, reason: null, reason_note: null, appointment_kind: null }, "payload: Paciente em acompanhamento");
same(buildFunnel({ target: "non_converted", reason: "other", note: "  vai pensar  " }, fromService), { to_stage: "non_converted", expected_version: 3, reason: "other", reason_note: "vai pensar", appointment_kind: null }, "payload: Outro com nota (trim)");
same(buildFunnel({ target: "non_converted", reason: "other", note: "   " }, fromService).reason_note, null, "nota em branco = null");
same(buildFunnel({ target: "scheduled", appointment: "procedure" }, { stage: "scheduled", version: 4 }), { to_stage: "scheduled", expected_version: 4, reason: null, reason_note: null, appointment_kind: null }, "manter a etapa sem motivo: reason null e sem compromisso");
same(buildFunnel({ target: "disqualified" }, { stage: "disqualified", version: 2 }), { to_stage: "disqualified", expected_version: 2, reason: null, reason_note: null, appointment_kind: null }, "manter Nao qualificado: reason null");
same(buildFunnel({ target: "non_converted", reason: "price" }, { stage: "non_converted", version: 6, reason: "price" }), { to_stage: "non_converted", expected_version: 6, reason: "price", reason_note: null, appointment_kind: null }, "manter Nao convertido: envia o motivo atual (backend exige)");
same(buildFunnel({ target: "non_converted", reason: "no_show" }, { stage: "non_converted", version: 6, reason: "price" }).reason, "no_show", "manter etapa com outro motivo = correcao do motivo");
same([buildFunnel({ target: "loyal" }, { stage: null, version: 0 }).expected_version, buildFunnel({ target: "loyal" }, { stage: "new", version: -1 }).expected_version, buildFunnel({ target: "loyal" }, { stage: "new", version: 1.5 }).expected_version, buildFunnel({ target: "loyal" }, { stage: "new", version: undefined }).expected_version], [0, 0, 0, 0], "expected_version invalida = 0");
same([buildFunnel({ target: "" }, fromService), buildFunnel({ target: "non_converted" }, fromService), buildFunnel({ target: "unclassified" }, fromService)], [null, null, null], "escolha invalida = sem payload");
same([c.stageLegacyQualification(clinic, "scheduled"), c.stageLegacyQualification(clinic, "loyal"), c.stageLegacyQualification(clinic, "awaiting_followup"), c.stageLegacyQualification(clinic, "disqualified"), c.stageLegacyQualification(clinic, "new"), c.stageLegacyQualification(clinic, ""), c.stageLegacyQualification(null, "scheduled")],
  ["convertido", "convertido", "nao_convertido", "nao_qualificado", null, null, null], "legado equivalente para o patch local do contato");
same(c.contactStagePatch({ key: "scheduled", version: 6, changed_at: "2026-10-26T12:00:00+00:00", source: "user", label: "Cliente Agendado" }), { crm_stage: "scheduled", crm_stage_version: 6, crm_stage_changed_at: "2026-10-26T12:00:00+00:00", crm_stage_source: "user" }, "patch da etapa a partir da resposta do encerramento");
same(c.contactStagePatch({ key: "loyal", version: 2, changed_at: null, source: "" }), { crm_stage: "loyal", crm_stage_version: 2 }, "patch sem data/origem: so etapa e versao");
same([c.contactStagePatch(null), c.contactStagePatch({ key: "Bad", version: 1 }), c.contactStagePatch({ key: "loyal", version: -1 }), c.contactStagePatch({ key: "loyal", version: 1.5 }), c.contactStagePatch({ key: "loyal" })], [{}, {}, {}, {}, {}], "payload incompleto = nada a aplicar");

// ---------------------------------------------------------------------------
// 10. Formulario da aba "Etapas" (settingsForm.ts)
// ---------------------------------------------------------------------------
check(s.LABEL_MAX === Number(/^LABEL_MAX = (\d+)/m.exec(pyCatalog)?.[1]) && s.DESCRIPTION_MAX === Number(/^DESCRIPTION_MAX = (\d+)/m.exec(pyCatalog)?.[1]) && s.LABEL_MAX === 40 && s.DESCRIPTION_MAX === 200, "limites 40/200 iguais aos do backend");
const settingsPayload = {
  version: 3, template: "clinic_v1",
  stage_labels: { scheduled: "Agendou", loyal: "   " }, stage_descriptions: { new: "Texto da clínica" }, reason_labels: { price: "Valor" },
  stages: savedSettings.stages, reasons: savedSettings.reasons,
};
const defaults = s.settingsDefaults(settingsPayload, null);
same(keysOf(defaults.stages), keysOf(templateStages), "padroes das etapas vem do GET /settings");
check(defaults.stages.find((stage) => stage.key === "scheduled").default_label === "Cliente Agendado" && defaults.reasons.find((reason) => reason.key === "other").default_label === "Outro", "padrao = texto do template");
const fromCatalog = s.settingsDefaults(null, { ...clinic, stages: clinic.stages.map((stage, index) => (index === 0 ? { ...stage, default_label: undefined, default_description: undefined } : stage)) });
check(fromCatalog.stages[0].default_label === "Novo contato" && fromCatalog.stages[0].default_description === stageDefs.new.description && fromCatalog.reasons.length === templateReasons.length, "sem a lista no payload: padrao vem do catalogo");
same(keysOf(s.settingsDefaults({ stages: [{ key: "" }, null, { key: "x" }], reasons: [] }, null).stages), ["x"], "itens sem chave descartados");
check(s.settingsDefaults({ stages: [{ key: "x" }], reasons: [] }, null).stages[0].default_label === "x", "padrao sem rotulo = a chave");
const loaded = s.settingsDraft(settingsPayload, defaults);
same([loaded.stage_labels.scheduled, loaded.stage_labels.loyal, loaded.stage_descriptions.new, loaded.stage_descriptions.loyal, loaded.reason_labels.price, loaded.reason_labels.other],
  ["Agendou", "Paciente em acompanhamento", "Texto da clínica", stageDefs.loyal.description, "Valor", "Outro"], "rascunho = texto da clinica ou, vazio, o padrao");
same(s.settingsBody(3, loaded, defaults), { version: 3, stage_labels: { scheduled: "Agendou" }, stage_descriptions: { new: "Texto da clínica" }, reason_labels: { price: "Valor" } }, "PUT: so o que difere do padrao, com a versao lida");
same([s.settingsBody(0, loaded, defaults).version, s.settingsBody(-2, loaded, defaults).version, s.settingsBody(1.5, loaded, defaults).version, s.settingsBody(NaN, loaded, defaults).version], [0, 0, 0, 0], "versao invalida = 0");
const edited = { ...loaded, stage_labels: { ...loaded.stage_labels, scheduled: "  Cliente Agendado ", loyal: " Em tratamento ", new: "" } };
same(s.settingsBody(3, edited, defaults).stage_labels, { loyal: "Em tratamento" }, "igual ao padrao (com espaco) ou vazio fica fora; texto vai com trim");
same(s.settingsBody(3, s.defaultDraft(defaults), defaults), { version: 3, stage_labels: {}, stage_descriptions: {}, reason_labels: {} }, "Restaurar todos os padroes = corpo vazio");
same(s.defaultDraft(defaults).stage_labels.scheduled, "Cliente Agendado", "rascunho padrao");
const savedBody = s.settingsBody(3, loaded, defaults);
check(s.sameSettings(savedBody, { ...savedBody, version: 9 }) && s.sameSettings(savedBody, { version: 3, reason_labels: { price: "Valor" }, stage_descriptions: { new: "Texto da clínica" }, stage_labels: { scheduled: "Agendou" } }), "sameSettings: ignora versao e ordem");
check(!s.sameSettings(savedBody, { ...savedBody, stage_labels: { scheduled: "Agendou!" } }), "sameSettings: texto diferente");
const limits = { ...loaded, stage_labels: { ...loaded.stage_labels, scheduled: "a".repeat(40), loyal: "b".repeat(41), new: `  ${"c".repeat(40)}  ` }, stage_descriptions: { ...loaded.stage_descriptions, scheduled: "d".repeat(200), loyal: "e".repeat(201), new: "linha\u0007x" }, reason_labels: { ...loaded.reason_labels, price: "f".repeat(41) } };
same(s.settingsProblems(limits), { "stage_labels.loyal": "Use até 40 caracteres.", "stage_descriptions.loyal": "Use até 200 caracteres.", "stage_descriptions.new": "Sem quebra de linha.", "reason_labels.price": "Use até 40 caracteres." }, "limites 40/200 (com trim) e sem controle");
same(s.settingsProblems(loaded), {}, "rascunho carregado sem problemas");
same([s.cleanSettingsText("a\nb\r\nc\td"), s.cleanSettingsText("ok")], ["a b c d", "ok"], "colar com quebra de linha vira espaco");
check(s.isSettingsPayload(settingsPayload) && !s.isSettingsPayload({ ...settingsPayload, version: "3" }) && !s.isSettingsPayload({ version: 3 }) && !s.isSettingsPayload(null), "isSettingsPayload");
// 409: reaplica so o que ESTA pessoa mudou sobre a versao do servidor.
const theirs = s.settingsDraft({ ...settingsPayload, version: 4, stage_labels: { scheduled: "Agendou", loyal: "Acompanhamento" }, reason_labels: { price: "Preço alto" } }, defaults);
const mine = { ...loaded, stage_labels: { ...loaded.stage_labels, scheduled: "Agendou consulta", in_service: " Em atendimento " }, stage_descriptions: { ...loaded.stage_descriptions } };
const rebased = s.rebaseSettingsDraft(mine, loaded, theirs);
same([rebased.stage_labels.scheduled, rebased.stage_labels.loyal, rebased.reason_labels.price, rebased.stage_labels.in_service, rebased.stage_descriptions.new],
  ["Agendou consulta", "Acompanhamento", "Preço alto", "Em atendimento", "Texto da clínica"], "rebase: minhas mudancas por cima; o resto do servidor; espaco nao conta como mudanca");
same(s.rebaseSettingsDraft(mine, null, theirs), theirs, "sem base carregada: vale o servidor");
same(Object.keys(s.rebaseSettingsDraft({ ...mine, stage_labels: { ...mine.stage_labels, gone: "x" } }, loaded, theirs).stage_labels), Object.keys(theirs.stage_labels), "chave que nao existe mais no servidor sai");
// Textos recem-salvos sobre um /config com cache velho (resolve_funnel local).
const staleCatalog = clinicCatalog(allowAll, { overrides_version: 2 });
const withTexts = s.catalogWithSettings(staleCatalog, settingsPayload);
check(withTexts !== staleCatalog && withTexts.overrides_version === 3, "catalogo com overrides_version menor recebe os textos salvos");
same([withTexts.stages.find((stage) => stage.key === "scheduled").label, withTexts.stages.find((stage) => stage.key === "loyal").label, withTexts.stages.find((stage) => stage.key === "new").description, withTexts.reasons.find((reason) => reason.key === "price").label, withTexts.reasons.find((reason) => reason.key === "other").label],
  ["Agendou", "Paciente em acompanhamento", "Texto da clínica", "Valor", "Outro"], "texto da clinica ou, vazio, o padrao");
check(withTexts.stages.find((stage) => stage.key === "scheduled").close_outcome === true && staleCatalog.stages.find((stage) => stage.key === "scheduled").label === "Cliente Agendado", "regras intactas e catalogo original sem mutacao");
check(s.catalogWithSettings(clinicCatalog(allowAll, { overrides_version: 3 }), settingsPayload).overrides_version === 3 && s.catalogWithSettings(clinicCatalog(allowAll, { overrides_version: 3 }), settingsPayload).stages.find((stage) => stage.key === "scheduled").label === "Cliente Agendado", "catalogo ja na versao fica como veio");
check(s.catalogWithSettings(staleCatalog, { version: "x" }) === staleCatalog && s.catalogWithSettings(staleCatalog, null) === staleCatalog, "payload salvo invalido = catalogo intacto");

// ---------------------------------------------------------------------------
// 11. Guardas estaticas do contrato (codigo do funil no frontend)
// ---------------------------------------------------------------------------
const featureDir = new URL("../frontend/src/features/funnel/", import.meta.url);
const componentDir = new URL("../frontend/src/components/funnel/", import.meta.url);
// Comentarios citam de proposito o que NAO se faz: as guardas olham so codigo.
const code = (text) => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
const sources = [
  ...readdirSync(featureDir).filter((name) => /\.tsx?$/.test(name)).map((name) => [name, code(readFileSync(new URL(name, featureDir), "utf8"))]),
  ...readdirSync(componentDir).filter((name) => /\.tsx?$/.test(name)).map((name) => [name, code(readFileSync(new URL(name, componentDir), "utf8"))]),
];
const sourceOf = (name) => sources.find(([file]) => file === name)?.[1] || "";
check(["FunnelEntry.tsx", "FunnelStageCard.tsx", "FunnelCloseFields.tsx", "FunnelSettingsPanel.tsx", "catalog.ts", "settingsForm.ts"].every((name) => sources.some(([file]) => file === name)), "modulos v2 existem (entrada, cartao, desfecho, aba Etapas, catalogo, formulario)");
for (const [name, text] of sources) {
  check(!/conversation\/open|openConversationForContact/.test(text), `${name}: nunca /api/wa/conversation/open`);
  check(!/visibilitychange/.test(text), `${name}: sem refresh em visibilitychange`);
  check(name === "ContactDrawer.tsx" || !/setInterval\(/.test(text), `${name}: sem polling (so o drawer revalida acesso)`);
  check(!/can_confirm_conversion|confirmar_conversao_funil|\brestricted\b/.test(text), `${name}: sem conversao restrita (v1)`);
}
const drawerSource = sourceOf("ContactDrawer.tsx");
check(/setInterval\(.*,\s*30000\)/.test(drawerSource) && /visibilityState !== "visible"/.test(drawerSource), "drawer revalida a cada 30 s so com a aba visivel");
for (const name of ["FunnelCard.tsx", "FunnelColumn.tsx", "FunnelBoard.tsx", "FunnelSearch.tsx", "ContactDrawer.tsx", "FunnelStageCard.tsx", "FunnelSettingsPanel.tsx", "MoveStageDialog.tsx"]) {
  check(!/\bqualification\b/.test(sourceOf(name)), `${name}: nao mostra qualification`);
}
const cardSource = sourceOf("FunnelCard.tsx");
check(cardSource.includes("Dono do lead:") && cardSource.includes("Próxima tarefa:"), "rotulos do card: Dono do lead, Próxima tarefa");
const dialogSource = sourceOf("MoveStageDialog.tsx");
check(dialogSource.includes("Não registre dados clínicos") && /const targets = moveTargets\(catalog, base\.stage\);/.test(dialogSource), "Mover para…: destinos de moveTargets (sem etapa invisivel); nota avisa dados clinicos");
check(/stage\.description && <small>\{stage\.description\}<\/small>/.test(dialogSource), "Mover para…: texto explicativo sob cada opcao");
const closeFieldsSource = sourceOf("FunnelCloseFields.tsx");
check(/\{noteAllowed && <label[\s\S]*?Não registre dados clínicos\.[\s\S]*?<\/label>\}/.test(closeFieldsSource), "Encerrar: nota so quando permitida (Outro), com o aviso de dados clinicos");
check(/closeOutcomeStages\(catalog\)/.test(closeFieldsSource) && /stage\.description && <small>\{stage\.description\}<\/small>/.test(closeFieldsSource), "Encerrar: desfechos = close_outcome, com o texto explicativo");
const stageCard = sourceOf("FunnelStageCard.tsx");
check(stageCard.includes("Classificação comercial do paciente") && stageCard.includes("O desfecho do encerramento do atendimento vira a etapa") && stageCard.includes("Incluir no funil") && stageCard.includes("Fora do funil"), "cartao: subtitulo v2, Fora do funil e Incluir no funil");
check(/if \(!access\.available\) return null;/.test(sourceOf("FunnelEntry.tsx")), "botao da TopBar some quando indisponivel");
const panelSource = sourceOf("FunnelPanel.tsx");
check(/REFRESH_LOCK_MS = 10_000/.test(panelSource) && /Dados de \{formatClock\(board\.generatedAt\)\}/.test(panelSource), "Atualizar com trava de 10 s e \"dados de HH:MM\"");
check(/capabilities\?\.can_dashboard/.test(panelSource), "painel gerencial so com can_dashboard");
check(/const canConfigure = capabilities\?\.can_configure === true;/.test(panelSource) && /\{canConfigure && <div[^\n]*\n\s*\{settingsVisited\.current && <FunnelSettingsPanel /.test(panelSource), "aba Etapas so com can_configure");
check(sources.filter(([, text]) => text.includes("<FunnelSettingsPanel")).length === 1, "FunnelSettingsPanel so montado pelo painel do funil");
check(/description && <InfoButton/.test(sourceOf("FunnelColumn.tsx")) && /description && <InfoButton/.test(stageCard), "botao ⓘ com o texto explicativo na coluna e no cartao");
check(/\{columns\.map\(\(column\) => <FunnelColumn /.test(sourceOf("FunnelBoard.tsx")) && !/catalog/.test(sourceOf("FunnelBoard.tsx")), "quadro desenha so as colunas devolvidas pelo /board");
const accessSource = sourceOf("useFunnelAccess.ts");
check(["mover_etapa_funil", "ver_contatos_agente_funil", "ver_dashboard_funil", "gerenciar_config_sistema"].every((key) => accessSource.includes(`can("${key}")`)), "chave do cache do /config muda com os toggles que alteram capabilities");

// Arquivos fora das pastas do funil (CRLF normalizado no read).
const frontendSrc = new URL("../frontend/src/", import.meta.url);
const allFrontend = readdirSync(frontendSrc, { recursive: true }).filter((name) => /\.tsx?$/.test(String(name))).map((name) => [String(name), readFileSync(new URL(String(name).replace(/\\/g, "/"), frontendSrc), "utf8")]);
check(allFrontend.length > 50, `frontend/src lido inteiro (${allFrontend.length} arquivos)`);
check(!allFrontend.some(([, text]) => /can_confirm_conversion|confirmar_conversao_funil/.test(text)), "nenhum can_confirm_conversion/confirmar_conversao_funil em frontend/src");
check(!allFrontend.some(([, text]) => /FunnelCloseNotice|O desfecho não altera o funil/.test(text)), "FunnelCloseNotice (\"o desfecho não altera o funil\") removido");
// Sem tirar comentarios: atributos como accept="image/*" abririam um falso
// bloco de comentario. As guardas abaixo procuram trechos exatos de codigo.
const app = read("../frontend/src/App.tsx");
const crmSource = read("../frontend/src/context/CrmContext.tsx");
check(/<FollowupEntry \/>\s*<FunnelEntry \/>/.test(app), "App: FunnelEntry logo depois do FollowupEntry da TopBar");
check(/<FollowupEntry contactId=\{selectedContact\.id\} variant="contact" \/>\s*<FunnelStageCard key=\{selectedContact\.id\} contact=\{selectedContact\} \/>/.test(app), "App: cartao logo apos o FollowupEntry do painel");
const hiddenKeys = /config\?\.feature_funnel && funnelEnabled \? \[\] : \[([^\]]*)\]/.exec(app)?.[1];
same(hiddenKeys && [...hiddenKeys.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]), ["ver_funil", "mover_etapa_funil", "ver_contatos_agente_funil", "ver_dashboard_funil"], "App: editor de perfis esconde as 4 chaves v2 sem funil");
check(/const funnelForm = useFunnelCloseForm\(contact, thread\);/.test(app) && /\{funnelMode \? <FunnelCloseFields form=\{funnelForm\} /.test(app), "App: modal Encerrar usa FunnelCloseFields com catalogo");
check(/const funnel = funnelForm\.prepare\(threadId\);\s*if \(!funnel\) return;\s*const ok = await setAttendance\(threadId, "fechado_manual", \{ notes, tags, tag_labels: tagLabels, funnel, legacyQualification: funnelForm\.legacyQualification \}, \{ onError: funnelForm\.handleError \}\);/.test(app), "App: encerramento manda `funnel` (sem qualification) e trata o erro no modal");
check(/const offerQualified = !\(config\?\.feature_funnel && funnelEnabled\);/.test(app) && /\{offerQualified \? <option value="qualificado">/.test(app), "App: Qualificado deixa de ser oferecido em tenant com funil");
check(/else if \(closeOpensModal\(funnelUi, selectedContact, selectedThread\)\) \{ setShowCloseModal\(true\); \}/.test(app), "App: menu Fechar abre o modal pelo gate");
check(/\{funnelUi\.status === "ready" \? <CollapsibleCard title="Notas do atendimento">[\s\S]*?: <CollapsibleCard title="Qualificacao">/.test(app), "App: com catalogo, o cartao Qualificacao sai (fica Notas do atendimento)");
check(/stageFilterOptions\(funnelUi\.catalog, \(permission\) => can\(permission as PermissionKey\)\)/.test(app) && /filterValueValid\(qualificationFilter, stageOptions, "nao_lidos"\)/.test(app), "App: filtro com as etapas visiveis e limpeza de valor invalido");
check((app.match(/contactStageLabel\(funnelUi\.catalog, /g) || []).length >= 2, "App: chips da barra lateral e do chat com o rotulo da etapa");
check(/const UNREAD_FILTER = "nao_lidos";/.test(crmSource) && /: contactMatchesFilter\(qualificationFilter, c\)\);/.test(crmSource), "CrmContext: filtro por contactMatchesFilter (stage: ou legado)");
check(/if \(outcome\.funnel\) body\.funnel = outcome\.funnel;\s*else body\.qualification = outcome\.qualification \?\? "";/.test(crmSource), "CrmContext: setAttendance repassa `funnel` no lugar da qualification");
check(/const stagePatch = contactStagePatch\(stage\);/.test(crmSource) && /if \(options\.onError\?\.\(e\)\) return false;/.test(crmSource), "CrmContext: patch da etapa da resposta e erro estruturado devolvido ao modal");
check(!/const LEAD_TEMPERATURE_META/.test(app) && /from "\.\/components\/LeadTemperatureDot"/.test(app), "App: usa o LeadTemperatureDot extraido");
const rbacKeys = [...read("../rbac.py").matchAll(/\("Funil", "([a-z_]+)"/g)].map((match) => match[1]);
const typesSource = read("../frontend/src/types.ts");
same(rbacKeys, ["ver_funil", "ver_contatos_agente_funil", "mover_etapa_funil", "ver_dashboard_funil"], "rbac.py: grupo Funil v2");
check(rbacKeys.every((key) => typesSource.includes(`| "${key}"`)) && !typesSource.includes("confirmar_conversao_funil"), "PermissionKey espelha as 4 chaves do grupo Funil do rbac.py");

// ---------------------------------------------------------------------------
// 12. Componentes de integracao (TSX real, JSX falso, fetch espionado): o
//     cartao "Etapa do funil", o desfecho do Encerrar e o botao da TopBar
// ---------------------------------------------------------------------------
const ui = await load(`
export { FunnelStageCard } from "./src/components/funnel/FunnelStageCard.tsx";
export { FunnelCloseFields, useFunnelCloseForm } from "./src/components/funnel/FunnelCloseFields.tsx";
export { FunnelEntry } from "./src/components/funnel/FunnelEntry.tsx";
export { InfoButton, MoveStageDialog, StageHistory, FUNNEL_CLOSE_ERROR_MESSAGES } from "./src/features/funnel/index.ts";
export { resetFunnelConfigCache } from "./src/features/funnel/useFunnelConfig.ts";
export { normalizeContact } from "./src/utils/normalization.ts";
export { apiErrorFromPayload } from "./src/api.ts";
`, { react: true, crm: true });

const fetchCalls = [];
let responder = () => ({ status: 404, body: { detail: { code: "out_of_scope", message: "x" } } });
globalThis.fetch = async (path, init = {}) => {
  let sent;
  try { sent = typeof init.body === "string" ? JSON.parse(init.body) : undefined; } catch { sent = init.body; }
  fetchCalls.push({ path: String(path), method: init.method || "GET", body: sent });
  const { status = 200, body: payload = {} } = responder(String(path), init) || {};
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
};
globalThis.document = { body: {} };
const settle = async () => { for (let turn = 0; turn < 6; turn += 1) await new Promise((resolve) => setImmediate(resolve)); };
function walk(node, visit) {
  if (node == null || typeof node === "boolean") return;
  if (Array.isArray(node)) { node.forEach((child) => walk(child, visit)); return; }
  if (typeof node !== "object") return;
  visit(node);
  walk(node.props?.children, visit);
}
function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return textOf(node.props?.children);
}
const elements = (tree, type) => { const found = []; walk(tree, (node) => { if (node.type === type) found.push(node); }); return found; };
const buttonNamed = (tree, label) => elements(tree, "button").find((node) => textOf(node.props.children).trim() === label) || null;
const simAuth = { currentUser: null };
function crm({ readOnly = false, feature = true, enabled = true, toggles = {}, user = { id: 5, firebase_uid: "uid-5", role: "operador" } } = {}) {
  const permissions = { ver_funil: true, mover_etapa_funil: true, ...toggles };
  return {
    bundle: { auth: simAuth }, config: { feature_funnel: feature, feature_followup: false }, readOnly, funnelEnabled: enabled,
    can: (key) => permissions[key] === true, canSeeAll: false, sessionUser: user,
  };
}
const configBody = (privileged = false, extra = {}) => ({ catalog: privileged ? clinicCatalog() : clinicCatalog(operatorHas), capabilities: capabilities({ privileged, can_see_agent_contacts: privileged, ...extra }) });
const historyBody = { items: [{ id: "stage_1", event_type: "crm_stage_changed", occurred_at: at(NOW), actor: { type: "user", user_id: 5, name: "Bia" }, from_stage: null, from_label: null, to_stage: "new", to_label: "Novo contato", reason: null, from_reason: null, reason_note: null, appointment_kind: null, entry_kind: "triage", rule_id: null, synthetic: false }], next_cursor: null };
const notFound = { status: 404, body: { detail: { code: "out_of_scope", message: "x" } } };
responder = (path) => (path === "/api/funnel/config" ? { body: configBody() } : path.startsWith("/api/funnel/contacts/") && path.includes("/history") ? { body: historyBody } : notFound);
const asContact = (record) => ui.normalizeContact({ id: 7, display_name: "Paciente Sim", assigned_to: null, assigned_to_uid: "", ...record }, String(record.id ?? 7));
const renderCard = (harness, contactValue) => harness.render(() => ui.FunnelStageCard({ contact: contactValue }));
// Modal "Encerrar atendimento": hook + campos no MESMO harness (como no App).
function closeHarness(contactValue, thread = null) {
  const harness = hookHarness();
  const reapplied = [];
  const render = () => harness.render(() => {
    const form = ui.useFunnelCloseForm(contactValue, thread);
    return { form, tree: ui.FunnelCloseFields({ form, disabled: false, onReapply: () => reapplied.push(form.choice.target) }) };
  });
  return { render, reapplied };
}
const radio = (tree, group, value) => elements(tree, "input").find((node) => node.props.type === "radio" && String(node.props.name).endsWith(`-${group}`) && node.props.value === value) || null;
const radios = (tree, group) => elements(tree, "input").filter((node) => node.props.type === "radio" && String(node.props.name).endsWith(`-${group}`)).map((node) => node.props.value);
const noteHelp = (tree) => elements(tree, "small").find((node) => String(node.props.id || "").endsWith("-note-help")) || null;

// Indisponivel: nada renderizado e NENHUMA requisicao (cartao, desfecho, botao).
for (const [options, why] of [[{ readOnly: true }, "Ver como"], [{ feature: false }, "flag global"], [{ enabled: false }, "tenant sem funil"], [{ toggles: { ver_funil: false } }, "sem ver_funil"]]) {
  globalThis.__simCrm = crm(options);
  check(renderCard(hookHarness(), asContact({})) === null, `cartao some: ${why}`);
  const closing = closeHarness(asContact({ crm_stage: "in_service", crm_stage_version: 2 })).render();
  check(closing.form.mode === "legacy" && closing.tree === null && closing.form.prepare("c1") === null, `Encerrar no modo legado: ${why}`);
  check(hookHarness().render(() => ui.FunnelEntry()) === null, `botao da TopBar some: ${why}`);
}
await settle();
check(fetchCalls.length === 0, "funil indisponivel: zero requisicoes");

// Disponivel, contato sem etapa e sem dono: 1 GET /config, "Fora do funil",
// "Incluir no funil" (expected_version 0) e historico so ao expandir.
ui.resetFunnelConfigCache();
globalThis.__simCrm = crm();
const cardHarness = hookHarness();
let unstaged = asContact({});
let tree = renderCard(cardHarness, unstaged);
check(textOf(tree).includes("Consultando o funil…") && textOf(tree).includes("Classificação comercial do paciente.") && !textOf(tree).includes("vira a etapa"), "cartao carregando, com o subtitulo");
await settle();
tree = renderCard(cardHarness, unstaged);
check(textOf(tree).includes("Classificação comercial do paciente. O desfecho do encerramento do atendimento vira a etapa."), "com catalogo: subtitulo diz que o desfecho do encerramento vira a etapa");
check(textOf(tree).includes("Fora do funil") && buttonNamed(tree, "Incluir no funil") && buttonNamed(tree, "Ver histórico"), "contato sem etapa: Fora do funil + Incluir no funil");
renderCard(hookHarness(), unstaged);
await settle();
same(fetchCalls.map((call) => `${call.method} ${call.path}`), ["GET /api/funnel/config"], "1 GET /config por sessao (2 cartoes) e nenhum historico sem expandir");
buttonNamed(tree, "Incluir no funil").props.onClick({ currentTarget: {} });
tree = renderCard(cardHarness, unstaged);
let dialogs = elements(tree, ui.MoveStageDialog);
check(dialogs.length === 1 && dialogs[0].props.expectedVersion === 0 && dialogs[0].props.currentStage === null && dialogs[0].props.contactId === 7, "Incluir no funil abre o dialogo com expected_version 0");
dialogs[0].props.onMoved({ contact_id: 7, replayed: false, activity_id: "stage_x", stage: { key: "in_service", label: "Em atendimento", kind: "open", version: 1, changed_at: at(NOW), source: "user", entered_at: at(NOW), reason: null, reason_note: null, appointment_kind: null } });
dialogs[0].props.onClose();
tree = renderCard(cardHarness, unstaged);
check(elements(tree, ui.MoveStageDialog).length === 0 && textOf(tree).includes("Em atendimento") && buttonNamed(tree, "Mover para…"), "resposta do POST vale ate o contato ao vivo alcancar a versao");
check(textOf(tree).includes("Etapa alterada para Em atendimento. Nenhuma mensagem foi enviada."), "aviso: nenhuma mensagem enviada");
const infoButtons = elements(tree, ui.InfoButton);
check(infoButtons.length === 1 && infoButtons[0].props.expanded === false && infoButtons[0].props.subject === "Em atendimento", "cartao: botao ⓘ do texto explicativo, fechado");
buttonNamed(tree, "Ver histórico").props.onClick();
tree = renderCard(cardHarness, unstaged);
await settle();
tree = renderCard(cardHarness, unstaged);
check(fetchCalls.length === 2 && fetchCalls[1].path === "/api/funnel/contacts/7/history" && elements(tree, ui.StageHistory)[0]?.props.items.length === 1, "historico: 1 GET so depois de expandir");
check(buttonNamed(tree, "Ocultar histórico")?.props["aria-expanded"] === true, "botao do historico expoe aria-expanded");
const liveAwaiting = () => asContact({ crm_stage: "awaiting_followup", crm_stage_version: 2, crm_stage_changed_at: at(NOW - 2 * DAY) });
tree = renderCard(cardHarness, liveAwaiting());
await settle();
tree = renderCard(cardHarness, liveAwaiting());
check(textOf(tree).includes("Aguardando retorno") && !textOf(tree).includes("Em atendimento"), "contato ao vivo com versao maior vence a copia local");
check(fetchCalls.length === 3 && fetchCalls[2].path.endsWith("/contacts/7/history"), "etapa mudou com o historico aberto: recarrega a 1a pagina");
check(textOf(tree).includes(stageDefs.awaiting_followup.description), "texto explicativo da etapa no cartao");
buttonNamed(tree, "Mover para…").props.onClick({ currentTarget: {} });
tree = renderCard(cardHarness, asContact({ crm_stage: "awaiting_followup", crm_stage_version: 2 }));
dialogs = elements(tree, ui.MoveStageDialog);
check(dialogs[0].props.expectedVersion === 2 && dialogs[0].props.currentStage === "awaiting_followup" && dialogs[0].props.catalog.stages.find((stage) => stage.key === "new").visible === false, "Mover para… parte da versao exibida, com o catalogo do usuario");
dialogs[0].props.onConflict({ stage: "scheduled", version: 9, changed_at: at(NOW), changed_by_user_id: 3, changed_by_name: "Ana" });
tree = renderCard(cardHarness, asContact({ crm_stage: "awaiting_followup", crm_stage_version: 2 }));
check(textOf(tree).includes("Cliente Agendado"), "409 stale_version: o cartao passa a mostrar a etapa atual do servidor");
// Etapa invisivel no QUADRO continua visivel no cartao (acesso do CRM).
const agentCard = renderCard(hookHarness(), asContact({ crm_stage: "new", crm_stage_version: 1 }));
check(textOf(agentCard).includes("Novo contato"), "cartao mostra Novo contato mesmo para quem nao o ve no quadro");

// Escopo de escrita (mesma regra do backend) e contato indisponivel.
const coex = renderCard(hookHarness(), asContact({ crm_stage: "scheduled", crm_stage_version: 4, assigned_to: 99, assigned_to_uid: "uid-99" }));
check(textOf(coex).includes("Cliente Agendado") && !buttonNamed(coex, "Mover para…") && !buttonNamed(coex, "Ver histórico"), "acesso so por thread propria: ve a etapa, nao move nem le historico");
check(textOf(coex).includes("Você pode consultar a etapa, mas só move contatos seus ou sem dono."), "explica por que nao move");
const mineCard = renderCard(hookHarness(), asContact({ crm_stage: "scheduled", crm_stage_version: 4, assigned_to: 5, assigned_to_uid: "uid-5" }));
check(buttonNamed(mineCard, "Mover para…") && buttonNamed(mineCard, "Ver histórico"), "dono do lead move e le historico");
const backup = renderCard(hookHarness(), asContact({ crm_stage: "scheduled", crm_stage_version: 4, assigned_to: 5, assigned_to_uid: "uid-5", is_backup: true }));
check(!buttonNamed(backup, "Mover para…") && !buttonNamed(backup, "Ver histórico") && textOf(backup).includes("Contato em backup: a etapa não muda por aqui."), "backup: sem mover (409 contact_unavailable evitado)");
globalThis.__simCrm = crm({ toggles: { mover_etapa_funil: false } });
ui.resetFunnelConfigCache();
responder = (path) => (path === "/api/funnel/config" ? { body: configBody(false, { can_move: false }) } : { status: 404, body: {} });
const viewer = hookHarness();
renderCard(viewer, asContact({ crm_stage: "in_service", crm_stage_version: 1 }));
await settle();
const viewOnly = renderCard(viewer, asContact({ crm_stage: "in_service", crm_stage_version: 1 }));
check(!buttonNamed(viewOnly, "Mover para…") && !textOf(viewOnly).includes("só move contatos seus") && textOf(viewOnly).includes("Em atendimento"), "perfil so com ver_funil: so consulta");
globalThis.__simCrm = crm({ user: { id: 1, firebase_uid: "uid-1", role: "admin" }, toggles: { ver_todos_leads: true, ver_contatos_agente_funil: true } });
ui.resetFunnelConfigCache();
responder = (path) => (path === "/api/funnel/config" ? { body: configBody(true) } : { status: 404, body: {} });
const manager = hookHarness();
renderCard(manager, asContact({ crm_stage: "new", crm_stage_version: 1, is_archived: 1, assigned_to: 99, assigned_to_uid: "uid-99" }));
await settle();
const archived = renderCard(manager, asContact({ crm_stage: "new", crm_stage_version: 1, is_archived: 1, assigned_to: 99, assigned_to_uid: "uid-99" }));
check(!buttonNamed(archived, "Mover para…") && buttonNamed(archived, "Ver histórico") && textOf(archived).includes("Contato arquivado"), "gestao: arquivado sem mover, com historico");

// Desfecho do "Encerrar atendimento" pelo funil (catalogo em cache).
globalThis.__simCrm = crm();
ui.resetFunnelConfigCache();
const lightStage = (extra = {}) => ({ key: "non_converted", label: "Não convertido", kind: "lost", version: 4, changed_at: at(NOW - DAY), source: "user", entered_at: at(NOW - 9 * DAY), reason: { key: "price", label: "Preço" }, reason_note: null, appointment_kind: null, ...extra });
let lightCheck = () => ({ body: { stage: lightStage(), version: 4, can_move: true, write_scope: true } });
let closeConfig = () => ({ body: configBody() });
responder = (path) => (path === "/api/funnel/config" ? closeConfig() : path === "/api/funnel/contacts/7/stage" ? lightCheck() : notFound);
let mark = fetchCalls.length;
const since = (start) => fetchCalls.slice(start).map((call) => `${call.method} ${call.path}`);
const inService = closeHarness(asContact({ crm_stage: "in_service", crm_stage_version: 3, qualification: "em_atendimento" }));
let closing = inService.render();
check(closing.form.mode === "loading" && textOf(closing.tree) === "Carregando os desfechos do funil…", "Encerrar: catalogo carregando");
await settle();
closing = inService.render();
same(since(mark), ["GET /api/funnel/config"], "Encerrar: 1 GET /config (sem GET leve: etapa atual sem motivo)");
check(closing.form.mode === "funnel" && textOf(closing.tree).includes("Etapa atual no funil: Em atendimento. O desfecho escolhido passa a ser a etapa do contato no funil comercial."), "Encerrar: o desfecho passa a ser a etapa");
same(radios(closing.tree, "outcome"), outcomeKeys, "Encerrar: desfechos = close_outcome do catalogo");
const outcomeLabels = elements(closing.tree, "label").filter((node) => elements(node, "input").some((input) => String(input.props.name).endsWith("-outcome")));
check(outcomeLabels.every((label, index) => textOf(label).includes(clinic.stages.find((stage) => stage.key === outcomeKeys[index]).description)), "Encerrar: texto explicativo sob cada desfecho");
check(closing.form.choice.target === "" && closing.form.problem === "Escolha o desfecho." && radio(closing.tree, "outcome", "awaiting_followup").props.autoFocus === true, "Encerrar: sem pre-selecao fora de desfecho; foco no primeiro");
check(closing.form.prepare("conv-1") === null, "Encerrar: sem desfecho nao envia");
closing = inService.render();
check(textOf(closing.tree).includes("Escolha o desfecho."), "Encerrar: o problema aparece no modal");
radio(closing.tree, "outcome", "scheduled").props.onChange();
closing = inService.render();
check(!textOf(closing.tree).includes("Escolha o desfecho.") && closing.form.legacyQualification === "convertido", "Encerrar: escolher limpa o erro; legado equivalente = convertido");
same(radios(closing.tree, "appointment"), ["", "consultation", "procedure"], "Cliente Agendado: tipo de compromisso opcional");
radio(closing.tree, "appointment", "consultation").props.onChange();
closing = inService.render();
const scheduledPayload = closing.form.prepare("conv-1");
same(Object.keys(scheduledPayload), ["to_stage", "expected_version", "reason", "reason_note", "appointment_kind", "operation_id"], "payload funnel do set-attendance: campos do contrato");
same({ ...scheduledPayload, operation_id: "x" }, { to_stage: "scheduled", expected_version: 3, reason: null, reason_note: null, appointment_kind: "consultation", operation_id: "x" }, "payload: Cliente Agendado com consulta a partir da versao do contato");
check(/^[A-Za-z0-9_-]{8,128}$/.test(scheduledPayload.operation_id) && closing.form.prepare("conv-1").operation_id === scheduledPayload.operation_id, "operation_id estavel para o mesmo payload");
check(closing.form.prepare("conv-2").operation_id !== scheduledPayload.operation_id, "outra conversa = outro operation_id");
radio(closing.tree, "outcome", "non_converted").props.onChange();
closing = inService.render();
same(radios(closing.tree, "reason"), templateReasons.filter((reason) => reason.selectable).map((reason) => reason.key), "Nao convertido: motivos escolhiveis (radios)");
check(radios(closing.tree, "appointment").length === 0 && closing.form.choice.appointment === "" && closing.form.problem === "Informe o motivo.", "trocar de desfecho limpa o compromisso; motivo obrigatorio");
radio(closing.tree, "reason", "price").props.onChange();
closing = inService.render();
check(noteHelp(closing.tree) === null && !elements(closing.tree, "input").some((node) => node.props.type === "text"), "motivo Preço: sem campo de nota");
radio(closing.tree, "reason", "other").props.onChange();
closing = inService.render();
const noteInput = elements(closing.tree, "input").find((node) => node.props.type === "text");
check(noteInput && noteInput.props.maxLength === 120 && textOf(noteHelp(closing.tree)).startsWith("Não registre dados clínicos."), "motivo Outro: nota com o aviso \"não registre dados clínicos\"");
noteInput.props.onChange({ target: { value: "  vai pensar  " } });
closing = inService.render();
check(textOf(noteHelp(closing.tree)).includes("(10/120)"), "contador da nota (com trim)");
same({ ...closing.form.prepare("conv-1"), operation_id: "x" }, { to_stage: "non_converted", expected_version: 3, reason: "other", reason_note: "vai pensar", appointment_kind: null, operation_id: "x" }, "payload: Nao convertido / Outro com nota");
check(closing.form.legacyQualification === "nao_convertido", "legado equivalente = nao_convertido");
radio(closing.tree, "reason", "no_show").props.onChange();
closing = inService.render();
check(closing.form.choice.note === "" && noteHelp(closing.tree) === null && closing.form.prepare("conv-1").reason_note === null, "trocar de Outro para outro motivo descarta a nota");
const beforeReuse = closing.form.prepare("conv-1").operation_id;
check(closing.form.handleError(ui.apiErrorFromPayload({ detail: { code: "operation_reused", message: "x" } }, 409)) === true, "operation_reused tratado no modal");
closing = inService.render();
check(closing.form.prepare("conv-1").operation_id !== beforeReuse, "operation_reused: proxima tentativa com id novo");
check(closing.form.handleError(ui.apiErrorFromPayload({ detail: { code: "permission_denied", message: "x" } }, 403)) === true, "permission_denied tratado no modal");
closing = inService.render();
check(textOf(closing.tree).includes(ui.FUNNEL_CLOSE_ERROR_MESSAGES.permission_denied), "permission_denied: texto do encerramento no modal");
radio(closing.tree, "reason", "price").props.onChange();
closing = inService.render();
check(!textOf(closing.tree).includes(ui.FUNNEL_CLOSE_ERROR_MESSAGES.permission_denied), "nova escolha limpa o erro");
check(closing.form.handleError(new Error("rede")) === false && closing.form.handleError(ui.apiErrorFromPayload({ detail: "texto" }, 500)) === false, "erro sem code do funil fica com o alerta global");

// Etapa atual ja e desfecho: pre-seleciona e mantem (so sincroniza o legado).
mark = fetchCalls.length;
const keepScheduled = closeHarness(asContact({ crm_stage: "scheduled", crm_stage_version: 5, qualification: "em_atendimento" }));
closing = keepScheduled.render();
await settle();
closing = keepScheduled.render();
same(since(mark), [], "manter etapa sem motivo: nenhum GET extra");
check(closing.form.choice.target === "scheduled" && radio(closing.tree, "outcome", "scheduled").props.checked === true && textOf(closing.tree).includes("Cliente Agendado (etapa atual)"), "pre-seleciona a etapa atual (desfecho)");
check(textOf(closing.tree).includes("O contato continua em Cliente Agendado; o encerramento só registra o desfecho.") && radios(closing.tree, "appointment").length === 0, "manter: aviso e sem tipo de compromisso");
same({ ...closing.form.prepare("conv-9"), operation_id: "x" }, { to_stage: "scheduled", expected_version: 5, reason: null, reason_note: null, appointment_kind: null, operation_id: "x" }, "payload: manter a etapa sem motivo -> reason null");
// 409 stale_version: quem mudou fica visivel e a escolha vista fica fixa.
const staleError = ui.apiErrorFromPayload({ detail: { code: "stale_version", message: "x", current: { stage: "loyal", version: 9, changed_at: "2026-10-26T12:00:00+00:00", changed_by_user_id: 3, changed_by_name: "Ana" } } }, 409);
check(closing.form.handleError(staleError) === true, "409 stale_version tratado no modal");
closing = keepScheduled.render();
check(textOf(closing.tree).includes("Outra pessoa mudou a etapa deste contato.") && textOf(closing.tree).includes("Agora está em Paciente em acompanhamento") && textOf(closing.tree).includes(", por Ana."), "409: mostra a etapa atual e quem mudou");
check(closing.form.choice.target === "scheduled" && closing.form.base.stage === "loyal" && closing.form.base.version === 9, "409: escolha vista congelada; base = servidor");
check(textOf(closing.tree).includes("Paciente em acompanhamento (etapa atual)") && radio(closing.tree, "outcome", "scheduled").props.checked === true, "409: etapa atual nova marcada, escolha mantida");
const reapply = buttonNamed(closing.tree, "Reaplicar minha escolha");
check(reapply !== null, "409: botao Reaplicar minha escolha");
reapply.props.onClick();
check(keepScheduled.reapplied.join() === "scheduled", "Reaplicar envia a escolha congelada");
same({ ...closing.form.prepare("conv-9"), operation_id: "x" }, { to_stage: "scheduled", expected_version: 9, reason: null, reason_note: null, appointment_kind: null, operation_id: "x" }, "Reaplicar: payload a partir da versao do servidor");
closing = keepScheduled.render();
check(!textOf(closing.tree).includes("Outra pessoa mudou a etapa"), "envio novo limpa o aviso de conflito");

// Manter Nao convertido: o motivo registrado vem do GET leve da etapa.
mark = fetchCalls.length;
const keepLost = closeHarness(asContact({ crm_stage: "non_converted", crm_stage_version: 4, qualification: "nao_convertido" }));
keepLost.render();
await settle();
closing = keepLost.render();
same(since(mark), ["GET /api/funnel/contacts/7/stage"], "manter etapa com motivo: 1 GET leve da etapa");
check(closing.form.choice.reason === "price" && textOf(closing.tree).includes("Motivo registrado: Preço. Escolher outro corrige o motivo.") && textOf(closing.tree).includes("Preço (atual)"), "motivo atual pre-selecionado");
same({ ...closing.form.prepare("conv-4"), operation_id: "x" }, { to_stage: "non_converted", expected_version: 4, reason: "price", reason_note: null, appointment_kind: null, operation_id: "x" }, "manter Nao convertido: envia o motivo atual (evita 422 reason_required)");
radio(closing.tree, "reason", "other").props.onChange();
closing = keepLost.render();
check(noteHelp(closing.tree) !== null && closing.form.prepare("conv-4").reason === "other", "corrigir para Outro: nota liberada");
lightCheck = () => ({ body: { stage: lightStage({ version: 5 }), version: 5, can_move: true, write_scope: true } });
const keepLostStale = closeHarness(asContact({ crm_stage: "non_converted", crm_stage_version: 4, qualification: "nao_convertido" }));
keepLostStale.render();
await settle();
closing = keepLostStale.render();
check(closing.form.choice.reason === "" && textOf(closing.tree).includes("Confirme o motivo. Se for outro, o motivo registrado é corrigido.") && closing.form.prepare("conv-4") === null, "GET leve de outra versao nao pre-seleciona (o 409 explica)");
closing = keepLostStale.render();
check(textOf(closing.tree).includes("Informe o motivo."), "sem motivo: o modal pede");
lightCheck = () => ({ status: 503, body: { detail: "x" } });
const keepLostDown = closeHarness(asContact({ crm_stage: "non_converted", crm_stage_version: 4, qualification: "nao_convertido" }));
keepLostDown.render();
await settle();
check(keepLostDown.render().form.choice.reason === "" && keepLostDown.render().form.mode === "funnel", "GET leve falhou: a pessoa escolhe o motivo");

// Backup/arquivado seguem o legado; menu Fechar = closeOpensModal.
mark = fetchCalls.length;
check(closeHarness(asContact({ crm_stage: "non_converted", crm_stage_version: 4, is_backup: true })).render().form.mode === "legacy" && closeHarness(asContact({ crm_stage: "in_service", crm_stage_version: 4 }), { is_backup: true }).render().form.mode === "legacy", "contato ou thread em backup: modal legado");
check(closeHarness(asContact({ crm_stage: "non_converted", crm_stage_version: 4, is_archived: 1 })).render().tree === null, "arquivado: sem campos do funil");
await settle();
same(since(mark), [], "legado: nenhum GET leve");

// 409 funnel_disabled: o /config e relido e, sem catalogo, o modal volta ao
// desfecho legado com o aviso.
const disabling = closeHarness(asContact({ crm_stage: "in_service", crm_stage_version: 3, qualification: "em_atendimento" }));
closing = disabling.render();
await settle();
closing = disabling.render();
check(closing.form.mode === "funnel", "antes: modal pelo funil");
closeConfig = () => ({ status: 409, body: { detail: { code: "funnel_disabled", message: "x" } } });
mark = fetchCalls.length;
check(closing.form.handleError(ui.apiErrorFromPayload({ detail: { code: "funnel_disabled", message: "x" } }, 409)) === true, "funnel_disabled tratado no modal");
disabling.render();
await settle();
closing = disabling.render();
same(since(mark), ["GET /api/funnel/config"], "funnel_disabled: /config relido (cache invalidado)");
check(closing.form.mode === "legacy" && closing.tree === null && closing.form.error === ui.FUNNEL_CLOSE_ERROR_MESSAGES.funnel_disabled, "sem catalogo: modal legado com o aviso do funil");
check(fetchCalls.every((call) => call.method === "GET"), "desfecho do encerramento nao grava nada sozinho (o envio e do setAttendance)");

// Botao da TopBar: abre o painel (portal) sem requisitar nada por conta propria.
ui.resetFunnelConfigCache();
responder = (path) => (path === "/api/funnel/config" ? { body: configBody() } : notFound);
globalThis.__simCrm = crm();
const callsBefore = fetchCalls.length;
const entry = hookHarness();
let topbar = entry.render(() => ui.FunnelEntry());
const trigger = elements(topbar, "button")[0];
check(trigger?.props["aria-label"] === "Abrir funil comercial" && trigger.props["aria-haspopup"] === "dialog" && elements(topbar, "Portal").length === 0, "botao Funil fechado");
trigger.props.onClick();
topbar = entry.render(() => ui.FunnelEntry());
check(elements(topbar, "Portal").length === 1 && elements(topbar, "Suspense").length === 1, "abrir = portal com o painel preguicoso (Suspense)");
await settle();
check(fetchCalls.length === callsBefore, "o botao em si nao faz requisicao (o painel lazy e quem carrega)");
check(fetchCalls.every((call) => call.method === "GET" && call.path.startsWith("/api/funnel/")), "componentes so leram /api/funnel (nenhum POST, nenhum /conversation/open)");

// ---------------------------------------------------------------------------
// 13. Drawer: revalidacao de 30 s pelo GET leve /contacts/{id}/stage; o GET
//     completo so volta quando a versao, a etapa exibida ou o escopo mudam
// ---------------------------------------------------------------------------
const views = await load(`
export { ContactDrawer, stageCheckChanged, applyStageCheck } from "./src/features/funnel/ContactDrawer.tsx";
export { FunnelDashboard, cohortBase, cohortRows, reasonRows } from "./src/features/funnel/FunnelDashboard.tsx";
export { FunnelColumn } from "./src/features/funnel/FunnelColumn.tsx";
export { FunnelBoard } from "./src/features/funnel/FunnelBoard.tsx";
export { FunnelSettingsPanel } from "./src/features/funnel/FunnelSettingsPanel.tsx";
export { panelTabs, nextPanelTab } from "./src/features/funnel/FunnelPanel.tsx";
export { InfoButton } from "./src/features/funnel/InfoButton.tsx";
export { MoveStageDialog, StageHistory } from "./src/features/funnel/index.ts";
`, { react: true, crm: true });
const { stageCheckChanged, applyStageCheck } = views;
const drawerStage = (extra = {}) => ({ key: "in_service", label: "Em atendimento", kind: "open", version: 4, changed_at: at(NOW - 2 * DAY), source: "rule:handoff", entered_at: at(NOW - 9 * DAY), reason: null, reason_note: null, appointment_kind: null, ...extra });
const drawerBody = (extra = {}) => ({
  contact: { id: 7, display_name: "Paciente Sim", lead_temperature: null, lead_temperature_at: null, owner: null, bot_completed: false, is_archived: false },
  stage: drawerStage(), badges: { with_bot: false, lgpd_pending: false, commercial_blocked: false, bot_outcome: null }, signals: quiet,
  history: historyBody, tasks: null, suggestions: [], capabilities: { can_move: true, write_scope: true }, ...extra,
});
const stageCheck = (extra = {}) => ({ stage: drawerStage(), version: 4, can_move: true, write_scope: true, ...extra });

check(!stageCheckChanged(drawerBody(), stageCheck()), "leve: mesma versao, etapa e escopo = sem GET completo");
check(stageCheckChanged(drawerBody(), stageCheck({ version: 5, stage: drawerStage({ version: 5 }) })), "leve: versao nova = GET completo");
check(stageCheckChanged(drawerBody(), stageCheck({ stage: drawerStage({ key: "scheduled", label: "Cliente Agendado" }) })), "leve: etapa diferente com a mesma versao = GET completo");
check(stageCheckChanged(drawerBody(), stageCheck({ stage: drawerStage({ reason_note: "nota" }) })), "leve: conteudo exibido da etapa mudou = GET completo");
check(stageCheckChanged(drawerBody(), stageCheck({ write_scope: false, can_move: false })), "leve: escopo de escrita mudou = GET completo (historico e nota dependem dele)");
check(!stageCheckChanged(drawerBody(), stageCheck({ can_move: false })), "leve: so o mover mudou = sem GET completo");
check(!stageCheckChanged(drawerBody(), { stage: drawerStage() }), "leve: sem version/escopo usa a versao da etapa (tolerancia)");
check(stageCheckChanged(drawerBody(), {}) && stageCheckChanged(drawerBody(), null) && stageCheckChanged(null, stageCheck()), "leve: resposta sem stage = GET completo (nunca 'nada mudou' por falta de dado)");
check(!stageCheckChanged(drawerBody({ stage: null }), { stage: null, version: 0, can_move: true, write_scope: true }), "leve: fora do funil nos dois = sem GET completo");
check(stageCheckChanged(drawerBody({ stage: null }), stageCheck()), "leve: contato entrou no funil = GET completo");
const unchanged = drawerBody();
check(applyStageCheck(unchanged, stageCheck()) === unchanged && applyStageCheck(unchanged, { stage: drawerStage() }) === unchanged, "nada a aplicar = mesmo objeto");
const applied = applyStageCheck(unchanged, stageCheck({ can_move: false }));
check(applied.capabilities.can_move === false && applied.capabilities.write_scope === true && applied.history === unchanged.history && applied.stage === unchanged.stage, "mover aplicado no lugar; historico e etapa intactos");

// Componente real no harness: relogio falso (setInterval), aba visivel/oculta
// e fetch espionado com respostas trocaveis.
const timers = [];
globalThis.window = {
  setInterval(fn, ms) { timers.push({ fn, ms, active: true }); return timers.length; },
  clearInterval(handle) { if (timers[handle - 1]) timers[handle - 1].active = false; },
  setTimeout() { return 0; }, clearTimeout() {},
};
globalThis.HTMLElement = class {};
globalThis.document = { body: {}, visibilityState: "visible", activeElement: null, addEventListener() {}, removeEventListener() {} };
const settleMore = async () => { await settle(); await settle(); };
const tick = async () => { timers.filter((timer) => timer.active && timer.ms === 30000).forEach((timer) => timer.fn()); await settleMore(); };
const drawerCatalog = configBody().catalog;
let fullReply = () => ({ body: drawerBody() });
let lightReply = () => ({ body: stageCheck() });
responder = (path) => {
  if (path === "/api/funnel/contacts/7") return fullReply();
  if (path === "/api/funnel/contacts/7/stage") return lightReply();
  if (path === "/api/funnel/contacts/7/context") return { body: { contact: { id: 7 }, conversations: [] } };
  return notFound;
};
function drawerCrm(contacts = new Map()) {
  return { ...crm(), channels: [], canPeek: false, peekMode: false, contactsById: contacts, conversations: [], selectedConversation: null, perfil: null };
}
async function openDrawer() {
  const events = { lost: [], seen: [], moved: [] };
  const props = {
    auth: simAuth, contactId: 7, catalog: drawerCatalog, returnFocus: () => null, onClose() {},
    onMoved: (contactId, result) => events.moved.push(result.stage.version), onConflict() {},
    onStageSeen: (contactId, stage) => events.seen.push(stage ? stage.version : null), onAccessLost: (contactId) => events.lost.push(contactId), onOpenConversation() {},
  };
  const harness = hookHarness();
  const render = () => harness.render(() => views.ContactDrawer(props));
  render();
  await settleMore();
  return { events, render, tree: render(), unmount: () => harness.unmount() };
}

globalThis.__simCrm = drawerCrm();
fullReply = () => ({ body: drawerBody() });
lightReply = () => ({ body: stageCheck() });
mark = fetchCalls.length;
let drawerView = await openDrawer();
same(since(mark), ["GET /api/funnel/contacts/7", "GET /api/funnel/contacts/7/context"], "drawer abre com 1 GET completo (+ conversas)");
check(textOf(drawerView.tree).includes("Em atendimento") && buttonNamed(drawerView.tree, "Mover para…") && drawerView.events.seen.join() === "4", "drawer mostra a etapa e avisa o quadro da versao vista");
check(timers.some((timer) => timer.active && timer.ms === 30000), "revalidacao agendada a cada 30 s");
mark = fetchCalls.length;
await tick();
same(since(mark), ["GET /api/funnel/contacts/7/stage"], "ciclo de 30 s sem mudanca = so o GET leve (sem historico/tarefas)");
tree = drawerView.render();
check(!textOf(tree).includes("A etapa deste contato foi alterada") && buttonNamed(tree, "Mover para…"), "sem mudanca: conteudo e aviso intactos");

lightReply = () => ({ body: stageCheck({ can_move: false }) });
mark = fetchCalls.length;
await tick();
tree = drawerView.render();
same(since(mark), ["GET /api/funnel/contacts/7/stage"], "so o mover mudou: sem GET completo");
check(!buttonNamed(tree, "Mover para…") && textOf(tree).includes("Em atendimento"), "mover some no lugar (toggle/arquivo)");
lightReply = () => ({ body: stageCheck() });
await tick();
check(buttonNamed(drawerView.render(), "Mover para…"), "mover volta quando o leve devolve can_move");

document.visibilityState = "hidden";
mark = fetchCalls.length;
await tick();
same(since(mark), [], "aba oculta: nenhuma revalidacao");
document.visibilityState = "visible";

const movedElsewhere = drawerStage({ key: "scheduled", label: "Cliente Agendado", kind: "won", version: 5, changed_at: at(NOW - 3_600_000), source: "user" });
lightReply = () => ({ body: stageCheck({ stage: movedElsewhere, version: 5 }) });
fullReply = () => ({ body: drawerBody({ stage: movedElsewhere, history: { items: [{ ...historyBody.items[0], id: "stage_2", to_stage: "scheduled", to_label: "Cliente Agendado" }, historyBody.items[0]], next_cursor: null } }) });
mark = fetchCalls.length;
await tick();
tree = drawerView.render();
same(since(mark), ["GET /api/funnel/contacts/7/stage", "GET /api/funnel/contacts/7"], "versao mudou em outra tela: leve + 1 GET completo");
check(textOf(tree).includes("Cliente Agendado") && textOf(tree).includes("A etapa deste contato foi alterada. Os dados foram atualizados."), "drawer recarregado avisa a mudanca");
check(elements(tree, views.StageHistory)[0]?.props.items.length === 2 && drawerView.events.seen.join() === "4,5", "historico recomeca e o quadro recebe a versao nova");
mark = fetchCalls.length;
await tick();
same(since(mark), ["GET /api/funnel/contacts/7/stage"], "depois da recarga, ciclo seguinte volta a ser so o leve");

// Mudanca feita aqui: a versao ja mudou, entao vai direto ao GET completo.
buttonNamed(drawerView.render(), "Mover para…").props.onClick({ currentTarget: {} });
tree = drawerView.render();
const drawerDialog = elements(tree, views.MoveStageDialog)[0];
check(drawerDialog?.props.expectedVersion === 5 && drawerDialog.props.currentStage === "scheduled", "Mover para… do drawer parte da versao exibida");
const ownStage = drawerStage({ key: "awaiting_followup", label: "Aguardando retorno", version: 6, source: "user" });
fullReply = () => ({ body: drawerBody({ stage: ownStage }) });
lightReply = () => ({ body: stageCheck({ stage: ownStage, version: 6 }) });
mark = fetchCalls.length;
drawerDialog.props.onMoved({ contact_id: 7, replayed: false, activity_id: "stage_6", stage: ownStage });
drawerDialog.props.onClose();
drawerView.render();
await settleMore();
tree = drawerView.render();
same(since(mark), ["GET /api/funnel/contacts/7"], "mudanca propria: 1 GET completo direto, sem o leve");
check(textOf(tree).includes("Etapa alterada para Aguardando retorno. Nenhuma mensagem foi enviada.") && !textOf(tree).includes("A etapa deste contato foi alterada") && drawerView.events.moved.join() === "6", "mudanca propria nao vira aviso de mudanca alheia");

// Escopo de escrita perdido (so thread propria, coex): recarga completa e o
// historico some, como no backend.
lightReply = () => ({ body: stageCheck({ stage: ownStage, version: 6, write_scope: false, can_move: false }) });
fullReply = () => ({ body: drawerBody({ stage: ownStage, history: { items: [], next_cursor: null }, capabilities: { can_move: false, write_scope: false } }) });
mark = fetchCalls.length;
await tick();
tree = drawerView.render();
same(since(mark), ["GET /api/funnel/contacts/7/stage", "GET /api/funnel/contacts/7"], "escopo de escrita mudou: leve + GET completo");
const coexHistory = elements(tree, views.StageHistory)[0];
check(coexHistory?.props.items.length === 0 && coexHistory.props.emptyText === "O histórico da etapa fica com o dono do lead e com a gestão." && !buttonNamed(tree, "Mover para…"), "sem escopo de escrita: historico some e nao move");

// Falha transitoria mantem os dados; 401/403/404 fecham com aviso (o painel
// mostra o aviso ao receber onAccessLost).
lightReply = () => ({ status: 503, body: { detail: "indisponivel" } });
await tick();
check(drawerView.events.lost.length === 0 && textOf(drawerView.render()).includes("Aguardando retorno"), "leve com 5xx: mantem os dados e tenta no proximo ciclo");
drawerView.unmount();
check(!timers.some((timer) => timer.active), "drawer fechado: revalidacao cancelada");
for (const status of [401, 403, 404]) {
  globalThis.__simCrm = drawerCrm();
  fullReply = () => ({ body: drawerBody() });
  lightReply = () => ({ body: stageCheck() });
  const opened = await openDrawer();
  lightReply = () => ({ status, body: { detail: { code: status === 404 ? "out_of_scope" : "user_inactive", message: "x" } } });
  mark = fetchCalls.length;
  await tick();
  same(since(mark), ["GET /api/funnel/contacts/7/stage"], `leve com ${status}: nenhum GET completo`);
  check(opened.events.lost.join() === "7" && !buttonNamed(opened.render(), "Mover para…"), `leve com ${status}: drawer fecha (acesso perdido)`);
  opened.unmount();
}
// Dono mudou no CRM ao vivo: evento raro e o dono aparece no cabecalho (o
// leve nao o traz) -> GET completo na hora, sem esperar 30 s; 404 fecha.
globalThis.__simCrm = drawerCrm();
fullReply = () => ({ body: drawerBody() });
lightReply = () => ({ body: stageCheck() });
drawerView = await openDrawer();
check(textOf(drawerView.tree).includes("Dono do lead: sem dono"), "drawer mostra o dono do lead");
globalThis.__simCrm = drawerCrm(new Map([[7, { id: 7, assigned_to: 9, assigned_to_uid: "uid-9", is_archived: 0 }]]));
fullReply = () => ({ body: drawerBody({ contact: { ...drawerBody().contact, owner: { user_id: 9, name: "Bia" } } }) });
mark = fetchCalls.length;
drawerView.render();
await settleMore();
tree = drawerView.render();
same(since(mark), ["GET /api/funnel/contacts/7"], "dono mudou no CRM: 1 GET completo na hora");
check(textOf(tree).includes("Dono do lead: Bia") && !textOf(tree).includes("A etapa deste contato foi alterada"), "drawer mostra o dono novo, sem aviso de mudanca de etapa");
mark = fetchCalls.length;
await tick();
same(since(mark), ["GET /api/funnel/contacts/7/stage"], "depois do evento, o ciclo volta ao leve");
globalThis.__simCrm = drawerCrm(new Map([[7, { id: 7, assigned_to: 11, assigned_to_uid: "uid-11", is_archived: 0 }]]));
fullReply = () => notFound;
drawerView.render();
await settleMore();
check(drawerView.events.lost.join() === "7", "lead foi para outra pessoa: drawer fecha");
drawerView.unmount();

// ---------------------------------------------------------------------------
// 14. Painel gerencial: coorte liquida (Nao qualificado fora das taxas),
//     motivos dos movimentos x classificacao de antigos, payload antigo
// ---------------------------------------------------------------------------
const { cohortBase, cohortRows, reasonRows } = views;
const levels = (newCount, scheduledCount) => [{ stage: "new", label: "Novo contato", reached: newCount, reached_gross: newCount + 20 }, { stage: "scheduled", label: "Cliente Agendado", reached: scheduledCount, reached_gross: scheduledCount + 1 }];
const netCohort = { entered: 100, excluded: 30, entered_net: 70, lgpd_accepted: 80, levels: levels(63, 14), closed_without_booking: 7 };
const oldCohort = { entered: 40, lgpd_accepted: 20, levels: [{ stage: "new", label: "Novo contato", reached: 30 }, { stage: "scheduled", label: "Cliente Agendado", reached: 10 }], closed_without_booking: 4 };
same(cohortBase(netCohort), { entered: 100, excluded: 30, net: 70 }, "base das taxas = entered_net");
same(cohortBase(oldCohort), { entered: 40, excluded: null, net: 40 }, "payload antigo: base = entered e sem excluidos");
same([cohortBase({ ...oldCohort, excluded: 5 }).net, cohortBase({ ...oldCohort, excluded: 90 }).net, cohortBase(null).net], [35, 0, 0], "sem entered_net: entered - excluded, nunca negativo");
const rowsByKey = (cohort, label) => Object.fromEntries(cohortRows(cohort, label).map((row) => [row.key, row]));
const netRows = rowsByKey(netCohort, "Não qualificado");
same(cohortRows(netCohort).map((row) => row.key), ["entered", "excluded", "lgpd", "level-new", "level-scheduled", "closed"], "coorte com a linha da etapa de exclusao");
check(cohortRows(netCohort).find((row) => row.key === "excluded").label === "Descartados" && netRows.excluded.label === "Não qualificado", "rotulo da exclusao vem do catalogo (fallback Descartados)");
check(netRows.excluded.value === 30 && netRows.excluded.base === null && netRows.entered.base === null, "Entraram e excluidos sem taxa");
check(netRows["level-scheduled"].value === 14 && netRows["level-scheduled"].base === 70 && netRows.closed.value === 7 && netRows.closed.base === 70, "degraus (reached liquido) e encerrados sobre a base sem excluidos");
check(netRows.lgpd.value === 80 && netRows.lgpd.base === 100, "aceite LGPD (coorte inteira) sobre todos que entraram: nunca passa de 100%");
same(cohortRows(oldCohort).map((row) => row.key), ["entered", "lgpd", "level-new", "level-scheduled", "closed"], "payload antigo: sem linha de excluidos");
same(reasonRows([{ reason: "price", label: "Preço", count: 2 }, { reason: "distance", label: "Distância", count: 2 }], [{ reason: "price", label: "Preço", count: 5 }, { reason: "other", label: "Outro", count: 1 }]).map((row) => [row.key, row.month, row.previous]),
  [["price", 2, 5], ["distance", 2, 0], ["other", 0, 1]], "motivos: mes e anterior unidos, ordem por mes/anterior/rotulo");
same(reasonRows(undefined, null), [], "motivos ausentes = nenhuma linha");

// Render real (FunnelDashboard + componentes internos sem hook expandidos).
function expand(node) {
  if (node == null || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map(expand);
  if (typeof node.type === "function") {
    // Componente interno do painel nao usa hook: chamar hook aqui quebraria.
    const hooks = globalThis.__simHooks;
    globalThis.__simHooks = null;
    try { return expand(node.type(node.props)); } finally { globalThis.__simHooks = hooks; }
  }
  return { ...node, props: { ...node.props, children: expand(node.props?.children) } };
}
const dashboardBody = (reasons, month, previous) => ({
  month: "2026-10", previous_month: "2026-09", generated_at: at(NOW), cached: false,
  current: { stages: [], with_stage: 0, unknown_stage: 0 }, cohort: { month, previous },
  movements: [], triage: { month: 3, previous: 0 }, reactivations: { month: 0, previous: 0 }, reasons, notes: [],
});
async function renderDashboard(payload) {
  responder = (path) => (path.startsWith("/api/funnel/dashboard?") ? { body: payload } : { status: 404, body: {} });
  const harness = hookHarness();
  const props = { auth: simAuth, catalog: drawerCatalog, onAccessLost() {} };
  harness.render(() => views.FunnelDashboard(props));
  await settleMore();
  return expand(harness.render(() => views.FunnelDashboard(props)));
}
const rowText = (dashboardView, label) => textOf(elements(dashboardView, "tr").find((row) => textOf(row).startsWith(label)) || "");
const sectionNamed = (dashboardView, title) => elements(dashboardView, "section").find((node) => textOf(elements(node, "h3")[0]).trim() === title) || null;
let dashboard = await renderDashboard(dashboardBody({
  month: [], previous: [], truncated: false,
  month_triage: [{ reason: "price", label: "Preço", count: 3 }], previous_triage: [],
}, netCohort, { ...netCohort, entered: 50, excluded: 10, entered_net: 40, lgpd_accepted: 30, levels: levels(30, 8), closed_without_booking: 2 }));
const moveReasons = sectionNamed(dashboard, "Não convertidos por motivo");
const triageSection = sectionNamed(dashboard, "Motivos — classificação de contatos antigos");
// 1o <p> da secao = subtitulo (o estado vazio vem depois, na tabela).
const moveSubtitle = textOf(elements(moveReasons, "p")[0]);
check(moveSubtitle.includes("nos movimentos do mês") && moveSubtitle.includes("a classificação de antigos aparece à parte"), "motivos dos movimentos: subtitulo diz movimentos do mes e antigos a parte");
check(textOf(moveReasons).includes("Nenhum não convertido nos movimentos do mês e do anterior; a classificação de antigos aparece à parte."), "motivos dos movimentos vazios: estado vazio corrigido");
check(triageSection && rowText(triageSection, "Preço").includes("3") && !textOf(moveReasons).includes("Preço"), "tabela separada com os motivos da classificacao de antigos");
check(textOf(sectionNamed(dashboard, "Movimentos do mês")).includes("no encerramento do atendimento"), "movimentos do mes incluem os do encerramento do atendimento");
check(rowText(dashboard, "Não qualificado").includes("30") && rowText(dashboard, "Não qualificado").includes("Fora das taxas de conversão") && !rowText(dashboard, "Não qualificado").includes("%"), "coorte mostra Nao qualificado (rotulo do catalogo), sem taxa");
check(rowText(dashboard, "Alcançaram Cliente Agendado").includes("14 20%") && rowText(dashboard, "Alcançaram Cliente Agendado").includes("8 20%"), "taxa do degrau sobre entered_net (14/70 e 8/40), nao sobre entered");
check(rowText(dashboard, "Encerraram sem agendar").includes("7 10%") && rowText(dashboard, "Aceitaram o aviso LGPD").includes("80 80%"), "encerrados sobre a base liquida; LGPD sobre todos que entraram");
const cohortSection = sectionNamed(dashboard, "Coorte do mês");
check(textOf(cohortSection).includes("Contatos antigos e backups graduados contam no mês do primeiro contato; meses fechados podem crescer."), "nota: antigos e backups graduados no mes do primeiro contato");
check(textOf(cohortSection).includes("Taxas sobre quem entrou, sem os contatos em Não qualificado (70 em outubro de 2026; 40 em setembro de 2026)"), "base das taxas explicita por mes");
check(textOf(dashboard).includes("Reativação = saiu de Não convertido ou Não qualificado para uma etapa aberta ou ganha."), "reativacao explicada com os rotulos do catalogo");
const summaryTiles = textOf(elements(dashboard, "div").find((node) => node.props.role === "group" && String(node.props["aria-label"] || "").startsWith("Resumo de")));
check(summaryTiles.includes("Alcançaram Cliente Agendado") && summaryTiles.split("Alcançaram ").length === 2, "KPI: um quadro so (agendamento = conversao na clinica)");

dashboard = await renderDashboard(dashboardBody({ month: [{ reason: "price", label: "Preço", count: 2 }], previous: [], truncated: true }, oldCohort, oldCohort));
check(sectionNamed(dashboard, "Motivos — classificação de contatos antigos") === null, "payload antigo sem *_triage: sem tabela de antigos (nada de 'nenhum' falso)");
check(!rowText(dashboard, "Não qualificado") && rowText(dashboard, "Alcançaram Cliente Agendado").includes("10 25%"), "payload antigo: sem linha de excluidos e taxa sobre entered");
check(textOf(sectionNamed(dashboard, "Coorte do mês")).includes("Taxas sobre quem entrou (40 em outubro de 2026") && !textOf(dashboard).includes("sem os contatos em"), "payload antigo: legenda nao promete excluir");
check(rowText(sectionNamed(dashboard, "Não convertidos por motivo"), "Preço").includes("2") && textOf(dashboard).includes("A consulta de motivos atingiu o limite de registros"), "motivos dos movimentos e aviso de truncamento");

// ---------------------------------------------------------------------------
// 15. Coluna e quadro: aviso de contatos fora do acesso, texto explicativo,
//     so as colunas devolvidas; abas do painel
// ---------------------------------------------------------------------------
const columnProps = (entry, extra = {}) => ({ column: entry, current: true, canMove: false, onOpen() {}, onMove() {}, onMore() {}, ...extra });
const renderColumn = (props, harness = hookHarness()) => harness.render(() => views.FunnelColumn(props));
const HIDDEN_TEXT = "Alguns contatos desta etapa estão fora do seu acesso.";
check(textOf(renderColumn(columnProps(col(partial, "new")))).includes(HIDDEN_TEXT), "coluna sem cursor e com menos cards que o total mostra o aviso");
const scheduledColumn = renderColumn(columnProps(col(partial, "scheduled")));
check(!textOf(scheduledColumn).includes(HIDDEN_TEXT) && buttonNamed(scheduledColumn, "Carregar mais (3 restantes)"), "coluna com cursor: Carregar mais, sem aviso");
const expiredColumn = renderColumn(columnProps(col(expiredPage, "scheduled")));
check(!textOf(expiredColumn).includes(HIDDEN_TEXT) && textOf(expiredColumn).includes("A lista expirou."), "cursor vencido: so o erro, sem aviso de acesso");
check(!textOf(renderColumn(columnProps(col(partial, "non_converted")))).includes(HIDDEN_TEXT), "coluna completa: sem aviso");
const columnHarness = hookHarness();
let columnTree = renderColumn(columnProps(col(partial, "scheduled"), { label: "Agendou consulta", description: stageDefs.scheduled.description }), columnHarness);
const columnInfo = elements(columnTree, views.InfoButton)[0];
const infoText = () => elements(columnTree, "p").find((node) => node.props.className === "fn-column-info");
check(textOf(elements(columnTree, "h3")[0]) === "Agendou consulta" && columnInfo?.props.expanded === false && infoText()?.props.hidden === true && textOf(infoText()) === stageDefs.scheduled.description, "cabecalho com o rotulo do catalogo e o ⓘ (texto oculto)");
columnInfo.props.onToggle();
columnTree = renderColumn(columnProps(col(partial, "scheduled"), { label: "Agendou consulta", description: stageDefs.scheduled.description }), columnHarness);
check(elements(columnTree, views.InfoButton)[0].props.expanded === true && infoText().props.hidden === false && elements(columnTree, views.InfoButton)[0].props.controls === infoText().props.id, "ⓘ abre o texto explicativo (aria-controls)");
check(elements(renderColumn(columnProps(col(partial, "scheduled"))), views.InfoButton).length === 0, "sem texto explicativo: sem ⓘ");

const boardHarness = hookHarness();
const boardStages = new Map(clinicOperator.stages.map((stage) => [stage.key, stage.key === "scheduled" ? { ...stage, label: "Agendou consulta" } : stage]));
const boardTree = boardHarness.render(() => views.FunnelBoard({ columns: operatorBoard.columns, stages: boardStages, canMove: true, busy: false, onOpen() {}, onMove() {}, onMore() {} }));
const boardColumns = elements(boardTree, views.FunnelColumn);
same(boardColumns.map((node) => node.props.column.stage), operatorBoard.columns.map((entry) => entry.stage), "quadro: so as colunas devolvidas (sem Novo contato)");
check(elements(boardTree, "nav")[0] && elements(elements(boardTree, "nav")[0], "button").length === operatorBoard.columns.length, "navegador de etapas com as mesmas colunas");
check(boardColumns.find((node) => node.props.column.stage === "scheduled").props.label === "Agendou consulta" && boardColumns.find((node) => node.props.column.stage === "in_service").props.description === stageDefs.in_service.description, "coluna recebe rotulo e texto do catalogo (textos da clinica)");
check(boardColumns[0].props.current === true && boardColumns.slice(1).every((node) => node.props.current === false), "primeira coluna devolvida e a atual");

same([views.panelTabs({ canDashboard: false, canConfigure: false }), views.panelTabs({ canDashboard: true, canConfigure: false }), views.panelTabs({ canDashboard: false, canConfigure: true }), views.panelTabs({ canDashboard: true, canConfigure: true })],
  [["board"], ["board", "dashboard"], ["board", "settings"], ["board", "dashboard", "settings"]], "abas: Etapas so com can_configure; painel gerencial so com can_dashboard");
same([views.nextPanelTab(["board", "dashboard", "settings"], "settings", "ArrowRight"), views.nextPanelTab(["board", "dashboard", "settings"], "board", "ArrowLeft"), views.nextPanelTab(["board", "settings"], "board", "End"), views.nextPanelTab(["board"], "board", "ArrowRight")],
  ["board", "settings", "settings", null], "teclado das abas (setas circulam, Home/End, aba unica ignora)");

// ---------------------------------------------------------------------------
// 16. Aba "Etapas" (FunnelSettingsPanel real): GET /settings, restaurar
//     padrao, PUT com a versao lida e 409 que rebaseia o rascunho
// ---------------------------------------------------------------------------
let serverSettings = { ...settingsPayload, stage_labels: { scheduled: "Agendou" }, stage_descriptions: {}, reason_labels: {} };
let putReply = (sent) => ({ body: { ...serverSettings, ...sent, version: sent.version + 1, stages: serverSettings.stages, reasons: serverSettings.reasons, template: "clinic_v1" } });
responder = (path, init) => {
  if (path !== "/api/funnel/settings") return notFound;
  if ((init.method || "GET") === "PUT") return putReply(JSON.parse(init.body));
  return { body: serverSettings };
};
const lostSettings = [];
const settingsHarness = hookHarness();
const renderSettings = () => settingsHarness.render(() => views.FunnelSettingsPanel({ auth: simAuth, catalog: clinic, onAccessLost: (error) => lostSettings.push(error) }));
mark = fetchCalls.length;
let settingsTree = renderSettings();
check(textOf(settingsTree).includes("Carregando os textos das etapas…"), "aba Etapas: carregando");
await settle();
settingsTree = renderSettings();
same(since(mark), ["GET /api/funnel/settings"], "aba Etapas: 1 GET /settings");
const fieldBy = (suffix) => [...elements(settingsTree, "input"), ...elements(settingsTree, "textarea")].find((node) => String(node.props.id || "").endsWith(suffix)) || null;
const helpBy = (suffix) => elements(settingsTree, "small").find((node) => String(node.props.id || "").endsWith(`${suffix}-help`)) || null;
const restoreButton = (subject) => elements(settingsTree, "button").find((node) => textOf(node).startsWith("Restaurar padrão") && textOf(node).includes(subject)) || null;
const submitButton = () => elements(settingsTree, "button").find((node) => node.props.type === "submit");
check(fieldBy("-label-scheduled").props.value === "Agendou" && fieldBy("-label-loyal").props.value === "Paciente em acompanhamento" && fieldBy("-description-new").props.value === stageDefs.new.description, "campos com o texto da clinica ou o padrao");
check(fieldBy("-label-scheduled").props.maxLength === 40 && fieldBy("-description-new").props.maxLength === 200 && fieldBy("-reason-other").props.maxLength === 40, "limites 40/200 nos campos");
check(textOf(helpBy("-description-new")) === `${stageDefs.new.description.length}/200` && textOf(helpBy("-label-scheduled")) === "7/40", "contadores dos campos");
check(restoreButton("da etapa Cliente Agendado")?.props.disabled === false && restoreButton("da etapa Paciente em acompanhamento")?.props.disabled === true, "restaurar padrao so na etapa personalizada");
check(submitButton().props.disabled === true && textOf(settingsTree).includes("Personalizado") && textOf(settingsTree).includes("Padrão"), "sem alteracao: salvar desabilitado; selos Personalizado/Padrao");
fieldBy("-label-loyal").props.onChange({ target: { value: "Em\ntratamento" } });
settingsTree = renderSettings();
check(fieldBy("-label-loyal").props.value === "Em tratamento" && submitButton().props.disabled === false && textOf(settingsTree).includes("Há alterações não salvas."), "colar com quebra vira espaco; alteracao habilita salvar");
fieldBy("-reason-price").props.onChange({ target: { value: "p".repeat(41) } });
settingsTree = renderSettings();
check(textOf(helpBy("-reason-price")).includes("41/40 · Use até 40 caracteres.") && fieldBy("-reason-price").props["aria-invalid"] === true && submitButton().props.disabled === true, "nome acima de 40: erro no campo e salvar bloqueado");
fieldBy("-reason-price").props.onChange({ target: { value: "Valor" } });
fieldBy("-description-loyal").props.onChange({ target: { value: "x".repeat(201) } });
settingsTree = renderSettings();
check(textOf(helpBy("-description-loyal")).includes("201/200 · Use até 200 caracteres.") && submitButton().props.disabled === true, "texto acima de 200: salvar bloqueado");
restoreButton("da etapa Paciente em acompanhamento").props.onClick();
settingsTree = renderSettings();
check(fieldBy("-label-loyal").props.value === "Paciente em acompanhamento" && fieldBy("-description-loyal").props.value === stageDefs.loyal.description, "restaurar padrao da etapa volta nome e texto");
restoreButton("do motivo Preço").props.onClick();
fieldBy("-label-loyal").props.onChange({ target: { value: "Em tratamento" } });
settingsTree = renderSettings();
mark = fetchCalls.length;
elements(settingsTree, "form")[0].props.onSubmit({ preventDefault() {} });
await settle();
settingsTree = renderSettings();
same(since(mark), ["PUT /api/funnel/settings"], "salvar = 1 PUT /settings");
same(fetchCalls.at(-1).body, { version: 3, stage_labels: { scheduled: "Agendou", loyal: "Em tratamento" }, stage_descriptions: {}, reason_labels: {} }, "PUT com a versao lida e so o que difere do padrao");
check(textOf(settingsTree).includes("Textos salvos.") && submitButton().props.disabled === true, "salvo: aviso e sem alteracoes pendentes");
// 409: outra pessoa salvou antes; recarrega e reaplica so o que mudei.
serverSettings = { ...settingsPayload, version: 9, stage_labels: { scheduled: "Agendou", awaiting_followup: "Retornar" }, stage_descriptions: {}, reason_labels: { other: "Outros" } };
putReply = () => ({ status: 409, body: { detail: { code: "stale_version", message: "x" } } });
fieldBy("-label-scheduled").props.onChange({ target: { value: "Agendou consulta" } });
settingsTree = renderSettings();
mark = fetchCalls.length;
elements(settingsTree, "form")[0].props.onSubmit({ preventDefault() {} });
await settle();
settingsTree = renderSettings();
await settle();
settingsTree = renderSettings();
same(since(mark), ["PUT /api/funnel/settings", "GET /api/funnel/settings"], "409: PUT recusado e a versao do servidor relida");
check(textOf(settingsTree).includes("Outra pessoa salvou estes textos antes. Carregamos a versão atual e mantivemos as suas alterações: revise e salve de novo."), "409: aviso de conflito");
same([fieldBy("-label-scheduled").props.value, fieldBy("-label-awaiting_followup").props.value, fieldBy("-reason-other").props.value, fieldBy("-label-loyal").props.value],
  ["Agendou consulta", "Retornar", "Outros", "Paciente em acompanhamento"], "rebase: minha mudanca por cima; o resto (inclusive o que a outra pessoa tirou) do servidor");
putReply = (sent) => ({ body: { ...serverSettings, ...sent, version: sent.version + 1 } });
mark = fetchCalls.length;
elements(settingsTree, "form")[0].props.onSubmit({ preventDefault() {} });
await settle();
same(fetchCalls.at(-1).body, { version: 9, stage_labels: { scheduled: "Agendou consulta", awaiting_followup: "Retornar" }, stage_descriptions: {}, reason_labels: { other: "Outros" } }, "salvar de novo: versao nova do servidor");
putReply = () => ({ status: 409, body: { detail: { code: "try_again", message: "x" } } });
settingsTree = renderSettings();
fieldBy("-label-scheduled").props.onChange({ target: { value: "Agendou!" } });
settingsTree = renderSettings();
mark = fetchCalls.length;
elements(settingsTree, "form")[0].props.onSubmit({ preventDefault() {} });
await settle();
settingsTree = renderSettings();
same(since(mark), ["PUT /api/funnel/settings"], "409 try_again: nao recarrega");
check(textOf(settingsTree).includes(FUNNEL_ERROR_MESSAGES.try_again) && fieldBy("-label-scheduled").props.value === "Agendou!", "try_again: mensagem e rascunho intacto");
putReply = () => ({ status: 403, body: { detail: { code: "permission_denied", message: "x" } } });
elements(settingsTree, "form")[0].props.onSubmit({ preventDefault() {} });
await settle();
check(lostSettings.length === 1 && lostSettings[0].status === 403, "403 no PUT: aba fecha (acesso perdido)");
check(fetchCalls.every((call) => call.method === "GET" || (call.method === "PUT" && call.path === "/api/funnel/settings")), "unica escrita do sim: PUT /api/funnel/settings");

console.log(`OK: ${checks} verificacoes do frontend do funil v2 (fixtures do clinic_v1, normalizacao, ApiError, erros e encerramento, reducer, sinais, cache do /config e textos salvos, operation_id, catalogo puro, aba Etapas, guardas, cartao, desfecho do Encerrar, revalidacao leve do drawer, painel gerencial, coluna e quadro), sem rede`);
