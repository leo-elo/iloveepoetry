#!/usr/bin/env python3
"""
link_orphans.py

Part 1: Link orphan Spanish posts to their English counterparts for known
        confident, non-conflicting matches.

Part 2: Ensure ALL translation links across the site are bidirectional.
        If post A links to post B but B does not link back to A, fix it.
"""

import os
import re
import glob

POSTS_EN = "/Users/floresll/Desktop/iloveepoetry/_posts/en"
POSTS_ES = "/Users/floresll/Desktop/iloveepoetry/_posts/es"

# ── helpers ──────────────────────────────────────────────────────────────

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def extract_front_matter(content):
    """Return (front_matter_str, rest_of_file) or (None, content)."""
    m = re.match(r'^(---\n.*?\n---)', content, re.DOTALL)
    if m:
        return m.group(1), content[m.end():]
    return None, content

def get_field(front_matter, field):
    """Extract the value of a YAML field from front matter text."""
    pattern = re.compile(r'^' + re.escape(field) + r':\s*(.+)$', re.MULTILINE)
    m = pattern.search(front_matter)
    if m:
        val = m.group(1).strip().strip('"').strip("'")
        return val
    return None

def has_field(front_matter, field):
    pattern = re.compile(r'^' + re.escape(field) + r':', re.MULTILINE)
    return bool(pattern.search(front_matter))

def add_translation_field(front_matter, translation_value):
    """Add translation: "<value>" to front matter after permalink or lang line."""
    line = 'translation: "' + translation_value + '"'
    # Try to insert after permalink line
    if re.search(r'^permalink:', front_matter, re.MULTILINE):
        new_fm = re.sub(
            r'^(permalink:\s*.+)$',
            r'\1\n' + line,
            front_matter,
            count=1,
            flags=re.MULTILINE
        )
        return new_fm
    # Try to insert after lang line
    if re.search(r'^lang:', front_matter, re.MULTILINE):
        new_fm = re.sub(
            r'^(lang:\s*.+)$',
            r'\1\n' + line,
            front_matter,
            count=1,
            flags=re.MULTILINE
        )
        return new_fm
    # Fallback: insert before closing ---
    new_fm = front_matter.rstrip()
    if new_fm.endswith('---'):
        new_fm = new_fm[:-3] + line + '\n---'
    return new_fm

# ── build permalink → file path index ────────────────────────────────────

def build_permalink_index():
    """Map permalink → absolute file path for all EN and ES posts."""
    index = {}
    for directory in [POSTS_EN, POSTS_ES]:
        for filepath in glob.glob(os.path.join(directory, "*.html")):
            content = read_file(filepath)
            fm, _ = extract_front_matter(content)
            if fm:
                permalink = get_field(fm, 'permalink')
                if permalink:
                    index[permalink] = filepath
    return index

def build_file_index():
    """Map filename → absolute file path for all EN and ES posts."""
    index = {}
    for directory in [POSTS_EN, POSTS_ES]:
        for filepath in glob.glob(os.path.join(directory, "*.html")):
            index[os.path.basename(filepath)] = filepath
    return index


# ═══════════════════════════════════════════════════════════════════════════
# PART 1: Link orphan Spanish posts to English counterparts
# ═══════════════════════════════════════════════════════════════════════════

CONFIDENT_MATCHES = [
    # (ES filename, EN filename)
    ("2017-01-01-i-\u2665\ufe0e-e-poetry-phase-3-begins-2.html",
     "2017-01-01-i-\u2665\ufe0e-e-poetry-phase-3-begins.html"),

    ("2017-03-07-presentation-i-\u2665\ufe0e-e-poetry-discovering-digital-media-poetry-2.html",
     "2016-07-11-presentation-i-\u2665\ufe0e-e-poetry-discovering-digital-media-poetry.html"),

    ("2018-02-25-4-square-por-jody-zellen.html",
     "2012-11-27-4-square-by-jody-zellen.html"),

    ("2018-04-30-cfp-the-e-lit-i-love-2.html",
     "2013-05-16-cfp-the-e-lit-i-love.html"),

    ("2018-05-02-iloveepoetry-a-break-bot-por-leonardo-flores.html",
     "2013-05-03-iloveepoetry-a-break-bot-by-leonardo-flores.html"),

    ("2018-05-08-e-poetry-as-code-and-data-remix-por-leonardo-flores.html",
     "2013-11-02-e-poetry-as-code-and-data-remix-by-leonardo-flores.html"),

    ("2018-05-08-teaching-with-i-\u2665-e-poetry-por-leonardo-flores.html",
     "2013-11-03-teaching-with-i-\u2665-e-poetry-by-leonardo-flores.html"),

    ("2018-05-08-visualizing-i-\u2665-e-poetry-por-leonardo-flores.html",
     "2013-11-03-visualizing-i-\u2665-e-poetry-by-leonardo-flores.html"),

    ("2018-05-22-i-\u2665-e-poetry-caguas-mini-maker-faire-2.html",
     "2015-01-30-i-\u2665-e-poetry-caguas-mini-maker-faire.html"),
]

