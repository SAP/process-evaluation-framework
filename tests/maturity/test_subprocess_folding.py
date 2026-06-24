"""Subprocess folding — flat vs. expanded subprocess.

Two fixtures (under ``examples/maturity/subprocess_folding/``):

- ``flat.bpmn`` — five tasks in a single linear chain (Pick → Pack →
  Label → Load → Dispatch).
- ``with_subprocess.bpmn`` — the same five labels, but the middle three
  (Pack, Label, Load) are nested inside an expanded subprocess between
  the two outer tasks (Pick and Dispatch).

What we expect:

- Aggregated structural score: lower than 1.0 because the subprocess
  side adds expanded-subprocess elements (and their internal flows) that
  the flat side lacks. But the activity *name* sets agree, so the
  ``elements`` sub-score stays moderately high.
- Behavioral (trace) score: depends on how the trace extractor handles
  the subprocess. We don't pin the absolute number; we just check that
  comparison completes without raising.
- The pair should score above pure-disjoint and below identical —
  i.e. land in a "structurally similar but not equal" band.
"""

import math

from bpmn_similarity import calculate_bpmn_similarity, calculate_trace_similarity
from trace_extraction import extract_traces

from .conftest import SANITY, SUBPROCESS_FOLDING, _load


def test_flat_vs_subprocess_overall_in_mid_band():
    flat = _load(SUBPROCESS_FOLDING / "flat.bpmn")
    sp = _load(SUBPROCESS_FOLDING / "with_subprocess.bpmn")
    overall = calculate_bpmn_similarity(flat, sp, method="dice")["overall"]
    assert overall is not None
    assert 0.3 <= overall <= 0.95, (
        f"flat vs subprocess overall = {overall:.3f}; expected in [0.3, 0.95]"
    )


def test_flat_vs_subprocess_elements_score_remains_high():
    """The activity-name sets agree, so the ``elements`` sub-score should
    sit high even when the aggregated overall is pulled down by the
    structural difference."""
    flat = _load(SUBPROCESS_FOLDING / "flat.bpmn")
    sp = _load(SUBPROCESS_FOLDING / "with_subprocess.bpmn")
    result = calculate_bpmn_similarity(flat, sp, method="dice")
    elements = result["high_level_scores"].get("elements")
    assert elements is not None
    assert elements >= 0.5, (
        f"elements sub-score = {elements:.3f}; expected ≥0.5 since the "
        f"task-name sets overlap"
    )


def test_flat_vs_subprocess_scores_above_disjoint_baseline():
    flat = _load(SUBPROCESS_FOLDING / "flat.bpmn")
    sp = _load(SUBPROCESS_FOLDING / "with_subprocess.bpmn")
    credit = _load(SANITY / "disjoint_left_credit.bpmn")
    student = _load(SANITY / "disjoint_right_student.bpmn")
    pair = calculate_bpmn_similarity(flat, sp, method="dice")["overall"]
    disjoint = calculate_bpmn_similarity(credit, student, method="dice")["overall"]
    assert pair > disjoint, (
        f"flat-vs-subprocess ({pair:.3f}) should exceed disjoint baseline "
        f"({disjoint:.3f})"
    )


def test_flat_vs_subprocess_trace_extraction_finite():
    flat = _load(SUBPROCESS_FOLDING / "flat.bpmn")
    sp = _load(SUBPROCESS_FOLDING / "with_subprocess.bpmn")
    res_flat = extract_traces(flat, timeout_seconds=3.0, max_loop_depth=3)
    res_sp = extract_traces(sp, timeout_seconds=3.0, max_loop_depth=3)
    score = calculate_trace_similarity(res_flat, res_sp, method="jaccard")
    # Trace extraction over a subprocess may legitimately return 0 or
    # None depending on how subprocess delimiters surface in the trace
    # tuples — we only require that no NaN/Inf leaks through.
    assert score is None or (0.0 <= score <= 1.0 and math.isfinite(score))


def test_subprocess_model_has_expanded_subprocess_flag():
    """The structural pipeline should detect the expanded subprocess."""
    flat = _load(SUBPROCESS_FOLDING / "flat.bpmn")
    sp = _load(SUBPROCESS_FOLDING / "with_subprocess.bpmn")
    result = calculate_bpmn_similarity(flat, sp, method="dice")
    assert result["has_expanded_subprocess"], (
        "expected has_expanded_subprocess=True when one side has an "
        "expanded subprocess"
    )
