"""Compact search prompt for the query editor."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input

from sqlit.shared.ui.widgets import Dialog


class QuerySearchScreen(ModalScreen[str | None]):
    """Collect a literal query-editor search term."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    QuerySearchScreen {
        align: center bottom;
        background: transparent;
    }

    #query-search-dialog {
        width: 70;
        max-width: 90%;
        height: auto;
        margin: 0 0 1 0;
    }

    #query-search-input {
        height: 3;
        border: solid $primary;
        background: $surface;
    }
    """

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Dialog(
            id="query-search-dialog",
            title="Search query",
            shortcuts=[("Search", "<enter>"), ("Cancel", "<esc>")],
        ):
            yield Input(
                value=self._initial,
                placeholder="Search...",
                id="query-search-input",
            )

    def on_mount(self) -> None:
        search_input = self.query_one("#query-search-input", Input)
        search_input.focus()
        if search_input.value:
            search_input.action_select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "query-search-input":
            self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
