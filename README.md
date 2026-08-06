# AI Job Market Intelligence Platform

An analytics platform for collecting AI job postings and transforming job
descriptions into structured market intelligence. The dashboard is a future
consumer of the platform, not the platform itself.

## Current pipeline

The platform has an explicit provider-based ingestion pipeline and a layered
ETL pipeline. Greenhouse is the initial provider; existing analysis scripts
remain supported through compatible processed CSV outputs.

```text
Registered ATS provider -> normalized JobPosting records -> data/raw/jobs_master.csv
                                                -> immutable bronze snapshot
                                                -> normalized silver records
                                                -> validated gold aggregates
                                                -> dashboard and existing analysis scripts
```

Run all registered providers from the repository root:

```bash
python -m ai_job_market ingest
```

Run only Greenhouse:

```bash
python -m ai_job_market ingest --provider greenhouse
```

Logs are emitted as JSON lines to standard error, which makes the command
suitable for cron jobs, GitHub Actions, and future cloud schedulers. The legacy
command remains available:

```bash
python scrapers/greenhouse.py
```

The command writes the canonical master dataset to
`data/raw/jobs_master.csv`. It retains every existing downstream column and
adds `provider`, `external_job_id`, and `collected_at` for provenance.

Create the ETL layers from the current master dataset:

```bash
python -m ai_job_market transform
```

The command creates an immutable JSON Lines snapshot under
`data/bronze/job_snapshots/`, validates and writes normalized records to
`data/silver/job_postings.csv`, and produces dashboard-ready aggregates in
`data/gold/`. It also refreshes the current `data/processed/` CSV contracts for
the existing analysis scripts.

Validate the currently published silver dataset without retransforming it:

```bash
python -m ai_job_market quality-check
```

The quality report is written to `data/quality/latest_report.json`. Bronze,
silver, gold, and quality artifacts are excluded from Git because they are
reproducible pipeline outputs.

## Streamlit dashboard

The dashboard is a read-only consumer of published gold datasets. It never
scrapes, transforms, or reads from raw, bronze, or silver data.

First materialize the gold layer, then launch the application:

```bash
python -m ai_job_market transform
streamlit run dashboard/app.py
```

The dashboard includes Overview, Companies, and Skills pages with interactive
Plotly charts, gold-layer KPIs, job tables, and data-freshness context.

## Adding an ATS provider

1. Create an implementation in `ai_job_market/providers/` that satisfies the
   `ATSProvider` protocol and emits `JobPosting` records.
2. Add one registration in `ai_job_market/providers/registry.py`, supplying
   its factory and configured organization identifiers.

No downstream ETL, analytics, or dashboard change is required.

## Verification

Run the offline ingestion tests without calling job-board APIs:

```bash
venv/bin/python -m unittest discover -s tests -v
```
