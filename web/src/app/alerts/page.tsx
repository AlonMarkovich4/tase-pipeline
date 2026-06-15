import { getAlertsData, type SysEvent } from "@/lib/data";
import { Message, Refresh, Calendar } from "@/components/icons";

const card = "rounded-2xl border border-border bg-surface/70 backdrop-blur";
const DOT: Record<string, string> = { pos: "bg-pos", accent: "bg-accent", warn: "bg-warn", neg: "bg-neg", text3: "bg-text3" };

function timeAgo(iso: string) {
  if (!iso) return "";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "הרגע";
  if (min < 60) return `לפני ${min} דק׳`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `לפני ${hr} שע׳`;
  return `לפני ${Math.round(hr / 24)} ימים`;
}

export default async function AlertsPage() {
  const { freshness, system } = await getAlertsData();
  const ago =
    freshness.agoMin == null ? "אין נתונים"
      : freshness.agoMin < 60 ? `לפני ${freshness.agoMin} דק׳`
      : `לפני ${Math.floor(freshness.agoMin / 60)}ש׳ ${freshness.agoMin % 60}ד׳`;
  const FRESH_DOT = { pos: "bg-pos", warn: "bg-warn", neg: "bg-neg" } as const;

  return (
    <div className="space-y-5">
      {/* freshness / health */}
      <section className={`${card} flex flex-wrap items-center justify-between gap-3 p-5`}>
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface2 px-3 py-1.5 text-xs text-text2">
          <span className={`h-2 w-2 rounded-full ${FRESH_DOT[freshness.tone]}`} />
          עודכן לאחרונה: <span className="font-medium text-text1">{freshness.label}</span> · {ago}
        </span>
        <div className="flex items-center gap-2 text-right">
          <h1 className="text-lg font-bold text-text1">התראות ואירועים</h1>
          <span className="text-accent text-xl"><Message /></span>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* system activity */}
        <section className={`${card} p-5`}>
          <div className="mb-4 flex items-center justify-end gap-2">
            <h2 className="text-lg font-bold text-text1">פעילות מערכת</h2>
            <span className="text-text3"><Refresh /></span>
          </div>
          {system.length === 0 ? (
            <div className="py-6 text-center text-sm text-text3">אין אירועי מערכת</div>
          ) : (
            <ul className="space-y-2.5">
              {system.map((e, i) => <SysRow key={i} e={e} />)}
            </ul>
          )}
        </section>

        {/* market events — placeholder, to be wired to a future source */}
        <section className={`${card} p-5`}>
          <div className="mb-4 flex items-center justify-end gap-2">
            <h2 className="text-lg font-bold text-text1">אירועי שוק</h2>
            <span className="text-text3"><Calendar /></span>
          </div>
          <div className="grid min-h-[180px] place-items-center text-center">
            <div>
              <div className="text-sm text-text2">אין אירועים להצגה</div>
              <div className="mt-1 text-xs text-text3">ייחובר למקור נתונים בהמשך</div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function SysRow({ e }: { e: SysEvent }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl bg-surface2/40 px-3 py-2.5">
      <span className="shrink-0 text-[11px] text-text3">{timeAgo(e.at)}</span>
      <div className="flex min-w-0 flex-1 items-center justify-end gap-2.5 text-right">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-text1">{e.label}</div>
          {e.detail && <div className="text-[11px] text-text3">{e.detail}</div>}
        </div>
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[e.tone] ?? "bg-text3"}`} />
      </div>
    </li>
  );
}
