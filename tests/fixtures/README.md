# Tier A ground-truth fixtures

Engineered regression fixtures for the deterministic SAM engine, built from real
`pilot.db` rows. Implements `docs/SAM_Tier_A_Fixture_Generator_Spec_v0_2.md`.
**Flows 1, 2, and 3 are implemented** (~195 fixtures). Not yet covered: Flow 3
*partial-payment* cases — the engine has no partial-payment intake field, so the
"full vs partial denial" sub-category is deferred until that input exists.

## Two separate programs (different cadences)
- **`generate.py`** — run *rarely, by hand*. Reads `pilot.db` (read-only), composes
  cases around real rows, computes expected outputs via `reference_calc.py`, and
  writes committed fixtures + `MANIFEST.json`. Never imports the engine.
- **`../test_fixtures.py`** (pytest) — runs in CI on every commit. Loads each
  committed fixture, materializes its `input` into a temp `app.db`, runs the engine,
  and asserts the engine's findings equal the fixture's `expected`. Does not read
  `pilot.db` for the assertion itself (only the engine does, for benchmarks).

## Regenerate
```bash
python tests/fixtures/generate.py --demo        # --demo also writes demo/flow2_demo_pack.md
pytest tests/test_fixtures.py                    # verify engine == expected
```
Regeneration is a maintenance task triggered by reference refreshes (NCCI quarterly,
PFS annual); review the fixture diff like any other change.

## Contracts
- **Independent expectations.** `reference_calc.py` re-derives results from first
  principles using the data layer (`app.pilot`) + config (`app.config`); it must
  never import `app.flows` (the engine under test).
- **Determinism.** A fixed `--seed` (default 1337) governs all sampling; output JSON
  is sorted with no timestamps, so re-running against the same `pilot.db` is
  byte-identical.
- **Provenance.** `MANIFEST.json` records, per source table, the `dataset_releases`
  `source_id` → `file_hash` / `row_count`, plus the generator version and seed. Each
  fixture's `provenance.source_rows` names the real row(s) it was built from.

## Layout
```
fixtures/
  generate.py          reference_calc.py     canonical.py
  data/flow1/*.json  data/flow2/*.json  data/flow3/*.json   # one file per category
  demo/sam_demo_pack.md   # --demo human-readable pack (Flows 1-3)
  MANIFEST.json
```

Flow-specific notes: Flow 1 fixtures assert the answer card's structured bits
(number, reconciliation category, per-line described/CPT-fallback, appealable);
Flow 3 covers the dollar anchor (base+mileage / base-only floor), segment weighting
(FFS/MA binding vs commercial persuasive + pathway), denial routing, and the air
handoff. The "full-truth" note below applies to Flow 2.

## Note on "full-truth" expectations
The engine runs all three Flow 2 checks over the whole bill regardless of a
fixture's headline category, so `expected` lists **every** finding a bill triggers
(e.g. an unbundling fixture may also carry an incidental facility-log or PFS line).
This is intentional — the fixture asserts the engine's complete output.
