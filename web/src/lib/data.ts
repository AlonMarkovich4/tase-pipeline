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

/** Current VTA35 volatility ("fear") index — Yahoo 598.TA, fetched server-side.
 *  Display-only. Fail-safe like `sb()`: returns null on failure (never throws).
 *  A 2-min in-process cache avoids hammering Yahoo on every page load and, on a
 *  transient Yahoo failure, serves the last good value so the readout doesn't flicker. */
let _vtaCache: { val: number | null; ts: number } = { val: null, ts: 0 };
const VTA_TTL_MS = 120_000;

export async function getVta35(): Promise<number | null> {
  const now = Date.now();
  if (_vtaCache.val != null && now - _vtaCache.ts < VTA_TTL_MS) return _vtaCache.val;
  try {
    const r = await fetch(
      "https://query1.finance.yahoo.com/v8/finance/chart/598.TA?interval=1d&range=1d",
      { headers: { "User-Agent": "Mozilla/5.0" }, cache: "no-store" },
    );
    if (r.ok) {
      const data = await r.json();
      const price = data?.chart?.result?.[0]?.meta?.regularMarketPrice;
      if (typeof price === "number" && price > 0) {
        _vtaCache = { val: price, ts: now };
        return price;
      }
    }
  } catch {
    // fall through to last-good value
  }
  return _vtaCache.val; // last good value (or null if never fetched)
}

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

// ── Strategy track record (pipeline's auto-generated iron condors) ─────
export type Strategy = {
  expiryDate: string;
  baseIndex: number | null;
  shortPut: number | null;
  shortCall: number | null;
  longPut: number | null;
  longCall: number | null;
  netPremium: number | null;
  maxProfit: number | null;
  maxRisk: number | null;
  riskReward: number | null;
  intervalPct: number | null;
  resultStatus: string | null;
  actualClose: number | null;
  actualPnl: number | null;
};
export type StrategiesData = {
  strategies: Strategy[];
  settled: number;
  wins: number;
  losses: number;
  totalPnl: number;
  winRate: number;
  outcomes: { maxProfit: number; partialLoss: number; maxLoss: number };
  byExpiry: { expiry: string; pnl: number; count: number }[];
};

/** Valid iron-condor strategies with their settled outcomes + aggregates. */
export async function getStrategiesData(): Promise<StrategiesData> {
  const rows = await sb<Record<string, unknown>>(
    "iron_condor_strategies?select=expiry_date,base_index_value,short_put_strike,short_call_strike," +
      "long_put_strike,long_call_strike,total_net_premium,max_profit_ils,max_risk_ils,risk_reward_ratio," +
      "interval_pct,result_status,actual_index_close,actual_pnl_ils&is_valid=eq.true&order=expiry_date.desc",
  );
  const strategies: Strategy[] = rows.map((r) => ({
    expiryDate: String(r.expiry_date ?? ""),
    baseIndex: num(r.base_index_value),
    shortPut: num(r.short_put_strike),
    shortCall: num(r.short_call_strike),
    longPut: num(r.long_put_strike),
    longCall: num(r.long_call_strike),
    netPremium: num(r.total_net_premium),
    maxProfit: num(r.max_profit_ils),
    maxRisk: num(r.max_risk_ils),
    riskReward: num(r.risk_reward_ratio),
    intervalPct: num(r.interval_pct),
    resultStatus: r.result_status ? String(r.result_status) : null,
    actualClose: num(r.actual_index_close),
    actualPnl: num(r.actual_pnl_ils),
  }));

  const settledList = strategies.filter((s) => s.actualPnl != null);
  const wins = settledList.filter((s) => (s.actualPnl ?? 0) > 0).length;
  const losses = settledList.filter((s) => (s.actualPnl ?? 0) < 0).length;
  const totalPnl = settledList.reduce((a, s) => a + (s.actualPnl ?? 0), 0);
  const outcomes = {
    maxProfit: strategies.filter((s) => s.resultStatus === "max_profit").length,
    partialLoss: strategies.filter((s) => s.resultStatus?.startsWith("partial")).length,
    maxLoss: strategies.filter((s) => s.resultStatus?.startsWith("max_loss")).length,
  };
  const byExpiryMap = new Map<string, { pnl: number; count: number }>();
  for (const s of settledList) {
    const cur = byExpiryMap.get(s.expiryDate) ?? { pnl: 0, count: 0 };
    cur.pnl += s.actualPnl ?? 0;
    cur.count += 1;
    byExpiryMap.set(s.expiryDate, cur);
  }
  const byExpiry = [...byExpiryMap.entries()]
    .map(([expiry, v]) => ({ expiry, ...v }))
    .sort((a, b) => a.expiry.localeCompare(b.expiry));

  return {
    strategies,
    settled: settledList.length,
    wins,
    losses,
    totalPnl,
    winRate: settledList.length ? Math.round((wins / settledList.length) * 100) : 0,
    outcomes,
    byExpiry,
  };
}

