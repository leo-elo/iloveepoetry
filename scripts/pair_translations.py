#!/usr/bin/env python3
"""
Detect and pair English/Spanish translations of the same content.
Updates post front matter with 'translation' field pointing to the other language version.
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
from difflib import SequenceMatcher

import yaml

PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
POSTS_DIR = PROJECT_DIR / "_posts"
PAGES_DIR = PROJECT_DIR / "_pages"
PAIRS_FILE = SCRIPTS_DIR / "translation_pairs.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def parse_front_matter(filepath):
    """Parse YAML front matter from a Jekyll file."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content
    try:
        fm = yaml.safe_load(parts[1])
        return fm, content
    except yaml.YAMLError:
        return None, content


def normalize_title(title):
    """Normalize a title for comparison by removing common translation differences."""
    if not title:
        return ""
    t = title.lower().strip()
    # Remove quotes
    t = t.replace('"', '').replace("'", '').replace('\u201c', '').replace('\u201d', '')
    # Normalize common words (by/por, and/y, the/el/la/los/las)
    t = re.sub(r'\bby\b', '', t)
    t = re.sub(r'\bpor\b', '', t)
    t = re.sub(r'\bde\b', '', t)
    t = re.sub(r'\band\b', '', t)
    t = re.sub(r'\by\b', '', t)
    t = re.sub(r'\bthe\b', '', t)
    t = re.sub(r'\bel\b', '', t)
    t = re.sub(r'\bla\b', '', t)
    t = re.sub(r'\blos\b', '', t)
    t = re.sub(r'\blas\b', '', t)
    # Remove extra whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extract_work_title(title):
    """Extract the quoted work title from a post title like '"Work Name" by Author'."""
    match = re.search(r'["\u201c]([^"\u201d]+)["\u201d]', title or "")
    if match:
        return match.group(1).lower().strip()
    return None


def load_posts(lang_dir):
    """Load all posts from a language directory."""
    posts = []
    if not lang_dir.exists():
        return posts
    for filepath in sorted(lang_dir.glob("*.html")):
        fm, content = parse_front_matter(filepath)
        if fm:
            posts.append({
                "filepath": filepath,
                "title": fm.get("title", ""),
                "slug": filepath.stem.split("-", 3)[-1] if "-" in filepath.stem else filepath.stem,
                "permalink": fm.get("permalink", ""),
                "wp_post_id": fm.get("wp_post_id"),
                "categories": fm.get("categories", []),
                "date": str(fm.get("date", "")),
                "lang": fm.get("lang", ""),
            })
    return posts


def find_pairs(en_posts, es_posts):
    """Find translation pairs between English and Spanish posts."""
    pairs = []
    matched_en = set()
    matched_es = set()

    # Build lookup indexes
    en_by_work_title = {}
    es_by_work_title = {}
    en_by_norm_title = {}
    es_by_norm_title = {}
    en_by_slug = {}
    es_by_slug = {}

    for i, post in enumerate(en_posts):
        work_title = extract_work_title(post["title"])
        if work_title:
            en_by_work_title.setdefault(work_title, []).append(i)
        norm = normalize_title(post["title"])
        if norm:
            en_by_norm_title.setdefault(norm, []).append(i)
        slug = post["slug"]
        if slug:
            en_by_slug[slug] = i

    for i, post in enumerate(es_posts):
        work_title = extract_work_title(post["title"])
        if work_title:
            es_by_work_title.setdefault(work_title, []).append(i)
        norm = normalize_title(post["title"])
        if norm:
            es_by_norm_title.setdefault(norm, []).append(i)
        slug = post["slug"]
        if slug:
            es_by_slug[slug] = i

    # Strategy 1: Match by quoted work title (highest confidence)
    for work_title, en_indices in en_by_work_title.items():
        if work_title in es_by_work_title:
            es_indices = es_by_work_title[work_title]
            for en_idx in en_indices:
                if en_idx in matched_en:
                    continue
                for es_idx in es_indices:
                    if es_idx in matched_es:
                        continue
                    pairs.append((en_idx, es_idx, "work_title"))
                    matched_en.add(en_idx)
                    matched_es.add(es_idx)
                    break

    # Strategy 2: Match by normalized title
    for norm_title, en_indices in en_by_norm_title.items():
        if norm_title in es_by_norm_title:
            es_indices = es_by_norm_title[norm_title]
            for en_idx in en_indices:
                if en_idx in matched_en:
                    continue
                for es_idx in es_indices:
                    if es_idx in matched_es:
                        continue
                    pairs.append((en_idx, es_idx, "normalized_title"))
                    matched_en.add(en_idx)
                    matched_es.add(es_idx)
                    break

    # Strategy 3: Match by slug similarity
    for en_slug, en_idx in en_by_slug.items():
        if en_idx in matched_en:
            continue
        # Check for slug-2, slug-es, etc.
        candidates = [
            f"{en_slug}-2",
            f"{en_slug}-es",
        ]
        for candidate in candidates:
            if candidate in es_by_slug:
                es_idx = es_by_slug[candidate]
                if es_idx not in matched_es:
                    pairs.append((en_idx, es_idx, "slug_variant"))
                    matched_en.add(en_idx)
                    matched_es.add(es_idx)
                    break

    # Strategy 4: Fuzzy title matching for remaining unmatched
    unmatched_en = [i for i in range(len(en_posts)) if i not in matched_en]
    unmatched_es = [i for i in range(len(es_posts)) if i not in matched_es]

    for en_idx in unmatched_en:
        en_norm = normalize_title(en_posts[en_idx]["title"])
        if not en_norm or len(en_norm) < 5:
            continue
        best_score = 0
        best_es_idx = None
        for es_idx in unmatched_es:
            if es_idx in matched_es:
                continue
            es_norm = normalize_title(es_posts[es_idx]["title"])
            if not es_norm:
                continue
            score = SequenceMatcher(None, en_norm, es_norm).ratio()
            if score > best_score:
                best_score = score
                best_es_idx = es_idx
        if best_score >= 0.7 and best_es_idx is not None:
            pairs.append((en_idx, best_es_idx, f"fuzzy_{best_score:.2f}"))
            matched_en.add(en_idx)
            matched_es.add(best_es_idx)

    return pairs


