"""Textual syntax-tree adapter for structural query analysis."""

from __future__ import annotations

import re
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


_CLAUSE_RE = re.compile(
    r"\b(?:WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|RETURNING)\b",
    re.IGNORECASE,
)
_JOIN_RE = re.compile(
    r"\b(?:(?:LEFT|RIGHT|FULL|INNER|CROSS|NATURAL)(?:\s+OUTER)?\s+)?JOIN\b",
    re.IGNORECASE,
)
_JOIN_CONDITION_RE = re.compile(r"\b(?:ON|USING)\b", re.IGNORECASE)


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
            while sibling is not None and sibling.type == "ERROR":
                end_node = sibling
                sibling = sibling.next_sibling
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

    def _position_to_offset(self, position: Position) -> int:
        document = self._text_area.document
        lines = document.lines
        row = min(max(position.row, 0), len(lines) - 1)
        col = min(max(position.col, 0), len(lines[row]))
        return sum(len(line) + len(document.newline) for line in lines[:row]) + col

    def _offset_to_position(self, offset: int) -> Position:
        document = self._text_area.document
        remaining = min(max(offset, 0), len(document.text))
        for row, line in enumerate(document.lines):
            if remaining <= len(line):
                return Position(row, remaining)
            remaining -= len(line) + len(document.newline)
        row = len(document.lines) - 1
        return Position(row, len(document.lines[row]))

    def _source_range(self, start: int, end: int, kind: str) -> SyntaxRange | None:
        text = self._text_area.text
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start == end:
            return None
        return SyntaxRange(
            self._offset_to_position(start),
            self._offset_to_position(end),
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
        if node is not None:
            return self._range(node)

        root = self._root_node()
        if root is None:
            return None
        for candidate in reversed(root.named_children):
            if candidate.type != "statement":
                continue
            candidate_range = self._range(candidate)
            if candidate_range.start <= position <= candidate_range.end:
                return candidate_range
        return None

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
                error = self._ancestor(node, "ERROR")
                return self._fallback_clause(position, error) if error is not None else None
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
                return (
                    self._fallback_join_condition(position)
                    if self._ancestor(node, "ERROR") is not None
                    else None
                )
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
                relation_range = self._semantic_range(relation, target)
                text = self._text_area.text
                start = self._position_to_offset(relation_range.start)
                end = self._position_to_offset(relation_range.end)
                if text[start:end].casefold() != "on":
                    return relation_range
                return None
            container = self._ancestor(node, "from", "join")
            if container is not None:
                relation = next(
                    (child for child in container.named_children if child.type == "relation"),
                    None,
                )
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

    def _outer_statement(self, root: Node, node: Node, position: Position) -> Node | None:
        statement = None
        current = node
        while current is not None:
            if current.type == "statement":
                statement = current
            current = current.parent
        if statement is None:
            for candidate in reversed(root.named_children):
                if candidate.type != "statement":
                    continue
                candidate_range = self._range(candidate)
                if candidate_range.start <= position <= candidate_range.end:
                    statement = candidate
                    break
        return statement

    def _semantic_ranges_for_node(self, candidate: Node) -> list[SyntaxRange]:
        values: list[SyntaxRange] = []
        if candidate.type == "cte":
            values.append(self._semantic_range(candidate, SemanticTarget.CTE))
            body = next(
                (child for child in candidate.named_children if child.type == "statement"),
                None,
            )
            if body is not None:
                values.append(self._semantic_range(body, SemanticTarget.CTE_BODY))
        elif candidate.type == "subquery":
            values.append(self._semantic_range(candidate, SemanticTarget.SUBQUERY))
        elif candidate.type == "select_expression":
            values.append(self._semantic_range(candidate, SemanticTarget.SELECT_LIST))
        elif candidate.type in {"where", "order_by", "limit", "returning"}:
            value = self._range(candidate)
            values.append(SyntaxRange(value.start, value.end, candidate.type))
        elif candidate.type == "group_by":
            value = self._range(candidate)
            values.append(SyntaxRange(value.start, value.end, candidate.type))
            having = next(
                (child for child in candidate.children if child.type == "keyword_having"),
                None,
            )
            if having is not None:
                values.append(self._range_between(having, candidate, "having"))
        elif candidate.type == "join":
            value = self.semantic_range(
                self._point_to_position(candidate.start_point),
                SemanticTarget.JOIN_CONDITION,
            )
            if value is not None:
                values.append(value)
        elif candidate.type == "relation":
            value = self._semantic_range(candidate, SemanticTarget.TABLE_EXPRESSION)
            text = self._text_area.text
            start = self._position_to_offset(value.start)
            end = self._position_to_offset(value.end)
            if text[start:end].casefold() != "on":
                values.append(value)
        elif (
            candidate.type == "object_reference"
            and candidate.parent is not None
            and candidate.parent.type == "from"
        ):
            values.append(self._semantic_range(candidate, SemanticTarget.TABLE_EXPRESSION))
        return values

    def semantic_ranges(self, position: Position) -> tuple[SyntaxRange, ...]:
        root = self._root_node()
        node = self._node_at(position)
        if root is None or node is None:
            return ()

        statement = self._outer_statement(root, node, position)
        if statement is None:
            return ()

        scope = self._range(statement)
        ranges: list[SyntaxRange] = [scope]
        seen = {(scope.start, scope.end, scope.kind)}

        def add(value: SyntaxRange | None) -> None:
            if value is None or value.start < scope.start or scope.end < value.end:
                return
            key = (value.start, value.end, value.kind)
            if key not in seen:
                seen.add(key)
                ranges.append(value)

        pending = [statement]
        trailing = statement.next_named_sibling
        while trailing is not None and trailing.type == "ERROR":
            pending.append(trailing)
            trailing = trailing.next_named_sibling

        while pending:
            candidate = pending.pop()
            candidate_range = self._range(candidate)
            if candidate_range.end < scope.start or scope.end < candidate_range.start:
                continue

            for value in self._semantic_ranges_for_node(candidate):
                add(value)

            if candidate.type.startswith("keyword_"):
                error = self._ancestor(candidate, "ERROR")
                if error is not None:
                    add(
                        self._fallback_clause(
                            self._point_to_position(candidate.start_point), error
                        )
                    )

            if candidate.type == "ERROR":
                error_position = self._point_to_position(candidate.start_point)
                add(self._fallback_join_condition(error_position))
                add(self._fallback_clause(error_position, candidate))
            pending.extend(reversed(candidate.named_children))

        priority = {
            "statement": 0,
            "cte": 1,
            "cte_body": 2,
            "subquery": 3,
            "select_list": 4,
            "where": 5,
            "group_by": 5,
            "having": 5,
            "order_by": 5,
            "limit": 5,
            "returning": 5,
            "join_condition": 6,
            "table_expression": 7,
        }
        ranges.sort(
            key=lambda value: (
                priority.get(value.kind, 99),
                value.start.row,
                value.start.col,
                value.end.row,
                value.end.col,
            )
        )
        return tuple(ranges)

    def _fallback_clause(
        self, position: Position, error: Node
    ) -> SyntaxRange | None:
        text = self._text_area.text
        offset = self._position_to_offset(position)
        error_start = self._position_to_offset(self._point_to_position(error.start_point))
        error_end = self._position_to_offset(self._point_to_position(error.end_point))
        matches = list(_CLAUSE_RE.finditer(text, error_start, error_end))
        for index in range(len(matches) - 1, -1, -1):
            match = matches[index]
            if match.start() > offset:
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else error_end
            semicolon = text.find(";", match.end(), end)
            if semicolon >= 0:
                end = semicolon
            if offset <= end:
                kind = match.group(0).casefold().replace(" ", "_")
                return self._source_range(match.start(), end, kind)
        return None

    def _fallback_join_condition(self, position: Position) -> SyntaxRange | None:
        text = self._text_area.text
        offset = self._position_to_offset(position)
        joins = list(_JOIN_RE.finditer(text))
        for join in reversed(joins):
            if join.start() > offset:
                continue
            boundary = _CLAUSE_RE.search(text, join.end())
            end = boundary.start() if boundary is not None else len(text)
            semicolon = text.find(";", join.end(), end)
            if semicolon >= 0:
                end = semicolon
            if offset > end:
                continue
            condition = _JOIN_CONDITION_RE.search(text, join.end(), end)
            if condition is not None:
                return self._source_range(condition.end(), end, "join_condition")
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
