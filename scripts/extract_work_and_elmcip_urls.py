#!/usr/bin/env python3
"""
Extract work URLs and ELMCIP URLs from WordPress XML export and Jekyll post files,
add them to Jekyll front matter, and remove ELMCIP <a><img></a> blocks from post bodies.
"""

import os
import re
import glob
import xml.etree.ElementTree as ET
from collections import defaultdict


# ── Configuration ──────────────────────────────────────────────────────────────

SITE_DIR = "/Users/floresll/Desktop/iloveepoetry"
XML_PATH = "/Users/floresll/Downloads/ie-poetry.WordPress.2026-03-19.xml"
EN_DIR = os.path.join(SITE_DIR, "_posts/en")
ES_DIR = os.path.join(SITE_DIR, "_posts/es")

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
}


# ── Step 1: Parse WordPress XML ───────────────────────────────────────────────

def extract_work_url_from_content(content):
    """
    Extract the work URL from WordPress post content.

    Strategies (in order):
    1. Look for Open/Abrir/Abre + <a href="URL"> inside a [caption] shortcode
    2. Look for Open/Abrir/Abre + <a href="URL"> anywhere in the content
    3. Look for the first non-image <a href="URL"> inside a [caption] shortcode
    """
    if not content:
        return None

    # Strategy 1 & 2: Look for Open/Abrir/Abre followed by <a href="URL">
    # Pattern: Open/Abrir/Abre (optional colon, optional whitespace/newline) <a href="URL">
    open_pattern = r'(?:Open|Abrir|Abre)\s*:?\s*(?:\n\s*)?<a\s+href=["\']([^"\']+)["\']'

    # First try within [caption] blocks
    caption_blocks = re.findall(r'\[caption[^\]]*\](.*?)\[/caption\]', content, re.DOTALL)
    for cap in caption_blocks:
        m = re.search(open_pattern, cap, re.IGNORECASE)
        if m:
            return m.group(1)

    # Then try anywhere in content (for posts without [caption])
    m = re.search(open_pattern, content, re.IGNORECASE)
    if m:
        return m.group(1)

    # Strategy 3: First non-image <a href> inside a [caption] block
    for cap in caption_blocks:
        links = re.findall(r'<a\s+href=["\']([^"\']+)["\']', cap)
        for link in links:
            # Skip image URLs and internal WordPress image URLs
            if not re.search(r'\.(png|jpg|jpeg|gif|svg|bmp|webp)(\?.*)?$', link, re.IGNORECASE):
                return link

    return None


