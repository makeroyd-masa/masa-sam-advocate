"""Code-type detection + denial-code parsing (format heuristics).

These feed the Stage-3 inline auto-detect chip (`bill_lines.detected_code_type`)
and Stage-2/4 denial-code capture. Detection is BEST-EFFORT from format; the
authoritative resolution is verifying against pilot.db (see app.pilot.lookup_code).
Some short numerics are genuinely ambiguous (e.g. "50" is a CARC *and* a POS), so
callers pass context where they have it.
"""

from __future__ import annotations

import re

# schema bill_lines.detected_code_type enum
_HCPCS = re.compile(r"[A-V]\d{4}")              # letter + 4 digits, e.g. A0429, J1885
_CPT_CAT_I = re.compile(r"\d{5}")               # 5 digits, e.g. 99214 (not stored — AMA)
_CPT_CAT_II_III = re.compile(r"\d{4}[FTUM]")    # e.g. 0500F, 0042T
_ICD10CM = re.compile(r"[A-TV-Z]\d[0-9A-Z](\.[0-9A-Z]{1,4})?")
_ICD10PCS = re.compile(r"[0-9A-HJ-NP-Z]{7}")
_REVENUE = re.compile(r"\d{3,4}")               # 3–4 digit revenue code (ambiguous)
_RARC = re.compile(r"(MA|MB|M|N)\d+", re.IGNORECASE)


def detect_code_type(raw: str, *, context: str = "line") -> str:
    """Best-effort code-type guess for a line code.

    context='line' biases toward billable code types (HCPCS/CPT). Returns a value
    from the detected_code_type enum, or 'unknown' when the format is ambiguous.
    """
    s = (raw or "").strip().upper().replace(" ", "")
    if not s:
        return "unknown"
    if _HCPCS.fullmatch(s):
        return "HCPCS"
    if _CPT_CAT_II_III.fullmatch(s):
        return "CPT"
    if _ICD10PCS.fullmatch(s) and not s.isdigit():
        return "ICD10PCS"
    if _ICD10CM.fullmatch(s):
        return "ICD10CM"
    if _CPT_CAT_I.fullmatch(s):
        return "CPT"
    return "unknown"


def detect_denial_code_type(code: str) -> str:
    """CARC vs RARC from format. RARC codes are M*/MA*/MB*/N*; CARC are numeric or
    a few alpha-prefixed (B7, B15, W*, P*)."""
    c = (code or "").strip().upper()
    return "RARC" if _RARC.fullmatch(c) else "CARC"


_DENIAL_PREFIX = re.compile(r"^\s*(CARC|RARC)\b[:\s]*", re.IGNORECASE)


def parse_denial_code(text: str) -> tuple[str, str] | None:
    """Parse free-text denial entry like 'CARC 50', 'RARC N386', '50', 'N386'.

    Returns (code, code_type) or None if nothing code-like is found. An explicit
    'CARC'/'RARC' prefix wins; otherwise the type is inferred from format.
    """
    if not text:
        return None
    raw = text.strip()
    explicit = None
    m = _DENIAL_PREFIX.match(raw)
    if m:
        explicit = m.group(1).upper()
        raw = raw[m.end():]
    code = raw.strip().upper().replace(" ", "")
    if not code:
        return None
    code_type = explicit or detect_denial_code_type(code)
    return code, code_type
