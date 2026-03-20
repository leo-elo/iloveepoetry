#!/usr/bin/env python3
"""
fix_remaining_images.py

Scans all Jekyll posts for remaining external image URLs and attempts to
resolve them to local files by:
1. Stripping WordPress thumbnail suffixes (e.g. -300x200) and matching to local full-size images
2. Matching UPRM images to local copies in assets/images/uprm/
3. Matching other external URLs by filename to existing local files
4. Downloading missing files (direct + Wayback Machine fallback)
"""

import os
import re
import sys
import time
import json
import hashlib
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# === Configuration ===
SITE_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIRS = [SITE_ROOT / "_posts" / "en", SITE_ROOT / "_posts" / "es"]
IMAGES_DIR = SITE_ROOT / "assets" / "images"
WP_UPLOADS_DIR = IMAGES_DIR / "wp-content" / "uploads"
UPRM_DIR = IMAGES_DIR / "uprm"
DOWNLOAD_DIR_WP = WP_UPLOADS_DIR  # Downloads go into the WP uploads tree
DOWNLOAD_DIR_UPRM = UPRM_DIR
DOWNLOAD_DIR_OTHER = IMAGES_DIR / "external"

MAX_WORKERS = 5
DOWNLOAD_TIMEOUT = 15

# WordPress thumbnail suffix pattern: -NNNxNNN before extension
WP_THUMB_RE = re.compile(r'-\d+x\d+(?=\.\w+$)')

# Patterns to skip (embeds, not images)
SKIP_URL_PATTERNS = [
    'youtube.com', 'youtu.be', 'vimeo.com', 'player.vimeo',
    'dailymotion.com', 'soundcloud.com', 'bandcamp.com',
    'google.com/forms', 'docs.google.com/forms',
    'scribd.com/embeds', 'issuu.com',
]

# Regex for external URLs in img src and featured_image
IMG_SRC_RE = re.compile(r'(<img[^>]*\ssrc=")([^"]+)(")')
FEATURED_IMG_RE = re.compile(r'^(featured_image:\s*")(https?://[^"]+)(")', re.MULTILINE)

# Wayback CDX API
WAYBACK_CDX_URL = "http://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"


def build_local_inventory():
    """Build a dict of filename -> list of local paths (relative to assets/images/)."""
    inventory = {}
    inventory_by_path = {}
    for root, dirs, files in os.walk(IMAGES_DIR):
        for f in files:
            full_path = Path(root) / f
            rel_path = full_path.relative_to(SITE_ROOT)
            local_url = "/" + str(rel_path)
            fname_lower = f.lower()
            if fname_lower not in inventory:
                inventory[fname_lower] = []
            inventory[fname_lower].append(local_url)
            # Also index by the relative path from a known structure
            inventory_by_path[local_url.lower()] = local_url
    return inventory, inventory_by_path


def should_skip_url(url):
    """Check if URL should be skipped (embeds, etc.)."""
    url_lower = url.lower()
    for pattern in SKIP_URL_PATTERNS:
        if pattern in url_lower:
            return True
    return False


def strip_wp_thumbnail_suffix(filename):
    """Strip WordPress thumbnail suffix from filename.
    e.g. 'euclid-300x296.png' -> 'euclid.png'
    """
    return WP_THUMB_RE.sub('', filename)


def parse_wp_upload_path(url):
    """Extract the /wp-content/uploads/YYYY/MM/filename part from a WP URL."""
    match = re.search(r'/wp-content/uploads/(\d{4}/\d{2}/[^/?#]+)', url)
    if match:
        return match.group(1)
    return None


def parse_uprm_filename(url):
    """Extract filename from a UPRM URL like academic.uprm.edu/flores/images/file.png."""
    match = re.search(r'academic\.uprm\.edu/flores/images/([^/?#]+)', url)
    if match:
        return match.group(1)
    return None


