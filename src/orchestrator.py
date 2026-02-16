import logging
from datetime import datetime, timezone

from src.config import load_settings
from src.models import CrawlerOutput, TweetWithContent, WorkNotebook

logger = logging.getLogger("ai_morning_brief")


def run_pipeline(dry_run: bool = False) -> None:
    logger.info("Starting AI Morning Brief pipeline")

    settings = load_settings()
    notebook = WorkNotebook(
        run_date=datetime.now(timezone.utc),
        seed_keywords=settings.seed_keywords,
    )

    # Stage 1: Collect
    try:
        logger.info("Stage 1/7: Collecting tweets")
        from src.collector import collect

        collector_output = collect(settings, notebook)
        logger.info(f"Collected {len(collector_output.tweets)} tweets")
    except Exception as e:
        logger.error(f"Collector failed: {e}")
        return

    # Stage 2: Rank
    try:
        logger.info("Stage 2/7: Ranking tweets")
        from src.ranker import rank

        ranker_output = rank(collector_output, settings, notebook)
        logger.info(
            f"Top tweet score: "
            f"{ranker_output.ranked_tweets[0].engagement_score:.1f}"
        )
    except Exception as e:
        logger.error(f"Ranker failed: {e}")
        return

    # Stage 3: Crawl
    try:
        logger.info("Stage 3/7: Crawling references")
        from src.crawler import crawl

        crawler_output = crawl(ranker_output, settings, notebook)
        logger.info(f"Crawled {len(crawler_output.all_crawled)} items")
    except Exception as e:
        logger.error(f"Crawler failed: {e}")
        notebook.stage_errors["crawler"] = str(e)
        # Continue with empty crawl data
        crawler_output = CrawlerOutput(
            enriched_tweets=[
                TweetWithContent(scored_tweet=st, crawled_contents=[])
                for st in ranker_output.ranked_tweets
            ],
            all_crawled=[],
        )

    # Stage 4: Analyze
    try:
        logger.info("Stage 4/7: Analyzing content")
        from src.analyzer import analyze

        analyzer_output = analyze(crawler_output, settings, notebook)
        logger.info(f"Analyzed {len(analyzer_output.items)} items")
    except Exception as e:
        logger.error(f"Analyzer failed: {e}")
        return

    # Stage 5: Summarize
    try:
        logger.info("Stage 5/7: Generating summary")
        from src.summarizer import summarize

        summarizer_output = summarize(analyzer_output, settings, notebook)
    except Exception as e:
        logger.error(f"Summarizer failed: {e}")
        return

    # Stage 6: Build digest
    try:
        logger.info("Stage 6/7: Building digest")
        from src.digest import build_digest

        digest_output = build_digest(summarizer_output, settings)
    except Exception as e:
        logger.error(f"Digest failed: {e}")
        return

    # Stage 7: Deliver
    if dry_run:
        logger.info("Dry run — skipping delivery")
        print(digest_output.full_markdown)
        return

    try:
        logger.info("Stage 7/7: Delivering to Discord")
        from src.delivery import deliver

        deliver(digest_output, settings)
        logger.info("Pipeline complete")
    except Exception as e:
        logger.error(f"Delivery failed: {e}")
        notebook.stage_errors["delivery"] = str(e)
