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
