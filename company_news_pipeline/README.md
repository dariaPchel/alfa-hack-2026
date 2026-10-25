# Company news analysis pipeline

This directory contains the company news feature as a reviewable bundle: the Flask blueprint, scheduled news collection, AutoGen analysis roles, typed agent tools, RouterAI chat and embedding clients, Chroma ingestion/retrieval, mock fixtures, methodology notes, dashboard assets, deployment files, and implementation plans.

## Layout

- `news_analytics/` — Python services and orchestration.
- `news_analytics/knowledge/` — RouterAI embedding adapter, two Chroma retrieval paths, and ingestion manifests.
- `data/mock/` — deterministic, fabricated hackathon-shaped CSVs.
- `data/methodology_sources/` — attributed local risk-method summaries.
- `templates/`, `static/` — company news dashboard.
- `docs/superpowers/` — accepted design and implementation plans.
- `Dockerfile`, `compose.yaml` — API, worker, ingestion job, and separate Alpha/methodology Chroma services.
- `requirements.txt` — feature-specific dependencies, included by the repository root requirements file.

## Runtime inputs kept outside this bundle

The supplied Alpha Bank research PDFs and their extraction output live in ignored root `data/alfa_research/`. The Rusprofile Playwright session remains in ignored root `.local/`. Runtime `.env`, SQLite, and local Chroma data also stay outside source control. This keeps credentials and large/private source material out of the commit while preserving the code, manifests, mock fixtures, and methodology notes needed to reproduce the pipeline.

## Start here

Follow [`docs/company-news-runbook.md`](docs/company-news-runbook.md) for RouterAI configuration, embedding ingestion, local use, and Docker deployment. Docker commands are run from the repository root with `-f company_news_pipeline/compose.yaml`.
