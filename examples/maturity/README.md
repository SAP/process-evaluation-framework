# Maturity Suite

This folder is the evidence base for the **maturity** section of the
demo paper. It pairs a small, browseable corpus of BPMN models with a
pytest-driven test suite that exercises the framework against
specific, named behaviors — so reviewers can spot-check the claim that
"the tool behaves as advertised" without re-running the dashboard.

**Layout** — one folder per behavior; one runnable test file per folder
(under `tests/maturity/`).

```
sanity/                      identical / disjoint / renamed-only
gateway_substitutions/       AND vs XOR vs OR (matched triplet)
structural_perturbations/    reorder / branch added / drift
semantic_naming/             paraphrase / synonym (relies on the normalizer)
subprocess_folding/          flat vs expanded subprocess
format_round_trip/           BPMN XML vs Signavio JSON
degenerate/                  empty, single-task, unsound nets
```

**Run everything** (from repo root):

```bash
poetry run pytest tests/maturity/                              # full correctness suite
poetry run jupyter notebook notebooks/maturity_report.ipynb    # interactive report
```

The notebook `notebooks/maturity_report.ipynb` dumps every edge-case
pair's actual sub-scores — useful for threshold calibration and for
quoting the right numbers in prose. The fixtures themselves are
plain BPMN files, edited directly under each folder.

---

## Categories

### 1. Sanity & boundary — `sanity/`

Three pairs proving the score lives in `[0, 1]` and reacts to the
obvious cases.

| File pair | Expected behavior | Test |
|---|---|---|
| `identical_baseline.bpmn` × self | All sub-scores ≥ 0.95; aggregated near 1.0. | `test_identical_model_scores_near_one` |
| `disjoint_left_credit.bpmn` × `disjoint_right_student.bpmn` | Aggregated ≤ 0.15 — a credit-approval process versus a student-enrollment process; no shared vocabulary, no shared structure. | `test_disjoint_models_score_low` |
| `identical_baseline.bpmn` × `renamed_only_b.bpmn` | Same 3-task linear shape, different label strings. Raw similarity is modest (~0.28); after `normalize_atomic_names` aligns the vocabularies, the score lifts to ~1.0. This is *the* canonical maturity claim of the tool. | `test_renamed_only_pair_recovers_under_normalization` |

`identical_baseline.bpmn`, `semantic_naming/paraphrase_a.bpmn`, and
`semantic_naming/synonym_a.bpmn` all share the same canonical 3-task
model (`Book flight → Pay → Confirm`) so every `_b` variant can be
diffed against a single reference. The rename pair (above) reuses
`identical_baseline.bpmn` as its A side — there is no separate
`renamed_only_a.bpmn`.

### 2. Gateway substitutions — `gateway_substitutions/`

A matched triplet: same four activities (`Receive Customer Order`,
`Prepare Order`, `Prepare Invoice`, `Ship Order with Invoice`), same
start/split/join/end skeleton — only the gateway type at the split and
join differs.

| File | Gateway type |
|---|---|
| `gateway_and.bpmn` | parallelGateway (AND) split + AND join |
| `gateway_xor.bpmn` | exclusiveGateway (XOR) split + XOR join |
| `gateway_or.bpmn`  | inclusiveGateway (OR) split + OR join |

Expected: self-similarity is exactly 1.0; cross-pair overall lands
in `[0.3, 0.9]` (measured 0.406 for all three pairs — same activities
and edges, only the gateway type disagrees); cross-pair trace
similarity is at-or-below self (AND vs {XOR, OR} = 0.000 because AND
demands both branches fire; XOR vs OR can legitimately equal 1.000
under the activity-set trace projection); OR yields ≥ 1 variant.

Tests: `test_gateway_model_self_similarity_is_one`,
`test_cross_gateway_pair_in_shared_domain_band`,
`test_cross_gateway_trace_strictly_below_self`,
`test_gateway_model_has_at_least_one_variant`.

### 3. Structural perturbations — `structural_perturbations/`

Linear-sequence and parallel-AND perturbation series, all sharing one
vocabulary so the test isolates structure from naming.

The linear series uses the same four tasks across all three fixtures —
`receive order`, `validate order`, `approve order`, `dispatch order` —
varying only the flow:

- `linear_baseline.bpmn`: canonical sequence.
- `linear_reorder.bpmn`: `validate` ↔ `approve` swapped in execution
  order. Same tasks, same edges-count, only target refs differ.
- `linear_drift.bpmn`: composes the reorder swap with a rework
  back-edge from `approve order` through an exclusive decision
  gateway back to `validate order` — strictly more perturbed than
  reorder alone.

The AND series:

- `and_two_branches.bpmn`: parallel split → {Task A, Task B} → join.
- `and_three_branches.bpmn`: clean superset — adds Task C as a third
  parallel branch with a 3-way `parallelGateway` join so the model
  stays sound. (The `degenerate/` folder covers the unsound-AND case.)

| File pair | Expected behavior | Test |
|---|---|---|
| `linear_baseline` × `linear_reorder` | Reordered sequence scores strictly below either self-pair. | `test_linear_baseline_vs_reorder_drops_below_self` |
| `linear_baseline` × `linear_drift` | More-perturbed variant scores strictly below the nearer-perturbation pair. | `test_perturbation_ranking_monotone_under_drift` |
| `and_two_branches` × `and_three_branches` | Adding a parallel branch lowers the aggregated score and changes the trace set. | `test_branch_added_lowers_score`, `test_branch_added_changes_trace_behavior` |

### 4. Semantic naming — `semantic_naming/`

Two pairs sharing the same `Book flight → Pay → Confirm` shape with
label variations.

| File pair | Label drift |
|---|---|
| `paraphrase_a.bpmn` × `paraphrase_b.bpmn` | Minor wording (`Pay` → `Make a payment`) |
| `synonym_a.bpmn` × `synonym_b.bpmn` | Domain synonyms (`Book flight` → `Reserve airline ticket`) |

Expected: **raw** similarity (no normalization) is modest because the
literal label strings disagree; after the embedding-driven
`normalize_atomic_names` step, both pairs score at least 0.6 above the
disjoint baseline (measured margin: ~0.9). Paraphrase is asserted to
rank at-or-above synonym. Relative assertions are used throughout to
stay robust against embedding-model drift.

Tests: `test_paraphrase_pair_normalizes_higher_than_raw`,
`test_paraphrase_pair_normalizes_above_disjoint_baseline`,
`test_synonym_pair_normalizes_higher_than_raw`,
`test_synonym_pair_normalizes_above_disjoint_baseline`,
`test_paraphrase_ranks_at_or_above_synonym`.

### 5. Subprocess folding — `subprocess_folding/`

Two models share the same five task labels (Pick, Pack, Label, Load,
Dispatch). In `flat.bpmn` they are inline; in
`with_subprocess.bpmn` the middle three are nested inside an expanded
subprocess.

Expected: overall lands in `[0.4, 0.8]` — never 1.0 (the subprocess
side has extra structural elements) and never near 0 (the activity-name
sets overlap). The `elements` sub-score stays high (≥ 0.7). The
structural pipeline correctly detects the expanded subprocess
(`has_expanded_subprocess` is `True`). Trace comparison runs without
raising or producing NaN/Inf.

Tests: `test_flat_vs_subprocess_overall_in_mid_band`,
`test_flat_vs_subprocess_elements_score_remains_high`,
`test_flat_vs_subprocess_scores_above_disjoint_baseline`,
`test_flat_vs_subprocess_trace_extraction_finite`,
`test_subprocess_model_has_expanded_subprocess_flag`.

### 6. Format round-trip — `format_round_trip/`

Each model exists as both BPMN XML and Signavio JSON. The two are NOT
byte-identical (JSON carries Signavio diagram metadata), but after
both converters land in the common dict shape the structural score
should be ~1.0. Calibrated floor: ≥ 0.99 (measured: 1.000 for both
pairs).

Tests: `test_bpmn_vs_json_round_trip_is_high[linear_sequence]`,
`test_bpmn_vs_json_round_trip_is_high[credit]`.

### 7. Degenerate inputs — `degenerate/`

Gracefulness, not magnitude. The pipeline must produce a finite,
in-range number and never raise.

| Fixture | What it tests |
|---|---|
| `empty.bpmn` (just `start → end`) | Empty-vs-empty returns a finite score; the `None` convention for "nothing to compare" is also accepted. |
| `single_task.bpmn` | Trivial baseline; self-comparison returns 1.0 exactly. |
| `unsound_and_no_join.bpmn` × `sound_and_with_join.bpmn` | An AND-split with no join deadlocks at the Petri-net level. The similarity layer must still return a finite score and the trace extractor must not raise (see also `tests/test_graceful_unsound_petri.py`). |

Tests: `test_empty_model_self_comparison_is_finite_and_safe`,
`test_single_task_model_self_comparison_is_perfect`,
`test_empty_vs_single_task_returns_finite_score`,
`test_unsound_vs_sound_returns_finite_score`.

---

## Limitations

We have not yet validated similarity scores against human-judged
similarity ratings. The thresholds in this suite are calibrated to the
observed distribution of the current converter, normalizer, and
embedding model; correlation with expert judgments of "how similar"
two business processes are is left for future work, alongside a larger
public-corpus quantitative analysis.
