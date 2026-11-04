"""Append-only job observation and change-detection history."""

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_job_market.config import (
    INGESTION_JOB_EVENTS_DIR,
    INGESTION_JOB_OBSERVATIONS_DIR,
)
from ai_job_market.etl.io import append_jsonl_records, read_jsonl_records
from ai_job_market.models import JobPosting
from ai_job_market.text import clean_html

_TRACKED_CHANGE_FIELDS = (
    "title",
    "location",
    "department",
    "normalized_description_hash",
)


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with timezone information."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_field_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return value


def _normalized_description_hash(description: str | None) -> str:
    normalized = clean_html(description or "")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _job_identity_key(provider: str, company_slug: str, external_job_id: str) -> tuple[str, str, str]:
    return provider, company_slug, external_job_id


def _job_key(provider: str, external_job_id: str) -> str:
    return f"{provider}:{external_job_id}"


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if not isinstance(value, str):
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _all_run_history_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for file_path in sorted(directory.glob("*.jsonl")):
        records.extend(read_jsonl_records(file_path))
    return records


def _latest_previous_observation(
    provider: str,
    company_slug: str,
    external_job_id: str,
    observations_dir: Path = INGESTION_JOB_OBSERVATIONS_DIR,
) -> dict[str, Any] | None:
    records = _all_run_history_records(observations_dir)
    matches = [
        record
        for record in records
        if record.get("provider") == provider
        and record.get("company_slug") == company_slug
        and record.get("external_job_id") == external_job_id
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: _parse_timestamp(item.get("observed_at") or item.get("created_at")),
    )


def record_company_job_history(
    *,
    run_id: str,
    company_result: Mapping[str, Any],
    jobs: Sequence[JobPosting],
    observations_dir: Path = INGESTION_JOB_OBSERVATIONS_DIR,
    events_dir: Path = INGESTION_JOB_EVENTS_DIR,
) -> None:
    """Append job observations and events for a trustworthy, complete company snapshot."""
    if not company_result.get("is_complete_snapshot") or not company_result.get("is_trustworthy"):
        return

    provider = str(company_result["provider"])
    company_slug = str(company_result["company_slug"])
    observation_file = observations_dir / f"{run_id}.jsonl"
    event_file = events_dir / f"{run_id}.jsonl"

    current_observation_keys: set[tuple[str, str, str]] = set()
    for record in read_jsonl_records(observation_file):
        current_observation_keys.add(
            _job_identity_key(
                str(record.get("provider")),
                str(record.get("company_slug")),
                str(record.get("external_job_id")),
            )
        )

    current_event_keys: set[tuple[str, str, str, str | None, str | None]] = set()
    for record in read_jsonl_records(event_file):
        current_event_keys.add(
            (
                str(record.get("run_id")),
                str(record.get("provider")),
                str(record.get("company_slug")),
                str(record.get("external_job_id")),
                record.get("event_type"),
            )
        )

    observations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    seen_in_snapshot: set[tuple[str, str, str]] = set()

    for job in jobs:
        historical_identity = _job_identity_key(provider, company_slug, job.external_job_id)
        if historical_identity in seen_in_snapshot or historical_identity in current_observation_keys:
            continue

        seen_in_snapshot.add(historical_identity)
        timestamp = utc_now()
        observation = {
            "observation_id": str(uuid.uuid4()),
            "provider": provider,
            "company_slug": company_slug,
            "external_job_id": job.external_job_id,
            "job_key": _job_key(provider, job.external_job_id),
            "run_id": run_id,
            "company_result_id": f"{run_id}:{provider}:{company_slug}",
            "observed_at": timestamp,
            "title": job.title,
            "location": job.location,
            "department": job.department,
            "office": job.office,
            "job_url": job.job_url,
            "normalized_description_hash": _normalized_description_hash(job.description),
            "skill_signature": None,
            "created_at": timestamp,
        }
        observations.append(observation)

        previous = _latest_previous_observation(
            provider,
            company_slug,
            job.external_job_id,
            observations_dir=observations_dir,
        )
        if previous is None:
            event_type = "discovered"
            previous_values = {field: None for field in _TRACKED_CHANGE_FIELDS}
            new_values = {
                field: _normalize_field_value(observation.get(field))
                for field in _TRACKED_CHANGE_FIELDS
            }
            changed_fields = list(_TRACKED_CHANGE_FIELDS)
        else:
            changed_fields = []
            previous_values = {}
            new_values = {}
            for field_name in _TRACKED_CHANGE_FIELDS:
                previous_value = _normalize_field_value(previous.get(field_name))
                new_value = _normalize_field_value(observation.get(field_name))
                if previous_value != new_value:
                    changed_fields.append(field_name)
                    previous_values[field_name] = previous_value
                    new_values[field_name] = new_value
            if not changed_fields:
                continue
            event_type = "updated"

        event_key = (
            run_id,
            provider,
            company_slug,
            job.external_job_id,
            event_type,
        )
        if event_key in current_event_keys:
            continue
        event = {
            "event_id": str(uuid.uuid4()),
            "provider": provider,
            "company_slug": company_slug,
            "external_job_id": job.external_job_id,
            "job_key": _job_key(provider, job.external_job_id),
            "run_id": run_id,
            "event_type": event_type,
            "occurred_at": timestamp,
            "changed_fields": changed_fields,
            "previous_values": previous_values,
            "new_values": new_values,
        }
        events.append(event)
        current_event_keys.add(event_key)

    if observations:
        append_jsonl_records(observations, observation_file)
    if events:
        append_jsonl_records(events, event_file)
