# """
# BPMN Similarity Visualization Module

# Interactive widgets for exploring BPMN model similarity results.

# Usage:
#     from bpmn_visualization import create_similarity_dashboard

#     # In Jupyter notebook:
#     dashboard = create_similarity_dashboard(
#         model_1,
#         model_2,
#         similarity_func=bert_cosine_optimized,
#         calculate_similarity_func=calculate_bpmn_similarity,
#         normalize_func=normalize_atomic_names,
#         initial_threshold=0.7
#     )
#     dashboard.display()
# """

# import ipywidgets as widgets
# from IPython.display import display, clear_output
# import matplotlib.pyplot as plt
# import matplotlib.patches as mpatches
# import numpy as np


# # Color scheme for categories
# CATEGORY_COLORS = {
#     "structural": "#3498db",  # Blue
#     "flows": "#2ecc71",       # Green
#     "organizational": "#f39c12",  # Orange
#     "subprocess": "#9b59b6",  # Purple
#     "behavioral": "#e74c3c",  # Red
# }


# class BPMNSimilarityDashboard:
#     """Interactive dashboard for BPMN similarity exploration."""

#     def __init__(
#         self,
#         model_1,
#         model_2,
#         similarity_func,
#         calculate_similarity_func,
#         normalize_func,
#         initial_threshold=0.7,
#         initial_method="dice",
#         initial_trace_timeout=5.0,
#         initial_max_loop_depth=3,
#     ):
#         """
#         Initialize the dashboard.

#         Args:
#             model_1: Reference BPMN model (ground truth)
#             model_2: BPMN model to compare
#             similarity_func: String similarity function for normalization
#             calculate_similarity_func: Function to calculate BPMN similarity.
#                 Must accept ``behavioral=``, ``trace_timeout_seconds=``,
#                 ``max_loop_depth=`` keyword args (matches
#                 ``calculate_bpmn_similarity``'s contract).
#             normalize_func: Function to normalize atomic names
#             initial_threshold: Initial normalization threshold (default: 0.7)
#             initial_method: Initial similarity method (default: "dice")
#             initial_trace_timeout: Initial trace-extraction timeout in seconds
#                 (default: 5.0)
#             initial_max_loop_depth: Initial max loop depth for trace extraction
#                 (default: 3)
#         """
#         self.model_1 = model_1
#         self.model_2 = model_2
#         self.similarity_func = similarity_func
#         self.calculate_similarity = calculate_similarity_func
#         self.normalize_func = normalize_func

#         self.current_metric = initial_method
#         self.current_threshold = initial_threshold
#         self.current_trace_timeout = initial_trace_timeout
#         self.current_max_loop_depth = initial_max_loop_depth

#         # Store the threshold used for initial normalization (for comparison later)
#         # This is the FIX: we compare against this, not self.current_threshold
#         self._normalized_with_threshold = initial_threshold

#         # Cache for results: (metric, threshold, trace_timeout, max_loop_depth)
#         # → (normalized_model, result). Behavioral is always on in the dashboard,
#         # so it isn't part of the key.
#         self.results_cache = {}

#         # Initial normalization and calculation
#         self.model_2_normalized, self.initial_mappings = normalize_func(
#             model_1, model_2, similarity_func, threshold=initial_threshold
#         )

#         # Initial calculation — behavioral is always on so the dashboard can
#         # render the fifth category bar. Default behavioral weight is 0%, so
#         # the overall score remains identical to a structural-only computation
#         # until the user moves the slider.
#         self.base_result = calculate_similarity_func(
#             model_1,
#             self.model_2_normalized,
#             method=initial_method,
#             behavioral=True,
#             trace_timeout_seconds=initial_trace_timeout,
#             max_loop_depth=initial_max_loop_depth,
#         )
#         self.results_cache[
#             (initial_method, initial_threshold, initial_trace_timeout, initial_max_loop_depth)
#         ] = (self.model_2_normalized, self.base_result)

#         self.has_subprocess = self.base_result.get("has_expanded_subprocess", False)
#         self.default_weights = self.base_result["weights_used"]

#         # Create widgets
#         self._create_widgets()

#     def _create_widgets(self):
#         """Create all interactive widgets."""
#         self.output = widgets.Output()
#         self.message_output = widgets.Output()

#         # Weight sliders
#         self.structural_slider = widgets.FloatSlider(
#             value=self.default_weights["structural"] * 100,
#             min=0, max=100, step=1,
#             description="Structural (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.flows_slider = widgets.FloatSlider(
#             value=self.default_weights["flows"] * 100,
#             min=0, max=100, step=1,
#             description="Flows (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.organizational_slider = widgets.FloatSlider(
#             value=self.default_weights["organizational"] * 100,
#             min=0, max=100, step=1,
#             description="Org (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.subprocess_slider = widgets.FloatSlider(
#             value=self.default_weights["subprocess"] * 100,
#             min=0, max=100 if self.has_subprocess else 0,
#             step=1,
#             description="Subprocess (%):",
#             continuous_update=False,
#             disabled=not self.has_subprocess,
#             style={'description_width': '100px'}
#         )
#         # Behavioral starts at 0% so existing structural-only overall scores
#         # are preserved by default; users opt in by raising the slider.
#         self.behavioral_slider = widgets.FloatSlider(
#             value=self.default_weights.get("behavioral", 0.0) * 100,
#             min=0, max=100, step=1,
#             description="Behavioral (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )

#         # Trace-extraction tuning
#         self.trace_timeout_slider = widgets.FloatSlider(
#             value=self.current_trace_timeout,
#             min=1.0, max=30.0, step=1.0,
#             description="Trace timeout (s):",
#             continuous_update=False,
#             readout_format=".0f",
#             style={'description_width': '100px'}
#         )
#         self.loop_depth_slider = widgets.IntSlider(
#             value=self.current_max_loop_depth,
#             min=1, max=6, step=1,
#             description="Max loop depth:",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )

#         # Threshold slider
#         self.threshold_slider = widgets.FloatSlider(
#             value=self.current_threshold,
#             min=0.0, max=1.0, step=0.05,
#             description="Threshold:",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.threshold_slider.observe(self._on_threshold_change, names="value")

#         # Metric buttons
#         self.metric_buttons = {
#             "dice": widgets.Button(description="Dice", button_style="primary"),
#             "jaccard": widgets.Button(description="Jaccard", button_style=""),
#             "precision": widgets.Button(description="Precision", button_style=""),
#             "recall": widgets.Button(description="Recall", button_style=""),
#             "f1": widgets.Button(description="F1", button_style=""),
#         }
#         for metric, button in self.metric_buttons.items():
#             button.on_click(lambda b, m=metric: self._set_metric(m))

#         # Control buttons
#         self.recalculate_button = widgets.Button(
#             description="Recalculate",
#             button_style="success",
#             icon="refresh"
#         )
#         self.recalculate_button.on_click(self._recalculate)

#         self.reset_button = widgets.Button(
#             description="Reset to Default",
#             button_style="info",
#             icon="undo"
#         )
#         self.reset_button.on_click(self._reset_to_defaults)

#     def _normalize_weights(self, structural, flows, organizational, subprocess, behavioral):
#         """Normalize weights to sum to 1.0."""
#         if not self.has_subprocess:
#             subprocess = 0.0
#         total = structural + flows + organizational + subprocess + behavioral
#         if total == 0:
#             return (
#                 self.default_weights["structural"],
#                 self.default_weights["flows"],
#                 self.default_weights["organizational"],
#                 self.default_weights["subprocess"],
#                 self.default_weights.get("behavioral", 0.0),
#             )
#         return (
#             structural / total,
#             flows / total,
#             organizational / total,
#             subprocess / total,
#             behavioral / total,
#         )

#     def _get_result_for_metric_and_threshold(self, metric, threshold):
#         """Get or calculate result for given metric and threshold."""
#         cache_key = (
#             metric,
#             threshold,
#             self.current_trace_timeout,
#             self.current_max_loop_depth,
#         )

#         if cache_key not in self.results_cache:
#             # FIX: Compare against _normalized_with_threshold (initial), not current_threshold
#             if abs(threshold - self._normalized_with_threshold) > 0.001:
#                 # Different threshold, need to renormalize
#                 normalized, _ = self.normalize_func(
#                     self.model_1, self.model_2,
#                     self.similarity_func, threshold=threshold
#                 )
#             else:
#                 # Same as initial threshold, use cached normalized model
#                 normalized = self.model_2_normalized

#             result = self.calculate_similarity(
#                 self.model_1,
#                 normalized,
#                 method=metric,
#                 behavioral=True,
#                 trace_timeout_seconds=self.current_trace_timeout,
#                 max_loop_depth=self.current_max_loop_depth,
#             )
#             self.results_cache[cache_key] = (normalized, result)

#         return self.results_cache[cache_key]

#     def _set_metric(self, metric_name):
#         """Change the active metric."""
#         self.current_metric = metric_name

#         for name, button in self.metric_buttons.items():
#             button.button_style = "primary" if name == metric_name else ""

#         self._recalculate(None)

#     def _on_threshold_change(self, change):
#         """Handle threshold slider changes."""
#         self.current_threshold = change["new"]

#     def _on_trace_timeout_change(self, change):
#         """Trace-extraction timeout changed — record it; cache key picks it up."""
#         self.current_trace_timeout = change["new"]

#     def _on_loop_depth_change(self, change):
#         """Max loop depth changed — record it; cache key picks it up."""
#         self.current_max_loop_depth = change["new"]

#     def _recalculate(self, button):
#         """Recalculate and update visualization."""
#         # Get slider values (convert from percentage)
#         structural = self.structural_slider.value / 100.0
#         flows = self.flows_slider.value / 100.0
#         organizational = self.organizational_slider.value / 100.0
#         subprocess = self.subprocess_slider.value / 100.0
#         behavioral = self.behavioral_slider.value / 100.0

#         # Normalize weights
#         structural, flows, organizational, subprocess, behavioral = self._normalize_weights(
#             structural, flows, organizational, subprocess, behavioral
#         )

#         # Update sliders to show normalized values
#         total = (self.structural_slider.value + self.flows_slider.value +
#                  self.organizational_slider.value + self.subprocess_slider.value +
#                  self.behavioral_slider.value)

#         normalized = False
#         if abs(total - 100.0) > 1.0:
#             self.structural_slider.value = structural * 100
#             self.flows_slider.value = flows * 100
#             self.organizational_slider.value = organizational * 100
#             self.subprocess_slider.value = subprocess * 100
#             self.behavioral_slider.value = behavioral * 100
#             normalized = True

#         with self.message_output:
#             clear_output(wait=True)
#             if normalized:
#                 print("⚠️ Weights were normalized to sum to 100%")

#         self._update_visualization(structural, flows, organizational, subprocess, behavioral)

#     def _reset_to_defaults(self, button):
#         """Reset sliders to default weights."""
#         self.structural_slider.value = self.default_weights["structural"] * 100
#         self.flows_slider.value = self.default_weights["flows"] * 100
#         self.organizational_slider.value = self.default_weights["organizational"] * 100
#         self.subprocess_slider.value = self.default_weights["subprocess"] * 100
#         self.behavioral_slider.value = self.default_weights.get("behavioral", 0.0) * 100

