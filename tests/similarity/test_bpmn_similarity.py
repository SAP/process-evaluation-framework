"""Algebraic contract tests for the top-level similarity functions.

These are the invariants a reviewer might explicitly ask you to prove
for the paper — that the numbers behave the way similarity metrics
should:

  * ``calculate_bpmn_similarity``  — self=1, symmetry for symmetric
    metrics, precision(A,B) == recall(B,A), correct weight-picking
    based on subprocess presence, weight-validation rejects bad input,
    None on empty-vs-empty.
  * ``calculate_trace_similarity`` — same self/symmetry contract, plus
    the "None on both-empty" convention documented in the source.
  * ``calculate_hybrid_similarity`` — exact weighted-sum math when both
    sides are numbers, None-propagation when one/both are None, weight
    validation.

Fixtures are hand-authored minimal BPMN dicts constructed inline so
this file has zero fixture-file coupling — the failure signal is
always about the math, not the loader. Complementary to
``tests/maturity/test_sanity.py`` (which does the same checks
end-to-end on real BPMN files); if the maturity numbers drift, this
file localises the failure to the math layer vs. the loader / set
extractor.
"""

import pytest

from model_evaluation.bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_hybrid_similarity,
    calculate_ngram_similarity,
    calculate_trace_similarity,
)


# ---------------------------------------------------------------------------
# Minimal BPMN dict fixtures
# ---------------------------------------------------------------------------

def _minimal(activities=None, events=None, gateways=None,
             seq_flows=None, message_flows=None, pools=None):
    """Build the smallest legal BPMN dict shape the pipeline consumes.

    Every top-level list defaults to empty so a test can wire up just
    the aspect it cares about (activities-only, flows-only, …).
    """
    return {
        "activities": activities or [],
        "events": events or [],
        "gateways": gateways or [],
        "sequenceFlows": seq_flows or [],
        "messageFlows": message_flows or [],
        "pools": pools or [],
    }


