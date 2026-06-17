"""Marimo dashboard for BPMN similarity exploration.

Reactive re-skin of ``model_evaluation/rendering/dashboard.py``. Same three
sections (structural / behavioral / hybrid + n-gram subpanel), same underlying
similarity functions; cleaner card-based layout, Plotly charts, and marimo's
reactive cell graph in place of ipywidgets event handlers and manual caches.

Run interactively:
    poetry run marimo edit notebooks/dashboard.py

Run as a read-only app:
    poetry run marimo run notebooks/dashboard.py
"""

import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _imports():
    # Imports + sys.path shim.
    #
    # Mirrors ``notebooks/model_eval_code_usage.ipynb`` cell 1 so the bare
    # imports (``from bpmn_similarity import ...``) work whether marimo is
    # started from the repo root or from ``notebooks/``.
    import base64
    import sys
    from pathlib import Path

    import marimo as mo
    import plotly.graph_objects as go

    _here = Path(__file__).resolve().parent
    _repo_root = _here.parent
    for _p in (str(_repo_root), str(_repo_root / "model_evaluation")):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from bpmn_normalization import normalize_atomic_names
    from bpmn_similarity import (
        calculate_bpmn_similarity,
        calculate_hybrid_similarity,
        calculate_ngram_similarity,
        calculate_trace_similarity,
    )
    from model_evaluation.BPMN_conversion import XMLBPMNConverter
    from model_evaluation.rendering.dashboard import CATEGORY_COLORS
    from trace_extraction import extract_ngrams, extract_traces
    from utils.string_similarity import cosine_sim_optimized

    NO_DATA_COLOR = "#95a5a6"
    REPO_ROOT = _repo_root
    EXAMPLES_DIR = _repo_root / "examples"
    return (
        CATEGORY_COLORS,
        EXAMPLES_DIR,
        NO_DATA_COLOR,
        XMLBPMNConverter,
        base64,
        calculate_bpmn_similarity,
        calculate_hybrid_similarity,
        calculate_ngram_similarity,
        calculate_trace_similarity,
        cosine_sim_optimized,
        extract_ngrams,
        extract_traces,
        go,
        mo,
        normalize_atomic_names,
    )


@app.cell
def _theme(mo):
    # Card / KPI CSS + small render helpers shared by every section.
    CARD_CSS = """
    <style>
    .pe-page { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
        Roboto, sans-serif; color: #334155; }
    .pe-card {
        background: #ffffff;
        border: 1px solid #eef0f3;
        border-radius: 14px;
        padding: 22px 26px;
        margin: 14px 0;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }
    .pe-card-title {
        margin: 0 0 14px 0;
        font-weight: 600;
        font-size: 18px;
        color: #0f172a;
        letter-spacing: -0.01em;
    }
    .pe-kpi-row { display: flex; gap: 28px; align-items: flex-end;
        margin: 6px 0 4px 0; }
    .pe-kpi-label { color: #64748b; font-size: 12px;
        text-transform: uppercase; letter-spacing: 0.05em; }
    .pe-kpi-value { font-size: 38px; font-weight: 700; color: #0f172a;
        line-height: 1.1; margin-top: 2px; }
    .pe-stale { background: #fff7ed; border: 1px solid #fed7aa;
        color: #9a3412; padding: 8px 12px; border-radius: 8px;
        font-size: 13px; margin-bottom: 10px; }
    .pe-muted { color: #64748b; font-size: 13px; }
    .pe-diag { background: #f8fafc; border: 1px solid #eef0f3;
        border-radius: 8px; padding: 10px 12px; font-family: ui-monospace,
        SFMono-Regular, Menlo, monospace; font-size: 12px; color: #1e293b;
        white-space: pre-wrap; line-height: 1.55; }
    </style>
    """

    def card(title: str, *body) -> "mo.Html":
        """Wrap a sequence of marimo elements in a styled card.

        We render the title and the body children inside a single
        ``mo.vstack`` so layout flows naturally; the surrounding card div
        comes from a thin HTML wrapper around the stack's HTML output.
        """
        inner = mo.vstack(list(body), gap=0.6)
        return mo.Html(
            f"<div class='pe-card'>"
            f"<div class='pe-card-title'>{title}</div>"
            f"{inner.text}"
            f"</div>"
        )

    def kpi_html(label: str, value: str, color: str = "#0f172a") -> str:
        return (
            f"<div>"
            f"<div class='pe-kpi-label'>{label}</div>"
            f"<div class='pe-kpi-value' style='color:{color}'>{value}</div>"
            f"</div>"
        )

    def fmt_pct(x):
        if x is None:
            return "N/A"
        return f"{x:.1%}"

    mo.output.append(mo.Html(CARD_CSS))
    return card, fmt_pct, kpi_html


