"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, bytes } from "@/lib/api";
import type { Conversation, Doc } from "@/lib/types";

const when = (t: number) => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

type FileGroup = { key: string; latest: Doc; copies: number; firstUploaded: number; convs: Conversation[]; lastUsed: number };

export default function HistoryPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([api.documents(), api.conversations()])
      .then(([d, c]) => { setDocs(d); setConvs(c); })
      .catch((e) => setErr(e.message)).finally(() => setLoaded(true));
  }, []);

  // One entry per file content: every copy of the same file shares its history.
  const { files, orphans } = useMemo(() => {
    const groups = new Map<string, FileGroup>();
    for (const d of [...docs].sort((a, b) => b.created_at - a.created_at)) {
      const key = d.sha256 ?? d.id;
      const g = groups.get(key);
      if (g) { g.copies++; g.firstUploaded = Math.min(g.firstUploaded, d.created_at); }
      else groups.set(key, { key, latest: d, copies: 1, firstUploaded: d.created_at, convs: [], lastUsed: d.created_at });
    }
    const ids = new Map(docs.map((d) => [d.id, d.sha256 ?? d.id]));
    const orphans: Conversation[] = [];
    for (const c of convs) {
      const key = c.doc_sha256 ?? (c.doc_id ? ids.get(c.doc_id) : undefined);
      const g = key ? groups.get(key) : undefined;
      if (g) { g.convs.push(c); g.lastUsed = Math.max(g.lastUsed, c.updated_at); } else orphans.push(c);
    }
    const files = [...groups.values()].sort((a, b) => b.lastUsed - a.lastUsed);
    return { files, orphans };
  }, [docs, convs]);

  const shown = files.filter((f) => f.latest.filename.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div className="h-full overflow-y-auto px-4 py-7 sm:px-8">
      <div className="mx-auto flex max-w-[1120px] flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-reading text-[30px] font-semibold">History</h1>
            <p className="text-ink-soft">Every file you have used, with its conversations. Upload a file again and its history comes back with it.</p>
          </div>
          <label className="flex w-full flex-col gap-1 text-[13px] text-muted sm:w-72">Search files
            <input type="search" className="field h-10 !py-0 text-ink" placeholder="Name of a file" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
        {err && <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-text">{err}</p>}
        {loaded && files.length === 0 && !err && (
          <p className="card px-6 py-5 text-muted">Nothing yet. <Link className="text-vlm underline" href="/ask">Upload a document</Link> and ask it something; it shows up here.</p>
        )}
        {loaded && files.length > 0 && shown.length === 0 && <p className="text-muted">No file matches “{q}”.</p>}

        <ul className="flex flex-col gap-3">
          {shown.map((f) => (
            <li key={f.key} className="card flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 flex-col gap-1">
                <h2 className="truncate text-[17px] font-semibold">{f.latest.filename}</h2>
                <p className="text-[13px] text-muted">
                  {f.latest.n_pages} {f.latest.n_pages === 1 ? "page" : "pages"} · {bytes(f.latest.size_bytes)} · first uploaded {when(f.firstUploaded)}
                  {f.copies > 1 && ` · uploaded ${f.copies} times`}
                </p>
                <p className="text-sm">
                  {f.convs.length === 0 ? <span className="text-muted">No questions asked yet.</span>
                    : <>{f.convs.length} {f.convs.length === 1 ? "conversation" : "conversations"}, last used {when(f.lastUsed)}</>}
                </p>
                {f.convs.length > 0 && (
                  <ul className="mt-1 flex flex-wrap gap-1.5">
                    {f.convs.slice(0, 4).map((c) => <li key={c.id} className="max-w-[16rem] truncate rounded-full bg-bench px-2.5 py-0.5 text-[13px]">{c.title}</li>)}
                    {f.convs.length > 4 && <li className="chip text-muted">+{f.convs.length - 4} more</li>}
                  </ul>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Link href={`/ask?doc=${f.latest.id}`} className="btn h-10 !px-4">Open</Link>
                <a href={api.historyUrl(f.latest.id, "md")} download className="btn-quiet h-10">Download history</a>
                <a href={api.historyUrl(f.latest.id, "json")} download aria-label={`Download history of ${f.latest.filename} as JSON`} className="px-1.5 py-2 text-sm text-muted hover:text-ink hover:underline">JSON</a>
              </div>
            </li>
          ))}
        </ul>

        {orphans.length > 0 && !q && (
          <section className="card flex flex-col gap-2 px-5 py-4" aria-label="Conversations about deleted files">
            <h2 className="text-[17px] font-semibold">Conversations about files you have deleted</h2>
            <p className="text-sm text-muted">They are kept. Upload the same file again and they reappear with it.</p>
            <ul className="flex flex-wrap gap-1.5">{orphans.map((c) => <li key={c.id} className="max-w-[16rem] truncate rounded-full bg-bench px-2.5 py-0.5 text-[13px]">{c.title}</li>)}</ul>
          </section>
        )}
      </div>
    </div>
  );
}
