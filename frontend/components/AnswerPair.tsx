"use client";
import ReactMarkdown from "react-markdown";
import { api, secs } from "@/lib/api";
import type { AskPayload, Pipeline } from "@/lib/types";
import ClaimLedger from "./ClaimLedger";
import CompareChart from "./CompareChart";

/** [1,2,3,5] -> "1-3, 5" */
function ranges(pages: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < pages.length; i++) {
    let j = i;
    while (j + 1 < pages.length && pages[j + 1] === pages[j] + 1) j++;
    out.push(j > i ? `${pages[i]}–${pages[j]}` : `${pages[i]}`);
    i = j;
  }
  return out.join(", ") || "-";
}
const partsNote = (p?: Pipeline | null) => ((p?.batches?.length ?? 0) > 1 ? ` · read in ${p!.batches!.length} parts` : "");

const VERDICT = {
  consistent: { text: "The readings match", cls: "text-agree", bar: "bg-agree" },
  partial: { text: "Partly the same", cls: "text-warn", bar: "bg-warn" },
  disagree: { text: "The readings differ", cls: "text-bad", bar: "bg-bad" },
  conflict: { text: "The readings conflict", cls: "text-bad", bar: "bg-bad" },
} as const;

function Reading({ title, tone, p, detail }: { title: string; tone: "vlm" | "ocr"; p: Pipeline | null; detail: string }) {
  const border = tone === "vlm" ? "border-vlm" : "border-ocr";
  const text = tone === "vlm" ? "text-vlm" : "text-ocr";
  return (
    <div className={`border-t-[3px] ${border} pt-2`}>
      <div className={`text-sm font-semibold ${text}`}>{title}</div>
      <div className="mb-2 text-xs text-muted">{p ? detail : "Not run"}</div>
      {p?.error ? (
        <div role="alert" className="rounded-[4px] bg-bad-soft p-2 text-sm text-bad">{p.error}</div>
      ) : p ? (
        <div className="reading"><ReactMarkdown>{p.answer ?? ""}</ReactMarkdown></div>
      ) : null}
      {p?.truncated && <p className="mt-1 text-xs text-warn">The OCR text was longer than the context budget, so lower-ranked pages were left out.</p>}
    </div>
  );
}

