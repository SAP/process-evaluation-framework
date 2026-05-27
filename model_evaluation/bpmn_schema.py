from typing import Any, Dict, List

# simplified BPMN JSON schema.
# it captures the most used BPMN elements as lists.
# each element has an id, which allows cross-referencing of elements across the lists.
bpmn_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "BPMN Schema",
    "type": "object",
    "properties": {
        "activities": {
            "type": "array",
            "items": {"$ref": "#/$defs/activity"},
        },
        "events": {"type": "array", "items": {"$ref": "#/$defs/event"}},
        "gateways": {"type": "array", "items": {"$ref": "#/$defs/gateway"}},
        "pools": {"type": "array", "items": {"$ref": "#/$defs/pool"}},
        "sequenceFlows": {"type": "array", "items": {"$ref": "#/$defs/sequenceFlow"}},
        "messageFlows": {"type": "array", "items": {"$ref": "#/$defs/messageFlow"}},
    },
    "required": ["activities", "events", "gateways", "pools", "sequenceFlows", "messageFlows"],
    "$defs": {
        "activity": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "type": {
                    "enum": [
                        "Task",
                        "Manual",
                        "User",
                        "Send",
                        "Receive",
                        "Service",
                        "Business Rule",
                        "Script",
                        "Subprocess",
                        "CollapsedSubprocess",
                        "EventSubprocess",
                        "CollapsedEventSubprocess",
                    ]
                },
                "parent_subprocess": {"type": "string"},
                "elemRefs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of elements inside this subprocess (for expanded subprocesses)"
                },
                "subprocessSequenceFlows": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/sequenceFlow"},
                    "description": "Sequence flows internal to this subprocess"
                },
            },
            "required": ["id", "type"],
            "description": "A unit of work, the job to be performed. Can be a simple task or a subprocess containing other elements.",
        },
        "event": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "type": {
                    "enum": [
                        "StartNoneEvent",
                        "EndNoneEvent",
                        "IntermediateMessageEventCatching",
                        "IntermediateTimerEvent",
                        "StartMessageEvent",
                        "IntermediateMessageEventThrowing",
                        "EndMessageEvent",
                        "IntermediateConditionalEvent",
                        "IntermediateEscalationEvent",
                        "IntermediateErrorEvent",
                        "EndEscalationEvent",
                        "EndCancelEvent",
                        "IntermediateMultipleEventThrowing",
                        "IntermediateLinkEventThrowing",
                        "StartTimerEvent",
                        "IntermediateCancelEvent",
                        "IntermediateLinkEventCatching",
                    ]
                },
                "parent_subprocess": {"type": "string"},
            },
            "required": ["id", "type"],
        },
        "gateway": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "type": {"enum": ["Exclusive", "Parallel", "Eventbased", "Inclusive", "Complex"]},
                "parent_subprocess": {"type": "string"},
            },
            "required": ["id", "type"],
        },
        "pool": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "lanes": {"type": "array", "items": {"$ref": "#/$defs/lane"}},
            },
            "required": ["id", "name", "lanes"],
            "description": "Organization or role who performs the tasks",
        },
        "lane": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "elemRefs": {"type": "array", "items": {"type": "string"}},
            },
        },
        "sequenceFlow": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "sourceRef": {"type": "string"},
                "targetRef": {"type": "string"},
                "condition": {"type": "string"},
            },
            "required": ["id", "sourceRef", "targetRef"],
            "description": "Defines the execution order of activities. Activities, events and gateways within a pool must be connected with sequence flow. They can not stand alone. Pictured as an solid arrow",
        },
        "messageFlow": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "sourceRef": {"type": "string"},
                "targetRef": {"type": "string"},
                "label": {"type": "string"},
            },
            "required": ["id", "sourceRef", "targetRef"],
            "description": "Messages flow between different pools. Pictured as a an dotted arrow",
        },
    },
}


SUBPROCESS_TYPES = {"Subprocess", "EventSubprocess"}
COLLAPSED_SUBPROCESS_TYPES = {"CollapsedSubprocess", "CollapsedEventSubprocess"}
ALL_SUBPROCESS_TYPES = SUBPROCESS_TYPES | COLLAPSED_SUBPROCESS_TYPES


def _iter_flow_nodes(d: Dict[str, Any]):
    for kind in ("activities", "events", "gateways"):
        for elem in d.get(kind, []) or []:
            yield elem, kind


