"""Extract and analyze traces from BPMN models using Petri net conversion.

This module provides utilities for extracting execution traces (variants) from BPMN models
by converting them to Petri nets and performing state-space exploration.

When a Petri net is not a sound workflow net (e.g. the source BPMN contains
unsynchronized parallel branches), trace extraction does not raise. Instead it
returns a :class:`TraceExtractionResult` carrying both the sound variants and
the partial traces that ended in deadlocks or hit the loop-depth cap, along
with structured :class:`ExplorationDiagnostics`. A ``WARNING`` is
emitted via the ``model_evaluation.trace_extraction`` logger per non-sound net.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Union

from .petri import (
    ExplorationDiagnostics,
    PetriNet,
    SEVERE_STRUCTURAL_ISSUES,
    SoundnessStatus,
    StructuralFinding,
)


logger = logging.getLogger(__name__)


@dataclass
class TraceExtractionResult:
    """Outcome of :func:`extract_traces`.

    ``variants`` are sound execution traces (those that reached the final
    marking exactly). ``partial_traces`` are prefixes that ended in a deadlock
    or were cut off by the loop-depth cap. ``diagnostics`` describes what was
    seen, why, and at what severity.

    Use :meth:`all_traces` when comparing two models behaviorally and you want
    similarity computed over sound + partial traces together. Use
    :attr:`variants` alone when only sound behavior should count.

    ``elapsed_seconds`` is the total wall-clock for :func:`extract_traces`
    (BPMN→Petri parse + structural check + state-space exploration). The
    exploration-only slice is available as
    ``diagnostics.exploration_elapsed_seconds``.
    """

    variants: List[List[str]] = field(default_factory=list)
    partial_traces: List[List[str]] = field(default_factory=list)
    diagnostics: ExplorationDiagnostics = field(default_factory=ExplorationDiagnostics)
    elapsed_seconds: float = 0.0

    @property
    def is_sound(self) -> bool:
        return self.diagnostics.status == SoundnessStatus.SOUND

    def all_traces(self) -> List[List[str]]:
        return self.variants + self.partial_traces


def _coerce_to_trace_list(arg) -> List[List[str]]:
    """Local copy of the trace coercion helper.

    The canonical version lives in ``bpmn_similarity`` next to
    :func:`calculate_trace_similarity`; this duplicate exists so
    ``compare_trace_sets`` (a reporting helper) does not need to import from
    ``bpmn_similarity`` at module load time.
    """
    if isinstance(arg, TraceExtractionResult):
        return arg.all_traces()
    return arg


def __getattr__(name):
    """Lazy backward-compatible re-export.

    ``calculate_trace_similarity`` was moved to :mod:`bpmn_similarity`. To keep
    existing ``from trace_extraction import calculate_trace_similarity`` imports
    working, resolve it lazily here. Lazy resolution avoids a circular import
    at module load time (``bpmn_similarity`` imports from this module).
    """
    if name == "calculate_trace_similarity":
        from .bpmn_similarity import calculate_trace_similarity as _cts
        return _cts
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _format_summary(diag: ExplorationDiagnostics) -> str:
    parts: List[str] = []
    severe = [f for f in diag.structural_findings if f.issue in SEVERE_STRUCTURAL_ISSUES]
    if severe:
        parts.append(f"{len(severe)} severe structural issue(s)")
    if diag.deadlock_markings:
        parts.append(f"{len(diag.deadlock_markings)} distinct deadlock marking(s)")
    loop_total = sum(diag.loop_cap_hits.values())
    if loop_total:
        parts.append(f"{loop_total} loop-cap hit(s)")
    if diag.truncated_by_timeout:
        parts.append("exploration timed out")
    if diag.truncated_by_active_cap:
        parts.append("exploration truncated by active-set cap")

    if not parts:
        return f"sound: {diag.sound_variant_count} variant(s)"
    return (
        f"{diag.sound_variant_count} sound variant(s), "
        f"{diag.partial_trace_count} partial trace(s); "
        + ", ".join(parts)
    )


def _derive_status(
    sound_count: int,
    structural_findings: List[StructuralFinding],
    diag: ExplorationDiagnostics,
) -> SoundnessStatus:
    has_severe_structural = any(f.issue in SEVERE_STRUCTURAL_ISSUES for f in structural_findings)
    has_runtime_unsoundness = bool(diag.deadlock_markings) or bool(diag.loop_cap_hits)
    truncated = diag.truncated_by_timeout or diag.truncated_by_active_cap

    if has_severe_structural and sound_count == 0:
        return SoundnessStatus.STRUCTURALLY_BROKEN
    if has_runtime_unsoundness or has_severe_structural:
        return (
            SoundnessStatus.UNSOUND_RECOVERED
            if sound_count > 0
            else SoundnessStatus.UNSOUND_NO_VARIANTS
        )
    if truncated:
        return SoundnessStatus.EXPLORATION_TRUNCATED
    return SoundnessStatus.SOUND


def extract_traces(
    minimal_bpmn: Dict[str, Any],
    max_loop_depth: int = 2,
    timeout_seconds: float = 30.0,
) -> TraceExtractionResult:
    """Extract execution traces from a BPMN model in minimal JSON format.

    Args:
        minimal_bpmn: BPMN model in minimal JSON format.
        max_loop_depth: Maximum iterations through any single transition.
        timeout_seconds: Maximum wall-clock time spent exploring.

    Returns:
        :class:`TraceExtractionResult` with ``variants``, ``partial_traces``,
        and ``diagnostics`` populated.
    """
    start = time.perf_counter()
    petri_net = PetriNet.from_simplified_json(minimal_bpmn)
    structural_findings = petri_net.structural_check()

    sound_set, partial_set, diag = petri_net.net_variants(
        time_out_sec=timeout_seconds, max_loop_depth=max_loop_depth
    )
    diag.structural_findings = structural_findings
    diag.status = _derive_status(len(sound_set), structural_findings, diag)
    diag.summary = _format_summary(diag)

    if diag.status != SoundnessStatus.SOUND:
        logger.warning(
            "Trace extraction recovered partial results for net %r: %s",
            petri_net.name or "<unnamed>",
            diag.summary,
        )

    return TraceExtractionResult(
        variants=[list(t) for t in sound_set],
        partial_traces=[list(t) for t in partial_set],
        diagnostics=diag,
        elapsed_seconds=time.perf_counter() - start,
    )


def get_trace_statistics(traces: List[List[str]]) -> Dict[str, Any]:
    """Calculate statistics about a set of traces.

    Args:
        traces: List of traces to analyze

    Returns:
        Dictionary containing trace statistics
    """
    if not traces:
        return {
            "num_variants": 0,
            "min_length": 0,
            "max_length": 0,
            "avg_length": 0.0,
            "unique_activities": set()
        }

    unique_traces = {tuple(trace) for trace in traces}
    trace_lengths = [len(trace) for trace in unique_traces]
    unique_activities = set()
    for trace in unique_traces:
        unique_activities.update(trace)

    return {
        "num_variants": len(unique_traces),
        "min_length": min(trace_lengths),
        "max_length": max(trace_lengths),
        "avg_length": sum(trace_lengths) / len(trace_lengths),
        "unique_activities": unique_activities
    }


def extract_ngrams(
    traces: Union[List[List[str]], "TraceExtractionResult"],
    n: int = 2,
    pad: bool = True,
) -> List[Tuple[str, ...]]:
    """Decompose traces into a flat list of length n contiguous subsequences.
    With pad=True (default), each trace is wrapped with <START> and <END>, so first/last
    activity differences become distinct n-grams.

    Args:
        traces: Trace list, or a class TraceExtractionResult (in which case its all_traces())
        n: Window length (Must be >= 1)
        pad: Whether to wrap each trace with <START> / <END>

    Returns:
        Flat list of n-grams (tuples of strings), in trace order
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    trace_list = _coerce_to_trace_list(traces)
    ngrams: List[Tuple[str, ...]] = []
    for trace in trace_list:
        seq = ["<START>", *trace, "<END>"] if pad else list(trace)
        if len(seq) < n:
            continue
        for i in range(len(seq) - n + 1):
            ngrams.append(tuple(seq[i : i + n]))
    return ngrams


