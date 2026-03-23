#!/usr/bin/env python3
"""
translate_all.py

Comprehensive translation management script for iloveepoetry.org.

Phase 1: Inventory - Find all untranslated posts and detect partial translations.
Phase 2: Translation template generation - Create translated counterpart files
          with properly translated front matter and the original body (for later
          AI-based body translation).
Phase 3: Bidirectional linking - Ensure every translation pair has cross-links.
Phase 4: Report - Summary statistics and JSON manifest output.

Usage:
    python3 scripts/translate_all.py              # Full run
    python3 scripts/translate_all.py --dry-run    # Preview without writing files
"""

import json
import os
import re
import sys
import unicodedata
import yaml
from pathlib import Path
from copy import deepcopy
from datetime import datetime
from difflib import SequenceMatcher

# ── Paths ────────────────────────────────────────────────────────────────────
SITE_ROOT = Path(__file__).resolve().parent.parent
EN_DIR    = SITE_ROOT / "_posts" / "en"
ES_DIR    = SITE_ROOT / "_posts" / "es"
MANIFEST  = SITE_ROOT / "scripts" / "translation_manifest.json"

DRY_RUN = "--dry-run" in sys.argv

# ── Front-matter regex ───────────────────────────────────────────────────────
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n(.*)", re.DOTALL)

# ── Category translation map (EN → ES) ──────────────────────────────────────
CATEGORY_MAP_EN_TO_ES = {
    "Entries":            "Entradas",
    "Adult":              "Adultos",
    "Teen":               "Adolescentes",
    "Children":           "Ninos",
    "aural":              "auditivo",
    "kinetic":            "cinetico",  # will be accented in output
    "mutable":            "mudable",
    "poetry":             "poesia",    # will be accented in output
    "responsive":         "sensible",
    "static":             "estatico",  # will be accented in output
    "scheduled":          "programado",
    "hypertext":          "hipertexto",
    "generative":         "generativo",
    "News":               "Noticias",
    "Reading Skill":      "Habilidad de lectura",
    "Writing Skill":      "Habilidad de escritura",
    "Listening Skill":    "Habilidad de escuchar",
    "Speaking Skill":     "Habilidad de hablar",
    "United States":      "Estados Unidos",
    "Uncategorized":      "Sin categorizar",
    "performance":        "rendimiento",
    "serial":             "serial",
    "dance":              "danza",
    "animated gif":       "gif animado",
    "bot":                "bot",
    "videogame":          "videojuego",
    "sound poetry":       "poesia sonora",
}

# Categories to keep as-is (years, tech names, collection names, etc.)
KEEP_AS_IS_PATTERNS = [
    r"^\d{4}$",           # years like 2001, 1999
    r"^Flash$",
    r"^DHTML$",
    r"^HTML$",
    r"^java$",
    r"^processing$",
    r"^javascript$",
    r"^Director$",
    r"^shockwave$",
    r"^Macromedia$",
    r"^Quicktime$",
    r"^CSS$",
    r"^iOS$",
    r"^Android$",
    r"^e-poetry$",
    r"^Electronic Literature",  # collection names
    r"^Cauldron",
    r"^Lettrisme$",
    r"^Frogger$",
    r"^ducthuan",
    r"^bunk$",
]

# Proper accent forms for categories
ACCENT_FIXES = {
    "cinetico":  "cin\u00e9tico",
    "poesia":    "poes\u00eda",
    "estatico":  "est\u00e1tico",
}

# ── Category translation map (ES → EN) ──────────────────────────────────────
CATEGORY_MAP_ES_TO_EN = {v: k for k, v in CATEGORY_MAP_EN_TO_ES.items()}


