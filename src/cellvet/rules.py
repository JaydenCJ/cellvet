"""Rule registry and the Finding record.

Rule IDs are stable and grouped by family:

- ``E1xx`` — execution-order metadata checks (no source analysis needed);
- ``N2xx`` — name-flow errors: a fresh top-to-bottom run raises ``NameError``;
- ``H3xx`` — hidden-state hazards: the notebook runs, but its recorded
  results depended on kernel history rather than document order;
- ``P0xx`` / ``W4xx`` — analysis-confidence notes (unparsable cells,
  star imports).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional


class Severity:
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    severity: str
    summary: str


_RULES = [
    Rule(
        "E101",
        "out-of-order-execution",
        Severity.WARNING,
        "Execution counts decrease down the notebook: cells were run in a different order than they are shown.",
    ),
    Rule(
        "E102",
        "never-executed-cell",
        Severity.WARNING,
        "A non-empty code cell was never executed while others were: the saved outputs do not cover it.",
    ),
    Rule(
        "E103",
        "execution-count-gap",
        Severity.INFO,
        "Execution counts have gaps: cells were re-run or deleted after running, so hidden state may linger.",
    ),
    Rule(
        "E104",
        "duplicate-execution-count",
        Severity.WARNING,
        "Two cells share an execution count: the notebook mixes cells from different sessions or copies.",
    ),
    Rule(
        "N201",
        "undefined-name",
        Severity.ERROR,
        "A name is used but never defined anywhere in the notebook: a fresh run raises NameError.",
    ),
    Rule(
        "N202",
        "defined-after-use",
        Severity.ERROR,
        "A name is used before the cell that defines it: the notebook only works when run out of order.",
    ),
    Rule(
        "N203",
        "use-after-delete",
        Severity.ERROR,
        "A name is used after `del` removed it: a fresh top-to-bottom run raises NameError.",
    ),
    Rule(
        "H301",
        "order-dependent-binding",
        Severity.WARNING,
        "A name resolved to a different cell's definition when this cell actually ran: outputs may not reproduce.",
    ),
    Rule(
        "P001",
        "unparsable-cell",
        Severity.WARNING,
        "A cell is not valid Python (even after magic rewriting): name analysis skipped it.",
    ),
    Rule(
        "W401",
        "star-import",
        Severity.INFO,
        "`from module import *` hides which names it binds: undefined-name checks are suppressed after it.",
    ),
]

RULES: Dict[str, Rule] = {rule.id: rule for rule in _RULES}


@dataclass
class Finding:
    """One diagnostic, addressed to a cell (and line) of a notebook."""

    rule: str
    path: str
    message: str
    cell: Optional[int] = None
    execution_count: Optional[int] = None
    line: Optional[int] = None

    @property
    def severity(self) -> str:
        return RULES[self.rule].severity

    def sort_key(self):
        return (self.path, self.cell if self.cell is not None else 0, self.line or 0, self.rule)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity
        data["name"] = RULES[self.rule].name
        return data
