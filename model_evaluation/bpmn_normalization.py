"""
BPMN Semantic Normalization

This module provides functions for semantically aligning BPMN model element names
using string similarity measures (e.g., BERT embeddings). This is an optional
preprocessing step that can improve similarity calculations when comparing models
with similar but not identical naming conventions.

Type fields (activity types, event types, gateway types) are NOT normalized here;
they are canonicalized deterministically at the conversion boundary
(see bpmn_conversion.py: canonicalize_gateway_type, ACTIVITY_TYPE_MAP).

Scope separation
----------------
Top-level elements and subprocess-internal elements are normalized in separate
passes and kept in separate mapping dicts. A subprocess-internal mapping for
'activity_names' is stored under the key 'activity_names__subprocess', so it
will only be applied to elements that have a 'parent_subprocess' field.
This prevents subprocess mappings from leaking into top-level elements
(or vice versa) when both scopes happen to share an element name.

Typical workflow:
1. Extract atomic names from both models
2. Build semantic mappings between names using similarity threshold
3. Apply mappings to align model2's names to model1's vocabulary
4. Proceed with standard BPMN similarity calculation

Example:
    from bpmn_normalization import normalize_atomic_names
    from utils.string_similarity import bert_cosine_optimized

    model2_aligned, mappings = normalize_atomic_names(
        model1, model2, bert_cosine_optimized, threshold=0.7
    )
"""

import copy

# Suffix used in the mappings dict to distinguish subprocess-internal mappings
# from top-level ones for the same atomic type.
SUBPROCESS_KEY_SUFFIX = "__subprocess"


