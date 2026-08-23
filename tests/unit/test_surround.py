"""Tests for selection surround editing."""

import pytest

from sqlit.domains.query.editing.surround import (
    SurroundResult,
    add_surround,
    delete_surround,
    replace_surround,
)


@pytest.mark.parametrize(
    ("delimiter", "expected"),
    [
        (")", SurroundResult("select (name) from users", 8, 12)),
        ("b", SurroundResult("select (name) from users", 8, 12)),
        ("B", SurroundResult("select {name} from users", 8, 12)),
        ('"', SurroundResult('select "name" from users', 8, 12)),
    ],
)
def test_add_surround_preserves_payload_selection(delimiter: str, expected: SurroundResult) -> None:
    assert add_surround("select name from users", 7, 11, delimiter) == expected


def test_add_surround_supports_multiline_selection() -> None:
    assert add_surround("one\ntwo", 0, 7, "[") == SurroundResult("[one\ntwo]", 1, 8)


def test_delete_surround_uses_nearest_nested_pair() -> None:
    text = "select ((name))"

    assert delete_surround(text, 9, 13, "(") == SurroundResult("select (name)", 8, 12)


def test_delete_surround_excludes_selected_delimiters() -> None:
    assert delete_surround("select (name)", 7, 13, ")") == SurroundResult("select name", 7, 11)


def test_replace_surround_handles_sql_escaped_quotes() -> None:
    text = "select 'it''s fine'"

    assert replace_surround(text, 8, 18, "'", "[") == SurroundResult("select [it''s fine]", 8, 18)


def test_replace_surround_supports_multiline_pair() -> None:
    assert replace_surround("(one\ntwo)", 1, 8, "(", "{") == SurroundResult("{one\ntwo}", 1, 8)


@pytest.mark.parametrize("operation", ["delete", "replace"])
def test_surround_edit_rejects_non_enclosing_pair(operation: str) -> None:
    text = "(one) two"
    result = delete_surround(text, 6, 9, "(") if operation == "delete" else replace_surround(text, 6, 9, "(", "[")

    assert result is None


def test_surround_edit_rejects_unknown_delimiter() -> None:
    assert add_surround("name", 0, 4, "x") is None
    assert delete_surround("(name)", 1, 5, "x") is None
    assert replace_surround("(name)", 1, 5, "(", "x") is None
