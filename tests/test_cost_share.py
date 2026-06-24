"""Cost-share verification checks (PRD addendum: cost-share v0.1, LITE scope).

Pure-function tests over the two real EOBs in docs/ — no pilot.db needed.
  * docs/full_eob_example.pdf p.3 (hospital): parts $1,425.45 vs owed $1,485.45 → flag.
  * docs/eob_table_example.png (office visit): $30 copay, consistent → no flag.
"""

from app.flows import cost_share


# --- #1 reconciliation ------------------------------------------------------
def test_reconciliation_gap_flagged():
    bill = {
        "copay_cents": 10000, "deductible_applied_cents": 20038,
        "coinsurance_cents": 112507, "not_covered_cents": 0,
        "patient_responsibility_cents": 148545,   # parts sum to 142545 → $60 gap
    }
    findings, flagged = cost_share.check(bill, "employer_erisa")
    assert flagged
    assert any("don't add up" in f.title for f in findings)
    assert any("$60.00" in f.text for f in findings)


def test_reconciliation_clean_copay_no_flag():
    bill = {
        "copay_cents": 3000, "deductible_applied_cents": 0,
        "coinsurance_cents": 0, "not_covered_cents": 0,
        "patient_responsibility_cents": 3000,
    }
    findings, flagged = cost_share.check(bill, "commercial_aca")
    assert not flagged
    assert findings == []


def test_partial_breakdown_does_not_flag():
    # Only copay entered → incomplete breakdown; reconciliation must not run.
    bill = {"copay_cents": 3000, "patient_responsibility_cents": 3000}
    findings, flagged = cost_share.check(bill, "employer_erisa")
    assert not flagged


# --- scope guard ------------------------------------------------------------
def test_non_insured_situations_skip():
    bill = {"copay_cents": 1, "deductible_applied_cents": 0, "coinsurance_cents": 0,
            "not_covered_cents": 0, "patient_responsibility_cents": 999}
    for sit in ("self_pay", "medicare_ffs", "medicaid", "medicare_advantage", None):
        findings, flagged = cost_share.check(bill, sit)
        assert findings == [] and not flagged


def test_none_bill_returns_empty():
    assert cost_share.check(None, "employer_erisa") == ([], False)


# --- #2 coinsurance rate ----------------------------------------------------
def test_coinsurance_rate_mismatch_flagged():
    # 20% of (5764.66 − 200.38) ≈ $1,112.86, but $1,500.00 shown.
    bill = {"coinsurance_rate_pct": 20, "total_allowed_cents": 576466,
            "deductible_applied_cents": 20038, "coinsurance_cents": 150000}
    findings, flagged = cost_share.check(bill, "employer_erisa")
    assert flagged
    assert any("20%" in f.title for f in findings)


def test_coinsurance_rate_within_tolerance_ok():
    # expected ≈ $1,112.86; shown $1,112.90 → within the $1 slack.
    bill = {"coinsurance_rate_pct": 20, "total_allowed_cents": 576466,
            "deductible_applied_cents": 20038, "coinsurance_cents": 111290}
    findings, flagged = cost_share.check(bill, "employer_erisa")
    assert not flagged


# --- #5 not-covered routing -------------------------------------------------
def test_not_covered_routes_when_no_denial():
    findings, flagged = cost_share.check({"not_covered_cents": 5000}, "employer_erisa")
    assert any("not covered" in f.title.lower() for f in findings)
    assert not flagged  # a routing nudge, not an arithmetic error


def test_not_covered_suppressed_when_denial_present():
    findings, _ = cost_share.check(
        {"not_covered_cents": 5000}, "employer_erisa", has_denial_code=True
    )
    assert findings == []
