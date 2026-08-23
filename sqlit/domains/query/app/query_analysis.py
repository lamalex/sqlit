"""Parser-neutral structural analysis for query text."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from sqlit.domains.query.editing import Position


@dataclass(frozen=True)
class SyntaxRange:
    """A half-open syntax range in editor coordinates."""

    start: Position
    end: Position
    kind: str


class DiagnosticSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"


class SemanticTarget(Enum):
    """SQL concepts addressable by structural selection commands."""

    CTE = "cte"
    CTE_BODY = "cte_body"
    SUBQUERY = "subquery"
    SELECT_LIST = "select_list"
    CLAUSE = "clause"
    JOIN_CONDITION = "join_condition"
    TABLE_EXPRESSION = "table_expression"


@dataclass(frozen=True)
class QueryDiagnostic:
    """A parser-neutral query diagnostic."""

    range: SyntaxRange
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR


class QueryAnalysisBackend(Protocol):
    """Structural syntax capability implemented by a parser adapter."""

    def node_at(self, position: Position) -> SyntaxRange | None: ...

    def statement_at(self, position: Position) -> SyntaxRange | None: ...

    def parent_range(self, selection: SyntaxRange) -> SyntaxRange | None: ...

    def sibling_range(
        self, selection: SyntaxRange, direction: int
    ) -> SyntaxRange | None: ...

    def semantic_range(
        self, position: Position, target: SemanticTarget
    ) -> SyntaxRange | None: ...

    def diagnostics(self) -> tuple[QueryDiagnostic, ...]: ...


class QueryAnalysisService:
    """Expose structural query concepts without exposing parser objects."""

    def __init__(
        self,
        backend: QueryAnalysisBackend,
        *,
        dialect: str | None = None,
    ) -> None:
        self._backend = backend
        self.dialect = dialect

    def node_at(self, position: Position) -> SyntaxRange | None:
        return self._backend.node_at(position)

    def statement_at(self, position: Position) -> SyntaxRange | None:
        return self._backend.statement_at(position)

    def parent_range(self, selection: SyntaxRange) -> SyntaxRange | None:
        return self._backend.parent_range(selection)

    def sibling_range(
        self, selection: SyntaxRange, direction: int
    ) -> SyntaxRange | None:
        if direction == 0:
            return selection
        return self._backend.sibling_range(selection, 1 if direction > 0 else -1)

    def semantic_range(
        self, position: Position, target: SemanticTarget
    ) -> SyntaxRange | None:
        return self._backend.semantic_range(position, target)

    def cte_at(self, position: Position, *, body: bool = False) -> SyntaxRange | None:
        target = SemanticTarget.CTE_BODY if body else SemanticTarget.CTE
        return self.semantic_range(position, target)

    def subquery_at(self, position: Position) -> SyntaxRange | None:
        return self.semantic_range(position, SemanticTarget.SUBQUERY)

    def select_list_at(self, position: Position) -> SyntaxRange | None:
        return self.semantic_range(position, SemanticTarget.SELECT_LIST)

    def clause_at(self, position: Position) -> SyntaxRange | None:
        return self.semantic_range(position, SemanticTarget.CLAUSE)

    def join_condition_at(self, position: Position) -> SyntaxRange | None:
        return self.semantic_range(position, SemanticTarget.JOIN_CONDITION)

    def table_expression_at(self, position: Position) -> SyntaxRange | None:
        return self.semantic_range(position, SemanticTarget.TABLE_EXPRESSION)

    def diagnostics(self) -> tuple[QueryDiagnostic, ...]:
        return self._backend.diagnostics()