def compare_trace_sets(
    traces_1,
    traces_2,
    model_1_name: str = "Model 1",
    model_2_name: str = "Model 2"
) -> Dict[str, Any]:
    """Perform comprehensive comparison of two trace sets.

    Args:
        traces_1: First list of traces, or a :class:`TraceExtractionResult`.
        traces_2: Second list of traces, or a :class:`TraceExtractionResult`.
        model_1_name: Name for first model
        model_2_name: Name for second model

    Returns:
        Dictionary containing comparison results. When the inputs are
        :class:`TraceExtractionResult` instances, the dict additionally
        contains ``model_1_diagnostics`` and ``model_2_diagnostics`` so the
        caller can render warnings for unsound nets.
    """
    # Lazy import: ``calculate_trace_similarity`` lives in ``bpmn_similarity``,
    # which itself imports from this module. Importing it here keeps the
    # top-level dependency one-way (bpmn_similarity → trace_extraction).
    from .bpmn_similarity import calculate_ngram_similarity, calculate_trace_similarity

    list_1 = _coerce_to_trace_list(traces_1)
    list_2 = _coerce_to_trace_list(traces_2)

    set_1 = {tuple(trace) for trace in list_1}
    set_2 = {tuple(trace) for trace in list_2}

    stats_1 = get_trace_statistics(list_1)
    stats_2 = get_trace_statistics(list_2)

    common = set_1 & set_2
    unique_to_1 = set_1 - set_2
    unique_to_2 = set_2 - set_1

    result: Dict[str, Any] = {
        "model_1_name": model_1_name,
        "model_2_name": model_2_name,
        "statistics_1": stats_1,
        "statistics_2": stats_2,
        "common_traces": common,
        "unique_to_1": unique_to_1,
        "unique_to_2": unique_to_2,
        "jaccard_similarity": calculate_trace_similarity(traces_1, traces_2, "jaccard"),
        "dice_similarity": calculate_trace_similarity(traces_1, traces_2, "dice"),
        "overlap_similarity": calculate_trace_similarity(traces_1, traces_2, "overlap"),
        "bigram_jaccard": calculate_ngram_similarity(traces_1, traces_2, n=2, method="jaccard"),
        "bigram_dice": calculate_ngram_similarity(traces_1, traces_2, n=2, method="dice"),
        "bigram_overlap": calculate_ngram_similarity(traces_1, traces_2, n=2, method="overlap"),
    }
    if isinstance(traces_1, TraceExtractionResult):
        result["model_1_diagnostics"] = traces_1.diagnostics
    if isinstance(traces_2, TraceExtractionResult):
        result["model_2_diagnostics"] = traces_2.diagnostics
    return result