def extract_atomic_names(bpmn, atomic_type, include_subprocess_internals=False):
    """
    Extract a set of atomic element names from a BPMN model.

    By default, extracts only top-level elements. Subprocess internal elements
    are extracted instead when include_subprocess_internals=True, maintaining
    scope separation.

    Args:
        bpmn: BPMN model dict in minimal JSON format
        atomic_type: Type of atomic elements to extract. Supported values:
            - 'activity_names': Names of activities
            - 'event_names': Names of events
            - 'gateway_names': Names of gateways
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
            result.update(a["name"] for a in bpmn.get("activities", [])
                         if a.get("name") and a.get("parent_subprocess"))
        else:
            result.update(a["name"] for a in bpmn.get("activities", [])
                         if a.get("name") and not a.get("parent_subprocess"))

    elif atomic_type == "event_names":
        if include_subprocess_internals:
            result.update(e["name"] for e in bpmn.get("events", [])
                         if e.get("name") and e.get("parent_subprocess"))
        else:
            result.update(e["name"] for e in bpmn.get("events", [])
                         if e.get("name") and not e.get("parent_subprocess"))

    elif atomic_type == "gateway_names":
        if include_subprocess_internals:
            result.update(g["name"] for g in bpmn.get("gateways", [])
                         if g.get("name") and g.get("parent_subprocess"))
        else:
            result.update(g["name"] for g in bpmn.get("gateways", [])
                         if g.get("name") and not g.get("parent_subprocess"))

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

    Greedy best-first 1-to-1 assignment: builds all candidate pairs above the
    similarity threshold, sorts by score descending, and walks the list
    assigning only when both sides are still free. Poor candidates (below
    threshold) remain unmatched rather than being force-paired.

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
    # Build all candidate pairs with scores
    candidates = []
    for n2 in names2:
        for n1 in names1:
            score = similarity_func(n1, n2)
            if score >= threshold:
                candidates.append((score, n2, n1))

    # Sort by score descending (best matches first)
    candidates.sort(reverse=True)

    # Assign greedily, respecting 1-to-1
    mapping = {}
    used_n1 = set()
    for score, n2, n1 in candidates:
        if n2 not in mapping and n1 not in used_n1:
            mapping[n2] = n1
            used_n1.add(n1)

    return mapping


def _apply_scoped(elements, mappings, key, in_subprocess):
    """
    Rename elements in-place if their name is in mappings[key], filtered by
    whether they are subprocess internals.

    Args:
        elements: List of element dicts (activities/events/gateways)
        mappings: Full mappings dict
        key: Mapping key to apply (e.g. 'event_names' or 'event_names__subprocess')
        in_subprocess: If True, only act on elements with parent_subprocess set.
                       If False, only act on elements without it.
    """
    if key not in mappings:
        return
    name_map = mappings[key]
    for el in elements:
        if bool(el.get("parent_subprocess")) != in_subprocess:
            continue
        name = el.get("name", "")
        if name in name_map:
            el["name"] = name_map[name]


def apply_atomic_name_mapping(bpmn, mappings):
    """
    Apply name mappings to a BPMN model, returning a modified copy.

    Mappings are scope-aware. Keys without the '__subprocess' suffix apply only
    to top-level elements; keys with the suffix apply only to subprocess
    internals. Pool and lane mappings have no subprocess variant since pools
    and lanes cannot live inside subprocesses.

    Args:
        bpmn: BPMN model dict in minimal JSON format
        mappings: Dict of name mappings, e.g.:
                 {
                     'activity_names':              {old: new, ...},  # top-level only
                     'activity_names__subprocess':  {old: new, ...},  # subprocess only
                     'event_names':                 {old: new, ...},
                     'event_names__subprocess':     {old: new, ...},
                     ...
                 }

    Returns:
        Deep copy of bpmn with names replaced according to mappings.
        Also fills empty subprocess parent names with their type for display.
    """
    bpmn2 = copy.deepcopy(bpmn)

    # Flow nodes — top-level and subprocess-internal handled separately
    for kind, collection_key in (("activity", "activities"),
                                 ("event",    "events"),
                                 ("gateway",  "gateways")):
        base_key = f"{kind}_names"
        sub_key  = base_key + SUBPROCESS_KEY_SUFFIX
        elements = bpmn2.get(collection_key, [])
        _apply_scoped(elements, mappings, base_key, in_subprocess=False)
        _apply_scoped(elements, mappings, sub_key,  in_subprocess=True)

    # Pool names (no subprocess scope possible)
    if "pool_names" in mappings:
        for pool in bpmn2.get("pools", []):
            name = pool.get("name", "")
            if name in mappings["pool_names"]:
                pool["name"] = mappings["pool_names"][name]

    # Lane names (no subprocess scope possible)
    if "lane_names" in mappings:
        for pool in bpmn2.get("pools", []):
            for lane in pool.get("lanes", []):
                lname = lane.get("name", "")
                if lname in mappings["lane_names"]:
                    lane["name"] = mappings["lane_names"][lname]

    # # Fill empty subprocess parent names with their type (for display/debugging)
    # for activity in bpmn2.get("activities", []):
    #     if activity.get("type", "").endswith("Subprocess") and not activity.get("name"):
    #         activity["name"] = activity.get("type", "Subprocess")

    return bpmn2


def create_all_atomic_mappings(bpmn1, bpmn2, similarity_func, threshold=0.7):
    """
    Create semantic mappings for all atomic element name types between two BPMN models.

    Top-level and subprocess-internal mappings are stored under DIFFERENT keys
    so they are not accidentally applied across scopes:
        'activity_names'              -> top-level activity name mappings
        'activity_names__subprocess'  -> subprocess-internal activity name mappings
        'event_names', 'event_names__subprocess'
        'gateway_names', 'gateway_names__subprocess'
        'pool_names', 'lane_names'    (no subprocess scope possible)

    Args:
        bpmn1: Reference BPMN model (ground truth vocabulary)
        bpmn2: BPMN model to align to bpmn1's vocabulary
        similarity_func: Function that compares two strings and returns similarity [0,1]
        threshold: Minimum similarity to create a mapping (default: 0.7)

    Returns:
        Dict of scoped mappings. Only includes keys for which at least one
        mapping was found.

    Example:
        >>> from string_similarity import bert_cosine_optimized
        >>> mappings = create_all_atomic_mappings(
        ...     model1, model2, bert_cosine_optimized, threshold=0.75
        ... )
        >>> sorted(mappings.keys())
        ['activity_names', 'event_names', 'event_names__subprocess', 'pool_names']
    """
    mapping_types = [
        "activity_names",
        "event_names",
        "gateway_names",
        "pool_names",
        "lane_names",
    ]
    mappings = {}

    # Top-level pass
    for mt in mapping_types:
        names1 = extract_atomic_names(bpmn1, mt, include_subprocess_internals=False)
        names2 = extract_atomic_names(bpmn2, mt, include_subprocess_internals=False)
        this_mapping = build_name_mapping(names1, names2, similarity_func, threshold)
        if this_mapping:
            mappings[mt] = this_mapping

    # Subprocess-internal pass — stored under separate keys so scopes don't bleed.
    # Only flow-node names can be inside subprocesses; pools and lanes cannot.
    subprocess_types = ["activity_names", "event_names", "gateway_names"]
    for mt in subprocess_types:
        sp_names1 = extract_atomic_names(bpmn1, mt, include_subprocess_internals=True)
        sp_names2 = extract_atomic_names(bpmn2, mt, include_subprocess_internals=True)
        if sp_names1 and sp_names2:
            sp_mapping = build_name_mapping(sp_names1, sp_names2, similarity_func, threshold)
            if sp_mapping:
                mappings[mt + SUBPROCESS_KEY_SUFFIX] = sp_mapping

    return mappings


def normalize_atomic_names(model1, model2, similarity_func, threshold=0.7):
    """
    Normalize model2's atomic element names to match model1's vocabulary.

    This is the main entry point for semantic normalization. It creates
    scope-separated mappings for all atomic name types and applies them to
    model2, returning an aligned version that uses model1's naming conventions
    where similar names are found.

    Args:
        model1: Reference BPMN model (ground truth vocabulary)
        model2: BPMN model to normalize
        similarity_func: String similarity function (e.g., bert_cosine_optimized)
        threshold: Minimum similarity score to align names (default: 0.7)
                  Higher = stricter matching, lower = more lenient

    Returns:
        Tuple of (model2_aligned, mappings) where:
        - model2_aligned: Deep copy of model2 with names aligned to model1
        - mappings: Dict of scope-separated name replacements
                    (top-level keys + '*__subprocess' keys; see
                    create_all_atomic_mappings for details)

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
        >>> # Or include behavioral (trace-based) similarity in the same call:
        >>> similarity = calculate_bpmn_similarity(
        ...     ground_truth_model,
        ...     model2_aligned,
        ...     method="dice",
        ...     behavioral=True,
        ... )
        >>> similarity["behavioral"]            # high-level behavioral score
        >>> similarity["behavioral_metric_used"]  # "dice" or "jaccard"
    """
    mappings = create_all_atomic_mappings(model1, model2, similarity_func, threshold)
    model2_aligned = apply_atomic_name_mapping(model2, mappings)
    return model2_aligned, mappings