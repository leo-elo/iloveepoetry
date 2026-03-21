#!/usr/bin/env python3
"""
Fix "Read more about this work at:" sections in Jekyll post files.

This script handles two main patterns found across 30 post files:

Pattern A: "Read more about this work at:" text + <strong>NAME</strong>: <a href="URL">URL_TEXT</a>
  - Found in Alvaro Seica's posts (Portuguese electronic literature series)
  - Both English and Spanish versions
  - Some have <strong> tags, some don't

Pattern B: ELMCIP image thumbnail links
  - <a href="ELMCIP_URL"><em><img alt="Read more about this work at ELMCIP." .../></em></a>
  - Found in Leonardo Flores' posts
  - Various attribute orderings and quote styles

Transformation:
  - Pattern A: Consolidate into single line with comma-separated links
    <br><br>Read more about this work at: <a href="URL1" target="_blank" rel="noopener">Name1</a>, <a href="URL2" target="_blank" rel="noopener">Name2</a>
  - Pattern B: Replace ELMCIP image with text link
    <br><br>Read more about this work at: <a href="URL" target="_blank" rel="noopener">ELMCIP</a>
"""

import re
import os

BASE_DIR = "/Users/floresll/Desktop/iloveepoetry"

# All 30 files to process
FILES = [
    # English files
    "_posts/en/2015-04-13-computer-poetry-by-silvestre-pestana.html",
    "_posts/en/2015-04-20-algorritmos-infopoemas-by-e-m-de-melo-e-castro.html",
    "_posts/en/2015-04-06-maquinas-pensantes-by-pedro-barbosa.html",
    "_posts/en/2015-03-30-a-literatura-cibernetica-2-by-pedro-barbosa.html",
    "_posts/en/2015-03-16-roda-lume-by-e-m-de-melo-e-castro.html",
    "_posts/en/2015-03-23-a-literatura-cibernetica-1-by-pedro-barbosa.html",
    "_posts/en/2013-03-01-walt-fml-whitman-by-mark-sample.html",
    "_posts/en/2013-02-20-google-poetics-by-sampsa-nuotio-and-raisa-omaheimo.html",
    "_posts/en/2013-02-21-217-views-of-the-tokaido-line-by-will-luers.html",
    "_posts/en/2013-02-19-10-print-ebooks-by-mark-sample.html",
    "_posts/en/2013-02-11-to-be-or-not-to-be-mouchette-by-martine-neddam.html",
    "_posts/en/2012-10-14-internal-damage-data-and-fleshis-tics-by-mez-breeze.html",
    "_posts/en/2012-07-14-agrippa-part-1-of-4-by-william-gibson.html",
    "_posts/en/2012-06-17-10-print-chr-205-5-rnd-1-goto-10-by-anonymous.html",
    "_posts/en/2012-05-19-along-the-briny-beach-by-j-r-carpenter.html",
    # Spanish files
    "_posts/es/2018-04-17-walt-fml-whitman-por-mark-sample.html",
    "_posts/es/2018-04-12-to-be-or-not-to-be-mouchette-por-martine-neddam.html",
    "_posts/es/2018-04-12-google-poetics-por-sampsa-nuotio-y-raisa-omaheimo.html",
    "_posts/es/2018-04-12-10-print-ebooks-por-mark-sample.html",
    "_posts/es/2018-04-12-217-views-of-the-tokaido-line-por-will-luers.html",
    "_posts/es/2018-03-28-internal-damage-data-y-fleshis-tics-por-mez-breeze.html",
    "_posts/es/2018-03-15-agrippa-por-william-gibson-parte-1-de-4.html",
    "_posts/es/2018-03-13-10-print-chr205-5rnd1-goto-10-por-anonymous-por-medio-de-nick-montfort.html",
    "_posts/es/2018-03-07-along-the-briny-beach-por-j-r-carpenter.html",
    "_posts/es/2018-03-16-roda-lume-por-e-m-de-melo-e-castro.html",
    "_posts/es/2018-03-16-maquinas-pensantes-por-pedro-barbosa.html",
    "_posts/es/2018-03-16-a-literatura-cibernetica-2-por-pedro-barbosa.html",
    "_posts/es/2018-03-16-algorritmos-infopoemas-por-e-m-de-melo-e-castro.html",
    "_posts/es/2018-03-16-computer-poetry-por-silvestre-pestana.html",
    "_posts/es/2018-03-16-a-literatura-cibernetica-1-by-pedro-barbosa-2.html",
]