def update_front_matter(filepath, translation_permalink):
    """Add translation field to a post's front matter."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False

    fm_text = parts[1]
    body = parts[2]

    # Add translation field if not already present
    if "translation:" not in fm_text:
        fm_text = fm_text.rstrip() + f"\ntranslation: \"{translation_permalink}\"\n"
        new_content = f"---{fm_text}---{body}"
        filepath.write_text(new_content, encoding="utf-8")
        return True
    return False


def main():
    logger.info("=== Translation Pairing Script ===")

    # Load posts
    en_posts = load_posts(POSTS_DIR / "en")
    es_posts = load_posts(POSTS_DIR / "es")

    # Load pages
    en_pages = load_posts(PAGES_DIR / "en")
    es_pages = load_posts(PAGES_DIR / "es")

    logger.info(f"English posts: {len(en_posts)}")
    logger.info(f"Spanish posts: {len(es_posts)}")
    logger.info(f"English pages: {len(en_pages)}")
    logger.info(f"Spanish pages: {len(es_pages)}")

    # Find post pairs
    post_pairs = find_pairs(en_posts, es_posts)
    logger.info(f"Post pairs found: {len(post_pairs)}")

    # Find page pairs
    page_pairs = find_pairs(en_pages, es_pages)
    logger.info(f"Page pairs found: {len(page_pairs)}")

    # Update front matter for posts
    updated = 0
    pair_data = []

    for en_idx, es_idx, method in post_pairs:
        en_post = en_posts[en_idx]
        es_post = es_posts[es_idx]

        en_permalink = en_post["permalink"]
        es_permalink = es_post["permalink"]

        if update_front_matter(en_post["filepath"], es_permalink):
            updated += 1
        if update_front_matter(es_post["filepath"], en_permalink):
            updated += 1

        pair_data.append({
            "en_title": en_post["title"],
            "es_title": es_post["title"],
            "en_permalink": en_permalink,
            "es_permalink": es_permalink,
            "method": method,
        })

    # Update front matter for pages
    for en_idx, es_idx, method in page_pairs:
        en_page = en_pages[en_idx]
        es_page = es_pages[es_idx]

        en_permalink = en_page["permalink"]
        es_permalink = es_page["permalink"]

        if update_front_matter(en_page["filepath"], es_permalink):
            updated += 1
        if update_front_matter(es_page["filepath"], en_permalink):
            updated += 1

        pair_data.append({
            "en_title": en_page["title"],
            "es_title": es_page["title"],
            "en_permalink": en_permalink,
            "es_permalink": es_permalink,
            "method": method,
            "type": "page",
        })

    # Save pairs data
    with open(PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump(pair_data, f, indent=2, ensure_ascii=False)

    # Stats by method
    methods = {}
    for _, _, method in post_pairs + page_pairs:
        methods[method] = methods.get(method, 0) + 1

    logger.info("=== Pairing Complete ===")
    logger.info(f"Total pairs: {len(post_pairs) + len(page_pairs)}")
    logger.info(f"Files updated: {updated}")
    logger.info(f"Unmatched EN posts: {len(en_posts) - len([p for p in post_pairs])}")
    logger.info(f"Unmatched ES posts: {len(es_posts) - len([p for p in post_pairs])}")
    logger.info(f"Pairs by method:")
    for method, count in sorted(methods.items()):
        logger.info(f"  {method}: {count}")
    logger.info(f"Pairs file: {PAIRS_FILE}")


if __name__ == "__main__":
    main()
