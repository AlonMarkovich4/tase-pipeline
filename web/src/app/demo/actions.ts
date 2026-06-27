"use server";

// Server action: settle demo paper-trades whose expiry has already settled, and
// credit the demo balance. This replaces the Streamlit-only flow
// (dashboard.py: close_demo_trade + _update_demo_balance) so the old dashboard
// can be retired.
//
// ATOMIC + IDEMPOTENT (does NOT copy the old read-modify-insert bug):
//   • The settle write is a CONDITIONAL PATCH guarded by `status=eq.open`, with
//     `Prefer: return=representation`. Only the call that actually flips
//     open→closed gets a row back; a repeat/concurrent call matches 0 rows and
//     skips the balance credit — so a trade can never be settled or counted
//     twice.
//   • The balance is credited ONLY when that PATCH returned a row (we are the
//     one that closed it). Due trades are processed sequentially, so within a
//     sweep each balance read sees the prior write.
// No client input — the sweep is fully server-driven (nothing to validate from a
// caller), which is strictly safer than a per-trade endpoint.
//
// Residual (web-only) limitation: the absolute-balance read-modify-insert can
// still lose an update if two *separate* page-loads settle *different* trades at
// the exact same instant. The true fix is a server-side atomic increment (RPC)
// or a delta-summed balance — tracked as a follow-up (QA Phase 0). Per-trade
// double-counting (the main risk) is fully prevented by the PATCH guard.

const URL = (process.env.SUPABASE_URL ?? "").replace(/\/$/, "");
const KEY = process.env.SUPABASE_KEY ?? "";
const MULT = 50;                       // ₪ per index point per contract (TA-35)
const DEMO_INITIAL_BALANCE = 100_000;  // matches dashboard.py DEMO_INITIAL_BALANCE
const IDX_MIN = 1000, IDX_MAX = 10000; // sane TA-35 settlement-price band

const h = (extra: Record<string, string> = {}) => ({
  apikey: KEY,
  Authorization: `Bearer ${KEY}`,
  "Content-Type": "application/json",
  ...extra,
});
const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

// Normalize one stored leg to ₪ inputs. Handles BOTH shapes that exist in
// demo_trades: the web shape {kind:"call"|"put", side:1|-1, strike, qty, entryPx(₪)}
// and the Streamlit shape {type:"Call"|"Put", action:"BUY"|"SELL", strike, qty,
// premium_pts(points)}. Returns null for any malformed leg.
function legIls(raw: unknown):
  | { call: boolean; side: number; strike: number; qty: number; entryIls: number }
  | null {
  if (raw == null || typeof raw !== "object") return null;
  const l = raw as Record<string, unknown>;

  const call =
    l.kind === "call" ? true : l.kind === "put" ? false
    : l.type === "Call" ? true : l.type === "Put" ? false : null;
  if (call === null) return null;

  const side =
    l.side === 1 || l.side === -1 ? (l.side as number)
    : l.action === "BUY" ? 1 : l.action === "SELL" ? -1 : null;
  if (side === null) return null;

  const strike = Number(l.strike);
  const qty = Number(l.qty ?? 1);
  // Entry premium in ₪: web stores entryPx already in ₪; Streamlit stores
  // premium_pts in index points (× MULT → ₪).
  const entryIls =
    l.entryPx != null ? Number(l.entryPx)
    : l.premium_pts != null ? Number(l.premium_pts) * MULT : NaN;

  if (![strike, qty, entryIls].every((n) => Number.isFinite(n))) return null;
  if (!(strike >= IDX_MIN && strike <= IDX_MAX)) return null;
  if (!Number.isInteger(qty) || qty <= 0) return null;
  return { call, side, strike, qty, entryIls };
}

// P&L in ₪ at the settlement index — identical math to web payoffAt and
// Streamlit sandbox_trade_pnl: Σ side·(intrinsic_₪ − entry_₪)·qty.
function tradePnlIls(legsRaw: unknown, idx: number): number | null {
  let legs: unknown = legsRaw;
  if (typeof legs === "string") {
    try { legs = JSON.parse(legs); } catch { return null; }
  }
  if (!Array.isArray(legs) || legs.length === 0) return null;
  let total = 0;
  for (const r of legs) {
    const lg = legIls(r);
    if (!lg) return null; // malformed leg → refuse to settle this trade
    const intrinsicIls =
      (lg.call ? Math.max(idx - lg.strike, 0) : Math.max(lg.strike - idx, 0)) * MULT;
    total += lg.side * (intrinsicIls - lg.entryIls) * lg.qty;
  }
  return Math.round(total * 100) / 100;
}

