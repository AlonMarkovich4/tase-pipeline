import { getIndexData, getKpis, getLastUpdate, getVta35, getSimulatorData, type Kpi } from "@/lib/data";
import Link from "next/link";
import IndexChart from "@/components/IndexChart";
import OptionChain from "@/components/OptionChain";
import { Trending, ArrowLeft, Wallet, Target, Shield, BarChart } from "@/components/icons";

const TONE: Record<Kpi["tone"], string> = {
  pos: "text-pos", neg: "text-neg", accent: "text-accent", warn: "text-warn",
};
const KPI_ICONS = [Wallet, Trending, Target, Shield];

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";

export default async function Home() {
  const [idx, kpis, fresh, vta, chains] = await Promise.all([
    getIndexData(), getKpis(), getLastUpdate(), getVta35(), getSimulatorData(),
  ]);
  const up = idx.changePct >= 0;
  const DOT = { pos: "bg-pos", warn: "bg-warn", neg: "bg-neg" } as const;
  const ago =
    fresh.agoMin == null ? "אין נתונים"
      : fresh.agoMin < 60 ? `לפני ${fresh.agoMin} דק׳`
      : `לפני ${Math.floor(fresh.agoMin / 60)}ש׳ ${fresh.agoMin % 60}ד׳`;

  return (
    <div className="space-y-5">
      {/* last-updated freshness */}
      <div className="flex justify-end">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1.5 text-xs text-text2">
          <span className={`h-2 w-2 rounded-full ${DOT[fresh.tone]}`} />
          עודכן לאחרונה: <span className="font-medium text-text1">{fresh.label}</span> · {ago}
        </span>
      </div>

      {/* KPI row — 3 live KPIs + VTA35 (replaces the static subscription card) */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.slice(0, 3).map((k, i) => {
          const Icon = KPI_ICONS[i];
          return (
            <div key={k.label} className={`${card} flex items-center justify-between p-5`}>
              <div className="text-right">
                <div className="mb-1 text-xs text-text2">{k.label}</div>
                <div className="text-2xl font-bold tabular-nums text-text1">{k.value}</div>
                <div className={`mt-0.5 text-xs ${TONE[k.tone]}`}>{k.sub}</div>
              </div>
              <span className={`grid h-11 w-11 place-items-center rounded-xl bg-surface2 text-xl ${TONE[k.tone]}`}>
                <Icon />
              </span>
            </div>
          );
        })}

        {/* VTA35 volatility index */}
        <div className={`${card} flex items-center justify-between p-5`}>
          <div className="text-right">
            <div className="mb-1 text-xs text-text2">מדד תנודתיות (VTA35)</div>
            <div className={`text-2xl font-bold tabular-nums ${vta != null ? "text-warn" : "text-text3"}`}>
              {vta != null ? vta.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
            </div>
            <div className="mt-0.5 text-xs text-text3">{vta != null ? "מדד הפחד · ת\"א-35" : "לא זמין"}</div>
          </div>
          <span className={`grid h-11 w-11 place-items-center rounded-xl bg-surface2 text-xl ${vta != null ? "text-warn" : "text-text3"}`}>
            <BarChart />
          </span>
        </div>
      </section>

      {/* TLV35 index hero */}
      <section className={`${card} p-6`}>
        <div className="flex items-start justify-between">
          <Link href="/strategies" className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3 py-2 text-sm text-text2 hover:text-text1">
            <ArrowLeft /> צפה בנתונים
          </Link>
          <div className="text-right">
            <div className="flex items-center justify-end gap-2">
              <h2 className="text-2xl font-bold text-text1">מדד TLV35</h2>
              <span className="text-accent text-xl"><Trending /></span>
            </div>
            <div className="mt-1 flex items-center justify-end gap-3">
              <span className={`text-sm ${up ? "text-pos" : "text-neg"}`}>
                {up ? "▲" : "▼"} {Math.abs(idx.changePct).toFixed(2)}%
              </span>
              <span className="text-3xl font-bold tabular-nums text-text1">
                {idx.current.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
          </div>
        </div>
        <div className="mt-2 text-center text-xs text-text3">10 פקיעות אחרונות</div>
        <IndexChart series={idx.series} />
      </section>

      {/* live option chain (visual, pageable across expiries) */}
      <OptionChain chains={chains} />

    </div>
  );
}
