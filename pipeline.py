import feedparser
import pandas as pd
from dateutil import parser as date_parser
import time
import urllib.parse
from difflib import SequenceMatcher
import re
import os
import sys
import io
import requests
from newspaper import Article   # pip package: newspaper3k, imported as: newspaper

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
STATES           = ["Karnataka", "Telangana", "Tamil Nadu", "Maharashtra", "Uttar Pradesh"]
OUTPUT_FILE      = "ai_policy_data.csv"
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search?q="
MAX_PER_STATE    = 30    # Limit articles per state to keep runtime reasonable
FETCH_TIMEOUT    = (5, 8)  # (connect timeout, read timeout) in seconds

# Browser User-Agent — required for Google News, also helps with other sites
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Verified working Indian news RSS feeds
DIRECT_RSS_FEEDS = {
    "The Hindu - National":   "https://www.thehindu.com/news/national/feeder/default.rss",
    "The Hindu - Technology": "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
    "LiveMint - Technology":  "https://www.livemint.com/rss/technology",
    "LiveMint - Politics":    "https://www.livemint.com/rss/politics",
    "Indian Express - Tech":  "https://indianexpress.com/section/technology/feed/",
    # Economic Times removed — their server hangs on reads
}

AI_KEYWORDS = [
    "artificial intelligence", " ai ", "machine learning", "deep learning",
    "generative ai", "large language model", "llm", "automation",
    "data governance", "digital infrastructure", "ai policy", "ai deployment",
]

STATE_VARIANTS = {
    "Karnataka":     ["karnataka", "bengaluru", "bangalore"],
    "Telangana":     ["telangana", "hyderabad", "ts government"],
    "Tamil Nadu":    ["tamil nadu", "tamilnadu", "chennai", "tn government"],
    "Maharashtra":   ["maharashtra", "mumbai", "pune", "nagpur"],
    "Uttar Pradesh": ["uttar pradesh", "up government", "lucknow", "yogi adityanath"],
}

