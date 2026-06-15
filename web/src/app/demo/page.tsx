import { getDemoBook, type DemoTrade } from "@/lib/data";
import { Wallet, Trending, Target, Shield } from "@/components/icons";
import DemoWeeks, { type Week } from "@/components/DemoWeeks";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) =>
  n == null ? "—" : `${n < 0 ? "-" : ""}₪${Math.abs(Math.round(n)).toLocaleString("en-US")}`;

export default async function DemoPage() {
  const book = await getDemoBook();
  const closed = book.trades.filter((t) => t.status === "closed");
  const wins = closed.filter((t) => (t.pnlIls ?? 0) > 0);
  const losses = closed.filter((t) => (t.pnlIls ?? 0) < 0);
  const totalWon = wins.reduce((a, t) => a + (t.pnlIls ?? 0), 0);
  const totalLost = losses.reduce((a, t) => a + (t.pnlIls ?? 0), 0);
  const net = totalWon + totalLost;
  const winRate = closed.length ? Math.round((wins.length / closed.length) * 100) : 0;

  // group trades by expiry week (TASE weekly options → one expiry per week)
  const byWeek = new Map<string, DemoTrade[]>();
  for (const t of book.trades) {
    const arr = byWeek.get(t.expiryDate) ?? [];
    arr.push(t);
    byWeek.set(t.expiryDate, arr);
  }
  const weeks: Week[] = [...byWeek.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([expiry, trades]) => ({ expiry, trades }));

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={<Wallet />} label="יתרת דמו" value={ils(book.balance)} tone="text-text1" />
        <Kpi icon={<Trending />} label="רווח/הפסד מסולק" value={ils(net)}
          tone={net >= 0 ? "text-pos" : "text-neg"}
          sub={closed.length ? `${winRate}% הצלחה · ${closed.length} עסקאות` : undefined} />
        <Kpi icon={<Target />} label="ניצחנו" value={`${wins.length}`} tone="text-pos"
          sub={wins.length ? ils(totalWon) : undefined} subTone="text-pos" />
        <Kpi icon={<Shield />} label="הפסדנו" value={`${losses.length}`} tone="text-neg"
          sub={losses.length ? ils(totalLost) : undefined} subTone="text-neg" />
      </section>

      {weeks.length === 0 ? (
        <div className={`${card} p-12 text-center`}>
          <div className="text-text2">אין עדיין פוזיציות בתיק הדמו</div>
          <div className="mt-1 text-sm text-text3">בנה אסטרטגיה בסימולטור ולחץ &quot;שגר לדמו&quot;</div>
        </div>
      ) : (
        <DemoWeeks weeks={weeks} />
      )}
    </div>
  );
}

function Kpi({ icon, label, value, tone, sub, subTone }: {
  icon: React.ReactNode; label: string; value: string; tone: string; sub?: string; subTone?: string;
}) {
  return (
    <div className={`${card} flex items-center justify-between p-5`}>
      <div className="text-right">
        <div className="mb-1 text-xs text-text2">{label}</div>
        <div className={`text-2xl font-bold tabular-nums ${tone}`}>{value}</div>
        {sub && <div className={`mt-0.5 text-[11px] ${subTone ?? "text-text3"}`}>{sub}</div>}
      </div>
      <span className="grid h-11 w-11 place-items-center rounded-xl bg-surface2 text-xl text-accent">{icon}</span>
    </div>
  );
}
