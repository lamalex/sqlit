"""UI tests for syntax-aware query selections."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services

SQL = "SELECT foo, bar FROM widgets;"


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


@pytest.mark.asyncio
async def test_expand_and_shrink_restore_exact_primary_selection() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = SQL
        app._set_normal_selection((0, 8))
        original = app._query_selection

        await pilot.press("alt+o")
        assert app._ordered_selection(app.query_input.selection) == ((0, 7), (0, 10))
        assert not app._query_selection.normal_selection_primary

        await pilot.press("alt+i")
        assert app._query_selection == original


@pytest.mark.asyncio
async def test_repeated_expand_and_shrink_walk_selection_history() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = SQL
        app._set_normal_selection((0, 8))

        await pilot.press("alt+o", "alt+o")
        assert app._ordered_selection(app.query_input.selection) == ((0, 7), (0, 15))

        await pilot.press("alt+i")
        assert app._ordered_selection(app.query_input.selection) == ((0, 7), (0, 10))


@pytest.mark.asyncio
async def test_syntax_sibling_navigation_preserves_history() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = SQL
        app._set_normal_selection((0, 8))

        await pilot.press("alt+o", "alt+n")
        assert app._ordered_selection(app.query_input.selection) == ((0, 12), (0, 15))

        await pilot.press("alt+p")
        assert app._ordered_selection(app.query_input.selection) == ((0, 7), (0, 10))

        await pilot.press("alt+i")
        assert app._ordered_selection(app.query_input.selection) == ((0, 12), (0, 15))


@pytest.mark.asyncio
async def test_regular_motion_invalidates_structural_history() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = SQL
        app._set_normal_selection((0, 8))

        await pilot.press("alt+o", "l")
        after_motion = app._query_selection
        await pilot.press("alt+i")

        assert app._query_selection == after_motion


@pytest.mark.asyncio
async def test_select_current_statement_includes_terminator() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)):
        app.action_focus_query()
        app.query_input.text = "SELECT 1; SELECT 2;"
        app._set_normal_selection((0, 12))

        app.action_select_current_statement()

        assert app._ordered_selection(app.query_input.selection) == ((0, 10), (0, 19))


@pytest.mark.asyncio
async def test_expand_is_safe_for_incomplete_sql() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "SELECT ("
        app._set_normal_selection((0, 7))

        await pilot.press("alt+o")

        start, end = app._ordered_selection(app.query_input.selection)
        assert start <= end
