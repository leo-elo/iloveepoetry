#!/usr/bin/env python3
"""
Fix missing bidirectional translation links.

For 10 Spanish files that have a `translation:` field pointing to their EN counterpart,
ensure the EN counterpart has a `translation:` field pointing back to the ES file.
"""

import os
import re
import glob

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts"
EN_DIR = os.path.join(BASE_DIR, "en")

# The 10 ES files and their EN permalink targets
PAIRS = [
    {
        "es_file": os.path.join(BASE_DIR, "es/2011-12-22-stir-fry-texts-por-jim-andrews.html"),
        "en_permalink": "/en/1999/stir-fry-texts-by-jim-andrews/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2011-12-23-cruising-por-ingrid-ankerson-and-megan-sapnar.html"),
        "en_permalink": "/en/2001/cruising-by-ingrid-ankerson-and-megan-sapnar/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2011-12-24-urbanalities-por-babel-vs-escha.html"),
        "en_permalink": "/en/2005/urbanalities-by-babel-vs-escha-this-short/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2011-12-25-the-set-of-u-por-philippe-bootz-y-marcel-fremiot.html"),
        "en_permalink": "/en/2004/the-set-of-u-by-philippe-bootz-and-marcel-fr-miot/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2011-12-26-jean-pierre-balpe-ou-les-lettres-derangees-por-patrick-henri-burgaud.html"),
        "en_permalink": "/en/2005/jean-pierre-balpe-ou-les-lettres-d-rang-es-by/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2012-01-08-faith-por-robert-kendall.html"),
        "en_permalink": "/en/2002/faith-by-robert-kendall/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2012-01-10-girls-day-out-por-kerry-lawrynovicz.html"),
        "en_permalink": "/en/2004/girls-day-out-by-kerry-lawrynovicz/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2012-01-11-landscapes-por-bill-marsh.html"),
        "en_permalink": "/en/2002/landscapes-by-bill-marsh/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2012-01-12-birds-singing-other-birds-songs-por-mar-a-mencia.html"),
        "en_permalink": "/en/2001/birds-singing-other-birds-songs-by-mar-a-mencia/",
    },
    {
        "es_file": os.path.join(BASE_DIR, "es/2012-01-13-lexia-to-perplexia-por-talan-memmott.html"),
        "en_permalink": "/en/2000/lexia-to-perplexia-by-talan-memmott/",
    },
]


def extract_permalink(content):
    """Extract the permalink value from front matter."""
    match = re.search(r'^permalink:\s*(.+)$', content, re.MULTILINE)
    if match:
        val = match.group(1).strip().strip('"').strip("'")
        return val
    return None


def has_translation_field(content):
    """Check if front matter already has a translation: field."""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False
    front_matter = parts[1]
    return bool(re.search(r'^translation:', front_matter, re.MULTILINE))


def find_en_file_by_permalink(en_permalink):
    """Find the EN file that has the given permalink."""
    en_files = glob.glob(os.path.join(EN_DIR, "*.html"))
    for filepath in en_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        plink = extract_permalink(content)
        if plink and plink.rstrip("/") == en_permalink.rstrip("/"):
            return filepath, content
    return None, None


def add_translation_to_en_file(en_filepath, en_content, es_permalink):
    """Add translation: field after the permalink: line in the EN file."""
    lines = en_content.split("\n")
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and line.strip().startswith("permalink:"):
            new_lines.append('translation: "' + es_permalink + '"')
            inserted = True

    if not inserted:
        print(f"  WARNING: Could not find permalink: line in {en_filepath}")
        return False

    new_content = "\n".join(new_lines)
    with open(en_filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def main():
    print("=" * 70)
    print("Fixing bidirectional translation links for 10 ES/EN pairs")
    print("=" * 70)

    fixed = 0
    skipped = 0
    errors = 0

    for i, pair in enumerate(PAIRS, 1):
        es_file = pair["es_file"]
        en_permalink = pair["en_permalink"]

        print(f"\n--- Pair {i}/10 ---")
        print(f"  ES file: {os.path.basename(es_file)}")

        # Step 1: Read ES file and get its permalink
        if not os.path.exists(es_file):
            print(f"  ERROR: ES file not found!")
            errors += 1
            continue

        with open(es_file, "r", encoding="utf-8") as f:
            es_content = f.read()

        es_permalink = extract_permalink(es_content)
        if not es_permalink:
            print(f"  ERROR: No permalink found in ES file!")
            errors += 1
            continue
        print(f"  ES permalink: {es_permalink}")

        # Step 2: Find the EN file by matching permalink
        print(f"  Looking for EN file with permalink: {en_permalink}")
        en_filepath, en_content = find_en_file_by_permalink(en_permalink)

        if not en_filepath:
            print(f"  ERROR: No EN file found with permalink {en_permalink}")
            errors += 1
            continue
        print(f"  EN file found: {os.path.basename(en_filepath)}")

        # Step 3: Check if EN file already has translation field
        if has_translation_field(en_content):
            existing_trans = re.search(r'^translation:\s*(.+)$', en_content, re.MULTILINE)
            existing_val = existing_trans.group(1).strip() if existing_trans else "?"
            print(f"  SKIPPED: EN file already has translation: {existing_val}")
            skipped += 1
            continue

        # Step 4: Add translation field to EN file
        success = add_translation_to_en_file(en_filepath, en_content, es_permalink)
        if success:
            print(f'  FIXED: Added translation: "{es_permalink}" to EN file')
            fixed += 1
        else:
            errors += 1

    print("\n" + "=" * 70)
    print(f"SUMMARY: {fixed} fixed, {skipped} already had links, {errors} errors")
    print("=" * 70)


if __name__ == "__main__":
    main()
