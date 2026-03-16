#!/usr/bin/env python3
"""
send_email.py - Odesílání emailových notifikací
"""

import argparse
import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def load_analysis(config: dict, run_type: str) -> dict:
    data_dir = SCRIPT_DIR / config["settings"]["data_dir"]
    latest_file = data_dir / f"latest_analysis_{run_type}.json"
    if not latest_file.exists():
        return {}
    with open(latest_file) as f:
        latest = json.load(f)
    analysis_file = Path(latest["analysis_file"])
    if not analysis_file.exists():
        return {}
    with open(analysis_file, encoding="utf-8") as f:
        return json.load(f)


def render_email(config: dict, analysis: dict, run_type: str) -> str:
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)
    base_url = config["settings"].get("base_url", "")

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    def format_date(value, fmt="%d. %m. %H:%M"):
        if isinstance(value, str):
            try:
                from dateutil import parser as dp
                value = dp.parse(value)
            except Exception:
                return value
        return value.strftime(fmt) if hasattr(value, "strftime") else str(value)

    env.filters["format_date"] = format_date

    total_articles = sum(len(v) for v in analysis.get("categories", {}).values())
    web_url = f"{base_url}/{now.strftime('%Y/%m/%d')}.html"

    context = {
        "date_str": now.strftime("%d. %m. %Y"),
        "total_articles": total_articles,
        "categories": analysis.get("categories", {}),
        "person_mentions": analysis.get("person_mentions", {}),
        "managerske_shrnuti": analysis.get("managerske_shrnuti", {}),
        "stats": analysis.get("stats", {}),
        "web_url": web_url,
    }

    return env.get_template("email.html").render(**context)


def send_email(config: dict, html_content: str, run_type: str) -> bool:
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_user or not smtp_password:
        logger.error("SMTP_USER or SMTP_PASSWORD environment variables not set")
        return False

    if not config["notifications"]["enabled"]:
        logger.info("Notifications disabled in config")
        return True

    recipients = config["notifications"]["recipients"]
    if not recipients or recipients[0] == "DOPLNIT_EMAIL":
        logger.warning("No valid email recipients configured")
        return False

    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)

    subject = f"Zelený radar – přehled zpráv {now.strftime('%d. %m. %Y')}"
    smtp_config = config["notifications"]["smtp"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)

    plain_text = f"Zelený radar – přehled zpráv {now.strftime('%d. %m. %Y')}\nHTML verze není k dispozici v textovém klientu."
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        logger.info(f"Connecting to SMTP {smtp_config['host']}:{smtp_config['port']}")
        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            server.ehlo()
            if smtp_config.get("use_tls", True):
                server.starttls()
                server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())
        logger.info(f"Email sent to {recipients}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected email error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send email notifications")
    parser.add_argument("--run", choices=["daily", "manual"], default="manual")
    args = parser.parse_args()

    logger.info(f"Starting email send - run type: {args.run}")

    config = load_config()
    analysis = load_analysis(config, args.run)

    if not analysis:
        logger.error("No analysis data found")
        sys.exit(1)

    html_content = render_email(config, analysis, args.run)
    success = send_email(config, html_content, args.run)

    if success:
        logger.info("Email notification sent successfully")
        return 0
    else:
        logger.warning("Email notification failed or skipped")
        return 1


if __name__ == "__main__":
    sys.exit(main())
