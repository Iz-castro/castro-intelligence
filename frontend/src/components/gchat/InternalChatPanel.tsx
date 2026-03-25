import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query } from "firebase/firestore";
import { useCrm } from "../../context/CrmContext";
import { getJson, sendJson } from "../../api";
import type { GcConversation, GcMessage } from "../../types";
import { CloseIcon, SendIcon } from "../icons";

// ---------------------------------------------------------------------------
// InternalChatPanel - Slide-in panel for Google Chat integration
// ---------------------------------------------------------------------------

type PanelView = "conversations" | "chat";

export function InternalChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { bundle, sessionUser, config } = useCrm();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const [view, setView] = useState<PanelView>("conversations");
  const [conversations, setConversations] = useState<GcConversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<GcConversation | null>(null);
  const [messages, setMessages] = useState<GcMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const userEmail = sessionUser?.email || "";

  // Fetch conversations on open
  useEffect(() => {
    if (!open || !bundle?.auth) return;
    setLoading(true);
    getJson<{ conversations: GcConversation[] }>(bundle.auth, "/api/gc/conversations")
      .then((r) => setConversations(r.conversations))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, bundle?.auth]);

  // Firestore real-time for conversations list
  useEffect(() => {
    if (!open || !bundle?.db || !config?.firestore?.collections?.gc_conversations) return;
    const colName = config.firestore.collections.gc_conversations;
    const q = query(collection(bundle.db, colName), orderBy("last_message_at", "desc"), firestoreLimit(50));
    const unsub = onSnapshot(q, (snap) => {
      const items: GcConversation[] = snap.docs.map((doc) => {
        const d = doc.data();
        return {
          id: d.id ?? parseInt(doc.id, 10),
          space_id: d.space_id ?? "",
          space_name: d.space_name ?? "",
          participants: d.participants ?? [],
          last_message: d.last_message ?? "",
          last_message_at: d.last_message_at?.toDate?.()?.toISOString?.() ?? d.last_message_at ?? "",
          unread_count: d.unread_count ?? {},
          created_at: d.created_at?.toDate?.()?.toISOString?.() ?? d.created_at ?? "",
        };
      });
      setConversations(items);
    });
    return () => unsub();
  }, [open, bundle?.db, config?.firestore?.collections?.gc_conversations]);

  // Firestore real-time for messages of selected conversation
  useEffect(() => {
    if (!selectedConv || !bundle?.db || !config?.firestore?.collections?.gc_messages) return;
    const colName = config.firestore.collections.gc_messages;
    const q = query(
      collection(bundle.db, colName),
      orderBy("created_at", "desc"),
      firestoreLimit(100),
    );
    const unsub = onSnapshot(q, (snap) => {
      const items: GcMessage[] = snap.docs
        .map((doc) => {
          const d = doc.data();
          return {
            id: d.id ?? parseInt(doc.id, 10),
            conversation_id: d.conversation_id,
            gchat_message_id: d.gchat_message_id ?? "",
            sender_email: d.sender_email ?? "",
            sender_name: d.sender_name ?? "",
            msg_type: d.msg_type ?? "text",
            content: d.content ?? "",
            media_path: d.media_path ?? "",
            media_mime: d.media_mime ?? "",
            source: d.source ?? "google_chat",
            create_time: d.create_time?.toDate?.()?.toISOString?.() ?? d.create_time ?? "",
            created_at: d.created_at?.toDate?.()?.toISOString?.() ?? d.created_at ?? "",
          };
        })
        .filter((m) => m.conversation_id === selectedConv.id)
        .sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
      setMessages(items);
    });
    return () => unsub();
  }, [selectedConv, bundle?.db, config?.firestore?.collections?.gc_messages]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Mark as read when opening a conversation
  useEffect(() => {
    if (!selectedConv || !bundle?.auth) return;
    sendJson(bundle.auth, `/api/gc/mark-read/${selectedConv.id}`, {}).catch(() => {});
  }, [selectedConv, bundle?.auth]);

  const openConversation = useCallback((conv: GcConversation) => {
    setSelectedConv(conv);
    setView("chat");
    setMessages([]);
  }, []);

  const goBack = useCallback(() => {
    setView("conversations");
    setSelectedConv(null);
    setMessages([]);
    setDraft("");
  }, []);

  const handleSend = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || !selectedConv || busy || !bundle?.auth) return;
    setBusy(true);
    try {
      await sendJson(bundle.auth, "/api/gc/send", {
        conversation_id: selectedConv.id,
        content: draft.trim(),
      });
      setDraft("");
      inputRef.current?.focus();
    } catch {
      // Error handled silently — message won't appear in list
    } finally {
      setBusy(false);
    }
  }, [draft, selectedConv, busy, bundle?.auth]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }, [handleSend]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Delay to avoid closing on the same click that opened
    const timer = setTimeout(() => window.addEventListener("pointerdown", handler), 100);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("pointerdown", handler);
    };
  }, [open, onClose]);

  const getUnread = (conv: GcConversation) => {
    return conv.unread_count?.[userEmail] || 0;
  };

  const totalUnread = conversations.reduce((sum, c) => sum + getUnread(c), 0);

  const formatTime = (iso?: string) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    } catch { return ""; }
  };

  if (!open) return null;

  return (
    <div className={`gc-panel ${open ? "gc-panel--open" : ""}`} ref={panelRef}>
      {/* Header */}
      <div className="gc-panel__header">
        {view === "chat" && (
          <button className="gc-panel__back" onClick={goBack} title="Voltar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
        )}
        <h3 className="gc-panel__title">
          {view === "conversations" ? "Chat Interno" : selectedConv?.space_name || "Conversa"}
        </h3>
        <button className="gc-panel__close" onClick={onClose} title="Fechar"><CloseIcon /></button>
      </div>

      {/* Conversations list */}
      {view === "conversations" && (
        <div className="gc-panel__list">
          {loading && <div className="gc-panel__empty">Carregando...</div>}
          {!loading && conversations.length === 0 && (
            <div className="gc-panel__empty">
              Nenhuma conversa ainda.<br />
              Adicione o bot Hubloc CRM a um space no Google Chat.
            </div>
          )}
          {conversations.map((conv) => {
            const unread = getUnread(conv);
            return (
              <button key={conv.id} className="gc-conv-item" onClick={() => openConversation(conv)}>
                <div className="gc-conv-item__avatar">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="24" height="24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
                <div className="gc-conv-item__body">
                  <span className="gc-conv-item__name">{conv.space_name}</span>
                  <span className="gc-conv-item__preview">{conv.last_message || "Sem mensagens"}</span>
                </div>
                <div className="gc-conv-item__meta">
                  <span className="gc-conv-item__time">{formatTime(conv.last_message_at)}</span>
                  {unread > 0 && <span className="gc-conv-item__badge">{unread > 99 ? "99+" : unread}</span>}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Chat view */}
      {view === "chat" && selectedConv && (
        <>
          <div className="gc-panel__messages">
            {messages.length === 0 && <div className="gc-panel__empty">Nenhuma mensagem ainda.</div>}
            {messages.map((msg) => {
              const isMe = msg.source === "crm" || msg.sender_email === userEmail;
              return (
                <div key={msg.id} className={`gc-msg ${isMe ? "gc-msg--out" : "gc-msg--in"}`}>
                  {!isMe && <span className="gc-msg__sender">{msg.sender_name}</span>}
                  {msg.msg_type === "audio" && msg.media_path ? (
                    <audio controls src={msg.media_path} className="gc-msg__audio" />
                  ) : msg.msg_type === "image" && msg.media_path ? (
                    <img src={msg.media_path} alt="" className="gc-msg__image" />
                  ) : (
                    <span className="gc-msg__text">{msg.content}</span>
                  )}
                  <span className="gc-msg__time">{formatTime(msg.created_at)}</span>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          <form className="gc-panel__composer" onSubmit={(e) => void handleSend(e)}>
            <textarea
              ref={inputRef}
              className="gc-panel__input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Digite uma mensagem..."
              rows={1}
              disabled={busy}
            />
            <button type="submit" className="gc-panel__send" disabled={busy || !draft.trim()} title="Enviar">
              <SendIcon />
            </button>
          </form>
        </>
      )}
    </div>
  );
}

// Badge icon for TopBar
export function GcBadgeIcon({ totalUnread }: { totalUnread: number }) {
  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      {totalUnread > 0 && (
        <span className="gc-topbar-badge">{totalUnread > 99 ? "99+" : totalUnread}</span>
      )}
    </span>
  );
}
