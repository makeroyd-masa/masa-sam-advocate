# SAM PRD Addendum — Cost-share verification layer (v0.1 proposal)

**Status:** Draft for review — proposes a new capability for a future PRD minor (target §11 / v0.4). Not yet built. No changes to shipped flows are implied until this is accepted.
**Motivates:** broadening SAM's value for **insured members** (employer/ERISA and commercial/ACA) — the segment MASA's Group enrollment skews toward (working-age, employer-sponsored), and the segment for whom the current gross-charge-centric value proposition is weakest.
**Evidence base:** two real member EOBs added to `docs/` on 2026-06-24 — `eob_table_example.png` (Anthem, in-network office visit) and `full_eob_example.pdf` (Anthem, in-network hospital claim + a year-to-date accumulator summary). Both are referenced throughout as the worked examples.
**Inherits:** PRD v0.3.2 (§6 flows, §7 answer card, §8 guardrails). This addendum adds a check; it does not relax any guardrail.

---

## A. Why this addendum exists

Two observations from the real EOBs, together, expose a gap in the current scope.

**1. A transparent EOB already does most of what Flow 1 does.** The Anthem EOBs print the full waterfall the member needs — billed → discount → **allowed** → plan paid → member responsibility — and break the member's share into its parts (**copay / deductible / coinsurance / not-covered**), with a glossary. Flow 1's bill-level reconciliation (`flow1.py:_reconcile`) reconstructs a thinner version of the same thing. **The value of *explaining* an EOB scales inversely with how transparent the EOB already is.**

**2. For an insured member, the gross-charge "× Medicare" multiple is largely not actionable.** On the office visit the member owes a flat **$30 copay** regardless of whether the $381 charge is 1× or 10× Medicare; on the in-network hospital claim the obligation is set by the **allowed amount** and the cost-share split, not the gross charge. Flow 2's PFS leverage tier is genuinely useful for self-pay / balance-bill members (where the gross charge *is* the ask), and the existing situation-aware framing (§6.2) correctly softens it for insured members — but for the Group segment it remains *context*, not the dispute.

**The durable, segment-agnostic value is checking what the EOB *asserts* but does not *prove*.** A good EOB needs no explanation; it still needs verification. The verification opportunity that SAM does not yet touch is the **cost-share layer**: the arithmetic that produces the member's responsibility, and the accumulators (deductible, out-of-pocket maximum) that govern it across the plan year.

**Worked illustration (does not assert an error).** On `full_eob_example.pdf` p.3, the printed parts of the member's share — copay $100.00 + deductible $200.38 + coinsurance $1,125.07 — sum to **$1,425.45**, while the EOB's "you pay" is **$1,485.45**, a ~$60 gap not obviously reconciled by the printed columns (it may resolve against a column not legible in the source image). Whether or not this particular figure is an error, **a clean reconciliation discrepancy of this kind is exactly what a member cannot eyeball and an automated check can surface** — under the standard "appears to / worth a closer look" framing.

---

## B. What SAM captures today vs. what the EOB contains

Stage 2 intake (`Stages.tsx`, `bill_summaries`) captures only:

| Captured today | Present on a real EOB but **not** captured |
|---|---|
| provider, date of service | **allowed amount** (schema column `total_allowed_cents` exists but the Stage-2 UI does not collect it) |
| total billed | **copay**, **deductible applied**, **coinsurance**, **not-covered** (the columns that actually determine the member's share) |
| total plan paid | the **discount / contractual write-off** amount |
| patient responsibility ("you owe") | year-to-date **accumulators**: deductible and OOP-max, individual vs. family, in- vs. out-of-network, applied vs. remaining (the `full_eob_example.pdf` p.2 summary) |
| one denial code | per-bucket medical vs. pharmacy accumulators |

The columns that govern an insured member's obligation are precisely the columns SAM does not model.

---

## C. Proposed scope — the cost-share verification layer

A new capability, scoped to **insured situations** (`employer_erisa`, `commercial_aca`; degrades gracefully for others). Two parts, both structured intake — **no OCR, no document storage** (§8 PHI separation unchanged).

### C.1 Extend the bill-level capture (per-claim)
Add to Stage 2 (and `bill_summaries`) the cost-share columns the member can read off the EOB, all optional:

- `copay_cents`, `deductible_applied_cents`, `coinsurance_cents`, `not_covered_cents`, `discount_cents`
- (`total_allowed_cents` already exists — surface it in the UI.)

### C.2 Optional accumulator capture (per-member, plan-year)
A small, optional capture of the YTD summary (`full_eob_example.pdf` p.2): deductible and OOP-max, each as **applied** and **remaining**, scoped by individual/family and in/out-of-network. Stored in `app.db` only. This is the data that powers the cross-claim checks in C.3 #3–4 and is the highest-value, least-collected information for the Group segment.

### C.3 The check — `cost_share_check` finding
A new finding type producing answer-card output (§7), under full framing discipline. Checks, in priority order:

1. **Cost-share reconciliation.** Does `copay + deductible_applied + coinsurance + not_covered` equal the stated patient responsibility? A material gap → "the parts of your share don't add up to the total here — worth a closer look." *(This is the §A worked example.)*
2. **Coinsurance rate consistency.** If the plan's coinsurance rate is known (member-entered or from `sbc_fields`/`plan_attributes` for ACA), check `coinsurance ≈ rate × (allowed − deductible_applied)`. Off by more than rounding → flag for review.
3. **Deductible over-application** *(needs C.2).* Was more applied to the deductible on this claim than the member had **remaining**? → likely error.
4. **Charging past the OOP maximum** *(needs C.2).* Is cost-share still being charged after the OOP-max is met? → likely error; high member impact.
5. **Not-covered → routing.** When `not_covered_cents > 0`, this is the denial entry point — hand off to the §5 denial router / Flow 3, not to the cost-share explainer.

### C.4 Framing (non-negotiable, per §8)
- Every finding is "**appears to / worth a closer look**," never an adjudication. SAM identifies arithmetic and accumulator inconsistencies; **coverage and benefit-design determinations remain the payer's.**
- The check reasons about the **member's contracted obligation**, not the gross charge — it never tells an insured member they are "owed" the discount or the gross-charge gap.
- Plan terms entered by the member are treated as member-asserted unless sourced from `sbc_fields`/`plan_attributes`; citations distinguish the two.

---

## D. Why this serves the Group strategy

This shifts SAM's center of gravity, for insured members, from **"explain the waterfall + negotiate the gross charge"** (a consumer / self-pay value proposition) to **"verify the bill is correct"** (the insured / Group value proposition):

- It is **most useful when the EOB is least transparent** — the inverse of Flow 1's explain value, so the two are complementary rather than redundant.
- It targets errors a member **cannot self-detect** (cross-claim accumulator integrity), which is where automation earns trust.
- It composes with the separate, already-noted screen-2 reorder (default toward `employer_erisa`, demote Medicare/MA) and the Medicare-benchmark transparency line — those remain worth doing independently of this addendum.

---

## E. Out of scope / explicitly deferred

- **No OCR / document upload.** Structured intake only (consistent with §1.1 non-goals).
- **No new pilot data dependency** beyond the existing `sbc_fields`/`plan_attributes` (ACA cost-sharing) already cited in §6.1. The check works on member-entered numbers when plan terms aren't available.
- **Balance-billing / NSA** stays behind the §8 counsel gate; this addendum does not cite NSA. (It is, however, where the *other* large insured-member value lives — flagged for the counsel-gate roadmap, not built here.)
- **Pharmacy accumulators** captured if offered but not yet checked in v0.1.

---

## F. Open questions / gates

1. **Member-entry burden.** The accumulator capture (C.2) is the highest-value but highest-friction step. Confirm with design whether it's an optional "power-user" path or skipped for v0.1 (which would limit the check to C.3 #1–2, #5 — still net-new value with near-zero added friction).
2. **ACA plan-terms coverage.** Confirm how reliably `sbc_fields`/`plan_attributes` yield a usable coinsurance rate / deductible for the check's #2; for `employer_erisa` (ERISA self-funded, not in pilot data) the rate is member-entered only.
3. **Schema sign-off.** The C.1/C.2 columns are additive to `bill_summaries` plus one small accumulators table — needs a schema minor (`app_schema_v0_2.sql`).
4. **Counsel framing review.** The reconciliation/accumulator copy is advocacy-adjacent; confirm whether it needs the same review treatment as appeal copy (§8 UPL) or clears as factual-arithmetic surfacing.
