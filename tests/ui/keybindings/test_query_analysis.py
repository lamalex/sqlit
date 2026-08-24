"""UI integration tests for structural query analysis."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.query.app.query_analysis import SemanticStatus, SyntaxRange
from sqlit.domains.query.editing import Position
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


@pytest.mark.asyncio
async def test_app_analysis_service_reads_live_query_document() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.query_input.text = "SELECT 1; SELECT 2;"
        await pilot.pause()

        analysis = app._get_query_analysis_service()
        assert analysis.statement_at(Position(0, 12)) == SyntaxRange(Position(0, 10), Position(0, 19), "statement")


@pytest.mark.asyncio
async def test_analysis_service_updates_semantic_dialect_with_provider() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)):
        app.query_input.text = "SELECT id FROM users"
        analysis = app._get_query_analysis_service()
        assert analysis.semantic_snapshot(app.query_input.text).status == SemanticStatus.UNAVAILABLE

        app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="postgres"))
        same_analysis = app._get_query_analysis_service()

        assert same_analysis is analysis
        snapshot = analysis.semantic_snapshot(app.query_input.text)
        assert snapshot.status == SemanticStatus.EXACT
        assert snapshot.dialect == "postgres"
        assert snapshot.tables[0].name.parts == ("users",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sql", "reference", "definition"),
    [
        (
            "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent",
            "recent.id",
            "recent",
        ),
        ("SELECT u.id FROM users AS u", "u.id", "AS u"),
        (
            "SELECT total AS amount FROM orders ORDER BY amount",
            "amount",
            "AS amount",
        ),
    ],
)
async def test_gd_goes_to_sql_definition(
    sql: str,
    reference: str,
    definition: str,
) -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.rindex(reference)))

        await pilot.press("g", "d")
        await pilot.pause()

        definition_name = definition.rsplit(" ", 1)[-1]
        definition_offset = sql.index(definition) + len(definition) - len(definition_name)
        assert app._query_logical_head() == (0, definition_offset)
        assert app.vim_mode == VimMode.NORMAL
        assert app._query_selection.normal_selection_primary is True


@pytest.mark.asyncio
async def test_gd_leaves_cursor_unchanged_when_semantics_are_unavailable() -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "SELECT id FROM users WHERE ("
        app._set_normal_selection((0, 7))

        await pilot.press("g", "d")
        await pilot.pause()

        assert app._query_logical_head() == (0, 7)
        assert not app._leader_pending
        assert not app._query_jump_back


@pytest.mark.asyncio
async def test_query_jump_history_restores_exact_visual_selection() -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))
    sql = "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("recent.id")))
        await pilot.press("v", "l")
        source = app._query_selection

        await pilot.press("g", "d")
        await pilot.pause()
        target = app._query_selection
        assert target != source

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert app._query_selection == source

        await pilot.press("ctrl+i")
        await pilot.pause()
        assert app._query_selection == target


@pytest.mark.asyncio
async def test_new_definition_jump_clears_forward_history() -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))
    sql = "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent ORDER BY recent.id"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("recent.id")))
        await pilot.press("g", "d", "ctrl+o")

        app._set_normal_selection((0, sql.rindex("recent.id")))
        await pilot.press("g", "d")
        await pilot.pause()
        second_target = app._query_selection

        assert app._query_jump_forward == []
        await pilot.press("ctrl+i")
        await pilot.pause()
        assert app._query_selection == second_target


@pytest.mark.asyncio
async def test_query_text_change_clears_jump_history() -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))
    sql = "WITH recent AS (SELECT id FROM users) SELECT id FROM recent"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.rindex("recent")))
        await pilot.press("g", "d")
        await pilot.pause()
        assert app._query_jump_back

        app.query_input.text = f"{sql} "
        await pilot.pause()
        changed_selection = app._query_selection

        assert app._query_jump_back == []
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert app._query_selection == changed_selection


@pytest.mark.asyncio
async def test_loading_same_history_query_clears_jump_history() -> None:
    app = _make_app()
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))
    sql = "WITH recent AS (SELECT id FROM users) SELECT id FROM recent"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.rindex("recent")))
        await pilot.press("g", "d")
        await pilot.pause()
        assert app._query_jump_back

        app._apply_history_query(sql)

        assert not app._query_jump_back
        assert not app._query_jump_forward
