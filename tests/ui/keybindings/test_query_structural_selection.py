"""UI tests for syntax-aware query selections."""

from __future__ import annotations

import pytest
from textual.widgets import OptionList, Static

from sqlit.domains.query.ui.screens import SyntaxObjectPickerScreen
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services

SQL = "SELECT foo, bar FROM widgets;"
INCOMPLETE_JOIN_SQL = '''with cte as (SELECT *
FROM "orders"
LIMIT 100)
select *
from (
  select *
  from cte
)
left join on 1=1
where true or 1 and not false 
'''


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


@pytest.mark.parametrize(
    ("sql", "column", "key", "expected"),
    [
        (
            "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent;",
            25,
            "e",
            ((0, 5), (0, 38)),
        ),
        (
            "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent;",
            25,
            "E",
            ((0, 16), (0, 37)),
        ),
        (
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders);",
            43,
            "q",
            ((0, 32), (0, 60)),
        ),
        (
            "SELECT first_name, last_name FROM users;",
            10,
            "l",
            ((0, 7), (0, 28)),
        ),
        (
            "SELECT * FROM users WHERE active = TRUE;",
            31,
            "c",
            ((0, 20), (0, 39)),
        ),
        (
            "SELECT * FROM users u JOIN teams t ON t.id = u.team_id;",
            43,
            "j",
            ((0, 38), (0, 54)),
        ),
        (
            "SELECT * FROM schema.widgets AS w;",
            23,
            "t",
            ((0, 14), (0, 33)),
        ),
        (
            "SELECT 1; SELECT 2;",
            12,
            "S",
            ((0, 10), (0, 19)),
        ),
    ],
)
@pytest.mark.asyncio
async def test_match_menu_selects_semantic_sql_ranges(
    sql: str,
    column: int,
    key: str,
    expected: tuple[tuple[int, int], tuple[int, int]],
) -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = sql
        app._set_normal_selection((0, column))

        await pilot.press("m", key)

        assert app._ordered_selection(app.query_input.selection) == expected


@pytest.mark.parametrize(
    ("position", "key", "expected"),
    [
        ((8, 14), "j", ((8, 13), (8, 16))),
        ((9, 10), "c", ((9, 0), (9, 29))),
        ((4, 2), "t", ((4, 5), (7, 1))),
        ((8, 5), "S", ((0, 0), (9, 29))),
    ],
)
@pytest.mark.asyncio
async def test_match_menu_recovers_ranges_from_incomplete_join(
    position: tuple[int, int],
    key: str,
    expected: tuple[tuple[int, int], tuple[int, int]],
) -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = INCOMPLETE_JOIN_SQL
        app._set_normal_selection(position)

        await pilot.press("m", key)

        assert app._ordered_selection(app.query_input.selection) == expected


@pytest.mark.asyncio
async def test_syntax_picker_lists_objects_from_the_outer_statement() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = INCOMPLETE_JOIN_SQL
        app._set_normal_selection((1, 8))

        await pilot.press("alt+s")

        assert isinstance(app.screen, SyntaxObjectPickerScreen)
        option_list = app.screen.query_one("#syntax-object-picker-list", OptionList)
        assert option_list.option_count == 13
        preview = app.screen.query_one("#syntax-object-picker-preview", Static)
        assert "left join on 1=1" in str(preview.content)


@pytest.mark.asyncio
async def test_syntax_picker_filters_and_selects_join_condition() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = INCOMPLETE_JOIN_SQL
        app._set_normal_selection((1, 8))
        original = app._query_selection

        await pilot.press("alt+s", "j", "o", "i", "n")
        option_list = app.screen.query_one("#syntax-object-picker-list", OptionList)
        assert option_list.option_count == 1
        preview = app.screen.query_one("#syntax-object-picker-preview", Static)
        assert str(preview.content) == "1=1"
        assert app._query_selection == original

        await pilot.press("enter")
        await pilot.pause()

        assert app._ordered_selection(app.query_input.selection) == ((8, 13), (8, 16))


@pytest.mark.asyncio
async def test_cancelling_syntax_picker_preserves_selection() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = SQL
        app._set_normal_selection((0, 8))
        original = app._query_selection

        await pilot.press("alt+s", "escape")

        assert app._query_selection == original
