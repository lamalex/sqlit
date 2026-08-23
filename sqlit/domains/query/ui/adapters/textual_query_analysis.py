"""Textual syntax-tree adapter for structural query analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets.text_area import SyntaxAwareDocument

from sqlit.domains.query.app.query_analysis import (
    QueryDiagnostic,
    SyntaxRange,
)
from sqlit.domains.query.editing import Position

if TYPE_CHECKING:
    from tree_sitter import Node

    from sqlit.shared.ui.widgets_text_area import QueryTextArea


class TextualQueryAnalysisBackend:
    """Adapt Textual's maintained tree-sitter tree to application ranges."""

    def __init__(self, text_area: QueryTextArea) -> None:
        self._text_area = text_area

    def _document(self) -> SyntaxAwareDocument | None:
        document = self._text_area.document
        return document if isinstance(document, SyntaxAwareDocument) else None

    def _root_node(self) -> Node | None:
        document = self._document()
        if document is None:
            return None
        # Textual has no public root accessor. Keep this compatibility seam local.
        return document._syntax_tree.root_node

    def _location_to_byte(self, position: Position) -> int:
        document = self._text_area.document
        lines = document.lines
        row = min(max(position.row, 0), len(lines) - 1)
        col = min(max(position.col, 0), len(lines[row]))
        newline = document.newline.encode("utf-8")
        preceding = sum(len(line.encode("utf-8")) + len(newline) for line in lines[:row])
        return preceding + len(lines[row][:col].encode("utf-8"))

    def _point_to_position(self, point: tuple[int, int]) -> Position:
        lines = self._text_area.document.lines
        if point[0] >= len(lines):
            row = len(lines) - 1
            return Position(row, len(lines[row]))
        row = max(point[0], 0)
        line = lines[row].encode("utf-8")
        byte_col = min(max(point[1], 0), len(line))
        return Position(row, len(line[:byte_col].decode("utf-8", errors="ignore")))

    def _range(self, node: Node) -> SyntaxRange:
        end_node = node
        if node.type == "statement":
            sibling = node.next_sibling
            if sibling is not None and sibling.type == ";":
                end_node = sibling
        return SyntaxRange(
            start=self._point_to_position(node.start_point),
            end=self._point_to_position(end_node.end_point),
            kind=node.type,
        )

    def _node_at(self, position: Position) -> Node | None:
        root = self._root_node()
        if root is None:
            return None
        offset = self._location_to_byte(position)
        node = root.named_descendant_for_byte_range(offset, offset)
        if node == root and offset > 0:
            node = root.named_descendant_for_byte_range(offset - 1, offset - 1)
        return node

    def _node_for_selection(self, selection: SyntaxRange) -> Node | None:
        node = self._node_at(selection.start)
        while node is not None:
            if self._range(node) == selection:
                return node
            node = node.parent

        root = self._root_node()
        if root is None:
            return None
        start = self._location_to_byte(selection.start)
        end = self._location_to_byte(selection.end)
        return root.named_descendant_for_byte_range(start, max(start, end - 1))

    def node_at(self, position: Position) -> SyntaxRange | None:
        node = self._node_at(position)
        return self._range(node) if node is not None else None

    def statement_at(self, position: Position) -> SyntaxRange | None:
        node = self._node_at(position)
        while node is not None and node.type != "statement":
            node = node.parent
        return self._range(node) if node is not None else None

    def parent_range(self, selection: SyntaxRange) -> SyntaxRange | None:
        node = self._node_for_selection(selection)
        while node is not None:
            node_range = self._range(node)
            if node_range.start != selection.start or node_range.end != selection.end:
                break
            node = node.parent
        return self._range(node) if node is not None else None

    def sibling_range(
        self, selection: SyntaxRange, direction: int
    ) -> SyntaxRange | None:
        node = self._node_for_selection(selection)
        while node is not None:
            sibling = node.next_named_sibling if direction > 0 else node.prev_named_sibling
            if sibling is not None:
                return self._range(sibling)
            node = node.parent
        return None

    def diagnostics(self) -> tuple[QueryDiagnostic, ...]:
        root = self._root_node()
        if root is None or not root.has_error:
            return ()

        diagnostics: list[QueryDiagnostic] = []
        pending = [root]
        while pending:
            node = pending.pop()
            if node.is_error or node.is_missing:
                kind = "missing" if node.is_missing else "error"
                diagnostics.append(
                    QueryDiagnostic(
                        range=self._range(node),
                        message=f"SQL syntax {kind}",
                    )
                )
                continue
            if node.has_error:
                pending.extend(reversed(node.children))
        return tuple(diagnostics)
