#!/usr/bin/env python3
"""
WordPress WXR XML to Jekyll converter for I Love E-Poetry.

Parses a WordPress export (WXR 1.2) and generates Jekyll-compatible
post and page files with proper YAML front matter, language detection,
permalink construction, and content cleaning.

Usage:
    python3 convert_wp.py [path_to_wxr_xml]

If no path is given, defaults to:
    ~/Downloads/ie-poetry.WordPress.2026-03-19.xml
"""

import sys
import os
import re
import json
import html
from pathlib import Path
from urllib.parse import unquote, urlparse

from lxml import etree
import yaml


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_XML_PATH = os.path.expanduser(
    "~/Downloads/ie-poetry.WordPress.2026-03-19.xml"
)

SITE_DIR = Path(__file__).resolve().parent.parent  # /Users/…/iloveepoetry
SCRIPTS_DIR = SITE_DIR / "scripts"
POSTS_DIR = SITE_DIR / "_posts"
PAGES_DIR = SITE_DIR / "_pages"

NAMESPACES = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "wfw": "http://wellformedweb.org/CommentAPI/",
}

# Categories to skip when choosing the "primary" category for permalink URL
PERMALINK_SKIP_CATEGORIES = {
    "entries",
    "entries-es",
    "uncategorized",
    "sin-categorizar",
    "e-poetry",
    "scheduled",
    "new-elmcip",
    "poetry",
}

# Known Spanish page slugs (prefix matching where noted with *)
SPANISH_PAGE_SLUGS_EXACT = {
    "acerca-de",
    "sobre-este-proyecto",
    "contacto",
    "contribuir",
    "suscribete",
    "el-equipo",
    "cumbre",
    "cfp-abierto",
    "recursos-revisados",
    "metadata",
}

SPANISH_PAGE_SLUG_PREFIXES = (
    "bienvenido",
    "indice",
    "caldero",
    "coleccion",
    "exposicion",
    "directrices",
    "nuevas-listas",
    "lectura",
    "recurso-poesia",
    "taroko-gorge-y",
    "la-serie",
)

# Slugs that are numbered duplicates of English pages, indicating Spanish
SPANISH_PAGE_SLUG_PATTERNS = [
    re.compile(r"^poems-that-go-3$"),
    re.compile(r"^beehive-3$"),
    re.compile(r"^marble-springs-2$"),
    re.compile(r"^elo-2012-media-art-show-2$"),
    re.compile(r"^the-electronic-literature-collection-volume-1-2$"),
    re.compile(r"^metadata-2$"),
]

# Image file extensions
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff",
}


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

class _LiteralStr(str):
    """Wrapper to force YAML literal block style for multi-line strings."""
    pass


def _literal_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(_LiteralStr, _literal_representer)


def build_front_matter(data: dict) -> str:
    """Serialize a dict to YAML front matter, using PyYAML for safe escaping."""
    # PyYAML handles quoting/escaping of special chars in strings
    yml = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,  # avoid line wrapping inside values
    )
    return "---\n" + yml + "---\n"


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _text(element, xpath, namespaces=None):
    """Return stripped text of first match, or empty string."""
    ns = namespaces or NAMESPACES
    nodes = element.xpath(xpath, namespaces=ns)
    if nodes:
        t = nodes[0].text
        return (t or "").strip()
    return ""


def _text_or_tail(element, xpath, namespaces=None):
    """Like _text but also checks .tail (for mixed-content edge cases)."""
    return _text(element, xpath, namespaces)


# ---------------------------------------------------------------------------
# Category hierarchy parsing
# ---------------------------------------------------------------------------

def parse_categories(channel):
    """
    Parse <wp:category> elements from the channel into a dict:
        slug -> {name, parent_slug, description}
    """
    categories = {}
    for cat_el in channel.xpath("wp:category", namespaces=NAMESPACES):
        slug = _text(cat_el, "wp:category_nicename")
        name = _text(cat_el, "wp:cat_name")
        parent = _text(cat_el, "wp:category_parent")
        desc = _text(cat_el, "wp:category_description")
        if slug:
            categories[slug] = {
                "name": name,
                "parent_slug": parent if parent else None,
                "description": desc,
            }
    return categories


# ---------------------------------------------------------------------------
# Attachment map
# ---------------------------------------------------------------------------

