import { getStrategiesData } from "@/lib/data";
import { File, Target, Trending, Shield } from "@/components/icons";
import StrategiesTable from "@/components/StrategiesTable";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) =>
  n == null ? "—" : `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;
const fmtDM = (iso: string) => (iso ? `${iso.slice(8)}/${iso.slice(5, 7)}` : "—");

export default async function StrategiesPage() {
  const d = await getStrategiesData();
  const rrs = d.strategies.map((s) => s.riskReward).filter((x): x is number => x != null && x > 0);
  const avgRR = rrs.length ? rrs.reduce((a, b) => a + b, 0) / rrs.length : null;

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={<File />} label="סך אסטרטגיות" value={`${d.strategies.length}`} tone="text-text1"
          sub={`${d.settled} סולקו`} />
        <Kpi icon={<Target />} label="אחוז הצלחה" value={`${d.winRate}%`} tone="text-accent"
          sub={`${d.wins} זכיות · ${d.losses} הפסדים`} />
        <Kpi icon={<Trending />} label="רווח/הפסד מצטבר" value={ils(d.totalPnl)}
          tone={d.totalPnl >= 0 ? "text-pos" : "text-neg"} sub="מעסקאות שסולקו" />
        <Kpi icon={<Shield />} label="יחס סיכון/סיכוי ממוצע" value={avgRR == null ? "—" : avgRR.toFixed(2)}
          tone="text-text1" />
      </section>

      {/* outcome distribution */}
      <section className={`${card} p-5`}>
        <h2 className="mb-3 text-right text-lg font-bold text-text1">התפלגות תוצאות</h2>
        <OutcomeBar outcomes={d.outcomes} />
      </section>

      {/* P&L per expiry */}
      {d.byExpiry.length > 0 && (
        <section className={`${card} p-6`}>
          <h2 className="mb-1 text-right text-lg font-bold text-text1">רווח/הפסד לפי פקיעה</h2>
          <div className="mb-4 text-right text-xs text-text3">{d.byExpiry.length} פקיעות שסולקו</div>
          <ExpiryPnlChart data={d.byExpiry} />
        </section>
      )}

      {/* strategies table with filters */}
      <StrategiesTable strategies={d.strategies} />
    </div>
  );
}

function Kpi({ icon, label, value, tone, sub }: {
  icon: React.ReactNode; label: string; value: string; tone: string; sub?: string;
}) {
  return (
    <div className={`${card} flex items-center justify-between p-5`}>
      <div className="text-right">
        <div className="mb-1 text-xs text-text2">{label}</div>
        <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
        {sub && <div className="mt-0.5 text-[11px] text-text3">{sub}</div>}
      </div>
      <span className="grid h-11 w-11 place-items-center rounded-xl bg-surface2 text-xl text-accent">{icon}</span>
    </div>
  );
}

function OutcomeBar({ outcomes }: { outcomes: { maxProfit: number; partialLoss: number; maxLoss: number } }) {
  const total = outcomes.maxProfit + outcomes.partialLoss + outcomes.maxLoss || 1;
  const segs = [
    { n: outcomes.maxProfit, color: "var(--color-pos)", label: "רווח מלא" },
    { n: outcomes.partialLoss, color: "var(--color-warn)", label: "הפסד חלקי" },
    { n: outcomes.maxLoss, color: "var(--color-neg)", label: "הפסד מלא" },
  ];
  return (
    <div>
      <div className="flex h-4 w-full overflow-hidden rounded-full bg-surface2">
        {segs.map((s, i) => s.n > 0 && (
          <div key={i} style={{ width: `${(s.n / total) * 100}%`, background: s.color }} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap justify-end gap-4 text-xs">
        {segs.map((s, i) => (
          <span key={i} className="flex items-center gap-1.5 text-text2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            {s.label} <span className="font-bold text-text1">{s.n}</span>
            <span className="text-text3">({Math.round((s.n / total) * 100)}%)</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ExpiryPnlChart({ data }: { data: { expiry: string; pnl: number; count: number }[] }) {
  const W = 1000, H = 240, padX = 36, padTop = 24, padBot = 36;
  const max = Math.max(1, ...data.map((d) => Math.abs(d.pnl)));
  const n = data.length;
  const slot = (W - 2 * padX) / n;
  const bw = Math.min(slot * 0.55, 54);
  const cx = (i: number) => padX + (i + 0.5) * slot;
  const zeroY = padTop + (H - padTop - padBot) / 2;
  const half = (H - padTop - padBot) / 2;
  const barY = (v: number) => (v >= 0 ? zeroY - (v / max) * half : zeroY);
  const barH = (v: number) => (Math.abs(v) / max) * half;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full">
      <line x1={padX} x2={W - padX} y1={zeroY} y2={zeroY} stroke="rgba(255,255,255,.18)" />
      {data.map((d, i) => {
        const pos = d.pnl >= 0;
        return (
          <g key={d.expiry}>
            <rect x={cx(i) - bw / 2} y={barY(d.pnl)} width={bw} height={Math.max(barH(d.pnl), 1)} rx="3"
              fill={pos ? "var(--color-pos)" : "var(--color-neg)"} opacity="0.85" />
            <text x={cx(i)} y={pos ? barY(d.pnl) - 5 : zeroY + barH(d.pnl) + 14} textAnchor="middle"
              fontSize="10" fill={pos ? "var(--color-pos)" : "var(--color-neg)"}>
              {ils(d.pnl)}
            </text>
            <text x={cx(i)} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--color-text3)">
              {fmtDM(d.expiry)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
