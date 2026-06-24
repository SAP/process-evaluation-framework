"""Gateway-typed BPMN models in the maturity suite.

NOTE on what these fixtures actually are: ``gateway_and.bpmn``,
``gateway_xor.bpmn``, and ``gateway_or.bpmn`` (copies of the repo's
``Gateway AND/XOR/Inclusive.bpmn``) are three different T-shirt-order
processes that demonstrate the three gateway flavors, NOT the same task
set with the gateway type swapped. They share the same business domain
(T-shirt order, Sales pool, the same start/end events) but their
activity sets differ. The maturity claim we can honestly make from them
is therefore weaker than "same activities, different gateway":

  - all three models load, normalize, and compare without errors
  - their pairwise overall scores land in a sensible band (low-medium,
    not 0, not 1) — they share a domain but not a flow
  - self-similarity is exactly 1.0 for each
  - trace extraction yields ≥1 variant for each, and cross-pair trace
    similarity is strictly below self-similarity

Authoring a properly-matched AND/XOR/OR triplet (same tasks, gateway
type swapped) is part of task #3. When those land they replace the
'banded' assertion here with a strict high-structural / variable-trace one.
"""

import pytest

from bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces

from .conftest import GATEWAY_SUBSTITUTIONS, _load


def _structural(model_a, model_b):
    return calculate_bpmn_similarity(model_a, model_b, method="dice")["overall"]


def _trace_jaccard(model_a, model_b):
    res_a = extract_traces(model_a, timeout_seconds=3.0, max_loop_depth=3)
    res_b = extract_traces(model_b, timeout_seconds=3.0, max_loop_depth=3)
    return calculate_trace_similarity(res_a, res_b, method="jaccard")


@pytest.fixture(scope="module")
def gateway_models():
    return {
        "and": _load(GATEWAY_SUBSTITUTIONS / "gateway_and.bpmn"),
        "xor": _load(GATEWAY_SUBSTITUTIONS / "gateway_xor.bpmn"),
        "or": _load(GATEWAY_SUBSTITUTIONS / "gateway_or.bpmn"),
    }


@pytest.mark.parametrize("key", ["and", "xor", "or"])
def test_gateway_model_self_similarity_is_one(gateway_models, key):
    """Each gateway-typed fixture should be perfectly similar to itself."""
    overall = _structural(gateway_models[key], gateway_models[key])
    assert overall == pytest.approx(1.0), (
        f"{key}-vs-{key} expected 1.0, got {overall}"
    )


@pytest.mark.parametrize(
    "left,right",
    [("and", "xor"), ("and", "or"), ("xor", "or")],
)
def test_cross_gateway_pair_in_shared_domain_band(gateway_models, left, right):
    """Cross-pair overall sits between 'disjoint' and 'identical'.

    Loose band — the three fixtures are different processes in the same
    domain. Tightened in calibration once we've replaced this corpus with
    a properly-aligned triplet (task #3).
    """
    overall = _structural(gateway_models[left], gateway_models[right])
    assert overall is not None
    assert 0.1 <= overall <= 0.9, (
        f"{left}-vs-{right} overall = {overall:.3f}; expected in [0.1, 0.9]"
    )


@pytest.mark.parametrize(
    "left,right",
    [("and", "xor"), ("and", "or"), ("xor", "or")],
)
def test_cross_gateway_trace_strictly_below_self(gateway_models, left, right):
    """Cross-pair trace similarity is strictly below self-similarity."""
    cross = _trace_jaccard(gateway_models[left], gateway_models[right])
    self_left = _trace_jaccard(gateway_models[left], gateway_models[left])
    assert self_left == pytest.approx(1.0)
    assert cross is None or cross < self_left, (
        f"{left}-vs-{right} trace ({cross}) should be < {left}-self ({self_left})"
    )


@pytest.mark.parametrize("key", ["and", "xor", "or"])
def test_gateway_model_has_at_least_one_variant(gateway_models, key):
    """Sanity: extraction must succeed and yield ≥1 variant per fixture."""
    res = extract_traces(gateway_models[key], timeout_seconds=3.0, max_loop_depth=3)
    assert res.is_sound or res.variants, (
        f"{key}: expected ≥1 variant or a sound extraction, got "
        f"variants={len(res.variants)} status={res.diagnostics.status}"
    )
    assert len(res.variants) >= 1
