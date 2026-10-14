"use client";
import React, { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, secs } from "@/lib/api";
import type { AskPayload } from "@/lib/types";
import { ranges } from "./VlmSection";

const NOT_FOUND = "not found in document";
const isShortPlain = (s?: string | null) => !!s && s.length <= 220 && !/[\n*#|`_[\]]/.test(s);

function Marked({ text, missing }: { text: string; missing: string[] }) {
  const words = missing.filter((w) => w.length > 1 && text.toLowerCase().includes(w.toLowerCase()));
  if (!words.length) return <>{text}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <>{text.split(re).map((part, i) => i % 2 ? <mark key={i} className="rounded-[3px] bg-bad-soft px-[3px] text-bad-text">{part}</mark> : part)}</>;
}

export default function OcrSection({
  p,
  docId,
  onOpenPage,
}: {
  p: Partial<AskPayload>;
  docId: string;
  onOpenPage: (page: number) => void;
}) {
  const ocr = p.ocr;
  const side = p.scorecard?.ocr;
  const reference = !!p.scorecard?.reference;
  const faith = p.xai?.faithfulness?.ocr;
  const [copied, setCopied] = useState(false);
  const [showFullOcr, setShowFullOcr] = useState(false);
  const [fetchedOcrText, setFetchedOcrText] = useState<string | null>(null);
  const [loadingText, setLoadingText] = useState(false);

  // If payload does not already have ocr_text, fetch it for the used pages
  useEffect(() => {
    if (ocr?.ocr_text) {
      setFetchedOcrText(ocr.ocr_text);
      return;
    }
    if (!ocr || !ocr.pages?.length || !docId) return;

    let active = true;
    setLoadingText(true);
    Promise.all(ocr.pages.map((pg) => api.pageOcr(docId, pg).catch(() => null)))
      .then((results) => {
        if (!active) return;
        const valid = results.filter(Boolean);
        if (valid.length > 0) {
          const combined = valid.map((r: any) => `--- Page ${r.page} ---\n${r.text}`).join("\n\n");
          setFetchedOcrText(combined);
        }
      })
      .finally(() => {
        if (active) setLoadingText(false);
      });

    return () => { active = false; };
  }, [ocr, docId]);

  if (!ocr && p.mode === "vlm") {
    return (
      <section id="section-ocr" aria-label="Section 2: OCR Text" className="card border-l-4 border-l-ocr p-6">
        <div className="flex items-center gap-3">
          <span className="chip bg-ocr-soft font-semibold text-ocr">Section 2</span>
          <h2 className="text-xl font-semibold">OCR Text Pipeline</h2>
        </div>
        <p className="mt-3 text-sm text-muted">
          The OCR pipeline was skipped for this question because the query was run in Vision-only mode.
        </p>
      </section>
    );
  }

  if (!ocr) return null;

  const answer = ocr.answer ?? "";
  const notFound = answer.toLowerCase().includes(NOT_FOUND);
  const missing = side?.missing ?? [];
  const ocrText = fetchedOcrText || ocr.ocr_text || "";

  const copyText = () => {
    if (!ocrText) return;
    navigator.clipboard.writeText(ocrText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const answerTokens = useMemo(() => {
    return answer
      .split(/\s+/)
      .map((w) => w.replace(/[^\w]/g, "").toLowerCase())
      .filter((w) => w.length > 2);
  }, [answer]);

  return (
    <section
      id="section-ocr"
      aria-label="Section 2: OCR Text and Text Model Output"
      className="card relative flex flex-col gap-5 border-l-4 border-l-ocr p-6 shadow-sm"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-hair pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="chip bg-ocr-soft font-semibold text-ocr">Section 2</span>
            <h2 className="font-reading text-2xl font-bold tracking-tight text-ink">
              OCR Text & Text Model Output
            </h2>
            <span className="chip bg-bench font-mono text-xs text-muted">RapidOCR + Qwen2.5-7B-Instruct</span>
          </div>
          <p className="text-sm text-ink-soft">
            Two-stage pipeline: extracts character bounding boxes and text via RapidOCR, then feeds serialized text into Qwen2.5-7B.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!ocr.error && (
            <span
              className="chip bg-ocr-soft font-mono text-sm font-semibold text-ocr"
              title={`OCR extraction: ${secs(ocr.ocr_ms)} | Text LLM: ${secs(ocr.llm_ms)}`}
            >
              ⏱ {secs(ocr.ms)} ({secs(ocr.ocr_ms)} OCR + {secs(ocr.llm_ms)} LLM)
            </span>
          )}
          {ocr.pages.length > 0 && (
            <button
              onClick={() => onOpenPage(ocr.pages[0])}
              className="chip bg-bench text-xs font-medium text-ink transition-colors hover:bg-select"
              title="Click to view first read page"
            >
              📄 {ocr.pages.length === 1 ? `Page ${ocr.pages[0]}` : `Pages ${ranges(ocr.pages)}`}
            </button>
          )}
        </div>
      </div>

      {/* Answer content */}
      <div className="flex flex-col gap-3 rounded-lg bg-paper p-5 border border-rule/60">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-ocr-text">
          <span>OCR Pipeline Answer</span>
          {side && side.answered && reference && side.support != null && (
            <span className={side.support >= 1 ? "text-agree-text font-normal" : "text-warn-text font-normal"}>
              {Math.round(side.support * 100)}% verified in document text
            </span>
          )}
        </div>

        {ocr.error ? (
          <div role="alert" className="rounded-md bg-bad-soft p-4 text-sm text-bad-text">
            <strong>OCR Pipeline Failed:</strong> {ocr.error}
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

      {/* Extracted OCR Text Viewer */}
      <div className="flex flex-col gap-3 rounded-lg border border-rule/70 bg-sheet/60 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-ocr" />
            <h3 className="text-sm font-semibold text-ink">Extracted OCR Text from Document</h3>
            {ocrText && (
              <span className="text-xs text-muted">
                ({ocrText.length} characters, {ocrText.split(/\s+/).filter(Boolean).length} words)
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {ocrText && (
              <button
                onClick={copyText}
                className="btn-quiet !h-7 !py-0 !text-xs"
                title="Copy extracted OCR text to clipboard"
              >
                {copied ? "✓ Copied!" : "📋 Copy OCR Text"}
              </button>
            )}
            <button
              onClick={() => setShowFullOcr((s) => !s)}
              className="text-xs font-medium text-ocr hover:underline"
            >
              {showFullOcr ? "Collapse text" : "Expand full text"}
            </button>
          </div>
        </div>

        {loadingText ? (
          <p className="text-xs text-muted italic">Loading extracted OCR text…</p>
        ) : ocrText ? (
          <div
            className={`overflow-auto rounded-md border border-rule bg-paper p-3.5 font-mono text-[13px] leading-relaxed text-ink ${
              showFullOcr ? "max-h-96" : "max-h-40"
            }`}
          >
            <pre className="whitespace-pre-wrap font-mono">
              {ocrText.split("\n").map((line, idx) => {
                const isHeading = line.startsWith("--- Page");
                const hasMatch =
                  !isHeading &&
                  answerTokens.some((tok) => line.toLowerCase().includes(tok));
                return (
                  <span
                    key={idx}
                    className={`block ${
                      isHeading
                        ? "font-bold text-ocr-text pt-2 first:pt-0"
                        : hasMatch
                        ? "bg-ocr-soft/40 px-1 rounded font-medium"
                        : "text-ink-soft"
                    }`}
                  >
                    {line}
                  </span>
                );
              })}
            </pre>
          </div>
        ) : (
          <p className="text-xs text-muted">
            OCR text preview is available when OCR runs on the document.
          </p>
        )}

        {ocrText && (
          <p className="text-[11px] text-muted">
            💡 Lines matching keywords from the answer are highlighted above. Notice how OCR flattens table rows into linear lines.
          </p>
        )}
      </div>

      {/* Faithfulness test for OCR */}
      {faith && (
        <div className="rounded-lg border border-hair bg-sheet/40 px-4 py-3 text-xs text-ink-soft">
          <span className="font-semibold text-ink">Faithfulness Counterfactual Test: </span>
          {faith.survived ? (
            <span className="text-warn-text">
              When the OCR text evidence was removed, the answer remained unchanged (“{faith.answer_without_evidence}”).
              The text model may have relied on parametric pre-training or conversational prior rather than the OCR context.
            </span>
          ) : (
            <span className="text-agree-text">
              When the OCR text evidence was removed, the answer changed (“{faith.answer_without_evidence}”).
              This proves the text model directly grounded its answer in the OCR context.
            </span>
          )}
        </div>
      )}

      {/* Context window truncation notice */}
      {ocr.truncated && (
        <div className="rounded-lg bg-warn-soft/60 px-4 py-2.5 text-xs text-warn-text">
          ⚠️ <strong>Context Truncated:</strong> The OCR text exceeded the maximum context character budget. Later pages were left out.
        </div>
      )}

      {/* Explainability footer */}
      <div className="flex items-start gap-2.5 rounded-lg bg-bench/50 p-3 text-xs text-ink-soft">
        <span className="font-semibold text-ocr">How OCR Works:</span>
        <span>
          RapidOCR detects bounding polygons around character sequences and transcribes them into text. The text model then reads this serialized stream. While very fast and accurate for clean paragraph text, OCR can misread visually ambiguous glyphs (e.g. swapping “0” and “o”, or “1” and “l”) and loses 2D tabular spatial structure.
        </span>
      </div>
    </section>
  );
}

