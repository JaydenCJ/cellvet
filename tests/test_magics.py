"""Rewriting IPython magics/shell syntax into analyzable Python.

Every rewrite must preserve the line count of the cell (findings point at
real lines) and must yield source that ``ast.parse`` accepts.
"""

import ast

from cellvet.magics import rewrite_cell


def test_plain_python_is_untouched_including_percent_operators():
    for src in ("x = 1\ny = x + 1", "a = 7 % 3\nfmt = '%s' % name", "ok = a != b"):
        assert rewrite_cell(src).source == src


def test_line_magic_and_shell_escape_become_pass():
    out = rewrite_cell("%matplotlib inline\n!pip list\nx = 1")
    assert out.source == "pass\npass\nx = 1"
    ast.parse(out.source)


def test_indented_shell_escape_keeps_indentation():
    out = rewrite_cell("for i in range(3):\n    !date")
    assert out.source == "for i in range(3):\n    pass"
    ast.parse(out.source)


def test_capture_assignments_bind_their_targets():
    shell = rewrite_cell("files = !ls -la")
    magic = rewrite_cell("home = %env HOME")
    assert shell.source == "files = None" and shell.implied_defines == ["files"]
    assert magic.source == "home = None" and magic.implied_defines == ["home"]


def test_time_line_magic_keeps_the_payload_statement():
    # %time wraps real Python; the names inside must stay visible
    out = rewrite_cell("%time result = compute(data)")
    assert out.source == "result = compute(data)"
    assert isinstance(ast.parse(out.source).body[0], ast.Assign)
    assert rewrite_cell("%time").source == "pass"  # bare form has no payload


def test_help_query_lines_become_pass():
    assert rewrite_cell("df.head?\nlen??").source == "pass\npass"


def test_opaque_cell_magic_blanks_the_whole_cell():
    out = rewrite_cell("%%bash\necho hi\nexport X=1")
    assert out.opaque is True
    assert ast.parse(out.source).body == []
    assert len(out.source.split("\n")) == 3  # line count preserved


def test_transparent_time_cell_magic_keeps_the_body():
    out = rewrite_cell("%%time\ntotal = sum(values)")
    assert out.opaque is False
    assert out.source == "pass\ntotal = sum(values)"


def test_capture_cell_magic_binds_its_argument():
    out = rewrite_cell("%%capture output\nprint('hi')")
    assert out.implied_defines == ["output"]
    assert "print('hi')" in out.source


def test_rewrite_always_preserves_line_count():
    cases = [
        "%%bash\na\nb\nc",
        "%cd ..\nx = 1\n!ls\ny = 2",
        "files = !ls\n%time z = 1\nobj?",
    ]
    for src in cases:
        assert len(rewrite_cell(src).source.split("\n")) == len(src.split("\n"))
