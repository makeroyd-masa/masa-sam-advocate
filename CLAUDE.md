# masa-sam-advocate

SAM is a member-facing, guided medical-bill advocacy tool for MASA. It explains bills/EOBs,
detects billing errors and overcharges, and builds ambulance denial appeals. Chat is the
interface skin; the engine is a deterministic, case-anchored guided flow — not an open-ended chatbot.

## Read first
- `docs/PRD.md` — the spec (v0.3.1). Start here before writing any code.
- `docs/app_schema_v0_1.sql` — the `app.db` schema (case/state, findings, answer cards).
- `docs/carc_rarc_plain_english.yaml` — the §5 denial-code routing layer.
- `docs/SAM_screens_v0_1.html` — the v0.1 screen set; the UI-to-schema reference (PRD §1.4).

## Stack
- Backend: FastAPI, Python 3.12
- Frontend: React 18 + TypeScript + Vite
- DB: SQLite — read-only `pilot.db` + writable `app.db`
- Config: YAML for pricing thresholds, escalation, and the code-explanation layer

## Data layer (two databases — separate files, no cross-db FKs)
- `pilot.db` is READ-ONLY reference data produced by the separate `medical_billing_data` repo.
  Never write to it. Its path comes from `PILOT_DB_PATH` (see `.env.example`).
- `app.db` is the app's writable case/state store. Create it from the schema:
  `sqlite3 "$APP_DB_PATH" < docs/app_schema_v0_1.sql`. Path from `APP_DB_PATH`.
- Store pilot codes as plain values and resolve against `pilot.db` at query time.

## Commands (keep current after scaffolding)
- Setup (backend): `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt` (POSIX: `.venv/bin/...`)
- Setup (frontend): `npm install`
- Backend dev:  `.venv/Scripts/python -m uvicorn app.main:app --reload` (serves `/health`)
- Frontend dev: `npm run dev` (proxies `/health`, `/api/*` to `:8000`)
- Tests:        `.venv/Scripts/python -m pytest`
- Init app.db:  `.venv/Scripts/python scripts/init_app_db.py` (`--force` to recreate). Portable Python script — the `sqlite3` CLI is not assumed present. Seeds a `dev-member-001` fixture.
- Config lives in `config/`: `carc_rarc_plain_english.yaml` (canonical §5 routing layer), `pricing_thresholds.yaml`, `feature_flags.yaml`, `pos_facility_map.yaml`, `escalation.yaml`.
- Load routing layer: load `config/carc_rarc_plain_english.yaml` into `code_explanations` (join `official_text` from `pilot.db` on `code`)

## Architecture
- Two-axis triage (`problem_type` × `insurance_situation`) routes each case to a flow.
- Intake is a resumable state machine in `app.db` (`cases.current_stage` + `machine_context`), Stages 0–4 + 3-alt.
- Three flows: Flow 1 explain · Flow 2 error/overcharge (NCCI PTP + MUE + PFS) · Flow 3 ambulance appeal.
- The denial code (CARC/RARC) is the dispatcher between flows via `code_explanations.suggested_action`.
- Every output is one answer card (PRD §7): headline → the number → why + citations → exactly one next action → "appears to / likely" framing → human-advocate escalation.

## Brand
- Source of truth: `src/styles/tokens.css` (tokens + fonts) and `public/logo.svg` (+ `logo-white.svg`, `mark-white.svg`). Import the tokens; do not hardcode hex in components.
- Horizon `#230871` = primary/advocate actions. Tide `#0071CE` = leverage/secondary. Flare `#E64B38` is RESERVED for links and escalation only. Shine `#FFD040` = honesty/caution nodes. Poppins (display) + Open Sans (body), sentence case.
- Use the logo SVG in structural positions (header/nav); never type "MASA" as a header/nav identifier.

## Guardrails (non-negotiable)
- PHI stays in `app.db` only. Never write member data to `pilot.db`. No documents are stored (no upload/OCR in this phase).
- NSA citations sit behind a feature flag DEFAULTED OFF until counsel sign-off. Ground-ambulance appeals don't cite NSA and are unaffected.
- Flow 3 is GROUND ONLY (v1): LOS A0426–A0429 / A0432–A0434 + A0425 mileage. **Air codes (A0430/A0431, and air-mileage A0435/A0436) route to the human-advocate handoff** — never run them through the ground appeal flow, never render the ground "not-NSA-protected" node for air, and never assert NSA protections in automated copy. Air ambulance IS NSA-protected; that content stays behind the 4c counsel gate.
- Generated appeal-letter templates are counsel-gated (UPL) — not user-facing until reviewed.
- Do NOT auto-author the CARC/RARC member copy (`plain_explanation` / `practical_meaning`); those are human-authored and review-gated.
- Do NOT regenerate `pilot.db` or any ingestor.
- Framing discipline: "× Medicare" is leverage, not entitlement; errors are "likely," not adjudicated; coverage determinations remain the payer's.

## Conventions
- Money: INTEGER cents everywhere. Timestamps: ISO-8601 UTC text.
- Enums must match the CHECK constraints in `app_schema_v0_1.sql`.
- Build in phases per PRD §9; commit per phase; use plan mode before large changes.