@app.cell
def _intro(mo):
    mo.md(
        """
    # BPMN Similarity Dashboard

    Compare two BPMN models along **structural**, **behavioral**, and
    **hybrid** axes. Pick the two models below, optionally tune the
    normalization threshold and metric, then explore the three sections.
    """
    )
    return


@app.cell
def _bpmn_options(EXAMPLES_DIR):
    # Recursive scan of examples/ for .bpmn files. Display labels are
    # relative to examples/ so nested folders (e.g. testing_models/...) are
    # visible in the dropdown.
    paths = sorted(EXAMPLES_DIR.rglob("*.bpmn"))
    bpmn_options = {str(p.relative_to(EXAMPLES_DIR)): str(p) for p in paths}

    # Defaults: the P2P pair if present, otherwise the first two entries.
    _preferred_1 = "testing_models/P2P - Running Example.bpmn"
    _preferred_2 = "testing_models/P2P - Variant Running Example.bpmn"
    _keys = list(bpmn_options.keys())
    default_1 = _preferred_1 if _preferred_1 in bpmn_options else (_keys[0] if _keys else None)
    default_2 = _preferred_2 if _preferred_2 in bpmn_options else (_keys[1] if len(_keys) > 1 else default_1)
    return bpmn_options, default_1, default_2


@app.cell
def _model_pickers(bpmn_options, default_1, default_2, mo):
    model1_dd = mo.ui.dropdown(
        options=bpmn_options, value=default_1, label="Model 1 (reference)"
    )
    model2_dd = mo.ui.dropdown(
        options=bpmn_options, value=default_2, label="Model 2 (compare)"
    )
    return model1_dd, model2_dd


@app.cell
def _models_card(card, mo, model1_dd, model2_dd):
    card("Models", mo.hstack([model1_dd, model2_dd], justify="start", gap=2))
    return


@app.cell
def _load_models(XMLBPMNConverter, mo, model1_dd, model2_dd):
    # Parse the two selected .bpmn files into the minimal-BPMN dicts.
    #
    # Reactivity: re-runs whenever either dropdown changes. The XML strings
    # are kept around for the BPMN preview iframes below.
    mo.stop(
        not (model1_dd.value and model2_dd.value),
        mo.md("_Pick two BPMN files above to load the models._"),
    )

    from pathlib import Path as _Path

    xml1 = _Path(model1_dd.value).read_text(encoding="utf-8")
    xml2 = _Path(model2_dd.value).read_text(encoding="utf-8")
    model_1_json = XMLBPMNConverter.convert_file(model1_dd.value).to_dict()
    model_2_json = XMLBPMNConverter.convert_file(model2_dd.value).to_dict()
    return model_1_json, model_2_json, xml1, xml2


