#!/usr/bin/env python3
"""
send_email.py - Odesílání emailových notifikací
"""

import argparse
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


def load_html_content(config: dict, run_type: str):
    tz = ZoneInfo(config["settings"]["timezone"])
    now = datetime.now(tz)

    output_dir = SCRIPT_DIR / config["settings"]["output_dir"]

    if run_type == "morning":
        html_file = (
            output_dir / now.strftime("%Y/%m") / f"{now.strftime('%d')}-morning.html"
        )
    elif run_type == "afternoon":
        html_file = (
            output_dir / now.strftime("%Y/%m") / f"{now.strftime('%d')}-afternoon.html"
        )
    else:
        html_file = output_dir / now.strftime("%Y/%m") / f"{now.strftime('%d')}.html"

    # Fallback to main daily file
    if not html_file.exists():
        html_file = output_dir / now.strftime("%Y/%m") / f"{now.strftime('%d')}.html"

    if not html_file.exists():
        logger.error(f"HTML file not found: {html_file}")
        return None

    with open(html_file, encoding="utf-8") as f:
        return f.read()


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

    run_labels = {
        "morning": "ranní přehled",
        "afternoon": "odpolední přehled",
        "daily": "denní souhrn",
        "manual": "manuální přehled",
    }

    subject = f"Brno News Monitor - {run_labels.get(run_type, run_type)} {now.strftime('%d. %m. %Y')}"

    smtp_config = config["notifications"]["smtp"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain_text = (
        f"Brno News Monitor - {run_labels.get(run_type, run_type)}\n"
        f"{now.strftime('%d. %m. %Y')}\n\n"
        f"HTML verze není k dispozici v textovém klientu."
    )
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        logger.info(
            f"Connecting to SMTP server {smtp_config['host']}:{smtp_config['port']}"
        )
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
    parser.add_argument(
        "--run",
        choices=["morning", "afternoon", "daily", "manual"],
        default="manual",
    )
    args = parser.parse_args()

    logger.info(f"Starting email send - run type: {args.run}")

    config = load_config()

    html_content = load_html_content(config, args.run)
    if not html_content:
        logger.error("Could not load HTML content for email")
        sys.exit(1)

    success = send_email(config, html_content, args.run)

    if success:
        logger.info("Email notification sent successfully")
        return 0
    else:
        logger.warning("Email notification failed or skipped")
        return 1


if __name__ == "__main__":
    sys.exit(main())
