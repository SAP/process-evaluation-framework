"""End-to-end tests for graceful handling of unsound Petri nets.

Covers three layers in one file:

1. Structural pre-check (Phase 1) — ``PetriNet.structural_check`` and the
   diagnostics dataclasses (``SoundnessStatus``, ``StructuralFinding``,
   ``DeadlockSignature``, ``ExplorationDiagnostics``).
2. Non-throwing explorer (Phase 2) — ``PetriNet.net_variants`` records
   deadlocks/loop caps instead of raising.
3. ``extract_traces`` integration (Phase 3) — full pipeline against real
   BPMN fixtures, plus similarity helpers accepting either lists or
   ``TraceExtractionResult``.
"""

import json
import logging
from pathlib import Path

import pytest

from BPMN_conversion import BPMNConverter
from XML_conversion import XMLBPMNConverter
from petri import (
    DeadlockSignature,
    ExplorationDiagnostics,
    Marking,
    PetriNet,
    Place,
    SoundnessStatus,
    Transition,
)
from trace_extraction import (
    TraceExtractionResult,
    compare_trace_sets,
    extract_traces,
)
from bpmn_similarity import calculate_trace_similarity


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------

def _wf_net(name: str = "wf") -> PetriNet:
    """Minimal sound workflow net: p_in -> t -> p_out."""
    pn = PetriNet(name=name)
    p_in = Place(name="p_in")
    p_out = Place(name="p_out")
    t = Transition(name="t", label_for_trace="A")
    pn.places.update({p_in, p_out})
    pn.transitions.add(t)
    pn.add_arc_from_to(p_in, t)
    pn.add_arc_from_to(t, p_out)
    pn.initial_marking = Marking({p_in: 1})
    pn.final_marking = Marking({p_out: 1})
    return pn


def _build_sound_seq() -> PetriNet:
    """p_in -> tA -> p_mid -> tB -> p_out (single trace: A,B)."""
    pn = PetriNet(name="seq")
    p_in, p_mid, p_out = Place(name="p_in"), Place(name="p_mid"), Place(name="p_out")
    tA = Transition(name="tA", label_for_trace="A")
    tB = Transition(name="tB", label_for_trace="B")
    pn.places.update({p_in, p_mid, p_out})
    pn.transitions.update({tA, tB})
    pn.add_arc_from_to(p_in, tA)
    pn.add_arc_from_to(tA, p_mid)
    pn.add_arc_from_to(p_mid, tB)
    pn.add_arc_from_to(tB, p_out)
    pn.initial_marking = Marking({p_in: 1})
    pn.final_marking = Marking({p_out: 1})
    return pn


def _build_deadlock_only() -> PetriNet:
    """AND-split that leaves a stuck token on one branch — every run deadlocks."""
    pn = PetriNet(name="deadlock_only")
    p_in = Place(name="p_in")
    p_a = Place(name="p_a")
    p_b = Place(name="p_b")
    p_out = Place(name="p_out")
    p_stuck = Place(name="p_stuck")
    t_split = Transition(name="t_split", label_for_trace=None)
    t_a = Transition(name="t_a", label_for_trace="A")
    t_b = Transition(name="t_b", label_for_trace="B")
    pn.places.update({p_in, p_a, p_b, p_out, p_stuck})
    pn.transitions.update({t_split, t_a, t_b})
    pn.add_arc_from_to(p_in, t_split)
    pn.add_arc_from_to(t_split, p_a)
    pn.add_arc_from_to(t_split, p_b)
    pn.add_arc_from_to(p_a, t_a)
    pn.add_arc_from_to(t_a, p_out)
    pn.add_arc_from_to(p_b, t_b)
    pn.add_arc_from_to(t_b, p_stuck)
    pn.initial_marking = Marking({p_in: 1})
    pn.final_marking = Marking({p_out: 1})
    return pn


def _build_mixed() -> PetriNet:
    """XOR-split: one branch reaches p_out cleanly, other deadlocks."""
    pn = PetriNet(name="mixed")
    p_in = Place(name="p_in")
    p_choice = Place(name="p_choice")
    p_out = Place(name="p_out")
    p_dead = Place(name="p_dead")
    t_x = Transition(name="t_x", label_for_trace=None)
    t_good = Transition(name="t_good", label_for_trace="GOOD")
    t_bad = Transition(name="t_bad", label_for_trace="BAD")
    pn.places.update({p_in, p_choice, p_out, p_dead})
    pn.transitions.update({t_x, t_good, t_bad})
    pn.add_arc_from_to(p_in, t_x)
    pn.add_arc_from_to(t_x, p_choice)
    pn.add_arc_from_to(p_choice, t_good)
    pn.add_arc_from_to(t_good, p_out)
    pn.add_arc_from_to(p_choice, t_bad)
    pn.add_arc_from_to(t_bad, p_dead)
    pn.initial_marking = Marking({p_in: 1})
    pn.final_marking = Marking({p_out: 1})
    return pn


