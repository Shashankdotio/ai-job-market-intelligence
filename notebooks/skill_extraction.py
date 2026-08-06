"""Backward-compatible skill-extraction entry point.

Use ``python -m ai_job_market transform`` for the complete bronze, silver,
gold, and data-quality workflow. This file retains the former importable skill
helpers and direct-script behavior.
"""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_job_market.etl.skills import SKILLS, extract_skills
from ai_job_market.pipeline.transformation import run_transformation
from ai_job_market.text import clean_html


def main() -> int:
    """Create the legacy skill datasets through the shared ETL pipeline."""
    summary = run_transformation()
    print(f"Saved jobs_with_skills.csv ({summary.quality_report.record_count} jobs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
