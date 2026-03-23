import type { ClientConfig } from "../types";

export function firebaseReady(config: ClientConfig | null) {
  if (!config) return false;
  const item = config.firebase_web_config;
  return Boolean(item.apiKey && item.authDomain && item.projectId && item.appId);
}