def parse_post(filepath: Path) -> dict | None:
    """Return parsed front matter dict + raw body, or None on failure."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  WARNING: Cannot read {filepath.name}: {exc}", file=sys.stderr)
        return None

    m = FRONT_MATTER_RE.match(text)
    if not m:
        return None

    fm_raw, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError as exc:
        print(f"  WARNING: YAML error in {filepath.name}: {exc}", file=sys.stderr)
        return None

    if not isinstance(fm, dict):
        return None

    fm["_body"] = body
    fm["_filepath"] = str(filepath)
    fm["_fm_raw"] = fm_raw
    return fm


def should_keep_category(cat: str) -> bool:
    """Return True if this category should be kept as-is (not translated)."""
    cat_str = str(cat)
    for pat in KEEP_AS_IS_PATTERNS:
        if re.match(pat, cat_str):
            return True
    return False


def translate_category_en_to_es(cat: str) -> str:
    """Translate a single EN category to ES."""
    cat_str = str(cat)
    if should_keep_category(cat_str):
        return cat_str
    translated = CATEGORY_MAP_EN_TO_ES.get(cat_str, cat_str)
    # Apply accent fixes
    translated = ACCENT_FIXES.get(translated, translated)
    return translated


def translate_category_es_to_en(cat: str) -> str:
    """Translate a single ES category to EN."""
    cat_str = str(cat)
    if should_keep_category(cat_str):
        return cat_str
    # Reverse accent fixes first
    reverse_accents = {v: k for k, v in ACCENT_FIXES.items()}
    lookup = reverse_accents.get(cat_str, cat_str)
    return CATEGORY_MAP_ES_TO_EN.get(lookup, CATEGORY_MAP_ES_TO_EN.get(cat_str, cat_str))


def translate_title_en_to_es(title: str) -> str:
    """Translate an EN title to ES.
    For entry posts: replace ' by ' with ' por ' and ' and ' with ' y '.
    For news/meta posts: keep as-is (would need real translation).
    """
    # Pattern: "Work Title" by Author Name
    # Replace the last ' by ' to avoid replacing 'by' inside work titles
    if '" by ' in title:
        title = title.replace('" by ', '" por ', 1)
    elif "' by " in title:
        title = title.replace("' by ", "' por ", 1)
    elif " by " in title:
        # Only replace if it looks like an attribution (comes after a quote or at end)
        title = title.replace(" by ", " por ", 1)

    # Replace ' and ' in author names (after 'por')
    if " por " in title:
        parts = title.split(" por ", 1)
        if len(parts) == 2:
            author_part = parts[1]
            author_part = author_part.replace(" and ", " y ")
            title = parts[0] + " por " + author_part

    return title


def translate_title_es_to_en(title: str) -> str:
    """Translate an ES title to EN."""
    if '" por ' in title:
        title = title.replace('" por ', '" by ', 1)
    elif "' por " in title:
        title = title.replace("' por ", "' by ", 1)
    elif " por " in title:
        title = title.replace(" por ", " by ", 1)

    if " by " in title:
        parts = title.split(" by ", 1)
        if len(parts) == 2:
            author_part = parts[1]
            author_part = author_part.replace(" y ", " and ")
            title = parts[0] + " by " + author_part

    return title


def translate_slug_en_to_es(slug: str) -> str:
    """Translate slug: replace 'by-' with 'por-' and '-and-' with '-y-'."""
    # Replace '-by-' for attribution
    slug = re.sub(r'-by-', '-por-', slug, count=1)
    # Replace '-and-' with '-y-' (in author names, typically after por)
    if '-por-' in slug:
        parts = slug.split('-por-', 1)
        if len(parts) == 2:
            author_part = parts[1].replace('-and-', '-y-')
            slug = parts[0] + '-por-' + author_part
    return slug


def translate_slug_es_to_en(slug: str) -> str:
    """Translate slug: replace 'por-' with 'by-' and '-y-' with '-and-'."""
    slug = re.sub(r'-por-', '-by-', slug, count=1)
    if '-by-' in slug:
        parts = slug.split('-by-', 1)
        if len(parts) == 2:
            author_part = parts[1].replace('-y-', '-and-')
            slug = parts[0] + '-by-' + author_part
    return slug


def build_es_permalink(en_permalink: str) -> str:
    """Build ES permalink from EN permalink.
    EN: /en/{dir}/{slug}/  ->  ES: /es/{dir}-es/{translated_slug}/
    Special cases: 'news' -> 'news-es', 'uncategorized' -> 'uncategorized',
                   'cfp' -> 'uncategorized'
    """
    parts = en_permalink.strip("/").split("/")
    if len(parts) < 3:
        # Fallback: just swap /en/ for /es/
        return en_permalink.replace("/en/", "/es/")

    lang, dir_seg, slug = parts[0], parts[1], "/".join(parts[2:])

    # Translate directory segment
    if dir_seg == "uncategorized":
        es_dir = "uncategorized"
    elif dir_seg == "cfp":
        es_dir = "uncategorized"
    elif dir_seg == "news" or dir_seg == "news-2":
        es_dir = "news-es"
    else:
        es_dir = f"{dir_seg}-es"

    # Translate slug
    es_slug = translate_slug_en_to_es(slug)

    return f"/es/{es_dir}/{es_slug}/"


def build_en_permalink(es_permalink: str) -> str:
    """Build EN permalink from ES permalink.
    ES: /es/{dir}/{slug}/  ->  EN: /en/{dir_without_es}/{translated_slug}/
    """
    parts = es_permalink.strip("/").split("/")
    if len(parts) < 3:
        return es_permalink.replace("/es/", "/en/")

    lang, dir_seg, slug = parts[0], parts[1], "/".join(parts[2:])

    # Remove -es suffix from directory
    if dir_seg.endswith("-es"):
        en_dir = dir_seg[:-3]
    elif dir_seg == "uncategorized":
        en_dir = "uncategorized"
    else:
        en_dir = dir_seg

    # Translate slug
    en_slug = translate_slug_es_to_en(slug)

    return f"/en/{en_dir}/{en_slug}/"


def build_es_filename(en_filename: str) -> str:
    """Build ES filename from EN filename.
    Translate slug portion: replace '-by-' with '-por-', '-and-' with '-y-'.
    """
    # Extract date prefix and slug
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", en_filename)
    if not match:
        return en_filename
    date_prefix = match.group(1)
    slug_ext = match.group(2)

    es_slug = translate_slug_en_to_es(slug_ext)
    return f"{date_prefix}-{es_slug}"


def build_en_filename(es_filename: str) -> str:
    """Build EN filename from ES filename."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", es_filename)
    if not match:
        return es_filename
    date_prefix = match.group(1)
    slug_ext = match.group(2)

    en_slug = translate_slug_es_to_en(slug_ext)
    return f"{date_prefix}-{en_slug}"


