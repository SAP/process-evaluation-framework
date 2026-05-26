"""Interactive BPMN comparison widget for Jupyter notebooks."""

import os
import io
import json
import base64

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import ipywidgets as widgets
import pandas as pd
from IPython.display import display

from model_evaluation.BPMN_conversion import BPMNConverter
from model_evaluation.XML_conversion import XMLBPMNConverter
from model_evaluation.bpmn_normalization import normalize_atomic_names
from model_evaluation.bpmn_similarity import calculate_bpmn_similarity
from model_evaluation.petri import SoundnessStatus
from model_evaluation.trace_extraction import (
    calculate_trace_similarity,
    extract_traces,
)
from model_evaluation.utils import cosine_sim_optimized

CATEGORY_COLORS = {
    "structural":     "#3498db",
    "flows":          "#2ecc71",
    "organizational": "#f39c12",
    "subprocess":     "#9b59b6",
}


def _load_model(path):
    if path.endswith(".xml") or path.endswith(".bpmn"):
        return XMLBPMNConverter.convert_file(path).to_dict()
    with open(path, "r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


def _bpmn_iframe_html(xml_str, height_px=500):
    viewer_script = "https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-navigated-viewer.production.min.js"
    safe_xml = xml_str.replace("`", "'")
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="{viewer_script}"></script>
<style>html,body{{margin:0;padding:0;overflow:hidden;height:100%;background:#fff;}}
#canvas{{width:100%;height:100%;}}</style>
</head><body><div id="canvas"></div><script>
var xml=`{safe_xml}`;
window.addEventListener('load',function(){{
var v=new BpmnJS({{container:document.getElementById('canvas')}});
v.importXML(xml).then(function(){{v.get('canvas').zoom('fit-viewport','auto');}});
}});</script></body></html>"""
    html_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("utf-8")
    return f'<iframe src="data:text/html;base64,{html_b64}" width="100%" height="{height_px}px" frameborder="0"></iframe>'


def _trace_scores_html(res_1, res_2, tj, td, to):
    return (
        f"<table style='border-collapse:collapse; font-size:13px;'>"
        f"<tr><td style='padding:4px 8px;'>Sound traces Model 1</td><td style='padding:4px 8px;'><b>{len(res_1.variants)}</b>"
        f"{f' + {len(res_1.partial_traces)} partial' if res_1.partial_traces else ''}</td></tr>"
        f"<tr><td style='padding:4px 8px;'>Sound traces Model 2</td><td style='padding:4px 8px;'><b>{len(res_2.variants)}</b>"
        f"{f' + {len(res_2.partial_traces)} partial' if res_2.partial_traces else ''}</td></tr>"
        f"<tr><td style='padding:4px 8px;'>Jaccard</td><td style='padding:4px 8px;'>{tj:.1%}</td></tr>"
        f"<tr><td style='padding:4px 8px;'>Dice</td><td style='padding:4px 8px;'>{td:.1%}</td></tr>"
        f"<tr><td style='padding:4px 8px;'>Overlap</td><td style='padding:4px 8px;'>{to:.1%}</td></tr>"
        f"</table>"
    )


def _per_model_diagnostics_html(label, diag):
    if diag.status == SoundnessStatus.SOUND:
        return (f"<li><b>{label}:</b> "
                f"<span style='color:#27ae60;'>sound</span> "
                f"({diag.sound_variant_count} variant(s))</li>")

    body_parts = [f"<li><b>{label}:</b> "
                  f"<span style='color:#c0392b;'>{diag.status.value}</span> — {diag.summary}"]

    if diag.deadlock_markings:
        body_parts.append("<ul style='margin:4px 0 0 16px;'>")
        for sig in diag.deadlock_markings[:5]:
            tokens_str = ", ".join(f"{name}:{count}" for name, count in sig.tokens)
            example = " → ".join(sig.example_partial_trace) or "<empty>"
            body_parts.append(
                f"<li>tokens stuck at <code>{{{tokens_str}}}</code>; "
                f"e.g. partial trace <code>{example}</code></li>"
            )
        if len(diag.deadlock_markings) > 5:
            body_parts.append(f"<li>… {len(diag.deadlock_markings) - 5} more</li>")
        body_parts.append("</ul>")

    if diag.structural_findings:
        body_parts.append(
            f"<details style='margin:4px 0 0 0;'>"
            f"<summary>Structural findings ({len(diag.structural_findings)})</summary>"
            f"<ul style='margin:4px 0 0 16px; font-size:12px;'>"
        )
        for f in diag.structural_findings[:20]:
            node_part = f" <code>{f.node_id}</code>" if f.node_id else ""
            body_parts.append(f"<li><b>{f.issue}</b>{node_part}: {f.detail}</li>")
        if len(diag.structural_findings) > 20:
            body_parts.append(f"<li>… {len(diag.structural_findings) - 20} more</li>")
        body_parts.append("</ul></details>")

    body_parts.append("</li>")
    return "".join(body_parts)


def _diagnostics_panel_html(label_1, res_1, label_2, res_2):
    if res_1.is_sound and res_2.is_sound:
        return ""
    return (
        "<div style='margin-top:10px; padding:10px 14px; "
        "background:#fff8e1; border-left:4px solid #f39c12; border-radius:4px;'>"
        "<b>⚠ Behavioral comparison includes partial results</b>"
        "<ul style='margin:6px 0 0 16px; padding:0;'>"
        + _per_model_diagnostics_html(label_1, res_1.diagnostics)
        + _per_model_diagnostics_html(label_2, res_2.diagnostics)
        + "</ul></div>"
    )


def _model_summary_html(name, m):
    acts  = len(m.get('activities', []))
    evts  = len(m.get('events', []))
    gws   = len(m.get('gateways', []))
    flows = len(m.get('sequenceFlows', []))
    pools = len(m.get('pools', []))
    return (f"<div style='padding:8px; background:#f8f9fa; border-radius:6px; margin:4px 0;'>"
            f"<b>{name}</b><br>"
            f"<span style='color:#555;'>{acts} activities &middot; {evts} events &middot; "
            f"{gws} gateways &middot; {flows} flows &middot; {pools} pools</span></div>")


def _charts_to_png_html(result, method, w_structural, w_flows, w_org, w_subprocess):
    has_subprocess = result.get("has_expanded_subprocess", False)

    cat_weights = [w_structural, w_flows, w_org, w_subprocess if has_subprocess else 0.0]
    total_w = sum(cat_weights) or 1.0
    cat_weights = [w / total_w for w in cat_weights]

    raw_scores = [
        result["high_level_scores"]["structural"],
        result["high_level_scores"]["flows"],
        result["high_level_scores"]["organizational"],
        result["high_level_scores"]["subprocess"],
    ]
    categories = ["Structural", "Flows", "Organizational", "Subprocess"]
    colors = [CATEGORY_COLORS[k] for k in ("structural", "flows", "organizational", "subprocess")]

    weighted_scores = [s * w for s, w in zip(raw_scores, cat_weights)]
    overall_cat     = sum(weighted_scores)

    equal_w    = 1.0 / (3 + int(has_subprocess))
    eq_weights = [equal_w, equal_w, equal_w, equal_w if has_subprocess else 0.0]
    eq_scores  = [s * w for s, w in zip(raw_scores, eq_weights)]
    overall_eq = sum(eq_scores)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax1, ax2  = axes

    y  = np.arange(len(categories))
    bh = 0.35
    ax1.barh(y + bh / 2, eq_scores,       color=colors, alpha=0.35, height=bh)
    ax1.barh(y - bh / 2, weighted_scores,  color=colors, alpha=0.90, height=bh)
    ax1.set_yticks(y)
    ax1.set_yticklabels([f"{c}  ({s:.0%})" for c, s in zip(categories, raw_scores)])
    ax1.set_xlabel("Weighted score (score × weight)")
    ax1.set_xlim(0, max(0.5, max(weighted_scores + eq_scores) * 1.35))
    ax1.set_title(f"Category contributions  |  metric: {method.upper()}", fontsize=10)
    legend_elems = [
        mpatches.Patch(facecolor="gray", alpha=0.35, label=f"Equal weights  ({overall_eq:.1%})"),
        mpatches.Patch(facecolor="gray", alpha=0.90, label=f"Current weights  ({overall_cat:.1%})"),
    ]
    ax1.legend(handles=legend_elems, fontsize=9)
    ax1.grid(axis="x", alpha=0.3)
    for i, (eq, cur) in enumerate(zip(eq_scores, weighted_scores)):
        if eq  > 0.005: ax1.text(eq  + 0.008, i + bh / 2, f"{eq:.2f}",  va="center", fontsize=8, color="gray")
        if cur > 0.005: ax1.text(cur + 0.008, i - bh / 2, f"{cur:.2f}", va="center", fontsize=8, weight="bold")
    ax1.text(0.5, 0.5, f"{overall_cat:.1%}", transform=ax1.transAxes,
             fontsize=46, weight="bold", ha="center", va="center", alpha=0.12)

    elements = [
        "Activities", "Events", "Gateways",
        "Seq Flows", "Msg Flows",
        "Pool/Lane Names", "Pool/Lane Elements",
        "Subprocess Names", "Subprocess Elements", "Subprocess Flows",
    ]
    el_scores = [
        result["activity_names"], result["event_names"], result["gateway_names"],
        result["seq_flows_str"],  result["mes_flows_str"],
        result["lane_names"],     result["lane_with_refs"],
        result["subprocess_names"], result["subprocess_elemrefs"], result["subprocess_flows"],
    ]
    el_colors = (
        [CATEGORY_COLORS["structural"]] * 3 +
        [CATEGORY_COLORS["flows"]] * 2 +
        [CATEGORY_COLORS["organizational"]] * 2 +
        [CATEGORY_COLORS["subprocess"]] * 3
    )
    y2 = np.arange(len(elements))
    ax2.barh(y2, el_scores, color=el_colors, alpha=0.82)
    ax2.set_yticks(y2)
    ax2.set_yticklabels(elements, fontsize=9)
    ax2.set_xlabel("Score (0 – 1)")
    ax2.set_xlim(0, 1.15)
    ax2.set_title("Element-level breakdown (unweighted)", fontsize=10)
    ax2.grid(axis="x", alpha=0.3)
    for i, s in enumerate(el_scores):
        ax2.text(s + 0.02, i, f"{s:.2f}", va="center", fontsize=8)
    legend_patches = [mpatches.Patch(color=CATEGORY_COLORS[k], label=k.title())
                      for k in ("structural", "flows", "organizational", "subprocess")]
    ax2.legend(handles=legend_patches, fontsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%;">'


def _combined_score_html(structural, behavioral, w_s):
    w_b      = 1.0 - w_s
    combined = w_s * structural + w_b * behavioral
    bar_w    = int(combined * 100)
    return (f"<h4 style='margin:16px 0 4px;'>Combined Score</h4>"
            f"<div style='padding:12px; background:#f0f7ff; border-radius:8px; "
            f"border:1px solid #b8d4f0; margin:8px 0; max-width:480px;'>"
            f"<div style='font-size:24px; font-weight:bold; color:#1a5276;'>{combined:.1%}</div>"
            f"<div style='background:#e0e0e0; border-radius:4px; height:10px; margin:8px 0;'>"
            f"<div style='background:#1a5276; width:{bar_w}%; height:100%; border-radius:4px;'></div></div>"
            f"<div style='font-size:12px; color:#555;'>"
            f"= {w_s:.0%} &times; structural ({structural:.1%}) "
            f"+ {w_b:.0%} &times; behavioral ({behavioral:.1%})</div></div>")


# --- MAIN WIDGET ---

def create_comparison_widget(example_dir="../examples"):
    """Create and display the interactive BPMN comparison widget."""

    available_files = sorted([f for f in os.listdir(example_dir)
                               if f.endswith(".json") or f.endswith(".xml") or f.endswith(".bpmn")])

    style       = {'description_width': '150px'}
    layout_wide = widgets.Layout(width='520px')

    dropdown_1 = widgets.Dropdown(options=available_files, description="Model 1:",
                                   style=style, layout=layout_wide)
    dropdown_2 = widgets.Dropdown(options=available_files,
                                   value=available_files[1] if len(available_files) > 1 else available_files[0],
                                   description="Model 2:", style=style, layout=layout_wide)

    threshold_slider = widgets.FloatSlider(value=0.6, min=0.0, max=1.0, step=0.05,
                                            description="Norm. threshold:",
                                            style=style, layout=layout_wide, readout_format=".2f")
    method_toggle = widgets.ToggleButtons(options=["dice", "jaccard", "f1"],
                                           value="dice", description="Metric:", style=style)
    trace_timeout_slider = widgets.FloatSlider(value=5.0, min=1.0, max=30.0, step=1.0,
                                                description="Trace timeout (s):",
                                                style=style, layout=layout_wide, readout_format=".0f")
    loop_depth_slider = widgets.IntSlider(value=3, min=1, max=6, step=1,
                                           description="Max loop depth:",
                                           style=style, layout=layout_wide)

    w_structural_sl = widgets.FloatSlider(value=35, min=0, max=100, step=1,
                                           description="Structural (%):",
                                           style=style, layout=layout_wide, readout_format=".0f")
    w_flows_sl      = widgets.FloatSlider(value=30, min=0, max=100, step=1,
                                           description="Flows (%):",
                                           style=style, layout=layout_wide, readout_format=".0f")
    w_org_sl        = widgets.FloatSlider(value=20, min=0, max=100, step=1,
                                           description="Organizational (%):",
                                           style=style, layout=layout_wide, readout_format=".0f")
    w_subprocess_sl = widgets.FloatSlider(value=15, min=0, max=100, step=1,
                                           description="Subprocess (%):",
                                           style=style, layout=layout_wide, readout_format=".0f")
    weights_note = widgets.HTML(value="<span style='color:#888; font-size:11px;'>Sum: 100%</span>")

    def _update_weights_note(*_):
        total = w_structural_sl.value + w_flows_sl.value + w_org_sl.value + w_subprocess_sl.value
        if abs(total - 100.0) < 0.5:
            weights_note.value = f"<span style='color:#27ae60; font-size:11px;'>Sum: {total:.0f}% ✓</span>"
        else:
            weights_note.value = f"<span style='color:#e74c3c; font-size:11px;'>Sum: {total:.0f}% — click Recalculate to normalise</span>"

    w_structural_sl.observe(_update_weights_note, names='value')
    w_flows_sl.observe(_update_weights_note, names='value')
    w_org_sl.observe(_update_weights_note, names='value')
    w_subprocess_sl.observe(_update_weights_note, names='value')

    w_struct_beh_sl = widgets.FloatSlider(value=0.6, min=0.0, max=1.0, step=0.05,
                                           description="Structural weight:",
                                           style=style, layout=layout_wide, readout_format=".2f")
    w_beh_label = widgets.HTML("<span style='color:#555; font-size:12px;'>Behavioral weight: 0.40</span>")

    def _update_beh_label(change):
        w_beh_label.value = f"<span style='color:#555; font-size:12px;'>Behavioral weight: {1.0 - change['new']:.2f}</span>"
    w_struct_beh_sl.observe(_update_beh_label, names='value')

    run_button    = widgets.Button(description="  Compare", button_style="primary",
                                    icon="play", layout=widgets.Layout(width="160px", height="38px"))
    recalc_button = widgets.Button(description="  Recalculate weights", button_style="info",
                                    icon="refresh", layout=widgets.Layout(width="200px", height="34px"))

    # Single HTML widget — just set .value to update, never call display()
    output_html = widgets.HTML(value="")

    _state = {}

    def _draw_results():
        if not _state:
            return
        html_parts = list(_state["header_html"])

        html_parts.append("<h4 style='margin:16px 0 4px;'>Structural Similarity</h4>")
        html_parts.append(_charts_to_png_html(
            _state["result"], _state["method"],
            w_structural_sl.value, w_flows_sl.value, w_org_sl.value, w_subprocess_sl.value,
        ))

        html_parts.append("<h4 style='margin:16px 0 4px;'>Behavioral Similarity</h4>")
        html_parts.append(_state["traces_html"])

        if _state.get("trace_sim") is not None:
            has_sub = _state["result"].get("has_expanded_subprocess", False)
            raw_w = [w_structural_sl.value, w_flows_sl.value, w_org_sl.value,
                     w_subprocess_sl.value if has_sub else 0.0]
            total_w = sum(raw_w) or 1.0
            overall_cat = sum(
                _state["result"]["high_level_scores"][k] * (raw_w[i] / total_w)
                for i, k in enumerate(("structural", "flows", "organizational", "subprocess"))
            )
            html_parts.append(_combined_score_html(overall_cat, _state["trace_sim"], w_struct_beh_sl.value))

        output_html.value = "\n".join(html_parts)

    def on_compare(_):
        _state.clear()
        output_html.value = "<p style='color:#555;'>Loading…</p>"

        path_1 = os.path.join(example_dir, dropdown_1.value)
        path_2 = os.path.join(example_dir, dropdown_2.value)

        try:
            m1 = _load_model(path_1)
            m2 = _load_model(path_2)
        except Exception as e:
            output_html.value = f"<p style='color:red;'>Error loading models: {e}</p>"
            return

        header = []
        header.append(_model_summary_html(dropdown_1.value, m1))
        header.append(_model_summary_html(dropdown_2.value, m2))

        for path, label in [(path_1, dropdown_1.value), (path_2, dropdown_2.value)]:
            if path.endswith(".xml") or path.endswith(".bpmn"):
                with open(path, "r", encoding="utf-8") as f:
                    iframe = _bpmn_iframe_html(f.read(), height_px=480)
                header.append(f"<h4 style='margin:12px 0 4px;'>{label}</h4>{iframe}")

        m2_norm, mappings = normalize_atomic_names(
            m1, m2, cosine_sim_optimized, threshold=threshold_slider.value
        )
        changed = [(et, old, new) for et, emap in mappings.items()
                   for old, new in emap.items() if old != new]
        header.append(f"<h4 style='margin:12px 0 4px;'>Normalization</h4>"
                      f"<p style='margin:0; color:#555;'>{len(changed)} labels aligned "
                      f"(threshold = {threshold_slider.value:.2f})</p>")
        if changed:
            df_map = pd.DataFrame(changed, columns=["Type", "Original", "Mapped to"])
            header.append(df_map.to_html(index=False))

        method = method_toggle.value
        result = calculate_bpmn_similarity(m1, m2_norm, method=method)

        trace_sim = None
        try:
            res_1 = extract_traces(m1,      timeout_seconds=trace_timeout_slider.value,
                                   max_loop_depth=loop_depth_slider.value)
            res_2 = extract_traces(m2_norm, timeout_seconds=trace_timeout_slider.value,
                                   max_loop_depth=loop_depth_slider.value)
            tj = calculate_trace_similarity(res_1, res_2, method="jaccard")
            td = calculate_trace_similarity(res_1, res_2, method="dice")
            to = calculate_trace_similarity(res_1, res_2, method="overlap")
            trace_sim = tj
            traces_html = _trace_scores_html(res_1, res_2, tj, td, to)
            traces_html += _diagnostics_panel_html(
                dropdown_1.value, res_1, dropdown_2.value, res_2
            )
        except Exception as e:
            traces_html = f"<p style='color:red;'>Unexpected error during trace extraction: {e}</p>"

        _state.update({
            "result":      result,
            "method":      method,
            "header_html": header,
            "traces_html": traces_html,
            "trace_sim":   trace_sim,
        })
        _draw_results()

    def on_recalc(_):
        # Normalize sliders to sum to 100 and update them
        total = w_structural_sl.value + w_flows_sl.value + w_org_sl.value + w_subprocess_sl.value
        if total > 0 and abs(total - 100.0) > 0.5:
            w_structural_sl.value = round(w_structural_sl.value / total * 100)
            w_flows_sl.value      = round(w_flows_sl.value      / total * 100)
            w_org_sl.value        = round(w_org_sl.value        / total * 100)
            w_subprocess_sl.value = round(w_subprocess_sl.value / total * 100)
            weights_note.value = "<span style='color:#e67e22; font-size:11px;'>⚠ Weights were normalised to sum to 100%.</span>"
        else:
            weights_note.value = "<span style='color:#888; font-size:11px;'>Weights are normalised to sum to 100% when Recalculate is clicked.</span>"
        _draw_results()

    run_button.on_click(on_compare)
    recalc_button.on_click(on_recalc)

    controls = widgets.VBox([
        widgets.HTML("<h4 style='margin:0 0 8px;'>Models</h4>"),
        dropdown_1,
        dropdown_2,
        widgets.HTML("<h4 style='margin:12px 0 8px;'>Similarity parameters</h4>"),
        threshold_slider,
        method_toggle,
        trace_timeout_slider,
        loop_depth_slider,
        widgets.HTML("<h4 style='margin:12px 0 8px;'>Category weights (structural score)</h4>"),
        w_structural_sl,
        w_flows_sl,
        w_org_sl,
        w_subprocess_sl,
        weights_note,
        widgets.HTML("<h4 style='margin:12px 0 8px;'>Structural vs behavioral split</h4>"),
        w_struct_beh_sl,
        w_beh_label,
        widgets.HTML("<br>"),
        run_button,
        widgets.HTML("<br>"),
        recalc_button,
    ])

    display(widgets.VBox([controls, output_html]))
