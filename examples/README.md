# cellvet examples

Two versions of the same tiny revenue analysis:

- **`stale_state.ipynb`** — the notebook every team has shipped. Its saved
  outputs are real, but they were produced by a kernel that ran the cells in
  the order `In [1] ... In [6]`, not in the order the file shows them. A fresh
  *Restart & Run All* raises `NameError` at cell 1, and cell 4's saved total
  was computed with a tax rate the fresh run never sees.
- **`clean.ipynb`** — the same analysis, reordered so document order and
  execution order agree. cellvet reports nothing.

Run them from the repository root:

```bash
python -m cellvet check examples/stale_state.ipynb   # exit code 1, 3 errors
python -m cellvet check examples/clean.ipynb         # exit code 0
python -m cellvet order examples/stale_state.ipynb   # see the two orders side by side
```

The buggy notebook triggers one finding from almost every rule family —
`E101`/`E102`/`E103` (execution order), `N201`/`N202` (name flow), and
`H301` (order-dependent binding) — which makes it a handy fixture for
experimenting with `--select`, `--ignore`, and `--format json`.
