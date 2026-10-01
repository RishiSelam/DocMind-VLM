"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AnswerPair from "@/components/AnswerPair";
import AskProgress from "@/components/AskProgress";
import EmptyState from "@/components/EmptyState";
import { useMode } from "@/components/ModeContext";
import PageStrip from "@/components/PageStrip";
import PageViewer from "@/components/PageViewer";
import Segmented from "@/components/Segmented";
import Rail from "@/components/Rail";
import { api } from "@/lib/api";
import type { AskPayload, Conversation, Doc, Message, OcrStatus } from "@/lib/types";

export default function Workbench() {
  const { mode } = useMode();
  const research = mode === "research";
  const [docs, setDocs] = useState<Doc[]>([]);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [docId, setDocId] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [askMode, setAskMode] = useState<"both" | "vlm" | "ocr">("both");
  const [short, setShort] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<number | null>(null);
  const [ocr, setOcr] = useState<OcrStatus | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [pageCap, setPageCap] = useState(6);
  const [readsAll, setReadsAll] = useState(true);
  useEffect(() => { api.health().then((h) => { setPageCap(h.page_cap); setReadsAll(h.read_all_pages ?? true); }).catch(() => {}); }, []);
  const feedEnd = useRef<HTMLDivElement>(null);

  const doc = useMemo(() => docs.find((d) => d.id === docId) ?? null, [docs, docId]);
  // A file's conversations follow its content: every copy, including ones uploaded and deleted earlier, shares them.
  const shownConvs = useMemo(() => {
    const sha = docs.find((d) => d.id === docId)?.sha256;
    return convs.filter((c) => !docId || c.doc_id === docId || (!!sha && c.doc_sha256 === sha));
  }, [convs, docs, docId]);

  const refresh = useCallback(async () => {
    try { const [d, c] = await Promise.all([api.documents(), api.conversations()]); setDocs(d); setConvs(c); }
    catch (e: any) { setError(e.message); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  // /ask?doc=<id> (from the History page) opens that document
  useEffect(() => {
    try { const id = new URLSearchParams(window.location.search).get("doc"); if (id) setDocId(id); } catch {}
  }, []);
  useEffect(() => { feedEnd.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);

  // OCR cache status for the selected document (research mode); polls while a job runs.
  useEffect(() => {
    setOcr(null);
    if (!docId || !research) return;
    let alive = true, t: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const s = await api.ocrStatus(docId); if (!alive) return; setOcr(s); if (s.status === "running") t = setTimeout(poll, 2000); } catch {}
    };
    void poll();
    return () => { alive = false; clearTimeout(t); };
  }, [docId, research]);

  const lastPayload = useMemo(() => [...messages].reverse().find((m) => m.role === "assistant")?.payload as Partial<AskPayload> | undefined, [messages]);

  async function upload(file: File) {
    setUploading(true); setError(null);
    try {
      const d = await api.upload(file);
      const [, all] = await Promise.all([refresh(), api.conversations()]);
      selectDoc(d.id); setRailOpen(false);
      const earlier = all.filter((c) => c.doc_id === d.id || (!!d.sha256 && c.doc_sha256 === d.sha256)).length;
      if (d.reused || earlier) setNotice(`You have used “${file.name}” before${earlier ? `: its ${earlier} earlier ${earlier === 1 ? "conversation is" : "conversations are"} in the list on the left, and a question you already asked is answered from history` : ", so the existing copy was opened"}.`);
    }
    catch (e: any) { setError(e.message); } finally { setUploading(false); }
  }
  function selectDoc(id: string) { setDocId(id); setConvId(null); setMessages([]); setError(null); setNotice(null); setRailOpen(false); }
  async function selectConv(c: Conversation) {
    setError(null);
    try {
      const full = await api.conversation(c.id);
      // its own copy may have been deleted; then stay on the current copy of the same file
      const target = docs.find((d) => d.id === c.doc_id) ?? docs.find((d) => d.id === docId && !!d.sha256 && d.sha256 === c.doc_sha256)
        ?? docs.find((d) => !!d.sha256 && d.sha256 === c.doc_sha256);
      setDocId(target?.id ?? null); setConvId(c.id); setMessages(full.messages); setRailOpen(false);
    }
    catch (e: any) { setError(e.message); }
  }
  async function deleteDoc(id: string) { try { await api.deleteDoc(id); if (id === docId) { setDocId(null); setConvId(null); setMessages([]); } await refresh(); } catch (e: any) { setError(e.message); } }
  async function deleteConv(id: string) { try { await api.deleteConversation(id); if (id === convId) { setConvId(null); setMessages([]); } await refresh(); } catch (e: any) { setError(e.message); } }

  async function ask(again?: string) {
    const q = (again ?? question).trim();
    if (!q || !docId || busy) return;
    setBusy(true); setError(null); if (!again) setQuestion("");
    const optimistic: Message = { id: `tmp_${Date.now()}`, conversation_id: convId ?? "", role: "user", content: q, payload: {}, created_at: Date.now() / 1000 };
    setMessages((m) => [...m, optimistic]);
    try {
      const r = await api.ask({ doc_id: docId, conversation_id: convId ?? undefined, question: q, mode: askMode, short, reuse: !again });
      setConvId(r.conversation_id);
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), r.user_message, r.assistant_message]);
      void refresh();
    } catch (e: any) {
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
      if (!again) setQuestion(q);
      setError(e.message);
    } finally { setBusy(false); }
  }

  async function runOcr() { if (!docId) return; try { setOcr(await api.startOcr(docId)); const t = setInterval(async () => { const s = await api.ocrStatus(docId); setOcr(s); if (s.status !== "running") clearInterval(t); }, 2000); } catch (e: any) { setError(e.message); } }

  return (
    <div className="flex h-full flex-col md:flex-row">
      <div className={`${railOpen ? "block" : "hidden"} h-full md:block`}>
        <Rail docs={docs} docId={docId} onSelectDoc={selectDoc} onDeleteDoc={deleteDoc} onUpload={upload} uploading={uploading}
          convs={shownConvs} convId={convId} onSelectConv={selectConv} onNewChat={() => { setConvId(null); setMessages([]); }} onDeleteConv={deleteConv} />
      </div>
      <main className={`${railOpen ? "hidden" : "flex"} min-h-0 min-w-0 flex-1 flex-col md:flex`}>
        <button className="btn-quiet m-3 h-11 self-start md:hidden" onClick={() => setRailOpen(true)}>Documents and conversations</button>
        {!doc ? (
          <div className="min-h-0 flex-1 overflow-y-auto"><EmptyState onUpload={upload} uploading={uploading} error={error} recent={docs} onOpen={selectDoc} /></div>
        ) : (
          <>
            <div className="flex flex-col gap-3.5 border-b border-rule bg-sheet px-8 pb-4 pt-5">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <h1 className="truncate font-reading text-[26px] font-semibold">{doc.filename}</h1>
                <span className="text-muted">{doc.n_pages} {doc.n_pages === 1 ? "page" : "pages"}{readsAll ? " · both methods read every page" : ""}</span>
                <span className="flex items-center gap-1 text-sm" title="Every question asked about this document, with both answers and the verdict">
                  <a className="btn-quiet h-9 !py-0" href={api.historyUrl(doc.id, "md")} download>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 4v11m-4-4 4 4 4-4M5 20h14" /></svg>
                    Download history</a>
                  <a className="px-2 py-2 text-muted underline-offset-2 hover:text-ink hover:underline" href={api.historyUrl(doc.id, "json")} download aria-label="Download history as JSON">JSON</a>
                </span>
                {research && ocr && (
                  <span className="ml-auto flex items-center gap-2 text-sm text-muted">
                    OCR kept for {ocr.cached_pages} of {ocr.total} pages
                    {ocr.status === "running" ? " (running…)" : ocr.cached_pages < ocr.total && <button className="btn-quiet h-8 !py-0" onClick={runOcr}>Run OCR on all pages</button>}
                  </span>
                )}
              </div>
              <PageStrip docId={doc.id} nPages={doc.n_pages} onOpen={setViewer}
                vlmPages={lastPayload?.vlm?.pages ?? []} ocrPages={lastPayload?.ocr?.pages ?? []} />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
              <div className="mx-auto flex max-w-[1120px] flex-col gap-5">
                {notice && <p role="status" className="rounded-md bg-vlm-soft px-3 py-2 text-sm">{notice}</p>}
                {messages.length === 0 && !busy && (
                  <div>
                    <p className="text-muted">Ask anything the document answers: a total, a date, a name, a value in a table, or a summary.</p>
                    <div className="mt-3 flex flex-wrap gap-2" aria-label="Example questions">
                      {["Summarize this document in five bullet points", "What are the most important numbers?", "Who is this document from and to whom?", "What dates or deadlines are mentioned?"].map((s) => (
                        <button key={s} className="btn-quiet h-9 !rounded-full !py-0" onClick={() => setQuestion(s)}>{s}</button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.map((m, i) => m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <p className="max-w-[70%] rounded-[12px_12px_2px_12px] bg-primary px-4 py-3 text-base text-on-primary">{m.content}</p>
                  </div>
                ) : (
                  <AnswerPair key={m.id} p={m.payload} docId={doc.id} research={research} onOpenPage={setViewer}
                    onAskAgain={busy ? undefined : () => { const q = messages[i - 1]?.role === "user" ? messages[i - 1].content : ""; if (q) void ask(q); }} />
                ))}
                {busy && <AskProgress nPages={doc.n_pages} pageCap={pageCap} mode={askMode} />}
                <div ref={feedEnd} />
              </div>
            </div>
            <div className="border-t border-rule bg-sheet px-8 pb-5 pt-4">
              <div className="mx-auto flex max-w-[1120px] flex-col gap-2.5">
                {error && <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-text">{error}</p>}
                <div className="flex flex-wrap items-end gap-2.5">
                  <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-[13px] text-muted" htmlFor="q">Your question
                    <textarea id="q" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={`Ask a question about ${doc.filename}…`}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(); } }}
                      className="field resize-none rounded-lg !px-3 !py-2.5 font-reading !text-[17px] text-ink" />
                  </label>
                  <div className="flex flex-col items-start gap-1.5">
                    <Segmented label="Which methods answer" value={askMode} onChange={setAskMode}
                      options={[{ value: "both", label: "Both" }, { value: "vlm", label: "Vision" }, { value: "ocr", label: "OCR" }]} />
                    {research && <label className="flex items-center gap-1.5 text-[13px] text-muted"><input type="checkbox" checked={short} onChange={(e) => setShort(e.target.checked)} /> Short answers</label>}
                  </div>
                  <button className="btn h-12 rounded-lg !px-6 text-[15px] font-semibold" disabled={busy || !question.trim()} onClick={() => void ask()}>
                    {busy ? "Answering…" : askMode === "both" ? "Ask both" : "Ask"}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </main>
      {doc && viewer != null && <PageViewer docId={doc.id} page={viewer} nPages={doc.n_pages} research={research} onClose={() => setViewer(null)} onPage={setViewer} />}
    </div>
  );
}
