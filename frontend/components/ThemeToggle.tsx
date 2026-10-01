"use client";
import { useEffect, useState } from "react";

/** Light/dark switch. The choice is remembered; until one is made the system setting decides (see app/layout.tsx). */
export default function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => { setDark(document.documentElement.classList.contains("dark")); }, []);

  function flip() {
    const next = !dark;
    const root = document.documentElement;
    root.classList.add("theme-switching");
    root.classList.toggle("dark", next);
    setTimeout(() => root.classList.remove("theme-switching"), 400);
    try { localStorage.setItem("docmind.theme", next ? "dark" : "light"); } catch {}
    setDark(next);
  }

  return (
    <button role="switch" aria-checked={dark} aria-label="Dark mode" title={dark ? "Switch to light mode" : "Switch to dark mode"} onClick={flip}
      className="relative h-8 w-[60px] shrink-0 rounded-full border border-rule bg-track transition-colors">
      <span aria-hidden className={`absolute left-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-paper text-ink shadow transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${dark ? "translate-x-7" : ""}`}>
        {dark ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        )}
      </span>
    </button>
  );
}
