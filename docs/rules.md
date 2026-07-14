# cellvet rules

Rule IDs are stable across releases. Select or suppress them with
`--select` / `--ignore`, using full IDs (`N201`) or family prefixes (`E`, `N2`).

Severities: **error** means a fresh top-to-bottom run raises `NameError`;
**warning** means the notebook's recorded results depend on state a fresh run
will not recreate; **info** is context that helps you judge the rest.

## E1xx — execution-order checks (metadata only)

These read only execution counts, so they work even on cells cellvet
cannot parse.

### E101 `out-of-order-execution` (warning)

An executed cell has a lower `In [n]` than a cell above it. The document
order shown to the reader was never executed as a whole; any correctness the
notebook appears to demonstrate is untested in that order.

```text
cell 2 (In [2]) ran before cell 1 (In [4]) but appears after it
```

Fix: *Kernel → Restart & Run All*, then save.

### E102 `never-executed-cell` (warning)

A non-empty code cell has no execution count while other cells do. Its saved
outputs (none) tell you nothing, and it may fail on the first real run.
Notebooks where *no* cell ran (freshly stripped or exported) are not flagged —
there is no execution story to distrust.

### E103 `execution-count-gap` (info)

Counts jump, e.g. `In [1]` then `In [5]`. The kernel executed code that is no
longer visible — cells re-run, edited, or deleted after running. State those
missing runs created may be what the surviving cells silently rely on.
Reported once per notebook.

### E104 `duplicate-execution-count` (warning)

Two cells share the same `In [n]`. One kernel session never reuses a count,
so the notebook mixes cells from different sessions (usually copy-paste
between notebooks). Their combined behavior has never been executed at all.

## N2xx — name-flow errors (fresh run breaks)

cellvet replays the notebook top to bottom without executing it, tracking
which cell binds each name. Function and lambda bodies are *deferred*: their
free names only need to exist somewhere in the notebook by call time.

### N201 `undefined-name` (error)

A name is read but no cell in the notebook ever binds it. The value existed
only in a dead kernel session (a deleted cell, a scratch console, a previous
notebook). This is the bug that ships: the notebook cannot run anywhere.

### N202 `defined-after-use` (error)

A name is read in a cell above the cell that defines it. A fresh run raises
`NameError`; the notebook only worked because the defining cell was executed
first. When execution counts prove that, the message says so:

```text
'data' is used here but only defined in cell 2 (In [2]), which comes later
in the notebook; it worked in your session only because cell 2 (In [2]) had
already run
```

Fix: move the defining cell above its first use.

### N203 `use-after-delete` (error)

A name is read after a `del` removed it, with no redefinition in between.
The read only worked against a kernel where the `del` had not (yet) run.

## H3xx — hidden-state hazards (runs, but may not reproduce)

### H301 `order-dependent-binding` (warning)

A name resolves fine in both orders — but to **different defining cells**.
Reconstructed from execution counts: when the cell actually ran, the name was
bound by a cell other than the one a fresh run will use, so the saved output
was produced from a value the fresh run never sees.

```python
# cell 1, In [1]:   rate = 0.1
# cell 2, In [5]:   price = 100 * (1 + rate)   # actually saw cell 3's 0.25
# cell 3, In [3]:   rate = 0.25
```

## P0xx / W4xx — analysis confidence

### P001 `unparsable-cell` (warning)

The cell is not valid Python even after IPython magic rewriting. Name
analysis skipped it, so name findings around it may be incomplete — and a
fresh run of the notebook will fail at this cell anyway.

### W401 `star-import` (info)

`from module import *` binds names cellvet cannot enumerate statically.
From that point on (document order, and from the star's own line inside its
cell), `undefined-name` checks are suppressed rather than risk false
positives. Replace the star with explicit imports to restore full checking.

## What cellvet deliberately does not flag

- **Attribute mutation across cells** (`df.col = ...`) — tracked as a use of
  the base object, not a rebinding; object identity is out of static reach.
- **`globals()` / `exec` / `eval` tricks** — dynamic by definition.
- **Functions that assign via `global`** — the binding happens at call time;
  cellvet treats the read side (a `global` read is still a notebook
  dependency) but does not credit the write.
- **Style** — line length, imports at the top, output size. Formatters and
  linters already do that; cellvet only cares about state.