def fix_pattern_a(content, filepath):
    """
    Fix Pattern A: "Read more about this work at:" followed by resource lines.

    Variations found:
    - English: "Read more about this work at:"
    - Spanish: "Lee más sobre esta obra en:", "Lea más sobre este trabajo en:",
      "Lee más sobre esta obre en:", wrapped in <span> tags, etc.

    Resource line formats:
    - <strong>NAME</strong>: <a href="URL" ...>URL_TEXT</a>
    - NAME: <a href="URL" ...>URL_TEXT</a>  (without bold tags)
    """

    # Match the "read more" header text (English and Spanish variants)
    # This needs to handle:
    # 1. "Read more about this work at:"
    # 2. "Lee más sobre esta obra en:"
    # 3. "Lea más sobre este trabajo en:"
    # 4. "Lee más sobre esta obre en:" (typo variant)
    # 5. <span ...><span ...>Lea más sobre este trabajo en</span></span>:
    #    (nested spans with colon outside)
    read_more_patterns = [
        r'Read more about this work at:',
        r'Lee más sobre esta obra en:',
        r'Lea más sobre este trabajo en:',
        r'Lee más sobre esta obre en:',  # typo variant
        r'(?:<span[^>]*>)+Lea más sobre este trabajo en(?:</span>)+\s*:',
        r'(?:<span[^>]*>)+Lee más sobre esta obra en(?:</span>)+\s*:',
        r'(?:<span[^>]*>)+Lea más sobre este trabajo en(?:</span>)+\s*(?:</span>)+\s*:',
    ]

    changes = []

    for rm_pattern in read_more_patterns:
        # Build a regex that captures the "read more" line and all following resource lines
        # The resource lines can be separated by newlines, and may or may not have <strong> tags
        # Pattern: header text + newlines + resource_line(s) + optional trailing whitespace
        resource_line = r'(?:<strong>([^<]+)</strong>|([A-Z][A-Za-z._-]+))\s*:\s*<a\s+href="([^"]+)"[^>]*>[^<]*</a>'

        # Build full pattern: header + whitespace/newlines + one or more resource lines
        full_pattern = (
            r'(' + rm_pattern + r')'  # Group 1: the header text
            r'(\s*\n\s*'  # whitespace/newlines after header
            r'(?:(?:<strong>[^<]+</strong>|[A-Z][A-Za-z._-]+)\s*:\s*<a\s+href="[^"]+"[^>]*>[^<]*</a>\s*\n?\s*)+'  # one or more resource lines
            r')'
        )

        matches = list(re.finditer(full_pattern, content))

        for match in matches:
            original_block = match.group(0)
            header = match.group(1)
            resource_block = match.group(2)

            # Determine the correct "Read more" text to use
            # Strip any span tags from header
            clean_header = re.sub(r'<span[^>]*>', '', header)
            clean_header = re.sub(r'</span>\s*', '', clean_header)
            clean_header = clean_header.strip()

            # Determine language for the header
            if 'Read more' in clean_header:
                header_text = 'Read more about this work at:'
            elif 'Lee más sobre esta obra' in clean_header:
                header_text = 'Lee más sobre esta obra en:'
            elif 'Lee más sobre esta obre' in clean_header:
                # Fix the typo
                header_text = 'Lee más sobre esta obra en:'
            elif 'Lea más sobre este trabajo' in clean_header:
                header_text = 'Lee más sobre esta obra en:'
            else:
                header_text = clean_header

            # Extract all resource entries from the resource block
            resources = []
            for res_match in re.finditer(resource_line, resource_block):
                name = res_match.group(1) if res_match.group(1) else res_match.group(2)
                url = res_match.group(3)
                resources.append((name.strip(), url))

            if not resources:
                continue

            # Build the replacement
            links = []
            for name, url in resources:
                links.append(f'<a href="{url}" target="_blank" rel="noopener">{name}</a>')

            # Check what comes before the match to determine if we need <br><br>
            match_start = match.start()
            text_before = content[:match_start]
            # Check if <br><br> is already right before
            has_br = text_before.rstrip().endswith('<br><br>')
            # Also check for </blockquote> right before (some posts end with a blockquote before "Read more")
            stripped_before = text_before.rstrip()

            if has_br:
                replacement = f'{header_text} {", ".join(links)}'
            else:
                replacement = f'<br><br>{header_text} {", ".join(links)}'

            # Ensure there's a newline after the replacement so following content
            # (e.g., "Traducido por...") doesn't run into the same line
            replacement += '\n'

            # Replace the original block with our new version
            content = content[:match.start()] + replacement + content[match.end():]

            changes.append(f"  Pattern A: Replaced '{clean_header}' block with {len(resources)} resource link(s)")
            # After replacement, we need to break since positions have changed
            break

        # If we made a change, re-run this pattern in case there are more matches
        # (unlikely but safe)

    return content, changes


