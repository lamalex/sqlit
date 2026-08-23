"""Results table focused state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class ResultsFocusedState(State):
    """Results table has focus."""

    help_category = "Results"
    keymap_context = "results"

    def _setup_actions(self) -> None:
        def has_results(app: InputContext) -> bool:
            return app.has_results

        def has_selection(app: InputContext) -> bool:
            return app.has_results and app.results_selection_active

        def has_single_cell(app: InputContext) -> bool:
            return app.has_results and app.results_selection_cell_count == 1

        def has_single_row(app: InputContext) -> bool:
            return app.has_results and app.results_selection_row_count == 1

        def has_collapsed_cell(app: InputContext) -> bool:
            return app.has_results and not app.results_selection_active

        self.allows("enter_results_selection", has_results, key="v", label="Select", help="Select cells")
        self.allows("select_results_rows", has_results, key="x", label="Select row", help="Select complete rows")
        self.allows("collapse_results_selection", has_selection, key=";", label="Collapse", help="Collapse selection")
        self.allows("yank_results_selection", has_results, key="y", label="Copy", help="Copy selection")
        self.allows("view_cell", has_collapsed_cell, key="ctrl+v", label="Preview", help="Preview cell tooltip")
        self.allows("view_cell_full", has_collapsed_cell, key="V", label="View full", help="View full cell value")
        self.allows("edit_cell", has_single_cell, key="r", label="Update cell", help="Update cell (generate UPDATE)")
        self.allows("delete_row", has_single_row, key="d", label="Delete row", help="Delete row (generate DELETE)")
        self.allows("navigate_fk", has_collapsed_cell, key="o", label="FK jump", help="Open row referenced by foreign key")
        self.allows("navigate_referrers", has_collapsed_cell, key="O", label="Refs", help="Show tables referencing this row")
        self.allows("results_yank_leader_key", has_collapsed_cell, key="Y", label="Copy menu", help="Copy/export menu")
        self.allows("clear_results", has_results, key="X", label="Clear", help="Clear results")
        self.allows("results_filter", has_results, key="slash", label="Filter", help="Filter rows")
        self.allows("results_cursor_left", has_results)  # vim h
        self.allows("results_cursor_down", has_results)  # vim j
        self.allows("results_cursor_up", has_results)  # vim k
        self.allows("results_cursor_right", has_results)  # vim l
        self.allows("rg_leader_key", has_results)
        self.allows("rg_first_row", has_results)
        self.allows("rg_last_row", has_results)
        self.allows("rg_first_column", has_results)
        self.allows("rg_last_column", has_results)
        self.allows("results_cursor_last_row", has_results)  # G alias
        self.allows("results_page_up", has_results)  # vim Ctrl+U
        self.allows("results_page_down", has_results)  # vim Ctrl+D
        self.allows("results_cursor_first_column", has_results)  # 0 alias
        self.allows("results_cursor_last_column", has_results)  # $ alias
        self.allows("results_column_picker", has_results)  # vim f/F
        self.allows("next_result_section", has_results, label="Next result", help="Next result section")
        self.allows("prev_result_section", has_results, label="Prev result", help="Previous result section")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        # No bindings when there are no results
        if not app.has_results:
            left: list[DisplayBinding] = []
            if self.parent:
                left, _ = self.parent.get_display_bindings(app)
            return left, []

        left: list[DisplayBinding] = []
        seen: set[str] = set()

        is_error = app.last_result_is_error

        if app.results_selection_active:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("yank_results_selection") or "y",
                    label="Copy",
                    action="yank_results_selection",
                )
            )
            if app.results_selection_row_count == 1:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("delete_row") or "d",
                        label="Delete row",
                        action="delete_row",
                    )
                )
            if app.results_selection_cell_count == 1:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("edit_cell") or "r",
                        label="Update",
                        action="edit_cell",
                    )
                )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("collapse_results_selection") or ";",
                    label="Collapse",
                    action="collapse_results_selection",
                )
            )
        else:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("enter_results_selection") or "v",
                    label="Select",
                    action="enter_results_selection",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("select_results_rows") or "x",
                    label="Select row",
                    action="select_results_rows",
                )
            )
            if is_error:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("yank_results_selection") or "y",
                        label="Copy error",
                        action="yank_results_selection",
                    )
                )
            else:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("view_cell_full") or "V",
                        label="View",
                        action="view_cell_full",
                    )
                )
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("edit_cell") or "r",
                        label="Update",
                        action="edit_cell",
                    )
                )
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("delete_row") or "d",
                        label="Delete",
                        action="delete_row",
                    )
                )
            if app.cursor_column_is_foreign_key:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("navigate_fk") or "o",
                        label="FK",
                        action="navigate_fk",
                    )
                )
            if app.cursor_column_is_foreign_key_target:
                left.append(
                    DisplayBinding(
                        key=resolve_display_key("navigate_referrers") or "O",
                        label="Refs",
                        action="navigate_referrers",
                    )
                )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("results_yank_leader_key") or "Y",
                    label="Copy menu",
                    action="results_yank_leader_key",
                )
            )
        left.append(
            DisplayBinding(
                key=resolve_display_key("clear_results") or "X",
                label="Clear",
                action="clear_results",
            )
        )
        left.append(
            DisplayBinding(
                key=resolve_display_key("results_filter") or "/",
                label="Filter",
                action="results_filter",
            )
        )
        if app.stacked_result_count > 1:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("next_result_section") or "tab",
                    label="Next result",
                    action="next_result_section",
                )
            )
            left.append(
                DisplayBinding(
                    key=resolve_display_key("prev_result_section") or "shift+tab",
                    label="Prev result",
                    action="prev_result_section",
                )
            )

        seen.update(
            [
                "view_cell",
                "enter_results_selection",
                "select_results_rows",
                "collapse_results_selection",
                "yank_results_selection",
                "view_cell_full",
                "delete_row",
                "navigate_fk",
                "navigate_referrers",
                "results_yank_leader_key",
                "clear_results",
                "results_filter",
                "next_result_section",
                "prev_result_section",
            ]
        )

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "results"
