import type { IndexPoint } from "@/lib/data";

// Catmull-Rom -> cubic-bezier smoothing for a pleasant curve.
function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

export default function IndexChart({ series }: { series: IndexPoint[] }) {
  const W = 1000, H = 280, padX = 40, padTop = 24, padBot = 40;
  const values = series.map((s) => s.value);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => padX + (i * (W - 2 * padX)) / Math.max(series.length - 1, 1);
  const y = (v: number) => padTop + (1 - (v - min) / span) * (H - padTop - padBot);
  const pts = series.map((s, i) => ({ x: x(i), y: y(s.value) }));
  const line = smoothPath(pts);
  const area = `${line} L ${pts.at(-1)!.x} ${H - padBot} L ${pts[0].x} ${H - padBot} Z`;
  const last = pts.at(-1)!;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-64 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="idxFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((g) => (
        <line key={g} x1={padX} x2={W - padX} y1={padTop + g * (H - padTop - padBot)}
              y2={padTop + g * (H - padTop - padBot)} stroke="rgba(255,255,255,.05)" />
      ))}
      <path d={area} fill="url(#idxFill)" />
      <path d={line} fill="none" stroke="var(--color-accent)" strokeWidth="2.5"
            strokeLinecap="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={i === pts.length - 1 ? 5 : 3.5}
                fill="var(--color-bg)" stroke="var(--color-accent)" strokeWidth="2" />
      ))}
      <circle cx={last.x} cy={last.y} r="9" fill="var(--color-accent)" opacity="0.18" />
      {series.map((s, i) =>
        i % 1 === 0 ? (
          <text key={i} x={x(i)} y={H - 12} textAnchor="middle"
                fill="var(--color-text3)" fontSize="11">
            {s.date.slice(5).replace("-", "/")}
          </text>
        ) : null,
      )}
    </svg>
  );
}
