"""UI tests for the canonical query selection snapshot."""

from __future__ import annotations

import pytest
from textual.widgets.text_area import Selection

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


def _assert_projected(app: SSMSTUI) -> None:
    state = app._query_selection
    assert app.query_input.selection == Selection(state.start, state.end)
    assert app.vim_mode == state.vim_mode


@pytest.mark.asyncio
async def test_native_selection_updates_canonical_state() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "select foo"
        app.query_input.selection = Selection((0, 0), (0, 6))
        await pilot.pause()

        _assert_projected(app)
        assert app._query_selection.logical_cursor == (0, 6)
        assert not app._query_selection.normal_selection_primary


@pytest.mark.asyncio
async def test_modal_transitions_replace_one_selection_snapshot() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "select foo\nfrom bar"
        app._set_normal_selection((0, 1))

        await pilot.press("v", "l")
        _assert_projected(app)
        assert app._query_selection.vim_mode == VimMode.VISUAL
        assert app._query_selection.visual_anchor == (0, 1)
        assert app._query_selection.visual_cursor == (0, 2)

        await pilot.press("V")
        _assert_projected(app)
        assert app._query_selection.vim_mode == VimMode.VISUAL_LINE
        assert app._query_selection.visual_line_anchor_row == 0

        await pilot.press("escape", "i")
        _assert_projected(app)
        assert app._query_selection.vim_mode == VimMode.INSERT
        assert app.query_input.selection.is_empty
        assert not app.query_input.read_only


@pytest.mark.asyncio
async def test_undo_capture_uses_canonical_snapshot() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "select foo"
        app._set_normal_selection((0, 2))
        await pilot.press("w")

        state = app._capture_undo_state()
        _assert_projected(app)
        assert state.selection is app._query_selection
