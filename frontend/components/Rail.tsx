"use client";
import { useMemo, useRef, useState } from "react";
import { bytes } from "@/lib/api";
import type { Conversation, Doc } from "@/lib/types";

type Props = {
  docs: Doc[]; docId: string | null; onSelectDoc: (id: string) => void; onDeleteDoc: (id: string) => void;
  onUpload: (f: File) => Promise<void>; uploading: boolean;
  convs: Conversation[]; convId: string | null; onSelectConv: (c: Conversation) => void; onNewChat: () => void; onDeleteConv: (id: string) => void;
};

const isImage = (name: string) => /\.(png|jpe?g|tiff?|bmp|webp)$/i.test(name);

function FileIcon({ image, className }: { image: boolean; className: string }) {
  return image ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className} aria-hidden><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m4 16 5-5 4 4 3-3 4 4" /></svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className} aria-hidden><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>
  );
}

export default function Rail(p: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [q, setQ] = useState("");
  const pick = (files: FileList | null) => { if (files?.[0]) void p.onUpload(files[0]); };
  const docs = useMemo(() => p.docs.filter((d) => d.filename.toLowerCase().includes(q.trim().toLowerCase())), [p.docs, q]);

  return (
    <aside className="flex h-full w-full flex-col gap-5 overflow-y-auto border-r border-rule bg-sheet p-4 md:w-[296px]" aria-label="Documents and conversations"
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={(e) => { if (e.currentTarget === e.target) setDrag(false); }}
      onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}>
      <input ref={input} type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
      <button className={`btn h-11 w-full text-[15px] ${drag ? "outline outline-2 outline-offset-4 outline-ink" : ""}`} disabled={p.uploading} onClick={() => input.current?.click()}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
        {p.uploading ? "Uploading…" : drag ? "Drop to upload" : "Upload a document"}
      </button>

      {/* Documents and conversations scroll separately, so conversations never disappear below a long list */}
      <section className="flex min-h-[11rem] flex-1 flex-col gap-2" aria-label="Documents">
        <div className="flex items-baseline justify-between"><h2 className="eyebrow">Documents</h2><span className="text-[13px] text-muted">{p.docs.length}</span></div>
        {p.docs.length > 5 && (
          <label className="flex flex-col gap-1 text-[13px] text-muted">Search documents
            <input type="search" className="field h-10 !py-0 text-ink" placeholder="Name of a file" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        )}
        {p.docs.length === 0 && <p className="text-sm text-muted">Nothing uploaded yet.</p>}
        {p.docs.length > 0 && docs.length === 0 && <p className="text-sm text-muted">No document matches “{q}”.</p>}
        <ul className="-mx-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1">
          {docs.map((d) => {
            const on = d.id === p.docId;
            return (
              <li key={d.id} className="group relative">
                <button onClick={() => p.onSelectDoc(d.id)} aria-current={on || undefined}
                  className={`flex min-h-[52px] w-full items-center gap-2.5 rounded-md py-2 pl-2.5 pr-9 text-left ${on ? "bg-primary text-on-primary" : "hover:bg-bench"}`}>
                  <FileIcon image={isImage(d.filename)} className={`shrink-0 ${on ? "" : "text-muted"}`} />
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate font-medium">{d.filename}</span>
                    <span className={`text-[13px] ${on ? "text-on-primary/70" : "text-muted"}`}>{d.n_pages} {d.n_pages === 1 ? "page" : "pages"} · {bytes(d.size_bytes)}</span>
                  </span>
                </button>
                <button aria-label={`Delete ${d.filename}`} title="Delete document"
                  onClick={() => { if (confirm(`Delete ${d.filename}? Its OCR cache goes too; conversations are kept.`)) p.onDeleteDoc(d.id); }}
                  className={`absolute right-1 top-1/2 h-8 w-8 -translate-y-1/2 rounded-md opacity-60 hover:opacity-100 group-hover:opacity-100 ${on ? "text-on-primary hover:bg-on-primary/10" : "text-muted hover:bg-paper hover:text-bad"}`}>×</button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="flex max-h-[40%] min-h-[8rem] flex-col gap-2 border-t border-rule pt-4" aria-label="Conversations">
        <div className="flex items-center justify-between">
          <h2 className="eyebrow">Conversations</h2>
          <button className="btn-quiet h-8 !px-2.5 !py-0 text-[13px]" disabled={!p.docId} onClick={p.onNewChat}>New</button>
        </div>
        {p.convs.length === 0 && <p className="text-sm text-muted">{p.docId ? "Your questions about this document are saved here." : "Pick a document to see its conversations."}</p>}
        <ul className="-mx-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1">
          {p.convs.map((c) => {
            const on = c.id === p.convId;
            return (
              <li key={c.id} className="group relative">
                <button onClick={() => p.onSelectConv(c)} aria-current={on || undefined}
                  className={`min-h-11 w-full truncate rounded-md py-2 pl-2.5 pr-9 text-left text-sm ${on ? "bg-select" : "hover:bg-bench"}`}>{c.title}</button>
                <button aria-label={`Delete conversation ${c.title}`} onClick={() => { if (confirm("Delete this conversation and all its messages?")) p.onDeleteConv(c.id); }}
                  className="absolute right-1 top-1/2 h-8 w-8 -translate-y-1/2 rounded-md text-muted opacity-60 hover:bg-paper hover:text-bad hover:opacity-100 group-hover:opacity-100">×</button>
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
