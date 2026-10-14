"use client";
import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, pct, secs } from "@/lib/api";
import type { AskPayload } from "@/lib/types";
import Analysis from "./Analysis";
import ClaimLedger from "./ClaimLedger";
import CompareChart from "./CompareChart";
import EvidenceCard from "./EvidenceCard";
import { ranges } from "./VlmSection";

const NOT_FOUND = "not found in document";
const isShortPlain = (s?: string | null) => !!s && s.length <= 220 && !/[\n*#|`_[\]]/.test(s);

function Icon({ kind }: { kind: "check" | "warn" | "minus" }) {
  const common = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (kind === "check") return <svg {...common}><path d="m5 12 5 5 9-10" /></svg>;
  if (kind === "warn") return <svg {...common}><path d="M12 4 2.5 20h19z" /><path d="M12 10v4M12 17v.5" /></svg>;
  return <svg {...common}><path d="M5 12h14" /></svg>;
}

const TRUST = {
  high: { text: "High trust", cls: "bg-agree-soft text-agree-text", bar: "bg-agree" },
  medium: { text: "Medium trust", cls: "bg-warn-soft text-warn-text", bar: "bg-warn" },
  low: { text: "Low trust", cls: "bg-bad-soft text-bad-text", bar: "bg-bad" },
  unknown: { text: "Trust: cannot tell", cls: "bg-bench text-ink", bar: "bg-muted" },
  "not rated": { text: "Trust: not rated", cls: "bg-bench text-muted", bar: "bg-muted" },
} as const;

function TrustPill({ t }: { t: NonNullable<AskPayload["xai"]>["trust"] }) {
  const m = TRUST[t.level] ?? TRUST.unknown;
  return (
    <details className="group mt-1 self-start">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 [&::-webkit-details-marker]:hidden">
        <span className={`chip font-medium ${m.cls}`}>{m.text}</span>
        {t.score != null && (
          <span className="flex items-center gap-2 text-[13px] text-muted">
            <span className="h-1.5 w-20 overflow-hidden rounded-full bg-track" aria-hidden>
              <span className={`block h-full rounded-full ${m.bar}`} style={{ width: `${t.score * 100}%` }} />
            </span>
            {Math.round(t.score * 100)} / 100
          </span>
        )}
        <span className="text-[13px] text-muted underline-offset-2 group-open:hidden hover:underline">why?</span>
      </summary>
      <ul className="mt-2 space-y-1 text-sm text-ink-soft">
        {t.reasons.map((r) => <li key={r}>• {r}</li>)}
        <li className="pt-1 text-[13px] text-muted">
          Transparent rule-based scoring calculated from evidence agreement, faithfulness, and document ground truth.
        </li>
      </ul>
    </details>
  );
}

export default function CombinedSection({
  p,
  docId,
  research,
  onOpenPage,
}: {
  p: Partial<AskPayload>;
  docId: string;
  research: boolean;
  onOpenPage: (page: number) => void;
}) {
  const c = p.scorecard;
  const v = p.verification;
  const vlm = p.vlm;
  const ocr = p.ocr;
  const [showGuide, setShowGuide] = useState(false);

  if (!vlm || !ocr) {
    return (
      <section id="section-combined" aria-label="Section 3: Combined Comparison" className="card border-l-4 border-l-agree p-6">
        <div className="flex items-center gap-3">
          <span className="chip bg-agree-soft font-semibold text-agree">Section 3</span>
          <h2 className="text-xl font-semibold">Combined Comparison & Explainability</h2>
        </div>
        <p className="mt-3 text-sm text-muted">
          Comparative output and explainability analysis require both Vision and OCR pipelines to run. Run in "Both" mode to see the comparative synthesis.
        </p>
      </section>
    );
  }

  const settled = p.analysis && (p.analysis.better === "vlm" || p.analysis.better === "ocr") && c?.winner !== p.analysis.better;
  const winner = settled ? p.analysis!.better : c?.winner;
  const pick = winner === "vlm" ? vlm : winner === "ocr" ? ocr : null;
  const answer = pick?.answer?.trim().replace(/\.$/, "");
  const both = !c?.vlm?.answered && !c?.ocr?.answered && !c?.vlm?.error && !c?.ocr?.error;

  const f = (p.explanation ?? []).find((x) => x.kind === "verdict");
  let title = settled ? p.analysis!.headline : f?.title ?? c?.reason ?? "Comparative Analysis";
  if ((winner === "vlm" || winner === "ocr") && isShortPlain(answer) && answer!.length <= 60) {
    title = `Recommended: Use the ${winner === "vlm" ? "Vision" : "OCR"} answer (${answer})`;
  }

  const tone = both ? { icon: "minus" as const, cls: "bg-bench text-ink" }
    : winner === "vlm" ? { icon: "check" as const, cls: "bg-vlm-soft text-vlm" }
      : winner === "ocr" ? { icon: "check" as const, cls: "bg-ocr-soft text-ocr" }
        : v?.verdict === "consistent" ? { icon: "check" as const, cls: "bg-agree-soft text-agree" }
          : { icon: "warn" as const, cls: "bg-warn-soft text-warn" };

  const chip = !v ? null
    : v.verdict === "consistent" ? { text: "Answers Match", cls: "bg-agree-soft text-agree-text" }
      : v.verdict === "partial" ? { text: "Partly Match", cls: "bg-warn-soft text-warn-text" }
        : { text: "Answers Differ", cls: "bg-bad-soft text-bad-text" };

  const vlmAns = vlm.answer ?? "";
  const ocrAns = ocr.answer ?? "";

  const cs = p.combined_summary;
  let summaryText = cs?.summary;
  let consensusPoints = cs?.consensus ?? [];
  let vlmPoints = cs?.vlm_unique ?? [];
  let ocrPoints = cs?.ocr_unique ?? [];
  let discrepancies = cs?.discrepancies ?? [];

  if (!summaryText) {
    if (v?.verdict === "consistent" || vlmAns.trim() === ocrAns.trim()) {
      summaryText = `**Consensus Answer:** ${vlmAns.trim()}\n\nBoth the Vision Language Model (reading visual page images directly) and the OCR text pipeline confirm this information identically, providing high cross-modal confidence.`;
      if (!consensusPoints.length) consensusPoints = [vlmAns.trim()];
    } else {
      const parts = [
        `### Comprehensive Merged Information:`,
        `- **Vision Model (Page Images):** ${vlmAns.trim()}`,
        `- **OCR Pipeline (Extracted Text):** ${ocrAns.trim()}`,
      ];
      if (p.analysis?.better === "vlm") {
        parts.push(`\n*Synthesis Note:* The Vision model provides the better-grounded interpretation of the page image.`);
      } else if (p.analysis?.better === "ocr") {
        parts.push(`\n*Synthesis Note:* The OCR pipeline provides the better-grounded reading from extracted text.`);
      }
      summaryText = parts.join("\n");
      if (!vlmPoints.length) vlmPoints = [vlmAns.trim()];
      if (!ocrPoints.length) ocrPoints = [ocrAns.trim()];
    }
  }

  return (
    <section
      id="section-combined"
      aria-label="Section 3: Combined Output, Comparison and Explainability"
      className="card relative flex flex-col gap-6 border-l-4 border-l-agree p-6 shadow-sm"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-hair pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="chip bg-agree-soft font-semibold text-agree">Section 3</span>
            <h2 className="font-reading text-2xl font-bold tracking-tight text-ink">
              Combined Output, Comparison & Explainability
            </h2>
          </div>
          <p className="text-sm text-ink-soft">
            Synthesizes both outputs, measures agreement, resolves discrepancies, and explains how and what is better between Vision and OCR.
          </p>
        </div>

        <button
          onClick={() => setShowGuide((s) => !s)}
          className="btn-quiet !h-8 !py-0 !text-xs"
        >
          {showGuide ? "Hide method guide" : "📖 How the 2 methods compare"}
        </button>
      </div>

      {/* Recommended Verdict & Decision Banner */}
      <div className="card flex items-start gap-4 bg-paper px-6 py-5 border-2 border-rule">
        <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone.cls}`}>
          <Icon kind={tone.icon} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2.5">
            <h3 className="text-xl font-bold text-ink">{title}</h3>
            {chip && <span className={`chip font-semibold ${chip.cls}`}>{chip.text}</span>}
            <span className="chip bg-bench text-xs text-muted">
              {c?.reference ? "✓ Ground truth from PDF embedded text" : "ℹ️ No embedded text layer (scanned/image document)"}
            </span>
          </div>

          <p className="text-[15px] text-ink-soft leading-relaxed">
            {p.analysis?.reason ?? (settled ? p.analysis!.summary : f?.text ?? c?.reason)}
          </p>

          {p.xai?.trust && <TrustPill t={p.xai.trust} />}
        </div>
      </div>

      {/* Unified Combined Summary Card */}
      <div className="card flex flex-col gap-4 border-2 border-agree/50 bg-paper p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair pb-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-agree text-white text-xs font-bold shadow-sm">
              ✨
            </span>
            <h3 className="font-reading text-xl font-bold text-ink">
              Unified Combined Summary (Synthesizing Both Methods)
            </h3>
          </div>
          <span className="chip bg-agree-soft font-semibold text-agree-text text-xs">
            Complete Merged Information
          </span>
        </div>

        <p className="text-xs text-muted">
          This summary synthesizes and combines the information extracted from both the Vision Language Model (visual page layout, tables, graphics) and the OCR text pipeline (character strings and verbatim paragraphs) into one complete answer.
        </p>

        {/* The Merged Synthesis Text */}
        <div className="rounded-lg bg-sheet/70 border border-rule/60 p-4 font-reading text-[16px] leading-relaxed text-ink reading">
          <ReactMarkdown>{summaryText}</ReactMarkdown>
        </div>

        {/* Information Source Breakdown */}
        {(consensusPoints.length > 0 || vlmPoints.length > 0 || ocrPoints.length > 0 || discrepancies.length > 0) && (
          <div className="grid gap-3 pt-1 text-xs sm:grid-cols-2">
            {consensusPoints.length > 0 && (
              <div className="rounded-md border border-agree/40 bg-agree-soft/30 p-3">
                <span className="font-semibold text-agree-text flex items-center gap-1.5 mb-1.5">
                  <span className="h-2 w-2 rounded-full bg-agree" />
                  Confirmed by Both Methods (High Confidence):
                </span>
                <ul className="space-y-1 text-ink-soft">
                  {consensusPoints.map((pt, i) => (
                    <li key={i}>• {pt}</li>
                  ))}
                </ul>
              </div>
            )}

            {vlmPoints.length > 0 && (
              <div className="rounded-md border border-vlm/40 bg-vlm-soft/30 p-3">
                <span className="font-semibold text-vlm flex items-center gap-1.5 mb-1.5">
                  <span className="h-2 w-2 rounded-full bg-vlm" />
                  Identified by Vision Model:
                </span>
                <ul className="space-y-1 text-ink-soft">
                  {vlmPoints.map((pt, i) => (
                    <li key={i}>• {pt}</li>
                  ))}
                </ul>
              </div>
            )}

            {ocrPoints.length > 0 && (
              <div className="rounded-md border border-ocr/40 bg-ocr-soft/30 p-3">
                <span className="font-semibold text-ocr-text flex items-center gap-1.5 mb-1.5">
                  <span className="h-2 w-2 rounded-full bg-ocr" />
                  Identified by OCR Text Pipeline:
                </span>
                <ul className="space-y-1 text-ink-soft">
                  {ocrPoints.map((pt, i) => (
                    <li key={i}>• {pt}</li>
                  ))}
                </ul>
              </div>
            )}

            {discrepancies.length > 0 && (
              <div className="rounded-md border border-warn/40 bg-warn-soft/30 p-3">
                <span className="font-semibold text-warn-text flex items-center gap-1.5 mb-1.5">
                  <span className="h-2 w-2 rounded-full bg-warn" />
                  Reconciled Value Discrepancies:
                </span>
                <ul className="space-y-1 text-ink-soft">
                  {discrepancies.map((pt, i) => (
                    <li key={i}>• {pt}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Side-by-Side Direct Comparison Cards */}
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Direct Side-by-Side Comparison
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {/* VLM side */}
          <div className="rounded-lg border-2 border-vlm/30 bg-paper p-4 flex flex-col gap-2">
            <div className="flex items-center justify-between border-b border-hair pb-2 text-xs">
              <span className="font-semibold text-vlm">1. Vision Model (VLM) Answer</span>
              <span className="font-mono text-muted">{secs(vlm.ms)}</span>
            </div>
            <div className="font-reading text-lg text-ink py-1">
              {vlm.error ? (
                <span className="text-bad-text text-sm">Failed: {vlm.error}</span>
              ) : isShortPlain(vlmAns) ? (
                <span>{vlmAns}</span>
              ) : (
                <div className="reading text-sm"><ReactMarkdown>{vlmAns}</ReactMarkdown></div>
              )}
            </div>
            <div className="mt-auto pt-2 border-t border-hair text-xs text-muted flex justify-between">
              <span>{c?.vlm?.support != null ? `${Math.round(c.vlm.support * 100)}% verified in doc` : "Pages " + ranges(vlm.pages)}</span>
              <span className="text-vlm font-medium">Multimodal pixels</span>
            </div>
          </div>

          {/* OCR side */}
          <div className="rounded-lg border-2 border-ocr/30 bg-paper p-4 flex flex-col gap-2">
            <div className="flex items-center justify-between border-b border-hair pb-2 text-xs">
              <span className="font-semibold text-ocr-text">2. OCR + Text Model Answer</span>
              <span className="font-mono text-muted">{secs(ocr.ms)}</span>
            </div>
            <div className="font-reading text-lg text-ink py-1">
              {ocr.error ? (
                <span className="text-bad-text text-sm">Failed: {ocr.error}</span>
              ) : isShortPlain(ocrAns) ? (
                <span>{ocrAns}</span>
              ) : (
                <div className="reading text-sm"><ReactMarkdown>{ocrAns}</ReactMarkdown></div>
              )}
            </div>
            <div className="mt-auto pt-2 border-t border-hair text-xs text-muted flex justify-between">
              <span>{c?.ocr?.support != null ? `${Math.round(c.ocr.support * 100)}% verified in doc` : "Pages " + ranges(ocr.pages)}</span>
              <span className="text-ocr font-medium">Serialized text</span>
            </div>
          </div>
        </div>
      </div>

      {/* Detailed Diagnostic Analysis: Why one method did better & root causes */}
      {p.analysis && (
        <div className="flex flex-col gap-3">
          <Analysis a={p.analysis} docId={docId} />
        </div>
      )}

      {/* Where the answers came from (Evidence Localization Agreement) */}
      {p.xai && (
        <div className="flex flex-col gap-3">
          <EvidenceCard x={p.xai} docId={docId} />
        </div>
      )}

      {/* Metrics Bar Charts & Plain-Language Findings */}
      {c && (
        <div className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted">
            Performance Metrics & Comparison Charts
          </h3>
          <CompareChart
            c={c}
            timings={p.timings}
            findings={p.analysis ? p.explanation?.filter((f) => f.kind !== "recognition") : p.explanation}
          />
        </div>
      )}

      {/* Claim-by-Claim Ledger */}
      {v && v.pairs && v.pairs.length > 0 && (
        <div className="card p-5 bg-paper">
          <ClaimLedger v={v} />
        </div>
      )}

      {/* Educational Explainability Guide (Collapsible or visible) */}
      {showGuide && (
        <div className="rounded-lg border border-rule bg-sheet p-6 text-sm text-ink-soft space-y-4">
          <h3 className="font-reading text-lg font-bold text-ink">
            Understanding the Architectural Differences: VLM vs OCR
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-md bg-paper p-4 border border-hair">
              <h4 className="font-semibold text-vlm mb-2">Vision-Language Model (VLM) Architecture</h4>
              <p className="text-xs leading-relaxed text-ink-soft">
                Qwen2.5-VL encodes entire page images through visual patches into a shared multimodal latent space.
                <strong> Advantages:</strong> It natively perceives 2D coordinates, column boundaries, table cell grids, stamps, handwriting, and graphic callouts.
                <strong> Vulnerabilities:</strong> Pixel resolution limits (e.g. tiny superscripts or low-DPI scans) can lead to hallucination if text is indistinct.
              </p>
            </div>
            <div className="rounded-md bg-paper p-4 border border-hair">
              <h4 className="font-semibold text-ocr-text mb-2">OCR + Text LLM Pipeline Architecture</h4>
              <p className="text-xs leading-relaxed text-ink-soft">
                A two-step pipeline where RapidOCR extracts text boxes, sort-orders them, and serializes them into a 1D prompt for Qwen2.5-7B.
                <strong> Advantages:</strong> Deterministic character extraction and highly efficient for linear prose.
                <strong> Vulnerabilities:</strong> Column flattening (reading across columns instead of down), missing unindexed stamps, and glyph confusions (e.g. confusing “O” with “0” or “l” with “1”).
              </p>
            </div>
          </div>
          <div className="rounded-md bg-bench/60 p-3 text-xs text-muted">
            <strong>Why DocMind reads twice:</strong> No single method is always right. When OCR makes a confusable swap (like <code>12oo0</code> for <code>12000</code>), the VLM catches the numeral. When the VLM is ungrounded, OCR provides exact token anchors. Combining them produces genuine explainability.
          </div>
        </div>
      )}
    </section>
  );
}
