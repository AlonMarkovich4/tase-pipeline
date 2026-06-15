// Server-only data layer. Reads Supabase with the service key from server env
// (never shipped to the client). Every fetch is `no-store` so the page renders
// live per request and the build never depends on the DB being reachable.
import "server-only";

const URL = (process.env.SUPABASE_URL ?? "").replace(/\/$/, "");
const KEY = process.env.SUPABASE_KEY ?? "";

async function sb<T = unknown>(path: string): Promise<T[]> {
  if (!URL || !KEY) return [];
  try {
    const r = await fetch(`${URL}/rest/v1/${path}`, {
      headers: { apikey: KEY, Authorization: `Bearer ${KEY}` },
      cache: "no-store",
    });
    if (!r.ok) return [];
    return (await r.json()) as T[];
  } catch {
    return [];
  }
}

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
};

export type IndexPoint = { date: string; value: number };
export type IndexData = { current: number; changePct: number; series: IndexPoint[] };

/** TLV35 index: latest value + the last ~10 expiries as a settlement series. */
export async function getIndexData(): Promise<IndexData> {
  // settled expiries -> one index point per expiry (the actual close)
  const rows = await sb<Record<string, unknown>>(
    "iron_condor_strategies?select=expiry_date,actual_index_close,base_index_value" +
      "&order=expiry_date.desc&limit=400",
  );
  const byExpiry = new Map<string, number>();
  for (const r of rows) {
    const d = String(r.expiry_date ?? "");
    const close = num(r.actual_index_close);
    if (d && close && close > 0 && !byExpiry.has(d)) byExpiry.set(d, close);
  }
  const series: IndexPoint[] = [...byExpiry.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .slice(-10)
    .map(([date, value]) => ({ date, value }));

  // current index: latest live underlying, else last settled, else mockup value
  const live = await sb<Record<string, unknown>>(
    "tase_putcall?select=underlingasset_call&order=id.desc&limit=20",
  );
  let current = 0;
  for (const r of live) {
    const v = num(r.underlingasset_call);
    if (v && v >= 1000 && v <= 10000) { current = v; break; }
  }
  if (!current) current = series.at(-1)?.value ?? 4292.94;

  const prev = series.at(-2)?.value ?? current;
  const changePct = prev ? ((current - prev) / prev) * 100 : 0;
  return { current, changePct, series: series.length ? series : FALLBACK_SERIES };
}

const FALLBACK_SERIES: IndexPoint[] = [
  ["2026-06-02", 4266], ["2026-06-03", 4262], ["2026-06-04", 4268],
  ["2026-06-05", 4232], ["2026-06-08", 4163], ["2026-06-09", 4287],
  ["2026-06-10", 4209], ["2026-06-11", 4203], ["2026-06-12", 4332],
  ["2026-06-15", 4292.94],
].map(([date, value]) => ({ date: date as string, value: value as number }));

export type Kpi = { label: string; value: string; sub: string; tone: "pos" | "neg" | "accent" | "warn" };

const ils = (n: number) => `₪ ${Math.round(n).toLocaleString("en-US")}`;

/** Home KPI cards, wired to live Supabase data. Subscription has no DB
 *  source yet, so it stays static. */
export async function getKpis(): Promise<Kpi[]> {
  const [bal, strat] = await Promise.all([
    sb<Record<string, unknown>>("demo_balance?select=balance&order=id.desc&limit=1"),
    sb<Record<string, unknown>>(
      "iron_condor_strategies?select=expiry_date,result_status,actual_index_close," +
        "actual_pnl_ils,is_valid&order=trigger_date.desc&limit=2000",
    ),
  ]);

  const balance = num(bal[0]?.balance) ?? 100000;

  const valid = strat.filter((x) => x.is_valid !== false);
  const isSettled = (x: Record<string, unknown>) =>
    !!x.result_status && (num(x.actual_index_close) ?? 0) > 0;
  const settled = valid.filter(isSettled);
  const active = valid.filter((x) => !isSettled(x));
  const pnl = settled.reduce((s, x) => s + (num(x.actual_pnl_ils) ?? 0), 0);
  const wins = settled.filter((x) => (num(x.actual_pnl_ils) ?? 0) > 0).length;
  const winRate = settled.length ? Math.round((wins / settled.length) * 100) : 0;
  const activeExpiries = new Set(active.map((x) => String(x.expiry_date))).size;

  const pnlValue = `${pnl >= 0 ? "+" : "−"}${ils(Math.abs(pnl))}`;
  return [
    { label: "שווי תיק דמו", value: ils(balance), sub: "תיק דמו", tone: "warn" },
    { label: "רווח/הפסד מסולק", value: pnlValue, sub: `${winRate}% הצלחה`, tone: pnl >= 0 ? "pos" : "neg" },
    { label: "פוזיציות פתוחות", value: String(active.length), sub: `${activeExpiries} פקיעות`, tone: "accent" },
    { label: "מצב המנוי", value: "מנוי פעיל", sub: "269 ימים נותרים", tone: "pos" },
  ];
}

export type Freshness = { label: string; agoMin: number | null; tone: "pos" | "warn" | "neg" };

/** Last pipeline update: newest fetch_date+fetch_time in tase_putcall (Israel time). */
export async function getLastUpdate(): Promise<Freshness> {
  const rows = await sb<Record<string, unknown>>(
    "tase_putcall?select=fetch_date,fetch_time&order=id.desc&limit=1",
  );
  const fd = rows[0]?.fetch_date ? String(rows[0].fetch_date) : "";
  const ft = rows[0]?.fetch_time ? String(rows[0].fetch_time) : "";
  if (!fd || !ft) return { label: "—", agoMin: null, tone: "neg" };
  // both parsed as server-local naive datetimes; the offset cancels in the diff,
  // so the result is the true Israel wall-clock minutes-ago regardless of server TZ.
  const last = new Date(`${fd}T${ft}`);
  const nowIL = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Jerusalem" }));
  const agoMin = Math.max(0, Math.round((nowIL.getTime() - last.getTime()) / 60000));
  const [, m, d] = fd.split("-");
  const tone: Freshness["tone"] = agoMin <= 30 ? "pos" : agoMin <= 120 ? "warn" : "neg";
  return { label: `${d}/${m} ${ft}`, agoMin, tone };
}

// ── Options simulator ─────────────────────────────────────────────────
export const MULT = 50; // ₪ per index point per contract (TASE TA-35)

export type ChainRow = {
  strike: number;
  callPx: number; // ₪ (lastrate)
  putPx: number;
  callDelta: number;
  putDelta: number;
};
export type ExpiryChain = {
  date: string;
  dayName: string;
  days: number;
  spot: number;
  rows: ChainRow[];
};

const DAYS_HE = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const nowIsrael = () =>
  new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Jerusalem" }));
function dayNameHe(iso: string) {
  return DAYS_HE[new Date(`${iso}T00:00:00`).getDay()] ?? "";
}
function daysTo(iso: string) {
  const t = new Date(`${iso}T00:00:00`).getTime();
  const n = nowIsrael(); n.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((t - n.getTime()) / 86400000));
}

