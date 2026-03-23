#!/usr/bin/env python3
"""
Add <br><br> before "Featured in" / "Presentado en" / "Exhibido en" lines
in Jekyll HTML post files, but only if a <br> isn't already present
immediately before the match.

This script handles the following patterns:
  - <strong>Featured in ...
  - <strong style="...">Featured in ...
  - <b>Featured in ...
  - <a href=...><strong style="...">Featured in ...
  - <p ...>Featured in ...
  - <p ...><strong>Featured in ...
  - <div ...><strong>Featured in ...  (only when no visible text precedes it)
  - <strong>Presentado en ...
  - <strong>Exhibido en ...
  - And similar variants with <b>, styling, etc.

The "Featured in" text typically appears near the end of post body content.
"""

import os
import re
import sys


# Directories to scan
POST_DIRS = [
    "/Users/floresll/Desktop/iloveepoetry/_posts/en/",
    "/Users/floresll/Desktop/iloveepoetry/_posts/es/",
]

# The phrases we're looking for
FEATURED_PHRASES = [
    "Featured in",
    "Presentado en",
    "Exhibido en",
]

# Build a regex that matches one of the featured phrases
PHRASE_PATTERN = re.compile(
    r"(" + "|".join(re.escape(p) for p in FEATURED_PHRASES) + r")"
)


def has_visible_text_before_phrase(line, phrase_match_start):
    """
    Check if there is substantial visible text content on the line before the
    matched phrase. This handles cases where 'Featured in' is embedded in a
    long paragraph within a <div> tag.
    """
    before = line[:phrase_match_start]
    # Strip all HTML tags
    visible = re.sub(r"<[^>]*>", "", before).strip()
    # If there's more than ~20 chars of visible text, it's inline
    return len(visible) > 20


def process_file(filepath):
    """
    Process a single HTML file. Returns True if the file was modified.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    modified = False
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this line contains a Featured phrase
        match = PHRASE_PATTERN.search(stripped)

        if match:
            # Check if the phrase is inline within a long paragraph
            if has_visible_text_before_phrase(stripped, match.start()):
                # This is an inline occurrence (e.g., inside a <div> with
                # preceding paragraph text). Insert <br><br> before the
                # tag that starts the "Featured in" segment.
                #
                # Find the tag sequence leading into the phrase in the
                # original (non-stripped) line.
                original_match = PHRASE_PATTERN.search(line)
                if original_match:
                    insert_pos = original_match.start()
                    # Walk backwards to find the start of the enclosing tag
                    # (e.g., <strong>, <b>, <a href=...>)
                    tag_start = insert_pos
                    search_back = line[:insert_pos]
                    # Find the last sequence of tags immediately before the phrase
                    tag_sequence = re.search(
                        r"((?:<(?:strong|b|a)\b[^>]*>\s*)+)$",
                        search_back,
                        re.IGNORECASE,
                    )
                    if tag_sequence and tag_sequence.group():
                        tag_start = tag_sequence.start()

                    # Check if <br> already immediately precedes this point
                    before_insert = line[:tag_start].rstrip()
                    if not re.search(r"<br\s*/?\s*>\s*$", before_insert, re.IGNORECASE):
                        new_line = (
                            line[:tag_start] + "<br><br>" + line[tag_start:]
                        )
                        new_lines.append(new_line)
                        modified = True
                        i += 1
                        continue

                # If we couldn't do the inline insert, just append as-is
                new_lines.append(line)
                i += 1
                continue

            # Standard case: the Featured phrase is at/near the start of the
            # line (possibly preceded only by HTML tags).
            # Check if the previous line (in new_lines) already ends with <br>.
            prev_content = ""
            if new_lines:
                prev_content = new_lines[-1].rstrip()

            already_has_br = bool(
                re.search(r"<br\s*/?\s*>\s*$", prev_content, re.IGNORECASE)
            )

            if not already_has_br:
                # Determine indentation of the current line
                leading_ws = line[: len(line) - len(line.lstrip())]
                new_lines.append(leading_ws + "<br><br>")
                modified = True

        new_lines.append(line)
        i += 1

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    return modified


def main():
    total_modified = 0
    total_scanned = 0
    modified_files = []

    for post_dir in POST_DIRS:
        if not os.path.isdir(post_dir):
            print(f"WARNING: Directory not found: {post_dir}")
            continue

        for filename in sorted(os.listdir(post_dir)):
            if not filename.endswith(".html"):
                continue

            filepath = os.path.join(post_dir, filename)
            total_scanned += 1

            if process_file(filepath):
                total_modified += 1
                modified_files.append(filepath)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Featured-in Line Break Insertion Summary")
    print(f"{'='*60}")
    print(f"  Files scanned:  {total_scanned}")
    print(f"  Files modified: {total_modified}")
    print(f"{'='*60}\n")

    if modified_files:
        print("Modified files:")
        for f in modified_files:
            # Show just the relative part
            short = f.split("_posts/")[-1] if "_posts/" in f else f
            print(f"  {short}")
    else:
        print("No files needed modification.")


if __name__ == "__main__":
    main()
