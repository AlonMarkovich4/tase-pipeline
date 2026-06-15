"use client";

import { useState } from "react";
import type { ExpiryEntry } from "@/lib/data";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number) => `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const DAYS_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const MONTHS_HE = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יוני", "יולי", "אוג", "ספט", "אוק", "נוב", "דצמ"];
const weekday = (iso: string) => (iso ? DAYS_HE[new Date(`${iso}T00:00:00`).getDay()] ?? "" : "");
const fmtDM = (iso: string) => `${iso.slice(8)}/${iso.slice(5, 7)}`;

export default function CalendarView({ entries }: { entries: ExpiryEntry[] }) {
  const [stratFilter, setStratFilter] = useState("all");
  const [weekFilter, setWeekFilter] = useState("all");

  const allStrategies = [...new Set(entries.flatMap((e) => e.strategyTypes))];
  const filtered = entries.filter(
    (e) =>
      (weekFilter === "all" || e.date === weekFilter) &&
      (stratFilter === "all" || e.strategyTypes.includes(stratFilter)),
  );
  const upcoming = filtered.filter((e) => e.daysTo >= 0);
  const past = filtered.filter((e) => e.daysTo < 0).reverse();

  return (
    <div className="space-y-5">
      <div className={`${card} flex flex-col gap-3 p-4`}>
        <FilterRow label="אסטרטגיה" value={stratFilter} onPick={setStratFilter}
          options={[{ v: "all", l: "הכל" }, ...allStrategies.map((s) => ({ v: s, l: s }))]} />
        <FilterRow label="שבוע" value={weekFilter} onPick={setWeekFilter}
          options={[{ v: "all", l: "הכל" }, ...entries.map((e) => ({ v: e.date, l: fmtDM(e.date) }))]} />
      </div>

      {filtered.length === 0 ? (
        <div className={`${card} p-10 text-center text-sm text-text3`}>אין פקיעות התואמות לסינון</div>
      ) : (
        <>
          {upcoming.length > 0 && <CalSection title="פקיעות קרובות" entries={upcoming} />}
          {past.length > 0 && <CalSection title="פקיעות שעברו" entries={past} />}
        </>
      )}
    </div>
  );
}

function CalSection({ title, entries }: { title: string; entries: ExpiryEntry[] }) {
  return (
    <section className={`${card} p-5`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-text3">{entries.length}</span>
        <h2 className="text-lg font-bold text-text1">{title}</h2>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {entries.map((e) => <DayCard key={e.date} e={e} />)}
      </div>
    </section>
  );
}

function DayCard({ e }: { e: ExpiryEntry }) {
  const [y, m, d] = e.date.split("-");
  const today = e.daysTo === 0;
  const upcoming = e.daysTo > 0;
  return (
    <div className={`flex items-center gap-4 rounded-xl border p-4 ${today ? "border-accent/40 bg-accent/5" : "border-border bg-surface2/40"}`}>
      <div className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-surface text-center">
        <div className="text-lg font-bold leading-none tabular-nums text-text1">{d}</div>
        <div className="text-[10px] text-text3">{MONTHS_HE[+m - 1]}</div>
      </div>

      <div className="min-w-0 flex-1 text-right">
        <div className="flex items-center justify-end gap-2">
          <h3 className="font-bold text-text1">יום {weekday(e.date)}</h3>
          {e.live && <span className="rounded-full bg-pos/15 px-2 py-0.5 text-[10px] font-bold text-pos">נסחר</span>}
        </div>
        <div className="text-xs text-text3 tabular-nums">{d}/{m}/{y}</div>
        <div className="mt-1.5 flex flex-wrap justify-end gap-1.5 text-[11px]">
          {e.strategies > 0 && <Chip>{e.strategies} אסטרטגיות</Chip>}
          {e.demoOpen > 0 && <Chip tone="accent">{e.demoOpen} דמו פתוח</Chip>}
          {e.demoClosed > 0 && <Chip>{e.demoClosed} דמו סגור</Chip>}
          {e.pnl != null && (
            <span className={`font-bold tabular-nums ${e.pnl >= 0 ? "text-pos" : "text-neg"}`}>{ils(e.pnl)}</span>
          )}
        </div>
      </div>

      <div className="shrink-0 text-center">
        {today ? (
          <span className="rounded-full bg-accent/15 px-2.5 py-1 text-xs font-bold text-accent">היום</span>
        ) : upcoming ? (
          <div>
            <div className="text-xl font-bold tabular-nums text-accent">{e.daysTo}</div>
            <div className="text-[10px] text-text3">ימים</div>
          </div>
        ) : (
          <span className="text-xs text-text3">עברה</span>
        )}
      </div>
    </div>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span className={`rounded-md px-1.5 py-0.5 ${tone === "accent" ? "bg-accent/15 text-accent" : "bg-surface text-text2"}`}>
      {children}
    </span>
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
