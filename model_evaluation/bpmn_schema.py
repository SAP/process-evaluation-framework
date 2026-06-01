from typing import Any, Dict

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
