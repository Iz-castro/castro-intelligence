import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useCrm } from "../../context/CrmContext";
import { deleteJson, getJson, sendJson } from "../../api";
import { errorText } from "../../utils/errors";
import { normalizeMessage } from "../../utils/normalization";
import { messageContentLabel } from "../../utils/formatting";
import { waPlainText } from "../../utils/waFormat";
import type { Channel, ChatMessage, Contact, Conversation, PickerRow, PinnedMessage, SessionUser } from "../../types";
import { useClickOutside } from "../../hooks/useClickOutside";

export function ForwardIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m13 4 7 7-7 7M4 20v-4a5 5 0 0 1 5-5h11M17 3l7 8-7 8" /></svg>;
}

export function PinIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M8 3h8l-1 7 3 4H6l3-4-1-7ZM12 14v8" /></svg>;
}

const MEDIA_KINDS = ["image", "audio", "video", "gif", "document", "sticker"];

// Fixar: qualquer bolha com conteudo do cliente/equipe (inclui template).
export function canPinMessage(message: ChatMessage) {
  if (!["inbound", "outbound"].includes(message.direction) || (message.visibility && message.visibility !== "all")) return false;
  if (["text", "template"].includes(message.msg_type)) return !!message.content?.trim();
  if (message.msg_type === "location") return message.latitude != null && message.longitude != null;
  return MEDIA_KINDS.includes(message.msg_type) && !!message.media_path;
}

// Encaminhar: so conteudo real. Template guarda o rotulo interno com dados de
// quem recebeu ('[template: nome] params'); toque em botao guarda o id do botao;
// clique de avaliacao e controle. O backend recusa os mesmos casos.
export function canForwardMessage(message: ChatMessage) {
  if (message.msg_type === "template" || message.interactive_reply || message.is_rating_message) return false;
  return canPinMessage(message);
}

// Espelha a origem ESTRITA do backend (_require_transfer_source_access): thread
// que atendo ou pool de verdade (thread e lead sem dono, ou lead meu). Gestao
// com ver_todos_leads age em qualquer thread. A thread coex de outra vendedora
// aberta pelo Dono do Lead fica de fora.
export function canActOnThread(conversation: Conversation | null | undefined, contact: Contact | null | undefined,
  sessionUser: SessionUser | null | undefined, canSeeAll: boolean | undefined) {
  if (canSeeAll) return true;
  if (!conversation || !sessionUser || conversation.is_backup) return false;
  if (conversation.assigned_to === sessionUser.id) return true;
  if (conversation.assigned_to_uid && conversation.assigned_to_uid === sessionUser.firebase_uid) return true;
  if (!conversation.assigned_to && !conversation.assigned_to_uid) {
    const leadOwner = contact?.assigned_to;
    return !leadOwner || leadOwner === sessionUser.id;
  }
  return false;
}

function channelText(channel: Channel) {
  const kind = channel.channel_type === "standard" ? "número da empresa" : "seu número";
  return [channel.label || kind, channel.display_phone_number].filter(Boolean).join(" · ");
}

// Thread so e destino se nao sair pelo coex de outra pessoa (o backend recusa).
function threadChannelAllowed(conversation: Conversation, channelsById: Map<number, Channel>, sessionUser: SessionUser | null | undefined) {
  const channel = conversation.channel_id != null ? channelsById.get(conversation.channel_id) : undefined;
  const type = channel?.channel_type || conversation.channel_type || conversation.source_channel_type;
  if (type !== "coexistence") return true;
  return !!channel && channel.owner_user_id === sessionUser?.id;
}

function activeElement(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  const el = document.activeElement as HTMLElement | null;
  return el && typeof el.focus === "function" ? el : null;
}

// Atalho de guias (Ctrl+Alt+Seta, useChatTabs) bloqueado enquanto um dialogo
// estiver aberto — na CAPTURA do window, porque com o botao "Encaminhando…"
// disabled o foco vai para o body e o lote seria interrompido pela troca.
function useBlockChatTabShortcut() {
  useEffect(() => {
    const block = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && (event.key === "ArrowDown" || event.key === "ArrowUp")) event.preventDefault();
    };
    window.addEventListener("keydown", block, true);
    return () => window.removeEventListener("keydown", block, true);
  }, []);
}

