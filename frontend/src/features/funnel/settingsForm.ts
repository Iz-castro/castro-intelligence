import type { FunnelCatalog, FunnelSettings, FunnelSettingsBody } from "./types";

// Aba "Etapas" (textos da clinica). PURO: rascunho do formulario, corpo do
// PUT e validacao com as mesmas regras do funnel_catalog.validate_overrides
// (nome <= 40, texto <= 200, sem caractere de controle; vazio = padrao).

export const LABEL_MAX = 40;
export const DESCRIPTION_MAX = 200;
const CONTROL = /[\x00-\x1f\x7f]/;
const CONTROL_RUN = /[\x00-\x1f\x7f]+/g;

export type SettingsField = "stage_labels" | "stage_descriptions" | "reason_labels";
export type SettingsDraft = Record<SettingsField, Record<string, string>>;
export type SettingsDefaults = {
  stages: { key: string; default_label: string; default_description: string }[];
  reasons: { key: string; default_label: string }[];
};

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringMap(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
}

function keyed<T extends { key?: unknown }>(items: unknown): (T & { key: string })[] {
  return Array.isArray(items) ? items.filter((item): item is T & { key: string } => Boolean(item) && typeof (item as T).key === "string" && Boolean((item as T).key)) : [];
}

// Padroes do template: vem do GET /settings. Payload sem a lista cai no
// catalogo (default_* quando o /config traz; senao o texto atual).
export function settingsDefaults(payload: Partial<FunnelSettings> | null | undefined, catalog: FunnelCatalog | null | undefined): SettingsDefaults {
  const stages = keyed<{ key?: unknown; default_label?: unknown; default_description?: unknown }>(payload?.stages);
  const reasons = keyed<{ key?: unknown; default_label?: unknown }>(payload?.reasons);
  return {
    stages: stages.length
      ? stages.map((stage) => ({ key: stage.key, default_label: text(stage.default_label) || stage.key, default_description: text(stage.default_description) }))
      : (catalog?.stages || []).map((stage) => ({ key: stage.key, default_label: stage.default_label || stage.label, default_description: stage.default_description ?? stage.description ?? "" })),
    reasons: reasons.length
      ? reasons.map((reason) => ({ key: reason.key, default_label: text(reason.default_label) || reason.key }))
      : (catalog?.reasons || []).map((reason) => ({ key: reason.key, default_label: reason.default_label || reason.label })),
  };
}

// Valores efetivos no formulario: o texto da clinica ou, sem ele, o padrao.
export function settingsDraft(payload: Partial<FunnelSettings> | null | undefined, defaults: SettingsDefaults): SettingsDraft {
  const labels = stringMap(payload?.stage_labels);
  const descriptions = stringMap(payload?.stage_descriptions);
  const reasons = stringMap(payload?.reason_labels);
  return {
    stage_labels: Object.fromEntries(defaults.stages.map((stage) => [stage.key, labels[stage.key]?.trim() || stage.default_label])),
    stage_descriptions: Object.fromEntries(defaults.stages.map((stage) => [stage.key, descriptions[stage.key]?.trim() || stage.default_description])),
    reason_labels: Object.fromEntries(defaults.reasons.map((reason) => [reason.key, reasons[reason.key]?.trim() || reason.default_label])),
  };
}

export function defaultDraft(defaults: SettingsDefaults): SettingsDraft {
  return settingsDraft(null, defaults);
}

// Corpo do PUT: so o que difere do padrao. Vazio ou igual ao padrao fica
// fora (volta ao texto do template, inclusive depois de um deploy novo).
export function settingsBody(version: number, draft: SettingsDraft, defaults: SettingsDefaults): FunnelSettingsBody {
  const changed = (values: Record<string, string>, items: { key: string }[], fallback: (key: string) => string) => Object.fromEntries(
    items.map((item) => [item.key, (values[item.key] || "").trim()] as const).filter(([key, value]) => value && value !== fallback(key)),
  );
  const stage = (key: string) => defaults.stages.find((entry) => entry.key === key);
  return {
    version: Number.isInteger(version) && version > 0 ? version : 0,
    stage_labels: changed(draft.stage_labels, defaults.stages, (key) => stage(key)?.default_label || ""),
    stage_descriptions: changed(draft.stage_descriptions, defaults.stages, (key) => stage(key)?.default_description || ""),
    reason_labels: changed(draft.reason_labels, defaults.reasons, (key) => defaults.reasons.find((entry) => entry.key === key)?.default_label || ""),
  };
}