@app.cell
def _bpmn_iframe_helper(base64):
    # Same iframe trick as ``rendering/bpmn_viewer.render_bpmn_xml_embed``,
    # but returns the HTML string directly (the stock helper calls
    # ``display(HTML(...))`` which marimo can't capture).
    _viewer_script = (
        "https://unpkg.com/bpmn-js@17.11.1/dist/"
        "bpmn-navigated-viewer.production.min.js"
    )
    _html_template = (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        '<meta charset="UTF-8">'
        '<script src="__VIEWER__"></script>'
        "<style>"
        "html, body { margin: 0; padding: 0; overflow: hidden; height: 100%; background: #ffffff; }"
        "#canvas { width: 100%; height: 100%; }"
        "#error { color: red; padding: 20px; display: none; }"
        "</style>"
        "</head>"
        "<body>"
        '<div id="error"></div>'
        '<div id="canvas"></div>'
        "<script>"
        "var xml = `__XML__`;"
        "window.addEventListener('load', function() {"
        "  var viewer = new BpmnJS({ container: document.getElementById('canvas') });"
        "  viewer.importXML(xml).then(function() {"
        "    var canvas = viewer.get('canvas');"
        "    canvas.zoom('fit-viewport', 'auto');"
        "  }).catch(function(err) {"
        "    document.getElementById('error').style.display = 'block';"
        "    document.getElementById('error').textContent = 'Error: ' + err.message;"
        "  });"
        "});"
        "</script>"
        "</body>"
        "</html>"
    )

    def bpmn_iframe(xml_str, height_px=320):
        safe_xml = xml_str.replace("`", "'")
        html_doc = _html_template.replace("__VIEWER__", _viewer_script).replace(
            "__XML__", safe_xml
        )
        html_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("utf-8")
        return (
            "<iframe src=\"data:text/html;base64,"
            + html_b64
            + "\" width=\"100%\" height=\""
            + str(height_px)
            + "px\" frameborder=\"0\" style=\"border-radius:8px;\"></iframe>"
        )

    return (bpmn_iframe,)


@app.cell
def _bpmn_preview(bpmn_iframe, card, mo, model1_dd, model2_dd, xml1, xml2):
    # Render both diagrams side-by-side, each in its own card.
    _label_1 = model1_dd.selected_key if hasattr(model1_dd, "selected_key") else "Model 1"
    _label_2 = model2_dd.selected_key if hasattr(model2_dd, "selected_key") else "Model 2"
    # selected_key isn't always available across marimo versions — fall back
    # to the value->label inverse lookup via the dropdown's options dict.
    try:
        _opts = model1_dd._options if hasattr(model1_dd, "_options") else None
    except Exception:
        _opts = None

    diagrams = mo.hstack(
        [
            card("Model 1", mo.Html(bpmn_iframe(xml1))),
            card("Model 2", mo.Html(bpmn_iframe(xml2))),
        ],
        widths="equal",
        gap=1,
    )
    diagrams
    return


@app.cell
def _global_controls(mo):
    metric_radio = mo.ui.radio(
        options=["dice", "jaccard", "overlap", "precision", "recall", "f1"],
        value="dice",
        label="Set-comparison metric",
        inline=True,
    )
    threshold_slider = mo.ui.slider(
        start=0.0,
        stop=1.0,
        step=0.05,
        value=0.7,
        label="Normalization threshold",
        show_value=True,
    )
    return metric_radio, threshold_slider


@app.cell
def _global_card(card, metric_radio, mo, threshold_slider):
    card(
        "Global controls",
        mo.md(
            "These two controls feed every section below. "
            "The threshold drives semantic name alignment; "
            "the metric is used for both structural and behavioral set comparisons."
        ),
        mo.hstack([metric_radio, threshold_slider], justify="start", gap=2),
    )
    return


@app.cell
def _structural_compute(
    calculate_bpmn_similarity,
    cosine_sim_optimized,
    metric_radio,
    model_1_json,
    model_2_json,
    normalize_atomic_names,
    threshold_slider,
):
    # Pure-reactive normalization + structural similarity. Recomputes on
    # threshold or metric change. For example-sized models this is fast enough
    # to run live; gate behind a run_button if dogfood says otherwise.
    m2_aligned, _name_mappings = normalize_atomic_names(
        model_1_json,
        model_2_json,
        cosine_sim_optimized,
        threshold=threshold_slider.value,
    )
    struct_result = calculate_bpmn_similarity(
        model_1_json, m2_aligned, method=metric_radio.value
    )
    return m2_aligned, struct_result


