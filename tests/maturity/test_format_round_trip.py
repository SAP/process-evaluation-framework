"""Format round-trip: BPMN XML vs Signavio JSON of the same model.

Both pairs live under ``examples/maturity/format_round_trip/``. They are
NOT byte-identical — JSON carries Signavio diagram metadata while BPMN
is the post-conversion XML — but after both converters land in the
common dict shape, the structural similarity should be close to 1.0.

Threshold is loose (≥0.8) because the converters can disagree on
incidental fields (e.g. anonymous gateway IDs surface as different
``*_names`` strings). Calibration will tighten this if the gap is in fact
narrow.
"""

import pytest

from bpmn_similarity import calculate_bpmn_similarity

from .conftest import FORMAT_ROUND_TRIP, _load


@pytest.mark.parametrize(
    "stem",
    ["linear_sequence", "credit"],
)
def test_bpmn_vs_json_round_trip_is_high(stem):
    """Calibrated: both measured pairs land at exactly 1.000 — the two
    converters agree on the dict shape they produce. The ≥0.99 floor
    leaves a hair of tolerance for incidental converter changes (e.g. a
    new anonymous-ID scheme) while still catching any real divergence.
    """
    bpmn = _load(FORMAT_ROUND_TRIP / f"{stem}.bpmn")
    sjson = _load(FORMAT_ROUND_TRIP / f"{stem}.json")

    result = calculate_bpmn_similarity(bpmn, sjson, method="dice")
    overall = result["overall"]
    assert overall is not None, f"{stem}: overall is None"
    assert overall >= 0.99, (
        f"{stem}: BPMN-vs-JSON round-trip overall = {overall:.3f} (<0.99)"
    )