export default function AnswerPair({ p, docId, research, onOpenPage }: { p: Partial<AskPayload>; docId: string; research: boolean; onOpenPage: (page: number) => void }) {
  const v = p.verification;
  const meta = v ? VERDICT[v.verdict] : null;
  const vlmPages = p.vlm?.pages ?? [];
  const ranked = p.retrieval?.ranked ?? [];
  const maxScore = Math.max(...ranked.map((r) => r.score), 0.0001);

  return (
    <article className="border-b border-rule pb-5">
      <div className="grid gap-x-4 gap-y-3 md:grid-cols-[1fr_9.5rem_1fr]">
        <Reading title="Vision model reads the page image" tone="vlm" p={p.vlm ?? null}
          detail={`Pages ${ranges(vlmPages)}${partsNote(p.vlm)} · ${secs(p.vlm?.ms)}`} />
        <div className="flex flex-row items-center gap-3 md:flex-col md:justify-center md:text-center" aria-live="polite">
          {meta && v ? (
            <>
              <div className={`h-1 flex-1 md:h-auto md:w-1 md:flex-1 ${meta.bar}`} aria-hidden />
              <div><div className={`text-sm font-semibold ${meta.cls}`}>{meta.text}</div><div className="text-xs text-muted">agreement {(v.agreement * 100).toFixed(0)}%</div></div>
              <div className={`h-1 flex-1 md:h-auto md:w-1 md:flex-1 ${meta.bar}`} aria-hidden />
            </>
          ) : <div className="text-xs text-muted">{p.mode && p.mode !== "both" ? "One pipeline only" : "No comparison"}</div>}
        </div>
        <Reading title="OCR text, then a text model" tone="ocr" p={p.ocr ?? null}
          detail={`Pages ${ranges(p.ocr?.pages ?? [])}${partsNote(p.ocr)} · OCR ${secs(p.ocr?.ocr_ms)} + model ${secs(p.ocr?.llm_ms)}`} />
      </div>

      {p.scorecard && <CompareChart c={p.scorecard} agree={v?.verdict === "consistent"} timings={p.timings} findings={p.explanation} />}

      {vlmPages.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Pages the vision model saw</span>
          {vlmPages.map((pg) => (
            <button key={pg} onClick={() => onOpenPage(pg)} className="overflow-hidden rounded-[3px] border border-rule hover:border-ink" title={`Open page ${pg}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={api.pageImageUrl(docId, pg, 40)} alt={`Page ${pg}`} loading="lazy" className="h-16 w-auto" />
            </button>
          ))}
        </div>
      )}

      {research && (
        <div className="mt-4 text-sm">
          {v && <ClaimLedger v={v} />}
          {([["Vision model", p.vlm], ["OCR + text model", p.ocr]] as const).some(([, x]) => (x?.batches?.length ?? 0) > 1) && (
            <section className="mt-4" aria-label="How the answers were put together">
              <h4 className="mb-1 font-semibold">How each answer was put together</h4>
              <p className="mb-1 text-xs text-muted">Long documents are read in parts that fit the GPU (vision) or the text model's context (OCR). Each part is asked the question; parts that find an answer are combined by the same model.</p>
              {([["Vision model", p.vlm, "text-vlm"], ["OCR + text model", p.ocr, "text-ocr"]] as const).map(([name, x, cls]) => (x?.batches?.length ?? 0) > 1 && (
                <table key={name} className="mb-2 w-full text-left">
                  <caption className={`text-left text-xs font-semibold ${cls}`}>{name}{x!.combined ? " (answers from several parts were combined)" : ""}</caption>
                  <tbody>{x!.batches!.map((b) => (
                    <tr key={b.pages.join()} className="border-t border-rule align-top"><td className="w-24 py-1 text-muted">Pages {ranges(b.pages)}</td><td>{b.answer}</td><td className="w-16 text-right text-muted">{secs(b.ms)}</td></tr>
                  ))}</tbody>
                </table>
              ))}
            </section>
          )}
          {ranked.length > 1 && (
            <section className="mt-4" aria-label="Page retrieval">
              <h4 className="mb-1 font-semibold">{p.retrieval?.read_all ? "How relevant each page looks to the question" : "Which pages the vision model was given"} (BM25 over {p.retrieval?.corpus === "textlayer" ? "the PDF's text layer" : "OCR text"})</h4>
              <div className="space-y-0.5">
                {ranked.slice(0, 12).map((r) => {
                  const chosen = p.retrieval?.vlm_pages.includes(r.page);
                  return (
                    <div key={r.page} className="flex items-center gap-2">
                      <span className="w-16 shrink-0 whitespace-nowrap text-muted">Page {r.page + 1}</span>
                      <div className="h-2 flex-1 bg-bench"><div className={`h-2 ${chosen ? "bg-vlm" : "bg-rule"}`} style={{ width: `${(r.score / maxScore) * 100}%` }} /></div>
                      <span className="w-12 text-right text-muted">{r.score.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-1 text-xs text-muted">{p.retrieval?.read_all
                ? `Both pipelines read every page; the vision model in batches of up to ${p.retrieval?.page_cap} pages. The ranking only orders the pages.`
                : `Cap ${p.retrieval?.page_cap} pages for the vision model. ${p.retrieval?.match_pages ? "The OCR pipeline saw the same pages." : "The OCR pipeline read every page, so the two readings did not have the same input."}`}</p>
            </section>
          )}
          {(p.audit ?? []).length > 0 && (
            <section className="mt-4" aria-label="OCR audit">
              <h4 className="mb-1 font-semibold">OCR audit for the pages the vision model saw</h4>
              <table className="w-full text-left">
                <thead className="text-xs text-muted"><tr><th className="font-normal">Page</th><th className="font-normal">OCR vs text layer</th><th className="font-normal">Images</th><th className="font-normal">Drawings</th><th className="font-normal">Tables</th><th className="font-normal">Flags</th></tr></thead>
                <tbody>
                  {p.audit!.map((a) => (
                    <tr key={a.page} className="border-t border-rule align-top">
                      <td className="py-1">{a.page + 1}</td>
                      <td>{a.ocr_vs_layer_similarity == null ? "no text layer" : `${(a.ocr_vs_layer_similarity * 100).toFixed(1)}% (${a.layer_tokens_missed_by_ocr} ${a.layer_tokens_missed_by_ocr === 1 ? "word" : "words"} missed)`}</td>
                      <td>{a.n_images} ({(a.image_area_ratio * 100).toFixed(0)}% of page)</td><td>{a.n_drawings}</td><td>{a.n_tables}</td>
                      <td className="text-warn">{a.flags.join("; ") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {p.timings && (
            <p className="mt-3 text-xs text-muted">
              Retrieval {secs(p.timings.retrieval_ms)} · vision {secs(p.timings.vlm_ms)} · OCR {secs(p.timings.ocr_ms)} (cost of the pages read; cached pages keep their original time) · text model {secs(p.timings.llm_ms)} · total {secs(p.timings.total_ms)}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
