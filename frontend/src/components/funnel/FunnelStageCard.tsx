import { useEffect, useId, useRef, useState } from "react";
import { useCrm } from "../../context/CrmContext";
import type { Contact } from "../../types";
import {
  closeOutcomeStages, daysInStageText, elapsedDays, formatDateTime, funnelErrorMessage, InfoButton, isAccessLost, loadContactHistory, MoveStageDialog, StageHistory,
  useFunnelAccess, useFunnelConfig, type FunnelCatalog, type HistoryItem, type MoveStageResponse,
} from "../../features/funnel";

// Etapa vinda do POST/409 desta tela. Vale sobre a do contato ao vivo so
// enquanto tiver versao MAIOR: contato fora do snapshot (picker, extra) nao
// recebe listener, e o snapshot pode atrasar alguns segundos.
type LocalStage = { contactId: number; key: string | null; version: number; changedAt: string | null; reason: { key: string; label: string } | null };

type HistoryState = { key: string; items: HistoryItem[]; cursor: string | null; busy: boolean; error: string };
const EMPTY_HISTORY: HistoryState = { key: "", items: [], cursor: null, busy: false, error: "" };

function stageLabel(catalog: FunnelCatalog | null | undefined, key: string | null | undefined): string | null {
  if (!key) return null;
  return catalog?.stages.find((stage) => stage.key === key)?.label || null;
}

function historyError(reason: unknown): string {
  return isAccessLost(reason) ? "O histórico deste contato não está disponível no seu acesso atual." : funnelErrorMessage(reason);
}

