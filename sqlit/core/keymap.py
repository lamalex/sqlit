"""Core keymap definitions (UI-agnostic)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass

from sqlit.shared.core.debug_events import emit_debug_event

KEY_DISPLAY_OVERRIDES: dict[str, str] = {
    "question_mark": "?",
    "slash": "/",
    "asterisk": "*",
    "circumflex_accent": "^",
    "dollar_sign": "$",
    "percent_sign": "%",
    "space": "<space>",
    "escape": "<esc>",
    "enter": "<enter>",
    "delete": "<del>",
    "backspace": "<backspace>",
    "tab": "<tab>",
    "shift+tab": "<s-tab>",
    "left": "<left>",
    "right": "<right>",
    "up": "<up>",
    "down": "<down>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<pgup>",
    "pagedown": "<pgdn>",
}


def format_key(key: str) -> str:
    """Format a key name for display in UI hints."""
    if key in KEY_DISPLAY_OVERRIDES:
        return KEY_DISPLAY_OVERRIDES[key]
    if key.startswith("ctrl+"):
        return f"^{key.split('+', 1)[1]}"
    return key


@dataclass
class LeaderCommandDef:
    """Definition of a leader command."""

    key: str  # The key to press (e.g., "q", "e")
    action: str  # The target action (e.g., "quit", "toggle_explorer")
    label: str  # Display label
    category: str  # Category for grouping ("View", "Connection", "Actions")
    guard: str | None = None  # Guard name (resolved at runtime)
    menu: str = "leader"  # Menu ID (supports multiple leader menus)


@dataclass
class ActionKeyDef:
    """Definition of a regular action keybinding."""

    key: str  # The key to press
    action: str  # The action name
    context: str | None = None  # Optional context hint (for documentation)
    guard: str | None = None  # Guard name (resolved at runtime)
    primary: bool = True  # Primary key for display vs secondary aliases
    show: bool = False  # Whether to show in Textual's binding hints
    priority: bool = False  # Whether to give priority to this binding
    leader_command: bool = False  # Explicit direct binding for a main leader command


class KeymapProvider(ABC):
    """Abstract base class for keymap providers."""

    @abstractmethod
    def get_leader_commands(self) -> list[LeaderCommandDef]:
        """Get all leader command definitions."""
        raise NotImplementedError

    @abstractmethod
    def get_action_keys(self) -> list[ActionKeyDef]:
        """Get all regular action key definitions."""
        raise NotImplementedError

    def leader(self, action: str, menu: str | None = "leader") -> str | None:
        """Get the key for a leader command action."""
        for cmd in self.get_leader_commands():
            if cmd.action == action and (menu is None or cmd.menu == menu):
                return cmd.key
        return None

    def action(self, action_name: str) -> str | None:
        """Get the key for a regular action."""
        primary = None
        fallback = None
        for ak in self.get_action_keys():
            if ak.action != action_name:
                continue
            if fallback is None:
                fallback = ak.key
            if ak.primary and primary is None:
                primary = ak.key
        return primary or fallback

    def keys_for_action(self, action_name: str, *, include_secondary: bool = True) -> list[str]:
        """Get all keys for an action, primary first."""
        primary_keys: list[str] = []
        secondary_keys: list[str] = []
        seen: set[str] = set()
        for ak in self.get_action_keys():
            if ak.action != action_name:
                continue
            if ak.key in seen:
                continue
            seen.add(ak.key)
            if ak.primary:
                primary_keys.append(ak.key)
            elif include_secondary:
                secondary_keys.append(ak.key)
        return primary_keys + secondary_keys

    def actions_for_key(self, key: str) -> list[str]:
        """Get all actions bound to a key."""
        return [ak.action for ak in self.get_action_keys() if ak.key == key]


class DefaultKeymapProvider(KeymapProvider):
    """Default keymap with hardcoded bindings."""

    def __init__(self) -> None:
        self._leader_commands_cache: list[LeaderCommandDef] | None = None
        self._action_keys_cache: list[ActionKeyDef] | None = None
        self._leader_emitted: bool = False
        self._action_emitted: bool = False

    def _emit_leader_keybindings(self, commands: list[LeaderCommandDef]) -> None:
        for cmd in commands:
            emit_debug_event(
                "keybinding.register",
                category="keybinding",
                kind="leader",
                provider=self.__class__.__name__,
                key=cmd.key,
                action=cmd.action,
                label=cmd.label,
                group=cmd.category,
                menu=cmd.menu,
                guard=cmd.guard,
            )

    def _emit_action_keybindings(self, bindings: list[ActionKeyDef]) -> None:
        for binding in bindings:
            emit_debug_event(
                "keybinding.register",
                category="keybinding",
                kind="action",
                provider=self.__class__.__name__,
                key=binding.key,
                action=binding.action,
                context=binding.context,
                guard=binding.guard,
                primary=binding.primary,
                show=binding.show,
                priority=binding.priority,
            )

    def _ensure_leader_commands(self) -> list[LeaderCommandDef]:
        if self._leader_commands_cache is None:
            self._leader_commands_cache = self._build_leader_commands()
        return self._leader_commands_cache

    def _ensure_action_keys(self) -> list[ActionKeyDef]:
        if self._action_keys_cache is None:
            self._action_keys_cache = self._build_action_keys()
        return self._action_keys_cache

    def get_leader_commands(self) -> list[LeaderCommandDef]:
        commands = self._ensure_leader_commands()
        if not self._leader_emitted:
            self._emit_leader_keybindings(commands)
            self._leader_emitted = True
        return list(commands)

    def get_action_keys(self) -> list[ActionKeyDef]:
        bindings = self._ensure_action_keys()
        if not self._action_emitted:
            self._emit_action_keybindings(bindings)
            self._action_emitted = True
        return list(bindings)

    def _build_leader_commands(self) -> list[LeaderCommandDef]:
        return [
            # View
            LeaderCommandDef("e", "toggle_explorer", "Toggle Explorer", "View"),
            LeaderCommandDef("f", "toggle_fullscreen", "Toggle Maximize", "View"),
            # Connection
            LeaderCommandDef("c", "show_connection_picker", "Connect", "Connection"),
            LeaderCommandDef("x", "disconnect", "Disconnect", "Connection", guard="has_connection"),
            # Actions
            LeaderCommandDef("z", "cancel_operation", "Cancel", "Actions", guard="query_executing"),
            LeaderCommandDef("t", "change_theme", "Change Theme", "Actions"),
            LeaderCommandDef(
                "o",
                "edit_query_in_editor",
                "Open in editor",
                "Actions",
            ),
            LeaderCommandDef(
                "p",
                "format_query",
                "Format Query",
                "Actions",
                guard="query_focused",
            ),
            LeaderCommandDef("q", "query_library", "Query Library", "Actions"),
            LeaderCommandDef("w", "save_query", "Save Query", "Actions"),
            LeaderCommandDef("S", "save_query_as", "Save Query As", "Actions"),
            LeaderCommandDef("r", "execute_query_atomic", "Run transaction", "Actions", guard="query_focused"),
            LeaderCommandDef("s", "execute_single_statement", "Run statement", "Actions", guard="query_focused"),
            LeaderCommandDef("h", "show_help", "Help", "Actions"),
            LeaderCommandDef("k", "show_keybinding_editor", "Edit Keybindings", "Actions"),
            LeaderCommandDef("space", "telescope", "Telescope", "Actions"),
            LeaderCommandDef("slash", "telescope_filter", "Telescope Search", "Actions"),
            # Helix-style text object selection (mi{object}, ma{object})
            LeaderCommandDef("i", "inner", "Select inside...", "Select", menu="match"),
            LeaderCommandDef("a", "around", "Select around...", "Select", menu="match"),
            LeaderCommandDef("s", "surround_add", "Add surround...", "Surround", menu="match"),
            LeaderCommandDef("d", "surround_delete", "Delete surround...", "Surround", menu="match"),
            LeaderCommandDef("r", "surround_replace", "Replace surround...", "Surround", menu="match"),
            LeaderCommandDef("S", "syntax_statement", "Select statement", "Syntax", menu="match"),
            LeaderCommandDef("e", "syntax_cte", "Select CTE", "Syntax", menu="match"),
            LeaderCommandDef("E", "syntax_cte_body", "Select CTE body", "Syntax", menu="match"),
            LeaderCommandDef("q", "syntax_subquery", "Select subquery", "Syntax", menu="match"),
            LeaderCommandDef("l", "syntax_select_list", "Select SELECT list", "Syntax", menu="match"),
            LeaderCommandDef("c", "syntax_clause", "Select clause", "Syntax", menu="match"),
            LeaderCommandDef("j", "syntax_join_condition", "Select JOIN condition", "Syntax", menu="match"),
            LeaderCommandDef("t", "syntax_table_expression", "Select table expression", "Syntax", menu="match"),
            # Helix window mode
            LeaderCommandDef("h", "left", "Focus Explorer", "Window", menu="window"),
            LeaderCommandDef("k", "up", "Focus Query", "Window", menu="window"),
            LeaderCommandDef("j", "down", "Focus Results", "Window", menu="window"),
            LeaderCommandDef("l", "right", "Focus right pane", "Window", menu="window"),
            # Helix goto menu
            LeaderCommandDef("g", "first_line", "Go to first line", "Go to", menu="g"),
            LeaderCommandDef("e", "last_line", "Go to last line", "Go to", menu="g"),
            LeaderCommandDef("h", "line_start", "Go to line start", "Go to", menu="g"),
            LeaderCommandDef("l", "line_end", "Go to line end", "Go to", menu="g"),
            LeaderCommandDef("s", "first_non_blank", "Go to first non-blank", "Go to", menu="g"),
            LeaderCommandDef("c", "comment", "Toggle comment...", "Toggle", menu="g"),
            # gc comment menu (vim-style)
            LeaderCommandDef("c", "line", "Toggle line comment", "Comment", menu="gc"),
            LeaderCommandDef("j", "down", "Comment line down", "Comment", menu="gc"),
            LeaderCommandDef("k", "up", "Comment line up", "Comment", menu="gc"),
            LeaderCommandDef("G", "to_end", "Comment to end", "Comment", menu="gc"),
            LeaderCommandDef("s", "selection", "Toggle selection", "Comment", menu="gc"),
            LeaderCommandDef("S", "statement", "Toggle statement", "Comment", menu="gc"),
            # ry results yank menu
            LeaderCommandDef("c", "cell", "Copy cell", "Copy", menu="ry"),
            LeaderCommandDef("y", "row", "Copy row", "Copy", menu="ry"),
            LeaderCommandDef("a", "all", "Copy all", "Copy", menu="ry"),
            LeaderCommandDef("o", "columns", "Copy columns...", "Copy", menu="ry"),
            LeaderCommandDef("f", "format", "Copy as...", "Copy", menu="ry"),
            LeaderCommandDef("e", "export", "Export...", "Export", menu="ry"),
            # rye results export menu
            LeaderCommandDef("c", "csv", "Export as CSV", "Export", menu="rye"),
            LeaderCommandDef("j", "json", "Export as JSON", "Export", menu="rye"),
            LeaderCommandDef("m", "markdown", "Export as Markdown", "Export", menu="rye"),
            LeaderCommandDef("o", "columns", "Columns...", "Export", menu="rye"),
            # ryf copy-as format picker
            LeaderCommandDef("m", "markdown", "Copy as Markdown...", "Copy as", menu="ryf"),
            LeaderCommandDef("j", "json", "Copy as JSON...", "Copy as", menu="ryf"),
            LeaderCommandDef("c", "csv", "Copy as CSV...", "Copy as", menu="ryf"),
            LeaderCommandDef("v", "values", "Copy column values", "Copy as", menu="ryf"),
            # ryfm markdown scope
            LeaderCommandDef("c", "cell", "Cell as Markdown", "Copy as", menu="ryfm"),
            LeaderCommandDef("y", "row", "Row as Markdown", "Copy as", menu="ryfm"),
            LeaderCommandDef("a", "all", "All as Markdown", "Copy as", menu="ryfm"),
            LeaderCommandDef("o", "columns", "Columns as Markdown...", "Copy as", menu="ryfm"),
            # ryfj json scope
            LeaderCommandDef("c", "cell", "Cell as JSON", "Copy as", menu="ryfj"),
            LeaderCommandDef("y", "row", "Row as JSON", "Copy as", menu="ryfj"),
            LeaderCommandDef("a", "all", "All as JSON", "Copy as", menu="ryfj"),
            LeaderCommandDef("o", "columns", "Columns as JSON...", "Copy as", menu="ryfj"),
            # ryfc csv scope
            LeaderCommandDef("c", "cell", "Cell as CSV", "Copy as", menu="ryfc"),
            LeaderCommandDef("y", "row", "Row as CSV", "Copy as", menu="ryfc"),
            LeaderCommandDef("a", "all", "All as CSV", "Copy as", menu="ryfc"),
            LeaderCommandDef("o", "columns", "Columns as CSV...", "Copy as", menu="ryfc"),
            # Helix-style results goto menu
            LeaderCommandDef("g", "first_row", "Go to first row", "Go to", menu="rg"),
            LeaderCommandDef("e", "last_row", "Go to last row", "Go to", menu="rg"),
            LeaderCommandDef("h", "first_column", "Go to first column", "Go to", menu="rg"),
            LeaderCommandDef("l", "last_column", "Go to last column", "Go to", menu="rg"),
            # vy value view yank menu (tree mode)
            LeaderCommandDef("y", "value", "Copy value", "Copy", menu="vy"),
            LeaderCommandDef("f", "field", "Copy field", "Copy", menu="vy"),
            LeaderCommandDef("a", "all", "Copy all", "Copy", menu="vy"),
        ]

    def _build_action_keys(self) -> list[ActionKeyDef]:
        return [
            # Tree actions
            ActionKeyDef("n", "new_connection", "tree"),
            ActionKeyDef("v", "enter_tree_visual_mode", "tree"),
            ActionKeyDef("escape", "exit_tree_visual_mode", "tree_visual"),
            ActionKeyDef("v", "exit_tree_visual_mode", "tree_visual", primary=False),
            ActionKeyDef("escape", "clear_connection_selection", "tree"),
            ActionKeyDef("s", "select_table", "tree"),
            ActionKeyDef("f", "refresh_tree", "tree"),
            ActionKeyDef("R", "refresh_tree", "tree", primary=False),
            ActionKeyDef("e", "edit_connection", "tree"),
            ActionKeyDef("r", "rename_saved_query", "tree"),
            ActionKeyDef("d", "delete_saved_query", "tree"),
            ActionKeyDef("delete", "delete_saved_query", "tree", primary=False),
            ActionKeyDef("M", "rename_connection_folder", "tree"),
            ActionKeyDef("d", "delete_connection_folder", "tree"),
            ActionKeyDef("delete", "delete_connection_folder", "tree", primary=False),
            ActionKeyDef("d", "delete_connection", "tree"),
            ActionKeyDef("delete", "delete_connection", "tree", primary=False),
            ActionKeyDef("D", "duplicate_connection", "tree"),
            ActionKeyDef("m", "move_connection_to_folder", "tree"),
            ActionKeyDef("x", "disconnect", "tree"),
            ActionKeyDef("z", "collapse_tree", "tree"),
            ActionKeyDef("j", "tree_cursor_down", "tree"),
            ActionKeyDef("down", "tree_cursor_down", "tree", primary=False),
            ActionKeyDef("k", "tree_cursor_up", "tree"),
            ActionKeyDef("up", "tree_cursor_up", "tree", primary=False),
            ActionKeyDef("slash", "tree_filter", "tree"),
            ActionKeyDef("escape", "tree_filter_close", "tree_filter"),
            ActionKeyDef("enter", "tree_filter_accept", "tree_filter"),
            # Global
            ActionKeyDef("space", "leader_key", "global", priority=True),
            ActionKeyDef("ctrl+w", "window_leader_key", "global", priority=True),
            # quit is intentionally not in the user-overridable keymap;
            # it lives only as Textual's built-in App.BINDINGS (ctrl+q) and
            # the `:q` command. Keeping it un-rebindable avoids the footgun
            # of a user accidentally locking themselves out of the exit key.
            ActionKeyDef("escape", "cancel_operation", "global"),
            ActionKeyDef("question_mark", "show_help", "global"),
            ActionKeyDef("colon", "enter_command_mode", "global"),
            ActionKeyDef("shift+semicolon", "enter_command_mode", "global", primary=False),
            ActionKeyDef(":", "enter_command_mode", "global", primary=False),
            # Query (normal mode)
            ActionKeyDef("i", "enter_insert_mode", "query_normal"),
            ActionKeyDef("I", "prepend_insert_mode", "query_normal"),
            ActionKeyDef("o", "open_line_below", "query_normal"),
            ActionKeyDef("O", "open_line_above", "query_normal"),
            ActionKeyDef("enter", "execute_query", "query_normal"),
            ActionKeyDef("p", "paste", "query_normal"),
            ActionKeyDef("y", "yank_leader_key", "query_normal"),
            ActionKeyDef("c", "change_leader_key", "query_normal"),
            ActionKeyDef("m", "match_leader_key", "query_normal"),
            ActionKeyDef("semicolon", "collapse_selection", "query_normal"),
            ActionKeyDef(";", "collapse_selection", "query_normal", primary=False),
            ActionKeyDef("alt+o", "expand_syntax_selection", "query_normal"),
            ActionKeyDef("alt+i", "shrink_syntax_selection", "query_normal"),
            ActionKeyDef("alt+n", "select_next_syntax_sibling", "query_normal"),
            ActionKeyDef("alt+p", "select_previous_syntax_sibling", "query_normal"),
            ActionKeyDef("g", "g_leader_key", "query_normal"),
            ActionKeyDef("backspace", "show_history", "query_normal"),
            ActionKeyDef("ctrl+n", "new_query", "query_normal"),
            ActionKeyDef("slash", "query_search", "query_normal"),
            ActionKeyDef("n", "query_search_next", "query_normal"),
            ActionKeyDef("N", "query_search_previous", "query_normal"),
            ActionKeyDef("d", "delete_leader_key", "query_normal"),
            ActionKeyDef("C", "change_line_end_motion", "query_normal"),
            ActionKeyDef("D", "delete_line_end", "query_normal"),
            ActionKeyDef("u", "undo", "query_normal"),
            ActionKeyDef("ctrl+r", "redo", "query_normal"),
            # Vim cursor movement (normal mode)
            ActionKeyDef("h", "cursor_left", "query_normal"),
            ActionKeyDef("j", "cursor_down", "query_normal"),
            ActionKeyDef("k", "cursor_up", "query_normal"),
            ActionKeyDef("l", "cursor_right", "query_normal"),
            ActionKeyDef("w", "cursor_word_forward", "query_normal"),
            ActionKeyDef("W", "cursor_WORD_forward", "query_normal"),
            ActionKeyDef("b", "cursor_word_back", "query_normal"),
            ActionKeyDef("B", "cursor_WORD_back", "query_normal"),
            ActionKeyDef("e", "cursor_word_end", "query_normal"),
            ActionKeyDef("E", "cursor_WORD_end", "query_normal"),
            ActionKeyDef("0", "cursor_line_start", "query_normal"),
            ActionKeyDef("circumflex_accent", "cursor_first_non_blank", "query_normal"),
            ActionKeyDef("dollar_sign", "cursor_line_end", "query_normal"),
            ActionKeyDef("G", "cursor_last_line", "query_normal"),
            ActionKeyDef("percent_sign", "cursor_matching_bracket", "query_normal"),
            ActionKeyDef("f", "cursor_find_char", "query_normal"),
            ActionKeyDef("F", "cursor_find_char_back", "query_normal"),
            ActionKeyDef("t", "cursor_till_char", "query_normal"),
            ActionKeyDef("T", "cursor_till_char_back", "query_normal"),
            ActionKeyDef("v", "enter_visual_mode", "query_normal"),
            ActionKeyDef("x", "enter_visual_line_mode", "query_normal"),
            ActionKeyDef("V", "enter_visual_line_mode", "query_normal", primary=False),
            ActionKeyDef("a", "append_insert_mode", "query_normal"),
            ActionKeyDef("A", "append_line_end", "query_normal"),
            ActionKeyDef("r", "replace_selection", "query_normal"),
            # Query (visual mode - charwise)
            ActionKeyDef("escape", "exit_visual_mode", "query_visual"),
            ActionKeyDef("v", "exit_visual_mode", "query_visual", primary=False),
            ActionKeyDef("x", "switch_to_visual_line_mode", "query_visual"),
            ActionKeyDef("V", "switch_to_visual_line_mode", "query_visual", primary=False),
            ActionKeyDef("y", "visual_yank", "query_visual"),
            ActionKeyDef("d", "visual_delete", "query_visual"),
            ActionKeyDef("c", "visual_change", "query_visual"),
            ActionKeyDef("enter", "visual_execute", "query_visual"),
            ActionKeyDef("m", "match_leader_key", "query_visual"),
            ActionKeyDef("semicolon", "collapse_selection", "query_visual"),
            ActionKeyDef(";", "collapse_selection", "query_visual", primary=False),
            ActionKeyDef("h", "cursor_left", "query_visual"),
            ActionKeyDef("j", "cursor_down", "query_visual"),
            ActionKeyDef("k", "cursor_up", "query_visual"),
            ActionKeyDef("l", "cursor_right", "query_visual"),
            ActionKeyDef("w", "cursor_word_forward", "query_visual"),
            ActionKeyDef("W", "cursor_WORD_forward", "query_visual"),
            ActionKeyDef("b", "cursor_word_back", "query_visual"),
            ActionKeyDef("B", "cursor_WORD_back", "query_visual"),
            ActionKeyDef("0", "cursor_line_start", "query_visual"),
            ActionKeyDef("circumflex_accent", "cursor_first_non_blank", "query_visual"),
            ActionKeyDef("dollar_sign", "cursor_line_end", "query_visual"),
            ActionKeyDef("G", "cursor_last_line", "query_visual"),
            ActionKeyDef("g", "g_leader_key", "query_visual"),
            ActionKeyDef("percent_sign", "cursor_matching_bracket", "query_visual"),
            ActionKeyDef("f", "cursor_find_char", "query_visual"),
            ActionKeyDef("F", "cursor_find_char_back", "query_visual"),
            ActionKeyDef("t", "cursor_till_char", "query_visual"),
            ActionKeyDef("T", "cursor_till_char_back", "query_visual"),
            ActionKeyDef("down", "cursor_down", "query_visual", primary=False),
            ActionKeyDef("up", "cursor_up", "query_visual", primary=False),
            ActionKeyDef("left", "cursor_left", "query_visual", primary=False),
            ActionKeyDef("right", "cursor_right", "query_visual", primary=False),
            # Query (visual line mode)
            ActionKeyDef("escape", "exit_visual_line_mode", "query_visual_line"),
            ActionKeyDef("V", "exit_visual_line_mode", "query_visual_line", primary=False),
            ActionKeyDef("v", "switch_to_visual_mode", "query_visual_line"),
            ActionKeyDef("y", "visual_line_yank", "query_visual_line"),
            ActionKeyDef("d", "visual_line_delete", "query_visual_line"),
            ActionKeyDef("c", "visual_line_change", "query_visual_line"),
            ActionKeyDef("m", "match_leader_key", "query_visual_line"),
            ActionKeyDef("semicolon", "collapse_selection", "query_visual_line"),
            ActionKeyDef(";", "collapse_selection", "query_visual_line", primary=False),
            ActionKeyDef("j", "cursor_down", "query_visual_line"),
            ActionKeyDef("x", "cursor_down", "query_visual_line", primary=False),
            ActionKeyDef("k", "cursor_up", "query_visual_line"),
            ActionKeyDef("G", "cursor_last_line", "query_visual_line"),
            ActionKeyDef("g", "g_leader_key", "query_visual_line"),
            ActionKeyDef("down", "cursor_down", "query_visual_line", primary=False),
            ActionKeyDef("up", "cursor_up", "query_visual_line", primary=False),
            ActionKeyDef("enter", "visual_line_execute", "query_visual_line"),
            # Query (insert mode)
            ActionKeyDef("escape", "exit_insert_mode", "query_insert"),
            ActionKeyDef("ctrl+enter", "execute_query_insert", "query_insert"),
            # autocomplete_accept lives in the 'autocomplete' context below;
            # the query_insert context still acquires it implicitly when the
            # dropdown is visible.
            # Query (autocomplete)
            ActionKeyDef("ctrl+j", "autocomplete_next", "autocomplete"),
            ActionKeyDef("down", "autocomplete_next", "autocomplete", primary=False),
            ActionKeyDef("ctrl+k", "autocomplete_prev", "autocomplete"),
            ActionKeyDef("up", "autocomplete_prev", "autocomplete", primary=False),
            ActionKeyDef("tab", "autocomplete_accept", "autocomplete"),
            ActionKeyDef("escape", "autocomplete_close", "autocomplete"),
            # Clipboard (only in insert mode for vim consistency)
            ActionKeyDef("ctrl+a", "select_all", "query_insert"),
            ActionKeyDef("ctrl+c", "copy_selection", "query_insert"),
            ActionKeyDef("ctrl+v", "paste", "query_insert"),
            ActionKeyDef("ctrl+z", "undo", "global"),
            ActionKeyDef("ctrl+y", "redo", "global"),
            # Results
            ActionKeyDef("v", "enter_results_selection", "results"),
            ActionKeyDef("V", "view_cell_full", "results"),
            ActionKeyDef("ctrl+v", "view_cell", "results"),
            ActionKeyDef("r", "edit_cell", "results"),
            ActionKeyDef("u", "edit_cell", "results", primary=False),
            ActionKeyDef("d", "delete_row", "results"),
            ActionKeyDef("o", "navigate_fk", "results"),
            ActionKeyDef("O", "navigate_referrers", "results"),
            ActionKeyDef("y", "yank_results_selection", "results"),
            ActionKeyDef("Y", "results_yank_leader_key", "results"),
            ActionKeyDef("x", "select_results_rows", "results"),
            ActionKeyDef("X", "clear_results", "results"),
            ActionKeyDef("semicolon", "collapse_results_selection", "results"),
            ActionKeyDef(";", "collapse_results_selection", "results", primary=False),
            ActionKeyDef("escape", "collapse_results_selection", "results", primary=False),
            ActionKeyDef("slash", "results_filter", "results"),
            ActionKeyDef("h", "results_cursor_left", "results"),
            ActionKeyDef("j", "results_cursor_down", "results"),
            ActionKeyDef("k", "results_cursor_up", "results"),
            ActionKeyDef("l", "results_cursor_right", "results"),
            ActionKeyDef("g", "rg_leader_key", "results"),
            ActionKeyDef("G", "results_cursor_last_row", "results"),
            ActionKeyDef("ctrl+u", "results_page_up", "results"),
            ActionKeyDef("ctrl+d", "results_page_down", "results"),
            ActionKeyDef("0", "results_cursor_first_column", "results"),
            ActionKeyDef("dollar_sign", "results_cursor_last_column", "results"),
            ActionKeyDef("f", "results_column_picker", "results"),
            ActionKeyDef("F", "results_column_picker", "results", primary=False),
            ActionKeyDef("tab", "next_result_section", "results"),
            ActionKeyDef("shift+tab", "prev_result_section", "results"),
            ActionKeyDef("z", "toggle_result_section", "results"),
            ActionKeyDef("escape", "results_filter_close", "results_filter"),
            ActionKeyDef("enter", "results_filter_accept", "results_filter"),
            # Value view
            ActionKeyDef("q", "close_value_view", "value_view"),
            ActionKeyDef("escape", "close_value_view", "value_view"),
            ActionKeyDef("y", "copy_value_view", "value_view"),
            ActionKeyDef("t", "toggle_value_view_mode", "value_view"),
            ActionKeyDef("z", "collapse_all_json_nodes", "value_view"),
            ActionKeyDef("Z", "expand_all_json_nodes", "value_view"),
            # Error dialog (screen-local — action methods live on ErrorScreen,
            # not the App; the validator skips this context for that reason)
            ActionKeyDef("y", "error_copy_message", "error_dialog"),
            # Connection editor (screen-local, same as above)
            ActionKeyDef("ctrl+s", "connection_save", "connection_editor"),
            ActionKeyDef("ctrl+t", "connection_test", "connection_editor"),
            ActionKeyDef("ctrl+d", "connection_install_driver", "connection_editor"),
        ]


# Global keymap instance
_keymap_provider: KeymapProvider | None = None


def get_keymap() -> KeymapProvider:
    """Get the current keymap provider."""
    global _keymap_provider
    if _keymap_provider is None:
        _keymap_provider = DefaultKeymapProvider()
    return _keymap_provider


def set_keymap(provider: KeymapProvider) -> None:
    """Set the keymap provider (for testing or custom keymaps)."""
    global _keymap_provider
    _keymap_provider = provider
    emit_keybinding_snapshot(provider)


def reset_keymap() -> None:
    """Reset to default keymap provider."""
    global _keymap_provider
    _keymap_provider = None


def emit_keybinding_snapshot(provider: KeymapProvider | None = None) -> None:
    """Emit debug events for the current keymap bindings."""
    keymap = provider or get_keymap()
    if hasattr(keymap, "_ensure_leader_commands"):
        commands = keymap._ensure_leader_commands()  # type: ignore[attr-defined]
    else:
        commands = keymap.get_leader_commands()
    for cmd in commands:
        emit_debug_event(
            "keybinding.register",
            category="keybinding",
            source="snapshot",
            kind="leader",
            provider=keymap.__class__.__name__,
            key=cmd.key,
            action=cmd.action,
            label=cmd.label,
            group=cmd.category,
            menu=cmd.menu,
            guard=cmd.guard,
        )
    if hasattr(keymap, "_leader_emitted"):
        try:
            keymap._leader_emitted = True  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(keymap, "_ensure_action_keys"):
        bindings = keymap._ensure_action_keys()  # type: ignore[attr-defined]
    else:
        bindings = keymap.get_action_keys()
    for binding in bindings:
        emit_debug_event(
            "keybinding.register",
            category="keybinding",
            source="snapshot",
            kind="action",
            provider=keymap.__class__.__name__,
            key=binding.key,
            action=binding.action,
            context=binding.context,
            guard=binding.guard,
            primary=binding.primary,
            show=binding.show,
            priority=binding.priority,
        )
    if hasattr(keymap, "_action_emitted"):
        try:
            keymap._action_emitted = True  # type: ignore[attr-defined]
        except Exception:
            pass


def build_textual_keymap(provider: KeymapProvider) -> dict[str, str]:
    """Build a Textual-compatible keymap dict from a KeymapProvider.

    Groups action keys by action name (across contexts) and joins the keys
    with commas — Textual's set_keymap accepts comma-separated key lists.
    Use the result with ``App.set_keymap(...)`` so that Bindings with
    matching ``id=`` get their keys overridden at runtime.
    """
    by_action: dict[str, list[str]] = defaultdict(list)
    for ak in provider.get_action_keys():
        if ak.key not in by_action[ak.action]:
            by_action[ak.action].append(ak.key)
    return {action: ",".join(keys) for action, keys in by_action.items()}
