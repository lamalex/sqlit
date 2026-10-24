"""Visual line mode actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost

from .query_editing_multicursor import per_selection


class QueryEditingVisualLineMixin:
    """Visual line mode (V) for the query editor."""

    @per_selection
    def action_enter_visual_line_mode(self: QueryMixinHost) -> None:
        """Enter visual line mode (V)."""
        from sqlit.core.vim import VimMode
        row, _ = self.query_input.cursor_location

        # Select the full current line
        lines = self.query_input.text.split("\n")
        end_col = len(lines[row]) if row < len(lines) else 0
        self._replace_query_selection(
            start=(row, 0),
            end=(row, end_col),
            logical_cursor=(row, max(0, end_col - 1)),
            normal_selection_primary=False,
            vim_mode=VimMode.VISUAL_LINE,
            visual_anchor=None,
            visual_cursor=None,
            visual_line_anchor_row=row,
            update_chrome=True,
        )

    @per_selection
    def action_exit_visual_line_mode(self: QueryMixinHost) -> None:
        """Exit visual line mode back to normal."""
        cursor = self.query_input.cursor_location
        self._set_normal_selection(cursor)

        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def _update_visual_line_selection(
        self: QueryMixinHost, cursor_row: int | None = None
    ) -> None:
        """Update selection to span full lines between anchor and cursor.

        Sets the TextArea selection directly, which also positions the cursor
        at the selection end. This avoids setting cursor_location separately,
        which would clear the selection via TextArea internals.
        """
        anchor = self._visual_line_anchor_row
        if anchor is None:
            return

        if cursor_row is None:
            cursor_row, _ = self.query_input.cursor_location

        lines = self.query_input.text.split("\n")
        start_row = min(anchor, cursor_row)
        end_row = max(anchor, cursor_row)
        end_col = len(lines[end_row]) if end_row < len(lines) else 0

        # Selection end is where the cursor lands. Place it on the cursor's side
        # so the TextArea cursor follows the direction of movement.
        if cursor_row >= anchor:
            start, end = (start_row, 0), (end_row, end_col)
        else:
            start, end = (end_row, end_col), (start_row, 0)
        logical_col = max(0, len(lines[cursor_row]) - 1)
        self._replace_query_selection(
            start=start,
            end=end,
            logical_cursor=(cursor_row, logical_col),
            normal_selection_primary=False,
            visual_line_anchor_row=anchor,
        )

    def _get_visual_line_range(self: QueryMixinHost) -> tuple[int, int]:
        """Get the (start_row, end_row) of the visual line selection."""
        anchor = self._visual_line_anchor_row
        if anchor is None:
            row, _ = self.query_input.cursor_location
            return row, row
        cursor_row, _ = self.query_input.cursor_location
        return min(anchor, cursor_row), max(anchor, cursor_row)

    def action_visual_line_yank(self: QueryMixinHost) -> None:
        """Yank (copy) selected lines."""
        if self._query_selection.secondary:
            self._yank_query_selections()
            self.action_exit_visual_line_mode()
            return
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_yank

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_yank(text, range_obj)
        if result.yanked:
            self._copy_text(result.yanked)

        from sqlit.core.vim import VimMode

        self._replace_query_selection(
            logical_cursor=(start_row, 0),
            vim_mode=VimMode.NORMAL,
            visual_line_anchor_row=None,
            update_chrome=True,
        )

        # _flash_yank_range sets the selection to the yanked range and
        # schedules its own 0.15s timer to clear it back to cursor.
        end_col = len(lines[end_row]) if end_row < len(lines) else 0
        self._flash_yank_range(start_row, 0, end_row, end_col)

    def action_visual_line_delete(self: QueryMixinHost) -> None:
        """Delete selected lines."""
        if self._query_selection.secondary:
            from sqlit.core.vim import VimMode

            self._yank_query_selections()
            self._edit_query_selections("", mode=VimMode.NORMAL, linewise=True)
            return
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_delete
        self._push_undo_state()

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_delete(text, range_obj)

        if result.yanked:
            self._copy_text(result.yanked)

        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        self._set_normal_selection()
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_visual_line_change(self: QueryMixinHost) -> None:
        """Change (delete + insert mode) selected lines."""
        if self._query_selection.secondary:
            from sqlit.core.vim import VimMode

            self._yank_query_selections()
            self._edit_query_selections("", mode=VimMode.INSERT)
            return
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_delete

        self._push_undo_state()

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_delete(text, range_obj)

        if result.yanked:
            self._copy_text(result.yanked)

        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        cursor = self.query_input.cursor_location
        self._replace_query_selection(
            start=cursor,
            end=cursor,
            logical_cursor=cursor,
            visual_line_anchor_row=None,
        )
        self._enter_insert_mode()

    def action_visual_line_execute(self: QueryMixinHost) -> None:
        """Execute only the visually selected lines."""
        # _get_query_to_execute already reads from self.query_input.selection,
        # so we just need to trigger execution and then exit visual line mode.
        # Keep the selection active during execution so _get_query_to_execute picks it up.
        self.action_execute_query()

        cursor = self.query_input.cursor_location
        self._set_normal_selection(cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()
