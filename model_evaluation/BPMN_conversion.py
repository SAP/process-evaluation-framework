import json
from typing import Any, Dict, List, Union

from sapsam_mapping import sapsam_mapping

BPMNShape = Dict[str, Any]
FlattenedBPMN = Dict[str, List[Dict[str, Any]]]


# == Gateway type canonicalization ===============================================
# Maps any known synonym, stencil ID, or XML tag → canonical output string.
# Case-insensitive lookup; falls back to the raw input if no alias matches.
# Shared by both the Signavio-JSON and BPMN-XML converters below to keep
# both pipelines symmetric.
_GATEWAY_TYPE_ALIASES = {
    # canonical → itself (idempotence)
    "exclusive":                    "Exclusive",
    "parallel":                     "Parallel",
    "inclusive":                    "Inclusive",
    "eventbased":                   "Eventbased",
    "complex":                      "Complex",
    # symbolic / textual aliases sometimes used as the type value
    "and":                          "Parallel",
    "xor":                          "Exclusive",
    "or":                           "Inclusive",
    # Signavio stencil IDs
    "parallelgateway":              "Parallel",
    "exclusive_databased_gateway":  "Exclusive",
    "inclusivegateway":             "Inclusive",
    "eventbasedgateway":            "Eventbased",
    "complexgateway":               "Complex",
    # BPMN 2.0 XML local tag names
    "exclusivegateway":             "Exclusive",
}


def canonicalize_gateway_type(raw: str) -> str:
    """Map any known gateway-type alias to its canonical form.
    Case-insensitive. Returns the input unchanged if no alias matches."""
    if not raw:
        return raw
    return _GATEWAY_TYPE_ALIASES.get(raw.strip().lower(), raw)


