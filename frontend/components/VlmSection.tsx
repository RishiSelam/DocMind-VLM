"use client";
import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, secs } from "@/lib/api";
import type { AskPayload, EvBox } from "@/lib/types";

const NOT_FOUND = "not found in document";
const isShortPlain = (s?: string | null) => !!s && s.length <= 220 && !/[\n*#|`_[\]]/.test(s);
const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const boxStyle = (b: number[]) => ({ left: pct(b[0]), top: pct(b[1]), width: pct(b[2] - b[0]), height: pct(b[3] - b[1]) });

export function ranges(pages: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < pages.length; i++) {
    let j = i;
    while (j + 1 < pages.length && pages[j + 1] === pages[j] + 1) j++;
    out.push(j > i ? `${pages[i]}–${pages[j]}` : `${pages[i]}`);
    i = j;
  }
  return out.join(", ") || "-";
}

function Marked({ text, missing }: { text: string; missing: string[] }) {
  const words = missing.filter((w) => w.length > 1 && text.toLowerCase().includes(w.toLowerCase()));
  if (!words.length) return <>{text}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <>{text.split(re).map((part, i) => i % 2 ? <mark key={i} className="rounded-[3px] bg-bad-soft px-[3px] text-bad-text">{part}</mark> : part)}</>;
}

