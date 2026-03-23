#!/usr/bin/env python3
"""
match_orphans.py — Find orphan Spanish posts and try to match them with English counterparts.

Reads all English and Spanish posts, identifies orphan Spanish posts (no translation field
or translation pointing to non-existent English permalink), and attempts to match them
using slug, title, tag/category, and wp_post_id heuristics.
"""

import os
import re
import unicodedata
import yaml
from collections import defaultdict
from pathlib import Path

EN_DIR = Path("/Users/floresll/Desktop/iloveepoetry/_posts/en")
ES_DIR = Path("/Users/floresll/Desktop/iloveepoetry/_posts/es")


def extract_front_matter(filepath):
    """Extract YAML front matter from a Jekyll post."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    return data


def parse_post(filepath):
    """Parse a post file and return a dict with extracted metadata."""
    data = extract_front_matter(filepath)
    if data is None:
        return None

    # Ensure categories and tags are lists of strings
    raw_cats = data.get("categories", []) or []
    raw_tags = data.get("tags", []) or []
    categories = [str(c) for c in raw_cats]
    tags = [str(t) for t in raw_tags]

    return {
        "filename": os.path.basename(filepath),
        "filepath": str(filepath),
        "title": str(data.get("title", "")),
        "permalink": str(data.get("permalink", "")),
        "translation": str(data.get("translation", "") or ""),
        "author": str(data.get("author", "")),
        "date": str(data.get("date", "")),
        "categories": categories,
        "tags": tags,
        "wp_post_id": data.get("wp_post_id"),
        "lang": str(data.get("lang", "")),
    }


def strip_accents(s):
    """Remove accents/diacritics from a string."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.category(c).startswith("M"))


def extract_slug(permalink):
    """
    Extract the slug portion from a permalink (the last path component).
    E.g. /es/2000-es/tierra-de-extraccion-by-domenico-chiappe/ -> tierra-de-extraccion-by-domenico-chiappe
         /en/2001/nio-by-jim-andrews/ -> nio-by-jim-andrews
    """
    parts = permalink.strip("/").split("/")
    if len(parts) < 2:
        return permalink.strip("/")
    return parts[-1]


def normalize_slug(slug):
    """
    Normalize a slug for comparison by removing language suffixes and trailing numbers.
    """
    s = slug.lower().strip()
    # Remove trailing -2, -3, etc. (WordPress duplicate suffixes)
    s = re.sub(r"-(\d+)$", "", s)
    # Remove trailing -es suffix
    s = re.sub(r"-es$", "", s)
    # Replace -por- with -by- for author name matching
    s = s.replace("-por-", "-by-")
    # Strip accents
    s = strip_accents(s)
    return s


