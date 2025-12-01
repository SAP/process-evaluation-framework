"""
BPMN Semantic Normalization

This module provides functions for semantically aligning BPMN model element names
using string similarity measures (e.g., BERT embeddings). This is an optional
preprocessing step that can improve similarity calculations when comparing models
with similar but not identical naming conventions.

Typical workflow:
1. Extract atomic names from both models
2. Build semantic mappings between names using similarity threshold
3. Apply mappings to align model2's names to model1's vocabulary
4. Proceed with standard BPMN similarity calculation

Example:
    from bpmn_normalization import normalize_atomic_names
    from string_similarity import bert_cosine_optimized

    model2_aligned, mappings = normalize_atomic_names(
        model1, model2, bert_cosine_optimized, threshold=0.7
    )
"""

import copy


def extract_atomic_names(bpmn, atomic_type, include_subprocess_internals=False):
    """
    Extract a set of atomic element names or types from a BPMN model.

    By default, extracts only top-level elements. Subprocess internal elements
    are excluded unless explicitly requested, maintaining scope separation.

    Args:
        bpmn: BPMN model dict in minimal JSON format
        atomic_type: Type of atomic elements to extract. Supported values:
            - 'activity_names': Names of activities
            - 'activity_types': Types of activities
            - 'event_names': Names of events
            - 'event_types': Types of events
            - 'gateway_names': Names of gateways
            - 'gateway_types': Types of gateways
            - 'pool_names': Names of pools
            - 'lane_names': Names of lanes
        include_subprocess_internals: If True, extract subprocess internal elements
            instead of top-level elements. This ensures proper scope separation
            during normalization (default: False)

    Returns:
        Set of strings representing the requested atomic elements

    Example:
        >>> # Top-level only
        >>> activity_names = extract_atomic_names(bpmn_model, 'activity_names')
        >>> {'Plan travel', 'Book flight'}
        >>> # Subprocess internals only
        >>> sp_names = extract_atomic_names(bpmn_model, 'event_names', include_subprocess_internals=True)
        >>> {'Send quote request', 'Quote received'}
    """
    result = set()

    if atomic_type == "activity_names":
        if include_subprocess_internals:
            # Only subprocess internal elements
            for a in bpmn.get("activities", []):
                if a.get("type", "").endswith("Subprocess") and "elemRefs" in a:
                    for eid in a["elemRefs"]:
                        el = None
                        for x in bpmn.get("activities", []) + bpmn.get("events", []) + bpmn.get("gateways", []):
                            if x.get("id", "") == eid:
                                el = x
                                break
                        if el:
                            n = el.get("name") or el.get("type")
                            if n:
                                result.add(n)
        else:
            # Top-level activities only
            result.update(a["name"] for a in bpmn.get("activities", [])
                         if a.get("name") and not a.get("parent_subprocess"))

    elif atomic_type == "activity_types":
        if include_subprocess_internals:
            # Subprocess internal types
            for a in bpmn.get("activities", []):
                if a.get("type", "").endswith("Subprocess") and "elemRefs" in a:
                    for eid in a["elemRefs"]:
                        el = None
                        for x in bpmn.get("activities", []) + bpmn.get("events", []) + bpmn.get("gateways", []):
                            if x.get("id") == eid:
                                el = x
                                break
                        if el:
                            t = el.get("type")
                            if t:
                                result.add(t)
        else:
            # Top-level types only
            result.update(a["type"] for a in bpmn.get("activities", [])
                         if a.get("type") and not a.get("parent_subprocess"))

    elif atomic_type == "event_names":
        if include_subprocess_internals:
            # Subprocess internal events only
            result.update(e["name"] for e in bpmn.get("events", [])
                         if e.get("name") and e.get("parent_subprocess"))
        else:
            # Top-level events only
            result.update(e["name"] for e in bpmn.get("events", [])
                         if e.get("name") and not e.get("parent_subprocess"))

    elif atomic_type == "event_types":
        if include_subprocess_internals:
            result.update(e["type"] for e in bpmn.get("events", [])
                         if e.get("type") and e.get("parent_subprocess"))
        else:
            result.update(e["type"] for e in bpmn.get("events", [])
                         if e.get("type") and not e.get("parent_subprocess"))

    elif atomic_type == "gateway_names":
        if include_subprocess_internals:
            result.update(g["name"] for g in bpmn.get("gateways", [])
                         if g.get("name") and g.get("parent_subprocess"))
        else:
            result.update(g["name"] for g in bpmn.get("gateways", [])
                         if g.get("name") and not g.get("parent_subprocess"))

    elif atomic_type == "gateway_types":
        if include_subprocess_internals:
            result.update(g["type"] for g in bpmn.get("gateways", [])
                         if g.get("type") and g.get("parent_subprocess"))
        else:
            result.update(g["type"] for g in bpmn.get("gateways", [])
                         if g.get("type") and not g.get("parent_subprocess"))

    elif atomic_type == "pool_names":
        result.update(p["name"] for p in bpmn.get("pools", []) if p.get("name"))

    elif atomic_type == "lane_names":
        for pool in bpmn.get("pools", []):
            for lane in pool.get("lanes", []):
                lname = lane.get("name", "")
                if lname:
                    result.add(lname)

    return result