def extract_filename_from_url(url):
    """Extract just the filename from a URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if path:
        return os.path.basename(path)
    return None


def download_file(url, dest_path, timeout=DOWNLOAD_TIMEOUT):
    """Download a file from a URL to dest_path. Returns True on success."""
    try:
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) iloveepoetry-image-fixer/1.0'
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            if len(data) < 100:
                return False
            with open(dest_path, 'wb') as f:
                f.write(data)
            return True
    except Exception as e:
        return False


def try_wayback_download(original_url, dest_path):
    """Try to download from Wayback Machine. Returns True on success."""
    try:
        cdx_url = WAYBACK_CDX_URL.format(url=urllib.parse.quote(original_url, safe=''))
        req = urllib.request.Request(cdx_url, headers={
            'User-Agent': 'Mozilla/5.0 iloveepoetry-image-fixer/1.0'
        })
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))
        if len(data) < 2:
            return False
        timestamp = data[1][0]
        orig = data[1][1]
        wayback_url = f"http://web.archive.org/web/{timestamp}id_/{orig}"
        return download_file(wayback_url, dest_path)
    except Exception:
        return False


def resolve_wp_url(url, inventory, inventory_by_path):
    """
    Resolve a WP iloveepoetry.org URL to a local path.
    Returns (local_path, action_taken) or (None, reason).
    """
    wp_path = parse_wp_upload_path(url)
    if not wp_path:
        return None, "no_wp_path"

    filename = os.path.basename(wp_path)
    dir_part = os.path.dirname(wp_path)  # YYYY/MM

    # Check if this exact file (thumbnail) is already local
    exact_local = f"/assets/images/wp-content/uploads/{wp_path}"
    if exact_local.lower() in inventory_by_path:
        return inventory_by_path[exact_local.lower()], "exact_match"

    # Strip thumbnail suffix and check for full-size version
    base_filename = strip_wp_thumbnail_suffix(filename)
    if base_filename != filename:
        base_local = f"/assets/images/wp-content/uploads/{dir_part}/{base_filename}"
        if base_local.lower() in inventory_by_path:
            return inventory_by_path[base_local.lower()], "thumb_to_fullsize"

    # Try to download the full-size version
    if base_filename != filename:
        # Build the full-size URL
        full_url = re.sub(r'/wp-content/uploads/' + re.escape(wp_path),
                          f'/wp-content/uploads/{dir_part}/{base_filename}', url)
        dest = DOWNLOAD_DIR_WP / dir_part / base_filename
        if download_file(full_url, dest):
            local_path = f"/assets/images/wp-content/uploads/{dir_part}/{base_filename}"
            return local_path, "downloaded_fullsize"

        # Try Wayback for full-size
        if try_wayback_download(full_url, dest):
            local_path = f"/assets/images/wp-content/uploads/{dir_part}/{base_filename}"
            return local_path, "wayback_fullsize"

    # Try to download the exact (thumbnail) URL
    dest = DOWNLOAD_DIR_WP / wp_path
    if download_file(url, dest):
        local_path = f"/assets/images/wp-content/uploads/{wp_path}"
        return local_path, "downloaded_exact"

    # Try Wayback for exact URL
    if try_wayback_download(url, dest):
        local_path = f"/assets/images/wp-content/uploads/{wp_path}"
        return local_path, "wayback_exact"

    return None, "wp_not_found"


def resolve_uprm_url(url, inventory, inventory_by_path):
    """
    Resolve a UPRM URL to a local path.
    Returns (local_path, action_taken) or (None, reason).
    """
    filename = parse_uprm_filename(url)
    if not filename:
        return None, "no_uprm_filename"

    # Check if already in uprm directory
    local_path = f"/assets/images/uprm/{filename}"
    if local_path.lower() in inventory_by_path:
        return inventory_by_path[local_path.lower()], "uprm_exact_match"

    # Check inventory by filename
    fname_lower = filename.lower()
    if fname_lower in inventory:
        # Prefer the uprm directory match
        for p in inventory[fname_lower]:
            if '/uprm/' in p:
                return p, "uprm_inventory_match"
        return inventory[fname_lower][0], "inventory_match"

    # Try to download
    dest = UPRM_DIR / filename
    if download_file(url, dest):
        return f"/assets/images/uprm/{filename}", "downloaded"

    # Try Wayback
    if try_wayback_download(url, dest):
        return f"/assets/images/uprm/{filename}", "wayback"

    return None, "uprm_not_found"


def resolve_other_url(url, inventory, inventory_by_path):
    """
    Resolve any other external URL by filename matching.
    Returns (local_path, action_taken) or (None, reason).
    """
    filename = extract_filename_from_url(url)
    if not filename:
        return None, "no_filename"

    fname_lower = filename.lower()

    # Check if we already have it by exact filename
    if fname_lower in inventory:
        return inventory[fname_lower][0], "filename_match"

    # Check in the 'other' and 'external' directories by URL structure
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    url_path = parsed.path.lstrip("/")

    # Check if file exists in other/{host}/{path} structure
    other_path = f"/assets/images/other/{host}/{url_path}"
    if other_path.lower() in inventory_by_path:
        return inventory_by_path[other_path.lower()], "other_path_match"

    external_path = f"/assets/images/external/{host}/{url_path}"
    if external_path.lower() in inventory_by_path:
        return inventory_by_path[external_path.lower()], "external_path_match"

    # Try to download to other/{host}/
    dest_dir = IMAGES_DIR / "other" / host
    dest = dest_dir / filename
    if download_file(url, dest):
        return f"/assets/images/other/{host}/{filename}", "downloaded"

    # Try Wayback
    if try_wayback_download(url, dest):
        return f"/assets/images/other/{host}/{filename}", "wayback"

    return None, "other_not_found"


def find_external_urls_in_post(content):
    """Find all external image URLs in a post (both img src and featured_image)."""
    urls = []

    # Find img src URLs
    for match in IMG_SRC_RE.finditer(content):
        url = match.group(2)
        if url.startswith('http') and not should_skip_url(url):
            urls.append(('img_src', url, match))

    # Find featured_image URLs
    for match in FEATURED_IMG_RE.finditer(content):
        url = match.group(2)
        if url.startswith('http') and not should_skip_url(url):
            urls.append(('featured_image', url, match))

    return urls


def classify_url(url):
    """Classify a URL into wp, uprm, or other."""
    url_lower = url.lower()
    if 'iloveepoetry.org/wp-content/uploads/' in url_lower or \
       'iloveepoetry.com/wp-content/uploads/' in url_lower:
        return 'wp'
    elif 'academic.uprm.edu' in url_lower:
        return 'uprm'
    else:
        return 'other'


def resolve_url(url, inventory, inventory_by_path):
    """Resolve a single external URL to a local path."""
    url_type = classify_url(url)
    if url_type == 'wp':
        return resolve_wp_url(url, inventory, inventory_by_path)
    elif url_type == 'uprm':
        return resolve_uprm_url(url, inventory, inventory_by_path)
    else:
        return resolve_other_url(url, inventory, inventory_by_path)


def collect_all_external_urls(posts_data):
    """Collect all unique external URLs from all posts."""
    all_urls = set()
    for filepath, content in posts_data:
        for url_type, url, match in find_external_urls_in_post(content):
            all_urls.add(url)
    return all_urls


def main():
    print("=" * 70)
    print("Fix Remaining External Image URLs")
    print("=" * 70)

    # Step 1: Build local inventory
    print("\n[1/5] Building local image inventory...")
    inventory, inventory_by_path = build_local_inventory()
    total_local = sum(len(v) for v in inventory.values())
    print(f"  Found {total_local} local image files across {len(inventory)} unique filenames")

    # Step 2: Scan all posts
    print("\n[2/5] Scanning posts for external image URLs...")
    posts_data = []
    for posts_dir in POSTS_DIRS:
        if not posts_dir.exists():
            print(f"  WARNING: {posts_dir} does not exist, skipping")
            continue
        for html_file in sorted(posts_dir.glob("*.html")):
            content = html_file.read_text(encoding='utf-8')
            posts_data.append((html_file, content))

    print(f"  Scanned {len(posts_data)} posts")

    # Step 3: Collect all unique external URLs
    all_urls = collect_all_external_urls(posts_data)
    print(f"  Found {len(all_urls)} unique external image URLs")

    # Classify them
    wp_urls = [u for u in all_urls if classify_url(u) == 'wp']
    uprm_urls = [u for u in all_urls if classify_url(u) == 'uprm']
    other_urls = [u for u in all_urls if classify_url(u) == 'other']
    print(f"    - WordPress (iloveepoetry.org): {len(wp_urls)}")
    print(f"    - UPRM (academic.uprm.edu): {len(uprm_urls)}")
    print(f"    - Other external: {len(other_urls)}")

    # Step 4: Resolve all URLs (with threading for downloads)
    print("\n[3/5] Resolving external URLs to local paths...")
    resolutions = {}  # url -> (local_path, action)
    urls_to_download = []

    # First pass: try local matching (no network)
    for url in all_urls:
        url_type = classify_url(url)
        if url_type == 'wp':
            wp_path = parse_wp_upload_path(url)
            if wp_path:
                filename = os.path.basename(wp_path)
                dir_part = os.path.dirname(wp_path)
                exact_local = f"/assets/images/wp-content/uploads/{wp_path}"
                if exact_local.lower() in inventory_by_path:
                    resolutions[url] = (inventory_by_path[exact_local.lower()], "exact_match")
                    continue
                base_filename = strip_wp_thumbnail_suffix(filename)
                if base_filename != filename:
                    base_local = f"/assets/images/wp-content/uploads/{dir_part}/{base_filename}"
                    if base_local.lower() in inventory_by_path:
                        resolutions[url] = (inventory_by_path[base_local.lower()], "thumb_to_fullsize")
                        continue
            urls_to_download.append(url)

        elif url_type == 'uprm':
            filename = parse_uprm_filename(url)
            if filename:
                local_path = f"/assets/images/uprm/{filename}"
                if local_path.lower() in inventory_by_path:
                    resolutions[url] = (inventory_by_path[local_path.lower()], "uprm_exact_match")
                    continue
                fname_lower = filename.lower()
                if fname_lower in inventory:
                    for p in inventory[fname_lower]:
                        if '/uprm/' in p:
                            resolutions[url] = (p, "uprm_inventory_match")
                            break
                    else:
                        resolutions[url] = (inventory[fname_lower][0], "inventory_match")
                    continue
            urls_to_download.append(url)

        else:
            filename = extract_filename_from_url(url)
            if filename:
                fname_lower = filename.lower()
                if fname_lower in inventory:
                    resolutions[url] = (inventory[fname_lower][0], "filename_match")
                    continue
                parsed = urllib.parse.urlparse(url)
                host = parsed.hostname or ""
                url_path = parsed.path.lstrip("/")
                other_path = f"/assets/images/other/{host}/{url_path}"
                if other_path.lower() in inventory_by_path:
                    resolutions[url] = (inventory_by_path[other_path.lower()], "other_path_match")
                    continue
                external_path = f"/assets/images/external/{host}/{url_path}"
                if external_path.lower() in inventory_by_path:
                    resolutions[url] = (inventory_by_path[external_path.lower()], "external_path_match")
                    continue
            urls_to_download.append(url)

    locally_matched = len(resolutions)
    print(f"  Locally matched: {locally_matched}")
    print(f"  Need download attempt: {len(urls_to_download)}")

    # Second pass: download with threading
    if urls_to_download:
        print(f"\n[4/5] Attempting to download {len(urls_to_download)} remaining images...")
        download_results = {"downloaded": 0, "wayback": 0, "failed": 0}

        def try_resolve(url):
            return url, resolve_url(url, inventory, inventory_by_path)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(try_resolve, url): url for url in urls_to_download}
            for i, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    url_result, (local_path, action) = future.result()
                    if local_path:
                        resolutions[url_result] = (local_path, action)
                        if 'wayback' in action:
                            download_results["wayback"] += 1
                        elif 'downloaded' in action:
                            download_results["downloaded"] += 1
                    else:
                        download_results["failed"] += 1
                        resolutions[url_result] = (None, action)
                except Exception as e:
                    download_results["failed"] += 1
                    resolutions[url] = (None, f"error: {e}")

                if i % 10 == 0 or i == len(urls_to_download):
                    print(f"    Progress: {i}/{len(urls_to_download)}")

        print(f"  Direct downloads: {download_results['downloaded']}")
        print(f"  Wayback downloads: {download_results['wayback']}")
        print(f"  Failed: {download_results['failed']}")
    else:
        print("\n[4/5] No downloads needed.")

    # Step 5: Rewrite posts
    print("\n[5/5] Rewriting posts...")
    files_modified = 0
    total_replacements = 0
    failed_urls = {}  # url -> count

    for filepath, original_content in posts_data:
        content = original_content
        modified = False

        # Process featured_image in front matter
        def replace_featured(match):
            nonlocal modified
            prefix = match.group(1)
            url = match.group(2)
            suffix = match.group(3)
            if url in resolutions and resolutions[url][0]:
                modified = True
                return prefix + resolutions[url][0] + suffix
            return match.group(0)

        # Split front matter and body
        parts = content.split('---', 2)
        if len(parts) >= 3:
            front_matter = parts[1]
            body = parts[2]

            # Replace featured_image in front matter
            new_front_matter = FEATURED_IMG_RE.sub(replace_featured, front_matter)

            # Replace img src in body
            def replace_img_src(match):
                nonlocal modified
                prefix = match.group(1)
                url = match.group(2)
                suffix = match.group(3)
                if url.startswith('http') and not should_skip_url(url):
                    if url in resolutions and resolutions[url][0]:
                        modified = True
                        return prefix + resolutions[url][0] + suffix
                return match.group(0)

            new_body = IMG_SRC_RE.sub(replace_img_src, body)
            new_content = '---' + new_front_matter + '---' + new_body
        else:
            new_content = content

        if modified:
            filepath.write_text(new_content, encoding='utf-8')
            files_modified += 1
            # Count replacements
            replacements = sum(1 for a, b in zip(
                re.findall(r'(?:src="|featured_image:\s*")[^"]+', original_content),
                re.findall(r'(?:src="|featured_image:\s*")[^"]+', new_content)
            ) if a != b)
            total_replacements += replacements

    # Count remaining external URLs
    remaining_external = {}
    for url, (local_path, action) in resolutions.items():
        if local_path is None:
            url_type = classify_url(url)
            if url_type not in remaining_external:
                remaining_external[url_type] = []
            remaining_external[url_type].append(url)

    # === Summary ===
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    resolved_count = sum(1 for url, (lp, act) in resolutions.items() if lp is not None)
    unresolved_count = sum(1 for url, (lp, act) in resolutions.items() if lp is None)

    print(f"\nTotal unique external URLs found: {len(all_urls)}")
    print(f"Resolved to local paths: {resolved_count}")
    print(f"Unresolved (still external): {unresolved_count}")
    print(f"\nFiles modified: {files_modified}")
    print(f"Total URL replacements in posts: {total_replacements}")

    # Breakdown by resolution method
    methods = {}
    for url, (lp, act) in resolutions.items():
        if lp is not None:
            methods[act] = methods.get(act, 0) + 1
    if methods:
        print("\nResolution methods:")
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            print(f"  {method}: {count}")

    # Show remaining external URLs
    if unresolved_count > 0:
        print(f"\nRemaining unresolved external URLs ({unresolved_count}):")
        for url_type, urls in sorted(remaining_external.items()):
            print(f"\n  [{url_type}] ({len(urls)} URLs):")
            for url in sorted(urls)[:15]:
                print(f"    - {url}")
            if len(urls) > 15:
                print(f"    ... and {len(urls) - 15} more")

    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == '__main__':
    main()