AMBIGUOUS_MATCHES = [
    ("2018-05-02-i-e-poetry-500-entries-later-9-2.html", "matched two EN posts"),
    ("2018-05-22-uncontrollable-semantics-por-jason-nelson-2-2.html", "matched two EN posts"),
]


def part1(file_index, permalink_index):
    print("=" * 72)
    print("PART 1: Link orphan Spanish posts to English counterparts")
    print("=" * 72)

    changes_made = []
    errors = []

    for es_file, en_file in CONFIDENT_MATCHES:
        es_path = os.path.join(POSTS_ES, es_file)
        en_path = os.path.join(POSTS_EN, en_file)

        if not os.path.exists(es_path):
            errors.append(f"  ERROR: ES file not found: {es_file}")
            continue
        if not os.path.exists(en_path):
            errors.append(f"  ERROR: EN file not found: {en_file}")
            continue

        es_content = read_file(es_path)
        en_content = read_file(en_path)

        es_fm, es_body = extract_front_matter(es_content)
        en_fm, en_body = extract_front_matter(en_content)

        if not es_fm or not en_fm:
            errors.append(f"  ERROR: Could not parse front matter for {es_file} or {en_file}")
            continue

        es_permalink = get_field(es_fm, 'permalink')
        en_permalink = get_field(en_fm, 'permalink')

        if not es_permalink or not en_permalink:
            errors.append(f"  ERROR: Missing permalink in {es_file} or {en_file}")
            continue

        # Check if EN already has a translation field pointing elsewhere
        en_existing_trans = get_field(en_fm, 'translation')
        if en_existing_trans and en_existing_trans != es_permalink:
            errors.append(
                f"  CONFLICT: EN {en_file} already has translation: {en_existing_trans} "
                f"(not {es_permalink}). Skipping this pair."
            )
            continue

        print(f"\nPair: {es_file}")
        print(f"  <-> {en_file}")
        print(f"  ES permalink: {es_permalink}")
        print(f"  EN permalink: {en_permalink}")

        # Add translation to ES post (pointing to EN)
        es_changed = False
        es_existing_trans = get_field(es_fm, 'translation')
        if es_existing_trans:
            if es_existing_trans == en_permalink:
                print(f"  ES already has correct translation: {en_permalink}")
            else:
                print(f"  ES has DIFFERENT translation: {es_existing_trans} (expected {en_permalink}). Skipping ES update.")
        else:
            es_fm_new = add_translation_field(es_fm, en_permalink)
            es_content_new = es_fm_new + es_body
            write_file(es_path, es_content_new)
            es_changed = True
            changes_made.append(f"  Added translation: \"{en_permalink}\" to ES {es_file}")
            print(f"  ADDED to ES: translation: \"{en_permalink}\"")

        # Add translation to EN post (pointing to ES)
        en_changed = False
        if en_existing_trans:
            if en_existing_trans == es_permalink:
                print(f"  EN already has correct translation: {es_permalink}")
            else:
                print(f"  EN has DIFFERENT translation: {en_existing_trans} (expected {es_permalink}). Skipping EN update.")
        else:
            en_fm_new = add_translation_field(en_fm, es_permalink)
            en_content_new = en_fm_new + en_body
            write_file(en_path, en_content_new)
            en_changed = True
            changes_made.append(f"  Added translation: \"{es_permalink}\" to EN {en_file}")
            print(f"  ADDED to EN: translation: \"{es_permalink}\"")

        if not es_changed and not en_changed:
            print(f"  No changes needed for this pair.")

    # Report ambiguous matches
    if AMBIGUOUS_MATCHES:
        print(f"\n{'─' * 72}")
        print("AMBIGUOUS matches (not modified):")
        for es_file, reason in AMBIGUOUS_MATCHES:
            print(f"  ES {es_file}: {reason}")

    # Report errors
    if errors:
        print(f"\n{'─' * 72}")
        print("Errors / Conflicts:")
        for e in errors:
            print(e)

    print(f"\n{'─' * 72}")
    print(f"Part 1 summary: {len(changes_made)} changes made")
    for c in changes_made:
        print(c)

    return changes_made


