"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** A segmented control whose highlight slides to the chosen option. */
export default function Segmented<T extends string>({ options, value, onChange, label, className = "" }: {
  options: { value: T; label: string; title?: string }[]; value: T; onChange: (v: T) => void; label: string; className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);
  const measure = () => {
    const el = refs.current[options.findIndex((o) => o.value === value)];
    if (el) setPill({ left: el.offsetLeft, width: el.offsetWidth });
  };
  useLayoutEffect(measure, [value, options.length]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); });

  return (
    <div role="radiogroup" aria-label={label} className={`relative inline-flex rounded-full border border-rule bg-paper p-1 ${className}`}>
      {pill && <span aria-hidden className="absolute bottom-1 top-1 rounded-full bg-primary shadow-sm transition-[left,width] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]" style={{ left: pill.left, width: pill.width }} />}
      {options.map((o, i) => (
        <button key={o.value} ref={(el) => { refs.current[i] = el; }} role="radio" aria-checked={value === o.value} title={o.title}
          onClick={() => onChange(o.value)}
          className={`relative z-10 h-8 whitespace-nowrap rounded-full px-3.5 text-sm transition-colors duration-300 ${value === o.value ? "text-on-primary" : "text-muted hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
