"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AnswerPair from "@/components/AnswerPair";
import { useMode } from "@/components/ModeContext";
import PageStrip from "@/components/PageStrip";
import PageViewer from "@/components/PageViewer";
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
  const feedEnd = useRef<HTMLDivElement>(null);

  const doc = useMemo(() => docs.find((d) => d.id === docId) ?? null, [docs, docId]);
  const shownConvs = useMemo(() => convs.filter((c) => !docId || c.doc_id === docId), [convs, docId]);

  const refresh = useCallback(async () => {
    try { const [d, c] = await Promise.all([api.documents(), api.conversations()]); setDocs(d); setConvs(c); }
    catch (e: any) { setError(e.message); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
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
    try { const d = await api.upload(file); await refresh(); selectDoc(d.id); setRailOpen(false); }
    catch (e: any) { setError(e.message); } finally { setUploading(false); }
  }
  function selectDoc(id: string) { setDocId(id); setConvId(null); setMessages([]); setError(null); setRailOpen(false); }
  async function selectConv(c: Conversation) {
    setError(null);
    try { const full = await api.conversation(c.id); setDocId(c.doc_id); setConvId(c.id); setMessages(full.messages); setRailOpen(false); }
    catch (e: any) { setError(e.message); }
  }
  async function deleteDoc(id: string) { try { await api.deleteDoc(id); if (id === docId) { setDocId(null); setConvId(null); setMessages([]); } await refresh(); } catch (e: any) { setError(e.message); } }
  async function deleteConv(id: string) { try { await api.deleteConversation(id); if (id === convId) { setConvId(null); setMessages([]); } await refresh(); } catch (e: any) { setError(e.message); } }

  async function ask() {
    const q = question.trim();
    if (!q || !docId || busy) return;
    setBusy(true); setError(null); setQuestion("");
    const optimistic: Message = { id: `tmp_${Date.now()}`, conversation_id: convId ?? "", role: "user", content: q, payload: {}, created_at: Date.now() / 1000 };
    setMessages((m) => [...m, optimistic]);
    try {
      const r = await api.ask({ doc_id: docId, conversation_id: convId ?? undefined, question: q, mode: askMode, short });
      setConvId(r.conversation_id);
      setMessages((m) => [...m.filter((x) => x.id !== optimistic.id), r.user_message, r.assistant_message]);
      void refresh();
    } catch (e: any) {
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
      setQuestion(q);
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
        <button className="btn-quiet m-2 self-start md:hidden" onClick={() => setRailOpen(true)}>Documents</button>
        {!doc ? (
          <div className="m-auto max-w-md p-6">
            <h1 className="font-reading text-2xl font-semibold">Ask a document, twice.</h1>
            <p className="mt-2 text-muted">Upload a PDF or a page image. DocMind answers your question by reading the page image directly, and again by running OCR and handing the text to a language model, then shows you where the two answers differ.</p>
            <p className="mt-2 text-sm text-muted">Upload with the panel on the left. A sample PDF is created by <code>python scripts/make_sample_data.py</code>.</p>
            {error && <p role="alert" className="mt-3 rounded-[4px] bg-bad-soft p-2 text-sm text-bad">{error}</p>}
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-x-4 border-b border-rule px-4 py-2">
              <h1 className="truncate font-reading text-lg font-semibold">{doc.filename}</h1>
              <span className="text-sm text-muted">{doc.n_pages} {doc.n_pages === 1 ? "page" : "pages"}</span>
              {research && ocr && (
                <span className="ml-auto flex items-center gap-2 text-sm text-muted">
                  OCR cached for {ocr.cached_pages} of {ocr.total} pages
                  {ocr.status === "running" ? " (running…)" : ocr.cached_pages < ocr.total && <button className="btn-quiet !py-0.5" onClick={runOcr}>Run OCR on all pages</button>}
                </span>
              )}
            </div>
            <PageStrip docId={doc.id} nPages={doc.n_pages} onOpen={setViewer}
              vlmPages={lastPayload?.vlm?.pages ?? []} ocrPages={lastPayload?.ocr?.pages ?? []} />
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {messages.length === 0 && <p className="mx-auto max-w-xl text-muted">Ask something the page answers, such as a total, a date, a name, or a value in a table.</p>}
              <div className="mx-auto max-w-5xl space-y-5">
                {messages.map((m) => m.role === "user" ? (
                  <p key={m.id} className="font-reading text-lg font-semibold">{m.content}</p>
                ) : (
                  <div key={m.id}>
                    {m.payload.demo && <p className="mb-1 text-xs text-warn">Demo mode: these answers come from text-matching stand-ins, not from the models.</p>}
                    <AnswerPair p={m.payload} docId={doc.id} research={research} onOpenPage={setViewer} />
                  </div>
                ))}
                {busy && <p role="status" className="text-sm text-muted">Reading the document… the first question can take a while because OCR runs on every page.</p>}
                <div ref={feedEnd} />
              </div>
            </div>
            <div className="border-t border-rule bg-sheet px-4 py-3">
              {error && <p role="alert" className="mx-auto mb-2 max-w-5xl rounded-[4px] bg-bad-soft p-2 text-sm text-bad">{error}</p>}
              <div className="mx-auto flex max-w-5xl flex-wrap items-end gap-2">
                <label className="sr-only" htmlFor="q">Your question</label>
                <textarea id="q" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What is the total due?"
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(); } }}
                  className="field min-w-[12rem] flex-1 resize-none font-reading text-base" />
                {research && (
                  <div className="flex flex-col gap-1 text-sm">
                    <select aria-label="Which pipelines to run" className="field" value={askMode} onChange={(e) => setAskMode(e.target.value as any)}>
                      <option value="both">Both pipelines</option><option value="vlm">Vision only</option><option value="ocr">OCR + text only</option>
                    </select>
                    <label className="flex items-center gap-1"><input type="checkbox" checked={short} onChange={(e) => setShort(e.target.checked)} /> Short answers</label>
                  </div>
                )}
                <button className="btn" disabled={busy || !question.trim()} onClick={() => void ask()}>{busy ? "Asking…" : "Ask"}</button>
              </div>
            </div>
          </>
        )}
      </main>
      {doc && viewer != null && <PageViewer docId={doc.id} page={viewer} nPages={doc.n_pages} research={research} onClose={() => setViewer(null)} onPage={setViewer} />}
    </div>
  );
}
