"""Literal search helpers for query text."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchMatch:
    start: int
    end: int
    wrapped: bool = False


def find_query_match(
    text: str,
    query: str,
    start: int,
    *,
    direction: int = 1,
) -> SearchMatch | None:
    """Find a smart-case literal match, wrapping at the document boundary."""
    if not text or not query:
        return None

    flags = re.ASCII if any(char.isupper() for char in query) else re.IGNORECASE | re.ASCII
    pattern = re.compile(re.escape(query), flags)
    start = min(max(start, -1), len(text))

    matches: list[re.Match[str]] = []
    offset = 0
    while offset <= len(text):
        match = pattern.search(text, offset)
        if match is None:
            break
        matches.append(match)
        offset = match.start() + 1

    if direction >= 0:
        match = next((candidate for candidate in matches if candidate.start() >= start), None)
        if match is not None:
            return SearchMatch(match.start(), match.end())
        if not matches:
            return None
        match = matches[0]
        return SearchMatch(match.start(), match.end(), wrapped=True)

    match = next(
        (candidate for candidate in reversed(matches) if candidate.start() <= start),
        None,
    )
    if match is not None:
        return SearchMatch(match.start(), match.end())
    if not matches:
        return None
    match = matches[-1]
    return SearchMatch(match.start(), match.end(), wrapped=True)
