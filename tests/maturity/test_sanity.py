"""Sanity / boundary cases for the maturity suite.

Three cases (all fixtures under ``examples/testing_models/sanity/``):

- ``identical``     — model compared to itself; every sub-score ≥ 0.95.
- ``disjoint``      — two completely unrelated models; overall ≤ 0.15.
- ``renamed_only``  — ``identical_baseline`` vs ``renamed_only_b``
  (same 3-task shape, different labels); normalized score ≥ 0.95 and
  strictly above raw.

Thresholds are intentionally loose for the first pass and will be tightened
by the calibration task after one full run.
"""

from model_evaluation import calculate_bpmn_similarity

from .conftest import SANITY, _load


def test_identical_model_scores_near_one():
    """A model compared to itself should produce ~1.0 across the board.

    Calibrated: measured overall = 1.000 across all categories. The 0.95
    floor leaves room for ID-randomization or hash-ordering drift in the
    converter without weakening the contract that "identical input →
    near-perfect score".
    """
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
    """Two unrelated business processes should score low overall.

    Calibrated threshold: measured score is ~0.09 for the credit/student
    pair, so 0.15 gives a healthy margin while still flagging any
    regression that would let an unrelated process drift into "similar"
    territory.
    """
    credit = _load(SANITY / "disjoint_left_credit.bpmn")
    student = _load(SANITY / "disjoint_right_student.bpmn")

    result = calculate_bpmn_similarity(credit, student, method="dice")

    assert result["overall"] is not None
    assert result["overall"] <= 0.15, (
        f"disjoint comparison should be ≤0.15, got {result['overall']:.3f}"
    )


def test_renamed_only_pair_recovers_under_normalization():
    """Same 3-task linear shape, second model uses different (but
    semantically equivalent) labels. Raw similarity is modest because the
    activity-name sets disagree; after ``normalize_atomic_names`` aligns
    model_b's vocabulary to model_a's, the score should jump close to 1.0.

    This is the canonical maturity claim of the framework: an authored
    rename should not look "disjoint" once you let the semantic
    normalizer line up the labels.

    The A side reuses ``identical_baseline.bpmn`` directly rather than a
    dedicated ``renamed_only_a.bpmn`` — they were byte-identical except
    for ids, and the indirection just hid the fact that ``renamed_only_b``
    is the *only* renamed fixture in this pair.
    """
    from model_evaluation import normalize_atomic_names
    from model_evaluation.utils.string_similarity import cosine_sim_optimized

    a = _load(SANITY / "identical_baseline.bpmn")
    b = _load(SANITY / "renamed_only_b.bpmn")

    raw = calculate_bpmn_similarity(a, b, method="dice")["overall"]
    aligned, _ = normalize_atomic_names(a, b, cosine_sim_optimized, threshold=0.7)
    norm = calculate_bpmn_similarity(a, aligned, method="dice")["overall"]

    assert raw is not None and norm is not None
    # Direction-of-effect is the strict assertion; the absolute floor on
    # ``norm`` is calibrated to the measured ~1.0 score with a tolerance
    # for embedding-model drift. The raw score sits around 0.28 because
    # only element *types* match (the labels diverge), so the ≥0.95
    # floor cleanly separates "normalizer worked" from "not applied".
    assert norm > raw, (
        f"renamed-only: normalization should lift the score "
        f"(raw={raw:.3f}, normalized={norm:.3f})"
    )
    assert norm >= 0.95, (
        f"renamed-only normalized score {norm:.3f} should be ≥0.95"
    )
