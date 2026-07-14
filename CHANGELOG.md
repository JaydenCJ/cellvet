# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Static hidden-state analysis for nbformat-4 Jupyter notebooks: pure
  stdlib (`json` + `ast`), no kernel, no execution, no network.
- Execution-order checks from cell metadata alone: `E101`
  out-of-order-execution, `E102` never-executed-cell, `E103`
  execution-count-gap, `E104` duplicate-execution-count.
- Cross-cell name-flow analysis with a document-order replay: `N201`
  undefined-name, `N202` defined-after-use, `N203` use-after-delete.
  Scope handling covers function locals (pre-scanned like CPython's symbol
  table), deferred call-time reads inside functions and lambdas, `global`
  declarations, comprehension scopes with walrus leakage, and
  class-body-vs-method visibility.
- Kernel-order replay reconstructed from `In [n]` counts: `N202` messages
  explain which cell's earlier execution made the broken notebook "work",
  and `H301` order-dependent-binding flags cells whose saved output was
  computed from a different cell's definition than a fresh run will use.
- IPython syntax rewriting that preserves line numbers: line/cell magics,
  shell escapes, `x = !cmd` / `x = %magic` capture assignments,
  `%%capture` targets, and `?` help queries; opaque cell magics
  (`%%bash`, ...) are excluded from analysis instead of misread.
- Analysis-confidence rules: `P001` unparsable-cell and `W401` star-import
  (which suppresses undefined-name checks from its position onward).
- `cellvet` CLI: `check` (text/JSON output, `--select`/`--ignore` by rule ID
  or family prefix, `--strict`, `--quiet`, recursive directory discovery
  that skips `.ipynb_checkpoints`), `order` (document order vs. execution
  order side by side), and `rules` (the registry). Exit codes: 0 clean,
  1 findings, 2 unusable input.
- Public Python API (`analyze_path`, `analyze_notebook`, `load_notebook`,
  `Config`) for embedding in other tools.
- Rule reference (`docs/rules.md`), runnable example notebooks
  (`examples/`), 90 offline tests, and `scripts/smoke.sh`.

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/cellvet/releases/tag/v0.1.0
