#!/usr/bin/env python3
"""
fix_inline_translators.py

Scans all Spanish posts in _posts/es/ for inline "Traducido por" credits,
compares them against the YAML front matter `translator` field, removes the
inline text, and (if needed) adds the translator to front matter.

Known typos of "Reina Santiago" are normalized before comparison:
  Reina Santaigo, Reina Santigo, Riena Santiago, Reina Sntiago, reina Santiago
"""

import os
import re
import sys

POSTS_DIR = "/Users/floresll/Desktop/iloveepoetry/_posts/es/"

# ---------------------------------------------------------------------------
# Known typo map  (inline text lowercase -> canonical name)
# ---------------------------------------------------------------------------
KNOWN_TYPOS = {
    "reina santaigo":    "Reina Santiago",
    "reina santigo":     "Reina Santiago",
    "riena santiago":    "Reina Santiago",
    "reina sntiago":     "Reina Santiago",
    "reina santiago":    "Reina Santiago",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def split_front_matter(text):
    """Return (front_matter_str, body_str).
    front_matter_str includes the opening and closing ---.
    body_str is everything after the closing ---.
    """
    if not text.startswith("---"):
        return ("", text)
    # Find the second ---
    second = text.find("\n---", 3)
    if second == -1:
        return ("", text)
    # The front matter ends after the closing --- line
    end_of_closing = text.index("\n", second + 1) + 1
    return (text[:end_of_closing], text[end_of_closing:])


def get_translator_from_fm(fm_text):
    """Extract the translator value from front matter text."""
    m = re.search(r'^translator:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return None


def add_translator_to_fm(fm_text, translator_name):
    """Add a translator field to the front matter, after the author line if present."""
    lines = fm_text.split("\n")
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and line.startswith("author:"):
            new_lines.append('translator: "{}"'.format(translator_name))
            inserted = True
    if not inserted:
        # Insert before the closing ---
        final_lines = []
        for i, line in enumerate(new_lines):
            # The closing --- is the last --- line
            if line.strip() == "---" and i > 0 and i == len(new_lines) - 2:
                final_lines.append('translator: "{}"'.format(translator_name))
            final_lines.append(line)
        new_lines = final_lines
    return "\n".join(new_lines)


def normalize_name(name):
    """Normalize a translator name: strip whitespace, HTML, punctuation."""
    # Remove HTML tags
    name = re.sub(r'<[^>]+>', '', name)
    # Remove &nbsp;
    name = name.replace('&nbsp;', ' ')
    # Remove trailing period
    name = name.rstrip('.')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def canonical_name(name):
    """Resolve known typos to the canonical form."""
    lower = name.lower().strip()
    if lower in KNOWN_TYPOS:
        return KNOWN_TYPOS[lower]
    return name


def names_match(fm_name, inline_name):
    """
    Check if front matter name and inline name refer to the same person.
    The front matter may use a shorter form (e.g. "Alan Valle" vs "Alan Valle Monagas").
    Also handles "Julianna Canabal" vs "Julianna Canabal-Rodriguez".
    """
    fm_canon = canonical_name(fm_name).lower().strip()
    in_canon = canonical_name(inline_name).lower().strip()

    if fm_canon == in_canon:
        return True

    # Check if one is a prefix of the other
    if in_canon.startswith(fm_canon) or fm_canon.startswith(in_canon):
        return True

    # Handle hyphen vs space in last name
    if fm_canon.replace("-", " ") == in_canon.replace("-", " "):
        return True
    if in_canon.replace("-", " ").startswith(fm_canon.replace("-", " ")):
        return True

    return False


def extract_inline_translator(line):
    """
    If the line contains a 'Traducido/a por' credit, extract and return the
    translator name (cleaned). Otherwise return None.
    """
    m = re.search(r'Traducid[oa]\s+por\s*:?\s*(.+)', line, re.IGNORECASE)
    if not m:
        # Also check for missing space: "Traducido porReina"
        m = re.search(r'Traducid[oa]\s+por(\S.+)', line, re.IGNORECASE)
        if not m:
            return None
    raw = m.group(1)
    # Remove closing HTML tags
    raw = re.sub(r'</\w+>', '', raw)
    # Remove any remaining HTML tags
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = normalize_name(raw)
    return raw if raw else None


def is_only_credit(line):
    """Return True if the entire line is just a translator credit (possibly HTML-wrapped)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Remove all HTML wrappers and check if what remains is just "Traducid[oa] por ..."
    text = re.sub(r'<[^>]+>', '', stripped).strip()
    if re.match(r'^Traducid[oa]\s+por\s*:?\s*.+$', text, re.IGNORECASE):
        return True
    return False


def is_empty_or_nbsp(line):
    """Check if a line is empty, just whitespace, or just &nbsp; / empty HTML tags / <br>."""
    stripped = line.strip()
    if not stripped:
        return True
    # Check for lines that are only &nbsp;
    if stripped == '&nbsp;':
        return True
    # Check for empty p tags, br tags, empty divs
    if re.match(r'^(?:<p>\s*</p>|<br\s*/?>|<div>\s*</div>|</em>|</div>|<p>\s*&nbsp;\s*</p>)$',
                stripped, re.IGNORECASE):
        return True
    return False


def process_file(filepath):
    """
    Process a single file. Returns a dict with details, or None if no changes.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fm_text, body = split_front_matter(content)
    if not fm_text:
        return None

    fm_translator = get_translator_from_fm(fm_text)

    # Process body line by line
    body_lines = body.split('\n')
    new_lines = []
    lines_removed = 0
    inline_names_found = []

    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        inline_name = extract_inline_translator(line)

        if inline_name is not None:
            inline_names_found.append(inline_name)

            if is_only_credit(line):
                # Remove the entire line
                lines_removed += 1

                # Also look back to remove an immediately preceding blank/&nbsp; line
                if new_lines and is_empty_or_nbsp(new_lines[-1]):
                    new_lines.pop()
                    lines_removed += 1

                # Look ahead: if next line is empty/&nbsp;/closing tag remnant, remove it too
                if i + 1 < len(body_lines) and is_empty_or_nbsp(body_lines[i + 1]):
                    i += 1  # skip the next line too
                    lines_removed += 1

                i += 1
                continue
            else:
                # The credit is embedded in a longer line — strip just the credit portion
                # Remove trailing portion: <div...>Traducido por...</div> etc.
                cleaned = line
                # Try removing trailing translator credit with wrapping divs
                cleaned = re.sub(
                    r'<div[^>]*>\s*</div>\s*<div[^>]*>\s*Traducid[oa]\s+por\s*:?\s*[^<]*(?:</div>)?\s*$',
                    '',
                    cleaned,
                    flags=re.IGNORECASE
                )
                if cleaned == line:
                    # Try a more general pattern for trailing credit with various HTML wrappers
                    cleaned = re.sub(
                        r'(?:<(?:div|p|span|em|strong)[^>]*>\s*)*'
                        r'Traducid[oa]\s+por\s*:?\s*[^<]+(?:</\w+>)*\s*$',
                        '',
                        cleaned,
                        flags=re.IGNORECASE
                    )
                if cleaned != line:
                    lines_removed += 1
                    new_lines.append(cleaned)
                    i += 1
                    continue
                else:
                    # Last resort: couldn't cleanly extract, just remove the whole line
                    lines_removed += 1
                    i += 1
                    continue

        new_lines.append(line)
        i += 1

    if not inline_names_found:
        return None

    # Determine the primary inline translator name
    primary_inline = inline_names_found[0]
    canonical_inline = canonical_name(primary_inline)

    # Build result
    result = {
        'file': os.path.basename(filepath),
        'filepath': filepath,
        'fm_translator': fm_translator,
        'inline_name': primary_inline,
        'canonical_inline': canonical_inline,
        'all_inline_names': inline_names_found,
        'lines_removed': lines_removed,
        'matched': False,
        'discrepancy': False,
        'added_to_fm': False,
    }

    new_fm = fm_text

    if fm_translator:
        if names_match(fm_translator, canonical_inline):
            result['matched'] = True
        else:
            result['discrepancy'] = True
    else:
        # No translator in front matter — add it
        result['added_to_fm'] = True
        new_fm = add_translator_to_fm(fm_text, canonical_inline)

    # Write back
    new_content = new_fm + '\n'.join(new_lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    files = sorted([
        os.path.join(POSTS_DIR, f)
        for f in os.listdir(POSTS_DIR)
        if f.endswith('.html')
    ])

    print("Scanning {} Spanish posts in {}\n".format(len(files), POSTS_DIR))

    results = []
    for fpath in files:
        r = process_file(fpath)
        if r:
            results.append(r)

    # Categorize
    matched = [r for r in results if r['matched']]
    discrepancies = [r for r in results if r['discrepancy']]
    added = [r for r in results if r['added_to_fm']]
    total_lines = sum(r['lines_removed'] for r in results)

    # Report
    print("=" * 80)
    print("INLINE TRANSLATOR CREDIT REMOVAL REPORT")
    print("=" * 80)
    print("\nTotal posts scanned:                    {}".format(len(files)))
    print("Posts with inline translator credits:    {}".format(len(results)))
    print("  - Matched front matter (verified):     {}".format(len(matched)))
    print("  - Discrepancies (front matter wins):   {}".format(len(discrepancies)))
    print("  - No front matter (added translator):  {}".format(len(added)))
    print("Total lines removed/modified:            {}".format(total_lines))

    if matched:
        print("\n" + "-" * 80)
        print("MATCHED & REMOVED ({} posts):".format(len(matched)))
        print("-" * 80)
        for r in matched:
            print("  {}".format(r['file']))
            print("    FM: {}  |  Inline: {}  |  Lines removed: {}".format(
                r['fm_translator'], r['inline_name'], r['lines_removed']))

    if discrepancies:
        print("\n" + "-" * 80)
        print("DISCREPANCIES ({} posts) -- front matter is authoritative, inline removed:".format(
            len(discrepancies)))
        print("-" * 80)
        for r in discrepancies:
            print("  {}".format(r['file']))
            print('    FM translator:     "{}"'.format(r['fm_translator']))
            print('    Inline translator: "{}"'.format(r['inline_name']))
            print("    Lines removed: {}".format(r['lines_removed']))

    if added:
        print("\n" + "-" * 80)
        print("ADDED TO FRONT MATTER ({} posts) -- inline removed, translator added to FM:".format(
            len(added)))
        print("-" * 80)
        for r in added:
            print("  {}".format(r['file']))
            print('    Added translator: "{}"'.format(r['canonical_inline']))
            print("    Lines removed: {}".format(r['lines_removed']))

    # Summary of unique translator names encountered inline
    all_names = {}
    for r in results:
        for name in r['all_inline_names']:
            canon = canonical_name(name)
            all_names[canon] = all_names.get(canon, 0) + 1
    print("\n" + "-" * 80)
    print("UNIQUE INLINE TRANSLATOR NAMES (after normalization):")
    print("-" * 80)
    for name, count in sorted(all_names.items(), key=lambda x: -x[1]):
        print("  {}: {} occurrences".format(name, count))

    print("\nDone. {} files modified.".format(len(results)))


if __name__ == "__main__":
    main()
