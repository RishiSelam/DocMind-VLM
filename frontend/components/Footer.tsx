"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { API, api } from "@/lib/api";
import type { Health } from "@/lib/types";

const short = (id?: string | null) => (id ? id.split("/").pop() : null);

/** A slim bar under every page: what is running, where the data lives, and where to read more. */
export default function Footer() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => { api.health().then(setH).catch(() => setH(null)); }, []);

  return (
    <footer className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-rule bg-sheet px-4 py-2 text-[13px] text-muted sm:px-6">
      <span className="font-medium text-ink">DocMind v2</span>
      {h && (
        <span className="hidden sm:inline">
          {h.demo_mode ? "Demo mode (no models)" : `Vision ${short(h.vlm)} · Text ${short(h.llm)}`} · OCR {h.ocr_engine}
        </span>
      )}
      <span className="hidden md:inline">Runs on this machine: your documents and history stay here.</span>
      <nav aria-label="Footer" className="ml-auto flex items-center gap-4">
        <Link href="/history" className="hover:text-ink hover:underline">History</Link>
        <Link href="/about" className="hover:text-ink hover:underline">How it works</Link>
        <a href={`${API}/docs`} target="_blank" rel="noreferrer" className="hover:text-ink hover:underline">API reference</a>
      </nav>
    </footer>
  );
}
