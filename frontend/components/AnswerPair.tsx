"use client";
import React from "react";
import { secs } from "@/lib/api";
import type { AskPayload } from "@/lib/types";
import CombinedSection from "./CombinedSection";
import OcrSection from "./OcrSection";
import VlmSection, { ranges } from "./VlmSection";

const NOT_FOUND = "not found in document";

function PartsTable({ p }: { p: Partial<AskPayload> }) {
  const rows = ([["vlm", p.vlm], ["ocr", p.ocr]] as const).flatMap(([k, x]) => (x?.batches ?? []).map((b) => ({ k, b })));
  if (!((p.vlm?.batches?.length ?? 0) > 1 || (p.ocr?.batches?.length ?? 0) > 1)) return null;
  return (
    <section aria-label="How each answer was put together" className="card flex flex-col gap-3 px-6 py-5">
      <h2 className="text-lg font-semibold">How each answer was put together</h2>
      <p className="text-[13px] text-muted">
        Long documents are read in parts that fit the GPU (vision) or the text model's context (OCR). Each part is asked the question; parts that find an answer are combined by the same model.
      </p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-[13px] text-muted">
            <th scope="col" className="py-1.5 font-medium">Method</th>
            <th scope="col" className="font-medium">Pages</th>
            <th scope="col" className="font-medium">What that part answered</th>
            <th scope="col" className="text-right font-medium">Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ k, b }) => {
            const nf = (b.answer ?? "").toLowerCase().includes(NOT_FOUND);
            return (
              <tr key={k + b.pages.join()} className="border-t border-hair align-top">
                <td className={`py-2.5 pr-3 font-medium ${k === "vlm" ? "text-vlm" : "text-ocr-text"}`}>{k === "vlm" ? "Vision" : "OCR"}</td>
                <td className="pr-3">{ranges(b.pages)}</td>
                <td className={`pr-3 ${nf ? "text-muted" : ""}`}>{nf ? "Not found in these pages" : b.answer}</td>
                <td className="text-right font-mono">{secs(b.ms)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {(p.vlm?.combined || p.ocr?.combined) && (
        <p className="text-[13px] text-muted">
          {[p.vlm?.combined && "vision", p.ocr?.combined && "OCR"].filter(Boolean).join(" and ")}: answers from several parts were combined into the final answer.
        </p>
      )}
    </section>
  );
}

export default function AnswerPair({
  p,
  docId,
  research,
  onOpenPage,
  onAskAgain,
}: {
  p: Partial<AskPayload>;
  docId: string;
  research: boolean;
  onOpenPage: (page: number) => void;
  onAskAgain?: () => void;
}) {
  const ranked = p.retrieval?.ranked ?? [];
  const maxScore = Math.max(...ranked.map((r) => r.score), 0.0001);

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <article className="flex flex-col gap-6">
      {/* Demo notice */}
      {p.demo && (
        <p className="chip self-start border border-warn text-warn-text">
          Demo mode: these answers come from text-matching stand-ins, not from the models
        </p>
      )}

      {/* History reuse banner */}
      {p.reused_from && (
        <div role="note" className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-rule bg-sheet px-4 py-2.5 text-sm">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted" aria-hidden>
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" />
          </svg>
          <span>
            Answered from history: you asked this about the same file on{" "}
            <strong className="font-medium">
              {new Date(p.reused_from.asked_at * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </strong>, with the same settings.
          </span>
          {onAskAgain && <button className="btn-quiet ml-auto h-9 !py-0" onClick={onAskAgain}>Ask again</button>}
        </div>
      )}

      {/* Section Quick Jump Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rule bg-sheet/80 px-4 py-2 text-xs">
        <span className="font-semibold text-muted uppercase tracking-wider">Output Sections:</span>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => scrollTo("section-vlm")}
            className="rounded-full bg-vlm-soft px-3 py-1 font-semibold text-vlm transition hover:brightness-95"
          >
            1. VLM Output
          </button>
          <button
            onClick={() => scrollTo("section-ocr")}
            className="rounded-full bg-ocr-soft px-3 py-1 font-semibold text-ocr-text transition hover:brightness-95"
          >
            2. OCR Text Output
          </button>
          <button
            onClick={() => scrollTo("section-combined")}
            className="rounded-full bg-agree-soft px-3 py-1 font-semibold text-agree-text transition hover:brightness-95"
          >
            3. Combined Comparison & Explainability
          </button>
        </div>
      </div>

      {/* 1st Section: Vision Language Model (VLM) Output */}
      <div className="rise">
        <VlmSection p={p} docId={docId} onOpenPage={onOpenPage} />
      </div>

      {/* 2nd Section: OCR Text Output */}
      <div className="rise" style={{ animationDelay: "100ms" }}>
        <OcrSection p={p} docId={docId} onOpenPage={onOpenPage} />
      </div>

      {/* 3rd Section: Combined Output, Comparison & Detailed Explainability */}
      <div className="rise" style={{ animationDelay: "200ms" }}>
        <CombinedSection p={p} docId={docId} research={research} onOpenPage={onOpenPage} />
      </div>

      {/* Research mode in-depth audits */}
      {research && (
        <div className="flex flex-col gap-4 mt-2">
          <PartsTable p={p} />

          {ranked.length > 1 && (
            <section aria-label="Page retrieval" className="card px-6 py-5 text-sm">
              <h2 className="mb-2 text-lg font-semibold">
                {p.retrieval?.read_all ? "How relevant each page looks to the question" : "Which pages the vision model was given"}
              </h2>
              <div className="space-y-1">
                {ranked.slice(0, 12).map((r) => {
                  const chosen = p.retrieval?.vlm_pages.includes(r.page);
                  return (
                    <div key={r.page} className="flex items-center gap-3">
                      <span className="w-16 shrink-0 whitespace-nowrap text-muted">Page {r.page + 1}</span>
                      <div className="h-2.5 flex-1 bg-track">
                        <div className={`h-2.5 rounded-r ${chosen ? "bg-vlm" : "bg-rule"}`} style={{ width: `${(r.score / maxScore) * 100}%` }} />
                      </div>
                      <span className="w-12 text-right font-mono text-[13px] text-muted">{r.score.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-2 text-[13px] text-muted">
                {p.retrieval?.read_all
                  ? `Keyword match (BM25 over ${p.retrieval?.corpus === "textlayer" ? "the PDF's text" : "the OCR text"}). Both methods read every page; this only orders them.`
                  : `Only the ${p.retrieval?.page_cap} best pages went to the vision model. ${p.retrieval?.match_pages ? "The OCR pipeline saw the same pages." : "The OCR pipeline read every page."}`}
              </p>
            </section>
          )}

          {(p.audit ?? []).length > 0 && (
            <section aria-label="OCR audit" className="card overflow-x-auto px-6 py-5 text-sm">
              <h2 className="mb-2 text-lg font-semibold">How well OCR read each page</h2>
              <table className="w-full text-left">
                <thead className="text-[13px] text-muted">
                  <tr>
                    <th className="py-1 font-medium">Page</th>
                    <th className="font-medium">OCR vs the PDF's text</th>
                    <th className="font-medium">Images</th>
                    <th className="font-medium">Drawings</th>
                    <th className="font-medium">Tables</th>
                    <th className="font-medium">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {p.audit!.map((a) => (
                    <tr key={a.page} className="border-t border-hair align-top">
                      <td className="py-1.5">{a.page + 1}</td>
                      <td>
                        {a.ocr_vs_layer_similarity == null
                          ? "no text layer"
                          : `${(a.ocr_vs_layer_similarity * 100).toFixed(1)}% (${a.layer_tokens_missed_by_ocr} ${a.layer_tokens_missed_by_ocr === 1 ? "word" : "words"} missed)`}
                      </td>
                      <td>{a.n_images} ({(a.image_area_ratio * 100).toFixed(0)}% of page)</td>
                      <td>{a.n_drawings}</td>
                      <td>{a.n_tables}</td>
                      <td className="text-warn-text">{a.flags.join("; ") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {p.timings && (
            <p className="text-[13px] text-muted">
              Retrieval {secs(p.timings.retrieval_ms)} · vision {secs(p.timings.vlm_ms)} · OCR {secs(p.timings.ocr_ms)} · text model {secs(p.timings.llm_ms)} · total {secs(p.timings.total_ms)}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
