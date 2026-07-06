"""BPMN process-model evaluation framework.

Public API for programmatic (library) use. Import from here — the internal
module layout (``bpmn_similarity``, ``trace_extraction``, ``petri``, etc.)
is not part of the stable surface.

Typical usage::

    from model_evaluation import (
        load_bpmn_xml,
        calculate_bpmn_similarity,
        calculate_trace_similarity,
        calculate_hybrid_similarity,
        extract_traces,
        normalize_atomic_names,
    )

    m1 = load_bpmn_xml("process1.bpmn")
    m2 = load_bpmn_xml("process2.bpmn")

    structural = calculate_bpmn_similarity(m1, m2, method="dice")
    t1, t2 = extract_traces(m1), extract_traces(m2)
    behavioral = calculate_trace_similarity(t1, t2, method="jaccard")
    hybrid = calculate_hybrid_similarity(
        structural, behavioral, structural_weight=0.5
    )

``normalize_atomic_names`` performs semantic name alignment via a
sentence-transformer model and is part of the standard public API.
"""

from ._loaders import load_bpmn, load_bpmn_xml, load_signavio_json
from .bpmn_conversion import BPMNConverter, XMLBPMNConverter
from .bpmn_normalization import normalize_atomic_names
from .bpmn_sets import extract_bpmn_sets
from .bpmn_similarity import (
    calculate_bpmn_similarity,
    calculate_hybrid_similarity,
    calculate_ngram_similarity,
    calculate_trace_similarity,
)
from .trace_extraction import (
    TraceExtractionResult,
    compare_trace_sets,
    extract_ngrams,
    extract_traces,
)

__all__ = [
    # Loaders
    "load_bpmn",
    "load_bpmn_xml",
    "load_signavio_json",
    # Converters (for callers who already have parsed JSON / XML strings)
    "BPMNConverter",
    "XMLBPMNConverter",
    # Similarity
    "calculate_bpmn_similarity",
    "calculate_hybrid_similarity",
    "calculate_ngram_similarity",
    "calculate_trace_similarity",
    # Trace extraction
    "TraceExtractionResult",
    "compare_trace_sets",
    "extract_ngrams",
    "extract_traces",
    # Structural sets
    "extract_bpmn_sets",
    # Semantic name alignment
    "normalize_atomic_names",
]
