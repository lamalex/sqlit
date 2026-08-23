"""UI integration tests for structural query analysis."""

from __future__ import annotations

import pytest

from sqlit.domains.query.app.query_analysis import SyntaxRange
from sqlit.domains.query.editing import Position
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


@pytest.mark.asyncio
async def test_app_analysis_service_reads_live_query_document() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        app.query_input.text = "SELECT 1; SELECT 2;"
        await pilot.pause()

        analysis = app._get_query_analysis_service()
        assert analysis.statement_at(Position(0, 12)) == SyntaxRange(
            Position(0, 10), Position(0, 19), "statement"
        )
