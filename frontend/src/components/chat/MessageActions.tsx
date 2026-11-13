import { useEffect, useRef, useState } from "react";
import { useCrm } from "../../context/CrmContext";
import { deleteJson, getJson, sendJson } from "../../api";
import { errorText } from "../../utils/errors";
import { normalizeMessage } from "../../utils/normalization";
import { messageContentLabel } from "../../utils/formatting";
import { waPlainText } from "../../utils/waFormat";
import type { ChatMessage, PickerRow, PinnedMessage } from "../../types";
import { useClickOutside } from "../../hooks/useClickOutside";

export function ForwardIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m13 4 7 7-7 7M4 20v-4a5 5 0 0 1 5-5h11M17 3l7 8-7 8" /></svg>;
}

export function PinIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M8 3h8l-1 7 3 4H6l3-4-1-7ZM12 14v8" /></svg>;
}

export function canForwardMessage(message: ChatMessage) {
  if (!["inbound", "outbound"].includes(message.direction) || (message.visibility && message.visibility !== "all")) return false;
  if (["text", "template"].includes(message.msg_type)) return !!message.content?.trim();
  if (message.msg_type === "location") return message.latitude != null && message.longitude != null;
  return ["image", "audio", "video", "gif", "document", "sticker"].includes(message.msg_type) && !!message.media_path;
}

type Destination = { key: string; contactId: number; name: string; detail: string; conversationId?: string; channelId?: number | null };

