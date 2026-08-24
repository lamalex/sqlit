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


class SemanticStatus(Enum):
    EXACT = "exact"
    UNAVAILABLE = "unavailable"


class TableReferenceKind(Enum):
    TABLE = "table"
    CTE = "cte"
    DERIVED = "derived"
    TABLE_FUNCTION = "table_function"


class AliasKind(Enum):
    RELATION = "relation"
    PROJECTION = "projection"


@dataclass(frozen=True)
class QualifiedName:
    parts: tuple[str, ...]
    quoted: tuple[bool, ...]


@dataclass(frozen=True)
class TableReference:
    statement: int
    scope: int
    name: QualifiedName
    alias: str | None
    kind: TableReferenceKind
    cte_id: int | None
    range: SyntaxRange | None


@dataclass(frozen=True)
class ColumnReference:
    statement: int
    scope: int
    name: QualifiedName
    source_alias: str | None
    resolved_table: int | None
    is_star: bool
    range: SyntaxRange | None


@dataclass(frozen=True)
class AliasReference:
    statement: int
    scope: int
    name: str
    kind: AliasKind
    range: SyntaxRange | None


@dataclass(frozen=True)
class CteDefinition:
    id: int
    statement: int
    scope: int
    name: str
    columns: tuple[str, ...]
    recursive: bool
    range: SyntaxRange | None


@dataclass(frozen=True)
class SemanticDiagnostic:
    message: str


@dataclass(frozen=True)
class SemanticSnapshot:
    parser_version: str
    dialect: str | None
    status: SemanticStatus
    tables: tuple[TableReference, ...] = ()
    columns: tuple[ColumnReference, ...] = ()
    aliases: tuple[AliasReference, ...] = ()
    ctes: tuple[CteDefinition, ...] = ()
    diagnostics: tuple[SemanticDiagnostic, ...] = ()


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

    def sibling_range(self, selection: SyntaxRange, direction: int) -> SyntaxRange | None: ...

    def semantic_range(self, position: Position, target: SemanticTarget) -> SyntaxRange | None: ...

    def semantic_ranges(self, position: Position) -> tuple[SyntaxRange, ...]: ...

    def diagnostics(self) -> tuple[QueryDiagnostic, ...]: ...


class QuerySemanticBackend(Protocol):
    def analyze(self, text: str, dialect: str) -> SemanticSnapshot: ...


class QueryAnalysisService:
    """Expose structural query concepts without exposing parser objects."""

    def __init__(
        self,
        backend: QueryAnalysisBackend,
        *,
        dialect: str | None = None,
        semantic_backend: QuerySemanticBackend | None = None,
    ) -> None:
        self._backend = backend
        self._semantic_backend = semantic_backend
        self.dialect = dialect

    def node_at(self, position: Position) -> SyntaxRange | None:
        return self._backend.node_at(position)

    def statement_at(self, position: Position) -> SyntaxRange | None:
        return self._backend.statement_at(position)

    def parent_range(self, selection: SyntaxRange) -> SyntaxRange | None:
        return self._backend.parent_range(selection)

    def sibling_range(self, selection: SyntaxRange, direction: int) -> SyntaxRange | None:
        if direction == 0:
            return selection
        return self._backend.sibling_range(selection, 1 if direction > 0 else -1)

    def semantic_range(self, position: Position, target: SemanticTarget) -> SyntaxRange | None:
        return self._backend.semantic_range(position, target)

    def semantic_ranges(self, position: Position) -> tuple[SyntaxRange, ...]:
        return self._backend.semantic_ranges(position)

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

    def semantic_snapshot(self, text: str) -> SemanticSnapshot:
        if self._semantic_backend is None or self.dialect is None:
            return SemanticSnapshot(
                parser_version="",
                dialect=self.dialect,
                status=SemanticStatus.UNAVAILABLE,
            )
        return self._semantic_backend.analyze(text, self.dialect)
