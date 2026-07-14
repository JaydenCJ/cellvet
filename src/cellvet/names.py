"""Per-cell name extraction: what a cell defines, uses, and deletes.

This module turns one cell's Python AST into four ordered fact lists:

- ``defines``    — names the cell binds at the top level (module scope);
- ``immediate_uses`` — names the cell reads *while it executes* (module
  and class bodies, decorators, defaults, comprehension iterables) before
  the cell itself has bound them;
- ``deferred_uses``  — free names inside function and lambda bodies,
  which only need to exist by the time the function is *called*;
- ``deletes``    — names removed from module scope with ``del``.

Scoping follows Python's real rules closely enough for notebooks:
function locals are pre-scanned (so a later assignment makes a name local
to the function, not a notebook dependency), comprehensions get their own
scope but leak walrus targets, class bodies read the enclosing scope
immediately, and ``global`` declarations route bindings back to module
scope.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

#: Names that exist in every IPython kernel session but not in ``builtins``.
NOTEBOOK_BUILTINS = frozenset(
    {"display", "get_ipython", "In", "Out", "exit", "quit", "_", "__", "___", "_ih", "_oh", "_dh"}
)

_BUILTIN_NAMES = frozenset(dir(builtins)) | NOTEBOOK_BUILTINS


def is_builtin(name: str) -> bool:
    """True for names available in a fresh kernel without any imports."""
    return name in _BUILTIN_NAMES


@dataclass(frozen=True)
class NameEvent:
    """One occurrence of a name at a 1-based line inside the cell."""

    name: str
    line: int


@dataclass
class CellNames:
    """Everything cellvet knows about one cell's names."""

    defines: List[NameEvent] = field(default_factory=list)
    immediate_uses: List[NameEvent] = field(default_factory=list)
    deferred_uses: List[NameEvent] = field(default_factory=list)
    deletes: List[NameEvent] = field(default_factory=list)
    star_import_line: Optional[int] = None
    syntax_error: Optional[str] = None


class _Scope:
    __slots__ = ("kind", "parent", "bound", "globals")

    def __init__(self, kind: str, parent: Optional["_Scope"]) -> None:
        self.kind = kind  # "module" | "function" | "class" | "comprehension"
        self.parent = parent
        self.bound: Set[str] = set()
        self.globals: Set[str] = set()


