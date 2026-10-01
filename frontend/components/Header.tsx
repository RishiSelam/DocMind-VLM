"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { useMode } from "./ModeContext";

export default function Header() {
  const { mode, setMode } = useMode();
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => api.health().then((h) => alive && (setHealth(h), setDown(false))).catch(() => alive && setDown(true));
    tick();
    const t = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const nav = (href: string, label: string) => (
    <Link href={href} className={`px-1 pb-0.5 text-sm ${path === href ? "border-b-2 border-ink font-semibold" : "text-muted hover:text-ink"}`}>{label}</Link>
  );

  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-rule bg-sheet px-4 py-2.5">
      <Link href="/" className="font-reading text-xl font-semibold tracking-tight">DocMind</Link>
      <nav className="flex gap-4">{nav("/", "Workbench")}{nav("/research", "Research")}</nav>
      <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
        {down && <span className="rounded-[4px] bg-bad-soft px-2 py-0.5 text-bad">Backend offline</span>}
        {health?.demo_mode && (
          <span title="Answers come from simple text-matching stand-ins, not from Qwen. Use it to try the app, not to judge the models."
            className="rounded-[4px] border border-warn px-2 py-0.5 text-warn">Demo mode</span>
        )}
        {health && !health.demo_mode && (
          <span className="text-muted">{health.gpu.available ? `${health.gpu.name} · ${health.gpu.free_gb} GB free` : "No GPU"}</span>
        )}
        <div role="group" aria-label="Interface mode" className="flex overflow-hidden rounded-[4px] border border-ink">
          {(["user", "research"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
              className={`px-3 py-1 ${mode === m ? "bg-ink text-white" : "bg-transparent hover:bg-bench"}`}>{m === "user" ? "Simple" : "Research"}</button>
          ))}
        </div>
      </div>
    </header>
  );
}