// ── Best condor per expiry (reads the best_condor_per_expiry View) ─────
export type BestCondor = {
  expiryDate: string;
  dayName: string;
  interval: number;
  pnl: number;        // ₪ potential — "how much we could have profited"
  rr: number | null;  // risk/reward ratio
  maxRisk: number | null;
  baseIndex: number | null;
  close: number | null;
};

/** The best-₪ condor per expiry — single source of truth shared with the bot.
 *  Reads the `best_condor_per_expiry` Supabase View directly. */
export async function getBestCondorPerExpiry(): Promise<BestCondor[]> {
  const rows = await sb<Record<string, unknown>>(
    "best_condor_per_expiry?select=expiry_date,expiry_day_name,interval_pct," +
      "actual_pnl_ils,risk_reward_ratio,max_risk_ils,base_index_value,actual_index_close" +
      "&order=expiry_date.desc",
  );
  return rows.map((r) => ({
    expiryDate: String(r.expiry_date ?? ""),
    dayName: String(r.expiry_day_name ?? ""),
    interval: num(r.interval_pct) ?? 0,
    pnl: num(r.actual_pnl_ils) ?? 0,
    rr: num(r.risk_reward_ratio),
    maxRisk: num(r.max_risk_ils),
    baseIndex: num(r.base_index_value),
    close: num(r.actual_index_close),
  }));
}

// ── Expiry calendar ───────────────────────────────────────────────────
export type ExpiryEntry = {
  date: string;
  daysTo: number; // signed: <0 past, 0 today, >0 upcoming (Israel days)
  strategies: number;
  strategiesSettled: number;
  demoOpen: number;
  demoClosed: number;
  pnl: number | null; // settled demo P&L for that expiry
  live: boolean; // tradeable now (present in tase_putcall)
  strategyTypes: string[]; // distinct strategy names present on this expiry
};

const ICONDOR = "איירון קונדור";

