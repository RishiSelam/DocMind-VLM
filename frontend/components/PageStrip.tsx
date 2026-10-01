"use client";
import { useState } from "react";
import { api } from "@/lib/api";

type Props = { docId: string; nPages: number; vlmPages: number[]; ocrPages: number[]; onOpen: (page: number) => void };

export default function PageStrip({ docId, nPages, vlmPages, ocrPages, onOpen }: Props) {
  const [shown, setShown] = useState(30);
  const n = Math.min(nPages, shown);
  const asked = vlmPages.length > 0 || ocrPages.length > 0;
  return (
    <div className="flex flex-col gap-2" aria-label="Pages">
      <div className="flex gap-2.5 overflow-x-auto pb-0.5">
        {Array.from({ length: n }, (_, i) => i + 1).map((pg) => {
          const v = vlmPages.includes(pg), o = ocrPages.includes(pg);
          return (
            <button key={pg} onClick={() => onOpen(pg)} title={`Open page ${pg}${v ? " · read by the vision model" : ""}${o ? " · read by OCR" : ""}`}
              className="flex shrink-0 flex-col overflow-hidden rounded border border-rule bg-paper hover:border-ink">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={api.pageImageUrl(docId, pg, 40)} alt={`Page ${pg}`} loading="lazy" className="h-[76px] w-auto min-w-[56px] object-contain" />
              <span className="flex items-center justify-between gap-2 bg-strip px-1.5 py-0.5 text-xs">
                {pg}
                {asked && (
                  <span className="flex gap-[3px]" aria-hidden>
                    <span className={`h-1.5 w-1.5 rounded-full ${v ? "bg-vlm" : "bg-rule"}`} />
                    <span className={`h-1.5 w-1.5 rounded-[1px] ${o ? "bg-ocr" : "bg-rule"}`} />
                  </span>
                )}
              </span>
            </button>
          );
        })}
        {n < nPages && <button className="btn-quiet shrink-0 self-center" onClick={() => setShown(shown + 30)}>Show {Math.min(30, nPages - n)} more</button>}
      </div>
      {asked && (
        <p className="flex flex-wrap gap-4 text-[13px] text-muted">
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-vlm" aria-hidden />read by the vision model</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-[1px] bg-ocr" aria-hidden />read by OCR</span>
          <span>on the last question</span>
        </p>
      )}
    </div>
  );
}
