"""Strict SQLGlot-backed semantic query analysis."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import replace
from typing import TYPE_CHECKING, TypeVar

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

from sqlit.domains.query.app.query_analysis import (
    AliasKind,
    AliasReference,
    ColumnReference,
    CteDefinition,
    DefinitionKind,
    DefinitionLink,
    QualifiedName,
    SemanticDiagnostic,
    SemanticSnapshot,
    SemanticStatus,
    SyntaxRange,
    TableReference,
    TableReferenceKind,
)
from sqlit.domains.query.editing import Position

if TYPE_CHECKING:
    from collections.abc import Iterable

_Key = TypeVar("_Key")
_Value = TypeVar("_Value")


class SQLGlotSemanticBackend:
    """Convert strict SQLGlot parses into immutable application values."""

    def analyze(self, text: str, dialect: str) -> SemanticSnapshot:
        try:
            expressions = sqlglot.parse(text, read=dialect, error_level=ErrorLevel.RAISE)
            return self._extract(text, dialect, expressions)
        except (SqlglotError, ValueError) as error:
            return SemanticSnapshot(
                parser_version=sqlglot.__version__,
                dialect=dialect,
                status=SemanticStatus.UNAVAILABLE,
                diagnostics=(SemanticDiagnostic(self._error_message(error)),),
            )

    @staticmethod
    def _error_message(error: Exception) -> str:
        details = getattr(error, "errors", None)
        if details:
            descriptions = [item.get("description") for item in details]
            message = "; ".join(value for value in descriptions if value)
            if message:
                return message
        return str(error).splitlines()[0]

    def _extract(
        self,
        text: str,
        dialect: str,
        expressions: list[exp.Expression | None],
    ) -> SemanticSnapshot:
        self._line_offsets = self._build_line_offsets(text)
        self._text_length = len(text)
        tables: list[TableReference] = []
        columns: list[ColumnReference] = []
        aliases: list[AliasReference] = []
        ctes: list[CteDefinition] = []
        definitions: list[DefinitionLink] = []

        for statement_index, expression in enumerate(expressions):
            if expression is None:
                continue
            self._extract_statement(
                expression,
                statement_index,
                tables,
                columns,
                aliases,
                ctes,
                definitions,
            )

        indexed_tables = sorted(
            enumerate(tables),
            key=lambda item: self._value_sort_key(item[1]),
        )
        table_indexes = {old_index: new_index for new_index, (old_index, _table) in enumerate(indexed_tables)}
        ordered_columns = sorted(columns, key=self._value_sort_key)

        return SemanticSnapshot(
            parser_version=sqlglot.__version__,
            dialect=dialect,
            status=SemanticStatus.EXACT,
            tables=tuple(table for _old_index, table in indexed_tables),
            columns=tuple(
                replace(
                    column,
                    resolved_table=table_indexes[column.resolved_table],
                )
                if column.resolved_table is not None
                else column
                for column in ordered_columns
            ),
            aliases=tuple(sorted(aliases, key=self._value_sort_key)),
            ctes=tuple(sorted(ctes, key=self._value_sort_key)),
            definitions=tuple(sorted(definitions, key=self._definition_sort_key)),
        )

    def _extract_statement(
        self,
        expression: exp.Expression,
        statement_index: int,
        tables: list[TableReference],
        columns: list[ColumnReference],
        aliases: list[AliasReference],
        ctes: list[CteDefinition],
        definitions: list[DefinitionLink],
    ) -> None:
        scopes = traverse_scope(expression)
        scope_indexes = {id(scope): index for index, scope in enumerate(scopes)}
        expression_scope_indexes = {id(scope.expression): index for index, scope in enumerate(scopes)}
        parent_scope_indexes = {index: scope_indexes.get(id(scope.parent), -1) for index, scope in enumerate(scopes)}
        cte_ids: dict[int, int] = {}

        for cte in expression.find_all(exp.CTE):
            cte_id = len(ctes)
            cte_ids[id(cte)] = cte_id
            body_scope = next(
                (scope for scope in scopes if scope.expression is cte.this),
                None,
            )
            with_node = cte.find_ancestor(exp.With)
            alias_identifier = self._alias_identifier(cte)
            ctes.append(
                CteDefinition(
                    id=cte_id,
                    statement=statement_index,
                    scope=scope_indexes.get(id(body_scope), -1),
                    name=cte.alias,
                    columns=tuple(cte.alias_column_names),
                    recursive=bool(with_node and with_node.args.get("recursive")),
                    range=self._range(cte, "cte"),
                    name_range=self._range(alias_identifier, "cte_name") if alias_identifier is not None else None,
                )
            )

        seen_tables: set[int] = set()
        table_by_scope_alias: dict[tuple[int, str], int] = {}
        relation_aliases: dict[tuple[int, tuple[str, bool]], tuple[str, SyntaxRange]] = {}
        cte_sources: dict[tuple[int, tuple[str, bool]], tuple[str, SyntaxRange]] = {}
        for scope_index, scope in enumerate(scopes):
            for source_alias, (reference, source) in scope.selected_sources.items():
                kind = TableReferenceKind.TABLE
                cte_id = None
                if isinstance(source, Scope):
                    kind = TableReferenceKind.CTE if source.is_cte else TableReferenceKind.DERIVED
                    if not source.is_cte and isinstance(reference.parent, exp.Subquery):
                        reference = reference.parent
                    definition = source.expression.find_ancestor(exp.CTE)
                    cte_id = cte_ids.get(id(definition)) if definition is not None else None
                elif isinstance(source, exp.Table) and not isinstance(source.this, exp.Identifier):
                    kind = TableReferenceKind.TABLE_FUNCTION

                table_index = self._add_table(
                    reference,
                    statement_index,
                    scope_index,
                    kind,
                    cte_id,
                    tables,
                    aliases,
                )
                seen_tables.add(id(reference))
                table_by_scope_alias[(scope_index, source_alias)] = table_index
                alias_identifier = self._alias_identifier(reference)
                alias_range = self._range(alias_identifier, "relation_alias") if alias_identifier is not None else None
                if alias_identifier is not None and alias_range is not None:
                    relation_aliases[(scope_index, self._identifier_key(alias_identifier))] = (alias_identifier.name, alias_range)

                if cte_id is not None and isinstance(reference, exp.Table):
                    cte_definition = next(
                        (item for item in ctes if item.id == cte_id),
                        None,
                    )
                    reference_identifier = reference.this
                    reference_range = self._range(reference_identifier, "cte_reference") if isinstance(reference_identifier, exp.Identifier) else None
                    if cte_definition is not None and cte_definition.name_range is not None and reference_range is not None:
                        if alias_identifier is None and isinstance(reference_identifier, exp.Identifier):
                            cte_sources[(scope_index, self._identifier_key(reference_identifier))] = (
                                cte_definition.name,
                                cte_definition.name_range,
                            )
                        definitions.append(
                            DefinitionLink(
                                statement=statement_index,
                                scope=scope_index,
                                name=cte_definition.name,
                                kind=DefinitionKind.CTE,
                                reference=reference_range,
                                definition=cte_definition.name_range,
                            )
                        )

        for table in expression.find_all(exp.Table):
            if id(table) in seen_tables:
                continue
            self._add_table(
                table,
                statement_index,
                -1,
                TableReferenceKind.TABLE,
                None,
                tables,
                aliases,
            )

        projection_aliases: dict[tuple[int, tuple[str, bool]], tuple[str, SyntaxRange]] = {}
        for scope_index, scope in enumerate(scopes):
            select = scope.expression if isinstance(scope.expression, exp.Select) else None
            if select is None:
                continue
            for projection in select.selects:
                if not isinstance(projection, exp.Alias):
                    continue
                alias = projection.args.get("alias")
                if not isinstance(alias, exp.Identifier):
                    continue
                alias_range = self._range(alias, "projection_alias")
                aliases.append(
                    AliasReference(
                        statement=statement_index,
                        scope=scope_index,
                        name=alias.name,
                        kind=AliasKind.PROJECTION,
                        range=alias_range,
                    )
                )
                if alias_range is not None:
                    projection_aliases[(scope_index, self._identifier_key(alias))] = (
                        alias.name,
                        alias_range,
                    )

        seen_columns: set[int] = set()
        for scope_index, scope in enumerate(scopes):
            for column in scope.columns:
                if id(column) in seen_columns:
                    continue
                seen_columns.add(id(column))
                source_alias = column.table or None
                columns.append(
                    ColumnReference(
                        statement=statement_index,
                        scope=scope_index,
                        name=self._qualified_name(column.parts),
                        source_alias=source_alias,
                        resolved_table=self._scope_lookup(
                            table_by_scope_alias,
                            parent_scope_indexes,
                            scope_index,
                            source_alias,
                        )
                        if source_alias
                        else None,
                        is_star=column.is_star,
                        range=self._range(column, "column"),
                    )
                )
                qualifier = column.args.get("table")
                reference_range = self._range(qualifier, "relation_alias_reference") if isinstance(qualifier, exp.Identifier) else None
                alias_definition = (
                    self._scope_lookup(
                        relation_aliases,
                        parent_scope_indexes,
                        scope_index,
                        self._identifier_key(qualifier),
                    )
                    if isinstance(qualifier, exp.Identifier)
                    else None
                )
                definition_kind = DefinitionKind.RELATION_ALIAS
                if alias_definition is None and isinstance(qualifier, exp.Identifier):
                    alias_definition = self._scope_lookup(
                        cte_sources,
                        parent_scope_indexes,
                        scope_index,
                        self._identifier_key(qualifier),
                    )
                    definition_kind = DefinitionKind.CTE
                if alias_definition is not None and reference_range is not None:
                    name, definition_range = alias_definition
                    definitions.append(
                        DefinitionLink(
                            statement=statement_index,
                            scope=scope_index,
                            name=name,
                            kind=definition_kind,
                            reference=reference_range,
                            definition=definition_range,
                        )
                    )

        self._add_projection_definition_links(
            expression,
            statement_index,
            expression_scope_indexes,
            projection_aliases,
            definitions,
        )

    def _add_projection_definition_links(
        self,
        expression: exp.Expression,
        statement: int,
        scope_indexes: dict[int, int],
        aliases: dict[tuple[int, tuple[str, bool]], tuple[str, SyntaxRange]],
        definitions: list[DefinitionLink],
    ) -> None:
        clause_types = (exp.Order, exp.Group, exp.Having, exp.Qualify)
        for column in expression.find_all(exp.Column):
            if column.table:
                continue
            select = column.find_ancestor(exp.Select)
            clause = next(
                (candidate for clause_type in clause_types if (candidate := column.find_ancestor(clause_type)) is not None),
                None,
            )
            if clause is None or clause.find_ancestor(exp.Select) is not select:
                continue
            scope = scope_indexes.get(id(select), -1)
            identifier = column.this
            if not isinstance(identifier, exp.Identifier):
                continue
            alias_definition = aliases.get((scope, self._identifier_key(identifier)))
            reference_range = self._range(identifier, "projection_alias_reference")
            if alias_definition is None or reference_range is None:
                continue
            name, definition_range = alias_definition
            definitions.append(
                DefinitionLink(
                    statement=statement,
                    scope=scope,
                    name=name,
                    kind=DefinitionKind.PROJECTION_ALIAS,
                    reference=reference_range,
                    definition=definition_range,
                )
            )

    def _add_table(
        self,
        reference: exp.Expression,
        statement: int,
        scope: int,
        kind: TableReferenceKind,
        cte_id: int | None,
        tables: list[TableReference],
        aliases: list[AliasReference],
    ) -> int:
        alias_name = reference.alias or None
        if isinstance(reference, exp.Table):
            name = self._qualified_name(reference.parts)
        else:
            name = QualifiedName(
                (alias_name,) if alias_name else (),
                (False,) if alias_name else (),
            )
        table_index = len(tables)
        tables.append(
            TableReference(
                statement=statement,
                scope=scope,
                name=name,
                alias=alias_name,
                kind=kind,
                cte_id=cte_id,
                range=self._range(reference, "table_reference"),
            )
        )

        alias = reference.args.get("alias")
        identifier = alias.this if isinstance(alias, exp.TableAlias) else None
        if isinstance(identifier, exp.Identifier):
            aliases.append(
                AliasReference(
                    statement=statement,
                    scope=scope,
                    name=identifier.name,
                    kind=AliasKind.RELATION,
                    range=self._range(identifier, "relation_alias"),
                )
            )
        return table_index

    @staticmethod
    def _qualified_name(parts: Iterable[exp.Expression]) -> QualifiedName:
        identifiers = tuple(part for part in parts if isinstance(part, exp.Identifier))
        return QualifiedName(
            parts=tuple(part.name for part in identifiers),
            quoted=tuple(part.quoted for part in identifiers),
        )

    @staticmethod
    def _alias_identifier(expression: exp.Expression) -> exp.Identifier | None:
        alias = expression.args.get("alias")
        identifier = alias.this if isinstance(alias, exp.TableAlias) else alias
        return identifier if isinstance(identifier, exp.Identifier) else None

    @staticmethod
    def _identifier_key(identifier: exp.Identifier) -> tuple[str, bool]:
        return (
            identifier.name if identifier.quoted else identifier.name.casefold(),
            identifier.quoted,
        )

    @staticmethod
    def _scope_lookup(
        values: dict[tuple[int, _Key], _Value],
        parents: dict[int, int],
        scope: int,
        key: _Key,
    ) -> _Value | None:
        while scope >= 0:
            value = values.get((scope, key))
            if value is not None:
                return value
            scope = parents.get(scope, -1)
        return None

    def _range(self, expression: exp.Expression, kind: str) -> SyntaxRange | None:
        positions = [(start, end) for node in expression.walk() if isinstance((start := node.meta_get("start")), int) and isinstance((end := node.meta_get("end")), int)]
        if not positions:
            return None
        start = min(value[0] for value in positions)
        end = max(value[1] for value in positions) + 1
        return SyntaxRange(
            self._offset_to_position(start),
            self._offset_to_position(end),
            kind,
        )

    @staticmethod
    def _build_line_offsets(text: str) -> list[int]:
        offsets = [0]
        offsets.extend(index + 1 for index, char in enumerate(text) if char == "\n")
        return offsets

    def _offset_to_position(self, offset: int) -> Position:
        offset = min(max(offset, 0), self._text_length)
        row = max(0, bisect_right(self._line_offsets, offset) - 1)
        return Position(row, offset - self._line_offsets[row])

    @staticmethod
    def _value_sort_key(value: object) -> tuple[int, int, int, int]:
        range_value = getattr(value, "range", None)
        if range_value is None:
            return (1, 0, 0, 0)
        return (
            0,
            range_value.start.row,
            range_value.start.col,
            range_value.end.col,
        )

    @staticmethod
    def _definition_sort_key(value: DefinitionLink) -> tuple[int, int, int]:
        return (
            value.reference.start.row,
            value.reference.start.col,
            value.reference.end.col,
        )
