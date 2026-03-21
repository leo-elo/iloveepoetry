#!/usr/bin/env python3
"""
fix_translators.py — For every Spanish post that has a matching English post:
1. Set the author to the English post's author (original author)
2. Add a 'translator' field with the Spanish post's current author (the translator)
"""

import os
import re

POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"


def read_post(filepath):
    """Read a post file, return (front_matter_text, body_text, full_content)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return None, content, content
    idx = content.index("---", 3)
    fm = content[3:idx].strip()
    body = content[idx + 3:]
    return fm, body, content


def extract_field(fm_text, field):
    """Extract a field value from front matter text."""
    m = re.search(rf'^{re.escape(field)}:\s*(.+)$', fm_text, re.MULTILINE)
    if m:
        val = m.group(1).strip()
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        return val
    return None


def quote_yaml(value):
    """Quote a value for YAML if needed."""
    return f'"{value}"'


def main():
    # Step 1: Build EN permalink -> author mapping
    en_authors = {}
    for fname in sorted(os.listdir(POSTS_EN)):
        if not fname.endswith(".html"):
            continue
        fpath = os.path.join(POSTS_EN, fname)
        fm, _, _ = read_post(fpath)
        if not fm:
            continue
        permalink = extract_field(fm, "permalink")
        author = extract_field(fm, "author")
        if permalink and author:
            en_authors[permalink] = author

    print(f"English posts with authors: {len(en_authors)}")

    # Step 2: Process Spanish posts
    updated = 0
    same_author = 0
    no_match = 0
    already_has_translator = 0

    for fname in sorted(os.listdir(POSTS_ES)):
        if not fname.endswith(".html"):
            continue
        fpath = os.path.join(POSTS_ES, fname)
        fm, body, full = read_post(fpath)
        if not fm:
            continue

        translation = extract_field(fm, "translation")
        es_author = extract_field(fm, "author")

        # Skip if no matching English post
        if not translation or translation not in en_authors:
            no_match += 1
            continue

        en_author = en_authors[translation]

        # Skip if already has translator field
        if extract_field(fm, "translator"):
            already_has_translator += 1
            continue

        # If authors are the same, the original author also translated
        # In that case, don't add a translator field
        if en_author == es_author:
            same_author += 1
            continue

        # Replace author with EN author and add translator field
        # Find the author line
        old_author_line = re.search(r'^author:\s*.+$', fm, re.MULTILINE)
        if not old_author_line:
            continue

        old_line = old_author_line.group(0)
        new_author_line = f'author: {quote_yaml(en_author)}'
        new_translator_line = f'translator: {quote_yaml(es_author)}'

        new_fm = fm.replace(old_line, f'{new_author_line}\n{new_translator_line}')

        # Reconstruct file
        new_content = f"---\n{new_fm}\n---{body}"
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(new_content)
        updated += 1

    print(f"\nResults:")
    print(f"  Updated (author + translator added): {updated}")
    print(f"  Same author (no translator needed):  {same_author}")
    print(f"  No matching EN post:                 {no_match}")
    print(f"  Already had translator field:        {already_has_translator}")


if __name__ == "__main__":
    main()