def fix_pattern_b(content, filepath):
    """
    Fix Pattern B: ELMCIP image thumbnail links.

    These are <a> tags wrapping <img> tags with ELMCIP logos.
    Various formats found:
    - <a href="URL"><em><img alt='ELMCIP logo...' src="...elmcipthumb.png" .../></em></a>
    - <a href="URL" target="_blank"><em><img .../></em></a>
    - <a href="URL" target="_blank" rel="noopener"><em><img .../></em></a>
    - <a href="ELMCIP logo with text:..."><img .../></a>  (broken href variant)
    - Various attribute orderings in <img> tags

    Some of these are preceded by other content on the same line or nearby.
    """

    changes = []

    # Pattern to match ELMCIP image links
    # The img src contains "elmcipthumb" and alt text often mentions "Read more" or "ELMCIP"
    # Note: Some files have broken hrefs with nested quotes, e.g.:
    #   href="ELMCIP logo with text: "Read more about this work at ELMCIP.""
    # We use a broad match for the <a> tag to handle these cases.
    elmcip_img_pattern = (
        r'\n*\s*'  # optional leading whitespace/newlines
        r'<a\s+href="(.*?)"[^>]*>'  # <a> with href (non-greedy to handle broken quotes)
        r'\s*(?:<em>)?\s*'  # optional <em>
        r'<img\s+[^>]*?(?:elmcipthumb|ELMCIP)[^>]*/?\s*>'  # <img> with elmcipthumb or ELMCIP
        r'\s*(?:</em>)?\s*'  # optional </em>
        r'</a>'
    )

    matches = list(re.finditer(elmcip_img_pattern, content, re.IGNORECASE))

    for match in reversed(matches):  # Process in reverse to maintain positions
        original = match.group(0)
        href = match.group(1)

        # Some hrefs are broken - they contain the alt text instead of a URL
        # e.g., href='ELMCIP logo with text: "Read more about this work at ELMCIP."'
        if not href.startswith('http') and not href.startswith('/'):
            # Broken href - try to get the ELMCIP URL from the elmcip_url in frontmatter
            elmcip_url_match = re.search(r'elmcip_url:\s*"([^"]+)"', content)
            if elmcip_url_match:
                href = elmcip_url_match.group(1)
            else:
                # No valid ELMCIP URL available at all - remove the broken image link
                content = content[:match.start()] + content[match.end():]
                changes.append(f"  Pattern B: Removed broken ELMCIP image link (no valid URL available)")
                continue

        # Normalize the ELMCIP URL
        # Convert http://www.elmcip.net/... to https://elmcip.net/...
        href = re.sub(r'^https?://(?:www\.)?elmcip\.net/', 'https://elmcip.net/', href)

        # Determine the language of the post
        is_spanish = '/_posts/es/' in filepath

        if is_spanish:
            header_text = 'Lee más sobre esta obra en:'
        else:
            header_text = 'Read more about this work at:'

        # Build replacement
        replacement = f'\n<br><br>{header_text} <a href="{href}" target="_blank" rel="noopener">ELMCIP</a>\n'

        # Check if there's already a <br><br> before this element on the preceding line(s)
        text_before_match = content[:match.start()]
        stripped_before = text_before_match.rstrip()

        # If what's right before is already a <br><br>, don't add another one
        # But we need to be careful: sometimes there's a "Featured in" line with <br><br> before it
        # In that case we just need the read more line without extra <br><br>

        # Check if the immediately preceding non-whitespace content ends with <br><br>
        if stripped_before.endswith('<br><br>'):
            replacement = f'\n{header_text} <a href="{href}" target="_blank" rel="noopener">ELMCIP</a>\n'

        content = content[:match.start()] + replacement + content[match.end():]
        changes.append(f"  Pattern B: Replaced ELMCIP image link -> text link to {href}")

    return content, changes


def process_file(rel_path):
    """Process a single file."""
    filepath = os.path.join(BASE_DIR, rel_path)

    if not os.path.exists(filepath):
        print(f"WARNING: File not found: {filepath}")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()

    content = original_content
    all_changes = []

    # Apply Pattern A fixes
    content, changes_a = fix_pattern_a(content, filepath)
    all_changes.extend(changes_a)

    # Apply Pattern B fixes
    content, changes_b = fix_pattern_b(content, filepath)
    all_changes.extend(changes_b)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"MODIFIED: {rel_path}")
        for change in all_changes:
            print(change)
        return True
    else:
        print(f"NO CHANGE: {rel_path}")
        return False


def main():
    print("=" * 70)
    print("Fixing 'Read more about this work at:' sections")
    print("=" * 70)
    print()

    modified_count = 0
    unchanged_count = 0

    for rel_path in FILES:
        result = process_file(rel_path)
        if result:
            modified_count += 1
        else:
            unchanged_count += 1
        print()

    print("=" * 70)
    print(f"SUMMARY: {modified_count} files modified, {unchanged_count} files unchanged")
    print("=" * 70)


if __name__ == "__main__":
    main()
