"""Provider interface for normalized ATS ingestion."""

from collections.abc import Sequence
from typing import Protocol

from ai_job_market.models import ProviderRunResult


class ATSProvider(Protocol):
    """Contract that each ATS scraper must satisfy."""

    name: str

    def scrape(
        self,
        companies: Sequence[str],
        collected_at: str,
    ) -> ProviderRunResult:
        """Collect normalized job postings for configured organizations."""