def parse_attachments(channel):
    """
    Build dict: post_id (int) -> attachment_url (str)
    from items with post_type == 'attachment'.
    """
    attachments = {}
    for item in channel.xpath("item"):
        post_type = _text(item, "wp:post_type")
        if post_type != "attachment":
            continue
        post_id_str = _text(item, "wp:post_id")
        att_url = _text(item, "wp:attachment_url")
        if post_id_str and att_url:
            try:
                attachments[int(post_id_str)] = att_url
            except ValueError:
                pass
    return attachments


# ---------------------------------------------------------------------------
# Content cleaning
# ---------------------------------------------------------------------------

# Gutenberg block comment patterns
_RE_GUTENBERG_OPEN = re.compile(r"<!-- wp:\S.*?-->", re.DOTALL)
_RE_GUTENBERG_CLOSE = re.compile(r"<!-- /wp:\S+\s*-->")

# Caption shortcode: [caption ...]<img .../>TEXT[/caption]
_RE_CAPTION = re.compile(
    r'\[caption[^\]]*\](.*?)\[/caption\]',
    re.DOTALL,
)

# Inside a caption, split img from the trailing caption text
_RE_CAPTION_INNER = re.compile(
    r'(<img\s[^>]*?/?>)\s*(.*)',
    re.DOTALL,
)

# <!--more--> tag
_RE_MORE = re.compile(r"<!--more(?:\s[^>]*)?\s*-->")

# Empty paragraphs
_RE_EMPTY_P = re.compile(r"<p>\s*(?:&nbsp;)?\s*</p>", re.IGNORECASE)

# Excessive blank lines (3+ newlines -> 2)
_RE_MULTI_BLANK = re.compile(r"\n{3,}")


def _caption_replacer(match):
    """Replace [caption]...[/caption] with <figure>...<figcaption>."""
    inner = match.group(1).strip()
    m = _RE_CAPTION_INNER.match(inner)
    if m:
        img_tag = m.group(1).strip()
        caption_text = m.group(2).strip()
        return (
            f'<figure class="wp-caption">{img_tag}'
            f"<figcaption>{caption_text}</figcaption></figure>"
        )
    # Fallback: wrap entire content in figure
    return f'<figure class="wp-caption">{inner}</figure>'


def clean_content(raw_content):
    """Apply all content transformations."""
    content = raw_content

    # 1. Strip Gutenberg block comments
    content = _RE_GUTENBERG_OPEN.sub("", content)
    content = _RE_GUTENBERG_CLOSE.sub("", content)

    # 2. Convert [caption] shortcodes to <figure>
    content = _RE_CAPTION.sub(_caption_replacer, content)

    # 3. Strip <!--more--> tags
    content = _RE_MORE.sub("", content)

    # 4. Remove empty paragraphs
    content = _RE_EMPTY_P.sub("", content)

    # 5. Clean up excessive whitespace while preserving structure
    content = _RE_MULTI_BLANK.sub("\n\n", content)

    # Trim leading/trailing whitespace
    content = content.strip()

    return content


# ---------------------------------------------------------------------------
# Image URL extraction
# ---------------------------------------------------------------------------

_RE_IMG_SRC = re.compile(r'<img\s[^>]*?src=["\']([^"\']+)["\']', re.IGNORECASE)
_RE_A_HREF = re.compile(r'<a\s[^>]*?href=["\']([^"\']+)["\']', re.IGNORECASE)