#         with self.message_output:
#             clear_output(wait=True)
#             print("✓ Reset to default weights")

#         self._update_visualization(
#             self.default_weights["structural"],
#             self.default_weights["flows"],
#             self.default_weights["organizational"],
#             self.default_weights["subprocess"],
#             self.default_weights.get("behavioral", 0.0),
#         )

#     def _update_visualization(self, structural, flows, organizational, subprocess, behavioral):
#         """Update the visualization with current weights."""
#         _, result = self._get_result_for_metric_and_threshold(
#             self.current_metric, self.current_threshold
#         )

#         behavioral_score = result.get("behavioral", 0.0)
#         behavioral_metric = result.get("behavioral_metric_used", "jaccard")

#         # Calculate overall score with current weights
#         overall = (
#             result["high_level_scores"]["structural"] * structural +
#             result["high_level_scores"]["flows"] * flows +
#             result["high_level_scores"]["organizational"] * organizational +
#             result["high_level_scores"]["subprocess"] * subprocess +
#             behavioral_score * behavioral
#         )

#         with self.output:
#             clear_output(wait=True)

#             # Inline minimal diagnostics warning when either net is unsound.
#             # Render as a print so it lives in the same Output widget as the
#             # figure (no separate widgets.HTML required).
#             tr1 = result.get("trace_result_1")
#             tr2 = result.get("trace_result_2")
#             if tr1 is not None and tr2 is not None and not (tr1.is_sound and tr2.is_sound):
#                 print("⚠ Behavioral comparison includes partial results")
#                 print(f"   Model 1: {tr1.diagnostics.status.value} — {tr1.diagnostics.summary}")
#                 print(f"   Model 2: {tr2.diagnostics.status.value} — {tr2.diagnostics.summary}")

#             fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

#             # === LEFT CHART: Weighted Category Scores ===
#             categories = ["Structural", "Flows", "Organizational", "Subprocess", "Behavioral"]
#             raw_scores = [
#                 result["high_level_scores"]["structural"],
#                 result["high_level_scores"]["flows"],
#                 result["high_level_scores"]["organizational"],
#                 result["high_level_scores"]["subprocess"],
#                 behavioral_score,
#             ]

#             # Current weights and weighted scores
#             weights_vals = [structural, flows, organizational, subprocess, behavioral]
#             weighted_scores = [s * w for s, w in zip(raw_scores, weights_vals)]

#             # Equal weights for comparison — split evenly across the categories
#             # that are "live" (subprocess only when there are expanded subprocesses;
#             # behavioral always counts since the dashboard always extracts traces).
#             live_count = 3 + int(self.has_subprocess) + 1  # +1 for behavioral
#             equal_weight = 1.0 / live_count
#             equal_weights_vals = [
#                 equal_weight,
#                 equal_weight,
#                 equal_weight,
#                 equal_weight if self.has_subprocess else 0,
#                 equal_weight,
#             ]
#             equal_weighted_scores = [s * w for s, w in zip(raw_scores, equal_weights_vals)]
#             overall_equal = sum(equal_weighted_scores)

#             colors = [
#                 CATEGORY_COLORS["structural"],
#                 CATEGORY_COLORS["flows"],
#                 CATEGORY_COLORS["organizational"],
#                 CATEGORY_COLORS["subprocess"],
#                 CATEGORY_COLORS["behavioral"],
#             ]
#             y_pos = np.arange(len(categories))
#             bar_height = 0.35

#             # Plot bars - grouped side by side
#             ax1.barh(y_pos + bar_height/2, equal_weighted_scores, color=colors, alpha=0.4, height=bar_height)
#             ax1.barh(y_pos - bar_height/2, weighted_scores, color=colors, alpha=0.9, height=bar_height)

#             # Y-axis labels with raw scores included
#             category_labels = [f"{cat}" for cat, raw in zip(categories, raw_scores)]
#             ax1.set_yticks(y_pos)
#             ax1.set_yticklabels(category_labels)
#             ax1.set_xlabel("Weighted Score (Score × Weight)")
#             ax1.set_xlim(0, max(0.5, max(weighted_scores + equal_weighted_scores) * 1.3))

#             metric_display = self.current_metric.upper()
#             ax1.set_title(
#                 f"Weighted Contributions | Metric: {metric_display} | Threshold: {self.current_threshold:.2f}",
#                 fontsize=11
#             )

#             # Custom legend
#             legend_elements = [
#                 mpatches.Patch(facecolor='gray', alpha=0.4, label=f'Equal Weights ({overall_equal:.1%})'),
#                 mpatches.Patch(facecolor='gray', alpha=0.9, label=f'Current Weights ({overall:.1%})')
#             ]
#             ax1.legend(handles=legend_elements, loc="best", fontsize=9)
#             ax1.grid(axis="x", alpha=0.3)

#             # Add value labels at end of bars
#             for i, (eq_score, cur_score) in enumerate(zip(equal_weighted_scores, weighted_scores)):
#                 if eq_score > 0.005:
#                     ax1.text(eq_score + 0.01, i + bar_height/2, f"{eq_score:.2f}",
#                             va="center", fontsize=8, color="gray")
#                 if cur_score > 0.005:
#                     ax1.text(cur_score + 0.01, i - bar_height/2, f"{cur_score:.2f}",
#                             va="center", fontsize=8, weight="bold")

#             # Overall score watermark
#             ax1.text(
#                 0.5, 0.5, f"{overall:.1%}",
#                 transform=ax1.transAxes, fontsize=48, weight="bold",
#                 ha="center", va="center", alpha=0.15, color="black"
#             )

#             # === RIGHT CHART: Raw Element Scores ===
#             elements = [
#                 "Activities", "Events", "Gateways",
#                 "Seq Flows", "Msg Flows",
#                 "Pool/Lane\nNames", "Pool/Lane\nElements",
#                 "Subprocess\nNames", "Subprocess\nElements", "Subprocess\nFlows",
#                 f"Behavioral\n",
#             ]
#             element_scores = [
#                 result["activity_names"],
#                 result["event_names"],
#                 result["gateway_names"],
#                 result["seq_flows_str"],
#                 result["mes_flows_str"],
#                 result["lane_names"],
#                 result["lane_with_refs"],
#                 result["subprocess_names"],
#                 result["subprocess_elemrefs"],
#                 result["subprocess_flows"],
#                 behavioral_score,
#             ]
#             element_colors = (
#                 [CATEGORY_COLORS["structural"]] * 3 +
#                 [CATEGORY_COLORS["flows"]] * 2 +
#                 [CATEGORY_COLORS["organizational"]] * 2 +
#                 [CATEGORY_COLORS["subprocess"]] * 3 +
#                 [CATEGORY_COLORS["behavioral"]]
#             )

#             y_pos2 = np.arange(len(elements))
#             ax2.barh(y_pos2, element_scores, color=element_colors, alpha=0.8)

#             ax2.set_yticks(y_pos2)
#             ax2.set_yticklabels(elements, fontsize=9)
#             ax2.set_xlabel("Raw Score (0-1)")
#             ax2.set_xlim(0, 1.1)
#             ax2.set_title("Element-Level Breakdown (Unweighted)", fontsize=11)
#             ax2.grid(axis="x", alpha=0.3)

#             for i, score in enumerate(element_scores):
#                 ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=8)

#             # Add category legend for right chart
#             legend_patches = [
#                 mpatches.Patch(color=CATEGORY_COLORS["structural"], label="Structural"),
#                 mpatches.Patch(color=CATEGORY_COLORS["flows"], label="Flows"),
#                 mpatches.Patch(color=CATEGORY_COLORS["organizational"], label="Organizational"),
#                 mpatches.Patch(color=CATEGORY_COLORS["subprocess"], label="Subprocess"),
#                 mpatches.Patch(color=CATEGORY_COLORS["behavioral"], label="Behavioral"),
#             ]
#             ax2.legend(handles=legend_patches, loc="best", fontsize=8)

#             plt.tight_layout()
#             plt.show()

#     def display(self):
#         """Display the dashboard."""
#         # Wire trace-extraction sliders so the cache key always reflects the
#         # current values without forcing a recalculate-on-every-tick.
#         self.trace_timeout_slider.observe(self._on_trace_timeout_change, names="value")
#         self.loop_depth_slider.observe(self._on_loop_depth_change, names="value")

#         # Initial visualization
#         self._update_visualization(
#             self.default_weights["structural"],
#             self.default_weights["flows"],
#             self.default_weights["organizational"],
#             self.default_weights["subprocess"],
#             self.default_weights.get("behavioral", 0.0),
#         )

#         # Layout widgets
#         metric_box = widgets.HBox(list(self.metric_buttons.values()))
#         button_box = widgets.HBox([self.recalculate_button, self.reset_button])

#         dashboard = widgets.VBox([
#             widgets.HTML("<h3>BPMN Similarity Dashboard</h3>"),
#             widgets.HTML("<b>Similarity Metric:</b>"),
#             metric_box,
#             widgets.HTML("<b>Normalization Threshold:</b>"),
#             self.threshold_slider,
#             widgets.HTML("<b>Category Weights (should sum to 100%):</b>"),
#             self.structural_slider,
#             self.flows_slider,
#             self.organizational_slider,
#             self.subprocess_slider,
#             self.behavioral_slider,
#             widgets.HTML("<b>Trace extraction:</b>"),
#             self.trace_timeout_slider,
#             self.loop_depth_slider,
#             button_box,
#             self.message_output,
#             self.output,
#         ])

#         display(dashboard)
#         return self


# def create_similarity_dashboard(
#     model_1,
#     model_2,
#     similarity_func,
#     calculate_similarity_func,
#     normalize_func,
#     initial_threshold=0.7,
#     initial_method="dice",
#     initial_trace_timeout=5.0,
#     initial_max_loop_depth=3,
# ):
#     """
#     Create an interactive BPMN similarity dashboard.

#     Args:
#         model_1: Reference BPMN model (minimal JSON dict)
#         model_2: BPMN model to compare (minimal JSON dict)
#         similarity_func: String similarity function (e.g., bert_cosine_optimized)
#         calculate_similarity_func: BPMN similarity function (calculate_bpmn_similarity).
#             Must accept ``behavioral=``, ``trace_timeout_seconds=``, ``max_loop_depth=``
#             keyword arguments — the dashboard always invokes it with ``behavioral=True``.
#         normalize_func: Normalization function (normalize_atomic_names)
#         initial_threshold: Initial normalization threshold (default: 0.7)
#         initial_method: Initial similarity method (default: "dice")
#         initial_trace_timeout: Initial trace-extraction timeout in seconds (default: 5.0)
#         initial_max_loop_depth: Initial max loop depth for trace extraction (default: 3)

#     Returns:
#         BPMNSimilarityDashboard instance. Call .display() to show.

#     Example:
#         from bpmn_visualization import create_similarity_dashboard
#         from bpmn_normalization import normalize_atomic_names
#         from bpmn_similarity import calculate_bpmn_similarity
#         from string_similarity import bert_cosine_optimized