def format_yaml_value(value) -> str:
    """Format a value for YAML front matter output."""
    if isinstance(value, str):
        # Quote strings that contain special YAML chars
        if any(c in value for c in [':', '#', '{', '}', '[', ']', ',', '&', '*',
                                     '?', '|', '-', '<', '>', '=', '!', '%',
                                     '@', '`', '"', "'"]):
            # Use double quotes, escaping internal double quotes
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        if not value or value.lower() in ('true', 'false', 'null', 'yes', 'no'):
            return f'"{value}"'
        return f'"{value}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        return f'"{value}"'


def format_category(cat) -> str:
    """Format a category for YAML list output."""
    cat_str = str(cat)
    # Pure numeric years can be unquoted
    if re.match(r'^\d+$', cat_str):
        return cat_str
    # Everything else gets quoted
    escaped = cat_str.replace('"', '\\"')
    return f'"{escaped}"'


def build_front_matter(fm_dict: dict) -> str:
    """Build YAML front matter string from dict, preserving field order."""
    lines = ["---"]

    # Ordered fields
    field_order = [
        "layout", "author", "translator", "title", "date", "lang",
        "categories", "tags", "excerpt", "permalink", "wp_post_id",
        "translation", "featured_image", "work_url", "elmcip_url",
    ]

    for field in field_order:
        if field not in fm_dict:
            continue
        value = fm_dict[field]

        if field == "categories" and isinstance(value, list):
            lines.append("categories:")
            for cat in value:
                lines.append(f"- {format_category(cat)}")
        elif field == "tags" and isinstance(value, list):
            lines.append("tags:")
            for tag in value:
                escaped = str(tag).replace('"', '\\"')
                lines.append(f'- "{escaped}"')
        else:
            lines.append(f"{field}: {format_yaml_value(value)}")

    lines.append("---")
    return "\n".join(lines) + "\n"


def write_file(filepath: Path, content: str) -> None:
    """Write content to file (respects DRY_RUN)."""
    if DRY_RUN:
        print(f"  [DRY RUN] Would write: {filepath}")
        return
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")


def add_translation_field(filepath: Path, translation_permalink: str) -> bool:
    """Add a translation: field to an existing post's front matter.
    Returns True if the file was modified, False otherwise.
    """
    text = filepath.read_text(encoding="utf-8")
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return False

    fm_raw = m.group(1)
    body = m.group(2)

    # Check if translation already exists
    if re.search(r'^translation:', fm_raw, re.M):
        return False

    # Add translation field before the closing ---
    # Insert it after the last meaningful field
    new_fm = fm_raw.rstrip("\n") + f'\ntranslation: "{translation_permalink}"\n'
    new_text = f"---\n{new_fm}---\n{body}"

    if DRY_RUN:
        print(f"  [DRY RUN] Would add translation to: {filepath.name}")
        return True

    filepath.write_text(new_text, encoding="utf-8")
    return True


