"""
FastAPI application entry point for Cloud Run.

Endpoints
---------
POST /trigger   Run the full pipeline: fetch > classify > digest > send.
GET  /health    Liveness probe.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException

from app.classifier import classify
from app.digest_writer import build_digest
from app.gmail_sender import send_email
from app.news_fetcher import fetch_all
from app.tracing import get_tracer, init_tracing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

app = FastAPI(title="Morning Brief")
init_tracing(app)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
def trigger():
    """
    Full pipeline execution:
    1. Fetch RSS headlines
    2. Classify into sections (dual-trigger logic)
    3. Build structured HTML digest
    4. Send via Gmail API
    """
    with tracer.start_as_current_span("pipeline") as span:
        t0 = time.time()

        # Step 1: Fetch
        logger.info("Step 1/4: Fetching RSS feeds")
        stories = fetch_all()
        span.set_attribute("pipeline.stories_fetched", len(stories))
        if not stories:
            raise HTTPException(status_code=502, detail="No stories fetched from any feed")

        # Step 2: Classify into section buckets
        logger.info("Step 2/4: Classifying headlines into sections")
        buckets = classify(stories)
        total_selected = sum(len(v) for v in buckets.values())
        span.set_attribute("pipeline.stories_selected", total_selected)
        if total_selected == 0:
            raise HTTPException(status_code=204, detail="No stories passed classification")

        # Step 3: Build digest
        logger.info("Step 3/4: Building structured digest")
        subject, html = build_digest(buckets)

        # Step 4: Send email
        logger.info("Step 4/4: Sending email")
        result = send_email(subject, html)

        elapsed = round(time.time() - t0, 2)
        section_counts = {k: len(v) for k, v in buckets.items() if v}
        span.set_attribute("pipeline.elapsed_seconds", elapsed)
        span.set_attribute("pipeline.sections", str(section_counts))
        logger.info(
            "Pipeline complete in %ss: %d stories delivered across %d sections",
            elapsed,
            total_selected,
            len(section_counts),
        )

        return {
            "stories_fetched": len(stories),
            "stories_selected": total_selected,
            "sections": section_counts,
            "email_message_id": result.get("id"),
            "elapsed_seconds": elapsed,
        }
