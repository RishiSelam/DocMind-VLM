/**
 * The DocMind "converter": one document goes in, splits into two readers (vision: teal, OCR: amber), and the two
 * streams converge into a single verdict. Pure SVG + CSS animation; motion stops under prefers-reduced-motion.
 */
export default function ConverterHero({ className = "" }: { className?: string }) {
  const line = (y: number, w: number) => <rect x={64} y={y} width={w} height={6} rx={3} className="fill-white/25" />;
  return (
    <svg viewBox="0 0 960 380" className={className} role="img" aria-label="A document is read twice, by a vision model and by OCR, and the two readings converge into one verdict">
      <defs>
        <linearGradient id="beam" x1="0" x2="1">
          <stop offset="0" style={{ stopColor: "rgb(var(--vlm))", stopOpacity: 0 }} />
          <stop offset="0.5" style={{ stopColor: "rgb(var(--vlm))", stopOpacity: 0.9 }} />
          <stop offset="1" style={{ stopColor: "rgb(var(--vlm))", stopOpacity: 0 }} />
        </linearGradient>
        <clipPath id="page"><rect x="40" y="60" width="200" height="260" rx="14" /></clipPath>
      </defs>

      {/* the document, being scanned */}
      <g>
        <rect x="40" y="60" width="200" height="260" rx="14" className="fill-white/[0.06] stroke-white/30" strokeWidth="1.5" />
        <rect x="64" y="88" width="96" height="10" rx="5" className="fill-white/60" />
        {line(116, 150)}{line(132, 136)}{line(148, 152)}
        <rect x="64" y="172" width="152" height="22" rx="5" className="fill-vlm/20 stroke-vlm" strokeWidth="1.5" />
        <rect x="72" y="181" width="96" height="5" rx="2.5" className="fill-white/80" />
        {line(208, 140)}{line(224, 152)}{line(240, 120)}{line(264, 150)}{line(280, 100)}
        <g clipPath="url(#page)"><rect x="40" y="60" width="200" height="3" fill="url(#beam)" className="conv-scan" /></g>
      </g>

      {/* two streams leave the page... */}
      <path d="M244 160 C 330 160, 340 96, 430 96" className="conv-flow stroke-vlm" />
      <path d="M244 220 C 330 220, 340 284, 430 284" className="conv-flow conv-flow-late stroke-ocr" />

      {/* ...through the two readers... */}
      <g>
        <circle cx="474" cy="96" r="44" className="fill-vlm/15 stroke-vlm" strokeWidth="1.5" />
        <path d="M452 96 C 460 84, 488 84, 496 96 C 488 108, 460 108, 452 96 Z" className="fill-none stroke-vlm" strokeWidth="2.2" />
        <circle cx="474" cy="96" r="5.5" className="fill-vlm" />
        <text x="474" y="168" textAnchor="middle" className="fill-white/80 text-[15px] font-medium">Vision model</text>
        <circle cx="474" cy="284" r="44" className="fill-ocr/15 stroke-ocr" strokeWidth="1.5" />
        <text x="474" y="292" textAnchor="middle" className="fill-ocr font-reading text-[24px] font-semibold">Aa</text>
        <text x="474" y="356" textAnchor="middle" className="fill-white/80 text-[15px] font-medium">OCR + text model</text>
      </g>

      {/* ...and converge into one verdict */}
      <path d="M518 96 C 610 96, 620 190, 700 190" className="conv-flow conv-flow-mid stroke-vlm" />
      <path d="M518 284 C 610 284, 620 190, 700 190" className="conv-flow conv-flow-late stroke-ocr" />
      <g className="conv-seal">
        <circle cx="770" cy="190" r="64" className="fill-white/[0.06] stroke-white/40" strokeWidth="1.5" />
        <circle cx="770" cy="190" r="48" className="fill-white" />
        <path d="m748 190 15 15 30-32" className="fill-none stroke-bench" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <text x="770" y="290" textAnchor="middle" className="fill-white text-[15px] font-semibold">One verdict</text>
      <text x="770" y="312" textAnchor="middle" className="fill-white/60 text-[13px]">with its evidence and a trust score</text>
    </svg>
  );
}
