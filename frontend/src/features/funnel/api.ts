import type { Auth } from "firebase/auth";
import { getJson, putJson, sendJson } from "../../api";
import type { PickerRow } from "../../types";
import type { BoardFilters, BoardResponse, ContactContext, ContactFunnel, ContactStageCheck, DashboardData, FunnelConfig, FunnelSettings, FunnelSettingsBody, HistoryPage, MoveStageBody, MoveStageResponse, StagePage } from "./types";

export const FUNNEL_BASE = "/api/funnel";

function boardQuery(filters: BoardFilters): URLSearchParams {
  const query = new URLSearchParams({ order: filters.order });
  // owner_id so para a gestao (o backend devolve 403 owner_filter_forbidden);
  // mine e para qualquer usuario. A UI nunca manda os dois.
  if (filters.ownerId != null) query.set("owner_id", String(filters.ownerId));
  else if (filters.mine) query.set("mine", "1");
  return query;
}

export function loadFunnelConfig(auth: Auth): Promise<FunnelConfig> {
  return getJson<FunnelConfig>(auth, `${FUNNEL_BASE}/config`);
}

export function loadBoard(auth: Auth, filters: BoardFilters): Promise<BoardResponse> {
  return getJson<BoardResponse>(auth, `${FUNNEL_BASE}/board?${boardQuery(filters)}`);
}

export function loadStageCards(auth: Auth, stage: string, filters: BoardFilters, cursor: string, limit = 20): Promise<StagePage> {
  const query = boardQuery(filters);
  query.set("cursor", cursor);
  query.set("limit", String(limit));
  return getJson<StagePage>(auth, `${FUNNEL_BASE}/stages/${encodeURIComponent(stage)}/cards?${query}`);
}

export function loadContactFunnel(auth: Auth, contactId: number): Promise<ContactFunnel> {
  return getJson<ContactFunnel>(auth, `${FUNNEL_BASE}/contacts/${contactId}`);
}

// Revalidacao do drawer a cada 30 s: so etapa, versao e escopo (barato). O
// GET completo acima so volta quando isto mostra mudanca.
export function loadContactStage(auth: Auth, contactId: number): Promise<ContactStageCheck> {
  return getJson<ContactStageCheck>(auth, `${FUNNEL_BASE}/contacts/${contactId}/stage`);
}

export function loadContactHistory(auth: Auth, contactId: number, cursor?: string | null): Promise<HistoryPage> {
  const query = cursor ? `?${new URLSearchParams({ cursor })}` : "";
  return getJson<HistoryPage>(auth, `${FUNNEL_BASE}/contacts/${contactId}/history${query}`);
}

export function loadContactContext(auth: Auth, contactId: number): Promise<ContactContext> {
  return getJson<ContactContext>(auth, `${FUNNEL_BASE}/contacts/${contactId}/context`);
}

export function moveContactStage(auth: Auth, contactId: number, body: MoveStageBody): Promise<MoveStageResponse> {
  return sendJson<MoveStageResponse>(auth, `${FUNNEL_BASE}/contacts/${contactId}/stage`, body);
}

// Aba "Etapas" (gerenciar_config_sistema): textos da clinica. PUT com a
// versao lida (409 stale_version = outra pessoa salvou antes).
export function loadFunnelSettings(auth: Auth): Promise<FunnelSettings> {
  return getJson<FunnelSettings>(auth, `${FUNNEL_BASE}/settings`);
}

export function saveFunnelSettings(auth: Auth, body: FunnelSettingsBody): Promise<Partial<FunnelSettings>> {
  return putJson<Partial<FunnelSettings>>(auth, `${FUNNEL_BASE}/settings`, body);
}

export function loadDashboard(auth: Auth, month: string, refresh = false): Promise<DashboardData> {
  const query = new URLSearchParams({ month, refresh: refresh ? "1" : "0" });
  return getJson<DashboardData>(auth, `${FUNNEL_BASE}/dashboard?${query}`);
}

// Busca do quadro = endpoint do picker v2.1 (escopo LGPD do backend). POST de
// proposito: nome/telefone do titular nunca em URL/log.
export function searchContacts(auth: Auth, term: string, limit = 20): Promise<{ contacts: PickerRow[]; truncated: boolean }> {
  return sendJson<{ contacts: PickerRow[]; truncated: boolean }>(auth, "/api/wa/contacts/picker/search", { q: term.slice(0, 120), limit });
}
