"""Command-line interface for running platform pipelines."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from ai_job_market.logging import configure_logging
from ai_job_market.pipeline.ingestion import run_ingestion
from ai_job_market.pipeline.transformation import run_quality_check, run_transformation
from ai_job_market.providers.registry import available_providers


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, scheduler-friendly pipeline command interface."""
    parser = argparse.ArgumentParser(
        prog="ai-job-market",
        description="Run AI Job Market Intelligence Platform pipelines.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Collect job postings from registered ATS providers.",
    )
    ingest_parser.add_argument(
        "--provider",
        action="append",
        choices=available_providers(),
        help="Provider to run. Repeat to run several; defaults to all.",
    )
    ingest_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit debug-level structured logs.",
    )
    transform_parser = subparsers.add_parser(
        "transform",
        help="Create bronze, silver, gold, and data-quality artifacts.",
    )
    transform_parser.add_argument(
        "--source",
        type=Path,
        help="Master jobs CSV to transform; defaults to data/raw/jobs_master.csv.",
    )
    transform_parser.add_argument(
        "--snapshot-id",
        help="Optional immutable bronze snapshot identifier.",
    )
    transform_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit debug-level structured logs.",
    )
    quality_parser = subparsers.add_parser(
        "quality-check",
        help="Validate the silver job-postings dataset.",
    )
    quality_parser.add_argument(
        "--silver-path",
        type=Path,
        help="Silver CSV to validate; defaults to data/silver/job_postings.csv.",
    )
    quality_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit debug-level structured logs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command and return a scheduler-friendly process exit code."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    configure_logging(verbose=arguments.verbose)

    try:
        if arguments.command == "ingest":
            run_ingestion(provider_names=arguments.provider)
            return 0
        if arguments.command == "transform":
            transform_kwargs = {
                key: value
                for key, value in {
                    "source_path": arguments.source,
                    "snapshot_id": arguments.snapshot_id,
                }.items()
                if value is not None
            }
            run_transformation(**transform_kwargs)
            return 0
        if arguments.command == "quality-check":
            if arguments.silver_path is None:
                run_quality_check()
            else:
                run_quality_check(silver_path=arguments.silver_path)
            return 0
    except Exception:
        LOGGER.exception(
            "Pipeline execution failed",
            extra={"event": "pipeline_failed"},
        )
        return 1

    parser.error(f"Unsupported command: {arguments.command}")
    return 2
