"""Build design documentation and the reference for the installed Python API."""

project = "EquiReduce"
author = "EquiReduce contributors"
release = "0.1.0.dev0"
language = "en"
extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]
autodoc_typehints = "none"
source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_build", "requirements.txt"]
nitpicky = True
myst_enable_extensions = ["dollarmath", "colon_fence"]
html_theme = "alabaster"
html_title = "EquiReduce — design documentation"
html_theme_options = {"description": "SymPy → exact reduction → Lean"}
