"""Pytest configuration for the maturity test suite.

Adds:

- A ``_load(path)`` helper mirroring ``tests/petri/test_petri_soundness.py``
  so every maturity test goes through the same loader the dashboard uses.

- Path constants (``EXAMPLES``, ``MATURITY``, ``SANITY``,
  ``FORMAT_ROUND_TRIP``, ``DEGENERATE``) so individual test files don't
  repeat path joining and a folder rename touches one line.
"""

from pathlib import Path

from model_evaluation import load_bpmn as _load  # re-exported for tests


_ROOT = Path(__file__).resolve().parent.parent.parent

# All maturity fixtures live under examples/maturity/<category>/. Category
# constants are exposed so individual test files don't have to repeat the
# path joining (and so a folder rename touches one line).
EXAMPLES = _ROOT / "examples"
MATURITY = EXAMPLES / "maturity"
SANITY = MATURITY / "sanity"
FORMAT_ROUND_TRIP = MATURITY / "format_round_trip"
DEGENERATE = MATURITY / "degenerate"

__all__ = [
    "_load",
    "EXAMPLES",
    "MATURITY",
    "SANITY",
    "FORMAT_ROUND_TRIP",
    "DEGENERATE",
]
