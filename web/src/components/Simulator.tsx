"use client";

import { useEffect, useMemo, useState } from "react";
import type { ExpiryChain, ChainRow } from "@/lib/data";
import { Trending, Refresh } from "@/components/icons";
import { dispatchToDemo } from "@/app/simulator/actions";

const MULT = 50; // ₪ per index point per contract
const COMMISSION = 2.5; // ₪ fixed commission per contract

type Side = 1 | -1; // +1 buy, -1 sell
type Kind = "call" | "put";
type Leg = { kind: Kind; strike: number; side: Side; qty: number; entryPx: number };
type Spec = { kind: Kind; side: Side; qty: number; pct: number }; // pct = offset from spot
type Strat = {
  id: string;
  name: string;
  tag: string;
  glyph: string; // mini payoff path, viewBox 0 0 40 24
  uses: ("off" | "wing")[];
  build: (off: number, wing: number) => Spec[];
};

// offset/wing arrive as fractions (0.02 = 2%)
const STRATEGIES: Strat[] = [
  { id: "condor", name: "איירון קונדור", tag: "טווח", glyph: "M2 18 L10 18 L16 7 L24 7 L30 18 L38 18", uses: ["off", "wing"],
    build: (o, w) => [
      { kind: "put", side: -1, qty: 1, pct: -o }, { kind: "put", side: 1, qty: 1, pct: -o - w },
      { kind: "call", side: -1, qty: 1, pct: o }, { kind: "call", side: 1, qty: 1, pct: o + w },
    ] },
  { id: "butterfly", name: "פרפר", tag: "מדויק", glyph: "M2 18 L17 18 L20 5 L23 18 L38 18", uses: ["wing"],
    build: (_o, w) => [
      { kind: "call", side: 1, qty: 1, pct: -w }, { kind: "call", side: -1, qty: 2, pct: 0 },
      { kind: "call", side: 1, qty: 1, pct: w },
    ] },
  { id: "bullput", name: "בול פוט", tag: "שורי", glyph: "M2 18 L12 18 L22 8 L38 8", uses: ["off", "wing"],
    build: (o, w) => [
      { kind: "put", side: -1, qty: 1, pct: -o }, { kind: "put", side: 1, qty: 1, pct: -o - w },
    ] },
  { id: "bearcall", name: "בר קול", tag: "דובי", glyph: "M2 8 L16 8 L26 18 L38 18", uses: ["off", "wing"],
    build: (o, w) => [
      { kind: "call", side: -1, qty: 1, pct: o }, { kind: "call", side: 1, qty: 1, pct: o + w },
    ] },
  { id: "straddle", name: "סטרדל", tag: "תנודתיות", glyph: "M2 5 L20 18 L38 5", uses: [],
    build: () => [{ kind: "call", side: 1, qty: 1, pct: 0 }, { kind: "put", side: 1, qty: 1, pct: 0 }] },
  { id: "strangle", name: "סטרנגל", tag: "תנודתיות", glyph: "M2 5 L14 16 L26 16 L38 5", uses: ["off"],
    build: (o) => [{ kind: "call", side: 1, qty: 1, pct: o }, { kind: "put", side: 1, qty: 1, pct: -o }] },
  { id: "call", name: "קול בודד", tag: "שורי", glyph: "M2 16 L18 16 L38 4", uses: [],
    build: () => [{ kind: "call", side: 1, qty: 1, pct: 0 }] },
  { id: "put", name: "פוט בודד", tag: "דובי", glyph: "M2 4 L22 16 L38 16", uses: [],
    build: () => [{ kind: "put", side: 1, qty: 1, pct: 0 }] },
];

const OFFSETS = [0.5, 1, 1.5, 2, 3, 5]; // מרחק קצר %
const WINGS = [0.5, 1, 1.5, 2, 3, 5]; // רוחב כנף %

