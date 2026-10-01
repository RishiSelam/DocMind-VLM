"use client";
import { useEffect, useRef, useState } from "react";

// Pen colours from tailwind.config.ts. The lighter OCR step marks the text-model share of the OCR pipeline's time.
export const COLORS = { vlm: "rgb(var(--vlm))", ocr: "rgb(var(--ocr))", ocrLight: "rgb(var(--ocr-light))", grid: "rgb(var(--rule))", ink: "rgb(var(--ink))", muted: "rgb(var(--muted))", track: "rgb(var(--track))" };

export type Segment = { value: number; color: string; name: string };
export type Bar = { who: string; segments: Segment[]; label: string; tip: string };
export type Group = { name: string; bars: Bar[] }; // an empty name draws no group label

/** 0, then 4-5 round steps (1, 2 or 5 x 10^k) that cover `max`. */
export function niceTicks(max: number): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? 10 * mag;
  const ticks = [];
  for (let t = 0; t < max + step * 0.999; t += step) ticks.push(+t.toFixed(10));
  return ticks;
}

const BAR_H = 14, BAR_GAP = 2, LABEL_H = 18, GROUP_GAP = 14, AXIS_H = 22, LEFT = 52, RIGHT_PAD = 108; // room for value labels such as "20 of 20 pages"

export default function BarChart({ title, groups, max, tickFmt, legend, caption }: {
  title: string; groups: Group[]; max?: number; tickFmt: (v: number) => string;
  legend: { name: string; color: string }[]; caption?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(480);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const dataMax = Math.max(...groups.flatMap((g) => g.bars.map((b) => b.segments.reduce((a, s) => a + s.value, 0))), 0);
  const ticks = niceTicks(max ?? dataMax);
  const top = ticks[ticks.length - 1];
  const plotW = width - LEFT - RIGHT_PAD;
  const x = (v: number) => LEFT + (Math.min(v, top) / top) * plotW;

  // Vertical layout: each group is a label line followed by its bars.
  let y = 4;
  const laid = groups.map((g) => {
    const labelY = y + 12;
    if (g.name) y += LABEL_H;
    const bars = g.bars.map((b) => { const by = y; y += BAR_H + BAR_GAP; return { ...b, y: by }; });
    y += GROUP_GAP - BAR_GAP;
    return { ...g, labelY, bars };
  });
  const plotBottom = y - GROUP_GAP + 6;
  const height = plotBottom + AXIS_H;

  const show = (e: React.MouseEvent | React.FocusEvent, text: string) => {
    const r = box.current!.getBoundingClientRect();
    const t = e.currentTarget.getBoundingClientRect();
    const px = "clientX" in e ? e.clientX : t.left + t.width / 2;
    setTip({ x: Math.max(Math.min(px - r.left + 12, width - 220), 0), y: t.bottom - r.top + 4, text }); // below the row: never clipped by the legend
  };

  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-1">
        <div className="text-base font-semibold">{title}</div>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted" aria-hidden>
          {legend.map((l) => (
            <span key={l.name} className="inline-flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: l.color }} />{l.name}
            </span>
          ))}
        </div>
      </figcaption>
      <div ref={box} className="relative w-full min-w-0" onMouseLeave={() => setTip(null)}>
        <svg width={width} height={height} style={{ maxWidth: "100%" }} role="group" aria-label={`${title}. ${caption ?? ""}`} className="block">
          {laid.flatMap((g) => g.bars.map((b) => <rect key={`${g.name}-${b.who}`} x={LEFT} y={b.y} width={plotW} height={BAR_H} style={{ fill: COLORS.track }} />))}
          {ticks.map((t) => (
            <g key={t}>
              {laid.map((g) => g.bars.length > 0 && (
                <line key={g.name} x1={x(t)} x2={x(t)} y1={g.bars[0].y - 3} y2={g.bars[g.bars.length - 1].y + BAR_H + 3}
                  style={{ stroke: COLORS.grid }} strokeWidth={t === 0 ? 1.5 : 1} strokeDasharray={t === 0 ? undefined : "2 3"} />
              ))}
              <text x={x(t)} y={plotBottom + 15} textAnchor="middle" fontSize={11} style={{ fill: COLORS.muted }}>{tickFmt(t)}</text>
            </g>
          ))}
          {laid.map((g) => (
            <g key={g.name}>
              {g.name && <text x={0} y={g.labelY} fontSize={12} fontWeight={600} style={{ fill: COLORS.ink }}>{g.name}</text>}
              {g.bars.map((b) => {
                let acc = 0;
                const total = b.segments.reduce((a, s) => a + s.value, 0);
                return (
                  <g key={b.who}>
                    <text x={LEFT - 6} y={b.y + BAR_H - 3} textAnchor="end" fontSize={12} style={{ fill: COLORS.muted }}>{b.who}</text>
                    {b.segments.map((s, i) => {
                      const x0 = x(acc), x1 = x(acc + s.value);
                      acc += s.value;
                      const last = i === b.segments.length - 1;
                      // 2px surface gap between stacked segments; rounded data end on the last one only
                      const w = Math.max(x1 - x0 - (last ? 0 : 2), s.value > 0 ? 2 : 0);
                      return last
                        ? <path key={i} d={roundedRight(x0, b.y, w, BAR_H, Math.min(4, w))} style={{ fill: s.color }} />
                        : <rect key={i} x={x0} y={b.y} width={w} height={BAR_H} style={{ fill: s.color }} />;
                    })}
                    <text x={x(total) + 6} y={b.y + BAR_H - 3} fontSize={12} style={{ fill: COLORS.ink }}>{b.label}</text>
                    {/* hit target: the whole row, larger than the mark */}
                    <rect x={0} y={b.y - 1} width={width} height={BAR_H + 2} fill="transparent" tabIndex={0} aria-label={b.tip}
                      onMouseMove={(e) => show(e, b.tip)} onFocus={(e) => show(e, b.tip)} onBlur={() => setTip(null)} className="outline-none focus:stroke-ink" />
                  </g>
                );
              })}
            </g>
          ))}
        </svg>
        {tip && (
          <div role="tooltip" className="pointer-events-none absolute z-10 max-w-[210px] rounded-[4px] bg-primary px-2 py-1 text-xs text-on-primary shadow"
            style={{ left: tip.x, top: tip.y }}>{tip.text}</div>
        )}
      </div>
      {caption && <p className="mt-2 text-[13px] text-muted">{caption}</p>}
      <details className="mt-1 text-xs">
        <summary className="cursor-pointer text-muted">Show as table</summary>
        <table className="mt-1 w-full text-left">
          <tbody>
            {groups.flatMap((g) => g.bars.map((b) => (
              <tr key={g.name + b.who} className="border-t border-rule"><td className="py-0.5 pr-2 text-muted">{g.name}</td><td className="pr-2">{b.who}</td><td>{b.label}</td></tr>
            )))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

function roundedRight(x: number, y: number, w: number, h: number, r: number): string {
  if (w <= 0) return "";
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h - rr} Q${x + w},${y + h} ${x + w - rr},${y + h} H${x} Z`;
}
