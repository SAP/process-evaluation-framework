"""Truth-table tests for the set-similarity primitives.

These four functions in ``utils/list_similarity.py`` are the mathematical
bedrock of the framework: every jaccard / dice / overlap /
precision / recall / F1 number reported by the paper flows through them.
A single-character regression in any of these would silently corrupt
every downstream score without the maturity suite catching it (the
maturity suite only asserts bounds ``0 <= x <= 1``, never the exact
values). This file pins:

  * The value on a hand-computed truth table of 7 canonical set pairs
    (identical, disjoint, subset, one-element overlap, both-empty,
    one-empty in each direction).
  * The tuple shape ``(score, weight)`` returned by each helper.
  * The invariants ``jaccard <= dice <= overlap`` (for non-empty sets)
    and ``precision(A, B) == recall(B, A)``.
  * The edge-case conventions for empty inputs — see docstrings inline;
    ``dice`` / ``jaccard`` return ``(1, 0)`` for both-empty (the "two
    empty sets are perfectly equal" convention) and ``(0, 0.0)`` when
    exactly one side is empty; ``overlap`` follows the same convention;
    ``scores`` uses ``0`` for every empty edge (precision / recall /
    F1 all guard against division by zero by returning ``0``).

Values were computed against the source functions once and pinned here;
any change to the helpers must go through this file first.
"""

import pytest

from utils.list_similarity import (
    dice_list,
    index_list,
    jaccard_list,
    overlap_list,
    scores,
)


# ---------------------------------------------------------------------------
# Canonical set pairs shared by every parametrized test below.
# ---------------------------------------------------------------------------
# Named so failures point at the case immediately.
IDENTICAL = (["a", "b", "c"], ["a", "b", "c"])
DISJOINT = (["a", "b", "c"], ["x", "y", "z"])
SUBSET = (["a", "b", "c"], ["a", "b"])           # set2 is a subset of set1
ONE_OVERLAP = (["a", "b", "c"], ["c", "d", "e"]) # exactly one common element
BOTH_EMPTY = ([], [])
LEFT_EMPTY = ([], ["a", "b", "c"])
RIGHT_EMPTY = (["a", "b", "c"], [])


# ---------------------------------------------------------------------------
# index_list — the disambiguation pass that turns a multiset into a set-safe
# list by appending an occurrence index. Downstream similarity helpers all
# ``set(...)`` their inputs, so duplicates need distinct labels to survive.
# ---------------------------------------------------------------------------

def test_index_list_disambiguates_repeats():
    assert index_list(["a", "b", "c", "c", "d", "b"]) == [
        "a1", "b1", "c1", "c2", "d1", "b2",
    ]


def test_index_list_all_same_gets_serialized_1_2_3():
    assert index_list(["x", "x", "x"]) == ["x1", "x2", "x3"]


def test_index_list_empty_returns_empty():
    assert index_list([]) == []


def test_index_list_no_duplicates_still_indexed_from_1():
    # Even without duplicates every item gets its "1" suffix — this is the
    # invariant the similarity helpers depend on.
    assert index_list(["a", "b", "c"]) == ["a1", "b1", "c1"]


# ---------------------------------------------------------------------------
# dice_list — 2 * |A ∩ B| / (|A| + |B|)
# ---------------------------------------------------------------------------
# Truth table computed against the reference implementation and pinned here.

@pytest.mark.parametrize(
    "a, b, expected_score",
    [
        (*IDENTICAL, 1.0),
        (*DISJOINT, 0.0),
        (*SUBSET, 0.8),                        # 2*2 / (3+2)
        (*ONE_OVERLAP, 1.0 / 3.0),             # 2*1 / (3+3)
    ],
)
def test_dice_list_truth_table(a, b, expected_score):
    score, _weight = dice_list(a, b)
    assert score == pytest.approx(expected_score)


def test_dice_list_both_empty_returns_one_with_zero_weight():
    """Convention: two empty sets are "perfectly equal". The (1, 0) return
    lets callers detect the degenerate case via the zero weight without
    special-casing the score."""
    assert dice_list([], []) == (1, 0)


