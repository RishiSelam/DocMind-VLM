import { pct, secs } from "@/lib/api";
import type { Experiment, Metrics } from "@/lib/types";
import BarChart, { COLORS, type Group } from "./BarChart";

const LEGEND = [{ name: "Vision model", color: COLORS.vlm }, { name: "OCR + text model", color: COLORS.ocr }];

function pair(name: string, v: number, o: number, fmt: (x: number) => string, scale = 1, what = ""): Group {
  return { name, bars: [
    { who: "Vision", segments: [{ value: v * scale, color: COLORS.vlm, name: "Vision" }], label: fmt(v), tip: `Vision model, ${name.toLowerCase()}: ${fmt(v)}${what}` },
    { who: "OCR", segments: [{ value: o * scale, color: COLORS.ocr, name: "OCR" }], label: fmt(o), tip: `OCR + text model, ${name.toLowerCase()}: ${fmt(o)}${what}` },
  ] };
}

/** Plain-language reading of an experiment's numbers. */
function interpret(m: Required<Pick<Metrics, "vlm" | "ocr" | "n">> & Metrics, winner: "vlm" | "ocr" | "none" | null): [string, string][] {
  const out: [string, string][] = [];
  const gap = (m.vlm.anls - m.ocr.anls) * 100;
  out.push(["Accuracy", Math.abs(gap) < 0.05
    ? `Both pipelines scored the same: ${pct(m.vlm.anls)} ANLS and ${pct(m.vlm.em)} vs ${pct(m.ocr.em)} exact match on ${m.n} questions.`
    : `The ${gap > 0 ? "vision model" : "OCR pipeline"} scored ${Math.abs(gap).toFixed(1)} points higher on ANLS (${pct(m.vlm.anls)} vs ${pct(m.ocr.anls)}). ${
      winner === "none" ? "With this many questions the gap could be chance; add questions before relying on it." : "The gap is larger than chance would explain on this sample."}`]);
  const dv = m.vlm.latency_ms.mean, dO = m.ocr.latency_ms.mean;
  const fast = dv < dO ? "vision model" : "OCR pipeline";
  out.push(["Speed", `The ${fast} was faster on average (${secs(Math.min(dv, dO))} vs ${secs(Math.max(dv, dO))} per question, ${(Math.max(dv, dO) / Math.max(Math.min(dv, dO), 1)).toFixed(1)}x). The 95th percentile shows the slow cases: ${secs(m.vlm.latency_ms.p95)} for vision, ${secs(m.ocr.latency_ms.p95)} for OCR.`]);
  const bad = [m.vlm.abstain_rate, m.ocr.abstain_rate, m.vlm.error_rate, m.ocr.error_rate].some((x) => x > 0);
  out.push(["Reliability", bad
    ? `Vision said "not found" on ${pct(m.vlm.abstain_rate)} and failed on ${pct(m.vlm.error_rate)} of questions; OCR said "not found" on ${pct(m.ocr.abstain_rate)} and failed on ${pct(m.ocr.error_rate)}.`
    : "Neither pipeline failed or gave up on any question."]);
  const acc = winner === "vlm" ? "the vision model is more accurate" : winner === "ocr" ? "the OCR pipeline is more accurate" : "neither is measurably more accurate";
  let bottom = `On this set ${acc}, and the ${fast} is faster.`;
  if (m.ocr_answer_coverage != null && m.ocr_answer_coverage > 0.97)
    bottom += " The set is easy for OCR (it captured nearly every answer), so it cannot show where vision reading helps. Test on scans, tables or charts to separate them.";
  out.push(["Bottom line", bottom]);
  return out;
}