def normalize_slug(s: str) -> str:
    """Normalize a slug for comparison: lowercase, strip accents, remove
    common stop words and language-specific connectors."""
    s = s.lower().strip("/")
    # Remove accents
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Remove common connector differences
    s = s.replace("-por-", "-by-")
    s = s.replace("-y-", "-and-")
    s = s.replace("-de-", "-of-")
    s = s.replace("-del-", "-of-the-")
    s = s.replace("-la-", "-the-")
    s = s.replace("-el-", "-the-")
    s = s.replace("-los-", "-the-")
    s = s.replace("-las-", "-the-")
    s = s.replace("-en-", "-in-")
    s = s.replace("-es/", "/")
    s = s.replace("/es/", "/en/")
    return s


def match_orphans(en_orphans: dict, es_orphans: dict) -> list:
    """Match orphaned EN and ES posts that are counterparts but have no
    translation links. Returns list of (en_permalink, es_permalink) tuples.

    Uses multiple heuristics:
    1. Same featured_image (strongest signal)
    2. Same wp_post_id (only if unique)
    3. Slug similarity after normalization
    """
    matches = []
    matched_en = set()
    matched_es = set()

    # Strategy 1: Match by featured_image
    en_by_image = {}
    for perm, fm in en_orphans.items():
        img = fm.get("featured_image", "")
        if img:
            en_by_image.setdefault(img, []).append(perm)

    for es_perm, es_fm in es_orphans.items():
        img = es_fm.get("featured_image", "")
        if img and img in en_by_image:
            candidates = en_by_image[img]
            if len(candidates) == 1:
                en_perm = candidates[0]
                if en_perm not in matched_en and es_perm not in matched_es:
                    matches.append((en_perm, es_perm))
                    matched_en.add(en_perm)
                    matched_es.add(es_perm)

    # Strategy 2: Same wp_post_id (only useful if not shared)
    remaining_en = {p: fm for p, fm in en_orphans.items() if p not in matched_en}
    remaining_es = {p: fm for p, fm in es_orphans.items() if p not in matched_es}

    en_by_wpid = {}
    for perm, fm in remaining_en.items():
        wpid = str(fm.get("wp_post_id", ""))
        if wpid and wpid != "None":
            en_by_wpid.setdefault(wpid, []).append(perm)

    for es_perm, es_fm in list(remaining_es.items()):
        if es_perm in matched_es:
            continue
        wpid = str(es_fm.get("wp_post_id", ""))
        if wpid and wpid != "None" and wpid in en_by_wpid:
            candidates = en_by_wpid[wpid]
            if len(candidates) == 1:
                en_perm = candidates[0]
                if en_perm not in matched_en:
                    matches.append((en_perm, es_perm))
                    matched_en.add(en_perm)
                    matched_es.add(es_perm)

    # Strategy 3: Slug similarity
    remaining_en = {p: fm for p, fm in en_orphans.items() if p not in matched_en}
    remaining_es = {p: fm for p, fm in es_orphans.items() if p not in matched_es}

    # Build normalized slug index for EN
    en_norm_slugs = {}
    for en_perm, en_fm in remaining_en.items():
        parts = en_perm.strip("/").split("/")
        if len(parts) >= 3:
            slug = parts[-1]
            norm = normalize_slug(slug)
            en_norm_slugs[en_perm] = norm

    for es_perm, es_fm in remaining_es.items():
        if es_perm in matched_es:
            continue
        parts = es_perm.strip("/").split("/")
        if len(parts) >= 3:
            slug = parts[-1]
            norm = normalize_slug(slug)

            best_match = None
            best_score = 0

            for en_perm, en_norm in en_norm_slugs.items():
                if en_perm in matched_en:
                    continue
                score = SequenceMatcher(None, norm, en_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_match = en_perm

            # Require high similarity (0.7+) for slug matching
            if best_match and best_score >= 0.7:
                matches.append((best_match, es_perm))
                matched_en.add(best_match)
                matched_es.add(es_perm)

    # Strategy 4: For remaining ES orphans, check if translate_slug would produce
    # a filename that matches an existing EN file with no translation field.
    # This catches cases where the ES filename IS the direct slug-translation
    # of the EN filename.
    remaining_en = {p: fm for p, fm in en_orphans.items() if p not in matched_en}
    remaining_es = {p: fm for p, fm in es_orphans.items() if p not in matched_es}

    # Build a map from EN filename to EN permalink
    en_by_filename = {}
    for en_perm, en_fm in remaining_en.items():
        en_fname = Path(en_fm["_filepath"]).name
        en_by_filename[en_fname] = en_perm

    for es_perm, es_fm in list(remaining_es.items()):
        if es_perm in matched_es:
            continue
        es_fname = Path(es_fm["_filepath"]).name
        # Derive what the EN filename would be
        derived_en_fname = build_en_filename(es_fname)
        if derived_en_fname in en_by_filename:
            en_perm = en_by_filename[derived_en_fname]
            if en_perm not in matched_en:
                matches.append((en_perm, es_perm))
                matched_en.add(en_perm)
                matched_es.add(es_perm)

    return matches


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  TRANSLATE ALL - iloveepoetry.org")
    print("=" * 70)
    if DRY_RUN:
        print("  *** DRY RUN MODE - no files will be written ***")
    print()

    # ── Phase 1: Inventory ───────────────────────────────────────────────
    print("PHASE 1: INVENTORY")
    print("-" * 70)

    # Parse all EN and ES posts
    en_posts = {}  # permalink -> parsed fm dict
    es_posts = {}  # permalink -> parsed fm dict

    en_by_file = {}  # filename -> parsed fm dict
    es_by_file = {}  # filename -> parsed fm dict

    for filepath in sorted(EN_DIR.glob("*.html")):
        fm = parse_post(filepath)
        if fm is None:
            continue
        permalink = fm.get("permalink", "")
        en_posts[permalink] = fm
        en_by_file[filepath.name] = fm

    for filepath in sorted(ES_DIR.glob("*.html")):
        fm = parse_post(filepath)
        if fm is None:
            continue
        permalink = fm.get("permalink", "")
        es_posts[permalink] = fm
        es_by_file[filepath.name] = fm

    print(f"  EN posts parsed: {len(en_posts)}")
    print(f"  ES posts parsed: {len(es_posts)}")

    # Build lookup: permalink -> set of files pointing to it as translation
    en_translation_targets = {}  # EN permalink -> ES post that links to it
    es_translation_targets = {}  # ES permalink -> EN post that links to it

    for perm, fm in en_posts.items():
        tr = fm.get("translation", "")
        if tr:
            es_translation_targets[tr] = fm

    for perm, fm in es_posts.items():
        tr = fm.get("translation", "")
        if tr:
            en_translation_targets[tr] = fm

    # Find EN posts without translation field
    en_no_translation = {}
    for perm, fm in en_posts.items():
        if not fm.get("translation"):
            en_no_translation[perm] = fm

    # Find ES posts without translation field
    es_no_translation = {}
    for perm, fm in es_posts.items():
        if not fm.get("translation"):
            es_no_translation[perm] = fm

    print(f"  EN posts without 'translation' field: {len(en_no_translation)}")
    print(f"  ES posts without 'translation' field: {len(es_no_translation)}")

    # Among EN posts without translation, check if an ES counterpart exists
    # (from partial earlier runs with Claude Opus 4.6)
    en_has_es_counterpart = {}     # EN permalink -> ES fm dict
    en_needs_new_es = {}           # EN permalink -> EN fm dict (truly needs new ES file)

    for en_perm, en_fm in en_no_translation.items():
        # Check if any ES post points to this EN permalink
        if en_perm in en_translation_targets:
            es_fm = en_translation_targets[en_perm]
            en_has_es_counterpart[en_perm] = es_fm
        else:
            en_needs_new_es[en_perm] = en_fm

    # Similarly for ES posts without translation
    es_has_en_counterpart = {}
    es_needs_new_en = {}

    for es_perm, es_fm in es_no_translation.items():
        if es_perm in es_translation_targets:
            en_fm = es_translation_targets[es_perm]
            es_has_en_counterpart[es_perm] = en_fm
        else:
            es_needs_new_en[es_perm] = es_fm

    print(f"\n  EN without translation, but ES counterpart exists: {len(en_has_es_counterpart)}")
    print(f"  EN without translation, needs NEW ES file:         {len(en_needs_new_es)}")
    print(f"  ES without translation, but EN counterpart exists: {len(es_has_en_counterpart)}")
    print(f"  ES without translation, needs NEW EN file:         {len(es_needs_new_en)}")

    # ── Phase 1b: Orphan matching ────────────────────────────────────────
    # Try to match EN and ES orphans that are actually counterparts
    # but neither has a translation field
    print("\n  Phase 1b: Matching orphaned pairs...")
    orphan_matches = match_orphans(en_needs_new_es, es_needs_new_en)
    print(f"  Matched {len(orphan_matches)} orphan pairs:")
    for en_perm, es_perm in orphan_matches:
        print(f"    {en_perm} <-> {es_perm}")

    # Move matched orphans from "needs new" to "has counterpart"
    for en_perm, es_perm in orphan_matches:
        if en_perm in en_needs_new_es and es_perm in es_needs_new_en:
            en_has_es_counterpart[en_perm] = es_needs_new_en[es_perm]
            es_has_en_counterpart[es_perm] = en_needs_new_es[en_perm]
            del en_needs_new_es[en_perm]
            del es_needs_new_en[es_perm]

    print(f"\n  After orphan matching:")
    print(f"  EN truly needs NEW ES file:   {len(en_needs_new_es)}")
    print(f"  ES truly needs NEW EN file:   {len(es_needs_new_en)}")
    print()

    # ── Phase 2: Translation template generation ─────────────────────────
    print("PHASE 2: TRANSLATION TEMPLATE GENERATION")
    print("-" * 70)

    files_created = []
    manifest_entries = []
    late_matched_pairs = []  # (source_filepath, target_permalink, source_permalink)

    # 2a. Create ES files for EN posts that need them
    for en_perm, en_fm in sorted(en_needs_new_es.items()):
        en_filepath = Path(en_fm["_filepath"])
        en_filename = en_filepath.name

        # Build ES filename
        es_filename = build_es_filename(en_filename)
        es_filepath_target = ES_DIR / es_filename

        # Check for collision: if the target ES file already exists, it may be the
        # actual ES counterpart that just doesn't have a translation field
        if es_filepath_target.exists():
            existing_fm = parse_post(es_filepath_target)
            if existing_fm and not existing_fm.get("translation"):
                # This existing ES file is likely the counterpart - link them
                es_perm_existing = existing_fm.get("permalink", "")
                late_matched_pairs.append((en_filepath, es_perm_existing, en_perm))
                print(f"  Matched (collision): {en_filename} <-> {es_filename}")
                continue
            else:
                base, ext = os.path.splitext(es_filename)
                es_filename = f"{base}-2{ext}"
                es_filepath_target = ES_DIR / es_filename

        # Build ES front matter
        es_fm = {}
        es_fm["layout"] = "post"
        es_fm["author"] = en_fm.get("author", "Leonardo Flores")
        es_fm["translator"] = "Claude Opus 4.6"

        # Translate title
        en_title = en_fm.get("title", "")
        es_fm["title"] = translate_title_en_to_es(en_title)

        # Keep same date
        es_fm["date"] = en_fm.get("date", "")
        es_fm["lang"] = "es"

        # Translate categories
        en_cats = en_fm.get("categories", [])
        es_cats = [translate_category_en_to_es(str(c)) for c in en_cats]
        es_fm["categories"] = es_cats

        # Keep tags
        es_fm["tags"] = en_fm.get("tags", [])

        # Excerpt: keep as-is (will be translated separately)
        if en_fm.get("excerpt"):
            es_fm["excerpt"] = en_fm["excerpt"]

        # Build ES permalink
        es_permalink = build_es_permalink(en_perm)
        es_fm["permalink"] = es_permalink

        # Keep wp_post_id
        if en_fm.get("wp_post_id"):
            es_fm["wp_post_id"] = en_fm["wp_post_id"]

        # Set translation pointing back to EN
        es_fm["translation"] = en_perm

        # Keep featured_image, work_url, elmcip_url
        if en_fm.get("featured_image"):
            es_fm["featured_image"] = en_fm["featured_image"]
        if en_fm.get("work_url"):
            es_fm["work_url"] = en_fm["work_url"]
        if en_fm.get("elmcip_url"):
            es_fm["elmcip_url"] = en_fm["elmcip_url"]

        # Build file content
        front_matter_str = build_front_matter(es_fm)
        body = en_fm.get("_body", "")
        body_with_comment = f"<!-- Body awaiting translation by Claude Opus 4.6 -->\n{body}"
        file_content = front_matter_str + "\n" + body_with_comment

        write_file(es_filepath_target, file_content)
        files_created.append({
            "source": str(en_filepath),
            "target": str(es_filepath_target),
            "direction": "en->es",
            "en_permalink": en_perm,
            "es_permalink": es_permalink,
        })

        manifest_entries.append({
            "source_file": str(en_filepath),
            "target_file": str(es_filepath_target),
            "source_lang": "en",
            "target_lang": "es",
            "source_permalink": en_perm,
            "target_permalink": es_permalink,
            "title": en_fm.get("title", ""),
            "needs_body_translation": True,
            "word_count": len(re.sub(r"<[^>]+>", " ", body).split()),
        })

        print(f"  Created: {es_filename}")

    # 2b. Create EN files for ES-only posts that need them
    for es_perm, es_fm in sorted(es_needs_new_en.items()):
        es_filepath = Path(es_fm["_filepath"])
        es_filename = es_filepath.name

        en_filename = build_en_filename(es_filename)
        en_filepath_new = EN_DIR / en_filename

        # Check for collision: if the target file already exists, it may be the actual
        # EN counterpart that just doesn't have a translation field.
        if en_filepath_new.exists():
            existing_fm = parse_post(en_filepath_new)
            if existing_fm and not existing_fm.get("translation"):
                # This existing EN file is likely the counterpart - link them
                # instead of creating a new file
                en_perm_existing = existing_fm.get("permalink", "")
                late_matched_pairs.append((en_filepath_new, es_perm, en_perm_existing))
                print(f"  Matched (collision): {en_filename} <-> {es_filename}")
                continue
            else:
                # Existing file has a different translation target or is unrelated
                base, ext = os.path.splitext(en_filename)
                en_filename = f"{base}-2{ext}"
                en_filepath_new = EN_DIR / en_filename

        # Build EN front matter
        en_fm_new = {}
        en_fm_new["layout"] = "post"
        en_fm_new["author"] = es_fm.get("author", "Leonardo Flores")
        en_fm_new["translator"] = "Claude Opus 4.6"

        # Translate title
        es_title = es_fm.get("title", "")
        en_fm_new["title"] = translate_title_es_to_en(es_title)

        en_fm_new["date"] = es_fm.get("date", "")
        en_fm_new["lang"] = "en"

        # Translate categories
        es_cats = es_fm.get("categories", [])
        en_cats = [translate_category_es_to_en(str(c)) for c in es_cats]
        en_fm_new["categories"] = en_cats

        en_fm_new["tags"] = es_fm.get("tags", [])

        if es_fm.get("excerpt"):
            en_fm_new["excerpt"] = es_fm["excerpt"]

        # Build EN permalink
        en_permalink = build_en_permalink(es_perm)
        en_fm_new["permalink"] = en_permalink

        if es_fm.get("wp_post_id"):
            en_fm_new["wp_post_id"] = es_fm["wp_post_id"]

        en_fm_new["translation"] = es_perm

        if es_fm.get("featured_image"):
            en_fm_new["featured_image"] = es_fm["featured_image"]
        if es_fm.get("work_url"):
            en_fm_new["work_url"] = es_fm["work_url"]
        if es_fm.get("elmcip_url"):
            en_fm_new["elmcip_url"] = es_fm["elmcip_url"]

        front_matter_str = build_front_matter(en_fm_new)
        body = es_fm.get("_body", "")
        body_with_comment = f"<!-- Body awaiting translation by Claude Opus 4.6 -->\n{body}"
        file_content = front_matter_str + "\n" + body_with_comment

        write_file(en_filepath_new, file_content)
        files_created.append({
            "source": str(es_filepath),
            "target": str(en_filepath_new),
            "direction": "es->en",
            "es_permalink": es_perm,
            "en_permalink": en_permalink,
        })

        manifest_entries.append({
            "source_file": str(es_filepath),
            "target_file": str(en_filepath_new),
            "source_lang": "es",
            "target_lang": "en",
            "source_permalink": es_perm,
            "target_permalink": en_permalink,
            "title": es_fm.get("title", ""),
            "needs_body_translation": True,
            "word_count": len(re.sub(r"<[^>]+>", " ", body).split()),
        })

        print(f"  Created: {en_filename}")

    print(f"\n  Total new files created: {len(files_created)}")
    print(f"  Late-matched collision pairs: {len(late_matched_pairs)}")
    print()

    # ── Phase 3: Bidirectional linking ───────────────────────────────────
    print("PHASE 3: BIDIRECTIONAL LINKING")
    print("-" * 70)

    links_added = 0

    # 3-pre. Handle late-matched collision pairs (found during file creation)
    # Build a permalink-to-filepath lookup from all parsed posts
    all_perm_to_filepath = {}
    for perm, fm in en_posts.items():
        all_perm_to_filepath[perm] = Path(fm["_filepath"])
    for perm, fm in es_posts.items():
        all_perm_to_filepath[perm] = Path(fm["_filepath"])

    for source_filepath, target_permalink, source_permalink in late_matched_pairs:
        if add_translation_field(source_filepath, target_permalink):
            links_added += 1
            print(f"  Added link (collision match): {source_filepath.name} -> {target_permalink}")

        # Also link the target file back to the source
        target_fp = all_perm_to_filepath.get(target_permalink)
        if target_fp and add_translation_field(target_fp, source_permalink):
            links_added += 1
            print(f"  Added link (collision match): {target_fp.name} -> {source_permalink}")

    # 3a. For newly created files, add translation link to the SOURCE files
    for entry in files_created:
        if entry["direction"] == "en->es":
            source_path = Path(entry["source"])
            target_permalink = entry["es_permalink"]
        else:
            source_path = Path(entry["source"])
            target_permalink = entry["en_permalink"]

        if add_translation_field(source_path, target_permalink):
            links_added += 1
            print(f"  Added link to: {source_path.name} -> {target_permalink}")

    # 3b. For EN posts that already have ES counterpart but missing translation field
    for en_perm, es_fm in en_has_es_counterpart.items():
        en_fm = en_no_translation[en_perm]
        en_filepath = Path(en_fm["_filepath"])
        es_permalink = es_fm.get("permalink", "")

        if es_permalink and add_translation_field(en_filepath, es_permalink):
            links_added += 1
            print(f"  Added link to: {en_filepath.name} -> {es_permalink}")

    # 3c. For ES posts that already have EN counterpart but missing translation field
    for es_perm, en_fm in es_has_en_counterpart.items():
        es_fm_local = es_no_translation[es_perm]
        es_filepath = Path(es_fm_local["_filepath"])
        en_permalink = en_fm.get("permalink", "")

        if en_permalink and add_translation_field(es_filepath, en_permalink):
            links_added += 1
            print(f"  Added link to: {es_filepath.name} -> {en_permalink}")

    # 3d. Scan ALL posts for one-way links (A links to B, but B doesn't link back)
    # Re-parse all files to pick up changes
    print("\n  Checking all posts for one-way links...")
    one_way_fixes = 0

    all_posts_fresh = {}
    for filepath in sorted(EN_DIR.glob("*.html")):
        fm = parse_post(filepath)
        if fm:
            all_posts_fresh[fm.get("permalink", "")] = fm

    for filepath in sorted(ES_DIR.glob("*.html")):
        fm = parse_post(filepath)
        if fm:
            all_posts_fresh[fm.get("permalink", "")] = fm

    for perm, fm in all_posts_fresh.items():
        tr = fm.get("translation", "")
        if not tr:
            continue

        # Check if the target post exists and links back
        target_fm = all_posts_fresh.get(tr)
        if target_fm is None:
            continue

        target_tr = target_fm.get("translation", "")
        if target_tr:
            # Already has a translation link
            continue

        # Target exists but doesn't link back - add the link
        target_filepath = Path(target_fm["_filepath"])
        if add_translation_field(target_filepath, perm):
            one_way_fixes += 1
            print(f"  Fixed one-way link: {target_filepath.name} -> {perm}")

    links_added += one_way_fixes

    print(f"\n  Total bidirectional links added/fixed: {links_added}")
    print()

    # ── Phase 4: Report ──────────────────────────────────────────────────
    print("PHASE 4: REPORT")
    print("-" * 70)

    # Write manifest
    manifest_data = {
        "generated_at": datetime.now().isoformat(),
        "dry_run": DRY_RUN,
        "summary": {
            "new_files_created": len(files_created),
            "en_to_es_files": sum(1 for f in files_created if f["direction"] == "en->es"),
            "es_to_en_files": sum(1 for f in files_created if f["direction"] == "es->en"),
            "bidirectional_links_added": links_added,
            "total_words_needing_translation": sum(e["word_count"] for e in manifest_entries),
        },
        "files_created": files_created,
        "translation_tasks": manifest_entries,
    }

    if not DRY_RUN:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        print(f"  Manifest written to: {MANIFEST}")
    else:
        print(f"  [DRY RUN] Manifest would be written to: {MANIFEST}")

    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  New files created:          {len(files_created)}")
    print(f"    EN -> ES:                 {manifest_data['summary']['en_to_es_files']}")
    print(f"    ES -> EN:                 {manifest_data['summary']['es_to_en_files']}")
    print(f"  Bidirectional links added:  {links_added}")
    print(f"  Words needing translation:  {manifest_data['summary']['total_words_needing_translation']:,}")
    print("=" * 70)

    if DRY_RUN:
        print("\n  *** This was a DRY RUN. No files were modified. ***")
        print("  *** Run without --dry-run to apply changes. ***")


if __name__ == "__main__":
    main()