export function ForwardPicker({ messageIds, onSent, onClose }: {
  messageIds: number[]; onSent: (ids: number[]) => void; onClose: () => void;
}) {
  const ctx = useCrm();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PickerRow[]>([]);
  const [searching, setSearching] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [destination, setDestination] = useState<Destination | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sending = useRef(false);
  const mounted = useRef(true);
  const searchRef = useRef(ctx.pickerSearch);
  searchRef.current = ctx.pickerSearch;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let active = true;
    setResults([]); setTruncated(false);
    if (query.trim().length < 2) { setSearching(false); return; }
    setSearching(true);
    const timer = window.setTimeout(() => {
      void searchRef.current(query.trim()).then((res) => {
        if (active) { setResults(res.contacts); setTruncated(res.truncated); }
      }).catch((e) => { if (active) setError(errorText(e)); }).finally(() => { if (active) setSearching(false); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query]);
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape" && !sending.current) onClose(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onClose]);

  const term = query.trim().toLocaleLowerCase();
  const conversations = (term ? ctx.conversations : ctx.meusConversations)
    .filter((c) => !c.is_backup && c.channel_active !== false)
    .filter((c) => !term || `${ctx.contactsById.get(c.contact_id)?.display_name || c.display_name} ${c.phone_formatted || c.wa_id}`.toLocaleLowerCase().includes(term))
    .sort((a, b) => Number(b.assigned_to === ctx.sessionUser?.id) - Number(a.assigned_to === ctx.sessionUser?.id)
      || (b.last_message_at || "").localeCompare(a.last_message_at || ""));
  const choices: Destination[] = conversations.map((c) => ({
    key: c.id, contactId: c.contact_id, conversationId: c.id,
    name: ctx.contactsById.get(c.contact_id)?.display_name || c.display_name || c.wa_id,
    detail: [c.channel_label, c.channel_phone_number, c.assigned_to === ctx.sessionUser?.id ? "Meu atendimento" : ""].filter(Boolean).join(" · "),
  }));
  const known = new Set(choices.map((c) => c.contactId));
  results.filter((c) => !known.has(c.id)).forEach((c) => choices.push({
    key: `contact-${c.id}`, contactId: c.id, channelId: c.channel_id, name: c.display_name, detail: c.phone_formatted,
  }));

  async function forward() {
    if (!destination || !ctx.bundle || ctx.readOnly || sending.current) return;
    sending.current = true; setBusy(true); setError("");
    const sent: number[] = [];
    try {
      let threadId = destination.conversationId;
      if (!threadId) {
        const opened = await sendJson<{ conversation_id: string }>(ctx.bundle.auth, "/api/wa/conversation/open", {
          contact_id: destination.contactId, ...(destination.channelId ? { channel_id: destination.channelId } : {}),
        });
        threadId = opened.conversation_id;
      }
      for (const id of messageIds) {
        if (!mounted.current) break;
        await sendJson(ctx.bundle.auth, "/api/wa/send", { conversation_id: threadId, forward_message_id: id });
        sent.push(id);
      }
      if (mounted.current && sent.length === messageIds.length) {
        ctx.setNotice(`${sent.length} mensagem${sent.length === 1 ? " encaminhada" : "s encaminhadas"} para ${destination.name}.`);
        onSent(sent); onClose();
      }
    } catch (e) {
      if (mounted.current) {
        onSent(sent);
        setError(`${sent.length ? `${sent.length} enviada(s). As restantes continuam selecionadas. ` : ""}${errorText(e)}`);
      }
    } finally { sending.current = false; if (mounted.current) setBusy(false); }
  }

  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}>
    <section className="modal forward-picker" role="dialog" aria-modal="true" aria-labelledby="forward-title" onClick={(e) => e.stopPropagation()}>
      <div className="row"><h2 id="forward-title">Encaminhar {messageIds.length} mensagem{messageIds.length === 1 ? "" : "s"}</h2><button type="button" className="ghost" onClick={onClose} disabled={busy} aria-label="Fechar">×</button></div>
      <input autoFocus value={query} onChange={(e) => { setQuery(e.target.value); setError(""); }} disabled={busy} placeholder="Buscar contato por nome ou telefone" aria-label="Buscar destino" />
      <p className="sub">{term ? "Resultados · seus atendimentos primeiro" : "Seus atendimentos"}</p>
      <div className="forward-picker-list" aria-busy={searching}>
        {choices.map((choice) => <button type="button" key={choice.key} className={`forward-destination ${destination?.key === choice.key ? "selected" : ""}`} disabled={busy} aria-pressed={destination?.key === choice.key} onClick={() => setDestination(choice)}><strong>{choice.name}</strong><span className="sub">{choice.detail}</span></button>)}
        {searching && <p role="status">Buscando…</p>}
        {!choices.length && !searching && <p className="sub">{term.length >= 2 ? "Nenhum contato encontrado." : "Busque um contato para escolher o destino."}</p>}
        {truncated && <p className="sub">Há mais resultados. Refine a busca.</p>}
        {!term && ctx.canLoadMoreMine && <button type="button" className="ghost" disabled={busy || ctx.loadingMoreConvs} onClick={() => void ctx.loadMoreMyConversations()}>Buscar atendimentos mais antigos</button>}
      </div>
      {error && <div className="alert danger" role="alert">{error}</div>}
      <div className="row"><span className="sub">{destination ? `Para: ${destination.name}` : "Selecione o destino"}</span><button type="button" className="primary" disabled={!destination || busy || ctx.readOnly || !messageIds.length} onClick={() => void forward()}>{busy ? "Encaminhando…" : "Encaminhar"}</button></div>
    </section>
  </div>;
}

export function PinDurationDialog({ busy, onPin, onClose }: { busy: boolean; onPin: (days: 1 | 7 | 30) => void; onClose: () => void }) {
  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}><section className="modal pin-dialog" role="dialog" aria-modal="true" aria-labelledby="pin-title" onClick={(e) => e.stopPropagation()}>
    <h2 id="pin-title">Fixar mensagem por quanto tempo?</h2><p className="sub">A mensagem ficará em destaque nesta conversa para a equipe. Uma nova fixação substitui a anterior.</p>
    <div className="pin-durations">{([1, 7, 30] as const).map((days) => <button type="button" className="ghost" key={days} disabled={busy} onClick={() => onPin(days)}>{days === 1 ? "24 horas" : `${days} dias`}</button>)}</div>
    <button type="button" className="ghost" onClick={onClose} disabled={busy}>Cancelar</button>
  </section></div>;
}

