"""Pytest configuration for the maturity test suite.

Adds:

- A session-scoped fixture that pre-warms the sentence-transformer used by
  ``utils.string_similarity.bert_cosine_optimized``. The model is loaded at
  module import time today, but pinning it through a fixture makes the
  one-time cost explicit in test timing and gives us a single hook to swap
  in a stub model if the suite ever needs to run without a network.

- A ``_load(path)`` helper mirroring ``tests/test_graceful_unsound_petri.py``
  so every maturity test goes through the same loader the dashboard uses.

- An ``EXAMPLES`` constant pointing at the repo's existing ``examples/``
  directory.
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure ``model_evaluation`` flat-layout modules import cleanly when pytest
# collects this subdirectory before the top-level tests/conftest.py runs.
# Mirrors pyproject.toml's ``pythonpath`` setting and tests/conftest.py.
_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_EVAL = _ROOT / "model_evaluation"
for _path in (str(_ROOT), str(_MODEL_EVAL)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from BPMN_conversion import BPMNConverter, XMLBPMNConverter  # noqa: E402


# All maturity fixtures live under examples/maturity/<category>/. Category
# constants are exposed so individual test files don't have to repeat the
# path joining (and so a folder rename touches one line).
EXAMPLES = _ROOT / "examples"
MATURITY = EXAMPLES / "maturity"
SANITY = MATURITY / "sanity"
GATEWAY_SUBSTITUTIONS = MATURITY / "gateway_substitutions"
STRUCTURAL_PERTURBATIONS = MATURITY / "structural_perturbations"
SEMANTIC_NAMING = MATURITY / "semantic_naming"
SUBPROCESS_FOLDING = MATURITY / "subprocess_folding"
FORMAT_ROUND_TRIP = MATURITY / "format_round_trip"
DEGENERATE = MATURITY / "degenerate"


def _load(path: Path):
    """Mirror ``comparison_widget._load_model`` and the unsound-net tests.

    XML / BPMN files go through ``XMLBPMNConverter``; everything else is
    treated as Signavio-style JSON.
    """
    if path.suffix in (".xml", ".bpmn"):
        return XMLBPMNConverter.convert_file(str(path)).to_dict()
    with path.open("r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


@pytest.fixture(scope="session")
def load_model():
    """Expose ``_load`` as a fixture for readability inside tests."""
    return _load


@pytest.fixture(scope="session")
def embedding_model():
    """Session-scoped handle on the sentence-transformer.

    Today the model is a module-level singleton in
    ``utils.string_similarity``; importing the module loads it. We import
    inside the fixture so the load time shows up in ``--durations`` against
    this fixture rather than scattered across the first semantic test.
    """
    from utils import string_similarity  # noqa: F401  (import is the point)
    return string_similarity
