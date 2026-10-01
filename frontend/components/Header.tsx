"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { useMode } from "./ModeContext";
import Segmented from "./Segmented";
import ThemeToggle from "./ThemeToggle";

export const NAV = [
  { href: "/ask", label: "Ask" },
  { href: "/history", label: "History" },
  { href: "/research", label: "Experiments" },
  { href: "/about", label: "How it works" },
] as const;

export default function Header() {
  const { mode, setMode } = useMode();
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => api.health().then((h) => alive && (setHealth(h), setDown(false))).catch(() => alive && setDown(true));
    tick();
    const t = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  useEffect(() => setMenu(false), [path]);

  // One status line: offline, demo, or the real models and the shared GPU's free memory.
  const status = down
    ? { dot: "bg-bad", text: "Backend offline", cls: "text-bad" }
    : !health ? null
      : health.demo_mode
        ? { dot: "bg-warn", text: "Demo mode · answers are text-matching stand-ins, not Qwen", cls: "text-warn-text" }
        : { dot: "bg-agree", text: `Real models · ${health.gpu.available ? `${health.gpu.name} · ${health.gpu.free_gb} GB free` : "no GPU"}`, cls: "text-muted" };

  const viewToggle = (
    <div className="flex items-center gap-3">
      <Segmented label="View" value={mode} onChange={setMode}
        options={[{ value: "user", label: "Simple" }, { value: "research", label: "Detailed", title: "Adds the claim table, how each answer was put together, page ranking, OCR audit and timings" }]} />
      <ThemeToggle />
    </div>
  );

  return (
    <header className="relative z-20 border-b border-rule bg-sheet">
      <div className="flex h-16 items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="font-reading text-2xl font-semibold">DocMind</Link>
        <nav aria-label="Main" className="hidden h-full gap-1 md:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={path === n.href ? "page" : undefined}
              className={`flex h-full items-center px-3 ${path === n.href ? "border-b-[3px] border-ink pt-[3px] font-semibold" : "text-muted hover:text-ink"}`}>{n.label}</Link>
          ))}
        </nav>
        <div className="ml-auto hidden items-center gap-4 text-sm lg:flex">
          {status && <span className={`flex items-center gap-2 ${status.cls}`}><span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden />{status.text}</span>}
        </div>
        <div className="ml-auto hidden md:block lg:ml-0">{viewToggle}</div>
        <button className="ml-auto flex h-11 w-11 items-center justify-center rounded-md hover:bg-bench md:hidden" aria-expanded={menu} aria-controls="mobile-nav"
          aria-label={menu ? "Close menu" : "Open menu"} onClick={() => setMenu(!menu)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            {menu ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </div>
      {menu && (
        <div id="mobile-nav" className="absolute inset-x-0 top-16 border-b border-rule bg-sheet px-4 pb-4 shadow-sm md:hidden">
          <nav aria-label="Main" className="flex flex-col">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} aria-current={path === n.href ? "page" : undefined}
                className={`flex min-h-12 items-center rounded-md px-3 ${path === n.href ? "bg-bench font-semibold" : "hover:bg-bench"}`}>{n.label}</Link>
            ))}
          </nav>
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-rule pt-3 text-sm">
            {status && <span className={`flex items-center gap-2 ${status.cls}`}><span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden />{status.text}</span>}
            {viewToggle}
          </div>
        </div>
      )}
    </header>
  );
}
