import json
from typing import Any, Dict, List, Union

from bpmn_schema import derive_parent_subprocess
from sapsam_mapping import sapsam_mapping

BPMNShape = Dict[str, Any]
FlattenedBPMN = Dict[str, List[Dict[str, Any]]]

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
        "CollapsedSubprocess": "CollapsedSubprocess",
        "EventSubprocess": "EventSubprocess",
        "CollapsedEventSubprocess": "CollapsedEventSubprocess",
        # Add more if needed
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
                    "Subprocess", "CollapsedSubprocess", "EventSubprocess", "CollapsedEventSubprocess"]:
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
                        parent_subprocess=elem["name"] or elem["id"]
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
                gateway_map = {
                    "InclusiveGateway": "Inclusive",
                    "Exclusive_Databased_Gateway": "Exclusive",
                    "ParallelGateway": "Parallel",
                    "EventbasedGateway": "Eventbased",
                    "ComplexGateway": "Complex"
                }
                elem["type"] = gateway_map.get(shape["stencil"]["id"], shape["stencil"]["id"])
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
        derive_parent_subprocess(model.to_dict())  # in-place: stamp back-refs from elemRefs
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



if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Module Usage: python BPMN_conversion.py <file.json>, this then prints minimal model to stdout", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        data = fh.read()

    model = BPMNConverter.convert(data)
    print(model.to_json())


