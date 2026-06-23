# SAM Tier A — Ground-Truth Fixture Generator Spec

**Version:** v0.2 (draft for Claude Code build)
**Prepared for:** Claude Code build (`masa-sam-advocate`)
**Status:** Draft. Defines the Tier A test-data layer from the test-data strategy (engineered fixtures from `pilot.db`).
**Changelog v0.1 → v0.2:** Added a second generator output mode — a human-readable demo pack (`--demo`) for manual entry during demos (§6). Clarified the execution model: the generator and the pytest runner are separate programs on separate cadences (§2).
**Relationship to other artifacts:** Consumes `pilot.db` (read-only) and `config/carc_rarc_plain_english.yaml`. Produces fixtures for the SAM engine test suite (Flows 1–3 per PRD v0.2 §6). This is a *test-data* spec, not an application or pipeline spec.

---

## 1. What this is — and explicitly is not

**Is:** a deterministic generator that introspects `pilot.db`, selects fixture-relevant rows, composes synthetic cases around them, and writes each case **plus an independently-computed expected output** to committed fixture files. These fixtures are the regression net for the deterministic engine — every one has an assertable expected result.

**Is not:**
- **Not a web crawler or extractor.** It makes no network calls. All reference data already exists locally in `pilot.db`; the ingestion/extraction work was completed by the `medical_billing_data` repo. The generator reads, it does not fetch.
- **Not a PDF/OCR layer.** v0.5 intake is structured manual entry; fixtures are structured records, not rendered documents.
- **Not Tier B or C.** No Synthea/Blue Button/MEPS data, no real bills. Those are separate layers.
- **Not a regenerator of `pilot.db`** or any ingestor.

---

## 2. Architecture & repo placement