async function getJson(path: string): Promise<Record<string, unknown>[] | null> {
  try {
    const r = await fetch(`${URL}/rest/v1/${path}`, { headers: h(), cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as Record<string, unknown>[];
  } catch {
    return null;
  }
}

export type SettleResult = { settled: number; skipped: number; errors: number };

// Sweep open demo trades whose expiry has already settled and book their P&L.
// Idempotent: safe to call from any page load (or a cron) as often as you like.
export async function settleDueDemoTrades(): Promise<SettleResult> {
  const out: SettleResult = { settled: 0, skipped: 0, errors: 0 };
  if (!URL || !KEY) return out;

  // Israel "today" (TASE calendar), YYYY-MM-DD.
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jerusalem" }).format(new Date());

  // Open trades whose expiry is already in the past.
  const due = await getJson(
    `demo_trades?status=eq.open&expiry_date=lt.${today}&select=*&limit=200`,
  );
  if (!due || due.length === 0) return out;

  for (const t of due) {
    const tradeId = String(t.trade_id ?? "");
    const expiry = String(t.expiry_date ?? "");
    if (!tradeId || !expiry) { out.errors++; continue; }

    // Settlement price = the real strategy's actual_index_close for that expiry.
    // No reliable close → leave the trade OPEN (don't guess a price); it settles
    // on a later sweep once the real strategy settles. Mirrors dashboard.py.
    const sc = await getJson(
      `iron_condor_strategies?expiry_date=eq.${encodeURIComponent(expiry)}` +
        `&actual_index_close=gt.0&select=actual_index_close&limit=1`,
    );
    const settleIdx = sc && sc[0] != null ? Number(sc[0].actual_index_close) : NaN;
    if (!isNum(settleIdx) || settleIdx < IDX_MIN || settleIdx > IDX_MAX) { out.skipped++; continue; }

    const pnl = tradePnlIls(t.legs, settleIdx);
    if (pnl === null) { out.errors++; continue; } // malformed legs → don't settle

    // ── Atomic settle: flips a row ONLY if it is still open ──────────────────
    let settledRows: unknown[] | null = null;
    try {
      const r = await fetch(
        `${URL}/rest/v1/demo_trades?trade_id=eq.${encodeURIComponent(tradeId)}&status=eq.open`,
        {
          method: "PATCH",
          headers: h({ Prefer: "return=representation" }),
          cache: "no-store",
          body: JSON.stringify({
            status: "closed",
            settlement_index: settleIdx,
            pnl_ils: pnl,
            close_reason: "web_expiry_settlement",
            closed_at: new Date().toISOString(),
          }),
        },
      );
      if (!r.ok) { out.errors++; continue; }
      settledRows = (await r.json()) as unknown[];
    } catch {
      out.errors++; continue;
    }

    // 0 rows → another sweep already settled it → idempotent no-op (no credit).
    if (!Array.isArray(settledRows) || settledRows.length === 0) { out.skipped++; continue; }

    // ── Credit balance ONLY because this call just closed the trade ──────────
    const balRows = await getJson(`demo_balance?select=balance&order=updated_at.desc&limit=1`);
    const base =
      balRows && balRows[0] != null && isNum(Number(balRows[0].balance))
        ? Number(balRows[0].balance)
        : DEMO_INITIAL_BALANCE;
    const newBalance = Math.round((base + pnl) * 100) / 100;
    try {
      const br = await fetch(`${URL}/rest/v1/demo_balance`, {
        method: "POST",
        headers: h({ Prefer: "return=minimal" }),
        cache: "no-store",
        body: JSON.stringify({
          balance: newBalance,
          change_amount: pnl,
          change_reason: `web_settle_${tradeId}`,
        }),
      });
      // Surface (don't swallow) a balance-write failure: the trade is closed but
      // the credit didn't land — the change_reason ties it for reconciliation.
      if (!br.ok) { out.errors++; continue; }
    } catch {
      out.errors++; continue;
    }
    out.settled++;
  }
  return out;
}
