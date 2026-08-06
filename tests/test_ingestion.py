"""Offline tests for the Milestone 1 ingestion foundation."""

import csv
import tempfile
import unittest
from pathlib import Path

from ai_job_market.models import JobPosting, ProviderRunResult
from ai_job_market.pipeline.ingestion import run_ingestion, validate_job_postings
from ai_job_market.providers.greenhouse import GreenhouseProvider


class FakeResponse:
    """Small requests.Response stand-in for deterministic provider tests."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Session that returns fixtures keyed by request URL."""

    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, float]] = []

    def get(self, url: str, timeout: float) -> FakeResponse:
        self.requests.append((url, timeout))
        return self.responses[url]


class FakeProvider:
    """Minimal provider used to test pipeline orchestration without HTTP."""

    name = "fake"

    def scrape(
        self,
        companies: tuple[str, ...],
        collected_at: str,
    ) -> ProviderRunResult:
        return ProviderRunResult(
            provider=self.name,
            attempted_companies=list(companies),
            jobs=[
                JobPosting(
                    provider=self.name,
                    external_job_id="role-1",
                    company="example",
                    title="Machine Learning Engineer",
                    location="Remote",
                    updated_at="2026-08-06T00:00:00Z",
                    job_url="https://jobs.example.test/role-1",
                    department="Engineering",
                    office="Remote",
                    description="Build reliable ML systems.",
                    collected_at=collected_at,
                )
            ],
        )


class GreenhouseProviderTests(unittest.TestCase):
    def test_normalizes_greenhouse_response(self) -> None:
        base_url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
        session = FakeSession(
            {
                base_url: FakeResponse(
                    {
                        "jobs": [
                            {
                                "id": 42,
                                "title": "AI Engineer",
                                "location": {"name": "New York"},
                                "updated_at": "2026-08-06T00:00:00Z",
                                "absolute_url": "https://jobs.acme.test/42",
                            }
                        ]
                    }
                ),
                f"{base_url}/42": FakeResponse(
                    {
                        "content": "<p>Build <strong>LLM</strong> systems.</p>",
                        "departments": [{"name": "Engineering"}],
                        "offices": [{"name": "New York"}],
                    }
                ),
            }
        )

        result = GreenhouseProvider(session=session).scrape(
            companies=("acme",),
            collected_at="2026-08-06T12:00:00+00:00",
        )

        self.assertEqual(result.failed_companies, {})
        self.assertEqual(result.detail_failure_count, 0)
        self.assertEqual(len(result.jobs), 1)
        job = result.jobs[0]
        self.assertEqual(job.identity, ("greenhouse", "42"))
        self.assertEqual(job.description, "Build LLM systems.")
        self.assertEqual(job.department, "Engineering")


class IngestionPipelineTests(unittest.TestCase):
    def test_writes_compatible_master_csv_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "jobs_master.csv"
            summary = run_ingestion(
                provider_names=("fake",),
                providers=[FakeProvider()],
                companies_by_provider={"fake": ("example",)},
                output_path=output_path,
                collected_at="2026-08-06T12:00:00+00:00",
            )

            with output_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(summary.job_count, 1)
        self.assertEqual(rows[0]["company"], "example")
        self.assertEqual(rows[0]["description"], "Build reliable ML systems.")
        self.assertEqual(rows[0]["provider"], "fake")
        self.assertEqual(rows[0]["external_job_id"], "role-1")

    def test_rejects_duplicate_provider_job_identity(self) -> None:
        job = FakeProvider().scrape(
            companies=("example",),
            collected_at="2026-08-06T12:00:00+00:00",
        ).jobs[0]

        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_job_postings([job, job])

    def test_rejects_empty_ingestion(self) -> None:
        with self.assertRaisesRegex(ValueError, "no job postings"):
            validate_job_postings([])


if __name__ == "__main__":
    unittest.main()
