#!/usr/bin/env python3
"""
generate_html.py - Generování HTML stránek z výsledků analýzy
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sources.yaml"
SCRIPT_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_action_network_signatures():
    api_key = os.environ.get("ACTION_NETWORK_API")
    if not api_key:
        logger.warning("ACTION_NETWORK_API not set, skipping")
        return None
    logger.info(f"ACTION_NETWORK_API key starts with: {api_key[:6]}... (len={len(api_key)})")
    try:
        url = "https://actionnetwork.org/api/v2/petitions/603ad1fa-9d5a-4892-9558-87d7d04e4337/"
        req = urllib.request.Request(url, headers={"OSDI-API-Token": api_key})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("total_signatures") or data.get("signatures_count")
    except Exception as e:
        logger.warning(f"Could not fetch Action Network signatures: {e}")
        return None


def fetch_petition_stats() -> dict:
    try:
        with urllib.request.urlopen("https://jakebrno.cz/stats.php", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return {"dnes": data.get("complete", 0), "celkem": data.get("total", 0)}
    except Exception as e:
        logger.warning(f"Could not fetch petition stats: {e}")
        return None


def load_analysis(config: dict, run_type: str):
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    latest_file = data_dir / f"latest_analysis_{run_type}.json"

    if not latest_file.exists():
        logger.warning(f"No analysis file for run type: {run_type}")
        return None

    with open(latest_file) as f:
        latest = json.load(f)

    analysis_file = Path(latest["analysis_file"])
    if not analysis_file.exists():
        logger.error(f"Analysis file not found: {analysis_file}")
        return None

    with open(analysis_file, encoding="utf-8") as f:
        return json.load(f)



def get_nav_dates(date: datetime, base_url: str) -> dict:
    prev_date = date - timedelta(days=1)
    next_date = date + timedelta(days=1)
    today = datetime.now(ZoneInfo("Europe/Prague"))

    def date_to_path(d):
        return f"{base_url}/{d.strftime('%Y/%m/%d')}.html"

    return {
        "prev": {"date": prev_date, "path": date_to_path(prev_date)},
        "next": (
            {"date": next_date, "path": date_to_path(next_date)}
            if next_date.date() <= today.date()
            else None
        ),
        "month_path": f"{base_url}/{date.strftime('%Y/%m')}/index.html",
    }


def generate_daily_page(env: Environment, analysis: dict, config: dict, run_type: str, petition_stats: dict = None, an_signatures: int = None):
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)

    template = env.get_template("daily.html")

    base_url = config["settings"].get("base_url", "")
    nav = get_nav_dates(now, base_url)

    # Count total articles
    total_articles = sum(
        len(articles) for articles in analysis.get("categories", {}).values()
    )

    context = {
        "date": now,
        "date_str": now.strftime("%d. %m. %Y"),
        "run_type": run_type,
        "analysis": analysis,
        "categories": analysis.get("categories", {}),
        "person_mentions": analysis.get("person_mentions", {}),
        "managerske_shrnuti": analysis.get("managerske_shrnuti", {}),
        "stats": analysis.get("stats", {}),
        "total_articles": total_articles,
        "nav": nav,
        "assets_path": "../../assets",
        "base_url": base_url,
        "category_labels": {
            "komunalni_politika": "Komunální politika",
            "doprava": "Doprava",
            "kultura": "Kultura",
            "sport": "Sport",
            "kriminalita": "Kriminalita",
            "ekonomika": "Ekonomika",
            "zdravotnictvi": "Zdravotnictví",
            "skolstvi": "Školství",
            "zivotni_prostredi": "Životní prostředí",
            "ostatni": "Ostatní",
        },
        "category_icons": {
            "komunalni_politika": "🏛️",
            "doprava": "🚌",
            "kultura": "🎭",
            "sport": "⚽",
            "kriminalita": "🚔",
            "ekonomika": "💼",
            "zdravotnictvi": "🏥",
            "skolstvi": "🎓",
            "zivotni_prostredi": "🌳",
            "ostatni": "📰",
        },
        "petition_stats": petition_stats,
        "an_signatures": an_signatures,
    }

    html = template.render(**context)

    output_dir = SCRIPT_DIR / config["settings"]["output_dir"] / now.strftime("%Y/%m")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{now.strftime('%d')}.html"
    main_output = output_dir / f"{now.strftime('%d')}.html"
    with open(main_output, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Generated daily page: {main_output}")
    return main_output


def generate_month_page(env: Environment, config: dict, petition_stats: dict = None, an_signatures: int = None):
    import calendar as cal_module
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)

    output_dir = SCRIPT_DIR / config["settings"]["output_dir"] / now.strftime("%Y/%m")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect days that have HTML files
    days_with_data = set()
    for day_file in output_dir.glob("??.html"):
        try:
            days_with_data.add(int(day_file.stem))
        except ValueError:
            pass

    # Build full calendar grid
    year, month = now.year, now.month
    _, days_in_month = cal_module.monthrange(year, month)
    first_weekday = cal_module.monthrange(year, month)[0]  # 0=Mon

    # Prev/next month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    base_url = config["settings"].get("base_url", "")
    prev_month_path = f"{base_url}/{prev_year:04d}/{prev_month:02d}/index.html"
    next_month_path = f"{base_url}/{next_year:04d}/{next_month:02d}/index.html"
    next_month_exists = (SCRIPT_DIR / config["settings"]["output_dir"] / f"{next_year:04d}/{next_month:02d}/index.html").exists()

    template = env.get_template("month.html")
    context = {
        "year": year,
        "month": month,
        "month_str": now.strftime("%B %Y"),
        "days_in_month": days_in_month,
        "first_weekday": first_weekday,
        "days_with_data": days_with_data,
        "today_day": now.day if now.year == year and now.month == month else None,
        "date": now,
        "prev_month_path": prev_month_path,
        "next_month_path": next_month_path,
        "next_month_exists": next_month_exists,
        "assets_path": "../../assets",
        "base_url": base_url,
        "petition_stats": petition_stats,
        "an_signatures": an_signatures,
    }

    html = template.render(**context)
    output_file = output_dir / "index.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Generated month page: {output_file}")


def generate_index_page(env: Environment, config: dict, latest_analysis: dict, petition_stats: dict = None, an_signatures: int = None):
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)

    output_dir = SCRIPT_DIR / config["settings"]["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    base_url = config["settings"].get("base_url", "")
    docs_dir = output_dir

    # Collect recent days (last 30) that have HTML files
    recent_days = []
    for year_dir in sorted(docs_dir.glob("????"), reverse=True)[:2]:
        for month_dir in sorted(year_dir.glob("??"), reverse=True)[:6]:
            for day_file in sorted(month_dir.glob("??.html"), reverse=True):
                try:
                    day_num = int(day_file.stem)
                    year = int(year_dir.name)
                    month = int(month_dir.name)
                    day_date = datetime(year, month, day_num, tzinfo=tz)
                    recent_days.append({
                        "date": day_date,
                        "path": f"{base_url}/{year_dir.name}/{month_dir.name}/{day_file.stem}.html",
                    })
                except (ValueError, Exception):
                    pass
    recent_days.sort(key=lambda x: x["date"], reverse=True)
    recent_days = recent_days[:30]

    # Collect months for archive
    months = []
    for year_dir in sorted(docs_dir.glob("????"), reverse=True)[:2]:
        for month_dir in sorted(year_dir.glob("??"), reverse=True)[:12]:
            month_index = month_dir / "index.html"
            months.append({
                "year": int(year_dir.name),
                "month": int(month_dir.name),
                "path": f"{base_url}/{year_dir.name}/{month_dir.name}/index.html",
                "has_index": month_index.exists(),
            })

    # Collect media sources for "O projektu" section
    media_sources = (
        [s["name"] for s in config.get("rss_sources", [])]
        + [s["name"] for s in config.get("web_scrape", [])]
        + [s["name"] for s in config.get("google_alerts", []) if s.get("category") == "media"]
    )
    watched_politicians = config.get("watched_names", {}).get("politicians", [])
    watched_other = [
        (item["name"] if isinstance(item, dict) else item)
        for item in config.get("watched_names", {}).get("other", [])
    ]

    template = env.get_template("index.html")
    context = {
        "date": now,
        "latest_analysis": latest_analysis,
        "latest_path": f"{base_url}/{now.strftime('%Y/%m/%d')}.html",
        "months": months,
        "recent_days": recent_days,
        "stats": latest_analysis.get("stats", {}) if latest_analysis else {},
        "assets_path": "assets",
        "base_url": base_url,
        "media_sources": media_sources,
        "watched_politicians": watched_politicians,
        "watched_other": watched_other,
        "petition_stats": petition_stats,
        "an_signatures": an_signatures,
    }

    html = template.render(**context)
    output_file = output_dir / "index.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Generated index page: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Generate HTML pages from analysis")
    parser.add_argument(
        "--run",
        choices=["daily", "manual"],
        default="manual",
    )
    args = parser.parse_args()

    logger.info(f"Starting HTML generation - run type: {args.run}")

    config = load_config()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )

    # Add custom filters
    def format_date(value, fmt="%d. %m. %Y %H:%M"):
        if isinstance(value, str):
            try:
                from dateutil import parser as date_parser

                value = date_parser.parse(value)
            except Exception:
                return value
        if hasattr(value, "strftime"):
            return value.strftime(fmt)
        return str(value)

    env.filters["format_date"] = format_date

    analysis = load_analysis(config, args.run)

    if not analysis:
        logger.warning("No analysis data, generating empty page")
        analysis = {
            "run_type": args.run,
            "analyzed_at": datetime.now().isoformat(),
            "categories": {
                cat: []
                for cat in [
                    "komunalni_politika",
                    "doprava",
                    "kultura",
                    "sport",
                    "kriminalita",
                    "ekonomika",
                    "zdravotnictvi",
                    "skolstvi",
                    "zivotni_prostredi",
                    "ostatni",
                ]
            },
            "person_mentions": {},
            "stats": {
                "total_analyzed": 0,
                "total_relevant": 0,
                "komunalni_politika_count": 0,
            },
        }

    petition_stats = fetch_petition_stats()
    logger.info(f"Petition stats: {petition_stats}")

    an_signatures = fetch_action_network_signatures()
    logger.info(f"Action Network signatures: {an_signatures}")

    generate_daily_page(env, analysis, config, args.run, petition_stats, an_signatures)
    generate_month_page(env, config, petition_stats, an_signatures)
    generate_index_page(env, config, analysis, petition_stats, an_signatures)

    logger.info("HTML generation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
