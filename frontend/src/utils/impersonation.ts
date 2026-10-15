import { assertFirebaseSessionActive, type FirebaseBundle } from "../firebase";
import type { SessionPerfil } from "../types";

export type RawDocument = Record<string, unknown> & { id: string | number };
export type ImpersonationRead = { read_at: string; expires_at: string };
export type ImpersonationSnapshot = ImpersonationRead & {
  contact_groups: Record<string, RawDocument[]>;
  conversation_groups: Record<string, RawDocument[]>;
  contact_saturated: Record<string, boolean>;
  conversation_saturated: Record<string, boolean>;
  mine_load_more: boolean;
  perfil: SessionPerfil & { role: string };
};
export type ImpersonationPage = ImpersonationRead & { groups: Record<string, RawDocument[]>; saturated: Record<string, boolean> };
export type ImpersonationThread = ImpersonationRead & { conversation: RawDocument | null };

export function assertImpersonationRead(bundle: FirebaseBundle, result: ImpersonationRead) {
  assertFirebaseSessionActive(bundle.auth);
  const deadline = Date.parse(result.expires_at);
  if (!Number.isFinite(deadline) || deadline !== Date.parse(bundle.impersonationExpiresAt || "") || deadline <= Date.now()) {
    throw new Error("A sessao de visualizacao expirou.");
  }
}

export function threadReadParams(contactId: number, channelId?: number) {
  const params = new URLSearchParams({ contact_id: String(contactId) });
  if (channelId) params.set("channel_id", String(channelId));
  return params;
}
