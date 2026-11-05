"""Orchestrate provider runs and persist the canonical jobs CSV."""

import csv
import logging
import os
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_job_market.config import (
    INGESTION_COMPANY_RESULTS_DIR,
    INGESTION_JOB_EVENTS_DIR,
    INGESTION_JOB_LIFECYCLE_DIR,
    INGESTION_JOB_OBSERVATIONS_DIR,
    INGESTION_RUNS_DIR,
    JOBS_MASTER_PATH,
    ensure_project_directories,
)
from ai_job_market.etl.io import append_jsonl_records, write_json_atomic, write_jsonl_atomic
from ai_job_market.history import record_company_job_history
from ai_job_market.lifecycle import process_company_lifecycle_result
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
    run_id: str | None = None

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
    runs_dir: Path | None = None,
    company_results_dir: Path | None = None,
    job_observations_dir: Path | None = None,
    job_events_dir: Path | None = None,
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

    ensure_project_directories()
    run_timestamp = collected_at or datetime.now(timezone.utc).isoformat()
    run_id = _build_run_id(run_timestamp)
    run_metadata_path = (runs_dir or INGESTION_RUNS_DIR) / f"{run_id}.json"
    company_results_path = (
        company_results_dir or INGESTION_COMPANY_RESULTS_DIR
    ) / f"{run_id}.jsonl"

    run_record: dict[str, object] = {
        "run_id": run_id,
        "provider": ",".join(provider.name for provider in provider_instances),
        "started_at": run_timestamp,
        "completed_at": None,
        "status": "running",
        "total_companies_attempted": 0,
        "total_companies_succeeded": 0,
        "total_companies_failed": 0,
        "total_jobs_observed": 0,
        "error_summary": {},
    }
    write_json_atomic(run_record, run_metadata_path)

    results: list[ProviderRunResult] = []
    all_jobs: list[JobPosting] = []
    all_company_results: list[dict[str, object]] = []

    def _refresh_run_record_state() -> None:
        total_companies_attempted = len(all_company_results)
        total_companies_succeeded = sum(
            1
            for item in all_company_results
            if item["status"] == "success"
        )
        total_companies_failed = sum(
            1
            for item in all_company_results
            if item["status"] in {"failed", "partial"}
        )
        error_summary = {
            "failed_companies": [
                {
                    "provider": item["provider"],
                    "company": item["company_slug"],
                    "error_code": item["error_code"],
                    "error_details": item["error_details"],
                }
                for item in all_company_results
                if item["status"] in {"failed", "partial"}
            ],
            "partial_companies": [
                item["company_slug"]
                for item in all_company_results
                if item["status"] == "partial"
            ],
        }
        run_record.update(
            {
                "completed_at": None,
                "status": "running",
                "total_companies_attempted": total_companies_attempted,
                "total_companies_succeeded": total_companies_succeeded,
                "total_companies_failed": total_companies_failed,
                "total_jobs_observed": len(all_jobs),
                "error_summary": error_summary,
            }
        )
        write_json_atomic(run_record, run_metadata_path)

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

        for company in companies:
            company_result = _summarize_company_result(
                run_id=run_id,
                provider=provider.name,
                company=company,
                result=result,
                observed_at=run_timestamp,
            )
            all_company_results.append(company_result)
            append_jsonl_records([company_result], company_results_path)
            record_company_job_history(
                run_id=run_id,
                company_result=company_result,
                jobs=result.get_company_jobs(company),
                observations_dir=job_observations_dir or INGESTION_JOB_OBSERVATIONS_DIR,
                events_dir=job_events_dir or INGESTION_JOB_EVENTS_DIR,
            )
            process_company_lifecycle_result(
                company_result=company_result,
                jobs=result.get_company_jobs(company),
                state_path=INGESTION_JOB_LIFECYCLE_DIR / "job_lifecycle_state.jsonl",
                events_path=INGESTION_JOB_LIFECYCLE_DIR / "job_lifecycle_events.jsonl",
                processed_results_path=INGESTION_JOB_LIFECYCLE_DIR / "processed_company_results.jsonl",
                company_cursor_path=INGESTION_JOB_LIFECYCLE_DIR / "company_cursors.jsonl",
            )
            _refresh_run_record_state()

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

    total_companies_attempted = len(all_company_results)
    total_companies_succeeded = sum(
        1
        for item in all_company_results
        if item["status"] == "success"
    )
    total_companies_failed = sum(
        1
        for item in all_company_results
        if item["status"] in {"failed", "partial"}
    )

    error_summary = {
        "failed_companies": [
            {
                "provider": item["provider"],
                "company": item["company_slug"],
                "error_code": item["error_code"],
                "error_details": item["error_details"],
            }
            for item in all_company_results
            if item["status"] in {"failed", "partial"}
        ],
        "partial_companies": [
            item["company_slug"]
            for item in all_company_results
            if item["status"] == "partial"
        ],
    }
    run_status = _summarize_run_status(all_company_results)
    run_record.update(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": run_status,
            "total_companies_attempted": total_companies_attempted,
            "total_companies_succeeded": total_companies_succeeded,
            "total_companies_failed": total_companies_failed,
            "total_jobs_observed": len(all_jobs),
            "error_summary": error_summary,
        }
    )
    write_json_atomic(run_record, run_metadata_path)

    if all_jobs:
        validate_job_postings(all_jobs)
        destination = output_path or JOBS_MASTER_PATH
        write_jobs_csv(all_jobs, destination)
        summary = IngestionSummary(
            output_path=destination,
            job_count=len(all_jobs),
            provider_results=tuple(results),
            run_id=run_id,
        )
        LOGGER.info(
            "Saved master jobs dataset",
            extra={
                "event": "ingestion_succeeded",
                "output_path": destination,
                "job_count": summary.job_count,
                "failed_company_count": summary.failed_company_count,
                "detail_failure_count": summary.detail_failure_count,
                "run_id": run_id,
            },
        )
        return summary

    LOGGER.warning(
        "Ingestion did not produce jobs; run metadata was preserved without updating the master dataset.",
        extra={
            "event": "ingestion_no_jobs",
            "run_id": run_id,
            "status": run_status,
            "failed_company_count": total_companies_failed,
        },
    )
    destination = output_path or JOBS_MASTER_PATH
    return IngestionSummary(
        output_path=destination,
        job_count=0,
        provider_results=tuple(results),
        run_id=run_id,
    )


