"""Utility modules for BPMN similarity calculations.

``cosine_sim_optimized`` lives in :mod:`.string_similarity`, which imports
``sentence_transformers`` and instantiates a model at load time. That
dependency is optional (behind the ``[normalization]`` extra), so we resolve
the symbol lazily on first access instead of eagerly re-exporting it here.
This keeps the core install (``pip install -e .``) importable without
``sentence-transformers`` / ``torch``.
"""

from .list_similarity import dice_list, index_list, jaccard_list, overlap_list, scores

__all__ = [
    "cosine_sim_optimized",
    "dice_list",
    "index_list",
    "jaccard_list",
    "overlap_list",
    "scores",
]


def __getattr__(name):
    if name == "cosine_sim_optimized":
        from .string_similarity import cosine_sim_optimized as _fn
        return _fn
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
