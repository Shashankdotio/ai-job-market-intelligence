"""File-backed lifecycle detection for historically observed jobs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_job_market.config import (
    CLOSED_MISSING_RUNS_THRESHOLD,
    INGESTION_JOB_LIFECYCLE_DIR,
    JOB_LIFECYCLE_COMPANY_CURSORS_PATH,
    JOB_LIFECYCLE_EVENTS_PATH,
    JOB_LIFECYCLE_PROCESSED_RESULTS_PATH,
    JOB_LIFECYCLE_STATE_PATH,
)
from ai_job_market.etl.io import read_jsonl_records, write_jsonl_atomic


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with timezone information."""
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if not isinstance(value, str):
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def job_lifecycle_identity(
    provider: str,
    company_slug: str,
    external_job_id: str,
) -> tuple[str, str, str]:
    """Return the company-scoped identity used for lifecycle tracking."""
    return provider, company_slug, external_job_id


def job_key(provider: str, external_job_id: str) -> str:
    """Return the compatibility key already used by observation history."""
    return f"{provider}:{external_job_id}"


def load_lifecycle_state(path: str | Path = JOB_LIFECYCLE_STATE_PATH) -> list[dict[str, Any]]:
    """Load the current lifecycle state file, returning an empty list when absent."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    return read_jsonl_records(file_path)


def load_lifecycle_events(path: str | Path = JOB_LIFECYCLE_EVENTS_PATH) -> list[dict[str, Any]]:
    """Load append-only lifecycle events, returning an empty list when absent."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    return read_jsonl_records(file_path)


def load_processed_company_results(
    path: str | Path = JOB_LIFECYCLE_PROCESSED_RESULTS_PATH,
) -> set[str]:
    """Return all processed company-result identifiers seen by the lifecycle pipeline."""
    file_path = Path(path)
    if not file_path.exists():
        return set()
    records = read_jsonl_records(file_path)
    return {str(record.get("company_result_id")) for record in records if record.get("company_result_id")}


def load_company_cursors(
    path: str | Path = JOB_LIFECYCLE_COMPANY_CURSORS_PATH,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return the last evaluated snapshot cursor per provider/company."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    records = read_jsonl_records(file_path)
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (str(record.get("provider")), str(record.get("company_slug")))
        index[key] = record
    return index


def _current_record_for_state(
    state_records: Sequence[Mapping[str, Any]],
    provider: str,
    company_slug: str,
    external_job_id: str,
) -> dict[str, Any] | None:
    for record in state_records:
        if (
            str(record.get("provider")) == provider
            and str(record.get("company_slug")) == company_slug
            and str(record.get("external_job_id")) == external_job_id
        ):
            return dict(record)
    return None


def _write_current_state(
    state_path: Path,
    state_records: Iterable[Mapping[str, Any]],
) -> None:
    ordered = sorted(
        (dict(record) for record in state_records),
        key=lambda record: (
            str(record.get("provider")),
            str(record.get("company_slug")),
            str(record.get("external_job_id")),
        ),
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(ordered, state_path)


def _write_company_cursor(
    cursor_path: Path,
    company_cursors: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    ordered = [dict(record) for record in company_cursors.values()]
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(ordered, cursor_path)


def _append_event_records(
    event_path: Path,
    records: Iterable[Mapping[str, Any]],
) -> None:
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), sort_keys=True))
            handle.write("\n")


def _append_processed_result(
    processed_results_path: Path,
    company_result_id: str,
    company_result: Mapping[str, Any],
) -> None:
    processed_results_path.parent.mkdir(parents=True, exist_ok=True)
    with processed_results_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "company_result_id": company_result_id,
                    "provider": company_result.get("provider"),
                    "company_slug": company_result.get("company_slug"),
                    "processed_at": utc_now(),
                },
                sort_keys=True,
            )
        )
        handle.write("\n")


def _emit_event(
    *,
    event_path: Path,
    event_key: tuple[str, str, str, str, str],
    existing_event_keys: set[tuple[str, str, str, str, str]],
    event_record: dict[str, Any],
) -> None:
    if event_key in existing_event_keys:
        return
    _append_event_records(event_path, [event_record])
    existing_event_keys.add(event_key)


def _evaluate_missing_transition(
    *,
    previous_state: dict[str, Any],
    threshold: int,
) -> tuple[str, int, str | None]:
    previous_lifecycle = str(previous_state.get("lifecycle_state") or "active")
    previous_count = int(previous_state.get("missing_snapshot_count", 0) or 0)

    if previous_lifecycle == "active":
        return "suspected_closed", 1, "suspected_closed"
    if previous_lifecycle == "suspected_closed":
        next_count = previous_count + 1
        if next_count >= threshold:
            return "closed", next_count, "closed"
        return "suspected_closed", next_count, None
    if previous_lifecycle == "closed":
        return "closed", previous_count + 1, None
    return "active", 0, None


