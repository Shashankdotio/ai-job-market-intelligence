"""Normalize bronze records into the stable silver job-postings contract."""

import hashlib
import json
from collections.abc import Iterable
from typing import Final
from urllib.parse import urlparse

from ai_job_market.etl.skills import extract_skills
from ai_job_market.models import JOB_COLUMNS, LEGACY_JOB_COLUMNS
from ai_job_market.text import clean_html


SILVER_JOB_COLUMNS: Final[tuple[str, ...]] = (
    "snapshot_id",
    "job_key",
    *JOB_COLUMNS,
    "provenance_status",
    "clean_description",
    "skills",
)


def normalize_records(
    records: Iterable[dict[str, str]],
    *,
    snapshot_id: str,
    snapshot_created_at: str,
) -> list[dict[str, str]]:
    """Map current and legacy master records onto the silver schema."""
    return [
        normalize_record(
            record,
            snapshot_id=snapshot_id,
            snapshot_created_at=snapshot_created_at,
        )
        for record in records
    ]


def normalize_record(
    record: dict[str, str],
    *,
    snapshot_id: str,
    snapshot_created_at: str,
) -> dict[str, str]:
    """Normalize one master record and backfill only absent legacy provenance."""
    job_url = _text(record.get("job_url"))
    provider = _text(record.get("provider")) or _infer_provider(job_url)
    external_job_id = _text(record.get("external_job_id")) or _infer_external_id(
        job_url
    )
    collected_at = _text(record.get("collected_at")) or snapshot_created_at
    provenance_status = (
        "recorded"
        if all(
            _text(record.get(field))
            for field in ("provider", "external_job_id", "collected_at")
        )
        else "inferred"
    )
    description = clean_html(_text(record.get("description")))
    skills = extract_skills(description)

    normalized = {
        "snapshot_id": snapshot_id,
        "job_key": f"{provider}:{external_job_id}",
        "provider": provider,
        "external_job_id": external_job_id,
        "company": _text(record.get("company")),
        "title": _text(record.get("title")),
        "location": _text(record.get("location")),
        "updated_at": _text(record.get("updated_at")),
        "job_url": job_url,
        "department": _text(record.get("department")),
        "office": _text(record.get("office")),
        "description": description,
        "collected_at": collected_at,
        "provenance_status": provenance_status,
        "clean_description": description,
        "skills": json.dumps(skills),
    }
    return {column: normalized[column] for column in SILVER_JOB_COLUMNS}


def silver_to_legacy_record(record: dict[str, str]) -> dict[str, str]:
    """Create the current jobs_with_skills.csv shape for existing scripts."""
    legacy_record = {column: record[column] for column in LEGACY_JOB_COLUMNS}
    legacy_record["clean_description"] = record["clean_description"]
    legacy_record["skills"] = str(json.loads(record["skills"]))
    return legacy_record


def _infer_provider(job_url: str) -> str:
    host = urlparse(job_url).netloc.lower()
    if "greenhouse.io" in host:
        return "greenhouse"
    return "legacy_unknown"


def _infer_external_id(job_url: str) -> str:
    parsed_url = urlparse(job_url)
    path_segments = [segment for segment in parsed_url.path.split("/") if segment]
    if path_segments and path_segments[-1].isdigit():
        return path_segments[-1]
    return hashlib.sha256(job_url.encode("utf-8")).hexdigest()[:24]


def _text(value: object | None) -> str:
    return str(value or "").strip()
