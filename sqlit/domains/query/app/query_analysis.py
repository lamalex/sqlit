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

    def diagnostics(self) -> tuple[QueryDiagnostic, ...]:
        return self._backend.diagnostics()