def _target_names(target: ast.expr) -> List[Tuple[str, int]]:
    """Plain names bound by an assignment target (tuples/lists unpacked).

    Attribute and subscript targets (``obj.x = 1``, ``d[k] = v``) bind
    nothing new — their base object shows up as a Load use instead.
    """
    if isinstance(target, ast.Name):
        return [(target.id, target.lineno)]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: List[Tuple[str, int]] = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _function_locals(node: ast.AST) -> Tuple[Set[str], Set[str]]:
    """Pre-scan a function body: (locally bound names, global-declared names).

    Mirrors CPython's symbol table pass: any assignment anywhere in the
    body makes the name function-local, unless declared ``global`` or
    ``nonlocal``. Nested functions/classes bind their own name here but
    keep their internals to themselves; comprehension targets do not leak.
    """
    bound: Set[str] = set()
    declared: Set[str] = set()

    def scan(stmts: List[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.Global, ast.Nonlocal)):
                declared.update(stmt.names)
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(stmt.name)
                continue  # inner scope keeps its own locals
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    bound.add(alias.asname or alias.name.split(".")[0])
                continue
            for child in ast.iter_child_nodes(stmt):
                collect_expr(child)

    def collect_expr(node2: ast.AST) -> None:
        if isinstance(node2, ast.Name) and isinstance(node2.ctx, ast.Store):
            bound.add(node2.id)
        if isinstance(node2, ast.NamedExpr):
            if isinstance(node2.target, ast.Name):
                bound.add(node2.target.id)
        if isinstance(node2, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node2.name)
            return
        if isinstance(node2, ast.Lambda):
            return
        if isinstance(node2, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            # comprehension targets live in their own scope; walrus inside
            # still leaks, which the recursive walk below picks up
            for gen in node2.generators:
                collect_expr(gen.iter)
                for cond in gen.ifs:
                    collect_expr(cond)
            return
        if isinstance(node2, (ast.Global, ast.Nonlocal)):
            declared.update(node2.names)
            return
        if isinstance(node2, ast.ExceptHandler) and node2.name:
            bound.add(node2.name)
        if isinstance(node2, (ast.Import, ast.ImportFrom)):
            for alias in node2.names:
                if alias.name == "*":
                    continue
                bound.add(alias.asname or alias.name.split(".")[0])
            return
        for child in ast.iter_child_nodes(node2):
            collect_expr(child)

    body = getattr(node, "body", [])
    if isinstance(body, list):
        scan(body)
    return bound - declared, declared


class _Extractor:
    """Walks a cell's AST, classifying every name occurrence."""

    def __init__(self) -> None:
        self.result = CellNames()
        self._seen_immediate: Set[Tuple[str, int]] = set()
        self._seen_deferred: Set[str] = set()

    # -- recording ---------------------------------------------------------

    def _record_use(self, name: str, line: int, deferred: bool) -> None:
        if deferred:
            if name not in self._seen_deferred:
                self._seen_deferred.add(name)
                self.result.deferred_uses.append(NameEvent(name, line))
        else:
            key = (name, line)
            if key not in self._seen_immediate:
                self._seen_immediate.add(key)
                self.result.immediate_uses.append(NameEvent(name, line))

    def _bind(self, scope: _Scope, name: str, line: int) -> None:
        if name in scope.globals:
            self.result.defines.append(NameEvent(name, line))
            return
        scope.bound.add(name)
        if scope.kind == "module":
            self.result.defines.append(NameEvent(name, line))

    def _resolvable(self, scope: _Scope, name: str) -> bool:
        """Is ``name`` bound somewhere in the scope chain (cell-locally)?"""
        current: Optional[_Scope] = scope
        while current is not None:
            if current.kind == "class" and current is not scope:
                current = current.parent  # class scopes are invisible to children
                continue
            if name in current.bound and name not in current.globals:
                return True
            current = current.parent
        return False

    # -- statements --------------------------------------------------------

    def run(self, tree: ast.Module) -> CellNames:
        module = _Scope("module", None)
        self._stmts(tree.body, module, deferred=False)
        return self.result

    def _stmts(self, stmts: List[ast.stmt], scope: _Scope, deferred: bool) -> None:
        for stmt in stmts:
            self._stmt(stmt, scope, deferred)

    def _stmt(self, stmt: ast.stmt, scope: _Scope, deferred: bool) -> None:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function(stmt, scope, deferred)
        elif isinstance(stmt, ast.ClassDef):
            self._class(stmt, scope, deferred)
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            self._import(stmt, scope)
        elif isinstance(stmt, ast.Global):
            scope.globals.update(stmt.names)
        elif isinstance(stmt, ast.Nonlocal):
            pass
        elif isinstance(stmt, ast.Assign):
            self._expr(stmt.value, scope, deferred)
            for target in stmt.targets:
                self._store_target(target, scope, deferred)
        elif isinstance(stmt, ast.AnnAssign):
            self._expr(stmt.annotation, scope, deferred)
            if stmt.value is not None:
                self._expr(stmt.value, scope, deferred)
                self._store_target(stmt.target, scope, deferred)
        elif isinstance(stmt, ast.AugAssign):
            # `x += 1` both reads and rebinds x
            if isinstance(stmt.target, ast.Name):
                if not self._resolvable(scope, stmt.target.id):
                    self._record_use(stmt.target.id, stmt.target.lineno, deferred)
            else:
                self._expr_children(stmt.target, scope, deferred)
            self._expr(stmt.value, scope, deferred)
            self._store_target(stmt.target, scope, deferred)
        elif isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    scope.bound.discard(target.id)
                    if scope.kind == "module":
                        self.result.deletes.append(NameEvent(target.id, target.lineno))
                else:
                    self._expr(target, scope, deferred)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            self._expr(stmt.iter, scope, deferred)
            self._store_target(stmt.target, scope, deferred)
            self._stmts(stmt.body, scope, deferred)
            self._stmts(stmt.orelse, scope, deferred)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                self._expr(item.context_expr, scope, deferred)
                if item.optional_vars is not None:
                    self._store_target(item.optional_vars, scope, deferred)
            self._stmts(stmt.body, scope, deferred)
        elif isinstance(stmt, ast.Try):
            self._stmts(stmt.body, scope, deferred)
            for handler in stmt.handlers:
                if handler.type is not None:
                    self._expr(handler.type, scope, deferred)
                if handler.name:
                    self._bind(scope, handler.name, handler.lineno)
                self._stmts(handler.body, scope, deferred)
            self._stmts(stmt.orelse, scope, deferred)
            self._stmts(stmt.finalbody, scope, deferred)
        elif isinstance(stmt, (ast.If, ast.While)):
            self._expr(stmt.test, scope, deferred)
            self._stmts(stmt.body, scope, deferred)
            self._stmts(stmt.orelse, scope, deferred)
        elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
            self._expr(stmt.subject, scope, deferred)
            for case in stmt.cases:
                self._pattern(case.pattern, scope)
                if case.guard is not None:
                    self._expr(case.guard, scope, deferred)
                self._stmts(case.body, scope, deferred)
        else:
            # Expr, Return, Raise, Assert, Pass, Break, Continue, ...
            for child in ast.iter_child_nodes(stmt):
                if isinstance(child, ast.expr):
                    self._expr(child, scope, deferred)
                elif isinstance(child, ast.stmt):
                    self._stmt(child, scope, deferred)

    def _pattern(self, pattern: ast.AST, scope: _Scope) -> None:
        """match-case capture patterns bind names in the enclosing scope."""
        name = getattr(pattern, "name", None)
        if isinstance(name, str):
            self._bind(scope, name, pattern.lineno)
        for child in ast.iter_child_nodes(pattern):
            if isinstance(child, ast.expr):
                self._expr(child, scope, deferred=False)
            else:
                self._pattern(child, scope)

    def _import(self, stmt: ast.stmt, scope: _Scope) -> None:
        assert isinstance(stmt, (ast.Import, ast.ImportFrom))
        for alias in stmt.names:
            if alias.name == "*":
                if self.result.star_import_line is None:
                    self.result.star_import_line = stmt.lineno
                continue
            bound = alias.asname or alias.name.split(".")[0]
            self._bind(scope, bound, stmt.lineno)

    def _function(self, node: ast.AST, scope: _Scope, deferred: bool) -> None:
        # Decorators, defaults and annotations evaluate when `def` runs.
        for deco in getattr(node, "decorator_list", []):
            self._expr(deco, scope, deferred)
        args = node.args  # type: ignore[attr-defined]
        for default in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
            self._expr(default, scope, deferred)
        for arg in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            + ([args.vararg] if args.vararg else [])
            + ([args.kwarg] if args.kwarg else [])
        ):
            if arg.annotation is not None:
                self._expr(arg.annotation, scope, deferred)
        returns = getattr(node, "returns", None)
        if returns is not None:
            self._expr(returns, scope, deferred)

        self._bind(scope, node.name, node.lineno)  # type: ignore[attr-defined]

        inner = _Scope("function", scope)
        local_names, declared_globals = _function_locals(node)
        inner.bound.update(local_names)
        inner.globals.update(declared_globals)
        for arg in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            + ([args.vararg] if args.vararg else [])
            + ([args.kwarg] if args.kwarg else [])
        ):
            inner.bound.add(arg.arg)
        # The body only runs when the function is called: deferred=True.
        self._stmts(node.body, inner, deferred=True)  # type: ignore[attr-defined]

    def _class(self, node: ast.ClassDef, scope: _Scope, deferred: bool) -> None:
        for deco in node.decorator_list:
            self._expr(deco, scope, deferred)
        for base in node.bases:
            self._expr(base, scope, deferred)
        for kw in node.keywords:
            self._expr(kw.value, scope, deferred)
        self._bind(scope, node.name, node.lineno)
        inner = _Scope("class", scope)
        # Class bodies execute immediately, in definition order.
        self._stmts(node.body, inner, deferred=deferred)

    def _store_target(self, target: ast.expr, scope: _Scope, deferred: bool) -> None:
        if isinstance(target, ast.Name):
            self._bind(scope, target.id, target.lineno)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._store_target(elt, scope, deferred)
        elif isinstance(target, ast.Starred):
            self._store_target(target.value, scope, deferred)
        else:
            # obj.attr = v / d[k] = v: reads the base object
            self._expr_children(target, scope, deferred)

    # -- expressions -------------------------------------------------------

    def _expr(self, node: ast.expr, scope: _Scope, deferred: bool) -> None:
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                if not self._resolvable(scope, node.id):
                    self._record_use(node.id, node.lineno, deferred)
            return
        if isinstance(node, ast.NamedExpr):
            self._expr(node.value, scope, deferred)
            # walrus binds in the nearest function/module scope
            target_scope = scope
            while target_scope.kind == "comprehension" and target_scope.parent:
                target_scope = target_scope.parent
            if isinstance(node.target, ast.Name):
                self._bind(target_scope, node.target.id, node.target.lineno)
            return
        if isinstance(node, ast.Lambda):
            for default in list(node.args.defaults) + [
                d for d in node.args.kw_defaults if d is not None
            ]:
                self._expr(default, scope, deferred)
            inner = _Scope("function", scope)
            for arg in (
                list(node.args.posonlyargs) + list(node.args.args)
                + list(node.args.kwonlyargs)
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            ):
                inner.bound.add(arg.arg)
            self._expr(node.body, inner, deferred=True)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            inner = _Scope("comprehension", scope)
            first = True
            for gen in node.generators:
                # the first iterable evaluates in the enclosing scope
                self._expr(gen.iter, scope if first else inner, deferred)
                first = False
                self._store_target(gen.target, inner, deferred)
                for cond in gen.ifs:
                    self._expr(cond, inner, deferred)
            if isinstance(node, ast.DictComp):
                self._expr(node.key, inner, deferred)
                self._expr(node.value, inner, deferred)
            else:
                self._expr(node.elt, inner, deferred)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expr(child, scope, deferred)

    def _expr_children(self, node: ast.expr, scope: _Scope, deferred: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expr(child, scope, deferred)


def extract_names(python_source: str) -> CellNames:
    """Extract name facts from (already magic-rewritten) Python source.

    A cell that fails to parse yields a :class:`CellNames` whose
    ``syntax_error`` is set; callers surface that as its own finding
    instead of silently skipping the cell.
    """
    try:
        tree = ast.parse(python_source)
    except SyntaxError as exc:
        bad = CellNames()
        bad.syntax_error = f"{exc.msg} (line {exc.lineno})"
        return bad
    return _Extractor().run(tree)
