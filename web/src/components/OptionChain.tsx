"use client";

import { useState } from "react";
import type { ExpiryChain } from "@/lib/data";
import { ChevronDown } from "@/components/icons";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const fmt = (n: number) => n.toLocaleString("en-US");

/** Read-only near-the-money option chain with depth bars + expiry paging — home page visual. */
export default function OptionChain({ chains }: { chains: ExpiryChain[] }) {
  const [idx, setIdx] = useState(0);
  if (!chains.length) return null;

  const chain = chains[Math.min(idx, chains.length - 1)];
  const { spot, rows } = chain;
  if (rows.length === 0) return null;

  const atm = rows.reduce((b, r) => (Math.abs(r.strike - spot) < Math.abs(b - spot) ? r.strike : b), rows[0].strike);
  const atmIdx = rows.findIndex((r) => r.strike === atm);
  const near = rows.slice(Math.max(0, atmIdx - 7), atmIdx + 8); // ~15 rows centered on ATM
  const maxPx = Math.max(1, ...near.flatMap((r) => [r.callPx, r.putPx]));
  const cols = "grid grid-cols-[1fr_5rem_1fr] items-center gap-2";

  const navBtn = "grid h-7 w-7 place-items-center rounded-lg border border-border bg-surface2 text-text2 transition enabled:hover:text-text1 disabled:opacity-30";

  return (
    <section className={`${card} overflow-hidden`}>
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        {/* expiry pager */}
        <div className="flex items-center gap-2">
          <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx === 0} className={navBtn} aria-label="פקיעה קודמת">
            <span className="inline-block -rotate-90"><ChevronDown /></span>
          </button>
          <span className="rounded-lg bg-surface2 px-2.5 py-1 text-xs text-text2">
            פקיעה <span className="font-medium text-text1">{chain.date.slice(8)}/{chain.date.slice(5, 7)}</span> · {chain.days} ימים
            <span className="ml-1 text-text3"> ({idx + 1}/{chains.length})</span>
          </span>
          <button onClick={() => setIdx((i) => Math.min(chains.length - 1, i + 1))} disabled={idx >= chains.length - 1} className={navBtn} aria-label="פקיעה הבאה">
            <span className="inline-block rotate-90"><ChevronDown /></span>
          </button>
        </div>
        <h2 className="text-lg font-bold text-text1">שרשרת אופציות</h2>
      </div>

      <div className={`${cols} px-5 pb-1 pt-3 text-[11px] font-medium uppercase`}>
        <span className="text-center text-pos/80">CALL</span>
        <span className="text-center text-text3">מימוש</span>
        <span className="text-center text-neg/80">PUT</span>
      </div>

      <div className="space-y-0.5 px-2 pb-3">
        {near.map((r) => {
          const isAtm = r.strike === atm;
          const callItm = r.strike < spot;
          const putItm = r.strike > spot;
          const callW = r.callPx ? Math.max(5, (r.callPx / maxPx) * 100) : 0;
          const putW = r.putPx ? Math.max(5, (r.putPx / maxPx) * 100) : 0;
          return (
            <div
              key={r.strike}
              className={`${cols} rounded-lg px-3 py-1 transition ${
                isAtm ? "bg-accent/10 ring-1 ring-inset ring-accent/25" : "hover:bg-surface2/40"
              }`}
            >
              <div className="relative flex h-7 items-center justify-end overflow-hidden rounded-md">
                <div className="absolute inset-y-0 left-0 rounded-md bg-gradient-to-r from-pos/5 to-pos/30" style={{ width: `${callW}%` }} />
                <span className={`relative px-2 text-sm tabular-nums ${callItm ? "font-semibold text-pos" : "text-text2"}`}>
                  {r.callPx ? fmt(r.callPx) : "—"}
                </span>
              </div>

              <span className={`text-center text-sm tabular-nums ${isAtm ? "font-bold text-accent" : "font-medium text-text1"}`}>
                {fmt(r.strike)}
              </span>

              <div className="relative flex h-7 items-center justify-start overflow-hidden rounded-md">
                <div className="absolute inset-y-0 right-0 rounded-md bg-gradient-to-l from-neg/5 to-neg/30" style={{ width: `${putW}%` }} />
                <span className={`relative px-2 text-sm tabular-nums ${putItm ? "font-semibold text-neg" : "text-text2"}`}>
                  {r.putPx ? fmt(r.putPx) : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="border-t border-border px-5 py-2.5 text-center text-[11px] text-text3">
        סביב הכסף · מדד <span className="font-medium tabular-nums text-text2">{fmt(Math.round(spot))}</span>
      </div>
    </section>
  );
}
