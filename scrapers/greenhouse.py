"""Backward-compatible Greenhouse scraper entry point.

Use ``python -m ai_job_market ingest --provider greenhouse`` for new runs.
Executing this file directly still runs the same Greenhouse ingestion pipeline.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path


# Direct execution sets sys.path to ``scrapers/``. Add the project root only
# for this legacy script so its original invocation remains supported.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_job_market.config import GREENHOUSE_COMPANIES
from ai_job_market.logging import configure_logging
from ai_job_market.pipeline.ingestion import run_ingestion
from ai_job_market.providers.greenhouse import GreenhouseProvider
from ai_job_market.text import clean_html


def fetch_jobs(company: str) -> list[dict[str, str]]:
    """Return legacy-shaped Greenhouse jobs for one company board.

    This helper preserves the original public function while delegating all
    collection and normalization behavior to the registered provider module.
    """
    result = GreenhouseProvider().scrape(
        companies=[company],
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    return [job.to_legacy_row() for job in result.jobs]


def main() -> int:
    """Run the Greenhouse-only ingestion command for legacy callers."""
    configure_logging()
    run_ingestion(
        provider_names=[GreenhouseProvider.name],
        companies_by_provider={GreenhouseProvider.name: GREENHOUSE_COMPANIES},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
