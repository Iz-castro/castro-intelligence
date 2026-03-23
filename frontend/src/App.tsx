import { CrmProvider, useCrm } from "./context/CrmContext";
import { MoonIcon, SunIcon, GearIcon, PlusIcon, PhotoIcon, VideoIcon, FileIcon, MapPinIcon, MicIcon, SendIcon, SearchIcon, DotsIcon, CloseIcon } from "./components/icons";
import { when, formatRecordingTime, messageTypeLabel, messageContentLabel } from "./utils/formatting";
import { resolveMessageMedia } from "./utils/media";
import { useClickOutside } from "./hooks/useClickOutside";
import type { ChatMessage } from "./types";

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
  const { sessionUser, theme, toggleTheme, showSettings, setShowSettings, toggleSettingsMenu, openSettingsPage, settingsMenuRef, logout } = useCrm();
  useClickOutside(settingsMenuRef, showSettings === "menu", () => setShowSettings(false));
  if (!sessionUser) return null;
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
        <div ref={settingsMenuRef} style={{ position: "relative" }}>
          <button className="composer-icon" onClick={toggleSettingsMenu} title="Configuracoes" aria-label="Configuracoes"><GearIcon /></button>
          {showSettings === "menu" && (
            <div className="settings-dropdown">
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("chat")}><span>💬</span><span>Chat</span></button>
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("quick")}><span>⚡</span><span>Mensagens rapidas</span></button>
              {sessionUser.role === "admin" && <button type="button" className="attach-option" onClick={() => void openSettingsPage("admin")}><span>🔧</span><span>Administracao</span></button>}
            </div>
          )}
        </div>
        <button className="ghost" style={{ padding: "0.55rem 1rem", fontSize: "0.9rem" }} onClick={() => void logout()}>Sair</button>
      </div>
    </header>
  );
}