#         dashboard = create_similarity_dashboard(
#             model_1,
#             model_2,
#             similarity_func=bert_cosine_optimized,
#             calculate_similarity_func=calculate_bpmn_similarity,
#             normalize_func=normalize_atomic_names,
#             initial_threshold=0.7
#         )
#         dashboard.display()
#     """
#     return BPMNSimilarityDashboard(
#         model_1=model_1,
#         model_2=model_2,
#         similarity_func=similarity_func,
#         calculate_similarity_func=calculate_similarity_func,
#         normalize_func=normalize_func,
#         initial_threshold=initial_threshold,
#         initial_method=initial_method,
#         initial_trace_timeout=initial_trace_timeout,
#         initial_max_loop_depth=initial_max_loop_depth,
#     )


# def plot_similarity_summary(result, title="BPMN Similarity Summary"):
#     """
#     Create a static summary plot of similarity results.

#     Args:
#         result: Result dict from calculate_bpmn_similarity
#         title: Plot title

#     Returns:
#         matplotlib Figure
#     """
#     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

#     # High-level scores
#     categories = list(result["high_level_scores"].keys())
#     scores = list(result["high_level_scores"].values())
#     weights = [result["weights_used"][c] for c in categories]

#     colors = [CATEGORY_COLORS.get(c, "#999999") for c in categories]

#     y_pos = np.arange(len(categories))
#     ax1.barh(y_pos, scores, color=colors, alpha=0.8)
#     ax1.set_yticks(y_pos)
#     ax1.set_yticklabels([f"{c.title()} ({w:.0%})" for c, w in zip(categories, weights)])
#     ax1.set_xlabel("Score")
#     ax1.set_xlim(0, 1)
#     ax1.set_title("High-Level Scores")
#     ax1.grid(axis="x", alpha=0.3)

#     for i, score in enumerate(scores):
#         ax1.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

#     # Overall
#     ax1.axvline(x=result["overall"], color="red", linestyle="--", alpha=0.7, label=f"Overall: {result['overall']:.1%}")
#     ax1.legend(loc="best")

#     # Fine-grained scores
#     fine_keys = ["activity_names", "event_names", "gateway_names",
#                  "seq_flows_str", "mes_flows_str", "lane_names", "lane_with_refs"]
#     fine_labels = ["Activities", "Events", "Gateways", "Seq Flows", "Msg Flows",
#                    "Pool/Lane Names", "Pool/Lane Elements"]
#     fine_scores = [result.get(k, 0) for k in fine_keys]
#     fine_colors = (
#         [CATEGORY_COLORS["structural"]] * 3 +
#         [CATEGORY_COLORS["flows"]] * 2 +
#         [CATEGORY_COLORS["organizational"]] * 2
#     )

#     y_pos2 = np.arange(len(fine_labels))
#     ax2.barh(y_pos2, fine_scores, color=fine_colors, alpha=0.7)
#     ax2.set_yticks(y_pos2)
#     ax2.set_yticklabels(fine_labels)
#     ax2.set_xlabel("Score")
#     ax2.set_xlim(0, 1)
#     ax2.set_title("Element-Level Scores")
#     ax2.grid(axis="x", alpha=0.3)

#     for i, score in enumerate(fine_scores):
#         ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

#     fig.suptitle(f"{title} — Overall: {result['overall']:.1%}", fontsize=12, weight="bold")
#     plt.tight_layout()

#     return fig


# def print_similarity_report(result, model_name="Model Comparison"):
#     """
#     Print a text summary of similarity results.

#     Args:
#         result: Result dict from calculate_bpmn_similarity
#         model_name: Name for the comparison
#     """
#     print(f"\n{'='*60}")
#     print(f" {model_name}")
#     print(f"{'='*60}")
#     print(f"\n OVERALL SIMILARITY: {result['overall']:.1%}")
#     print(f"\n High-Level Scores (weighted):")
#     print(f" {'-'*40}")

#     for category, score in result["high_level_scores"].items():
#         weight = result["weights_used"][category]
#         contribution = score * weight
#         print(f"   {category:15s}: {score:5.1%} × {weight:4.0%} = {contribution:5.1%}")

#     print(f"\n Fine-Grained Scores:")
#     print(f" {'-'*40}")

#     fine_items = [
#         ("Activities (names)", "activity_names"),
#         ("Activities (types)", "activity_types"),
#         ("Events (names)", "event_names"),
#         ("Events (types)", "event_types"),
#         ("Gateways (names)", "gateway_names"),
#         ("Gateways (types)", "gateway_types"),
#         ("Sequence Flows", "seq_flows_str"),
#         ("Message Flows", "mes_flows_str"),
#         ("Pool/Lane Names", "lane_names"),
#         ("Pool/Lane Elements", "lane_with_refs"),
#     ]

#     for label, key in fine_items:
#         score = result.get(key, 0)
#         print(f"   {label:20s}: {score:5.1%}")

#     if result.get("has_expanded_subprocess"):
#         print(f"\n Subprocess Scores:")
#         print(f" {'-'*40}")
#         print(f"   {'Names':20s}: {result.get('subprocess_names', 0):5.1%}")
#         print(f"   {'Elements':20s}: {result.get('subprocess_elemrefs', 0):5.1%}")
#         print(f"   {'Flows':20s}: {result.get('subprocess_flows', 0):5.1%}")

#     print(f"\n{'='*60}\n")

# """
# BPMN Similarity Visualization Module

# Independent interactive widgets for exploring BPMN model similarity.

# This module exposes three widget classes that are intentionally decoupled:

# - :class:`StructuralWidget` — owns the structural-similarity controls and
#   rendering (element, flow, organizational, and subprocess categories with
#   user-tunable weights and a metric choice).
# - ``BehavioralWidget``    — added in a separate step; owns trace extraction
#   and behavioral similarity scoring.
# - ``HybridWidget``        — added in a separate step; reads the last computed
#   scores from the other two and combines them with a single weight.

# Usage in a notebook::

#     from rendering.dashboard import StructuralWidget
#     from bpmn_normalization import normalize_atomic_names
#     from bpmn_similarity import calculate_bpmn_similarity
#     from string_similarity import cosine_sim_optimized

#     structural = StructuralWidget(
#         m1, m2,
#         similarity_func=cosine_sim_optimized,
#         calculate_similarity_func=calculate_bpmn_similarity,
#         normalize_func=normalize_atomic_names,
#         initial_threshold=0.7,
#     )
#     structural.display()
# """

# import ipywidgets as widgets
# from IPython.display import display, clear_output
# import matplotlib.pyplot as plt
# import matplotlib.patches as mpatches
# import numpy as np


# # Color scheme for categories.
# # "elements" is the activities + events + gateways bucket (renamed from
# # "structural" to avoid clashing with the top-level structural-similarity
# # concept). "behavioral" stays here because BehavioralWidget will read this
# # same color map.
# CATEGORY_COLORS = {
#     "elements": "#3498db",        # Blue
#     "flows": "#2ecc71",           # Green
#     "organizational": "#f39c12",  # Orange
#     "subprocess": "#9b59b6",      # Purple
#     "behavioral": "#e74c3c",      # Red
# }

# # Gray, used to mark empty-vs-empty rows in the element-level breakdown
# # (where the similarity functions return 1.0 by convention, which would be
# # visually misleading).
# NO_DATA_COLOR = "#bdc3c7"


# class StructuralWidget:
#     """Interactive widget for BPMN structural similarity.

#     Owns its own controls (metric, normalization threshold, four category
#     weight sliders) and its own output area. Exposes ``get_overall_score()``
#     and stores ``_last_result`` so that :class:`HybridWidget` can read the
#     last computed structural score.
#     """

#     def __init__(
#         self,
#         model_1,
#         model_2,
#         similarity_func,
#         calculate_similarity_func,
#         normalize_func,
#         initial_threshold=0.7,
#         initial_method="dice",
#     ):
#         """
#         Args:
#             model_1: Reference BPMN model (minimal JSON dict).
#             model_2: BPMN model to compare (minimal JSON dict).
#             similarity_func: String similarity function used by ``normalize_func``.
#             calculate_similarity_func: Structural similarity function
#                 (``bpmn_similarity.calculate_bpmn_similarity``). Must return a
#                 dict with ``high_level_scores`` keyed by
#                 ``elements / flows / organizational / subprocess`` and a
#                 ``data_presence`` dict for fine-grained keys.
#             normalize_func: Normalization function
#                 (``bpmn_normalization.normalize_atomic_names``).
#             initial_threshold: Initial normalization threshold (default 0.7).
#             initial_method: Initial similarity method (default ``"dice"``).
#         """
#         self.model_1 = model_1
#         self.model_2 = model_2
#         self.similarity_func = similarity_func
#         self.calculate_similarity = calculate_similarity_func
#         self.normalize_func = normalize_func

#         self.current_metric = initial_method
#         self.current_threshold = initial_threshold

#         # Threshold used for the cached initial normalization (so we know when
#         # the user has dragged the slider to a different value and we need to
#         # re-normalize).
#         self._normalized_with_threshold = initial_threshold

#         # Cache for results: (metric, threshold) -> (normalized_model, result).
#         self.results_cache = {}

#         # Initial normalization and calculation
#         self.model_2_normalized, self.initial_mappings = normalize_func(
#             model_1, model_2, similarity_func, threshold=initial_threshold
#         )
#         self.base_result = calculate_similarity_func(
#             model_1,
#             self.model_2_normalized,
#             method=initial_method,
#         )
#         self.results_cache[(initial_method, initial_threshold)] = (
#             self.model_2_normalized,
#             self.base_result,
#         )

#         self.has_subprocess = self.base_result.get("has_expanded_subprocess", False)
#         self.default_weights = self.base_result["weights_used"]

#         # State exposed to HybridWidget. Populated by _update_visualization.
#         self._last_result = None
#         self._last_overall = None

#         self._create_widgets()

#     def _create_widgets(self):
#         """Create all interactive widgets."""
#         self.output = widgets.Output()
#         self.message_output = widgets.Output()

#         # Weight sliders. "elements" is the activities + events + gateways
#         # bucket; "structural" as a top-level name now refers to the whole
#         # widget's output, not this slider.
#         self.elements_slider = widgets.FloatSlider(
#             value=self.default_weights["elements"] * 100,
#             min=0, max=100, step=1,
#             description="Elements (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.flows_slider = widgets.FloatSlider(
#             value=self.default_weights["flows"] * 100,
#             min=0, max=100, step=1,
#             description="Flows (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.organizational_slider = widgets.FloatSlider(
#             value=self.default_weights["organizational"] * 100,
#             min=0, max=100, step=1,
#             description="Org (%):",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.subprocess_slider = widgets.FloatSlider(
#             value=self.default_weights["subprocess"] * 100,
#             min=0, max=100 if self.has_subprocess else 0,
#             step=1,
#             description="Subprocess (%):",
#             continuous_update=False,
#             disabled=not self.has_subprocess,
#             style={'description_width': '100px'}
#         )

#         # Threshold slider
#         self.threshold_slider = widgets.FloatSlider(
#             value=self.current_threshold,
#             min=0.0, max=1.0, step=0.05,
#             description="Threshold:",
#             continuous_update=False,
#             style={'description_width': '100px'}
#         )
#         self.threshold_slider.observe(self._on_threshold_change, names="value")