# Two-activity linear model: start → Review → Approve → end
MODEL_A = _minimal(
    activities=[
        {"id": "a1", "name": "Review", "type": "Task"},
        {"id": "a2", "name": "Approve", "type": "Task"},
    ],
    events=[
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    seq_flows=[
        {"sourceRef": "e1", "targetRef": "a1"},
        {"sourceRef": "a1", "targetRef": "a2"},
        {"sourceRef": "a2", "targetRef": "e2"},
    ],
)


# Structurally identical to MODEL_A but different ids — the extractor
# must ignore ids and compare by name/type, so overall should still be
# 1.0. Guards against a regression where the set builder starts
# leaking ids into the comparable string.
MODEL_A_COPY = _minimal(
    activities=[
        {"id": "xREVIEW", "name": "Review", "type": "Task"},
        {"id": "xAPPROVE", "name": "Approve", "type": "Task"},
    ],
    events=[
        {"id": "xSTART", "name": "Start", "type": "StartNoneEvent"},
        {"id": "xEND", "name": "End", "type": "EndNoneEvent"},
    ],
    seq_flows=[
        {"sourceRef": "xSTART", "targetRef": "xREVIEW"},
        {"sourceRef": "xREVIEW", "targetRef": "xAPPROVE"},
        {"sourceRef": "xAPPROVE", "targetRef": "xEND"},
    ],
)


# Distinct model with only the start/end labels in common with MODEL_A.
MODEL_B = _minimal(
    activities=[
        {"id": "b1", "name": "Log", "type": "Task"},
        {"id": "b2", "name": "Cancel", "type": "Task"},
    ],
    events=[
        {"id": "eb1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "eb2", "name": "End", "type": "EndNoneEvent"},
    ],
    seq_flows=[
        {"sourceRef": "eb1", "targetRef": "b1"},
        {"sourceRef": "b1", "targetRef": "b2"},
        {"sourceRef": "b2", "targetRef": "eb2"},
    ],
)


# Contains an expanded subprocess — flips ``has_expanded_subprocess``
# and therefore the default-weight branch.
MODEL_WITH_SUBPROCESS = _minimal(
    activities=[
        {
            "id": "sub1",
            "name": "Review Subprocess",
            "type": "Subprocess",
            "elemRefs": ["inner1"],
            "subprocessSequenceFlows": [],
        },
        {"id": "inner1", "name": "Inner Task", "type": "Task"},
    ],
    events=[
        {"id": "e1", "name": "Start", "type": "StartNoneEvent"},
        {"id": "e2", "name": "End", "type": "EndNoneEvent"},
    ],
    seq_flows=[
        {"sourceRef": "e1", "targetRef": "sub1"},
        {"sourceRef": "sub1", "targetRef": "e2"},
    ],
)


EMPTY_MODEL = _minimal()


# Symmetric metric names for the metrics whose formula is symmetric in
# its two arguments. ``precision`` and ``recall`` are deliberately
# excluded — they're asymmetric by definition and swapping arguments
# swaps their roles (see ``test_precision_of_ab_equals_recall_of_ba``).
SYMMETRIC_METHODS = ("dice", "jaccard", "overlap")
ALL_METHODS = SYMMETRIC_METHODS + ("precision", "recall")


# ---------------------------------------------------------------------------
# calculate_bpmn_similarity — invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ALL_METHODS)
def test_bpmn_self_similarity_is_one(method):
    """Any method against a copy of the same model must be exactly 1.0.
    Structural identity is the anchor of every downstream number; if
    it drifts, every "identical" test in maturity/ starts to look
    suspicious for the wrong reason."""
    r = calculate_bpmn_similarity(MODEL_A, MODEL_A_COPY, method=method)
    assert r["overall"] == pytest.approx(1.0)


@pytest.mark.parametrize("method", SYMMETRIC_METHODS)
def test_bpmn_symmetry_for_symmetric_methods(method):
    """dice / jaccard / overlap must produce the same overall
    regardless of argument order. If this drifts, an asymmetry has crept
    into the extraction or grouping layer."""
    ab = calculate_bpmn_similarity(MODEL_A, MODEL_B, method=method)["overall"]
    ba = calculate_bpmn_similarity(MODEL_B, MODEL_A, method=method)["overall"]
    assert ab == pytest.approx(ba)


def test_bpmn_precision_of_ab_equals_recall_of_ba():
    """The load-bearing identity for the asymmetric pair: swapping the
    model order turns precision into recall. If it breaks, every
    downstream number using ``method="precision"`` is silently wrong."""
    p = calculate_bpmn_similarity(MODEL_A, MODEL_B, method="precision")["overall"]
    r = calculate_bpmn_similarity(MODEL_B, MODEL_A, method="recall")["overall"]
    assert p == pytest.approx(r)


def test_bpmn_overall_returns_none_when_both_models_are_empty():
    """The math-layer convention: if there is nothing to compare, return
    None rather than the bogus 1.0 that Dice/Jaccard would produce over
    empty sets. Downstream code (dashboard, hybrid combiner) branches on
    this None."""
    r = calculate_bpmn_similarity(EMPTY_MODEL, EMPTY_MODEL, method="dice")
    assert r["overall"] is None


def test_bpmn_default_weights_when_no_expanded_subprocess():
    """The default-weight table is a paper-facing knob. Any tweak must
    be explicit; pin the current values so silent drift is impossible.
    When there is no expanded subprocess the ``subprocess`` weight
    redistributes onto ``organizational``."""
    r = calculate_bpmn_similarity(MODEL_A, MODEL_B, method="dice")
    assert r["has_expanded_subprocess"] is False
    assert r["weights_used"] == {
        "elements": 0.3,
        "flows": 0.5,
        "organizational": 0.2,
        "subprocess": 0.0,
    }


def test_bpmn_default_weights_when_expanded_subprocess_present():
    r = calculate_bpmn_similarity(
        MODEL_WITH_SUBPROCESS, MODEL_WITH_SUBPROCESS, method="dice"
    )
    assert r["has_expanded_subprocess"] is True
    assert r["weights_used"] == {
        "elements": 0.3,
        "flows": 0.5,
        "organizational": 0.15,
        "subprocess": 0.05,
    }


def test_bpmn_custom_weights_are_applied():
    """User-provided weights that sum to 1.0 must override the defaults
    verbatim (with the tolerance the code documents)."""
    custom = {
        "elements": 0.5,
        "flows": 0.5,
        "organizational": 0.0,
        "subprocess": 0.0,
    }
    r = calculate_bpmn_similarity(MODEL_A, MODEL_A_COPY, method="dice", weights=custom)
    assert r["weights_used"] == custom
    # Self-similarity should still be 1.0 regardless of weight choice
    # (rescaling of live categories preserves 1.0 when every category is 1.0).
    assert r["overall"] == pytest.approx(1.0)


def test_bpmn_rejects_weights_that_do_not_sum_to_one():
    bad = {"elements": 0.4, "flows": 0.4, "organizational": 0.1, "subprocess": 0.05}
    with pytest.raises(ValueError, match="must sum to 1.0"):
        calculate_bpmn_similarity(MODEL_A, MODEL_B, method="dice", weights=bad)


def test_bpmn_rejects_weights_with_wrong_keys():
    bad = {"elements": 0.5, "flows": 0.5}  # missing the required keys
    with pytest.raises(ValueError, match="must have exactly these keys"):
        calculate_bpmn_similarity(MODEL_A, MODEL_B, method="dice", weights=bad)


def test_bpmn_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unsupported method"):
        calculate_bpmn_similarity(MODEL_A, MODEL_B, method="banana")


def test_bpmn_result_shape_has_expected_keys():
    """The result dict is a public contract: the dashboard and the
    hybrid combiner index into these keys by name. Pin the shape so a
    refactor that renames a key is caught here first, not in the UI."""
    r = calculate_bpmn_similarity(MODEL_A, MODEL_B, method="dice")
    for key in (
        "fine_scores",
        "grouped_scores",
        "high_level_scores",
        "overall",
        "weights_used",
        "has_expanded_subprocess",
        "data_presence",
    ):
        assert key in r, f"missing key: {key}"
    # Flat backward-compat aliases the dashboard also reads.
    for flat in (
        "elements_grouped",
        "flow_grouped",
        "organizational_grouped",
        "subprocess_grouped",
    ):
        assert flat in r, f"missing flat alias: {flat}"


# ---------------------------------------------------------------------------
# calculate_trace_similarity — invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ("dice", "jaccard", "overlap"))
def test_trace_self_similarity_is_one(method):
    traces = [["A", "B", "C"], ["A", "D"]]
    assert calculate_trace_similarity(traces, traces, method=method) == pytest.approx(1.0)


@pytest.mark.parametrize("method", ("dice", "jaccard", "overlap"))
def test_trace_symmetry_for_symmetric_methods(method):
    tr1 = [["A", "B", "C"], ["A", "D"]]
    tr2 = [["A", "B", "C"], ["X"]]
    ab = calculate_trace_similarity(tr1, tr2, method=method)
    ba = calculate_trace_similarity(tr2, tr1, method=method)
    assert ab == pytest.approx(ba)


def test_trace_precision_of_ab_equals_recall_of_ba():
    tr1 = [["A", "B", "C"], ["A", "D"]]
    tr2 = [["A", "B", "C"], ["X"]]
    p = calculate_trace_similarity(tr1, tr2, method="precision")
    r = calculate_trace_similarity(tr2, tr1, method="recall")
    assert p == pytest.approx(r)


def test_trace_both_empty_returns_none():
    """Documented in the source: two empty trace sets give None (there
    is no behavior to compare). The dashboard branches on this — if
    Jaccard's bogus 1.0 leaks through, the hybrid score becomes
    misleadingly optimistic."""
    assert calculate_trace_similarity([], [], method="jaccard") is None


def test_trace_deduplicates_before_scoring():
    """Two lists that dedupe to the same set must score identically —
    the source explicitly ``set()``s each side before comparing."""
    a = [["A", "B"], ["A", "B"], ["C"]]                # 2 unique variants
    b = [["A", "B"], ["C"], ["C"]]                     # 2 unique variants
    dedup_score = calculate_trace_similarity(a, b, method="jaccard")
    plain_score = calculate_trace_similarity(
        [["A", "B"], ["C"]],
        [["A", "B"], ["C"]],
        method="jaccard",
    )
    assert dedup_score == pytest.approx(plain_score)
    assert dedup_score == pytest.approx(1.0)


def test_trace_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown similarity method"):
        calculate_trace_similarity([["A"]], [["B"]], method="banana")


# ---------------------------------------------------------------------------
# calculate_ngram_similarity — quick contract checks
# ---------------------------------------------------------------------------
# The ngram path shares its scoring backend with trace_similarity but has
# its own extraction step. Two smoke checks are enough here — the deep
# tests for ngram extraction live wherever extract_ngrams is unit-tested.

@pytest.mark.parametrize("method", ("dice", "jaccard", "overlap"))
def test_ngram_self_similarity_is_one(method):
    traces = [["A", "B", "C"], ["A", "D"]]
    assert calculate_ngram_similarity(traces, traces, n=2, method=method) == pytest.approx(1.0)


def test_ngram_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown similarity method"):
        calculate_ngram_similarity([["A", "B"]], [["A", "C"]], method="banana")


# ---------------------------------------------------------------------------
# calculate_hybrid_similarity — the weighted combiner math
# ---------------------------------------------------------------------------
# Contract: hybrid = w * structural + (1 - w) * behavioral, with
# None-propagation rules and weight validation.

def _struct_result(overall):
    """Helper: build the minimal structural-result shape the combiner reads."""
    return {"overall": overall}


def test_hybrid_computes_weighted_sum_when_both_are_floats():
    h = calculate_hybrid_similarity(_struct_result(0.4), 0.6, structural_weight=0.25)
    assert h["hybrid"] == pytest.approx(0.25 * 0.4 + 0.75 * 0.6)
    assert h["structural"] == pytest.approx(0.4)
    assert h["behavioral"] == pytest.approx(0.6)
    assert h["structural_weight"] == pytest.approx(0.25)
    assert h["behavioral_weight"] == pytest.approx(0.75)


def test_hybrid_defaults_to_equal_weights():
    """Default structural_weight is 0.5 — an equal-weight blend. Pin the
    default so a change to the signature has to update this test."""
    h = calculate_hybrid_similarity(_struct_result(0.2), 0.8)
    assert h["hybrid"] == pytest.approx(0.5)


def test_hybrid_propagates_behavioral_when_structural_is_none():
    """When structural is undefined, hybrid == behavioral and the effective
    weights are (0, 1) regardless of what the user slid the weight to."""
    h = calculate_hybrid_similarity(_struct_result(None), 0.4, structural_weight=0.6)
    assert h["hybrid"] == pytest.approx(0.4)
    assert h["structural_weight"] == 0.0
    assert h["behavioral_weight"] == 1.0


def test_hybrid_propagates_structural_when_behavioral_is_none():
    h = calculate_hybrid_similarity(_struct_result(0.7), None, structural_weight=0.6)
    assert h["hybrid"] == pytest.approx(0.7)
    assert h["structural_weight"] == 1.0
    assert h["behavioral_weight"] == 0.0


def test_hybrid_is_none_when_both_sides_are_none():
    h = calculate_hybrid_similarity(_struct_result(None), None)
    assert h["hybrid"] is None
    assert h["structural"] is None
    assert h["behavioral"] is None
    # Effective weights should both be 0 — signals "nothing to weight".
    assert h["structural_weight"] == 0.0
    assert h["behavioral_weight"] == 0.0


@pytest.mark.parametrize("bad_w", [-0.01, 1.01, 2.0, -1.0])
def test_hybrid_rejects_out_of_range_weight(bad_w):
    with pytest.raises(ValueError, match=r"structural_weight must be in \[0, 1\]"):
        calculate_hybrid_similarity(_struct_result(0.5), 0.5, structural_weight=bad_w)


def test_hybrid_result_shape_has_expected_keys():
    """Public contract read by the dashboard's KPI card."""
    h = calculate_hybrid_similarity(_struct_result(0.4), 0.6, structural_weight=0.5)
    assert set(h.keys()) == {
        "structural",
        "behavioral",
        "structural_weight",
        "behavioral_weight",
        "hybrid",
    }
