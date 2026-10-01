"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import ConverterHero from "@/components/ConverterHero";
import { api, pct } from "@/lib/api";
import type { Experiment } from "@/lib/types";

/** Sections rise into view once, as they are scrolled to. */
function Reveal({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect(); } }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={`reveal ${shown ? "shown" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</div>;
}

function Icon({ kind }: { kind: "eye" | "text" | "seal" }) {
  const p = { width: 28, height: 28, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  if (kind === "eye") return <svg {...p}><path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z" /><circle cx="12" cy="12" r="2.8" /></svg>;
  if (kind === "text") return <svg {...p}><path d="M4 7V5h16v2M12 5v14M9 19h6" /></svg>;
  return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></svg>;
}

export default function Landing() {
  const [exp, setExp] = useState<Experiment | null>(null);
  useEffect(() => {
    api.experiments().then((es) => setExp(es.find((e) => e.status === "finished" && e.metrics?.trust && !e.config.demo_mode) ?? null)).catch(() => {});
  }, []);
  const t = exp?.metrics.trust;

  return (
    <div className="h-full overflow-y-auto">
      {/* hero: always dark, like a product stage */}
      <section className="dark relative overflow-hidden bg-bench text-ink">
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 mx-auto h-[520px] max-w-5xl rounded-full bg-vlm/10 blur-[120px]" />
        <div className="relative mx-auto flex max-w-6xl flex-col items-center px-6 pb-16 pt-20 text-center sm:pt-28">
          <p className="rise text-sm font-semibold uppercase tracking-[0.18em] text-vlm">DocMind</p>
          <h1 className="rise mt-4 max-w-4xl font-reading text-[44px] font-semibold leading-[1.05] tracking-tight sm:text-[76px]" style={{ animationDelay: "80ms" }}>
            Read every document twice.
          </h1>
          <p className="rise mt-6 max-w-2xl text-lg text-ink-soft sm:text-xl" style={{ animationDelay: "160ms" }}>
            A vision model looks at the page. OCR reads its text. DocMind shows where they agree, where each answer came from, and how far to trust it.
          </p>
          <div className="rise mt-9 flex flex-wrap justify-center gap-3" style={{ animationDelay: "240ms" }}>
            <Link href="/ask" className="inline-flex h-12 items-center rounded-full bg-primary px-7 text-[15px] font-semibold text-on-primary transition hover:brightness-110 active:scale-[0.98]">Open the workspace</Link>
            <Link href="/about" className="inline-flex h-12 items-center rounded-full border border-rule px-7 text-[15px] transition hover:border-ink">How it works</Link>
          </div>
          <ConverterHero className="rise mt-14 w-full max-w-4xl" />
        </div>
      </section>

      {/* two readers, one verdict */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <Reveal className="mx-auto max-w-3xl text-center">
          <h2 className="font-reading text-4xl font-semibold tracking-tight sm:text-5xl">Two readers. One verdict.</h2>
          <p className="mt-4 text-lg text-ink-soft">They fail in different ways, which is exactly why reading twice works.</p>
        </Reveal>
        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {[
            { k: "eye" as const, tone: "text-vlm bg-vlm-soft", title: "The vision model sees the page", text: "Qwen2.5-VL reads page images directly, so layout, tables, stamps and handwriting stay intact." },
            { k: "text" as const, tone: "text-ocr bg-ocr-soft", title: "OCR reads the words", text: "The page is turned into text and Qwen2.5 answers from it: precise with words, blind to what OCR missed." },
            { k: "seal" as const, tone: "text-agree bg-agree-soft", title: "You get one verdict", text: "Which answer to use, whether the document backs it, and a trust score with its reasons." },
          ].map((c, i) => (
            <Reveal key={c.title} delay={i * 120} className="card flex flex-col gap-3 p-7">
              <span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${c.tone}`}><Icon kind={c.k} /></span>
              <h3 className="text-xl font-semibold">{c.title}</h3>
              <p className="text-ink-soft">{c.text}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* explainability: evidence, look closer */}
      <section className="border-y border-rule bg-sheet">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-24 lg:grid-cols-2">
          <Reveal>
            <p className="eyebrow">Explainable by design</p>
            <h2 className="mt-3 font-reading text-4xl font-semibold tracking-tight sm:text-5xl">See where every answer came from.</h2>
            <p className="mt-5 text-lg text-ink-soft">Both readers mark the spot they read. If they disagree, DocMind enlarges that spot and reads it again. Then it hides the evidence and asks once more: if the answer survives, the highlight was not what it relied on.</p>
            <ul className="mt-6 flex flex-col gap-2 text-ink-soft">
              <li className="flex gap-2.5"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-vlm" />Evidence boxes from both readers, on the page</li>
              <li className="flex gap-2.5"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-ocr" />A closer look whenever the answers differ</li>
              <li className="flex gap-2.5"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-agree" />A faithfulness test, so explanations are checked, not assumed</li>
            </ul>
          </Reveal>
          <Reveal delay={150}>
            <figure className="card overflow-hidden p-0 shadow-xl shadow-black/5">
              <div className="flex flex-col gap-2.5 bg-paper p-7">
                <span className="h-2.5 w-24 rounded bg-muted/50" />
                <span className="h-2 w-full rounded bg-track" /><span className="h-2 w-5/6 rounded bg-track" />
                <div className="relative mt-2 rounded-md px-3 py-2.5">
                  <span aria-hidden className="absolute inset-0 rounded-md border-[3px] border-vlm" />
                  <span aria-hidden className="absolute inset-1 rounded border-2 border-ocr bg-ocr/10" />
                  <span className="relative font-reading text-xl">The audit committee chair is Meera Iyer.</span>
                </div>
                <span className="h-2 w-4/5 rounded bg-track" /><span className="h-2 w-2/3 rounded bg-track" />
              </div>
              <figcaption className="grid gap-3 border-t border-rule p-6 sm:grid-cols-2">
                <div><div className="text-[13px] font-semibold text-vlm">Vision model</div><div className="font-reading text-lg">Meera Iyer</div></div>
                <div><div className="text-[13px] font-semibold text-ocr-text">OCR + text model</div><div className="font-reading text-lg">Meera <mark className="rounded bg-bad-soft px-1 text-bad-text">lyer</mark></div></div>
                <p className="text-sm text-ink-soft sm:col-span-2">Looking closer reads “Meera Iyer”: the vision answer is confirmed. <span className="text-muted">From a real run on an 8-page report.</span></p>
              </figcaption>
            </figure>
          </Reveal>
        </div>
      </section>

      {/* trust you can measure: live numbers from the latest real experiment, or nothing */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <Reveal className="mx-auto max-w-3xl text-center">
          <h2 className="font-reading text-4xl font-semibold tracking-tight sm:text-5xl">Trust you can measure.</h2>
          <p className="mt-4 text-lg text-ink-soft">A trust score is only useful if it predicts mistakes. DocMind tests that on questions with known answers.</p>
        </Reveal>
        {t ? (
          <Reveal delay={120} className="mt-12 grid gap-5 sm:grid-cols-3">
            {[["AUROC of the trust score", t.auroc_trust == null ? "n/a" : t.auroc_trust.toFixed(2), "how well it separates right from wrong answers (0.5 = chance)"],
              ["Accuracy, most-trusted quarter", pct(t.risk_coverage[0]?.accuracy, 0), `answering only the top ${t.risk_coverage[0]?.n} of ${t.n} questions`],
              ["Accuracy, every question", pct(t.accuracy, 0), `recommended answer, all ${t.n} questions`]].map(([k, v, s]) => (
              <div key={k} className="card flex flex-col gap-1 p-7 text-center">
                <span className="font-mono text-5xl font-medium tracking-tight">{v}</span>
                <span className="mt-2 font-semibold">{k}</span>
                <span className="text-sm text-muted">{s}</span>
              </div>
            ))}
            <p className="text-center text-sm text-muted sm:col-span-3">From experiment {exp!.id} “{exp!.name}”, real models. <Link href="/research" className="underline">See the full results</Link>.</p>
          </Reveal>
        ) : (
          <Reveal delay={120} className="mx-auto mt-10 max-w-xl text-center text-ink-soft">
            No finished experiment with trust scores yet. <Link href="/research" className="text-vlm underline">Run one</Link> to see these numbers for your own questions.
          </Reveal>
        )}
      </section>

      {/* closing call */}
      <section className="dark bg-bench text-ink">
        <Reveal className="mx-auto flex max-w-4xl flex-col items-center px-6 py-24 text-center">
          <h2 className="font-reading text-4xl font-semibold tracking-tight sm:text-5xl">Your documents stay on this machine.</h2>
          <p className="mt-4 max-w-2xl text-lg text-ink-soft">Both models run locally on the GPU. Nothing is uploaded anywhere, and every answer is kept in your history.</p>
          <Link href="/ask" className="mt-9 inline-flex h-12 items-center rounded-full bg-primary px-7 text-[15px] font-semibold text-on-primary transition hover:brightness-110 active:scale-[0.98]">Open the workspace</Link>
        </Reveal>
      </section>
    </div>
  );
}
