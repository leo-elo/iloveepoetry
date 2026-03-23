#!/usr/bin/env python3
"""
link_deep_matches.py

Links 21 matched English/Spanish translation pairs bidirectionally by adding
`translation:` fields pointing to each other's permalinks.

Skips match #14 (questionable CFP match) from the original 22-pair list.
"""

import re
import os

EN_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/en/"
ES_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"

# 21 pairs to link (match #14 from original list already excluded)
PAIRS = [
    # HIGH CONFIDENCE (17 pairs)
    ("2014-02-14-love-e-poems.html", "2018-05-17-i-love-love-e-poetry.html"),
    ("2013-05-21-i-♥-e-poetry-and-elmcip-knowledge-base-partnership.html", "2018-04-30-i-♥-e-poetry-y-elmcip-knowledge-base-partnership.html"),
    ("2013-06-19-i-♥-e-poetry-500-entries-later.html", "2018-05-02-i-e-poetry-500-entries-later-9-2.html"),
    ("2018-03-12-uncontrollable-semantics-por-jason-nelson.html", "2018-05-22-uncontrollable-semantics-por-jason-nelson-2-2.html"),
    ("2013-05-30-literaturtidsskriftet-lasso-interview.html", "2018-04-26-literatura-tidsskriftet-lasso-entrevista.html"),
    ("2014-07-18-new-contributor-kyle-brett.html", "2018-05-19-nuevo-contribuidor-kyle-brett.html"),
    ("2015-02-17-new-contributor-calum-rodger.html", "2018-03-16-nuevo-colaborador-calum-rodger.html"),
    ("2013-09-09-new-contributor-barbara-bordalejo.html", "2018-05-07-nueva-colaboradora-barbara-bordalejo.html"),
    ("2015-04-08-new-contributor-nohelia-meza.html", "2018-03-16-nueva-colaboradora-nohelia-meza.html"),
    ("2013-09-05-new-contributor-samira-nadkarni.html", "2018-05-07-nueva-colaboradora-samira-nadkarni.html"),
    ("2013-09-04-new-contributor-luis-claudio-costa-fajardo.html", "2018-05-07-nuevo-colaborador-luis-claudio-costa-fajardo.html"),
    ("2014-02-12-new-contributor-jonathan-baillehache.html", "2018-05-14-nuevo-colaborador-jonathan-baillehache.html"),
    ("2014-03-18-new-contributor-lauren-perez-mangonez.html", "2018-05-17-nueva-colaboradora-lauren-perez-mangonez.html"),
    ("2013-12-22-i-♥-e-poetry-year-two-retrospective.html", "2018-05-15-i-♥-e-poetry-ano-dos-retrospectiva.html"),
    ("2013-09-02-i-♥-e-poetry-phase-2-the-next-500-entries.html", "2018-05-07-i-♥-e-poetry-phase-2-las-siguientes-500-entradas.html"),
    ("2014-03-19-new-series-e-lit-for-esl.html", "2018-05-17-nueva-serie-e-lit-para-esl.html"),
    ("2014-11-07-i-♥-e-poetry-asa-conference.html", "2018-05-19-i-♥-e-poetry-conferencia-de-asa.html"),
    # MEDIUM CONFIDENCE (4 pairs)
    ("2012-04-10-by-duc-thuan.html", "2018-02-28-echo-the_signifier-por-duc-thuan.html"),
    ("2012-07-23-reading-the-agrippa-code.html", "2018-03-14-leyendo-el-codigo-de-agrippa-parte-4-de-4.html"),
    ("2012-07-16-a-close-reading-of-william-gibsons-agrippa-part-3.html", "2018-03-14-una-lectura-detallada-de-agripa-de-william-gibson-parte-3-de-4.html"),
    ("2014-01-31-i-♥-e-poetry-nominated-for-2013-dh-awards.html", "2018-05-15-i-♥-e-poetry-nominada-para-los-premios-dh-2013.html"),
]


def extract_permalink(content):
    """Extract the permalink value from YAML front matter."""
    match = re.search(r'^permalink:\s*(.+)$', content, re.MULTILINE)
    if match:
        value = match.group(1).strip().strip('"').strip("'")
        return value
    return None


