"""Helix multiple-selection editing through real key events."""

import pytest

from sqlit.core.vim import VimMode

from .test_vim_motions import _make_app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (["C", "C", "i", "X", "escape"], "Xfoo\nXbar\nXbaz"),
        (["C", "l", "d"], "fo\nbr\nbaz"),
        (["C", "c", "X", "escape"], "Xoo\nXar\nbaz"),
        (["C", "w", "d"], "baz"),
        (["C", "r", "X"], "Xoo\nXar\nbaz"),
        (["C", "ctrl+c"], "-- foo\n-- bar\nbaz"),
        (["C", "ctrl+c", "ctrl+c"], "foo\nbar\nbaz"),
        (["C", "i", "X", "backspace", "escape"], "foo\nbar\nbaz"),
        (["C", "a", "X", "escape"], "fXoo\nbXar\nbaz"),
        (["C", "A", "X", "escape"], "fooX\nbarX\nbaz"),
        (["C", "i", "right", "X", "escape"], "fXoo\nbXar\nbaz"),
        (["C", "v", "l", "d"], "o\nr\nbaz"),
        (["C", "m", "i", "w", "c", "X", "escape"], "X\nX\nbaz"),
        (["C", "x", "d"], "baz"),
        (["C", "o", "X", "escape"], "foo\nX\nbar\nX\nbaz"),
        (["C", "O", "X", "escape"], "X\nfoo\nX\nbar\nbaz"),
    ],
)
async def test_multicursor_edits(keys, expected):
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar\nbaz"
        app._set_normal_selection((0, 0))
        await pilot.press(*keys)
        await pilot.pause()
        assert app.query_input.text == expected
        assert app.vim_mode == VimMode.NORMAL
        if expected != "baz":  # Adjacent deletions can merge cursors.
            assert app._query_selection.secondary


@pytest.mark.asyncio
async def test_undo_redo_restores_all_cursors():
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar"
        app._set_normal_selection((0, 0))
        await pilot.press("C")
        before = app._query_selection
        await pilot.press("d", "u")
        assert app.query_input.text == "foo\nbar"
        assert app._query_selection == before
        await pilot.press("ctrl+r")
        assert app.query_input.text == "oo\nar"
        assert app._query_selection.secondary
        await pilot.press("escape")
        assert not app._query_selection.secondary


@pytest.mark.asyncio
async def test_comment_in_insert_mode():
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "  select 1;"
        app._set_normal_selection((0, 2))
        await pilot.press("i", "ctrl+c")
        assert app.query_input.text == "  -- select 1;"
        assert app.vim_mode == VimMode.INSERT


@pytest.mark.asyncio
async def test_cursor_count_and_eof_do_not_duplicate():
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar\nbaz"
        app._set_normal_selection((0, 0))
        await pilot.press("2", "C", "C", "C")
        assert len(app._query_selections()) == 3
        await pilot.press("2", "l")
        assert [selection.logical_cursor for selection in app._query_selections()] == [(0, 2), (1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_comment_overlapping_line_ranges_once():
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar\nbaz"
        app._set_normal_selection((0, 0))
        await pilot.press("v", "j", "C", "ctrl+c")
        assert app.query_input.text == "-- foo\n-- bar\n-- baz"
        await pilot.press("ctrl+c")
        assert app.query_input.text == "foo\nbar\nbaz"


@pytest.mark.asyncio
async def test_multicursor_terminal_paste_and_newlines():
    from textual.events import Paste

    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar"
        app._set_normal_selection((0, 0))
        await pilot.press("C", "i")
        app.query_input.post_message(Paste("X\nY"))
        await pilot.pause()
        assert app.query_input.text == "X\nYfoo\nX\nYbar"
        assert [selection.logical_cursor for selection in app._query_selections()] == [(1, 1), (3, 1)]


@pytest.mark.asyncio
async def test_empty_primary_does_not_prevent_changing_other_selections():
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\n"
        app._set_normal_selection((0, 0))
        await pilot.press("C", "c", "X", "escape")
        assert app.query_input.text == "Xoo\nX"


@pytest.mark.asyncio
async def test_yank_and_paste_all_selections(monkeypatch):
    app = _make_app()
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_focus_query()
        app.query_input.text = "foo\nbar"
        app._set_normal_selection((0, 0))
        copied = []
        monkeypatch.setattr(app, "_copy_text", copied.append)
        await pilot.press("C", "y")
        assert copied == ["f\nb"]
        monkeypatch.setattr(app, "_get_clipboard_text", lambda: "X")
        await pilot.press("p")
        assert app.query_input.text == "fXoo\nbXar"