export default function VlmSection({
  p,
  docId,
  onOpenPage,
}: {
  p: Partial<AskPayload>;
  docId: string;
  onOpenPage: (page: number) => void;
}) {
  const vlm = p.vlm;
  const side = p.scorecard?.vlm;
  const reference = !!p.scorecard?.reference;
  const xai = p.xai;
  const vBox = xai?.vision;
  const faith = xai?.faithfulness?.vlm;
  const [showCrop, setShowCrop] = useState(false);

  if (!vlm && p.mode === "ocr") {
    return (
      <section id="section-vlm" aria-label="Section 1: VLM" className="card border-l-4 border-l-vlm p-6">
        <div className="flex items-center gap-3">
          <span className="chip bg-vlm-soft font-semibold text-vlm">Section 1</span>
          <h2 className="text-xl font-semibold">Vision Language Model (VLM)</h2>
        </div>
        <p className="mt-3 text-sm text-muted">
          The vision pipeline was skipped for this question because the query was run in OCR-only mode.
        </p>
      </section>
    );
  }

  if (!vlm) return null;

  const answer = vlm.answer ?? "";
  const notFound = answer.toLowerCase().includes(NOT_FOUND);
  const missing = side?.missing ?? [];
  const parts = vlm.batches?.length ?? 0;

  return (
    <section
      id="section-vlm"
      aria-label="Section 1: Vision Language Model (VLM) Output"
      className="card relative flex flex-col gap-5 border-l-4 border-l-vlm p-6 shadow-sm"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-hair pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="chip bg-vlm-soft font-semibold text-vlm">Section 1</span>
            <h2 className="font-reading text-2xl font-bold tracking-tight text-ink">
              Vision Language Model (VLM) Output
            </h2>
            <span className="chip bg-bench font-mono text-xs text-muted">Qwen2.5-VL-7B-Instruct</span>
          </div>
          <p className="text-sm text-ink-soft">
            Direct visual reading of page images. Preserves 2D layout, multi-column tables, graphics, coordinates, and typography.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!vlm.error && (
            <span className="chip bg-vlm-soft font-mono text-sm font-semibold text-vlm">
              ⏱ {secs(vlm.ms)}
            </span>
          )}
          {vlm.pages.length > 0 && (
            <button
              onClick={() => onOpenPage(vlm.pages[0])}
              className="chip bg-bench text-xs font-medium text-ink transition-colors hover:bg-select"
              title="Click to view first inspected page"
            >
              📄 {vlm.pages.length === 1 ? `Page ${vlm.pages[0]}` : `Pages ${ranges(vlm.pages)}`}
            </button>
          )}
        </div>
      </div>

      {/* Answer content */}
      <div className="flex flex-col gap-3 rounded-lg bg-paper p-5 border border-rule/60">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-vlm">
          <span>Model Answer</span>
          {side && side.answered && reference && side.support != null && (
            <span className={side.support >= 1 ? "text-agree-text font-normal" : "text-warn-text font-normal"}>
              {Math.round(side.support * 100)}% verified in document text
            </span>
          )}
        </div>

        {vlm.error ? (
          <div role="alert" className="rounded-md bg-bad-soft p-4 text-sm text-bad-text">
            <strong>VLM Failed:</strong> {vlm.error}
          </div>
        ) : notFound ? (
          <p className="font-reading text-xl text-muted italic">Not found in the document.</p>
        ) : isShortPlain(answer) ? (
          <p className={`font-reading ${answer.length <= 60 ? "text-2xl font-medium" : "text-xl"} leading-relaxed text-ink`}>
            <Marked text={answer} missing={missing} />
          </p>
        ) : (
          <div className="reading text-ink">
            <ReactMarkdown>{answer}</ReactMarkdown>
          </div>
        )}

        {missing.length > 0 && reference && (
          <p className="text-xs text-warn-text">
            ⚠️ Tokens not detected in PDF embedded text: {missing.map((w) => `“${w}”`).join(", ")}
          </p>
        )}
      </div>

      {/* Grounding and Visual Attention (Where VLM looked) */}
      {vBox && (
        <div className="flex flex-col gap-3 rounded-lg border border-rule/70 bg-sheet/60 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-vlm" />
              Visual Evidence & Grounding Localization
            </h3>
            <button
              onClick={() => setShowCrop((s) => !s)}
              className="text-xs font-medium text-vlm hover:underline"
            >
              {showCrop ? "Hide visual crop" : "Inspect visual crop"}
            </button>
          </div>

          <p className="text-xs text-ink-soft">
            The vision model identified its supporting evidence on{" "}
            <strong>Page {vBox.page + 1}</strong> within coordinates{" "}
            <code className="rounded bg-bench px-1.5 py-0.5 font-mono text-[11px]">
              [{vBox.box.map((n) => n.toFixed(3)).join(", ")}]
            </code>
            .
          </p>

          {showCrop && (
            <div className="mt-2 flex flex-col sm:flex-row items-center gap-4 rounded-md border border-rule bg-paper p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={api.cropUrl(docId, vBox.page + 1, vBox.box)}
                alt="Enlarged region focused on by Vision Model"
                className="max-h-32 w-auto max-w-full rounded border border-rule object-contain"
              />
              <div className="text-xs text-muted flex-1 space-y-1">
                <p className="font-medium text-ink">High-Resolution Visual Crop</p>
                <p>
                  Direct pixel patch extracted from Page {vBox.page + 1}. Because Qwen2.5-VL processes 2D patches
                  directly, column structures and graphic borders remain aligned.
                </p>
                <button
                  onClick={() => onOpenPage(vBox.page + 1)}
                  className="btn-quiet !h-7 !py-0 !text-xs mt-1"
                >
                  Open Page {vBox.page + 1} in Viewer
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Faithfulness test for VLM */}
      {faith && (
        <div className="rounded-lg border border-hair bg-sheet/40 px-4 py-3 text-xs text-ink-soft">
          <span className="font-semibold text-ink">Faithfulness Counterfactual Test: </span>
          {faith.survived ? (
            <span className="text-warn-text">
              When the visual evidence was occluded, the answer remained unchanged (“{faith.answer_without_evidence}”).
              The vision model may have inferred this answer from question context or surrounding layout.
            </span>
          ) : (
            <span className="text-agree-text">
              When the visual evidence was occluded, the answer changed (“{faith.answer_without_evidence}”).
              This confirms the vision model genuinely relied on the highlighted visual region.
            </span>
          )}
        </div>
      )}

      {/* Multi-batch details if read in multiple parts */}
      {parts > 1 && (
        <details className="rounded-lg border border-hair bg-sheet/30 p-3 text-xs text-muted">
          <summary className="cursor-pointer font-medium text-ink hover:text-vlm">
            View multi-batch processing ({parts} parts combined)
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-hair font-semibold text-ink">
                  <th className="py-1">Part</th>
                  <th>Pages</th>
                  <th>Answer from Part</th>
                  <th className="text-right">Latency</th>
                </tr>
              </thead>
              <tbody>
                {vlm.batches?.map((b, i) => (
                  <tr key={i} className="border-b border-hair/50">
                    <td className="py-1 font-medium">Batch {i + 1}</td>
                    <td>{ranges(b.pages)}</td>
                    <td className="truncate max-w-xs">{b.answer ?? "-"}</td>
                    <td className="text-right font-mono">{secs(b.ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {/* Explainability footer */}
      <div className="flex items-start gap-2.5 rounded-lg bg-bench/50 p-3 text-xs text-ink-soft">
        <span className="font-semibold text-vlm">How VLM Works:</span>
        <span>
          Qwen2.5-VL processes document pages as 2D visual tokens through a Vision Transformer (ViT). This enables
          it to understand tabular column headers, spatial proximity, checkboxes, and handwriting without needing
          an intermediate text serialization step.
        </span>
      </div>
    </section>
  );
}