// Mesmo conteudo salvo? (compara so os textos, nunca a versao)
export function sameSettings(left: FunnelSettingsBody, right: FunnelSettingsBody): boolean {
  const canonical = (body: FunnelSettingsBody) => JSON.stringify([body.stage_labels, body.stage_descriptions, body.reason_labels].map((values) => Object.entries(values).sort(([a], [b]) => a.localeCompare(b))));
  return canonical(left) === canonical(right);
}

// Problemas por campo ("stage_labels.new" -> texto). Vazio = ok.
export function settingsProblems(draft: SettingsDraft): Record<string, string> {
  const problems: Record<string, string> = {};
  for (const [field, maximum] of [["stage_labels", LABEL_MAX], ["stage_descriptions", DESCRIPTION_MAX], ["reason_labels", LABEL_MAX]] as const) {
    for (const [key, raw] of Object.entries(draft[field])) {
      const value = raw.trim();
      if (value.length > maximum) problems[`${field}.${key}`] = `Use até ${maximum} caracteres.`;
      else if (CONTROL.test(value)) problems[`${field}.${key}`] = "Sem quebra de linha.";
    }
  }
  return problems;
}

// Texto digitado/colado: quebra de linha e outros controles viram espaco
// (o backend recusa caractere de controle).
export function cleanSettingsText(value: string): string {
  return value.replace(CONTROL_RUN, " ");
}

export function isSettingsPayload(value: unknown): value is FunnelSettings {
  const item = value as Partial<FunnelSettings> | null;
  return Boolean(item) && typeof item === "object" && Number.isInteger(item?.version)
    && Boolean(item?.stage_labels) && typeof item?.stage_labels === "object";
}

const FIELDS: readonly SettingsField[] = ["stage_labels", "stage_descriptions", "reason_labels"];

// 409 stale_version (outra pessoa salvou antes): o formulario recarrega a
// versao do servidor e reaplica por cima SO o que esta pessoa mudou em
// relacao ao que ela tinha carregado (`base`); o resto vem do servidor.
// Nada e salvo sem ela revisar e salvar de novo.
export function rebaseSettingsDraft(mine: SettingsDraft, base: SettingsDraft | null, theirs: SettingsDraft): SettingsDraft {
  const next = {} as SettingsDraft;
  for (const field of FIELDS) {
    next[field] = Object.fromEntries(Object.keys(theirs[field] || {}).map((key) => {
      const own = mine[field]?.[key];
      const loaded = base?.[field]?.[key];
      const changed = typeof own === "string" && (base ? own.trim() !== (loaded ?? "").trim() : false);
      return [key, changed ? own : theirs[field][key]];
    }));
  }
  return next;
}

// Textos recem-salvos (resposta do PUT) sobre um catalogo do /config que
// ainda nao os tem (overrides_version menor: outra instancia do backend com
// o cache de 30 s). Mesmo resultado do resolve_funnel: texto da clinica ou,
// sem ele, o padrao. Catalogo ja na versao (ou mais novo) volta intacto.
export function catalogWithSettings(catalog: FunnelCatalog, saved: Partial<FunnelSettings> | null | undefined): FunnelCatalog {
  if (!catalog || !isSettingsPayload(saved)) return catalog;
  const current = Number.isInteger(catalog.overrides_version) ? Number(catalog.overrides_version) : 0;
  if (current >= saved.version) return catalog;
  const texts = settingsDraft(saved, settingsDefaults(saved, catalog));
  return {
    ...catalog,
    overrides_version: saved.version,
    stages: (catalog.stages || []).map((stage) => ({
      ...stage,
      label: texts.stage_labels[stage.key] || stage.label,
      description: texts.stage_descriptions[stage.key] ?? stage.description,
    })),
    reasons: (catalog.reasons || []).map((reason) => ({ ...reason, label: texts.reason_labels[reason.key] || reason.label })),
  };
}
