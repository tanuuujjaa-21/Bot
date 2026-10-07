// Single place that talks to the FastAPI backend.

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "noobsync.token";

export interface User {
  id: number;
  name: string;
  phone: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface MessageSource {
  type: "uploaded_document" | "rag_pipeline" | "none";
  files: string[];
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  source: MessageSource | null;
  latency_ms: number | null;
  created_at: string;
}

export type DocStatus = "processing" | "ready" | "error";

export interface DocumentInfo {
  id: string;
  filename: string;
  ext: string;
  size_bytes: number;
  chunk_count: number;
  status: DocStatus;
  error: string | null;
  created_at: string;
}

export interface UploadLimits {
  max_file_mb: number;
  max_documents: number;
  max_files_per_upload: number;
}

export interface RejectedFile {
  filename: string;
  error: string;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// ── Token handling ──────────────────────────────────────────────────────────
export const getToken = (): string | null => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};
export const setToken = (token: string): void => {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private mode: the session simply won't survive a reload */
  }
};
export const clearToken = (): void => {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
};

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (fn: (() => void) | null): void => {
  onUnauthorized = fn;
};

// ── Core request helper ─────────────────────────────────────────────────────
async function request<T>(
  path: string,
  init: RequestInit = {},
  opts: { auth?: boolean } = {},
): Promise<T> {
  const auth = opts.auth ?? true;
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && auth) onUnauthorized?.();
    throw new ApiError(
      (body && typeof body.error === "string" && body.error) ||
        "Something went wrong. Please try again.",
      res.status,
    );
  }
  return body as T;
}

// ── Auth ────────────────────────────────────────────────────────────────────
export const register = (name: string, phone: string) =>
  request<{ token: string; user: User }>(
    "/api/auth/register",
    { method: "POST", body: JSON.stringify({ name, phone }) },
    { auth: false },
  );

export const fetchMe = () => request<{ user: User }>("/api/auth/me");

export const logout = () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });

// ── Conversations ───────────────────────────────────────────────────────────
export const listConversations = () =>
  request<{ conversations: Conversation[] }>("/api/conversations");

export const createConversation = () =>
  request<{ conversation: Conversation }>("/api/conversations", { method: "POST" });

export const getConversation = (id: string) =>
  request<{ conversation: Conversation; messages: Message[] }>(`/api/conversations/${id}`);

export const deleteConversation = (id: string) =>
  request<{ ok: boolean }>(`/api/conversations/${id}`, { method: "DELETE" });

export const ask = (id: string, question: string) =>
  request<{
    user_message: Message;
    assistant_message: Message;
    conversation_title: string;
  }>(`/api/conversations/${id}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });

// ── Documents ───────────────────────────────────────────────────────────────
export const listDocuments = () =>
  request<{ documents: DocumentInfo[]; limits: UploadLimits }>("/api/documents");

export const uploadDocuments = (files: File[]) => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f, f.name));
  return request<{ documents: DocumentInfo[]; rejected: RejectedFile[] }>("/api/documents", {
    method: "POST",
    body: form,
  });
};

export const deleteDocument = (id: string) =>
  request<{ ok: boolean }>(`/api/documents/${id}`, { method: "DELETE" });
