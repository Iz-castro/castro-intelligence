import { useEffect, useId, useRef, useState } from "react";
import type { Auth } from "firebase/auth";
import { loadCommercialPreference, setCommercialPreference, type CommercialPreference } from "./api";
import { formatMoment } from "./time";
import { isAccessDenied, requestError, useOperationId } from "./useOperation";

export function PreferenceEditor({ auth, contactId, canRegister, canReactivate, onChanged, onAccessDenied }: {
  auth: Auth; contactId: number; canRegister: boolean; canReactivate: boolean; onChanged: (active: boolean) => void;
  onAccessDenied?: (reason: unknown) => void;
}) {
  const id = useId();
  const [preference, setPreference] = useState<CommercialPreference | null>(null);
  const [mode, setMode] = useState<"block" | "unblock" | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const operationId = useOperationId();

  useEffect(() => {
    let cancelled = false;
    setPreference(null); setError(""); setMode(null);
    void loadCommercialPreference(auth, contactId).then((value) => {
      if (!cancelled) { setPreference(value); onChanged(value.active); }
    }).catch((reason) => { if (!cancelled) { if (isAccessDenied(reason)) onAccessDenied?.(reason); setError(requestError(reason)); } });
    return () => { cancelled = true; };
  }, [auth, contactId, onChanged, onAccessDenied]);

  async function save() {
    if (!preference || !mode || !confirmed || lock.current) return;
    lock.current = true; setBusy(true); setError("");
    const body = { active: mode === "block", version: preference.version, patient_request_confirmed: true };
    try {
      await setCommercialPreference(auth, contactId, body, operationId(body));
      const refreshed = await loadCommercialPreference(auth, contactId);
      setPreference(refreshed); onChanged(refreshed.active); setMode(null); setConfirmed(false);
    } catch (reason) { if (isAccessDenied(reason)) onAccessDenied?.(reason); setError(requestError(reason)); }
    finally { lock.current = false; setBusy(false); }
  }

  return <section className="fu-preference" aria-labelledby={`${id}-title`}>
    <h4 id={`${id}-title`}>Preferência de contato comercial</h4>
    {error && <p className="fu-notice fu-notice--danger" role="alert">{error}</p>}
    {!preference && !error && <p className="fu-help" role="status">Consultando preferência…</p>}
    {preference?.active ? <p className="fu-notice fu-notice--warning"><strong>Paciente não deseja novos contatos comerciais.</strong><span>Retomadas comerciais estão impedidas. Consultas marcadas e tarefas independentes permanecem.</span>{preference.updated_at && <span>Registro: {formatMoment(preference.updated_at)}</span>}</p> : preference && <p className="fu-help">Nenhuma recusa comercial geral registrada. Os demais bloqueios e regras de contato continuam válidos.</p>}
    {!mode && preference && <div className="fu-inline">{!preference.active && canRegister && <button className="fu-button fu-button--danger" type="button" onClick={() => { setMode("block"); setConfirmed(false); }}>Registrar pedido de não receber contatos comerciais</button>}{preference.active && canReactivate && <button className="fu-button" type="button" onClick={() => { setMode("unblock"); setConfirmed(false); }}>Registrar nova autorização do paciente</button>}</div>}
    {mode && <div className="fu-confirm">
      <p>{mode === "block" ? "Este pedido vale para futuras retomadas comerciais deste paciente na clínica. Não se limita a esta tarefa e não cancela consultas, revoga LGPD ou fecha o atendimento." : "A reversão exige uma manifestação específica do paciente. Uma mensagem nova genérica não basta. Os outros bloqueios e limites permanecem."}</p>
      <label className="fu-check" htmlFor={`${id}-confirmed`}><input id={`${id}-confirmed`} type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} /><span>{mode === "block" ? "O paciente pediu explicitamente que parem os novos contatos comerciais." : "O paciente pediu explicitamente para voltar a receber contatos comerciais."}</span></label>
      <div className="fu-inline"><button type="button" className="fu-button" disabled={busy} onClick={() => setMode(null)}>Voltar</button><button type="button" className={`fu-button ${mode === "block" ? "fu-button--danger" : "fu-button--primary"}`} disabled={busy || !confirmed} onClick={() => void save()}>{busy ? "Salvando…" : "Confirmar registro"}</button></div>
    </div>}
  </section>;
}
