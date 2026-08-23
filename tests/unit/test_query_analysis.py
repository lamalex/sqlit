"""Tests for parser-neutral structural query analysis."""

from __future__ import annotations

from sqlit.domains.query.app.query_analysis import (
    QueryAnalysisService,
    QueryDiagnostic,
    SyntaxRange,
)
from sqlit.domains.query.editing import Position
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend
from sqlit.shared.ui.widgets_text_area import QueryTextArea


def _service(text: str, *, language: str | None = "sql") -> QueryAnalysisService:
    text_area = QueryTextArea(text, language=language)
    return QueryAnalysisService(TextualQueryAnalysisBackend(text_area))


def test_statement_at_returns_half_open_range_with_terminator() -> None:
    analysis = _service("SELECT a FROM t;\nUPDATE t SET a = 1;")

    assert analysis.statement_at(Position(0, 3)) == SyntaxRange(
        Position(0, 0), Position(0, 16), "statement"
    )
    assert analysis.statement_at(Position(1, 3)) == SyntaxRange(
        Position(1, 0), Position(1, 19), "statement"
    )


def test_node_and_parent_ranges_do_not_expose_parser_objects() -> None:
    analysis = _service("SELECT foo FROM bar;")

    node = analysis.node_at(Position(0, 8))
    assert node == SyntaxRange(Position(0, 7), Position(0, 10), "identifier")

    parent = analysis.parent_range(node)
    assert parent is not None
    assert parent.start <= node.start
    assert node.end <= parent.end
    assert (parent.start, parent.end) != (node.start, node.end)


def test_sibling_range_navigates_between_statements() -> None:
    analysis = _service("SELECT 1;\nSELECT 2;")
    first = analysis.statement_at(Position(0, 0))
    assert first is not None

    assert analysis.sibling_range(first, 1) == SyntaxRange(
        Position(1, 0), Position(1, 9), "statement"
    )
    assert analysis.sibling_range(first, 0) is first


def test_parent_range_clamps_virtual_document_end() -> None:
    analysis = _service("SELECT 1;\nSELECT 2;")
    statement = analysis.statement_at(Position(0, 0))
    assert statement is not None

    assert analysis.parent_range(statement) == SyntaxRange(
        Position(0, 0), Position(1, 9), "program"
    )


def test_ranges_use_editor_columns_for_utf8_text() -> None:
    analysis = _service("SELECT 'café';")

    statement = analysis.statement_at(Position(0, 10))
    assert statement == SyntaxRange(Position(0, 0), Position(0, 14), "statement")


def test_diagnostics_convert_error_nodes_to_application_values() -> None:
    diagnostics = _service("SELECT (").diagnostics()

    assert diagnostics
    assert all(isinstance(item, QueryDiagnostic) for item in diagnostics)
    assert all(item.range.kind in {"ERROR", "MISSING"} for item in diagnostics)


def test_analysis_degrades_when_syntax_support_is_unavailable() -> None:
    analysis = _service("SELECT 1", language=None)

    assert analysis.node_at(Position(0, 0)) is None
    assert analysis.statement_at(Position(0, 0)) is None
    assert analysis.diagnostics() == ()


def test_adapter_reads_the_current_tree_after_text_replacement() -> None:
    text_area = QueryTextArea("SELECT 1;", language="sql")
    analysis = QueryAnalysisService(TextualQueryAnalysisBackend(text_area))
    assert analysis.statement_at(Position(0, 0)) is not None

    text_area.text = "UPDATE widgets SET active = TRUE;"

    assert analysis.statement_at(Position(0, 0)) == SyntaxRange(
        Position(0, 0), Position(0, 33), "statement"
    )
