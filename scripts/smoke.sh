#!/usr/bin/env bash
# Smoke test for cellvet: run the real CLI end-to-end against the example
# notebooks and a freshly generated one. Self-contained: pure stdlib, no
# network, idempotent (works from a clean tree without installing).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies: running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/cellvet-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. --version agrees with the package version.
version_out="$("$PYTHON" -m cellvet --version)"
pkg_version="$("$PYTHON" -c 'import cellvet; print(cellvet.__version__)')"
[ "$version_out" = "cellvet $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

# 2. The clean example passes with exit code 0.
clean_out="$("$PYTHON" -m cellvet check "$ROOT/examples/clean.ipynb")" \
  || fail "clean.ipynb should exit 0"
echo "$clean_out" | grep -q "no hidden-state issues" || fail "clean summary missing"

# 3. The stale-state example fails with exit code 1 and names the bugs.
set +e
stale_out="$("$PYTHON" -m cellvet check "$ROOT/examples/stale_state.ipynb")"
stale_rc=$?
set -e
echo "$stale_out" | sed 's/^/[check] /'
[ "$stale_rc" -eq 1 ] || fail "stale_state.ipynb should exit 1, got $stale_rc"
echo "$stale_out" | grep -q "N202 defined-after-use" || fail "N202 not reported"
echo "$stale_out" | grep -q "worked in your session only because" \
  || fail "kernel-order explanation missing"
echo "$stale_out" | grep -q "H301 order-dependent-binding" || fail "H301 not reported"
echo "$stale_out" | grep -q "E101 out-of-order-execution" || fail "E101 not reported"

# 4. JSON output parses and carries the same findings.
json_out="$("$PYTHON" -m cellvet check --format json "$ROOT/examples/stale_state.ipynb" || true)"
echo "$json_out" | "$PYTHON" -m json.tool >/dev/null || fail "JSON output does not parse"
echo "$json_out" | grep -q '"rule": "N202"' || fail "JSON missing N202 finding"
echo "$json_out" | grep -q '"notebooks_checked": 1' || fail "JSON missing notebook count"

# 5. Rule selection flips the exit code: E-family findings are warnings only.
"$PYTHON" -m cellvet check --select E "$ROOT/examples/stale_state.ipynb" >/dev/null \
  || fail "check --select E should exit 0 (warnings only)"

# 6. `order` shows that execution order differs from document order.
order_out="$("$PYTHON" -m cellvet order "$ROOT/examples/stale_state.ipynb")"
echo "$order_out" | sed 's/^/[order] /'
echo "$order_out" | grep -q "execution order differs from document order" \
  || fail "order did not detect the mismatch"

# 7. `rules` lists the full registry.
rules_out="$("$PYTHON" -m cellvet rules)"
for rule in E101 E102 E103 E104 N201 N202 N203 H301 P001 W401; do
  echo "$rules_out" | grep -q "^$rule" || fail "rules missing $rule"
done

# 8. Directory discovery: fix the notebook, re-check, and go green.
mkdir -p "$WORKDIR/project/.ipynb_checkpoints"
cp "$ROOT/examples/clean.ipynb" "$WORKDIR/project/analysis.ipynb"
cp "$ROOT/examples/stale_state.ipynb" \
   "$WORKDIR/project/.ipynb_checkpoints/analysis-checkpoint.ipynb"
dir_out="$("$PYTHON" -m cellvet check "$WORKDIR/project")" \
  || fail "directory with only a clean notebook should exit 0 (checkpoints skipped)"
echo "$dir_out" | grep -q "no hidden-state issues in 1 notebook" \
  || fail "checkpoint directory was not skipped"

echo "SMOKE OK"
