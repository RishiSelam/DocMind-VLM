"use client";
import { api } from "@/lib/api";
import { CAUSE, KIND, WHO_NAME, causeTone } from "@/lib/causes";
import type { Analysis as A, Region, WordRead } from "@/lib/types";

const WHO_CLS = { vlm: "bg-vlm-soft text-vlm", ocr: "bg-ocr-soft text-ocr-text", both: "bg-bench text-ink" } as const;
const BETTER_CLS = { vlm: "bg-vlm-soft text-vlm", ocr: "bg-ocr-soft text-ocr-text", same: "bg-agree-soft text-agree-text", undecided: "bg-bench text-ink" } as const;
const BASIS = { textlayer: "Judged against the PDF's own text", closer_look: "Judged by an enlarged re-reading of the region" } as const;

/** One word as a method rendered it: ✓ right, ✗ misread (as what), – not in its output. */
function Read({ r, word }: { r: WordRead; word: string }) {
  if (r.status === "right") return <span className="text-agree-text">✓ {r.as ?? word}</span>;
  if (r.status === "misread") return <span className="text-bad-text">✗ {r.as}</span>;
  return <span className="text-muted">–</span>;
}

function RegionRow({ r, docId }: { r: Region; docId: string }) {
  const pad = [Math.max(0, r.box[0] - 0.01), Math.max(0, r.box[1] - 0.01), Math.min(1, r.box[2] + 0.01), Math.min(1, r.box[3] + 0.01)];
  const verdict = r.better === "vlm" ? { t: "Vision read this part right, OCR did not", c: "text-vlm" }
    : r.better === "ocr" ? { t: "OCR read this part right, vision did not", c: "text-ocr-text" }
      : r.better === "both" ? { t: "Both read this part right", c: "text-agree-text" }
        : r.better === "neither" ? { t: "Neither got this part right", c: "text-bad-text" } : { t: "Not checked: no neutral reference", c: "text-muted" };
  return (
    <li className="flex flex-col gap-2 border-t border-hair pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="chip bg-bench">{KIND[r.kind] ?? r.kind} · page {r.page + 1}</span>
        <span className={r.conf < 0.9 ? "text-warn-text" : "text-muted"}>OCR confidence {Math.round(r.conf * 100)}%{r.conf < 0.9 ? " (low)" : ""}</span>
        <span className={`ml-auto font-medium ${verdict.c}`}>{verdict.t}</span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={api.cropUrl(docId, r.page + 1, pad)} alt={`The part of page ${r.page + 1} that holds the answer`} className="max-h-20 w-full rounded-md border border-rule bg-paper object-contain object-left" />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-sm">
          <thead className="text-left text-[13px] text-muted">
            <tr><th className="py-1 font-medium">On the page</th><th className="font-medium text-vlm">Vision answer</th><th className="font-medium text-ocr-text">OCR's text</th><th className="font-medium text-ocr-text">OCR pipeline answer</th></tr>
          </thead>
          <tbody>
            {r.words.map((w) => (
              <tr key={w.word} className="border-t border-hair">
                <td className="py-1.5 pr-3 font-reading">{w.word}{w.in_page === false && <span className="text-[13px] text-muted"> (not in the PDF's text)</span>}</td>
                <td className="pr-3"><Read r={w.vision} word={w.word} /></td>
                <td className="pr-3"><Read r={w.ocr_text} word={w.word} /></td>
                <td><Read r={w.ocr_answer} word={w.word} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </li>
  );
}

/** Which method did better on this question, the cause behind each answer, and which part of the page each read right. */
export default function Analysis({ a, docId }: { a: A; docId: string }) {
  return (
    <section aria-label="Which method did better, and why" className="card flex flex-col gap-4 px-6 py-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <h2 className="text-lg font-semibold">Which method did better, and why</h2>
        <span className={`chip font-medium ${BETTER_CLS[a.better]}`}>{a.headline}</span>
        {a.basis && <span className="chip bg-bench">{BASIS[a.basis]}</span>}
      </div>
      {a.summary && <p className="text-ink-soft">{a.summary}</p>}
      {a.why.length > 0 && (
        <ul className="flex flex-col gap-3">
          {a.why.map((w, i) => (
            <li key={i} className="flex flex-col gap-1.5 sm:flex-row sm:gap-3">
              <span className="flex shrink-0 gap-1.5 sm:w-56 sm:flex-col sm:items-start">
                <span className={`chip font-medium ${WHO_CLS[w.who]}`}>{w.who === "both" ? "Both methods" : WHO_NAME[w.who]}</span>
                <span className={`chip ${causeTone(w.cause)}`}>{CAUSE[w.cause] ?? w.label}</span>
              </span>
              <span className="text-ink-soft">{w.text}</span>
            </li>
          ))}
        </ul>
      )}
      {a.regions.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-hair pt-4">
          <h3 className="font-semibold">Which part of the page each method read right</h3>
          <ul className="flex flex-col gap-3">{a.regions.map((r, i) => <RegionRow key={i} r={r} docId={docId} />)}</ul>
          <p className="text-[13px] text-muted">The line OCR found for each word of the answer, with what each method made of it. “OCR's text” is what OCR read there; “OCR pipeline answer” is what the text model answered from it, so the two can differ when the text model repairs or repeats an OCR error.</p>
        </div>
      )}
    </section>
  );
}
