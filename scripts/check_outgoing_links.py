#!/usr/bin/env python3
"""
check_outgoing_links.py

Scans all HTML files in _posts/en, _posts/es, _pages/en, _pages/es for outgoing
external links in the body content (not YAML front matter). Checks each unique URL
for liveness, looks up Wayback Machine archives for dead links, and replaces dead
URLs with archived versions where available.
"""

import os
import re
import json
import html
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# =============================================================================
# Configuration
# =============================================================================
BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"
SCAN_DIRS = [
    os.path.join(BASE_DIR, "_posts", "en"),
    os.path.join(BASE_DIR, "_posts", "es"),
    os.path.join(BASE_DIR, "_pages", "en"),
    os.path.join(BASE_DIR, "_pages", "es"),
]
RESULTS_FILE = os.path.join(BASE_DIR, "scripts", "link_check_results.json")

MAX_WORKERS = 15
REQUEST_TIMEOUT = 15
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

ALIVE_CODES = {200, 201, 202, 203, 204, 301, 302, 303, 307, 308, 403, 405, 429}

SKIP_DOMAINS = {"iloveepoetry.org", "web.archive.org", "elmcip.net"}

# =============================================================================
# Helpers
# =============================================================================

def split_front_matter(content):
    """Split YAML front matter from body content."""
    match = re.match(r'^(---\s*\n.*?\n---\s*\n)(.*)', content, re.DOTALL)
    if match:
        return match.group(1), match.group(2)
    return '', content


def extract_links_from_body(body):
    """Extract all href values from <a> tags in the body HTML."""
    pattern = re.compile(r'<a\s[^>]*?href\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s>]+))', re.IGNORECASE)
    links = []
    for m in pattern.finditer(body):
        url = m.group(1) if m.group(1) is not None else (m.group(2) if m.group(2) is not None else m.group(3))
        if url is not None:
            url = html.unescape(url).strip()
            links.append(url)
    return links


def is_external_link(url):
    """Return True if the URL is an external link that should be checked."""
    if not url or not url.strip():
        return False
    url_lower = url.strip().lower()
    if url_lower.startswith('/iloveepoetry/'):
        return False
    if url_lower.startswith('#'):
        return False
    if url_lower.startswith('mailto:'):
        return False
    if url_lower.startswith('javascript:'):
        return False
    if not (url_lower.startswith('http://') or url_lower.startswith('https://')):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.hostname
        if domain:
            domain = domain.lower()
            for skip in SKIP_DOMAINS:
                if domain == skip or domain.endswith('.' + skip):
                    return False
    except Exception:
        pass
    return True


def check_url(url):
    """Check if a URL is alive. Returns (url, alive: bool, status_code_or_error: str)."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.max_redirects = MAX_REDIRECTS
    try:
        resp = session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False)
        if resp.status_code in ALIVE_CODES:
            return (url, True, str(resp.status_code))
        # HEAD gave non-alive code, try GET as fallback
        resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True, verify=False, stream=True)
        resp.close()
        if resp.status_code in ALIVE_CODES:
            return (url, True, str(resp.status_code))
        return (url, False, str(resp.status_code))
    except requests.exceptions.SSLError:
        return (url, False, "SSLError")
    except requests.exceptions.ConnectionError as e:
        return (url, False, f"ConnectionError: {str(e)[:100]}")
    except requests.exceptions.Timeout:
        return (url, False, "Timeout")
    except requests.exceptions.TooManyRedirects:
        return (url, False, "TooManyRedirects")
    except Exception as e:
        return (url, False, f"Error: {str(e)[:100]}")
    finally:
        session.close()


def lookup_wayback(url):
    """Look up a Wayback Machine archived version of the URL."""
    cdx_url = (
        f"http://web.archive.org/cdx/search/cdx"
        f"?url={urllib.parse.quote(url, safe='')}"
        f"&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"
    )
    try:
        resp = requests.get(cdx_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if len(data) > 1:
                timestamp = data[1][0]
                original = data[1][1]
                return f"https://web.archive.org/web/{timestamp}/{original}"
    except Exception:
        pass
    return None


def replace_url_in_file(filepath, old_url, new_url, content=None):
    """Replace a URL within href attributes in a file's content."""
    if content is None:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

    old_escaped = html.escape(old_url, quote=False)
    modified = False
    new_content = content

    for old_variant in set([old_url, old_escaped]):
        # Double-quoted href
        pattern = re.compile(
            r'(href\s*=\s*")' + re.escape(old_variant) + r'(")',
            re.IGNORECASE
        )
        new_content_candidate = pattern.sub(r'\g<1>' + new_url.replace('\\', '\\\\') + r'\2', new_content)
        if new_content_candidate != new_content:
            new_content = new_content_candidate
            modified = True

        # Single-quoted href
        pattern = re.compile(
            r"(href\s*=\s*')" + re.escape(old_variant) + r"(')",
            re.IGNORECASE
        )
        new_content_candidate = pattern.sub(r'\g<1>' + new_url.replace('\\', '\\\\') + r'\2', new_content)
        if new_content_candidate != new_content:
            new_content = new_content_candidate
            modified = True

    if modified:
        return new_content
    return None


# =============================================================================
# Main
# =============================================================================