// Foco volta ao gatilho ao fechar. Capturado no 1o RENDER: o autoFocus do
// dialogo roda no commit, antes de qualquer useEffect.
function useReturnFocus(fallbackSelector?: string) {
  const [previous] = useState(() => activeElement());
  const fallbackRef = useRef(fallbackSelector);
  fallbackRef.current = fallbackSelector;
  useEffect(() => () => {
    if (previous?.isConnected) { previous.focus(); return; }
    const selector = fallbackRef.current;
    if (selector && typeof document !== "undefined") document.querySelector<HTMLElement>(selector)?.focus();
  }, []);
}

// Tab circula dentro do modal.
function dialogKeyDown(event: ReactKeyboardEvent<HTMLElement>, container: HTMLElement | null) {
  if (event.key !== "Tab" || !container) return;
  const focusable = Array.from(container.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = activeElement();
  if (event.shiftKey && current === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && current === last) { event.preventDefault(); first.focus(); }
}

type Destination = {
  key: string; contactId: number; name: string; detail: string;
  conversationId?: string; channelId?: number | null; disabled?: boolean;
};

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
  const dialogRef = useRef<HTMLElement | null>(null);
  const searchRef = useRef(ctx.pickerSearch);
  searchRef.current = ctx.pickerSearch;
  useReturnFocus();
  useBlockChatTabShortcut();
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  // Lista de canais vazia = /api/admin/channels falhou na carga da sessao (o
  // CrmContext cai em []): busca de novo aqui. Sem ela o coex proprio sumia e o
  // contato da busca voltava a abrir pelo canal de criacao (coex de colega).
  const sessionChannels = ctx.channels || [];
  const [fetchedChannels, setFetchedChannels] = useState<Channel[] | null>(null);
  const [channelsFailed, setChannelsFailed] = useState(false);
  useEffect(() => {
    if (sessionChannels.length || !ctx.bundle) return undefined;
    let active = true;
    getJson<{ channels: Channel[] }>(ctx.bundle.auth, "/api/admin/channels")
      .then((res) => { if (active) setFetchedChannels(res.channels || []); })
      .catch(() => { if (active) setChannelsFailed(true); });
    return () => { active = false; };
  }, []);
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

  const me = ctx.sessionUser;
  const knownChannels = sessionChannels.length ? sessionChannels : fetchedChannels;
  const channels = knownChannels || [];
  const channelsById = new Map(channels.map((ch) => [ch.id, ch] as const));
  // Numeros de saida possiveis: os da empresa e o coex do proprio usuario.
  const allowedChannels = channels.filter((ch) => ch.is_active !== false && (ch.channel_type === "standard" || ch.owner_user_id === me?.id));
  const term = query.trim().toLocaleLowerCase();
  const searchable = term.length >= 2;
  // Mesmo universo das caixas: proprios (inclui paginados/guias) e, com busca,
  // a pool visivel (Novos) e as caixas da gestao. Nunca a camada crua do
  // listener: thread orfa de lead alheio mostraria o telefone (revisao PR #8).
  const own = ctx.meusConversations || [];
  const wider = searchable ? [
    ...(ctx.novosConversations || []),
    ...(ctx.canSeeAll ? [...(ctx.equipeConversations || []), ...(ctx.botConversations || []), ...(ctx.nqConversations || [])] : []),
  ] : [];
  const seenThreads = new Set<string>();
  const rows: { c: Conversation; mine: boolean; name: string }[] = [];
  for (const [list, mine] of [[own, true], [wider, false]] as const) {
    for (const c of list) {
      if (seenThreads.has(c.id) || c.is_backup || c.channel_active === false) continue;
      seenThreads.add(c.id);
      const contact = ctx.contactsById.get(c.contact_id);
      if (!mine && !contact) continue;
      if (!threadChannelAllowed(c, channelsById, me)) continue;
      const name = contact?.display_name || contact?.phone_formatted || c.display_name || c.phone_formatted || (mine ? c.wa_id : "") || "Contato";
      const phone = contact?.phone_formatted || c.phone_formatted || "";
      if (term && !`${name} ${phone}`.toLocaleLowerCase().includes(term)) continue;
      rows.push({ c, mine: mine || c.assigned_to === me?.id, name });
    }
  }
  rows.sort((a, b) => Number(b.mine) - Number(a.mine) || (b.c.last_message_at || "").localeCompare(a.c.last_message_at || ""));
  const choices: Destination[] = rows.map(({ c, mine, name }) => {
    const channel = c.channel_id != null ? channelsById.get(c.channel_id) : undefined;
    const via = channel ? channelText(channel) : [c.channel_label, c.channel_phone_number].filter(Boolean).join(" · ");
    return { key: c.id, contactId: c.contact_id, conversationId: c.id, name, detail: [via, mine ? "Meu atendimento" : ""].filter(Boolean).join(" · ") };
  });
  const known = new Set(choices.map((c) => c.contactId));
  if (searchable) {
    for (const row of results) {
      if (known.has(row.id)) continue;
      // Contato sem thread na tela: o canal de CRIACAO pode ser o coex de outra
      // vendedora — so vale se for numero permitido; senao sai pelo da empresa.
      // Canais ainda desconhecidos: linha desabilitada (nunca cai no canal de criacao).
      const channel = allowedChannels.find((ch) => ch.id === row.channel_id)
        || allowedChannels.find((ch) => ch.channel_type === "standard") || null;
      const reason = knownChannels ? "Sem número da empresa disponível" : channelsFailed ? "Números indisponíveis" : "Carregando números…";
      choices.push({
        key: `contact-${row.id}`, contactId: row.id,
        channelId: channel ? channel.id : null,
        name: row.display_name || row.phone_formatted || "Contato",
        detail: [row.phone_formatted, channel ? `Sai por ${channelText(channel)}` : reason].filter(Boolean).join(" · "),
        disabled: !channel,
      });
    }
  }

  async function forward() {
    if (!destination || destination.disabled || !ctx.bundle || ctx.readOnly || sending.current) return;
    sending.current = true; setBusy(true); setError("");
    const sent: number[] = [];
    const total = messageIds.length;
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
      if (sent.length === total) {
        ctx.setNotice(`${sent.length} mensagem${sent.length === 1 ? " encaminhada" : "s encaminhadas"} para ${destination.name}.`);
        if (mounted.current) { onSent(sent); onClose(); }
      } else if (!mounted.current) {
        // Troca de conversa/guia no meio do lote: antes sumia sem aviso.
        ctx.setNotice(`Encaminhamento interrompido ao trocar de conversa: ${sent.length} de ${total} enviada(s).`);
      }
    } catch (e) {
      if (mounted.current) {
        onSent(sent);
        setError(`${sent.length ? `${sent.length} enviada(s). As restantes continuam selecionadas. ` : ""}${errorText(e)}`);
      } else {
        ctx.setNotice(`Encaminhamento interrompido: ${sent.length} de ${total} enviada(s). ${errorText(e)}`);
      }
    } finally { sending.current = false; if (mounted.current) setBusy(false); }
  }

  const sourceName = ctx.selectedContact?.display_name || ctx.selectedContact?.phone_formatted || "";
  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}>
    <section ref={dialogRef} className="modal forward-picker" role="dialog" aria-modal="true" aria-labelledby="forward-title" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => dialogKeyDown(e, dialogRef.current)}>
      <div className="row"><h2 id="forward-title">Encaminhar {messageIds.length} mensagem{messageIds.length === 1 ? "" : "s"}</h2><button type="button" className="ghost" onClick={onClose} disabled={busy} aria-label="Fechar">×</button></div>
      <input autoFocus value={query} onChange={(e) => { setQuery(e.target.value); setError(""); }} disabled={busy} placeholder="Buscar contato por nome ou telefone" aria-label="Buscar destino" />
      <p className="sub">{searchable ? "Resultados · seus atendimentos primeiro" : "Seus atendimentos"}</p>
      <div className="forward-picker-list" aria-busy={searching}>
        {choices.map((choice) => <button type="button" key={choice.key} className={`forward-destination ${destination?.key === choice.key ? "selected" : ""}`} disabled={busy || choice.disabled} aria-pressed={destination?.key === choice.key} onClick={() => setDestination(choice)}><strong>{choice.name}</strong><span className="sub">{choice.detail}</span></button>)}
        {searching && <p role="status">Buscando…</p>}
        {!choices.length && !searching && <p className="sub">{searchable ? "Nenhum contato encontrado." : "Busque um contato para escolher o destino."}</p>}
        {truncated && <p className="sub">Há mais resultados. Refine a busca.</p>}
        {channelsFailed && !knownChannels && <p className="sub">Não foi possível carregar os números: conversas pelo seu número pessoal não aparecem agora.</p>}
        {!term && ctx.canLoadMoreMine && <button type="button" className="ghost" disabled={busy || ctx.loadingMoreConvs} onClick={() => void ctx.loadMoreMyConversations()}>Buscar atendimentos mais antigos</button>}
      </div>
      {error && <div className="alert danger" role="alert">{error}</div>}
      <div className="row">
        <span className="sub forward-route">{destination ? `${sourceName ? `De: ${sourceName} → ` : ""}Para: ${destination.name}` : "Selecione o destino"}</span>
        <button type="button" className="primary" disabled={!destination || destination.disabled || busy || ctx.readOnly || !messageIds.length} onClick={() => void forward()}>{busy ? "Encaminhando…" : "Encaminhar"}</button>
      </div>
    </section>
  </div>;
}

