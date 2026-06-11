import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { CrmProvider, useCrm } from "./context/CrmContext";
import { MoonIcon, SunIcon, GearIcon, PlusIcon, AddressBookIcon, PhotoIcon, VideoIcon, FileIcon, MapPinIcon, MicIcon, SendIcon, SearchIcon, DotsIcon, CloseIcon } from "./components/icons";
import { when, formatRecordingTime, messageTypeLabel, messageContentLabel, messageSenderLabel } from "./utils/formatting";
import { resolveMessageMedia } from "./utils/media";
import { playBeep } from "./utils/audio";
import { useClickOutside } from "./hooks/useClickOutside";
import { InternalChatPanel, GcBadgeIcon } from "./components/gchat/InternalChatPanel";
import { getJson, sendJson, putJson, deleteJson, sendForm } from "./api";
import type { Channel, ChatMessage, ConflictLead, Contact, Conversation, Department, Operator, ProtocolSearchResult, TemplateComponent, TemplateSendComponent, WhatsAppTemplate } from "./types";
import sussurroIcon from "./assets/sussurro-icon.png";

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
  const { config, bundle, busyLogin, error, loginWithGoogle, loginWithEmail } = useCrm();
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Entrar</h1>
      <p>{config?.allowed_email_domain ? `Use sua conta ${config.allowed_email_domain}.` : "Use uma conta Google autorizada."}</p>
      <button className="primary" onClick={() => void loginWithGoogle()} disabled={!bundle || busyLogin}>{busyLogin ? "Conectando..." : "Entrar com Google"}</button>
      <button className="ghost" style={{ marginTop: "0.6rem" }} onClick={() => setShowEmailForm((v) => !v)}>{showEmailForm ? "Ocultar email/senha" : "Entrar com email/senha"}</button>
      {showEmailForm && (
        <form style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.8rem" }} onSubmit={(e) => { e.preventDefault(); if (email.trim() && password) void loginWithEmail(email.trim(), password); }}>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" autoComplete="email" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="senha" autoComplete="current-password" />
          <button className="primary" type="submit" disabled={!bundle || busyLogin || !email.trim() || !password}>{busyLogin ? "Conectando..." : "Entrar"}</button>
        </form>
      )}
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
        <span className="sub">{sessionUser.email || sessionUser.username} · <span className="chip">{sessionUser.role}</span>{sessionUser.department_name ? <> · <span className="chip">{sessionUser.department_name}</span></> : null}</span>
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
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor" || !!sessionUser.coex_authorized) && <button type="button" className="attach-option" onClick={() => void openSettingsPage("whatsapp")}><span>📱</span><span>WhatsApp Coexistence</span></button>}
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor") && <button type="button" className="attach-option" onClick={() => void openSettingsPage("whatsapp-standard")}><span>☁️</span><span>Conectar numero (Cloud API)</span></button>}
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
  const { activeView, setActiveView, setQualificationFilter, setEquipeOperatorFilter, isManagerRole, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, backupUnread, systemSettings } = useCrm();
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
      {isManagerRole && <button className={`nav-item ${activeView === "backup" ? "active" : ""}`} onClick={() => { setActiveView("backup"); setQualificationFilter(""); }} title="Conversas em backup (historico importado)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/></svg>
        <span className="nav-label">Backup</span>
        {backupUnread > 0 && <span className="nav-badge">{backupUnread > 99 ? "99+" : backupUnread}</span>}
      </button>}
    </nav>
  );
}

type ContactPickerMode = "list" | "create";

