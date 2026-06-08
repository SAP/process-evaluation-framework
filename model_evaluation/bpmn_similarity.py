# # similarity functions for comparing two bpmn instances
# #
# # This module is the single home for all similarity computation:
# #   - structural similarity from `calculate_bpmn_similarity` (BPMN element/flow sets)
# #   - behavioral similarity from `calculate_trace_similarity` (execution traces)
# #
# # `calculate_bpmn_similarity` can compute both in one call when ``behavioral=True``
# # is passed; it then internally invokes `extract_traces` from `trace_extraction`.

# from typing import List, Union

# from bpmn_sets import extract_bpmn_sets
# from trace_extraction import TraceExtractionResult, extract_traces
# from utils.list_similarity import dice_list, index_list, jaccard_list, overlap_list, scores

# # Public type alias: most similarity helpers accept either raw traces or a
# # TraceExtractionResult.
# TracesOrResult = Union[List[List[str]], TraceExtractionResult]


# def _coerce_to_trace_list(arg: TracesOrResult) -> List[List[str]]:
#     if isinstance(arg, TraceExtractionResult):
#         return arg.all_traces()
#     return arg


# def calculate_trace_similarity(
#     traces_1: TracesOrResult,
#     traces_2: TracesOrResult,
#     method: str = "jaccard"
# ) -> float:
#     """Calculate similarity between two sets of traces.

#     Args:
#         traces_1: First set of traces, or a :class:`TraceExtractionResult`.
#         traces_2: Second set of traces, or a :class:`TraceExtractionResult`.
#         method: Similarity metric – ``"jaccard"`` (default), ``"dice"``,
#             ``"overlap"`` (overlap coefficient), or ``"precision"`` /
#             ``"recall"`` / ``"f1"`` (computed over the deduped trace sets,
#             with ``traces_1`` treated as ground truth).

#     Returns:
#         Similarity score between 0.0 and 1.0. When given
#         :class:`TraceExtractionResult` arguments, similarity is computed over
#         the union of sound variants and partial traces from each side.
#     """
#     list_1 = _coerce_to_trace_list(traces_1)
#     list_2 = _coerce_to_trace_list(traces_2)

#     set_1 = list({tuple(trace) for trace in list_1})
#     set_2 = list({tuple(trace) for trace in list_2})

#     if method == "jaccard":
#         score, _ = jaccard_list(set_1, set_2)
#         return score
#     elif method == "dice":
#         score, _ = dice_list(set_1, set_2)
#         return score
#     elif method == "overlap":
#         score, _ = overlap_list(set_1, set_2)
#         return score
#     elif method in {"precision", "recall", "f1"}:
#         score, _ = scores(set_1, set_2, score_type=method)
#         return score
#     else:
#         raise ValueError(f"Unknown similarity method: {method}")


# def calculate_bpmn_similarity(
#     bpmn_object1,
#     bpmn_object2,
#     method="dice",
#     weights=None,
#     behavioral=False,
#     trace_timeout_seconds=5.0,
#     max_loop_depth=3,
# ):
#     """
#     Calculates BPMN similarity at three levels: fine, grouped, and high-level, with weighted overall score.

#     Dynamically adjusts weights based on subprocess presence:
#     - If either model has expanded subprocesses: structural=35%, flows=45%, organizational=15%, subprocess=5%
#     - If no expanded subprocesses: redistributes subprocess weight proportionally
#       (structural=36.84%, flows=47.37%, organizational=15.79%, subprocess=0%)

#     Collapsed subprocesses are treated as regular activities and don't trigger subprocess weighting.

#     When ``behavioral=True``, the function additionally extracts execution traces from
#     both models (via :func:`trace_extraction.extract_traces`), computes their similarity,
#     and adds the following keys to the result dict:

#     - ``behavioral``: high-level behavioral score, weighted into ``overall``
#     - ``behavioral_metric_used``: actual metric used (``"dice"`` or ``"jaccard"``)
#     - ``trace_result_1``, ``trace_result_2``: the :class:`TraceExtractionResult` objects
#     - ``high_level_scores["behavioral"]`` and ``weights_used["behavioral"]`` (defaults to 0.0)

#     With ``behavioral=False`` (default), no trace extraction is performed and the
#     result dict is identical to the structural-only output.

#     Returns a dict with all levels including 'weights_used' and 'has_expanded_subprocess' keys.
#     """
#     sets1 = extract_bpmn_sets(bpmn_object1)
#     sets2 = extract_bpmn_sets(bpmn_object2)

