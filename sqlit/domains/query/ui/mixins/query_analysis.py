"""Query analysis service integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.core.vim import VimMode
from sqlit.domains.query.app.query_analysis import (
    QueryAnalysisService,
    SemanticTarget,
    SyntaxRange,
)
from sqlit.domains.query.editing import Position, QuerySelectionSnapshot
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import QueryMixinHost


class QueryAnalysisMixin:
    """Provide structural analysis for the live query document."""

    _query_analysis_service: QueryAnalysisService | None = None
    _syntax_selection_history: list[tuple[SyntaxRange, QuerySelectionSnapshot]] | None = None
    _syntax_selection_current: SyntaxRange | None = None
    _applying_syntax_selection: bool = False

    def _get_query_analysis_service(self: QueryMixinHost) -> QueryAnalysisService:
        provider = getattr(self, "current_provider", None)
        metadata = getattr(provider, "metadata", None)
        dialect = getattr(metadata, "db_type", None)
        if self._query_analysis_service is None:
            backend = TextualQueryAnalysisBackend(self.query_input)
            self._query_analysis_service = QueryAnalysisService(backend, dialect=dialect)
        else:
            self._query_analysis_service.dialect = dialect
        return self._query_analysis_service

    def _reset_syntax_selection_history(self: QueryMixinHost) -> None:
        if self._syntax_selection_history is not None:
            self._syntax_selection_history.clear()
        self._syntax_selection_current = None

    def _current_syntax_selection(self: QueryMixinHost) -> SyntaxRange:
        start, end = self._ordered_selection(self.query_input.selection)
        return SyntaxRange(Position(*start), Position(*end), "selection")

    def _syntax_selection_base(self: QueryMixinHost) -> SyntaxRange:
        current = self._current_syntax_selection()
        tracked = self._syntax_selection_current
        if tracked is not None and tracked.start == current.start and tracked.end == current.end:
            return tracked
        self._reset_syntax_selection_history()
        return current

    def _apply_syntax_selection(
        self: QueryMixinHost,
        target: SyntaxRange,
        *,
        remember: SyntaxRange | None = None,
    ) -> None:
        if target.start == target.end:
            return
        if remember is not None:
            if self._syntax_selection_history is None:
                self._syntax_selection_history = []
            self._syntax_selection_history.append((remember, self._query_selection))

        start = (target.start.row, target.start.col)
        end = (target.end.row, target.end.col)
        self._applying_syntax_selection = True
        try:
            self._replace_query_selection(
                start=start,
                end=end,
                logical_cursor=self._position_before(end),
                normal_selection_primary=False,
                vim_mode=VimMode.NORMAL,
                visual_anchor=None,
                visual_cursor=None,
                visual_line_anchor_row=None,
                update_chrome=True,
            )
        finally:
            self._applying_syntax_selection = False
        self._syntax_selection_current = target

    def action_expand_syntax_selection(self: QueryMixinHost) -> None:
        """Expand the selection to the smallest enclosing syntax node."""
        current = self._syntax_selection_base()
        target = self._get_query_analysis_service().parent_range(current)
        if target is not None:
            self._apply_syntax_selection(target, remember=current)

    def action_shrink_syntax_selection(self: QueryMixinHost) -> None:
        """Restore the previous structural selection."""
        self._syntax_selection_base()
        if not self._syntax_selection_history:
            return
        target, snapshot = self._syntax_selection_history.pop()
        self._applying_syntax_selection = True
        try:
            self._apply_query_selection(snapshot, update_chrome=True)
        finally:
            self._applying_syntax_selection = False
        self._syntax_selection_current = target

    def _select_syntax_sibling(self: QueryMixinHost, direction: int) -> None:
        current = self._syntax_selection_base()
        target = self._get_query_analysis_service().sibling_range(current, direction)
        if target is not None:
            self._apply_syntax_selection(target, remember=current)

    def action_select_next_syntax_sibling(self: QueryMixinHost) -> None:
        """Select the next syntax sibling."""
        self._select_syntax_sibling(1)

    def action_select_previous_syntax_sibling(self: QueryMixinHost) -> None:
        """Select the previous syntax sibling."""
        self._select_syntax_sibling(-1)

    def action_select_current_statement(self: QueryMixinHost) -> None:
        """Select the statement containing the logical head."""
        current = self._syntax_selection_base()
        row, col = self._query_logical_head()
        target = self._get_query_analysis_service().statement_at(Position(row, col))
        if target is not None:
            self._apply_syntax_selection(target, remember=current)

    def _select_semantic_target(
        self: QueryMixinHost, target_type: SemanticTarget
    ) -> None:
        self._clear_leader_pending()
        current = self._syntax_selection_base()
        row, col = self._query_logical_head()
        target = self._get_query_analysis_service().semantic_range(
            Position(row, col), target_type
        )
        if target is not None:
            self._apply_syntax_selection(target, remember=current)

    def action_match_syntax_statement(self: QueryMixinHost) -> None:
        self._clear_leader_pending()
        self.action_select_current_statement()

    def action_match_syntax_cte(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.CTE)

    def action_match_syntax_cte_body(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.CTE_BODY)

    def action_match_syntax_subquery(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.SUBQUERY)

    def action_match_syntax_select_list(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.SELECT_LIST)

    def action_match_syntax_clause(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.CLAUSE)

    def action_match_syntax_join_condition(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.JOIN_CONDITION)

    def action_match_syntax_table_expression(self: QueryMixinHost) -> None:
        self._select_semantic_target(SemanticTarget.TABLE_EXPRESSION)
