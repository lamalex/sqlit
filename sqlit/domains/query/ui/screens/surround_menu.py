"""Delimiter prompt for selection surround commands."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.domains.query.editing import SURROUND_PAIRS
from sqlit.shared.ui.widgets import Dialog


class SurroundMenuScreen(ModalScreen[str | None]):
    """Collect one or two delimiters for a surround edit."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    SurroundMenuScreen {
        align: right bottom;
        background: rgba(0, 0, 0, 0);
        overlay: none;
    }

    #surround-menu {
        max-width: 34;
        margin: 0;
        border: solid $primary;
    }

    #surround-menu-content {
        width: auto;
        height: auto;
    }
    """

    def __init__(self, operation: str) -> None:
        super().__init__()
        self._operation = operation
        self._first_delimiter: str | None = None

    def compose(self) -> ComposeResult:
        with Dialog(id="surround-menu", shortcuts=[("Cancel", "esc")]):
            yield Static(self._content(), id="surround-menu-content")

    def _content(self) -> str:
        titles = {
            "add": "Add surround",
            "delete": "Delete surround",
            "replace": "Replace surround",
        }
        if self._operation == "replace" and self._first_delimiter is not None:
            prompt = "Type replacement delimiter..."
        elif self._operation == "replace":
            prompt = "Type existing delimiter..."
        else:
            prompt = "Type delimiter..."
        return f"""[bold $text-muted]{titles[self._operation]}[/]
  [dim]( )  [ ]  {{ }}  < >  ' \" `  b B[/]

[bold $warning]{prompt}[/]
  [dim]or press ESC to cancel[/]"""

    def on_key(self, event: Any) -> None:
        """Capture the requested delimiter or delimiters."""
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
            return

        char = event.character if hasattr(event, "character") else None
        if not char or char not in SURROUND_PAIRS:
            return

        if self._operation == "replace" and self._first_delimiter is None:
            self._first_delimiter = char
            self.query_one("#surround-menu-content", Static).update(self._content())
        else:
            self.dismiss((self._first_delimiter or "") + char)
        event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)
