"""Cursor and navigation actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost

from .query_editing_multicursor import per_selection


class QueryEditingCursorMixin:
    """Cursor movement and navigation for the query editor."""

    @per_selection
    def _move_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Move cursor using a vim motion, with optional count prefix support."""
        from sqlit.domains.query.editing import MOTIONS

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        # Get count prefix (if any)
        count = self._get_and_clear_count() or 1

        text = self.query_input.text
        # In charwise visual mode, read the logical cursor position (not the
        # extended selection end) so motions operate from the correct position.
        from sqlit.core.vim import VimMode as _VM

        if self.vim_mode == _VM.VISUAL and getattr(self, "_visual_cursor", None) is not None:
            row, col = self._visual_cursor
        elif (
            self.vim_mode == _VM.NORMAL
            and self._has_selection()
        ):
            row, col = self._query_logical_head()
        else:
            row, col = self.query_input.cursor_location
        origin = (row, col)

        # Apply motion `count` times
        for _ in range(count):
            result = motion_func(text, row, col, char)
            new_row, new_col = result.position.row, result.position.col
            # Stop if motion didn't move (hit boundary)
            if (new_row, new_col) == (row, col):
                break
            row, col = new_row, new_col

        # In visual modes, update the selection directly instead of setting
        # cursor_location, which would clear the TextArea selection.
        from sqlit.core.vim import VimMode

        if self.vim_mode == VimMode.VISUAL_LINE and hasattr(self, "_update_visual_line_selection"):
            self._update_visual_line_selection(cursor_row=row)
        elif self.vim_mode == VimMode.VISUAL and hasattr(self, "_update_query_visual_selection"):
            self._update_query_visual_selection(cursor=(row, col))
        else:
            self._set_normal_motion_selection(origin, (row, col), motion_key)

    def action_g_leader_key(self: QueryMixinHost) -> None:
        """Show the g motion leader menu."""
        self._start_leader_pending("g")

    @per_selection
    def action_g_first_line(self: QueryMixinHost) -> None:
        """Go to first line (gg), or to line N with count prefix (e.g., 3gg)."""
        from sqlit.core.vim import VimMode

        self._clear_leader_pending()
        count = self._get_and_clear_count()
        if count is not None:
            lines = self.query_input.text.split("\n")
            num_lines = len(lines)
            target_row = min(count - 1, num_lines - 1)
            target_row = max(0, target_row)
        else:
            target_row = 0

        if self.vim_mode == VimMode.VISUAL_LINE and hasattr(self, "_update_visual_line_selection"):
            self._update_visual_line_selection(cursor_row=target_row)
        elif self.vim_mode == VimMode.VISUAL and hasattr(self, "_update_query_visual_selection"):
            self._update_query_visual_selection(cursor=(target_row, 0))
        else:
            self._set_normal_selection((target_row, 0))

    def action_g_last_line(self: QueryMixinHost) -> None:
        """Go to the last line (ge)."""
        self._clear_leader_pending()
        self._move_with_motion("G")

    def action_g_line_start(self: QueryMixinHost) -> None:
        """Go to the start of the current line (gh)."""
        self._clear_leader_pending()
        self._move_with_motion("0")

    def action_g_line_end(self: QueryMixinHost) -> None:
        """Go to the end of the current line (gl)."""
        self._clear_leader_pending()
        self._move_with_motion("$")

    def action_g_first_non_blank(self: QueryMixinHost) -> None:
        """Go to the first non-whitespace character (gs)."""
        self._clear_leader_pending()
        self._move_with_motion("^")

    def action_cursor_left(self: QueryMixinHost) -> None:
        """Move cursor left (h in normal mode), with count support."""
        self._move_with_motion("h")

    def action_cursor_right(self: QueryMixinHost) -> None:
        """Move cursor right (l in normal mode), with count support."""
        self._move_with_motion("l")

    def action_cursor_up(self: QueryMixinHost) -> None:
        """Move cursor up (k in normal mode), with count support."""
        self._move_with_motion("k")

    def action_cursor_down(self: QueryMixinHost) -> None:
        """Move cursor down (j in normal mode), with count support."""
        self._move_with_motion("j")

    def action_cursor_word_forward(self: QueryMixinHost) -> None:
        """Move cursor to next word (w)."""
        self._move_with_motion("w")

    def action_cursor_WORD_forward(self: QueryMixinHost) -> None:
        """Move cursor to next WORD (W)."""
        self._move_with_motion("W")

    def action_cursor_word_back(self: QueryMixinHost) -> None:
        """Move cursor to previous word (b)."""
        self._move_with_motion("b")

    def action_cursor_WORD_back(self: QueryMixinHost) -> None:
        """Move cursor to previous WORD (B)."""
        self._move_with_motion("B")

    def action_cursor_word_end(self: QueryMixinHost) -> None:
        """Move cursor to end of word (e). Unbound by default."""
        self._move_with_motion("e")

    def action_cursor_WORD_end(self: QueryMixinHost) -> None:
        """Move cursor to end of WORD (E). Unbound by default."""
        self._move_with_motion("E")

    def action_cursor_first_non_blank(self: QueryMixinHost) -> None:
        """Move cursor to first non-whitespace character (^)."""
        self._move_with_motion("^")

    def action_cursor_line_start(self: QueryMixinHost) -> None:
        """Move cursor to start of line (0)."""
        self._move_with_motion("0")

    def action_cursor_line_end(self: QueryMixinHost) -> None:
        """Move cursor to end of line ($)."""
        self._move_with_motion("$")

    def action_cursor_last_line(self: QueryMixinHost) -> None:
        """Move cursor to last line (G), or to line N with count prefix (e.g., 25G)."""
        from sqlit.core.vim import VimMode

        count = self._get_and_clear_count()
        if count is not None:
            # Go to specific line (1-indexed)
            lines = self.query_input.text.split("\n")
            num_lines = len(lines)
            target_row = min(count - 1, num_lines - 1)  # Convert to 0-indexed, clamp
            target_row = max(0, target_row)
            if self.vim_mode == VimMode.VISUAL_LINE and hasattr(self, "_update_visual_line_selection"):
                self._update_visual_line_selection(cursor_row=target_row)
            elif self.vim_mode == VimMode.VISUAL and hasattr(self, "_update_query_visual_selection"):
                self._update_query_visual_selection(cursor=(target_row, 0))
            else:
                self._set_normal_selection((target_row, 0))
        else:
            # Go to last line
            self._move_with_motion("G")

    def action_cursor_matching_bracket(self: QueryMixinHost) -> None:
        """Move cursor to matching bracket (%)."""
        self._move_with_motion("%")

    def action_cursor_find_char(self: QueryMixinHost) -> None:
        """Find next occurrence of char (f{c})."""
        self._show_motion_char_pending_menu("f")

    def action_cursor_find_char_back(self: QueryMixinHost) -> None:
        """Find previous occurrence of char (F{c})."""
        self._show_motion_char_pending_menu("F")

    def action_cursor_till_char(self: QueryMixinHost) -> None:
        """Move till before next char (t{c})."""
        self._show_motion_char_pending_menu("t")

    def action_cursor_till_char_back(self: QueryMixinHost) -> None:
        """Move till after previous char (T{c})."""
        self._show_motion_char_pending_menu("T")

    @per_selection
    def action_prepend_insert_mode(self: QueryMixinHost) -> None:
        """Enter insert mode at start of line (I)."""
        row, _ = self._query_logical_head()
        target = (row, 0)
        self._replace_query_selection(start=target, end=target, logical_cursor=target)
        self.action_enter_insert_mode()

    @per_selection
    def action_append_insert_mode(self: QueryMixinHost) -> None:
        """Enter insert mode after the current selection (a)."""
        _, end = self._ordered_selection(self.query_input.selection)
        self._replace_query_selection(start=end, end=end, logical_cursor=end)
        self.action_enter_insert_mode()

    @per_selection
    def action_append_line_end(self: QueryMixinHost) -> None:
        """Enter insert mode at end of line (A)."""
        lines = self.query_input.text.split("\n")
        row, _ = self._query_logical_head()
        line_len = len(lines[row]) if row < len(lines) else 0
        target = (row, line_len)
        self._replace_query_selection(start=target, end=target, logical_cursor=target)
        self.action_enter_insert_mode()

    def _show_motion_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show char pending menu for f/F/t/T motions (cursor movement)."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._move_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

    def action_open_line_below(self: QueryMixinHost) -> None:
        """Open new line below current line and enter insert mode (o in normal mode)."""
        if self._query_selection.secondary:
            from sqlit.core.vim import VimMode

            self._edit_query_selections("\n", mode=VimMode.INSERT, open_line="below")
            return
        self._push_undo_state()
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location

        # Insert new line after current row
        lines.insert(row + 1, "")
        self.query_input.text = "\n".join(lines)
        self.query_input.cursor_location = (row + 1, 0)

        # Enter insert mode
        self.action_enter_insert_mode()

    def action_open_line_above(self: QueryMixinHost) -> None:
        """Open new line above current line and enter insert mode (O in normal mode)."""
        if self._query_selection.secondary:
            from sqlit.core.vim import VimMode

            self._edit_query_selections("\n", mode=VimMode.INSERT, open_line="above")
            return
        self._push_undo_state()
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location

        # Insert new line before current row
        lines.insert(row, "")
        self.query_input.text = "\n".join(lines)
        self.query_input.cursor_location = (row, 0)

        # Enter insert mode
        self.action_enter_insert_mode()
