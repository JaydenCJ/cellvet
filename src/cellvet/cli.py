"""The ``cellvet`` command-line interface.

Subcommands:

- ``cellvet check <path>...``  — analyze notebooks; exit 1 when errors are
  found (or any finding with ``--strict``), exit 2 on unusable input;
- ``cellvet order <notebook>`` — show document order vs. execution order;
- ``cellvet rules``            — list every rule with severity and summary.

Directories are searched recursively for ``*.ipynb``;
``.ipynb_checkpoints`` directories are always skipped.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence, Set

from . import __version__
from .analyzer import Config, analyze_notebook
from .notebook import Notebook, NotebookError, load_notebook
from .report import render_json, render_text, summary_line
from .rules import RULES, Severity

USAGE_ERROR = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cellvet",
        description="Detect hidden-state bugs in Jupyter notebooks — statically.",
    )
    parser.add_argument(
        "--version", action="version", version=f"cellvet {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    check = sub.add_parser(
        "check", help="analyze notebooks for hidden-state bugs"
    )
    check.add_argument(
        "paths", nargs="+", metavar="path", help=".ipynb files or directories"
    )
    check.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument(
        "--select",
        action="append",
        default=None,
        metavar="RULES",
        help="only these rules; comma-separated IDs or prefixes (e.g. N201,E)",
    )
    check.add_argument(
        "--ignore",
        action="append",
        default=None,
        metavar="RULES",
        help="skip these rules; comma-separated IDs or prefixes",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on any finding, not only on errors",
    )
    check.add_argument(
        "--quiet",
        action="store_true",
        help="print nothing when the notebooks are clean",
    )

    order = sub.add_parser(
        "order", help="show a notebook's document order vs. execution order"
    )
    order.add_argument("path", metavar="notebook", help="an .ipynb file")

    sub.add_parser("rules", help="list all rules")
    return parser


def _split_rule_args(values: Optional[List[str]]) -> Optional[Set[str]]:
    if values is None:
        return None
    out: Set[str] = set()
    for value in values:
        out.update(part.strip() for part in value.split(",") if part.strip())
    return out or None


def _discover(paths: Sequence[str]) -> List[str]:
    """Expand files and directories into a sorted list of notebook paths."""
    found: List[str] = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d != ".ipynb_checkpoints")
                for name in sorted(files):
                    if name.endswith(".ipynb"):
                        found.append(os.path.join(root, name))
        else:
            found.append(path)
    return found


def _cmd_check(args: argparse.Namespace) -> int:
    config = Config(
        select=_split_rule_args(args.select),
        ignore=_split_rule_args(args.ignore) or set(),
    )
    try:
        config.validate()
    except ValueError as exc:
        print(f"cellvet: error: {exc}", file=sys.stderr)
        return USAGE_ERROR

    paths = _discover(args.paths)
    if not paths:
        print("cellvet: error: no notebooks found", file=sys.stderr)
        return USAGE_ERROR

    findings = []
    for path in paths:
        try:
            findings.extend(analyze_notebook(load_notebook(path), config))
        except NotebookError as exc:
            print(f"cellvet: error: {path}: {exc}", file=sys.stderr)
            return USAGE_ERROR

    if args.format == "json":
        print(render_json(findings, len(paths)))
    elif findings:
        print(render_text(findings, len(paths)))
    elif not args.quiet:
        print(summary_line(findings, len(paths)))

    if args.strict:
        return 1 if findings else 0
    return 1 if any(f.severity == Severity.ERROR for f in findings) else 0


def _cmd_order(args: argparse.Namespace) -> int:
    try:
        nb = load_notebook(args.path)
    except NotebookError as exc:
        print(f"cellvet: error: {args.path}: {exc}", file=sys.stderr)
        return USAGE_ERROR
    print(_render_order(nb))
    return 0


def _render_order(nb: Notebook) -> str:
    lines = [
        f"{nb.path} — {len(nb.cells)} code cells, {len(nb.executed_cells)} executed",
        " doc | In [#] | first line",
    ]
    for cell in nb.cells:
        count = str(cell.execution_count) if cell.is_executed else "-"
        first = next(
            (ln.strip() for ln in cell.source.splitlines() if ln.strip()), ""
        )
        if len(first) > 60:
            first = first[:57] + "..."
        lines.append(f" {cell.index:>3} | {count:<6} | {first}")
    executed = [c.execution_count for c in nb.executed_cells]
    if executed == sorted(executed) and len(set(executed)) == len(executed):
        lines.append("execution order matches document order")
    else:
        lines.append("execution order differs from document order")
    return "\n".join(lines)


def _cmd_rules() -> int:
    width = max(len(rule.name) for rule in RULES.values())
    for rule in RULES.values():
        print(f"{rule.id}  {rule.name:<{width}}  [{rule.severity:<7}]  {rule.summary}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "order":
        return _cmd_order(args)
    if args.command == "rules":
        return _cmd_rules()
    parser.print_help()
    return USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
