# AI Morning Brief

A daily AI intelligence digest that monitors influential accounts and trending topics, analyzes content, and delivers concise summaries to Discord.

## Features

- **Account-Based Fetching**: Monitors 26 influential AI accounts (Karpathy, OpenAI, Anthropic, etc.)
- **Dynamic Keyword Extraction**: Discovers trending topics from account tweets
- **Multi-Source Crawling**: Extracts content from arXiv papers, GitHub repos, and blogs
- **AI-Powered Analysis**: Classifies and summarizes content using GPT-4o-mini
- **Discord Delivery**: Sends formatted daily digests to your Discord channel

## Pipeline Architecture

```
Collector → Ranker → Crawler → Analyzer → Summarizer → Digest → Delivery
```

| Stage | Description |
|-------|-------------|
| **Collector** | Fetches tweets from influential accounts + keyword search |
| **Ranker** | Scores tweets by engagement (likes, retweets, replies, quotes) |
| **Crawler** | Extracts content from URLs (arXiv, GitHub, blogs) |
| **Analyzer** | Classifies items and finds connections (LLM) |
| **Summarizer** | Generates markdown summary (LLM) |
| **Digest** | Assembles final output, splits into Discord-safe chunks |
| **Delivery** | Sends to Discord via webhook |

## Quick Start

### 1. Install

```bash
pip install -e .            # production deps
pip install -e ".[dev]"     # + pytest, pytest-mock, responses
```

### 2. Configure

Copy `config/.env.example` to `.env` and fill in your credentials:

```bash
cp config/.env.example .env
```

Required environment variables:
- `TWITTER_BEARER_TOKEN` - Twitter API v2 bearer token
- `OPENAI_API_KEY` - OpenAI API key
- `DISCORD_WEBHOOK_URL` - Discord webhook URL
- `GITHUB_TOKEN` (optional) - Raises GitHub API rate limits

### 3. GitHub Secrets (For Automated Runs)

To enable the daily GitHub Action, add the following secrets in your repository settings (**Settings** > **Secrets and variables** > **Actions** > **New repository secret**):

- `TWITTER_BEARER_TOKEN`
- `OPENAI_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `GH_PAT` (Optional, maps to `GITHUB_TOKEN`)

### 4. Run

```bash
# Dry run (prints digest, no Discord delivery)
python run.py --dry-run -v

# Full run (sends to Discord)
python run.py -v
```

### 4. Schedule (Optional)

Run daily at 7 AM:

```bash
0 7 * * * cd /path/to/ai-morning-brief && python run.py
```

## Configuration

Edit `config/config.yaml` to customize:

- `seed_keywords` - Base keywords for tweet search
- `influential_accounts` - Twitter accounts to monitor
- `account_fetch_limit` / `tweet_fetch_limit` - Number of tweets to fetch
- `top_tweets_count` - How many top tweets to process
- Scoring weights, content limits, model settings, etc.

## Testing

```bash
pytest tests/                          # all tests
pytest tests/test_collector.py         # single file
pytest tests/test_collector.py::test_name  # single test
```

## Project Structure

```
ai-morning-brief/
├── src/                  # Core pipeline code
│   ├── collector.py      # Twitter fetching + keyword extraction
│   ├── ranker.py         # Engagement scoring
│   ├── crawler.py        # URL content extraction
│   ├── analyzer.py       # LLM classification
│   ├── summarizer.py     # LLM summarization
│   ├── digest.py         # Markdown assembly
│   ├── delivery.py       # Discord webhook
│   ├── orchestrator.py   # Pipeline coordinator
│   ├── models.py         # Pydantic models
│   └── config.py         # Settings loader
├── config/               # Configuration files
│   ├── config.yaml       # Tunable parameters
│   └── .env.example      # Environment template
├── docs/                 # Documentation
│   └── architecture.md   # System design
├── tests/                # Unit tests
├── run.py                # Entry point
└── pyproject.toml        # Dependencies
```

## License

MIT
