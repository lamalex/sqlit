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
        from sqlit.domains.query.editing import UndoState

        return UndoState(
            text=self.query_input.text,
            selection=self._query_selection,
        )

    def _restore_undo_state(self: QueryMixinHost, state: Any) -> None:
        """Restore a complete query editor snapshot without normalizing it."""
        snapshot = state.selection
        self._restoring_undo_state = True
        self._suppress_autocomplete_once = True
        try:
            self.query_input.text = state.text
            self._apply_query_selection(snapshot, update_chrome=True)
            self.query_input._last_text = state.text
            self._hide_autocomplete()
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