def derive_parent_subprocess(d: Dict[str, Any]) -> None:
    """Make `parent_subprocess` consistent with `elemRefs`, in place.

    `elemRefs` on subprocess activities is the source of truth. For every id
    listed in any `S.elemRefs`, set `parent_subprocess = S.id` on the
    referenced element. Any `parent_subprocess` on an element that is not
    referenced by some subprocess's `elemRefs` is removed.

    Call this once after a converter has produced a simplified BPMN dict.
    """
    id_to_subprocess: Dict[str, str] = {}
    for sp in d.get("activities", []) or []:
        if sp.get("type") in SUBPROCESS_TYPES:
            for child_id in sp.get("elemRefs", []) or []:
                id_to_subprocess[child_id] = sp["id"]

    for elem, _kind in _iter_flow_nodes(d):
        sp_id = id_to_subprocess.get(elem["id"])
        if sp_id is not None:
            elem["parent_subprocess"] = sp_id
        elif "parent_subprocess" in elem:
            del elem["parent_subprocess"]


def validate_simplified_bpmn(d: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable invariant violations.

    Empty list means the dict satisfies the canonical subprocess invariant.
    See the data-layer cleanup plan for the full statement.
    """
    issues: List[str] = []

    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    for elem, kind in _iter_flow_nodes(d):
        eid = elem.get("id")
        if eid is None:
            issues.append(f"{kind} entry without id: {elem!r}")
            continue
        if eid in nodes_by_id:
            issues.append(f"duplicate element id across activities/events/gateways: {eid}")
        nodes_by_id[eid] = elem

    subprocesses: Dict[str, Dict[str, Any]] = {}
    for sp in d.get("activities", []) or []:
        if sp.get("type") in ALL_SUBPROCESS_TYPES:
            subprocesses[sp["id"]] = sp

    # Rule: collapsed subprocesses have no internals
    for sp_id, sp in subprocesses.items():
        if sp.get("type") in COLLAPSED_SUBPROCESS_TYPES:
            if sp.get("elemRefs"):
                issues.append(f"collapsed subprocess {sp_id} has non-empty elemRefs")
            if sp.get("subprocessSequenceFlows"):
                issues.append(f"collapsed subprocess {sp_id} has non-empty subprocessSequenceFlows")

    # Rule: no id appears in more than one elemRefs
    seen_in_elemrefs: Dict[str, str] = {}
    for sp_id, sp in subprocesses.items():
        for child_id in sp.get("elemRefs", []) or []:
            prior = seen_in_elemrefs.get(child_id)
            if prior is not None and prior != sp_id:
                issues.append(
                    f"element {child_id} listed in elemRefs of both {prior} and {sp_id}"
                )
            seen_in_elemrefs[child_id] = sp_id

    # Rule 1: forward-implies-back
    for sp_id, sp in subprocesses.items():
        if sp.get("type") not in SUBPROCESS_TYPES:
            continue
        for child_id in sp.get("elemRefs", []) or []:
            child = nodes_by_id.get(child_id)
            if child is None:
                issues.append(
                    f"subprocess {sp_id} elemRefs references unknown element {child_id}"
                )
                continue
            if child.get("parent_subprocess") != sp_id:
                issues.append(
                    f"element {child_id} should have parent_subprocess={sp_id} "
                    f"but has {child.get('parent_subprocess')!r}"
                )

    # Rule 2: back-implies-forward
    for elem, _kind in _iter_flow_nodes(d):
        p = elem.get("parent_subprocess")
        if p is None:
            continue
        sp = subprocesses.get(p)
        if sp is None:
            issues.append(
                f"element {elem['id']} has parent_subprocess={p} but no such subprocess exists"
            )
            continue
        if elem["id"] not in (sp.get("elemRefs") or []):
            issues.append(
                f"element {elem['id']} claims parent_subprocess={p} "
                f"but is not in that subprocess's elemRefs"
            )

    # Rule: internal flow containment
    for sp_id, sp in subprocesses.items():
        ref_ids = set(sp.get("elemRefs") or [])
        for f in sp.get("subprocessSequenceFlows", []) or []:
            for endpoint_key in ("sourceRef", "targetRef"):
                endpoint = f.get(endpoint_key)
                if endpoint is not None and endpoint not in ref_ids:
                    issues.append(
                        f"subprocess {sp_id} internal flow {f.get('id')} "
                        f"{endpoint_key}={endpoint} not in elemRefs"
                    )

    # Rule: top-level sequenceFlows do not reference subprocess-internal elements
    for f in d.get("sequenceFlows", []) or []:
        for endpoint_key in ("sourceRef", "targetRef"):
            endpoint = f.get(endpoint_key)
            if endpoint is None:
                continue
            target_elem = nodes_by_id.get(endpoint)
            if target_elem is not None and target_elem.get("parent_subprocess"):
                issues.append(
                    f"top-level flow {f.get('id')} {endpoint_key}={endpoint} "
                    f"references element inside subprocess "
                    f"{target_elem['parent_subprocess']}"
                )

    return issues
