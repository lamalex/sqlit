"""UI tests for query-editor surround commands."""

from __future__ import annotations

import pytest
from textual.widgets.text_area import Selection

from sqlit.core.keymap import get_keymap
from sqlit.core.vim import VimMode
from sqlit.domains.query.ui.screens import SurroundMenuScreen
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


def _select_name(app: SSMSTUI, *, backward: bool = False) -> None:
    start = (0, 7)
    end = (0, 11)
    app.query_input.selection = Selection(end, start) if backward else Selection(start, end)
    app._normal_cursor = start if backward else (0, 10)
    app._normal_textual_cursor = start if backward else end


class TestQuerySurround:
    def test_default_surround_keymap(self) -> None:
        keymap = get_keymap()

        assert keymap.leader("surround_add", menu="match") == "s"
        assert keymap.leader("surround_delete", menu="match") == "d"
        assert keymap.leader("surround_replace", menu="match") == "r"

    @pytest.mark.asyncio
    async def test_ms_adds_surround_and_preserves_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select name from users"
            _select_name(app)

            await pilot.press("m", "s")
            await pilot.pause()
            assert isinstance(app.screen, SurroundMenuScreen)
            await pilot.press("(")
            await pilot.pause()

            assert app.query_input.text == "select (name) from users"
            assert app._ordered_selection(app.query_input.selection) == ((0, 8), (0, 12))
            assert app._query_logical_head() == (0, 11)

    @pytest.mark.asyncio
    async def test_md_deletes_nearest_surround(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select ((name))"
            app.query_input.selection = Selection((0, 9), (0, 13))
            app._normal_cursor = (0, 12)
            app._normal_textual_cursor = (0, 13)

            await pilot.press("m", "d", ")")
            await pilot.pause()

            assert app.query_input.text == "select (name)"
            assert app._ordered_selection(app.query_input.selection) == ((0, 8), (0, 12))

    @pytest.mark.asyncio
    async def test_mr_replaces_surround_and_preserves_backward_head(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select (name)"
            app.query_input.selection = Selection((0, 12), (0, 8))
            app._normal_cursor = (0, 8)
            app._normal_textual_cursor = (0, 8)

            await pilot.press("m", "r", "(", "[")
            await pilot.pause()

            assert app.query_input.text == "select [name]"
            assert app.query_input.selection == Selection((0, 12), (0, 8))
            assert app._query_logical_head() == (0, 8)

    @pytest.mark.asyncio
    async def test_surround_edit_is_undoable(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select name"
            _select_name(app)

            await pilot.press("m", "s", "{")
            await pilot.pause()
            assert app.query_input.text == "select {name}"

            await pilot.press("u")
            await pilot.pause()
            assert app.query_input.text == "select name"

    @pytest.mark.asyncio
    async def test_md_without_enclosing_pair_keeps_query_unchanged(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select name"
            _select_name(app)
            before = app.query_input.selection

            await pilot.press("m", "d", "(")
            await pilot.pause()

            assert app.query_input.text == "select name"
            assert app.query_input.selection == before

    @pytest.mark.asyncio
    async def test_xms_surrounds_selected_line(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "select name"
            app._set_normal_selection((0, 0))

            await pilot.press("x", "m", "s", "(")
            await pilot.pause()

            assert app.query_input.text == "(select name)"
            assert app._ordered_selection(app.query_input.selection) == ((0, 1), (0, 12))
            assert app._query_logical_head() == (0, 11)
            assert app.vim_mode == VimMode.NORMAL
            assert app._get_query_to_execute() == "select name"

    @pytest.mark.asyncio
    async def test_visual_ms_surrounds_character_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "name"
            app._set_normal_selection((0, 0))

            await pilot.press("v", "l", "l", "l", "m", "s", "[")
            await pilot.pause()

            assert app.query_input.text == "[name]"
            assert app._ordered_selection(app.query_input.selection) == ((0, 1), (0, 5))
            assert app._query_logical_head() == (0, 4)
            assert app.vim_mode == VimMode.NORMAL
