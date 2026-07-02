import collections
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .json_to_pn import parse_simplified_bpmn_json, get_bpmn_element_type, is_bpmn_element_relevant_for_pn, is_bpmn_choice_gateway, get_direct_preset_bpmn_ids, get_direct_postset_bpmn_ids, BpmnElementType


class SoundnessStatus(str, Enum):
    """Outcome of trace extraction relative to workflow-net soundness.

    A net is ``SOUND`` only when every explored execution reached the final
    marking exactly. The other statuses describe the kind of degradation.
    """

    SOUND = "sound"
    UNSOUND_RECOVERED = "unsound_recovered"
    UNSOUND_NO_VARIANTS = "unsound_no_variants"
    STRUCTURALLY_BROKEN = "structurally_broken"
    EXPLORATION_TRUNCATED = "exploration_truncated"


# Structural-finding issue codes considered severe enough to flip the overall
# status to STRUCTURALLY_BROKEN when no sound variants were produced.
SEVERE_STRUCTURAL_ISSUES: frozenset[str] = frozenset({
    "no_source_place",
    "no_sink_place",
})


@dataclass(frozen=True)
class StructuralFinding:
    issue: str
    detail: str
    node_id: Optional[str] = None


@dataclass(frozen=True)
class DeadlockSignature:
    """Deduplicated representation of a dead non-final marking.

    ``tokens`` is sorted so two deadlocks with the same place→count map hash
    equal regardless of the order they were discovered in.
    """

    tokens: Tuple[Tuple[str, int], ...]
    example_partial_trace: Tuple[str, ...]


@dataclass
class ExplorationDiagnostics:
    status: SoundnessStatus = SoundnessStatus.SOUND
    summary: str = ""
    structural_findings: List[StructuralFinding] = field(default_factory=list)
    deadlock_markings: List[DeadlockSignature] = field(default_factory=list)
    loop_cap_hits: Dict[str, int] = field(default_factory=dict)
    truncated_by_active_cap: bool = False
    truncated_by_timeout: bool = False
    sound_variant_count: int = 0
    partial_trace_count: int = 0
    exploration_elapsed_seconds: float = 0.0



class Place(BaseModel):
    name: str
    in_arcs: Set["Arc"] = Field(default_factory=set, repr=False, exclude=True)
    out_arcs: Set["Arc"] = Field(default_factory=set, repr=False, exclude=True)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    def __repr__(self) -> str: return f"P({self.name})"
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Place): return self.name == other.name
        return False
    def __hash__(self) -> int: return hash(self.name)

class Transition(BaseModel):
    name: str
    label_for_trace: Optional[str] = Field(default=None)
    in_arcs: Set["Arc"] = Field(default_factory=set, repr=False, exclude=True)
    out_arcs: Set["Arc"] = Field(default_factory=set, repr=False, exclude=True)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    def __repr__(self) -> str: return f"T({self.name}, Label: '{self.label_for_trace}')"
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Transition): return self.name == other.name
        return False
    def __hash__(self) -> int: return hash(self.name)

class Arc(BaseModel):
    source: Union[Place, Transition]
    target: Union[Place, Transition]
    weight: int = Field(default=1, gt=0)
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    @model_validator(mode='after')
    def check_arc_source_target_types(self) -> 'Arc':
        if isinstance(self.source, Place) and isinstance(self.target, Place):
            raise ValueError("Arc source and target cannot both be Places.")
        if isinstance(self.source, Transition) and isinstance(self.target, Transition):
            raise ValueError("Arc source and target cannot both be Transitions.")
        if not (isinstance(self.source, (Place, Transition)) and
                isinstance(self.target, (Place, Transition))):
            raise TypeError("Arc source and target must be Place or Transition instances.")
        return self
    def __repr__(self) -> str:
        source_name = self.source.name
        target_name = self.target.name
        return f"Arc({source_name}-({self.weight})->{target_name})"

class Marking(collections.Counter[Place]):
    def __hash__(self) -> int: return hash(frozenset(self.items()))
    def __repr__(self) -> str:
        if not self: 
            return "Marking({})"
        return (f"Marking({','.join(f'{p.name}:{c}' for p, c in sorted(self.items(), key=lambda item: item[0].name))})")

