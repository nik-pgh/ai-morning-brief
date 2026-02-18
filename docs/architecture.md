# AI Morning Brief — v2 Pipeline Architecture

## Overview
Daily AI intelligence briefing: monitors high-signal Twitter accounts and curated blogs, ranks tweets by engagement, follows reference links, runs three-phase LLM analysis, and delivers a witty digest to Discord.

**Design goal:** minimal, reliable, extensible, stateless

---

# 1. System Flow

```
TwitterCollector → Tweet Ranking (top 10) → BlogCollector → LinkCrawler → Analyzer → Digest → Delivery
```

Runs daily at 6am UTC via GitHub Actions (`.github/workflows/daily-brief.yml`) or manually via `python run.py`.

---

# 2. Entry Points

### `run.py` — CLI entry point (34 lines)
- `main()` → parses `--dry-run` and `--verbose`/`-v` flags → calls `run_pipeline(dry_run)`
- Dry run prints digest to stdout instead of sending to Discord

### `.github/workflows/daily-brief.yml` — GitHub Actions scheduler
- Cron: `0 6 * * *` (6am UTC) + `workflow_dispatch` for manual trigger
- Secrets required: `TWITTER_BEARER_TOKEN`, `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`, `GH_PAT`
- Steps: checkout → setup Python 3.11 → `pip install -e .` → `python run.py`

---

# 3. Configuration

### `src/config.py` — Settings loader (33 lines)
- **Function:** `load_settings() → Settings`
- Merges `config/config.yaml` + `.env` (via python-dotenv)
- YAML sections: `collector` (accounts, fetch_limit), `blog_sources` (URL list), `crawler` (content_limits), `analyzer` (model, tokens, batch_size), `delivery` (embed chars)
- Environment variables: `TWITTER_BEARER_TOKEN`, `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`, `GITHUB_TOKEN` (optional)

### `config/config.yaml` — Runtime configuration
- `collector.influential_accounts`: 37 Twitter handles (karpathy, OpenAI, AnthropicAI, sama, etc.)
- `collector.account_fetch_limit`: 100
- `blog_sources`: 22 blog/newsletter URLs
- `crawler.content_limits`: blog=3000, paper=2000, readme=2000 chars
- `analyzer`: openai_model="gpt-4o-mini", openai_max_tokens=1024, batch_size=10
- `delivery`: discord_max_embed_chars=4096

---

# 4. Data Models — `src/models.py`

All Pydantic v2 BaseModels. This is the single source of truth for data structures.

### Settings (lines 9–24)
```
Settings: twitter_bearer_token, openai_api_key, discord_webhook_url, github_token?,
          influential_accounts[], account_fetch_limit=100, blog_sources[],
          content_max_chars_blog=3000, content_max_chars_paper=2000, content_max_chars_readme=2000,
          openai_model="gpt-4o-mini", openai_max_tokens=1024, analyzer_batch_size=10,
          discord_max_embed_chars=4096
```

### Stage 1 — Twitter (lines 29–51)
```
TweetAuthor: id, username, name, followers_count=0
RawTweet: id, text, author:TweetAuthor, created_at, retweet_count=0, reply_count=0,
          like_count=0, quote_count=0, urls[], hashtags[]
CollectorOutput: tweets: list[RawTweet], fetched_at
```

### Stage 2 — Blog (lines 56–66)
```
BlogPost: url, title, content, published?, source_blog
BlogCollectorOutput: posts: list[BlogPost], errors[]
```

### Shared (lines 71–90)
```
CrawledContent: source_url, source_type ("arxiv"|"github"|"blog"|"unknown"), title, content, metadata{}
ContentItem: id, source_type ("twitter"|"blog"), title, content, author, url, published?,
             reference_links[], crawled_references: list[CrawledContent]
```

**ID convention:** tweets use `tweet_{tweet.id}`, blogs use `blog_{md5(url)[:12]}`

### Analyzer Output (lines 95–116)
```
ContentSummary: item_id, summary, reference_links[]
SemanticAnalysis: discussion_points[], trends[], food_for_thought[]
Insight: title, content, source_item_ids[]
AnalyzerOutput: summaries: list[ContentSummary], semantic_analysis: SemanticAnalysis, insights: list[Insight]
```

### Digest & Cross-stage (lines 121–132)
```
DigestOutput: title, full_markdown, chunks[]
WorkNotebook: run_date, blog_errors[], stage_errors{}
```

---

# 5. Pipeline Stages — `src/orchestrator.py`

**Entry:** `run_pipeline(dry_run: bool = False) → None` (line 12)

Stages execute sequentially. Lazy imports inside each stage block.

