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
    from model_evaluation.BPMN_conversion import BPMNConverter, XMLBPMNConverter
    from trace_extraction import extract_ngrams, extract_traces
    from utils.string_similarity import cosine_sim_optimized

    CATEGORY_COLORS = {
        "elements": "#3498db",        # Blue
        "flows": "#2ecc71",           # Green
        "organizational": "#f39c12",  # Orange
        "subprocess": "#9b59b6",      # Purple
        "behavioral": "#e74c3c",      # Red
    }
    NO_DATA_COLOR = "#95a5a6"
    REPO_ROOT = _repo_root
    EXAMPLES_DIR = _repo_root / "examples"
    return (
        BPMNConverter,
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
    .pe-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin: 0 0 14px 0;
    }
    .pe-card-title {
        margin: 0;
        font-weight: 600;
        font-size: 18px;
        color: #0f172a;
        letter-spacing: -0.01em;
    }
    .pe-info {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        font-size: 12px;
        font-weight: 600;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        color: #94a3b8;
        background: #f1f5f9;
        cursor: help;
        user-select: none;
        flex: 0 0 auto;
        transition: color .12s ease, background .12s ease;
    }
    .pe-info:hover, .pe-info:focus-within {
        color: #475569;
        background: #e2e8f0;
        outline: none;
    }
    .pe-info-bubble {
        position: absolute;
        top: calc(100% + 6px);
        right: 0;
        width: max-content;
        max-width: 520px;
        background: #ffffff;
        color: #334155;
        font-size: 12.5px;
        font-weight: 400;
        line-height: 1.45;
        text-align: left;
        padding: 10px 12px;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        box-shadow: 0 6px 18px rgba(15, 23, 42, .12);
        opacity: 0;
        visibility: hidden;
        transform: translateY(-4px);
        transition: opacity .12s ease, transform .12s ease, visibility 0s linear .12s;
        pointer-events: none;
        z-index: 1000;
        white-space: normal;
    }
    .pe-info:hover .pe-info-bubble,
    .pe-info:focus-within .pe-info-bubble {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
        transition: opacity .12s ease, transform .12s ease, visibility 0s linear 0s;
    }
    .pe-info-bubble ul { margin: 6px 0 0 0; padding-left: 18px; }
    .pe-info-bubble li { margin: 2px 0; }
    .pe-info-bubble code {
        background: #f1f5f9; border-radius: 4px;
        padding: 1px 5px; font-size: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
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
    .pe-chips { display: flex; flex-direction: column; gap: 8px;
        margin: 4px 0 8px 0; }
    .pe-chip-row { display: flex; flex-wrap: wrap; align-items: center;
        gap: 8px; font-size: 12.5px; color: #334155; }
    .pe-chip-label { font-weight: 600; min-width: 64px; color: #0f172a; }
    .pe-badge { color: white; font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 999px; letter-spacing: .02em;
        text-transform: capitalize; }
    .pe-chip { background: #f1f5f9; border-radius: 999px; padding: 2px 10px;
        font-variant-numeric: tabular-nums; }
    .pe-chip-sound   { color: #15803d; background: #dcfce7; }
    .pe-chip-partial { color: #b45309; background: #fef3c7; }
    .pe-chip-loop    { color: #6d28d9; background: #ede9fe; }
    .pe-chip-notes   { font-size: 12px; color: #64748b; padding-left: 76px; }
    .pe-norm-list {
        margin: 4px 0 0 0;
        padding: 6px 10px 6px 26px;
        max-height: 180px;
        overflow-y: auto;
        background: #f8fafc;
        border: 1px solid #eef0f3;
        border-radius: 8px;
        list-style: disc;
    }
    .pe-norm-list li { margin: 2px 0; font-size: 12.5px; }
    /* Inline radios — when wrapped in ``.pe-radio-spread`` the options
       fan out evenly across the full row width with a touch of side
       padding so the first/last circles aren't flush against the card
       edge. Targets marimo's inline radiogroup container. */
    .pe-radio-spread marimo-radio > div,
    .pe-radio-spread [role="radiogroup"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        justify-content: space-between !important;
        align-items: center !important;
        width: 100% !important;
        padding: 0 8px !important;
        gap: 8px !important;
    }
    .pe-radio-spread marimo-radio { display: block !important; width: 100% !important; }
    .pe-radio-spread marimo-radio label { text-transform: none; }
    </style>
    """

    def card(title: str, *body, info: str | None = None) -> "mo.Html":
        """Wrap a sequence of marimo elements in a styled card.

        We render the title and the body children inside a single
        ``mo.vstack`` so layout flows naturally; the surrounding card div
        comes from a thin HTML wrapper around the stack's HTML output.

        When ``info`` is provided, render a small "i" icon in the card's
        top-right corner that reveals the text on hover/focus. Pure CSS,
        no JS — see ``.pe-info`` / ``.pe-info-bubble`` in ``CARD_CSS``.

        ``info`` is interpolated as raw HTML so callers can embed bullet
        lists, ``<code>`` snippets, etc. All callsites here are internal /
        trusted; do not pass user-controlled strings without escaping.
        """
        inner = mo.vstack(list(body), gap=0.6)
        if info:
            info_html = (
                f"<span class='pe-info' tabindex='0' "
                f"aria-label='About this section'>"
                f"i"
                f"<span class='pe-info-bubble' role='tooltip'>"
                f"{info}"
                f"</span>"
                f"</span>"
            )
        else:
            info_html = ""
        return mo.Html(
            f"<div class='pe-card'>"
            f"<div class='pe-card-header'>"
            f"<div class='pe-card-title'>{title}</div>"
            f"{info_html}"
            f"</div>"
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

    def normalization_summary_html(name_mappings):
        """Short summary of what the normalization threshold did:
        total count, per-category breakdown, and the full list of mappings
        rendered in a scrollable panel.

        ``name_mappings`` is the dict returned by ``normalize_atomic_names``:
        keys are scopes (``activity_names``, ``event_names``, …, plus
        ``*__subprocess`` variants) and values are ``{model2_name: model1_name}``
        dicts.
        """
        # Category labels in display order; merge top-level + __subprocess scopes.
        # Each entry: (plural label for breakdown, singular label for per-row prefix, scope keys).
        categories = [
            ("activities", "Activity", ["activity_names", "activity_names__subprocess"]),
            ("events",     "Event",    ["event_names",    "event_names__subprocess"]),
            ("gateways",   "Gateway",  ["gateway_names",  "gateway_names__subprocess"]),
            ("pools",      "Pool",     ["pool_names"]),
            ("lanes",      "Lane",     ["lane_names"]),
        ]
        counts = {}
        for label, _singular, keys in categories:
            n = sum(len(name_mappings.get(k, {})) for k in keys)
            if n:
                counts[label] = n
        total = sum(counts.values())

        if total == 0:
            return mo.md(
                "_No names from Model 2 were aligned at the current threshold._"
            )

        breakdown = ", ".join(f"{n} {label}" for label, n in counts.items())

        # All mappings across all scopes, in the iteration order above.
        items = []
        for _label, singular, keys in categories:
            for k in keys:
                for src, dst in name_mappings.get(k, {}).items():
                    items.append((singular, src, dst))

        rows_html = "".join(
            f"<li><strong>{kind}:</strong> "
            f"<code>{src}</code> → <code>{dst}</code></li>"
            for kind, src, dst in items
        )
        return mo.Html(
            f"<div class='pe-muted' style='padding:4px 0 0 0;'>"
            f"<div><strong>{total}</strong> names from Model 2 mapped to Model 1 "
            f"({breakdown}).</div>"
            f"<div style='margin-top:4px;'>All mappings:</div>"
            f"<ul class='pe-norm-list'>{rows_html}</ul>"
            f"</div>"
        )

    mo.output.append(mo.Html(CARD_CSS))
    return card, fmt_pct, kpi_html, normalization_summary_html


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
    # Recursive scan of examples/ for supported model files (.bpmn for
    # BPMN 2.0 XML, .json for Signavio export). Display labels are
    # relative to examples/ so nested folders (e.g. maturity/...) are
    # visible in the dropdown and BPMN/JSON variants of the same model
    # sort next to each other.
    paths = sorted(
        list(EXAMPLES_DIR.rglob("*.bpmn")) + list(EXAMPLES_DIR.rglob("*.json"))
    )
    bpmn_options = {str(p.relative_to(EXAMPLES_DIR)): str(p) for p in paths}

    # Defaults: the P2P pair if present, otherwise the first two entries.
    _preferred_1 = "P2P - Running Example.bpmn"
    _preferred_2 = "P2P - Variant Running Example.bpmn"
    _keys = list(bpmn_options.keys())
    default_1 = _preferred_1 if _preferred_1 in bpmn_options else (_keys[0] if _keys else None)
    default_2 = _preferred_2 if _preferred_2 in bpmn_options else (_keys[1] if len(_keys) > 1 else default_1)
    # Flag for the downstream cards: when the user only has one model
    # file in examples/, both dropdowns default to it. We surface a
    # banner instead of silently comparing a model with itself (which
    # yields a misleading 100% similarity).
    only_one_file = len(_keys) < 2
    return bpmn_options, default_1, default_2, only_one_file


@app.cell
def _model_pickers(bpmn_options, default_1, default_2, mo):
    model1_dd = mo.ui.dropdown(
        options=bpmn_options,
        value=default_1,
        label="Model 1 (reference)",
        full_width=True,
    )
    model2_dd = mo.ui.dropdown(
        options=bpmn_options,
        value=default_2,
        label="Model 2 (compare)",
        full_width=True,
    )
    return model1_dd, model2_dd


@app.cell
def _models_card(card, mo, model1_dd, model2_dd, only_one_file):
    # Lay the two dropdowns side-by-side (equal-width columns, small gap)
    # so they each span half the card with a touch of breathing room on
    # the outer edges. ``full_width=True`` on the dropdowns themselves
    # makes them stretch to fill their column.
    #
    # When the user only has one model file in examples/, prepend a
    # warning banner so they don't mistake the resulting self-comparison
    # for a real result. The downstream ``_load_models`` cell also
    # refuses to proceed when both dropdowns point at the same file.
    _body = [mo.hstack([model1_dd, model2_dd], widths="equal", gap=1)]
    if only_one_file:
        _body.insert(
            0,
            mo.Html(
                "<div class='pe-stale'>"
                "Only one model file found in <code>examples/</code> — "
                "add a second file (or pick different ones below) to "
                "compare two distinct models."
                "</div>"
            ),
        )
    card(
        "Models",
        mo.vstack(_body, gap=0.8),
        info=(
            "Pick the two BPMN files to compare. Changing either model "
            "re-runs every section below."
        ),
    )
    return


@app.cell
def _load_models(BPMNConverter, XMLBPMNConverter, mo, model1_dd, model2_dd):
    # Parse the two selected model files into the minimal-BPMN dicts.
    #
    # Supports both BPMN 2.0 XML (.bpmn/.xml) and Signavio JSON (.json),
    # dispatched on suffix — mirrors the canonical ``load_model``
    # pattern documented in ``notebooks/model_eval_code_usage.ipynb``.
    # Both converters land in the same dict shape so everything
    # downstream is format-agnostic.
    #
    # Reactivity: re-runs whenever either dropdown changes. The XML
    # strings are kept around for the BPMN preview iframes below — for
    # JSON files xml1/xml2 stay None and the preview cell renders a
    # stub instead.
    #
    # Stop conditions:
    #  - either dropdown empty (initial render before defaults resolve,
    #    or no model files in examples/);
    #  - both dropdowns pointing at the same file (would silently
    #    produce a 100%-identical "comparison").
    mo.stop(
        not (model1_dd.value and model2_dd.value),
        mo.md("_Pick two model files above to load the models._"),
    )
    mo.stop(
        model1_dd.value == model2_dd.value,
        mo.md("_Pick two **different** model files to compare._"),
    )

    import json as _json
    from pathlib import Path as _Path

    def _load_one(path_str):
        path = _Path(path_str)
        if path.suffix.lower() in (".bpmn", ".xml"):
            return (
                XMLBPMNConverter.convert_file(path_str).to_dict(),
                path.read_text(encoding="utf-8"),
            )
        # Signavio JSON path — no XML preview available.
        with open(path_str, "r", encoding="utf-8") as fh:
            raw = _json.load(fh)
        return BPMNConverter.convert(raw).to_dict(), None

    model_1_json, xml1 = _load_one(model1_dd.value)
    model_2_json, xml2 = _load_one(model2_dd.value)
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
    #
    # When the selected file is Signavio JSON, xml1/xml2 is None — we
    # don't have a BPMN viewer for that format, so we render a small
    # stub message instead of failing. Similarity comparison further
    # down still runs because both formats land in the same dict shape.
    _label_1 = model1_dd.selected_key if hasattr(model1_dd, "selected_key") else "Model 1"
    _label_2 = model2_dd.selected_key if hasattr(model2_dd, "selected_key") else "Model 2"
    # selected_key isn't always available across marimo versions — fall back
    # to the value->label inverse lookup via the dropdown's options dict.
    try:
        _opts = model1_dd._options if hasattr(model1_dd, "_options") else None
    except Exception:
        _opts = None

    _json_stub = mo.Html(
        "<div style='padding: 28px; color: #64748b; font-style: italic; "
        "text-align: center; border: 1px dashed #cbd5e1; border-radius: 8px;'>"
        "Preview unavailable for Signavio JSON — comparison still runs below."
        "</div>"
    )

    diagrams = mo.vstack(
        [
            card(
                "Model 1",
                mo.Html(bpmn_iframe(xml1)) if xml1 is not None else _json_stub,
                info=(
                    "Rendered diagram of the first selected BPMN file "
                    "(bpmn-js viewer). Scroll to zoom, drag to pan."
                ),
            ),
            card(
                "Model 2",
                mo.Html(bpmn_iframe(xml2)) if xml2 is not None else _json_stub,
                info=(
                    "Rendered diagram of the second selected BPMN file "
                    "(bpmn-js viewer). Scroll to zoom, drag to pan."
                ),
            ),
        ],
        gap=1,
    )
    diagrams
    return


@app.cell
def _global_controls(mo):
    # Display labels are Capitalized; the radio's ``value`` stays
    # lowercase so the similarity functions keep working unchanged.
    metric_radio = mo.ui.radio(
        options={
            "Dice": "dice",
            "Jaccard": "jaccard",
            "Overlap": "overlap",
            "Precision": "precision",
            "Recall": "recall",
            "F1": "f1",
        },
        value="Dice",
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
def _global_card(card, metric_radio, mo, name_mappings, normalization_summary_html, threshold_slider):
    # Wrap the inline radio so the ``.pe-radio-spread`` CSS rule kicks in
    # — options fan out evenly across the full card width instead of
    # bunching at the left edge.
    _metric_row = mo.Html(
        "<div class='pe-radio-spread'>" + metric_radio.text + "</div>"
    )
    card(
        "Global controls",
        mo.md(
            "These two controls feed every section below. "
            "The threshold drives semantic name alignment; "
            "the metric is used for both structural and behavioral set comparisons."
        ),
        mo.vstack(
            [
                _metric_row,
                threshold_slider,
                normalization_summary_html(name_mappings),
            ],
            gap=1,
        ),
        info=(
            "Set-comparison metric and the semantic name-alignment "
            "threshold. Names from Model 2 with similarity above the "
            "threshold are aligned to their Model 1 counterpart before "
            "any set comparison."
            "<ul>"
            "<li><strong>Dice</strong>: harmonic-style overlap between "
            "the two sets.</li>"
            "<li><strong>Jaccard</strong>: overlap relative to the "
            "union of both sets.</li>"
            "<li><strong>Overlap</strong> (Szymkiewicz–Simpson): overlap "
            "relative to the smaller set.</li>"
            "<li><strong>Precision</strong>: share of Model 2 items "
            "that also appear in Model 1.</li>"
            "<li><strong>Recall</strong>: share of Model 1 items "
            "recovered by Model 2.</li>"
            "<li><strong>F1</strong>: harmonic mean of precision and "
            "recall.</li>"
            "</ul>"
        ),
    )
    return


@app.cell
def _normalize(
    cosine_sim_optimized,
    model_1_json,
    model_2_json,
    normalize_atomic_names,
    threshold_slider,
):
    # Semantic name alignment of Model 2 against Model 1's vocabulary. Lives
    # in its own cell so the Global Controls card's normalization-summary
    # panel can repaint as soon as alignment is done — without waiting on the
    # downstream structural / behavioral pipelines that also consume the
    # aligned model. Re-runs only on (model, threshold) change.
    m2_aligned, name_mappings = normalize_atomic_names(
        model_1_json,
        model_2_json,
        cosine_sim_optimized,
        threshold=threshold_slider.value,
    )
    return m2_aligned, name_mappings


@app.cell
def _structural_compute(
    calculate_bpmn_similarity,
    m2_aligned,
    metric_radio,
    model_1_json,
):
    # Structural similarity over the already-aligned Model 2. Reactive on
    # metric and (transitively, via ``m2_aligned``) threshold + models.
    # For example-sized models this is fast enough to run live; gate behind
    # a run_button if dogfood says otherwise.
    struct_result = calculate_bpmn_similarity(
        model_1_json, m2_aligned, method=metric_radio.value
    )
    return (struct_result,)


@app.cell
def _structural_weight_state(mo, struct_result):
    # Shared state for the four weight sliders, keyed by category. Sliders
    # both read from and write to this state, which lets external updates
    # (the Reset button, the auto-normalize on_change) rewrite all four
    # values in one go and have the sliders re-render at the new positions.
    _weights_used = struct_result.get("weights_used", {})
    _has_sub = struct_result.get("has_expanded_subprocess", False)

    def _init(key, default_pct):
        return int(round(_weights_used.get(key, default_pct / 100) * 100))

    # The values the sliders are seeded with on first render of this
    # model pair — derived from ``weights_used`` returned by the structural
    # similarity calculation (it normalizes against live categories). These
    # are also what the "Reset to default values" button restores, so a
    # reset returns the sliders to exactly the positions they had on load
    # for the currently-selected models.
    weight_initial = {
        "elements": _init("elements", 35),
        "flows": _init("flows", 25),
        "organizational": _init("organizational", 20),
        "subprocess": _init("subprocess", 20) if _has_sub else 0,
    }

    # Which categories are "live" — have a score in at least one model and,
    # for subprocess, an actually-expanded subprocess. Dead categories must
    # stay at 0 and not participate in normalization.
    _hls = struct_result["high_level_scores"]
    weight_live = {
        k: (_hls.get(k) is not None) and (k != "subprocess" or _has_sub)
        for k in ("elements", "flows", "organizational", "subprocess")
    }

    def rescale_to_100(weights, live, pin=None):
        """Rescale live categories so they sum to exactly 100.

        - Dead categories are forced to 0.
        - ``pin`` is an optional ``(key, value)`` for the slider the user
          just moved: that value is held fixed (clamped to [0, 100]) and
          the remaining ``100 - value`` is distributed across the *other*
          live categories proportionally to their current shares. If those
          others currently sum to 0, distribute equally.
        - Without ``pin``, all live categories share 100 proportionally to
          their current values; if they all happen to be 0, split evenly.
        - Uses largest-remainder rounding so the four returned integers
          sum to exactly 100 (avoids 33+33+33 = 99 artefacts).
        """
        keys = list(weights.keys())
        live_keys = [k for k in keys if live[k]]
        if not live_keys:
            return {k: 0 for k in keys}

        if pin is not None:
            pin_key, pin_val = pin
            pin_val = max(0, min(100, int(pin_val)))
            if pin_key not in live_keys:
                # Pinning a dead key shouldn't happen, but degrade gracefully.
                return rescale_to_100(weights, live)
            others = [k for k in live_keys if k != pin_key]
            if not others:
                # Only one live category — it gets whatever the user picked.
                return {k: (pin_val if k == pin_key else 0) for k in keys}
            remaining = 100 - pin_val
            other_sum = sum(weights[k] for k in others)
            if other_sum > 0:
                raw_others = {
                    k: (weights[k] / other_sum) * remaining for k in others
                }
            else:
                share = remaining / len(others)
                raw_others = {k: share for k in others}
            raw = {pin_key: float(pin_val)}
            raw.update(raw_others)
        else:
            live_sum = sum(weights[k] for k in live_keys)
            if live_sum > 0:
                raw = {k: (weights[k] / live_sum) * 100 for k in live_keys}
            else:
                share = 100 / len(live_keys)
                raw = {k: share for k in live_keys}

        # Largest-remainder rounding across the live keys only.
        floors = {k: int(raw[k]) for k in live_keys}
        remainder = 100 - sum(floors.values())
        order = sorted(
            live_keys, key=lambda k: raw[k] - floors[k], reverse=True
        )
        for k in order[: max(0, remainder)]:
            floors[k] += 1

        return {k: floors.get(k, 0) for k in keys}

    get_weights, set_weights = mo.state(
        dict(weight_initial),
        # The slider on_change handlers live in the same cell that reads
        # get_weights() to build the sliders. Without this, marimo blocks
        # the cell from re-running in response to its own set_weights() call
        # and the *other* sliders stay frozen at their old positions while
        # state is silently updated. Allowing the self-loop lets the cell
        # rebuild every slider at the rescaled value, so the proportional
        # auto-normalization is actually visible.
        allow_self_loops=True,
    )
    return (
        get_weights,
        rescale_to_100,
        set_weights,
        weight_initial,
        weight_live,
    )


@app.cell
def _structural_weight_sliders(
    get_weights,
    mo,
    rescale_to_100,
    set_weights,
    struct_result,
    weight_live,
):
    # One slider per high-level category, in percent. Values come from the
    # shared state cell above; an on_change handler rescales the other live
    # sliders proportionally so the live-categories sum stays at exactly 100
    # at every tick — no manual "normalize" step needed. Disabled when the
    # corresponding score is None (no data in either model on that axis).
    hls = struct_result["high_level_scores"]
    has_subprocess = struct_result.get("has_expanded_subprocess", False)
    _w = get_weights()

    def _make(key, label, disabled, stop=100):
        def _on_change(v, _k=key):
            # Pin the moved slider to v and redistribute the rest across
            # the other live categories. set_weights uses a lambda so we
            # rescale against the latest state, not a stale snapshot.
            set_weights(
                lambda s, _k=_k, _v=v: rescale_to_100(
                    s, weight_live, pin=(_k, _v)
                )
            )

        return mo.ui.slider(
            start=0,
            stop=stop,
            step=1,
            value=_w[key],
            label=label,
            show_value=True,
            disabled=disabled,
            on_change=_on_change,
        )

    elements_w = _make("elements", "Elements %", hls.get("elements") is None)
    flows_w = _make("flows", "Flows %", hls.get("flows") is None)
    org_w = _make("organizational", "Organizational %", hls.get("organizational") is None)
    subprocess_w = _make(
        "subprocess",
        "Subprocess %",
        (not has_subprocess) or hls.get("subprocess") is None,
        stop=100 if has_subprocess else 0,
    )
    return elements_w, flows_w, org_w, subprocess_w


@app.cell
def _structural_weight_controls(
    mo,
    set_weights,
    weight_initial,
):
    # Reset button — restores the slider values the cell first rendered
    # with for the currently-selected model pair (``weight_initial``), which
    # is what the user perceives as the "initial" state of the section.
    def _reset(_event):
        set_weights(dict(weight_initial))

    reset_button = mo.ui.button(label="Reset to default values", on_click=_reset)
    return (reset_button,)


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
    overall,
    overall_equal,
    struct_result,
    weights_pct,
):
    # Plotly chart 1 — Weighted Contributions (left).
    _hls = struct_result["high_level_scores"]
    _keys = ["elements", "flows", "organizational", "subprocess"]
    _labels = ["Elements", "Flows", "Organizational", "Subprocess"]

    # "Has data" per category is rolled up from the fine-grained
    # ``data_presence`` flags so the no-data banner triggers ONLY when both
    # models are empty for every fine key in that category — looser checks
    # (e.g. ``_hls.get(key) is not None``) can flip to "missing" for other
    # reasons.
    _dp = struct_result.get("data_presence", {})
    _category_fine_keys = {
        "elements":       ["activity_names", "event_names", "gateway_names"],
        "flows":          ["seq_flows_str", "mes_flows_str"],
        "organizational": ["lane_names", "lane_with_refs"],
        "subprocess":     ["subprocess_names", "subprocess_elemrefs", "subprocess_flows"],
    }
    _present_flags = [
        any(_dp.get(_fk, True) for _fk in _category_fine_keys[_k])
        for _k in _keys
    ]
    _raw = [_hls.get(_k) if _p else 0 for _k, _p in zip(_keys, _present_flags)]

    # Normalize weights against the live-category sum so the stacked bar
    # always sums in [0, 1] and matches the headline ``overall``, regardless
    # of whether the user has clicked Normalize. Mirrors the live-keys
    # rescaling in ``_structural_overall``.
    _live_sum = sum(weights_pct[_k] for _k, _p in zip(_keys, _present_flags) if _p) or 1
    _weights_norm = [
        (weights_pct[_k] / _live_sum) if (_p and weights_pct[_k]) else 0
        for _k, _p in zip(_keys, _present_flags)
    ]
    _weighted = [s * w if p else 0 for s, w, p in zip(_raw, _weights_norm, _present_flags)]

    _live_count = sum(_present_flags) or 1
    _eq_w = 1.0 / _live_count
    _equal_weighted = [s * _eq_w if p else 0 for s, p in zip(_raw, _present_flags)]

    _max_val = max(_weighted + _equal_weighted) if (_weighted + _equal_weighted) else 0
    _xlim = max(0.5, _max_val * 1.3)

    # Outside-bar numeric labels, blank on no-data rows so the banner row
    # isn't cluttered with stray ``0.00``s.
    _eq_text = [f"{v:.2f}" if p else "" for v, p in zip(_equal_weighted, _present_flags)]
    _cur_text = [f"{v:.2f}" if p else "" for v, p in zip(_weighted, _present_flags)]

    _fig = go.Figure()
    _fig.add_bar(
        orientation="h",
        y=_labels,
        x=_equal_weighted,
        name=f"Equal weights ({fmt_pct(overall_equal)})",
        marker_color=NO_DATA_COLOR,
        opacity=0.55,
        text=_eq_text,
        textposition="outside",
        textfont=dict(size=10, color="#334155"),
        hovertemplate="<b>%{y}</b><br>Equal-weight contribution: %{x:.3f}<extra></extra>",
    )
    _fig.add_bar(
        orientation="h",
        y=_labels,
        x=_weighted,
        name=f"Current weights ({fmt_pct(overall)})",
        marker_color="#2c3e50",
        opacity=0.92,
        text=_cur_text,
        textposition="outside",
        textfont=dict(size=10, color="#334155"),
        hovertemplate="<b>%{y}</b><br>Weighted contribution: %{x:.3f}<extra></extra>",
    )

    # Unified "no data in either model" banner — solid grey row spanning the
    # full axis with centered bold white text. Same treatment as the
    # element-level breakdown chart.
    _missing = [lbl for lbl, p in zip(_labels, _present_flags) if not p]
    if _missing:
        _fig.add_bar(
            orientation="h",
            y=_missing,
            x=[_xlim] * len(_missing),
            marker_color=NO_DATA_COLOR,
            opacity=0.6,
            showlegend=False,
            hoverinfo="skip",
        )
        for _lbl in _missing:
            _fig.add_annotation(
                x=_xlim / 2,
                y=_lbl,
                text="<b>No data in either model</b>",
                showarrow=False,
                xanchor="center",
                font=dict(color="#ffffff", size=12, family="sans-serif"),
            )

    # All four categories empty — overlay a single chart-spanning banner on
    # top of the per-row banners so the empty state is unmissable.
    if not any(_present_flags):
        _fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            text="<b>No data in either model</b>",
            showarrow=False,
            xanchor="center",
            yanchor="middle",
            font=dict(color="#ffffff", size=18, family="sans-serif"),
        )

    _fig.update_layout(
        barmode="group",
        height=480,
        margin=dict(l=120, r=20, t=110, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        title=dict(
            text="<b>Weighted contributions</b>",
            font=dict(size=15, color="#0f172a", family="sans-serif"),
            x=0,
            xanchor="left",
            y=0.97,
            yanchor="top",
            yref="container",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
            entrywidth=0,
            traceorder="normal",
        ),
        font=dict(family="sans-serif", color="#334155"),
    )
    _fig.update_xaxes(
        range=[0, _xlim],
        gridcolor="#eef0f3",
        title_text="Weighted score (score × weight)",
        title_font=dict(size=11),
    )
    _fig.update_yaxes(
        autorange="reversed",
        gridcolor="#eef0f3",
        ticklabelstandoff=8,
    )
    fig_weighted = _fig
    return (fig_weighted,)


@app.cell
def _fig_element_breakdown(CATEGORY_COLORS, NO_DATA_COLOR, go, struct_result):
    # Plotly chart 2 — Element-level breakdown (right).
    # Each *_names row is paired with its *_types sibling: the type score is
    # what differentiates AND/XOR/OR-substituted gateways even when names
    # normalize to 1.0, and what surfaces the small residual signal between
    # otherwise-disjoint processes (shared startEvent/endEvent types). Both
    # show up here so the headline overall is explainable from the chart.
    _e_element_rows = [
        ("Activity Names", "activity_names", "elements"),
        ("Activity Types", "activity_types", "elements"),
        ("Event Names", "event_names", "elements"),
        ("Event Types", "event_types", "elements"),
        ("Gateway Names", "gateway_names", "elements"),
        ("Gateway Types", "gateway_types", "elements"),
        ("Seq Flows", "seq_flows_str", "flows"),
        ("Msg Flows", "mes_flows_str", "flows"),
        ("Pool/Lane Names", "lane_names", "organizational"),
        ("Pool/Lane Elements", "lane_with_refs", "organizational"),
        ("Subprocess Names", "subprocess_names", "subprocess"),
        ("Subprocess Elements", "subprocess_elemrefs", "subprocess"),
        ("Subprocess Flows", "subprocess_flows", "subprocess"),
    ]
    _e_data_presence = struct_result.get("data_presence", {})
    _e_labels, _e_scores, _e_colors, _e_presents = [], [], [], []
    for _e_label, _e_key, _e_category in _e_element_rows:
        _e_present = _e_data_presence.get(_e_key, True)
        _e_labels.append(_e_label)
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

    # Unified "no data in either model" banner — solid grey row spanning the
    # full axis with centered bold white text. Same treatment as the
    # weighted-contributions chart.
    _e_missing = [lbl for lbl, p in zip(_e_labels, _e_presents) if not p]
    if _e_missing:
        _fig2.add_bar(
            orientation="h",
            y=_e_missing,
            x=[1.15] * len(_e_missing),
            marker_color=NO_DATA_COLOR,
            opacity=0.6,
            showlegend=False,
            hoverinfo="skip",
        )
        for _e_lbl in _e_missing:
            _fig2.add_annotation(
                x=1.15 / 2,
                y=_e_lbl,
                text="<b>No data in either model</b>",
                showarrow=False,
                xanchor="center",
                font=dict(color="#ffffff", size=12, family="sans-serif"),
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

    _fig2.update_layout(
        height=480,
        barmode="overlay",
        margin=dict(l=140, r=30, t=110, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
        title=dict(
            text="<b>Element-level breakdown</b>",
            font=dict(size=15, color="#0f172a", family="sans-serif"),
            x=0,
            xanchor="left",
            y=0.97,
            yanchor="top",
            yref="container",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
            entrywidth=0,
            traceorder="normal",
        ),
        font=dict(family="sans-serif", color="#334155"),
    )
    _fig2.update_xaxes(
        range=[0, 1.15],
        gridcolor="#eef0f3",
        title_text="Raw score (0–1)",
        title_font=dict(size=11),
    )
    _fig2.update_yaxes(
        autorange="reversed",
        gridcolor="#eef0f3",
        ticklabelstandoff=8,
    )
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
    mo,
    org_w,
    overall,
    reset_button,
    subprocess_w,
):
    # Two rows of two sliders each — at four-up the slider track and the
    # right-hand value label fight for a column that's too narrow once the
    # card padding is taken out, so the value clips. 2×2 lets each slider
    # have ~50% of the card width and reflow as the page resizes. A third
    # row holds the Reset button, right-aligned.
    weights_row = mo.vstack(
        [
            mo.hstack([elements_w, flows_w], widths="equal", gap=2),
            mo.hstack([org_w, subprocess_w], widths="equal", gap=2),
            mo.hstack([reset_button], justify="end", gap=2),
        ],
        gap=1,
    )
    # Charts read left-to-right as inputs → result: the per-element breakdown
    # on the left, the weighted contributions that compose it into the overall
    # score on the right.
    charts = mo.hstack([fig_breakdown, fig_weighted], widths="equal", gap=2)
    # Extra breathing room between the slider/button row and the charts —
    # the third weights_row line otherwise sits visually flush against the
    # chart titles.
    _spacer = mo.Html("<div style='height:14px'></div>")
    # Hero footer block: the card's headline number sits in a tinted band
    # below the charts so it reads as a real summary, not a stat squeezed
    # into the title. Flex layout keeps the label on the left and the big
    # percentage hugging the right edge regardless of card width.
    _hero_html = (
        "<div style='"
        "margin-top:18px;"
        "background:#eef2ff;"
        "border:1px solid #c7d2fe;"
        "border-radius:12px;"
        "padding:16px 24px;"
        "display:flex;"
        "align-items:center;"
        "justify-content:space-between;"
        "gap:24px;"
        "'>"
        "<div style='"
        "color:#475569;"
        "font-size:13px;"
        "font-weight:600;"
        "text-transform:uppercase;"
        "letter-spacing:0.06em;"
        "'>Structural overall</div>"
        "<div style='"
        "color:#1e293b;"
        "font-size:32px;"
        "font-weight:700;"
        "line-height:1;"
        "font-variant-numeric:tabular-nums;"
        f"'>{fmt_pct(overall)}</div>"
        "</div>"
    )
    _hero = mo.Html(_hero_html)
    card(
        "Structural similarity",
        weights_row,
        _spacer,
        charts,
        _hero,
        info=(
            "Compares the static structure of the two models across "
            "five components (activities, gateways, events, "
            "pools/lanes, and edges) using the chosen set metric. "
            "Each component contributes its own similarity score; the "
            "overall score is a weighted average of these scores, "
            "with the weights taken from the sliders above."
        ),
    )
    return


@app.cell
def _extract_traces(
    extract_traces,
    m2_aligned,
    model_1_json,
):
    # Reactive trace extraction. Re-runs whenever ``m2_aligned`` or
    # ``model_1_json`` changes (model selection, normalization threshold,
    # metric). Trace timeout and max-loop-depth are pinned to sensible
    # defaults — the original ipywidgets dashboard exposed them as sliders
    # but they're rarely touched in practice, and the run-button gate
    # added more friction than it saved.
    TRACE_TIMEOUT = 15  # seconds; raised from 5 to let the P2P examples
                        # enumerate their full trace set deterministically
                        # before the Petri-net explorer's wall-clock budget
                        # trips. The 20k active-set cap in petri.py is the
                        # ultimate backstop against pathological models.
    LOOP_DEPTH = 3

    tr1 = extract_traces(
        model_1_json,
        timeout_seconds=TRACE_TIMEOUT,
        max_loop_depth=LOOP_DEPTH,
    )
    tr2 = extract_traces(
        m2_aligned,
        timeout_seconds=TRACE_TIMEOUT,
        max_loop_depth=LOOP_DEPTH,
    )
    return tr1, tr2


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
def _behavioral_set_counts(behavioral_kind, extract_ngrams, ngram_n, tr1, tr2):
    # Single source of truth for the only_1 / shared / only_2 / union numbers
    # consumed by both the diagnostics block and the set-overlap chart. Owns
    # the arithmetic for both kinds — n-gram sets come from
    # ``extract_ngrams`` (with padding to match the headline similarity
    # score), trace sets from ``all_traces``.
    if behavioral_kind.value == "N-gram":
        _n = ngram_n.value
        _set_1 = set(extract_ngrams(tr1, n=_n, pad=True))
        _set_2 = set(extract_ngrams(tr2, n=_n, pad=True))
        _unit = f"{_n}-grams"
    else:
        _set_1 = {tuple(t) for t in tr1.all_traces()}
        _set_2 = {tuple(t) for t in tr2.all_traces()}
        _unit = "trace variants"
    _shared = len(_set_1 & _set_2)
    _only_1 = len(_set_1 - _set_2)
    _only_2 = len(_set_2 - _set_1)
    set_counts = {
        "only_1": _only_1,
        "shared": _shared,
        "only_2": _only_2,
        "union": _shared + _only_1 + _only_2,
        "unit": _unit,
    }
    return (set_counts,)


@app.cell
def _fig_behavioral_overlap(go, mo, set_counts):
    # Single horizontal stacked bar — Only-Model-1 / Shared / Only-Model-2.
    # Visualizes what DICE / Jaccard are computing on the same set: how
    # the union splits between the two models. Mirrors the layout of the
    # structural charts (title pinned to container top, h-orient legend
    # just below) so the two sections look like one family.
    # Locals are underscore-prefixed so marimo doesn't promote them to
    # global names that conflict with ``_behavioral_set_counts``.
    _only_1 = set_counts["only_1"]
    _shared = set_counts["shared"]
    _only_2 = set_counts["only_2"]
    _union = set_counts["union"]
    _unit = set_counts["unit"]

    if _union == 0:
        # Degenerate case: no traces / n-grams on either side. Bar would
        # divide by zero; render a quiet placeholder instead. Wrap in
        # mo.Html so it sits at the same vstack position the chart would.
        fig_behavioral = mo.Html(
            "<div class='pe-muted' style='padding:14px 0;'>"
            f"No {_unit} extracted — set-overlap chart unavailable."
            "</div>"
        )
    else:
        _fig = go.Figure()
        _segments = [
            ("Only Model 1", _only_1, "#3498db"),
            ("Shared",        _shared, "#2c3e50"),
            ("Only Model 2", _only_2, "#9b59b6"),
        ]
        for _name, _count, _color in _segments:
            _pct = _count / _union
            # Hide the inside text label for very thin segments — it would
            # overflow into a neighbour and look broken.
            _text = f"{_count:,} {_unit} • {_pct:.1%}" if _pct >= 0.06 else ""
            _fig.add_bar(
                name=_name,
                x=[_count],
                y=[" "],
                orientation="h",
                marker_color=_color,
                text=[_text],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="white", size=12),
                customdata=[[_pct]],
                hovertemplate=(
                    f"{_name}: %{{x:,}} ({_pct:.1%} of union)<extra></extra>"
                ),
            )

        _fig.update_layout(
            barmode="stack",
            height=180,
            margin=dict(l=20, r=20, t=90, b=30),
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=True,
            bargap=0.0,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                font=dict(size=11),
                itemclick=False,
                itemdoubleclick=False,
                traceorder="normal",
            ),
            title=dict(
                text=f"<b>Across both models, {_union:,} unique {_unit}</b>",
                font=dict(size=15, color="#0f172a", family="sans-serif"),
                x=0,
                xanchor="left",
                y=0.97,
                yanchor="top",
                yref="container",
            ),
            font=dict(family="sans-serif", color="#334155"),
        )
        _fig.update_xaxes(visible=False, range=[0, _union])
        _fig.update_yaxes(visible=False)
        fig_behavioral = _fig
    return (fig_behavioral,)


@app.cell
def _behavioral_diagnostics(behavioral_kind, metric_radio, ngram_n, tr1, tr2):
    # One quiet sentence per model: status, then the underlying counts
    # (sound / partial / loop-cap when nonzero), then truncation notes
    # when present. Replaces the colored badge + pill chips, which read
    # as more important than the KPI below them.
    #
    # "sound" = traces that reached the final marking exactly (complete
    # executions). "partial" = prefixes that ended in a deadlock or were
    # cut off by the loop-depth cap. When truncation flags are set, the
    # numbers are by definition incomplete — surface that prominently
    # rather than as a quiet trailing clause.
    def _chips_for(label, tr):
        d = tr.diagnostics
        status_text = d.status.value.replace("_", " ")
        parts = [
            f"{d.sound_variant_count:,} complete variant(s)",
            f"{d.partial_trace_count:,} partial trace(s)",
        ]
        loop_total = sum(d.loop_cap_hits.values())
        if loop_total:
            parts.append(f"{loop_total:,} loop-cap hit(s)")
        notes = []
        if d.truncated_by_timeout:
            notes.append("timed out")
        if d.truncated_by_active_cap:
            notes.append("active-set cap")
        counts = ", ".join(parts)
        if notes:
            warn = (
                f" <strong style='color:#b45309;'>"
                f"counts incomplete — exploration truncated by "
                f"{', '.join(notes)}</strong>"
            )
        else:
            warn = ""
        return f"<div>{label}: {status_text}; {counts}.{warn}</div>"

    diagnostics_html = (
        "<div class='pe-muted' style='padding:2px 0 4px 0;'>"
        f"{_chips_for('Model 1', tr1)}"
        f"{_chips_for('Model 2', tr2)}"
        "</div>"
    )

    # Headline score label honors the kind + n + metric.
    if behavioral_kind.value == "N-gram":
        score_label = f"n-gram, n={ngram_n.value}, {metric_radio.value}"
    else:
        score_label = metric_radio.value
    return diagnostics_html, score_label


@app.cell
def _behavioral_card(
    active_score,
    behavioral_kind,
    card,
    diagnostics_html,
    fig_behavioral,
    fmt_pct,
    mo,
    ngram_n,
):
    # Subtitle shows only the *kind* of behavioral comparison (Full Trace or
    # N-gram with its n) — not the distance metric, which lives in the
    # diagnostics block above.
    if behavioral_kind.value == "N-gram":
        _b_subtitle = f"N-gram (n={ngram_n.value})"
    else:
        _b_subtitle = behavioral_kind.value

    # Hero footer block — mirrors the structural card so all three section
    # summaries share the same tinted band, label/value layout, and sizing.
    # Two-line label: "Behavioral overall" on top, the active scorer kind
    # as a lighter subtitle.
    _b_hero_html = (
        "<div style='"
        "margin-top:18px;"
        "background:#eef2ff;"
        "border:1px solid #c7d2fe;"
        "border-radius:12px;"
        "padding:16px 24px;"
        "display:flex;"
        "align-items:center;"
        "justify-content:space-between;"
        "gap:24px;"
        "'>"
        "<div>"
        "<div style='"
        "color:#475569;"
        "font-size:13px;"
        "font-weight:600;"
        "text-transform:uppercase;"
        "letter-spacing:0.06em;"
        "'>Behavioral overall</div>"
        "<div style='"
        "color:#64748b;"
        "font-size:12px;"
        "font-weight:400;"
        "margin-top:4px;"
        f"'>{_b_subtitle}</div>"
        "</div>"
        "<div style='"
        "color:#1e293b;"
        "font-size:32px;"
        "font-weight:700;"
        "line-height:1;"
        "font-variant-numeric:tabular-nums;"
        f"'>{fmt_pct(active_score)}</div>"
        "</div>"
    )
    _b_hero = mo.Html(_b_hero_html)
    card(
        "Behavioral similarity",
        mo.hstack([behavioral_kind, ngram_n], widths="equal", gap=2),
        mo.Html(diagnostics_html),
        fig_behavioral,
        _b_hero,
        info=(
            "Compares execution behavior by extracting traces from each "
            "model's Petri-net semantics and measuring set overlap."
            "<p>Each trace is one feasible end-to-end execution. A "
            "<strong>loop-depth cap</strong> (pinned at 3) bounds how "
            "often a trace may re-enter the same marking, so loops in the "
            "BPMN model contribute finitely many unrolled iterations. "
            "Traces are classified as:</p>"
            "<ul>"
            "<li><strong>Complete</strong> — reached the final marking "
            "cleanly; a real, valid execution of the model.</li>"
            "<li><strong>Partial</strong> — recorded as a prefix because "
            "either the loop-depth cap was hit (the trace would unroll a "
            "4th time) or the explorer reached a deadlock marking (no "
            "transition enabled, final marking not reached — a soundness "
            "defect in the model).</li>"
            "</ul>"
            "Both kinds feed into the score so loops and soundness issues "
            "are not silently penalised; the diagnostics line above "
            "reports the split per model."
            "<p>Pick the comparison granularity and, for n-grams, the "
            "length:</p>"
            "<ul>"
            "<li><strong>Full Trace</strong> — each end-to-end trace is "
            "one set element; only models sharing entire variants score "
            "high.</li>"
            "<li><strong>1-gram</strong> (unigram) — single activities; "
            "captures which steps appear at all.</li>"
            "<li><strong>2-gram</strong> (bigram) — pairs of consecutive "
            "activities; captures directly-follows relationships.</li>"
            "<li><strong>3-gram</strong> (trigram) — three consecutive "
            "activities; captures short ordering patterns.</li>"
            "<li><strong>4-gram</strong> (tetragram) — four consecutive "
            "activities; captures medium-range ordering patterns.</li>"
            "<li><strong>5-gram</strong> (pentagram) — five consecutive "
            "activities; captures longer ordering patterns.</li>"
            "</ul>"
            "Larger n approaches the strictness of the full-trace view; "
            "smaller n probes local control flow and tolerates more "
            "divergence. The chart below shows how the resulting set "
            "splits between only-Model-1, shared, and only-Model-2."
        ),
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
    card,
    fmt_pct,
    hybrid,
    hybrid_weight,
    mo,
):
    # Threshold drives both structural and behavioral reactively, so neither
    # side can be stale relative to the other — no banner needed.
    structural_line = (
        f"<div class='pe-muted'>Structural: <b>{fmt_pct(hybrid['structural'])}</b> "
        f"× {hybrid['structural_weight']:.0%}</div>"
    )
    behavioral_line = (
        f"<div class='pe-muted'>Behavioral: <b>{fmt_pct(hybrid['behavioral'])}</b> "
        f"× {hybrid['behavioral_weight']:.0%}</div>"
    )

    # Hero footer block — same styling as the structural and behavioral cards
    # so all three summaries share the same visual weight. Single-line label;
    # the diagnostic lines above already spell out which components feed in.
    _h_hero_html = (
        "<div style='"
        "margin-top:18px;"
        "background:#eef2ff;"
        "border:1px solid #c7d2fe;"
        "border-radius:12px;"
        "padding:16px 24px;"
        "display:flex;"
        "align-items:center;"
        "justify-content:space-between;"
        "gap:24px;"
        "'>"
        "<div style='"
        "color:#475569;"
        "font-size:13px;"
        "font-weight:600;"
        "text-transform:uppercase;"
        "letter-spacing:0.06em;"
        "'>Hybrid overall</div>"
        "<div style='"
        "color:#1e293b;"
        "font-size:32px;"
        "font-weight:700;"
        "line-height:1;"
        "font-variant-numeric:tabular-nums;"
        f"'>{fmt_pct(hybrid['hybrid'])}</div>"
        "</div>"
    )
    _h_hero = mo.Html(_h_hero_html)
    card(
        "Hybrid similarity",
        hybrid_weight,
        mo.Html(structural_line),
        mo.Html(behavioral_line),
        _h_hero,
        info=(
            "Weighted combination of the structural and behavioral "
            "scores above. The slider biases the blend toward one or "
            "the other."
        ),
    )
    return


if __name__ == "__main__":
    app.run()
