#!/usr/bin/env python3
"""Download external featured images from the Wayback Machine and update posts to use local paths."""
import os
import re
import time
import json
import urllib.request
import urllib.parse
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIRS = [os.path.join(BASE_DIR, '_posts', d) for d in ['en', 'es']]
IMAGES_DIR = os.path.join(BASE_DIR, 'assets', 'images', 'external')
CDX_API = 'http://web.archive.org/cdx/search/cdx'
WAYBACK_DL = 'https://web.archive.org/web'

def find_external_images():
    """Find all posts with external featured_image URLs. Returns {url: [filepath, ...]}."""
    external = {}
    for posts_dir in POSTS_DIRS:
        if not os.path.isdir(posts_dir):
            continue
        for fn in sorted(os.listdir(posts_dir)):
            if not fn.endswith('.html'):
                continue
            fp = os.path.join(posts_dir, fn)
            with open(fp, 'r', encoding='utf-8') as f:
                content = f.read()
            parts = content.split('---', 2)
            if len(parts) < 3:
                continue
            m = re.search(r'featured_image:\s*["\']([^"\']+)["\']', parts[1])
            if not m:
                continue
            img = m.group(1).strip()
            if img.startswith('http'):
                if img not in external:
                    external[img] = []
                external[img].append(fp)
    return external


def url_to_filename(url):
    """Derive a clean local filename from a URL path."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    # Get just the filename part
    basename = os.path.basename(path)
    # Decode percent-encoded characters
    basename = urllib.parse.unquote(basename)
    # Replace HTML entities like &amp; with actual characters
    basename = basename.replace('&amp;', '&')
    # Replace special/problematic characters for filesystem
    # Keep letters, digits, dots, hyphens, underscores
    clean = re.sub(r'[^\w.\-]', '_', basename)
    # Collapse multiple underscores
    clean = re.sub(r'_+', '_', clean)
    # Strip leading/trailing underscores
    clean = clean.strip('_')
    return clean


def download_from_wayback(url):
    """Try to download a URL from the Wayback Machine. Returns image bytes or None."""
    # Query CDX API for the latest snapshot
    query_url = f'{CDX_API}?url={urllib.parse.quote(url, safe="")}&output=json&limit=1'
    try:
        req = urllib.request.Request(query_url, headers={'User-Agent': 'Mozilla/5.0 (iloveepoetry image restore)'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f'  CDX query failed: {e}')
        return None

    if len(data) < 2:
        print(f'  No Wayback snapshot found')
        return None

    # data[0] is headers, data[1] is first result
    # Headers: ["urlkey","timestamp","original","mimetype","statuscode","digest","length"]
    row = data[1]
    timestamp = row[1]
    original = row[2]
    status = row[4]

    if status != '200':
        print(f'  Wayback snapshot has status {status}, trying anyway...')

    # Download the raw file (id_ modifier avoids Wayback wrapper)
    dl_url = f'{WAYBACK_DL}/{timestamp}id_/{original}'
    try:
        req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0 (iloveepoetry image restore)'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        print(f'  Download failed: {e}')
        return None


def update_posts(posts, old_url, new_path):
    """Update featured_image in all given post files from old_url to new_path."""
    count = 0
    for fp in posts:
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        # Replace the URL in the featured_image field
        # The URL may appear with single or double quotes
        new_content = content.replace(old_url, new_path)
        if new_content != content:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(new_content)
            count += 1
    return count


def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    external = find_external_images()
    total_urls = len(external)
    total_posts = sum(len(v) for v in external.values())
    print(f'Found {total_urls} unique external URLs across {total_posts} posts')
    print()

    successes = 0
    failures = 0
    failed_urls = []
    posts_updated = 0

    for i, (url, posts) in enumerate(sorted(external.items()), 1):
        filename = url_to_filename(url)
        local_path = os.path.join(IMAGES_DIR, filename)
        relative_path = f'/assets/images/external/{filename}'

        print(f'[{i}/{total_urls}] {url}')
        print(f'  -> {filename} ({len(posts)} posts)')

        # Check if already downloaded
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f'  Already downloaded, updating posts...')
            updated = update_posts(posts, url, relative_path)
            posts_updated += updated
            successes += 1
            print(f'  Updated {updated} posts')
            continue

        # Download from Wayback Machine
        img_data = download_from_wayback(url)
        if img_data:
            with open(local_path, 'wb') as f:
                f.write(img_data)
            print(f'  Downloaded {len(img_data)} bytes')

            updated = update_posts(posts, url, relative_path)
            posts_updated += updated
            successes += 1
            print(f'  Updated {updated} posts')
        else:
            failures += 1
            failed_urls.append(url)
            print(f'  FAILED')

        # Be polite: wait between downloads
        if i < total_urls:
            time.sleep(1)

    print()
    print('=' * 60)
    print(f'Summary:')
    print(f'  Total URLs: {total_urls}')
    print(f'  Successes: {successes}')
    print(f'  Failures: {failures}')
    print(f'  Posts updated: {posts_updated}')
    if failed_urls:
        print(f'\nFailed URLs:')
        for u in failed_urls:
            print(f'  - {u}')


if __name__ == '__main__':
    main()
