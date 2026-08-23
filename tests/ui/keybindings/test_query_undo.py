"""UI regressions for selection-aware query undo and redo."""

from __future__ import annotations

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestQuerySelectionUndo:
    @pytest.mark.asyncio
    async def test_undo_restores_backward_normal_selection_and_provenance(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "alpha beta"
            app._set_normal_selection((0, 6))
            await pilot.press("b")
            before = app._capture_undo_state()

            await pilot.press("r", "x", "u")
            await pilot.pause()

            assert app._capture_undo_state() == before
            assert app._normal_selection_primary is False
            assert app._get_query_to_execute() == "alpha"

    @pytest.mark.asyncio
    async def test_redo_restores_exact_post_edit_normal_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "alpha beta"
            app._set_normal_selection((0, 0))
            await pilot.press("e", "r", "x")
            after = app._capture_undo_state()

            await pilot.press("u", "ctrl+r")
            await pilot.pause()

            assert app._capture_undo_state() == after

    @pytest.mark.asyncio
    async def test_visual_delete_undo_restores_mode_anchor_and_head(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "alpha beta"
            app._set_normal_selection((0, 6))
            await pilot.press("v", "l", "l")
            before = app._capture_undo_state()

            await pilot.press("d", "u")
            await pilot.pause()

            assert app._capture_undo_state() == before
            assert app.vim_mode == VimMode.VISUAL

    @pytest.mark.asyncio
    async def test_visual_line_delete_undo_restores_line_anchor(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one\ntwo\nthree"
            app._set_normal_selection((0, 0))
            await pilot.press("x", "x")
            before = app._capture_undo_state()

            await pilot.press("d", "u")
            await pilot.pause()

            assert app._capture_undo_state() == before
            assert app.vim_mode == VimMode.VISUAL_LINE
            assert app._visual_line_anchor_row == 0

    @pytest.mark.asyncio
    async def test_visual_change_undo_and_redo_restore_both_modes(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "alpha beta"
            app._set_normal_selection((0, 6))
            await pilot.press("v", "l", "l")
            before = app._capture_undo_state()

            await pilot.press("c")
            after = app._capture_undo_state()
            assert after.selection.vim_mode == VimMode.INSERT

            await pilot.press("ctrl+z")
            await pilot.pause()
            assert app._capture_undo_state() == before

            await pilot.press("ctrl+y")
            await pilot.pause()
            assert app._capture_undo_state() == after


class TestQueryInsertUndo:
    @pytest.mark.asyncio
    async def test_first_insert_character_undo_and_redo_restore_collapsed_cursor(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = ""
            app._set_normal_selection((0, 0))

            await pilot.press("i", "a", "ctrl+z")
            await pilot.pause()

            assert app.query_input.text == ""
            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.selection.start == app.query_input.selection.end == (0, 0)

            await pilot.press("ctrl+y")
            await pilot.pause()

            assert app.query_input.text == "a"
            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.selection.start == app.query_input.selection.end == (0, 1)

    @pytest.mark.asyncio
    async def test_new_insert_after_undo_invalidates_redo_immediately(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = ""
            app._set_normal_selection((0, 0))

            await pilot.press("i", "a", "ctrl+z", "b", "ctrl+y")
            await pilot.pause()

            assert app.query_input.text == "b"
            assert app.vim_mode == VimMode.INSERT
