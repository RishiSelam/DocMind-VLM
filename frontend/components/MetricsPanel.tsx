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
  if (!m.n || !m.vlm || !m.ocr) return <p className="card px-6 py-5 text-muted">No scored questions yet.</p>;
  const d = m.paired?.anls_vlm_minus_ocr;
  const sig = d ? d.ci_low > 0 || d.ci_high < 0 : false;
  const mc = m.paired?.em_mcnemar;
  const rows: [string, string, string][] = [
    ["Said “not found”", pct(m.vlm.abstain_rate), pct(m.ocr.abstain_rate)],
    ["Failed to answer", pct(m.vlm.error_rate), pct(m.ocr.error_rate)],
  ];
  // A winner is only named when the bootstrap interval on the ANLS difference excludes zero.
  const winner = !d ? null : !sig ? "none" : d.diff > 0 ? "vlm" : "ocr";
  const all = m.vlm.anls === 1 && m.ocr.anls === 1;
  const faster = m.vlm.latency_ms.mean < m.ocr.latency_ms.mean ? "vision model" : "OCR pipeline";

  const title = winner === "vlm" ? "More accurate on this set: the vision model"
    : winner === "ocr" ? "More accurate on this set: OCR + text model"
      : all ? `No winner on this set: both answered all ${m.n} questions correctly`
        : "No clear winner on this set";
  const text = winner === "none" || !winner
    ? `ANLS: vision ${pct(m.vlm.anls)}, OCR ${pct(m.ocr.anls)}. ${d && d.diff === 0 ? "Both scored exactly the same." : "The difference could be chance at this sample size."} The ${faster} was faster (${secs(Math.min(m.vlm.latency_ms.mean, m.ocr.latency_ms.mean))} vs ${secs(Math.max(m.vlm.latency_ms.mean, m.ocr.latency_ms.mean))} per question).`
    : `ANLS: vision ${pct(m.vlm.anls)}, OCR ${pct(m.ocr.anls)}. The 95% interval on the difference excludes zero, so the gap is larger than chance on this sample.`;
  const tone = winner === "vlm" ? "bg-vlm-soft text-vlm" : winner === "ocr" ? "bg-ocr-soft text-ocr" : "bg-bench text-ink";

  return (
    <>
      <section aria-label="Verdict" className="card flex items-start gap-4 px-6 py-5">
        <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone}`} aria-hidden>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">{winner === "vlm" || winner === "ocr" ? <path d="m5 12 5 5 9-10" /> : <path d="M5 12h14" />}</svg>
        </span>
        <div className="flex flex-col gap-1.5">
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="text-ink-soft">{text}</p>
        </div>
      </section>

      <section aria-label="Charts" className="card grid gap-10 px-6 py-5 lg:grid-cols-2">
        <BarChart title={`Accuracy on ${m.n} questions`} max={1} tickFmt={(x) => `${Math.round(x * 100)}%`} legend={LEGEND}
          groups={[pair("ANLS (soft match)", m.vlm.anls, m.ocr.anls, (x) => pct(x)), pair("Exact match", m.vlm.em, m.ocr.em, (x) => pct(x)),
            pair("Contains the correct answer", m.vlm.contains, m.ocr.contains, (x) => pct(x))]}
          caption="Longer is better. ANLS gives partial credit for near misses such as a small typo; exact match gives none." />
        <BarChart title="Time per question" tickFmt={(x) => `${x} s`} legend={LEGEND}
          groups={[pair("Mean", m.vlm.latency_ms.mean, m.ocr.latency_ms.mean, secs, 1 / 1000), pair("Median", m.vlm.latency_ms.p50, m.ocr.latency_ms.p50, secs, 1 / 1000),
            pair("95th percentile (slow cases)", m.vlm.latency_ms.p95, m.ocr.latency_ms.p95, secs, 1 / 1000)]}
          caption="Shorter is better. OCR time is the recorded cost of OCR on the pages read plus the text model's time." />
      </section>

      {m.trust && <TrustSection t={m.trust} />}
      {m.by_type && Object.keys(m.by_type).length > 1 && <TypeSection b={m.by_type} />}

      <section aria-label="What the results mean" className="card flex flex-col gap-3.5 px-6 py-5">
        <h2 className="text-lg font-semibold">What the results mean</h2>
        <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-[200px_minmax(0,1fr)]">
          {interpret({ ...m, n: m.n, vlm: m.vlm, ocr: m.ocr }, winner).map(([k, t]) => (
            <div key={k} className="contents"><dt className="font-semibold">{k}</dt><dd className="text-ink-soft">{t}</dd></div>
          ))}
          {d && (
            <div className="contents"><dt className="font-semibold">Is the difference real?</dt><dd className="text-ink-soft">
              ANLS, vision minus OCR: <strong>{d.diff >= 0 ? "+" : ""}{d.diff.toFixed(3)}</strong> (95% bootstrap interval {d.ci_low.toFixed(3)} to {d.ci_high.toFixed(3)}). {sig ? "The interval excludes zero on this sample." : "The interval includes zero, so this sample cannot separate the two."}
              {mc && ` Exact match: vision alone was right on ${mc.a_only} questions, OCR alone on ${mc.b_only} (McNemar p = ${mc.p_value.toFixed(3)}).`}
            </dd></div>
          )}
          <div className="contents"><dt className="font-semibold">Where OCR loses information</dt><dd className="text-ink-soft">
            The correct answer appears in the OCR text for <strong>{pct(m.ocr_answer_coverage)}</strong> of questions, the ceiling for any text model reading this OCR. Vision got {m.ocr_loss_cases ?? 0} questions right whose answer never made it into the OCR text, and the two methods gave different answers on {pct(m.disagreement_rate)} of questions.
          </dd></div>
        </dl>
        {m.ocr_answer_coverage != null && m.ocr_answer_coverage > 0.97 && (
          <p className="rounded-md bg-ocr-soft px-3 py-2 text-sm">OCR captured nearly every answer, so this set leaves little room for the vision model to win. Add harder pages from your own documents (tables, forms, low-quality scans, charts) before drawing conclusions.</p>
        )}
        <table className="w-full max-w-md text-sm">
          <thead><tr className="text-left text-[13px] text-muted"><th /><th className="font-medium text-vlm">Vision</th><th className="font-medium text-ocr-text">OCR + text</th></tr></thead>
          <tbody>{rows.map(([k, a, b]) => <tr key={k} className="border-t border-hair"><td className="py-1.5 text-muted">{k}</td><td>{a}</td><td>{b}</td></tr>)}</tbody>
        </table>
      </section>
    </>
  );
}

const auc = (x: number | null) => (x == null ? "n/a" : x.toFixed(2));
const aucWords = (x: number | null) => x == null ? "cannot be measured (all answers right or all wrong)"
  : x >= 0.8 ? "separates right from wrong answers well" : x >= 0.65 ? "separates them moderately" : x > 0.55 ? "separates them only weakly" : "does no better than chance";

/** Does the trust score predict wrong answers? (selective answering) */
function TrustSection({ t }: { t: NonNullable<Metrics["trust"]> }) {
  const top = t.risk_coverage[0], all = t.risk_coverage[t.risk_coverage.length - 1];
  return (
    <section aria-label="Does the trust score predict wrong answers?" className="card flex flex-col gap-5 px-6 py-5">
      <div>
        <h2 className="text-lg font-semibold">Does the trust score predict wrong answers?</h2>
        <p className="text-ink-soft">For each question DocMind recommends one answer and scores how far to trust it. If the score works, the most-trusted answers should be right more often.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {[["Trust score", t.auroc_trust, "AUROC"], ["Answers agree (alone)", t.auroc_agreement, "AUROC"]].map(([name, v, unit]) => (
          <div key={String(name)} className="rounded-lg border border-rule bg-sheet px-4 py-3">
            <div className="text-[13px] text-muted">{name}</div>
            <div className="font-mono text-3xl font-medium">{auc(v as number | null)}<span className="ml-1.5 font-sans text-sm text-muted">{unit}</span></div>
          </div>
        ))}
        <div className="rounded-lg border border-rule bg-sheet px-4 py-3">
          <div className="text-[13px] text-muted">Recommended answer correct</div>
          <div className="font-mono text-3xl font-medium">{pct(t.accuracy, 0)}<span className="ml-1.5 font-sans text-sm text-muted">of {t.n}</span></div>
        </div>
      </div>
      <BarChart title="Accuracy when only the most-trusted answers are kept" max={1} tickFmt={(x) => `${Math.round(x * 100)}%`}
        legend={[{ name: "Recommended answer correct", color: COLORS.vlm }]}
        groups={t.risk_coverage.map((r) => ({ name: r.coverage === 1 ? `All ${r.n} answers` : `Top ${Math.round(r.coverage * 100)}% by trust (${r.n})`,
          bars: [{ who: "Correct", segments: [{ value: r.accuracy, color: COLORS.vlm, name: "Correct" }], label: pct(r.accuracy, 0),
            tip: `Keeping the ${r.n} most-trusted answers: ${pct(r.accuracy, 1)} correct` }] }))}
        caption="Higher bars at the top mean the trust score puts right answers first. 1.0 AUROC would separate them perfectly; 0.5 is chance." />
      <p className="text-ink-soft">
        The trust score {aucWords(t.auroc_trust)} (AUROC {auc(t.auroc_trust)}); agreement between the two methods alone {aucWords(t.auroc_agreement)} (AUROC {auc(t.auroc_agreement)}).
        {top && all && ` Answering only the most-trusted quarter, ${pct(top.accuracy, 0)} are correct, against ${pct(all.accuracy, 0)} when every question is answered.`}
        {t.unrated > 0 && ` ${t.unrated} questions had no rating (long answers, or answers that differ with nothing to settle them).`}
      </p>
    </section>
  );
}

/** Vision vs OCR accuracy per question type. */
function TypeSection({ b }: { b: NonNullable<Metrics["by_type"]> }) {
  const rows = Object.entries(b);
  const gaps = rows.map(([k, r]) => [k, r.vlm_anls - r.ocr_anls, r.n] as const).filter(([, , n]) => n >= 5).sort((x, y) => y[1] - x[1]);
  const best = gaps[0], worst = gaps[gaps.length - 1];
  return (
    <section aria-label="Where each method is stronger" className="card flex flex-col gap-4 px-6 py-5">
      <div>
        <h2 className="text-lg font-semibold">Where each method is stronger</h2>
        <p className="text-ink-soft">The same questions, split by the kind of reading they need (DocVQA's own labels; a question can have several).</p>
      </div>
      <BarChart title="ANLS by question type" max={1} tickFmt={(x) => `${Math.round(x * 100)}%`} legend={LEGEND}
        groups={rows.map(([k, r]) => pair(`${k} (${r.n})`, r.vlm_anls, r.ocr_anls, (x) => pct(x, 0)))}
        caption="Types with fewer than about 10 questions are noisy; read them as hints, not results." />
      {best && worst && best[0] !== worst[0] && (
        <p className="text-ink-soft">The vision model's biggest lead is on <strong>{best[0]}</strong> ({best[1] >= 0 ? "+" : ""}{(best[1] * 100).toFixed(0)} points); {worst[1] < 0 ? <>OCR leads on <strong>{worst[0]}</strong> ({(worst[1] * 100).toFixed(0)} points)</> : <>its smallest lead is on <strong>{worst[0]}</strong> ({(worst[1] * 100).toFixed(0)} points)</>}. Only types with at least 5 questions are compared.</p>
      )}
    </section>
  );
}
