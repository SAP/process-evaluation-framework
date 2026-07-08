"""BPMN XML viewer using bpmn-js.

Two entry points share a single HTML template:

* :func:`build_bpmn_iframe_html` — pure builder, returns the ``<iframe …>``
  string. Use this from marimo cells (which capture returned HTML) or anywhere
  you need the raw markup without a display side effect.
* :func:`render_bpmn_xml_embed` — thin IPython wrapper around the builder that
  calls ``display(HTML(...))``, for classic Jupyter notebooks.
"""

import base64


def build_bpmn_iframe_html(
    xml_str: str,
    height_px: int = 320,
    navigated: bool = True,
    background: str = "#ffffff",
) -> str:
    """Build a self-contained bpmn-js iframe for the given BPMN XML.

    Args:
        xml_str: BPMN 2.0 XML content as a string.
        height_px: iframe height in pixels.
        navigated: when True, use the navigated viewer with built-in zoom/pan.
        background: background color for the viewer.

    Returns:
        An ``<iframe src="data:text/html;base64,…">`` HTML string that renders
        the diagram via bpmn-js loaded from unpkg.
    """
    viewer_script = (
        "https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-navigated-viewer.production.min.js"
        if navigated
        else "https://unpkg.com/bpmn-js@17.11.1/dist/bpmn-viewer.production.min.js"
    )

    safe_xml = xml_str.replace("`", "'")

    html_doc = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="{viewer_script}"></script>
    <style>
        html, body {{ margin: 0; padding: 0; overflow: hidden; height: 100%; background: {background}; }}
        #canvas {{ width: 100%; height: 100%; }}
        #error {{ color: red; padding: 20px; display: none; }}
    </style>
</head>
<body>
    <div id="error"></div>
    <div id="canvas"></div>
    <script>
        var xml = `{safe_xml}`;
        window.addEventListener('load', function() {{
            var viewer = new BpmnJS({{ container: document.getElementById('canvas') }});
            viewer.importXML(xml).then(function() {{
                var canvas = viewer.get('canvas');
                canvas.zoom('fit-viewport', 'auto');
            }}).catch(function(err) {{
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = 'Error: ' + err.message;
            }});
        }});
    </script>
</body>
</html>
"""

    html_b64 = base64.b64encode(html_doc.encode("utf-8")).decode("utf-8")
    return (
        f'<iframe src="data:text/html;base64,{html_b64}" '
        f'width="100%" height="{height_px}px" frameborder="0" '
        f'style="border-radius:8px;"></iframe>'
    )


def render_bpmn_xml_embed(
    xml_str: str,
    height_px: int = 300,
    navigated: bool = True,
    background: str = "#ffffff",
):
    """Embed a raw BPMN XML string in an HTML iframe using bpmn-js.

    Notebook-friendly wrapper: builds the iframe HTML and hands it to
    ``IPython.display`` for inline rendering.
    """
    from IPython.display import HTML, display

    display(
        HTML(
            build_bpmn_iframe_html(
                xml_str,
                height_px=height_px,
                navigated=navigated,
                background=background,
            )
        )
    )
