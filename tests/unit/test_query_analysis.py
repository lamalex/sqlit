"""Tests for parser-neutral structural query analysis."""

from __future__ import annotations

import pytest

from sqlit.domains.query.app.query_analysis import (
    QueryAnalysisService,
    QueryDiagnostic,
    SyntaxRange,
)
from sqlit.domains.query.editing import Position
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend
from sqlit.shared.ui.widgets_text_area import QueryTextArea

INCOMPLETE_JOIN_SQL = '''with cte as (SELECT *
FROM "orders"
LIMIT 100)
select *
from (
  select *
  from cte
)
left join on 1=1
where true or 1 and not false 
'''


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


def test_cte_definition_body_and_select_list_ranges() -> None:
    analysis = _service(
        "WITH recent AS (SELECT id, total FROM orders WHERE total > 10) "
        "SELECT recent.id FROM recent;"
    )

    assert analysis.cte_at(Position(0, 25)) == SyntaxRange(
        Position(0, 5), Position(0, 62), "cte"
    )
    assert analysis.cte_at(Position(0, 25), body=True) == SyntaxRange(
        Position(0, 16), Position(0, 61), "cte_body"
    )
    assert analysis.select_list_at(Position(0, 25)) == SyntaxRange(
        Position(0, 23), Position(0, 32), "select_list"
    )


def test_subquery_and_where_ranges() -> None:
    analysis = _service("SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);")

    assert analysis.subquery_at(Position(0, 43)) == SyntaxRange(
        Position(0, 32), Position(0, 60), "subquery"
    )
    assert analysis.clause_at(Position(0, 25)) == SyntaxRange(
        Position(0, 20), Position(0, 60), "where"
    )


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (42, SyntaxRange(Position(0, 34), Position(0, 67), "group_by")),
        (58, SyntaxRange(Position(0, 48), Position(0, 67), "having")),
    ],
)
def test_group_by_and_synthesized_having_ranges(
    column: int, expected: SyntaxRange
) -> None:
    analysis = _service(
        "SELECT team, COUNT(*) FROM scores GROUP BY team HAVING COUNT(*) > 2;"
    )

    assert analysis.clause_at(Position(0, column)) == expected


@pytest.mark.parametrize(
    ("sql", "column", "expected"),
    [
        (
            "SELECT a FROM t WHERE a > 1 ORDER BY a LIMIT 5;",
            33,
            SyntaxRange(Position(0, 28), Position(0, 38), "order_by"),
        ),
        (
            "SELECT a FROM t WHERE a > 1 ORDER BY a LIMIT 5;",
            44,
            SyntaxRange(Position(0, 39), Position(0, 46), "limit"),
        ),
        (
            "UPDATE t SET a = 1 WHERE id = 2 RETURNING id;",
            41,
            SyntaxRange(Position(0, 32), Position(0, 44), "returning"),
        ),
    ],
)
def test_order_limit_and_returning_clause_ranges(
    sql: str, column: int, expected: SyntaxRange
) -> None:
    assert _service(sql).clause_at(Position(0, column)) == expected


def test_join_condition_and_table_expression_ranges() -> None:
    join_analysis = _service("SELECT * FROM a JOIN b USING (id);")
    table_analysis = _service("SELECT * FROM schema.widgets AS w;")

    assert join_analysis.join_condition_at(Position(0, 30)) == SyntaxRange(
        Position(0, 29), Position(0, 33), "join_condition"
    )
    assert table_analysis.table_expression_at(Position(0, 23)) == SyntaxRange(
        Position(0, 14), Position(0, 33), "table_expression"
    )


def test_delete_table_expression_handles_direct_object_reference() -> None:
    analysis = _service("DELETE FROM widgets WHERE id = 1;")

    assert analysis.table_expression_at(Position(0, 15)) == SyntaxRange(
        Position(0, 12), Position(0, 19), "table_expression"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO events(name) SELECT name FROM pending RETURNING id;",
        "SELECT u.id FROM public.users u LEFT JOIN orders o ON o.user_id = u.id;",
        "SELECT IFNULL(u.name, 'n/a') FROM `users` u LIMIT 10;",
        "SELECT TOP 10 u.id FROM dbo.users u ORDER BY u.id;",
        "SELECT user_id, COUNT(*) FROM events GROUP BY user_id;",
        "SELECT ROW_NUMBER() OVER (ORDER BY created_at) FROM events;",
        "WITH active AS (SELECT id FROM users WHERE",
    ],
)
def test_semantic_analysis_degrades_gracefully_across_sql_styles(sql: str) -> None:
    analysis = _service(sql)
    position = Position(0, min(10, len(sql)))

    for selector in (
        analysis.cte_at,
        analysis.subquery_at,
        analysis.select_list_at,
        analysis.clause_at,
        analysis.join_condition_at,
        analysis.table_expression_at,
    ):
        result = selector(position)
        assert result is None or isinstance(result, SyntaxRange)
    assert isinstance(analysis.diagnostics(), tuple)


def test_incomplete_join_recovers_statement_condition_and_where_ranges() -> None:
    analysis = _service(INCOMPLETE_JOIN_SQL)

    assert analysis.statement_at(Position(8, 5)) == SyntaxRange(
        Position(0, 0), Position(9, 29), "statement"
    )
    assert analysis.join_condition_at(Position(8, 14)) == SyntaxRange(
        Position(8, 13), Position(8, 16), "join_condition"
    )
    assert analysis.clause_at(Position(9, 10)) == SyntaxRange(
        Position(9, 0), Position(9, 29), "where"
    )
    assert analysis.clause_at(Position(8, 14)) is None


def test_incomplete_join_table_recovery_avoids_misparsed_on_identifier() -> None:
    analysis = _service(INCOMPLETE_JOIN_SQL)

    assert analysis.table_expression_at(Position(4, 2)) == SyntaxRange(
        Position(4, 5), Position(7, 1), "table_expression"
    )
    assert analysis.table_expression_at(Position(8, 10)) is None


def test_recovery_does_not_classify_keywords_inside_valid_strings() -> None:
    analysis = _service("SELECT 'LEFT JOIN ON 1=1 WHERE false';")

    assert analysis.join_condition_at(Position(0, 20)) is None
    assert analysis.clause_at(Position(0, 28)) is None
