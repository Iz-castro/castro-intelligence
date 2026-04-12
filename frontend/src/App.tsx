import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { CrmProvider, useCrm } from "./context/CrmContext";
import { MoonIcon, SunIcon, GearIcon, PlusIcon, PhotoIcon, VideoIcon, FileIcon, MapPinIcon, MicIcon, SendIcon, SearchIcon, DotsIcon, CloseIcon } from "./components/icons";
import { when, formatRecordingTime, messageTypeLabel, messageContentLabel, messageSenderLabel } from "./utils/formatting";
import { resolveMessageMedia } from "./utils/media";
import { useClickOutside } from "./hooks/useClickOutside";
import { InternalChatPanel, GcBadgeIcon } from "./components/gchat/InternalChatPanel";
import { getJson, sendJson, putJson, deleteJson, sendForm } from "./api";
import type { Channel, ChatMessage, Contact, Department, Operator } from "./types";

const TEAM_OPERATOR_COLORS = ["#0f766e", "#1d4ed8", "#c2410c", "#7c3aed", "#be123c", "#0f766e", "#0369a1", "#15803d", "#b45309", "#4338ca"];

function withAlpha(hex: string, alpha: string) {
  return `${hex}${alpha}`;
}

function operatorColor(seed: number | string) {
  const text = String(seed || "operator");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  return TEAM_OPERATOR_COLORS[Math.abs(hash) % TEAM_OPERATOR_COLORS.length];
}

function operatorLogin(operator: Partial<Operator> | null | undefined) {
  return String(operator?.username || operator?.email?.split("@")[0] || operator?.display_name || "").trim();
}

function operatorInitial(operator: Partial<Operator> | null | undefined) {
  return (operatorLogin(operator) || "?").slice(0, 1).toUpperCase();
}

function findAssignedOperator(contact: Contact | null | undefined, operators: Operator[]) {
  if (!contact?.assigned_to) return null;
  return operators.find((operator) => operator.id === contact.assigned_to) || null;
}

function findMessageOperator(message: ChatMessage, operators: Operator[], selectedContact: Contact | null) {
  if (message.operator_id) {
    const operator = operators.find((item) => item.id === message.operator_id);
    if (operator) return operator;
  }
  if (message.operator_name) {
    const byName = operators.find((item) => item.display_name === message.operator_name);
    if (byName) return byName;
  }
  return findAssignedOperator(selectedContact, operators);
}

function operatorAccentStyle(color: string | null): CSSProperties | undefined {
  if (!color) return undefined;
  return {
    borderColor: withAlpha(color, "55"),
    boxShadow: `inset 4px 0 0 ${color}`,
  };
}

// ---------------------------------------------------------------------------
// Small inline sub-components (consume context via useCrm)
// ---------------------------------------------------------------------------

function BootScreen() {
  return <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Carregando Firebase e Firestore</h1></div></div>;
}

function LoginScreen() {
  const { config, bundle, busyLogin, error, loginWithGoogle } = useCrm();
  return (
    <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Entrar com Google</h1>
      <p>{config?.allowed_email_domain ? `Use sua conta ${config.allowed_email_domain}.` : "Use uma conta Google autorizada."}</p>
      <button className="primary" onClick={() => void loginWithGoogle()} disabled={!bundle || busyLogin}>{busyLogin ? "Conectando..." : "Entrar com Google"}</button>
      {error ? <div className="alert danger">{error}</div> : null}
    </div></div>
  );
}

function TopBar() {
  const { sessionUser, config, theme, toggleTheme, showSettings, setShowSettings, toggleSettingsMenu, openSettingsPage, settingsMenuRef, logout } = useCrm();
  const [gcOpen, setGcOpen] = useState(false);
  useClickOutside(settingsMenuRef, showSettings === "menu", () => setShowSettings(false));
  if (!sessionUser) return null;
  const gcEnabled = config?.feature_google_chat ?? false;
  return (
    <header className="crm-topbar">
      <div className="topbar-brand"><p className="eyebrow">Hubloc CRM</p></div>
      <div className="topbar-user">
        <strong>{sessionUser.display_name}</strong>
        <span className="sub">{sessionUser.email || sessionUser.username} · <span className="chip">{sessionUser.role}</span></span>
      </div>
      <div className="topbar-actions">
        <button className="composer-icon" onClick={toggleTheme} title={theme === "dark" ? "Tema claro" : "Tema escuro"} aria-label="Alternar tema">
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        {gcEnabled && (
          <button className="composer-icon" onClick={() => setGcOpen((v) => !v)} title="Chat Interno" aria-label="Chat Interno">
            <GcBadgeIcon totalUnread={0} />
          </button>
        )}
        <div ref={settingsMenuRef} style={{ position: "relative" }}>
          <button className="composer-icon" onClick={toggleSettingsMenu} title="Configuracoes" aria-label="Configuracoes"><GearIcon /></button>
          {showSettings === "menu" && (
            <div className="settings-dropdown">
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("chat")}><span>💬</span><span>Chat</span></button>
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("quick")}><span>⚡</span><span>Mensagens rapidas</span></button>
              {sessionUser.role === "admin" && <button type="button" className="attach-option" onClick={() => void openSettingsPage("admin")}><span>🔧</span><span>Administracao</span></button>}
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor") && <button type="button" className="attach-option" onClick={() => void openSettingsPage("whatsapp")}><span>📱</span><span>WhatsApp Coexistence</span></button>}
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor") && <button type="button" className="attach-option" onClick={() => void openSettingsPage("dashboard")}><span>📊</span><span>Dashboard</span></button>}
            </div>
          )}
        </div>
        <button className="ghost" style={{ padding: "0.55rem 1rem", fontSize: "0.9rem" }} onClick={() => void logout()}>Sair</button>
      </div>
      {gcEnabled && <InternalChatPanel open={gcOpen} onClose={() => setGcOpen(false)} />}
    </header>
  );
}

function NavBar() {
  const { activeView, setActiveView, setQualificationFilter, setEquipeOperatorFilter, isManagerRole, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, systemSettings } = useCrm();
  return (
    <nav className="crm-nav">
      {isManagerRole && systemSettings.bot_enabled && <button className={`nav-item ${activeView === "bot" ? "active" : ""}`} onClick={() => { setActiveView("bot"); setQualificationFilter(""); }} title="Contatos no bot">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="3"/><line x1="8" y1="16" x2="8" y2="16.01"/><line x1="16" y1="16" x2="16" y2="16.01"/><line x1="12" y1="19" x2="12" y2="19.01"/></svg>
        <span className="nav-label">Bot</span>
        {botUnread > 0 && <span className="nav-badge">{botUnread > 99 ? "99+" : botUnread}</span>}
      </button>}
      <button className={`nav-item ${activeView === "novos" ? "active" : ""}`} onClick={() => { setActiveView("novos"); setQualificationFilter(""); }} title="Novos leads">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="12" y1="8" x2="12" y2="14"/><line x1="9" y1="11" x2="15" y2="11"/></svg>
        <span className="nav-label">Novos</span>
        {novosUnread > 0 && <span className="nav-badge">{novosUnread > 99 ? "99+" : novosUnread}</span>}
      </button>
      <button className={`nav-item ${activeView === "meus" ? "active" : ""}`} onClick={() => { setActiveView("meus"); setQualificationFilter(""); }} title="Meus atendimentos">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <span className="nav-label">Meus</span>
        {meusUnread > 0 && <span className="nav-badge">{meusUnread > 99 ? "99+" : meusUnread}</span>}
      </button>
      <button className={`nav-item ${activeView === "nao_qualificados" ? "active" : ""}`} onClick={() => { setActiveView("nao_qualificados"); setQualificationFilter(""); }} title="Nao qualificados">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>
        <span className="nav-label">N/Q</span>
        {nqUnread > 0 && <span className="nav-badge">{nqUnread > 99 ? "99+" : nqUnread}</span>}
      </button>
      {isManagerRole && <button className={`nav-item ${activeView === "equipe" ? "active" : ""}`} onClick={() => { setActiveView("equipe"); setQualificationFilter(""); setEquipeOperatorFilter(""); }} title="Atendimentos da equipe">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <span className="nav-label">Equipe</span>
        {equipeUnread > 0 && <span className="nav-badge">{equipeUnread > 99 ? "99+" : equipeUnread}</span>}
      </button>}
    </nav>
  );
}

