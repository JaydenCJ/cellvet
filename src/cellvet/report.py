"""Rendering findings as text (for terminals) or JSON (for tooling)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List

from .rules import RULES, Finding, Severity


def render_text(findings: List[Finding], notebooks_checked: int) -> str:
    """Grouped-by-file report plus a one-line summary."""
    lines: List[str] = []
    by_path: Dict[str, List[Finding]] = {}
    for finding in findings:
        by_path.setdefault(finding.path, []).append(finding)

    for path in sorted(by_path):
        lines.append(path)
        for f in by_path[path]:
            where = f"cell {f.cell}" if f.cell is not None else "notebook"
            if f.line is not None:
                where += f", line {f.line}"
            rule = RULES[f.rule]
            lines.append(f"  {where}: {f.rule} {rule.name} [{f.severity}]")
            lines.append(f"    {f.message}")
        lines.append("")

    lines.append(summary_line(findings, notebooks_checked))
    return "\n".join(lines)


def summary_line(findings: List[Finding], notebooks_checked: int) -> str:
    counts = Counter(f.severity for f in findings)
    noun = "notebook" if notebooks_checked == 1 else "notebooks"
    if not findings:
        return f"no hidden-state issues in {notebooks_checked} {noun}"
    parts = []
    for severity, word in ((Severity.ERROR, "error"), (Severity.WARNING, "warning")):
        n = counts.get(severity, 0)
        if n:
            parts.append(f"{n} {word}{'' if n == 1 else 's'}")
    if counts.get(Severity.INFO, 0):
        parts.append(f"{counts[Severity.INFO]} info")
    return f"{', '.join(parts)} in {notebooks_checked} {noun}"


def render_json(findings: List[Finding], notebooks_checked: int) -> str:
    """Stable, sorted-key JSON for editors, bots, and CI annotations."""
    payload = {
        "notebooks_checked": notebooks_checked,
        "findings": [f.to_dict() for f in findings],
        "counts": {
            severity: sum(1 for f in findings if f.severity == severity)
            for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO)
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)
