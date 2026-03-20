#!/usr/bin/env python3
"""
Rewrite links in generated Jekyll posts:
1. Image URLs -> local paths
2. Internal WordPress links -> new Jekyll permalinks
3. wp.me shortlinks -> resolved permalinks
4. localhost links -> cleaned up or flagged
5. Broken external links -> Wayback Machine archived versions
"""

import json
import os
import re
import sys
import logging
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

# Configuration
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
POSTS_DIR = PROJECT_DIR / "_posts"
PAGES_DIR = PROJECT_DIR / "_pages"
BASEURL = "/iloveepoetry"

URL_MAP_FILE = SCRIPTS_DIR / "url_map.json"
IMAGE_MANIFEST_FILE = SCRIPTS_DIR / "image_manifest.json"
LINK_REPORT_FILE = SCRIPTS_DIR / "link_rewrite_report.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_url_map():
    """Load the URL mapping from convert_wp.py output."""
    if not URL_MAP_FILE.exists():
        logger.error(f"URL map not found: {URL_MAP_FILE}")
        logger.info("Run convert_wp.py first")
        sys.exit(1)
    with open(URL_MAP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_image_manifest():
    """Load the image manifest from download_images.py output."""
    if not IMAGE_MANIFEST_FILE.exists():
        logger.warning(f"Image manifest not found: {IMAGE_MANIFEST_FILE}")
        logger.info("Run download_images.py first for image path rewriting")
        return {}
    with open(IMAGE_MANIFEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def decode_wp_shortlink(encoded_id):
    """Decode a WordPress wp.me shortlink base-62 encoded post ID."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = 0
    for c in encoded_id:
        if c not in chars:
            return None
        result = result * 62 + chars.index(c)
    return result


def resolve_wpme_link(url, url_map):
    """Resolve a wp.me shortlink to a new permalink."""
    # wp.me format: http://wp.me/p{blogid}-{base62id}
    match = re.match(r'https?://wp\.me/p[A-Za-z0-9]+-([A-Za-z0-9]+)', url)
    if not match:
        return None
    encoded = match.group(1)
    post_id = decode_wp_shortlink(encoded)
    if post_id is None:
        return None
    key = f"p_{post_id}"
    return url_map.get(key)


def rewrite_image_url(url, image_manifest):
    """Rewrite an image URL to local path if available."""
    if url in image_manifest:
        local_path = image_manifest[url]
        if local_path:  # None means skipped
            # Convert to site-relative URL with baseurl
            return f"{BASEURL}/{local_path}"
    return None


def rewrite_internal_link(url, url_map):
    """Rewrite an internal iloveepoetry.org link to new Jekyll permalink."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Check if this is an internal link
    internal_hosts = [
        "iloveepoetry.org", "www.iloveepoetry.org",
        "iloveepoetry.com", "www.iloveepoetry.com",
        "localhost",
    ]
    if host not in internal_hosts and "iloveepoetry" not in host:
        return None

    # Try ?p=ID pattern
    params = parse_qs(parsed.query)
    if "p" in params:
        post_id = params["p"][0]
        key = f"p_{post_id}"
        new_url = url_map.get(key)
        if new_url:
            return f"{BASEURL}{new_url}"

    # Try slug-based lookup
    path = parsed.path.strip("/")
    if path:
        # Try direct slug match
        key = f"slug/{path}"
        new_url = url_map.get(key)
        if new_url:
            return f"{BASEURL}{new_url}"

        # Try just the last path segment
        slug = path.split("/")[-1]
        if slug:
            key = f"slug/{slug}"
            new_url = url_map.get(key)
            if new_url:
                return f"{BASEURL}{new_url}"

    return None


def check_wayback(url, session):
    """Check the Wayback Machine for an archived version of a URL."""
    try:
        api_url = f"https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"
        resp = session.get(api_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if len(data) > 1:  # First row is header
                timestamp = data[1][0]
                original = data[1][1]
                return f"https://web.archive.org/web/{timestamp}/{original}"
    except Exception:
        pass
    return None


def is_image_url(url):
    """Check if URL points to an image or media file."""
    ext = Path(urlparse(url).path).suffix.lower()
    return ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".pdf", ".mp4", ".svg"}


def process_file(filepath, url_map, image_manifest, stats, check_broken=False, session=None):
    """Process a single Jekyll post/page file to rewrite links."""
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Split front matter from content
    parts = content.split("---", 2)
    if len(parts) < 3:
        stats["skipped_no_frontmatter"] += 1
        return

    front_matter = parts[1]
    body = parts[2]

    # Parse HTML content
    soup = BeautifulSoup(body, "html.parser")
    changed = False

    # Process all tags with src or href attributes
    for tag in soup.find_all(["img", "a", "iframe", "source", "video", "audio"]):
        for attr in ["src", "href"]:
            url = tag.get(attr)
            if not url or not url.startswith("http"):
                continue

            original_url = url
            new_url = None

            # 1. Try image rewriting
            if is_image_url(url):
                new_url = rewrite_image_url(url, image_manifest)
                if new_url:
                    stats["images_rewritten"] += 1

            # 2. Try wp.me shortlink resolution
            if not new_url and "wp.me" in url:
                new_url = resolve_wpme_link(url, url_map)
                if new_url:
                    new_url = f"{BASEURL}{new_url}"
                    stats["wpme_resolved"] += 1

            # 3. Try internal link rewriting
            if not new_url:
                parsed = urlparse(url)
                host = parsed.hostname or ""
                if "iloveepoetry" in host or host == "localhost":
                    # Check if it's an image in wp-content
                    if "wp-content/uploads/" in url:
                        new_url = rewrite_image_url(url, image_manifest)
                        if new_url:
                            stats["images_rewritten"] += 1
                    else:
                        new_url = rewrite_internal_link(url, url_map)
                        if new_url:
                            stats["internal_links_rewritten"] += 1
                        else:
                            stats["internal_links_unresolved"] += 1
                            stats["unresolved_urls"].add(original_url)

            # 4. For localhost URLs without resolution, remove the link
            if not new_url:
                parsed = urlparse(url)
                if parsed.hostname in ("localhost", "127.0.0.1"):
                    # Try to map by post ID in query string
                    params = parse_qs(parsed.query)
                    if "p" in params:
                        key = f"p_{params['p'][0]}"
                        resolved = url_map.get(key)
                        if resolved:
                            new_url = f"{BASEURL}{resolved}"
                            stats["localhost_resolved"] += 1
                    if not new_url:
                        stats["localhost_removed"] += 1
                        # Remove the href/src but keep the tag text
                        if attr == "href":
                            tag[attr] = "#"
                        continue

            if new_url:
                tag[attr] = new_url
                changed = True

    if changed:
        new_body = str(soup)
        new_content = f"---{front_matter}---\n{new_body}"
        filepath.write_text(new_content, encoding="utf-8")
        stats["files_modified"] += 1
    else:
        stats["files_unchanged"] += 1


def process_all_files(url_map, image_manifest, check_broken=False):
    """Process all generated Jekyll post and page files."""
    stats = {
        "files_modified": 0,
        "files_unchanged": 0,
        "skipped_no_frontmatter": 0,
        "images_rewritten": 0,
        "internal_links_rewritten": 0,
        "internal_links_unresolved": 0,
        "wpme_resolved": 0,
        "localhost_resolved": 0,
        "localhost_removed": 0,
        "unresolved_urls": set(),
    }

    session = requests.Session() if check_broken else None

    # Collect all files
    files = []
    for subdir in [POSTS_DIR / "en", POSTS_DIR / "es", PAGES_DIR / "en", PAGES_DIR / "es"]:
        if subdir.exists():
            files.extend(subdir.glob("*.html"))

    logger.info(f"Processing {len(files)} files...")

    for i, filepath in enumerate(sorted(files), 1):
        process_file(filepath, url_map, image_manifest, stats, check_broken, session)
        if i % 100 == 0:
            logger.info(f"Processed {i}/{len(files)} files...")

    # Convert set to list for JSON
    stats["unresolved_urls"] = sorted(stats["unresolved_urls"])
    return stats


def main():
    logger.info("=== Link Rewriting Script ===")

    url_map = load_url_map()
    image_manifest = load_image_manifest()

    logger.info(f"URL map entries: {len(url_map)}")
    logger.info(f"Image manifest entries: {len(image_manifest)}")

    stats = process_all_files(url_map, image_manifest, check_broken=False)

    # Write report
    with open(LINK_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info("=== Rewriting Complete ===")
    logger.info(f"Files modified: {stats['files_modified']}")
    logger.info(f"Files unchanged: {stats['files_unchanged']}")
    logger.info(f"Images rewritten: {stats['images_rewritten']}")
    logger.info(f"Internal links rewritten: {stats['internal_links_rewritten']}")
    logger.info(f"wp.me links resolved: {stats['wpme_resolved']}")
    logger.info(f"Localhost resolved: {stats['localhost_resolved']}")
    logger.info(f"Localhost removed: {stats['localhost_removed']}")
    logger.info(f"Unresolved internal: {stats['internal_links_unresolved']}")
    logger.info(f"Report: {LINK_REPORT_FILE}")

    if stats["unresolved_urls"]:
        logger.warning(f"Unresolved URLs ({len(stats['unresolved_urls'])}):")
        for url in stats["unresolved_urls"][:20]:
            logger.warning(f"  {url}")


if __name__ == "__main__":
    main()
