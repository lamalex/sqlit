"""Multiple selections and atomic edits for the query editor."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import wraps
from typing import Any

from sqlit.core.vim import VimMode
from sqlit.domains.query.editing.undo_history import Location, QuerySelectionSnapshot
from sqlit.shared.ui.protocols import QueryMixinHost


def per_selection(method: Callable[..., Any]) -> Callable[..., Any]:
    """Apply a non-text-editing command independently to every selection."""
    @wraps(method)
    def wrapped(self: QueryMixinHost, *args: Any, **kwargs: Any) -> Any:
        if not self._query_selection.secondary:
            return method(self, *args, **kwargs)
        snapshots = self._query_selections()
        count = self._get_and_clear_count()
        results = []
        for snapshot in snapshots:
            self._apply_query_selection(snapshot)
            if count is not None:
                self._count_buffer = str(count)
            method(self, *args, **kwargs)
            results.append(self._query_selection)
        self._install_query_selections(results)
    return wrapped


class QueryEditingMulticursorMixin:
    """The primary selection remains Textual's selection; others are semantic."""

    def _query_selections(self: QueryMixinHost) -> list[QuerySelectionSnapshot]:
        snapshot = self._query_selection
        return [*snapshot.secondary, replace(snapshot, secondary=())]

    def _install_query_selections(self: QueryMixinHost, snapshots: Sequence[QuerySelectionSnapshot]) -> None:
        # Keep the newest selection primary, and merge identical selections.
        unique: dict[tuple[Location, ...], QuerySelectionSnapshot] = {}
        for snapshot in snapshots:
            key = tuple(sorted((snapshot.start, snapshot.end)))
            unique.pop(key, None)
            unique[key] = replace(snapshot, secondary=())
        snapshots = list(unique.values())
        self._apply_query_selection(replace(snapshots[-1], secondary=tuple(snapshots[:-1])), update_chrome=True)
        self.query_input._line_cache.clear()
        self.query_input.refresh()

    def action_add_cursor_below(self: QueryMixinHost) -> None:
        """Copy the primary selection to the next line without dropping others."""
        snapshots = self._query_selections()
        snapshot = snapshots[-1]
        lines = self.query_input.text.split("\n")
        count = self._get_and_clear_count() or 1
        for _ in range(count):
            if max(snapshot.start[0], snapshot.end[0], snapshot.logical_cursor[0]) + 1 >= len(lines):
                break

            def below(location: Location) -> Location:
                row, col = location
                return row + 1, min(col, len(lines[row + 1]))

            snapshot = replace(
                snapshot, start=below(snapshot.start), end=below(snapshot.end),
                logical_cursor=below(snapshot.logical_cursor),
                visual_anchor=below(snapshot.visual_anchor) if snapshot.visual_anchor is not None else None,
                visual_cursor=below(snapshot.visual_cursor) if snapshot.visual_cursor is not None else None,
                visual_line_anchor_row=snapshot.visual_line_anchor_row + 1 if snapshot.visual_line_anchor_row is not None else None,
            )
            snapshots.append(snapshot)
        self._install_query_selections(snapshots)

    def action_keep_primary_selection(self: QueryMixinHost) -> None:
        """Drop extra cursors without changing the primary selection."""
        self._install_query_selections([replace(self._query_selection, secondary=())])

    @per_selection
    def _move_query_insert_cursor(self: QueryMixinHost, key: str) -> None:
        actions = {
            "left": "cursor_left", "right": "cursor_right", "up": "cursor_up", "down": "cursor_down",
            "home": "cursor_line_start", "end": "cursor_line_end",
        }
        select = key.startswith("shift+")
        action = actions[key.removeprefix("shift+")]
        getattr(self.query_input, f"action_{action}")(select=select)

    def _edit_query_selections(
        self: QueryMixinHost,
        replacement: str | Callable[[str], str],
        *,
        mode: VimMode | None = None,
        delete_key: str | None = None,
        after: bool = False,
        linewise: bool = False,
        preserve: bool = False,
        open_line: str | None = None,
    ) -> None:
        """Replace disjoint ranges in one transaction, remapping every cursor.

        Overlapping ranges are merged so no character can be edited twice.
        Replacement may be a string or a function of the selected text.
        """
        text = self.query_input.text
        snapshots = self._query_selections()
        edits: list[tuple[int, int, QuerySelectionSnapshot]] = []
        for snapshot in snapshots:
            start, end = sorted((snapshot.start, snapshot.end))
            a = self._location_to_offset(text, start)
            b = self._location_to_offset(text, end)
            if open_line:
                row = snapshot.logical_cursor[0]
                col = len(text.split("\n")[row]) if open_line == "below" else 0
                a = b = self._location_to_offset(text, (row, col))
            if linewise:
                lines = text.split("\n")
                a = self._location_to_offset(text, (start[0], 0))
                if end[0] + 1 < len(lines):
                    b = self._location_to_offset(text, (end[0] + 1, 0))
                else:
                    b = len(text)
                    a = max(0, a - 1)
            if after:
                a = b
            if a == b and delete_key == "backspace":
                a = max(0, a - 1)
            elif a == b and delete_key == "delete":
                b = min(len(text), b + 1)
            edits.append((a, b, snapshot))
        groups: list[tuple[int, int, list[QuerySelectionSnapshot]]] = []
        for a, b, snapshot in sorted(edits, key=lambda edit: (edit[0], edit[1])):
            if groups and (a < groups[-1][1] or a == b == groups[-1][0] == groups[-1][1]):
                old_a, old_b, members = groups[-1]
                groups[-1] = (old_a, max(old_b, b), [*members, snapshot])
            else:
                groups.append((a, b, [snapshot]))
        self._push_undo_state()
        pieces: list[str] = []
        last = 0
        delta = 0
        locations: dict[int, tuple[int, int]] = {}
        for a, b, members in groups:
            value = replacement(text[a:b]) if callable(replacement) else replacement
            pieces.extend((text[last:a], value))
            for member in members:
                locations[id(member)] = (a + delta, a + delta + len(value))
            delta += len(value) - (b - a)
            last = b
        pieces.append(text[last:])
        new_text = "".join(pieces)
        self._suppress_autocomplete_once = True
        self.query_input.text = new_text
        results = []
        for snapshot in snapshots:
            a, b = locations[id(snapshot)]
            cursor = self._offset_to_location(new_text, a if open_line == "above" else b)
            target_mode = mode or snapshot.vim_mode
            if preserve:
                old_start = min(snapshot.start, snapshot.end)
                head_delta = self._location_to_offset(text, snapshot.logical_cursor) - self._location_to_offset(text, old_start)
                head = self._offset_to_location(new_text, min(b, a + max(0, head_delta)))
                start = self._offset_to_location(new_text, a)
                end = cursor
                if snapshot.start > snapshot.end:
                    start, end = end, start
                results.append(replace(snapshot, start=start, end=end, logical_cursor=head))
                continue
            self._apply_query_selection(replace(
                snapshot, start=cursor, end=cursor, logical_cursor=cursor,
                vim_mode=target_mode, visual_anchor=None, visual_cursor=None, visual_line_anchor_row=None,
            ))
            if target_mode == VimMode.NORMAL:
                self._set_normal_selection(cursor)
            results.append(self._query_selection)
        self._install_query_selections(results)

    def _yank_query_selections(self: QueryMixinHost) -> None:
        text = self.query_input.text
        values = []
        for snapshot in self._query_selections():
            start, end = sorted((snapshot.start, snapshot.end))
            values.append(text[self._location_to_offset(text, start):self._location_to_offset(text, end)])
        self._copy_text("\n".join(values))

    def action_toggle_query_comment(self: QueryMixinHost) -> None:
        """Toggle each selected SQL line once, preserving all selections."""
        from sqlit.domains.query.editing.comments import _comment_line, _uncomment_line, is_comment_line

        self._clear_count_buffer()
        snapshots = self._query_selections()
        lines = self.query_input.text.split("\n")
        rows: set[int] = set()
        for snapshot in snapshots:
            start, end = sorted((snapshot.start, snapshot.end))
            last = end[0] - (end[1] == 0 and end[0] > start[0])
            rows.update(range(start[0], last + 1))
        nonempty = [lines[row] for row in rows if lines[row].strip()]
        uncomment = bool(nonempty) and all(is_comment_line(line) for line in nonempty)
        transform = _uncomment_line if uncomment else _comment_line
        self._push_undo_state()
        changes = {}
        for row in rows:
            old = lines[row]
            lines[row], _ = transform(old)
            indent = len(old) - len(old.lstrip())
            changes[row] = (indent, len(lines[row]) - len(old))

        def remap(location: Location) -> Location:
            row, col = location
            indent, delta = changes.get(row, (0, 0))
            return row, min(len(lines[row]), max(indent, col + delta) if col >= indent else col)

        self.query_input.text = "\n".join(lines)
        self._install_query_selections([
            replace(snapshot, start=remap(snapshot.start), end=remap(snapshot.end),
                     logical_cursor=remap(snapshot.logical_cursor),
                     visual_anchor=remap(snapshot.visual_anchor) if snapshot.visual_anchor is not None else None,
                     visual_cursor=remap(snapshot.visual_cursor) if snapshot.visual_cursor is not None else None)
            for snapshot in snapshots
        ])
