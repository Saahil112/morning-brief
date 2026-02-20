"""
Digest writer -- renders classified, section-bucketed stories into a
clean, structured HTML email for the Morning Brief.

Sections
--------
1. Headline         (suppressed if empty)
2. Global News
3. AI & Technology
4. Macro & Markets
5. Merger News      (special situations focus)
6. Watchlist        (short forward-looking bullets)

Style rules
-----------
- Crisp analytical tone
- No fluff
- No em dashes
- Clear why-it-matters logic
- Max 300 words per story (configurable)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import openai

from app.config import BRIEF_TITLE, OPENAI_API_KEY, OPENAI_MODEL, STORY_MAX_WORDS
from app.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── LLM summariser prompt ──────────────────────────────────────────────────

_SUMMARY_SYSTEM = """\
You are a senior intelligence analyst writing a morning brief for a
decision-maker. Rules:

- Crisp, analytical tone. No filler, no fluff.
- NEVER use em dashes (--) or the unicode em dash character.
- Each summary must be {max_words} words or fewer.
- Start with the key fact, then explain why it matters.
- Use short sentences. Structured logic.

You will receive a JSON list of stories grouped by section.
Return a JSON list of objects:
[
  {{"title": "<exact original title>", "summary": "<your summary>"}},
  ...
]
Return ONLY valid JSON, no markdown fences.
""".format(max_words=STORY_MAX_WORDS)

_WATCHLIST_SYSTEM = """\
You are a senior analyst writing the Watchlist section of a morning brief.
Given headlines, produce short forward-looking bullets (one per story).
Each bullet must start with one of:
  "Watch for...", "Risk to monitor...", "Potential second-order impact..."

