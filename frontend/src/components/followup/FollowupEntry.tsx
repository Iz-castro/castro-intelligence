import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useCrm } from "../../context/CrmContext";
import type { Contact } from "../../types";
import { FollowupPanel } from "../../features/followup";
import { loadTasks } from "../../features/followup/api";
import { formatMoment } from "../../features/followup/time";
import type { FollowupTask } from "../../features/followup/types";
import { requestError } from "../../features/followup/useOperation";

export function CommercialContactBanner({ contact }: { contact: Contact }) {
  if (!contact.commercial_contact_block?.active) return null;
  return <div className="followup-commercial-banner" role="status"><strong>Não realizar novas retomadas comerciais.</strong><span>Pedido do paciente registrado. Consultas marcadas e tarefas independentes permanecem. Uma mensagem nova não remove esta preferência.</span></div>;
}

export function FollowupEntry({ contactId, variant = "topbar" }: { contactId?: number; variant?: "topbar" | "contact" }) {
  const { bundle, config, can, canSeeAll } = useCrm();
  const [open, setOpen] = useState(false);
  const [next, setNext] = useState<FollowupTask | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const enabled = Boolean(config?.feature_followup && can("gerenciar_followup"));
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!enabled) setOpen(false);
    if (!enabled || !bundle || !contactId || open) return;
    let cancelled = false;
    setLoading(true); setError(""); setNext(null);
    void loadTasks(bundle.auth, { contact_id: contactId, group: "all" }).then((page) => {
      if (!cancelled) { setNext(page.items[0] || null); setHasMore(Boolean(page.next_cursor)); }
    }).catch((reason) => { if (!cancelled) setError(requestError(reason)); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [enabled, bundle, contactId, open, refresh]);

  if (!enabled) return null;
  function close() { setOpen(false); setRefresh((value) => value + 1); trigger.current?.focus(); }
  const panel = open ? createPortal(<FollowupPanel contactId={contactId} onClose={close} canManageSettings={can("gerenciar_horarios_followup")} canManageTeam={canSeeAll && can("redistribuir_followup")} />, document.body) : null;

  return <>
    {variant === "topbar" ? <button type="button" className="composer-icon" ref={trigger} onClick={() => setOpen(true)} title="Follow-up" aria-label="Abrir fila de follow-up"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18m-13 5 2 2 5-5" /></svg></button> : <section className="followup-contact-card" aria-label="Próxima ação do contato"><div className="followup-contact-card-heading"><strong>Próxima ação</strong><button type="button" ref={trigger} className="ghost" onClick={() => setOpen(true)}>Follow-up</button></div>{loading ? <p className="sub" role="status">Consultando pendências…</p> : error ? <div><p className="sub" role="alert">{error}</p><button type="button" className="ghost" onClick={() => setRefresh((value) => value + 1)}>Tentar novamente</button></div> : next ? <><p>{next.title}</p><p className="sub">{formatMoment(next.due_at)}</p>{next.response_received && <p className="followup-contact-response">{next.response_label || "Paciente respondeu após a referência da tarefa"}</p>}</> : <p className="sub">{hasMore ? "Consulte as próximas pendências no painel." : "Nenhuma tarefa pendente acessível."}</p>}<button type="button" className="ghost" onClick={() => setOpen(true)}>Ver tarefas / combinar retorno</button></section>}
    {panel}
  </>;
}
