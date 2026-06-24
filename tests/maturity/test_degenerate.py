"""Degenerate-input handling (partial — unsound case only).

The "empty" and "single-task" cases are deferred to task #3 (new models).
This file pins the unsound-net handling that already ships: comparing
``and_gateway_no_join.bpmn`` (no join, AND-split deadlocks) against a
sound counterpart MUST return a finite score rather than raise.

The behavior itself is covered in detail by
``tests/test_graceful_unsound_petri.py``; the assertion below is a
maturity-suite checkpoint that the gracefulness is observable at the
similarity-API layer, not just in the explorer.
"""

import math

import pytest

from bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces

from .conftest import EXAMPLES, _load


def test_unsound_vs_sound_returns_finite_score():
    unsound = _load(EXAMPLES / "and_gateway_no_join.bpmn")
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")

    structural = calculate_bpmn_similarity(unsound, sound, method="dice")
    assert structural["overall"] is not None
    assert 0.0 <= structural["overall"] <= 1.0
    assert math.isfinite(structural["overall"])

    res_unsound = extract_traces(unsound, timeout_seconds=3.0, max_loop_depth=3)
    res_sound = extract_traces(sound, timeout_seconds=3.0, max_loop_depth=3)
    trace = calculate_trace_similarity(res_unsound, res_sound, method="jaccard")
    # Trace can legitimately be None if the unsound side produced no
    # variants at all; either way it must NOT raise.
    assert trace is None or (0.0 <= trace <= 1.0)


@pytest.mark.skip(reason="empty + single-task fixtures authored in task #3")
def test_empty_and_single_task_models_handled_gracefully():
    """Placeholder for ``examples/maturity/degenerate/empty.*`` and ``single_task.*``."""
