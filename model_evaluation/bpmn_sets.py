
def get_element_by_id_from_sublist(bpmn_sublist, id_):
    """Find element by id in one of the sublists."""
    for item in bpmn_sublist:
        if item.get("id", "") == id_:
            return item
    return None

def get_name_by_id(bpmn_instance, id_):
    """Returns the name of the element with the given id."""
    # Search all relevant sublists in the bpmn_instance for the given id.
    for sublist in ["activities", "events", "gateways", "pools"]:
        for item in bpmn_instance.get(sublist, []):
            if item.get("id", "") == id_:
                return item.get("name", "")
    return ""

def get_flows_with_values(bpmn_instance):
    """Get sequence and message flows as [sourceValue, label, targetValue], where label is 'condition' or 'label'."""
    # Helper for looking up names/types for referenced IDs
    def get_ref_value(ref_id):
        if not ref_id:
            return ''
        # Try activities, events first (by name)
        for sublist in ["activities", "events"]:
            elem = get_element_by_id_from_sublist(bpmn_instance.get(sublist, []), ref_id)
            if elem:
                return elem.get("name", "")
        # Then try pools (by name)
        elem = get_element_by_id_from_sublist(bpmn_instance.get("pools", []), ref_id)
        if elem:
            return elem.get("name", "")
        # Then try gateways (by type)
        elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
        if elem:
            return elem.get("name") or elem.get("type", "")
        return ""

    sequence_flows_with_values = []

    # Top-level sequence flows only (subprocess internal flows handled separately)
    for sequence_flow in bpmn_instance.get("sequenceFlows", []):
        sourceValue = get_ref_value(sequence_flow.get("sourceRef"))
        targetValue = get_ref_value(sequence_flow.get("targetRef"))
        # condition = sequence_flow.get("condition", "")
        sequence_flows_with_values.append([sourceValue ,  targetValue])

    message_flows_with_values = []
    for message_flow in bpmn_instance.get("messageFlows", []):
        sourceValue = get_ref_value(message_flow.get("sourceRef"))
        targetValue = get_ref_value(message_flow.get("targetRef"))
        # label = message_flow.get("label", "")
        message_flows_with_values.append([sourceValue,  targetValue])

    return sequence_flows_with_values, message_flows_with_values



def get_lane_groups_with_refs(bpmn_instance):
    """
    Returns:
      - lane_names: list of "pool|lane" strings. Unnamed pools/lanes contribute
        empty name components (e.g. "|Driver" or "Car|"); a group is omitted
        only when BOTH the pool and lane names are empty (no identity signal).
      - lane_with_refs: list of "pool|lane|elemRefName". Element rows are kept
        even when the pool/lane is unnamed (e.g. "||Start"), so the set of
        contained elements is still compared across models.

    No placeholder strings ("Pool"/"Lane") are injected for missing names, since
    that would make unnamed containers falsely match across unrelated models.
    """
    lane_names = []
    lane_with_refs = []
    for pool in bpmn_instance.get("pools", []):
        pool_name = pool.get("name", "")
        lanes = pool.get("lanes", [])
        if not lanes:
            # Pool with no lanes: only contributes if it actually has a name.
            if pool_name:
                lane_names.append(pool_name)
            continue
        for lane in lanes:
            lane_name = lane.get("name", "")
            # Add the lane group only if there is some name signal.
            if pool_name or lane_name:
                lane_names.append("|".join([pool_name, lane_name]))
            for ref_id in lane.get("elemRefs", []):
                # Lookup: activities, events, gateways; no id fallback in the set
                ref_val = ""
                for sublist in ["activities", "events"]:
                    elem = get_element_by_id_from_sublist(bpmn_instance.get(sublist, []), ref_id)
                    if elem:
                        ref_val = elem.get("name", "") or elem.get("type", "")
                        break
                if not ref_val:
                    elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
                    if elem:
                        ref_val = elem.get("type", "")
                # Keep element rows even when pool/lane are unnamed, but only when
                # the referenced element itself resolves to a real name/type.
                if ref_val:
                    lane_with_refs.append("|".join([pool_name, lane_name, ref_val]))
    return lane_names, lane_with_refs


