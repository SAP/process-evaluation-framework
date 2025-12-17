"""BPMN rendering and visualization module."""

from .bpmn_viewer import render_bpmn_xml_embed
from .dashboard import (
    CATEGORY_COLORS,
    BPMNSimilarityDashboard,
    create_similarity_dashboard,
    plot_similarity_summary,
    print_similarity_report,
)

__all__ = [
    "render_bpmn_xml_embed",
    "BPMNSimilarityDashboard",
    "create_similarity_dashboard",
    "plot_similarity_summary",
    "print_similarity_report",
    "CATEGORY_COLORS",
]
