#!/usr/bin/env python3
"""
fetch_rss.py - Stahování RSS feedů pro Zelený radar
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import re

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sources.yaml"
SCRIPT_DIR = Path(__file__).parent.parent


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_run_dir(config: dict, run_type: str) -> tuple:
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    run_dir = data_dir / now.strftime("%Y/%m/%d") / now.strftime("%H-%M")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, now


def get_seen_urls_path(config: dict) -> Path:
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "seen_urls.json"


def load_seen_urls(config: dict) -> set:
    path = get_seen_urls_path(config)
    if path.exists():
        try:
            with open(path, "r") as f:
                data = json.load(f)
                # Keep only last 7 days worth of URLs (approx 10000 entries)
                urls = set(data.get("urls", []))
                logger.info(f"Loaded {len(urls)} already seen URLs")
                return urls
        except Exception as e:
            logger.warning(f"Could not load seen URLs: {e}")
    return set()


def save_seen_urls(config: dict, seen_urls: set):
    path = get_seen_urls_path(config)
    # Limit to last 20000 to avoid unbounded growth
    urls_list = list(seen_urls)[-20000:]
    with open(path, "w") as f:
        json.dump({"urls": urls_list, "updated": datetime.now().isoformat()}, f)


def url_hash(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()


def fetch_feed(source: dict) -> list:
    url = source["url"]
    name = source["name"]

    if "DOPLNIT" in url:
        logger.info(f"Skipping placeholder source: {name}")
        return []

    logger.info(f"Fetching: {name} ({url})")

    try:
        # feedparser can handle the URL directly but we add timeout via requests
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ZelenyRadar/1.0; +https://github.com/user/brno-news-monitor)"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        articles = []
        for entry in feed.entries:
            # Extract published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6]).isoformat()
            else:
                published = datetime.now().isoformat()

            # Extract summary
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            # Clean HTML from summary
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()

            article = {
                "id": url_hash(entry.get("link", entry.get("id", ""))),
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": summary[:1000],  # Limit summary length
                "published": published,
                "source": name,
                "source_url": url,
                "category": source.get("category", "media"),
                "fetched_at": datetime.now().isoformat(),
            }

            if article["link"] and article["title"]:
                articles.append(article)

        logger.info(f"  -> {len(articles)} articles from {name}")
        return articles

    except requests.RequestException as e:
        logger.error(f"  -> HTTP error for {name}: {e}")
        return []
    except Exception as e:
        logger.error(f"  -> Error fetching {name}: {e}")
        return []


def scrape_article_text(url: str, headers: dict) -> str:
    """Fetch individual article page and extract main text."""
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Try common article body selectors
        for selector in [".article__body", ".article-body", ".content__body", "article p", ".perex"]:
            el = soup.select(selector)
            if el:
                text = " ".join(e.get_text(" ", strip=True) for e in el[:5])
                return text[:800]
        return ""
    except Exception:
        return ""


def scrape_web(source: dict) -> list:
    """Scrape a website without RSS using configured regex patterns."""
    url = source["url"]
    name = source["name"]
    logger.info(f"Scraping: {name} ({url})")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ZelenyRadar/1.0)",
        "Accept-Language": "cs,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text

        link_pattern = source.get("article_link_pattern", "")
        title_pattern = source.get("title_pattern", "")

        # Extract unique links
        links = list(dict.fromkeys(re.findall(link_pattern, html)))

        # Build title map via BeautifulSoup — find <a href="link">Title</a>
        title_map = {}
        links_set = set(links)
        soup = BeautifulSoup(html, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href in links_set:
                text = a_tag.get_text(strip=True)
                if len(text) > 10 and href not in title_map:
                    title_map[href] = text

        brno_filter = source.get("brno_filter", False)

        articles = []
        for link in links:
            title = title_map.get(link, "")
            if not title:
                continue
            if brno_filter and "brno" not in (link + title).lower():
                continue

            summary = ""
            if source.get("fetch_article_text"):
                summary = scrape_article_text(link, headers)

            articles.append({
                "id": url_hash(link),
                "title": title,
                "link": link,
                "summary": summary,
                "published": datetime.now().isoformat(),
                "source": name,
                "source_url": url,
                "category": source.get("category", "media"),
                "fetched_at": datetime.now().isoformat(),
            })

        logger.info(f"  -> {len(articles)} articles from {name}")
        return articles

    except requests.RequestException as e:
        logger.error(f"  -> HTTP error scraping {name}: {e}")
        return []
    except Exception as e:
        logger.error(f"  -> Error scraping {name}: {e}")
        return []


def fetch_all(config: dict, seen_urls: set) -> tuple:
    all_articles = []
    new_seen_urls = set(seen_urls)

    sources = config.get("rss_sources", []) + config.get("google_alerts", [])
    scrape_sources = config.get("web_scrape", [])

    for source in sources:
        articles = fetch_feed(source)
        _add_new(articles, seen_urls, new_seen_urls, all_articles)

    for source in scrape_sources:
        articles = scrape_web(source)
        _add_new(articles, seen_urls, new_seen_urls, all_articles)

    return all_articles, new_seen_urls


def _add_new(articles: list, seen_urls: set, new_seen_urls: set, all_articles: list):
    new = []
    for article in articles:
        if article["id"] not in seen_urls:
            new.append(article)
            new_seen_urls.add(article["id"])
        else:
            logger.debug(f"  Skipping duplicate: {article['title'][:60]}")
    logger.info(f"  -> {len(new)} new (skipped {len(articles) - len(new)} duplicates)")
    all_articles.extend(new)


def main():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds for Zelený radar")
    parser.add_argument(
        "--run",
        choices=["daily", "manual"],
        default="manual",
        help="Run type",
    )
    args = parser.parse_args()

    logger.info(f"Starting RSS fetch - run type: {args.run}")

    config = load_config()
    seen_urls = load_seen_urls(config)

    articles, new_seen_urls = fetch_all(config, seen_urls)

    run_dir, now = get_run_dir(config, args.run)

    output = {
        "run_type": args.run,
        "fetched_at": now.isoformat(),
        "timezone": config["settings"]["timezone"],
        "total_articles": len(articles),
        "articles": articles,
    }

    output_file = run_dir / "articles.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(articles)} new articles to {output_file}")

    # Save latest run info
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    latest_file = data_dir / f"latest_{args.run}.json"
    with open(latest_file, "w") as f:
        json.dump({"run_dir": str(run_dir), "run_at": now.isoformat()}, f)

    save_seen_urls(config, new_seen_urls)

    logger.info(f"Done. Total new articles: {len(articles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
