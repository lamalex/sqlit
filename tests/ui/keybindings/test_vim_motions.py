"""UI tests for vim motion keybindings in the query editor."""

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


class TestVimMotionKeybindings:
    """Test vim motion keybindings in NORMAL mode."""

    @pytest.mark.asyncio
    async def test_word_motions_w_W_b_B(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "foo-bar baz"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            await pilot.press("W")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 8)

            await pilot.press("b")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            await pilot.press("B")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_e_selects_through_word_end(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))

            await pilot.press("e")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert app.query_input.text[start[1] : end[1]] == "hello"

    @pytest.mark.asyncio
    async def test_r_replaces_selected_word_range(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))

            await pilot.press("w", "r")
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()

            assert app.query_input.text == "xxxxxxworld"
            assert app.query_input.selection.start != app.query_input.selection.end

    @pytest.mark.asyncio
    async def test_r_replaces_primary_character(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello"
            app._set_normal_selection((0, 0))

            await pilot.press("r")
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()

            assert app.query_input.text == "xello"

    @pytest.mark.asyncio
    async def test_r_preserves_backward_selection_head(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 6))

            await pilot.press("b", "r")
            await pilot.pause()
            await pilot.press("x", ";")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert app.query_input.text == "xxxxxxworld"
            assert (start, end) == ((0, 0), (0, 1))

    @pytest.mark.asyncio
    async def test_word_motion_then_delete_uses_selected_range(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))
            await pilot.pause()

            await pilot.press("w", "d")
            await pilot.pause()

            assert app.query_input.text == "world"
            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.selection.start != app.query_input.selection.end

    @pytest.mark.asyncio
    async def test_word_motion_then_change_enters_insert_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))
            await pilot.pause()

            await pilot.press("w", "c")
            await pilot.pause()

            assert app.query_input.text == "world"
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_semicolon_collapses_to_selection_head(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello world"
            app._set_normal_selection((0, 0))
            await pilot.press("w", ";")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert start == (0, 6)
            assert end == (0, 7)

    @pytest.mark.asyncio
    async def test_miw_selects_inner_word(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "alpha beta"
            app._set_normal_selection((0, 7))

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert app.query_input.text[start[1] : end[1]] == "beta"

    @pytest.mark.asyncio
    async def test_ma_quote_selects_quotes_and_contents(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = 'SELECT "cat"'
            app._set_normal_selection((0, 9))

            await pilot.press("m", "a")
            await pilot.pause()
            await pilot.press('"')
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert app.query_input.text[start[1] : end[1]] == '"cat"'

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("text", "object_key", "expected_cursor"),
        [('SELECT ""', '"', (0, 8)), ("SELECT ()", "(", (0, 8))],
    )
    async def test_mi_empty_object_selects_empty_interior(
        self,
        text: str,
        object_key: str,
        expected_cursor: tuple[int, int],
    ) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = text
            app._set_normal_selection((0, 7))

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press(object_key)
            await pilot.pause()

            selection = app.query_input.selection
            assert selection.start == selection.end == expected_cursor

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "keys",
        [("2", "d"), ("2", "y"), ("2", "c"), ("2", ";"), ("2", "r"), ("2", "m")],
    )
    async def test_selection_commands_consume_ignored_count(
        self, keys: tuple[str, ...]
    ) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two three"
            app._set_normal_selection((0, 0))

            await pilot.press(*keys)
            await pilot.pause()

            assert app._count_buffer == ""

    @pytest.mark.asyncio
    async def test_ignored_delete_count_does_not_affect_next_motion(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two three"
            app._set_normal_selection((0, 0))

            await pilot.press("2", "d", "w")
            await pilot.pause()

            assert app._normal_cursor == (0, 3)

    @pytest.mark.asyncio
    async def test_d_without_range_deletes_primary_character(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "hello"
            app.query_input.cursor_location = (0, 0)

            await pilot.press("d")
            await pilot.pause()

            assert app.query_input.text == "ello"
            assert app._leader_pending is False

    @pytest.mark.asyncio
    async def test_line_motions_0_dollar_G(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            lines = "SELECT * FROM cats\nSELECT * FROM dogs"
            app.query_input.text = lines
            app.query_input.cursor_location = (0, 7)
            await pilot.pause()

            await pilot.press("0")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

            await pilot.press("$")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, len("SELECT * FROM cats"))

            await pilot.press("G")
            await pilot.pause()
            assert app.query_input.cursor_location == (1, 0)

    @pytest.mark.asyncio
    async def test_find_char_motions_f_F(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            line = "select cat catalog"
            app.query_input.text = line
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("f")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            app.query_input.cursor_location = (0, len(line))
            await pilot.pause()

            await pilot.press("F")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 11)

    @pytest.mark.asyncio
    async def test_till_char_motions_t_T(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            line = "select cat catalog"
            app.query_input.text = line
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("t")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 3)

            line_back = "abcdeabc"
            app.query_input.text = line_back
            app.query_input.cursor_location = (0, len(line_back) - 1)
            await pilot.pause()

            await pilot.press("T")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 6)

    @pytest.mark.asyncio
    async def test_matching_bracket_motion(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "(cats)"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("%")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 5)

    @pytest.mark.asyncio
    async def test_go_to_first_line_gg(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT 1\nSELECT 2\nSELECT 3"
            app.query_input.cursor_location = (2, 4)
            await pilot.pause()

            await pilot.press("g", "g")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_go_to_last_line_ge(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT 1\nSELECT 2\nSELECT 3"
            app._set_normal_selection((0, 3))

            await pilot.press("g", "e")
            await pilot.pause()

            assert app.query_input.cursor_location == (2, 0)

    @pytest.mark.asyncio
    async def test_gh_and_gl_go_to_line_boundaries(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT cats"
            app._set_normal_selection((0, 4))

            await pilot.press("g", "h")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

            await pilot.press("g", "l")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, len("SELECT cats") - 1)

    @pytest.mark.asyncio
    async def test_gs_goes_to_first_non_whitespace(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "    SELECT 1"
            app._set_normal_selection((0, 10))

            await pilot.press("g", "s")
            await pilot.pause()

            assert app.query_input.cursor_location == (0, 4)

    @pytest.mark.asyncio
    async def test_ge_extends_select_mode_to_last_line(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one\ntwo\nthree"
            app._set_normal_selection((0, 0))

            await pilot.press("v", "g", "e")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert start == (0, 0)
            assert end[0] == 2

    @pytest.mark.asyncio
    async def test_select_to_line_end_then_change(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM cats"
            app.query_input.cursor_location = (0, 7)
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL

            await pilot.press("v", "$", "c")
            await pilot.pause()

            assert app.query_input.text == "SELECT "
            assert app.query_input.cursor_location == (0, 7)
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_select_word_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("w", "d")
            await pilot.pause()

            assert app.query_input.text == "world"
            assert app.query_input.cursor_location == (0, 0)
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_select_to_line_end_then_copy(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM cats"
            app.query_input.cursor_location = (0, 7)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("v", "$", "y")
            await pilot.pause()

            assert app._internal_clipboard == "* FROM cats"

    @pytest.mark.asyncio
    async def test_select_to_line_start_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("v", "0", "d")
            await pilot.pause()

            assert app.query_input.text == "orld"
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_select_lines_to_end_then_copy(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 2)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("x", "G", "y")
            await pilot.pause()

            assert app._internal_clipboard == "beta\ngamma"

    @pytest.mark.asyncio
    async def test_select_inside_word_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press("w", "d")
            await pilot.pause()

            assert app.query_input.text == "alpha "
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_select_around_word_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta gamma"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("m", "a")
            await pilot.pause()
            await pilot.press("w", "d")
            await pilot.pause()

            assert app.query_input.text == "alpha gamma"

    @pytest.mark.asyncio
    async def test_select_inside_word_then_change(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press("w", "c")
            await pilot.pause()

            assert app.query_input.text == "alpha "
            assert app.query_input.cursor_location == (0, 6)
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_select_inside_quotes_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = 'SELECT "cat" AS name'
            app.query_input.cursor_location = (0, 9)
            await pilot.pause()

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press('"', "d")
            await pilot.pause()

            assert app.query_input.text == 'SELECT "" AS name'
            assert app.query_input.cursor_location == (0, 8)

    @pytest.mark.asyncio
    async def test_select_inside_parens_then_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "func(call(arg))"
            app.query_input.cursor_location = (0, 11)
            await pilot.pause()

            await pilot.press("m", "i")
            await pilot.pause()
            await pilot.press("(", "d")
            await pilot.pause()

            assert app.query_input.text == "func(call())"

    # ========================================================================
    # Count prefix tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_5j_moves_down_5_lines(self) -> None:
        """5j should move cursor down 5 lines."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5\nline6\nline7"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            # Press 5 then j
            await pilot.press("5")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 5, f"Expected row 5, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_3k_moves_up_3_lines(self) -> None:
        """3k should move cursor up 3 lines."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5"
            app.query_input.cursor_location = (4, 0)  # Start at line 5
            await pilot.pause()

            await pilot.press("3")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 1, f"Expected row 1, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_2w_moves_forward_2_words(self) -> None:
        """2w should move cursor forward 2 words."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world goodbye"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("2")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            # After 2w: hello(0) -> world(6) -> goodbye(12)
            assert app.query_input.cursor_location == (0, 12), f"Expected (0, 12), got {app.query_input.cursor_location}"

    @pytest.mark.asyncio
    async def test_word_selection_on_semicolon_delimited_string(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hey;hello;whatsup"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("w", "d")
            await pilot.pause()

            assert app.query_input.text == "hello;whatsup", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_two_word_selection_on_semicolon_delimited_string(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hey;hello;whatsup"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("2")
            await pilot.pause()
            await pilot.press("w", "d")
            await pilot.pause()

            # "hey;hello;whatsup"
            #  01234567890123456
            # w from 0 -> 4 ("hello"), w from 4 -> 10 ("whatsup")
            assert app.query_input.text == "whatsup", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_repeated_x_then_d_deletes_three_lines(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5"
            app.query_input.cursor_location = (1, 0)  # Start at line2
            await pilot.pause()

            await pilot.press("x", "x", "x", "d")
            await pilot.pause()

            # Should delete line2, line3, line4
            assert app.query_input.text == "line1\nline5", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_25G_goes_to_line_25(self) -> None:
        """25G should go to line 25."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 30 lines
            lines = [f"line{i+1}" for i in range(30)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("2", "5")
            await pilot.pause()
            await pilot.press("G")
            await pilot.pause()

            # 25G goes to line 25 (0-indexed: row 24)
            assert app.query_input.cursor_location[0] == 24, f"Expected row 24, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_3gg_goes_to_line_3(self) -> None:
        """3gg should go to line 3 (0-indexed: row 2)."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 10 lines
            lines = [f"line{i+1}" for i in range(10)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (7, 0)
            await pilot.pause()

            await pilot.press("3", "g", "g")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 2, f"Expected row 2, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_colon_25_goes_to_line_25(self) -> None:
        """:25 command should go to line 25."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 30 lines
            lines = [f"line{i+1}" for i in range(30)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            # Type :25 and press enter
            await pilot.press(":")
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("5")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # :25 goes to line 25 (0-indexed: row 24)
            assert app.query_input.cursor_location[0] == 24, f"Expected row 24, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_zero_alone_goes_to_line_start(self) -> None:
        """0 alone should go to line start, not be treated as count."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("0")
            await pilot.pause()

            assert app.query_input.cursor_location == (0, 0), f"Expected (0, 0), got {app.query_input.cursor_location}"

    @pytest.mark.asyncio
    async def test_10j_works_with_zero_in_count(self) -> None:
        """10j should move down 10 lines (0 appends to count)."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 15 lines
            lines = [f"line{i+1}" for i in range(15)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("1", "0")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 10, f"Expected row 10, got {app.query_input.cursor_location[0]}"
