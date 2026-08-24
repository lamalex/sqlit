"""Tests for strict SQLGlot semantic snapshots."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.catalog import get_provider_spec
from sqlit.domains.query.app.query_analysis import (
    AliasKind,
    QueryAnalysisService,
    SemanticStatus,
    TableReferenceKind,
)
from sqlit.domains.query.app.sqlglot_analysis import SQLGlotSemanticBackend
from sqlit.domains.query.editing import Position
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend
from sqlit.shared.ui.widgets_text_area import QueryTextArea


@pytest.mark.parametrize(
    ("db_type", "expected"),
    [
        ("sqlite", "sqlite"),
        ("postgresql", "postgres"),
        ("mysql", "mysql"),
        ("mssql", "tsql"),
        ("bigquery", "bigquery"),
        ("snowflake", "snowflake"),
    ],
)
def test_provider_specs_declare_semantic_dialects(db_type: str, expected: str) -> None:
    assert get_provider_spec(db_type).analysis_dialect == expected


@pytest.mark.parametrize(
    ("dialect", "sql", "parts", "quoted"),
    [
        ("sqlite", "SELECT u.id FROM main.users AS u", ("main", "users"), (False, False)),
        (
            "postgres",
            'SELECT o.id FROM "analytics"."orders" AS o',
            ("analytics", "orders"),
            (True, True),
        ),
        (
            "mysql",
            "SELECT o.id FROM `shop`.`orders` AS o",
            ("shop", "orders"),
            (True, True),
        ),
        (
            "tsql",
            "SELECT o.id FROM [server].[db].[dbo].[orders] AS o",
            ("server", "db", "dbo", "orders"),
            (True, True, True, True),
        ),
        (
            "bigquery",
            "SELECT o.id FROM `project.dataset.orders` AS o",
            ("project", "dataset", "orders"),
            (True, True, True),
        ),
        (
            "snowflake",
            'SELECT o.id FROM "DB"."PUBLIC"."ORDERS" AS o',
            ("DB", "PUBLIC", "ORDERS"),
            (True, True, True),
        ),
    ],
)
def test_qualified_table_names_across_dialects(
    dialect: str,
    sql: str,
    parts: tuple[str, ...],
    quoted: tuple[bool, ...],
) -> None:
    snapshot = SQLGlotSemanticBackend().analyze(sql, dialect)

    assert snapshot.status == SemanticStatus.EXACT
    assert len(snapshot.tables) == 1
    assert snapshot.tables[0].name.parts == parts
    assert snapshot.tables[0].name.quoted == quoted
    assert snapshot.tables[0].alias in {"o", "u"}


def test_snapshot_links_cte_references_and_resolves_qualified_columns() -> None:
    sql = "WITH recent AS (SELECT user_id, total FROM orders) SELECT r.user_id, u.name AS customer FROM recent r JOIN users u ON u.id = r.user_id"
    snapshot = SQLGlotSemanticBackend().analyze(sql, "postgres")

    assert snapshot.status == SemanticStatus.EXACT
    assert len(snapshot.ctes) == 1
    cte_reference = next(table for table in snapshot.tables if table.kind == TableReferenceKind.CTE)
    assert cte_reference.name.parts == ("recent",)
    assert cte_reference.cte_id == snapshot.ctes[0].id

    relation_aliases = {alias.name for alias in snapshot.aliases if alias.kind == AliasKind.RELATION}
    projection_aliases = {alias.name for alias in snapshot.aliases if alias.kind == AliasKind.PROJECTION}
    assert relation_aliases == {"r", "u"}
    assert projection_aliases == {"customer"}

    qualified_columns = [column for column in snapshot.columns if column.source_alias]
    assert qualified_columns
    assert all(column.resolved_table is not None for column in qualified_columns)
    assert all(column.range is not None for column in snapshot.columns)


def test_strict_parse_failure_returns_no_best_effort_entities() -> None:
    snapshot = SQLGlotSemanticBackend().analyze(
        "SELECT a FROM users WHERE (",
        "sqlite",
    )

    assert snapshot.status == SemanticStatus.UNAVAILABLE
    assert snapshot.tables == ()
    assert snapshot.columns == ()
    assert snapshot.ctes == ()
    assert snapshot.diagnostics


def test_semantic_failure_does_not_disable_tree_sitter_analysis() -> None:
    text = "SELECT a FROM users WHERE ("
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(text, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )

    assert service.semantic_snapshot(text).status == SemanticStatus.UNAVAILABLE
    assert service.statement_at(Position(0, 3)) is not None


def test_service_without_semantic_dialect_is_explicitly_unavailable() -> None:
    text = "SELECT 1"
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(text, language="sql")),
        semantic_backend=SQLGlotSemanticBackend(),
    )

    snapshot = service.semantic_snapshot(text)
    assert snapshot.status == SemanticStatus.UNAVAILABLE
    assert snapshot.dialect is None


def test_unknown_semantic_dialect_degrades_without_raising() -> None:
    snapshot = SQLGlotSemanticBackend().analyze("SELECT 1", "not-real")

    assert snapshot.status == SemanticStatus.UNAVAILABLE
    assert snapshot.diagnostics


def test_multiple_statements_retain_statement_identity() -> None:
    snapshot = SQLGlotSemanticBackend().analyze(
        "SELECT id FROM first_table; SELECT id FROM second_table;",
        "sqlite",
    )

    assert snapshot.status == SemanticStatus.EXACT
    assert [(table.statement, table.name.parts) for table in snapshot.tables] == [
        (0, ("first_table",)),
        (1, ("second_table",)),
    ]


def test_derived_table_alias_has_consistent_qualified_name_metadata() -> None:
    snapshot = SQLGlotSemanticBackend().analyze(
        "SELECT derived.id FROM (SELECT id FROM users) AS derived",
        "sqlite",
    )

    derived = next(table for table in snapshot.tables if table.kind == TableReferenceKind.DERIVED)
    assert derived.name.parts == ("derived",)
    assert derived.name.quoted == (False,)
