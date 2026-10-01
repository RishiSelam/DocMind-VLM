"use client";
import ReactMarkdown from "react-markdown";
import { secs } from "@/lib/api";
import type { AskPayload, Pipeline, ScoreSide } from "@/lib/types";
import ClaimLedger from "./ClaimLedger";
import CompareChart from "./CompareChart";
import EvidenceCard from "./EvidenceCard";

/** [1,2,3,5] -> "1–3, 5" */
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

const NOT_FOUND = "not found in document";
const isShortPlain = (s?: string | null) => !!s && s.length <= 220 && !/[\n*#|`_[\]]/.test(s);
const quoteList = (ws: string[]) => ws.slice(0, 3).map((w) => `“${w}”`).join(", ");

function Icon({ kind }: { kind: "check" | "warn" | "minus" }) {
  const common = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (kind === "check") return <svg {...common}><path d="m5 12 5 5 9-10" /></svg>;
  if (kind === "warn") return <svg {...common}><path d="M12 4 2.5 20h19z" /><path d="M12 10v4M12 17v.5" /></svg>;
  return <svg {...common}><path d="M5 12h14" /></svg>;
}

/** The answer's words that are not printed in the document, marked in place (short plain answers only). */
function Marked({ text, missing }: { text: string; missing: string[] }) {
  const words = missing.filter((w) => w.length > 1 && text.toLowerCase().includes(w.toLowerCase()));
  if (!words.length) return <>{text}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <>{text.split(re).map((part, i) => i % 2 ? <mark key={i} className="rounded-[3px] bg-bad-soft px-[3px] text-bad-text">{part}</mark> : part)}</>;
}

const TRUST = {
  high: { text: "High trust", cls: "bg-agree-soft text-agree-text", bar: "bg-agree" },
  medium: { text: "Medium trust", cls: "bg-warn-soft text-warn-text", bar: "bg-warn" },
  low: { text: "Low trust", cls: "bg-bad-soft text-bad-text", bar: "bg-bad" },
  unknown: { text: "Trust: cannot tell", cls: "bg-bench text-ink", bar: "bg-muted" },
  "not rated": { text: "Trust: not rated", cls: "bg-bench text-muted", bar: "bg-muted" },
} as const;

/** How far to trust the recommended answer, with the reasons it is built from. */
function TrustPill({ t }: { t: NonNullable<AskPayload["xai"]>["trust"] }) {
  const m = TRUST[t.level] ?? TRUST.unknown;
  return (
    <details className="group mt-1 self-start">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 [&::-webkit-details-marker]:hidden">
        <span className={`chip font-medium ${m.cls}`}>{m.text}</span>
        {t.score != null && (
          <span className="flex items-center gap-2 text-[13px] text-muted">
            <span className="h-1.5 w-20 overflow-hidden rounded-full bg-track" aria-hidden><span className={`block h-full rounded-full ${m.bar}`} style={{ width: `${t.score * 100}%` }} /></span>
            {Math.round(t.score * 100)} / 100
          </span>
        )}
        <span className="text-[13px] text-muted underline-offset-2 group-open:hidden hover:underline">why?</span>
      </summary>
      <ul className="mt-2 space-y-1 text-sm text-ink-soft">
        {t.reasons.map((r) => <li key={r}>{r}</li>)}
        <li className="pt-1 text-[13px] text-muted">A transparent rule over these signals, not a learned model. Experiments measure whether it predicts wrong answers.</li>
      </ul>
    </details>
  );
}

function Verdict({ p }: { p: Partial<AskPayload> }) {
  const c = p.scorecard, v = p.verification;
  if (!c || !c.vlm || !c.ocr) return null;
  const f = (p.explanation ?? []).find((x) => x.kind === "verdict");
  const pick = c.winner === "vlm" ? p.vlm : c.winner === "ocr" ? p.ocr : null;
  const answer = pick?.answer?.trim().replace(/\.$/, "");
  const both = !c.vlm.answered && !c.ocr.answered && !c.vlm.error && !c.ocr.error;

  let title = f?.title ?? c.reason;
  if ((c.winner === "vlm" || c.winner === "ocr") && isShortPlain(answer) && answer!.length <= 60)
    title = `Use the ${c.winner === "vlm" ? "vision" : "OCR"} answer: ${answer}`;

  const tone = both ? { icon: "minus" as const, cls: "bg-bench text-ink" }
    : c.winner === "vlm" ? { icon: "check" as const, cls: "bg-vlm-soft text-vlm" }
      : c.winner === "ocr" ? { icon: "check" as const, cls: "bg-ocr-soft text-ocr" }
        : v?.verdict === "consistent" ? { icon: "check" as const, cls: "bg-agree-soft text-agree" }
          : { icon: "warn" as const, cls: "bg-warn-soft text-warn" };
  const chip = !v ? null
    : v.verdict === "consistent" ? { text: "Answers match", cls: "bg-agree-soft text-agree-text" }
      : v.verdict === "partial" ? { text: "Partly the same", cls: "bg-warn-soft text-warn-text" }
        : { text: "Answers differ", cls: "bg-bad-soft text-bad-text" };

  return (
    <section aria-label="Verdict" className="card flex items-start gap-4 px-6 py-5">
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone.cls}`}><Icon kind={tone.icon} /></span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-xl font-semibold">{title}</h2>
          {chip && <span className={`chip font-medium ${chip.cls}`}>{chip.text}</span>}
          <span className="chip bg-bench">{c.reference ? "Checked against the PDF's own text" : "No embedded text to check against"}</span>
        </div>
        <p className="text-ink-soft">{f?.text ?? c.reason}</p>
        {p.xai?.trust && <TrustPill t={p.xai.trust} />}
      </div>
    </section>
  );
}

function AnswerCard({ tone, p, side, reference }: { tone: "vlm" | "ocr"; p: Pipeline | null | undefined; side: ScoreSide | null | undefined; reference: boolean }) {
  const vlm = tone === "vlm";
  const title = vlm ? "Vision model · reads the page images" : "OCR + text model · reads the extracted text";
  if (!p) return null;
  const parts = p.batches?.length ?? 0;
  const missing = side?.missing ?? [];
  const answer = p.answer ?? "";
  const notFound = answer.toLowerCase().includes(NOT_FOUND);

  return (
    <article className={`card flex min-w-0 flex-col gap-2.5 border-t-4 px-5 py-4 ${vlm ? "border-t-vlm" : "border-t-ocr"}`}>
      <div className="flex justify-between gap-3">
        <h3 className={`text-[15px] font-semibold ${vlm ? "text-vlm" : "text-ocr-text"}`}>{title}</h3>
        {!p.error && <span className="shrink-0 whitespace-nowrap font-mono text-[13px] text-muted" title={vlm ? undefined : `OCR ${secs(p.ocr_ms)} + text model ${secs(p.llm_ms)}`}>{secs(p.ms)}</span>}
      </div>
      {p.error ? (
        <p role="alert" className="rounded-md bg-bad-soft p-2.5 text-sm text-bad-text">This method failed: {p.error}</p>
      ) : notFound ? (
        <p className="font-reading text-xl text-muted">Not found in the document.</p>
      ) : isShortPlain(answer) ? (
        <p className={`font-reading ${answer.length <= 60 ? "text-2xl" : "text-xl"} leading-snug`}><Marked text={answer} missing={missing} /></p>
      ) : (
        <div className="reading"><ReactMarkdown>{answer}</ReactMarkdown></div>
      )}
      <div className="mt-auto flex flex-wrap gap-x-3.5 gap-y-1 text-[13px] text-muted">
        {side && !p.error && side.answered && reference && side.support != null && (side.support >= 1 ? (
          <span className="inline-flex items-center gap-1.5 text-agree-text"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden><path d="m5 12 5 5 9-10" /></svg>{Math.round(side.support * 100)}% found in the document</span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-warn-text"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden><path d="M12 4 2.5 20h19z" /><path d="M12 10v4M12 17v.5" /></svg>
            {Math.round(side.support * 100)}% found{missing.length > 0 && ` · ${quoteList(missing)} ${missing.length === 1 ? "is" : "are"} not in the document`}</span>
        ))}
        {!p.error && <span>Pages {ranges(p.pages)}{parts > 1 ? `, read in ${parts} parts` : ""}</span>}
        {p.truncated && <span className="text-warn-text">Text was cut to fit the text model; later pages were left out</span>}
      </div>
    </article>
  );
}

function PartsTable({ p }: { p: Partial<AskPayload> }) {
  const rows = ([["vlm", p.vlm], ["ocr", p.ocr]] as const).flatMap(([k, x]) => (x?.batches ?? []).map((b) => ({ k, b })));
  if (!((p.vlm?.batches?.length ?? 0) > 1 || (p.ocr?.batches?.length ?? 0) > 1)) return null;
  return (
    <section aria-label="How each answer was put together" className="card flex flex-col gap-3 px-6 py-5">
      <h2 className="text-lg font-semibold">How each answer was put together</h2>
      <p className="text-[13px] text-muted">Long documents are read in parts that fit the GPU (vision) or the text model's context (OCR). Each part is asked the question; parts that find an answer are combined by the same model.</p>
      <table className="w-full border-collapse text-sm">
        <thead><tr className="text-left text-[13px] text-muted"><th scope="col" className="py-1.5 font-medium">Method</th><th scope="col" className="font-medium">Pages</th><th scope="col" className="font-medium">What that part answered</th><th scope="col" className="text-right font-medium">Time</th></tr></thead>
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
      {(p.vlm?.combined || p.ocr?.combined) && <p className="text-[13px] text-muted">{[p.vlm?.combined && "vision", p.ocr?.combined && "OCR"].filter(Boolean).join(" and ")}: answers from several parts were combined into the final answer.</p>}
    </section>
  );
}

export default function AnswerPair({ p, docId, research, onAskAgain }: {
  p: Partial<AskPayload>; docId: string; research: boolean; onOpenPage: (page: number) => void; onAskAgain?: () => void;
}) {
  const v = p.verification;
  const ranked = p.retrieval?.ranked ?? [];
  const maxScore = Math.max(...ranked.map((r) => r.score), 0.0001);
  const c = p.scorecard;

  return (
    <article className="flex flex-col gap-4">
      {p.demo && <p className="chip self-start border border-warn text-warn-text">Demo mode: these answers come from text-matching stand-ins, not from the models</p>}
      {p.reused_from && (
        <div role="note" className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-rule bg-sheet px-4 py-2.5 text-sm">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted" aria-hidden><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>
          <span>Answered from history: you asked this about the same file on <strong className="font-medium">{new Date(p.reused_from.asked_at * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong>, with the same settings.</span>
          {onAskAgain && <button className="btn-quiet ml-auto h-9 !py-0" onClick={onAskAgain}>Ask again</button>}
        </div>
      )}
      <div className="rise"><Verdict p={p} /></div>
      <div className={`rise grid gap-4 ${p.vlm && p.ocr ? "md:grid-cols-2" : ""}`} style={{ animationDelay: "120ms" }}>
        <AnswerCard tone="vlm" p={p.vlm} side={c?.vlm} reference={!!c?.reference} />
        <AnswerCard tone="ocr" p={p.ocr} side={c?.ocr} reference={!!c?.reference} />
      </div>
      {p.xai && <div className="rise" style={{ animationDelay: "240ms" }}><EvidenceCard x={p.xai} docId={docId} /></div>}
      {c && <CompareChart c={c} timings={p.timings} findings={p.explanation} />}

      {research && (
        <>
          <PartsTable p={p} />
          {v && <section aria-label="Claim by claim" className="card px-6 py-5 text-sm"><ClaimLedger v={v} /></section>}
          {ranked.length > 1 && (
            <section aria-label="Page retrieval" className="card px-6 py-5 text-sm">
              <h2 className="mb-2 text-lg font-semibold">{p.retrieval?.read_all ? "How relevant each page looks to the question" : "Which pages the vision model was given"}</h2>
              <div className="space-y-1">
                {ranked.slice(0, 12).map((r) => {
                  const chosen = p.retrieval?.vlm_pages.includes(r.page);
                  return (
                    <div key={r.page} className="flex items-center gap-3">
                      <span className="w-16 shrink-0 whitespace-nowrap text-muted">Page {r.page + 1}</span>
                      <div className="h-2.5 flex-1 bg-track"><div className={`h-2.5 rounded-r ${chosen ? "bg-vlm" : "bg-rule"}`} style={{ width: `${(r.score / maxScore) * 100}%` }} /></div>
                      <span className="w-12 text-right font-mono text-[13px] text-muted">{r.score.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-2 text-[13px] text-muted">{p.retrieval?.read_all
                ? `Keyword match (BM25 over ${p.retrieval?.corpus === "textlayer" ? "the PDF's text" : "the OCR text"}). Both methods read every page; this only orders them.`
                : `Only the ${p.retrieval?.page_cap} best pages went to the vision model. ${p.retrieval?.match_pages ? "The OCR pipeline saw the same pages." : "The OCR pipeline read every page."}`}</p>
            </section>
          )}
          {(p.audit ?? []).length > 0 && (
            <section aria-label="OCR audit" className="card overflow-x-auto px-6 py-5 text-sm">
              <h2 className="mb-2 text-lg font-semibold">How well OCR read each page</h2>
              <table className="w-full text-left">
                <thead className="text-[13px] text-muted"><tr><th className="py-1 font-medium">Page</th><th className="font-medium">OCR vs the PDF's text</th><th className="font-medium">Images</th><th className="font-medium">Drawings</th><th className="font-medium">Tables</th><th className="font-medium">Flags</th></tr></thead>
                <tbody>
                  {p.audit!.map((a) => (
                    <tr key={a.page} className="border-t border-hair align-top">
                      <td className="py-1.5">{a.page + 1}</td>
                      <td>{a.ocr_vs_layer_similarity == null ? "no text layer" : `${(a.ocr_vs_layer_similarity * 100).toFixed(1)}% (${a.layer_tokens_missed_by_ocr} ${a.layer_tokens_missed_by_ocr === 1 ? "word" : "words"} missed)`}</td>
                      <td>{a.n_images} ({(a.image_area_ratio * 100).toFixed(0)}% of page)</td><td>{a.n_drawings}</td><td>{a.n_tables}</td>
                      <td className="text-warn-text">{a.flags.join("; ") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          {p.timings && (
            <p className="text-[13px] text-muted">
              Retrieval {secs(p.timings.retrieval_ms)} · vision {secs(p.timings.vlm_ms)} · OCR {secs(p.timings.ocr_ms)} (cost of the pages read; cached pages keep their original time) · text model {secs(p.timings.llm_ms)} · total {secs(p.timings.total_ms)}
            </p>
          )}
        </>
      )}
    </article>
  );
}
