import type { Auth } from "firebase/auth";
import { assertFirebaseSessionActive, impersonationTab, stopImpersonationReading, trackImpersonationTask } from "./firebase";

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

let impersonationQueue: Promise<unknown> = Promise.resolve();
let impersonationReadGeneration = 0;
const impersonationControllers = new Set<AbortController>();

export function invalidateImpersonationReads() {
  if (!impersonationTab) return;
  impersonationReadGeneration += 1;
  for (const controller of impersonationControllers) controller.abort();
}

function request<T>(auth: Auth | null, path: string, init: RequestInit = {}, isFormData = false, binary = false): Promise<T> {
  const generation = impersonationReadGeneration;
  if (impersonationTab && auth && path !== "/api/impersonation/end") {
    // Uma consulta por vez, inclusive entre paineis e mudancas de selecao.
    const queued = impersonationQueue.then(() => performRequest<T>(auth, path, init, isFormData, binary, generation));
    // A fila guarda apenas conclusao, nunca o ultimo payload recebido.
    impersonationQueue = queued.then(() => undefined, () => undefined);
    return queued;
  }
  return performRequest<T>(auth, path, init, isFormData, binary, generation);
}

async function performRequest<T>(auth: Auth | null, path: string, init: RequestInit = {}, isFormData = false, binary = false, generation = impersonationReadGeneration): Promise<T> {
  const endingOwnSession = path === "/api/impersonation/end" && init.method === "POST";
  const controller = impersonationTab && auth && !endingOwnSession ? new AbortController() : null;
  if (controller) impersonationControllers.add(controller);
  const abort = () => controller?.abort();
  const release = controller ? trackImpersonationTask(abort) : () => {};
  if (init.signal?.aborted) abort();
  else init.signal?.addEventListener("abort", abort, { once: true });
  const assertCurrent = () => {
    if (endingOwnSession) return;
    assertFirebaseSessionActive(auth);
    if (impersonationTab && auth && generation !== impersonationReadGeneration) throw new DOMException("Leitura descartada após mudança de permissões.", "AbortError");
  };
  try {
    assertCurrent();
    const headers = await buildHeaders(auth, init.headers, isFormData);
    assertCurrent();
    const response = await fetch(path, {
      ...init,
      signal: controller?.signal || init.signal,
      headers,
    });
    if (binary && response.ok) {
      const blob = await response.blob();
      assertCurrent();
      return blob as T;
    }
    const raw = await response.text();
    assertCurrent();
    if (impersonationTab && auth && response.status === 401 && !endingOwnSession) stopImpersonationReading("A sessão de visualização ficou inválida e foi encerrada.");
    let payload: Record<string, unknown> = {};
    try { payload = raw ? JSON.parse(raw) : {}; }
    catch { if (response.ok) throw new ApiError("Resposta inválida do servidor.", response.status); }
    if (!response.ok) {
      const detail = payload.detail || payload.error || payload.message || `Erro HTTP ${response.status}`;
      // 422 do FastAPI manda detail como ARRAY de erros de validacao.
      const message = Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d?.msg || "Valor invalido").join("; ")
        : detail;
      throw new ApiError(String(message), response.status);
    }
    return payload as T;
  } finally {
    if (controller) impersonationControllers.delete(controller);
    release();
    init.signal?.removeEventListener("abort", abort);
  }
}

export function getJson<T>(auth: Auth | null, path: string, options: { signal?: AbortSignal } = {}) {
  return request<T>(auth, path, { method: "GET", ...options });
}

export function getDownload(auth: Auth, path: string) {
  return request<Blob>(auth, path, { method: "GET" }, false, true);
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

export async function endImpersonationRequest(auth: Auth) {
  const controller = new AbortController();
  let timeoutId: number | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => {
      controller.abort();
      reject(new Error("Encerramento no servidor não confirmado."));
    }, 5000);
  });
  try {
    await Promise.race([request(auth, "/api/impersonation/end", { method: "POST", signal: controller.signal }), timeout]);
  } finally { window.clearTimeout(timeoutId); }
}