def parse_wordpress_xml(xml_path):
    """
    Parse the WordPress XML export and extract work URLs for each published post.
    Returns a dict mapping wp_post_id -> work_url.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    work_urls = {}  # wp_post_id -> work_url

    for item in root.findall(".//item"):
        post_type = item.find("wp:post_type", NS)
        status = item.find("wp:status", NS)

        if post_type is None or post_type.text != "post":
            continue
        if status is None or status.text != "publish":
            continue

        post_id_el = item.find("wp:post_id", NS)
        if post_id_el is None:
            continue
        post_id = post_id_el.text

        content_el = item.find("content:encoded", NS)
        content = content_el.text if content_el is not None else ""

        work_url = extract_work_url_from_content(content)
        if work_url:
            work_urls[post_id] = work_url

    return work_urls


# ── Step 2: Parse Jekyll Post Files ───────────────────────────────────────────

def split_front_matter_and_body(file_content):
    """
    Split a Jekyll file into front matter (as string) and body.
    Returns (front_matter_str, body_str, full_match).
    front_matter_str does NOT include the --- delimiters.
    """
    m = re.match(r'^---\n(.*?\n)---\n(.*)', file_content, re.DOTALL)
    if m:
        return m.group(1), m.group(2)
    return None, file_content


def get_front_matter_value(fm_str, key):
    """Get a value from front matter string."""
    m = re.search(r'^' + re.escape(key) + r':\s*["\']?(.+?)["\']?\s*$', fm_str, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return None


def extract_elmcip_url_from_body(body):
    """
    Extract ELMCIP URL from the post body HTML.
    Only matches specific work entry URLs:
    - http(s)://www.elmcip.net/node/NNN
    - http(s)://elmcip.net/creative-work/SLUG
    - elmcip.net/creative-work/SLUG (without protocol)
    Does NOT match general references like elmcip.net/knowledgebase.
    """
    # Match with or without http(s):// protocol prefix
    m = re.search(
        r'<a\s+[^>]*href=["\'](?:https?://)?(?:www\.)?elmcip\.net/(node/(\d+)[^"\']*|creative-work/([^"\']+))["\']',
        body, re.IGNORECASE
    )
    if m:
        # Normalize: always return with http:// prefix and clean path
        if m.group(2):
            # /node/NNN pattern - extract just the node number
            return f"http://elmcip.net/node/{m.group(2)}"
        elif m.group(3):
            # /creative-work/SLUG pattern
            slug = m.group(3).rstrip('\u200e')  # Strip right-to-left mark if present
            return f"http://elmcip.net/creative-work/{slug}"
    return None


def remove_elmcip_block_from_body(body):
    """
    Remove the ELMCIP <a><img elmcipthumb></a> block from the body.
    Only removes <a> tags that contain an <img> child (the elmcipthumb image block),
    NOT inline text links to ELMCIP.

    Patterns to remove:
    1. <a href="...elmcip..."><img ...elmcipthumb.../></a>
    2. <a href="...elmcip..."><img ... /></a> where the img references elmcipthumb
    """
    # Remove the ELMCIP <a><img></a> element - only when the <a> wraps an <img>
    # This handles various attribute orderings and self-closing img tags
    # Also handles URLs with or without http:// protocol prefix
    body = re.sub(
        r'\n?[ \t]*<a\s+[^>]*href=["\'](?:https?://)?(?:www\.)?elmcip\.net[^"\']*["\'][^>]*>\s*'
        r'<img[^>]*/?\s*>\s*</a>[ \t]*\n?',
        '\n',
        body,
        flags=re.IGNORECASE | re.DOTALL
    )

    return body


def add_front_matter_fields(fm_str, fields):
    """
    Add new fields to front matter string (before the closing ---).
    fields is a dict of key -> value.
    Only adds if the key doesn't already exist.
    Returns the updated front matter string.
    """
    lines = fm_str.rstrip('\n').split('\n')

    for key, value in fields.items():
        # Check if key already exists
        existing = re.search(r'^' + re.escape(key) + r':', fm_str, re.MULTILINE)
        if existing:
            continue
        # Escape the value for YAML - use double quotes
        # Make sure the URL itself doesn't contain unescaped double quotes
        escaped_value = value.replace('"', '\\"')
        lines.append(f'{key}: "{escaped_value}"')

    return '\n'.join(lines) + '\n'


# ── Step 3: Process all Jekyll posts ──────────────────────────────────────────

def process_jekyll_posts(work_urls_from_xml):
    """
    Process all Jekyll post files:
    1. Match with XML data via wp_post_id
    2. Extract ELMCIP URLs from body
    3. Add work_url and elmcip_url to front matter
    4. Remove ELMCIP block from body
    5. Handle Spanish translations by copying from English counterpart
    """

    # Collect all post data first
    all_posts = {}  # wp_post_id -> {path, fm, body, lang, translation, ...}
    permalink_to_wpid = {}  # permalink -> wp_post_id (for translation matching)

    post_files = (
        glob.glob(os.path.join(EN_DIR, "*.html")) +
        glob.glob(os.path.join(ES_DIR, "*.html"))
    )

    for filepath in post_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        fm_str, body = split_front_matter_and_body(content)
        if fm_str is None:
            continue

        wp_post_id = get_front_matter_value(fm_str, "wp_post_id")
        lang = get_front_matter_value(fm_str, "lang")
        translation = get_front_matter_value(fm_str, "translation")
        permalink = get_front_matter_value(fm_str, "permalink")

        if not wp_post_id:
            continue

        # Extract ELMCIP URL from body
        elmcip_url = extract_elmcip_url_from_body(body)

        post_data = {
            "path": filepath,
            "fm_str": fm_str,
            "body": body,
            "lang": lang,
            "translation": translation,
            "permalink": permalink,
            "wp_post_id": wp_post_id,
            "elmcip_url": elmcip_url,
            "work_url": work_urls_from_xml.get(wp_post_id),
        }

        all_posts[wp_post_id] = post_data
        if permalink:
            permalink_to_wpid[permalink] = wp_post_id

    # Build a reverse lookup: permalink -> post_data
    # For Spanish posts that lack work_url/elmcip_url, try to find from English counterpart

    # Also build translation pairs based on the translation field
    # The translation field in EN posts points to ES permalink and vice versa

    for wp_id, post in all_posts.items():
        if post["lang"] == "es":
            translation_permalink = post.get("translation")
            if translation_permalink:
                # Find the English counterpart by permalink
                counterpart_wpid = permalink_to_wpid.get(translation_permalink)
                if counterpart_wpid and counterpart_wpid in all_posts:
                    counterpart = all_posts[counterpart_wpid]
                    # Copy work_url from counterpart if we don't have one
                    if not post["work_url"] and counterpart.get("work_url"):
                        post["work_url"] = counterpart["work_url"]
                    # Copy elmcip_url from counterpart if we don't have one
                    if not post["elmcip_url"] and counterpart.get("elmcip_url"):
                        post["elmcip_url"] = counterpart["elmcip_url"]

    # Also check: English posts might get URLs from Spanish counterparts
    for wp_id, post in all_posts.items():
        if post["lang"] == "en":
            translation_permalink = post.get("translation")
            if translation_permalink:
                counterpart_wpid = permalink_to_wpid.get(translation_permalink)
                if counterpart_wpid and counterpart_wpid in all_posts:
                    counterpart = all_posts[counterpart_wpid]
                    if not post["work_url"] and counterpart.get("work_url"):
                        post["work_url"] = counterpart["work_url"]
                    if not post["elmcip_url"] and counterpart.get("elmcip_url"):
                        post["elmcip_url"] = counterpart["elmcip_url"]

    # Now write updates
    stats = {
        "total": 0,
        "got_work_url": 0,
        "got_elmcip_url": 0,
        "got_both": 0,
        "got_neither": 0,
        "elmcip_blocks_removed": 0,
        "en_work_url": 0,
        "es_work_url": 0,
        "en_elmcip_url": 0,
        "es_elmcip_url": 0,
    }

    for wp_id, post in all_posts.items():
        stats["total"] += 1

        fields_to_add = {}

        has_work_url = False
        has_elmcip_url = False

        # Check if front matter already has these fields
        existing_work_url = get_front_matter_value(post["fm_str"], "work_url")
        existing_elmcip_url = get_front_matter_value(post["fm_str"], "elmcip_url")

        if post["work_url"] and not existing_work_url:
            fields_to_add["work_url"] = post["work_url"]
            has_work_url = True
        elif existing_work_url:
            has_work_url = True

        if post["elmcip_url"] and not existing_elmcip_url:
            fields_to_add["elmcip_url"] = post["elmcip_url"]
            has_elmcip_url = True
        elif existing_elmcip_url:
            has_elmcip_url = True

        # Track stats by language
        if has_work_url:
            stats["got_work_url"] += 1
            if post["lang"] == "en":
                stats["en_work_url"] += 1
            else:
                stats["es_work_url"] += 1
        if has_elmcip_url:
            stats["got_elmcip_url"] += 1
            if post["lang"] == "en":
                stats["en_elmcip_url"] += 1
            else:
                stats["es_elmcip_url"] += 1
        if has_work_url and has_elmcip_url:
            stats["got_both"] += 1
        if not has_work_url and not has_elmcip_url:
            stats["got_neither"] += 1

        # Only write if we have changes to make
        body = post["body"]
        body_changed = False

        # Remove ELMCIP block from body if there's an ELMCIP URL present
        if has_elmcip_url:
            new_body = remove_elmcip_block_from_body(body)
            if new_body != body:
                body = new_body
                body_changed = True
                stats["elmcip_blocks_removed"] += 1

        if fields_to_add or body_changed:
            new_fm = add_front_matter_fields(post["fm_str"], fields_to_add)
            new_content = f"---\n{new_fm}---\n{body}"

            with open(post["path"], "w", encoding="utf-8") as f:
                f.write(new_content)

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Extracting work URLs and ELMCIP URLs")
    print("=" * 70)

    # Step 1: Parse WordPress XML
    print("\n[1/3] Parsing WordPress XML export...")
    work_urls = parse_wordpress_xml(XML_PATH)
    print(f"  Found work URLs for {len(work_urls)} posts in XML")

    # Step 2 & 3: Process Jekyll posts
    print("\n[2/3] Processing Jekyll post files...")
    stats = process_jekyll_posts(work_urls)

    # Step 3: Print summary
    print("\n[3/3] Summary")
    print("=" * 70)
    print(f"  Total posts processed:          {stats['total']}")
    print(f"  Posts with work_url:            {stats['got_work_url']}")
    print(f"    - English:                    {stats['en_work_url']}")
    print(f"    - Spanish:                    {stats['es_work_url']}")
    print(f"  Posts with elmcip_url:          {stats['got_elmcip_url']}")
    print(f"    - English:                    {stats['en_elmcip_url']}")
    print(f"    - Spanish:                    {stats['es_elmcip_url']}")
    print(f"  Posts with both:                {stats['got_both']}")
    print(f"  Posts with neither:             {stats['got_neither']}")
    print(f"  ELMCIP blocks removed from body: {stats['elmcip_blocks_removed']}")
    print("=" * 70)
    print("Done!")


if __name__ == "__main__":
    main()
