"""Tests for keybindings in vim INSERT mode."""

from __future__ import annotations

import pytest

from sqlit.core.keymap import get_keymap
from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestInsertModeKeybindings:
    """Test keybindings in vim INSERT mode."""

    @pytest.mark.asyncio
    async def test_enter_insert_mode_key(self):
        """Enter insert mode key should enter INSERT mode when in query normal mode."""
        keymap = get_keymap()
        insert_key = keymap.action("enter_insert_mode")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL

            await pilot.press(insert_key)
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_exit_insert_mode_key(self):
        """Exit insert mode key should exit INSERT mode."""
        keymap = get_keymap()
        exit_key = keymap.action("exit_insert_mode")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select"
            app._set_normal_selection((0, 0))
            await pilot.pause()

            # Enter insert mode
            app.action_enter_insert_mode()
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT

            # Exit with configured key
            await pilot.press(exit_key)
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.selection.start != app.query_input.selection.end

    @pytest.mark.asyncio
    async def test_navigation_blocked_in_insert_mode(self):
        """Navigation keys should be blocked in INSERT mode."""
        keymap = get_keymap()
        window_key = keymap.action("window_leader_key")
        focus_explorer_key = keymap.leader("left", "window")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Enter insert mode
            app.action_enter_insert_mode()
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.has_focus

            # Try to navigate with focus explorer key - should NOT switch focus
            await pilot.press(window_key, focus_explorer_key)
            await pilot.pause()

            # Should still be in query with insert mode
            assert app.query_input.has_focus
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_i_inserts_before_selection(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))
            await pilot.press("w", "i")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_a_inserts_after_selection(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))
            await pilot.press("w", "a")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.cursor_location == (0, 6)
