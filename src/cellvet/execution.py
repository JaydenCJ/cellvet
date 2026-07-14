"""Execution-order checks (rule family E1xx).

These checks read only cell metadata — execution counts and positions —
so they work even on notebooks whose code cellvet cannot parse. They are
the cheapest, highest-signal indicator of a notebook that was edited and
run interactively but never re-run top to bottom.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from .notebook import Notebook
from .rules import Finding


def check_execution_order(nb: Notebook) -> List[Finding]:
    findings: List[Finding] = []
    findings.extend(_out_of_order(nb))
    findings.extend(_never_executed(nb))
    findings.extend(_duplicates(nb))
    findings.extend(_gaps(nb))
    return findings


def _out_of_order(nb: Notebook) -> List[Finding]:
    """E101: an executed cell whose count is lower than an earlier cell's."""
    findings: List[Finding] = []
    high = None  # highest execution count seen so far, and its cell
    for cell in nb.executed_cells:
        if high is not None and cell.execution_count < high.execution_count:
            findings.append(
                Finding(
                    rule="E101",
                    path=nb.path,
                    cell=cell.index,
                    execution_count=cell.execution_count,
                    message=(
                        f"{cell.label()} ran before {high.label()} but appears after it; "
                        "the document order was never executed as shown"
                    ),
                )
            )
        if high is None or cell.execution_count > high.execution_count:
            high = cell
    return findings


def _never_executed(nb: Notebook) -> List[Finding]:
    """E102: a non-blank code cell with no count, in an otherwise-run notebook.

    A notebook where *nothing* ran is simply unexecuted (freshly stripped,
    or exported) — that is not a bug, so E102 stays quiet then.
    """
    if not nb.executed_cells:
        return []
    findings: List[Finding] = []
    for cell in nb.cells:
        if not cell.is_executed and not cell.is_blank:
            findings.append(
                Finding(
                    rule="E102",
                    path=nb.path,
                    cell=cell.index,
                    message=(
                        f"{cell.label()} was never executed although other cells were; "
                        "its behavior on a fresh run is untested"
                    ),
                )
            )
    return findings


def _duplicates(nb: Notebook) -> List[Finding]:
    """E104: the same execution count on two cells (merged/copied sessions)."""
    counts = Counter(c.execution_count for c in nb.executed_cells)
    findings: List[Finding] = []
    for cell in nb.executed_cells:
        if counts[cell.execution_count] > 1:
            others = [
                c.index
                for c in nb.executed_cells
                if c.execution_count == cell.execution_count and c is not cell
            ]
            noun = "cell" if len(others) == 1 else "cells"
            findings.append(
                Finding(
                    rule="E104",
                    path=nb.path,
                    cell=cell.index,
                    execution_count=cell.execution_count,
                    message=(
                        f"{cell.label()} shares In [{cell.execution_count}] with "
                        f"{noun} {', '.join(str(i) for i in others)}; counts from one "
                        "kernel session are unique, so these cells came from different sessions"
                    ),
                )
            )
    return findings


def _gaps(nb: Notebook) -> List[Finding]:
    """E103: missing counts 1..max — cells were re-run or deleted after running.

    Reported once per notebook: a gap means the kernel executed code that is
    no longer visible, so state the remaining cells relied on may be gone.
    """
    counts = sorted({c.execution_count for c in nb.executed_cells})
    if not counts:
        return []
    missing = sorted(set(range(1, counts[-1] + 1)) - set(counts))
    if not missing:
        return []
    shown = ", ".join(str(n) for n in missing[:6])
    if len(missing) > 6:
        shown += f", ... ({len(missing)} total)"
    return [
        Finding(
            rule="E103",
            path=nb.path,
            message=(
                f"execution counts jump over In [{shown}]; cells were re-run or "
                "deleted after running, so the session held state this file no longer shows"
            ),
        )
    ]
