# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install -e .            # production deps
pip install -e ".[dev]"     # + pytest, pytest-mock, responses

# Run
python run.py --dry-run -v  # full pipeline, prints digest to stdout
python run.py               # full pipeline, sends to Discord

# Test
pytest tests/
pytest tests/test_analyzer.py            # single file
pytest tests/test_analyzer.py::test_name # single test
```

## Required Environment

Copy `config/.env.example` → `.env` with: `TWITTER_BEARER_TOKEN`, `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`, `GITHUB_TOKEN` (optional, raises GitHub rate limits).

Blog sources and Twitter accounts are configured in `config/config.yaml`.

## Architecture

**6-stage sequential pipeline** orchestrated by `src/orchestrator.py`, invoked from `run.py`. Runs stateless once daily — no database, no persistent state between runs.

```
TwitterCollector → BlogCollector → LinkCrawler → Analyzer → Digest → Delivery
```

**Data flow:** Each stage receives the prior stage's typed Pydantic output (all models in `src/models.py`). Tweets and blog posts are merged into unified `ContentItem` objects. A mutable `WorkNotebook` model is passed by reference through every stage, accumulating errors.

**Stage responsibilities:**
- **TwitterCollector** (`src/collector.py`): Twitter API v2 `search/recent` fetching posts from listed influential accounts (last 24h). No keyword search or engagement scoring.
- **BlogCollector** (`src/blog_collector.py`): RSS/Atom feed discovery with HTML scraping fallback. Checks listed blog URLs for new posts in last 24h. Logs failures to `blog_errors.txt`.
- **LinkCrawler** (`src/crawler.py`): Follows reference links 1 level deep from tweets/blog posts. URL dispatch — arXiv (via `arxiv` library), GitHub (REST API for repo metadata + README), blogs (trafilatura with bs4 fallback).
- **Analyzer** (`src/analyzer.py`): Three-phase OpenAI analysis — (1) summarize each content item with reference links, (2) find inter-content relationships with strength ratings, (3) derive insights at technical/business/product levels. Uses JSON response format.
- **Digest** (`src/digest.py`): Assembles 3 markdown sections (Summary, Analysis, Insights), splits into Discord-safe chunks (≤4096 chars per embed)
- **Delivery** (`src/delivery.py`): Discord webhook with embeds, retry with exponential backoff

**Error handling:** Twitter collector failure aborts the run. Blog collector failure degrades gracefully (continues without blog posts). Crawler failure degrades gracefully (continues with uncrawled items). Individual URL failures are skipped. Analyzer failure aborts. Delivery retries 3x.

**Config loading** (`src/config.py`): Merges `config/config.yaml` (accounts, blog sources, thresholds) + `.env` (secrets) into a single `Settings` Pydantic model.
