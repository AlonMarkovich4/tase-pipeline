"""
Delta-convention tests (Bug #5 / audit M-3).

Verified from diag_raw_response.json: TASE delta scale is 0..100, with
  Δcall ∈ [0, +100]   (positive)
  Δput  ∈ [−100, 0]   (negative — standard quant convention)
parity |Δcall| + |Δput| ≈ 100.

The validation must enforce each side's SIGN separately (not |delta|≤100), so a
sign-violating value (put with positive delta / call with negative) is rejected.
"""
import option_schema as osch


def _item(delta_c="50", delta_p="-50"):
    return {
        "ExpirationPrice_Call": "4200", "ExpirationPrice_Put": "4200",
        "LastRate_Call": "100", "LastRate_Put": "100",
        "Delta_Call": delta_c, "Delta_Put": delta_p,
    }


def _ok(item):
    """True if the row validates (accepted)."""
    res = osch.validate_items([item], "2026-06-08", "08/06/2026", "2026-06-10")
    return res.accepted_count == 1


# ── 2. Put delta boundaries / real values are valid ───────────────────────
def test_put_delta_zero_valid():       assert _ok(_item(delta_p="0"))
def test_put_delta_minus_100_valid():  assert _ok(_item(delta_p="-100"))
def test_put_delta_real_diag_value():  assert _ok(_item(delta_p="-9.01"))


# ── 3. Sign enforcement — the protection we must NOT lose ─────────────────
def test_put_positive_delta_rejected():  assert not _ok(_item(delta_p="50"))
def test_call_negative_delta_rejected(): assert not _ok(_item(delta_c="-50"))


# ── 4. Call delta boundaries ──────────────────────────────────────────────
def test_call_delta_zero_valid():     assert _ok(_item(delta_c="0"))
def test_call_delta_100_valid():      assert _ok(_item(delta_c="100"))
def test_call_delta_over_100_rejected(): assert not _ok(_item(delta_c="100.01"))
def test_call_delta_negative_rejected(): assert not _ok(_item(delta_c="-0.01"))


# ── Out-of-range put delta still rejected ─────────────────────────────────
def test_put_delta_below_minus_100_rejected(): assert not _ok(_item(delta_p="-100.01"))