function NewContactModal({ onClose }: { onClose: () => void }) {
  const { createManualContact, busyCreateContact, channels } = useCrm();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const availableChannels = channels.filter(ch => ch.is_active);
  const [channelId, setChannelId] = useState<number | "">(availableChannels.length === 1 ? availableChannels[0].id : "");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !phone.trim()) return;
    const result = await createManualContact(name.trim(), phone.trim(), channelId ? Number(channelId) : undefined);
    if (result) onClose();
  }

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Novo contato" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" style={{ width: "min(420px, 92vw)" }} onClick={(e) => e.stopPropagation()}>
        <p className="eyebrow">Novo contato</p>
        <h2 style={{ margin: "0 0 1rem" }}>Criar contato manual</h2>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do contato" autoFocus required />
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Telefone (ex: 31999990000)" required />
          {availableChannels.length > 1 && (
            <select value={channelId} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecionar canal</option>
              {availableChannels.map(ch => <option key={ch.id} value={ch.id}>{ch.label || ch.display_phone_number}</option>)}
            </select>
          )}
          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="primary" disabled={busyCreateContact || !name.trim() || !phone.trim()}>{busyCreateContact ? "Criando..." : "Criar contato"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ContactList() {
  const { activeView, filteredContacts, selectedContactId, setSelectedContactId, search, setSearch, qualificationFilter, setQualificationFilter, equipeOperatorFilter, setEquipeOperatorFilter, operators, sessionUser } = useCrm();
  const [showNewContact, setShowNewContact] = useState(false);
  const viewTitle = activeView === "bot" ? "Bot" : activeView === "novos" ? "Novos Leads" : activeView === "meus" ? "Meus Atendimentos" : activeView === "equipe" ? "Equipe" : "Nao Qualificados";
  const visibleTeamOperators = activeView === "equipe"
    ? operators
      .filter((operator) => operator.id !== sessionUser?.id && filteredContacts.some((contact) => contact.assigned_to === operator.id))
      .sort((left, right) => left.display_name.localeCompare(right.display_name))
    : [];
  return (
    <aside className="panel sidebar">
      <div className={`panel-head ${activeView === "equipe" ? "panel-head--stacked" : ""}`}>
        <div><p className="eyebrow">{viewTitle}</p><h2>{filteredContacts.length} conversa{filteredContacts.length !== 1 ? "s" : ""}</h2></div>
        {activeView === "equipe" && visibleTeamOperators.length ? (
          <div className="operator-presence-strip" aria-label="Operadores com conversas visiveis">
            {visibleTeamOperators.map((operator) => {
              const color = operatorColor(operator.id);
              return (
                <span
                  key={operator.id}
                  className="operator-presence-dot"
                  title={operator.display_name}
                  aria-label={operator.display_name}
                  style={{ borderColor: withAlpha(color, "55"), background: `linear-gradient(135deg, ${withAlpha(color, "2e")}, ${withAlpha(color, "14")})`, color }}
                >
                  {operatorInitial(operator)}
                </span>
              );
            })}
          </div>
        ) : null}
      </div>
      <div className="toolbar">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar contato" />
        {activeView === "meus" && <>
          <button type="button" className="composer-icon" style={{ width: 36, height: 36, flexShrink: 0 }} onClick={() => setShowNewContact(true)} title="Novo contato" aria-label="Novo contato"><PlusIcon /></button>
          <select className="compact" value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}><option value="">Todos</option><option value="novo">Novo</option><option value="em_atendimento">Em atend.</option><option value="qualificado">Qualificado</option><option value="convertido">Convertido</option></select>
        </>}
        {activeView === "equipe" && <select className="compact" value={equipeOperatorFilter} onChange={(e) => setEquipeOperatorFilter(e.target.value)}><option value="">Todos operadores</option>{operators.filter((op) => op.id !== sessionUser?.id).map((op) => <option key={op.id} value={String(op.id)}>{op.display_name}</option>)}</select>}
      </div>
      <div className="contact-list">
        {filteredContacts.map((contact) => {
          const assignedOperator = activeView === "equipe" ? findAssignedOperator(contact, operators) : null;
          const accent = assignedOperator ? operatorColor(assignedOperator.id) : null;
          return (
            <button key={contact.id} className={`contact ${selectedContactId === contact.id ? "active" : ""} ${accent ? "contact--team-accent" : ""}`} onClick={() => setSelectedContactId(contact.id)} style={operatorAccentStyle(accent)}>
              <div className="avatar">{contact.contact_avatar_path ? <img src={contact.contact_avatar_path} alt={contact.display_name} /> : <span>{contact.display_name.slice(0, 1).toUpperCase()}</span>}</div>
              <div className="contact-copy">
                <div className="row">
                  <strong>{contact.display_name}</strong>
                  <div className="contact-meta">
                    {assignedOperator ? (
                      <span
                        className="contact-operator-dot"
                        title={assignedOperator.display_name}
                        aria-label={assignedOperator.display_name}
                        style={{ borderColor: withAlpha(accent || "#0f766e", "55"), background: withAlpha(accent || "#0f766e", "18"), color: accent || "#0f766e" }}
                      >
                        {operatorInitial(assignedOperator)}
                      </span>
                    ) : null}
                    <span>{when(contact.last_message_at)}</span>
                  </div>
                </div>
                <div className="sub">{contact.phone_formatted || contact.wa_id}{activeView === "equipe" && contact.assigned_name ? ` · ${contact.assigned_name}` : ""}</div>
                <div className="row">
                  <span className="chip">{contact.qualification || "novo"}</span>
                  {contact.source_channel_type === "coexistence" ? <span className="chip" style={{ fontSize: "0.65rem", opacity: 0.7 }}>coex</span> : null}
                  {contact.unread ? <b className="badge">{contact.unread}</b> : null}
                </div>
              </div>
            </button>
          );
        })}
        {!filteredContacts.length ? <div className="empty">{activeView === "bot" ? "Nenhum contato no bot." : activeView === "novos" ? "Nenhum lead novo na fila." : activeView === "meus" ? "Nenhum atendimento ativo." : activeView === "equipe" ? "Nenhum atendimento da equipe." : "Nenhum contato nao qualificado."}</div> : null}
      </div>
      {showNewContact && <NewContactModal onClose={() => setShowNewContact(false)} />}
    </aside>
  );
}

function MessageMedia({ message }: { message: ChatMessage }) {
  const { transcribingMessageId, transcribeMessage, openLightbox } = useCrm();
  const media = resolveMessageMedia(message);
  if (!media || !message.media_path) return null;

  if (media.kind === "image") {
    const cls = ["media"];
    if (media.sticker) cls.push("sticker-media");
    if (media.gifLike) cls.push("gif-media");
    return <button type="button" className={`media-button ${media.sticker ? "sticker-button" : ""}`} onClick={() => openLightbox(message.media_path || "", "image", media.alt, media.gifLike)} aria-label="Ampliar imagem"><img className={cls.join(" ")} src={message.media_path} alt={media.alt} loading="lazy" /></button>;
  }
  if (media.kind === "video") {
    if (media.gifLike) return <button type="button" className="media-button gif-button" onClick={() => openLightbox(message.media_path || "", "video", media.alt, true)} aria-label="Ampliar GIF"><video className="media video-media gif-video" src={message.media_path} autoPlay loop muted playsInline /></button>;
    return <a href={message.media_path} download={message.filename || "video"} target="_blank" rel="noreferrer" className="video-download-link"><VideoIcon /> <span>Baixar video{message.filename ? ` — ${message.filename}` : ""}</span></a>;
  }
  if (media.kind === "audio") return (
    <div className="audio-container">
      <audio controls src={message.media_path} />
      {message.transcription ? <p className="transcription-text">{message.transcription}</p> : (
        <button type="button" className="transcribe-btn" onClick={() => void transcribeMessage(message.id)} disabled={transcribingMessageId === message.id}>{transcribingMessageId === message.id ? "Transcrevendo..." : "🔤 Transcrever"}</button>
      )}
    </div>
  );
  return <a href={message.media_path} target="_blank" rel="noreferrer">Abrir {message.filename || "arquivo"}</a>;
}

function ReplyQuote({ senderName, preview, compact = false }: { senderName: string; preview: string; compact?: boolean }) {
  if (!preview.trim()) return null;
  return (
    <div className={`reply-quote ${compact ? "compact" : ""}`}>
      <span className="reply-quote__sender">{senderName.trim() || "Mensagem"}</span>
      <p>{preview}</p>
    </div>
  );
}

