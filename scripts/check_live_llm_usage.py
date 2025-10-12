"""
Simple grep-style check to find backend/adapters files that contain direct references
to ENABLE_*, LIVE_LLM, or provider-specific ENABLE_* flags instead of using
backend.llm_utils.is_live_llm_enabled.

Exit code 0: no matches found
Exit code 1: matches found (prints file:line snippets)

Intended for CI to run as an early safety guard to avoid accidental live LLM calls.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS_DIR = ROOT / "backend" / "adapters"

PATTERNS = [
    re.compile(r"\bENABLE_\w+\b"),
    re.compile(r"\bLIVE_LLM\b"),
    re.compile(r"\bLIVE_HTTP\b"),
]

IGNORE_FILES = {"__init__.py"}

matches = []
for p in ADAPTERS_DIR.glob("**/*.py"):
    if p.name in IGNORE_FILES:
        continue
    text = p.read_text(encoding="utf-8")
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            # Filter out the approved helper usage
            if "is_live_llm_enabled" in text:
                # if the file already calls helper, likely OK; still report only direct env checks
                # but skip matches inside comments that mention ENABLE_* in docs
                pass
            line_no = text.count("\n", 0, m.start()) + 1
            snippet = text.splitlines()[line_no - 1].strip()
            matches.append(f"{p.relative_to(ROOT)}:{line_no}: {snippet}")

if matches:
    print("Found potential direct live-LLM/env checks in adapters:")
    for m in matches:
        print(m)
    sys.exit(1)
else:
    print("No direct enablement-env references found in backend/adapters.")
    sys.exit(0)
