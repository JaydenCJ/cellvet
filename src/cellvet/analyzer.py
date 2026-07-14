"""Orchestration: run every check on a notebook and filter by config."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from .execution import check_execution_order
from .flow import analyze_flow
from .notebook import Notebook, load_notebook
from .rules import RULES, Finding


@dataclass
class Config:
    """What to report.

    ``select`` and ``ignore`` accept full rule IDs (``N201``) or family
    prefixes (``E``, ``N2``). ``ignore`` wins over ``select``.
    """

    select: Optional[Set[str]] = None
    ignore: Set[str] = field(default_factory=set)

    def wants(self, rule_id: str) -> bool:
        if any(rule_id.startswith(prefix) for prefix in self.ignore):
            return False
        if self.select is None:
            return True
        return any(rule_id.startswith(prefix) for prefix in self.select)

    def validate(self) -> None:
        """Reject selectors that match no known rule (catches typos)."""
        for prefix in (self.select or set()) | self.ignore:
            if not any(rule_id.startswith(prefix) for rule_id in RULES):
                raise ValueError(f"unknown rule or prefix: {prefix!r}")


def analyze_notebook(nb: Notebook, config: Optional[Config] = None) -> List[Finding]:
    """Run every check on an already-parsed notebook."""
    config = config or Config()
    findings: List[Finding] = []
    findings.extend(check_execution_order(nb))
    findings.extend(analyze_flow(nb))
    findings = [f for f in findings if config.wants(f.rule)]
    findings.sort(key=Finding.sort_key)
    return findings


def analyze_path(path: str, config: Optional[Config] = None) -> List[Finding]:
    """Load one ``.ipynb`` file and analyze it.

    Raises :class:`cellvet.NotebookError` when the file is unreadable or
    not a v4 notebook.
    """
    return analyze_notebook(load_notebook(path), config)
