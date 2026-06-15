import { getSettings } from "@/lib/data";
import { Wallet, Target, Trending, Refresh } from "@/components/icons";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const ils = (n: number | null) => (n == null ? "—" : `₪${Math.round(n).toLocaleString("en-US")}`);
const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d ? `${d}/${m}/${y}` : iso;
};
const REASON_HE: Record<string, string> = { initial_balance: "יתרה התחלתית" };

export default async function SettingsPage() {
  const s = await getSettings();
  const ago =
    s.lastUpdate.agoMin == null ? "אין נתונים"
      : s.lastUpdate.agoMin < 60 ? `לפני ${s.lastUpdate.agoMin} דק׳`
      : `לפני ${Math.floor(s.lastUpdate.agoMin / 60)}ש׳ ${s.lastUpdate.agoMin % 60}ד׳`;
  const intervalsLabel = s.intervals.length
    ? `${s.intervals[0]}%–${s.intervals.at(-1)}% · ${s.intervals.length} רמות`
    : "—";

  return (
    <div className="space-y-5">
      <div className="text-right">
        <h1 className="text-2xl font-bold text-text1">הגדרות מערכת</h1>
        <p className="mt-1 text-sm text-text3">התצורה החיה שהפייפליין פועל לפיה (לקריאה בלבד)</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="חשבון דמו" icon={<Wallet />}>
          <Row label="יתרה נוכחית" value={ils(s.demoBalance)} />
          <Row label="מקור היתרה" value={s.demoReason ? REASON_HE[s.demoReason] ?? s.demoReason : "—"} desc="עדכון אחרון של היתרה" />
          <Row label="הוקם בתאריך" value={fmtDate(s.demoSince)} />
        </Section>

        <Section title="פרמטרי סריקת אסטרטגיה" icon={<Target />}>
          <Row label="מרווחים נסרקים" value={intervalsLabel} desc="מרחק הרגליים הקצרות מהמדד" />
          <Row label="רוחב כנף" value={s.wingWidth == null ? "—" : `${s.wingWidth} נק׳`} desc="מרחק הרגליים המגנות" />
          <Row label="ימים לפקיעה" value={s.daysMin == null ? "—" : `${s.daysMin}–${s.daysMax} ימים`} />
          <Row label="תקרת סיכון לפוזיציה" value={ils(s.maxRisk)} />
        </Section>

        <Section title="מסחר" icon={<Trending />}>
          <Row label="ערך נקודה" value="₪50" desc="לכל נקודת מדד, לחוזה" />
          <Row label="עמלה לחוזה" value="₪2.5" desc="עמלה קבועה" />
          <Row label="נכס בסיס" value="TA-35 (TLV35)" />
          <Row label="סוג אסטרטגיה" value="איירון קונדור" />
        </Section>

        <Section title="נתונים והתראות" icon={<Refresh />}>
          <Row label="מקור נתונים" value="TASE API" desc="api.tase.co.il" />
          <Row label="עדכון אחרון" value={s.lastUpdate.label} desc={ago} />
          <Row label="ערוץ התראות" value="טלגרם" desc="מוגדר בצד השרת" />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className={`${card} p-5`}>
      <div className="mb-2 flex items-center justify-end gap-2">
        <h2 className="text-lg font-bold text-text1">{title}</h2>
        <span className="text-accent">{icon}</span>
      </div>
      <div>{children}</div>
    </section>
  );
}

function Row({ label, value, desc }: { label: string; value: string; desc?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-3 last:border-0">
      <div className="text-right">
        <div className="text-sm font-medium text-text1">{label}</div>
        {desc && <div className="text-xs text-text3">{desc}</div>}
      </div>
      <div className="shrink-0 text-sm font-bold tabular-nums text-accent">{value}</div>
    </div>
  );
}