def test_dice_list_one_side_empty_returns_zero_zero():
    # Intersection is empty, weight-normalization also collapses to 0.
    assert dice_list(*LEFT_EMPTY) == (0.0, 0.0)
    assert dice_list(*RIGHT_EMPTY) == (0.0, 0.0)


def test_dice_list_is_symmetric():
    a, b = ONE_OVERLAP
    assert dice_list(a, b)[0] == pytest.approx(dice_list(b, a)[0])


def test_dice_list_ignores_duplicate_elements():
    """dice_list deliberately set-ifies its inputs — duplicates carry no
    weight. Callers that need multiset semantics must ``index_list`` first."""
    plain, _ = dice_list(["a", "b"], ["a", "b"])
    dup, _ = dice_list(["a", "a", "b"], ["a", "b", "b"])
    assert plain == dup == 1.0


# ---------------------------------------------------------------------------
# jaccard_list — |A ∩ B| / |A ∪ B|
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, b, expected_score",
    [
        (*IDENTICAL, 1.0),
        (*DISJOINT, 0.0),
        (*SUBSET, 2.0 / 3.0),                  # 2 / (3+2-2)
        (*ONE_OVERLAP, 0.2),                   # 1 / (3+3-1)
    ],
)
def test_jaccard_list_truth_table(a, b, expected_score):
    score, _weight = jaccard_list(a, b)
    assert score == pytest.approx(expected_score)


def test_jaccard_list_both_empty_returns_one_with_zero_weight():
    assert jaccard_list([], []) == (1, 0)


def test_jaccard_list_one_side_empty_returns_zero_zero():
    assert jaccard_list(*LEFT_EMPTY) == (0.0, 0.0)
    assert jaccard_list(*RIGHT_EMPTY) == (0.0, 0.0)


def test_jaccard_list_is_symmetric():
    a, b = ONE_OVERLAP
    assert jaccard_list(a, b)[0] == pytest.approx(jaccard_list(b, a)[0])


# ---------------------------------------------------------------------------
# overlap_list — |A ∩ B| / min(|A|, |B|)   (Szymkiewicz–Simpson coefficient)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, b, expected_score",
    [
        (*IDENTICAL, 1.0),
        (*DISJOINT, 0.0),
        (*SUBSET, 1.0),                        # 2 / min(3,2) — subset ⇒ 1.0
        (*ONE_OVERLAP, 1.0 / 3.0),             # 1 / min(3,3)
    ],
)
def test_overlap_list_truth_table(a, b, expected_score):
    score, _weight = overlap_list(a, b)
    assert score == pytest.approx(expected_score)


def test_overlap_list_subset_scores_perfectly_by_definition():
    """A key differentiator vs Jaccard/Dice: overlap treats a strict subset
    as identical (min-size normalisation). This is a load-bearing property
    of the metric that reviewers may ask about; pin it explicitly."""
    subset_score, _ = overlap_list(*SUBSET)
    assert subset_score == 1.0


def test_overlap_list_both_empty_returns_one_zero():
    # Same "two empty sets are equal" convention as dice/jaccard, expressed
    # via the ``len(set1) == len(set2)`` guard in the source.
    assert overlap_list([], []) == (1, 0)


def test_overlap_list_one_side_empty_returns_zero_zero():
    assert overlap_list(*LEFT_EMPTY) == (0, 0)
    assert overlap_list(*RIGHT_EMPTY) == (0, 0)


def test_overlap_list_is_symmetric():
    a, b = ONE_OVERLAP
    assert overlap_list(a, b)[0] == pytest.approx(overlap_list(b, a)[0])


# ---------------------------------------------------------------------------
# scores — precision / recall / F1 (asymmetric: list_1 is ground truth)
# ---------------------------------------------------------------------------
# Precision = |A ∩ B| / |B|,   Recall = |A ∩ B| / |A|,
# F1 = 2·P·R / (P + R)
# The docstring names list_1 the ground truth, so precision measures
# "how many of B's elements are correct" and recall "how many of A's
# elements were retrieved".

