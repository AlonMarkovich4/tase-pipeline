"use server";

// Server action: dispatch a simulated position to the demo paper-trading book
// (demo_trades). Uses the service key from server env — never reaches the client.
//
// SECURITY: this endpoint is currently UNAUTHENTICATED and writes with the
// service-role (RLS-bypassing) key. Until that changes, every field is strictly
// validated server-side and the row is REBUILT from validated values only (the
// client object is never spread into the DB), so a hostile caller cannot inject
// arbitrary columns or out-of-range values. Follow-up (separate, larger change —
// QA_ASSESSMENT Phase 0 #2): require authentication and switch to the anon key +
// row-level security so the service key is no longer exposed to public writes.

const URL = (process.env.SUPABASE_URL ?? "").replace(/\/$/, "");
const KEY = process.env.SUPABASE_KEY ?? "";

export type LegPayload = { kind: "call" | "put"; strike: number; side: 1 | -1; qty: number; entryPx: number };
export type SimPayload = {
  strategyName: string;
  expiryDate: string;
  entryIndex: number;
  netPremiumPts: number;
  maxProfitIls: number;
  maxRiskIls: number;
  legs: LegPayload[];
};

// ── Validation bounds — sane TA-35 ranges; reject NaN/Infinity/garbage ──
const IDX_MIN = 1000, IDX_MAX = 10000;   // TA-35 index value & option strikes
const QTY_MAX = 10000;                    // contracts per leg
const PX_MAX = 100000;                    // option price (index points)
const ILS_MAX = 1e9;                      // ₪ profit / risk magnitude
const PTS_MAX = 1e6;                      // net premium (index points)
const MAX_LEGS = 8;                       // simulator builds 1–4; cap generously
const NAME_MAX = 120;

const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const inRange = (x: number, lo: number, hi: number) => x >= lo && x <= hi;

function validateLeg(l: unknown, i: number): string | null {
  if (l == null || typeof l !== "object") return `רגל ${i + 1}: מבנה לא תקין`;
  const leg = l as Record<string, unknown>;
  if (leg.kind !== "call" && leg.kind !== "put") return `רגל ${i + 1}: סוג אופציה לא תקין`;
  if (leg.side !== 1 && leg.side !== -1) return `רגל ${i + 1}: כיוון לא תקין`;
  if (!isNum(leg.strike) || !inRange(leg.strike, IDX_MIN, IDX_MAX)) return `רגל ${i + 1}: סטרייק מחוץ לטווח`;
  if (!isNum(leg.qty) || !Number.isInteger(leg.qty) || !inRange(leg.qty, 1, QTY_MAX)) return `רגל ${i + 1}: כמות לא תקינה`;
  if (!isNum(leg.entryPx) || !inRange(leg.entryPx, 0, PX_MAX)) return `רגל ${i + 1}: מחיר כניסה לא תקין`;
  return null;
}

// Validate the raw payload (treated as untrusted) and return a Hebrew error
// string, or null when everything is well-formed and in range.
function validate(raw: unknown): string | null {
  if (raw == null || typeof raw !== "object") return "מבנה הבקשה לא תקין";
  const p = raw as Record<string, unknown>;

  if (typeof p.strategyName !== "string" || !p.strategyName.trim() || p.strategyName.length > NAME_MAX)
    return "שם אסטרטגיה לא תקין";

  if (typeof p.expiryDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(p.expiryDate))
    return "תאריך פקיעה לא תקין";
  if (Number.isNaN(Date.parse(`${p.expiryDate}T00:00:00Z`))) return "תאריך פקיעה לא תקין";
  const yr = Number(p.expiryDate.slice(0, 4));
  if (yr < 2020 || yr > 2100) return "תאריך פקיעה מחוץ לטווח";

  if (!isNum(p.entryIndex) || !inRange(p.entryIndex, IDX_MIN, IDX_MAX)) return "מדד כניסה מחוץ לטווח";
  if (!isNum(p.netPremiumPts) || !inRange(p.netPremiumPts, -PTS_MAX, PTS_MAX)) return "פרמיה נטו לא תקינה";
  // maxProfit may be negative for a guaranteed-loss custom position — bound by magnitude, not sign.
  if (!isNum(p.maxProfitIls) || !inRange(p.maxProfitIls, -ILS_MAX, ILS_MAX)) return "רווח מקסימלי לא תקין";
  if (!isNum(p.maxRiskIls) || !inRange(p.maxRiskIls, 0, ILS_MAX)) return "סיכון מקסימלי לא תקין";

  if (!Array.isArray(p.legs) || p.legs.length < 1 || p.legs.length > MAX_LEGS) return "מספר רגליים לא תקין";
  for (let i = 0; i < p.legs.length; i++) {
    const e = validateLeg(p.legs[i], i);
    if (e) return e;
  }
  return null;
}

// ── Coarse rate limit (defense-in-depth; per-process, global) ──
// NOT a substitute for auth — once the endpoint is authenticated, rate-limit per
// identity. Single long-running Node server on Render → module state persists.
const RL_WINDOW_MS = 60_000;
const RL_MAX = 20;                        // inserts per minute (whole process)
let rlHits: number[] = [];
function rateLimited(now: number): boolean {
  rlHits = rlHits.filter((t) => now - t < RL_WINDOW_MS);
  if (rlHits.length >= RL_MAX) return true;
  rlHits.push(now);
  return false;
}

export async function dispatchToDemo(p: SimPayload): Promise<{ ok: boolean; error?: string }> {
  if (!URL || !KEY) return { ok: false, error: "חסר חיבור ל-Supabase" };

  const err = validate(p as unknown);
  if (err) return { ok: false, error: err };

  if (rateLimited(Date.now())) return { ok: false, error: "יותר מדי שיגורים — נסה שוב בעוד דקה" };

  // Rebuild the row from validated fields only — never spread the client object,
  // so no unexpected columns/keys can reach the DB.
  const legs = p.legs.map((l) => ({ kind: l.kind, strike: l.strike, side: l.side, qty: l.qty, entryPx: l.entryPx }));
  try {
    const r = await fetch(`${URL}/rest/v1/demo_trades`, {
      method: "POST",
      headers: {
        apikey: KEY,
        Authorization: `Bearer ${KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        trade_id: `SIM-${Date.now()}`,
        strategy_name: p.strategyName.trim(),
        expiry_date: p.expiryDate,
        status: "open",
        legs,
        entry_index: p.entryIndex,
        net_premium_pts: p.netPremiumPts,
        max_profit_ils: p.maxProfitIls,
        max_risk_ils: p.maxRiskIls,
      }),
    });
    if (!r.ok) return { ok: false, error: `DB ${r.status}: ${(await r.text()).slice(0, 140)}` };
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "שגיאה לא ידועה" };
  }
}