def has_translation_field(content):
    """Check if the file already has a translation: field in front matter."""
    # Only look within front matter (between --- delimiters)
    fm_match = re.match(r'^---\n(.*?\n)---', content, re.DOTALL)
    if fm_match:
        front_matter = fm_match.group(1)
        return re.search(r'^translation:', front_matter, re.MULTILINE) is not None
    return False


def get_existing_translation(content):
    """Get the existing translation value if present."""
    fm_match = re.match(r'^---\n(.*?\n)---', content, re.DOTALL)
    if fm_match:
        front_matter = fm_match.group(1)
        match = re.search(r'^translation:\s*(.+)$', front_matter, re.MULTILINE)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return None


def add_translation_field(content, target_permalink):
    """Add translation: field after the permalink: line in front matter."""
    # Insert translation: line right after permalink: line
    new_line = f'translation: "{target_permalink}"'
    content = re.sub(
        r'^(permalink:\s*.+)$',
        r'\1\n' + new_line,
        content,
        count=1,
        flags=re.MULTILINE
    )
    return content


def main():
    added = 0
    skipped = 0
    conflicts = 0
    errors = 0

    print("=" * 70)
    print("LINKING 21 TRANSLATION PAIRS BIDIRECTIONALLY")
    print("=" * 70)
    print()

    for i, (en_file, es_file) in enumerate(PAIRS, 1):
        en_path = os.path.join(EN_DIR, en_file)
        es_path = os.path.join(ES_DIR, es_file)

        print(f"--- Pair {i}: ---")
        print(f"  EN: {en_file}")
        print(f"  ES: {es_file}")

        # Check files exist
        if not os.path.exists(en_path):
            print(f"  ERROR: EN file not found: {en_path}")
            errors += 1
            print()
            continue
        if not os.path.exists(es_path):
            print(f"  ERROR: ES file not found: {es_path}")
            errors += 1
            print()
            continue

        # Read files
        with open(en_path, 'r', encoding='utf-8') as f:
            en_content = f.read()
        with open(es_path, 'r', encoding='utf-8') as f:
            es_content = f.read()

        # Extract permalinks
        en_permalink = extract_permalink(en_content)
        es_permalink = extract_permalink(es_content)

        if not en_permalink:
            print(f"  ERROR: No permalink found in EN file")
            errors += 1
            print()
            continue
        if not es_permalink:
            print(f"  ERROR: No permalink found in ES file")
            errors += 1
            print()
            continue

        print(f"  EN permalink: {en_permalink}")
        print(f"  ES permalink: {es_permalink}")

        # Process EN file: add translation pointing to ES permalink
        en_modified = False
        if has_translation_field(en_content):
            existing = get_existing_translation(en_content)
            if existing == es_permalink:
                print(f"  EN: Already linked correctly -> {existing}")
                skipped += 1
            else:
                print(f"  EN: CONFLICT - already has translation: {existing}")
                print(f"       (expected: {es_permalink})")
                conflicts += 1
        else:
            en_content = add_translation_field(en_content, es_permalink)
            en_modified = True
            print(f"  EN: Added translation -> {es_permalink}")
            added += 1

        # Process ES file: add translation pointing to EN permalink
        es_modified = False
        if has_translation_field(es_content):
            existing = get_existing_translation(es_content)
            if existing == en_permalink:
                print(f"  ES: Already linked correctly -> {existing}")
                skipped += 1
            else:
                print(f"  ES: CONFLICT - already has translation: {existing}")
                print(f"       (expected: {en_permalink})")
                conflicts += 1
        else:
            es_content = add_translation_field(es_content, en_permalink)
            es_modified = True
            print(f"  ES: Added translation -> {en_permalink}")
            added += 1

        # Write modified files
        if en_modified:
            with open(en_path, 'w', encoding='utf-8') as f:
                f.write(en_content)
        if es_modified:
            with open(es_path, 'w', encoding='utf-8') as f:
                f.write(es_content)

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Pairs processed:      {len(PAIRS)}")
    print(f"  Translation links added: {added}")
    print(f"  Already linked (skip):   {skipped}")
    print(f"  Conflicts (not touched): {conflicts}")
    print(f"  Errors:                  {errors}")
    print(f"  Files modified:          {added} (across {len(PAIRS)} pairs)")
    print()


if __name__ == "__main__":
    main()
