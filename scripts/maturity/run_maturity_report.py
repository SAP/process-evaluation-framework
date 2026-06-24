"""Run the maturity suite end-to-end and print a numbers-ready report.

Produces two tables, suitable for pasting straight into the paper text:

1. **Scalability** — wall-clock time per generated model
   (``examples/maturity/scalability/linear_N.bpmn`` and ``and_N.bpmn``).
2. **Edge-case scores** — for every pair the test suite exercises, print
   the actual sub-scores so thresholds can be calibrated and the prose
   numbers can be checked.

Usage::

    poetry run python scripts/maturity/run_maturity_report.py

The script does not assert thresholds; it just measures and prints. That
is intentional — calibration (task #4) decides what the floors / ceilings
should be once we've seen the distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_EVAL = REPO_ROOT / "model_evaluation"
for _p in (str(REPO_ROOT), str(MODEL_EVAL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from BPMN_conversion import BPMNConverter, XMLBPMNConverter  # noqa: E402
from bpmn_similarity import (  # noqa: E402
    calculate_bpmn_similarity,
    calculate_trace_similarity,
)
from trace_extraction import extract_traces  # noqa: E402


EXAMPLES = REPO_ROOT / "examples"
SCALABILITY = EXAMPLES / "maturity" / "scalability"

LINEAR_SIZES = (5, 10, 20, 50, 100, 200)
AND_SIZES = (2, 3, 4, 5, 6, 7, 8)


# ---------------------------------------------------------------------------
# Loaders / measurement helpers
# ---------------------------------------------------------------------------

def load_model(path: Path):
    if path.suffix in (".xml", ".bpmn"):
        return XMLBPMNConverter.convert_file(str(path)).to_dict()
    with path.open("r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


def time_pipeline(path: Path, *, timeout_s: float = 120.0) -> dict:
    """Measure load + trace-extraction + structural self-similarity."""
    t0 = time.perf_counter()
    model = load_model(path)
    t_load = time.perf_counter() - t0

    t0 = time.perf_counter()
    res = extract_traces(model, timeout_seconds=timeout_s, max_loop_depth=3)
    t_trace = time.perf_counter() - t0

    t0 = time.perf_counter()
    sim = calculate_bpmn_similarity(model, model, method="dice")
    t_sim = time.perf_counter() - t0

    return {
        "load_s": t_load,
        "trace_s": t_trace,
        "sim_s": t_sim,
        "total_s": t_load + t_trace + t_sim,
        "variants": len(res.variants),
        "is_sound": res.is_sound,
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _hr(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(c.ljust(w) for c, w in zip(cells, widths))


def report_scalability() -> None:
    _hr("Scalability — linear chain (N tasks in sequence)")
    widths = [6, 10, 10, 10, 12, 10]
    header = ["N", "load (s)", "trace (s)", "sim (s)", "total (s)", "variants"]
    print(_row(header, widths))
    print(_row(["-" * w for w in widths], widths))
    for n in LINEAR_SIZES:
        path = SCALABILITY / f"linear_{n}.bpmn"
        if not path.exists():
            print(f"  (missing: {path.relative_to(REPO_ROOT)})")
            continue
        m = time_pipeline(path)
        print(_row(
            [
                str(n),
                f"{m['load_s']:.3f}",
                f"{m['trace_s']:.3f}",
                f"{m['sim_s']:.3f}",
                f"{m['total_s']:.3f}",
                str(m["variants"]),
            ],
            widths,
        ))

    _hr("Scalability — AND-split (N parallel branches)")
    print(_row(header, widths))
    print(_row(["-" * w for w in widths], widths))
    for n in AND_SIZES:
        path = SCALABILITY / f"and_{n}.bpmn"
        if not path.exists():
            print(f"  (missing: {path.relative_to(REPO_ROOT)})")
            continue
        m = time_pipeline(path)
        print(_row(
            [
                str(n),
                f"{m['load_s']:.3f}",
                f"{m['trace_s']:.3f}",
                f"{m['sim_s']:.3f}",
                f"{m['total_s']:.3f}",
                str(m["variants"]),
            ],
            widths,
        ))


# ---------------------------------------------------------------------------
# Edge-case score dump
# ---------------------------------------------------------------------------

# Each pair: (category, left_relpath_under_maturity, right_relpath_under_maturity, note).
# Relative paths are resolved against ``EXAMPLES / "maturity"``.
EdgePair = tuple[str, str, str, str]


EDGE_PAIRS: list[EdgePair] = [
    ("sanity", "sanity/identical_baseline.bpmn", "sanity/identical_baseline.bpmn",
     "identical — expect ~1.0 everywhere"),
    ("sanity", "sanity/disjoint_left_credit.bpmn", "sanity/disjoint_right_student.bpmn",
     "disjoint — expect low overall"),
    ("gateway", "gateway_substitutions/gateway_and.bpmn", "gateway_substitutions/gateway_xor.bpmn",
     "different gateway type, shared domain"),
    ("gateway", "gateway_substitutions/gateway_and.bpmn", "gateway_substitutions/gateway_or.bpmn",
     "different gateway type, shared domain"),
    ("gateway", "gateway_substitutions/gateway_xor.bpmn", "gateway_substitutions/gateway_or.bpmn",
     "different gateway type, shared domain"),
    ("structural", "structural_perturbations/linear_baseline.bpmn", "structural_perturbations/linear_reorder.bpmn",
     "small perturbation on linear sequence"),
    ("structural", "structural_perturbations/linear_baseline.bpmn", "structural_perturbations/linear_drift.bpmn",
     "larger perturbation on linear sequence"),
    ("structural", "structural_perturbations/and_two_branches.bpmn", "structural_perturbations/and_three_branches.bpmn",
     "branch added"),
    ("round_trip", "format_round_trip/linear_sequence.bpmn", "format_round_trip/linear_sequence.json",
     "BPMN vs Signavio JSON"),
    ("round_trip", "format_round_trip/credit.bpmn", "format_round_trip/credit.json",
     "BPMN vs Signavio JSON"),
    ("degenerate", "degenerate/unsound_and_no_join.bpmn", "degenerate/sound_and_with_join.bpmn",
     "unsound vs sound — must not raise"),
]


MATURITY_DIR = EXAMPLES / "maturity"


def _safe_trace_similarity(model_a, model_b) -> Optional[float]:
    try:
        res_a = extract_traces(model_a, timeout_seconds=10.0, max_loop_depth=3)
        res_b = extract_traces(model_b, timeout_seconds=10.0, max_loop_depth=3)
        return calculate_trace_similarity(res_a, res_b, method="jaccard")
    except Exception as exc:  # pragma: no cover — surfacing a failure here is fine
        return None


def report_edge_cases() -> None:
    _hr("Edge-case scores (actual values for calibration / paper)")
    widths = [12, 50, 50, 11, 9, 9]
    header = ["category", "left", "right", "overall", "elem", "trace"]
    print(_row(header, widths))
    print(_row(["-" * w for w in widths], widths))
    for category, left_name, right_name, note in EDGE_PAIRS:
        left_path = MATURITY_DIR / left_name
        right_path = MATURITY_DIR / right_name
        if not left_path.exists() or not right_path.exists():
            print(f"  (missing: {left_name} or {right_name})")
            continue
        left = load_model(left_path)
        right = load_model(right_path)
        struct = calculate_bpmn_similarity(left, right, method="dice")
        trace = _safe_trace_similarity(left, right)
        overall = struct["overall"]
        elem = struct["high_level_scores"].get("elements")
        print(_row(
            [
                category,
                left_name[:50],
                right_name[:50],
                _fmt(overall),
                _fmt(elem),
                _fmt(trace),
            ],
            widths,
        ))
        print(f"  note: {note}")


def _fmt(x) -> str:
    if x is None:
        return "None"
    return f"{x:.3f}"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-scalability",
        action="store_true",
        help="Only dump edge-case scores",
    )
    parser.add_argument(
        "--skip-edge-cases",
        action="store_true",
        help="Only dump scalability numbers",
    )
    args = parser.parse_args()

    if not args.skip_scalability:
        report_scalability()
    if not args.skip_edge_cases:
        report_edge_cases()
    print()


if __name__ == "__main__":
    main()