const legKey = (k: Kind, strike: number) => `${k}-${strike}`;
const ils = (n: number) =>
  `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const fmt = (n: number, d = 2) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pctStr = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

/** P&L (₪) of the whole position if the index settles at `s`. */
function payoffAt(legs: Leg[], s: number): number {
  let total = 0;
  for (const l of legs) {
    const intrinsic =
      l.kind === "call" ? Math.max(s - l.strike, 0) * MULT : Math.max(l.strike - s, 0) * MULT;
    total += l.side * (intrinsic - l.entryPx) * l.qty;
  }
  return total;
}

export default function Simulator({ chains }: { chains: ExpiryChain[] }) {
  const [expIdx, setExpIdx] = useState(0);
  const [legMap, setLegMap] = useState<Record<string, Leg>>({});
  const [strat, setStrat] = useState<string | null>(null);
  const [off, setOff] = useState(2);
  const [wing, setWing] = useState(3);
  const [sending, setSending] = useState(false);
  const [dispatchMsg, setDispatchMsg] = useState<{ tone: "pos" | "neg"; text: string } | null>(null);

  const chain = chains[expIdx];
  const spot = chain?.spot ?? 0;
  const legs = useMemo(() => Object.values(legMap), [legMap]);

  // (re)build legs whenever the selected strategy or its % params change
  useEffect(() => {
    if (!strat || !chain) return;
    const def = STRATEGIES.find((s) => s.id === strat);
    if (!def) return;
    const specs = def.build(off / 100, wing / 100);
    const next: Record<string, Leg> = {};
    for (const sp of specs) {
      const target = spot * (1 + sp.pct);
      const r = chain.rows
        .filter((x) => (sp.kind === "call" ? x.callPx : x.putPx) > 0)
        .reduce<ChainRow | null>(
          (b, x) => (!b || Math.abs(x.strike - target) < Math.abs(b.strike - target) ? x : b),
          null,
        );
      if (!r) continue;
      const px = sp.kind === "call" ? r.callPx : r.putPx;
      const key = legKey(sp.kind, r.strike);
      next[key] = {
        kind: sp.kind, strike: r.strike, side: sp.side,
        qty: (next[key]?.qty ?? 0) + sp.qty, entryPx: px,
      };
    }
    setLegMap(next);
  }, [strat, off, wing, chain, spot]);

  if (!chain) {
    return (
      <div className="rounded-2xl border border-border bg-surface/70 p-10 text-center text-text2">
        אין נתוני שרשרת אופציות זמינים כרגע.
      </div>
    );
  }

  function setQty(key: string, q: number) {
    setStrat(null);
    setLegMap((m) => (m[key] ? { ...m, [key]: { ...m[key], qty: Math.max(1, q) } } : m));
  }
  function removeLeg(key: string) {
    setStrat(null);
    setLegMap((m) => {
      const next = { ...m };
      delete next[key];
      return next;
    });
  }
  const clearAll = () => { setStrat(null); setLegMap({}); };

  // ── analytics (commission shifts the whole P&L curve down) ─────────
  const fees = legs.reduce((a, l) => a + l.qty, 0) * COMMISSION;
  const lo = Math.min(spot * 0.85, ...legs.map((l) => l.strike)) * 0.99;
  const hi = Math.max(spot * 1.15, ...legs.map((l) => l.strike)) * 1.01;
  const N = 240;
  const samples = Array.from({ length: N + 1 }, (_, i) => {
    const s = lo + ((hi - lo) * i) / N;
    return { s, v: payoffAt(legs, s) - fees };
  });
  const maxProfit = legs.length ? Math.max(...samples.map((p) => p.v)) : 0;
  const maxLoss = legs.length ? Math.min(...samples.map((p) => p.v)) : 0;
  const risk = Math.abs(maxLoss);
  const roi = risk > 1 ? (maxProfit / risk) * 100 : null;
  const premium = legs.reduce((a, l) => a - l.side * l.entryPx * l.qty, 0);
  const netCredit = premium - fees;
  const breakevens: number[] = [];
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i];
    if ((a.v <= 0 && b.v > 0) || (a.v >= 0 && b.v < 0)) {
      const t = Math.abs(a.v) / (Math.abs(a.v) + Math.abs(b.v));
      breakevens.push(a.s + (b.s - a.s) * t);
    }
  }
  const selDef = STRATEGIES.find((s) => s.id === strat);
  const showOff = !selDef || selDef.uses.includes("off");
  const showWing = !selDef || selDef.uses.includes("wing");

  async function dispatch() {
    setDispatchMsg(null);
    setSending(true);
    const res = await dispatchToDemo({
      strategyName: selDef?.name ?? "מותאם אישית",
      expiryDate: chain.date,
      entryIndex: spot,
      netPremiumPts: netCredit / MULT,
      maxProfitIls: Math.round(maxProfit),
      maxRiskIls: Math.round(risk),
      legs: legs.map((l) => ({ kind: l.kind, strike: l.strike, side: l.side, qty: l.qty, entryPx: l.entryPx })),
    });
    setSending(false);
    setDispatchMsg(
      res.ok
        ? { tone: "pos", text: "✓ הסימולציה שוגרה לתיק הדמו" }
        : { tone: "neg", text: `שגיאה בשיגור: ${res.error}` },
    );
  }

  const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";

  return (
    <div className="space-y-5">
      {/* ── header: expiry tabs + spot ── */}
      <section className={`${card} flex flex-wrap items-center justify-between gap-4 p-5`}>
        <div className="flex flex-wrap items-center gap-2">
          {chains.map((c, i) => (
            <button
              key={c.date}
              onClick={() => setExpIdx(i)}
              className={`rounded-xl border px-3 py-2 text-sm transition ${
                i === expIdx
                  ? "border-accent/40 bg-accent/15 text-accent"
                  : "border-border bg-surface2 text-text2 hover:text-text1"
              }`}
            >
              <span className="font-medium tabular-nums">{c.date.slice(8)}/{c.date.slice(5, 7)}</span>
              <span className="mx-1 text-text3">·</span>
              <span className="text-xs">{c.dayName}</span>
              <span className="mx-1 text-text3">·</span>
              <span className="text-xs tabular-nums">{c.days} ימים</span>
            </button>
          ))}
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end gap-2 text-text2">
            <span className="text-sm">מדד TLV35</span>
            <span className="text-accent"><Trending /></span>
          </div>
          <div className="text-2xl font-bold tabular-nums text-text1">{fmt(spot)}</div>
        </div>
      </section>

      {/* ── strategy builder ── */}
      <section className={`${card} p-5`}>
        <div className="mb-3 flex items-center justify-between">
          <button
            onClick={clearAll}
            className="flex items-center gap-1.5 rounded-xl border border-border bg-surface2 px-3 py-1.5 text-xs text-text2 hover:text-text1"
          >
            <Refresh /> נקה
          </button>
          <h2 className="text-lg font-bold text-text1">בנה אסטרטגיה</h2>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {STRATEGIES.map((s) => {
            const active = strat === s.id;
            return (
              <button
                key={s.id}
                onClick={() => setStrat(s.id)}
                className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 text-right transition ${
                  active
                    ? "border-accent/40 bg-accent/15"
                    : "border-border bg-surface2 hover:border-text3/40"
                }`}
              >
                <svg viewBox="0 0 40 24" className={`h-6 w-10 shrink-0 ${active ? "text-accent" : "text-text3"}`}>
                  <path d={s.glyph} fill="none" stroke="currentColor" strokeWidth="2"
                        strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="min-w-0">
                  <span className={`block truncate text-sm font-medium ${active ? "text-accent" : "text-text1"}`}>
                    {s.name}
                  </span>
                  <span className="block text-[11px] text-text3">{s.tag}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* percentage spread controls — only the ones this strategy uses */}
        {(showOff || showWing) && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {showOff && <PctRow label="מרחק קצר" values={OFFSETS} value={off} onPick={setOff} />}
            {showWing && <PctRow label="רוחב כנף" values={WINGS} value={wing} onPick={setWing} />}
          </div>
        )}
        {selDef && !showOff && !showWing && (
          <div className="mt-4 text-center text-xs text-text3">אסטרטגיה בכסף (ATM) — ללא מרווחים</div>
        )}
      </section>

      {/* ── payoff + metrics ── */}
      <section className={`${card} p-6`}>
        <div className="mb-4 flex items-center justify-between">
          <span className="text-xs text-text3">
            כל נקודה = ₪50{legs.length ? ` · ${legs.length} רגליים` : ""}
          </span>
          <h2 className="text-lg font-bold text-text1">גרף רווח/הפסד</h2>
        </div>
        <PayoffChart
          samples={samples}
          spot={spot}
          strikes={legs.map((l) => l.strike)}
          breakevens={breakevens}
          maxProfit={maxProfit}
          maxLoss={maxLoss}
        />
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Metric label="רווח מקסימלי" value={ils(maxProfit)}
          sub={risk > 1 ? `${((maxProfit / spot / MULT) * 100).toFixed(2)}% מהמדד` : undefined} tone="pos" />
        <Metric label="הפסד מקסימלי" value={ils(maxLoss)} tone="neg" />
        <Metric label="תשואה על סיכון" value={roi == null ? "—" : `${roi.toFixed(0)}%`} tone="accent" />
        <Metric label={netCredit >= 0 ? "זיכוי נטו" : "חיוב נטו"} value={ils(netCredit)}
          tone={netCredit >= 0 ? "pos" : "neg"} />
      </section>

      {/* ── selected positions (centered table) ── */}
      {legs.length > 0 && (
        <section className={`${card} w-full p-6`}>
          <div className="mb-1 text-center text-lg font-bold text-text1">
            פוזיציות נבחרות <span className="text-text3">({legs.length})</span>
          </div>
          <div className="mb-4 text-center text-xs text-text3">כל נקודה = ₪50 · כולל עמלה קבועה ₪2.5 לחוזה</div>

          <div className="overflow-x-auto">
            <table className="w-full text-center text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] text-text3">
                  <th className="px-3 py-3 font-medium">פעולה</th>
                  <th className="px-3 py-3 font-medium">סוג</th>
                  <th className="px-3 py-3 font-medium">מימוש</th>
                  <th className="px-3 py-3 font-medium">כמות</th>
                  <th className="px-3 py-3 font-medium">מחיר כניסה</th>
                  <th className="px-3 py-3 font-medium">עמלה</th>
                  <th className="px-3 py-3 font-medium">עלות</th>
                  <th className="px-3 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {legs.map((l) => {
                  const key = legKey(l.kind, l.strike);
                  const buy = l.side === 1;
                  const commission = COMMISSION * l.qty;
                  const cost = -l.side * l.entryPx * l.qty - commission; // +זיכוי / -חיוב, נטו מעמלה
                  return (
                    <tr key={key} className="border-b border-border/50">
                      <td className="px-3 py-3">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${buy ? "bg-pos/15 text-pos" : "bg-neg/15 text-neg"}`}>
                          {buy ? "קנייה" : "מכירה"}
                        </span>
                      </td>
                      <td className={`px-3 py-3 font-medium uppercase ${l.kind === "call" ? "text-accent" : "text-warn"}`}>{l.kind}</td>
                      <td className="px-3 py-3 tabular-nums text-text1">{fmt(l.strike, 0)}</td>
                      <td className="px-3 py-3">
                        <div className="flex items-center justify-center gap-1.5">
                          <button onClick={() => setQty(key, l.qty - 1)}
                            className="grid h-5 w-5 place-items-center rounded bg-surface2 text-text2 hover:text-text1">−</button>
                          <span className="w-4 text-center tabular-nums text-text1">{l.qty}</span>
                          <button onClick={() => setQty(key, l.qty + 1)}
                            className="grid h-5 w-5 place-items-center rounded bg-surface2 text-text2 hover:text-text1">+</button>
                        </div>
                      </td>
                      <td className="px-3 py-3 tabular-nums text-text2">{fmt(l.entryPx, 0)}</td>
                      <td className="px-3 py-3 tabular-nums text-text3">₪{commission.toFixed(2)}</td>
                      <td className={`px-3 py-3 tabular-nums ${cost >= 0 ? "text-pos" : "text-neg"}`}>{ils(cost)}</td>
                      <td className="px-3 py-3">
                        <button onClick={() => removeLeg(key)} aria-label="הסר רגל"
                          className="grid h-5 w-5 place-items-center rounded text-text3 hover:bg-neg/15 hover:text-neg">×</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {breakevens.length > 0 && (
            <div className="mt-3 border-t border-border pt-3 text-center">
              <div className="text-[11px] text-text3">נקודות איזון</div>
              <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs font-medium text-text1">
                {breakevens.map((b, i) => (
                  <span key={i} className="tabular-nums">
                    {fmt(b, 0)} <span className="text-text3">({pctStr(((b - spot) / spot) * 100)})</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* dispatch bar */}
          <div className="mt-4 flex flex-col items-center gap-2 border-t border-border pt-4">
            <button
              onClick={dispatch}
              disabled={sending}
              className="rounded-xl bg-accent px-6 py-2 text-sm font-bold text-bg transition hover:opacity-90 disabled:opacity-50"
            >
              {sending ? "משגר…" : "שגר לדמו"}
            </button>
            {dispatchMsg && (
              <div className={`text-xs ${dispatchMsg.tone === "pos" ? "text-pos" : "text-neg"}`}>
                {dispatchMsg.text}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function PctRow({
  label, values, value, onPick,
}: { label: string; values: number[]; value: number; onPick: (v: number) => void }) {
  return (
    <div>
      <div className="mb-1.5 text-right text-xs text-text2">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <button
            key={v}
            onClick={() => onPick(v)}
            className={`min-w-[44px] flex-1 rounded-lg border py-1.5 text-sm tabular-nums transition ${
              value === v
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-border bg-surface2 text-text2 hover:text-text1"
            }`}
          >
            {v}%
          </button>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: string }) {
  const TONE: Record<string, string> = { pos: "text-pos", neg: "text-neg", accent: "text-accent", warn: "text-warn" };
  return (
    <div className="rounded-2xl border border-border bg-surface/70 p-4 text-right backdrop-blur">
      <div className="mb-1 text-xs text-text2">{label}</div>
      <div className={`text-xl font-bold tabular-nums ${TONE[tone]}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-text3">{sub}</div>}
    </div>
  );
}

function PayoffChart({
  samples, spot, strikes, breakevens, maxProfit, maxLoss,
}: {
  samples: { s: number; v: number }[];
  spot: number; strikes: number[]; breakevens: number[];
  maxProfit: number; maxLoss: number;
}) {
  const W = 1000, H = 320, padX = 8, padTop = 22, padBot = 32;
  const xs = samples.map((p) => p.s);
  const vs = samples.map((p) => p.v);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  let vMin = Math.min(...vs, 0), vMax = Math.max(...vs, 0);
  const pad = (vMax - vMin) * 0.12 || 1;
  vMin -= pad; vMax += pad;
  const x = (s: number) => padX + ((s - xMin) / (xMax - xMin || 1)) * (W - 2 * padX);
  const y = (v: number) => padTop + (1 - (v - vMin) / (vMax - vMin || 1)) * (H - padTop - padBot);
  const y0 = y(0);

  const [hover, setHover] = useState<{ s: number; v: number } | null>(null);
  const vAt = (sx: number) => {
    const n = samples.length;
    const t = (sx - samples[0].s) / (samples[n - 1].s - samples[0].s || 1);
    const idx = Math.max(0, Math.min(n - 1, t * (n - 1)));
    const i0 = Math.floor(idx), i1 = Math.min(n - 1, i0 + 1), f = idx - i0;
    return samples[i0].v * (1 - f) + samples[i1].v * f;
  };

  const line = samples.map((p, i) => `${i ? "L" : "M"} ${x(p.s)} ${y(p.v)}`).join(" ");
  const area = `${line} L ${x(samples.at(-1)!.s)} ${y0} L ${x(samples[0].s)} ${y0} Z`;
  const hasPos = maxProfit > 0, hasNeg = maxLoss < 0;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-72 w-full cursor-crosshair"
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const px = ((e.clientX - rect.left) / rect.width) * W;
        const sx = Math.max(xMin, Math.min(xMax, xMin + ((px - padX) / (W - 2 * padX)) * (xMax - xMin)));
        setHover({ s: sx, v: vAt(sx) });
      }}
      onMouseLeave={() => setHover(null)}>
      <defs>
        <clipPath id="above"><rect x="0" y="0" width={W} height={y0} /></clipPath>
        <clipPath id="below"><rect x="0" y={y0} width={W} height={H - y0} /></clipPath>
      </defs>

      <path d={area} fill="var(--color-pos)" opacity="0.16" clipPath="url(#above)" />
      <path d={area} fill="var(--color-neg)" opacity="0.16" clipPath="url(#below)" />

      {/* max-profit / max-loss guide lines */}
      {hasPos && (
        <>
          <line x1={padX} x2={W - padX} y1={y(maxProfit)} y2={y(maxProfit)} stroke="var(--color-pos)" strokeWidth="1" strokeDasharray="2 5" opacity="0.5" />
          <text x={W - padX} y={y(maxProfit) - 5} textAnchor="end" fill="var(--color-pos)" fontSize="11">{ils(maxProfit)}</text>
        </>
      )}
      {hasNeg && (
        <>
          <line x1={padX} x2={W - padX} y1={y(maxLoss)} y2={y(maxLoss)} stroke="var(--color-neg)" strokeWidth="1" strokeDasharray="2 5" opacity="0.5" />
          <text x={W - padX} y={y(maxLoss) + 14} textAnchor="end" fill="var(--color-neg)" fontSize="11">{ils(maxLoss)}</text>
        </>
      )}

      {/* zero baseline */}
      <line x1={padX} x2={W - padX} y1={y0} y2={y0} stroke="rgba(255,255,255,.25)" strokeDasharray="4 4" />

      {/* strike gridlines */}
      {strikes.map((k, i) => (
        <line key={i} x1={x(k)} x2={x(k)} y1={padTop} y2={H - padBot} stroke="rgba(255,255,255,.07)" />
      ))}

      {/* P&L line (green above 0, red below) */}
      <path d={line} fill="none" stroke="var(--color-pos)" strokeWidth="2.5" clipPath="url(#above)" strokeLinejoin="round" />
      <path d={line} fill="none" stroke="var(--color-neg)" strokeWidth="2.5" clipPath="url(#below)" strokeLinejoin="round" />

      {/* breakevens */}
      {breakevens.map((b, i) => (
        <g key={i}>
          <circle cx={x(b)} cy={y0} r="4" fill="var(--color-bg)" stroke="var(--color-text2)" strokeWidth="2" />
          <text x={x(b)} y={H - 12} textAnchor="middle" fill="var(--color-text3)" fontSize="11">
            {b.toLocaleString("en-US", { maximumFractionDigits: 0 })}
          </text>
        </g>
      ))}

      {/* current spot */}
      <line x1={x(spot)} x2={x(spot)} y1={padTop} y2={H - padBot} stroke="var(--color-accent)" strokeWidth="1.5" strokeDasharray="5 4" />
      <text x={x(spot)} y={padTop - 7} textAnchor="middle" fill="var(--color-accent)" fontSize="12" fontWeight="700">
        {spot.toLocaleString("en-US", { maximumFractionDigits: 0 })}
      </text>

      {/* hover P&L readout */}
      {hover && (
        <g>
          <line x1={x(hover.s)} x2={x(hover.s)} y1={padTop} y2={H - padBot}
            stroke="var(--color-text2)" strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />
          <circle cx={x(hover.s)} cy={y(hover.v)} r="4.5" fill="var(--color-text1)" stroke="var(--color-bg)" strokeWidth="1.5" />
          <rect x={Math.max(70, Math.min(W - 70, x(hover.s))) - 62} y={padTop - 2} width="124" height="34" rx="6"
            fill="var(--color-surface2)" stroke="var(--color-border)" />
          <text x={Math.max(70, Math.min(W - 70, x(hover.s)))} y={padTop + 10} textAnchor="middle" fontSize="11" fill="var(--color-text2)">
            מדד {Math.round(hover.s).toLocaleString("en-US")}
          </text>
          <text x={Math.max(70, Math.min(W - 70, x(hover.s)))} y={padTop + 24} textAnchor="middle" fontSize="12" fontWeight="700"
            fill={hover.v >= 0 ? "var(--color-pos)" : "var(--color-neg)"}>
            {ils(hover.v)}
          </text>
        </g>
      )}
    </svg>
  );
}