| Stage | Call | On Failure |
|-------|------|------------|
| 1. Collect tweets | `collect(settings, notebook) → CollectorOutput` | **ABORT** |
| 1b. Rank tweets | `_rank_tweets(tweets, top_n=10) → list[RawTweet]` | — |
| 2. Collect blogs | `collect_blogs(settings, notebook) → BlogCollectorOutput` | **DEGRADE** (empty) |
| 3. Merge + crawl | `_build_content_items(ranked_tweets, blog_output)` then `crawl_references(items, settings, notebook)` | **DEGRADE** (uncrawled) |
| 4. Analyze | `analyze(content_items, settings, notebook) → AnalyzerOutput` | **ABORT** |
| 5. Build digest | `build_digest(analyzer_output, content_items, settings) → DigestOutput` | **ABORT** |
| 6. Deliver | `deliver(digest_output, settings)` (skipped if dry_run) | Log error |

### Key internal functions
- **`_rank_tweets(tweets, top_n=10)`** (line 116): sorts by `retweet_count + reply_count + like_count + quote_count` descending, returns top N
- **`_build_content_items(ranked_tweets, blog_output)`** (line 126): converts RawTweet/BlogPost → ContentItem. Tweet IDs: `tweet_{id}`, URL: `https://x.com/{username}/status/{id}`. Blog IDs: `blog_{md5(url)[:12]}`
- **`_log_blog_errors(errors)`** (line 163): appends timestamped errors to `blog_errors.txt`

---

# 6. Stage 1 — `src/collector.py` (Twitter)

**Entry:** `collect(settings, notebook) → CollectorOutput` (line 25)

### Constants (lines 16–22)
```python
TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
TWEET_FIELDS = "created_at,public_metrics,entities"
USER_FIELDS = "id,username,name,public_metrics"
EXPANSIONS = "author_id"
MAX_QUERY_LENGTH = 512
```

### Functions
- **`_batch_accounts(accounts, max_length=512)`** (line 36): splits accounts into batches fitting Twitter's query char limit. Query format: `(from:a OR from:b) -is:retweet`
- **`_parse_tweet_response(data)`** (line 60): parses Twitter API v2 JSON → list[RawTweet]. Maps `includes.users` by author_id. Extracts `expanded_url` from entities.urls, `tag` from entities.hashtags
- **`_fetch_account_tweets(settings)`** (line 111): iterates batches, paginates via `next_token`, respects `account_fetch_limit`. Uses `sort_order=recency`, `start_time=now-24h`

---

# 7. Stage 2 — `src/blog_collector.py` (Blogs)

**Entry:** `collect_blogs(settings, notebook) → BlogCollectorOutput` (line 17)

### Constants (lines 13–30)
```python
USER_AGENT = "Mozilla/5.0 (AI Morning Brief Bot)"
FEED_PATHS = ["/feed", "/rss", "/atom.xml", "/feed.xml", "/index.xml", "/rss.xml"]
SKIPPED_URL_KEYWORDS = ["about", "contact", "terms", "privacy", ...] # Filters non-article pages
```

### Functions
- **`_fetch_blog_posts(blog_url, cutoff, settings)`** (line 42): tries RSS/Atom feed first, falls back to HTML scraping
- **`_discover_feed(blog_url)`** (line 51): tries FEED_PATHS with HEAD requests checking content-type, then looks for `<link rel="alternate">` in HTML
- **`_parse_feed(feed_url, blog_url, cutoff, settings)`** (line 90): uses feedparser, filters by cutoff date, fetches full page if content < 200 chars
- **`_parse_feed_date(entry)`** (line 126): reads `published_parsed`/`updated_parsed`, uses `calendar.timegm` for correct UTC conversion
- **`_scrape_index(blog_url, cutoff, settings)`** (line 152): fallback scraper. Filters URLs by `SKIPPED_URL_KEYWORDS`. **Strictly requires** verifiable publication date (via `_extract_date_from_html`) to include a post.
- **`_fetch_page_content(url, settings)`** (line 211): tries trafilatura first, then BeautifulSoup. Extracts publication date.
- **`_extract_date_from_html(html)`** (line 273): attempts date extraction via trafilatura metadata, then falls back to common HTML meta tags (`article:published_time`, `og:published_time`, etc.)

---

# 8. Stage 3 — `src/crawler.py` (Link Crawler)

**Entry:** `crawl_references(items, settings, notebook) → list[ContentItem]` (line 17)

Mutates items in-place by appending to `item.crawled_references`. Skips failed URLs with warning.

### URL dispatch — `_classify_url(url)` (line 38)
| Host contains | Type | Handler |
|---|---|---|
| `arxiv.org` | arxiv | `_fetch_arxiv_paper` |
| `github.com` | github | `_fetch_github_repo` |
| anything else | blog | `_fetch_blog` |

