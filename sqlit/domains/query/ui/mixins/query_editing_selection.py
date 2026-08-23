"""Selection helpers for query editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.shared.ui.protocols import QueryMixinHost

if TYPE_CHECKING:
    from textual.widgets.text_area import Selection

    from sqlit.domains.query.editing.types import Range


class QueryEditingSelectionMixin:
    """Selection-related actions for the query editor."""

    def _query_logical_head(self: QueryMixinHost) -> tuple[int, int]:
        tracked_cursor = getattr(self, "_normal_cursor", None)
        tracked_textual_cursor = getattr(self, "_normal_textual_cursor", None)
        selection = self.query_input.selection
        tracking_is_visible = (
            selection.start != selection.end or tracked_cursor == tracked_textual_cursor
        )
        if (
            tracked_cursor is not None
            and self.query_input.cursor_location == tracked_textual_cursor
            and tracking_is_visible
        ):
            return tracked_cursor
        return self.query_input.cursor_location

    def _set_normal_selection(
        self: QueryMixinHost,
        position: tuple[int, int] | None = None,
    ) -> None:
        """Select the character under the NORMAL-mode cursor."""
        from textual.widgets.text_area import Selection

        text = self.query_input.text
        lines = text.split("\n")
        row, col = position or self.query_input.cursor_location
        row = min(max(row, 0), len(lines) - 1)
        col = min(max(col, 0), len(lines[row]))

        if col < len(lines[row]):
            cursor = (row, col)
            boundary = (row, col + 1)
        elif row < len(lines) - 1:
            cursor = (row, col)
            boundary = (row + 1, 0)
        elif col > 0:
            cursor = (row, col - 1)
            boundary = (row, col)
        else:
            cursor = (row, col)
            boundary = cursor

        # Reverse the Textual selection so its logical head remains on the
        # selected character rather than one position after it.
        self.query_input.selection = Selection(boundary, cursor)
        self._normal_cursor = cursor
        self._normal_textual_cursor = cursor
        self._normal_selection_primary = True

    def _set_normal_motion_selection(
        self: QueryMixinHost,
        origin: tuple[int, int],
        destination: tuple[int, int],
        motion_key: str,
    ) -> None:
        """Apply Helix-style NORMAL selection semantics for a motion."""
        from textual.widgets.text_area import Selection

        if origin == destination and motion_key not in {"e", "E"}:
            self._set_normal_selection(destination)
            return

        if motion_key in {"e", "E"}:
            boundary = self._position_after(destination)
            self.query_input.selection = Selection(origin, boundary)
            self._normal_cursor = destination
            self._normal_textual_cursor = boundary
            self._normal_selection_primary = False
            return

        if motion_key not in {"w", "W", "b", "B"}:
            self._set_normal_selection(destination)
            return

        self.query_input.selection = Selection(origin, destination)
        self._normal_cursor = destination
        self._normal_textual_cursor = destination
        self._normal_selection_primary = False

    def action_collapse_selection(self: QueryMixinHost) -> None:
        """Collapse the current range to its logical head."""
        from sqlit.core.vim import VimMode

        self._clear_count_buffer()
        selection = self.query_input.selection
        if self.vim_mode == VimMode.VISUAL:
            cursor = self._visual_cursor or selection.end
        elif self.vim_mode == VimMode.VISUAL_LINE:
            cursor = (
                selection.end
                if selection.start > selection.end
                else self._position_before(selection.end)
            )
        else:
            cursor = self._query_logical_head()

        was_visual = self.vim_mode in {VimMode.VISUAL, VimMode.VISUAL_LINE}
        self._visual_anchor = None
        self._visual_cursor = None
        self._visual_line_anchor_row = None
        if was_visual:
            self.vim_mode = VimMode.NORMAL
        self._set_normal_selection(cursor)
        if was_visual:
            self._update_vim_mode_visuals()
            self._update_footer_bindings()

    def action_match_leader_key(self: QueryMixinHost) -> None:
        """Wait for an inner/around text-object selector."""
        self._clear_count_buffer()
        self._start_leader_pending("match")

    def action_match_inner(self: QueryMixinHost) -> None:
        self._clear_leader_pending()
        self._show_select_text_object_menu(around=False)

    def action_match_around(self: QueryMixinHost) -> None:
        self._clear_leader_pending()
        self._show_select_text_object_menu(around=True)

    def action_match_surround_add(self: QueryMixinHost) -> None:
        """Prompt for a delimiter to add around the selection."""
        self._clear_leader_pending()
        self._show_surround_menu("add")

    def action_match_surround_delete(self: QueryMixinHost) -> None:
        """Prompt for an enclosing delimiter to delete."""
        self._clear_leader_pending()
        self._show_surround_menu("delete")

    def action_match_surround_replace(self: QueryMixinHost) -> None:
        """Prompt for enclosing and replacement delimiters."""
        self._clear_leader_pending()
        self._show_surround_menu("replace")

    def _show_surround_menu(self: QueryMixinHost, operation: str) -> None:
        from sqlit.domains.query.ui.screens import SurroundMenuScreen

        def handle_result(delimiters: str | None) -> None:
            if not delimiters:
                return
            self._apply_surround_edit(operation, delimiters)

        self.push_screen(SurroundMenuScreen(operation), handle_result)

    def _apply_surround_edit(
        self: QueryMixinHost, operation: str, delimiters: str
    ) -> None:
        from textual.widgets.text_area import Selection

        from sqlit.core.vim import VimMode
        from sqlit.domains.query.editing import (
            add_surround,
            delete_surround,
            replace_surround,
        )

        selection = self.query_input.selection
        selection_was_primary = self._normal_selection_primary
        backward = selection.start > selection.end
        start, end = self._ordered_selection(selection)
        text = self.query_input.text
        start_offset = self._location_to_offset(text, start)
        end_offset = self._location_to_offset(text, end)
        was_visual = self.vim_mode in {VimMode.VISUAL, VimMode.VISUAL_LINE}
        if self.vim_mode == VimMode.VISUAL:
            head = self._visual_cursor or (start if backward else self._position_before(end))
        elif self.vim_mode == VimMode.VISUAL_LINE:
            head = start if backward else self._position_before(end)
        else:
            head = self._query_logical_head()
        head_offset = self._location_to_offset(text, head)

        if operation == "add":
            result = add_surround(text, start_offset, end_offset, delimiters)
        elif operation == "delete":
            result = delete_surround(text, start_offset, end_offset, delimiters)
        else:
            result = replace_surround(
                text, start_offset, end_offset, delimiters[0], delimiters[1]
            )
        if result is None:
            self.notify("No matching surround found", severity="warning")
            return

        original_length = end_offset - start_offset
        payload_length = result.end - result.start
        head_delta = max(0, head_offset - start_offset)
        if payload_length < original_length and head_delta >= payload_length:
            head_delta = max(0, payload_length - 1)
        else:
            head_delta = min(head_delta, payload_length)

        self._push_undo_state()
        self.query_input.text = result.text
        new_start = self._offset_to_location(result.text, result.start)
        new_end = self._offset_to_location(result.text, result.end)
        new_head = self._offset_to_location(result.text, result.start + head_delta)
        if backward:
            self.query_input.selection = Selection(new_end, new_start)
            textual_cursor = new_start
        else:
            self.query_input.selection = Selection(new_start, new_end)
            textual_cursor = new_end
        self._normal_cursor = new_head
        self._normal_textual_cursor = textual_cursor
        self._normal_selection_primary = False if was_visual else selection_was_primary
        if was_visual:
            self._visual_anchor = None
            self._visual_cursor = None
            self._visual_line_anchor_row = None
            self.vim_mode = VimMode.NORMAL
            self._update_vim_mode_visuals()
            self._update_footer_bindings()

    def action_replace_selection(self: QueryMixinHost) -> None:
        """Replace every selected character with one typed character."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        self._clear_count_buffer()
        if not self._has_selection():
            self._set_normal_selection()
        if not self._has_selection():
            return

        def handle_result(char: str | None) -> None:
            if not char:
                return

            from textual.widgets.text_area import Selection

            from sqlit.domains.query.editing import get_selection_text, operator_delete, paste_text

            selection = self.query_input.selection
            selection_was_primary = self._normal_selection_primary
            backward = selection.start > selection.end
            start, end = self._ordered_selection(selection)
            selected = get_selection_text(self.query_input.text, start[0], start[1], end[0], end[1])
            replacement = "".join("\n" if value == "\n" else char for value in selected)

            self._push_undo_state()
            deleted = operator_delete(self.query_input.text, self._selection_range(start, end))
            replaced = paste_text(deleted.text, deleted.row, deleted.col, replacement)
            self.query_input.text = replaced.text

            selection_end = (replaced.row, replaced.col)
            if backward:
                self.query_input.selection = Selection(selection_end, start)
                self._normal_cursor = start
                self._normal_textual_cursor = start
            else:
                self.query_input.selection = Selection(start, selection_end)
                self._normal_cursor = self._position_before(selection_end)
                self._normal_textual_cursor = selection_end
            self._normal_selection_primary = selection_was_primary

        self.push_screen(CharPendingMenuScreen("r"), handle_result)

    def _show_select_text_object_menu(self: QueryMixinHost, *, around: bool) -> None:
        from sqlit.domains.query.ui.screens import TextObjectMenuScreen

        def handle_result(obj_char: str | None) -> None:
            if not obj_char:
                return

            from textual.widgets.text_area import Selection

            from sqlit.domains.query.editing import get_text_object

            tracked_cursor = getattr(self, "_normal_cursor", None)
            tracked_textual_cursor = getattr(self, "_normal_textual_cursor", None)
            if tracked_cursor is not None and self.query_input.cursor_location == tracked_textual_cursor:
                row, col = tracked_cursor
            else:
                row, col = self.query_input.cursor_location
            range_obj = get_text_object(obj_char, self.query_input.text, row, col, around)
            if range_obj is None:
                return

            if range_obj.start > range_obj.end:
                cursor = (range_obj.start.row, range_obj.start.col)
                self.query_input.selection = Selection(cursor, cursor)
                self._normal_cursor = cursor
                self._normal_textual_cursor = cursor
                self._normal_selection_primary = False
                return

            ordered = range_obj.ordered()
            start = (ordered.start.row, ordered.start.col)
            end = self._position_after((ordered.end.row, ordered.end.col))
            self.query_input.selection = Selection(start, end)
            self._normal_cursor = (ordered.end.row, ordered.end.col)
            self._normal_textual_cursor = end
            self._normal_selection_primary = False

        mode = "around" if around else "inner"
        self.push_screen(TextObjectMenuScreen(mode, operator="select"), handle_result)

    def _position_after(self: QueryMixinHost, position: tuple[int, int]) -> tuple[int, int]:
        lines = self.query_input.text.split("\n")
        row, col = position
        if row < len(lines) and col < len(lines[row]):
            return row, col + 1
        if row < len(lines) - 1:
            return row + 1, 0
        return row, col

    def _position_before(self: QueryMixinHost, position: tuple[int, int]) -> tuple[int, int]:
        lines = self.query_input.text.split("\n")
        row, col = position
        if col > 0:
            return row, col - 1
        if row > 0:
            return row - 1, len(lines[row - 1])
        return position

    def _ordered_selection(
        self: QueryMixinHost,
        selection: Selection,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return ordered (start, end) selection coordinates."""
        start = selection.start
        end = selection.end
        if start > end:
            start, end = end, start
        return start, end

    def _selection_range(
        self: QueryMixinHost,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> Range:
        """Build a charwise range from selection bounds."""
        from sqlit.domains.query.editing.types import MotionType, Position, Range

        return Range(
            Position(start[0], start[1]),
            Position(end[0], end[1]),
            MotionType.CHARWISE,
            inclusive=False,
        )

    def _has_selection(self: QueryMixinHost) -> bool:
        """Check if there's an active text selection."""
        selection = self.query_input.selection
        return selection.start != selection.end

    def _flash_yank_range(
        self: QueryMixinHost,
        start_row: int,
        start_col: int,
        end_row: int,
        end_col: int,
    ) -> None:
        """Flash the yanked range by temporarily selecting it."""
        from textual.widgets.text_area import Selection

        # Save current cursor position
        cursor = self.query_input.cursor_location

        # Set selection to yanked range to highlight it
        self.query_input.selection = Selection(
            (start_row, start_col), (end_row, end_col)
        )
        self._normal_selection_primary = True

        # Clear selection after a short delay
        def clear_flash() -> None:
            self._set_normal_selection(cursor)

        self.set_timer(0.15, clear_flash)

    def _yank_selection(self: QueryMixinHost) -> None:
        """Yank the current selection."""
        from sqlit.domains.query.editing import get_selection_text

        selection = self.query_input.selection
        start_row, start_col = selection.start
        end_row, end_col = selection.end

        text = get_selection_text(
            self.query_input.text,
            start_row,
            start_col,
            end_row,
            end_col,
        )

        if text:
            self._copy_text(text)
            self._normal_selection_primary = True
            # Flash: keep selection visible briefly, then clear
            cursor = self.query_input.cursor_location

            def clear_selection() -> None:
                self._set_normal_selection(cursor)

            self.set_timer(0.15, clear_selection)

    def _change_selection(self: QueryMixinHost, *, push_undo: bool = True) -> None:
        """Change (delete and enter insert mode) the current selection."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import get_selection_text, operator_delete

        selection = self.query_input.selection
        start, end = self._ordered_selection(selection)

        if push_undo:
            self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = self._selection_range(start, end)
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection and enter insert mode
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

        # Enter insert mode
        self._enter_insert_mode()

    def _delete_selection(self: QueryMixinHost) -> None:
        """Delete the current selection."""
        from sqlit.domains.query.editing import get_selection_text, operator_delete

        selection = self.query_input.selection
        if selection.start == selection.end:
            return

        start, end = self._ordered_selection(selection)

        # Push undo state before delete
        self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = self._selection_range(start, end)
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        self._set_normal_selection(self.query_input.cursor_location)

    def _extend_selection(self: QueryMixinHost, new_row: int, new_col: int) -> None:
        """Extend selection from current anchor to new position."""
        from textual.widgets.text_area import Selection

        # Get current selection anchor (start point)
        selection = self.query_input.selection
        anchor = selection.start

        # Update cursor and selection
        self.query_input.cursor_location = (new_row, new_col)
        self.query_input.selection = Selection(anchor, (new_row, new_col))
        self._normal_selection_primary = False

    def action_select_left(self: QueryMixinHost) -> None:
        """Extend selection one character left (Shift+Left)."""
        row, col = self.query_input.cursor_location
        new_col = max(0, col - 1)
        self._extend_selection(row, new_col)

    def action_select_right(self: QueryMixinHost) -> None:
        """Extend selection one character right (Shift+Right)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        line_len = len(lines[row]) if row < len(lines) else 0
        new_col = min(col + 1, line_len)
        self._extend_selection(row, new_col)

    def action_select_up(self: QueryMixinHost) -> None:
        """Extend selection one line up (Shift+Up)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = max(0, row - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self._extend_selection(new_row, new_col)

    def action_select_down(self: QueryMixinHost) -> None:
        """Extend selection one line down (Shift+Down)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = min(row + 1, len(lines) - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self._extend_selection(new_row, new_col)

    def action_select_word_left(self: QueryMixinHost) -> None:
        """Extend selection one word left (Ctrl+Shift+Left)."""
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["b"](text, row, col, None)
        self._extend_selection(result.position.row, result.position.col)

    def action_select_word_right(self: QueryMixinHost) -> None:
        """Extend selection one word right (Ctrl+Shift+Right)."""
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["w"](text, row, col, None)
        self._extend_selection(result.position.row, result.position.col)

    def action_select_line_start(self: QueryMixinHost) -> None:
        """Extend selection to line start (Shift+Home)."""
        row, _ = self.query_input.cursor_location
        self._extend_selection(row, 0)

    def action_select_line_end(self: QueryMixinHost) -> None:
        """Extend selection to line end (Shift+End)."""
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location
        end_col = len(lines[row]) if row < len(lines) else 0
        self._extend_selection(row, end_col)

    def action_select_to_start(self: QueryMixinHost) -> None:
        """Extend selection to document start (Ctrl+Shift+Home)."""
        self._extend_selection(0, 0)

    def action_select_to_end(self: QueryMixinHost) -> None:
        """Extend selection to document end (Ctrl+Shift+End)."""
        lines = self.query_input.text.split("\n")
        last_row = len(lines) - 1
        last_col = len(lines[last_row]) if lines else 0
        self._extend_selection(last_row, last_col)
