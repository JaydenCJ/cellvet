"""Text and JSON rendering of findings."""

import json

from cellvet.analyzer import analyze_notebook
from cellvet.report import render_json, render_text, summary_line

from conftest import code, nb_from


def _findings():
    nb = nb_from(
        code("mean = statistics.mean(data)", 4),
        code("import statistics\ndata = [1, 2, 3]", 2),
    )
    return analyze_notebook(nb)


def test_text_report_groups_by_path_and_names_the_rule():
    text = render_text(_findings(), notebooks_checked=1)
    assert "memory.ipynb" in text
    assert "N202 defined-after-use [error]" in text
    assert "cell 1, line 1" in text


def test_text_report_ends_with_a_summary_line():
    text = render_text(_findings(), notebooks_checked=1)
    assert text.splitlines()[-1].endswith("in 1 notebook")


def test_summary_line_counts_by_severity_and_pluralizes():
    # _findings() yields 2 N202 errors, 1 E101 warning, 1 E103 info:
    # singular "warning", plural "errors", and no "0 ..." noise.
    line = summary_line(_findings(), notebooks_checked=1)
    assert line == "2 errors, 1 warning, 1 info in 1 notebook"
    only_error = [f for f in _findings() if f.severity == "error"][:1]
    assert summary_line(only_error, notebooks_checked=1) == "1 error in 1 notebook"


def test_clean_runs_render_cleanly_in_both_formats():
    assert summary_line([], 3) == "no hidden-state issues in 3 notebooks"
    payload = json.loads(render_json([], notebooks_checked=2))
    assert payload["findings"] == []
    assert payload["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_json_report_is_valid_and_machine_friendly():
    payload = json.loads(render_json(_findings(), notebooks_checked=1))
    assert payload["notebooks_checked"] == 1
    assert payload["counts"]["error"] == 2
    first = payload["findings"][0]
    assert {"rule", "severity", "name", "path", "cell", "line", "message"} <= set(first)
