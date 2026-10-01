"use client";
import { useEffect, useState } from "react";

/**
 * Shown while a question runs. The backend answers in one request, so this does not claim which step is running;
 * it shows the elapsed time and a range measured on the A4000 (about 0.8 s per page for vision, about 1 s per page
 * for OCR the first time a document is read, plus the text model).
 */
export default function AskProgress({ nPages, pageCap, mode }: { nPages: number; pageCap: number; mode: "both" | "vlm" | "ocr" }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const elapsed = Math.floor((now - start) / 1000);

  const vision = mode !== "ocr", ocr = mode !== "vlm";
  const lo = Math.round((vision ? 0.8 * nPages + 1 : 0) + (ocr ? 1 : 0) + 1);            // OCR already cached
  const hi = Math.round((vision ? 0.9 * nPages + 2 : 0) + (ocr ? 1.1 * nPages + 3 : 0) + 2); // first question on the file
  const parts = Math.ceil(nPages / Math.max(pageCap, 1));
  const steps: { dot: string; who: string; text: string }[] = [
    ...(vision ? [{ dot: "rounded-full bg-vlm", who: "Vision model", text: `reads the ${nPages === 1 ? "page image" : `${nPages} page images`}${parts > 1 ? ` in ${parts} parts of up to ${pageCap} pages, so each part fits in GPU memory` : ""}.` }] : []),
    ...(ocr ? [{ dot: "rounded-[2px] bg-ocr", who: "OCR", text: `turns the ${nPages === 1 ? "page" : `${nPages} pages`} into text, then the text model answers from it.` }] : []),
    ...(vision && ocr ? [{ dot: "rounded-full border-2 border-ink", who: "Comparison", text: "the two answers are checked against each other and against the document." }] : []),
  ];

  return (
    <section role="status" aria-live="polite" aria-label="Answering" className="card flex flex-col gap-4 px-7 py-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-xl font-semibold">Reading {nPages === 1 ? "the page" : `all ${nPages} pages`}{vision && ocr ? " with both methods" : ""}</h2>
        <span className="whitespace-nowrap font-mono text-[28px] font-medium tabular-nums">{elapsed}<span className="ml-1 font-sans text-base font-normal text-muted">s</span></span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-bench" aria-hidden>
        <div className="h-1.5 w-1/3 animate-[slide_1.6s_ease-in-out_infinite] rounded-full bg-ink" />
      </div>
      <ul className="flex flex-col gap-3">
        {steps.map((s) => (
          <li key={s.who} className="flex items-start gap-3"><span className={`mt-[7px] h-2.5 w-2.5 shrink-0 box-border ${s.dot}`} aria-hidden /><span><strong className="font-semibold">{s.who}</strong> {s.text}</span></li>
        ))}
      </ul>
      <p className="border-t border-hair pt-3.5 text-sm text-muted">
        Usually {lo}–{hi} s for this document. The first question on a file is the slowest; OCR is kept, so follow-up questions are quicker.
        {elapsed > hi * 1.5 && " This is taking longer than usual: the GPU may be busy with another job."}
      </p>
    </section>
  );
}