def print_trace_comparison(comparison: Dict[str, Any], show_traces: bool = False):
    """
    Print a formatted report of trace comparison results.

    Args:
        comparison: Comparison dictionary from compare_trace_sets()
        show_traces: Whether to print actual trace sequences (default: False)
    """
    model_1 = comparison["model_1_name"]
    model_2 = comparison["model_2_name"]
    stats_1 = comparison["statistics_1"]
    stats_2 = comparison["statistics_2"]

    print(f"\n{'='*70}")
    print(f"TRACE COMPARISON: {model_1} vs {model_2}")
    print(f"{'='*70}")

    print(f"\n{model_1} Statistics:")
    print(f"  • Variants: {stats_1['num_variants']}")
    print(f"  • Trace length: {stats_1['min_length']}-{stats_1['max_length']} (avg: {stats_1['avg_length']:.1f})")
    print(f"  • Unique activities: {len(stats_1['unique_activities'])}")

    print(f"\n{model_2} Statistics:")
    print(f"  • Variants: {stats_2['num_variants']}")
    print(f"  • Trace length: {stats_2['min_length']}-{stats_2['max_length']} (avg: {stats_2['avg_length']:.1f})")
    print(f"  • Unique activities: {len(stats_2['unique_activities'])}")

    print("\nSimilarity Scores:")
    print(f"  • Jaccard: {comparison['jaccard_similarity']:.2%}")
    print(f"  • Dice: {comparison['dice_similarity']:.2%}")
    print(f"  • Overlap: {comparison['overlap_similarity']:.2%}")

    if "bigram_jaccard" in comparison:
        print("\nBigram Similarity (graded — shared directly-follows pairs):")
        print(f"  • Jaccard: {comparison['bigram_jaccard']:.2%}")
        print(f"  • Dice: {comparison['bigram_dice']:.2%}")
        print(f"  • Overlap: {comparison['bigram_overlap']:.2%}")

    print("\nTrace Coverage:")
    print(f"  • Common variants: {len(comparison['common_traces'])}")
    print(f"  • Only in {model_1}: {len(comparison['unique_to_1'])}")
    print(f"  • Only in {model_2}: {len(comparison['unique_to_2'])}")

    for diag_key, model_label in (
        ("model_1_diagnostics", model_1),
        ("model_2_diagnostics", model_2),
    ):
        diag = comparison.get(diag_key)
        if diag is None or diag.status == SoundnessStatus.SOUND:
            continue
        print(f"\nDiagnostics for {model_label} ({diag.status.value}):")
        print(f"  • {diag.summary}")
        if diag.deadlock_markings:
            for sig in diag.deadlock_markings[:3]:
                tokens_str = ", ".join(f"{name}:{count}" for name, count in sig.tokens)
                print(f"    - deadlock at {{{tokens_str}}}, e.g. trace: {' → '.join(sig.example_partial_trace) or '<empty>'}")

    if show_traces and comparison['common_traces']:
        print("\nCommon Traces (first 5):")
        for i, trace in enumerate(list(comparison['common_traces'])[:5], 1):
            print(f"  {i}. {' → '.join(trace)}")

    if show_traces and comparison['unique_to_1']:
        print(f"\nUnique to {model_1} (first 3):")
        for i, trace in enumerate(list(comparison['unique_to_1'])[:3], 1):
            print(f"  {i}. {' → '.join(trace)}")

    if show_traces and comparison['unique_to_2']:
        print(f"\nUnique to {model_2} (first 3):")
        for i, trace in enumerate(list(comparison['unique_to_2'])[:3], 1):
            print(f"  {i}. {' → '.join(trace)}")

    print(f"{'='*70}\n")