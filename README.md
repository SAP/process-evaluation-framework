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

## Project Structure

```
model_evaluation/
├── utils/                      # Utility functions
│   ├── string_similarity.py    # BERT-based semantic similarity
│   └── list_similarity.py      # Set comparison metrics (Dice, Jaccard, etc.)
├── rendering/                  # Visualization modules
│   ├── bpmn_viewer.py          # BPMN XML viewer using bpmn-js
│   └── dashboard.py            # Interactive similarity dashboard
├── BPMN_conversion.py          # Signavio JSON → minimal BPMN converter
├── bpmn_normalization.py       # Semantic name alignment
├── bpmn_sets.py                # Element set extraction
├── bpmn_similarity.py          # Similarity calculation engine
├── bpmn_schema.py              # Data structures and validation
├── json_to_pn.py               # Minimal JSON to Flow Structure
├── petri.py                    # Petri net
├── trace_extraction.py         # Trace/variant extraction via Petri nets
├── sapsam_mapping.py           # SAP-specific mappings
└── XML_conversion.py           # BPMN XML 2.0 → minimal BPMN converter

notebooks/
└── model_eval_code_usage.ipynb # Usage examples and demonstrations

examples/                       # Sample BPMN models for testing
```

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
