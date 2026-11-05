import type { Contact, Conversation } from "../../types";
import type { AppointmentKind, CloseFunnelBody, FunnelCatalog, FunnelReason, FunnelStage, StageState } from "./types";

// Helpers PUROS do catalogo do funil (sem React, sem I/O). Este modulo so
// importa tipos: o CrmContext usa daqui sem criar ciclo de import com as
// telas do funil (que importam o CrmContext).

// Filtro da barra lateral com catalogo: valores com prefixo para nunca
// colidir com os valores legados de qualification ("novo", "convertido"...).
export const STAGE_FILTER_PREFIX = "stage:";
// qualification legada que ainda NAO e desfecho (gate do fechamento manual).
export const LEGACY_OPEN_QUALIFICATIONS: readonly string[] = ["novo", "em_atendimento"];
export const CLOSE_NOTE_MAX = 120;

const CONTROL = /[\x00-\x1f\x7f]/;
const STAGE_KEY = /^[a-z][a-z0-9_]{1,39}$/;

export type FunnelUiStatus = "off" | "loading" | "ready";
export type FunnelUi = { status: FunnelUiStatus; catalog: FunnelCatalog | null };

export function findStage(catalog: FunnelCatalog | null | undefined, key: string | null | undefined): FunnelStage | null {
  if (!catalog || !key || !Array.isArray(catalog.stages)) return null;
  return catalog.stages.find((stage) => stage.key === key) || null;
}

// Mesma regra do funnel_catalog.stage_visible: sem permissao de
// visibilidade, a etapa aparece para quem ve o funil. `visible` do /config
// (calculado no servidor para este usuario) tambem precisa permitir.
export function stageVisible(stage: Pick<FunnelStage, "visibility_permission" | "visible"> | null | undefined, has: (permission: string) => boolean): boolean {
  if (stage?.visible === false) return false;
  const permission = stage?.visibility_permission;
  return !permission || Boolean(has(permission));
}

// Rotulo curto da etapa do contato (chips do chat e da barra lateral).
export function contactStageLabel(catalog: FunnelCatalog | null | undefined, key: string | null | undefined): string {
  if (!key) return "Fora do funil";
  return findStage(catalog, key)?.label || "Etapa fora do catálogo";
}

export type StageFilterOption = { value: string; label: string };

// Opcoes do filtro da barra lateral: etapas ativas e visiveis ao usuario.
export function stageFilterOptions(catalog: FunnelCatalog | null | undefined, has: (permission: string) => boolean): StageFilterOption[] {
  return (catalog?.stages || [])
    .filter((stage) => stage.active !== false && stageVisible(stage, has))
    .map((stage) => ({ value: `${STAGE_FILTER_PREFIX}${stage.key}`, label: stage.label }));
}

// Etapa de um valor do filtro ("stage:new" -> "new"); null = valor legado.
export function stageFromFilter(value: string | null | undefined): string | null {
  if (typeof value !== "string" || !value.startsWith(STAGE_FILTER_PREFIX)) return null;
  return value.slice(STAGE_FILTER_PREFIX.length) || null;
}

// O valor do filtro ainda existe entre as opcoes exibidas? (catalogo chegou
// ou saiu: o filtro antigo esconderia tudo sem opcao visivel no select).
export function filterValueValid(value: string, stageOptions: StageFilterOption[] | null, unreadValue: string): boolean {
  if (!value || value === unreadValue) return true;
  if (stageOptions) return stageOptions.some((option) => option.value === value);
  return stageFromFilter(value) === null;
}

// Filtro da barra lateral sobre o CONTATO (o "Não lidas" e da thread e fica
// no chamador): "stage:<chave>" compara a etapa; o resto, a qualificacao.
export function contactMatchesFilter(value: string, contact: Pick<Contact, "crm_stage" | "qualification"> | null | undefined): boolean {
  if (!value) return true;
  const stage = stageFromFilter(value);
  if (stage) return contact?.crm_stage === stage;
  return (contact?.qualification || "novo") === value;
}

