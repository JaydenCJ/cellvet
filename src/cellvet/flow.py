"""Name-flow simulation (rule families N2xx, H3xx, P0xx, W4xx).

cellvet replays the notebook twice, without executing anything:

1. **Document order** — the run a fresh reader (or ``jupyter nbconvert
   --execute``, or CI) will get. Every name a cell reads must already be
   bound by an earlier cell, a builtin, or the kernel's notebook globals.
2. **Kernel order** — the run the author actually had, reconstructed by
   sorting executed cells by their ``In [n]`` counts.

Comparing the two replays is what finds the bugs formatters cannot see:
a name that only resolves in kernel order is the classic "works on my
kernel" NameError-in-waiting; a name that resolves to *different* defining
cells in the two orders means the saved outputs came from state a fresh
run will not recreate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .magics import rewrite_cell
from .names import CellNames, NameEvent, extract_names, is_builtin
from .notebook import Cell, Notebook
from .rules import Finding


@dataclass
class CellFacts:
    """One cell plus everything extracted from its source."""

    cell: Cell
    names: CellNames
    implied_defines: List[str] = field(default_factory=list)
    opaque: bool = False

    def events(self) -> List[Tuple[int, int, str, NameEvent]]:
        """The cell's name events interleaved in source-line order.

        Each item is ``(line, tiebreak, kind, event)`` with kind in
        ``{"use", "delete", "define"}``. On the same line, uses come first
        (``x = x + 1`` reads the old ``x``), then deletes, then defines.
        """
        events: List[Tuple[int, int, str, NameEvent]] = []
        for name in self.implied_defines:
            events.append((0, 2, "define", NameEvent(name, 0)))
        for ev in self.names.immediate_uses:
            events.append((ev.line, 0, "use", ev))
        for ev in self.names.deletes:
            events.append((ev.line, 1, "delete", ev))
        for ev in self.names.defines:
            events.append((ev.line, 2, "define", ev))
        events.sort(key=lambda item: (item[0], item[1]))
        return events


def extract_cell_facts(cell: Cell) -> CellFacts:
    rewritten = rewrite_cell(cell.source)
    if rewritten.opaque:
        return CellFacts(cell=cell, names=CellNames(), implied_defines=[], opaque=True)
    names = extract_names(rewritten.source)
    return CellFacts(cell=cell, names=names, implied_defines=rewritten.implied_defines)


class _Replay:
    """Tracks the environment while cells are applied in some order."""

    def __init__(self) -> None:
        self.env: Dict[str, Cell] = {}  # name -> cell that last bound it
        self.deleted_by: Dict[str, Cell] = {}
        self.star_cells: List[Cell] = []

    def star_active(self, facts: CellFacts, line: int) -> bool:
        """Has a star import happened before this point?"""
        if self.star_cells:
            return True
        star = facts.names.star_import_line
        return star is not None and star <= line

    def resolve(self, name: str) -> Optional[Cell]:
        return self.env.get(name)

    def define(self, facts: CellFacts, name: str) -> None:
        self.env[name] = facts.cell
        self.deleted_by.pop(name, None)

    def delete(self, facts: CellFacts, name: str) -> None:
        if name in self.env:
            self.deleted_by[name] = facts.cell
        self.env.pop(name, None)

    def finish_cell(self, facts: CellFacts) -> None:
        if facts.names.star_import_line is not None:
            self.star_cells.append(facts.cell)


def analyze_flow(nb: Notebook) -> List[Finding]:
    all_facts = [extract_cell_facts(cell) for cell in nb.cells]
    findings: List[Finding] = []

    # P001 / W401: analysis-confidence notes.
    for facts in all_facts:
        if facts.names.syntax_error:
            findings.append(
                Finding(
                    rule="P001",
                    path=nb.path,
                    cell=facts.cell.index,
                    execution_count=facts.cell.execution_count,
                    message=(
                        f"{facts.cell.label()} is not valid Python: "
                        f"{facts.names.syntax_error}; name analysis skipped this cell"
                    ),
                )
            )
        if facts.names.star_import_line is not None:
            findings.append(
                Finding(
                    rule="W401",
                    path=nb.path,
                    cell=facts.cell.index,
                    execution_count=facts.cell.execution_count,
                    line=facts.names.star_import_line,
                    message=(
                        f"{facts.cell.label()} uses `from ... import *`; cellvet cannot "
                        "see what it binds, so undefined-name checks are suppressed from here on"
                    ),
                )
            )

    kernel_providers = _kernel_replay(all_facts)
    findings.extend(_document_replay(nb, all_facts, kernel_providers))
    return findings


def _kernel_replay(all_facts: List[CellFacts]) -> Dict[Tuple[int, str], Cell]:
    """Replay executed cells in In[n] order; map (cell, name) -> provider."""
    executed = [f for f in all_facts if f.cell.is_executed]
    executed.sort(key=lambda f: (f.cell.execution_count, f.cell.index))
    replay = _Replay()
    providers: Dict[Tuple[int, str], Cell] = {}
    for facts in executed:
        for _line, _tie, kind, ev in facts.events():
            if kind == "use":
                provider = replay.resolve(ev.name)
                if provider is not None:
                    providers.setdefault((facts.cell.index, ev.name), provider)
            elif kind == "define":
                replay.define(facts, ev.name)
            else:
                replay.delete(facts, ev.name)
        replay.finish_cell(facts)
    return providers


def _document_replay(
    nb: Notebook,
    all_facts: List[CellFacts],
    kernel_providers: Dict[Tuple[int, str], Cell],
) -> List[Finding]:
    findings: List[Finding] = []
    replay = _Replay()

    # Where each name is ever defined, for defined-after-use messages.
    first_definer: Dict[str, Cell] = {}
    for facts in all_facts:
        for ev in facts.names.defines:
            first_definer.setdefault(ev.name, facts.cell)
        for name in facts.implied_defines:
            first_definer.setdefault(name, facts.cell)

    reported: Set[Tuple[int, str, str]] = set()  # (cell, rule, name)

    def report(rule: str, facts: CellFacts, use: NameEvent, message: str) -> None:
        key = (facts.cell.index, rule, use.name)
        if key in reported:
            return
        reported.add(key)
        findings.append(
            Finding(
                rule=rule,
                path=nb.path,
                cell=facts.cell.index,
                execution_count=facts.cell.execution_count,
                line=use.line,
                message=message,
            )
        )

    for facts in all_facts:
        for _line, _tie, kind, use in facts.events():
            if kind == "define":
                replay.define(facts, use.name)
                continue
            if kind == "delete":
                replay.delete(facts, use.name)
                continue
            provider = replay.resolve(use.name)
            if provider is not None:
                kernel = kernel_providers.get((facts.cell.index, use.name))
                if kernel is not None and kernel.index != provider.index:
                    report(
                        "H301",
                        facts,
                        use,
                        f"'{use.name}' comes from {provider.label()} on a fresh run, "
                        f"but this cell actually ran against the value from {kernel.label()}; "
                        "its saved output may not reproduce",
                    )
                continue
            if is_builtin(use.name):
                continue
            if replay.star_active(facts, use.line):
                continue
            if use.name in replay.deleted_by:
                deleter = replay.deleted_by[use.name]
                report(
                    "N203",
                    facts,
                    use,
                    f"'{use.name}' is used after {deleter.label()} deleted it; "
                    "a fresh top-to-bottom run raises NameError",
                )
            elif use.name in first_definer:
                definer = first_definer[use.name]
                if definer.index == facts.cell.index:
                    message = (
                        f"'{use.name}' is used before it is assigned later in this same cell"
                    )
                else:
                    message = (
                        f"'{use.name}' is used here but only defined in {definer.label()}, "
                        "which comes later in the notebook"
                    )
                kernel = kernel_providers.get((facts.cell.index, use.name))
                if kernel is not None:
                    message += (
                        f"; it worked in your session only because {kernel.label()} had already run"
                    )
                report("N202", facts, use, message)
            else:
                report(
                    "N201",
                    facts,
                    use,
                    f"'{use.name}' is never defined anywhere in the notebook; "
                    "a fresh run raises NameError",
                )
        replay.finish_cell(facts)

    # Deferred uses (inside functions/lambdas) only need to exist by call
    # time, so they are checked against everything the notebook ever binds.
    star_anywhere = any(f.names.star_import_line is not None for f in all_facts)
    if not star_anywhere:
        for facts in all_facts:
            for use in facts.names.deferred_uses:
                if use.name in first_definer or is_builtin(use.name):
                    continue
                key = (facts.cell.index, "N201", use.name)
                if key in reported:
                    continue
                reported.add(key)
                findings.append(
                    Finding(
                        rule="N201",
                        path=nb.path,
                        cell=facts.cell.index,
                        execution_count=facts.cell.execution_count,
                        line=use.line,
                        message=(
                            f"'{use.name}' (used inside a function) is never defined "
                            "anywhere in the notebook; calling that function raises NameError"
                        ),
                    )
                )
    return findings
