"use client";

import { useState } from "react";
import type { BestCondor } from "@/lib/data";
import { ChevronDown } from "@/components/icons";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) =>
  n == null ? "—" : `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const DAYS_HE: Record<string, string> = {
  Sunday: "ראשון", Monday: "שני", Tuesday: "שלישי", Wednesday: "רביעי",
  Thursday: "חמישי", Friday: "שישי", Saturday: "שבת",
};
const dm = (iso: string) => (iso.length >= 10 ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso);

export default function BestCondorPager({ items }: { items: BestCondor[] }) {
  const [idx, setIdx] = useState(0);
  if (!items.length) return null;
  const e = items[Math.min(idx, items.length - 1)];
  const pos = e.pnl >= 0;
  const navBtn =
    "grid h-7 w-7 place-items-center rounded-lg border border-border bg-surface2 text-text2 transition enabled:hover:text-text1 disabled:opacity-30";

  return (
    <section className={`${card} p-6`}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx === 0} className={navBtn} aria-label="פקיעה חדשה יותר">
            <span className="inline-block -rotate-90"><ChevronDown /></span>
          </button>
          <span className="rounded-lg bg-surface2 px-2.5 py-1 text-xs text-text2">
            פקיעה <span className="font-medium text-text1">{dm(e.expiryDate)}</span> · יום {DAYS_HE[e.dayName] ?? e.dayName}
            <span className="ml-1 text-text3"> ({idx + 1}/{items.length})</span>
          </span>
          <button onClick={() => setIdx((i) => Math.min(items.length - 1, i + 1))} disabled={idx >= items.length - 1} className={navBtn} aria-label="פקיעה ישנה יותר">
            <span className="inline-block rotate-90"><ChevronDown /></span>
          </button>
        </div>
        <h2 className="text-lg font-bold text-text1">פוטנציאל פר פקיעה</h2>
      </div>

      <div className="mb-4 text-right text-xs text-text3">
        המרווח הטוב ביותר: <span className="font-bold text-accent">{e.interval.toFixed(1)}%</span>
        {e.close != null && <> · סגירה <span className="tabular-nums text-text2">{e.close.toLocaleString("en-US")}</span></>}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="פוטנציאל (₪)" value={ils(e.pnl)} tone={pos ? "text-pos" : "text-neg"} />
        <Stat label="יחס סיכון/רווח" value={e.rr == null ? "—" : e.rr.toFixed(2)} tone="text-text1" />
        <Stat label="מקס׳ סיכון" value={ils(e.maxRisk)} tone="text-neg" />
      </div>
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface2/40 p-4 text-center">
      <div className="mb-1 text-[11px] text-text3">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}
