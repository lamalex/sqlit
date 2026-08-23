"""UI tests for vim visual mode keybindings in the query editor."""

from __future__ import annotations

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services

SAMPLE_TEXT = "select\n  foo,\n  bar,\n  baz\nfrom foo\nwhere 1=1"


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestEnterExitVisualMode:
    """Test entering and exiting visual modes."""

    @pytest.mark.asyncio
    async def test_v_enters_visual_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

    @pytest.mark.asyncio
    async def test_V_enters_visual_line_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

    @pytest.mark.asyncio
    async def test_x_selects_current_line(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (1, 2)
            await pilot.pause()

            await pilot.press("x")
            await pilot.pause()

            assert app.vim_mode == VimMode.VISUAL_LINE
            start, end = app._ordered_selection(app.query_input.selection)
            assert start == (1, 0)
            assert end == (1, len("  foo,"))

    @pytest.mark.asyncio
    async def test_repeated_x_extends_line_selection(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (1, 2)
            await pilot.pause()

            await pilot.press("x", "x")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert start == (1, 0)
            assert end == (2, len("  bar,"))

    @pytest.mark.asyncio
    async def test_escape_exits_visual_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("escape")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_escape_exits_visual_line_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("escape")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_v_exits_visual_mode(self) -> None:
        """Pressing v again in visual mode should exit."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    @pytest.mark.parametrize("start,motion", [((0, 0), "w"), ((0, 6), "b")])
    async def test_v_preserves_existing_normal_selection(
        self, start: tuple[int, int], motion: str
    ) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection(start)
            await pilot.press(motion)
            before = app._ordered_selection(app.query_input.selection)

            await pilot.press("v")
            await pilot.pause()

            assert app.vim_mode == VimMode.VISUAL
            assert app._ordered_selection(app.query_input.selection) == before

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("start", "motion", "expected"),
        [((0, 0), "w", (0, 6)), ((0, 6), "b", (0, 0))],
    )
    async def test_visual_exit_collapses_to_logical_head(
        self,
        start: tuple[int, int],
        motion: str,
        expected: tuple[int, int],
    ) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection(start)

            await pilot.press("v", motion, "escape")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._normal_cursor == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("start", "motions", "expected"),
        [((0, 0), ("l", "l"), (0, 2)), ((0, 4), ("h", "h"), (0, 2))],
    )
    async def test_semicolon_collapses_character_selection_to_head(
        self,
        start: tuple[int, int],
        motions: tuple[str, ...],
        expected: tuple[int, int],
    ) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello"
            app._set_normal_selection(start)

            await pilot.press("v", *motions, "semicolon")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._normal_cursor == expected
            assert app._normal_selection_primary is True

    @pytest.mark.asyncio
    async def test_semicolon_collapses_line_selection_to_head(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one\ntwo\nthree"
            app._set_normal_selection((1, 1))

            await pilot.press("x", "x", "semicolon")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._normal_cursor == (2, len("three") - 1)
            assert app._normal_selection_primary is True

    @pytest.mark.asyncio
    async def test_V_exits_visual_line_mode(self) -> None:
        """Pressing V again in visual line mode should exit."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL


class TestVisualModeToggle:
    """Test toggling between visual and visual line modes."""

    @pytest.mark.asyncio
    async def test_V_in_visual_switches_to_visual_line(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

    @pytest.mark.asyncio
    async def test_v_in_visual_line_switches_to_visual(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL


class TestVisualModeMotions:
    """Test that motions extend selection in visual mode."""

    @pytest.mark.asyncio
    async def test_visual_mode_h_l_movement(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 5)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()

            sel = app.query_input.selection
            assert sel.start != sel.end, "Selection should be non-empty after motion"

    @pytest.mark.asyncio
    async def test_visual_mode_w_extends_selection(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            sel = app.query_input.selection
            assert sel.start != sel.end
            assert app.vim_mode == VimMode.VISUAL

    @pytest.mark.asyncio
    async def test_visual_line_mode_j_k_movement(self) -> None:
        """j/k should extend selection by full lines in visual line mode."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            # Move down
            await pilot.press("j")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            # Should span from row 1 col 0 to row 2 end
            assert start[0] == 1
            assert start[1] == 0
            assert end[0] == 2

            # Move back up
            await pilot.press("k")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            assert start[0] == 1
            assert end[0] == 1

    @pytest.mark.asyncio
    async def test_visual_line_mode_G_extends_to_end(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("G")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            assert start[0] == 0
            last_row = SAMPLE_TEXT.count("\n")
            assert end[0] == last_row


class TestVisualModeOperators:
    """Test operators (y, d, c) in visual modes."""

    @pytest.mark.asyncio
    async def test_visual_yank(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            # Select "hello w" — w moves to col 6, inclusive of cursor char
            await pilot.press("w")
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._internal_clipboard == "hello w"
            # Text should be unchanged
            assert app.query_input.text == "hello world"

    @pytest.mark.asyncio
    async def test_normal_p_uses_internal_clipboard_when_system_clipboard_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = _make_app()

        monkeypatch.setattr("sqlit.shared.ui.clipboard.get_system_clipboard_text", lambda: "")

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM users"
            app.query_input.cursor_location = (0, len(app.query_input.text))
            app._internal_clipboard = " WHERE id = 1"
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()

            assert app.query_input.text == "SELECT * FROM users WHERE id = 1"

    @pytest.mark.asyncio
    async def test_normal_p_prefers_system_clipboard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app = _make_app()

        monkeypatch.setattr(
            "sqlit.shared.ui.clipboard.get_system_clipboard_text",
            lambda: " WHERE active = true",
        )

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM users"
            app.query_input.cursor_location = (0, len(app.query_input.text))
            app._internal_clipboard = " WHERE id = 1"
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()

            assert app.query_input.text == "SELECT * FROM users WHERE active = true"

    @pytest.mark.asyncio
    async def test_normal_p_inserts_after_selection_without_replacing_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = _make_app()
        monkeypatch.setattr("sqlit.shared.ui.clipboard.get_system_clipboard_text", lambda: "")

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._internal_clipboard = "SQL "
            app._set_normal_selection((0, 0))
            await pilot.press("w", "p")
            await pilot.pause()

            assert app.query_input.text == "hello SQL world"

    @pytest.mark.asyncio
    async def test_visual_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "orld"

    @pytest.mark.asyncio
    async def test_visual_change_enters_insert(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.text == "orld"

    @pytest.mark.asyncio
    async def test_visual_line_yank(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._internal_clipboard == "beta"
            assert app.query_input.text == "alpha\nbeta\ngamma"

    @pytest.mark.asyncio
    async def test_visual_line_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "alpha\ngamma"

    @pytest.mark.asyncio
    async def test_visual_line_delete_multiple_lines(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma\ndelta"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "alpha\ndelta"

    @pytest.mark.asyncio
    async def test_visual_line_change_enters_insert(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.text == "alpha\ngamma"


class TestSelectionExecution:
    @pytest.mark.asyncio
    async def test_normal_primary_selection_executes_full_query(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)):
            app.action_focus_query()
            app.query_input.text = "SELECT 1"
            app._set_normal_selection((0, 0))

            assert app._get_query_to_execute() == "SELECT 1"
            assert app._query_execution_scope == "query"

    @pytest.mark.asyncio
    async def test_select_mode_executes_selected_query(self) -> None:
        from textual.widgets.text_area import Selection

        app = _make_app()

        async with app.run_test(size=(100, 35)):
            app.action_focus_query()
            app.query_input.text = "SELECT 1; SELECT 2"
            app.vim_mode = VimMode.VISUAL
            app.query_input.selection = Selection((0, 0), (0, 8))

            assert app._get_query_to_execute() == "SELECT 1"
            assert app._query_execution_scope == "selection"

    @pytest.mark.asyncio
    async def test_normal_motion_selection_executes_selected_sql(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT 1; SELECT 2"
            app._set_normal_selection((0, 0))

            await pilot.press("e")
            await pilot.pause()

            assert app._get_query_to_execute() == "SELECT"
            assert app._query_execution_scope == "selection"

    @pytest.mark.asyncio
    async def test_one_character_search_selection_is_substantive(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT 1; SELECT 2"
            app._set_normal_selection((0, 0))

            await pilot.press("slash", "1", "enter")
            await pilot.pause()

            assert app._get_query_to_execute() == "1"
            assert app._query_execution_scope == "selection"

    @pytest.mark.asyncio
    async def test_one_character_word_end_selection_is_substantive(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "x"
            app._set_normal_selection((0, 0))

            await pilot.press("e")
            await pilot.pause()

            assert app._get_query_to_execute() == "x"
            assert app._query_execution_scope == "selection"

    @pytest.mark.asyncio
    async def test_collapsed_selection_executes_full_query(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT 1; SELECT 2"
            app._set_normal_selection((0, 0))

            await pilot.press("e", "semicolon")
            await pilot.pause()

            assert app._get_query_to_execute() == "SELECT 1; SELECT 2"
            assert app._query_execution_scope == "query"

    @pytest.mark.asyncio
    async def test_native_normal_selection_is_substantive(self) -> None:
        from textual.widgets.text_area import Selection

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT 1; SELECT 2"
            app._set_normal_selection((0, 0))
            app.query_input.selection = Selection((0, 10), (0, 18))
            await pilot.pause()

            assert app._get_query_to_execute() == "SELECT 2"
