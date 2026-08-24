"""Query analysis service integration."""

from __future__ import annotations

from dataclasses import replace
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
    _query_jump_back: list[QuerySelectionSnapshot] | None = None
    _query_jump_forward: list[QuerySelectionSnapshot] | None = None
    _query_rename_token: int = 0

    def _get_query_analysis_service(self: QueryMixinHost) -> QueryAnalysisService:
        provider = getattr(self, "current_provider", None)
        metadata = getattr(provider, "metadata", None)
        dialect = getattr(metadata, "analysis_dialect", None)
        if self._query_analysis_service is None:
            from sqlit.domains.query.app.sqlglot_analysis import SQLGlotSemanticBackend

            backend = TextualQueryAnalysisBackend(self.query_input)
            self._query_analysis_service = QueryAnalysisService(
                backend,
                dialect=dialect,
                semantic_backend=SQLGlotSemanticBackend(),
            )
        else:
            self._query_analysis_service.dialect = dialect
        return self._query_analysis_service

    def _reset_syntax_selection_history(self: QueryMixinHost) -> None:
        if self._syntax_selection_history is not None:
            self._syntax_selection_history.clear()
        self._syntax_selection_current = None

    def _reset_query_jump_history(self: QueryMixinHost) -> None:
        if self._query_jump_back is not None:
            self._query_jump_back.clear()
        if self._query_jump_forward is not None:
            self._query_jump_forward.clear()

    def _record_query_jump(self: QueryMixinHost) -> None:
        if self._query_jump_back is None:
            self._query_jump_back = []
        self._query_jump_back.append(self._query_selection)
        del self._query_jump_back[:-100]
        if self._query_jump_forward is not None:
            self._query_jump_forward.clear()

    def _restore_query_jump(self: QueryMixinHost, *, forward: bool) -> None:
        source = self._query_jump_forward if forward else self._query_jump_back
        if not source:
            return
        destination = self._query_jump_back if forward else self._query_jump_forward
        if destination is None:
            destination = []
            if forward:
                self._query_jump_back = destination
            else:
                self._query_jump_forward = destination
        destination.append(self._query_selection)
        del destination[:-100]
        self._reset_syntax_selection_history()
        self._apply_query_selection(source.pop(), update_chrome=True)

    def action_query_jump_back(self: QueryMixinHost) -> None:
        """Restore the selection before the previous semantic jump."""
        self._restore_query_jump(forward=False)

    def action_query_jump_forward(self: QueryMixinHost) -> None:
        """Restore the selection after the next semantic jump."""
        self._restore_query_jump(forward=True)

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

    def action_g_definition(self: QueryMixinHost) -> None:
        """Go to the CTE or alias definition under the logical head."""
        self._clear_leader_pending()
        self._clear_count_buffer()
        row, col = self._query_logical_head()
        target = self._get_query_analysis_service().definition_at(
            self.query_input.text,
            Position(row, col),
        )
        if target is None:
            self.notify("No SQL definition found at cursor", severity="warning")
            return
        self._commit_query_jump(target)

    def _commit_query_jump(self: QueryMixinHost, target: SyntaxRange) -> bool:
        target_position = (target.start.row, target.start.col)
        if self.vim_mode == VimMode.NORMAL and self._query_selection.normal_selection_primary and self._query_logical_head() == target_position:
            return False
        self._record_query_jump()
        self._reset_syntax_selection_history()
        self._set_normal_selection(target_position)
        return True

    def _apply_query_range_preview(
        self: QueryMixinHost,
        original_snapshot: QuerySelectionSnapshot,
        original_syntax_current: SyntaxRange | None,
        target: SyntaxRange | None,
    ) -> None:
        snapshot = original_snapshot
        if target is not None:
            end = (target.end.row, target.end.col)
            snapshot = replace(
                original_snapshot,
                start=(target.start.row, target.start.col),
                end=end,
                logical_cursor=self._position_before(end),
                normal_selection_primary=False,
                vim_mode=VimMode.NORMAL,
                visual_anchor=None,
                visual_cursor=None,
                visual_line_anchor_row=None,
            )
        self._applying_syntax_selection = True
        try:
            self._apply_query_selection(snapshot)
        finally:
            self._applying_syntax_selection = False
        self._syntax_selection_current = original_syntax_current

    def action_g_references(self: QueryMixinHost) -> None:
        """Find references to the CTE or alias under the logical head."""
        from sqlit.domains.query.ui.screens import SyntaxObjectPickerScreen

        self._clear_leader_pending()
        self._clear_count_buffer()
        row, col = self._query_logical_head()
        references = self._get_query_analysis_service().references_at(
            self.query_input.text,
            Position(row, col),
        )
        if not references:
            self.notify("No SQL references found at cursor", severity="warning")
            return
        if len(references) == 1:
            if not self._commit_query_jump(references[0]):
                self.notify("Only SQL reference is at cursor")
            return

        original_snapshot = self._query_selection
        original_syntax_current = self._syntax_selection_current

        def apply_preview(target: SyntaxRange | None) -> None:
            self._apply_query_range_preview(
                original_snapshot,
                original_syntax_current,
                target,
            )

        def handle_result(target: SyntaxRange | None) -> None:
            apply_preview(None)
            if target is not None:
                self._commit_query_jump(target)

        self.push_screen(
            SyntaxObjectPickerScreen(
                self.query_input.text,
                references,
                apply_preview,
                title="Find SQL reference",
                description="References linked to this declaration. Type to filter.",
                placeholder="Filter SQL references...",
            ),
            handle_result,
        )

    def action_g_rename(self: QueryMixinHost) -> None:
        """Rename the CTE or alias under the logical head."""
        from sqlit.domains.query.app.query_rename import (
            RenameError,
            build_rename_plan,
            offset_to_position,
            syntax_range_to_span,
        )
        from sqlit.domains.query.ui.screens import QueryRenameScreen

        self._clear_leader_pending()
        self._clear_count_buffer()
        original_text = self.query_input.text
        row, col = self._query_logical_head()
        service = self._get_query_analysis_service()
        symbol = service.symbol_at(original_text, Position(row, col))
        if symbol is None:
            self.notify("No renameable SQL symbol found at cursor", severity="warning")
            return

        self._query_rename_token += 1
        token = self._query_rename_token

        def handle_result(new_name: str | None) -> None:
            if new_name is None:
                return
            if token != self._query_rename_token or self.query_input.text != original_text:
                self.notify("Query changed before rename could be applied", severity="warning")
                return
            try:
                plan = build_rename_plan(original_text, symbol, new_name)
                renamed_symbol = service.symbol_at(
                    plan.text,
                    offset_to_position(plan.text, plan.declaration.start),
                )
                if (
                    renamed_symbol is None
                    or renamed_symbol.kind != symbol.kind
                    or renamed_symbol.name != new_name
                    or syntax_range_to_span(plan.text, renamed_symbol.declaration) != plan.declaration
                    or tuple(syntax_range_to_span(plan.text, value) for value in renamed_symbol.references) != plan.references
                    or service.symbol_has_conflict(plan.text, renamed_symbol)
                ):
                    raise RenameError("Rename would change SQL symbol resolution")
            except RenameError as error:
                self.notify(str(error), severity="error")
                return

            self._push_undo_state()
            self._reset_query_jump_history()
            self._reset_syntax_selection_history()
            self._suppress_autocomplete_once = True
            self.query_input.text = plan.text
            target = offset_to_position(plan.text, plan.declaration.start)
            self._set_normal_selection((target.row, target.col))
            self.notify(f"Renamed {symbol.name} to {new_name} ({plan.occurrence_count} occurrence{'s' if plan.occurrence_count != 1 else ''})")

        self.push_screen(
            QueryRenameScreen(symbol.name, len(symbol.references) + 1),
            handle_result,
        )

    def action_show_syntax_object_picker(self: QueryMixinHost) -> None:
        """Choose a semantic object from the current SQL statement."""
        from sqlit.domains.query.ui.screens import (
            SyntaxObjectPickerScreen,
            syntax_kind_label,
        )

        self._clear_count_buffer()
        row, col = self._query_logical_head()
        selections = self._get_query_analysis_service().semantic_ranges(Position(row, col))
        if not selections:
            self.notify("No SQL objects found at cursor", severity="warning")
            return
        current = self._syntax_selection_base()
        original_snapshot = self._query_selection
        original_syntax_current = self._syntax_selection_current

        def apply_preview(target: SyntaxRange | None) -> None:
            self._apply_query_range_preview(
                original_snapshot,
                original_syntax_current,
                target,
            )

        def handle_result(target: SyntaxRange | None) -> None:
            if target is None:
                apply_preview(None)
                return
            apply_preview(None)
            self._apply_syntax_selection(target, remember=current)
            self.notify(f"Selected {syntax_kind_label(target.kind)}")

        self.push_screen(
            SyntaxObjectPickerScreen(self.query_input.text, selections, apply_preview),
            handle_result,
        )

    def _select_semantic_target(self: QueryMixinHost, target_type: SemanticTarget) -> None:
        self._clear_leader_pending()
        current = self._syntax_selection_base()
        row, col = self._query_logical_head()
        target = self._get_query_analysis_service().semantic_range(Position(row, col), target_type)
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
