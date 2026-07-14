"""Cross-cell name-flow analysis: the document-order vs kernel-order replays.

This is the heart of cellvet — the cases here are the real notebook bugs
the tool exists to catch, each encoded as a miniature notebook.
"""

from cellvet.flow import analyze_flow

from conftest import code, nb_from


def rules_of(findings):
    return [f.rule for f in findings]


def only(findings, rule):
    return [f for f in findings if f.rule == rule]


# -- clean notebooks ---------------------------------------------------------


def test_clean_notebooks_stay_clean():
    ordered = nb_from(
        code("import json", 1),
        code("data = json.loads('[1, 2]')", 2),
        code("total = sum(data)", 3),
    )
    builtins_only = nb_from(code("print(len([1]))\ndisplay(sorted([2, 1]))", 1))
    unexecuted = nb_from(code("x = 1"), code("y = x + 1"))
    assert analyze_flow(ordered) == []
    assert analyze_flow(builtins_only) == []
    assert analyze_flow(unexecuted) == []


# -- N201 undefined-name -----------------------------------------------------


def test_name_never_defined_anywhere_is_n201_reported_once_per_cell():
    nb = nb_from(code("summary = df.describe()\nprint(df)\nprint(df)", 1))
    findings = analyze_flow(nb)
    assert rules_of(findings) == ["N201"]
    assert "'df'" in findings[0].message
    assert findings[0].cell == 1 and findings[0].line == 1


def test_deferred_uses_resolve_against_the_whole_notebook():
    # defining `template` further down is legal — the function is only
    # called after that cell; but a name defined NOWHERE is still a bug
    fine = nb_from(
        code("def report():\n    return template.format(1)", 1),
        code("template = 'total: {}'", 2),
    )
    assert analyze_flow(fine) == []
    broken = nb_from(code("def report():\n    return template.format(1)", 1))
    findings = only(analyze_flow(broken), "N201")
    assert len(findings) == 1
    assert "inside a function" in findings[0].message


# -- N202 defined-after-use --------------------------------------------------


def test_use_before_defining_cell_is_n202():
    nb = nb_from(code("print(result)"), code("result = 42"))
    findings = only(analyze_flow(nb), "N202")
    assert len(findings) == 1
    assert "cell 2" in findings[0].message


def test_n202_explains_the_kernel_order_that_made_it_work():
    # the classic: cell shown first, but executed second
    nb = nb_from(
        code("mean = statistics.mean(data)", 4),
        code("import statistics\ndata = [1, 2, 3]", 2),
    )
    findings = only(analyze_flow(nb), "N202")
    assert len(findings) == 2  # statistics and data
    assert all("worked in your session only because" in f.message for f in findings)
    assert all("In [2]" in f.message for f in findings)


def test_use_before_assignment_in_the_same_cell_is_n202():
    nb = nb_from(code("print(x)\nx = 1", 1))
    findings = only(analyze_flow(nb), "N202")
    assert len(findings) == 1
    assert "this same cell" in findings[0].message


def test_self_referential_first_assignment_is_n202():
    # `x = x + 1` with no earlier x only ever worked against stale state
    nb = nb_from(code("x = x + 1", 1))
    assert rules_of(analyze_flow(nb)) == ["N202"]


# -- N203 use-after-delete ----------------------------------------------------


def test_use_after_del_in_earlier_cell_is_n203_until_redefined():
    nb = nb_from(
        code("data = [1, 2]", 1),
        code("del data", 2),
        code("print(data)", 3),
    )
    findings = only(analyze_flow(nb), "N203")
    assert len(findings) == 1
    assert "cell 2" in findings[0].message
    redefined = nb_from(
        code("data = [1]", 1),
        code("del data", 2),
        code("data = [2]", 3),
        code("print(data)", 4),
    )
    assert analyze_flow(redefined) == []


def test_use_after_del_in_the_same_cell_is_n203():
    nb = nb_from(code("data = [1]", 1), code("del data\nprint(data)", 2))
    assert rules_of(analyze_flow(nb)) == ["N203"]


# -- H301 order-dependent binding ---------------------------------------------


def test_binding_from_a_different_cell_at_run_time_is_h301():
    # doc order: cell 1 defines rate, cell 2 uses it, cell 3 redefines it.
    # kernel order: cell 3 ran BEFORE cell 2, so cell 2 actually saw cell
    # 3's value — its saved output will not reproduce on a fresh run.
    nb = nb_from(
        code("rate = 0.1", 1),
        code("price = 100 * (1 + rate)", 5),
        code("rate = 0.25", 3),
    )
    findings = only(analyze_flow(nb), "H301")
    assert len(findings) == 1
    assert findings[0].cell == 2
    assert "cell 1" in findings[0].message and "cell 3" in findings[0].message


def test_h301_needs_evidence_of_a_different_provider():
    # same provider cell in both orders: re-execution alone is fine
    rerun = nb_from(
        code("rate = 0.1", 4),
        code("price = 100 * (1 + rate)", 5),
    )
    assert analyze_flow(rerun) == []
    # a never-executed redefinition leaves no kernel-order evidence
    unexecuted = nb_from(
        code("rate = 0.1", 1),
        code("price = 100 * (1 + rate)", 2),
        code("rate = 0.25"),
    )
    assert analyze_flow(unexecuted) == []


# -- star imports and unparsable cells -----------------------------------------


def test_star_import_emits_w401_and_suppresses_n201_after_it():
    nb = nb_from(
        code("from math import *", 1),
        code("print(sqrt(2))", 2),
    )
    assert rules_of(analyze_flow(nb)) == ["W401"]


def test_star_import_suppresses_only_from_its_own_position():
    later_cell = nb_from(code("print(sqrt(2))", 1), code("from math import *", 2))
    assert "N201" in rules_of(analyze_flow(later_cell))
    later_line = nb_from(code("print(sqrt(2))\nfrom math import *", 1))
    assert "N201" in rules_of(analyze_flow(later_line))


def test_unparsable_cell_is_p001_and_does_not_crash_the_replay():
    nb = nb_from(
        code("x = 1", 1),
        code("def broken(:", 2),
        code("print(x)", 3),
    )
    findings = analyze_flow(nb)
    assert rules_of(findings) == ["P001"]
    assert findings[0].cell == 2


# -- magics integration ---------------------------------------------------------


def test_shell_capture_assignment_counts_as_a_definition():
    nb = nb_from(code("files = !ls", 1), code("print(files)", 2))
    assert analyze_flow(nb) == []


def test_opaque_cell_magic_neither_defines_nor_uses():
    nb = nb_from(code("%%bash\necho $HOME", 1), code("x = 1", 2))
    assert analyze_flow(nb) == []


def test_findings_point_at_the_correct_line_despite_magics():
    nb = nb_from(code("%matplotlib inline\nplot(df)", 1))
    findings = only(analyze_flow(nb), "N201")
    assert sorted(f.line for f in findings) == [2, 2]
