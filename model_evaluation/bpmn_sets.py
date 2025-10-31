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
    for sequence_flow in bpmn_instance.get("sequenceFlows", []):
        sourceValue = get_ref_value(sequence_flow.get("sourceRef"))
        targetValue = get_ref_value(sequence_flow.get("targetRef"))
        condition = sequence_flow.get("condition", "")
        sequence_flows_with_values.append([sourceValue , condition, targetValue])

    message_flows_with_values = []
    for message_flow in bpmn_instance.get("messageFlows", []):
        sourceValue = get_ref_value(message_flow.get("sourceRef"))
        targetValue = get_ref_value(message_flow.get("targetRef"))
        label = message_flow.get("label", "")
        message_flows_with_values.append([sourceValue, label, targetValue])

    return sequence_flows_with_values, message_flows_with_values

def get_lanes_and_subprocess_groups(bpmn_instance):
    """
    Returns two lists:
      - lanes/group_names: all pool lanes and all expanded subprocess 'groups' (name or id if name absent)
      - lanes_with_refs: for both lanes and subprocesses, the full composition as a string like:
        "Pool - Lane - Activity", "Subprocess - Activity"
    """
    lanes_names = []
    lanes_with_refs = []
    # First, handle lanes as before
    for pool in bpmn_instance.get("pools", []):
        pool_name = pool.get("name", "")
        lanes = pool.get("lanes", [])
        if not lanes:
            lanes_names.append(pool_name)
        for lane in lanes:
            lane_name = lane.get("name", "")
            group_name = f"{pool_name} - {lane_name}"
            lanes_names.append(group_name)
            for ref_id in lane.get("elemRefs", []):
                ref_val = get_name_by_id(bpmn_instance, ref_id)
                if not ref_val:
                    # fallback type for gateway?
                    elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
                    ref_val = elem.get("type", "") if elem else ""
                lanes_with_refs.append(f"{group_name} - {ref_val}")

    # Now, for each expanded subprocess, treat as a group (like a lane)
    for activity in bpmn_instance.get("activities", []):
        if (
            activity.get("type", "").endswith("Subprocess")
            and "elemRefs" in activity
            and activity["type"] not in ["CollapsedSubprocess", "CollapsedEventSubprocess"]
        ):
            subprocess_name = activity.get("name", "") or activity.get("id", "")
            lanes_names.append(subprocess_name)
            for ref_id in activity.get("elemRefs", []):
                ref_val = get_name_by_id(bpmn_instance, ref_id)
                if not ref_val:
                    elem = get_element_by_id_from_sublist(bpmn_instance.get("gateways", []), ref_id)
                    ref_val = elem.get("type", "") if elem else ""
                lanes_with_refs.append(f"{subprocess_name} - {ref_val}")

    return lanes_names, lanes_with_refs

def get_list(bpmn_object, sublist, attribute):
    """Returns a list of attributes within a sublist of a bpmn_object."""
    return [t[attribute] for t in bpmn_object.get(sublist, []) if t.get(attribute)]

def extract_bpmn_sets(bpmn_object):
    """Extracts sets for structural comparison from a BPMN minimal instance."""
    sets = {}
    sets["activity_names"] = get_list(bpmn_object, "activities", "name")
    sets["activity_types"] = get_list(bpmn_object, "activities", "type")
    sets["event_names"] = get_list(bpmn_object, "events", "name")
    sets["event_types"] = get_list(bpmn_object, "events", "type")
    sets["gateway_names"] = get_list(bpmn_object, "gateways", "name")
    sets["gateway_types"] = get_list(bpmn_object, "gateways", "type")

    seq_flow_with_values, mes_flow_with_values = get_flows_with_values(bpmn_object)
    sets["seq_flows_str"] = [" ".join(e) for e in seq_flow_with_values]
    sets["mes_flows_str"] = [" ".join(e) for e in mes_flow_with_values]

    group_names, groups_with_refs = get_lanes_and_subprocess_groups(bpmn_object)
    sets["groups"] = group_names
    sets["groups_with_refs"] = groups_with_refs

    return sets

from string_similarity import bert_cosine_optimized as similarity_func


def extract_atomic_names(bpmn, atomic_type):
    """
    atomic_type: 'activity_names', 'event_names', 'gateway_names', 'pool_names', 'lane_names'
    """
    if atomic_type == "activity_names":
        return set(e['name'] for e in bpmn.get('activities', []) if e.get('name'))
    if atomic_type == "event_names":
        return set(e['name'] for e in bpmn.get('events', []) if e.get('name'))
    if atomic_type == "gateway_names":
        return set(e['name'] for e in bpmn.get('gateways', []) if e.get('name'))
    if atomic_type == "gateway_types":
        return set(e['type'] for e in bpmn.get('gateways', []) if e.get('type'))
    if atomic_type == "pool_names":
        return set(p['name'] for p in bpmn.get('pools', []) if p.get('name'))
    if atomic_type == "lane_names":
        lanes = []
        for pool in bpmn.get('pools', []):
            for lane in pool.get('lanes', []):
                lname = lane.get('name', '')
                if lname:
                    lanes.append(lname)
        return set(lanes)
    return set()

def build_name_mapping(names1, names2, similarity_func, threshold):
    """
    For each name2, finds the most similar name1 above threshold (if any),
    and returns name2 -> name1 mapping.
    """
    name_mapping = {}
    used_names1 = set()
    similarity_matrix = []
    for n2 in names2:
        row = []
        for n1 in names1:
            score = similarity_func(n2, n1)
            row.append((score, n1))
        similarity_matrix.append((n2, sorted(row, reverse=True)))  # sorted by score descending

    # greedy matching: for each n2, assign highest-available n1 if score above threshold
    for n2, candidates in sorted(similarity_matrix, key=lambda r: r[1][0][0], reverse=True):
        for score, n1 in candidates:
            if score >= threshold and n1 not in used_names1:
                name_mapping[n2] = n1
                used_names1.add(n1)
                break
    return name_mapping

def apply_atomic_name_mapping(bpmn, mapping_dict, atomic_type):
    """
    Returns a DEEP COPY of bpmn with mapped names.
    mapping_dict: {'activity_names': {...}, 'lane_names': {...}, ...}
    """
    import copy
    bpmn2 = copy.deepcopy(bpmn)
    # Activities
    if "activity_names" in mapping_dict:
        for activity in bpmn2.get('activities', []):
            old = activity.get('name', '')
            if old in mapping_dict['activity_names']:
                activity['name'] = mapping_dict['activity_names'][old]
    # Gateways/events
    if "event_names" in mapping_dict:
        for e in bpmn2.get('events', []):
            old = e.get('name', '')
            if old in mapping_dict['event_names']:
                e['name'] = mapping_dict['event_names'][old]
    if "gateway_names" in mapping_dict:
        for e in bpmn2.get('gateways', []):
            old = e.get('name', '')
            if old in mapping_dict['gateway_names']:
                e['name'] = mapping_dict['gateway_names'][old]
    # Pools
    if "pool_names" in mapping_dict:
        for p in bpmn2.get('pools', []):
            old = p.get('name', '')
            if old in mapping_dict['pool_names']:
                p['name'] = mapping_dict['pool_names'][old]
    # Lanes
    if "lane_names" in mapping_dict:
        for pool in bpmn2.get('pools', []):
            for lane in pool.get('lanes', []):
                old = lane.get('name', '')
                if old in mapping_dict['lane_names']:
                    lane['name'] = mapping_dict['lane_names'][old]
    return bpmn2