def build_name_mapping(names1, names2, similarity_func, threshold=0.7):
    """
    Build a mapping from names2 to semantically similar names in names1.

    For each name in names2, finds the most similar name in names1 using the
    provided similarity function. Only creates mappings where similarity >= threshold.

    Args:
        names1: Set/list of reference names (ground truth vocabulary)
        names2: Set/list of names to map
        similarity_func: Function that takes two strings and returns similarity score [0,1]
                        (e.g., bert_cosine_optimized from string_similarity module)
        threshold: Minimum similarity score to create a mapping (default: 0.7)

    Returns:
        Dict mapping names from names2 to their best match in names1
        {name2: name1} only for pairs with similarity >= threshold

    Example:
        >>> from string_similarity import bert_cosine_optimized
        >>> names1 = {'Plan travel', 'Book flight'}
        >>> names2 = {'Plan travels', 'Book flights'}
        >>> build_name_mapping(names1, names2, bert_cosine_optimized, threshold=0.8)
        {'Plan travels': 'Plan travel', 'Book flights': 'Book flight'}
    """
    mapping = {}
    for n2 in names2:
        best_score = -float("inf")
        best_n1 = None
        for n1 in names1:
            score = similarity_func(n1, n2)
            if score > best_score:
                best_score = score
                best_n1 = n1
        if best_score >= threshold:
            mapping[n2] = best_n1
    return mapping


def apply_atomic_name_mapping(bpmn, mappings):
    """
    Apply name mappings to a BPMN model, returning a modified copy.

    Replaces atomic element names/types according to the provided mappings.
    Handles both top-level elements and subprocess internals.

    Args:
        bpmn: BPMN model dict in minimal JSON format
        mappings: Dict of mappings for different atomic types, e.g.:
                 {
                     'activity_names': {old_name: new_name, ...},
                     'event_types': {old_type: new_type, ...},
                     ...
                 }

    Returns:
        Deep copy of bpmn with names/types replaced according to mappings.
        Also fills empty subprocess names with their type for display purposes.

    Example:
        >>> mappings = {'activity_names': {'Plan travels': 'Plan travel'}}
        >>> aligned_model = apply_atomic_name_mapping(model2, mappings)
    """
    bpmn2 = copy.deepcopy(bpmn)

    # Activity names (top-level)
    if "activity_names" in mappings:
        for activity in bpmn2.get("activities", []):
            name = activity.get("name", "")
            if name in mappings["activity_names"]:
                activity["name"] = mappings["activity_names"][name]

    # Activity names (subprocess internals)
    if "activity_names" in mappings:
        for a in bpmn2.get("activities", []):
            if a.get("type", "").endswith("Subprocess") and "elemRefs" in a:
                for eid in a["elemRefs"]:
                    for x in bpmn2.get("activities", []) + bpmn2.get("events", []):
                        if x.get("id", "") == eid:
                            name = x.get("name", "")
                            if name in mappings["activity_names"]:
                                x["name"] = mappings["activity_names"][name]

    # Activity types
    if "activity_types" in mappings:
        for activity in bpmn2.get("activities", []):
            typename = activity.get("type", "")
            if typename in mappings["activity_types"]:
                activity["type"] = mappings["activity_types"][typename]
        # Subprocess internals
        for a in bpmn2.get("activities", []):
            if a.get("type", "").endswith("Subprocess") and "elemRefs" in a:
                for eid in a["elemRefs"]:
                    for x in bpmn2.get("activities", []) + bpmn2.get("events", []):
                        if x.get("id", "") == eid:
                            typename = x.get("type", "")
                            if typename in mappings["activity_types"]:
                                x["type"] = mappings["activity_types"][typename]

    # Event names
    if "event_names" in mappings:
        for event in bpmn2.get("events", []):
            name = event.get("name", "")
            if name in mappings["event_names"]:
                event["name"] = mappings["event_names"][name]

    # Event types
    if "event_types" in mappings:
        for event in bpmn2.get("events", []):
            typename = event.get("type", "")
            if typename in mappings["event_types"]:
                event["type"] = mappings["event_types"][typename]

    # Gateway names
    if "gateway_names" in mappings:
        for gateway in bpmn2.get("gateways", []):
            name = gateway.get("name", "")
            if name in mappings["gateway_names"]:
                gateway["name"] = mappings["gateway_names"][name]

    # Gateway types
    if "gateway_types" in mappings:
        for gateway in bpmn2.get("gateways", []):
            typename = gateway.get("type", "")
            if typename in mappings["gateway_types"]:
                gateway["type"] = mappings["gateway_types"][typename]

    # Pool names
    if "pool_names" in mappings:
        for pool in bpmn2.get("pools", []):
            name = pool.get("name", "")
            if name in mappings["pool_names"]:
                pool["name"] = mappings["pool_names"][name]

    # Lane names
    if "lane_names" in mappings:
        for pool in bpmn2.get("pools", []):
            for lane in pool.get("lanes", []):
                lname = lane.get("name", "")
                if lname in mappings["lane_names"]:
                    lane["name"] = mappings["lane_names"][lname]

    # Fill empty subprocess names with their type (for display/debugging)
    for activity in bpmn2.get("activities", []):
        if activity.get("type", "").endswith("Subprocess") and not activity.get("name"):
            activity["name"] = activity.get("type", "Subprocess")

    return bpmn2


