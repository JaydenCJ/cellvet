"""Execution-order metadata checks (E101-E104)."""

from cellvet.execution import check_execution_order

from conftest import code, nb_from


def rules_of(findings):
    return [f.rule for f in findings]


def test_monotonic_contiguous_execution_order_is_clean():
    nb = nb_from(code("a = 1", 1), code("b = 2", 2), code("c = 3", 3))
    assert check_execution_order(nb) == []


def test_out_of_order_cell_triggers_e101():
    nb = nb_from(code("b", 5), code("a", 2))
    findings = check_execution_order(nb)
    assert "E101" in rules_of(findings)
    e101 = next(f for f in findings if f.rule == "E101")
    assert e101.cell == 2
    assert "In [2]" in e101.message and "In [5]" in e101.message


def test_e101_fires_once_per_offending_cell():
    nb = nb_from(code("c", 9), code("a", 1), code("b", 2))
    findings = [f for f in check_execution_order(nb) if f.rule == "E101"]
    assert [f.cell for f in findings] == [2, 3]


def test_never_executed_cell_triggers_e102():
    nb = nb_from(code("a = 1", 1), code("b = a + 1"))
    findings = check_execution_order(nb)
    assert rules_of(findings) == ["E102"]
    assert findings[0].cell == 2


def test_fully_unexecuted_notebook_is_not_flagged():
    # a stripped/exported notebook has no execution story to distrust
    nb = nb_from(code("a = 1"), code("b = a + 1"))
    assert check_execution_order(nb) == []


def test_blank_unexecuted_cells_are_not_flagged():
    nb = nb_from(code("a = 1", 1), code(""), code("# scratch"))
    assert check_execution_order(nb) == []


def test_gap_in_execution_counts_triggers_e103_once():
    nb = nb_from(code("a", 1), code("b", 5))
    findings = check_execution_order(nb)
    assert rules_of(findings) == ["E103"]
    assert "In [2, 3, 4]" in findings[0].message


def test_long_gap_list_is_truncated_in_the_message():
    nb = nb_from(code("a", 1), code("b", 20))
    findings = check_execution_order(nb)
    assert "..." in findings[0].message and "18 total" in findings[0].message


def test_duplicate_execution_counts_trigger_e104_on_both_cells():
    nb = nb_from(code("a", 3), code("b", 3))
    findings = [f for f in check_execution_order(nb) if f.rule == "E104"]
    assert [f.cell for f in findings] == [1, 2]
    assert "different sessions" in findings[0].message
