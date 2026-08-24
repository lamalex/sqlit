"""Tests for semantic SQL rename planning."""

from __future__ import annotations

import pytest

from sqlit.domains.query.app.query_analysis import (
    DefinitionKind,
    QueryAnalysisService,
)
from sqlit.domains.query.app.query_rename import (
    RenameError,
    build_rename_plan,
    offset_to_position,
    syntax_range_to_span,
)
from sqlit.domains.query.app.sqlglot_analysis import SQLGlotSemanticBackend
from sqlit.domains.query.editing import Position
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend
from sqlit.shared.ui.widgets_text_area import QueryTextArea


def _service(text: str, dialect: str = "sqlite") -> QueryAnalysisService:
    return QueryAnalysisService(
        TextualQueryAnalysisBackend(QueryTextArea(text, language="sql")),
        dialect=dialect,
        semantic_backend=SQLGlotSemanticBackend(),
    )


def test_plan_renames_only_the_linked_shadow_scope() -> None:
    sql = "WITH item AS (SELECT id FROM products) SELECT item.id FROM item WHERE EXISTS (WITH item AS (SELECT id FROM archived) SELECT item.id FROM item)"
    service = _service(sql)
    symbol = service.symbol_at(sql, Position(0, sql.index("item")))
    assert symbol is not None

    plan = build_rename_plan(sql, symbol, "current_item")

    assert plan.occurrence_count == 3
    assert plan.text.count("current_item") == 3
    assert "WITH item AS (SELECT id FROM archived) SELECT item.id FROM item" in plan.text
    renamed = service.symbol_at(
        plan.text,
        offset_to_position(plan.text, plan.declaration.start),
    )
    assert renamed is not None
    assert renamed.name == "current_item"
    assert tuple(syntax_range_to_span(plan.text, value) for value in renamed.references) == plan.references


@pytest.mark.parametrize(
    ("dialect", "sql", "new_name", "expected"),
    [
        (
            "postgres",
            'SELECT "u".id FROM users AS "u"',
            'new"name',
            'SELECT "new""name".id FROM users AS "new""name"',
        ),
        (
            "mysql",
            "SELECT `u`.id FROM users AS `u`",
            "new`name",
            "SELECT `new``name`.id FROM users AS `new``name`",
        ),
        (
            "tsql",
            "SELECT [u].id FROM users AS [u]",
            "new]name",
            "SELECT [new]]name].id FROM users AS [new]]name]",
        ),
    ],
)
def test_plan_preserves_and_escapes_identifier_quoting(
    dialect: str,
    sql: str,
    new_name: str,
    expected: str,
) -> None:
    service = _service(sql, dialect)
    symbol = service.symbol_at(sql, Position(0, sql.rindex("u")))
    assert symbol is not None

    plan = build_rename_plan(sql, symbol, new_name)
    assert plan.text == expected
    renamed = service.symbol_at(
        plan.text,
        offset_to_position(plan.text, plan.declaration.start),
    )
    assert renamed is not None
    assert renamed.name == new_name


def test_plan_rejects_invalid_or_unchanged_bare_names() -> None:
    sql = "SELECT u.id FROM users AS u"
    symbol = _service(sql).symbol_at(sql, Position(0, sql.rindex("u")))
    assert symbol is not None

    with pytest.raises(RenameError, match="Unquoted"):
        build_rename_plan(sql, symbol, "not valid")
    with pytest.raises(RenameError, match="already"):
        build_rename_plan(sql, symbol, "u")


@pytest.mark.parametrize(
    ("sql", "name", "kind"),
    [
        (
            "WITH unused AS (SELECT 1) SELECT 1",
            "unused",
            DefinitionKind.CTE,
        ),
        (
            "SELECT 1 FROM users AS unused",
            "unused",
            DefinitionKind.RELATION_ALIAS,
        ),
        (
            "SELECT id AS unused FROM users",
            "unused",
            DefinitionKind.PROJECTION_ALIAS,
        ),
    ],
)
def test_symbol_at_finds_unused_declarations(
    sql: str,
    name: str,
    kind: DefinitionKind,
) -> None:
    symbol = _service(sql).symbol_at(sql, Position(0, sql.index(name)))

    assert symbol is not None
    assert symbol.kind == kind
    assert symbol.references == ()
    assert build_rename_plan(sql, symbol, "renamed").text.count("renamed") == 1


def test_candidate_projection_alias_collision_is_detected() -> None:
    sql = "SELECT id AS first, name AS second FROM users"
    service = _service(sql)
    symbol = service.symbol_at(sql, Position(0, sql.index("first")))
    assert symbol is not None
    plan = build_rename_plan(sql, symbol, "second")
    renamed = service.symbol_at(
        plan.text,
        offset_to_position(plan.text, plan.declaration.start),
    )

    assert renamed is not None
    assert service.symbol_has_conflict(plan.text, renamed)
