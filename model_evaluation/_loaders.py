"""Convenience file loaders for the two supported BPMN input formats.

These wrap the existing :class:`BPMNConverter` / :class:`XMLBPMNConverter`
classes so library users can go from a file on disk to the internal minimal
BPMN dict — the input format used by every evaluation function — in one call.
"""

import json
from pathlib import Path
from typing import Union

from .BPMN_conversion import BPMNConverter, XMLBPMNConverter


def load_bpmn_xml(path: Union[str, Path]) -> dict:
    """Load a BPMN 2.0 XML file and return the minimal BPMN dict."""
    return XMLBPMNConverter.convert_file(str(path)).to_dict()


def load_signavio_json(path: Union[str, Path]) -> dict:
    """Load a Signavio JSON export file and return the minimal BPMN dict."""
    with Path(path).open("r", encoding="utf-8") as f:
        return BPMNConverter.convert(json.load(f)).to_dict()


def load_bpmn(path: Union[str, Path]) -> dict:
    """Dispatch to the right loader by file suffix.

    ``.xml`` / ``.bpmn`` → :func:`load_bpmn_xml`; everything else is treated
    as Signavio-style JSON. Suffix matching is case-insensitive to match the
    dashboard's own loader.
    """
    p = Path(path)
    if p.suffix.lower() in (".xml", ".bpmn"):
        return load_bpmn_xml(p)
    return load_signavio_json(p)