#     # Level 1: Fine-grained
#     fine_scores = {}
#     for key in [
#         "activity_names", "activity_types", "event_names", "event_types",
#         "gateway_names", "gateway_types", "seq_flows_str", "mes_flows_str",
#         "lane_names", "lane_with_refs", "subprocess_names", "subprocess_elemrefs", "subprocess_flows"
#     ]:
#         l1 = index_list(sets1.get(key, []))
#         l2 = index_list(sets2.get(key, []))
#         if method == "dice":
#             fine_scores[key] = dice_list(l1, l2)[0]
#         elif method == "jaccard":
#             fine_scores[key] = jaccard_list(l1, l2)[0]
#         elif method in {"precision", "recall", "f1"}:
#             fine_scores[key] = scores(l1, l2, score_type=method)[0]
#         else:
#             raise ValueError("Unsupported method")

#     # Level 2: Grouped
#     grouped_scores = {
#         "activities": (fine_scores["activity_names"] + fine_scores["activity_types"]) / 2,
#         "events": (fine_scores["event_names"] + fine_scores["event_types"]) / 2,
#         "gateways": (fine_scores["gateway_names"] + fine_scores["gateway_types"]) / 2,
#         "flows": (fine_scores["seq_flows_str"] + fine_scores["mes_flows_str"]) / 2,
#         "pools": (fine_scores["lane_names"] + fine_scores["lane_with_refs"]) / 2,
#         "subprocess": (
#             fine_scores["subprocess_names"] * 0.2 +      # 20% - subprocess identity
#             fine_scores["subprocess_elemrefs"] * 0.3 +   # 30% - element containment
#             fine_scores["subprocess_flows"] * 0.5        # 50% - flow structure (most important)
#         ),
#     }

#     # Level 3: High-level
#     # Check if either model has expanded subprocesses
#     # Check both names and elements to catch subprocesses without names
#     has_expanded_subprocess = (
#         len(sets1.get("subprocess_names", [])) > 0 or
#         len(sets2.get("subprocess_names", [])) > 0 or
#         len(sets1.get("subprocess_elemrefs", [])) > 0 or
#         len(sets2.get("subprocess_elemrefs", [])) > 0 or
#         len(sets1.get("subprocess_flows", [])) > 0 or
#         len(sets2.get("subprocess_flows", [])) > 0
#     )

#     # Default weights if not provided
#     if has_expanded_subprocess:
#         # Standard weights when subprocesses are present
#         default_weights = {
#             "structural": 0.3,
#             "flows": 0.5,
#             "organizational": 0.15,
#             "subprocess": 0.05
#         }
#     else:
#         # Redistribute subprocess weight proportionally when no expanded subprocesses
#         # Original: structural=0.35, flows=0.45, organizational=0.15, subprocess=0.05
#         # Without subprocess: redistribute 0.05 proportionally to other 3 (total 0.95)
#         # structural: 0.35/0.95 = 0.3684, flows: 0.45/0.95 = 0.4737, org: 0.15/0.95 = 0.1579
#         default_weights = {
#             "structural": 0.3,
#             "flows": 0.5,
#             "organizational": 0.2,
#             "subprocess": 0.0
#         }

#     # When behavioral is requested, add the bucket *before* weight validation and
#     # the overall computation so they pick it up uniformly. Default weight is 0.0
#     # so existing callers see an unchanged ``overall`` value.
#     if behavioral:
#         default_weights["behavioral"] = 0.0

#     if weights is not None:
#         # Validate weights
#         expected_keys = set(default_weights.keys())
#         provided_keys = set(weights.keys())
#         if expected_keys != provided_keys:
#             raise ValueError(
#                 f"Weights must have exactly these keys: {expected_keys}. Got: {provided_keys}"
#             )
#         weight_sum = sum(weights.values())
#         if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point tolerance
#             raise ValueError(
#                 f"Weights must sum to 1.0 (100%). Got sum: {weight_sum}"
#             )
#         for k in default_weights:
#             if k in weights:
#                 default_weights[k] = weights[k]

#     high_level_scores = {
#         "structural": (grouped_scores["activities"] + grouped_scores["events"] + grouped_scores["gateways"]) / 3,
#         "flows": grouped_scores["flows"],
#         "organizational": grouped_scores["pools"],
#         "subprocess": grouped_scores["subprocess"]
#     }

#     # Behavioral block: extract traces and compute similarity. Only runs when
#     # opted in. Records the actual metric used so callers can label the result.
#     behavioral_metric_used = None
#     trace_result_1 = None
#     trace_result_2 = None
#     if behavioral:
#         trace_result_1 = extract_traces(
#             bpmn_object1,
#             max_loop_depth=max_loop_depth,
#             timeout_seconds=trace_timeout_seconds,
#         )
#         trace_result_2 = extract_traces(
#             bpmn_object2,
#             max_loop_depth=max_loop_depth,
#             timeout_seconds=trace_timeout_seconds,
#         )
#         # Mirror the structural metric — calculate_trace_similarity supports
#         # the same methods as the structural toggle (dice, jaccard, precision,
#         # recall, f1) plus overlap, so no fallback is needed.
#         behavioral_metric_used = method
#         high_level_scores["behavioral"] = calculate_trace_similarity(
#             trace_result_1, trace_result_2, method=behavioral_metric_used
#         )

