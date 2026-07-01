"""Pytest configuration for the maturity test suite.

Adds:

- A ``_load(path)`` helper mirroring ``tests/test_graceful_unsound_petri.py``
  so every maturity test goes through the same loader the dashboard uses.

- Path constants (``EXAMPLES``, ``MATURITY``, ``SANITY``,
  ``FORMAT_ROUND_TRIP``, ``DEGENERATE``) so individual test files don't
  repeat path joining and a folder rename touches one line.
"""

import json
from pathlib import Path

from model_evaluation import BPMNConverter, XMLBPMNConverter


_ROOT = Path(__file__).resolve().parent.parent.parent

# All maturity fixtures live under examples/maturity/<category>/. Category
# constants are exposed so individual test files don't have to repeat the
# path joining (and so a folder rename touches one line).
EXAMPLES = _ROOT / "examples"
MATURITY = EXAMPLES / "maturity"
SANITY = MATURITY / "sanity"
FORMAT_ROUND_TRIP = MATURITY / "format_round_trip"
DEGENERATE = MATURITY / "degenerate"


def _load(path: Path):
    """Mirror ``comparison_widget._load_model`` and the unsound-net tests.

    XML / BPMN files go through ``XMLBPMNConverter``; everything else is
    treated as Signavio-style JSON. Suffix matching is case-insensitive
    to match ``notebooks/dashboard.py``'s loader.
    """
    if path.suffix.lower() in (".xml", ".bpmn"):
        return XMLBPMNConverter.convert_file(str(path)).to_dict()
    with path.open("r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()
