"use client";
import { useState } from "react";
import { api } from "@/lib/api";

type Props = { docId: string; nPages: number; vlmPages: number[]; ocrPages: number[]; onOpen: (page: number) => void };

export default function PageStrip({ docId, nPages, vlmPages, ocrPages, onOpen }: Props) {
  const [shown, setShown] = useState(30);
  const n = Math.min(nPages, shown);
  return (
    <div className="border-b border-rule bg-sheet px-4 py-2" aria-label="Pages">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {Array.from({ length: n }, (_, i) => i + 1).map((pg) => {
          const v = vlmPages.includes(pg), o = ocrPages.includes(pg);
          return (
            <button key={pg} onClick={() => onOpen(pg)} title={`Page ${pg}${v ? " · shown to the vision model" : ""}${o ? " · read by OCR" : ""}`}
              className={`relative shrink-0 border bg-white ${v ? "border-vlm shadow-[0_0_0_2px_#0B7A75]" : "border-rule"} hover:border-ink`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={api.pageImageUrl(docId, pg, 30)} alt={`Page ${pg}`} loading="lazy" className="h-20 w-auto" />
              <span className="absolute bottom-0 left-0 bg-ink/80 px-1 text-[0.65rem] text-white">{pg}</span>
              {o && <span className="absolute right-0 top-0 h-2 w-2 bg-ocr" aria-hidden />}
            </button>
          );
        })}
        {n < nPages && <button className="btn-quiet shrink-0 self-center" onClick={() => setShown(shown + 30)}>Show {Math.min(30, nPages - n)} more</button>}
      </div>
      {(vlmPages.length > 0 || ocrPages.length > 0) && (
        <p className="text-xs text-muted"><span className="text-vlm">Teal outline</span>: pages given to the vision model on the last question. <span className="text-ocr">Amber corner</span>: pages the OCR pipeline read{ocrPages.length === nPages ? " (all)" : ""}.</p>
      )}
    </div>
  );
}
