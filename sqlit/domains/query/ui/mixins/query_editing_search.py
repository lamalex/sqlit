"""Query-editor search actions."""

from __future__ import annotations

import re

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingSearchMixin:
    """Helix-style `/`, `n`, and `N` query search."""

    _last_query_search: str = ""
    _last_query_search_direction: int = 1

    def action_query_search(self: QueryMixinHost) -> None:
        """Prompt for a forward search term."""
        from sqlit.domains.query.ui.screens import QuerySearchScreen

        self._clear_count_buffer()

        def handle_result(query: str | None) -> None:
            if query is None:
                return
            query = query or self._last_query_search
            if not query:
                return
            self._last_query_search = query
            self._last_query_search_direction = 1
            self._select_query_search_match(direction=1, initial=True)

        self.push_screen(QuerySearchScreen(self._last_query_search), handle_result)

    def action_query_search_next(self: QueryMixinHost) -> None:
        """Repeat search in its original direction."""
        self._clear_count_buffer()
        self._select_query_search_match(direction=self._last_query_search_direction)

    def action_query_search_previous(self: QueryMixinHost) -> None:
        """Repeat search opposite to its original direction."""
        self._clear_count_buffer()
        self._select_query_search_match(direction=-self._last_query_search_direction)

    def _select_query_search_match(
        self: QueryMixinHost,
        *,
        direction: int,
        initial: bool = False,
    ) -> None:
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing.search import find_query_match

        query = self._last_query_search
        if not query:
            return

        text = self.query_input.text
        if initial:
            head_offset = self._location_to_offset(text, self._query_logical_head())
            start_offset = head_offset + direction
        else:
            start, end = self._ordered_selection(self.query_input.selection)
            selected = self.query_input.selected_text
            flags = re.ASCII if any(char.isupper() for char in query) else re.IGNORECASE | re.ASCII
            if re.fullmatch(re.escape(query), selected, flags):
                match_start = self._location_to_offset(text, start)
                start_offset = match_start + direction
            else:
                head_offset = self._location_to_offset(text, self._query_logical_head())
                start_offset = head_offset + direction

        match = find_query_match(text, query, start_offset, direction=direction)
        if match is None:
            self.notify(f"No matches for {query!r}", severity="warning")
            return

        start = self._offset_to_location(text, match.start)
        end = self._offset_to_location(text, match.end)
        if direction >= 0:
            self.query_input.selection = Selection(start, end)
            self._normal_cursor = self._position_before(end)
            self._normal_textual_cursor = end
        else:
            self.query_input.selection = Selection(end, start)
            self._normal_cursor = start
            self._normal_textual_cursor = start
        self._normal_selection_primary = False
