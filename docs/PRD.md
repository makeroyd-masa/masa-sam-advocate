# SAM Medical Bill Advocate — Prototype PRD

**Version:** v0.3.2 (draft for review)
**Prepared for:** Claude Code build (`masa-sam-advocate`)
**Status:** Draft — third pass + screen fold-in + air/ground scope correction. v0.2 decisions carried forward; data figures corrected against the verified pilot overview; the app schema, CARC/RARC routing layer, SAM interaction model, and the v0.1 screen set are specified and pointed at canonical artifacts. Remaining gates are in §10.
**Changelog v0.3.1 → v0.3.2:**
- **Air vs. ground scope corrected (§4.2, §6.3, §9, §10).** The ambulance fee schedule's A0425–A0434 set is **not** all ground: **A0430 (fixed-wing) and A0431 (rotary-wing) are air-ambulance codes.** Air ambulance **is** NSA-protected; ground is the carve-out — so the ground "not-NSA-protected" honesty node must never render for an air transport. Flow 3 v1 is now defined as **ground-only**: LOS codes **A0426, A0427, A0428, A0429, A0432, A0433, A0434 + A0425 mileage**. Air codes are detected and routed to the human-advocate handoff with neutral copy; the bot does not assert NSA protections (those stay behind the 4c counsel gate). The air branch is built as a stub seam for a future flagged unlock. Known data limit recorded: air-mileage codes **A0435/A0436 are not in `ambulance_fee_schedule`**, so an air anchor would be base-only regardless.

**Changelog v0.3 → v0.3.1:**
- **Screen set folded in (§1.3, new §1.4, §9, §10):** the v0.1 screen mockups are delivered as `SAM_screens_v0_1.html` and summarized in the new §1.4 (eleven frames, each mapped to its stage and `app.db` write). §1.3 now points to the delivered file rather than a forthcoming one; §10b moves to resolved (v0.1 delivered; visual sign-off / member testing still open for iteration).

