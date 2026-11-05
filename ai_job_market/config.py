"""Project configuration and filesystem locations."""

from pathlib import Path
from typing import Final


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
RAW_DATA_DIR: Final[Path] = DATA_DIR / "raw"
BRONZE_DATA_DIR: Final[Path] = DATA_DIR / "bronze"
BRONZE_SNAPSHOTS_DIR: Final[Path] = BRONZE_DATA_DIR / "job_snapshots"
SILVER_DATA_DIR: Final[Path] = DATA_DIR / "silver"
GOLD_DATA_DIR: Final[Path] = DATA_DIR / "gold"
QUALITY_DATA_DIR: Final[Path] = DATA_DIR / "quality"
PROCESSED_DATA_DIR: Final[Path] = DATA_DIR / "processed"
OUTPUTS_DIR: Final[Path] = PROJECT_ROOT / "outputs"
CHARTS_DIR: Final[Path] = OUTPUTS_DIR / "charts"
REPORTS_DIR: Final[Path] = OUTPUTS_DIR / "reports"
INGESTION_DATA_DIR: Final[Path] = DATA_DIR / "ingestion"
INGESTION_RUNS_DIR: Final[Path] = INGESTION_DATA_DIR / "runs"
INGESTION_COMPANY_RESULTS_DIR: Final[Path] = (
    INGESTION_DATA_DIR / "company_results"
)
INGESTION_JOB_OBSERVATIONS_DIR: Final[Path] = (
    INGESTION_DATA_DIR / "job_observations"
)
INGESTION_JOB_EVENTS_DIR: Final[Path] = INGESTION_DATA_DIR / "job_events"
INGESTION_JOB_LIFECYCLE_DIR: Final[Path] = INGESTION_DATA_DIR / "job_lifecycle"
JOB_LIFECYCLE_STATE_PATH: Final[Path] = (
    INGESTION_JOB_LIFECYCLE_DIR / "job_lifecycle_state.jsonl"
)
JOB_LIFECYCLE_EVENTS_PATH: Final[Path] = (
    INGESTION_JOB_LIFECYCLE_DIR / "job_lifecycle_events.jsonl"
)
JOB_LIFECYCLE_PROCESSED_RESULTS_PATH: Final[Path] = (
    INGESTION_JOB_LIFECYCLE_DIR / "processed_company_results.jsonl"
)
JOB_LIFECYCLE_COMPANY_CURSORS_PATH: Final[Path] = (
    INGESTION_JOB_LIFECYCLE_DIR / "company_cursors.jsonl"
)
CLOSED_MISSING_RUNS_THRESHOLD: Final[int] = 2
JOBS_MASTER_PATH: Final[Path] = RAW_DATA_DIR / "jobs_master.csv"
SILVER_JOB_POSTINGS_PATH: Final[Path] = SILVER_DATA_DIR / "job_postings.csv"
GOLD_COMPANY_COUNTS_PATH: Final[Path] = GOLD_DATA_DIR / "company_counts.csv"
GOLD_SKILL_COUNTS_PATH: Final[Path] = GOLD_DATA_DIR / "skill_counts.csv"
GOLD_COMPANY_SKILL_COUNTS_PATH: Final[Path] = (
    GOLD_DATA_DIR / "company_skill_counts.csv"
)
GOLD_JOB_POSTINGS_PATH: Final[Path] = GOLD_DATA_DIR / "job_postings.csv"
GOLD_METADATA_PATH: Final[Path] = GOLD_DATA_DIR / "metadata.json"
GOLD_HIRING_TRENDS_DAILY_PATH: Final[Path] = GOLD_DATA_DIR / "hiring_trends_daily.csv"
GOLD_HIRING_TRENDS_WEEKLY_PATH: Final[Path] = GOLD_DATA_DIR / "hiring_trends_weekly.csv"
GOLD_COMPANY_ACTIVITY_PATH: Final[Path] = GOLD_DATA_DIR / "company_activity.csv"
GOLD_LIFECYCLE_SUMMARY_PATH: Final[Path] = GOLD_DATA_DIR / "lifecycle_summary.csv"
GOLD_JOB_CHANGES_PATH: Final[Path] = GOLD_DATA_DIR / "job_changes.csv"
GOLD_SKILL_DEMAND_TRENDS_PATH: Final[Path] = GOLD_DATA_DIR / "skill_demand_trends.csv"
GOLD_SKILL_COOCCURRENCE_PATH: Final[Path] = GOLD_DATA_DIR / "skill_cooccurrence.csv"
GOLD_SKILL_COOCCURRENCE_BY_COMPANY_PATH: Final[Path] = (
    GOLD_DATA_DIR / "skill_cooccurrence_by_company.csv"
)
GOLD_SKILL_COOCCURRENCE_BY_TITLE_PATH: Final[Path] = (
    GOLD_DATA_DIR / "skill_cooccurrence_by_title.csv"
)
QUALITY_REPORT_PATH: Final[Path] = QUALITY_DATA_DIR / "latest_report.json"

# Board tokens are provider configuration, not pipeline logic. A new provider
# can add its own configured organizations without changing downstream ETL.
GREENHOUSE_COMPANIES: Final[tuple[str, ...]] = (
    "anthropic",
    "figma",
    "plaid",
    "vercel",
    "datadog",
    "ramp",
    "scaleai",
)

def ensure_project_directories() -> None:
    """Create directories owned by the local data pipeline when needed."""
    for directory in (
        DATA_DIR,
        RAW_DATA_DIR,
        BRONZE_DATA_DIR,
        BRONZE_SNAPSHOTS_DIR,
        SILVER_DATA_DIR,
        GOLD_DATA_DIR,
        QUALITY_DATA_DIR,
        PROCESSED_DATA_DIR,
        INGESTION_DATA_DIR,
        INGESTION_RUNS_DIR,
        INGESTION_COMPANY_RESULTS_DIR,
        INGESTION_JOB_OBSERVATIONS_DIR,
        INGESTION_JOB_EVENTS_DIR,
        INGESTION_JOB_LIFECYCLE_DIR,
        OUTPUTS_DIR,
        CHARTS_DIR,
        REPORTS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