function ChatPanel() {
  const ctx = useCrm();
  const { activeView, operators, selectedContact, sessionUser, error, notice, config, messagesRef, scrollIntentRef, prevMessageCountRef, messages, selectedContactId, loadingMore, setLoadingMore, messageLimit, setMessageLimit, visibleMessages, visibleMessagesFiltered, showChatSearch, chatSearch, setChatSearch, toggleChatSearch, showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef, busyAssume, assumeContact, quickSuggestions, applyQuickMessage, replyTarget, startReplyToMessage, cancelReply, copyMessageText, draft, handleDraftChange, handleDraftKeyDown, submitText, recording, recordingSeconds, discardRecording, handlePrimaryAction, busySend, busyAudio, busyUpload, busyComposerAction, showAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, sendLocation, handleImageSelected, submitFile, imageInputRef, videoInputRef, documentInputRef, attachMenuRef, composerInputRef, correctionTarget, startCorrection, cancelCorrection, correctMessage, updateDeclaredName } = { ...ctx, busyComposerAction: ctx.busyAudio || ctx.busySend };
  const hasDraft = Boolean(draft.trim());
  const [editingNickname, setEditingNickname] = useState(false);
  const [nicknameInput, setNicknameInput] = useState("");
  const [openMessageMenuId, setOpenMessageMenuId] = useState<number | null>(null);
  const [openMessageMenuDirection, setOpenMessageMenuDirection] = useState<"down" | "up">("down");
  const activeMessageMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedOperator = activeView === "equipe" ? findAssignedOperator(selectedContact, operators) : null;
  const selectedOperatorColor = selectedOperator ? operatorColor(selectedOperator.id) : null;
  const noInboundWindow = selectedContact && !selectedContact.last_inbound_at;
  const isManualContact = selectedContact?.created_source === "manual";
  const chatIsEmpty = selectedContact && visibleMessages.length === 0;
  useClickOutside(activeMessageMenuRef, openMessageMenuId !== null, () => setOpenMessageMenuId(null));

  // Scroll management — must live here (not in CrmProvider) because messagesRef is attached to a DOM node inside this component
  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    if (scrollIntentRef.current === "load_older") {
      // Older messages loaded (or all messages already fetched — count unchanged)
      if (messages.length > prevMessageCountRef.current) {
        const newH = container.scrollHeight;
        const prevH = container.dataset.prevScrollHeight;
        if (prevH) container.scrollTop = newH - Number(prevH);
      }
      scrollIntentRef.current = "normal";
    } else if (scrollIntentRef.current === "normal") {
      // Auto-scroll to bottom when:
      // - initial load (prevCount === 0)
      // - new message arrived (count increased) and user was reasonably near bottom
      // - user is already near the bottom
      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const isNewMessage = messages.length > prevMessageCountRef.current && prevMessageCountRef.current > 0;
      if (prevMessageCountRef.current === 0 || isNewMessage || distFromBottom < 300) {
        container.scrollTop = container.scrollHeight;
      }
    }
    prevMessageCountRef.current = messages.length;
    setLoadingMore(false);
  }, [messages, selectedContactId]);

  // Infinite scroll — attach scroll listener to load older messages
  useEffect(() => {
    const container = messagesRef.current;
    if (!container || !selectedContactId) return undefined;
    const handleScroll = () => {
      const hasPotentialOlderMessages = messages.length >= messageLimit;
      if (container.scrollTop < 40 && !loadingMore && hasPotentialOlderMessages) {
        container.dataset.prevScrollHeight = String(container.scrollHeight);
        scrollIntentRef.current = "load_older";
        setLoadingMore(true);
        setMessageLimit((prev) => prev + 15);
      }
    };
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [selectedContactId, loadingMore, messageLimit, messages.length]);

  useEffect(() => {
    setOpenMessageMenuId(null);
  }, [selectedContactId]);

  useEffect(() => {
    if (openMessageMenuId === null) {
      setOpenMessageMenuDirection("down");
      return undefined;
    }

    const updateMenuDirection = () => {
      const anchor = activeMessageMenuRef.current;
      const container = messagesRef.current;
      const menu = anchor?.querySelector<HTMLElement>(".bubble-menu");
      if (!anchor || !container || !menu) return;

      const anchorRect = anchor.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const menuHeight = menu.offsetHeight;
      const gap = 8;
      const spaceBelow = containerRect.bottom - anchorRect.bottom;
      const spaceAbove = anchorRect.top - containerRect.top;
      setOpenMessageMenuDirection(spaceBelow < menuHeight + gap && spaceAbove > spaceBelow ? "up" : "down");
    };

    const frameId = window.requestAnimationFrame(updateMenuDirection);
    const scrollContainer = messagesRef.current;
    scrollContainer?.addEventListener("scroll", updateMenuDirection, { passive: true });
    window.addEventListener("resize", updateMenuDirection);

    return () => {
      window.cancelAnimationFrame(frameId);
      scrollContainer?.removeEventListener("scroll", updateMenuDirection);
      window.removeEventListener("resize", updateMenuDirection);
    };
  }, [messagesRef, openMessageMenuId]);

  return (
    <main className="panel chat-panel">
      {error ? <div className="alert danger"><span>{error}</span><button type="button" className="alert-close" onClick={() => ctx.setError("")}>&#10005;</button></div> : null}
      {notice ? <div className="alert success"><span>{notice}</span><button type="button" className="alert-close" onClick={() => ctx.setNotice("")}>&#10005;</button></div> : null}
      {selectedContact ? <>
        <div className="contact-banner">
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", flexWrap: "wrap" }}>
              <strong>{selectedContact.whatsapp_profile_name || selectedContact.phone_formatted || selectedContact.wa_id}</strong>
              {selectedContact.declared_name ? (
                <span className="sub" style={{ fontSize: "0.82rem" }}>- {selectedContact.declared_name}</span>
              ) : null}
            </div>
            {selectedOperator ? (
              <div className="contact-operator-chip">
                <span
                  className="contact-operator-dot"
                  title={selectedOperator.display_name}
                  aria-label={selectedOperator.display_name}
                  style={{ borderColor: withAlpha(selectedOperatorColor || "#0f766e", "55"), background: withAlpha(selectedOperatorColor || "#0f766e", "18"), color: selectedOperatorColor || "#0f766e" }}
                >
                  {operatorInitial(selectedOperator)}
                </span>
                <span className="sub" style={{ color: selectedOperatorColor || undefined }}>{selectedOperator.display_name}</span>
              </div>
            ) : null}
            <div className="sub">{selectedContact.phone_formatted || selectedContact.wa_id}{selectedContact.assigned_name ? ` · ${selectedContact.assigned_name}` : ""}</div>
            {selectedContact.attendance_protocol ? <div className="sub" style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: "0.72rem", marginTop: "0.2rem" }}>{selectedContact.attendance_protocol}{selectedContact.attendance_started_at ? ` · inicio ${when(selectedContact.attendance_started_at)}` : ""}</div> : null}
          </div>
          <div className="banner-actions">
            <div className="chips">
              <span className="chip">{selectedContact.department_name || "Sem setor"}</span>
              <span className="chip">{selectedContact.qualification || "sem classificacao"}</span>
            </div>
            <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.4rem", justifyContent: "flex-end" }}>
              {!selectedContact.assigned_to || selectedContact.assigned_to !== sessionUser!.id ? <button className="assume-btn" onClick={() => void assumeContact(selectedContact.id)} disabled={busyAssume}>{busyAssume ? "Assumindo..." : "Assumir atendimento"}</button> : null}
              <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleChatSearch} aria-label="Buscar na conversa" title="Buscar na conversa">{showChatSearch ? <CloseIcon /> : <SearchIcon />}</button>
              <div ref={dotsMenuRef} style={{ position: "relative" }}>
                <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleDotsMenu} aria-label="Mais opcoes" title="Mais opcoes"><DotsIcon /></button>
                {showDotsMenu ? (
                  <div className="attach-menu" style={{ right: 0, left: "auto", bottom: "auto", top: "calc(100% + 0.5rem)", minWidth: 220 }}>
                    <button type="button" className="attach-option" onClick={() => closeDotsMenu()}><span>📋</span><span>Templates Utility</span></button>
                    <button type="button" className="attach-option" onClick={() => closeDotsMenu()}><span>📣</span><span>Templates Marketing</span></button>
                    <div style={{ height: 1, background: "var(--border)", margin: "0.3rem 0.5rem" }} />
                    <button type="button" className="attach-option" onClick={() => { setNicknameInput(selectedContact.declared_name || ""); setEditingNickname(true); closeDotsMenu(); }}><span>✏️</span><span>Editar apelido</span></button>
                    {selectedContact.attendance_protocol ? <button type="button" className="attach-option" onClick={() => { navigator.clipboard.writeText(selectedContact.attendance_protocol!).catch(() => {}); closeDotsMenu(); ctx.setNotice(`Protocolo copiado: ${selectedContact.attendance_protocol}`); }}><span>📋</span><span>Copiar protocolo</span></button> : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {editingNickname ? (
          <form className="toolbar" onSubmit={(e) => { e.preventDefault(); void updateDeclaredName(selectedContact.id, nicknameInput.trim()); setEditingNickname(false); }} style={{ gap: "0.4rem" }}>
            <input value={nicknameInput} onChange={(e) => setNicknameInput(e.target.value)} placeholder="Apelido do contato (vazio para remover)" autoFocus style={{ flex: 1 }} />
            <button type="submit" className="ghost" style={{ padding: "0.6rem 0.8rem", fontSize: "0.82rem" }}>Salvar</button>
            <button type="button" className="ghost" style={{ padding: "0.6rem 0.8rem", fontSize: "0.82rem", opacity: 0.6 }} onClick={() => setEditingNickname(false)}>x</button>
          </form>
        ) : null}
        {showChatSearch ? <div className="toolbar"><input value={chatSearch} onChange={(e) => setChatSearch(e.target.value)} placeholder="Buscar na conversa..." autoFocus />{chatSearch ? <span className="sub">{(visibleMessagesFiltered ?? []).length} resultado(s)</span> : null}</div> : null}

        <div className="messages" ref={messagesRef}>
          {chatIsEmpty && isManualContact ? (
            <div className="empty" style={{ alignSelf: "center", textAlign: "center", marginTop: "2rem" }}>
              <p style={{ marginBottom: "0.5rem" }}>Contato criado manualmente.</p>
              <p>Envie um template para iniciar a conversa.</p>
            </div>
          ) : null}
          {loadingMore && <div className="sub" style={{ textAlign: "center", padding: "0.5rem" }}>Carregando mensagens anteriores...</div>}
          {(visibleMessagesFiltered ?? visibleMessages).map((message) => {
            const canInteract = message.direction !== "system";
            const isMenuOpen = openMessageMenuId === message.id;
            const bubbleOperator = activeView === "equipe" && message.direction === "outbound" ? findMessageOperator(message, operators, selectedContact) : null;
            const bubbleColor = bubbleOperator ? operatorColor(bubbleOperator.id) : null;
            return (
              <article key={message.id} className={`bubble ${message.direction} ${canInteract ? "has-actions" : ""} ${bubbleColor ? "bubble--team-accent" : ""}`} style={operatorAccentStyle(bubbleColor)}>
                {canInteract ? (
                  <div className="bubble-menu-anchor" ref={isMenuOpen ? activeMessageMenuRef : null}>
                    <button type="button" className="bubble-menu-trigger" onClick={() => setOpenMessageMenuId((current) => current === message.id ? null : message.id)} aria-label="Acoes da mensagem" aria-expanded={isMenuOpen}>v</button>
                    {isMenuOpen ? (
                      <div className={`bubble-menu attach-menu ${openMessageMenuDirection === "up" ? "open-upward" : ""}`}>
                        <button type="button" className="attach-option" onClick={() => { startReplyToMessage(message); setOpenMessageMenuId(null); }}><span>Responder</span></button>
                        <button type="button" className="attach-option" onClick={() => { void copyMessageText(message); setOpenMessageMenuId(null); }}><span>Copiar</span></button>
                        {message.direction === "outbound" && message.msg_type === "text" && !message.is_corrected && (message.operator_id === sessionUser?.id || sessionUser?.role === "admin" || sessionUser?.role === "supervisor") ? (
                          <button type="button" className="attach-option" onClick={() => { startCorrection(message); setOpenMessageMenuId(null); }}><span>Corrigir</span></button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <header><strong style={bubbleColor ? { color: bubbleColor } : undefined}>{messageSenderLabel(message)}</strong><span>{when(message.created_at || message.timestamp_wa)}</span></header>
                {message.reply_to_preview ? <ReplyQuote senderName={message.reply_to_sender_name || "Mensagem"} preview={message.reply_to_preview} /> : null}
                {messageContentLabel(message) ? <p>{messageContentLabel(message)}</p> : null}
                <MessageMedia message={message} />
                <footer><span>{messageTypeLabel(message.msg_type)}{message.is_corrected ? " · corrigida" : ""}</span>{config?.feature_message_status !== false && <span>{message.status || "ok"}</span>}</footer>
              </article>
            );
          })}
          {visibleMessagesFiltered !== null && visibleMessagesFiltered.length === 0 ? <div className="empty" style={{ alignSelf: "center" }}>Nenhuma mensagem encontrada para "{chatSearch}".</div> : null}
        </div>

        {quickSuggestions.length > 0 && (
          <div className="quick-suggestions">{quickSuggestions.map((qm, idx) => (
            <button key={idx} type="button" className="quick-suggestion-item" onClick={() => applyQuickMessage(qm)}>
              <strong>{qm.shortcut.startsWith("/") ? qm.shortcut : `/${qm.shortcut}`}</strong>
              <span className="sub">{qm.message.length > 80 ? qm.message.slice(0, 80) + "..." : qm.message}</span>
            </button>
          ))}</div>
        )}

        {noInboundWindow ? (
          <div className="composer" style={{ padding: "0.8rem 1rem" }}>
            <div className="sub" style={{ textAlign: "center", width: "100%" }}>Janela de 24h indisponivel. Use o menu de templates para iniciar a conversa.</div>
          </div>
        ) : (
        <form className="composer" onSubmit={correctionTarget ? (e) => { e.preventDefault(); if (draft.trim()) void correctMessage(correctionTarget.id, draft.trim()); } : submitText}>
          {correctionTarget ? (
            <div className="composer-reply-preview" style={{ borderLeft: "3px solid var(--warm)" }}>
              <div style={{ flex: 1 }}>
                <span className="sub" style={{ fontWeight: 600, color: "var(--warm)" }}>Corrigindo mensagem</span>
                <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem" }}>{(correctionTarget.content || "").slice(0, 100)}</p>
              </div>
              <button type="button" className="reply-preview-close" onClick={cancelCorrection} aria-label="Cancelar correcao">x</button>
            </div>
          ) : replyTarget ? (
            <div className="composer-reply-preview">
              <ReplyQuote senderName={replyTarget.sender_name} preview={replyTarget.preview} compact />
              <button type="button" className="reply-preview-close" onClick={cancelReply} aria-label="Cancelar resposta">x</button>
            </div>
          ) : null}
          <div className={`composer-shell ${recording ? "is-recording" : ""}`}>
            <div className="composer-menu" ref={attachMenuRef}>
              <button type="button" className="composer-icon attach-trigger" onClick={toggleAttachMenu} disabled={!selectedContact || busyUpload || busyAudio} aria-label="Abrir menu de anexos"><PlusIcon /></button>
              {showAttachMenu ? (
                <div className="attach-menu">
                  <button type="button" className="attach-option" onClick={openImagePicker}><PhotoIcon /><span>Foto</span></button>
                  <button type="button" className="attach-option" onClick={openVideoPicker}><VideoIcon /><span>Vídeo</span></button>
                  <button type="button" className="attach-option" onClick={openDocPicker}><FileIcon /><span>Documento</span></button>
                  <button type="button" className="attach-option" onClick={() => void sendLocation()}><MapPinIcon /><span>Localização</span></button>
                </div>
              ) : null}
              <input ref={imageInputRef} type="file" accept="image/*" onChange={handleImageSelected} hidden />
              <input ref={videoInputRef} type="file" accept="video/*" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Vídeo"); }} hidden />
              <input ref={documentInputRef} type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.zip,.csv" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Documento"); }} hidden />
            </div>
            <div className="composer-field">
              {recording ? <div className="recording-status"><span className="recording-dot" /><span>Gravando audio</span><strong>{formatRecordingTime(recordingSeconds)}</strong><button type="button" className="recording-cancel" onClick={discardRecording}>Cancelar</button></div> : <textarea ref={composerInputRef} value={draft} onChange={handleDraftChange} onKeyDown={handleDraftKeyDown} rows={1} placeholder="Digite uma mensagem" disabled={busySend || busyAudio} />}
            </div>
            <button type="button" className={`composer-icon mic-trigger ${recording ? "recording" : ""} ${hasDraft && !recording ? "send-ready" : ""}`} onClick={handlePrimaryAction} disabled={!selectedContact || busyUpload || busyComposerAction} aria-label={recording ? "Enviar audio gravado" : hasDraft ? "Enviar mensagem" : "Gravar audio"}>
              {busyComposerAction ? <span className="button-spinner" aria-hidden="true" /> : recording || hasDraft ? <SendIcon /> : <MicIcon />}
            </button>
          </div>
        </form>
        )}
      </> : <div className="empty large">Selecione um contato para abrir a conversa.</div>}
    </main>
  );
}

function CollapsibleCard({ title, defaultOpen = true, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="card collapsible-card">
      <button type="button" className="collapsible-header" onClick={() => setOpen((v) => !v)}>
        <h3>{title}</h3>
        <span className={`collapsible-arrow ${open ? "open" : ""}`}>&#9662;</span>
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

function DetailPanel() {
  const { bundle, selectedContact, sessionUser, isManagerRole, operators, departments, channels, qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary, busySave, busyTransfer, saveQualification, transferContact, editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole, setError, setNotice, refreshPollingViews } = useCrm();
  const [busyReturnBot, setBusyReturnBot] = useState(false);
  const [bulkFromUser, setBulkFromUser] = useState<number | "">("");
  const [bulkAction, setBulkAction] = useState<"return_to_bot" | "transfer">("return_to_bot");
  const [bulkToUser, setBulkToUser] = useState<number | "">("");
  const [busyBulk, setBusyBulk] = useState(false);
  const [busyResetCounter, setBusyResetCounter] = useState<number | null>(null);

  const resetAssumeCounter = useCallback(async (userId: number, displayName: string) => {
    if (!bundle) return;
    setBusyResetCounter(userId);
    try {
      await sendJson(bundle.auth, `/api/admin/operator/${userId}/reset-assume-counter`, {});
      setNotice(`Contador de ${displayName} resetado.`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyResetCounter(null);
  }, [bundle, setError, setNotice]);

  const returnToBot = useCallback(async (contactId: number) => {
    if (!bundle) return;
    setBusyReturnBot(true);
    try {
      await sendJson(bundle.auth, `/api/wa/contact/${contactId}/return-to-bot`);
      setNotice("Contato devolvido ao bot");
      await refreshPollingViews();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyReturnBot(false);
  }, [bundle, setError, setNotice, refreshPollingViews]);

  const executeBulkReassign = useCallback(async () => {
    if (!bundle || !bulkFromUser) return;
    setBusyBulk(true);
    try {
      const res = await sendJson<{ count: number }>(bundle.auth, "/api/admin/bulk-reassign", {
        from_user_id: bulkFromUser,
        action: bulkAction,
        to_user_id: bulkAction === "transfer" ? bulkToUser || undefined : undefined,
      });
      setNotice(`${res.count} contato(s) reatribuido(s)`);
      setBulkFromUser("");
      await refreshPollingViews();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyBulk(false);
  }, [bundle, bulkFromUser, bulkAction, bulkToUser, setError, setNotice, refreshPollingViews]);

  const contactChannel = selectedContact?.channel_id ? channels.find((ch) => ch.id === selectedContact.channel_id) : null;

  return (
    <aside className="panel detail-panel">
      <div className="panel-head"><div><p className="eyebrow">Contato</p><h2>Operacao</h2></div><span className="sub">{operators.length} operadores - {departments.length} setores</span></div>
      <div className="detail-scroll">
        {selectedContact ? <>
          {/* Info do canal */}
          {contactChannel ? (
            <div style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", opacity: 0.7, display: "flex", gap: "0.3rem", alignItems: "center" }}>
              <span className="chip" style={{ fontSize: "0.65rem" }}>{contactChannel.channel_type === "standard" ? "Cloud API" : "Coexistence"}</span>
              <span>{contactChannel.label}</span>
            </div>
          ) : null}

          {/* Rating (visivel apenas para admin/supervisor) */}
          {isManagerRole && selectedContact.qualification === "convertido" ? (
            <div style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
              {selectedContact.rating != null ? (
                <><span style={{ fontWeight: 600 }}>Avaliacao:</span><span className="chip" style={{ fontSize: "0.8rem", background: selectedContact.rating >= 7 ? "var(--success)" : selectedContact.rating >= 4 ? "#e6a817" : "var(--danger)", color: "#fff" }}>{selectedContact.rating}/10</span></>
              ) : (
                <span className="sub">Avaliacao pendente...</span>
              )}
            </div>
          ) : null}

          <CollapsibleCard title="Qualificacao">
            <select value={qualification} onChange={(e) => setQualification(e.target.value)}><option value="novo">Novo</option><option value="em_atendimento">Em atendimento</option><option value="qualificado">Qualificado</option><option value="nao_qualificado">Nao qualificado</option><option value="convertido">Convertido</option></select>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Notas do atendimento" />
            <button className="primary" onClick={() => void saveQualification()} disabled={busySave}>{busySave ? "Salvando..." : "Salvar"}</button>
            {isManagerRole && selectedContact.assigned_to ? (
              <button className="ghost" style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} disabled={busyReturnBot} onClick={() => { if (confirm("Devolver este contato para a fila do bot?")) void returnToBot(selectedContact.id); }}>{busyReturnBot ? "Devolvendo..." : "Devolver ao bot"}</button>
            ) : null}
          </CollapsibleCard>
          <CollapsibleCard title="Transferencia" defaultOpen={false}>
            <select value={toUserId} onChange={(e) => setToUserId(e.target.value ? Number(e.target.value) : "")}><option value="">Selecione um operador</option>{operators.filter((item) => item.id !== sessionUser!.id).map((item) => <option key={item.id} value={item.id}>{item.display_name} - {item.department_name || "Sem setor"}</option>)}</select>
            <select value={toDepartmentId} onChange={(e) => setToDepartmentId(e.target.value ? Number(e.target.value) : "")}><option value="">Manter departamento atual</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
            <input value={transferReason} onChange={(e) => setTransferReason(e.target.value)} placeholder="Motivo da transferencia" />
            <textarea value={transferSummary} onChange={(e) => setTransferSummary(e.target.value)} rows={3} placeholder="Resumo obrigatorio" />
            <button className="primary" onClick={() => void transferContact()} disabled={!toUserId || !transferSummary.trim() || busyTransfer}>{busyTransfer ? "Transferindo..." : "Transferir"}</button>
          </CollapsibleCard>
        </> : <div className="empty">As acoes do contato aparecem aqui.</div>}

        {isManagerRole ? (
          <CollapsibleCard title={sessionUser?.role === "admin" ? "Usuarios e Roles" : "Operadores"} defaultOpen={false}>
            <div className="admin-user-list">{operators.map((op) => (
              <div key={op.id} className="admin-user-row">
                <div className="admin-user-info"><strong>{op.display_name}</strong><span className="sub">{op.email || ""}</span></div>
                {sessionUser?.role === "admin" && editingUserId === op.id ? (
                  <div className="admin-user-edit">
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value)}><option value="admin">admin</option><option value="supervisor">supervisor</option><option value="operador">operador</option></select>
                    <select value={editDeptId} onChange={(e) => setEditDeptId(e.target.value ? Number(e.target.value) : "")}><option value="">Sem setor</option>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button className="primary" style={{ flex: 1, padding: "0.5rem" }} onClick={() => void saveUserRole(op.id)} disabled={busyRoleUpdate}>{busyRoleUpdate ? "..." : "Salvar"}</button>
                      <button className="ghost" style={{ padding: "0.5rem 0.7rem" }} onClick={() => setEditingUserId(null)}>✕</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <span className="chip" style={{ fontSize: "0.68rem" }}>{op.role}</span>
                    {sessionUser?.role === "admin" && <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} onClick={() => startEditUser(op)}>Editar</button>}
                    <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} disabled={busyResetCounter === op.id} onClick={() => void resetAssumeCounter(op.id, op.display_name)} title="Resetar contador">{busyResetCounter === op.id ? "..." : "Reset"}</button>
                  </div>
                )}
              </div>
            ))}</div>
          </CollapsibleCard>
        ) : null}

        {isManagerRole ? (
          <CollapsibleCard title="Reatribuicao em lote" defaultOpen={false}>
            <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Reatribuir todos os contatos de um operador:</span>
            <select value={bulkFromUser} onChange={(e) => setBulkFromUser(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecione operador de origem</option>
              {operators.map((op) => <option key={op.id} value={op.id}>{op.display_name}</option>)}
            </select>
            <select value={bulkAction} onChange={(e) => setBulkAction(e.target.value as "return_to_bot" | "transfer")}>
              <option value="return_to_bot">Devolver ao bot</option>
              <option value="transfer">Transferir para operador</option>
            </select>
            {bulkAction === "transfer" ? (
              <select value={bulkToUser} onChange={(e) => setBulkToUser(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Selecione operador destino</option>
                {operators.filter((op) => op.id !== bulkFromUser).map((op) => <option key={op.id} value={op.id}>{op.display_name}</option>)}
              </select>
            ) : null}
            <button className="primary" style={{ marginTop: "0.4rem" }} disabled={!bulkFromUser || (bulkAction === "transfer" && !bulkToUser) || busyBulk} onClick={() => { if (confirm("Reatribuir TODOS os contatos deste operador?")) void executeBulkReassign(); }}>{busyBulk ? "Processando..." : "Executar reatribuicao"}</button>
          </CollapsibleCard>
        ) : null}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// WhatsApp Embedded Signup (Coexistence)
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    fbAsyncInit?: () => void;
    FB?: {
      init: (params: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }) => void;
      login: (callback: (response: { authResponse?: { code?: string } }) => void, params: { config_id: string; response_type: string; override_default_response_type: boolean; extras: Record<string, unknown> }) => void;
    };
  }
}

function WhatsAppSignupModal() {
  const { bundle, setShowSettings } = useCrm();
  const [step, setStep] = useState<"loading" | "ready" | "signing" | "exchanging" | "done" | "error">("loading");
  const [signupConfig, setSignupConfig] = useState<{ app_id: string; config_id: string; graph_api_version: string } | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const fbLoaded = useRef(false);

  useEffect(() => {
    if (!bundle) return;
    getJson<{ app_id: string; config_id: string; graph_api_version: string }>(bundle.auth, "/api/admin/embedded-signup/config")
      .then((cfg) => {
        setSignupConfig(cfg);
        loadFacebookSDK(cfg.app_id, cfg.graph_api_version);
      })
      .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
  }, [bundle]);

  function loadFacebookSDK(appId: string, version: string) {
    if (fbLoaded.current || window.FB) {
      setStep("ready");
      return;
    }
    window.fbAsyncInit = () => {
      window.FB!.init({ appId, autoLogAppEvents: true, xfbml: false, version });
      fbLoaded.current = true;
      setStep("ready");
    };
    const script = document.createElement("script");
    script.src = "https://connect.facebook.net/pt_BR/sdk.js";
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    document.body.appendChild(script);
  }

  const launchSignup = useCallback(() => {
    if (!window.FB || !signupConfig) return;
    setStep("signing");
    window.FB.login(
      (response) => {
        const code = response.authResponse?.code;
        if (!code) {
          setErrorMsg("Signup cancelado ou nenhum codigo retornado.");
          setStep("error");
          return;
        }
        setStep("exchanging");
        sendJson<Record<string, unknown>>(bundle?.auth ?? null, "/api/admin/embedded-signup/exchange", { code, channel_type: "coexistence" })
          .then((data) => { setResult(data); setStep("done"); })
          .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
      },
      {
        config_id: signupConfig.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: "whatsapp_business_app_onboarding",
          sessionInfoVersion: "3",
        },
      },
    );
  }, [signupConfig, bundle]);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="WhatsApp Coexistence" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
        <h2 style={{ margin: "0 0 1.2rem" }}>WhatsApp Coexistence</h2>

        {step === "loading" && <p>Carregando configuracao...</p>}

        {step === "error" && (
          <div className="settings-section">
            <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "1rem", color: "#991b1b" }}>
              <strong>Erro:</strong> {errorMsg}
            </div>
            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => setStep("ready")}>Tentar novamente</button>
          </div>
        )}

        {step === "ready" && (
          <div className="settings-section">
            <p style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
              Conecte um numero do WhatsApp Business App ao CRM via Coexistence.
              O administrador do portfolio <strong>cliente</strong> deve fazer login no popup do Facebook.
            </p>
            <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginBottom: "1rem", fontSize: "0.9rem" }}>
              <strong>Requisitos:</strong>
              <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                <li>Numero ativo no WhatsApp Business App (Android/iOS)</li>
                <li>App versao 2.24.17 ou superior</li>
                <li>Portfolio do cliente verificado no Meta Business Manager</li>
                <li>Camera do celular pronta para escanear QR Code</li>
              </ul>
            </div>
            <button className="primary" style={{ fontSize: "1rem", padding: "0.75rem 1.5rem" }} onClick={launchSignup}>
              Iniciar Embedded Signup
            </button>
          </div>
        )}

        {step === "signing" && (
          <div className="settings-section" style={{ textAlign: "center" }}>
            <p>Aguardando conclusao do signup no popup do Facebook...</p>
            <p style={{ fontSize: "0.85rem", color: "#666" }}>Complete o fluxo no popup: login, selecao do WABA, e escaneamento do QR Code no celular.</p>
          </div>
        )}

        {step === "exchanging" && (
          <div className="settings-section" style={{ textAlign: "center" }}>
            <p>Trocando credenciais e configurando webhooks...</p>
          </div>
        )}

        {step === "done" && result && (
          <div className="settings-section">
            <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
              <strong>Conexao realizada com sucesso!</strong>
            </div>
            <table style={{ width: "100%", fontSize: "0.9rem", borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["WABA ID", result.waba_id],
                  ["Phone Number ID", result.phone_number_id],
                  ["Numero", result.display_phone_number],
                  ["Nome Verificado", result.verified_name],
                  ["Status", result.phone_status],
                  ["Plataforma", result.platform_type],
                  ["Qualidade", result.quality_rating],
                  ["Webhook", result.webhook_subscribed ? "Inscrito" : "Falhou"],
                ].map(([label, value]) => (
                  <tr key={String(label)}>
                    <td style={{ padding: "0.4rem 0.8rem 0.4rem 0", fontWeight: 600, whiteSpace: "nowrap" }}>{String(label)}</td>
                    <td style={{ padding: "0.4rem 0", fontFamily: "monospace" }}>{String(value ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginTop: "1rem", fontSize: "0.85rem" }}>
              <strong>Proximo passo:</strong> Atualize o <code>.env</code> do servidor com os novos valores:
              <pre style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>
{`WHATSAPP_TOKEN=${result.access_token || "???"}
WHATSAPP_PHONE_NUMBER_ID=${result.phone_number_id || "???"}
WHATSAPP_WABA_ID=${result.waba_id || "???"}`}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsModals() {
  const { showSettings, setShowSettings, sessionUser, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, saveUserSettingsAction, saveSystemSettingsAction } = useCrm();
  if (!sessionUser) return null;
  return (
    <>
      {showSettings === "chat" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Configuracoes do Chat" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Chat</h2>
            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              {systemSettings.chat_prefix_roles.includes(sessionUser.role) ? (
                <div className="settings-block">
                  <label className="settings-toggle"><input type="checkbox" checked={userSettings.chat_prefix_enabled} onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} /><span>Usar prefixo (ex: <strong>Rafael:</strong> Bom dia...)</span></label>
                  {userSettings.chat_prefix_enabled && <input value={userSettings.chat_prefix_name} onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_name: e.target.value }))} placeholder="Nome que aparecera como prefixo" style={{ marginTop: "0.5rem" }} />}
                </div>
              ) : <div className="empty" style={{ fontSize: "0.88rem" }}>Prefixo de mensagem nao habilitado para seu cargo.</div>}
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {showSettings === "quick" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Mensagens rapidas" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Mensagens rapidas</h2>
            <div className="settings-section">
              <h3>Minhas mensagens rapidas</h3>
              <div className="settings-block">
                {userSettings.quick_messages.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input value={qm.shortcut} onChange={(e) => { const u = [...userSettings.quick_messages]; u[idx] = { ...u[idx], shortcut: e.target.value }; setUserSettings((prev) => ({ ...prev, quick_messages: u })); }} placeholder="/atalho" style={{ width: 100 }} />
                    <input value={qm.message} onChange={(e) => { const u = [...userSettings.quick_messages]; u[idx] = { ...u[idx], message: e.target.value }; setUserSettings((prev) => ({ ...prev, quick_messages: u })); }} placeholder="Mensagem completa" style={{ flex: 1 }} />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => setUserSettings((prev) => ({ ...prev, quick_messages: prev.quick_messages.filter((_, i) => i !== idx) }))}>X</button>
                  </div>
                ))}
                {userSettings.quick_messages.length < systemSettings.quick_message_max ? (
                  <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => setUserSettings((prev) => ({ ...prev, quick_messages: [...prev.quick_messages, { shortcut: "", message: "" }] }))}>+ Adicionar mensagem rapida</button>
                ) : <div className="sub" style={{ fontSize: "0.82rem" }}>Limite de {systemSettings.quick_message_max} mensagens rapidas atingido.</div>}
              </div>
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {showSettings === "whatsapp" ? <WhatsAppSignupModal /> : null}

      {showSettings === "admin" && sessionUser.role === "admin" ? <AdminSettingsModal /> : null}

      {showSettings === "dashboard" && (sessionUser.role === "admin" || sessionUser.role === "supervisor") ? <DashboardModal /> : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Modal (audit metrics, export)
// ---------------------------------------------------------------------------

function DashboardModal() {
  const { bundle, setShowSettings, operators, setError } = useCrm();
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [ratings, setRatings] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDashboard = useCallback(async () => {
    if (!bundle) return;
    setLoading(true);
    try {
      const [sumRes, ratRes] = await Promise.all([
        getJson<Record<string, unknown>>(bundle.auth, `/api/admin/dashboard/summary?date_from=${dateFrom}&date_to=${dateTo}`),
        getJson<{ ratings: Record<string, unknown>[] }>(bundle.auth, `/api/admin/dashboard/ratings?date_from=${dateFrom}&date_to=${dateTo}`),
      ]);
      setSummary(sumRes);
      setRatings(ratRes.ratings || []);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setLoading(false);
  }, [bundle, dateFrom, dateTo, setError]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  const operatorName = (uid: unknown) => {
    const id = typeof uid === "number" ? uid : Number(uid);
    return operators.find((o) => o.id === id)?.display_name || `#${uid}`;
  };

  const exportCsv = useCallback(async () => {
    if (!bundle) return;
    try {
      const token = await bundle.auth.currentUser?.getIdToken();
      const resp = await fetch(`/api/admin/export?date_from=${dateFrom}&date_to=${dateTo}&format=csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `export_${dateFrom}_${dateTo}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }, [bundle, dateFrom, dateTo, setError]);

  const peakData = summary?.peak_chart as Record<string, number> | undefined;
  const peakSlots = peakData ? Object.entries(peakData).sort(([a], [b]) => a.localeCompare(b)) : [];
  const peakMax = peakSlots.length ? Math.max(...peakSlots.map(([, v]) => v)) : 1;
  const opsData = (summary?.operators || []) as { user_id: unknown; inbound: number; outbound: number; leads_assumed: number; first_activity: string | null; last_activity: string | null }[];

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Dashboard" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 750, maxHeight: "90vh", overflow: "auto" }}>
        <h2 style={{ margin: "0 0 0.8rem" }}>Dashboard de Auditoria</h2>

        {/* Date range */}
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap" }}>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <span>ate</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          <button className="primary" style={{ padding: "0.4rem 0.8rem" }} onClick={() => void loadDashboard()} disabled={loading}>{loading ? "..." : "Atualizar"}</button>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => void exportCsv()}>Exportar CSV</button>
        </div>

        {summary ? (
          <>
            {/* Summary cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.6rem", marginBottom: "1.2rem" }}>
              {([
                ["Leads recebidos", summary.total_leads_received],
                ["Leads assumidos", summary.total_leads_assumed],
                ["Msgs recebidas", summary.total_messages_inbound],
                ["Msgs enviadas", summary.total_messages_outbound],
                ["Total mensagens", summary.total_messages],
              ] as [string, unknown][]).map(([label, value]) => (
                <div key={label} style={{ background: "var(--card-bg, var(--bg-alt))", borderRadius: 8, padding: "0.8rem", textAlign: "center" }}>
                  <div style={{ fontSize: "1.6rem", fontWeight: 700 }}>{String(value ?? 0)}</div>
                  <div className="sub" style={{ fontSize: "0.75rem" }}>{label}</div>
                </div>
              ))}
            </div>

            {/* Peak chart (bar chart with CSS) */}
            {peakSlots.length > 0 && (
              <div className="settings-section" style={{ marginBottom: "1.2rem" }}>
                <h3>Pico de mensagens (por meia hora)</h3>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 100, overflow: "auto" }}>
                  {peakSlots.map(([slot, count]) => (
                    <div key={slot} style={{ flex: "0 0 auto", display: "flex", flexDirection: "column", alignItems: "center", minWidth: 28 }}>
                      <div style={{ width: 20, height: Math.max(2, (count / peakMax) * 80), background: "var(--accent)", borderRadius: "3px 3px 0 0" }} title={`${slot}: ${count}`} />
                      <span style={{ fontSize: "0.55rem", marginTop: 2, transform: "rotate(-45deg)", whiteSpace: "nowrap" }}>{slot}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Per-operator table */}
            {opsData.length > 0 && (
              <div className="settings-section" style={{ marginBottom: "1.2rem" }}>
                <h3>Por operador</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                    <thead><tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Operador</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Recebidas</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Enviadas</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Assumidos</th>
                    </tr></thead>
                    <tbody>
                      {opsData.map((op) => (
                        <tr key={String(op.user_id)} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "0.4rem" }}>{operatorName(op.user_id)}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.inbound}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.outbound}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.leads_assumed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Ratings table */}
            {ratings.length > 0 && (
              <div className="settings-section">
                <h3>Avaliacoes de atendimento</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                    <thead><tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Contato</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Nota</th>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Operador</th>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Data</th>
                    </tr></thead>
                    <tbody>
                      {ratings.map((r, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "0.4rem" }}>{String(r.display_name || r.wa_id || "")}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>
                            <span className="chip" style={{ fontSize: "0.75rem", background: Number(r.rating) >= 7 ? "var(--success)" : Number(r.rating) >= 4 ? "#e6a817" : "var(--danger)", color: "#fff" }}>{String(r.rating)}/10</span>
                          </td>
                          <td style={{ padding: "0.4rem" }}>{r.converted_by_user_id ? operatorName(r.converted_by_user_id) : "-"}</td>
                          <td style={{ padding: "0.4rem" }}>{String(r.rating_received_at || "").slice(0, 10)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : loading ? (
          <p className="sub">Carregando...</p>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin Settings Modal (departments, channels, system config)
// ---------------------------------------------------------------------------

function AdminSettingsModal() {
  const {
    bundle, setShowSettings, departments, channels, operators,
    systemSettings, setSystemSettings, busySettings, saveSystemSettingsAction,
    setError, setNotice,
  } = useCrm();
  const [adminTab, setAdminTab] = useState<"system" | "departments" | "channels" | "notifications">("system");

  // -- Department state --
  const [depts, setDepts] = useState<Department[]>(departments);
  const [newDeptName, setNewDeptName] = useState("");
  const [newDeptDesc, setNewDeptDesc] = useState("");
  const [editingDeptId, setEditingDeptId] = useState<number | null>(null);
  const [editDeptName, setEditDeptName] = useState("");
  const [editDeptDesc, setEditDeptDesc] = useState("");
  const [busyDept, setBusyDept] = useState(false);

  // -- Channel state --
  const [chans, setChans] = useState<Channel[]>(channels);

  useEffect(() => { setDepts(departments); }, [departments]);
  useEffect(() => { setChans(channels); }, [channels]);

  const reloadDepts = useCallback(async () => {
    if (!bundle) return;
    const res = await getJson<{ departments: Department[] }>(bundle.auth, "/api/departments");
    setDepts(res.departments);
  }, [bundle]);

  const reloadChans = useCallback(async () => {
    if (!bundle) return;
    const res = await getJson<{ channels: Channel[] }>(bundle.auth, "/api/admin/channels").catch(() => ({ channels: [] as Channel[] }));
    setChans(res.channels);
  }, [bundle]);

  const createDept = useCallback(async () => {
    if (!bundle || !newDeptName.trim()) return;
    setBusyDept(true);
    try {
      await sendJson(bundle.auth, "/api/admin/departments", { name: newDeptName.trim(), description: newDeptDesc.trim() });
      setNewDeptName(""); setNewDeptDesc("");
      await reloadDepts();
      setNotice("Departamento criado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, newDeptName, newDeptDesc, reloadDepts, setError, setNotice]);

  const saveDeptEdit = useCallback(async (deptId: number) => {
    if (!bundle || !editDeptName.trim()) return;
    setBusyDept(true);
    try {
      await putJson(bundle.auth, `/api/admin/departments/${deptId}`, { name: editDeptName.trim(), description: editDeptDesc.trim() });
      setEditingDeptId(null);
      await reloadDepts();
      setNotice("Departamento atualizado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, editDeptName, editDeptDesc, reloadDepts, setError, setNotice]);

  const deleteDept = useCallback(async (deptId: number) => {
    if (!bundle) return;
    setBusyDept(true);
    try {
      await deleteJson(bundle.auth, `/api/admin/departments/${deptId}`);
      await reloadDepts();
      setNotice("Departamento removido");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, reloadDepts, setError, setNotice]);

  const deactivateChannel = useCallback(async (channelId: number) => {
    if (!bundle) return;
    try {
      await deleteJson(bundle.auth, `/api/admin/channels/${channelId}`);
      await reloadChans();
      setNotice("Canal desativado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }, [bundle, reloadChans, setError, setNotice]);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Administracao" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <h2 style={{ margin: "0 0 1rem" }}>Administracao</h2>

        {/* Tabs */}
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.2rem", borderBottom: "1px solid var(--border)", paddingBottom: "0.5rem" }}>
          <button className={adminTab === "system" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("system")}>Sistema</button>
          <button className={adminTab === "departments" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("departments")}>Departamentos</button>
          <button className={adminTab === "channels" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("channels")}>Canais WhatsApp</button>
          <button className={adminTab === "notifications" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("notifications")}>Notificacoes</button>
        </div>

        {/* Tab: Sistema */}
        {adminTab === "system" && (
          <>
            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              <div className="settings-block"><label className="settings-toggle"><input type="checkbox" checked={systemSettings.chat_prefix_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} /><span>Habilitar prefixo de mensagem (padrao do sistema)</span></label></div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Cargos que podem usar prefixo:</span>
                {["admin", "supervisor", "operador"].map((role) => (
                  <label key={role} className="settings-toggle" style={{ marginBottom: "0.25rem" }}><input type="checkbox" checked={systemSettings.chat_prefix_roles.includes(role)} onChange={(e) => setSystemSettings((prev) => ({ ...prev, chat_prefix_roles: e.target.checked ? [...prev.chat_prefix_roles, role] : prev.chat_prefix_roles.filter((r) => r !== role) }))} /><span>{role}</span></label>
                ))}
              </div>
            </div>
            <div className="settings-section" style={{ marginTop: "1.2rem" }}>
              <h3>Mensagens rapidas</h3>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Limite por usuario:</span>
                <input type="number" min={1} max={100} value={systemSettings.quick_message_max} onChange={(e) => setSystemSettings((prev) => ({ ...prev, quick_message_max: Math.max(1, Number(e.target.value) || 1) }))} style={{ width: 100 }} />
              </div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Mensagens globais (padrao para todos):</span>
                {systemSettings.quick_messages_global.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input value={qm.shortcut} onChange={(e) => { const u = [...systemSettings.quick_messages_global]; u[idx] = { ...u[idx], shortcut: e.target.value }; setSystemSettings((prev) => ({ ...prev, quick_messages_global: u })); }} placeholder="/atalho" style={{ width: 100 }} />
                    <input value={qm.message} onChange={(e) => { const u = [...systemSettings.quick_messages_global]; u[idx] = { ...u[idx], message: e.target.value }; setSystemSettings((prev) => ({ ...prev, quick_messages_global: u })); }} placeholder="Mensagem completa" style={{ flex: 1 }} />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => setSystemSettings((prev) => ({ ...prev, quick_messages_global: prev.quick_messages_global.filter((_, i) => i !== idx) }))}>X</button>
                  </div>
                ))}
                <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => setSystemSettings((prev) => ({ ...prev, quick_messages_global: [...prev.quick_messages_global, { shortcut: "", message: "" }] }))}>+ Adicionar mensagem global</button>
              </div>
            </div>
            <div className="settings-section" style={{ marginTop: "1.2rem" }}>
              <h3>Bot de atendimento</h3>
              <div className="settings-block">
                <label className="settings-toggle">
                  <input type="checkbox" checked={systemSettings.bot_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, bot_enabled: e.target.checked }))} />
                  <span>Habilitar bot (coleta nome, equipamento e setor antes de encaminhar)</span>
                </label>
                <p className="sub" style={{ marginTop: "0.3rem", fontSize: "0.8rem" }}>Quando desabilitado, mensagens novas caem direto para "Novos".</p>
              </div>
            </div>
            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar configuracoes do sistema"}</button>
          </>
        )}

        {/* Tab: Departamentos */}
        {adminTab === "departments" && (
          <div className="settings-section">
            <h3>Departamentos</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {depts.map((dept) => (
                <div key={dept.id} className="admin-user-row" style={{ padding: "0.5rem 0.6rem" }}>
                  {editingDeptId === dept.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", flex: 1 }}>
                      <input value={editDeptName} onChange={(e) => setEditDeptName(e.target.value)} placeholder="Nome" />
                      <input value={editDeptDesc} onChange={(e) => setEditDeptDesc(e.target.value)} placeholder="Descricao (opcional)" />
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button className="primary" style={{ flex: 1, padding: "0.4rem" }} disabled={busyDept} onClick={() => void saveDeptEdit(dept.id)}>{busyDept ? "..." : "Salvar"}</button>
                        <button className="ghost" style={{ padding: "0.4rem 0.6rem" }} onClick={() => setEditingDeptId(null)}>Cancelar</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="admin-user-info">
                        <strong>{dept.name}</strong>
                        {dept.description ? <span className="sub">{dept.description}</span> : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.3rem" }}>
                        <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem" }} onClick={() => { setEditingDeptId(dept.id); setEditDeptName(dept.name); setEditDeptDesc(dept.description || ""); }}>Editar</button>
                        <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => { if (confirm(`Remover departamento "${dept.name}"?`)) void deleteDept(dept.id); }}>Remover</button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
            <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.4rem", borderTop: "1px solid var(--border)", paddingTop: "0.8rem" }}>
              <span className="sub">Novo departamento:</span>
              <input value={newDeptName} onChange={(e) => setNewDeptName(e.target.value)} placeholder="Nome do departamento" />
              <input value={newDeptDesc} onChange={(e) => setNewDeptDesc(e.target.value)} placeholder="Descricao (opcional)" />
              <button className="primary" style={{ padding: "0.5rem" }} disabled={!newDeptName.trim() || busyDept} onClick={() => void createDept()}>{busyDept ? "Criando..." : "Criar departamento"}</button>
            </div>
          </div>
        )}

        {/* Tab: Canais WhatsApp */}
        {adminTab === "channels" && (
          <div className="settings-section">
            <h3>Canais WhatsApp conectados</h3>
            {chans.length === 0 ? (
              <p className="sub">Nenhum canal configurado. Use o Embedded Signup para conectar um numero.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {chans.map((ch) => {
                  const owner = ch.owner_user_id ? operators.find((o) => o.id === ch.owner_user_id) : null;
                  return (
                    <div key={ch.id} className="admin-user-row" style={{ padding: "0.6rem" }}>
                      <div className="admin-user-info">
                        <strong>{ch.label}</strong>
                        <span className="sub">
                          {ch.display_phone_number || ch.phone_number_id}
                          {" | "}
                          <span className="chip" style={{ fontSize: "0.7rem" }}>{ch.channel_type === "standard" ? "Cloud API" : "Coexistence"}</span>
                          {ch.is_bot_enabled ? <span className="chip" style={{ fontSize: "0.7rem", marginLeft: "0.3rem" }}>Bot</span> : null}
                        </span>
                        {owner ? <span className="sub">Operador: {owner.display_name}</span> : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                        <span className="chip" style={{ fontSize: "0.7rem", background: ch.is_active ? "var(--success)" : "var(--danger)", color: "#fff" }}>
                          {ch.is_active ? "Ativo" : "Inativo"}
                        </span>
                        {ch.channel_type !== "standard" && (
                          <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => { if (confirm(`Desativar canal "${ch.label}"?`)) void deactivateChannel(ch.id); }}>Desativar</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "0.8rem" }}>
              <p className="sub">Para adicionar um canal coexistence, use a opcao <strong>WhatsApp Coexistence</strong> no menu de configuracoes.</p>
            </div>
          </div>
        )}

        {/* Tab: Notificacoes */}
        {adminTab === "notifications" && (
          <NotificationsTab />
        )}
      </div>
    </div>
  );
}

function NotificationsTab() {
  const { bundle, departments, systemSettings, setSystemSettings, busySettings, saveSystemSettingsAction, setError, setNotice } = useCrm();
  const [uploadingNotif, setUploadingNotif] = useState(false);
  const [uploadingAlarm, setUploadingAlarm] = useState(false);
  const notifFileRef = useRef<HTMLInputElement | null>(null);
  const alarmFileRef = useRef<HTMLInputElement | null>(null);

  const uploadSound = useCallback(async (file: File, kind: "alarm" | "notification") => {
    if (!bundle) return;
    const setter = kind === "alarm" ? setUploadingAlarm : setUploadingNotif;
    setter(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      const res = await sendForm<{ path: string }>(bundle.auth, "/api/admin/upload-alarm-sound", form);
      setSystemSettings((prev) => ({
        ...prev,
        [kind === "alarm" ? "alarm_sound_path" : "notification_sound_path"]: res.path,
      }));
      setNotice(`Som de ${kind === "alarm" ? "alarme" : "notificacao"} atualizado`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setter(false);
  }, [bundle, setError, setNotice, setSystemSettings]);

  const testSound = useCallback((path: string, fallbackFreq: number) => {
    if (path) {
      const audio = new Audio(path);
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } else {
      try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = fallbackFreq;
        osc.type = fallbackFreq > 800 ? "sine" : "square";
        gain.gain.value = 0.3;
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.stop(ctx.currentTime + 0.4);
        setTimeout(() => ctx.close(), 600);
      } catch { /* audio not available */ }
    }
  }, []);

  return (
    <>
      <div className="settings-section">
        <h3>Notificacao de nova mensagem</h3>
        <p className="sub" style={{ marginBottom: "0.6rem" }}>Todos os usuarios ouvem um beep quando chega uma nova mensagem.</p>
        <div className="settings-block">
          <label className="settings-toggle">
            <input type="checkbox" checked={systemSettings.notification_sound_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, notification_sound_enabled: e.target.checked }))} />
            <span>Habilitar som de notificacao</span>
          </label>
        </div>
        <div className="settings-block" style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.4rem" }}>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => notifFileRef.current?.click()} disabled={uploadingNotif}>
            {uploadingNotif ? "Enviando..." : systemSettings.notification_sound_path ? "Trocar som" : "Upload som personalizado"}
          </button>
          {systemSettings.notification_sound_path && <span className="sub" style={{ fontSize: "0.75rem" }}>Personalizado ativo</span>}
          <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => testSound(systemSettings.notification_sound_path, 880)} title="Testar som">Testar</button>
          {systemSettings.notification_sound_path && (
            <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => setSystemSettings((prev) => ({ ...prev, notification_sound_path: "" }))}>Usar padrao</button>
          )}
          <input ref={notifFileRef} type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/webm,.mp3,.wav,.ogg" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadSound(f, "notification"); }} />
        </div>
      </div>

      <div className="settings-section" style={{ marginTop: "1.2rem" }}>
        <h3>Alarme de mensagens sem resposta</h3>
        <p className="sub" style={{ marginBottom: "0.6rem" }}>Alarme sonoro repetitivo para operadores dos departamentos selecionados quando ha mensagens sem visualizar.</p>
        <div className="settings-block">
          <label className="settings-toggle">
            <input type="checkbox" checked={systemSettings.alarm_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, alarm_enabled: e.target.checked }))} />
            <span>Habilitar alarme</span>
          </label>
        </div>
        <div className="settings-block" style={{ marginTop: "0.6rem" }}>
          <span className="sub" style={{ display: "block", marginBottom: "0.3rem" }}>Tempo sem resposta (minutos):</span>
          <input type="number" min={1} max={60} value={systemSettings.alarm_threshold_minutes} onChange={(e) => setSystemSettings((prev) => ({ ...prev, alarm_threshold_minutes: Math.max(1, Number(e.target.value) || 5) }))} style={{ width: 100 }} />
        </div>
        <div className="settings-block" style={{ marginTop: "0.6rem" }}>
          <span className="sub" style={{ display: "block", marginBottom: "0.3rem" }}>Departamentos que recebem alarme:</span>
          {departments.map((dept) => (
            <label key={dept.id} className="settings-toggle" style={{ marginBottom: "0.25rem" }}>
              <input type="checkbox" checked={(systemSettings.alarm_department_ids || []).includes(dept.id)} onChange={(e) => setSystemSettings((prev) => ({
                ...prev,
                alarm_department_ids: e.target.checked
                  ? [...(prev.alarm_department_ids || []), dept.id]
                  : (prev.alarm_department_ids || []).filter((id) => id !== dept.id),
              }))} />
              <span>{dept.name}</span>
            </label>
          ))}
          {departments.length === 0 && <span className="sub">Nenhum departamento cadastrado.</span>}
        </div>
        <div className="settings-block" style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.6rem" }}>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => alarmFileRef.current?.click()} disabled={uploadingAlarm}>
            {uploadingAlarm ? "Enviando..." : systemSettings.alarm_sound_path ? "Trocar alarme" : "Upload alarme personalizado"}
          </button>
          {systemSettings.alarm_sound_path && <span className="sub" style={{ fontSize: "0.75rem" }}>Personalizado ativo</span>}
          <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => testSound(systemSettings.alarm_sound_path, 660)} title="Testar alarme">Testar</button>
          {systemSettings.alarm_sound_path && (
            <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => setSystemSettings((prev) => ({ ...prev, alarm_sound_path: "" }))}>Usar padrao</button>
          )}
          <input ref={alarmFileRef} type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/webm,.mp3,.wav,.ogg" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadSound(f, "alarm"); }} />
        </div>
      </div>

      <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar configuracoes de notificacao"}</button>
    </>
  );
}

function Lightbox() {
  const { lightboxMedia, closeLightbox } = useCrm();
  if (!lightboxMedia) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Visualizacao de midia" onClick={closeLightbox}>
      <button type="button" className="lightbox-close" onClick={closeLightbox} aria-label="Fechar visualizacao">Fechar</button>
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        {lightboxMedia.kind === "image" ? <img className="lightbox-media" src={lightboxMedia.src} alt={lightboxMedia.alt} /> : <video className="lightbox-media" src={lightboxMedia.src} controls={!lightboxMedia.gifLike} autoPlay loop={lightboxMedia.gifLike} muted={lightboxMedia.gifLike} playsInline />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main CRM layout
// ---------------------------------------------------------------------------

function CrmApp() {
  const { booting, config, firebaseUser, sessionUser, error } = useCrm();

  if (booting) return <BootScreen />;
  if (config?.auth_mode !== "firebase") return <div className="screen"><div className="hero-card"><p className="eyebrow">Configuracao invalida</p><h1>Este frontend exige Firebase Auth</h1><p>{error || "O backend deve operar em modo Firebase."}</p></div></div>;
  if (!firebaseUser || !sessionUser) return <LoginScreen />;

  return (
    <>
      <div className="crm-layout">
        <TopBar />
        <div className="crm-grid">
          <NavBar />
          <ContactList />
          <ChatPanel />
          <DetailPanel />
        </div>
      </div>
      <SettingsModals />
      <Lightbox />
    </>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <CrmProvider>
      <CrmApp />
    </CrmProvider>
  );
}
