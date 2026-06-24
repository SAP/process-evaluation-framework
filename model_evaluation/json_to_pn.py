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

def _build_subprocess_inline_maps(
    simplified_json: Dict[str, Any], model_id_prefix: str
) -> Tuple[Dict[str, str], Dict[str, str], Set[str], Set[str]]:
    """For each expanded subprocess, find its inner start/end events so the
    outer flow can be re-wired straight into the subprocess body.

    Returns ``(redirect_target, redirect_source, expanded_ids, silent_inner_boundaries)``:
      - ``redirect_target[subprocess_id]`` → id of the inner start event a
        flow ``X → subprocess`` should target instead (so the body is entered
        directly).
      - ``redirect_source[subprocess_id]`` → id of the inner end event a flow
        ``subprocess → Y`` should source from instead (so the body's exit
        flows directly to Y).
      - ``expanded_ids`` → the set of subprocess activity ids that should be
        skipped when wiring ``follows``: the outer flows now bypass them.
      - ``silent_inner_boundaries`` → ids of the inner start/end events for
        each inlined subprocess. Their labels are blanked out so they act as
        silent transitions in the resulting Petri net (a flat process and
        the same process wrapped in an unnamed subprocess then emit the
        same trace).

    A subprocess is "expanded" when its activity dict has a non-empty
    ``elemRefs`` list (matching the convention in :mod:`bpmn_sets`). If we
    can't unambiguously identify an inner start AND inner end inside the
    subprocess body, we fall back to leaving the subprocess opaque (no
    redirect entries), so the behavior is the same as before this change.
    """
    redirect_target: Dict[str, str] = {}
    redirect_source: Dict[str, str] = {}
    expanded_ids: Set[str] = set()
    silent_inner_boundaries: Set[str] = set()

    events_by_id = {e.get("id", ""): e for e in simplified_json.get("events", [])}

    for activity in simplified_json.get("activities", []):
        elem_refs = activity.get("elemRefs") or []
        if not elem_refs:
            continue
        sub_id = f"{model_id_prefix}{activity['id']}"

        # Inner sequence flow edges, restricted to refs that name actual
        # inner elements (defensive — the flow list is the source of truth).
        inner_flows = activity.get("subprocessSequenceFlows") or []
        sources = {f.get("sourceRef") for f in inner_flows if f.get("sourceRef")}
        targets = {f.get("targetRef") for f in inner_flows if f.get("targetRef")}
        if not sources or not targets:
            continue  # can't inline a body with no internal flow

        # Pick the inner start (event with no inner predecessor) and inner
        # end (event with no inner successor). Prefer explicit StartNoneEvent
        # / EndNoneEvent typing when available; otherwise fall back to the
        # topological roots.
        candidates = [r for r in elem_refs if r in sources or r in targets]
        starts = [
            r for r in candidates
            if r not in targets and events_by_id.get(r, {}).get("type", "").lower().startswith("start")
        ] or [r for r in candidates if r not in targets]
        ends = [
            r for r in candidates
            if r not in sources and events_by_id.get(r, {}).get("type", "").lower().startswith("end")
        ] or [r for r in candidates if r not in sources]

        if len(starts) != 1 or len(ends) != 1:
            # Ambiguous body shape (multiple entry/exit points); leave the
            # subprocess opaque rather than guess which inner element to
            # bind the outer flow to.
            continue

        redirect_target[sub_id] = f"{model_id_prefix}{starts[0]}"
        redirect_source[sub_id] = f"{model_id_prefix}{ends[0]}"
        expanded_ids.add(sub_id)
        silent_inner_boundaries.add(f"{model_id_prefix}{starts[0]}")
        silent_inner_boundaries.add(f"{model_id_prefix}{ends[0]}")

    return redirect_target, redirect_source, expanded_ids, silent_inner_boundaries


def parse_simplified_bpmn_json(
    simplified_json: Dict[str, Any],
    model_id_prefix: str = ""
) -> Tuple[Dict[str, List[str]], Dict[str, str], Dict[str, str]]:
    """
    Parses the simplified BPMN JSON structure into maps compatible with the original logic.

    Expanded subprocesses (activities with ``elemRefs`` and an
    unambiguous inner start/end) are inlined: outer sequence flows that
    point at the subprocess transition are redirected to its inner start,
    and flows leaving the subprocess are sourced from its inner end. The
    subprocess activity itself is dropped from ``follows`` so the resulting
    Petri net traverses the body directly instead of treating the
    subprocess as a single opaque event. Subprocesses whose body shape
    can't be unambiguously inlined fall back to the previous opaque
    behavior.
    """
    follows: Dict[str, List[str]] = {}
    bpmn_id_to_stencil: Dict[str, str] = {}
    bpmn_id_to_label: Dict[str, str] = {}

    redirect_target, redirect_source, expanded_ids, silent_inner_boundaries = (
        _build_subprocess_inline_maps(simplified_json, model_id_prefix)
    )

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

            # Label fallback logic: use type if name is missing. Inner
            # start/end events of inlined subprocesses are silenced — their
            # label stays empty so the Petri-net layer treats them as
            # invisible transitions and a flat process matches the same
            # process wrapped in an (unnamed) subprocess.
            if eid in silent_inner_boundaries:
                bpmn_id_to_label[eid] = ""
            elif not ename.strip():
                bpmn_id_to_label[eid] = etype
            else:
                bpmn_id_to_label[eid] = ename

            # Initialize the follows entry for this node, unless this is an
            # expanded subprocess we're inlining (its incoming/outgoing flows
            # are re-pointed at the body instead).
            if eid not in follows and eid not in expanded_ids:
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
        raw_source = f"{model_id_prefix}{flow['sourceRef']}"
        raw_target = f"{model_id_prefix}{flow['targetRef']}"
        # If either endpoint is an inlined subprocess transition, hop over it
        # to the body's inner end/start respectively.
        source_id = redirect_source.get(raw_source, raw_source)
        target_id = redirect_target.get(raw_target, raw_target)

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