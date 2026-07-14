"""Parsing .ipynb JSON into the Notebook model."""

import pytest

from cellvet.notebook import NotebookError, parse_notebook

from conftest import code, make_notebook, markdown, nb_from


def test_code_cells_are_extracted_in_document_order():
    nb = nb_from(code("a = 1", 1), markdown(), code("b = 2", 2))
    assert [c.source for c in nb.cells] == ["a = 1", "b = 2"]
    assert [c.index for c in nb.cells] == [1, 2]


def test_markdown_cells_count_toward_doc_index_but_not_code_index():
    nb = nb_from(markdown(), code("x = 1", 1))
    assert nb.cells[0].index == 1
    assert nb.cells[0].doc_index == 1
    assert nb.total_cells == 2


def test_source_as_list_of_lines_is_joined():
    # nbformat stores source as a list of '\n'-terminated strings
    nb = parse_notebook(make_notebook({**code("", 1), "source": ["x = 1\n", "y = 2"]}))
    assert nb.cells[0].source == "x = 1\ny = 2"


def test_cell_labels_reflect_execution_state():
    nb = nb_from(code("x = 1"), code("y = 2", 7))
    assert nb.cells[0].execution_count is None
    assert nb.cells[0].label() == "cell 1 (never run)"
    assert nb.cells[1].label() == "cell 2 (In [7])"
    assert [c.index for c in nb.executed_cells] == [2]


def test_blank_and_comment_only_cells_are_blank():
    nb = nb_from(code("", 1), code("  \n\n", 2), code("# note\n  # later", 3), code("x = 1", 4))
    assert [c.is_blank for c in nb.cells] == [True, True, True, False]


def test_invalid_json_raises_notebook_error():
    with pytest.raises(NotebookError, match="not valid JSON"):
        parse_notebook("{not json")


def test_wrong_shape_notebooks_are_rejected():
    with pytest.raises(NotebookError, match="nbformat 3"):
        parse_notebook('{"nbformat": 3, "cells": []}')
    with pytest.raises(NotebookError, match="'cells'"):
        parse_notebook('{"nbformat": 4}')


def test_non_integer_execution_count_is_rejected():
    bad = make_notebook({**code("x = 1"), "execution_count": "7"})
    with pytest.raises(NotebookError, match="execution_count"):
        parse_notebook(bad)
