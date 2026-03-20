#!/usr/bin/env python3
"""
Download external media referenced in Jekyll post files and rewrite
references to point to local copies.

Scans _posts/en/*.html and _posts/es/*.html for:
  - <img src="..."> in post body HTML
  - featured_image in YAML front matter

Downloads images to local assets/images/ directories and rewrites
references in the post files. Uses Wayback Machine as fallback.
"""

import os
import re
import sys
import time
import hashlib
import logging
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIRS = [PROJECT_ROOT / "_posts" / "en", PROJECT_ROOT / "_posts" / "es"]
ASSETS_DIR = PROJECT_ROOT / "assets" / "images"

MAX_WORKERS = 10
TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY = 2

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Domains whose iframe/embed URLs should be left alone
EMBED_DOMAINS = {
    "youtube.com", "www.youtube.com", "youtu.be",
    "vimeo.com", "player.vimeo.com", "www.vimeo.com",
    "slideshare.net", "www.slideshare.net",
    "docs.google.com", "drive.google.com",
    "google.com", "www.google.com",
    "archive.org", "web.archive.org",
    "soundcloud.com", "www.soundcloud.com", "w.soundcloud.com",
    "bandcamp.com",
    "twitter.com", "www.twitter.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "flickr.com", "www.flickr.com",
    "vine.co",
    "maps.google.com",
    "scribd.com", "www.scribd.com",
    "issuu.com", "www.issuu.com",
    "ustream.tv", "www.ustream.tv",
    "livestream.com", "www.livestream.com",
    "prezi.com", "www.prezi.com",
    "storify.com", "www.storify.com",
    "padlet.com", "www.padlet.com",
}

# Skip these entirely — not downloadable image content
SKIP_DOMAINS = EMBED_DOMAINS | {
    "localhost", "127.0.0.1",
}

# Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


# ── URL → local path mapping ──────────────────────────────────────────────