# ═══════════════════════════════════════════════════════════════════════════
# PART 2: Ensure ALL translation links are bidirectional
# ═══════════════════════════════════════════════════════════════════════════

def part2():
    print("\n" + "=" * 72)
    print("PART 2: Ensure ALL translation links are bidirectional")
    print("=" * 72)

    # Rebuild permalink index fresh (includes Part 1 changes)
    all_posts = {}  # permalink -> (filepath, content, front_matter, body)

    for directory in [POSTS_EN, POSTS_ES]:
        for filepath in glob.glob(os.path.join(directory, "*.html")):
            content = read_file(filepath)
            fm, body = extract_front_matter(content)
            if fm:
                permalink = get_field(fm, 'permalink')
                if permalink:
                    all_posts[permalink] = (filepath, content, fm, body)

    changes_made = []
    warnings = []

    # For each post with a translation field, check that the target links back
    for src_permalink in sorted(all_posts.keys()):
        src_path, src_content, src_fm, src_body = all_posts[src_permalink]
        src_trans = get_field(src_fm, 'translation')
        if not src_trans:
            continue

        # Find the target post
        if src_trans not in all_posts:
            warnings.append(
                f"  WARNING: {os.path.basename(src_path)} has translation: {src_trans} "
                f"but no post found at that permalink"
            )
            continue

        tgt_path, tgt_content, tgt_fm, tgt_body = all_posts[src_trans]
        tgt_trans = get_field(tgt_fm, 'translation')

        if tgt_trans == src_permalink:
            # Already bidirectional, good
            continue

        if tgt_trans and tgt_trans != src_permalink:
            warnings.append(
                f"  WARNING: {os.path.basename(src_path)} (permalink: {src_permalink}) "
                f"links to {src_trans}, but that post already links to {tgt_trans} instead. "
                f"Not overwriting."
            )
            continue

        # Target has no translation field - add one pointing back to source
        tgt_fm_new = add_translation_field(tgt_fm, src_permalink)
        tgt_content_new = tgt_fm_new + tgt_body
        write_file(tgt_path, tgt_content_new)

        change_msg = (
            f"  Fixed: {os.path.basename(tgt_path)} now links back to {src_permalink} "
            f"(was linked from {os.path.basename(src_path)})"
        )
        changes_made.append(change_msg)
        print(change_msg)

        # Update in-memory data so subsequent checks see this change
        all_posts[src_trans] = (tgt_path, tgt_content_new, tgt_fm_new, tgt_body)

    if warnings:
        print(f"\n{'─' * 72}")
        print("Warnings:")
        for w in warnings:
            print(w)

    print(f"\n{'─' * 72}")
    print(f"Part 2 summary: {len(changes_made)} bidirectional links fixed")
    if not changes_made:
        print("  All existing translation links were already bidirectional.")
    else:
        for c in changes_made:
            print(c)

    return changes_made


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Building indexes...")
    permalink_index = build_permalink_index()
    file_index = build_file_index()
    print(f"  {len(permalink_index)} posts indexed by permalink")
    print(f"  {len(file_index)} posts indexed by filename")
    print()

    part1_changes = part1(file_index, permalink_index)
    part2_changes = part2()

    print("\n" + "=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    total = len(part1_changes) + len(part2_changes)
    print(f"  Part 1: {len(part1_changes)} translation links added to orphan pairs")
    print(f"  Part 2: {len(part2_changes)} bidirectional links fixed")
    print(f"  Total changes: {total}")
