"""Linear undo/redo history for text editing.

Simple linear history - no branching, redo is cleared on new edits.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.core.vim import VimMode

Location = tuple[int, int]


@dataclass(frozen=True)
class QuerySelectionSnapshot:
    """Canonical query selection and modal state."""

    start: Location
    end: Location
    logical_cursor: Location
    normal_selection_primary: bool
    vim_mode: VimMode
    visual_anchor: Location | None = None
    visual_cursor: Location | None = None
    visual_line_anchor_row: int | None = None


@dataclass(frozen=True)
class UndoState:
    """A complete query editor snapshot for undo/redo."""

    text: str
    selection: QuerySelectionSnapshot


class UndoHistory:
    """Linear undo/redo history manager.

    Usage:
        history = UndoHistory()
        history.push(before_state)  # Save state before edit
        # ... perform edit ...
        history.push(after_state)  # Save state after edit

        # Undo
        if history.can_undo():
            state = history.undo()
            # Apply state.text and state.selection

        # Redo
        if history.can_redo():
            state = history.redo()
            # Apply state.text and state.selection
    """

    def __init__(self, max_size: int = 100) -> None:
        """Initialize undo history.

        Args:
            max_size: Maximum number of undo states to keep.
        """
        self._undo_stack: list[UndoState] = []
        self._redo_stack: list[UndoState] = []
        self._max_size = max_size
        self._current: UndoState | None = None

    def push(self, state: UndoState) -> None:
        """Push a new state to the history.

        This clears the redo stack (no branching history).
        """
        # Don't push duplicate states
        if self._current is not None and self._current.text == state.text:
            # Selection changes alone update the current snapshot.
            self._current = state
            return

        # Push current state to undo stack before replacing
        if self._current is not None:
            self._undo_stack.append(self._current)

            # Trim stack if too large
            if len(self._undo_stack) > self._max_size:
                self._undo_stack = self._undo_stack[-self._max_size :]

        self._current = state
        self._redo_stack.clear()  # Clear redo on new edit

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self._redo_stack) > 0

    def undo(self) -> UndoState | None:
        """Undo to previous state.

        Returns:
            The state to restore, or None if nothing to undo.
        """
        if not self._undo_stack:
            return None

        # Push current to redo stack
        if self._current is not None:
            self._redo_stack.append(self._current)

        # Pop from undo stack
        self._current = self._undo_stack.pop()
        return self._current

    def redo(self) -> UndoState | None:
        """Redo to next state.

        Returns:
            The state to restore, or None if nothing to redo.
        """
        if not self._redo_stack:
            return None

        # Push current to undo stack
        if self._current is not None:
            self._undo_stack.append(self._current)

        # Pop from redo stack
        self._current = self._redo_stack.pop()
        return self._current

    def clear(self) -> None:
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current = None

    @property
    def current(self) -> UndoState | None:
        """Get the current state."""
        return self._current
