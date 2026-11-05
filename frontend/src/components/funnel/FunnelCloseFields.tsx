import { useEffect, useId, useState } from "react";
import { ApiError } from "../../api";
import { useOperationId } from "../../features/followup/useOperation";
import {
  buildCloseFunnel, CLOSE_NOTE_MAX, closeChoiceProblem, closeFormMode, closeKeepsStage, closeNoteAllowed, closeOutcomeStages, contactStageLabel, effectiveCloseChoice,
  EMPTY_CLOSE_DRAFT, findStage, formatDateTime, freezeCloseDraft, funnelCloseErrorMessage, invalidateFunnelConfig, loadContactStage, patchCloseDraft, selectableReasons,
  staleCurrent, stageLegacyQualification, useFunnelAccess, useFunnelCatalog,
  type CloseBase, type CloseChoice, type CloseDraft, type CloseFormMode, type CloseFunnelBody, type FunnelCatalog, type StaleCurrent,
} from "../../features/funnel";
import type { Contact, Conversation } from "../../types";

export type FunnelCloseForm = {
  mode: CloseFormMode;
  catalog: FunnelCatalog | null;
  // Base efetiva (com o motivo atual, quando o GET leve ja respondeu).
  base: CloseBase;
  choice: CloseChoice;
  setChoice: (patch: Partial<CloseChoice>) => void;
  conflict: StaleCurrent | null;
  error: string;
  problem: string;
  // Legado equivalente da etapa escolhida (patch local do contato).
  legacyQualification: string | null;
  // Valida e devolve o `funnel` do set-attendance (operation_id estavel por
  // payload: reenvio apos falha de rede vira replay no backend) ou null.
  prepare: (conversationId: string) => CloseFunnelBody | null;
  // Erro do encerramento: 409 stale_version vira o aviso de conflito (e a
  // nova base); erros com code do funil ficam no modal. true = tratado.
  handleError: (error: unknown) => boolean;
};

type CurrentReason = { stage: string; version: number; reason: string | null };