/** Live option chain per expiry (latest snapshot), for the simulator. */
export async function getSimulatorData(): Promise<ExpiryChain[]> {
  const { current: spot } = await getIndexData();
  const exps = await sb<Record<string, unknown>>("tase_putcall?select=expiry_date&order=expiry_date");
  const dates = [...new Set(exps.map((e) => String(e.expiry_date)).filter(Boolean))].sort();

  const out: ExpiryChain[] = [];
  for (const d of dates) {
    const latest = await sb<Record<string, unknown>>(
      `tase_putcall?select=fetch_date,fetch_time&expiry_date=eq.${d}&order=id.desc&limit=1`,
    );
    const fd = latest[0]?.fetch_date, ft = latest[0]?.fetch_time;
    if (!fd || !ft) continue;
    const raw = await sb<Record<string, unknown>>(
      `tase_putcall?select=expirationprice_call,lastrate_call,lastrate_put,delta_call,delta_put` +
        `&expiry_date=eq.${d}&fetch_date=eq.${fd}&fetch_time=eq.${ft}&order=expirationprice_call`,
    );
    const rows: ChainRow[] = raw
      .map((r) => ({
        strike: num(r.expirationprice_call) ?? 0,
        callPx: num(r.lastrate_call) ?? 0,
        putPx: num(r.lastrate_put) ?? 0,
        callDelta: num(r.delta_call) ?? 0,
        putDelta: num(r.delta_put) ?? 0,
      }))
      .filter((r) => r.strike >= 1000)
      .sort((a, b) => a.strike - b.strike);
    out.push({ date: d, dayName: dayNameHe(d), days: daysTo(d), spot, rows });
  }
  return out;
}

// ── Demo paper-trading book ───────────────────────────────────────────
export type DemoLeg = { kind: "call" | "put"; strike: number; side: 1 | -1; qty: number; entryPx: number };
export type DemoTrade = {
  tradeId: string;
  strategyName: string;
  expiryDate: string;
  status: string;
  legs: DemoLeg[];
  entryIndex: number | null;
  netPremiumPts: number | null;
  maxProfitIls: number | null;
  maxRiskIls: number | null;
  settlementIndex: number | null;
  pnlIls: number | null;
  closeReason: string | null;
  createdAt: string | null;
};
export type DemoBook = { balance: number | null; balanceUpdated: string | null; trades: DemoTrade[] };

/** Demo book: latest balance + all paper trades (newest first). */
export async function getDemoBook(): Promise<DemoBook> {
  const [bal, rows] = await Promise.all([
    sb<Record<string, unknown>>("demo_balance?select=balance,updated_at&order=updated_at.desc&limit=1"),
    sb<Record<string, unknown>>("demo_trades?select=*&order=created_at.desc"),
  ]);
  const trades: DemoTrade[] = rows.map((r) => ({
    tradeId: String(r.trade_id ?? r.id ?? ""),
    strategyName: String(r.strategy_name ?? "—"),
    expiryDate: String(r.expiry_date ?? ""),
    status: String(r.status ?? "open"),
    legs: Array.isArray(r.legs) ? (r.legs as DemoLeg[]) : [],
    entryIndex: num(r.entry_index),
    netPremiumPts: num(r.net_premium_pts),
    maxProfitIls: num(r.max_profit_ils),
    maxRiskIls: num(r.max_risk_ils),
    settlementIndex: num(r.settlement_index),
    pnlIls: num(r.pnl_ils),
    closeReason: r.close_reason ? String(r.close_reason) : null,
    createdAt: r.created_at ? String(r.created_at) : null,
  }));
  return {
    balance: num(bal[0]?.balance),
    balanceUpdated: bal[0]?.updated_at ? String(bal[0].updated_at) : null,
    trades,
  };
}
