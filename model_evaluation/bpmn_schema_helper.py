### some helper function to get data from the bpmn_schema or transform it into different formats


import json
from typing import Any, Dict, List, Union

from sapsam_mapping import sapsam_mapping

# Type definitions for better type hinting
BPMNShape = Dict[str, Any]
FlattenedBPMN = Dict[str, List[Dict[str, Any]]]

class BPMNModel:
    """Data class representing a flattened BPMN model."""

    def __init__(self):
        self.tasks: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.gateways: List[Dict[str, Any]] = []
        self.pools: List[Dict[str, Any]] = []
        self.message_flows: List[Dict[str, Any]] = []
        self.sequence_flows: List[Dict[str, Any]] = []

    def to_dict(self) -> FlattenedBPMN:
        """Convert the model to a dictionary."""
        return {
            "tasks": self.tasks,
            "events": self.events,
            "gateways": self.gateways,
            "pools": self.pools,
            "messageFlows": self.message_flows,
            "sequenceFlows": self.sequence_flows
        }

    def to_json(self) -> str:
        """Convert the model to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class BPMNConverter:
    """Converter for transforming Signavio BPMN diagrams into a minimal JSON format."""

    @classmethod
    def convert(cls, json_data: Union[str, BPMNShape]) -> BPMNModel:
        """Convert Signavio BPMN JSON to a minimal format."""
        if isinstance(json_data, str):
            json_data = json.loads(json_data)

        model = BPMNModel()
        cls._process_element(json_data, model)
        cls._finalize_model(model)

        return model

    @classmethod
    def _create_base_element(cls, shape: BPMNShape, parent_lane: str = "") -> Dict[str, Any]:
        """Create the base element dictionary that all element types share."""
        element = {
            "id": shape["resourceId"],
            "name": shape["properties"].get("name", "").replace("\n", " ").strip(),
            "outgoing": shape.get("outgoing", []),
        }

        if parent_lane:
            element["parent_lane"] = parent_lane

        return element

    @classmethod
    def _process_element(cls, shape: BPMNShape, model: BPMNModel, parent_lane: str = "") -> None:
        """Process a single BPMN element and update the model."""
        try:
            element_type = sapsam_mapping[shape["stencil"]["id"]]
            if element_type == "Diagram":
                cls._process_diagram(shape, model)
                return

            base_element = cls._create_base_element(shape, parent_lane)


            if element_type == "Events":
                cls._process_event(shape, base_element, model)
            elif element_type == "Activities":
                cls._process_activity(shape, base_element, model)
            elif element_type == "Gateways":
                cls._process_gateway(shape, base_element, model)
            elif element_type == "Sequence Flows":
                cls._process_sequence_flow(shape, base_element, model)
            elif element_type == "Message Flows":
                cls._process_message_flow(shape, base_element, model)
            elif element_type == "Pools":
                cls._process_pool(shape, base_element, model)
            elif element_type == "Diagram":
                cls._process_diagram(shape, model)

        except Exception as e:
            print(f"Error processing element {shape['stencil']['id']}: {e}")

    @classmethod
    def _process_event(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process an event element."""
        assert len(shape.get("childShapes", [])) == 0, "Events don't have child shapes"
        element["type"] = shape["stencil"]["id"]
        model.events.append(element)

    @classmethod
    def _process_activity(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process an activity element."""
        assert len(shape.get("childShapes", [])) == 0, "Activities don't have child shapes"
        task_type = shape["properties"].get("tasktype", None)
        if task_type == "None":
            task_type = None
        element["type"] = task_type if task_type else shape["stencil"]["id"]
        model.tasks.append(element)

    @classmethod
    def _process_gateway(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process a gateway element."""
        assert len(shape.get("childShapes", [])) == 0, "Gateways don't have child shapes"
        gateway_type = shape["stencil"]["id"]
        if gateway_type == "InclusiveGateway":
            gateway_type = "Inclusive"
        elif gateway_type == "Exclusive_Databased_Gateway":
            gateway_type = "Exclusive"
        elif gateway_type == "ParallelGateway":
            gateway_type = "Parallel"
        elif gateway_type == "EventbasedGateway":
            gateway_type = "Eventbased"
        elif gateway_type == "ComplexGateway":
            gateway_type = "Complex"

        element["type"] = gateway_type
        if not element["name"]:
            del element["name"]
        model.gateways.append(element)

    @classmethod
    def _process_sequence_flow(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process a sequence flow element."""
        assert len(shape.get("childShapes", [])) == 0, "Sequence Flows don't have child shapes"
        element["targetRef"] = shape.get("target").get("resourceId")
        name = element.pop("name")
        if name:
            element["condition"] = name
        model.sequence_flows.append(element)

    @classmethod
    def _process_message_flow(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process a message flow element."""
        assert len(shape.get("childShapes", [])) == 0, "Message Flows don't have child shapes"
        element["targetRef"] = shape.get("target").get("resourceId")
        name = element.pop("name")
        if name:
            element["label"] = name
        model.message_flows.append(element)

    @classmethod
    def _process_pool(cls, shape: BPMNShape, element: Dict[str, Any], model: BPMNModel) -> None:
        """Process a pool element."""
        element["lanes"] = []
        for lane in shape.get("childShapes", []):
            assert sapsam_mapping[lane["stencil"]["id"]] == "Lanes", "Pools should only have lanes as children"
            assert len(lane.get("outgoing", [])) == 0, "Lanes should not have any outgoing elements"

            lane_info = {
                "id": lane["resourceId"],
                "name": lane["properties"].get("name", "").strip(),
            }
            element["lanes"].append(lane_info)

            for child in lane.get("childShapes", []):
                cls._process_element(child, model, lane["resourceId"])

        model.pools.append(element)

    @classmethod
    def _process_diagram(cls, shape: BPMNShape, model: BPMNModel) -> None:
        """Process a diagram element."""
        for child_shape in shape.get("childShapes", []):
            cls._process_element(child_shape, model)

    @classmethod
    def _finalize_model(cls, model: BPMNModel) -> None:
        """Finalize the model by resolving references and cleaning up."""
        cls._connect_flows(model)
        cls._remove_outgoing_references(model)
        cls._link_elements_to_lanes(model)
        cls._remove_parent_lane_references(model)

    @classmethod
    def _connect_flows(cls, model: BPMNModel) -> None:
        """Connect sequence flows and message flows to their source elements."""
        all_flows = model.sequence_flows + model.message_flows
        all_elements = model.tasks + model.events + model.gateways + model.pools

        for flow in all_flows:
            for element in all_elements:
                for outgoing in element.get("outgoing", []):
                    if flow.get("id") == outgoing.get("resourceId"):
                        flow["sourceRef"] = element.get("id")

    @classmethod
    def _remove_outgoing_references(cls, model: BPMNModel) -> None:
        """Remove outgoing references from all elements."""
        for collection in [model.tasks, model.events, model.gateways,
                          model.pools, model.sequence_flows, model.message_flows]:
            for item in collection:
                item.pop("outgoing", None)

    @classmethod
    def _link_elements_to_lanes(cls, model: BPMNModel) -> None:
        """Link elements to their parent lanes."""
        for pool in model.pools:
            for lane in pool.get("lanes", []):
                element_refs = []
                for collection in [model.tasks, model.events, model.gateways]:
                    for item in collection:
                        if lane.get("id") == item.get("parent_lane", ""):
                            element_refs.append(item.get("id"))

                lane["elemRefs"] = element_refs

    @classmethod
    def _remove_parent_lane_references(cls, model: BPMNModel) -> None:
        """Remove parent lane references from all elements."""
        for collection in [model.tasks, model.events, model.gateways]:
            for item in collection:
                if item.get("parent_lane", ""):
                    del item["parent_lane"]


def get_element_by_id_from_sublist(bpmn_sublist, id):
    """Returns the element with the passed id. Takes a bpmn sublist like tasks, events, ect. as an argument."""
    for item in bpmn_sublist:
        if item.get("id", "") == id:
            return item
    return ""


def get_flows_with_values(bpmn_instance):
    """Returns sequence and message flows. Replaces the ids with the names (for tasks, events and pools) or types (for gateways) of the references"""

    def get_ref_value(ref_id):
        task_or_event_or_pool = get_element_by_id_from_sublist(
            bpmn_instance["tasks"] + bpmn_instance["events"] + bpmn_instance["pools"], ref_id
        )
        if task_or_event_or_pool:
            return task_or_event_or_pool.get("name", "")
        else:
            gateway = get_element_by_id_from_sublist(bpmn_instance["gateways"], ref_id)
            if gateway:
                return gateway.get("type", "")
            else:
                return ""

    sequence_flows_with_values = []
    for sequence_flow in bpmn_instance["sequenceFlows"]:
        sourceValue = get_ref_value(sequence_flow["sourceRef"])
        targetValue = get_ref_value(sequence_flow["targetRef"])
        sequence_flows_with_values.append(
            [sourceValue, sequence_flow.get("condition", ""), targetValue]
        )

    message_flows_with_values = []
    for sequence_flow in bpmn_instance["messageFlows"]:
        sourceValue = get_ref_value(sequence_flow["sourceRef"])
        targetValue = get_ref_value(sequence_flow["targetRef"])
        message_flows_with_values.append(
            [sourceValue, sequence_flow.get("message", ""), targetValue]
        )

    return sequence_flows_with_values, message_flows_with_values


def get_name_by_id(bpmn_instance, id):
    """Returns the name of the element with the passed id"""
    for list in bpmn_instance.values():
        for item in list:
            if item.get("id", "") == id:
                return item.get("name", "")
    return ""


def get_lanes(bpmn_instance):
    """Returns two lists: lanes_name and lanes_with_refs.
    lanes_name is a list of names from the lanes, where the pool and lane name are concatinated.
    lanes_with_refs has the references concatinated as well. Thereby the reference ids are replaced with the names (for tasks, events and pools)
    or types (for gateways) of the references.
    """

    # helper function
    def get_ref_value_from_task_or_event_or_gateway(bpmn_instance, ref_id):
        task_or_event = get_element_by_id_from_sublist(
            bpmn_instance["tasks"] + bpmn_instance["events"], ref_id
        )
        if task_or_event:
            return task_or_event.get("name", "")
        else:
            gateway = get_element_by_id_from_sublist(bpmn_instance["gateways"], ref_id)
            if gateway:
                return gateway.get("type", "")
            else:
                return ""

    lanes_name = []
    lanes_with_refs = []
    for pool in bpmn_instance["pools"]:
        lanes = pool["lanes"]
        if not lanes:
            lanes_name.append(pool["name"])
        for lane in lanes:
            lane_and_pool_name = pool.get("name", "") + " - " + lane.get("name", "")
            lanes_name.append(lane_and_pool_name)
            for ref in lane.get("elemRefs", []):
                ref_value = get_ref_value_from_task_or_event_or_gateway(bpmn_instance, ref)
                lanes_with_refs.append(f"{lane_and_pool_name} - {ref_value}")

    return lanes_name, lanes_with_refs


def get_tasks_events_gateways_only(bpmn_instance):
    """Returns the task, event and gateway lists of the bpmn_instance"""
    return {
        "tasks": bpmn_instance["tasks"],
        "events": bpmn_instance["events"],
        "gateways": bpmn_instance["gateways"],
    }


def get_tasks_events_gateways_pools_only(bpmn_instance):
    """Returns the task, event and gateway and pool lists of the bpmn_instance"""
    return {
        "tasks": bpmn_instance["tasks"],
        "events": bpmn_instance["events"],
        "gateways": bpmn_instance["gateways"],
        "pools": bpmn_instance["pools"],
    }


def get_seq_and_mes_flow_only(bpmn_instance):
    """Returns the seuqnec and message flow lists of the bpmn_instance"""
    return {
        "sequenceFlows": bpmn_instance["sequenceFlows"],
        "messageFlows": bpmn_instance["messageFlows"],
    }
