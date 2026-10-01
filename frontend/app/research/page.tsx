"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import MetricsPanel from "@/components/MetricsPanel";
import { api, pct, secs } from "@/lib/api";
import type { Dataset, ExpItem, Experiment, SystemMetrics } from "@/lib/types";

type Filter = "all" | "disagree" | "vlm_only" | "ocr_only" | "ocr_missing";
const FILTERS: [Filter, string][] = [["all", "All"], ["disagree", "Pipelines disagree"], ["vlm_only", "Only vision correct"], ["ocr_only", "Only OCR correct"], ["ocr_missing", "Answer missing from OCR"]];

function keep(it: ExpItem, f: Filter) {
  const v = it.vlm_scores.contains === 1, o = it.ocr_scores.contains === 1;
  if (f === "disagree") return it.agree === 0;
  if (f === "vlm_only") return v && !o;
  if (f === "ocr_only") return o && !v;
  if (f === "ocr_missing") return it.answer_in_ocr === 0;
  return true;
}
const badge = (s: { anls?: number; contains?: number }) => (s.contains === 1 ? "text-agree" : (s.anls ?? 0) > 0 ? "text-warn" : "text-bad");

export default function Research() {
  const [exps, setExps] = useState<Experiment[]>([]);
  const [sel, setSel] = useState<Experiment | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [sys, setSys] = useState<SystemMetrics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [form, setForm] = useState({ name: "", dataset: "", limit: "", mode: "both", notes: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [e, d, s] = await Promise.all([api.experiments(), api.datasets(), api.metrics()]);
      setExps(e); setDatasets(d); setSys(s);
      setForm((f) => (f.dataset || !d.length ? f : { ...f, dataset: d[0].name }));
    } catch (x: any) { setErr(x.message); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const openExp = useCallback(async (id: string) => { try { setSel(await api.experiment(id)); setFilter("all"); } catch (x: any) { setErr(x.message); } }, []);

  // poll while anything is queued/running
  useEffect(() => {
    const active = exps.some((e) => e.status === "running" || e.status === "queued") || sel?.status === "running";
    if (!active) return;
    const t = setInterval(() => { void load(); if (sel) void openExp(sel.id); }, 2500);
    return () => clearInterval(t);
  }, [exps, sel, load, openExp]);

  async function create() {
    setBusy(true); setErr(null);
    try {
      const e = await api.createExperiment({ name: form.name || `run ${exps.length + 1}`, dataset: form.dataset, limit: form.limit ? Number(form.limit) : undefined, mode: form.mode, notes: form.notes });
      await load(); await openExp(e.id);
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  }
  async function act(fn: () => Promise<unknown>) { try { await fn(); await load(); if (sel) await openExp(sel.id).catch(() => setSel(null)); } catch (x: any) { setErr(x.message); } }

  const items = useMemo(() => (sel?.items ?? []).filter((i) => keep(i, filter)), [sel, filter]);
  const c = sel?.config ?? {};

  return (
    <div className="flex h-full flex-col overflow-hidden md:flex-row">
      <aside className="w-full shrink-0 overflow-y-auto border-r border-rule bg-sheet p-3 md:w-80">
        <h2 className="mb-2 font-semibold">New experiment</h2>
        <div className="space-y-2 text-sm">
          <input className="field w-full" placeholder="Name" aria-label="Experiment name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select className="field w-full" aria-label="Dataset" value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })}>
            {datasets.length === 0 && <option value="">No datasets found</option>}
            {datasets.map((d) => <option key={d.name} value={d.name}>{d.name} ({d.n} questions)</option>)}
          </select>
          {datasets.length === 0 && <p className="text-xs text-muted">Run <code>python scripts/make_sample_data.py</code> in backend/, or <code>scripts/prepare_docvqa.py</code> for DocVQA.</p>}
          <div className="flex gap-2">
            <input className="field w-24" type="number" min={1} placeholder="Limit" aria-label="Question limit" value={form.limit} onChange={(e) => setForm({ ...form, limit: e.target.value })} />
            <select className="field flex-1" aria-label="Pipelines" value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
              <option value="both">Both pipelines</option><option value="vlm">Vision only</option><option value="ocr">OCR + text only</option>
            </select>
          </div>
          <input className="field w-full" placeholder="Notes (kept with the run)" aria-label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button className="btn w-full" disabled={busy || !form.dataset} onClick={create}>{busy ? "Starting…" : "Run experiment"}</button>
        </div>

        <h2 className="mb-1 mt-6 font-semibold">Experiments</h2>
        {exps.length === 0 && <p className="text-sm text-muted">None yet. Runs are saved after every question, so an interrupted run can be resumed.</p>}
        <ul>
          {exps.map((e) => (
            <li key={e.id}>
              <button onClick={() => openExp(e.id)} className={`w-full border-t border-rule py-1.5 text-left ${sel?.id === e.id ? "border-l-[3px] border-l-ink pl-2" : "pl-[11px]"}`}>
                <div className="flex justify-between text-sm"><span className="font-medium">{e.id} {e.name}</span><span className={e.status === "failed" ? "text-bad" : e.status === "finished" ? "text-agree" : "text-warn"}>{e.status}</span></div>
                <div className="text-xs text-muted">{e.progress_done}/{e.progress_total} questions{e.metrics.vlm ? ` · ANLS vision ${e.metrics.vlm.anls.toFixed(2)}, OCR ${e.metrics.ocr!.anls.toFixed(2)}` : ""}{e.config.demo_mode ? " · demo" : ""}</div>
              </button>
            </li>
          ))}
        </ul>

        {sys && (
          <section className="mt-6" aria-label="System performance">
            <h2 className="mb-1 font-semibold">This server</h2>
            <p className="text-sm text-muted">{sys.gpu.available ? `${sys.gpu.name}: ${sys.gpu.free_gb} of ${sys.gpu.total_gb} GB free` : `No GPU (${sys.gpu.reason})`}</p>
            <p className="text-sm text-muted">{sys.n_requests} questions since start. Median total {secs(sys.total_ms?.p50)}, 95th percentile {secs(sys.total_ms?.p95)}.</p>
          </section>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto p-4">
        {err && <p role="alert" className="mb-3 rounded-[4px] bg-bad-soft p-2 text-sm text-bad">{err}</p>}
        {!sel ? (
          <div className="max-w-xl"><h1 className="font-reading text-2xl font-semibold">Compare the two pipelines on a dataset</h1>
            <p className="mt-2 text-muted">Pick a dataset and run it. Each question goes through the vision model and through OCR plus a text model; the results are scored with exact match and ANLS, and stored with the full configuration so the run can be reported and repeated.</p></div>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-x-4">
              <h1 className="font-reading text-2xl font-semibold">{sel.id} · {sel.name}</h1>
              <span className="text-sm text-muted">{sel.status} · {sel.progress_done}/{sel.progress_total} questions</span>
              <span className="ml-auto flex gap-2">
                <a className="btn-quiet" href={api.experimentCsvUrl(sel.id)}>Download CSV</a>
                {(sel.status === "failed" || sel.status === "queued") && <button className="btn-quiet" onClick={() => act(() => api.resumeExperiment(sel.id))}>Resume</button>}
                <button className="btn-quiet" disabled={sel.status === "running"} onClick={() => { if (confirm(`Delete ${sel.id}?`)) act(async () => { await api.deleteExperiment(sel.id); setSel(null); }); }}>Delete</button>
              </span>
            </div>
            {sel.progress_total > 0 && <div className="my-2 h-1.5 bg-bench" role="progressbar" aria-valuenow={sel.progress_done} aria-valuemax={sel.progress_total}><div className="h-1.5 bg-ink" style={{ width: `${(sel.progress_done / sel.progress_total) * 100}%` }} /></div>}
            {sel.error && <p role="alert" className="rounded-[4px] bg-bad-soft p-2 text-sm text-bad">{sel.error}</p>}
            {c.demo_mode && <p className="my-2 rounded-[4px] border border-warn p-2 text-sm text-warn">This run used demo mode. The scores come from text-matching stand-ins and say nothing about Qwen. Set DEMO_MODE=false on the GPU workstation for real results.</p>}

            <dl className="my-3 grid grid-cols-2 gap-x-6 gap-y-0.5 text-xs text-muted md:grid-cols-4">
              {[["Vision model", c.vlm_model], ["Text model", c.llm_model], ["OCR engine", c.ocr_engine], ["Vision page cap", c.vlm_page_cap], ["Same pages for OCR", String(c.match_pages)], ["Prompt version", c.prompt_version], ["Decoding", c.decoding], ["Dataset", String(c.dataset ?? "").split("/").slice(-2).join("/")]].map(([k, v]) => (
                <div key={String(k)}><dt className="inline">{k}: </dt><dd className="inline text-ink">{String(v)}</dd></div>
              ))}
            </dl>
            {c.notes && <p className="mb-3 text-sm">Notes: {c.notes}</p>}

            <MetricsPanel exp={sel} />

            <h3 className="mb-1 mt-6 font-semibold">Questions</h3>
            <div className="mb-2 flex flex-wrap gap-3 text-sm">
              {FILTERS.map(([k, label]) => <button key={k} onClick={() => setFilter(k)} className={`pb-0.5 ${filter === k ? "border-b-2 border-ink font-semibold" : "text-muted"}`}>{label}</button>)}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[46rem] text-left text-sm">
                <thead className="text-xs text-muted"><tr><th className="font-normal">Question</th><th className="font-normal">Reference</th><th className="font-normal text-vlm">Vision answer</th><th className="font-normal text-ocr">OCR + text answer</th><th className="font-normal">In OCR text?</th></tr></thead>
                <tbody>
                  {items.map((i) => (
                    <tr key={i.idx} className="border-t border-rule align-top">
                      <td className="max-w-[16rem] py-1.5 pr-3">{i.question}</td>
                      <td className="pr-3 font-reading">{i.gold.join(" / ")}</td>
                      <td className={`pr-3 font-reading ${badge(i.vlm_scores)}`}>{i.vlm_pred ?? "(no answer)"}<div className="font-sans text-xs text-muted">{secs(i.vlm_ms)}</div></td>
                      <td className={`pr-3 font-reading ${badge(i.ocr_scores)}`}>{i.ocr_pred ?? "(no answer)"}<div className="font-sans text-xs text-muted">{secs(i.ocr_ms)}</div></td>
                      <td>{i.answer_in_ocr == null ? "n/a" : i.answer_in_ocr ? "yes" : <span className="text-bad">no</span>}</td>
                    </tr>
                  ))}
                  {items.length === 0 && <tr><td colSpan={5} className="py-3 text-muted">No questions match this filter.</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">Green: the answer contains the reference. Amber: partial string match. Red: no match. Showing {items.length} of {sel.items?.length ?? 0}. Disagreement rate {pct(sel.metrics.disagreement_rate)}.</p>
          </>
        )}
      </main>
    </div>
  );
}
