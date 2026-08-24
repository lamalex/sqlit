"""Semantic SQL symbol rename prompt."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from sqlit.shared.ui.widgets import Dialog


class QueryRenameScreen(ModalScreen[str | None]):
    """Collect a logical identifier name and preview the rename scope."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    QueryRenameScreen {
        align: center middle;
        background: transparent;
    }

    #query-rename-dialog {
        width: 72;
        max-width: 92%;
        height: auto;
    }

    #query-rename-description, #query-rename-preview {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }

    #query-rename-input {
        height: 3;
        border: solid $primary;
        background: $surface;
    }
    """

    def __init__(self, name: str, occurrences: int) -> None:
        super().__init__()
        self._name = name
        self._occurrences = occurrences

    def compose(self) -> ComposeResult:
        with Dialog(
            id="query-rename-dialog",
            title="Rename SQL symbol",
            shortcuts=[("Rename", "<enter>"), ("Cancel", "<esc>")],
        ):
            yield Static(
                "Existing SQL quoting is preserved. The candidate must retain exact semantic links.",
                id="query-rename-description",
            )
            yield Static("", id="query-rename-preview")
            yield Input(value=self._name, id="query-rename-input")

    def on_mount(self) -> None:
        rename_input = self.query_one("#query-rename-input", Input)
        rename_input.focus()
        rename_input.action_select_all()
        self._update_preview(rename_input.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "query-rename-input":
            self._update_preview(event.value)

    def _update_preview(self, value: str) -> None:
        count = f"{self._occurrences} occurrence"
        if self._occurrences != 1:
            count += "s"
        self.query_one("#query-rename-preview", Static).update(f"[bold]{escape(self._name)}[/] -> [bold]{escape(value or '...')}[/]  [dim]{count}[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query-rename-input":
            self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: Any) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
