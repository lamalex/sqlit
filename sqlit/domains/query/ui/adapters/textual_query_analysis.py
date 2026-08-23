"""Textual syntax-tree adapter for structural query analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets.text_area import SyntaxAwareDocument

from sqlit.domains.query.app.query_analysis import (
    QueryDiagnostic,
    SemanticTarget,
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

    def _semantic_range(self, node: Node, target: SemanticTarget) -> SyntaxRange:
        node_range = self._range(node)
        return SyntaxRange(node_range.start, node_range.end, target.value)

    def _range_between(self, start: Node, end: Node, kind: str) -> SyntaxRange:
        return SyntaxRange(
            self._point_to_position(start.start_point),
            self._point_to_position(end.end_point),
            kind,
        )

    @staticmethod
    def _ancestor(node: Node | None, *types: str) -> Node | None:
        while node is not None:
            if node.type in types:
                return node
            node = node.parent
        return None

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

    def semantic_range(
        self, position: Position, target: SemanticTarget
    ) -> SyntaxRange | None:
        node = self._node_at(position)
        if node is None:
            return None

        if target == SemanticTarget.CTE:
            cte = self._ancestor(node, "cte")
            return self._semantic_range(cte, target) if cte is not None else None

        if target == SemanticTarget.CTE_BODY:
            cte = self._ancestor(node, "cte")
            if cte is None:
                return None
            body = next((child for child in cte.named_children if child.type == "statement"), None)
            return self._semantic_range(body, target) if body is not None else None

        if target == SemanticTarget.SUBQUERY:
            subquery = self._ancestor(node, "subquery")
            return self._semantic_range(subquery, target) if subquery is not None else None

        if target == SemanticTarget.SELECT_LIST:
            select_list = self._ancestor(node, "select_expression")
            return self._semantic_range(select_list, target) if select_list is not None else None

        if target == SemanticTarget.CLAUSE:
            clause = self._ancestor(node, "where", "group_by", "order_by", "limit", "returning")
            if clause is None:
                return None
            if clause.type == "group_by":
                having = next(
                    (child for child in clause.children if child.type == "keyword_having"),
                    None,
                )
                offset = self._location_to_byte(position)
                if having is not None and offset >= having.start_byte:
                    return self._range_between(having, clause, "having")
            clause_range = self._range(clause)
            return SyntaxRange(clause_range.start, clause_range.end, clause.type)

        if target == SemanticTarget.JOIN_CONDITION:
            join = self._ancestor(node, "join")
            if join is None:
                return None
            predicate = join.child_by_field_name("predicate")
            if predicate is None:
                using_index = next(
                    (i for i, child in enumerate(join.children) if child.type == "keyword_using"),
                    None,
                )
                if using_index is not None:
                    predicate = next(
                        (child for child in join.children[using_index + 1 :] if child.is_named),
                        None,
                    )
            return self._semantic_range(predicate, target) if predicate is not None else None

        if target == SemanticTarget.TABLE_EXPRESSION:
            relation = self._ancestor(node, "relation")
            if relation is not None:
                return self._semantic_range(relation, target)
            object_reference = self._ancestor(node, "object_reference")
            if (
                object_reference is not None
                and object_reference.parent is not None
                and object_reference.parent.type == "from"
            ):
                return self._semantic_range(object_reference, target)
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
