from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# --- Configuration ---

class Settings(BaseModel):
    twitter_bearer_token: str
    openai_api_key: str
    discord_webhook_url: str
    github_token: str | None = None

    influential_accounts: list[str] = Field(default_factory=list)
    account_fetch_limit: int = 100
    blog_sources: list[str] = Field(default_factory=list)
    content_max_chars_blog: int = 3000
    content_max_chars_paper: int = 2000
    content_max_chars_readme: int = 2000
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 1024
    analyzer_batch_size: int = 10
    discord_max_embed_chars: int = 4096


# --- Stage 1: Twitter Collector ---

class TweetAuthor(BaseModel):
    id: str
    username: str
    name: str
    followers_count: int = 0


class RawTweet(BaseModel):
    id: str
    text: str
    author: TweetAuthor
    created_at: datetime
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    urls: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)


class CollectorOutput(BaseModel):
    tweets: list[RawTweet]
    fetched_at: datetime


# --- Stage 2: Blog Collector ---

class BlogPost(BaseModel):
    url: str
    title: str
    content: str
    published: datetime | None = None
    source_blog: str


class BlogCollectorOutput(BaseModel):
    posts: list[BlogPost]
    errors: list[str] = Field(default_factory=list)


# --- Crawled content (shared) ---

class CrawledContent(BaseModel):
    source_url: str
    source_type: str  # "arxiv" | "github" | "blog" | "unknown"
    title: str
    content: str
    metadata: dict = Field(default_factory=dict)


# --- Unified content item ---

class ContentItem(BaseModel):
    id: str
    source_type: str  # "twitter" | "blog"
    title: str
    content: str
    author: str
    url: str
    published: datetime | None = None
    reference_links: list[str] = Field(default_factory=list)
    crawled_references: list[CrawledContent] = Field(default_factory=list)


# --- Analyzer output ---

class ContentSummary(BaseModel):
    item_id: str
    summary: str
    reference_links: list[str] = Field(default_factory=list)


class SemanticAnalysis(BaseModel):
    discussion_points: list[str] = Field(default_factory=list)
    trends: list[str] = Field(default_factory=list)
    food_for_thought: list[str] = Field(default_factory=list)


class Insight(BaseModel):
    title: str
    content: str
    source_item_ids: list[str] = Field(default_factory=list)


class AnalyzerOutput(BaseModel):
    summaries: list[ContentSummary]
    semantic_analysis: SemanticAnalysis
    insights: list[Insight]


# --- Digest ---

class DigestOutput(BaseModel):
    title: str
    full_markdown: str
    chunks: list[str]


# --- Cross-stage context ---

class WorkNotebook(BaseModel):
    run_date: datetime
    blog_errors: list[str] = Field(default_factory=list)
    stage_errors: dict[str, str] = Field(default_factory=dict)
