"""Read-only validation and loading for dashboard gold datasets."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd


GOLD_FILE_NAMES: Final[dict[str, str]] = {
    "company_counts": "company_counts.csv",
    "skill_counts": "skill_counts.csv",
    "company_skill_counts": "company_skill_counts.csv",
    "job_postings": "job_postings.csv",
    "metadata": "metadata.json",
}
REQUIRED_COLUMNS: Final[dict[str, set[str]]] = {
    "company_counts": {"company", "job_count"},
    "skill_counts": {"skill", "job_count"},
    "company_skill_counts": {"company", "skill", "job_count"},
    "job_postings": {
        "company",
        "title",
        "location",
        "updated_at",
        "job_url",
        "skills",
    },
}


class GoldDataUnavailableError(RuntimeError):
    """Raised when the dashboard's published data contract is unavailable."""


@dataclass(frozen=True, slots=True)
class GoldData:
    """Dashboard datasets loaded exclusively from the published gold layer."""

    company_counts: pd.DataFrame
    skill_counts: pd.DataFrame
    company_skill_counts: pd.DataFrame
    job_postings: pd.DataFrame
    metadata: dict[str, Any]


def load_gold_data(gold_directory: Path) -> GoldData:
    """Load and validate all datasets required by the Streamlit application."""
    paths = {
        name: gold_directory / file_name
        for name, file_name in GOLD_FILE_NAMES.items()
    }
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        missing_files = ", ".join(sorted(missing))
        raise GoldDataUnavailableError(
            "Gold dashboard datasets are unavailable: "
            f"{missing_files}. Run `python -m ai_job_market transform`."
        )

    frames = {
        name: _read_gold_csv(path, REQUIRED_COLUMNS[name])
        for name, path in paths.items()
        if name != "metadata"
    }
    with paths["metadata"].open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)

    if not isinstance(metadata, dict):
        raise GoldDataUnavailableError("Gold metadata.json must contain an object.")

    for frame_name in ("company_counts", "skill_counts", "company_skill_counts"):
        frames[frame_name]["job_count"] = pd.to_numeric(
            frames[frame_name]["job_count"], errors="raise"
        )

    return GoldData(metadata=metadata, **frames)


def _read_gold_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise GoldDataUnavailableError(
            f"Gold dataset {path.name} is missing columns: "
            f"{', '.join(sorted(missing_columns))}."
        )
    return frame
