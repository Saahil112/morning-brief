"""
Configuration for the Morning Brief.
All tunables loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.2")

# ── Gmail OAuth ─────────────────────────────────────────────────────────────
GMAIL_CREDENTIALS_JSON: str = os.getenv("GMAIL_CREDENTIALS_JSON", "credentials.json")
GMAIL_TOKEN_JSON: str = os.getenv("GMAIL_TOKEN_JSON", "token.json")
GMAIL_SENDER: str = os.getenv("GMAIL_SENDER", "")
GMAIL_RECIPIENT: str = os.getenv("GMAIL_RECIPIENT", "")
GMAIL_CLIENT_ID: str = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET: str = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN: str = os.getenv("GMAIL_REFRESH_TOKEN", "")

# ── RSS Feeds ───────────────────────────────────────────────────────────────
# Comma-separated list of RSS / Atom feed URLs.
# Grouped by category so the classifier has feed-level hints.

_DEFAULT_GLOBAL_FEEDS: list[str] = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

_DEFAULT_AI_TECH_FEEDS: list[str] = [
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
]

_DEFAULT_MACRO_MARKET_FEEDS: list[str] = [
    "https://www.ft.com/?format=rss",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bloomberg.com/markets/news.rss",
]

_DEFAULT_MERGER_FEEDS: list[str] = [
    "https://feeds.reuters.com/reuters/mergersNews",
    "https://www.ft.com/mergers-acquisitions?format=rss",
]


def _parse_feeds(env_key: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(env_key, ",".join(defaults))
    return [u.strip() for u in raw.split(",") if u.strip()]


FEEDS_GLOBAL: list[str] = _parse_feeds("RSS_FEEDS_GLOBAL", _DEFAULT_GLOBAL_FEEDS)
FEEDS_AI_TECH: list[str] = _parse_feeds("RSS_FEEDS_AI_TECH", _DEFAULT_AI_TECH_FEEDS)
FEEDS_MACRO: list[str] = _parse_feeds("RSS_FEEDS_MACRO", _DEFAULT_MACRO_MARKET_FEEDS)
FEEDS_MERGER: list[str] = _parse_feeds("RSS_FEEDS_MERGER", _DEFAULT_MERGER_FEEDS)

# Flat list for the fetcher (backward compat)
DEFAULT_FEEDS: list[str] = FEEDS_GLOBAL + FEEDS_AI_TECH + FEEDS_MACRO + FEEDS_MERGER

# ── Classifier thresholds ──────────────────────────────────────────────────
# Macro-threshold trigger: minimum number of feeds that must carry a story
# for it to be auto-included even without LLM confirmation.
MACRO_HEADLINE_THRESHOLD: int = int(os.getenv("MACRO_HEADLINE_THRESHOLD", "3"))

# ── Special Situations / Merger News keywords (case-insensitive) ───────────
SPECIAL_SITUATIONS_KEYWORDS: list[str] = [
    kw.strip()
    for kw in os.getenv(
        "SPECIAL_SITUATIONS_KEYWORDS",
        "takeover,demerger,split,reverse split,hiving off,"
        "activist investor,merger,acquisition,IPO,SPAC,"
        "spin-off,spinoff,carve-out,carveout,restructuring",
    ).split(",")
    if kw.strip()
]

# ── Headline trigger criteria (Section 1) ──────────────────────────────────
# The LLM uses these as its filter; they are also in the prompt.
HEADLINE_CRITERIA: list[str] = [
    "Market-moving macro shock",
    "Major geopolitical escalation",
    "Large unexpected policy move",
    "$50B+ M&A",
    "Systemic risk event",
]

# ── Section story limits ───────────────────────────────────────────────────
SEC_HEADLINE_MAX: int = int(os.getenv("SEC_HEADLINE_MAX", "2"))
SEC_GLOBAL_MAX: int = int(os.getenv("SEC_GLOBAL_MAX", "4"))
SEC_AI_TECH_MAX: int = int(os.getenv("SEC_AI_TECH_MAX", "3"))
SEC_MACRO_MAX: int = int(os.getenv("SEC_MACRO_MAX", "3"))
SEC_MERGER_MAX: int = int(os.getenv("SEC_MERGER_MAX", "3"))
SEC_WATCHLIST_MAX: int = int(os.getenv("SEC_WATCHLIST_MAX", "5"))

# ── Per-story word cap ─────────────────────────────────────────────────────
STORY_MAX_WORDS: int = int(os.getenv("STORY_MAX_WORDS", "300"))

# ── Digest ──────────────────────────────────────────────────────────────────
BRIEF_TITLE: str = os.getenv("BRIEF_TITLE", "Morning Brief")