class BPMNModel:
    """Data class representing a flattened BPMN model with subprocess awareness."""
    def __init__(self):
        self.activities: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.gateways: List[Dict[str, Any]] = []
        self.pools: List[Dict[str, Any]] = []
        self.message_flows: List[Dict[str, Any]] = []
        self.sequence_flows: List[Dict[str, Any]] = []

    def to_dict(self) -> FlattenedBPMN:
        return {
            "activities": self.activities,
            "events": self.events,
            "gateways": self.gateways,
            "pools": self.pools,
            "messageFlows": self.message_flows,
            "sequenceFlows": self.sequence_flows
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

class BPMNConverter:
    """Signavio-to-minimal BPMN converter with subprocesses and correct flow refs."""

    ACTIVITY_TYPE_MAP = {
        "Task": "Task",
        "Manual": "Manual",
        "User": "User",
        "Send": "Send",
        "Receive": "Receive",
        "Service": "Service",
        "Business Rule": "Business Rule",
        "Script": "Script",
        "Subprocess": "Subprocess",
        "CollapsedSubprocess": "CollapsedSubprocess",              # was "Subprocess" — reverted
        "EventSubprocess": "EventSubprocess",
        "CollapsedEventSubprocess": "CollapsedEventSubprocess",    # was "EventSubprocess" — reverted
    }

    @classmethod
    def convert(cls, json_data: Union[str, BPMNShape]) -> BPMNModel:
        if isinstance(json_data, str):
            json_data = json.loads(json_data)
        model = BPMNModel()
        shape = json_data
        if sapsam_mapping.get(shape['stencil']['id']) == "Diagram":
            cls._process_scope(
                shape.get("childShapes", []),
                model,
                activities=model.activities,
                events=model.events,
                gateways=model.gateways,
                sequence_flows=model.sequence_flows,
                message_flows=model.message_flows,
                parent_lane=None,
                parent_subprocess=None
            )
        else:
            cls._process_scope(
                [shape], model,
                activities=model.activities,
                events=model.events,
                gateways=model.gateways,
                sequence_flows=model.sequence_flows,
                message_flows=model.message_flows,
                parent_lane=None,
                parent_subprocess=None
            )
        cls._finalize_model(model)
        return model

    @classmethod
    def _process_scope(cls, shape_list, model, activities, events, gateways, sequence_flows, message_flows, parent_lane=None, parent_subprocess=None):
        """
        Recursively process a list of shapes. Adds elements/flows to provided lists.
        """
        element_map = {}  # id -> element dict (for connecting sequence flow sourceRef in-scope only)
        flows_to_process = []
        for shape in shape_list:
            stencil = sapsam_mapping.get(shape["stencil"]["id"])
            if not stencil:
                print(f"WARNING: Unrecognized shape {shape['stencil']['id']} -- skipped")
                continue
            if stencil == "Pools":
                pool_elem = cls._create_base_element(shape, parent_lane)
                pool_elem["lanes"] = []
                for lane in shape.get("childShapes", []):
                    lane_stencil = sapsam_mapping.get(lane["stencil"]["id"])
                    assert lane_stencil == "Lanes", "Pools should only have lanes as children"
                    assert len(lane.get("outgoing", [])) == 0, "Lanes should not have outgoing elements"
                    lane_info = {
                        "id": lane["resourceId"],
                        "name": cls._extract_name(lane),
                    }
                    pool_elem["lanes"].append(lane_info)
                    # Process everything in this lane
                    cls._process_scope(
                        lane.get("childShapes", []), model,
                        activities=activities,
                        events=events,
                        gateways=gateways,
                        sequence_flows=sequence_flows,
                        message_flows=message_flows,
                        parent_lane=lane["resourceId"],
                        parent_subprocess=parent_subprocess
                    )
                model.pools.append(pool_elem)
            elif stencil == "Activities":
                elem = cls._create_base_element(shape, parent_lane, parent_subprocess)
                task_type = shape["properties"].get("tasktype", None)
                if task_type and task_type != "None":
                    minimal_type = cls.ACTIVITY_TYPE_MAP.get(task_type, task_type)
                else:
                    minimal_type = cls.ACTIVITY_TYPE_MAP.get(shape["stencil"]["id"], shape["stencil"]["id"])
                elem["type"] = minimal_type
                # If this is a subprocess, recurse!
                if minimal_type in [
                    "Subprocess", "EventSubprocess"]:
                    # Split childShapes into flows and children
                    children = []
                    sub_flows = []
                    for c in shape.get("childShapes", []):
                        c_type = sapsam_mapping.get(c["stencil"]["id"])
                        if c_type == "Sequence Flows":
                            sub_flows.append(c)
                        elif c_type in {"Activities", "Events", "Gateways"}:
                            children.append(c)
                    elem_refs = [c["resourceId"] for c in children]
                    elem["elemRefs"] = elem_refs

                    # Local lists for subprocess children
                    sub_acts, sub_events, sub_gats, sub_seq = [], [], [], []
                    cls._process_scope(children, model,
                        activities=sub_acts,
                        events=sub_events,
                        gateways=sub_gats,
                        sequence_flows=sub_seq,
                        message_flows=[],
                        parent_lane=parent_lane,
                        parent_subprocess=elem["id"]
                    )
                    for a in sub_acts:
                        if a["id"] not in {e["id"] for e in model.activities}:
                            model.activities.append(a)
                    for e in sub_events:
                        if e["id"] not in {ev["id"] for ev in model.events}:
                            model.events.append(e)
                    for g in sub_gats:
                        if g["id"] not in {gw["id"] for gw in model.gateways}:
                            model.gateways.append(g)
                    # Subprocess flows (internal only)
                    sub_seq_flows = []
                    for sf in sub_flows:
                        flow = cls._create_base_element(sf)
                        flow["targetRef"] = sf.get("target", {}).get("resourceId")
                        name = flow.pop("name", None)
                        if name:
                            flow["condition"] = name
                        # Compute sourceRef local to this subprocess only
                        for e in (sub_acts + sub_events + sub_gats):
                            for outgoing in e.get("outgoing", []):
                                if outgoing.get("resourceId") == sf["resourceId"]:
                                    flow["sourceRef"] = e["id"]
                        sub_seq_flows.append({k: v for k, v in flow.items() if v is not None})
                    if sub_seq_flows:
                        elem["subprocessSequenceFlows"] = sub_seq_flows
                    activities.append(elem)
                else:
                    activities.append(elem)
                element_map[elem["id"]] = elem
            elif stencil == "Events":
                elem = cls._create_base_element(shape, parent_lane, parent_subprocess)
                elem["type"] = shape["stencil"]["id"]
                events.append(elem)
                element_map[elem["id"]] = elem
            elif stencil == "Gateways":
                elem = cls._create_base_element(shape, parent_lane, parent_subprocess)
                elem["type"] = canonicalize_gateway_type(shape["stencil"]["id"])
                if not elem["name"]:
                    del elem["name"]
                gateways.append(elem)
                element_map[elem["id"]] = elem
            elif stencil == "Sequence Flows":
                flow = cls._create_base_element(shape)
                flow["targetRef"] = shape.get("target", {}).get("resourceId")
                name = flow.pop("name", None)
                if name:
                    flow["condition"] = name
                flows_to_process.append(flow)


            elif stencil == "Message Flows":
                flow = cls._create_base_element(shape)
                flow["targetRef"] = shape.get("target", {}).get("resourceId")
                name = flow.pop("name", None)
                if name:
                    flow["label"] = name
                message_flows.append(flow)
            # Lanes handled only inside pools

        # Don't do sourceRef processing in element_map for global flows! (handled in finalize)
        for flow in flows_to_process:
            # Only add to output if this is the main/top-level
            if sequence_flows is not None:
                sequence_flows.append({k: v for k, v in flow.items() if v is not None})

    @classmethod
    def _extract_name(cls, shape: BPMNShape) -> str:
        props = shape.get("properties", {})
        for key in ("name", "name_en_gb", "name_de_de"):
            if props.get(key):
                return props[key].replace("\n", " ").strip()
        return ""

    @classmethod
    def _create_base_element(cls, shape: BPMNShape, parent_lane: str = None, parent_subprocess: str = None) -> Dict[str, Any]:
        element = {
            "id": shape["resourceId"],
            "name": cls._extract_name(shape),
            "outgoing": shape.get("outgoing", []),
        }
        if parent_lane:
            element["parent_lane"] = parent_lane
        if parent_subprocess:
            element["parent_subprocess"] = parent_subprocess
        return element

    @classmethod
    def _connect_flows(cls, model: BPMNModel) -> None:
        """Set sourceRef for all top-level sequence and message flows (like classic)."""
        all_flows = model.sequence_flows + model.message_flows
        all_elements = model.activities + model.events + model.gateways + model.pools
        for flow in all_flows:
            for element in all_elements:
                for outgoing in element.get("outgoing", []):
                    if flow.get("id") == outgoing.get("resourceId"):
                        flow["sourceRef"] = element.get("id")

    @classmethod
    def _reorganize_subprocess_flows(cls, model: BPMNModel):
        """Move internal subprocess flows from top-level to subprocessSequenceFlows."""
        # Build map: element_id -> parent_subprocess_id (or None if top-level)
        element_to_subprocess = {}

        # Initialize all elements as top-level
        for element in model.activities + model.events + model.gateways:
            element_to_subprocess[element["id"]] = None

        # Map subprocess internal elements to their parent subprocess
        subprocess_map = {}  # subprocess_id -> subprocess_dict
        for sp in model.activities:
            if sp["type"].endswith("Subprocess") and "elemRefs" in sp:
                subprocess_map[sp["id"]] = sp
                for elem_id in sp["elemRefs"]:
                    element_to_subprocess[elem_id] = sp["id"]

        # Separate flows: internal vs top-level
        remaining_flows = []
        for flow in model.sequence_flows:
            src = flow.get("sourceRef")
            tgt = flow.get("targetRef")

            if src and tgt:
                src_parent = element_to_subprocess.get(src)
                tgt_parent = element_to_subprocess.get(tgt)

                # If both are in the same subprocess, move to subprocessSequenceFlows
                if src_parent and src_parent == tgt_parent:
                    subprocess = subprocess_map[src_parent]
                    if "subprocessSequenceFlows" not in subprocess:
                        subprocess["subprocessSequenceFlows"] = []
                    subprocess["subprocessSequenceFlows"].append(flow)
                else:
                    remaining_flows.append(flow)
            else:
                remaining_flows.append(flow)

        model.sequence_flows[:] = remaining_flows

    @classmethod
    def _validate_no_cross_boundary_flows(cls, model: BPMNModel):
        """Raises an error if a flow crosses a subprocess boundary."""
        # Build map: element_id -> parent_subprocess_id (or None if top-level)
        element_to_subprocess = {}

        for element in model.activities + model.events + model.gateways:
            element_to_subprocess[element["id"]] = None

        for sp in model.activities:
            if sp["type"].endswith("Subprocess") and "elemRefs" in sp:
                for elem_id in sp["elemRefs"]:
                    element_to_subprocess[elem_id] = sp["id"]

        # Validate top-level sequence flows (internal ones should be moved already)
        for flow in model.sequence_flows:
            src = flow.get("sourceRef")
            tgt = flow.get("targetRef")

            if src and tgt:
                src_parent = element_to_subprocess.get(src)
                tgt_parent = element_to_subprocess.get(tgt)

                # One inside, one outside = boundary crossing (ERROR!)
                if (src_parent is None and tgt_parent is not None) or \
                   (src_parent is not None and tgt_parent is None):
                    raise ValueError(
                        f"Process structure error: Sequence flow {flow.get('id')} crosses subprocess boundary "
                        f"(from '{src}' in subprocess '{src_parent}' to '{tgt}' in subprocess '{tgt_parent}')."
                    )
                # Both inside but different subprocesses = also error
                elif src_parent and tgt_parent and src_parent != tgt_parent:
                    raise ValueError(
                        f"Process structure error: Sequence flow {flow.get('id')} crosses between subprocesses "
                        f"(from '{src}' in '{src_parent}' to '{tgt}' in '{tgt_parent}')."
                    )

    @classmethod
    def _finalize_model(cls, model: BPMNModel) -> None:
        cls._connect_flows(model)  # set sourceRef for sequence/message flows
        cls._reorganize_subprocess_flows(model)  # move internal flows to subprocessSequenceFlows
        cls._remove_outgoing_references(model)
        cls._link_elements_to_lanes(model)
        cls._remove_parent_lane_references(model)
        cls._validate_no_cross_boundary_flows(model)

    @classmethod
    def _remove_outgoing_references(cls, model: BPMNModel) -> None:
        for collection in [model.activities, model.events, model.gateways,
                           model.pools, model.sequence_flows, model.message_flows]:
            for item in collection:
                item.pop("outgoing", None)
        # Remove from subprocess internals as well!
        for act in model.activities:
            if "subprocessSequenceFlows" in act:
                for flow in act["subprocessSequenceFlows"]:
                    flow.pop("outgoing", None)

    @classmethod
    def _link_elements_to_lanes(cls, model: BPMNModel) -> None:
        for pool in model.pools:
            for lane in pool.get("lanes", []):
                element_refs = []
                for collection in [model.activities, model.events, model.gateways]:
                    for item in collection:
                        if lane.get("id") == item.get("parent_lane", ""):
                            element_refs.append(item.get("id"))
                lane["elemRefs"] = element_refs

    @classmethod
    def _remove_parent_lane_references(cls, model: BPMNModel) -> None:
        for collection in [model.activities, model.events, model.gateways]:
            for item in collection:
                item.pop("parent_lane", None)
        # for act in model.activities:
        #     if "parent_subprocess" in act:
        #         del act["parent_subprocess"]


"""
XML_conversion.py
=================
Converts BPMN 2.0 XML files to the same minimal JSON format that
BPMN_conversion.py (Signavio JSON → minimal JSON) produces.

Supported input
---------------
Standard BPMN 2.0 XML exported by any tool that follows the spec
(namespace http://www.omg.org/spec/BPMN/20100524/MODEL).

Output format
-------------
A BPMNModel instance (identical structure to what BPMNConverter.convert()
returns) whose .to_dict() / .to_json() methods produce:

{
  "activities":    [ {id, name, type, [parent_subprocess], [elemRefs],
                       [subprocessSequenceFlows]} ],
  "events":        [ {id, name, type, [parent_subprocess]} ],
  "gateways":      [ {id, name, type, [parent_subprocess]} ],
  "pools":         [ {id, name, lanes: [{id, name, elemRefs}]} ],
  "sequenceFlows": [ {id, sourceRef, targetRef, [condition]} ],
  "messageFlows":  [ {id, sourceRef, targetRef, [label]} ]
}

Usage
-----
    from XML_conversion import XMLBPMNConverter

    # from a file
    model = XMLBPMNConverter.convert_file("path/to/process.xml")
    print(model.to_json())

    # from a string / bytes
    with open("process.xml", "rb") as fh:
        model = XMLBPMNConverter.convert(fh.read())
"""

import sys
import xml.etree.ElementTree as ET
from typing import Optional

# == BPMN namespace ==============================================================

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _tag(local: str) -> str:
    """Return the Clark-notation tag for a BPMN 2.0 element, e.g. '{...}task'."""
    return f"{{{BPMN_NS}}}{local}"


def _local_name(element: ET.Element) -> str:
    """Strip the namespace URI and return just the local tag name."""
    tag = element.tag
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _get_name(element: ET.Element) -> str:
    """Return the *name* attribute of a BPMN element, normalising whitespace."""
    return element.get("name", "").replace("\n", " ").strip()


# == Type-mapping tables =========================================================

# XML local tag name → minimal activity type
ACTIVITY_TAG_MAP: Dict[str, str] = {
    "task":             "Task",
    "sendTask":         "Send",
    "receiveTask":      "Receive",
    "userTask":         "User",
    "manualTask":       "Manual",
    "serviceTask":      "Service",
    "businessRuleTask": "Business Rule",
    "scriptTask":       "Script",
    # subProcess is handled separately (Subprocess / EventSubprocess)
}

# Gateway XML local tag names that this converter recognises.
# The mapping from tag → canonical type is handled by canonicalize_gateway_type
# (shared with the JSON converter above) so both pipelines stay symmetric.
GATEWAY_TAGS = frozenset({
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
    "complexGateway",
})

# (event-container local tag, event-definition local tag | None) → minimal type
EVENT_TYPE_MAP: Dict[tuple, str] = {
    # ---- Start events ----
    ("startEvent", None):                           "StartNoneEvent",
    ("startEvent", "timerEventDefinition"):         "StartTimerEvent",
    ("startEvent", "messageEventDefinition"):       "StartMessageEvent",
    ("startEvent", "conditionalEventDefinition"):   "StartNoneEvent",
    ("startEvent", "signalEventDefinition"):        "StartNoneEvent",
    ("startEvent", "escalationEventDefinition"):    "StartNoneEvent",
    ("startEvent", "errorEventDefinition"):         "StartNoneEvent",
    # ---- End events ----
    ("endEvent", None):                             "EndNoneEvent",
    ("endEvent", "messageEventDefinition"):         "EndMessageEvent",
    ("endEvent", "escalationEventDefinition"):      "EndEscalationEvent",
    ("endEvent", "cancelEventDefinition"):          "EndCancelEvent",
    ("endEvent", "terminateEventDefinition"):       "EndNoneEvent",
    ("endEvent", "errorEventDefinition"):           "EndNoneEvent",
    ("endEvent", "signalEventDefinition"):          "EndNoneEvent",
    # ---- Intermediate catching ----
    ("intermediateCatchEvent", None):               "IntermediateMessageEventCatching",
    ("intermediateCatchEvent", "messageEventDefinition"):    "IntermediateMessageEventCatching",
    ("intermediateCatchEvent", "timerEventDefinition"):      "IntermediateTimerEvent",
    ("intermediateCatchEvent", "conditionalEventDefinition"):"IntermediateConditionalEvent",
    ("intermediateCatchEvent", "escalationEventDefinition"): "IntermediateEscalationEvent",
    ("intermediateCatchEvent", "errorEventDefinition"):      "IntermediateErrorEvent",
    ("intermediateCatchEvent", "cancelEventDefinition"):     "IntermediateCancelEvent",
    ("intermediateCatchEvent", "linkEventDefinition"):       "IntermediateLinkEventCatching",
    ("intermediateCatchEvent", "signalEventDefinition"):     "IntermediateMessageEventCatching",
    # ---- Intermediate throwing ----
    ("intermediateThrowEvent", None):               "IntermediateMessageEventThrowing",
    ("intermediateThrowEvent", "messageEventDefinition"):   "IntermediateMessageEventThrowing",
    ("intermediateThrowEvent", "escalationEventDefinition"):"IntermediateEscalationEvent",
    ("intermediateThrowEvent", "linkEventDefinition"):      "IntermediateLinkEventThrowing",
    ("intermediateThrowEvent", "signalEventDefinition"):    "IntermediateMessageEventThrowing",
    ("intermediateThrowEvent", "multipleEventDefinition"):  "IntermediateMultipleEventThrowing",
    # ---- Boundary events (treated as intermediate catching) ----
    ("boundaryEvent", None):                        "IntermediateMessageEventCatching",
    ("boundaryEvent", "timerEventDefinition"):      "IntermediateTimerEvent",
    ("boundaryEvent", "messageEventDefinition"):    "IntermediateMessageEventCatching",
    ("boundaryEvent", "errorEventDefinition"):      "IntermediateErrorEvent",
    ("boundaryEvent", "escalationEventDefinition"): "IntermediateEscalationEvent",
    ("boundaryEvent", "cancelEventDefinition"):     "IntermediateCancelEvent",
    ("boundaryEvent", "signalEventDefinition"):     "IntermediateMessageEventCatching",
}

ACTIVITY_TAGS = frozenset(ACTIVITY_TAG_MAP) | {"subProcess"}
EVENT_TAGS    = frozenset({
    "startEvent", "endEvent",
    "intermediateCatchEvent", "intermediateThrowEvent",
    "boundaryEvent",
})


def _get_event_type(element: ET.Element) -> str:
    """Determine the minimal event type string for a BPMN event element."""
    local = _local_name(element)
    event_def_tag: Optional[str] = None
    for child in element:
        child_local = _local_name(child)
        if child_local.endswith("EventDefinition"):
            event_def_tag = child_local
            break
    key = (local, event_def_tag)
    # Fall back to (local, None) if the specific definition is not mapped
    return EVENT_TYPE_MAP.get(key, EVENT_TYPE_MAP.get((local, None), "StartNoneEvent"))


# == Converter ===================================================================

class XMLBPMNConverter:
    """
    BPMN 2.0 XML → minimal BPMNModel converter.

    Mirrors the design of BPMNConverter (BPMN_conversion.py) but reads XML
    instead of Signavio JSON.  Key differences:

    * sourceRef / targetRef are explicit attributes on <sequenceFlow> in XML,
      so no reverse 'outgoing' look-up is needed.
    * Pools come from <collaboration>/<participant>; lanes from <laneSet>/<lane>.
    * Subprocesses are <subProcess> children of <process>.
    """

    @classmethod
    def convert(cls, xml_source: Union[str, bytes]) -> BPMNModel:
        """
        Convert BPMN 2.0 XML supplied as a *string* or *bytes* object.

        Returns a BPMNModel instance.
        """
        if isinstance(xml_source, str):
            xml_source = xml_source.encode("utf-8")
        root = ET.fromstring(xml_source)
        model = BPMNModel()
        cls._parse(root, model)
        cls._finalize(model)
        return model

    @classmethod
    def convert_file(cls, path: str) -> BPMNModel:
        """Load *path* (a BPMN 2.0 XML file) and return a BPMNModel."""
        tree = ET.parse(path)
        root = tree.getroot()
        model = BPMNModel()
        cls._parse(root, model)
        cls._finalize(model)
        return model

    # == Top-level parse =========================================================

    @classmethod
    def _parse(cls, root: ET.Element, model: BPMNModel) -> None:
        """Dispatch to collaboration-aware or plain-process parsing."""
        # Collect all <process> direct children of <definitions>
        process_map: Dict[str, ET.Element] = {
            proc.get("id", ""): proc
            for proc in root.findall(_tag("process"))
        }

        collaboration = root.find(_tag("collaboration"))
        if collaboration is not None:
            cls._parse_collaboration(collaboration, model, process_map)
            # Any process not referenced by a participant is parsed without a pool
            referenced: set = {
                p.get("processRef")
                for p in collaboration.findall(_tag("participant"))
                if p.get("processRef")
            }
            for pid, proc in process_map.items():
                if pid not in referenced:
                    cls._parse_process(proc, model, pool_entry=None)
        else:
            for proc in process_map.values():
                # If the process has a laneSet, create an implicit pool for it
                if proc.find(_tag("laneSet")) is not None:
                    pool_name = proc.get("name", "") or proc.get("id", "")
                    pool_entry: Dict[str, Any] = {
                        "id": proc.get("id", ""),
                        "name": pool_name,
                        "lanes": [],
                    }
                    model.pools.append(pool_entry)
                    cls._parse_process(proc, model, pool_entry=pool_entry)
                else:
                    cls._parse_process(proc, model, pool_entry=None)

    # == Collaboration ===========================================================

    @classmethod
    def _parse_collaboration(
        cls,
        collab: ET.Element,
        model: BPMNModel,
        process_map: Dict[str, ET.Element],
    ) -> None:
        """Parse <participant> elements into pools and <messageFlow> into message flows."""
        for participant in collab.findall(_tag("participant")):
            pool_id   = participant.get("id", "")
            pool_name = _get_name(participant)
            process_ref = participant.get("processRef")

            pool_entry: Dict[str, Any] = {
                "id": pool_id,
                "name": pool_name,
                "lanes": [],
            }
            model.pools.append(pool_entry)

            if process_ref and process_ref in process_map:
                cls._parse_process(
                    process_map[process_ref],
                    model,
                    pool_entry=pool_entry,
                )

        for mf in collab.findall(_tag("messageFlow")):
            flow: Dict[str, Any] = {
                "id":        mf.get("id", ""),
                "sourceRef": mf.get("sourceRef", ""),
                "targetRef": mf.get("targetRef", ""),
            }
            name = _get_name(mf)
            if name:
                flow["label"] = name
            model.message_flows.append(flow)

    # == Process =================================================================

    @classmethod
    def _parse_process(
        cls,
        proc: ET.Element,
        model: BPMNModel,
        pool_entry: Optional[Dict[str, Any]] = None,
        parent_subprocess: Optional[str] = None,
    ) -> None:
        """
        Parse a <process> element.

        Builds the element-to-lane map from <laneSet> children, then delegates
        to _parse_scope for the actual flow nodes.
        """
        element_to_lane: Dict[str, str] = {}

        for lane_set in proc.findall(_tag("laneSet")):
            for lane in lane_set.findall(_tag("lane")):
                lane_id   = lane.get("id", "")
                lane_name = _get_name(lane)
                lane_entry: Dict[str, Any] = {"id": lane_id, "name": lane_name}
                if pool_entry is not None:
                    pool_entry["lanes"].append(lane_entry)
                for ref in lane.findall(_tag("flowNodeRef")):
                    if ref.text:
                        element_to_lane[ref.text.strip()] = lane_id

        cls._parse_scope(
            proc,
            model,
            element_to_lane=element_to_lane,
            parent_subprocess=parent_subprocess,
            collect_to=None,  # top-level → go directly into model
        )

    # == Scope (process or subProcess body) =====================================

    @classmethod
    def _parse_scope(
        cls,
        container: ET.Element,
        model: BPMNModel,
        element_to_lane: Optional[Dict[str, str]] = None,
        parent_subprocess: Optional[str] = None,
        collect_to: Optional[Dict[str, List]] = None,
    ) -> None:
        """
        Iterate the direct children of *container* and classify each one.

        Parameters
        ----------
        container        : the <process> or <subProcess> element to parse
        model            : the BPMNModel being built (subprocess children are
                           always added to model.* so they appear at top level)
        element_to_lane  : maps element id → lane id (empty for subprocesses)
        parent_subprocess: name/id of the enclosing subprocess, if any
        collect_to       : if not None, a dict with keys
                           'activities', 'events', 'gateways', 'flows'
                           used to accumulate subprocess-internal elements
                           before folding them into model.*
        """
        acts  = collect_to["activities"] if collect_to is not None else model.activities
        evts  = collect_to["events"]     if collect_to is not None else model.events
        gways = collect_to["gateways"]   if collect_to is not None else model.gateways
        flows = collect_to["flows"]      if collect_to is not None else model.sequence_flows

        for child in container:
            local  = _local_name(child)
            eid    = child.get("id", "")
            p_lane = element_to_lane.get(eid) if element_to_lane else None

            # == Activities ======================================================
            if local in ACTIVITY_TAGS:
                elem: Dict[str, Any] = {
                    "id":   eid,
                    "name": _get_name(child),
                }
                if p_lane:
                    elem["parent_lane"] = p_lane
                if parent_subprocess:
                    elem["parent_subprocess"] = parent_subprocess

                if local == "subProcess":
                    triggered = child.get("triggeredByEvent", "false").lower() == "true"
                    elem["type"] = "EventSubprocess" if triggered else "Subprocess"

                    # Recursively parse the subprocess body
                    sub: Dict[str, List] = {
                        "activities": [], "events": [], "gateways": [], "flows": []
                    }
                    cls._parse_scope(
                        child,
                        model,
                        element_to_lane={},          # no lanes inside a subprocess
                        parent_subprocess=elem["name"] or eid,
                        collect_to=sub,
                    )
                    elem["elemRefs"] = [
                        e["id"] for e in sub["activities"] + sub["events"] + sub["gateways"]
                    ]
                    if sub["flows"]:
                        elem["subprocessSequenceFlows"] = sub["flows"]

                    # Fold subprocess elements into the main model
                    for a in sub["activities"]:
                        model.activities.append(a)
                    for e in sub["events"]:
                        model.events.append(e)
                    for g in sub["gateways"]:
                        model.gateways.append(g)
                    # sub["flows"] are stored in elem["subprocessSequenceFlows"]
                    # and do NOT go into model.sequence_flows
                else:
                    elem["type"] = ACTIVITY_TAG_MAP.get(local, "Task")

                acts.append(elem)

            # == Events ==========================================================
            elif local in EVENT_TAGS:
                elem = {
                    "id":   eid,
                    "name": _get_name(child),
                    "type": _get_event_type(child),
                }
                if p_lane:
                    elem["parent_lane"] = p_lane
                if parent_subprocess:
                    elem["parent_subprocess"] = parent_subprocess
                evts.append(elem)

            # == Gateways ========================================================
            elif local in GATEWAY_TAGS:
                elem = {
                    "id":   eid,
                    "name": _get_name(child),
                    "type": canonicalize_gateway_type(local),
                }
                if p_lane:
                    elem["parent_lane"] = p_lane
                if parent_subprocess:
                    elem["parent_subprocess"] = parent_subprocess
                gways.append(elem)

            # == Sequence flows ===================================================
            elif local == "sequenceFlow":
                flow: Dict[str, Any] = {
                    "id":        eid,
                    "sourceRef": child.get("sourceRef", ""),
                    "targetRef": child.get("targetRef", ""),
                }
                # Use 'name' attribute as the condition label (matches Signavio converter)
                name = _get_name(child)
                if name:
                    flow["condition"] = name
                else:
                    # Fall back to inline <conditionExpression> text
                    cond = child.find(_tag("conditionExpression"))
                    if cond is not None and cond.text:
                        flow["condition"] = cond.text.strip()
                flows.append(flow)

            # Everything else (laneSet, dataObject, association, ioSpec …) is skipped

    # == Finalization ========================================================

    @classmethod
    def _finalize(cls, model: BPMNModel) -> None:
        """
        Post-processing step (mirrors BPMNConverter._finalize):

        1. Compute lane elemRefs from the temporary parent_lane attribute.
        2. Remove parent_lane from all elements.
        """
        cls._link_elements_to_lanes(model)
        cls._remove_parent_lane_references(model)

    @classmethod
    def _link_elements_to_lanes(cls, model: BPMNModel) -> None:
        """Populate lane['elemRefs'] for every lane in every pool."""
        for pool in model.pools:
            for lane in pool.get("lanes", []):
                elem_refs: List[str] = []
                for collection in (model.activities, model.events, model.gateways):
                    for item in collection:
                        if item.get("parent_lane") == lane["id"]:
                            elem_refs.append(item["id"])
                lane["elemRefs"] = elem_refs

    @classmethod
    def _remove_parent_lane_references(cls, model: BPMNModel) -> None:
        """Strip the temporary parent_lane key from all flow-node dicts."""
        for collection in (model.activities, model.events, model.gateways):
            for item in collection:
                item.pop("parent_lane", None)


# == Command-line convenience ================================================

# def convert_file(path: str) -> BPMNModel:
#     """Module-level shortcut: load *path* and return a BPMNModel."""
#     return XMLBPMNConverter.convert_file(path)

# if __name__ == "__main__":
#     import sys

#     if len(sys.argv) < 2:
#         print("Module Usage: python XML_conversion.py <file.bpmn>, this then prints minimal model to stdout", file=sys.stderr)
#         sys.exit(1)

#     with open(sys.argv[1], "r", encoding="utf-8") as fh:
#         data = fh.read()

#     model = XMLBPMNConverter.convert(data)
#     print(model.to_json())



# if __name__ == "__main__":
#     import sys

#     if len(sys.argv) < 2:
#         print("Module Usage: python BPMN_conversion.py <file.json>, this then prints minimal model to stdout", file=sys.stderr)
#         sys.exit(1)

#     with open(sys.argv[1], "r", encoding="utf-8") as fh:
#         data = fh.read()

#     model = BPMNConverter.convert(data)
#     print(model.to_json())