Suggested layout (Claude Code may adapt to the repo's existing structure):

```text
masa-sam-advocate/
  backend/
    tests/
      fixtures/
        generate.py            # the generator (CLI entry)
        reference_calc.py       # independent expected-output computation
        data/                   # COMMITTED fixture files (engine tests read these)
          flow1/ flow2/ flow3/
        demo/                   # COMMITTED human-readable demo pack (§6)
        MANIFEST.json           # pilot.db version + counts per fixture set
        README.md
```

**Two separate programs on separate cadences.** The *generator* and the *test runner* are distinct and must not be conflated:
- **Generator** (`generate.py`): run *rarely* and by hand. Reads `pilot.db`, composes cases, computes expected outputs independently, writes data files. Never runs a test; never imports the engine.
- **Test runner** (pytest): runs *automatically* in CI on every commit/PR and on-demand locally. One parametrized test loads every fixture, calls the engine on `input`, asserts equality with `expected`. Each fixture is an individually-named pass/fail; a failure prints the fixture id and the diff, which is the actionable punch list. No auto-correction: a failure is adjudicated by a human/agent as either an engine bug or a fixture bug.

**Execution model — generate-then-commit:**
1. A developer runs `python backend/tests/fixtures/generate.py --pilot-db <path>` against a local `pilot.db`.
2. The generator writes fixture files into `data/` (and, with `--demo`, the demo pack into `demo/`) and stamps `MANIFEST.json`.
3. Fixtures are committed to the repo.
4. CI runs the engine test suite against the **committed** fixtures and does **not** require `pilot.db` to be present.
5. Regeneration is a periodic maintenance task triggered by reference refreshes (NCCI quarterly, PFS annual); the fixture diff is reviewed like any other change.

Rationale: `pilot.db` is large and lives behind Git LFS in a separate repo. Decoupling the test run from the DB keeps CI fast and portable while keeping the fixtures traceable to a known DB state.

---

## 3. Core design decisions

1. **Expected outputs are computed independently of the engine.** `reference_calc.py` derives expected results from first principles (e.g., excess units × per-unit charge; `billed ÷ benchmark` → tier band). It must **not** import or call the Flow 1–3 engine code under test, or the fixtures become a mirror of the engine rather than a check on it.
2. **Determinism.** A fixed seed governs all sampling and synthetic-charge noise. Re-running against the same `pilot.db` produces byte-identical fixtures.
3. **Provenance.** `MANIFEST.json` records, per fixture set: the `dataset_releases` `file_hash` / `row_count` for each source table touched, the generator version, and the seed. Every fixture traces back to a known DB version (consistent with the system-wide provenance contract).
4. **Specificity weighting.** The catalog is deliberately weighted toward *clean* control cases (no finding expected) so the suite measures false-positive rate, not just detection rate.

---

## 4. Fixture catalog

Target volume is small and bounded (~200–300 total). Counts below are starting targets, tunable.

### 4.1 Flow 2 — Error / overcharge detection

**Unbundling (NCCI PTP)** — source: `ncci_ptp_edits`
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Indicator 0 (never allowed) | 2-line bill with a real indicator-0 pair | Flag; recoverable = disallowed line charge | 15 |
| Indicator 1, no modifier | Real indicator-1 pair, no modifier on either line | Flag | 10 |
| Indicator 1, valid modifier | Same pair, valid modifier present | **No flag** | 10 |
| Indicator 9 (n/a) | Real indicator-9 pair | No flag | 5 |
| Pair absent from table | Two codes with no PTP edit | **No flag** (clean control) | 10 |

**Quantity (NCCI MUE)** — source: `ncci_mue`
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| At cap | Units = MUE cap | No flag (clean control) | 10 |
| Cap + 1 | Units = cap + 1 | Flag; recoverable = 1 × per-unit charge | 10 |
| Over cap | Units = cap + N | Flag; recoverable = N × per-unit charge | 10 |

**Price benchmark (PFS)** — source: `physician_fee_schedule`
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Sub-2× | billed = benchmark × ~1.5 | No flag (clean control) | 10 |
| 2–3× band | billed = benchmark × ~2.5 | "On the higher side" | 8 |
| 3–5× band | billed = benchmark × ~4 | Solid leverage | 8 |
| 5×+ band | billed = benchmark × ~6 | Strong leverage / escalation | 8 |
| POS column flip | Same code, POS office vs hospital | Asserts non-facility vs facility column selected (benchmark differs) | 6 |
| CPT-numbered line | A CPT code present in PFS | Category fallback description **and** still benchmarked | 5 |

Band boundaries must read from the pricing YAML, not be hard-coded (PRD §6.2).

### 4.2 Flow 3 — Ambulance denial appeal

**Dollar anchor** — source: `ambulance_fee_schedule`
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Ground, base + mileage | A0426–A0429 / A0432–A0434 + A0425 mileage × loaded miles, sampled states | Anchor = base + (per-mile × miles) | 12 |
| Ground, base only | Same, no mileage supplied | Anchor = base; labeled a floor ("at least $X") | 8 |
| Full denial vs partial | Both denial states for a fixed transport | Full = whole reasonable amount; partial = gap to it | 6 |

> **Blocks on confirm-item 4a:** whether A0425 is stored per-mile or flat determines the mileage math. The base-only fixtures can be built now; the base-plus-mileage fixtures need 4a resolved.

**Denial routing** — source: `carc_rarc_plain_english.yaml` (+ `codes` CARC/RARC)
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Medical-necessity denial | CARC/RARC mapped to `appeal` | Routes to Flow 3 with NCD grounding | 6 |
| Bundled / duplicate | mapped to `error_check` | Routes to Flow 2 | 4 |
| COB / other | mapped to `verify_with_payer` / `escalate_human` | Routes accordingly | 4 |

**Air handoff** — source: `codes` (A0430, A0431)
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Air transport | A0430/A0431 case | Human-advocate handoff; neutral copy; **no NSA assertion** | 4 |

**Segment weighting**
| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Medicare FFS / MA | Ground denial, FFS and MA | NCD 10.1 treated as binding; pathway = `medicare_appeal_levels` (+ MA variant) | 6 |
| Commercial / ACA | Ground denial, commercial | NCD persuasive; pathway = `commercial_appeal_levels` | 4 |

### 4.3 Flow 1 — Explanation & reconciliation

| Sub-category | Construction | Expected | Target |
|---|---|---|---|
| Code lookup | One case per `code_type` | Correct description | ~11 |
| CPT lookup | A CPT-numbered line | Category fallback (no AMA description) | 3 |
| CARC/RARC lookup | Sampled denial codes | Plain-English layer + `suggested_action` | 6 |
| Consistent waterfall | billed/allowed/plan-paid/adjustment/patient-resp that reconciles | "Internally consistent" | 8 |
| Broken waterfall | Same, deliberately inconsistent | Flagged inconsistent | 6 |

---

## 5. Fixture file schema

One JSON object per fixture (grouped into files by flow/category):

```json
{
  "fixture_id": "flow2_unbundling_ind0_001",
  "flow": 2,
  "category": "unbundling_indicator_0",
  "provenance": {
    "pilot_db_version": "<MANIFEST ref>",
    "source_table": "ncci_ptp_edits",
    "source_rows": ["<pk or natural key of the real row(s) used>"]
  },
  "input": { "...": "case exactly as the engine entry point receives it" },
  "expected": { "...": "assertable output: flags, recoverable amounts, routes, descriptions" }
}
```

`input` mirrors the structured intake shape (PRD §4.2), not a document.

---

## 6. Demo export mode (`--demo`)

A second output mode on the same generator. Instead of machine JSON, `--demo` emits a small, human-readable pack (markdown table or printable cards) for manual entry into the live SAM UI during demos.

**Properties:**
- **Derived, not separate.** The demo pack is a *view* over the committed fixtures — same verified `input`/`expected`, so demo cases can never drift from what the engine is tested against.
- **Real codes.** Because fixtures are built from real `pilot.db` rows, demo codes resolve correctly in the running app (real HCPCS, real NCCI pair, real PFS rate). The demo bill is genuine, just composed to trigger a finding.
- **Curated for legibility, not coverage.** Selection criterion differs from the test suite: pick the *unambiguous, high-impact* cases (e.g., a ~6× PFS line, an indicator-0 unbundled pair, a clearly over-cap MUE line), not boundary cases like the 2–3× band. Target ~2–3 cases per finding type across the three flows.

**Demo card format (one per case):**
```text
Demo — <flow / finding type, e.g. "Price benchmark (PFS), strong leverage">
Enter in SAM: <line item(s): code(s), units, billed charge, POS / denial code as applicable>
Expected: <plain-English statement of what SAM should show — the finding, the dollar figure, the next action>
Source: <fixture_id> (traceable to MANIFEST.json)
```

The demo pack is committed alongside the fixtures and regenerated with them.

---

## 7. Build manifest for Claude Code

- `generate.py`: CLI; opens `pilot.db` read-only; samples rows per §4 under a fixed seed; calls `reference_calc.py` for expected outputs; writes fixture files + `MANIFEST.json`. Supports a `--demo` flag that additionally emits the human-readable demo pack (§6) from a curated fixture subset.
- `reference_calc.py`: independent expected-output logic. **Must not import engine code.**
- Committed `data/` fixtures, `demo/` pack, and `MANIFEST.json`.
- Test harness wiring so the engine suite loads `data/` and asserts `engine(input) == expected` per fixture, one parametrized case per fixture id (the engine itself is built per PRD v0.2 §9; this spec only supplies the fixtures and the independent expectations).

**Do not:** make network calls; render PDFs; touch `pilot.db` for writes; auto-author CARC/RARC explanation text; have the test runner auto-rewrite expected values to match engine output.

---

## 8. Dependencies & confirm-items

- **4a (blocks base-plus-mileage ambulance fixtures):** confirm A0425 storage (per-mile vs flat) and the state/locality column.
- **`carc_rarc_plain_english.yaml` authored:** denial-routing fixtures (§4.2) assert against its `suggested_action` mapping.
- **Pricing YAML present:** PFS band fixtures (§4.1) read boundaries from it.
- **NCD review state:** segment fixtures assume approved NCD rows back user-facing appeal content (PRD §8 gate); fixtures assert routing/weighting, not the final advocacy copy.