export function PinDurationDialog({ busy, error = "", returnFocusSelector, onPin, onClose }: {
  busy: boolean; error?: string; returnFocusSelector?: string; onPin: (days: 1 | 7 | 30) => void; onClose: () => void;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // Aberto pelo menu da bolha, o gatilho ("Fixar") desmonta junto com o menu:
  // o foco volta ao botao de acoes daquela bolha.
  useReturnFocus(returnFocusSelector);
  useBlockChatTabShortcut();
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape" && !busyRef.current) closeRef.current(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  return <div className="modal-backdrop" onClick={() => { if (!busy) onClose(); }}><section ref={dialogRef} className="modal pin-dialog" role="dialog" aria-modal="true" aria-labelledby="pin-title" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => dialogKeyDown(e, dialogRef.current)}>
    <h2 id="pin-title">Fixar mensagem por quanto tempo?</h2><p className="sub">A mensagem fica em destaque nesta conversa só para a equipe (o cliente não é avisado). Uma nova fixação substitui a anterior.</p>
    <div className="pin-durations">{([1, 7, 30] as const).map((days) => <button type="button" className="ghost" key={days} autoFocus={days === 1} disabled={busy} onClick={() => onPin(days)}>{days === 1 ? "24 horas" : `${days} dias`}</button>)}</div>
    {error && <div className="alert danger" role="alert">{error}</div>}
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
  const [pinError, setPinError] = useState("");
  const [pin, setPin] = useState<PinnedMessage | null>(ctx.selectedConversation?.pinned_message || null);
  const [pinMenu, setPinMenu] = useState(false);
  const [busyPin, setBusyPin] = useState(false);
  const [historicalMessages, setHistoricalMessages] = useState<ChatMessage[] | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [loadingPin, setLoadingPin] = useState(false);
  const pendingJump = useRef<number | null>(null);
  const mutating = useRef(false);
  const pinMenuRef = useRef<HTMLDivElement | null>(null);
  // Recencia da THREAD (doc da conversa, listener proprio) quando o trecho da
  // fixada abriu: mudou (cliente respondeu, operador enviou) => volta as
  // recentes. Nao usa o fim de ctx.messages: as mensagens sao por contato, o
  // 1o snapshot pode chegar depois do /context e cliques admin_only entram no
  // array sem aparecer (revisao das correcoes).
  const lastActivity = ctx.selectedConversation?.last_message_at || "";
  const lastActivityRef = useRef(lastActivity);
  lastActivityRef.current = lastActivity;
  const excerptArmed = useRef(false);
  const excerptBaseline = useRef("");
  const canAct = canActOnThread(ctx.selectedConversation, ctx.selectedContact, ctx.sessionUser, ctx.canSeeAll);
  useClickOutside(pinMenuRef, pinMenu, () => setPinMenu(false));
  const pinVersion = JSON.stringify(ctx.selectedConversation?.pinned_message || null);
  useEffect(() => { setPin(ctx.selectedConversation?.pinned_message || null); }, [thread, pinVersion]);
  useEffect(() => {
    setSelection(null); setShowPicker(false); setPinTarget(null); setPinError(""); setPinMenu(false);
    setHistoricalMessages(null); setHighlight(null); setLoadingPin(false); pendingJump.current = null;
    excerptArmed.current = false;
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

  function leaveExcerpt() {
    setHistoricalMessages(null); pendingJump.current = null; excerptArmed.current = false;
    ctx.scrollIntentRef.current = "normal";
    requestAnimationFrame(() => { const node = ctx.messagesRef.current; if (node) node.scrollTop = node.scrollHeight; });
  }
  // Mensagem nova (do cliente ou enviada aqui) com o trecho aberto: a lista
  // mostrava so o trecho, a thread era marcada como lida e o operador podia
  // reenviar sem ver a propria mensagem (revisao PR #8). Texto neutro: pode ser
  // a propria resposta do operador.
  useEffect(() => {
    if (!historicalMessages || !excerptArmed.current) return;
    if (lastActivity !== excerptBaseline.current) {
      leaveExcerpt();
      ctx.setNotice("Conversa atualizada: voltando às mensagens recentes.");
    }
  }, [lastActivity, historicalMessages]);
  // Busca digitada com o trecho aberto vale para a conversa ao vivo.
  useEffect(() => { if (historicalMessages && ctx.chatSearch) leaveExcerpt(); }, [ctx.chatSearch]);

  async function jump() {
    if (!pin || !ctx.bundle || loadingPin) return;
    setPinMenu(false);
    const id = pin.message_id;
    // Presenca decidida pelos DADOS, nao pelo DOM: com a busca aberta a bolha
    // carregada nao esta renderizada e o /context era chamado a toa.
    const inWindow = ctx.messages.some((m) => m.id === id) || !!historicalMessages?.some((m) => m.id === id);
    pendingJump.current = id;
    if (ctx.chatSearch) ctx.setChatSearch("");
    const node = ctx.messagesRef.current?.querySelector<HTMLElement>(`[data-message-id="${id}"]`);
    if (node) { node.scrollIntoView({ block: "center", behavior: "smooth" }); setHighlight(id); pendingJump.current = null; return; }
    if (inWindow) return; // o efeito rola quando a lista sem busca renderizar
    if (ctx.readOnly) { ctx.setNotice("Carregue as mensagens anteriores para acessar esta fixada no modo de visualização."); pendingJump.current = null; return; }
    // Fora do escopo estrito o /context responde 403: orienta em vez de chamar.
    if (!canAct) { ctx.setNotice("Role a conversa para cima para ver a mensagem fixada."); pendingJump.current = null; return; }
    setLoadingPin(true);
    const startedThread = thread;
    try {
      const res = await getJson<{ messages: Record<string, unknown>[] }>(ctx.bundle.auth, `/api/wa/messages/${id}/context`);
      if (threadRef.current !== startedThread) return;
      excerptArmed.current = true;
      excerptBaseline.current = lastActivityRef.current;
      setHistoricalMessages(res.messages.map((m) => normalizeMessage(m, String(m.id))));
    } catch (e) {
      // Sem desarmar, o salto disparava sozinho minutos depois, quando o lote
      // com a fixada chegasse pelo "carregar anteriores".
      if (pendingJump.current === id) pendingJump.current = null;
      if (threadRef.current === startedThread) ctx.setError(errorText(e));
    } finally { if (threadRef.current === startedThread) setLoadingPin(false); }
  }
  async function savePin(days: 1 | 7 | 30) {
    if (!ctx.bundle || !pinTarget || ctx.readOnly || mutating.current) return;
    const startedThread = thread;
    mutating.current = true; setBusyPin(true); setPinError("");
    try {
      const res = await sendJson<{ pinned_message: PinnedMessage }>(ctx.bundle.auth, `/api/wa/messages/${pinTarget.id}/pin`, { duration_days: days });
      if (threadRef.current === startedThread) { setPin(res.pinned_message); setPinTarget(null); }
    } catch (e) {
      // Erro dentro do dialogo: o alerta global ficava escondido atras do fundo escuro.
      if (threadRef.current === startedThread) setPinError(errorText(e));
    } finally { mutating.current = false; setBusyPin(false); }
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
    selection, toggleSelection, historicalMessages, highlight, canAct,
    startForward(message: ChatMessage) { if (!ctx.readOnly) setSelection(new Map([[message.id, message]])); },
    startPin(message: ChatMessage) { if (!ctx.readOnly) { setPinError(""); setPinTarget(message); } },
    pinBar: pin ? <div className="pinned-message-bar">
      <button type="button" className="pinned-message-preview" onClick={() => void jump()} disabled={loadingPin} title={`Fixada até ${new Date(pin.expires_at).toLocaleString("pt-BR")}`}><PinIcon /><span>{loadingPin ? "Buscando mensagem…" : waPlainText(pin.preview)}</span></button>
      <div className="pinned-message-options" ref={pinMenuRef}><button type="button" className="ghost" aria-label="Opções da mensagem fixada" aria-expanded={pinMenu} onClick={() => setPinMenu((v) => !v)}>⌄</button>
        {pinMenu && <div className="attach-menu"><button type="button" className="attach-option" onClick={() => void jump()}>Ir para a mensagem</button><button type="button" className="attach-option" disabled={ctx.readOnly || busyPin || !canAct} onClick={() => void unpin()}>Desfixar mensagem</button></div>}
      </div></div> : null,
    historyBar: historicalMessages ? <div className="message-history-bar"><span>Trecho da mensagem fixada</span><button type="button" className="ghost" onClick={leaveExcerpt}>Voltar às recentes</button></div> : null,
    selectionBar: selection ? <div className="message-selection-bar" role="region" aria-label="Encaminhar mensagens"><button type="button" className="ghost" aria-label="Cancelar seleção" onClick={() => { setSelection(null); setShowPicker(false); }}>×</button><span aria-live="polite">{selection.size} selecionada{selection.size === 1 ? "" : "s"}</span><button type="button" className="ghost" disabled={!selection.size || ctx.readOnly} onClick={() => setShowPicker(true)} aria-label="Escolher destino do encaminhamento"><ForwardIcon /></button></div> : null,
    dialogs: <>{showPicker && selection && <ForwardPicker key={thread} messageIds={selectedIds} onClose={() => setShowPicker(false)} onSent={(ids) => setSelection((prev) => { const next = new Map(prev); ids.forEach((id) => next.delete(id)); return next.size ? next : null; })} />}{pinTarget && <PinDurationDialog busy={busyPin} error={pinError} returnFocusSelector={`[data-message-id="${pinTarget.id}"] .bubble-menu-trigger`} onPin={(days) => void savePin(days)} onClose={() => { setPinTarget(null); setPinError(""); }} />}</>,
    selectionLabel(message: ChatMessage) { return `Selecionar mensagem: ${messageContentLabel(message).slice(0, 80) || message.msg_type}`; },
  };
}