@app.cell
def _structural_weight_sliders(mo, struct_result):
    # One slider per high-level category, in percent. Defaults pulled from
    # the result's ``weights_used``. Disabled when the corresponding score is
    # None (no data in either model on that axis).
    hls = struct_result["high_level_scores"]
    weights_used = struct_result.get("weights_used", {})
    has_subprocess = struct_result.get("has_expanded_subprocess", False)

    def _w(key, default_pct):
        return int(round(weights_used.get(key, default_pct / 100) * 100))

    elements_w = mo.ui.slider(
        start=0,
        stop=100,
        step=1,
        value=_w("elements", 35),
        label="Elements %",
        show_value=True,
        disabled=hls.get("elements") is None,
    )
    flows_w = mo.ui.slider(
        start=0,
        stop=100,
        step=1,
        value=_w("flows", 25),
        label="Flows %",
        show_value=True,
        disabled=hls.get("flows") is None,
    )
    org_w = mo.ui.slider(
        start=0,
        stop=100,
        step=1,
        value=_w("organizational", 20),
        label="Organizational %",
        show_value=True,
        disabled=hls.get("organizational") is None,
    )
    subprocess_w = mo.ui.slider(
        start=0,
        stop=100 if has_subprocess else 0,
        step=1,
        value=_w("subprocess", 20) if has_subprocess else 0,
        label="Subprocess %",
        show_value=True,
        disabled=(not has_subprocess) or hls.get("subprocess") is None,
    )
    return elements_w, flows_w, org_w, subprocess_w


@app.cell
def _structural_overall(
    elements_w,
    flows_w,
    org_w,
    struct_result,
    subprocess_w,
):
    # Compute the user-weighted overall score — mirrors the live-keys
    # rescaling in dashboard.py:580–599 so categories with no data don't drag
    # the average toward zero.
    _hls = struct_result["high_level_scores"]
    weights_pct = {
        "elements": elements_w.value,
        "flows": flows_w.value,
        "organizational": org_w.value,
        "subprocess": subprocess_w.value,
    }
    live_keys = [k for k, v in _hls.items() if v is not None]
    if not live_keys:
        overall = None
    else:
        live_weight_sum = sum(weights_pct[k] for k in live_keys)
        if live_weight_sum == 0:
            overall = None
        else:
            overall = sum(
                _hls[k] * weights_pct[k] for k in live_keys
            ) / live_weight_sum

    # Equal-weight overall, used as the comparison series in the left chart.
    live_count = len(live_keys)
    if live_count == 0:
        overall_equal = None
    else:
        overall_equal = sum(_hls[k] for k in live_keys) / live_count
    return overall, overall_equal, weights_pct


