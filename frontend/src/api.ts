import type { Auth } from "firebase/auth";

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function buildHeaders(auth: Auth | null, initHeaders?: HeadersInit, isFormData = false) {
  const headers = new Headers(initHeaders || {});
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = auth?.currentUser ? await auth.currentUser.getIdToken() : "";
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function request<T>(auth: Auth | null, path: string, init: RequestInit = {}, isFormData = false): Promise<T> {
  const headers = await buildHeaders(auth, init.headers, isFormData);
  const response = await fetch(path, {
    ...init,
    headers,
  });

  const raw = await response.text();
  const payload = raw ? JSON.parse(raw) : {};
  if (!response.ok) {
    const message = payload.detail || payload.error || payload.message || `Erro HTTP ${response.status}`;
    throw new ApiError(String(message), response.status);
  }
  return payload as T;
}

export function getJson<T>(auth: Auth | null, path: string) {
  return request<T>(auth, path, { method: "GET" });
}

export function sendJson<T>(auth: Auth | null, path: string, body?: JsonValue | Record<string, unknown>) {
  return request<T>(auth, path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function putJson<T>(auth: Auth | null, path: string, body?: JsonValue | Record<string, unknown>) {
  return request<T>(auth, path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function deleteJson<T>(auth: Auth | null, path: string) {
  return request<T>(auth, path, { method: "DELETE" });
}

export function sendForm<T>(auth: Auth | null, path: string, formData: FormData) {
  return request<T>(auth, path, {
    method: "POST",
    body: formData,
  }, true);
}
