"""Generate the small hand-authored fixtures the maturity suite needs.

Output layout (under ``examples/maturity/``):

- ``sanity/renamed_only_a.bpmn`` / ``renamed_only_b.bpmn`` — same 3-task
  linear shape, second uses paraphrased labels. Pair tests whether
  semantic-naming normalization can keep the aggregated score high.
- ``semantic_naming/paraphrase_a.bpmn`` / ``paraphrase_b.bpmn`` — very
  small label variations of the same flow.
- ``semantic_naming/synonym_a.bpmn`` / ``synonym_b.bpmn`` — same shape,
  domain-specific synonyms.
- ``degenerate/empty.bpmn`` — start → end, no tasks.
- ``degenerate/single_task.bpmn`` — start → 1 task → end.
- ``subprocess_folding/flat.bpmn`` — 5 sequential tasks.
- ``subprocess_folding/with_subprocess.bpmn`` — 2 outer tasks wrapping a
  3-task subprocess; total task labels match ``flat.bpmn``.

Every file ships a full ``<bpmndi:BPMNDiagram>`` block so it renders in
the dashboard. Coordinates are simple left-to-right grids.

Run from repo root::

    poetry run python scripts/maturity/generate_small_models.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MATURITY = REPO_ROOT / "examples" / "maturity"


# ---------------------------------------------------------------------------
# Layout constants — matched against the hand-authored fixtures in
# examples/ (event 36×36, task 100×80) so styling stays consistent.
# ---------------------------------------------------------------------------

EVENT_W, EVENT_H = 36, 36
TASK_W, TASK_H = 100, 80
SUBPROCESS_PAD_X = 40
SUBPROCESS_PAD_Y = 60
STEP_X = 140
AXIS_Y = 200


# ---------------------------------------------------------------------------
# XML emission helpers (intentionally duplicated from
# generate_scalability_models.py rather than imported — both scripts are
# tiny and self-contained, so a future edit to one shouldn't affect the
# other).
# ---------------------------------------------------------------------------

_HEADER = dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
                 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                 xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                 xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 id="Definitions_1"
                 targetNamespace="http://example.org/bpmn/maturity"
                 exporter="generate_small_models.py"
                 exporterVersion="1.0">
    """
)

_FOOTER = "</definitions>\n"


def _start(node_id: str, outgoing: str) -> str:
    return (
        f'    <startEvent id="{node_id}" name="Start">\n'
        f"      <outgoing>{outgoing}</outgoing>\n"
        f"    </startEvent>\n"
    )


def _end(node_id: str, incoming: str) -> str:
    return (
        f'    <endEvent id="{node_id}" name="End">\n'
        f"      <incoming>{incoming}</incoming>\n"
        f"    </endEvent>\n"
    )


def _task(node_id: str, name: str, incoming: str, outgoing: str, *, indent: int = 4) -> str:
    pad = " " * indent
    return (
        f'{pad}<task id="{node_id}" name="{name}">\n'
        f"{pad}  <incoming>{incoming}</incoming>\n"
        f"{pad}  <outgoing>{outgoing}</outgoing>\n"
        f"{pad}</task>\n"
    )


def _flow(flow_id: str, src: str, tgt: str, *, indent: int = 4) -> str:
    pad = " " * indent
    return f'{pad}<sequenceFlow id="{flow_id}" sourceRef="{src}" targetRef="{tgt}"/>\n'


def _shape(node_id: str, x: int, y: int, w: int, h: int) -> str:
    return (
        f'      <bpmndi:BPMNShape id="shape_{node_id}" bpmnElement="{node_id}">\n'
        f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}"/>\n'
        f"      </bpmndi:BPMNShape>\n"
    )


def _edge(flow_id: str, waypoints: list[tuple[int, int]]) -> str:
    wp = "\n".join(f'        <di:waypoint x="{x}" y="{y}"/>' for x, y in waypoints)
    return (
        f'      <bpmndi:BPMNEdge id="edge_{flow_id}" bpmnElement="{flow_id}">\n'
        f"{wp}\n"
        f"      </bpmndi:BPMNEdge>\n"
    )