#         # Metric buttons
#         self.metric_buttons = {
#             "dice": widgets.Button(description="Dice", button_style="primary"),
#             "jaccard": widgets.Button(description="Jaccard", button_style=""),
#             "precision": widgets.Button(description="Precision", button_style=""),
#             "recall": widgets.Button(description="Recall", button_style=""),
#             "f1": widgets.Button(description="F1", button_style=""),
#         }
#         for metric, button in self.metric_buttons.items():
#             button.on_click(lambda b, m=metric: self._set_metric(m))

#         # Control buttons
#         self.recalculate_button = widgets.Button(
#             description="Recalculate",
#             button_style="success",
#             icon="refresh"
#         )
#         self.recalculate_button.on_click(self._recalculate)

#         self.reset_button = widgets.Button(
#             description="Reset to Default",
#             button_style="info",
#             icon="undo"
#         )
#         self.reset_button.on_click(self._reset_to_defaults)

#     def _normalize_weights(self, elements, flows, organizational, subprocess):
#         """Normalize weights to sum to 1.0."""
#         if not self.has_subprocess:
#             subprocess = 0.0
#         total = elements + flows + organizational + subprocess
#         if total == 0:
#             return (
#                 self.default_weights["elements"],
#                 self.default_weights["flows"],
#                 self.default_weights["organizational"],
#                 self.default_weights["subprocess"],
#             )
#         return (
#             elements / total,
#             flows / total,
#             organizational / total,
#             subprocess / total,
#         )

#     def _get_result_for_metric_and_threshold(self, metric, threshold):
#         """Get or calculate result for given metric and threshold."""
#         cache_key = (metric, threshold)

#         if cache_key not in self.results_cache:
#             # If threshold drifted from the initially-normalized one, re-normalize.
#             if abs(threshold - self._normalized_with_threshold) > 0.001:
#                 normalized, _ = self.normalize_func(
#                     self.model_1, self.model_2,
#                     self.similarity_func, threshold=threshold
#                 )
#             else:
#                 normalized = self.model_2_normalized

#             result = self.calculate_similarity(
#                 self.model_1,
#                 normalized,
#                 method=metric,
#             )
#             self.results_cache[cache_key] = (normalized, result)

#         return self.results_cache[cache_key]

#     def _set_metric(self, metric_name):
#         """Change the active metric."""
#         self.current_metric = metric_name

#         for name, button in self.metric_buttons.items():
#             button.button_style = "primary" if name == metric_name else ""

#         self._recalculate(None)

#     def _on_threshold_change(self, change):
#         """Handle threshold slider changes."""
#         self.current_threshold = change["new"]

#     def _recalculate(self, button):
#         """Recalculate and update visualization."""
#         # Get slider values (convert from percentage)
#         elements = self.elements_slider.value / 100.0
#         flows = self.flows_slider.value / 100.0
#         organizational = self.organizational_slider.value / 100.0
#         subprocess = self.subprocess_slider.value / 100.0

#         # Normalize weights
#         elements, flows, organizational, subprocess = self._normalize_weights(
#             elements, flows, organizational, subprocess
#         )

#         # Update sliders to show normalized values if they were off
#         total = (self.elements_slider.value + self.flows_slider.value +
#                  self.organizational_slider.value + self.subprocess_slider.value)

#         normalized = False
#         if abs(total - 100.0) > 1.0:
#             self.elements_slider.value = elements * 100
#             self.flows_slider.value = flows * 100
#             self.organizational_slider.value = organizational * 100
#             self.subprocess_slider.value = subprocess * 100
#             normalized = True

#         with self.message_output:
#             clear_output(wait=True)
#             if normalized:
#                 print("⚠️ Weights were normalized to sum to 100%")

#         self._update_visualization(elements, flows, organizational, subprocess)

#     def _reset_to_defaults(self, button):
#         """Reset sliders to default weights."""
#         self.elements_slider.value = self.default_weights["elements"] * 100
#         self.flows_slider.value = self.default_weights["flows"] * 100
#         self.organizational_slider.value = self.default_weights["organizational"] * 100
#         self.subprocess_slider.value = self.default_weights["subprocess"] * 100

#         with self.message_output:
#             clear_output(wait=True)
#             print("✓ Reset to default weights")

#         self._update_visualization(
#             self.default_weights["elements"],
#             self.default_weights["flows"],
#             self.default_weights["organizational"],
#             self.default_weights["subprocess"],
#         )

#     def _update_visualization(self, elements, flows, organizational, subprocess):
#         """Update the visualization with current weights."""
#         _, result = self._get_result_for_metric_and_threshold(
#             self.current_metric, self.current_threshold
#         )

#         # Calculate overall score with current weights
#         overall = (
#             result["high_level_scores"]["elements"] * elements +
#             result["high_level_scores"]["flows"] * flows +
#             result["high_level_scores"]["organizational"] * organizational +
#             result["high_level_scores"]["subprocess"] * subprocess
#         )

#         # Persist for HybridWidget to read.
#         self._last_result = result
#         self._last_overall = overall

#         data_presence = result.get("data_presence", {})

#         with self.output:
#             clear_output(wait=True)

#             fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

#             # === LEFT CHART: Weighted Category Scores ===
#             categories = ["Elements", "Flows", "Organizational", "Subprocess"]
#             raw_scores = [
#                 result["high_level_scores"]["elements"],
#                 result["high_level_scores"]["flows"],
#                 result["high_level_scores"]["organizational"],
#                 result["high_level_scores"]["subprocess"],
#             ]

#             weights_vals = [elements, flows, organizational, subprocess]
#             weighted_scores = [s * w for s, w in zip(raw_scores, weights_vals)]

#             # Equal weights for comparison — split evenly across the live
#             # categories (subprocess only counts when expanded subprocesses
#             # are present in either model).
#             live_count = 3 + int(self.has_subprocess)
#             equal_weight = 1.0 / live_count
#             equal_weights_vals = [
#                 equal_weight,
#                 equal_weight,
#                 equal_weight,
#                 equal_weight if self.has_subprocess else 0,
#             ]
#             equal_weighted_scores = [s * w for s, w in zip(raw_scores, equal_weights_vals)]
#             overall_equal = sum(equal_weighted_scores)

#             colors_current = "#2c3e50"   # near-black for current-weight bars
#             colors_equal = "#95a5a6"     # medium gray for equal-weight bars
#             y_pos = np.arange(len(categories))
#             bar_height = 0.35

#             # Plot bars - grouped side by side, in gray (equal) and dark
#             # (current). Category color lives in the right chart; the left
#             # chart focuses on equal-vs-current weight contrast.
#             ax1.barh(y_pos + bar_height/2, equal_weighted_scores, color=colors_equal, alpha=0.5, height=bar_height)
#             ax1.barh(y_pos - bar_height/2, weighted_scores, color=colors_current, alpha=0.9, height=bar_height)

#             ax1.set_yticks(y_pos)
#             ax1.set_yticklabels(categories)
#             ax1.set_xlabel("Weighted Score (Score × Weight)")
#             ax1.set_xlim(0, max(0.5, max(weighted_scores + equal_weighted_scores) * 1.3))

#             metric_display = self.current_metric.upper()
#             ax1.set_title(
#                 f"Weighted Contributions | Metric: {metric_display} | Threshold: {self.current_threshold:.2f}",
#                 fontsize=11
#             )

#             # Custom legend — colors match the bars exactly.
#             legend_elements = [
#                 mpatches.Patch(facecolor=colors_equal, alpha=0.5, label=f'Equal Weights ({overall_equal:.1%})'),
#                 mpatches.Patch(facecolor=colors_current, alpha=0.9, label=f'Current Weights ({overall:.1%})')
#             ]
#             ax1.legend(handles=legend_elements, loc="best", fontsize=9)
#             ax1.grid(axis="x", alpha=0.3)

#             # Add value labels at end of bars
#             for i, (eq_score, cur_score) in enumerate(zip(equal_weighted_scores, weighted_scores)):
#                 if eq_score > 0.005:
#                     ax1.text(eq_score + 0.01, i + bar_height/2, f"{eq_score:.2f}",
#                             va="center", fontsize=8, color="gray")
#                 if cur_score > 0.005:
#                     ax1.text(cur_score + 0.01, i - bar_height/2, f"{cur_score:.2f}",
#                             va="center", fontsize=8, weight="bold")

#             # Overall score watermark — solid black, more visible than before.
#             ax1.text(
#                 0.5, 0.5, f"{overall:.1%}",
#                 transform=ax1.transAxes, fontsize=48, weight="bold",
#                 ha="center", va="center", color="#2c3e50"             # ← changed
#             )

#             # === RIGHT CHART: Raw Element Scores ===
#             # Each row tied to a fine-grained key, so we can gray out
#             # empty-vs-empty rows via data_presence.
#             element_rows = [
#                 ("Activities",          "activity_names",      "elements"),
#                 ("Events",              "event_names",         "elements"),
#                 ("Gateways",            "gateway_names",       "elements"),
#                 ("Seq Flows",           "seq_flows_str",       "flows"),
#                 ("Msg Flows",           "mes_flows_str",       "flows"),
#                 ("Pool/Lane\nNames",    "lane_names",          "organizational"),
#                 ("Pool/Lane\nElements", "lane_with_refs",      "organizational"),
#                 ("Subprocess\nNames",   "subprocess_names",    "subprocess"),
#                 ("Subprocess\nElements","subprocess_elemrefs", "subprocess"),
#                 ("Subprocess\nFlows",   "subprocess_flows",    "subprocess"),
#             ]

#             elements_labels = []
#             element_scores = []
#             element_colors = []
#             present_flags = []
#             for label, key, category in element_rows:
#                 present = data_presence.get(key, True)
#                 # If both models are empty for this key, fade the row out and
#                 # display "—" instead of the misleading 1.0.
#                 elements_labels.append(label if present else f"{label}\n(no data)")
#                 element_scores.append(result.get(key, 0) if present else 0)
#                 element_colors.append(CATEGORY_COLORS[category] if present else NO_DATA_COLOR)
#                 present_flags.append(present)

#             y_pos2 = np.arange(len(elements_labels))

#             # Plot real-score bars (gray entries for non-present rows would be
#             # zero-width and invisible, so we handle those separately below).
#             present_scores = [s if p else 0 for s, p in zip(element_scores, present_flags)]
#             present_colors = [c if p else NO_DATA_COLOR for c, p in zip(element_colors, present_flags)]
#             ax2.barh(y_pos2, present_scores, color=present_colors, alpha=0.8)

#             ax2.set_yticks(y_pos2)
#             ax2.set_yticklabels(elements_labels, fontsize=9)
#             ax2.set_xlabel("Raw Score (0-1)")
#             ax2.set_xlim(0, 1.1)
#             ax2.set_title("Element-Level Breakdown (Unweighted)", fontsize=11)
#             ax2.grid(axis="x", alpha=0.3)

#             # For non-present rows, overlay a faint gray band spanning the
#             # whole chart width so the legend's "No data" swatch is honest
#             # and the row reads as "no data" rather than "score of zero".
#             for i, present in enumerate(present_flags):
#                 if not present:
#                     ax2.barh(i, 1.1, color=NO_DATA_COLOR, alpha=0.18, height=0.6)
#                     ax2.text(0.55, i, "no data in either model",
#                              va="center", ha="center", fontsize=8,
#                              color="gray", style="italic")

