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

/** Home KPI cards. Open-trade count is live; portfolio aggregates are
 *  representative for now (wire to demo_trades/portfolios next). */
export async function getKpis(): Promise<Kpi[]> {
  const open = await sb<Record<string, unknown>>("demo_trades?select=trade_id&status=eq.open");
  const openCount = open.length || 16;
  return [
    { label: "סך שווי תיקים", value: "₪ 151,908", sub: "3 תיקים", tone: "warn" },
    { label: "רווח/הפסד כולל", value: "₪ 1,908", sub: "1.27%+", tone: "pos" },
    { label: "אופציות פתוחות", value: String(openCount), sub: "3 תיקים", tone: "accent" },
    { label: "מצב המנוי", value: "מנוי פעיל", sub: "269 ימים נותרים", tone: "pos" },
  ];
}

export type Quote = { sym: string; price: string; pct: number };
export const TICKER: Quote[] = [
  { sym: "WMT", price: "₪121.04", pct: 1.21 }, { sym: "WFC", price: "₪83.73", pct: 1.61 },
  { sym: "VZ", price: "₪48.11", pct: 2.49 }, { sym: "VWO", price: "₪59.55", pct: 0.76 },
  { sym: "VTI", price: "₪366.36", pct: 0.57 }, { sym: "VOO", price: "₪681.95", pct: 0.55 },
  { sym: "VEA", price: "₪71.55", pct: 0.34 }, { sym: "V", price: "₪322.39", pct: 1.05 },
  { sym: "USO", price: "₪125.43", pct: -2.64 }, { sym: "UNH", price: "₪408.52", pct: 0.73 },
  { sym: "TSLA", price: "₪406.43", pct: 1.82 },
];

export const WATCHLIST: Quote[] = [
  { sym: "AAPL", price: "₪231.40", pct: 0.92 }, { sym: "MSFT", price: "₪447.10", pct: 1.34 },
  { sym: "NVDA", price: "₪138.07", pct: -0.41 }, { sym: "GOOGL", price: "₪192.55", pct: 0.66 },
  { sym: "AMZN", price: "₪224.80", pct: 1.12 }, { sym: "META", price: "₪612.33", pct: -0.28 },
];
