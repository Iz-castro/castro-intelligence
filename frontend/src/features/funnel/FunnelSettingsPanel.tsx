import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import type { Auth } from "firebase/auth";
import { ApiError } from "../../api";
import { loadFunnelSettings, saveFunnelSettings } from "./api";
import { funnelErrorCode, funnelErrorMessage, isAccessLost } from "./errors";
import {
  cleanSettingsText, defaultDraft, DESCRIPTION_MAX, isSettingsPayload, LABEL_MAX, rebaseSettingsDraft, sameSettings, settingsBody, settingsDefaults, settingsDraft, settingsProblems,
  type SettingsDraft, type SettingsField,
} from "./settingsForm";
import { invalidateFunnelConfig } from "./useFunnelConfig";
import type { FunnelCatalog, FunnelSettings } from "./types";

type Props = { auth: Auth; catalog: FunnelCatalog; onAccessLost: (error: unknown) => void };

function versionOf(settings: Partial<FunnelSettings> | null): number {
  return Number.isInteger(settings?.version) && Number(settings?.version) > 0 ? Number(settings?.version) : 0;
}

// Aba "Etapas" (capabilities.can_configure = gerenciar_config_sistema): a
// clinica renomeia etapas e motivos e edita o texto explicativo de cada
// etapa, sem deploy. Nao cria nem remove etapas; as chaves nunca mudam.
// Salvar = PUT com a versao lida; 409 stale_version recarrega a versao do
// servidor (com as alteracoes desta pessoa por cima, para revisar e salvar
// de novo); depois de salvar, o cache do /config e invalidado (quadro,
// cartao, filtro e encerramento usam os nomes novos).
export function FunnelSettingsPanel({ auth, catalog, onAccessLost }: Props) {
  const id = useId();
  const [server, setServer] = useState<FunnelSettings | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<{ tone: "success" | "warning"; text: string } | null>(null);
  const [nonce, setNonce] = useState(0);
  const sequence = useRef(0);
  const catalogRef = useRef(catalog);
  catalogRef.current = catalog;
  const lostRef = useRef(onAccessLost);
  lostRef.current = onAccessLost;
  // Rascunho a reaplicar sobre a versao recarregada depois de um 409.
  const rebaseRef = useRef<{ mine: SettingsDraft; base: SettingsDraft | null } | null>(null);

  useEffect(() => {
    const request = ++sequence.current;
    let cancelled = false;
    setLoading(true); setError("");
    loadFunnelSettings(auth).then((value) => {
      if (cancelled || request !== sequence.current) return;
      const fresh = settingsDraft(value, settingsDefaults(value, catalogRef.current));
      const rebase = rebaseRef.current;
      rebaseRef.current = null;
      setServer(value);
      setDraft(rebase ? rebaseSettingsDraft(rebase.mine, rebase.base, fresh) : fresh);
    }, (reason: unknown) => {
      if (cancelled || request !== sequence.current) return;
      if (isAccessLost(reason)) { lostRef.current(reason); return; }
      setError(funnelErrorMessage(reason));
    }).finally(() => { if (!cancelled && request === sequence.current) setLoading(false); });
    return () => { cancelled = true; };
  }, [auth, nonce]);

  const defaults = useMemo(() => settingsDefaults(server, catalog), [server, catalog]);
  const problems = draft ? settingsProblems(draft) : {};
  const hasProblems = Object.keys(problems).length > 0;
  const savedBody = useMemo(() => (server ? settingsBody(versionOf(server), settingsDraft(server, defaults), defaults) : null), [server, defaults]);
  const draftBody = draft ? settingsBody(versionOf(server), draft, defaults) : null;
  const dirty = Boolean(savedBody && draftBody && !sameSettings(savedBody, draftBody));
  const allDefault = Boolean(draftBody && !Object.keys(draftBody.stage_labels).length && !Object.keys(draftBody.stage_descriptions).length && !Object.keys(draftBody.reason_labels).length);
  // Salvando ou recarregando (ex.: depois de um 409): o formulario nao muda.
  const locked = busy || loading;

  function update(field: SettingsField, key: string, value: string) {
    setNotice(null);
    setDraft((current) => (current ? { ...current, [field]: { ...current[field], [key]: cleanSettingsText(value) } } : current));
  }

  function restoreStage(key: string) {
    const stage = defaults.stages.find((entry) => entry.key === key);
    if (!stage) return;
    setNotice(null);
    setDraft((current) => (current ? {
      ...current,
      stage_labels: { ...current.stage_labels, [key]: stage.default_label },
      stage_descriptions: { ...current.stage_descriptions, [key]: stage.default_description },
    } : current));
  }

  function restoreReason(key: string) {
    const reason = defaults.reasons.find((entry) => entry.key === key);
    if (!reason) return;
    setNotice(null);
    setDraft((current) => (current ? { ...current, reason_labels: { ...current.reason_labels, [key]: reason.default_label } } : current));
  }

  async function save(event?: FormEvent) {
    event?.preventDefault();
    if (!draft || !server || locked || hasProblems || !dirty) return;
    setBusy(true); setError(""); setNotice(null);
    try {
      const response = await saveFunnelSettings(auth, settingsBody(versionOf(server), draft, defaults));
      // Resposta com o estado novo (shape do GET) vale direto (e ja vale nas
      // outras telas, mesmo antes do /config novo chegar); senao, rele.
      const saved = isSettingsPayload(response) ? response : null;
      invalidateFunnelConfig(saved);
      if (saved) { setServer(saved); setDraft(settingsDraft(saved, settingsDefaults(saved, catalog))); }
      else setNonce((value) => value + 1);
      setNotice({ tone: "success", text: "Textos salvos. O quadro, o “Mover para…”, o filtro das conversas e o encerramento do atendimento já usam os novos nomes." });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409 && funnelErrorCode(cause) !== "try_again") {
        // stale_version: recarrega a versao do servidor e reaplica por cima
        // o que esta pessoa mudou (nada e salvo sem ela revisar).
        rebaseRef.current = { mine: draft, base: settingsDraft(server, defaults) };
        setNotice({ tone: "warning", text: "Outra pessoa salvou estes textos antes. Carregamos a versão atual e mantivemos as suas alterações: revise e salve de novo." });
        setNonce((value) => value + 1);
      } else if (isAccessLost(cause)) {
        onAccessLost(cause);
      } else if (cause instanceof ApiError && cause.code === "overrides_invalid") {
        // Mensagem do backend diz qual campo (nome, texto ou motivo).
        setError(cause.message || funnelErrorMessage(cause));
      } else {
        setError(funnelErrorMessage(cause));
      }
    } finally { setBusy(false); }
  }

  const counter = (value: string, maximum: number) => `${value.trim().length}/${maximum}`;
  return <div className="fn-settings">
    <p className="fn-help">Nomes e textos explicativos que a equipe vê no quadro, no “Mover para…” e no encerramento do atendimento. Valem para toda a empresa. As etapas e as regras não mudam: o histórico e os relatórios continuam válidos.</p>
    {notice && <p className={`fn-notice fn-notice--${notice.tone}`} role="status">{notice.text}</p>}
    {error && <div className="fn-notice fn-notice--danger" role="alert"><span>{error}</span>{!draft && <button type="button" className="fn-button" onClick={() => setNonce((value) => value + 1)}>Tentar novamente</button>}</div>}
    {loading && !draft ? <p className="fn-help" role="status">Carregando os textos das etapas…</p> : draft && <form onSubmit={(event) => void save(event)} noValidate aria-busy={locked}>
      <section className="fn-settings-section" aria-labelledby={`${id}-stages`}>
        <h3 id={`${id}-stages`}>Etapas</h3>
        <ol className="fn-settings-list">{defaults.stages.map((stage) => {
          const label = draft.stage_labels[stage.key] ?? "";
          const description = draft.stage_descriptions[stage.key] ?? "";
          const labelProblem = problems[`stage_labels.${stage.key}`];
          const descriptionProblem = problems[`stage_descriptions.${stage.key}`];
          const custom = label.trim() !== stage.default_label || description.trim() !== stage.default_description;
          return <li key={stage.key} className="fn-settings-item">
            <div className="fn-settings-item-head">
              <strong>{label.trim() || stage.default_label}</strong>
              {custom ? <span className="fn-badge fn-badge--info">Personalizado</span> : <span className="fn-badge fn-badge--neutral">Padrão</span>}
            </div>
            <label className="fn-field" htmlFor={`${id}-label-${stage.key}`}>
              <span>Nome da etapa</span>
              <input id={`${id}-label-${stage.key}`} type="text" value={label} maxLength={LABEL_MAX} autoComplete="off" disabled={locked}
                aria-describedby={`${id}-label-${stage.key}-help`} aria-invalid={labelProblem ? true : undefined}
                onChange={(event) => update("stage_labels", stage.key, event.target.value)} />
              <small id={`${id}-label-${stage.key}-help`} className="fn-counter">{counter(label, LABEL_MAX)}{labelProblem ? ` · ${labelProblem}` : label.trim() ? "" : ` · vazio volta ao padrão: ${stage.default_label}`}</small>
            </label>
            <label className="fn-field" htmlFor={`${id}-description-${stage.key}`}>
              <span>Texto explicativo</span>
              <textarea id={`${id}-description-${stage.key}`} rows={3} value={description} maxLength={DESCRIPTION_MAX} disabled={locked}
                aria-describedby={`${id}-description-${stage.key}-help`} aria-invalid={descriptionProblem ? true : undefined}
                onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }}
                onChange={(event) => update("stage_descriptions", stage.key, event.target.value)} />
              <small id={`${id}-description-${stage.key}-help`} className="fn-counter">{counter(description, DESCRIPTION_MAX)}{descriptionProblem ? ` · ${descriptionProblem}` : ""}</small>
            </label>
            <button type="button" className="fn-button" disabled={locked || !custom} onClick={() => restoreStage(stage.key)}>Restaurar padrão<span className="fn-sr"> da etapa {stage.default_label}</span></button>
          </li>;
        })}</ol>
      </section>
      <section className="fn-settings-section" aria-labelledby={`${id}-reasons`}>
        <h3 id={`${id}-reasons`}>Motivos de não conversão</h3>
        <ul className="fn-settings-reasons">{defaults.reasons.map((reason) => {
          const label = draft.reason_labels[reason.key] ?? "";
          const problem = problems[`reason_labels.${reason.key}`];
          const custom = label.trim() !== reason.default_label;
          return <li key={reason.key} className="fn-settings-reason">
            <label className="fn-field" htmlFor={`${id}-reason-${reason.key}`}>
              <span>{reason.default_label}{custom ? " (personalizado)" : ""}</span>
              <input id={`${id}-reason-${reason.key}`} type="text" value={label} maxLength={LABEL_MAX} autoComplete="off" disabled={locked}
                aria-describedby={`${id}-reason-${reason.key}-help`} aria-invalid={problem ? true : undefined}
                onChange={(event) => update("reason_labels", reason.key, event.target.value)} />
              <small id={`${id}-reason-${reason.key}-help`} className="fn-counter">{counter(label, LABEL_MAX)}{problem ? ` · ${problem}` : ""}</small>
            </label>
            <button type="button" className="fn-button" disabled={locked || !custom} onClick={() => restoreReason(reason.key)}>Restaurar padrão<span className="fn-sr"> do motivo {reason.default_label}</span></button>
          </li>;
        })}</ul>
      </section>
      <div className="fn-settings-actions">
        <button type="button" className="fn-button" disabled={locked || allDefault} onClick={() => { setNotice(null); setDraft(defaultDraft(defaults)); }}>Restaurar todos os padrões</button>
        <button type="button" className="fn-button" disabled={locked || !dirty} onClick={() => { setNotice(null); setDraft(server ? settingsDraft(server, defaults) : draft); }}>Descartar alterações</button>
        <button type="submit" className="fn-button fn-button--primary" disabled={locked || !dirty || hasProblems}>{busy ? "Salvando…" : "Salvar textos"}</button>
      </div>
      {dirty && !busy && <p className="fn-help" role="status">Há alterações não salvas.</p>}
    </form>}
  </div>;
}