class PetriNet(BaseModel):
    name: str
    places: Set[Place] = Field(default_factory=set)
    transitions: Set[Transition] = Field(default_factory=set)
    arcs: Set[Arc] = Field(default_factory=set)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    initial_marking: Marking = Field(default_factory=Marking)
    final_marking: Marking = Field(default_factory=Marking)

    bpmn_id_to_stencil: Dict[str, str] = {}
    bpmn_id_to_label: Dict[str, str] = {}
    bpmn_elements_map: Dict[str, Union[Place, Transition]] = {}
    gateway_shared_input_places: Dict[str, Place] = {}
    gateway_shared_output_places: Dict[str, Place] = {}
    all_bpmn_ids_in_model: Set[str] = set()
    internal_id_counter: int = 0


    def __repr__(self) -> str:
        node_names: List[str] = sorted(p.name for p in self.places) + \
                                sorted(t.name for t in self.transitions)
        return (f"PetriNet(name='{self.name}', P={len(self.places)}, "
                f"T={len(self.transitions)}, A={len(self.arcs)}, "
                f"Nodes={{{', '.join(node_names)}}})")
    
    def add_arc_from_to(self, source: Union[Place, Transition], 
                    target: Union[Place, Transition], weight: int = 1) -> Arc:
        # check if source and target are of the same type and if so handle this by adding a place between them
        # in case of type = Transition and a transition between them if type = Place
        if type(source) is type(target):
            if isinstance(source, Place):
                # add a transition between source and target
                new_transition = Transition(name=f"{source.name}_{target.name}_T")
                self.transitions.add(new_transition)
                self.places.add(source)
                self.places.add(target)
                self.add_arc_from_to(source, new_transition, weight)
                self.add_arc_from_to(new_transition, target, weight)
            elif isinstance(source, Transition):
                # add a place between source and target
                new_place = Place(name=f"{source.name}_{target.name}_P")
                self.places.add(new_place)
                self.transitions.add(source)
                self.transitions.add(target)
                self.add_arc_from_to(source, new_place, weight)
                self.add_arc_from_to(new_place, target, weight)
            return
        arc = Arc(source=source, target=target, weight=weight)
        existing_arc = next((existing for existing in self.arcs if existing == arc), None)
        if existing_arc:
            return existing_arc

        self.arcs.add(arc)
        source.out_arcs.add(arc)
        target.in_arcs.add(arc)
        return arc

    def structural_check(self) -> List[StructuralFinding]:
        """Run lightweight structural checks for workflow-net soundness.

        These checks are O(|V|+|E|) and deliberately conservative: they catch
        common BPMN modeling errors (missing source/sink, isolated nodes, dead
        transitions, unreachable subgraphs) but make no claims about full
        WF-net soundness, which requires a coverability-graph analysis.

        Findings are advisory: the caller may still attempt exploration even
        when severe issues are reported.
        """
        findings: List[StructuralFinding] = []

        sources = {p for p in self.places if not p.in_arcs}
        sinks = {p for p in self.places if not p.out_arcs}

        if not sources:
            findings.append(StructuralFinding(
                issue="no_source_place",
                detail="No place without incoming arcs was found; the net has no entry point.",
            ))
        elif len(sources) > 1:
            for src in sources:
                findings.append(StructuralFinding(
                    issue="multiple_source_places",
                    detail=f"Place '{src.name}' is one of {len(sources)} source places; a workflow net should have exactly one.",
                    node_id=src.name,
                ))

        if not sinks:
            findings.append(StructuralFinding(
                issue="no_sink_place",
                detail="No place without outgoing arcs was found; the net has no exit point.",
            ))
        elif len(sinks) > 1:
            for snk in sinks:
                findings.append(StructuralFinding(
                    issue="multiple_sink_places",
                    detail=f"Place '{snk.name}' is one of {len(sinks)} sink places; a workflow net should have exactly one.",
                    node_id=snk.name,
                ))

        # Forward reachability from sources.
        reachable_forward: Set[Union[Place, Transition]] = set()
        if sources:
            stack: List[Union[Place, Transition]] = list(sources)
            while stack:
                node = stack.pop()
                if node in reachable_forward:
                    continue
                reachable_forward.add(node)
                for arc in node.out_arcs:
                    if arc.target not in reachable_forward:
                        stack.append(arc.target)

            for node in self.places | self.transitions:
                if node not in reachable_forward:
                    findings.append(StructuralFinding(
                        issue="unreachable_from_source",
                        detail=f"Node '{node.name}' is not reachable from any source place.",
                        node_id=node.name,
                    ))

        # Backward reachability from sinks (can the sink be reached?).
        reachable_backward: Set[Union[Place, Transition]] = set()
        if sinks:
            stack = list(sinks)
            while stack:
                node = stack.pop()
                if node in reachable_backward:
                    continue
                reachable_backward.add(node)
                for arc in node.in_arcs:
                    if arc.source not in reachable_backward:
                        stack.append(arc.source)

            for node in self.places | self.transitions:
                if node not in reachable_backward:
                    findings.append(StructuralFinding(
                        issue="cannot_reach_sink",
                        detail=f"Node '{node.name}' cannot reach any sink place.",
                        node_id=node.name,
                    ))

        for node in self.places | self.transitions:
            if not node.in_arcs and not node.out_arcs:
                findings.append(StructuralFinding(
                    issue="isolated_node",
                    detail=f"Node '{node.name}' has neither incoming nor outgoing arcs.",
                    node_id=node.name,
                ))

        for t in self.transitions:
            if not t.in_arcs:
                findings.append(StructuralFinding(
                    issue="dead_transition_no_preset",
                    detail=f"Transition '{t.name}' has no input places and can never fire.",
                    node_id=t.name,
                ))
            elif not t.out_arcs:
                findings.append(StructuralFinding(
                    issue="dead_transition_no_postset",
                    detail=f"Transition '{t.name}' has no output places.",
                    node_id=t.name,
                ))

        return findings

    def is_enabled(self, transition: Transition, marking: Marking) -> bool:
        if transition not in self.transitions:
            return False
        for arc in transition.in_arcs:
            place = arc.source 
            if marking[place] < arc.weight:
                return False
        return True
    

    def execute(self, transition: Transition, marking: Marking) -> Optional[Marking]:
        if not self.is_enabled(transition, marking):
            return None

        new_marking = Marking(marking.copy())
        for arc in transition.in_arcs:
            place = arc.source
            new_marking[place] -= arc.weight
            if new_marking[place] == 0:
                del new_marking[place]

        for arc in transition.out_arcs:
            place = arc.target
            new_marking[place] += arc.weight
        return new_marking
    

    def get_enabled_transitions(self, marking: Marking) -> Set[Transition]:
        enabled = set()
        for t in self.transitions:
            # Skip fully-isolated transitions (no preset and no postset).
            if not t.in_arcs and not t.out_arcs:
                continue
            if self.is_enabled(t, marking):
                enabled.add(t)
        return enabled
    

    def net_variants(
        self,
        time_out_sec: float = 1.0,
        max_loop_depth: int = 3,
    ) -> Tuple[Set[Tuple[str, ...]], Set[Tuple[str, ...]], ExplorationDiagnostics]:
        """Explore the reachability graph and collect execution traces.

        Returns a 3-tuple ``(variants, partial_traces, diagnostics)``:

        - ``variants`` are traces that reached the final marking exactly.
        - ``partial_traces`` are prefixes that ended in a non-final dead
          marking (a structural deadlock) or were cut off when a transition
          was about to be fired beyond ``max_loop_depth`` iterations.
        - ``diagnostics`` carries deduplicated deadlock signatures, loop-cap
          counters, and truncation flags. The caller is expected to set the
          final ``status`` field after merging in any structural findings.

        This method never raises on unsound nets. Genuine programmer errors
        (e.g. invalid transitions) still propagate.
        """
        active: Set[Tuple[Marking, Tuple[str, ...], Tuple[str, ...]]] = set()
        active.add((self.initial_marking, tuple(), tuple()))

        variants: Set[Tuple[str, ...]] = set()
        partial_traces: Set[Tuple[str, ...]] = set()
        # Keyed by tokens so two deadlocks with the same place→count map dedupe;
        # the value preserves one example partial trace for diagnostics.
        deadlock_index: Dict[Tuple[Tuple[str, int], ...], Tuple[str, ...]] = {}
        loop_cap_hits: Dict[str, int] = {}
        truncated_by_active_cap = False
        truncated_by_timeout = False

        start_time: float = time.monotonic()
        visited_states: Set[Tuple[Marking, Tuple[str, ...]]] = set()

        while active:
            if time.monotonic() - start_time > time_out_sec:
                truncated_by_timeout = True
                break

            curr_marking, curr_trace, curr_trans_names_path = active.pop()

            state_key = (curr_marking, curr_trace)
            if state_key in visited_states:
                continue
            visited_states.add(state_key)

            enabled = self.get_enabled_transitions(curr_marking)

            if not enabled:
                if curr_marking == self.final_marking:
                    variants.add(curr_trace)
                else:
                    tokens = tuple(sorted((p.name, c) for p, c in curr_marking.items()))
                    deadlock_index.setdefault(tokens, curr_trace)
                    partial_traces.add(curr_trace)
                continue

            for t in enabled:
                if curr_trans_names_path.count(t.name) >= max_loop_depth:
                    loop_cap_hits[t.name] = loop_cap_hits.get(t.name, 0) + 1
                    # The current prefix is what we have; record it as partial.
                    partial_traces.add(curr_trace)
                    continue

                next_marking = self.execute(t, curr_marking)
                if next_marking is None:
                    continue

                next_trace = curr_trace
                if t.label_for_trace is not None:
                    next_trace = curr_trace + (t.label_for_trace,)

                next_trans_names_path = curr_trans_names_path + (t.name,)

                if next_marking == self.final_marking:
                    variants.add(next_trace)
                else:
                    if len(active) < 20000:
                        active.add((next_marking, next_trace, next_trans_names_path))
                    else:
                        truncated_by_active_cap = True

        diagnostics = ExplorationDiagnostics(
            deadlock_markings=[
                DeadlockSignature(tokens=tokens, example_partial_trace=example)
                for tokens, example in deadlock_index.items()
            ],
            loop_cap_hits=loop_cap_hits,
            truncated_by_active_cap=truncated_by_active_cap,
            truncated_by_timeout=truncated_by_timeout,
            sound_variant_count=len(variants),
            partial_trace_count=len(partial_traces),
            exploration_elapsed_seconds=time.monotonic() - start_time,
        )
        return variants, partial_traces, diagnostics

    def to_variant_event_log(
        self,
        time_out_sec: float = 1.0,
        max_loop_depth: int = 3,
    ) -> Tuple[Set[Tuple[str, ...]], Set[Tuple[str, ...]], ExplorationDiagnostics]:
        """Alias for :meth:`net_variants` retained for the legacy name."""
        return self.net_variants(time_out_sec, max_loop_depth)
    

    def _get_new_internal_name(self, prefix: str) -> str:
        self.internal_id_counter += 1
        return f"_{prefix}_{self.internal_id_counter}"

    def _create_pn_place(self, name: Optional[str] = None, is_bpmn_element: bool = True) -> Place:
        place_name = name if name else self._get_new_internal_name("p")
        if place_name in self.bpmn_elements_map:
            existing_elem = self.bpmn_elements_map[place_name]
            if is_bpmn_element and isinstance(existing_elem, Place):
                return existing_elem
            raise ValueError(f"PN Place name conflict or type mismatch for {place_name}")

        p = Place(name=place_name) 
        self.places.add(p)
        if name:
             self.bpmn_elements_map[place_name] = p
        return p

    def _create_pn_transition(self, name: Optional[str] = None, label_for_trace: Optional[str] = None, is_bpmn_element: bool = True) -> Transition:
        trans_name = name if name else self._get_new_internal_name("t")
        if trans_name in self.bpmn_elements_map:
            existing_elem = self.bpmn_elements_map[trans_name]
            if is_bpmn_element and isinstance(existing_elem, Transition):
                return existing_elem
            raise ValueError(f"PN Transition name conflict or type mismatch for {trans_name}")
            
        t = Transition(name=trans_name, label_for_trace=label_for_trace) # Instantiates the dataclass
        self.transitions.add(t)
        if name:
            self.bpmn_elements_map[trans_name] = t
        return t

    def _get_pn_element(self, bpmn_id: str) -> Optional[Union[Place, Transition]]:
        return self.bpmn_elements_map.get(bpmn_id)

    def _create_initial_pn_elements_from_bpmn(
        self,
        follows: Dict[str, List[str]],
        implicit_join_bpmn_ids: Set[str]
    ):
        self.all_bpmn_ids_in_model.update(follows.keys())
        for successors in follows.values():
            self.all_bpmn_ids_in_model.update(successors)
        
        for bpmn_id in self.all_bpmn_ids_in_model:
            if bpmn_id in self.bpmn_elements_map and is_bpmn_element_relevant_for_pn(bpmn_id, self.bpmn_id_to_stencil):
                continue

            elem_type = get_bpmn_element_type(bpmn_id, self.bpmn_id_to_stencil)
            
            if elem_type == BpmnElementType.EVENT:
                self._create_pn_place(name=bpmn_id)
            elif elem_type == BpmnElementType.TASK:
                task_label_in_bpmn = self.bpmn_id_to_label.get(bpmn_id, bpmn_id)
                stencil = self.bpmn_id_to_stencil.get(bpmn_id, "")
                if stencil.startswith("CollapsedSubprocess") and task_label_in_bpmn.startswith(stencil):
                    potential_actual_label = task_label_in_bpmn[len(stencil):].strip()
                    if potential_actual_label.startswith("(") and potential_actual_label.endswith(")"):
                        task_label_in_bpmn = potential_actual_label[1:-1].strip()
                self._create_pn_transition(name=bpmn_id, label_for_trace=task_label_in_bpmn or bpmn_id)
                
                preset_count = len(get_direct_preset_bpmn_ids(bpmn_id, follows, self.bpmn_id_to_stencil, self.all_bpmn_ids_in_model))
                if preset_count > 1:
                    implicit_join_bpmn_ids.add(bpmn_id)

            elif elem_type == BpmnElementType.GATEWAY:
                self._create_pn_transition(name=bpmn_id, label_for_trace=None)

    def _establish_flow_relations(self, follows: Dict[str, List[str]]):
        for source_bpmn_id in self.all_bpmn_ids_in_model:
            source_pn_elem = self._get_pn_element(source_bpmn_id)
            if not source_pn_elem: continue

            source_bpmn_type = get_bpmn_element_type(source_bpmn_id, self.bpmn_id_to_stencil)
            postset_bpmn_ids = get_direct_postset_bpmn_ids(source_bpmn_id, follows, self.bpmn_id_to_stencil)

            for target_bpmn_id in postset_bpmn_ids:
                target_pn_elem = self._get_pn_element(target_bpmn_id)
                if not target_pn_elem: continue

                target_bpmn_type = get_bpmn_element_type(target_bpmn_id, self.bpmn_id_to_stencil)

                if source_bpmn_type == BpmnElementType.EVENT and isinstance(source_pn_elem, Place):
                    if target_bpmn_type == BpmnElementType.EVENT and isinstance(target_pn_elem, Place):
                        t_conn = self._create_pn_transition(label_for_trace=None)
                        self.add_arc_from_to(source_pn_elem, t_conn)
                        self.add_arc_from_to(t_conn, target_pn_elem)
                    elif isinstance(target_pn_elem, Transition):
                        self.add_arc_from_to(source_pn_elem, target_pn_elem)
                
                elif source_bpmn_type == BpmnElementType.TASK and isinstance(source_pn_elem, Transition):
                    if target_bpmn_type == BpmnElementType.GATEWAY and isinstance(target_pn_elem, Transition):
                        is_choice = is_bpmn_choice_gateway(target_bpmn_id, self.bpmn_id_to_stencil)
                        p_intermediate: Place
                        if is_choice:
                            if target_bpmn_id in self.gateway_shared_input_places:
                                p_intermediate = self.gateway_shared_input_places[target_bpmn_id]
                            else:
                                p_intermediate = self._create_pn_place(name=f"gin_{target_bpmn_id}")
                                self.gateway_shared_input_places[target_bpmn_id] = p_intermediate
                                self.add_arc_from_to(p_intermediate, target_pn_elem)
                        else:
                            p_intermediate = self._create_pn_place()
                            self.add_arc_from_to(p_intermediate, target_pn_elem)
                        self.add_arc_from_to(source_pn_elem, p_intermediate)

                    elif target_bpmn_type == BpmnElementType.TASK and isinstance(target_pn_elem, Transition):
                        p_conn = self._create_pn_place()
                        self.add_arc_from_to(source_pn_elem, p_conn)
                        self.add_arc_from_to(p_conn, target_pn_elem)
                    elif target_bpmn_type == BpmnElementType.EVENT and isinstance(target_pn_elem, Place):
                        self.add_arc_from_to(source_pn_elem, target_pn_elem)

                elif source_bpmn_type == BpmnElementType.GATEWAY and isinstance(source_pn_elem, Transition):
                    is_src_choice = is_bpmn_choice_gateway(source_bpmn_id, self.bpmn_id_to_stencil)
                    p_output_of_gateway: Place

                    if is_src_choice:
                        if source_bpmn_id in self.gateway_shared_output_places:
                            p_output_of_gateway = self.gateway_shared_output_places[source_bpmn_id]
                        else:
                            p_output_of_gateway = self._create_pn_place(name=f"gout_{source_bpmn_id}")
                            self.gateway_shared_output_places[source_bpmn_id] = p_output_of_gateway
                            self.add_arc_from_to(source_pn_elem, p_output_of_gateway)
                    else:
                        p_output_of_gateway = self._create_pn_place()
                        self.add_arc_from_to(source_pn_elem, p_output_of_gateway)

                    if target_bpmn_type == BpmnElementType.EVENT and isinstance(target_pn_elem, Place):
                        if is_src_choice:
                            t_choice_to_event = self._create_pn_transition(label_for_trace=None)
                            self.add_arc_from_to(p_output_of_gateway, t_choice_to_event)
                            self.add_arc_from_to(t_choice_to_event, target_pn_elem)
                        else:
                            self.add_arc_from_to(p_output_of_gateway, target_pn_elem)
                    
                    elif isinstance(target_pn_elem, Transition):
                        if target_bpmn_type == BpmnElementType.GATEWAY:
                            is_tgt_choice = is_bpmn_choice_gateway(target_bpmn_id, self.bpmn_id_to_stencil)
                            if is_src_choice and is_tgt_choice:
                                p_input_to_target_gw: Place
                                if target_bpmn_id in self.gateway_shared_input_places:
                                    p_input_to_target_gw = self.gateway_shared_input_places[target_bpmn_id]
                                else:
                                    p_input_to_target_gw = self._create_pn_place(name=f"gin_{target_bpmn_id}")
                                    self.gateway_shared_input_places[target_bpmn_id] = p_input_to_target_gw
                                    self.add_arc_from_to(p_input_to_target_gw, target_pn_elem)
                                
                                t_conn_gateways = self._create_pn_transition(label_for_trace=None)
                                self.add_arc_from_to(p_output_of_gateway, t_conn_gateways)
                                self.add_arc_from_to(t_conn_gateways, p_input_to_target_gw)
                            
                            elif is_src_choice and not is_tgt_choice:
                                p_in_for_tgt_parallel_gw = self._create_pn_place()
                                t_conn = self._create_pn_transition(label_for_trace=None)
                                self.add_arc_from_to(p_output_of_gateway, t_conn)
                                self.add_arc_from_to(t_conn, p_in_for_tgt_parallel_gw)
                                self.add_arc_from_to(p_in_for_tgt_parallel_gw, target_pn_elem)
                            
                            elif not is_src_choice:
                                p_input_to_target_gw: Place
                                if is_tgt_choice:
                                    if target_bpmn_id in self.gateway_shared_input_places:
                                        p_input_to_target_gw = self.gateway_shared_input_places[target_bpmn_id]
                                    else:
                                        p_input_to_target_gw = self._create_pn_place(name=f"gin_{target_bpmn_id}")
                                        self.gateway_shared_input_places[target_bpmn_id] = p_input_to_target_gw
                                        self.add_arc_from_to(p_input_to_target_gw, target_pn_elem)
                                else:
                                    p_input_to_target_gw = self._create_pn_place()
                                    self.add_arc_from_to(p_input_to_target_gw, target_pn_elem)
                                self.add_arc_from_to(p_output_of_gateway, p_input_to_target_gw)
                        else:
                            self.add_arc_from_to(p_output_of_gateway, target_pn_elem)
    
    def _correct_implicit_joins(self, implicit_join_bpmn_ids: Set[str]):
        for bpmn_id in implicit_join_bpmn_ids:
            pn_task_elem = self._get_pn_element(bpmn_id)
            if not (pn_task_elem and isinstance(pn_task_elem, Transition)):
                continue
            
            current_in_places = {arc.source for arc in pn_task_elem.in_arcs if isinstance(arc.source, Place)}
            
            if len(current_in_places) > 1:
                p_shared_join = self._create_pn_place(name=f"p_join_{bpmn_id}")
                old_in_arcs = list(pn_task_elem.in_arcs)
                for arc_to_task in old_in_arcs:
                    if arc_to_task.source in current_in_places:
                        self.arcs.remove(arc_to_task)
                        arc_to_task.source.out_arcs.remove(arc_to_task)
                        pn_task_elem.in_arcs.remove(arc_to_task)
                        
                        t_path_to_join = self._create_pn_transition(label_for_trace=None)
                        self.add_arc_from_to(arc_to_task.source, t_path_to_join)
                        self.add_arc_from_to(t_path_to_join, p_shared_join)
                
                self.add_arc_from_to(p_shared_join, pn_task_elem)

    def _transform_labeled_bpmn_events_to_ptp(self):
        places_to_transform = []
        for p_event in list(self.places):
            bpmn_event_id = p_event.name
            if get_bpmn_element_type(bpmn_event_id, self.bpmn_id_to_stencil) == BpmnElementType.EVENT:
                event_text_label = self.bpmn_id_to_label.get(bpmn_event_id)
                generic_event_stencil_names = {"startevent", "endevent", "intermediatethrowevent", "intermediatecatchevent", "boundaryevent", "event"}
                if event_text_label and event_text_label.strip() and event_text_label.lower() not in generic_event_stencil_names:
                    places_to_transform.append(p_event)
        
        for p_old_event_place in places_to_transform:
            if p_old_event_place not in self.places: 
                continue

            bpmn_event_id = p_old_event_place.name
            
            p_in = self._create_pn_place(name=f"pin_{bpmn_event_id}")
            t_event = self._create_pn_transition(name=f"t_{bpmn_event_id}", label_for_trace=self.bpmn_id_to_label.get(bpmn_event_id) or bpmn_event_id)
            p_out = self._create_pn_place(name=f"pout_{bpmn_event_id}")

            self.add_arc_from_to(p_in, t_event)
            self.add_arc_from_to(t_event, p_out)

            for arc in list(p_old_event_place.in_arcs):
                source_node = arc.source
                self.arcs.remove(arc)
                source_node.out_arcs.remove(arc)
                p_old_event_place.in_arcs.remove(arc)
                self.add_arc_from_to(source_node, p_in)

            for arc in list(p_old_event_place.out_arcs):
                target_node = arc.target
                self.arcs.remove(arc)
                target_node.in_arcs.remove(arc)
                p_old_event_place.out_arcs.remove(arc)
                self.add_arc_from_to(p_out, target_node)

            self.places.remove(p_old_event_place)
            if bpmn_event_id in self.bpmn_elements_map and self.bpmn_elements_map[bpmn_event_id] == p_old_event_place:
                del self.bpmn_elements_map[bpmn_event_id]

    def _handle_attached_events(self, follows: Dict[str, List[str]]):
        raise NotImplementedError("Attached events handling is not implemented yet.")

    def _silence_gateway_transitions(self):
        from model_evaluation.json_to_pn import get_bpmn_element_type, BpmnElementType, GATEWAY_STENCIL_NAMES
        for t in self.transitions:
            if t.name in self.bpmn_id_to_stencil:
                stencil = self.bpmn_id_to_stencil[t.name].lower()
                if "gateway" in stencil or stencil in GATEWAY_STENCIL_NAMES:
                    t.label_for_trace = None

    def _ensure_single_start_end_places_and_get_markings(self) -> Tuple[Marking, Marking]:
        current_source_places = {p for p in self.places if not p.in_arcs}
        current_sink_places = {p for p in self.places if not p.out_arcs}

        final_start_place: Optional[Place] = None # Initialize to satisfy linter if no paths lead to assignment
        if not current_source_places:
            source_transitions = {t for t in self.transitions if not t.in_arcs}
            if source_transitions:
                final_start_place = self._create_pn_place(name="_global_start_p")
                for t_source in source_transitions:
                    self.add_arc_from_to(final_start_place, t_source)
            elif self.places:
                 final_start_place = self._create_pn_place(name="_global_start_p_fallback")
                 if self.transitions: 
                     self.add_arc_from_to(final_start_place, next(iter(self.transitions)))
            elif not self.places and not self.transitions:
                return Marking(), Marking()
            else:
                final_start_place = self._create_pn_place(name="_global_start_p_unhandled")
        elif len(current_source_places) == 1:
            final_start_place = list(current_source_places)[0]
        else:
            final_start_place = self._create_pn_place(name="_global_start_p")
            for p_source in current_source_places:
                t_connect = self._create_pn_transition(label_for_trace=None)
                self.add_arc_from_to(final_start_place, t_connect)
                self.add_arc_from_to(t_connect, p_source)
        
        initial_marking = Marking({final_start_place: 1}) if final_start_place else Marking()

        final_end_place: Optional[Place] = None # Initialize
        if not current_sink_places:
            sink_transitions = {t for t in self.transitions if not t.out_arcs}
            if sink_transitions:
                final_end_place = self._create_pn_place(name="_global_end_p")
                for t_sink in sink_transitions:
                    self.add_arc_from_to(t_sink, final_end_place)
            elif self.places:
                final_end_place = self._create_pn_place(name="_global_end_p_fallback")
                if self.transitions: self.add_arc_from_to(next(iter(self.transitions)), final_end_place)
            elif not self.places and not self.transitions:
                 return initial_marking, Marking()
            else:
                final_end_place = self._create_pn_place(name="_global_end_p_unhandled")
        elif len(current_sink_places) == 1:
            final_end_place = list(current_sink_places)[0]
        else:
            final_end_place = self._create_pn_place(name="_global_end_p")
            for p_sink in current_sink_places:
                t_connect = self._create_pn_transition(label_for_trace=None)
                self.add_arc_from_to(p_sink, t_connect)
                self.add_arc_from_to(t_connect, final_end_place)
        
        final_marking = Marking({final_end_place: 1}) if final_end_place else Marking()
        return initial_marking, final_marking
    
    @classmethod    
    def from_simplified_json(
        cls,
        model_json_dict: Dict[str, Any],
        model_id_prefix: str = "",
        with_event_labels: bool = True
    ) -> "PetriNet":
        """
        Converts a BPMN JSON dictionary to a Petri net.
        Args:
            model_json_dict: The BPMN JSON dictionary to convert.
            model_id_prefix: Optional prefix for element IDs (should be the original model ID).
            with_event_labels: Whether to include event labels in the Petri net. This means that
            places that are events will be transformed into a place-transition-place structure.
        Returns:
            A tuple containing the Petri net, initial marking, final marking, and a mapping from ids to labels.
        """
        follows, bpmn_id_to_stencil, bpmn_id_to_label = parse_simplified_bpmn_json(model_json_dict, model_id_prefix)
        pn = PetriNet(name=model_id_prefix)
        pn.internal_id_counter = 0
        pn.bpmn_id_to_stencil = bpmn_id_to_stencil
        pn.bpmn_id_to_label = bpmn_id_to_label
        implicit_join_task_bpmn_ids: Set[str] = set()  

        pn._create_initial_pn_elements_from_bpmn(follows, implicit_join_task_bpmn_ids)
        pn._establish_flow_relations(follows)
        
        pn._correct_implicit_joins(implicit_join_task_bpmn_ids)
        if with_event_labels:
            pn._transform_labeled_bpmn_events_to_ptp()
        # self._handle_attached_events(follows) # TODO Not implemented yet
        pn._silence_gateway_transitions()
        
        im, fm = pn._ensure_single_start_end_places_and_get_markings()
        pn.initial_marking = im
        pn.final_marking = fm
        return pn
