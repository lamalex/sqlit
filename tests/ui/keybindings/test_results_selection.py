"""Helix-style selection behavior in results tables."""

from __future__ import annotations

from typing import Any

import pytest
from textual.coordinate import Coordinate

from sqlit.core.keymap import get_keymap
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


async def _populate_results(
    pilot: Any,
    app: SSMSTUI,
    columns: list[str],
    rows: list[tuple[Any, ...]],
) -> None:
    await pilot.pause()
    await app._display_query_results(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        elapsed_ms=0,
    )
    for _ in range(3):
        await pilot.pause(0.05)
    app.action_focus_results()
    await pilot.pause()


class TestResultsSelection:
    def test_default_selection_keymap(self) -> None:
        keymap = get_keymap()

        assert keymap.action("enter_results_selection") == "v"
        assert keymap.action("select_results_rows") == "x"
        assert keymap.action("yank_results_selection") == "y"
        assert keymap.action("edit_cell") == "r"
        assert keymap.action("clear_results") == "X"

    @pytest.mark.asyncio
    async def test_v_and_motions_select_rectangle(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name", "active"],
                [(1, "Ada", True), (2, "Linus", False)],
            )

            await pilot.press("v", "l", "j")
            await pilot.pause()

            table = app.results_table
            assert table.results_selection_mode == "rectangle"
            assert table.results_selection_bounds() == (0, 1, 0, 1)

    @pytest.mark.asyncio
    async def test_x_repeated_selects_complete_rows(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name", "active"],
                [(1, "Ada", True), (2, "Linus", False), (3, "Grace", True)],
            )

            await pilot.press("x", "x")
            await pilot.pause()

            table = app.results_table
            assert table.results_selection_mode == "rows"
            assert table.results_selection_bounds() == (0, 1, 0, 2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("collapse_key", ["semicolon", "escape"])
    async def test_collapse_keeps_logical_head(self, collapse_key: str) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name"],
                [(1, "Ada"), (2, "Linus")],
            )

            await pilot.press("v", "l", "j", collapse_key)
            await pilot.pause()

            table = app.results_table
            assert not table.results_selection_active
            assert table.cursor_coordinate == (1, 1)

    @pytest.mark.asyncio
    async def test_normal_movement_after_collapse_has_single_cell_bounds(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["a", "b", "c"],
                [(1, 2, 3)],
            )

            await pilot.press("v", "l", "semicolon", "l")
            await pilot.pause()

            table = app.results_table
            assert table.cursor_coordinate == (0, 2)
            assert table.results_selection_bounds() == (0, 0, 2, 2)

    @pytest.mark.asyncio
    async def test_external_cursor_move_collapses_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["a", "b"],
                [(1, 2), (3, 4)],
            )
            await pilot.press("x")
            table = app.results_table

            table.cursor_coordinate = Coordinate(1, 0)
            await pilot.pause()

            assert not table.results_selection_active
            assert table.results_selection_bounds() == (1, 1, 0, 0)

    @pytest.mark.asyncio
    async def test_row_to_rectangle_uses_logical_head_column(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["a", "b", "c"],
                [(1, 2, 3), (4, 5, 6)],
            )

            await pilot.press("l", "x", "v")
            await pilot.pause()

            table = app.results_table
            assert table.results_selection_mode == "rectangle"
            assert table.results_selection_bounds() == (0, 0, 1, 1)

    @pytest.mark.asyncio
    async def test_y_copies_selected_raw_rectangle(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["name", "value"],
                [("[bold]Ada", None), ("Linus", "a\tb")],
            )

            await pilot.press("v", "l", "j", "y")
            await pilot.pause()

            assert app._internal_clipboard == "[bold]Ada\tNULL\nLinus\ta b"
            assert app.results_table.results_selection_active

    @pytest.mark.asyncio
    async def test_filtered_selection_copies_raw_values(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            rows = [("[bold]Ada", None), ("Linus", "other")]
            await _populate_results(pilot, app, ["name", "value"], rows)
            app._results_filter_fuzzy = False
            app._rebuild_results_with_matches([rows[0]], "Ada")
            await pilot.pause()
            app.action_focus_results()

            await pilot.press("v", "l", "y")
            await pilot.pause()

            assert app.results_table.result_raw_rows == [rows[0]]
            assert app._internal_clipboard == "[bold]Ada\tNULL"

    @pytest.mark.asyncio
    async def test_ge_extends_active_rectangle_to_last_row(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name"],
                [(1, "Ada"), (2, "Linus"), (3, "Grace")],
            )

            await pilot.press("v", "g", "e")
            await pilot.pause()

            assert app.results_table.results_selection_bounds() == (0, 2, 0, 0)

    @pytest.mark.asyncio
    async def test_multirow_delete_is_blocked(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name"],
                [(1, "Ada"), (2, "Linus")],
            )

            await pilot.press("x", "x", "d")
            await pilot.pause()

            assert app.query_input.text == ""
            assert app.results_table.results_selection_active

    @pytest.mark.asyncio
    async def test_multicell_update_is_blocked(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name"],
                [(1, "Ada"), (2, "Linus")],
            )

            await pilot.press("v", "l", "r")
            await pilot.pause()

            assert app.query_input.text == ""
            assert app.results_table.results_selection_active

    @pytest.mark.asyncio
    async def test_new_results_reset_selection(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await _populate_results(
                pilot,
                app,
                ["id", "name"],
                [(1, "Ada"), (2, "Linus")],
            )
            await pilot.press("v", "l")
            assert app.results_table.results_selection_active

            await app._display_query_results(
                columns=["id"],
                rows=[(3,)],
                row_count=1,
                truncated=False,
                elapsed_ms=0,
            )
            await pilot.pause()

            assert not app.results_table.results_selection_active
            assert app.results_table.result_raw_rows == [(3,)]