#             for i, (score, present) in enumerate(zip(element_scores, present_flags)):
#                 if present:
#                     ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=8)

#             # Add category legend for right chart
#             legend_patches = [
#                 mpatches.Patch(color=CATEGORY_COLORS["elements"], label="Elements"),
#                 mpatches.Patch(color=CATEGORY_COLORS["flows"], label="Flows"),
#                 mpatches.Patch(color=CATEGORY_COLORS["organizational"], label="Organizational"),
#                 mpatches.Patch(color=CATEGORY_COLORS["subprocess"], label="Subprocess"),
#                 mpatches.Patch(color=NO_DATA_COLOR, label="No data in either model"),
#             ]
#             ax2.legend(handles=legend_patches, loc="best", fontsize=8)

#             plt.tight_layout()
#             plt.show()

#     def get_overall_score(self):
#         """Return the most recent user-weighted overall structural score.

#         Returns ``None`` before the first ``_update_visualization`` call.
#         Read by :class:`HybridWidget` to combine with the behavioral score.
#         """
#         return self._last_overall

#     def display(self):
#         """Display the widget."""
#         # Initial visualization
#         self._update_visualization(
#             self.default_weights["elements"],
#             self.default_weights["flows"],
#             self.default_weights["organizational"],
#             self.default_weights["subprocess"],
#         )

#         # Layout widgets
#         metric_box = widgets.HBox(list(self.metric_buttons.values()))
#         button_box = widgets.HBox([self.recalculate_button, self.reset_button])

#         layout = widgets.VBox([
#             widgets.HTML("<h3>Structural Similarity</h3>"),
#             widgets.HTML("<b>Similarity Metric:</b>"),
#             metric_box,
#             widgets.HTML("<b>Normalization Threshold:</b>"),
#             self.threshold_slider,
#             widgets.HTML("<b>Category Weights (should sum to 100%):</b>"),
#             self.elements_slider,
#             self.flows_slider,
#             self.organizational_slider,
#             self.subprocess_slider,
#             button_box,
#             self.message_output,
#             self.output,
#         ])

#         display(layout)
#         return self


# def create_similarity_dashboard(
#     model_1,
#     model_2,
#     similarity_func,
#     calculate_similarity_func,
#     normalize_func,
#     initial_threshold=0.7,
#     initial_method="dice",
# ):
#     """
#     Create a structural BPMN similarity widget.

#     Kept as a thin factory for backwards compatibility with existing notebook
#     cells. New code should instantiate :class:`StructuralWidget` directly.

#     Args:
#         model_1: Reference BPMN model (minimal JSON dict)
#         model_2: BPMN model to compare (minimal JSON dict)
#         similarity_func: String similarity function (e.g., cosine_sim_optimized)
#         calculate_similarity_func: BPMN similarity function (calculate_bpmn_similarity)
#         normalize_func: Normalization function (normalize_atomic_names)
#         initial_threshold: Initial normalization threshold (default: 0.7)
#         initial_method: Initial similarity method (default: "dice")

#     Returns:
#         StructuralWidget instance. Call .display() to show.
#     """
#     return StructuralWidget(
#         model_1=model_1,
#         model_2=model_2,
#         similarity_func=similarity_func,
#         calculate_similarity_func=calculate_similarity_func,
#         normalize_func=normalize_func,
#         initial_threshold=initial_threshold,
#         initial_method=initial_method,
#     )


# def plot_similarity_summary(result, title="BPMN Similarity Summary"):
#     """
#     Create a static summary plot of similarity results.

#     Args:
#         result: Result dict from calculate_bpmn_similarity
#         title: Plot title

#     Returns:
#         matplotlib Figure
#     """
#     fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

#     # High-level scores (dynamically picks up renamed keys, e.g. "elements").
#     categories = list(result["high_level_scores"].keys())
#     scores = list(result["high_level_scores"].values())
#     weights = [result["weights_used"][c] for c in categories]

#     colors = [CATEGORY_COLORS.get(c, "#999999") for c in categories]

#     y_pos = np.arange(len(categories))
#     ax1.barh(y_pos, scores, color=colors, alpha=0.8)
#     ax1.set_yticks(y_pos)
#     ax1.set_yticklabels([f"{c.title()} ({w:.0%})" for c, w in zip(categories, weights)])
#     ax1.set_xlabel("Score")
#     ax1.set_xlim(0, 1)
#     ax1.set_title("High-Level Scores")
#     ax1.grid(axis="x", alpha=0.3)

#     for i, score in enumerate(scores):
#         ax1.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

#     ax1.axvline(x=result["overall"], color="red", linestyle="--", alpha=0.7,
#                 label=f"Overall: {result['overall']:.1%}")
#     ax1.legend(loc="best")

#     # Fine-grained scores
#     fine_keys = ["activity_names", "event_names", "gateway_names",
#                  "seq_flows_str", "mes_flows_str", "lane_names", "lane_with_refs"]
#     fine_labels = ["Activities", "Events", "Gateways", "Seq Flows", "Msg Flows",
#                    "Pool/Lane Names", "Pool/Lane Elements"]
#     fine_scores = [result.get(k, 0) for k in fine_keys]
#     fine_colors = (
#         [CATEGORY_COLORS["elements"]] * 3 +
#         [CATEGORY_COLORS["flows"]] * 2 +
#         [CATEGORY_COLORS["organizational"]] * 2
#     )

#     y_pos2 = np.arange(len(fine_labels))
#     ax2.barh(y_pos2, fine_scores, color=fine_colors, alpha=0.7)
#     ax2.set_yticks(y_pos2)
#     ax2.set_yticklabels(fine_labels)
#     ax2.set_xlabel("Score")
#     ax2.set_xlim(0, 1)
#     ax2.set_title("Element-Level Scores")
#     ax2.grid(axis="x", alpha=0.3)

#     for i, score in enumerate(fine_scores):
#         ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

#     fig.suptitle(f"{title} — Overall: {result['overall']:.1%}", fontsize=12, weight="bold")
#     plt.tight_layout()

#     return fig


# def print_similarity_report(result, model_name="Model Comparison"):
#     """
#     Print a text summary of similarity results.

#     Args:
#         result: Result dict from calculate_bpmn_similarity
#         model_name: Name for the comparison
#     """
#     print(f"\n{'='*60}")
#     print(f" {model_name}")
#     print(f"{'='*60}")
#     print(f"\n OVERALL SIMILARITY: {result['overall']:.1%}")
#     print(f"\n High-Level Scores (weighted):")
#     print(f" {'-'*40}")

#     for category, score in result["high_level_scores"].items():
#         weight = result["weights_used"][category]
#         contribution = score * weight
#         print(f"   {category:15s}: {score:5.1%} × {weight:4.0%} = {contribution:5.1%}")

#     print(f"\n Fine-Grained Scores:")
#     print(f" {'-'*40}")

#     fine_items = [
#         ("Activities (names)", "activity_names"),
#         ("Activities (types)", "activity_types"),
#         ("Events (names)", "event_names"),
#         ("Events (types)", "event_types"),
#         ("Gateways (names)", "gateway_names"),
#         ("Gateways (types)", "gateway_types"),
#         ("Sequence Flows", "seq_flows_str"),
#         ("Message Flows", "mes_flows_str"),
#         ("Pool/Lane Names", "lane_names"),
#         ("Pool/Lane Elements", "lane_with_refs"),
#     ]

#     for label, key in fine_items:
#         score = result.get(key, 0)
#         print(f"   {label:20s}: {score:5.1%}")

#     if result.get("has_expanded_subprocess"):
#         print(f"\n Subprocess Scores:")
#         print(f" {'-'*40}")
#         print(f"   {'Names':20s}: {result.get('subprocess_names', 0):5.1%}")
#         print(f"   {'Elements':20s}: {result.get('subprocess_elemrefs', 0):5.1%}")
#         print(f"   {'Flows':20s}: {result.get('subprocess_flows', 0):5.1%}")

#     print(f"\n{'='*60}\n")
"""
BPMN Similarity Visualization Module

Interactive dashboard for exploring BPMN model similarity along structural,
behavioral, and hybrid dimensions.

The :class:`BPMNSimilarityDashboard` is a single widget with three stacked
sections that share a normalization threshold and a similarity metric:

- **Structural** — element / flow / organizational / subprocess categories
  with user-tunable weights.
- **Behavioral** — trace-based comparison. Owns its own trace-timeout and
  max-loop-depth sliders. The user clicks "Compute behavioral" to extract
  traces and score.
- **Hybrid** — single slider weighting the structural and behavioral scores
  into a combined hybrid score.

Threshold and metric changes propagate to every section. When threshold or
trace-extraction parameters change after a behavioral compute, the behavioral
section is marked stale until the user clicks "Compute behavioral" again.

Usage in a notebook::

    from rendering.dashboard import BPMNSimilarityDashboard
    from bpmn_normalization import normalize_atomic_names
    from bpmn_similarity import (
        calculate_bpmn_similarity,
        calculate_trace_similarity,
        calculate_hybrid_similarity,
    )
    from trace_extraction import extract_traces
    from string_similarity import cosine_sim_optimized

    dashboard = BPMNSimilarityDashboard(
        m1, m2,
        similarity_func=cosine_sim_optimized,
        calculate_similarity_func=calculate_bpmn_similarity,
        normalize_func=normalize_atomic_names,
        extract_traces_func=extract_traces,
        calculate_trace_similarity_func=calculate_trace_similarity,
        calculate_hybrid_func=calculate_hybrid_similarity,
        initial_threshold=0.7,
    )
    dashboard.display()
"""

import ipywidgets as widgets
from IPython.display import display, clear_output, HTML
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Color scheme for categories.
# "elements" is the activities + events + gateways bucket (renamed from
# "structural" to avoid clashing with the top-level structural-similarity
# concept). "behavioral" stays here because BehavioralWidget will read this
# same color map.
CATEGORY_COLORS = {
    "elements": "#3498db",        # Blue
    "flows": "#2ecc71",           # Green
    "organizational": "#f39c12",  # Orange
    "subprocess": "#9b59b6",      # Purple
    "behavioral": "#e74c3c",      # Red
}

# Gray, used to mark empty-vs-empty rows in the element-level breakdown
# (where the similarity functions return 1.0 by convention, which would be
# visually misleading).
NO_DATA_COLOR = "#95a5a6"