def main():
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    print("=" * 70)
    print("OUTGOING LINK CHECKER")
    print("=" * 70)

    # Step 1: Scan files and extract links
    print("\n[1/6] Scanning HTML files for external links...")
    url_to_files = {}
    total_files = 0
    total_links_found = 0

    for scan_dir in SCAN_DIRS:
        if not os.path.isdir(scan_dir):
            print(f"  WARNING: Directory does not exist: {scan_dir}")
            continue
        for filename in sorted(os.listdir(scan_dir)):
            if not filename.endswith('.html'):
                continue
            filepath = os.path.join(scan_dir, filename)
            total_files += 1
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            front_matter, body = split_front_matter(content)
            links = extract_links_from_body(body)
            for link in links:
                if is_external_link(link):
                    total_links_found += 1
                    if link not in url_to_files:
                        url_to_files[link] = set()
                    url_to_files[link].add(filepath)

    unique_urls = list(url_to_files.keys())
    print(f"  Scanned {total_files} HTML files")
    print(f"  Found {total_links_found} external link references")
    print(f"  {len(unique_urls)} unique external URLs")

    # Step 2: Check URLs for liveness
    print(f"\n[2/6] Checking {len(unique_urls)} unique URLs for liveness...")
    alive_urls = {}
    dead_urls = {}

    checked = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(check_url, url): url for url in unique_urls}
        for future in as_completed(future_to_url):
            url, is_alive, status = future.result()
            if is_alive:
                alive_urls[url] = status
            else:
                dead_urls[url] = status
            checked += 1
            if checked % 50 == 0 or checked == len(unique_urls):
                elapsed = time.time() - start_time
                print(f"  Checked {checked}/{len(unique_urls)} URLs ({elapsed:.1f}s elapsed) -- "
                      f"{len(alive_urls)} alive, {len(dead_urls)} dead so far")

    print(f"\n  Results: {len(alive_urls)} alive, {len(dead_urls)} dead")

    # Step 3: Look up Wayback Machine for dead URLs
    print(f"\n[3/6] Looking up Wayback Machine archives for {len(dead_urls)} dead URLs...")
    wayback_map = {}
    no_archive = {}

    wb_checked = 0
    for url, error in dead_urls.items():
        wb_checked += 1
        if wb_checked % 10 == 0:
            print(f"  Wayback lookup {wb_checked}/{len(dead_urls)}...")
        archive_url = lookup_wayback(url)
        if archive_url:
            wayback_map[url] = archive_url
        else:
            no_archive[url] = error

    print(f"  Found {len(wayback_map)} Wayback Machine archives")
    print(f"  {len(no_archive)} URLs have no archive")

    # Step 4: Save results to JSON
    print(f"\n[4/6] Saving results to {RESULTS_FILE}...")
    results = {
        "total_files_scanned": total_files,
        "total_link_references": total_links_found,
        "total_unique_urls": len(unique_urls),
        "alive_count": len(alive_urls),
        "dead_count": len(dead_urls),
        "fixed_via_wayback": len(wayback_map),
        "unfixable_count": len(no_archive),
        "alive_urls": {u: s for u, s in sorted(alive_urls.items())},
        "dead_urls_fixed": {u: {"wayback": wb, "files": sorted(url_to_files[u])}
                           for u, wb in sorted(wayback_map.items())},
        "dead_urls_unfixable": {u: {"error": no_archive[u], "files": sorted(url_to_files[u])}
                                for u in sorted(no_archive.keys())},
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("  Saved.")

    # Step 5: Replace dead URLs with Wayback Machine URLs
    print(f"\n[5/6] Replacing {len(wayback_map)} dead URLs with Wayback Machine archives...")
    files_modified = set()
    replacements_made = 0

    file_replacements = {}
    for old_url, new_url in wayback_map.items():
        for filepath in url_to_files[old_url]:
            if filepath not in file_replacements:
                file_replacements[filepath] = []
            file_replacements[filepath].append((old_url, new_url))

    for filepath, replacements in file_replacements.items():
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        original_content = content
        for old_url, new_url in replacements:
            result = replace_url_in_file(filepath, old_url, new_url, content)
            if result is not None:
                content = result
                replacements_made += 1
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            files_modified.add(filepath)

    print(f"  Made {replacements_made} URL replacements across {len(files_modified)} files")

    # Step 6: Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total files scanned:          {total_files}")
    print(f"  Total external link refs:     {total_links_found}")
    print(f"  Total unique external URLs:   {len(unique_urls)}")
    print(f"  URLs checked:                 {checked}")
    print(f"  Alive:                        {len(alive_urls)}")
    print(f"  Dead:                         {len(dead_urls)}")
    print(f"  Fixed via Wayback Machine:    {len(wayback_map)}")
    print(f"  Unfixable (no archive):       {len(no_archive)}")
    print(f"  Total files modified:         {len(files_modified)}")

    if wayback_map:
        print(f"\n--- FIXED URLs (replaced with Wayback Machine archives) ---")
        for old_url, new_url in sorted(wayback_map.items()):
            file_list = sorted(url_to_files[old_url])
            print(f"\n  DEAD:    {old_url}")
            print(f"  ARCHIVE: {new_url}")
            for fp in file_list:
                print(f"    in: {os.path.relpath(fp, BASE_DIR)}")

    if no_archive:
        print(f"\n--- UNFIXABLE URLs (dead, no Wayback Machine archive) ---")
        for url in sorted(no_archive.keys()):
            file_list = sorted(url_to_files[url])
            print(f"\n  URL:   {url}")
            print(f"  Error: {no_archive[url]}")
            for fp in file_list:
                print(f"    in: {os.path.relpath(fp, BASE_DIR)}")

    if files_modified:
        print(f"\n--- MODIFIED FILES ---")
        for fp in sorted(files_modified):
            print(f"  {os.path.relpath(fp, BASE_DIR)}")

    print(f"\nResults saved to: {RESULTS_FILE}")
    print("Done.")


if __name__ == "__main__":
    main()
