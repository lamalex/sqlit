"""Query analysis service integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.domains.query.app.query_analysis import QueryAnalysisService
from sqlit.domains.query.ui.adapters import TextualQueryAnalysisBackend

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import QueryMixinHost


class QueryAnalysisMixin:
    """Provide structural analysis for the live query document."""

    _query_analysis_service: QueryAnalysisService | None = None

    def _get_query_analysis_service(self: QueryMixinHost) -> QueryAnalysisService:
        if self._query_analysis_service is None:
            backend = TextualQueryAnalysisBackend(self.query_input)
            self._query_analysis_service = QueryAnalysisService(backend)
        return self._query_analysis_service