// Estado do desfecho pelo funil no "Encerrar atendimento" (decisao do PO de
// 28/10: o desfecho E a etapa). A base (etapa + versao) e a do contato ao
// abrir o modal; so um 409 stale_version a troca (quem mudou fica visivel e
// a escolha que a pessoa via fica fixa para o "Reaplicar").
export function useFunnelCloseForm(contact: Contact, thread?: Conversation | null): FunnelCloseForm {
  const funnel = useFunnelCatalog();
  const access = useFunnelAccess();
  const operationId = useOperationId();
  const [base, setBase] = useState<CloseBase>(() => ({ stage: contact.crm_stage || null, version: contact.crm_stage_version ?? 0 }));
  const [draft, setDraft] = useState<CloseDraft>(EMPTY_CLOSE_DRAFT);
  const [current, setCurrent] = useState<CurrentReason | null>(null);
  const [conflict, setConflict] = useState<StaleCurrent | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const mode = closeFormMode(funnel, contact, thread);
  const catalog = funnel.catalog;
  // Etapa atual com motivo (Não convertido): o motivo nao vem no contato
  // (pode ser dado de saude). 1 GET leve da etapa so neste caso, para
  // pre-selecionar o motivo registrado (manter = so sincroniza o legado).
  const needsReason = mode === "funnel" && Boolean(base.stage) && Boolean(findStage(catalog, base.stage)?.requires_reason);
  const auth = access.auth;
  useEffect(() => {
    if (!needsReason || !auth || !base.stage) return;
    let cancelled = false;
    const stage = base.stage;
    const version = base.version;
    loadContactStage(auth, contact.id).then((check) => {
      const fresh = check?.stage;
      const freshVersion = Number.isInteger(check?.version) ? Number(check.version) : fresh?.version;
      // So vale para a MESMA etapa e versao da base (senao o 409 explica).
      if (!cancelled && fresh && fresh.key === stage && freshVersion === version) {
        setCurrent({ stage, version, reason: fresh.reason?.key || null });
      }
    }, () => { /* sem pre-selecao: a pessoa escolhe o motivo */ });
    return () => { cancelled = true; };
  }, [needsReason, auth, contact.id, base.stage, base.version]);

  const effectiveBase: CloseBase = current && current.stage === base.stage && current.version === base.version ? { ...base, reason: current.reason } : base;
  const choice = effectiveCloseChoice(catalog, draft, effectiveBase);
  const problem = mode === "funnel" ? closeChoiceProblem(catalog, choice, effectiveBase) : "";

  function setChoice(patch: Partial<CloseChoice>) {
    setError("");
    setDraft((value) => patchCloseDraft(value, patch));
  }

  function prepare(conversationId: string): CloseFunnelBody | null {
    if (mode !== "funnel") return null;
    const invalid = closeChoiceProblem(catalog, choice, effectiveBase);
    if (invalid) { setError(invalid); return null; }
    const payload = buildCloseFunnel(catalog, choice, effectiveBase);
    if (!payload) return null;
    setError(""); setConflict(null);
    return { ...payload, operation_id: operationId({ contact_id: contact.id, conversation_id: conversationId, attempt, ...payload }) };
  }

  function handleError(cause: unknown): boolean {
    const stale = staleCurrent(cause);
    if (stale) {
      // A escolha exibida (inclusive pre-selecao) fica fixa: a base nova nao
      // pode trocar sozinha o desfecho que a pessoa confirmou.
      setDraft((value) => freezeCloseDraft(value, choice));
      setConflict(stale);
      setBase({ stage: stale.stage, version: stale.version });
      setError("");
      return true;
    }
    if (!(cause instanceof ApiError) || !cause.code) return false;
    // Mesmo operation_id com outro corpo: a proxima tentativa usa id novo.
    if (cause.code === "operation_reused") setAttempt((value) => value + 1);
    // Funil saiu do ar depois que a tela carregou: o /config e relido e, sem
    // catalogo, o modal volta ao desfecho legado.
    if (cause.code === "funnel_disabled") invalidateFunnelConfig();
    setError(funnelCloseErrorMessage(cause));
    return true;
  }

  return {
    mode, catalog, base: effectiveBase, choice, setChoice, conflict, error, problem,
    legacyQualification: mode === "funnel" ? stageLegacyQualification(catalog, choice.target) : null,
    prepare, handleError,
  };
}

const APPOINTMENT_OPTIONS = [["", "Não informar"], ["consultation", "Consulta"], ["procedure", "Procedimento"]] as const;

