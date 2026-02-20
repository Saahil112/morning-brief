"""
Section-aware classifier with dual headline trigger logic.

Assigns each story to one of six sections:

1. Headline       (only truly major events)
2. Global News    (geopolitics, treaties, breaking world events)
3. AI & Technology
4. Macro & Markets
5. Merger News    (special situations: demergers, spin-offs, etc.)
6. Watchlist      (forward-looking short bullets)

Two independent paths can surface a story:

  LLM relevance   -- OpenAI classifies + assigns section
  Macro threshold  -- if >= N feeds carry the same headline it is
                      auto-included regardless of LLM score

A keyword filter also flags merger / special-situation stories.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from app.tracing import get_tracer
from app.config import (
    HEADLINE_CRITERIA,
    MACRO_HEADLINE_THRESHOLD,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    SEC_AI_TECH_MAX,
    SEC_GLOBAL_MAX,
    SEC_HEADLINE_MAX,
    SEC_MACRO_MAX,
    SEC_MERGER_MAX,
    SEC_WATCHLIST_MAX,
    SPECIAL_SITUATIONS_KEYWORDS,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Valid section keys (order matters for digest rendering)
SECTIONS = [
    "headline",
    "global_news",
    "ai_tech",
    "macro_markets",
    "merger_news",
    "watchlist",
]

SECTION_LIMITS: dict[str, int] = {
    "headline": SEC_HEADLINE_MAX,
    "global_news": SEC_GLOBAL_MAX,
    "ai_tech": SEC_AI_TECH_MAX,
    "macro_markets": SEC_MACRO_MAX,
    "merger_news": SEC_MERGER_MAX,
    "watchlist": SEC_WATCHLIST_MAX,
}

# ── LLM section classifier ─────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior news-desk editor building a morning brief.
You will receive a JSON list of headlines (title, source, summary).

For EACH headline, decide:
  1. Whether it belongs in the brief (relevant = true/false).
  2. Which section it belongs to.
  3. A one-sentence reason.

Sections (use these exact keys):
  "headline"       -- ONLY for truly major events matching ANY of these:
                      {criteria}
                      If nothing qualifies, assign ZERO stories here.
  "global_news"    -- Breaking world events, treaties, trade agreements,
                      geopolitical developments.
  "ai_tech"        -- AI model releases, big tech moves, regulation,
                      strategic pivots, infrastructure plays.
  "macro_markets"  -- Central bank moves, GDP, inflation, bond/equity
                      shifts, commodities, FX.
  "merger_news"    -- ONLY structurally interesting special situations:
                      demergers, spin-offs, reverse splits, carve-outs,
                      hiving off divisions, activist campaigns, SPACs.
                      NOT generic acquisitions unless structurally notable.
  "watchlist"      -- Forward-looking items worth monitoring.
                      Phrase reason as "Watch for...", "Risk to monitor...",
                      or "Potential second-order impact...".

Return ONLY valid JSON (no markdown fences), a list of objects:
[
  {{
    "title": "<exact original title>",
    "relevant": true,
    "section": "<section key>",
    "reason": "<one sentence>"
  }},
  ...
]

Be strict. No fluff. Crisp analytical filter.
""".format(criteria="; ".join(HEADLINE_CRITERIA))


# Maximum stories per LLM batch.  Each story is ~500 tokens on average;
# 50 stories ≈ 25 000 prompt tokens which stays well under typical TPM
# limits even for free-tier orgs.
_LLM_BATCH_SIZE = 50


