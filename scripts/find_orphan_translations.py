#!/usr/bin/env python3
"""
Find Spanish posts that have no `translation` field, or whose `translation`
field doesn't match any English post's permalink.

Approach:
  1. Read all English posts and build a set of their `permalink` values.
  2. Read all Spanish posts.
  3. For each Spanish post, check if it has a `translation` field and whether
     that value exists in the English permalink set.
  4. Print orphans sorted by filename (which starts with the date).
"""

import os
import re
import glob

EN_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/en"
ES_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/es"

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def extract_front_matter(filepath):
    """Return the raw YAML front-matter string (between the --- markers)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    m = FRONT_MATTER_RE.match(content)
    if m:
        return m.group(1)
    return ""


def get_yaml_value(fm_text, key):
    """
    Quick extraction of a top-level YAML scalar value.
    Handles both quoted and unquoted values.
    Returns None if the key is not found.
    """
    pattern = re.compile(
        rf'^{re.escape(key)}\s*:\s*["\']?(.*?)["\']?\s*$', re.MULTILINE
    )
    m = pattern.search(fm_text)
    if m:
        val = m.group(1).strip().strip("\"'")
        return val if val else None
    return None


def normalize_permalink(p):
    """Normalize permalink for comparison: strip whitespace, ensure trailing slash."""
    p = p.strip().strip("\"'")
    if not p.endswith("/"):
        p += "/"
    return p


# Step 1: Build set of English permalinks

en_permalinks = set()
en_files = glob.glob(os.path.join(EN_DIR, "*.html"))

for fp in en_files:
    fm = extract_front_matter(fp)
    permalink = get_yaml_value(fm, "permalink")
    if permalink:
        en_permalinks.add(normalize_permalink(permalink))

print(f"English posts found: {len(en_files)}")
print(f"English permalinks collected: {len(en_permalinks)}")
print()

# Step 2-3: Check each Spanish post

es_files = sorted(glob.glob(os.path.join(ES_DIR, "*.html")))

orphans = []  # (filename, title, author, reason)

for fp in es_files:
    fm = extract_front_matter(fp)
    translation = get_yaml_value(fm, "translation")
    title = get_yaml_value(fm, "title") or "(no title)"
    author = get_yaml_value(fm, "author") or "(no author)"
    filename = os.path.basename(fp)

    if not translation:
        orphans.append((filename, title, author, "NO translation field"))
    else:
        norm = normalize_permalink(translation)
        if norm not in en_permalinks:
            orphans.append(
                (filename, title, author, f"translation not found: {translation}")
            )

# Step 4: Print results sorted by filename (date)

orphans.sort(key=lambda x: x[0])

print(f"Spanish posts checked: {len(es_files)}")
print(f"Orphan Spanish posts (no match): {len(orphans)}")
print("=" * 100)

for i, (filename, title, author, reason) in enumerate(orphans, 1):
    print(f"\n{i:3d}. {filename}")
    print(f"     Title:  {title}")
    print(f"     Author: {author}")
    print(f"     Reason: {reason}")

print()
print(f"Total orphans: {len(orphans)}")
