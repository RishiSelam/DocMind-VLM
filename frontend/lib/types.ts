export type Doc = { id: string; filename: string; n_pages: number; size_bytes: number; created_at: number; ocr?: OcrStatus };
export type OcrStatus = { status: "idle" | "running" | "done" | "error"; cached_pages: number; total: number; error?: string | null };
export type Conversation = { id: string; title: string; doc_id: string | null; created_at: number; updated_at: number };

export type Pipeline = {
  answer: string | null; pages: number[]; ms: number; error: string | null;
  ocr_ms?: number; llm_ms?: number; engine?: string; context_chars?: number; truncated?: boolean;
  batches?: { pages: number[]; answer: string | null; ms: number }[]; combined?: boolean; // the parts a long document was read in
};
export type PairLabel = "agree" | "partial" | "conflict" | "only_vlm" | "only_ocr";
export type Pair = { vlm: string | null; ocr: string | null; label: PairLabel; score: number };
export type OcrSupport = {
  found: string[]; near: { token: string; ocr_token: string }[]; missing: string[]; coverage: number | null; note: string;
};
export type Verification = {
  verdict: "consistent" | "partial" | "disagree" | "conflict"; agreement: number; pairs: Pair[];
  numbers_only_vlm: string[]; numbers_only_ocr: string[]; ocr_support: OcrSupport | null; note: string;
};
export type Audit = {
  page: number; // 0-based
  is_image_file: number; text_layer_chars: number; n_images: number; image_area_ratio: number; n_drawings: number;
  n_tables: number; ocr_chars: number; ocr_tokens: number; ocr_vs_layer_similarity: number | null;
  layer_tokens_missed_by_ocr: number | null; flags: string[];
};
export type AskPayload = {
  question: string; mode: "both" | "vlm" | "ocr"; demo: boolean; short: boolean;
  // NOTE: pipeline `pages` are 1-based; retrieval.* and audit[].page are 0-based.
  retrieval: { ranked: { page: number; score: number }[]; vlm_pages: number[]; corpus: string; page_cap: number; match_pages: boolean; read_all?: boolean };
  vlm: Pipeline | null; ocr: Pipeline | null; verification: Verification | null; audit: Audit[];
  timings: Record<string, number>; scorecard?: Scorecard | null; explanation?: Finding[];
};
export type Finding = { kind: "verdict" | "recognition" | "speed" | "pages"; title: string; text: string };
export type ScoreSide = { answered: boolean; error: boolean; ms: number | null; pages_read: number; support: number | null };
export type Scorecard = {
  reference: "textlayer" | null; n_pages: number; vlm: ScoreSide | null; ocr: ScoreSide | null;
  ocr_read_accuracy: number | null; faster: "vlm" | "ocr" | null; winner: "vlm" | "ocr" | "tie" | "unknown" | null; reason: string;
};
export type Message = { id: string; conversation_id: string; role: "user" | "assistant"; content: string; payload: Partial<AskPayload> & { doc_id?: string }; created_at: number };

export type Scores = { em?: number; anls?: number; contains?: number; abstain?: number; error?: number };
export type ExpItem = {
  idx: number; qid: string; question: string; gold: string[]; vlm_pred: string | null; ocr_pred: string | null;
  vlm_scores: Scores; ocr_scores: Scores; vlm_ms: number | null; ocr_ms: number | null; answer_in_ocr: number | null; agree: number | null;
};
export type Side = { em: number; anls: number; contains: number; abstain_rate: number; error_rate: number; latency_ms: { mean: number; p50: number; p95: number } };
export type Metrics = {
  n?: number; vlm?: Side; ocr?: Side;
  paired?: { anls_vlm_minus_ocr: { diff: number; ci_low: number; ci_high: number }; em_mcnemar: { a_only: number; b_only: number; p_value: number } };
  ocr_answer_coverage?: number | null; disagreement_rate?: number | null; ocr_loss_cases?: number;
};
export type Experiment = {
  id: string; name: string; status: "queued" | "running" | "finished" | "failed"; config: Record<string, any>; metrics: Metrics;
  progress_done: number; progress_total: number; error: string | null; created_at: number; finished_at: number | null; items?: ExpItem[];
};
export type Health = { status: string; demo_mode: boolean; loaded: boolean; vlm: string | null; llm: string | null; ocr_engine: string; gpu: { available: boolean; name?: string; free_gb?: number; total_gb?: number; reason?: string }; page_cap: number; match_pages: boolean };
export type Dataset = { name: string; path: string; n: number };
export type OcrPage = { page: number; engine: string; text: string; boxes: { text: string; score: number; x0: number; y0: number; x1: number; y1: number }[]; render_dpi: number; mean_conf: number | null; ms: number; audit: Audit };
export type SystemMetrics = { n_requests: number; uptime_s: number; gpu: Health["gpu"]; [k: string]: any };