**Changelog v0.2 → v0.3:**
- **Data figures corrected** against the verified Project Overview (queried `pilot.db` 2026-06-20). §2 table updated: `ma_plans` is **6,030** (plan×state, not the 137,714 pre-collapse county count); NCCI PTP is **2,633,128 total / 1,728,585 active** (Flow 2 queries the active subset); ambulance fee schedule is **A0425–A0434** (see §6.3 for the ground/air split, corrected in v0.3.2); ACA `plans` is **5,486**.
- **NCD 10.1 resolved (§2.1, §6.3, §10 #4b):** `ncd_ambulance` is **35 rows, all `reviewed=1`**. Flow 3's medical-necessity gate is effectively open today. The earlier "40 rows / review-pending" language is removed.
- **App schema specified (§9):** the `app.db` case/state schema is now an artifact — `app_schema_v0_1.sql` — referenced as canonical instead of described abstractly.
- **CARC/RARC routing layer specified (§5, §9):** the curation is an artifact — `carc_rarc_plain_english.yaml` (50 CARC + 30 RARC, `suggested_action` mapping populated; member-facing copy authored separately per §5.3). Two routing exceptions locked: **CARC 45 is `insurance_situation`-aware** (contractual write-off for insured vs. negotiation leverage for self-pay/balance-bill), **CARC 29 (timely filing) is verify-then-escalate**, not a medical-necessity appeal.
- **SAM interaction model added (§1.3):** no dedicated SAM page; universal SAM via a persistent FAB plus contextual entry points; the active flow renders as a **bottom-sheet that expands to near-full** for line-item entry. Screen mockups are a companion design artifact (referenced, not embedded).
**Inherits from:** Data Ingestion Layer PRD v1.1 (`pilot.db`) and the app-layer interaction model in `PRD.md`. This document specifies the *application* prototype, not the data pipeline.

---

## 1. What this prototype is

A member-facing, guided advocacy tool that helps MASA members understand, audit, and dispute medical bills and ambulance claim denials. The prototype is built to be **theoretically go-live-able**: real data, real workflows, real document output — with bill upload, OCR, and a private medical-data LLM deferred to a later phase and replaced for now by **structured, guided manual entry**.

The prototype scopes **three flows**:

1. **Flow 1 — Bill / EOB explanation** (commodity, offered free): plain-English interpretation of codes and bill-level totals.
2. **Flow 2 — Error / overcharge detection + savings** (the differentiator vs. Solomon Copilot): rule-based billing-error detection plus a Medicare-benchmark "× Medicare" savings signal.
3. **Flow 3 — Ambulance primary-claim denial appeal** (the MASA wedge): denial-reason triage, medical-necessity grounding, appeal-pathway routing, and generated appeal-document output.

### 1.1 Non-goals for the prototype

- No document upload, no OCR, no PHI-bearing LLM. Intake is structured manual entry only.
- No open-ended chatbot. Chat is the interface skin; the engine is a deterministic, case-anchored guided flow. A member message that does not map to a workflow is redirected to the available actions, not improvised on.
- No per-line *dollar* reconciliation in Flow 1 (bill-level only). Per-line capture is introduced deliberately in Flow 2 — see §4.
- No facility-side price benchmarking (OPPS / ASC / CLFS / DME). The Medicare benchmark in Flow 2 covers professional/physician lines only — see §6.2.

### 1.2 Architecture context

- **Two repos.** `medical_billing_data` produces `pilot.db` (read-only reference data). `masa-sam-advocate` is the application; it reads `pilot.db` and persists case state to a separate writable `app.db` (schema: `app_schema_v0_1.sql`, §9).
- **Stack.** FastAPI + Python 3.12 backend; React 18 + TypeScript + Vite frontend; SQLite. YAML config for escalation, pricing thresholds, and the code-explanation layer (§5).
- **PHI posture.** No PHI is written to `pilot.db`. Member-entered bill details live in `app.db` case records in the application tier only. The prototype never stores uploaded documents (there are none).

### 1.3 Interaction model — universal SAM (new in v0.3)

SAM has **no dedicated page.** A standalone SAM destination risks low engagement ("members don't know what they don't know"), so SAM is surfaced universally with contextual entry:

- **Persistent FAB.** A floating action button (bottom-right, always visible) opens SAM with the full capability set from anywhere in the app.
- **Contextual entry points.** Where SAM is invoked pre-seeds the workflow. Examples: from **Claims**, "help me file a new claim" / appeal; from **Plan / plan documents**, "ask SAM if you're covered" (coverage checker, future); from **Payments**, bill explanation / overcharge check. The launch surface and pre-seeded intent are captured per-case (`cases.entry_point`, `cases.seed_intent`) so contextual launches are first-class and measurable.
- **Surface behavior.** The active flow renders as a **bottom-sheet** for entry and the §4 checkpoint, **expanding to near-full** when the member commits to line-item entry (Stage 3) or the ambulance appeal capture (Stage 4) — heavier entry earns more screen, lighter interaction stays unobtrusive.
- **Forward compatibility.** The same router/surface accommodates the roadmap experiences (medical-bill-advocacy human handover, coverage checker, claims support, post-ER coordination) without a UX re-cut. The schema (`problem_type`, `active_flow`, `handoffs`) already carries these.

Screen mockups (FAB/contextual entry, Stage 0–4 card states, 3-alt, and the answer cards) are delivered as the companion artifact **`SAM_screens_v0_1.html`** and summarized in §1.4. They are drawn on the existing MASA app surfaces using the official brand tokens (Horizon `#230871` for advocate actions, Tide `#0071CE` for leverage/secondary, Flare `#E64B38` reserved for links and escalation, Shine `#FFD040` for honesty/caution nodes; Poppins + Open Sans).

### 1.4 Screen inventory & state mapping (v0.1)

Eleven frames in three groups. Each state ties to a stage (§4) / flow (§6) and the `app.db` object it reads or writes — this is the UI-to-schema contract for the build.

| # | Screen | Maps to | `app.db` |
|---|---|---|---|
| 1 | Contextual FAB (on Claims) | §1.3 universal entry | writes `cases.entry_point` |
| 2 | SAM launcher (FAB tapped) | §1.3 capability set + contextual seed | creates `cases`; writes `seed_intent` |
| 3 | Stage 0 — Intent checkpoint (sheet) | §4.2 Stage 0 | writes `cases.problem_type` |
| 4 | Stage 1 — Insurance situation (sheet) | §4.2 Stage 1 | writes `insurance_situation`, `plan_identifier` |
| 5 | Stage 2 — Bill-level capture (sheet) | §4.2 Stage 2 | writes `bill_summaries`, `captured_denial_codes` |
| 6 | Stage 3 — Line-item capture (near-full) | §4.2 Stage 3 | writes `bill_lines` |
| 7 | Stage 3-alt — No-codes path (sheet) | §4.2 Stage 3-alt | writes `itemized_bill_requests` |
| 8 | Stage 4 — Ambulance appeal capture (near-full) | §4.2 Stage 4 | writes `ambulance_claims` |
| 9 | Flow 1 — Explanation + checkpoint card | §6.1 / §7 | reads `code_explanations`, `sbc_fields` → `answer_cards` |
| 10 | Flow 2 — Two-tier savings card | §6.2 / §7 | reads `ncci_ptp_edits`/`ncci_mue`/`physician_fee_schedule` → `flow2_findings` |
| 11 | Flow 3 — Appeal package card | §6.3 / §7 | reads `ncd_ambulance`/`*_appeal_levels`/`ambulance_fee_schedule` → `flow3_appeals` |

**Surface heights:** sheet at ~74% for entry/checkpoint stages (0–2, 3-alt); ~93% ("near-full") for Stage 3 and Stage 4 line/claim entry and for the answer cards. **Intake affordances shown:** inline code-type auto-detect chip and "add another line" (Stage 3); optional loaded-mileage field with floor-vs-full explanation as an inline honesty node (Stage 4). **Answer cards** render the §7 structure verbatim (eyebrow + headline → the number → why-with-citations → one primary action → "appears to / likely" framing line → human-advocate escalation); Flow 2 shows the two honest tiers side-by-side (recoverable error $ vs. ×-Medicare leverage), Flow 3 leads with the base-plus-mileage anchor and carries the ground-ambulance / NSA carve-out honesty node. Sample data is illustrative, not authored copy.

---

## 2. Data coverage (corrected, as of 2026-06-20)

Every flow below is backed by data already in `pilot.db`. This table is the authoritative coverage snapshot; figures are reconciled to the verified Project Overview and supersede earlier status documents.

| Reference data | `pilot.db` object | Volume | Serves |
|---|---|---|---|
| ICD-10-CM diagnosis codes | `codes` (ICD10CM) | 97,584 | Flow 1 |
| ICD-10-PCS procedure codes | `codes` (ICD10PCS) | 78,986 | Flow 1 |
| HCPCS Level II (incl. ambulance) | `codes` (HCPCS) | 8,846 | Flows 1–3 |
| CARC denial/adjustment codes | `codes` (CARC) | 308 | Flows 1–3 (trigger) |
| RARC remark codes | `codes` (RARC) | 1,198 | Flows 1–3 (trigger) |
| Revenue codes | `codes` (RevenueCode) | 196 | Flow 1 |
| MS-DRG groups | `codes` (MSDRG) | 771 | Flow 1 |
| Place of Service | `codes` (POS) | 53 | Flows 1–2 (column selection) |
| Modifiers | `codes` (Modifier) | 383 | Flows 1–2 |
| FDA NDC products | `codes` (NDC) | 113,516 | Flow 1 |
| **NCCI PTP edits** | `ncci_ptp_edits` | **2,633,128 total / 1,728,585 active (2026 Q3)** — query the active subset | Flow 2 (unbundling) |
| **NCCI MUE caps** | `ncci_mue` | **15,162 codes (2026 Q3)** | Flow 2 (quantity) |
| **Medicare Physician Fee Schedule** | `physician_fee_schedule` | **9,135 rows / 7,481 unique HCPCS/CPT** (national median non-facility + facility, integer cents) | Flow 2 (savings benchmark) |
| Ambulance fee schedule | `ambulance_fee_schedule` | **520 rows — 10 HCPCS (A0425–A0434) × 52 geo areas** (50 states + DC + PR), integer cents, state-level median | Flow 3 (dollar anchor) |
| Medicare Advantage landscape | `ma_plans` | **6,030 plan×state (CY2026)** — collapsed from 137,714 county rows | Flows 1–3 (plan ID) |
| NCD 10.1 ambulance criteria | `ncd_ambulance` | **35 rows, all `reviewed=1`** (6 covered, 4 non-covered, 2 conditional, 23 informational) | Flow 3 (medical necessity) |
| Medicare appeals framework | `medicare_appeal_levels` | 6 rows (5-level + MA variant) | Flow 3 |
| Commercial/ACA appeals framework | `commercial_appeal_levels` | 4 rows | Flow 3 |
| NSA / GFE / PPDR / ground-ambulance rules | `nsa_rules` | 59 rows, Tables A–K (**all `draft`, not counsel-approved**) | Flow 3 (carve-out logic) |
| SBC structured fields | `sbc_documents` / `sbc_fields` | 2,384 docs / 22,886 fields (2,278 fully parsed) | Flow 1–2 (ACA plan-term checks) |
| ACA marketplace plans | `plans` + attributes/benefits | **5,486 plans** (FFE/SBE-FP + Covered CA + SADP dental); 1.6M benefit rows | Flow 1–2 (ACA members) |

**Net coverage statement:** Flow 2's error-detection signal is complete (full NCCI PTP + MUE) and its savings signal is live (PFS). Nothing in any of the three flows is blocked on missing reference data. With NCD 10.1 fully reviewed, Flow 3's medical-necessity grounding is review-clean. Remaining limits are scope choices (professional-line-only benchmark, national-median rates) and one process gate (counsel review of NSA-citing content and of generated appeal-letter framing), both specified below.

### 2.1 Known data limits the copy must respect

- **CPT is detection-only.** CPT descriptors are not stored (AMA license). CPT-coded lines return a category fallback. Numeric CPT codes still resolve against NCCI and PFS because those tables are keyed by code number, not description.
- **PFS is national median, not locality-adjusted.** Output frames findings as a *multiple* ("≈6× the Medicare benchmark"), which is robust to locality even when the exact dollar is not. ZIP-level precision is a later re-aggregation of the ~995K carrier×locality rows already collected, not a new ingestion.
- **PFS prices professional lines only.** Hospital outpatient (OPPS/APC), ambulatory surgery (ASC), clinical lab (CLFS), and DME (DMEPOS) are not benchmarked. Facility/revenue-code lines do not resolve against PFS. Savings copy must scope itself accordingly (§6.2).
- **Medicare Advantage benefit depth is thin.** `ma_plans` is plan landscape (premium, county, star rating), not plan-benefit-package cost-sharing. There is no MA SBC/EOC corpus. The richest plan-term data (SBC, marketplace PUFs) is ACA individual-market only. Because the member base skews 55+ Medicare/MA, Flow 1's "why did I owe this exact amount" depth is limited for MA members; Flows 2–3 are insulated because NCCI, PFS, and the ambulance fee schedule are payer-agnostic Medicare references.
- **NCD 10.1 is fully reviewed.** All 35 `ncd_ambulance` rows are `reviewed=1`, so the Flow 3 medical-necessity grounding is go-live-ready on the data side. The remaining Flow 3 go-live gate is app-layer (counsel review of generated appeal-letter framing, §8), not data.

---

## 3. Triage model (two axes)

Triage classifies every case on two axes before any workflow runs:

- **Axis 1 — Problem Type:** explain / error-or-overcharge / denial-appeal (prototype set; the broader product also has balance-bill, partial-payment, catastrophic, collections; the roadmap adds coverage-check, file-claim, post-ER — all carried in the schema `problem_type` enum).
- **Axis 2 — Insurance Situation (primary):** Medicare FFS · Medicare Advantage · Commercial/ACA · Employer (ERISA) · Medicaid · Uninsured/self-pay.

Insurance Situation can short-circuit routing: **Medicaid always routes to the Medicaid pathway (Workflow 5)** regardless of problem type, and **self-pay routes the price-dispute path toward GFE/PPDR** rather than the insured appeal flows. Both axes are captured in intake (§4) and can also be set by the denial code itself: a CARC/RARC parsed in intake can pre-fill Problem Type via the §5 `suggested_action` router (e.g., a medical-necessity denial code pre-selects the appeal path).

---

## 4. Intake design — the checkpoint pattern

Intake is the heart of this prototype because UC1 and UC2 have fundamentally different data costs: explanation works off bill-level totals and whatever codes the member can read, while error/overcharge detection requires **per-line code + units + billed charge**. Forcing every member through full line-item entry would crush completion in a 55+ population; skipping it would gut the differentiator. The resolution is a **checkpoint** that lets the member opt into depth only when the payoff (a dollar figure) justifies the extra entry.

On the **surface** (§1.3): Stages 0–2 and the checkpoint live in the bottom-sheet; selecting error/overcharge detection (Stage 3) or the ambulance appeal capture (Stage 4) expands the sheet to near-full to support per-line entry.

### 4.1 Two entry points, one convergence

The checkpoint is offered **both** upfront and progressively, and both paths converge on the same per-line intake when error/overcharge detection is selected:

- **Upfront:** the case-start intent question lets a member who already knows they want the full audit go straight to line-item entry.
- **Progressive (default narrative):** a member who just wants to understand the bill gets the explanation first (fast, free, low-friction), and is then offered the checkpoint *after* seeing value: "Want me to check this bill for billing errors and overcharges? I'll need a few details from each line — most people find at least one thing worth disputing." This reframes the heavier entry as earned, not as a wall.

### 4.2 Intake stages

| Stage | When | Captures | Backs |
|---|---|---|---|
| **0 — Intent checkpoint** | Always, at case start | What the member wants: *Understand my bill* / *Check it for errors & overcharges* / *Appeal a denied ambulance claim* | Axis 1 (Problem Type) |
| **1 — Insurance situation** | Always | Medicare FFS / MA / Commercial-ACA / Employer / Medicaid / Self-pay; plan identifiers if known | Axis 2; routing + short-circuits |
| **2 — Bill-level capture** | Always | Provider, date(s) of service, total billed, total plan-paid, patient responsibility; any denial codes (CARC/RARC) the member can read | Flow 1 reconciliation; CARC/RARC trigger (§5) |
| **3 — Line-item capture** | Only if error/overcharge selected (upfront or via the post-explanation checkpoint) | **Per line:** code (+ auto-detected code type), units/quantity, billed charge, modifier if present; encounter POS | Flow 2 (NCCI needs the pair + units; PFS needs the charge) |
| **3-alt — No codes path** | If the member selects error-check but has no itemized bill | Route to the itemized-bill-request workflow (generate the request letter, then resume Flow 2 when the bill arrives) | Flow 2 prerequisite |
| **4 — Ambulance appeal capture** | Only if denial-appeal selected | Transport HCPCS + modifier, denial code(s) (CARC/RARC) + denial-letter date, emergency vs. non-emergency, origin/destination, and **loaded mileage** (member-optional, see below) | Flow 3 (medical-necessity grounding + dollar anchor) |

Design requirements for Stage 3: one line at a time with an explicit "add another line" affordance; partial entry allowed; inline code-type auto-detection from format; and a graceful exit to 3-alt when the member can't supply codes. The intake is a state machine in `app.db` keyed to the case (`cases.current_stage` + `machine_context`), so a member can leave and resume.

**Loaded mileage (Stage 4).** The Medicare reasonable amount for a transport is the base rate for the level of service *plus* a per-mile mileage rate × the loaded miles (the miles the patient was actually transported). Intake asks for loaded miles but treats it as optional and explains why it matters: if the member has it (often on the bill or run sheet), the dollar anchor is the full reasonable amount; if they don't, the engine computes from the base rate only and labels the figure as a floor ("at least $X — likely more once mileage is added"). The member is never blocked on a number they may not have.

**Transport-code validation (Stage 4) — ground/air split.** Flow 3 v1 is **ground-only.** Validate the entered transport HCPCS against the ground set: LOS codes **A0426, A0427, A0428, A0429, A0432, A0433, A0434**, plus **A0425** (ground mileage). If the member enters an **air** code — **A0430 (fixed-wing)** or **A0431 (rotary-wing)**, or the air-mileage codes **A0435/A0436** — do **not** proceed into the ground appeal flow: route to the human-advocate handoff (`escalate_human`) with neutral, accurate copy (e.g., "air ambulance is handled differently and may involve federal protections — let me connect you with an advocate"). The bot must **not** assert NSA protections in automated copy; air NSA-citing content stays behind the 4c counsel gate. Build the air branch as a stub seam now so it can be unlocked behind a flag later. Note: A0430/A0431 base rates exist in `ambulance_fee_schedule`, but air-mileage codes A0435/A0436 do **not**, so an air dollar anchor would be base-only regardless (see §10).

### 4.3 Why this respects the product principle

Every interaction still resolves to a concrete next action and, where applicable, a dollar figure. Flow 1 ends in an explanation + the *offer* to find money; Flow 2 ends in a savings figure + the specific dispute action. The checkpoint is the seam between "free clarity" and "found dollars," and it is the natural place to surface the value proposition.

---

## 5. CARC/RARC plain-English layer (critical component)

### 5.1 Why it is load-bearing

Raw CARC (308) and RARC (1,198) text is X12/WPC adjuster jargon — accurate but unreadable to a member. More importantly, the denial/adjustment code is the **dispatcher between all three flows**: it is simultaneously the thing the member needs explained (Flow 1), the signal that a charge may be a recoverable error (Flow 2), and the trigger that opens an appeal with a specific medical-necessity or procedural basis (Flow 3). A curated plain-English layer is therefore not cosmetic copy — it is the routing intelligence that connects explanation to action.

### 5.2 Specification

A curated, human-authored, reviewed translation asset layered over the raw `pilot.db` codes.

- **Source of truth:** `config/carc_rarc_plain_english.yaml` in `masa-sam-advocate` (canonical skeleton: `carc_rarc_plain_english.yaml`, §9), loaded into an `app.db` table `code_explanations` on deploy for fast joins. Authored against the raw `pilot.db` CARC/RARC text (join key = `code`).
- **Coverage (v1):** top 50 CARC + top 30 RARC, matching the Data PRD's ≥95% denial-code explanation metric. The long tail falls back to the official wording, clearly labeled as the payer's exact language.
- **Frequency basis:** the v0.1 `rank_frequency` ordering is grounded in the established revenue-cycle denial-index literature (head) and standard-commonality (tail). It is to be re-validated against a current published source or MASA's own denial data before lock — only the order changes, not the routing (see §10).
- **Per-entry schema:**

| Field | Purpose |
|---|---|
| `code`, `code_type` | Join key to `pilot.db` |
| `official_text` | The raw X12/WPC wording (joined from `pilot.db` at load), shown as "the official reason" |
| `plain_explanation` | Member-facing plain-English meaning (**authored + reviewed**, §5.3) |
| `practical_meaning` | What it usually signals in practice (**authored + reviewed**, §5.3) |
| `commonly_disputable` | Boolean — is this a code members frequently and successfully challenge |
| `suggested_action` | Enum routing the member onward: `explain_only` / `error_check` (→ Flow 2) / `appeal` (→ Flow 3) / `verify_with_payer` / `escalate_human` |
| `rank_frequency` | Within-type rank (CARC 1–50, RARC 1–30); re-validated per §10 |
| `reviewed` | Content review gate for the authored copy |

- **Routing taxonomy (semantic bucket → default action):** auth/precert-absent · medical-necessity · experimental · coverage-guidelines → `appeal`; bundling/included/sequencing · duplicate · quantity-exceeds · coding-inconsistency (dx/px/modifier/POS) → `error_check`; missing-info · COB/wrong-payer · coverage-terminated/not-eligible · timely-filing → `verify_with_payer`; deductible/coinsurance/copay · contractual write-off · benefit-max → `explain_only`.
- **Locked routing exceptions (v0.3):**
  - **CARC 45 (charge exceeds fee schedule)** is **`insurance_situation`-aware.** For insured members it is the contractual write-off they do not owe (`explain_only` framing). For self-pay / balance-bill members the same code is real negotiation leverage and surfaces accordingly. The router must read `insurance_situation`; do not treat 45 as universally benign.
  - **CARC 29 (timely-filing limit expired)** routes **verify-then-escalate** (`verify_with_payer`, escalate if the member was actually billed), **not** a medical-necessity appeal — it is generally the provider's failure and the member should not owe.

### 5.3 Build note

This is a content artifact with an engineering wrapper. The YAML's **routing fields** (`suggested_action`, `commonly_disputable`, `rank_frequency`) are populated in the v0.1 skeleton. The **member-facing copy** (`plain_explanation`, `practical_meaning`) is hand-authored and review-gated like the NSA ruleset workbook and is intentionally left blank for the content team. Claude Code builds the loader, the `code_explanations` table, and the `suggested_action` → workflow router, but should **not** auto-generate the explanation text. v1.1 enhancement (out of scope here): curated handling of common CARC+RARC *combinations*, which EOBs frequently pair.

---

## 6. The three flows

### 6.1 Flow 1 — Bill / EOB explanation

**Input (from intake stages 0–2):** any supported code(s) and bill-level totals.

**Behavior:** auto-detect each code's type and return its description via `lookup_code()` over Family A. CPT returns the category fallback. CARC/RARC return the §5 plain-English explanation, including the `suggested_action` routing. Reconcile bill-level totals (`billed` / `allowed` / `plan_paid` / `patient_responsibility`) into a plain-English account of how the member's share was reached and whether it looks internally consistent. If an ACA plan is identified, pull cost-sharing context from `sbc_fields` / `plan_attributes` to sharpen the reconciliation (limited for MA members per §2.1).

**Output:** an answer card (§7) explaining each line and the bottom line, ending in the §4 checkpoint offer to run error/overcharge detection. Where the explanation surfaces a likely error or a likely-winnable denial, it hands off to Flow 2 or Flow 3.

### 6.2 Flow 2 — Error / overcharge detection + savings

**Input (intake stage 3):** per-line code, units, billed charge, modifier, encounter POS.

**Behavior — three independent checks, kept distinct in the output:**

1. **Unbundling (NCCI PTP).** For every code pair on the bill, look up `ncci_ptp_edits` (active subset). Flag pairs that cannot be billed together; account for the PTP modifier indicator (0 = never allowed; 1 = allowed with appropriate modifier; 9 = not applicable). A disallowed pair with no valid modifier is a **likely recoverable error**; the disallowed line's charge is the recoverable amount.
2. **Quantity (NCCI MUE).** For each line, compare units against the `ncci_mue` per-code daily cap. Units over the cap are a **likely recoverable error**; the excess-unit charge is the recoverable amount.
3. **Price benchmark (PFS).** For each professional line, look up `physician_fee_schedule` and compute `billed ÷ benchmark`. **Select the facility vs. non-facility column from the encounter POS** (office vs. hospital changes the correct Medicare rate). Apply the starting tiers (all boundaries in the pricing YAML, tunable as real bills arrive): under ~2× → don't surface; ~2–3× → note as "on the higher side"; ~3–5× → flag as solid negotiation leverage; 5×+ → flag as strong leverage and suggest escalation. Facility/revenue-code lines do not resolve here, are labeled "facility charge — not benchmarked in this version," **and are logged** (line, code, billed amount) so coverage of un-benchmarkable facility spend is measurable — the volume signal that would later justify adding facility schedules (§10).

**Savings output — two honest tiers:**

- **Likely errors (recoverable):** sum of NCCI PTP + MUE disallowed charges. Framed as "these appear to be billing errors worth up to $X you can ask to have removed."
- **Above-benchmark (negotiation leverage):** professional lines billed at a high multiple. Framed as "this line is ≈N× the Medicare benchmark — a strong basis to request a reduction," **never** as "you are owed the difference." The call-to-action is **situation-aware**: for self-pay and balance-bill members (where the billed charge is what they're actually being asked to pay) the multiple is directly actionable and drives a negotiation step; for insured members (where the allowed amount, not the gross charge, governs what they owe) the same multiple is surfaced as *context* with a softer prompt, since chasing the gross charge isn't their dispute. Providers may bill above Medicare; the member's actual obligation depends on plan-allowed amount and network status.

**Output:** an answer card with the two-tier savings figure, the specific lines implicated with citations (NCCI edit, MUE cap, PFS code), and the concrete next action (correction request / negotiation script / escalation). All findings carry the "appears to / likely" framing.

### 6.3 Flow 3 — Ambulance primary-claim denial appeal

**Input:** a **ground** ambulance claim — LOS HCPCS A0426–A0429 / A0432–A0434 (+ A0425 mileage) + modifier; see Stage 4 validation — plus the denial code(s), insurance situation, and denial-letter date. **Air codes (A0430/A0431) are out of scope for v1** and route to the human-advocate handoff before this flow runs (§4.2 Stage 4).

**Behavior:**

1. **Denial trigger.** The §5 layer classifies the CARC/RARC. A medical-necessity denial routes here with that basis attached.
2. **Medical-necessity grounding.** Cross-reference `ncd_ambulance` (NCD 10.1) coverage criteria and exclusions to build the medical-necessity argument. **All 35 NCD rows are reviewed**, so all are available to back user-facing appeal content. The weight of NCD 10.1 differs by segment: for **Medicare FFS and Medicare Advantage it is binding** — CMS codified at 42 CFR 422.101(b)(2) that MA plans must apply Traditional Medicare coverage criteria including NCDs/LCDs for basic benefits and may use more restrictive internal criteria only where Medicare criteria aren't fully established, so an MA ambulance denial measured against NCD 10.1 is the governing standard, and a denial on a *more* restrictive internal rule is itself appeal leverage. For **commercial/ACA, NCD 10.1 is persuasive authority** layered onto the plan's own medical policy and contract terms.
3. **Pathway + deadline.** Route by insurance situation to `medicare_appeal_levels` (Medicare FFS or MA variant) or `commercial_appeal_levels` (ACA/commercial), surfacing the correct level, filing deadline, and citation. Deadlines always carry a "verify the current deadline" caveat.
4. **Dollar anchor (ground).** Compute the Medicare reasonable amount from `ambulance_fee_schedule` for the ground LOS HCPCS + state: base rate for the level of service **plus** the A0425 per-mile rate × loaded miles (Stage 4 intake). Full denial = the whole reasonable amount; partial payment = the gap to it. If the member didn't supply loaded mileage, compute from the base rate only and present the figure as a floor ("at least $X"). *The fee schedule is state-level (52 geo areas) and includes A0425; confirm A0425 is stored as a per-mile rate (vs. flat) before locking the mileage math — see §10 #4a.*
5. **Ground-ambulance honesty node (ground only).** For a **ground** transport, ground ambulance is generally **not** protected by the federal NSA (Tables A–K model the carve-out). A ground-ambulance *denial appeal* rests on medical necessity + appeal procedure + plan terms, **not** NSA citations — so this flow does not depend on the 59 NSA rules being live. The node states the carve-out plainly and pivots to the medical-necessity + reference-rate position. **This node must never render for an air transport:** air ambulance **is** NSA-protected, so the ground "not-protected" framing would be the opposite of the member's actual rights. Air codes are intercepted at Stage 4 and routed to the human-advocate handoff; the bot does not assert NSA protections in automated copy (air NSA-citing content stays behind the 4c counsel gate).
6. **Document generation.** Assemble the appeal package: member/claim details, denial basis, medical-necessity argument (NCD-cited), the correct appeal level + deadline, the dollar figure, and required next steps. *Gate: generated appeal-letter templates require counsel review of advocacy framing before go-live (UPL) — an app-layer gate independent of the data.*

**Insurance-situation scope (confirmed):** v1 supports Medicare FFS, Medicare Advantage, and commercial/ACA denials. The Family G payer-policy corpus is not built, but for the ambulance wedge this barely bites: NCD 10.1 is binding on MA plans for basic benefits, so the medical-necessity grounding (now fully reviewed) is the *governing* standard for the FFS and MA segments — which together are most of the member base. Commercial/ACA is the only segment relying on NCD as persuasive-only, and its appeal pathway (`commercial_appeal_levels`) is in the data.

---

## 7. Answer-card output format

Every workflow output uses one card structure (persisted to `answer_cards` + `card_citations`):

1. **Headline finding** — one sentence.
2. **The number** — savings, gap, or exposure, where applicable (the product principle: a concrete dollar figure).
3. **Why** — the plain-English reasoning, line by line where relevant.
4. **Citations / provenance** — every user-facing fact traces to a source (code set, NCCI edit, PFS code, NCD criterion, appeal rule), per the Data PRD provenance contract.
5. **Concrete next action** — exactly one recommended step (request a correction, negotiate with this script, file this appeal by this date, escalate to a human).
6. **Framing** — protections/determinations are always "appears to / likely," never definitive legal conclusions.
7. **Escalation** — the option to hand off to an in-house human advocate (Wellthy under evaluation as a future partner; `handoffs` table).

---

## 8. Guardrails

- **UPL.** Appeal-letter framing and any deadline calculation require human/counsel review before user-facing publication; application-layer disclaimers throughout.
- **Counsel gates open at go-live:** (a) generated appeal-letter templates require counsel review of advocacy framing; (b) **NSA rules are not yet counsel-reviewed.** The build proceeds *as if* they are reviewed so development isn't blocked, but no NSA-citing output (air-ambulance or emergency balance-billing protections) may go live until sign-off lands. Ground-ambulance denial appeals are unaffected because they don't cite NSA. Treat the NSA "reviewed" state as a feature flag defaulted off for user-facing NSA citations until counsel confirms. *(The NCD review gate from v0.2 is now resolved — all 35 rows reviewed — and is no longer a blocker.)*
- **Framing discipline.** "× Medicare" is leverage, not entitlement; errors are "likely," not adjudicated; coverage determinations remain the payer's.
- **PHI separation.** Structured intake only; member bill data lives in `app.db` (application tier); nothing written to `pilot.db`; no documents stored.

---

## 9. Build manifest for Claude Code (`masa-sam-advocate`)

- **Reads from `pilot.db` (read-only):** `lookup_code()` over `codes`; `ncci_ptp_edits` (active subset), `ncci_mue`, `physician_fee_schedule`, `ambulance_fee_schedule`, `ncd_ambulance`, `medicare_appeal_levels`, `commercial_appeal_levels`, `nsa_rules`, `ma_plans`, `sbc_fields`/`plan_attributes`.
- **Canonical artifacts (this PRD package):**
  - **`app_schema_v0_1.sql`** — the `app.db` schema. Implements the two-axis triage, the resumable Stage 0–4 state machine (+ 3-alt), `code_explanations`, Flow 2 `flow2_findings` (three finding types + facility-unbenchmarked log), Flow 3 `flow3_appeals` + `appeal_citations`, the universal `answer_cards` + `card_citations`, `handoffs`, `case_events`, and the `v_case_savings` view. `entry_point`/`seed_intent` and the extensible `problem_type`/`active_flow` enums carry the universal-SAM model and roadmap workflows.
  - **`carc_rarc_plain_english.yaml`** — the §5 routing layer (50 CARC + 30 RARC; routing fields populated, copy stubbed for authoring).
  - **`SAM_screens_v0_1.html`** — the v0.1 screen set (§1.4): contextual FAB + launcher, intake Stages 0–4 and 3-alt (bottom-sheet → near-full), and the three answer cards, on MASA app surfaces with brand tokens. Each frame is captioned with its stage and `app.db` write; treat it as the UI-to-schema reference for the build.
- **Build new in app layer:**
  - Intake state machine (§4) in `app.db`, with the checkpoint at Stage 0, the progressive checkpoint after the Flow 1 card, and Stage 4 ambulance capture incl. member-optional loaded mileage and transport-code validation.
  - `code_explanations` table + YAML loader (joins `official_text` from `pilot.db`) + `suggested_action` router (§5), including the CARC 45 `insurance_situation`-aware branch and CARC 29 verify-then-escalate. Do **not** auto-author the explanation text.
  - Flow 2 engine: PTP pair check (with modifier indicator), MUE unit check, PFS benchmark with POS-driven facility/non-facility column selection, tiered + situation-aware above-benchmark flagging (boundaries in pricing YAML), two-tier savings aggregation, and logging of un-benchmarkable facility lines.
  - Flow 3 engine (**ground-only v1**): Stage-4 ground/air split (ground LOS A0426–A0429 / A0432–A0434 + A0425; air A0430/A0431/A0435/A0436 → human-advocate handoff with neutral copy, air branch stubbed for a future flagged unlock) → denial classification → NCD grounding (all 35 rows available; binding-vs-persuasive by segment) → pathway/deadline routing → base-plus-mileage dollar anchor → appeal-package assembly (templates pending counsel). Ground honesty node renders for ground only. NSA citations behind a feature flag defaulted off until sign-off.
  - Universal-SAM surface (§1.3–§1.4): FAB + contextual entry seeding (`entry_point`/`seed_intent`), bottom-sheet → near-full expansion. Build to the v0.1 screen set (`SAM_screens_v0_1.html`); the eleven frames in §1.4 define the states and their schema writes.
  - Answer-card renderer (§7) and the in-house escalation handoff.
- **Do not regenerate:** `pilot.db` or any ingestor; the NSA ruleset; the CARC/RARC explanation copy.

---

## 10. Resolved decisions & remaining confirm-items

**Resolved in v0.2:**

1. **Flow 3 scope:** Medicare FFS + MA + commercial/ACA. NCD 10.1 binding for FFS/MA, persuasive for commercial (§6.3).
2. **Checkpoint default:** progressive (explain first, then offer error-check), upfront option retained (§4).
3. **Savings tiers:** under 2× none; 2–3× "on the higher side"; 3–5× solid leverage; 5×+ strong leverage / escalation. Situation-aware call-to-action. All boundaries in the pricing YAML, tunable on real data (§6.2).
4. **Facility benchmarking:** deferred; Flow 2 logs un-benchmarkable facility lines so the add is data-driven later (§6.2).

**Resolved in v0.3:**

5. **NCD review (was #4b):** `ncd_ambulance` is 35 rows, all `reviewed=1`. Flow 3 medical-necessity grounding is review-clean; no longer a go-live blocker.
6. **app.db schema:** specified as `app_schema_v0_1.sql` (§9).
7. **CARC/RARC routing:** specified as `carc_rarc_plain_english.yaml` (§5/§9); CARC 45 `insurance_situation`-aware and CARC 29 verify-then-escalate locked.
8. **SAM interaction model:** universal SAM, FAB + contextual entry, bottom-sheet → near-full (§1.3).
9. **Data figures:** §2 reconciled to the verified overview.

**Resolved in v0.3.1:**

10. **Screen set (was #10b):** v0.1 delivered as `SAM_screens_v0_1.html` and folded into the PRD (§1.4). Visual sign-off and member testing remain open for iteration but no longer block the build.

**Resolved in v0.3.2:**

11. **Air vs. ground scope:** Flow 3 v1 is ground-only (LOS A0426–A0429 / A0432–A0434 + A0425 mileage). Air codes (A0430/A0431) are detected and routed to the human-advocate handoff; the ground honesty node never renders for air; air NSA-citing content stays behind the 4c gate. Air is a future flagged unlock (§4.2, §6.3, §9).

**Remaining confirm-items (do not block PRD, do gate go-live):**

- **4a. Ambulance fee schedule (largely answered):** the table is state-level (52 geo areas) and includes A0425, so the locality column exists and the base-plus-mileage inputs are present. The only residual check is whether A0425 is stored as a true per-mile rate (vs. flat) in `pilot.db`. If base-only, the dollar anchor degrades gracefully to a floor.
- **4c. NSA counsel sign-off (pending):** not yet reviewed. Build proceeds as-if-reviewed; NSA-citing output stays behind a flag until sign-off. Ground-ambulance denial appeals are unaffected.
- **10a. CARC/RARC frequency re-validation:** the `rank_frequency` ordering is grounded in published denial-index literature; re-validate against a current published source or MASA's own denial data. Routing is rank-independent, so this does not block the engine.
- **10c. Screen visual sign-off / member testing:** v0.1 is delivered; capture markups and usability feedback (55+ population) before locking final copy and spacing.
- **11a. Air-ambulance data limit (when air is unlocked):** A0430/A0431 base rates exist in `ambulance_fee_schedule`, but air-mileage codes **A0435/A0436 are not** — so an air anchor would be base-only until air mileage is sourced. Air also needs the 4c NSA sign-off and an air-specific appeal model (NSA/IDR/QPA), not just a flag flip.
