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


def _adaptive_grouped(fine_scores, data_presence, components):
    """Weighted average over components, dropping empty-vs-empty ones.

    Each ``component`` is a ``(fine_key, weight)`` pair. The weight is the
    nominal contribution when *all* components have data. When a component's
    ``data_presence`` is ``False``, that component is dropped and the
    remaining weights are rescaled to sum to 1.0 among themselves. If every
    component is empty-vs-empty, returns ``None`` — there is nothing to
    compare, so any number would be misleading.
    """
    present = [(key, w) for key, w in components if data_presence.get(key, False)]
    if not present:
        return None
    total_weight = sum(w for _, w in present)
    return sum(fine_scores[key] * w / total_weight for key, w in present)


def _adaptive_grouped(fine_scores, data_presence, components):
    """Weighted average over components, dropping empty-vs-empty ones.

    Each ``component`` is a ``(fine_key, weight)`` pair. The weight is the
    nominal contribution when *all* components have data. When a component's
    ``data_presence`` is ``False``, that component is dropped and the
    remaining weights are rescaled to sum to 1.0 among themselves. If every
    component is empty-vs-empty, returns ``None`` — there is nothing to
    compare so any number would be misleading.

    Used to compute the grouped scores (activities, events, gateways, flows,
    pools, subprocess) so that empty-vs-empty fine scores (which return the
    bogus 1.0 from Jaccard/Dice convention) do not inflate group totals.
    """
    present = [(key, w) for key, w in components if data_presence.get(key, False)]
    if not present:
        return None
    total_weight = sum(w for _, w in present)
    return sum(fine_scores[key] * w / total_weight for key, w in present)


