"use client";
import { useRef, useState } from "react";
import { bytes } from "@/lib/api";
import type { Conversation, Doc } from "@/lib/types";

type Props = {
  docs: Doc[]; docId: string | null; onSelectDoc: (id: string) => void; onDeleteDoc: (id: string) => void;
  onUpload: (f: File) => Promise<void>; uploading: boolean;
  convs: Conversation[]; convId: string | null; onSelectConv: (c: Conversation) => void; onNewChat: () => void; onDeleteConv: (id: string) => void;
};

export default function Rail(p: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const pick = (files: FileList | null) => { if (files?.[0]) void p.onUpload(files[0]); };

  return (
    <aside className="flex h-full w-full flex-col overflow-y-auto border-r border-rule bg-sheet md:w-72" aria-label="Documents and conversations">
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files); }}
        className={`m-3 border border-dashed p-3 text-sm ${drag ? "border-ink bg-bench" : "border-rule"}`}>
        <input ref={input} type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
        <button className="btn w-full" disabled={p.uploading} onClick={() => input.current?.click()}>{p.uploading ? "Uploading…" : "Upload a document"}</button>
        <p className="mt-2 text-xs text-muted">PDF or page image, any size. You can also drop a file here.</p>
      </div>

      <section className="px-3" aria-label="Documents">
        <h2 className="mb-1 text-sm font-semibold">Documents</h2>
        {p.docs.length === 0 && <p className="text-sm text-muted">Nothing uploaded yet.</p>}
        <ul>
          {p.docs.map((d) => (
            <li key={d.id} className={`group flex items-start justify-between gap-2 border-t border-rule py-1.5 ${d.id === p.docId ? "border-l-[3px] border-l-ink pl-2" : "pl-[11px]"}`}>
              <button onClick={() => p.onSelectDoc(d.id)} className="min-w-0 flex-1 text-left">
                <span className="block truncate text-sm font-medium">{d.filename}</span>
                <span className="text-xs text-muted">{d.n_pages} {d.n_pages === 1 ? "page" : "pages"} · {bytes(d.size_bytes)}</span>
              </button>
              <button aria-label={`Delete ${d.filename}`} title="Delete document" onClick={() => { if (confirm(`Delete ${d.filename}? Its OCR cache goes too; conversations are kept.`)) p.onDeleteDoc(d.id); }}
                className="px-1 text-muted hover:text-bad">×</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-4 px-3 pb-4" aria-label="Conversations">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <button className="btn-quiet !px-2 !py-0.5 text-xs" disabled={!p.docId} onClick={p.onNewChat}>New</button>
        </div>
        {p.convs.length === 0 && <p className="text-sm text-muted">Ask a question and it is saved here. Every message is kept.</p>}
        <ul>
          {p.convs.map((c) => (
            <li key={c.id} className={`flex items-start justify-between gap-2 border-t border-rule py-1.5 ${c.id === p.convId ? "border-l-[3px] border-l-ink pl-2" : "pl-[11px]"}`}>
              <button onClick={() => p.onSelectConv(c)} className="min-w-0 flex-1 truncate text-left text-sm">{c.title}</button>
              <button aria-label={`Delete conversation ${c.title}`} onClick={() => { if (confirm("Delete this conversation and all its messages?")) p.onDeleteConv(c.id); }} className="px-1 text-muted hover:text-bad">×</button>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
