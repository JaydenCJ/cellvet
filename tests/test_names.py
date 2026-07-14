"""Name extraction: defines, uses (immediate vs deferred), deletes, scoping.

These tests pin the scoping rules that make cellvet's cross-cell analysis
trustworthy: function locals must not look like notebook dependencies,
and deferred (call-time) reads must not be confused with immediate ones.
"""

from cellvet.names import extract_names, is_builtin


def defined(src):
    return {ev.name for ev in extract_names(src).defines}


# The extractor is deliberately builtin-agnostic (flow.py filters builtins
# at replay time), so these helpers apply the same filter the analyzer does.


def immediate(src):
    return {
        ev.name for ev in extract_names(src).immediate_uses if not is_builtin(ev.name)
    }


def deferred(src):
    return {
        ev.name for ev in extract_names(src).deferred_uses if not is_builtin(ev.name)
    }


# -- defines ---------------------------------------------------------------


def test_assignment_targets_define_including_unpacking():
    assert defined("x = 1") == {"x"}
    assert defined("a = b = 1\nc, d = 1, 2\n[e, *rest] = [1, 2, 3]") == {
        "a", "b", "c", "d", "e", "rest",
    }


def test_imports_defs_and_classes_define_their_bound_names():
    src = "import os\nimport os.path\nimport numpy as np\nfrom json import loads as parse"
    assert defined(src) == {"os", "np", "parse"}
    assert defined("def f():\n    pass\nclass C:\n    pass") == {"f", "C"}


def test_for_loop_and_with_as_targets_define():
    src = "for i, row in enumerate(data):\n    pass\nwith open('f') as fh:\n    pass"
    assert defined(src) >= {"i", "row", "fh"}


def test_walrus_defines_at_module_level_even_inside_comprehensions():
    assert "n" in defined("if (n := len(items)) > 3:\n    pass")
    # PEP 572: assignment expressions in a comprehension bind in the
    # containing scope — a real notebook idiom for capturing a last value
    assert "last" in defined("values = [(last := v) for v in data]")


def test_bare_annotations_and_class_attributes_do_not_define_module_names():
    assert defined("x: int") == set()
    assert "x" in defined("x: int = 1")
    assert defined("class C:\n    attr = 1") == {"C"}


def test_del_records_a_delete_event():
    result = extract_names("x = 1\ndel x")
    assert [(ev.name, ev.line) for ev in result.deletes] == [("x", 2)]


# -- immediate uses --------------------------------------------------------


def test_within_cell_ordering_decides_whether_a_use_is_a_dependency():
    assert immediate("print(df)") == {"df"}
    assert immediate("x = 1\nprint(x)") == set()  # defined above the use
    result = extract_names("print(x)\nx = 1")  # used above the definition
    uses = [(ev.name, ev.line) for ev in result.immediate_uses if not is_builtin(ev.name)]
    assert uses == [("x", 1)]


def test_augmented_assignment_reads_before_writing():
    result = extract_names("total += 1")
    assert {ev.name for ev in result.immediate_uses} == {"total"}
    assert {ev.name for ev in result.defines} == {"total"}


def test_attribute_and_subscript_stores_read_the_base_object():
    assert immediate("df.col = 1\ncache['k'] = 2") == {"df", "cache"}


def test_decorators_defaults_bases_and_class_bodies_evaluate_immediately():
    src = "@register\ndef f(x=default):\n    pass\nclass C(Base):\n    value = seed * 2"
    assert immediate(src) == {"register", "default", "Base", "seed"}


def test_comprehension_target_does_not_leak_but_iterable_is_used():
    result = extract_names("squares = [i * i for i in numbers]")
    assert {ev.name for ev in result.immediate_uses} == {"numbers"}
    assert "i" not in {ev.name for ev in result.defines}


# -- deferred uses (function bodies) ----------------------------------------


def test_function_free_names_are_deferred_and_locals_are_not():
    src = "def report():\n    return template.format(stats)"
    assert deferred(src) == {"template", "stats"}
    assert immediate(src) == set()
    # params and locals assigned anywhere in the body are not free —
    # Python's symbol table makes `x` local for the whole body
    assert deferred("def f(a, b=1, *args):\n    y = x\n    x = a\n    return y") == set()


def test_global_declaration_keeps_the_name_a_module_reference():
    assert deferred("def bump():\n    global counter\n    counter = counter + 1") == {"counter"}


def test_nested_functions_and_lambdas_see_enclosing_locals():
    src = "def outer():\n    n = 1\n    def inner():\n        return n + m\n    return inner"
    assert deferred(src) == {"m"}
    result = extract_names("key = lambda row: row[column]")
    assert {ev.name for ev in result.deferred_uses} == {"column"}


def test_class_scope_is_invisible_to_methods():
    # a method reading `attr` does NOT see the class attribute — that read
    # goes to module scope, exactly the trap this rule family catches
    src = "class C:\n    attr = 1\n    def m(self):\n        return attr"
    assert deferred(src) == {"attr"}


def test_except_handler_name_is_a_local_inside_functions():
    src = "def f():\n    try:\n        pass\n    except ValueError as exc:\n        return exc"
    assert deferred(src) == set()


# -- star imports, errors, builtins ------------------------------------------


def test_star_import_sets_the_flag_and_syntax_errors_are_reported_not_raised():
    assert extract_names("x = 1\nfrom math import *").star_import_line == 2
    broken = extract_names("def broken(:\n    pass")
    assert broken.syntax_error is not None
    assert broken.defines == []


def test_builtins_and_notebook_globals_are_recognized():
    assert is_builtin("len") and is_builtin("print")
    assert is_builtin("display") and is_builtin("get_ipython")
    assert not is_builtin("df")
