"""Tests for strict SQLGlot semantic snapshots."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.catalog import get_provider_spec
from sqlit.domains.query.app.query_analysis import (
    AliasKind,
    DefinitionKind,
    QueryAnalysisService,
    SemanticStatus,
    SyntaxRange,
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


@pytest.mark.parametrize(
    ("sql", "reference", "definition", "kind"),
    [
        (
            "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent",
            "recent.id",
            "recent",
            DefinitionKind.CTE,
        ),
        (
            "SELECT u.id FROM users AS u",
            "u.id",
            "AS u",
            DefinitionKind.RELATION_ALIAS,
        ),
        (
            "SELECT total AS amount FROM orders ORDER BY amount",
            "amount",
            "AS amount",
            DefinitionKind.PROJECTION_ALIAS,
        ),
    ],
)
def test_definition_at_links_semantic_references(
    sql: str,
    reference: str,
    definition: str,
    kind: DefinitionKind,
) -> None:
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )
    reference_offset = sql.rindex(reference)
    definition_name = definition.rsplit(" ", 1)[-1]
    definition_offset = sql.index(definition) + len(definition) - len(definition_name)

    snapshot = service.semantic_snapshot(sql)
    assert any(link.kind == kind for link in snapshot.definitions)
    assert service.definition_at(sql, Position(0, reference_offset)) == SyntaxRange(
        Position(0, definition_offset),
        Position(0, definition_offset + len(definition_name)),
        {
            DefinitionKind.CTE: "cte_name",
            DefinitionKind.RELATION_ALIAS: "relation_alias",
            DefinitionKind.PROJECTION_ALIAS: "projection_alias",
        }[kind],
    )
    references = service.references_at(sql, Position(0, definition_offset))
    assert references
    assert any(item.start <= Position(0, reference_offset) < item.end for item in references)


def test_relation_alias_lookup_honors_nested_scope_shadowing() -> None:
    sql = "SELECT u.id FROM users AS u WHERE EXISTS (SELECT u.id FROM orders AS u)"
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )

    inner_reference = sql.rindex("u.id")
    inner_definition = sql.rindex("AS u") + 3
    assert service.definition_at(sql, Position(0, inner_reference)) == SyntaxRange(
        Position(0, inner_definition),
        Position(0, inner_definition + 1),
        "relation_alias",
    )


def test_relation_alias_lookup_resolves_correlated_outer_reference() -> None:
    sql = "SELECT u.id FROM users AS u WHERE EXISTS (SELECT 1 FROM orders AS o WHERE o.user_id = u.id)"
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="postgres",
        semantic_backend=SQLGlotSemanticBackend(),
    )

    outer_reference = sql.rindex("u.id")
    outer_definition = sql.index("AS u") + 3
    assert service.definition_at(sql, Position(0, outer_reference)) == SyntaxRange(
        Position(0, outer_definition),
        Position(0, outer_definition + 1),
        "relation_alias",
    )


def test_definition_lookup_preserves_quoted_alias_ranges() -> None:
    sql = 'SELECT "u".id FROM users AS "u"'
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="postgres",
        semantic_backend=SQLGlotSemanticBackend(),
    )
    definition = sql.rindex('"u"')

    assert service.definition_at(sql, Position(0, sql.index('"u"'))) == SyntaxRange(
        Position(0, definition),
        Position(0, definition + 3),
        "relation_alias",
    )


def test_cte_definition_lookup_honors_nested_shadowing() -> None:
    sql = "WITH item AS (SELECT 1) SELECT * FROM (WITH item AS (SELECT 2) SELECT * FROM item)"
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )
    outer_definition = sql.index("item")
    inner_definition = sql.index("item", outer_definition + 1)

    assert service.definition_at(sql, Position(0, sql.rindex("item"))) == SyntaxRange(
        Position(0, inner_definition),
        Position(0, inner_definition + 4),
        "cte_name",
    )
    assert service.references_at(sql, Position(0, inner_definition)) == (
        SyntaxRange(
            Position(0, sql.rindex("item")),
            Position(0, sql.rindex("item") + 4),
            "cte_reference",
        ),
    )


def test_references_at_resolves_declaration_and_reference_to_same_group() -> None:
    sql = "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent ORDER BY recent.id"
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(sql, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )
    declaration = sql.index("recent")
    snapshot = service.semantic_snapshot(sql)
    expected = tuple(link.reference for link in snapshot.definitions if link.definition.start == Position(0, declaration))

    assert len(expected) == 3
    assert service.references_at(sql, Position(0, declaration)) == expected
    assert service.references_at(sql, expected[-1].start) == expected


def test_references_at_is_empty_when_semantics_are_unavailable() -> None:
    text = "SELECT id FROM users WHERE ("
    service = QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(text, language="sql")),
        dialect="sqlite",
        semantic_backend=SQLGlotSemanticBackend(),
    )

    assert service.references_at(text, Position(0, 7)) == ()


def test_resolved_table_indexes_survive_snapshot_source_sorting() -> None:
    snapshot = SQLGlotSemanticBackend().analyze(
        "SELECT derived.id FROM (SELECT id FROM users) AS derived",
        "sqlite",
    )

    column = next(item for item in snapshot.columns if item.source_alias == "derived")
    assert column.resolved_table is not None
    assert snapshot.tables[column.resolved_table].kind == TableReferenceKind.DERIVED
