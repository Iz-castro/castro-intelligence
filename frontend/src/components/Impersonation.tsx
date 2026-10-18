import { useState, type ReactNode } from "react";
import { useCrm } from "../context/CrmContext";
import { impersonationTab } from "../firebase";
import { sendJson } from "../api";
import { errorText } from "../utils/errors";
import type { Operator } from "../types";

export const READ_ONLY_TOOLTIP = "Somente leitura (modo Ver como)";

export function ImpersonationLayout({ children }: { children: ReactNode }) {
  const { sessionUser, bundle, logout, impersonationLastUpdated, impersonationStale, impersonationRefreshing, impersonationPollIntervalMs, refreshPollingViews } = useCrm();
  const [ending, setEnding] = useState(false);
  if (!impersonationTab && !sessionUser?.impersonation) return <>{children}</>;
  const expires = sessionUser?.impersonation?.expires_at || bundle?.impersonationExpiresAt;
  const end = async () => {
    setEnding(true);
    const confirmed = await logout();
    // Mantem o aviso honesto visivel quando o servidor nao confirmou o fim.
    if (confirmed) window.close();
  };
  return (
    <div className="impersonation-layout">
      <div className="impersonation-banner" role="status">
        <span>Visualizando como <strong>{sessionUser?.display_name || "usuário"}</strong> — <strong>SOMENTE LEITURA</strong> — {expires ? `expira às ${new Date(expires).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : "sessão encerrada"}</span>
        <span className="impersonation-freshness">
          Atualização a cada {impersonationPollIntervalMs / 1000}s.
          {impersonationLastUpdated ? ` Última atualização ${new Date(impersonationLastUpdated).toLocaleTimeString("pt-BR")}.` : " Aguardando primeira leitura."}
          {impersonationStale ? " Algumas leituras falharam; dados desatualizados." : ""}
        </span>
        <div className="impersonation-actions">
          <button type="button" onClick={() => void refreshPollingViews()} disabled={ending || !sessionUser || impersonationRefreshing}>{impersonationRefreshing ? "Atualizando..." : "Atualizar"}</button>
          <button type="button" onClick={() => void end()} disabled={ending}>Encerrar</button>
        </div>
      </div>
      {children}
    </div>
  );
}

type Access = { custom_token: string; session_id: string; expires_at: string; target: { id: number; display_name: string; role: string } };

export function ImpersonateModal({ target, onClose }: { target: Operator; onClose: () => void }) {
  const { bundle } = useCrm();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // O link so existe nesta instancia do modal. Fechar descarta o segredo.
  const [access, setAccess] = useState<{ url: string; expiresAt: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const generate = async () => {
    if (!bundle || reason.trim().length < 10 || busy || access) return;
    setBusy(true); setError("");
    try {
      const result = await sendJson<Access>(bundle.auth, "/api/admin/impersonate", { user_id: target.id, reason: reason.trim() });
      setAccess({ url: `${window.location.origin}/#imp=${result.custom_token}`, expiresAt: result.expires_at });
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Ver como outro usuário" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose}>Fechar</button>
      <div className="settings-modal" style={{ maxWidth: 540 }} onClick={(e) => e.stopPropagation()}>
        <h2>Ver como {target.display_name}</h2>
        <p>Somente leitura. Este acesso é auditado para proteção dos dados pessoais.</p>
        {access ? <>
          <p>Expira às {new Date(access.expiresAt).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}. O link é mostrado uma única vez; feche este modal ao terminar.</p>
          <textarea readOnly value={access.url} rows={3} aria-label="Link de visualização" style={{ width: "100%", overflowWrap: "anywhere" }} />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.8rem" }}>
            <button type="button" className="ghost" onClick={() => { void navigator.clipboard.writeText(access.url).then(() => setCopied(true)).catch(() => setError("Não foi possível copiar. Selecione e copie o link.")); }}>{copied ? "Copiado" : "Copiar"}</button>
            <button type="button" className="primary" onClick={() => window.open(access.url, "_blank", "noopener")}>Abrir em nova aba</button>
          </div>
        </> : <form onSubmit={(e) => { e.preventDefault(); void generate(); }}>
          <label htmlFor="impersonate-reason">Motivo do acesso (mínimo de 10 caracteres)</label>
          <textarea id="impersonate-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} minLength={10} maxLength={200} required disabled={busy} autoFocus style={{ width: "100%", margin: "0.5rem 0" }} />
          <button type="submit" className="primary" disabled={busy || reason.trim().length < 10}>{busy ? "Gerando..." : "Gerar acesso"}</button>
        </form>}
        {error ? <div className="alert danger" role="alert">{error}</div> : null}
      </div>
    </div>
  );
}
