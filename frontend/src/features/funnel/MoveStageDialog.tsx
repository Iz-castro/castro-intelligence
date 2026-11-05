import { useId, useMemo, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import type { Auth } from "firebase/auth";
import { ApiError } from "../../api";
import { useOperationId } from "../followup/useOperation";
import { useLayer } from "./a11y";
import { moveContactStage } from "./api";
import { moveTargets, selectableReasons } from "./catalog";
import { funnelErrorMessage } from "./errors";
import { formatDateTime } from "./format";
import type { AppointmentKind, FunnelCatalog, FunnelStage, MoveStageBody, MoveStageResponse, StaleCurrent, SuggestionSource } from "./types";

export type MoveStageDialogProps = {
  auth: Auth;
  catalog: FunnelCatalog;
  contactId: number;
  contactName: string;
  currentStage: string | null;
  currentReason?: string | null;
  expectedVersion: number;
  initialTarget?: string | null;
  suggestedBy?: SuggestionSource | null;
  returnFocus?: () => HTMLElement | null;
  onClose: () => void;
  onMoved: (response: MoveStageResponse) => void;
  onConflict?: (current: StaleCurrent) => void;
  // 401/404/sessao invalida: o contato saiu do acesso (quem abriu fecha tudo).
  onAccessLost?: (error: unknown) => void;
};

const CONTROL = /[\x00-\x1f\x7f]/;
const NOTE_MAX = 120;
const SESSION_CODES = ["tenant_mismatch", "read_only_session", "user_inactive", "funnel_disabled", "out_of_scope"];

export function staleCurrent(error: unknown): StaleCurrent | null {
  if (!(error instanceof ApiError) || error.status !== 409 || error.code !== "stale_version") return null;
  const current = (error.detail as { current?: Partial<StaleCurrent> } | undefined)?.current;
  if (!current || typeof current !== "object") return null;
  return {
    stage: typeof current.stage === "string" && current.stage ? current.stage : null,
    version: Number.isInteger(current.version) ? Number(current.version) : 0,
    changed_at: typeof current.changed_at === "string" ? current.changed_at : null,
    changed_by_user_id: typeof current.changed_by_user_id === "number" ? current.changed_by_user_id : null,
    changed_by_name: typeof current.changed_by_name === "string" ? current.changed_by_name : null,
  };
}

export function MoveStageDialog(props: MoveStageDialogProps) {
  const { auth, catalog, contactId, contactName, onClose, onMoved, onConflict, onAccessLost } = props;
  const id = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const operationId = useOperationId();
  const stages = useMemo(() => new Map(catalog.stages.map((stage) => [stage.key, stage])), [catalog]);
  // Ponto de partida da mudanca (expected_version). Um 409 stale_version troca
  // para o estado atual do servidor: reaplicar ou escolher outra etapa.
  const [base, setBase] = useState<{ stage: string | null; version: number; reason: string | null }>({
    stage: props.currentStage, version: props.expectedVersion, reason: props.currentReason ?? null,
  });
  // Sugestao (ex.: bot registrou agendamento) so pre-seleciona destino valido.
  const initial = props.initialTarget && moveTargets(catalog, props.currentStage).some((stage) => stage.key === props.initialTarget) ? props.initialTarget : "";
  const [target, setTarget] = useState(initial);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [appointment, setAppointment] = useState<"" | AppointmentKind>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<StaleCurrent | null>(null);
  const [attempt, setAttempt] = useState(0);
  useLayer(dialogRef, () => { if (!busyRef.current) onClose(); }, { initialFocus: firstFieldRef, returnFocus: props.returnFocus });

  // Destinos escolhiveis e visiveis no quadro deste usuario (moveTargets).
  const targets = moveTargets(catalog, base.stage);
  const targetDef: FunnelStage | null = target ? stages.get(target) || null : null;
  const reasons = selectableReasons(catalog, targetDef);
  const reasonDef = reasons.find((entry) => entry.key === reason) || null;
  const correcting = Boolean(targetDef && target === base.stage);
  const focusKey = target || targets[0]?.key || "";
  const label = (key: string | null) => (key ? stages.get(key)?.label || key : "Fora do funil");
  const fromLabel = label(base.stage);
  const alreadyThere = Boolean(targetDef && target === base.stage && !targetDef.requires_reason);

  function choose(key: string) {
    setTarget(key); setError("");
    const next = stages.get(key);
    if (!next?.requires_reason) { setReason(""); setNote(""); }
    if (!next?.appointment_kind) setAppointment("");
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (busyRef.current) return;
    setError("");
    if (!targetDef) { setError("Escolha a nova etapa."); return; }
    if (targetDef.requires_reason && !reasonDef) { setError("Informe o motivo."); return; }
    if (target === base.stage && (!targetDef.requires_reason || reason === base.reason)) { setError(targetDef.requires_reason ? "Escolha um motivo diferente do atual." : "O contato já está nesta etapa."); return; }
    const cleanNote = reasonDef?.allows_note ? note.trim() : "";
    if (cleanNote && (cleanNote.length > NOTE_MAX || CONTROL.test(cleanNote))) { setError(`Use até ${NOTE_MAX} caracteres, sem quebra de linha.`); return; }
    const body: Omit<MoveStageBody, "operation_id"> = {
      to_stage: target,
      expected_version: base.version,
      reason: targetDef.requires_reason ? reason : null,
      reason_note: cleanNote || null,
      appointment_kind: targetDef.appointment_kind && appointment ? appointment : null,
      suggested_by: props.suggestedBy && target === initial ? props.suggestedBy : null,
    };
    busyRef.current = true; setBusy(true); setConflict(null);
    try {
      // Mesmo corpo = mesmo operation_id (reenvio apos falha de rede vira replay).
      const response = await moveContactStage(auth, contactId, { ...body, operation_id: operationId({ contact_id: contactId, attempt, ...body }) });
      busyRef.current = false; setBusy(false);
      onMoved(response);
      onClose();
    } catch (cause) {
      busyRef.current = false; setBusy(false);
      const current = staleCurrent(cause);
      if (current) {
        setConflict(current);
        setBase({ stage: current.stage, version: current.version, reason: null });
        onConflict?.(current);
        return;
      }
      if (cause instanceof ApiError && (cause.status === 401 || cause.status === 404 || SESSION_CODES.includes(cause.code || ""))) { onAccessLost?.(cause); return; }
      // Mesmo operation_id com outro corpo: a proxima tentativa usa id novo.
      if (cause instanceof ApiError && cause.code === "operation_reused") setAttempt((value) => value + 1);
      setError(funnelErrorMessage(cause));
    }
  }

  return createPortal(<div className="fn-layer fn-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busyRef.current) onClose(); }}>
    <div className="fn-dialog" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-subtitle`} ref={dialogRef} tabIndex={-1}>
      <header className="fn-dialog-header">
        <div><h2 id={`${id}-title`}>Mover para…</h2><p id={`${id}-subtitle`}>{contactName} · etapa atual: <strong>{fromLabel}</strong></p></div>
        <button type="button" className="fn-icon-button" onClick={onClose} disabled={busy} aria-label="Fechar sem mudar a etapa">✕</button>
      </header>
      <form onSubmit={(event) => void submit(event)} className="fn-dialog-body" noValidate>
        {conflict && <div className="fn-notice fn-notice--warning" role="alert">
          <strong>Outra pessoa mudou a etapa deste contato.</strong>
          <span>Agora está em <strong>{label(conflict.stage)}</strong>{conflict.changed_at ? ` desde ${formatDateTime(conflict.changed_at)}` : ""}{conflict.changed_by_name ? `, por ${conflict.changed_by_name}` : ""}.</span>
          {alreadyThere ? <span>O contato já está na etapa escolhida: nada mais a fazer.</span>
            : targetDef ? <div className="fn-inline"><button type="button" className="fn-button fn-button--primary" onClick={() => void submit()} disabled={busy}>Reaplicar minha escolha</button><span className="fn-help">Parte da etapa atual. Você também pode escolher outra etapa abaixo.</span></div> : null}
        </div>}
        {error && <p className="fn-notice fn-notice--danger" role="alert">{error}</p>}
        <fieldset className="fn-fieldset" disabled={busy}>
          <legend>Nova etapa</legend>
          <div className="fn-radio-list">{targets.map((stage) => {
            const selected = target === stage.key;
            return <label key={stage.key} className={`fn-radio fn-kind-edge--${stage.kind}${selected ? " is-selected" : ""}`}>
              <input type="radio" name={`${id}-stage`} value={stage.key} checked={selected} ref={stage.key === focusKey ? firstFieldRef : undefined} onChange={() => choose(stage.key)} />
              <span><strong>{stage.label}{stage.key === base.stage ? " (corrigir motivo)" : ""}</strong>{stage.description && <small>{stage.description}</small>}</span>
            </label>;
          })}</div>
        </fieldset>
        {targetDef?.requires_reason && <fieldset className="fn-fieldset" disabled={busy}>
          <legend>Motivo *</legend>
          <div className="fn-radio-list fn-radio-list--compact">{reasons.map((entry) => <label key={entry.key} className={`fn-radio${reason === entry.key ? " is-selected" : ""}`}>
            <input type="radio" name={`${id}-reason`} value={entry.key} checked={reason === entry.key} onChange={() => { setReason(entry.key); if (!entry.allows_note) setNote(""); setError(""); }} />
            <span><strong>{entry.label}{correcting && entry.key === base.reason ? " (atual)" : ""}</strong>{entry.hint && <small>{entry.hint}</small>}</span>
          </label>)}</div>
        </fieldset>}
        {targetDef?.requires_reason && reasonDef?.allows_note && <label className="fn-field" htmlFor={`${id}-note`}>
          <span>Detalhe do motivo (opcional)</span>
          <input id={`${id}-note`} type="text" value={note} maxLength={NOTE_MAX} onChange={(event) => setNote(event.target.value)} aria-describedby={`${id}-note-help`} disabled={busy} autoComplete="off" />
          <small id={`${id}-note-help`} className="fn-warning-text">Não registre dados clínicos. Texto curto, até {NOTE_MAX} caracteres ({note.trim().length}/{NOTE_MAX}), visível só no histórico.</small>
        </label>}
        {targetDef?.appointment_kind && <fieldset className="fn-fieldset" disabled={busy}>
          <legend>Tipo de compromisso (opcional)</legend>
          <div className="fn-choice-row">
            {([["", "Não informar"], ["consultation", "Consulta"], ["procedure", "Procedimento"]] as const).map(([value, text]) => <label key={value || "none"} className="fn-choice"><input type="radio" name={`${id}-appointment`} value={value} checked={appointment === value} onChange={() => setAppointment(value)} /><span>{text}</span></label>)}
          </div>
        </fieldset>}
        {targetDef && !alreadyThere && <p className="fn-summary" aria-live="polite">{correcting ? `Corrigir o motivo em ${targetDef.label}` : `De ${fromLabel} para ${targetDef.label}`}</p>}
        <p className="fn-help">Mudar a etapa não envia mensagem ao paciente e não altera o dono do lead, o atendimento nem as tarefas.</p>
        <div className="fn-dialog-actions">
          <button type="button" className="fn-button" onClick={onClose} disabled={busy}>Cancelar</button>
          <button type="submit" className="fn-button fn-button--primary" disabled={busy || !targetDef || alreadyThere || (Boolean(targetDef?.requires_reason) && !reasonDef)}>{busy ? "Salvando…" : "Confirmar mudança"}</button>
        </div>
      </form>
    </div>
  </div>, document.body);
}