class BPMNSimilarityDashboard:
    """Interactive dashboard for BPMN similarity exploration.

    Combines structural, behavioral, and hybrid similarity sections into a
    single widget. Threshold and metric are shared across all sections.

    Structural is computed eagerly (on threshold/metric/weight change).
    Behavioral is computed on demand (trace extraction is expensive); when the
    threshold or trace-extraction parameters drift after a compute, the
    behavioral section displays a stale indicator until the user re-clicks
    "Compute behavioral".

    The hybrid score combines the most recent structural overall and the most
    recent behavioral score via a single weight slider.
    """

    def __init__(
        self,
        model_1,
        model_2,
        similarity_func,
        calculate_similarity_func,
        normalize_func,
        initial_threshold=0.7,
        initial_method="dice",
        # Behavioral and hybrid hooks. Optional — when omitted, the dashboard
        # falls back to a structural-only view (the behavioral and hybrid
        # sections are hidden).
        extract_traces_func=None,
        calculate_trace_similarity_func=None,
        calculate_hybrid_func=None,
        initial_trace_timeout=5.0,
        initial_max_loop_depth=3,
        initial_structural_weight=0.5,
    ):
        """
        Args:
            model_1: Reference BPMN model (minimal JSON dict).
            model_2: BPMN model to compare (minimal JSON dict).
            similarity_func: String similarity function used by ``normalize_func``.
            calculate_similarity_func: Structural similarity function
                (``bpmn_similarity.calculate_bpmn_similarity``). Must return a
                dict with ``high_level_scores`` keyed by
                ``elements / flows / organizational / subprocess`` and a
                ``data_presence`` dict for fine-grained keys.
            normalize_func: Normalization function
                (``bpmn_normalization.normalize_atomic_names``).
            initial_threshold: Initial normalization threshold (default 0.7).
            initial_method: Initial similarity method (default ``"dice"``).
            extract_traces_func: ``trace_extraction.extract_traces``. When
                ``None``, the behavioral section is omitted.
            calculate_trace_similarity_func:
                ``bpmn_similarity.calculate_trace_similarity``.
            calculate_hybrid_func:
                ``bpmn_similarity.calculate_hybrid_similarity``.
            initial_trace_timeout: Initial trace-extraction timeout in seconds
                (default 5.0).
            initial_max_loop_depth: Initial max loop depth for trace extraction
                (default 3).
            initial_structural_weight: Initial weight for the structural side
                of the hybrid score, in [0, 1] (default 0.5 — equal weighting).
        """
        self.model_1 = model_1
        self.model_2 = model_2
        self.similarity_func = similarity_func
        self.calculate_similarity = calculate_similarity_func
        self.normalize_func = normalize_func

        # Behavioral / hybrid hooks (all three must be provided together).
        self.extract_traces = extract_traces_func
        self.calculate_trace_similarity = calculate_trace_similarity_func
        self.calculate_hybrid = calculate_hybrid_func
        self._behavioral_enabled = all(
            f is not None
            for f in (extract_traces_func, calculate_trace_similarity_func, calculate_hybrid_func)
        )

        self.current_metric = initial_method
        self.current_threshold = initial_threshold
        self.current_trace_timeout = initial_trace_timeout
        self.current_max_loop_depth = initial_max_loop_depth

        # Threshold used for the cached initial normalization (so we know when
        # the user has dragged the slider to a different value and we need to
        # re-normalize).
        self._normalized_with_threshold = initial_threshold

        # Cache for results: (metric, threshold) -> (normalized_model, result).
        self.results_cache = {}

        # Behavioral state. Populated by _on_compute_behavioral.
        self._last_trace_result_1 = None
        self._last_trace_result_2 = None
        self._last_behavioral_score = None
        self._last_behavioral_metric = None
        # Triple identifying which (threshold, timeout, loop_depth) the last
        # extraction was performed against. Used to detect staleness.
        self._last_extraction_key = None

        # Hybrid weight slider initial value, used by _create_widgets.
        self._initial_structural_weight = initial_structural_weight

        # Initial normalization and calculation
        self.model_2_normalized, self.initial_mappings = normalize_func(
            model_1, model_2, similarity_func, threshold=initial_threshold
        )
        self.base_result = calculate_similarity_func(
            model_1,
            self.model_2_normalized,
            method=initial_method,
        )
        self.results_cache[(initial_method, initial_threshold)] = (
            self.model_2_normalized,
            self.base_result,
        )

        self.has_subprocess = self.base_result.get("has_expanded_subprocess", False)
        self.default_weights = self.base_result["weights_used"]

        # State exposed to HybridWidget. Populated by _update_visualization.
        self._last_result = None
        self._last_overall = None

        self._create_widgets()

    def _create_widgets(self):
        """Create all interactive widgets."""
        self.output = widgets.Output()
        self.message_output = widgets.Output()

        # Weight sliders. "elements" is the activities + events + gateways
        # bucket; "structural" as a top-level name now refers to the whole
        # widget's output, not this slider.
        self.elements_slider = widgets.FloatSlider(
            value=self.default_weights["elements"] * 100,
            min=0, max=100, step=1,
            description="Elements (%):",
            continuous_update=False,
            style={'description_width': '100px'}
        )
        self.flows_slider = widgets.FloatSlider(
            value=self.default_weights["flows"] * 100,
            min=0, max=100, step=1,
            description="Flows (%):",
            continuous_update=False,
            style={'description_width': '100px'}
        )
        self.organizational_slider = widgets.FloatSlider(
            value=self.default_weights["organizational"] * 100,
            min=0, max=100, step=1,
            description="Org (%):",
            continuous_update=False,
            style={'description_width': '100px'}
        )
        self.subprocess_slider = widgets.FloatSlider(
            value=self.default_weights["subprocess"] * 100,
            min=0, max=100 if self.has_subprocess else 0,
            step=1,
            description="Subprocess (%):",
            continuous_update=False,
            disabled=not self.has_subprocess,
            style={'description_width': '100px'}
        )

        # Threshold slider
        self.threshold_slider = widgets.FloatSlider(
            value=self.current_threshold,
            min=0.0, max=1.0, step=0.05,
            description="Threshold:",
            continuous_update=False,
            style={'description_width': '100px'}
        )
        self.threshold_slider.observe(self._on_threshold_change, names="value")

        # Metric buttons
        self.metric_buttons = {
            "dice": widgets.Button(description="Dice", button_style="primary"),
            "jaccard": widgets.Button(description="Jaccard", button_style=""),
            "precision": widgets.Button(description="Precision", button_style=""),
            "recall": widgets.Button(description="Recall", button_style=""),
            "f1": widgets.Button(description="F1", button_style=""),
        }
        for metric, button in self.metric_buttons.items():
            button.on_click(lambda b, m=metric: self._set_metric(m))

        # Control buttons
        self.recalculate_button = widgets.Button(
            description="Recalculate",
            button_style="success",
            icon="refresh"
        )
        self.recalculate_button.on_click(self._recalculate)

        self.reset_button = widgets.Button(
            description="Reset to Default",
            button_style="info",
            icon="undo"
        )
        self.reset_button.on_click(self._reset_to_defaults)

        # === Behavioral and hybrid widgets ===
        # Only created (and shown) when the behavioral hooks were provided.
        if self._behavioral_enabled:
            self.behavioral_output = widgets.Output()

            self.trace_timeout_slider = widgets.FloatSlider(
                value=self.current_trace_timeout,
                min=1.0, max=30.0, step=1.0,
                description="Trace timeout (s):",
                continuous_update=False,
                readout_format=".0f",
                style={'description_width': '140px'}
            )
            self.trace_timeout_slider.observe(self._on_trace_timeout_change, names="value")

            self.loop_depth_slider = widgets.IntSlider(
                value=self.current_max_loop_depth,
                min=1, max=6, step=1,
                description="Max loop depth:",
                continuous_update=False,
                style={'description_width': '140px'}
            )
            self.loop_depth_slider.observe(self._on_loop_depth_change, names="value")

            self.compute_behavioral_button = widgets.Button(
                description="Compute behavioral",
                button_style="success",
                icon="play",
            )
            self.compute_behavioral_button.on_click(self._on_compute_behavioral)

            # Hybrid section.
            self.hybrid_output = widgets.Output()
            self.hybrid_weight_slider = widgets.FloatSlider(
                value=self._initial_structural_weight,
                min=0.0, max=1.0, step=0.05,
                description="Structural weight:",
                continuous_update=False,
                readout_format=".2f",
                style={'description_width': '140px'}
            )
            self.hybrid_weight_slider.observe(self._on_hybrid_weight_change, names="value")

    def _normalize_weights(self, elements, flows, organizational, subprocess):
        """Normalize weights to sum to 1.0."""
        if not self.has_subprocess:
            subprocess = 0.0
        total = elements + flows + organizational + subprocess
        if total == 0:
            return (
                self.default_weights["elements"],
                self.default_weights["flows"],
                self.default_weights["organizational"],
                self.default_weights["subprocess"],
            )
        return (
            elements / total,
            flows / total,
            organizational / total,
            subprocess / total,
        )

    def _get_result_for_metric_and_threshold(self, metric, threshold):
        """Get or calculate result for given metric and threshold."""
        cache_key = (metric, threshold)

        if cache_key not in self.results_cache:
            # If threshold drifted from the initially-normalized one, re-normalize.
            if abs(threshold - self._normalized_with_threshold) > 0.001:
                normalized, _ = self.normalize_func(
                    self.model_1, self.model_2,
                    self.similarity_func, threshold=threshold
                )
            else:
                normalized = self.model_2_normalized

            result = self.calculate_similarity(
                self.model_1,
                normalized,
                method=metric,
            )
            self.results_cache[cache_key] = (normalized, result)

        return self.results_cache[cache_key]

    def _set_metric(self, metric_name):
        """Change the active metric."""
        self.current_metric = metric_name

        for name, button in self.metric_buttons.items():
            button.button_style = "primary" if name == metric_name else ""

        self._recalculate(None)

        # Metric also drives behavioral scoring. If traces are already
        # extracted, re-score them under the new metric (cheap) and refresh
        # the behavioral and hybrid sections.
        if self._behavioral_enabled and self._last_trace_result_1 is not None:
            self._last_behavioral_score = self.calculate_trace_similarity(
                self._last_trace_result_1,
                self._last_trace_result_2,
                method=self.current_metric,
            )
            self._last_behavioral_metric = self.current_metric
            self._render_behavioral()
            self._render_hybrid()

    def _on_threshold_change(self, change):
        """Handle threshold slider changes."""
        self.current_threshold = change["new"]
        # Threshold drift makes any previously-extracted behavioral traces
        # stale (they were extracted against a differently-aligned model).
        # Re-render the behavioral and hybrid sections so the staleness shows.
        if self._behavioral_enabled:
            self._render_behavioral()
            self._render_hybrid()

    def _recalculate(self, button):
        """Recalculate and update visualization."""
        # Get slider values (convert from percentage)
        elements = self.elements_slider.value / 100.0
        flows = self.flows_slider.value / 100.0
        organizational = self.organizational_slider.value / 100.0
        subprocess = self.subprocess_slider.value / 100.0

        # Normalize weights
        elements, flows, organizational, subprocess = self._normalize_weights(
            elements, flows, organizational, subprocess
        )

        # Update sliders to show normalized values if they were off
        total = (self.elements_slider.value + self.flows_slider.value +
                 self.organizational_slider.value + self.subprocess_slider.value)

        normalized = False
        if abs(total - 100.0) > 1.0:
            self.elements_slider.value = elements * 100
            self.flows_slider.value = flows * 100
            self.organizational_slider.value = organizational * 100
            self.subprocess_slider.value = subprocess * 100
            normalized = True

        with self.message_output:
            clear_output(wait=True)
            if normalized:
                print("⚠️ Weights were normalized to sum to 100%")

        self._update_visualization(elements, flows, organizational, subprocess)

    def _reset_to_defaults(self, button):
        """Reset sliders to default weights."""
        self.elements_slider.value = self.default_weights["elements"] * 100
        self.flows_slider.value = self.default_weights["flows"] * 100
        self.organizational_slider.value = self.default_weights["organizational"] * 100
        self.subprocess_slider.value = self.default_weights["subprocess"] * 100

        with self.message_output:
            clear_output(wait=True)
            print("✓ Reset to default weights")

        self._update_visualization(
            self.default_weights["elements"],
            self.default_weights["flows"],
            self.default_weights["organizational"],
            self.default_weights["subprocess"],
        )

    def _update_visualization(self, elements, flows, organizational, subprocess):
        """Update the visualization with current weights."""
        _, result = self._get_result_for_metric_and_threshold(
            self.current_metric, self.current_threshold
        )

        # Calculate overall score with current weights
        overall = (
            result["high_level_scores"]["elements"] * elements +
            result["high_level_scores"]["flows"] * flows +
            result["high_level_scores"]["organizational"] * organizational +
            result["high_level_scores"]["subprocess"] * subprocess
        )

        # Persist for HybridWidget to read.
        self._last_result = result
        self._last_overall = overall

        data_presence = result.get("data_presence", {})

        with self.output:
            clear_output(wait=True)

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

            # === LEFT CHART: Weighted Category Scores ===
            categories = ["Elements", "Flows", "Organizational", "Subprocess"]
            raw_scores = [
                result["high_level_scores"]["elements"],
                result["high_level_scores"]["flows"],
                result["high_level_scores"]["organizational"],
                result["high_level_scores"]["subprocess"],
            ]

            weights_vals = [elements, flows, organizational, subprocess]
            weighted_scores = [s * w for s, w in zip(raw_scores, weights_vals)]

            # Equal weights for comparison — split evenly across the live
            # categories (subprocess only counts when expanded subprocesses
            # are present in either model).
            live_count = 3 + int(self.has_subprocess)
            equal_weight = 1.0 / live_count
            equal_weights_vals = [
                equal_weight,
                equal_weight,
                equal_weight,
                equal_weight if self.has_subprocess else 0,
            ]
            equal_weighted_scores = [s * w for s, w in zip(raw_scores, equal_weights_vals)]
            overall_equal = sum(equal_weighted_scores)

            colors_current = "#2c3e50"   # near-black for current-weight bars
            colors_equal = "#95a5a6"     # medium gray for equal-weight bars
            y_pos = np.arange(len(categories))
            bar_height = 0.35

            # Plot bars - grouped side by side, in gray (equal) and dark
            # (current). Category color lives in the right chart; the left
            # chart focuses on equal-vs-current weight contrast.
            ax1.barh(y_pos + bar_height/2, equal_weighted_scores, color=colors_equal, alpha=0.5, height=bar_height)
            ax1.barh(y_pos - bar_height/2, weighted_scores, color=colors_current, alpha=0.9, height=bar_height)

            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(categories)
            ax1.set_xlabel("Weighted Score (Score × Weight)")
            ax1.set_xlim(0, max(0.5, max(weighted_scores + equal_weighted_scores) * 1.3))

            metric_display = self.current_metric.upper()
            ax1.set_title(
                f"Weighted Contributions | Metric: {metric_display} | Threshold: {self.current_threshold:.2f}",
                fontsize=11
            )

            # Custom legend — colors match the bars exactly.
            legend_elements = [
                mpatches.Patch(facecolor=colors_equal, alpha=0.5, label=f'Equal Weights ({overall_equal:.1%})'),
                mpatches.Patch(facecolor=colors_current, alpha=0.9, label=f'Current Weights ({overall:.1%})')
            ]
            ax1.legend(handles=legend_elements, loc="best", fontsize=9)
            ax1.grid(axis="x", alpha=0.3)

            # Add value labels at end of bars
            for i, (eq_score, cur_score) in enumerate(zip(equal_weighted_scores, weighted_scores)):
                if eq_score > 0.005:
                    ax1.text(eq_score + 0.01, i + bar_height/2, f"{eq_score:.2f}",
                            va="center", fontsize=8, color="gray")
                if cur_score > 0.005:
                    ax1.text(cur_score + 0.01, i - bar_height/2, f"{cur_score:.2f}",
                            va="center", fontsize=8, weight="bold")

            # Overall score watermark — same dark gray as the current-weight
            # bars and the legend swatch. Higher alpha so it visually reads
            # as dark gray rather than a faded ghost.
            ax1.text(
                0.5, 0.5, f"{overall:.1%}",
                transform=ax1.transAxes, fontsize=48, weight="bold",
                ha="center", va="center", alpha=0.7, color="#2c3e50"
            )

            # === RIGHT CHART: Raw Element Scores ===
            # Each row tied to a fine-grained key, so we can gray out
            # empty-vs-empty rows via data_presence.
            element_rows = [
                ("Activities",          "activity_names",      "elements"),
                ("Events",              "event_names",         "elements"),
                ("Gateways",            "gateway_names",       "elements"),
                ("Seq Flows",           "seq_flows_str",       "flows"),
                ("Msg Flows",           "mes_flows_str",       "flows"),
                ("Pool/Lane\nNames",    "lane_names",          "organizational"),
                ("Pool/Lane\nElements", "lane_with_refs",      "organizational"),
                ("Subprocess\nNames",   "subprocess_names",    "subprocess"),
                ("Subprocess\nElements","subprocess_elemrefs", "subprocess"),
                ("Subprocess\nFlows",   "subprocess_flows",    "subprocess"),
            ]

            elements_labels = []
            element_scores = []
            element_colors = []
            present_flags = []
            for label, key, category in element_rows:
                present = data_presence.get(key, True)
                # If both models are empty for this key, fade the row out and
                # display "—" instead of the misleading 1.0.
                elements_labels.append(label if present else f"{label}\n(no data)")
                element_scores.append(result.get(key, 0) if present else 0)
                element_colors.append(CATEGORY_COLORS[category] if present else NO_DATA_COLOR)
                present_flags.append(present)

            y_pos2 = np.arange(len(elements_labels))

            # Plot real-score bars (gray entries for non-present rows would be
            # zero-width and invisible, so we handle those separately below).
            present_scores = [s if p else 0 for s, p in zip(element_scores, present_flags)]
            present_colors = [c if p else NO_DATA_COLOR for c, p in zip(element_colors, present_flags)]
            ax2.barh(y_pos2, present_scores, color=present_colors, alpha=0.8)

            ax2.set_yticks(y_pos2)
            ax2.set_yticklabels(elements_labels, fontsize=9)
            ax2.set_xlabel("Raw Score (0-1)")
            ax2.set_xlim(0, 1.1)
            ax2.set_title("Element-Level Breakdown (Unweighted)", fontsize=11)
            ax2.grid(axis="x", alpha=0.3)

            # For non-present rows, overlay a faint gray band spanning the
            # whole chart width so the legend's "No data" swatch is honest
            # and the row reads as "no data" rather than "score of zero".
            for i, present in enumerate(present_flags):
                if not present:
                    ax2.barh(i, 1.1, color=NO_DATA_COLOR, alpha=0.5, height=0.6)
                    ax2.text(0.55, i, "no data in either model",
                             va="center", ha="center", fontsize=8,
                             color="gray", style="italic")

            for i, (score, present) in enumerate(zip(element_scores, present_flags)):
                if present:
                    ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=8)

            # Add category legend for right chart
            legend_patches = [
                mpatches.Patch(color=CATEGORY_COLORS["elements"], label="Elements"),
                mpatches.Patch(color=CATEGORY_COLORS["flows"], label="Flows"),
                mpatches.Patch(color=CATEGORY_COLORS["organizational"], label="Organizational"),
                mpatches.Patch(color=CATEGORY_COLORS["subprocess"], label="Subprocess"),
                mpatches.Patch(color=NO_DATA_COLOR, label="No data in either model"),
            ]
            ax2.legend(handles=legend_patches, loc="best", fontsize=8)

            plt.tight_layout()
            plt.show()

        # Structural overall changed; refresh the hybrid section so it picks
        # up the new value. (Behavioral was already refreshed by _set_metric
        # if the change came from a metric click; threshold changes alone
        # don't re-run structural so we don't double-render here.)
        if self._behavioral_enabled:
            self._render_hybrid()

    # ----- Behavioral section -----

    def _on_trace_timeout_change(self, change):
        self.current_trace_timeout = change["new"]
        # Param drift → previously-extracted traces no longer match these
        # parameters. Reflect staleness in the behavioral output.
        self._render_behavioral()
        self._render_hybrid()

    def _on_loop_depth_change(self, change):
        self.current_max_loop_depth = change["new"]
        self._render_behavioral()
        self._render_hybrid()

    def _behavioral_is_stale(self):
        """Whether the last-extracted traces match the current parameters.

        Returns ``False`` if traces were never extracted (treated as
        "fresh-not-yet-computed" rather than "stale").
        """
        if self._last_extraction_key is None:
            return False
        return self._last_extraction_key != (
            self.current_threshold,
            self.current_trace_timeout,
            self.current_max_loop_depth,
        )

    def _on_compute_behavioral(self, _button):
        """Extract traces with the current parameters and compute the score."""
        # Pull the aligned model_2 from the structural cache at the current
        # (metric, threshold). This guarantees behavioral uses the same
        # alignment as structural.
        normalized, _ = self._get_result_for_metric_and_threshold(
            self.current_metric, self.current_threshold
        )

        self._last_trace_result_1 = self.extract_traces(
            self.model_1,
            timeout_seconds=self.current_trace_timeout,
            max_loop_depth=self.current_max_loop_depth,
        )
        self._last_trace_result_2 = self.extract_traces(
            normalized,
            timeout_seconds=self.current_trace_timeout,
            max_loop_depth=self.current_max_loop_depth,
        )
        self._last_behavioral_score = self.calculate_trace_similarity(
            self._last_trace_result_1,
            self._last_trace_result_2,
            method=self.current_metric,
        )
        self._last_behavioral_metric = self.current_metric
        self._last_extraction_key = (
            self.current_threshold,
            self.current_trace_timeout,
            self.current_max_loop_depth,
        )

        self._render_behavioral()
        self._render_hybrid()

    def _render_behavioral(self):
        """Render the behavioral output area."""
        if not self._behavioral_enabled:
            return
        with self.behavioral_output:
            clear_output(wait=True)
            if self._last_behavioral_score is None:
                print("Click 'Compute behavioral' to extract traces and score them.")
                return

            tr1, tr2 = self._last_trace_result_1, self._last_trace_result_2
            traces_1 = tr1.all_traces()
            traces_2 = tr2.all_traces()

            # Staleness banner (if any extraction parameter has drifted).
            if self._behavioral_is_stale():
                key = self._last_extraction_key
                print("⚠ STALE — re-click 'Compute behavioral' to refresh.")
                print(f"   Last computed at threshold={key[0]:.2f}, "
                      f"timeout={key[1]:.0f}s, max_loop={key[2]}")
                print(f"   Current settings: threshold={self.current_threshold:.2f}, "
                      f"timeout={self.current_trace_timeout:.0f}s, "
                      f"max_loop={self.current_max_loop_depth}")
                print()

            # Soundness diagnostics.
            if not (tr1.is_sound and tr2.is_sound):
                print("⚠ Behavioral comparison includes partial results")
                print(f"   Model 1: {tr1.diagnostics.status.value} — {tr1.diagnostics.summary}")
                print(f"   Model 2: {tr2.diagnostics.status.value} — {tr2.diagnostics.summary}")
                print()

            # Counts and score.
            set_1 = {tuple(t) for t in traces_1}
            set_2 = {tuple(t) for t in traces_2}
            print(f"Model 1: {len(traces_1)} trace variant(s)")
            print(f"Model 2: {len(traces_2)} trace variant(s)")
            print(f"Traces matched exactly: {len(set_1 & set_2)} / {len(set_1 | set_2)}")

            # Prominent score render — large dark-gray number with the metric
            # in smaller gray text alongside, matching the structural
            # watermark style.
            display(HTML(
                f"<div style='font-size:28px; font-weight:bold; "
                f"color:#2c3e50; margin-top:10px;'>"
                f"Behavioral: {self._last_behavioral_score:.1%} "
                f"<span style='font-size:14px; color:#7f8c8d; "
                f"font-weight:normal;'>"
                f"({self._last_behavioral_metric})</span>"
                f"</div>"
            ))

    # ----- Hybrid section -----

    def _on_hybrid_weight_change(self, _change):
        self._render_hybrid()

    def _render_hybrid(self):
        if not self._behavioral_enabled:
            return
        with self.hybrid_output:
            clear_output(wait=True)
            structural_overall = self._last_overall
            beh_score = self._last_behavioral_score
            if structural_overall is None or beh_score is None:
                print("Compute structural (above) and behavioral, then the "
                      "hybrid score will appear here.")
                return
            # Use the user-weighted overall (self._last_overall), NOT
            # self._last_result["overall"] which holds the default-weighted
            # value computed by calculate_bpmn_similarity and doesn't reflect
            # the structural weight sliders.
            hybrid = self.calculate_hybrid(
                {"overall": self._last_overall},
                beh_score,
                structural_weight=self.hybrid_weight_slider.value,
            )
            stale_note = (
                " <span style='color:#e67e22;'>⚠ behavioral is STALE</span>"
                if self._behavioral_is_stale() else ""
            )
            display(HTML(
                f"<div style='font-family:sans-serif; line-height:1.5;'>"
                f"<div style='color:#555; font-size:13px;'>"
                f"Structural: <b>{hybrid['structural']:.1%}</b> × "
                f"{hybrid['structural_weight']:.0%}"
                f"</div>"
                f"<div style='color:#555; font-size:13px;'>"
                f"Behavioral: <b>{hybrid['behavioral']:.1%}</b> × "
                f"{hybrid['behavioral_weight']:.0%}{stale_note}"
                f"</div>"
                f"<div style='font-size:36px; font-weight:bold; "
                f"color:#2c3e50; margin-top:8px;'>"
                f"Hybrid: {hybrid['hybrid']:.1%} "
                f"<span style='font-size:14px; color:#7f8c8d; "
                f"font-weight:normal;'>"
                f"(metric: {self.current_metric})</span>"
                f"</div>"
                f"</div>"
            ))

    def get_overall_score(self):
        """Return the most recent user-weighted overall structural score.

        Returns ``None`` before the first ``_update_visualization`` call.
        Read by :class:`HybridWidget` to combine with the behavioral score.
        """
        return self._last_overall

    def display(self):
        """Display the widget."""
        # Initial visualization
        self._update_visualization(
            self.default_weights["elements"],
            self.default_weights["flows"],
            self.default_weights["organizational"],
            self.default_weights["subprocess"],
        )

        # Layout widgets
        metric_box = widgets.HBox(list(self.metric_buttons.values()))
        button_box = widgets.HBox([self.recalculate_button, self.reset_button])

        sections = [
            widgets.HTML("<b>Similarity Metric:</b>"),
            metric_box,
            widgets.HTML("<b>Normalization Threshold:</b>"),
            self.threshold_slider,
            widgets.HTML("<hr><h3>Structural Similarity</h3>"),
            widgets.HTML("<b>Category Weights (should sum to 100%):</b>"),
            self.elements_slider,
            self.flows_slider,
            self.organizational_slider,
            self.subprocess_slider,
            button_box,
            self.message_output,
            self.output,
        ]

        if self._behavioral_enabled:
            # Render the initial (empty) behavioral and hybrid output areas so
            # the placeholders show until the user clicks the buttons.
            self._render_behavioral()
            self._render_hybrid()
            sections.extend([
                widgets.HTML("<hr><h3>Behavioral Similarity</h3>"),
                widgets.HTML("<b>Trace extraction parameters:</b>"),
                self.trace_timeout_slider,
                self.loop_depth_slider,
                self.compute_behavioral_button,
                self.behavioral_output,
                widgets.HTML("<hr><h3>Hybrid Similarity</h3>"),
                self.hybrid_weight_slider,
                self.hybrid_output,
            ])

        layout = widgets.VBox(sections)

        display(layout)
        return self


