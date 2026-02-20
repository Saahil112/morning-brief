# Morning Brief

A containerised agent that aggregates RSS news, classifies headlines using dual-trigger logic (LLM relevance + macro cross-feed threshold), and delivers a structured HTML digest to your inbox at 9:30 AM daily via the Gmail API.

## Digest Structure

| # | Section | Content | Story Cap |
|---|---------|---------|-----------|
| 1 | **Headline** | Only truly major events: macro shocks, geopolitical escalations, $50B+ M&A, systemic risk. **Suppressed if empty.** | 2 |
| 2 | **Global News** | Breaking world events, treaties, trade agreements | 3-4 |
| 3 | **AI & Technology** | Model releases, big tech moves, regulation, infrastructure plays | 2-3 |
| 4 | **Macro & Markets** | Central bank moves, GDP, inflation, bond/equity/FX shifts | 2-3 |
| 5 | **Merger News** | Special situations only: demergers, spin-offs, reverse splits, carve-outs, activist campaigns, SPACs. Not generic acquisitions. | 4 |
| 6 | **Watchlist** | Short forward-looking bullets: "Watch for...", "Risk to monitor...", "Potential second-order impact..." | 5 |

Max 300 words per story. Crisp analytical tone. No fluff. No em dashes.

## Project Structure

```
morning-brief/
|-- app/
|   |-- main.py            # FastAPI entry point
|   |-- config.py          # Environment-driven configuration
|   |-- tracing.py         # OpenTelemetry / Cloud Trace setup
|   |-- news_fetcher.py    # RSS aggregation and dedup
|   |-- classifier.py      # Dual-trigger, section-based classification
|   |-- digest_writer.py   # Structured HTML digest builder (6 sections)
|   |-- gmail_sender.py    # Gmail API OAuth sender
|-- .env                   # Environment variables (git-ignored)
|-- .gitignore
|-- requirements.txt
|-- Dockerfile
|-- README.md
```

## Dual Headline Trigger Logic

A story is included if **either** trigger fires:

| Trigger | How it works |
|---------|-------------|
| **LLM relevance** | OpenAI classifies each headline by importance and assigns it to a section. |
| **Macro threshold** | If N+ feeds carry the same headline (configurable via `MACRO_HEADLINE_THRESHOLD`), it is auto-included. |

## Setup

### 1. Environment Variables

Create a `.env` file (or set in Cloud Run):

```env
OPENAI_API_KEY=sk-...
GMAIL_SENDER=you@gmail.com
GMAIL_RECIPIENT=you@gmail.com
GMAIL_CREDENTIALS_JSON=credentials.json
GMAIL_TOKEN_JSON=token.json

# Optional: override feed lists (comma-separated)
RSS_FEEDS_GLOBAL=https://feeds.bbci.co.uk/news/world/rss.xml,...
RSS_FEEDS_AI_TECH=https://feeds.feedburner.com/TechCrunch/,...
RSS_FEEDS_MACRO=https://www.ft.com/?format=rss,...
RSS_FEEDS_MERGER=https://feeds.reuters.com/reuters/mergersNews,...

# Optional: tune limits
MACRO_HEADLINE_THRESHOLD=3
SEC_HEADLINE_MAX=2
SEC_GLOBAL_MAX=4
SEC_AI_TECH_MAX=3
SEC_MACRO_MAX=3
SEC_MERGER_MAX=4
SEC_WATCHLIST_MAX=5
STORY_MAX_WORDS=300
OPENAI_MODEL=gpt-4o
```

### 2. Gmail OAuth

1. Create an OAuth 2.0 Client ID in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Download the client secret JSON and save as `credentials.json`.
3. Run the app locally once. It will open a browser for consent and create `token.json`.
4. Upload `token.json` alongside the container (or mount as a secret).

### 3. Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
# Then: curl -X POST http://localhost:8080/trigger
```

### 4. Docker

```bash
docker build -t morning-brief .
docker run -p 8080:8080 --env-file .env morning-brief
```

### 5. Deploy to Cloud Run

```bash
gcloud run deploy morning-brief \
  --source . \
  --region us-central1 \
  --allow-unauthenticated=false \
  --set-env-vars OPENAI_API_KEY=sk-...,GMAIL_SENDER=you@gmail.com,GMAIL_RECIPIENT=you@gmail.com
```

### 6. Cloud Scheduler (9:30 AM daily)

```bash
gcloud scheduler jobs create http morning-brief-trigger \
  --schedule="30 9 * * *" \
  --uri="https://<CLOUD_RUN_URL>/trigger" \
  --http-method=POST \
  --oidc-service-account-email=<SA>@<PROJECT>.iam.gserviceaccount.com
```


## Observability (Cloud Trace)

Every pipeline run is fully traced via OpenTelemetry. On Cloud Run, spans export automatically to [Cloud Trace](https://console.cloud.google.com/traces). Locally, spans print to the console.

| Span | Key Attributes |
|------|----------------|
| `pipeline` | `stories_fetched`, `stories_selected`, `elapsed_seconds`, `sections` |
| `fetch_all` | `feeds.count`, `feeds.stories_total` |
| `fetch_feed` (per feed) | `feed.url`, `feed.source`, `feed.entries`, `feed.error` |
| `llm_classify` | `llm.model`, `llm.stories_count`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.total_tokens` |
| `classify` | `classify.input_stories`, `classify.output_stories` |
| `llm_summarize` | Token usage (same as above) |
| `llm_watchlist` | Token usage (same as above) |
| `build_digest` | `digest.total_stories` |
| `send_email` | `email.recipient`, `email.subject`, `email.message_id` |

FastAPI inbound requests and outbound HTTP calls (via `requests`) are auto-instrumented.

To override the service name, set:

```env
OTEL_SERVICE_NAME=morning-brief
```