def _evaluate_present_transition(
    *,
    previous_state: dict[str, Any] | None,
    company_result: Mapping[str, Any],
    current_record: dict[str, Any],
) -> tuple[str, int, str | None]:
    if previous_state is None:
        return "active", 0, None

    previous_lifecycle = str(previous_state.get("lifecycle_state") or "active")
    if previous_lifecycle == "suspected_closed":
        return "active", 0, None
    if previous_lifecycle == "closed":
        return "active", 0, "reopened"
    return "active", 0, None


def process_company_lifecycle_result(
    *,
    company_result: Mapping[str, Any],
    jobs: Sequence[Any],
    state_path: str | Path = JOB_LIFECYCLE_STATE_PATH,
    events_path: str | Path = JOB_LIFECYCLE_EVENTS_PATH,
    processed_results_path: str | Path = JOB_LIFECYCLE_PROCESSED_RESULTS_PATH,
    company_cursor_path: str | Path = JOB_LIFECYCLE_COMPANY_CURSORS_PATH,
    closed_missing_runs_threshold: int = CLOSED_MISSING_RUNS_THRESHOLD,
) -> list[dict[str, Any]]:
    """Evaluate one trustworthy company result and update lifecycle state/events."""
    state_file = Path(state_path)
    events_file = Path(events_path)
    processed_file = Path(processed_results_path)
    cursor_file = Path(company_cursor_path)

    if not company_result.get("is_complete_snapshot") or not company_result.get("is_trustworthy"):
        company_result_id = str(
            company_result.get("company_result_id")
            or f"{company_result.get('run_id')}:{company_result.get('provider')}:{company_result.get('company_slug')}"
        )
        processed = load_processed_company_results(processed_file)
        if company_result_id not in processed:
            _append_processed_result(processed_file, company_result_id, company_result)
        return []

    provider = str(company_result.get("provider"))
    company_slug = str(company_result.get("company_slug"))
    run_id = str(company_result.get("run_id"))
    company_result_id = str(
        company_result.get("company_result_id")
        or f"{run_id}:{provider}:{company_slug}"
    )

    processed = load_processed_company_results(processed_file)
    if company_result_id in processed:
        return []

    state_records = load_lifecycle_state(state_file)
    state_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in state_records:
        state_by_key[
            (
                str(record.get("provider")),
                str(record.get("company_slug")),
                str(record.get("external_job_id")),
            )
        ] = dict(record)

    current_job_ids = {
        job_lifecycle_identity(
            provider,
            company_slug,
            str(job.external_job_id),
        )
        for job in jobs
        if getattr(job, "provider", None) == provider and getattr(job, "company", None) == company_slug
    }

    existing_event_keys = {
        (
            str(event.get("company_result_id")),
            str(event.get("provider")),
            str(event.get("company_slug")),
            str(event.get("external_job_id")),
            str(event.get("event_type")),
        )
        for event in load_lifecycle_events(events_file)
    }

    cursor_map = load_company_cursors(cursor_file)
    last_cursor = cursor_map.get((provider, company_slug))
    attempted_at_value = company_result.get("attempted_at") or company_result.get("completed_at") or run_id
    if last_cursor is not None:
        last_attempted = last_cursor.get("attempted_at")
        if last_attempted and attempted_at_value and _parse_timestamp(attempted_at_value) < _parse_timestamp(last_attempted):
            _append_processed_result(processed_file, company_result_id, company_result)
            return []

    updated_state: dict[tuple[str, str, str], dict[str, Any]] = dict(state_by_key)
    new_events: list[dict[str, Any]] = []

    for identity, previous_state in list(state_by_key.items()):
        if identity[0] != provider or identity[1] != company_slug:
            continue
        if identity in current_job_ids:
            continue
        previous_lifecycle = str(previous_state.get("lifecycle_state") or "active")
        next_state, next_count, event_type = _evaluate_missing_transition(
            previous_state=previous_state,
            threshold=closed_missing_runs_threshold,
        )
        if previous_lifecycle == next_state and int(previous_state.get("missing_snapshot_count", 0) or 0) == next_count:
            continue
        event_record = None
        if event_type is not None:
            event_record = {
                "event_id": f"evt-{company_result_id}-{identity[2]}-{event_type}-{len(new_events)}",
                "event_type": event_type,
                "provider": provider,
                "company_slug": company_slug,
                "external_job_id": identity[2],
                "job_key": job_key(provider, identity[2]),
                "run_id": run_id,
                "company_result_id": company_result_id,
                "occurred_at": utc_now(),
                "previous_state": previous_lifecycle,
                "new_state": next_state,
                "missing_snapshot_count": next_count,
                "reason": "job_missing_from_trustworthy_snapshot",
            }
            event_key = (
                company_result_id,
                provider,
                company_slug,
                identity[2],
                event_type,
            )
            if event_key not in existing_event_keys:
                new_events.append(event_record)
                existing_event_keys.add(event_key)
        updated_state[identity] = {
            **previous_state,
            "lifecycle_state": next_state,
            "missing_snapshot_count": next_count,
            "last_seen_run_id": previous_state.get("last_seen_run_id"),
            "last_seen_company_result_id": previous_state.get("last_seen_company_result_id"),
            "last_evaluated_run_id": run_id,
            "last_evaluated_company_result_id": company_result_id,
            "last_updated_at": utc_now(),
            "run_sequence": previous_state.get("run_sequence", 0),
        }

    for job in jobs:
        identity = job_lifecycle_identity(
            provider,
            company_slug,
            str(job.external_job_id),
        )
        previous_state = updated_state.get(identity, state_by_key.get(identity))
        previous_lifecycle = str((previous_state or {}).get("lifecycle_state") or "active")
        new_state, new_count, event_type = _evaluate_present_transition(
            previous_state=previous_state,
            company_result=company_result,
            current_record={
                "provider": provider,
                "company_slug": company_slug,
                "external_job_id": str(job.external_job_id),
            },
        )
        if previous_state is None:
            updated_state[identity] = {
                "provider": provider,
                "company_slug": company_slug,
                "external_job_id": str(job.external_job_id),
                "job_key": job_key(provider, str(job.external_job_id)),
                "lifecycle_state": "active",
                "missing_snapshot_count": 0,
                "first_seen_at": (job.updated_at or utc_now()),
                "last_seen_at": (job.updated_at or utc_now()),
                "first_seen_run_id": run_id,
                "last_seen_run_id": run_id,
                "first_seen_company_result_id": company_result_id,
                "last_seen_company_result_id": company_result_id,
                "last_evaluated_run_id": run_id,
                "last_evaluated_company_result_id": company_result_id,
                "last_updated_at": utc_now(),
            }
            continue

        if previous_lifecycle == "active":
            updated_state[identity] = {
                **previous_state,
                "lifecycle_state": "active",
                "missing_snapshot_count": 0,
                "last_seen_at": job.updated_at or utc_now(),
                "last_seen_run_id": run_id,
                "last_seen_company_result_id": company_result_id,
                "last_evaluated_run_id": run_id,
                "last_evaluated_company_result_id": company_result_id,
                "last_updated_at": utc_now(),
            }
            continue

        if previous_lifecycle == "suspected_closed":
            updated_state[identity] = {
                **previous_state,
                "lifecycle_state": "active",
                "missing_snapshot_count": 0,
                "last_seen_at": job.updated_at or utc_now(),
                "last_seen_run_id": run_id,
                "last_seen_company_result_id": company_result_id,
                "last_evaluated_run_id": run_id,
                "last_evaluated_company_result_id": company_result_id,
                "last_updated_at": utc_now(),
            }
            continue

        if previous_lifecycle == "closed":
            reopened_event = {
                "event_id": f"evt-{company_result_id}-{identity[2]}-reopened-{len(new_events)}",
                "event_type": "reopened",
                "provider": provider,
                "company_slug": company_slug,
                "external_job_id": identity[2],
                "job_key": job_key(provider, identity[2]),
                "run_id": run_id,
                "company_result_id": company_result_id,
                "occurred_at": utc_now(),
                "previous_state": "closed",
                "new_state": "active",
                "missing_snapshot_count": 0,
                "reason": "job_reappeared_after_closure",
            }
            event_key = (company_result_id, provider, company_slug, identity[2], "reopened")
            if event_key not in existing_event_keys:
                new_events.append(reopened_event)
                existing_event_keys.add(event_key)
            updated_state[identity] = {
                **previous_state,
                "lifecycle_state": "active",
                "missing_snapshot_count": 0,
                "last_seen_at": job.updated_at or utc_now(),
                "last_seen_run_id": run_id,
                "last_seen_company_result_id": company_result_id,
                "last_evaluated_run_id": run_id,
                "last_evaluated_company_result_id": company_result_id,
                "last_updated_at": utc_now(),
            }
            continue

        updated_state[identity] = {
            **previous_state,
            "lifecycle_state": new_state,
            "missing_snapshot_count": new_count,
            "last_seen_at": job.updated_at or utc_now(),
            "last_seen_run_id": run_id,
            "last_seen_company_result_id": company_result_id,
            "last_evaluated_run_id": run_id,
            "last_evaluated_company_result_id": company_result_id,
            "last_updated_at": utc_now(),
        }

    _write_current_state(state_file, updated_state.values())
    if new_events:
        _append_event_records(events_file, new_events)

    cursor_entry = {
        "provider": provider,
        "company_slug": company_slug,
        "last_evaluated_run_id": run_id,
        "last_evaluated_company_result_id": company_result_id,
        "attempted_at": attempted_at_value,
        "last_updated_at": utc_now(),
    }
    cursor_map[(provider, company_slug)] = cursor_entry
    _write_company_cursor(cursor_file, cursor_map)

    _append_processed_result(processed_file, company_result_id, company_result)
    return list(new_events)
