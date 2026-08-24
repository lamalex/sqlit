"""UI tests for semantic SQL symbol rename."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from textual.widgets import Input

from sqlit.core.vim import VimMode
from sqlit.domains.connections.app.mocks import get_mock_profile
from sqlit.domains.query.ui.screens import QueryRenameScreen
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)
    app.current_provider = SimpleNamespace(metadata=SimpleNamespace(analysis_dialect="sqlite"))
    return app


@pytest.mark.asyncio
async def test_gR_cancel_restores_exact_visual_selection() -> None:
    app = _make_app()
    sql = "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("recent.id")))
        await pilot.press("v", "l")
        original = app._query_selection

        await pilot.press("g", "R")
        assert isinstance(app.screen, QueryRenameScreen)
        assert app.screen.query_one("#query-rename-input", Input).value == "recent"

        await pilot.press("escape")

        assert app.query_input.text == sql
        assert app._query_selection == original
        assert not app._get_undo_history().can_undo()


@pytest.mark.asyncio
async def test_gR_renames_once_and_undo_redo_restore_exact_states() -> None:
    app = _make_app()
    sql = "WITH recent AS (SELECT id FROM users) SELECT recent.id FROM recent"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("recent.id")))
        await pilot.press("v", "l")
        original = app._query_selection

        await pilot.press("g", "R")
        rename_input = app.screen.query_one("#query-rename-input", Input)
        rename_input.value = "active_recent"
        await pilot.press("enter")
        await pilot.pause()

        renamed_text = "WITH active_recent AS (SELECT id FROM users) SELECT active_recent.id FROM active_recent"
        renamed = app._query_selection
        assert app.query_input.text == renamed_text
        assert app._query_logical_head() == (0, 5)
        assert app.vim_mode == VimMode.NORMAL
        assert renamed.normal_selection_primary is True

        await pilot.press("u")
        assert app.query_input.text == sql
        assert app._query_selection == original

        await pilot.press("ctrl+y")
        assert app.query_input.text == renamed_text
        assert app._query_selection == renamed


@pytest.mark.asyncio
async def test_gR_rejects_alias_collision_without_mutating_query() -> None:
    app = _make_app()
    sql = "SELECT a.id, b.id FROM users AS a JOIN orders AS b ON a.id = b.user_id"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("a.id")))
        original = app._query_selection

        await pilot.press("g", "R")
        app.screen.query_one("#query-rename-input", Input).value = "b"
        await pilot.press("enter")
        await pilot.pause()

        assert app.query_input.text == sql
        assert app._query_selection == original
        assert not app._get_undo_history().can_undo()


@pytest.mark.asyncio
async def test_gR_ignores_stale_prompt_after_query_changes() -> None:
    app = _make_app()
    sql = "SELECT u.id FROM users AS u"

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("u.id")))
        await pilot.press("g", "R")

        changed = f"{sql} WHERE active"
        app.query_input.text = changed
        app.screen.query_one("#query-rename-input", Input).value = "customer"
        await pilot.press("enter")
        await pilot.pause()

        assert app.query_input.text == changed
        assert not app._get_undo_history().can_undo()


@pytest.mark.asyncio
async def test_gR_is_unavailable_for_incomplete_sql() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "SELECT id FROM users WHERE ("
        app._set_normal_selection((0, 7))
        original = app._query_selection

        await pilot.press("g", "R")
        await pilot.pause()

        assert app._query_selection == original
        assert not app._leader_pending
        assert not isinstance(app.screen, QueryRenameScreen)


@pytest.mark.asyncio
async def test_gR_uses_single_mock_profile_dialect_before_connecting() -> None:
    profile = get_mock_profile("sqlite-demo")
    assert profile is not None
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    services.apply_mock_profile(profile)
    app = SSMSTUI(services=services)
    sql = "WITH recent_orders AS (SELECT 1) SELECT * FROM recent_orders"

    async with app.run_test(size=(100, 35)) as pilot:
        assert app.current_provider is None
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, sql.index("recent_orders")))

        await pilot.press("g", "R")

        assert isinstance(app.screen, QueryRenameScreen)
        assert app._get_query_analysis_service().dialect == "sqlite"
