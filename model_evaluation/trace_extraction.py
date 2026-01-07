"""Extract and analyze traces from BPMN models using Petri net conversion.

This module provides utilities for extracting execution traces (variants) from BPMN models
by converting them to Petri nets and performing state-space exploration.
"""

from typing import List, Dict, Any

from petri import PetriNet



def extract_traces(
    minimal_bpmn: Dict[str, Any],
    max_traces: int = 100,
    max_loop_depth: int = 2,
    timeout_seconds: float = 30.0,
) -> List[List[str]]:
    """Extract execution traces from a BPMN model in minimal JSON format.
    
    Args:
        minimal_bpmn: BPMN model in minimal JSON format
        max_traces: Maximum number of traces to extract
        max_loop_depth: Maximum iterations for loops
        timeout_seconds: Maximum execution time in seconds
    
    Returns:
        List of traces, where each trace is a list of transition names
    
    Raises:
        ValueError: If conversion or extraction fails
        TimeoutError: If extraction exceeds timeout
    """
    # Convert to Petri net
    petri_net = PetriNet.from_simplified_json(minimal_bpmn)
    return petri_net.net_variants(time_out_sec=timeout_seconds, max_loop_depth=max_loop_depth)


def calculate_trace_similarity(
    traces_1: List[List[str]],
    traces_2: List[List[str]],
    method: str = "jaccard"
) -> float:
    """Calculate similarity between two sets of traces.
    
    Args:
        traces_1: First list of traces
        traces_2: Second list of traces
        method: Similarity metric ("jaccard", "dice", or "overlap")
    
    Returns:
        Similarity score between 0.0 and 1.0
    """
    # Convert to sets of tuples for comparison
    set_1 = {tuple(trace) for trace in traces_1}
    set_2 = {tuple(trace) for trace in traces_2}
    
    if not set_1 and not set_2:
        return 1.0
    
    if not set_1 or not set_2:
        return 0.0
    
    intersection = set_1 & set_2
    union = set_1 | set_2
    
    if method == "jaccard":
        return len(intersection) / len(union) if union else 0.0
    elif method == "dice":
        return (2.0 * len(intersection)) / (len(set_1) + len(set_2))
    elif method == "overlap":
        min_size = min(len(set_1), len(set_2))
        return len(intersection) / min_size if min_size > 0 else 0.0
    else:
        raise ValueError(f"Unknown similarity method: {method}")


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
    
    # Convert to unique traces
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


def compare_trace_sets(
    traces_1: List[List[str]],
    traces_2: List[List[str]],
    model_1_name: str = "Model 1",
    model_2_name: str = "Model 2"
) -> Dict[str, Any]:
    """Perform comprehensive comparison of two trace sets.
    
    Args:
        traces_1: First list of traces
        traces_2: Second list of traces
        model_1_name: Name for first model
        model_2_name: Name for second model
    
    Returns:
        Dictionary containing comparison results
    """
    # Convert to sets for comparison
    set_1 = {tuple(trace) for trace in traces_1}
    set_2 = {tuple(trace) for trace in traces_2}
    
    stats_1 = get_trace_statistics(traces_1)
    stats_2 = get_trace_statistics(traces_2)
    
    common = set_1 & set_2
    unique_to_1 = set_1 - set_2
    unique_to_2 = set_2 - set_1
    
    return {
        "model_1_name": model_1_name,
        "model_2_name": model_2_name,
        "statistics_1": stats_1,
        "statistics_2": stats_2,
        "common_traces": common,
        "unique_to_1": unique_to_1,
        "unique_to_2": unique_to_2,
        "jaccard_similarity": calculate_trace_similarity(traces_1, traces_2, "jaccard"),
        "dice_similarity": calculate_trace_similarity(traces_1, traces_2, "dice"),
        "overlap_similarity": calculate_trace_similarity(traces_1, traces_2, "overlap")
    }


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
    
    print("\nTrace Coverage:")
    print(f"  • Common variants: {len(comparison['common_traces'])}")
    print(f"  • Only in {model_1}: {len(comparison['unique_to_1'])}")
    print(f"  • Only in {model_2}: {len(comparison['unique_to_2'])}")
    
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