export default function MetricsPanel({ exp }: { exp: Experiment }) {
  const m: Metrics = exp.metrics;
  if (!m.n || !m.vlm || !m.ocr) return <p className="text-sm text-muted">No scored items yet.</p>;
  const d = m.paired?.anls_vlm_minus_ocr;
  const sig = d ? d.ci_low > 0 || d.ci_high < 0 : false;
  const mc = m.paired?.em_mcnemar;
  const rows: [string, string, string][] = [
    ["Said “not found”", pct(m.vlm.abstain_rate), pct(m.ocr.abstain_rate)],
    ["Failed to answer", pct(m.vlm.error_rate), pct(m.ocr.error_rate)],
  ];
  // The winner is only named when the bootstrap interval on the ANLS difference excludes zero.
  const winner = !d ? null : !sig ? "none" : d.diff > 0 ? "vlm" : "ocr";
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {winner && (
        <div className={`border-l-4 pl-2 md:col-span-2 ${winner === "vlm" ? "border-vlm" : winner === "ocr" ? "border-ocr" : "border-rule"}`}>
          <h3 className="font-semibold">
            {winner === "vlm" ? "More accurate on this set: the vision model" : winner === "ocr" ? "More accurate on this set: OCR + text model" : "No clear winner on this set"}
          </h3>
          <p className="text-sm text-muted">
            {winner === "none" && d!.diff === 0
              ? `ANLS: vision ${pct(m.vlm.anls)}, OCR ${pct(m.ocr.anls)}. Both scored exactly the same.`
              : winner === "none"
              ? `ANLS: vision ${pct(m.vlm.anls)}, OCR ${pct(m.ocr.anls)}. The difference could be chance at this sample size.`
              : `ANLS: vision ${pct(m.vlm.anls)}, OCR ${pct(m.ocr.anls)}. The 95% interval on the difference excludes zero.`}
          </p>
        </div>
      )}
      <div className="space-y-5">
        <BarChart title={`Accuracy on ${m.n} questions`} max={1} tickFmt={(x) => `${Math.round(x * 100)}%`} legend={LEGEND}
          groups={[pair("ANLS (soft string match)", m.vlm.anls, m.ocr.anls, (x) => pct(x)), pair("Exact match", m.vlm.em, m.ocr.em, (x) => pct(x)),
            pair("Contains the reference answer", m.vlm.contains, m.ocr.contains, (x) => pct(x))]}
          caption="Longer is better. ANLS gives partial credit for near-misses such as small typos; exact match gives none." />
        <BarChart title="Time per question (seconds)" tickFmt={(x) => `${x} s`} legend={LEGEND}
          groups={[pair("Mean", m.vlm.latency_ms.mean, m.ocr.latency_ms.mean, secs, 1 / 1000), pair("Median", m.vlm.latency_ms.p50, m.ocr.latency_ms.p50, secs, 1 / 1000),
            pair("95th percentile (slow cases)", m.vlm.latency_ms.p95, m.ocr.latency_ms.p95, secs, 1 / 1000)]}
          caption="Shorter is better. OCR time is the recorded cost of OCR on the pages read plus the text model's time; cached OCR keeps its original cost." />
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-muted"><th /><th className="font-normal text-vlm">Vision</th><th className="font-normal text-ocr">OCR + text</th></tr></thead>
          <tbody>{rows.map(([k, a, b]) => <tr key={k} className="border-t border-rule"><td className="py-1 text-muted">{k}</td><td>{a}</td><td>{b}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="text-sm">
        <h3 className="mb-1 font-semibold">What the results mean</h3>
        <dl className="mb-4 space-y-2">
          {interpret({ ...m, n: m.n, vlm: m.vlm, ocr: m.ocr }, winner).map(([k, t]) => <div key={k}><dt className="font-medium">{k}</dt><dd>{t}</dd></div>)}
        </dl>
        <h3 className="mb-2 font-semibold">Is the difference real?</h3>
        {d && (
          <p>
            ANLS, vision minus OCR: <strong>{d.diff >= 0 ? "+" : ""}{d.diff.toFixed(3)}</strong> (95% bootstrap interval {d.ci_low.toFixed(3)} to {d.ci_high.toFixed(3)}).{" "}
            {sig ? "The interval excludes zero on this sample." : "The interval includes zero, so this sample cannot separate the two."}
          </p>
        )}
        {mc && <p className="mt-2">Exact match, discordant questions: vision alone was right on {mc.a_only}, OCR alone on {mc.b_only} (exact McNemar p = {mc.p_value.toFixed(3)}).</p>}
        <h3 className="mb-1 mt-4 font-semibold">Where OCR loses information</h3>
        <p>The reference answer appears in the OCR text for <strong>{pct(m.ocr_answer_coverage)}</strong> of questions. That is the ceiling for any text model reading this OCR.</p>
        <p className="mt-1">Vision got {m.ocr_loss_cases ?? 0} questions right whose answer never made it into the OCR text.</p>
        <p className="mt-1">The two pipelines gave different answers on <strong>{pct(m.disagreement_rate)}</strong> of questions.</p>
        {m.ocr_answer_coverage != null && m.ocr_answer_coverage > 0.97 && (
          <p className="mt-3 rounded-[4px] bg-ocr-soft p-2">OCR captured nearly every answer, so this set leaves little room for the vision model to win. If both scores are close to the ceiling, add harder pages (tables, forms, low-quality scans) before drawing conclusions.</p>
        )}
      </div>
    </div>
  );
}