def _is_image_url(url):
    """Check if a URL points to an image file based on extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    _, ext = os.path.splitext(path)
    return ext in IMAGE_EXTENSIONS


def extract_image_urls(content):
    """Extract all image URLs from HTML content."""
    urls = set()
    # img src
    for m in _RE_IMG_SRC.finditer(content):
        urls.add(m.group(1))
    # a href pointing to images
    for m in _RE_A_HREF.finditer(content):
        href = m.group(1)
        if _is_image_url(href):
            urls.add(href)
    return urls


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_post_language(cat_nicenames):
    """
    Detect language for a post based on its category nicenames.
    Returns 'es' or 'en'.
    """
    has_entries_en = False
    has_entries_es = False
    es_count = 0
    en_count = 0

    for slug in cat_nicenames:
        if slug == "entries":
            has_entries_en = True
        if slug == "entries-es":
            has_entries_es = True

        if slug.endswith("-es"):
            es_count += 1
        else:
            en_count += 1

    # Clear signals first
    if has_entries_es and not has_entries_en:
        return "es"
    if has_entries_en and not has_entries_es:
        return "en"
    if has_entries_es and has_entries_en:
        # Both present — use majority of category suffixes
        if es_count > en_count:
            return "es"
        return "en"

    # No entries/entries-es signal: check if majority have -es suffix
    if es_count > en_count:
        return "es"

    return "en"


def detect_page_language(slug):
    """
    Detect language for a page based on its slug.
    Returns 'es' or 'en'.
    """
    if slug in SPANISH_PAGE_SLUGS_EXACT:
        return "es"

    for prefix in SPANISH_PAGE_SLUG_PREFIXES:
        if slug.startswith(prefix):
            return "es"

    for pat in SPANISH_PAGE_SLUG_PATTERNS:
        if pat.match(slug):
            return "es"

    return "en"


# ---------------------------------------------------------------------------
# Permalink construction
# ---------------------------------------------------------------------------

def get_primary_category(cat_nicenames):
    """
    Pick the first category slug that is NOT in the skip list.
    Falls back to 'uncategorized'.
    """
    for slug in cat_nicenames:
        if slug not in PERMALINK_SKIP_CATEGORIES:
            return slug
    return "uncategorized"


def build_post_permalink(lang, primary_cat, slug):
    return f"/{lang}/{primary_cat}/{slug}/"


def build_page_permalink(lang, slug):
    return f"/{lang}/{slug}/"


# ---------------------------------------------------------------------------
# Excerpt generation
# ---------------------------------------------------------------------------

_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_WHITESPACE = re.compile(r"\s+")


def generate_excerpt(content, max_words=55):
    """
    Generate a plain-text excerpt from HTML content.
    Strips tags, normalizes whitespace, truncates to max_words words.
    """
    text = _RE_HTML_TAG.sub(" ", content)
    text = html.unescape(text)
    text = _RE_WHITESPACE.sub(" ", text).strip()
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return " ".join(words)


# ---------------------------------------------------------------------------
# Featured image URL construction
# ---------------------------------------------------------------------------

def resolve_featured_image(thumbnail_id, attachment_map):
    """
    Given a thumbnail post ID, resolve it to a local asset path.
    Converts full WP URL to /assets/images/wp-content/uploads/...
    """
    if not thumbnail_id:
        return None
    try:
        tid = int(thumbnail_id)
    except (ValueError, TypeError):
        return None
    url = attachment_map.get(tid)
    if not url:
        return None
    # Convert https://iloveepoetry.org/wp-content/uploads/2013/02/img.png
    # to /assets/images/wp-content/uploads/2013/02/img.png
    parsed = urlparse(url)
    path = parsed.path  # /wp-content/uploads/2013/02/img.png
    return f"/assets/images{path}"


# ---------------------------------------------------------------------------
# Post metadata extraction from an <item> element
# ---------------------------------------------------------------------------

def extract_postmeta(item, key):
    """
    Return the meta_value for a given meta_key from <wp:postmeta> children.
    Returns None if not found.
    """
    for meta in item.xpath("wp:postmeta", namespaces=NAMESPACES):
        mk = _text(meta, "wp:meta_key")
        if mk == key:
            return _text(meta, "wp:meta_value")
    return None


def extract_item_data(item, attachment_map):
    """
    Extract all relevant fields from an <item> element.
    Returns a dict or None if the item should be skipped.
    Also returns a skip_reason string if skipped.
    """
    post_type = _text(item, "wp:post_type")
    status = _text(item, "wp:status")
    slug_raw = _text(item, "wp:post_name")

    # Decode URL-encoded slugs
    slug = unquote(slug_raw) if slug_raw else ""

    # Skip criteria
    if post_type not in ("post", "page"):
        return None, f"post_type={post_type}"
    if status != "publish":
        return None, f"status={status}"
    if not slug:
        return None, "empty slug"

    # Title
    title_el = item.find("title")
    title = (title_el.text or "").strip() if title_el is not None else ""
    title = html.unescape(title)

    # Date
    date_str = _text(item, "wp:post_date")  # YYYY-MM-DD HH:MM:SS

    # Post ID
    post_id_str = _text(item, "wp:post_id")
    try:
        post_id = int(post_id_str)
    except (ValueError, TypeError):
        post_id = 0

    # Content
    content_raw = _text(item, "content:encoded")

    # Excerpt
    excerpt_raw = _text(item, "excerpt:encoded")

    # Categories and tags
    categories = []
    cat_nicenames = []
    tags = []
    for cat_el in item.findall("category"):
        domain = cat_el.get("domain", "")
        nicename = cat_el.get("nicename", "")
        display_name = (cat_el.text or "").strip()
        if domain == "category":
            categories.append({"nicename": nicename, "name": display_name})
            cat_nicenames.append(nicename)
        elif domain == "post_tag":
            tags.append({"nicename": nicename, "name": display_name})

    # Featured image
    thumbnail_id = extract_postmeta(item, "_thumbnail_id")
    featured_image = resolve_featured_image(thumbnail_id, attachment_map)

    # Sticky
    is_sticky = _text(item, "wp:is_sticky")

    return {
        "title": title,
        "date": date_str,
        "slug": slug,
        "content_raw": content_raw,
        "excerpt_raw": excerpt_raw,
        "post_id": post_id,
        "post_type": post_type,
        "categories": categories,
        "cat_nicenames": cat_nicenames,
        "tags": tags,
        "featured_image": featured_image,
        "is_sticky": is_sticky == "1",
    }, None


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_post_file(data, lang, permalink, content):
    """Write a Jekyll post file to _posts/{lang}/YYYY-MM-DD-slug.html"""
    date_str = data["date"]  # "2013-02-19 15:30:00"
    date_prefix = date_str[:10] if len(date_str) >= 10 else "0000-00-00"

    filename = f"{date_prefix}-{data['slug']}.html"
    out_dir = POSTS_DIR / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    # Build front matter dict
    fm = {}
    fm["layout"] = "post"
    fm["title"] = data["title"]
    fm["date"] = date_str
    fm["lang"] = lang
    fm["categories"] = [c["nicename"] for c in data["categories"]]
    if data["tags"]:
        fm["tags"] = [t["nicename"] for t in data["tags"]]
    if data["featured_image"]:
        fm["featured_image"] = data["featured_image"]

    # Excerpt
    excerpt = data["excerpt_raw"]
    if not excerpt:
        excerpt = generate_excerpt(content)
    if excerpt:
        fm["excerpt"] = excerpt

    fm["permalink"] = permalink
    fm["wp_post_id"] = data["post_id"]

    front_matter = build_front_matter(fm)
    out_path.write_text(front_matter + "\n" + content + "\n", encoding="utf-8")
    return str(out_path)


def write_page_file(data, lang, permalink, content):
    """Write a Jekyll page file to _pages/{lang}/slug.html"""
    filename = f"{data['slug']}.html"
    out_dir = PAGES_DIR / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    fm = {}
    fm["layout"] = "page"
    fm["title"] = data["title"]
    fm["lang"] = lang
    fm["permalink"] = permalink
    fm["wp_post_id"] = data["post_id"]

    front_matter = build_front_matter(fm)
    out_path.write_text(front_matter + "\n" + content + "\n", encoding="utf-8")
    return str(out_path)


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------

def main():
    # Determine XML path
    if len(sys.argv) > 1:
        xml_path = sys.argv[1]
    else:
        xml_path = DEFAULT_XML_PATH

    if not os.path.isfile(xml_path):
        print(f"ERROR: XML file not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing WXR export: {xml_path}")
    print(f"Output site directory: {SITE_DIR}")

    # ------------------------------------------------------------------
    # Parse the XML
    # ------------------------------------------------------------------
    parser = etree.XMLParser(recover=True, huge_tree=True)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    channel = root.find("channel")

    if channel is None:
        print("ERROR: No <channel> element found in XML.", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Parse category hierarchy
    # ------------------------------------------------------------------
    print("Parsing category hierarchy...")
    category_map = parse_categories(channel)
    print(f"  Found {len(category_map)} categories")

    # ------------------------------------------------------------------
    # 2. Parse attachment map
    # ------------------------------------------------------------------
    print("Parsing attachment map...")
    attachment_map = parse_attachments(channel)
    print(f"  Found {len(attachment_map)} attachments")

    # ------------------------------------------------------------------
    # 3-7. Process each item
    # ------------------------------------------------------------------
    print("Processing items...")

    # Counters
    stats = {
        "total_items_processed": 0,
        "posts_en": 0,
        "posts_es": 0,
        "posts_other": 0,
        "pages_en": 0,
        "pages_es": 0,
        "skipped_items": [],
        "warnings": [],
    }

    url_map = {}
    all_image_urls = set()
    items_processed = 0

    for item in channel.xpath("item"):
        data, skip_reason = extract_item_data(item, attachment_map)

        if data is None:
            # Track skipped items (but don't track every attachment/nav_menu_item)
            post_type_raw = _text(item, "wp:post_type")
            if post_type_raw in ("post", "page"):
                title_el = item.find("title")
                title = (title_el.text or "").strip() if title_el is not None else ""
                pid = _text(item, "wp:post_id")
                stats["skipped_items"].append({
                    "post_id": pid,
                    "title": title[:80],
                    "reason": skip_reason,
                })
            continue

        items_processed += 1

        # Clean content
        content = clean_content(data["content_raw"])

        # Warn about empty content
        if not content.strip():
            stats["warnings"].append(
                f"Empty content: post_id={data['post_id']} title={data['title'][:60]}"
            )

        # Extract image URLs from content
        content_images = extract_image_urls(data["content_raw"])
        all_image_urls.update(content_images)
        if data["featured_image"]:
            all_image_urls.add(data["featured_image"])

        # Determine language
        if data["post_type"] == "post":
            lang = detect_post_language(data["cat_nicenames"])
        else:
            lang = detect_page_language(data["slug"])

        # Determine permalink
        if data["post_type"] == "post":
            primary_cat = get_primary_category(data["cat_nicenames"])
            permalink = build_post_permalink(lang, primary_cat, data["slug"])
        else:
            permalink = build_page_permalink(lang, data["slug"])

        # Write file
        if data["post_type"] == "post":
            file_path = write_post_file(data, lang, permalink, content)
            if lang == "es":
                stats["posts_es"] += 1
            elif lang == "en":
                stats["posts_en"] += 1
            else:
                stats["posts_other"] += 1
        else:
            file_path = write_page_file(data, lang, permalink, content)
            if lang == "es":
                stats["pages_es"] += 1
            else:
                stats["pages_en"] += 1

        # Build URL map entries
        # p_ID -> new permalink
        url_map[f"p_{data['post_id']}"] = permalink
        # slug/SLUG -> new permalink
        url_map[f"slug/{data['slug']}"] = permalink
        # Old URL patterns
        if data["post_type"] == "post":
            url_map[f"/?p={data['post_id']}"] = permalink
        elif data["post_type"] == "page":
            url_map[f"/?page_id={data['post_id']}"] = permalink
        # Old category/slug pattern for posts
        if data["post_type"] == "post" and data["cat_nicenames"]:
            old_primary = get_primary_category(data["cat_nicenames"])
            url_map[f"/{old_primary}/{data['slug']}/"] = permalink

    stats["total_items_processed"] = items_processed

    # ------------------------------------------------------------------
    # 8. Generate output files
    # ------------------------------------------------------------------

    # Ensure scripts dir exists
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # url_map.json
    url_map_path = SCRIPTS_DIR / "url_map.json"
    with open(url_map_path, "w", encoding="utf-8") as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)
    print(f"Wrote URL map: {url_map_path} ({len(url_map)} entries)")

    # image_urls.txt
    image_urls_path = SCRIPTS_DIR / "image_urls.txt"
    sorted_urls = sorted(all_image_urls)
    with open(image_urls_path, "w", encoding="utf-8") as f:
        for url in sorted_urls:
            f.write(url + "\n")
    print(f"Wrote image URLs: {image_urls_path} ({len(sorted_urls)} URLs)")

    # conversion_report.json
    report_path = SCRIPTS_DIR / "conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"Wrote conversion report: {report_path}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n=== Conversion Summary ===")
    print(f"  Total items processed: {stats['total_items_processed']}")
    print(f"  English posts:         {stats['posts_en']}")
    print(f"  Spanish posts:         {stats['posts_es']}")
    print(f"  Other/mixed posts:     {stats['posts_other']}")
    print(f"  English pages:         {stats['pages_en']}")
    print(f"  Spanish pages:         {stats['pages_es']}")
    print(f"  Skipped items:         {len(stats['skipped_items'])}")
    print(f"  Warnings:              {len(stats['warnings'])}")
    print(f"  Image URLs found:      {len(sorted_urls)}")
    print(f"  URL map entries:       {len(url_map)}")
    print("Done.")


if __name__ == "__main__":
    main()
