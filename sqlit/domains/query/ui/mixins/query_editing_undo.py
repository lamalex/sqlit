"""Undo/redo helpers for query editing."""

from __future__ import annotations

from typing import Any

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingUndoMixin:
    """Undo history management for the query editor."""

    _restoring_undo_state: bool = False

    def _get_undo_history(self: QueryMixinHost) -> Any:
        """Get or create the undo history instance."""
        from sqlit.domains.query.editing import UndoHistory

        if self._undo_history is None:
            self._undo_history = UndoHistory()
        return self._undo_history

    def _push_undo_state(self: QueryMixinHost) -> None:
        """Push current state to undo history."""
        if self._restoring_undo_state:
            return
        self._get_undo_history().push(self._capture_undo_state())

    def _capture_undo_state(self: QueryMixinHost) -> Any:
        """Capture text, selection, logical cursor, and modal state."""
        from sqlit.core.vim import VimMode
        from sqlit.domains.query.editing import QuerySelectionSnapshot, UndoState

        selection = self.query_input.selection
        if self.vim_mode == VimMode.NORMAL:
            logical_cursor = self._query_logical_head()
        elif self.vim_mode == VimMode.VISUAL:
            logical_cursor = self._visual_cursor or selection.end
        else:
            logical_cursor = self.query_input.cursor_location

        return UndoState(
            text=self.query_input.text,
            selection=QuerySelectionSnapshot(
                start=selection.start,
                end=selection.end,
                logical_cursor=logical_cursor,
                normal_selection_primary=self._normal_selection_primary,
                vim_mode=self.vim_mode,
                visual_anchor=self._visual_anchor,
                visual_cursor=self._visual_cursor,
                visual_line_anchor_row=self._visual_line_anchor_row,
            ),
        )

    def _restore_undo_state(self: QueryMixinHost, state: Any) -> None:
        """Restore a complete query editor snapshot without normalizing it."""
        from textual.widgets.text_area import Selection

        from sqlit.core.vim import VimMode

        snapshot = state.selection
        self._restoring_undo_state = True
        self._suppress_autocomplete_once = True
        try:
            self.query_input.text = state.text
            self.vim_mode = snapshot.vim_mode
            self.query_input.read_only = snapshot.vim_mode != VimMode.INSERT
            self.query_input.selection = Selection(snapshot.start, snapshot.end)
            self._normal_cursor = snapshot.logical_cursor
            self._normal_textual_cursor = snapshot.end
            self._visual_anchor = snapshot.visual_anchor
            self._visual_cursor = snapshot.visual_cursor
            self._visual_line_anchor_row = snapshot.visual_line_anchor_row
            self._normal_selection_primary = snapshot.normal_selection_primary
            self.query_input._last_text = state.text
            self._hide_autocomplete()
            self._update_vim_mode_visuals()
            self._update_footer_bindings()
        finally:
            self._restoring_undo_state = False

    def action_undo(self: QueryMixinHost) -> None:
        """Undo the last edit."""
        history = self._get_undo_history()
        self._push_undo_state()
        if not history.can_undo():
            return

        state = history.undo()
        if state:
            self._restore_undo_state(state)

    def action_redo(self: QueryMixinHost) -> None:
        """Redo the last undone edit."""
        history = self._get_undo_history()
        self._push_undo_state()
        if not history.can_redo():
            return

        state = history.redo()
        if state:
            self._restore_undo_state(state)
