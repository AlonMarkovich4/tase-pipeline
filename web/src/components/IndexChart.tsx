"use client";

import { useState } from "react";
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
  const [hover, setHover] = useState<number | null>(null);

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

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    const i = Math.round(rel * (series.length - 1));
    setHover(Math.max(0, Math.min(series.length - 1, i)));
  };
  const hp = hover != null ? pts[hover] : null;

  return (
    <div className="relative cursor-crosshair" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-64 w-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="idxFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1={padX} x2={W - padX} y1={padTop + g * (H - padTop - padBot)}
                y2={padTop + g * (H - padTop - padBot)} stroke="var(--color-grid)" />
        ))}
        <path d={area} fill="url(#idxFill)" />
        <path d={line} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinecap="round" />

        {/* hover guide line */}
        {hp && (
          <line x1={hp.x} x2={hp.x} y1={padTop} y2={H - padBot}
                stroke="var(--color-accent)" strokeWidth="1.5" strokeDasharray="5 4" opacity="0.6" />
        )}

        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === pts.length - 1 ? 5 : 3.5}
                  fill="var(--color-bg)" stroke="var(--color-accent)" strokeWidth="2"
                  opacity={hover == null || hover === i ? 1 : 0.5} />
        ))}
        <circle cx={last.x} cy={last.y} r="9" fill="var(--color-accent)" opacity="0.18" />
        {hp && <circle cx={hp.x} cy={hp.y} r="6" fill="var(--color-accent)" stroke="var(--color-bg)" strokeWidth="2" />}

        {series.map((s, i) => (
          <text key={i} x={x(i)} y={H - 12} textAnchor="middle"
                fill={hover === i ? "var(--color-text1)" : "var(--color-text3)"} fontSize="11">
            {s.date.slice(5).replace("-", "/")}
          </text>
        ))}
      </svg>

      {/* hover tooltip (HTML overlay — avoids SVG text stretching) */}
      {hover != null && hp && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[140%] whitespace-nowrap rounded-lg border border-border bg-surface2 px-2.5 py-1 text-center shadow-lg"
          style={{ left: `${(hp.x / W) * 100}%`, top: `${(hp.y / H) * 100}%` }}
        >
          <div className="text-[10px] text-text3">
            {(() => { const [, m, d] = series[hover].date.split("-"); return `${d}/${m}`; })()}
          </div>
          <div className="text-sm font-bold tabular-nums text-text1">
            {series[hover].value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      )}
    </div>
  );
}