def create_similarity_dashboard(
    model_1,
    model_2,
    similarity_func,
    calculate_similarity_func,
    normalize_func,
    initial_threshold=0.7,
    initial_method="dice",
    extract_traces_func=None,
    calculate_trace_similarity_func=None,
    calculate_hybrid_func=None,
    initial_trace_timeout=5.0,
    initial_max_loop_depth=3,
    initial_structural_weight=0.5,
):
    """
    Create a BPMN similarity dashboard.

    Kept as a thin factory for backwards compatibility with existing notebook
    cells. New code should instantiate :class:`BPMNSimilarityDashboard` directly.

    Args:
        model_1: Reference BPMN model (minimal JSON dict)
        model_2: BPMN model to compare (minimal JSON dict)
        similarity_func: String similarity function (e.g., cosine_sim_optimized)
        calculate_similarity_func: BPMN similarity function (calculate_bpmn_similarity)
        normalize_func: Normalization function (normalize_atomic_names)
        initial_threshold: Initial normalization threshold (default: 0.7)
        initial_method: Initial similarity method (default: "dice")
        extract_traces_func, calculate_trace_similarity_func,
        calculate_hybrid_func: Optional behavioral / hybrid hooks. When all
            three are provided, the dashboard also renders the behavioral and
            hybrid sections.
        initial_trace_timeout, initial_max_loop_depth: Initial trace-extraction
            parameters (defaults 5.0s, 3).
        initial_structural_weight: Initial hybrid structural-side weight
            (default 0.5).

    Returns:
        BPMNSimilarityDashboard instance. Call .display() to show.
    """
    return BPMNSimilarityDashboard(
        model_1=model_1,
        model_2=model_2,
        similarity_func=similarity_func,
        calculate_similarity_func=calculate_similarity_func,
        normalize_func=normalize_func,
        initial_threshold=initial_threshold,
        initial_method=initial_method,
        extract_traces_func=extract_traces_func,
        calculate_trace_similarity_func=calculate_trace_similarity_func,
        calculate_hybrid_func=calculate_hybrid_func,
        initial_trace_timeout=initial_trace_timeout,
        initial_max_loop_depth=initial_max_loop_depth,
        initial_structural_weight=initial_structural_weight,
    )


