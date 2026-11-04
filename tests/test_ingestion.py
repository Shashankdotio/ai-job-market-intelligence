"""Offline tests for the Milestone 1 ingestion foundation."""

import csv
import importlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import requests

import ai_job_market.history as history_module
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


class FlakySession:
    """Session that fails once before succeeding to exercise retry logic."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url: str, timeout: float) -> FakeResponse:
        if self.calls >= len(self.responses):
            raise AssertionError("No more mocked responses configured")
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


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


class EmptyProvider:
    """Provider that returns a valid empty board snapshot."""

    name = "empty"

    def scrape(
        self,
        companies: tuple[str, ...],
        collected_at: str,
    ) -> ProviderRunResult:
        return ProviderRunResult(
            provider=self.name,
            attempted_companies=list(companies),
            jobs=[],
        )


class FailingProvider:
    """Provider that fails its configured company without returning jobs."""

    name = "failing"

    def scrape(
        self,
        companies: tuple[str, ...],
        collected_at: str,
    ) -> ProviderRunResult:
        return ProviderRunResult(
            provider=self.name,
            attempted_companies=list(companies),
            failed_companies={companies[0]: "board fetch failed"},
            jobs=[],
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

    def test_tracks_company_specific_outcomes(self) -> None:
        class MixedProvider:
            name = "mixed"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs("good-company", [
                    JobPosting(
                        provider=self.name,
                        external_job_id="job-1",
                        company="good-company",
                        title="Engineer",
                        location="Remote",
                        updated_at="2026-01-01T00:00:00Z",
                        job_url="https://jobs.example.test/job-1",
                        department="Engineering",
                        office="Remote",
                        description="Build things.",
                        collected_at=collected_at,
                    )
                ])
                result.record_company_failure("bad-company", "board fetch failed")
                return result

        result = MixedProvider().scrape(("good-company", "bad-company"), "2026-08-06T00:00:00Z")
        self.assertEqual(len(result.get_company_jobs("good-company")), 1)
        self.assertEqual(len(result.get_company_jobs("bad-company")), 0)
        self.assertEqual(result.get_company_failed("good-company"), None)
        self.assertEqual(result.get_company_failed("bad-company"), "board fetch failed")


class IngestionPipelineTests(unittest.TestCase):
    def test_retries_transient_greenhouse_failures(self) -> None:
        base_url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
        session = FlakySession(
            [
                requests.exceptions.Timeout("temporary timeout"),
                FakeResponse(
                    {
                        "jobs": [
                            {
                                "id": 42,
                                "title": "AI Engineer",
                                "location": "Remote",
                                "updated_at": "2026-08-06T00:00:00Z",
                                "absolute_url": "https://jobs.acme.test/42",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "content": "<p>Build <strong>LLM</strong> systems.</p>",
                        "departments": [{"name": "Engineering"}],
                        "offices": [{"name": "Remote"}],
                    }
                ),
            ]
        )

        result = GreenhouseProvider(
            session=session,
            max_retries=1,
            backoff_seconds=0.0,
        ).scrape(
            companies=("acme",),
            collected_at="2026-08-06T12:00:00+00:00",
        )

        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].location, "Remote")

    def test_records_all_success_run_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_dir = root / "runs"
            company_results_dir = root / "company_results"
            output_path = root / "jobs_master.csv"
            summary = run_ingestion(
                provider_names=("fake",),
                providers=[FakeProvider()],
                companies_by_provider={"fake": ("example",)},
                output_path=output_path,
                collected_at="2026-08-06T12:00:00+00:00",
                runs_dir=runs_dir,
                company_results_dir=company_results_dir,
            )
            run_files = sorted(runs_dir.glob("*.json"))
            company_files = sorted(company_results_dir.glob("*.jsonl"))

            self.assertEqual(summary.run_id, run_files[0].stem)
            self.assertEqual(len(run_files), 1)
            self.assertEqual(len(company_files), 1)
            self.assertEqual(summary.job_count, 1)
            self.assertTrue(output_path.exists())

    def test_records_partial_success_and_all_failure_without_overwriting_master_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_path = root / "jobs_master.csv"
            output_path.write_text("existing-data\n", encoding="utf-8")

            partial = run_ingestion(
                provider_names=("fake", "failing"),
                providers=[FakeProvider(), FailingProvider()],
                companies_by_provider={
                    "fake": ("example",),
                    "failing": ("bad-company",),
                },
                output_path=output_path,
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
            )
            partial_csv = output_path.read_text(encoding="utf-8")

            failing = run_ingestion(
                provider_names=("failing",),
                providers=[FailingProvider()],
                companies_by_provider={"failing": ("example",)},
                output_path=output_path,
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
            )

            partial_json = sorted((root / "runs").glob("*.json"))[0].read_text(
                encoding="utf-8"
            )
            failing_json = sorted((root / "runs").glob("*.json"))[-1].read_text(
                encoding="utf-8"
            )

            self.assertEqual(partial.job_count, 1)
            self.assertEqual(failing.job_count, 0)
            self.assertIn('"status": "partial_success"', partial_json)
            self.assertIn('"status": "failed"', failing_json)
            self.assertEqual(output_path.read_text(encoding="utf-8"), partial_csv)

    def test_incremental_company_results_are_preserved_after_interruption(self) -> None:
        class InterruptionProvider:
            name = "interrupt"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(
                    companies[0],
                    [
                        JobPosting(
                            provider=self.name,
                            external_job_id="job-1",
                            company=companies[0],
                            title="Engineer",
                            location="Remote",
                            updated_at="2026-08-06T00:00:00Z",
                            job_url="https://jobs.example.test/job-1",
                            department="Engineering",
                            office="Remote",
                            description="Build things.",
                            collected_at=collected_at,
                        )
                    ],
                )
                result.record_company_failure(companies[1], "board fetch failed")
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_dir = root / "runs"
            company_results_dir = root / "company_results"
            output_path = root / "jobs_master.csv"
            summary = run_ingestion(
                provider_names=("interrupt",),
                providers=[InterruptionProvider()],
                companies_by_provider={"interrupt": ("first-company", "second-company")},
                output_path=output_path,
                runs_dir=runs_dir,
                company_results_dir=company_results_dir,
            )
            lines = sorted((company_results_dir / f"{summary.run_id}.jsonl").read_text(encoding="utf-8").splitlines())

        self.assertEqual(len(lines), 2)
        self.assertIn('"company_slug": "first-company"', lines[0])
        self.assertIn('"company_slug": "second-company"', lines[1])

    def test_company_summaries_are_independent_per_company(self) -> None:
        class MixedFakeProvider:
            name = "fake"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                for company in companies:
                    if company == "good-company":
                        result.record_company_jobs(
                            company,
                            [
                                JobPosting(
                                    provider=self.name,
                                    external_job_id="job-1",
                                    company=company,
                                    title="Engineer",
                                    location="Remote",
                                    updated_at="2026-08-06T00:00:00Z",
                                    job_url="https://jobs.example.test/job-1",
                                    department="Engineering",
                                    office="Remote",
                                    description="Build things.",
                                    collected_at=collected_at,
                                )
                            ],
                        )
                    else:
                        result.record_company_failure(company, "board fetch failed")
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = run_ingestion(
                provider_names=("fake",),
                providers=[MixedFakeProvider()],
                companies_by_provider={"fake": ("good-company", "bad-company")},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
            )
            company_results = [
                json.loads(line)
                for line in (root / "company_results").joinpath(f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(company_results), 2)
        good = next(item for item in company_results if item["company_slug"] == "good-company")
        bad = next(item for item in company_results if item["company_slug"] == "bad-company")
        self.assertEqual(good["jobs_fetched"], 1)
        self.assertTrue(good["is_trustworthy"])
        self.assertEqual(bad["jobs_fetched"], 0)
        self.assertFalse(bad["is_trustworthy"])

    def test_records_empty_valid_company_board_as_successful(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_path = root / "jobs_master.csv"
            run = run_ingestion(
                provider_names=("empty",),
                providers=[EmptyProvider()],
                companies_by_provider={"empty": ("example",)},
                output_path=output_path,
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
            )
            run_record = next((root / "runs").glob("*.json")).read_text(encoding="utf-8")

        self.assertEqual(run.job_count, 0)
        self.assertIn('"status": "succeeded"', run_record)
        self.assertFalse(output_path.exists())

    def test_legacy_scraper_module_imports(self) -> None:
        module = importlib.import_module("scrapers.greenhouse")
        self.assertTrue(hasattr(module, "fetch_jobs"))

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

    def test_records_discovered_observation_and_event_for_first_trustworthy_snapshot(self) -> None:
        class HistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(
                    companies[0],
                    [
                        JobPosting(
                            provider=self.name,
                            external_job_id="job-1",
                            company=companies[0],
                            title="Staff Engineer",
                            location="Remote",
                            updated_at="2026-08-06T00:00:00Z",
                            job_url="https://jobs.example.test/job-1",
                            department="Engineering",
                            office="Remote",
                            description="Build platform systems.",
                            collected_at=collected_at,
                        )
                    ],
                )
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider()],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observations = [
                json.loads(line)
                for line in (observations_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events = [
                json.loads(line)
                for line in (events_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["job_key"], "history:job-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "discovered")
        self.assertIn("title", events[0]["changed_fields"])

    def test_unchanged_reobservation_does_not_emit_update_event(self) -> None:
        class HistoryProvider:
            name = "history"

            def __init__(self, job: JobPosting) -> None:
                self.job = job

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [self.job])
                return result

        job = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Staff Engineer",
            location="Remote",
            updated_at="2026-08-06T00:00:00Z",
            job_url="https://jobs.example.test/job-1",
            department="Engineering",
            office="Remote",
            description="Build platform systems.",
            collected_at="2026-08-06T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            first_run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(job)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            second_run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(job)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            first_events = [
                json.loads(line)
                for line in (events_dir / f"{first_run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            second_event_path = events_dir / f"{second_run.run_id}.jsonl"
            second_events = (
                [
                    json.loads(line)
                    for line in second_event_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if second_event_path.exists()
                else []
            )
            second_observations = [
                json.loads(line)
                for line in (observations_dir / f"{second_run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(first_events), 1)
        self.assertEqual(first_events[0]["event_type"], "discovered")
        self.assertEqual(len(second_observations), 1)
        self.assertEqual(second_events, [])

    def test_uses_custom_observation_directory_for_change_detection(self) -> None:
        class HistoryProvider:
            name = "history"

            def __init__(self, job: JobPosting) -> None:
                self.job = job

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [self.job])
                return result

        current_job = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Engineer",
            location="Remote",
            updated_at="2026-08-06T00:00:00Z",
            job_url="https://jobs.example.test/job-1",
            department="Engineering",
            office="Remote",
            description="Build platform systems.",
            collected_at="2026-08-06T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            global_history_dir = root / "global_history"
            custom_history_dir = root / "custom_history"
            events_dir = root / "job_events"
            global_history_dir.mkdir(parents=True, exist_ok=True)
            custom_history_dir.mkdir(parents=True, exist_ok=True)
            previous_global = {
                "observation_id": "legacy-global",
                "provider": "history",
                "company_slug": "alpha",
                "external_job_id": "job-1",
                "job_key": "history:job-1",
                "run_id": "legacy-run",
                "company_result_id": "legacy-run:history:alpha",
                "observed_at": "2026-08-05T00:00:00Z",
                "title": "Legacy Title",
                "location": "Remote",
                "department": "Engineering",
                "office": "Remote",
                "job_url": "https://jobs.example.test/job-1",
                "normalized_description_hash": "deadbeef",
                "skill_signature": None,
                "created_at": "2026-08-05T00:00:00Z",
            }
            custom_hash = history_module._normalized_description_hash(current_job.description)
            previous_custom = {
                "observation_id": "custom-prior",
                "provider": "history",
                "company_slug": "alpha",
                "external_job_id": "job-1",
                "job_key": "history:job-1",
                "run_id": "custom-run",
                "company_result_id": "custom-run:history:alpha",
                "observed_at": "2026-08-06T00:00:00Z",
                "title": "Engineer",
                "location": "Remote",
                "department": "Engineering",
                "office": "Remote",
                "job_url": "https://jobs.example.test/job-1",
                "normalized_description_hash": custom_hash,
                "skill_signature": None,
                "created_at": "2026-08-06T00:00:00Z",
            }
            (global_history_dir / "global.jsonl").write_text(
                json.dumps(previous_global, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (custom_history_dir / "custom.jsonl").write_text(
                json.dumps(previous_custom, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            original_global_dir = history_module.INGESTION_JOB_OBSERVATIONS_DIR
            history_module.INGESTION_JOB_OBSERVATIONS_DIR = global_history_dir
            try:
                run = run_ingestion(
                    provider_names=("history",),
                    providers=[HistoryProvider(current_job)],
                    companies_by_provider={"history": ("alpha",)},
                    output_path=root / "jobs_master.csv",
                    runs_dir=root / "runs",
                    company_results_dir=root / "company_results",
                    job_observations_dir=custom_history_dir,
                    job_events_dir=events_dir,
                )
                event_path = events_dir / f"{run.run_id}.jsonl"
                events = (
                    [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    if event_path.exists()
                    else []
                )
            finally:
                history_module.INGESTION_JOB_OBSERVATIONS_DIR = original_global_dir

        self.assertEqual(events, [])

    def test_detects_field_changes_and_ignores_url_only_changes(self) -> None:
        class HistoryProvider:
            name = "history"

            def __init__(self, job: JobPosting) -> None:
                self.job = job

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [self.job])
                return result

        baseline = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Staff Engineer",
            location="Remote",
            updated_at="2026-08-06T00:00:00Z",
            job_url="https://jobs.example.test/job-1",
            department="Engineering",
            office="Remote",
            description="Build platform systems.",
            collected_at="2026-08-06T00:00:00Z",
        )
        changed = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Senior Staff Engineer",
            location="New York",
            updated_at="2026-08-07T00:00:00Z",
            job_url="https://jobs.example.test/job-1-v2",
            department="Platform",
            office="New York",
            description="Build distributed systems.",
            collected_at="2026-08-07T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            _ = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(baseline)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(changed)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            events = [
                json.loads(line)
                for line in (events_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "updated")
        self.assertEqual(
            set(events[0]["changed_fields"]),
            {"title", "location", "department", "normalized_description_hash"},
        )

    def test_failed_or_incomplete_company_snapshots_do_not_record_history(self) -> None:
        class FailingHistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_failure(companies[0], "board fetch failed")
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[FailingHistoryProvider()],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observation_file = observations_dir / f"{run.run_id}.jsonl"
            event_file = events_dir / f"{run.run_id}.jsonl"

        self.assertFalse(observation_file.exists())
        self.assertFalse(event_file.exists())

    def test_same_external_job_id_across_companies_stays_separate(self) -> None:
        class SameIdentityProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                for company in companies:
                    result.record_company_jobs(
                        company,
                        [
                            JobPosting(
                                provider=self.name,
                                external_job_id="job-1",
                                company=company,
                                title="Engineer",
                                location="Remote",
                                updated_at="2026-08-06T00:00:00Z",
                                job_url=f"https://jobs.example.test/{company}/job-1",
                                department="Engineering",
                                office="Remote",
                                description=f"Build for {company}.",
                                collected_at=collected_at,
                            )
                        ],
                    )
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[SameIdentityProvider()],
                companies_by_provider={"history": ("alpha", "beta")},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observations = [
                json.loads(line)
                for line in (observations_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events = [
                json.loads(line)
                for line in (events_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(observations), 2)
        self.assertEqual({item["company_slug"] for item in observations}, {"alpha", "beta"})
        self.assertEqual(len(events), 2)
        self.assertEqual({event["company_slug"] for event in events}, {"alpha", "beta"})

    def test_partial_run_records_history_only_for_successful_company(self) -> None:
        class PartialHistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(
                    "good-company",
                    [
                        JobPosting(
                            provider=self.name,
                            external_job_id="job-1",
                            company="good-company",
                            title="Engineer",
                            location="Remote",
                            updated_at="2026-08-06T00:00:00Z",
                            job_url="https://jobs.example.test/good-company/job-1",
                            department="Engineering",
                            office="Remote",
                            description="Build things.",
                            collected_at=collected_at,
                        )
                    ],
                )
                result.record_company_failure("bad-company", "board fetch failed")
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[PartialHistoryProvider()],
                companies_by_provider={"history": ("good-company", "bad-company")},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observations = [
                json.loads(line)
                for line in (observations_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events = [
                json.loads(line)
                for line in (events_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["company_slug"], "good-company")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["company_slug"], "good-company")

    def test_valid_empty_company_snapshot_generates_no_history_records(self) -> None:
        class EmptyHistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [])
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[EmptyHistoryProvider()],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observation_path = observations_dir / f"{run.run_id}.jsonl"
            event_path = events_dir / f"{run.run_id}.jsonl"

        self.assertEqual(run.job_count, 0)
        self.assertFalse(observation_path.exists())
        self.assertFalse(event_path.exists())

    def test_observation_and_event_timestamps_are_utc_aware(self) -> None:
        class HistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(
                    companies[0],
                    [
                        JobPosting(
                            provider=self.name,
                            external_job_id="job-1",
                            company=companies[0],
                            title="Engineer",
                            location="Remote",
                            updated_at="2026-08-06T00:00:00Z",
                            job_url="https://jobs.example.test/job-1",
                            department="Engineering",
                            office="Remote",
                            description="Build things.",
                            collected_at=collected_at,
                        )
                    ],
                )
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider()],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observation = json.loads((observations_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").strip())
            event = json.loads((events_dir / f"{run.run_id}.jsonl").read_text(encoding="utf-8").strip())

        for key in ("observed_at", "created_at"):
            value = datetime.fromisoformat(observation[key].replace("Z", "+00:00"))
            self.assertIsNotNone(value.tzinfo)
            self.assertEqual(value.utcoffset(), timedelta(0))
        value = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.utcoffset(), timedelta(0))

    def test_individual_field_changes_emit_specific_updated_events(self) -> None:
        class HistoryProvider:
            name = "history"

            def __init__(self, job: JobPosting) -> None:
                self.job = job

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [self.job])
                return result

        scenarios = [
            ("title", "Engineer", "Senior Engineer", "Build things."),
            ("location", "Remote", "New York", "Build things."),
            ("department", "Engineering", "Platform", "Build things."),
            ("normalized_description_hash", "Build things.", "Build new things.", "Build things."),
        ]

        for field_name, original_value, updated_value, description in scenarios:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                observations_dir = root / "job_observations"
                events_dir = root / "job_events"
                baseline = JobPosting(
                    provider="history",
                    external_job_id="job-1",
                    company="alpha",
                    title="Engineer",
                    location="Remote",
                    updated_at="2026-08-06T00:00:00Z",
                    job_url="https://jobs.example.test/job-1",
                    department="Engineering",
                    office="Remote",
                    description=description,
                    collected_at="2026-08-06T00:00:00Z",
                )
                changed = JobPosting(
                    provider="history",
                    external_job_id="job-1",
                    company="alpha",
                    title="Engineer" if field_name != "title" else updated_value,
                    location="Remote" if field_name != "location" else updated_value,
                    updated_at="2026-08-07T00:00:00Z",
                    job_url="https://jobs.example.test/job-1",
                    department="Engineering" if field_name != "department" else updated_value,
                    office="Remote",
                    description=description if field_name != "normalized_description_hash" else "<p>Build <b>new things</b>.</p>",
                    collected_at="2026-08-07T00:00:00Z",
                )
                _ = run_ingestion(
                    provider_names=("history",),
                    providers=[HistoryProvider(baseline)],
                    companies_by_provider={"history": ("alpha",)},
                    output_path=root / "jobs_master.csv",
                    runs_dir=root / "runs",
                    company_results_dir=root / "company_results",
                    job_observations_dir=observations_dir,
                    job_events_dir=events_dir,
                )
                run = run_ingestion(
                    provider_names=("history",),
                    providers=[HistoryProvider(changed)],
                    companies_by_provider={"history": ("alpha",)},
                    output_path=root / "jobs_master.csv",
                    runs_dir=root / "runs",
                    company_results_dir=root / "company_results",
                    job_observations_dir=observations_dir,
                    job_events_dir=events_dir,
                )
                event_path = events_dir / f"{run.run_id}.jsonl"
                events = (
                    [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    if event_path.exists()
                    else []
                )

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "updated")
            self.assertEqual(events[0]["changed_fields"], [field_name])

    def test_description_html_whitespace_only_changes_do_not_emit_update_event(self) -> None:
        class HistoryProvider:
            name = "history"

            def __init__(self, job: JobPosting) -> None:
                self.job = job

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(companies[0], [self.job])
                return result

        baseline = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Engineer",
            location="Remote",
            updated_at="2026-08-06T00:00:00Z",
            job_url="https://jobs.example.test/job-1",
            department="Engineering",
            office="Remote",
            description="Build platform systems.",
            collected_at="2026-08-06T00:00:00Z",
        )
        changed = JobPosting(
            provider="history",
            external_job_id="job-1",
            company="alpha",
            title="Engineer",
            location="Remote",
            updated_at="2026-08-07T00:00:00Z",
            job_url="https://jobs.example.test/job-1",
            department="Engineering",
            office="Remote",
            description="<p>  Build   platform   systems. </p>",
            collected_at="2026-08-07T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            _ = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(baseline)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            run = run_ingestion(
                provider_names=("history",),
                providers=[HistoryProvider(changed)],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            event_path = events_dir / f"{run.run_id}.jsonl"
            events = (
                [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if event_path.exists()
                else []
            )

        self.assertEqual(events, [])

    def test_duplicate_processing_of_same_company_result_is_idempotent(self) -> None:
        class HistoryProvider:
            name = "history"

            def scrape(self, companies, collected_at):
                result = ProviderRunResult(provider=self.name, attempted_companies=list(companies))
                result.record_company_jobs(
                    companies[0],
                    [
                        JobPosting(
                            provider=self.name,
                            external_job_id="job-1",
                            company=companies[0],
                            title="Staff Engineer",
                            location="Remote",
                            updated_at="2026-08-06T00:00:00Z",
                            job_url="https://jobs.example.test/job-1",
                            department="Engineering",
                            office="Remote",
                            description="Build platform systems.",
                            collected_at=collected_at,
                        )
                    ],
                )
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observations_dir = root / "job_observations"
            events_dir = root / "job_events"
            provider = HistoryProvider()
            run = run_ingestion(
                provider_names=("history",),
                providers=[provider],
                companies_by_provider={"history": ("alpha",)},
                output_path=root / "jobs_master.csv",
                runs_dir=root / "runs",
                company_results_dir=root / "company_results",
                job_observations_dir=observations_dir,
                job_events_dir=events_dir,
            )
            observation_file = observations_dir / f"{run.run_id}.jsonl"
            event_file = events_dir / f"{run.run_id}.jsonl"
            first_observations = [
                json.loads(line)
                for line in observation_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            first_events = [
                json.loads(line)
                for line in event_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            # Re-run the same company result in the same run should not create duplicates.
            company_result = {
                "provider": "history",
                "company_slug": "alpha",
                "is_complete_snapshot": True,
                "is_trustworthy": True,
            }
            from ai_job_market.history import record_company_job_history

            record_company_job_history(
                run_id=run.run_id,
                company_result=company_result,
                jobs=provider.scrape(("alpha",), "2026-08-06T00:00:00Z").get_company_jobs("alpha"),
                observations_dir=observations_dir,
                events_dir=events_dir,
            )
            second_observations = [
                json.loads(line)
                for line in observation_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            second_events = [
                json.loads(line)
                for line in event_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(first_observations), 1)
        self.assertEqual(len(first_events), 1)
        self.assertEqual(len(second_observations), 1)
        self.assertEqual(len(second_events), 1)


if __name__ == "__main__":
    unittest.main()
