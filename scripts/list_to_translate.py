#!/usr/bin/env python3
"""
list_to_translate.py

Scans all Jekyll posts in _posts/en/ and _posts/es/, identifies those
that do NOT have a `translation` front-matter field, and writes a JSON
manifest of posts that still need translating.

Output: scripts/to_translate.json
"""

import json
import os
import re
import sys
import yaml
from pathlib import Path
from datetime import datetime

# ── Paths ────────────────────────────────────────────────────────────────
SITE_ROOT = Path(__file__).resolve().parent.parent          # iloveepoetry/
EN_DIR    = SITE_ROOT / "_posts" / "en"
ES_DIR    = SITE_ROOT / "_posts" / "es"
OUT_FILE  = SITE_ROOT / "scripts" / "to_translate.json"

# Regex that splits a Jekyll file into front matter (YAML) and body (HTML).
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n(.*)", re.DOTALL)


def parse_post(filepath: Path) -> dict | None:
    """Return parsed front matter dict + body, or None on failure."""
    text = filepath.read_text(encoding="utf-8")
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
    return fm


def extract_date_from_filename(filename: str) -> str:
    """Return ISO date string (YYYY-MM-DD) from a Jekyll filename."""
    parts = filename.split("-", 3)
    if len(parts) >= 3:
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return "9999-99-99"


def word_count(html: str) -> int:
    """Rough word count: strip HTML tags, then count whitespace-delimited tokens."""
    text = re.sub(r"<[^>]+>", " ", html)
    return len(text.split())


def collect_untranslated(directory: Path, lang: str) -> list[dict]:
    """Scan *directory* for posts missing a `translation` field."""
    results = []
    for filepath in sorted(directory.glob("*.html")):
        fm = parse_post(filepath)
        if fm is None:
            print(f"  SKIP (parse error): {filepath.name}", file=sys.stderr)
            continue

        # If the post already has a translation link, skip it.
        if fm.get("translation"):
            continue

        target_lang = "es" if lang == "en" else "en"
        body_html = fm.get("_body", "").strip()

        entry = {
            "source_file":    fm["_filepath"],
            "source_lang":    lang,
            "target_lang":    target_lang,
            "filename":       filepath.name,
            "title":          fm.get("title", ""),
            "permalink":      fm.get("permalink", ""),
            "author":         fm.get("author", ""),
            "categories":     fm.get("categories", []),
            "tags":           fm.get("tags", []),
            "excerpt":        fm.get("excerpt", ""),
            "featured_image": fm.get("featured_image", ""),
            "work_url":       fm.get("work_url", ""),
            "elmcip_url":     fm.get("elmcip_url", ""),
            "wp_post_id":     str(fm.get("wp_post_id", "")),
            "body_html":      body_html,
            "word_count":     word_count(body_html),
        }
        results.append(entry)

    return results


def main() -> None:
    print("Scanning English posts …")
    en_posts = collect_untranslated(EN_DIR, "en")
    print(f"  Found {len(en_posts)} untranslated English posts")

    print("Scanning Spanish posts …")
    es_posts = collect_untranslated(ES_DIR, "es")
    print(f"  Found {len(es_posts)} untranslated Spanish posts")

    # Combine: English first, then Spanish.  Within each group, sort by date
    # extracted from the filename (ascending).
    for group in (en_posts, es_posts):
        group.sort(key=lambda p: extract_date_from_filename(p["filename"]))

    all_posts = en_posts + es_posts

    # Write JSON output
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, indent=2, ensure_ascii=False)

    # ── Summary ──────────────────────────────────────────────────────────
    total_en = len(list(EN_DIR.glob("*.html")))
    total_es = len(list(ES_DIR.glob("*.html")))
    total_words_en = sum(p["word_count"] for p in en_posts)
    total_words_es = sum(p["word_count"] for p in es_posts)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"English posts total:        {total_en:>5}")
    print(f"  Already translated:       {total_en - len(en_posts):>5}")
    print(f"  Need translation (en→es): {len(en_posts):>5}  ({total_words_en:,} words)")
    print()
    print(f"Spanish posts total:        {total_es:>5}")
    print(f"  Already translated:       {total_es - len(es_posts):>5}")
    print(f"  Need translation (es→en): {len(es_posts):>5}  ({total_words_es:,} words)")
    print()
    print(f"Grand total to translate:   {len(all_posts):>5}  ({total_words_en + total_words_es:,} words)")
    print(f"Output written to: {OUT_FILE}")


if __name__ == "__main__":
    main()
