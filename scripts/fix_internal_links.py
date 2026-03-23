#!/usr/bin/env python3
"""
fix_internal_links.py

Replaces all internal links pointing to iloveepoetry.org with relative links
to the new Jekyll site at /iloveepoetry/.

Handles:
  - ?page_id=XXXX  -> mapped Jekyll permalink
  - ?p=NNN / ?post=NNN -> find post by wp_post_id in front matter
  - ?cat=NNN, ?tag=SLUG, ?author=NNN, ?s=QUERY, ?m=YYYYMM -> log only
  - wp-content/uploads/... -> /iloveepoetry/assets/images/wp-content/uploads/...
  - wp-admin/... -> log only
  - bare http://iloveepoetry.org or http://iloveepoetry.org/ -> /iloveepoetry/
  - path-based URLs -> attempt slug matching
  - Spanish posts get Spanish page permalinks when available
"""

import os
import re
import sys
import yaml
from collections import defaultdict

# --- Configuration ---

SITE_ROOT = "/Users/floresll/Desktop/iloveepoetry"
BASEURL = "/iloveepoetry"

POSTS_EN_DIR = os.path.join(SITE_ROOT, "_posts", "en")
POSTS_ES_DIR = os.path.join(SITE_ROOT, "_posts", "es")
PAGES_EN_DIR = os.path.join(SITE_ROOT, "_pages", "en")
PAGES_ES_DIR = os.path.join(SITE_ROOT, "_pages", "es")
UPLOADS_DIR = os.path.join(SITE_ROOT, "assets", "images", "wp-content", "uploads")

# page_id -> English Jekyll permalink
PAGE_ID_MAP = {
    2607: "/en/about-2/",
    15276: "/en/about/",
    7913: "/en/agrippa/",
    6835: "/en/avenues-access-exhibition-mla-2013/",
    7915: "/en/beehive/",
    6803: "/en/cauldron-and-net-volumes-1-4-test-master-post/",
    5839: "/en/contribute/",
    6626: "/en/electronic-literature-collection-volume-2-works-coverednot-covered/",
    6799: "/en/elo-2012-media-art-show/",
    2674: "/en/feedback/",
    7911: "/en/frequency-by-scott-rettberg/",
    2645: "/en/guidelines/",
    9054: "/en/index-a-to-z-by-title/",
    7918: "/en/marble-springs/",
    6862: "/en/new-media-writing-prize-2012-shortlist/",
    14979: "/en/nube-de-categoria/",
    5114: "/en/open-cfp/",
    7898: "/en/poems-that-go/",
    2591: "/en/resources-reviewed/",
    2: "/en/sample-page/",
    5513: "/en/subscribe/",
    2593: "/en/tags-typology/",
    7907: "/en/taroko-gorge-remixes-series/",
    7422: "/en/technique-remix/",
    6602: "/en/the-electronic-literature-collection-volume-1/",
    6580: "/en/the-team/",
    11381: "/en/welcome-to-i-love-e-poetry/",
    15002: "/en/welcome/",
}

# Map English page_id -> Spanish permalink (manually matched by page content/name)
EN_TO_ES_PAGE = {
    2607: "/es/acerca-de/",           # about-2 -> acerca-de
    15276: "/es/acerca-de/",          # about -> acerca-de
    7913: "/es/lectura-de-agripa-una-serie-de-4-partes/",  # agrippa
    6835: "/es/exposicion-de-avenues-of-access-en-mla-2013/",  # avenues of access
    7915: "/es/beehive-3/",           # beehive
    6803: "/es/caldero-y-red/",       # cauldron-and-net
    5839: "/es/contribuir/",          # contribute
    6626: "/es/coleccion-electronica-de-literatura-volumen-2/",  # ELC vol 2
    6799: "/es/elo-2012-media-art-show-2/",  # ELO 2012
    2674: "/es/contacto/",            # feedback -> contacto
    7911: "/es/la-serie-frequency/",  # frequency
    2645: "/es/directrices-para-el-envio/",  # guidelines
    9054: "/es/indice-a-a-z-por-titulo/",  # index a-z
    7918: "/es/marble-springs-2/",    # marble springs
    6862: "/es/nuevas-listas-de-premios-de-redaccion-de-medios/",  # new media writing prize
    5114: "/es/cfp-abierto/",         # open CFP
    7898: "/es/poems-that-go-3/",     # poems that go
    2591: "/es/recursos-revisados/",  # resources reviewed
    5513: "/es/suscribete/",          # subscribe
    2593: "/es/recurso-poesia-electronica-como-codigo-y-combinacion-de-datos/",  # tags-typology
    7907: "/es/taroko-gorge-y-sus-remezclas/",  # taroko gorge remixes
    6602: "/es/the-electronic-literature-collection-volume-1-2/",  # ELC vol 1
    6580: "/es/el-equipo/",           # the team
    11381: "/es/bienvenido-a-i-love-e-poetry/",  # welcome to i love e-poetry
    15002: "/es/bienvenido/",         # welcome
    14979: "/es/sobre-este-proyecto/", # nube-de-categoria -> sobre-este-proyecto
}

