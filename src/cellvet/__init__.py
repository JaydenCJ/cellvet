"""cellvet — static hidden-state analysis for Jupyter notebooks.

cellvet parses ``.ipynb`` files (no kernel, no execution, no network) and
reports the class of bugs that formatters and output-strippers ignore:
cells that were executed out of document order, names that a fresh
top-to-bottom run would not find, and cells whose recorded output depended
on stale kernel state.

Public API::

    from cellvet import analyze_path, load_notebook, RULES

    findings = analyze_path("analysis.ipynb")
    for f in findings:
        print(f.rule, f.message)
"""

from .analyzer import Config, analyze_notebook, analyze_path
from .notebook import Cell, Notebook, NotebookError, load_notebook
from .rules import RULES, Finding, Rule, Severity

__version__ = "0.1.0"

__all__ = [
    "Cell",
    "Config",
    "Finding",
    "Notebook",
    "NotebookError",
    "RULES",
    "Rule",
    "Severity",
    "analyze_notebook",
    "analyze_path",
    "load_notebook",
    "__version__",
]