### Handlers
- **`_fetch_arxiv_paper(url, settings)`** (line 64): extracts ID via regex `arxiv.org/(abs|pdf)/(\d+\.\d+)`, uses `arxiv` library. Metadata: authors (first 5), published, categories. Content truncated to `content_max_chars_paper`
- **`_fetch_github_repo(url, settings)`** (line 94): regex extracts `owner/repo`, fetches repo metadata + raw README via GitHub REST API. Uses `github_token` if available. Metadata: stars, forks, language, description. Content truncated to `content_max_chars_readme`
- **`_fetch_blog(url, settings)`** (line 137): trafilatura extraction with BeautifulSoup fallback (article/main/body). Content truncated to `content_max_chars_blog`

---

# 9. Stage 4 — `src/analyzer.py` (Three-Phase LLM Analysis)

**Entry:** `analyze(items, settings, notebook) → AnalyzerOutput` (line 64)

Creates `OpenAI` client with `settings.openai_api_key`. Returns empty output if no items.

### Phase 1: Blog Summarization — `_summarize_blog_posts(client, items, settings)` (line 101)
- **Filters:** only `source_type == "blog"` items (tweets skipped entirely)
- **One LLM call per blog post** — sends item as JSON (content[:800], crawled_references[:500] excerpts)
- **Prompt:** `BLOG_SUMMARIZE_SYSTEM_PROMPT` (line 20) — concise summary, key details, reference links
- **LLM params:** model=`settings.openai_model`, temp=0.3, max_tokens=`settings.openai_max_tokens`, response_format=json_object
- **Output:** list[ContentSummary]

### Phase 2: Semantic Analysis — `_semantic_analysis(client, items, summaries, settings)` (line 152)
- **Input:** all items — tweets as full text, blogs as summaries (from Phase 1)
- **Single LLM call** — holistic synthesis, NOT pairwise comparison
- **Prompt:** `SEMANTIC_ANALYSIS_SYSTEM_PROMPT` (line 30) — extract discussion_points, trends, food_for_thought
- **LLM params:** temp=0.4, max_tokens=`settings.openai_max_tokens * 2`
- **Output:** SemanticAnalysis

### Phase 3: Insights — `_derive_insights(client, summaries, semantic, items, settings)` (line 199)
- **Input:** blog_summaries + tweets (full text) + semantic analysis results
- **Character prompt:** `INSIGHTS_SYSTEM_PROMPT` (line 46) — witty, casual, friendly tone. "That friend who reads everything and explains it over coffee."
- **LLM params:** temp=0.5, max_tokens=`settings.openai_max_tokens * 2`
- **Output:** list[Insight] (title + content paragraph + source_item_ids)

### LLM call count per run
`N_blog_posts + 2` (one per blog summary + one semantic + one insights)

---

# 10. Stage 5 — `src/digest.py` (Markdown Assembly)

**Entry:** `build_digest(analyzer_output, content_items, settings) → DigestOutput` (line 9)

### Output markdown structure
```markdown
# AI Morning Brief — {Month Day, Year}

# Tweets
### @{author}
{full tweet text verbatim}
[Link]({tweet_url})

# Blog Posts
### {blog_title}
*by {author}*
{summary from Phase 1}
**References:** {comma-separated links}

# Analysis
## Discussion Points
- {point}
## Trends
- {trend}
## Food for Thought
- {thought}

# Insights
### {insight_title}
{insight_paragraph}
```

### Discord chunking
- **`_split_for_discord(markdown, max_chars)`** (line 89): splits on `\n# ` section boundaries. If a section exceeds max_chars, splits on `\n\n` paragraph breaks
- **`_split_on_delimiter(text, delimiter, max_chars)`** (line 121): generic delimiter-based splitter, truncates oversized parts
- Default max: `settings.discord_max_embed_chars` = 4096

---

# 11. Stage 6 — `src/delivery.py` (Discord Webhook)

**Entry:** `deliver(digest, settings) → None` (line 11)

- Creates `DiscordWebhook` with username "AI Morning Brief"
- First chunk: blue embed (`#1a73e8`) with main title
- Subsequent chunks: gray embeds (`#6c757d`) with "(cont.)" suffix
- Last embed gets footer + timestamp
- Max 10 embeds per webhook message — starts new webhook after 10
- **`_execute_with_retry(webhook, max_retries=3)`** (line 43): handles 429 rate limits (waits retry_after seconds), exponential backoff for other failures

---

# 12. Test Coverage