// Cartao "Etapa do funil" no painel do contato: e a classificacao do
// contato (decisao do PO de 28/10: "uma classificação só"; o antigo cartao
// "Qualificação" sai quando ha catalogo). Le a etapa do contato NORMALIZADO
// (ao vivo) + o catalogo de useFunnelConfig (1 GET por sessao, em cache);
// historico so ao expandir; "Mover para…"/"Incluir no funil" sempre pelo
// dialogo confirmado. Nada aqui assume, abre conversa, pega tarefa ou manda
// mensagem. Indisponivel (Ver como, flag, tenant, permissao) = nada
// renderizado e nenhuma requisicao.
export function FunnelStageCard({ contact }: { contact: Contact }) {
  const { sessionUser } = useCrm();
  const access = useFunnelAccess();
  const { config, error: configError, accessLost, loading, reload } = useFunnelConfig(access.auth, access.available, access.accessKey);
  const auth = access.auth;
  const id = useId();
  const contactId = contact.id;
  const moveRef = useRef<HTMLButtonElement>(null);
  const historySeq = useRef(0);
  const [local, setLocal] = useState<LocalStage | null>(null);
  // `version`: o aviso de sucesso vale so enquanto a etapa exibida for a que
  // ele anuncia (outra pessoa mudou depois = aviso velho some).
  const [notice, setNotice] = useState<{ contactId: number; text: string; tone: "success" | "warning"; version?: number } | null>(null);
  const [dialog, setDialog] = useState<{ contactId: number; trigger: HTMLElement | null } | null>(null);
  // Estado amarrado ao contato: trocar de contato no painel fecha historico,
  // explicacao, dialogo e aviso no MESMO render (o App tambem remonta por key).
  const [historyFor, setHistoryFor] = useState<number | null>(null);
  const historyOpen = historyFor === contactId;
  const [infoFor, setInfoFor] = useState<number | null>(null);
  const infoOpen = infoFor === contactId;
  const [history, setHistory] = useState<HistoryState>(EMPTY_HISTORY);

  useEffect(() => {
    historySeq.current++;
    setHistory(EMPTY_HISTORY);
  }, [contactId]);

  const catalog = config?.catalog || null;
  const capabilities = config?.capabilities || null;
  const liveVersion = contact.crm_stage_version ?? 0;
  const own = local && local.contactId === contactId && local.version > liveVersion ? local : null;
  const stageKey = own ? own.key : contact.crm_stage || null;
  const version = own ? own.version : liveVersion;
  const changedAt = own ? own.changedAt : contact.crm_stage_changed_at || null;
  // Motivo nunca vem no contato (pode ser dado de saude): so o que esta tela
  // acabou de gravar, enquanto for a versao exibida.
  const reason = local && local.contactId === contactId && local.version === version && local.key === stageKey ? local.reason : null;
  const stageDef = stageKey && catalog ? catalog.stages.find((stage) => stage.key === stageKey) || null : null;
  const privileged = Boolean(capabilities?.privileged);
  const unavailable = Boolean(contact.is_backup || contact.is_archived);
  // Mesma regra do _write_scope do backend: gestao, dono do lead ou contato
  // sem dono. Quem so acessa por thread propria (coex) ve a etapa, nao move.
  const writeScope = privileged || (sessionUser != null && contact.assigned_to === sessionUser.id) || (!contact.assigned_to_uid && contact.assigned_to == null);
  const canMove = Boolean(capabilities?.can_move) && writeScope && !unavailable;
  // Historico: o backend so entrega no escopo de escrita; arquivado/backup
  // so para a gestao (os demais recebem 404).
  const historyAllowed = writeScope && (privileged || !unavailable);
  const historyKey = `${contactId}:${version}`;
  const shownNotice = notice && notice.contactId === contactId && (notice.version === undefined || notice.version === version) ? notice : null;

  // Primeira pagina ao expandir (e de novo se a etapa mudar com ele aberto).
  useEffect(() => {
    if (!historyOpen || !historyAllowed || !auth || !access.available) return;
    let cancelled = false;
    const request = ++historySeq.current;
    setHistory({ key: historyKey, items: [], cursor: null, busy: true, error: "" });
    loadContactHistory(auth, contactId).then((page) => {
      if (cancelled || request !== historySeq.current) return;
      setHistory({ key: historyKey, items: Array.isArray(page.items) ? page.items : [], cursor: page.next_cursor || null, busy: false, error: "" });
    }, (cause: unknown) => {
      if (cancelled || request !== historySeq.current) return;
      setHistory({ key: historyKey, items: [], cursor: null, busy: false, error: historyError(cause) });
    });
    return () => { cancelled = true; };
  }, [historyOpen, historyAllowed, auth, access.available, contactId, historyKey]);

  if (!access.available || accessLost) return null;

  function moreHistory() {
    if (!auth || !history.cursor || history.busy) return;
    const request = ++historySeq.current;
    const { key, cursor } = history;
    setHistory((state) => ({ ...state, busy: true, error: "" }));
    loadContactHistory(auth, contactId, cursor).then((page) => {
      if (request !== historySeq.current) return;
      setHistory((state) => state.key !== key ? state : {
        ...state,
        items: [...state.items, ...(Array.isArray(page.items) ? page.items : []).filter((item) => !state.items.some((existing) => existing.id === item.id && existing.event_type === item.event_type))],
        cursor: page.next_cursor || null, busy: false, error: "",
      });
    }, (cause: unknown) => {
      if (request === historySeq.current) setHistory((state) => ({ ...state, busy: false, error: historyError(cause) }));
    });
  }

  function moved(response: MoveStageResponse) {
    const stage = response.stage;
    if (stage && Number.isInteger(stage.version)) {
      setLocal({ contactId, key: stage.key, version: stage.version, changedAt: stage.changed_at || null, reason: stage.reason || null });
    }
    const label = stage?.label || stageLabel(catalog, stage?.key) || "a nova etapa";
    setNotice({ contactId, tone: "success", version: stage?.version, text: `Etapa alterada para ${label}. Nenhuma mensagem foi enviada.` });
  }

  const title = <div className="fn-stage-card-heading">
    <strong id={`${id}-title`}>Etapa do funil</strong>
    {stageDef && !stageDef.active && <span className="fn-badge fn-badge--neutral">Etapa inativa</span>}
  </div>;
  const closeWithFunnel = closeOutcomeStages(catalog).length > 0;
  const subtitle = <p className="fn-help" id={`${id}-subtitle`}>Classificação comercial do paciente{closeWithFunnel ? ". O desfecho do encerramento do atendimento vira a etapa" : ""}.</p>;

  if (!catalog) {
    return <section className="fn-stage-card" aria-labelledby={`${id}-title`} aria-describedby={`${id}-subtitle`}>
      {title}{subtitle}
      {configError
        ? <div className="fn-inline"><p className="fn-warning-text" role="alert">{configError}</p><button type="button" className="fn-button" onClick={reload}>Tentar novamente</button></div>
        : <p className="fn-help" role="status">{loading ? "Consultando o funil…" : "Funil indisponível no momento."}</p>}
    </section>;
  }

  const days = elapsedDays(changedAt);
  const description = stageDef?.description || "";
  return <section className="fn-stage-card" aria-labelledby={`${id}-title`} aria-describedby={`${id}-subtitle`}>
    {title}{subtitle}
    {stageKey ? <>
      <p className="fn-stage-line">
        <span className={`fn-stage-pill fn-kind-bg--${stageDef?.kind || "excluded"}`}>{stageDef?.label || "Etapa fora do catálogo atual"}</span>
        <span title={changedAt ? `Na etapa desde ${formatDateTime(changedAt)}` : undefined}>{daysInStageText(days)}</span>
        {description && <InfoButton expanded={infoOpen} controls={`${id}-info`} subject={stageDef?.label || ""} onToggle={() => setInfoFor((value) => (value === contactId ? null : contactId))} />}
      </p>
      {description && <p id={`${id}-info`} className="fn-help fn-stage-info" hidden={!infoOpen}>{description}</p>}
      {reason && <p>Motivo: {reason.label}</p>}
    </> : <p><strong>Fora do funil</strong></p>}
    {shownNotice && <p className={`fn-notice fn-notice--${shownNotice.tone}`} role="status">{shownNotice.text}</p>}
    <div className="fn-inline">
      {canMove && <button type="button" className="fn-button" ref={moveRef} onClick={(event) => { setNotice(null); setDialog({ contactId, trigger: event.currentTarget }); }}>{stageKey ? "Mover para…" : "Incluir no funil"}</button>}
      {historyAllowed && <button type="button" className="fn-button" aria-expanded={historyOpen} aria-controls={`${id}-history`} onClick={() => setHistoryFor((value) => (value === contactId ? null : contactId))}>{historyOpen ? "Ocultar histórico" : "Ver histórico"}</button>}
    </div>
    {!canMove && (unavailable
      ? <p className="fn-help">{contact.is_backup ? "Contato em backup" : "Contato arquivado"}: a etapa não muda por aqui.</p>
      : capabilities?.can_move && !writeScope ? <p className="fn-help">Você pode consultar a etapa, mas só move contatos seus ou sem dono.</p> : null)}
    {historyAllowed && <div id={`${id}-history`} hidden={!historyOpen}>
      {historyOpen && <StageHistory items={history.items} nextCursor={history.cursor} busy={history.busy} error={history.error} onMore={moreHistory} />}
    </div>}
    {dialog && dialog.contactId === contactId && auth && <MoveStageDialog
      auth={auth} catalog={catalog} contactId={contactId} contactName={contact.display_name || `Contato #${contactId}`}
      currentStage={stageKey} currentReason={reason?.key || null}
      // "Incluir no funil" parte da versao 0 (contato sem etapa); 409 traz o atual.
      expectedVersion={stageKey ? version : 0}
      returnFocus={() => moveRef.current || (dialog.trigger?.isConnected ? dialog.trigger : null)}
      onClose={() => setDialog(null)}
      onMoved={moved}
      onConflict={(current) => {
        // Etapa atual do servidor (quem mudou primeiro): o cartao acompanha
        // mesmo sem listener para este contato.
        setLocal({ contactId, key: current.stage, version: current.version, changedAt: current.changed_at, reason: null });
      }}
      onAccessLost={(error) => {
        setDialog(null);
        setNotice({ contactId, tone: "warning", text: funnelErrorMessage(error) });
      }} />}
  </section>;
}
