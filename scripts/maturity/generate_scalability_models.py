"""Generate scalability BPMN fixtures for the maturity suite.

Two shapes:

- **Linear chain.** ``start → task_1 → task_2 → ... → task_N → end``.
  Polynomial growth in element count, single trace variant — stresses
  loading, set construction, and normalization but not behavioral
  exploration.

- **Parallel AND.** ``start → AND-split → (task_1, ..., task_N) → AND-join
  → end``. Element count grows linearly in ``N`` but the trace-extraction
  state space grows factorially (``N!`` interleavings). This is the
  *intentional* fidelity/cost trade-off of behavioral similarity and we
  surface where the wall is.

Sizes (mirrors the plan):

- Linear: N ∈ {5, 10, 20, 50, 100, 200}
- AND:    N ∈ {2, 3, 4, 5, 6, 7, 8}

Each file also contains a ``<bpmndi:BPMNDiagram>`` block with synthetic
shape + edge coordinates. bpmn-js (the viewer the dashboard uses) refuses
to render a process that has no diagram block ("no diagram to display"),
so we emit a simple grid layout. Coordinates aren't beautiful — they're
just valid, and the viewer renders them fine.

Run from repo root::

    poetry run python scripts/maturity/generate_scalability_models.py

Files land in ``examples/maturity/scalability/`` and are intended to be
committed — reviewers should not have to regenerate them.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent
from typing import Iterable


LINEAR_SIZES: tuple[int, ...] = (5, 10, 20, 50, 100, 200)
AND_SIZES: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "examples" / "maturity" / "scalability"


# ---------------------------------------------------------------------------
# Layout constants — match the dimensions used by the hand-authored fixtures
# in examples/and_gateway_with_join.bpmn so the styling stays consistent.
# ---------------------------------------------------------------------------

EVENT_W, EVENT_H = 36, 36
TASK_W, TASK_H = 100, 80
GATE_W, GATE_H = 50, 50

# Horizontal step between successive node centers. Big enough that a
# task (100 wide) sits between two events without overlap.
STEP_X = 140

# Vertical lane center for the horizontal main axis.
AXIS_Y = 200

# For AND fans: how far apart consecutive branch tasks sit vertically.
BRANCH_STEP_Y = 100


# ---------------------------------------------------------------------------
# XML emission
# ---------------------------------------------------------------------------

_BPMN_HEADER = dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
                 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                 xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                 xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 id="Definitions_1"
                 targetNamespace="http://example.org/bpmn/maturity"
                 exporter="generate_scalability_models.py"
                 exporterVersion="1.0">
    """
)

_BPMN_FOOTER = "</definitions>\n"


def _process_open(process_id: str, name: str) -> str:
    return f'  <process id="{process_id}" name="{name}" isExecutable="true">\n'


def _process_close() -> str:
    return "  </process>\n"


def _start(node_id: str, outgoing: str) -> str:
    return dedent(
        f"""\
            <startEvent id="{node_id}" name="Start">
              <outgoing>{outgoing}</outgoing>
            </startEvent>
        """
    )


def _end(node_id: str, incoming: str) -> str:
    return dedent(
        f"""\
            <endEvent id="{node_id}" name="End">
              <incoming>{incoming}</incoming>
            </endEvent>
        """
    )


def _task(node_id: str, name: str, incoming: str, outgoing: str) -> str:
    return dedent(
        f"""\
            <task id="{node_id}" name="{name}">
              <incoming>{incoming}</incoming>
              <outgoing>{outgoing}</outgoing>
            </task>
        """
    )


def _parallel_gateway(
    node_id: str, name: str, incoming: Iterable[str], outgoing: Iterable[str]
) -> str:
    in_lines = "\n".join(f"      <incoming>{x}</incoming>" for x in incoming)
    out_lines = "\n".join(f"      <outgoing>{x}</outgoing>" for x in outgoing)
    return (
        f'    <parallelGateway id="{node_id}" name="{name}">\n'
        f"{in_lines}\n{out_lines}\n"
        f"    </parallelGateway>\n"
    )


def _flow(flow_id: str, src: str, tgt: str) -> str:
    return f'    <sequenceFlow id="{flow_id}" sourceRef="{src}" targetRef="{tgt}"/>\n'