export function useMessageActions() {
  const ctx = useCrm();
  const thread = ctx.selectedThreadId;
  const threadRef = useRef(thread);
  threadRef.current = thread;
  const [selection, setSelection] = useState<Map<number, ChatMessage> | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [pinTarget, setPinTarget] = useState<ChatMessage | null>(null);
  const [pin, setPin] = useState<PinnedMessage | null>(ctx.selectedConversation?.pinned_message || null);
  const [pinMenu, setPinMenu] = useState(false);
  const [busyPin, setBusyPin] = useState(false);
  const [historicalMessages, setHistoricalMessages] = useState<ChatMessage[] | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [loadingPin, setLoadingPin] = useState(false);
  const pendingJump = useRef<number | null>(null);
  const mutating = useRef(false);
  const pinMenuRef = useRef<HTMLDivElement | null>(null);
  useClickOutside(pinMenuRef, pinMenu, () => setPinMenu(false));
  const pinVersion = JSON.stringify(ctx.selectedConversation?.pinned_message || null);
  useEffect(() => { setPin(ctx.selectedConversation?.pinned_message || null); }, [thread, pinVersion]);
  useEffect(() => {
    setSelection(null); setShowPicker(false); setPinTarget(null); setPinMenu(false);
    setHistoricalMessages(null); setHighlight(null); setLoadingPin(false); pendingJump.current = null;
  }, [thread]);
  useEffect(() => {
    if (!pin) return;
    let timer: number;
    const expire = () => {
      const remaining = new Date(pin.expires_at).getTime() - Date.now();
      if (!Number.isFinite(remaining) || remaining <= 0) setPin(null);
      else timer = window.setTimeout(expire, Math.min(remaining, 2_147_483_647));
    };
    expire();
    return () => window.clearTimeout(timer);
  }, [pin]);
  useEffect(() => {
    if (!highlight) return;
    const timer = window.setTimeout(() => setHighlight(null), 2500);
    return () => window.clearTimeout(timer);
  }, [highlight]);
  useEffect(() => {
    if (!pendingJump.current) return;
    const id = pendingJump.current;
    const frame = requestAnimationFrame(() => {
      const node = ctx.messagesRef.current?.querySelector<HTMLElement>(`[data-message-id="${id}"]`);
      if (node) { node.scrollIntoView({ block: "center", behavior: "smooth" }); setHighlight(id); pendingJump.current = null; }
    });
    return () => cancelAnimationFrame(frame);
  }, [historicalMessages, ctx.chatSearch, ctx.messages]);

  async function jump() {
    if (!pin || !ctx.bundle || loadingPin) return;
    setPinMenu(false); ctx.setChatSearch("");
    const id = pin.message_id;
    pendingJump.current = id;
    const node = ctx.messagesRef.current?.querySelector<HTMLElement>(`[data-message-id="${id}"]`);
    if (node) { node.scrollIntoView({ block: "center", behavior: "smooth" }); setHighlight(id); pendingJump.current = null; return; }
    if (ctx.readOnly) { ctx.setNotice("Carregue as mensagens anteriores para acessar esta fixada no modo de visualização."); pendingJump.current = null; return; }
    setLoadingPin(true);
    const startedThread = thread;
    try {
      const res = await getJson<{ messages: Record<string, unknown>[] }>(ctx.bundle.auth, `/api/wa/messages/${id}/context`);
      if (threadRef.current !== startedThread) return;
      setHistoricalMessages(res.messages.map((m) => normalizeMessage(m, String(m.id))));
    } catch (e) { if (threadRef.current === startedThread) ctx.setError(errorText(e)); }
    finally { if (threadRef.current === startedThread) setLoadingPin(false); }
  }
  async function savePin(days: 1 | 7 | 30) {
    if (!ctx.bundle || !pinTarget || ctx.readOnly || mutating.current) return;
    const startedThread = thread;
    mutating.current = true; setBusyPin(true);
    try {
      const res = await sendJson<{ pinned_message: PinnedMessage }>(ctx.bundle.auth, `/api/wa/messages/${pinTarget.id}/pin`, { duration_days: days });
      if (threadRef.current === startedThread) { setPin(res.pinned_message); setPinTarget(null); }
    } catch (e) { if (threadRef.current === startedThread) ctx.setError(errorText(e)); }
    finally { mutating.current = false; setBusyPin(false); }
  }
  async function unpin() {
    if (!ctx.bundle || !thread || ctx.readOnly || mutating.current) return;
    const startedThread = thread;
    mutating.current = true; setBusyPin(true);
    try {
      await deleteJson(ctx.bundle.auth, `/api/wa/conversation/${encodeURIComponent(thread)}/pin`);
      if (threadRef.current === startedThread) { setPin(null); setPinMenu(false); }
    } catch (e) { if (threadRef.current === startedThread) ctx.setError(errorText(e)); }
    finally { mutating.current = false; setBusyPin(false); }
  }
  function toggleSelection(message: ChatMessage) {
    setSelection((prev) => {
      const next = new Map(prev);
      if (next.has(message.id)) next.delete(message.id); else next.set(message.id, message);
      return next;
    });
  }
  const selectedIds = [...(selection?.values() || [])]
    .sort((a, b) => (a.timestamp_wa || a.created_at || "").localeCompare(b.timestamp_wa || b.created_at || "") || a.id - b.id).map((m) => m.id);
  return {
    selection, toggleSelection, historicalMessages, highlight,
    startForward(message: ChatMessage) { if (!ctx.readOnly) setSelection(new Map([[message.id, message]])); },
    startPin(message: ChatMessage) { if (!ctx.readOnly) setPinTarget(message); },
    pinBar: pin ? <div className="pinned-message-bar">
      <button type="button" className="pinned-message-preview" onClick={() => void jump()} disabled={loadingPin} title={`Fixada até ${new Date(pin.expires_at).toLocaleString("pt-BR")}`}><PinIcon /><span>{loadingPin ? "Buscando mensagem…" : waPlainText(pin.preview)}</span></button>
      <div className="pinned-message-options" ref={pinMenuRef}><button type="button" className="ghost" aria-label="Opções da mensagem fixada" aria-expanded={pinMenu} onClick={() => setPinMenu((v) => !v)}>⌄</button>
        {pinMenu && <div className="attach-menu"><button type="button" className="attach-option" onClick={() => void jump()}>Ir para a mensagem</button><button type="button" className="attach-option" disabled={ctx.readOnly || busyPin} onClick={() => void unpin()}>Desfixar mensagem</button></div>}
      </div></div> : null,
    historyBar: historicalMessages ? <div className="message-history-bar"><span>Trecho da mensagem fixada</span><button type="button" className="ghost" onClick={() => { setHistoricalMessages(null); pendingJump.current = null; ctx.scrollIntentRef.current = "normal"; requestAnimationFrame(() => { const node = ctx.messagesRef.current; if (node) node.scrollTop = node.scrollHeight; }); }}>Voltar às recentes</button></div> : null,
    selectionBar: selection ? <div className="message-selection-bar" role="region" aria-label="Encaminhar mensagens"><button type="button" className="ghost" aria-label="Cancelar seleção" onClick={() => { setSelection(null); setShowPicker(false); }}>×</button><span aria-live="polite">{selection.size} selecionada{selection.size === 1 ? "" : "s"}</span><button type="button" className="ghost" disabled={!selection.size || ctx.readOnly} onClick={() => setShowPicker(true)} aria-label="Escolher destino do encaminhamento"><ForwardIcon /></button></div> : null,
    dialogs: <>{showPicker && selection && <ForwardPicker key={thread} messageIds={selectedIds} onClose={() => setShowPicker(false)} onSent={(ids) => setSelection((prev) => { const next = new Map(prev); ids.forEach((id) => next.delete(id)); return next.size ? next : null; })} />}{pinTarget && <PinDurationDialog busy={busyPin} onPin={(days) => void savePin(days)} onClose={() => setPinTarget(null)} />}</>,
    selectionLabel(message: ChatMessage) { return `Selecionar mensagem: ${messageContentLabel(message).slice(0, 80) || message.msg_type}`; },
  };
}
