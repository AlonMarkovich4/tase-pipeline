"use client";

import { useState } from "react";
import type { MarketEvent } from "@/lib/data";

const CAT_TONE: Record<string, string> = {
  משבר: "bg-neg/15 text-neg",
  מלחמה: "bg-neg/15 text-neg",
  מגפה: "bg-warn/15 text-warn",
  ריבית: "bg-accent/15 text-accent",
  פוליטי: "bg-warn/15 text-warn",
};
const fmtDate = (iso: string) => {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
};

export default function MarketEvents({ events }: { events: MarketEvent[] }) {
  const [cat, setCat] = useState("all");
  const cats = [...new Set(events.map((e) => e.category))];
  const filtered = cat === "all" ? events : events.filter((e) => e.category === cat);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="ml-1 text-xs text-text3">קטגוריה:</span>
        {[{ v: "all", l: "הכל" }, ...cats.map((c) => ({ v: c, l: c }))].map((o) => (
          <button key={o.v} onClick={() => setCat(o.v)}
            className={`rounded-lg border px-3 py-1.5 text-xs transition ${
              cat === o.v
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-border bg-surface2 text-text2 hover:text-text1"
            }`}>
            {o.l}
          </button>
        ))}
      </div>

      <ol className="relative space-y-4 border-r border-border pr-4">
        {filtered.map((e, i) => (
          <li key={i} className="relative">
            <span className="absolute -right-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-accent ring-4 ring-bg" />
            <div className="flex items-start justify-between gap-3">
              <span className="shrink-0 text-xs tabular-nums text-text3">{fmtDate(e.date)}</span>
              <div className="min-w-0 flex-1 text-right">
                <div className="flex items-center justify-end gap-2">
                  <h4 className="font-bold text-text1">{e.name}</h4>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${CAT_TONE[e.category] ?? "bg-surface text-text2"}`}>
                    {e.category}
                  </span>
                </div>
                {e.description && <p className="mt-0.5 text-xs leading-relaxed text-text2">{e.description}</p>}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