def url_to_local_path(url: str) -> str | None:
    """
    Map an external URL to a local asset path (relative to project root,
    with leading /).
    Returns None if the URL should be skipped.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return None

    hostname_lower = hostname.lower()

    # Skip embed/localhost domains
    for skip_domain in SKIP_DOMAINS:
        if hostname_lower == skip_domain or hostname_lower.endswith("." + skip_domain):
            return None

    path = unquote(parsed.path).strip("/")
    if not path:
        return None

    filename = os.path.basename(path)
    if not filename:
        return None

    # academic.uprm.edu/flores/images/FILENAME → assets/images/uprm/FILENAME
    if hostname_lower == "academic.uprm.edu":
        return f"/assets/images/uprm/{filename}"

    # iloveepoetry.org/wp-content/uploads/YYYY/MM/FILENAME
    # → assets/images/wp-content/uploads/YYYY/MM/FILENAME
    if hostname_lower in ("iloveepoetry.org", "www.iloveepoetry.org", "iloveepoetry.com", "www.iloveepoetry.com"):
        # Extract wp-content/uploads/... path
        match = re.search(r'(wp-content/uploads/.+)', path)
        if match:
            return f"/assets/images/{match.group(1)}"
        # Other paths on iloveepoetry.org
        return f"/assets/images/external/iloveepoetry.org/{filename}"

    # elmcip.net → assets/images/external/elmcip/FILENAME
    if hostname_lower == "elmcip.net" or hostname_lower.endswith(".elmcip.net"):
        return f"/assets/images/external/elmcip/{filename}"

    # Other domains → assets/images/external/DOMAIN/FILENAME
    return f"/assets/images/external/{hostname_lower}/{filename}"


def local_path_to_disk(local_path: str) -> Path:
    """Convert a local URL path to an absolute disk path."""
    # local_path starts with /assets/images/...
    rel = local_path.lstrip("/")
    return PROJECT_ROOT / rel


# ── Extraction ─────────────────────────────────────────────────────────────

def split_front_matter(content: str):
    """
    Split Jekyll post content into (front_matter, body, first_delim, second_delim).
    Returns (front_matter_text, body_text) or (None, content) if no front matter.
    """
    # Match the YAML front matter between --- delimiters
    if not content.startswith("---"):
        return None, content

    # Find the second ---
    second_idx = content.index("---", 3)
    if second_idx < 0:
        return None, content

    front_matter = content[3:second_idx]
    body = content[second_idx + 3:]
    return front_matter, body


def extract_featured_image(front_matter: str) -> str | None:
    """Extract featured_image URL from YAML front matter text."""
    match = re.search(r'^featured_image:\s*["\']?(https?://[^\s"\']+)["\']?', front_matter, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def extract_img_src_urls(body: str) -> list[str]:
    """
    Extract all src URLs from <img> tags in the body HTML.
    Skip iframe/embed src attributes.
    """
    urls = []
    # Match img tags and extract src attribute
    for match in re.finditer(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', body, re.IGNORECASE):
        url = match.group(1)
        urls.append(url)
    return urls


def is_external_url(url: str) -> bool:
    """Check if a URL is an external http(s) URL."""
    return url.startswith("http://") or url.startswith("https://")


# ── Download logic ─────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def download_url(url: str, dest: Path) -> tuple[str, bool, str]:
    """
    Download a URL to dest path.
    Returns (url, success, message).
    Tries direct download first, then Wayback Machine.
    """
    if dest.exists() and dest.stat().st_size > 0:
        return (url, True, "already_exists")

    # Ensure directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Try direct download
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                # Basic check: skip HTML responses that aren't images
                if "text/html" in content_type and "image" not in content_type:
                    # Might be a redirect page or error page, try Wayback
                    break
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                if dest.stat().st_size > 0:
                    return (url, True, "downloaded")
                else:
                    dest.unlink(missing_ok=True)
                    break
            elif resp.status_code in (403, 404, 410, 500, 502, 503):
                break  # Don't retry, go to Wayback
        except (requests.RequestException, OSError) as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            break

    # Try Wayback Machine
    return download_from_wayback(url, dest)


def download_from_wayback(url: str, dest: Path) -> tuple[str, bool, str]:
    """
    Try to download a URL from the Wayback Machine.
    """
    try:
        cdx_url = (
            f"http://web.archive.org/cdx/search/cdx?"
            f"url={url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"
        )
        resp = session.get(cdx_url, timeout=TIMEOUT)
        if resp.status_code != 200:
            return (url, False, f"wayback_cdx_error_{resp.status_code}")

        data = resp.json()
        if len(data) < 2:
            return (url, False, "not_in_wayback")

        timestamp = data[1][0]
        original = data[1][1]
        wayback_url = f"https://web.archive.org/web/{timestamp}id_/{original}"

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp2 = session.get(wayback_url, timeout=TIMEOUT, stream=True, allow_redirects=True)
                if resp2.status_code == 200:
                    with open(dest, "wb") as f:
                        for chunk in resp2.iter_content(chunk_size=8192):
                            f.write(chunk)
                    if dest.stat().st_size > 0:
                        return (url, True, "downloaded_wayback")
                    else:
                        dest.unlink(missing_ok=True)
                break
            except (requests.RequestException, OSError):
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                break

        return (url, False, "wayback_download_failed")

    except Exception as e:
        return (url, False, f"wayback_error: {e}")


# ── Rewriting ──────────────────────────────────────────────────────────────

def rewrite_body_img_srcs(body: str, url_map: dict[str, str]) -> str:
    """
    Rewrite <img src="..."> in the body HTML.
    url_map: {original_url: new_local_path}
    Also handles /iloveepoetry/ prefixed local paths that should be rewritten.
    """
    def replace_img_src(match):
        full_match = match.group(0)
        src_url = match.group(1)

        # Check if this is a /iloveepoetry/assets/... path that needs rewriting
        if src_url.startswith("/iloveepoetry/assets/"):
            # Strip the /iloveepoetry prefix
            new_path = src_url.replace("/iloveepoetry/assets/", "/assets/", 1)
            return full_match.replace(src_url, new_path)

        if src_url in url_map:
            return full_match.replace(src_url, url_map[src_url])

        return full_match

    return re.sub(
        r'(<img\b[^>]*\bsrc\s*=\s*["\'])([^"\']+)(["\'])',
        lambda m: m.group(1) + _rewrite_single_src(m.group(2), url_map) + m.group(3),
        body,
        flags=re.IGNORECASE
    )


def _rewrite_single_src(src_url: str, url_map: dict[str, str]) -> str:
    """Rewrite a single src URL."""
    # Handle /iloveepoetry/assets/... prefix
    if src_url.startswith("/iloveepoetry/assets/"):
        return src_url.replace("/iloveepoetry/assets/", "/assets/", 1)

    if src_url in url_map:
        return url_map[src_url]

    return src_url


def rewrite_body_href_for_local_prefix(body: str) -> str:
    """
    Also fix href="/iloveepoetry/assets/..." → href="/assets/..."
    These are often wrapping <a> tags around images.
    """
    return body.replace('href="/iloveepoetry/assets/', 'href="/assets/')


def rewrite_featured_image(front_matter: str, url_map: dict[str, str]) -> str:
    """Rewrite featured_image in front matter."""
    def replace_fi(match):
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)

        if url in url_map:
            return f'{prefix}{url_map[url]}{suffix}'
        return match.group(0)

    return re.sub(
        r'(^featured_image:\s*["\']?)(https?://[^\s"\']+)(["\']?\s*$)',
        replace_fi,
        front_matter,
        flags=re.MULTILINE
    )


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("External Media Downloader for iloveepoetry Jekyll site")
    print("=" * 70)
    print(f"Project root: {PROJECT_ROOT}")
    print()

    # Step 1: Collect all post files
    post_files = []
    for posts_dir in POSTS_DIRS:
        if posts_dir.exists():
            for f in sorted(posts_dir.glob("*.html")):
                post_files.append(f)
    print(f"Found {len(post_files)} post files to scan")

    # Step 2: Extract all external URLs and build URL → local path map
    # Also track which files reference which URLs for rewriting
    url_to_local = {}           # {external_url: local_path}
    file_body_urls = {}         # {filepath: [external_urls_in_body]}
    file_featured_urls = {}     # {filepath: external_url_or_None}
    files_needing_prefix_fix = set()  # files with /iloveepoetry/assets/ prefix

    total_body_refs = 0
    total_featured_refs = 0
    domain_counts = defaultdict(int)

    for fpath in post_files:
        content = fpath.read_text(encoding="utf-8")

        if not content.startswith("---"):
            continue

        front_matter, body = split_front_matter(content)
        if front_matter is None:
            continue

        # Check for /iloveepoetry/assets/ prefix in body
        if "/iloveepoetry/assets/" in body:
            files_needing_prefix_fix.add(fpath)

        # Extract featured_image
        fi_url = extract_featured_image(front_matter)
        if fi_url and is_external_url(fi_url):
            local_path = url_to_local_path(fi_url)
            if local_path:
                url_to_local[fi_url] = local_path
                file_featured_urls[fpath] = fi_url
                total_featured_refs += 1
                domain = urlparse(fi_url).hostname
                domain_counts[domain] += 1

        # Extract body img srcs
        body_urls = []
        for url in extract_img_src_urls(body):
            if is_external_url(url):
                local_path = url_to_local_path(url)
                if local_path:
                    url_to_local[url] = local_path
                    body_urls.append(url)
                    total_body_refs += 1
                    domain = urlparse(url).hostname
                    domain_counts[domain] += 1

        if body_urls:
            file_body_urls[fpath] = body_urls

    unique_urls = set(url_to_local.keys())
    print(f"\nExtracted {total_body_refs} body image references")
    print(f"Extracted {total_featured_refs} featured_image references")
    print(f"Unique external URLs to download: {len(unique_urls)}")
    print(f"Files with /iloveepoetry/assets/ prefix to fix: {len(files_needing_prefix_fix)}")
    print()

    print("Domain breakdown:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count} references")
    print()

    # Step 3: Check which already exist locally
    already_exist = 0
    to_download = []
    for url, local_path in url_to_local.items():
        disk_path = local_path_to_disk(local_path)
        if disk_path.exists() and disk_path.stat().st_size > 0:
            already_exist += 1
        else:
            to_download.append((url, disk_path))

    print(f"Already exist locally: {already_exist}")
    print(f"Need to download: {len(to_download)}")
    print()

    # Step 4: Download with thread pool
    downloaded = 0
    downloaded_wayback = 0
    failed = 0
    failed_urls = []

    if to_download:
        print(f"Downloading {len(to_download)} files with {MAX_WORKERS} threads...")
        print()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_url, url, dest): url
                for url, dest in to_download
            }

            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                url, success, message = future.result()
                if success:
                    if message == "downloaded":
                        downloaded += 1
                        log.info(f"[{done_count}/{len(to_download)}] Downloaded: {url}")
                    elif message == "downloaded_wayback":
                        downloaded_wayback += 1
                        log.info(f"[{done_count}/{len(to_download)}] Wayback: {url}")
                    elif message == "already_exists":
                        already_exist += 1
                        # Race condition: another thread may have downloaded it
                else:
                    failed += 1
                    failed_urls.append((url, message))
                    log.warning(f"[{done_count}/{len(to_download)}] FAILED ({message}): {url}")

    # Step 5: Build final rewrite map — only include URLs that were
    # successfully downloaded (or already existed)
    successful_url_map = {}
    for url, local_path in url_to_local.items():
        disk_path = local_path_to_disk(local_path)
        if disk_path.exists() and disk_path.stat().st_size > 0:
            successful_url_map[url] = local_path

    # Step 6: Rewrite post files
    print()
    print("Rewriting post files...")

    files_rewritten = 0
    body_refs_rewritten = 0
    featured_refs_rewritten = 0
    prefix_fixes = 0

    for fpath in post_files:
        content = fpath.read_text(encoding="utf-8")
        original_content = content

        if not content.startswith("---"):
            continue

        front_matter, body = split_front_matter(content)
        if front_matter is None:
            continue

        modified = False

        # Rewrite featured_image
        if fpath in file_featured_urls:
            fi_url = file_featured_urls[fpath]
            if fi_url in successful_url_map:
                new_fm = rewrite_featured_image(front_matter, successful_url_map)
                if new_fm != front_matter:
                    front_matter = new_fm
                    featured_refs_rewritten += 1
                    modified = True

        # Rewrite body img srcs
        new_body = rewrite_body_img_srcs(body, successful_url_map)

        # Fix /iloveepoetry/assets/ prefix in href
        new_body = rewrite_body_href_for_local_prefix(new_body)

        if new_body != body:
            # Count actual replacements
            old_ext_count = len([u for u in extract_img_src_urls(body) if is_external_url(u) and u in successful_url_map])
            # Count prefix fixes
            old_prefix_count = body.count("/iloveepoetry/assets/")
            new_prefix_count = new_body.count("/iloveepoetry/assets/")
            prefix_fixes_this = old_prefix_count - new_prefix_count

            body_refs_rewritten += old_ext_count
            prefix_fixes += prefix_fixes_this
            body = new_body
            modified = True

        if modified:
            new_content = f"---{front_matter}---{body}"
            if new_content != original_content:
                fpath.write_text(new_content, encoding="utf-8")
                files_rewritten += 1

    # ── Summary ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Post files scanned:          {len(post_files)}")
    print(f"Unique external URLs found:  {len(unique_urls)}")
    print()
    print(f"Downloads:")
    print(f"  Already existed locally:   {already_exist}")
    print(f"  Downloaded (direct):       {downloaded}")
    print(f"  Downloaded (Wayback):      {downloaded_wayback}")
    print(f"  Failed:                    {failed}")
    print(f"  Total successful:          {already_exist + downloaded + downloaded_wayback}")
    print()
    print(f"Rewrites:")
    print(f"  Files modified:            {files_rewritten}")
    print(f"  Body img src rewritten:    {body_refs_rewritten}")
    print(f"  Featured image rewritten:  {featured_refs_rewritten}")
    print(f"  /iloveepoetry/ prefix fix: {prefix_fixes}")
    print(f"  Total refs rewritten:      {body_refs_rewritten + featured_refs_rewritten + prefix_fixes}")
    print()

    if failed_urls:
        print(f"Failed downloads ({len(failed_urls)}):")
        for url, msg in sorted(failed_urls):
            print(f"  {msg}: {url}")
        print()

    print("Done!")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
