"""Immutable bronze snapshots produced from the ingestion master dataset."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_job_market.config import BRONZE_SNAPSHOTS_DIR
from ai_job_market.etl.io import read_csv_records


SNAPSHOT_FILE_NAME = "jobs.jsonl"
MANIFEST_FILE_NAME = "manifest.json"
_SAFE_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class BronzeSnapshot:
    """An immutable, manifest-backed snapshot of a master jobs dataset."""

    snapshot_id: str
    path: Path
    created_at: str
    record_count: int

    @property
    def records_path(self) -> Path:
        """Return the JSON Lines records file stored in this snapshot."""
        return self.path / SNAPSHOT_FILE_NAME


def create_bronze_snapshot(
    source_path: Path,
    *,
    snapshots_dir: Path = BRONZE_SNAPSHOTS_DIR,
    snapshot_id: str | None = None,
    created_at: str | None = None,
) -> BronzeSnapshot:
    """Copy a master CSV into a content-verified immutable bronze snapshot."""
    if not source_path.is_file():
        raise FileNotFoundError(f"Master jobs dataset does not exist: {source_path}")

    records = read_csv_records(source_path)
    if not records:
        raise ValueError("Cannot create a bronze snapshot from an empty dataset")

    snapshot_timestamp = created_at or datetime.now(timezone.utc).isoformat()
    resolved_id = snapshot_id or _build_snapshot_id(snapshot_timestamp)
    if not _SAFE_SNAPSHOT_ID.fullmatch(resolved_id):
        raise ValueError(
            "Snapshot ID may contain only letters, numbers, underscores, and hyphens"
        )

    snapshots_dir.mkdir(parents=True, exist_ok=True)
    destination = snapshots_dir / resolved_id
    if destination.exists():
        raise FileExistsError(f"Bronze snapshot already exists: {destination}")

    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{resolved_id}.", dir=snapshots_dir)
    )
    try:
        records_path = temporary_directory / SNAPSHOT_FILE_NAME
        with records_path.open("w", encoding="utf-8", newline="") as snapshot_file:
            for record in records:
                snapshot_file.write(json.dumps(record, sort_keys=True))
                snapshot_file.write("\n")

        manifest = {
            "schema_version": 1,
            "snapshot_id": resolved_id,
            "created_at": snapshot_timestamp,
            "source_path": str(source_path),
            "source_sha256": _sha256_file(source_path),
            "records_sha256": _sha256_file(records_path),
            "record_count": len(records),
            "source_columns": list(records[0]),
        }
        with (temporary_directory / MANIFEST_FILE_NAME).open(
            "w", encoding="utf-8"
        ) as manifest_file:
            json.dump(manifest, manifest_file, indent=2, sort_keys=True)
            manifest_file.write("\n")

        os.replace(temporary_directory, destination)
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise

    return BronzeSnapshot(
        snapshot_id=resolved_id,
        path=destination,
        created_at=snapshot_timestamp,
        record_count=len(records),
    )


def load_bronze_snapshot(snapshot: BronzeSnapshot) -> list[dict[str, str]]:
    """Load a bronze snapshot only when its manifest matches its records."""
    manifest_path = snapshot.path / MANIFEST_FILE_NAME
    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    if manifest.get("snapshot_id") != snapshot.snapshot_id:
        raise ValueError(
            f"Bronze manifest ID does not match directory: {snapshot.path}"
        )
    if manifest.get("records_sha256") != _sha256_file(snapshot.records_path):
        raise ValueError(f"Bronze snapshot checksum mismatch: {snapshot.path}")

    with snapshot.records_path.open(encoding="utf-8") as records_file:
        records = [json.loads(line) for line in records_file if line.strip()]
    if manifest.get("record_count") != len(records):
        raise ValueError(f"Bronze snapshot record count mismatch: {snapshot.path}")
    return records


def _build_snapshot_id(timestamp: str) -> str:
    normalized_timestamp = timestamp.replace("+00:00", "Z")
    timestamp_token = re.sub(r"[^A-Za-z0-9]", "", normalized_timestamp)
    return f"snapshot_{timestamp_token}_{os.urandom(4).hex()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
