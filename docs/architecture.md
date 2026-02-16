# AI Signal Agent — v1 Pipeline Architecture

## Overview
This system detects important AI developments by monitoring high-signal social posts, extracting referenced sources, analyzing them, and generating concise intelligence summaries.

**Design goal:** minimal, reliable, extensible

---

# 1. System Flow

Collector → Ranker → Reference Extractor → Source Crawler → Analyzer → Summarizer → Digest → Delivery

Runs once per day via scheduler.

---

# 2. Components

## 2.1 Collector — Trending Post Fetcher
Fetches posts using a two-phase approach for dynamic content discovery.

### Data Flow
```
influential_accounts (26)          seed_keywords (generic)
         |                                  |
         v                                  |
  Batch into groups (~10 per batch)         |
  (respects 512 char Twitter query limit)   |
         |                                  |
         v                                  |
  Fetch tweets from accounts                |
         |                                  |
         v                                  |
  Extract hashtags/keywords ----------------+
         |                                  |
         +----------------------------------+
                         |
                         v
              Combined keyword list
                         |
                         v
              Fetch general tweets
                         |
         +---------------+---------------+
         |                               |
   Account tweets                  General tweets
         |                               |
         +---------------+---------------+
                         |
                         v
              Merge & deduplicate
                         |
                         v
              CollectorOutput
```

### Phase 1: Account-Based Fetching
Fetch tweets from 26 influential AI accounts:
- karpathy, OpenAI, AnthropicAI, GoogleDeepMind, huggingface
- sama, ylecun, JeffDean, geoffreyhinton, AndrewYNg, drfeifei
- lexfridman, ycombinator, ilyasut, NeelNanda5, jovialjoy
- And more curated accounts...

Accounts are batched to fit Twitter API's 512 character query limit.

### Phase 2: Keyword Extraction & General Search
1. Extract trending hashtags from account tweets
2. Combine with generic seed keywords (AI, machine learning, deep learning, etc.)
3. Fetch general tweets matching combined keywords
4. Merge and deduplicate all tweets

**Input**
None

**Output**
```json
[
  {
    "id": "...",
    "author": "...",
    "text": "...",
    "likes": 1200,
    "shares": 340,
    "replies": 80,
    "urls": [...],
    "hashtags": [...]
  }
]
```

**Additional Output**
- `discovered_keywords`: hashtags from all tweets
- `account_keywords`: hashtags specifically from influential accounts
- `top_authors`: most followed authors from fetched tweets


⸻

2.2 Ranker — Importance Scoring

Ranks posts by signal strength.

Formula (v1)

score = (likes + shares*2 + replies*1.5) / follower_count

Keeps only top N (example: 20)

⸻

2.3 Reference Extractor

Pulls structured references from post text.

Extract:
	•	URLs
	•	repo links
	•	paper titles
	•	model names

Output:

{
  "post_id": "...",
  "links": [...],
  "entities": [...]
}


⸻

2.4 Source Crawler

Visits each reference link.

Handler logic:

Type	Action
Paper	fetch metadata
Repository	fetch README + stars
Blog	extract article text
Thread	expand replies


⸻

2.5 Analyzer — Content Classifier

Filters only meaningful signals.

Categories:
	•	research
	•	release
	•	benchmark
	•	opinion
	•	meme

Pass condition

category ∈ {research, release, benchmark}


⸻

2.6 Summarizer

Combines post + source content.

Output format

TITLE:
SUMMARY:
WHY IT MATTERS:
KEY METRICS:
SOURCE LINKS:


⸻

2.7 Digest Generator

Creates daily report.

Example

Top AI Signals — Feb 15

1. New open-source reasoning model surpasses baseline benchmarks
Impact: improves small model performance

2. Robotics dataset released
Impact: enables cheaper training


⸻

2.8 Delivery Layer

Send digest to:
	•	messaging bot (discord)

⸻

3. Scheduler

Run daily using cron:

0 7 * * *

Recommended runner: automated cloud workflow runner.

⸻

4. Folder Structure

ai-signal-agent/
│
├── collectors/
├── rankers/
├── extractors/
├── crawlers/
├── analyzers/
├── summarizers/
├── output/
└── workflow.yml


⸻

5. Minimal Tech Stack

Language: Python

Libraries:
	•	requests
	•	beautifulsoup4
	•	pydantic

Optional:
	•	trafilatura (better article extraction)

⸻

6. Environment Variables

API_KEY_SOCIAL=
API_KEY_LLM=
EMAIL_USER=
EMAIL_PASS=
1

⸻

7. Failure Handling

Step	Behavior
Fetch fails	skip run
Link fails	skip link
LLM fails	fallback summary
Delivery fails	retry


⸻

8. v1 Constraints (Intentional)

To keep system simple:
	•	no real-time streaming
	•	no database
	•	no clustering
	•	no UI

Everything runs stateless daily.

⸻

9. v2 Upgrade Ideas

Future improvements:
	•	story clustering
	•	novelty detection
	•	credibility scoring
	•	trend graphs
	•	memory database
	•	real-time alerts

⸻

10. Philosophy

Design principle

Signal first, depth second

Start from high-impact posts → expand outward.

This prevents noise overload and keeps system efficient.

⸻

End of Architecture