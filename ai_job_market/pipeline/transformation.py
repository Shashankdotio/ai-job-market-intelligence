"""Build bronze, silver, gold, and quality artifacts from the master dataset."""

import logging
from dataclasses import dataclass
from pathlib import Path

from ai_job_market.config import (
    GOLD_COMPANY_COUNTS_PATH,
    GOLD_COMPANY_SKILL_COUNTS_PATH,
    GOLD_JOB_POSTINGS_PATH,
    GOLD_METADATA_PATH,
    GOLD_SKILL_COUNTS_PATH,
    JOBS_MASTER_PATH,
    OUTPUTS_DIR,
    PROCESSED_DATA_DIR,
    QUALITY_REPORT_PATH,
    SILVER_JOB_POSTINGS_PATH,
    ensure_project_directories,
)
from ai_job_market.etl.bronze import (
    BronzeSnapshot,
    create_bronze_snapshot,
    load_bronze_snapshot,
)
from ai_job_market.etl.gold import (
    COMPANY_COUNT_COLUMNS,
    COMPANY_SKILL_COUNT_COLUMNS,
    JOB_POSTING_COLUMNS,
    SKILL_COUNT_COLUMNS,
    build_company_counts,
    build_company_skill_counts,
    build_job_postings,
    build_market_metadata,
    build_skill_counts,
)
from ai_job_market.etl.io import read_csv_records, write_csv_atomic, write_json_atomic
from ai_job_market.etl.normalize import (
    SILVER_JOB_COLUMNS,
    normalize_records,
    silver_to_legacy_record,
)
from ai_job_market.etl.quality import QualityReport, assess_silver_records
from ai_job_market.models import LEGACY_JOB_COLUMNS


LOGGER = logging.getLogger(__name__)
LEGACY_PROCESSED_COLUMNS = (*LEGACY_JOB_COLUMNS, "clean_description", "skills")


@dataclass(frozen=True, slots=True)
class TransformationSummary:
    """Addresses and row counts for one complete ETL materialization."""

    snapshot: BronzeSnapshot
    silver_path: Path
    gold_paths: tuple[Path, ...]
    quality_report: QualityReport