# ---------------------------------------------------------------------------
# BPMNDI emission
# ---------------------------------------------------------------------------

def _di_shape(node_id: str, x: int, y: int, w: int, h: int) -> str:
    return (
        f'      <bpmndi:BPMNShape id="shape_{node_id}" bpmnElement="{node_id}">\n'
        f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}"/>\n'
        f"      </bpmndi:BPMNShape>\n"
    )


def _di_edge(flow_id: str, waypoints: list[tuple[int, int]]) -> str:
    wp = "\n".join(f'        <di:waypoint x="{x}" y="{y}"/>' for x, y in waypoints)
    return (
        f'      <bpmndi:BPMNEdge id="edge_{flow_id}" bpmnElement="{flow_id}">\n'
        f"{wp}\n"
        f"      </bpmndi:BPMNEdge>\n"
    )


def _diagram_open(plane_id: str, element_ref: str) -> str:
    return (
        '  <bpmndi:BPMNDiagram id="BPMNDiagram_1">\n'
        f'    <bpmndi:BPMNPlane id="{plane_id}" bpmnElement="{element_ref}">\n'
    )


def _diagram_close() -> str:
    return "    </bpmndi:BPMNPlane>\n  </bpmndi:BPMNDiagram>\n"


def _center_right(x: int, w: int, y: int, h: int) -> tuple[int, int]:
    """Right-middle anchor point of a box at (x, y) with size (w, h)."""
    return (x + w, y + h // 2)


def _center_left(x: int, h: int, y: int) -> tuple[int, int]:
    """Left-middle anchor point of a box at (x, y) with height h."""
    return (x, y + h // 2)


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def build_linear(n: int) -> str:
    """Linear chain of ``n`` tasks between a single start and end event."""
    assert n >= 1
    process_id = f"linear_{n}"
    parts: list[str] = [_BPMN_HEADER, _process_open(process_id, f"Linear N={n}")]

    # --- process block ---
    flow_ids = [f"flow_{i}" for i in range(n + 1)]
    parts.append(_start("start", flow_ids[0]))
    for i in range(1, n + 1):
        parts.append(_task(f"task_{i}", f"Task {i}", flow_ids[i - 1], flow_ids[i]))
    parts.append(_end("end", flow_ids[-1]))

    parts.append(_flow(flow_ids[0], "start", "task_1"))
    for i in range(1, n):
        parts.append(_flow(flow_ids[i], f"task_{i}", f"task_{i + 1}"))
    parts.append(_flow(flow_ids[n], f"task_{n}", "end"))
    parts.append(_process_close())

    # --- diagram block: lay out start, task_1, ..., task_n, end on a row ---
    parts.append(_diagram_open("BPMNPlane_1", process_id))

    # x-position of each element's bounding box, in order: start, task_1..n, end
    x_start = 100
    start_x = x_start
    task_xs = [x_start + STEP_X * (i + 1) - (TASK_W - EVENT_W) // 2 for i in range(n)]
    end_x = task_xs[-1] + TASK_W + STEP_X // 2

    # Vertical alignment — center the smaller boxes against the task center.
    task_y = AXIS_Y - TASK_H // 2
    event_y = AXIS_Y - EVENT_H // 2

    parts.append(_di_shape("start", start_x, event_y, EVENT_W, EVENT_H))
    for i, x in enumerate(task_xs, start=1):
        parts.append(_di_shape(f"task_{i}", x, task_y, TASK_W, TASK_H))
    parts.append(_di_shape("end", end_x, event_y, EVENT_W, EVENT_H))

    # Edges: simple straight lines on the main axis.
    prev_anchor = _center_right(start_x, EVENT_W, event_y, EVENT_H)
    parts.append(_di_edge(flow_ids[0], [prev_anchor, _center_left(task_xs[0], TASK_H, task_y)]))
    for i in range(1, n):
        a = _center_right(task_xs[i - 1], TASK_W, task_y, TASK_H)
        b = _center_left(task_xs[i], TASK_H, task_y)
        parts.append(_di_edge(flow_ids[i], [a, b]))
    a = _center_right(task_xs[-1], TASK_W, task_y, TASK_H)
    b = _center_left(end_x, EVENT_H, event_y)
    parts.append(_di_edge(flow_ids[n], [a, b]))

    parts.append(_diagram_close())
    parts.append(_BPMN_FOOTER)
    return "".join(parts)


def build_and_split(n: int) -> str:
    """AND-split → ``n`` parallel tasks → AND-join."""
    assert n >= 2
    process_id = f"and_{n}"
    parts: list[str] = [_BPMN_HEADER, _process_open(process_id, f"AND N={n}")]

    split_in = "flow_start_to_split"
    join_out = "flow_join_to_end"
    split_outs = [f"flow_split_to_task_{i}" for i in range(1, n + 1)]
    join_ins = [f"flow_task_{i}_to_join" for i in range(1, n + 1)]

    parts.append(_start("start", split_in))
    parts.append(_parallel_gateway("split", "AND Split", [split_in], split_outs))
    for i in range(1, n + 1):
        parts.append(
            _task(f"task_{i}", f"Task {i}", split_outs[i - 1], join_ins[i - 1])
        )
    parts.append(_parallel_gateway("join", "AND Join", join_ins, [join_out]))
    parts.append(_end("end", join_out))

    parts.append(_flow(split_in, "start", "split"))
    for i in range(1, n + 1):
        parts.append(_flow(split_outs[i - 1], "split", f"task_{i}"))
        parts.append(_flow(join_ins[i - 1], f"task_{i}", "join"))
    parts.append(_flow(join_out, "join", "end"))
    parts.append(_process_close())

    # --- diagram block ---
    parts.append(_diagram_open("BPMNPlane_1", process_id))

    # Center the n branches vertically around AXIS_Y.
    branch_total_h = (n - 1) * BRANCH_STEP_Y
    top_y = AXIS_Y - branch_total_h // 2
    branch_ys = [top_y + i * BRANCH_STEP_Y for i in range(n)]

    start_x = 100
    split_x = start_x + STEP_X
    task_x = split_x + STEP_X
    join_x = task_x + TASK_W + STEP_X // 2
    end_x = join_x + STEP_X

    event_y = AXIS_Y - EVENT_H // 2
    gate_y = AXIS_Y - GATE_H // 2

    parts.append(_di_shape("start", start_x, event_y, EVENT_W, EVENT_H))
    parts.append(_di_shape("split", split_x, gate_y, GATE_W, GATE_H))
    for i, by in enumerate(branch_ys, start=1):
        parts.append(_di_shape(f"task_{i}", task_x, by - TASK_H // 2, TASK_W, TASK_H))
    parts.append(_di_shape("join", join_x, gate_y, GATE_W, GATE_H))
    parts.append(_di_shape("end", end_x, event_y, EVENT_W, EVENT_H))

    # Edges
    parts.append(_di_edge(split_in, [
        _center_right(start_x, EVENT_W, event_y, EVENT_H),
        (split_x, AXIS_Y),
    ]))
    for i, by in enumerate(branch_ys, start=1):
        task_top_y = by - TASK_H // 2
        # Out from split → branch task left edge (small zig to the branch row).
        parts.append(_di_edge(split_outs[i - 1], [
            (split_x + GATE_W, AXIS_Y),
            (task_x, by),
        ]))
        # Branch task right edge → join.
        parts.append(_di_edge(join_ins[i - 1], [
            (task_x + TASK_W, by),
            (join_x, AXIS_Y),
        ]))
    parts.append(_di_edge(join_out, [
        (join_x + GATE_W, AXIS_Y),
        _center_left(end_x, EVENT_H, event_y),
    ]))

    parts.append(_diagram_close())
    parts.append(_BPMN_FOOTER)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def emit_all(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for n in LINEAR_SIZES:
        path = output_dir / f"linear_{n}.bpmn"
        path.write_text(build_linear(n), encoding="utf-8")
        written.append(path)
    for n in AND_SIZES:
        path = output_dir / f"and_{n}.bpmn"
        path.write_text(build_and_split(n), encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Where to write the BPMN files (default: {OUTPUT_DIR})",
    )
    args = parser.parse_args()

    written = emit_all(args.output_dir)
    print(f"Wrote {len(written)} files to {args.output_dir}")
    for path in written:
        print(f"  {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
