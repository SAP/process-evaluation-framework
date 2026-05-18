"""Interactive BPMN comparison widget for Jupyter notebooks."""

import os
import json
import base64

import ipywidgets as widgets
import pandas as pd
from IPython.display import display, HTML, clear_output

from BPMN_conversion import BPMNConverter
from XML_conversion import XMLBPMNConverter
from bpmn_normalization import normalize_atomic_names
from bpmn_similarity import calculate_bpmn_similarity
from trace_extraction import extract_traces, calculate_trace_similarity
from utils import cosine_sim_optimized


def _load_model(path):
    if path.endswith(".xml") or path.endswith(".bpmn"):
        return XMLBPMNConverter.convert_file(path).to_dict()
    with open(path, "r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


def _bpmn_iframe_html(xml_str, height_px=500):
    """Return an HTML iframe string for rendering BPMN XML via bpmn-js."""
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


def _model_summary_html(name, m):
    acts = len(m.get('activities', []))
    evts = len(m.get('events', []))
    gws = len(m.get('gateways', []))
    flows = len(m.get('sequenceFlows', []))
    pools = len(m.get('pools', []))
    return (f"<div style='padding:8px; background:#f8f9fa; border-radius:6px; margin:4px 0;'>"
            f"<b>{name}</b><br>"
            f"<span style='color:#555;'>{acts} activities &middot; {evts} events &middot; "
            f"{gws} gateways &middot; {flows} flows &middot; {pools} pools</span></div>")


def _score_table_html(result, method):
    rows = ""
    for cat in ["structural", "flows", "organizational", "subprocess"]:
        score = result['high_level_scores'][cat]
        bar_width = int(score * 100)
        rows += (f"<tr><td style='padding:4px 8px;'>{cat.title()}</td>"
                 f"<td style='padding:4px 8px;'>{score:.1%}</td>"
                 f"<td style='padding:4px 8px; width:200px;'>"
                 f"<div style='background:#e0e0e0; border-radius:3px; height:14px;'>"
                 f"<div style='background:#4a90d9; width:{bar_width}%; height:100%; border-radius:3px;'></div>"
                 f"</div></td></tr>")
    overall = result['overall']
    bar_width = int(overall * 100)
    rows += (f"<tr style='font-weight:bold; border-top:2px solid #ccc;'>"
             f"<td style='padding:4px 8px;'>Overall</td>"
             f"<td style='padding:4px 8px;'>{overall:.1%}</td>"
             f"<td style='padding:4px 8px; width:200px;'>"
             f"<div style='background:#e0e0e0; border-radius:3px; height:14px;'>"
             f"<div style='background:#2d6cb4; width:{bar_width}%; height:100%; border-radius:3px;'></div>"
             f"</div></td></tr>")
    return (f"<table style='border-collapse:collapse; font-size:13px;'>"
            f"<thead><tr><th style='text-align:left; padding:4px 8px;'>Category</th>"
            f"<th style='text-align:left; padding:4px 8px;'>Score ({method})</th>"
            f"<th style='padding:4px 8px;'></th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def _trace_table_html(n1, n2, tj, td, to):
    return (f"<table style='border-collapse:collapse; font-size:13px;'>"
            f"<tr><td style='padding:4px 8px;'>Traces Model 1</td><td style='padding:4px 8px;'><b>{n1}</b></td></tr>"
            f"<tr><td style='padding:4px 8px;'>Traces Model 2</td><td style='padding:4px 8px;'><b>{n2}</b></td></tr>"
            f"<tr><td style='padding:4px 8px;'>Jaccard</td><td style='padding:4px 8px;'>{tj:.1%}</td></tr>"
            f"<tr><td style='padding:4px 8px;'>Dice</td><td style='padding:4px 8px;'>{td:.1%}</td></tr>"
            f"<tr><td style='padding:4px 8px;'>Overlap</td><td style='padding:4px 8px;'>{to:.1%}</td></tr>"
            f"</table>")


def _combined_score_html(structural, behavioral, w_s, w_b):
    combined = w_s * structural + w_b * behavioral
    bar_width = int(combined * 100)
    return (f"<div style='padding:12px; background:#f0f7ff; border-radius:8px; border:1px solid #b8d4f0; margin:8px 0;'>"
            f"<div style='font-size:22px; font-weight:bold; color:#1a5276;'>{combined:.1%}</div>"
            f"<div style='background:#e0e0e0; border-radius:4px; height:10px; margin:8px 0;'>"
            f"<div style='background:#1a5276; width:{bar_width}%; height:100%; border-radius:4px;'></div></div>"
            f"<div style='font-size:12px; color:#555;'>"
            f"= {w_s:.0%} &times; structural ({structural:.1%}) + {w_b:.0%} &times; behavioral ({behavioral:.1%})</div></div>")


# --- MAIN WIDGET ---

def create_comparison_widget(example_dir="../examples"):
    """Create and display the interactive BPMN comparison widget."""

    available_files = sorted([f for f in os.listdir(example_dir)
                              if f.endswith(".json") or f.endswith(".xml") or f.endswith(".bpmn")])

    style = {'description_width': '130px'}
    layout_wide = widgets.Layout(width='500px')

    dropdown_1 = widgets.Dropdown(options=available_files, description="Model 1:",
                                  style=style, layout=layout_wide)
    dropdown_2 = widgets.Dropdown(options=available_files,
                                  value=available_files[1] if len(available_files) > 1 else available_files[0],
                                  description="Model 2:",
                                  style=style, layout=layout_wide)

    threshold_slider = widgets.FloatSlider(value=0.6, min=0.0, max=1.0, step=0.05,
                                           description="Norm. threshold:",
                                           style=style, layout=layout_wide,
                                           readout_format=".2f")

    method_toggle = widgets.ToggleButtons(options=["dice", "jaccard", "f1"],
                                          value="dice", description="Metric:",
                                          style=style)

    trace_timeout_slider = widgets.FloatSlider(value=5.0, min=1.0, max=30.0, step=1.0,
                                               description="Trace timeout (s):",
                                               style=style, layout=layout_wide,
                                               readout_format=".0f")

    loop_depth_slider = widgets.IntSlider(value=3, min=1, max=6, step=1,
                                          description="Max loop depth:",
                                          style=style, layout=layout_wide)

    weight_structural_slider = widgets.FloatSlider(value=0.6, min=0.0, max=1.0, step=0.05,
                                                   description="Weight structural:",
                                                   style=style, layout=layout_wide,
                                                   readout_format=".2f")

    weight_behavioral_label = widgets.HTML(
        value="<span style='color:#555; font-size:12px;'>Weight behavioral: 0.40</span>"
    )

    def update_behavioral_label(change):
        w_b = 1.0 - change['new']
        weight_behavioral_label.value = (
            f"<span style='color:#555; font-size:12px;'>Weight behavioral: {w_b:.2f}</span>"
        )

    weight_structural_slider.observe(update_behavioral_label, names='value')

    run_button = widgets.Button(description="  Compare", button_style="primary",
                                icon="play",
                                layout=widgets.Layout(width="160px", height="38px"))

    output_area = widgets.Output(layout=widgets.Layout(border='1px solid #e0e0e0',
                                                        padding='12px',
                                                        margin='10px 0',
                                                        border_radius='8px'))

    def on_compare(_):
        with output_area:
            clear_output(wait=True)
            path_1 = os.path.join(example_dir, dropdown_1.value)
            path_2 = os.path.join(example_dir, dropdown_2.value)

            try:
                m1 = _load_model(path_1)
                m2 = _load_model(path_2)
            except Exception as e:
                display(HTML(f"<p style='color:red;'>Error loading models: {e}</p>"))
                return

            html_parts = []

            # Model summaries
            html_parts.append(_model_summary_html(dropdown_1.value, m1))
            html_parts.append(_model_summary_html(dropdown_2.value, m2))

            # Render XML diagrams
            for path, label in [(path_1, dropdown_1.value), (path_2, dropdown_2.value)]:
                if path.endswith(".xml") or path.endswith(".bpmn"):
                    with open(path, "r", encoding="utf-8") as f:
                        iframe = _bpmn_iframe_html(f.read(), height_px=500)
                    html_parts.append(f"<h4 style='margin:12px 0 4px;'>{label}</h4>{iframe}")

            # Normalization
            m2_norm, mappings = normalize_atomic_names(
                m1, m2, cosine_sim_optimized, threshold=threshold_slider.value
            )
            changed_mappings = [(etype, old, new) for etype, emap in mappings.items()
                                for old, new in emap.items() if old != new]
            html_parts.append(f"<h4 style='margin:12px 0 4px;'>Normalization</h4>"
                              f"<p style='margin:0; color:#555;'>{len(changed_mappings)} labels aligned "
                              f"(threshold = {threshold_slider.value:.2f})</p>")
            if changed_mappings:
                df_map = pd.DataFrame(changed_mappings, columns=["Type", "Original", "Mapped to"])
                html_parts.append(df_map.to_html(index=False, classes="table"))

            # Structural similarity
            method = method_toggle.value
            result = calculate_bpmn_similarity(m1, m2_norm, method=method)
            html_parts.append("<h4 style='margin:16px 0 4px;'>Structural Similarity</h4>")
            html_parts.append(_score_table_html(result, method))

            # Trace extraction
            html_parts.append("<h4 style='margin:16px 0 4px;'>Behavioral Similarity</h4>")
            try:
                timeout = trace_timeout_slider.value
                max_loop = loop_depth_slider.value
                traces_1 = extract_traces(m1, timeout_seconds=timeout, max_loop_depth=max_loop)
                traces_2 = extract_traces(m2_norm, timeout_seconds=timeout, max_loop_depth=max_loop)

                tj = calculate_trace_similarity(list(traces_1), list(traces_2), method="jaccard")
                td = calculate_trace_similarity(list(traces_1), list(traces_2), method="dice")
                to = calculate_trace_similarity(list(traces_1), list(traces_2), method="overlap")

                html_parts.append(_trace_table_html(len(traces_1), len(traces_2), tj, td, to))

                # Combined score
                w_s = weight_structural_slider.value
                w_b = 1.0 - w_s
                html_parts.append("<h4 style='margin:16px 0 4px;'>Combined Score</h4>")
                html_parts.append(_combined_score_html(result['overall'], tj, w_s, w_b))

            except Exception as e:
                html_parts.append(f"<p style='color:orange;'>Trace extraction failed: {e}</p>")

            display(HTML("\n".join(html_parts)))

    run_button.on_click(on_compare)

    controls = widgets.VBox([
        widgets.HTML("<h4 style='margin:0 0 8px;'>Models</h4>"),
        dropdown_1,
        dropdown_2,
        widgets.HTML("<h4 style='margin:12px 0 8px;'>Parameters</h4>"),
        threshold_slider,
        method_toggle,
        trace_timeout_slider,
        loop_depth_slider,
        widgets.HTML("<h4 style='margin:12px 0 8px;'>Combined Score Weights</h4>"),
        weight_structural_slider,
        weight_behavioral_label,
        widgets.HTML("<br>"),
        run_button,
    ])

    display(widgets.VBox([controls, output_area]))
