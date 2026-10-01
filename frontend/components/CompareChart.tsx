import { pct, secs } from "@/lib/api";
import type { Finding, Scorecard, ScoreSide } from "@/lib/types";
import BarChart, { COLORS, type Group } from "./BarChart";

const pct0 = (x: number) => `${Math.round(x * 100)}%`;
const supportLabel = (s: ScoreSide) => (s.error ? "failed" : !s.answered ? "no answer" : pct(s.support, 0));
const pagesOf = (n: number) => `${n} ${n === 1 ? "page" : "pages"}`;
// A failed pipeline draws no bar: its pages and time say nothing about how it performs.
const read = (s: ScoreSide, n: number) => (s.error ? { v: 0, label: "failed" } : { v: s.pages_read / n, label: `${s.pages_read} of ${pagesOf(n)}` });

/** The two charts and the plain-language findings under every answer. The verdict itself is shown above, by AnswerPair. */
export default function CompareChart({ c, timings, findings }: { c: Scorecard; timings?: Record<string, number>; findings?: Finding[] }) {
  if (!c.vlm || !c.ocr) return null;
  const rest = (findings ?? []).filter((f) => f.kind !== "verdict");
  const SHORT: Record<string, string> = { recognition: "Which read better", speed: "Speed", pages: "Pages" };

  // Chart 1: everything on a 0-100% scale.
  const quality: Group[] = [];
  if (c.reference) {
    quality.push({ name: "Answer found in the document's text", bars: [
      { who: "Vision", segments: [{ value: c.vlm.support ?? 0, color: COLORS.vlm, name: "Vision" }], label: supportLabel(c.vlm),
        tip: `Vision: ${supportLabel(c.vlm)} of the key words and numbers in its answer are printed in the PDF` },
      { who: "OCR", segments: [{ value: c.ocr.support ?? 0, color: COLORS.ocr, name: "OCR" }], label: supportLabel(c.ocr),
        tip: `OCR pipeline: ${supportLabel(c.ocr)} of the key words and numbers in its answer are printed in the PDF` },
    ] });
  }
  const rv = read(c.vlm, c.n_pages), ro = read(c.ocr, c.n_pages);
  quality.push({ name: "Share of the document read", bars: [
    { who: "Vision", segments: [{ value: rv.v, color: COLORS.vlm, name: "Vision" }], label: rv.label,
      tip: c.vlm.error ? "The vision model failed" : `The vision model saw ${c.vlm.pages_read} of ${pagesOf(c.n_pages)}` },
    { who: "OCR", segments: [{ value: ro.v, color: COLORS.ocr, name: "OCR" }], label: ro.label,
      tip: c.ocr.error ? "The OCR pipeline failed" : `The text model saw OCR text from ${c.ocr.pages_read} of ${pagesOf(c.n_pages)}` },
  ] });
  if (c.ocr_read_accuracy != null) {
    quality.push({ name: "OCR text similarity to the PDF's own text", bars: [
      { who: "OCR", segments: [{ value: c.ocr_read_accuracy, color: COLORS.ocr, name: "OCR" }], label: pct(c.ocr_read_accuracy, 1),
        tip: `OCR's text is ${pct(c.ocr_read_accuracy, 1)} similar to the embedded text, compared word by word (how well OCR read the page)` },
    ] });
  }

  // Chart 2: seconds, with the OCR pipeline split into OCR reading and the text model.
  const ocrRead = timings?.ocr_ms ?? 0, llm = timings?.llm_ms ?? 0;
  const time: Group[] = [{ name: "", bars: [
    { who: "Vision", segments: [{ value: c.vlm.error ? 0 : (c.vlm.ms ?? 0) / 1000, color: COLORS.vlm, name: "Vision model" }],
      label: c.vlm.error ? "failed" : secs(c.vlm.ms), tip: c.vlm.error ? "The vision model failed" : `Vision model: ${secs(c.vlm.ms)} to read the page images and answer` },
    { who: "OCR", segments: c.ocr.error ? [{ value: 0, color: COLORS.ocr, name: "OCR reading" }]
        : [{ value: ocrRead / 1000, color: COLORS.ocr, name: "OCR reading" }, { value: llm / 1000, color: COLORS.ocrLight, name: "Text model" }],
      label: c.ocr.error ? "failed" : secs(c.ocr.ms), tip: c.ocr.error ? "The OCR pipeline failed" : `OCR pipeline: ${secs(ocrRead)} OCR reading + ${secs(llm)} text model = ${secs(c.ocr.ms)}` },
  ] }];


  return (
    <>
      <section aria-label="Comparison charts" className="card grid gap-10 px-6 py-5 lg:grid-cols-2">
        <BarChart title="How each method did" groups={quality} max={1} tickFmt={pct0}
          legend={[{ name: "Vision model", color: COLORS.vlm }, { name: "OCR + text model", color: COLORS.ocr }]}
          caption={c.reference ? "Longer is better. Scored against the text embedded in the PDF, which neither method produced."
            : "This file has no embedded text, so the answers cannot be scored against the document."} />
        <BarChart title="Time to answer" groups={time} tickFmt={(v) => `${v} s`}
          legend={[{ name: "Vision model", color: COLORS.vlm }, { name: "OCR reading", color: COLORS.ocr }, { name: "Text model", color: COLORS.ocrLight }]}
          caption="Shorter is better. OCR is cached per document, so its share shrinks on follow-up questions." />
      </section>

      {rest.length > 0 && (
        <section aria-label="What the results mean" className="card flex flex-col gap-3.5 px-6 py-5">
          <h2 className="text-lg font-semibold">What the results mean</h2>
          <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-[200px_minmax(0,1fr)]">
            {rest.map((f) => (
              <div key={f.kind} className="contents">
                <dt className="font-semibold">{SHORT[f.kind] ?? f.title}</dt>
                <dd className="text-ink-soft">{f.text}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t border-hair pt-3 text-[13px] text-muted">
            This checks whether each answer is printed in the document, not whether it answers the question correctly. To measure accuracy, run an experiment with reference answers under Experiments.
          </p>
        </section>
      )}
    </>
  );
}
