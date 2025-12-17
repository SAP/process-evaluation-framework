# similarity functions for comparing two bpmn instances

from bpmn_sets import extract_bpmn_sets
from utils.list_similarity import dice_list, index_list, jaccard_list, scores


def calculate_bpmn_similarity(bpmn_object1, bpmn_object2, method="dice", weights=None):
    """
    Calculates BPMN similarity at three levels: fine, grouped, and high-level, with weighted overall score.

    Dynamically adjusts weights based on subprocess presence:
    - If either model has expanded subprocesses: structural=35%, flows=45%, organizational=15%, subprocess=5%
    - If no expanded subprocesses: redistributes subprocess weight proportionally
      (structural=36.84%, flows=47.37%, organizational=15.79%, subprocess=0%)

    Collapsed subprocesses are treated as regular activities and don't trigger subprocess weighting.

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

    return result


