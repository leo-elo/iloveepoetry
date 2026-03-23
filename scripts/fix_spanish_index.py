#!/usr/bin/env python3
"""
Fix the Spanish index page so that links point to Spanish (/es/) translations
instead of English (/en/) posts.

Reads all Spanish posts in _posts/es/ to build a mapping from English
permalink (the `translation` field) to Spanish permalink, then rewrites
every /iloveepoetry/en/... href in the Spanish index to point to the
corresponding /iloveepoetry/es/... URL.
"""

import glob
import os
import re
import yaml

# Paths
BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"
SPANISH_INDEX = os.path.join(BASE_DIR, "_pages/es/indice-a-a-z-por-titulo.html")
SPANISH_POSTS_DIR = os.path.join(BASE_DIR, "_posts/es")


def extract_front_matter(filepath):
    """Extract YAML front matter from a Jekyll post file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Match YAML front matter between --- delimiters
    match = re.match(r"^---\s*\n(.*?\n)---\s*\n", content, re.DOTALL)
    if not match:
        return None

    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def build_translation_mapping():
    """
    Build a mapping: English permalink -> Spanish permalink.

    For each Spanish post that has a `translation` field (pointing to the
    English version) and a `permalink` field (its own Spanish URL), create
    a mapping entry.
    """
    mapping = {}
    posts = glob.glob(os.path.join(SPANISH_POSTS_DIR, "*.html"))

    for post_path in posts:
        fm = extract_front_matter(post_path)
        if fm is None:
            continue

        translation = fm.get("translation")
        permalink = fm.get("permalink")

        if not translation or not permalink:
            continue

        # Normalize: strip quotes, ensure leading/trailing slashes
        en_path = translation.strip().strip('"').strip("'")
        es_path = permalink.strip().strip('"').strip("'")

        # Ensure trailing slash for consistent matching
        if not en_path.endswith("/"):
            en_path += "/"
        if not es_path.endswith("/"):
            es_path += "/"

        mapping[en_path] = es_path

    return mapping


def fix_spanish_index(mapping):
    """
    Read the Spanish index file, replace English hrefs with Spanish ones,
    and write the result back. Print a summary.
    """
    with open(SPANISH_INDEX, "r", encoding="utf-8") as f:
        content = f.read()

    # Pattern to match href="/iloveepoetry/en/..."
    # We capture the path portion after /iloveepoetry
    href_pattern = re.compile(r'href="/iloveepoetry(/en/[^"]*)"')

    total_links = 0
    remapped = 0
    kept_english = 0

    def replace_href(match):
        nonlocal total_links, remapped, kept_english
        total_links += 1

        en_path = match.group(1)  # e.g., /en/2003/3-proposals-for.../

        # Normalize trailing slash for lookup
        lookup_path = en_path if en_path.endswith("/") else en_path + "/"

        if lookup_path in mapping:
            es_path = mapping[lookup_path]
            remapped += 1
            return f'href="/iloveepoetry{es_path}"'
        else:
            kept_english += 1
            return match.group(0)  # Keep original

    new_content = href_pattern.sub(replace_href, content)

    with open(SPANISH_INDEX, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("=" * 60)
    print("Spanish Index Link Fix - Summary")
    print("=" * 60)
    print(f"Total /en/ links found:              {total_links}")
    print(f"Links remapped to Spanish (/es/):    {remapped}")
    print(f"Links kept as English (no mapping):  {kept_english}")
    print("=" * 60)

    if kept_english > 0:
        print(f"\nNote: {kept_english} links remain pointing to English")
        print("because no Spanish translation was found for those posts.")


def main():
    print(f"Reading Spanish posts from: {SPANISH_POSTS_DIR}")
    mapping = build_translation_mapping()
    print(f"Built mapping with {len(mapping)} English->Spanish translation pairs.\n")

    print(f"Processing Spanish index: {SPANISH_INDEX}\n")
    fix_spanish_index(mapping)


if __name__ == "__main__":
    main()
