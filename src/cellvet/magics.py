"""Rewriting IPython-only syntax into analyzable Python.

Notebook cells are not plain Python: they may contain line magics
(``%cd ..``), cell magics (``%%bash``), shell escapes (``!pip list``),
capture assignments (``files = !ls``) and help queries (``df.head?``).
``ast.parse`` rejects all of these, so cellvet rewrites each cell into an
equivalent-for-name-flow Python source **with the same number of lines**,
preserving line numbers in findings.

The rewrite is deliberately conservative:

- opaque cell magics (``%%bash``, ``%%html``, ...) blank the whole cell —
  the body is not Python and defines no Python names we can trust;
- transparent cell magics (``%%time``, ``%%capture``) keep the body,
  and ``%%capture out`` additionally binds ``out``;
- ``x = !cmd`` and ``x = %magic`` become ``x = None`` so the binding of
  ``x`` survives analysis;
- bare magics, shell escapes and ``?`` help lines become ``pass`` at the
  same indentation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# Cell magics whose body is executed as regular Python in the user
# namespace, so name analysis of the body stays meaningful.
TRANSPARENT_CELL_MAGICS = frozenset({"time", "capture", "prun", "debug"})

_CELL_MAGIC_RE = re.compile(r"^\s*%%(?P<name>[A-Za-z_][\w.]*)(?P<args>.*)$")
_LINE_MAGIC_RE = re.compile(r"^(?P<indent>\s*)%(?P<name>[A-Za-z_][\w.]*)(?P<rest>.*)$")
_SHELL_RE = re.compile(r"^(?P<indent>\s*)!(?!=)")
_CAPTURE_ASSIGN_RE = re.compile(
    r"^(?P<indent>\s*)(?P<target>[A-Za-z_]\w*)\s*=\s*[!%][^=].*$"
)
_HELP_RE = re.compile(r"^(?P<indent>\s*)[\w.\[\]'\"]+\s*\?{1,2}\s*$")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


@dataclass
class RewriteResult:
    """A cell rewritten to plain Python plus what the rewrite implied."""

    source: str
    #: names bound by IPython constructs (e.g. ``%%capture out``, ``x = !ls``)
    implied_defines: List[str] = field(default_factory=list)
    #: True when an opaque cell magic blanked the whole cell
    opaque: bool = False


def _blank_like(lines: List[str]) -> str:
    """Same line count as ``lines``, but nothing to analyze."""
    return "\n".join("" for _ in lines)


def rewrite_cell(source: str) -> RewriteResult:
    """Rewrite one cell's source into plain Python of identical line count."""
    lines = source.split("\n")
    result = RewriteResult(source="")

    cm = _CELL_MAGIC_RE.match(lines[0]) if lines else None
    if cm:
        name = cm.group("name")
        if name not in TRANSPARENT_CELL_MAGICS:
            result.opaque = True
            result.source = _blank_like(lines)
            return result
        # Transparent: neutralize the magic line, keep the body.
        if name == "capture":
            target = _IDENT_RE.match(cm.group("args").strip())
            if target:
                result.implied_defines.append(target.group(0))
        lines = ["pass"] + lines[1:]

    out: List[str] = []
    for line in lines:
        out.append(_rewrite_line(line, result))
    result.source = "\n".join(out)
    return result


def _rewrite_line(line: str, result: RewriteResult) -> str:
    """Rewrite a single line; records implied bindings on ``result``."""
    capture = _CAPTURE_ASSIGN_RE.match(line)
    if capture:
        result.implied_defines.append(capture.group("target"))
        return f"{capture.group('indent')}{capture.group('target')} = None"

    shell = _SHELL_RE.match(line)
    if shell:
        return f"{shell.group('indent')}pass"

    magic = _LINE_MAGIC_RE.match(line)
    if magic:
        # `%time expr` and `%timeit expr` wrap real Python; keep the payload
        # so its name uses are still seen. Everything else becomes `pass`.
        if magic.group("name") in {"time", "timeit"} and magic.group("rest").strip():
            return f"{magic.group('indent')}{magic.group('rest').strip()}"
        return f"{magic.group('indent')}pass"

    helpq = _HELP_RE.match(line)
    if helpq:
        return f"{helpq.group('indent')}pass"

    return line
