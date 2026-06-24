"""Semantic-naming pairs — paraphrase and synonym variations.

Two pairs (under ``examples/maturity/semantic_naming/``):

- ``paraphrase_a.bpmn`` / ``paraphrase_b.bpmn`` — same 3-task linear
  shape; the second uses minor wording variations (``Book flight`` →
  ``Book a flight``, ``Pay`` → ``Make a payment``, ``Confirm`` →
  ``Confirm booking``).
- ``synonym_a.bpmn`` / ``synonym_b.bpmn`` — same shape; the second uses
  domain synonyms (``Book flight`` → ``Reserve airline ticket``,
  ``Pay`` → ``Process payment``, ``Confirm`` → ``Acknowledge``).

Two assertions per pair:

1. **Raw** (no normalization) score should be modest — different label
   strings mean different activity-name sets. This is just a sanity
   check that the test is exercising what we think it is.
2. **Normalized** (``normalize_atomic_names`` first, then
   ``calculate_bpmn_similarity``) score should be substantially higher,
   and at least as high as the disjoint-pair baseline by a clear margin.

Relative assertions (paraphrase ≥ synonym ≥ disjoint after normalization)
mirror the recommendation in the plan: more robust than pinning an
absolute floor on an embedding-driven score.
"""

import pytest

from bpmn_normalization import normalize_atomic_names
from bpmn_similarity import calculate_bpmn_similarity
from utils.string_similarity import cosine_sim_optimized

from .conftest import SANITY, SEMANTIC_NAMING, _load


# Threshold used by the dashboard's default normalization slider.
_THRESHOLD = 0.7


def _raw_overall(a, b):
    return calculate_bpmn_similarity(a, b, method="dice")["overall"]


def _normalized_overall(a, b):
    aligned, _ = normalize_atomic_names(a, b, cosine_sim_optimized, threshold=_THRESHOLD)
    return calculate_bpmn_similarity(a, aligned, method="dice")["overall"]


@pytest.fixture(scope="module")
def disjoint_baseline_overall(embedding_model):
    """Disjoint-pair normalized overall — a ceiling we expect to clear."""
    a = _load(SANITY / "disjoint_left_credit.bpmn")
    b = _load(SANITY / "disjoint_right_student.bpmn")
    return _normalized_overall(a, b)


def test_paraphrase_pair_normalizes_higher_than_raw(embedding_model):
    a = _load(SEMANTIC_NAMING / "paraphrase_a.bpmn")
    b = _load(SEMANTIC_NAMING / "paraphrase_b.bpmn")
    raw = _raw_overall(a, b)
    norm = _normalized_overall(a, b)
    assert norm > raw, (
        f"paraphrase: normalization should improve the score "
        f"(raw={raw:.3f}, normalized={norm:.3f})"
    )


def test_paraphrase_pair_normalizes_above_disjoint_baseline(
    embedding_model, disjoint_baseline_overall
):
    a = _load(SEMANTIC_NAMING / "paraphrase_a.bpmn")
    b = _load(SEMANTIC_NAMING / "paraphrase_b.bpmn")
    norm = _normalized_overall(a, b)
    assert norm >= disjoint_baseline_overall + 0.3, (
        f"paraphrase normalized={norm:.3f} should exceed disjoint baseline "
        f"({disjoint_baseline_overall:.3f}) by ≥0.3"
    )


def test_synonym_pair_normalizes_higher_than_raw(embedding_model):
    a = _load(SEMANTIC_NAMING / "synonym_a.bpmn")
    b = _load(SEMANTIC_NAMING / "synonym_b.bpmn")
    raw = _raw_overall(a, b)
    norm = _normalized_overall(a, b)
    assert norm > raw, (
        f"synonym: normalization should improve the score "
        f"(raw={raw:.3f}, normalized={norm:.3f})"
    )


def test_synonym_pair_normalizes_above_disjoint_baseline(
    embedding_model, disjoint_baseline_overall
):
    a = _load(SEMANTIC_NAMING / "synonym_a.bpmn")
    b = _load(SEMANTIC_NAMING / "synonym_b.bpmn")
    norm = _normalized_overall(a, b)
    assert norm >= disjoint_baseline_overall + 0.3, (
        f"synonym normalized={norm:.3f} should exceed disjoint baseline "
        f"({disjoint_baseline_overall:.3f}) by ≥0.3"
    )


def test_paraphrase_ranks_at_or_above_synonym(embedding_model):
    """Paraphrases (closer wording) should not score below synonyms.

    Asserts ≥ (not strictly >) because the embedding model is allowed to
    tie the two. Plan called this out: relative assertions are robust;
    absolute pinning would be brittle.
    """
    pa = _load(SEMANTIC_NAMING / "paraphrase_a.bpmn")
    pb = _load(SEMANTIC_NAMING / "paraphrase_b.bpmn")
    sa = _load(SEMANTIC_NAMING / "synonym_a.bpmn")
    sb = _load(SEMANTIC_NAMING / "synonym_b.bpmn")

    paraphrase = _normalized_overall(pa, pb)
    synonym = _normalized_overall(sa, sb)
    assert paraphrase >= synonym - 0.01, (
        f"paraphrase ({paraphrase:.3f}) should be ≥ synonym ({synonym:.3f})"
    )