Keep each bullet under 40 words. No em dashes. No filler.
Return a JSON list: [{{"title": "...", "bullet": "..."}}]
Return ONLY valid JSON, no markdown fences.
"""


def _llm_summarize(stories: list[dict[str, Any]]) -> dict[str, str]:
    """Return {{title: summary}} for non-watchlist stories."""
    if not client or not stories:
        return {}

    payload = [
        {"title": s["title"], "source": s["source"], "summary": s.get("summary", "")}
        for s in stories
    ]

    with tracer.start_as_current_span("llm_summarize") as span:
        span.set_attribute("llm.model", OPENAI_MODEL)
        span.set_attribute("llm.stories_count", len(payload))
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                temperature=0.3,
            )
            usage = resp.usage
            if usage:
                span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
                span.set_attribute("llm.completion_tokens", usage.completion_tokens)
                span.set_attribute("llm.total_tokens", usage.total_tokens)
            raw = resp.choices[0].message.content or "[]"
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            results = json.loads(raw)
            return {r["title"]: r["summary"] for r in results if "title" in r}
        except Exception:
            span.set_attribute("llm.error", True)
            logger.exception("LLM summarisation failed")
            return {}


def _llm_watchlist(stories: list[dict[str, Any]]) -> dict[str, str]:
    """Return {{title: bullet}} for watchlist stories."""
    if not client or not stories:
        return {}

    payload = [
        {"title": s["title"], "source": s["source"], "summary": s.get("summary", "")}
        for s in stories
    ]

    with tracer.start_as_current_span("llm_watchlist") as span:
        span.set_attribute("llm.model", OPENAI_MODEL)
        span.set_attribute("llm.stories_count", len(payload))
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": _WATCHLIST_SYSTEM},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                temperature=0.3,
            )
            usage = resp.usage
            if usage:
                span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
                span.set_attribute("llm.completion_tokens", usage.completion_tokens)
                span.set_attribute("llm.total_tokens", usage.total_tokens)
            raw = resp.choices[0].message.content or "[]"
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            results = json.loads(raw)
            return {r["title"]: r["bullet"] for r in results if "title" in r}
        except Exception:
            span.set_attribute("llm.error", True)
            logger.exception("LLM watchlist generation failed")
            return {}


# ── HTML helpers ────────────────────────────────────────────────────────────

_SECTION_META: dict[str, dict[str, str]] = {
    "headline": {
        "label": "Headline",
        "icon": "&#9889;",  # lightning bolt
        "color": "#c62828",
    },
    "global_news": {
        "label": "Global News",
        "icon": "&#127758;",  # globe
        "color": "#1565c0",
    },
    "ai_tech": {
        "label": "AI & Technology",
        "icon": "&#129302;",  # robot
        "color": "#6a1b9a",
    },
    "macro_markets": {
        "label": "Macro & Markets",
        "icon": "&#128200;",  # chart
        "color": "#2e7d32",
    },
    "merger_news": {
        "label": "Merger News",
        "icon": "&#128176;",  # money bag
        "color": "#e65100",
    },
    "watchlist": {
        "label": "Watchlist",
        "icon": "&#128065;",  # eye
        "color": "#37474f",
    },
}


def _story_row(idx: int, story: dict[str, Any], summary: str) -> str:
    title = story["title"]
    link = story.get("link", "#")
    source = story.get("source", "")
    specials = story.get("special_situations", [])
    special_tag = ""
    if specials:
        tags = ", ".join(specials)
        special_tag = (
            f'<span style="display:inline-block; margin-left:6px; '
            f'font-size:11px; background:#fff3e0; color:#e65100; '
            f'padding:1px 6px; border-radius:3px;">{tags}</span>'
        )
    return f"""
    <tr>
      <td style="padding:10px 14px; border-bottom:1px solid #eee;">
        <strong style="font-size:15px;">
          <a href="{link}" style="color:#1a73e8; text-decoration:none;">
            {idx}. {title}
          </a>
        </strong>{special_tag}
        <br/>
        <span style="font-size:12px; color:#999;">{source}</span>
        <p style="margin:6px 0 2px; font-size:14px; color:#222; line-height:1.5;">
          {summary}
        </p>
      </td>
    </tr>"""


def _watchlist_bullet(story: dict[str, Any], bullet: str) -> str:
    link = story.get("link", "#")
    return (
        f'<li style="margin-bottom:6px; font-size:14px; color:#222;">'
        f'<a href="{link}" style="color:#1a73e8; text-decoration:none;">'
        f'{story["title"]}</a><br/>'
        f'<span style="color:#555;">{bullet}</span></li>'
    )


def _section_header(section_key: str) -> str:
    meta = _SECTION_META[section_key]
    return (
        f'<h3 style="color:{meta["color"]}; margin:28px 0 10px; '
        f'border-bottom:1px solid {meta["color"]}; padding-bottom:4px;">'
        f'{meta["icon"]} {meta["label"]}</h3>'
    )


# ── Public API ──────────────────────────────────────────────────────────────

def build_digest(
    buckets: dict[str, list[dict[str, Any]]],
) -> tuple[str, str]:
    """
    Build the HTML digest email from section buckets.

    Parameters
    ----------
    buckets : dict mapping section key to list of story dicts.

    Returns
    -------
    (subject, html_body)
    """
    with tracer.start_as_current_span("build_digest") as span:
        today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
        subject = f"{BRIEF_TITLE} // {today}"

        # Collect all non-watchlist stories for a single summarise call
        non_wl_stories = [
            s
            for key in ("headline", "global_news", "ai_tech", "macro_markets", "merger_news")
            for s in buckets.get(key, [])
        ]
        summaries = _llm_summarize(non_wl_stories)
        watchlist_bullets = _llm_watchlist(buckets.get("watchlist", []))

        total_stories = sum(len(v) for v in buckets.values())
        span.set_attribute("digest.total_stories", total_stories)

        # ── Assemble HTML ───────────────────────────────────────────────
        sections_html = ""
        story_counter = 0

        render_order = [
            "headline",
            "global_news",
            "ai_tech",
            "macro_markets",
            "merger_news",
            "watchlist",
        ]

        for sec in render_order:
            stories = buckets.get(sec, [])
            if not stories:
                continue  # suppress empty sections (especially headline)

            sections_html += _section_header(sec)

            if sec == "watchlist":
                bullets_html = ""
                for s in stories:
                    bullet = watchlist_bullets.get(s["title"], s.get("reason", ""))
                    bullets_html += _watchlist_bullet(s, bullet)
                sections_html += f'<ul style="padding-left:20px;">{bullets_html}</ul>'
            else:
                rows_html = ""
                for s in stories:
                    story_counter += 1
                    summary = summaries.get(s["title"], s.get("summary", ""))
                    rows_html += _story_row(story_counter, s, summary)
                sections_html += (
                    f'<table style="width:100%; border-collapse:collapse;">'
                    f"{rows_html}</table>"
                )

        html = f"""\
<html>
<body style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width:700px; margin:auto; padding:24px; background:#fafafa;">
  <div style="background:#fff; border-radius:8px; padding:24px; border:1px solid #e0e0e0;">
    <h2 style="margin:0 0 4px; color:#111;">{BRIEF_TITLE}</h2>
    <p style="color:#888; font-size:13px; margin:0 0 20px;">{today} // {total_stories} stories</p>
    {sections_html}
    <p style="font-size:11px; color:#bbb; margin-top:36px; text-align:center;">
      Generated automatically // RSS + LLM pipeline // 9:30 AM daily
    </p>
  </div>
</body>
</html>"""

        return subject, html