/** Unified expiry calendar across the live chain, strategies, and demo book. */
export async function getExpiryCalendar(): Promise<ExpiryEntry[]> {
  const [live, strat, demo] = await Promise.all([
    sb<Record<string, unknown>>("tase_putcall?select=expiry_date"),
    sb<Record<string, unknown>>("iron_condor_strategies?select=expiry_date,result_status&is_valid=eq.true"),
    sb<Record<string, unknown>>("demo_trades?select=expiry_date,status,pnl_ils,strategy_name"),
  ]);
  const nIL = nowIsrael();
  nIL.setHours(0, 0, 0, 0);
  const signedDays = (iso: string) =>
    Math.round((new Date(`${iso}T00:00:00`).getTime() - nIL.getTime()) / 86400000);

  const liveSet = new Set(live.map((x) => String(x.expiry_date ?? "")).filter(Boolean));
  const map = new Map<string, ExpiryEntry>();
  const types = new Map<string, Set<string>>();
  const get = (d: string) => {
    let e = map.get(d);
    if (!e) {
      e = { date: d, daysTo: signedDays(d), strategies: 0, strategiesSettled: 0, demoOpen: 0, demoClosed: 0, pnl: null, live: liveSet.has(d), strategyTypes: [] };
      map.set(d, e);
      types.set(d, new Set());
    }
    return e;
  };
  liveSet.forEach((d) => get(d));
  for (const s of strat) {
    const d = String(s.expiry_date ?? "");
    if (!d) continue;
    const e = get(d);
    e.strategies++;
    if (s.result_status) e.strategiesSettled++;
    types.get(d)!.add(ICONDOR);
  }
  for (const t of demo) {
    const d = String(t.expiry_date ?? "");
    if (!d) continue;
    const e = get(d);
    if (String(t.status) === "closed") {
      e.demoClosed++;
      const p = num(t.pnl_ils);
      if (p != null) e.pnl = (e.pnl ?? 0) + p;
    } else e.demoOpen++;
    if (t.strategy_name) types.get(d)!.add(String(t.strategy_name));
  }
  for (const [d, e] of map) e.strategyTypes = [...(types.get(d) ?? [])];
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

// ── Alerts & events ───────────────────────────────────────────────────
export type SysEvent = { type: string; label: string; detail: string; tone: string; at: string };
export type MarketEvent = { date: string; name: string; category: string; description: string };
export type AlertsData = { freshness: Freshness; system: SysEvent[]; market: MarketEvent[] };

const SYS_LABELS: Record<string, { label: string; tone: string }> = {
  settlement_done: { label: "סילוק פקיעה בוצע", tone: "pos" },
  daily_summary_sent: { label: "סיכום יומי נשלח", tone: "accent" },
  weekly_heartbeat: { label: "פעימה שבועית", tone: "text3" },
  strategy_triggered: { label: "אסטרטגיה שבועית הופעלה", tone: "accent" },
};

/** System activity (pipeline_state milestones) + freshness. Market events
 *  intentionally left empty for now — to be wired to a future source. */
export async function getAlertsData(): Promise<AlertsData> {
  const [freshness, state] = await Promise.all([
    getLastUpdate(),
    sb<Record<string, unknown>>("pipeline_state?select=key,value,updated_at"),
  ]);
  const system: SysEvent[] = state
    .map((r) => {
      const key = String(r.key ?? "");
      const [type, arg = ""] = key.split(":");
      const m = SYS_LABELS[type];
      return { type, label: m?.label ?? type, detail: arg, tone: m?.tone ?? "text3", at: String(r.updated_at ?? "") };
    })
    .sort((a, b) => b.at.localeCompare(a.at));
  const market: MarketEvent[] = [];
  return { freshness, system, market };
}

// ── Settings (live system configuration, read-only) ───────────────────
export type SettingsData = {
  intervals: number[];
  wingWidth: number | null;
  daysMin: number | null;
  daysMax: number | null;
  maxRisk: number | null;
  demoBalance: number | null;
  demoSince: string | null;
  demoReason: string | null;
  lastUpdate: Freshness;
};

/** Real parameters the pipeline runs with, derived from the data. */
export async function getSettings(): Promise<SettingsData> {
  const [rows, bal, lastUpdate] = await Promise.all([
    sb<Record<string, unknown>>(
      "iron_condor_strategies?select=interval_pct,wing_width,days_to_expiry,max_risk_ils&is_valid=eq.true",
    ),
    sb<Record<string, unknown>>("demo_balance?select=balance,change_reason,updated_at&order=updated_at.desc&limit=1"),
    getLastUpdate(),
  ]);
  const vals = (f: string) => rows.map((r) => num(r[f])).filter((x): x is number => x != null);
  const intervals = [...new Set(vals("interval_pct"))].sort((a, b) => a - b);
  const widths = [...new Set(vals("wing_width"))];
  const days = vals("days_to_expiry");
  const risks = vals("max_risk_ils");
  return {
    intervals,
    wingWidth: widths.length ? Math.max(...widths) : null,
    daysMin: days.length ? Math.min(...days) : null,
    daysMax: days.length ? Math.max(...days) : null,
    maxRisk: risks.length ? Math.max(...risks) : null,
    demoBalance: num(bal[0]?.balance),
    demoSince: bal[0]?.updated_at ? String(bal[0].updated_at) : null,
    demoReason: bal[0]?.change_reason ? String(bal[0].change_reason) : null,
    lastUpdate,
  };
}
