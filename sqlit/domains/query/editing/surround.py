"""Selection surround editing helpers."""

from __future__ import annotations

from dataclasses import dataclass

SURROUND_PAIRS = {
    "(": ("(", ")"),
    ")": ("(", ")"),
    "b": ("(", ")"),
    "[": ("[", "]"),
    "]": ("[", "]"),
    "{": ("{", "}"),
    "}": ("{", "}"),
    "B": ("{", "}"),
    "<": ("<", ">"),
    ">": ("<", ">"),
    "'": ("'", "'"),
    '"': ('"', '"'),
    "`": ("`", "`"),
}


@dataclass(frozen=True)
class SurroundResult:
    """Text and preserved payload range after a surround edit."""

    text: str
    start: int
    end: int


def add_surround(text: str, start: int, end: int, delimiter: str) -> SurroundResult | None:
    """Wrap the selected range and keep its payload selected."""
    pair = SURROUND_PAIRS.get(delimiter)
    if pair is None or not _valid_range(text, start, end):
        return None

    opening, closing = pair
    return SurroundResult(
        text[:start] + opening + text[start:end] + closing + text[end:],
        start + len(opening),
        end + len(opening),
    )


def delete_surround(text: str, start: int, end: int, delimiter: str) -> SurroundResult | None:
    """Delete the nearest requested pair enclosing the selected range."""
    pair = SURROUND_PAIRS.get(delimiter)
    if pair is None or not _valid_range(text, start, end):
        return None

    bounds = _find_enclosing_pair(text, start, end, *pair)
    if bounds is None:
        return None

    opening_at, closing_at = bounds
    inner_start = max(start, opening_at + 1)
    inner_end = min(end, closing_at)
    return SurroundResult(
        text[:opening_at] + text[opening_at + 1 : closing_at] + text[closing_at + 1 :],
        inner_start - 1,
        inner_end - 1,
    )


def replace_surround(
    text: str,
    start: int,
    end: int,
    old_delimiter: str,
    new_delimiter: str,
) -> SurroundResult | None:
    """Replace the nearest requested pair enclosing the selected range."""
    old_pair = SURROUND_PAIRS.get(old_delimiter)
    new_pair = SURROUND_PAIRS.get(new_delimiter)
    if old_pair is None or new_pair is None or not _valid_range(text, start, end):
        return None

    bounds = _find_enclosing_pair(text, start, end, *old_pair)
    if bounds is None:
        return None

    opening_at, closing_at = bounds
    inner_start = max(start, opening_at + 1)
    inner_end = min(end, closing_at)
    opening, closing = new_pair
    return SurroundResult(
        text[:opening_at] + opening + text[opening_at + 1 : closing_at] + closing + text[closing_at + 1 :],
        inner_start,
        inner_end,
    )


def _valid_range(text: str, start: int, end: int) -> bool:
    return 0 <= start <= end <= len(text)


def _find_enclosing_pair(text: str, start: int, end: int, opening: str, closing: str) -> tuple[int, int] | None:
    target_end = max(start, end - 1)
    pairs = _quote_pairs(text, opening) if opening == closing else _bracket_pairs(text, opening, closing)
    candidates = [pair for pair in pairs if pair[0] <= start and pair[1] >= target_end]
    return max(candidates, key=lambda pair: pair[0], default=None)


def _bracket_pairs(text: str, opening: str, closing: str) -> list[tuple[int, int]]:
    stack: list[int] = []
    pairs: list[tuple[int, int]] = []
    for offset, character in enumerate(text):
        if character == opening:
            stack.append(offset)
        elif character == closing and stack:
            pairs.append((stack.pop(), offset))
    return pairs


def _quote_pairs(text: str, quote: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    opening_at: int | None = None
    offset = 0
    while offset < len(text):
        if text[offset] != quote or _is_backslash_escaped(text, offset):
            offset += 1
            continue
        if opening_at is not None and offset + 1 < len(text) and text[offset + 1] == quote:
            offset += 2
            continue
        if opening_at is None:
            opening_at = offset
        else:
            pairs.append((opening_at, offset))
            opening_at = None
        offset += 1
    return pairs


def _is_backslash_escaped(text: str, offset: int) -> bool:
    backslashes = 0
    offset -= 1
    while offset >= 0 and text[offset] == "\\":
        backslashes += 1
        offset -= 1
    return backslashes % 2 == 1
