"""Settings + YAML config loading.

Two databases (CLAUDE.md / PRD §1.2): a read-only reference `pilot.db` and the
app's writable `app.db`. Paths come from the environment (see env.example),
defaulting to the repo-local locations. YAML config (pricing tiers, feature
flags, POS map, escalation, the §5 routing layer) lives in `config/`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _resolve(path_str: str) -> Path:
    """Resolve a configured DB path; relative paths are anchored at the repo root."""
    p = Path(path_str)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Match env.example. pydantic-settings reads PILOT_DB_PATH / APP_DB_PATH.
    pilot_db_path: str = "./data/pilot.db"
    app_db_path: str = "./app.db"

    @property
    def pilot_db_file(self) -> Path:
        return _resolve(self.pilot_db_path)

    @property
    def app_db_file(self) -> Path:
        return _resolve(self.app_db_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# YAML config accessors (cached). Files live in config/.
# ---------------------------------------------------------------------------
@lru_cache
def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def feature_flags() -> dict:
    """App-layer gates (NSA off, air off, letter gen off). PRD §8."""
    return _load_yaml("feature_flags.yaml").get("flags", {})


def pricing_thresholds() -> dict:
    """Flow 2 above-benchmark tier bands. PRD §6.2."""
    return _load_yaml("pricing_thresholds.yaml")


def pos_facility_map() -> dict:
    """POS → PFS facility/non_facility column rule. PRD §6.2."""
    return _load_yaml("pos_facility_map.yaml")


def escalation_config() -> dict:
    """Human-advocate handoff triggers. PRD §7.7."""
    return _load_yaml("escalation.yaml")
