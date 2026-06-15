import { getIndexData, getKpis, WATCHLIST, type Kpi } from "@/lib/data";
import IndexChart from "@/components/IndexChart";
import { Trending, ArrowLeft, Star, Refresh, Wallet, Target, Shield } from "@/components/icons";

const TONE: Record<Kpi["tone"], string> = {
  pos: "text-pos", neg: "text-neg", accent: "text-accent", warn: "text-warn",
};
const KPI_ICONS = [Wallet, Trending, Target, Shield];

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";

export default async function Home() {
  const [idx, kpis] = await Promise.all([getIndexData(), getKpis()]);
  const up = idx.changePct >= 0;

  return (
    <div className="space-y-5">
      {/* KPI row */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k, i) => {
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
      </section>

      {/* TLV35 index hero */}
      <section className={`${card} p-6`}>
        <div className="flex items-start justify-between">
          <button className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3 py-2 text-sm text-text2 hover:text-text1">
            <ArrowLeft /> צפה בנתונים
          </button>
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

      {/* Watchlist */}
      <section className={`${card} p-6`}>
        <div className="mb-4 flex items-center justify-between">
          <button className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3 py-2 text-sm text-text2 hover:text-text1">
            <Refresh /> רענן עכשיו
          </button>
          <div className="flex items-center justify-end gap-2">
            <h2 className="text-xl font-bold text-text1">מניות במעקב</h2>
            <span className="text-warn text-lg"><Star /></span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {WATCHLIST.map((q) => {
            const u = q.pct >= 0;
            return (
              <div key={q.sym} className="rounded-xl border border-border bg-surface2/60 p-3 text-right">
                <div className="text-sm font-semibold text-text1">{q.sym}</div>
                <div className="mt-1 text-sm tabular-nums text-text2">{q.price}</div>
                <div className={`mt-0.5 text-xs tabular-nums ${u ? "text-pos" : "text-neg"}`}>
                  {u ? "▲" : "▼"} {Math.abs(q.pct).toFixed(2)}%
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
