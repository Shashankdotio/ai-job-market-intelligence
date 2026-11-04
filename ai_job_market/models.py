"""Canonical records shared by all ATS providers and the ingestion pipeline."""

from dataclasses import dataclass, field
from typing import Any, Final


LEGACY_JOB_COLUMNS: Final[tuple[str, ...]] = (
    "company",
    "title",
    "location",
    "updated_at",
    "job_url",
    "department",
    "office",
    "description",
)

JOB_COLUMNS: Final[tuple[str, ...]] = LEGACY_JOB_COLUMNS + (
    "provider",
    "external_job_id",
    "collected_at",
)


@dataclass(frozen=True, slots=True)
class JobPosting:
    """A normalized job posting emitted by any ATS provider."""

    provider: str
    external_job_id: str
    company: str
    title: str
    location: str
    updated_at: str
    job_url: str
    department: str
    office: str
    description: str
    collected_at: str

    def __post_init__(self) -> None:
        required_fields = {
            "provider": self.provider,
            "external_job_id": self.external_job_id,
            "company": self.company,
            "title": self.title,
            "job_url": self.job_url,
            "collected_at": self.collected_at,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            raise ValueError(
                f"Job posting is missing required fields: {', '.join(missing)}"
            )

    @property
    def identity(self) -> tuple[str, str]:
        """Return the stable provider-specific identity used for deduplication."""
        return self.provider, self.external_job_id

    def to_legacy_row(self) -> dict[str, str]:
        """Return the original CSV shape used by the existing ETL scripts."""
        return {column: str(getattr(self, column)) for column in LEGACY_JOB_COLUMNS}

    def to_csv_row(self) -> dict[str, str]:
        """Return the canonical CSV representation, including provenance fields."""
        return {column: str(getattr(self, column)) for column in JOB_COLUMNS}


@dataclass(slots=True)
class ProviderRunResult:
    """Outcome of one provider's scrape attempt."""

    provider: str
    jobs: list[JobPosting] = field(default_factory=list)
    attempted_companies: list[str] = field(default_factory=list)
    failed_companies: dict[str, str] = field(default_factory=dict)
    detail_failure_count: int = 0
    company_jobs: dict[str, list[JobPosting]] = field(default_factory=dict)
    company_failed: dict[str, str] = field(default_factory=dict)
    company_detail_failures: dict[str, int] = field(default_factory=dict)

    def record_company_jobs(self, company: str, jobs: list[JobPosting]) -> None:
        """Persist the jobs emitted for an individual company."""
        self.company_jobs.setdefault(company, [])
        self.company_jobs[company].extend(jobs)

    def record_company_failure(self, company: str, error: str) -> None:
        """Record a company-specific fetch failure."""
        self.company_failed[company] = error
        self.failed_companies[company] = error

    def record_company_detail_failure(self, company: str) -> None:
        """Record an individual company's detail-fetch failure count."""
        self.company_detail_failures[company] = (
            self.company_detail_failures.get(company, 0) + 1
        )

    def get_company_jobs(self, company: str) -> list[JobPosting]:
        """Return the jobs produced for one company in this run."""
        return list(self.company_jobs.get(company, []))

    def get_company_failed(self, company: str) -> str | None:
        """Return the failure message for one company, if any."""
        return self.company_failed.get(company) or self.failed_companies.get(company)

    def get_company_detail_failures(self, company: str) -> int:
        """Return the number of failed detail fetches for one company."""
        return self.company_detail_failures.get(company, 0)