def calculate_trace_similarity(
    traces_1: TracesOrResult,
    traces_2: TracesOrResult,
    method: str = "jaccard"
):
    """Calculate similarity between two sets of traces.

    Args:
        traces_1: First set of traces, or a :class:`TraceExtractionResult`.
        traces_2: Second set of traces, or a :class:`TraceExtractionResult`.
        method: Similarity metric – ``"jaccard"`` (default), ``"dice"``,
            ``"overlap"`` (overlap coefficient), or ``"precision"`` /
            ``"recall"`` / ``"f1"`` (computed over the deduped trace sets,
            with ``traces_1`` treated as ground truth).

    Returns:
        Similarity score between 0.0 and 1.0, or ``None`` when both trace
        sets are empty (no behavior to compare). The math-layer convention:
        when there is nothing to compare, return ``None`` rather than the
        bogus 1.0 that empty-vs-empty Jaccard/Dice produces.

        When given :class:`TraceExtractionResult` arguments, similarity is
        computed over the union of sound variants and partial traces from
        each side.
    """
    list_1 = _coerce_to_trace_list(traces_1)
    list_2 = _coerce_to_trace_list(traces_2)

    set_1 = list({tuple(trace) for trace in list_1})
    set_2 = list({tuple(trace) for trace in list_2})

    # Refuse to compare two empty trace sets — there is no behavior to
    # compare, so any number we return would be misleading. The dashboard
    # and other consumers branch on this None.
    if not set_1 and not set_2:
        return None

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

    # Level 2: Grouped — adaptive: each grouped score is a weighted average
    # over its fine-grained components, dropping empty-vs-empty ones and
    # rescaling the remaining weights. All-empty group → None.
    #
    # This subsumes:
    #   - Rule 2 (fine-grain empty in both → drop and rescale).
    #   - Rule 3 (msg flow empty in both → seq only): falls out automatically
    #     from the (seq, 0.7) / (mes, 0.3) pair when mes_flows_str has no data.
    #   - Rule 4 (seq AND msg empty → flows None): falls out from the helper
    #     returning None when no component has data.
    #   - Rule 5 (subprocess sub-keys): the 0.2/0.3/0.5 split rescales
    #     correctly when one or two sub-keys are empty; all three empty → None.
    grouped_scores = {
        "activities": _adaptive_grouped(fine_scores, data_presence, [
            ("activity_names", 0.5),
            ("activity_types", 0.5),
        ]),
        "events": _adaptive_grouped(fine_scores, data_presence, [
            ("event_names", 0.5),
            ("event_types", 0.5),
        ]),
        "gateways": _adaptive_grouped(fine_scores, data_presence, [
            ("gateway_names", 0.5),
            ("gateway_types", 0.5),
        ]),
        "flows": _adaptive_grouped(fine_scores, data_presence, [
            ("seq_flows_str", 0.7),
            ("mes_flows_str", 0.3),
        ]),
        "pools": _adaptive_grouped(fine_scores, data_presence, [
            ("lane_names", 0.5),
            ("lane_with_refs", 0.5),
        ]),
        "subprocess": _adaptive_grouped(fine_scores, data_presence, [
            ("subprocess_names", 0.2),
            ("subprocess_elemrefs", 0.3),
            ("subprocess_flows", 0.5),
        ]),
    }

    # Level 3: High-level
    # Check if either model has expanded subprocesses
    # Check both names and elements to catch subprocesses without names
    has_expanded_subprocess = (
        # len(sets1.get("subprocess_names", [])) > 0 or
        # len(sets2.get("subprocess_names", [])) > 0 or
        len(sets1.get("subprocess_elemrefs", [])) > 0 or
        len(sets2.get("subprocess_elemrefs", [])) > 0
        # len(sets1.get("subprocess_flows", [])) > 0 or
        # len(sets2.get("subprocess_flows", [])) > 0
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

    # High-level: "elements" averages over the present grouped sub-categories
    # (activities/events/gateways), skipping any that are None. All three None
    # → elements is None. The other three pass through directly (they are
    # already None-aware via _adaptive_grouped above).
    elements_present = [
        grouped_scores[g]
        for g in ("activities", "events", "gateways")
        if grouped_scores[g] is not None
    ]
    elements_score = (
        sum(elements_present) / len(elements_present) if elements_present else None
    )
    high_level_scores = {
        "elements": elements_score,
        "flows": grouped_scores["flows"],
        "organizational": grouped_scores["pools"],
        "subprocess": grouped_scores["subprocess"],
    }

    # Weighted overall score — skip None high-level categories and rescale
    # the remaining weights to sum to 1.0 among themselves. If every
    # high-level score is None, overall is None.
    live_categories = [k for k, v in high_level_scores.items() if v is not None]
    if not live_categories:
        overall = None
    else:
        live_weight_sum = sum(default_weights[k] for k in live_categories)
        if live_weight_sum == 0:
            # All live categories have weight 0 — can't compute a meaningful
            # weighted average. None is honest here.
            overall = None
        else:
            overall = sum(
                high_level_scores[k] * default_weights[k]
                for k in live_categories
            ) / live_weight_sum

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

    Args:
        structural_result: Result dict with an ``"overall"`` key holding a
            float or ``None``. Typically from :func:`calculate_bpmn_similarity`
            (or, in the dashboard's case, a small wrapper dict carrying the
            user-weighted overall).
        behavioral_score: Behavioral similarity (float in ``[0, 1]``) or
            ``None`` when no behavior could be compared, typically from
            :func:`calculate_trace_similarity`.
        structural_weight: Weight for the structural side (float in
            ``[0, 1]``). Behavioral weight is implicit as
            ``1 - structural_weight``. Default 0.5.

    Returns:
        Dict with ``structural``, ``behavioral``, ``structural_weight``,
        ``behavioral_weight``, and ``hybrid`` keys. When one side is
        ``None``, the other side becomes the hybrid (its effective weight is
        1.0 regardless of ``structural_weight``). When both are ``None``,
        ``hybrid`` is ``None``.
    """
    if not 0.0 <= structural_weight <= 1.0:
        raise ValueError(
            f"structural_weight must be in [0, 1], got {structural_weight}"
        )

    structural_score = structural_result["overall"]
    behavioral_weight = 1.0 - structural_weight

    # Handle undefined inputs per the propagation rules:
    #  - both None  → hybrid is undefined.
    #  - one None   → the defined side IS the hybrid; the slider position is
    #                 informational only (effective weight goes to 1.0/0.0).
    #  - both float → standard weighted combination.
    if structural_score is None and behavioral_score is None:
        hybrid = None
        effective_struct_w = 0.0
        effective_beh_w = 0.0
    elif structural_score is None:
        hybrid = behavioral_score
        effective_struct_w = 0.0
        effective_beh_w = 1.0
    elif behavioral_score is None:
        hybrid = structural_score
        effective_struct_w = 1.0
        effective_beh_w = 0.0
    else:
        hybrid = structural_weight * structural_score + behavioral_weight * behavioral_score
        effective_struct_w = structural_weight
        effective_beh_w = behavioral_weight

    return {
        "structural": structural_score,
        "behavioral": behavioral_score,
        "structural_weight": effective_struct_w,
        "behavioral_weight": effective_beh_w,
        "hybrid": hybrid,
    }