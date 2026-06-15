"use server";

// Server action: dispatch a simulated position to the demo paper-trading book
// (demo_trades). Uses the service key from server env — never reaches the client.

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

export async function dispatchToDemo(p: SimPayload): Promise<{ ok: boolean; error?: string }> {
  if (!URL || !KEY) return { ok: false, error: "חסר חיבור ל-Supabase" };
  if (!p.legs.length) return { ok: false, error: "אין רגליים לשיגור" };
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
        strategy_name: p.strategyName,
        expiry_date: p.expiryDate,
        status: "open",
        legs: p.legs,
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