def _diagram(process_id: str, shapes: str, edges: str) -> str:
    return (
        '  <bpmndi:BPMNDiagram id="BPMNDiagram_1">\n'
        f'    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{process_id}">\n'
        f"{shapes}{edges}"
        "    </bpmndi:BPMNPlane>\n"
        "  </bpmndi:BPMNDiagram>\n"
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_linear_with_labels(process_id: str, process_name: str, labels: Iterable[str]) -> str:
    """``start → task_1 → ... → task_n → end`` with caller-supplied labels.

    Used for the renamed-only, paraphrase, and synonym pairs.
    """
    labels = list(labels)
    n = len(labels)

    body: list[str] = [_HEADER, f'  <process id="{process_id}" name="{process_name}" isExecutable="true">\n']
    flow_ids = [f"flow_{i}" for i in range(n + 1)]
    body.append(_start("start", flow_ids[0]))
    for i, label in enumerate(labels, start=1):
        body.append(_task(f"task_{i}", label, flow_ids[i - 1], flow_ids[i]))
    body.append(_end("end", flow_ids[-1]))
    body.append(_flow(flow_ids[0], "start", "task_1"))
    for i in range(1, n):
        body.append(_flow(flow_ids[i], f"task_{i}", f"task_{i + 1}"))
    body.append(_flow(flow_ids[n], f"task_{n}", "end"))
    body.append("  </process>\n")

    # --- diagram ---
    event_y = AXIS_Y - EVENT_H // 2
    task_y = AXIS_Y - TASK_H // 2
    start_x = 100
    task_xs = [start_x + STEP_X * (i + 1) - (TASK_W - EVENT_W) // 2 for i in range(n)]
    end_x = task_xs[-1] + TASK_W + STEP_X // 2

    shapes = [_shape("start", start_x, event_y, EVENT_W, EVENT_H)]
    for i, x in enumerate(task_xs, start=1):
        shapes.append(_shape(f"task_{i}", x, task_y, TASK_W, TASK_H))
    shapes.append(_shape("end", end_x, event_y, EVENT_W, EVENT_H))

    edges = [_edge(flow_ids[0], [(start_x + EVENT_W, AXIS_Y), (task_xs[0], AXIS_Y)])]
    for i in range(1, n):
        edges.append(_edge(flow_ids[i], [(task_xs[i - 1] + TASK_W, AXIS_Y), (task_xs[i], AXIS_Y)]))
    edges.append(_edge(flow_ids[n], [(task_xs[-1] + TASK_W, AXIS_Y), (end_x, AXIS_Y)]))

    body.append(_diagram(process_id, "".join(shapes), "".join(edges)))
    body.append(_FOOTER)
    return "".join(body)


def build_empty(process_id: str) -> str:
    """A minimal valid BPMN: ``start → end`` with one sequence flow."""
    body: list[str] = [_HEADER, f'  <process id="{process_id}" name="Empty" isExecutable="true">\n']
    body.append(_start("start", "flow_se"))
    body.append(_end("end", "flow_se"))
    body.append(_flow("flow_se", "start", "end"))
    body.append("  </process>\n")

    event_y = AXIS_Y - EVENT_H // 2
    start_x = 100
    end_x = start_x + STEP_X
    shapes = "".join([
        _shape("start", start_x, event_y, EVENT_W, EVENT_H),
        _shape("end", end_x, event_y, EVENT_W, EVENT_H),
    ])
    edges = _edge("flow_se", [(start_x + EVENT_W, AXIS_Y), (end_x, AXIS_Y)])
    body.append(_diagram(process_id, shapes, edges))
    body.append(_FOOTER)
    return "".join(body)


def build_single_task(process_id: str) -> str:
    """``start → task → end`` — the smallest non-trivial linear flow."""
    return build_linear_with_labels(process_id, "Single Task", ["Do the thing"])


def build_subprocess_folded(process_id: str, outer_labels: tuple[str, str], inner_labels: tuple[str, str, str]) -> str:
    """``start → outer1 → subProcess(inner1, inner2, inner3) → outer2 → end``.

    The subprocess is expanded (its internals are explicit) so the
    structural-similarity pipeline can compare it against the flat
    counterpart that lists the same five labels inline.
    """
    o1, o2 = outer_labels
    i1, i2, i3 = inner_labels

    body: list[str] = [_HEADER, f'  <process id="{process_id}" name="With Subprocess" isExecutable="true">\n']
    # Top-level: start, outer_1, subprocess, outer_2, end.
    body.append(_start("start", "flow_0"))
    body.append(_task("outer_1", o1, "flow_0", "flow_1"))

    # Expanded subprocess.
    body.append('    <subProcess id="sp_1" name="Inner Subprocess">\n')
    body.append("      <incoming>flow_1</incoming>\n")
    body.append("      <outgoing>flow_2</outgoing>\n")
    body.append('      <startEvent id="sp_start">\n      <outgoing>sp_flow_0</outgoing>\n      </startEvent>\n')
    body.append(_task("inner_1", i1, "sp_flow_0", "sp_flow_1", indent=6))
    body.append(_task("inner_2", i2, "sp_flow_1", "sp_flow_2", indent=6))
    body.append(_task("inner_3", i3, "sp_flow_2", "sp_flow_3", indent=6))
    body.append('      <endEvent id="sp_end">\n      <incoming>sp_flow_3</incoming>\n      </endEvent>\n')
    body.append(_flow("sp_flow_0", "sp_start", "inner_1", indent=6))
    body.append(_flow("sp_flow_1", "inner_1", "inner_2", indent=6))
    body.append(_flow("sp_flow_2", "inner_2", "inner_3", indent=6))
    body.append(_flow("sp_flow_3", "inner_3", "sp_end", indent=6))
    body.append("    </subProcess>\n")

    body.append(_task("outer_2", o2, "flow_2", "flow_3"))
    body.append(_end("end", "flow_3"))
    body.append(_flow("flow_0", "start", "outer_1"))
    body.append(_flow("flow_1", "outer_1", "sp_1"))
    body.append(_flow("flow_2", "sp_1", "outer_2"))
    body.append(_flow("flow_3", "outer_2", "end"))
    body.append("  </process>\n")

    # --- diagram ---
    event_y = AXIS_Y - EVENT_H // 2
    task_y = AXIS_Y - TASK_H // 2

    start_x = 100
    outer1_x = start_x + STEP_X
    sp_x = outer1_x + TASK_W + STEP_X // 2
    sp_w = 3 * TASK_W + 2 * SUBPROCESS_PAD_X + 2 * SUBPROCESS_PAD_X
    sp_h = TASK_H + 2 * SUBPROCESS_PAD_Y
    sp_y = AXIS_Y - sp_h // 2
    outer2_x = sp_x + sp_w + STEP_X // 2
    end_x = outer2_x + TASK_W + STEP_X // 2

    # Inner shapes (relative to top-level coords; we draw them at their
    # absolute positions inside the same plane).
    inner_y = AXIS_Y - TASK_H // 2
    inner_xs = [
        sp_x + SUBPROCESS_PAD_X + i * (TASK_W + SUBPROCESS_PAD_X) for i in range(3)
    ]

    shape_parts = [
        _shape("start", start_x, event_y, EVENT_W, EVENT_H),
        _shape("outer_1", outer1_x, task_y, TASK_W, TASK_H),
        _shape("sp_1", sp_x, sp_y, sp_w, sp_h),
        _shape("inner_1", inner_xs[0], inner_y, TASK_W, TASK_H),
        _shape("inner_2", inner_xs[1], inner_y, TASK_W, TASK_H),
        _shape("inner_3", inner_xs[2], inner_y, TASK_W, TASK_H),
        _shape("outer_2", outer2_x, task_y, TASK_W, TASK_H),
        _shape("end", end_x, event_y, EVENT_W, EVENT_H),
    ]

    edge_parts = [
        _edge("flow_0", [(start_x + EVENT_W, AXIS_Y), (outer1_x, AXIS_Y)]),
        _edge("flow_1", [(outer1_x + TASK_W, AXIS_Y), (sp_x, AXIS_Y)]),
        _edge("flow_2", [(sp_x + sp_w, AXIS_Y), (outer2_x, AXIS_Y)]),
        _edge("flow_3", [(outer2_x + TASK_W, AXIS_Y), (end_x, AXIS_Y)]),
        _edge("sp_flow_0", [(inner_xs[0] - SUBPROCESS_PAD_X // 2, AXIS_Y), (inner_xs[0], AXIS_Y)]),
        _edge("sp_flow_1", [(inner_xs[0] + TASK_W, AXIS_Y), (inner_xs[1], AXIS_Y)]),
        _edge("sp_flow_2", [(inner_xs[1] + TASK_W, AXIS_Y), (inner_xs[2], AXIS_Y)]),
        _edge("sp_flow_3", [(inner_xs[2] + TASK_W, AXIS_Y), (inner_xs[2] + TASK_W + SUBPROCESS_PAD_X // 2, AXIS_Y)]),
    ]

    body.append(_diagram(process_id, "".join(shape_parts), "".join(edge_parts)))
    body.append(_FOOTER)
    return "".join(body)


# ---------------------------------------------------------------------------
# Manifest — name → (subfolder, builder, args)
# ---------------------------------------------------------------------------

# Label sets are intentionally small and book-flight-themed. The pairs:
#
#   renamed_only_a   / renamed_only_b   — exact-rename test (different
#       strings, identical semantics). Stresses the normalization step.
#   paraphrase_a     / paraphrase_b     — minor wording variation; the
#       normalizer should land them very close.
#   synonym_a        / synonym_b        — domain synonyms; harder than
#       paraphrase, easier than disjoint.
#
# Flat vs with_subprocess share the SAME five task labels (pick, pack,
# label, load, dispatch) so the trace-level / per-label sets are
# identical, the difference is purely structural (one subprocess).

LABELS_A = ("Book flight", "Pay", "Confirm")
LABELS_RENAMED_B = ("Reserve flight", "Make payment", "Send confirmation")
LABELS_PARAPHRASE_B = ("Book a flight", "Make a payment", "Confirm booking")
LABELS_SYNONYM_B = ("Reserve airline ticket", "Process payment", "Acknowledge")

FLAT_LABELS = ("Pick", "Pack", "Label", "Load", "Dispatch")
SP_OUTER = ("Pick", "Dispatch")
SP_INNER = ("Pack", "Label", "Load")


def emit_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def _w(subdir: str, name: str, content: str) -> None:
        sub = out_dir / subdir
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    _w("sanity", "renamed_only_a.bpmn",
       build_linear_with_labels("renamed_only_a", "Renamed Only A", LABELS_A))
    _w("sanity", "renamed_only_b.bpmn",
       build_linear_with_labels("renamed_only_b", "Renamed Only B", LABELS_RENAMED_B))

    _w("semantic_naming", "paraphrase_a.bpmn",
       build_linear_with_labels("paraphrase_a", "Paraphrase A", LABELS_A))
    _w("semantic_naming", "paraphrase_b.bpmn",
       build_linear_with_labels("paraphrase_b", "Paraphrase B", LABELS_PARAPHRASE_B))

    _w("semantic_naming", "synonym_a.bpmn",
       build_linear_with_labels("synonym_a", "Synonym A", LABELS_A))
    _w("semantic_naming", "synonym_b.bpmn",
       build_linear_with_labels("synonym_b", "Synonym B", LABELS_SYNONYM_B))

    _w("degenerate", "empty.bpmn", build_empty("empty_model"))
    _w("degenerate", "single_task.bpmn", build_single_task("single_task"))

    _w("subprocess_folding", "flat.bpmn",
       build_linear_with_labels("flat_dispatch", "Flat Dispatch", FLAT_LABELS))
    _w("subprocess_folding", "with_subprocess.bpmn",
       build_subprocess_folded("subprocess_dispatch", SP_OUTER, SP_INNER))

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MATURITY,
        help=f"Where to write the fixtures (default: {MATURITY})",
    )
    args = parser.parse_args()
    written = emit_all(args.output_dir)
    print(f"Wrote {len(written)} files under {args.output_dir}")
    for path in written:
        print(f"  {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
