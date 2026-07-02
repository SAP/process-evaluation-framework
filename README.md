[![REUSE status](https://api.reuse.software/badge/github.com/SAP/process-evaluation-framework)](https://api.reuse.software/info/github.com/SAP/process-evaluation-framework)

# process evaluation framework

## About this project

This repository provides a comprehensive framework for evaluating and comparing BPMN process models using semantic similarity metrics. In addition to structural similarity, we also report a trace similarity score.

**Evaluation Pipeline:**

1. **Load Models** - Import BPMN models from Signavio JSON format
2. **Convert** - Transform to minimal BPMN representation
3. **Normalize** - Align element names semantically using an embedding sentence transformer model (e.g., "Book flight" ↔ "Book a flight")
4. **Extract Traces** - Convert to Petri nets and extract execution traces/variants to analyze behavioral similarity
5. **Calculate Similarity** - Compute structural, flow, organizational, subprocess and trace similarity scores
6. **Visualize** - Interactive dashboard with adjustable weights and metrics (Dice, Jaccard, Precision, Recall, F1)

The framework supports pools, lanes, message flows, subprocesses, and provides detailed element-level breakdowns with configurable category weights.

## Using as a library

The evaluation logic is packaged as an importable Python library. Install the repo in editable mode from its root:

```
poetry install                         # core only — enough for structural + trace + hybrid similarity
poetry install --extras normalization  # adds semantic name alignment (pulls sentence-transformers / torch)
poetry install --extras dashboard      # adds the marimo dashboard + notebook deps
poetry install --all-extras            # everything
```

(Equivalent with pip: `pip install -e .`, `pip install -e '.[normalization]'`, `pip install -e '.[dashboard]'`.)

Then use the public API:

```python
from model_evaluation import (
    load_bpmn_xml, load_signavio_json,
    calculate_bpmn_similarity,
    calculate_trace_similarity, calculate_ngram_similarity,
    calculate_hybrid_similarity,
    extract_traces,
)

m1 = load_bpmn_xml("process1.bpmn")
m2 = load_bpmn_xml("process2.bpmn")

structural = calculate_bpmn_similarity(m1, m2, method="dice")
t1, t2 = extract_traces(m1), extract_traces(m2)
behavioral = calculate_trace_similarity(t1, t2, method="jaccard")
hybrid = calculate_hybrid_similarity(structural, behavioral, structural_weight=0.5)

print(f"structural={structural['overall']:.2f}  behavioral={behavioral:.2f}  hybrid={hybrid['hybrid']:.2f}")
```

`normalize_atomic_names` is available when the `normalization` extra is installed; calling it without the extra raises a clear `ImportError`.

**Input format.** All similarity and trace functions accept the same internal *minimal BPMN* dict: keys `activities`, `events`, `gateways`, `pools`, `sequenceFlows`, `messageFlows`. `load_bpmn_xml` / `load_signavio_json` produce this format from a file on disk; if you already have parsed XML / JSON in memory, use `XMLBPMNConverter.convert(xml_string).to_dict()` or `BPMNConverter.convert(parsed_dict).to_dict()` directly.

## Project Structure

```
model_evaluation/
├── utils/                      # Utility functions
│   ├── string_similarity.py    # BERT-based semantic similarity
│   └── list_similarity.py      # Set comparison metrics (Dice, Jaccard, etc.)
├── bpmn_conversion.py          # Signavio JSON and XML 2.0 → minimal BPMN converter
├── bpmn_normalization.py       # Semantic name alignment
├── bpmn_sets.py                # Element set extraction
├── bpmn_similarity.py          # Similarity calculation engine
├── json_to_pn.py               # Minimal JSON to Flow Structure
├── petri.py                    # Petri net
├── trace_extraction.py         # Trace/variant extraction via Petri nets
├── sapsam_mapping.py           # SAP-specific mappings


notebooks/
├── dashboard.py                # Interactive similarity dashboard (marimo)
└── model_eval_code_usage.ipynb # Usage examples and demonstrations

examples/                       # Sample BPMN models for testing
```

## Running the dashboard

The interactive similarity dashboard is a [marimo](https://marimo.io) notebook. Launch it from the repo root:

```
poetry run marimo edit notebooks/dashboard.py
```

It bundles the structural, behavioral (with n-gram subpanel), and hybrid sections into one reactive view. Use `marimo run` instead of `edit` for a read-only app view.

## Known limitations

- **Attached (boundary) events** on BPMN activities are not currently handled by the Petri-net trace extraction; models that rely on them may not fully reflect their behavioral variants.

## Requirements and Setup

*Insert a short description what is required to get your project running...*

## Support, Feedback, Contributing

This project is open to feature requests/suggestions, bug reports etc. via [GitHub issues](https://github.com/SAP/process-evaluation-framework/issues). Contribution and feedback are encouraged and always welcome. For more information about how to contribute, the project structure, as well as additional contribution information, see our [Contribution Guidelines](CONTRIBUTING.md).

## Security / Disclosure
If you find any bug that may be a security problem, please follow our instructions at [in our security policy](https://github.com/SAP/process-evaluation-framework/security/policy) on how to report it. Please do not create GitHub issues for security-related doubts or problems.

## Code of Conduct

We as members, contributors, and leaders pledge to make participation in our community a harassment-free experience for everyone. By participating in this project, you agree to abide by its [Code of Conduct](https://github.com/SAP/.github/blob/main/CODE_OF_CONDUCT.md) at all times.

## Licensing

Copyright 2025 SAP SE or an SAP affiliate company and process-evaluation-framework contributors. Please see our [LICENSE](LICENSE) for copyright and license information. Detailed information including third-party components and their licensing/copyright information is available [via the REUSE tool](https://api.reuse.software/info/github.com/SAP/process-evaluation-framework).