def get_subprocess_groups_with_refs(bpmn_instance):
    """
    Returns:
      - subprocess_names: list of subprocess names (real names only; unnamed
        subprocesses are not added here — no type placeholder).
      - subprocess_elemrefs: list of "scopeKey|elementName" within subprocesses.
        Each element is prefixed with its subprocess scope so elements are only
        compared within their corresponding subprocess (mirrors how lanes are
        scoped by pool|lane), not pooled across unrelated subprocesses.
      - subprocess_flows: list of "scopeKey|sourceElem|targetElem" for internal
        flows, prefixed the same way.

    Scope key (per subprocess):
      - the subprocess name when it has one (already normalized upstream, since
        the subprocess parent is a top-level activity)
      - "__sp{N}" otherwise, where N counts unnamed subprocesses in document
        order. This pairs the i-th unnamed subprocess of one model with the
        i-th unnamed subprocess of the other ("name and order" matching).
    """
    # Helper for looking up names/types for referenced IDs
    def get_ref_value(ref_id):
        if not ref_id:
            return ''
        for sublist in ["activities", "events"]:
            elem = get_element_by_id_from_sublist(bpmn_instance.get(sublist, []), ref_id)
            if elem:
                return elem.get("name", "") or elem.get("type", "")
        elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
        if elem:
            return elem.get("type", "")
        return ""

    subprocess_names = []
    subprocess_elemrefs = []
    subprocess_flows = []
    unnamed_counter = 0
    for activity in bpmn_instance.get("activities", []):
        act_type = activity.get("type", "")
        # Use exact type matching for expanded subprocesses
        if (
            act_type in ["Subprocess", "EventSubprocess"]
            and "elemRefs" in activity
        ):
            subprocess_name = activity.get("name", "").strip()
            if subprocess_name:
                # Named subprocess: scope by name, also contribute to the names set.
                scope_key = subprocess_name
                subprocess_names.append(subprocess_name)
            else:
                # Unnamed subprocess: scope by positional identity (document order).
                scope_key = f"__sp{unnamed_counter}"
                unnamed_counter += 1

            for ref_id in activity.get("elemRefs", []):
                ref_val = ""
                # Should check both activities AND events for referenced elements!
                for sublist in ["activities", "events"]:
                    elem = get_element_by_id_from_sublist(bpmn_instance.get(sublist, []), ref_id)
                    if elem:
                        ref_val = elem.get("name", "") or elem.get("type", "")
                        break
                if not ref_val:
                    elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
                    if elem:
                        ref_val = elem.get("type", "")
                if ref_val:
                    # Prefix with scope key so elements are compared within their
                    # subprocess, not pooled across all subprocesses.
                    subprocess_elemrefs.append(f"{scope_key}|{ref_val}")

            # Extract subprocess internal flows
            for flow in activity.get("subprocessSequenceFlows", []):
                source_val = get_ref_value(flow.get("sourceRef"))
                target_val = get_ref_value(flow.get("targetRef"))
                if source_val and target_val:
                    # Prefix with scope key so flows are compared within their subprocess.
                    subprocess_flows.append(f"{scope_key}|{source_val}|{target_val}")

    return subprocess_names, subprocess_elemrefs, subprocess_flows

def get_list(bpmn_object, sublist, attribute):
    """Returns a list of attributes within a sublist of a bpmn_object."""
    return [t[attribute] for t in bpmn_object.get(sublist, []) if t.get(attribute)]

def extract_bpmn_sets(bpmn_object):
    """Extracts structure-aware lists for comparison — main process only unless otherwise specified."""

    # Only MAIN process elements (top-level, not in subprocess)
    sets = {}
    sets["activity_names"] = [a.get("name", "") for a in bpmn_object.get("activities", []) if not a.get("parent_subprocess", "")]
    sets["activity_types"] = [a.get("type", "") for a in bpmn_object.get("activities", []) if not a.get("parent_subprocess", "")]
    sets["event_names"]    = [e.get("name", "") for e in bpmn_object.get("events", []) if not e.get("parent_subprocess", "")]
    sets["event_types"]    = [e.get("type", "") for e in bpmn_object.get("events", []) if not e.get("parent_subprocess", "")]
    sets["gateway_names"]  = [g.get("name", "") for g in bpmn_object.get("gateways", []) if not g.get("parent_subprocess", "")]
    sets["gateway_types"]  = [g.get("type", "") for g in bpmn_object.get("gateways", []) if not g.get("parent_subprocess", "")]

    # Flows, lanes, pools as before — filter as needed
    seq_flow_with_values, mes_flow_with_values = get_flows_with_values(bpmn_object)
    sets["seq_flows_str"] = ["|".join(e) for e in seq_flow_with_values]
    sets["mes_flows_str"] = ["|".join(e) for e in mes_flow_with_values]

    lane_names, lane_with_refs = get_lane_groups_with_refs(bpmn_object)
    sets["lane_names"] = lane_names
    sets["lane_with_refs"] = lane_with_refs

    subprocess_names, subprocess_elemrefs, subprocess_flows = get_subprocess_groups_with_refs(bpmn_object)
    sets["subprocess_names"] = subprocess_names
    sets["subprocess_elemrefs"] = subprocess_elemrefs
    sets["subprocess_flows"] = subprocess_flows

    return sets