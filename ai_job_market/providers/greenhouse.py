"""Greenhouse ATS provider implementation."""

import logging
from collections.abc import Sequence
from typing import Any

import requests

from ai_job_market.models import JobPosting, ProviderRunResult
from ai_job_market.text import clean_html


LOGGER = logging.getLogger(__name__)
GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseProvider:
    """Collect public job postings from Greenhouse job-board APIs."""

    name = "greenhouse"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds

    def scrape(
        self,
        companies: Sequence[str],
        collected_at: str,
    ) -> ProviderRunResult:
        """Fetch summary and detail records for each configured company board."""
        result = ProviderRunResult(
            provider=self.name,
            attempted_companies=list(companies),
        )

        for company in companies:
            self._scrape_company(company, collected_at, result)

        return result

    def _scrape_company(
        self,
        company: str,
        collected_at: str,
        result: ProviderRunResult,
    ) -> None:
        try:
            summary = self._get_json(f"{GREENHOUSE_API_URL}/{company}/jobs")
            jobs = summary["jobs"]
            if not isinstance(jobs, list):
                raise ValueError("Greenhouse response field 'jobs' is not a list")
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            requests.RequestException,
        ) as error:
            result.failed_companies[company] = str(error)
            LOGGER.error(
                "Unable to fetch Greenhouse company board",
                extra={
                    "event": "company_fetch_failed",
                    "provider": self.name,
                    "company": company,
                },
            )
            return

        LOGGER.info(
            "Fetched Greenhouse company board",
            extra={
                "event": "company_fetch_succeeded",
                "provider": self.name,
                "company": company,
                "job_count": len(jobs),
            },
        )

        for summary_job in jobs:
            self._scrape_job(company, summary_job, collected_at, result)

    def _scrape_job(
        self,
        company: str,
        summary_job: dict[str, Any],
        collected_at: str,
        result: ProviderRunResult,
    ) -> None:
        job_id = summary_job.get("id")
        if job_id is None:
            result.detail_failure_count += 1
            LOGGER.warning(
                "Skipped Greenhouse job without an identifier",
                extra={
                    "event": "job_skipped_missing_id",
                    "provider": self.name,
                    "company": company,
                },
            )
            return

        try:
            detail = self._get_json(
                f"{GREENHOUSE_API_URL}/{company}/jobs/{job_id}"
            )
            posting = self._to_job_posting(
                company=company,
                summary_job=summary_job,
                detail=detail,
                collected_at=collected_at,
            )
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            requests.RequestException,
        ) as error:
            result.detail_failure_count += 1
            LOGGER.warning(
                "Unable to fetch or normalize Greenhouse job",
                extra={
                    "event": "job_fetch_failed",
                    "provider": self.name,
                    "company": company,
                    "job_id": job_id,
                },
            )
            return

        result.jobs.append(posting)

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._session.get(url, timeout=self._timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object from Greenhouse")
        return payload

    @staticmethod
    def _to_job_posting(
        company: str,
        summary_job: dict[str, Any],
        detail: dict[str, Any],
        collected_at: str,
    ) -> JobPosting:
        departments = ", ".join(
            department.get("name", "")
            for department in detail.get("departments", [])
            if isinstance(department, dict) and department.get("name")
        )
        offices = ", ".join(
            office.get("name", "")
            for office in detail.get("offices", [])
            if isinstance(office, dict) and office.get("name")
        )
        location = summary_job.get("location") or {}

        return JobPosting(
            provider=GreenhouseProvider.name,
            external_job_id=str(summary_job["id"]),
            company=company,
            title=str(summary_job.get("title") or ""),
            location=str(location.get("name") or ""),
            updated_at=str(summary_job.get("updated_at") or ""),
            job_url=str(summary_job.get("absolute_url") or ""),
            department=departments,
            office=offices,
            description=clean_html(str(detail.get("content") or "")),
            collected_at=collected_at,
        )
