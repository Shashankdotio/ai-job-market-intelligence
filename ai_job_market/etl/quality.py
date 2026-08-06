"""Data-quality checks for the silver job-postings layer."""

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final
from urllib.parse import urlparse

from ai_job_market.etl.normalize import SILVER_JOB_COLUMNS


REQUIRED_SILVER_FIELDS: Final[tuple[str, ...]] = (
    "snapshot_id",
    "job_key",
    "provider",
    "external_job_id",
    "company",
    "title",
    "job_url",
    "collected_at",
)


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """A precise validation finding that can be surfaced to operators."""

    severity: str
    code: str
    message: str
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Machine-readable quality result for a single silver dataset."""

    checked_at: str
    record_count: int
    errors: tuple[QualityIssue, ...]
    warnings: tuple[QualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        """Serialize the report for the quality artifact and CLI consumers."""
        return {
            "checked_at": self.checked_at,
            "record_count": self.record_count,
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
        }


def assess_silver_records(records: list[dict[str, str]]) -> QualityReport:
    """Validate required fields, identities, URLs, and skill serialization."""
    errors: list[QualityIssue] = []
    warnings: list[QualityIssue] = []
    if not records:
        errors.append(
            QualityIssue(
                severity="error",
                code="empty_dataset",
                message="Silver job-postings dataset is empty.",
            )
        )

    expected_columns = set(SILVER_JOB_COLUMNS)
    job_keys: list[str] = []
    for row_number, record in enumerate(records, start=2):
        missing_columns = expected_columns.difference(record)
        if missing_columns:
            errors.append(
                QualityIssue(
                    severity="error",
                    code="missing_columns",
                    message=(
                        "Silver record is missing columns: "
                        f"{', '.join(sorted(missing_columns))}"
                    ),
                    row_number=row_number,
                )
            )
            continue

        for field in REQUIRED_SILVER_FIELDS:
            if not record[field].strip():
                errors.append(
                    QualityIssue(
                        severity="error",
                        code="missing_required_value",
                        message=f"Required field '{field}' is blank.",
                        row_number=row_number,
                    )
                )

        parsed_url = urlparse(record["job_url"])
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            errors.append(
                QualityIssue(
                    severity="error",
                    code="invalid_job_url",
                    message="Job URL must be an absolute HTTP(S) URL.",
                    row_number=row_number,
                )
            )

        try:
            skills = json.loads(record["skills"])
            if not isinstance(skills, list) or not all(
                isinstance(skill, str) for skill in skills
            ):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append(
                QualityIssue(
                    severity="error",
                    code="invalid_skills_json",
                    message="Skills must be a JSON array of strings.",
                    row_number=row_number,
                )
            )

        if record["provenance_status"] == "inferred":
            warnings.append(
                QualityIssue(
                    severity="warning",
                    code="inferred_provenance",
                    message="Provider provenance was inferred from a legacy record.",
                    row_number=row_number,
                )
            )
        if not record["description"]:
            warnings.append(
                QualityIssue(
                    severity="warning",
                    code="empty_description",
                    message=(
                        "Job description is empty; skill extraction is unavailable."
                    ),
                    row_number=row_number,
                )
            )
        job_keys.append(record["job_key"])

    for job_key, count in Counter(job_keys).items():
        if count > 1:
            errors.append(
                QualityIssue(
                    severity="error",
                    code="duplicate_job_key",
                    message=f"Job identity '{job_key}' appears {count} times.",
                )
            )

    return QualityReport(
        checked_at=datetime.now(timezone.utc).isoformat(),
        record_count=len(records),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
