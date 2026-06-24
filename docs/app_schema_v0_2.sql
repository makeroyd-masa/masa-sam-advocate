-- ============================================================================
-- app_schema_v0_2.sql  |  Cost-share verification layer (delta on v0.1)
-- ----------------------------------------------------------------------------
-- Applied AFTER app_schema_v0_1.sql by scripts/init_app_db.py. ADDITIVE ONLY —
-- new columns + one new table; no rewrites of v0.1 objects. Spec: the cost-share
-- PRD addendum (docs/PRD_addendum_costshare_v0_1.md), v0.1 LITE scope.
-- PHI: member data stays in app.db (PRD §1.2, §8). Nothing here touches pilot.db.
-- ============================================================================

-- Per-claim cost-share breakdown the member can read off a transparent EOB.
-- All OPTIONAL. Powers the Flow 1 cost-share reconciliation (checks #1, #2, #5).
-- (total_allowed_cents already exists in the v0.1 bill_summaries.)
ALTER TABLE bill_summaries ADD COLUMN copay_cents              INTEGER;  -- flat copay
ALTER TABLE bill_summaries ADD COLUMN deductible_applied_cents INTEGER;  -- applied to deductible on THIS claim
ALTER TABLE bill_summaries ADD COLUMN coinsurance_cents        INTEGER;  -- member coinsurance amount
ALTER TABLE bill_summaries ADD COLUMN not_covered_cents        INTEGER;  -- "services not covered" column
ALTER TABLE bill_summaries ADD COLUMN discount_cents           INTEGER;  -- network discount / contractual write-off
ALTER TABLE bill_summaries ADD COLUMN coinsurance_rate_pct     REAL;     -- plan coinsurance %, member- or plan-sourced (check #2)

-- Forward-compat for the DEFERRED accumulator checks (#3 deductible
-- over-application, #4 charging past the OOP maximum). Present so the fast-follow
-- needs no second migration; NOT written by intake or read by any check in v0.1.
CREATE TABLE IF NOT EXISTS member_accumulators (
    accumulator_id   INTEGER PRIMARY KEY,
    case_id          INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    scope            TEXT NOT NULL CHECK (scope IN ('individual','family')),
    network          TEXT NOT NULL CHECK (network IN ('in_network','out_of_network')),
    bucket           TEXT NOT NULL CHECK (bucket IN ('deductible','oop_max')),
    accumulator_kind TEXT NOT NULL DEFAULT 'medical'
                     CHECK (accumulator_kind IN ('medical','pharmacy')),
    limit_cents      INTEGER,    -- plan limit
    applied_cents    INTEGER,    -- YTD applied
    remaining_cents  INTEGER,    -- YTD remaining
    plan_year        TEXT,       -- ISO year or plan-year label
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
