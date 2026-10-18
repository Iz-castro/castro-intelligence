import type { Auth } from "firebase/auth";
import { getJson, putJson, sendJson } from "../../api";
import type { ActionBody, FollowupActivity, FollowupSettings, FollowupTask, Page, TaskScope, TaskView } from "./types";

const BASE = "/api/followup";

export async function loadSettings(auth: Auth): Promise<FollowupSettings> {
  const response = await getJson<FollowupSettings | { settings: FollowupSettings }>(auth, `${BASE}/settings`);
  return "settings" in response ? response.settings : response;
}

export async function saveSettings(auth: Auth, settings: FollowupSettings, operationId: string): Promise<FollowupSettings> {
  const response = await putJson<FollowupSettings | { settings: FollowupSettings }>(auth, `${BASE}/settings`, {
    ...settings, operation_id: operationId,
  });
  return "settings" in response ? response.settings : response;
}

export async function loadTasks(auth: Auth, filters: {
  view?: TaskView; scope?: TaskScope; queue_key?: string; contact_id?: number | null; cursor?: string | null; group?: "all";
}): Promise<Page<FollowupTask>> {
  const query = new URLSearchParams({ limit: "30" });
  if (filters.view) query.set("view", filters.view);
  if (filters.group) { query.set("group", filters.group); query.set("status", "pending"); }
  if (filters.scope) query.set("scope", filters.scope);
  if (filters.queue_key) query.set("queue_key", filters.queue_key);
  if (filters.contact_id) query.set("contact_id", String(filters.contact_id));
  if (filters.cursor) query.set("cursor", filters.cursor);
  const response = await getJson<Page<FollowupTask> & { tasks?: FollowupTask[] }>(auth, `${BASE}/tasks?${query}`);
  return { ...response, items: response.items || response.tasks || [] };
}

export async function loadTask(auth: Auth, taskId: string): Promise<FollowupTask> {
  const response = await getJson<FollowupTask | { task: FollowupTask; eligible_assignees?: { id: number; display_name: string }[] }>(auth, `${BASE}/tasks/${encodeURIComponent(taskId)}`);
  return "task" in response ? { ...response.task, eligible_assignees: response.eligible_assignees || response.task.eligible_assignees } : response;
}

export async function loadActivities(auth: Auth, taskId: string, cursor?: string | null): Promise<Page<FollowupActivity>> {
  const query = new URLSearchParams({ limit: "30" });
  if (cursor) query.set("cursor", cursor);
  const response = await getJson<Page<FollowupActivity> & { activities?: FollowupActivity[] }>(auth,
    `${BASE}/tasks/${encodeURIComponent(taskId)}/activities?${query}`);
  return { ...response, items: response.items || response.activities || [] };
}

export async function createTask(auth: Auth, body: Record<string, unknown>, operationId: string): Promise<FollowupTask> {
  const response = await sendJson<{ task: FollowupTask }>(auth, `${BASE}/tasks`, { ...body, operation_id: operationId });
  return response.task;
}

export async function actOnTask(auth: Auth, taskId: string, body: ActionBody, operationId: string): Promise<FollowupTask> {
  const response = await sendJson<{ task: FollowupTask }>(auth, `${BASE}/tasks/${encodeURIComponent(taskId)}/actions`, {
    ...body, operation_id: operationId,
  });
  return response.task;
}

export function setCommercialPreference(auth: Auth, contactId: number, body: Record<string, unknown>, operationId: string) {
  return sendJson<Record<string, unknown>>(auth, `${BASE}/contacts/${contactId}/commercial-preference`, {
    ...body, operation_id: operationId,
  });
}

export type CommercialPreference = { active: boolean; version: number; updated_at?: string; actor_name?: string; reason?: string; source?: string };

export async function loadCommercialPreference(auth: Auth, contactId: number): Promise<CommercialPreference> {
  const response = await getJson<{ commercial_contact_block: CommercialPreference }>(auth, `${BASE}/contacts/${contactId}/commercial-preference`);
  return response.commercial_contact_block;
}
