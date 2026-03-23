#!/usr/bin/env python3
"""
Comprehensive media asset audit for the Jekyll site at iloveepoetry.
Scans all post files in _posts/en/*.html and _posts/es/*.html and finds every
src attribute in <img>, <video>, <source>, <iframe>, and <embed> tags.

Categorizes them into:
1. Local assets that exist on disk
2. Local assets that are MISSING
3. External URLs (grouped by domain)

Also audits featured_image front matter values.
"""

import os
import re
import glob
from urllib.parse import urlparse
from collections import defaultdict, Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_BASE = os.path.join(PROJECT_ROOT, "assets", "images")

# ─── Helpers ────────────────────────────────────────────────────────────────

def extract_front_matter(content):
    """Extract YAML front matter from a post file."""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if match:
        return match.group(1)
    return ""

def extract_featured_image(front_matter_text):
    """Extract featured_image value from front matter."""
    match = re.search(r'featured_image:\s*["\']?(.+?)["\']?\s*$', front_matter_text, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None

def extract_src_attributes(content):
    """Extract all src attributes from img, video, source, iframe, embed tags."""
    # Match src="..." or src='...' inside the target tags
    tag_pattern = re.compile(
        r'<(?:img|video|source|iframe|embed)\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    return tag_pattern.findall(content)

def classify_src(src):
    """
    Classify a src value as 'local' or 'external'.
    Returns (classification, normalized_path_or_url)
    """
    src = src.strip()
    if src.startswith('http://') or src.startswith('https://') or src.startswith('//'):
        return 'external', src
    elif src.startswith('/') or src.startswith('./') or src.startswith('../'):
        return 'local', src
    elif src.startswith('data:'):
        return 'data_uri', src
    else:
        # Relative path without prefix - treat as local
        return 'local', src

def normalize_local_path(src):
    """
    Normalize a local src path to a filesystem path under the project.
    Handles paths like:
      /assets/images/...
      /iloveepoetry/assets/images/...
      {{ site.baseurl }}/assets/images/...
    """
    path = src.strip()
    # Remove Jekyll liquid tags
    path = re.sub(r'\{\{.*?\}\}', '', path).strip()
    # Strip /iloveepoetry/ prefix
    if path.startswith('/iloveepoetry/'):
        path = path[len('/iloveepoetry'):]  # keep the leading /
    # Now path should start with /assets/ or /wp-content/ etc.
    # Map to project root
    if path.startswith('/'):
        full_path = os.path.join(PROJECT_ROOT, path.lstrip('/'))
    else:
        full_path = os.path.join(PROJECT_ROOT, path)
    return full_path

def get_domain(url):
    """Extract domain from a URL."""
    url = url.strip()
    if url.startswith('//'):
        url = 'https:' + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Strip www. prefix for grouping
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return 'unknown'


# ─── Main Audit Logic ──────────────────────────────────────────────────────

def audit():
    # Collect all post files
    en_posts = sorted(glob.glob(os.path.join(PROJECT_ROOT, '_posts', 'en', '*.html')))
    es_posts = sorted(glob.glob(os.path.join(PROJECT_ROOT, '_posts', 'es', '*.html')))
    all_posts = en_posts + es_posts

    print(f"{'='*80}")
    print(f"  MEDIA ASSET AUDIT - I Love E-Poetry Jekyll Site")
    print(f"{'='*80}")
    print(f"\nScanning {len(en_posts)} English posts and {len(es_posts)} Spanish posts")
    print(f"Total posts: {len(all_posts)}")
    print()

    # Data structures
    local_exists = []         # (post_file, src, disk_path)
    local_missing = []        # (post_file, src, expected_disk_path)
    external_urls = []        # (post_file, src, domain)
    data_uris = []            # (post_file, src_preview)
    domain_counts = Counter()
    domain_urls = defaultdict(list)  # domain -> [(post, url)]

    # Featured image tracking
    fi_local_exists = []
    fi_local_missing = []
    fi_external = []
    fi_none = []

    total_src_count = 0
    posts_with_media = 0

    for post_path in all_posts:
        rel_post = os.path.relpath(post_path, PROJECT_ROOT)
        with open(post_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # ── Featured Image ──
        fm = extract_front_matter(content)
        fi = extract_featured_image(fm)
        if fi:
            fi_class, _ = classify_src(fi)
            if fi_class == 'external':
                fi_external.append((rel_post, fi, get_domain(fi)))
            elif fi_class == 'local':
                disk_path = normalize_local_path(fi)
                if os.path.isfile(disk_path):
                    fi_local_exists.append((rel_post, fi, disk_path))
                else:
                    fi_local_missing.append((rel_post, fi, disk_path))
            # data URIs ignored for featured_image
        else:
            fi_none.append(rel_post)

        # ── Src Attributes in Body ──
        # Get only the body (after front matter)
        body_match = re.search(r'^---\s*\n.*?\n---\s*\n(.*)', content, re.DOTALL)
        body = body_match.group(1) if body_match else content

        srcs = extract_src_attributes(body)
        if srcs:
            posts_with_media += 1
        total_src_count += len(srcs)

        for src in srcs:
            classification, normalized = classify_src(src)
            if classification == 'external':
                domain = get_domain(normalized)
                external_urls.append((rel_post, normalized, domain))
                domain_counts[domain] += 1
                domain_urls[domain].append((rel_post, normalized))
            elif classification == 'local':
                disk_path = normalize_local_path(src)
                if os.path.isfile(disk_path):
                    local_exists.append((rel_post, src, disk_path))
                else:
                    local_missing.append((rel_post, src, disk_path))
            elif classification == 'data_uri':
                data_uris.append((rel_post, src[:80] + '...'))

    # ─── Report ─────────────────────────────────────────────────────────

    print(f"{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  Total src attributes found:       {total_src_count}")
    print(f"  Posts with at least one media tag: {posts_with_media}")
    print()
    print(f"  LOCAL ASSETS THAT EXIST:           {len(local_exists)}")
    print(f"  LOCAL ASSETS THAT ARE MISSING:     {len(local_missing)}")
    print(f"  EXTERNAL URLs:                     {len(external_urls)}")
    print(f"  Data URIs:                         {len(data_uris)}")
    print()

    # ── Section 1: Local assets that exist ──
    print(f"\n{'='*80}")
    print(f"  1. LOCAL ASSETS THAT EXIST ({len(local_exists)} files)")
    print(f"{'='*80}")
    if local_exists:
        # Group by directory
        dir_counts = Counter()
        for _, src, _ in local_exists:
            parts = src.split('/')
            # Get a meaningful directory grouping
            dir_key = '/'.join(parts[:4]) if len(parts) > 4 else '/'.join(parts[:-1])
            dir_counts[dir_key] += 1
        print("  By directory prefix:")
        for dir_path, count in sorted(dir_counts.items(), key=lambda x: -x[1]):
            print(f"    {dir_path}: {count}")
    print()

    # ── Section 2: Local assets that are MISSING ──
    print(f"\n{'='*80}")
    print(f"  2. LOCAL ASSETS THAT ARE MISSING ({len(local_missing)} files)")
    print(f"{'='*80}")
    if local_missing:
        for post, src, expected in local_missing:
            print(f"  POST: {post}")
            print(f"    SRC: {src}")
            print(f"    Expected at: {os.path.relpath(expected, PROJECT_ROOT)}")
            print()
    else:
        print("  None! All local assets exist on disk.")
    print()

    # ── Section 3: External URLs ──
    print(f"\n{'='*80}")
    print(f"  3. EXTERNAL URLs ({len(external_urls)} total)")
    print(f"{'='*80}")

    # ── Section 4: External URLs by Domain ──
    print(f"\n{'='*80}")
    print(f"  4. EXTERNAL URLs BY DOMAIN ({len(domain_counts)} unique domains)")
    print(f"{'='*80}")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"\n  [{count:>4}] {domain}")
        # Show up to 5 sample URLs per domain
        samples = domain_urls[domain][:5]
        for post, url in samples:
            print(f"         - {url}")
            print(f"           in: {post}")
        if len(domain_urls[domain]) > 5:
            print(f"         ... and {len(domain_urls[domain]) - 5} more")
    print()

    # ── Section 5: Featured Image Audit ──
    total_fi = len(fi_local_exists) + len(fi_local_missing) + len(fi_external)
    print(f"\n{'='*80}")
    print(f"  5. FEATURED IMAGE AUDIT")
    print(f"{'='*80}")
    print(f"  Posts with featured_image:         {total_fi}")
    print(f"  Posts WITHOUT featured_image:       {len(fi_none)}")
    print()
    print(f"  Featured images - local, EXISTS:    {len(fi_local_exists)}")
    print(f"  Featured images - local, MISSING:   {len(fi_local_missing)}")
    print(f"  Featured images - external URL:     {len(fi_external)}")
    print()

    if fi_local_missing:
        print(f"  --- Missing local featured images ---")
        for post, fi_val, expected in fi_local_missing:
            print(f"  POST: {post}")
            print(f"    featured_image: {fi_val}")
            print(f"    Expected at: {os.path.relpath(expected, PROJECT_ROOT)}")
            print()

    if fi_external:
        print(f"  --- External featured images ---")
        fi_ext_domains = Counter()
        for post, fi_val, domain in fi_external:
            fi_ext_domains[domain] += 1
        print(f"  By domain:")
        for domain, count in sorted(fi_ext_domains.items(), key=lambda x: -x[1]):
            print(f"    [{count:>4}] {domain}")
        print()
        print(f"  Full list of external featured images:")
        for post, fi_val, domain in fi_external:
            print(f"    {post}")
            print(f"      -> {fi_val}")
        print()

    # ── Final summary ──
    print(f"\n{'='*80}")
    print(f"  FINAL OVERVIEW")
    print(f"{'='*80}")
    print(f"  Total posts scanned:                {len(all_posts)}")
    print(f"  Total media src attributes:          {total_src_count}")
    print(f"  Local assets (exist):                {len(local_exists)}")
    print(f"  Local assets (MISSING):              {len(local_missing)}")
    print(f"  External URLs:                       {len(external_urls)}")
    print(f"  Unique external domains:             {len(domain_counts)}")
    print(f"  Featured images (local, exist):      {len(fi_local_exists)}")
    print(f"  Featured images (local, MISSING):    {len(fi_local_missing)}")
    print(f"  Featured images (external):          {len(fi_external)}")
    print(f"  Posts with no featured_image:         {len(fi_none)}")
    print(f"{'='*80}")


if __name__ == '__main__':
    audit()
