"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card flex flex-col gap-2.5 px-6 py-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="flex flex-col gap-2 text-ink-soft">{children}</div>
    </section>
  );
}

export default function About() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => { api.health().then(setH).catch(() => setH(null)); }, []);
  const cap = h?.page_cap ?? 6;

  return (
    <div className="h-full overflow-y-auto px-4 py-7 sm:px-8">
      <div className="mx-auto flex max-w-[860px] flex-col gap-5">
        <div>
          <h1 className="font-reading text-[30px] font-semibold">How it works</h1>
          <p className="text-ink-soft">DocMind answers every question twice, by two methods that read the document differently, and shows you where they agree.</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="card flex flex-col gap-1.5 border-t-4 border-t-vlm px-5 py-4">
            <span className="text-[13px] font-semibold text-vlm">Vision model</span>
            <span className="font-semibold">Looks at the pages</span>
            <span className="text-ink-soft">Qwen2.5-VL reads each page as an image, so it sees layout, tables, stamps and handwriting as they are printed.</span>
          </div>
          <div className="card flex flex-col gap-1.5 border-t-4 border-t-ocr px-5 py-4">
            <span className="text-[13px] font-semibold text-ocr-text">OCR + text model</span>
            <span className="font-semibold">Reads the extracted text</span>
            <span className="text-ink-soft">OCR turns each page into text, and Qwen2.5 answers from that text alone. It is precise with words, but it cannot see what OCR missed or misread.</span>
          </div>
        </div>

        <Section title="Reading every page">
          <p>Both methods read the whole document, whatever its length. The GPU can only hold about {cap} page images at once, so the vision model reads long documents in parts of up to {cap} pages; the text model reads long OCR text in parts too. Each part is asked your question, and the parts that find something are combined.</p>
          <p>One limit: a question about two things on far-apart pages (“the Pune warehouse <em>and</em> the Nagpur depot”) can lose one half on the vision side. Ask about one thing at a time when that matters.</p>
        </Section>

        <Section title="Reading the verdict">
          <p><strong className="font-semibold text-ink">“Answers match”</strong> means the two independent readings agree. That is strong evidence, but not proof.</p>
          <p><strong className="font-semibold text-ink">“Found in the document”</strong> is the share of an answer's key words and numbers that are printed in the PDF's own embedded text, which neither method produced. A misreading such as “12oo0” for “12000” does not count as found.</p>
          <p>Scans and photos have no embedded text, so their answers cannot be checked this way; the verdict says so instead of guessing. None of this proves an answer is <em>correct</em>: a value can be printed in the document and still be the wrong one for the question.</p>
        </Section>

        <Section title="History">
          <p>Every question and both answers are saved. History belongs to the file itself: upload the same file again, even after deleting it, and its conversations come back. A question you already asked with the same settings is answered instantly from history; <strong className="font-semibold text-ink">Ask again</strong> recomputes it.</p>
          <p>See every file on the <Link href="/history" className="text-vlm underline">History</Link> page, and download a file's full record there or from the document's page.</p>
        </Section>

        <Section title="Which method is more accurate?">
          <p>A single question cannot tell you. Run an <Link href="/research" className="text-vlm underline">experiment</Link>: a set of questions with known answers, scored for both methods. DocMind only names a winner when the difference is larger than chance on that set.</p>
        </Section>

        <Section title="This installation">
          {h ? (
            <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-[180px_minmax(0,1fr)]">
              <dt className="text-muted">Mode</dt><dd>{h.demo_mode ? "Demo: text-matching stand-ins, not the models" : "Real models"}</dd>
              <dt className="text-muted">Vision model</dt><dd>{h.vlm ?? "not loaded"}</dd>
              <dt className="text-muted">Text model</dt><dd>{h.llm ?? "not loaded"}</dd>
              <dt className="text-muted">OCR engine</dt><dd>{h.ocr_engine}</dd>
              <dt className="text-muted">Pages per vision call</dt><dd>{h.page_cap}</dd>
              <dt className="text-muted">Reads every page</dt><dd>{h.read_all_pages === false ? "No: the vision model sees only the best-matching pages" : "Yes"}</dd>
              <dt className="text-muted">GPU</dt><dd>{h.gpu.available ? `${h.gpu.name}, ${h.gpu.free_gb} of ${h.gpu.total_gb} GB free (shared with other users)` : `none (${h.gpu.reason ?? "unavailable"})`}</dd>
            </dl>
          ) : <p className="text-muted">The backend is not reachable, so the settings cannot be shown.</p>}
          <p className="text-sm text-muted">Everything runs on this machine. Documents, answers and history are stored in <code>data/</code> and are not sent anywhere.</p>
        </Section>
      </div>
    </div>
  );
}
