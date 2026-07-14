"""Loading and modelling ``.ipynb`` files.

Only the parts of the nbformat 4 schema that cellvet needs are modelled:
code cells, their source, and their execution counts. Markdown and raw
cells are counted for document position but otherwise ignored. Parsing is
pure stdlib ``json`` — cellvet has no runtime dependency on nbformat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional


class NotebookError(Exception):
    """Raised when a file cannot be understood as a v4 Jupyter notebook."""


@dataclass
class Cell:
    """One code cell of a notebook.

    ``index`` is the 1-based position among *code* cells (what cellvet
    prints as ``cell N``); ``doc_index`` is the 0-based position among all
    cells including markdown and raw.
    """

    index: int
    doc_index: int
    source: str
    execution_count: Optional[int] = None

    @property
    def is_executed(self) -> bool:
        return self.execution_count is not None

    @property
    def is_blank(self) -> bool:
        """True when the cell contains no statements worth analyzing."""
        return all(
            not line.strip() or line.lstrip().startswith("#")
            for line in self.source.splitlines()
        )

    def label(self) -> str:
        """Human label, e.g. ``cell 3 (In [7])`` or ``cell 3 (never run)``."""
        if self.execution_count is None:
            return f"cell {self.index} (never run)"
        return f"cell {self.index} (In [{self.execution_count}])"


@dataclass
class Notebook:
    """A parsed notebook reduced to its code cells."""

    path: str
    cells: List[Cell] = field(default_factory=list)
    total_cells: int = 0

    @property
    def executed_cells(self) -> List[Cell]:
        return [c for c in self.cells if c.is_executed]


def _join_source(raw: object) -> str:
    """The schema allows source as a string or a list of lines."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and all(isinstance(part, str) for part in raw):
        return "".join(raw)
    raise NotebookError("cell 'source' must be a string or a list of strings")


def _parse_execution_count(raw: object) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise NotebookError("cell 'execution_count' must be an integer or null")
    return raw


def parse_notebook(text: str, path: str = "<string>") -> Notebook:
    """Parse notebook JSON text into a :class:`Notebook`.

    Raises :class:`NotebookError` on malformed JSON, a non-v4 format, or
    structurally invalid cells — cellvet refuses to guess about files it
    cannot trust, because a silently skipped cell would hide real bugs.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NotebookError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise NotebookError("top level of a notebook must be a JSON object")

    fmt = data.get("nbformat")
    if fmt != 4:
        raise NotebookError(f"unsupported nbformat {fmt!r} (cellvet reads nbformat 4)")

    raw_cells = data.get("cells")
    if not isinstance(raw_cells, list):
        raise NotebookError("notebook has no 'cells' list")

    nb = Notebook(path=path, total_cells=len(raw_cells))
    code_index = 0
    for doc_index, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise NotebookError(f"cell {doc_index} is not a JSON object")
        if raw.get("cell_type") != "code":
            continue
        code_index += 1
        nb.cells.append(
            Cell(
                index=code_index,
                doc_index=doc_index,
                source=_join_source(raw.get("source", "")),
                execution_count=_parse_execution_count(raw.get("execution_count")),
            )
        )
    return nb


def load_notebook(path: str) -> Notebook:
    """Read and parse a notebook file from disk."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise NotebookError(f"cannot read {path}: {exc.strerror or exc}") from exc
    return parse_notebook(text, path=path)
