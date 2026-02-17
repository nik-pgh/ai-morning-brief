# AI Morning Brief — v2 Pipeline Architecture

## Overview
This system detects important AI developments by monitoring high-signal Twitter accounts and curated blog sources, extracting referenced content, analyzing relationships between items, and generating intelligence briefs with actionable insights.

**Design goal:** minimal, reliable, extensible

---

# 1. System Flow

```
TwitterCollector → BlogCollector → LinkCrawler → Analyzer → Digest → Delivery
```

Runs once per day via scheduler.

---

# 2. Components

## 2.1 TwitterCollector — Account Tweet Fetcher
Fetches recent posts (last 24h) from listed influential accounts.

### Data Flow
```
influential_accounts (37)
         |
         v
  Batch into groups (~10 per batch)
  (respects 512 char Twitter query limit)
         |
         v
  Fetch tweets from accounts
         |
         v
  CollectorOutput (tweets + fetched_at)
```

### Account List
37 curated AI accounts including:
- karpathy, OpenAI, AnthropicAI, GoogleDeepMind, huggingface
- sama, ylecun, JeffDean, geoffreyhinton, AndrewYNg, drfeifei
- lexfridman, ycombinator, ilyasut, NeelNanda5, jovialjoy
- naval, demishassabis, EpochAIResearch, and more...

Accounts are batched to fit Twitter API's 512 character query limit.

**Input:** None

**Output:**
```json
{
  "tweets": [
    {
      "id": "...",
      "text": "...",
      "author": {"username": "...", "followers_count": 1000},
      "created_at": "...",
      "urls": ["..."],
      "hashtags": ["..."],
      "like_count": 1200,
      "retweet_count": 340,
      "reply_count": 80
    }
  ],
  "fetched_at": "..."
}
```

---

## 2.2 BlogCollector — RSS/HTML Blog Fetcher
Checks 22 curated blog sources for new posts in the last 24h.

### Strategy
1. **RSS/Atom discovery** (preferred): Try common feed paths (`/feed`, `/rss`, `/atom.xml`, etc.) and HTML `<link rel="alternate">` tags
2. **HTML scraping fallback**: Scrape index page for recent post links, fetch content via trafilatura/bs4

### Blog Sources
- newsletter.ruder.io, karpathy.github.io, lilianweng.github.io
- eugeneyan.com, huyenchip.com, simonwillison.net
- openai.com/news, deepmind.google/blog, anthropic.com/engineering
- thezvi.substack.com, interconnects.ai, oneusefulthing.org
- lesswrong.com, gwern.net, lucumr.pocoo.org, and more...

**Output:**
```json
{
  "posts": [
    {
      "url": "...",
      "title": "...",
      "content": "...",
      "published": "...",
      "source_blog": "..."
    }
  ],
  "errors": ["..."]
}
```

Blog fetch failures are logged to `blog_errors.txt` for user review.

---

## 2.3 Content Merging
Tweets and blog posts are merged into unified `ContentItem` objects in the orchestrator:

```
Tweets → ContentItem (source_type="twitter", reference_links=tweet.urls)
Blog posts → ContentItem (source_type="blog")
```

Each ContentItem has: `id`, `source_type`, `title`, `content`, `author`, `url`, `reference_links`, `crawled_references`.

---

## 2.4 LinkCrawler — Reference Link Follower
Follows reference links from each content item, 1 level deep.

### URL Dispatch

| Type       | Action                              |
|------------|-------------------------------------|
| arXiv      | Fetch paper metadata via arxiv lib  |
| GitHub     | Fetch repo metadata + README        |
| Blog/Other | Extract article text via trafilatura |

Individual link failures are logged and skipped.

---

## 2.5 Analyzer — Three-Phase LLM Analysis
Processes all content items through three sequential OpenAI calls.

### Phase 1: Summarize
- Batch content items (10 per call)
- Produce concise summary per item with all reference links
- Output: `ContentSummary` list

### Phase 2: Relationships
- Single call analyzing all summaries together
- Find inter-content relationships with strength ratings (strong/moderate/weak)
- Output: `RelationshipAnalysis` list

### Phase 3: Insights
- Single call combining summaries + relationships
- Derive actionable insights at three levels:
  - **Technical**: engineering/research implications
  - **Business**: market/strategy implications
  - **Product**: product development implications
- Each insight is a paragraph combining information from multiple sources
- Output: `Insight` list

---

## 2.6 Digest Generator
Assembles three markdown sections:

```markdown
# AI Morning Brief — {date}

# Summary
### {item_id}
{summary}
**References:** {links}

# Analysis
- [{strength}] **{item_ids}**: {relationship}

# Insights
### [{LEVEL}] {title}
{paragraph combining multiple sources}
```

Splits into Discord-safe chunks (≤4096 chars per embed).

---

## 2.7 Delivery Layer
Send digest to Discord via webhook with embeds and retry logic.

- First chunk: blue embed with main title
- Continuation chunks: gray embeds with "(cont.)" suffix
- Max 10 embeds per webhook message
- Retry with exponential backoff (max 3 retries)

---

# 3. Scheduler

Run daily using cron:

```
0 7 * * *
```

---

# 4. Folder Structure

```
ai-morning-brief/
├── src/
│   ├── models.py            # All Pydantic data models
│   ├── config.py            # Settings loader (.env + config.yaml)
│   ├── orchestrator.py      # 6-stage pipeline coordinator
│   ├── collector.py         # Stage 1: Twitter account fetcher
│   ├── blog_collector.py    # Stage 2: Blog RSS/HTML fetcher
│   ├── crawler.py           # Stage 3: Reference link follower
│   ├── analyzer.py          # Stage 4: 3-phase LLM analysis
│   ├── digest.py            # Stage 5: Markdown assembly
│   └── delivery.py          # Stage 6: Discord webhook
├── config/
│   ├── config.yaml          # Accounts, blog sources, thresholds
│   └── .env.example         # Environment variable template
├── tests/                   # Unit tests (pytest)
├── docs/
│   └── architecture.md      # This file
├── run.py                   # CLI entry point
└── pyproject.toml           # Dependencies
```

---

# 5. Tech Stack

Language: Python ≥3.10

Dependencies:
- requests, pydantic, python-dotenv, pyyaml
- beautifulsoup4, trafilatura (article extraction)
- feedparser (RSS/Atom feed parsing)
- openai (LLM analysis)
- arxiv (paper metadata)
- discord-webhook (delivery)

---

# 6. Environment Variables

```
TWITTER_BEARER_TOKEN=    # Required: Twitter API v2
OPENAI_API_KEY=          # Required: LLM analysis
DISCORD_WEBHOOK_URL=     # Required: Digest delivery
GITHUB_TOKEN=            # Optional: Higher GitHub API rate limits
```

---

# 7. Failure Handling

| Stage            | Behavior                                    |
|------------------|---------------------------------------------|
| Twitter fetch    | Abort run                                   |
| Blog fetch       | Degrade gracefully (continue without blogs) |
| Link crawl       | Degrade gracefully (skip failed links)      |
| LLM analysis     | Abort run                                   |
| Digest build     | Abort run                                   |
| Delivery         | Retry 3x with exponential backoff           |

---

# 8. Design Constraints (Intentional)

To keep system simple:
- No real-time streaming
- No database
- No clustering
- No UI

Everything runs stateless daily.

---

# 9. Philosophy

Design principle:

> Signal first, depth second

Start from high-signal accounts and blogs → follow reference links outward → analyze relationships → derive insights.

This prevents noise overload and keeps the system efficient.

---

End of Architecture
