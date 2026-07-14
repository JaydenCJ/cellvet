"""Shared fixtures: tiny builders for in-memory and on-disk notebooks.

``code(...)`` builds one code cell dict; ``make_notebook(...)`` wraps
cells into valid nbformat-4 JSON. Everything is deterministic and offline.
"""

import json

import pytest

from cellvet.notebook import parse_notebook


def code(source, count=None):
    """A code-cell dict. ``source`` is a string; ``count`` is In [n] or None."""
    return {
        "cell_type": "code",
        "metadata": {},
        "outputs": [],
        "execution_count": count,
        "source": source,
    }


def markdown(source="# notes"):
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def make_notebook(*cells):
    """nbformat-4 notebook JSON text containing the given cell dicts."""
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "language": "python"}},
            "cells": list(cells),
        }
    )


def nb_from(*cells, path="memory.ipynb"):
    """Parse cell dicts straight into a Notebook object."""
    return parse_notebook(make_notebook(*cells), path=path)


@pytest.fixture
def write_notebook(tmp_path):
    """Write cells to ``<tmp>/<name>.ipynb`` and return the path as str."""

    def _write(*cells, name="nb"):
        path = tmp_path / f"{name}.ipynb"
        path.write_text(make_notebook(*cells), encoding="utf-8")
        return str(path)

    return _write