// Destinos do "Mover para…": etapas ativas, escolhiveis e visiveis no quadro
// deste usuario (mover para uma etapa que ele nao ve tiraria o contato da
// vista dele). A etapa atual so entra quando usa motivo (corrigir o motivo).
export function moveTargets(catalog: FunnelCatalog | null | undefined, currentStage: string | null | undefined): FunnelStage[] {
  return (catalog?.stages || []).filter((stage) => stage.active && stage.manual_target && stage.visible !== false
    && (stage.key !== currentStage || stage.requires_reason));
}

// ---------------------------------------------------------------------------
// Encerrar atendimento ("uma classificação só", decisao do PO de 28/10)
// ---------------------------------------------------------------------------

// Desfechos oferecidos no modal (fc.close_outcomes). Template sem sync do
// legado (explicito) nao usa o funil no encerramento.
export function closeOutcomeStages(catalog: FunnelCatalog | null | undefined): FunnelStage[] {
  if (!catalog || catalog.legacy_qualification_sync === false || !Array.isArray(catalog.stages)) return [];
  return catalog.stages.filter((stage) => stage.active !== false && stage.manual_target !== false && stage.close_outcome === true);
}

// Backup e arquivado nao mudam de etapa (409 contact_unavailable): o
// encerramento deles segue o fluxo legado.
export function closeExcluded(contact: Pick<Contact, "is_backup" | "is_archived"> | null | undefined, thread?: Pick<Conversation, "is_backup"> | null): boolean {
  return !contact || Boolean(contact.is_backup) || Boolean(contact.is_archived) || Boolean(thread?.is_backup);
}

export type CloseFormMode = "legacy" | "loading" | "funnel";

export function closeFormMode(funnel: FunnelUi, contact: Pick<Contact, "is_backup" | "is_archived"> | null | undefined, thread?: Pick<Conversation, "is_backup"> | null): CloseFormMode {
  if (closeExcluded(contact, thread) || funnel.status === "off") return "legacy";
  if (funnel.status === "loading") return "loading";
  return closeOutcomeStages(funnel.catalog).length > 0 ? "funnel" : "legacy";
}

// Tipos de etapa que continuam pedindo o desfecho no fechamento (decisao do
// PO): em andamento (Aguardando retorno) e perdida (Nao convertido) abrem o
// modal mesmo sendo desfechos; ganha (Cliente Agendado, Paciente em
// acompanhamento) e excluida (Nao qualificado) fecham direto.
export const CLOSE_GATE_KINDS: readonly string[] = ["open", "lost"];

// Espelha o gate do backend (funnel_service.close_gate): etapa atual que nao
// e desfecho de encerramento (inclusive sem etapa), etapa de tipo em
// CLOSE_GATE_KINDS OU legado ainda novo/em_atendimento.
export function closeGateApplies(catalog: FunnelCatalog | null | undefined, contact: Pick<Contact, "crm_stage" | "qualification"> | null | undefined): boolean {
  const current = contact?.crm_stage || null;
  const isOutcome = Boolean(current) && closeOutcomeStages(catalog).some((stage) => stage.key === current);
  const kind = findStage(catalog, current)?.kind;
  return !isOutcome || (typeof kind === "string" && CLOSE_GATE_KINDS.includes(kind))
    || LEGACY_OPEN_QUALIFICATIONS.includes(contact?.qualification || "novo");
}

// Menu "Fechar atendimento": abre o modal (desfecho obrigatorio) ou fecha
// direto. Catalogo ainda carregando = modal (ele mostra o carregamento).
export function closeOpensModal(funnel: FunnelUi, contact: Pick<Contact, "crm_stage" | "qualification" | "is_backup" | "is_archived">, thread?: Pick<Conversation, "is_backup"> | null): boolean {
  const mode = closeFormMode(funnel, contact, thread);
  if (mode === "loading") return true;
  if (mode === "funnel") return closeGateApplies(funnel.catalog, contact);
  return LEGACY_OPEN_QUALIFICATIONS.includes(contact.qualification || "novo");
}

