"use client";
import { useRef, useState } from "react";
import type { Doc } from "@/lib/types";

const STEPS = [
  { band: "border-t-vlm", who: "Reader 1", whoCls: "text-vlm", title: "The vision model looks at each page", text: "Qwen2.5-VL reads the page images directly: tables, stamps, layout and handwriting included." },
  { band: "border-t-ocr", who: "Reader 2", whoCls: "text-ocr-text", title: "OCR turns the pages into text", text: "The text is handed to Qwen2.5, which answers from the words alone." },
  { band: "border-t-ink", who: "Then", whoCls: "text-muted", title: "You see which answer to trust", text: "Both answers side by side, checked against the document, with a plain-language verdict." },
];

export default function EmptyState({ onUpload, uploading, error, recent, onOpen }: {
  onUpload: (f: File) => Promise<void>; uploading: boolean; error: string | null; recent: Doc[]; onOpen: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const pick = (files: FileList | null) => { if (files?.[0]) void onUpload(files[0]); };

  return (
    <div className="mx-auto flex w-full max-w-[920px] flex-col gap-8 px-6 py-16">
      <div className="flex flex-col gap-2.5">
        <h1 className="font-reading text-5xl font-semibold leading-[1.1]">Ask a document, twice.</h1>
        <p className="max-w-[640px] text-lg text-ink-soft">Two independent readers answer every question: one looks at the pages, one reads their text. When they agree you can move on; when they don't, DocMind shows you why.</p>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
        className={`flex flex-col items-center gap-3.5 rounded-[14px] border-2 border-dashed px-6 py-12 text-center transition-colors ${drag ? "border-ink bg-paper" : "border-muted/50 bg-sheet"}`}>
        <input ref={input} type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-bench" aria-hidden>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M12 18v-6m-3 3 3-3 3 3" /></svg>
        </span>
        <span className="text-xl font-semibold">{drag ? "Drop to upload" : "Drop a PDF or an image here"}</span>
        <button className="btn h-12 rounded-lg !px-6 text-base font-semibold" disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "Uploading…" : "Choose a file"}</button>
        <span className="text-sm text-muted">PDF, PNG, JPG or TIFF · any number of pages · scans and photos work too</span>
        {error && <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-text">{error}</p>}
      </div>

      <ol className="grid gap-4 sm:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.who} className={`card flex flex-col gap-1.5 border-t-4 px-5 py-4 ${s.band}`}>
            <span className={`text-[13px] font-semibold ${s.whoCls}`}>{s.who}</span>
            <span className="text-[17px] font-semibold leading-snug">{s.title}</span>
            <span className="text-ink-soft">{s.text}</span>
          </li>
        ))}
      </ol>

      {recent.length > 0 && (
        <section aria-label="Recent documents" className="flex flex-col gap-2.5">
          <h2 className="eyebrow">Or continue with a recent document</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            {recent.slice(0, 3).map((d) => (
              <button key={d.id} onClick={() => onOpen(d.id)} className="flex min-h-16 flex-col rounded-lg border border-rule bg-sheet px-4 py-3 text-left hover:border-ink">
                <span className="truncate font-medium">{d.filename}</span>
                <span className="text-[13px] text-muted">{d.n_pages} {d.n_pages === 1 ? "page" : "pages"}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
