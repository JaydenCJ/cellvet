"""The orchestration layer: config filtering and combined analysis."""

import pytest

from cellvet import Config, analyze_notebook, analyze_path

from conftest import code, nb_from


BUGGY = (
    code("mean = statistics.mean(data)", 4),
    code("import statistics\ndata = [1, 2, 3]", 2),
    code("print(undefined_thing)", 5),
)


def test_combined_analysis_fires_all_families_sorted_by_cell_then_line():
    nb = nb_from(*BUGGY)
    findings = analyze_notebook(nb)
    assert {"E101", "E103", "N201", "N202"} <= {f.rule for f in findings}
    keys = [(f.cell or 0, f.line or 0) for f in findings]
    assert keys == sorted(keys)


def test_select_accepts_full_ids_and_family_prefixes():
    nb = nb_from(*BUGGY)
    by_id = analyze_notebook(nb, Config(select={"N201"}))
    assert {f.rule for f in by_id} == {"N201"}
    by_prefix = analyze_notebook(nb, Config(select={"E"}))
    assert by_prefix and {f.rule for f in by_prefix} <= {"E101", "E102", "E103", "E104"}


def test_ignore_wins_over_select():
    nb = nb_from(*BUGGY)
    findings = analyze_notebook(nb, Config(select={"N"}, ignore={"N202"}))
    assert {f.rule for f in findings} == {"N201"}


def test_unknown_selector_is_rejected():
    with pytest.raises(ValueError, match="unknown rule"):
        Config(select={"Z999"}).validate()


def test_analyze_path_reads_from_disk(write_notebook):
    path = write_notebook(code("print(df)", 1))
    findings = analyze_path(path)
    assert [f.rule for f in findings] == ["N201"]
    assert findings[0].path == path


def test_finding_to_dict_carries_severity_and_rule_name():
    nb = nb_from(code("print(df)", 1))
    (finding,) = analyze_notebook(nb)
    data = finding.to_dict()
    assert data["severity"] == "error"
    assert data["name"] == "undefined-name"
    assert data["cell"] == 1
