"""BPMN XML viewer using bpmn-js in Jupyter notebooks."""

import base64
from IPython.display import HTML, display


def render_bpmn_xml_embed(
    xml_str: str,
    height_px: int = 300,
    navigated: bool = True,
    background: str = "#ffffff",
):
    """Embed a raw BPMN XML string in an HTML iframe using bpmn-js.

    Args:
        xml_str: BPMN 2.0 XML content as a string
        height_px: iframe height in pixels
        navigated: when True, use the navigated viewer with built-in zoom/pan
        background: background color for the viewer

    This is the notebook-friendly version of the HTML embedding.
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

                // Constrain scrolling to diagram bounds
                var viewbox = canvas.viewbox();
                var outer = viewbox.outer;
                canvas.scroll({{ dx: 0, dy: 0 }});  // Reset scroll position

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
    iframe_html = f'<iframe src="data:text/html;base64,{html_b64}" width="100%" height="{height_px}px" frameborder="0"></iframe>'
    display(HTML(iframe_html))
