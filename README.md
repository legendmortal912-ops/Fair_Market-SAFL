# SAFL — AI Policy Activity Tracker for Indian States

A data pipeline + interactive dashboard that collects and visualises AI-related policy activity across Indian states.

**🌐 Live Dashboard:** [legendmortal912-ops.github.io/SAFL-AI-Policy-Dashboard](https://legendmortal912-ops.github.io/SAFL-AI-Policy-Dashboard/)

---

## What It Does

1. **Collects** news about AI policy activity from Google News RSS, The Hindu, LiveMint, Indian Express, and PIB (Press Information Bureau)
2. **Extracts** full article text using `newspaper3k` and generates clean one-line summaries
3. **Categorises** each article into a policy taxonomy using keyword heuristics
4. **Deduplicates** syndicated stories using headline similarity matching
5. **Presents** the data as a filterable, searchable dashboard with charts

## States Covered

Karnataka · Telangana · Tamil Nadu · Maharashtra · Uttar Pradesh

## Category Taxonomy

| Category | What It Captures |
|----------|-----------------|
| Policy/Mission | State AI policies, missions, strategy documents |
| Task Force/CoE | Committees, working groups, centres of excellence |
| MoU/Partnership | Agreements with companies/universities |
| Governance Deployment | AI in health, agriculture, policing, education |
| Budget/Funding | State budget allocations, grants, investments |
| Regulation/Ethics | Guidelines, compliance, accountability measures |

## Dataset Schema

Each record in `ai_policy_data.csv` contains:

| Field | Description |
|-------|-------------|
| State | Normalised state name |
| Headline | Article title |
| Date | YYYY-MM-DD (or "Unknown") |
| Source | Publisher name |
| URL | Link to article |
| Summary | First substantive sentence of the article |
| Category | One of the 6 categories above, or "Other" |

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the pipeline (first run: ~2-4 min, subsequent runs: faster)
python pipeline.py
```

The pipeline supports **incremental updates** — re-running it will only fetch and process new articles, appending them to the existing CSV.

## Project Structure

```
├── pipeline.py           # Data collection, extraction, classification, deduplication
├── index.html            # Interactive dashboard (Chart.js + PapaParse)
├── ai_policy_data.csv    # The collected dataset
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Design Decisions

- **Google News RSS over NewsAPI** — No API key, no rate limits, wider coverage
- **Keyword classification over LLM** — Transparent, auditable, no external dependencies
- **newspaper3k over RSS snippets** — Cleaner, more complete summaries
- **Static HTML over Streamlit** — Instant load, free GitHub Pages hosting, no server needed
- **Incremental updates** — Pipeline appends new data on re-run, never reprocesses old articles

## Known Limitations

- ~28% of articles fall into "Other" — keyword matching can't handle ambiguous headlines
- Google News RSS only surfaces articles from the last 2-4 weeks
- PIB scraper only gets today's releases (no historical pagination)
- Some paywalled articles return truncated summaries
- Deduplication threshold (0.6 similarity) is heuristic, not formally evaluated

## Tech Stack

- **Pipeline:** Python (feedparser, newspaper3k, pandas, BeautifulSoup, requests)
- **Dashboard:** HTML + CSS + JavaScript (Chart.js, PapaParse)
- **Hosting:** GitHub Pages