function NavBar() {
  const { activeView, setActiveView, setQualificationFilter, setEquipeOperatorFilter, isManagerRole, novosUnread, meusUnread, nqUnread, equipeUnread } = useCrm();
  return (
    <nav className="crm-nav">
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

function ContactList() {
  const { activeView, filteredContacts, selectedContactId, setSelectedContactId, search, setSearch, qualificationFilter, setQualificationFilter, equipeOperatorFilter, setEquipeOperatorFilter, operators, sessionUser } = useCrm();
  const viewTitle = activeView === "novos" ? "Novos Leads" : activeView === "meus" ? "Meus Atendimentos" : activeView === "equipe" ? "Equipe" : "Nao Qualificados";
  return (
    <aside className="panel sidebar">
      <div className="panel-head"><div><p className="eyebrow">{viewTitle}</p><h2>{filteredContacts.length} conversa{filteredContacts.length !== 1 ? "s" : ""}</h2></div></div>
      <div className="toolbar">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar contato" />
        {activeView === "meus" && <select className="compact" value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}><option value="">Todos</option><option value="novo">Novo</option><option value="em_atendimento">Em atend.</option><option value="qualificado">Qualificado</option><option value="convertido">Convertido</option></select>}
        {activeView === "equipe" && <select className="compact" value={equipeOperatorFilter} onChange={(e) => setEquipeOperatorFilter(e.target.value)}><option value="">Todos operadores</option>{operators.filter((op) => op.id !== sessionUser?.id).map((op) => <option key={op.id} value={String(op.id)}>{op.display_name}</option>)}</select>}
      </div>
      <div className="contact-list">{filteredContacts.map((contact) => <button key={contact.id} className={`contact ${selectedContactId === contact.id ? "active" : ""}`} onClick={() => setSelectedContactId(contact.id)}><div className="avatar">{contact.contact_avatar_path ? <img src={contact.contact_avatar_path} alt={contact.display_name} /> : <span>{contact.display_name.slice(0, 1).toUpperCase()}</span>}</div><div className="contact-copy"><div className="row"><strong>{contact.display_name}</strong><span>{when(contact.last_message_at)}</span></div><div className="sub">{contact.phone_formatted || contact.wa_id}{activeView === "equipe" && contact.assigned_name ? ` · ${contact.assigned_name}` : ""}</div><div className="row"><span className="chip">{contact.qualification || "novo"}</span>{contact.unread ? <b className="badge">{contact.unread}</b> : null}</div></div></button>)}{!filteredContacts.length ? <div className="empty">{activeView === "novos" ? "Nenhum lead novo na fila." : activeView === "meus" ? "Nenhum atendimento ativo." : activeView === "equipe" ? "Nenhum atendimento da equipe." : "Nenhum contato nao qualificado."}</div> : null}</div>
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

function ChatPanel() {
  const ctx = useCrm();
  const { selectedContact, sessionUser, error, notice, config, messagesRef, loadingMore, visibleMessages, visibleMessagesFiltered, showChatSearch, chatSearch, setChatSearch, toggleChatSearch, showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef, busyAssume, assumeContact, quickSuggestions, applyQuickMessage, draft, handleDraftChange, handleDraftKeyDown, submitText, recording, recordingSeconds, discardRecording, handlePrimaryAction, busySend, busyAudio, busyUpload, busyComposerAction, showAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, sendLocation, handleImageSelected, submitFile, imageInputRef, videoInputRef, documentInputRef, attachMenuRef, composerInputRef } = { ...ctx, busyComposerAction: ctx.busyAudio || ctx.busySend };
  const hasDraft = Boolean(draft.trim());

  return (
    <main className="panel chat-panel">
      {error ? <div className="alert danger">{error}</div> : null}
      {notice ? <div className="alert success">{notice}</div> : null}
      {selectedContact ? <>
        <div className="contact-banner">
          <div>
            <strong>{selectedContact.display_name}</strong>
            <div className="sub">{selectedContact.phone_formatted || selectedContact.wa_id} · {selectedContact.assigned_name || "Fila aberta"}</div>
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
                    <button type="button" className="attach-option" onClick={() => { if (selectedContact.attendance_protocol) navigator.clipboard.writeText(selectedContact.attendance_protocol).catch(() => {}); closeDotsMenu(); ctx.setNotice(`Protocolo copiado: ${selectedContact.attendance_protocol}`); }}><span>📋</span><span>Copiar protocolo</span></button>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {showChatSearch ? <div className="toolbar"><input value={chatSearch} onChange={(e) => setChatSearch(e.target.value)} placeholder="Buscar na conversa..." autoFocus />{chatSearch ? <span className="sub">{(visibleMessagesFiltered ?? []).length} resultado(s)</span> : null}</div> : null}

        <div className="messages" ref={messagesRef}>
          {loadingMore && <div className="sub" style={{ textAlign: "center", padding: "0.5rem" }}>Carregando mensagens anteriores...</div>}
          {(visibleMessagesFiltered ?? visibleMessages).map((message) => (
            <article key={message.id} className={`bubble ${message.direction}`}>
              <header><strong>{message.direction === "outbound" ? (message.operator_name || "Equipe") : message.direction === "inbound" ? "Cliente" : "Sistema"}</strong><span>{when(message.created_at || message.timestamp_wa)}</span></header>
              {messageContentLabel(message) ? <p>{messageContentLabel(message)}</p> : null}
              <MessageMedia message={message} />
              <footer><span>{messageTypeLabel(message.msg_type)}</span>{config?.feature_message_status !== false && <span>{message.status || "ok"}</span>}</footer>
            </article>
          ))}
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

        <form className="composer" onSubmit={submitText}>
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
      </> : <div className="empty large">Selecione um contato para abrir a conversa.</div>}
    </main>
  );
}

function DetailPanel() {
  const { selectedContact, sessionUser, operators, departments, qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary, busySave, busyTransfer, saveQualification, transferContact, editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole } = useCrm();
  return (
    <aside className="panel detail-panel">
      <div className="panel-head"><div><p className="eyebrow">Contato</p><h2>Operacao</h2></div><span className="sub">{operators.length} operadores - {departments.length} setores</span></div>
      <div className="detail-scroll">
        {selectedContact ? <>
          <section className="card">
            <h3>Qualificacao</h3>
            <select value={qualification} onChange={(e) => setQualification(e.target.value)}><option value="">Sem classificacao</option><option value="novo">Novo</option><option value="em_atendimento">Em atendimento</option><option value="qualificado">Qualificado</option><option value="nao_qualificado">Nao qualificado</option><option value="convertido">Convertido</option></select>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="Notas do atendimento" />
            <button className="primary" onClick={() => void saveQualification()} disabled={busySave}>{busySave ? "Salvando..." : "Salvar"}</button>
          </section>
          <section className="card">
            <h3>Transferencia</h3>
            <select value={toUserId} onChange={(e) => setToUserId(e.target.value ? Number(e.target.value) : "")}><option value="">Selecione um operador</option>{operators.filter((item) => item.id !== sessionUser!.id).map((item) => <option key={item.id} value={item.id}>{item.display_name} - {item.department_name || "Sem setor"}</option>)}</select>
            <select value={toDepartmentId} onChange={(e) => setToDepartmentId(e.target.value ? Number(e.target.value) : "")}><option value="">Manter departamento atual</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
            <input value={transferReason} onChange={(e) => setTransferReason(e.target.value)} placeholder="Motivo da transferencia" />
            <textarea value={transferSummary} onChange={(e) => setTransferSummary(e.target.value)} rows={4} placeholder="Resumo obrigatorio" />
            <button className="primary" onClick={() => void transferContact()} disabled={!toUserId || !transferSummary.trim() || busyTransfer}>{busyTransfer ? "Transferindo..." : "Transferir"}</button>
          </section>
        </> : <div className="empty">As acoes do contato aparecem aqui.</div>}

        {sessionUser?.role === "admin" ? (
          <section className="card">
            <h3>Usuarios e Roles</h3>
            <div className="admin-user-list">{operators.map((op) => (
              <div key={op.id} className="admin-user-row">
                <div className="admin-user-info"><strong>{op.display_name}</strong><span className="sub">{op.email || ""}</span></div>
                {editingUserId === op.id ? (
                  <div className="admin-user-edit">
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value)}><option value="admin">admin</option><option value="supervisor">supervisor</option><option value="operador">operador</option></select>
                    <select value={editDeptId} onChange={(e) => setEditDeptId(e.target.value ? Number(e.target.value) : "")}><option value="">Sem setor</option>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button className="primary" style={{ flex: 1, padding: "0.5rem" }} onClick={() => void saveUserRole(op.id)} disabled={busyRoleUpdate}>{busyRoleUpdate ? "..." : "Salvar"}</button>
                      <button className="ghost" style={{ padding: "0.5rem 0.7rem" }} onClick={() => setEditingUserId(null)}>✕</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="chip">{op.role}</span>
                    <button className="ghost" style={{ padding: "0.35rem 0.6rem", fontSize: "0.8rem" }} onClick={() => startEditUser(op)}>Editar</button>
                  </div>
                )}
              </div>
            ))}</div>
          </section>
        ) : null}
      </div>
    </aside>
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

      {showSettings === "admin" && sessionUser.role === "admin" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Administracao" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Administracao</h2>
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
            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar configuracoes do sistema"}</button>
          </div>
        </div>
      ) : null}
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
  if (config?.auth_mode !== "firebase") return <div className="screen"><div className="hero-card"><p className="eyebrow">Modo legado</p><h1>Este frontend exige Firebase Auth</h1><p>{error || "Defina AUTH_MODE=firebase para usar o CRM React."}</p></div></div>;
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