export type CloseChoice = { target: string; reason: string; note: string; appointment: "" | AppointmentKind };
// Ponto de partida do encerramento: etapa e versao do contato ao abrir o
// modal (ou do 409). `reason` = motivo ATUAL (Activity apontada, lido pelo
// GET leve da etapa) so para pre-selecionar; undefined = desconhecido.
export type CloseBase = { stage: string | null; version: number; reason?: string | null };
// Rascunho do usuario: target/reason undefined = ainda nao escolheu (vale a
// pre-selecao da etapa atual e do motivo atual).
export type CloseDraft = { target?: string; reason?: string; note: string; appointment: "" | AppointmentKind };
export const EMPTY_CLOSE_DRAFT: CloseDraft = { note: "", appointment: "" };

export function selectableReasons(catalog: FunnelCatalog | null | undefined, stage: Pick<FunnelStage, "reason_keys"> | null | undefined): FunnelReason[] {
  const allowed = stage?.reason_keys;
  return (catalog?.reasons || []).filter((reason) => reason.active && reason.selectable && (!allowed?.length || allowed.includes(reason.key)));
}

// Pre-selecao do modal: a etapa atual, quando ja e desfecho.
export function initialCloseTarget(catalog: FunnelCatalog | null | undefined, base: CloseBase): string {
  return base.stage && closeOutcomeStages(catalog).some((stage) => stage.key === base.stage) ? base.stage : "";
}

// Manter a etapa atual nao muda a etapa (o backend so sincroniza o legado).
// Etapa com motivo continua exigindo o motivo (validate_change exige antes
// de comparar): o motivo atual mantem; outro motivo corrige o registrado.
export function closeKeepsStage(choice: Pick<CloseChoice, "target">, base: CloseBase): boolean {
  return Boolean(choice.target) && choice.target === base.stage;
}

// O que o modal mostra e envia: o rascunho com as pre-selecoes aplicadas e
// sem os campos que nao valem para o desfecho escolhido.
export function effectiveCloseChoice(catalog: FunnelCatalog | null | undefined, draft: CloseDraft, base: CloseBase): CloseChoice {
  const target = draft.target ?? initialCloseTarget(catalog, base);
  const stage = closeOutcomeStages(catalog).find((entry) => entry.key === target) || null;
  let reason = "";
  if (stage?.requires_reason) {
    const wanted = draft.reason ?? (target === base.stage ? base.reason || "" : "");
    reason = selectableReasons(catalog, stage).some((entry) => entry.key === wanted) ? wanted : "";
  }
  const keep = Boolean(target) && target === base.stage;
  const choice: CloseChoice = { target, reason, note: "", appointment: stage?.appointment_kind && !keep ? draft.appointment : "" };
  if (closeNoteAllowed(catalog, choice, base)) choice.note = draft.note;
  return choice;
}

// Nota livre: so no motivo que aceita (Outro). Manter o MESMO motivo atual
// nao grava nada (o backend so sincroniza o legado): sem nota.
export function closeNoteAllowed(catalog: FunnelCatalog | null | undefined, choice: Pick<CloseChoice, "target" | "reason">, base: CloseBase): boolean {
  const stage = closeOutcomeStages(catalog).find((entry) => entry.key === choice.target);
  if (!stage?.requires_reason) return false;
  const reason = selectableReasons(catalog, stage).find((entry) => entry.key === choice.reason);
  if (!reason?.allows_note) return false;
  return !(closeKeepsStage(choice, base) && base.reason && base.reason === reason.key);
}

// Mudanca do usuario no rascunho. Trocar de desfecho recomeca motivo, nota e
// compromisso; trocar de motivo limpa a nota.
export function patchCloseDraft(draft: CloseDraft, patch: Partial<CloseChoice>): CloseDraft {
  if (patch.target !== undefined && patch.target !== draft.target) {
    return { target: patch.target, reason: patch.reason, note: patch.note ?? "", appointment: patch.appointment ?? "" };
  }
  const next: CloseDraft = { ...draft, ...patch };
  if (patch.reason !== undefined && patch.reason !== draft.reason && patch.note === undefined) next.note = "";
  return next;
}

