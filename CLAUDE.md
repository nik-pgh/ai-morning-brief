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
pytest tests/test_ranker.py            # single file
pytest tests/test_ranker.py::test_name # single test
```

## Required Environment

Copy `config/.env.example` → `.env` with: `TWITTER_BEARER_TOKEN`, `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`, `GITHUB_TOKEN` (optional, raises GitHub rate limits).

Tunable thresholds (seed keywords, scoring weights, content limits, batch sizes) live in `config/config.yaml`.

## Architecture

**7-stage sequential pipeline** orchestrated by `src/orchestrator.py`, invoked from `run.py`. Runs stateless once daily — no database, no persistent state between runs.

```
Collector → Ranker → Crawler → Analyzer → Summarizer → Digest → Delivery
```

**Data flow:** Each stage receives the prior stage's typed Pydantic output (all models in `src/models.py`). A mutable `WorkNotebook` model is passed by reference through every stage, accumulating cross-stage context (discovered keywords, top authors, connection notes, errors).

**Stage responsibilities:**
- **Collector** (`src/collector.py`): Twitter API v2 `search/recent` with seed keywords, extracts hashtag-based keywords and top authors
- **Ranker** (`src/ranker.py`): Scores tweets by weighted engagement (`likes*1 + retweets*2 + replies*1.5 + quotes*3`), compacts keywords to top 10
- **Crawler** (`src/crawler.py`): URL dispatch — arXiv (via `arxiv` library), GitHub (REST API for repo metadata + README), blogs (trafilatura with bs4 fallback). Also searches arXiv per trending keyword.
- **Analyzer** (`src/analyzer.py`): Two OpenAI calls — (1) batch classify items with "why?" analysis, (2) find cross-item connections. Uses JSON response format.
- **Summarizer** (`src/summarizer.py`): Single OpenAI call producing 4 markdown sections: Keywords, Summary, Connections, Further Reading
- **Digest** (`src/digest.py`): Assembles final markdown, splits into Discord-safe chunks (≤4096 chars per embed)
- **Delivery** (`src/delivery.py`): Discord webhook with embeds, retry with exponential backoff

**Error handling:** Collector/Ranker failure aborts the run. Crawler failure degrades gracefully (continues with empty crawl data). Individual URL failures are skipped. Analyzer/Summarizer failure aborts. Delivery retries 3x.

**Config loading** (`src/config.py`): Merges `config/config.yaml` (thresholds) + `.env` (secrets) into a single `Settings` Pydantic model.