def run_transformation(
    *,
    source_path: Path = JOBS_MASTER_PATH,
    snapshot_id: str | None = None,
    bronze_snapshots_dir: Path | None = None,
    silver_path: Path = SILVER_JOB_POSTINGS_PATH,
    gold_directory: Path | None = None,
    quality_report_path: Path = QUALITY_REPORT_PATH,
    write_legacy_outputs: bool = True,
) -> TransformationSummary:
    """Snapshot source jobs, normalize them, validate quality, and aggregate gold."""
    ensure_project_directories()
    snapshot_options: dict[str, Path | str] = {}
    if bronze_snapshots_dir is not None:
        snapshot_options["snapshots_dir"] = bronze_snapshots_dir
    if snapshot_id is not None:
        snapshot_options["snapshot_id"] = snapshot_id
    snapshot = create_bronze_snapshot(source_path, **snapshot_options)
    bronze_records = load_bronze_snapshot(snapshot)
    silver_records = normalize_records(
        bronze_records,
        snapshot_id=snapshot.snapshot_id,
        snapshot_created_at=snapshot.created_at,
    )
    quality_report = assess_silver_records(silver_records)
    write_json_atomic(quality_report.to_dict(), quality_report_path)
    if not quality_report.passed:
        raise ValueError(
            "Silver data quality failed; existing silver and gold datasets were kept"
        )

    if gold_directory is None:
        company_counts_path = GOLD_COMPANY_COUNTS_PATH
        skill_counts_path = GOLD_SKILL_COUNTS_PATH
        company_skill_counts_path = GOLD_COMPANY_SKILL_COUNTS_PATH
        job_postings_path = GOLD_JOB_POSTINGS_PATH
        metadata_path = GOLD_METADATA_PATH
    else:
        company_counts_path = gold_directory / "company_counts.csv"
        skill_counts_path = gold_directory / "skill_counts.csv"
        company_skill_counts_path = gold_directory / "company_skill_counts.csv"
        job_postings_path = gold_directory / "job_postings.csv"
        metadata_path = gold_directory / "metadata.json"
    write_csv_atomic(silver_records, SILVER_JOB_COLUMNS, silver_path)
    company_counts = build_company_counts(silver_records)
    skill_counts = build_skill_counts(silver_records)
    company_skill_counts = build_company_skill_counts(silver_records)
    job_postings = build_job_postings(silver_records)
    metadata = build_market_metadata(
        silver_records,
        snapshot_id=snapshot.snapshot_id,
        generated_at=quality_report.checked_at,
    )
    write_csv_atomic(company_counts, COMPANY_COUNT_COLUMNS, company_counts_path)
    write_csv_atomic(skill_counts, SKILL_COUNT_COLUMNS, skill_counts_path)
    write_csv_atomic(
        company_skill_counts,
        COMPANY_SKILL_COUNT_COLUMNS,
        company_skill_counts_path,
    )
    write_csv_atomic(job_postings, JOB_POSTING_COLUMNS, job_postings_path)
    write_json_atomic(metadata, metadata_path)

    if write_legacy_outputs:
        _write_legacy_outputs(
            silver_records=silver_records,
            company_counts=company_counts,
            skill_counts=skill_counts,
            company_skill_counts=company_skill_counts,
        )

    LOGGER.info(
        "Transformation completed",
        extra={
            "event": "transformation_succeeded",
            "output_path": silver_path,
            "job_count": len(silver_records),
        },
    )
    return TransformationSummary(
        snapshot=snapshot,
        silver_path=silver_path,
        gold_paths=(
            company_counts_path,
            skill_counts_path,
            company_skill_counts_path,
            job_postings_path,
            metadata_path,
        ),
        quality_report=quality_report,
    )


def run_quality_check(
    silver_path: Path = SILVER_JOB_POSTINGS_PATH,
    quality_report_path: Path = QUALITY_REPORT_PATH,
) -> QualityReport:
    """Validate an existing silver dataset without rewriting ETL artifacts."""
    records = read_csv_records(silver_path)
    quality_report = assess_silver_records(records)
    write_json_atomic(quality_report.to_dict(), quality_report_path)
    if not quality_report.passed:
        raise ValueError("Silver data quality failed; see the quality report")
    return quality_report


def _write_legacy_outputs(
    *,
    silver_records: list[dict[str, str]],
    company_counts: list[dict[str, int | str]],
    skill_counts: list[dict[str, int | str]],
    company_skill_counts: list[dict[str, int | str]],
) -> None:
    """Keep existing analysis scripts working during the ETL-layer transition."""
    write_csv_atomic(
        (silver_to_legacy_record(record) for record in silver_records),
        LEGACY_PROCESSED_COLUMNS,
        PROCESSED_DATA_DIR / "jobs_with_skills.csv",
    )
    write_csv_atomic(
        (
            {"company": record["company"], "Jobs Posted": record["job_count"]}
            for record in company_counts
        ),
        ("company", "Jobs Posted"),
        PROCESSED_DATA_DIR / "company_counts.csv",
    )
    write_csv_atomic(
        (
            {"Skill": record["skill"], "Count": record["job_count"]}
            for record in skill_counts
        ),
        ("Skill", "Count"),
        PROCESSED_DATA_DIR / "skill_counts.csv",
    )
    write_csv_atomic(
        (
            {"Skill": record["skill"], "Count": record["job_count"]}
            for record in skill_counts
        ),
        ("Skill", "Count"),
        OUTPUTS_DIR / "skill_counts.csv",
    )
    write_csv_atomic(
        (
            {
                "company": record["company"],
                "skills": record["skill"],
                "Count": record["job_count"],
            }
            for record in company_skill_counts
        ),
        ("company", "skills", "Count"),
        PROCESSED_DATA_DIR / "company_skill_counts.csv",
    )
