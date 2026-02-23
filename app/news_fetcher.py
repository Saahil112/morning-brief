"""
RSS / Atom feed aggregator.

Fetches headlines from every configured feed, deduplicates by title
similarity, and returns a flat list of story dicts.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser

from app.config import DEFAULT_FEEDS
from app.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _fingerprint(title: str) -> str:
    """Lowercase, stripped MD5 — used for cheap dedup."""
    return hashlib.md5(title.strip().lower().encode()).hexdigest()


def _is_recent(entry: Any, cutoff: datetime) -> bool:
    """Return True if the entry was published/updated within the cutoff window."""
    import calendar
    import time

    for key in ("published_parsed", "updated_parsed"):
        tp = entry.get(key)
        if tp:
            try:
                entry_dt = datetime.fromtimestamp(calendar.timegm(tp), tz=timezone.utc)
                return entry_dt >= cutoff
            except (ValueError, OverflowError, OSError):
                continue
    # If no parseable date is available, exclude the entry
    return False


def fetch_all(feeds: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Fetch and merge entries from all RSS feeds.

    Returns a list of dicts, each containing:
        title, link, source, published, fingerprint
    """
    feeds = feeds or DEFAULT_FEEDS
    seen: set[str] = set()
    stories: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    with tracer.start_as_current_span("fetch_all") as span:
        span.set_attribute("feeds.count", len(feeds))

        for url in feeds:
            with tracer.start_as_current_span("fetch_feed") as feed_span:
                feed_span.set_attribute("feed.url", url)
                try:
                    parsed = feedparser.parse(url)
                    source = parsed.feed.get("title", url)
                    feed_span.set_attribute("feed.source", source)
                    feed_span.set_attribute("feed.entries", len(parsed.entries))
                    for entry in parsed.entries:
                        if not _is_recent(entry, cutoff):
                            continue
                        title = entry.get("title", "").strip()
                        if not title:
                            continue
                        fp = _fingerprint(title)
                        if fp in seen:
                            for s in stories:
                                if s["fingerprint"] == fp:
                                    s["feed_count"] += 1
                                    break
                            continue
                        seen.add(fp)

                        published = entry.get("published", entry.get("updated", ""))
                        stories.append(
                            {
                                "title": title,
                                "link": entry.get("link", ""),
                                "source": source,
                                "published": published,
                                "fingerprint": fp,
                                "summary": entry.get("summary", ""),
                                "feed_count": 1,
                            }
                        )
                except Exception:
                    feed_span.set_attribute("feed.error", True)
                    logger.exception("Failed to fetch feed: %s", url)

        span.set_attribute("feeds.stories_total", len(stories))

    logger.info("Fetched %d unique stories from %d feeds", len(stories), len(feeds))
    return stories