# --- Regex patterns ---

# Match any iloveepoetry.org URL (http/https, www optional)
# Captures the path+query portion after the domain
ILOVEEPOETRY_URL_RE = re.compile(
    r'https?://(?:www\.)?iloveepoetry\.org'
    r'(/[^"\'<>\s]*|/?\?[^"\'<>\s]*)?'
    r'(?=["\'\s<>]|$)'
)

# Sub-patterns for query string types
PAGE_ID_RE = re.compile(r'^\?page_id=(\d+)/?$')
POST_P_RE = re.compile(r'^\?p=(\d+)/?$')
POST_POST_RE = re.compile(r'^\?post=(\d+)/?$')
CAT_RE = re.compile(r'^\?cat=(\d+)')
TAG_RE = re.compile(r'^\?tag=([^&\s"\'<>]+)')
AUTHOR_RE = re.compile(r'^\?author=(\d+)')
SEARCH_RE = re.compile(r'^\?s=([^"\'<>\s]+)')
MONTH_RE = re.compile(r'^\?m=(\d+)')
WP_CONTENT_RE = re.compile(r'^/wp-content/uploads/(.+)$')
WP_ADMIN_RE = re.compile(r'^/wp-admin(/.*)?$')


# --- Helper functions ---

def parse_front_matter(filepath):
    """Parse YAML front matter from a file. Returns dict or None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def build_post_id_map():
    """
    Build a mapping from wp_post_id -> permalink for all posts.
    Returns two dicts: one for en posts, one for es posts.
    """
    en_map = {}
    es_map = {}

    for dir_path, target_map in [(POSTS_EN_DIR, en_map), (POSTS_ES_DIR, es_map)]:
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".html"):
                continue
            fpath = os.path.join(dir_path, fname)
            fm = parse_front_matter(fpath)
            if fm and "wp_post_id" in fm and "permalink" in fm:
                wp_id = int(fm["wp_post_id"])
                target_map[wp_id] = fm["permalink"]

    return en_map, es_map


def build_page_id_map_from_files():
    """
    Build a mapping from wp_post_id -> permalink for ALL pages (en and es),
    reading from actual files.
    """
    en_map = {}
    es_map = {}

    for dir_path, target_map in [(PAGES_EN_DIR, en_map), (PAGES_ES_DIR, es_map)]:
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".html"):
                continue
            fpath = os.path.join(dir_path, fname)
            fm = parse_front_matter(fpath)
            if fm and "wp_post_id" in fm and "permalink" in fm:
                wp_id = int(fm["wp_post_id"])
                target_map[wp_id] = fm["permalink"]

    return en_map, es_map


def check_upload_exists(rel_path):
    """Check if a wp-content/uploads file exists locally."""
    local_path = os.path.join(UPLOADS_DIR, rel_path)
    return os.path.isfile(local_path)


def get_all_html_files():
    """Get all HTML files to scan."""
    files = []
    for directory in [POSTS_EN_DIR, POSTS_ES_DIR, PAGES_EN_DIR, PAGES_ES_DIR]:
        if os.path.isdir(directory):
            for fname in sorted(os.listdir(directory)):
                if fname.endswith(".html"):
                    files.append(os.path.join(directory, fname))
    return files


def detect_file_lang(filepath):
    """Detect if a file is English or Spanish based on its path."""
    if "/_posts/es/" in filepath or "/_pages/es/" in filepath:
        return "es"
    return "en"


# --- Main processing ---

def main():
    print("=" * 70)
    print("  fix_internal_links.py")
    print("  Replacing iloveepoetry.org links with local Jekyll links")
    print("=" * 70)
    print()

    # Build lookup maps
    print("Building post ID map from front matter...")
    post_en_map, post_es_map = build_post_id_map()
    print(f"  Found {len(post_en_map)} English posts with wp_post_id")
    print(f"  Found {len(post_es_map)} Spanish posts with wp_post_id")

    print("Building page ID map from files...")
    page_en_from_files, page_es_from_files = build_page_id_map_from_files()
    print(f"  Found {len(page_en_from_files)} English pages with wp_post_id")
    print(f"  Found {len(page_es_from_files)} Spanish pages with wp_post_id")

    # Merge all post IDs (en + es) for general lookup
    all_post_map = {}
    all_post_map.update(post_en_map)
    all_post_map.update(post_es_map)

    # Get all files
    files = get_all_html_files()
    print(f"\nScanning {len(files)} HTML files...\n")

    # Stats
    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "page_id_replaced": 0,
        "post_id_replaced": 0,
        "wp_content_replaced": 0,
        "homepage_replaced": 0,
        "path_slug_replaced": 0,
    }

    # Unresolved logs
    unresolved = defaultdict(list)

    for filepath in files:
        stats["files_scanned"] += 1
        file_lang = detect_file_lang(filepath)
        rel_file = os.path.relpath(filepath, SITE_ROOT)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  ERROR reading {rel_file}: {e}")
            continue

        original_content = content
        replacements_in_file = [0]  # use list for mutability in closure

        def replace_url(match):
            full_url = match.group(0)
            path_part = match.group(1) or ""

            # Normalize: strip trailing whitespace
            path_part = path_part.rstrip()

            # -- Case: bare homepage URL (empty path or just /) --
            if path_part == "" or path_part == "/":
                replacements_in_file[0] += 1
                stats["homepage_replaced"] += 1
                return f"{BASEURL}/"

            # -- Case: Query string URLs --
            if path_part.startswith("?") or path_part.startswith("/?"):
                query = path_part.lstrip("/")

                # page_id
                m = PAGE_ID_RE.match(query)
                if m:
                    pid = int(m.group(1))
                    # For Spanish files, prefer Spanish permalink
                    if file_lang == "es" and pid in EN_TO_ES_PAGE:
                        permalink = EN_TO_ES_PAGE[pid]
                        replacements_in_file[0] += 1
                        stats["page_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in PAGE_ID_MAP:
                        permalink = PAGE_ID_MAP[pid]
                        replacements_in_file[0] += 1
                        stats["page_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    # Check if it's a page_id from files not in the hardcoded map
                    elif pid in page_en_from_files:
                        if file_lang == "es" and pid in page_es_from_files:
                            permalink = page_es_from_files[pid]
                        else:
                            permalink = page_en_from_files[pid]
                        replacements_in_file[0] += 1
                        stats["page_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    else:
                        unresolved["page_id_unknown"].append((rel_file, full_url))
                        return full_url

                # ?p=NNN
                m = POST_P_RE.match(query)
                if m:
                    pid = int(m.group(1))
                    if file_lang == "es" and pid in post_es_map:
                        permalink = post_es_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in post_en_map:
                        permalink = post_en_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in all_post_map:
                        permalink = all_post_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    # Also check pages
                    elif pid in page_en_from_files:
                        if file_lang == "es" and pid in page_es_from_files:
                            permalink = page_es_from_files[pid]
                        else:
                            permalink = page_en_from_files[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    else:
                        unresolved["post_p_unknown"].append((rel_file, full_url))
                        return full_url

                # ?post=NNN
                m = POST_POST_RE.match(query)
                if m:
                    pid = int(m.group(1))
                    if file_lang == "es" and pid in post_es_map:
                        permalink = post_es_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in post_en_map:
                        permalink = post_en_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in all_post_map:
                        permalink = all_post_map[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    elif pid in page_en_from_files:
                        if file_lang == "es" and pid in page_es_from_files:
                            permalink = page_es_from_files[pid]
                        else:
                            permalink = page_en_from_files[pid]
                        replacements_in_file[0] += 1
                        stats["post_id_replaced"] += 1
                        return f"{BASEURL}{permalink}"
                    else:
                        unresolved["post_post_unknown"].append((rel_file, full_url))
                        return full_url

                # ?cat=NNN
                m = CAT_RE.match(query)
                if m:
                    unresolved["cat"].append((rel_file, full_url))
                    return full_url

                # ?tag=SLUG
                m = TAG_RE.match(query)
                if m:
                    unresolved["tag"].append((rel_file, full_url))
                    return full_url

                # ?author=NNN
                m = AUTHOR_RE.match(query)
                if m:
                    unresolved["author"].append((rel_file, full_url))
                    return full_url

                # ?s=QUERY
                m = SEARCH_RE.match(query)
                if m:
                    unresolved["search"].append((rel_file, full_url))
                    return full_url

                # ?m=YYYYMM
                m = MONTH_RE.match(query)
                if m:
                    unresolved["month_archive"].append((rel_file, full_url))
                    return full_url

                # Unknown query string
                unresolved["unknown_query"].append((rel_file, full_url))
                return full_url

            # -- Case: wp-content/uploads/ --
            m = WP_CONTENT_RE.match(path_part)
            if m:
                upload_path = m.group(1)
                # Clean up any trailing junk like [/embed]
                clean_path = upload_path.split("[")[0].rstrip("/")
                if check_upload_exists(clean_path):
                    replacements_in_file[0] += 1
                    stats["wp_content_replaced"] += 1
                    return f"{BASEURL}/assets/images/wp-content/uploads/{clean_path}"
                else:
                    unresolved["wp_content_missing"].append((rel_file, full_url))
                    return full_url

            # -- Case: wp-admin/ --
            m = WP_ADMIN_RE.match(path_part)
            if m:
                unresolved["wp_admin"].append((rel_file, full_url))
                return full_url

            # -- Case: path-based URL (e.g. /viz/AWY/) --
            unresolved["path_based"].append((rel_file, full_url))
            return full_url

        # Apply replacements
        content = ILOVEEPOETRY_URL_RE.sub(replace_url, content)

        if content != original_content:
            stats["files_modified"] += 1
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            if replacements_in_file[0] > 0:
                print(f"  Modified: {rel_file} ({replacements_in_file[0]} replacements)")

    # --- Summary ---

    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print()
    print(f"  Total files scanned:   {stats['files_scanned']}")
    print(f"  Total files modified:  {stats['files_modified']}")
    print()

    total_replaced = (
        stats["page_id_replaced"]
        + stats["post_id_replaced"]
        + stats["wp_content_replaced"]
        + stats["homepage_replaced"]
        + stats["path_slug_replaced"]
    )
    print(f"  Total links replaced:  {total_replaced}")
    print(f"    page_id links:       {stats['page_id_replaced']}")
    print(f"    post/p links:        {stats['post_id_replaced']}")
    print(f"    wp-content links:    {stats['wp_content_replaced']}")
    print(f"    homepage links:      {stats['homepage_replaced']}")
    print(f"    path/slug links:     {stats['path_slug_replaced']}")
    print()

    total_unresolved = sum(len(v) for v in unresolved.values())
    print(f"  Total links not replaced: {total_unresolved}")
    print()

    if unresolved:
        print("-" * 70)
        print("  UNRESOLVED LINKS (left unchanged)")
        print("-" * 70)

        for link_type in sorted(unresolved.keys()):
            items = unresolved[link_type]
            # Deduplicate URLs for summary
            url_counts = defaultdict(list)
            for fpath, url in items:
                url_counts[url].append(fpath)

            print(f"\n  [{link_type}] ({len(items)} occurrences, {len(url_counts)} unique URLs)")
            for url, fpaths in sorted(url_counts.items(), key=lambda x: -len(x[1])):
                print(f"    {url}")
                print(f"      in {len(fpaths)} file(s): {fpaths[0]}", end="")
                if len(fpaths) > 1:
                    print(f" (and {len(fpaths)-1} more)")
                else:
                    print()

    print()
    print("Done.")


if __name__ == "__main__":
    main()