function NewContactModal({ onClose }: { onClose: () => void }) {
  const { createManualContact, busyCreateContact, channels, loadAllContacts, openConversationForContact, operators, sessionUser, isManagerRole } = useCrm();
  const [mode, setMode] = useState<ContactPickerMode>("list");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const availableChannels = channels.filter(ch => ch.is_active);
  const [channelId, setChannelId] = useState<number | "">(availableChannels.length === 1 ? availableChannels[0].id : "");
  const [search, setSearchLocal] = useState("");
  const [allContacts, setAllContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(false);
  const [busyOpen, setBusyOpen] = useState(false);
  // Filtro de agenda por operador atribuido (so privilegiado ve a agenda toda):
  // null = Todos; sessionUser.id = "Meus"; outro id = carteira daquele operador.
  // Client-side sobre os contatos ja carregados — sem leitura extra no Firestore.
  const [ownerFilter, setOwnerFilter] = useState<number | null>(null);

  // Carrega contatos quando entra no modo list ou quando search muda (debounce).
  useEffect(() => {
    if (mode !== "list") return;
    let disposed = false;
    setLoadingList(true);
    const handle = window.setTimeout(async () => {
      const res = await loadAllContacts(search);
      if (disposed) return;
      setAllContacts(res.contacts);
      setTotal(res.total);
      setLoadingList(false);
    }, search ? 250 : 0);
    return () => { disposed = true; window.clearTimeout(handle); };
  }, [mode, search, loadAllContacts]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !phone.trim()) return;
    const result = await createManualContact(name.trim(), phone.trim(), channelId ? Number(channelId) : undefined);
    if (result) onClose();
  }

  async function handlePickContact(contact: Contact) {
    if (busyOpen) return;
    setBusyOpen(true);
    try {
      const channel = contact.channel_id || (availableChannels.length === 1 ? availableChannels[0].id : undefined);
      const convId = await openConversationForContact(contact.id, channel);
      if (convId) onClose();
    } finally {
      setBusyOpen(false);
    }
  }

  const visibleContacts = ownerFilter == null ? allContacts : allContacts.filter((c) => (c.assigned_to ?? null) === ownerFilter);

  if (mode === "create") {
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
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "space-between" }}>
              <button type="button" className="ghost" onClick={() => setMode("list")}>Voltar</button>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
                <button type="submit" className="primary" disabled={busyCreateContact || !name.trim() || !phone.trim()}>{busyCreateContact ? "Criando..." : "Criar contato"}</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Selecionar contato" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" style={{ width: "min(520px, 92vw)", maxHeight: "85vh", display: "flex", flexDirection: "column" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Total de contatos ({ownerFilter == null ? total : visibleContacts.length})</p>
        </div>
        <input
          value={search}
          onChange={(e) => setSearchLocal(e.target.value)}
          placeholder="Buscar contato por nome ou telefone"
          autoFocus
          style={{ marginBottom: "0.75rem" }}
        />
        <button
          type="button"
          className="primary"
          onClick={() => setMode("create")}
          style={{ width: "100%", marginBottom: "0.75rem" }}
        >
          + Novo contato
        </button>
        {isManagerRole && operators.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", marginBottom: "0.6rem" }}>
            <button type="button" className={ownerFilter === sessionUser?.id ? "primary" : "ghost"} style={{ padding: "0.25rem 0.6rem", fontSize: "0.72rem" }} onClick={() => setOwnerFilter(sessionUser?.id ?? null)}>Meus</button>
            {operators.filter((o) => o.id !== sessionUser?.id).map((o) => (
              <button key={o.id} type="button" className={ownerFilter === o.id ? "primary" : "ghost"} style={{ padding: "0.25rem 0.6rem", fontSize: "0.72rem" }} onClick={() => setOwnerFilter(o.id)} title={o.display_name}>{o.display_name.split(" ")[0]}</button>
            ))}
            <button type="button" className={ownerFilter == null ? "primary" : "ghost"} style={{ padding: "0.25rem 0.6rem", fontSize: "0.72rem" }} onClick={() => setOwnerFilter(null)}>Todos</button>
          </div>
        ) : null}
        <div style={{ flex: 1, overflowY: "auto", borderTop: "1px solid var(--border, #2a2f3a)", paddingTop: "0.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Contatos Salvos</p>
          {loadingList && allContacts.length === 0 ? (
            <p className="sub" style={{ padding: "0.5rem 0" }}>Carregando...</p>
          ) : visibleContacts.length === 0 ? (
            <p className="sub" style={{ padding: "0.5rem 0" }}>{search ? "Nenhum contato encontrado." : ownerFilter != null ? "Nenhum contato atribuido a este operador." : "Nenhum contato sincronizado."}</p>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {visibleContacts.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => handlePickContact(c)}
                    disabled={busyOpen}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "0.5rem 0.75rem",
                      background: "transparent",
                      border: "none",
                      borderBottom: "1px solid var(--border-soft, #1c2029)",
                      color: "inherit",
                      cursor: busyOpen ? "default" : "pointer",
                    }}
                  >
                    <div style={{ fontWeight: 500 }}>{c.display_name || c.declared_name || c.wa_id}</div>
                    <div className="sub">{c.phone_formatted || c.wa_id}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function ProtocolSearchCard() {
  // Fase 5A: busca por protocolo (admin/sup). Mostra Atendimento + timeline
  // do dia (todas as mensagens com aquele protocol_id).
  const { loadProtocol, operators } = useCrm();
  const [pid, setPid] = useState("");
  const [result, setResult] = useState<ProtocolSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const handleSearch = async () => {
    const trimmed = pid.trim();
    if (!trimmed) return;
    setLoading(true);
    setSearched(true);
    try { setResult(await loadProtocol(trimmed)); }
    finally { setLoading(false); }
  };
  const opName = (id?: number | null) => id != null ? (operators.find((o) => o.id === id)?.display_name || `#${id}`) : "—";
  return (
    <CollapsibleCard title="Buscar protocolo" defaultOpen={false}>
      <span className="sub" style={{ display: "block", marginBottom: "0.3rem", opacity: 0.75 }}>Formato: YYYYMMDD-{`{contact_id}`}-SETOR (ex.: 20260528-1870-VEN)</span>
      <div style={{ display: "flex", gap: "0.3rem" }}>
        <input value={pid} onChange={(e) => setPid(e.target.value)} placeholder="20260528-1870-VEN" style={{ flex: 1 }} />
        <button type="button" className="primary" onClick={() => void handleSearch()} disabled={loading || !pid.trim()}>{loading ? "..." : "Buscar"}</button>
      </div>
      {!loading && searched && !result ? (
        <div className="sub" style={{ opacity: 0.7, marginTop: "0.4rem" }}>Protocolo não encontrado.</div>
      ) : null}
      {result ? (
        <div style={{ marginTop: "0.5rem", fontSize: "0.75rem" }}>
          <div><strong>Lead:</strong> {result.contact?.display_name || `#${result.atendimento.contact_id}`} ({result.contact?.phone_formatted || result.contact?.wa_id || "—"})</div>
          <div><strong>Status:</strong> {result.atendimento.status}{result.atendimento.protocolo_informado ? " · ✓ protocolo informado" : " · ⚠ não informado"}</div>
          <div><strong>Setor:</strong> {result.atendimento.setor} · <strong>Dia:</strong> {result.atendimento.date}</div>
          {result.atendimento.fechado_por_user_id ? <div><strong>Fechado por:</strong> {opName(result.atendimento.fechado_por_user_id)}</div> : null}
          <div style={{ marginTop: "0.4rem" }}><strong>{result.count} mensagem(s)</strong></div>
          <div style={{ maxHeight: 260, overflowY: "auto", marginTop: "0.3rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            {result.messages.map((m) => {
              const accent = m.direction === "inbound" ? "#0ea5e9" : m.direction === "outbound" ? "#22c55e" : m.direction === "internal" ? "#facc15" : "#94a3b8";
              return (
                <div key={m.id} style={{ padding: "0.2rem 0.4rem", borderLeft: `3px solid ${accent}`, opacity: 0.95 }}>
                  <div className="sub" style={{ fontSize: "0.65rem", opacity: 0.7 }}>{when(m.timestamp_wa || m.created_at)} · {m.direction}</div>
                  <div style={{ fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>{(m.content || `[${m.msg_type}]`).slice(0, 200)}</div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </CollapsibleCard>
  );
}

function ReassignLeadCard() {
  // Fase 3B: reatribui SO o Dono do Lead; os atendimentos mantem seus donos.
  const { operators, sessionUser, reassignLead, busyTransfer } = useCrm();
  const [uid, setUid] = useState<number | "">("");
  const [reason, setReason] = useState("");
  return (
    <CollapsibleCard title="Reatribuir Lead (dono)" defaultOpen={false}>
      <span className="sub" style={{ display: "block", marginBottom: "0.3rem", opacity: 0.75 }}>Muda so o dono do Lead — os atendimentos abertos mantem seus donos.</span>
      <select value={uid} onChange={(e) => setUid(e.target.value ? Number(e.target.value) : "")}><option value="">Selecione o operador</option>{operators.filter((o) => o.id !== sessionUser?.id).map((o) => <option key={o.id} value={o.id}>{o.display_name}</option>)}</select>
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motivo (opcional)" />
      <button className="primary" onClick={() => { if (uid) { void reassignLead(Number(uid), null, reason, ""); setReason(""); setUid(""); } }} disabled={!uid || busyTransfer}>{busyTransfer ? "..." : "Reatribuir Lead"}</button>
    </CollapsibleCard>
  );
}

function ConflictsPanel() {
  // Fase 3A: Leads com >=2 atendimentos ativos de operadores distintos.
  // Read-only; clicar num atendimento abre a thread correspondente.
  const { loadConflicts, operators, setSelectedThreadId, setActiveView } = useCrm();
  const [conflicts, setConflicts] = useState<ConflictLead[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const refresh = async () => {
    setLoading(true);
    try { setConflicts(await loadConflicts()); setLoadedOnce(true); }
    catch { /* erro nao-fatal: mantem lista atual / vazia */ }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const opName = (id: number | null) => operators.find((o) => o.id === id)?.display_name || (id ? `#${id}` : "—");
  const jump = (conversationId: string) => { setActiveView("equipe"); setSelectedThreadId(conversationId); };
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
        <span className="sub">{loading ? "Carregando..." : `${conflicts.length} lead(s) em conflito`}</span>
        <button type="button" className="ghost" style={{ padding: "0.2rem 0.5rem", fontSize: "0.72rem" }} onClick={() => void refresh()} disabled={loading}>Atualizar</button>
      </div>
      {!loading && loadedOnce && conflicts.length === 0 ? (
        <div className="sub" style={{ opacity: 0.7 }}>Nenhum lead com 2+ atendimentos ativos de operadores distintos. ✓</div>
      ) : null}
      {conflicts.map((lead) => (
        <div key={lead.contact_id} className="admin-user-row" style={{ flexDirection: "column", alignItems: "stretch", gap: "0.3rem", padding: "0.5rem 0.6rem" }}>
          <div className="admin-user-info">
            <strong>{lead.display_name}</strong>
            <span className="sub">{lead.phone_formatted}{lead.phone_formatted ? " · " : ""}dono do lead: {opName(lead.lead_owner_user_id)}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
            {lead.conversations.map((cv) => (
              <button key={cv.conversation_id} type="button" className="ghost" style={{ display: "flex", justifyContent: "space-between", gap: "0.4rem", padding: "0.3rem 0.45rem", fontSize: "0.72rem", textAlign: "left" }} onClick={() => jump(cv.conversation_id)} title="Abrir este atendimento">
                <span>👤 {opName(cv.assigned_to)}</span>
                <span className="sub" style={{ whiteSpace: "nowrap" }}>{cv.channel_phone_number || cv.channel_label || "—"}{cv.channel_active === false ? " ⚠" : ""}{cv.unread ? ` · ${cv.unread} nao lida(s)` : ""}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ContactList() {
  const { activeView, filteredConversations, contactsById, selectedThreadId, setSelectedThreadId, search, setSearch, qualificationFilter, setQualificationFilter, equipeOperatorFilter, setEquipeOperatorFilter, operators, sessionUser, loadAllContacts } = useCrm();
  const [showNewContact, setShowNewContact] = useState(false);
  // Total de contatos do tenant (inclui agenda telefonica do state_sync,
  // nao apenas conversas ativas). Usado no header da sidebar.
  const [totalContacts, setTotalContacts] = useState(0);
  useEffect(() => {
    let disposed = false;
    void loadAllContacts().then((res) => {
      if (!disposed) setTotalContacts(res.total);
    });
    return () => { disposed = true; };
  }, [loadAllContacts]);
  const viewTitle = activeView === "bot" ? "Bot" : activeView === "novos" ? "Novos Leads" : activeView === "meus" ? "Meus Atendimentos" : activeView === "equipe" ? "Equipe" : activeView === "backup" ? "Backup" : "Nao Qualificados";

  // Render incremental: com ~3k conversas, montar 1000+ itens no DOM trava a
  // coluna. Renderiza em paginas de 50 ("Carregar mais"); o contador do header
  // segue sendo o total carregado. Reseta ao trocar de caixa/busca/filtro.
  const SIDEBAR_PAGE = 50;
  const [visibleLimit, setVisibleLimit] = useState(SIDEBAR_PAGE);
  useEffect(() => { setVisibleLimit(SIDEBAR_PAGE); }, [activeView, search, qualificationFilter, equipeOperatorFilter]);

  // Helper robusto: last_message_at pode vir como string ISO (do polling
  // /api/wa/conversations) OU como Firestore Timestamp object (do snapshot
  // direto). Converte ambos para epoch ms para ordenacao.
  const toMillis = (v: unknown): number => {
    if (!v) return 0;
    if (typeof v === "string") return new Date(v).getTime() || 0;
    if (typeof v === "number") return v;
    if (v instanceof Date) return v.getTime();
    if (typeof v === "object" && v !== null && typeof (v as { toDate?: () => Date }).toDate === "function") {
      return (v as { toDate: () => Date }).toDate().getTime();
    }
    if (typeof v === "object" && v !== null && "seconds" in v) {
      return Number((v as { seconds: number }).seconds) * 1000;
    }
    return 0;
  };
  type RenderItem = { contact: Contact; conversation: Conversation };
  // Fase 3.D: cada item da sidebar e uma Conversation. O Contact e
  // resolvido via contactsById (join in-memory). Mesmo wa_id em 2 canais
  // = 2 entradas distintas, com badge proprio do canal.
  const renderItems: RenderItem[] = filteredConversations
    .slice()
    .sort((a, b) => {
      // Canal oficial (standard) sempre acima dos coex; dentro de cada grupo,
      // mais recente primeiro.
      const pa = (a.channel_type || a.source_channel_type) === "standard" ? 0 : 1;
      const pb = (b.channel_type || b.source_channel_type) === "standard" ? 0 : 1;
      if (pa !== pb) return pa - pb;
      return toMillis(b.last_message_at) - toMillis(a.last_message_at);
    })
    .flatMap((conversation): RenderItem[] => {
      const contact = contactsById.get(conversation.contact_id);
      return contact ? [{ contact, conversation }] : [];
    });

  const visibleTeamOperators = activeView === "equipe"
    ? operators
      .filter((operator) => operator.id !== sessionUser?.id && filteredConversations.some((conv) => conv.assigned_to === operator.id))
      .sort((left, right) => left.display_name.localeCompare(right.display_name))
    : [];
  return (
    <aside className="panel sidebar">
      <div className={`panel-head ${activeView === "equipe" ? "panel-head--stacked" : ""}`}>
        <div>
          <p className="eyebrow">{viewTitle}</p>
          <h2>{renderItems.length} conversa{renderItems.length !== 1 ? "s" : ""}</h2>
          {totalContacts > 0 && activeView === "meus" ? (
            <p className="sub" style={{ marginTop: "0.15rem" }}>{totalContacts} contato{totalContacts !== 1 ? "s" : ""} cadastrado{totalContacts !== 1 ? "s" : ""}</p>
          ) : null}
        </div>
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
          <button type="button" className="composer-icon" style={{ width: 36, height: 36, flexShrink: 0 }} onClick={() => setShowNewContact(true)} title="Selecionar ou criar contato" aria-label="Selecionar contato"><AddressBookIcon /></button>
          <select className="compact" value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}><option value="">Todos</option><option value="novo">Novo</option><option value="em_atendimento">Em atend.</option><option value="qualificado">Qualificado</option><option value="convertido">Convertido</option></select>
        </>}
        {activeView === "equipe" && <select className="compact" value={equipeOperatorFilter} onChange={(e) => setEquipeOperatorFilter(e.target.value)}><option value="">Todos operadores</option>{operators.filter((op) => op.id !== sessionUser?.id).map((op) => <option key={op.id} value={String(op.id)}>{op.display_name}</option>)}</select>}
      </div>
      <div className="contact-list">
        {renderItems.slice(0, visibleLimit).map(({ contact, conversation }) => {
          // Fase 3.D: assigned/department vem da Conversation (cutover Fase 2C);
          // qualification/notes/avatar continuam no Contact.
          const assignedOperator = activeView === "equipe"
            ? (operators.find((o) => o.id === conversation.assigned_to) || null)
            : null;
          const accent = assignedOperator ? operatorColor(assignedOperator.id) : null;
          const lastMessageAt = conversation.last_message_at || contact.last_message_at;
          const unreadCount = conversation.unread_count ?? conversation.unread ?? 0;
          const channelLabel = conversation.channel_label || "";
          const channelType = conversation.channel_type || conversation.source_channel_type || contact.source_channel_type || "";
          const isActive = selectedThreadId === conversation.id;
          const handleClick = () => setSelectedThreadId(conversation.id);
          return (
            <button key={conversation.id} className={`contact ${isActive ? "active" : ""} ${accent ? "contact--team-accent" : ""}`} onClick={handleClick} style={operatorAccentStyle(accent)}>
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
                    <span>{when(lastMessageAt)}</span>
                  </div>
                </div>
                <div className="sub">{contact.phone_formatted || contact.wa_id}{activeView === "equipe" && assignedOperator ? ` · ${assignedOperator.display_name}` : ""}</div>
                <div className="row">
                  <span className="chip">{contact.qualification || "novo"}</span>
                  {unreadCount ? <b className="badge">{unreadCount}</b> : null}
                </div>
                {channelLabel ? (
                  <div style={{ marginTop: "0.2rem", maxWidth: "100%" }}>
                    <span className="chip" style={{ display: "inline-block", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", verticalAlign: "bottom", fontSize: "0.65rem", background: channelType === "coexistence" ? "#dbeafe" : "#dcfce7", color: channelType === "coexistence" ? "#1e40af" : "#166534" }} title={`${channelLabel}${channelType === "coexistence" ? " (Coexistence)" : " (Cloud API)"}`}>
                      {channelLabel}
                    </span>
                  </div>
                ) : channelType === "coexistence" ? (
                  <div style={{ marginTop: "0.2rem" }}>
                    <span className="chip" style={{ fontSize: "0.65rem", opacity: 0.7 }}>coex</span>
                  </div>
                ) : null}
              </div>
            </button>
          );
        })}
        {!renderItems.length ? <div className="empty">{activeView === "bot" ? "Nenhum contato no bot." : activeView === "novos" ? "Nenhum lead novo na fila." : activeView === "meus" ? "Nenhum atendimento ativo." : activeView === "equipe" ? "Nenhum atendimento da equipe." : activeView === "backup" ? "Nenhuma conversa em backup." : "Nenhum contato nao qualificado."}</div> : null}
        {renderItems.length > visibleLimit ? (
          <button type="button" className="ghost" style={{ margin: "0.5rem auto", display: "block" }} onClick={() => setVisibleLimit((v) => v + 100)}>
            Carregar mais ({renderItems.length - visibleLimit} restantes)
          </button>
        ) : null}
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
  const { activeView, operators, selectedContact, sessionUser, error, notice, config, messagesRef, scrollIntentRef, prevMessageCountRef, messages, selectedContactId, loadingMore, setLoadingMore, messageLimit, setMessageLimit, visibleMessages, visibleMessagesFiltered, showChatSearch, chatSearch, setChatSearch, toggleChatSearch, showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef, busyAssume, assumeContact, quickSuggestions, applyQuickMessage, replyTarget, startReplyToMessage, cancelReply, copyMessageText, draft, handleDraftChange, handleDraftKeyDown, submitText, recording, recordingSeconds, discardRecording, handlePrimaryAction, busySend, busyAudio, busyUpload, busyComposerAction, showAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, sendLocation, handleImageSelected, submitFile, imageInputRef, videoInputRef, documentInputRef, attachMenuRef, composerInputRef, correctionTarget, startCorrection, cancelCorrection, correctMessage, updateDeclaredName, conversations, selectedThreadId, takeoverConversation, returnConversation, internalMode, setInternalMode, supervisorTakeover, setAttendance } = { ...ctx, busyComposerAction: ctx.busyAudio || ctx.busySend };
  // Canal usado para listar templates: prioriza o canal da thread aberta
  // (mesma regra do _resolve_send_target no backend) sobre o canal do
  // contato, evitando WABA mismatch #132001 em cenarios de transferencia
  // ou contato cross-canal.
  const selectedThread = selectedThreadId ? conversations.find((c) => c.id === selectedThreadId) : null;
  const sendChannelId = selectedThread?.channel_id ?? selectedContact?.channel_id ?? null;
  const hasDraft = Boolean(draft.trim());
  const [editingNickname, setEditingNickname] = useState(false);
  const [nicknameInput, setNicknameInput] = useState("");
  const [openMessageMenuId, setOpenMessageMenuId] = useState<number | null>(null);
  const [openMessageMenuDirection, setOpenMessageMenuDirection] = useState<"down" | "up">("down");
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [busyTakeover, setBusyTakeover] = useState(false);
  const [showTakeoverPrompt, setShowTakeoverPrompt] = useState(false);
  const [greetDraft, setGreetDraft] = useState("");
  const activeMessageMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedOperator = activeView === "equipe" ? findAssignedOperator(selectedContact, operators) : null;
  const selectedOperatorColor = selectedOperator ? operatorColor(selectedOperator.id) : null;
  const noInboundWindow = selectedContact && !selectedContact.last_inbound_at;
  const isManualContact = selectedContact?.created_source === "manual";
  // Takeover temporario (coexistence): lead de outro operador escreveu neste numero.
  // O banner/prompt e uma acao do HANDLER (dono do numero onde o lead de outro
  // operador escreveu). So aparece para ele — nunca para o proprio dono do lead,
  // que senao veria "Este contato pertence a <ele mesmo>. Assuma..." ao abrir a
  // thread do canal do handler (o mesmo wa_id aparece em mais de um canal coex).
  const takeoverStatus = selectedThread?.takeover_status;
  const isTakeoverHandler =
    sessionUser?.id != null && selectedThread?.takeover_handler_user_id === sessionUser.id;
  // O dono do Lead nunca precisa "assumir" o proprio lead. Se eu sou dono do
  // Lead (mesmo sendo handler/dono do numero), o conflito acabou — evita o
  // banner/prompt de takeover stale apos reatribuir o Lead pra mim.
  const iAmLeadOwner = selectedContact?.assigned_to != null && sessionUser?.id === selectedContact.assigned_to;
  const isTakeoverPending = takeoverStatus === "pending" && isTakeoverHandler && !iAmLeadOwner;
  const isTakeoverActive = takeoverStatus === "active" && isTakeoverHandler && !iAmLeadOwner;
  const isManager = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";
  // Modo 2/3: admin/sup vendo thread que nao e dele (nem do lead dele) ->
  // intervindo como supervisao (envio assinado) e pode assumir.
  const iAmIntervening = isManager && selectedThread?.assigned_to != null && selectedThread.assigned_to !== sessionUser?.id && !iAmLeadOwner;
  // Fase 4 (ciclo de vida): ausente = aberto.
  const attendanceStatus = selectedThread?.attendance_status || "aberto";
  const attendanceClosed = attendanceStatus !== "aberto";
  const leadOwnerName = operators.find((o) => o.id === selectedThread?.lead_owner_user_id)?.display_name || "outro operador";
  // Faixa de contexto (visivel para todos): de quem e o lead, em que numero
  // a conversa vive, estado do takeover e qual o meu papel nesta thread.
  // Ajuda a debugar o cenario do mesmo wa_id em varios canais coex.
  const leadOwnerOp = operators.find((o) => o.id === selectedContact?.assigned_to);
  const leadOwnerLabel = leadOwnerOp?.display_name
    || (selectedContact?.assigned_to ? `#${selectedContact.assigned_to}` : "sem dono");
  const threadHandlerOp = operators.find((o) => o.id === selectedThread?.takeover_handler_user_id);
  const takeoverLabel = takeoverStatus === "pending"
    ? `pendente (handler: ${threadHandlerOp?.display_name || "?"})`
    : takeoverStatus === "active"
      ? `ativo (handler: ${threadHandlerOp?.display_name || "?"})`
      : "nenhum";
  const iOwnLead = selectedContact?.assigned_to != null && sessionUser?.id === selectedContact.assigned_to;
  const iOwnThread = selectedThread?.assigned_to != null && sessionUser?.id === selectedThread.assigned_to;
  const iAmActiveHandler = selectedThread?.takeover_status === "active"
    && selectedThread?.takeover_handler_user_id != null
    && sessionUser?.id === selectedThread.takeover_handler_user_id;
  const myThreadRole = iOwnLead ? "dono do lead"
    : iOwnThread ? "dono do atendimento"
    : iAmActiveHandler ? "handler (assumido)"
    : "observador";
  const channelInactive = selectedThread?.channel_active === false;
  const clientGreetName = selectedContact?.declared_name || selectedContact?.whatsapp_profile_name || "";
  const greetSuggestion = `Ola${clientGreetName ? " " + clientGreetName : ""}! Aqui e ${sessionUser?.display_name || "o atendimento"}. Vi no nosso sistema que voce costuma falar com ${leadOwnerName}. Como voce me chamou por aqui, como posso te ajudar hoje?`;
  const openTakeoverPrompt = () => { setGreetDraft(greetSuggestion); setShowTakeoverPrompt(true); };
  const confirmTakeover = async (withMessage: boolean) => { if (!selectedThreadId) return; setBusyTakeover(true); try { await takeoverConversation(selectedThreadId, withMessage ? greetDraft : undefined); setShowTakeoverPrompt(false); } finally { setBusyTakeover(false); } };
  const doReturn = async () => { if (!selectedThreadId) return; setBusyTakeover(true); try { await returnConversation(selectedThreadId); } finally { setBusyTakeover(false); } };
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
                    <button type="button" className="attach-option" onClick={() => { setShowTemplatePicker(true); closeDotsMenu(); }}><span>📋</span><span>Enviar template</span></button>
                    <div style={{ height: 1, background: "var(--border)", margin: "0.3rem 0.5rem" }} />
                    <button type="button" className="attach-option" onClick={() => { setNicknameInput(selectedContact.declared_name || ""); setEditingNickname(true); closeDotsMenu(); }}><span>✏️</span><span>Editar apelido</span></button>
                    {selectedThreadId ? <button type="button" className="attach-option" onClick={() => { void setAttendance(selectedThreadId, attendanceClosed ? "aberto" : "fechado_manual"); closeDotsMenu(); }}><span>{attendanceClosed ? "🔓" : "🔒"}</span><span>{attendanceClosed ? "Reabrir atendimento" : "Fechar atendimento"}</span></button> : null}
                    {selectedContact.attendance_protocol ? <button type="button" className="attach-option" onClick={() => { navigator.clipboard.writeText(selectedContact.attendance_protocol!).catch(() => {}); closeDotsMenu(); ctx.setNotice(`Protocolo copiado: ${selectedContact.attendance_protocol}`); }}><span>📋</span><span>Copiar protocolo</span></button> : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {selectedContact ? (
          <div className="sub" style={{ display: "flex", flexWrap: "wrap", gap: "0.2rem 1rem", padding: "0.35rem 1rem", fontSize: "0.72rem", borderBottom: "1px solid var(--border, rgba(0,0,0,0.08))", background: "var(--surface-2, rgba(0,0,0,0.03))" }}>
            <span>👤 Dono do lead: <strong>{leadOwnerLabel}</strong></span>
            {selectedThread ? <span>📱 Conversa no número: <strong>{selectedThread.channel_phone_number || "—"}</strong>{selectedThread.channel_label ? ` (${selectedThread.channel_label})` : ""}{channelInactive ? <strong style={{ color: "var(--danger, #c0392b)" }}> · ⚠ canal removido/antigo</strong> : null}</span> : null}
            <span>🔄 Takeover: <strong>{takeoverLabel}</strong></span>
            {attendanceClosed ? <span style={{ color: "var(--danger, #c0392b)" }}>🔒 <strong>{attendanceStatus === "fechado_inatividade" ? "fechado (inatividade)" : attendanceStatus === "fechado_cliente" ? "fechado (cliente)" : "fechado"}</strong></span> : null}
            {selectedContact.attendance_protocol ? <span>📄 <strong>{selectedContact.attendance_protocol}</strong></span> : null}
            <span>Você: <strong>{myThreadRole}</strong></span>
          </div>
        ) : null}

        {iAmIntervening ? (
          <div className="sub" style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 0.8rem", alignItems: "center", padding: "0.3rem 1rem", fontSize: "0.72rem", background: "rgba(250,204,21,0.12)", borderBottom: "1px solid var(--border, rgba(0,0,0,0.08))" }}>
            <span>👁️ Intervindo como supervisão — suas mensagens vão assinadas <strong>[Supervisão - {(sessionUser?.display_name || "").split(" ")[0]}]</strong>.</span>
            <button type="button" className="ghost" style={{ padding: "0.2rem 0.5rem", fontSize: "0.7rem", whiteSpace: "nowrap" }} disabled={busySend} onClick={() => { if (selectedThreadId) void supervisorTakeover(selectedThreadId); }}>Assumir como supervisor</button>
          </div>
        ) : null}

        {(isTakeoverPending || isTakeoverActive) ? (
          <div className={`alert ${isTakeoverPending ? "danger" : "success"}`} style={{ alignItems: "center", gap: "0.6rem" }}>
            <span style={{ flex: 1 }}>
              {isTakeoverPending
                ? <>Este contato pertence a <strong>{leadOwnerName}</strong>. Assuma para responder sem transferir o lead.</>
                : <>Voce assumiu este atendimento temporariamente — lead de <strong>{leadOwnerName}</strong>.</>}
            </span>
            {isTakeoverActive ? <button type="button" className="ghost" style={{ whiteSpace: "nowrap" }} disabled={busyTakeover} onClick={() => void doReturn()}>{busyTakeover ? "..." : "Encerrar e devolver"}</button> : null}
          </div>
        ) : null}

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
            const isInternal = message.direction === "internal";
            const canInteract = message.direction !== "system" && !isInternal;
            const isMenuOpen = openMessageMenuId === message.id;
            const bubbleOperator = activeView === "equipe" && message.direction === "outbound" ? findMessageOperator(message, operators, selectedContact) : null;
            const bubbleColor = bubbleOperator ? operatorColor(bubbleOperator.id) : null;
            return (
              <article key={message.id} className={`bubble ${message.direction} ${canInteract ? "has-actions" : ""} ${bubbleColor ? "bubble--team-accent" : ""}`} style={isInternal ? { background: "#fef9c3", borderColor: "#facc15", color: "#713f12" } : operatorAccentStyle(bubbleColor)}>
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
                <header><strong style={bubbleColor ? { color: bubbleColor } : undefined}>{messageSenderLabel(message)}{isInternal ? " · 🔒 nota interna" : ""}</strong><span>{when(message.timestamp_wa || message.created_at)}</span></header>
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

        {channelInactive ? (
          <div className="composer" style={{ padding: "0.8rem 1rem" }}>
            <div className="sub" style={{ textAlign: "center", width: "100%" }}>{selectedThread?.is_backup
              ? "📦 Conversa de backup (historico) — somente leitura. Transfira para um operador para atender quando o cliente voltar."
              : "⚠ Canal removido/antigo — somente leitura. Nao e possivel enviar por este atendimento."}</div>
          </div>
        ) : isTakeoverPending ? (
          <div className="composer" style={{ padding: "0.8rem 1rem", flexDirection: "column", gap: "0.5rem" }}>
            {showTakeoverPrompt ? (
              <>
                <span className="sub" style={{ width: "100%" }}>Mensagem ao cliente (opcional, editavel):</span>
                <textarea value={greetDraft} onChange={(e) => setGreetDraft(e.target.value)} rows={3} style={{ width: "100%", resize: "vertical" }} />
                <div style={{ display: "flex", gap: "0.5rem", width: "100%", flexWrap: "wrap" }}>
                  <button type="button" className="primary" style={{ flex: 1 }} disabled={busyTakeover} onClick={() => void confirmTakeover(true)}>{busyTakeover ? "..." : "Assumir e enviar"}</button>
                  <button type="button" className="ghost" disabled={busyTakeover} onClick={() => void confirmTakeover(false)}>Assumir sem mensagem</button>
                  <button type="button" className="ghost" disabled={busyTakeover} onClick={() => setShowTakeoverPrompt(false)}>Cancelar</button>
                </div>
              </>
            ) : (
              <>
                <div className="sub" style={{ textAlign: "center", width: "100%" }}>Contato de {leadOwnerName}. Assuma para responder sem transferir o lead.</div>
                <button type="button" className="assume-btn" style={{ background: "var(--danger)", borderColor: "var(--danger)" }} disabled={busyTakeover} onClick={openTakeoverPrompt}>Assumir atendimento temporariamente</button>
              </>
            )}
          </div>
        ) : noInboundWindow ? (
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
              {(sessionUser?.role === "admin" || sessionUser?.role === "supervisor") ? (
                <button type="button" className="composer-icon" onClick={() => setInternalMode(!internalMode)} title={internalMode ? "Modo interno ATIVO — cliente nao recebe" : "Nota interna (sussurro ao operador)"} aria-pressed={internalMode} style={internalMode ? { background: "#facc15" } : undefined}><img src={sussurroIcon} alt="" style={{ width: 22, height: 22, display: "block" }} /></button>
              ) : null}
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
              {recording ? <div className="recording-status"><span className="recording-dot" /><span>Gravando audio</span><strong>{formatRecordingTime(recordingSeconds)}</strong><button type="button" className="recording-cancel" onClick={discardRecording}>Cancelar</button></div> : <textarea ref={composerInputRef} value={draft} onChange={handleDraftChange} onKeyDown={handleDraftKeyDown} rows={1} placeholder={internalMode ? "Nota interna — o cliente nao ve" : "Digite uma mensagem"} disabled={busySend || busyAudio} style={internalMode ? { background: "#fef9c3" } : undefined} />}
            </div>
            <button type="button" className={`composer-icon mic-trigger ${recording ? "recording" : ""} ${hasDraft && !recording ? "send-ready" : ""}`} onClick={handlePrimaryAction} disabled={!selectedContact || busyUpload || busyComposerAction} aria-label={recording ? "Enviar audio gravado" : hasDraft ? "Enviar mensagem" : "Gravar audio"}>
              {busyComposerAction ? <span className="button-spinner" aria-hidden="true" /> : recording || hasDraft ? <SendIcon /> : <MicIcon />}
            </button>
          </div>
        </form>
        )}
      </> : <div className="empty large">Selecione um contato para abrir a conversa.</div>}
      {showTemplatePicker && selectedContact ? (
        <TemplatePickerModal
          contactId={selectedContact.id}
          channelId={sendChannelId}
          conversation={selectedThread ?? null}
          contact={selectedContact}
          onClose={() => setShowTemplatePicker(false)}
        />
      ) : null}
    </main>
  );
}

function countBodyPlaceholders(text: string): number {
  const matches = text.match(/\{\{\d+\}\}/g);
  return matches ? matches.length : 0;
}

function renderTemplatePreview(components: TemplateComponent[], vars: Record<string, string>): { header: string; body: string; footer: string; buttons: string[] } {
  let header = "";
  let body = "";
  let footer = "";
  const buttons: string[] = [];
  for (const c of components || []) {
    const type = String(c.type || "").toUpperCase();
    if (type === "HEADER" && c.format === "TEXT" && c.text) {
      header = c.text.replace(/\{\{(\d+)\}\}/g, (_, idx) => vars[`header_${idx}`] || `{{${idx}}}`);
    } else if (type === "BODY" && c.text) {
      body = c.text.replace(/\{\{(\d+)\}\}/g, (_, idx) => vars[`body_${idx}`] || `{{${idx}}}`);
    } else if (type === "FOOTER" && c.text) {
      footer = c.text;
    } else if (type === "BUTTONS" && c.buttons) {
      for (const b of c.buttons) {
        buttons.push(b.text || "");
      }
    }
  }
  return { header, body, footer, buttons };
}

// Detecta o template de reabertura por inatividade pelos botoes quick-reply
// (Retomar / Encerrar), robusto a variacoes do nome — a Meta gera o nome sem
// acentos (ex.: "atualizao_de_solicitao"). {{1}}/{{2}} sao preenchidos
// automaticamente; a resposta do cliente e' tratada no webhook.
function isReopenTemplate(t?: WhatsAppTemplate | null): boolean {
  if (!t) return false;
  const norm = (s: string) => s.toLowerCase();
  const buttonTexts = (t.components || [])
    .filter((c) => String(c.type).toUpperCase() === "BUTTONS")
    .flatMap((c) => (c.buttons || []).map((b) => norm(b.text || "")));
  return buttonTexts.some((x) => x.includes("retomar")) && buttonTexts.some((x) => x.includes("encerrar"));
}

function formatDateBR(raw?: string | null): string {
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric" });
}

function reopenFirstName(contact?: Contact | null): string {
  const name = (contact?.whatsapp_profile_name || contact?.declared_name || contact?.display_name || "").trim();
  return name ? name.split(/\s+/)[0] : "cliente";
}

function TemplatePickerModal({ contactId, channelId, conversation, contact, onClose }: { contactId: number; channelId: number | null; conversation?: Conversation | null; contact?: Contact | null; onClose: () => void }) {
  const { fetchTemplates, sendTemplate, reopenConversation, busyTemplate } = useCrm();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<"ALL" | "MARKETING" | "UTILITY" | "AUTHENTICATION">("ALL");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setLoadError("");
      const list = await fetchTemplates(channelId);
      if (!cancelled) {
        setTemplates(list);
        setLoading(false);
        if (!list.length) setLoadError("Nenhum template aprovado encontrado na WABA.");
      }
    })();
    return () => { cancelled = true; };
  }, [fetchTemplates, channelId]);

  const selected = selectedIdx !== null ? templates[selectedIdx] : null;
  const filtered = categoryFilter === "ALL" ? templates : templates.filter((t) => String(t.category).toUpperCase() === categoryFilter);
  const preview = selected ? renderTemplatePreview(selected.components || [], vars) : null;
  const conversationId = conversation?.id ?? null;
  const isReopen = isReopenTemplate(selected);
  const reopenName = reopenFirstName(contact);
  const reopenDate = formatDateBR(conversation?.last_message_at);

  // Discover placeholders once template selected
  const bodyComp = selected?.components?.find((c) => String(c.type).toUpperCase() === "BODY");
  const headerComp = selected?.components?.find((c) => String(c.type).toUpperCase() === "HEADER" && c.format === "TEXT");
  const bodyPlaceholders = bodyComp?.text ? countBodyPlaceholders(bodyComp.text) : 0;
  const headerPlaceholders = headerComp?.text ? countBodyPlaceholders(headerComp.text) : 0;

  function pickTemplate(idx: number) {
    setSelectedIdx(idx);
    const t = templates[idx];
    if (isReopenTemplate(t)) {
      // Reabertura: vars sao so para o preview; o backend recalcula e e a
      // fonte da verdade ao enviar via reopenConversation.
      setVars({ body_1: reopenFirstName(contact), body_2: formatDateBR(conversation?.last_message_at) });
    } else {
      setVars({});
    }
  }

  async function submit() {
    if (!selected) return;
    if (isReopen) {
      // {{1}}/{{2}} resolvidos no backend; nao envia components manuais.
      if (!conversationId) return;
      const ok = await reopenConversation(conversationId, selected.name, selected.language);
      if (ok) onClose();
      return;
    }
    const components: TemplateSendComponent[] = [];
    if (headerPlaceholders > 0) {
      const parameters = [];
      for (let i = 1; i <= headerPlaceholders; i += 1) {
        parameters.push({ type: "text" as const, text: vars[`header_${i}`] || "" });
      }
      components.push({ type: "header", parameters });
    }
    if (bodyPlaceholders > 0) {
      const parameters = [];
      for (let i = 1; i <= bodyPlaceholders; i += 1) {
        parameters.push({ type: "text" as const, text: vars[`body_${i}`] || "" });
      }
      components.push({ type: "body", parameters });
    }
    const ok = await sendTemplate({
      contactId,
      templateName: selected.name,
      language: selected.language,
      components: components.length ? components : undefined,
    });
    if (ok) onClose();
  }

  const canSubmit = selected && !busyTemplate && (
    isReopen
      ? !!conversationId
      : Array.from({ length: bodyPlaceholders }, (_, i) => `body_${i + 1}`).every((k) => (vars[k] || "").trim())
        && Array.from({ length: headerPlaceholders }, (_, i) => `header_${i + 1}`).every((k) => (vars[k] || "").trim())
  );

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enviar template" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 820, maxHeight: "85vh", overflow: "auto" }}>
        <h2 style={{ margin: "0 0 1rem" }}>Enviar template WhatsApp</h2>

        {loading ? <p>Carregando templates aprovados da Meta...</p> : null}
        {loadError ? (
          <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "0.8rem", color: "#991b1b", marginBottom: "1rem" }}>
            {loadError} Crie e aprove um template em <a href="https://business.facebook.com/wa/manage/message-templates" target="_blank" rel="noreferrer">WhatsApp Manager</a>.
          </div>
        ) : null}

        {!loading && templates.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1rem" }}>
            <div>
              <div style={{ display: "flex", gap: "0.3rem", marginBottom: "0.6rem", flexWrap: "wrap" }}>
                {(["ALL", "MARKETING", "UTILITY", "AUTHENTICATION"] as const).map((c) => (
                  <button key={c} type="button" className="chip" onClick={() => setCategoryFilter(c)} style={{ cursor: "pointer", opacity: categoryFilter === c ? 1 : 0.6 }}>{c}</button>
                ))}
              </div>
              <div style={{ maxHeight: "55vh", overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8 }}>
                {filtered.map((t, idx) => {
                  const globalIdx = templates.indexOf(t);
                  const active = globalIdx === selectedIdx;
                  return (
                    <button
                      key={`${t.name}-${t.language}`}
                      type="button"
                      onClick={() => pickTemplate(globalIdx)}
                      style={{
                        display: "block", width: "100%", textAlign: "left",
                        padding: "0.6rem 0.8rem",
                        border: "none",
                        borderBottom: idx < filtered.length - 1 ? "1px solid var(--border)" : "none",
                        background: active ? "var(--accent, #e0f2fe)" : "transparent",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{t.name}</div>
                      <div className="sub" style={{ fontSize: "0.72rem" }}>{t.category} · {t.language}</div>
                    </button>
                  );
                })}
                {filtered.length === 0 ? <p style={{ padding: "0.8rem", textAlign: "center" }} className="sub">Sem templates nessa categoria.</p> : null}
              </div>
            </div>

            <div>
              {selected ? (
                <>
                  <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.8rem", background: "#f9fafb", color: "#111", marginBottom: "1rem" }}>
                    <div style={{ fontSize: "0.7rem", marginBottom: "0.3rem", color: "#374151", fontWeight: 600 }}>Preview</div>
                    {preview?.header ? <div style={{ fontWeight: 600, marginBottom: "0.3rem", color: "#111" }}>{preview.header}</div> : null}
                    {preview?.body ? <div style={{ whiteSpace: "pre-wrap", fontSize: "0.9rem", color: "#111" }}>{preview.body}</div> : null}
                    {preview?.footer ? <div style={{ fontSize: "0.75rem", marginTop: "0.3rem", color: "#374151" }}>{preview.footer}</div> : null}
                    {preview?.buttons && preview.buttons.length > 0 ? (
                      <div style={{ display: "flex", gap: "0.3rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                        {preview.buttons.map((b, i) => <span key={i} className="chip" style={{ fontSize: "0.72rem", color: "#7a3f17" }}>{b}</span>)}
                      </div>
                    ) : null}
                  </div>

                  {isReopen ? (
                    <div style={{ marginBottom: "1rem", background: "#ecfdf5", border: "1px solid #6ee7b7", borderRadius: 8, padding: "0.7rem 0.8rem", color: "#065f46", fontSize: "0.8rem" }}>
                      <div style={{ fontWeight: 600, marginBottom: "0.3rem" }}>Preenchido automaticamente</div>
                      <div><strong>{`{{1}}`}</strong> nome do cliente — <strong>{reopenName}</strong></div>
                      <div><strong>{`{{2}}`}</strong> data da última conversa — <strong>{reopenDate || "—"}</strong></div>
                      {!conversationId ? <div style={{ color: "#b91c1c", marginTop: "0.4rem" }}>Abra a conversa do cliente para reabrir.</div> : null}
                    </div>
                  ) : (headerPlaceholders > 0 || bodyPlaceholders > 0) ? (
                    <div style={{ marginBottom: "1rem" }}>
                      <div className="sub" style={{ marginBottom: "0.4rem", fontWeight: 600 }}>Variáveis</div>
                      {Array.from({ length: headerPlaceholders }, (_, i) => i + 1).map((n) => (
                        <div key={`h-${n}`} style={{ marginBottom: "0.4rem" }}>
                          <label className="sub" style={{ fontSize: "0.75rem" }}>Cabeçalho {`{{${n}}}`}</label>
                          <input
                            style={{ width: "100%", padding: "0.4rem 0.6rem" }}
                            value={vars[`header_${n}`] || ""}
                            onChange={(e) => setVars((v) => ({ ...v, [`header_${n}`]: e.target.value }))}
                          />
                        </div>
                      ))}
                      {Array.from({ length: bodyPlaceholders }, (_, i) => i + 1).map((n) => (
                        <div key={`b-${n}`} style={{ marginBottom: "0.4rem" }}>
                          <label className="sub" style={{ fontSize: "0.75rem" }}>Corpo {`{{${n}}}`}</label>
                          <input
                            style={{ width: "100%", padding: "0.4rem 0.6rem" }}
                            value={vars[`body_${n}`] || ""}
                            onChange={(e) => setVars((v) => ({ ...v, [`body_${n}`]: e.target.value }))}
                          />
                        </div>
                      ))}
                    </div>
                  ) : <p className="sub" style={{ fontSize: "0.8rem" }}>Template sem variáveis.</p>}

                  <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                    <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
                    <button type="button" className="primary" onClick={() => void submit()} disabled={!canSubmit}>
                      {busyTemplate ? "Enviando..." : isReopen ? "Enviar reabertura" : "Enviar template"}
                    </button>
                  </div>
                </>
              ) : (
                <p className="sub">Selecione um template na lista à esquerda.</p>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
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
  const { bundle, selectedContact, selectedThreadId, conversations, sessionUser, isManagerRole, operators, departments, channels, qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary, busySave, busyTransfer, saveQualification, transferContact, editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole, coexEditingUserId, coexPhoneInput, setCoexPhoneInput, busyCoexUpdate, startEditCoex, cancelEditCoex, saveCoex, revokeCoex, setError, setNotice, refreshPollingViews } = useCrm();
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

  // V2 Fase 3: prioriza o canal da thread selecionada (selectedThreadId)
  // sobre o canal "primario" do contato. Se o usuario abriu a linha do
  // canal coexistence, o painel direito reflete esse canal.
  const selectedThread = selectedThreadId ? conversations.find((c) => c.id === selectedThreadId) : null;
  const threadChannelId = selectedThread?.channel_id ?? selectedContact?.channel_id ?? null;
  const contactChannel = threadChannelId ? channels.find((ch) => ch.id === threadChannelId) : null;

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
          <CollapsibleCard title="Transferir atendimento" defaultOpen={false}>
            <span className="sub" style={{ display: "block", marginBottom: "0.3rem", opacity: 0.75 }}>Move so este atendimento (thread). O Dono do Lead nao muda.</span>
            <select value={toUserId} onChange={(e) => setToUserId(e.target.value ? Number(e.target.value) : "")}><option value="">Selecione um operador</option>{operators.filter((item) => item.id !== sessionUser!.id).map((item) => <option key={item.id} value={item.id}>{item.display_name} - {item.department_name || "Sem setor"}</option>)}</select>
            <select value={toDepartmentId} onChange={(e) => setToDepartmentId(e.target.value ? Number(e.target.value) : "")}><option value="">Manter departamento atual</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
            <input value={transferReason} onChange={(e) => setTransferReason(e.target.value)} placeholder="Motivo da transferencia" />
            <textarea value={transferSummary} onChange={(e) => setTransferSummary(e.target.value)} rows={3} placeholder="Resumo obrigatorio" />
            <button className="primary" onClick={() => void transferContact()} disabled={!toUserId || !transferSummary.trim() || busyTransfer}>{busyTransfer ? "Transferindo..." : "Transferir"}</button>
          </CollapsibleCard>
          {isManagerRole ? <ReassignLeadCard /> : null}
        </> : <div className="empty">As acoes do contato aparecem aqui.</div>}

        {isManagerRole ? (
          <CollapsibleCard title="Conflitos de atendimento" defaultOpen={false}>
            <ConflictsPanel />
          </CollapsibleCard>
        ) : null}

        {isManagerRole ? <ProtocolSearchCard /> : null}

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
                ) : coexEditingUserId === op.id ? (
                  <div className="admin-user-edit">
                    <input type="tel" value={coexPhoneInput} onChange={(e) => setCoexPhoneInput(e.target.value)} placeholder="Numero coex (ex: 5531999990000)" />
                    <span className="sub" style={{ fontSize: "0.66rem", lineHeight: 1.3 }}>Numero corporativo que o operador vai conectar. Libera o Embedded Signup pra ele.</span>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button className="primary" style={{ flex: 1, padding: "0.5rem" }} onClick={() => void saveCoex(op.id)} disabled={busyCoexUpdate}>{busyCoexUpdate ? "..." : "Salvar"}</button>
                      {op.coex_authorized ? <button className="ghost" style={{ padding: "0.5rem 0.7rem", color: "var(--danger)" }} onClick={() => void revokeCoex(op.id)} disabled={busyCoexUpdate} title="Revogar autorizacao">⊘</button> : null}
                      <button className="ghost" style={{ padding: "0.5rem 0.7rem" }} onClick={() => cancelEditCoex()}>✕</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <span className="chip" style={{ fontSize: "0.68rem" }}>{op.role}</span>
                    {op.coex_authorized ? <span className="chip" style={{ fontSize: "0.62rem" }} title={op.coex_phone ? `Coex liberado: ${op.coex_phone}` : "Coex liberado"}>📱 Coex</span> : null}
                    {sessionUser?.role === "admin" && <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} onClick={() => startEditUser(op)}>Editar</button>}
                    {isManagerRole && <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} onClick={() => startEditCoex(op)} title="Autorizar WhatsApp coexistence do operador">Coex</button>}
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

function WhatsAppSignupModal({ channelType = "coexistence" }: { channelType?: "coexistence" | "standard" }) {
  const { bundle, setShowSettings } = useCrm();
  const isStandard = channelType === "standard";
  const [step, setStep] = useState<"loading" | "ready" | "signing" | "exchanging" | "done" | "error">("loading");
  const [signupConfig, setSignupConfig] = useState<{ app_id: string; config_id: string; graph_api_version: string } | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const fbLoaded = useRef(false);
  // Embedded Signup v4: a Meta entrega waba_id/phone_number_id na mensagem de
  // session-info (postMessage), NAO mais nos scopes do token. Capturado abaixo.
  const sessionInfoRef = useRef<{ phone_number_id?: string; waba_id?: string }>({});

  useEffect(() => {
    if (!bundle) return;
    getJson<{ app_id: string; config_id: string; graph_api_version: string }>(bundle.auth, `/api/admin/embedded-signup/config?type=${channelType}`)
      .then((cfg) => {
        setSignupConfig(cfg);
        loadFacebookSDK(cfg.app_id, cfg.graph_api_version);
      })
      .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
  }, [bundle, channelType]);

  // Captura a session-info do Embedded Signup (postMessage da Meta) com o
  // waba_id/phone_number_id do numero conectado. No v4 a WABA vem por aqui,
  // nao mais nos granular_scopes do token (que voltam so com public_profile).
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (typeof event.origin === "string" && !event.origin.endsWith("facebook.com")) return;
      let data: { type?: string; data?: { phone_number_id?: string; waba_id?: string } };
      try { data = typeof event.data === "string" ? JSON.parse(event.data) : event.data; } catch { return; }
      if (data && data.type === "WA_EMBEDDED_SIGNUP" && data.data) {
        if (data.data.phone_number_id) sessionInfoRef.current.phone_number_id = String(data.data.phone_number_id);
        if (data.data.waba_id) sessionInfoRef.current.waba_id = String(data.data.waba_id);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

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
    const sdkVersion = encodeURIComponent(version);
    const script = document.createElement("script");
    script.src = `https://connect.facebook.net/pt_BR/sdk.js?v=${sdkVersion}`;
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
        sendJson<Record<string, unknown>>(bundle?.auth ?? null, "/api/admin/embedded-signup/exchange", { code, channel_type: channelType, phone_number_id: sessionInfoRef.current.phone_number_id || "", waba_id: sessionInfoRef.current.waba_id || "" })
          .then((data) => { setResult(data); setStep("done"); })
          .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
      },
      {
        config_id: signupConfig.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: isStandard
          ? { setup: {}, sessionInfoVersion: "3" }
          : { setup: {}, featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" },
      },
    );
  }, [signupConfig, bundle, channelType, isStandard]);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={isStandard ? "Conectar numero (Cloud API)" : "WhatsApp Coexistence"} onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
        <h2 style={{ margin: "0 0 1.2rem" }}>{isStandard ? "Conectar numero oficial (Cloud API)" : "WhatsApp Coexistence"}</h2>

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
            {isStandard ? (
              <>
                <p style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
                  Conecte (ou migre) o numero oficial da empresa para a <strong>Cloud API</strong> como canal padrao.
                  O numero <strong>sai do app do WhatsApp Business</strong> e passa a ser gerenciado 100% pelo CRM.
                  Faca login no popup com a conta que administra a WABA.
                </p>
                <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginBottom: "1rem", fontSize: "0.9rem" }}>
                  <strong>Requisitos:</strong>
                  <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                    <li>Forma de pagamento ativa na WABA (linha de credito ou cartao)</li>
                    <li>Voce define o PIN de 6 digitos no popup (verificacao em 2 etapas)</li>
                    <li>O app do WhatsApp Business desconecta deste numero</li>
                  </ul>
                </div>
              </>
            ) : (
              <>
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
              </>
            )}
            <button className="primary" style={{ fontSize: "1rem", padding: "0.75rem 1.5rem" }} onClick={launchSignup}>
              {isStandard ? "Conectar numero (Cloud API)" : "Iniciar Embedded Signup"}
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
            {isStandard ? (
              <div style={{ background: "#eff6ff", border: "1px solid #93c5fd", borderRadius: 8, padding: "1rem", marginTop: "1rem", fontSize: "0.85rem" }}>
                <strong>Pronto.</strong> Canal standard criado. O envio usa o <strong>token do proprio canal</strong>.
                <br />NAO defina <code>WHATSAPP_TOKEN</code>/<code>WHATSAPP_PHONE_NUMBER_ID</code> no Cloud Run — deixe vazios para suportar mais de uma empresa (multi-tenant).
              </div>
            ) : (
              <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginTop: "1rem", fontSize: "0.85rem" }}>
                <strong>Proximo passo:</strong> Atualize o <code>.env</code> do servidor com os novos valores:
                <pre style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>
{`WHATSAPP_TOKEN=${result.access_token || "???"}
WHATSAPP_PHONE_NUMBER_ID=${result.phone_number_id || "???"}
WHATSAPP_WABA_ID=${result.waba_id || "???"}`}
                </pre>
              </div>
            )}
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
      {showSettings === "whatsapp-standard" ? <WhatsAppSignupModal channelType="standard" /> : null}

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
  const [newDeptBotKey, setNewDeptBotKey] = useState<string>("");
  const [editingDeptId, setEditingDeptId] = useState<number | null>(null);
  const [editDeptName, setEditDeptName] = useState("");
  const [editDeptDesc, setEditDeptDesc] = useState("");
  const [editDeptBotKey, setEditDeptBotKey] = useState<string>("");
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
      await sendJson(bundle.auth, "/api/admin/departments", {
        name: newDeptName.trim(),
        description: newDeptDesc.trim(),
        bot_key: newDeptBotKey || null,
      });
      setNewDeptName(""); setNewDeptDesc(""); setNewDeptBotKey("");
      await reloadDepts();
      setNotice("Departamento criado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, newDeptName, newDeptDesc, newDeptBotKey, reloadDepts, setError, setNotice]);

  const saveDeptEdit = useCallback(async (deptId: number) => {
    if (!bundle || !editDeptName.trim()) return;
    setBusyDept(true);
    try {
      await putJson(bundle.auth, `/api/admin/departments/${deptId}`, {
        name: editDeptName.trim(),
        description: editDeptDesc.trim(),
        bot_key: editDeptBotKey || null,
      });
      setEditingDeptId(null);
      await reloadDepts();
      setNotice("Departamento atualizado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, editDeptName, editDeptDesc, editDeptBotKey, reloadDepts, setError, setNotice]);

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
                      <label className="sub" style={{ fontSize: "0.75rem" }}>Setor do bot (roteamento automatico):</label>
                      <select value={editDeptBotKey} onChange={(e) => setEditDeptBotKey(e.target.value)}>
                        <option value="">Nenhum (nao recebe do bot)</option>
                        <option value="comercial">Comercial</option>
                        <option value="financeiro">Financeiro</option>
                        <option value="administrativo">Administrativo</option>
                        <option value="sac">SAC</option>
                      </select>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button className="primary" style={{ flex: 1, padding: "0.4rem" }} disabled={busyDept} onClick={() => void saveDeptEdit(dept.id)}>{busyDept ? "..." : "Salvar"}</button>
                        <button className="ghost" style={{ padding: "0.4rem 0.6rem" }} onClick={() => setEditingDeptId(null)}>Cancelar</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="admin-user-info">
                        <strong>{dept.name}</strong>
                        {dept.bot_key ? <span className="chip" style={{ fontSize: "0.65rem", marginLeft: "0.3rem" }}>bot: {dept.bot_key}</span> : null}
                        {dept.description ? <span className="sub">{dept.description}</span> : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.3rem" }}>
                        <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem" }} onClick={() => { setEditingDeptId(dept.id); setEditDeptName(dept.name); setEditDeptDesc(dept.description || ""); setEditDeptBotKey(dept.bot_key || ""); }}>Editar</button>
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
              <select value={newDeptBotKey} onChange={(e) => setNewDeptBotKey(e.target.value)}>
                <option value="">Setor do bot: Nenhum</option>
                <option value="comercial">Setor do bot: Comercial</option>
                <option value="financeiro">Setor do bot: Financeiro</option>
                <option value="administrativo">Setor do bot: Administrativo</option>
                <option value="sac">Setor do bot: SAC</option>
              </select>
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
      playBeep({ freq: fallbackFreq, type: fallbackFreq > 800 ? "sine" : "square", gain: 0.3, duration: 0.4 });
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

// Fase 2.10: banner persistente que avisa admin/supervisor quando o canal
// principal nao tem metodo de pagamento configurado na Meta. Sem isso,
// envio de templates de marketing/utility falha. Apenas roles
// admin/supervisor veem o banner.
function BillingHealthBanner() {
  const { sessionUser, channels, fetchBillingStatus } = useCrm();
  const [status, setStatus] = useState<{ ok: boolean; has_payment_method: boolean; error?: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const isPrivileged = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";
  const standardChannel = channels.find((c) => c.is_active && c.channel_type === "standard");

  useEffect(() => {
    if (!isPrivileged || !standardChannel) return;
    let cancelled = false;
    void fetchBillingStatus(standardChannel.id).then((res) => {
      if (!cancelled) setStatus(res);
    });
    return () => { cancelled = true; };
  }, [isPrivileged, standardChannel, fetchBillingStatus]);

  if (!isPrivileged || !standardChannel || !status || dismissed) return null;
  if (status.ok && status.has_payment_method) return null;
  // [Temporario] Castro Intelligence e Tech Provider (nao BSP), entao a consulta
  // de billing da Meta retorna #10 ("no permission") — erro COSMETICO: o envio
  // funciona via managed billing (Castro Operacoes). Suprime o banner de "nao
  // foi possivel verificar o billing". Mantem o alerta REAL (sem metodo de
  // pagamento). Reativar a verificacao se/quando virar BSP.
  if (!status.ok) return null;

  const isError = !status.ok;
  const message = isError
    ? `Nao foi possivel verificar o billing da Meta para o canal ${standardChannel.label}. ${status.error || ""}`
    : `O canal ${standardChannel.label} ainda nao tem metodo de pagamento configurado na Meta. Templates de marketing/utility nao serao entregues ate isso ser corrigido.`;

  return (
    <div style={{
      background: isError ? "#fef3c7" : "#fee2e2",
      borderBottom: `1px solid ${isError ? "#f59e0b" : "#dc2626"}`,
      color: isError ? "#92400e" : "#991b1b",
      padding: "0.6rem 1rem",
      display: "flex",
      gap: "0.8rem",
      alignItems: "center",
      justifyContent: "space-between",
      fontSize: "0.85rem",
    }}>
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <span style={{ fontSize: "1.1rem" }}>⚠</span>
        <span>{message}</span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <a
          href="https://business.facebook.com/wa/manage/billing/"
          target="_blank"
          rel="noreferrer"
          style={{ color: "inherit", textDecoration: "underline", fontWeight: 600 }}
        >
          Configurar agora
        </a>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          style={{ background: "transparent", border: "none", cursor: "pointer", color: "inherit", fontSize: "1rem", padding: "0 0.3rem" }}
          aria-label="Dispensar aviso"
          title="Dispensar"
        >
          ×
        </button>
      </div>
    </div>
  );
}


function CrmApp() {
  const { booting, config, firebaseUser, sessionUser, error } = useCrm();

  if (booting) return <BootScreen />;
  if (config?.auth_mode !== "firebase") return <div className="screen"><div className="hero-card"><p className="eyebrow">Configuracao invalida</p><h1>Este frontend exige Firebase Auth</h1><p>{error || "O backend deve operar em modo Firebase."}</p></div></div>;
  if (!firebaseUser || !sessionUser) return <LoginScreen />;

  return (
    <>
      <div className="crm-layout">
        <TopBar />
        <BillingHealthBanner />
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
