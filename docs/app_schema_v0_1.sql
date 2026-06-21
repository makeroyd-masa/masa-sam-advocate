-- ============================================================================
-- app.db — SAM Medical Bill Advocate (application tier)  |  schema v0.1
-- Companion to read-only pilot.db (reference data). Hand-off target: Claude Code
-- (masa-sam-advocate). Implements the case/state machine, intake stages 0–4,
-- Flow 2/3 engine outputs, the §5 CARC/RARC routing layer, and §7 answer cards.
--
-- CONVENTIONS
--   * Money is INTEGER cents (matches pilot.db). Never store floats for money.
--   * Timestamps are TEXT ISO-8601 UTC. Default via CURRENT_TIMESTAMP.
--   * pilot.db codes are stored as plain values (no cross-db FK); resolve at
--     query time against pilot.db. The two DBs are separate files.
--   * Enumerations are TEXT + CHECK for hand-off clarity and to document the
--     PRD vocabularies in one place.
--   * PHI/member-entered bill data lives ONLY here, never in pilot.db (PRD §1.2).
--   * No documents are stored (prototype has no upload/OCR) (PRD §1.1).
--   * Counsel/feature gating (NSA flag default-off, NCD approval gate) is
--     config-driven (YAML) at the app layer; this schema only RECORDS when gated
--     content was suppressed, for audit (see answer_cards.gated_content_note).
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- member_profile — OPTIONAL seed cache. Member identity/PII comes from the host
-- MASA app; we keep only an opaque ref plus a few fields used to pre-seed intake
-- (insurance situation, plan id). Keep this minimal.
-- ----------------------------------------------------------------------------
CREATE TABLE member_profile (
    member_ref            TEXT PRIMARY KEY,        -- opaque id from host app
    default_insurance_situation TEXT
        CHECK (default_insurance_situation IN
            ('medicare_ffs','medicare_advantage','commercial_aca',
             'employer_erisa','medicaid','self_pay')),
    plan_identifier       TEXT,                    -- e.g. HIOS / contract id if known
    updated_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- cases — the central entity. One row per advocacy case (one bill/claim issue).
-- The state machine lives here: current_stage + status + a JSON context blob for
-- transient machine state (e.g. which checkpoint has been shown).
-- Extensible: problem_type and active_flow carry future workflows so the
-- coverage-checker / file-claim / post-ER experiences slot in WITHOUT a schema
-- revision (PRD §3 broader set + your future-capability notes).
-- ----------------------------------------------------------------------------
CREATE TABLE cases (
    case_id          INTEGER PRIMARY KEY,
    member_ref       TEXT NOT NULL REFERENCES member_profile(member_ref),

    -- Axis 1 — Problem Type (PRD §3). Prototype set = first three; broader
    -- product + your future notes included so routing is future-proof.
    problem_type     TEXT
        CHECK (problem_type IN
            ('explain','error_overcharge','denial_appeal',          -- prototype
             'balance_bill','partial_payment','catastrophic','collections', -- broader
             'coverage_check','file_claim','post_er')),             -- future

    -- Axis 2 — Insurance Situation (primary) (PRD §3).
    insurance_situation TEXT
        CHECK (insurance_situation IN
            ('medicare_ffs','medicare_advantage','commercial_aca',
             'employer_erisa','medicaid','self_pay')),

    -- Which engine is currently active. Mapped: flow1=explain, flow2=error,
    -- flow3=appeal. Future workflows use their own value.
    active_flow      TEXT
        CHECK (active_flow IN
            ('flow1_explain','flow2_error','flow3_appeal',
             'coverage_check','file_claim','post_er','none')),

    -- State machine.
    current_stage    TEXT NOT NULL DEFAULT 'stage0_intent'
        CHECK (current_stage IN
            ('stage0_intent','stage1_insurance','stage2_bill','stage3_lines',
             'stage3alt_no_codes','stage4_ambulance','analysis','output','done')),
    status           TEXT NOT NULL DEFAULT 'intake'
        CHECK (status IN
            ('intake','awaiting_member_input','analyzing','complete',
             'escalated','handed_off','abandoned')),
    machine_context  TEXT,                          -- JSON: transient FSM state

    -- Universal-SAM / contextual entry (your UX direction). Records WHERE the
    -- case was launched from and what intent it was pre-seeded with, so the FAB
    -- and contextual entry points are first-class and measurable.
    entry_point      TEXT,                          -- e.g. 'fab_global','claims',
                                                    -- 'plan','payments','overview'
    seed_intent      TEXT,                          -- pre-seeded workflow, if any

    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_cases_member ON cases(member_ref);
CREATE INDEX idx_cases_status ON cases(status);

-- ----------------------------------------------------------------------------
-- case_events — append-only audit / state-transition log. Backs the funnel
-- instrumentation (completion, checkpoint take-rate) and provenance trail.
-- ----------------------------------------------------------------------------
CREATE TABLE case_events (
    event_id     INTEGER PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,                     -- 'stage_enter','stage_complete',
                                                    -- 'checkpoint_offered','checkpoint_accepted',
                                                    -- 'flow_started','finding_created',
                                                    -- 'card_rendered','handoff_requested', etc.
    from_stage   TEXT,
    to_stage     TEXT,
    detail       TEXT,                              -- JSON payload
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_events_case ON case_events(case_id);

-- ----------------------------------------------------------------------------
-- INTAKE STAGE 2 — bill-level capture (PRD §4.2). One row per case.
-- ----------------------------------------------------------------------------
CREATE TABLE bill_summaries (
    case_id                    INTEGER PRIMARY KEY
                               REFERENCES cases(case_id) ON DELETE CASCADE,
    provider_name              TEXT,
    date_of_service_start      TEXT,                -- ISO date
    date_of_service_end        TEXT,
    total_billed_cents         INTEGER,
    total_allowed_cents        INTEGER,             -- if member can read it
    total_plan_paid_cents      INTEGER,
    patient_responsibility_cents INTEGER,
    notes                      TEXT,
    created_at                 TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- INTAKE STAGE 3 — line-item capture (PRD §4.2). One row per bill line.
-- detected_code_type aligns to pilot.db code_type values. CPT is allowed as a
-- detected type even though descriptions aren't stored (numeric CPT still
-- resolves against NCCI + PFS, which are keyed by code number — PRD §2.1).
-- ----------------------------------------------------------------------------
CREATE TABLE bill_lines (
    line_id            INTEGER PRIMARY KEY,
    case_id            INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    line_no            INTEGER NOT NULL,            -- member-facing ordering
    raw_code           TEXT NOT NULL,
    detected_code_type TEXT
        CHECK (detected_code_type IN
            ('ICD10CM','ICD10PCS','HCPCS','CPT','CARC','RARC',
             'RevenueCode','MSDRG','POS','Modifier','NDC','unknown')),
    units              INTEGER,
    billed_charge_cents INTEGER,
    modifier           TEXT,
    encounter_pos      TEXT,                        -- POS code; drives PFS
                                                    -- facility vs non-facility column
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (case_id, line_no)
);
CREATE INDEX idx_lines_case ON bill_lines(case_id);

-- ----------------------------------------------------------------------------
-- Captured denial codes (CARC/RARC the member can read). The denial code is the
-- dispatcher between all three flows (PRD §5.1), so it is captured explicitly
-- and tracked by where it was seen (bill level vs a specific line).
-- ----------------------------------------------------------------------------
CREATE TABLE captured_denial_codes (
    id           INTEGER PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    code         TEXT NOT NULL,
    code_type    TEXT NOT NULL CHECK (code_type IN ('CARC','RARC')),
    where_seen   TEXT CHECK (where_seen IN ('bill_level','line')),
    line_id      INTEGER REFERENCES bill_lines(line_id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_denials_case ON captured_denial_codes(case_id);

-- ----------------------------------------------------------------------------
-- INTAKE STAGE 3-alt — itemized-bill-request workflow (PRD §4.2). For error
-- cases where the member has no itemized bill; we generate a request letter and
-- resume Flow 2 when the bill arrives.
-- ----------------------------------------------------------------------------
CREATE TABLE itemized_bill_requests (
    case_id        INTEGER PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    letter_status  TEXT NOT NULL DEFAULT 'draft'
        CHECK (letter_status IN ('draft','generated','sent','bill_received')),
    generated_at   TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- INTAKE STAGE 4 — ambulance appeal capture (PRD §4.2 / §6.3). One row per
-- appeal case. loaded_miles is member-optional; when null the dollar anchor is
-- computed from base rate only and labeled a floor.
-- SCOPE (v1 = GROUND ONLY): validate transport_hcpcs against the ground set —
-- LOS A0426,A0427,A0428,A0429,A0432,A0433,A0434 + A0425 (mileage). AIR codes
-- A0430 (fixed-wing) / A0431 (rotary-wing) (and air-mileage A0435/A0436) must
-- NOT enter this flow: route to the human-advocate handoff (insert into
-- `handoffs`, handoff_type='in_house_advocate') with neutral copy. Air ambulance
-- IS NSA-protected, so the ground honesty node must never render for air, and the
-- bot must not assert NSA protections in automated copy (4c counsel gate). Air is
-- a future flagged unlock. See PRD §6.3 / §10 #11/#11a.
-- ----------------------------------------------------------------------------
CREATE TABLE ambulance_claims (
    case_id              INTEGER PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    transport_hcpcs      TEXT,                      -- ground LOS code (v1); air codes routed out at intake
    transport_modifier   TEXT,
    denial_letter_date   TEXT,                      -- ISO date
    is_emergency         INTEGER CHECK (is_emergency IN (0,1)),
    origin               TEXT,
    destination          TEXT,
    loaded_miles         REAL,                      -- nullable; optional intake
    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- code_explanations — the §5 curated CARC/RARC plain-English + routing layer.
-- Hand-authored YAML (config/carc_rarc_plain_english.yaml) loaded here on
-- deploy for fast joins. Claude Code builds the loader + router, NOT the text.
-- This is the table the routing layer reads.
-- ----------------------------------------------------------------------------
CREATE TABLE code_explanations (
    code               TEXT NOT NULL,
    code_type          TEXT NOT NULL CHECK (code_type IN ('CARC','RARC')),
    official_text      TEXT,                        -- raw X12/WPC wording (from pilot.db)
    plain_explanation  TEXT NOT NULL,               -- member-facing meaning
    practical_meaning  TEXT,                        -- what it usually signals
    commonly_disputable INTEGER NOT NULL DEFAULT 0
        CHECK (commonly_disputable IN (0,1)),
    suggested_action   TEXT NOT NULL
        CHECK (suggested_action IN
            ('explain_only','error_check','appeal',
             'verify_with_payer','escalate_human')),
    rank_frequency     INTEGER,                     -- nullable; populated when a
                                                    -- frequency source is chosen
    reviewed           INTEGER NOT NULL DEFAULT 0   -- content review gate
        CHECK (reviewed IN (0,1)),
    PRIMARY KEY (code, code_type)
);

-- ----------------------------------------------------------------------------
-- FLOW 2 — error/overcharge findings (PRD §6.2). One row per finding; three
-- independent check types kept distinct, plus the facility-unbenchmarked log
-- line so coverage of un-benchmarkable facility spend is measurable.
-- ----------------------------------------------------------------------------
CREATE TABLE flow2_findings (
    finding_id          INTEGER PRIMARY KEY,
    case_id             INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    finding_type        TEXT NOT NULL
        CHECK (finding_type IN
            ('unbundling_ptp','quantity_mue','price_benchmark','facility_unbenchmarked')),

    -- implicated line(s). For PTP, two lines pair up (line_id + paired_line_id).
    line_id             INTEGER REFERENCES bill_lines(line_id) ON DELETE CASCADE,
    paired_line_id      INTEGER REFERENCES bill_lines(line_id) ON DELETE CASCADE,

    -- unbundling specifics
    ptp_modifier_indicator INTEGER CHECK (ptp_modifier_indicator IN (0,1,9)),

    -- quantity specifics
    mue_cap             INTEGER,
    units_over_cap      INTEGER,

    -- price-benchmark specifics
    pfs_setting         TEXT CHECK (pfs_setting IN ('facility','non_facility')),
    benchmark_cents     INTEGER,                    -- Medicare rate used
    billed_multiple     REAL,                       -- billed ÷ benchmark
    benchmark_tier      TEXT
        CHECK (benchmark_tier IN
            ('below_threshold','higher_side','solid_leverage','strong_leverage')),

    -- savings classification (PRD §6.2 two tiers)
    savings_class       TEXT NOT NULL
        CHECK (savings_class IN ('likely_error_recoverable','above_benchmark_leverage')),
    recoverable_cents   INTEGER,                    -- for likely_error rows
    framing             TEXT NOT NULL DEFAULT 'likely', -- always "appears to/likely"
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_findings_case ON flow2_findings(case_id);

-- ----------------------------------------------------------------------------
-- FLOW 3 — appeal package (PRD §6.3). One row per appeal case.
-- ----------------------------------------------------------------------------
CREATE TABLE flow3_appeals (
    case_id            INTEGER PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
    segment            TEXT NOT NULL
        CHECK (segment IN ('medicare_ffs','medicare_advantage','commercial_aca')),
    ncd_weight         TEXT NOT NULL CHECK (ncd_weight IN ('binding','persuasive')),
    denial_basis       TEXT,                        -- classified denial reason

    -- pathway / deadline (resolved against pilot.db appeal-level tables)
    appeal_level_ref   TEXT,                        -- which level row was selected
    filing_deadline    TEXT,                        -- ISO date; always caveated
    deadline_caveat_shown INTEGER NOT NULL DEFAULT 1 CHECK (deadline_caveat_shown IN (0,1)),

    -- dollar anchor (base + per-mile × loaded_miles); floor if miles null
    base_rate_cents    INTEGER,
    per_mile_rate_cents INTEGER,
    loaded_miles_used  REAL,
    reasonable_amount_cents INTEGER,                -- full anchor (or floor)
    anchor_is_floor    INTEGER NOT NULL DEFAULT 0 CHECK (anchor_is_floor IN (0,1)),
    gap_to_anchor_cents INTEGER,                    -- partial-payment case

    -- generated letter — counsel gate (PRD §8)
    letter_status      TEXT NOT NULL DEFAULT 'draft'
        CHECK (letter_status IN
            ('draft','pending_counsel_review','counsel_approved','sent')),
    nsa_content_suppressed INTEGER NOT NULL DEFAULT 1  -- NSA flag default-off
        CHECK (nsa_content_suppressed IN (0,1)),
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- appeal_citations — the NCD criteria / appeal-level / fee-schedule references an
-- appeal relies on. Only reviewed/approved NCD rows back user-facing content
-- (PRD §6.3 gate); record which were used for provenance + audit.
CREATE TABLE appeal_citations (
    id            INTEGER PRIMARY KEY,
    case_id       INTEGER NOT NULL REFERENCES flow3_appeals(case_id) ON DELETE CASCADE,
    source_type   TEXT NOT NULL
        CHECK (source_type IN ('ncd','medicare_appeal_level','commercial_appeal_level',
                               'ambulance_fs','nsa_rule')),
    source_ref    TEXT NOT NULL,                    -- pilot.db row identifier
    was_approved  INTEGER CHECK (was_approved IN (0,1)),  -- review gate state at use
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- answer_cards — the §7 universal output structure. One row per rendered card
-- (cases can produce several across a session). card_citations holds provenance.
-- ----------------------------------------------------------------------------
CREATE TABLE answer_cards (
    card_id            INTEGER PRIMARY KEY,
    case_id            INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    flow               TEXT
        CHECK (flow IN ('flow1_explain','flow2_error','flow3_appeal',
                        'coverage_check','file_claim','post_er')),
    headline           TEXT NOT NULL,               -- §7.1 one sentence
    number_cents       INTEGER,                     -- §7.2 the number (if any)
    number_label       TEXT,                        -- e.g. 'recoverable','gap','exposure'
    why_text           TEXT,                        -- §7.3 plain-English reasoning
    next_action        TEXT,                        -- §7.5 exactly one step
    framing            TEXT NOT NULL DEFAULT 'likely',-- §7.6
    escalation_offered INTEGER NOT NULL DEFAULT 0 CHECK (escalation_offered IN (0,1)),
    gated_content_note TEXT,                         -- audit: what was suppressed
                                                     -- (NSA flag / unapproved NCD)
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_cards_case ON answer_cards(case_id);

CREATE TABLE card_citations (
    id           INTEGER PRIMARY KEY,
    card_id      INTEGER NOT NULL REFERENCES answer_cards(card_id) ON DELETE CASCADE,
    source_type  TEXT NOT NULL
        CHECK (source_type IN
            ('code_set','ncci_ptp','ncci_mue','pfs','ambulance_fs','ncd',
             'medicare_appeal_level','commercial_appeal_level','nsa_rule',
             'sbc_field','plan_attribute','code_explanation')),
    source_ref   TEXT NOT NULL,                     -- the specific code/edit/row
    display_text TEXT
);

-- ----------------------------------------------------------------------------
-- handoffs — in-house advocate escalation now; 3P case-manager handover later
-- (your future-capability notes). Generic enough for both without a revision.
-- ----------------------------------------------------------------------------
CREATE TABLE handoffs (
    handoff_id    INTEGER PRIMARY KEY,
    case_id       INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    handoff_type  TEXT NOT NULL
        CHECK (handoff_type IN ('in_house_advocate','third_party_case_manager')),
    partner       TEXT,                             -- e.g. 'wellthy' (future)
    status        TEXT NOT NULL DEFAULT 'requested'
        CHECK (status IN ('requested','accepted','in_progress','resolved','declined')),
    reason        TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_handoffs_case ON handoffs(case_id);

-- ----------------------------------------------------------------------------
-- VIEW — per-case savings rollup for the §7 answer card (two honest tiers).
-- ----------------------------------------------------------------------------
CREATE VIEW v_case_savings AS
SELECT
    case_id,
    SUM(CASE WHEN savings_class = 'likely_error_recoverable'
             THEN COALESCE(recoverable_cents,0) ELSE 0 END) AS recoverable_cents,
    SUM(CASE WHEN savings_class = 'above_benchmark_leverage' THEN 1 ELSE 0 END)
             AS leverage_line_count
FROM flow2_findings
GROUP BY case_id;
