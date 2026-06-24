"""Sanity / boundary cases for the maturity suite.

Three cases:

- ``identical``  — model compared to itself; every sub-score ≥ 0.95.
- ``disjoint``   — two completely unrelated models; overall ≤ 0.3.
- ``renamed_only`` — covered by the new-models task; placeholder skip here.

Thresholds are intentionally loose for the first pass and will be tightened
by the calibration task after one full run.
"""

import pytest

from bpmn_similarity import calculate_bpmn_similarity

from .conftest import EXAMPLES, _load


def test_identical_model_scores_near_one():
    """A model compared to itself should produce ~1.0 across the board."""
    model = _load(EXAMPLES / "linear_sequence.bpmn")
    result = calculate_bpmn_similarity(model, model, method="dice")

    assert result["overall"] is not None
    assert result["overall"] >= 0.95, (
        f"identical comparison should be ≥0.95, got {result['overall']:.3f}"
    )
    for key, value in result["high_level_scores"].items():
        if value is None:
            continue  # category not present in this model
        assert value >= 0.95, (
            f"identical comparison: high-level '{key}' = {value:.3f} (<0.95)"
        )


def test_disjoint_models_score_low():
    """Two unrelated business processes should score low overall."""
    credit = _load(EXAMPLES / "credit.bpmn")
    student = _load(EXAMPLES / "student_project.bpmn")

    result = calculate_bpmn_similarity(credit, student, method="dice")

    assert result["overall"] is not None
    assert result["overall"] <= 0.3, (
        f"disjoint comparison should be ≤0.3, got {result['overall']:.3f}"
    )


@pytest.mark.skip(reason="renamed-only pair authored in the 'new models' task")
def test_renamed_only_pair_high_structural_low_naming():
    """Placeholder — same structure, renamed elements.

    Will be wired up against ``examples/maturity/sanity/renamed_only_*``
    once those models exist (task #3).
    """