// Campos do desfecho pelo funil: lista de desfechos (rotulo + texto
// explicativo), motivo obrigatorio em etapa que exige (nota so em "Outro",
// com o aviso de dado clinico) e tipo de compromisso opcional.
export function FunnelCloseFields({ form, disabled, onReapply }: { form: FunnelCloseForm; disabled: boolean; onReapply?: () => void }) {
  const id = useId();
  if (form.mode === "loading") return <p className="sub fn-close-loading" role="status">Carregando os desfechos do funil…</p>;
  if (form.mode !== "funnel" || !form.catalog) return null;
  const { catalog, base, choice, conflict, error } = form;
  const outcomes = closeOutcomeStages(catalog);
  const target = outcomes.find((stage) => stage.key === choice.target) || null;
  const keep = closeKeepsStage(choice, base);
  const reasons = target?.requires_reason ? selectableReasons(catalog, target) : [];
  const noteAllowed = closeNoteAllowed(catalog, choice, base);
  const note = choice.note;
  const currentReason = keep && base.reason ? reasons.find((entry) => entry.key === base.reason) || null : null;
  return <div className="fn-close-fields">
    <p className="sub">Etapa atual no funil: <strong>{contactStageLabel(catalog, base.stage)}</strong>. O desfecho escolhido passa a ser a etapa do contato no funil comercial.</p>
    {conflict && <div className="fn-notice fn-notice--warning" role="alert">
      <strong>Outra pessoa mudou a etapa deste contato.</strong>
      <span>Agora está em <strong>{contactStageLabel(catalog, conflict.stage)}</strong>{conflict.changed_at ? ` desde ${formatDateTime(conflict.changed_at)}` : ""}{conflict.changed_by_name ? `, por ${conflict.changed_by_name}` : ""}.</span>
      {onReapply && !form.problem ? <div className="fn-inline"><button type="button" className="fn-button fn-button--primary" onClick={onReapply} disabled={disabled}>Reaplicar minha escolha</button><span className="fn-help">Encerra com o desfecho marcado abaixo, a partir da etapa atual.</span></div>
        : <span>Revise o desfecho abaixo antes de encerrar.</span>}
    </div>}
    {error && <p className="fn-notice fn-notice--danger" role="alert">{error}</p>}
    <fieldset className="fn-fieldset" disabled={disabled}>
      <legend>Desfecho *</legend>
      <div className="fn-radio-list">{outcomes.map((stage, index) => {
        const selected = choice.target === stage.key;
        // Foco inicial do modal (o select legado tinha autoFocus).
        const focus = selected || (!target && index === 0);
        return <label key={stage.key} className={`fn-radio fn-kind-edge--${stage.kind}${selected ? " is-selected" : ""}`}>
          <input type="radio" name={`${id}-outcome`} value={stage.key} checked={selected} autoFocus={focus} onChange={() => form.setChoice({ target: stage.key })} />
          <span><strong>{stage.label}{stage.key === base.stage ? " (etapa atual)" : ""}</strong>{stage.description && <small>{stage.description}</small>}</span>
        </label>;
      })}</div>
    </fieldset>
    {keep && <p className="sub fn-close-keep">O contato continua em <strong>{target?.label}</strong>; o encerramento só registra o desfecho.</p>}
    {reasons.length > 0 && <fieldset className="fn-fieldset" disabled={disabled}>
      <legend>Motivo *</legend>
      {keep && <p className="fn-help">{currentReason ? `Motivo registrado: ${currentReason.label}. Escolher outro corrige o motivo.` : "Confirme o motivo. Se for outro, o motivo registrado é corrigido."}</p>}
      <div className="fn-radio-list fn-radio-list--compact">{reasons.map((entry) => <label key={entry.key} className={`fn-radio${choice.reason === entry.key ? " is-selected" : ""}`}>
        <input type="radio" name={`${id}-reason`} value={entry.key} checked={choice.reason === entry.key} onChange={() => form.setChoice({ reason: entry.key })} />
        <span><strong>{entry.label}{currentReason?.key === entry.key ? " (atual)" : ""}</strong>{entry.hint && <small>{entry.hint}</small>}</span>
      </label>)}</div>
    </fieldset>}
    {noteAllowed && <label className="fn-field" htmlFor={`${id}-note`}>
      <span>Detalhe do motivo (opcional)</span>
      <input id={`${id}-note`} type="text" value={note} maxLength={CLOSE_NOTE_MAX} autoComplete="off" disabled={disabled} aria-describedby={`${id}-note-help`}
        onChange={(event) => form.setChoice({ note: event.target.value })} />
      <small id={`${id}-note-help`} className="fn-warning-text">Não registre dados clínicos. Texto curto, até {CLOSE_NOTE_MAX} caracteres ({note.trim().length}/{CLOSE_NOTE_MAX}), visível só no histórico do funil.</small>
    </label>}
    {target?.appointment_kind && !keep && <fieldset className="fn-fieldset" disabled={disabled}>
      <legend>Tipo de compromisso (opcional)</legend>
      <div className="fn-choice-row">{APPOINTMENT_OPTIONS.map(([value, text]) => <label key={value || "none"} className="fn-choice">
        <input type="radio" name={`${id}-appointment`} value={value} checked={choice.appointment === value} onChange={() => form.setChoice({ appointment: value })} /><span>{text}</span>
      </label>)}</div>
    </fieldset>}
  </div>;
}
