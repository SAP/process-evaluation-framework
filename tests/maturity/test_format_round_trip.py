"""Format round-trip: BPMN XML vs Signavio JSON of the same model.

Both pairs live under ``examples/maturity/format_round_trip/``. They are
NOT byte-identical — JSON carries Signavio diagram metadata while BPMN
is the post-conversion XML — but after both converters land in the
common dict shape, the structural similarity should be near-perfect.

Calibrated threshold: both measured pairs land at exactly 1.000, so the
per-test floor is ≥0.99 (one hair of tolerance for incidental converter
changes such as a new anonymous-ID scheme).
"""

import pytest

from model_evaluation import calculate_bpmn_similarity

from .conftest import FORMAT_ROUND_TRIP, _load


@pytest.mark.parametrize(
    "stem",
    ["linear_sequence", "credit"],
)
def test_bpmn_vs_json_round_trip_is_high(stem):
    """Per-pair check enforcing the ≥0.99 floor described in the module
    docstring."""
    bpmn = _load(FORMAT_ROUND_TRIP / f"{stem}.bpmn")
    sjson = _load(FORMAT_ROUND_TRIP / f"{stem}.json")

    result = calculate_bpmn_similarity(bpmn, sjson, method="dice")
    overall = result["overall"]
    assert overall is not None, f"{stem}: overall is None"
    assert overall >= 0.99, (
        f"{stem}: BPMN-vs-JSON round-trip overall = {overall:.3f} (<0.99)"
    )