CATEGORY_KEYWORDS = {
    "Policy/Mission":        ["policy", "mission", "vision", "strategy", "framework", "roadmap", "initiative"],
    "Task Force/CoE":        ["task force", "taskforce", "centre of excellence", "committee", "working group", "coe"],
    "MoU/Partnership":       ["mou", "memorandum", "agreement", "partnership", "collaboration", "signed", "pact", "tie-up"],
    "Governance Deployment": ["deploy", "health", "agriculture", "policing", "education", "surveillance", "governance", "implement", "pilot"],
    "Budget/Funding":        ["crore", "fund", "budget", "allocat", "invest", "grant", "financial", "scheme"],
    "Regulation/Ethics":     ["regulat", "ethics", "guideline", "compliance", "audit", "accountability", "law", "data protection"],
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def clean_html(text):
    if not isinstance(text, str):
        return ""
    return re.sub(re.compile("<.*?>"), "", text).strip()

def is_ai_related(text):
    return any(kw in text.lower() for kw in AI_KEYWORDS)

def detect_state(text):
    tl = text.lower()
    for state, variants in STATE_VARIANTS.items():
        if any(v in tl for v in variants):
            return state
    return None

def parse_date(entry):
    for attr in ["published", "updated", "created"]:
        val = getattr(entry, attr, None)
        if val:
            try:
                return date_parser.parse(val).strftime("%Y-%m-%d")
            except Exception:
                pass
    return "Unknown"

def extract_summary(url, fallback):
    """
    WHY THIS IS SLOW:
    newspaper3k makes a real HTTP request to download each article page,
    then parses the HTML to extract the body text. With dozens of articles
    and 1 request per article, this naturally takes 1-5 min total.
    We limit MAX_PER_STATE to keep it manageable.
    """
    try:
        article = Article(url, request_timeout=8)
        article.download()
        article.parse()
        text = article.text or ""
        sentences = [s.strip() + "." for s in text.split(".") if len(s.strip()) > 40]
        if sentences:
            return sentences[0]
    except Exception:
        pass  # Silently fall back — paywalls, 403s, etc.
    return clean_html(fallback)

def categorize(headline, snippet, summary=""):
    combined = f"{headline} {snippet} {summary}".lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category
    return "Other"

def safe_fetch_rss(url):
    """
    Fetch an RSS feed using requests (with browser UA) then parse with feedparser.
    This bypasses User-Agent blocks (e.g. Google News).
    Falls back to empty list on any error — never stalls.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return feed.entries
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT] {url}")
    except requests.exceptions.HTTPError as e:
        print(f"  [HTTP ERROR {e.response.status_code}] {url}")
    except requests.exceptions.ConnectionError:
        print(f"  [CONNECTION ERROR] {url}")
    except Exception as e:
        print(f"  [ERROR] {url} -- {e}")
    return []   # Safe empty return


# ─────────────────────────────────────────────
# Fetchers
# ─────────────────────────────────────────────
def fetch_google_news(state):
    """Query Google News RSS for a given state with AI + policy terms."""
    query = (
        f"AI OR \"Artificial Intelligence\" "
        f"policy OR MoU OR \"task force\" OR deployment OR budget "
        f"\"{state}\""
    )
    url = GOOGLE_NEWS_BASE + urllib.parse.quote(query) + "&hl=en-IN&gl=IN&ceid=IN:en"
    print(f"[Google News] Fetching for: {state} ...", end=" ", flush=True)

    entries = safe_fetch_rss(url)
    articles = []
    for entry in entries[:MAX_PER_STATE]:
        src = getattr(entry, "source", None)
        src_name = src.title if src and hasattr(src, "title") else "Google News"
        articles.append({
            "state":       state,
            "headline":    entry.get("title", ""),
            "date":        parse_date(entry),
            "source_name": src_name,
            "source_url":  entry.get("link", ""),
            "rss_snippet": clean_html(entry.get("summary", "")),
        })
    print(f"{len(articles)} articles.")
    return articles

def fetch_direct_feeds():
    """Fetch verified Indian news RSS feeds; filter for AI + state relevance."""
    articles = []
    for source_name, feed_url in DIRECT_RSS_FEEDS.items():
        print(f"[RSS] {source_name} ...", end=" ", flush=True)
        entries = safe_fetch_rss(feed_url)
        count = 0
        for entry in entries:
            headline = entry.get("title", "")
            snippet  = clean_html(entry.get("summary", ""))
            combined = f"{headline} {snippet}"
            if not is_ai_related(combined):
                continue
            state = detect_state(combined)
            if not state:
                continue
            articles.append({
                "state":       state,
                "headline":    headline,
                "date":        parse_date(entry),
                "source_name": source_name,
                "source_url":  entry.get("link", ""),
                "rss_snippet": snippet,
            })
            count += 1
        print(f"{count} relevant articles.")
    return articles


# ─────────────────────────────────────────────
# Incremental update support
# ─────────────────────────────────────────────
def load_seen_urls():
    if os.path.exists(OUTPUT_FILE):
        try:
            df = pd.read_csv(OUTPUT_FILE, encoding="utf-8")
            urls = set(df["URL"].dropna().tolist())
            print(f"[Incremental] {len(urls)} articles already in CSV -- will skip these.")
            return urls, df
        except Exception as e:
            print(f"[!] Could not read existing CSV: {e}")
    print("[Fresh Run] No existing CSV found.")
    return set(), pd.DataFrame()


# ─────────────────────────────────────────────
# Core processing
# ─────────────────────────────────────────────
def process_articles(articles, seen_urls):
    df = pd.DataFrame(articles)
    if df.empty:
        print("No articles fetched from any source.")
        return pd.DataFrame()

    df = df.drop_duplicates(subset="source_url")
    df = df[~df["source_url"].isin(seen_urls)]

    if df.empty:
        print("No new articles to process (all already in CSV).")
        return pd.DataFrame()

    total = len(df)
    print(f"\nExtracting summaries for {total} new articles.")
    print("(This takes ~1-3 min because newspaper3k downloads each article page individually)\n")

    records = []
    processed = 0

    for (state, date), group in df.groupby(["state", "date"]):
        unique = []
        for _, row in group.iterrows():
            # Collapse near-duplicate headlines (same event, multiple outlets)
            is_dup = any(
                SequenceMatcher(None, row["headline"], s["Headline"]).ratio() > 0.60
                for s in unique
            )
            if is_dup:
                continue

            processed += 1
            print(f"  [{processed}/{total}] {row['headline'][:75]}")
            summary  = extract_summary(row["source_url"], row["rss_snippet"])
            category = categorize(row["headline"], row["rss_snippet"], summary)

            unique.append({
                "State":    state,
                "Headline": row["headline"],
                "Date":     date,
                "Source":   row["source_name"],
                "URL":      row["source_url"],
                "Summary":  summary,
                "Category": category,
            })
            time.sleep(0.5)   # polite crawl delay

        records.extend(unique)

    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  AI Policy News Pipeline -- India")
    print("=" * 60 + "\n")

    seen_urls, existing_df = load_seen_urls()
    print()

    # Step 1: Fetch from all sources
    all_raw = []
    for state in STATES:
        all_raw.extend(fetch_google_news(state))
    all_raw.extend(fetch_direct_feeds())
    print(f"\nTotal raw articles fetched: {len(all_raw)}")

    # Step 2: Deduplicate + summarize + categorize
    new_df = process_articles(all_raw, seen_urls)

    if new_df.empty:
        return

    # Step 3: Save (append or fresh)
    if not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"\n[DONE] Appended {len(new_df)} records. Total in CSV: {len(combined)}")
    else:
        new_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"\n[DONE] Saved {len(new_df)} records to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
