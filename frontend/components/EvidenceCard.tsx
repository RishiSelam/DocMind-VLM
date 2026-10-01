"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { EvBox, Xai } from "@/lib/types";

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const boxStyle = (b: number[]) => ({ left: pct(b[0]), top: pct(b[1]), width: pct(b[2] - b[0]), height: pct(b[3] - b[1]) });
const quote = (ws: string[]) => ws.map((w) => `“${w}”`).join(", ");
const bare = (t: string) => t.trim().replace(/[.\s]+$/, "");   // quoted text ends without its own full stop

const PLACE: Record<string, string> = {
  "same place": "Both methods found the answer in the same place",
  "same page": "Both methods used the same page, but different spots on it",
  "different pages": "The two methods took the answer from different pages",
};

function Overlay({ docId, page, vision, ocr, reference }: { docId: string; page: number; vision: EvBox | null; ocr: EvBox[]; reference: EvBox[] }) {
  return (
    <figure className="m-0 flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-md border border-rule bg-paper">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={api.pageImageUrl(docId, page + 1, 110)} alt={`Page ${page + 1} with the evidence marked`} className="block h-auto w-full" />
        {reference.filter((r) => r.page === page).map((r, i) => (
          <span key={`r${i}`} className="absolute rounded-[2px] border-2 border-dashed border-ink/70" style={boxStyle(r.box)} aria-hidden />
        ))}
        {ocr.filter((o) => o.page === page).map((o, i) => (
          <span key={`o${i}`} className="absolute rounded-[3px] border-2 border-ocr bg-ocr/15" style={boxStyle(o.box)} aria-hidden />
        ))}
        {vision && vision.page === page && <span className="absolute rounded-[3px] border-[3px] border-vlm bg-vlm/10" style={boxStyle(vision.box)} aria-hidden />}
      </div>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3.5 rounded-[2px] border-2 border-vlm" aria-hidden />vision model</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3.5 rounded-[2px] border-2 border-ocr bg-ocr/15" aria-hidden />OCR</span>
        {reference.length > 0 && <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-3.5 rounded-[2px] border-2 border-dashed border-ink/70" aria-hidden />where the PDF prints it</span>}
        <span>Page {page + 1}</span>
      </figcaption>
    </figure>
  );
}

/** Where each answer came from, whether it depended on that place, and a closer look when the answers differ. */
export default function EvidenceCard({ x, docId }: { x: Xai; docId: string }) {
  const pages = Array.from(new Set([x.vision?.page, x.ocr[0]?.page].filter((p): p is number => p != null)));
  const [page, setPage] = useState(pages[0] ?? 0);
  if (x.skipped || pages.length === 0) return null;
  const lc = x.look_closer, f = x.faithfulness;

  const findings: { tone: "good" | "warn" | "plain"; text: React.ReactNode }[] = [];
  if (x.agreement) findings.push({ tone: x.agreement === "same place" ? "good" : "warn", text: `${PLACE[x.agreement]}${x.vision ? ` (page ${x.vision.page + 1})` : ""}.` });
  if (!x.vision) findings.push({ tone: "plain", text: "The vision model did not point to a place for its answer." });
  if (x.vision_at_reference) findings.push({ tone: x.vision_at_reference === "same place" ? "good" : "warn",
    text: x.vision_at_reference === "same place" ? "The vision model's region is where the PDF itself prints the answer." : "The vision model's region is not where the PDF prints the answer." });
  if (lc) findings.push({ tone: lc.supports ? "good" : "plain", text: (
    <>A closer look at the region reads: <q className="font-reading">{bare(lc.transcription.split("\n").find((l) => [...lc.vision_confirmed, ...lc.ocr_confirmed, ...lc.vision_not_seen, ...lc.ocr_not_seen].some((w) => l.toLowerCase().includes(w))) ?? lc.transcription.split("\n")[0])}</q>.{" "}
      {lc.supports === "vlm" ? <>That confirms the vision answer{lc.ocr_not_seen.length ? <>: {quote(lc.ocr_not_seen)} is not there</> : null}.</>
        : lc.supports === "ocr" ? <>That confirms the OCR answer{lc.vision_not_seen.length ? <>: {quote(lc.vision_not_seen)} is not there</> : null}.</>
          : "It does not settle which answer is right."}</>) });
  for (const [k, name] of [["vlm", "vision"], ["ocr", "OCR"]] as const) {
    const r = f[k];
    if (!r) continue;
    findings.push({ tone: r.survived ? "warn" : "good", text: r.survived
      ? <>With its evidence removed, the {name} answer stays the same (“{bare(r.answer_without_evidence)}”): the highlight may not be what it relied on.</>
      : <>With its evidence removed, the {name} answer becomes “{bare(r.answer_without_evidence)}”: it relied on that region.</> });
  }

  return (
    <section aria-label="Where the answer came from" className="card grid gap-6 px-6 py-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="flex flex-col gap-2">
        {pages.length > 1 && (
          <div role="group" aria-label="Page" className="flex gap-1.5">
            {pages.map((p) => <button key={p} onClick={() => setPage(p)} aria-pressed={page === p} className={`h-8 rounded-full px-3 text-[13px] ${page === p ? "bg-primary text-on-primary" : "border border-rule"}`}>Page {p + 1}</button>)}
          </div>
        )}
        <Overlay docId={docId} page={page} vision={x.vision} ocr={x.ocr} reference={x.reference} />
      </div>
      <div className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Where the answer came from</h2>
        <ul className="flex flex-col gap-2.5">
          {findings.map((fi, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className={`mt-[7px] h-2 w-2 shrink-0 rounded-full ${fi.tone === "good" ? "bg-agree" : fi.tone === "warn" ? "bg-warn" : "bg-muted"}`} aria-hidden />
              <span className="text-ink-soft">{fi.text}</span>
            </li>
          ))}
        </ul>
        {lc && (
          <figure className="m-0 flex flex-col gap-1.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={api.cropUrl(docId, lc.page + 1, lc.box)} alt="The enlarged region the vision model re-read" className="max-h-28 w-full rounded-md border border-rule bg-paper object-contain object-left" />
            <figcaption className="text-[13px] text-muted">The enlarged region (page {lc.page + 1}) that was read again</figcaption>
          </figure>
        )}
        <p className="border-t border-hair pt-3 text-[13px] text-muted">The highlights come from the models themselves: the vision model is asked where it read the answer, and OCR records where each word is. Removing the evidence and asking again tests whether the highlight is what the answer really depended on.</p>
      </div>
    </section>
  );
}