@app.cell
def _fig_weighted_contributions(
    NO_DATA_COLOR,
    fmt_pct,
    go,
    metric_radio,
    overall,
    overall_equal,
    struct_result,
    threshold_slider,
    weights_pct,
):
    # Plotly chart 1 — Weighted Contributions (left).
    _hls = struct_result["high_level_scores"]
    _keys = ["elements", "flows", "organizational", "subprocess"]
    _labels = ["Elements", "Flows", "Organizational", "Subprocess"]
    _present_flags = [_hls.get(_k) is not None for _k in _keys]
    _raw = [_hls.get(_k) if _p else 0 for _k, _p in zip(_keys, _present_flags)]

    _weights_norm = [
        weights_pct[_k] / 100.0 if weights_pct[_k] else 0 for _k in _keys
    ]
    _weighted = [s * w if p else 0 for s, w, p in zip(_raw, _weights_norm, _present_flags)]

    _live_count = sum(_present_flags) or 1
    _eq_w = 1.0 / _live_count
    _equal_weighted = [s * _eq_w if p else 0 for s, p in zip(_raw, _present_flags)]

    _max_val = max(_weighted + _equal_weighted) if (_weighted + _equal_weighted) else 0
    _xlim = max(0.5, _max_val * 1.3)

    _fig = go.Figure()
    _fig.add_bar(
        orientation="h",
        y=_labels,
        x=_equal_weighted,
        name=f"Equal weights ({fmt_pct(overall_equal)})",
        marker_color=NO_DATA_COLOR,
        opacity=0.55,
        hovertemplate="<b>%{y}</b><br>Equal-weight contribution: %{x:.3f}<extra></extra>",
    )
    _fig.add_bar(
        orientation="h",
        y=_labels,
        x=_weighted,
        name=f"Current weights ({fmt_pct(overall)})",
        marker_color="#2c3e50",
        opacity=0.92,
        hovertemplate="<b>%{y}</b><br>Weighted contribution: %{x:.3f}<extra></extra>",
    )

    # Grey "no data" overlay row(s).
    if not all(_present_flags):
        _fig.add_bar(
            orientation="h",
            y=[lbl for lbl, p in zip(_labels, _present_flags) if not p],
            x=[_xlim for p in _present_flags if not p],
            marker_color=NO_DATA_COLOR,
            opacity=0.35,
            showlegend=False,
            hoverinfo="skip",
        )
        for _lbl, _p in zip(_labels, _present_flags):
            if not _p:
                _fig.add_annotation(
                    x=_xlim * 0.5,
                    y=_lbl,
                    text="<i>N/A — no data in either model</i>",
                    showarrow=False,
                    font=dict(color="#64748b", size=11, family="sans-serif"),
                )

    # Watermark with the overall score.
    _fig.add_annotation(
        text=fmt_pct(overall),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        font=dict(size=56, color="#2c3e50", family="sans-serif"),
        opacity=0.18,
        showarrow=False,
    )

    _fig.update_layout(
        barmode="group",
        height=320,
        margin=dict(l=120, r=20, t=60, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        title=dict(
            text=(
                f"Weighted Contributions — {metric_radio.value.upper()} "
                f"@ threshold {threshold_slider.value:.2f}"
            ),
            font=dict(size=13, color="#0f172a"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        font=dict(family="sans-serif", color="#334155"),
    )
    _fig.update_xaxes(
        range=[0, _xlim],
        gridcolor="#eef0f3",
        title_text="Weighted score (score × weight)",
        title_font=dict(size=11),
    )
    _fig.update_yaxes(autorange="reversed", gridcolor="#eef0f3")
    fig_weighted = _fig
    return (fig_weighted,)


@app.cell
def _fig_element_breakdown(CATEGORY_COLORS, NO_DATA_COLOR, go, struct_result):
    # Plotly chart 2 — Element-level breakdown (right).
    _e_element_rows = [
        ("Activities", "activity_names", "elements"),
        ("Events", "event_names", "elements"),
        ("Gateways", "gateway_names", "elements"),
        ("Seq Flows", "seq_flows_str", "flows"),
        ("Msg Flows", "mes_flows_str", "flows"),
        ("Pool/Lane Names", "lane_names", "organizational"),
        ("Pool/Lane Elements", "lane_with_refs", "organizational"),
        ("Subprocess Names", "subprocess_names", "subprocess"),
        ("Subprocess Elements", "subprocess_elemrefs", "subprocess"),
        ("Subprocess Flows", "subprocess_flows", "subprocess"),
    ]
    _e_data_presence = struct_result.get("_e_data_presence", {})
    _e_labels, _e_scores, _e_colors, _e_presents = [], [], [], []
    for _e_label, _e_key, _e_category in _e_element_rows:
        _e_present = _e_data_presence.get(_e_key, True)
        _e_labels.append(_e_label if _e_present else f"{_e_label}  (no data)")
        _e_scores.append(struct_result.get(_e_key, 0) if _e_present else 0)
        _e_colors.append(CATEGORY_COLORS[_e_category] if _e_present else NO_DATA_COLOR)
        _e_presents.append(_e_present)

    _fig2 = go.Figure()
    _fig2.add_bar(
        orientation="h",
        y=_e_labels,
        x=_e_scores,
        marker_color=_e_colors,
        opacity=0.85,
        text=[f"{s:.2f}" if _e_p else "" for s, _e_p in zip(_e_scores, _e_presents)],
        textposition="outside",
        textfont=dict(size=10, color="#334155"),
        showlegend=False,
        hovertemplate="<b>%{y}</b><br>Raw score: %{x:.3f}<extra></extra>",
    )

    # Grey "no data" full-width band per missing row.
    for _e_lbl, _e_p in zip(_e_labels, _e_presents):
        if not _e_p:
            _fig2.add_bar(
                orientation="h",
                y=[_e_lbl],
                x=[1.1],
                marker_color=NO_DATA_COLOR,
                opacity=0.4,
                showlegend=False,
                hoverinfo="skip",
            )
            _fig2.add_annotation(
                x=0.55,
                y=_e_lbl,
                text="no data in either model",
                showarrow=False,
                font=dict(color="#64748b", size=10, family="sans-serif"),
            )

    # Manual _e_category legend via invisible scatter traces.
    for _e_cat, _e_label in [
        ("elements", "Elements"),
        ("flows", "Flows"),
        ("organizational", "Organizational"),
        ("subprocess", "Subprocess"),
    ]:
        _fig2.add_scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker=dict(size=10, color=CATEGORY_COLORS[_e_cat]),
            name=_e_label,
            showlegend=True,
        )
    _fig2.add_scatter(
        x=[None],
        y=[None],
        mode="markers",
        marker=dict(size=10, color=NO_DATA_COLOR),
        name="No data",
        showlegend=True,
    )

    _fig2.update_layout(
        height=420,
        barmode="overlay",
        margin=dict(l=140, r=30, t=60, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        title=dict(
            text="Element-Level Breakdown (unweighted)",
            font=dict(size=13, color="#0f172a"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        font=dict(family="sans-serif", color="#334155"),
    )
    _fig2.update_xaxes(
        range=[0, 1.15],
        gridcolor="#eef0f3",
        title_text="Raw score (0–1)",
        title_font=dict(size=11),
    )
    _fig2.update_yaxes(autorange="reversed", gridcolor="#eef0f3")
    fig_breakdown = _fig2
    return (fig_breakdown,)


@app.cell
def _structural_card(
    card,
    elements_w,
    fig_breakdown,
    fig_weighted,
    flows_w,
    fmt_pct,
    kpi_html,
    mo,
    org_w,
    overall,
    subprocess_w,
):
    weights_row = mo.hstack(
        [elements_w, flows_w, org_w, subprocess_w], justify="start", gap=2
    )
    _s_headline = mo.Html(kpi_html("Structural overall", fmt_pct(overall), "#2c3e50"))
    charts = mo.hstack([fig_weighted, fig_breakdown], widths="equal", gap=1)
    card("Structural similarity", weights_row, _s_headline, charts)
    return


@app.cell
def _trace_controls(mo):
    trace_timeout = mo.ui.slider(
        start=1, stop=30, step=1, value=5, label="Trace timeout (s)", show_value=True
    )
    loop_depth = mo.ui.slider(
        start=1, stop=6, step=1, value=3, label="Max loop depth", show_value=True
    )
    compute_button = mo.ui.run_button(
        label="Compute behavioral", kind="success"
    )
    return compute_button, loop_depth, trace_timeout


@app.cell
def _trace_controls_card(card, compute_button, loop_depth, mo, trace_timeout):
    card(
        "Trace extraction parameters",
        mo.md(
            "Trace extraction is the expensive step — click **Compute "
            "behavioral** to run it. Changing the metric or n-gram length "
            "below will _not_ re-extract."
        ),
        mo.hstack(
            [trace_timeout, loop_depth, compute_button],
            justify="start",
            gap=2,
        ),
    )
    return


@app.cell
def _extract_traces(
    compute_button,
    extract_traces,
    loop_depth,
    m2_aligned,
    mo,
    model_1_json,
    threshold_slider,
    trace_timeout,
):
    # Gated trace extraction. ``mo.stop`` short-circuits this cell — and
    # everything downstream that depends on its outputs — until the run button
    # has been clicked. Critically, this cell does NOT depend on
    # ``metric_radio`` or ``ngram_n``, so changes to either won't re-extract.
    #
    mo.stop(
        not compute_button.value,
        mo.md("_Click **Compute behavioral** to extract traces and score them._"),
    )

    tr1 = extract_traces(
        model_1_json,
        timeout_seconds=trace_timeout.value,
        max_loop_depth=loop_depth.value,
    )
    tr2 = extract_traces(
        m2_aligned,
        timeout_seconds=trace_timeout.value,
        max_loop_depth=loop_depth.value,
    )
    extraction_key = (
        threshold_slider.value,
        trace_timeout.value,
        loop_depth.value,
    )
    return extraction_key, tr1, tr2


@app.cell
def _behavioral_kind(mo):
    behavioral_kind = mo.ui.radio(
        options=["Full Trace", "N-gram"],
        value="Full Trace",
        label="Representation",
        inline=True,
    )
    ngram_n = mo.ui.slider(
        start=1,
        stop=5,
        step=1,
        value=2,
        label="n-gram n",
        show_value=True,
    )
    return behavioral_kind, ngram_n


@app.cell
def _behavioral_scores(
    behavioral_kind,
    calculate_ngram_similarity,
    calculate_trace_similarity,
    metric_radio,
    ngram_n,
    tr1,
    tr2,
):
    # Cheap recompute on metric / n / kind changes. Does NOT re-extract
    # — depends only on tr1, tr2 from the gated extraction cell.
    trace_score = calculate_trace_similarity(tr1, tr2, method=metric_radio.value)
    ngram_score = calculate_ngram_similarity(
        tr1, tr2, n=ngram_n.value, method=metric_radio.value
    )
    if behavioral_kind.value == "N-gram":
        active_score = ngram_score
    else:
        active_score = trace_score
    return (active_score,)


@app.cell
def _ngram_counts(extract_ngrams, ngram_n, tr1, tr2):
    # Mirrors ``_compute_ngram_counts`` in the original dashboard.
    n = ngram_n.value
    ngrams_1 = set(extract_ngrams(tr1, n=n, pad=True))
    ngrams_2 = set(extract_ngrams(tr2, n=n, pad=True))
    shared = len(ngrams_1 & ngrams_2)
    only_1 = len(ngrams_1 - ngrams_2)
    only_2 = len(ngrams_2 - ngrams_1)
    union = shared + only_1 + only_2
    overlap_pct = (shared / union) if union else 0.0
    ngram_counts = {
        "n": n,
        "total_1": len(ngrams_1),
        "total_2": len(ngrams_2),
        "shared": shared,
        "only_1": only_1,
        "only_2": only_2,
        "union": union,
        "overlap_pct": overlap_pct,
    }
    return (ngram_counts,)


@app.cell
def _behavioral_diagnostics(
    behavioral_kind,
    extraction_key,
    loop_depth,
    metric_radio,
    ngram_counts,
    ngram_n,
    threshold_slider,
    tr1,
    tr2,
    trace_timeout,
):
    # Compose the diagnostics block + n-gram summary HTML. Pure render,
    # no recomputation.
    current_key = (threshold_slider.value, trace_timeout.value, loop_depth.value)
    is_stale = extraction_key != current_key

    lines = []
    if is_stale:
        lines.append("⚠ STALE — re-click 'Compute behavioral' to refresh.")
        lines.append(
            f"   Last computed at threshold={extraction_key[0]:.2f}, "
            f"timeout={extraction_key[1]:.0f}s, max_loop={extraction_key[2]}"
        )
        lines.append(
            f"   Current settings: threshold={current_key[0]:.2f}, "
            f"timeout={current_key[1]:.0f}s, max_loop={current_key[2]}"
        )
        lines.append("")

    if not (tr1.is_sound and tr2.is_sound):
        lines.append("⚠ Behavioral comparison includes partial results")
        lines.append(
            f"   Model 1: {tr1.diagnostics.status.value} — {tr1.diagnostics.summary}"
        )
        lines.append(
            f"   Model 2: {tr2.diagnostics.status.value} — {tr2.diagnostics.summary}"
        )
        lines.append("")

    traces_1 = tr1.all_traces()
    traces_2 = tr2.all_traces()
    lines.append(f"Model 1: {len(traces_1)} trace variant(s)")
    lines.append(f"Model 2: {len(traces_2)} trace variant(s)")

    set_1 = {tuple(t) for t in traces_1}
    set_2 = {tuple(t) for t in traces_2}
    if set_1 or set_2:
        lines.append(
            f"Traces matched exactly: {len(set_1 & set_2)} / {len(set_1 | set_2)}"
        )

    diag_html_parts = []
    if is_stale:
        diag_html_parts.append(
            "<div class='pe-stale'>⚠ Stale — extraction parameters have "
            "changed since the last compute. Click "
            "<b>Compute behavioral</b> again to refresh.</div>"
        )
    diag_html_parts.append(
        "<div class='pe-diag'>" + "\n".join(lines) + "</div>"
    )
    diagnostics_html = "".join(diag_html_parts)

    plural = "s" if ngram_counts["total_1"] != 1 else ""
    ngram_summary_html = (
        "<div class='pe-muted' style='line-height:1.7;'>"
        f"<b>n = {ngram_counts['n']}</b>: Model 1 produced "
        f"<b>{ngram_counts['total_1']}</b> distinct n-gram{plural}; "
        f"Model 2 produced <b>{ngram_counts['total_2']}</b>.<br>"
        f"<b>{ngram_counts['shared']}</b> shared "
        f"(<b>{ngram_counts['overlap_pct']:.1%}</b> of the union of "
        f"<b>{ngram_counts['union']}</b>).<br>"
        f"<b>{ngram_counts['only_1']}</b> unique to Model 1, "
        f"<b>{ngram_counts['only_2']}</b> unique to Model 2."
        "</div>"
    )

    # Headline score label honors the kind + n + metric.
    if behavioral_kind.value == "N-gram":
        score_label = f"n-gram, n={ngram_n.value}, {metric_radio.value}"
    else:
        score_label = metric_radio.value
    return diagnostics_html, is_stale, ngram_summary_html, score_label


@app.cell
def _behavioral_card(
    CATEGORY_COLORS,
    active_score,
    behavioral_kind,
    card,
    diagnostics_html,
    fmt_pct,
    kpi_html,
    mo,
    ngram_n,
    ngram_summary_html,
    score_label,
):
    _b_headline = mo.Html(
        kpi_html(
            f"Behavioral ({score_label})",
            fmt_pct(active_score),
            CATEGORY_COLORS["behavioral"],
        )
    )
    card(
        "Behavioral similarity",
        mo.hstack([behavioral_kind, ngram_n], justify="start", gap=2),
        mo.Html(diagnostics_html),
        mo.Html(ngram_summary_html),
        _b_headline,
    )
    return


@app.cell
def _hybrid_weight(mo):
    hybrid_weight = mo.ui.slider(
        start=0.0,
        stop=1.0,
        step=0.05,
        value=0.5,
        label="Structural weight",
        show_value=True,
    )
    return (hybrid_weight,)


@app.cell
def _hybrid_compute(
    active_score,
    calculate_hybrid_similarity,
    hybrid_weight,
    overall,
):
    hybrid = calculate_hybrid_similarity(
        {"overall": overall},
        active_score,
        structural_weight=hybrid_weight.value,
    )
    return (hybrid,)


@app.cell
def _hybrid_card(
    behavioral_kind,
    card,
    fmt_pct,
    hybrid,
    hybrid_weight,
    is_stale,
    kpi_html,
    metric_radio,
    mo,
    ngram_n,
):
    behavioral_stale = is_stale and hybrid["behavioral"] is not None
    structural_stale_note = ""  # threshold drives both reactively, never stale here
    behavioral_stale_note = (
        " <span style='color:#b45309;'>⚠ behavioral is stale</span>"
        if behavioral_stale
        else ""
    )

    structural_line = (
        f"<div class='pe-muted'>Structural: <b>{fmt_pct(hybrid['structural'])}</b> "
        f"× {hybrid['structural_weight']:.0%}{structural_stale_note}</div>"
    )
    behavioral_line = (
        f"<div class='pe-muted'>Behavioral: <b>{fmt_pct(hybrid['behavioral'])}</b> "
        f"× {hybrid['behavioral_weight']:.0%}{behavioral_stale_note}</div>"
    )

    if hybrid["hybrid"] is None:
        kpi_label = "Hybrid (no data)"
    elif hybrid["structural"] is None:
        kpi_label = "Hybrid (behavioral only)"
    elif hybrid["behavioral"] is None:
        kpi_label = "Hybrid (structural only)"
    else:
        if behavioral_kind.value == "N-gram":
            kpi_label = (
                f"Hybrid (n-gram n={ngram_n.value}, {metric_radio.value})"
            )
        else:
            kpi_label = f"Hybrid ({metric_radio.value})"

    _h_headline = mo.Html(kpi_html(kpi_label, fmt_pct(hybrid["hybrid"]), "#0f172a"))
    card(
        "Hybrid similarity",
        hybrid_weight,
        mo.Html(structural_line),
        mo.Html(behavioral_line),
        _h_headline,
    )
    return


if __name__ == "__main__":
    app.run()
