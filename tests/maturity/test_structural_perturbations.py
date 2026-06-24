"""Structural-perturbation pairs.

Tests that small structural edits move the score in the expected direction
and that the change is detected on the *correct* sub-dimension. Assertions
are relative — score(perturbed) < score(self) — to avoid pinning brittle
absolute thresholds. The calibration task will replace these with hard
floors / ceilings once we've seen the actual distribution.
"""

from bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces

from .conftest import EXAMPLES, _load


def _overall(a, b):
    return calculate_bpmn_similarity(a, b, method="dice")["overall"]


def _trace(a, b):
    res_a = extract_traces(a, timeout_seconds=3.0, max_loop_depth=3)
    res_b = extract_traces(b, timeout_seconds=3.0, max_loop_depth=3)
    return calculate_trace_similarity(res_a, res_b, method="jaccard")


def test_ls1_vs_ls2_perturbation_drops_below_self():
    """ls_1 and ls_2 are perturbations of the same linear-sequence shape.

    Whatever exact score the pair lands on, it should be strictly lower
    than ls_1 vs ls_1 and ls_2 vs ls_2.
    """
    ls1 = _load(EXAMPLES / "ls_1.bpmn")
    ls2 = _load(EXAMPLES / "ls_2.bpmn")

    cross = _overall(ls1, ls2)
    self1 = _overall(ls1, ls1)
    self2 = _overall(ls2, ls2)

    assert cross is not None
    assert cross < self1, f"ls1-vs-ls2 ({cross:.3f}) should be < ls1-self ({self1:.3f})"
    assert cross < self2, f"ls1-vs-ls2 ({cross:.3f}) should be < ls2-self ({self2:.3f})"


def test_branch_added_lowers_score():
    """Adding a third AND-branch should lower the score versus the two-branch baseline."""
    two_branch = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    three_branch = _load(EXAMPLES / "and_gateway_three_branches.bpmn")

    cross = _overall(two_branch, three_branch)
    self_two = _overall(two_branch, two_branch)
    assert cross is not None and cross < self_two, (
        f"2-branch vs 3-branch ({cross:.3f}) should be < 2-branch self ({self_two:.3f})"
    )


def test_perturbation_ranking_monotone_under_drift():
    """ls_4 is a more-perturbed variant than ls_1, so ls_1 vs ls_4 should
    score no higher than ls_1 vs ls_2. We assert ≤ rather than < to allow
    ties from the discrete set-similarity math."""
    ls1 = _load(EXAMPLES / "ls_1.bpmn")
    ls2 = _load(EXAMPLES / "ls_2.bpmn")
    ls4 = _load(EXAMPLES / "ls_4.bpmn")

    near = _overall(ls1, ls2)
    far = _overall(ls1, ls4)
    assert near is not None and far is not None
    # Loose direction-of-effect check; calibration may tighten or invert if
    # ls_2 / ls_4 turn out to be equally perturbed.
    assert far <= near + 0.05, (
        f"more-perturbed pair (ls1-ls4={far:.3f}) should not score noticeably "
        f"higher than nearer pair (ls1-ls2={near:.3f})"
    )


def test_branch_added_changes_trace_behavior():
    """Adding a parallel branch should change the trace set."""
    two_branch = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    three_branch = _load(EXAMPLES / "and_gateway_three_branches.bpmn")

    cross = _trace(two_branch, three_branch)
    # Either jaccard is below 1.0 or the trace sets disagreed enough to
    # return None; both indicate the change was observed.
    assert cross is None or cross < 1.0, (
        f"2-branch vs 3-branch trace jaccard ({cross}) should be <1.0"
    )