def normalize_title(title):
    """
    Normalize a title for comparison.
    """
    t = title.lower().strip()
    # Remove various quote characters
    t = re.sub(r'["""\u201c\u201d\u2018\u2019\u00ab\u00bb\'`]', "", t)
    # Remove "by <author>", "por <author>", "de <author>" at the end
    t = re.sub(r"\s+(by|por|de)\s+.*$", "", t)
    # Strip accents
    t = strip_accents(t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_posts(directory):
    """Load all posts from a directory."""
    posts = []
    for filepath in sorted(directory.glob("*.html")):
        post = parse_post(filepath)
        if post:
            posts.append(post)
    return posts


def main():
    print("=" * 100)
    print("ORPHAN POST MATCHER - I Love E-Poetry")
    print("=" * 100)
    print()

    # Load all posts
    print("Loading posts...")
    en_posts = load_posts(EN_DIR)
    es_posts = load_posts(ES_DIR)
    print(f"  English posts: {len(en_posts)}")
    print(f"  Spanish posts: {len(es_posts)}")
    print()

    # Build lookup maps for English posts
    en_by_permalink = {}
    en_by_normalized_slug = defaultdict(list)
    en_by_normalized_title = defaultdict(list)
    en_by_tags = defaultdict(list)
    en_by_wp_post_id = {}

    for post in en_posts:
        permalink = post["permalink"]
        en_by_permalink[permalink] = post

        slug = extract_slug(permalink)
        norm_slug = normalize_slug(slug)
        en_by_normalized_slug[norm_slug].append(post)

        norm_title = normalize_title(post["title"])
        if norm_title:
            en_by_normalized_title[norm_title].append(post)

        for tag in post["tags"]:
            en_by_tags[tag.lower()].append(post)

        if post["wp_post_id"] is not None:
            en_by_wp_post_id[post["wp_post_id"]] = post

    en_permalink_set = set(en_by_permalink.keys())

    # Build reverse map: what English post points TO a given Spanish permalink
    en_pointing_to_es = defaultdict(list)
    for post in en_posts:
        if post["translation"]:
            en_pointing_to_es[post["translation"]].append(post)

    # Identify orphan Spanish posts
    linked_es = []
    orphan_es = []
    broken_link_es = []

    for post in es_posts:
        translation = post["translation"]
        if not translation:
            orphan_es.append(post)
        elif translation in en_permalink_set:
            linked_es.append(post)
        elif translation.startswith("/es/"):
            # Points to another Spanish post, not English — treat as orphan
            orphan_es.append(post)
        else:
            broken_link_es.append(post)
            orphan_es.append(post)

    print(f"Spanish posts with valid EN translation link: {len(linked_es)}")
    print(f"Spanish posts with broken/missing translation link: {len(orphan_es)}")
    if broken_link_es:
        print(f"  (of which {len(broken_link_es)} have a translation field pointing to non-existent EN permalink)")
    print()

    # Try to match orphan Spanish posts
    confident_matches = []
    possible_matches = []
    no_match = []

    for es_post in orphan_es:
        es_slug = extract_slug(es_post["permalink"])
        es_norm_slug = normalize_slug(es_slug)
        es_norm_title = normalize_title(es_post["title"])
        es_tags = set(t.lower() for t in es_post["tags"])
        es_cats = set(c.lower() for c in es_post["categories"])
        es_wp_id = es_post["wp_post_id"]

        match_found = False
        match_reasons = []
        matched_en_posts = []

        # Heuristic A: Slug matching
        if es_norm_slug in en_by_normalized_slug:
            candidates = en_by_normalized_slug[es_norm_slug]
            for en_post in candidates:
                matched_en_posts.append(en_post)
                match_reasons.append(f"SLUG: '{es_norm_slug}' matches")
            match_found = True

        # Heuristic B: Title matching (only if slug didn't match)
        if not match_found and es_norm_title:
            if es_norm_title in en_by_normalized_title:
                candidates = en_by_normalized_title[es_norm_title]
                for en_post in candidates:
                    if en_post not in matched_en_posts:
                        matched_en_posts.append(en_post)
                        match_reasons.append(f"TITLE: '{es_norm_title}' matches")
                match_found = True

        if match_found:
            for en_post in matched_en_posts:
                conflict = None
                if en_post["translation"]:
                    if en_post["translation"] != es_post["permalink"]:
                        conflict = en_post["translation"]
                confident_matches.append((es_post, en_post, match_reasons, conflict))
            continue

        # Heuristic C: Tag matching (author names) + category overlap
        tag_matches = []
        if es_tags:
            for tag in es_tags:
                if tag in en_by_tags:
                    for en_post in en_by_tags[tag]:
                        en_cats = set(c.lower() for c in en_post["categories"])
                        cat_overlap = es_cats & en_cats
                        if cat_overlap:
                            tag_matches.append((en_post, f"TAG+CAT: author='{tag}', shared categories={cat_overlap}"))

        # Heuristic D: wp_post_id proximity
        wpid_matches = []
        if es_wp_id is not None:
            for delta in range(-5, 6):
                if delta == 0:
                    continue
                candidate_id = es_wp_id + delta
                if candidate_id in en_by_wp_post_id:
                    en_post = en_by_wp_post_id[candidate_id]
                    wpid_matches.append((en_post, f"WP_POST_ID: es={es_wp_id}, en={candidate_id} (delta={delta})"))

        if tag_matches or wpid_matches:
            seen = set()
            for en_post, reason in tag_matches + wpid_matches:
                key = en_post["permalink"]
                if key not in seen:
                    seen.add(key)
                    conflict = None
                    if en_post["translation"] and en_post["translation"] != es_post["permalink"]:
                        conflict = en_post["translation"]
                    possible_matches.append((es_post, en_post, [reason], conflict))
        else:
            no_match.append(es_post)

    # ===== PRINT RESULTS =====

    print("=" * 100)
    print(f"CONFIDENT MATCHES (slug or title): {len(confident_matches)}")
    print("=" * 100)
    for i, (es_post, en_post, reasons, conflict) in enumerate(confident_matches, 1):
        print(f"\n  [{i}] MATCH:")
        print(f"      ES file:      {es_post['filename']}")
        print(f"      ES title:     {es_post['title']}")
        print(f"      ES permalink: {es_post['permalink']}")
        print(f"      EN file:      {en_post['filename']}")
        print(f"      EN title:     {en_post['title']}")
        print(f"      EN permalink: {en_post['permalink']}")
        print(f"      Reason:       {'; '.join(reasons)}")
        if es_post["translation"]:
            print(f"      ES translation field: {es_post['translation']} (BROKEN - target does not exist)")
        if conflict:
            print(f"      *** CONFLICT: EN post already has translation -> {conflict}")

    print()
    print("=" * 100)
    print(f"POSSIBLE MATCHES (tag/category or wp_post_id proximity): {len(possible_matches)}")
    print("=" * 100)
    for i, (es_post, en_post, reasons, conflict) in enumerate(possible_matches, 1):
        print(f"\n  [{i}] POSSIBLE:")
        print(f"      ES file:      {es_post['filename']}")
        print(f"      ES title:     {es_post['title']}")
        print(f"      ES permalink: {es_post['permalink']}")
        print(f"      EN file:      {en_post['filename']}")
        print(f"      EN title:     {en_post['title']}")
        print(f"      EN permalink: {en_post['permalink']}")
        print(f"      Reason:       {'; '.join(reasons)}")
        if es_post["translation"]:
            print(f"      ES translation field: {es_post['translation']} (BROKEN - target does not exist)")
        if conflict:
            print(f"      *** CONFLICT: EN post already has translation -> {conflict}")

    print()
    print("=" * 100)
    print(f"NO MATCH FOUND (Spanish-only content): {len(no_match)}")
    print("=" * 100)
    for i, es_post in enumerate(no_match, 1):
        print(f"\n  [{i}] ORPHAN:")
        print(f"      ES file:      {es_post['filename']}")
        print(f"      ES title:     {es_post['title']}")
        print(f"      ES permalink: {es_post['permalink']}")
        if es_post["tags"]:
            print(f"      ES tags:      {', '.join(es_post['tags'])}")
        if es_post["wp_post_id"]:
            print(f"      ES wp_post_id: {es_post['wp_post_id']}")

    # ===== ORPHAN ENGLISH POSTS =====
    es_permalink_set = set(p["permalink"] for p in es_posts)
    es_translation_targets = set()
    for p in es_posts:
        if p["translation"]:
            es_translation_targets.add(p["translation"])

    confident_en_permalinks = set()
    for es_post, en_post, reasons, conflict in confident_matches:
        confident_en_permalinks.add(en_post["permalink"])

    orphan_en = []
    for en_post in en_posts:
        has_counterpart = False

        # Check 1: EN post's translation field points to existing ES permalink
        if en_post["translation"] and en_post["translation"] in es_permalink_set:
            has_counterpart = True

        # Check 2: Some ES post's translation field points to this EN post
        if en_post["permalink"] in es_translation_targets:
            has_counterpart = True

        # Check 3: Found in our confident matches
        if en_post["permalink"] in confident_en_permalinks:
            has_counterpart = True

        if not has_counterpart:
            orphan_en.append(en_post)

    print()
    print("=" * 100)
    print(f"ORPHAN ENGLISH POSTS (no Spanish counterpart): {len(orphan_en)}")
    print("=" * 100)
    for i, en_post in enumerate(orphan_en, 1):
        extra = ""
        if en_post["translation"]:
            if en_post["translation"] not in es_permalink_set:
                extra = f"  [translation field '{en_post['translation']}' -> TARGET NOT FOUND]"
            else:
                extra = f"  [translation -> {en_post['translation']}]"
        print(f"  [{i:3d}] {en_post['filename']:70s} {en_post['permalink']}{extra}")

    # ===== SUMMARY =====
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  Total English posts:                      {len(en_posts)}")
    print(f"  Total Spanish posts:                      {len(es_posts)}")
    print()
    print(f"  Spanish with valid EN link:                {len(linked_es)}")
    print(f"  Spanish with broken EN link:               {len(broken_link_es)}")
    print(f"  Spanish orphans (no/bad link):             {len(orphan_es)}")
    print()
    print(f"  Confident matches found:                   {len(confident_matches)}")
    print(f"  Possible matches found:                    {len(possible_matches)}")
    print(f"  No match found (Spanish-only):             {len(no_match)}")
    print()
    conflicts = sum(1 for _, _, _, c in confident_matches + possible_matches if c)
    print(f"  Matches with EN translation conflicts:     {conflicts}")
    print()
    print(f"  Orphan English posts (no ES counterpart):  {len(orphan_en)}")
    print()

    # Sanity check
    possible_es_set = set(p[0]["permalink"] for p in possible_matches)
    confident_es_set = set(p[0]["permalink"] for p in confident_matches)
    uniq_confident = len(confident_es_set)
    uniq_possible = len(possible_es_set - confident_es_set)
    print(f"  Sanity check:")
    print(f"    linked({len(linked_es)}) + orphan({len(orphan_es)}) = {len(linked_es) + len(orphan_es)} (should be {len(es_posts)})")
    print(f"    unique_confident_es({uniq_confident}) + unique_possible_es({uniq_possible}) + no_match({len(no_match)}) = {uniq_confident + uniq_possible + len(no_match)} (should be {len(orphan_es)})")


if __name__ == "__main__":
    main()
