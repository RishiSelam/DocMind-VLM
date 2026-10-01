"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { OcrPage } from "@/lib/types";

type Props = { docId: string; page: number; nPages: number; research: boolean; onClose: () => void; onPage: (n: number) => void };

export default function PageViewer({ docId, page, nPages, research, onClose, onPage }: Props) {
  const [tab, setTab] = useState<"page" | "ocr">("page");
  const [ocr, setOcr] = useState<OcrPage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => { closeRef.current?.focus(); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && page < nPages) onPage(page + 1);
      if (e.key === "ArrowLeft" && page > 1) onPage(page - 1);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [page, nPages, onClose, onPage]);

  useEffect(() => {
    setOcr(null); setErr(null); setSize(null);
    if (!(research && tab === "ocr")) return;
    let alive = true;
    setLoading(true);
    api.pageOcr(docId, page).then((r) => alive && setOcr(r)).catch((e) => alive && setErr(e.message)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [docId, page, research, tab]);

  const showOcr = research && tab === "ocr";
  const dpi = showOcr && ocr ? ocr.render_dpi : 110;

  return (
    <div role="dialog" aria-modal="true" aria-label={`Page ${page}`} className="fixed inset-0 z-20 flex items-stretch justify-center bg-ink/60 p-3 md:p-8" onClick={onClose}>
      <div className="flex max-h-full w-full max-w-5xl flex-col bg-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-rule px-3 py-2 text-sm">
          <button className="btn-quiet !px-2 !py-0.5" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">‹</button>
          <span>Page {page} of {nPages}</span>
          <button className="btn-quiet !px-2 !py-0.5" disabled={page >= nPages} onClick={() => onPage(page + 1)} aria-label="Next page">›</button>
          {research && (
            <div className="ml-4 flex gap-3">
              {(["page", "ocr"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`pb-0.5 ${tab === t ? "border-b-2 border-ink font-semibold" : "text-muted"}`}>{t === "page" ? "Page" : "What OCR read"}</button>
              ))}
            </div>
          )}
          <button ref={closeRef} className="btn-quiet ml-auto !px-2 !py-0.5" onClick={onClose}>Close</button>
        </div>
        <div className="grid min-h-0 flex-1 gap-4 overflow-auto p-3 md:grid-cols-2">
          <div className="relative self-start">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={api.pageImageUrl(docId, page, dpi)} alt={`Page ${page}`} className="block w-full border border-rule bg-white"
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
            {showOcr && ocr && size && (
              <svg viewBox={`0 0 ${size.w} ${size.h}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
                {ocr.boxes.map((b, i) => (
                  <rect key={i} x={b.x0} y={b.y0} width={b.x1 - b.x0} height={b.y1 - b.y0} fill="none" strokeWidth={Math.max(size.w / 500, 1.5)}
                    stroke={b.score < 0.8 ? "#B42318" : "#A8580C"} />
                ))}
              </svg>
            )}
          </div>
          {!showOcr ? (
            <p className="text-sm text-muted">{research ? "Switch to “What OCR read” to see the text OCR extracted, with each recognised line boxed on the page. Red boxes are lines OCR was unsure about." : "This is the page as the vision model sees it."}</p>
          ) : (
            <div className="min-w-0 text-sm">
              {loading && <p className="text-muted">Running OCR on this page…</p>}
              {err && <p role="alert" className="rounded-[4px] bg-bad-soft p-2 text-bad">{err}</p>}
              {ocr && (
                <>
                  <p className="mb-2 text-muted">{ocr.engine} · {ocr.boxes.length} lines · mean confidence {ocr.mean_conf == null ? "n/a" : (ocr.mean_conf * 100).toFixed(1) + "%"} · {Math.round(ocr.ms)} ms</p>
                  {ocr.audit.flags.length > 0 && <ul className="mb-2 list-disc pl-5 text-warn">{ocr.audit.flags.map((f) => <li key={f}>{f}</li>)}</ul>}
                  {ocr.audit.ocr_vs_layer_similarity != null && <p className="mb-2">Matches the PDF's own text layer at {(ocr.audit.ocr_vs_layer_similarity * 100).toFixed(1)}%; {ocr.audit.layer_tokens_missed_by_ocr} words missed.</p>}
                  <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap border border-rule bg-white p-2 font-reading text-[0.95rem]">{ocr.text || "(OCR found no text on this page)"}</pre>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
