"""Canonical records shared by all ATS providers and the ingestion pipeline."""

from dataclasses import dataclass, field
from typing import Final


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
