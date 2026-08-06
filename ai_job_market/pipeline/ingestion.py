"""Orchestrate provider runs and persist the canonical jobs CSV."""

import csv
import logging
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_job_market.config import (
    JOBS_MASTER_PATH,
    ensure_project_directories,
)
from ai_job_market.models import JOB_COLUMNS, JobPosting, ProviderRunResult
from ai_job_market.providers.base import ATSProvider
from ai_job_market.providers.registry import (
    available_providers,
    companies_for_provider,
    create_provider,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Persisted result of one ingestion command."""

    output_path: Path
    job_count: int
    provider_results: tuple[ProviderRunResult, ...]

    @property
    def failed_company_count(self) -> int:
        return sum(
            len(result.failed_companies) for result in self.provider_results
        )

    @property
    def detail_failure_count(self) -> int:
        return sum(
            result.detail_failure_count for result in self.provider_results
        )


def run_ingestion(
    provider_names: Sequence[str] | None = None,
    *,
    companies_by_provider: Mapping[str, Sequence[str]] | None = None,
    providers: Iterable[ATSProvider] | None = None,
    output_path: Path | None = None,
    collected_at: str | None = None,
) -> IngestionSummary:
    """Run selected providers and atomically replace the master jobs dataset."""
    selected_names = tuple(provider_names or available_providers())
    if not selected_names:
        raise ValueError("At least one provider must be selected")

    configured_companies = companies_by_provider
    provider_instances = list(providers) if providers is not None else [
        create_provider(name) for name in selected_names
    ]
    if not provider_instances:
        raise ValueError("At least one provider instance must be supplied")

    run_timestamp = collected_at or datetime.now(timezone.utc).isoformat()
    results: list[ProviderRunResult] = []
    all_jobs: list[JobPosting] = []

    for provider in provider_instances:
        companies = (
            configured_companies.get(provider.name)
            if configured_companies is not None
            else companies_for_provider(provider.name)
        )
        if companies is None:
            raise ValueError(f"No companies configured for provider '{provider.name}'")

        LOGGER.info(
            "Starting provider ingestion",
            extra={
                "event": "provider_ingestion_started",
                "provider": provider.name,
                "company": ",".join(companies),
            },
        )
        result = provider.scrape(companies, run_timestamp)
        if result.provider != provider.name:
            raise ValueError("Provider result name does not match provider instance")

        results.append(result)
        all_jobs.extend(result.jobs)
        LOGGER.info(
            "Completed provider ingestion",
            extra={
                "event": "provider_ingestion_completed",
                "provider": provider.name,
                "job_count": len(result.jobs),
                "failed_company_count": len(result.failed_companies),
                "detail_failure_count": result.detail_failure_count,
            },
        )

    validate_job_postings(all_jobs)
    destination = output_path or JOBS_MASTER_PATH
    ensure_project_directories()
    write_jobs_csv(all_jobs, destination)

    summary = IngestionSummary(
        output_path=destination,
        job_count=len(all_jobs),
        provider_results=tuple(results),
    )
    LOGGER.info(
        "Saved master jobs dataset",
        extra={
            "event": "ingestion_succeeded",
            "output_path": destination,
            "job_count": summary.job_count,
            "failed_company_count": summary.failed_company_count,
            "detail_failure_count": summary.detail_failure_count,
        },
    )
    return summary


def validate_job_postings(postings: Sequence[JobPosting]) -> None:
    """Prevent an empty or duplicate scrape from replacing the master dataset."""
    if not postings:
        raise ValueError("Ingestion produced no job postings; existing data was kept")

    identities = [posting.identity for posting in postings]
    duplicate_count = len(identities) - len(set(identities))
    if duplicate_count:
        raise ValueError(
            f"Ingestion produced {duplicate_count} duplicate provider job identities"
        )


def write_jobs_csv(postings: Sequence[JobPosting], destination: Path) -> None:
    """Write job records atomically so readers never observe a partial CSV."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(temporary_file, fieldnames=JOB_COLUMNS)
            writer.writeheader()
            writer.writerows(posting.to_csv_row() for posting in postings)

        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        raise
