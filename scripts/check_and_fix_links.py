#!/usr/bin/env python3
"""
Check all work_url and elmcip_url in Jekyll post front matter.
Fix broken links:
  - work_url: replace with Wayback Machine archived version
  - elmcip_url: try HTTPS, try /creative-work/ path, try Wayback, or remove
"""

import os
import re
import sys
import time
import logging
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIRS = [PROJECT_ROOT / "_posts" / "en", PROJECT_ROOT / "_posts" / "es"]

MAX_WORKERS = 15
TIMEOUT = 10
WAYBACK_DELAY = 0.3

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def check_url(url):
    """
    Check if a URL is alive.
    Returns (url, status, final_url_or_none)
    status: 'alive', 'redirect', 'dead'
    """
    try:
        resp = session.head(url, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code < 400:
            if resp.url != url and resp.url.rstrip('/') != url.rstrip('/'):
                return (url, 'redirect', resp.url)
            return (url, 'alive', None)
        # Some servers don't support HEAD, try GET
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        resp.close()
        if resp.status_code < 400:
            if resp.url != url and resp.url.rstrip('/') != url.rstrip('/'):
                return (url, 'redirect', resp.url)
            return (url, 'alive', None)
        return (url, 'dead', f'status_{resp.status_code}')
    except requests.exceptions.SSLError:
        # Try HTTP if HTTPS fails
        if url.startswith('https://'):
            try:
                http_url = url.replace('https://', 'http://', 1)
                resp = session.get(http_url, timeout=TIMEOUT, allow_redirects=True, stream=True)
                resp.close()
                if resp.status_code < 400:
                    return (url, 'alive', None)
            except Exception:
                pass
        return (url, 'dead', 'ssl_error')
    except requests.exceptions.ConnectionError:
        return (url, 'dead', 'connection_error')
    except requests.exceptions.Timeout:
        return (url, 'dead', 'timeout')
    except Exception as e:
        return (url, 'dead', str(e)[:80])


def get_wayback_url(url):
    """
    Look up a URL in the Wayback Machine CDX API.
    Returns the Wayback URL or None.
    """
    try:
        time.sleep(WAYBACK_DELAY)
        cdx_url = (
            f"http://web.archive.org/cdx/search/cdx?"
            f"url={url}&output=json&limit=1&fl=timestamp,original&filter=statuscode:200"
        )
        resp = session.get(cdx_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if len(data) >= 2:
                timestamp = data[1][0]
                original = data[1][1]
                return f"https://web.archive.org/web/{timestamp}/{original}"
    except Exception as e:
        log.warning(f"Wayback lookup failed for {url}: {e}")
    return None


def fix_elmcip_url(url):
    """
    Try alternate ELMCIP URLs.
    Returns (new_url, method) or (None, None) if all fail.
    """
    alternates = []

    # Try HTTPS
    if url.startswith('http://'):
        https_url = url.replace('http://', 'https://', 1)
        alternates.append((https_url, 'https'))

    # Try without www
    if '://www.elmcip.net/' in url:
        no_www = url.replace('://www.elmcip.net/', '://elmcip.net/')
        alternates.append((no_www, 'no_www'))
        if no_www.startswith('http://'):
            alternates.append((no_www.replace('http://', 'https://', 1), 'https_no_www'))

    # Try HTTPS with www
    if url.startswith('http://www.elmcip.net/'):
        alternates.append((url.replace('http://', 'https://', 1), 'https_www'))

    for alt_url, method in alternates:
        try:
            resp = session.head(alt_url, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code < 400:
                return (alt_url, method)
            resp = session.get(alt_url, timeout=TIMEOUT, allow_redirects=True, stream=True)
            resp.close()
            if resp.status_code < 400:
                return (alt_url, method)
        except Exception:
            continue

    return (None, None)


def main():
    print("=" * 70)
    print("Link Checker & Fixer for iloveepoetry")
    print("=" * 70)

    # Phase 1: Collect all URLs
    print("\n[Phase 1] Collecting URLs from post front matter...")
    work_urls = {}      # {url: [list of file paths]}
    elmcip_urls = {}    # {url: [list of file paths]}
    file_data = {}      # {filepath: {work_url, elmcip_url}}

    for posts_dir in POSTS_DIRS:
        if not posts_dir.exists():
            continue
        for fpath in sorted(posts_dir.glob("*.html")):
            content = fpath.read_text(encoding='utf-8')
            wm = re.search(r'^work_url:\s*"?([^"\n]+)"?\s*$', content, re.M)
            em = re.search(r'^elmcip_url:\s*"?([^"\n]+)"?\s*$', content, re.M)

            data = {}
            if wm:
                wurl = wm.group(1).strip()
                data['work_url'] = wurl
                work_urls.setdefault(wurl, []).append(fpath)
            if em:
                eurl = em.group(1).strip()
                data['elmcip_url'] = eurl
                elmcip_urls.setdefault(eurl, []).append(fpath)
            if data:
                file_data[fpath] = data

    unique_work = len(work_urls)
    unique_elmcip = len(elmcip_urls)
    all_urls = set(work_urls.keys()) | set(elmcip_urls.keys())
    print(f"  Unique work_url values: {unique_work}")
    print(f"  Unique elmcip_url values: {unique_elmcip}")
    print(f"  Total unique URLs to check: {len(all_urls)}")

    # Phase 2: Check all URLs
    print(f"\n[Phase 2] Checking {len(all_urls)} URLs with {MAX_WORKERS} threads...")
    url_status = {}  # {url: (status, detail)}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_url, url): url for url in all_urls}
        done = 0
        for future in as_completed(futures):
            done += 1
            url, status, detail = future.result()
            url_status[url] = (status, detail)
            if done % 50 == 0:
                print(f"  Checked {done}/{len(all_urls)}...")

    alive = sum(1 for s, _ in url_status.values() if s == 'alive')
    redirect = sum(1 for s, _ in url_status.values() if s == 'redirect')
    dead = sum(1 for s, _ in url_status.values() if s == 'dead')
    print(f"\n  Results: {alive} alive, {redirect} redirect, {dead} dead")

    # Separate dead URLs by type
    dead_work = {u for u in work_urls if url_status.get(u, ('dead',))[0] == 'dead'}
    dead_elmcip = {u for u in elmcip_urls if url_status.get(u, ('dead',))[0] == 'dead'}
    print(f"  Dead work_urls: {len(dead_work)}")
    print(f"  Dead elmcip_urls: {len(dead_elmcip)}")

    # Phase 3: Fix broken work_url links via Wayback
    print(f"\n[Phase 3] Fixing {len(dead_work)} dead work_urls via Wayback...")
    work_fixes = {}  # {old_url: new_url}
    work_unfixable = []

    for i, url in enumerate(sorted(dead_work), 1):
        wb = get_wayback_url(url)
        if wb:
            work_fixes[url] = wb
            log.info(f"  [{i}/{len(dead_work)}] Fixed: {url}")
        else:
            work_unfixable.append(url)
            if i <= 20:
                log.warning(f"  [{i}/{len(dead_work)}] No Wayback: {url}")

    print(f"  Fixed via Wayback: {len(work_fixes)}")
    print(f"  Unfixable: {len(work_unfixable)}")

    # Phase 4: Fix broken elmcip_url links
    print(f"\n[Phase 4] Fixing {len(dead_elmcip)} dead elmcip_urls...")
    elmcip_fixes = {}     # {old_url: new_url}
    elmcip_to_remove = [] # URLs to completely remove

    for i, url in enumerate(sorted(dead_elmcip), 1):
        # Try ELMCIP alternate URLs
        alt_url, method = fix_elmcip_url(url)
        if alt_url:
            elmcip_fixes[url] = alt_url
            log.info(f"  [{i}/{len(dead_elmcip)}] Fixed ({method}): {url}")
            continue

        # Try Wayback
        wb = get_wayback_url(url)
        if wb:
            elmcip_fixes[url] = wb
            log.info(f"  [{i}/{len(dead_elmcip)}] Wayback: {url}")
            continue

        # Remove it
        elmcip_to_remove.append(url)
        if i <= 20:
            log.warning(f"  [{i}/{len(dead_elmcip)}] Removing: {url}")

    print(f"  Fixed via alternate URL: {sum(1 for v in elmcip_fixes.values() if 'web.archive.org' not in v)}")
    print(f"  Fixed via Wayback: {sum(1 for v in elmcip_fixes.values() if 'web.archive.org' in v)}")
    print(f"  To remove: {len(elmcip_to_remove)}")

    # Also handle redirected URLs - update to final URL
    redirect_work = {u: d for u, (s, d) in url_status.items() if s == 'redirect' and u in work_urls}
    redirect_elmcip = {u: d for u, (s, d) in url_status.items() if s == 'redirect' and u in elmcip_urls}

    # Phase 5: Update post files
    print(f"\n[Phase 5] Updating post files...")
    files_modified = 0
    work_urls_fixed = 0
    elmcip_urls_fixed = 0
    elmcip_urls_removed = 0

    for fpath, data in file_data.items():
        content = fpath.read_text(encoding='utf-8')
        original = content

        # Fix work_url
        if 'work_url' in data:
            old_wurl = data['work_url']
            new_wurl = work_fixes.get(old_wurl) or redirect_work.get(old_wurl)
            if new_wurl:
                content = re.sub(
                    r'^(work_url:\s*)"?[^"\n]+"?\s*$',
                    f'work_url: "{new_wurl}"',
                    content,
                    count=1,
                    flags=re.M
                )
                if content != original:
                    work_urls_fixed += 1

        # Fix or remove elmcip_url
        if 'elmcip_url' in data:
            old_eurl = data['elmcip_url']
            if old_eurl in elmcip_to_remove:
                # Remove the line entirely
                content = re.sub(r'^elmcip_url:.*\n', '', content, count=1, flags=re.M)
                elmcip_urls_removed += 1
            else:
                new_eurl = elmcip_fixes.get(old_eurl) or redirect_elmcip.get(old_eurl)
                if new_eurl:
                    content = re.sub(
                        r'^(elmcip_url:\s*)"?[^"\n]+"?\s*$',
                        f'elmcip_url: "{new_eurl}"',
                        content,
                        count=1,
                        flags=re.M
                    )
                    if content != original:
                        elmcip_urls_fixed += 1

        if content != original:
            fpath.write_text(content, encoding='utf-8')
            files_modified += 1

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"URLs checked:              {len(all_urls)}")
    print(f"  Alive:                   {alive}")
    print(f"  Redirected:              {redirect}")
    print(f"  Dead:                    {dead}")
    print()
    print(f"Work URLs fixed (Wayback): {len(work_fixes)}")
    print(f"Work URLs unfixable:       {len(work_unfixable)}")
    print()
    print(f"ELMCIP URLs fixed:         {len(elmcip_fixes)}")
    print(f"ELMCIP URLs removed:       {len(elmcip_to_remove)}")
    print()
    print(f"Post files modified:       {files_modified}")
    print(f"  work_url updated:        {work_urls_fixed}")
    print(f"  elmcip_url updated:      {elmcip_urls_fixed}")
    print(f"  elmcip_url removed:      {elmcip_urls_removed}")
    print()

    if work_unfixable:
        print(f"Unfixable work_urls ({len(work_unfixable)}):")
        for u in sorted(work_unfixable)[:30]:
            print(f"  {u}")
        if len(work_unfixable) > 30:
            print(f"  ... and {len(work_unfixable) - 30} more")
    print()
    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
