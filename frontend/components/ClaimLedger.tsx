import type { Pair, PairLabel, Verification } from "@/lib/types";

const LABEL: Record<PairLabel, { text: string; cls: string }> = {
  agree: { text: "Agree", cls: "text-agree" },
  partial: { text: "Partly", cls: "text-warn" },
  conflict: { text: "Conflict", cls: "bg-bad-soft text-bad" },
  only_vlm: { text: "Vision only", cls: "text-vlm" },
  only_ocr: { text: "OCR only", cls: "text-ocr" },
};

function Row({ p }: { p: Pair }) {
  const l = LABEL[p.label];
  return (
    <tr className={`border-t border-rule align-top ${p.label === "conflict" ? "bg-bad-soft/50" : ""}`}>
      <td className="w-[38%] py-1.5 pr-3 font-reading">{p.vlm ?? <span className="text-muted">-</span>}</td>
      <td className={`w-[24%] whitespace-nowrap px-2 py-1.5 text-center text-sm font-medium ${l.cls}`}>{l.text}{p.score > 0 ? ` · ${(p.score * 100).toFixed(0)}%` : ""}</td>
      <td className="w-[38%] py-1.5 pl-3 font-reading">{p.ocr ?? <span className="text-muted">-</span>}</td>
    </tr>
  );
}

export default function ClaimLedger({ v }: { v: Verification }) {
  const s = v.ocr_support;
  return (
    <section aria-label="Claim comparison" className="mt-4">
      <h4 className="mb-1 text-sm font-semibold">Claim by claim</h4>
      {v.note && <p className="mb-2 text-sm text-muted">{v.note}</p>}
      {v.pairs.length > 0 && (
        <table className="w-full text-[0.95rem]">
          <thead><tr className="text-left text-sm text-muted"><th className="pb-1 font-normal text-vlm">Vision model says</th><th /><th className="pb-1 pl-3 font-normal text-ocr">OCR + text model says</th></tr></thead>
          <tbody>{v.pairs.map((p, i) => <Row key={i} p={p} />)}</tbody>
        </table>
      )}
      {(v.numbers_only_vlm.length > 0 || v.numbers_only_ocr.length > 0) && (
        <p className="mt-2 text-sm">
          Numbers that appear on one side only: {v.numbers_only_vlm.length > 0 && <span className="text-vlm">vision {v.numbers_only_vlm.join(", ")}</span>}
          {v.numbers_only_vlm.length > 0 && v.numbers_only_ocr.length > 0 && "; "}
          {v.numbers_only_ocr.length > 0 && <span className="text-ocr">OCR {v.numbers_only_ocr.join(", ")}</span>}
        </p>
      )}
      {s && (
        <div className="mt-3 border-t border-rule pt-2 text-sm">
          <h4 className="mb-1 font-semibold">Did OCR capture what the vision model answered?</h4>
          <p>
            {s.coverage == null ? "Nothing to check." : `${(s.coverage * 100).toFixed(0)}% of the vision answer's key words are in the OCR text.`}{" "}
            {s.found.length} exact, {s.near.length} near-match, {s.missing.length} absent.
          </p>
          {s.near.length > 0 && <p className="mt-1">Probable OCR misreads: {s.near.map((n) => <span key={n.token} className="mr-2 rounded-[3px] bg-ocr-soft px-1.5 py-0.5">{n.token} read as {n.ocr_token}</span>)}</p>}
          {s.missing.length > 0 && <p className="mt-1">Not in the OCR text: {s.missing.map((m) => <span key={m} className="mr-2 rounded-[3px] bg-bad-soft px-1.5 py-0.5 text-bad">{m}</span>)}</p>}
          <p className="mt-1 text-muted">{s.note}</p>
        </div>
      )}
    </section>
  );
}
