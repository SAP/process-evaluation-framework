"""Pytest configuration for the model_evaluation test suite."""

import sys
from pathlib import Path

# Make `model_evaluation` and its flat-layout submodules importable regardless
# of how pytest is invoked. Mirrors the pyproject.toml `pythonpath` setting.
ROOT = Path(__file__).resolve().parent.parent
MODEL_EVAL = ROOT / "model_evaluation"
for path in (str(ROOT), str(MODEL_EVAL)):
    if path not in sys.path:
        sys.path.insert(0, path)
