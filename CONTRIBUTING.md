# Contributing to cellvet

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/cellvet
cd cellvet
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 90 unit + CLI tests, fully offline
bash scripts/smoke.sh  # end-to-end: real CLI against the example notebooks
```

Both must pass before a pull request is reviewed; `smoke.sh` must print
`SMOKE OK`. The suite needs no kernel, no Jupyter installation, and no
network.

## Ground rules

- **No new runtime dependencies.** The analyzer is standard-library only
  (`ast` + `json`); that is a feature. Test-only dependencies belong in the
  `dev` extra.
- **Rule IDs are stable.** Never reuse or renumber an existing ID. A new rule
  needs an entry in `rules.py`, a section in `docs/rules.md`, and tests for
  both the firing and the non-firing case — false positives are what kill
  linters, so every rule needs a "stays quiet" test.
- **Nothing is ever executed.** cellvet must stay safe to run on untrusted
  notebooks: parsing and AST analysis only, no kernels, no `exec`.
- **Every public API needs an English docstring and a test.** Keep logic in
  pure, unit-testable modules; the CLI layer stays thin.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` share the same structure; update all three when you change
  one (English is the authoritative version).

## Reporting bugs

Please include `cellvet --version`, the smallest `.ipynb` that reproduces the
problem (strip outputs if they are private — cellvet never reads outputs),
and the finding you expected versus the one you got. False positives are
treated as bugs with the same priority as missed detections.

## Security

Please do not open public issues for security problems; use GitHub's private
vulnerability reporting on the repository instead.
