"""Dialect-style capability tests for structural query analysis."""

from __future__ import annotations

import time
from collections import Counter

import pytest

from sqlit.domains.query.app.query_analysis import QueryAnalysisService
from sqlit.domains.query.editing import Position, get_selection_text
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend
from sqlit.shared.ui.widgets_text_area import QueryTextArea


def _analysis(sql: str, dialect: str) -> QueryAnalysisService:
    return QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect=dialect,
    )


DIALECT_CASES = [
    pytest.param(
        "sqlite",
        "WITH recent AS (SELECT user_id, total FROM orders WHERE total > 10) "
        "SELECT r.user_id, COUNT(*) FROM recent r JOIN users u ON u.id = r.user_id "
        "GROUP BY r.user_id HAVING COUNT(*) > 1 ORDER BY r.user_id LIMIT 20;",
        {
            "statement": 1,
            "cte": 1,
            "cte_body": 1,
            "select_list": 2,
            "where": 1,
            "group_by": 1,
            "having": 1,
            "order_by": 1,
            "limit": 1,
            "join_condition": 1,
            "table_expression": 3,
        },
        id="sqlite",
    ),
    pytest.param(
        "postgresql",
        "WITH ranked AS (SELECT DISTINCT ON (user_id) user_id, total FROM orders "
        "ORDER BY user_id, created_at DESC) SELECT r.user_id FROM ranked r "
        "WHERE r.total > 10 ORDER BY r.user_id LIMIT 5;",
        {
            "statement": 1,
            "cte": 1,
            "cte_body": 1,
            "select_list": 2,
            "where": 1,
            "order_by": 2,
            "limit": 1,
            "table_expression": 2,
        },
        id="postgresql",
    ),
    pytest.param(
        "mysql",
        "SELECT u.id, COUNT(o.id) FROM `users` u LEFT JOIN `orders` o "
        "ON o.user_id <=> u.id WHERE u.active = 1 GROUP BY u.id "
        "HAVING COUNT(o.id) > 2 ORDER BY u.id LIMIT 10;",
        {
            "statement": 1,
            "select_list": 1,
            "where": 1,
            "group_by": 1,
            "having": 1,
            "order_by": 1,
            "limit": 1,
            "join_condition": 1,
            "table_expression": 2,
        },
        id="mysql",
    ),
    pytest.param(
        "mssql",
        "WITH ranked AS (SELECT TOP (10) id, ROW_NUMBER() OVER "
        "(ORDER BY created_at) AS rn FROM dbo.users) "
        "SELECT id FROM ranked WHERE rn = 1 ORDER BY id;",
        {
            "statement": 1,
            "cte": 1,
            "cte_body": 1,
            "select_list": 2,
            "where": 1,
            "order_by": 2,
            "table_expression": 2,
        },
        id="mssql",
    ),
    pytest.param(
        "bigquery",
        "WITH events AS (SELECT user_id, event_name FROM `proj.analytics.events` "
        "WHERE event_date > '2026-01-01') SELECT user_id, COUNT(*) FROM events "
        "GROUP BY user_id ORDER BY user_id LIMIT 100;",
        {
            "statement": 1,
            "cte": 1,
            "cte_body": 1,
            "select_list": 2,
            "group_by": 1,
            "order_by": 1,
            "limit": 1,
            "table_expression": 1,
        },
        id="bigquery",
    ),
    pytest.param(
        "snowflake",
        "WITH events AS (SELECT user_id, created_at FROM analytics.events "
        "WHERE created_at > CURRENT_DATE - 7) SELECT user_id, ROW_NUMBER() OVER "
        "(PARTITION BY user_id ORDER BY created_at) AS rn FROM events "
        "ORDER BY user_id LIMIT 100;",
        {
            "statement": 1,
            "cte": 1,
            "cte_body": 1,
            "select_list": 2,
            "where": 1,
            "order_by": 2,
            "limit": 1,
            "table_expression": 2,
        },
        id="snowflake",
    ),
]


@pytest.mark.parametrize(("dialect", "sql", "minimum_counts"), DIALECT_CASES)
def test_dialect_semantic_capability_matrix(
    dialect: str,
    sql: str,
    minimum_counts: dict[str, int],
) -> None:
    ranges = _analysis(sql, dialect).semantic_ranges(Position(0, 10))
    counts = Counter(value.kind for value in ranges)

    for kind, minimum in minimum_counts.items():
        assert counts[kind] >= minimum, f"{dialect} lost {kind}: {ranges}"
    assert all(value.start <= value.end for value in ranges)


@pytest.mark.parametrize(
    ("dialect", "sql"),
    [
        (
            "mssql",
            "MERGE dbo.target AS t USING dbo.source AS s ON t.id=s.id "
            "WHEN MATCHED THEN UPDATE SET t.x=s.x;",
        ),
        (
            "snowflake",
            "COPY INTO analytics.events FROM @stage/events FILE_FORMAT=(TYPE=PARQUET);",
        ),
    ],
)
def test_unsupported_statements_still_offer_statement_selection(
    dialect: str, sql: str
) -> None:
    ranges = _analysis(sql, dialect).semantic_ranges(Position(0, 5))

    assert [value.kind for value in ranges] == ["statement"]
    assert get_selection_text(
        sql,
        ranges[0].start.row,
        ranges[0].start.col,
        ranges[0].end.row,
        ranges[0].end.col,
    ) == sql


def test_insert_target_is_available_as_a_table_expression() -> None:
    sql = "INSERT INTO users(name) VALUES ('Ada') RETURNING id;"
    ranges = _analysis(sql, "sqlite").semantic_ranges(Position(0, 8))
    tables = [value for value in ranges if value.kind == "table_expression"]

    assert len(tables) == 1
    assert get_selection_text(
        sql,
        tables[0].start.row,
        tables[0].start.col,
        tables[0].end.row,
        tables[0].end.col,
    ) == "users"


def test_dangling_join_does_not_absorb_following_where_clause() -> None:
    sql = (
        "SELECT u.id FROM users u LEFT JOIN orders o "
        "ON o.user_id = WHERE u.status = 'active'"
    )
    ranges = _analysis(sql, "mysql").semantic_ranges(Position(0, 10))
    join = next(value for value in ranges if value.kind == "join_condition")
    where = next(value for value in ranges if value.kind == "where")

    assert get_selection_text(
        sql,
        join.start.row,
        join.start.col,
        join.end.row,
        join.end.col,
    ) == "o.user_id ="
    assert get_selection_text(
        sql,
        where.start.row,
        where.start.col,
        where.end.row,
        where.end.col,
    ) == "WHERE u.status = 'active'"


def test_truncated_backtick_table_expression_is_not_offered() -> None:
    sql = "SELECT * FROM `proj.analytics.events_*`;"
    ranges = _analysis(sql, "bigquery").semantic_ranges(Position(0, 8))

    assert all(value.kind != "table_expression" for value in ranges)


def test_large_statement_semantic_enumeration_stays_responsive() -> None:
    count = 300
    sql = (
        "SELECT\n"
        + ",\n".join(f"  t{i}.id" for i in range(count))
        + "\nFROM base t0\n"
        + "\n".join(
            f"LEFT JOIN table_{i} t{i} ON t{i}.id = t0.id"
            for i in range(1, count)
        )
        + ";"
    )
    analysis = _analysis(sql, "sqlite")

    started = time.perf_counter()
    ranges = analysis.semantic_ranges(Position(1, 3))
    elapsed = time.perf_counter() - started

    assert len(ranges) == count * 2 + 1
    assert elapsed < 0.5
