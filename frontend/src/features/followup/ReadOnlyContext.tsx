import { useEffect, useId, useRef, useState } from "react";
import type { Auth } from "firebase/auth";
import { getJson } from "../../api";
import { WaText } from "../../components/chat/WaText";
import { formatMoment } from "./time";
import { requestError } from "./useOperation";
import { useAccessSignal } from "./useAccessSignal";

type Thread = { id: string; channel_label?: string; channel_id?: number; status?: string; assigned_to?: number | null };
type Message = { id: number | string; direction?: string; content?: string; msg_type?: string; filename?: string; media_path?: string; created_at?: string; timestamp_wa?: string | number; sender_name?: string; sent_by_name?: string };

export function ReadOnlyContext({ auth, contactId, conversationId }: { auth: Auth; contactId: number; conversationId?: string | null }) {
  const id = useId();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selected, setSelected] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  const contextReady = useRef(false);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const contextKey = `${contactId}/${conversationId || ""}/${reload}`;
  const accessSignal = useAccessSignal(contactId, selected || conversationId);

  useEffect(() => {
    let cancelled = false;
    contextReady.current = false; setLoadedFor(null);
    const request = ++generation.current;
    setLoading(true); setError(""); setMessages([]); setThreads([]); setSelected("");
    const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
    void getJson<{ conversations: Thread[] }>(auth, `/api/followup/contacts/${contactId}/context${query}`).then((response) => {
      if (cancelled || request !== generation.current) return;
      contextReady.current = true; setLoadedFor(contextKey);
      setThreads(response.conversations || []);
      setSelected(response.conversations?.[0]?.id || "");
      if (!response.conversations?.length) setLoading(false);
    }).catch((reason) => { if (!cancelled && request === generation.current) { generation.current++; contextReady.current = false; setLoadedFor(null); setMessages([]); setThreads([]); setSelected(""); setError(requestError(reason)); setLoading(false); } });
    return () => { cancelled = true; };
  }, [auth, contactId, conversationId, reload, contextKey]);

  useEffect(() => {
    if (!selected || !contextReady.current || loadedFor !== contextKey) return;
    let cancelled = false;
    const request = ++generation.current;
    setLoading(true); setMessages([]); setError("");
    void getJson<{ messages: Message[] }>(auth, `/api/followup/contacts/${contactId}/messages?conversation_id=${encodeURIComponent(selected)}&limit=50`).then((response) => {
      if (!cancelled && request === generation.current) setMessages(response.messages || []);
    }).catch((reason) => { if (!cancelled && request === generation.current) { generation.current++; contextReady.current = false; setLoadedFor(null); setMessages([]); setThreads([]); setSelected(""); setError(requestError(reason)); setLoading(false); } }).finally(() => { if (!cancelled && request === generation.current) setLoading(false); });
    return () => { cancelled = true; };
  }, [auth, contactId, selected, accessSignal, loadedFor, contextKey]);

  useEffect(() => {
    if (!selected || !contextReady.current || loadedFor !== contextKey) return;
    let cancelled = false;
    async function validate() {
      if (document.visibilityState !== "visible") return;
      const request = generation.current;
      try {
        await getJson(auth, `/api/followup/contacts/${contactId}/context?conversation_id=${encodeURIComponent(selected)}`);
      } catch (reason) {
        if (!cancelled && request === generation.current) { generation.current++; contextReady.current = false; setLoadedFor(null); setMessages([]); setThreads([]); setSelected(""); setError(requestError(reason)); setLoading(false); }
      }
    }
    void validate();
    const timer = window.setInterval(() => void validate(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [auth, contactId, selected, accessSignal, loadedFor, contextKey]);

  return <section className="fu-readonly" aria-labelledby={`${id}-title`}>
    <div className="fu-section-heading"><h4 id={`${id}-title`}>Contexto da conversa</h4><button className="fu-button" type="button" disabled={loading} onClick={() => setReload((value) => value + 1)}>Atualizar contexto</button></div>
    <p className="fu-help">Consulta sem assumir atendimento, enviar mensagem, registrar tentativa ou alterar a Val. Exibe até 50 mensagens recentes da conversa acessível.</p>
    {threads.length > 0 && <label className="fu-field" htmlFor={`${id}-thread`}><span>Conversa existente</span><select id={`${id}-thread`} value={selected} onChange={(event) => setSelected(event.target.value)}>{threads.map((thread) => <option key={thread.id} value={thread.id}>{thread.channel_label || `Canal ${thread.channel_id || thread.id}`}</option>)}</select></label>}
    {error && <p className="fu-notice fu-notice--danger" role="alert">{error}</p>}
    {loading ? <p role="status" className="fu-help">Carregando contexto…</p> : !threads.length && !error ? <p className="fu-help">Nenhuma conversa acessível. Nenhum atendimento foi criado.</p> : !messages.length && !error ? <p className="fu-help">Nenhuma mensagem acessível nesta conversa.</p> : <ol className="fu-context-messages">{messages.map((message) => {
      const rawTime = message.timestamp_wa;
      const numericTime = typeof rawTime === "number" ? rawTime : typeof rawTime === "string" && /^\d+$/.test(rawTime) ? Number(rawTime) : null;
      const timeValue = numericTime === null ? null : new Date(numericTime * (numericTime < 1e12 ? 1000 : 1));
      const timestamp = timeValue && Number.isFinite(timeValue.getTime()) ? timeValue.toISOString() : typeof rawTime === "string" ? rawTime : message.created_at;
      const safeMedia = message.media_path && (/^https:\/\//i.test(message.media_path) || /^\/(?!\/)/.test(message.media_path));
      return <li key={message.id} className={message.direction === "outbound" ? "fu-context-message--out" : ""}><small>{message.direction === "inbound" ? "Paciente" : message.sent_by_name || message.sender_name || (message.direction === "system" ? "Sistema" : "Equipe")} · {formatMoment(timestamp)}</small>{message.content ? <div><WaText text={message.content} /></div> : <p>{message.msg_type === "audio" ? "Áudio" : message.filename || message.msg_type || "Mensagem"}</p>}{safeMedia && <a href={message.media_path} target="_blank" rel="noopener noreferrer">Abrir {message.filename || "anexo"}</a>}</li>;
    })}</ol>}
  </section>;
}
