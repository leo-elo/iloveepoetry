#!/usr/bin/env python3
"""
For images that failed to download, check the Wayback Machine for archived versions
and download them from there.
"""

import json
import os
import re
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
ASSETS_DIR = PROJECT_DIR / "assets" / "images"
FAILURES_LOG = SCRIPTS_DIR / "download_failures.log"
MANIFEST_FILE = SCRIPTS_DIR / "image_manifest.json"
WAYBACK_REPORT = SCRIPTS_DIR / "wayback_report.json"

MAX_WORKERS = 3
TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def url_to_local_path(url):
    """Map URL to local path - same logic as download_images.py."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = unquote(parsed.path).lstrip("/")

    if "iloveepoetry" in host and "wp-content/uploads/" in path:
        idx = path.index("wp-content/uploads/")
        rel = path[idx:]
        return ASSETS_DIR / rel

    if "academic.uprm.edu" in host and "/flores/images/" in path:
        filename = path.split("/flores/images/")[-1]
        return ASSETS_DIR / "uprm" / filename

    safe_path = path.replace("..", "_")
    return ASSETS_DIR / "other" / host / safe_path


def get_wayback_url(original_url):
    """Get the most recent Wayback Machine snapshot of a URL."""
    try:
        encoded = quote(original_url, safe='')
        api_url = f"https://web.archive.org/cdx/search/cdx?url={original_url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200&sort=reverse"
        resp = requests.get(api_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if len(data) > 1:
                timestamp = data[1][0]
                original = data[1][1]
                return f"https://web.archive.org/web/{timestamp}id_/{original}"
    except Exception as e:
        pass
    return None


def download_from_wayback(original_url, wayback_url, local_path):
    """Download a file from the Wayback Machine."""
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(wayback_url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size = local_path.stat().st_size
        if size == 0:
            local_path.unlink()
            return False
        return True
    except Exception:
        if local_path.exists():
            local_path.unlink()
        return False


def main():
    logger.info("=== Wayback Machine Fallback Script ===")

    # Read failures
    if not FAILURES_LOG.exists():
        logger.error("No failures log found")
        return

    failed_urls = []
    with open(FAILURES_LOG, "r") as f:
        for line in f:
            parts = line.strip().split("\t", 1)
            if parts:
                failed_urls.append(parts[0])

    logger.info(f"Failed URLs to check: {len(failed_urls)}")

    # Load existing manifest
    manifest = {}
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, "r") as f:
            manifest = json.load(f)

    report = {
        "checked": 0,
        "found_on_wayback": 0,
        "downloaded_from_wayback": 0,
        "not_on_wayback": 0,
        "download_failed": 0,
    }

    for i, url in enumerate(failed_urls):
        if i % 20 == 0 and i > 0:
            logger.info(f"Progress: {i}/{len(failed_urls)} (found: {report['found_on_wayback']}, downloaded: {report['downloaded_from_wayback']})")
            time.sleep(1)  # Rate limiting for Wayback API

        local_path = url_to_local_path(url)

        # Skip if already downloaded
        if local_path.exists() and local_path.stat().st_size > 0:
            continue

        report["checked"] += 1

        wayback_url = get_wayback_url(url)
        if wayback_url:
            report["found_on_wayback"] += 1
            if download_from_wayback(url, wayback_url, local_path):
                report["downloaded_from_wayback"] += 1
                rel_path = os.path.relpath(str(local_path), str(PROJECT_DIR))
                manifest[url] = rel_path
            else:
                report["download_failed"] += 1
        else:
            report["not_on_wayback"] += 1

        # Rate limit Wayback API
        time.sleep(0.5)

    # Update manifest
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Write report
    with open(WAYBACK_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("=== Wayback Fallback Complete ===")
    logger.info(f"Checked: {report['checked']}")
    logger.info(f"Found on Wayback: {report['found_on_wayback']}")
    logger.info(f"Downloaded: {report['downloaded_from_wayback']}")
    logger.info(f"Not on Wayback: {report['not_on_wayback']}")
    logger.info(f"Download failed: {report['download_failed']}")


if __name__ == "__main__":
    main()