def plot_similarity_summary(result, title="BPMN Similarity Summary"):
    """
    Create a static summary plot of similarity results.

    Args:
        result: Result dict from calculate_bpmn_similarity
        title: Plot title

    Returns:
        matplotlib Figure
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # High-level scores (dynamically picks up renamed keys, e.g. "elements").
    categories = list(result["high_level_scores"].keys())
    scores = list(result["high_level_scores"].values())
    weights = [result["weights_used"][c] for c in categories]

    colors = [CATEGORY_COLORS.get(c, "#999999") for c in categories]

    y_pos = np.arange(len(categories))
    ax1.barh(y_pos, scores, color=colors, alpha=0.8)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([f"{c.title()} ({w:.0%})" for c, w in zip(categories, weights)])
    ax1.set_xlabel("Score")
    ax1.set_xlim(0, 1)
    ax1.set_title("High-Level Scores")
    ax1.grid(axis="x", alpha=0.3)

    for i, score in enumerate(scores):
        ax1.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

    ax1.axvline(x=result["overall"], color="red", linestyle="--", alpha=0.7,
                label=f"Overall: {result['overall']:.1%}")
    ax1.legend(loc="best")

    # Fine-grained scores
    fine_keys = ["activity_names", "event_names", "gateway_names",
                 "seq_flows_str", "mes_flows_str", "lane_names", "lane_with_refs"]
    fine_labels = ["Activities", "Events", "Gateways", "Seq Flows", "Msg Flows",
                   "Pool/Lane Names", "Pool/Lane Elements"]
    fine_scores = [result.get(k, 0) for k in fine_keys]
    fine_colors = (
        [CATEGORY_COLORS["elements"]] * 3 +
        [CATEGORY_COLORS["flows"]] * 2 +
        [CATEGORY_COLORS["organizational"]] * 2
    )

    y_pos2 = np.arange(len(fine_labels))
    ax2.barh(y_pos2, fine_scores, color=fine_colors, alpha=0.7)
    ax2.set_yticks(y_pos2)
    ax2.set_yticklabels(fine_labels)
    ax2.set_xlabel("Score")
    ax2.set_xlim(0, 1)
    ax2.set_title("Element-Level Scores")
    ax2.grid(axis="x", alpha=0.3)

    for i, score in enumerate(fine_scores):
        ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=9)

    fig.suptitle(f"{title} — Overall: {result['overall']:.1%}", fontsize=12, weight="bold")
    plt.tight_layout()

    return fig


def print_similarity_report(result, model_name="Model Comparison"):
    """
    Print a text summary of similarity results.

    Args:
        result: Result dict from calculate_bpmn_similarity
        model_name: Name for the comparison
    """
    print(f"\n{'='*60}")
    print(f" {model_name}")
    print(f"{'='*60}")
    print(f"\n OVERALL SIMILARITY: {result['overall']:.1%}")
    print(f"\n High-Level Scores (weighted):")
    print(f" {'-'*40}")

    for category, score in result["high_level_scores"].items():
        weight = result["weights_used"][category]
        contribution = score * weight
        print(f"   {category:15s}: {score:5.1%} × {weight:4.0%} = {contribution:5.1%}")

    print(f"\n Fine-Grained Scores:")
    print(f" {'-'*40}")

    fine_items = [
        ("Activities (names)", "activity_names"),
        ("Activities (types)", "activity_types"),
        ("Events (names)", "event_names"),
        ("Events (types)", "event_types"),
        ("Gateways (names)", "gateway_names"),
        ("Gateways (types)", "gateway_types"),
        ("Sequence Flows", "seq_flows_str"),
        ("Message Flows", "mes_flows_str"),
        ("Pool/Lane Names", "lane_names"),
        ("Pool/Lane Elements", "lane_with_refs"),
    ]

    for label, key in fine_items:
        score = result.get(key, 0)
        print(f"   {label:20s}: {score:5.1%}")

    if result.get("has_expanded_subprocess"):
        print(f"\n Subprocess Scores:")
        print(f" {'-'*40}")
        print(f"   {'Names':20s}: {result.get('subprocess_names', 0):5.1%}")
        print(f"   {'Elements':20s}: {result.get('subprocess_elemrefs', 0):5.1%}")
        print(f"   {'Flows':20s}: {result.get('subprocess_flows', 0):5.1%}")

    print(f"\n{'='*60}\n")