# similarity functions for comparing two bpmn instances
#
# This module is the single home for all similarity computation:
#   - structural similarity from `calculate_bpmn_similarity` (BPMN element/flow sets)
#   - behavioral similarity from `calculate_trace_similarity` (execution traces)
#
# `calculate_bpmn_similarity` can compute both in one call when ``behavioral=True``
# is passed; it then internally invokes `extract_traces` from `trace_extraction`.

from typing import List, Union, Literal

from bpmn_sets import extract_bpmn_sets
from trace_extraction import TraceExtractionResult, extract_ngrams, extract_traces
from utils.list_similarity import dice_list, index_list, jaccard_list, overlap_list, scores

# Public type alias: most similarity helpers accept either raw traces or a
# TraceExtractionResult.
TracesOrResult = Union[List[List[str]], TraceExtractionResult]


def _coerce_to_trace_list(arg: TracesOrResult) -> List[List[str]]:
    if isinstance(arg, TraceExtractionResult):
        return arg.all_traces()
    return arg


def calculate_trace_similarity(
    traces_1: TracesOrResult,
    traces_2: TracesOrResult,
    method: str = "jaccard"
) -> float:
    """Calculate similarity between two sets of traces.

    Args:
        traces_1: First set of traces, or a :class:`TraceExtractionResult`.
        traces_2: Second set of traces, or a :class:`TraceExtractionResult`.
        method: Similarity metric – ``"jaccard"`` (default), ``"dice"``,
            ``"overlap"`` (overlap coefficient), or ``"precision"`` /
            ``"recall"`` / ``"f1"`` (computed over the deduped trace sets,
            with ``traces_1`` treated as ground truth).

    Returns:
        Similarity score between 0.0 and 1.0. When given
        :class:`TraceExtractionResult` arguments, similarity is computed over
        the union of sound variants and partial traces from each side.
    """
    list_1 = _coerce_to_trace_list(traces_1)
    list_2 = _coerce_to_trace_list(traces_2)

    set_1 = list({tuple(trace) for trace in list_1})
    set_2 = list({tuple(trace) for trace in list_2})

    if method == "jaccard":
        score, _ = jaccard_list(set_1, set_2)
        return score
    elif method == "dice":
        score, _ = dice_list(set_1, set_2)
        return score
    elif method == "overlap":
        score, _ = overlap_list(set_1, set_2)
        return score
    elif method in {"precision", "recall", "f1"}:
        score, _ = scores(set_1, set_2, score_type=method)
        return score
    else:
        raise ValueError(f"Unknown similarity method: {method}")


