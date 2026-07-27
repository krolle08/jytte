import os
from datetime import date

project = "Jytte"
author = "Nichlas Madsen"
copyright = f"{date.today().year}, {author}"
release = "0.4.0"

extensions = [
    "sphinxcontrib.plantuml",
    "sphinx_needs",
    "sphinx_design",
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

_docs_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plantuml = f"java -Djava.awt.headless=true -jar {os.path.join(_docs_dir, '.plantuml', 'plantuml.jar')}"
plantuml_output_format = "png"

needs_types = [
    dict(directive="req",  title="Requirement",          prefix="REQ-",  color="#BFD8D2", style="node"),
    dict(directive="spec", title="Design Specification", prefix="SPEC-", color="#FEDCD2", style="node"),
]

needs_links = {
    "fulfills": {
        "incoming": "fulfilled by",
        "outgoing": "fulfills",
    },
}

needs_id_required = True
needs_id_regex = r"^(REQ|SPEC)-\d+$"

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
}
html_static_path = ["_static"]
html_css_files = ["custom.css"]

linkcheck_ignore = [
    r"http://localhost.*",
    r"http://127\.0\.0\.1.*",
    r"http://0\.0\.0\.0.*",
]
linkcheck_timeout = 10
linkcheck_retries = 2

templates_path = ["_templates"]
exclude_patterns = []
