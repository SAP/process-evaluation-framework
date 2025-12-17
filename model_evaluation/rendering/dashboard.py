"""
BPMN Similarity Visualization Module

Interactive widgets for exploring BPMN model similarity results.

Usage:
    from bpmn_visualization import create_similarity_dashboard

    # In Jupyter notebook:
    dashboard = create_similarity_dashboard(
        model_1,
        model_2,
        similarity_func=bert_cosine_optimized,
        calculate_similarity_func=calculate_bpmn_similarity,
        normalize_func=normalize_atomic_names,
        initial_threshold=0.7
    )
    dashboard.display()
"""

import ipywidgets as widgets
from IPython.display import display, clear_output
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Color scheme for categories
CATEGORY_COLORS = {
    "structural": "#3498db",  # Blue
    "flows": "#2ecc71",       # Green
    "organizational": "#f39c12",  # Orange
    "subprocess": "#9b59b6",  # Purple
}


class BPMNSimilarityDashboard:
    """Interactive dashboard for BPMN similarity exploration."""

    def __init__(
        self,
        model_1,
        model_2,
        similarity_func,
        calculate_similarity_func,
        normalize_func,
        initial_threshold=0.7,
        initial_method="dice"
    ):
        """
        Initialize the dashboard.

        Args:
            model_1: Reference BPMN model (ground truth)
            model_2: BPMN model to compare
            similarity_func: String similarity function for normalization
            calculate_similarity_func: Function to calculate BPMN similarity
            normalize_func: Function to normalize atomic names
            initial_threshold: Initial normalization threshold (default: 0.7)
            initial_method: Initial similarity method (default: "dice")
        """
        self.model_1 = model_1
        self.model_2 = model_2
        self.similarity_func = similarity_func
        self.calculate_similarity = calculate_similarity_func
        self.normalize_func = normalize_func

        self.current_metric = initial_method
        self.current_threshold = initial_threshold

        # Store the threshold used for initial normalization (for comparison later)
        # This is the FIX: we compare against this, not self.current_threshold
        self._normalized_with_threshold = initial_threshold

        # Cache for results: (metric, threshold) -> (normalized_model, result)
        self.results_cache = {}

        # Initial normalization and calculation
        self.model_2_normalized, self.initial_mappings = normalize_func(
            model_1, model_2, similarity_func, threshold=initial_threshold
        )

        # Initial calculation
        self.base_result = calculate_similarity_func(
            model_1, self.model_2_normalized, method=initial_method
        )
        self.results_cache[(initial_method, initial_threshold)] = (
            self.model_2_normalized, self.base_result
        )

        self.has_subprocess = self.base_result.get("has_expanded_subprocess", False)
        self.default_weights = self.base_result["weights_used"]

        # Create widgets
        self._create_widgets()

    def _create_widgets(self):
        """Create all interactive widgets."""
        self.output = widgets.Output()
        self.message_output = widgets.Output()

        # Weight sliders
        self.structural_slider = widgets.FloatSlider(
            value=self.default_weights["structural"] * 100,
            min=0, max=100, step=1,
            description="Structural (%):",
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

    def _normalize_weights(self, structural, flows, organizational, subprocess):
        """Normalize weights to sum to 1.0."""
        if not self.has_subprocess:
            subprocess = 0.0
        total = structural + flows + organizational + subprocess
        if total == 0:
            return (
                self.default_weights["structural"],
                self.default_weights["flows"],
                self.default_weights["organizational"],
                self.default_weights["subprocess"]
            )
        return (
            structural / total,
            flows / total,
            organizational / total,
            subprocess / total
        )

    def _get_result_for_metric_and_threshold(self, metric, threshold):
        """Get or calculate result for given metric and threshold."""
        cache_key = (metric, threshold)

        if cache_key not in self.results_cache:
            # FIX: Compare against _normalized_with_threshold (initial), not current_threshold
            if abs(threshold - self._normalized_with_threshold) > 0.001:
                # Different threshold, need to renormalize
                normalized, _ = self.normalize_func(
                    self.model_1, self.model_2,
                    self.similarity_func, threshold=threshold
                )
            else:
                # Same as initial threshold, use cached normalized model
                normalized = self.model_2_normalized

            result = self.calculate_similarity(self.model_1, normalized, method=metric)
            self.results_cache[cache_key] = (normalized, result)

        return self.results_cache[cache_key]

    def _set_metric(self, metric_name):
        """Change the active metric."""
        self.current_metric = metric_name

        for name, button in self.metric_buttons.items():
            button.button_style = "primary" if name == metric_name else ""

        self._recalculate(None)

    def _on_threshold_change(self, change):
        """Handle threshold slider changes."""
        self.current_threshold = change["new"]

    def _recalculate(self, button):
        """Recalculate and update visualization."""
        # Get slider values (convert from percentage)
        structural = self.structural_slider.value / 100.0
        flows = self.flows_slider.value / 100.0
        organizational = self.organizational_slider.value / 100.0
        subprocess = self.subprocess_slider.value / 100.0

        # Normalize weights
        structural, flows, organizational, subprocess = self._normalize_weights(
            structural, flows, organizational, subprocess
        )

        # Update sliders to show normalized values
        total = (self.structural_slider.value + self.flows_slider.value +
                 self.organizational_slider.value + self.subprocess_slider.value)

        normalized = False
        if abs(total - 100.0) > 1.0:
            self.structural_slider.value = structural * 100
            self.flows_slider.value = flows * 100
            self.organizational_slider.value = organizational * 100
            self.subprocess_slider.value = subprocess * 100
            normalized = True

        with self.message_output:
            clear_output(wait=True)
            if normalized:
                print("⚠️ Weights were normalized to sum to 100%")

        self._update_visualization(structural, flows, organizational, subprocess)

    def _reset_to_defaults(self, button):
        """Reset sliders to default weights."""
        self.structural_slider.value = self.default_weights["structural"] * 100
        self.flows_slider.value = self.default_weights["flows"] * 100
        self.organizational_slider.value = self.default_weights["organizational"] * 100
        self.subprocess_slider.value = self.default_weights["subprocess"] * 100

        with self.message_output:
            clear_output(wait=True)
            print("✓ Reset to default weights")

        self._update_visualization(
            self.default_weights["structural"],
            self.default_weights["flows"],
            self.default_weights["organizational"],
            self.default_weights["subprocess"]
        )

    def _update_visualization(self, structural, flows, organizational, subprocess):
        """Update the visualization with current weights."""
        _, result = self._get_result_for_metric_and_threshold(
            self.current_metric, self.current_threshold
        )

        # Calculate overall score with current weights
        overall = (
            result["high_level_scores"]["structural"] * structural +
            result["high_level_scores"]["flows"] * flows +
            result["high_level_scores"]["organizational"] * organizational +
            result["high_level_scores"]["subprocess"] * subprocess
        )

        with self.output:
            clear_output(wait=True)

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

            # === LEFT CHART: Weighted Category Scores ===
            categories = ["Structural", "Flows", "Organizational", "Subprocess"]
            raw_scores = [
                result["high_level_scores"]["structural"],
                result["high_level_scores"]["flows"],
                result["high_level_scores"]["organizational"],
                result["high_level_scores"]["subprocess"],
            ]

            # Current weights and weighted scores
            weights_vals = [structural, flows, organizational, subprocess]
            weighted_scores = [s * w for s, w in zip(raw_scores, weights_vals)]

            # Equal weights for comparison
            if self.has_subprocess:
                equal_weight = 0.25
            else:
                equal_weight = 1.0 / 3.0
            equal_weights_vals = [equal_weight, equal_weight, equal_weight,
                                  equal_weight if self.has_subprocess else 0]
            equal_weighted_scores = [s * w for s, w in zip(raw_scores, equal_weights_vals)]
            overall_equal = sum(equal_weighted_scores)

            colors = [
                CATEGORY_COLORS["structural"],
                CATEGORY_COLORS["flows"],
                CATEGORY_COLORS["organizational"],
                CATEGORY_COLORS["subprocess"]
            ]
            y_pos = np.arange(len(categories))
            bar_height = 0.35

            # Plot bars - grouped side by side
            ax1.barh(y_pos + bar_height/2, equal_weighted_scores, color=colors, alpha=0.4, height=bar_height)
            ax1.barh(y_pos - bar_height/2, weighted_scores, color=colors, alpha=0.9, height=bar_height)

            # Y-axis labels with raw scores included
            category_labels = [f"{cat}" for cat, raw in zip(categories, raw_scores)]
            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(category_labels)
            ax1.set_xlabel("Weighted Score (Score × Weight)")
            ax1.set_xlim(0, max(0.5, max(weighted_scores + equal_weighted_scores) * 1.3))

            metric_display = self.current_metric.upper()
            ax1.set_title(
                f"Weighted Contributions | Metric: {metric_display} | Threshold: {self.current_threshold:.2f}",
                fontsize=11
            )

            # Custom legend
            legend_elements = [
                mpatches.Patch(facecolor='gray', alpha=0.4, label=f'Equal Weights ({overall_equal:.1%})'),
                mpatches.Patch(facecolor='gray', alpha=0.9, label=f'Current Weights ({overall:.1%})')
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

            # Overall score watermark
            ax1.text(
                0.5, 0.5, f"{overall:.1%}",
                transform=ax1.transAxes, fontsize=48, weight="bold",
                ha="center", va="center", alpha=0.15, color="black"
            )

            # === RIGHT CHART: Raw Element Scores ===
            elements = [
                "Activities", "Events", "Gateways",
                "Seq Flows", "Msg Flows",
                "Pool/Lane\nNames", "Pool/Lane\nElements",
                "Subprocess\nNames", "Subprocess\nElements", "Subprocess\nFlows"
            ]
            element_scores = [
                result["activity_names"],
                result["event_names"],
                result["gateway_names"],
                result["seq_flows_str"],
                result["mes_flows_str"],
                result["lane_names"],
                result["lane_with_refs"],
                result["subprocess_names"],
                result["subprocess_elemrefs"],
                result["subprocess_flows"],
            ]
            element_colors = (
                [CATEGORY_COLORS["structural"]] * 3 +
                [CATEGORY_COLORS["flows"]] * 2 +
                [CATEGORY_COLORS["organizational"]] * 2 +
                [CATEGORY_COLORS["subprocess"]] * 3
            )

            y_pos2 = np.arange(len(elements))
            ax2.barh(y_pos2, element_scores, color=element_colors, alpha=0.8)

            ax2.set_yticks(y_pos2)
            ax2.set_yticklabels(elements, fontsize=9)
            ax2.set_xlabel("Raw Score (0-1)")
            ax2.set_xlim(0, 1.1)
            ax2.set_title("Element-Level Breakdown (Unweighted)", fontsize=11)
            ax2.grid(axis="x", alpha=0.3)

            for i, score in enumerate(element_scores):
                ax2.text(score + 0.02, i, f"{score:.2f}", va="center", fontsize=8)

            # Add category legend for right chart
            legend_patches = [
                mpatches.Patch(color=CATEGORY_COLORS["structural"], label="Structural"),
                mpatches.Patch(color=CATEGORY_COLORS["flows"], label="Flows"),
                mpatches.Patch(color=CATEGORY_COLORS["organizational"], label="Organizational"),
                mpatches.Patch(color=CATEGORY_COLORS["subprocess"], label="Subprocess"),
            ]
            ax2.legend(handles=legend_patches, loc="best", fontsize=8)

            plt.tight_layout()
            plt.show()

    def display(self):
        """Display the dashboard."""
        # Initial visualization
        self._update_visualization(
            self.default_weights["structural"],
            self.default_weights["flows"],
            self.default_weights["organizational"],
            self.default_weights["subprocess"]
        )

        # Layout widgets
        metric_box = widgets.HBox(list(self.metric_buttons.values()))
        button_box = widgets.HBox([self.recalculate_button, self.reset_button])

        dashboard = widgets.VBox([
            widgets.HTML("<h3>BPMN Similarity Dashboard</h3>"),
            widgets.HTML("<b>Similarity Metric:</b>"),
            metric_box,
            widgets.HTML("<b>Normalization Threshold:</b>"),
            self.threshold_slider,
            widgets.HTML("<b>Category Weights (should sum to 100%):</b>"),
            self.structural_slider,
            self.flows_slider,
            self.organizational_slider,
            self.subprocess_slider,
            button_box,
            self.message_output,
            self.output,
        ])

        display(dashboard)
        return self


def create_similarity_dashboard(
    model_1,
    model_2,
    similarity_func,
    calculate_similarity_func,
    normalize_func,
    initial_threshold=0.7,
    initial_method="dice"
):
    """
    Create an interactive BPMN similarity dashboard.

    Args:
        model_1: Reference BPMN model (minimal JSON dict)
        model_2: BPMN model to compare (minimal JSON dict)
        similarity_func: String similarity function (e.g., bert_cosine_optimized)
        calculate_similarity_func: BPMN similarity function (calculate_bpmn_similarity)
        normalize_func: Normalization function (normalize_atomic_names)
        initial_threshold: Initial normalization threshold (default: 0.7)
        initial_method: Initial similarity method (default: "dice")

    Returns:
        BPMNSimilarityDashboard instance. Call .display() to show.

    Example:
        from bpmn_visualization import create_similarity_dashboard
        from bpmn_normalization import normalize_atomic_names
        from bpmn_similarity import calculate_bpmn_similarity
        from string_similarity import bert_cosine_optimized

        dashboard = create_similarity_dashboard(
            model_1,
            model_2,
            similarity_func=bert_cosine_optimized,
            calculate_similarity_func=calculate_bpmn_similarity,
            normalize_func=normalize_atomic_names,
            initial_threshold=0.7
        )
        dashboard.display()
    """
    return BPMNSimilarityDashboard(
        model_1=model_1,
        model_2=model_2,
        similarity_func=similarity_func,
        calculate_similarity_func=calculate_similarity_func,
        normalize_func=normalize_func,
        initial_threshold=initial_threshold,
        initial_method=initial_method
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

    # High-level scores
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

    # Overall
    ax1.axvline(x=result["overall"], color="red", linestyle="--", alpha=0.7, label=f"Overall: {result['overall']:.1%}")
    ax1.legend(loc="best")

    # Fine-grained scores
    fine_keys = ["activity_names", "event_names", "gateway_names",
                 "seq_flows_str", "mes_flows_str", "lane_names", "lane_with_refs"]
    fine_labels = ["Activities", "Events", "Gateways", "Seq Flows", "Msg Flows",
                   "Pool/Lane Names", "Pool/Lane Elements"]
    fine_scores = [result.get(k, 0) for k in fine_keys]
    fine_colors = (
        [CATEGORY_COLORS["structural"]] * 3 +
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