def calculate_ngram_similarity(
    traces_1: TracesOrResult,
    traces_2: TracesOrResult,
    n: int = 2,
    method: Literal["jaccard", "dice", "overlap", "precision", "recall", "f1"] = "jaccard",
    pad: bool = True,
) -> float:
    """Set-based n-gram similarity between two trace collections.

    Decomposes each side into length-n contiguous subsequences, dedupes to a set,
    and scores with the same metrics :func:`calculate_trace_similarity` supports.

    Args:
        traces_1: First trace set or a class TraceExtractionResult
        traces_2: Second trace set, same accepted shapes
        n: N-gram window length. Must be >= 1
        method
        pad: Whether to wrap each trace with <START> / <END>

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    set_1 = list(set(extract_ngrams(traces_1, n=n, pad=pad)))
    set_2 = list(set(extract_ngrams(traces_2, n=n, pad=pad)))

    if method == "jaccard":
        score, _ = jaccard_list(set_1, set_2)
        return score
    elif method == "dice":
        score, _ = dice_list(set_1, set_2)
        return score
    elif method == "overlap":
        score, _ = overlap_list(set_1, set_2)
        return score
    elif method in {"precision", "recall", "f1"}:
        score, _ = scores(set_1, set_2, score_type=method)
        return score
    else:
        raise ValueError(f"Unknown similarity method: {method}")


def calculate_bpmn_similarity(
    bpmn_object1,
    bpmn_object2,
    method="dice",
    weights=None,
    behavioral=False,
    trace_timeout_seconds=5.0,
    max_loop_depth=3,
):
    """
    Calculates BPMN similarity at three levels: fine, grouped, and high-level, with weighted overall score.

    Dynamically adjusts weights based on subprocess presence:
    - If either model has expanded subprocesses: structural=35%, flows=45%, organizational=15%, subprocess=5%
    - If no expanded subprocesses: redistributes subprocess weight proportionally
      (structural=36.84%, flows=47.37%, organizational=15.79%, subprocess=0%)

    Collapsed subprocesses are treated as regular activities and don't trigger subprocess weighting.

    When ``behavioral=True``, the function additionally extracts execution traces from
    both models (via :func:`trace_extraction.extract_traces`), computes their similarity,
    and adds the following keys to the result dict:

    - ``behavioral``: high-level behavioral score, weighted into ``overall``
    - ``behavioral_metric_used``: actual metric used (``"dice"`` or ``"jaccard"``)
    - ``trace_result_1``, ``trace_result_2``: the :class:`TraceExtractionResult` objects
    - ``high_level_scores["behavioral"]`` and ``weights_used["behavioral"]`` (defaults to 0.0)

    With ``behavioral=False`` (default), no trace extraction is performed and the
    result dict is identical to the structural-only output.

    Returns a dict with all levels including 'weights_used' and 'has_expanded_subprocess' keys.
    """
    sets1 = extract_bpmn_sets(bpmn_object1)
    sets2 = extract_bpmn_sets(bpmn_object2)

    # Level 1: Fine-grained
    fine_scores = {}
    for key in [
        "activity_names", "activity_types", "event_names", "event_types",
        "gateway_names", "gateway_types", "seq_flows_str", "mes_flows_str",
        "lane_names", "lane_with_refs", "subprocess_names", "subprocess_elemrefs", "subprocess_flows"
    ]:
        l1 = index_list(sets1.get(key, []))
        l2 = index_list(sets2.get(key, []))
        if method == "dice":
            fine_scores[key] = dice_list(l1, l2)[0]
        elif method == "jaccard":
            fine_scores[key] = jaccard_list(l1, l2)[0]
        elif method in {"precision", "recall", "f1"}:
            fine_scores[key] = scores(l1, l2, score_type=method)[0]
        else:
            raise ValueError("Unsupported method")

    # Level 2: Grouped
    grouped_scores = {
        "activities": (fine_scores["activity_names"] + fine_scores["activity_types"]) / 2,
        "events": (fine_scores["event_names"] + fine_scores["event_types"]) / 2,
        "gateways": (fine_scores["gateway_names"] + fine_scores["gateway_types"]) / 2,
        "flows": (fine_scores["seq_flows_str"] + fine_scores["mes_flows_str"]) / 2,
        "pools": (fine_scores["lane_names"] + fine_scores["lane_with_refs"]) / 2,
        "subprocess": (
            fine_scores["subprocess_names"] * 0.2 +      # 20% - subprocess identity
            fine_scores["subprocess_elemrefs"] * 0.3 +   # 30% - element containment
            fine_scores["subprocess_flows"] * 0.5        # 50% - flow structure (most important)
        ),
    }

    # Level 3: High-level
    # Check if either model has expanded subprocesses
    # Check both names and elements to catch subprocesses without names
    has_expanded_subprocess = (
        len(sets1.get("subprocess_names", [])) > 0 or
        len(sets2.get("subprocess_names", [])) > 0 or
        len(sets1.get("subprocess_elemrefs", [])) > 0 or
        len(sets2.get("subprocess_elemrefs", [])) > 0 or
        len(sets1.get("subprocess_flows", [])) > 0 or
        len(sets2.get("subprocess_flows", [])) > 0
    )

    # Default weights if not provided
    if has_expanded_subprocess:
        # Standard weights when subprocesses are present
        default_weights = {
            "structural": 0.3,
            "flows": 0.5,
            "organizational": 0.15,
            "subprocess": 0.05
        }
    else:
        # Redistribute subprocess weight proportionally when no expanded subprocesses
        # Original: structural=0.35, flows=0.45, organizational=0.15, subprocess=0.05
        # Without subprocess: redistribute 0.05 proportionally to other 3 (total 0.95)
        # structural: 0.35/0.95 = 0.3684, flows: 0.45/0.95 = 0.4737, org: 0.15/0.95 = 0.1579
        default_weights = {
            "structural": 0.3,
            "flows": 0.5,
            "organizational": 0.2,
            "subprocess": 0.0
        }

    # When behavioral is requested, add the bucket *before* weight validation and
    # the overall computation so they pick it up uniformly. Default weight is 0.0
    # so existing callers see an unchanged ``overall`` value.
    if behavioral:
        default_weights["behavioral"] = 0.0

    if weights is not None:
        # Validate weights
        expected_keys = set(default_weights.keys())
        provided_keys = set(weights.keys())
        if expected_keys != provided_keys:
            raise ValueError(
                f"Weights must have exactly these keys: {expected_keys}. Got: {provided_keys}"
            )
        weight_sum = sum(weights.values())
        if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point tolerance
            raise ValueError(
                f"Weights must sum to 1.0 (100%). Got sum: {weight_sum}"
            )
        for k in default_weights:
            if k in weights:
                default_weights[k] = weights[k]

    high_level_scores = {
        "structural": (grouped_scores["activities"] + grouped_scores["events"] + grouped_scores["gateways"]) / 3,
        "flows": grouped_scores["flows"],
        "organizational": grouped_scores["pools"],
        "subprocess": grouped_scores["subprocess"]
    }

    # Behavioral block: extract traces and compute similarity. Only runs when
    # opted in. Records the actual metric used so callers can label the result.
    behavioral_metric_used = None
    trace_result_1 = None
    trace_result_2 = None
    if behavioral:
        trace_result_1 = extract_traces(
            bpmn_object1,
            max_loop_depth=max_loop_depth,
            timeout_seconds=trace_timeout_seconds,
        )
        trace_result_2 = extract_traces(
            bpmn_object2,
            max_loop_depth=max_loop_depth,
            timeout_seconds=trace_timeout_seconds,
        )
        # Mirror the structural metric — calculate_trace_similarity supports
        # the same methods as the structural toggle (dice, jaccard, precision,
        # recall, f1) plus overlap, so no fallback is needed.
        behavioral_metric_used = method
        high_level_scores["behavioral"] = calculate_trace_similarity(
            trace_result_1, trace_result_2, method=behavioral_metric_used
        )

    # Weighted overall score
    total_weight = sum(default_weights.values())
    overall = sum(high_level_scores[k] * default_weights[k] for k in high_level_scores) / total_weight

    # Build comprehensive result dict with both nested and flat access patterns
    result = {
        # Nested structure
        "fine_scores": fine_scores,
        "grouped_scores": grouped_scores,
        "high_level_scores": high_level_scores,
        "overall": overall,
        "weights_used": default_weights,
        "has_expanded_subprocess": has_expanded_subprocess
    }

    # Add flat access for convenience (backward compatibility)
    # Fine-grained scores with original keys
    for key, value in fine_scores.items():
        result[key] = value

    # Grouped scores with _grouped suffix
    result["structural_grouped"] = high_level_scores["structural"]
    result["flow_grouped"] = high_level_scores["flows"]
    result["organizational_grouped"] = high_level_scores["organizational"]
    result["subprocess_grouped"] = high_level_scores["subprocess"]

    if behavioral:
        result["behavioral"] = high_level_scores["behavioral"]
        result["behavioral_metric_used"] = behavioral_metric_used
        result["trace_result_1"] = trace_result_1
        result["trace_result_2"] = trace_result_2

    return result
