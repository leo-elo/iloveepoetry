#!/usr/bin/env python3
"""
Extract the first image from each post's HTML body and set it as
the featured_image in the YAML front matter.  Then remove the first
<figure> (or standalone <img>) from the body so the image is not
duplicated when the layout renders the featured image.
"""

import os
import re
import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST_DIRS = [
    os.path.join(PROJECT_ROOT, "_posts", "en"),
    os.path.join(PROJECT_ROOT, "_posts", "es"),
]

# ── regex helpers ──────────────────────────────────────────────────
# Match the first <img …> tag and capture its src attribute.
IMG_RE = re.compile(r'<img\s[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\'][^>]*?/?>', re.IGNORECASE)

# Match a <figure class="wp-caption"> … </figure> block that contains the first <img>.
# We use a non-greedy match so we grab only the nearest closing </figure>.
FIGURE_RE = re.compile(
    r'<figure\b[^>]*class\s*=\s*["\'][^"\']*wp-caption[^"\']*["\'][^>]*>.*?</figure>',
    re.IGNORECASE | re.DOTALL,
)


def parse_front_matter(text):
    """Return (front_matter_str, body_str) split on the --- delimiters.

    front_matter_str does NOT include the delimiters.
    """
    # Front matter lives between the first two --- lines.
    # The file must start with ---.
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end == -1:
        return None, text
    # end points to the start of the closing ---
    fm = text[3:end].strip()
    body = text[end + 3:]  # everything after the closing ---
    return fm, body


def build_file(front_matter, body):
    """Re-assemble the file from front matter and body."""
    return "---\n" + front_matter + "\n---\n" + body


def escape_yaml_value(value):
    """Wrap value in double quotes, escaping inner double-quotes and backslashes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def first_img_is_inside_figure(body, img_match):
    """Determine whether the first <img> sits inside a <figure class="wp-caption">."""
    img_start = img_match.start()
    # Look for the nearest preceding <figure ...wp-caption...> tag
    for fig_match in FIGURE_RE.finditer(body):
        if fig_match.start() <= img_start <= fig_match.end():
            return fig_match  # return the figure match object
    return None


def process_file(filepath):
    """Process one post file.  Returns a status string:
        'already'   – already had featured_image
        'added'     – featured_image was extracted and added
        'no_image'  – no <img> found in body
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        text = fh.read()

    fm, body = parse_front_matter(text)
    if fm is None:
        return "no_image"  # can't parse front matter

    # Check if featured_image already exists
    if re.search(r'^featured_image\s*:', fm, re.MULTILINE):
        return "already"

    # Find the first <img> in the body
    img_match = IMG_RE.search(body)
    if img_match is None:
        return "no_image"

    src = img_match.group(1)

    # ── Remove the first image element from the body ──────────────
    fig_match = first_img_is_inside_figure(body, img_match)
    if fig_match is not None:
        # Remove the whole <figure>…</figure>
        body = body[:fig_match.start()] + body[fig_match.end():]
    else:
        # Remove just the standalone <img> tag
        body = body[:img_match.start()] + body[img_match.end():]

    # ── Add featured_image to front matter ────────────────────────
    fm += "\nfeatured_image: " + escape_yaml_value(src)

    # Write back
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(build_file(fm, body))

    return "added"


def main():
    stats = {"processed": 0, "already": 0, "added": 0, "no_image": 0}

    for post_dir in POST_DIRS:
        pattern = os.path.join(post_dir, "*.html")
        files = sorted(glob.glob(pattern))
        for filepath in files:
            result = process_file(filepath)
            stats["processed"] += 1
            stats[result] += 1

    print("=" * 60)
    print("Featured-image extraction complete")
    print("=" * 60)
    print(f"  Total posts processed : {stats['processed']}")
    print(f"  Already had featured  : {stats['already']}")
    print(f"  New featured_image set: {stats['added']}")
    print(f"  No images found       : {stats['no_image']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