// 409 stale_version: a base troca para o estado do servidor; o que o
// usuario VIA escolhido (inclusive pre-selecao) fica fixo para o "Reaplicar".
export function freezeCloseDraft(draft: CloseDraft, choice: CloseChoice): CloseDraft {
  return { ...draft, target: choice.target || draft.target, reason: choice.reason || draft.reason, note: choice.note || draft.note };
}

// "" = escolha valida; senao, o que falta (texto ao usuario).
export function closeChoiceProblem(catalog: FunnelCatalog | null | undefined, choice: CloseChoice, base: CloseBase): string {
  const target = closeOutcomeStages(catalog).find((stage) => stage.key === choice.target);
  if (!target) return "Escolha o desfecho.";
  if (!target.requires_reason) return "";
  const reason = selectableReasons(catalog, target).find((entry) => entry.key === choice.reason);
  if (!reason) return "Informe o motivo.";
  const note = closeNoteAllowed(catalog, choice, base) ? choice.note.trim() : "";
  if (note && (note.length > CLOSE_NOTE_MAX || CONTROL.test(note))) return `Use até ${CLOSE_NOTE_MAX} caracteres, sem quebra de linha.`;
  return "";
}

// Corpo `funnel` do set-attendance (sem operation_id) ou null se invalido.
export function buildCloseFunnel(catalog: FunnelCatalog | null | undefined, choice: CloseChoice, base: CloseBase): Omit<CloseFunnelBody, "operation_id"> | null {
  if (closeChoiceProblem(catalog, choice, base)) return null;
  const target = closeOutcomeStages(catalog).find((stage) => stage.key === choice.target);
  if (!target) return null;
  const keep = closeKeepsStage(choice, base);
  const reason = target.requires_reason ? selectableReasons(catalog, target).find((entry) => entry.key === choice.reason) || null : null;
  const note = closeNoteAllowed(catalog, choice, base) ? choice.note.trim() : "";
  return {
    to_stage: target.key,
    expected_version: Number.isInteger(base.version) && base.version > 0 ? base.version : 0,
    reason: reason ? reason.key : null,
    reason_note: note || null,
    appointment_kind: !keep && target.appointment_kind && choice.appointment ? choice.appointment : null,
  };
}

// qualification legada que o backend grava junto da etapa (patch local do
// contato apos o encerramento); null = o catalogo nao informa.
export function stageLegacyQualification(catalog: FunnelCatalog | null | undefined, key: string | null | undefined): string | null {
  const value = findStage(catalog, key)?.legacy_qualification;
  return typeof value === "string" && value ? value : null;
}

// Campos crm_* do contato a partir do StageState devolvido pelo backend
// (resposta do encerramento). Payload incompleto = nada a aplicar.
export function contactStagePatch(stage: Partial<StageState> | null | undefined): Partial<Pick<Contact, "crm_stage" | "crm_stage_version" | "crm_stage_changed_at" | "crm_stage_source">> {
  if (!stage || typeof stage.key !== "string" || !STAGE_KEY.test(stage.key) || !Number.isInteger(stage.version) || Number(stage.version) < 0) return {};
  return {
    crm_stage: stage.key,
    crm_stage_version: Number(stage.version),
    ...(typeof stage.changed_at === "string" && stage.changed_at ? { crm_stage_changed_at: stage.changed_at } : {}),
    ...(typeof stage.source === "string" && stage.source ? { crm_stage_source: stage.source } : {}),
  };
}

// Copia local do contato com a etapa gravada por uma tela do funil ("Mover
// para…", 409 com a etapa atual). So avanca a versao (nunca regride o que o
// listener ja entregou); `legacyQualification` = legado que a mudanca MANUAL
// gravou junto. Nada a aplicar = o MESMO objeto (sem re-render).
export function contactWithStage<T extends Pick<Contact, "crm_stage_version" | "qualification">>(contact: T, stage: Partial<StageState> | null | undefined, legacyQualification?: string | null): T {
  const patch = contactStagePatch(stage);
  if (patch.crm_stage_version === undefined || (contact.crm_stage_version ?? 0) >= patch.crm_stage_version) return contact;
  return { ...contact, ...patch, ...(legacyQualification ? { qualification: legacyQualification } : {}) };
}