def _build_self_loop() -> PetriNet:
    """A loop transition that fires forever; max_loop_depth caps it."""
    pn = PetriNet(name="loop")
    p = Place(name="p_loop")
    p_out = Place(name="p_out")
    t_loop = Transition(name="t_loop", label_for_trace="L")
    t_exit = Transition(name="t_exit", label_for_trace="X")
    pn.places.update({p, p_out})
    pn.transitions.update({t_loop, t_exit})
    pn.add_arc_from_to(p, t_loop)
    pn.add_arc_from_to(t_loop, p)
    pn.add_arc_from_to(p, t_exit)
    pn.add_arc_from_to(t_exit, p_out)
    pn.initial_marking = Marking({p: 1})
    pn.final_marking = Marking({p_out: 1})
    return pn


def _load(path: Path):
    """Mirror comparison_widget._load_model so tests use the same pipeline."""
    if path.suffix in (".xml", ".bpmn"):
        return XMLBPMNConverter.convert_file(str(path)).to_dict()
    with path.open("r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


# ---------------------------------------------------------------------------
# Phase 1 — structural pre-check & diagnostics dataclasses
# ---------------------------------------------------------------------------

def test_structural_check_clean_net_returns_empty():
    pn = _wf_net()
    findings = pn.structural_check()
    assert findings == []


def test_structural_check_missing_sink():
    pn = _wf_net()
    p_out = next(p for p in pn.places if p.name == "p_out")
    arc_to_remove = next(a for a in pn.arcs if a.target is p_out)
    pn.arcs.discard(arc_to_remove)
    arc_to_remove.source.out_arcs.discard(arc_to_remove)
    pn.places.discard(p_out)

    findings = pn.structural_check()
    issues = {f.issue for f in findings}
    assert "no_sink_place" in issues


def test_structural_check_missing_source():
    pn = PetriNet(name="no_source")
    p_only = Place(name="orphan")
    t = Transition(name="t")
    pn.places.add(p_only)
    pn.transitions.add(t)
    pn.add_arc_from_to(t, p_only)

    findings = pn.structural_check()
    issues = {f.issue for f in findings}
    assert "no_source_place" in issues


def test_structural_check_isolated_node():
    pn = _wf_net()
    floater = Place(name="floater")
    pn.places.add(floater)

    findings = pn.structural_check()
    isolated = [f for f in findings if f.issue == "isolated_node"]
    assert len(isolated) == 1
    assert isolated[0].node_id == "floater"


def test_structural_check_unreachable_node():
    pn = _wf_net()
    detached_p = Place(name="detached_p")
    detached_t = Transition(name="detached_t")
    pn.places.add(detached_p)
    pn.transitions.add(detached_t)
    pn.add_arc_from_to(detached_p, detached_t)
    pn.add_arc_from_to(detached_t, detached_p)

    findings = pn.structural_check()
    issues = {(f.issue, f.node_id) for f in findings}
    assert ("unreachable_from_source", "detached_p") in issues
    assert ("unreachable_from_source", "detached_t") in issues


def test_structural_check_dead_transition_no_preset():
    pn = PetriNet(name="dead_t")
    p = Place(name="p")
    t_dead = Transition(name="t_dead")
    pn.places.add(p)
    pn.transitions.add(t_dead)
    pn.add_arc_from_to(t_dead, p)

    findings = pn.structural_check()
    issues = {f.issue for f in findings}
    assert "dead_transition_no_preset" in issues


def test_structural_check_multiple_sinks():
    pn = _wf_net()
    p_extra = Place(name="p_extra_sink")
    t = next(iter(pn.transitions))
    pn.places.add(p_extra)
    pn.add_arc_from_to(t, p_extra)

    findings = pn.structural_check()
    sink_issues = [f for f in findings if f.issue == "multiple_sink_places"]
    assert len(sink_issues) >= 2


def test_soundness_status_enum_values():
    # Sanity: string values used in logging/UI must stay stable.
    assert SoundnessStatus.SOUND.value == "sound"
    assert SoundnessStatus.UNSOUND_RECOVERED.value == "unsound_recovered"
    assert SoundnessStatus.UNSOUND_NO_VARIANTS.value == "unsound_no_variants"
    assert SoundnessStatus.STRUCTURALLY_BROKEN.value == "structurally_broken"
    assert SoundnessStatus.EXPLORATION_TRUNCATED.value == "exploration_truncated"


def test_deadlock_signature_dedupes_by_tokens():
    sig_a = DeadlockSignature(tokens=(("p1", 1), ("p2", 2)), example_partial_trace=("A",))
    sig_b = DeadlockSignature(tokens=(("p1", 1), ("p2", 2)), example_partial_trace=("B",))
    sig_c = DeadlockSignature(tokens=(("p1", 1),), example_partial_trace=("A",))
    # Default dataclass __eq__ compares ALL fields including the example trace.
    # The dedup contract dedupes on `tokens` alone — caller's responsibility
    # (we use a dict keyed by the tokens tuple). This test pins that behavior.
    assert sig_a != sig_b
    assert sig_a != sig_c


def test_exploration_diagnostics_default_is_sound():
    diag = ExplorationDiagnostics()
    assert diag.status == SoundnessStatus.SOUND
    assert diag.structural_findings == []
    assert diag.deadlock_markings == []
    assert diag.loop_cap_hits == {}
    assert diag.truncated_by_active_cap is False
    assert diag.truncated_by_timeout is False


# ---------------------------------------------------------------------------
# Phase 2 — non-throwing net_variants explorer
# ---------------------------------------------------------------------------

def test_net_variants_sound_returns_variants_only():
    pn = _build_sound_seq()
    variants, partials, diag = pn.net_variants(time_out_sec=1.0, max_loop_depth=3)
    assert variants == {("A", "B")}
    assert partials == set()
    assert diag.deadlock_markings == []
    assert diag.loop_cap_hits == {}
    assert not diag.truncated_by_timeout
    assert not diag.truncated_by_active_cap
    assert diag.sound_variant_count == 1
    assert diag.partial_trace_count == 0


def test_net_variants_deadlock_only_does_not_raise():
    pn = _build_deadlock_only()
    # Previously this raised ValueError; now it should record a deadlock.
    variants, partials, diag = pn.net_variants(time_out_sec=1.0, max_loop_depth=3)
    assert variants == set()
    assert partials
    assert len(diag.deadlock_markings) >= 1
    seen_places = {
        place_name
        for sig in diag.deadlock_markings
        for place_name, _count in sig.tokens
    }
    assert "p_stuck" in seen_places or "p_out" in seen_places


def test_net_variants_mixed_returns_both_buckets():
    pn = _build_mixed()
    variants, partials, diag = pn.net_variants(time_out_sec=1.0, max_loop_depth=3)
    assert ("GOOD",) in variants
    assert ("BAD",) in partials
    assert len(diag.deadlock_markings) == 1
    sig = diag.deadlock_markings[0]
    assert ("p_dead", 1) in sig.tokens
    assert sig.example_partial_trace == ("BAD",)


def test_net_variants_loop_cap_hits_recorded():
    pn = _build_self_loop()
    variants, partials, diag = pn.net_variants(time_out_sec=1.0, max_loop_depth=2)
    assert ("X",) in variants
    assert diag.loop_cap_hits.get("t_loop", 0) >= 1


def test_net_variants_dedupes_deadlock_signatures():
    """Two distinct paths into the same dead marking should dedupe to one signature."""
    pn = PetriNet(name="dup_deadlock")
    p_in = Place(name="p_in")
    p_mid = Place(name="p_mid")
    p_dead = Place(name="p_dead")
    p_out_unreachable = Place(name="p_out")
    t_x1 = Transition(name="t_x1", label_for_trace="X1")
    t_x2 = Transition(name="t_x2", label_for_trace="X2")
    t_to_dead = Transition(name="t_to_dead", label_for_trace="D")
    pn.places.update({p_in, p_mid, p_dead, p_out_unreachable})
    pn.transitions.update({t_x1, t_x2, t_to_dead})
    pn.add_arc_from_to(p_in, t_x1)
    pn.add_arc_from_to(t_x1, p_mid)
    pn.add_arc_from_to(p_in, t_x2)
    pn.add_arc_from_to(t_x2, p_mid)
    pn.add_arc_from_to(p_mid, t_to_dead)
    pn.add_arc_from_to(t_to_dead, p_dead)
    pn.initial_marking = Marking({p_in: 1})
    pn.final_marking = Marking({p_out_unreachable: 1})

    variants, partials, diag = pn.net_variants(time_out_sec=1.0, max_loop_depth=3)
    assert variants == set()
    assert len(diag.deadlock_markings) == 1
    assert diag.deadlock_markings[0].tokens == (("p_dead", 1),)


def test_to_variant_event_log_alias_returns_same_shape():
    pn = _build_sound_seq()
    a = pn.to_variant_event_log(time_out_sec=1.0, max_loop_depth=3)
    b = pn.net_variants(time_out_sec=1.0, max_loop_depth=3)
    assert a[0] == b[0]
    assert a[1] == b[1]


# ---------------------------------------------------------------------------
# Phase 3 — extract_traces against real BPMN fixtures + similarity helpers
# ---------------------------------------------------------------------------

def test_extract_traces_returns_result_object_for_sound_model():
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    res = extract_traces(sound, timeout_seconds=2.0, max_loop_depth=3)
    assert isinstance(res, TraceExtractionResult)
    assert res.is_sound, f"expected sound, got {res.diagnostics.status}: {res.diagnostics.summary}"
    assert res.partial_traces == []
    assert len(res.variants) >= 1


def test_extract_traces_handles_unsound_model_without_raising(caplog):
    """The exact bug described in the plan: AND-split with no join."""
    unsound = _load(EXAMPLES / "and_gateway_no_join.bpmn")

    with caplog.at_level(logging.WARNING, logger="trace_extraction"):
        res = extract_traces(unsound, timeout_seconds=2.0, max_loop_depth=3)

    assert isinstance(res, TraceExtractionResult)
    assert not res.is_sound
    assert res.diagnostics.status in {
        SoundnessStatus.UNSOUND_RECOVERED,
        SoundnessStatus.UNSOUND_NO_VARIANTS,
        SoundnessStatus.STRUCTURALLY_BROKEN,
    }
    # Plan acceptance criterion: exactly one WARNING per non-sound extraction.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "partial results" in warnings[0].getMessage()


def test_extract_traces_sound_model_emits_no_warnings(caplog):
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    with caplog.at_level(logging.WARNING, logger="trace_extraction"):
        extract_traces(sound, timeout_seconds=2.0, max_loop_depth=3)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_calculate_trace_similarity_accepts_results():
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    res = extract_traces(sound, timeout_seconds=2.0, max_loop_depth=3)

    score_self = calculate_trace_similarity(res, res, method="jaccard")
    assert score_self == pytest.approx(1.0)


def test_calculate_trace_similarity_unsound_vs_sound_does_not_crash():
    """Even when one side is unsound, similarity should produce a number."""
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    unsound = _load(EXAMPLES / "and_gateway_no_join.bpmn")

    res_sound = extract_traces(sound, timeout_seconds=2.0, max_loop_depth=3)
    res_unsound = extract_traces(unsound, timeout_seconds=2.0, max_loop_depth=3)

    score = calculate_trace_similarity(res_sound, res_unsound, method="jaccard")
    assert 0.0 <= score <= 1.0


def test_compare_trace_sets_includes_diagnostics_when_given_results():
    sound = _load(EXAMPLES / "and_gateway_with_join.bpmn")
    unsound = _load(EXAMPLES / "and_gateway_no_join.bpmn")

    res_sound = extract_traces(sound, timeout_seconds=2.0, max_loop_depth=3)
    res_unsound = extract_traces(unsound, timeout_seconds=2.0, max_loop_depth=3)

    comp = compare_trace_sets(res_sound, res_unsound, model_1_name="sound", model_2_name="unsound")
    assert "model_1_diagnostics" in comp
    assert "model_2_diagnostics" in comp
    assert comp["model_1_diagnostics"].status == SoundnessStatus.SOUND
    assert comp["model_2_diagnostics"].status != SoundnessStatus.SOUND


def test_calculate_trace_similarity_back_compat_with_lists():
    """The list-of-lists API must still work."""
    score = calculate_trace_similarity(
        [["A", "B"], ["A", "C"]],
        [["A", "B"]],
        method="jaccard",
    )
    assert score == pytest.approx(0.5)
