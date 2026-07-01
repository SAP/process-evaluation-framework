"""Degenerate-input handling for the maturity suite.

Four cases (all fixtures under ``examples/maturity/degenerate/``):

- ``unsound_vs_sound``  — ``unsound_and_no_join.bpmn`` (AND-split with
  no join, deadlocks) compared to ``sound_and_with_join.bpmn`` must
  return a finite structural score and a non-raising trace score.
  Tighter behavioral coverage lives in
  ``tests/petri/test_petri_soundness.py``; the assertion below is a
  maturity-suite checkpoint that the gracefulness is observable at the
  similarity-API layer, not just in the explorer.
- ``empty self-compare``      — ``empty.bpmn`` (start → end, no tasks)
  against itself: finite score, no crash.
- ``single-task self-compare`` — ``single_task.bpmn`` against itself
  is ~1.0 (identical).
- ``empty vs single-task``    — exercises the "one side is sparse" path
  on both structural and trace similarity.
"""

import math

import pytest

from bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces

from .conftest import DEGENERATE, _load


def test_unsound_vs_sound_returns_finite_score():
    unsound = _load(DEGENERATE / "unsound_and_no_join.bpmn")
    sound = _load(DEGENERATE / "sound_and_with_join.bpmn")

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


def test_empty_model_self_comparison_is_finite_and_safe():
    """A ``start → end`` model (no tasks) compared to itself must return
    a finite score without crashing.

    The math layer's convention is that two empty sets compare as 1.0,
    so we expect ~1.0 here, but the assertion only requires finiteness
    so that an upstream change that returns ``None`` for the all-empty
    case (also defensible) doesn't break this test."""
    empty = _load(DEGENERATE / "empty.bpmn")
    result = calculate_bpmn_similarity(empty, empty, method="dice")
    overall = result["overall"]
    assert overall is None or (0.0 <= overall <= 1.0 and math.isfinite(overall))


def test_single_task_model_self_comparison_is_perfect():
    """A trivial ``start → task → end`` model is identical to itself."""
    single = _load(DEGENERATE / "single_task.bpmn")
    result = calculate_bpmn_similarity(single, single, method="dice")
    assert result["overall"] == pytest.approx(1.0)


def test_empty_vs_single_task_returns_finite_score():
    """Comparing an empty model to a single-task model exercises the
    "one side is sparse" code path. It must not crash and must return a
    finite, in-range number."""
    empty = _load(DEGENERATE / "empty.bpmn")
    single = _load(DEGENERATE / "single_task.bpmn")
    result = calculate_bpmn_similarity(empty, single, method="dice")
    overall = result["overall"]
    assert overall is not None
    assert 0.0 <= overall <= 1.0 and math.isfinite(overall)

    # Trace similarity should also survive — empty side has no variants,
    # single-task side has one. The math layer returns ``None`` or a
    # finite number; both are acceptable, NaN/raise is not.
    res_empty = extract_traces(empty, timeout_seconds=3.0, max_loop_depth=3)
    res_single = extract_traces(single, timeout_seconds=3.0, max_loop_depth=3)
    trace = calculate_trace_similarity(res_empty, res_single, method="jaccard")
    assert trace is None or (0.0 <= trace <= 1.0 and math.isfinite(trace))
