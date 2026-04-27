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

import json
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Union
from BPMN_conversion import BPMNModel

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

# XML local tag name → minimal gateway type
GATEWAY_TAG_MAP: Dict[str, str] = {
    "exclusiveGateway": "Exclusive",
    "parallelGateway":  "Parallel",
    "inclusiveGateway": "Inclusive",
    "eventBasedGateway": "Eventbased",
    "complexGateway":   "Complex",
}

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
GATEWAY_TAGS  = frozenset(GATEWAY_TAG_MAP)


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
                    "type": GATEWAY_TAG_MAP[local],
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

def convert_file(path: str) -> BPMNModel:
    """Module-level shortcut: load *path* and return a BPMNModel."""
    return XMLBPMNConverter.convert_file(path)

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Module Usage: python XML_conversion.py <file.xml>, this then prints minimal model to stdout", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        data = fh.read()

    model = XMLBPMNConverter.convert(data)
    print(model.to_json())




