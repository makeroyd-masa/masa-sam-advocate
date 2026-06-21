"""Load the §5 CARC/RARC routing layer into app.db `code_explanations`.

Reads config/carc_rarc_plain_english.yaml (routing fields populated; member copy
intentionally blank — PRD §5.3) and joins official_text from pilot.db on (code,
code_type). Idempotent upsert on the (code, code_type) primary key.

GUARDRAIL: this loads the human-authored asset verbatim. It NEVER fabricates
plain_explanation / practical_meaning — blanks stay blank until the content team
fills them and sets reviewed=true.
"""

from __future__ import annotations

import sqlite3

import yaml

from . import pilot
from .config import CONFIG_DIR

ROUTING_YAML = CONFIG_DIR / "carc_rarc_plain_english.yaml"


def load_code_explanations(
    app_conn: sqlite3.Connection,
    pilot_conn: sqlite3.Connection,
    yaml_path=ROUTING_YAML,
) -> int:
    """Upsert all YAML entries into code_explanations. Returns the row count."""
    with open(yaml_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    rows = doc.get("codes", [])
    for entry in rows:
        code = entry["code"]
        code_type = entry["code_type"]
        text = pilot.official_text(pilot_conn, code, code_type)
        app_conn.execute(
            """
            INSERT INTO code_explanations
                (code, code_type, official_text, plain_explanation, practical_meaning,
                 commonly_disputable, suggested_action, rank_frequency, reviewed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, code_type) DO UPDATE SET
                official_text      = excluded.official_text,
                plain_explanation  = excluded.plain_explanation,
                practical_meaning  = excluded.practical_meaning,
                commonly_disputable = excluded.commonly_disputable,
                suggested_action   = excluded.suggested_action,
                rank_frequency     = excluded.rank_frequency,
                reviewed           = excluded.reviewed
            """,
            (
                code,
                code_type,
                text,
                entry.get("plain_explanation", "") or "",
                entry.get("practical_meaning", "") or "",
                int(bool(entry.get("commonly_disputable", False))),
                entry["suggested_action"],
                entry.get("rank_frequency"),
                int(bool(entry.get("reviewed", False))),
            ),
        )
    app_conn.commit()
    return len(rows)