All tests in `tests/` using pytest + pytest-mock + responses.

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/test_collector.py` | 7 | `_batch_accounts` (single/split/limit/empty), `_parse_tweet_response` (basic/missing user/empty) |
| `tests/test_blog_collector.py` | 6 | `_parse_feed_date`, `_get_feed_entry_content`, `collect_blogs` error handling |
| `tests/test_crawler.py` | 7 | `_classify_url` (arxiv/github/blog), `_extract_arxiv_id`, `crawl_references` (empty/no links) |
| `tests/test_analyzer.py` | 6 | `_summarize_blog_posts` (individual calls, skip tweets), `_semantic_analysis`, `_derive_insights`, `analyze` (empty, end-to-end) |
| `tests/test_digest.py` | 10 | `_split_for_discord`, `_split_on_delimiter`, `build_digest` (structure, verbatim tweets, blog summary, semantic analysis, no level tags) |
| `tests/test_delivery.py` | 4 | `deliver` (embeds, batching at 10), `_execute_with_retry` (success, retry) |
| `tests/test_config.py` | 2 | `load_settings` from env+yaml, optional github_token |

**Test patterns:** Mock OpenAI via `unittest.mock.patch("src.analyzer.OpenAI")` with `side_effect` chains. Mock Discord via `mocker.patch("src.delivery.DiscordWebhook")`. Helper functions `_make_settings()`, `_make_content_items()`, `_mock_openai_response(dict)`.

---

# 13. Tech Stack

Python ≥3.10 | Dependencies in `pyproject.toml`:
- **HTTP:** requests
- **Data:** pydantic, python-dotenv, pyyaml
- **Extraction:** beautifulsoup4, trafilatura, feedparser
- **AI:** openai (gpt-4o-mini)
- **Domain:** arxiv
- **Delivery:** discord-webhook
- **Dev:** pytest, pytest-mock, responses

---

# 14. Folder Structure

```
ai-morning-brief/
├── .github/workflows/
│   └── daily-brief.yml       # GitHub Actions: 6am UTC daily
├── src/
│   ├── models.py             # All Pydantic models (Settings → DigestOutput)
│   ├── config.py             # load_settings(): .env + config.yaml → Settings
│   ├── orchestrator.py       # run_pipeline() + _rank_tweets() + _build_content_items()
│   ├── collector.py          # collect(): Twitter API v2 search/recent
│   ├── blog_collector.py     # collect_blogs(): RSS/Atom + HTML scraping
│   ├── crawler.py            # crawl_references(): arXiv/GitHub/blog dispatch
│   ├── analyzer.py           # analyze(): 3-phase LLM (summarize blogs, semantic, insights)
│   ├── digest.py             # build_digest(): 4-section markdown + Discord chunking
│   └── delivery.py           # deliver(): Discord webhook with embeds + retry
├── config/
│   ├── config.yaml           # 37 Twitter accounts, 22 blog sources, thresholds
│   └── .env.example          # Required env vars template
├── tests/                    # 42 unit tests (pytest)
├── docs/
│   └── architecture.md       # This file
├── run.py                    # CLI: --dry-run, --verbose
└── pyproject.toml            # Dependencies + project metadata
```

---

# 15. Quick Reference — Function Signatures

```python
# orchestrator.py
run_pipeline(dry_run: bool = False) → None
_rank_tweets(tweets: list[RawTweet], top_n: int = 10) → list[RawTweet]
_build_content_items(ranked_tweets, blog_output) → list[ContentItem]

# collector.py
collect(settings: Settings, notebook: WorkNotebook) → CollectorOutput
_batch_accounts(accounts: list[str], max_length: int = 512) → list[list[str]]
_parse_tweet_response(data: dict) → list[RawTweet]
_fetch_account_tweets(settings: Settings) → list[RawTweet]

# blog_collector.py
collect_blogs(settings: Settings, notebook: WorkNotebook) → BlogCollectorOutput
_discover_feed(blog_url: str) → str | None
_parse_feed(feed_url, blog_url, cutoff, settings) → list[BlogPost]
_scrape_index(blog_url, cutoff, settings) → list[BlogPost]

# crawler.py
crawl_references(items: list[ContentItem], settings, notebook) → list[ContentItem]
_classify_url(url: str) → str  # "arxiv" | "github" | "blog"
_fetch_arxiv_paper(url, settings) → CrawledContent | None
_fetch_github_repo(url, settings) → CrawledContent | None
_fetch_blog(url, settings) → CrawledContent | None

# analyzer.py
analyze(items: list[ContentItem], settings, notebook) → AnalyzerOutput
_summarize_blog_posts(client, items, settings) → list[ContentSummary]
_semantic_analysis(client, items, summaries, settings) → SemanticAnalysis
_derive_insights(client, summaries, semantic, items, settings) → list[Insight]

# digest.py
build_digest(analyzer_output, content_items: list[ContentItem], settings) → DigestOutput
_split_for_discord(markdown: str, max_chars: int) → list[str]

# delivery.py
deliver(digest: DigestOutput, settings: Settings) → None
_execute_with_retry(webhook, max_retries: int = 3) → None

# config.py
load_settings() → Settings
```

---

End of Architecture
