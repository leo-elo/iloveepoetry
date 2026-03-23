#!/usr/bin/env python3
"""
Comprehensive image audit for the I Love E-Poetry Jekyll site.

Scans all posts, pages, and HTML files for image references, checks whether
the referenced files exist on disk, and identifies orphaned images that are
not referenced anywhere.

Outputs a structured report to stdout and saves full details as JSON.
"""

import os
import re
import json
import glob
import yaml
from collections import defaultdict
from urllib.parse import unquote

SITE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(SITE_ROOT, "assets", "images")
BASEURL = "/iloveepoetry"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_front_matter(filepath):
    """Extract YAML front matter from a Jekyll file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {}, ""

    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_text = content[3:end]
    body = content[end + 3:]

    try:
        fm = yaml.safe_load(fm_text)
        if fm is None:
            fm = {}
    except yaml.YAMLError:
        fm = {}

    return fm, body


def normalize_image_path(src):
    """
    Given an image src attribute, return the local filesystem path to check,
    or None if it's an external URL or can't be resolved.
    Also returns a category string: 'local', 'external', or 'unresolvable'.
    """
    if not src or not src.strip():
        return None, "empty"

    src = src.strip()

    # Handle Liquid relative_url filter:  {{ "/assets/..." | relative_url }}
    # Also handle variations with extra whitespace
    liquid_match = re.search(r'\{\{\s*["\'](.+?)["\']\s*\|\s*\w+\s*\}\}', src)
    if liquid_match:
        src = liquid_match.group(1)

    # Handle already-resolved relative_url with baseurl prefix
    if src.startswith(BASEURL + "/"):
        src = src[len(BASEURL):]

    # External URLs
    if src.startswith(("http://", "https://", "//", "data:")):
        return src, "external"

    # Liquid tags we can't resolve -- try harder to extract a path
    if "{{" in src or "{%" in src:
        # Try to extract a quoted path
        inner = re.search(r'["\']([^"\']+?)["\']', src)
        if inner:
            src = inner.group(1)
            if src.startswith(BASEURL + "/"):
                src = src[len(BASEURL):]
        else:
            return src, "unresolvable"

    # Now src should be a site-root-relative path like /assets/images/...
    # or a relative path
    if src.startswith("/"):
        disk_path = os.path.join(SITE_ROOT, src.lstrip("/"))
    else:
        # Relative path -- resolve relative to site root
        disk_path = os.path.join(SITE_ROOT, src)

    # URL-decode the path
    disk_path = unquote(disk_path)

    return disk_path, "local"


def extract_img_srcs(html_body):
    """Extract all src attributes from <img> tags in HTML content.

    Handles Liquid template tags like {{ "..." | relative_url }} inside
    the src attribute value.
    """
    srcs = []

    # Strategy: find each <img tag, then extract src from it
    for img_match in re.finditer(r'<img\s[^>]*?>', html_body, re.IGNORECASE | re.DOTALL):
        img_tag = img_match.group(0)

        # Try to extract src= with double quotes (allowing internal quotes for Liquid)
        # Pattern: src="...anything until the closing quote that's NOT inside {{ }}"
        m = re.search(r'src\s*=\s*"((?:[^"]*?\{\{[^}]*\}\}[^"]*?)|[^"]*?)"', img_tag, re.IGNORECASE)
        if not m:
            # Try single quotes
            m = re.search(r"src\s*=\s*'((?:[^']*?\{\{[^}]*\}\}[^']*?)|[^']*?)'", img_tag, re.IGNORECASE)
        if not m:
            # Try unquoted
            m = re.search(r'src\s*=\s*([^\s>]+)', img_tag, re.IGNORECASE)

        if m:
            src = m.group(1).strip()
            if src:
                srcs.append(src)

    return srcs


def collect_all_images_on_disk():
    """Walk the assets/images directory and return a set of absolute paths."""
    images = set()
    if not os.path.isdir(IMAGES_DIR):
        return images
    for root, dirs, files in os.walk(IMAGES_DIR):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            images.add(os.path.join(root, f))
    return images


def collect_html_files():
    """Collect all relevant HTML files: posts, pages, layouts, includes, root."""
    files = []

    # Posts
    for lang in ["en", "es"]:
        post_dir = os.path.join(SITE_ROOT, "_posts", lang)
        if os.path.isdir(post_dir):
            for f in os.listdir(post_dir):
                if f.endswith(".html") and not f.startswith("."):
                    files.append(os.path.join(post_dir, f))

    # Pages
    pages_dir = os.path.join(SITE_ROOT, "_pages")
    if os.path.isdir(pages_dir):
        for root, dirs, fnames in os.walk(pages_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in fnames:
                if f.endswith(".html"):
                    files.append(os.path.join(root, f))

    # Layouts and includes
    for subdir in ["_layouts", "_includes"]:
        d = os.path.join(SITE_ROOT, subdir)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".html"):
                    files.append(os.path.join(d, f))

    # Root HTML files
    for f in os.listdir(SITE_ROOT):
        fp = os.path.join(SITE_ROOT, f)
        if os.path.isfile(fp) and f.endswith(".html"):
            files.append(fp)

    # en/ and es/ index files
    for lang in ["en", "es"]:
        d = os.path.join(SITE_ROOT, lang)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".html"):
                    files.append(os.path.join(d, f))

    return files


# ──────────────────────────────────────────────────────────────────────────────
# Main audit
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 78)
    print("  IMAGE AUDIT REPORT  --  I Love E-Poetry")
    print("=" * 78)
    print(f"\nSite root: {SITE_ROOT}")
    print(f"Images dir: {IMAGES_DIR}\n")

    # ── Collect all images on disk ────────────────────────────────────────
    all_disk_images = collect_all_images_on_disk()
    print(f"Total image files on disk: {len(all_disk_images)}")

    # Track which disk images are referenced (for orphan detection)
    referenced_disk_images = set()

    # ── Collect all HTML files ────────────────────────────────────────────
    all_files = collect_html_files()
    print(f"Total HTML files to scan: {len(all_files)}")

    # Separate posts from other files for reporting
    post_files = [f for f in all_files if "/_posts/" in f]
    other_files = [f for f in all_files if "/_posts/" not in f]

    # ── 1. Featured images from front matter ─────────────────────────────
    missing_featured = []
    total_featured = 0
    external_featured = 0

    for filepath in post_files:
        fm, body = parse_front_matter(filepath)
        fi = fm.get("featured_image", "")
        if not fi:
            continue

        total_featured += 1
        disk_path, category = normalize_image_path(fi)

        if category == "external":
            external_featured += 1
            continue
        elif category == "unresolvable":
            missing_featured.append({
                "file": os.path.relpath(filepath, SITE_ROOT),
                "featured_image": fi,
                "expected_path": fi,
                "reason": "unresolvable Liquid/template path"
            })
            continue

        if disk_path and os.path.isfile(disk_path):
            referenced_disk_images.add(os.path.normpath(disk_path))
        else:
            missing_featured.append({
                "file": os.path.relpath(filepath, SITE_ROOT),
                "featured_image": fi,
                "expected_path": os.path.relpath(disk_path, SITE_ROOT) if disk_path else fi,
                "reason": "file not found on disk"
            })

    # ── 2. Body images from posts ─────────────────────────────────────────
    missing_body_post = []
    total_body_post = 0
    external_body_post = 0

    for filepath in post_files:
        fm, body = parse_front_matter(filepath)
        srcs = extract_img_srcs(body)

        for src in srcs:
            total_body_post += 1
            disk_path, category = normalize_image_path(src)

            if category == "external":
                external_body_post += 1
                continue
            elif category in ("unresolvable", "empty"):
                missing_body_post.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": src,
                    "expected_path": src,
                    "reason": f"{category} path"
                })
                continue

            if disk_path and os.path.isfile(disk_path):
                referenced_disk_images.add(os.path.normpath(disk_path))
            else:
                missing_body_post.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": src,
                    "expected_path": os.path.relpath(disk_path, SITE_ROOT) if disk_path else src,
                    "reason": "file not found on disk"
                })

    # ── 3. Images in pages and other HTML files ───────────────────────────
    missing_body_pages = []
    total_body_pages = 0
    external_body_pages = 0

    for filepath in other_files:
        fm, body = parse_front_matter(filepath)
        # Also check featured images in pages
        fi = fm.get("featured_image", "")
        if fi:
            total_body_pages += 1
            disk_path, category = normalize_image_path(fi)
            if category == "external":
                external_body_pages += 1
            elif category in ("unresolvable", "empty"):
                missing_body_pages.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": fi,
                    "expected_path": fi,
                    "reason": f"featured_image: {category} path"
                })
            elif disk_path and os.path.isfile(disk_path):
                referenced_disk_images.add(os.path.normpath(disk_path))
            else:
                missing_body_pages.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": fi,
                    "expected_path": os.path.relpath(disk_path, SITE_ROOT) if disk_path else fi,
                    "reason": "featured_image: file not found on disk"
                })

        # Body images
        full_content = body
        srcs = extract_img_srcs(full_content)
        for src in srcs:
            total_body_pages += 1
            disk_path, category = normalize_image_path(src)

            if category == "external":
                external_body_pages += 1
                continue
            elif category in ("unresolvable", "empty"):
                missing_body_pages.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": src,
                    "expected_path": src,
                    "reason": f"{category} path"
                })
                continue

            if disk_path and os.path.isfile(disk_path):
                referenced_disk_images.add(os.path.normpath(disk_path))
            else:
                missing_body_pages.append({
                    "file": os.path.relpath(filepath, SITE_ROOT),
                    "img_src": src,
                    "expected_path": os.path.relpath(disk_path, SITE_ROOT) if disk_path else src,
                    "reason": "file not found on disk"
                })

    # ── Also scan for images referenced in featured_image across ALL posts
    #    that might be in <a href="..."><img> or background-image patterns ──
    # (Already covered above via extract_img_srcs and front matter parsing)

    # ── Also check CSS background-image and srcset ────────────────────────
    bg_missing = []
    for filepath in all_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except:
            continue

        # background-image: url(...)
        for m in re.finditer(r'background(?:-image)?\s*:\s*url\(\s*["\']?([^"\')\s]+)["\']?\s*\)', content):
            src = m.group(1)
            disk_path, category = normalize_image_path(src)
            if category == "local":
                if disk_path and os.path.isfile(disk_path):
                    referenced_disk_images.add(os.path.normpath(disk_path))

        # srcset
        for m in re.finditer(r'srcset\s*=\s*"([^"]+)"', content, re.IGNORECASE):
            for entry in m.group(1).split(","):
                parts = entry.strip().split()
                if parts:
                    src = parts[0]
                    disk_path, category = normalize_image_path(src)
                    if category == "local":
                        if disk_path and os.path.isfile(disk_path):
                            referenced_disk_images.add(os.path.normpath(disk_path))

    # ── Also scan for <a href="..."> pointing to images ───────────────────
    img_extensions = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff"}
    for filepath in all_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except:
            continue

        for m in re.finditer(r'href\s*=\s*"([^"]*)"', content, re.IGNORECASE):
            href = m.group(1)
            _, ext = os.path.splitext(href.split("?")[0].split("#")[0])
            if ext.lower() in img_extensions:
                disk_path, category = normalize_image_path(href)
                if category == "local":
                    if disk_path and os.path.isfile(disk_path):
                        referenced_disk_images.add(os.path.normpath(disk_path))

    # ── 4. Orphaned images ────────────────────────────────────────────────
    orphaned = sorted(
        os.path.relpath(p, SITE_ROOT)
        for p in all_disk_images
        if os.path.normpath(p) not in referenced_disk_images
    )

    # ══════════════════════════════════════════════════════════════════════
    # REPORT
    # ══════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 78)
    print("  1. MISSING FEATURED IMAGES")
    print("=" * 78)
    if missing_featured:
        for i, item in enumerate(missing_featured, 1):
            print(f"  {i:3d}. {item['file']}")
            print(f"       featured_image: {item['featured_image']}")
            print(f"       expected: {item['expected_path']}")
            print(f"       reason: {item['reason']}")
    else:
        print("  None -- all featured images found!")
    print(f"\n  Total featured images: {total_featured}")
    print(f"  External (not checked): {external_featured}")
    print(f"  Missing: {len(missing_featured)}")

    print("\n" + "=" * 78)
    print("  2. MISSING BODY IMAGES (Posts)")
    print("=" * 78)
    if missing_body_post:
        for i, item in enumerate(missing_body_post, 1):
            print(f"  {i:3d}. {item['file']}")
            print(f"       src: {item['img_src'][:120]}")
            print(f"       expected: {item['expected_path'][:120]}")
            print(f"       reason: {item['reason']}")
    else:
        print("  None -- all body images in posts found!")
    print(f"\n  Total body images in posts: {total_body_post}")
    print(f"  External (not checked): {external_body_post}")
    print(f"  Missing: {len(missing_body_post)}")

    print("\n" + "=" * 78)
    print("  3. MISSING IMAGES (Pages & Other HTML)")
    print("=" * 78)
    if missing_body_pages:
        for i, item in enumerate(missing_body_pages, 1):
            print(f"  {i:3d}. {item['file']}")
            print(f"       src: {item['img_src'][:120]}")
            print(f"       expected: {item['expected_path'][:120]}")
            print(f"       reason: {item['reason']}")
    else:
        print("  None -- all page images found!")
    print(f"\n  Total images in pages/other: {total_body_pages}")
    print(f"  External (not checked): {external_body_pages}")
    print(f"  Missing: {len(missing_body_pages)}")

    print("\n" + "=" * 78)
    print("  4. ORPHANED IMAGES (on disk but not referenced)")
    print("=" * 78)
    if orphaned:
        for i, path in enumerate(orphaned, 1):
            print(f"  {i:3d}. {path}")
    else:
        print("  None -- all images are referenced!")
    print(f"\n  Total orphaned: {len(orphaned)}")

    # ── Summary ───────────────────────────────────────────────────────────
    total_refs = total_featured + total_body_post + total_body_pages
    total_external = external_featured + external_body_post + external_body_pages
    total_missing = len(missing_featured) + len(missing_body_post) + len(missing_body_pages)

    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print(f"  Total image references scanned:     {total_refs}")
    print(f"    - Local image references:          {total_refs - total_external}")
    print(f"    - External URLs (not checked):     {total_external}")
    print(f"  Total images on disk:                {len(all_disk_images)}")
    print(f"  Total referenced disk images found:  {len(referenced_disk_images)}")
    print(f"  Total MISSING images:                {total_missing}")
    print(f"    - Missing featured images:         {len(missing_featured)}")
    print(f"    - Missing body images (posts):     {len(missing_body_post)}")
    print(f"    - Missing images (pages/other):    {len(missing_body_pages)}")
    print(f"  Total ORPHANED images:               {len(orphaned)}")
    print("=" * 78)

    # ── Save JSON report ──────────────────────────────────────────────────
    report = {
        "summary": {
            "total_image_references": total_refs,
            "local_image_references": total_refs - total_external,
            "external_urls_not_checked": total_external,
            "total_images_on_disk": len(all_disk_images),
            "total_referenced_images_found": len(referenced_disk_images),
            "total_missing": total_missing,
            "missing_featured_images": len(missing_featured),
            "missing_body_images_posts": len(missing_body_post),
            "missing_images_pages": len(missing_body_pages),
            "total_orphaned": len(orphaned),
        },
        "missing_featured_images": missing_featured,
        "missing_body_images_posts": missing_body_post,
        "missing_images_pages": missing_body_pages,
        "orphaned_images": orphaned,
    }

    output_path = os.path.join(SITE_ROOT, "scripts", "image_audit_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to: {output_path}")


if __name__ == "__main__":
    main()
