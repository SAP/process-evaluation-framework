"""Structural-perturbation pairs.

All fixtures under ``examples/maturity/structural_perturbations/``:

- ``linear_baseline.bpmn`` / ``linear_reorder.bpmn`` / ``linear_drift.bpmn``
  — increasingly perturbed linear sequences (copies of repo's ls_1/2/4).
- ``and_two_branches.bpmn`` / ``and_three_branches.bpmn`` — same shape,
  one extra parallel branch on the right.

Assertions are relative — score(perturbed) < score(self) — to avoid
pinning brittle absolute thresholds. The calibration task will replace
these with hard floors / ceilings once we've seen the actual distribution.
"""

from bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces

from .conftest import STRUCTURAL_PERTURBATIONS, _load


def _overall(a, b):
    return calculate_bpmn_similarity(a, b, method="dice")["overall"]


def _trace(a, b):
    res_a = extract_traces(a, timeout_seconds=3.0, max_loop_depth=3)
    res_b = extract_traces(b, timeout_seconds=3.0, max_loop_depth=3)
    return calculate_trace_similarity(res_a, res_b, method="jaccard")


def test_linear_baseline_vs_reorder_drops_below_self():
    """A reordered linear sequence should score below either self-pair."""
    base = _load(STRUCTURAL_PERTURBATIONS / "linear_baseline.bpmn")
    reorder = _load(STRUCTURAL_PERTURBATIONS / "linear_reorder.bpmn")

    cross = _overall(base, reorder)
    self_base = _overall(base, base)
    self_reorder = _overall(reorder, reorder)

    assert cross is not None
    assert cross < self_base, (
        f"baseline-vs-reorder ({cross:.3f}) should be < baseline-self ({self_base:.3f})"
    )
    assert cross < self_reorder, (
        f"baseline-vs-reorder ({cross:.3f}) should be < reorder-self ({self_reorder:.3f})"
    )


def test_branch_added_lowers_score():
    """Adding a third AND-branch should lower the score versus the two-branch baseline."""
    two_branch = _load(STRUCTURAL_PERTURBATIONS / "and_two_branches.bpmn")
    three_branch = _load(STRUCTURAL_PERTURBATIONS / "and_three_branches.bpmn")

    cross = _overall(two_branch, three_branch)
    self_two = _overall(two_branch, two_branch)
    assert cross is not None and cross < self_two, (
        f"2-branch vs 3-branch ({cross:.3f}) should be < 2-branch self ({self_two:.3f})"
    )


def test_perturbation_ranking_monotone_under_drift():
    """``linear_drift`` is a more-perturbed variant than ``linear_reorder``,
    so baseline-vs-drift should score strictly below baseline-vs-reorder.

    Calibrated: measured scores are 0.174 (drift) vs 0.268 (reorder),
    a 0.094 gap in the correct direction. We assert ``<`` rather than
    ``≤`` to detect any regression that would put the more-perturbed pair
    at or above the nearer pair.
    """
    base = _load(STRUCTURAL_PERTURBATIONS / "linear_baseline.bpmn")
    reorder = _load(STRUCTURAL_PERTURBATIONS / "linear_reorder.bpmn")
    drift = _load(STRUCTURAL_PERTURBATIONS / "linear_drift.bpmn")

    near = _overall(base, reorder)
    far = _overall(base, drift)
    assert near is not None and far is not None
    assert far < near, (
        f"more-perturbed pair (baseline-drift={far:.3f}) should score "
        f"strictly below nearer pair (baseline-reorder={near:.3f})"
    )


def test_branch_added_changes_trace_behavior():
    """Adding a parallel branch should change the trace set."""
    two_branch = _load(STRUCTURAL_PERTURBATIONS / "and_two_branches.bpmn")
    three_branch = _load(STRUCTURAL_PERTURBATIONS / "and_three_branches.bpmn")

    cross = _trace(two_branch, three_branch)
    # Either jaccard is below 1.0 or the trace sets disagreed enough to
    # return None; both indicate the change was observed.
    assert cross is None or cross < 1.0, (
        f"2-branch vs 3-branch trace jaccard ({cross}) should be <1.0"
    )