@pytest.mark.parametrize(
    "a, b, prec, rec, f1",
    [
        (*IDENTICAL, 1.0, 1.0, 1.0),
        (*DISJOINT, 0.0, 0.0, 0),              # f1 short-circuits to 0
        (*SUBSET, 1.0, 2.0 / 3.0, 0.8),        # every b∈B is in A; A has one extra
        (*ONE_OVERLAP, 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
    ],
)
def test_scores_truth_table(a, b, prec, rec, f1):
    p, _ = scores(a, b, "precision")
    r, _ = scores(a, b, "recall")
    f, _ = scores(a, b, "f1")
    assert p == pytest.approx(prec)
    assert r == pytest.approx(rec)
    assert f == pytest.approx(f1)


def test_scores_precision_of_ab_equals_recall_of_ba():
    """The load-bearing identity: swapping ground-truth and prediction
    turns precision into recall. Every asymmetric-metric user relies on
    this; if it breaks, every downstream number that used ``precision``
    is silently wrong."""
    a, b = ONE_OVERLAP
    p_ab, _ = scores(a, b, "precision")
    r_ba, _ = scores(b, a, "recall")
    assert p_ab == pytest.approx(r_ba)


def test_scores_both_empty_returns_zero_zero():
    """Division-by-zero guard: when either set is empty the fraction is
    undefined; the code returns 0 rather than 1 (unlike dice/jaccard).
    This asymmetric behaviour is intentional — precision/recall are
    retrieval metrics; there's no "correct" answer to precision-of-nothing.
    Callers wanting the empty-vs-empty = 1 convention should use
    dice/jaccard/overlap instead."""
    assert scores([], [], "precision") == (0, 0)
    assert scores([], [], "recall") == (0, 0)
    assert scores([], [], "f1") == (0, 0)


def test_scores_f1_is_zero_when_precision_plus_recall_is_zero():
    """Explicit guard in the source; pin so a refactor can't remove it
    and hand back a NaN or ZeroDivisionError."""
    f, _ = scores(*DISJOINT, "f1")
    assert f == 0


def test_scores_rejects_unknown_type():
    with pytest.raises(ValueError, match="Invalid score type"):
        scores(["a"], ["a"], score_type="banana")


# ---------------------------------------------------------------------------
# Cross-metric invariants — hold for any non-empty pair with a defined score.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [IDENTICAL, DISJOINT, SUBSET, ONE_OVERLAP])
def test_jaccard_le_dice_le_overlap_for_nonempty_sets(a, b):
    """For any two non-empty sets: J(A,B) <= D(A,B) <= O(A,B). This is a
    textbook property of the three metrics; if the code ever violates it,
    one of the formulas has been mangled."""
    j, _ = jaccard_list(a, b)
    d, _ = dice_list(a, b)
    o, _ = overlap_list(a, b)
    assert j <= d + 1e-12
    assert d <= o + 1e-12


@pytest.mark.parametrize("a, b", [IDENTICAL, DISJOINT, SUBSET, ONE_OVERLAP])
def test_dice_equals_f1_for_symmetric_case(a, b):
    """Well-known identity: Dice coefficient over two sets equals the F1
    score when precision and recall are computed set-wise. Pinning this
    lets a refactorer discover if either implementation drifts."""
    d, _ = dice_list(a, b)
    f, _ = scores(a, b, "f1")
    assert d == pytest.approx(f)


@pytest.mark.parametrize(
    "a, b",
    [IDENTICAL, DISJOINT, SUBSET, ONE_OVERLAP],
)
def test_self_similarity_is_one(a, b):
    """Any of the four metrics against itself on a non-empty set must be
    exactly 1.0 — the identity floor. If this drifts, comparisons of a
    model to itself will stop returning 1.0 and every downstream
    identical-baseline test starts to look suspicious."""
    for helper in (dice_list, jaccard_list, overlap_list):
        assert helper(a, a)[0] == 1.0
    assert scores(a, a, "precision")[0] == 1.0
    assert scores(a, a, "recall")[0] == 1.0
    assert scores(a, a, "f1")[0] == 1.0
