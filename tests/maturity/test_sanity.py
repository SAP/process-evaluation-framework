"""Sanity / boundary cases for the maturity suite.

Three cases (all fixtures under ``examples/maturity/sanity/``):

- ``identical``  — model compared to itself; every sub-score ≥ 0.95.
- ``disjoint``   — two completely unrelated models; overall ≤ 0.3.
- ``renamed_only`` — covered by the new-models task; placeholder skip here.

Thresholds are intentionally loose for the first pass and will be tightened
by the calibration task after one full run.
"""

import pytest

from bpmn_similarity import calculate_bpmn_similarity

from .conftest import SANITY, _load


def test_identical_model_scores_near_one():
    """A model compared to itself should produce ~1.0 across the board."""
    model = _load(SANITY / "identical_baseline.bpmn")
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
    credit = _load(SANITY / "disjoint_left_credit.bpmn")
    student = _load(SANITY / "disjoint_right_student.bpmn")

    result = calculate_bpmn_similarity(credit, student, method="dice")

    assert result["overall"] is not None
    assert result["overall"] <= 0.3, (
        f"disjoint comparison should be ≤0.3, got {result['overall']:.3f}"
    )


def test_renamed_only_pair_recovers_under_normalization(embedding_model):
    """Same 3-task linear shape, second model uses different (but
    semantically equivalent) labels. Raw similarity is modest because the
    activity-name sets disagree; after ``normalize_atomic_names`` aligns
    model_b's vocabulary to model_a's, the score should jump close to 1.0.

    This is the canonical maturity claim of the framework: an authored
    rename should not look "disjoint" once you let the semantic
    normalizer line up the labels.
    """
    from bpmn_normalization import normalize_atomic_names
    from utils.string_similarity import cosine_sim_optimized

    a = _load(SANITY / "renamed_only_a.bpmn")
    b = _load(SANITY / "renamed_only_b.bpmn")

    raw = calculate_bpmn_similarity(a, b, method="dice")["overall"]
    aligned, _ = normalize_atomic_names(a, b, cosine_sim_optimized, threshold=0.7)
    norm = calculate_bpmn_similarity(a, aligned, method="dice")["overall"]

    assert raw is not None and norm is not None
    # Direction-of-effect is the strict assertion; the absolute floor on
    # ``norm`` is loose enough to survive embedding-model drift.
    assert norm > raw, (
        f"renamed-only: normalization should lift the score "
        f"(raw={raw:.3f}, normalized={norm:.3f})"
    )
    assert norm >= 0.7, (
        f"renamed-only normalized score {norm:.3f} should be ≥0.7"
    )
