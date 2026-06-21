"""Ensure the repo root is importable so `from app...` works under pytest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