def create_all_atomic_mappings(bpmn1, bpmn2, similarity_func, threshold=0.7):
    """
    Create semantic mappings for all atomic element types between two BPMN models.

    Maintains scope separation: top-level elements map to top-level elements,
    subprocess internal elements map to subprocess internal elements. This prevents
    incorrect mappings across hierarchical boundaries.

    Args:
        bpmn1: Reference BPMN model (ground truth vocabulary)
        bpmn2: BPMN model to align to bpmn1's vocabulary
        similarity_func: Function that compares two strings and returns similarity [0,1]
        threshold: Minimum similarity to create a mapping (default: 0.7)

    Returns:
        Dict of mappings for each atomic type that has at least one mapping:
        {
            'activity_names': {name2: name1, ...},
            'event_types': {type2: type1, ...},
            ...
        }
        Only includes keys for types where mappings were found.

    Example:
        >>> from string_similarity import bert_cosine_optimized
        >>> mappings = create_all_atomic_mappings(
        ...     model1, model2, bert_cosine_optimized, threshold=0.75
        ... )
        >>> mappings.keys()
        dict_keys(['activity_names', 'event_names', 'pool_names'])
    """
    mapping_types = [
        "activity_names",
        "activity_types",
        "event_names",
        "event_types",
        "gateway_names",
        "gateway_types",
        "pool_names",
        "lane_names",
    ]
    mappings = {}

    # Map top-level elements
    for mt in mapping_types:
        names1 = extract_atomic_names(bpmn1, mt, include_subprocess_internals=False)
        names2 = extract_atomic_names(bpmn2, mt, include_subprocess_internals=False)
        this_mapping = build_name_mapping(names1, names2, similarity_func, threshold)
        if this_mapping:
            mappings[mt] = this_mapping

    # Map subprocess internal elements separately (only for element types that can be inside subprocesses)
    subprocess_types = ["activity_names", "activity_types", "event_names", "event_types",
                        "gateway_names", "gateway_types"]
    for mt in subprocess_types:
        sp_names1 = extract_atomic_names(bpmn1, mt, include_subprocess_internals=True)
        sp_names2 = extract_atomic_names(bpmn2, mt, include_subprocess_internals=True)

        # Only create mappings if both models have subprocess internal elements of this type
        if sp_names1 and sp_names2:
            sp_mapping = build_name_mapping(sp_names1, sp_names2, similarity_func, threshold)
            if sp_mapping:
                # Merge with existing mappings for this type (top-level + subprocess)
                if mt in mappings:
                    mappings[mt].update(sp_mapping)
                else:
                    mappings[mt] = sp_mapping

    return mappings


def normalize_atomic_names(model1, model2, similarity_func, threshold=0.7):
    """
    Normalize model2's atomic element names to match model1's vocabulary.

    This is the main entry point for semantic normalization. It creates mappings
    for all atomic element types and applies them to model2, returning an aligned
    version that uses model1's naming conventions where similar names are found.

    Args:
        model1: Reference BPMN model (ground truth vocabulary)
        model2: BPMN model to normalize
        similarity_func: String similarity function (e.g., bert_cosine_optimized)
        threshold: Minimum similarity score to align names (default: 0.7)
                  Higher = stricter matching, lower = more lenient

    Returns:
        Tuple of (model2_aligned, mappings) where:
        - model2_aligned: Deep copy of model2 with names aligned to model1
        - mappings: Dict showing all name replacements made

    Example:
        >>> from string_similarity import bert_cosine_optimized
        >>> model2_aligned, mappings = normalize_atomic_names(
        ...     ground_truth_model,
        ...     generated_model,
        ...     bert_cosine_optimized,
        ...     threshold=0.7
        ... )
        >>> # Now compare with standard similarity calculation
        >>> from bpmn_similarity import calculate_bpmn_similarity
        >>> similarity = calculate_bpmn_similarity(
        ...     ground_truth_model, model2_aligned, method="dice"
        ... )
    """
    mappings = create_all_atomic_mappings(model1, model2, similarity_func, threshold)
    model2_aligned = apply_atomic_name_mapping(model2, mappings)
    return model2_aligned, mappings
