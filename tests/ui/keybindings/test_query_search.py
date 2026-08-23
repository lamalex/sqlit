"""UI tests for query-editor `/` search."""

from __future__ import annotations

import pytest

from sqlit.core.keymap import get_keymap
from sqlit.domains.query.ui.screens import QuerySearchScreen
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestQuerySearch:
    def test_default_search_keymap(self) -> None:
        keymap = get_keymap()

        assert keymap.action("query_search") == "slash"
        assert keymap.action("query_search_next") == "n"
        assert keymap.action("query_search_previous") == "N"
        assert keymap.action("new_query") == "ctrl+n"

    @pytest.mark.asyncio
    async def test_slash_search_selects_complete_next_match(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two one"
            app._set_normal_selection((0, 0))

            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen, QuerySearchScreen)
            await pilot.press("o", "n", "e", "enter")
            await pilot.pause()

            start, end = app._ordered_selection(app.query_input.selection)
            assert (start, end) == ((0, 8), (0, 11))
            assert app.query_input.text[start[1] : end[1]] == "one"

    @pytest.mark.asyncio
    async def test_n_and_N_repeat_with_wrap(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two one"
            app._set_normal_selection((0, 0))
            await pilot.press("slash", "o", "n", "e", "enter")
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()
            assert app._ordered_selection(app.query_input.selection) == ((0, 0), (0, 3))

            await pilot.press("N")
            await pilot.pause()
            assert app._ordered_selection(app.query_input.selection) == ((0, 8), (0, 11))
            assert app.query_input.text == "one two one"

    @pytest.mark.asyncio
    async def test_escape_cancels_without_changing_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two one"
            app._set_normal_selection((0, 4))
            before = app.query_input.selection

            await pilot.press("slash", "escape")
            await pilot.pause()

            assert not isinstance(app.screen, QuerySearchScreen)
            assert app.query_input.selection == before

    @pytest.mark.asyncio
    async def test_lowercase_search_matches_uppercase_sql(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "SELECT one\nSELECT two"
            app._set_normal_selection((0, 0))

            await pilot.press("slash", "s", "e", "l", "e", "c", "t", "enter")
            await pilot.pause()

            assert app._ordered_selection(app.query_input.selection) == ((1, 0), (1, 6))

    @pytest.mark.asyncio
    async def test_n_repeats_from_backward_selection_head(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one xx one"
            app._set_normal_selection((0, 7))
            app._last_query_search = "one"

            await pilot.press("b", "n")
            await pilot.pause()

            assert app._ordered_selection(app.query_input.selection) == ((0, 7), (0, 10))

    @pytest.mark.asyncio
    async def test_reopening_search_replaces_previous_term(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "one two one"
            app._set_normal_selection((0, 0))
            await pilot.press("slash", "o", "n", "e", "enter")
            await pilot.pause()

            await pilot.press("slash", "t", "w", "o", "enter")
            await pilot.pause()

            assert app._last_query_search == "two"
            assert app._ordered_selection(app.query_input.selection) == ((0, 4), (0, 7))

    @pytest.mark.asyncio
    async def test_n_cycles_overlapping_matches(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            app.query_input.text = "aaa"
            app._set_normal_selection((0, 0))

            await pilot.press("slash", "a", "a", "enter")
            await pilot.pause()
            assert app._ordered_selection(app.query_input.selection) == ((0, 1), (0, 3))

            await pilot.press("n")
            await pilot.pause()
            assert app._ordered_selection(app.query_input.selection) == ((0, 0), (0, 2))