#     # Weighted overall score
#     total_weight = sum(default_weights.values())
#     overall = sum(high_level_scores[k] * default_weights[k] for k in high_level_scores) / total_weight

#     # Build comprehensive result dict with both nested and flat access patterns
#     result = {
#         # Nested structure
#         "fine_scores": fine_scores,
#         "grouped_scores": grouped_scores,
#         "high_level_scores": high_level_scores,
#         "overall": overall,
#         "weights_used": default_weights,
#         "has_expanded_subprocess": has_expanded_subprocess
#     }

#     # Add flat access for convenience (backward compatibility)
#     # Fine-grained scores with original keys
#     for key, value in fine_scores.items():
#         result[key] = value

#     # Grouped scores with _grouped suffix
#     result["structural_grouped"] = high_level_scores["structural"]
#     result["flow_grouped"] = high_level_scores["flows"]
#     result["organizational_grouped"] = high_level_scores["organizational"]
#     result["subprocess_grouped"] = high_level_scores["subprocess"]

#     if behavioral:
#         result["behavioral"] = high_level_scores["behavioral"]
#         result["behavioral_metric_used"] = behavioral_metric_used
#         result["trace_result_1"] = trace_result_1
#         result["trace_result_2"] = trace_result_2

#     return result


# similarity functions for comparing two bpmn instances
#
# This module provides three independent similarity functions:
#   - calculate_bpmn_similarity:    structural similarity (BPMN element/flow sets)
#   - calculate_trace_similarity:   behavioral similarity over execution traces
#   - calculate_hybrid_similarity:  combines an already-computed structural
#                                   result with an already-computed behavioral
#                                   score into a hybrid score
#
# The three are intentionally decoupled. Structural and behavioral are computed
# separately (with their own metric choices and their own parameters); the
# hybrid combiner just weights two scores in [0, 1] and is cheap to recompute
# as the user adjusts the structural/behavioral weight.

# similarity functions for comparing two bpmn instances
#
# This module provides three independent similarity functions:
#   - calculate_bpmn_similarity:    structural similarity (BPMN element/flow sets)
#   - calculate_trace_similarity:   behavioral similarity over execution traces
#   - calculate_hybrid_similarity:  combines an already-computed structural
#                                   result with an already-computed behavioral
#                                   score into a hybrid score
#
# The three are intentionally decoupled. Structural and behavioral are computed
# separately (with their own metric choices and their own parameters); the
# hybrid combiner just weights two scores in [0, 1] and is cheap to recompute
# as the user adjusts the structural/behavioral weight.

# similarity functions for comparing two bpmn instances
#
# This module provides three independent similarity functions:
#   - calculate_bpmn_similarity:    structural similarity (BPMN element/flow sets)
#   - calculate_trace_similarity:   behavioral similarity over execution traces
#   - calculate_hybrid_similarity:  combines an already-computed structural
#                                   result with an already-computed behavioral
#                                   score into a hybrid score
#
# The three are intentionally decoupled. Structural and behavioral are computed
# separately (with their own metric choices and their own parameters); the
# hybrid combiner just weights two scores in [0, 1] and is cheap to recompute
# as the user adjusts the structural/behavioral weight.

from typing import List, Union

from bpmn_sets import extract_bpmn_sets
from trace_extraction import TraceExtractionResult
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


