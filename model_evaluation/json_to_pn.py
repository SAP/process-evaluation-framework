from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple



IRRELEVANT_BPMN_SHAPES = (
    "SequenceFlow", "MessageFlow", "DataObject", "Pool", "Lane",
    "TextAnnotation", "Association_Undirected", "Association_Bidirectional",
    "Association_Unidirectional", "Group", "CollapsedPool", "ITSystem", "DataStore"
)

class BpmnElementType(Enum):
    EVENT = "Event"
    TASK = "Task"
    GATEWAY = "Gateway"
    OTHER = "Other"
    IRRELEVANT = "Irrelevant"


def get_bpmn_element_stereotype(bpmn_id: str, bpmn_id_to_stencil: Dict[str, str]) -> str:
    return bpmn_id_to_stencil.get(bpmn_id, "")

GATEWAY_STENCIL_NAMES = {"exclusive", "inclusive", "parallel", "complex", "eventbased"}

def get_bpmn_element_type(bpmn_id: str, bpmn_id_to_stencil: Dict[str, str]) -> BpmnElementType:
    stencil = bpmn_id_to_stencil.get(bpmn_id, "").lower()

    if any(event_keyword in stencil for event_keyword in ["event", "startevent", "endevent"]):
        return BpmnElementType.EVENT
    if "gateway" in stencil or stencil in GATEWAY_STENCIL_NAMES:
        return BpmnElementType.GATEWAY
    if any(task_keyword in stencil for task_keyword in ["task", "subprocess", "callactivity", "transaction"]):
         return BpmnElementType.TASK
    if any(irrelevant_keyword.lower() in stencil for irrelevant_keyword in IRRELEVANT_BPMN_SHAPES):
        return BpmnElementType.IRRELEVANT
    
    if stencil:
        return BpmnElementType.TASK 
    return BpmnElementType.IRRELEVANT

def is_bpmn_element_relevant_for_pn(bpmn_id: str, bpmn_id_to_stencil: Dict[str, str]) -> bool:
    return get_bpmn_element_type(bpmn_id, bpmn_id_to_stencil) != BpmnElementType.IRRELEVANT

def is_bpmn_choice_gateway(bpmn_id: str, bpmn_id_to_stencil: Dict[str, str]) -> bool:
    stencil = bpmn_id_to_stencil.get(bpmn_id, "").lower()
    return "exclusive" in stencil or "inclusive" in stencil or "eventbased" in stencil

def get_direct_postset_bpmn_ids(
    source_bpmn_id: str,
    follows: Dict[str, List[str]],
    bpmn_id_to_stencil: Dict[str, str]
) -> Set[str]:
    post_elements = set()
    if source_bpmn_id not in follows:
        return post_elements

    for successor_id in follows[source_bpmn_id]:
        successor_stencil = bpmn_id_to_stencil.get(successor_id, "")
        if successor_stencil.startswith("SequenceFlow") or successor_stencil.startswith("MessageFlow"):
            if successor_id in follows:
                for actual_element_id in follows[successor_id]:
                    if is_bpmn_element_relevant_for_pn(actual_element_id, bpmn_id_to_stencil):
                        post_elements.add(actual_element_id)
        elif is_bpmn_element_relevant_for_pn(successor_id, bpmn_id_to_stencil):
            post_elements.add(successor_id)
    return post_elements

def get_direct_preset_bpmn_ids(
    target_bpmn_id: str,
    follows: Dict[str, List[str]],
    bpmn_id_to_stencil: Dict[str, str],
    all_bpmn_ids: Optional[Set[str]] = None
) -> Set[str]:
    pre_elements = set()
    relevant_ids_to_scan = all_bpmn_ids if all_bpmn_ids else follows.keys()

    for source_bpmn_id in relevant_ids_to_scan:
        if source_bpmn_id == target_bpmn_id:
            continue

        direct_successors = follows.get(source_bpmn_id, [])
        if target_bpmn_id in direct_successors:
            if is_bpmn_element_relevant_for_pn(source_bpmn_id, bpmn_id_to_stencil):
                pre_elements.add(source_bpmn_id)
        else:
            for intermediate_flow_id in direct_successors:
                flow_stencil = bpmn_id_to_stencil.get(intermediate_flow_id, "")
                is_intermediate_a_flow = flow_stencil.startswith("SequenceFlow") or flow_stencil.startswith("MessageFlow")
                
                if is_intermediate_a_flow:
                    flow_successors = follows.get(intermediate_flow_id, [])
                    if target_bpmn_id in flow_successors:
                        if is_bpmn_element_relevant_for_pn(source_bpmn_id, bpmn_id_to_stencil):
                            pre_elements.add(source_bpmn_id)
                            break
    return pre_elements

def parse_simplified_bpmn_json(
    simplified_json: Dict[str, Any],  
    model_id_prefix: str = ""
) -> Tuple[Dict[str, List[str]], Dict[str, str], Dict[str, str]]:
    """
    Parses the simplified BPMN JSON structure into maps compatible with the original logic.
    """
    follows: Dict[str, List[str]] = {}
    bpmn_id_to_stencil: Dict[str, str] = {}
    bpmn_id_to_label: Dict[str, str] = {}

    # 1. Process Nodes (Activities, Events, Gateways)
    # These are all categorized similarly in the output maps
    node_categories = ['activities', 'events', 'gateways', 'pools']
    
    for category in node_categories:
        for element in simplified_json.get(category, []):
            # Apply prefix for consistency
            eid = f"{model_id_prefix}{element['id']}"
            etype = element.get('type', category.rstrip('s').capitalize()) # Fallback to category name
            ename = element.get('name', "")

            bpmn_id_to_stencil[eid] = etype
            
            # Label fallback logic: use type if name is missing
            if not ename.strip():
                bpmn_id_to_label[eid] = etype
            else:
                bpmn_id_to_label[eid] = ename
            
            # Initialize the follows entry for this node
            if eid not in follows:
                follows[eid] = []

    # 2. Process Flows (SequenceFlows, MessageFlows)
    # To match your original parser, we create the chain: Source -> Flow -> Target
    flow_categories = {
        'sequenceFlows': 'SequenceFlow',
        'messageFlows': 'MessageFlow'
    }

    # Collect every flow we want to wire into ``follows``.
    flow_sources: List[Tuple[str, Any]] = []
    for key, stencil_name in flow_categories.items():
        for flow in simplified_json.get(key, []):
            flow_sources.append((stencil_name, flow))
    for activity in simplified_json.get('activities', []):
        for flow in activity.get('subprocessSequenceFlows', []) or []:
            flow_sources.append(('SequenceFlow', flow))

    for stencil_name, flow in flow_sources:
        fid = f"{model_id_prefix}{flow['id']}"
        source_id = f"{model_id_prefix}{flow['sourceRef']}"
        target_id = f"{model_id_prefix}{flow['targetRef']}"

        # Register the flow itself in the stencil/label maps
        bpmn_id_to_stencil[fid] = stencil_name
        bpmn_id_to_label[fid] = flow.get('name', "") # Flows usually have empty names

        # Map: Source -> Flow
        if source_id not in follows:
            follows[source_id] = []
        follows[source_id].append(fid)

        # Map: Flow -> Target
        follows[fid] = [target_id]

    return follows, bpmn_id_to_stencil, bpmn_id_to_label