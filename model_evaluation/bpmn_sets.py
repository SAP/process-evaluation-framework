# bpmn_sets.py

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
            return elem.get("type", "")
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
      - lane_names: list of "pool|lane" strings (one for each lane; if no lanes, just the pool).
      - lane_with_refs: list of "pool|lane|elemRefName" (if no lane, "pool||elemRefName")
    """
    lane_names = []
    lane_with_refs = []
    for pool in bpmn_instance.get("pools", []):
        pool_name = pool.get("name") or "Pool"
        lanes = pool.get("lanes", [])
        if not lanes:
            lane_names.append(pool_name)
        for lane in lanes:
            lane_name = lane.get("name") or "Lane"
            lane_group = "|".join([pool_name, lane_name])
            lane_names.append(lane_group)
            for ref_id in lane.get("elemRefs", []):
                # Lookup: activities, events, gateways; then fallback to id only if nothing found
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
                if not ref_val:
                    ref_val = ""  # Do not use the id in the visible set
                lane_with_refs.append("|".join([pool_name, lane_name, ref_val]))
    return lane_names, lane_with_refs


def get_subprocess_groups_with_refs(bpmn_instance):
    """
    Returns:
      - subprocess_names: list of subprocess names (uses type as fallback if name is empty).
      - subprocess_elemrefs: list of element names/types within subprocesses (structure-independent).
      - subprocess_flows: list of "sourceElem|targetElem" for internal flows (structure-independent).
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
    for activity in bpmn_instance.get("activities", []):
        act_type = activity.get("type", "")
        # Use exact type matching for expanded subprocesses
        if (
            act_type in ["Subprocess", "EventSubprocess"]
            and "elemRefs" in activity
        ):
            subprocess_name = activity.get("name") or activity.get("type", "Subprocess")
            subprocess_names.append(subprocess_name)
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
                if not ref_val:
                    ref_val = ""
                if ref_val:
                    # Remove subprocess name prefix to test structure independently
                    subprocess_elemrefs.append(ref_val)

            # Extract subprocess internal flows
            for flow in activity.get("subprocessSequenceFlows", []):
                source_val = get_ref_value(flow.get("sourceRef"))
                target_val = get_ref_value(flow.get("targetRef"))
                if source_val and target_val:
                    # Remove subprocess name prefix to test flow structure independently
                    subprocess_flows.append(f"{source_val}|{target_val}")

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