def calculate_bpmn_similarity(
    bpmn_object1,
    bpmn_object2,
    method="dice",
    weights=None,
):
    """
    Calculates BPMN structural similarity at three levels: fine, grouped, and
    high-level, with a weighted overall score.

    High-level categories (in ``high_level_scores`` and ``weights_used``):
        - "elements"       — activities + events + gateways (the flow-element
                             nodes of the BPMN graph). Renamed from
                             "structural" to avoid a name clash with the
                             top-level structural-similarity concept.
        - "flows"          — sequence + message flows, weighted 70/30 when at
                             least one model has message flows; sequence-only
                             when neither does.
        - "organizational" — pools and lanes.
        - "subprocess"     — expanded-subprocess identity, contents, and
                             internal flows.

    Dynamically adjusts category weights based on subprocess presence:
    - If either model has expanded subprocesses: elements=30%, flows=50%,
      organizational=15%, subprocess=5%
    - If no expanded subprocesses: redistributes subprocess weight
      (elements=30%, flows=50%, organizational=20%, subprocess=0%)

    Collapsed subprocesses are treated as regular activities and don't
    trigger subprocess weighting.

    For behavioral (trace-based) similarity, use ``calculate_trace_similarity``.
    For a combined score, use ``calculate_hybrid_similarity``.

    Returns a dict with all levels including 'weights_used' and
    'has_expanded_subprocess' keys.
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

    # Data-presence flags: True iff at least one of the two models contributes
    # something for this fine-grained key. When both models are empty, the
    # similarity functions return 1.0 by convention (two empty sets are
    # "perfectly equal"), which is mathematically defensible but visually
    # misleading in a per-element breakdown — a 1.0 bar for "Msg Flows" when
    # neither model has any message flows looks like a perfect match. The
    # dashboard reads these flags to gray out / hide empty-vs-empty rows.
    data_presence = {
        key: (len(sets1.get(key, [])) > 0 or len(sets2.get(key, [])) > 0)
        for key in fine_scores
    }

    # Level 2: Grouped
    # Adaptive flow weighting: sequence flows carry the core control-flow
    # signal; message flows are inter-pool communication and many models have
    # none. When neither model has message flows, the flow score reduces to
    # sequence-flow similarity alone (no empty-vs-empty inflation). When at
    # least one model has message flows, sequence dominates (70/30).
    has_message_flows = (
        len(sets1.get("mes_flows_str", [])) > 0 or
        len(sets2.get("mes_flows_str", [])) > 0
    )
    if has_message_flows:
        flows_grouped = 0.7 * fine_scores["seq_flows_str"] + 0.3 * fine_scores["mes_flows_str"]
    else:
        flows_grouped = fine_scores["seq_flows_str"]

    grouped_scores = {
        "activities": (fine_scores["activity_names"] + fine_scores["activity_types"]) / 2,
        "events": (fine_scores["event_names"] + fine_scores["event_types"]) / 2,
        "gateways": (fine_scores["gateway_names"] + fine_scores["gateway_types"]) / 2,
        "flows": flows_grouped,
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

    # Default weights if not provided.
    # NOTE: the "elements" key refers to the activities + events + gateways
    # bucket (the flow-element nodes of the BPMN graph). It is intentionally
    # NOT called "structural" any more, to avoid a name clash with the
    # top-level structural-similarity concept (the whole result of this
    # function is the *structural* score; "elements" is one of its parts).
    if has_expanded_subprocess:
        # Standard weights when subprocesses are present
        default_weights = {
            "elements": 0.3,
            "flows": 0.5,
            "organizational": 0.15,
            "subprocess": 0.05
        }
    else:
        # Redistribute subprocess weight proportionally when no expanded subprocesses
        default_weights = {
            "elements": 0.3,
            "flows": 0.5,
            "organizational": 0.2,
            "subprocess": 0.0
        }

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
        "elements": (grouped_scores["activities"] + grouped_scores["events"] + grouped_scores["gateways"]) / 3,
        "flows": grouped_scores["flows"],
        "organizational": grouped_scores["pools"],
        "subprocess": grouped_scores["subprocess"]
    }

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
        "has_expanded_subprocess": has_expanded_subprocess,
        "data_presence": data_presence,
    }

    # Add flat access for convenience (backward compatibility)
    # Fine-grained scores with original keys
    for key, value in fine_scores.items():
        result[key] = value

    # Grouped scores with _grouped suffix
    result["elements_grouped"] = high_level_scores["elements"]
    result["flow_grouped"] = high_level_scores["flows"]
    result["organizational_grouped"] = high_level_scores["organizational"]
    result["subprocess_grouped"] = high_level_scores["subprocess"]

    return result


def calculate_hybrid_similarity(
    structural_result,
    behavioral_score,
    structural_weight=0.5,
):
    """Combine a structural similarity result and a behavioral score.

    The hybrid is a simple weighted combination of two scores already in
    ``[0, 1]``. The metric used inside each side is an internal property of
    that side; the two need not match.

    Args:
        structural_result: Result dict from :func:`calculate_bpmn_similarity`.
        behavioral_score: Behavioral similarity (float in ``[0, 1]``),
            typically from :func:`calculate_trace_similarity`.
        structural_weight: Weight for the structural side (float in
            ``[0, 1]``). Behavioral weight is implicit as
            ``1 - structural_weight``. Default 0.5.

    Returns:
        Dict with keys ``structural``, ``behavioral``, ``structural_weight``,
        ``behavioral_weight``, ``hybrid``.
    """
    if not 0.0 <= structural_weight <= 1.0:
        raise ValueError(
            f"structural_weight must be in [0, 1], got {structural_weight}"
        )
    behavioral_weight = 1.0 - structural_weight
    structural_score = structural_result["overall"]
    return {
        "structural": structural_score,
        "behavioral": behavioral_score,
        "structural_weight": structural_weight,
        "behavioral_weight": behavioral_weight,
        "hybrid": structural_weight * structural_score + behavioral_weight * behavioral_score,
    }