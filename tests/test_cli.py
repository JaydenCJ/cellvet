"""End-to-end CLI behavior: exit codes, formats, discovery, subcommands."""

import json
import os
import subprocess
import sys

from cellvet import __version__
from cellvet.cli import main

from conftest import code, make_notebook


CLEAN = (code("x = 1", 1), code("y = x + 1", 2))
BUGGY = (code("print(result)", 3), code("result = 42", 1))
# executed out of order, but every name still resolves: warnings only
WARN_ONLY = (code("x = 1", 5), code("y = x + 1", 6), code("z = 1", 2))


def test_check_clean_notebook_exits_zero_and_quiet_silences_it(write_notebook, capsys):
    path = write_notebook(*CLEAN)
    assert main(["check", path]) == 0
    assert "no hidden-state issues in 1 notebook" in capsys.readouterr().out
    assert main(["check", "--quiet", path]) == 0
    assert capsys.readouterr().out == ""


def test_check_buggy_notebook_exits_one_and_reports(write_notebook, capsys):
    path = write_notebook(*BUGGY)
    assert main(["check", path]) == 1
    out = capsys.readouterr().out
    assert "N202" in out and "E101" in out
    assert "'result'" in out


def test_warnings_exit_zero_unless_strict(write_notebook):
    path = write_notebook(*WARN_ONLY)
    assert main(["check", path]) == 0
    assert main(["check", "--strict", path]) == 1


def test_json_format_emits_parseable_payload_and_select_filters_it(write_notebook, capsys):
    path = write_notebook(*BUGGY)
    assert main(["check", "--format", "json", path]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["notebooks_checked"] == 1
    assert any(f["rule"] == "N202" for f in payload["findings"])
    main(["check", "--format", "json", "--select", "E101,E103", path])
    filtered = json.loads(capsys.readouterr().out)
    assert {f["rule"] for f in filtered["findings"]} <= {"E101", "E103"}


def test_ignore_drops_rules_and_can_flip_exit_code(write_notebook):
    path = write_notebook(*BUGGY)
    assert main(["check", "--ignore", "N", path]) == 0


def test_unknown_rule_selector_is_a_usage_error(write_notebook, capsys):
    path = write_notebook(*CLEAN)
    assert main(["check", "--select", "X9", path]) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_directory_discovery_recurses_and_skips_checkpoints(tmp_path, capsys):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "good.ipynb").write_text(make_notebook(*CLEAN))
    (tmp_path / "bad.ipynb").write_text(make_notebook(*BUGGY))
    ckpt = tmp_path / ".ipynb_checkpoints"
    ckpt.mkdir()
    (ckpt / "bad-checkpoint.ipynb").write_text(make_notebook(*BUGGY))
    assert main(["check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "2 notebooks" in out
    assert "checkpoint" not in out


def test_unusable_inputs_are_usage_errors(tmp_path, capsys):
    assert main(["check", str(tmp_path / "nope.ipynb")]) == 2
    assert "cannot read" in capsys.readouterr().err
    corrupt = tmp_path / "corrupt.ipynb"
    corrupt.write_text("{broken")
    assert main(["check", str(corrupt)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    (tmp_path / "empty").mkdir()
    assert main(["check", str(tmp_path / "empty")]) == 2
    assert "no notebooks found" in capsys.readouterr().err


def test_order_command_compares_the_two_orders(write_notebook, capsys):
    buggy = write_notebook(*BUGGY, name="buggy")
    assert main(["order", buggy]) == 0
    out = capsys.readouterr().out
    assert "2 code cells, 2 executed" in out
    assert "execution order differs from document order" in out
    clean = write_notebook(*CLEAN, name="clean")
    main(["order", clean])
    assert "execution order matches document order" in capsys.readouterr().out


def test_rules_command_lists_every_rule_and_bare_invocation_shows_help(capsys):
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    for rule_id in ("E101", "N201", "H301", "W401"):
        assert rule_id in out
    assert main([]) == 2
    assert "usage: cellvet" in capsys.readouterr().out


def test_version_flag(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.strip() == f"cellvet {__version__}"


def test_module_entry_point_runs(write_notebook):
    # `python -m cellvet` must behave like the console script
    path = write_notebook(*CLEAN)
    env = dict(os.environ)
    src = os.path.join(os.path.dirname(__file__), "..", "src")
    env["PYTHONPATH"] = os.path.abspath(src)
    proc = subprocess.run(
        [sys.executable, "-m", "cellvet", "check", path],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0
    assert "no hidden-state issues" in proc.stdout
