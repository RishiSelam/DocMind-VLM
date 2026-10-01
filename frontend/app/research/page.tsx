"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import MetricsPanel from "@/components/MetricsPanel";
import { api, pct, secs } from "@/lib/api";
import type { Dataset, ExpItem, Experiment, SystemMetrics } from "@/lib/types";

type Filter = "all" | "disagree" | "vlm_only" | "ocr_only" | "ocr_missing";
const FILTERS: [Filter, string][] = [["all", "All"], ["disagree", "Methods disagree"], ["vlm_only", "Only vision right"], ["ocr_only", "Only OCR right"], ["ocr_missing", "Answer missing from OCR"]];

function keep(it: ExpItem, f: Filter) {
  const v = it.vlm_scores.contains === 1, o = it.ocr_scores.contains === 1;
  if (f === "disagree") return it.agree === 0;
  if (f === "vlm_only") return v && !o;
  if (f === "ocr_only") return o && !v;
  if (f === "ocr_missing") return it.answer_in_ocr === 0;
  return true;
}
const badge = (s: { anls?: number; contains?: number }) => (s.contains === 1 ? "text-agree-text" : (s.anls ?? 0) > 0 ? "text-warn-text" : "text-bad-text");
const mark = (s: { anls?: number; contains?: number }) => (s.contains === 1 ? "✓ " : (s.anls ?? 0) > 0 ? "≈ " : "✗ ");
const STATUS: Record<string, string> = { finished: "bg-agree-soft text-agree-text", failed: "bg-bad-soft text-bad-text", running: "bg-warn-soft text-warn-text", queued: "bg-bench text-ink" };

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

  const count = (f: Filter) => (sel?.items ?? []).filter((i) => keep(i, f)).length;
  const field = "field h-10 w-full !py-0 text-ink";
  const label = "flex flex-col gap-1 text-[13px] text-muted";

  return (
    <div className="flex h-full flex-col overflow-hidden md:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-6 overflow-y-auto border-r border-rule bg-sheet p-5 md:w-80">
        <form className="flex flex-col gap-3" aria-label="New experiment" onSubmit={(e) => { e.preventDefault(); void create(); }}>
          <h2 className="text-[17px] font-semibold">New experiment</h2>
          <p className="text-sm text-muted">Questions with known answers, run through both methods. This is how you find out which one is more accurate.</p>
          <label className={label}>Name<input className={field} placeholder="e.g. invoices-oct" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className={label}>Question set
            <select className={field} value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })}>
              {datasets.length === 0 && <option value="">No question sets found</option>}
              {datasets.map((d) => <option key={d.name} value={d.name}>{d.name} · {d.n} questions</option>)}
            </select>
          </label>
          {datasets.length === 0 && <p className="text-xs text-muted">Run <code>python scripts/make_sample_data.py</code> in backend/, or <code>scripts/prepare_docvqa.py</code> for DocVQA.</p>}
          <div className="grid grid-cols-2 gap-2.5">
            <label className={label}>Limit<input className={field} type="number" min={1} placeholder="All" value={form.limit} onChange={(e) => setForm({ ...form, limit: e.target.value })} /></label>
            <label className={label}>Methods
              <select className={field} value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                <option value="both">Both</option><option value="vlm">Vision only</option><option value="ocr">OCR + text only</option>
              </select>
            </label>
          </div>
          <label className={label}>Notes<input className={field} placeholder="Kept with the run" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
          <button type="submit" className="btn h-11 font-semibold" disabled={busy || !form.dataset}>{busy ? "Starting…" : "Run experiment"}</button>
        </form>

        <section className="flex flex-col gap-2 border-t border-rule pt-4" aria-label="Past experiments">
          <h2 className="eyebrow">Past experiments</h2>
          {exps.length === 0 && <p className="text-sm text-muted">None yet. Runs are saved after every question, so an interrupted run can be resumed.</p>}
          <ul className="space-y-1">
            {exps.map((e) => {
              const on = sel?.id === e.id;
              return (
                <li key={e.id}>
                  <button onClick={() => openExp(e.id)} aria-current={on || undefined} className={`flex min-h-14 w-full flex-col rounded-md px-3 py-2.5 text-left ${on ? "bg-primary text-on-primary" : "hover:bg-bench"}`}>
                    <span className="flex justify-between gap-2"><span className="truncate font-medium">{e.id} · {e.name}</span>
                      <span className={`text-[13px] capitalize ${on ? "text-on-primary/80" : e.status === "failed" ? "text-bad-text" : e.status === "finished" ? "text-agree-text" : "text-warn-text"}`}>{e.status}</span></span>
                    <span className={`text-[13px] ${on ? "text-on-primary/70" : "text-muted"}`}>{e.progress_done}/{e.progress_total} questions{e.metrics.vlm ? ` · vision ${pct(e.metrics.vlm.anls, 0)} · OCR ${pct(e.metrics.ocr!.anls, 0)}` : ""}{e.config.demo_mode ? " · demo" : ""}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        {sys && (
          <section className="flex flex-col gap-1 border-t border-rule pt-4 text-sm text-muted" aria-label="This server">
            <h2 className="eyebrow">This server</h2>
            <p>{sys.gpu.available ? `${sys.gpu.name}: ${sys.gpu.free_gb} of ${sys.gpu.total_gb} GB free` : `No GPU (${sys.gpu.reason})`}</p>
            <p>{sys.n_requests} {sys.n_requests === 1 ? "question" : "questions"} since start{sys.n_requests ? ` · median ${secs(sys.total_ms?.p50)}, 95th percentile ${secs(sys.total_ms?.p95)}` : ""}.</p>
          </section>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-5">
          {err && <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-text">{err}</p>}
          {!sel ? (
            <div className="max-w-xl py-10"><h1 className="font-reading text-[30px] font-semibold">Which method is more accurate on your documents?</h1>
              <p className="mt-2 text-ink-soft">Pick a question set with known answers and run it. Every question goes through the vision model and through OCR plus a text model; the answers are scored and stored with the full configuration, so a run can be reported and repeated.</p></div>
          ) : (
            <>
              <div className="flex flex-col gap-2.5">
                <div className="flex flex-wrap items-center gap-3.5">
                  <h1 className="font-reading text-[30px] font-semibold">{sel.id} · {sel.name}</h1>
                  <span className={`chip font-medium ${STATUS[sel.status] ?? "bg-bench"}`}>{sel.status[0].toUpperCase() + sel.status.slice(1)} · {sel.progress_done} of {sel.progress_total}</span>
                  <span className="ml-auto flex gap-2">
                    <a className="btn-quiet h-10 !py-0" href={api.experimentCsvUrl(sel.id)}>Download CSV</a>
                    {(sel.status === "failed" || sel.status === "queued") && <button className="btn-quiet h-10 !py-0" onClick={() => act(() => api.resumeExperiment(sel.id))}>Resume</button>}
                    <button className="btn-quiet h-10 !py-0 text-bad-text" disabled={sel.status === "running"} onClick={() => { if (confirm(`Delete ${sel.id}?`)) act(async () => { await api.deleteExperiment(sel.id); setSel(null); }); }}>Delete</button>
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 text-[13px]">
                  {[["Vision", c.vlm_model], ["Text", c.llm_model], ["OCR", c.ocr_engine], ["Pages per vision call", c.vlm_page_cap], ["Reads all pages", c.read_all_pages == null ? "n/a (older run)" : c.read_all_pages ? "yes" : "no"], ["Prompt", c.prompt_version], ["Decoding", c.decoding], ["Set", String(c.dataset ?? "").split("/").slice(-2).join("/")]].map(([k, v]) => (
                    <span key={String(k)} className="rounded-md border border-rule bg-sheet px-2.5 py-0.5"><span className="text-muted">{k}: </span>{String(v)}</span>
                  ))}
                  <span className={`rounded-md px-2.5 py-0.5 ${c.demo_mode ? "border border-warn text-warn-text" : "border border-rule bg-sheet"}`}>{c.demo_mode ? "Demo mode" : "Real models"}</span>
                </div>
                {c.notes && <p className="text-sm">Notes: {c.notes}</p>}
              </div>
              {sel.progress_total > 0 && sel.progress_done < sel.progress_total && <div className="h-1.5 rounded-full bg-paper" role="progressbar" aria-valuenow={sel.progress_done} aria-valuemax={sel.progress_total}><div className="h-1.5 rounded-full bg-ink" style={{ width: `${(sel.progress_done / sel.progress_total) * 100}%` }} /></div>}
              {sel.error && <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-text">{sel.error}</p>}
              {c.demo_mode && <p className="rounded-md border border-warn bg-paper px-3 py-2 text-sm text-warn-text">This run used demo mode. The scores come from text-matching stand-ins and say nothing about Qwen. Set DEMO_MODE=false on the GPU workstation for real results.</p>}

              <MetricsPanel exp={sel} />

              <section aria-label="Questions" className="card flex flex-col gap-3 px-6 py-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="mr-3 text-lg font-semibold">Questions</h2>
                  {FILTERS.map(([k, name]) => (
                    <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
                      className={`h-9 rounded-full px-3.5 text-sm ${filter === k ? "bg-primary text-on-primary" : "border border-rule bg-paper hover:border-ink"}`}>{name} · {count(k)}</button>
                  ))}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
                    <thead className="text-[13px] text-muted"><tr><th className="py-1.5 font-medium">Question</th><th className="font-medium">Correct answer</th><th className="font-medium text-vlm">Vision</th><th className="font-medium text-ocr-text">OCR + text</th><th className="font-medium">In OCR text?</th></tr></thead>
                    <tbody>
                      {items.map((i) => (
                        <tr key={i.idx} className="border-t border-hair align-top">
                          <td className="max-w-[16rem] py-2.5 pr-3">{i.question}</td>
                          <td className="pr-3 font-reading">{i.gold.join(" / ")}</td>
                          <td className={`pr-3 ${badge(i.vlm_scores)}`}>{mark(i.vlm_scores)}{i.vlm_pred ?? "(no answer)"}<div className="font-mono text-xs text-muted">{secs(i.vlm_ms)}</div></td>
                          <td className={`pr-3 ${badge(i.ocr_scores)}`}>{mark(i.ocr_scores)}{i.ocr_pred ?? "(no answer)"}<div className="font-mono text-xs text-muted">{secs(i.ocr_ms)}</div></td>
                          <td>{i.answer_in_ocr == null ? "n/a" : i.answer_in_ocr ? "yes" : <span className="text-bad-text">no</span>}</td>
                        </tr>
                      ))}
                      {items.length === 0 && <tr><td colSpan={5} className="py-3 text-muted">No questions match this filter.</td></tr>}
                    </tbody>
                  </table>
                </div>
                <p className="text-[13px] text-muted">✓ contains the correct answer · ≈ partly matches · ✗ no match. Showing {items.length} of {sel.items?.length ?? 0}.</p>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
