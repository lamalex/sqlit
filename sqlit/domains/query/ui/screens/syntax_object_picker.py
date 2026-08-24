"""Filterable picker for semantic SQL objects in the current statement."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.query.app.query_analysis import SyntaxRange
from sqlit.domains.query.editing import get_selection_text
from sqlit.shared.ui.widgets import Dialog

_KIND_LABELS = {
    "statement": "Statement",
    "cte": "CTE definition",
    "cte_body": "CTE body",
    "subquery": "Subquery",
    "select_list": "SELECT list",
    "where": "WHERE clause",
    "group_by": "GROUP BY clause",
    "having": "HAVING clause",
    "order_by": "ORDER BY clause",
    "limit": "LIMIT clause",
    "returning": "RETURNING clause",
    "join_condition": "JOIN condition",
    "table_expression": "Table expression",
    "cte_reference": "CTE reference",
    "relation_alias_reference": "Relation alias reference",
    "projection_alias_reference": "Projection alias reference",
}


def syntax_kind_label(kind: str) -> str:
    """Return a user-facing label for a semantic syntax kind."""
    return _KIND_LABELS.get(kind, kind.replace("_", " ").title())


@dataclass(frozen=True)
class SyntaxPickerEntry:
    selection: SyntaxRange
    label: str
    snippet: str


class SyntaxObjectPickerScreen(ModalScreen[SyntaxRange | None]):
    """Choose a semantic SQL range from the current statement."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "submit", "Select", show=False),
        Binding("down", "cursor_down", "Next", show=False),
        Binding("up", "cursor_up", "Previous", show=False),
        Binding("ctrl+j", "cursor_down", "Next", show=False),
        Binding("ctrl+k", "cursor_up", "Previous", show=False),
    ]

    CSS = """
    SyntaxObjectPickerScreen {
        align: center middle;
        background: transparent;
    }

    #syntax-object-picker-dialog {
        width: 84;
        max-width: 92%;
        height: auto;
        max-height: 28;
    }

    #syntax-object-picker-description {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }

    #syntax-object-picker-body {
        height: auto;
        max-height: 22;
    }

    #syntax-object-picker-input {
        height: 3;
        border: solid $panel;
        background: $surface;
    }

    #syntax-object-picker-list {
        height: auto;
        max-height: 17;
        border: none;
        background: $surface;
    }
    """

    def __init__(
        self,
        text: str,
        selections: tuple[SyntaxRange, ...],
        preview: Callable[[SyntaxRange | None], None],
        *,
        title: str = "Select SQL object",
        description: str = "Objects available in the current statement. Type to filter.",
        placeholder: str = "Filter SQL objects...",
    ) -> None:
        super().__init__()
        self._entries = [self._entry(text, selection) for selection in selections]
        self._filtered: list[tuple[int, SyntaxPickerEntry]] = list(enumerate(self._entries))
        self._preview = preview
        self._title = title
        self._description = description
        self._placeholder = placeholder

    @staticmethod
    def _entry(text: str, selection: SyntaxRange) -> SyntaxPickerEntry:
        source = get_selection_text(
            text,
            selection.start.row,
            selection.start.col,
            selection.end.row,
            selection.end.col,
        )
        snippet = " ".join(source.split())
        if len(snippet) > 58:
            snippet = f"{snippet[:55]}..."
        label = syntax_kind_label(selection.kind)
        return SyntaxPickerEntry(selection, label, snippet)

    def compose(self) -> ComposeResult:
        shortcuts = [("Select", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(
            id="syntax-object-picker-dialog",
            title=self._title,
            shortcuts=shortcuts,
        ):
            yield Static(
                self._description,
                id="syntax-object-picker-description",
            )
            with Vertical(id="syntax-object-picker-body"):
                yield Input(placeholder=self._placeholder, id="syntax-object-picker-input")
                yield OptionList(*self._render_options(), id="syntax-object-picker-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#syntax-object-picker-list", OptionList)
        if option_list.option_count:
            option_list.highlighted = 0
            self._preview(self._filtered[0][1].selection)
        self.query_one("#syntax-object-picker-input", Input).focus()

    def _render_options(self) -> list[Option]:
        return [
            Option(
                f"[bold]{escape(entry.label)}[/]  [dim]{escape(entry.snippet)}[/]",
                id=str(index),
            )
            for index, entry in self._filtered
        ]

    def _rebuild_options(self, query: str) -> None:
        needle = query.strip().casefold()
        self._filtered = [(index, entry) for index, entry in enumerate(self._entries) if not needle or needle in f"{entry.label} {entry.snippet}".casefold()]
        option_list = self.query_one("#syntax-object-picker-list", OptionList)
        option_list.clear_options()
        for option in self._render_options():
            option_list.add_option(option)
        option_list.highlighted = 0 if self._filtered else None
        if self._filtered:
            self._preview(self._filtered[0][1].selection)
        else:
            self._preview(None)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "syntax-object-picker-input":
            self._rebuild_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "syntax-object-picker-input":
            self._submit_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self.dismiss(self._entries[int(event.option.id)].selection)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None:
            self._preview(self._entries[int(event.option.id)].selection)

    def action_cursor_down(self) -> None:
        option_list = self.query_one("#syntax-object-picker-list", OptionList)
        if option_list.option_count:
            option_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        option_list = self.query_one("#syntax-object-picker-list", OptionList)
        if option_list.option_count:
            option_list.action_cursor_up()

    def action_submit(self) -> None:
        self._submit_highlighted()

    def _submit_highlighted(self) -> None:
        option_list = self.query_one("#syntax-object-picker-list", OptionList)
        if not self._filtered:
            return
        highlighted = option_list.highlighted if option_list.highlighted is not None else 0
        highlighted = max(0, min(highlighted, len(self._filtered) - 1))
        self.dismiss(self._filtered[highlighted][1].selection)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: Any) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