def _llm_classify_batch(
    stories: list[dict[str, Any]],
    span_parent: Any = None,
) -> tuple[list[dict], dict]:
    """Classify a single batch; return (results_list, usage_totals)."""
    payload = [
        {"title": s["title"], "source": s["source"], "summary": s.get("summary", "")}
        for s in stories
    ]
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        temperature=0.2,
    )
    usage = resp.usage
    totals = {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }
    raw = resp.choices[0].message.content or "[]"
    raw = (
        raw.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    return json.loads(raw), totals


def _llm_classify(
    stories: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Return {{fingerprint: {{"relevant": bool, "section": str, "reason": str}} }}

    Stories are split into batches of _LLM_BATCH_SIZE to stay under
    OpenAI token-per-minute limits.
    """
    if not client:
        logger.warning("No OpenAI key -- skipping LLM classification")
        return {}

    # Split into batches
    batches = [
        stories[i : i + _LLM_BATCH_SIZE]
        for i in range(0, len(stories), _LLM_BATCH_SIZE)
    ]
    logger.info(
        "Classifying %d stories in %d batch(es) of up to %d",
        len(stories),
        len(batches),
        _LLM_BATCH_SIZE,
    )

    all_results: list[dict] = []
    total_prompt = total_completion = total_tokens = 0

    with tracer.start_as_current_span("llm_classify") as span:
        span.set_attribute("llm.model", OPENAI_MODEL)
        span.set_attribute("llm.stories_count", len(stories))
        span.set_attribute("llm.batches", len(batches))

        for batch_idx, batch in enumerate(batches):
            try:
                results, usage = _llm_classify_batch(batch, span)
                all_results.extend(results)
                total_prompt += usage["prompt_tokens"]
                total_completion += usage["completion_tokens"]
                total_tokens += usage["total_tokens"]
                logger.info(
                    "Batch %d/%d: classified %d stories (%d tokens)",
                    batch_idx + 1,
                    len(batches),
                    len(batch),
                    usage["total_tokens"],
                )
            except Exception:
                logger.exception("LLM classification failed on batch %d", batch_idx + 1)
                # Continue with remaining batches instead of failing entirely

        span.set_attribute("llm.prompt_tokens", total_prompt)
        span.set_attribute("llm.completion_tokens", total_completion)
        span.set_attribute("llm.total_tokens", total_tokens)

    title_to_fp = {s["title"]: s["fingerprint"] for s in stories}
    out: dict[str, dict[str, Any]] = {}
    for r in all_results:
        title = r.get("title", "")
        fp = title_to_fp.get(title)
        if not fp:
            continue
        section = r.get("section", "global_news")
        if section not in SECTIONS:
            section = "global_news"
        out[fp] = {
            "relevant": r.get("relevant", False),
            "section": section,
            "reason": r.get("reason", ""),
        }
    return out


# ── Macro threshold trigger ────────────────────────────────────────────────


def _macro_trigger(stories: list[dict[str, Any]]) -> set[str]:
    """Return fingerprints that exceed the cross-feed threshold."""
    return {
        s["fingerprint"]
        for s in stories
        if s.get("feed_count", 1) >= MACRO_HEADLINE_THRESHOLD
    }


# ── Keyword-based special-situations detector ──────────────────────────────


def _detect_special_situations(story: dict[str, Any]) -> list[str]:
    """Return matching special-situation keywords for a story."""
    text = f"{story['title']} {story.get('summary', '')}".lower()
    return [kw for kw in SPECIAL_SITUATIONS_KEYWORDS if kw.lower() in text]


# ── Public API ──────────────────────────────────────────────────────────────


def classify(
    stories: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Classify stories into sections.

    Returns a dict keyed by section name, each value a list of annotated
    story dicts.  Stories have extra fields:
        section: str
        triggered_by: list[str]
        special_situations: list[str]
        reason: str
    """
    with tracer.start_as_current_span("classify") as span:
        span.set_attribute("classify.input_stories", len(stories))

        llm_results = _llm_classify(stories)
        macro_fps = _macro_trigger(stories)

        buckets: dict[str, list[dict[str, Any]]] = {s: [] for s in SECTIONS}

        for s in stories:
            fp = s["fingerprint"]
            triggers: list[str] = []

            llm_info = llm_results.get(fp, {})
            if llm_info.get("relevant"):
                triggers.append("llm")
            if fp in macro_fps:
                triggers.append("macro")

            if not triggers:
                continue

            # Determine section
            section = llm_info.get("section", "global_news")

            # Keyword override: if special-situation keywords match, also
            # consider for merger_news
            specials = _detect_special_situations(s)
            if specials and section not in ("headline", "merger_news"):
                section = "merger_news"

            s["section"] = section
            s["triggered_by"] = triggers
            s["special_situations"] = specials
            s["reason"] = llm_info.get("reason", "")

            # Respect per-section caps
            if len(buckets[section]) < SECTION_LIMITS.get(section, 5):
                buckets[section].append(s)

        # Log summary
        total = sum(len(v) for v in buckets.values())
        per_sec = ", ".join(f"{k}={len(v)}" for k, v in buckets.items() if v)
        span.set_attribute("classify.output_stories", total)
        logger.info(
            "Classified %d stories into %d selected: %s",
            len(stories),
            total,
            per_sec,
        )
        return buckets
