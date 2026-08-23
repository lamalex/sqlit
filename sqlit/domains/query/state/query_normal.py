"""Query editor normal mode state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key
from sqlit.core.vim import VimMode


class QueryNormalModeState(State):
    """Query editor in NORMAL mode."""

    help_category = "Query Editor (Normal)"
    keymap_context = "query_normal"

    def _setup_actions(self) -> None:
        self.allows("enter_insert_mode", label="Insert Mode", help="Enter INSERT mode")
        self.allows("execute_query", label="Execute", help="Execute query")
        self.allows("execute_single_statement", label="Run Statement", help="Execute statement at cursor")
        self.allows("delete_leader_key", label="Delete", help="Delete selection")
        self.allows("yank_leader_key", label="Copy", help="Copy selection")
        self.allows("change_leader_key", label="Change", help="Change selection")
        self.allows(
            "match_leader_key",
            label="Match",
            help="Select text objects or syntax, or edit surrounds",
        )
        self.allows("collapse_selection", label="Collapse", help="Collapse selection to its head")
        self.allows("expand_syntax_selection", label="Expand Syntax", help="Expand to parent syntax node")
        self.allows("shrink_syntax_selection", label="Shrink Syntax", help="Restore previous syntax selection")
        self.allows("select_next_syntax_sibling", help="Select next syntax sibling")
        self.allows("select_previous_syntax_sibling", help="Select previous syntax sibling")
        self.allows("select_current_statement", help="Select statement at cursor")
        self.allows(
            "show_syntax_object_picker",
            label="SQL Objects",
            help="Choose a semantic object from the current statement",
        )
        self.allows("replace_selection", label="Replace", help="Replace selection with a character")
        self.allows("g_leader_key", label="Go", help="Go motions (menu)")
        self.allows("new_query", label="New", help="New query (clear all)")
        self.allows("query_search", label="Search", help="Search query text")
        self.allows("query_search_next", help="Next search match")
        self.allows("query_search_previous", help="Previous search match")
        self.allows("show_history", label="History", help="Query history")
        self.allows(
            "edit_query_in_editor",
            help="Open current query in your terminal editor",
        )
        self.allows("format_query", help="Format the current query")
        self.allows("query_library", help="Browse saved query files")
        self.allows("save_query", help="Save the current query")
        self.allows("save_query_as", help="Save the query under a new name")
        # Vim cursor movement
        self.allows("cursor_left", help="Move cursor left")
        self.allows("cursor_right", help="Move cursor right")
        self.allows("cursor_up", help="Move cursor up")
        self.allows("cursor_down", help="Move cursor down")
        self.allows("cursor_word_forward", help="Move to next word")
        self.allows("cursor_WORD_forward", help="Move to next WORD")
        self.allows("cursor_word_back", help="Move to previous word")
        self.allows("cursor_WORD_back", help="Move to previous WORD")
        self.allows("cursor_word_end", help="Move to end of word")
        self.allows("cursor_WORD_end", help="Move to end of WORD")
        self.allows("cursor_first_non_blank", help="Move to first non-blank")
        self.allows("cursor_line_start", help="Move to line start")
        self.allows("cursor_line_end", help="Move to line end")
        self.allows("cursor_last_line", help="Move to last line")
        self.allows("cursor_matching_bracket", help="Move to matching bracket")
        self.allows("cursor_find_char", help="Find char forward")
        self.allows("cursor_find_char_back", help="Find char backward")
        self.allows("cursor_till_char", help="Move till char forward")
        self.allows("cursor_till_char_back", help="Move till char backward")
        self.allows("prepend_insert_mode", help="Insert at line start")
        self.allows("append_insert_mode", help="Append after cursor")
        self.allows("append_line_end", help="Append at line end")
        # Vim open line
        self.allows("open_line_below", help="Open line below")
        self.allows("open_line_above", help="Open line above")
        # Vim delete char
        self.allows("delete_char", help="Delete character under cursor")
        # Vim delete or change
        self.allows("change_line_end_motion", help="Change to line end")
        self.allows("delete_line_end", help="Delete to line end")
        # Clipboard actions
        self.allows("select_all", help="Select all text")
        self.allows("copy_selection", help="Copy selection")
        self.allows("paste", help="Paste")
        # Selection actions
        self.allows("select_left", help="Select left")
        self.allows("select_right", help="Select right")
        self.allows("select_up", help="Select up")
        self.allows("select_down", help="Select down")
        self.allows("select_word_left", help="Select word left")
        self.allows("select_word_right", help="Select word right")
        self.allows("select_line_start", help="Select to line start")
        self.allows("select_line_end", help="Select to line end")
        self.allows("select_to_start", help="Select to start")
        self.allows("select_to_end", help="Select to end")
        # Undo/redo
        self.allows("undo", help="Undo")
        self.allows("redo", help="Redo")
        # Selection modes
        self.allows("enter_visual_mode", label="Select", help="Enter select mode")
        self.allows("enter_visual_line_mode", label="Select Line", help="Select current line")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("enter_insert_mode") or "i",
                label="Insert Mode",
                action="enter_insert_mode",
            )
        )
        seen.add("enter_insert_mode")
        left.append(
            DisplayBinding(
                key=resolve_display_key("execute_query") or "enter",
                label="Execute",
                action="execute_query",
            )
        )
        seen.add("execute_query")

        left.append(
            DisplayBinding(
                key=resolve_display_key("yank_leader_key") or "y",
                label="Copy",
                action="yank_leader_key",
            )
        )
        seen.add("yank_leader_key")

        left.append(
            DisplayBinding(
                key=resolve_display_key("delete_leader_key") or "d",
                label="Delete",
                action="delete_leader_key",
            )
        )
        seen.add("delete_leader_key")

        # Keep change and go actions available but not shown in footer
        seen.add("change_leader_key")
        seen.add("g_leader_key")

        left.append(
            DisplayBinding(
                key=resolve_display_key("show_history") or "H",
                label="History",
                action="show_history",
            )
        )
        seen.add("show_history")
        left.append(
            DisplayBinding(
                key=resolve_display_key("new_query") or "ctrl+n",
                label="New",
                action="new_query",
            )
        )
        seen.add("new_query")

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query" and app.vim_mode == VimMode.NORMAL
