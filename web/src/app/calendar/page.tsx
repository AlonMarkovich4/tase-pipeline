import { getExpiryCalendar } from "@/lib/data";
import { Calendar, Target, Wallet } from "@/components/icons";
import CalendarView from "@/components/CalendarView";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";

export default async function CalendarPage() {
  const entries = await getExpiryCalendar();
  const upcoming = entries.filter((e) => e.daysTo >= 0);
  const next = upcoming[0];
  const liveCount = entries.filter((e) => e.live).length;
  const demoOpen = entries.reduce((a, e) => a + e.demoOpen, 0);
  const nextSub = next ? (next.daysTo === 0 ? "היום" : next.daysTo === 1 ? "מחר" : `בעוד ${next.daysTo} ימים`) : undefined;

  return (
    <div className="space-y-5">
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Kpi icon={<Calendar />} label="הפקיעה הקרובה"
          value={next ? `${next.date.slice(8)}/${next.date.slice(5, 7)}` : "—"} sub={nextSub} />
        <Kpi icon={<Target />} label="פקיעות נסחרות" value={`${liveCount}`} tone="text-accent" />
        <Kpi icon={<Wallet />} label="פוזיציות דמו פתוחות" value={`${demoOpen}`} tone="text-text1" />
      </section>

      <CalendarView entries={entries} />
    </div>
  );
}

function Kpi({ icon, label, value, tone = "text-text1", sub }: {
  icon: React.ReactNode; label: string; value: string; tone?: string; sub?: string;
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
