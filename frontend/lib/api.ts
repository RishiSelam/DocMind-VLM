import type { AskPayload, Conversation, Dataset, Doc, Experiment, Health, Message, OcrPage, OcrStatus, SystemMetrics } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new Error(`Cannot reach the DocMind backend at ${API}. Is it running? (uvicorn app.main:app --port 8000)`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  health: () => req<Health>("/api/health"),
  metrics: () => req<SystemMetrics>("/api/system/metrics"),
  documents: () => req<Doc[]>("/api/documents"),
  document: (id: string) => req<Doc>(`/api/documents/${id}`),
  upload: (file: File) => { const fd = new FormData(); fd.append("file", file); return req<Doc>("/api/documents", { method: "POST", body: fd }); },
  deleteDoc: (id: string) => req(`/api/documents/${id}`, { method: "DELETE" }),
  startOcr: (id: string) => req<OcrStatus>(`/api/documents/${id}/ocr`, { method: "POST" }),
  ocrStatus: (id: string) => req<OcrStatus>(`/api/documents/${id}/ocr/status`),
  pageOcr: (id: string, page: number) => req<OcrPage>(`/api/documents/${id}/pages/${page}/ocr`),
  pageImageUrl: (id: string, page: number, dpi = 110) => `${API}/api/documents/${id}/pages/${page}/image?dpi=${dpi}`,
  conversations: () => req<Conversation[]>("/api/conversations"),
  conversation: (id: string) => req<Conversation & { messages: Message[] }>(`/api/conversations/${id}`),
  deleteConversation: (id: string) => req(`/api/conversations/${id}`, { method: "DELETE" }),
  exportUrl: (id: string, format: "md" | "json") => `${API}/api/conversations/${id}/export?format=${format}`,
  ask: (b: { doc_id?: string; conversation_id?: string; question: string; mode?: string; short?: boolean }) =>
    req<{ conversation_id: string; user_message: Message; assistant_message: Message & { payload: AskPayload } }>("/api/ask", json(b)),
  datasets: () => req<Dataset[]>("/api/eval/datasets"),
  experiments: () => req<Experiment[]>("/api/experiments"),
  experiment: (id: string) => req<Experiment>(`/api/experiments/${id}`),
  createExperiment: (b: { name: string; dataset: string; limit?: number; mode?: string; notes?: string }) => req<Experiment>("/api/experiments", json(b)),
  resumeExperiment: (id: string) => req(`/api/experiments/${id}/resume`, { method: "POST" }),
  deleteExperiment: (id: string) => req(`/api/experiments/${id}`, { method: "DELETE" }),
  experimentCsvUrl: (id: string) => `${API}/api/experiments/${id}/csv`,
};

export const pct = (x: number | null | undefined, d = 1) => (x == null ? "n/a" : `${(x * 100).toFixed(d)}%`);
export const secs = (ms: number | null | undefined) => (ms == null ? "n/a" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
export const bytes = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);
