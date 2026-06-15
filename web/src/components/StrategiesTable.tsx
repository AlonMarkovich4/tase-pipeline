"use client";

import { useState } from "react";
import type { Strategy } from "@/lib/data";
import { ChevronDown } from "@/components/icons";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) =>
  n == null ? "—" : `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const fmtDate = (iso: string) => {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
};
const num = (n: number | null) => (n == null ? "—" : n.toLocaleString("en-US"));
const DAYS_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const weekday = (iso: string) => (iso ? DAYS_HE[new Date(`${iso}T00:00:00`).getDay()] ?? "" : "");

const RESULT: Record<string, { label: string; cls: string }> = {
  max_profit: { label: "רווח מלא", cls: "bg-pos/15 text-pos" },
  partial_loss_put: { label: "הפסד חלקי", cls: "bg-warn/15 text-warn" },
  partial_loss_call: { label: "הפסד חלקי", cls: "bg-warn/15 text-warn" },
  max_loss_put: { label: "הפסד מלא", cls: "bg-neg/15 text-neg" },
  max_loss_call: { label: "הפסד מלא", cls: "bg-neg/15 text-neg" },
};
const RESULT_FILTERS = [
  { v: "all", l: "הכל" },
  { v: "max_profit", l: "רווח מלא" },
  { v: "partial", l: "הפסד חלקי" },
  { v: "max_loss", l: "הפסד מלא" },
  { v: "open", l: "פעיל" },
];

export default function StrategiesTable({ strategies }: { strategies: Strategy[] }) {
  const [resultFilter, setResultFilter] = useState("all");
  // weeks with any unsettled strategy start expanded
  const [openSet, setOpenSet] = useState<Set<string>>(
    () => new Set(strategies.filter((s) => s.resultStatus == null).map((s) => s.expiryDate)),
  );
  const toggle = (e: string) =>
    setOpenSet((s) => {
      const n = new Set(s);
      if (n.has(e)) n.delete(e); else n.add(e);
      return n;
    });

  const matchResult = (s: Strategy) => {
    if (resultFilter === "all") return true;
    if (resultFilter === "open") return s.resultStatus == null;
    if (resultFilter === "partial") return !!s.resultStatus?.startsWith("partial");
    if (resultFilter === "max_loss") return !!s.resultStatus?.startsWith("max_loss");
    return s.resultStatus === resultFilter; // max_profit
  };
  const filtered = strategies.filter(matchResult);

  const byWeek = new Map<string, Strategy[]>();
  for (const s of filtered) {
    const arr = byWeek.get(s.expiryDate) ?? [];
    arr.push(s);
    byWeek.set(s.expiryDate, arr);
  }
  const weeks = [...byWeek.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  const filtersActive = resultFilter !== "all";

  return (
    <section className={`${card} p-5`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-text3">{filtered.length} מתוך {strategies.length}</span>
        <h2 className="text-lg font-bold text-text1">פירוט אסטרטגיות פר שבוע</h2>
      </div>

      <div className="mb-4">
        <FilterRow label="תוצאה" value={resultFilter} onPick={setResultFilter} options={RESULT_FILTERS} />
      </div>

      {weeks.length === 0 ? (
        <div className="py-8 text-center text-sm text-text3">אין אסטרטגיות התואמות לסינון</div>
      ) : (
        <div className="space-y-3">
          {weeks.map(([expiry, list]) => {
            const settled = list.filter((s) => s.actualPnl != null);
            const weekPnl = settled.reduce((a, s) => a + (s.actualPnl ?? 0), 0);
            const allOpen = settled.length === 0;
            const isOpen = filtersActive || openSet.has(expiry);
            return (
              <div key={expiry} className="overflow-hidden rounded-xl border border-border bg-surface2/30">
                <button
                  onClick={() => toggle(expiry)}
                  aria-expanded={isOpen}
                  className="flex w-full items-center justify-between gap-3 p-4 text-right transition hover:bg-surface2/50"
                >
                  <div className="flex items-center gap-3">
                    <div>
                      <h3 className="font-bold text-text1">פקיעה {fmtDate(expiry)}</h3>
                      <div className="text-xs text-text3">יום {weekday(expiry)} · {list.length} אסטרטגיות</div>
                    </div>
                    {allOpen ? (
                      <span className="rounded-full bg-accent/15 px-2.5 py-1 text-xs font-bold text-accent">פעיל</span>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        <span className="text-xs text-text3">תוצאת שבוע</span>
                        <span className={`tabular-nums font-bold ${weekPnl >= 0 ? "text-pos" : "text-neg"}`}>{ils(weekPnl)}</span>
                      </span>
                    )}
                  </div>
                  <span className={`text-text3 transition-transform ${isOpen ? "" : "-rotate-90"}`}>
                    <ChevronDown />
                  </span>
                </button>
                {isOpen && (
                  <div className="overflow-x-auto px-2 pb-2">
                    <table className="w-full text-center text-xs">
                      <thead>
                        <tr className="border-b border-border text-[11px] text-text3">
                          <th className="px-2 py-2 font-medium">מדד בסיס</th>
                          <th className="px-2 py-2 font-medium">טווח קצר</th>
                          <th className="px-2 py-2 font-medium">מרווח %</th>
                          <th className="px-2 py-2 font-medium">מקס׳ רווח</th>
                          <th className="px-2 py-2 font-medium">מקס׳ סיכון</th>
                          <th className="px-2 py-2 font-medium">R/R</th>
                          <th className="px-2 py-2 font-medium">תוצאה</th>
                          <th className="px-2 py-2 font-medium">P&amp;L בפועל</th>
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((s, i) => <Row key={i} s={s} />)}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Row({ s }: { s: Strategy }) {
  const res = s.resultStatus ? RESULT[s.resultStatus] : null;
  return (
    <tr className="border-b border-border/40">
      <td className="px-2 py-2 tabular-nums text-text2">{num(s.baseIndex)}</td>
      <td className="px-2 py-2 tabular-nums text-text2">{num(s.shortPut)}–{num(s.shortCall)}</td>
      <td className="px-2 py-2 tabular-nums text-text3">{s.intervalPct == null ? "—" : `${s.intervalPct}%`}</td>
      <td className="px-2 py-2 tabular-nums text-pos">{ils(s.maxProfit)}</td>
      <td className="px-2 py-2 tabular-nums text-neg">{ils(s.maxRisk)}</td>
      <td className="px-2 py-2 tabular-nums text-text2">{s.riskReward == null ? "—" : s.riskReward.toFixed(2)}</td>
      <td className="px-2 py-2">
        {res ? (
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${res.cls}`}>{res.label}</span>
        ) : (
          <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold text-accent">פעיל</span>
        )}
      </td>
      <td className={`px-2 py-2 tabular-nums font-medium ${(s.actualPnl ?? 0) >= 0 ? "text-pos" : "text-neg"}`}>
        {s.actualPnl == null ? "—" : ils(s.actualPnl)}
      </td>
    </tr>
  );
}

function FilterRow({ label, options, value, onPick }: {
  label: string; options: { v: string; l: string }[]; value: string; onPick: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="ml-1 text-xs text-text3">{label}:</span>
      {options.map((o) => (
        <button key={o.v} onClick={() => onPick(o.v)}
          className={`rounded-lg border px-3 py-1.5 text-xs transition ${
            value === o.v
              ? "border-accent/40 bg-accent/15 text-accent"
              : "border-border bg-surface2 text-text2 hover:text-text1"
          }`}>
          {o.l}
        </button>
      ))}
    </div>
  );
}
