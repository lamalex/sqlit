"""Pure planning for conservative semantic SQL renames."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from sqlit.domains.query.app.query_analysis import SemanticSymbol, SyntaxRange
from sqlit.domains.query.editing import Position

_BARE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*\Z")


class RenameError(ValueError):
    """Raised when a semantic rename cannot be constructed safely."""


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int


@dataclass(frozen=True)
class TextReplacement:
    start: int
    end: int
    text: str
    declaration: bool


@dataclass(frozen=True)
class RenamePlan:
    text: str
    symbol: SemanticSymbol
    new_name: str
    replacements: tuple[TextReplacement, ...]
    declaration: TextSpan
    references: tuple[TextSpan, ...]

    @property
    def occurrence_count(self) -> int:
        return len(self.replacements)


def position_to_offset(text: str, position: Position) -> int:
    lines = text.split("\n")
    row = min(max(position.row, 0), len(lines) - 1)
    col = min(max(position.col, 0), len(lines[row]))
    return sum(len(value) + 1 for value in lines[:row]) + col


def offset_to_position(text: str, offset: int) -> Position:
    offset = min(max(offset, 0), len(text))
    before = text[:offset]
    row = before.count("\n")
    line_start = before.rfind("\n") + 1
    return Position(row, offset - line_start)


def syntax_range_to_span(text: str, value: SyntaxRange) -> TextSpan:
    return TextSpan(
        position_to_offset(text, value.start),
        position_to_offset(text, value.end),
    )


def build_rename_plan(
    text: str,
    symbol: SemanticSymbol,
    new_name: str,
) -> RenamePlan:
    if not new_name or "\n" in new_name or "\r" in new_name or "\x00" in new_name:
        raise RenameError("Enter a non-empty single-line identifier")
    if new_name == symbol.name:
        raise RenameError("The SQL symbol already has that name")

    declaration_span = syntax_range_to_span(text, symbol.declaration)
    ranges = [(symbol.declaration, True), *((value, False) for value in symbol.references)]
    replacements: list[TextReplacement] = []
    seen: set[TextSpan] = set()
    for value, is_declaration in ranges:
        span = syntax_range_to_span(text, value)
        if span in seen:
            continue
        seen.add(span)
        source = text[span.start : span.end]
        replacements.append(
            TextReplacement(
                span.start,
                span.end,
                _replacement_spelling(source, new_name),
                is_declaration,
            )
        )
    replacements.sort(key=lambda item: item.start)
    for previous, current in pairwise(replacements):
        if previous.end > current.start:
            raise RenameError("Semantic rename ranges overlap")

    candidate = text
    for replacement in reversed(replacements):
        candidate = candidate[: replacement.start] + replacement.text + candidate[replacement.end :]

    delta = 0
    renamed_declaration: TextSpan | None = None
    renamed_references: list[TextSpan] = []
    for replacement in replacements:
        start = replacement.start + delta
        span = TextSpan(start, start + len(replacement.text))
        if replacement.declaration and TextSpan(replacement.start, replacement.end) == declaration_span:
            renamed_declaration = span
        else:
            renamed_references.append(span)
        delta += len(replacement.text) - (replacement.end - replacement.start)

    if renamed_declaration is None:
        raise RenameError("SQL symbol declaration is unavailable")
    return RenamePlan(
        text=candidate,
        symbol=symbol,
        new_name=new_name,
        replacements=tuple(replacements),
        declaration=renamed_declaration,
        references=tuple(renamed_references),
    )


def _replacement_spelling(source: str, new_name: str) -> str:
    if len(source) >= 2 and source[0] == source[-1] == '"':
        return f'"{new_name.replace(chr(34), chr(34) * 2)}"'
    if len(source) >= 2 and source[0] == source[-1] == "`":
        return f"`{new_name.replace('`', '``')}`"
    if len(source) >= 2 and source[0] == "[" and source[-1] == "]":
        return f"[{new_name.replace(']', ']]')}]"
    if not _BARE_IDENTIFIER.fullmatch(new_name):
        raise RenameError("Unquoted SQL identifiers may contain only letters, digits, _, or $")
    return new_name
