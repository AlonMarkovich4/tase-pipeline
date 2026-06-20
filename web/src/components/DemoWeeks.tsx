"use client";

import { useState } from "react";
import type { DemoTrade } from "@/lib/data";
import { ChevronDown } from "@/components/icons";
import { STRATEGY_NAMES } from "@/lib/strategies";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) =>
  n == null ? "—" : `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const fmtDate = (iso: string) => {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
};
const DAYS_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const weekday = (iso: string) => (iso ? DAYS_HE[new Date(`${iso}T00:00:00`).getDay()] ?? "" : "");

export type Week = { expiry: string; trades: DemoTrade[] };

export default function DemoWeeks({ weeks }: { weeks: Week[] }) {
  // active (all-open) weeks start expanded; settled weeks start collapsed
  const [openSet, setOpenSet] = useState<Set<string>>(
    () => new Set(weeks.filter((w) => w.trades.every((t) => t.status !== "closed")).map((w) => w.expiry)),
  );
  const toggle = (e: string) =>
    setOpenSet((s) => {
      const n = new Set(s);
      if (n.has(e)) n.delete(e); else n.add(e);
      return n;
    });

  const [stratFilter, setStratFilter] = useState("all");
  const [weekFilter, setWeekFilter] = useState("all");

  // all canonical strategies + any extra actually present in the demo trades
  const allStrategies = [...new Set([...STRATEGY_NAMES, ...weeks.flatMap((w) => w.trades.map((t) => t.strategyName))])];
  const filtersActive = stratFilter !== "all" || weekFilter !== "all";
  const filtered = weeks
    .filter((w) => weekFilter === "all" || w.expiry === weekFilter)
    .map((w) => ({
      expiry: w.expiry,
      trades: w.trades.filter((t) => stratFilter === "all" || t.strategyName === stratFilter),
    }))
    .filter((w) => w.trades.length > 0);

  return (
    <div className="space-y-4">
      <div className={`${card} flex flex-col gap-3 p-4`}>
        <FilterRow label="אסטרטגיה" value={stratFilter} onPick={setStratFilter}
          options={[{ v: "all", l: "הכל" }, ...allStrategies.map((s) => ({ v: s, l: s }))]} />
        <FilterRow label="שבוע" value={weekFilter} onPick={setWeekFilter}
          options={[{ v: "all", l: "הכל" }, ...weeks.map((w) => ({ v: w.expiry, l: fmtDate(w.expiry) }))]} />
      </div>

      {filtered.length === 0 ? (
        <div className={`${card} p-10 text-center text-sm text-text3`}>אין פוזיציות התואמות לסינון</div>
      ) : filtered.map(({ expiry, trades }) => {
        const closed = trades.filter((t) => t.status === "closed");
        const weekPnl = closed.reduce((a, t) => a + (t.pnlIls ?? 0), 0);
        const allOpen = closed.length === 0;
        const isOpen = filtersActive || openSet.has(expiry);
        return (
          <section key={expiry} className={`${card} overflow-hidden`}>
            <button
              onClick={() => toggle(expiry)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-3 p-5 text-right transition hover:bg-surface2/30"
            >
              <div className="flex items-center gap-3">
                <div>
                  <h2 className="text-lg font-bold text-text1">פקיעה {fmtDate(expiry)}</h2>
                  <div className="text-xs text-text3">יום {weekday(expiry)} · {trades.length} פוזיציות</div>
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
              <div className="grid gap-3 p-5 pt-0 lg:grid-cols-2">
                {trades.map((t) => <TradeCard key={t.tradeId} t={t} />)}
              </div>
            )}
          </section>
        );
      })}
    </div>
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

function TradeCard({ t }: { t: DemoTrade }) {
  const open = t.status !== "closed";
  return (
    <div className="rounded-xl border border-border bg-surface2/40 p-4">
      <div className="flex items-start justify-between">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${open ? "bg-accent/15 text-accent" : "bg-surface text-text3"}`}>
          {open ? "פתוח" : "סגור"}
        </span>
        <div className="text-right">
          <div className="font-bold text-text1">{t.strategyName}</div>
          {t.closeReason && <div className="text-xs text-text3">{t.closeReason}</div>}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-1.5">
        {t.legs.map((l, i) => (
          <span key={i} className="rounded-md bg-surface px-2 py-1 text-[11px] tabular-nums">
            <span className={l.side === 1 ? "text-pos" : "text-neg"}>{l.side === 1 ? "+" : "−"}{l.qty}</span>{" "}
            <span className={l.kind === "call" ? "text-accent" : "text-warn"}>{l.kind.toUpperCase()}</span>{" "}
            <span className="text-text2">{l.strike.toLocaleString("en-US")}</span>
          </span>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-3 sm:grid-cols-4">
        <Stat label="מדד כניסה" value={t.entryIndex?.toLocaleString("en-US") ?? "—"} />
        <Stat label="פרמיה (נק׳)" value={t.netPremiumPts == null ? "—" : t.netPremiumPts.toFixed(1)} />
        <Stat label="רווח מקס׳" value={ils(t.maxProfitIls)} tone="text-pos" />
        <Stat label="סיכון מקס׳" value={ils(t.maxRiskIls)} tone="text-neg" />
        {!open && <Stat label="תוצאה" value={ils(t.pnlIls)} tone={(t.pnlIls ?? 0) >= 0 ? "text-pos" : "text-neg"} />}
        {!open && t.settlementIndex != null && (
          <Stat label="מדד סילוק" value={t.settlementIndex.toLocaleString("en-US")} />
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "text-text1" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="text-right">
      <div className="text-[10px] text-text3">{label}</div>
      <div className={`text-sm font-medium tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}
