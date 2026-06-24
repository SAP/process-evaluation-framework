"""Scalability benchmarks for the maturity suite.

Marked ``@pytest.mark.slow`` — run with ``poetry run pytest tests/maturity/
-m slow`` or include explicitly. Per-test budgets are deliberately generous;
the goal is "completes within budget", NOT exact timings. The real numbers
for the paper are captured by ``scripts/maturity/run_maturity_report.py``.

The AND-branches series intentionally surfaces the factorial trace-variant
wall: ``N!`` variants for ``N`` parallel tasks. Generous timeouts keep CI
green for the sizes we ship; sizes beyond what we generate are not
explored here.
"""

import time

import pytest

from bpmn_similarity import calculate_bpmn_similarity
from trace_extraction import extract_traces

from .conftest import SCALABILITY, _load


LINEAR_SIZES = (5, 10, 20, 50, 100, 200)
AND_SIZES = (2, 3, 4, 5, 6, 7, 8)

# Generous wall-clock ceilings — calibrated upward to stay green on slow CI.
LINEAR_BUDGET_S = 30.0
AND_BUDGET_S = 120.0


def _full_pipeline(model):
    """Run the maturity-relevant end-to-end pipeline: trace extraction
    + structural self-similarity. Returns (elapsed_s, variant_count)."""
    start = time.perf_counter()
    res = extract_traces(model, timeout_seconds=AND_BUDGET_S, max_loop_depth=3)
    sim = calculate_bpmn_similarity(model, model, method="dice")
    elapsed = time.perf_counter() - start
    assert sim["overall"] == pytest.approx(1.0), (
        f"self-similarity should be 1.0, got {sim['overall']}"
    )
    return elapsed, len(res.variants)


@pytest.mark.slow
@pytest.mark.parametrize("n", LINEAR_SIZES)
def test_linear_chain_within_budget(n):
    """Linear chains scale smoothly — 200-element chain must clear 30s."""
    path = SCALABILITY / f"linear_{n}.bpmn"
    assert path.exists(), f"missing fixture: {path}"
    model = _load(path)

    elapsed, variants = _full_pipeline(model)
    assert variants == 1, f"linear_{n}: expected exactly 1 variant, got {variants}"
    assert elapsed <= LINEAR_BUDGET_S, (
        f"linear_{n}: took {elapsed:.2f}s (budget {LINEAR_BUDGET_S}s)"
    )


@pytest.mark.slow
@pytest.mark.parametrize("n", AND_SIZES)
def test_and_split_within_budget(n):
    """AND-split with N branches yields up to N! interleaved variants.

    Budget is generous and the same for every N; surfacing that the
    factorial growth eats it is the *point* of this benchmark.
    """
    path = SCALABILITY / f"and_{n}.bpmn"
    assert path.exists(), f"missing fixture: {path}"
    model = _load(path)

    elapsed, variants = _full_pipeline(model)
    import math

    # Up to N! variants — the explorer may legitimately cap or dedupe.
    assert variants >= 1
    assert variants <= math.factorial(n), (
        f"and_{n}: got {variants} variants, expected ≤ {math.factorial(n)}"
    )
    assert elapsed <= AND_BUDGET_S, (
        f"and_{n}: took {elapsed:.2f}s (budget {AND_BUDGET_S}s)"
    )
