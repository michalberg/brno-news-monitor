#!/usr/bin/env python3
"""
daily_summary.py - Agregace denního souhrnu z ranního a odpoledního běhu
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent


def run_script(script_name: str, args: list) -> bool:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path)] + args
    logger.info(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        logger.error(f"Script {script_name} failed with exit code {result.returncode}")
        return False
    return True


def main():
    logger.info("Starting daily summary aggregation")

    # Generate daily HTML (merges morning + afternoon)
    if not run_script("generate_html.py", ["--run", "daily"]):
        logger.error("Failed to generate daily HTML")
        sys.exit(1)

    # Send daily email
    if not run_script("send_email.py", ["--run", "daily"]):
        logger.warning("Daily email failed (non-fatal)")

    logger.info("Daily summary complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
