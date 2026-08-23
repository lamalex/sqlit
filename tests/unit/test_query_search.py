"""Tests for query-editor literal search."""

from __future__ import annotations

from sqlit.domains.query.editing.search import SearchMatch, find_query_match


def test_forward_search_and_wrap() -> None:
    text = "one two one"

    assert find_query_match(text, "one", 1) == SearchMatch(8, 11)
    assert find_query_match(text, "one", 11) == SearchMatch(0, 3, wrapped=True)


def test_backward_search_and_wrap() -> None:
    text = "one two one"

    assert find_query_match(text, "one", 7, direction=-1) == SearchMatch(0, 3)
    assert find_query_match(text, "one", -1, direction=-1) == SearchMatch(
        8, 11, wrapped=True
    )


def test_search_is_smart_case() -> None:
    text = "select SELECT"

    assert find_query_match(text, "select", 0) == SearchMatch(0, 6)
    assert find_query_match(text, "SELECT", 0) == SearchMatch(7, 13)


def test_multiline_literal_search() -> None:
    text = "SELECT *\nFROM users\nWHERE active"

    assert find_query_match(text, "FROM users", 0) == SearchMatch(9, 19)


def test_matches_crossing_boundary_are_found_after_wrap() -> None:
    assert find_query_match("abcde", "cde", 3) == SearchMatch(2, 5, wrapped=True)
    assert find_query_match("abcde", "cde", 2, direction=-1) == SearchMatch(2, 5)


def test_overlapping_matches_are_distinct() -> None:
    text = "aaa"

    assert find_query_match(text, "aa", 0) == SearchMatch(0, 2)
    assert find_query_match(text, "aa", 1) == SearchMatch(1, 3)


def test_empty_or_missing_search() -> None:
    assert find_query_match("text", "", 0) is None
    assert find_query_match("text", "missing", 0) is None