def _build_run_id(run_timestamp: str) -> str:
    """Create a deterministic, timestamp-based run identifier."""
    normalized = run_timestamp.replace(":", "").replace("+", "").replace(".", "")
    return f"run_{normalized}_{uuid.uuid4().hex[:8]}"


def _summarize_run_status(company_results: Sequence[dict[str, object]]) -> str:
    """Return a run-level status based on the trustworthiness of company results."""
    if not company_results:
        return "failed"
    status_values = {item["status"] for item in company_results}
    if status_values == {"success"}:
        return "succeeded"
    if "success" in status_values and (
        status_values - {"success"}
    ):
        return "partial_success"
    return "failed"


def _summarize_company_result(
    *,
    run_id: str,
    provider: str,
    company: str,
    result: ProviderRunResult,
    observed_at: str,
) -> dict[str, object]:
    """Convert a company-specific provider outcome into a run-scoped result."""
    summary_error = result.get_company_failed(company)
    detail_failure_count = result.get_company_detail_failures(company)
    job_count = len(result.get_company_jobs(company))
    company_name = company

    if summary_error is not None:
        status = "failed"
        is_complete_snapshot = False
        is_trustworthy = False
        error_code = "company_fetch_failed"
        error_details = summary_error
    elif detail_failure_count > 0:
        status = "partial"
        is_complete_snapshot = False
        is_trustworthy = False
        error_code = "job_detail_incomplete"
        error_details = (
            f"{detail_failure_count} job-detail fetch(es) failed while the company"
            " board completed."
        )
    else:
        status = "success"
        is_complete_snapshot = True
        is_trustworthy = True
        error_code = None
        error_details = None

    return {
        "run_id": run_id,
        "provider": provider,
        "company_slug": company,
        "company_name": company_name,
        "attempted_at": observed_at,
        "completed_at": observed_at,
        "status": status,
        "jobs_fetched": job_count,
        "error_code": error_code,
        "error_details": error_details,
        "is_complete_snapshot": is_complete_snapshot,
        "is_trustworthy": is_trustworthy,
    }


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
